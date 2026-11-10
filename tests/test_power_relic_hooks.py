"""能力、敌人能力和遗物钩子，走 Combat 的结算而不是直接调用钩子。

不启动游戏。数值按各能力上的说明：仪式在敌人自己施加的那个回合结束时不加力量，
易伤/虚弱按 1.5 和 0.75 相乘后再取整，人工制品在修正层数之前抵消。
"""
import random

from sts2sim.core import Combat, Creature, Player, Power, register_power
from sts2sim.cards import CardDef
from sts2sim.core import Card
from sts2sim.relics import Relic, make_relic, register_relic

import sts2sim.powers  # noqa: F401
import sts2sim.powers_enemy  # noqa: F401


class _Mod:
    def __init__(self):
        self.listeners = []
        self.hook_modules = []
        self.cards = {}

    def call(self, name, *args, **kwargs):
        raise AssertionError(name)


class _Foe(Creature):
    def __init__(self, name, hp, mid="DUMMY"):
        super().__init__(name, hp)
        self.data = {}
        self.m = type("M", (), {"id": mid, "ai": {"states": {"SLASH_MOVE": 1, "ROLL_OUT_MOVE": 1}}})()
        self.intent = None
        self.stunned = None

    def stun(self, state=None):
        self.stunned = state
        self.data["stunned"] = True

    def intent_bonus(self):
        return 0

    def choose_intent(self, combat):
        return None

    def setup(self, combat):
        return None

    def take_turn(self, combat):
        return None


def _combat(*foes, hp=50, energy=3):
    player = Player("铁甲", hp)
    player.energy = energy
    player.draw_per_turn = 0
    combat = Combat(player, list(foes), _Mod(), rng=random.Random(0))
    combat.phase = "player"
    combat.turn = 1
    return combat


def _card(type_="攻击", cost=1, effects=None, target="enemy"):
    return Card(CardDef({
        "id": "T", "name": "测", "type": type_, "cost": cost, "target": target,
        "effects": effects or [],
    }))


def _play(combat, card, target):
    combat.player.hand = [card]
    return combat.play(0, target)


@register_relic
class _Lizard(Relic):
    id = "_COV_LIZARD"

    def on_player_would_die(self, combat, ev):
        if not self.data.get("used"):
            self.data["used"] = True
            combat.player.hp = 1


@register_relic
class _Surcharge(Relic):
    id = "_COV_SURCHARGE"

    def on_modify_cost(self, combat, ev):
        if ev.card.type == "攻击" and ev.cost is not None:
            ev.cost += 1


@register_relic
class _MoreWeak(Relic):
    id = "_COV_MORE_WEAK"
    seen = 0

    def on_modify_apply(self, combat, ev):
        type(self).seen += 1
        if ev.pid == "WEAK":
            ev.amount += 1


def test_strength_weak_vulnerable_intangible_and_thorns():
    foe = _Foe("木桩", 40)
    combat = _combat(foe)
    combat.apply_power(combat.player, "STRENGTH", 3)
    combat.apply_power(combat.player, "WEAK", 1)
    combat.apply_power(foe, "VULNERABLE", 1)
    lost = combat.deal_damage(combat.player, foe, 10, "attack")
    # (10+3)*0.75*1.5 = 14.625 → 14
    assert lost == 14 and foe.hp == 26

    combat.apply_power(foe, "INTANGIBLE", 1)
    lost = combat.deal_damage(combat.player, foe, 10, "attack")
    assert lost == 1 and foe.hp == 25
    combat.emit("turn_end", side="enemy", creature=foe)
    assert "INTANGIBLE" not in foe.powers

    combat.apply_power(foe, "THORNS", 3)
    combat.player.hp = 20
    combat.deal_damage(combat.player, foe, 4, "attack")
    assert combat.player.hp == 17
    foe.powers.pop("VULNERABLE", None)
    before = foe.hp
    combat.deal_damage(foe, foe, 4, "attack")
    assert foe.hp == before - 4


