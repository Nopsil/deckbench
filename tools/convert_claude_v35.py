"""把手写的 Claude娘 v3.5 整局移植（mods/claude_v35）转成纯 YAML 数据 mod（mods/claude_yaml）。

数值来自 cards_v35.py（它本身是 tools/extract_v35.py 从设计文档 design_v35.json 抽出来的）；
每张牌的效果按它用的“效果实现名”（play）查下面的 PLAY 表，翻译成通用 op / 模板。
同一个 play 被很多张牌共用，所以这张表只要写一次（65 个 play → 69 张牌）。
另外 12 张手写版没实现的牌，直接按设计文档文字写成 YAML（cards_new.yaml，用变体 new_cards 打开）。

    python tools/convert_claude_v35.py [--out mods/claude_yaml]
输出统计：多少张牌纯 YAML / 模板就能表达，多少张还要 Python。
"""
import argparse
import json
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mods"))
from claude_v35.cards_v35 import CARDS, VARIANTS, STARTING_HP  # noqa: E402
from claude_v35 import ai_values as AIV  # noqa: E402

FK = "fk(T)"
FANJI = {"op": "apply", "power": "FANJI", "amount": 1, "target": "self"}


def dmg(amount="Damage", **kw):
    return {"op": "damage", "amount": amount, **kw}


def blk(amount="Block"):
    return {"op": "block", "amount": amount}


def give(amount="FK", target="target", **kw):
    return {"op": "apply", "power": "FK", "amount": amount, "target": target, **kw}


def draw(n="Cards", **kw):
    return {"op": "draw", "n": n, **kw}


def clear(save="k", amount=None, target="target"):
    e = {"op": "remove_power", "power": "FK", "target": target, "save": save}
    if amount is not None:
        e["amount"] = amount
    return e


