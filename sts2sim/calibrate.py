"""真对局和模拟局的校准：同一颗种子、同一个角色、同一条选牌路径上，按每场战斗比掉血。

模拟样本只来自选牌序列完全相同的局。一场真机战斗要对上模拟，层数、房间
（Monster / Elite / Boss）和遭遇 ID 必须都一致。对不上就标 unmatched，不用旁边的层
或别的遭遇来凑。真值落在模拟掉血的 p5–p95 之外时，记成疑似模拟模型缺口。

百分位：模拟分布用线性插值（numpy 默认的 linear，index = p/100*(n-1)）。
真值的位置用 midrank：100 * (小于真值的个数 + 0.5 * 相等的个数) / n。

Calibration of an imported run against simulations that share its seed, character
and card-pick path. A real fight matches a simulated fight only when the floor,
the combat room and the encounter id all agree. Anything else is unmatched.
A real HP loss outside the simulated p5–p95 band is a likely sim-model gap.
"""
from __future__ import annotations

import json
import math
import os
import re

from sts2sim.analysis import AnalysisError, _batch_file, _load_jsonl, allowed_roots, resolve_read
from sts2sim.engine.seed import canonicalize
from sts2sim.saveimport import SaveImportError, _sim_character, load_path

_EXCLUDED_KEYS = (
    "seed", "character", "ascension", "deck_path", "sim_error", "not_a_run", "bad_combat",
)
_REASON_RANK = (
    "ambiguous_sim",
    "encounter_mismatch",
    "room_mismatch",
    "act_mismatch",
    "missing_encounter",
    "sim_hp_missing",
    "no_sim_fight",
)
_COMBAT_ROOMS = {"Monster", "Elite", "Boss"}
_QUIET_ROOMS = {"Ancient", "RestSite", "Shop", "Treasure", "Event"}
_ROOM_NAMES = {
    "monster": "Monster",
    "elite": "Elite",
    "boss": "Boss",
    "ancient": "Ancient",
    "restsite": "RestSite",
    "rest": "RestSite",
    "shop": "Shop",
    "merchant": "Shop",
    "treasure": "Treasure",
    "unknown": "Unknown",
    "unassigned": "Unknown",
    "event": "Event",
}
_LIST_LIMIT = 200
_LIST_DEPTH = 6
_LIST_SKIP = {"saves", "history", "SlayTheSpire2", "node_modules", ".git", "__pycache__"}
_CURRENT_SAVES = ("current_run.save", "current_run_mp.save")
_BLANK_SIM = {
    "sim_n": None,
    "mean": None,
    "p10": None,
    "p90": None,
    "p5": None,
    "p95": None,
    "percentile": None,
    "outside_p5_p95": None,
    "likely_sim_gap": False,
}


class CalibrateError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def _dump(body):
    return json.dumps(body, ensure_ascii=False, indent=1) + "\n"


def _error_json(err):
    body = {"ok": False, "read_only": True, "error": err.code}
    for key, value in getattr(err, "params", {}).items():
        if value is None or isinstance(value, (str, int, float, bool)):
            body[key] = value
    return _dump(body)


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return None


