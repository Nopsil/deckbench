"""YAML 数据 mod：格式表、读取、规范化、校验。

一个 mod 是一个文件夹（或 zip）：
  mod.yaml          名字、角色、要读哪些文件、辅助表达式、AI 提示
  cards.yaml        卡牌（效果用 op 列表 + 模板）
  powers.yaml       能力（触发器 + 模板）          ← 整局新增
  relics.yaml       遗物（触发器 + 模板）          ← 整局新增（也可以直接写在 mod.yaml 的 relics: 里）
  potions.yaml      药水（可选）
  hooks.py          旧版 YAML 战斗模拟器的 Python 钩子（整局不用）
  fullrun_hooks.py  整局用的 Python 钩子（可选，模板写不出来时的后门）

这里只做“读文件 + 检查”，不依赖游戏代码；图形界面、测试、整局引擎都用它。所有错误信息是中英双语的大白话。
"""
import ast
import io
import os
import re
import zipfile

import yaml


class ModFormatError(Exception):
    """problems: [(位置, 中文, English)]"""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__(self.text())

    def text(self, lang="zhs"):
        out = []
        for where, zh, en in self.problems:
            msg = zh if lang.startswith("zh") else en
            out.append(f"- {where}: {msg}" if where else f"- {msg}")
        return "\n".join(out)


# ---------------------------------------------------------------- 名称规范化（中英都认）
RARITY = {"基础": "Basic", "初始": "Basic", "普通": "Common", "罕见": "Uncommon", "稀有": "Rare", "特殊": "Token",
          "生成": "Token", "衍生": "Token", "状态": "Status", "诅咒": "Curse", "先古之民": "Ancient", "远古": "Ancient",
          "事件": "Event"}
RARITIES = ("Basic", "Common", "Uncommon", "Rare", "Token", "Status", "Curse", "Ancient", "Event")
TYPE = {"攻击": "Attack", "技能": "Skill", "能力": "Power", "状态": "Status", "诅咒": "Curse"}
TYPES = ("Attack", "Skill", "Power", "Status", "Curse")
TARGET = {"enemy": "AnyEnemy", "self": "Self", "none": "Self", "all": "AllEnemies", "random": "RandomEnemy",
          "anyenemy": "AnyEnemy", "allenemies": "AllEnemies", "randomenemy": "RandomEnemy"}
TARGETS = ("AnyEnemy", "Self", "AllEnemies", "RandomEnemy")
KEYWORD = {"消耗": "Exhaust", "虚无": "Ethereal", "保留": "Retain", "固有": "Innate", "不能被打出": "Unplayable",
           "exhaust": "Exhaust", "ethereal": "Ethereal", "retain": "Retain", "innate": "Innate", "unplayable": "Unplayable",
           "replay": "Replay"}
KEYWORDS = ("Exhaust", "Ethereal", "Retain", "Innate", "Unplayable")
RELIC_RARITY = {"初始": "Starter", "普通": "Common", "罕见": "Uncommon", "稀有": "Rare", "商店": "Shop", "事件": "Event",
                "先古之民": "Ancient", "远古": "Ancient", "starter": "Starter", "common": "Common", "uncommon": "Uncommon",
                "rare": "Rare", "shop": "Shop", "event": "Event", "ancient": "Ancient"}
RELIC_RARITIES = ("Starter", "Common", "Uncommon", "Rare", "Shop", "Event", "Ancient")
POTION_RARITY = {"普通": "Common", "罕见": "Uncommon", "稀有": "Rare", "common": "Common", "uncommon": "Uncommon", "rare": "Rare"}


def _norm(table, allowed, v, default):
    if v is None:
        return default
    s = str(v).strip()
    if s in allowed:
        return s
    if s in table:
        return table[s]
    low = s.lower()
    if low in table:
        return table[low]
    for a in allowed:
        if a.lower() == low:
            return a
    return None


def norm_rarity(v):
    return _norm(RARITY, RARITIES, v, "Common")


def norm_type(v):
    return _norm(TYPE, TYPES, v, "Skill")


def norm_target(v):
    return _norm(TARGET, TARGETS, v, "Self")


def norm_keyword(v):
    return _norm(KEYWORD, KEYWORDS + ("Replay",), v, None)


