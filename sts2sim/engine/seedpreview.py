"""种子预览：给一个游戏种子（角色、进阶），不跑完整一局，列出第 1 幕地图、
普通/精英/首领的出场顺序，以及开局就能确定的奖励。

Seed preview: map, encounter order and opening rewards for one game seed, without playing a run.
Names come from the player's own install at runtime (gui.i18n / gameloc) and are never shipped.
"""
import argparse
import json
import threading

from .seed import SEED_CHARS, SEED_LEN, canonicalize

CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]
# 地图点类型。短标记在 gui/locales 的 sp.glyph.*，长名字在 room.*。
POINT_TYPES = ("Monster", "Elite", "Unknown", "Shop", "RestSite", "Treasure", "Boss", "Ancient", "Unassigned")
_LOCK = threading.Lock()


class PreviewError(Exception):
    """可翻译的失败：http 状态码 + 翻译键。"""

    def __init__(self, http, key, **kw):
        super().__init__(key)
        self.http = http
        self.key = key
        self.kw = kw


class _Stop(Exception):
    pass


def ui_lang(lang):
    from gui import i18n
    if lang in (None, ""):
        return i18n.current()
    return i18n.normalize(lang)


def warning_codes(raw, canon=None):
    """结构化警告（界面按语言翻译）。和 seed.warnings 的判定一致。"""
    canon = canonicalize(raw) if canon is None else canon
    out = []
    if str(raw) != canon:
        out.append({"code": "normalized", "raw": str(raw), "canon": canon})
    bad = sorted({c for c in canon if c not in SEED_CHARS})
    if bad:
        out.append({"code": "charset", "chars": "".join(bad)})
    elif canon and len(canon) != SEED_LEN:
        out.append({"code": "length", "length": len(canon), "expect": SEED_LEN})
    return out


def _t(key, lang, **kw):
    from gui import i18n
    return i18n.t(key, lang, **kw)


def warning_text(codes, lang):
    lang = ui_lang(lang)
    lines = []
    for c in codes:
        code = c.get("code")
        if code == "normalized":
            lines.append(_t("sp.warn.normalized", lang, raw=c.get("raw", ""), canon=c.get("canon", "")))
        elif code == "charset":
            lines.append(_t("sp.warn.charset", lang, chars=c.get("chars", "")))
        elif code == "length":
            lines.append(_t("sp.warn.length", lang, length=c.get("length", 0), expect=c.get("expect", SEED_LEN)))
    return lines


def room_counts(mp):
    """地图上每种点各有几个。首领点如果已经在某一行里，不重复计。"""
    from collections import Counter
    c = Counter()
    seen = set()
    for row in (mp or {}).get("rows") or []:
        for n in row:
            key = (n.get("col"), n.get("row"))
            if key in seen:
                continue
            seen.add(key)
            c[n.get("type") or "Unassigned"] += 1
    b = (mp or {}).get("boss")
    if b and (b.get("col"), b.get("row")) not in seen:
        c["Boss"] += 1
    return [{"type": t, "count": c[t]} for t in POINT_TYPES if c.get(t)]


def tally(ids):
    """按第一次出现的顺序统计次数，并保留完整抽取顺序。"""
    counts = {}
    first = []
    order = []
    for i in ids or []:
        order.append(i)
        if i not in counts:
            first.append(i)
            counts[i] = 0
        counts[i] += 1
    return {"order": order, "counts": [{"id": i, "count": counts[i]} for i in first]}


def distribution(mp, rooms):
    acts = []
    for r in rooms or []:
        acts.append({
            "act": r.get("act"),
            "normal": tally(r.get("normal")),
            "elite": tally(r.get("elite")),
            "boss": r.get("boss"),
            "second_boss": r.get("second_boss"),
            "ancient": r.get("ancient"),
            "events": tally(r.get("events")),
        })
    return {"map_rooms": room_counts(mp), "acts": acts}


def _entry(obj):
    ident = getattr(obj, "Id", None)
    if ident is None and isinstance(obj, str):
        return obj
    ent = getattr(ident, "Entry", None)
    return ent if isinstance(ent, str) and ent else None


