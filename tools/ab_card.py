"""单卡 A/B：同一批种子，各跑一遍「原始起始牌组」和「起始牌组 + 指定牌」（可选替换掉 1 张），做配对比较。

  PYTHONPATH=. python3 tools/ab_card.py --char Claude --asc 0 --n 400 --force CLAUDE_CLASSIFIER [--replace CLAUDE_STRIKE]
      [--variant classifier_flat] [--agent strong-nosearch] [--base-variant ...]

强制加牌发生在进入第一幕之前，种子相同 → 地图、遭遇、奖励池的随机序列相同，两边的差别只来自牌组（以及因此改变的决策）。
输出：平均层数差（配对，带标准误和 95% 区间）、到达幕 1 首领/幕 2 比例差、胜率差、幕 1 每场掉血差。
B 组可以另外指定 --variant（例如比较 宪法分类器 原版 vs 平加变体：两边都 --force CLAUDE_CLASSIFIER，B 组 --variant classifier_flat）。
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch  # noqa: E402


def run(char, asc, seeds, agent, force, replace, variant, procs):
    cfg = {"name": agent, "kw": {}, "variant": variant, "force": force, "replace": replace,
           "timeout": 60 if agent == "heuristic" else 900}
    with mp.Pool(procs, initializer=batch._init, initargs=(cfg,)) as pool:
        return pool.map(batch._one, [(char, asc, s) for s in seeds], chunksize=1)


def stats(res):
    ok = [r for r in res if not r.get("error")]
    boss = lambda r: any(c[1] == "Boss" for c in r["combats"])  # noqa
    a1 = [c[4] for r in ok for c in r["combats"] if c[6] == 0]
    return {"n": len(ok), "err": len(res) - len(ok), "floor": sum(r["floor"] for r in ok) / max(1, len(ok)),
            "boss1": sum(map(boss, ok)) / max(1, len(ok)), "act2": sum(r["act"] >= 1 for r in ok) / max(1, len(ok)),
            "win": sum(r["victory"] for r in ok) / max(1, len(ok)), "loss_a1": sum(a1) / max(1, len(a1))}


def paired(a, b, key):
    da = {r["seed"]: r for r in a if not r.get("error")}
    d = [key(r) - key(da[r["seed"]]) for r in b if not r.get("error") and r["seed"] in da]
    n = len(d)
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / max(1, n - 1))
    se = sd / math.sqrt(n)
    return m, se, sum(1 for x in d if x != 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Claude")
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--agent", default="strong-nosearch")
    ap.add_argument("--force", required=True)
    ap.add_argument("--replace", default="")
    ap.add_argument("--base-force", default="", help="A 组也加的牌（比较同一张牌的两个变体时用）")
    ap.add_argument("--variant", default=None, help="B 组的变体")
    ap.add_argument("--base-variant", default=None)
    ap.add_argument("--procs", type=int, default=mp.cpu_count())
    ap.add_argument("--out", default=None, help="把两组原始结果写到 <out>_A.jsonl / <out>_B.jsonl")
    a = ap.parse_args()
    seeds = [f"R{i}" for i in range(a.start, a.start + a.n)]
    sp = lambda x: [y for y in x.split(",") if y]  # noqa
    t = time.time()
    A = run(a.char, a.asc, seeds, a.agent, sp(a.base_force), [], a.base_variant, a.procs)
    B = run(a.char, a.asc, seeds, a.agent, sp(a.force), sp(a.replace), a.variant, a.procs)
    if a.out:
        for tag, res in (("A", A), ("B", B)):
            with open(f"{a.out}_{tag}.jsonl", "w") as f:
                for r in res:
                    f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    sa, sb = stats(A), stats(B)
    lab = f"+{a.force}" + (f" -{a.replace}" if a.replace else "") + (f" [{a.variant}]" if a.variant else "")
    print(f"{a.char} A{a.asc} {a.agent} N={a.n}  A=基线{(' +' + a.base_force) if a.base_force else ''}  B={lab}  ({time.time() - t:.0f}s)")
    for k, name in (("floor", "平均层数"), ("boss1", "到达幕1首领"), ("act2", "到达幕2"), ("win", "胜率"), ("loss_a1", "幕1每场掉血")):
        print(f"  {name:8s} A {sa[k]:.3f}  B {sb[k]:.3f}")
    for name, key in (("层数", lambda r: r["floor"]), ("到达幕2", lambda r: float(r["act"] >= 1)),
                      ("胜", lambda r: float(r["victory"]))):
        m, se, nd = paired(A, B, key)
        print(f"  配对差 {name}: {m:+.3f} ± {1.96 * se:.3f} (95%)  [不同的种子 {nd}/{sa['n']}]")
    if sa["err"] or sb["err"]:
        print(f"  errors A {sa['err']} B {sb['err']}")


if __name__ == "__main__":
    main()
