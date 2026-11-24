"""把本机反编译和中英本地化写成旧版战斗模拟器用的目录。

写出的 JSON 沿用模拟器已经在读的字段（怪物血量与招式、遭遇、遗物、药水、能力、卡牌），
并多一份角色表。目录放在缓存的 ``legacy-codex/``，``codex_stamp.json`` 记着
``sts2.dll`` 的 SHA-256 和游戏版本。不写进仓库。

直译效果只覆盖 OnPlay 里能看清的伤害和格挡。箭袋、Dread 加值、进阶数值和不走直线的牌不在这里结算。
"""
import json
import os
import re
import sys

FORMAT = 1
KIND = "deckbench-legacy-codex"
STAMP = "codex_stamp.json"
TABLES = ("monsters", "encounters", "cards", "relics", "potions", "powers", "characters", "acts")
KINDS = ("monsters", "encounters", "cards", "relics", "potions", "powers", "characters")

TYPE_ZH = {
    "Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态",
    "Curse": "诅咒", "Quest": "状态",
}
RARITY_ZH = {
    "Basic": "基础", "Common": "普通", "Uncommon": "罕见", "Rare": "稀有",
    "Event": "事件", "Status": "状态", "Curse": "诅咒", "Token": "特殊",
    "Starter": "初始遗物", "Shop": "商店", "Ancient": "先古之民", "None": "",
}
TARGET_ZH = {
    "AnyEnemy": "enemy", "AllEnemies": "all", "RandomEnemy": "random",
    "Self": "self", "None": "none",
}
_MECH = ("DamageCmd", "CreatureCmd", "PowerCmd", "CardCmd", "PlayerCmd")
_ALLOWED_CALLS = {("DamageCmd", "Attack"), ("CreatureCmd", "GainBlock")}


class LegacyCodexError(ValueError):
    pass


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _read(path):
    with open(path, encoding="utf-8-sig") as handle:
        return json.load(handle)


def _dump(path, payload, indent=None):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        if indent is None:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(payload, handle, ensure_ascii=False, indent=indent)
        handle.write("\n")


