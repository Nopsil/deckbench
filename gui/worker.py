"""界面后台的工作进程：调用模拟器现有的批量/实验函数，并按行输出进度。

  batch   —— 整局批量（复用 tools/batch.py 的 _init / _one / force_cards_hook / make_agent），imap 逐局报告进度
  combat  —— 战斗实验（复用 sts2sim.runner 的 plan / _task / make_report），分块报告进度
  cards   —— 列出可强制加入/移除的卡牌（JSON）
  validate-mod —— 用模拟器的 ModSet 试加载一个 mod
  mod-check —— 检查 / 试注册一个 YAML 数据 mod（整局用），输出问题、提醒、角色和每张牌在游戏里的 ID（JSON）

进度协议（stdout 单独一行）：@@PROGRESS {"done": n, "total": m}；结束：@@DONE {...}
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui import i18n, paths  # noqa: E402

paths.setup_sys_path()


def emit(tag, obj):
    print(f"@@{tag} " + json.dumps(obj, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------- 整局批量
def _one_safe(args):
    """batch._one；没有 SIGALRM 的平台（Windows）去掉超时，其余逻辑一致。"""
    import signal
    import batch
    if hasattr(signal, "SIGALRM"):
        return batch._one(args)
    char, asc, seed = args
    batch._load_mods(char)
    from sts2sim.engine.run import play_run
    A = batch.AGENT
    hooks = [batch.force_cards_hook(A["force"], A.get("replace", ()))] if A.get("force") or A.get("replace") else []
    ag = None
    try:
        ag = batch.wrap_log(batch.build_agent(seed), char, asc, seed)
        r = play_run(char, asc, seed, agent=ag, setup_hooks=hooks)
        d = r.to_dict()
    except Exception:
        import traceback
        d = {"victory": False, "floor": -1, "act": 0, "path": [], "combats": [], "error": traceback.format_exc()[-2000:]}
    if ag is not None and getattr(ag, "mstats", None):
        d["mstats"] = ag.mstats
    d["seed"] = seed
    d["char"] = char
    d["asc"] = asc
    d["style"] = A.get("style") or "standard"
    return d


def _batch_init(cfg):
    paths.setup_sys_path()
    import batch
    batch._init(cfg)


def _style_list():
    from sts2sim.engine import style as ST
    return ST.list_styles(i18n.current())


def cmd_batch(a):
    import batch  # noqa: F401  (tools/batch.py)
    if a.game_seed:
        jobs = [(a.char, a.asc, s) for s in batch.game_seeds(a.game_seed)]
    else:
        jobs = [(a.char, a.asc, f"R{i}") for i in range(a.start, a.start + a.n)]
    akw = {"width": a.width, "depth": a.depth} if a.agent == "search" else {}
    if a.agent.startswith(("strong", "learned", "modai")):
        akw.update(boss_aware=True, boss_search=False)
    cfg = {"name": a.agent, "kw": akw, "variant": a.variant or None,
           "force": [x for x in a.force.split(",") if x], "replace": [x for x in a.replace.split(",") if x],
           "timeout": a.timeout or (60 if a.agent == "heuristic" else 900), "log_dir": a.log_dir or None,
           "mods": [os.path.abspath(m) for m in a.mod], "style": batch.check_style(a.style, a.agent)}
    if cfg["mods"]:
        batch._check_mods(cfg["mods"], a.char, cfg["variant"])   # 格式有错：大白话报错并退出（不开子进程）
    T = i18n.t
    if str(a.agent).startswith("mentor"):
        from sts2sim.engine import mentor_paths as MP
        err = MP.import_error()
        if err:
            safe = str(err).replace("{", "(").replace("}", ")")
            print(T("log.mentorUnavailable", err=safe), flush=True)
            sys.exit(2)
        if a.char not in MP.VANILLA:
            print(T("log.mentorVanilla", char=a.char), flush=True)
    none = T("common.none")
    seeds = T("log.seed", s=jobs[0][2]) if a.game_seed else T("log.seedRange", a=f"R{a.start}", b=f"R{a.start + a.n - 1}")
    print(T("log.batchStart", char=a.char, asc=a.asc, n=len(jobs), seeds=seeds, agent=a.agent, variant=a.variant or none,
            force=i18n.join(cfg["force"]) or none, replace=i18n.join(cfg["replace"]) or none, procs=a.procs), flush=True)
    sty = next((s["name"] for s in _style_list() if s["id"] == cfg["style"]), cfg["style"])
    print(T("log.style", style=sty), flush=True)
    emit("PROGRESS", {"done": 0, "total": len(jobs)})
    t = time.time()
    res = []
    with mp.Pool(a.procs, initializer=_batch_init, initargs=(cfg,)) as pool:
        for r in pool.imap_unordered(_one_safe, jobs, chunksize=1):
            res.append(r)
            tag = T("log.win") if r.get("victory") else (T("log.error") if r.get("error") else T("log.diedAt", floor=r.get("floor")))
            dr = r.get("death_room")
            where = ""
            if dr and not r.get("victory"):
                enc = i18n.game_text("events" if dr[1] == "Event" else "encounters", str(dr[2])) or str(dr[2])
                where = f" ({i18n.tr('room.', dr[1])} {enc})"
            print(f"[{len(res)}/{len(jobs)}] {r['seed']}: {tag}{where}", flush=True)
            emit("PROGRESS", {"done": len(res), "total": len(jobs)})
    order = {s: i for i, (_, _, s) in enumerate(jobs)}
    res.sort(key=lambda r: order.get(r["seed"], 0))
    dt = time.time() - t
    with open(a.out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    wins = sum(bool(r.get("victory")) for r in res)
    errs = sum(1 for r in res if r.get("error"))
    print(T("log.batchDone", wins=wins, n=len(res), errs=errs, secs=f"{dt:.1f}"), flush=True)
    if str(a.agent).startswith("mentor"):
        from sts2sim.engine.mentor_paths import mstats_line
        info = mstats_line(res)
        if info:
            print(T("log.mentorStats", ok=info["ok"], fb=info["fb"], pct=info["pct"], ppo=info["ppo"]), flush=True)
            if info["ok"] == 0 and info["fb"] > 0:
                print(T("log.mentorAllFallback"), flush=True)
            if info["ppo_net"] == 0 and info["ppo_fb"] > 0:
                print(T("log.mentorPpoFallback"), flush=True)
    emit("DONE", {"secs": dt, "out": a.out})


# ---------------------------------------------------------------- 战斗实验
def _combat_init():
    paths.setup_sys_path()
    from gui import modpatch
    modpatch.apply()


def cmd_combat(a):
    import yaml
    from gui import modpatch
    modpatch.apply()
    from sts2sim import runner as R
    from sts2sim import enemies as EN
    from sts2sim.report import make_report
    exp = yaml.safe_load(open(a.experiment, encoding="utf-8"))
    if a.seed is not None:
        exp["seed"] = a.seed
    if a.agent:
        exp["agent"] = a.agent
    if a.fights:
        exp["fights"] = a.fights
    for k, v in (exp.get("env") or {}).items():
        os.environ[str(k)] = str(v)
    M = R.get_modset(exp["mods"])
    tasks = R.plan(exp, M, a.fights)
    jobs = a.jobs or os.cpu_count() or 1
    T = i18n.t
    print(T("log.combatStart", title=exp.get("title") or exp["name"], n=len(tasks), agent=exp.get("agent", "heuristic"), procs=jobs), flush=True)
    emit("PROGRESS", {"done": 0, "total": len(tasks)})
    t0 = time.time()
    results = []
    with mp.Pool(jobs, initializer=_combat_init) as pool:
        cs = max(1, len(tasks) // (jobs * 8))
        last = 0
        for r in pool.imap(R._task, tasks, chunksize=cs):
            results.append(r)
            if len(results) - last >= max(1, len(tasks) // 50) or len(results) == len(tasks):
                last = len(results)
                emit("PROGRESS", {"done": len(results), "total": len(tasks)})
                print(f"[{len(results)}/{len(tasks)}] " + T("log.progressDone"), flush=True)
        approx = pool.map(R._collect_approx, range(jobs * 4))
    allapprox = {}
    for x in approx:
        allapprox.update(x)
    allapprox.update(EN.APPROX)
    wall = time.time() - t0
    os.makedirs(a.out, exist_ok=True)
    meta = {"exp": exp, "n_tasks": len(tasks), "wall_secs": wall, "jobs": jobs, "approx": allapprox}
    with open(os.path.join(a.out, "raw.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            r = dict(r)
            r.pop("log", None)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(T("log.makingReport"), flush=True)
    make_report(a.out, M)
    print(T("log.combatDone", n=len(tasks), secs=f"{wall:.1f}"), flush=True)
    emit("DONE", {"secs": wall, "out": a.out})


# ---------------------------------------------------------------- 卡牌列表
# 卡池/稀有度/类型只输出英文 ID（rarity_id / type_id / pool），显示用的文字由界面按所选语言翻译（gui/locales）


def cmd_cards(a):
    from claude_v35 import claude as CL
    from claude_v35.cards_v35 import VARIANTS
    CL.load()
    from sts2sim.rt.boot import game as G
    from sts2sim.engine.run import CHARACTERS
    starters = {}
    for ch, cls in CHARACTERS.items():
        try:
            starters[ch] = [c.Id.Entry for c in G._iter(G.ModelDb.Character(_g=(cls,)).StartingDeck)]
        except Exception as e:  # noqa
            starters[ch] = []
    zh = {}
    p = os.path.join(__import__("sts2sim.gamedata").gamedata.codex_dir(), "zhs_cards.json")
    if os.path.exists(p):
        zh = {c["id"]: c for c in json.load(open(p, encoding="utf-8"))}
    out = []
    for c in G._iter(G.ModelDb.AllCards):
        cid = c.Id.Entry
        pool = type(c.Pool).__name__.replace("CardPool", "")
        own = getattr(c, "ClaudeName", None)    # 我们自己 mod 的卡（名字是 mod 内容，不随语言变）
        codex = (zh.get(cid) or {}).get("name")
        name = own or codex or cid
        up_name = None
        spec = getattr(type(c), "_claude_spec", None)
        if spec and spec.get("up_name"):
            up_name = spec["up_name"]
        out.append({"id": cid, "name": str(name), "own_name": bool(own), "name_codex": codex, "up_name": up_name, "pool": pool,
                    "rarity_id": str(c.Rarity), "type_id": str(c.Type),
                    "desc": (zh.get(cid) or {}).get("description")})
    vdesc = {}
    try:
        import re
        src = open(os.path.join(paths.SIM_ROOT, "mods", "claude_v35", "cards_v35.py"), encoding="utf-8").read().splitlines()
        prev = ""
        for line in src:
            m = re.match(r'\s{4}"([A-Za-z0-9_]+)":\s*\{', line)
            if m and m.group(1) in VARIANTS:
                tail = line.split("#", 1)[1].strip() if "#" in line else ""
                vdesc[m.group(1)] = tail or prev
            st = line.strip()
            prev = st.lstrip("#").strip(" -") if st.startswith("#") else (prev if not st else "")
    except Exception:
        pass
    vdesc.setdefault("v35_orig", "")
    vdesc["v35_orig"] = ""     # 说明在 gui/locales 的 variant.v35_orig（随界面语言）
    vlist = [{"id": k, "desc": vdesc.get(k) or "", "detail": repr(v)[:300]} for k, v in VARIANTS.items()]
    print(json.dumps({"cards": out, "variants": vlist, "starters": starters, "characters": list(CHARACTERS)},
                     ensure_ascii=False))


def cmd_validate(a):
    from gui import modpatch
    modpatch.apply(a.user_mods)
    from sts2sim.modloader import ModSet
    names = [x for x in a.deps.split(",") if x] + [a.name]
    M = ModSet(names)
    own = [d for d in M.decks.values() if d.get("_mod", a.name) == a.name] if M.decks else []
    print(json.dumps({"ok": True, "cards": len(M.cards), "decks": len(M.decks), "characters": list(M.characters)},
                     ensure_ascii=False))


def cmd_mod_check(a):
    """YAML 数据 mod：先校验（不需要游戏）；没问题再真注册一遍（需要游戏数据），拿到每张牌在游戏里的 ID（强制加牌用）。"""
    from sts2sim.engine import yamlmod
    from sts2sim.modfmt import ModFormatError
    pair = lambda xs: [{"where": w, "zhs": zh, "en": en} for w, zh, en in xs]  # noqa
    chars, problems, warnings = yamlmod.check(a.dir, a.variant or None)
    out = {"ok": not problems, "characters": chars, "problems": pair(problems), "warnings": pair(warnings), "cards": {}}
    if not problems and a.build:
        try:
            yamlmod.load(a.dir, variant=a.variant or None)
            m = yamlmod.loaded()[-1]
            from sts2sim.rt.boot import game as G
            out["cards"] = {cid: G.ModelDb.GetId(cls).Entry for cid, cls in m.card_classes.items()}
        except ModFormatError as e:
            out["ok"] = False
            out["problems"] = pair(e.problems)
        except Exception as e:  # noqa
            import traceback
            out["ok"] = False
            out["problems"] = [{"where": "", "zhs": "注册到游戏引擎时出错：" + str(e), "en": "error while registering into the game engine: " + str(e),
                                "trace": traceback.format_exc()[-1500:]}]
    print(json.dumps(out, ensure_ascii=False))


def _utf8_stdio():
    # 打包后的 exe 不读 PYTHONIOENCODING / PYTHONUNBUFFERED，这里显式设成 UTF-8 + 行缓冲，界面按 UTF-8 读日志
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass


def main(argv=None):
    _utf8_stdio()
    ap = argparse.ArgumentParser(prog="worker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("batch")
    b.add_argument("--char", default="Claude")
    b.add_argument("--asc", type=int, default=0)
    b.add_argument("--n", type=int, default=20)
    b.add_argument("--start", type=int, default=0)
    b.add_argument("--procs", type=int, default=mp.cpu_count())
    b.add_argument("--out", required=True)
    b.add_argument("--agent", default="heuristic", choices=["heuristic", "search", "strong", "strong-nosearch", "learned", "learned-search", "learned-boss", "mentor-full", "mentor-full-ev", "modai", "modai-boss"])
    b.add_argument("--width", type=int, default=6)
    b.add_argument("--depth", type=int, default=1)
    b.add_argument("--variant", default="")
    b.add_argument("--force", default="")
    b.add_argument("--replace", default="")
    b.add_argument("--timeout", type=int, default=0)
    b.add_argument("--game-seed", default="", help="真游戏种子（逗号分隔）；给了就忽略 --n/--start")
    b.add_argument("--log-dir", default="", help="逐步决策日志目录（每局一个 JSONL）")
    b.add_argument("--mod", action="append", default=[], help="YAML 数据 mod 文件夹（整局），可多次")
    b.add_argument("--style", default="standard", help="打法风格（sts2sim/engine/style.py 的 STYLES）：standard / juggler")
    c = sub.add_parser("combat")
    c.add_argument("experiment")
    c.add_argument("--fights", type=int)
    c.add_argument("--jobs", type=int)
    c.add_argument("--seed", type=int)
    c.add_argument("--agent")
    c.add_argument("--out", required=True)
    sub.add_parser("cards")
    v = sub.add_parser("validate-mod")
    v.add_argument("name")
    v.add_argument("--deps", default="")
    v.add_argument("--user-mods", required=True)
    mc = sub.add_parser("mod-check")
    mc.add_argument("dir")
    mc.add_argument("--variant", default="")
    mc.add_argument("--build", action="store_true", help="也真注册一遍（需要游戏数据），输出每张牌的游戏 ID")
    a = ap.parse_args(argv)
    {"batch": cmd_batch, "combat": cmd_combat, "cards": cmd_cards, "validate-mod": cmd_validate,
     "mod-check": cmd_mod_check}[a.cmd](a)


if __name__ == "__main__":
    mp.freeze_support()
    main()