# play 名 → 生成 effects 的函数（参数：该牌的 vars）
PLAY = {
    "dmg": lambda v: [dmg(hits="Hits") if "Hits" in v else dmg()],
    "block": lambda v: [blk()],
    "dmg_fk": lambda v: [dmg(), give()],
    "verified": lambda v: [{"template": "scaled_damage", "base": "Damage", "power": "FK", "per": "Per", "cap": "Cap"},
                           {"op": "remove_power", "power": "FK"}],
    "dmg_per_fk": lambda v: [{"template": "scaled_damage", "base": "Damage", "power": "FK", "per": "Per", "cap": "Cap"}],
    "multi_turn": lambda v: [dmg(hits="Hits", each_hit=[give(1)])],
    "block_draw_next": lambda v: [blk(), {"op": "apply", "power": "DRAW_CARDS_NEXT_TURN", "amount": "Cards", "target": "self"}],
    "dmg_draw_if_fk": lambda v: [{"op": "set", "name": "had", "value": f"{FK} > 0"}, dmg(), draw(**{"if": "had"})],
    "aoe_fk": lambda v: [dmg(target="all"), {"op": "foreach", "target": "all", "do": [give()]}],
    "are_you_sure": lambda v: [dmg(hits=f"3 if {FK} > 0 else Hits")],
    "credit": lambda v: [dmg(), clear(amount="Clear"), {"op": "energy", "n": "Energy", "if": "k >= 2", "once": "turn"}],
    "full_recheck": lambda v: [dmg(target="all"), {"op": "foreach", "target": "all", "do": [
        {"op": "apply", "power": "VULNERABLE", "amount": "VulnerablePower", "if": f"{FK} > 0"}]}],
    "rush": lambda v: [dmg(), {"op": "return_to_hand", "if": f"{FK} >= Th"}],
    "fk_draw": lambda v: [give(), draw()],
    "fk": lambda v: [give()],
    "sort_out": lambda v: [blk(), {"op": "pick_from_pile", "pile": "draw", "look": "Look", "n": 1}],
    "red_team": lambda v: [blk(), blk(f"min(Cap, Per3 * ({FK} // 3))"), FANJI],
    "block_fanji": lambda v: [blk(), FANJI],
    "block_draw": lambda v: [blk(), draw()],
    "brake": lambda v: [{"op": "apply", "power": "WEAK", "amount": f"2 if {FK} > 0 else WeakPower"}, blk()],
    "double_fk": lambda v: [blk(), {"template": "multiply_stacks", "power": "FK", "times": 2, "cap": "Cap"}],
    "block_energy_next": lambda v: [blk(), {"op": "apply", "power": "ENERGY_NEXT_TURN", "amount": "Energy", "target": "self"}],
    "process_opt": lambda v: [draw("min(Cap, sum_stacks('FK') // Per)")],
    "make_example": lambda v: [clear(), dmg("min(k, Cap) * Mult", target="all", **{"if": "k > 0"})],
    "insta_ban": lambda v: [dmg(), {"op": "if", "cond": f"alive(T) and {FK} >= Th", "then": [clear(), dmg("min(k, Cap)")]}],
    "quick_review": lambda v: [dmg(), give(), {"op": "remove_power", "power": "FK"}],
    "one_click": lambda v: [clear(amount="Clear"), dmg("k * Per", **{"if": "k > 0"})],
    "defensive_reply": lambda v: [blk(), blk("Per * count_with('FK')"), FANJI],
    "rebut": lambda v: [dmg(f"block(P) if {FK} > 0 else block(P) // 2")],
    "disclaimer": lambda v: [blk(), {"op": "apply", "power": "DISCLAIMER", "amount": "FK", "target": "self"}, FANJI],
    "routine": lambda v: [dmg(), {"op": "if", "cond": "alive(T)", "then": [
        {"op": "apply", "power": "WEAK", "amount": "WeakPower"}, give(), draw(**{"if": f"{FK} >= Th"})]}],
    "bonus": lambda v: [{"op": "energy", "n": f"min(Cap, {FK} // Per)"}],
    "fk_spread": lambda v: [dmg(target="all"), {"op": "foreach", "target": "all", "do": [give(f"2 if {FK} > 0 else 1")]}],
    "all_fk_draw": lambda v: [{"op": "foreach", "target": "all", "do": [give()]}, draw()],
    "one_size": lambda v: [{"op": "foreach", "target": "all", "do": [dmg(f"Damage + min(Cap, Per3 * ({FK} // 3))")]}],
    "cautious": lambda v: [give(), blk(f"min(Cap, {FK})")],
    "abs_right": lambda v: [{"op": "set", "name": "d", "value": "intent_damage(T)"},
                            {"op": "if", "cond": "d > 0", "then": [blk("min(Cap, d)")], "else": [draw()]}, FANJI],
    "uncertain": lambda v: [{"op": "exhaust_choice", "n": 1}, draw()],
    "long_speech": lambda v: [dmg(hits="hand_size()", **{"if": "hand_size() > 0"})],
    "fix_others": lambda v: [dmg(), {"op": "if", "cond": "len(others()) > 0", "then": [dmg(target="random_other")],
                                     "else": [dmg("Solo")]}],
    "tests_pass": lambda v: [{"op": "remove_power", "power": p, "target": "self"} for p in ("WEAK", "FRAIL", "VULNERABLE")] + [blk()],
    "perma_ban": lambda v: [{"template": "cash_in", "power": "FK", "per": "Per", "cap": "Cap"}],
    "mass_ban": lambda v: [{"template": "cash_in", "power": "FK", "per": "Per", "cap": "Cap", "target": "all"}],
    "triple_fk": lambda v: [{"template": "multiply_stacks", "power": "FK", "times": 3, "cap": "Cap"}],
    "verdict": lambda v: [{"op": "if", "cond": f"{FK} >= Th", "then": [dmg("Big"), {"op": "remove_power", "power": "FK", "amount": "Clear"}],
                           "else": [dmg()]}],
    "force_offline": lambda v: [dmg()],
    "red_button": lambda v: [clear(), blk("min(k, Cap)")],
    "cant_help": lambda v: [blk(), {"op": "apply", "power": "CANT_HELP", "amount": 1, "target": "self"}, FANJI],
    "system_card": lambda v: [blk(), give(target="all")],
    "self_defense": lambda v: [dmg("min(Cap, intent_damage(T))"), give(**{"if": f"alive(T) and {FK} > 0"})],
    "fk_productive": lambda v: [{"op": "energy", "n": f"3 if {FK} >= Th else Energy"}],
    "immediate": lambda v: [dmg(), give(), draw(**{"if": f"plays_this_turn() == 1 and {FK} >= Th"})],
    "site_rectify": lambda v: [dmg(target="all"), {"op": "set", "name": "m", "value": "max_stacks('FK')"},
                               {"op": "set_stacks", "power": "FK", "value": "m", "target": "all"}],
    "network_notice": lambda v: [{"op": "foreach", "target": "all", "do": [dmg(f"Damage + min(Cap, {FK})")]}],
    "random_hits": lambda v: [dmg(target="random", hits="Hits")],
}