def test_slippery_hard_to_kill_and_hardened_shell_cap_the_loss():
    foe = _Foe("木桩", 30)
    combat = _combat(foe)
    combat.apply_power(foe, "SLIPPERY", 2)
    assert combat.deal_damage(combat.player, foe, 9, "attack") == 1
    assert foe.hp == 29 and foe.amt("SLIPPERY") == 1
    assert combat.deal_damage(combat.player, foe, 9, "attack") == 1
    assert "SLIPPERY" not in foe.powers

    foe.hp = 30
    combat.apply_power(foe, "HARD_TO_KILL", 4)
    assert combat.deal_damage(combat.player, foe, 9, "hp_loss") == 4
    assert foe.hp == 26

    player = combat.player
    player.hp = 30
    combat.apply_power(player, "HARDENED_SHELL", 5)
    assert combat.deal_damage(foe, player, 9, "attack") == 5
    assert combat.deal_damage(foe, player, 9, "attack") == 0
    combat.emit("turn_start", side="player", creature=player)
    assert combat.deal_damage(foe, player, 9, "attack") == 5


def test_block_powers_and_barricade_keep_block_for_the_owner():
    foe = _Foe("木桩", 20)
    combat = _combat(foe)
    combat.apply_power(combat.player, "DEXTERITY", 5)
    combat.apply_power(foe, "PLATING", 1)
    combat.emit("turn_end", side="enemy", creature=foe)
    assert foe.block == 1
    combat.emit("turn_start", side="enemy", creature=foe)
    assert "PLATING" not in foe.powers

    combat.apply_power(foe, "CURL_UP", 6)
    foe.block = 0
    combat.deal_damage(combat.player, foe, 4, "hp_loss")
    assert foe.block == 0 and "CURL_UP" in foe.powers
    combat.deal_damage(combat.player, foe, 1, "attack")
    assert foe.block == 6 and "CURL_UP" not in foe.powers

    combat.apply_power(foe, "SKITTISH", 4)
    foe.block = 0
    combat.deal_damage(combat.player, foe, 1, "attack")
    combat.deal_damage(combat.player, foe, 1, "attack")
    assert foe.block == 3
    combat.emit("turn_start", side="player", creature=combat.player)
    combat.deal_damage(combat.player, foe, 1, "attack")
    assert foe.block == 6

    combat.apply_power(combat.player, "RAMPART", 1)
    combat.player.block = 0
    combat.emit("turn_start", side="player", creature=combat.player)
    assert combat.player.block == 25
    combat.player.powers.pop("RAMPART", None)

    combat.player.block = 8
    combat.apply_power(combat.player, "BARRICADE", 1)
    combat.player.draw_per_turn = 0
    combat.start_player_turn()
    assert combat.player.block == 8


def test_ritual_skips_only_the_turn_it_was_applied_and_territorial_does_not():
    foe = _Foe("木桩", 20)
    combat = _combat(foe)
    combat.apply_power(foe, "RITUAL", 2, source=("enemy", foe))
    combat.emit("turn_end", side="enemy", creature=foe)
    assert foe.amt("STRENGTH") == 0
    combat.emit("turn_end", side="enemy", creature=foe)
    assert foe.amt("STRENGTH") == 2

    other = _Foe("乙", 20)
    combat.enemies.append(other)
    combat.apply_power(other, "TERRITORIAL", 3, source=("enemy", other))
    combat.emit("turn_end", side="enemy", creature=other)
    assert other.amt("STRENGTH") == 3


