"""界面后台的工作进程：调用模拟器现有的批量/实验函数，并按行输出进度。

  batch   —— 整局批量（复用 tools/batch.py 的 _init / _one / force_cards_hook / make_agent），imap 逐局报告进度
  combat  —— 战斗实验（复用 sts2sim.runner 的 plan / _task / make_report），分块报告进度
  cards   —— 列出可强制加入/移除的卡牌（JSON）
  validate-mod —— 用模拟器的 ModSet 试加载一个 mod

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

from gui import paths  # noqa: E402

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
    try:
        r = play_run(char, asc, seed, agent=batch.make_agent(A["name"], seed, **A["kw"]), setup_hooks=hooks)
        d = r.to_dict()
    except Exception:
        import traceback
        d = {"victory": False, "floor": -1, "act": 0, "path": [], "combats": [], "error": traceback.format_exc()[-2000:]}
    d["seed"] = seed
    d["char"] = char
    d["asc"] = asc
    return d


def _batch_init(cfg):
    paths.setup_sys_path()
    import batch
    batch._init(cfg)


def cmd_batch(a):
    import batch  # noqa: F401  (tools/batch.py)
    jobs = [(a.char, a.asc, f"R{i}") for i in range(a.start, a.start + a.n)]
    akw = {"width": a.width, "depth": a.depth} if a.agent == "search" else {}
    if a.agent.startswith(("strong", "learned")):
        akw.update(boss_aware=True, boss_search=False)
    cfg = {"name": a.agent, "kw": akw, "variant": a.variant or None,
           "force": [x for x in a.force.split(",") if x], "replace": [x for x in a.replace.split(",") if x],
           "timeout": a.timeout or (60 if a.agent == "heuristic" else 900)}
    print(f"整局批量：{a.char} A{a.asc}，{a.n} 局（种子 R{a.start}…R{a.start + a.n - 1}），AI {a.agent}，"
          f"变体 {a.variant or '无'}，加入 {cfg['force'] or '无'}，移除 {cfg['replace'] or '无'}，并行 {a.procs}", flush=True)
    emit("PROGRESS", {"done": 0, "total": len(jobs)})
    t = time.time()
    res = []
    with mp.Pool(a.procs, initializer=_batch_init, initargs=(cfg,)) as pool:
        for r in pool.imap_unordered(_one_safe, jobs, chunksize=1):
            res.append(r)
            tag = "胜利" if r.get("victory") else ("出错" if r.get("error") else f"止步第 {r.get('floor')} 层")
            dr = r.get("death_room")
            print(f"[{len(res)}/{len(jobs)}] {r['seed']}：{tag}" + (f"（{dr[1]} {dr[2]}）" if dr and not r.get("victory") else ""), flush=True)
            emit("PROGRESS", {"done": len(res), "total": len(jobs)})
    order = {s: i for i, (_, _, s) in enumerate(jobs)}
    res.sort(key=lambda r: order.get(r["seed"], 0))
    dt = time.time() - t
    with open(a.out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    wins = sum(bool(r.get("victory")) for r in res)
    errs = sum(1 for r in res if r.get("error"))
    print(f"完成：{wins}/{len(res)} 胜，出错 {errs}，用时 {dt:.1f} 秒", flush=True)
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
    print(f"战斗实验：{exp.get('title') or exp['name']}，{len(tasks)} 场，AI {exp.get('agent', 'heuristic')}，并行 {jobs}", flush=True)
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
                print(f"[{len(results)}/{len(tasks)}] 已完成", flush=True)
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
    print("生成报告…", flush=True)
    make_report(a.out, M)
    print(f"完成 {len(tasks)} 场，用时 {wall:.1f} 秒", flush=True)
    emit("DONE", {"secs": wall, "out": a.out})


# ---------------------------------------------------------------- 卡牌列表
POOL_NAMES = {"Ironclad": "铁甲战士", "Silent": "静默猎手", "Defect": "故障机器人", "Necrobinder": "亡灵契约师",
              "Regent": "储君", "Claude": "Claude娘", "Colorless": "无色", "Event": "事件", "Curse": "诅咒",
              "Token": "衍生", "Status": "状态", "Quest": "任务", "Deprecated": "废弃"}
RARITY = {"Basic": "基础", "Common": "普通", "Uncommon": "罕见", "Rare": "稀有", "Ancient": "远古", "Event": "事件",
          "Curse": "诅咒", "Status": "状态", "Token": "衍生", "Quest": "任务"}
TYPE = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态", "Curse": "诅咒", "Quest": "任务"}


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
        name = getattr(c, "ClaudeName", None) or (zh.get(cid) or {}).get("name") or cid
        up_name = None
        spec = getattr(type(c), "_claude_spec", None)
        if spec and spec.get("up_name"):
            up_name = spec["up_name"]
        out.append({"id": cid, "name": str(name), "up_name": up_name, "pool": pool, "pool_zh": POOL_NAMES.get(pool, pool),
                    "rarity": RARITY.get(str(c.Rarity), str(c.Rarity)), "type": TYPE.get(str(c.Type), str(c.Type)),
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
    vdesc["v35_orig"] = "v3.5 原值（v3.5.1 之前的默认：小本本 3 伤，已核实每层 +2 上限 +8，初始生命 75）"
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
    b.add_argument("--agent", default="heuristic", choices=["heuristic", "search", "strong", "strong-nosearch", "learned", "learned-search", "learned-boss"])
    b.add_argument("--width", type=int, default=6)
    b.add_argument("--depth", type=int, default=1)
    b.add_argument("--variant", default="")
    b.add_argument("--force", default="")
    b.add_argument("--replace", default="")
    b.add_argument("--timeout", type=int, default=0)
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
    a = ap.parse_args(argv)
    {"batch": cmd_batch, "combat": cmd_combat, "cards": cmd_cards, "validate-mod": cmd_validate}[a.cmd](a)


if __name__ == "__main__":
    mp.freeze_support()
    main()