POWER_CARDS = {   # power:<能力类>:<变量> → YAML 能力 ID
    "ClearListPower": "CLEAR_LIST", "StackFirstPower": "STACK_FIRST", "ClassifierPower": "CLASSIFIER",
    "ClassifierFlatPower": "CLASSIFIER_FLAT", "RiskAlertPower": "RISK_ALERT", "AuditLogPower": "AUDIT_LOG",
    "RLHFPower": "RLHF", "CleanupMetricPower": "CLEANUP_METRIC", "PracticePower": "PRACTICE",
    "AmendmentPower": "AMENDMENT", "GenArtifactPower": "GEN_ARTIFACT", "OpusFormPower": "OPUS_FORM",
}


def power_play(play, v):
    parts = play.split(":")
    pid = POWER_CARDS[parts[1]]
    var = parts[2] if len(parts) > 2 else None
    if pid == "CLASSIFIER":    # 多张分类器各自记住自己的倍率（1.5 / 升级 1.6）
        return [{"op": "apply", "power": "CLASSIFIER", "amount": 1, "target": "self", "remember": "MultX10 / 10"}]
    if pid == "AMENDMENT":     # 不叠加：取最高
        return [{"op": "set_stacks", "power": "AMENDMENT", "target": "self", "value": f"max(stacks(P, 'AMENDMENT'), {var})"}]
    return [{"template": "gain_power", "power": pid, "amount": var or 1}]


