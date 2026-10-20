"""把 raw.jsonl 汇总成中文 Markdown 报告和 CSV。"""
import csv
import json
import os
import statistics as S
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 原版基线（spire-codex 五角色奖励池中位数，见 tools/baseline.py）：1 费单体攻击 8 伤/能量，格挡 6/能量；0 费攻击 6 伤
BASE_DMG = 8.0
BASE_BLK = 6.0
BASE_DMG0 = 6.0
BASE_BLK0 = 4.0
ALARM_RATIO = 2.0
SOFT_LOOP_ACTIONS = 40

ENGINE_APPROX = [
    "单场战斗、满血开局，不连续爬塔；不计药水、升级（除非卡组写了 +）、非初始遗物（除非卡组写了）、事件与商店。",
    "普通难度（进阶 0）；敌人血量在数据给的区间内均匀随机。",
    "遭遇按幕、房间类型从 spire-codex encounters 里均匀抽取（不按游戏里的楼层权重）；第 1 幕包含 Overgrowth 与 Underdocks 两个地区。遭遇的真实组成（几只、哪几种、随机组成）取自反编译 Encounters/*.cs。",
    "敌人意图按反编译 C# 的 GenerateMoveStateMachine() 状态机走（固定循环、RandomBranchState 权重与 CannotRepeat/最多连续 N 次/UseOnlyOnce/冷却、ConditionalBranchState 条件、开场招、MustPerformOnce），语义照抄 MonsterMoveStateMachine.cs；随机数用模拟器自己的种子，所以和游戏里同一个种子的出招不会逐招相同，但分布和约束一致。",
    "招式数值优先取 spire-codex（同源解析），spire-codex 漏掉的招式用反编译代码里的意图参数和招式函数推出；塞状态牌的种类、张数、去向（弃牌堆/手牌/抽牌堆）取自代码。召唤类招式只结算伤害/格挡/能力，不生成新敌人；被击晕时跳过本回合，之后接代码指定的招式（没有指定则接原本的招式）。",
    "伤害公式：(基础 + 力量 [+ 熟练度/活力]) × 虚弱 0.75 × 易伤 1.5 向下取整；无实体压到 1；滑溜、难以杀灭、硬化外壳按描述处理。能力/遗物伤害（荆棘、清退名单等）不吃力量和易伤。",
    "易伤/虚弱/脆弱在拥有者回合结束时 -1。格挡在拥有者回合开始时清空（壁垒、数据留存政策例外）。",
    "出牌 AI 是启发式贪心（逐个模拟每个合法动作，用局面估值选最高），不偷看抽牌堆；选牌界面（消耗/弃牌/捞牌/发现/保留）按卡牌价值启发式选择。AI 比熟练玩家笨，尤其不会为下回合规划。",
    "掉血 = 开局生命 − 战斗结束生命；战败记为掉光全部生命；燃烧之血等战后回复不计。",
    "单卡贡献只统计直接伤害（敌人实际失去的生命）和获得的格挡；抽牌、能量、叠层、易伤/虚弱、力量的价值都不计入（力量带来的伤害记在打出的攻击牌上）。",
    "故障机器人：只有闪电充能球（被动回合末 3 伤、激发 8 伤，随机敌人，不吃易伤），3 个球位，集中为 0。",
    "亡灵契约师：奥斯提近似为一个吸收「格挡后剩余攻击伤害」的生命池，召唤增加其生命；释放 = 6 + 奥斯提当前生命。",
    "储君：星辰是跨回合保留的资源，陨星需要 2 星。",
]


