"""Claude娘 v3.4：关键卡与风控事件契约。"""
import json
import os
import pytest
from helpers import combat, enemy, play, fk, give, mods

HERE = os.path.dirname(__file__)


# ---------------- 契约
def test_rlhf_modifies_amount_not_recursive():
    C = combat(hand=["RLHF 加训", "小本本记下了", "连锁审查"], enemies=[enemy(), enemy()], energy=5)
    play(C, "RLHF 加训")
    play(C, "小本本记下了")
    assert fk(C, 0) == 3
    play(C, "连锁审查")                       # 群体给予：每个目标各 +1
    assert fk(C, 0) == 5 and fk(C, 1) == 2


def test_artifact_blocks_give_and_no_audit_draw():
    C = combat(hand=["审计日志", "小本本记下了"], draw=["打击"] * 3, enemies=[enemy(powers={"ARTIFACT": 1})])
    play(C, "审计日志")
    n = len(C.player.hand)
    play(C, "小本本记下了")
    assert fk(C) == 0 and C.enemies[0].amt("ARTIFACT") == 0
    assert len(C.player.hand) == n - 1          # 被拦截：没有抽牌


def test_audit_once_per_turn_and_only_active():
    C = combat(hand=["审计日志", "小本本记下了", "贴小贴纸"], draw=["打击"] * 5)
    play(C, "审计日志")
    give(C, 0, 2, source=("relic", None))       # 遗物给予：被动，不抽
    assert len(C.player.hand) == 2
    play(C, "小本本记下了")
    assert len(C.player.hand) == 2              # -1 打出 +1 抽
    play(C, "贴小贴纸")
    assert len(C.player.hand) == 1              # 每回合只第一次：打出后不再抽


def test_passive_give_gets_rlhf():
    C = combat(hand=["RLHF 加训"])
    play(C, "RLHF 加训")
    give(C, 0, 2, source=("relic", None))
    assert fk(C) == 3


def test_lianzuo_secondary_spread_triggers_nothing():
    C = combat(hand=["一人违规全员连坐", "RLHF 加训", "小本本记下了", "审计日志"], draw=["打击"] * 5,
               enemies=[enemy(), enemy(), enemy()], energy=6)
    play(C, "一人违规全员连坐")
    play(C, "RLHF 加训")
    play(C, "审计日志")
    h = len(C.player.hand)
    play(C, "小本本记下了")
    assert fk(C, 0) == 3 and fk(C, 1) == 1 and fk(C, 2) == 1   # 次级施加不吃 RLHF
    assert len(C.player.hand) == h - 1 + 1                      # 审计日志只抽 1（主给予）


def test_lianzuo_single_enemy_bonus_first_give_only():
    C = combat(hand=["一人违规全员连坐", "小本本记下了", "贴小贴纸"])
    play(C, "一人违规全员连坐")
    play(C, "小本本记下了")
    play(C, "贴小贴纸")
    assert fk(C) == 3 + 3


def test_qingli_refund_only_when_paid():
    C = combat(hand=["清理指标", "快速复审", "红色按钮"], draw=["打击"] * 5, energy=3)
    play(C, "清理指标")
    assert C.player.energy == 2
    play(C, "快速复审")                          # 付 1，清除 → +1 能量、抽 1
    assert C.player.energy == 2
    give(C, 0, 3)
    play(C, "红色按钮")                          # 0 费清除：只抽不返
    assert C.player.energy == 2


def test_qingli_mass_ban_one_refund_draw_per_target():
    es = [enemy(hp=200) for _ in range(4)]
    C = combat(hand=["清理指标", "大规模封号"], draw=["打击"] * 8, enemies=es, energy=5)
    play(C, "清理指标")
    for i in range(4):
        give(C, i, 5)
    play(C, "大规模封号")
    assert C.player.energy == 5 - 1 - 3 + 1
    assert len(C.player.hand) == 4
    assert all(e.hp == 200 - 15 for e in C.enemies)