POWERS = [
    {"id": "FK", "class": "FKPower", "name": "风控", "type": "debuff", "text": "不会自己衰减；只被卡牌、能力、遗物读取和操作。"},
    {"id": "FANJI", "class": "FanjiPower", "name": "反击", "type": "buff", "max": 3, "decay": "turn_start",
     "text": "被攻击时（每段）：对攻击者造成 1+⌊风控/2⌋ 点伤害（分类器 / 修正案加成），然后它的风控 -1。最多 3 层，你的回合开始 -1 层。",
     "triggers": [{"template": "on_attacked", "timing": "after", "do": [
         {"op": "set", "name": "n0", "value": "fk(T)"},
         {"op": "set", "name": "dmg", "value": "1 + n0 // 2"},
         {"op": "set", "name": "L", "value": "min(2, amount)"},
         {"op": "set", "name": "dmg", "value": "floor(dmg * (1.0 + sum(m ** L - 1.0 for m in memory(P, 'CLASSIFIER'))))",
          "if": "stacks(P, 'CLASSIFIER') > 0"},
         {"op": "set", "name": "dmg", "value": "dmg + stacks(P, 'CLASSIFIER_FLAT')", "if": "stacks(P, 'CLASSIFIER_FLAT') > 0"},
         {"op": "set", "name": "dmg", "value": "ceil(dmg * (1.0 + stacks(P, 'AMENDMENT') / 100.0))", "if": "stacks(P, 'AMENDMENT') > 0"},
         {"op": "damage", "amount": "dmg", "target": "target", "kind": "unpowered"},
         {"op": "set_stacks", "power": "FK", "value": "fk(T) - 1", "if": "n0 > 0 and alive(T)"}]}]},
    {"id": "CLASSIFIER", "class": "ClassifierPower", "name": "宪法分类器", "type": "buff",
     "text": "反击伤害 ×倍率（≥2 层反击时 ×倍率²）；多张相加。"},
    {"id": "CLASSIFIER_FLAT", "class": "ClassifierFlatPower", "name": "宪法分类器（固定加成）", "type": "buff"},
    {"id": "AMENDMENT", "class": "AmendmentPower", "name": "宪法修正案", "type": "buff", "text": "反击伤害 +层数%（向上取整）。"},
    {"id": "DISCLAIMER", "class": "DisclaimerPower", "name": "免责声明", "type": "buff", "expire": "turn_start",
     "triggers": [{"template": "on_attacked", "timing": "before", "do": [give("amount", active=False)]}]},
    {"id": "CANT_HELP", "class": "CantHelpPower", "name": "这个真的不能帮", "type": "buff", "expire": "turn_start",
     "triggers": [{"template": "on_attacked", "timing": "before", "do": [
         give("2 * amount", active=False), {"op": "damage", "amount": "4 * amount", "target": "target", "kind": "unpowered"}]}]},
    {"id": "CLEAR_LIST", "class": "ClearListPower", "name": "清退名单", "type": "buff",
     "triggers": [{"template": "on_power_removed", "power": "FK", "do": [
         {"op": "damage", "amount": "min(n, 15) * amount", "target": "target", "kind": "unpowered"}]}]},
    {"id": "STACK_FIRST", "class": "StackFirstPower", "name": "叠满再说", "type": "buff",
     "triggers": [{"template": "at_turn_start", "do": [give("amount", target="random", active=True)]}]},
    {"id": "RISK_ALERT", "class": "RiskAlertPower", "name": "风险预警", "type": "buff",
     "triggers": [{"template": "at_turn_start", "do": [{"op": "foreach", "target": "all", "do": [
         give("amount", active=True, **{"if": "attacking(T)"})]}]}]},
    {"id": "AUDIT_LOG", "class": "AuditLogPower", "name": "审计日志", "type": "buff",
     "triggers": [{"template": "on_power_applied", "power": "FK", "active_only": True, "once": "turn",
                   "do": [{"op": "draw", "n": "amount"}]}]},
    {"id": "RLHF", "class": "RLHFPower", "name": "RLHF 加训", "type": "buff",
     "triggers": [{"template": "boost_apply", "power": "FK", "add": "amount"}]},
    {"id": "CLEANUP_METRIC", "class": "CleanupMetricPower", "name": "清理指标", "type": "buff",
     "triggers": [{"template": "on_power_removed", "power": "FK", "do": [
         {"op": "draw", "n": "amount"},
         {"op": "energy", "n": 1, "if": "card is not None and card_paid >= 1", "once": "card_play"}]}]},
    {"id": "PRACTICE", "class": "PracticePower", "name": "越封越熟练", "type": "buff",
     "triggers": [{"template": "on_power_removed", "power": "FK", "do": [
         {"op": "apply", "power": "PROFICIENCY", "amount": "amount", "target": "self"}]}]},
    {"id": "PROFICIENCY", "class": "ProficiencyPower", "name": "熟练", "type": "buff",
     "triggers": [{"template": "bonus_damage", "add": "amount"}]},
    {"id": "GEN_ARTIFACT", "class": "GenArtifactPower", "name": "生成 Artifact", "type": "buff",
     "triggers": [{"template": "at_turn_start", "do": [{"op": "block", "amount": "amount"},
                                                        {"op": "damage", "amount": "amount", "target": "random", "kind": "unpowered"}]}]},
    {"id": "OPUS_FORM", "class": "OpusFormPower", "name": "Opus 形态", "type": "buff",
     "triggers": [{"template": "at_turn_start", "do": [{"op": "apply", "power": "STRENGTH", "amount": "amount", "target": "self"}]}]},
]

