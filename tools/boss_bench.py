"""首领战基准：用同一个快速 AI 打到幕 1 首领（之前的决策完全相同，所以首领战前的局面逐局一致），
首领战换成不同的配置，比较首领战胜率和掉血。打完首领（或死）就停。
python tools/boss_bench.py --char Ironclad --asc 0 --n 60 --variant learned --variant "learned-boss:boss_depth=2"
变体写法：agent 名[:k=v,k=v]（kw 传给 StrongAgent）。"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)


def parse_variant(v):
    name, _, rest = v.partition(":")
    kw = {}
    for kv in filter(None, rest.split(",")):
        k, _, x = kv.partition("=")
        kw[k] = int(x) if x.lstrip("-").isdigit() else float(x) if x.replace(".", "", 1).isdigit() else x
    return name, kw


def _task(args):
    variant, char, asc, seed, act = args
    import batch
    from sts2sim.engine import run as R
    from sts2sim.engine.manager import RunOver
    batch._load_mods(char)
    name, kw = parse_variant(variant)
    kw = dict({"boss_aware": True}, **kw)
    ag = batch.make_agent(name, seed, **kw)
    out = {"seed": seed, "reached": False}
    orig = R.RunDriver._combat

    def _combat(self, room):
        boss = R.C._n(room.RoomType) == "Boss" and self.state.CurrentActIndex == act
        hp0 = self.player.Creature.CurrentHp
        t = time.time()
        try:
            orig(self, room)
        except RunOver:
            if boss:
                out.update(reached=True, won=False, hp0=hp0, loss=hp0, sec=time.time() - t,
                           boss=room.Encounter.Id.Entry, rounds=self.result.combats[-1][3])
            raise
        if boss:
            c = self.result.combats[-1]
            out.update(reached=True, won=bool(c[5]), hp0=hp0, loss=c[4], sec=time.time() - t, boss=c[2], rounds=c[3])
            raise RunOver(False)
    R.RunDriver._combat = _combat
    try:
        r = R.play_run(char, asc, seed, agent=ag)
        out["error"] = r.error
        if getattr(ag, "mstats", None):
            out["mstats"] = ag.mstats
    finally:
        R.RunDriver._combat = orig
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Ironclad")
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--act", type=int, default=0)
    ap.add_argument("--variant", action="append", required=True)
    ap.add_argument("--procs", type=int, default=mp.cpu_count())
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    seeds = [f"R{i}" for i in range(a.start, a.start + a.n)]
    res = {}
    with mp.Pool(a.procs, maxtasksperchild=20) as pool:
        for v in a.variant:
            t = time.time()
            rs = pool.map(_task, [(v, a.char, a.asc, s, a.act) for s in seeds], chunksize=1)
            res[v] = rs
            b = [r for r in rs if r["reached"]]
            w = sum(r["won"] for r in b)
            loss = sum(r["loss"] for r in b) / max(1, len(b))
            sec = sum(r["sec"] for r in b) / max(1, len(b))
            err = sum(1 for r in rs if r.get("error"))
            ms = [r["mstats"] for r in rs if r.get("mstats")]
            if ms:
                nm, nf = sum(m["mentor"] for m in ms), sum(m["fallback"] for m in ms)
                print(f"  mentor decisions {nm}, fallback {nf}, mcts {sum(m['mcts_sec'] for m in ms) / max(1, nm) * 1000:.0f} ms/decision", flush=True)
            print(f"{a.char} A{a.asc} act{a.act + 1} boss | {v}: reached {len(b)}/{len(rs)}, won {w} ({w / max(1, len(b)):.0%}), "
                  f"avg HP loss {loss:.1f}, {sec:.1f}s/boss fight, errors {err}, wall {time.time() - t:.0f}s", flush=True)
    if len(a.variant) >= 2:
        v0 = a.variant[0]
        for v in a.variant[1:]:
            both = [(x, y) for x, y in zip(res[v0], res[v]) if x["reached"] and y["reached"]]
            gain = sum(1 for x, y in both if y["won"] and not x["won"])
            lose = sum(1 for x, y in both if x["won"] and not y["won"])
            print(f"  paired vs {v0}: +{gain} / -{lose} boss wins (of {len(both)})")
    if a.out:
        json.dump(res, open(a.out, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
