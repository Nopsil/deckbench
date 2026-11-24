"""对照 v0.113.1 生成代码里的固定数值。没有缓存就跳过。

这些断言来自这份 DLL 转译出来的模型（伤害变量、遗物变量、远古进房治疗），
不是真机客户端的逐条录像。
"""
import pytest

pytest.importorskip("sts2sim.gen.game")

from sts2sim.engine import combat as Combat
from sts2sim.engine.agents import Agent
from sts2sim.engine.run import RunDriver
from sts2sim.rt.boot import game as G


def _fight():
    driver = RunDriver("Fool", 0, "NUMLOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    encounter = next(item for item in G._iter(G.ModelDb.AllEncounters) if item.Id.Entry == "SLIMES_WEAK")
    room = driver.mgr.CreateRoom(G.RoomType.Monster, model=encounter.ToMutable())
    driver.mgr.EnterRoom(room)
    driver.player.PlayerCombatState.Energy = 9
    enemy = Combat.alive_enemies(room.CombatState)[0]
    enemy.MaxHp = 200
    enemy.CurrentHp = 200
    return driver, room, enemy


def _card(name):
    return next(card for card in G._iter(G.ModelDb.CardPool(_g=(G.FoolCardPool,)).AllCards) if card.Id.Entry == name)


def _give(room, player, name):
    card = room.CombatState.CreateCard(_card(name), player)
    G.CardPileCmd.Add(card, G.PileType.Hand)
    return card


def _play(driver, room, card, enemy):
    action = next(item for item in Combat.legal_actions(room.CombatState, driver.player, include_potions=False)
                  if item[0] == "play" and item[1] is card and (item[2] is enemy or item[2] is None))
    before = int(enemy.CurrentHp)
    block = int(driver.player.Creature.Block)
    Combat.execute(action, room.CombatState, driver.player)
    return before - int(enemy.CurrentHp), int(driver.player.Creature.Block) - block


def _aim(player):
    powers = [power for power in player.Creature.Powers if type(power).__name__ == "AimPower"]
    return 0 if not powers else float(powers[0].Amount)


def _impale(enemy):
    powers = [power for power in enemy.Powers if type(power).__name__ == "ImpaledPower"]
    if not powers:
        return None
    power = powers[0]
    return int(power.HitCounter), len(list(power.Arrows))


def test_foolish_shot_spends_all_aim_and_one_arrow():
    driver, room, enemy = _fight()
    assert _aim(driver.player) == 6
    assert driver.player.PlayerCombatState.AvailableArrowCount == 1
    dealt, _ = _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    # 依据：DamageVar 15，FromArrow；AimPower 把当前层数加到每一击，攻击结束后一次扣光。
    assert dealt == 21
    assert _aim(driver.player) == 0
    assert driver.player.PlayerCombatState.AvailableArrowCount == 0
    assert _impale(enemy) == (3, 1)


def test_shot_without_an_arrow_deals_no_damage():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    second = _give(room, driver.player, "FOOLISH_SHOT")
    dealt, _ = _play(driver, room, second, enemy)
    # 依据：ShootArrowAtTarget 在没有箭时不调用攻击。牌仍然能打出。
    assert dealt == 0
    assert _aim(driver.player) == 0


def test_quiver_adds_a_slot_and_the_second_shot_has_no_aim_left():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "QUIVER"), enemy)
    assert driver.player.PlayerCombatState.AvailableArrowCount == 2
    first, _ = _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    second, _ = _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    assert first == 21
    assert second == 15
    assert _aim(driver.player) == 0
    assert driver.player.PlayerCombatState.AvailableArrowCount == 0