# ---------------------------------------------------------------- 格式表（文档 / 图形界面 / 校验共用）
# 参数类型：expr 数字或表达式；int 整数；power 能力 ID；card 卡牌 ID；target 目标；ops 效果列表；bool；str；choice:<a|b>
TARGET_SPECS = ("target", "self", "all", "others", "random", "random_other")
OPS = {
    "damage": {"amount": ("expr", True), "hits": ("expr", False, 1), "target": ("target", False, "target"),
               "kind": ("choice:attack|unpowered|hp_loss", False, None), "each_hit": ("ops", False)},
    "block": {"amount": ("expr", True)},
    "apply": {"power": ("power", True), "amount": ("expr", True), "target": ("target", False, "target"),
              "secondary": ("bool", False, False), "active": ("bool", False, None), "remember": ("expr", False)},
    "remove_power": {"power": ("power", True), "amount": ("expr", False), "target": ("target", False, "target"),
                     "save": ("str", False)},
    "set_stacks": {"power": ("power", True), "value": ("expr", True), "target": ("target", False, "target")},
    "draw": {"n": ("expr", True)},
    "energy": {"n": ("expr", True)},
    "lose_hp": {"amount": ("expr", True), "target": ("target", False, "self")},
    "heal": {"amount": ("expr", True)},
    "add_card": {"card": ("card", True), "n": ("expr", False, 1), "to": ("choice:hand|draw|discard", False, "hand"),
                 "upgraded": ("bool", False, False)},
    "set": {"name": ("str", True), "value": ("expr", True)},
    "if": {"cond": ("expr", True), "then": ("ops", False), "else": ("ops", False)},
    "foreach": {"target": ("target", False, "all"), "do": ("ops", True)},
    "repeat": {"n": ("expr", True), "do": ("ops", True)},
    "exhaust_choice": {"n": ("expr", False, 1), "save": ("str", False)},
    "discard_choice": {"n": ("expr", False, 1)},
    "pick_from_pile": {"pile": ("choice:draw|discard|exhaust", False, "draw"), "look": ("expr", False, 3),
                       "n": ("expr", False, 1)},
    "exhaust_hand": {"save": ("str", False)},
    "return_to_hand": {},
    "end_turn": {},
    "py": {"fn": ("str", True)},
}
# 每个效果都可以带：if（条件）、once（turn 每回合一次〔同名牌共用〕/ turn_instance 每张牌每回合一次 /
#                    card_play 每次打出一次 / attacker_turn 每个攻击者每回合一次）
EFFECT_COMMON = ("op", "if", "once", "note", "template")
ONCE = ("turn", "turn_instance", "card_play", "attacker_turn", "combat")

# 卡牌效果模板：展开成上面的 op（写 {template: 名字, 参数...} 或 {op: 名字, 参数...} 都行）
TEMPLATES = {
    "scaled_damage": {"base": ("expr", True), "power": ("power", True), "per": ("expr", False, 1),
                      "cap": ("expr", False, 999), "hits": ("expr", False, 1), "on": ("choice:target|self", False, "target")},
    "cash_in": {"power": ("power", True), "per": ("expr", True), "cap": ("expr", False, 999),
                "target": ("choice:target|all", False, "target"), "save": ("str", False)},
    "gain_power": {"power": ("power", True), "amount": ("expr", False, 1)},
    "multiply_stacks": {"power": ("power", True), "times": ("expr", False, 2), "cap": ("expr", False, 999),
                        "target": ("target", False, "target")},
    "if_stacks": {"power": ("power", True), "at_least": ("expr", False, 1), "on": ("choice:target|self", False, "target"),
                  "then": ("ops", False), "else": ("ops", False)},
}

# 能力 / 遗物的触发器（on: 名字）
TRIGGERS = {
    "turn_start": {}, "turn_end": {}, "battle_start": {},
    "attacked": {"timing": ("choice:before|after", False, "after")},
    "card_played": {"card_type": ("choice:any|Attack|Skill|Power", False, "any"), "every": ("int", False, 1)},
    "stacks_reach": {"n": ("int", True), "reset": ("choice:subtract|remove|keep", False, "subtract")},
    "power_applied": {"power": ("power", False), "active_only": ("bool", False, False)},
    "power_removed": {"power": ("power", False)},
    "enemy_died": {},
    "card_exhausted": {},
    "modify_damage": {"add": ("expr", False), "mult": ("expr", False)},
    "modify_block": {"add": ("expr", False)},
    "modify_apply": {"power": ("power", True), "add": ("expr", True)},
    "play_count": {"card_type": ("choice:any|Attack|Skill|Power", False, "Attack"), "extra": ("int", False, 1)},
}
TRIGGER_COMMON = ("on", "do", "if", "once", "note", "template")

# 触发器模板（大白话名字 → 触发器），写 {template: 名字, ...}
TRIGGER_TEMPLATES = {
    "at_turn_start": ("turn_start", {"do": ("ops", True)}),
    "at_turn_end": ("turn_end", {"do": ("ops", True)}),
    "at_battle_start": ("battle_start", {"do": ("ops", True)}),
    "every_n_cards": ("card_played", {"n": ("int", True), "card_type": ("choice:any|Attack|Skill|Power", False, "any"),
                                      "do": ("ops", True)}),
    "stacks_reach": ("stacks_reach", {"n": ("int", True), "reset": ("choice:subtract|remove|keep", False, "subtract"),
                                      "do": ("ops", True)}),
    "on_attacked": ("attacked", {"timing": ("choice:before|after", False, "after"), "do": ("ops", True)}),
    "thorns": ("attacked", {"amount": ("expr", True)}),
    "bonus_damage": ("modify_damage", {"add": ("expr", True)}),
    "bonus_block": ("modify_block", {"add": ("expr", True)}),
    "boost_apply": ("modify_apply", {"power": ("power", True), "add": ("expr", True)}),
    "on_power_applied": ("power_applied", {"power": ("power", False), "active_only": ("bool", False, False),
                                           "do": ("ops", True)}),
    "on_power_removed": ("power_removed", {"power": ("power", False), "do": ("ops", True)}),
    "on_enemy_died": ("enemy_died", {"do": ("ops", True)}),
    "replay_first": ("play_count", {"card_type": ("choice:any|Attack|Skill|Power", False, "Attack")}),
}

# 表达式里能用的名字（整局引擎实现，见 sts2sim/engine/yamlmod.py）
EXPR_NAMES = {
    "min", "max", "abs", "int", "floor", "ceil", "round", "len", "sum", "any", "all", "True", "False", "None",
    "T", "P", "card", "upgraded", "amount", "n", "active", "card_paid", "damage", "multi",
    "stacks", "memory", "intent_damage", "attacking", "hand_size", "draw_size", "discard_size", "exhaust_size",
    "n_enemies", "enemies", "energy", "block", "hp", "max_hp", "alive", "hand_has", "turn", "sum_stacks",
    "max_stacks", "count_with", "plays_this_turn", "cards_played_this_turn",
}


