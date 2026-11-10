"""牌组构建：只读列出模拟器已经认识的牌和遭遇，并把一套牌存成用户预设。

预设的格式和 ``experiments/*.yaml`` 一样，另外带一份 ``user_deck``，
界面开跑时才在这次测试自己的目录里生成一个临时 mod。``extra`` 里每一行是
一场要打的遭遇。没选遭遇时仍是一场训练木桩。不改模拟器的出牌、种子和 AI，
也不写入 ``experiments/``、``mods/`` 或已有的种子和配置。

*Deck builder. Lists cards and encounters the simulator already loads, and
saves a deck as a user preset in the same shape as ``experiments/*.yaml``.
A ``user_deck`` block is turned into a temporary mod inside that one test's
folder when a run starts. Each ``extra`` row is one encounter. With no
encounter chosen, the preset is still one training-dummy fight. Simulator
play, seeds and AI stay as they are. Shipped presets, mods, seeds and configs
are not written.*
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from sts2sim.modloader import BUILTIN, MODS_DIR

MAX_BYTES = 64 * 1024
MAX_COPIES = 15
MAX_ROWS = 40
MAX_CARDS = 60
MAX_FILE = 2_000_000
MAX_ENCOUNTERS = 40
MAX_FIGHTS_EACH = 100
MAX_FIGHTS_TOTAL = 400
# Same ceiling as the New test max-turns control. The default cap is not this
# number: it is read from shipped experiments, or from the runner default.
TURN_LIMIT = 200
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_MOD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
_CARD_ID = re.compile(r"^[A-Za-z0-9_]{1,80}$")
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
_WORDS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_TYPE = {
    "攻击": "Attack", "Attack": "Attack", "attack": "Attack",
    "技能": "Skill", "Skill": "Skill", "skill": "Skill",
    "能力": "Power", "Power": "Power", "power": "Power",
    "状态": "Status", "Status": "Status", "status": "Status",
    "诅咒": "Curse", "Curse": "Curse", "curse": "Curse",
    "任务": "Quest", "Quest": "Quest",
}
_RARITY = {
    "基础": "Basic", "Basic": "Basic",
    "普通": "Common", "Common": "Common",
    "罕见": "Uncommon", "Uncommon": "Uncommon",
    "稀有": "Rare", "Rare": "Rare",
    "先古": "Ancient", "Ancient": "Ancient",
    "状态": "Status", "Status": "Status",
    "诅咒": "Curse", "Curse": "Curse",
    "事件": "Event", "Event": "Event",
    "衍生": "Token", "Token": "Token",
}
_BANNED_FIELDS = ("path", "filename", "file", "dir", "directory", "dest", "folder")
_SKIP_PARTS = {"saves", "history", "SlayTheSpire2", "__pycache__"}
_CACHE: dict = {"sig": None, "cards": []}


class DeckPresetError(Exception):
    """可返回给调用方的失败。params 里只有字段名和数字，没有用户输入的原文。"""

    def __init__(self, code, **params):
        self.code = code
        self.params = {k: v for k, v in params.items() if k in ("field", "expected", "n")}
        super().__init__(code)


def _within(path, root):
    try:
        left = os.path.normcase(os.path.realpath(path))
        right = os.path.normcase(os.path.realpath(root))
        return os.path.normcase(os.path.commonpath([left, right])) == right
    except (OSError, ValueError):
        return False


def _data_dir():
    env = os.environ.get("STS2SIM_GUI_DATA")
    if isinstance(env, str) and env.strip() and "\x00" not in env:
        return env
    from gui import paths
    return paths.DATA_DIR


def _sim_root():
    return os.path.dirname(MODS_DIR)


def presets_dir(create=False):
    """用户预设目录。必须在界面数据目录里，且不能落在 experiments/ 或 mods/ 上。"""
    data = _data_dir()
    if not isinstance(data, str) or not data.strip() or "\x00" in data:
        raise DeckPresetError("path")
    override = os.environ.get("DECKBENCH_PRESETS_DIR")
    raw = override if isinstance(override, str) and override.strip() else os.path.join(data, "presets")
    if "\x00" in raw:
        raise DeckPresetError("path")
    folder = os.path.realpath(raw)
    data_real = os.path.realpath(data)
    experiments = os.path.realpath(os.path.join(_sim_root(), "experiments"))
    mods = os.path.realpath(MODS_DIR)
    if not _within(folder, data_real):
        raise DeckPresetError("path")
    if _within(folder, experiments) or _within(folder, mods):
        raise DeckPresetError("path")
    if os.path.normcase(folder) == os.path.normcase(os.path.realpath(_sim_root())):
        raise DeckPresetError("path")
    if set(Path(folder).parts) & _SKIP_PARTS:
        raise DeckPresetError("path")
    if create:
        os.makedirs(folder, exist_ok=True)
        folder = os.path.realpath(folder)
        if not os.path.isdir(folder) or not _within(folder, os.path.realpath(data)):
            raise DeckPresetError("path")
        if _within(folder, experiments) or _within(folder, mods):
            raise DeckPresetError("path")
    return folder


def _reject_path(value):
    if "\x00" in value or "/" in value or "\\" in value or ".." in value:
        raise DeckPresetError("path")


def _clean_name(value, limit=80):
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\x00", " ").split())
    if not text or any(ch in text for ch in ("\n", "\r")):
        return ""
    return text[:limit]


def _cost(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().upper() == "X":
        return "X"
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    return None


def _cost_key(cost):
    if cost is None:
        return "none"
    if cost == "X":
        return "X"
    return str(cost)


def _id_words(cid):
    words = []
    for part in re.split(r"[_\-]+", cid):
        bits = _WORDS.findall(part)
        words.extend(bits or [part])
    return " ".join(words)[:80]


def _loc_title(table, cid):
    if not isinstance(table, dict):
        return ""
    value = table.get(f"{cid}.title")
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())[:80]
    return ""


def _loc_maps():
    try:
        from sts2sim import gameloc
        eng = gameloc.table("cards", "eng") or {}
        zhs = gameloc.table("cards", "zhs") or {}
    except (OSError, ValueError, TypeError):
        return {}, {}
    if not isinstance(eng, dict):
        eng = {}
    if not isinstance(zhs, dict):
        zhs = {}
    return eng, zhs


def _names(raw, cid, eng, zhs):
    name = _clean_name(raw.get("name")) or cid
    zh = _clean_name(raw.get("name_zh") or raw.get("zh") or raw.get("name_zhs"))
    en = _clean_name(raw.get("name_en") or raw.get("en") or raw.get("name_eng"))
    if _CJK.search(name):
        zh = zh or name
    elif name and name != cid:
        en = en or name
    zh = zh or _loc_title(zhs, cid)
    en = en or _loc_title(eng, cid)
    if not en and cid.isascii():
        en = _id_words(cid)
    return name, zh, en


def _character(raw, chars):
    for key in ("character", "color"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip() and "\x00" not in value:
            return value.strip()[:40]
    pool = raw.get("pool")
    if isinstance(pool, str) and pool.strip() and pool.strip().lower() not in ("false", "true"):
        return pool.strip()[:40]
    if len(chars) == 1:
        return chars[0]
    return ""


def _load_yaml(path):
    if os.path.getsize(path) > MAX_FILE:
        return None
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _card_record(raw, mod_name, chars, eng, zhs):
    if not isinstance(raw, dict):
        return None
    cid = raw.get("id")
    if not isinstance(cid, str) or not _CARD_ID.match(cid):
        return None
    upgrade = raw.get("upgrade") if isinstance(raw.get("upgrade"), dict) else {}
    cost = _cost(raw.get("cost", 1))
    cost_up = _cost(upgrade.get("cost")) if "cost" in upgrade else cost
    type_id = _TYPE.get(str(raw.get("type") or "").strip(), "")
    rarity = _RARITY.get(str(raw.get("rarity") or "").strip(), "")
    name, zh, en = _names(raw, cid, eng, zhs)
    return {
        "id": cid,
        "name": name,
        "name_zh": zh,
        "name_en": en,
        "mod": mod_name,
        "character": _character(raw, chars),
        "type": type_id,
        "rarity": rarity,
        "cost": cost,
        "cost_up": cost_up,
        "upgradable": bool(upgrade),
    }


def _safe_child(root, rel):
    if not isinstance(rel, str) or not rel.strip():
        return None
    rel = rel.strip()
    if "\x00" in rel or rel.startswith(("/", "\\")):
        return None
    parts = rel.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    full = os.path.realpath(os.path.join(root, *parts))
    if not _within(full, root) or not os.path.isfile(full):
        return None
    joined = os.path.join(root, *parts)
    if os.path.islink(joined):
        return None
    return full


def _mod_roots():
    found = []
    seen = set()
    candidates = [MODS_DIR, os.path.join(_data_dir(), "mods")]
    extra = os.environ.get("STS2SIM_USER_MODS", "")
    if isinstance(extra, str):
        candidates.extend(part.strip() for part in extra.split(os.pathsep))
    for root in candidates:
        if not isinstance(root, str) or not root or "\x00" in root or not os.path.isdir(root):
            continue
        real = os.path.realpath(root)
        if real in seen:
            continue
        seen.add(real)
        found.append(root)
    return found


def _each_mod():
    for root in _mod_roots():
        root_real = os.path.realpath(root)
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for name in names:
            if not _MOD.match(name):
                continue
            folder = os.path.join(root, name)
            if not os.path.isdir(folder) or os.path.islink(folder) or not _within(folder, root_real):
                continue
            manifest = os.path.join(folder, "mod.yaml")
            if not os.path.isfile(manifest) or os.path.islink(manifest) or not _within(manifest, root_real):
                continue
            yield os.path.realpath(folder), manifest


def _signature():
    rows = []
    files = []
    if os.path.isfile(BUILTIN) and not os.path.islink(BUILTIN):
        files.append(BUILTIN)
    for folder, manifest in _each_mod():
        files.append(manifest)
        try:
            meta = _load_yaml(manifest)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(meta, dict):
            continue
        for rel in meta.get("cards") or []:
            child = _safe_child(folder, rel)
            if child:
                files.append(child)
    for path in files:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        rows.append((path, stat.st_size, stat.st_mtime_ns))
    loc = tuple(os.environ.get(key, "") for key in (
        "DECKBENCH_GAME_LOC_ENG", "DECKBENCH_GAME_LOC_ZHS", "DECKBENCH_GAME_PCK", "DECKBENCH_GAME_DIR",
        "STS2SIM_GUI_DATA", "STS2SIM_USER_MODS",
    ))
    return (tuple(rows), loc)


def _scan():
    eng, zhs = _loc_maps()
    cards = []
    seen = set()
    if os.path.isfile(BUILTIN) and not os.path.islink(BUILTIN):
        _take_file(cards, seen, BUILTIN, "builtin", [], eng, zhs)
    for folder, manifest in _each_mod():
        try:
            meta = _load_yaml(manifest)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(meta, dict):
            continue
        chars = [key for key in (meta.get("characters") or {}) if isinstance(key, str)]
        for rel in meta.get("cards") or []:
            child = _safe_child(folder, rel)
            if child:
                _take_file(cards, seen, child, os.path.basename(folder), chars, eng, zhs)
    cards.sort(key=lambda card: (card["mod"], card["character"], card["id"]))
    return cards


def _take_file(cards, seen, path, mod_name, chars, eng, zhs):
    try:
        loaded = _load_yaml(path)
    except (OSError, yaml.YAMLError):
        return
    if not isinstance(loaded, list):
        return
    for raw in loaded:
        card = _card_record(raw, mod_name, chars, eng, zhs)
        if card is None:
            continue
        key = (card["mod"], card["id"])
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)


def _pool():
    sig = _signature()
    if _CACHE["sig"] == sig:
        return _CACHE["cards"]
    cards = _scan()
    _CACHE["sig"] = sig
    _CACHE["cards"] = cards
    return cards


def _facets(cards):
    costs = {_cost_key(card["cost"]) for card in cards}

    def cost_order(key):
        if key == "X":
            return (1, 0)
        if key == "none":
            return (2, 0)
        return (0, int(key))

    return {
        "characters": sorted({card["character"] for card in cards if card["character"]}),
        "types": sorted({card["type"] for card in cards if card["type"]}),
        "rarities": sorted({card["rarity"] for card in cards if card["rarity"]}),
        "costs": sorted(costs, key=cost_order),
        "mods": sorted({card["mod"] for card in cards if card["mod"]}),
    }


def _as_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeckPresetError("bad_type", field=field, expected="integer")
    return value


def _check_filter(value, field, limit=40):
    if not isinstance(value, str):
        raise DeckPresetError("bad_type", field=field, expected="string")
    if "\x00" in value or len(value) > limit:
        raise DeckPresetError("query")
    return value.strip()


def list_cards(q="", character="", type_id="", cost="", rarity="", mod="", offset=0, limit=40):
    """分页、可筛选。q 同时匹配中文名、英文名（没有英文名时用 id 拆出的词）和 id。"""
    q = _check_filter(q, "q", 80)
    character = _check_filter(character, "character")
    type_id = _check_filter(type_id, "type")
    cost = _check_filter(cost, "cost", 8)
    rarity = _check_filter(rarity, "rarity")
    mod = _check_filter(mod, "mod")
    for value in (character, type_id, rarity, mod):
        if "/" in value or "\\" in value or ".." in value:
            raise DeckPresetError("query")
    if cost and cost not in ("X", "none") and not (cost.isdigit() and len(cost) <= 3):
        raise DeckPresetError("query")
    offset = _as_int(offset, "offset")
    limit = _as_int(limit, "limit")
    if offset < 0 or offset > 100_000 or limit < 1 or limit > 200:
        raise DeckPresetError("query")
    pool = _pool()
    want_type = _TYPE.get(type_id, type_id)
    want_rarity = _RARITY.get(rarity, rarity)
    needle = q.casefold()
    matched = []
    for card in pool:
        if character and card["character"] != character:
            continue
        if mod and card["mod"] != mod:
            continue
        if type_id and card["type"] != want_type:
            continue
        if rarity and card["rarity"] != want_rarity:
            continue
        if cost and _cost_key(card["cost"]) != cost:
            continue
        if needle:
            blob = "\n".join((card["id"], card["name"], card["name_zh"], card["name_en"])).casefold()
            if needle not in blob:
                continue
        matched.append(card)
    page = matched[offset:offset + limit]
    return {"total": len(matched), "offset": offset, "limit": limit, "cards": page, **_facets(pool)}


_ROOM_QUERY = {
    "normal": "normal", "monster": "normal", "普通": "normal",
    "elite": "elite", "精英": "elite",
    "boss": "boss", "首领": "boss",
}
_ROOM_YAML = {"normal": "普通", "elite": "精英", "boss": "首领", "probe": "probe"}
_GAUNTLET_ROOMS = (("normal", "普通"), ("elite", "精英"), ("boss", "首领"))
_ROOM_ORDER = {"normal": 0, "elite": 1, "boss": 2}
_GAUNTLET_ID = re.compile(r"^act([123])_(normal|elite|boss)$")
_ENC_CACHE = {"sig": None, "rows": None}
_CODEX = {"path": None}


def dummy_encounter():
    """训练木桩。模拟器不读怪物数据也能打，所以名单里始终有它。"""
    return {
        "id": "DUMMY",
        "name": "木桩",
        "name_zh": "木桩",
        "name_en": "Training dummy",
        "act": None,
        "room": "probe",
        "room_id": "probe",
        "weak": False,
    }


def _safe_id(value):
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or len(text) > 80:
        return ""
    if "\x00" in text or "/" in text or "\\" in text or ".." in text:
        return ""
    return text


def _codex_sig():
    from sts2sim.gamedata import codex_dir
    root = codex_dir()
    if not isinstance(root, str) or "\x00" in root:
        return ("", ())
    names = ("eng_monsters.json", "zhs_monsters.json", "eng_encounters.json", "zhs_encounters.json")
    rows = []
    for name in names:
        path = os.path.join(root, name)
        try:
            stat = os.stat(path)
        except OSError:
            rows.append((name, 0, 0))
            continue
        rows.append((name, stat.st_size, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9))))
    try:
        real = os.path.realpath(root)
    except OSError:
        real = root
    return (real, tuple(rows))


def _sim_db():
    """模拟器自己的遭遇库。没有本机怪物数据时返回 None，不把 SystemExit 抛出去。

    ``enemies.DATA_DIR`` 在导入时记下目录。测试或界面如果之后才设置
    ``DECKBENCH_CODEX_DIR``，这里把它指回 ``codex_dir()``，再交给 ``load_db``。
    """
    from sts2sim import enemies as EN
    from sts2sim.gamedata import codex_dir
    root = codex_dir()
    try:
        real = os.path.realpath(root) if isinstance(root, str) else ""
    except OSError:
        real = ""
    try:
        current = os.path.realpath(EN.DATA_DIR) if isinstance(EN.DATA_DIR, str) else ""
    except OSError:
        current = ""
    if real and os.path.normcase(real) != os.path.normcase(current):
        EN.DATA_DIR = real
        EN._DB.clear()
        _CODEX["path"] = None
    if _CODEX["path"] != real:
        EN._DB.clear()
        _CODEX["path"] = real
    try:
        return EN.load_db()
    except (SystemExit, OSError, ValueError, TypeError, KeyError):
        return None


def _encounter_record(enc, act, room):
    eid = _safe_id(enc.get("id"))
    if not eid:
        return None
    zh = _clean_name(enc.get("zh_name") or enc.get("name")) or eid
    en = _clean_name(enc.get("name")) or eid
    return {
        "id": eid,
        "name": zh,
        "name_zh": zh,
        "name_en": en,
        "act": act,
        "room": room,
        "room_id": _ROOM_YAML[room],
        "weak": bool(enc.get("is_weak")),
    }


def _scan_playable():
    """只收 ``encounter_pool`` 会拿去打的遭遇。弱怪、缺怪物、缺血量的不进名单。"""
    from sts2sim import enemies as EN
    before = dict(EN.APPROX)
    try:
        if _sim_db() is None:
            return []
        rows = []
        seen = set()
        for act in (1, 2, 3):
            for room, sim_room in _GAUNTLET_ROOMS:
                try:
                    pool = EN.encounter_pool(act, sim_room)
                except (SystemExit, OSError, ValueError, TypeError, KeyError):
                    continue
                if not isinstance(pool, list):
                    continue
                for enc in pool:
                    if not isinstance(enc, dict):
                        continue
                    row = _encounter_record(enc, act, room)
                    if row is None or row["id"] in seen or row["id"] == "DUMMY":
                        continue
                    seen.add(row["id"])
                    rows.append(row)
        rows.sort(key=lambda row: (row["act"], _ROOM_ORDER.get(row["room"], 9), row["id"]))
        return rows
    finally:
        EN.APPROX.clear()
        EN.APPROX.update(before)


def playable_encounters():
    """模拟器按自己的规则会打的遭遇。不含训练木桩。"""
    sig = _codex_sig()
    if _ENC_CACHE["sig"] == sig and _ENC_CACHE["rows"] is not None:
        return _ENC_CACHE["rows"]
    from sts2sim import enemies as EN
    EN._DB.clear()
    _CODEX["path"] = None
    rows = _scan_playable()
    _ENC_CACHE["sig"] = sig
    _ENC_CACHE["rows"] = rows
    return rows


def _gauntlet_list(rows):
    out = []
    for act in (1, 2, 3):
        for room, _sim_room in _GAUNTLET_ROOMS:
            members = [row for row in rows if row["act"] == act and row["room"] == room]
            if not members:
                continue
            out.append({
                "id": f"act{act}_{room}",
                "act": act,
                "room": room,
                "encounters": members,
            })
    return out


def _room_filter(value):
    if value in _ROOM_QUERY:
        return _ROOM_QUERY[value]
    folded = value.casefold()
    return _ROOM_QUERY.get(folded)


def list_encounters(q="", act="", room="", offset=0, limit=40):
    """分页、可按幕和房间筛选。名字同时给中文和英文。连战从同一份遭遇池拼出来。"""
    q = _check_filter(q, "q", 80)
    act = _check_filter(act, "act", 8)
    room = _check_filter(room, "room", 16)
    for value in (act, room, q):
        if "/" in value or "\\" in value or ".." in value:
            raise DeckPresetError("query")
    if act and act not in ("1", "2", "3"):
        raise DeckPresetError("query")
    room_key = ""
    if room:
        room_key = _room_filter(room)
        if not room_key:
            raise DeckPresetError("query")
    offset = _as_int(offset, "offset")
    limit = _as_int(limit, "limit")
    if offset < 0 or offset > 100_000 or limit < 1 or limit > 200:
        raise DeckPresetError("query")
    playable = playable_encounters()
    pool = [dummy_encounter(), *playable]
    needle = q.casefold()
    matched = []
    for row in pool:
        if act and str(row["act"] or "") != act:
            continue
        if room_key and row["room"] != room_key:
            continue
        if needle:
            blob = "\n".join((row["id"], row["name"], row["name_zh"], row["name_en"])).casefold()
            if needle not in blob:
                continue
        matched.append(row)
    page = matched[offset:offset + limit]
    acts = sorted({row["act"] for row in playable if row["act"]})
    rooms = [key for key in ("normal", "elite", "boss") if any(row["room"] == key for row in playable)]
    return {
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "encounters": page,
        "probe": dummy_encounter(),
        "acts": acts,
        "rooms": rooms,
        "gauntlets": _gauntlet_list(playable),
        "full_turns": full_fight_turns(),
        "turn_limit": TURN_LIMIT,
    }


def _fight_count(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeckPresetError("bad_type", field="fights", expected="integer")
    if value < 1 or value > MAX_FIGHTS_EACH:
        raise DeckPresetError("fights", n=MAX_FIGHTS_EACH)
    return value


def _known_encounters():
    rows = [dummy_encounter(), *playable_encounters()]
    return {row["id"]: row for row in rows}


def _gauntlet_members(gid):
    if not isinstance(gid, str):
        raise DeckPresetError("bad_type", field="gauntlet", expected="string")
    text = gid.strip()
    if not text:
        raise DeckPresetError("missing", field="gauntlet")
    _reject_path(text)
    match = _GAUNTLET_ID.match(text)
    if not match:
        raise DeckPresetError("gauntlet")
    act = int(match.group(1))
    room = match.group(2)
    members = [row for row in playable_encounters() if row["act"] == act and row["room"] == room]
    if not members:
        raise DeckPresetError("gauntlet")
    return members


def resolve_encounters(payload, allow_default=True):
    """校验要打的遭遇。没写 encounters / gauntlet 时，保存预设默认一场木桩。

    返回的每一项都是模拟器名单里的副本，并带 ``fights``。空列表在
    ``allow_default`` 为假时表示「这次不改房间抽取」。
    """
    if not isinstance(payload, dict):
        raise DeckPresetError("bad_type", field="body", expected="object")
    has_enc = "encounters" in payload and payload["encounters"] is not None
    has_gauntlet = "gauntlet" in payload and payload["gauntlet"] not in (None, "")
    if not has_enc and not has_gauntlet:
        if allow_default:
            return [dict(dummy_encounter(), fights=1)]
        return []
    if has_enc and payload["encounters"] == [] and not has_gauntlet:
        if allow_default:
            raise DeckPresetError("no_encounter")
        return []
    chosen = []
    index = {}
    if has_gauntlet:
        each = 1
        if payload.get("fights") is not None:
            each = _fight_count(payload["fights"])
        for row in _gauntlet_members(payload["gauntlet"]):
            index[row["id"]] = len(chosen)
            chosen.append(dict(row, fights=each))
    if has_enc:
        raw = payload["encounters"]
        if not isinstance(raw, list):
            raise DeckPresetError("bad_type", field="encounters", expected="array")
        known = _known_encounters()
        for entry in raw:
            if isinstance(entry, str):
                eid = entry.strip()
                if not eid:
                    raise DeckPresetError("missing", field="encounters.id")
                fights = 1
            elif isinstance(entry, dict):
                if any(key in entry for key in _BANNED_FIELDS):
                    raise DeckPresetError("path")
                eid = entry.get("id")
                if not isinstance(eid, str) or not eid.strip():
                    raise DeckPresetError("missing", field="encounters.id")
                eid = eid.strip()
                if "fights" not in entry or entry["fights"] is None:
                    fights = 1
                else:
                    fights = _fight_count(entry["fights"])
            else:
                raise DeckPresetError("bad_type", field="encounters", expected="object")
            _reject_path(eid)
            row = known.get(eid)
            if row is None:
                raise DeckPresetError("unknown_encounter")
            if eid in index:
                chosen[index[eid]]["fights"] = fights
            else:
                index[eid] = len(chosen)
                chosen.append(dict(row, fights=fights))
    if not chosen:
        raise DeckPresetError("no_encounter")
    if len(chosen) > MAX_ENCOUNTERS:
        raise DeckPresetError("too_many_encounters", n=MAX_ENCOUNTERS)
    total = sum(item["fights"] for item in chosen)
    if total > MAX_FIGHTS_TOTAL:
        raise DeckPresetError("too_many_fights", n=MAX_FIGHTS_TOTAL)
    return chosen


def _runner_turn_default():
    import inspect

    from sts2sim.runner import run_fight
    value = inspect.signature(run_fight).parameters["max_turns"].default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _shipped_turn_caps():
    """出厂实验顶层的 max_turns。extra 里木桩用的更短上限不算。"""
    folder = os.path.join(_sim_root(), "experiments")
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    found = []
    for name in names:
        if not name.endswith(".yaml"):
            continue
        path = os.path.join(folder, name)
        if os.path.islink(path) or not os.path.isfile(path) or not _within(path, folder):
            continue
        try:
            if os.path.getsize(path) > MAX_FILE:
                continue
            with open(path, encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(loaded, dict):
            continue
        turns = loaded.get("max_turns")
        if isinstance(turns, bool) or not isinstance(turns, int) or turns < 1:
            continue
        found.append(turns)
    return found


def full_fight_turns():
    """出厂实验共用的整场回合上限。它们不一致时，取出现最多的那个；和模拟器默认打平则用默认。"""
    fallback = _runner_turn_default()
    counts = {}
    for turns in _shipped_turn_caps():
        counts[turns] = counts.get(turns, 0) + 1
    if not counts:
        return fallback if fallback is not None else 1
    best = max(counts.values())
    modes = [turns for turns, count in counts.items() if count == best]
    if fallback in modes:
        return fallback
    return min(modes)


def _checked_turns(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeckPresetError("bad_type", field="max_turns", expected="integer")
    if value < 1 or value > TURN_LIMIT:
        raise DeckPresetError("max_turns", n=TURN_LIMIT)
    return value


def preset_turns(payload, chosen):
    """一份预设的回合上限。只含训练木桩且没写 max_turns 时是 1，否则用整场上限。"""
    dummy_only = bool(chosen) and all(item.get("id") == "DUMMY" for item in chosen)
    if not isinstance(payload, dict) or "max_turns" not in payload or payload.get("max_turns") is None:
        return 1 if dummy_only else full_fight_turns()
    return _checked_turns(payload.get("max_turns"))


def fight_rows(deck_ids, chosen, max_turns):
    """写成实验 YAML 的 ``extra`` 行。模拟器按每一行自己的 max_turns 打。"""
    turns = _checked_turns(max_turns)
    rows = []
    for did in deck_ids:
        for enc in chosen:
            rows.append({
                "deck": did,
                "encounter": enc["id"],
                "fights": enc["fights"],
                "max_turns": turns,
                "act": enc["act"] or 1,
                "room": enc["room_id"],
            })
    return rows


def _collides(pid):
    shipped = os.path.join(_sim_root(), "experiments", pid + ".yaml")
    if os.path.isfile(shipped):
        return True
    folder = os.path.join(MODS_DIR, pid)
    return os.path.isdir(folder)


def _is_shipped_mod(name):
    folder = os.path.join(MODS_DIR, name)
    manifest = os.path.join(folder, "mod.yaml")
    return os.path.isfile(manifest) and not os.path.islink(folder) and _within(manifest, MODS_DIR)


def _find_mod_dir(name):
    if not _MOD.match(name):
        return None
    for root in _mod_roots():
        folder = os.path.join(root, name)
        manifest = os.path.join(folder, "mod.yaml")
        if os.path.isdir(folder) and not os.path.islink(folder) and os.path.isfile(manifest) and _within(folder, root):
            return os.path.realpath(folder)
    return None


def _require_str(payload, field):
    if field not in payload or payload[field] is None:
        raise DeckPresetError("missing", field=field)
    value = payload[field]
    if not isinstance(value, str):
        raise DeckPresetError("bad_type", field=field, expected="string")
    text = value.strip()
    if not text:
        raise DeckPresetError("missing", field=field)
    _reject_path(text)
    return text


def _card_rows(payload):
    cards = payload.get("cards")
    if not isinstance(cards, list):
        if "cards" not in payload or cards is None:
            raise DeckPresetError("missing", field="cards")
        raise DeckPresetError("bad_type", field="cards", expected="array")
    if not cards:
        raise DeckPresetError("empty")
    if len(cards) > MAX_ROWS:
        raise DeckPresetError("too_many")
    merged = {}
    order = []
    for entry in cards:
        if not isinstance(entry, dict):
            raise DeckPresetError("bad_type", field="cards", expected="object")
        cid = entry.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise DeckPresetError("missing", field="cards.id")
        cid = cid.strip()
        _reject_path(cid)
        if not _CARD_ID.match(cid):
            raise DeckPresetError("unknown_card")
        if "count" not in entry or entry["count"] is None:
            count = 1
        else:
            count = entry["count"]
            if isinstance(count, bool) or not isinstance(count, int):
                raise DeckPresetError("bad_type", field="count", expected="integer")
        if count < 1 or count > MAX_COPIES:
            raise DeckPresetError("count")
        upgrade = entry.get("upgrade", False)
        if not isinstance(upgrade, bool):
            raise DeckPresetError("bad_type", field="upgrade", expected="boolean")
        key = (cid, upgrade)
        if key not in merged:
            order.append(key)
            merged[key] = 0
        merged[key] += count
        if merged[key] > MAX_COPIES:
            raise DeckPresetError("count")
    total = sum(merged.values())
    if total > MAX_CARDS:
        raise DeckPresetError("too_many")
    return [(cid, upgrade, merged[(cid, upgrade)]) for cid, upgrade in order], total


def _acts(payload):
    if "acts" not in payload or payload["acts"] is None:
        return [1]
    acts = payload["acts"]
    if not isinstance(acts, list) or not acts or len(acts) > 3:
        raise DeckPresetError("bad_type", field="acts", expected="array")
    out = []
    for act in acts:
        if isinstance(act, bool) or not isinstance(act, int) or act not in (1, 2, 3):
            raise DeckPresetError("bad_type", field="acts", expected="integer")
        if act not in out:
            out.append(act)
    return out


def _optional_agent(payload):
    if "agent" not in payload or payload["agent"] in (None, ""):
        return "heuristic"
    agent = payload["agent"]
    if not isinstance(agent, str):
        raise DeckPresetError("bad_type", field="agent", expected="string")
    if agent not in ("heuristic", "beam"):
        raise DeckPresetError("agent")
    return agent


def _optional_seed(payload):
    if "seed" not in payload or payload["seed"] is None:
        return 1
    seed = payload["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise DeckPresetError("bad_type", field="seed", expected="integer")
    if seed < 0 or seed > 2_147_483_647:
        raise DeckPresetError("query")
    return seed


def _load_modset(mod_name):
    from sts2sim.modloader import ModSet
    folder = _find_mod_dir(mod_name)
    if folder is None:
        raise DeckPresetError("mod")
    shipped = _is_shipped_mod(mod_name)

    def _build():
        try:
            return ModSet([mod_name])
        except SystemExit as exc:
            raise DeckPresetError("mod") from exc
        except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
            raise DeckPresetError("mod") from exc

    if shipped:
        return _build(), True
    key = "STS2SIM_USER_MODS"
    old = os.environ.get(key)
    os.environ[key] = os.path.dirname(folder)
    try:
        return _build(), False
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


def _tokens(modset, mod_name, rows):
    tokens = []
    for cid, upgrade, count in rows:
        try:
            defin = modset.find_card(cid)
        except KeyError as exc:
            raise DeckPresetError("unknown_card") from exc
        if defin.mod not in (mod_name, "builtin"):
            raise DeckPresetError("unknown_card")
        token = defin.id + ("+" if upgrade else "")
        if count != 1:
            token += "×" + str(count)
        tokens.append(token)
    try:
        parsed = modset.parse_deck(tokens)
    except (KeyError, ValueError) as exc:
        raise DeckPresetError("cards") from exc
    if len(parsed) != sum(count for _cid, _up, count in rows):
        raise DeckPresetError("cards")
    return tokens


def _write_text(folder, name, text):
    if name not in ("mod.yaml", "decks.yaml") and not (name.endswith(".yaml") and _ID.match(name.removesuffix(".yaml"))):
        raise DeckPresetError("path")
    parent = os.path.realpath(folder)
    dest = os.path.join(parent, name)
    if os.path.normcase(os.path.dirname(os.path.realpath(dest))) != os.path.normcase(parent):
        raise DeckPresetError("path")
    if os.path.islink(dest) or os.path.isdir(dest):
        raise DeckPresetError("symlink")
    tmp = dest + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        if os.path.islink(dest):
            raise DeckPresetError("symlink")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    if not _within(dest, folder):
        raise DeckPresetError("path")


def save_preset(payload):
    """校验并写入用户预设目录里的 ``<id>.yaml``。同名用户预设可以更新。"""
    if not isinstance(payload, dict):
        raise DeckPresetError("bad_type", field="body", expected="object")
    if any(key in payload for key in _BANNED_FIELDS):
        raise DeckPresetError("path")
    pid = _require_str(payload, "id")
    name = _require_str(payload, "name")
    mod_name = _require_str(payload, "mod")
    if not _ID.match(pid):
        raise DeckPresetError("bad_id")
    if len(name) > 80:
        raise DeckPresetError("name")
    if not _MOD.match(mod_name) or mod_name == pid:
        raise DeckPresetError("mod")
    if _collides(pid):
        raise DeckPresetError("shipped")
    rows, total = _card_rows(payload)
    acts = _acts(payload)
    agent = _optional_agent(payload)
    seed = _optional_seed(payload)
    modset, _shipped = _load_modset(mod_name)
    chars = list(modset.characters)
    if "character" in payload and payload["character"] not in (None, ""):
        character = _require_str(payload, "character")
        if character not in chars:
            raise DeckPresetError("character")
    elif len(chars) == 1:
        character = chars[0]
    else:
        raise DeckPresetError("missing", field="character")
    tokens = _tokens(modset, mod_name, rows)
    chosen = resolve_encounters(payload)
    turns = preset_turns(payload, chosen)
    exp = {
        "name": pid,
        "title": name,
        "mods": [mod_name, pid],
        "seed": seed,
        "fights": 1,
        "max_turns": turns,
        "agent": agent,
        "rooms": [],
        "decks": [pid],
        "extra": fight_rows([pid], chosen, turns),
        "user_deck": {
            "id": pid,
            "name": name,
            "mod": mod_name,
            "character": character,
            "acts": acts,
            "cards": tokens,
        },
    }
    text = (
        "# User deck preset. extra lists the encounters this deck runs against.\n"
        "# max_turns is the fight cap. A dummy-only preset defaults to 1 turn.\n"
        "# This file is not a shipped experiment.\n"
    )
    text += yaml.safe_dump(exp, allow_unicode=True, sort_keys=False)
    folder = presets_dir(create=True)
    _write_text(folder, pid + ".yaml", text)
    return {
        "ok": True,
        "id": pid,
        "title": name,
        "file": pid + ".yaml",
        "cards": total,
        "mod": mod_name,
        "character": character,
        "encounters": [enc["id"] for enc in chosen],
        "fights": sum(enc["fights"] for enc in chosen),
        "max_turns": turns,
    }


def _read_mapping(path, folder):
    if os.path.getsize(path) > MAX_BYTES:
        raise DeckPresetError("too_big", n=MAX_BYTES)
    with open(path, encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if not isinstance(loaded, dict) or not _within(path, folder):
        raise DeckPresetError("preset")
    return loaded


def list_presets():
    """供新建测试的预设列表使用。坏文件跳过，不创建目录。"""
    try:
        folder = presets_dir(create=False)
    except DeckPresetError:
        return []
    if not os.path.isdir(folder):
        return []
    out = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    for name in names:
        if not name.endswith(".yaml"):
            continue
        pid = name[:-5]
        if not _ID.match(pid) or _collides(pid):
            continue
        path = os.path.join(folder, name)
        if os.path.islink(path) or not os.path.isfile(path) or not _within(path, folder):
            continue
        try:
            exp = _read_mapping(path, folder)
        except (OSError, yaml.YAMLError, DeckPresetError):
            continue
        if exp.get("name") != pid or not isinstance(exp.get("user_deck"), dict):
            continue
        decks = exp.get("decks") if isinstance(exp.get("decks"), list) else []
        rooms = exp.get("rooms") if isinstance(exp.get("rooms"), list) else []
        mods = exp.get("mods") if isinstance(exp.get("mods"), list) else []
        extra = exp.get("extra") if isinstance(exp.get("extra"), list) else []
        encounters = []
        for row in extra:
            if not isinstance(row, dict):
                continue
            eid = _safe_id(row.get("encounter"))
            if not eid:
                continue
            count = row.get("fights")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                count = 1
            encounters.append({"id": eid, "fights": count})
        out.append({
            "id": pid,
            "name": pid,
            "title": _clean_name(exp.get("title")) or pid,
            "mods": mods,
            "decks": decks,
            "rooms": rooms,
            "fights": exp.get("fights") if isinstance(exp.get("fights"), int) else 1,
            "max_turns": exp.get("max_turns") if isinstance(exp.get("max_turns"), int) else 1,
            "agent": exp.get("agent") if exp.get("agent") in ("heuristic", "beam") else "heuristic",
            "seed": exp.get("seed") if isinstance(exp.get("seed"), int) else 1,
            "n_extra": len(extra),
            "encounters": encounters,
            "user": True,
        })
    return out


def _copy_tree(src, dst):
    src_real = os.path.realpath(src)
    os.makedirs(dst, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        rel = os.path.relpath(dirpath, src)
        if rel.startswith("..") or not _within(dirpath, src_real):
            dirnames.clear()
            continue
        dirnames[:] = [
            name for name in dirnames
            if name not in _SKIP_PARTS and not os.path.islink(os.path.join(dirpath, name))
        ]
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        if not _within(out_dir, os.path.realpath(os.path.dirname(dst))):
            continue
        os.makedirs(out_dir, exist_ok=True)
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            src_file = os.path.join(dirpath, name)
            if os.path.islink(src_file) or not _within(src_file, src_real):
                continue
            try:
                if os.path.getsize(src_file) > MAX_FILE:
                    continue
                with open(src_file, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            with open(os.path.join(out_dir, name), "wb") as fh:
                fh.write(data)


def _dump_inside(folder, name, obj):
    text = yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)
    _write_text(folder, name, text)


def materialize_run_mod(exp, run_dir):
    """在这次测试的目录里写出临时 mod，返回 ``STS2SIM_USER_MODS`` 应指向的父目录。"""
    info = exp.get("user_deck") if isinstance(exp, dict) else None
    if not isinstance(info, dict):
        raise DeckPresetError("preset")
    pid = info.get("id")
    mod_name = info.get("mod")
    cards = info.get("cards")
    character = info.get("character")
    if not isinstance(pid, str) or not _ID.match(pid):
        raise DeckPresetError("preset")
    if not isinstance(mod_name, str) or not _MOD.match(mod_name):
        raise DeckPresetError("preset")
    if not isinstance(character, str) or not character or "\x00" in character:
        raise DeckPresetError("preset")
    if not isinstance(cards, list) or not cards or not all(isinstance(item, str) and item for item in cards):
        raise DeckPresetError("preset")
    if not isinstance(run_dir, str) or not os.path.isdir(run_dir):
        raise DeckPresetError("preset")
    root = os.path.realpath(run_dir)
    parent = os.path.join(root, "user_mods")
    mod_dir = os.path.join(parent, pid)
    if not _within(mod_dir, root):
        raise DeckPresetError("path")
    os.makedirs(mod_dir, exist_ok=True)
    if mod_name != pid and not _is_shipped_mod(mod_name):
        src = _find_mod_dir(mod_name)
        if src is None:
            raise DeckPresetError("mod")
        _copy_tree(src, os.path.join(parent, mod_name))
    title = _clean_name(info.get("name")) or pid
    acts = info.get("acts") if isinstance(info.get("acts"), list) and info.get("acts") else [1]
    _dump_inside(mod_dir, "mod.yaml", {"name": pid, "title": title, "decks": ["decks.yaml"]})
    _dump_inside(mod_dir, "decks.yaml", [{
        "id": pid,
        "name": title,
        "character": character,
        "stage": "custom",
        "acts": acts,
        "cards": cards,
    }])
    return parent


def existing_user_preset(preset_id):
    if not isinstance(preset_id, str) or not _ID.match(preset_id) or _collides(preset_id):
        return None
    try:
        folder = presets_dir(create=False)
    except DeckPresetError:
        return None
    path = os.path.join(folder, preset_id + ".yaml")
    if not os.path.isfile(path) or os.path.islink(path) or not _within(path, folder):
        return None
    return path


def open_for_run(preset_id, run_dir):
    """用户预设返回 (实验 dict, 临时 mod 父目录)。出厂预设返回 (None, None)。"""
    path = existing_user_preset(preset_id)
    if path is None:
        return None, None
    folder = os.path.dirname(path)
    exp = _read_mapping(path, folder)
    parent = materialize_run_mod(exp, run_dir)
    return exp, parent
