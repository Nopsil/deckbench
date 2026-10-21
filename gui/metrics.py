"""从模拟器真实输出里算指标（不编造任何数）：整局 jsonl、战斗实验 cells.csv。"""
import collections
import csv
import json
import math
import os

ROOM_ZH = {"Monster": "普通", "Elite": "精英", "Boss": "首领"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _boss1(r):
    # 与 tools/ab_card.py / ab_table.py 相同：打过首领战 = 到达幕 1 首领
    return any(c[1] == "Boss" for c in r["combats"])


def batch_summary(res):
    ok = [r for r in res if not r.get("error")]
    n = len(ok)
    out = {"n_total": len(res), "n": n, "errors": len(res) - n}
    if not n:
        return out
    floors = sorted(r["floor"] for r in ok)
    out.update({
        "avg_floor": sum(floors) / n,
        "median_floor": floors[n // 2],
        "max_floor": floors[-1],
        "boss1": sum(map(_boss1, ok)) / n,
        "act2": sum(r["act"] >= 1 for r in ok) / n,
        "act3": sum(r["act"] >= 2 for r in ok) / n,
        "win": sum(bool(r["victory"]) for r in ok) / n,
        "wins": sum(bool(r["victory"]) for r in ok),
    })
    # 幕 1 每场掉血（按房间类型）
    loss = collections.defaultdict(list)
    for r in ok:
        for c in r["combats"]:
            act = c[6] if len(c) > 6 else 0
            loss[(c[1], act)].append(c[4])
    out["hp_loss"] = [{"room": ROOM_ZH.get(k[0], k[0]), "act": k[1] + 1, "avg": sum(v) / len(v), "n": len(v)}
                      for k, v in sorted(loss.items(), key=lambda kv: (kv[0][1], ["Monster", "Elite", "Boss"].index(kv[0][0]) if kv[0][0] in ("Monster", "Elite", "Boss") else 9))]
    a1 = [c[4] for r in ok for c in r["combats"] if c[1] == "Monster" and (c[6] if len(c) > 6 else 0) == 0]
    out["mon_loss_a1"] = sum(a1) / len(a1) if a1 else None
    # 存活曲线：到达（≥）第 f 层的局数比例
    mx = max(floors + [1])
    out["survival"] = [{"floor": f, "rate": sum(1 for x in floors if x >= f) / n} for f in range(1, mx + 1)]
    # 死因
    by_enc = collections.Counter()
    by_room = collections.Counter()
    for r in ok:
        if r["victory"]:
            continue
        dr = r.get("death_room")
        if dr:
            by_enc[str(dr[2])] += 1
            by_room[ROOM_ZH.get(dr[1], str(dr[1]))] += 1
        else:
            by_enc["_unrecorded"] += 1     # 界面按语言显示「未记录」
            by_room["_unrecorded"] += 1
    out["death_by_encounter"] = [{"name": k, "count": v} for k, v in by_enc.most_common(15)]
    out["death_by_room"] = [{"name": k, "count": v} for k, v in by_room.most_common()]
    picks = collections.Counter(p for r in ok for p in r.get("picked", []))
    out["top_picks"] = [{"id": k, "count": v} for k, v in picks.most_common(15)]
    out["avg_secs"] = sum(r.get("seconds", 0) for r in ok) / n
    out["loop_alarm"] = sum(1 for r in ok if r.get("loop_alarm"))
    return out


def paired(a, b, key):
    """同种子配对差（与 tools/ab_card.paired 一样的算法）；没有共同种子时用两独立样本。"""
    da = {r["seed"]: r for r in a if not r.get("error")}
    d = [key(r) - key(da[r["seed"]]) for r in b if not r.get("error") and r["seed"] in da]
    n = len(d)
    if n >= 2:
        m = sum(d) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1))
        se = sd / math.sqrt(n)
        return {"diff": m, "ci95": 1.96 * se, "n": n, "paired": True, "differ": sum(1 for x in d if x != 0)}
    xa = [key(r) for r in a if not r.get("error")]
    xb = [key(r) for r in b if not r.get("error")]
    if len(xa) < 2 or len(xb) < 2:
        return None

    def mv(x):
        m = sum(x) / len(x)
        return m, sum((y - m) ** 2 for y in x) / (len(x) - 1)
    ma, va = mv(xa)
    mb, vb = mv(xb)
    se = math.sqrt(va / len(xa) + vb / len(xb))
    return {"diff": mb - ma, "ci95": 1.96 * se, "n": min(len(xa), len(xb)), "paired": False}


