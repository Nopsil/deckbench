"""把决策说明日志里的一场战斗打成 Markdown。

    python tools/explain_fight.py explain.jsonl
    python tools/explain_fight.py runs.explain.jsonl --fight 2 --seed R0 --out fight.md

``--fight`` 是过滤 ``--seed`` 之后的第几场（从 0 开始）。只渲染这一场的出牌、目标和药水；
若日志里有同一层的奖励或商店，附在后面。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sts2sim.explain import load_jsonl, render_fight  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="把一场战斗的决策说明日志打成 Markdown")
    ap.add_argument("log", help="explain.jsonl")
    ap.add_argument("--fight", type=int, default=0, help="第几场战斗，从 0 开始（先按 --seed 过滤）")
    ap.add_argument("--seed", default="", help="只看这个种子")
    ap.add_argument("--out", default="", help="写到这个文件；不写就打到标准输出")
    a = ap.parse_args(argv)
    rows = load_jsonl(a.log)
    try:
        text = render_fight(rows, a.fight, seed=a.seed or None)
    except IndexError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    if a.out:
        parent = os.path.dirname(os.path.abspath(a.out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace") if hasattr(sys.stdout, "reconfigure") else None
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
