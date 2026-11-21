"""Custom cards for the combat engine, stored as a data-only user mod.

The editor reuses ``sts2sim.modfmt.schema`` (the same card fields, ops and
templates as a YAML mod). It does not load hooks, and it refuses ``py``
effects and expressions that reach past the names the schema already allows.
Templates are expanded to ops in ``cards.yaml`` because the combat engine
runs ops. The editor reopens the form the author saved in ``library.json``.

Nothing in an imported file is executed.
"""
from __future__ import annotations

import ast
import json
import os
import re

import yaml

from . import expr
from .modfmt import schema

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,27}$")
CARD_RE = schema._ID_RE
MAX_CARDS = 24
MAX_EFFECTS = 40
MAX_DEPTH = 8
MAX_IMPORT = 1_000_000
LIBRARY_FILE = "library.json"
ENCOUNTERS = ("DUMMY", "SYN_BRUTE")
BLOCKED_OPS = frozenset({"py"})

# Calls an expression in the card editor may make. Attribute access is refused.
SAFE_CALLS = frozenset(name for name, fn in expr.BASE.items() if callable(fn))
COMBAT_NAMES = frozenset(set(expr.BASE) | {"T", "P", "C", "card", "ctx", "upgraded", "amount", "n", "X"})
_NEST = ("then", "else", "do", "each_hit")
_OPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd, ast.MatMult,
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
)


def supported_ops():
    """Ops the combat engine runs. ``py`` is omitted on purpose."""
    from .cards import OPS
    return tuple(name for name in OPS if name not in BLOCKED_OPS)


def known_power_ids():
    from . import powers as _powers  # noqa: F401  (registers POWER_TYPES)
    from . import powers_enemy as _enemy  # noqa: F401
    from .core import POWER_TYPES
    return tuple(sorted(POWER_TYPES))


def public_schema():
    """The same tables as the mod editor, without the ``py`` op."""
    ops = {name: params for name, params in schema.OPS.items() if name not in BLOCKED_OPS}
    return {
        "ops": _spec(ops),
        "templates": _spec(schema.TEMPLATES),
        "target_specs": list(schema.TARGET_SPECS),
        "once": list(schema.ONCE),
        "rarities": list(schema.RARITIES),
        "types": list(schema.TYPES),
        "targets": list(schema.TARGETS),
        "keywords": [key for key in schema.KEYWORDS if key != "Unplayable"],
        "expr_names": sorted(schema.EXPR_NAMES),
        "powers": list(known_power_ids()),
        "encounters": list(ENCOUNTERS),
        "supported_ops": list(supported_ops()),
    }


def _spec(table):
    out = {}
    for name, params in table.items():
        out[name] = [
            {"name": key, "kind": value[0], "required": bool(value[1]),
             "default": value[2] if len(value) > 2 else None}
            for key, value in params.items()
        ]
    return out


def blank():
    """A new library. One attack, four copies, the training dummy."""
    return {
        "name": "custom_cards",
        "title": "Custom cards",
        "character": {"id": "Hero", "name": "Hero", "hp": 70, "energy": 3},
        "cards": [_blank_card()],
        "deck": [{"id": "JAB", "count": 4, "upgrade": False}],
        "seed": 1,
        "max_turns": 8,
        "fights": 1,
        "encounter": "DUMMY",
    }


def _blank_card():
    return {
        "id": "JAB", "name": "Jab", "type": "Attack", "rarity": "Common", "cost": 1,
        "target": "AnyEnemy", "keywords": [], "vars": {"dmg": 6},
        "upgrade": {"vars": {"dmg": 9}}, "effects": [{"op": "damage", "amount": "dmg"}],
        "text": "", "pool": True, "ai": {},
    }


class CardLibraryError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _problems_of(items):
    return [{"where": where, "zhs": zh, "en": en} for where, zh, en in items]