def test_rapid_shot_adds_aim_to_each_of_three_hits_and_uses_one_arrow():
    driver, room, enemy = _fight()
    dealt, _ = _play(driver, room, _give(room, driver.player, "RAPID_SHOT"), enemy)
    # 依据：伤害 3，段数 3，整段攻击只射一支箭；瞄准在 AfterAttack 才扣除。
    assert dealt == 27
    assert _aim(driver.player) == 0
    assert driver.player.PlayerCombatState.AvailableArrowCount == 0
    assert _impale(enemy) == (3, 1)


def test_heavy_shot_doubles_aim_before_consuming_it():
    driver, room, enemy = _fight()
    dealt, _ = _play(driver, room, _give(room, driver.player, "HEAVY_SHOT"), enemy)
    # 依据：伤害 20，AimMultiplier 2。20 + 6*2。
    assert dealt == 32
    assert _aim(driver.player) == 0


def test_killing_the_target_returns_the_arrow():
    driver, room, enemy = _fight()
    enemy.CurrentHp = 10
    _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    assert enemy.IsDead
    assert driver.player.PlayerCombatState.AvailableArrowCount == 1
    assert _impale(enemy) is None


def test_three_powered_hits_dislodge_the_arrow():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "FOOLISH_SHOT"), enemy)
    seen = []
    for _ in range(3):
        dealt, _ = _play(driver, room, _give(room, driver.player, "STRIKE_FOOL"), enemy)
        seen.append((dealt, _impale(enemy), driver.player.PlayerCombatState.AvailableArrowCount))
    # 依据：ImpaledPower 的 HitCounter 从 3 开始，玩家的有力量攻击每段减 1，到 0 就把箭拔回。
    assert seen[0][0] == 6 and seen[0][1] == (2, 1) and seen[0][2] == 0
    assert seen[1][1] == (1, 1)
    assert seen[2][1] is None and seen[2][2] == 1


def test_wah_blast_hits_twice_after_cho_was_played():
    driver, room, enemy = _fight()
    plain, _ = _play(driver, room, _give(room, driver.player, "WAH_BLAST"), enemy)
    cho, block = _play(driver, room, _give(room, driver.player, "WAH_CHO"), enemy)
    twice, _ = _play(driver, room, _give(room, driver.player, "WAH_BLAST"), enemy)
    # 依据：WahBlast 伤害 14；本回合打过啾或叽则段数变 2。WahCho 伤害 3、格挡 3。
    assert plain == 14
    assert cho == 3 and block == 3
    assert twice == 28


def test_first_wah_and_cho_trigger_violent_chord_and_song_path_once():
    driver, room, enemy = _fight()
    G.PowerCmd.Apply(G.ThrowingPlayerChoiceContext(), driver.player.Creature, 5, driver.player.Creature, None, _g=(G.ViolentChordPower,))
    G.PowerCmd.Apply(G.ThrowingPlayerChoiceContext(), driver.player.Creature, 4, driver.player.Creature, None, _g=(G.SongPathPower,))
    first = _play(driver, room, _give(room, driver.player, "WAH_CHO"), enemy)
    second = _play(driver, room, _give(room, driver.player, "WAH_CHO"), enemy)
    # 依据：ViolentChord 只在本回合第一张哇牌后对敌人造成层数点无力量伤害；SongPath 只在第一张啾牌后给层数点格挡。
    assert first == (3 + 5, 3 + 4)
    assert second == (3, 3)


def test_wah_cho_ki_counts_as_all_three_melodies_and_lullaby_blocks():
    driver, room, enemy = _fight()
    G.PowerCmd.Apply(G.ThrowingPlayerChoiceContext(), driver.player.Creature, 7, driver.player.Creature, None, _g=(G.LullabyPower,))
    dealt, block = _play(driver, room, _give(room, driver.player, "WAH_CHO_KI"), enemy)
    # 依据：牌面伤害 9、格挡 9、抽 1。出牌记录先于 AfterCardPlayed，所以这一张同时满足哇啾叽，摇篮曲再给 7 点格挡。
    assert dealt == 9
    assert block == 9 + 7
    assert G.MelodyCmd.MelodiesThisTurn(driver.player) == 3