def test_vigor_enrage_demon_form_fumes_and_next_turn_buffs():
    foe = _Foe("木桩", 40)
    combat = _combat(foe, energy=10)
    combat.apply_power(combat.player, "VIGOR", 4)
    _play(combat, _card(effects=[{"op": "damage", "amount": 6}]), foe)
    assert foe.hp == 30 and "VIGOR" not in combat.player.powers
    combat.apply_power(combat.player, "VIGOR", 4)
    _play(combat, _card(type_="技能", target="none", effects=[{"op": "block", "amount": 1}]), None)
    assert combat.player.amt("VIGOR") == 4

    combat.apply_power(foe, "ENRAGE", 2)
    _play(combat, _card(type_="技能", target="none", effects=[]), None)
    assert foe.amt("STRENGTH") == 2
    _play(combat, _card(effects=[{"op": "damage", "amount": 1}]), foe)
    assert foe.amt("STRENGTH") == 2

    combat.apply_power(combat.player, "DEMON_FORM", 2)
    combat.apply_power(combat.player, "NOXIOUS_FUMES", 3)
    combat.apply_power(combat.player, "NEXT_ENERGY", 2)
    combat.apply_power(combat.player, "NEXT_BLOCK", 4)
    top = _card(type_="技能", cost=0, target="none")
    mid = _card(type_="技能", cost=0, target="none")
    low = _card(type_="技能", cost=0, target="none")
    combat.player.draw_pile = [low, mid, top]
    combat.player.draw_per_turn = 1
    combat.apply_power(combat.player, "NEXT_DRAW", 2)
    combat.player.energy_per_turn = 3
    combat.start_player_turn()
    assert combat.player.energy == 5
    assert combat.player.block == 4
    assert combat.player.amt("STRENGTH") == 2
    assert foe.amt("POISON") == 3
    assert len(combat.player.hand) == 3
    assert "NEXT_ENERGY" not in combat.player.powers
    assert "NEXT_DRAW" not in combat.player.powers
    assert "NEXT_BLOCK" not in combat.player.powers


def test_no_draw_blocks_mid_turn_draw_but_not_the_opening_draw():
    combat = _combat()
    a = _card(type_="技能", cost=0, target="none")
    b = _card(type_="技能", cost=0, target="none")
    combat.player.draw_pile = [a, b]
    combat.apply_power(combat.player, "NO_DRAW", 1)
    assert combat.draw(1) == []
    combat.data["_drawing_turn"] = True
    assert combat.draw(1) == [b]
    combat.data["_drawing_turn"] = False
    combat.emit("turn_end", side="player", creature=combat.player)
    assert "NO_DRAW" not in combat.player.powers
    assert combat.draw(1) == [a]


def test_flame_barrier_asleep_and_slumber():
    foe = _Foe("木桩", 30)
    combat = _combat(foe)
    combat.apply_power(combat.player, "FLAME_BARRIER", 4)
    combat.deal_damage(foe, combat.player, 3, "attack")
    assert foe.hp == 26
    combat.emit("turn_start", side="player", creature=combat.player)
    assert "FLAME_BARRIER" not in combat.player.powers

    combat.apply_power(foe, "PLATING", 5)
    combat.apply_power(foe, "ASLEEP", 2)
    foe.block = 8
    combat.deal_damage(combat.player, foe, 3, "attack")
    assert "ASLEEP" in foe.powers and foe.amt("PLATING") == 5
    foe.block = 0
    combat.deal_damage(combat.player, foe, 3, "attack")
    assert "ASLEEP" not in foe.powers and "PLATING" not in foe.powers
    assert foe.stunned == "SLASH_MOVE"

    slumber = _Foe("乙", 30)
    combat.enemies.append(slumber)
    combat.apply_power(slumber, "SLUMBER", 2)
    combat.deal_damage(combat.player, slumber, 1, "attack")
    assert slumber.amt("SLUMBER") == 1 and slumber.stunned is None
    combat.deal_damage(combat.player, slumber, 1, "attack")
    assert "SLUMBER" not in slumber.powers and slumber.stunned == "ROLL_OUT_MOVE"