def _as_mod(library):
    """Author form → the dict ``schema.validate`` already understands."""
    character = library.get("character") if isinstance(library.get("character"), dict) else {}
    cid = str(character.get("id") or "Hero")
    cards = []
    for raw in library.get("cards") or []:
        if isinstance(raw, dict):
            card = dict(raw)
            card.setdefault("upgrade", {})
            if not isinstance(card["upgrade"], dict):
                card["upgrade"] = {}
            card["upgrade"].setdefault("vars", {})
            card.setdefault("keywords", [])
            card.setdefault("vars", {})
            card.setdefault("effects", [])
            cards.append(card)
    return {
        "name": str(library.get("name") or ""),
        "title": library.get("title") or library.get("name") or "",
        "prefix": "Custom",
        "characters": {
            cid: {
                "id": cid,
                "name": character.get("name") or cid,
                "hp": character.get("hp", 70),
                "energy": character.get("energy", 3),
                "gold": 99,
                "starting_deck": [],
                "relics": [],
            },
        },
        "cards": cards,
        "powers": [],
        "relics": [],
        "potions": [],
        "helpers": {},
        "ai_values": {},
        "hooks": None,
        "fullrun_hooks": None,
        "files": {},
    }


def _walk(effects, visit, depth=0):
    if effects is None:
        return
    if not isinstance(effects, list):
        visit(None, depth, "not_list")
        return
    if len(effects) > MAX_EFFECTS:
        visit(None, depth, "too_many")
        return
    if depth > MAX_DEPTH:
        visit(None, depth, "too_deep")
        return
    for effect in effects:
        visit(effect, depth, None)
        if isinstance(effect, dict):
            for key in _NEST:
                if key in effect:
                    _walk(effect.get(key), visit, depth + 1)


_AST_OK = (
    ast.Expression, ast.Name, ast.Constant, ast.Load, ast.Call, ast.keyword,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Tuple, ast.List, *_OPS,
)


def _expr_issue(text, scope):
    """Refuse attribute access and calls the combat engine does not provide.

    ``schema.validate`` allows every name in ``EXPR_NAMES``. Some of those
    names exist only in the full-run engine. A card test runs the combat
    engine, so those names are rejected here. ``().__class__`` has no names
    and is rejected because it uses an attribute.
    """
    if not isinstance(text, str):
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            return "attribute"
        if isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in SAFE_CALLS:
                return "call"
        if isinstance(node, (ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.expr_context)):
            continue
        if type(node) not in _AST_OK:
            return "unsupported"
    names, _bad = schema._names_in(text)
    if names is None:
        return None
    if any(name not in scope and name not in COMBAT_NAMES for name in names):
        return "name"
    return None


def _extra_problems(mod):
    """Problems the shared schema does not state in card-editor terms."""
    problems = []
    warnings = []

    def add(where, zh, en):
        problems.append((where, zh, en))

    def warn(where, zh, en):
        warnings.append((where, zh, en))

    if mod.get("hooks") or mod.get("fullrun_hooks"):
        add("mod.yaml", "卡牌编辑器不加载 Python 钩子。", "The card editor does not load Python hooks.")
    known = set(known_power_ids())
    scope = set()

    def visit(effect, depth, flag):
        if flag == "not_list":
            add("effects", "效果必须是列表。", "Effects must be a list.")
            return
        if flag == "too_many":
            add("effects", f"一张牌最多 {MAX_EFFECTS} 条效果。", f"A card can have at most {MAX_EFFECTS} effects.")
            return
        if flag == "too_deep":
            add("effects", "效果嵌套太深。", "Effects are nested too deeply.")
            return
        if not isinstance(effect, dict):
            return
        name = effect.get("op") or effect.get("template")
        if name in BLOCKED_OPS or effect.get("op") == "py" or effect.get("fn"):
            add("effects", "py 效果会运行 Python，卡牌编辑器不提供。请改用列表里的效果。",
                "A py effect runs Python. The card editor does not offer it. Use an effect from the list.")
        if effect.get("once"):
            warn("effects", "once 会保存，但战斗测试不会按它少结算。每次打出都会执行。",
                 "once is saved, but the combat test does not skip repeats. The effect runs on every play.")
        spec = schema.OPS.get(effect.get("op")) or schema.TEMPLATES.get(effect.get("template")) or {}
        expr_keys = {key for key, value in spec.items() if value and value[0] == "expr"}
        expr_keys.add("if")
        for key, value in effect.items():
            if key not in expr_keys:
                continue
            issue = _expr_issue(value, scope) if isinstance(value, str) else None
            if issue == "attribute":
                add("effects", "表达式不能读取属性。只能写数字、vars 里的名字，以及列出的函数。",
                    "An expression cannot read attributes. Use a number, a var, or a listed function.")
            elif issue == "name":
                add("effects", "表达式里有战斗测试用不了的名字。整局引擎里的名字不会在这里生效。",
                    "The expression uses a name the combat test does not provide. Full-run names do not run here.")
            elif issue in ("call", "unsupported"):
                add("effects", "这个表达式用了战斗引擎不支持的写法。",
                    "This expression uses a form the combat engine does not support.")
        power = effect.get("power")
        if isinstance(power, str) and power and power not in known:
            shown = power if re.fullmatch(r"[A-Za-z0-9_]{1,40}", power) else ""
            if shown:
                warn("effects", f"能力 {shown} 不是战斗引擎里已实现的能力。测试只会记下层数，不会触发它的效果。",
                     f"Power {shown} is not implemented by the combat engine. The test stores stacks and does not run a trigger.")
            else:
                warn("effects", "有一个能力 id 不是战斗引擎里已实现的能力。测试只会记下层数，不会触发它的效果。",
                     "A power id is not implemented by the combat engine. The test stores stacks and does not run a trigger.")

    for card in mod.get("cards") or []:
        where = f"card {card.get('id') or '?'}"
        scope = set(card.get("vars") or ())
        _walk(card.get("effects"), visit)
        upgrade = card.get("upgrade") if isinstance(card.get("upgrade"), dict) else {}
        if upgrade.get("effects") is not None:
            _walk(upgrade.get("effects"), visit)
        bonus = (card.get("ai") or {}).get("bonus") if isinstance(card.get("ai"), dict) else None
        if bonus is not None and not isinstance(bonus, (int, float)):
            add(where, "AI 加分必须是数字。", "The AI bonus must be a number.")
    if len(mod.get("cards") or []) > MAX_CARDS:
        add("cards", f"最多 {MAX_CARDS} 张牌。", f"At most {MAX_CARDS} cards.")
    return problems, warnings


