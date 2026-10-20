"""真游戏种子探针：给一个游戏里显示/输入的种子 + 角色 + 进阶，打印第一幕地图、涅奥选项、第一场普通战斗的奖励。

用途：拿玩家真游戏里的一局（种子 + 第一幕地图截图）对照我们模拟器是不是同一局。
  python tools/seed_probe.py 7F3K9Q2ZB8MA --char Ironclad --asc 0            # 打印
  python tools/seed_probe.py 7F3K9Q2ZB8MA --char Ironclad --neow all --json out.json
种子规范化和游戏一致（SeedHelper.CanonicalizeSeed）：转大写、O→0、I→1、去首尾空格。
游戏随机生成的种子是 12 位，字符集 0-9 A-H J-N P-Z（没有 I、O）；自定义模式可以输入任意文字，同样先规范化。

前提（和真游戏一致的条件，不满足时幕/卡池可能不同）：
  - 全解锁存档（所有时间线纪元已揭示、第一幕「暗港」已发现过）；新存档的卡池和选幕规则不同
  - 不是教程局（存档第一局铁甲战士有固定奖励）
  - 没有勾选自定义模式的修改器
中文名：运行时从玩家本机的游戏安装读（sts2sim/gameloc.py），没有就只显示 ID。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]
TYPE_ZH = {"Monster": "怪", "Elite": "精", "Unknown": "？", "Shop": "商", "RestSite": "火", "Treasure": "宝",
           "Boss": "王", "Ancient": "古", "Unassigned": "·"}
TYPE_EN = {"Monster": "M", "Elite": "E", "Unknown": "?", "Shop": "$", "RestSite": "R", "Treasure": "T",
           "Boss": "B", "Ancient": "A", "Unassigned": "."}


from sts2sim.engine.seed import SEED_CHARS, canonicalize, warnings as seed_warnings  # noqa: E402


# ---------------- 中文名（运行时读本机游戏文本，不进仓库） ----------------
_LOC = {}


def _loc(table):
    if table not in _LOC:
        from sts2sim import gameloc
        _LOC[table] = gameloc.table(table, "zhs") or {}
    return _LOC[table]


def zh(table, key):
    v = _loc(table).get(key + ".title") or _loc(table).get(key)
    return v if isinstance(v, str) else None


def zh_card(cid):
    up = cid.endswith("+")
    n = zh("cards", cid.rstrip("+"))
    return (n + ("+" if up else "")) if n else cid


def zh_neow(text_key):
    n = zh("ancients", text_key) or zh("events", text_key)
    if n:
        return n
    last = text_key.rsplit(".", 1)[-1]
    return zh("relics", last) or last


# ---------------- 我们的引擎 ----------------
class _Stop(Exception):
    pass


def _build(char, asc, seed, neow=None):
    from sts2sim.rt.boot import game as G
    from sts2sim.engine import run as R
    from sts2sim.engine.agents import Agent

    out = {}

    class PD(R.RunDriver):
        def on_room_entered(self, room):
            if not isinstance(room, G.EventRoom):
                raise _Stop()
            ev = self.mgr.EventSynchronizer.GetLocalEvent()
            out["ancient"] = ev.Id.Entry if ev is not None else None
            out["options"] = [o.TextKey for o in ev.CurrentOptions] if ev is not None else []
            out["locked"] = [bool(o.IsLocked) for o in ev.CurrentOptions] if ev is not None else []
            if neow is None:
                raise _Stop()
            first = [True]

            class A(Agent):
                def event_option(self_, event, options, run):
                    if first[0]:
                        first[0] = False
                        return neow
                    return Agent.event_option(self_, event, options, run)
            self.agent = A()
            self.agent.player = self.player
            sel = R.Selector(self.agent)
            G.CardSelectCmd._selectorStack.Clear()
            G.CardSelectCmd._selectorStack.Push(sel)
            self._event(room)
            raise _Stop()

    d = PD(char, asc, seed, agent=Agent())
    try:
        d._create()
        d.mgr.EnterAct(0)
    except _Stop:
        pass
    return d, out, G


def _map(G, st):
    m = st.Map
    rows = []
    for r in range(m.GetRowCount()):
        row = []
        for p in m.GetPointsInRow(r):
            if p is None:
                continue
            row.append({"col": int(p.coord.col), "row": int(p.coord.row), "type": _tn(p.PointType),
                        "children": sorted([[int(c.coord.col), int(c.coord.row)] for c in p.Children])})
        if row:
            rows.append(sorted(row, key=lambda x: x["col"]))
    b = m.BossMapPoint
    return {"rows": rows, "boss": {"col": int(b.coord.col), "row": int(b.coord.row)},
            "cols": int(m.GetColumnCount())}


def _tn(e):
    try:
        return e.name
    except AttributeError:
        return str(e).split(".")[-1]


def _rooms(st):
    acts = []
    for a in st.Acts:
        rs = a._rooms
        d = {"act": a.Id.Entry, "normal": [e.Id.Entry for e in rs.normalEncounters],
             "elite": [e.Id.Entry for e in rs.eliteEncounters], "events": [e.Id.Entry for e in rs.events]}
        try:
            d["boss"] = rs.Boss.Id.Entry
        except Exception:  # noqa
            d["boss"] = None
        d["second_boss"] = rs.SecondBoss.Id.Entry if rs.SecondBoss is not None else None
        try:
            d["ancient"] = rs.Ancient.Id.Entry if rs.HasAncient else None
        except Exception:  # noqa
            d["ancient"] = None
        acts.append(d)
    return acts


def _rewards(G, d):
    st, p = d.state, d.player
    room = G.CombatRoom(st.Act.PullNextEncounter(G.RoomType.Monster).ToMutable(), st)
    rs = G.RewardsCmd.GenerateForRoomEnd(p, room)
    out = []
    for r in rs.Rewards:
        x = {"kind": type(r).__name__}
        if isinstance(r, G.CardReward):
            x["cards"] = [c.Id.Entry + ("+" if c.IsUpgraded else "") for c in r.Cards]
        if isinstance(r, G.GoldReward):
            x["gold"] = int(r.Amount)
        if isinstance(r, G.PotionReward):
            x["potion"] = r.Potion.Id.Entry if r.Potion is not None else None
        if isinstance(r, G.RelicReward):
            x["relic"] = r._relic.Id.Entry if getattr(r, "_relic", None) is not None else None
        out.append(x)
    return {"encounter": room.Encounter.Id.Entry, "rewards": out, "gold": int(p.Gold),
            "deck": [c.Id.Entry for c in p.Deck.Cards], "relics": [x.Id.Entry for x in p.Relics],
            "potions": [x.Id.Entry for x in p.Potions if x is not None]}


def probe(seed, char="Ironclad", asc=0, neow="all"):
    """neow: None（不选）/ 选项序号 / 'all'（每个选项各开一局，报告选完后第一场普通战斗的奖励）。"""
    canon = canonicalize(seed)
    d, ev, G = _build(char, asc, canon)
    st = d.state
    res = {"v": 1, "seed_input": seed, "seed": canon, "warnings": seed_warnings(seed, canon),
           "character": char, "ascension": asc, "acts": [a.Id.Entry for a in st.Acts],
           "map": _map(G, st), "rooms": _rooms(st), "ancient": ev.get("ancient"),
           "neow_options": [{"index": i, "key": k, "id": k.rsplit(".", 1)[-1], "locked": lk}
                            for i, (k, lk) in enumerate(zip(ev.get("options", []), ev.get("locked", [])))],
           "after_neow": {}}
    idxs = [] if neow is None else (range(len(res["neow_options"])) if neow == "all" else [int(neow)])
    for i in idxs:
        d2, _, G = _build(char, asc, canon, neow=i)
        try:
            res["after_neow"][str(i)] = _rewards(G, d2)
        except Exception as e:  # noqa
            res["after_neow"][str(i)] = {"error": f"{type(e).__name__}: {e}"}
    return res


# ---------------- 打印（方便和游戏截图对照） ----------------
def render_map(mp, lang="zh"):
    tbl = TYPE_ZH if lang == "zh" else TYPE_EN
    cols = mp["cols"]
    W = 4
    lines = []
    rows = mp["rows"]
    by = {(n["col"], n["row"]): n for row in rows for n in row}
    maxrow = max(n["row"] for n in by.values())
    # 自上而下打印：最上面是 Boss，最下面是第 1 层，和游戏地图画面同方向
    lines.append(" " * (W * mp["boss"]["col"]) + ("  王" if lang == "zh" else "  B") + f"   ← Boss（第 {mp['boss']['row']} 行）")
    for r in range(maxrow, 0, -1):
        cells = []
        for c in range(cols):
            n = by.get((c, r))
            cells.append(f"[{tbl.get(n['type'], '?')}]" if n else "  ")
        line = "".join(x.center(W) for x in cells)
        lines.append(f"{r:>2} " + line)
        # 连线：本行 → 下一行（r+1）用 / | \ 表示，画在本行上方；这里画到下一行之间
        if r > 1:
            conn = [" "] * (cols * W)
            for c in range(cols):
                n = by.get((c, r - 1))
                if not n:
                    continue
                for cc, rr in n["children"]:
                    if rr != r:
                        continue
                    pos = c * W + W // 2
                    if cc == c:
                        conn[pos] = "|"
                    elif cc > c:
                        conn[pos + W // 2] = "/"
                    else:
                        conn[pos - W // 2] = "\\"
            lines.append("   " + "".join(conn))
    lines.append("   " + "".join(str(c).center(W) for c in range(cols)) + "  ← 列号（0 = 最左）")
    return "\n".join(lines)


def render(res, lang="zh"):
    L = []
    L.append(f"种子 {res['seed']}  角色 {res['character']}  进阶 {res['ascension']}")
    for w in res["warnings"]:
        L.append("  注意：" + w)
    L.append("幕：" + " → ".join(f"{a}({zh('acts', a) or a})" for a in res["acts"]))
    r0 = res["rooms"][0]
    L.append(f"第一幕 Boss：{r0['boss']}（{zh('encounters', r0['boss']) or ''}）")
    L.append("前 3 场普通战斗：" + "、".join(f"{e}({zh('encounters', e) or ''})" for e in r0["normal"][:3]))
    L.append("第 1 场精英：" + f"{r0['elite'][0]}({zh('encounters', r0['elite'][0]) or ''})")
    L.append("")
    L.append("第一幕地图（上 = Boss，下 = 第 1 层，和游戏画面同方向；怪=普通 精=精英 ？=未知 商=商店 火=休息 宝=宝箱）：")
    L.append(render_map(res["map"], lang))
    L.append("")
    L.append(f"开局古神 {res['ancient']} 的选项：")
    for o in res["neow_options"]:
        L.append(f"  [{o['index']}] {zh_neow(o['key'])}  ({o['id']}){'  [锁定]' if o['locked'] else ''}")
    for i, a in res["after_neow"].items():
        if "error" in a:
            L.append(f"选 [{i}] 后：出错 {a['error']}")
            continue
        parts = []
        for x in a["rewards"]:
            if "cards" in x:
                parts.append("卡牌 " + " / ".join(zh_card(c) for c in x["cards"]))
            if "gold" in x:
                parts.append(f"金币 {x['gold']}")
            if x.get("potion"):
                parts.append("药水 " + (zh("potions", x["potion"]) or x["potion"]))
            if x.get("relic"):
                parts.append("遗物 " + (zh("relics", x["relic"]) or x["relic"]))
        L.append(f"选 [{i}] 后，第一场普通战斗（{zh('encounters', a['encounter']) or a['encounter']}）的奖励：" + "；".join(parts))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed")
    ap.add_argument("--char", default="Ironclad", choices=CHARS)
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--neow", default="all", help="all / 序号 / none")
    ap.add_argument("--json", help="另存 JSON")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    a = ap.parse_args()
    neow = None if a.neow == "none" else a.neow
    res = probe(a.seed, a.char, a.asc, neow)
    print(render(res, a.lang))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