def test_enemy_damage_hooks_constrict_paper_shrink_slow_suck_and_back_attack():
    foe = _Foe("绞杀", 30, mid="SLITHERING_STRANGLER")
    combat = _combat(foe, hp=30)
    combat.apply_power(combat.player, "CONSTRICT", 4)
    combat.emit("turn_end", side="player", creature=combat.player)
    assert combat.player.hp == 26
    foe.alive = False
    combat.emit("turn_end", side="player", creature=combat.player)
    assert combat.player.hp == 26

    foe.alive = True
    combat.apply_power(foe, "PAPER_CUTS", 6)
    combat.player.block = 10
    combat.player.max_hp = 40
    combat.deal_damage(foe, combat.player, 4, "attack")
    assert combat.player.max_hp == 40
    combat.player.block = 0
    combat.deal_damage(foe, combat.player, 4, "attack")
    assert combat.player.max_hp == 34 and combat.player.hp == 22

    combat.apply_power(foe, "SHRINK", 1)
    assert combat.deal_damage(foe, combat.player, 10, "attack") == 7
    foe.powers.pop("SHRINK", None)

    combat.cards_played_turn = [_card()]
    combat.apply_power(foe, "SLOW", 1)
    assert combat.deal_damage(combat.player, foe, 10, "attack") == 11

    before = foe.amt("STRENGTH")
    combat.player.block = 5
    combat.apply_power(foe, "SUCK", 2)
    combat.deal_damage(foe, combat.player, 3, "attack")
    assert foe.amt("STRENGTH") == before
    combat.player.block = 0
    combat.deal_damage(foe, combat.player, 3, "attack")
    assert foe.amt("STRENGTH") == before + 2

    foe.powers.pop("STRENGTH", None)
    combat.cards_played_turn = []
    combat.apply_power(foe, "BACK_ATTACK_LEFT", 1)
    combat.player.hp = 40
    assert combat.deal_damage(foe, combat.player, 10, "attack") == 15
    right = _Foe("右", 20)
    combat.enemies.append(right)
    combat.apply_power(right, "BACK_ATTACK_RIGHT", 1)
    combat.player.hp = 40
    assert combat.deal_damage(right, combat.player, 10, "attack") == 15


def test_play_restrictions_tangled_tender_ringing_and_smoggy():
    foe = _Foe("木桩", 20)
    combat = _combat(foe, energy=10)
    combat.apply_power(combat.player, "TANGLED", 2)
    attack = _card(cost=1)
    skill = _card(type_="技能", cost=1, target="none")
    assert combat.card_cost(attack) == 3
    assert combat.card_cost(skill) == 1

    combat.apply_power(combat.player, "STRENGTH", 3)
    combat.apply_power(combat.player, "DEXTERITY", 3)
    combat.apply_power(combat.player, "TENDER", 1)
    _play(combat, skill, None)
    assert combat.player.amt("STRENGTH") == 2 and combat.player.amt("DEXTERITY") == 2
    combat.emit("turn_end", side="player", creature=combat.player)
    assert "TENDER" not in combat.player.powers
    assert "TANGLED" not in combat.player.powers

    combat.cards_played_turn = []
    combat.apply_power(combat.player, "RINGING", 1)
    first = _card()
    second = _card()
    assert combat.can_play(first) is True
    combat.cards_played_turn.append(first)
    assert combat.can_play(second) is False

    combat.cards_played_turn = []
    combat.player.powers.pop("RINGING", None)
    combat.apply_power(combat.player, "SMOGGY", 1)
    skill_a = _card(type_="技能", target="none")
    skill_b = _card(type_="技能", target="none")
    assert combat.can_play(skill_a) is True
    combat.cards_played_turn.append(skill_a)
    assert combat.can_play(skill_b) is False
    assert combat.can_play(_card()) is True