def _library_shape(raw):
    """Reject a body that is not the editor's object. Does not echo values."""
    if not isinstance(raw, dict):
        raise CardLibraryError("body")
    for key in ("path", "filename", "file", "dir", "directory", "dest", "folder", "hooks", "fullrun_hooks"):
        if key in raw:
            raise CardLibraryError("refused")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise CardLibraryError("name")
    title = raw.get("title") or name
    if not isinstance(title, str) or len(title) > 80:
        raise CardLibraryError("title")
    character = raw.get("character")
    if not isinstance(character, dict):
        raise CardLibraryError("character")
    cid = character.get("id")
    if not isinstance(cid, str) or not CARD_RE.match(cid):
        raise CardLibraryError("character")
    cname = character.get("name") or cid
    if not isinstance(cname, str) or len(cname) > 80:
        raise CardLibraryError("character")
    for field, limit in (("hp", 999), ("energy", 10)):
        value = character.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > limit:
            raise CardLibraryError("character")
    if not isinstance(raw.get("cards"), list) or not raw["cards"]:
        raise CardLibraryError("cards")
    return {
        "name": name,
        "title": title.strip() or name,
        "character": {"id": cid, "name": cname.strip() or cid, "hp": int(character["hp"]),
                      "energy": int(character["energy"])},
        "cards": raw["cards"],
        "deck": raw.get("deck") if isinstance(raw.get("deck"), list) else [],
        "seed": raw.get("seed", 1),
        "max_turns": raw.get("max_turns", 8),
        "fights": raw.get("fights", 1),
        "encounter": raw.get("encounter") or "DUMMY",
    }


def _check_numbers(library):
    problems = []
    seed = library.get("seed", 1)
    turns = library.get("max_turns", 8)
    fights = library.get("fights", 1)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 or seed > 2_147_483_647:
        problems.append(("", "种子必须是 0 到 2147483647 的整数。", "Seed must be an integer from 0 to 2147483647."))
    if isinstance(turns, bool) or not isinstance(turns, int) or turns < 1 or turns > 30:
        problems.append(("", "回合上限必须是 1 到 30 的整数。", "Max turns must be an integer from 1 to 30."))
    if isinstance(fights, bool) or not isinstance(fights, int) or fights < 1 or fights > 8:
        problems.append(("", "卡牌测试一次最多 8 场。", "A card test runs at most 8 fights."))
    encounter = library.get("encounter") or "DUMMY"
    if encounter not in ENCOUNTERS:
        problems.append(("", "卡牌测试只能打训练木桩，或合成蛮兵（不是游戏遭遇）。",
                         "A card test can run the training dummy or the synthetic brute. That brute is not a game encounter."))
    return problems