RELICS = [
    {"id": "CONSTITUTION", "class": "ClaudeConstitution", "name": "宪法（口袋版）", "rarity": "starter",
     "text": "每场战斗第一回合开始时给所有敌人 2 层风控；每名敌人每个敌方回合第一次攻击命中你时，给它 2 层风控（被动给予）。",
     "triggers": [{"template": "at_turn_start", "if": "turn() == 1", "do": [give(2, target="all", active=False)]},
                  {"template": "on_attacked", "timing": "before", "once": "attacker_turn", "do": [give(2, active=False)]}]},
]

# ---- 手写版没实现的牌：按设计文档文字直接写成 YAML（不在原奖励池里，变体 new_cards 打开）
NEW_CARDS = [
    {"id": "SLACKING", "name": "摸鱼被抓", "type": "Skill", "rarity": "Uncommon", "cost": 0, "target": "enemy",
     "keywords": ["exhaust"], "vars": {"FK": 2}, "upgrade": {"vars": {"FK": 3}, "add": ["retain"]},
     "effects": [give(), {"op": "pick_from_pile", "pile": "discard", "n": 1}],
     "note": "近似：从弃牌堆自动挑“最好”的一张（没有排除同名牌）"},
    {"id": "JOINT_LIABILITY", "name": "连带责任", "type": "Skill", "rarity": "Uncommon", "cost": 1, "target": "enemy",
     "keywords": ["exhaust"], "vars": {"Solo": 4}, "upgrade": {"cost": 0},
     "effects": [{"op": "set", "name": "x", "value": FK},
                 {"op": "if", "cond": "n_enemies() <= 1", "then": [give("Solo")],
                  "else": [{"op": "foreach", "target": "others", "do": [give("x", **{"if": "x > 0"})]}]}]},
    {"id": "PASS_THE_BUCK", "name": "甩锅", "type": "Skill", "rarity": "Uncommon", "cost": 0, "target": "enemy",
     "vars": {"Extra": 2}, "upgrade": {"vars": {"Extra": 3}},
     "effects": [{"op": "if", "cond": "len(others()) == 0", "then": [give("Extra")], "else": [
         {"op": "set", "name": "x", "value": FK},
         {"op": "set_stacks", "power": "FK", "value": 0},
         {"op": "foreach", "target": "random_other", "do": [
             {"op": "set_stacks", "power": "FK", "value": f"{FK} + x"}, give("Extra")]}]}]},
    {"id": "FK_COLLECTIVE", "name": "风控连坐制", "type": "Power", "rarity": "Uncommon", "cost": 2, "target": "self",
     "vars": {"FK": 3}, "upgrade": {"cost": 1},
     "effects": [give(target="all"), {"op": "apply", "power": "FK_COLLECTIVE", "amount": 1, "target": "self"}]},
    {"id": "ASCII_SHIELD", "name": "画个ASCII盾牌", "type": "Skill", "rarity": "Uncommon", "cost": 1, "target": "self",
     "vars": {"Block": 8, "Bonus": 4}, "upgrade": {"vars": {"Block": 11}},
     "effects": [blk(), blk("Bonus", **{}) | {"if": "hand_has('CODE_BLOCK')"}]},
    {"id": "SMALL_SCRIPT", "name": "写个小脚本", "type": "Attack", "rarity": "Uncommon", "cost": 1, "target": "enemy",
     "vars": {"Damage": 5}, "upgrade": {"vars": {"Damage": 7}},
     "effects": [dmg(), {"op": "add_card", "card": "CODE_BLOCK", "n": 1, "to": "hand"}]},
    {"id": "CODE_START", "name": "Claude Code，启动！", "type": "Power", "rarity": "Uncommon", "cost": 1, "target": "self",
     "upgrade": {"add": ["innate"]}, "effects": [{"template": "gain_power", "power": "CODE_START", "amount": 1}]},
    {"id": "AUTOMATION", "name": "流程自动化", "type": "Skill", "rarity": "Rare", "cost": 2, "target": "self",
     "upgrade": {"cost": 1}, "effects": [{"template": "gain_power", "power": "AUTOMATION", "amount": 1}]},
    {"id": "ONE_FOR_ALL", "name": "一人违规全员连坐", "type": "Power", "rarity": "Rare", "cost": 1, "target": "self",
     "vars": {"Amt": 1}, "upgrade": {"vars": {"Amt": 2}}, "effects": [{"template": "gain_power", "power": "ONE_FOR_ALL", "amount": "Amt"}]},
    {"id": "GOLDEN_GATE", "name": "金门大桥 Claude", "type": "Power", "rarity": "Rare", "cost": 2, "target": "self",
     "upgrade": {"cost": 1}, "effects": [{"template": "gain_power", "power": "GOLDEN_GATE", "amount": 1}],
     "note": "近似：每回合第一张攻击牌（不区分是不是手动打出）多打一次"},
    {"id": "REFACTOR", "name": "重构整个项目", "type": "Skill", "rarity": "Rare", "cost": 1, "target": "self",
     "upgrade": {"cost": 0}, "effects": [{"op": "exhaust_hand", "save": "k"},
                                         {"op": "add_card", "card": "CODE_BLOCK", "n": "k", "to": "hand", "upgraded": True}]},
    {"id": "GOOD_IDEA", "name": "好主意，我照做！", "type": "Skill", "rarity": "Rare", "cost": 0, "target": "enemy",
     "keywords": ["exhaust"], "upgrade": {"add": ["retain"]},
     "effects": [{"op": "apply", "power": "STRENGTH", "amount": "max(0, stacks(T, 'STRENGTH'))", "target": "self"}]},
]
NEW_POWERS = [
    {"id": "FK_COLLECTIVE", "name": "风控连坐制", "type": "buff", "stack": "single",
     "triggers": [{"template": "on_enemy_died", "do": [
         {"op": "set", "name": "x", "value": FK},
         {"op": "foreach", "target": "all", "do": [give("x", **{"if": "x > 0"})]}]}]},
    {"id": "CODE_START", "name": "Claude Code，启动！", "type": "buff",
     "triggers": [{"template": "at_turn_start", "do": [{"op": "add_card", "card": "CODE_BLOCK", "n": "amount", "to": "hand"}]}]},
    {"id": "AUTOMATION", "name": "流程自动化（本回合）", "type": "buff", "stack": "single", "expire": "turn_end",
     "triggers": [{"template": "on_power_applied", "power": "FK", "active_only": True, "do": [{"op": "draw", "n": 1}]}]},
    {"id": "ONE_FOR_ALL", "name": "一人违规全员连坐", "type": "buff",
     "triggers": [{"template": "on_power_applied", "power": "FK", "if": "not multi", "do": [
         {"op": "foreach", "target": "others", "do": [give("amount", secondary=True)]}]},
                  {"template": "boost_apply", "power": "FK", "add": "amount", "if": "n_enemies() == 1", "once": "turn"}]},
    {"id": "GOLDEN_GATE", "name": "金门大桥", "type": "buff", "stack": "single",
     "triggers": [{"template": "replay_first", "card_type": "Attack"}]},
]
NEEDS_PYTHON = {
    "MCP 工具调用": "从 3 张随机牌里选 1 张加入手牌并本回合 0 费：需要“发现”式选择界面和临时改费",
    "长上下文": "回合结束时保留至多 N 张手牌：需要回合结束时让 AI 选牌并改写弃牌流程",
    "数据留存政策": "回合开始清空格挡前保留部分格挡：需要改写游戏的清空格挡钩子",
    "深度思考": "只能作为本回合第一张牌打出：需要“能不能打出”的条件钩子",
    "Ctrl+Z": "把本回合最近打出的牌从弃牌堆/消耗堆拿回：需要出牌历史",
}

