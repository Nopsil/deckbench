"""只读解析《杀戮尖塔 2》的历史记录（.run）和当前存档（current_run*.save）。

不写回任何文件，也不需要游戏安装。两种 JSON 长得不像，字段还随版本漂；
踩到的坑记在 docs/SAVE_FORMAT.md。这里输出的是我们自己的视图（种子、路线、
选牌、遗物），不是游戏的存档对象。

Read-only parser for Slay the Spire 2 run history and live saves.
Never writes. See docs/SAVE_FORMAT.md for the format pitfalls.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys

from sts2sim.engine.seed import canonicalize

MAX_IN = 32 * 1024 * 1024
MAX_OUT = 64 * 1024 * 1024
MAX_FILES = 400
MAX_WALK = 8000
MAX_DEPTH = 6
STEAM_APP = "2868840"

# 界面翻译键 imp.warn.<code> / imp.err.<code> / imp.point.<code> / imp.letter.<code> 要和这里一致。
WARN_CODES = (
    "gzip", "bom", "utf16", "seed_from_rng", "seed_missing", "seed_numeric_only",
    "coords_partial", "coords_unmatched", "map_unknown", "flat_history", "bad_act",
    "game_mode_numeric", "scan_cap", "time_ms",
)
ERR_CODES = (
    "not_found", "not_run", "json", "empty", "too_big", "not_file", "io", "bad_player",
)
POINT_TYPES = (
    "ancient", "boss", "elite", "monster", "rest_site", "shop", "treasure", "unknown", "event",
)

_SKIP_NAMES = {
    "progress.save", "progress.save.backup",
    "settings.save", "settings.save.backup",
    "prefs.save", "prefs.save.backup",
    "profile.save", "profile.save.backup",
}
_POINT = {
    "ancient": "ancient", "boss": "boss", "elite": "elite", "monster": "monster",
    "restsite": "rest_site", "rest_site": "rest_site", "rest-site": "rest_site",
    "shop": "shop", "merchant": "shop", "treasure": "treasure", "unknown": "unknown",
    "event": "event", "?": "unknown",
}
_MODES = {"standard": "standard", "daily": "daily", "custom": "custom", "0": "standard", "1": "daily", "2": "custom"}
_PREFIX_TABLE = {
    "CARD": "cards", "RELIC": "relics", "POTION": "potions", "CHARACTER": "characters",
    "ENCOUNTER": "encounters", "EVENT": "events", "MONSTER": "monsters", "ACT": "acts",
    "ENCHANTMENT": "enchantments", "MODIFIER": "modifiers", "POWER": "powers",
}


class SaveImportError(Exception):
    def __init__(self, code, **info):
        self.code = code
        self.info = {k: v for k, v in info.items()}
        super().__init__(code)


def _warn(ws, code, **info):
    item = {"code": code}
    item.update(info)
    if item not in ws:
        ws.append(item)


def as_int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.lstrip("-").isdigit():
            return int(s)
    return None


def id_str(v):
    """玩家 id（常常是超过 2^53 的 Steam64）一律变成十进制字符串，避免再经 JSON 进浏览器时被截断。"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def model_id(v):
    """游戏的 ModelId：多数时候是 'CARD.ALPHA' 字符串，旧档或个别字段可能是 {category, entry}。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, dict):
        if "entry" in v or "Entry" in v or "category" in v or "Category" in v:
            entry = v.get("entry", v.get("Entry"))
            cat = v.get("category", v.get("Category"))
            if entry is None and "id" in v:
                return model_id(v.get("id"))
            if entry is None:
                return None
            e = str(entry).strip()
            if not e:
                return None
            if cat:
                c = str(cat).strip().rstrip(".")
                if not c:
                    return e
                if e.upper().startswith(c.upper() + "."):
                    return e
                return f"{c}.{e}"
            return e
        if "id" in v:
            return model_id(v.get("id"))
        if "key" in v and isinstance(v.get("key"), str):
            key = v["key"].strip()
            return key or None
    return None


def norm_point(v):
    if v is None or isinstance(v, bool):
        return "unknown"
    if isinstance(v, (int, float)):
        return str(int(v))
    s = str(v).strip().lower().replace(" ", "").replace("-", "_")
    s = s.replace("__", "_")
    return _POINT.get(s, s or "unknown")


def _as_list(v):
    return v if isinstance(v, list) else []


def _prefix_short(mid, prefix):
    """没有点的短名（古遗物选项的 TextKey）补上前缀。已有前缀的不动。"""
    if not mid or not prefix:
        return mid, False
    if "." in mid:
        return mid, False
    return f"{prefix}.{mid}", True


# ---------------------------------------------------------------- 读文件（只读）
def decode_save(data, warnings):
    if data is None:
        raise SaveImportError("empty")
    if len(data) > MAX_IN:
        raise SaveImportError("too_big", mb=MAX_IN // (1024 * 1024))
    if not data.strip(b"\x00 \t\r\n"):
        raise SaveImportError("empty")
    for _ in range(2):
        if data[:2] != b"\x1f\x8b":
            break
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError):
            raise SaveImportError("json", err="gzip")
        if len(data) > MAX_OUT:
            raise SaveImportError("too_big", mb=MAX_OUT // (1024 * 1024))
        _warn(warnings, "gzip")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            text = data.decode("utf-16")
        except UnicodeError:
            raise SaveImportError("json", err="encoding")
        _warn(warnings, "utf16")
    else:
        if data.startswith(b"\xef\xbb\xbf"):
            _warn(warnings, "bom")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            raise SaveImportError("json", err="encoding")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise SaveImportError("json", err=f"line {e.lineno} col {e.colno}")
    if not isinstance(obj, dict):
        raise SaveImportError("not_run")
    return obj


def read_file(path):
    if not os.path.lexists(path):
        raise SaveImportError("not_found", path=path)
    if not os.path.isfile(path):
        raise SaveImportError("not_file", path=path)
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise SaveImportError("io", err=e.strerror or "io")
    if size > MAX_IN:
        raise SaveImportError("too_big", mb=MAX_IN // (1024 * 1024))
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as e:
        raise SaveImportError("io", err=e.strerror or "io")
    try:
        data = os.read(fd, MAX_IN + 1)
    except OSError as e:
        raise SaveImportError("io", err=e.strerror or "io")
    finally:
        os.close(fd)
    if len(data) > MAX_IN:
        raise SaveImportError("too_big", mb=MAX_IN // (1024 * 1024))
    return data


# ---------------------------------------------------------------- 字段
def _card(c):
    if isinstance(c, str) or not isinstance(c, dict):
        return {"id": model_id(c), "upgrade": None, "floor": None, "enchantment": None, "props": []}
    ench = c.get("enchantment")
    enchantment = None
    if isinstance(ench, dict):
        eid = ench.get("id") if "id" in ench else ench
        enchantment = {"id": model_id(eid), "amount": as_int(ench.get("amount"))}
    elif isinstance(ench, str) and ench.strip():
        enchantment = {"id": model_id(ench), "amount": None}
    props = []
    raw = c.get("props")
    if isinstance(raw, dict):
        for item in _as_list(raw.get("ints")):
            if isinstance(item, dict) and item.get("name") is not None:
                props.append({"name": str(item.get("name")), "value": as_int(item.get("value"))})
    return {
        "id": model_id(c.get("id")),
        "upgrade": as_int(c.get("current_upgrade_level")),
        "floor": as_int(c.get("floor_added_to_deck")),
        "enchantment": enchantment,
        "props": props,
    }


def _relic(r):
    if isinstance(r, str) or not isinstance(r, dict):
        return {"id": model_id(r), "floor": None}
    return {"id": model_id(r.get("id")), "floor": as_int(r.get("floor_added_to_deck"))}


def _potion(p):
    if isinstance(p, str) or not isinstance(p, dict):
        return {"id": model_id(p), "slot": None}
    return {"id": model_id(p.get("id")), "slot": as_int(p.get("slot_index"))}


def _picked(obj):
    if not isinstance(obj, dict):
        return False
    if "was_picked" in obj:
        return bool(obj.get("was_picked"))
    if "was_chosen" in obj:
        return bool(obj.get("was_chosen"))
    return False


def _card_choice(c):
    if not isinstance(c, dict):
        return None
    card = _card(c.get("card")) if c.get("card") is not None else _card(c.get("id"))
    card["picked"] = _picked(c)
    return card


def _model_choice(c, prefix=None):
    if isinstance(c, str):
        mid, inferred = _prefix_short(model_id(c), prefix)
        return {"id": mid, "picked": False, "inferred": inferred}
    if not isinstance(c, dict):
        return None
    raw = None
    for key in ("choice", "TextKey", "text_key", "textKey", "id"):
        if key in c and c.get(key) not in (None, ""):
            raw = c.get(key)
            break
    if raw is None and isinstance(c.get("title"), dict):
        key = c["title"].get("key") or ""
        raw = key.split(".")[0] if key else None
    mid = model_id(raw)
    mid, inferred = _prefix_short(mid, prefix)
    return {"id": mid, "picked": _picked(c), "inferred": inferred}


def _event_id(c):
    if isinstance(c, str):
        return model_id(c)
    if not isinstance(c, dict):
        return None
    for key in ("TextKey", "text_key", "choice", "id"):
        if c.get(key):
            return model_id(c.get(key))
    title = c.get("title")
    if isinstance(title, dict) and title.get("key"):
        return str(title.get("key")).split(".")[0] or None
    return None


def _id_list(raw):
    out = []
    for x in _as_list(raw):
        mid = model_id(x if not isinstance(x, dict) else x.get("id", x))
        if mid:
            out.append(mid)
    return out


def _player(p):
    if not isinstance(p, dict):
        return None
    pid = id_str(p.get("id")) if "id" in p else None
    if pid is None:
        pid = id_str(p.get("net_id"))
    character = model_id(p.get("character")) if p.get("character") is not None else None
    if not character:
        character = model_id(p.get("character_id"))
    return {
        "id": pid,
        "character": character,
        "deck": [_card(c) for c in _as_list(p.get("deck"))],
        "relics": [_relic(r) for r in _as_list(p.get("relics"))],
        "potions": [_potion(x) for x in _as_list(p.get("potions"))],
        "potion_slots": as_int(p.get("max_potion_slot_count")),
    }


def _stats(st):
    if not isinstance(st, dict):
        return None
    pid = id_str(st.get("player_id")) if "player_id" in st else id_str(st.get("id"))
    return {
        "id": pid,
        "hp": as_int(st.get("current_hp")) if "current_hp" in st else None,
        "max_hp": as_int(st.get("max_hp")) if "max_hp" in st else None,
        "gold": as_int(st.get("current_gold")) if "current_gold" in st else None,
        "card_choices": [c for c in (_card_choice(x) for x in _as_list(st.get("card_choices"))) if c and c.get("id")],
        "relic_choices": [c for c in (_model_choice(x) for x in _as_list(st.get("relic_choices"))) if c and c.get("id")],
        "ancient": [c for c in (_model_choice(x, "RELIC") for x in _as_list(st.get("ancient_choice"))) if c and c.get("id")],
        "cards_gained": [_card(c) for c in _as_list(st.get("cards_gained"))],
        "cards_removed": [_card(c) for c in _as_list(st.get("cards_removed"))],
        "upgraded": _id_list(st.get("upgraded_cards")),
        "bought_relics": _id_list(st.get("bought_relics")),
        "bought_cards": _id_list(st.get("bought_colorless")),
        "rest": [str(x) for x in _as_list(st.get("rest_site_choices")) if isinstance(x, (str, int)) and not isinstance(x, bool)],
        "events": [x for x in (_event_id(e) for e in _as_list(st.get("event_choices"))) if x],
    }


def _room(r):
    if isinstance(r, str):
        return {"type": None, "id": model_id(r), "monsters": [], "turns": None}
    if not isinstance(r, dict):
        return None
    monsters = _id_list(r.get("monster_ids"))
    return {
        "type": norm_point(r.get("room_type")) if r.get("room_type") else None,
        "id": model_id(r.get("model_id") if r.get("model_id") is not None else r.get("id")),
        "monsters": monsters,
        "turns": as_int(r.get("turns_taken")),
    }


def _coord(v):
    if isinstance(v, dict):
        col = None
        row = None
        for k in ("col", "x", "Col", "X"):
            if k in v:
                col = as_int(v.get(k))
                break
        for k in ("row", "y", "Row", "Y"):
            if k in v:
                row = as_int(v.get(k))
                break
        if col is None or row is None:
            inner = v.get("coord") or v.get("map_coord")
            if isinstance(inner, dict) and inner is not v:
                return _coord(inner)
            return None
        return {"col": col, "row": row}
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        col, row = as_int(v[0]), as_int(v[1])
        if col is None or row is None:
            return None
        return {"col": col, "row": row}
    return None


def _children(raw, src_row):
    out = []
    ints = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict) or (isinstance(item, (list, tuple)) and item and not isinstance(item[0], (int, float))):
            c = _coord(item)
            if c:
                out.append(c)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            c = _coord(item)
            if c:
                out.append(c)
        elif isinstance(item, int) and not isinstance(item, bool):
            ints.append(item)
    if ints and not out:
        for col in ints:
            out.append({"col": col, "row": src_row + 1})
    return out


def _point_type_of(v):
    for k in ("point_type", "map_point_type", "type", "PointType"):
        if k in v and not isinstance(v.get(k), (dict, list)):
            return norm_point(v.get(k))
    return None


def _as_map_point(v):
    if not isinstance(v, dict):
        return None
    coord = None
    if isinstance(v.get("coord"), (dict, list)):
        coord = _coord(v.get("coord"))
    elif isinstance(v.get("map_coord"), (dict, list)):
        coord = _coord(v.get("map_coord"))
    else:
        # 顶层 col/row，但别把 children 里的数字误当成坐标
        if any(k in v for k in ("col", "row", "x", "y", "Col", "Row")):
            coord = _coord({k: v.get(k) for k in ("col", "row", "x", "y", "Col", "Row", "X", "Y") if k in v})
    typ = _point_type_of(v)
    if coord is None or typ is None and "children" not in v and "point_type" not in v and "map_point_type" not in v and "type" not in v:
        if coord is None:
            return None
    if coord is None:
        return None
    kids = _children(v.get("children") if "children" in v else v.get("child_coords") or v.get("next"), coord["row"])
    return {"col": coord["col"], "row": coord["row"], "type": typ or "unknown", "children": kids, "visited": False}


def _from_grid(rows):
    points = []
    for r, row in enumerate(rows):
        if not isinstance(row, list):
            return None
        for c, cell in enumerate(row):
            if cell is None:
                continue
            if isinstance(cell, str):
                points.append({"col": c, "row": r, "type": norm_point(cell), "children": [], "visited": False})
                continue
            if not isinstance(cell, dict):
                continue
            typ = _point_type_of(cell)
            kids = _children(cell.get("children"), r)
            if not kids and isinstance(cell.get("next"), list):
                kids = _children(cell.get("next"), r)
            if typ is None and not kids:
                continue
            points.append({"col": c, "row": r, "type": typ or "unknown", "children": kids, "visited": False})
    return points


def _map_points(node, depth=0):
    if node is None or depth > 4:
        return None
    if isinstance(node, list):
        if not node:
            return []
        if all(isinstance(r, list) or r is None for r in node):
            return _from_grid([r if isinstance(r, list) else [] for r in node])
        pts = [_as_map_point(x) for x in node]
        pts = [p for p in pts if p]
        return pts or None
    if isinstance(node, dict):
        for key in ("points", "map_points", "nodes", "grid", "rows"):
            if key in node:
                got = _map_points(node[key], depth + 1)
                if got is not None:
                    return got
        values = [v for v in node.values() if isinstance(v, dict)]
        if len(values) >= 1 and len(values) == len(node):
            pts = [_as_map_point(v) for v in values]
            if pts and all(pts):
                return pts
        one = _as_map_point(node)
        if one and any(k in node for k in ("coord", "col", "point_type", "map_point_type")):
            return [one]
    return None


def _acts(raw, warnings):
    ids = []
    maps = []
    if not isinstance(raw, list):
        return ids, maps
    unknown = False
    for a in raw:
        if isinstance(a, str) or not isinstance(a, dict):
            ids.append(model_id(a))
            maps.append(None)
            continue
        # {category, entry} 这种 ModelId，不是幕对象
        if "entry" in a and "saved_map" not in a and "rooms" not in a and "id" not in a and "Id" not in a:
            ids.append(model_id(a))
            maps.append(None)
            continue
        mid = model_id(a.get("id")) if "id" in a else model_id(a.get("Id"))
        ids.append(mid)
        key = "saved_map" if "saved_map" in a else ("SavedMap" if "SavedMap" in a else None)
        if key is None or a.get(key) is None:
            maps.append(None)
            continue
        pts = _map_points(a.get(key))
        if pts is None:
            unknown = True
            maps.append(None)
        else:
            maps.append(pts)
    if unknown:
        _warn(warnings, "map_unknown")
    return ids, maps


def _detect_kind(obj):
    players = obj.get("players") if isinstance(obj.get("players"), list) else []
    p0 = players[0] if players and isinstance(players[0], dict) else {}
    if any(k in p0 for k in ("character_id", "net_id")) and "character" not in p0:
        return "live"
    if "character" in p0 and "character_id" not in p0 and "net_id" not in p0:
        return "history"
    if "win" in obj and isinstance(obj.get("seed"), str):
        return "history"
    rng = obj.get("rng")
    if isinstance(rng, dict) and isinstance(rng.get("seed"), str) and "map_point_history" in obj:
        return "live"
    if "win" in obj or "was_abandoned" in obj:
        return "history"
    if "current_act_index" in obj or "visited_map_coords" in obj or "win_time" in obj:
        return "live"
    return "history"


def _looks_like_run(obj):
    players = obj.get("players") if isinstance(obj.get("players"), list) else []
    has_player = any(isinstance(p, dict) and any(k in p for k in ("deck", "relics", "character", "character_id", "net_id")) for p in players)
    has_map = isinstance(obj.get("map_point_history"), list)
    return has_player or has_map


def _seed(obj, kind, warnings):
    top = obj.get("seed") if "seed" in obj else None
    rng = obj.get("rng") if isinstance(obj.get("rng"), dict) else {}
    rng_seed = rng.get("seed") if "seed" in rng else None
    top_s = top.strip() if isinstance(top, str) else None
    rng_s = rng_seed.strip() if isinstance(rng_seed, str) else None

    def numeric(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if kind == "live" and rng_s:
        return rng_s
    if top_s and not top_s.isdigit():
        return top_s
    if rng_s:
        _warn(warnings, "seed_from_rng")
        return rng_s
    if top_s:
        # 纯数字字符串不是游戏里那串种子
        _warn(warnings, "seed_numeric_only")
        return top_s
    if numeric(rng_seed) or numeric(top):
        _warn(warnings, "seed_numeric_only")
        n = rng_seed if numeric(rng_seed) else top
        return str(int(n))
    _warn(warnings, "seed_missing")
    return None


def _result(obj, kind):
    if obj.get("was_abandoned") is True:
        return "abandoned"
    if isinstance(obj.get("win"), bool):
        return "won" if obj["win"] else "lost"
    wt = as_int(obj.get("win_time")) if "win_time" in obj else None
    if wt is not None and wt > 0:
        return "won"
    if kind == "live":
        return "in_progress"
    return "unknown"


def _mode(v, warnings):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        s = str(int(v))
        if s not in _MODES:
            _warn(warnings, "game_mode_numeric", value=s)
            return s
        return _MODES[s]
    s = str(v).strip().lower()
    if not s:
        return None
    return _MODES.get(s, s)


def _platform(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return {0: "none", 1: "steam"}.get(int(v), str(int(v)))
    s = str(v).strip().lower()
    if s in ("steam",):
        return "steam"
    if s in ("none", "null"):
        return "none"
    return s or None


def _modifiers(raw):
    out = []
    for m in _as_list(raw):
        mid = model_id(m.get("id") if isinstance(m, dict) else m)
        if mid:
            out.append({"id": mid})
    return out


def _history(obj, warnings):
    mph = obj.get("map_point_history")
    if isinstance(mph, list) and mph and all(isinstance(x, dict) for x in mph):
        _warn(warnings, "flat_history")
        mph = [mph]
    if not isinstance(mph, list):
        mph = []
    return mph


def _attach_coords(route, coords, current_act, warnings):
    if not coords:
        return
    by_act = {}
    for i, step in enumerate(route):
        by_act.setdefault(step["act"], []).append(i)
    target = None
    if current_act is not None and current_act in by_act and len(by_act[current_act]) == len(coords):
        target = current_act
    elif len(by_act) == 1 and len(route) == len(coords):
        target = next(iter(by_act))
    else:
        matches = [a for a, idxs in by_act.items() if len(idxs) == len(coords)]
        if len(matches) == 1:
            target = matches[0]
    if target is None:
        _warn(warnings, "coords_unmatched")
        return
    for step_i, coord in zip(by_act[target], coords):
        route[step_i]["coord"] = coord
    if len(by_act) > 1:
        _warn(warnings, "coords_partial", act=target + 1)


def _mark_visited(maps, route):
    seen = {}
    for step in route:
        c = step.get("coord")
        if c:
            seen.setdefault(step["act"], set()).add((c["col"], c["row"]))
    for m in maps:
        have = seen.get(m["act"], set())
        for p in m["points"]:
            p["visited"] = (p["col"], p["row"]) in have


def _start_time(obj, warnings):
    if "start_time" not in obj:
        return None
    n = as_int(obj.get("start_time"))
    if n is None:
        return None
    if n > 10 ** 12:
        _warn(warnings, "time_ms")
        return n // 1000
    return n


def parse_obj(obj, filename=None, path=None):
    """把一份已解析的 JSON 对象收成视图。不是对局就抛 SaveImportError('not_run')。"""
    if not isinstance(obj, dict) or not _looks_like_run(obj):
        raise SaveImportError("not_run", name=filename or "")
    warnings = []
    kind = _detect_kind(obj)
    act_ids, act_maps = _acts(obj.get("acts"), warnings)
    mph = _history(obj, warnings)
    route = []
    floor = 0
    for ai, points in enumerate(mph):
        if not isinstance(points, list):
            _warn(warnings, "bad_act")
            continue
        act_id = act_ids[ai] if ai < len(act_ids) else None
        for pt in points:
            if not isinstance(pt, dict):
                _warn(warnings, "bad_act")
                continue
            floor += 1
            rooms = [r for r in (_room(x) for x in _as_list(pt.get("rooms"))) if r]
            players = [s for s in (_stats(x) for x in _as_list(pt.get("player_stats"))) if s]
            route.append({
                "act": ai,
                "act_id": act_id,
                "floor": floor,
                "type": norm_point(pt.get("map_point_type") or pt.get("point_type") or pt.get("type")),
                "coord": None,
                "rooms": rooms,
                "players": players,
            })
    coords = [c for c in (_coord(x) for x in _as_list(obj.get("visited_map_coords"))) if c]
    current_act = as_int(obj.get("current_act_index")) if "current_act_index" in obj else None
    _attach_coords(route, coords, current_act, warnings)
    maps = []
    for i, pts in enumerate(act_maps):
        if pts:
            maps.append({"act": i, "act_id": act_ids[i] if i < len(act_ids) else None, "points": pts})
    _mark_visited(maps, route)
    seed = _seed(obj, kind, warnings)
    killed = model_id(obj.get("killed_by_encounter")) or model_id(obj.get("killed_by_event"))
    run_time = obj.get("run_time")
    if isinstance(run_time, float) and run_time.is_integer():
        run_time = int(run_time)
    elif not isinstance(run_time, (int, float)) or isinstance(run_time, bool):
        run_time = None
    players = [p for p in (_player(p) for p in _as_list(obj.get("players"))) if p]
    return {
        "source": {"filename": filename, "path": path},
        "kind": kind,
        "schema_version": as_int(obj.get("schema_version")),
        "seed": seed,
        "seed_canonical": canonicalize(seed) if seed else None,
        "ascension": as_int(obj.get("ascension")),
        "game_mode": _mode(obj.get("game_mode"), warnings),
        "result": _result(obj, kind),
        "platform": _platform(obj.get("platform_type")),
        "start_time": _start_time(obj, warnings),
        "run_time": run_time,
        "build_id": obj.get("build_id") if isinstance(obj.get("build_id"), str) else None,
        "killed_by": killed,
        "acts": act_ids,
        "modifiers": _modifiers(obj.get("modifiers")),
        "players": players,
        "route": route,
        "maps": maps,
        "warnings": warnings,
    }


def parse_bytes(data, filename="upload"):
    warnings = []
    obj = decode_save(data, warnings)
    try:
        run = parse_obj(obj, filename=filename, path=None)
    except SaveImportError as e:
        if e.code == "not_run":
            raise SaveImportError("not_run", name=filename or "")
        raise
    for w in warnings:
        if w not in run["warnings"]:
            run["warnings"].insert(0, w)
    return run


def parse_path(path):
    data = read_file(path)
    filename = os.path.basename(path)
    warnings = []
    obj = decode_save(data, warnings)
    try:
        run = parse_obj(obj, filename=filename, path=os.path.abspath(path))
    except SaveImportError as e:
        if e.code == "not_run":
            raise SaveImportError("not_run", name=filename)
        raise
    for w in warnings:
        if w not in run["warnings"]:
            run["warnings"].insert(0, w)
    return run


def summarize(run):
    return {
        "path": (run.get("source") or {}).get("path"),
        "filename": (run.get("source") or {}).get("filename"),
        "kind": run.get("kind"),
        "seed": run.get("seed"),
        "seed_canonical": run.get("seed_canonical"),
        "result": run.get("result"),
        "ascension": run.get("ascension"),
        "floors": len(run.get("route") or []),
        "start_time": run.get("start_time"),
        "schema_version": run.get("schema_version"),
        "players": [{"id": p.get("id"), "character": p.get("character")} for p in run.get("players") or []],
        "error": None,
    }


def _interesting(name):
    low = name.lower()
    if low in _SKIP_NAMES or low.startswith("progress.") or low.startswith("settings.") or low.startswith("prefs.") or low.startswith("profile."):
        return False
    if low.endswith(".run") or low.endswith(".run.backup"):
        return True
    if "current_run" in low and (low.endswith(".save") or ".save.backup" in low or low.endswith(".corrupt")):
        return True
    return False


def scan_dir(path):
    if not os.path.isdir(path):
        raise SaveImportError("not_file", path=path)
    root = os.path.abspath(path)
    warnings = []
    found = []
    seen = 0
    capped = False
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in ("logs", "node_modules", ".git")]
        for fn in filenames:
            seen += 1
            if seen > MAX_WALK or len(found) >= MAX_FILES:
                capped = True
                break
            if not _interesting(fn):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                run = parse_path(fp)
                found.append(summarize(run))
            except SaveImportError as e:
                found.append({
                    "path": os.path.abspath(fp), "filename": fn, "kind": None, "seed": None,
                    "seed_canonical": None, "result": None, "ascension": None, "floors": None,
                    "start_time": None, "schema_version": None, "players": [],
                    "error": e.code, "error_info": e.info,
                })
        if capped:
            break
    if capped:
        _warn(warnings, "scan_cap", n=MAX_FILES)
    found.sort(key=lambda r: (r.get("start_time") or 0, r.get("filename") or ""), reverse=True)
    return {"type": "index", "root": root, "runs": found, "warnings": warnings}


def open_path(path):
    if not os.path.lexists(path):
        raise SaveImportError("not_found", path=path)
    if os.path.isdir(path):
        return scan_dir(path)
    if not os.path.isfile(path):
        raise SaveImportError("not_file", path=path)
    return {"type": "run", "run": parse_path(path)}


def resolve_player(run, which):
    players = run.get("players") or []
    if which is None or which == "":
        return 0 if players else None
    s = str(which)
    for i, p in enumerate(players):
        if p.get("id") == s:
            return i
    if s.isdigit():
        i = int(s)
        if 0 <= i < len(players):
            return i
    raise SaveImportError("bad_player", player=s)


def apply_names(node, lookup):
    """给带点的 ModelId 填上 lookup(id) 返回的名字。lookup 失败就保持没有 name。"""
    if lookup is None:
        return node
    if isinstance(node, dict):
        mid = node.get("id")
        if isinstance(mid, str) and "." in mid and "name" not in node:
            try:
                n = lookup(mid)
            except Exception:
                n = None
            if n:
                node["name"] = n
        ch = node.get("character")
        if isinstance(ch, str) and "." in ch and "character_name" not in node:
            try:
                n = lookup(ch)
            except Exception:
                n = None
            if n:
                node["character_name"] = n
        for v in node.values():
            apply_names(v, lookup)
    elif isinstance(node, list):
        for v in node:
            apply_names(v, lookup)
    return node


def lookup_tables(model):
    """'CARD.ALPHA' → 可能的 (本地化表, 键)。表名是我们用来查玩家自己安装的，不是游戏文本。"""
    if not model or not isinstance(model, str) or "." not in model:
        return []
    prefix, _, rest = model.partition(".")
    table = _PREFIX_TABLE.get(prefix.upper())
    if not table or not rest:
        return []
    short = rest[:-6] if rest.endswith(".title") else rest
    keys = []
    for k in (short, model, rest):
        if k and k not in keys:
            keys.append(k)
    return [(table, k) for k in keys]


# ---------------------------------------------------------------- 文本（命令行）
def _ids(items):
    out = []
    for it in items or []:
        if isinstance(it, dict):
            mark = ""
            if "picked" in it:
                mark = "*" if it.get("picked") else "-"
            label = it.get("id") or "?"
            if mark:
                label = mark + label
            out.append(label)
        elif it:
            out.append(str(it))
    return out


def format_text(run, player=0):
    players = run.get("players") or []
    who = players[player] if players and 0 <= player < len(players) else None
    lines = [
        f"kind: {run.get('kind')}",
        f"file: {(run.get('source') or {}).get('filename') or '-'}",
        f"seed: {run.get('seed') or '-'}",
    ]
    if run.get("seed_canonical") and run.get("seed_canonical") != run.get("seed"):
        lines.append(f"seed_canonical: {run.get('seed_canonical')}")
    lines.append(f"result: {run.get('result')}")
    lines.append(f"ascension: {run.get('ascension')}")
    if run.get("killed_by"):
        lines.append(f"killed_by: {run.get('killed_by')}")
    if who:
        lines.append(f"character: {who.get('character') or '-'}")
        lines.append(f"player: {who.get('id') or '-'}")
    if len(players) > 1:
        lines.append(f"players: {len(players)} (showing {player})")
    lines.append("route:")
    pid = who.get("id") if who else None
    if not run.get("route"):
        lines.append("  -")
    for step in run.get("route") or []:
        rooms = ", ".join(r.get("id") or "-" for r in step.get("rooms") or []) or "-"
        coord = ""
        if step.get("coord"):
            coord = f"  @{step['coord']['col']},{step['coord']['row']}"
        act_id = step.get("act_id") or ""
        lines.append(f"  {step['floor']}  act {step['act'] + 1} {act_id}  {step['type']}  {rooms}{coord}")
    lines.append("picks:")
    any_pick = False
    for step in run.get("route") or []:
        st = None
        for s in step.get("players") or []:
            if pid is not None and s.get("id") == pid:
                st = s
                break
        # 这一层没有该玩家的记录就跳过，不要改成显示别人的选牌
        if st is None and pid is None and step.get("players"):
            st = step["players"][0]
        if not st:
            continue
        bits = []
        cards = _ids(st.get("card_choices"))
        relics = _ids(st.get("relic_choices"))
        ancient = _ids(st.get("ancient"))
        if cards:
            bits.append("cards " + " ".join(cards))
        if relics:
            bits.append("relics " + " ".join(relics))
        if ancient:
            bits.append("ancient " + " ".join(ancient))
        if bits:
            any_pick = True
            lines.append(f"  floor {step['floor']}: " + "; ".join(bits))
    if not any_pick:
        lines.append("  -")
    lines.append("relics:")
    rels = (who or {}).get("relics") or []
    if not rels:
        lines.append("  -")
    for r in rels:
        floor = "-" if r.get("floor") is None else r.get("floor")
        lines.append(f"  {r.get('id')}  floor {floor}")
    if run.get("warnings"):
        lines.append("warnings:")
        for w in run["warnings"]:
            extra = " ".join(f"{k}={v}" for k, v in w.items() if k != "code")
            lines.append(f"  {w.get('code')}" + (f" {extra}" if extra else ""))
    return "\n".join(lines) + "\n"


def format_index(index):
    lines = [f"folder: {index.get('root')}", f"runs: {len(index.get('runs') or [])}"]
    for r in index.get("runs") or []:
        if r.get("error"):
            lines.append(f"  {r.get('filename')}  error {r.get('error')}")
            continue
        who = (r.get("players") or [{}])[0].get("character") or "-"
        lines.append(f"  {r.get('filename')}  seed {r.get('seed') or '-'}  {who}  {r.get('result')}  floors {r.get('floors')}")
    for w in index.get("warnings") or []:
        lines.append(f"warning: {w.get('code')}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 本机可能的存档目录（只列目录，不读内容以外的用途：发现）
def _existing(paths):
    out, seen = [], set()
    for p in paths:
        if not p:
            continue
        ap = os.path.abspath(os.path.expanduser(p))
        if ap in seen or not os.path.isdir(ap):
            continue
        seen.add(ap)
        out.append(ap)
    return out


def _label(path):
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if parts and parts[-1].lower() == "saves":
        parts = parts[:-1]
    return "/".join(parts[-3:])


def discover():
    """找到本机上像是存档目录的文件夹。读目录名，不修改。没有就返回空列表。"""
    home = os.path.expanduser("~")
    roots = []
    env = os.environ.get("DECKBENCH_STS2_SAVES")
    if env:
        roots.append(env)
    if os.name == "nt":
        app = os.environ.get("APPDATA")
        if app:
            roots.append(os.path.join(app, "SlayTheSpire2"))
        roots.append(os.path.join(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)", "Steam", "userdata"))
    else:
        roots.extend([
            os.path.join(home, ".local", "share", "SlayTheSpire2"),
            os.path.join(home, "Library", "Application Support", "SlayTheSpire2"),
            os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "SlayTheSpire2"),
            os.path.join(home, ".steam", "steam", "userdata"),
            os.path.join(home, ".steam", "root", "userdata"),
            os.path.join(home, ".local", "share", "Steam", "userdata"),
            os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam", "userdata"),
        ])
    try:
        from sts2sim.gamedata import _steam_roots
        for r in _steam_roots():
            roots.append(os.path.join(r, "userdata"))
    except Exception:
        pass
    patterns = [
        os.path.join("steam", "*", "profile*", "saves"),
        os.path.join("steam", "*", "modded", "profile*", "saves"),
        os.path.join("*", "profile*", "saves"),
        os.path.join("*", "modded", "profile*", "saves"),
        os.path.join("*", STEAM_APP, "remote", "profile*", "saves"),
        os.path.join("*", STEAM_APP, "remote", "modded", "profile*", "saves"),
        os.path.join(STEAM_APP, "remote", "profile*", "saves"),
        os.path.join(STEAM_APP, "remote", "modded", "profile*", "saves"),
    ]
    found, seen = [], set()

    def add(p):
        ap = os.path.abspath(p)
        if ap in seen or not os.path.isdir(ap):
            return
        seen.add(ap)
        found.append({"path": ap, "label": _label(ap)})

    if env and os.path.isdir(os.path.expanduser(env)):
        ep = os.path.abspath(os.path.expanduser(env))
        try:
            names = set(os.listdir(ep))
        except OSError:
            names = set()
        if "history" in names or "current_run.save" in names or "current_run_mp.save" in names or any(n.endswith(".run") for n in names):
            add(ep)
    import glob as _glob
    for root in _existing(roots):
        for pat in patterns:
            for p in _glob.glob(os.path.join(root, pat)):
                add(p)
                if len(found) >= 24:
                    return found
    return found


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m sts2sim.saveimport",
        description="Read a Slay the Spire 2 save or run history (read-only) and print seed, route, card picks and relics.",
    )
    p.add_argument("path", help="a .run / current_run.save file, or a folder of them")
    p.add_argument("--json", action="store_true", help="print the parsed view as JSON")
    p.add_argument("--player", default=None, help="player id or 0-based index (default: first)")
    args = p.parse_args(argv)
    try:
        result = open_path(args.path)
    except SaveImportError as e:
        extra = " ".join(f"{k}={v}" for k, v in e.info.items())
        sys.stderr.write(f"error: {e.code}" + (f" {extra}" if extra else "") + "\n")
        return 1
    if result.get("type") == "index":
        if args.json:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(format_index(result))
        return 0
    run = result["run"]
    try:
        idx = resolve_player(run, args.player)
    except SaveImportError as e:
        extra = " ".join(f"{k}={v}" for k, v in e.info.items())
        sys.stderr.write(f"error: {e.code}" + (f" {extra}" if extra else "") + "\n")
        return 1
    if args.json:
        if args.player is not None and idx is not None:
            run = dict(run, focus=idx)
        json.dump(run, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(format_text(run, 0 if idx is None else idx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
