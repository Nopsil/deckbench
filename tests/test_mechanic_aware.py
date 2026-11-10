"""荆棘、受击加格挡、多敌人总伤害：同一颗种子上，显式打开修正比默认（关）少掉血。

数字是这些构造局面的掉血（玩家起始生命减去打完时的生命）：

- 荆棘多段：启发式 16 → 7。束搜索默认深度已经先格挡，两边都是 7；只看一步时 16 → 7。
- 胆小（第一次被打才获得格挡）：启发式和束搜索都是 42 → 28。
- 两只敌人的意图伤害加在一起：启发式和束搜索都是 20 → 12。

``--explain`` 的候选 ``note`` 写 ``thorns:`` / ``armour`` / ``incoming:``。修正不抽额外的随机数。
"""
import random
import subprocess
import sys

import pytest

import sts2sim.powers  # noqa: F401  注册荆棘、胆小
from sts2sim import explain
from sts2sim.ai.base import as_bool, mechanic_adjust
from sts2sim.ai.beam import BeamAgent
from sts2sim.ai.heuristic import HeuristicAgent
from sts2sim.cards import CardDef
from sts2sim.core import Card, Combat, Player
from sts2sim.enemies import Enemy, MonsterDef
from sts2sim.modloader import ModSet
from sts2sim.runner import plan


class _Mod:
    listeners = []
    hook_modules = []
    cards = {}
    ai_values = {}


def _card(**raw):
    raw.setdefault("keywords", ["innate"])
    return CardDef(raw)


DEFEND = _card(id="DEFEND", name="防御", type="技能", cost=1, target="self",
               effects=[{"op": "block", "amount": 12}])
MULTI = _card(id="MULTI", name="连打", type="攻击", cost=1, target="enemy", multi_hit=True,
              effects=[{"op": "damage", "amount": 8, "hits": 4}])
STRIKE = _card(id="STRIKE", name="打击", type="攻击", cost=1, target="enemy",
               effects=[{"op": "damage", "amount": 6}])
BIG = _card(id="BIG", name="重击", type="攻击", cost=1, target="enemy",
            effects=[{"op": "damage", "amount": 14}])
# 格挡点数写在 vars 里，和真实卡一样，不是字面量。
SMALL = _card(id="DEF8", name="小防", type="技能", cost=1, target="self", vars={"b": 8},
              effects=[{"op": "block", "amount": "b"}])
FUTURE = _card(id="FUTURE", name="未来", type="攻击", cost=1, target="enemy",
               effects=[{"op": "damage", "amount": 1}])
OTHER = _card(id="OTHER", name="另一张", type="技能", cost=1, target="self",
              effects=[{"op": "block", "amount": 3}])


def _foe(name, hp, dmg, powers=None):
    raw = {
        "id": name, "name": name, "min_hp": hp, "max_hp": hp,
        "moves": [{"id": "HIT", "name": "打", "intent": "Attack",
                   "damage": {"normal": dmg, "hit_count": 1}}],
        "innate_powers": [{"power_id": k, "amount": v} for k, v in (powers or {}).items()],
    }
    return Enemy(MonsterDef(raw, name), random.Random(0))


def _fight(agent, cards, foes, hp, energy, hand, turns, seed=1, log=False):
    """牌都是固有，牌序不洗。种子固定。log 为真时打开 --explain 用的那条日志。"""
    explain.configure(on=log, reset=True)
    Card._uid[0] = 0
    player = Player("铁甲", hp, energy_per_turn=energy, hand_size=hand)
    player.draw_pile = [Card(c) for c in cards]
    enemies = [_foe(*f) for f in foes]
    combat = Combat(player, enemies, _Mod(), rng=random.Random(seed), agent=agent, max_turns=turns + 2)
    combat.start_battle()
    played = []
    start = player.hp
    for _ in range(turns):
        if combat.result:
            break
        combat.start_player_turn()
        if combat.result:
            break
        before = len(combat.cards_played_turn)
        combat.agent.play_turn(combat)
        played.extend(c.id for c in combat.cards_played_turn[before:])
        if combat.result:
            break
        combat.end_player_turn()
        if combat.result:
            break
        combat.enemy_phase()
    rows = explain.take()
    explain.configure(on=False, reset=True)
    lost = start if combat.result == "loss" or player.hp <= 0 else start - max(0, player.hp)
    return {"hp_lost": lost, "hp": player.hp, "result": combat.result, "played": played,
            "enemies": [(e.name, e.hp, e.alive) for e in combat.enemies], "rows": rows}


