"""种子预览：给定游戏种子（和角色、进阶），给出地图、遭遇队列和开局奖励，不打战斗。

地图和遭遇来自本机生成的游戏逻辑（和 tools/seed_probe.py 同一条路），不是把游戏数据打进仓库。
没有本机游戏缓存时 preview() 抛 PreviewError('no_engine')。

和真游戏一致的前提（和种子探针相同）：全解锁、不是教程局、没有自定义修改器。
第 1 幕地图是进幕时 CreateMap 的结果。后面几幕也是「如果现在进这一幕会生成的图」，
中间没有把上一幕真的打完，所以标成 projected：只有地图随机流不被战斗消耗时才和实机一致。
普通/精英/首领队列是开局 GenerateRooms 就排好的，不依赖有没有把图打完。
未知节点（?）要走进去才掷点，这里不提前掷。
奖励是选完开局古神之后、第一场普通战斗的奖励界面，不模拟那一场战斗。
"""
from __future__ import annotations

import os
import sys

from sts2sim.engine.seed import SEED_CHARS, SEED_LEN, canonicalize

CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]

LIMITS = (
    "full_unlocks",
    "not_tutorial",
    "no_modifiers",
    "unknown_nodes",
    "later_act_maps_projected",
    "rewards_no_combat",
)


class PreviewError(Exception):
    def __init__(self, code, **params):
        self.code = code
        self.params = params
        super().__init__(code)


