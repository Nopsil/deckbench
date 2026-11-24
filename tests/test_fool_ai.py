"""愚者出牌顺序：不依赖本机游戏缓存。"""
from sts2sim.engine import fool_ai as F


class _Tag:
    def __init__(self, name):
        self.name = name


class _Card:
    def __init__(self, shoot=False, kind="Attack", aim=0.0, damage=0.0, mult=0.0, cost=1, x=False):
        self.Tags = [_Tag("Shoot")] if shoot else []
        self.Type = _Tag(kind)
        self.AimPower = aim
        self.Damage = damage
        self.AimMultiplier = mult
        self.cost = cost
        self.x = x
        self.Id = type("I", (), {"Entry": "X"})()


class _Power:
    def __init__(self, entry, amount):
        self.Id = type("I", (), {"Entry": entry})()
        self.Amount = amount


class _Enemy:
    def __init__(self, slip):
        self.IsAlive = True
        self.Powers = [_Power("SLIPPERY_POWER", slip)] if slip else []


class _State:
    def __init__(self, hand, energy=3):
        self.Hand = type("H", (), {"Cards": hand})()
        self.Energy = energy


def _player(hand, aim=0, energy=3):
    powers = [_Power("AIM_POWER", aim)] if aim else []
    return type("P", (), {
        "PlayerCombatState": _State(hand, energy),
        "Creature": type("C", (), {"Powers": powers})(),
        "Character": type("Ch", (), {"_cs_name": "Fool"})(),
    })()


def _cs(slip):
    return type("S", (), {"Enemies": [_Enemy(slip)]})()


def test_is_fool_only_for_that_character():
    assert F.is_fool(_player([]))
    other = _player([])
    other.Character = type("Ch", (), {"_cs_name": "Ironclad"})()
    assert not F.is_fool(other)
    assert not F.is_fool(None)


def test_hold_aimed_shot_while_slippery_if_another_attack_exists(monkeypatch):
    monkeypatch.setattr(F, "dvar", lambda c, key: getattr(c, key, 0.0))
    shot = _Card(shoot=True)
    strike = _Card(shoot=False)
    player = _player([shot, strike], aim=6)
    assert F.defer_aimed_shot(shot, player, _cs(8))
    assert not F.defer_aimed_shot(shot, player, _cs(0))
    assert not F.defer_aimed_shot(shot, _player([shot], aim=6), _cs(8))


def test_heavy_shot_is_preferred_once_slippery_is_gone(monkeypatch):
    monkeypatch.setattr(F, "arrows_available", lambda _p: 1)
    monkeypatch.setattr(F, "card_cost", lambda c: c.cost)
    monkeypatch.setattr(F, "costs_x", lambda c: c.x)
    monkeypatch.setattr(F, "dvar", lambda c, key: getattr(c, key, 0.0))
    light = _Card(shoot=True, damage=15, mult=1, cost=1)
    heavy = _Card(shoot=True, damage=20, mult=2, cost=2)
    player = _player([light, heavy], aim=6, energy=3)
    chosen = F.prefer_aimed_shot(("play", light, None), [("play", light, None), ("play", heavy, None)], player, _cs(0))
    assert chosen[1] is heavy
    assert F.prefer_aimed_shot(("play", light, None), [("play", light, None), ("play", heavy, None)], player, _cs(4)) is None


def test_nock_before_shot_when_energy_remains(monkeypatch):
    monkeypatch.setattr(F, "arrows_available", lambda _p: 1)
    monkeypatch.setattr(F, "card_cost", lambda c: c.cost)
    monkeypatch.setattr(F, "costs_x", lambda c: c.x)
    monkeypatch.setattr(F, "immediate_aim", lambda c: c.AimPower)

    class _Play:
        def __init__(self, card):
            self.card = card

        def OnPlay(self):
            return None

    nock = _Card(kind="Skill", aim=5, cost=0)
    shot = _Card(shoot=True, damage=15, cost=1)
    # immediate_aim is patched, so the real source scan is not used
    player = _player([nock, shot], aim=6, energy=3)
    chosen = F.aim_before_shot(("play", shot, None), [("play", nock, None), ("play", shot, None)], player)
    assert chosen[1] is nock
    brace = _Card(kind="Skill", aim=8, cost=0, x=True)
    assert F.aim_before_shot(("play", shot, None), [("play", brace, None), ("play", shot, None)], player) is None
