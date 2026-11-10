"""把一份或多份校准 JSON 里的疑似模拟缺口，按遭遇和敌人能力汇总成 Markdown。

真机掉血高于这一场的 p95，记成模拟偏乐观；低于 p5，记成模拟偏悲观。
只读校准结果、可选的名册，以及报告里已经指向、并且还读得开的真对局。
不新开模拟，不改种子，不改 AI。

Aggregate likely_sim_gap rows from calibration JSON by encounter and by the
enemy power or mechanic involved. Real HP lost above that fight's p95 means
the sim was too optimistic; below p5 means it was too pessimistic. Read-only:
it does not start a simulation and does not change seeds or AI.

  python tools/gap_triage.py calibration.json
  python tools/gap_triage.py a.json b.json --catalog catalog.json --out triage.md
  python tools/gap_triage.py tests/fixtures/gap_triage --catalog tests/fixtures/gap_triage/catalog.json --json -
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sts2sim.calibrate import _classify_floor, _norm_enc
from sts2sim.enemies import ENCOUNTER_SETUP, ROTATING_START
from sts2sim.gamedata import codex_dir, data_path
from sts2sim.saveimport import MAX_BYTES, SaveImportError, load_path, refuse_save_write

_POWER_FILES = (
    "sts2sim/powers_enemy.py",
    "sts2sim/powers.py",
    "sts2sim/enemies.py",
)
_SYMBOL_FILES = _POWER_FILES + (
    "sts2sim/ai/base.py",
    "sts2sim/ai/heuristic.py",
)
_MODEL_FILES = (
    "sts2sim/powers_enemy.py",
    "sts2sim/powers.py",
    "sts2sim/enemies.py",
)
# 这些指针是引擎里已经写明的近似，不是从游戏数据里抄来的表。
_MECHANICS = {
    "summon_skipped": {
        "label_zh": "召唤不生成新敌人",
        "label_en": "Summon does not add enemies",
        "symbols": (("sts2sim/enemies.py", "take_turn"),),
    },
    "status_card": {
        "label_zh": "Status 意图塞晕眩",
        "label_en": "Status intent adds Dazed",
        "symbols": (("sts2sim/enemies.py", "take_turn"),),
    },
    "conditional_branch": {
        "label_zh": "条件分支取第一个能用的",
        "label_en": "A conditional branch takes the first branch it can",
        "symbols": (("sts2sim/enemies.py", "_resolve"), ("sts2sim/enemies.py", "_ai_next")),
    },
    "encounter_setup": {
        "label_zh": "遭遇设定开场字段",
        "label_en": "Encounter sets start flags",
        "symbols": (("sts2sim/enemies.py", "ENCOUNTER_SETUP"),),
    },
    "rotating_start": {
        "label_zh": "开场招按站位轮换",
        "label_en": "Opening move rotates by slot",
        "symbols": (("sts2sim/enemies.py", "ROTATING_START"),),
    },
    "back_attack_always": {
        "label_zh": "后方攻击始终按背后结算",
        "label_en": "Back attack always counts as from behind",
        "symbols": (("sts2sim/powers_enemy.py", "BackAttack"),),
    },
}
_EXTRA_POINTERS = {
    "THORNS": ("sts2sim/ai/base.py", "mechanic_adjust", "optional; off unless mechanic_aware"),
}
_BACK_ATTACK = {"BACK_ATTACK_LEFT", "BACK_ATTACK_RIGHT"}
_COUNT_KEYS = ("compared", "optimistic", "pessimistic", "unknown_direction")
_KIND_RANK = {"power": 0, "mechanic": 1, "encounter": 2}
_INDEX = None


class TriageError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def _message(err):
    path = err.params.get("path", "")
    detail = err.params.get("detail", "")
    text = {
        "need_input": "需要至少一份校准 JSON。 / Need at least one calibration JSON.",
        "not_found": "找不到 {path}。 / Not found: {path}",
        "not_json": "{path} 不是 JSON。 / Not JSON: {path}",
        "too_big": "{path} 超过读取上限。 / Larger than the read limit: {path}",
        "not_calibration": "没有可用的校准报告。 / No calibration report to read.",
        "bad_catalog": "名册不是一份对象 JSON。 / The catalog is not a JSON object: {path}",
        "refuse_write": "拒绝写入 {path}。 / Refusing to write: {path}",
    }.get(err.code, err.code)
    text = text.format(path=path)
    if detail:
        text = text + " " + detail
    return text


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def _read_text(path):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise TriageError("not_found", path=path) from exc
    if size > MAX_BYTES:
        raise TriageError("too_big", path=path)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError as exc:
        raise TriageError("not_found", path=path) from exc
    except UnicodeError as exc:
        raise TriageError("not_json", path=path) from exc


def _read_json(path):
    try:
        return json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise TriageError("not_json", path=path) from exc
    except RecursionError as exc:
        raise TriageError("not_json", path=path) from exc


def _is_report(obj):
    return (
        isinstance(obj, dict)
        and obj.get("ok") is True
        and obj.get("v") == 1
        and obj.get("alignment") == "floor_room_encounter"
        and isinstance(obj.get("fights"), list)
    )


def _iter_files(paths, catalog_path):
    catalog_real = ""
    if catalog_path:
        catalog_real = os.path.realpath(os.path.expanduser(catalog_path))
    files = []
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            raise TriageError("need_input")
        path = os.path.abspath(os.path.expanduser(raw.strip()))
        if os.path.isdir(path):
            try:
                names = sorted(os.listdir(path))
            except OSError as exc:
                raise TriageError("not_found", path=path) from exc
            found = [os.path.join(path, name) for name in names if name.endswith(".json")]
            if not found:
                raise TriageError("not_found", path=path)
            files.extend(found)
        elif os.path.isfile(path):
            files.append(path)
        else:
            raise TriageError("not_found", path=path)
    if catalog_real:
        files = [path for path in files if os.path.realpath(path) != catalog_real]
    unique = []
    seen = set()
    for path in files:
        key = os.path.realpath(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    if not unique:
        raise TriageError("need_input")
    return unique


def _skip_note(path):
    return f"跳过（不是校准报告）/ skipped (not a calibration report): {path}"


def load_reports(paths, catalog_path=""):
    """读校准 JSON。目录只取其中的 ``*.json``。不是报告的对象跳过，坏 JSON 直接失败。"""
    reports = []
    sources = []
    notes = []
    for path in _iter_files(paths, catalog_path):
        obj = _read_json(path)
        taken = []
        if isinstance(obj, list):
            for item in obj:
                if _is_report(item):
                    taken.append(item)
            if not taken:
                notes.append(_skip_note(path))
        elif _is_report(obj):
            taken.append(obj)
        else:
            notes.append(_skip_note(path))
        for item in taken:
            reports.append(item)
            sources.append(path)
    if not reports:
        detail = " ".join(notes)
        raise TriageError("not_calibration", detail=detail)
    return reports, sources, notes


def _strings(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str) and item.strip() and item.strip() not in out:
            out.append(item.strip())
    return out


def _norm_monster(raw):
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.upper().startswith("MONSTER."):
        text = text.split(".", 1)[1]
    return text or None


def _clean_entry(raw):
    if not isinstance(raw, dict):
        return {"powers": [], "mechanics": [], "monsters": []}
    monsters = []
    for item in _strings(raw.get("monsters")):
        mid = _norm_monster(item)
        if mid and mid not in monsters:
            monsters.append(mid)
    return {
        "powers": _strings(raw.get("powers")),
        "mechanics": _strings(raw.get("mechanics")),
        "monsters": monsters,
    }


def _clean_map(raw):
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        mid = _norm_monster(key) or key.strip()
        out[mid] = _clean_entry(value)
    return out


def empty_catalog():
    return {"encounters": {}, "monsters": {}}


def load_catalog(path):
    if not path:
        return empty_catalog()
    raw_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(raw_path):
        raise TriageError("not_found", path=raw_path)
    data = _read_json(raw_path)
    if not isinstance(data, dict):
        raise TriageError("bad_catalog", path=raw_path)
    encounters = data.get("encounters", {})
    monsters = data.get("monsters", {})
    if not isinstance(encounters, dict) or not isinstance(monsters, dict):
        raise TriageError("bad_catalog", path=raw_path)
    return {"encounters": _clean_map(encounters), "monsters": _clean_map(monsters)}


def _add_power(powers, raw):
    if isinstance(raw, dict):
        pid = raw.get("power_id")
    elif isinstance(raw, str):
        pid = raw
    else:
        pid = None
    if isinstance(pid, str) and pid.strip() and pid.strip() not in powers:
        powers.append(pid.strip())


def _monster_record(raw):
    powers = []
    mechanics = []
    if not isinstance(raw, dict):
        return {"powers": powers, "mechanics": mechanics, "monsters": []}
    for item in raw.get("innate_powers") or []:
        _add_power(powers, item)
    for move in raw.get("moves") or []:
        if not isinstance(move, dict):
            continue
        for item in move.get("powers") or []:
            _add_power(powers, item)
        intent = move.get("intent")
        if isinstance(intent, str):
            folded = intent.lower()
            if "summon" in folded and "summon_skipped" not in mechanics:
                mechanics.append("summon_skipped")
            if "status" in folded and "status_card" not in mechanics:
                mechanics.append("status_card")
        if move.get("summons") is True and "summon_skipped" not in mechanics:
            mechanics.append("summon_skipped")
    return {"powers": powers, "mechanics": mechanics, "monsters": []}


def _composition_ids(comp):
    ids = []
    if not isinstance(comp, dict):
        return ids

    def add(raw):
        mid = _norm_monster(raw) if isinstance(raw, str) else None
        if mid and mid not in ids:
            ids.append(mid)

    for alt in comp.get("alternatives") or []:
        group = alt[1] if isinstance(alt, (list, tuple)) and len(alt) > 1 else None
        if isinstance(group, (list, tuple)):
            for item in group:
                add(item)
    for slot in comp.get("slots") or []:
        if isinstance(slot, (list, tuple)):
            for item in slot:
                add(item)
    pool = comp.get("pool")
    options = pool.get("options") if isinstance(pool, dict) else None
    if isinstance(options, dict):
        for item in options:
            add(item)
    return ids


def catalog_from_records(monsters, encounters, compositions=None):
    """从已经读入的怪物 / 遭遇记录收能力。记录是调用方自己的，函数不读盘。"""
    by_monster = {}
    if isinstance(monsters, list):
        for raw in monsters:
            if not isinstance(raw, dict):
                continue
            mid = _norm_monster(raw.get("id")) if isinstance(raw.get("id"), str) else None
            if mid:
                by_monster[mid] = _monster_record(raw)
    enc_map = {}
    comps = compositions if isinstance(compositions, dict) else {}
    if isinstance(encounters, list):
        for raw in encounters:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                continue
            key = _norm_enc(raw["id"]) or raw["id"].strip()
            if not key:
                continue
            mids = _composition_ids(comps.get(raw["id"])) or _composition_ids(comps.get(key))
            if not mids:
                for item in raw.get("monsters") or []:
                    if isinstance(item, dict):
                        mid = _norm_monster(item.get("id")) if isinstance(item.get("id"), str) else None
                    else:
                        mid = _norm_monster(item) if isinstance(item, str) else None
                    if mid and mid not in mids:
                        mids.append(mid)
            powers = []
            mechanics = []
            for mid in mids:
                rec = by_monster.get(mid) or {}
                for pid in rec.get("powers") or []:
                    if pid not in powers:
                        powers.append(pid)
                for mech in rec.get("mechanics") or []:
                    if mech not in mechanics:
                        mechanics.append(mech)
            enc_map[key] = {"powers": powers, "mechanics": mechanics, "monsters": mids}
    return {"encounters": enc_map, "monsters": by_monster}


def load_codex_catalog():
    """本机 spire-codex 导出存在时才读。没有、或读坏了，返回 (None, note)。"""
    root = codex_dir()
    monsters_path = os.path.join(root, "eng_monsters.json")
    enc_path = os.path.join(root, "eng_encounters.json")
    if not (os.path.isfile(monsters_path) and os.path.isfile(enc_path)):
        return None, ""
    try:
        monsters = _read_json(monsters_path)
        encounters = _read_json(enc_path)
    except TriageError:
        return None, "本机怪物数据读不开，能力只按名册和引擎里的开场字段。 / Local monster data could not be read; powers come from the catalog and engine start flags only."
    compositions = None
    comp_path = data_path("encounter_monsters.json")
    if comp_path:
        try:
            compositions = _read_json(comp_path)
        except TriageError:
            compositions = None
    if not isinstance(monsters, list) or not isinstance(encounters, list):
        return None, "本机怪物数据不是预期的列表。 / Local monster data is not the expected list."
    return catalog_from_records(monsters, encounters, compositions), ""


def _assigned_str(stmt):
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None, None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        return None, None
    value = stmt.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return target.id, value.value
    return None, None


def _class_power(node, rel):
    fields = {}
    for stmt in node.body:
        key, value = _assigned_str(stmt)
        if key in {"id", "name"} and key not in fields:
            fields[key] = value
    pid = fields.get("id")
    if not pid:
        return None
    doc = ast.get_docstring(node) or ""
    short = ""
    if doc:
        first = doc.strip().splitlines()[0].strip()
        for sep in ("：", ":"):
            if sep in first:
                first = first.split(sep, 1)[0].strip()
                break
        short = first
    return {
        "id": pid,
        "class": node.name,
        "file": rel,
        "line": node.lineno,
        "label_zh": fields.get("name") or short or node.name,
        "label_en": node.name,
    }


def _decl_line(node, lines):
    """装饰器会占掉 AST 的 lineno。指针指到 class / def 那一行。"""
    if isinstance(node, ast.ClassDef):
        keyword = "class "
    elif isinstance(node, ast.AsyncFunctionDef):
        keyword = "async def "
    else:
        keyword = "def "
    last = min(len(lines), node.lineno + 15)
    for lineno in range(node.lineno, last + 1):
        if lines[lineno - 1].lstrip().startswith(keyword):
            return lineno
    return node.lineno


def load_engine_index(root=None):
    """从仓库里的能力源码收集 id → 类和行号。不读游戏数据。"""
    root = root or ROOT
    powers = {}
    symbols = {}
    for rel in _SYMBOL_FILES:
        path = os.path.join(root, *rel.split("/"))
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        lines = text.splitlines()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        if rel in _POWER_FILES:
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                info = _class_power(node, rel)
                if info and info["id"] not in powers:
                    info["line"] = _decl_line(node, lines)
                    powers[info["id"]] = info
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.setdefault((rel, node.name), _decl_line(node, lines))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.setdefault((rel, target.id), node.lineno)
    return powers, symbols


def engine_index():
    global _INDEX
    if _INDEX is None:
        _INDEX = load_engine_index()
    return _INDEX


def _symbol_pointer(symbols, rel, symbol, note=""):
    return {"file": rel, "line": symbols.get((rel, symbol)), "symbol": symbol, "note": note}


def _extend(bucket, values):
    for value in values:
        if value and value not in bucket:
            bucket.append(value)


def resolve_encounter(encounter, run_monsters, catalogs):
    powers = []
    mechanics = []
    monsters = []
    for cat in catalogs:
        if not cat or not encounter:
            continue
        row = (cat.get("encounters") or {}).get(encounter) or {}
        _extend(powers, row.get("powers") or [])
        _extend(mechanics, row.get("mechanics") or [])
        _extend(monsters, row.get("monsters") or [])
    _extend(monsters, run_monsters or [])
    for mid in monsters:
        for cat in catalogs:
            if not cat:
                continue
            row = (cat.get("monsters") or {}).get(mid) or {}
            _extend(powers, row.get("powers") or [])
            _extend(mechanics, row.get("mechanics") or [])
    if encounter and encounter in ENCOUNTER_SETUP:
        _extend(mechanics, ["encounter_setup"])
    if encounter and encounter in ROTATING_START:
        _extend(mechanics, ["rotating_start"])
    if any(pid in _BACK_ATTACK for pid in powers):
        _extend(mechanics, ["back_attack_always"])
    return sorted(powers), sorted(mechanics), sorted(monsters)


def _encounter_key(raw):
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return _norm_enc(raw.strip()) or raw.strip()


def _is_num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def gap_direction(fight):
    """``optimistic``：真机掉血 > p95。``pessimistic``：真机掉血 < p5。端点上不是缺口。"""
    if not isinstance(fight, dict) or fight.get("likely_sim_gap") is not True:
        return None
    real = fight.get("real_hp_lost")
    p5 = fight.get("p5")
    p95 = fight.get("p95")
    if not (_is_num(real) and _is_num(p5) and _is_num(p95)):
        return "unknown_direction"
    above = real > p95
    below = real < p5
    if above and not below:
        return "optimistic"
    if below and not above:
        return "pessimistic"
    return "unknown_direction"


def _blank():
    return {"compared": 0, "optimistic": 0, "pessimistic": 0, "unknown_direction": 0}


def _remember(bucket, value, key):
    if isinstance(value, str) and value and value not in bucket[key]:
        bucket[key].append(value)


def _floor_number(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def monsters_from_run(run):
    """归一化后的一局里，每一场战斗的怪物 ID。对不上的层不加进来。"""
    found = {}
    for floor in run.get("route") or []:
        if not isinstance(floor, dict):
            continue
        kind, _room, encounter, _reason = _classify_floor(floor)
        if kind != "fight" or not encounter:
            continue
        ids = found.setdefault(encounter, [])
        for room in floor.get("rooms") or []:
            if not isinstance(room, dict):
                continue
            for raw in room.get("monster_ids") or []:
                mid = _norm_monster(raw)
                if mid and mid not in ids:
                    ids.append(mid)
    return found


def monsters_from_reports(reports):
    merged = {}
    notes = []
    seen = {}
    for report in reports:
        raw = report.get("real_path")
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = os.path.abspath(os.path.expanduser(raw.strip()))
        if path in seen:
            found = seen[path]
        else:
            if not os.path.isfile(path):
                notes.append(
                    "读不到真对局，怪物 ID 没接上 / real run was not read, so monster ids were not attached: "
                    + path
                )
                seen[path] = {}
                continue
            try:
                doc = load_path(path)
            except SaveImportError:
                notes.append(
                    "真对局读不开，怪物 ID 没接上 / the real run could not be read, so monster ids were not attached: "
                    + path
                )
                seen[path] = {}
                continue
            run = doc.get("run") if isinstance(doc, dict) else None
            found = monsters_from_run(run) if isinstance(run, dict) and doc.get("kind") == "run" else {}
            if not found and doc.get("kind") != "run":
                notes.append(
                    "真对局不是一局记录，怪物 ID 没接上 / real_path is not one run, so monster ids were not attached: "
                    + path
                )
            seen[path] = found
        for encounter, ids in found.items():
            bucket = merged.setdefault(encounter, [])
            _extend(bucket, ids)
    return merged, notes


def _rate(count, total):
    if total <= 0:
        return 0.0
    return count / total


def _lean(optimistic, pessimistic, optimistic_rate, pessimistic_rate):
    if optimistic > 0 and pessimistic > 0 and optimistic_rate == pessimistic_rate:
        return "tie", optimistic_rate
    if optimistic_rate > pessimistic_rate and optimistic > 0:
        return "optimistic", optimistic_rate
    if pessimistic_rate > optimistic_rate and pessimistic > 0:
        return "pessimistic", pessimistic_rate
    if optimistic > 0:
        return "optimistic", optimistic_rate
    if pessimistic > 0:
        return "pessimistic", pessimistic_rate
    return "unknown", 0.0


def _code_for_power(pid, powers, symbols):
    hit = powers.get(pid)
    if hit:
        code = [{"file": hit["file"], "line": hit["line"], "symbol": hit["class"], "note": ""}]
        extra = _EXTRA_POINTERS.get(pid)
        if extra:
            rel, symbol, note = extra
            code.append(_symbol_pointer(symbols, rel, symbol, note))
        return code, hit, False
    return [_symbol_pointer(symbols, "sts2sim/enemies.py", "take_turn", "unimplemented; stacks only")], None, True


def _code_for_mechanic(mid, symbols):
    spec = _MECHANICS.get(mid)
    if not spec:
        return [], {"label_zh": mid, "label_en": mid}
    code = [_symbol_pointer(symbols, rel, symbol) for rel, symbol in spec["symbols"]]
    return code, spec


def _default_code():
    return [{"file": rel, "line": None, "symbol": "", "note": ""} for rel in _MODEL_FILES]


def _row_from_counts(kind, pid, counts, label_zh, label_en, encounters, code, unimplemented=False):
    optimistic_rate = _rate(counts["optimistic"], counts["compared"])
    pessimistic_rate = _rate(counts["pessimistic"], counts["compared"])
    lean, rate = _lean(counts["optimistic"], counts["pessimistic"], optimistic_rate, pessimistic_rate)
    row = {
        "kind": kind,
        "id": pid,
        "label_zh": label_zh,
        "label_en": label_en,
        "compared": counts["compared"],
        "gaps": counts["optimistic"] + counts["pessimistic"] + counts["unknown_direction"],
        "optimistic": counts["optimistic"],
        "pessimistic": counts["pessimistic"],
        "unknown_direction": counts["unknown_direction"],
        "optimistic_rate": optimistic_rate,
        "pessimistic_rate": pessimistic_rate,
        "lean": lean,
        "rate": rate,
        "encounters": sorted(encounters),
        "code": code,
        "unimplemented": unimplemented,
    }
    return row


def _ranked(rows, direction, min_compared):
    picked = [row for row in rows if row["compared"] >= min_compared and row[direction] > 0]
    picked.sort(key=lambda row: (-row[direction + "_rate"], -row[direction], row["id"]))
    return picked


def triage_reports(reports, *, catalog=None, codex=None, run_monsters=None, min_compared=1, index=None):
    """纯汇总。``reports`` 是已经读入的校准对象。不读盘，不写盘。"""
    catalog = catalog or empty_catalog()
    catalogs = [catalog, codex]
    monsters = run_monsters or {}
    if index is None:
        index = engine_index()
    powers_index, symbols = index
    enc_counts = {}
    meta = {}
    totals = _blank()
    totals["unmatched"] = 0
    totals["not_a_fight"] = 0
    for report in reports:
        for fight in report.get("fights") or []:
            if not isinstance(fight, dict):
                continue
            status = fight.get("status")
            if status == "unmatched":
                totals["unmatched"] += 1
                continue
            if status == "not_a_fight":
                totals["not_a_fight"] += 1
                continue
            if status != "compared":
                continue
            key = _encounter_key(fight.get("encounter"))
            bucket = enc_counts.setdefault(key, _blank())
            info = meta.setdefault(key, {"rooms": [], "floors": []})
            bucket["compared"] += 1
            totals["compared"] += 1
            direction = gap_direction(fight)
            if direction:
                bucket[direction] += 1
                totals[direction] += 1
            _remember(info, fight.get("room") if isinstance(fight.get("room"), str) else "", "rooms")
            floor = _floor_number(fight.get("floor"))
            if floor is not None and floor not in info["floors"]:
                info["floors"].append(floor)
    encounters = []
    power_counts = {}
    for key, counts in enc_counts.items():
        info = meta[key]
        info["rooms"] = sorted(info["rooms"])
        info["floors"] = sorted(info["floors"])
        powers, mechanics, mids = resolve_encounter(key, monsters.get(key), catalogs)
        shown = key or "—"
        if powers or mechanics:
            code = []
            for pid in powers:
                pointers, _hit, _missing = _code_for_power(pid, powers_index, symbols)
                for pointer in pointers:
                    if pointer not in code:
                        code.append(pointer)
            for mid in mechanics:
                pointers, _spec = _code_for_mechanic(mid, symbols)
                for pointer in pointers:
                    if pointer not in code:
                        code.append(pointer)
        else:
            code = _default_code()
        optimistic_rate = _rate(counts["optimistic"], counts["compared"])
        pessimistic_rate = _rate(counts["pessimistic"], counts["compared"])
        lean, rate = _lean(counts["optimistic"], counts["pessimistic"], optimistic_rate, pessimistic_rate)
        row = {
            "kind": "encounter",
            "id": key,
            "label_zh": shown,
            "label_en": shown,
            "encounter": shown,
            "rooms": info["rooms"],
            "floors": info["floors"],
            "monsters": mids,
            "powers": powers,
            "mechanics": mechanics,
            "compared": counts["compared"],
            "gaps": counts["optimistic"] + counts["pessimistic"] + counts["unknown_direction"],
            "optimistic": counts["optimistic"],
            "pessimistic": counts["pessimistic"],
            "unknown_direction": counts["unknown_direction"],
            "optimistic_rate": optimistic_rate,
            "pessimistic_rate": pessimistic_rate,
            "lean": lean,
            "rate": rate,
            "encounters": [shown] if shown != "—" else [],
            "code": code,
            "unimplemented": any(
                _code_for_power(pid, powers_index, symbols)[2] for pid in powers
            ),
        }
        encounters.append(row)
        for pid in powers:
            slot = power_counts.setdefault(("power", pid), (_blank(), []))
            for name in _COUNT_KEYS:
                slot[0][name] += counts[name]
            if key not in slot[1]:
                slot[1].append(key)
        for mid in mechanics:
            slot = power_counts.setdefault(("mechanic", mid), (_blank(), []))
            for name in _COUNT_KEYS:
                slot[0][name] += counts[name]
            if key not in slot[1]:
                slot[1].append(key)
    encounters.sort(key=lambda row: row["id"])
    by_power = []
    for (kind, pid), (counts, enc_ids) in power_counts.items():
        if kind == "power":
            pointers, hit, missing = _code_for_power(pid, powers_index, symbols)
            label_zh = hit["label_zh"] if hit else pid
            label_en = hit["label_en"] if hit else pid
            by_power.append(_row_from_counts(
                "power", pid, counts, label_zh, label_en, enc_ids, pointers, missing,
            ))
        else:
            pointers, spec = _code_for_mechanic(pid, symbols)
            by_power.append(_row_from_counts(
                "mechanic", pid, counts, spec["label_zh"], spec["label_en"], enc_ids, pointers, False,
            ))
    by_power.sort(key=lambda row: (-row["rate"], -(row["optimistic"] + row["pessimistic"]), _KIND_RANK[row["kind"]], row["id"]))
    floor_min = min_compared if isinstance(min_compared, int) and not isinstance(min_compared, bool) else 1
    floor_min = max(floor_min, 1)
    optimistic = _ranked(encounters, "optimistic", floor_min)
    pessimistic = _ranked(encounters, "pessimistic", floor_min)
    top = []
    for row in by_power:
        if row["compared"] >= floor_min and (row["optimistic"] or row["pessimistic"]):
            top.append(row)
    for row in encounters:
        if row["powers"] or row["mechanics"]:
            continue
        if row["compared"] >= floor_min and (row["optimistic"] or row["pessimistic"]):
            top.append(row)
    top.sort(key=lambda row: (
        -row["rate"],
        -(row["optimistic"] + row["pessimistic"]),
        _KIND_RANK[row["kind"]],
        row["id"],
    ))
    gaps = totals["optimistic"] + totals["pessimistic"] + totals["unknown_direction"]
    return {
        "ok": True,
        "read_only": True,
        "v": 1,
        "rule": {
            "optimistic": "likely_sim_gap and real_hp_lost > p95",
            "pessimistic": "likely_sim_gap and real_hp_lost < p5",
            "ignored": "unmatched and not_a_fight; a value on p5 or p95 is not outside",
        },
        "min_compared": floor_min,
        "counts": {
            "compared": totals["compared"],
            "gaps": gaps,
            "optimistic": totals["optimistic"],
            "pessimistic": totals["pessimistic"],
            "unknown_direction": totals["unknown_direction"],
            "unmatched": totals["unmatched"],
            "not_a_fight": totals["not_a_fight"],
        },
        "encounters": {
            "all": encounters,
            "optimistic": optimistic,
            "pessimistic": pessimistic,
        },
        "by_power": by_power,
        "top_gaps": top,
    }


def analyze(paths, catalog_path="", min_compared=1):
    reports, sources, notes = load_reports(paths, catalog_path)
    catalog = load_catalog(catalog_path)
    codex, codex_note = load_codex_catalog()
    if codex_note:
        notes.append(codex_note)
    run_monsters, run_notes = monsters_from_reports(reports)
    notes.extend(run_notes)
    body = triage_reports(
        reports,
        catalog=catalog,
        codex=codex,
        run_monsters=run_monsters,
        min_compared=min_compared,
    )
    body["sources"] = []
    seen = []
    for path in sources:
        if path not in seen:
            seen.append(path)
    for path in seen:
        body["sources"].append({"path": os.path.realpath(path), "name": os.path.basename(path)})
    body["catalog"] = os.path.realpath(catalog_path) if catalog_path else None
    body["codex"] = codex is not None
    body["notes"] = notes
    return body


def _md_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _fmt_ratio(count, total):
    if total <= 0:
        return "—"
    pct = 100.0 * count / total
    if abs(pct - round(pct)) < 1e-9:
        shown = str(round(pct))
    else:
        shown = f"{pct:.1f}"
    return f"{count}/{total} ({shown}%)"


def _fmt_code(code):
    if not code:
        return "—"
    parts = []
    for item in code:
        if item.get("line"):
            bit = f"{item['file']}:{item['line']}"
        else:
            bit = item["file"]
        if item.get("symbol"):
            bit += " " + item["symbol"]
        if item.get("note"):
            bit += " (" + item["note"] + ")"
        parts.append(bit)
    return ", ".join(parts)


def _fmt_tags(powers, mechanics, monsters=None):
    bits = []
    if powers:
        bits.append(", ".join(powers))
    if mechanics:
        bits.append(", ".join(mechanics))
    if monsters:
        bits.append("monsters: " + ", ".join(monsters))
    return "; ".join(bits) if bits else "—"


def _table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return lines


def _encounter_table(rows, direction):
    headers = [
        "#",
        "遭遇 / encounter",
        "偏乐观 / optimistic",
        "偏悲观 / pessimistic",
        "对上 / compared",
        "这一侧 / this side",
        "能力与机制 / powers and mechanics",
        "代码 / code",
    ]
    body = []
    for i, row in enumerate(rows, 1):
        body.append([
            i,
            row["encounter"],
            row["optimistic"],
            row["pessimistic"],
            row["compared"],
            _fmt_ratio(row[direction], row["compared"]),
            _fmt_tags(row["powers"], row["mechanics"], row.get("monsters")),
            _fmt_code(row["code"]),
        ])
    return _table(headers, body)


def _power_table(rows):
    headers = [
        "#",
        "种类 / kind",
        "能力或机制 / power or mechanic",
        "名称 / name",
        "偏向 / lean",
        "比例 / rate",
        "遭遇 / encounters",
        "代码 / code",
    ]
    body = []
    for i, row in enumerate(rows, 1):
        name = row["label_zh"]
        if row["label_en"] and row["label_en"] != row["label_zh"]:
            name = f"{row['label_zh']} / {row['label_en']}"
        body.append([
            i,
            row["kind"],
            row["id"],
            name,
            row["lean"],
            _fmt_ratio(row["optimistic"] if row["lean"] != "pessimistic" else row["pessimistic"], row["compared"]),
            ", ".join(row["encounters"]) or "—",
            _fmt_code(row["code"]),
        ])
    return _table(headers, body)


def _section(lines, title, rows, render, top, empty):
    lines.append("## " + title)
    lines.append("")
    if not rows:
        lines.append(empty)
        lines.append("")
        return
    shown = rows[:top]
    lines.extend(render(shown))
    left = len(rows) - len(shown)
    if left:
        lines.append("")
        lines.append(f"还有 {left} 条没列出（`--top`）。 / {left} more not shown (`--top`).")
    lines.append("")


def render_markdown(body, top=10):
    if isinstance(top, int) and not isinstance(top, bool) and top >= 1:
        limit = top
    else:
        limit = 1
    counts = body["counts"]
    names = [item["name"] for item in body.get("sources") or []]
    listed = ", ".join(names) if names else "—"
    codex = "有 / yes" if body.get("codex") else "无 / none"
    catalog = body.get("catalog") or "—"
    lines = [
        "# 模拟缺口分诊 / Sim-gap triage",
        "",
        (
            "只读。不改模拟器、种子或 AI。输入是校准 JSON（`tools/calibrate.py --json`）。"
            "一场对上的战斗里，`likely_sim_gap` 为真并且真机掉血高于 p95，记成模拟偏乐观（真机掉得更多）；"
            "低于 p5 记成模拟偏悲观（真机掉得更少）。落在 p5 或 p95 上不算外面。对不上的层、不是战斗的层，不进分母。"
        ),
        "",
        (
            "*Read-only. It does not change the simulator, seeds, or AI. Input is calibration JSON "
            "(`tools/calibrate.py --json`). On a compared fight, `likely_sim_gap` with real HP lost above p95 "
            "means the sim was too optimistic (the real fight lost more). Below p5 means too pessimistic "
            "(the real fight lost less). A value on p5 or p95 is not outside. Unmatched floors and floors that "
            "are not fights stay out of the denominator.*"
        ),
        "",
        "## 样本 / Sample",
        "",
        f"- 报告 / reports: {len(names)}（{listed}）",
        (
            f"- 对上的战斗 / compared: {counts['compared']}"
        ),
        (
            f"- 疑似缺口 / likely_sim_gap: {counts['gaps']}"
            f"（偏乐观 / too optimistic {counts['optimistic']}，"
            f"偏悲观 / too pessimistic {counts['pessimistic']}，"
            f"方向不明 / unknown {counts['unknown_direction']}）"
        ),
        f"- 对不上 / unmatched: {counts['unmatched']}；不是战斗 / not a fight: {counts['not_a_fight']}",
        f"- 至少对上几场才进排名 / minimum compared fights in a ranking: {body.get('min_compared')}",
        f"- 名册 / catalog: {catalog}",
        f"- 本机怪物数据 / local codex: {codex}",
        "",
    ]

    def show_optimistic(rows):
        return _encounter_table(rows, "optimistic")

    def show_pessimistic(rows):
        return _encounter_table(rows, "pessimistic")

    _section(
        lines,
        "模拟最常偏乐观的遭遇 / Encounters where the sim is most often too optimistic",
        body["encounters"]["optimistic"],
        show_optimistic,
        limit,
        "这一侧没有疑似缺口。 / No likely gaps on this side.",
    )
    _section(
        lines,
        "模拟最常偏悲观的遭遇 / Encounters where the sim is most often too pessimistic",
        body["encounters"]["pessimistic"],
        show_pessimistic,
        limit,
        "这一侧没有疑似缺口。 / No likely gaps on this side.",
    )
    powered = [
        row for row in body["by_power"]
        if row["compared"] >= body.get("min_compared", 1) and (row["optimistic"] or row["pessimistic"])
    ]
    _section(
        lines,
        "按能力与机制 / By enemy power and mechanic",
        powered,
        _power_table,
        limit,
        "没有对上能力或机制。 / No power or mechanic was attached to a gap.",
    )
    _section(
        lines,
        "最可疑的模拟模型缺口 / Top suspected sim-model gaps",
        body["top_gaps"],
        _power_table,
        limit,
        "没有疑似缺口。 / No likely sim gap.",
    )
    lines.extend([
        "## 模型代码 / Where the model lives",
        "",
        "- `sts2sim/powers_enemy.py` — 敌人专属能力（紧缠、吮吸、后方攻击等）。 / Enemy-only powers (Constrict, Suck, BackAttack, and the rest).",
        "- `sts2sim/powers.py` — 双方都会用到的能力，含荆棘。 / Powers used on either side, including Thorns.",
        "- `sts2sim/enemies.py` — 意图、召唤不生成新敌人、Status 塞晕眩、遭遇开场字段；没实现的能力只记层数。 / Intents, summon not adding enemies, a Status intent adding Dazed, encounter start flags; an unimplemented power only stores stacks.",
        "- `sts2sim/ai/base.py` `mechanic_adjust` — 可选的荆棘、已有格挡、多敌人伤害修正，默认关。 / Optional thorns, block-already-there, and multi-enemy incoming adjustment. Off by default.",
        "- `sts2sim/ai/heuristic.py` — `mechanic_aware` 开关。 / The `mechanic_aware` switch.",
        "",
    ])
    notes = body.get("notes") or []
    if notes:
        lines.append("## 备注 / Notes")
        lines.append("")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dump(payload, fh):
    json.dump(payload, fh, ensure_ascii=False, indent=1)
    fh.write("\n")


def _refuse_output(dest, sources):
    if not dest or dest == "-":
        return None
    try:
        kept = refuse_save_write(dest, sources[0] if sources else None)
    except SaveImportError as exc:
        raise TriageError("refuse_write", path=dest) from exc
    dest_real = os.path.realpath(kept)
    for src in sources:
        if os.path.isfile(src) and os.path.realpath(src) == dest_real:
            raise TriageError("refuse_write", path=dest_real)
    return kept


def _write(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main(argv=None):
    _configure_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="校准 JSON，或放着这些 JSON 的目录")
    ap.add_argument("--catalog", default="", help="遭遇 → 能力 / 机制的 JSON 名册")
    ap.add_argument("--top", type=int, default=10, help="Markdown 每一节最多几行")
    ap.add_argument("--min-compared", type=int, default=1, help="少于此数的遭遇不进排名")
    ap.add_argument("--json", default="", help="写出汇总 JSON。- 表示只打到标准输出")
    ap.add_argument("--out", default="", help="把 Markdown 写到这个文件")
    args = ap.parse_args(argv)
    try:
        files = _iter_files(args.paths, args.catalog)
        out_path = _refuse_output(args.out, files)
        json_path = None if args.json == "-" else _refuse_output(args.json, files)
        if out_path and json_path and os.path.realpath(out_path) == os.path.realpath(json_path):
            raise TriageError("refuse_write", path=out_path)
        body = analyze(args.paths, args.catalog, args.min_compared)
    except TriageError as err:
        print(_message(err), file=sys.stderr)
        return 2
    text = render_markdown(body, args.top)
    if args.json == "-":
        _dump(body, sys.stdout)
    else:
        if json_path:
            _write(json_path, json.dumps(body, ensure_ascii=False, indent=1) + "\n")
        if out_path:
            _write(out_path, text)
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