def expand_template(eff):
    """卡牌效果模板 → op 列表。"""
    name = eff.get("template") or eff.get("op")
    p = dict(eff)
    for k in ("template", "op"):
        p.pop(k, None)
    common = {k: p.pop(k) for k in ("if", "once", "note") if k in p}
    pw = p.get("power")
    if name == "scaled_damage":
        who = "T" if p.get("on", "target") == "target" else "P"
        amt = f"({p['base']}) + min(({p.get('cap', 999)}), ({p.get('per', 1)}) * stacks({who}, '{pw}'))"
        out = [{"op": "damage", "amount": amt, "hits": p.get("hits", 1)}]
    elif name == "cash_in":
        save = p.get("save", "_k")
        one = [{"op": "remove_power", "power": pw, "save": save},
               {"op": "if", "cond": f"{save} > 0",
                "then": [{"op": "damage", "amount": f"min({save}, ({p.get('cap', 999)})) * ({p['per']})"}]}]
        out = one if p.get("target", "target") == "target" else [{"op": "foreach", "target": "all", "do": one}]
    elif name == "gain_power":
        out = [{"op": "apply", "power": pw, "amount": p.get("amount", 1), "target": "self"}]
    elif name == "multiply_stacks":
        t = p.get("times", 2)
        out = [{"op": "set_stacks", "power": pw, "target": p.get("target", "target"),
                "value": f"stacks(T, '{pw}') + min(stacks(T, '{pw}') * (({t}) - 1), ({p.get('cap', 999)}))"}]
    elif name == "if_stacks":
        who = "T" if p.get("on", "target") == "target" else "P"
        out = [{"op": "if", "cond": f"stacks({who}, '{pw}') >= ({p.get('at_least', 1)})",
                "then": p.get("then") or [], "else": p.get("else") or []}]
    else:
        raise KeyError(name)
    if common:
        if len(out) == 1:
            out[0].update(common)
        else:
            out = [{"op": "if", "cond": common.pop("if", "True"), "then": out, **common}]
    return out


def expand_trigger(tr):
    """触发器模板 → 触发器。"""
    name = tr.get("template")
    if not name:
        return dict(tr)
    on, _params = TRIGGER_TEMPLATES[name]
    out = {k: v for k, v in tr.items() if k != "template"}
    out["on"] = on
    if name == "every_n_cards":
        out["every"] = out.pop("n")
    elif name == "thorns":
        out["timing"] = "after"
        out["do"] = [{"op": "damage", "amount": out.pop("amount"), "target": "target", "kind": "unpowered"}]
    elif name == "replay_first":
        out.setdefault("once", "turn")
        out["extra"] = 1
    return out


# ---------------------------------------------------------------- 读取
def _y(text, where):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f"第 {mark.line + 1} 行 / line {mark.line + 1}" if mark else ""
        raise ModFormatError([(where, f"YAML 写法有错（{line}）：{getattr(e, 'problem', e)}",
                               f"YAML syntax error ({line}): {getattr(e, 'problem', e)}")])


def load_mod_dir(path):
    files = {}
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            if f.endswith((".yaml", ".yml", ".py", ".json", ".md")):
                rel = os.path.relpath(os.path.join(dp, f), path).replace(os.sep, "/")
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    files[rel] = fh.read()
    if "mod.yaml" not in files:
        raise ModFormatError([(path, "这个文件夹里没有 mod.yaml", "no mod.yaml in this folder")])
    m = load_mod_files(files)
    m["_dir"] = os.path.abspath(path)
    return m


def load_mod_zip(data):
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = [n for n in zf.namelist() if not n.endswith("/")]
    tops = [n for n in names if n.endswith("mod.yaml")]
    if not tops:
        raise ModFormatError([("zip", "压缩包里找不到 mod.yaml", "mod.yaml not found in the zip")])
    root = min(tops, key=len)[:-len("mod.yaml")]
    files = {n[len(root):]: zf.read(n).decode("utf-8") for n in names if n.startswith(root)
             and n.endswith((".yaml", ".yml", ".py", ".json", ".md"))}
    return load_mod_files(files)


def _list_or_files(v, files, where, problems):
    """mod.yaml 里的 cards/powers/relics/potions：可以是文件名列表，也可以直接写内容列表。"""
    out = []
    for i, it in enumerate(v or []):
        if isinstance(it, str):
            if it not in files:
                problems.append((where, f"找不到文件 {it}", f"file not found: {it}"))
                continue
            data = _y(files[it], it) or []
            if isinstance(data, dict):
                data = [data]
            for d in data:
                if isinstance(d, dict):
                    d.setdefault("_file", it)
                    out.append(d)
        elif isinstance(it, dict):
            it.setdefault("_file", "mod.yaml")
            out.append(it)
        else:
            problems.append((f"{where}[{i}]", "应该是文件名或一项定义", "expected a file name or an entry"))
    return out


