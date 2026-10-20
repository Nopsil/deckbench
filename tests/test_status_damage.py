"""手牌里回合结束伤害的状态牌（异蛙寄生虫的 感染 Infection 等）：引擎结算 + AI 把它算进需要的格挡。"""
import pytest

pytest.importorskip("sts2sim.gen.game")


def test_infection_end_turn_damage_and_ai_need():
    from sts2sim.rt.boot import game as G
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent, end_turn_hand_damage
    out = {}

    class A(HeuristicAgent):
        step = 0

        def combat_action(self, cs, player, acts):
            pc = player.Creature
            if self.step == 0:
                self.step = 1
                for _ in range(2):
                    card = cs.CreateCard(G.ModelDb.Card(_g=(G.Infection,)), player)
                    G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)
                out["etd"] = end_turn_hand_damage(player)
                # 不出牌直接结束回合：掉血 = 敌人攻击 + 2×3（感染可被格挡，这里格挡为 0）
                out["hp0"], out["inc"], out["blk"] = pc.CurrentHp, C_inc(cs, player), pc.Block
                out["r0"] = cs.RoundNumber
                return ("end",)
            if "hp1" not in out and cs.RoundNumber == out["r0"] + 1:
                out["hp1"] = pc.CurrentHp
                raise RuntimeError("stop")
            return ("end",)

    def C_inc(cs, player):
        from sts2sim.engine.agents import incoming_damage
        return incoming_damage(cs, player)

    R.play_run("Ironclad", 0, "T1", agent=A())
    assert out["etd"] == 6
    assert out["hp0"] - out["hp1"] == max(0, out["inc"] - out["blk"]) + 6


def test_end_turn_damage_counts_only_blockable_status_curse():
    from sts2sim.rt.boot import game as G
    from sts2sim.engine.agents import dvar
    for cls, dmg in [(G.Infection, 3), (G.Burn, 2), (G.Decay, 2)]:
        c = G.ModelDb.Card(_g=(cls,))
        assert c.HasTurnEndInHandEffect and dvar(c, "Damage") == dmg
    # Regret / BadLuck 是 Unblockable 的 HpLoss（不带 Damage 变量），不计入格挡需求
    assert dvar(G.ModelDb.Card(_g=(G.BadLuck,)), "Damage") == 0