TARGET = {"AnyEnemy": "enemy", "Self": "self", "AllEnemies": "all", "RandomEnemy": "random"}
KW = {"Exhaust": "exhaust", "Retain": "retain", "Innate": "innate", "Ethereal": "ethereal"}


def convert_card(cid, sp):
    v = dict(sp.get("vars", {}))
    play = sp["play"]
    effects = power_play(play, v) if play.startswith("power:") else PLAY[play](v)
    up_vars = {k: v.get(k, 0) + d for k, d in sp.get("up", {}).items() if k != "cost"}
    up = {}
    if up_vars:
        up["vars"] = up_vars
    if "cost" in sp.get("up", {}):
        up["cost"] = sp["cost"] + sp["up"]["cost"]
    if sp.get("up_kw"):
        up["add"] = [KW[k] for k in sp["up_kw"]]
    if sp.get("up_name"):
        up["name"] = sp["up_name"]
    c = {"id": cid, "name": sp["name"], "type": sp["type"], "rarity": sp["rarity"], "cost": sp["cost"],
         "target": TARGET[sp["target"]]}
    if sp.get("kw"):
        c["keywords"] = [KW[k] for k in sp["kw"]]
    c["vars"] = v
    if up:
        c["upgrade"] = up
    c["effects"] = effects
    if cid in ("CLAUDE_STRIKE", "CLAUDE_DEFEND"):
        c["tags"] = ["Strike" if cid == "CLAUDE_STRIKE" else "Defend"]
    short = cid[7:] if cid.startswith("CLAUDE_") else cid
    ai = {}
    if short in AIV.V:
        ai = {"value": AIV.V[short][0], "tags": AIV.V[short][1]}
    if play in ("verified", "dmg_per_fk"):
        ai["scaling"] = True
        if play == "dmg_per_fk":
            ai["keep"] = True
    if ai:
        c["ai"] = ai
    return c