def load_mod_files(files):
    """files: {相对路径: 文本}。返回规范化后的 mod 字典；有严重问题抛 ModFormatError。"""
    problems = []
    meta = _y(files["mod.yaml"], "mod.yaml") or {}
    if not isinstance(meta, dict):
        raise ModFormatError([("mod.yaml", "mod.yaml 最外层应该是 键: 值 的形式", "mod.yaml must be a mapping")])
    m = {"meta": meta, "files": dict(files)}
    m["name"] = str(meta.get("name") or "").strip()
    m["title"] = meta.get("title") or m["name"]
    m["prefix"] = meta.get("prefix") or _camel(m["name"] or "Mod")
    m["cards"] = [_norm_card(c) for c in _list_or_files(meta.get("cards"), files, "mod.yaml cards", problems)]
    m["powers"] = [_norm_power(p) for p in _list_or_files(meta.get("powers"), files, "mod.yaml powers", problems)]
    m["relics"] = [_norm_relic(r) for r in _list_or_files(meta.get("relics"), files, "mod.yaml relics", problems)]
    pots = meta.get("potions") or []
    # 旧格式的 potions.yaml 是旧战斗模拟器的药水表（引用游戏药水）；整局的模组药水写在 mod_potions
    m["potions"] = [_norm_potion(p) for p in _list_or_files(meta.get("mod_potions"), files, "mod.yaml mod_potions", problems)]
    m["legacy_potions"] = pots
    chars = meta.get("characters") or {}
    m["characters"] = {}
    for cid, ch in (chars.items() if isinstance(chars, dict) else []):
        ch = dict(ch or {})
        m["characters"][str(cid)] = {
            "id": str(cid), "name": ch.get("name", cid), "hp": ch.get("hp", 75), "energy": ch.get("energy", 3),
            "gold": ch.get("gold", 99), "hand": ch.get("hand", 5),
            "starting_deck": list(ch.get("starting_deck") or []),
            "relics": list(ch.get("relics") or ch.get("starting_relics") or []),
            "class": ch.get("class"), "base": ch.get("base", "Ironclad"),
        }
    m["helpers"] = dict(meta.get("helpers") or {})
    m["ai_values"] = dict(meta.get("ai_values") or {})
    m["hooks"] = meta.get("hooks")
    m["fullrun_hooks"] = meta.get("fullrun_hooks")
    m["ai_hooks"] = meta.get("ai_hooks")
    m["variants"] = dict(meta.get("variants") or {})
    m["decks"] = meta.get("decks") or []
    if problems:
        raise ModFormatError(problems)
    return m


def _camel(s):
    s = re.sub(r"[^0-9A-Za-z_]", "_", str(s))
    out = "".join(w[:1].upper() + w[1:].lower() for w in s.split("_") if w)
    if not out or not out[0].isalpha():
        out = "M" + out
    return out


def _kw_list(v):
    return [k for k in (norm_keyword(x) for x in (v or [])) if k]


def _norm_card(raw):
    c = dict(raw)
    up = dict(c.get("upgrade") or {})
    card = {
        "id": str(c.get("id", "")).strip(), "name": c.get("name") or c.get("id"), "_raw_type": c.get("type"),
        "type": norm_type(c.get("type")), "_raw_rarity": c.get("rarity"), "rarity": norm_rarity(c.get("rarity")),
        "cost": c.get("cost", 1), "_raw_target": c.get("target"), "target": norm_target(c.get("target")),
        "keywords": _kw_list(c.get("keywords")), "vars": dict(c.get("vars") or {}),
        "effects": list(c.get("effects") or []), "pool": c.get("pool", True), "ai": c.get("ai") or {},
        "text": c.get("text", ""), "text_up": c.get("text_up", ""), "class": c.get("class"), "tags": list(c.get("tags") or []),
        "upgrade": {"vars": dict(up.get("vars") or {}), "cost": up.get("cost"), "add": _kw_list(up.get("add")),
                    "remove": _kw_list(up.get("remove")), "effects": up.get("effects"), "name": up.get("name")},
        "_file": c.get("_file"),
    }
    if card["cost"] is None:
        if "Unplayable" not in card["keywords"]:
            card["keywords"].append("Unplayable")
    return card


def _norm_triggers(raw, problems=None):
    out = []
    for t in raw.get("triggers") or []:
        if isinstance(t, dict):
            out.append(t)
    return out


def _norm_power(raw):
    p = dict(raw)
    return {"id": str(p.get("id", "")).strip(), "name": p.get("name") or p.get("id"),
            "type": "Debuff" if str(p.get("type", p.get("kind", "buff"))).lower() in ("debuff", "负面") else "Buff",
            "stack": "Single" if str(p.get("stack", "counter")).lower() == "single" else "Counter",
            "max": p.get("max"), "decay": p.get("decay"), "expire": p.get("expire"),
            "triggers": _norm_triggers(p), "vars": dict(p.get("vars") or {}), "class": p.get("class"),
            "text": p.get("text", ""), "_file": p.get("_file")}


def _norm_relic(raw):
    r = dict(raw)
    rr = _norm(RELIC_RARITY, RELIC_RARITIES, r.get("rarity"), "Common")
    return {"id": str(r.get("id", "")).strip(), "name": r.get("name") or r.get("id"), "rarity": rr,
            "_raw_rarity": r.get("rarity"), "triggers": _norm_triggers(r), "vars": dict(r.get("vars") or {}),
            "class": r.get("class"), "pool": r.get("pool", True), "text": r.get("text", ""), "_file": r.get("_file")}


def _norm_potion(raw):
    p = dict(raw)
    return {"id": str(p.get("id", "")).strip(), "name": p.get("name") or p.get("id"),
            "rarity": _norm(POTION_RARITY, ("Common", "Uncommon", "Rare"), p.get("rarity"), "Common"),
            "_raw_rarity": p.get("rarity"), "target": norm_target(p.get("target")), "_raw_target": p.get("target"),
            "effects": list(p.get("effects") or []), "vars": dict(p.get("vars") or {}), "class": p.get("class"),
            "text": p.get("text", ""), "_file": p.get("_file")}


