"""可选的决策说明日志（JSONL）。默认关闭。

打开方式：环境变量 ``DECKBENCH_EXPLAIN=1``、命令行 ``--explain``、实验 YAML 的 ``explain: true``、
或 ``tools/batch.py --explain``。关闭时 ``enabled()`` 为假，``publish`` 立刻返回，决策代码不组装候选列表。

记录的是决策当时已经算好的分数，不调用随机数。嵌套决策（搜索里的启发式推演、风格层改写最终选择）
只写出最外层真正执行的那一条。
"""
import json
import os
from contextlib import contextmanager

_TRUE = {"1", "true", "yes", "on"}
TOP = 5


def num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, 4)


def requested(flag=False):
    """命令行开关或环境变量。两者都没开就是关。"""
    if flag:
        return True
    return os.environ.get("DECKBENCH_EXPLAIN", "").strip().lower() in _TRUE


def sibling_path(out_path):
    """说明日志放在运行输出旁边。目录 → ``explain.jsonl``；``*.jsonl`` → ``*.explain.jsonl``。"""
    if not out_path:
        return os.path.abspath("explain.jsonl")
    if os.path.isdir(out_path) or not os.path.splitext(out_path)[1]:
        return os.path.join(out_path, "explain.jsonl")
    root, ext = os.path.splitext(out_path)
    if ext.lower() == ".jsonl":
        return root + ".explain.jsonl"
    return out_path + ".explain.jsonl"


def _same(a, b):
    if not a or not b:
        return False
    return a.get("id") == b.get("id") and a.get("target") == b.get("target") and a.get("hand") == b.get("hand")


def _chosen_list(chosen):
    if chosen is None:
        return []
    if isinstance(chosen, list):
        return [c for c in chosen if c]
    return [chosen]


def top(cands, chosen, n=TOP):
    """按分数从高到低留 n 条，并保证被选中的项还在列表里。不改调用方的列表。"""
    decorated = []
    for i, c in enumerate(cands or []):
        if not isinstance(c, dict):
            continue
        item = {k: v for k, v in c.items() if k != "picked"}
        if "score" in item:
            item["score"] = num(item.get("score"))
        decorated.append((item, i))

    def key(pair):
        s = pair[0].get("score")
        return (s is None, -(s if s is not None else 0.0), pair[1])

    decorated.sort(key=key)
    out = [c for c, _ in decorated[:n]]
    for ch in _chosen_list(chosen):
        if ch.get("id") is None and ch.get("kind") == "end":
            continue
        if not any(_same(c, ch) for c in out):
            extra = {k: v for k, v in ch.items() if k != "picked"}
            if "score" in extra:
                extra["score"] = num(extra.get("score"))
            out.append(extra)
    wanted = {(c.get("id"), c.get("target"), c.get("hand")) for c in _chosen_list(chosen) if c.get("kind") != "end"}
    for c in out:
        if (c.get("id"), c.get("target"), c.get("hand")) in wanted:
            c["picked"] = True
    return out


def _fill_scores(chosen, cands):
    """改写 chosen 时，若没带分数，从已有候选里抄过来。"""
    if isinstance(chosen, list):
        return [_fill_scores(c, cands) for c in chosen]
    if not isinstance(chosen, dict) or chosen.get("score") is not None:
        return chosen
    for c in cands:
        if _same(c, chosen) and c.get("score") is not None:
            out = dict(chosen)
            out["score"] = c.get("score")
            return out
    return chosen


def _strip(step):
    out = {}
    for k in ("id", "name", "target", "hand", "score", "value", "note", "cost"):
        if k in step and step[k] is not None:
            out[k] = num(step[k]) if k in ("score", "value", "cost") else step[k]
    return out