def validate_library(raw):
    """Return ``{ok, problems, warnings, library}``. ``library`` is set when the shape is usable."""
    try:
        library = _library_shape(raw)
    except CardLibraryError as exc:
        return {"ok": False, "problems": [_shape_problem(exc.code)], "warnings": [], "library": None}
    mod = _as_mod(library)
    try:
        files = schema.dump_mod_dir(mod)
        files = {name: text for name, text in files.items() if not str(name).endswith(".py")}
        normalized = schema.load_mod_files(files)
    except schema.ModFormatError as exc:
        return {"ok": False, "problems": _problems_of(exc.problems), "warnings": [], "library": None}
    except (TypeError, ValueError, KeyError, yaml.YAMLError):
        return {"ok": False, "problems": [("", "这份卡牌数据读不下来。", "This card data could not be read.")],
                "warnings": [], "library": None}
    schema_problems, schema_warnings = schema.validate(normalized, fullrun=False)
    extra, extra_warnings = _extra_problems(normalized)
    number_problems = _check_numbers(library)
    problems = _problems_of(schema_problems + extra + number_problems)
    warnings = _problems_of(schema_warnings + extra_warnings)
    if problems:
        return {"ok": False, "problems": problems, "warnings": warnings, "library": None}
    stored = _public_from_normalized(normalized, library)
    return {"ok": True, "problems": [], "warnings": warnings, "library": stored}


def _shape_problem(code):
    text = {
        "body": ("请求应该是一份卡牌库。", "The request should be a card library."),
        "refused": ("卡牌编辑器不接受钩子或路径字段。", "The card editor does not accept hooks or path fields."),
        "name": ("名字只能用字母、数字和下划线，最多 28 个字符，并且以字母开头。",
                 "The name must start with a letter and use at most 28 letters, digits and underscores."),
        "title": ("标题太长。", "The title is too long."),
        "character": ("角色需要 id、名字、1 到 999 的生命，以及 1 到 10 的能量。",
                      "The character needs an id, a name, HP from 1 to 999, and energy from 1 to 10."),
        "cards": ("至少要有一张牌。", "Add at least one card."),
    }.get(code, ("这份卡牌数据不能用。", "This card data cannot be used."))
    return {"where": "", "zhs": text[0], "en": text[1]}


def _public_card(card):
    upgrade = card.get("upgrade") if isinstance(card.get("upgrade"), dict) else {}
    ai = card.get("ai") if isinstance(card.get("ai"), dict) else {}
    return {
        "id": card.get("id") or "",
        "name": card.get("name") or card.get("id") or "",
        "type": card.get("type") or "Skill",
        "rarity": card.get("rarity") or "Common",
        "cost": card.get("cost", 1),
        "target": card.get("target") or "Self",
        "keywords": [key for key in (card.get("keywords") or []) if key != "Unplayable"],
        "vars": dict(card.get("vars") or {}),
        "upgrade": {
            "vars": dict(upgrade.get("vars") or {}),
            "cost": upgrade.get("cost"),
            "name": upgrade.get("name") or "",
            "effects": upgrade.get("effects"),
        },
        "effects": list(card.get("effects") or []),
        "text": card.get("text") or "",
        "pool": card.get("pool", True) is not False,
        "ai": {"bonus": ai.get("bonus")} if ai.get("bonus") not in (None, "") else {},
    }


def _public_from_normalized(mod, library):
    character = next(iter(mod["characters"].values()))
    return {
        "name": mod["name"],
        "title": mod.get("title") or mod["name"],
        "character": {
            "id": character["id"],
            "name": character["name"],
            "hp": int(character["hp"]),
            "energy": int(character["energy"]),
        },
        "cards": [_public_card(card) for card in mod["cards"]],
        "deck": _clean_deck(library.get("deck"), [card["id"] for card in mod["cards"]]),
        "seed": int(library.get("seed", 1)) if isinstance(library.get("seed", 1), int) else 1,
        "max_turns": int(library.get("max_turns", 8)) if isinstance(library.get("max_turns", 8), int) else 8,
        "fights": int(library.get("fights", 1)) if isinstance(library.get("fights", 1), int) else 1,
        "encounter": library.get("encounter") if library.get("encounter") in ENCOUNTERS else "DUMMY",
    }


