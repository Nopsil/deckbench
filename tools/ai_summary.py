"""汇总 batch.py 的 jsonl：平均层数±SE、各幕到达率、胜率（Wilson 95% CI）、主要死因、各类战斗掉血。
用法：python tools/ai_summary.py a.jsonl [b.jsonl ...] [--deaths 5] [--md]"""
import argparse
import collections
import json
import math
import os
import statistics as st


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def load(f):
    return [json.loads(l) for l in open(f) if l.strip()]


def summarize(rs):
    n = len(rs)
    err = sum(1 for r in rs if r.get("error"))
    fl = [max(0, r["floor"]) for r in rs]
    wins = sum(1 for r in rs if r["victory"])

    def boss_reached(r, act):
        return any(c[1] == "Boss" and (c[6] if len(c) > 6 else -1) == act for c in r["combats"])

    def boss_won(r, act):
        return any(c[1] == "Boss" and c[6] == act and c[5] for c in r["combats"])
    out = {"n": n, "err": err, "floor": st.mean(fl), "se": (st.pstdev(fl) / math.sqrt(n)) if n > 1 else 0.0,
           "b1": sum(boss_reached(r, 0) for r in rs) / n, "a2": sum(boss_won(r, 0) for r in rs) / n,
           "b2": sum(boss_reached(r, 1) for r in rs) / n, "a3": sum(boss_won(r, 1) for r in rs) / n,
           "b3": sum(boss_reached(r, 2) for r in rs) / n, "wins": wins, "win": wins / n, "ci": wilson(wins, n),
           "sec": st.mean(r.get("seconds", 0) for r in rs)}
    deaths = collections.Counter()
    for r in rs:
        if r["victory"] or r.get("error"):
            continue
        d = r.get("death_room")
        if d:
            deaths[f"{d[2]}({d[1]})"] += 1
        else:
            deaths["?"] += 1
    out["deaths"] = deaths
    loss = collections.defaultdict(list)
    for r in rs:
        for c in r["combats"]:
            loss[f"{c[1]}@{c[6] + 1}"].append(c[4])
    out["loss"] = {k: st.mean(v) for k, v in sorted(loss.items())}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--deaths", type=int, default=5)
    a = ap.parse_args()
    print("| 文件 | N | 错 | 平均层数±SE | 到幕1首领 | 过幕1 | 到幕2首领 | 过幕2 | 到幕3首领 | 胜率 (95%CI) | 秒/局 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    S = []
    for f in a.files:
        s = summarize(load(f))
        S.append((f, s))
        print(f"| {os.path.basename(f)[:-6]} | {s['n']} | {s['err']} | {s['floor']:.2f}±{s['se']:.2f} | {s['b1']:.0%} | {s['a2']:.0%} | "
              f"{s['b2']:.0%} | {s['a3']:.0%} | {s['b3']:.0%} | {s['win']:.1%} ({s['ci'][0]:.1%}–{s['ci'][1]:.1%}) | {s['sec']:.1f} |")
    if a.deaths:
        print()
        for f, s in S:
            tot = sum(s["deaths"].values()) or 1
            top = ", ".join(f"{k} {v / tot:.0%}" for k, v in s["deaths"].most_common(a.deaths))
            ls = " ".join(f"{k}:{v:.0f}" for k, v in s["loss"].items())
            print(f"- {os.path.basename(f)[:-6]}：死因 {top}｜均掉血 {ls}")


if __name__ == "__main__":
    main()