def _tools():
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    tools = os.path.join(root, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    if root not in sys.path:
        sys.path.insert(0, root)
    import seed_probe
    return seed_probe


def tally(ids):
    counts = {}
    order = []
    for i in ids or []:
        if i not in counts:
            order.append(i)
            counts[i] = 0
        counts[i] += 1
    return [{"id": i, "n": counts[i]} for i in order]


def distribution(rooms):
    out = []
    for a in rooms or []:
        normals = list(a.get("normal") or [])
        elites = list(a.get("elite") or [])
        out.append({
            "act": a.get("act"),
            "boss": a.get("boss"),
            "second_boss": a.get("second_boss"),
            "ancient": a.get("ancient"),
            "normal": normals,
            "elite": elites,
            "events": list(a.get("events") or []),
            "normal_counts": tally(normals),
            "elite_counts": tally(elites),
        })
    return out


def map_counts(mp):
    counts = {}
    saw_boss = False
    for row in (mp or {}).get("rows") or []:
        for n in row:
            typ = n.get("type") or "Unassigned"
            counts[typ] = counts.get(typ, 0) + 1
            if typ == "Boss":
                saw_boss = True
    if (mp or {}).get("boss") and not saw_boss:
        counts["Boss"] = counts.get("Boss", 0) + 1
    return counts


def _model_id(obj, depth=0):
    if obj is None or depth > 3 or isinstance(obj, (bool, int, float)):
        return None
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    ident = getattr(obj, "Id", None)
    entry = getattr(ident, "Entry", None) if ident is not None else None
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    for name in ("Relic", "Model", "CanonicalRelic"):
        inner = getattr(obj, name, None)
        if inner is not None and inner is not obj:
            hit = _model_id(inner, depth + 1)
            if hit:
                return hit
    return None


def _seq_ids(seq, limit):
    if seq is None or isinstance(seq, (str, bytes)):
        return []
    try:
        items = list(seq)
    except TypeError:
        return []
    ids = []
    for it in items:
        if len(ids) >= limit:
            break
        eid = _model_id(it)
        if eid:
            ids.append(eid)
    return ids


def _bag_ids(bag, limit=16):
    if not bag:
        return []
    found = []
    seen = set()

    def take(seq):
        for eid in _seq_ids(seq, limit):
            if eid not in seen:
                seen.add(eid)
                found.append(eid)

    data = getattr(bag, "__dict__", None) or {}
    for key, val in data.items():
        if str(key).startswith("__"):
            continue
        take(val)
        if len(found) >= limit:
            return found[:limit]
    for name in ("_relics", "relics", "_items", "_queue", "_models", "Models"):
        if name not in data:
            take(getattr(bag, name, None))
    return found[:limit]


def peek_relics(state, player, limit=16):
    """开局就已放进遗物袋的顺序（若引擎把列表露在字段上）。不调用会消耗随机的抽取方法。"""
    shared = _bag_ids(getattr(state, "SharedRelicGrabBag", None), limit)
    char_bag = None
    for name in ("RelicGrabBag", "_relicGrabBag"):
        cand = getattr(player, name, None)
        if cand:
            char_bag = cand
            break
    if char_bag is None:
        for key, val in (getattr(player, "__dict__", None) or {}).items():
            low = str(key).lower()
            if "relic" in low and "grab" in low:
                char_bag = val
                break
    starting = []
    try:
        for relic in list(getattr(player, "Relics", []) or []):
            eid = _model_id(relic)
            if eid:
                starting.append(eid)
    except TypeError:
        pass
    return {"starting": starting, "shared_queue": shared, "character_queue": _bag_ids(char_bag, limit)}


def _first_unlocked(options):
    for o in options:
        if not o.get("locked"):
            return o["index"]
    return 0 if options else None


def _neow_indexes(neow, options):
    if neow in (None, "none"):
        return []
    if neow in ("all",):
        return [o["index"] for o in options]
    if neow in ("first",):
        i = _first_unlocked(options)
        return [] if i is None else [i]
    try:
        return [int(neow)]
    except (TypeError, ValueError):
        raise PreviewError("bad_neow")


def seed_warning_codes(raw, canon):
    """和 sts2sim.engine.seed.warnings 同一套判断，但返回可翻译的 code，避免界面只有中文。"""
    codes = []
    if str(raw) != canon:
        codes.append({"code": "seedNormalized", "raw": str(raw), "canon": canon})
    bad = sorted({c for c in canon if c not in SEED_CHARS})
    if bad:
        codes.append({"code": "seedCharset", "chars": "".join(bad)})
    elif len(canon) != SEED_LEN:
        codes.append({"code": "seedLength", "n": len(canon), "want": SEED_LEN})
    return codes


def assemble(seed, canon, warnings, character, ascension, acts, maps, rooms, ancient, neow_options, after_neow, relics, extra_warnings=()):
    noted = []
    for w in list(warnings) + list(extra_warnings):
        if isinstance(w, str):
            noted.append({"code": "text", "text": w})
        elif isinstance(w, dict) and w not in noted:
            noted.append(w)
    if not (relics or {}).get("shared_queue") and not (relics or {}).get("character_queue"):
        if not any(w.get("code") == "relicQueueHidden" for w in noted):
            noted.append({"code": "relicQueueHidden"})
    rich_maps = []
    for mp in maps:
        item = dict(mp)
        if "counts" not in item:
            item["counts"] = map_counts(item)
        rich_maps.append(item)
    return {
        "v": 1,
        "seed_input": seed,
        "seed": canon,
        "warnings": noted,
        "character": character,
        "ascension": int(ascension),
        "acts": list(acts),
        "maps": rich_maps,
        "rooms": rooms,
        "distribution": distribution(rooms),
        "ancient": ancient,
        "neow_options": neow_options,
        "after_neow": after_neow,
        "relics": relics or {"starting": [], "shared_queue": [], "character_queue": []},
        "limits": list(LIMITS),
    }


def _fresh(char, asc, seed):
    from sts2sim.engine.agents import Agent
    from sts2sim.engine.run import RunDriver
    return RunDriver(char, asc, seed, agent=Agent())


def preview(seed, char="Ironclad", asc=0, neow="first"):
    if char not in CHARS:
        raise PreviewError("bad_char", char=str(char))
    try:
        asc = int(asc)
    except (TypeError, ValueError):
        raise PreviewError("bad_asc")
    if asc < 0 or asc > 10:
        raise PreviewError("bad_asc")
    canon = canonicalize(seed)
    if not str(canon).strip():
        raise PreviewError("need_seed")
    try:
        from sts2sim.rt.boot import game as G  # noqa: F401
    except Exception as e:
        first = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
        raise PreviewError("no_engine", err=first) from e
    sp = _tools()
    driver = _fresh(char, asc, canon)
    driver._create()
    state = driver.state
    rooms = sp._rooms(state)
    relics = peek_relics(state, driver.player)
    acts = []
    maps = []
    for i, act in enumerate(list(state.Acts)):
        aid = act.Id.Entry
        acts.append(aid)
        try:
            driver.mgr.SetActInternal(i)
            mp = sp._map(G, state)
        except Exception as e:  # noqa: BLE001 — 某一幕地图失败不要丢掉整份预览
            maps.append({
                "act_index": i, "act": aid, "rows": [], "cols": 0, "boss": None,
                "confidence": "failed", "error": f"{type(e).__name__}: {e}", "counts": {},
            })
            continue
        mp["act_index"] = i
        mp["act"] = aid
        mp["confidence"] = "act_entry" if i == 0 else "projected"
        mp["counts"] = map_counts(mp)
        maps.append(mp)

    _d, ev, _G = sp._build(char, asc, canon)
    neow_options = [
        {"index": i, "key": k, "id": k.rsplit(".", 1)[-1], "locked": lk}
        for i, (k, lk) in enumerate(zip(ev.get("options", []), ev.get("locked", [])))
    ]
    after = {}
    for i in _neow_indexes(neow, neow_options):
        try:
            d2, _, g2 = sp._build(char, asc, canon, neow=i)
            after[str(i)] = sp._rewards(g2, d2)
        except Exception as e:  # noqa: BLE001
            after[str(i)] = {"error": f"{type(e).__name__}: {e}"}
    return assemble(
        seed, canon, seed_warning_codes(seed, canon), char, asc, acts, maps, rooms,
        ev.get("ancient"), neow_options, after, relics,
    )


def format_text(res, lang="zhs"):
    """命令行用的纯文本。名字保持 ID（游戏文本不进仓库）。"""
    from gui import i18n
    t = lambda key, **kw: i18n.t(key, lang, **kw)  # noqa: E731
    lines = [t("prev.text.head", seed=res.get("seed"), char=res.get("character"), asc=res.get("ascension"))]
    for w in res.get("warnings") or []:
        if isinstance(w, dict) and w.get("code") and i18n.has("prev.warn." + w["code"], lang):
            lines.append(t("prev.warn." + w["code"], **{k: v for k, v in w.items() if k != "code"}))
        elif isinstance(w, str):
            lines.append(w)
        elif isinstance(w, dict) and w.get("text"):
            lines.append(str(w["text"]))
    lines.append(t("prev.text.acts", acts=i18n.join(res.get("acts") or [], lang) or t("common.none")))
    for mp in res.get("maps") or []:
        conf = mp.get("confidence") or ""
        label = t("prev.confidence." + conf) if conf and i18n.has("prev.confidence." + conf, lang) else conf
        lines.append("")
        lines.append(t("prev.text.mapHead", n=mp.get("act_index", 0) + 1, act=mp.get("act") or "", conf=label))
        if mp.get("error"):
            lines.append(mp["error"])
            continue
        lines.append(_ascii_map(mp))
        counts = mp.get("counts") or {}
        if counts:
            bits = [f"{t('mp.' + k) if i18n.has('mp.' + k, lang) else k} {v}" for k, v in counts.items()]
            lines.append(t("prev.text.counts", bits=i18n.join(bits, lang)))
    lines.append("")
    lines.append(t("prev.text.distHead"))
    for d in res.get("distribution") or []:
        lines.append(t("prev.text.actBoss", act=d.get("act"), boss=d.get("boss") or t("common.none"),
                       second=d.get("second_boss") or t("common.none"), ancient=d.get("ancient") or t("common.none")))
        lines.append(t("prev.text.queue", kind=t("prev.normal"), ids=i18n.join(d.get("normal") or [], lang) or t("common.none")))
        lines.append(t("prev.text.queue", kind=t("prev.elite"), ids=i18n.join(d.get("elite") or [], lang) or t("common.none")))
    lines.append("")
    lines.append(t("prev.text.neow", ancient=res.get("ancient") or t("common.none")))
    for o in res.get("neow_options") or []:
        lock = t("prev.locked") if o.get("locked") else ""
        lines.append(f"  [{o.get('index')}] {o.get('id')}{lock}")
    for key, block in (res.get("after_neow") or {}).items():
        lines.append(t("prev.rewardFor", index=key))
        if not isinstance(block, dict):
            continue
        if block.get("error"):
            lines.append("  " + block["error"])
            continue
        lines.append("  " + t("prev.encounter") + " " + str(block.get("encounter")))
        for reward in block.get("rewards") or []:
            if "cards" in reward:
                lines.append("  " + t("prev.cards") + " " + i18n.join(reward["cards"], lang))
            if "gold" in reward:
                lines.append("  " + t("prev.gold") + " " + str(reward["gold"]))
            if reward.get("potion"):
                lines.append("  " + t("prev.potion") + " " + reward["potion"])
            if reward.get("relic"):
                lines.append("  " + t("prev.relic") + " " + reward["relic"])
    rel = res.get("relics") or {}
    lines.append("")
    lines.append(t("prev.text.starting", ids=i18n.join(rel.get("starting") or [], lang) or t("common.none")))
    lines.append(t("prev.text.shared", ids=i18n.join(rel.get("shared_queue") or [], lang) or t("prev.noQueue")))
    lines.append(t("prev.text.characterQueue", ids=i18n.join(rel.get("character_queue") or [], lang) or t("prev.noQueue")))
    lines.append("")
    for code in res.get("limits") or []:
        if i18n.has("prev.limit." + code, lang):
            lines.append("- " + t("prev.limit." + code))
    return "\n".join(lines)


def _ascii_map(mp):
    symbols = {"Monster": "M", "Elite": "E", "Unknown": "?", "Shop": "$", "RestSite": "R",
               "Treasure": "T", "Boss": "B", "Ancient": "A", "Unassigned": "."}
    cols = int(mp.get("cols") or 0)
    by = {(n["col"], n["row"]): n for row in mp.get("rows") or [] for n in row}
    boss = mp.get("boss") or {}
    rows = [n["row"] for n in by.values()]
    if boss.get("row") is not None:
        rows.append(boss["row"])
    if not rows or cols <= 0:
        return ""
    maxrow = max(rows)
    w = 4
    lines = []
    if boss.get("col") is not None:
        lines.append(" " * (w * int(boss["col"])) + "  B")
    for r in range(maxrow, 0, -1):
        cells = []
        for c in range(cols):
            if boss.get("row") == r and boss.get("col") == c and (c, r) not in by:
                cells.append("[B]")
                continue
            n = by.get((c, r))
            cells.append(f"[{symbols.get(n['type'], '?')}]" if n else "  ")
        lines.append(f"{r:>2} " + "".join(x.center(w) for x in cells))
    return "\n".join(lines)