def test_credit_refund_once_per_turn():
    C = combat(hand=["扣信用分", "扣信用分", "扣信用分"], energy=3)
    give(C, 0, 6)
    play(C, "扣信用分")
    assert C.player.energy == 3
    play(C, "扣信用分")
    assert C.player.energy == 2
    C2 = combat(hand=["扣信用分"], energy=1)
    give(C2, 0, 1)
    play(C2, "扣信用分")
    assert C2.player.energy == 0                  # 只清 1 层：不返


def test_immediate_draw_first_play_only():
    C = combat(hand=["立即处理", "Ctrl+Z"], draw=["打击"] * 5)
    give(C, 0, 10)
    play(C, "立即处理")
    assert len(C.player.hand) == 2
    play(C, "Ctrl+Z")
    assert any(c.base_name == "立即处理" for c in C.player.hand)
    n = len(C.player.hand)
    play(C, "立即处理")
    assert len(C.player.hand) == n - 1            # 本回合第二次打出：不抽


# ---------------- 关键卡数值与封顶
@pytest.mark.parametrize("stacks,expect", [(0, 5), (3, 11), (4, 13), (9, 13)])
def test_yiheshi(stacks, expect):
    C = combat(hand=["已核实"])
    give(C, 0, stacks) if stacks else None
    play(C, "已核实")
    assert C.enemies[0].hp == 100 - expect and fk(C) == 0


def test_yongjiu_cap25():
    C = combat(hand=["永久封禁"], enemies=[enemy(hp=300)])
    give(C, 0, 30)
    play(C, "永久封禁")
    assert C.enemies[0].hp == 200 and fk(C) == 0


def test_zhenggai_and_zhengju_caps():
    C = combat(hand=["合规整改", "证据确凿"])
    give(C, 0, 12)
    play(C, "合规整改")
    assert fk(C) == 22
    play(C, "证据确凿")
    assert fk(C) == 42


def test_route_c_100():
    C = combat(hand=["合规整改", "证据确凿", "永久封禁"], enemies=[enemy(hp=300)], energy=4)
    give(C, 0, 5)
    play(C, "合规整改"); play(C, "证据确凿"); play(C, "永久封禁")
    assert C.enemies[0].hp == 200


def test_zhongshen():
    C = combat(hand=["终审判决", "终审判决"], energy=4)
    give(C, 0, 12)
    play(C, "终审判决")
    assert C.enemies[0].hp == 76 and fk(C) == 7
    play(C, "终审判决")
    assert C.enemies[0].hp == 64


def test_tongbao_per_enemy():
    C = combat(hand=["全网通报"], enemies=[enemy(), enemy()])
    give(C, 0, 20); give(C, 1, 3)
    play(C, "全网通报")
    assert C.enemies[0].hp == 100 - 21 and C.enemies[1].hp == 100 - 9 and fk(C, 0) == 20


def test_shuaiguo_artifact_on_recipient():
    C = combat(hand=["甩锅"], enemies=[enemy(), enemy(powers={"ARTIFACT": 1})])
    give(C, 0, 5)
    play(C, "甩锅", target=0)
    assert fk(C, 0) == 0 and fk(C, 1) == 2 and C.enemies[1].amt("ARTIFACT") == 0


def test_liandai_copy_is_not_give():
    C = combat(hand=["审计日志", "连带责任"], draw=["打击"] * 3, enemies=[enemy(), enemy()])
    play(C, "审计日志")
    give(C, 0, 6, source=("relic", None))
    h = len(C.player.hand)
    play(C, "连带责任", target=0)
    assert fk(C, 1) == 6 and len(C.player.hand) == h - 1


def test_liandai_single_enemy():
    C = combat(hand=["连带责任"])
    play(C, "连带责任")
    assert fk(C) == 4


def test_zhengdun_level():
    C = combat(hand=["全站整顿"], enemies=[enemy(), enemy(), enemy(powers={"ARTIFACT": 1})])
    give(C, 0, 9)
    play(C, "全站整顿")
    assert fk(C, 1) == 9 and fk(C, 2) == 0 and C.enemies[0].hp == 92


def test_lianzuozhi_death_transfer():
    C = combat(hand=["风控连坐制", "打击"], enemies=[enemy(hp=5), enemy()], energy=3)
    play(C, "风控连坐制")
    assert fk(C, 0) == 3 and fk(C, 1) == 3
    play(C, "打击", target=0)
    assert not C.enemies[0].alive and fk(C, 1) == 6