def from_steps(steps, chosen, turn=None, threshold=None, potion_threshold=None, note=None):
    """把已经打好分的出牌/药水步骤收成 play、target、potion 三条记录（有哪条写哪条）。"""
    steps = list(steps or [])
    plays = [s for s in steps if s.get("kind") == "play"]
    pots = [s for s in steps if s.get("kind") == "potion"]
    ch = chosen or {}
    ch_kind = ch.get("kind")
    recs = []
    if plays:
        if ch_kind == "play":
            pch = _strip(ch)
            if pch.get("score") is None:
                for s in plays:
                    if _same(s, ch) and s.get("score") is not None:
                        pch["score"] = num(s.get("score"))
                        break
        elif ch_kind == "end":
            pch = {"id": "end_turn", "score": num(ch.get("score")) if ch.get("score") is not None else 0.0}
        else:
            pch = None
        rec = {"kind": "play", "chosen": pch, "candidates": [_strip(s) for s in plays]}
        if turn is not None:
            rec["turn"] = turn
        if threshold is not None:
            rec["threshold"] = num(threshold)
        if note and ch_kind == "play":
            rec["note"] = note
        recs.append(rec)
        if ch_kind == "play":
            same = [s for s in plays if s.get("id") == ch.get("id") and (ch.get("hand") is None or s.get("hand") == ch.get("hand"))]
            targeted = [s for s in same if s.get("target")]
            if ch.get("target") or len(targeted) > 1:
                recs.append({
                    "kind": "target", "card": ch.get("id"), "chosen": _strip(ch),
                    "candidates": [_strip(s) for s in (targeted or same)],
                    **({"turn": turn} if turn is not None else {}),
                })
    if pots or ch_kind == "potion":
        pch = _strip(ch) if ch_kind == "potion" else None
        rec = {"kind": "potion", "chosen": pch, "candidates": [_strip(s) for s in pots]}
        if turn is not None:
            rec["turn"] = turn
        if potion_threshold is not None:
            rec["threshold"] = num(potion_threshold)
        elif threshold is not None and ch_kind == "potion":
            rec["threshold"] = num(threshold)
        if note and ch_kind == "potion":
            rec["note"] = note
        recs.append(rec)
    return recs


class Log:
    def __init__(self):
        self.on = False
        self.rows = []
        self.seq = 0
        self.ctx = {}
        self.fight_ctx = {}
        self.fight_n = 0
        self.stack = []
        self._off = 0

    def configure(self, on=False, reset=True):
        self.on = bool(on)
        if reset:
            self.rows = []
            self.seq = 0
            self.ctx = {}
            self.fight_ctx = {}
            self.fight_n = 0
            self.stack = []
            self._off = 0
        return self.on

    def set_ctx(self, **kw):
        if not self.on:
            return
        self.ctx = {k: v for k, v in kw.items() if v is not None}

    def update_fight(self, **kw):
        if not self.on:
            return
        for k, v in kw.items():
            if v is not None:
                self.fight_ctx[k] = v

    def emit(self, rec):
        rec = dict(rec)
        chosen = rec.get("chosen")
        rec["candidates"] = top(rec.get("candidates") or [], chosen)
        self.seq += 1
        row = {"v": 1, "seq": self.seq}
        row.update(self.ctx)
        row.update(self.fight_ctx)
        row.update(rec)
        self.rows.append(row)

    def publish(self, records):
        if not self.on:
            return
        records = list(records or [])
        if self.stack:
            self.stack[-1] = records
        else:
            for rec in records:
                self.emit(rec)

    def align_action(self, chosen, note=None):
        """最外层若改了内层的选择（风格、强制先打），把已经记下来的 chosen 改成实际打出的。"""
        if not self.on or not self.stack or not chosen:
            return
        frame = self.stack[-1]
        kind = chosen.get("kind")
        if not frame:
            base = [chosen] if kind in ("play", "potion") else []
            frame.extend(from_steps(base, chosen, note=note))
            return
        changed = False
        for rec in frame:
            rk = rec.get("kind")
            if rk == "play" and kind in ("play", "end"):
                prev = rec.get("chosen") or {}
                new = {"id": "end_turn", "score": 0.0} if kind == "end" else _strip(chosen)
                if kind == "play" and new.get("score") is None:
                    for c in rec.get("candidates") or []:
                        if _same(c, chosen) and c.get("score") is not None:
                            new["score"] = num(c.get("score"))
                            break
                if prev.get("id") != new.get("id") or prev.get("target") != new.get("target"):
                    rec["chosen"] = new
                    changed = True
            elif rk == "target" and kind == "play":
                prev = rec.get("chosen") or {}
                if prev.get("id") != chosen.get("id") or prev.get("target") != chosen.get("target"):
                    rec["chosen"] = _strip(chosen)
                    rec["card"] = chosen.get("id")
                    changed = True
            elif rk == "potion" and kind == "potion":
                prev = rec.get("chosen") or {}
                if prev.get("id") != chosen.get("id") or prev.get("target") != chosen.get("target"):
                    rec["chosen"] = _strip(chosen)
                    changed = True
        if changed and note:
            frame[-1]["note"] = note

    def align_simple(self, kind, chosen, note=None):
        """奖励 / 商店：把这条记录的 chosen 改成最终拿走的东西。"""
        if not self.on or not self.stack:
            return
        frame = self.stack[-1]
        for rec in frame:
            if rec.get("kind") == kind:
                rec["chosen"] = _fill_scores(chosen, rec.get("candidates") or [])
                if note:
                    rec["note"] = note
                return
        if chosen is not None:
            frame.append({"kind": kind, "chosen": chosen, "candidates": _chosen_list(chosen), **({"note": note} if note else {})})

    def take(self):
        rows = self.rows
        self.rows = []
        return rows


