"""v0.113.1 缓存上的回归：假商人库存、事件战、愚者瞄准。没有缓存就跳过。"""
import pytest

pytest.importorskip("sts2sim.gen.game")

from sts2sim.engine import combat as Combat
from sts2sim.engine.agents import Agent
from sts2sim.engine.run import RunDriver, RunOver
from sts2sim.rt.boot import game as G


def _fool(seed):
    driver = RunDriver("Fool", 0, seed, agent=Agent())
    real = driver.on_room_entered

    def on_room(room):
        if isinstance(room, G.EventRoom):
            return None
        return real(room)

    driver.on_room_entered = on_room
    driver._create()
    driver.mgr.EnterAct(0)
    return driver


def _event(driver, entry):
    model = next(event for event in G._iter(G.ModelDb.AllEvents) if event.Id.Entry == entry)
    driver.mgr.EnterRoom(driver.mgr.CreateRoom(G.RoomType.Event, model=model))
    return driver.mgr.EventSynchronizer


def test_fake_merchant_stocks_six_relics():
    driver = _fool("FAKEAUDIT")
    sync = _event(driver, "FAKE_MERCHANT")
    inventory = driver.mgr.MerchantSynchronizer.GetInventoryFor(driver.player)
    stocked = [entry for entry in inventory.RelicEntries if entry.IsStocked]
    assert len(stocked) == 6
    assert sync.GetLocalEvent().IsFinished


def test_battleworn_setting_enters_its_encounter():
    driver = _fool("BWAUDIT")
    sync = _event(driver, "BATTLEWORN_DUMMY")
    sync.ChooseLocalOption(0)
    assert sync.GetLocalEvent().IsFinished
    assert driver.result.combats
    assert driver.result.combats[0][2] == "BATTLEWORN_DUMMY_EVENT_V1_ENCOUNTER"
    assert driver.result.combats[0][5] is True


def test_foolish_shot_adds_starting_aim():
    driver = _fool("AIMOUDIT")
    driver.on_room_entered = lambda room: None
    encounter = next(item for item in G._iter(G.ModelDb.AllEncounters) if item.Id.Entry == "SLIMES_WEAK")
    room = driver.mgr.CreateRoom(G.RoomType.Monster, model=encounter.ToMutable())
    driver.mgr.EnterRoom(room)
    enemy = Combat.alive_enemies(room.CombatState)[0]
    enemy.CurrentHp = 80
    aim = next(power for power in driver.player.Creature.Powers if type(power).__name__ == "AimPower")
    assert float(aim.Amount) == 6
    shot = next(card for card in G._iter(G.ModelDb.CardPool(_g=(G.FoolCardPool,)).AllCards) if card.Id.Entry == "FOOLISH_SHOT")
    mutable = room.CombatState.CreateCard(shot, driver.player)
    G.CardPileCmd.Add(mutable, G.PileType.Hand)
    driver.player.PlayerCombatState.Energy = 9
    action = next(item for item in Combat.legal_actions(room.CombatState, driver.player, include_potions=False)
                  if item[0] == "play" and item[1] is mutable and item[2] is enemy)
    Combat.execute(action, room.CombatState, driver.player)
    assert int(enemy.CurrentHp) == 80 - 21


def test_dense_vegetation_fight_starts_combat():
    driver = _fool("DENAUDIT")
    sync = _event(driver, "DENSE_VEGETATION")
    try:
        sync.ChooseLocalOption(1)
        sync.ChooseLocalOption(0)
    except RunOver:
        pass
    assert any(row[2] == "DENSE_VEGETATION_EVENT_ENCOUNTER" for row in driver.result.combats)
