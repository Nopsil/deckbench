"""汇总单卡/变体 A/B（同种子配对）：python3 tools/ab_table.py <目录> [--base base] [--ref 原版文件...]

目录下每个 <名字>.jsonl 是一组（同一批种子）。以 --base 组为基线，输出按平均层数排序的表：
平均层数、配对差 ± 95% 区间、到达幕 1 首领、到达幕 2、胜率、幕 1 普通战每场掉血。
"""
import argparse
import glob
import json
import math
import os


def load(f):
    return {r["seed"]: r for r in map(json.loads, open(f)) if not r.get("error")}


def boss1(r):
    return any(c[1] == "Boss" for c in r["combats"])


def row(rs):
    n = len(rs)
    mo = [c[4] for r in rs for c in r["combats"] if c[1] == "Monster" and c[6] == 0]
    return {"n": n, "floor": sum(r["floor"] for r in rs) / n, "boss1": sum(map(boss1, rs)) / n,
            "act2": sum(r["act"] >= 1 for r in rs) / n, "win": sum(r["victory"] for r in rs) / n,
            "mon": sum(mo) / max(1, len(mo))}


def paired(a, b, key):
    common = [s for s in b if s in a]
    d = [key(b[s]) - key(a[s]) for s in common]
    m = sum(d) / len(d)
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / max(1, len(d) - 1))
    return m, 1.96 * sd / math.sqrt(len(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--base", default="base")
    ap.add_argument("--labels", default=None, help="json：名字→说明")
    a = ap.parse_args()
    labels = json.load(open(a.labels)) if a.labels else {}
    groups = {os.path.basename(f)[:-6]: load(f) for f in sorted(glob.glob(os.path.join(a.dir, "*.jsonl")))}
    base = groups[a.base]
    rows = []
    for name, g in groups.items():
        r = row(list(g.values()))
        if name != a.base:
            r["d"], r["ci"] = paired(base, g, lambda x: x["floor"])
            r["db"], r["cib"] = paired(base, g, lambda x: float(boss1(x)))
        rows.append((name, r))
    rows.sort(key=lambda x: -x[1]["floor"])
    print("| 方案 | 说明 | N | 平均层数 | 配对差（95%） | 到达幕1首领 | 首领到达率差（95%） | 到达幕2 | 幕1普通战每场掉血 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, r in rows:
        d = f"{r['d']:+.2f} ± {r['ci']:.2f}" if "d" in r else "基线"
        db = f"{100 * r['db']:+.1f} ± {100 * r['cib']:.1f} pp" if "db" in r else "—"
        print(f"| {name} | {labels.get(name, '')} | {r['n']} | {r['floor']:.2f} | {d} | {100 * r['boss1']:.1f}% | {db} | "
              f"{100 * r['act2']:.1f}% | {r['mon']:.1f} |")


if __name__ == "__main__":
    main()