def _index(value):
    """层数、幕序号、进阶：整数。布尔和小数不算。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _json_num(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
    return value


def _norm_room(raw):
    """Combat 这种含糊的名字不映射。认不出就返回 None，调用方不拿它去凑。"""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if "." in text:
        text = text.split(".")[-1]
    return _ROOM_NAMES.get(re.sub(r"[^a-z]", "", text.lower()))


def _norm_enc(raw):
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text.upper() in {"NONE", "NONE.NONE", "NULL", "?", "UNKNOWN"}:
        return None
    upper = text.upper()
    if upper.startswith("EVENT.") or upper.startswith("ACT."):
        return None
    if upper.startswith("ENCOUNTER."):
        text = text.split(".", 1)[1]
        return text or None
    return text


def _card_entry(raw):
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or text.lower() in {"none", "none.none", "null"}:
        return None
    if text.upper().startswith("CARD."):
        text = text.split(".", 1)[1]
        if not text:
            return None
    return text


def character_key(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    mapped = _sim_character(text)
    if mapped:
        return mapped
    return text.split(".")[-1]


def _linear(sorted_values, percent):
    """线性百分位。n=1 时就是那一个数。index = percent/100 * (n-1)。"""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return sorted_values[0]
    num = percent * (n - 1)
    lo = num // 100
    rem = num % 100
    if rem == 0:
        return sorted_values[lo]
    hi = lo + 1
    left = sorted_values[lo]
    right = sorted_values[hi]
    return (left * (100 - rem) + right * rem) / 100


def _midrank(values, real):
    n = len(values)
    less = sum(1 for value in values if value < real)
    equal = sum(1 for value in values if value == real)
    return 100.0 * (less + 0.5 * equal) / n


def _real_deck(run, player_id):
    out = []
    for floor in run.get("route") or []:
        if not isinstance(floor, dict):
            continue
        for group in floor.get("picks") or []:
            if not isinstance(group, dict):
                continue
            group_id = group.get("player_id")
            if group_id is not None and player_id is not None and group_id != player_id:
                continue
            for card in group.get("cards") or []:
                if not isinstance(card, dict) or card.get("was_picked") is not True:
                    continue
                entry = _card_entry(card.get("id"))
                if entry:
                    out.append(entry)
    return out


def _real_identity(run):
    if not isinstance(run, dict):
        raise CalibrateError("no_character")
    players = run.get("players")
    if not isinstance(players, list) or not players:
        raise CalibrateError("no_character")
    if len(players) != 1 or not isinstance(players[0], dict):
        raise CalibrateError("multiplayer" if len(players) > 1 else "no_character")
    player = players[0]
    from_player = character_key(player.get("sim_character") or player.get("character"))
    from_run = character_key(run.get("sim_character")) if run.get("sim_character") else None
    if from_player and from_run and from_player != from_run:
        raise CalibrateError("no_character")
    character = from_player or from_run
    if not character:
        raise CalibrateError("no_character")
    seed = run.get("seed")
    if not isinstance(seed, str) or not canonicalize(seed):
        raise CalibrateError("no_seed")
    ascension = _index(run.get("ascension"))
    if ascension is None:
        raise CalibrateError("no_ascension")
    return {
        "seed": canonicalize(seed),
        "character": character,
        "ascension": ascension,
        "player_id": player.get("id"),
        "deck_path": _real_deck(run, player.get("id")),
    }


def _sim_deck(picked):
    """认不出整段选牌时返回 None。空列表是「没选牌」，和缺字段不是一回事。"""
    if not isinstance(picked, list):
        return None
    out = []
    for item in picked:
        if isinstance(item, str):
            entry = _card_entry(item)
        elif isinstance(item, dict):
            entry = _card_entry(item.get("id"))
        else:
            return None
        if not entry:
            return None
        out.append(entry)
    return out


def _one_combat(raw):
    if isinstance(raw, dict):
        floor = _index(raw.get("floor"))
        room = _norm_room(raw.get("room", raw.get("room_type")))
        encounter = _norm_enc(raw.get("encounter"))
        hp = _number(raw.get("hp_lost"))
        if "act_index" in raw:
            act = _index(raw.get("act_index"))
        elif "act" in raw:
            act = _index(raw.get("act"))
        else:
            act = None
        if "act_index" in raw and "act" in raw and _index(raw.get("act_index")) != _index(raw.get("act")):
            return None
    elif isinstance(raw, (list, tuple)) and not isinstance(raw, str) and len(raw) >= 5:
        floor = _index(raw[0])
        room = _norm_room(raw[1])
        encounter = _norm_enc(raw[2])
        hp = _number(raw[4])
        act = _index(raw[6]) if len(raw) > 6 else None
    else:
        return None
    if floor is None:
        return None
    return {"floor": floor, "room": room, "encounter": encounter, "hp": hp, "act": act}


def _parse_sim_row(row):
    if not isinstance(row, dict):
        return {"kind": "not_a_run"}
    if row.get("error"):
        return {"kind": "sim_error"}
    seed = row.get("seed")
    seed_key = canonicalize(seed) if isinstance(seed, str) and seed.strip() else None
    names = []
    for key in ("char", "character"):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            mapped = character_key(raw)
            if mapped:
                names.append(mapped)
    character = names[0] if names and len(set(names)) == 1 else None
    asc_values = []
    if "asc" in row and row.get("asc") is not None:
        asc_values.append(_index(row.get("asc")))
    if "ascension" in row and row.get("ascension") is not None:
        asc_values.append(_index(row.get("ascension")))
    if asc_values and all(value is not None for value in asc_values) and len(set(asc_values)) == 1:
        ascension = asc_values[0]
    else:
        ascension = None
    if "picked" not in row:
        deck = None
    else:
        deck = _sim_deck(row.get("picked"))
    combats = row.get("combats")
    fights = []
    bad = not isinstance(combats, list)
    if not bad:
        for item in combats:
            parsed = _one_combat(item)
            if parsed is None:
                bad = True
                fights = []
                break
            fights.append(parsed)
    return {
        "kind": "ok",
        "seed": seed_key,
        "char": character,
        "asc": ascension,
        "deck": deck,
        "deck_known": deck is not None,
        "fights": fights,
        "bad_combat": bad,
    }


def _exclude_reason(row, ident):
    if row["kind"] == "not_a_run":
        return "not_a_run"
    if row["kind"] == "sim_error":
        return "sim_error"
    if row["seed"] is None or row["seed"] != ident["seed"]:
        return "seed"
    if row["char"] is None or row["char"] != ident["character"]:
        return "character"
    if row["asc"] is None or row["asc"] != ident["ascension"]:
        return "ascension"
    if not row["deck_known"] or row["deck"] != ident["deck_path"]:
        return "deck_path"
    if row["bad_combat"]:
        return "bad_combat"
    return None


def _pool_reason(parsed, ident):
    if not parsed:
        return "no_sim_rows"
    usable = [row for row in parsed if row["kind"] == "ok"]
    if not usable:
        if any(row["kind"] == "sim_error" for row in parsed):
            return "sim_error" if all(row["kind"] == "sim_error" for row in parsed) else "not_a_run"
        return "not_a_run"
    seeded = [row for row in usable if row["seed"] == ident["seed"]]
    if not seeded:
        return "seed"
    matched_char = [row for row in seeded if row["char"] == ident["character"]]
    if not matched_char:
        return "character"
    matched_asc = [row for row in matched_char if row["asc"] == ident["ascension"]]
    if not matched_asc:
        return "ascension"
    matched_path = [row for row in matched_asc if row["deck_known"] and row["deck"] == ident["deck_path"]]
    if not matched_path:
        return "deck_path"
    return "bad_combat"


def _room_encounter(room):
    if not isinstance(room, dict):
        return None
    raw = room.get("model_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    upper = raw.strip().upper()
    if upper.startswith("EVENT.") or upper.startswith("ACT.") or upper.startswith("NONE"):
        return None
    if upper.startswith("ENCOUNTER.") or _norm_room(room.get("room_type")) in _COMBAT_ROOMS:
        return _norm_enc(raw)
    return None


def _classify_floor(floor):
    """返回 (kind, room, encounter, reason)。kind 是 fight / not_a_fight / unmatched。"""
    if not isinstance(floor, dict) or _index(floor.get("floor")) is None:
        return "unmatched", None, None, "unknown_floor"
    map_type = _norm_room(floor.get("type"))
    room_types = []
    encounters = []
    for room in floor.get("rooms") or []:
        if not isinstance(room, dict):
            continue
        room_type = _norm_room(room.get("room_type"))
        if room_type:
            room_types.append(room_type)
        encounter = _room_encounter(room)
        if encounter and encounter not in encounters:
            encounters.append(encounter)
    combat = []
    quiet = []
    for name in [map_type, *room_types]:
        if name in _COMBAT_ROOMS and name not in combat:
            combat.append(name)
        elif name in _QUIET_ROOMS and name not in quiet:
            quiet.append(name)
    if len(combat) > 1 or (combat and map_type in _QUIET_ROOMS):
        return "unmatched", combat[0] if len(combat) == 1 else None, None, "ambiguous_floor"
    if len(encounters) > 1:
        return "unmatched", combat[0] if combat else map_type, None, "ambiguous_encounter"
    if len(combat) == 1:
        encounter = encounters[0] if encounters else None
        if encounter is None:
            return "unmatched", combat[0], None, "missing_encounter"
        return "fight", combat[0], encounter, None
    if map_type == "Unknown" or "Unknown" in room_types or map_type is None and not room_types:
        return "unmatched", map_type, None, "unknown_floor"
    if map_type in _QUIET_ROOMS or quiet:
        return "not_a_fight", map_type or (quiet[0] if quiet else None), None, None
    return "unmatched", map_type, None, "unknown_floor"


def _real_hp(floor, player_id):
    stats = [item for item in (floor.get("stats") or []) if isinstance(item, dict)]
    if player_id is not None:
        owned = [item for item in stats if item.get("player_id") == player_id]
        if owned:
            stats = owned
        elif len(stats) > 1:
            return "ambiguous"
    if len(stats) != 1:
        return "missing" if not stats else "ambiguous"
    if stats[0].get("damage_taken") is None:
        return "missing"
    number = _number(stats[0].get("damage_taken"))
    if number is None:
        return "missing"
    return number


def _sample(real_fight, sim_row):
    fights = [item for item in sim_row["fights"] if item["floor"] == real_fight["floor"]]
    if real_fight["act"] is not None:
        act_ok = [item for item in fights if item["act"] is None or item["act"] == real_fight["act"]]
        if fights and not act_ok:
            return None, "act_mismatch"
        fights = act_ok
    if not fights:
        return None, "no_sim_fight"
    room_ok = [item for item in fights if item["room"] == real_fight["room"]]
    if not room_ok:
        return None, "room_mismatch"
    enc_ok = [item for item in room_ok if item["encounter"] == real_fight["encounter"]]
    if not enc_ok:
        if any(item["encounter"] is None for item in room_ok):
            return None, "missing_encounter"
        return None, "encounter_mismatch"
    hp_ok = [item for item in enc_ok if item["hp"] is not None]
    if not hp_ok:
        return None, "sim_hp_missing"
    if len(hp_ok) != 1:
        return None, "ambiguous_sim"
    return hp_ok[0]["hp"], None


def _top_reason(reasons):
    if not reasons:
        return "no_sim_fight"
    counts = {}
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1
    best = max(counts.values())
    for name in _REASON_RANK:
        if counts.get(name) == best:
            return name
    return reasons[0]


def _hp_value(hp_state):
    if isinstance(hp_state, (int, float)) and not isinstance(hp_state, bool):
        return _json_num(hp_state)
    return None


def _fight_row(floor, act, room, encounter, status, reason, real_hp, stats=None):
    row = {
        "floor": floor,
        "act_index": act,
        "room": room,
        "encounter": encounter,
        "status": status,
        "reason": reason,
        "real_hp_lost": _hp_value(real_hp),
    }
    row.update(stats or _BLANK_SIM)
    return row


def _compared_stats(values, real_hp):
    ordered = sorted(values)
    p5 = _linear(ordered, 5)
    p10 = _linear(ordered, 10)
    p90 = _linear(ordered, 90)
    p95 = _linear(ordered, 95)
    outside = bool(real_hp < p5 or real_hp > p95)
    return {
        "sim_n": len(ordered),
        "mean": _json_num(sum(ordered) / len(ordered)),
        "p10": _json_num(p10),
        "p90": _json_num(p90),
        "p5": _json_num(p5),
        "p95": _json_num(p95),
        "percentile": _json_num(_midrank(ordered, real_hp)),
        "outside_p5_p95": outside,
        "likely_sim_gap": outside,
    }


def report(run, sim_rows):
    """归一化后的一局（saveimport.normalize 的结果）对一组模拟行。不读盘，不写盘。"""
    ident = _real_identity(run)
    parsed = [_parse_sim_row(row) for row in sim_rows]
    excluded_counts = {key: 0 for key in _EXCLUDED_KEYS}
    eligible = []
    for row in parsed:
        reason = _exclude_reason(row, ident)
        if reason:
            excluded_counts[reason] += 1
        else:
            eligible.append(row)
    pool = None if eligible else _pool_reason(parsed, ident)
    fights = []
    for floor in run.get("route") or []:
        kind, room, encounter, identity_reason = _classify_floor(floor if isinstance(floor, dict) else {})
        number = _index(floor.get("floor")) if isinstance(floor, dict) else None
        act = _index(floor.get("act_index")) if isinstance(floor, dict) else None
        hp_state = _real_hp(floor, ident["player_id"]) if isinstance(floor, dict) else "missing"
        if kind == "not_a_fight":
            fights.append(_fight_row(number, act, room, None, "not_a_fight", None, None))
            continue
        if kind == "unmatched":
            fights.append(_fight_row(number, act, room, encounter, "unmatched", identity_reason, hp_state))
            continue
        if pool:
            fights.append(_fight_row(number, act, room, encounter, "unmatched", pool, hp_state))
            continue
        samples = []
        reasons = []
        spec = {"floor": number, "act": act, "room": room, "encounter": encounter}
        for row in eligible:
            hp, why = _sample(spec, row)
            if why:
                reasons.append(why)
            else:
                samples.append(hp)
        if not samples:
            fights.append(_fight_row(number, act, room, encounter, "unmatched", _top_reason(reasons), hp_state))
            continue
        if hp_state == "ambiguous":
            fights.append(_fight_row(number, act, room, encounter, "unmatched", "ambiguous_hp", None))
            continue
        if not isinstance(hp_state, (int, float)) or isinstance(hp_state, bool):
            fights.append(_fight_row(number, act, room, encounter, "unmatched", "missing_hp", None))
            continue
        fights.append(_fight_row(
            number, act, room, encounter, "compared", None, hp_state, _compared_stats(samples, hp_state),
        ))
    excluded = {key: excluded_counts[key] for key in _EXCLUDED_KEYS if excluded_counts[key]}
    return {
        "ok": True,
        "read_only": True,
        "v": 1,
        "seed": ident["seed"],
        "character": ident["character"],
        "ascension": ident["ascension"],
        "deck_path": list(ident["deck_path"]),
        "deck_path_rule": "exact_picked_cards",
        "alignment": "floor_room_encounter",
        "percentile_method": "midrank",
        "sim_percentile_method": "linear",
        "gap_band": [5, 95],
        "sim_rows": len(sim_rows),
        "sim_matched": len(eligible),
        "excluded": excluded,
        "gaps": [item["floor"] for item in fights if item["likely_sim_gap"]],
        "unmatched": [item["floor"] for item in fights if item["status"] == "unmatched"],
        "fights": fights,
    }


def _with_paths(body, real_path, sim_path):
    out = {}
    for key, value in body.items():
        out[key] = value
        if key == "v":
            out["real_path"] = os.path.realpath(real_path)
            out["sim_path"] = os.path.realpath(sim_path)
    return out


def _load_open(path):
    raw = os.path.abspath(os.path.expanduser(path.strip()))
    candidate = os.path.join(raw, "runs.jsonl") if os.path.isdir(raw) else raw
    if not os.path.isfile(candidate):
        raise CalibrateError("not_found", path=candidate)
    return os.path.realpath(candidate), _load_jsonl(candidate)


def _load_restricted(path):
    found = _batch_file(path)
    return found, _load_jsonl(found)


def calibrate_paths(real, sim, *, restricted=True):
    """读一份对局和一份模拟 jsonl。restricted 时模拟路径走 analysis 的允许目录。"""
    if not isinstance(real, str) or not real.strip():
        raise CalibrateError("need_real")
    if not isinstance(sim, str) or not sim.strip():
        raise CalibrateError("need_sim")
    doc = load_path(real.strip())
    if doc.get("kind") != "run":
        raise CalibrateError("one_run")
    if restricted:
        sim_path, rows = _load_restricted(sim)
    else:
        sim_path, rows = _load_open(sim)
    real_path = doc["run"].get("path") or real
    return _with_paths(report(doc["run"], rows), real_path, sim_path)


def calibrate_json(real, sim):
    """MCP / 调用方用的 JSON。失败也是 JSON，不抛异常。模拟路径受 analysis 目录限制。"""
    try:
        return _dump(calibrate_paths(real, sim, restricted=True))
    except (CalibrateError, SaveImportError, AnalysisError) as err:
        return _error_json(err)


def parse_sim_bytes(data):
    """上传的模拟 jsonl。空行跳过，一行一个对象。不写盘。超过存档上限的正文不解析。"""
    from sts2sim.saveimport import MAX_BYTES
    if not isinstance(data, (bytes, bytearray)):
        raise AnalysisError("not_json", line=1)
    if len(data) > MAX_BYTES:
        raise AnalysisError("too_big")
    try:
        text = bytes(data).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AnalysisError("not_json", line=1)
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            raise AnalysisError("not_json", line=i)
        if not isinstance(row, dict):
            raise AnalysisError("not_json", line=i)
        rows.append(row)
    return rows


def calibrate_rows(real, rows):
    """一份对局路径对已经读入的模拟行。不读模拟文件，不写盘。"""
    if not isinstance(real, str) or not real.strip():
        raise CalibrateError("need_real")
    if not isinstance(rows, list):
        raise CalibrateError("need_sim")
    doc = load_path(real.strip())
    if doc.get("kind") != "run":
        raise CalibrateError("one_run")
    body = report(doc["run"], rows)
    real_path = doc["run"].get("path") or real.strip()
    try:
        shown = os.path.realpath(real_path)
    except OSError:
        shown = str(real_path)
    out = {}
    for key, value in body.items():
        out[key] = value
        if key == "v":
            out["real_path"] = shown
    return out


def _history_runs(saves_dir):
    hist = os.path.join(saves_dir, "history")
    if not os.path.isdir(hist):
        return []
    try:
        names = sorted(os.listdir(hist))
    except OSError:
        return []
    out = []
    for name in names:
        if not name.lower().endswith(".run"):
            continue
        path = os.path.join(hist, name)
        if os.path.isfile(path):
            out.append(path)
    return out


def _files_named(dirpath, wanted):
    try:
        names = sorted(os.listdir(dirpath))
    except OSError:
        return []
    folded = {name.lower(): name for name in names}
    out = []
    for want in wanted:
        hit = folded.get(want)
        if not hit:
            continue
        path = os.path.join(dirpath, hit)
        if os.path.isfile(path):
            out.append(path)
    return out


def list_imported_runs():
    """discover() 找到的 history/*.run 和 current_run.save。只列路径，不读内容。"""
    from sts2sim.saveimport import discover

    runs = []
    seen = set()
    truncated = False
    for root in discover():
        if truncated:
            break
        base = root.get("path") if isinstance(root, dict) else None
        if not isinstance(base, str) or not os.path.isdir(base):
            continue
        for path in _history_runs(base) + _files_named(base, _CURRENT_SAVES):
            try:
                real = os.path.realpath(path)
            except OSError:
                continue
            if real in seen or not os.path.isfile(real):
                continue
            seen.add(real)
            runs.append({"path": real, "name": os.path.basename(real)})
            if len(runs) >= _LIST_LIMIT:
                truncated = True
                break
    runs.sort(key=lambda item: item["path"])
    return {"ok": True, "read_only": True, "runs": runs, "truncated": truncated}


def list_sim_files():
    """允许目录里的 runs.jsonl。只列路径，不读内容，不创建目录。"""
    found = []
    seen = set()
    truncated = False
    for root in allowed_roots():
        if truncated:
            break
        for dirpath, dirnames, names in os.walk(root, followlinks=False):
            rel = os.path.relpath(dirpath, root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth >= _LIST_DEPTH:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if d not in _LIST_SKIP and not d.startswith(".")]
            for name in sorted(names):
                if name != "runs.jsonl":
                    continue
                try:
                    real = resolve_read(os.path.join(dirpath, name))
                except AnalysisError:
                    continue
                if not os.path.isfile(real) or real in seen:
                    continue
                seen.add(real)
                found.append({"path": real, "name": os.path.basename(real)})
                if len(found) >= _LIST_LIMIT:
                    truncated = True
                    break
            if truncated:
                break
    found.sort(key=lambda item: item["path"])
    return {"ok": True, "read_only": True, "sims": found, "truncated": truncated}


def _fmt(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text
    return str(value)


def _fight_line(fight):
    floor = fight.get("floor")
    room = fight.get("room") or "—"
    if fight.get("status") == "not_a_fight":
        return f"floor {floor}  {room}  not a fight / 不是战斗"
    if fight.get("status") != "compared":
        return f"floor {floor}  {room}  unmatched / 对不上: {fight.get('reason')}"
    if fight.get("likely_sim_gap"):
        band = "  OUTSIDE p5–p95  likely sim gap / 疑似模拟缺口"
    else:
        band = "  inside p5–p95"
    encounter = fight.get("encounter") or "—"
    return (
        f"floor {floor}  {room}  {encounter}  real {_fmt(fight.get('real_hp_lost'))}  "
        f"n={fight.get('sim_n')}  mean {_fmt(fight.get('mean'))}  "
        f"p10 {_fmt(fight.get('p10'))}  p90 {_fmt(fight.get('p90'))}  "
        f"p5 {_fmt(fight.get('p5'))}  p95 {_fmt(fight.get('p95'))}  "
        f"percentile {_fmt(fight.get('percentile'))}{band}"
    )


def render_text(body):
    picks = body.get("deck_path") or []
    path = ", ".join(picks) if picks else "—"
    lines = [
        (
            f"校准 / calibration  seed={body.get('seed')}  "
            f"character={body.get('character')}  ascension={body.get('ascension')}"
        ),
        f"deck path / 选牌: {path}",
        (
            f"sim rows {body.get('sim_rows')}, matched {body.get('sim_matched')}, "
            f"gaps {len(body.get('gaps') or [])}, unmatched {len(body.get('unmatched') or [])}"
        ),
    ]
    for fight in body.get("fights") or []:
        lines.append(_fight_line(fight))
    return "\n".join(lines) + "\n"
