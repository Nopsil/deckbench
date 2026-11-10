"""两次已经跑完的战斗实验：按格子和按卡算差值。不新开模拟，不写文件。

格子对齐键是（卡组 id，幕，房间）。两边没有同一个卡组 id 时，
同一幕、同一房间、且这一侧只有一套牌，才按幕和房间配对（两套不同的牌对打）。
差值一律是 B − A。
胜率和超时是比例：两比例 z 检验，并附上 Wilson 区间以及两个区间是否重叠。
平均回合、掉血、每回合输出，在两侧都有逐场记录时用 Welch t 检验。
只有 cells.csv 里的平均数时，差值照给，显著性为 null（没有方差，不能做 Welch）。
单卡使用次数同样：有逐场次数就做 Welch，否则只给每场使用的差。
效率倍数是合计之后的比值（和报告里的 cards.csv 同一公式），只给差，不做 t 检验。
探针房间（「探针」）的单卡不计入，和报告汇总一致；格子仍保留。
"""
import csv
import json
import math
import os
from collections import defaultdict

from sts2sim.report import ratio
from sts2sim.stats import min_sample_fields, proportion_compare_fields, welch_ttest

PROBE_ROOM = "探针"
ALPHA = 0.05


class CompareError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _act(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value == int(value):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if math.isfinite(number) and number == int(number):
        return int(number)
    return text


def _read_text(path):
    from sts2sim.saveimport import MAX_BYTES
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise CompareError("unreadable") from exc
    if size > MAX_BYTES:
        raise CompareError("too_big")
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise CompareError("unreadable") from exc
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompareError("not_json", line=1) from exc


def _jsonl(text):
    rows = []
    for index, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise CompareError("not_json", line=index) from exc
        if not isinstance(row, dict):
            raise CompareError("not_json", line=index)
        rows.append(row)
    return rows


def _csv_rows(path):
    text = _read_text(path)
    try:
        return list(csv.DictReader(text.splitlines()))
    except csv.Error as exc:
        raise CompareError("unreadable") from exc


def _card_parts(value):
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    plays, dmg, blk, energy = (_num(value[0]), _num(value[1]), _num(value[2]), _num(value[3]))
    if None in (plays, dmg, blk, energy):
        return None
    return plays, dmg, blk, energy


def _blank_cell():
    return {"n": 0, "wins": 0.0, "timeouts": 0.0, "turns": [], "hp_loss": [], "dpt": []}


def _from_raw(text):
    cells = defaultdict(_blank_cell)
    names = {}
    fights = defaultdict(list)
    seen = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    for row in _jsonl(text):
        result = row.get("result")
        if result not in ("win", "loss", "timeout", "loop"):
            continue
        deck = row.get("deck")
        act = _act(row.get("act"))
        room = row.get("room")
        if deck is None or act is None or room is None:
            continue
        deck = str(deck)
        room = str(room)
        names.setdefault(deck, deck)
        cell = cells[(deck, act, room)]
        cell["n"] += 1
        if result == "win":
            cell["wins"] += 1.0
        if result == "timeout":
            cell["timeouts"] += 1.0
        turns = _num(row.get("turns"))
        if turns is not None:
            cell["turns"].append(turns)
            dmg = _num(row.get("dmg_total"))
            cell["dpt"].append((0.0 if dmg is None else dmg) / max(1.0, turns))
        hp = _num(row.get("hp_lost"))
        if hp is not None:
            cell["hp_loss"].append(hp)
        if room == PROBE_ROOM:
            continue
        bucket = fights[deck]
        index = len(bucket)
        bucket.append({})
        cards = row.get("cards") if isinstance(row.get("cards"), dict) else {}
        for name, raw in cards.items():
            parts = _card_parts(raw)
            if parts is None:
                continue
            card = str(name)
            bucket[index][card] = parts[0]
            total = seen[(deck, card)]
            total[0] += parts[0]
            total[1] += parts[1]
            total[2] += parts[2]
            total[3] += parts[3]
    card_rows = {}
    for (deck, card), (plays, dmg, blk, energy) in seen.items():
        samples = [float(fight.get(card, 0.0)) for fight in fights[deck]]
        count = len(samples)
        card_rows[(deck, card)] = {
            "plays": plays,
            "per_fight": (plays / count) if count else None,
            "samples": samples,
            "efficiency": ratio(dmg, blk, energy, plays),
            "fights": count,
        }
    return {"source": "raw", "names": names, "cells": dict(cells), "cards": card_rows, "fights": dict(fights)}


def _from_csv(folder):
    cells = {}
    names = {}
    cells_path = os.path.join(folder, "cells.csv")
    if os.path.isfile(cells_path):
        for row in _csv_rows(cells_path):
            deck = str(row.get("卡组id") or "").strip()
            act = _act(row.get("幕"))
            room = str(row.get("房间") or "").strip()
            n = _num(row.get("场数"))
            if not deck or act is None or not room or n is None or n <= 0:
                continue
            n = int(n)
            name = str(row.get("卡组") or "").strip() or deck
            names[deck] = name
            win = _num(row.get("胜率%"))
            timeout = _num(row.get("超时%"))
            cells[(deck, act, room)] = {
                "n": n,
                "wins": None if win is None else win / 100.0 * n,
                "timeouts": None if timeout is None else timeout / 100.0 * n,
                "turns": None,
                "hp_loss": None,
                "dpt": None,
                "turns_mean": _num(row.get("平均回合")),
                "hp_loss_mean": _num(row.get("平均掉血")),
                "dpt_mean": _num(row.get("每回合输出")),
            }
    cards = {}
    cards_path = os.path.join(folder, "cards.csv")
    deck_fights = defaultdict(int)
    for (deck, _act_value, room), cell in cells.items():
        if room != PROBE_ROOM:
            deck_fights[deck] += cell["n"]
    if os.path.isfile(cards_path):
        for row in _csv_rows(cards_path):
            deck = str(row.get("卡组id") or "").strip()
            card = str(row.get("卡牌/来源") or "").strip()
            if not deck or not card:
                continue
            name = str(row.get("卡组") or "").strip()
            if name:
                names.setdefault(deck, name)
            plays = _num(row.get("总使用次数"))
            per_fight = _num(row.get("每场使用"))
            efficiency = _num(row.get("效率倍数(原版中位=1)"))
            if efficiency is None:
                dmg = _num(row.get("每次伤害"))
                blk = _num(row.get("每次格挡"))
                energy = _num(row.get("每次付费"))
                if None not in (plays, dmg, blk, energy) and plays > 0:
                    efficiency = ratio(dmg * plays, blk * plays, energy * plays, plays)
            fights = deck_fights.get(deck) or 0
            cards[(deck, card)] = {
                "plays": plays,
                "per_fight": per_fight,
                "samples": None,
                "efficiency": efficiency,
                "fights": fights or None,
            }
    if not cells and not cards:
        raise CompareError("no_data")
    return {"source": "csv", "names": names, "cells": cells, "cards": cards, "fights": {}}


def _load_side(folder):
    if not folder or not os.path.isdir(folder):
        raise CompareError("no_data")
    raw_path = os.path.join(folder, "raw.jsonl")
    cells_path = os.path.join(folder, "cells.csv")
    cards_path = os.path.join(folder, "cards.csv")
    if not any(os.path.isfile(path) for path in (raw_path, cells_path, cards_path)):
        raise CompareError("no_data")
    if os.path.isfile(raw_path):
        side = _from_raw(_read_text(raw_path))
        if os.path.isfile(cells_path):
            try:
                named = _from_csv(folder)
            except CompareError:
                named = None
            if named:
                for deck, name in named["names"].items():
                    if name and name != deck:
                        side["names"][deck] = name
        return side
    return _from_csv(folder)


def _sig(p_value):
    if p_value is None:
        return None
    return bool(p_value < ALPHA)


def _overlap(lo_a, hi_a, lo_b, hi_b):
    if None in (lo_a, hi_a, lo_b, hi_b):
        return None
    return not (hi_a < lo_b or hi_b < lo_a)


def _proportion_metric(name, k_a, n_a, k_b, n_b):
    n_a = int(n_a or 0)
    n_b = int(n_b or 0)
    usable = n_a > 0 and n_b > 0 and k_a is not None and k_b is not None
    fields = proportion_compare_fields(k_a if usable else 0, n_a if usable else 0, k_b if usable else 0, n_b if usable else 0)
    warned = min_sample_fields(n_a, n_b)
    if not usable:
        return {
            "metric": name,
            "a": None,
            "b": None,
            "delta": None,
            "method": "two_proportion_z",
            "p_value": None,
            "z": None,
            "significant": None,
            "wilson_overlap": None,
            "a_ci_low": None,
            "a_ci_high": None,
            "b_ci_low": None,
            "b_ci_high": None,
            "ci_method": None,
            "k_a": k_a,
            "k_b": k_b,
            "n_a": n_a,
            "n_b": n_b,
            **warned,
        }
    a = k_a / n_a
    b = k_b / n_b
    return {
        "metric": name,
        "a": a,
        "b": b,
        "delta": b - a,
        "method": "two_proportion_z",
        "p_value": fields["p_value"],
        "z": fields["z"],
        "significant": _sig(fields["p_value"]),
        "wilson_overlap": _overlap(fields["a_ci_low"], fields["a_ci_high"], fields["b_ci_low"], fields["b_ci_high"]),
        "a_ci_low": fields["a_ci_low"],
        "a_ci_high": fields["a_ci_high"],
        "b_ci_low": fields["b_ci_low"],
        "b_ci_high": fields["b_ci_high"],
        "ci_method": fields["ci_method"],
        "k_a": k_a,
        "k_b": k_b,
        "n_a": n_a,
        "n_b": n_b,
        "min_n": fields["min_n"],
        "sample_warning": fields["sample_warning"],
        "sample_warning_code": fields["sample_warning_code"],
        "sample_warning_text": fields["sample_warning_text"],
    }


def _mean(values):
    if not values:
        return None
    return sum(values) / len(values)


def _welch_metric(name, xs, ys):
    xs = list(xs or [])
    ys = list(ys or [])
    test = welch_ttest(xs, ys)
    a = _mean(xs)
    b = _mean(ys)
    delta = None if a is None or b is None else b - a
    warned = min_sample_fields(len(xs), len(ys))
    return {
        "metric": name,
        "a": a,
        "b": b,
        "delta": delta,
        "method": "welch",
        "p_value": test["p_value"],
        "t": test["t"],
        "df": test["df"],
        "significant": _sig(test["p_value"]),
        "n_a": len(xs),
        "n_b": len(ys),
        **warned,
    }


def _means_metric(name, a, b, n_a, n_b):
    delta = None if a is None or b is None else b - a
    warned = min_sample_fields(int(n_a or 0), int(n_b or 0))
    return {
        "metric": name,
        "a": a,
        "b": b,
        "delta": delta,
        "method": "means_only",
        "p_value": None,
        "significant": None,
        "n_a": int(n_a or 0),
        "n_b": int(n_b or 0),
        **warned,
    }


def _continuous(name, left, right, list_key, mean_key):
    xs = left.get(list_key)
    ys = right.get(list_key)
    if isinstance(xs, list) and isinstance(ys, list):
        return _welch_metric(name, xs, ys)
    a = _mean(xs) if isinstance(xs, list) else left.get(mean_key)
    b = _mean(ys) if isinstance(ys, list) else right.get(mean_key)
    n_a = len(xs) if isinstance(xs, list) else left.get("n") or 0
    n_b = len(ys) if isinstance(ys, list) else right.get("n") or 0
    return _means_metric(name, a, b, n_a, n_b)


def _cell_row(key, left, right, names, other=None):
    deck, act, room = key
    label = names.get(deck) or deck
    deck_id = deck
    if other is not None and other != deck:
        label = f"{label} / {names.get(other) or other}"
        deck_id = f"{deck}/{other}"
    metrics = {
        "win": _proportion_metric("win", left.get("wins"), left.get("n"), right.get("wins"), right.get("n")),
        "timeout": _proportion_metric(
            "timeout", left.get("timeouts"), left.get("n"), right.get("timeouts"), right.get("n"),
        ),
        "turns": _continuous("turns", left, right, "turns", "turns_mean"),
        "hp_loss": _continuous("hp_loss", left, right, "hp_loss", "hp_loss_mean"),
        "dpt": _continuous("dpt", left, right, "dpt", "dpt_mean"),
    }
    return {
        "deck_id": deck_id,
        "deck": label,
        "act": act,
        "room": room,
        "n_a": int(left.get("n") or 0),
        "n_b": int(right.get("n") or 0),
        "metrics": metrics,
    }


def _missing_card(fights, samples):
    count = fights or 0
    return {
        "plays": 0.0,
        "per_fight": 0.0 if count else None,
        "samples": [0.0] * count if samples else None,
        "efficiency": None,
        "fights": count or None,
    }


def _card_row(key, left, right, names, other=None):
    deck, card = key
    label = names.get(deck) or deck
    deck_id = deck
    if other is not None and other != deck:
        label = f"{label} / {names.get(other) or other}"
        deck_id = f"{deck}/{other}"
    use_samples = isinstance(left.get("samples"), list) and isinstance(right.get("samples"), list)
    if use_samples:
        usage = _welch_metric("usage", left["samples"], right["samples"])
        method = "welch"
        p_value = usage["p_value"]
        significant = usage["significant"]
        n_a = usage["n_a"]
        n_b = usage["n_b"]
        warned = {k: usage[k] for k in ("min_n", "sample_warning", "sample_warning_code", "sample_warning_text")}
    else:
        n_a = int(left.get("fights") or 0)
        n_b = int(right.get("fights") or 0)
        warned = min_sample_fields(n_a, n_b)
        method = "means_only"
        p_value = None
        significant = None
    a_per = left.get("per_fight")
    b_per = right.get("per_fight")
    a_eff = left.get("efficiency")
    b_eff = right.get("efficiency")
    return {
        "deck_id": deck_id,
        "deck": label,
        "card": card,
        "n_a": n_a,
        "n_b": n_b,
        "a_plays": left.get("plays"),
        "b_plays": right.get("plays"),
        "a_per_fight": a_per,
        "b_per_fight": b_per,
        "usage_delta": None if a_per is None or b_per is None else b_per - a_per,
        "usage_method": method,
        "usage_p_value": p_value,
        "usage_significant": significant,
        "a_efficiency": a_eff,
        "b_efficiency": b_eff,
        "efficiency_delta": None if a_eff is None or b_eff is None else b_eff - a_eff,
        **warned,
    }


def _sort_key(key):
    deck, act, room = key
    act_key = (0, act) if isinstance(act, int) else (1, str(act))
    return (deck, act_key, room)


def _place_key(place):
    act, room = place
    act_key = (0, act) if isinstance(act, int) else (1, str(act))
    return (act_key, str(room))


def _group_places(cells):
    grouped = {}
    for (deck, act, room), cell in cells.items():
        grouped.setdefault((act, room), []).append((deck, cell))
    return grouped


def _place_pairs(left, right):
    """卡组 id 对不上时，按幕和房间配。这一侧有不止一套牌就跳过，不猜哪套对哪套。"""
    grouped_a = _group_places(left["cells"])
    grouped_b = _group_places(right["cells"])
    pairs = []
    for place in sorted(set(grouped_a) & set(grouped_b), key=_place_key):
        side_a = grouped_a[place]
        side_b = grouped_b[place]
        if len(side_a) != 1 or len(side_b) != 1:
            continue
        deck_a, cell_a = side_a[0]
        deck_b, cell_b = side_b[0]
        pairs.append(((deck_a, place[0], place[1]), (deck_b, place[0], place[1]), cell_a, cell_b))
    return pairs


def _shared_cards(shared, left, right, names):
    decks = {deck for deck, _act_value, _room in shared}
    decks |= {deck for deck, _card in left["cards"]} & {deck for deck, _card in right["cards"]}
    fights_a = {deck: len(rows) for deck, rows in left.get("fights", {}).items()}
    fights_b = {deck: len(rows) for deck, rows in right.get("fights", {}).items()}
    card_keys = sorted(
        ({key for key in left["cards"] if key[0] in decks} | {key for key in right["cards"] if key[0] in decks}),
        key=lambda item: (item[0], item[1]),
    )
    cards = []
    for key in card_keys:
        deck = key[0]
        sample_a = isinstance(left["cards"].get(key, {}).get("samples"), list) or left["source"] == "raw"
        sample_b = isinstance(right["cards"].get(key, {}).get("samples"), list) or right["source"] == "raw"
        side_a = left["cards"].get(key) or _missing_card(fights_a.get(deck, 0), sample_a and sample_b)
        side_b = right["cards"].get(key) or _missing_card(fights_b.get(deck, 0), sample_a and sample_b)
        if not (side_a.get("plays") or side_b.get("plays")):
            continue
        cards.append(_card_row(key, side_a, side_b, names))
    return cards


def _cross_cards(pairs, left, right, names):
    if not pairs:
        return []
    deck_a = pairs[0][0][0]
    deck_b = pairs[0][1][0]
    if any(key_a[0] != deck_a or key_b[0] != deck_b for key_a, key_b, _cell_a, _cell_b in pairs):
        return []
    fights_a = len(left.get("fights", {}).get(deck_a, []))
    fights_b = len(right.get("fights", {}).get(deck_b, []))
    names_a = {card for deck, card in left["cards"] if deck == deck_a}
    names_b = {card for deck, card in right["cards"] if deck == deck_b}
    cards = []
    for card in sorted(names_a | names_b):
        key_a = (deck_a, card)
        key_b = (deck_b, card)
        sample_a = isinstance(left["cards"].get(key_a, {}).get("samples"), list) or left["source"] == "raw"
        sample_b = isinstance(right["cards"].get(key_b, {}).get("samples"), list) or right["source"] == "raw"
        side_a = left["cards"].get(key_a) or _missing_card(fights_a, sample_a and sample_b)
        side_b = right["cards"].get(key_b) or _missing_card(fights_b, sample_a and sample_b)
        if not (side_a.get("plays") or side_b.get("plays")):
            continue
        cards.append(_card_row(key_a, side_a, side_b, names, other=deck_b))
    return cards


def compare_dirs(dir_a, dir_b):
    """比较两个战斗输出目录（含 raw.jsonl，或 cells.csv / cards.csv）。"""
    left = _load_side(dir_a)
    right = _load_side(dir_b)
    names = dict(left["names"])
    names.update({deck: name for deck, name in right["names"].items() if name})
    shared = sorted(set(left["cells"]) & set(right["cells"]), key=_sort_key)
    if shared:
        cells = [_cell_row(key, left["cells"][key], right["cells"][key], names) for key in shared]
        cards = _shared_cards(shared, left, right, names)
    else:
        pairs = _place_pairs(left, right)
        cells = [
            _cell_row(key_a, cell_a, cell_b, names, other=key_b[0])
            for key_a, key_b, cell_a, cell_b in pairs
        ]
        cards = _cross_cards(pairs, left, right, names)
    return _finite({
        "sources": {"a": left["source"], "b": right["source"]},
        "cells": cells,
        "cards": cards,
    })