def _tools():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools = os.path.join(root, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import parse_encounters
    import parse_monster_ai
    return parse_monster_ai, parse_encounters


def _loc_from_dir(directory):
    out = {}
    if not directory or not os.path.isdir(directory):
        return out
    for name in TABLES:
        path = os.path.join(directory, name + ".json")
        if os.path.isfile(path):
            out[name] = _read(path)
    return out


def load_loc_pair():
    """eng/zhs 表。先看 DECKBENCH_GAME_LOC_*，再看本机 .pck。没有卡牌表就返回 (None, None)。"""
    eng = _loc_from_dir(os.environ.get("DECKBENCH_GAME_LOC_ENG"))
    zhs = _loc_from_dir(os.environ.get("DECKBENCH_GAME_LOC_ZHS"))
    if not eng.get("cards") or not zhs.get("cards"):
        from . import gameloc
        eng = {name: gameloc.table(name, "eng") or {} for name in TABLES}
        zhs = {name: gameloc.table(name, "zhs") or {} for name in TABLES}
    if eng.get("cards") and zhs.get("cards"):
        return eng, zhs
    return None, None


def _text(table, key):
    if not table:
        return ""
    value = table.get(key)
    return value if isinstance(value, str) else ""


def _name_along(cid, table, bases, suffix):
    seen = set()
    while cid and cid not in seen:
        seen.add(cid)
        found = _text(table, cid + suffix)
        if found:
            return found
        cid = bases.get(cid)
    return ""


def _enum_value(src, name):
    """``Type Name => Type.Value`` 或表达式里的 ``Type.Value``。"""
    match = re.search(r"\b" + name + r"(?:\s+\w+)?\s*=>\s*" + name + r"\.(\w+)", src)
    if match:
        return match.group(1)
    match = re.search(r"\b" + name + r"\.(\w+)", src)
    return match.group(1) if match else None


def _prop(src, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*=>\s*([^;]+);", src)
    return match.group(1).strip() if match else None


def normal_int(expr, src=None, seen=None):
    """非进阶、非 Dread 的整数。``GetValueIfAscension`` 取第二个数；``=> OtherProp`` 再顺着看。"""
    if not expr:
        return None
    match = re.search(r"GetValueIfAscension\(\s*[^,]+,\s*(-?\d+)m?\s*,\s*(-?\d+)m?\s*\)", expr)
    if match:
        return int(match.group(2))
    token = expr.strip()
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if src and re.fullmatch(r"\w+", token):
        seen = seen or set()
        if token in seen:
            return None
        return normal_int(_prop(src, token), src, seen | {token})
    return None


def _files(directory):
    if not directory or not os.path.isdir(directory):
        return []
    return sorted(name for name in os.listdir(directory) if name.endswith(".cs"))


def _skip(name):
    return name.startswith(("Mock", "Deprecated"))


def _class_base(src, cls):
    match = re.search(r"class\s+" + re.escape(cls) + r"\s*:\s*(\w+)", src)
    return snake(match.group(1)) if match else None


def _chain_value(cid, sources, bases, pick, seen=None):
    seen = seen or set()
    if cid in seen:
        return None
    src = sources.get(cid)
    if src:
        found = pick(src)
        if found is not None:
            return found
    parent = bases.get(cid)
    if not parent or parent == "MONSTER_MODEL":
        return None
    return _chain_value(parent, sources, bases, pick, seen | {cid})


def _applies(body):
    out = []
    for match in re.finditer(
            r"PowerCmd\.Apply<(\w+?)Power>\((?:new \w*PlayerChoiceContext\(\)|choiceContext|ctx|context),\s*([^,]+),\s*([^,]+),",
            body):
        target = match.group(2).strip()
        if target not in ("base.Creature", "base.Owner.Creature"):
            continue
        raw_amount = match.group(3).strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?m", raw_amount):
            raw_amount = raw_amount[:-1]
        amount = normal_int(raw_amount)
        if amount is None:
            continue
        out.append({"power_id": snake(match.group(1)), "amount": amount})
    return out


def _innate(src):
    monster_ai, _enc = _tools()
    body = monster_ai.body_of(src, "AfterAddedToRoom(")
    if not body:
        return None
    powers = _applies(body)
    if "base.AfterAddedToRoom" in body:
        return powers, True
    return powers, False


def _move_id(state_id):
    if state_id.endswith("_MOVE"):
        return state_id[:-5]
    return state_id


def _moves(ai):
    moves = []
    states = []
    if not ai:
        return moves, {"type": "missing", "states": [], "initial_move": None}
    order = ai.get("order") or list(ai.get("states") or [])
    for sid in order:
        state = (ai.get("states") or {}).get(sid)
        if not state:
            continue
        if state.get("kind") != "move":
            continue
        code = state.get("code_move") or {}
        mid = _move_id(sid)
        intents = [item.get("type") for item in state.get("intents") or [] if item.get("type")]
        raw = {
            "id": mid,
            "name": mid,
            "intent": " + ".join(intents) or "Unknown",
            "damage": {"normal": int(code.get("damage") or 0), "hit_count": int(code.get("hits") or 1)},
            "block": int(code.get("block") or 0),
            "powers": list(code.get("powers") or []),
            "heal": int(code.get("heal") or 0),
        }
        if code.get("unknown"):
            raw["partial"] = True
        if not raw["damage"]["normal"]:
            raw.pop("damage")
        if not raw["block"]:
            raw.pop("block")
        if not raw["powers"]:
            raw.pop("powers")
        if not raw["heal"]:
            raw.pop("heal")
        moves.append(raw)
        states.append({"id": sid, "type": "move", "move_id": mid, "next": state.get("next")})
    initial = ai.get("initial")
    pattern = {"type": "code", "states": states, "initial_move": _move_id(initial) if initial else None}
    return moves, pattern


def _monsters(monster_dir, ai, eng, zhs):
    sources = {}
    bases = {}
    for name in _files(monster_dir):
        if _skip(name[:-3]):
            continue
        path = os.path.join(monster_dir, name)
        with open(path, encoding="utf-8") as handle:
            src = handle.read()
        cid = snake(name[:-3])
        sources[cid] = src
        bases[cid] = _class_base(src, name[:-3])
    rows = []
    for cid in sorted(sources):
        src = sources[cid]
        min_hp = _chain_value(cid, sources, bases, lambda text: normal_int(_prop(text, "MinInitialHp"), text))
        max_hp = _chain_value(cid, sources, bases, lambda text: normal_int(_prop(text, "MaxInitialHp"), text))
        if max_hp is None:
            max_hp = min_hp
        info = ai.get(cid)
        moves, pattern = _moves(info)
        innate_here = _innate(src)
        innate = []
        if innate_here is None:
            parent = bases.get(cid)
            if parent:
                inherited = _chain_value(parent, sources, bases, lambda text: _innate(text) or ([], False))
                innate = list((inherited or ([], False))[0] or [])
        else:
            powers, calls_base = innate_here
            if calls_base and bases.get(cid):
                parent_powers = _chain_value(bases[cid], sources, bases, lambda text: (_innate(text) or ([], False))[0])
                innate.extend(parent_powers or [])
            innate.extend(powers)
        if min_hp is None and not moves:
            continue
        name_en = _name_along(cid, eng.get("monsters"), bases, ".name") or cid
        name_zh = _name_along(cid, zhs.get("monsters"), bases, ".name") or name_en
        localized = []
        for move in moves:
            title = cid + ".moves." + move["id"] + ".title"
            move_en = dict(move)
            move_zh = dict(move)
            move_en["name"] = _text(eng.get("monsters"), title) or move["id"]
            move_zh["name"] = _text(zhs.get("monsters"), title) or move_en["name"]
            localized.append((move_en, move_zh))
        innate_rows = [{"power_id": item["power_id"], "amount": item["amount"]} for item in innate]
        base = {
            "id": cid,
            "min_hp": min_hp,
            "max_hp": max_hp or min_hp,
            "innate_powers": innate_rows,
            "attack_pattern": pattern,
        }
        en = dict(base, name=name_en, moves=[pair[0] for pair in localized])
        zh = dict(base, name=name_zh, moves=[pair[1] for pair in localized])
        rows.append((en, zh))
    return rows


def _acts(act_dir):
    found = {}
    for name in _files(act_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(act_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        index = normal_int(_prop(src, "Index"))
        if index is None or index < 0:
            continue
        label = f"Act {index + 1} {name[:-3]}"
        for enc in re.findall(r"ModelDb\.Encounter<(\w+)>", src):
            found.setdefault(snake(enc), label)
    return found


def _encounters(enc_dir, act_dir, compositions, eng, zhs):
    labels = _acts(act_dir)
    rows = []
    for name in _files(enc_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(enc_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        cid = snake(name[:-3])
        room = _enum_value(src, "RoomType") or "Monster"
        weak = bool(re.search(r"bool\s+IsWeak\s*=>\s*true", src))
        monsters = []
        for mid in re.findall(r"ModelDb\.Monster<(\w+)>", src):
            sid = snake(mid)
            if sid not in monsters:
                monsters.append(sid)
        comp = compositions.get(cid) or {}
        if comp.get("source") and comp.get("source") != "缺失":
            ordered = []
            for slot in comp.get("slots") or []:
                for mid in slot:
                    if mid not in ordered:
                        ordered.append(mid)
            for _weight, group in comp.get("alternatives") or []:
                for mid in group:
                    if mid not in ordered:
                        ordered.append(mid)
            pool = (comp.get("pool") or {}).get("options") or {}
            for mid in pool:
                if mid not in ordered:
                    ordered.append(mid)
            if ordered:
                monsters = ordered
        name_en = _text(eng.get("encounters"), cid + ".title") or cid
        name_zh = _text(zhs.get("encounters"), cid + ".title") or name_en
        base = {
            "id": cid,
            "act": labels.get(cid),
            "room_type": room,
            "is_weak": weak,
            "monsters": [{"id": mid} for mid in monsters],
        }
        en = dict(base, name=name_en)
        zh = dict(base, name=name_zh)
        rows.append((en, zh))
    rows.sort(key=lambda pair: pair[0]["id"])
    return rows


def _pools(directory, needle, suffix):
    out = {}
    for name in _files(directory):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as handle:
            src = handle.read()
        pool = snake(name[:-3]).removesuffix(suffix)
        for item in re.findall(needle, src):
            out.setdefault(snake(item), pool)
    return out


def _ctor(src):
    match = re.search(
        r":\s*base\(\s*(-?\d+)\s*,\s*CardType\.(\w+)\s*,\s*CardRarity\.(\w+)\s*,\s*TargetType\.(\w+)",
        src)
    if not match:
        return None
    return {
        "cost": int(match.group(1)),
        "type_key": match.group(2),
        "rarity_key": match.group(3),
        "target": TARGET_ZH.get(match.group(4), "none"),
    }


def _straight_card(src):
    """OnPlay 只有伤害和/或格挡时给出可打的效果。其它调用只进索引。"""
    monster_ai, _enc = _tools()
    body = monster_ai.body_of(src, "OnPlay(") or ""
    calls = re.findall(r"\b(DamageCmd|CreatureCmd|PowerCmd|CardCmd|PlayerCmd|ArrowCmd)\.(\w+)", body)
    mech = [pair for pair in calls if pair[0] in _MECH]
    if any(pair not in _ALLOWED_CALLS for pair in mech):
        return None
    effects = []
    upgrade = {}
    from_arrow = "FromArrow" in src or any(pair[0] == "ArrowCmd" for pair in calls)
    if ("DamageCmd", "Attack") in mech or from_arrow and ("ArrowCmd", "ShootArrowAtTarget") in calls:
        match = re.search(r"new\s+DamageVar\(\s*(-?\d+(?:\.\d+)?)m?", src)
        if not match:
            return None
        base = int(float(match.group(1)))
        effects.append({"op": "damage", "amount": "dmg"})
        upgrade["dmg"] = base
        up = re.search(r"DynamicVars\.Damage\.UpgradeValueBy\(\s*(-?\d+(?:\.\d+)?)m?", src)
        if up:
            upgrade["dmg_up"] = base + int(float(up.group(1)))
    if ("CreatureCmd", "GainBlock") in mech:
        match = re.search(r"new\s+BlockVar\(\s*(-?\d+(?:\.\d+)?)m?", src)
        if not match:
            return None
        base = int(float(match.group(1)))
        effects.append({"op": "block", "amount": "blk"})
        upgrade["blk"] = base
        up = re.search(r"DynamicVars\.Block\.UpgradeValueBy\(\s*(-?\d+(?:\.\d+)?)m?", src)
        if up:
            upgrade["blk_up"] = base + int(float(up.group(1)))
    if not effects:
        return None
    return {"effects": effects, "upgrade": upgrade, "from_arrow": from_arrow}


def _card_record(cid, header, straight, pool, name, description):
    raw = {
        "id": cid,
        "name": name or cid,
        "description": description or "",
        "cost": header["cost"],
        "type": TYPE_ZH.get(header["type_key"], header["type_key"]),
        "type_key": header["type_key"],
        "rarity": RARITY_ZH.get(header["rarity_key"], header["rarity_key"]),
        "rarity_key": header["rarity_key"],
        "target": header["target"],
        "pool": pool,
    }
    if not straight:
        raw["effects_status"] = "index_only"
        return raw
    variables = {}
    upgraded = {}
    if "dmg" in straight["upgrade"]:
        variables["dmg"] = straight["upgrade"]["dmg"]
        upgraded["dmg"] = straight["upgrade"].get("dmg_up", straight["upgrade"]["dmg"])
    if "blk" in straight["upgrade"]:
        variables["blk"] = straight["upgrade"]["blk"]
        upgraded["blk"] = straight["upgrade"].get("blk_up", straight["upgrade"]["blk"])
    raw["vars"] = variables
    raw["effects"] = straight["effects"]
    raw["upgrade"] = {"vars": upgraded}
    raw["effects_status"] = "straight_line"
    if straight["from_arrow"]:
        raw["tags"] = ["arrow"]
        raw["from_arrow"] = True
        raw["limits"] = ["arrow_ammo_not_simulated"]
    return raw


def _cards(card_dir, pool_dir, eng, zhs):
    pools = _pools(pool_dir, r"ModelDb\.Card<(\w+)>", "_CARD_POOL")
    rows = []
    for name in _files(card_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(card_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        header = _ctor(src)
        if not header:
            continue
        cid = snake(name[:-3])
        straight = _straight_card(src)
        en = _card_record(cid, header, straight, pools.get(cid),
                          _text(eng.get("cards"), cid + ".title"), _text(eng.get("cards"), cid + ".description"))
        zh = _card_record(cid, header, straight, pools.get(cid),
                          _text(zhs.get("cards"), cid + ".title") or en["name"],
                          _text(zhs.get("cards"), cid + ".description"))
        rows.append((en, zh))
    return rows


def _combat_start(src):
    monster_ai, _enc = _tools()
    body = monster_ai.body_of(src, "AfterRoomEntered(") or ""
    if "CombatRoom" not in body:
        return []
    out = []
    for match in re.finditer(r"PowerCmd\.Apply<(\w+?)Power>", body):
        power = match.group(1)
        amount = None
        var = re.search(r"new\s+PowerVar<" + power + r"Power>\(\s*(-?\d+(?:\.\d+)?)m?", src)
        if var:
            amount = int(float(var.group(1)))
        if amount is None:
            continue
        out.append({"power_id": snake(power), "amount": amount})
    return out


def _relics(relic_dir, pool_dir, eng, zhs):
    pools = _pools(pool_dir, r"ModelDb\.Relic<(\w+)>", "_RELIC_POOL")
    rows = []
    for name in _files(relic_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(relic_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        cid = snake(name[:-3])
        rarity = _enum_value(src, "RelicRarity") or "None"
        start = _combat_start(src)
        base = {"id": cid, "rarity_key": rarity, "pool": pools.get(cid), "combat_start": start}
        en = dict(base, name=_text(eng.get("relics"), cid + ".title") or cid,
                  description=_text(eng.get("relics"), cid + ".description"),
                  rarity=RARITY_ZH.get(rarity, rarity))
        zh = dict(base, name=_text(zhs.get("relics"), cid + ".title") or en["name"],
                  description=_text(zhs.get("relics"), cid + ".description"),
                  rarity=RARITY_ZH.get(rarity, rarity))
        rows.append((en, zh))
    return rows


def _potions(potion_dir, pool_dir, eng, zhs):
    pools = _pools(pool_dir, r"ModelDb\.Potion<(\w+)>", "_POTION_POOL")
    rows = []
    for name in _files(potion_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(potion_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        cid = snake(name[:-3])
        rarity = _enum_value(src, "PotionRarity") or "Common"
        target = TARGET_ZH.get(_enum_value(src, "TargetType") or "", "none")
        base = {"id": cid, "rarity_key": rarity, "target": target, "pool": pools.get(cid)}
        en = dict(base, name=_text(eng.get("potions"), cid + ".title") or cid,
                  description=_text(eng.get("potions"), cid + ".description"),
                  rarity=RARITY_ZH.get(rarity, rarity))
        zh = dict(base, name=_text(zhs.get("potions"), cid + ".title") or en["name"],
                  description=_text(zhs.get("potions"), cid + ".description"),
                  rarity=RARITY_ZH.get(rarity, rarity))
        rows.append((en, zh))
    return rows


def _powers(power_dir, eng, zhs):
    rows = []
    for name in _files(power_dir):
        if _skip(name[:-3]):
            continue
        cls = name[:-3]
        cid = snake(cls.removesuffix("Power"))
        loc_key = cid + "_POWER" if not cid.endswith("_POWER") else cid
        with open(os.path.join(power_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        kind = _enum_value(src, "PowerType") or "Buff"
        base = {"id": cid, "type": kind}
        en = dict(base, name=_text(eng.get("powers"), loc_key + ".title") or cid,
                  description=_text(eng.get("powers"), loc_key + ".description"))
        zh = dict(base, name=_text(zhs.get("powers"), loc_key + ".title") or en["name"],
                  description=_text(zhs.get("powers"), loc_key + ".description"))
        rows.append((en, zh))
    return rows


def _deck_ids(src, prop):
    expr = _prop(src, prop) or ""
    return [snake(name) for name in re.findall(r"ModelDb\.Card<(\w+)>", expr)] if prop == "StartingDeck" else [
        snake(name) for name in re.findall(r"ModelDb\.Relic<(\w+)>", expr)]


def _characters(char_dir, eng, zhs):
    rows = []
    for name in _files(char_dir):
        if _skip(name[:-3]):
            continue
        with open(os.path.join(char_dir, name), encoding="utf-8") as handle:
            src = handle.read()
        cid = snake(name[:-3])
        playable = "bool IsPlayable => false" not in src and "bool IsPlayable=>false" not in src
        energy_expr = _prop(src, "MaxEnergy")
        base = {
            "id": cid,
            "hp": normal_int(_prop(src, "StartingHp"), src),
            "energy": normal_int(energy_expr) if energy_expr else 3,
            "energy_source": "override" if energy_expr else "default",
            "gold": normal_int(_prop(src, "StartingGold"), src),
            "starting_deck": _deck_ids(src, "StartingDeck"),
            "starting_relics": _deck_ids(src, "StartingRelics"),
            "playable": playable,
        }
        en = dict(base, name=_text(eng.get("characters"), cid + ".title") or cid,
                  description=_text(eng.get("characters"), cid + ".description"))
        zh = dict(base, name=_text(zhs.get("characters"), cid + ".title") or en["name"],
                  description=_text(zhs.get("characters"), cid + ".description"))
        rows.append((en, zh))
    return rows


def _models(core):
    root = os.path.join(core, "Models")
    return {
        "monsters": os.path.join(root, "Monsters"),
        "encounters": os.path.join(root, "Encounters"),
        "acts": os.path.join(root, "Acts"),
        "cards": os.path.join(root, "Cards"),
        "card_pools": os.path.join(root, "CardPools"),
        "relics": os.path.join(root, "Relics"),
        "relic_pools": os.path.join(root, "RelicPools"),
        "potions": os.path.join(root, "Potions"),
        "potion_pools": os.path.join(root, "PotionPools"),
        "powers": os.path.join(root, "Powers"),
        "characters": os.path.join(root, "Characters"),
    }


def export_tree(core, eng, zhs, out_dir, dll_sha256, release_info=None):
    """从反编译的 Core 目录和两份本地化表写出 legacy-codex。返回 stamp。"""
    if not dll_sha256 or len(dll_sha256) != 64:
        raise LegacyCodexError("dll_sha256")
    paths = _models(core)
    if not os.path.isdir(paths["monsters"]) or not os.path.isdir(paths["cards"]):
        raise LegacyCodexError("core layout")
    monster_ai, encounters = _tools()
    ai = monster_ai.parse_dir(paths["monsters"])
    compositions = encounters.parse_dir(paths["encounters"]) if os.path.isdir(paths["encounters"]) else {}
    built = {
        "monsters": _monsters(paths["monsters"], ai, eng, zhs),
        "encounters": _encounters(paths["encounters"], paths["acts"], compositions, eng, zhs),
        "cards": _cards(paths["cards"], paths["card_pools"], eng, zhs),
        "relics": _relics(paths["relics"], paths["relic_pools"], eng, zhs),
        "potions": _potions(paths["potions"], paths["potion_pools"], eng, zhs),
        "powers": _powers(paths["powers"], eng, zhs),
        "characters": _characters(paths["characters"], eng, zhs),
    }
    os.makedirs(out_dir, exist_ok=True)
    counts = {}
    for kind, pairs in built.items():
        counts[kind] = len(pairs)
        _dump(os.path.join(out_dir, "eng_" + kind + ".json"), [pair[0] for pair in pairs])
        _dump(os.path.join(out_dir, "zhs_" + kind + ".json"), [pair[1] for pair in pairs])
    straight = sum(1 for en, _zh in built["cards"] if en.get("effects_status") == "straight_line")
    playable = [en["id"] for en, _zh in built["characters"] if en.get("playable")]
    rel = release_info or {}
    stamp = {
        "format": FORMAT,
        "kind": KIND,
        "dll_sha256": dll_sha256,
        "version": rel.get("version"),
        "branch": rel.get("branch"),
        "commit": rel.get("commit"),
        "date": rel.get("date"),
        "counts": counts,
        "straight_line_cards": straight,
        "playable_characters": playable,
        "limits": [
            "hp and move numbers are the non-ascension, non-Dread values",
            "straight-line card effects are damage and block only",
            "arrow ammo is not simulated; from_arrow cards stay playable",
            "Aim adds to from_arrow damage and clears after that hit",
            "other relic, potion and power effects stay index-only",
        ],
        "note": "Generated locally from your own install. Do not redistribute.",
    }
    _dump(os.path.join(out_dir, STAMP), stamp, indent=1)
    return stamp


def read_stamp(directory):
    path = os.path.join(directory, STAMP)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def card_raw(record):
    """索引里能打的牌 → 旧战斗模拟器的 CardDef 原料。没有效果就返回 None。"""
    if not record or not record.get("effects"):
        return None
    raw = {
        "id": record["id"],
        "name": record.get("name") or record["id"],
        "type": record.get("type") or "技能",
        "rarity": record.get("rarity") or "普通",
        "cost": record.get("cost", 1),
        "target": record.get("target") or "none",
        "vars": dict(record.get("vars") or {}),
        "effects": list(record["effects"]),
        "upgrade": record.get("upgrade") or {},
        "text": record.get("description") or "",
    }
    if record.get("tags"):
        raw["tags"] = list(record["tags"])
    return raw


class CodexStartRelic:
    """进战斗时按目录里的 combat_start 施加能力。没写进目录的遗物效果不会出现在这里。"""

    def __init__(self, rid, name, applies):
        from .relics import Relic
        self._relic = Relic()
        self.id = rid
        self.name = name
        self.applies = [(item[0], int(item[1])) for item in applies]
        self.data = {}
        self._on = dict(self._relic._on)
        self._on["on_battle_start"] = CodexStartRelic.on_battle_start

    def on_battle_start(self, combat, _ev):
        for pid, amount in self.applies:
            combat.apply_power(combat.player, pid, amount, source=("relic", self))

    def src(self):
        return ("relic", self)

    def clone(self):
        copied = CodexStartRelic(self.id, self.name, self.applies)
        copied.data = dict(self.data)
        return copied


def load_character(folder, character_id, lang="eng"):
    chars = {row["id"]: row for row in _read(os.path.join(folder, lang + "_characters.json"))}
    cards = {row["id"]: row for row in _read(os.path.join(folder, lang + "_cards.json"))}
    relic_path = os.path.join(folder, lang + "_relics.json")
    relics = {row["id"]: row for row in _read(relic_path)} if os.path.isfile(relic_path) else {}
    if character_id not in chars:
        raise LegacyCodexError("character")
    character = chars[character_id]
    from .cards import CardDef
    defs = []
    skipped = []
    for cid in character.get("starting_deck") or []:
        raw = card_raw(cards.get(cid))
        if raw is None:
            skipped.append(cid)
            continue
        defs.append(CardDef(raw, "legacy"))
    relic_objs = []
    for rid in character.get("starting_relics") or []:
        rec = relics.get(rid) or {}
        applies = [(item["power_id"], item["amount"]) for item in rec.get("combat_start") or []]
        if not applies:
            continue
        relic_objs.append(CodexStartRelic(rid, rec.get("name") or rid, applies))
    return {"character": character, "cards": defs, "skipped": skipped, "relics": relic_objs}


def fight_character(folder, character_id, encounter_id, seed=1, max_turns=12, lang="eng"):
    """用目录里的起始牌组和一场遭遇打一局。随机数只来自 seed。"""
    import random

    from .ai import HeuristicAgent
    from .core import Card, Combat, Player
    from .enemies import build_encounter, load_db
    from .modloader import ModSet

    loaded = load_character(folder, character_id, lang)
    character = loaded["character"]
    db = load_db()
    enc = next(row for row in db["encounters"] if row["id"] == encounter_id)
    rng = random.Random(seed)
    enemies = build_encounter(enc, rng)
    mods = ModSet([])
    player = Player(character.get("name") or character_id, character.get("hp") or 70, character.get("energy") or 3)
    player.draw_pile = [Card(defn) for defn in loaded["cards"]]
    combat = Combat(player, enemies, mods, rng=random.Random(seed), agent=HeuristicAgent(), max_turns=max_turns)
    combat.relics = list(loaded["relics"])
    result = combat.run()
    return {
        "result": result,
        "turns": combat.turn,
        "hp_left": max(0, player.hp),
        "hp": character.get("hp"),
        "skipped": list(loaded["skipped"]),
        "encounter": encounter_id,
    }


def main(argv=None):
    import argparse
    import hashlib
    parser = argparse.ArgumentParser(prog="python -m sts2sim.legacycodex")
    parser.add_argument("--src", required=True, help="反编译出来的 MegaCrit/Sts2/Core 目录")
    parser.add_argument("--loc-eng", required=True)
    parser.add_argument("--loc-zhs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--dll")
    parser.add_argument("--dll-sha256")
    parser.add_argument("--release-info")
    args = parser.parse_args(argv)
    digest = args.dll_sha256
    if args.dll:
        hasher = hashlib.sha256()
        with open(args.dll, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    if not digest:
        raise SystemExit("需要 --dll 或 --dll-sha256")
    rel = {}
    if args.release_info:
        rel = _read(args.release_info)
    eng = _loc_from_dir(args.loc_eng)
    zhs = _loc_from_dir(args.loc_zhs)
    if not eng.get("cards") or not zhs.get("cards"):
        raise SystemExit("本地化目录里没有 cards.json")
    stamp = export_tree(args.src, eng, zhs, args.out, digest, rel)
    print(json.dumps({"out": args.out, "counts": stamp["counts"], "playable_characters": stamp["playable_characters"],
                      "straight_line_cards": stamp["straight_line_cards"], "dll_sha256": digest},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