def _notes(rows):
    out = []
    for row in rows:
        for cand in row.get("candidates") or []:
            if cand.get("note"):
                out.append(cand["note"])
        chosen = row.get("chosen")
        if isinstance(chosen, dict) and chosen.get("note"):
            out.append(chosen["note"])
    return out


@pytest.fixture(autouse=True)
def _explain_off():
    explain.configure(on=False, reset=True)
    yield
    explain.configure(on=False, reset=True)


def test_thorns_block_before_multihit_loses_less_hp():
    foes = [("荆", 80, 3, {"THORNS": 4})]
    deck = [DEFEND, MULTI]
    off = _fight(HeuristicAgent(), deck, foes, 50, 2, 2, 1)
    on = _fight(HeuristicAgent(mechanic_aware=True), deck, foes, 50, 2, 2, 1, log=True)
    quiet = _fight(HeuristicAgent(mechanic_aware=True), deck, foes, 50, 2, 2, 1, log=False)
    assert off["played"] == ["MULTI", "DEFEND"]
    assert off["hp_lost"] == 16
    assert on["played"] == ["DEFEND", "MULTI"]
    assert on["hp_lost"] == 7
    assert quiet["hp_lost"] == on["hp_lost"] and quiet["played"] == on["played"]
    assert any(n.startswith("thorns:16") for n in _notes(on["rows"]))
    text = explain.render_fight(on["rows"], 0)
    assert "thorns:16" in text

    # 默认束搜索看得深，这两张牌本来就会先格挡。只展开一步时，修正本身把 16 降到 7。
    kw = dict(cards=deck, foes=foes, hp=50, energy=2, hand=2, turns=1)
    deep_off = _fight(BeamAgent(width=4, depth=3), **kw)
    deep_on = _fight(BeamAgent(width=4, depth=3, mechanic_aware=True), **kw, log=True)
    assert deep_off["hp_lost"] == 7 and deep_on["hp_lost"] == 7
    assert deep_on["played"][0] == "DEFEND"
    assert any("thorns:" in n for n in _notes(deep_on["rows"]))
    ply_off = _fight(BeamAgent(width=4, depth=1), **kw)
    ply_on = _fight(BeamAgent(width=4, depth=1, mechanic_aware=True), **kw)
    assert ply_off["hp_lost"] == 16 and ply_off["played"][0] == "MULTI"
    assert ply_on["hp_lost"] == 7 and ply_on["played"][0] == "DEFEND"


def test_skittish_focuses_the_unarmoured_enemy_and_loses_less_hp():
    foes = [("甲", 18, 7, {"SKITTISH": 8}), ("乙", 18, 7, {"SKITTISH": 8})]
    deck = [STRIKE] * 8
    for cls, kw in ((HeuristicAgent, {}), (BeamAgent, {"width": 4, "depth": 4})):
        off = _fight(cls(**kw), deck, foes, 70, 2, 5, 1)
        on = _fight(cls(mechanic_aware=True, **kw), deck, foes, 70, 2, 5, 1, log=True)
        full_off = _fight(cls(**kw), deck, foes, 70, 2, 5, 6)
        full_on = _fight(cls(mechanic_aware=True, **kw), deck, foes, 70, 2, 5, 6)
        assert off["enemies"] == [("甲", 12, True), ("乙", 18, True)]
        assert on["enemies"] == [("甲", 12, True), ("乙", 12, True)]
        assert any(n == "armour" for n in _notes(on["rows"]))
        assert full_off["hp_lost"] == 42 and full_off["result"] == "win"
        assert full_on["hp_lost"] == 28 and full_on["result"] == "win"


def test_lethal_hit_still_targets_the_armoured_enemy():
    """已经有格挡的那只，这一下能打死，就仍然打它，不改去打没格挡的。"""
    for flag in (False, True):
        Card._uid[0] = 0
        player = Player("铁甲", 40, energy_per_turn=1, hand_size=1)
        player.hand = [Card(BIG)]
        player.energy = 1
        armoured = _foe("甲", 8, 6)
        naked = _foe("乙", 30, 6)
        armoured.block = 5
        for foe in (armoured, naked):
            foe.intent = foe.m.moves["HIT"]
        combat = Combat(player, [armoured, naked], _Mod(), rng=random.Random(1),
                        agent=HeuristicAgent(mechanic_aware=flag), max_turns=2)
        combat.turn = 1
        combat.phase = "player"
        combat.agent.play_turn(combat)
        assert armoured.alive is False
        assert naked.alive is True
        assert naked.hp == 30