# 指标名：界面按 key 翻译（metric.<key>）；name 只是给脚本看的当前语言文字
AB_KEYS = [("floor", lambda r: r["floor"], False),
           ("boss1", lambda r: float(_boss1(r)), True),
           ("act2", lambda r: float(r["act"] >= 1), True),
           ("act3", lambda r: float(r["act"] >= 2), True),
           ("win", lambda r: float(bool(r["victory"])), True)]


def batch_ab(a, b):
    sa, sb = batch_summary(a), batch_summary(b)
    rows = []
    from . import i18n
    for k, key, pct in AB_KEYS:
        p = paired(a, b, key)
        sk = "avg_floor" if k == "floor" else k
        row = {"key": k, "name": i18n.t(f"metric.{k}"), "pct": pct, "a": sa.get(sk), "b": sb.get(sk)}
        if p:
            row.update(p)
            row["significant"] = p["ci95"] > 0 and abs(p["diff"]) > p["ci95"]
            if p["ci95"] == 0 and p["diff"] == 0:
                row["significant"] = False
        rows.append(row)
    return {"a": sa, "b": sb, "rows": rows}


# ---------------------------------------------------------------- 战斗实验
def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def combat_summary(out_dir):
    cells = read_csv(os.path.join(out_dir, "cells.csv"))
    meta = {}
    mp = os.path.join(out_dir, "meta.json")
    if os.path.exists(mp):
        meta = json.load(open(mp, encoding="utf-8"))
    rows = []
    tot = wins = 0
    for c in cells:
        n = int(_num(c.get("场数")) or 0)
        w = _num(c.get("胜率%"))
        rows.append({"deck_id": c.get("卡组id"), "deck": c.get("卡组"), "stage": c.get("阶段"), "act": c.get("幕"),
                     "room": c.get("房间"), "n": n, "win": w, "loss": _num(c.get("战败%")), "timeout": _num(c.get("超时%")),
                     "turns": _num(c.get("平均回合")), "hp_loss": _num(c.get("平均掉血")), "dpt": _num(c.get("每回合输出")),
                     "loops": int(_num(c.get("循环报警场数")) or 0)})
        if w is not None and n:
            tot += n
            wins += n * w / 100
    cards = read_csv(os.path.join(out_dir, "cards.csv"))
    rep = os.path.join(out_dir, "report.md")
    return {"cells": rows, "fights": meta.get("n_tasks", tot), "cell_fights": tot,
            "win": (wins / tot) if tot else None, "wall_secs": meta.get("wall_secs"),
            "title": (meta.get("exp") or {}).get("title"), "cards_columns": list(cards[0].keys()) if cards else [],
            "cards": cards[:300], "has_report": os.path.exists(rep)}


def combat_ab(da, db):
    """两次战斗实验按（卡组, 幕, 房间）对齐，胜率差用两比例 z 检验（95%）。"""
    ia = {(r["deck_id"], r["act"], r["room"]): r for r in da["cells"]}
    rows = []
    for r in db["cells"]:
        k = (r["deck_id"], r["act"], r["room"])
        if k not in ia:
            continue
        x = ia[k]
        if x["win"] is None or r["win"] is None or not x["n"] or not r["n"]:
            continue
        pa, pb = x["win"] / 100, r["win"] / 100
        se = math.sqrt(pa * (1 - pa) / x["n"] + pb * (1 - pb) / r["n"])
        d = pb - pa
        rows.append({"deck": r["deck"], "act": r["act"], "room": r["room"], "a": pa, "b": pb, "diff": d, "ci95": 1.96 * se,
                     "significant": se > 0 and abs(d) > 1.96 * se, "na": x["n"], "nb": r["n"],
                     "a_turns": x["turns"], "b_turns": r["turns"], "a_loss": x["hp_loss"], "b_loss": r["hp_loss"]})
    return {"rows": rows}