# ---------------------------------------------------------------- 校验
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _names_in(expr):
    try:
        tree = ast.parse(str(expr), mode="eval")
    except SyntaxError as e:
        return None, str(e.msg)
    names = set()
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        elif isinstance(node, ast.Lambda):
            for a in node.args.args:
                bound.add(a.arg)
    return names - bound, None


class _V:
    def __init__(self, mod, fullrun):
        self.mod = mod
        self.fullrun = fullrun
        self.problems = []
        self.warnings = []
        self.power_ids = {p["id"] for p in mod["powers"]}
        self.card_ids = {c["id"] for c in mod["cards"]}
        self.helper_names = {re.split(r"[ (]", h.strip())[0] for h in mod["helpers"]}
        self.py_names = set()

    def err(self, where, zh, en):
        self.problems.append((where, zh, en))

    def warn(self, where, zh, en):
        self.warnings.append((where, zh, en))

    def expr(self, where, v, scope):
        if isinstance(v, (int, float, bool)) or v is None:
            return
        if not isinstance(v, str):
            self.err(where, f"应该是数字或表达式，现在是 {type(v).__name__}", f"expected a number or expression, got {type(v).__name__}")
            return
        names, bad = _names_in(v)
        if bad:
            self.err(where, f"表达式写错了：「{v}」（{bad}）", f"invalid expression: '{v}' ({bad})")
            return
        legacy = set() if self.fullrun else {"C", "ctx", "intent_damage", "attacking"}
        unknown = sorted(n for n in names if n not in scope and n not in EXPR_NAMES and n not in self.helper_names
                         and n not in legacy)
        soft = bool(self.mod.get("fullrun_hooks") if self.fullrun else self.mod.get("hooks"))
        if unknown:
            (self.warn if soft else self.err)(where, f"表达式「{v}」里有不认识的名字：{', '.join(unknown)}（是不是忘了写进 vars，或者拼错了？）",
                     f"unknown name(s) in '{v}': {', '.join(unknown)} (missing from vars, or a typo?)")

    def power(self, where, pid):
        if not pid:
            self.err(where, "没写能力 ID（power）", "missing power id")
            return
        if pid not in self.power_ids and not re.match(r"^[A-Z][A-Z0-9_]*$|^[A-Z][A-Za-z0-9]*Power$", str(pid)):
            self.err(where, f"能力「{pid}」既不是这个 mod 里定义的，也不像游戏自带能力的 ID（例如 WEAK、STRENGTH）",
                     f"power '{pid}' is neither defined in this mod nor looks like a built-in power id (e.g. WEAK, STRENGTH)")

    def ops(self, where, effects, scope):
        if effects is None:
            return
        if not isinstance(effects, list):
            self.err(where, "效果应该是一个列表（每行以 - 开头）", "effects must be a list")
            return
        for i, eff in enumerate(effects):
            self.op(f"{where}[{i}]", eff, scope)

    def op(self, where, eff, scope):
        if not isinstance(eff, dict):
            self.err(where, "每个效果应该是 {op: ..., ...}", "each effect must be a mapping like {op: ...}")
            return
        name = eff.get("template") or eff.get("op")
        if name is None:
            self.err(where, "效果缺少 op（要做什么）", "effect has no 'op'")
            return
        if "if" in eff:
            self.expr(where + ".if", eff["if"], scope)
        if eff.get("once") is not None and eff["once"] not in ONCE:
            self.err(where + ".once", f"once 只能是 {'/'.join(ONCE)}", f"once must be one of {'/'.join(ONCE)}")
        if name in TEMPLATES:
            spec = TEMPLATES[name]
            for k, s in spec.items():
                if s[1] and k not in eff:
                    self.err(where, f"模板 {name} 缺少参数 {k}", f"template {name} needs '{k}'")
            if "power" in eff:
                self.power(where + ".power", eff["power"])
            try:
                exp = expand_template(eff)
            except Exception as e:  # noqa
                self.err(where, f"模板 {name} 展开失败：{e}", f"template {name} failed to expand: {e}")
                return
            sub = set(scope)
            if eff.get("save"):
                sub.add(eff["save"])
            sub.add("_k")
            for j, x in enumerate(exp):
                self.op(f"{where}<{name}>", x, sub)
            if eff.get("save"):
                scope.add(eff["save"])
            return
        spec = OPS.get(name)
        if spec is None:
            self.err(where, f"不认识的效果 op：{name}（可用：{', '.join(sorted(OPS))}；模板：{', '.join(sorted(TEMPLATES))}）",
                     f"unknown op: {name} (ops: {', '.join(sorted(OPS))}; templates: {', '.join(sorted(TEMPLATES))})")
            return
        for k, s in spec.items():
            if s[1] and k not in eff:
                self.err(where, f"{name} 缺少参数 {k}", f"{name} needs '{k}'")
        for k, v in eff.items():
            if k in EFFECT_COMMON:
                continue
            if k not in spec:
                if name == "py":
                    continue
                self.err(where, f"{name} 没有参数 {k}（可用：{', '.join(spec) or '无'}）",
                         f"{name} has no parameter '{k}' (allowed: {', '.join(spec) or 'none'})")
                continue
            t = spec[k][0]
            if t == "expr":
                self.expr(f"{where}.{k}", v, scope)
            elif t == "power":
                self.power(f"{where}.{k}", v)
            elif t == "card":
                if v not in self.card_ids and not re.match(r"^[A-Z][A-Z0-9_]*$", str(v)):
                    self.err(f"{where}.{k}", f"卡牌「{v}」不在这个 mod 里", f"card '{v}' is not in this mod")
            elif t == "target":
                if v not in TARGET_SPECS:
                    self.err(f"{where}.{k}", f"目标只能是 {'/'.join(TARGET_SPECS)}", f"target must be one of {'/'.join(TARGET_SPECS)}")
            elif t.startswith("choice:"):
                if v is not None and str(v) not in t[7:].split("|"):
                    self.err(f"{where}.{k}", f"{k} 只能是 {t[7:].replace('|', '/')}", f"{k} must be one of {t[7:].replace('|', '/')}")
        if name == "set":
            scope.add(str(eff.get("name")))
        for k in ("save",):
            if eff.get(k):
                scope.add(str(eff[k]))
        if name == "if":
            self.ops(where + ".then", eff.get("then"), scope)
            self.ops(where + ".else", eff.get("else"), scope)
        elif name in ("foreach", "repeat"):
            self.ops(where + ".do", eff.get("do"), scope)
        elif name == "damage":
            self.ops(where + ".each_hit", eff.get("each_hit"), scope)
        elif name == "end_turn" and self.fullrun:
            self.warn(where, "end_turn 在整局里会直接结束你的回合（后面的效果不再结算）",
                      "end_turn ends your turn in full runs (later effects are skipped)")
        elif name == "py":
            hooks = self.mod.get("fullrun_hooks") if self.fullrun else self.mod.get("hooks")
            if not hooks:
                self.err(where, "用了 py 效果，但 mod.yaml 里没写 " + ("fullrun_hooks" if self.fullrun else "hooks"),
                         "uses a py effect but mod.yaml has no " + ("fullrun_hooks" if self.fullrun else "hooks"))

    def trigger(self, where, tr, scope):
        if not isinstance(tr, dict):
            self.err(where, "每个触发器应该是 {on: ..., do: [...]}", "each trigger must be a mapping like {on: ..., do: [...]}")
            return
        if tr.get("template") and tr["template"] not in TRIGGER_TEMPLATES:
            self.err(where, f"不认识的触发器模板：{tr['template']}（可用：{', '.join(TRIGGER_TEMPLATES)}）",
                     f"unknown trigger template: {tr['template']} (available: {', '.join(TRIGGER_TEMPLATES)})")
            return
        if tr.get("template"):
            _on, spec = TRIGGER_TEMPLATES[tr["template"]]
            for k, s in spec.items():
                if s[1] and k not in tr:
                    self.err(where, f"模板 {tr['template']} 缺少参数 {k}", f"template {tr['template']} needs '{k}'")
                    return
        t = expand_trigger(tr)
        on = t.get("on")
        if on not in TRIGGERS:
            self.err(where, f"不认识的触发时机 on: {on}（可用：{', '.join(TRIGGERS)}）",
                     f"unknown trigger on: {on} (available: {', '.join(TRIGGERS)})")
            return
        for k, s in TRIGGERS[on].items():
            if s[1] and k not in t:
                self.err(where, f"触发器 {on} 缺少参数 {k}", f"trigger {on} needs '{k}'")
        for k in t:
            if k not in TRIGGERS[on] and k not in TRIGGER_COMMON:
                self.err(where, f"触发器 {on} 没有参数 {k}", f"trigger {on} has no parameter '{k}'")
        sc = set(scope) | {"amount", "n", "active", "card_paid", "damage", "multi"}
        for k in ("add", "mult"):
            if k in t:
                self.expr(f"{where}.{k}", t[k], sc)
        if "if" in t:
            self.expr(where + ".if", t["if"], sc)
        if t.get("power"):
            self.power(where + ".power", t["power"])
        if t.get("once") is not None and t["once"] not in ONCE:
            self.err(where + ".once", f"once 只能是 {'/'.join(ONCE)}", f"once must be one of {'/'.join(ONCE)}")
        if on not in ("modify_damage", "modify_block", "modify_apply", "play_count") and not t.get("do"):
            self.err(where, f"触发器 {on} 没写 do（触发时做什么）", f"trigger {on} has no 'do'")
        self.ops(where + ".do", t.get("do"), sc)


