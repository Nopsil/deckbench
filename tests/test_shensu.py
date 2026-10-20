"""「反击」状态：没有反击无伤害；反击先按当前风控结算伤害再减 1 层；不算清除；上限与衰减；分类器三种强化；修正案。"""
import os
import random
from sts2sim.runner import get_modset, Dummy
from sts2sim.core import Combat

ENV = ("STS2SIM_FANJI", "STS2SIM_FLQ", "STS2SIM_FENLEIQI", "STS2SIM_GRANT", "STS2SIM_FANJI_AI")


def _setup(fanji="attack-2-L", flq="flat"):
    os.environ["STS2SIM_FANJI"] = fanji
    os.environ["STS2SIM_FLQ"] = flq
    M = get_modset(["vanilla", "claude_v34"])
    P, relics, _ = M.build_player("cl_def_a2")
    e = Dummy(500)
    C = Combat(P, [e], M, rng=random.Random(1), max_turns=3)
    C.relics = []
    C.data["cl_mod"] = True
    return C, e


def _hit(C, e, hits):
    for _ in range(hits):
        C.deal_damage(e, C.player, 1, "attack")
    C.emit("enemy_attack_done", enemy=e, move=None)


def teardown_function(_):
    for k in ENV:
        os.environ.pop(k, None)


def test_no_fanji_no_damage():
    C, e = _setup()
    C.apply_power(e, "FK", 10)
    C.apply_power(C.player, "CL_FENLEIQI", 3)
    hp0 = e.hp
    _hit(C, e, 3)
    assert e.hp == hp0 and e.amt("FK") == 10


def test_per_attack_vs_per_hit():
    for mode, dmg, left in (("attack", 10, 9), ("hit", 10 + 9 + 8, 7)):
        C, e = _setup(f"{mode}-2-L")
        C.apply_power(e, "FK", 10)
        C.apply_power(C.player, "CL_FANJI", 1)
        C.data["fk_cleared"] = 0
        hp0 = e.hp
        _hit(C, e, 3)
        assert hp0 - e.hp == dmg, mode
        assert e.amt("FK") == left
        assert C.data.get("fk_cleared", 0) == 0


def test_formulas_and_enhancers():
    cases = [("attack-2-2L", "null", 12, 9), ("attack-2-H", "null", 5, 9), ("attack-2-1H", "null", 6, 9),
             ("attack-2-L", "flat", 13, 9), ("attack-2-L", "keep", 10, 10)]
    for fj, opt, dmg, left in cases:
        C, e = _setup(fj, opt)
        C.apply_power(e, "FK", 10)
        C.apply_power(C.player, "CL_FENLEIQI", 3)
        C.apply_power(C.player, "CL_FANJI", 1)
        hp0 = e.hp
        _hit(C, e, 1)
        assert (hp0 - e.hp, e.amt("FK")) == (dmg, left), (fj, opt)


def test_xiuzheng_and_cap_decay_stack():
    C, e = _setup("attack-2-L", "null")
    C.apply_power(e, "FK", 10)
    C.apply_power(C.player, "CL_FANJI", 1)
    C.apply_power(C.player, "CL_XIUZHENG", 50)
    hp0 = e.hp
    _hit(C, e, 1)
    assert hp0 - e.hp == 15
    C, e = _setup("attack-2-L", "stack")
    C.apply_power(C.player, "CL_FENLEIQI", 3)
    C.emit("turn_start", side="player", creature=C.player)
    assert C.player.amt("CL_FANJI") == 1
    C.emit("turn_start", side="player", creature=C.player)
    assert C.player.amt("CL_FANJI") == 1
    C2, _ = _setup("attack-2-L", "null")
    C2.apply_power(C2.player, "CL_FANJI", 2)
    C2.emit("turn_start", side="player", creature=C2.player)
    assert C2.player.amt("CL_FANJI") == 1
    C2.emit("turn_start", side="player", creature=C2.player)
    assert not C2.player.has("CL_FANJI")


def test_grant6_and_xz_rounding_and_look():
    from sts2sim.core import Card
    C, e = _setup("hit-2-1H", "flat")
    M = C.mod
    hooks = next(h for h in M.hook_modules if hasattr(h, "fanji_grants"))
    w = Card(M.find_card("你说得完全正确！")); s = Card(M.find_card("稍等，我再确认一下"))
    assert not hooks.fanji_grants(w) and not hooks.fanji_grants(s)
    os.environ["STS2SIM_GRANT"] = "6"
    try:
        assert hooks.fanji_grants(w) and hooks.fanji_grants(s)
    finally:
        os.environ.pop("STS2SIM_GRANT", None)
    C.apply_power(C.player, "CL_XIUZHENG_C", 50)
    assert hooks.xz_apply(C, 5) == 8          # 5 + ceil(2.5)
    C.player.powers.pop("CL_XIUZHENG_C")
    C.apply_power(C.player, "CL_XIUZHENG", 50)
    assert hooks.xz_apply(C, 5) == 7          # 5 + floor(2.5)
    os.environ["STS2SIM_FANJI_AI"] = "look"
    try:
        C.apply_power(e, "FK", 6)
        C.apply_power(C.player, "CL_FANJI", 2)
        assert hooks.fanji_look_value(C) >= 0
    finally:
        os.environ.pop("STS2SIM_FANJI_AI", None)


def test_flq_mult():
    C, e = _setup("hit-3-1H", "mult16")
    hooks = next(h for h in C.mod.hook_modules if hasattr(h, "flq_mult"))
    C.apply_power(C.player, "CL_FENLEIQI", 3)          # 未升级：1.5^n
    assert abs(hooks.flq_mult(C, 2) - 2.25) < 1e-9
    C.player.powers["CL_FENLEIQI"].data["copies"] = (False, False)
    assert abs(hooks.flq_mult(C, 2) - 3.5) < 1e-9     # 两张：1 + 2×1.25
    C.player.powers["CL_FENLEIQI"].data["copies"] = (True,)
    assert abs(hooks.flq_mult(C, 1) - 1.6) < 1e-9
    C.player.powers["CL_FENLEIQI"].data["copies"] = (False,)
    C.apply_power(e, "FK", 10)
    C.apply_power(C.player, "CL_FANJI", 3)
    hp0 = e.hp
    _hit(C, e, 1)
    assert hp0 - e.hp == int(6 * 3.375)                 # (1+10//2)×3.375 = 20
