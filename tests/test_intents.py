"""敌人意图：按反编译 C# 状态机（data/monster_ai.json）出招。给定种子的出招序列 + 规则性质检查。"""
import random
from helpers import combat
from sts2sim import enemies as EN


def setup(enc_id, seed=1):
    db = EN.load_db()
    enc = [e for e in db["encounters"] if e["id"] == enc_id][0]
    es = EN.build_encounter(enc, random.Random(seed))
    C = combat(enemies=es)
    C.rng = random.Random(seed)
    for e in es:
        e.state_log = []
        e.performed_first = False
        e.choose_intent(C, first=True)
    C.player.hp = C.player.max_hp = 9999
    return C, es


def step(C, block=0):
    C.player.block = block
    C.end_player_turn()
    C.enemy_phase()
    C.turn += 1


def seq(enc_id, n=8, seed=1, block=0):
    C, es = setup(enc_id, seed)
    out = [[] for _ in es]
    for _ in range(n):
        for i, e in enumerate(es):
            out[i].append(e.intent.id if e.intent is not None else None)
        step(C, block)
    return out


def test_all_act_monsters_have_code_ai():
    db = EN.load_db()
    used = {m["id"] for e in db["encounters"] if e.get("act") for m in e["monsters"]}
    srcs = {mid: db["monsters"][mid].ai_source for mid in used}
    assert sum(v == "代码" for v in srcs.values()) >= len(used) - 2


def test_cultists_fixed():
    a, b = seq("CULTISTS_NORMAL", 5)
    assert a == ["INCANTATION"] + ["DARK_STRIKE"] * 4 and b == a


def test_chompers_scream_first():
    a, b = seq("CHOMPERS_NORMAL", 4)
    assert a == ["CLAMP", "SCREECH", "CLAMP", "SCREECH"]
    assert b == ["SCREECH", "CLAMP", "SCREECH", "CLAMP"]


def test_chomper_screech_adds_three_dazed():
    C, es = setup("CHOMPERS_NORMAL")
    step(C)
    assert sum(c.base_name == "晕眩" for c in C.player.discard) == 3


def test_nibbits_front_back():
    a, b = seq("NIBBITS_NORMAL", 4)
    assert a == ["SLICE", "HISS", "BUTT", "SLICE"]
    assert b == ["HISS", "BUTT", "SLICE", "HISS"]
    (c,) = seq("NIBBITS_WEAK", 3)
    assert c == ["BUTT", "SLICE", "HISS"]


def test_scrolls_rotating_start():
    for seed in range(5):
        s = seq("SCROLLS_OF_BITING_NORMAL", 1, seed=seed)
        firsts = [x[0] for x in s]
        assert sorted(firsts[:3]) == ["CHEW", "CHOMP", "MORE_TEETH"] and firsts[3] == "MORE_TEETH"


def test_queen_branches_on_amalgam():
    C, es = setup("QUEEN_BOSS")
    q = [e for e in es if e.m.id == "QUEEN"][0]
    a = [e for e in es if e.m.id == "TORCH_HEAD_AMALGAM"][0]
    got = []
    for t in range(4):
        got.append(q.intent.id)
        step(C)
    assert got == ["PUPPET_STRINGS", "YOU_ARE_MINE", "BURN_BRIGHT_FOR_ME", "BURN_BRIGHT_FOR_ME"]   # v0.111 改名 YOU_ARE_MINE_MOVE
    assert a.amt("STRENGTH") == 2               # 燃烧吧：给火炬头 +1 力量（两次）
    a.hp = 0; a.alive = False
    got = []
    for t in range(4):
        step(C)
        got.append(q.intent.id)
    assert got == ["OFF_WITH_YOUR_HEAD", "EXECUTION", "ENRAGE", "OFF_WITH_YOUR_HEAD"]


def test_amalgam_cycle():
    a, _ = seq("QUEEN_BOSS", 8)     # 站位：火炬头聚合体在前、女王在后（QueenBoss.cs）
    assert a == ["STRONG_TACKLE_MOVE", "TACKLE_2", "BEAM", "TACKLE_3", "TACKLE_4", "BEAM", "TACKLE_3", "TACKLE_4"]  # v0.111：首招 STRONG_TACKLE 26


