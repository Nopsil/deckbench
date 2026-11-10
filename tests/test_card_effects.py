"""卡牌效果解释器的边界。不启动游戏，不改默认出牌。

重放（modify_play_count）是同一次打出：上一遍 set 出来的局部变量要清掉，
但 X 费牌这次付出的能量还在。对没有活目标施加能力时，save 记 0。
"""
import random

from sts2sim.cards import OPS, CardDef, PlayCtx, play_card, register_op, run_effects
from sts2sim.core import Card, Combat, Creature, Player, Power, register_power
from sts2sim.potions import POTION_DEFS, PotionDef, use_potion

import sts2sim.powers  # noqa: F401  注册力量、敏捷、易伤


class _Mod:
    def __init__(self):
        self.listeners = []
        self.hook_modules = []
        self.cards = {}
        self.fns = {}

    def call(self, name, *args, **kwargs):
        return self.fns[name](*args, **kwargs)


class _Agent:
    def __init__(self, picks=None):
        self.picks = list(picks or [])

    def choose_cards(self, combat, kind, opts, n, ctx):
        chosen = [c for c in self.picks if c in opts]
        if chosen:
            return chosen[:n]
        return list(opts)[:n]


class _Foe(Creature):
    def __init__(self, name, hp):
        super().__init__(name, hp)
        self.data = {}


@register_power
class _Echo(Power):
    id = "_COV_ECHO"

    def on_modify_play_count(self, combat, ev):
        ev.count += 1


@register_power
class _ExtraHit(Power):
    id = "_COV_EXTRA_HIT"

    def on_before_play(self, combat, ev):
        ev.ctx.extra_hits += 1


def _combat(*foes, energy=3, hp=40):
    player = Player("铁甲", hp)
    player.energy = energy
    mod = _Mod()
    combat = Combat(player, list(foes), mod, rng=random.Random(0), agent=_Agent())
    combat.phase = "player"
    combat.turn = 1
    return combat


def _defn(**over):
    raw = {
        "id": "T", "name": "测", "type": "攻击", "cost": 1, "target": "enemy",
        "effects": [],
    }
    raw.update(over)
    return CardDef(raw)


def _put(combat, defn, energy=None):
    card = Card(defn)
    combat.player.hand = [card]
    if energy is not None:
        combat.player.energy = energy
    return card


def _play(combat, defn, target=None, energy=None):
    card = _put(combat, defn, energy)
    if target is None and defn.target == "enemy" and combat.enemies:
        target = next(e for e in combat.enemies if e.alive)
    return combat.play(0, target)


def test_attack_uses_strength_and_a_skill_does_not():
    foe = _Foe("木桩", 30)
    combat = _combat(foe)
    combat.apply_power(combat.player, "STRENGTH", 3)
    _play(combat, _defn(effects=[{"op": "damage", "amount": 5}]))
    assert foe.hp == 22
    foe.hp = 30
    _play(combat, _defn(type="技能", effects=[{"op": "damage", "amount": 5, "target": "self"}]))
    assert combat.player.hp == 35
    assert foe.hp == 30


def test_targets_all_others_random_and_a_dead_primary():
    a = _Foe("甲", 20)
    b = _Foe("乙", 20)
    combat = _combat(a, b)
    _play(combat, _defn(effects=[{"op": "damage", "amount": 3, "target": "all"}]))
    assert a.hp == 17 and b.hp == 17
    _play(combat, _defn(effects=[{"op": "damage", "amount": 4, "target": "others"}]), target=a)
    assert a.hp == 17 and b.hp == 13
    _play(combat, _defn(effects=[{"op": "damage", "amount": 2, "target": "random_other"}]), target=a)
    assert a.hp == 17 and b.hp == 11
    a.alive = False
    _play(combat, _defn(effects=[{"op": "damage", "amount": 5}]), target=a)
    assert b.hp == 6


def test_unknown_target_and_unknown_op_raise():
    foe = _Foe("木桩", 10)
    combat = _combat(foe)
    card = Card(_defn())
    ctx = PlayCtx(combat, card, foe, 1)
    try:
        run_effects(ctx, [{"op": "damage", "amount": 1, "target": "front"}])
    except ValueError as exc:
        assert "front" in str(exc)
    else:
        raise AssertionError("未知目标应报错")
    try:
        run_effects(ctx, [{"op": "nope"}])
    except ValueError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("未知 op 应报错")