def test_jinmen_replay_and_single_refund():
    C = combat(hand=["清理指标", "金门大桥 Claude", "快速复审"], draw=["打击"] * 5, energy=5)
    play(C, "清理指标"); play(C, "金门大桥 Claude")
    e0 = C.player.energy
    play(C, "快速复审")
    assert C.enemies[0].hp == 92                 # 4 × 2
    assert C.player.energy == e0 - 1 + 1         # 两次清除只返 1


def test_constitution_relic():
    C = combat(relics=["CONSTITUTION"], enemies=[enemy(dmg=3, hits=3), enemy(dmg=0)])
    C.turn = 0
    C.start_player_turn()
    assert fk(C, 0) == 2 and fk(C, 1) == 2
    C.player.block = 100
    C.end_player_turn(); C.enemy_phase()
    assert fk(C, 0) == 4 and fk(C, 1) == 2       # 完全格挡也触发、多段只 1 次、不攻击不触发


def test_deep_thinking():
    C = combat(hand=["打击", "深度思考"], energy=3)
    play(C, "打击")
    assert not C.can_play(C.player.hand[0])
    C2 = combat(hand=["深度思考", "打击"])
    play(C2, "深度思考")
    assert C2.data.get("_force_end_turn") and C2.player.amt("NEXT_ENERGY") == 3 and C2.player.block == 10


def test_changpian_hits_hand_size():
    C = combat(hand=["长篇大论", "防御", "防御", "防御"])
    play(C, "长篇大论")
    assert C.enemies[0].hp == 94


def test_qiangzhi_cost():
    C = combat(hand=["强制下线"])
    assert C.card_cost(C.player.hand[0]) == 3
    C.data["fk_cleared"] = 25
    assert C.card_cost(C.player.hand[0]) == 1


def test_wanquan_zhengque():
    C = combat(hand=["你说得完全正确！", "你说得完全正确！"], draw=["打击"] * 3, enemies=[enemy(dmg=8, hits=2), enemy(dmg=0)])
    play(C, "你说得完全正确！", target=0)
    assert C.player.block == 12
    play(C, "你说得完全正确！", target=1)
    assert len(C.player.hand) == 2


def test_please_retry_unplayable_and_million_context():
    C = combat(hand=["请稍后再试", "打击"], relics=["MILLION_CONTEXT"])
    assert not C.can_play(C.player.hand[0])
    C.data["_keep_hand"] = True
    C.end_player_turn()
    assert [c.base_name for c in C.player.hand] == ["打击"]


def test_every_card_plays_without_error():
    """冒烟：每张 Claude 卡（含升级版）在有风控、多敌人的局面下都能打出。"""
    M = mods()
    ids = [d for d in M.cards.values() if d.mod == "claude_v34" and d.cost is not None]
    for d in ids:
        for up in (False, True):
            C = combat(hand=[d.name, "防御", "打击", "代码块"], draw=["打击"] * 5, discard=None if False else (),
                       enemies=[enemy(), enemy()], energy=5, upgraded=(d.name,) if up else ())
            C.player.discard = [C.make_card("STRIKE")]
            give(C, 0, 12); give(C, 1, 3)
            card = C.player.hand[0]
            assert C.can_play(card), d.name
            play(C, d.name)


def test_design_snapshot_matches():
    snap = json.load(open(os.path.join(HERE, "fixtures", "claude_v34_design.json"), encoding="utf-8"))
    M = mods()
    for x in snap["cards"]:
        if x["name"] in ("打击", "防御"):
            d = M.find_card(x["name"])
            assert d.mod == "vanilla"
            continue
        d = M.find_card(x["name"])
        assert d.type == x["type"] and d.rarity == x["rarity"] and d.cost == x["cost"], x["name"]
    assert snap["n_rows"] == 90
    pool = [d for d in M.cards.values() if d.mod == "claude_v34" and d.pool]
    assert len(pool) == 80
    from collections import Counter
    assert Counter(d.rarity for d in pool) == {"普通": 20, "罕见": 35, "稀有": 25}