def test_total_incoming_blocks_before_a_pure_attack():
    foes = [("甲", 40, 10, {}), ("乙", 40, 10, {})]
    # 牌堆顶两张是小防和重击，未来留在牌堆里，修正只能看见「还剩 1 张」。
    deck = [FUTURE, BIG, SMALL]
    for cls, kw in ((HeuristicAgent, {}), (BeamAgent, {"width": 3, "depth": 2})):
        off = _fight(cls(**kw), deck, foes, 40, 1, 2, 1)
        on = _fight(cls(mechanic_aware=True, **kw), deck, foes, 40, 1, 2, 1, log=True)
        assert off["played"] == ["BIG"] and off["hp_lost"] == 20
        assert on["played"] == ["DEF8"] and on["hp_lost"] == 12
        assert any(n == "incoming:20>0x2+unknown" for n in _notes(on["rows"]))


def test_adjust_ignores_unseen_card_identity_and_does_not_draw_rng():
    Card._uid[0] = 0
    player = Player("铁甲", 40, energy_per_turn=1, hand_size=2)
    player.hand = [Card(BIG), Card(SMALL)]
    player.energy = 1
    player.draw_pile = [Card(FUTURE)]
    foes = [_foe("甲", 40, 10), _foe("乙", 40, 10)]
    combat = Combat(player, foes, _Mod(), rng=random.Random(1), agent=HeuristicAgent(mechanic_aware=True), max_turns=2)
    combat.turn = 1
    combat.phase = "player"
    for foe in foes:
        foe.intent = foe.m.moves["HIT"]
    state = combat.rng.getstate()
    clones = combat._clone_n
    HeuristicAgent(mechanic_aware=True).best_action(combat)
    assert combat.rng.getstate() == state
    aware_clones = combat._clone_n - clones
    combat._clone_n = clones
    HeuristicAgent().best_action(combat)
    assert combat.rng.getstate() == state
    assert combat._clone_n - clones == aware_clones

    strike = player.hand[0]
    sim = combat.clone()
    sim.play(0, sim.enemies[0])
    pen_future, note_future = mechanic_adjust(combat, sim, strike, foes[0], paid=1)
    player.draw_pile = [Card(OTHER)]
    pen_other, note_other = mechanic_adjust(combat, sim, strike, foes[0], paid=1)
    assert pen_future == pen_other
    assert note_future == note_other == "incoming:20>0x2+unknown"
    player.draw_pile = []
    player.discard = []
    pen_empty, note_empty = mechanic_adjust(combat, sim, strike, foes[0], paid=1)
    assert pen_empty < pen_future
    assert note_empty == "incoming:20>0x2"
    assert "FUTURE" not in note_future and "OTHER" not in note_other


def test_flag_defaults_off_and_experiment_kw_can_enable_it():
    assert as_bool(True) is True
    assert as_bool(False) is False
    assert as_bool("false") is False
    assert as_bool("off") is False
    assert as_bool("0") is False
    assert as_bool("true") is True
    assert as_bool(None, default=False) is False
    assert HeuristicAgent().mechanic_aware is False
    assert HeuristicAgent(mechanic_aware=True).mechanic_aware is True
    assert HeuristicAgent(mechanic_aware="yes").mechanic_aware is True
    assert BeamAgent().mechanic_aware is False
    assert BeamAgent(width=2, depth=1, mechanic_aware=True).mechanic_aware is True
    exp = {"mods": ["claude_v34"], "decks": ["claude_start"], "rooms": ["普通"], "fights": 1,
           "seed": 1, "agent": "heuristic", "agent_kw": {"mechanic_aware": True}}
    tasks = plan(exp, ModSet(["claude_v34"]), fights=1)
    assert tasks and tasks[0][1]["agent_kw"]["mechanic_aware"] is True
    plain = {"mods": ["claude_v34"], "decks": ["claude_start"], "rooms": ["普通"], "fights": 1, "seed": 1}
    assert plan(plain, ModSet(["claude_v34"]), fights=1)[0][1]["agent_kw"] == {}


def test_runner_help_lists_the_switch():
    proc = subprocess.run([sys.executable, "-m", "sts2sim.runner", "--help"],
                          check=False, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--mechanic-aware" in proc.stdout
    assert "--no-mechanic-aware" in proc.stdout