def test_brighten_up_makes_two_sadness_and_growth_clears_them_for_stretch():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "BRIGHTEN_UP"), enemy)
    hand = list(G.PileType.Hand.GetPile(driver.player).Cards)
    assert sum(1 for card in hand if card.Id.Entry == "SADNESS") == 2
    assert sum(1 for card in hand if card.Id.Entry == "JOY") == 2
    _play(driver, room, _give(room, driver.player, "GROWTH"), enemy)
    hand = list(G.PileType.Hand.GetPile(driver.player).Cards)
    assert not any(card.Id.Entry == "SADNESS" for card in hand)
    stretch = next(power for power in driver.player.Creature.Powers if type(power).__name__ == "StretchPower")
    # 依据：Growth 的额外值是 4，手牌里每张悲伤给 4 层伸展，然后把这些悲伤消耗掉。
    assert float(stretch.Amount) == 8


def test_ennui_adds_one_sadness_and_two_extra_draws():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "ENNUI"), enemy)
    power = next(item for item in driver.player.Creature.Powers if type(item).__name__ == "EnnuiPower")
    assert float(power.Amount) == 2
    assert float(power.DynamicVars.Cards.BaseValue) == 1
    Combat.execute(("end",), room.CombatState, driver.player)

    def sadness():
        piles = (G.PileType.Hand, G.PileType.Draw, G.PileType.Discard, G.PileType.Exhaust)
        return sum(1 for pile in piles for card in pile.GetPile(driver.player).Cards if card.Id.Entry == "SADNESS")

    hand = list(G.PileType.Hand.GetPile(driver.player).Cards)
    # 依据：Cards 变量决定生成几张悲伤（打出后 Increment 成 1）；层数加在抽牌数上（5+2）。
    assert sadness() == 1
    assert sum(1 for card in hand if card.Id.Entry == "SADNESS") == 1
    assert len(hand) == 8


def test_archery_adds_four_aim_at_the_next_player_turn():
    driver, room, enemy = _fight()
    _play(driver, room, _give(room, driver.player, "ARCHERY"), enemy)
    assert _aim(driver.player) == 6
    Combat.execute(("end",), room.CombatState, driver.player)
    # 依据：ArcheryPower 在自己这一侧回合开始时获得等于层数的瞄准。这一回合已经开始过了，所以是下一回合 +4。
    assert _aim(driver.player) == 10


def test_signet_ring_grants_888_gold_immediately():
    driver, _room, _enemy = _fight()
    before = int(driver.player.Gold)
    G.RelicCmd.Obtain(G.ModelDb.Relic(_g=(G.SignetRing,)).ToMutable(), driver.player)
    # 依据：SignetRing 的 GoldVar 是 888，AfterObtained 立刻 GainGold。
    assert int(driver.player.Gold) == before + 888


def test_dense_vegetation_trudge_matches_its_rolled_gold_and_hp_loss():
    driver = RunDriver("Fool", 0, "DENSELOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    event = next(item for item in G._iter(G.ModelDb.AllEvents) if item.Id.Entry == "DENSE_VEGETATION")
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=event))
    local = driver.mgr.EventSynchronizer.GetLocalEvent()
    hp_loss = int(local.DynamicVars.HpLoss.BaseValue)
    gold = int(local.DynamicVars.Gold.BaseValue)
    assert hp_loss == 8
    assert 61 <= gold <= 99
    before_hp = int(driver.player.Creature.CurrentHp)
    before_gold = int(driver.player.Gold)
    driver.mgr.EventSynchronizer.ChooseLocalOption(0)
    assert int(driver.player.Creature.CurrentHp) == before_hp - hp_loss
    assert int(driver.player.Gold) == before_gold + gold