def test_multi_hit_extra_hits_each_hit_and_stop_when_the_fight_ends():
    foe = _Foe("木桩", 20)
    combat = _combat(foe, energy=10)
    combat.player.powers["_COV_EXTRA_HIT"] = _ExtraHit(combat.player, 1)
    _play(combat, _defn(effects=[
        {"op": "damage", "amount": 1, "hits": 2, "each_hit": [{"op": "energy", "n": 1}]},
        {"op": "damage", "amount": 1, "hits": 2},
    ]), energy=10)
    # 第一段 2 击 + 1 次额外，额外击打在这一段用掉；第二段仍是 2 击。每击回复 1 能量。
    assert foe.hp == 15
    assert combat.player.energy == 10 - 1 + 3

    foe.hp = 1
    combat.player.hp = 30
    _play(combat, _defn(effects=[
        {"op": "damage", "amount": 5},
        {"op": "heal", "amount": 4},
    ]))
    assert foe.alive is False and combat.result == "win"
    assert combat.player.hp == 30


def test_block_draw_energy_heal_lose_hp_and_add_card():
    foe = _Foe("木桩", 10)
    combat = _combat(foe, hp=10)
    combat.player.max_hp = 12
    combat.apply_power(combat.player, "DEXTERITY", 2)
    combat.apply_power(combat.player, "FRAIL", 1)
    top = Card(_defn(id="TOP", name="顶", type="技能", cost=0, target="none", effects=[]))
    bottom = Card(_defn(id="BOT", name="底", type="技能", cost=0, target="none", effects=[]))
    combat.player.draw_pile = [bottom, top]
    combat.mod.cards["DAZED"] = _defn(id="DAZED", name="晕眩", type="状态", cost=None, target="none")
    _play(combat, _defn(type="技能", target="none", effects=[
        {"op": "block", "amount": 10},
        {"op": "draw", "n": 1},
        {"op": "energy", "n": 2},
        {"op": "heal", "amount": 100},
        {"op": "lose_hp", "amount": 3},
        {"op": "add_card", "card": "DAZED", "n": 1, "to": "draw_top", "free_turn": True},
    ]), energy=3)
    assert combat.player.block == 9
    assert combat.player.hand == [top]
    assert [c.id for c in combat.player.draw_pile] == ["BOT", "DAZED"]
    assert combat.player.energy == 3 - 1 + 2
    assert combat.player.hp == 9
    added = combat.player.draw_pile[-1]
    assert added.id == "DAZED" and added.cost_turn == 0
    drawn = combat.draw(1)
    assert drawn == [added]


def test_add_card_full_hand_goes_to_discard_and_draw_inserts():
    combat = _combat(energy=5)
    filler = [Card(_defn(id=f"F{i}", name=str(i), type="技能", cost=0, target="none")) for i in range(10)]
    combat.mod.cards["DAZED"] = _defn(id="DAZED", name="晕眩", type="状态", cost=0, target="none")
    played = Card(_defn(type="技能", target="none", cost=0, effects=[
        {"op": "add_card", "card": "DAZED", "to": "hand"},
        {"op": "add_card", "card": "DAZED", "to": "discard", "upgraded": True},
        {"op": "add_card", "card": "DAZED", "to": "draw", "n": 1},
    ]))
    combat.player.hand = [played, *filler]
    combat.player.energy = 1
    combat.play(0, None)
    assert all(c.id != "DAZED" for c in combat.player.hand)
    assert combat.player.discard[0].id == "DAZED" and combat.player.discard[0].upgraded is False
    assert combat.player.discard[1].upgraded is True
    assert len(combat.player.draw_pile) == 1 and combat.player.draw_pile[0].id == "DAZED"


