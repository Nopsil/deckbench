"""批量跑整局：python tools/batch.py --char Ironclad --asc 10 --n 50 --procs 8 [--out x.jsonl]"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time


AGENT = {"name": "heuristic", "kw": {}}
STYLE_IDS = ["standard", "juggler"]   # 和 sts2sim/engine/style.py 的 STYLES 一致（tests/test_style.py 检查）


def make_agent(name, seed, **kw):
    import zlib
    s = zlib.crc32(str(seed).encode()) & 0xFFFF
    if name == "search":
        from sts2sim.engine.search import SearchAgent
        return SearchAgent(seed=s, **kw)
    if name in ("learned", "learned-search", "learned-boss"):
        # 自我对局 CMA-ES 学到的参数（data/ai_weights.json）+ StrongAgent；learned-search 另开 fork 前瞻（仅 Linux/macOS）
        from sts2sim.engine.weights import load_learned
        load_learned()
        from sts2sim.engine.strong import StrongAgent
        if name == "learned-boss":      # 只在首领战开搜索（首领战用整场推演），其余同 learned
            kw = dict(kw, boss_search=True)
            kw.setdefault("boss_width", 8)
            kw.setdefault("boss_depth", 99)
        return StrongAgent(seed=s, search=(name == "learned-search"), **kw)
    if name in ("strong", "strong-nosearch"):
        from sts2sim.engine.strong import StrongAgent
        return StrongAgent(seed=s, search=(name == "strong"), **kw)
    if name in ("planner", "planner-search"):
        from sts2sim.engine.planner import PlannerAgent
        return PlannerAgent(seed=s, search=(name == "planner-search"), **kw)
    if name == "imitation":
        # 模仿学习：搜索 AI 的出牌蒸馏成线性打分模型（data/imitation_model.json）；局外同 learned
        from sts2sim.engine.weights import load_learned
        load_learned()
        from sts2sim.engine.imitate import ImitationAgent
        return ImitationAgent(seed=s, **kw)
    if name in ("mentor-mcts", "mentor-boss", "mentor-full", "mentor-full-ev"):
        # 外部 spire-mentor（Rust）MCTS 打战斗；不认识的内容回退 learned-search。需要用户本地构建 sts2_rs（见 docs/DEVELOPER.md）
        from sts2sim.engine.weights import load_learned
        load_learned()
        from sts2sim.engine.mentor import make_mentor_agent
        if name == "mentor-boss":
            # 只在首领战用 MCTS；其余同 learned，首领战回退 = learned-boss 的整场推演
            kw = dict(kw, mentor_rooms={"Boss"}, fallback_search=False, boss_search=True)
            kw.setdefault("boss_width", 8)
            kw.setdefault("boss_depth", 99)
        if name == "mentor-full":
            kw = dict(kw, noncombat=True)
        if name == "mentor-full-ev":
            # mentor-full + 普通事件、局外选牌（锻造/删牌/变形/附魔）也交给 PPO；首领/精英默认 4000 模拟（A10 实测最好）
            # 事件选项的英文文本运行时从本机游戏安装读（sts2sim/gameloc.py），读不到就回退
            kw = dict(kw, noncombat=True, ppo_events=True, ppo_select=True)
            kw.setdefault("boss_sims", 4000)
            kw.setdefault("elite_sims", 4000)
        if os.name == "nt":      # 回退搜索要 os.fork()，Windows 上没有 → 回退到不搜索的 learned
            kw.setdefault("fallback_search", False)
        return make_mentor_agent(seed=s, **kw)
    if name.startswith("modai"):
        # 与角色无关的蒸馏局外 AI（sts2sim/engine/modai.py）：modai = 学生网络局外 + learned 出牌（模组角色也能用）；
        # modai-boss = 再加首领战整场推演（fork，仅 Linux/macOS）；modai-teacher = 老师 PPO 局外（需 spire-mentor，仅原版角色）
        from sts2sim.engine.modai import make_modai_agent
        mode = {"modai": "student", "modai-boss": "student", "modai-teacher": "teacher", "modai-dagger": "dagger"}[name]
        kw = dict(kw)
        bs = kw.pop("boss_search", False) or name == "modai-boss"
        if os.name == "nt":   # 首领推演要 os.fork()，Windows 没有
            bs = False
        return make_modai_agent(seed=s, mode=mode, boss_search=bs, **kw)
    if name == "heuristic":
        return None
    raise ValueError(name)


def _init(agent):
    AGENT.update(agent)


class RunTimeout(BaseException):
    pass


def _alarm(*_):
    raise RunTimeout("run exceeded time limit")


def _load_mods(char):
    if AGENT.get("mods"):
        # YAML 数据 mod（整局）：--mod <文件夹>，可以多个；--variant 作用在这些 mod 上
        from sts2sim.engine import yamlmod
        for d in AGENT["mods"]:
            yamlmod.load(d, variant=AGENT.get("variant"))
        return
    if char.startswith("Claude"):
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mods"))
        from claude_v35 import claude as CL
        CL.load(variant=AGENT.get("variant"))


def force_cards_hook(force, replace=()):
    """setup hook：把 force 里的牌加入起始牌组（'ID+' 表示升级），并移除 replace 里的牌（各移除 1 张）。
    在 RunState 建好、进入第一幕之前执行，所以对同一个种子，地图/遭遇/奖励的随机序列不受影响（只有牌组不同）。"""
    def hook(state, player):
        from sts2sim.rt.boot import game as G
        by = {c.Id.Entry: c for c in G._iter(G.ModelDb.AllCards)}
        for r in replace:
            for c in list(G._iter(player.Deck.Cards)):
                if c.Id.Entry == r:
                    player.Deck.RemoveInternal(c, True)
                    break
            else:
                raise ValueError(f"replace: {r} not in starting deck")
        for f in force:
            up = f.endswith("+")
            cid = f.rstrip("+")
            if cid not in by:
                raise ValueError(f"force: unknown card {cid}")
            card = state.CreateCard(by[cid], player)
            if up:
                card.UpgradeInternal()
            card.FloorAddedToDeck = 1
            player.Deck.AddInternal(card, -1, True)
    return hook


def wrap_log(ag, char, asc, seed):
    """AGENT["log_dir"] 设了就包一层逐步决策日志：<log_dir>/<角色>_A<进阶>_<种子>.jsonl（见 sts2sim/engine/decision_log.py）。"""
    d = AGENT.get("log_dir")
    if not d:
        return ag
    import os
    from sts2sim.engine.decision_log import DecisionLogger
    if ag is None:   # heuristic：和 RunDriver 默认一样建
        import zlib
        from sts2sim.engine.agents import HeuristicAgent
        ag = HeuristicAgent(seed=zlib.crc32(str(seed).encode()) & 0xFFFF)
    os.makedirs(d, exist_ok=True)
    return DecisionLogger(ag, os.path.join(d, f"{char}_A{asc}_{seed}.jsonl"), agent_name=AGENT["name"])


def game_seeds(spec):
    """--seed 'A,B,…'：真游戏种子（按游戏规则规范化：大写、O→0、I→1、去空格）。"""
    from sts2sim.engine.seed import canonicalize, warnings
    out = []
    for raw in [x for x in spec.split(",") if x.strip()]:
        c = canonicalize(raw)
        for w in warnings(raw, c):
            print("seed:", w)
        out.append(c)
    return out


def build_agent(seed):
    """按 AGENT 建这一局的 AI：make_agent → --force-pick → 打法风格（sts2sim/engine/style.py 的 STYLES）。批量和图形界面共用。"""
    from sts2sim.engine import style as ST
    ag = make_agent(AGENT["name"], seed, **AGENT["kw"])
    if AGENT.get("force_pick"):
        from sts2sim.engine.prefs import ForcePickAgent
        ag = ForcePickAgent(ag, AGENT["force_pick"], play_first=AGENT.get("force_pick_first", False))
    sid = ST.resolve(AGENT.get("style"))
    if sid != ST.DEFAULT:
        ag = ST.apply_style(ag, sid, AGENT["name"])
    return ag


def check_style(style_id, agent_name):
    """主进程里先检查风格 id 和 AI 能不能叠（不行就大白话报错退出，不开子进程）。返回规范化的 id。"""
    from sts2sim.engine import style as ST
    try:
        sid = ST.resolve(style_id)
    except ValueError as e:
        sys.stderr.write(f"打法风格 / play style: {e}\n")
        raise SystemExit(2)
    if not ST.compatible(sid, agent_name):
        sys.stderr.write(f"打法风格「{sid}」不能叠在 AI「{agent_name}」上，可用：{', '.join(a + '*' for a in ST.STYLES[sid]['agents'])}\n"
                         f"play style '{sid}' does not work with agent '{agent_name}'\n")
        raise SystemExit(2)
    return sid


def _one(args):
    import signal
    char, asc, seed = args
    _load_mods(char)
    from sts2sim.engine.run import play_run
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(AGENT.get("timeout", 600))
    try:
        hooks = [force_cards_hook(AGENT["force"], AGENT.get("replace", ()))] if AGENT.get("force") or AGENT.get("replace") else []
        ag = wrap_log(build_agent(seed), char, asc, seed)
        r = play_run(char, asc, seed, agent=ag, setup_hooks=hooks)
    except RunTimeout:
        import traceback
        return {"victory": False, "floor": -1, "act": 0, "path": [], "combats": [], "seed": seed, "char": char,
                "asc": asc, "error": "RunTimeout\n" + "".join(traceback.format_exc().splitlines(True)[-14:])}
    finally:
        signal.alarm(0)
    d = r.to_dict()
    d["style"] = AGENT.get("style") or "standard"
    if AGENT.get("force_pick") or (AGENT.get("style") or "standard") != "standard":
        d["forced_picks"] = getattr(ag, "forced", None)
    if getattr(ag, "mstats", None):
        d["mstats"] = ag.mstats
    d["seed"] = seed
    d["char"] = char
    d["asc"] = asc
    return d


def _check_mods(dirs, char, variant):
    """在主进程里先检查一遍（不注册）：格式有错就用大白话报出来并退出（不要等到每个子进程各报一遍）。"""
    from sts2sim.engine import yamlmod
    chars, bad = [], []
    for d in dirs:
        if not os.path.isdir(d):
            bad.append(("", f"找不到文件夹 {d}", f"folder not found: {d}"))
            continue
        c, problems, _w = yamlmod.check(d, variant)
        chars += c
        bad += problems
    if bad:
        sys.stderr.write("mod 有问题 / mod problems:\n" + "\n".join(f"  - {w + ': ' if w else ''}{zh}\n    {en}" for w, zh, en in bad) + "\n")
        raise SystemExit(2)
    if char not in chars and char not in ("Ironclad", "Silent", "Defect", "Necrobinder", "Regent"):
        sys.stderr.write(f"mod 里没有角色「{char}」/ no character '{char}' in the mod(s); 有 / available: {', '.join(chars)}\n")
        raise SystemExit(2)


def main():
    from sts2sim import gamedata
    gamedata.require()   # 没有本机安装 / 缓存不匹配 → 打印说明并退出
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Ironclad")
    ap.add_argument("--asc", type=int, default=10)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--procs", type=int, default=mp.cpu_count())
    ap.add_argument("--out", default=None)
    ap.add_argument("--agent", default="heuristic", choices=["heuristic", "search", "strong", "strong-nosearch", "planner", "planner-search", "learned", "learned-search", "learned-boss", "imitation", "mentor-mcts", "mentor-boss", "mentor-full", "mentor-full-ev", "modai", "modai-boss", "modai-teacher", "modai-dagger"])
    ap.add_argument("--sims", type=int, default=0, help="mentor-*：每个决策的 MCTS 模拟次数（默认 1000）")
    ap.add_argument("--boss-sims", type=int, default=0, help="mentor-*：首领战每步模拟次数（mentor-full-ev 默认 4000）")
    ap.add_argument("--elite-sims", type=int, default=0, help="mentor-*：精英战每步模拟次数（mentor-full-ev 默认 4000）")
    ap.add_argument("--width", type=int, default=6)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--variant", default=None, help="变体：Claude娘 手写版是 cards_v35.VARIANTS 的键；YAML mod 是 mod.yaml 里 variants 的键（多个用 + 连接）")
    ap.add_argument("--mod", action="append", default=[], help="YAML 数据 mod 文件夹（整局），可以给多个；例：--mod mods/claude_yaml --char Claude")
    ap.add_argument("--force", default="", help="强制加入起始牌组的牌，逗号分隔，'ID+' 为升级版（单卡 A/B 用）")
    ap.add_argument("--replace", default="", help="同时从起始牌组移除的牌，逗号分隔（例：CLAUDE_STRIKE）")
    ap.add_argument("--no-boss-aware", action="store_true", help="关闭首领感知（选牌/休息）")
    ap.add_argument("--boss-search", action="store_true", help="strong-nosearch 下只在首领战开搜索")
    ap.add_argument("--timeout", type=int, default=0, help="每局秒数上限（默认 heuristic 60，其余 900）")
    ap.add_argument("--style", default="standard", choices=STYLE_IDS, type=lambda x: x.strip().lower() or "standard",
                    help="打法风格：standard = 标准（不加规则）；juggler = 杂耍流（优先拿 JUGGLING，偏好多段攻击和反直觉的组合，攻击优先、冲精英；"
                         "要 strong/learned/modai/mentor 系 AI）。见 sts2sim/engine/style.py")
    ap.add_argument("--force-pick-first", action="store_true", help="配合 --force-pick：战斗里能打出就先打")
    ap.add_argument("--force-pick", default="", help="风格规则：卡牌奖励/商店里见到这些牌（ID，逗号分隔）就拿，例 JUGGLING")
    ap.add_argument("--seed", default="", help="指定真游戏种子（逗号分隔，可多个）；给了就只打这些局，忽略 --n/--start")
    ap.add_argument("--log-dir", default="", help="逐步决策日志目录（每局一个 JSONL）")
    a = ap.parse_args()
    a.style = check_style(a.style, a.agent)
    if a.mod:
        _check_mods(a.mod, a.char, a.variant)
    if a.seed:
        jobs = [(a.char, a.asc, s) for s in game_seeds(a.seed)]
    else:
        jobs = [(a.char, a.asc, f"R{i}") for i in range(a.start, a.start + a.n)]
    t = time.time()
    akw = {"width": a.width, "depth": a.depth} if a.agent == "search" else {}
    if a.agent.startswith(("strong", "planner", "learned", "imitation", "modai")):
        akw.update(boss_aware=not a.no_boss_aware, boss_search=a.boss_search)
    if a.agent.startswith("mentor"):
        akw.update(boss_aware=not a.no_boss_aware)
        if a.sims:
            akw["sims"] = a.sims
        if a.boss_sims:
            akw["boss_sims"] = a.boss_sims
        if a.elite_sims:
            akw["elite_sims"] = a.elite_sims
    with mp.Pool(a.procs, initializer=_init, initargs=({"name": a.agent, "kw": akw, "mods": [os.path.abspath(m) for m in a.mod],
                                                               "variant": a.variant, "force": [x for x in a.force.split(",") if x],
                                                               "replace": [x for x in a.replace.split(",") if x], "log_dir": a.log_dir, "force_pick": [x for x in a.force_pick.split(",") if x], "style": a.style, "force_pick_first": a.force_pick_first, "timeout": a.timeout or (60 if a.agent == "heuristic" else 900)},)) as pool:
        res = pool.map(_one, jobs, chunksize=1)
    dt = time.time() - t
    wins = sum(r["victory"] for r in res)
    errs = [r for r in res if r["error"]]
    floors = sorted(r["floor"] for r in res)
    print(f"{a.char} A{a.asc} [{a.agent}, style {a.style}]: {wins}/{len(res)} wins, errors {len(errs)}, median floor {floors[len(floors)//2]}, "
          f"acts reached {[sum(1 for r in res if r['act'] >= k) for k in range(3)]}, {dt:.1f}s ({len(res)/dt:.2f} runs/s)")
    import collections
    loss = collections.defaultdict(list)
    for r in res:
        for c in r["combats"]:
            loss[(c[1], c[6] if len(c) > 6 else (0 if c[0] <= 17 else 1 if c[0] <= 34 else 2))].append(c[4])
    print("  avg HP loss:", {f"{k[0]}@act{k[1]+1}": round(sum(v) / len(v), 1) for k, v in sorted(loss.items())},
          "| combats won", sum(1 for r in res for c in r["combats"] if c[5]), "| avg floor", round(sum(floors) / len(floors), 1))
    ms = [r["mstats"] for r in res if r.get("mstats")]
    if ms:
        nm, nf = sum(m["mentor"] for m in ms), sum(m["fallback"] for m in ms)
        print(f"  mentor decisions {nm}, fallback {nf} ({nf / max(1, nm + nf):.1%}), "
              f"mcts {sum(m['mcts_sec'] for m in ms) / max(1, nm) * 1000:.0f} ms/decision")
        pp = collections.defaultdict(lambda: [0, 0])
        for m in ms:
            for k, v in (m.get("ppo") or {}).items():
                pp[k][0] += v[0]; pp[k][1] += v[1]
        if pp:
            print("  ppo non-combat (net/fallback):", {k: tuple(v) for k, v in sorted(pp.items())},
                  "| errors", dict(collections.Counter(k for m in ms for k, n in (m.get("ppo_err") or {}).items() for _ in range(n))))
    for r in errs[:5]:
        ls = r["error"].splitlines()
        print("ERR", r["seed"], ls[0][:200], "|", ls[-2][:200] if len(ls) > 1 else "")
    if a.out:
        with open(a.out, "w") as f:
            for r in res:
                f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
