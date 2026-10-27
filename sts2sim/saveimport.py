"""只读解析《杀戮尖塔 2》的对局记录 / 进行中存档。

不写盘、不解密、不携带任何游戏文件。`summarize()` / `summary_json()` 给外部代理一份短 JSON，同样不写盘。
`batch_summary()` 把一个目录里每条能读的 history 记录收成稳定的短行（种子、进阶、角色、层数、有胜负才写结果）。
格式结论和已知缺口见 docs/SAVE_FORMAT.md。
公开的对局记录（history/<unix 秒>.run）和进行中存档（current_run.save /
current_run_mp.save）都是 UTF-8 JSON，但字段形状不一样，而且会随 schema_version 变。
这里按「认得出的键」取值（snake_case / camelCase / PascalCase 都认），认不出的键留着不报错。

Read-only parser for finished run history and in-progress saves. Never writes, never
decrypts, ships no game files. summarize() / summary_json() are the short JSON
an external agent can read. batch_summary() is the stable per-run list for a
history folder (seed, ascension, character, floors, result when the run ended).
See docs/SAVE_FORMAT.md.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import zlib

MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 200
# 给外部代理的短摘要上限。牌优先留升级 / 附魔 / 第 0 层之后拿到的；没有这类牌时才列牌组。
SUMMARY_CARD_CAP = 40
SUMMARY_RELIC_CAP = 40
SUMMARY_PICK_CAP = 20

# 模拟器角色类名。只在记录里的模型 ID 能对上时填，用来跳到种子预览。
_SIM_CHAR = {
    "IRONCLAD": "Ironclad",
    "SILENT": "Silent",
    "DEFECT": "Defect",
    "NECROBINDER": "Necrobinder",
    "REGENT": "Regent",
    "THEIRONCLAD": "Ironclad",
    "THESILENT": "Silent",
    "THEDEFECT": "Defect",
}
_NOT_RUN = {"progress.save", "prefs.save", "settings.save", "profile.save"}
_NONE = {"", "none", "none.none", "null"}


class SaveImportError(Exception):
    def __init__(self, code, **params):
        self.code = code
        self.params = params
        super().__init__(code)


def _norm_key(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _idx(d):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.setdefault(_norm_key(k), v)
    return out


def _get(d, *names, default=None):
    if not isinstance(d, dict):
        return default
    idx = _idx(d)
    for n in names:
        hit = _norm_key(n)
        if hit in idx:
            return idx[hit]
    return default


def _as_id(v):
    """模型 ID：字符串 "CARD.X"，或 {id}/{entry}，或 {category, entry}。NONE.NONE → None。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        s = v.strip()
        return None if s.lower() in _NONE else s
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(int(v)) if float(v).is_integer() else str(v)
    if isinstance(v, dict):
        for k in ("id", "entry", "model_id", "modelId", "name"):
            if _get(v, k) is not None and not isinstance(_get(v, k), (dict, list)):
                return _as_id(_get(v, k))
        cat = _get(v, "category")
        ent = _get(v, "entry")
        if isinstance(ent, str) and ent.strip():
            if isinstance(cat, str) and cat.strip() and "." not in ent:
                return f"{cat}.{ent}"
            return _as_id(ent)
    return None