def test_if_foreach_repeat_choices_py_and_custom_op():
    a = _Foe("甲", 15)
    b = _Foe("乙", 15)
    keep = Card(_defn(id="KEEP", name="留", type="技能", cost=0, target="none"))
    drop = Card(_defn(id="DROP", name="弃", type="技能", cost=0, target="none"))
    combat = _combat(a, b, energy=10)
    combat.agent = _Agent([drop])
    seen = []
    combat.mod.fns["mark"] = lambda ctx, **k: seen.append((ctx.card.id, k.get("tag")))
    try:
        register_op("cov_ping", lambda ctx, eff: seen.append("ping"))
        _play(combat, _defn(effects=[
            {"op": "if", "cond": "False", "then": [{"op": "damage", "amount": 9}],
             "else": [{"op": "damage", "amount": 1, "target": "all"}]},
            {"op": "foreach", "target": "all", "do": [{"op": "apply", "power": "WEAK", "amount": 1}]},
            {"op": "repeat", "n": 2, "do": [{"op": "damage", "amount": 1}]},
            {"op": "py", "fn": "mark", "tag": "ok"},
            {"op": "cov_ping"},
        ]), target=a)
    finally:
        OPS.pop("cov_ping", None)
    assert a.hp == 12 and b.hp == 14
    assert a.amt("WEAK") == 1 and b.amt("WEAK") == 1
    assert seen == [("T", "ok"), "ping"]

    combat.player.hand = [keep, drop]
    combat.player.discard = []
    run_effects(PlayCtx(combat, Card(_defn()), a, 0), [
        {"op": "discard_choice", "n": 1, "save": "dumped"},
        {"op": "exhaust_choice", "n": 1, "save": "burned"},
    ])
    assert combat.player.discard == [drop]
    assert combat.player.hand == []
    assert combat.player.exhaust_pile == [keep]


def test_empty_choice_saves_zero_and_end_turn_skips_the_rest():
    foe = _Foe("木桩", 10)
    combat = _combat(foe, hp=20)
    ctx = PlayCtx(combat, Card(_defn()), foe, 0)
    run_effects(ctx, [
        {"op": "exhaust_choice", "n": 1, "save": "burned"},
        {"op": "end_turn"},
        {"op": "heal", "amount": 5},
    ])
    assert ctx.locals["burned"] == 0
    assert ctx.end_turn is True
    assert combat.player.hp == 20
    play_card(combat, _put(combat, _defn(type="技能", target="none", effects=[{"op": "end_turn"}])), None)
    assert combat.data.get("_force_end_turn") is True


def test_return_to_hand_exhaust_and_power_destination():
    foe = _Foe("木桩", 10)
    combat = _combat(foe, energy=5)
    card = _play(combat, _defn(effects=[{"op": "return_to_hand"}])).card
    assert card in combat.player.hand
    full = [Card(_defn(id=f"F{i}", name=str(i), type="技能", cost=0, target="none")) for i in range(10)]
    played = _put(combat, _defn(effects=[{"op": "return_to_hand"}]))
    combat.player.hand = [played, *full]
    combat.play(0, foe)
    assert played in combat.player.discard
    assert played not in combat.player.hand
    burned = _play(combat, _defn(keywords=["exhaust"], effects=[{"op": "damage", "amount": 1}]))
    assert burned.card in combat.player.exhaust_pile
    power = _play(combat, _defn(type="能力", target="none", effects=[]))
    assert power.card not in combat.player.hand
    assert power.card not in combat.player.discard
    assert power.card not in combat.player.exhaust_pile


def test_x_cost_replay_keeps_x_and_drops_set_locals():
    foe = _Foe("木桩", 40)
    combat = _combat(foe, energy=4)
    combat.player.powers["_COV_ECHO"] = _Echo(combat.player, 1)
    _play(combat, _defn(cost="X", effects=[
        {"op": "set", "name": "hit", "value": "X"},
        {"op": "damage", "amount": "hit"},
    ]), energy=4)
    assert combat.player.energy == 0
    assert foe.hp == 32

    foe.hp = 40
    combat.player.powers.pop("_COV_ECHO", None)
    _play(combat, _defn(vars={"hit": 1}, effects=[
        {"op": "damage", "amount": "hit"},
        {"op": "set", "name": "hit", "value": 9},
    ]), energy=3)
    assert foe.hp == 39
    combat.player.powers["_COV_ECHO"] = _Echo(combat.player, 1)
    _play(combat, _defn(vars={"hit": 1}, effects=[
        {"op": "damage", "amount": "hit"},
        {"op": "set", "name": "hit", "value": 9},
    ]), energy=3)
    assert foe.hp == 37


