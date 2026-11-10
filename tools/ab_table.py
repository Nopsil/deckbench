"""汇总单卡/变体 A/B（同种子配对）：python3 tools/ab_table.py <目录> [--base base] [--format markdown|text|json]

目录下每个 <名字>.jsonl 是一组（同一批种子）。以 --base 组为基线，输出按平均层数排序的表：
平均层数、配对差 ± 95% 区间、到达幕 1 首领、到达幕 2、胜率（Wilson 95% 区间）、
相对基线的两比例 z 检验 p 值、幕 1 普通战每场掉血。任一组 n < 30 时样本列标明不能下结论。
默认 Markdown。`--format text` 打成行，`--format json` 打每组一行字段（只追加，旧键还在）。
"""
import argparse
import glob
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from sts2sim.stats import proportion_compare_fields, win_rate_fields  # noqa: E402


def load(f):
    return {r["seed"]: r for r in map(json.loads, open(f)) if not r.get("error")}


def boss1(r):
    return any(c[1] == "Boss" for c in r["combats"])


def row(rs):
    n = len(rs)
    mo = [c[4] for r in rs for c in r["combats"] if c[1] == "Monster" and c[6] == 0]
    wins = sum(bool(r["victory"]) for r in rs)
    out = {"n": n, "floor": sum(r["floor"] for r in rs) / n, "boss1": sum(map(boss1, rs)) / n,
           "act2": sum(r["act"] >= 1 for r in rs) / n, "wins": wins, "win": wins / n,
           "mon": sum(mo) / max(1, len(mo))}
    out.update(win_rate_fields(wins, n))
    return out


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
    ap.add_argument("--format", choices=("markdown", "text", "json"), default="markdown")
    a = ap.parse_args()
    labels = json.load(open(a.labels)) if a.labels else {}
    groups = {os.path.basename(f)[:-6]: load(f) for f in sorted(glob.glob(os.path.join(a.dir, "*.jsonl")))}
    base = groups[a.base]
    base_row = row(list(base.values()))
    rows = []
    for name, g in groups.items():
        r = base_row if name == a.base else row(list(g.values()))
        if name != a.base:
            r["d"], r["ci"] = paired(base, g, lambda x: x["floor"])
            r["db"], r["cib"] = paired(base, g, lambda x: float(boss1(x)))
            r.update(proportion_compare_fields(base_row["wins"], base_row["n"], r["wins"], r["n"]))
        rows.append((name, r))
    rows.sort(key=lambda x: -x[1]["floor"])
    if a.format == "json":
        payload = []
        for name, r in rows:
            item = {"name": name, "label": labels.get(name, ""), "baseline": name == a.base}
            item.update(r)
            payload.append(item)
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
        return
    if a.format == "text":
        for name, r in rows:
            ci = ""
            if r.get("win_ci_low") is not None:
                ci = f"  Wilson 95% CI {100 * r['win_ci_low']:.1f}%–{100 * r['win_ci_high']:.1f}%"
            p = ""
            if "p_value" in r:
                pv = r["p_value"]
                p = "  胜率差 p=" + ("—" if pv is None else f"{pv:.4f}" if pv >= 0.0001 else f"{pv:.2e}")
            warn = ("  " + r["sample_warning_text"]) if r.get("sample_warning_text") else ""
            print(f"{name}: 胜率 {100 * r['win']:.1f}% ({r['wins']}/{r['n']}){ci}{p}{warn}")
        return
    print("| 方案 | 说明 | N | 平均层数 | 配对差（95%） | 到达幕1首领 | 首领到达率差（95%） | 到达幕2 | 幕1普通战每场掉血 | 胜率 (Wilson 95%) | 胜率差 p | 样本 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, r in rows:
        d = f"{r['d']:+.2f} ± {r['ci']:.2f}" if "d" in r else "基线"
        db = f"{100 * r['db']:+.1f} ± {100 * r['cib']:.1f} pp" if "db" in r else "—"
        if r.get("win_ci_low") is None:
            wcell = "—"
        else:
            wcell = f"{100 * r['win']:.1f}% ({100 * r['win_ci_low']:.1f}%–{100 * r['win_ci_high']:.1f}%)"
        if "p_value" not in r:
            pcell = "—"
        elif r["p_value"] is None:
            pcell = "—"
        elif r["p_value"] < 0.0001:
            pcell = f"{r['p_value']:.2e}"
        else:
            pcell = f"{r['p_value']:.4f}"
        sample = "不足，不能下结论" if r.get("sample_warning") else "够"
        print(f"| {name} | {labels.get(name, '')} | {r['n']} | {r['floor']:.2f} | {d} | {100 * r['boss1']:.1f}% | {db} | "
              f"{100 * r['act2']:.1f}% | {r['mon']:.1f} | {wcell} | {pcell} | {sample} |")


if __name__ == "__main__":
    main()
