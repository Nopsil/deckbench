"""Claude娘 v3.5（新引擎）：风控 / 反击 / 宪法（口袋版）的结算顺序。"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mods"))
pytest.importorskip("sts2sim.gen.game")


def test_fanji_order_and_formula():
    from claude_v35 import claude as CL
    CL.load()
    from sts2sim.rt.boot import game as G
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent
    out = {}

    class A(HeuristicAgent):
        done = False

        def combat_action(self, cs, player, acts):
            if not self.done:
                self.done = True
                for cid in ["DOUBLE_CHECK", "STICKER", "DISCLAIMER"]:
                    card = cs.CreateCard(G.ModelDb.Card(_g=(CL.CARD_CLASSES[cid],)), player)
                    G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)
            hand = {getattr(c, "_claude_id", c.Id.Entry): c for c in C.hand(player)}
            en = C.alive_enemies(cs)
            for cid in ["DOUBLE_CHECK", "STICKER", "DISCLAIMER"]:
                if cid in hand:
                    return ("play", hand[cid], en[0] if cid == "STICKER" else None)
            if cs.RoundNumber == 1:
                out["before"] = [(e.CurrentHp, CL.fk(e)) for e in en]
                return ("end",)
            out["after"] = [(e.CurrentHp, CL.fk(e)) for e in cs.Enemies]
            out["fanji"] = int(player.Creature.GetPower(_g=(CL.FanjiPower,)).Amount)
            raise RuntimeError("stop")

    # v0.111（XxHash64 种子 + MegaRandom）下种子与旧版不可比：C1 第一场 [0] 8HP 5 层被攻击 1 段；C3 第一场 [2] 9HP 2 层被攻击 1 段
    # 每段：宪法 +2、免责声明 +1（先挂层）→ 反伤 1+⌊层/2⌋ → 减 1 层
    R.play_run("Claude", 0, "C1", agent=A())
    assert out["before"][0] == (8, 5) and out["after"][0] == (3, 7)
    assert out["fanji"] == 1      # 两次获得 → 2 层，回合开始 -1
    out.clear()
    R.play_run("Claude", 0, "C3", agent=A())
    assert out["before"][2] == (9, 2) and out["after"][2] == (6, 4)
    assert out["fanji"] == 1      # 两次获得 → 2 层，回合开始 -1


def test_v351_starter_values():
    """v3.5.1 默认值：已核实 每层+3 最多+16（升级 +4/+20），小本本 5 伤（升级 7），初始生命 80；v35_orig 保留 v3.5 原值。"""
    from claude_v35.cards_v35 import CARDS, VARIANTS, STARTING_HP
    v, n = CARDS["VERIFIED"], CARDS["NOTEBOOK"]
    assert v["cost"] == 1 and v["vars"] == {"Damage": 5, "Per": 3, "Cap": 16} and v["up"] == {"Damage": 2, "Per": 1, "Cap": 4}
    assert n["cost"] == 0 and n["vars"] == {"Damage": 5, "FK": 2} and n["up"] == {"Damage": 2, "FK": 1}
    assert STARTING_HP == 80
    o = VARIANTS["v35_orig"]
    assert o["_hp"] == 75 and o["NOTEBOOK"]["vars"] == {"Damage": 3} and o["VERIFIED"]["vars"] == {"Per": 2, "Cap": 8}


def test_v351_starter_in_combat():
    """整局里：初始生命 80；小本本 5 伤 + 2 层；已核实 6 层时 5+16=21 伤（8 层仍封顶 21），然后清层。"""
    from claude_v35 import claude as CL
    CL.load()
    from sts2sim.rt.boot import game as G
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent
    out = {}

    class A(HeuristicAgent):
        step = 0

        def combat_action(self, cs, player, acts):
            e = C.alive_enemies(cs)[0]
            pc = player.Creature
            if self.step == 0:
                out["hp"] = (pc.CurrentHp, pc.MaxHp)
                for cid in ["NOTEBOOK", "VERIFIED", "VERIFIED"]:
                    card = cs.CreateCard(G.ModelDb.Card(_g=(CL.CARD_CLASSES[cid],)), player)
                    G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)   # v0.111：第三参改为 creator
                e.SetMaxHpInternal(300)
                e.SetCurrentHpInternal(300)
                CL.set_fk(player, e, 0)
            hand = [c for c in C.hand(player)]
            pick = lambda cid: next(c for c in hand if getattr(c, "_claude_id", None) == cid)
            self.step += 1
            if self.step == 1:
                out["s0"] = (e.CurrentHp, CL.fk(e))
                return ("play", pick("NOTEBOOK"), e)
            if self.step == 2:
                out["s1"] = (e.CurrentHp, CL.fk(e))
                CL.set_fk(player, e, 6)
                return ("play", pick("VERIFIED"), e)
            if self.step == 3:
                out["s2"] = (e.CurrentHp, CL.fk(e))
                CL.set_fk(player, e, 8)
                return ("play", pick("VERIFIED"), e)
            out["s3"] = (e.CurrentHp, CL.fk(e))
            raise RuntimeError("stop")

    try:
        R.play_run("Claude", 0, "C3", agent=A())
    except Exception:
        pass
    assert out["hp"] == (80, 80), out
    assert out["s0"] == (300, 0)
    assert out["s1"] == (295, 2)            # 小本本：5 伤 + 2 层
    assert out["s2"] == (295 - 21, 0)       # 已核实 6 层：5 + min(18, 16)
    assert out["s3"] == (274 - 21, 0)       # 8 层仍封顶 +16


def test_opus_form_upgrade_name():
    """v3.5.1：「Opus 形态」升级后显示名为「Fable 形态」，id 与效果不变（2→3 力量）。"""
    from claude_v35 import claude as CL
    from claude_v35.cards_v35 import CARDS
    CL.load()
    from sts2sim.rt.boot import game as G
    sp = CARDS["OPUS_FORM"]
    assert sp["name"] == "Opus 形态" and sp["up_name"] == "Fable 形态"
    assert sp["cost"] == 3 and sp["vars"] == {"Amt": 2} and sp["up"] == {"Amt": 1}
    c = G.ModelDb.Card(_g=(CL.CARD_CLASSES["OPUS_FORM"],)).ToMutable()
    assert c.ClaudeName == "Opus 形态" and int(c.DynamicVars["Amt"].BaseValue) == 2
    c.UpgradeInternal()
    assert c.IsUpgraded and c.ClaudeName == "Fable 形态" and int(c.DynamicVars["Amt"].BaseValue) == 3
    s = G.ModelDb.Card(_g=(CL.CARD_CLASSES["CLAUDE_STRIKE"],)).ToMutable()
    s.UpgradeInternal()
    assert s.ClaudeName == "打击"            # 没有 up_name 的牌升级后名字不变


def test_code_block_v351():
    """v3.5.1：代码块（生成牌）0 费 3 伤 + 1 层风控、消耗；升级 6 伤 + 1 层。不进角色卡池。"""
    from claude_v35 import claude as CL
    from claude_v35.cards_v35 import CARDS
    CL.load()
    from sts2sim.rt.boot import game as G
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent
    sp = CARDS["CODE_BLOCK"]
    assert sp["name"] == "代码块" and sp["rarity"] == "Token" and sp["cost"] == 0 and "Exhaust" in sp["kw"]
    assert sp["vars"] == {"Damage": 3, "FK": 1} and sp["up"] == {"Damage": 3}
    out = {}

    class A(HeuristicAgent):
        step = 0

        def combat_action(self, cs, player, acts):
            e = C.alive_enemies(cs)[0]
            if self.step == 0:
                out["pool"] = [c.Id.Entry for c in player.Character.CardPool.AllCards]
                for up in (False, True):
                    card = cs.CreateCard(G.ModelDb.Card(_g=(CL.CARD_CLASSES["CODE_BLOCK"],)), player)
                    if up:
                        card.UpgradeInternal()
                    G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)
                e.SetMaxHpInternal(300)
                e.SetCurrentHpInternal(300)
                CL.set_fk(player, e, 0)
            cbs = [c for c in C.hand(player) if getattr(c, "_claude_id", None) == "CODE_BLOCK"]
            self.step += 1
            if self.step == 1:
                out["s0"] = (e.CurrentHp, CL.fk(e))
                return ("play", next(c for c in cbs if not c.IsUpgraded), e)
            if self.step == 2:
                out["s1"] = (e.CurrentHp, CL.fk(e))
                return ("play", next(c for c in cbs if c.IsUpgraded), e)
            out["s2"] = (e.CurrentHp, CL.fk(e))
            out["exhaust"] = sum(1 for c in player.PlayerCombatState.ExhaustPile.Cards if getattr(c, "_claude_id", None) == "CODE_BLOCK")
            raise RuntimeError("stop")

    try:
        R.play_run("Claude", 0, "C3", agent=A())
    except Exception as ex:
        out.setdefault("err", repr(ex))
    assert "s2" in out, out
    assert out["s0"] == (300, 0)
    assert out["s1"] == (297, 1)            # 3 伤 + 1 层
    assert out["s2"] == (291, 2)            # 升级：6 伤 + 1 层
    assert out["exhaust"] == 2
    assert not any("CODE_BLOCK" in x for x in out["pool"])
