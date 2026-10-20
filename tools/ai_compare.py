"""两组 jsonl 目录对比（同名文件 = 同角色同进阶同种子）：python tools/ai_compare.py 旧目录 新目录"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_summary import load, summarize  # noqa: E402

a, b = sys.argv[1], sys.argv[2]
print("| 角色/进阶 | N | 平均层数 旧→新 | 到幕1首领 | 过幕1 | 到幕2首领 | 过幕2 | 胜 |")
print("|---|---|---|---|---|---|---|---|")
for f in sorted(glob.glob(os.path.join(b, "*.jsonl")), key=lambda p: ("A10" in p, p)):
    g = os.path.join(a, os.path.basename(f))
    if not os.path.exists(g):
        continue
    x, y = summarize(load(g)), summarize(load(f))
    pct = lambda k: f"{x[k]:.0%}→{y[k]:.0%}"  # noqa
    print(f"| {os.path.basename(f)[:-6]} | {y['n']} | {x['floor']:.2f}→**{y['floor']:.2f}** ({y['floor'] - x['floor']:+.2f}, ±{(x['se']**2 + y['se']**2) ** 0.5:.2f}) | "
          f"{pct('b1')} | {pct('a2')} | {pct('b2')} | {pct('a3')} | {x['wins']}→{y['wins']} |")