def _clean_deck(rows, card_ids):
    allowed = set(card_ids)
    out = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("id")
        if cid not in allowed:
            continue
        count = row.get("count", 1)
        upgrade = row.get("upgrade", False)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 15:
            continue
        if not isinstance(upgrade, bool):
            continue
        out.append({"id": cid, "count": count, "upgrade": upgrade})
    return out


def expand_effects(effects):
    """Templates → the ops ``cards.run_effects`` actually runs. Nested too."""
    out = []
    for effect in effects or []:
        if not isinstance(effect, dict):
            continue
        if effect.get("template") and not effect.get("op") and effect.get("template") in schema.TEMPLATES:
            expanded = schema.expand_template(effect)
            out.extend(expand_effects(expanded))
            continue
        effect = dict(effect)
        for key in _NEST:
            if isinstance(effect.get(key), list):
                effect[key] = expand_effects(effect[key])
        out.append(effect)
    return out


# The combat engine treats an attack as type "攻击". The editor stores Attack.
_ENGINE_TYPE = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态", "Curse": "诅咒"}


def engine_cards(cards):
    """Card dicts whose effects are ops. The editor form is not this list."""
    written = []
    for card in cards:
        card = dict(card)
        if card.get("type") in _ENGINE_TYPE:
            card["type"] = _ENGINE_TYPE[card["type"]]
        card["effects"] = expand_effects(card.get("effects"))
        upgrade = dict(card.get("upgrade") or {})
        if upgrade.get("effects"):
            upgrade["effects"] = expand_effects(upgrade.get("effects"))
            card["upgrade"] = upgrade
        written.append(card)
    return written


def iter_effects(effects):
    for effect in effects or []:
        if isinstance(effect, dict):
            yield effect
            for key in _NEST:
                yield from iter_effects(effect.get(key))


def contains_blocked(effects):
    for effect in iter_effects(effects):
        if effect.get("op") in BLOCKED_OPS or effect.get("template") == "py" or effect.get("fn"):
            return True
    return False


def prepare_save(raw):
    """Validated library plus the mod files to write. Raises ``CardLibraryError``."""
    checked = validate_library(raw)
    if not checked["ok"] or not checked["library"]:
        raise CardLibraryError("invalid")
    library = checked["library"]
    mod = _as_mod(library)
    mod["cards"] = engine_cards(mod["cards"])
    files = schema.dump_mod_dir(mod)
    files = {name: text for name, text in files.items() if isinstance(name, str) and not name.endswith(".py")}
    if any(name.endswith(".py") for name in files):
        raise CardLibraryError("py")
    files[LIBRARY_FILE] = json.dumps(library, ensure_ascii=False, indent=1)
    return library, files, checked["warnings"]


def read_library_dir(folder):
    """Reopen a saved library. Prefers ``library.json``. Does not execute files."""
    if not os.path.isdir(folder):
        raise CardLibraryError("missing")
    for name in os.listdir(folder):
        if name.endswith(".py"):
            raise CardLibraryError("py")
    library_path = os.path.join(folder, LIBRARY_FILE)
    if os.path.isfile(library_path) and not os.path.islink(library_path):
        try:
            raw = json.loads(_read_text(library_path))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CardLibraryError("read") from exc
        checked = validate_library(raw)
        if not checked["ok"]:
            raise CardLibraryError("invalid")
        return checked["library"]
    try:
        loaded = schema.load_mod_dir(folder)
    except schema.ModFormatError as exc:
        raise CardLibraryError("invalid") from exc
    library = _public_from_normalized(loaded, {"deck": [], "seed": 1, "max_turns": 8, "fights": 1, "encounter": "DUMMY"})
    checked = validate_library(library)
    if not checked["ok"]:
        raise CardLibraryError("invalid")
    return checked["library"]


