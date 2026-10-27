"""从 mod 的 C#（作者源码，或 ilspycmd 反编译结果）里抽出能映射到 YAML 的部分。

只认直线效果。遇到分支、循环或未知调用就留下空效果，避免把「有条件才发动」导入成「必定发动」。
枚举如果被反编译成数字（没有游戏程序集做引用时会这样），不猜测含义。
"""
import re

VAR_TYPES = {"DamageVar": "Damage", "BlockVar": "Block", "CardsVar": "Cards", "EnergyVar": "Energy",
             "PowerVar": "Power", "HealVar": "Heal", "ForgeVar": "Forge", "GoldVar": "Gold"}
TYPE_NAMES = {"Attack", "Skill", "Power", "Status", "Curse"}
RARITY_NAMES = {"Basic", "Common", "Uncommon", "Rare", "Token", "Status", "Curse", "Ancient", "Event", "Starter", "Shop"}
TARGET_NAMES = {"AnyEnemy", "Self", "AllEnemies", "RandomEnemy"}
KEYWORDS = {"Exhaust", "Ethereal", "Retain", "Innate", "Unplayable"}
HOOKS = {"AfterTurnStart": "turn_start", "BeforeTurnStart": "turn_start", "AtStartOfTurn": "turn_start",
         "AfterTurnEnd": "turn_end", "BeforeTurnEnd": "turn_end", "AtEndOfTurn": "turn_end",
         "BeforeCombat": "battle_start", "AfterCombatStarted": "battle_start", "AtBattleStart": "battle_start",
         "BeforeCombatStart": "battle_start"}
MODEL_BASES = {"CardModel": "card", "PowerModel": "power", "RelicModel": "relic",
               "PotionModel": "potion", "CharacterModel": "character"}
_NUM = re.compile(r"^-?\d+(?:\.\d+)?[mMfFdDlL]?$")
_CONTROL = re.compile(r"\b(if|for|foreach|switch|while|try|catch|throw|goto|lock)\b")


def scream(name):
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", str(name))
    s = re.sub(r"[^0-9A-Za-z_]+", "_", s).strip("_")
    return (s or "MOD").upper()


def pretty(name):
    return re.sub(r"(?<!^)(?=[A-Z])", " ", str(name)).replace("_", " ").strip()


def mask(src):
    """注释和字符串换成空格，长度不变，方便配对括号。"""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if src[i] == "$" and i + 1 < n and src[i + 1] == '"':
            out[i] = " "
            i += 1
        if src[i] == "@" and i + 1 < n and src[i + 1] == '"':
            out[i] = " "
            i += 1
            i = _skip_verbatim(src, out, i)
            continue
        if src[i] in "\"'":
            q = src[i]
            out[i] = " "
            i += 1
            while i < n:
                if src[i] == "\\":
                    out[i] = " "
                    i += 1
                    if i < n:
                        out[i] = " "
                        i += 1
                    continue
                if src[i] == q:
                    out[i] = " "
                    i += 1
                    break
                out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def _skip_verbatim(src, out, i):
    n = len(src)
    out[i] = " "
    i += 1
    while i < n:
        if src.startswith('""', i):
            out[i] = out[i + 1] = " "
            i += 2
            continue
        if src[i] == '"':
            out[i] = " "
            return i + 1
        out[i] = " "
        i += 1
    return i


