"""固定种子的战斗样本，用来核对加速前后、以及不同进程数的结果。

不读游戏安装，也不用 mods/vanilla。卡组和怪物都是合成的，只走内部 Python 战斗引擎。
"""
import hashlib
import json
import multiprocessing as mp
import random
import sys

from .ai.beam import BeamAgent
from .ai.heuristic import HeuristicAgent
from .core import Card, Combat, Player
from .enemies import Enemy, MonsterDef
from .modloader import ModSet
from .relics import make_relic
from .runner import _seed


DECKS = {
    "start": ["小本本记下了", "小本本记下了", "已核实", "已核实", "计划模式", "轻轻敲一下", "你确定吗？", "继续"],
    "burst": ["小本本记下了", "已核实", "账号已停用", "贴小贴纸", "批量打标", "一键封号", "清退名单", "继续", "叠满再说", "合规整改"],
    "draw": ["小本本记下了", "已核实", "轻轻敲一下", "该对话已被记录", "流程优化", "你确定吗？", "继续", "审计日志", "例行巡检"],
}


def _monster(mid, name, hp, moves, innate=None):
    raw = {
        "id": mid, "name": name, "min_hp": hp, "max_hp": hp,
        "moves": moves,
        "innate_powers": [{"power_id": k, "amount": v} for k, v in (innate or {}).items()],
        "attack_pattern": {"type": "cycle"},
    }
    return MonsterDef(raw, name)


FOES = [
    _monster("BRUTE", "蛮兵", 48, [
        {"id": "HIT", "name": "重击", "intent": "Attack", "damage": {"normal": 9, "hit_count": 1}},
        {"id": "SLAM", "name": "连打", "intent": "Attack", "damage": {"normal": 4, "hit_count": 2}},
        {"id": "GUARD", "name": "格挡", "intent": "Defend", "block": 8},
    ], {"ARTIFACT": 1}),
    _monster("HEX", "术士", 36, [
        {"id": "WEAK", "name": "虚弱", "intent": "Debuff", "powers": [{"power_id": "WEAK", "target": "player", "amount": 2}]},
        {"id": "BOLT", "name": "飞弹", "intent": "Attack", "damage": {"normal": 7, "hit_count": 1}},
        {"id": "VULN", "name": "易伤", "intent": "Debuff", "powers": [{"power_id": "VULNERABLE", "target": "player", "amount": 1}]},
    ]),
    _monster("THORN", "荆棘", 40, [
        {"id": "STAB", "name": "刺", "intent": "Attack", "damage": {"normal": 6, "hit_count": 1},
         "powers": [{"power_id": "STRENGTH", "target": "self", "amount": 1}]},
        {"id": "SHELL", "name": "壳", "intent": "Defend", "block": 10},
        {"id": "DAZE", "name": "晕", "intent": "Status", "status": []},
    ], {"THORNS": 2}),
]


def build_player(M, deck_id, seed):
    ch = M.characters["claude"]
    P = Player(ch["name"], ch["hp"], ch["energy"], ch["hand"])
    rng = random.Random(_seed("deck", seed, deck_id))
    specs = list(DECKS[deck_id])
    up_n = 2 if deck_id != "start" else 1
    idxs = list(range(len(specs)))
    rng.shuffle(idxs)
    upgraded = set(idxs[:up_n])
    P.draw_pile = [Card(M.find_card(n), i in upgraded) for i, n in enumerate(specs)]
    relics = [make_relic("CONSTITUTION")]
    if deck_id == "burst":
        relics.append(make_relic("SONNET"))
    return P, relics


def make_enemies(rng):
    order = list(range(len(FOES)))
    rng.shuffle(order)
    n = 2 if rng.random() < 0.5 else 3
    return [Enemy(FOES[i], rng, slot=slot) for slot, i in enumerate(order[:n])]


def fight_once(M, deck_id, seed, idx, agent_name="heuristic", max_turns=12):
    Card._uid[0] = 0
    rng = random.Random(_seed(seed, deck_id, idx, agent_name))
    P, relics = build_player(M, deck_id, seed)
    enemies = make_enemies(rng)
    if agent_name == "beam":
        agent = BeamAgent(width=3, depth=2)
    else:
        agent = HeuristicAgent()
    C = Combat(P, enemies, M, rng=rng, agent=agent, max_turns=max_turns)
    C.relics = relics
    C.data["_room"] = "精英" if idx % 2 else "普通"
    C.data["cl_mod"] = True
    start_hp = P.hp
    enemy_hp0 = [e.hp for e in enemies]
    res = C.run()
    return {
        "deck": deck_id,
        "seed": seed,
        "idx": idx,
        "agent": agent_name,
        "result": res,
        "turns": C.turn,
        "hp_left": max(0, P.hp),
        "hp_lost": start_hp - max(0, P.hp) if res != "loss" else start_hp,
        "cards": {k: list(v) for k, v in (C.stats.card.items() if C.stats else [])},
        "loop": C.loop_alarm,
        "enemy_hp0": enemy_hp0,
        "enemy_hp": [e.hp if e.alive else 0 for e in enemies],
        "enemy_ids": [e.m.id for e in enemies],
        "powers": {e.m.id: {pid: p.amount for pid, p in e.powers.items()} for e in enemies},
        "player_powers": {pid: p.amount for pid, p in P.powers.items()},
        "energy": P.energy,
        "block": P.block,
    }


def canonical(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(rows):
    return hashlib.sha256(canonical(rows).encode()).hexdigest()


def specs(n_seeds, fights, agents):
    out = []
    for s in range(n_seeds):
        seed = 1000 + s * 17
        for deck in ("start", "burst", "draw"):
            for i in range(fights):
                for agent in agents:
                    out.append((deck, seed, i, agent))
    return out


_MOD = None


def _mod():
    global _MOD
    if _MOD is None:
        _MOD = ModSet(["claude_v34"])
    return _MOD


def _spec(spec):
    deck, seed, idx, agent = spec
    return fight_once(_mod(), deck, seed, idx, agent)


def workload(n_seeds=4, fights=2, agents=("heuristic",), workers=1):
    """按固定顺序打这些场。workers>1 时每场仍用自己的种子，结果顺序与串行相同。"""
    jobs = specs(n_seeds, fights, agents)
    workers = max(1, int(workers))
    if workers == 1:
        return [_spec(job) for job in jobs]
    ctx = mp.get_context("spawn" if sys.platform == "win32" else "fork")
    with ctx.Pool(workers) as pool:
        return pool.map(_spec, jobs, chunksize=1)
