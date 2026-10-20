"""自我对局 + CMA-ES 学习 AI 参数（sts2sim/engine/weights.py 里的 ~30 个出牌/选牌/路线/休息/商店参数）。

每一代：λ 组候选参数 × 同一批训练种子（T<代>_<i>，与评估种子 R0… 不重叠）× 5 个原版角色跑整局；
适应度 = 平均层数 + 8×通关率（同代候选用同样的种子，减少噪声）。CMA-ES 的均值向量就是“学到的参数”，
每代写到 data/ai_weights.json（含历史）。

python tools/tune_cma.py --gens 14 --pop 10 --n 16 --asc 0 --agent strong-nosearch
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]


def _task(args):
    w, agent, char, asc, seed = args
    import batch
    from sts2sim.engine.weights import set_weights
    set_weights(w)
    batch.AGENT.update({"name": agent, "kw": {"boss_aware": True, "boss_search": False}, "timeout": 120})
    r = batch._one((char, asc, seed))
    return (max(0, r["floor"]) if not r.get("error") else 0) + 8.0 * bool(r["victory"]), bool(r["victory"]), bool(r.get("error"))


class CMA:
    """标准 CMA-ES（Hansen 2016 教程版，purecma 的精简实现）。"""

    def __init__(self, x0, sigma, pop):
        n = self.n = len(x0)
        self.xmean = np.array(x0, float)
        self.sigma = sigma
        self.lam = pop
        self.mu = pop // 2
        w = np.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.w = w / w.sum()
        self.mueff = 1.0 / (self.w ** 2).sum()
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.pc = np.zeros(n)
        self.ps = np.zeros(n)
        self.C = np.eye(n)
        self.chiN = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.gen = 0

    def ask(self, rng):
        D, B = np.linalg.eigh(self.C)
        D = np.sqrt(np.maximum(D, 1e-20))
        self.B, self.D = B, D
        z = rng.standard_normal((self.lam, self.n))
        return [self.xmean + self.sigma * (B @ (D * zi)) for zi in z]

    def tell(self, xs, fit):     # fit：越小越好
        n = self.n
        idx = np.argsort(fit)
        xold = self.xmean.copy()
        X = np.array([xs[i] for i in idx[: self.mu]])
        self.xmean = self.w @ X
        y = (self.xmean - xold) / self.sigma
        Cinvsqrt = self.B @ np.diag(1 / self.D) @ self.B.T
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * (Cinvsqrt @ y)
        self.gen += 1
        hsig = np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * self.gen)) / self.chiN < 1.4 + 2 / (n + 1)
        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y
        Y = (X - xold) / self.sigma
        self.C = (1 - self.c1 - self.cmu) * self.C + self.c1 * (np.outer(self.pc, self.pc) + (1 - hsig) * self.cc * (2 - self.cc) * self.C) \
            + self.cmu * (Y.T * self.w) @ Y
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chiN - 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=14)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--n", type=int, default=16, help="每角色每候选的局数")
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--agent", default="strong-nosearch")
    ap.add_argument("--sigma", type=float, default=0.5)
    ap.add_argument("--procs", type=int, default=mp.cpu_count())
    ap.add_argument("--init", default=None, help="从已有参数文件（weights）出发")
    ap.add_argument("--seed-prefix", default="T", help="训练种子前缀（换一批训练种子）")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "data", "ai_weights.json"))
    ap.add_argument("--log", default=os.path.join(HERE, "..", "reports", "ai_upgrade", "tune_log.jsonl"))
    a = ap.parse_args()
    from sts2sim.engine.weights import DEFAULTS, SCALE
    keys = sorted(DEFAULTS)
    d0 = np.array([DEFAULTS[k] for k in keys])
    sc = np.array([SCALE[k] for k in keys])

    def to_w(x):
        v = d0 + x * sc
        return {k: float(max(0.0, v[i])) if not k.startswith("c_k") else float(max(0.05, v[i])) for i, k in enumerate(keys)}
    x0 = np.zeros(len(keys))
    if a.init:
        wi = json.load(open(a.init, encoding="utf-8"))["weights"]
        x0 = np.array([(wi.get(k, DEFAULTS[k]) - DEFAULTS[k]) / sc[i] for i, k in enumerate(keys)])
    es = CMA(x0, a.sigma, a.pop)
    rng = np.random.default_rng(12345)
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    hist = []
    with mp.Pool(a.procs, maxtasksperchild=40) as pool:
        for g in range(a.gens):
            t = time.time()
            xs = es.ask(rng)
            cands = [to_w(x) for x in xs] + [to_w(es.xmean)]     # 最后一个 = 当前均值（只记录，不参与更新）
            seeds = [f"{a.seed_prefix}{g}_{i}" for i in range(a.n)]
            jobs = [(w, a.agent, c, a.asc, s) for w in cands for c in CHARS for s in seeds]
            res = pool.map(_task, jobs, chunksize=2)
            per = len(CHARS) * a.n
            fit = [sum(r[0] for r in res[i * per:(i + 1) * per]) / per for i in range(len(cands))]
            errs = sum(r[2] for r in res)
            es.tell(xs, [-f for f in fit[:-1]])
            rec = {"gen": g, "fit_mean_cand": float(np.mean(fit[:-1])), "fit_best": float(max(fit[:-1])), "fit_xmean": fit[-1],
                   "sigma": es.sigma, "errors": errs, "sec": time.time() - t, "xmean": to_w(es.xmean)}
            hist.append({k: rec[k] for k in rec if k != "xmean"})
            with open(a.log, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"gen {g}: cand mean {rec['fit_mean_cand']:.2f} best {rec['fit_best']:.2f} | old-mean {fit[-1]:.2f} | sigma {es.sigma:.3f} | err {errs} | {rec['sec']:.0f}s", flush=True)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump({"agent": a.agent, "asc": a.asc, "gens": g + 1, "pop": a.pop, "n_per_char": a.n,
                           "note": "CMA-ES 自我对局学习的参数（均值向量）；默认值见 sts2sim/engine/weights.py",
                           "weights": to_w(es.xmean), "history": hist}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