def _brace_end(masked, open_at):
    depth = 0
    for i in range(open_at, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(masked)


def _paren_end(text, open_at):
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def split_args(s):
    args, depth, start = [], 0, 0
    for i, c in enumerate(s):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == "," and depth == 0:
            args.append(s[start:i])
            start = i + 1
    tail = s[start:]
    if tail.strip():
        args.append(tail)
    return args


def _num(s):
    t = s.strip().rstrip("mMfFdDlL")
    f = float(t)
    return int(f) if f == int(f) else f


def clean_expr(e):
    e = re.sub(r"\s+", "", e)
    prev = None
    while e != prev:
        prev = e
        e = re.sub(r"\([^()]*\)", "", e)
    e = e.replace("base.", "").replace("this.", "").lstrip(".")
    return e


def amount_of(expr):
    e = clean_expr(expr)
    m = re.fullmatch(r"DynamicVars\.([A-Za-z_][A-Za-z0-9_]*)(?:\.BaseValue)?", e)
    if m:
        return m.group(1)
    m = re.fullmatch(r'DynamicVars\["([A-Za-z_][A-Za-z0-9_]*)"\](?:\.BaseValue)?', e)
    if m:
        return m.group(1)
    if _NUM.fullmatch(e):
        return _num(e)
    return None


def enum_name(arg):
    a = re.sub(r"\s+", "", arg or "")
    if not a or a.startswith("(") or re.search(r"\)\d+$", a):
        return None
    m = re.fullmatch(r"(?:[A-Za-z_][A-Za-z0-9_]*\.)*([A-Za-z_][A-Za-z0-9_]*)", a)
    return m.group(1) if m else None


def iter_types(src):
    """产出 (name, bases, body)。嵌套类型单独产出，并且从外层正文里抠掉。"""
    masked = mask(src)
    found = []
    for m in re.finditer(r"\b(?:class|struct|record)\s+([A-Za-z_][A-Za-z0-9_]*)\b", masked):
        name = m.group(1)
        if name.startswith("_003C") or "ReadOnly" in name and name.startswith("z__"):
            continue
        j = m.end()
        while j < len(masked) and masked[j] != "{" and masked[j] != ";":
            j += 1
        if j >= len(masked) or masked[j] != "{":
            continue
        end = _brace_end(masked, j)
        header = src[m.end():j]
        body = src[j + 1:end - 1]
        found.append((m.start(), end, name, header, body))
    found.sort(key=lambda t: t[0])
    spans = [(a, b) for a, b, *_ in found]
    out = []
    for i, (a, b, name, header, body) in enumerate(found):
        inner = [(x, y) for x, y, *_ in found[i + 1:] if a < x and y <= b]
        # body 起点是 a 所在 `{` 之后；inner 是全文坐标
        open_at = masked.find("{", a)
        blanked = body
        if inner and open_at >= 0:
            chars = list(body)
            for x, y in inner:
                lo, hi = x - (open_at + 1), y - (open_at + 1)
                for k in range(max(0, lo), min(len(chars), hi)):
                    if chars[k] != "\n":
                        chars[k] = " "
            blanked = "".join(chars)
        bases = _bases(header)
        out.append({"name": name, "bases": bases, "body": blanked, "header": header})
    return out


def _bases(header):
    h = header.split("where", 1)[0]
    if ":" not in h:
        return []
    rest = h.split(":", 1)[1]
    parts, depth, start = [], 0, 0
    for i, c in enumerate(rest):
        if c == "<":
            depth += 1
        elif c == ">":
            depth = max(0, depth - 1)
        elif c == "," and depth == 0:
            parts.append(rest[start:i])
            start = i + 1
    parts.append(rest[start:])
    names = []
    for p in parts:
        p = p.strip().rstrip("{").strip()
        if not p:
            continue
        names.append(re.split(r"[<\s]", p)[0].split(".")[-1])
    return names


def _member(body, name):
    masked = mask(body)
    for m in re.finditer(r"\b" + re.escape(name) + r"\b", masked):
        if m.start() and masked[m.start() - 1] == ".":
            continue
        j = m.end()
        while j < len(masked) and masked[j].isspace():
            j += 1
        if j >= len(masked):
            continue
        if masked[j] == "<":
            continue
        if masked[j] == "(":
            end = _paren_end(masked, j)
            k = end
            while k < len(masked) and masked[k].isspace():
                k += 1
            if k < len(masked) and masked[k] == "{":
                bend = _brace_end(masked, k)
                return body[k + 1:bend - 1]
            if masked.startswith("=>", k):
                return _until_semi(body, masked, k + 2)
            continue
        if masked.startswith("=>", j):
            return _until_semi(body, masked, j + 2)
        if masked[j] == "{":
            bend = _brace_end(masked, j)
            return body[j + 1:bend - 1]
    return None


def _until_semi(body, masked, i):
    depth = 0
    for k in range(i, len(masked)):
        if masked[k] in "([{":
            depth += 1
        elif masked[k] in ")]}":
            depth = max(0, depth - 1)
        elif masked[k] == ";" and depth == 0:
            return body[i:k]
    return body[i:]


def _statements(body):
    if body is None:
        return []
    masked = mask(body)
    stmts, depth, start = [], 0, 0
    i = 0
    while i < len(masked):
        c = masked[i]
        if c == "{" and depth == 0:
            chunk = body[start:i].strip()
            if chunk:
                stmts.append(chunk)
            depth = 1
            bstart = i
            i += 1
            while i < len(masked) and depth:
                if masked[i] == "{":
                    depth += 1
                elif masked[i] == "}":
                    depth -= 1
                i += 1
            stmts.append(body[bstart:i].strip())
            start = i
            continue
        if c == ";" and depth == 0:
            chunk = body[start:i].strip()
            if chunk:
                stmts.append(chunk)
            start = i + 1
        i += 1
    tail = body[start:].strip()
    if tail:
        stmts.append(tail)
    return [s for s in stmts if s and s not in ("{", "}")]


def _controlled(stmt):
    s = re.sub(r"\?\.", "", stmt)
    if "?" in s:
        return True
    return bool(_CONTROL.search(stmt))


def _call(flat, name):
    key = name + "("
    i = flat.find(key)
    if i < 0:
        return None, ""
    open_at = i + len(name)
    end = _paren_end(flat, open_at)
    return flat[open_at + 1:end - 1], flat[end:]


def _effect(stmt):
    if _controlled(stmt):
        return None
    f = re.sub(r"\s+", "", stmt).rstrip(";")
    if not f or f == "return":
        return {"op": "nop"}
    args, rest = _call(f, "DamageCmd.Attack")
    if args is not None and "DamageCmd.Attack" in f:
        parts = split_args(args)
        amt = amount_of(parts[0]) if parts else None
        if amt is None:
            return None
        eff = {"op": "damage", "amount": amt}
        hm = re.search(r"\.WithHitCount\(([^)]*)\)", rest)
        if hm:
            hits = amount_of(hm.group(1))
            if hits not in (None, 1):
                eff["hits"] = hits
        if "AllEnemies" in rest or "TargetingAll" in rest:
            eff["target"] = "all"
        return eff
    args, _rest = _call(f, "CreatureCmd.GainBlock")
    if args is not None:
        parts = split_args(args)
        amt = amount_of(parts[1]) if len(parts) > 1 else None
        return {"op": "block", "amount": amt} if amt is not None else None
    args, _rest = _call(f, "CardPileCmd.Draw")
    if args is not None:
        parts = split_args(args)
        n = amount_of(parts[1]) if len(parts) > 1 else (amount_of(parts[0]) if parts else None)
        return {"op": "draw", "n": n} if n is not None else None
    args, _rest = _call(f, "PlayerCmd.GainEnergy")
    if args is not None:
        parts = split_args(args)
        n = amount_of(parts[0]) if parts else None
        return {"op": "energy", "n": n} if n is not None else None
    args, _rest = _call(f, "PlayerCmd.LoseEnergy")
    if args is not None:
        parts = split_args(args)
        n = amount_of(parts[0]) if parts else None
        return {"op": "energy", "n": -n if isinstance(n, (int, float)) else None} if isinstance(n, (int, float)) else None
    args, _rest = _call(f, "CreatureCmd.Heal")
    if args is not None:
        parts = split_args(args)
        amt = amount_of(parts[1]) if len(parts) > 1 else None
        return {"op": "heal", "amount": amt} if amt is not None else None
    m = re.search(r"PowerCmd\.Apply<([A-Za-z_][A-Za-z0-9_]*)>\(", f)
    if m:
        open_at = m.end() - 1
        end = _paren_end(f, open_at)
        parts = split_args(f[open_at + 1:end - 1])
        amt = amount_of(parts[2]) if len(parts) > 2 else (amount_of(parts[0]) if parts else None)
        if amt is None:
            return None
        target = "target" if len(parts) > 1 and "Target" in parts[1] else "self"
        return {"op": "apply", "power_class": m.group(1), "amount": amt, "target": target}
    return None


def _effects_of(body):
    """(effects or None, partial)。None 表示整段不能安全导入。"""
    if body is None:
        return [], False
    effects = []
    for stmt in _statements(body):
        eff = _effect(stmt)
        if eff is None:
            return None, True
        if eff.get("op") != "nop":
            effects.append(eff)
    return effects, False


def _vars_of(body):
    if not body:
        return {}
    out = {}
    f = body
    i = 0
    while True:
        m = re.search(r"\bnew\s+(DamageVar|BlockVar|CardsVar|EnergyVar|PowerVar|HealVar|ForgeVar|GoldVar|DynamicVar)\s*\(", f[i:])
        if not m:
            break
        open_at = i + m.end() - 1
        end = _paren_end(f, open_at)
        args = split_args(f[open_at + 1:end - 1])
        kind = m.group(1)
        if kind == "DynamicVar" and args:
            sm = re.search(r'"([^"]+)"', args[0])
            name = sm.group(1) if sm else None
            val = amount_of(args[1]) if len(args) > 1 else None
        else:
            name = VAR_TYPES.get(kind)
            val = amount_of(args[0]) if args else None
        if name and isinstance(val, (int, float)) and name not in out:
            out[name] = val
        i = end
    return out


def _only_receiver(prefix):
    """调用前面只允许强制转换、base. 和 this.。"""
    g = prefix
    prev = None
    while g != prev:
        prev = g
        g = re.sub(r"\([^()]*\)", "", g)
    g = re.sub(r"(?:base|this)\.", "", g).replace(".", "")
    return g == ""


def _upgrades(body, base_vars, cost):
    if body is None or not str(body).strip():
        return {}, None, False
    up_vars, up_cost = {}, None
    for stmt in _statements(body):
        f = re.sub(r"\s+", "", stmt).rstrip(";")
        i = f.find("DynamicVars.")
        j = f.find("EnergyCost.UpgradeBy(")
        if i >= 0 and _only_receiver(f[:i]):
            rest = f[i:]
            m = re.match(r"DynamicVars\.([A-Za-z_][A-Za-z0-9_]*)\.UpgradeValueBy\(", rest)
            if not m:
                return {}, None, True
            open_at = m.end() - 1
            end = _paren_end(rest, open_at)
            if end != len(rest):
                return {}, None, True
            delta = amount_of(rest[open_at + 1:end - 1])
            name = m.group(1)
            if not isinstance(delta, (int, float)) or name not in base_vars:
                return {}, None, True
            up_vars[name] = base_vars[name] + delta
            continue
        if j >= 0 and _only_receiver(f[:j]):
            rest = f[j:]
            open_at = len("EnergyCost.UpgradeBy")
            end = _paren_end(rest, open_at)
            if end != len(rest):
                return {}, None, True
            delta = amount_of(rest[open_at + 1:end - 1])
            if not isinstance(delta, int) or not isinstance(cost, int):
                return {}, None, True
            up_cost = cost + delta
            continue
        return {}, None, True
    return up_vars, up_cost, False


def _ctor(body):
    m = re.search(r"\bbase\s*\(", body)
    if not m:
        return {}
    end = _paren_end(body, m.end() - 1)
    args = split_args(body[m.end():end - 1])
    named = {}
    pos = []
    for a in args:
        if ":" in a.split("(")[0] and re.match(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*:", a):
            k, v = a.split(":", 1)
            named[k.strip()] = v.strip()
        else:
            pos.append(a.strip())
    def pick(key, idx):
        return named.get(key, pos[idx] if idx < len(pos) else None)
    cost_raw = pick("canonicalEnergyCost", 0)
    show_raw = pick("shouldShowInCardLibrary", 4)
    cost = amount_of(cost_raw) if cost_raw else None
    show = None
    if show_raw:
        s = re.sub(r"\s+", "", show_raw).lower()
        if s in ("true", "false"):
            show = s == "true"
    return {"cost": cost if isinstance(cost, int) else None, "cost_known": isinstance(cost, int),
            "type": enum_name(pick("type", 1) or ""), "rarity": enum_name(pick("rarity", 2) or ""),
            "target": enum_name(pick("targetType", 3) or ""), "show": show,
            "header_ordinal": any(v and enum_name(v) is None and re.search(r"\)\s*\d+", v or "")
                               for v in (pick("type", 1), pick("rarity", 2), pick("targetType", 3)))}


def _keywords(body):
    if not body:
        return [], False
    names = re.findall(r"CardKeyword\.([A-Za-z_][A-Za-z0-9_]*)", body)
    ordinal = bool(re.search(r"\(CardKeyword\)\s*\d+", body))
    return [n for n in names if n in KEYWORDS], ordinal


def _tags(body):
    if not body:
        return []
    return [n for n in re.findall(r"CardTag\.([A-Za-z_][A-Za-z0-9_]*)", body) if n in ("Strike", "Defend")]


def _enum_in(body, prefix):
    if not body:
        return None
    m = re.search(prefix + r"\.([A-Za-z_][A-Za-z0-9_]*)", body)
    return m.group(1) if m else None


def _int_prop(body, name):
    member = _member(body, name)
    if member is None:
        return None
    m = re.search(r"-?\d+", re.sub(r"\s+", "", member))
    return int(m.group(0)) if m else None


def _straight(body, card_target):
    effects, partial = _effects_of(body)
    if effects is None:
        return [], True
    out = []
    for e in effects:
        e = dict(e)
        if e.get("op") == "damage" and "target" not in e and card_target == "AllEnemies":
            e["target"] = "all"
        elif e.get("op") == "damage" and "target" not in e and card_target == "RandomEnemy":
            e["target"] = "random"
        if e.get("op") == "apply" and e.get("target") == "self":
            e.pop("target", None)
        out.append(e)
    return out, partial


def parse_sources(files):
    """files: {路径: 文本}。返回 {class_name: spec} 和 registrations。"""
    specs = {}
    regs = []
    ordinal = False
    for _path, text in files.items():
        if not text or "class " not in text and "struct " not in text:
            continue
        regs += re.findall(r"AddModelToPool\s*<\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*>", text)
        for t in iter_types(text):
            kind = next((MODEL_BASES[b] for b in t["bases"] if b in MODEL_BASES), None)
            if not kind or t["name"] in specs:
                continue
            spec = _parse_type(t, kind)
            ordinal = ordinal or spec.pop("_ordinal", False)
            specs[t["name"]] = spec
    return specs, regs, ordinal


def _parse_type(t, kind):
    body = t["body"]
    notes = []
    ctor = _ctor(body) if kind in ("card", "potion") else {}
    ordinal = bool(ctor.get("header_ordinal"))
    vars_ = _vars_of(_member(body, "CanonicalVars"))
    cost = ctor.get("cost") if ctor.get("cost_known") else None
    up_vars, up_cost, up_partial = _upgrades(_member(body, "OnUpgrade"), vars_, cost if cost is not None else ctor.get("cost"))
    kws, kw_ordinal = _keywords(_member(body, "CanonicalKeywords"))
    ordinal = ordinal or kw_ordinal
    play_name = {"card": "OnPlay", "potion": "OnUse"}.get(kind)
    effects, partial = ([], False)
    if kw_ordinal:
        partial = True
    if play_name:
        effects, partial = _straight(_member(body, play_name), ctor.get("target"))
    triggers = []
    if kind in ("power", "relic"):
        for hook, on in HOOKS.items():
            member = _member(body, hook)
            if member is None:
                continue
            do, bad = _straight(member, None)
            if bad or not do:
                partial = True
                continue
            triggers.append({"on": on, "do": do})
    if up_partial:
        partial = True
        up_vars, up_cost = {}, None
    type_name = ctor.get("type") if ctor.get("type") in TYPE_NAMES else None
    rarity = ctor.get("rarity") if ctor.get("rarity") in RARITY_NAMES else None
    target = ctor.get("target") if ctor.get("target") in TARGET_NAMES else None
    if kind == "relic":
        rarity = _enum_in(body, "RelicRarity") or rarity
        if rarity not in RARITY_NAMES:
            rarity = None
    header_ok = kind not in ("card", "potion") or (type_name and rarity and target and cost is not None)
    if kind == "card" and not header_ok:
        partial = True
    if kind in ("power", "relic") and not triggers:
        partial = True
    status = "partial" if partial or not header_ok else "translated"
    if kind == "card" and play_name and _member(body, play_name) is None and not effects:
        status = "partial"
    return {
        "class_name": t["name"], "kind": kind, "status": status, "notes": notes,
        "cost": cost, "type": type_name, "rarity": rarity, "target": target,
        "keywords": kws, "tags": _tags(_member(body, "CanonicalTags")), "vars": vars_,
        "upgrade_vars": up_vars, "upgrade_cost": up_cost, "effects": effects, "triggers": triggers,
        "stack": (_enum_in(body, "PowerStackType") or "Counter"),
        "power_type": _enum_in(body, "PowerType") or "Buff",
        "show": ctor.get("show", True),
        "hp": _int_prop(body, "StartingHp"), "energy": _int_prop(body, "MaxEnergy") or _int_prop(body, "BaseEnergy"),
        "gold": _int_prop(body, "StartingGold"), "starting_deck": _deck(body),
        "_ordinal": ordinal,
    }


def _deck(body):
    member = _member(body, "StartingDeck")
    if not member:
        return []
    names = re.findall(r"Card\s*<\s*([A-Za-z_][A-Za-z0-9_]*)\s*>", member)
    names += re.findall(r"\bnew\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", member)
    return names


def note_pair(status, ordinal, kind, kept=False):
    if status == "inventory":
        return ("只从 DLL 的类型表读到了这个类，没有读到方法体。费用、类型和效果都还不能拿来测试。",
                "Only the class was read from DLL metadata, not its method body. Cost, type and effects are not safe to test yet.")
    bits_z, bits_e = [], []
    if ordinal and kind == "card":
        bits_z.append("构造函数里的类型、稀有度或目标被反编译成了数字，没有拿来猜测。")
        bits_e.append("Type, rarity or target was decompiled as a number and was not guessed.")
    if status == "partial":
        if kept:
            bits_z.append("认得出的直线效果已经留下。其余的分支或还没对应的命令留空，没有当成每次都发动。")
            bits_e.append("Straight-line effects that were recognized are kept. Anything else (a branch or a command DeckBench does not map yet) was left blank, and was not imported as if it always happens.")
        else:
            bits_z.append("有认不出的代码（分支或还不支持的命令）。为了不把「有时发动」写成「每次都发动」，没把握的效果留空。")
            bits_e.append("Some code was not recognized (a branch or a command DeckBench does not map yet). Uncertain effects were left blank so a conditional effect is not imported as if it always happens.")
    elif status == "translated":
        bits_z.append("费用、类型和直线效果已导入。")
        bits_e.append("Cost, type and straight-line effects were imported.")
    if not bits_z:
        return ("", "")
    return ("".join(bits_z), " ".join(bits_e))