def test_hex_hive_burrowed_escape_nemesis_crab_and_ravenous():
    knight = _Foe("骑士", 20, mid="SPECTRAL_KNIGHT")
    combat = _combat(knight)
    keep = _card(type_="技能", cost=0, target="none")
    keep.d.kw = frozenset({"retain"})
    drop = _card(type_="技能", cost=0, target="none")
    combat.player.hand = [keep, drop]
    combat.apply_power(combat.player, "HEX", 1)
    knight.alive = False
    combat.emit("turn_end", side="player", creature=combat.player)
    assert drop in combat.player.hand
    knight.alive = True
    combat.emit("turn_end", side="player", creature=combat.player)
    assert combat.player.hand == [keep]
    assert drop in combat.player.exhaust_pile

    hive = _Foe("蜂", 20)
    combat.enemies.append(hive)
    combat.mod.cards["DAZED"] = CardDef({
        "id": "DAZED", "name": "晕眩", "type": "状态", "cost": None, "target": "none", "effects": [],
    })
    combat.apply_power(hive, "PERSONAL_HIVE", 1)
    combat.deal_damage(combat.player, hive, 1, "attack")
    assert [c.id for c in combat.player.draw_pile] == ["DAZED"]

    burrow = _Foe("埋", 20)
    combat.enemies.append(burrow)
    combat.apply_power(burrow, "BURROWED", 1)
    burrow.block = 8
    combat.enemy_phase()
    assert burrow.block == 8
    combat.deal_damage(combat.player, burrow, 3, "attack")
    assert burrow.stunned is None and "BURROWED" in burrow.powers
    combat.deal_damage(combat.player, burrow, 5, "attack")
    assert burrow.data.get("stunned") is True and "BURROWED" not in burrow.powers

    left = _Foe("逃", 10)
    crab = _Foe("蟹", 20)
    fight = _combat(left, crab)
    fight.apply_power(left, "ESCAPE_ARTIST", 1)
    fight.apply_power(crab, "CRAB_RAGE", 1)
    fight.emit("turn_end", side="enemy", creature=left)
    assert left.alive is False and fight.result is None
    assert crab.amt("STRENGTH") == 0 and crab.block == 0
    snack = _Foe("饵", 5)
    fight.enemies.append(snack)
    fight.apply_power(crab, "RAVENOUS", 1)
    fight.kill(snack)
    assert crab.amt("STRENGTH") == 6 + 1 and crab.block == 99 and crab.data.get("stunned") is True

    solo = _Foe("只", 10)
    last = _combat(solo)
    last.apply_power(solo, "ESCAPE_ARTIST", 1)
    last.emit("turn_end", side="enemy", creature=solo)
    assert solo.alive is False and last.result == "win"

    nemesis = _Foe("罚", 20)
    tick = _combat(nemesis)
    tick.apply_power(nemesis, "NEMESIS", 1)
    tick.emit("turn_end", side="enemy", creature=nemesis)
    assert nemesis.amt("INTANGIBLE") == 0
    tick.emit("turn_end", side="enemy", creature=nemesis)
    assert nemesis.amt("INTANGIBLE") == 1


def test_relic_hooks_prevent_death_change_cost_and_clone():
    foe = _Foe("木桩", 20)
    combat = _combat(foe, hp=5)
    lizard = _Lizard()
    surcharge = _Surcharge()
    more = _MoreWeak()
    _MoreWeak.seen = 0
    combat.relics = [lizard, surcharge, more]
    attack = _card(cost=1)
    assert combat.card_cost(attack) == 2
    combat.deal_damage(foe, combat.player, 9, "attack")
    assert combat.player.alive is True and combat.player.hp == 1 and combat.result is None
    assert lizard.data["used"] is True
    cloned = lizard.clone()
    cloned.data["used"] = False
    assert lizard.data["used"] is True

    combat.deal_damage(foe, combat.player, 9, "attack")
    assert combat.player.alive is False and combat.result == "loss"

    live = _combat(_Foe("乙", 10))
    live.relics = [_MoreWeak()]
    _MoreWeak.seen = 0
    live.apply_power(live.enemies[0], "ARTIFACT", 1)
    _MoreWeak.seen = 0
    assert live.apply_power(live.enemies[0], "WEAK", 2, source=("card", None)) == 0
    assert _MoreWeak.seen == 0 and "WEAK" not in live.enemies[0].powers
    assert live.apply_power(live.enemies[0], "WEAK", 2, source=("card", None)) == 3
    assert _MoreWeak.seen == 1

    assert make_relic("_COV_LIZARD").id == "_COV_LIZARD"
    try:
        make_relic("_COV_MISSING")
    except KeyError as exc:
        assert "_COV_MISSING" in str(exc)
    else:
        raise AssertionError("未注册的遗物应报错")
    assert surcharge.src() == ("relic", surcharge)