def validate(mod, fullrun=True):
    """返回 (problems, warnings)，都是 [(位置, 中文, English)]。problems 非空时这个 mod 不能用。"""
    v = _V(mod, fullrun)
    if not mod.get("name"):
        v.err("mod.yaml", "缺少 name（mod 的英文名，用来做文件夹名和内部 ID）", "missing 'name'")
    elif not _ID_RE.match(mod["name"]):
        v.err("mod.yaml name", "name 只能用英文字母、数字、下划线，并以字母开头", "name: letters, digits and _ only, starting with a letter")
    seen = {}
    for kind, items in (("card", mod["cards"]), ("power", mod["powers"]), ("relic", mod["relics"]), ("potion", mod["potions"])):
        for it in items:
            where = f"{it.get('_file') or ''} {kind} {it.get('id') or '?'}".strip()
            if not it["id"]:
                v.err(where, "缺少 id", "missing id")
                continue
            if not _ID_RE.match(it["id"]):
                v.err(where, "id 只能用英文字母、数字、下划线，并以字母开头（名字 name 可以写中文）",
                      "id: letters, digits and _ only, starting with a letter (the display name can be anything)")
            key = (kind, it["id"])
            if key in seen:
                v.err(where, f"id 重复了：{it['id']}", f"duplicate id: {it['id']}")
            seen[key] = True
    for c in mod["cards"]:
        where = f"{c.get('_file') or 'cards'} card {c['id']}"
        if c["type"] is None:
            v.err(where, f"type「{c['_raw_type']}」不认识，可用：攻击/技能/能力/状态/诅咒（或 Attack/Skill/Power/Status/Curse）",
                  f"unknown type '{c['_raw_type']}' (Attack/Skill/Power/Status/Curse)")
        if c["rarity"] is None:
            v.err(where, f"rarity「{c['_raw_rarity']}」不认识，可用：基础/普通/罕见/稀有/特殊（或 Basic/Common/Uncommon/Rare/Token）",
                  f"unknown rarity '{c['_raw_rarity']}' (Basic/Common/Uncommon/Rare/Token)")
        if c["target"] is None:
            v.err(where, f"target「{c['_raw_target']}」不认识，可用：enemy/self/all/random/none", f"unknown target '{c['_raw_target']}'")
        cost = c["cost"]
        if cost == "X":
            if fullrun:
                v.err(where, "X 费牌在整局里暂不支持（旧版战斗模拟器可以）", "X-cost cards are not supported in full runs yet")
        elif cost is not None and not isinstance(cost, int):
            v.err(where, "cost 应该是整数（不能打出就写 null）", "cost must be an integer (null = unplayable)")
        if fullrun and "Replay" in c["keywords"]:
            v.warn(where, "关键词 replay 在整局里没有效果", "keyword 'replay' has no effect in full runs")
        for k, val in list(c["vars"].items()) + list(c["upgrade"]["vars"].items()):
            if not isinstance(val, (int, float)):
                v.err(f"{where} vars.{k}", "vars 里的数值必须是数字", "vars must be numbers")
        for k in c["upgrade"]["vars"]:
            if k not in c["vars"]:
                v.err(f"{where} upgrade.vars.{k}", f"升级里的 {k} 在 vars 里没有", f"upgrade var {k} is not in vars")
        scope = set(c["vars"])
        v.ops(f"{where} effects", c["effects"], set(scope))
        if c["upgrade"].get("effects") is not None:
            v.ops(f"{where} upgrade.effects", c["upgrade"]["effects"], set(scope))
        if not c["effects"] and c["type"] in ("Attack", "Skill", "Power") and "Unplayable" not in c["keywords"]:
            v.warn(where, "这张牌没有任何效果", "this card has no effects")
    for p in mod["powers"]:
        where = f"{p.get('_file') or 'powers'} power {p['id']}"
        for i, t in enumerate(p["triggers"]):
            v.trigger(f"{where} triggers[{i}]", t, set(p["vars"]))
        for k in ("decay", "expire"):
            if p.get(k) not in (None, "turn_start", "turn_end", "none"):
                v.err(f"{where} {k}", f"{k} 只能是 turn_start / turn_end / none", f"{k} must be turn_start / turn_end / none")
        if p.get("max") is not None and not isinstance(p["max"], int):
            v.err(f"{where} max", "max 应该是整数", "max must be an integer")
    for r in mod["relics"]:
        where = f"{r.get('_file') or 'relics'} relic {r['id']}"
        if r["rarity"] is None:
            v.err(where, f"rarity「{r['_raw_rarity']}」不认识，可用：初始/普通/罕见/稀有/商店/事件", f"unknown relic rarity '{r['_raw_rarity']}'")
        for i, t in enumerate(r["triggers"]):
            v.trigger(f"{where} triggers[{i}]", t, set(r["vars"]))
        if fullrun and not r["triggers"] and not mod.get("fullrun_hooks"):
            v.warn(where, "这个遗物没有写 triggers，整局里不会有任何效果", "this relic has no triggers; it does nothing in full runs")
    for p in mod["potions"]:
        where = f"{p.get('_file') or 'potions'} potion {p['id']}"
        v.ops(f"{where} effects", p["effects"], set(p["vars"]))
    if fullrun:
        if not mod["characters"]:
            v.err("mod.yaml characters", "整局需要至少一个角色（characters）", "full runs need at least one character")
        for cid, ch in mod["characters"].items():
            where = f"mod.yaml characters.{cid}"
            if not _ID_RE.match(cid):
                v.err(where, "角色 id 只能用英文字母、数字、下划线", "character id: letters, digits and _ only")
            if not ch["starting_deck"]:
                v.err(where, "整局需要初始牌组 starting_deck（例：[MY_STRIKE×4, MY_DEFEND×4, MY_SPECIAL]）",
                      "full runs need a starting_deck (e.g. [MY_STRIKE×4, MY_DEFEND×4, MY_SPECIAL])")
            for item in ch["starting_deck"]:
                cid2, _n, _up = parse_deck_item(item)
                if cid2 not in v.card_ids:
                    v.err(where, f"初始牌组里的「{cid2}」不在这个 mod 的卡表里", f"starting deck card '{cid2}' is not in this mod")
            rel_ids = {r["id"] for r in mod["relics"]}
            for rid in ch["relics"]:
                if rid not in rel_ids:
                    v.warn(where, f"初始遗物「{rid}」不在这个 mod 里，会当成游戏自带遗物去找", f"starting relic '{rid}' is not in this mod; treated as a built-in relic")
            for k in ("hp", "energy", "gold"):
                if not isinstance(ch.get(k), int) or ch[k] < 0:
                    v.err(f"{where}.{k}", f"{k} 应该是非负整数", f"{k} must be a non-negative integer")
        pool = [c for c in mod["cards"] if c["pool"] and c["rarity"] in ("Common", "Uncommon", "Rare")]
        for r in ("Common", "Uncommon", "Rare"):
            if not any(c["rarity"] == r for c in pool):
                v.err("cards", f"整局奖励需要至少一张「{ {'Common': '普通', 'Uncommon': '罕见', 'Rare': '稀有'}[r] }」牌",
                      f"full runs need at least one {r} card in the pool")
        if mod.get("hooks") and not mod.get("fullrun_hooks"):
            v.warn("mod.yaml hooks", "hooks.py 是给旧版战斗模拟器写的，整局不会加载它；只靠 hooks.py 实现的能力/遗物在整局里没有效果",
                   "hooks.py is for the legacy combat simulator and is not loaded in full runs")
        for h, body in mod["helpers"].items():
            v.expr(f"mod.yaml helpers.{h}", body, set(re.findall(r"\(([^)]*)\)", h)[0].replace(" ", "").split(",")) if "(" in h else set())
    return v.problems, v.warnings


