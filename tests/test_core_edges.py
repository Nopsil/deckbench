"""战斗核心的边界：过量伤害不能把生命打成负数，中毒统计按实际失去的生命算。"""
import random

from sts2sim.core import Combat, Creature, Player
from sts2sim.powers import Poison


class _Mod:
    listeners = []
    hook_modules = []
    cards = {}


class _Foe(Creature):
    def __init__(self, name, hp):
        super().__init__(name, hp)
        self.data = {}
        self.max_hp = hp


def _combat(*foes):
    return Combat(Player("铁甲", 70), list(foes), _Mod(), rng=random.Random(0))


def test_overkill_stops_at_zero_hp_and_records_actual_loss():
    foe = _Foe("木桩", 4)
    combat = _combat(foe)
    combat.push_attr("打击")
    lost = combat.deal_damage(combat.player, foe, 9, "attack")
    assert lost == 4
    assert foe.hp == 0
    assert foe.alive is False
    assert combat.stats.card["打击"][1] == 4


def test_poison_records_hp_lost_not_the_full_stack_when_the_target_revives():
    victim = _Foe("木桩", 5)
    victim.max_hp = 40
    victim.powers["ILLUSION"] = type("Illusion", (), {"amount": 1, "data": {}})()
    friend = _Foe("同伴", 12)
    combat = _combat(victim, friend)
    poison = Poison(victim, 8, src="毒雾")
    victim.powers["POISON"] = poison
    poison.on_turn_start(combat, type("Ev", (), {"creature": victim, "side": "enemy"})())
    assert victim.alive is True
    assert victim.hp == 40
    assert combat.stats.card["毒雾"][1] == 5


def test_lethal_poison_does_not_leave_negative_hp():
    foe = _Foe("木桩", 5)
    combat = _combat(foe)
    poison = Poison(foe, 8, src="毒雾")
    foe.powers["POISON"] = poison
    poison.on_turn_start(combat, type("Ev", (), {"creature": foe, "side": "enemy"})())
    assert foe.hp == 0
    assert foe.alive is False
    assert combat.stats.card["毒雾"][1] == 5


def test_nonlethal_poison_still_ticks_for_the_stack():
    foe = _Foe("木桩", 10)
    combat = _combat(foe)
    poison = Poison(foe, 3, src="毒雾")
    foe.powers["POISON"] = poison
    poison.on_turn_start(combat, type("Ev", (), {"creature": foe, "side": "enemy"})())
    assert foe.hp == 7
    assert foe.alive is True
    assert combat.stats.card["毒雾"][1] == 3
    assert foe.powers["POISON"].amount == 2
