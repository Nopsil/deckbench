import random
from sts2sim.modloader import ModSet
from sts2sim.core import Combat, Player, Card
from sts2sim.enemies import Enemy, MonsterDef
from sts2sim.relics import make_relic
from sts2sim.ai import HeuristicAgent

_M = {}


def mods():
    if "m" not in _M:
        _M["m"] = ModSet(["vanilla", "claude_v34"])
    return _M["m"]


def enemy(hp=100, dmg=10, hits=1, name="靶子", powers=None, block=0):
    raw = {"id": name, "name": name, "min_hp": hp, "max_hp": hp,
           "moves": [{"id": "HIT", "name": "打", "intent": "Attack" if dmg else "Buff",
                      **({"damage": {"normal": dmg, "hit_count": hits}} if dmg else {}), **({"block": block} if block else {})}],
           "innate_powers": [{"power_id": k, "amount": v} for k, v in (powers or {}).items()]}
    return Enemy(MonsterDef(raw, name), random.Random(0))


def combat(hand=(), draw=(), enemies=None, relics=(), energy=3, hp=75, start=True, upgraded=(), discard=()):
    M = mods()
    P = Player("测试", hp, 3)
    C = Combat(P, enemies or [enemy()], M, rng=random.Random(1), agent=HeuristicAgent())
    C.relics = [make_relic(r) for r in relics]
    for e in C.enemies:
        e.setup(C)
    C.emit("battle_start")
    C.turn = 1
    C.phase = "player"
    P.energy = energy
    P.hand = [Card(M.find_card(n), n in upgraded) for n in hand]
    P.draw_pile = [Card(M.find_card(n)) for n in draw]
    return C


def play(C, name, target=0, upgraded=None):
    for i, c in enumerate(C.player.hand):
        if c.base_name == name and (upgraded is None or c.upgraded == upgraded):
            t = C.enemies[target] if C.needs_target(c) else None
            return C.play(i, t)
    raise AssertionError(f"手里没有 {name}: {C.player.hand}")


def fk(C, i=0):
    return C.enemies[i].amt("FK")


def give(C, i, n, source=("card", None)):
    return C.apply_power(C.enemies[i], "FK", n, source=source)
