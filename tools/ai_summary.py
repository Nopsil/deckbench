"""汇总 batch.py 的 jsonl：平均层数±SE、各幕到达率、胜率（Wilson 95% CI）、主要死因、各类战斗掉血。

用法：python tools/ai_summary.py a.jsonl [b.jsonl ...] [--deaths 5] [--json]
默认打 Markdown 表。两个及以上文件时，在表后给出相对第一个文件的胜率两比例 z 检验（p 值）。
任一组 n < 30 时标明样本不足、不能下结论。`--json` 改为打 JSON（旧键保留，另加区间和 p 值）。
"""
import argparse
import collections
import json
import math
import os
import statistics as st
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from sts2sim.stats import proportion_compare_fields, wilson_interval, win_rate_fields  # noqa: E402


def wilson(k, n, z=1.96):
    """兼容旧调用：n=0 仍返回 (0, 0)。区间本身来自 sts2sim.stats.wilson_interval。"""
    if n == 0:
        return 0.0, 0.0
    return wilson_interval(k, n, z)


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
    out.update(win_rate_fields(wins, n))
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
    ap.add_argument("--json", action="store_true", help="打 JSON，而不是 Markdown 表")
    a = ap.parse_args()
    S = []
    for f in a.files:
        s = summarize(load(f))
        S.append((f, s))
    if len(S) >= 2:
        base = S[0][1]
        for _f, s in S[1:]:
            # 对照字段单独命名，不覆盖这一组自己的 Wilson 区间和样本警告。
            cmp = proportion_compare_fields(base["wins"], base["n"], s["wins"], s["n"])
            s["p_value_vs_first"] = cmp["p_value"]
            s["z_vs_first"] = cmp["z"]
            s["test_vs_first"] = cmp["test"]
            s["sample_warning_vs_first"] = cmp["sample_warning"]
            s["sample_warning_text_vs_first"] = cmp["sample_warning_text"]
    if a.json:
        payload = []
        for f, s in S:
            item = {"file": os.path.basename(f)}
            item.update(s)
            item["ci"] = list(s["ci"])
            item["deaths"] = dict(s["deaths"])
            payload.append(item)
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=1)
        sys.stdout.write("\n")
        return
    print("| 文件 | N | 错 | 平均层数±SE | 到幕1首领 | 过幕1 | 到幕2首领 | 过幕2 | 到幕3首领 | 胜率 (Wilson 95% CI) | 秒/局 | 样本 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f, s in S:
        sample = "不足，不能下结论" if s.get("sample_warning") else "够"
        print(f"| {os.path.basename(f)[:-6]} | {s['n']} | {s['err']} | {s['floor']:.2f}±{s['se']:.2f} | {s['b1']:.0%} | {s['a2']:.0%} | "
              f"{s['b2']:.0%} | {s['a3']:.0%} | {s['b3']:.0%} | {s['win']:.1%} ({s['ci'][0]:.1%}–{s['ci'][1]:.1%}) | {s['sec']:.1f} | {sample} |")
    compared = [(f, s) for f, s in S[1:] if "p_value_vs_first" in s]
    if compared:
        print()
        print("胜率两比例 z 检验（相对第一个文件，双侧，合并比例） / two-proportion z-test vs the first file:")
        for f, s in compared:
            pv = s["p_value_vs_first"]
            ptxt = "—" if pv is None else (f"{pv:.4f}" if pv >= 0.0001 else f"{pv:.2e}")
            z = s.get("z_vs_first")
            ztxt = "—" if z is None else f"{z:+.3f}"
            warn = ("  " + s["sample_warning_text_vs_first"]) if s.get("sample_warning_text_vs_first") else ""
            print(f"- {os.path.basename(f)[:-6]}: z={ztxt}  p={ptxt}{warn}")
    if a.deaths:
        print()
        for f, s in S:
            tot = sum(s["deaths"].values()) or 1
            top = ", ".join(f"{k} {v / tot:.0%}" for k, v in s["deaths"].most_common(a.deaths))
            ls = " ".join(f"{k}:{v:.0f}" for k, v in s["loss"].items())
            extra = ("｜" + s["sample_warning_text"]) if s.get("sample_warning_text") else ""
            print(f"- {os.path.basename(f)[:-6]}：死因 {top}｜均掉血 {ls}{extra}")


if __name__ == "__main__":
    main()
