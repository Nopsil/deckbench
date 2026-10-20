"""模仿学习流程：
  collect：python tools/imitate.py collect --n 40 --asc 0 [--boss-depth 99]   （learned-search 打整局并记录搜索决策）
  train：  python tools/imitate.py train                                     （→ data/imitation_model.json）
  评估：   python tools/batch.py --agent imitation ...
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "..", "reports", "ai_upgrade", "imit")
CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]


def _collect(args):
    char, asc, seed, bd, timeout = args
    import signal
    import zlib
    import batch
    from sts2sim.engine.weights import load_learned
    from sts2sim.engine.imitate import Recorder, RecordingSearchAgent
    from sts2sim.engine.run import play_run
    load_learned()
    rec = Recorder(os.path.join(OUT, f"rec_{os.getpid()}.jsonl"))
    s = zlib.crc32(str(seed).encode()) & 0xFFFF
    ag = RecordingSearchAgent(rec, seed=s, search=True, boss_aware=True, boss_depth=bd)
    signal.signal(signal.SIGALRM, batch._alarm)
    signal.alarm(timeout)
    try:
        r = play_run(char, asc, seed, agent=ag)
        fl = r.floor
    except BaseException:  # noqa
        fl = -1
    finally:
        signal.alarm(0)
        rec.flush()
    return char, seed, fl


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--n", type=int, default=40)
    c.add_argument("--asc", type=int, default=0)
    c.add_argument("--prefix", default="I")
    c.add_argument("--boss-depth", type=int, default=None)
    c.add_argument("--procs", type=int, default=mp.cpu_count())
    c.add_argument("--timeout", type=int, default=900)
    t = sub.add_parser("train")
    t.add_argument("--l2", type=float, default=1e-3)
    t.add_argument("--iters", type=int, default=400)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.cmd == "collect":
        jobs = [(ch, a.asc, f"{a.prefix}{i}", a.boss_depth, a.timeout) for i in range(a.n) for ch in CHARS]
        with mp.Pool(a.procs, maxtasksperchild=4) as pool:
            for k, (ch, sd, fl) in enumerate(pool.imap_unordered(_collect, jobs)):
                print(f"[{k + 1}/{len(jobs)}] {ch} {sd} floor {fl}", flush=True)
    else:
        from sts2sim.engine.imitate import train, heuristic_agreement
        paths = sorted(glob.glob(os.path.join(OUT, "rec_*.jsonl")))
        m = train(paths, l2=a.l2, iters=a.iters)
        m["heuristic_agreement"] = heuristic_agreement(paths)
        dst = os.path.join(HERE, "..", "data", "imitation_model.json")
        json.dump(m, open(dst, "w"), indent=1)
        print(f"samples train {m['n_train']} val {m['n_val']} | acc train {m['train_acc']:.3f} val {m['val_acc']:.3f} | "
              f"heuristic agreement {m['heuristic_agreement']:.3f}")
        for f, w in sorted(zip(m["feats"], m["w"]), key=lambda x: -abs(x[1]))[:12]:
            print(f"  {f}: {w:+.3f}")


if __name__ == "__main__":
    main()