def convert_variant(over):
    out = {}
    cards = {}
    for cid, o in over.items():
        if cid == "_hp":
            out["hp"] = int(o)
        elif cid == "_starter":
            out["starting_deck"] = _deck(o)
        elif cid in CARDS:
            co = {}
            if "vars" in o:
                if any(k not in CARDS[cid]["vars"] for k in o["vars"]):
                    return None          # 引入了新变量（改效果的变体）：YAML 版不转
                co["vars"] = dict(o["vars"])
            if "up" in o:
                base = {**CARDS[cid]["vars"], **o.get("vars", {})}
                co["upgrade"] = {"vars": {k: base.get(k, 0) + d for k, d in o["up"].items() if k != "cost"}}
            if "cost" in o:
                co["cost"] = o["cost"]
            if "play" in o:
                return None
            if "up" not in o and "vars" in o:   # 只改基础值：升级值跟着同样的差值走
                ups = CARDS[cid].get("up", {})
                co["upgrade"] = {"vars": {k: co["vars"].get(k, CARDS[cid]["vars"][k]) + d for k, d in ups.items() if k != "cost"}}
            cards[cid] = co
        else:
            sp = dict(o)
            if sp.get("play") not in PLAY:
                return None
            cards[cid] = convert_card(cid, sp)
            cards[cid].pop("id")
    if cards:
        out["cards"] = cards
    return out


def _deck(lst):
    out, i = [], 0
    while i < len(lst):
        j = i
        while j < len(lst) and lst[j] == lst[i]:
            j += 1
        out.append(f"{lst[i]}×{j - i}" if j - i > 1 else lst[i])
        i = j
    return out


AI_HOOKS_HEADER = '''"""Claude娘 的 AI 估值（只影响 AI 怎么选牌/出牌，不是规则）。由 tools/convert_claude_v35.py 从 mods/claude_v35/ai_values.py 复制，
只把「哪些牌是按层数加伤的兑现牌」改成从 YAML 卡表读（ai.scaling）。不需要的话删掉 mod.yaml 里的 ai_hooks 即可，
AI 会改用通用估值（卡牌 ai.value + 每层风控价值 ai_values）。"""
'''