def _as_list(v):
    if v is None or isinstance(v, (str, bytes)):
        return None
    try:
        return list(v)
    except TypeError:
        pass
    n = getattr(v, "Count", None)
    if isinstance(n, int):
        try:
            return [v[i] for i in range(n)]
        except Exception:  # noqa
            return None
    return None


def relic_ids(bag, limit=24):
    """从遗物包对象里读出 Id（读不到就空列表）。顺序是包里当前的顺序，不保证抽取顺序。"""
    if bag is None:
        return []
    seqs = []
    direct = _as_list(bag)
    if direct:
        seqs.append(direct)
    for name in ("_relics", "relics", "Relics", "_contents", "_items", "_bag", "Bag"):
        v = getattr(bag, name, None)
        if v is None or v is bag:
            continue
        seq = _as_list(v)
        if seq:
            seqs.append(seq)
    for seq in seqs:
        ids = [e for e in (_entry(x) for x in seq) if e]
        if ids:
            return ids[:limit]
    return []


def _lookup(table, key, lang):
    """游戏表里的名字。<key>.title，没有再试完整键。没有安装就 None。"""
    if not key:
        return None
    from gui import i18n
    v = i18n.game_text(table, key, lang)
    if v:
        return v
    try:
        from sts2sim import gameloc
    except Exception:  # noqa
        return None
    for g in i18n.game_langs(lang):
        try:
            tb = gameloc.table(table, g) or {}
        except Exception:  # noqa
            tb = {}
        val = tb.get(key + ".title") or tb.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def card_name(cid, lang):
    if not cid:
        return None
    up = str(cid).endswith("+")
    base = str(cid).rstrip("+")
    n = _lookup("cards", base, lang)
    if not n:
        return None
    return n + ("+" if up else "")


def neow_name(text_key, lang):
    if not text_key:
        return None
    n = _lookup("ancients", text_key, lang) or _lookup("events", text_key, lang)
    if n:
        return n
    last = str(text_key).rsplit(".", 1)[-1]
    return _lookup("relics", last, lang)


def _put(bucket, key, name):
    if key and name:
        bucket.setdefault(key, name)


def collect_labels(res, lang):
    """ID → 名字。读不到的键不放进去，界面就显示 ID。"""
    lang = ui_lang(lang)
    enc, relics, cards, potions, acts, ancients, neow = {}, {}, {}, {}, {}, {}, {}

    def enc_id(i):
        _put(enc, i, _lookup("encounters", i, lang) or _lookup("events", i, lang))

    def relic(i):
        _put(relics, i, _lookup("relics", i, lang))

    def potion(i):
        _put(potions, i, _lookup("potions", i, lang))

    for a in res.get("acts") or []:
        _put(acts, a, _lookup("acts", a, lang))
    for room in res.get("rooms") or []:
        _put(acts, room.get("act"), _lookup("acts", room.get("act"), lang))
        for i in (room.get("normal") or []) + (room.get("elite") or []) + (room.get("events") or []):
            enc_id(i)
        enc_id(room.get("boss"))
        enc_id(room.get("second_boss"))
        _put(ancients, room.get("ancient"), _lookup("ancients", room.get("ancient"), lang) or _lookup("events", room.get("ancient"), lang))
    notable = res.get("notable") or {}
    for i in notable.get("relics") or []:
        relic(i)
    for i in notable.get("deck") or []:
        _put(cards, i, card_name(i, lang))
    anc = res.get("ancient")
    _put(ancients, anc, _lookup("ancients", anc, lang) or _lookup("events", anc, lang))
    for o in res.get("neow_options") or []:
        name = neow_name(o.get("key"), lang)
        if name:
            neow[o.get("key")] = name
    for block in (res.get("after_neow") or {}).values():
        if not isinstance(block, dict):
            continue
        enc_id(block.get("encounter"))
        for rw in block.get("rewards") or []:
            for c in rw.get("cards") or []:
                _put(cards, c, card_name(c, lang))
            potion(rw.get("potion"))
            relic(rw.get("relic"))
    return {"encounters": enc, "relics": relics, "cards": cards, "potions": potions,
            "acts": acts, "ancients": ancients, "neow": neow}


def _nm(labels, bucket, key):
    if not key:
        return ""
    name = (labels.get(bucket) or {}).get(key)
    if name and name != key:
        return f"{name} ({key})"
    return str(key)