def _read_text(path):
    size = os.path.getsize(path)
    if size > MAX_IMPORT:
        raise CardLibraryError("big")
    with open(path, encoding="utf-8") as handle:
        return handle.read(MAX_IMPORT + 1)


def library_from_import(filename, data):
    """A ``.zip`` or YAML body → a library that has not been saved yet.

    ``.py`` members and ``py`` effects are refused. The bytes are not executed.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise CardLibraryError("import")
    if len(data) > MAX_IMPORT:
        raise CardLibraryError("big")
    name = str(filename or "").lower()
    if name.endswith(".py"):
        raise CardLibraryError("py")
    try:
        if name.endswith(".zip"):
            loaded = _zip_cards(bytes(data))
        else:
            loaded = _yaml_cards(bytes(data))
    except schema.ModFormatError as exc:
        raise CardLibraryError("invalid") from exc
    except yaml.YAMLError as exc:
        raise CardLibraryError("invalid") from exc
    checked = validate_library(loaded)
    if not checked["ok"]:
        raise CardLibraryError("invalid")
    return checked


def _zip_cards(data):
    import io
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CardLibraryError("import") from exc
    names = [item for item in zf.namelist() if not item.endswith("/")]
    if any(item.endswith((".py", ".dll")) for item in names):
        raise CardLibraryError("py")
    if any(".." in item.replace("\\", "/") or item.startswith(("/", "\\")) for item in names):
        raise CardLibraryError("import")
    tops = [item for item in names if item.endswith("mod.yaml")]
    if tops:
        root = min(tops, key=len)[:-len("mod.yaml")]
        files = {}
        for item in names:
            if not item.startswith(root):
                continue
            rel = item[len(root):]
            if rel.endswith((".yaml", ".yml", ".json")):
                blob = zf.read(item)
                if len(blob) > MAX_IMPORT:
                    raise CardLibraryError("big")
                files[rel] = blob.decode("utf-8")
        loaded = schema.load_mod_files(files)
        return _public_from_normalized(loaded, {"deck": [], "seed": 1, "max_turns": 8, "fights": 1, "encounter": "DUMMY"})
    yaml_names = [item for item in names if item.endswith((".yaml", ".yml"))]
    if len(yaml_names) != 1:
        raise CardLibraryError("import")
    blob = zf.read(yaml_names[0])
    return _cards_to_library(yaml.safe_load(blob.decode("utf-8")))


def _yaml_cards(data):
    text = data.decode("utf-8")
    loaded = yaml.safe_load(text)
    if isinstance(loaded, dict) and "mod.yaml" in loaded:
        return _public_from_normalized(schema.load_mod_files(loaded),
                                      {"deck": [], "seed": 1, "max_turns": 8, "fights": 1, "encounter": "DUMMY"})
    if isinstance(loaded, dict) and isinstance(loaded.get("cards"), list) and loaded.get("name"):
        return loaded
    return _cards_to_library(loaded)


def _cards_to_library(loaded):
    if isinstance(loaded, dict):
        loaded = [loaded]
    if not isinstance(loaded, list) or not loaded:
        raise CardLibraryError("import")
    library = blank()
    library["cards"] = loaded
    first = loaded[0].get("id") if isinstance(loaded[0], dict) else None
    if isinstance(first, str):
        library["deck"] = [{"id": first, "count": 1, "upgrade": False}]
    return library


def deck_rows_for(library, focus_id=None):
    """The test deck. Adds one copy of ``focus_id`` when the deck does not contain it."""
    rows = _clean_deck(library.get("deck"), [card["id"] for card in library["cards"]])
    ids = {row["id"] for row in rows}
    focus = focus_id if focus_id in {card["id"] for card in library["cards"]} else None
    if focus and focus not in ids:
        rows.append({"id": focus, "count": 1, "upgrade": False})
    if not rows and library["cards"]:
        rows.append({"id": library["cards"][0]["id"], "count": 1, "upgrade": False})
    if not rows:
        raise CardLibraryError("deck")
    return rows


def preset_id_for(name):
    preset = f"{name}_try"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", preset):
        raise CardLibraryError("name")
    return preset


def expr_names_cover_safe_calls():
    """The safe call list stays inside the names the schema documents."""
    missing = sorted(SAFE_CALLS - schema.EXPR_NAMES - {"int"})
    return missing