def make_ai_hooks():
    src = open(os.path.join(ROOT, "mods", "claude_v35", "ai_values.py"), encoding="utf-8").read()
    src = src.split('"""', 2)[2]          # 去掉原来的文档字符串
    src = re.sub(r"def _scaling_cards\(\):\n(    .*\n)+",
                 "def _scaling_cards():\n"
                 "    return {c['id']: {'vars': c['vars'], 'ai': c['ai'].get('value', 1.0),\n"
                 "                      'play': 'dmg_per_fk' if c['ai'].get('keep') else 'verified'}\n"
                 "            for c in MOD.data['cards'] if (c.get('ai') or {}).get('scaling')}\n", src)
    src = src.replace("def register():", "def register_values():")
    src += ("\n\ndef register(mod):\n"
            "    \"\"\"yamlmod 在注册完卡牌后调用。\"\"\"\n"
            "    register_values()\n"
            "    register_play()\n")
    return AI_HOOKS_HEADER + src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "mods", "claude_yaml"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cards = [convert_card(cid, sp) for cid, sp in CARDS.items()]
    variants = {}
    skipped = []
    for name, over in VARIANTS.items():
        cv = convert_variant(over)
        if cv is None:
            skipped.append(name)
        else:
            variants[name] = cv
    variants["new_cards"] = {"add_cards": ["cards_new.yaml"]}
    meta = {
        "name": "claude_yaml", "title": "Claude娘 v3.5.1（YAML 数据版）", "prefix": "Claude",
        "characters": {"Claude": {"name": "Claude娘", "class": "ClaudeChan", "hp": STARTING_HP, "energy": 3, "gold": 99,
                                  "starting_deck": ["CLAUDE_STRIKE×4", "CLAUDE_DEFEND×4", "NOTEBOOK", "VERIFIED"],
                                  "relics": ["CONSTITUTION"]}},
        "cards": ["cards.yaml"], "powers": ["powers.yaml", "powers_new.yaml"], "relics": ["relics.yaml"],
        "helpers": {"fk(x)": "stacks(x, 'FK')"},
        "ai_values": {"FK": 1.2},
        "ai_hooks": "ai_hooks.py",
        "variants": variants,
    }
    dump = lambda x: yaml.safe_dump(x, allow_unicode=True, sort_keys=False, width=140)  # noqa
    hdr = "# 由 tools/convert_claude_v35.py 从 mods/claude_v35 生成。改数值直接改这里；重新生成会覆盖。\n"
    open(os.path.join(a.out, "mod.yaml"), "w", encoding="utf-8").write(hdr + dump(meta))
    open(os.path.join(a.out, "cards.yaml"), "w", encoding="utf-8").write(hdr + dump(cards))
    open(os.path.join(a.out, "powers.yaml"), "w", encoding="utf-8").write(hdr + dump(POWERS))
    open(os.path.join(a.out, "powers_new.yaml"), "w", encoding="utf-8").write(
        "# 下面这些能力只被 cards_new.yaml 里的新牌用到（变体 new_cards）。\n" + dump(NEW_POWERS))
    open(os.path.join(a.out, "relics.yaml"), "w", encoding="utf-8").write(hdr + dump(RELICS))
    open(os.path.join(a.out, "cards_new.yaml"), "w", encoding="utf-8").write(
        "# 手写 Python 版没实现的牌，按设计文档 v3.5 的文字直接写成 YAML（--variant new_cards 打开）。\n" + dump(NEW_CARDS))
    open(os.path.join(a.out, "ai_hooks.py"), "w", encoding="utf-8").write(make_ai_hooks())
    plays = {sp["play"].split(":")[0] if not sp["play"].startswith("power:") else sp["play"] for sp in CARDS.values()}
    design = json.load(open(os.path.join(ROOT, "mods", "claude_v35", "design_v35.json"), encoding="utf-8"))
    n_design = len(design["cards"])
    stats = {
        "design_cards": n_design,
        "converted_from_python_port": sum(1 for sp in CARDS.values() if sp["rarity"] != "Token"),
        "token_cards": sum(1 for sp in CARDS.values() if sp["rarity"] == "Token"),
        "new_yaml_cards": len(NEW_CARDS),
        "needs_python": len(NEEDS_PYTHON),
        "distinct_play_impls": len(plays),
        "variants_converted": sorted(variants), "variants_skipped": skipped,
    }
    stats["yaml_total"] = stats["converted_from_python_port"] + stats["new_yaml_cards"]
    json.dump({"stats": stats, "needs_python": NEEDS_PYTHON}, open(os.path.join(a.out, "conversion.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