ROADMAP = """## 9. 路线图（最终目标：复刻游戏里全部敌人、遗物/药水与机制）

| 阶段 | 内容 | 数据来源 | 主要不确定点 |
|-|-|-|-|
| v0.1（本版） | 战斗核心、Claude娘 v3.4 全卡、5 角色初始卡组与初始遗物、示例成型卡组；敌人按反编译状态机出招；20 种数值类药水与用药 AI（实验暂不带药）；覆盖率统计 | spire-codex JSON；Hexpion 反编译镜像（状态机、遭遇组成、部分能力） | 召唤不生成新敌人；约 10 个敌人能力只记层数；AI 不规划下回合；单场战斗、满血开局 |
| v0.2 | 全部遗物/药水（先用 tools/import_codex.py 导出桩，按 Relics/*.cs、Potions/*.cs 逐个实现）；复杂敌人机制：召唤（Summon 招式生成小怪、爪牙）、变身/复活（实验体 Adaptable、多阶段首领）、魂缚锁链等卡牌侵蚀类能力、敌人死亡触发；原版全卡（spire-codex 577 张卡的数值 + Cards/*.cs 效果）；进阶等级 | Hexpion 镜像 Models/{Relics,Potions,Cards,Powers,Monsters}；spire-codex 数值与中文 | 反编译镜像对应的游戏版本与 spire-codex 不一定一致（已发现少数招式 ID/数值差异，需要版本对齐）；部分逻辑在 UI/动画回调或 Cmd 层（CreatureCmd.Stun、召唤站位），需要读 Commands/*.cs；游戏 RNG 流（monster/shuffle/card RNG 分离）是否要逐位复刻 |
| v0.3 | 整局模拟：地图生成与路线选择、卡牌奖励与选卡 AI、商店、事件、篝火（休息/升级）、宝箱与遗物获取、先古之民；按幕成长的生命/卡组 | Hexpion 镜像 Map/Rooms/Events/Rewards；spire-codex events.json（56/66 个事件有完整分支）、acts.json | 选卡/路线 AI 的强度决定结论可信度；事件里大量随机与条件分支；整局规模下需要更快的引擎（或 Rust/numba 加速） |
"""


def _load(out_dir):
    rows = [json.loads(l) for l in open(os.path.join(out_dir, "raw.jsonl"), encoding="utf-8")]
    meta = json.load(open(os.path.join(out_dir, "meta.json"), encoding="utf-8"))
    return rows, meta


def _pct(a, b):
    return 100.0 * a / b if b else 0.0


def _r(x, n=1):
    return round(x, n) if x is not None else None


def summarize_cells(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["deck"], r["act"], r["room"])].append(r)
    cells = {}
    for k, L in g.items():
        n = len(L)
        wins = [x for x in L if x["result"] == "win"]
        cells[k] = {
            "n": n,
            "win": _pct(len(wins), n),
            "loss": _pct(sum(x["result"] == "loss" for x in L), n),
            "timeout": _pct(sum(x["result"] == "timeout" for x in L), n),
            "loop": sum(x["result"] == "loop" for x in L),
            "turns": S.mean(x["turns"] for x in L),
            "turns_win": S.mean(x["turns"] for x in wins) if wins else None,
            "hp_lost": S.mean(x["hp_lost"] for x in L),
            "hp_lost_win": S.mean(x["hp_lost"] for x in wins) if wins else None,
            "dpt": S.mean(x.get("dmg_total", 0) / max(1, x["turns"]) for x in L),
            "soft_loop": sum(1 for x in L if x.get("max_actions", 0) >= SOFT_LOOP_ACTIONS),
            "max_actions": max(x.get("max_actions", 0) for x in L),
        }
    return cells


def summarize_cards(rows, decks_filter=None):
    """按（卡组, 卡）汇总单卡使用与贡献。"""
    g = defaultdict(lambda: [0, 0, 0, 0])
    fights = defaultdict(int)
    for r in rows:
        if decks_filter and r["deck"] not in decks_filter:
            continue
        fights[r["deck"]] += 1
        for name, (p, d, b, e) in r["cards"].items():
            x = g[(r["deck"], name)]
            x[0] += p
            x[1] += d
            x[2] += b
            x[3] += e
    return g, fights


def ratio(dmg, blk, energy, plays):
    if plays <= 0:
        return None
    if energy / plays >= 0.5:
        return (dmg / BASE_DMG + blk / BASE_BLK) / energy
    return (dmg / BASE_DMG0 + blk / BASE_BLK0) / plays