def test_this_or_that_plain_loses_6_hp_and_gains_the_rolled_gold():
    driver = RunDriver("Fool", 0, "TOTLOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    event = next(item for item in G._iter(G.ModelDb.AllEvents) if item.Id.Entry == "THIS_OR_THAT")
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=event))
    local = driver.mgr.EventSynchronizer.GetLocalEvent()
    rolled = int(local.DynamicVars.Gold.IntValue)
    assert int(local.DynamicVars.HpLoss.IntValue) == 6
    assert 41 <= rolled <= 68
    before_hp = int(driver.player.Creature.CurrentHp)
    before_gold = int(driver.player.Gold)
    driver.mgr.EventSynchronizer.ChooseLocalOption(0)
    assert int(driver.player.Creature.CurrentHp) == before_hp - 6
    assert int(driver.player.Gold) == before_gold + rolled


def test_abyssal_baths_immerse_gains_2_max_hp_and_then_takes_3_damage():
    driver = RunDriver("Fool", 0, "BATHLOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    event = next(item for item in G._iter(G.ModelDb.AllEvents) if item.Id.Entry == "ABYSSAL_BATHS")
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=event))
    before_hp = int(driver.player.Creature.CurrentHp)
    before_max = int(driver.player.Creature.MaxHp)
    driver.mgr.EventSynchronizer.ChooseLocalOption(0)
    # 依据：GainMaxHp 会把增加的最大值也治疗上来，然后再受到伤害变量 3。
    assert int(driver.player.Creature.MaxHp) == before_max + 2
    assert int(driver.player.Creature.CurrentHp) == before_hp + 2 - 3


def test_ancient_event_heals_to_full_as_it_starts():
    driver = RunDriver("Fool", 0, "ANCIENTLOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    event = next(item for item in G._iter(G.ModelDb.AllAncients) if item.Id.Entry == "DARV")
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=event))
    local = driver.mgr.EventSynchronizer.GetLocalEvent()
    driver.player.Creature.CurrentHp = 6
    local.BeforeEventStarted(False)
    # 依据：AncientEventModel.BeforeEventStarted 治疗 (最大生命 - 当前生命)。Neow 会先把生命设成 0 再治疗。
    assert int(driver.player.Creature.CurrentHp) == int(driver.player.Creature.MaxHp)


def test_calling_bell_adds_one_curse_of_the_bell():
    driver = RunDriver("Fool", 0, "BELLLOCK", agent=Agent())
    driver.on_room_entered = lambda room: None
    driver._create()
    driver.mgr.EnterAct(0)
    before = [card.Id.Entry for card in driver.player.Deck.Cards]
    G.RelicCmd.Obtain(G.ModelDb.Relic(_g=(G.CallingBell,)).ToMutable(), driver.player)
    after = [card.Id.Entry for card in driver.player.Deck.Cards]
    added = [entry for entry in after if after.count(entry) > before.count(entry)]
    assert added == ["CURSE_OF_THE_BELL"]
    assert sum(1 for card in driver.player.Deck.Cards if card.Type == G.CardType.Curse) == 1


def test_fast_battleworn_win_grants_a_potion_and_does_not_repeat():
    class Kill(Agent):
        def combat_action(self, cs, player, acts):
            for enemy in list(cs.Enemies):
                if enemy.IsAlive:
                    G.CreatureCmd.Kill(G.Seq([enemy]))
            return ("end",)

    driver = RunDriver("Fool", 0, "BWLOCK", agent=Kill())
    driver._create()
    driver.mgr.EnterAct(0)
    event = next(item for item in G._iter(G.ModelDb.AllEvents) if item.Id.Entry == "BATTLEWORN_DUMMY")
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=event))
    potions = [potion.Id.Entry for potion in driver.player.Potions if potion]
    assert len(potions) == 1
    assert driver.mgr.EventSynchronizer.GetLocalEvent().IsFinished
    assert len(driver.result.combats) == 1
    assert driver.result.combats[0][2] == "BATTLEWORN_DUMMY_EVENT_V1_ENCOUNTER"