LOG = Log()


def enabled():
    return LOG.on


def configure(on=False, reset=True):
    return LOG.configure(on=on, reset=reset)


def set_ctx(**kw):
    LOG.set_ctx(**kw)


def update_fight(**kw):
    LOG.update_fight(**kw)


def publish(records):
    LOG.publish(records)


def align_action(chosen, note=None):
    LOG.align_action(chosen, note=note)


def align_simple(kind, chosen, note=None):
    LOG.align_simple(kind, chosen, note=note)


def take():
    return LOG.take()


class scope:
    """最外层 ``with`` 结束时才把记录写出去。内层的 publish 先挂起，外层可以改写或替换。"""

    def __enter__(self):
        if not LOG.on:
            LOG._off += 1
            self._live = False
            return False
        self._live = True
        LOG.stack.append([])
        return len(LOG.stack) == 1

    def __exit__(self, et, ev, tb):
        if not self._live:
            LOG._off -= 1
            return False
        frame = LOG.stack.pop()
        if et is None and frame:
            if LOG.stack:
                LOG.stack[-1] = frame
            else:
                for rec in frame:
                    LOG.emit(rec)
        return False


@contextmanager
def fight(**kw):
    """一场战斗的上下文（层数、房间、序号）。关闭时只是 yield，不分配记录。"""
    if not LOG.on:
        yield
        return
    prev = dict(LOG.fight_ctx)
    LOG.fight_n += 1
    LOG.fight_ctx = {k: v for k, v in kw.items() if v is not None}
    LOG.fight_ctx["fight"] = LOG.fight_n
    try:
        yield
    finally:
        LOG.fight_ctx = prev


def write_jsonl(path, rows):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def peel(results, key="explain"):
    """从每局结果里取出说明行（没有这个键就不动）。"""
    rows = []
    for r in results:
        if isinstance(r, dict) and key in r:
            got = r.pop(key) or []
            rows.extend(got)
    return rows


def _combat_group_key(row):
    return (
        "combat",
        row.get("seed"),
        row.get("char"),
        row.get("deck"),
        row.get("act"),
        row.get("room"),
        row.get("fight"),
        row.get("floor"),
        row.get("index"),
    )


def combat_groups(rows):
    """按一场战斗把 play / target / potion 行分组，保持文件里的顺序。"""
    order = []
    buckets = {}
    for row in rows:
        if row.get("kind") not in ("play", "target", "potion"):
            continue
        key = _combat_group_key(row)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(row)
    return [(key, buckets[key]) for key in order]