def test_apply_save_is_zero_when_nobody_is_alive_and_sums_when_someone_is():
    foe = _Foe("木桩", 10)
    foe.powers["ARTIFACT"] = sts2sim.powers.Artifact(foe, 1)
    combat = _combat(foe)
    ctx = PlayCtx(combat, Card(_defn()), foe, 0)
    run_effects(ctx, [{"op": "apply", "power": "WEAK", "amount": 2, "save": "applied"}])
    assert ctx.locals["applied"] == 0
    assert "WEAK" not in foe.powers
    assert "ARTIFACT" not in foe.powers

    empty = _combat()
    dead = _Foe("亡", 0)
    dead.alive = False
    empty.enemies = [dead]
    ctx = PlayCtx(empty, Card(_defn()), dead, 0)
    run_effects(ctx, [
        {"op": "apply", "power": "WEAK", "amount": 2, "target": "all", "save": "n"},
        {"op": "lose_hp", "amount": "n"},
    ])
    assert ctx.locals["n"] == 0
    assert empty.player.hp == 40

    live = _Foe("甲", 10)
    other = _Foe("乙", 10)
    both = _combat(live, other)
    ctx = PlayCtx(both, Card(_defn()), live, 0)
    run_effects(ctx, [{"op": "apply", "power": "WEAK", "amount": 2, "target": "all", "save": "n"}])
    assert ctx.locals["n"] == 4


def test_remove_and_set_stacks_honor_artifact_and_save_the_removed_count():
    foe = _Foe("木桩", 10)
    combat = _combat(foe)
    combat.apply_power(foe, "WEAK", 5)
    ctx = PlayCtx(combat, Card(_defn()), foe, 0)
    run_effects(ctx, [
        {"op": "remove_power", "power": "WEAK", "amount": 2, "save": "gone"},
        {"op": "set_stacks", "power": "POISON", "value": 4, "artifact_blocks": True},
    ])
    assert ctx.locals["gone"] == 2 and foe.amt("WEAK") == 3
    assert foe.amt("POISON") == 4
    foe.powers["ARTIFACT"] = sts2sim.powers.Artifact(foe, 1)
    run_effects(ctx, [{"op": "set_stacks", "power": "POISON", "value": 9, "artifact_blocks": True}])
    assert foe.amt("POISON") == 4
    assert "ARTIFACT" not in foe.powers
    run_effects(ctx, [{"op": "set_stacks", "power": "POISON", "value": 0}])
    assert "POISON" not in foe.powers
    run_effects(ctx, [{"op": "remove_power", "power": "WEAK", "amount": "all", "save": "gone"}])
    assert ctx.locals["gone"] == 3 and "WEAK" not in foe.powers


def test_cost_expr_can_play_and_potion_use_the_same_interpreter():
    foe = _Foe("木桩", 10)
    combat = _combat(foe, energy=5)
    combat.mod.fns["allow"] = lambda combat, card: False
    gated = _defn(cost_expr="2", can_play="allow")
    card = Card(gated)
    assert combat.card_cost(card) == 2
    assert combat.can_play(card) is False
    combat.mod.fns["allow"] = lambda combat, card: True
    assert combat.can_play(card) is True

    combat.player.hp = 10
    combat.player.max_hp = 20
    POTION_DEFS["_COV_POT"] = PotionDef({
        "id": "_COV_POT", "name": "药", "target": "none",
        "effects": [{"op": "heal", "amount": 5}, {"op": "block", "amount": 2}],
    })
    try:
        combat.player.potions = ["_COV_POT"]
        use_potion(combat, 0)
    finally:
        POTION_DEFS.pop("_COV_POT", None)
    assert combat.player.potions == []
    assert combat.player.hp == 15 and combat.player.block == 2


def test_replay_of_an_x_cost_card_is_the_energy_paid_once():
    """没有重放时，X 就是打出那一下付掉的能量。"""
    foe = _Foe("木桩", 20)
    combat = _combat(foe)
    _play(combat, _defn(cost="X", effects=[{"op": "damage", "amount": "X"}]), energy=5)
    assert foe.hp == 15 and combat.player.energy == 0
