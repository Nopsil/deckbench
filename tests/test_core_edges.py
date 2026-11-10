"""战斗核心的边界：过量伤害不能把生命打成负数，中毒统计按实际失去的生命算。

监听缓存必须和「先快照再调用」同一顺序：前面一组新加上的能力，这次事件看得到；
同一组里新加上的，这次看不到。
"""
import random

from sts2sim.core import Combat, Creature, Player, Power, register_power
from sts2sim.powers import Poison
from sts2sim.relics import Relic, register_relic


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


class _PingLog:
    order = []


@register_power
class _BenchLate(Power):
    id = "_BENCH_LATE"

    def on_ping(self, C, ev):
        _PingLog.order.append(("late", self.owner.name))


@register_power
class _BenchEarly(Power):
    id = "_BENCH_EARLY"

    def on_ping(self, C, ev):
        _PingLog.order.append(("early", self.owner.name))
        if "_BENCH_LATE" not in self.owner.powers:
            C.apply_power(self.owner, "_BENCH_LATE", 1)
        foe = C.enemies[0]
        if "_BENCH_LATE" not in foe.powers:
            C.apply_power(foe, "_BENCH_LATE", 1)


@register_relic
class _BenchRelic(Relic):
    id = "_BENCH_RELIC"

    def on_ping(self, C, ev):
        _PingLog.order.append(("relic",))
        if "_BENCH_EARLY" not in C.player.powers:
            C.apply_power(C.player, "_BENCH_EARLY", 1)


def test_emit_snapshot_shows_powers_added_for_later_groups_only():
    foe = _Foe("木桩", 20)
    combat = _combat(foe)
    combat.relics = [_BenchRelic()]
    _PingLog.order = []
    ev = combat.emit("ping")
    assert ev is not None
    # 遗物先跑，给玩家加上 Early。玩家这组的快照在遗物之后，所以 Early 这次看得到。
    # Early 再给自己加 Late：同一张表已经快照过，这次看不到。
    # Early 给敌人加 Late：敌人那组还没快照，这次看得到。
    assert _PingLog.order == [("relic",), ("early", "铁甲"), ("late", "木桩")]
    _PingLog.order = []
    combat.emit("ping")
    assert _PingLog.order == [
        ("relic",),
        ("early", "铁甲"),
        ("late", "铁甲"),
        ("late", "木桩"),
    ]
    foe.alive = False
    _PingLog.order = []
    combat.emit("ping")
    assert _PingLog.order == [("relic",), ("early", "铁甲"), ("late", "铁甲")]


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