def _sim_character(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    if raw in ("Ironclad", "Silent", "Defect", "Necrobinder", "Regent"):
        return raw
    entry = re.sub(r"[^A-Z0-9]", "", raw.split(".")[-1].upper())
    return _SIM_CHAR.get(entry)


def _upgraded(d):
    if not isinstance(d, dict):
        return False
    if _get(d, "is_upgraded", "upgraded") is True:
        return True
    for k in ("current_upgrade", "upgrade_level", "upgrade_count", "times_upgraded"):
        n = _get(d, k)
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return True
        if isinstance(n, str) and n.strip().isdigit() and int(n) > 0:
            return True
    return False


def _enchant(d):
    if not isinstance(d, dict):
        return None
    raw = _get(d, "enchantment")
    if not isinstance(raw, dict):
        return None
    eid = _as_id(_get(raw, "id"))
    if not eid:
        return None
    amount = _get(raw, "amount")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = None
    return {"id": eid, "amount": amount}


def _floor(d):
    if not isinstance(d, dict):
        return None
    for k in ("floor_added_to_deck", "floor_added", "floor"):
        n = _get(d, k)
        if isinstance(n, bool):
            continue
        if isinstance(n, (int, float)):
            return int(n)
        if isinstance(n, str) and n.strip().isdigit():
            return int(n.strip())
    return None


def _card(raw):
    if isinstance(raw, str):
        eid = _as_id(raw)
        return None if not eid else {"id": eid, "floor": None, "upgraded": False, "enchantment": None}
    if not isinstance(raw, dict):
        return None
    eid = _as_id(_get(raw, "id", "card", "model_id"))
    if not eid:
        return None
    return {"id": eid, "floor": _floor(raw), "upgraded": _upgraded(raw), "enchantment": _enchant(raw)}


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return False


def _int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.lstrip("-").isdigit():
            return int(s)
    return None


def _players(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            continue
        character = _as_id(_get(p, "character", "character_id"))
        pid = _int(_get(p, "id", "net_id", "player_id"))
        if pid is None:
            pid = i + 1
        deck = []
        for c in _get(p, "deck") or []:
            card = _card(c)
            if card:
                deck.append(card)
        relics = []
        for r in _get(p, "relics") or []:
            if isinstance(r, str):
                eid = _as_id(r)
                if eid:
                    relics.append({"id": eid, "floor": None})
            elif isinstance(r, dict):
                eid = _as_id(_get(r, "id", "relic", "model_id"))
                if eid:
                    relics.append({"id": eid, "floor": _floor(r)})
        potions = []
        for pot in _get(p, "potions") or []:
            if isinstance(pot, str):
                eid = _as_id(pot)
                if eid:
                    potions.append({"id": eid, "slot": None})
            elif isinstance(pot, dict):
                eid = _as_id(_get(pot, "id", "potion"))
                if eid:
                    potions.append({"id": eid, "slot": _int(_get(pot, "slot_index", "slot"))})
        out.append({
            "id": pid,
            "character": character,
            "sim_character": _sim_character(character or ""),
            "deck": deck,
            "relics": relics,
            "potions": potions,
            "max_potion_slots": _int(_get(p, "max_potion_slot_count")),
            "current_hp": _int(_get(p, "current_hp")),
            "max_hp": _int(_get(p, "max_hp")),
            "gold": _int(_get(p, "gold")),
        })
    return out


def _point_type(raw):
    eid = _as_id(raw)
    if not eid:
        return None
    return eid.split(".")[-1]


def _room(raw):
    if not isinstance(raw, dict):
        return None
    return {
        "model_id": _as_id(_get(raw, "model_id")),
        "room_type": _point_type(_get(raw, "room_type")),
        "monster_ids": [x for x in (_as_id(m) for m in (_get(raw, "monster_ids") or [])) if x],
        "turns_taken": _int(_get(raw, "turns_taken")),
    }


def _choices(raw, id_keys):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, str):
            eid = _as_id(item)
            if eid:
                out.append({"id": eid, "was_picked": False})
            continue
        if not isinstance(item, dict):
            continue
        picked = _bool(_get(item, "was_picked", "picked"))
        inner = None
        for k in id_keys:
            inner = _get(item, k)
            if inner is not None:
                break
        if isinstance(inner, dict):
            card = _card(inner)
            if card:
                card["was_picked"] = picked
                out.append(card)
                continue
        eid = _as_id(inner if inner is not None else _get(item, "id"))
        if eid:
            out.append({"id": eid, "was_picked": picked, "floor": _floor(item), "upgraded": _upgraded(item)})
    return out


def _route(mph, acts):
    """map_point_history：外层是幕，内层是这一幕走过的点。也接受扁平的一层列表（旧档/残缺档）。"""
    if not isinstance(mph, list):
        return []
    nested = any(isinstance(x, list) for x in mph)
    groups = mph if nested else [mph]
    floors = []
    n = 0
    for ai, group in enumerate(groups):
        if not isinstance(group, list):
            continue
        act_id = acts[ai]["id"] if ai < len(acts) else None
        for pt in group:
            if not isinstance(pt, dict):
                continue
            n += 1
            stats = []
            picks = []
            potions = []
            relic_picks = []
            for ps in _get(pt, "player_stats") or []:
                if not isinstance(ps, dict):
                    continue
                pid = _int(_get(ps, "player_id"))
                stats.append({
                    "player_id": pid,
                    "current_hp": _int(_get(ps, "current_hp")),
                    "max_hp": _int(_get(ps, "max_hp")),
                    "gold": _int(_get(ps, "current_gold")),
                    "damage_taken": _int(_get(ps, "damage_taken")),
                })
                cards = _choices(_get(ps, "card_choices"), ("card", "id"))
                if cards:
                    picks.append({"player_id": pid, "cards": cards})
                pots = _choices(_get(ps, "potion_choices"), ("choice", "potion", "id"))
                if pots:
                    potions.append({"player_id": pid, "potions": pots})
                rels = _choices(_get(ps, "relic_choices"), ("relic", "choice", "id"))
                if rels:
                    relic_picks.append({"player_id": pid, "relics": rels})
            floors.append({
                "floor": n,
                "act_index": ai,
                "act": act_id,
                "index_in_act": sum(1 for f in floors if f["act_index"] == ai) + 1,
                "type": _point_type(_get(pt, "map_point_type", "point_type")),
                "rooms": [r for r in (_room(x) for x in (_get(pt, "rooms") or [])) if r],
                "stats": stats,
                "picks": picks,
                "potion_picks": potions,
                "relic_picks": relic_picks,
            })
    return floors


def _parse_saved_map(raw):
    """进行中存档里 acts[].saved_map 的尽力解析。对不上就返回 None，调用方记一条警告。

    认这些形状（键名大小写不敏感）：
      {points: [{coord:{col,row}, point_type, children:[{col,row}]}], boss?: {...}}
      {rows: [[{col,row,type}]]}   （已经是我们预览用的形状）
    """
    if not isinstance(raw, dict):
        return None
    if isinstance(_get(raw, "rows"), list) and isinstance(_get(raw, "cols"), (int, float)):
        return raw
    points = _get(raw, "points", "map_points", "nodes")
    if not isinstance(points, list) or not points:
        return None
    nodes = []
    boss = None
    for p in points:
        if not isinstance(p, dict):
            continue
        coord = _get(p, "coord") if isinstance(_get(p, "coord"), dict) else p
        col, row = _int(_get(coord, "col")), _int(_get(coord, "row"))
        if col is None or row is None:
            continue
        typ = _point_type(_get(p, "point_type", "map_point_type", "type")) or "Unassigned"
        children = []
        for c in _get(p, "children") or []:
            if isinstance(c, dict):
                cc = _get(c, "coord") if isinstance(_get(c, "coord"), dict) else c
                ccol, crow = _int(_get(cc, "col")), _int(_get(cc, "row"))
                if ccol is not None and crow is not None:
                    children.append([ccol, crow])
        node = {"col": col, "row": row, "type": typ, "children": children}
        if typ == "Boss":
            boss = {"col": col, "row": row}
        else:
            nodes.append(node)
    if not nodes and boss is None:
        return None
    by_row = {}
    for n in nodes:
        by_row.setdefault(n["row"], []).append(n)
    rows = [sorted(by_row[r], key=lambda n: n["col"]) for r in sorted(by_row)]
    cols = 1 + max((n["col"] for n in nodes), default=0)
    if boss:
        cols = max(cols, boss["col"] + 1)
    return {"rows": rows, "cols": cols, "boss": boss}


def _acts(raw, warnings):
    """返回 (acts, saw_obj, saw_str)。对象形态的 acts 是否算异常由调用方按文件种类决定。"""
    if raw is None:
        return [], False, False
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return [], False, False
    out = []
    saw_obj = saw_str = False
    for i, a in enumerate(raw):
        if isinstance(a, str):
            saw_str = True
            out.append({"index": i, "id": _as_id(a) or a, "map": None})
        elif isinstance(a, dict):
            saw_obj = True
            mid = _as_id(_get(a, "id")) or ""
            sm = _get(a, "saved_map")
            parsed = _parse_saved_map(sm) if sm is not None else None
            if sm not in (None, {}, []) and parsed is None:
                warnings.append({"code": "mapUnparsed", "act": mid or str(i)})
            out.append({"index": i, "id": mid, "map": parsed})
    if saw_obj and saw_str:
        warnings.append({"code": "actsMixed"})
    return out, saw_obj, saw_str


def _coords(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        col, row = _int(_get(c, "col")), _int(_get(c, "row"))
        if col is None or row is None:
            coord = _get(c, "coord")
            if isinstance(coord, dict):
                col, row = _int(_get(coord, "col")), _int(_get(coord, "row"))
        if col is not None and row is not None:
            out.append({"col": col, "row": row})
    return out


def _classify(obj):
    keys = {_norm_key(k) for k in obj}
    players = _get(obj, "players")
    live_player = hist_player = False
    if isinstance(players, list) and players and isinstance(players[0], dict):
        pkeys = {_norm_key(k) for k in players[0]}
        live_player = "characterid" in pkeys or "netid" in pkeys
        hist_player = "character" in pkeys and "characterid" not in pkeys
    live_markers = bool(keys & {"prefinishedroom", "currentactindex", "visitedmapcoords", "rng", "sharedrelicgrabbag"})
    if live_markers or live_player:
        return "live_save"
    if "mappointhistory" in keys or hist_player or ("seed" in keys and "players" in keys):
        return "run_history"
    prog = keys & {"epochs", "characterunlocks", "cardsunlocked", "discoveredcards", "encounterstats", "cardstats"}
    if prog and "mappointhistory" not in keys:
        raise SaveImportError("not_a_run")
    raise SaveImportError("unknown_shape")


def _result(kind, obj):
    has_win = _norm_key("win") in {_norm_key(k) for k in obj}
    if kind == "live_save" and not has_win:
        return "in_progress"
    if _bool(_get(obj, "was_abandoned")) and not _bool(_get(obj, "win")):
        return "abandoned"
    if _bool(_get(obj, "win")):
        return "won"
    if has_win:
        return "lost"
    return "in_progress"


def normalize(obj, *, filename=None, path=None):
    """一个 JSON 对象 → 展示用的对局。认不出就抛 SaveImportError。"""
    if isinstance(obj, str):
        obj = json.loads(obj)
    if not isinstance(obj, dict):
        raise SaveImportError("not_object")
    base = os.path.basename(filename or path or "").lower()
    for suf in (".backup", ".bak"):
        if base.endswith(suf):
            base = base[: -len(suf)]
    if base in _NOT_RUN and _norm_key("map_point_history") not in {_norm_key(k) for k in obj}:
        raise SaveImportError("not_a_run")
    kind = _classify(obj)
    warnings = []
    if filename and filename.endswith(".backup"):
        warnings.append({"code": "backup"})
    if kind == "live_save":
        warnings.append({"code": "liveInProgress"})
    acts, saw_obj, _saw_str = _acts(_get(obj, "acts"), warnings)
    if saw_obj and kind == "run_history":
        warnings.append({"code": "actsObjects"})
    seed = _get(obj, "seed")
    seed_source = "seed"
    if not isinstance(seed, str) or not seed.strip():
        rng = _get(obj, "rng")
        rng_seed = _get(rng, "seed") if isinstance(rng, dict) else None
        if isinstance(rng_seed, str) and rng_seed.strip():
            seed = rng_seed.strip()
            seed_source = "rng.seed"
            warnings.append({"code": "seedFromRng"})
        else:
            seed = None
            warnings.append({"code": "seedMissing"})
    else:
        seed = seed.strip()
    players = _players(_get(obj, "players"))
    route = _route(_get(obj, "map_point_history"), acts)
    if kind == "run_history":
        warnings.append({"code": "noRouteColumn"})
    coords = _coords(_get(obj, "visited_map_coords"))
    modifiers = []
    for m in _get(obj, "modifiers") or []:
        if isinstance(m, str):
            eid = _as_id(m)
            if eid:
                modifiers.append({"id": eid})
        elif isinstance(m, dict):
            eid = _as_id(_get(m, "id"))
            if eid:
                modifiers.append({"id": eid})
    sim = next((p["sim_character"] for p in players if p.get("sim_character")), None)
    return {
        "v": 1,
        "kind": kind,
        "filename": filename,
        "path": path,
        "schema_version": _int(_get(obj, "schema_version")),
        "seed": seed,
        "seed_source": seed_source if seed else None,
        "ascension": _int(_get(obj, "ascension", "ascension_level")) or 0,
        "game_mode": _as_id(_get(obj, "game_mode")) or (None if _get(obj, "game_mode") is None else str(_get(obj, "game_mode"))),
        "platform_type": _as_id(_get(obj, "platform_type")),
        "build_id": _get(obj, "build_id") if isinstance(_get(obj, "build_id"), str) else None,
        "start_time": _int(_get(obj, "start_time")),
        "run_time": _int(_get(obj, "run_time")),
        "result": _result(kind, obj),
        "win": _bool(_get(obj, "win")) if _get(obj, "win") is not None else None,
        "was_abandoned": _bool(_get(obj, "was_abandoned")) if _get(obj, "was_abandoned") is not None else None,
        "killed_by_encounter": _as_id(_get(obj, "killed_by_encounter")),
        "killed_by_event": _as_id(_get(obj, "killed_by_event")),
        "acts": acts,
        "modifiers": modifiers,
        "players": players,
        "sim_character": sim,
        "route": route,
        "visited_map_coords": coords,
        "current_act_index": _int(_get(obj, "current_act_index")),
        "warnings": warnings,
    }


def _decode(data):
    """bytes → (text, warnings)。认 gzip、UTF-16 BOM、UTF-8 BOM。不是文本就 not_json。"""
    warnings = []
    if data.startswith(b"\x1f\x8b"):
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as e:
            # 截断的 gzip 头会抛 EOFError，坏的 deflate 流会抛 zlib.error。都不是能读的存档。
            raise SaveImportError("not_json", detail=str(e)) from e
        warnings.append({"code": "gzip"})
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            return data.decode("utf-16"), warnings + [{"code": "utf16"}]
        except UnicodeError as e:
            raise SaveImportError("decode", detail=str(e)) from e
    if data.startswith(b"\xef\xbb\xbf"):
        warnings.append({"code": "bom"})
        data = data[3:]
    try:
        return data.decode("utf-8"), warnings
    except UnicodeError as e:
        raise SaveImportError("decode", detail=str(e)) from e


def parse_bytes(data, *, filename=None, path=None):
    if not data or not data.strip():
        raise SaveImportError("not_json")
    if len(data) > MAX_BYTES:
        raise SaveImportError("too_big")
    # 明显的二进制（大量 NUL）不要硬解成乱码
    head = data[:64]
    if b"\x00" in head and not data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x1f\x8b")):
        raise SaveImportError("not_json")
    text, warnings = _decode(data)
    text_stripped = text.lstrip("\ufeff \t\r\n")
    if not text_stripped or text_stripped[0] not in '{["':
        raise SaveImportError("not_json")
    try:
        obj = json.loads(text_stripped)
    except json.JSONDecodeError as e:
        raise SaveImportError("not_json", detail=e.msg) from e
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError as e:
            raise SaveImportError("not_json", detail=e.msg) from e
        warnings.append({"code": "doubleEncoded"})
    run = normalize(obj, filename=filename, path=path)
    run["warnings"] = warnings + run["warnings"]
    return run


def parse_path(path):
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise SaveImportError("not_found", path=path)
    try:
        with open(path, "rb") as f:
            data = f.read(MAX_BYTES + 1)
    except OSError as e:
        raise SaveImportError("not_found", path=path, detail=str(e)) from e
    return parse_bytes(data, filename=os.path.basename(path), path=path)


def _history_dir(path):
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.basename(path).lower() == "history" and os.path.isdir(path):
        return path
    nested = os.path.join(path, "history")
    if os.path.isdir(nested):
        return nested
    saves = os.path.join(path, "saves")
    if os.path.isdir(os.path.join(saves, "history")):
        return os.path.join(saves, "history")
    return None


def _save_dir(path):
    """用户指向 profile、saves 或 history 时，返回含 current_run / history 的 saves 目录。"""
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.basename(path).lower() == "history":
        parent = os.path.dirname(path)
        return parent if os.path.isdir(parent) else path
    if os.path.isdir(os.path.join(path, "saves")):
        return os.path.join(path, "saves")
    return path


def _list_run_files(directory):
    """只挑对局文件，不读 progress/prefs。同名 .run 存在时跳过 .backup。"""
    directory = _save_dir(directory)
    found = []
    hist = _history_dir(directory)
    # 标准布局是 saves/history/*.run。也接受用户把 .run 直接放在一个文件夹里。
    loose = hist is None
    hist = hist if hist and os.path.isdir(hist) else directory
    if os.path.isdir(hist):
        names = set(os.listdir(hist))
        for name in sorted(names):
            low = name.lower()
            full = os.path.join(hist, name)
            if not os.path.isfile(full):
                continue
            if loose and not (low.endswith(".run") or low.endswith(".run.backup") or low.endswith(".run.bak")):
                continue
            if low.endswith(".run"):
                found.append((full, "history"))
            elif low.endswith(".run.backup") or low.endswith(".run.bak"):
                primary = name.rsplit(".", 1)[0]
                if primary not in names:
                    found.append((full, "history"))
    for name, role in (("current_run.save", "current"), ("current_run_mp.save", "current_mp")):
        full = os.path.join(directory, name)
        if os.path.isfile(full):
            found.append((full, role))
        elif os.path.isfile(full + ".backup"):
            found.append((full + ".backup", role))
    return found


def load_path(path):
    """文件 → {kind: run, run}；目录 → {kind: folder, entries}。只读。"""
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.isfile(path):
        return {"v": 1, "kind": "run", "run": parse_path(path)}
    if not os.path.isdir(path):
        raise SaveImportError("not_found", path=path)
    files = _list_run_files(path)
    warnings = []
    if len(files) > MAX_FILES:
        warnings.append({"code": "truncated", "n": MAX_FILES})
        files = files[:MAX_FILES]
    entries = []
    for full, role in files:
        try:
            run = parse_path(full)
            entries.append({"file": os.path.basename(full), "path": full, "role": role, "run": run})
        except SaveImportError as e:
            entries.append({"file": os.path.basename(full), "path": full, "role": role,
                            "error": {"code": e.code, **e.params}})
    if not entries:
        raise SaveImportError("dir_empty", path=path)
    return {"v": 1, "kind": "folder", "path": _save_dir(path), "warnings": warnings, "entries": entries}


def candidate_roots():
    """可能放着游戏用户数据的目录。DECKBENCH_SAVE_ROOTS 用 os.pathsep 追加，方便测试和自定义位置。"""
    home = os.path.expanduser("~")
    roots = []
    extra = os.environ.get("DECKBENCH_SAVE_ROOTS", "")
    if extra:
        roots.extend(p for p in extra.split(os.pathsep) if p)
    app = os.environ.get("APPDATA")
    if app:
        roots.append(os.path.join(app, "SlayTheSpire2"))
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        roots.append(os.path.join(xdg, "SlayTheSpire2"))
    roots.append(os.path.join(home, ".local", "share", "SlayTheSpire2"))
    roots.append(os.path.join(home, ".var", "app", "com.valvesoftware.Steam", "data", "SlayTheSpire2"))
    roots.append(os.path.join(home, "Library", "Application Support", "SlayTheSpire2"))
    out = []
    for r in roots:
        r = os.path.abspath(os.path.expanduser(r))
        if r not in out and os.path.isdir(r):
            out.append(r)
    return out


def discover():
    """在常见位置找 saves 目录（含 history 或 current_run）。不读取文件内容。"""
    found = []
    seen = set()
    for root in candidate_roots():
        for dirpath, dirnames, filenames in os.walk(root):
            rel = os.path.relpath(dirpath, root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > 6:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d.lower() not in ("logs", "replay")]
            base = os.path.basename(dirpath).lower()
            interesting = base == "saves" or "current_run.save" in filenames or "current_run_mp.save" in filenames
            hist = os.path.join(dirpath, "history")
            if interesting and (os.path.isdir(hist) or "current_run.save" in filenames or "current_run_mp.save" in filenames):
                ap = os.path.abspath(dirpath)
                if ap not in seen:
                    seen.add(ap)
                    n = 0
                    if os.path.isdir(hist):
                        n = sum(1 for f in os.listdir(hist) if f.lower().endswith(".run"))
                    found.append({
                        "path": ap,
                        "label": os.path.relpath(ap, root),
                        "history": n,
                        "has_current": "current_run.save" in filenames or "current_run_mp.save" in filenames,
                    })
    return found


def _save_filename(name):
    low = os.path.basename(str(name)).lower()
    if low in _NOT_RUN:
        return True
    return low.endswith((
        ".run", ".save", ".run.backup", ".save.backup", ".run.bak", ".save.bak",
    ))


_SAVE_DIR_NAMES = ("saves", "history", "slaythespire2")


def _looks_like_save_dir(path):
    """路径上的 saves / history / SlayTheSpire2。旁边有夹具文件的普通文件夹不算。"""
    if not path or not os.path.isdir(path):
        return False
    return os.path.basename(path).lower() in _SAVE_DIR_NAMES


def _realpath(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _under(path, root):
    path = os.path.normcase(_realpath(path))
    root = os.path.normcase(_realpath(root))
    if path == root:
        return True
    try:
        return os.path.normcase(os.path.commonpath([path, root])) == root
    except ValueError:
        return False


def _save_ancestors(start):
    roots = []
    cur = os.path.abspath(start)
    for _ in range(10):
        if _looks_like_save_dir(cur):
            roots.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return roots


def refuse_save_write(dest, source=None):
    """拒绝把输出写进存档树、覆盖刚读的文件，或写成 .run / .save。

    存档树是本机游戏数据根（candidate_roots），以及路径上名叫 saves / history /
    SlayTheSpire2 的目录。旁边有夹具的工作目录可以写 JSON。通过则返回规范化后的目标路径。
    """
    dest_abs = _realpath(dest)
    if _save_filename(dest_abs):
        raise SaveImportError("refuse_write", path=dest_abs)
    roots = [_realpath(r) for r in candidate_roots()]
    if source:
        src = _realpath(source)
        if os.path.lexists(src) and _under(dest_abs, src) and (os.path.isfile(src) or not os.path.isdir(src)):
            raise SaveImportError("refuse_write", path=dest_abs)
        if os.path.isdir(src):
            roots.extend(_save_ancestors(src))
            save_dir = _realpath(_save_dir(src))
            # 只把真正的存档目录加进去。放着夹具的普通文件夹不是存档树。
            if _looks_like_save_dir(save_dir):
                roots.append(save_dir)
        else:
            roots.extend(_save_ancestors(os.path.dirname(src)))
    parent = os.path.dirname(dest_abs)
    if parent:
        roots.extend(_save_ancestors(parent))
    seen = set()
    for root in roots:
        key = os.path.normcase(root)
        if key in seen or not os.path.isdir(root):
            continue
        seen.add(key)
        if _under(dest_abs, root):
            raise SaveImportError("refuse_write", path=dest_abs)
    return dest_abs


def _floor_reached(run):
    floors = []
    for fl in run.get("route") or []:
        n = fl.get("floor") if isinstance(fl, dict) else None
        if isinstance(n, int) and not isinstance(n, bool):
            floors.append(n)
    if floors:
        return max(floors)
    coords = run.get("visited_map_coords") or []
    return len(coords) if isinstance(coords, list) else 0


def _vitals(run):
    for fl in reversed(run.get("route") or []):
        for st in fl.get("stats") or []:
            if isinstance(st, dict) and any(st.get(k) is not None for k in ("current_hp", "max_hp", "gold")):
                return st.get("current_hp"), st.get("max_hp"), st.get("gold")
    for p in run.get("players") or []:
        if any(p.get(k) is not None for k in ("current_hp", "max_hp", "gold")):
            return p.get("current_hp"), p.get("max_hp"), p.get("gold")
    return None, None, None


def _notable_card(card):
    if card.get("upgraded"):
        return True
    ench = card.get("enchantment") or {}
    if isinstance(ench, dict) and ench.get("id"):
        return True
    floor = card.get("floor")
    return isinstance(floor, int) and not isinstance(floor, bool) and floor > 0


def _card_brief(card, player):
    item = {"id": card.get("id"), "upgraded": bool(card.get("upgraded")), "floor": card.get("floor")}
    ench = card.get("enchantment") or {}
    if isinstance(ench, dict) and ench.get("id"):
        item["enchantment"] = ench["id"]
        if ench.get("amount") is not None:
            item["enchantment_amount"] = ench["amount"]
    if player is not None:
        item["player"] = player
    return item


def _relic_brief(relic, player):
    item = {"id": relic.get("id"), "floor": relic.get("floor")}
    if player is not None:
        item["player"] = player
    return item


def _summarize_run(run):
    players = [p for p in (run.get("players") or []) if isinstance(p, dict)]
    multi = len(players) > 1
    characters, character_ids = [], []
    cards, relics = [], []
    for p in players:
        display = p.get("sim_character") or p.get("character")
        if display:
            characters.append(display)
        if p.get("character"):
            character_ids.append(p.get("character"))
        pid = p.get("id") if multi else None
        for c in p.get("deck") or []:
            if isinstance(c, dict) and c.get("id"):
                cards.append((c, pid))
        for r in p.get("relics") or []:
            if isinstance(r, dict) and r.get("id"):
                relics.append((r, pid))
    notable = [(c, pid) for c, pid in cards if _notable_card(c)]
    shown = notable or cards
    card_rows = [_card_brief(c, pid) for c, pid in shown[:SUMMARY_CARD_CAP]]

    def _notable_relic(relic):
        floor = relic.get("floor")
        return isinstance(floor, int) and not isinstance(floor, bool) and floor > 0

    relic_rows = [_relic_brief(r, pid) for r, pid in (
        [(r, pid) for r, pid in relics if _notable_relic(r)]
        + [(r, pid) for r, pid in relics if not _notable_relic(r)]
    )[:SUMMARY_RELIC_CAP]]
    picks = []
    for fl in run.get("route") or []:
        if not isinstance(fl, dict):
            continue
        for group in fl.get("picks") or []:
            if not isinstance(group, dict):
                continue
            offered, picked = [], []
            for c in group.get("cards") or []:
                if not isinstance(c, dict) or not c.get("id"):
                    continue
                offered.append(c["id"])
                if c.get("was_picked"):
                    picked.append(c["id"])
            if not offered:
                continue
            entry = {"floor": fl.get("floor"), "type": fl.get("type"), "picked": picked, "offered": offered}
            if group.get("player_id") is not None:
                entry["player"] = group["player_id"]
            picks.append(entry)
    hp, max_hp, gold = _vitals(run)
    primary = players[0] if players else {}
    return {
        "ok": True,
        "v": 1,
        "read_only": True,
        "kind": run.get("kind"),
        "file": run.get("filename"),
        "path": run.get("path"),
        "seed": run.get("seed"),
        "seed_source": run.get("seed_source"),
        "character": primary.get("sim_character") or primary.get("character"),
        "character_id": primary.get("character"),
        "characters": characters,
        "character_ids": character_ids,
        "ascension": run.get("ascension"),
        "floor_reached": _floor_reached(run),
        "result": run.get("result"),
        "schema_version": run.get("schema_version"),
        "hp": hp,
        "max_hp": max_hp,
        "gold": gold,
        "killed_by": run.get("killed_by_encounter") or run.get("killed_by_event"),
        "acts": [a.get("id") for a in run.get("acts") or [] if isinstance(a, dict) and a.get("id")],
        "highlights": {
            "cards": card_rows,
            "cards_truncated": len(shown) > SUMMARY_CARD_CAP,
            "deck_size": len(cards),
            "relics": relic_rows,
            "relics_truncated": len(relics) > SUMMARY_RELIC_CAP,
            "relic_count": len(relics),
            "picks": picks[-SUMMARY_PICK_CAP:],
            "picks_truncated": len(picks) > SUMMARY_PICK_CAP,
        },
        "warnings": [w.get("code") for w in run.get("warnings") or [] if isinstance(w, dict) and w.get("code")],
    }


def _summarize_folder(doc):
    entries, failures = [], []
    for e in doc.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if isinstance(e.get("run"), dict):
            row = _summarize_run(e["run"])
            row["role"] = e.get("role")
            entries.append(row)
        else:
            err = e.get("error") or {}
            failures.append({
                "ok": False,
                "read_only": True,
                "file": e.get("file"),
                "path": e.get("path"),
                "role": e.get("role"),
                "error": err.get("code") if isinstance(err, dict) else None,
            })
    return {
        "ok": True,
        "v": 1,
        "read_only": True,
        "kind": "folder",
        "path": doc.get("path"),
        "count": len(entries),
        "entries": entries,
        "failures": failures,
        "warnings": [w.get("code") for w in doc.get("warnings") or [] if isinstance(w, dict) and w.get("code")],
    }


_BATCH_RESULTS = {"won", "lost", "abandoned"}


def _batch_row(run, file=None):
    """一局 → 键顺序固定的短行。没有胜负或放弃时不写 result。"""
    players = [p for p in (run.get("players") or []) if isinstance(p, dict)]
    primary = players[0] if players else {}
    route = run.get("route")
    row = {
        "file": file if file is not None else run.get("filename"),
        "seed": run.get("seed"),
        "ascension": run.get("ascension"),
        "character": primary.get("sim_character") or primary.get("character"),
        "floors": len(route) if isinstance(route, list) else 0,
    }
    result = run.get("result")
    if result in _BATCH_RESULTS:
        row["result"] = result
    return row


def _batch_failure(entry):
    err = entry.get("error") or {}
    code = err.get("code") if isinstance(err, dict) else None
    return {"file": entry.get("file"), "error": code}


def batch_summary(doc):
    """load_path / normalize 的结果 → 稳定的每局摘要列表。不读盘、不写盘。

    目录只收 history 记录（current_run 不在内），顺序跟文件名排序一致。
    成功行的键是 file、seed、ascension、character、floors，打完才加 result
    （won / lost / abandoned）。读不开的文件是 {file, error}，error 为
    SaveImportError 的 code。扫过的文件超过上限时，末尾加 {error: truncated, n}。
    """
    if not isinstance(doc, dict):
        raise SaveImportError("not_object")
    if doc.get("kind") == "folder" and "entries" in doc:
        rows = []
        for entry in doc.get("entries") or []:
            if not isinstance(entry, dict) or entry.get("role") != "history":
                continue
            run = entry.get("run")
            if isinstance(run, dict):
                rows.append(_batch_row(run, entry.get("file")))
            else:
                rows.append(_batch_failure(entry))
        for warning in doc.get("warnings") or []:
            if not isinstance(warning, dict) or warning.get("code") != "truncated":
                continue
            extra = {"error": "truncated"}
            n = warning.get("n")
            if isinstance(n, int) and not isinstance(n, bool):
                extra["n"] = n
            rows.append(extra)
        return rows
    if doc.get("kind") == "run" and isinstance(doc.get("run"), dict):
        return [_batch_row(doc["run"], doc["run"].get("filename"))]
    if doc.get("kind") in ("run_history", "live_save") or "players" in doc or "route" in doc:
        return [_batch_row(doc)]
    raise SaveImportError("unknown_shape")


def summarize(doc):
    """load_path / normalize 的结果 → 短摘要。不读盘、不写盘。"""
    if not isinstance(doc, dict):
        raise SaveImportError("not_object")
    if doc.get("kind") == "folder" and "entries" in doc:
        return _summarize_folder(doc)
    if doc.get("kind") == "run" and isinstance(doc.get("run"), dict):
        return _summarize_run(doc["run"])
    if doc.get("kind") in ("run_history", "live_save") or "players" in doc or "route" in doc:
        return _summarize_run(doc)
    raise SaveImportError("unknown_shape")


def _error_body(err):
    body = {"ok": False, "read_only": True, "error": err.code}
    for k, v in err.params.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            body[k] = v
    return body


def summary_json(path):
    """读 path，返回一行可解析的 JSON 文本。失败也是 JSON，并且不写盘。"""
    try:
        return json.dumps(summarize(load_path(path)), ensure_ascii=False)
    except SaveImportError as e:
        return json.dumps(_error_body(e), ensure_ascii=False)