def _fmt_cand(c):
    bits = []
    name = c.get("name") or c.get("id")
    if name is not None:
        bits.append(str(name))
    if c.get("target"):
        bits.append("→ " + str(c["target"]))
    label = " ".join(bits) if bits else "?"
    if c.get("picked"):
        label += " ←"
    score = c.get("score")
    if score is None:
        return f"| {label} | — |"
    return f"| {label} | {score} |"


def _fmt_chosen(ch):
    if ch is None:
        return "（不选 / none）"
    if isinstance(ch, list):
        if not ch:
            return "（不买 / none）"
        parts = []
        for c in ch:
            name = c.get("name") or c.get("id")
            if c.get("score") is not None:
                parts.append(f"{name} ({c.get('score')})")
            else:
                parts.append(str(name))
        return ", ".join(parts)
    name = ch.get("name") or ch.get("id") or "?"
    if ch.get("target"):
        name = f"{name} → {ch['target']}"
    if ch.get("score") is not None:
        return f"{name} ({ch['score']})"
    return str(name)


_KIND = {
    "play": "出牌 / play",
    "target": "目标 / target",
    "potion": "药水 / potion",
    "reward": "奖励 / reward",
    "shop": "商店 / shop",
}


def _section(row):
    kind = _KIND.get(row.get("kind"), row.get("kind"))
    turn = row.get("turn")
    head = f"### {kind}"
    if turn is not None:
        head += f" — turn {turn}"
    lines = [head, "", f"选择 / chosen: **{_fmt_chosen(row.get('chosen'))}**"]
    if row.get("card") and row.get("kind") == "target":
        lines.append(f"牌 / card: {row['card']}")
    if row.get("threshold") is not None:
        lines.append(f"门槛 / threshold: {row['threshold']}")
    if row.get("note"):
        lines.append(f"备注 / note: {row['note']}")
    lines.append("")
    lines.append("| 候选 / candidate | 分数 / score |")
    lines.append("| --- | --- |")
    cands = row.get("candidates") or []
    if not cands:
        lines.append("| — | — |")
    else:
        for c in cands:
            lines.append(_fmt_cand(c))
    lines.append("")
    return "\n".join(lines)


def _where(rows):
    r = rows[0] if rows else {}
    bits = []
    if r.get("seed") is not None:
        bits.append(f"seed {r['seed']}")
    if r.get("char"):
        bits.append(str(r["char"]))
    if r.get("deck"):
        bits.append(str(r["deck"]))
    if r.get("act") is not None:
        bits.append(f"act {r['act']}")
    if r.get("floor") is not None:
        bits.append(f"floor {r['floor']}")
    if r.get("room"):
        bits.append(str(r["room"]))
    if r.get("encounter"):
        bits.append(str(r["encounter"]))
    if r.get("fight") is not None:
        bits.append(f"fight {r['fight']}")
    return " · ".join(bits)


def render_fight(rows, index=0, seed=None):
    """把一场战斗渲染成 Markdown。``index`` 是过滤种子之后的第几场（从 0 开始）。"""
    rows = list(rows)
    if seed:
        rows = [r for r in rows if str(r.get("seed")) == str(seed)]
    groups = combat_groups(rows)
    if not groups:
        return "# 说明日志 / explanation\n\n这场记录里没有战斗决策。 / No combat decisions in this log.\n"
    if index < 0 or index >= len(groups):
        raise IndexError(f"fight {index} out of range (0..{len(groups) - 1})")
    _key, fight_rows = groups[index]
    lines = [f"# 一场战斗 / one fight", "", _where(fight_rows), ""]
    for row in fight_rows:
        lines.append(_section(row))
    floor = fight_rows[0].get("floor")
    seed_v = fight_rows[0].get("seed")
    if floor is not None:
        extra = [r for r in rows if r.get("kind") in ("reward", "shop") and r.get("floor") == floor
                 and r.get("seed") == seed_v]
        if extra:
            lines.append("## 这一层的奖励和商店 / rewards and shop on this floor")
            lines.append("")
            for row in extra:
                lines.append(_section(row))
    return "\n".join(lines).rstrip() + "\n"


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out