def _fmt_order(ids, labels, bucket, lang):
    if not ids:
        return _t("sp.none", lang)
    return _t("sep.list", lang).join(f"{i + 1}. {_nm(labels, bucket, x)}" for i, x in enumerate(ids))


def render_map(mp, lang="zh"):
    """第一幕地图的字符画。上 = 首领，下 = 第 1 行，和游戏画面同方向。"""
    lang = ui_lang(lang)
    cols = int(mp.get("cols") or 0)
    W = 4
    lines = []
    by = {(n["col"], n["row"]): n for row in mp.get("rows") or [] for n in row}
    if not by and not mp.get("boss"):
        return ""
    boss = mp.get("boss") or {"col": 0, "row": max((n["row"] for n in by.values()), default=1)}
    maxrow = max(n["row"] for n in by.values()) if by else int(boss["row"])
    glyph = _t("sp.glyph.Boss", lang)
    lines.append(" " * (W * int(boss["col"])) + f"  {glyph}" + "   " + _t("sp.mapBoss", lang, row=boss["row"]))
    for r in range(maxrow, 0, -1):
        cells = []
        for c in range(cols):
            n = by.get((c, r))
            if n:
                g = _t("sp.glyph." + n["type"], lang) if n["type"] in POINT_TYPES else "?"
                cells.append(f"[{g}]")
            else:
                cells.append("  ")
        lines.append(f"{r:>2} " + "".join(x.center(W) for x in cells))
        if r > 1:
            conn = [" "] * (cols * W)
            for c in range(cols):
                n = by.get((c, r - 1))
                if not n:
                    continue
                for cc, rr in n.get("children") or []:
                    if rr != r:
                        continue
                    pos = c * W + W // 2
                    if cc == c:
                        conn[pos] = "|"
                    elif cc > c:
                        conn[min(len(conn) - 1, pos + W // 2)] = "/"
                    else:
                        conn[max(0, pos - W // 2)] = "\\"
            lines.append("   " + "".join(conn))
    lines.append("   " + "".join(str(c).center(W) for c in range(cols)) + "  " + _t("sp.mapCols", lang))
    return "\n".join(lines)


def _reward_parts(rewards, labels, lang):
    parts = []
    for x in rewards or []:
        if x.get("cards"):
            parts.append(_t("sp.cards", lang) + " " + _t("sep.list", lang).join(_nm(labels, "cards", c) for c in x["cards"]))
        if "gold" in x:
            parts.append(_t("sp.goldReward", lang, n=x["gold"]))
        if x.get("potion"):
            parts.append(_t("sp.potion", lang) + " " + _nm(labels, "potions", x["potion"]))
        if x.get("relic"):
            parts.append(_t("sp.relic", lang) + " " + _nm(labels, "relics", x["relic"]))
    return parts


def render(res, lang="zh"):
    """纯文本：地图 + 遭遇分布 + 开局奖励。给命令行，也放进 API 的 summary。"""
    lang = ui_lang(lang)
    labels = res.get("labels") or {}
    L = []
    L.append(_t("sp.head", lang, seed=res.get("seed", ""), char=res.get("character", ""), asc=res.get("ascension", 0)))
    for w in res.get("warnings") or []:
        L.append("  " + w)
    acts = res.get("acts") or []
    if acts:
        L.append(_t("sp.actsLine", lang, acts=_t("sep.list", lang).join(_nm(labels, "acts", a) for a in acts)))
    dist = res.get("distribution") or {}
    mix = dist.get("map_rooms") or []
    if mix:
        L.append(_t("sp.roomMix", lang) + _t("sep.list", lang).join(
            _t("sp.times", lang, name=_t("room." + it["type"], lang) if it["type"] in POINT_TYPES else it["type"], n=it["count"])
            for it in mix))
    mp = res.get("map")
    if mp:
        act0 = acts[0] if acts else ""
        L.append("")
        L.append(_t("sp.mapTitle", lang, act=_nm(labels, "acts", act0) if act0 else _t("sp.actN", lang, n=1)))
        L.append(render_map(mp, lang))
    L.append("")
    L.append(_t("sp.distTitle", lang))
    L.append(_t("sp.queueHint", lang))
    L.append(_t("sp.unknownHint", lang))
    for i, act in enumerate(dist.get("acts") or []):
        L.append(_t("sp.actN", lang, n=i + 1) + "  " + _nm(labels, "acts", act.get("act")))
        if act.get("boss"):
            L.append("  " + _t("sp.boss", lang) + " " + _nm(labels, "encounters", act["boss"]))
        if act.get("second_boss"):
            L.append("  " + _t("sp.secondBoss", lang) + " " + _nm(labels, "encounters", act["second_boss"]))
        if act.get("ancient"):
            L.append("  " + _t("sp.ancient", lang) + " " + _nm(labels, "ancients", act["ancient"]))
        L.append("  " + _t("sp.normal", lang) + " " + _fmt_order((act.get("normal") or {}).get("order"), labels, "encounters", lang))
        L.append("  " + _t("sp.elite", lang) + " " + _fmt_order((act.get("elite") or {}).get("order"), labels, "encounters", lang))
        ev = (act.get("events") or {}).get("order") or []
        if ev:
            L.append("  " + _t("sp.events", lang) + " " + _fmt_order(ev, labels, "encounters", lang))
    notable = res.get("notable") or {}
    L.append("")
    L.append(_t("sp.notable", lang))
    L.append("  " + _t("sp.startingRelics", lang) + " " + (
        _t("sep.list", lang).join(_nm(labels, "relics", r) for r in notable.get("relics") or []) or _t("sp.none", lang)))
    L.append("  " + _t("sp.startingDeck", lang) + " " + (
        _t("sep.list", lang).join(_nm(labels, "cards", c) for c in notable.get("deck") or []) or _t("sp.none", lang)))
    if notable.get("gold") is not None:
        L.append("  " + _t("sp.gold", lang) + " " + str(notable["gold"]))
    if res.get("ancient"):
        L.append("  " + _t("sp.neowTitle", lang) + " " + _nm(labels, "ancients", res.get("ancient")))
    for o in res.get("neow_options") or []:
        name = (labels.get("neow") or {}).get(o.get("key")) or o.get("id") or o.get("key")
        lock = ("  [" + _t("sp.locked", lang) + "]") if o.get("locked") else ""
        L.append(f"    [{o.get('index')}] {name}{lock}")
    after = res.get("after_neow") or {}
    for i in sorted(after, key=lambda s: int(s) if str(s).isdigit() else str(s)):
        a = after[i]
        if not isinstance(a, dict):
            continue
        if a.get("error"):
            L.append("  " + _t("sp.failed", lang, err=a["error"]))
            continue
        enc = _nm(labels, "encounters", a.get("encounter"))
        parts = _reward_parts(a.get("rewards"), labels, lang)
        L.append("  " + _t("sp.firstReward", lang, index=i, encounter=enc or _t("sp.none", lang))
                 + (" " + _t("sep.problems", lang).join(parts) if parts else ""))
    return "\n".join(L)


def assemble(seed, char, asc, mp, rooms, ancient, options, starting, after_neow, lang="zhs"):
    """把已经读出的地图 / 遭遇 / 奖励收成预览结果。不接触游戏。"""
    lang = ui_lang(lang)
    canon = canonicalize(seed)
    codes = warning_codes(seed, canon)
    notable = {
        "relics": list((starting or {}).get("relics") or []),
        "deck": list((starting or {}).get("deck") or []),
        "gold": (starting or {}).get("gold"),
    }
    res = {
        "v": 2,
        "seed_input": str(seed),
        "seed": canon,
        "warning_codes": codes,
        "warnings": warning_text(codes, lang),
        "character": char,
        "ascension": int(asc),
        "acts": [r.get("act") for r in (rooms or [])],
        "map": mp,
        "rooms": rooms,
        "distribution": distribution(mp, rooms),
        "ancient": ancient,
        "neow_options": options or [],
        "after_neow": after_neow or {},
        "notable": notable,
    }
    res["labels"] = collect_labels(res, lang)
    res["summary"] = render(res, lang)
    return res


def parse_args_values(seed, char="Ironclad", asc=0, neow="all"):
    """校验种子 / 角色 / 进阶 / Neow。失败抛 PreviewError。"""
    if seed is None or not str(seed).strip():
        raise PreviewError(400, "sp.badSeed")
    if char not in CHARS:
        raise PreviewError(400, "sp.badChar", char=str(char))
    try:
        asc_i = int(asc)
    except (TypeError, ValueError):
        raise PreviewError(400, "sp.badAsc")
    if asc_i < 0 or asc_i > 10:
        raise PreviewError(400, "sp.badAsc")
    if neow is None or neow == "all":
        neow_v = "all"
    elif str(neow) == "none":
        neow_v = None
    else:
        try:
            neow_v = int(neow)
        except (TypeError, ValueError):
            raise PreviewError(400, "sp.badNeow")
        if neow_v < 0:
            raise PreviewError(400, "sp.badNeow")
    return str(seed), char, asc_i, neow_v


# ---------------- 引擎（本机游戏生成的代码；没有安装就 PreviewError） ----------------
def _tn(e):
    try:
        return e.name
    except AttributeError:
        return str(e).split(".")[-1]


def _build(char, asc, seed, neow=None):
    try:
        from sts2sim.rt.boot import game as G
        from sts2sim.engine import run as R
        from sts2sim.engine.agents import Agent
    except ModuleNotFoundError as e:
        raise PreviewError(503, "sp.noGame") from e
    except Exception as e:  # noqa
        raise PreviewError(503, "sp.noGame") from e

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


def read_map(G, st):
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


def read_rooms(st):
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


def _starting(d):
    p = d.player
    return {
        "relics": [x.Id.Entry for x in p.Relics],
        "deck": [c.Id.Entry + ("+" if c.IsUpgraded else "") for c in p.Deck.Cards],
        "gold": int(p.Gold),
    }


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
    return {"encounter": room.Encounter.Id.Entry, "rewards": out}


def _preview_unlocked(seed, char, asc, neow, lang):
    seed, char, asc, neow_v = parse_args_values(seed, char, asc, neow)
    canon = canonicalize(seed)
    try:
        d, ev, G = _build(char, asc, canon)
    except PreviewError:
        raise
    except Exception as e:  # noqa
        raise PreviewError(500, "sp.failed", err=f"{type(e).__name__}: {e}") from e
    if d.state is None:
        raise PreviewError(500, "sp.failed", err="no run state")
    try:
        mp = read_map(G, d.state)
        rooms = read_rooms(d.state)
        starting = _starting(d)
    except Exception as e:  # noqa
        raise PreviewError(500, "sp.failed", err=f"{type(e).__name__}: {e}") from e
    options = [{"index": i, "key": k, "id": k.rsplit(".", 1)[-1], "locked": lk}
               for i, (k, lk) in enumerate(zip(ev.get("options", []), ev.get("locked", [])))]
    if isinstance(neow_v, int) and neow_v >= len(options):
        raise PreviewError(400, "sp.badNeow")
    idxs = [] if neow_v is None else (range(len(options)) if neow_v == "all" else [neow_v])
    after = {}
    for i in idxs:
        try:
            d2, _, G2 = _build(char, asc, canon, neow=i)
            after[str(i)] = _rewards(G2, d2)
        except PreviewError:
            raise
        except Exception as e:  # noqa
            after[str(i)] = {"error": f"{type(e).__name__}: {e}"}
    return assemble(seed, char, asc, mp, rooms, ev.get("ancient"), options, starting, after, lang)


def preview(seed, char="Ironclad", asc=0, neow="all", lang=None):
    """生成预览。同一进程里引擎状态是全局的，所以加锁。"""
    with _LOCK:
        return _preview_unlocked(seed, char, asc, neow, lang)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="种子预览 / Seed preview: act 1 map, encounter order, opening rewards. Does not play a run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("seed")
    ap.add_argument("--char", default="Ironclad", choices=CHARS)
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--neow", default="all", help="all / an option index / none")
    ap.add_argument("--json", help="also write the JSON preview to this path")
    ap.add_argument("--lang", default=None, help="zhs / en / ja / ko (default: the UI language)")
    a = ap.parse_args(argv)
    try:
        res = preview(a.seed, a.char, a.asc, a.neow, a.lang)
    except PreviewError as e:
        from gui import i18n
        print(i18n.t(e.key, ui_lang(a.lang), **e.kw))
        return 1
    print(res["summary"])
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