def make_report(out_dir, M):
    rows, meta = _load(out_dir)
    exp = meta["exp"]
    decks = M.decks
    cells = summarize_cells(rows)
    deck_name = lambda d: decks[d]["name"] if d in decks else d

    # ---------- CSV：格子
    with open(os.path.join(out_dir, "cells.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["卡组id", "卡组", "阶段", "幕", "房间", "场数", "胜率%", "战败%", "超时%", "循环报警场数", "平均回合", "胜场平均回合",
                    "平均掉血", "胜场平均掉血", "每回合输出", "单回合动作≥40场数", "最大单回合动作数"])
        for (d, a, ro), c in sorted(cells.items()):
            w.writerow([d, deck_name(d), decks.get(d, {}).get("stage", ""), a, ro, c["n"], _r(c["win"]), _r(c["loss"]), _r(c["timeout"]),
                        c["loop"], _r(c["turns"]), _r(c["turns_win"]), _r(c["hp_lost"]), _r(c["hp_lost_win"]), _r(c["dpt"]), c["soft_loop"], c["max_actions"]])

    # ---------- CSV：单卡
    cg, fights = summarize_cards([r for r in rows if r["room"] != "探针"])
    card_rows = []
    for (d, name), (p, dm, bl, en) in cg.items():
        card_rows.append({
            "deck": d, "card": name, "plays": p, "per_fight": p / fights[d], "dmg_play": dm / p if p else 0,
            "blk_play": bl / p if p else 0, "energy_play": en / p if p else 0, "ratio": ratio(dm, bl, en, p),
            "dmg": dm, "blk": bl, "energy": en,
        })
    with open(os.path.join(out_dir, "cards.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["卡组id", "卡组", "卡牌/来源", "总使用次数", "每场使用", "每次伤害", "每次格挡", "每次付费", "效率倍数(原版中位=1)"])
        for x in sorted(card_rows, key=lambda x: (x["deck"], -x["plays"])):
            w.writerow([x["deck"], deck_name(x["deck"]), x["card"], x["plays"], _r(x["per_fight"], 2), _r(x["dmg_play"]), _r(x["blk_play"]),
                        _r(x["energy_play"], 2), _r(x["ratio"], 2)])

    # ---------- CSV：遭遇
    eg = defaultdict(list)
    for r in rows:
        eg[(r["deck"], r["act"], r["room"], r["enc_name"])].append(r)
    with open(os.path.join(out_dir, "encounters.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["卡组", "幕", "房间", "遭遇", "场数", "胜率%", "平均回合", "平均掉血"])
        for (d, a, ro, en), L in sorted(eg.items()):
            w.writerow([deck_name(d), a, ro, en, len(L), _r(_pct(sum(x["result"] == "win" for x in L), len(L))),
                        _r(S.mean(x["turns"] for x in L)), _r(S.mean(x["hp_lost"] for x in L))])

    # ---------- Markdown
    L = []
    A = L.append
    A(f"# 战斗模拟报告：{exp.get('title', exp['name'])}")
    A("")
    A(f"- 模拟器：DeckBench（旧版 YAML 战斗模拟器）；出牌 AI：{exp.get('agent', 'heuristic')}；种子 {exp.get('seed')}；每格 {exp.get('fights')} 场；回合上限 {exp.get('max_turns', 30)}；单回合动作上限 200。")
    A(f"- 共 {meta['n_tasks']} 场，{meta['jobs']} 进程并行，用时 {meta['wall_secs']:.0f} 秒（约 {meta['wall_secs']/max(1,meta['n_tasks'])*1000*meta['jobs']:.0f} 毫秒/场/核）。")
    A(f"- 敌人数据：spire-codex（commit 8449ba14）monsters / encounters 的数值 + Hexpion/Slay-the-spire-2 反编译镜像（commit 64ed626b）的出招状态机与遭遇组成；原版卡牌数值取自 spire-codex。")
    A("- 所有数字都是模拟器 + 启发式 AI 的结果，只适合在同一套假设下横向比较，不能当真实胜率。")
    A("")
    if exp.get("summary_md"):
        _sm = exp["summary_md"]
        for _p in (os.path.join(out_dir, _sm), _sm, os.path.join("experiments", _sm)):
            if os.path.exists(_p):
                A(open(_p, encoding="utf-8").read())
                break
        else:
            A(_sm)
        A("")

    def table(deck_ids, rooms, title, act=None):
        A(f"### {title}")
        A("")
        A("| 卡组 | " + " | ".join(f"{ro} 胜率 / 回合 / 掉血 / 每回合输出" for ro in rooms) + " |")
        A("|" + "-|" * (len(rooms) + 1))
        for d in deck_ids:
            dk = decks.get(d)
            if dk is None:
                continue
            acts = [act] if act else dk.get("acts", [1])
            for a in acts:
                cs = []
                for ro in rooms:
                    c = cells.get((d, a, ro))
                    if not c:
                        cs.append("—")
                        continue
                    tw = c["turns_win"]
                    cs.append(f"{c['win']:.0f}% / {tw:.1f} / {c['hp_lost']:.0f} / {c['dpt']:.1f}" if tw else f"{c['win']:.0f}% / 撑{c['turns']:.1f} / {c['hp_lost']:.0f} / {c['dpt']:.1f}")
                A(f"| {dk['name']}（第{a}幕） | " + " | ".join(cs) + " |")
        A("")
        A("回合 = 胜场平均回合数（胜率 0% 时写「撑 N」= 平均坚持回合数）；掉血 = 全部场次平均（战败算掉光）；每回合输出 = 对敌人造成的实际生命损失 ÷ 回合数（不受战败影响，最适合比较进攻速度）。")
        A("")

    rooms = exp.get("rooms", ["普通", "精英", "首领"])
    A("## 1. 总表")
    A("")
    groups = exp.get("groups") or [{"title": "全部卡组", "decks": exp["decks"]}]
    for gp in groups:
        table(gp["decks"], rooms, gp["title"])

    # ---------- 与旧简化模拟对比
    legacy = exp.get("legacy")
    if legacy:
        lp = os.path.join(ROOT, legacy["file"])
        if os.path.exists(lp):
            old = json.load(open(lp, encoding="utf-8"))["results"]
            A("## 2. 与之前简化模拟（单一血池、固定意图伤害）的对照")
            A("")
            A("旧模拟把一场战斗的所有敌人合成一个血池、每回合固定挨「意图均值」的伤害、玩家不会死、卡组不升级；新模拟用反编译代码里的真实遭遇组成和出招状态机（多敌人、意图序列、增益、人工制品、状态牌）、玩家会战败，第2/3幕卡组分别自动升级 3/6 张（旧模拟没有升级）。")
            A("")
            A("| 卡组 | 房间 | 旧：回合 | 旧：掉血 | 新：胜场回合 | 新：平均掉血 | 新：胜率 |")
            A("|-|-|-|-|-|-|-|")
            for d, (stage, oname) in legacy["map"].items():
                dk = decks.get(d)
                if not dk:
                    continue
                for a in dk.get("acts", [1]):
                    for ro in rooms:
                        o = old.get(stage, {}).get(oname, {}).get(f"第{a}幕{ro}")
                        c = cells.get((d, a, ro))
                        if not o or not c:
                            continue
                        A(f"| {dk['name']}（第{a}幕） | {ro} | {o[0]} | {o[1]} | {_r(c['turns_win']) if c['turns_win'] else '—'} | {c['hp_lost']:.1f} | {c['win']:.0f}% |")
            A("")

    # ---------- 报警
    A("## 3. 报警")
    A("")
    A("### 3.1 无限循环")
    A("")
    loops = [r for r in rows if r["result"] == "loop" and r["room"] != "探针"]
    soft = [r for r in rows if r.get("max_actions", 0) >= SOFT_LOOP_ACTIONS and r["room"] != "探针"]
    if loops:
        A(f"正式对局里有 {len(loops)} 场撞到单回合 200 个动作的上限：")
        A("")
        agg = defaultdict(int)
        for r in loops:
            agg[(deck_name(r["deck"]), " → ".join(r["loop"]["tail"][-6:]))] += 1
        for (dn, tail), n in sorted(agg.items(), key=lambda x: -x[1])[:15]:
            A(f"- {dn}：{n} 场，最后 6 个动作：{tail}")
    else:
        A("正式对局（非探针）里没有任何一场撞到单回合 200 个动作的上限。")
    A("")
    if soft:
        A(f"单回合动作数 ≥ {SOFT_LOOP_ACTIONS} 的场次：{len(soft)} 场（可能是长连击，也可能是接近循环）。")
    else:
        A(f"也没有单回合动作数 ≥ {SOFT_LOOP_ACTIONS} 的场次。")
    A("")
    probes = [r for r in rows if r["room"] == "探针"]
    if probes:
        A("### 3.2 循环探针（精简卡组打 9999 血木桩 3 回合）")
        A("")
        A("| 探针 | 设计预期 | 场数 | 撞上限场数（启发式 / 束搜索） | 最大单回合动作数 | 结论 |")
        A("|-|-|-|-|-|-|")
        pg = defaultdict(list)
        for r in probes:
            pg[r["deck"]].append(r)
        for d, Lr in pg.items():
            dk = decks.get(d, {})
            nl = sum(x["result"] == "loop" for x in Lr)
            mx = max(x.get("max_actions", 0) for x in Lr)
            exp_ = dk.get("expect", "")
            ok = ("无限" in exp_ and "不应" not in exp_ and nl > 0) or (("不应" in exp_ or "断开" in exp_) and nl == 0)
            def _n(ag):
                xs = [x for x in Lr if x.get("agent", "heuristic") == ag]
                return f"{sum(x['result'] == 'loop' for x in xs)}/{len(xs)}" if xs else "—"
            A(f"| {dk.get('name', d)} | {exp_} | {len(Lr)} | {_n('heuristic')} / {_n('beam')} | {mx} | {'符合' if ok else '**不符合，需检查**'} |")
        A("")
        A("探针只能证明「AI 找到/没找到」循环，没找到不等于不存在；全组合穷举请继续用设计目录里的 loopcheck.py。")
        A("")

    # 单卡效率
    A("### 3.3 单卡每费输出")
    A("")
    A(f"效率倍数 =（每次伤害/{BASE_DMG:.0f} + 每次格挡/{BASE_BLK:.0f}）÷ 每次付费；平均每次付费 < 0.5 的牌（0 费牌）改用（伤害/{BASE_DMG0:.0f} + 格挡/{BASE_BLK0:.0f}）÷ 次数。能力牌的伤害是整场持续收益，倍数只作参考。原版五角色奖励池中位数 = 1.0。"
      f"倍数 ≥ {ALARM_RATIO} 且使用 ≥ 50 次记为报警。只算直接伤害和格挡，所以兑现牌（吃别的牌叠的层数）天然偏高、叠层/过牌牌天然偏低；原版同类牌一起列出作为参照。")
    A("")
    agg = defaultdict(lambda: [0, 0, 0, 0, set()])
    for x in card_rows:
        k = x["card"]
        a = agg[k]
        a[0] += x["plays"]; a[1] += x["dmg"]; a[2] += x["blk"]; a[3] += x["energy"]; a[4].add(deck_name(x["deck"]).split("·")[0])
    cl_names = set(d.name for d in M.cards.values() if d.mod not in ("vanilla", "builtin"))
    van_names = set(d.name for d in M.cards.values() if d.mod == "vanilla")
    typ = {d.name: d.type for d in M.cards.values()}
    alarm_rows = []
    for k, (p, dm, bl, en, owners) in agg.items():
        rr = ratio(dm, bl, en, p)
        if rr is None:
            continue
        alarm_rows.append((k, p, dm / p, bl / p, en / p, rr, owners))
    alarm_rows.sort(key=lambda x: -x[5])
    flagged = [x for x in alarm_rows if x[5] >= ALARM_RATIO and x[1] >= 50]
    A("| 卡牌/来源 | 类型 | 归属 | 使用次数 | 每次伤害 | 每次格挡 | 每次付费 | 效率倍数 | 报警 |")
    A("|-|-|-|-|-|-|-|-|-|")
    for k, p, dmp, blp, enp, rr, owners in alarm_rows[:40]:
        side = "Claude娘" if k in cl_names else ("原版" if k in van_names else "/".join(sorted(owners)))
        flag = "⚠" if (rr >= ALARM_RATIO and p >= 50) else ""
        A(f"| {k} | {typ.get(k, '来源')} | {side} | {p} | {dmp:.1f} | {blp:.1f} | {enp:.2f} | {rr:.2f} | {flag} |")
    A("")
    A(f"超过 {ALARM_RATIO} 倍的：" + ("、".join(f"{x[0]}（{x[5]:.2f}）" for x in flagged) if flagged else "无") + "。完整列表见 cards.csv。")
    A("")

    # 单卡使用频率（每个 Claude 卡组前 8）
    A("## 4. 单卡使用频率与贡献（每个卡组使用最多的 8 项）")
    A("")
    for d in exp["decks"]:
        xs = sorted([x for x in card_rows if x["deck"] == d], key=lambda x: -x["plays"])[:8]
        if not xs:
            continue
        A(f"**{deck_name(d)}**（{decks[d].get('stage','')}）：" + "；".join(
            f"{x['card']} {x['per_fight']:.1f}次/场" + (f"·{x['dmg_play']:.0f}伤" if x['dmg_play'] >= 0.5 else "") +
            (f"·{x['blk_play']:.0f}挡" if x['blk_play'] >= 0.5 else "") for x in xs))
        A("")

    # 最难遭遇
    A("## 5. 每个卡组最难的遭遇（胜率最低的 3 个，≥5 场）")
    A("")
    for d in exp["decks"]:
        es = []
        for (dd, a, ro, en), Lr in eg.items():
            if dd != d or len(Lr) < 5:
                continue
            es.append((_pct(sum(x["result"] == "win" for x in Lr), len(Lr)), ro, en, len(Lr)))
        es.sort()
        if es:
            A(f"- {deck_name(d)}：" + "；".join(f"{ro}「{en}」{w:.0f}%（{n}场）" for w, ro, en, n in es[:3]))
    A("")

    # 近似清单
    # 覆盖率
    from .catalog import coverage, coverage_md, write_csvs, monsters_table_md
    cov = coverage(M)
    write_csvs(cov, out_dir)
    A("## 6. 数据覆盖率与敌人意图来源")
    A("")
    A("数据来源：spire-codex（数值、中文名、描述）+ Hexpion/Slay-the-spire-2 反编译镜像（commit 64ed626b，怪物状态机、遭遇组成、能力实现）。"
      "「代码」= 出招逻辑完全按反编译状态机且没有已知近似；「代码+近似」= 状态机来自代码，但有召唤/未实现能力/无法求值的条件等近似（见说明列）。")
    A("")
    A(coverage_md(cov))
    A("")
    A("<details><summary>每个怪物的意图逻辑来源（展开）</summary>")
    A("")
    A(monsters_table_md(cov))
    A("")
    A("</details>")
    A("")
    miss = [r for r in cov["encounters"] if r["status"] == "缺失"]
    if miss:
        A("不参与模拟的遭遇：" + "；".join(f"{r['name']}（{r['id']}，{r['why']}）" for r in miss) + "。")
        A("")
    A("意图单元测试见 tests/test_intents.py（固定种子的前 N 回合出招序列、不能连续同招/最多连续 2 次、站位与开场招、血量阈值、沉睡/失衡/击晕、AI 读取意图伤害）。")
    A("")
    A("## 7. 近似清单")
    A("")
    A("### 7.1 引擎与敌人")
    A("")
    for x in ENGINE_APPROX:
        A(f"- {x}")
    for k, v in sorted(meta.get("approx", {}).items()):
        A(f"- {v}")
    A("")
    for m in M.hook_modules:
        notes = getattr(m, "APPROX_NOTES", None)
        if notes:
            A(f"### 7.2 {getattr(m, 'MOD_TITLE', m.__name__)}")
            A("")
            for x in notes:
                A(f"- {x}")
            A("")
    A("## 8. 输出文件")
    A("")
    A("- cells.csv：每个（卡组×幕×房间）的胜率、回合、掉血、循环报警。")
    A("- cards.csv：每个卡组里每张卡（及能力/遗物来源）的使用次数、每次伤害/格挡/付费、效率倍数。")
    A("- encounters.csv：每个卡组对每个具体遭遇的胜率与回合。")
    A("- raw.jsonl：每一场的原始结果；meta.json：实验配置与用时。")
    A("- coverage_monsters.csv / coverage_encounters.csv：每个怪物的意图逻辑来源、每个遭遇的组成来源与可模拟状态。")
    A("")
    A(ROADMAP)
    open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8").write("\n".join(L))
    return os.path.join(out_dir, "report.md")