def test_axebot_repeat_rules():
    """旧版 RAND_MOVE 规则；v0.111 已改为固定交替，仍应满足（不连续 3 次、无 SHARPEN 连续）。"""
    for seed in range(20):
        s = seq("AXEBOTS_NORMAL", 30, seed=seed)[0]
        for i in range(2, len(s)):
            assert not (s[i] == s[i - 1] == s[i - 2] and s[i] in ("ONE_TWO", "HAMMER_UPPERCUT")), s
        for i in range(1, len(s)):
            assert not (s[i] == s[i - 1] == "SHARPEN_MOVE"), s


def test_axebot_seeded_sequence_regression():
    s = seq("AXEBOTS_NORMAL", 8, seed=7)[0]
    assert s == REGRESSION_AXEBOT_7


def test_lagavulin_sleep_and_wake_on_damage():
    C, (lg,) = setup("LAGAVULIN_MATRIARCH_BOSS")
    assert lg.intent.id == "SLEEP" and C.predict_intent_damage(lg) == 0
    step(C)
    assert lg.intent.id == "SLEEP"
    C.deal_damage(C.player, lg, 30, "attack")   # 打破格挡/覆甲后有未格挡伤害 → 苏醒并被击晕
    lg.block = 0
    C.deal_damage(C.player, lg, 30, "attack")
    assert not lg.has("ASLEEP")
    step(C)                                      # 被击晕：这一回合不行动
    assert lg.intent.id == "SLASH"


def test_bowlbug_rock_off_balance():
    C, es = setup("SLUMBERING_BEETLE_NORMAL")
    rock = [e for e in es if e.m.id == "BOWLBUG_ROCK"][0]
    assert rock.intent.id == "HEADBUTT"
    step(C, block=999)                           # 头槌被完全格挡 → 失衡 → 下一招 DIZZY
    assert rock.intent.id == "DIZZY"
    step(C, block=999)
    assert rock.intent.id == "HEADBUTT"


def test_frog_knight_half_health_once():
    C, (fk,) = setup("FROG_KNIGHT_NORMAL")
    s = []
    for _ in range(3):
        s.append(fk.intent.id)
        step(C)
    assert s == ["TONGUE_LASH", "STRIKE_DOWN_EVIL", "FOR_THE_QUEEN"]
    assert fk.intent.id == "TONGUE_LASH"         # 满血：不冲锋
    fk.hp = fk.max_hp // 2 - 1
    for _ in range(3):
        step(C)
    assert fk.intent.id == "BEETLE_CHARGE"
    step(C)
    assert fk.intent.id == "TONGUE_LASH"
    for _ in range(3):
        step(C)
    assert fk.intent.id == "TONGUE_LASH"         # 只冲锋一次


def test_ai_reads_intent_damage():
    C, (a, q) = setup("QUEEN_BOSS")
    assert C.predict_intent_damage(a) == 26     # v0.111 StrongTackle 26（旧 Tackle1 18）
    C.apply_power(a, "STRENGTH", 2)
    assert C.predict_intent_damage(a) == 28
    C.apply_power(C.player, "VULNERABLE", 1, source=("enemy", a))
    assert C.predict_intent_damage(a) == 42


def test_mecha_knight_burns_to_hand():
    C, (mk,) = setup("MECHA_KNIGHT_ELITE")
    for _ in range(8):
        if mk.intent.status:
            n0 = sum(c.base_name == "灼伤" for c in C.player.hand)
            C.player.hand = []
            C.enemy_phase()
            assert sum(c.base_name == "灼伤" for c in C.player.hand) == 4
            break
        step(C)
    else:
        raise AssertionError("8 回合内没有塞灼伤")


REGRESSION_AXEBOT_7 = ['HAMMER_UPPERCUT', 'ONE_TWO'] * 4   # v0.111：Axebot 不再随机，开场 HAMMER_UPPERCUT 后与 ONE_TWO 交替（SHARPEN 已删）


def test_ritual_skips_first_turn_end():
    """RitualPower.cs：敌人自己施加仪式的那个回合不加力量，下回合起每回合 +N。"""
    from tests.helpers import combat
    C = combat()
    e = C.enemies[0]
    C.apply_power(e, "RITUAL", 2, source=("enemy", e))
    C.emit("turn_end", side="enemy", creature=e)
    assert e.amt("STRENGTH") == 0
    C.emit("turn_end", side="enemy", creature=e)
    assert e.amt("STRENGTH") == 2
