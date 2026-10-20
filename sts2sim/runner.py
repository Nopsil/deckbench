"""跑实验：python -m sts2sim.runner experiments/xxx.yaml [--fights N] [--jobs J] [--seed S] [--agent beam]

实验 YAML：
  name: claude_v34_first
  mods: [vanilla, claude_v34]
  seed: 20261020
  fights: 200              # 每个（卡组×房间）格子打多少场
  max_turns: 30
  agent: heuristic         # heuristic / beam
  rooms: [普通, 精英, 首领]
  decks: [claude_start, ironclad_start, ...]   # 每个卡组按自己 acts 字段打对应幕
  extra:                   # 可选：额外格子，例如循环探针
    - {deck: claude_loopA, encounter: DUMMY, fights: 20}
"""
import argparse
import hashlib
import json
import os
import random
import time
from multiprocessing import Pool

import yaml

from .modloader import ModSet
from .core import Combat
from . import enemies as EN
from .ai import AGENTS

_MODSETS = {}


def get_modset(names):
    key = tuple(names)
    if key not in _MODSETS:
        _MODSETS[key] = ModSet(names)
    return _MODSETS[key]


def _seed(*parts):
    h = hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:12], 16)


class Dummy(EN.Enemy):
    """木桩：9999 血、不攻击。用于循环探针。"""
    def __init__(self, hp=9999):
        md = EN.MonsterDef({"id": "DUMMY", "name": "木桩", "min_hp": hp, "max_hp": hp,
                            "moves": [{"id": "IDLE", "name": "发呆", "intent": "Unknown"}]}, "木桩")
        super().__init__(md, random.Random(0))


def run_fight(mod_names, deck_id, act, room, idx, seed, agent_name="heuristic", max_turns=30,
              encounter_id=None, log=False, agent_kw=None, potions=None):
    M = get_modset(mod_names)
    rng = random.Random(_seed(seed, deck_id, act, room, idx, encounter_id))
    P, relics, dk = M.build_player(deck_id)
    if potions is not None:
        P.potions = list(potions)
    if encounter_id == "DUMMY":
        enemies = [Dummy()]
        enc_name = "木桩"
    else:
        if encounter_id:
            enc = [e for e in EN.load_db()["encounters"] if e["id"] == encounter_id][0]
        else:
            pool = EN.encounter_pool(act, room)
            enc = pool[rng.randrange(len(pool))]
        enemies = EN.build_encounter(enc, rng)
        enc_name = enc["zh_name"]
        encounter_id = enc["id"]
    agent = AGENTS[agent_name](**(agent_kw or {}))
    C = Combat(P, enemies, M, rng=rng, agent=agent, max_turns=max_turns)
    C.relics = relics
    C.data["_room"] = room
    if log:
        C.log = []
    start_hp = P.hp
    enemy_hp0 = sum(e.hp for e in enemies)
    t0 = time.perf_counter()
    res = C.run()
    out = {
        "deck": deck_id, "act": act, "room": room, "encounter": encounter_id, "enc_name": enc_name, "agent": agent_name,
        "result": res, "turns": C.turn, "hp_lost": start_hp - max(0, P.hp) if res != "loss" else start_hp,
        "hp_left": max(0, P.hp), "cards": C.stats.card, "loop": C.loop_alarm,
        "max_actions": C.data.get("_max_actions", 0), "secs": time.perf_counter() - t0,
        "dmg_total": sum(v[1] for v in C.stats.card.values()), "enemy_hp": enemy_hp0,
    }
    if C.data.get("_extra"):
        out["extra"] = C.data["_extra"]   # mod 钩子自定义统计（可 JSON 序列化）
    if log:
        out["log"] = C.log
    return out


def _task(a):
    return run_fight(*a[0], **a[1])


def plan(exp, M, fights=None):
    tasks = []
    n = fights or exp.get("fights", 100)
    for did in exp["decks"]:
        dk = M.decks[did]
        for act in dk.get("acts", [1]):
            for room in exp.get("rooms", ["普通", "精英", "首领"]):
                for i in range(n):
                    tasks.append(((exp["mods"], did, act, room, i, exp.get("seed", 1)),
                                  {"agent_name": exp.get("agent", "heuristic"), "max_turns": exp.get("max_turns", 30)}))
    for x in exp.get("extra", []) or []:
        for i in range(x.get("fights", 20)):
            tasks.append(((exp["mods"], x["deck"], x.get("act", 1), x.get("room", "探针"), i, exp.get("seed", 1)),
                          {"agent_name": x.get("agent", exp.get("agent", "heuristic")), "max_turns": x.get("max_turns", 3),
                           "encounter_id": x.get("encounter")}))
    return tasks


def run_experiment(path, fights=None, jobs=None, seed=None, agent=None, out_dir=None):
    exp = yaml.safe_load(open(path, encoding="utf-8"))
    if seed is not None:
        exp["seed"] = seed
    if agent:
        exp["agent"] = agent
    if fights:
        exp["fights"] = fights
    for k, v in (exp.get("env") or {}).items():   # 变体开关：子进程继承环境变量
        os.environ[str(k)] = str(v)
    M = get_modset(exp["mods"])
    tasks = plan(exp, M, fights)
    jobs = jobs or os.cpu_count() or 1
    t0 = time.time()
    if jobs > 1:
        with Pool(jobs) as pool:
            results = pool.map(_task, tasks, chunksize=max(1, len(tasks) // (jobs * 8)))
            approx = pool.map(_collect_approx, range(jobs * 4))
    else:
        results = [_task(t) for t in tasks]
        approx = [dict(EN.APPROX)]
    allapprox = {}
    for a in approx:
        allapprox.update(a)
    allapprox.update(EN.APPROX)
    wall = time.time() - t0
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", exp["name"])
    os.makedirs(out_dir, exist_ok=True)
    meta = {"exp": exp, "n_tasks": len(tasks), "wall_secs": wall, "jobs": jobs, "approx": allapprox}
    with open(os.path.join(out_dir, "raw.jsonl"), "w", encoding="utf-8") as f:
        for r in results:
            r = dict(r)
            r.pop("log", None)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from .report import make_report
    make_report(out_dir, M)
    return out_dir, wall, len(tasks)


def _collect_approx(_):
    # 让每个子进程都把自己遇到的近似说明交回来（有几个算几个）
    time.sleep(0.05)
    return dict(EN.APPROX)


def main():
    ap = argparse.ArgumentParser(description="StS2 mod 战斗模拟器")
    ap.add_argument("experiment")
    ap.add_argument("--fights", type=int)
    ap.add_argument("--jobs", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--agent")
    ap.add_argument("--out")
    a = ap.parse_args()
    out, wall, n = run_experiment(a.experiment, a.fights, a.jobs, a.seed, a.agent, a.out)
    print(f"完成 {n} 场，用时 {wall:.1f} 秒，报告在 {out}")


if __name__ == "__main__":
    main()
