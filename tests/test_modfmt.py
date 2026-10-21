"""YAML 数据 mod（整局）：格式校验、模板展开、写回 / 读回，以及和手写 Python 版 Claude娘逐张牌对拍。"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sts2sim.modfmt import schema as S  # noqa: E402


def _mini(**over):
    files = {
        "mod.yaml": "name: mini\nprefix: Mini\ncharacters:\n  Hero: {name: Hero, hp: 70, starting_deck: ['HIT×5', 'GUARD×5'], relics: [COIN]}\n"
                    "cards: [cards.yaml]\npowers: [powers.yaml]\nrelics: [relics.yaml]\n",
        "cards.yaml": "- {id: HIT, type: 攻击, rarity: 基础, cost: 1, target: enemy, vars: {dmg: 6}, upgrade: {vars: {dmg: 9}}, effects: [{op: damage, amount: dmg}]}\n"
                      "- {id: GUARD, type: skill, rarity: Basic, cost: 1, target: self, vars: {blk: 5}, effects: [{op: block, amount: blk}]}\n"
                      "- {id: C1, type: Attack, rarity: Common, cost: 1, target: enemy, effects: [{template: scaled_damage, base: 4, power: SHOCK, per: 2}]}\n"
                      "- {id: U1, type: Skill, rarity: Uncommon, cost: 1, target: enemy, effects: [{op: apply, power: SHOCK, amount: 3}]}\n"
                      "- {id: C2, type: Skill, rarity: Common, cost: 0, target: self, effects: [{op: draw, n: 1}]}\n"
                      "- {id: R2, type: Attack, rarity: Rare, cost: 2, target: all, effects: [{op: damage, amount: 12, target: all}]}\n"
                      "- {id: R1, type: Power, rarity: Rare, cost: 2, target: self, effects: [{template: gain_power, power: AMP}]}\n",
        "powers.yaml": "- {id: SHOCK, type: debuff, decay: turn_start}\n- {id: AMP, triggers: [{template: bonus_damage, add: amount}]}\n",
        "relics.yaml": "- {id: COIN, rarity: 初始, triggers: [{template: at_battle_start, do: [{op: block, amount: 3}]}]}\n",
    }
    files.update(over)
    return S.load_mod_files(files)


def test_mini_mod_is_valid_and_normalized():
    m = _mini()
    pr, _w = S.validate(m, fullrun=True)
    assert pr == []
    hit = m["cards"][0]
    assert (hit["type"], hit["rarity"], hit["target"]) == ("Attack", "Basic", "AnyEnemy")
    assert m["relics"][0]["rarity"] == "Starter"


def test_plain_language_errors():
    m = _mini(**{"cards.yaml": "- {id: HIT, type: Attack, rarity: Basic, cost: 1, target: enemy, effects: [{op: damage, amount: dmgg}, {op: blast}]}\n"
                               "- {id: GUARD, type: Skill, rarity: Basic, cost: 1, effects: [{op: apply, power: no such, amount: 1}]}\n"})
    pr, _w = S.validate(m, fullrun=True)
    text = json.dumps(pr, ensure_ascii=False)
    assert "dmgg" in text                      # 不认识的名字
    assert "blast" in text                     # 不认识的操作
    assert "no such" in text                   # 不存在的能力
    for _where, zh, en in pr:                  # 中英双语
        assert zh and en


def test_small_pool_warnings_and_shop_rule():
    m = _mini()
    _pr, w = S.validate(m, fullrun=True)
    assert any("3" in en for _w, _zh, en in w)          # 每种稀有度少于 3 张：提醒
    m["cards"] = [c for c in m["cards"] if c["id"] != "C2"]
    pr, _w = S.validate(m, fullrun=True)
    assert any("shop" in en for _w, _zh, en in pr)      # 商店要 2 攻击 2 技能 1 能力


def test_templates_expand_to_ops():
    ops = S.expand_template({"template": "cash_in", "power": "P", "per": 3, "target": "all"})
    assert ops[0]["op"] == "foreach" and ops[0]["do"][0]["op"] == "remove_power"
    tr = S.expand_trigger({"template": "thorns", "amount": 2})
    assert tr["on"] == "attacked" and tr["do"][0]["kind"] == "unpowered"


def test_dump_roundtrip():
    m = _mini()
    m2 = S.load_mod_files(S.dump_mod_dir(m))
    strip = lambda xs: json.dumps(S._clean(xs), sort_keys=True, ensure_ascii=False)  # noqa
    for k in ("cards", "powers", "relics", "characters"):
        assert strip(m[k]) == strip(m2[k]), k


def test_claude_yaml_and_legacy_v34_validate():
    m = S.load_mod_dir(os.path.join(ROOT, "mods", "claude_yaml"))
    pr, _w = S.validate(m, fullrun=True)
    assert pr == []
    assert len(m["cards"]) >= 69
    old = S.load_mod_dir(os.path.join(ROOT, "mods", "claude_v34"))   # 旧格式照样能读
    assert old["decks"]


def test_yaml_cards_match_hand_port():
    """几张代表性的牌：YAML 版和手写 Python 版在同一局面下打出后的局面完全一样（全部 70 张见 tools/parity_yaml.py）。"""
    pytest.importorskip("sts2sim.gen.game")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "parity_yaml.py"), "--seeds", "C3",
                        "--only", "VERIFIED,CLASSIFIER,NOTEBOOK,AMENDMENT,OPUS_FORM,MASS_BAN"],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=ROOT), timeout=900)
    assert p.returncode == 0, p.stderr[-2000:]
    assert "不一致 0" in p.stdout and "场景 12 个" in p.stdout, p.stdout