def parse_deck_item(item):
    """「ID×4」「ID+」「ID*2」→ (ID, 数量, 升级)。"""
    s = str(item).strip()
    n = 1
    for sep in ("×", "*", " x"):
        if sep in s:
            s, k = s.rsplit(sep, 1)
            try:
                n = int(k)
            except ValueError:
                n = 1
            s = s.strip()
            break
    up = s.endswith("+")
    if up:
        s = s[:-1]
    return s, n, up


# ---------------------------------------------------------------- 写回（图形界面导出）
def _clean(d):
    if isinstance(d, dict):
        return {k: _clean(v) for k, v in d.items() if not str(k).startswith("_") and v not in (None, [], {}, "")}
    if isinstance(d, list):
        return [_clean(x) for x in d]
    return d


def dump_mod_dir(mod, path=None):
    """把规范化后的 mod 写成文件（{相对路径: 文本}）；给了 path 就写到磁盘。"""
    meta = {"name": mod["name"], "title": mod.get("title") or mod["name"], "prefix": mod.get("prefix")}
    files = {}
    chars = {}
    for cid, ch in mod["characters"].items():
        chars[cid] = _clean({"name": ch["name"], "hp": ch["hp"], "energy": ch["energy"], "gold": ch.get("gold", 99),
                             "starting_deck": ch["starting_deck"], "relics": ch["relics"], "class": ch.get("class")})
    meta["characters"] = chars
    if mod["cards"]:
        meta["cards"] = ["cards.yaml"]
        cards = []
        for c in mod["cards"]:
            up = _clean(dict(c["upgrade"]))
            d = {"id": c["id"], "name": c["name"], "type": c["type"], "rarity": c["rarity"], "cost": c["cost"],
                 "target": {"AnyEnemy": "enemy", "Self": "self", "AllEnemies": "all", "RandomEnemy": "random"}[c["target"]],
                 "keywords": [k.lower() for k in c["keywords"] if not (k == "Unplayable" and c["cost"] is None)],
                 "vars": c["vars"], "upgrade": up, "effects": c["effects"], "text": c.get("text"),
                 "text_up": c.get("text_up"), "ai": c.get("ai"), "class": c.get("class")}
            if c.get("pool") is False:
                d["pool"] = False
            d = _clean(d)
            d["cost"] = c["cost"]
            cards.append(d)
        files["cards.yaml"] = yaml.safe_dump(cards, allow_unicode=True, sort_keys=False, width=120)
    if mod["powers"]:
        meta["powers"] = ["powers.yaml"]
        files["powers.yaml"] = yaml.safe_dump([_clean({k: p.get(k) for k in ("id", "name", "type", "stack", "max", "decay", "expire", "vars", "triggers", "text", "class")})
                                               for p in mod["powers"]], allow_unicode=True, sort_keys=False, width=120)
    if mod["relics"]:
        meta["relics"] = ["relics.yaml"]
        files["relics.yaml"] = yaml.safe_dump([_clean({k: r.get(k) for k in ("id", "name", "rarity", "vars", "triggers", "text", "class")}
                                                      | ({"pool": False} if r.get("pool") is False else {}))
                                               for r in mod["relics"]], allow_unicode=True, sort_keys=False, width=120)
    if mod["potions"]:
        meta["mod_potions"] = ["potions.yaml"]
        files["potions.yaml"] = yaml.safe_dump([_clean({k: p.get(k) for k in ("id", "name", "rarity", "target", "vars", "effects", "text", "class")})
                                                for p in mod["potions"]], allow_unicode=True, sort_keys=False, width=120)
    for k in ("helpers", "ai_values", "variants"):
        if mod.get(k):
            meta[k] = mod[k]
    for k in ("fullrun_hooks", "ai_hooks", "hooks"):
        if mod.get(k):
            meta[k] = mod[k]
            if mod.get("files", {}).get(mod[k]) is not None:
                files[mod[k]] = mod["files"][mod[k]]
    if mod.get("decks"):
        meta["decks"] = mod["decks"]
        for f in mod["decks"]:
            if mod.get("files", {}).get(f) is not None:
                files[f] = mod["files"][f]
    files["mod.yaml"] = yaml.safe_dump(_clean(meta), allow_unicode=True, sort_keys=False, width=120)
    if path:
        os.makedirs(path, exist_ok=True)
        for rel, text in files.items():
            fp = os.path.join(path, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(text)
    return files
