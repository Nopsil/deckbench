"""一份已保存牌组的单卡贡献：留一法。

基线照预设打。每一种牌再打一份少一张的变体，需要时也可以多一张。
遭遇、种子、回合上限都和基线相同。卡组 id 也不改，战斗仍走原来的播种。
全部变体加起来不超过 400 场：默认按比例把每种遭遇的场数缩小；
``scale`` 为假，或者缩到每种变体一场仍放不下，就拒绝。

胜率差用 Wilson 区间。任一侧局数小于 ``MIN_N``，或者两侧区间重叠，
记成样本太小或噪声太大。不改模拟器的出牌。

*Leave-one-out card impact for a saved deck. The baseline and one variant per
unique card (one copy removed, and optionally one copy added) share encounters,
seed and turn cap. The deck id stays the same, so the runner's seeding stays
the same. The whole ablation is capped at 400 fights. Win-rate deltas use a
Wilson interval. A side under ``MIN_N``, or overlapping intervals, is flagged
too small or noisy. Simulator play is unchanged.*
"""
from __future__ import annotations

from sts2sim.deckpresets import (
    _BANNED_FIELDS,
    _ID,
    MAX_COPIES,
    MAX_FIGHTS_TOTAL,
    DeckPresetError,
    _clean_name,
    _encounter_override,
    _load_modset,
    _load_user_preset,
    _optional_seed,
    _pool,
    _reject_path,
    _stored_agent,
    _stored_encounters,
    _stored_seed,
    _stored_turns,
    _tokens,
    format_deck_tokens,
    parse_deck_tokens,
    preset_turns,
    resolve_encounters,
)
from sts2sim.stats import MIN_N, min_sample_fields, wilson_interval


def _flag(payload, field, default):
    if not isinstance(payload, dict) or field not in payload or payload[field] is None:
        return default
    value = payload[field]
    if not isinstance(value, bool):
        raise DeckPresetError("bad_type", field=field, expected="boolean")
    return value


def _deck_id(deck_id):
    if not isinstance(deck_id, str) or not deck_id.strip():
        raise DeckPresetError("missing", field="deck")
    text = deck_id.strip()
    _reject_path(text)
    if not _ID.match(text):
        raise DeckPresetError("bad_id")
    return text


def allocate_fights(encounters, target):
    """把 ``target`` 场按原来的场数比例分回每种遭遇。最大余数法。0 场的遭遇去掉。"""
    if not encounters:
        return []
    weights = [int(row["fights"]) for row in encounters]
    total = sum(weights)
    if total < 1 or target >= total:
        return [dict(row) for row in encounters]
    if target < 1:
        return []
    raw = [weight * target / total for weight in weights]
    floors = [int(piece) for piece in raw]
    left = target - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: (raw[i] - floors[i], weights[i]), reverse=True)
    for index in order:
        if left <= 0:
            break
        floors[index] += 1
        left -= 1
    out = []
    for row, count in zip(encounters, floors):
        if count < 1:
            continue
        copied = dict(row)
        copied["fights"] = count
        out.append(copied)
    return out


def scale_plan(encounters, n_variants, *, scale=True, cap=MAX_FIGHTS_TOTAL):
    """全体变体合计不超过 ``cap`` 场。

    返回 ``(encounters, fights_each, total, scaled)``。
    缩完仍至少要给每个变体 1 场，否则 ``too_many_fights``。
    """
    if isinstance(n_variants, bool) or not isinstance(n_variants, int) or n_variants < 1:
        raise DeckPresetError("ablation")
    rows = [dict(row) for row in encounters]
    base = sum(int(row["fights"]) for row in rows)
    if base < 1:
        raise DeckPresetError("no_encounter")
    total = n_variants * base
    if total <= cap:
        return rows, base, total, False
    if not scale:
        raise DeckPresetError("too_many_fights", n=cap)
    each = cap // n_variants
    if each < 1:
        raise DeckPresetError("too_many_fights", n=cap)
    scaled = allocate_fights(rows, each)
    if not scaled:
        raise DeckPresetError("too_many_fights", n=cap)
    per = sum(int(row["fights"]) for row in scaled)
    if per < 1 or n_variants * per > cap:
        raise DeckPresetError("too_many_fights", n=cap)
    return scaled, per, n_variants * per, True


def _catalog_card(mod_name, card_id):
    fallback = None
    for card in _pool():
        if card.get("id") != card_id:
            continue
        if card.get("mod") == mod_name:
            return card
        if fallback is None:
            fallback = card
    return fallback


def _names(mod_name, card_id):
    card = _catalog_card(mod_name, card_id)
    if not isinstance(card, dict):
        return {"name": card_id, "name_zh": "", "name_en": ""}
    return {
        "name": card.get("name") or card_id,
        "name_zh": card.get("name_zh") or "",
        "name_en": card.get("name_en") or "",
    }


def _variant(change, card_id, upgrade, count, baseline_count, lines, names):
    return {
        "role": "baseline" if change == "baseline" else "variant",
        "change": change,
        "card_id": card_id,
        "upgrade": bool(upgrade),
        "count": count,
        "baseline_count": baseline_count,
        "cards": format_deck_tokens(lines),
        "name": names.get("name") or card_id or "",
        "name_zh": names.get("name_zh") or "",
        "name_en": names.get("name_en") or "",
    }


def _variants(modset, mod_name, lines, plus):
    """基线，每种牌少一张，以及可选的多一张。少一张会把牌组打空的，整份拒绝。"""
    baseline = _tokens(modset, mod_name, lines)
    variants = [_variant("baseline", "", False, sum(count for _c, _u, count in lines), None, lines,
                         {"name": "", "name_zh": "", "name_en": ""})]
    variants[0]["cards"] = baseline
    skipped = []
    removable = 0
    for index, (card_id, upgrade, count) in enumerate(lines):
        names = _names(mod_name, card_id)
        removed = []
        for cursor, row in enumerate(lines):
            cid, up, copies = row
            if cursor == index:
                copies -= 1
            if copies > 0:
                removed.append((cid, up, copies))
        if removed:
            variants.append(_variant(
                "remove", card_id, upgrade, count - 1, count, removed, names,
            ))
            variants[-1]["cards"] = _tokens(modset, mod_name, removed)
            removable += 1
        if not plus:
            continue
        if count >= MAX_COPIES:
            skipped.append({
                "card_id": card_id,
                "upgrade": upgrade,
                "change": "add",
                "reason": "count",
                "name": names["name"],
                "name_zh": names["name_zh"],
                "name_en": names["name_en"],
            })
            continue
        added = []
        for cursor, row in enumerate(lines):
            cid, up, copies = row
            if cursor == index:
                copies += 1
            added.append((cid, up, copies))
        variants.append(_variant("add", card_id, upgrade, count + 1, count, added, names))
        variants[-1]["cards"] = _tokens(modset, mod_name, added)
    if removable < 1:
        raise DeckPresetError("ablation")
    return variants, skipped


def plan_ablation(deck_id, payload=None):
    """排好基线和变体。不写文件，也不开跑。"""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise DeckPresetError("bad_type", field="body", expected="object")
    if any(key in payload for key in _BANNED_FIELDS):
        raise DeckPresetError("path")
    deck_id = _deck_id(deck_id)
    plus = _flag(payload, "plus", False)
    scale = _flag(payload, "scale", True)
    exp = _load_user_preset(deck_id)
    info = exp.get("user_deck") if isinstance(exp.get("user_deck"), dict) else {}
    mod_name = info.get("mod")
    if not isinstance(mod_name, str):
        raise DeckPresetError("preset")
    lines = parse_deck_tokens(info.get("cards") if isinstance(info.get("cards"), list) else [])
    if not lines:
        raise DeckPresetError("empty")
    modset, _shipped = _load_modset(mod_name)
    variants, skipped = _variants(modset, mod_name, lines, plus)
    if _encounter_override(payload):
        chosen = resolve_encounters(payload, allow_default=False)
        if not chosen:
            raise DeckPresetError("no_encounter")
    else:
        chosen = _stored_encounters(exp)
    if "max_turns" in payload and payload.get("max_turns") is not None:
        turns = preset_turns({"max_turns": payload.get("max_turns")}, chosen)
    else:
        turns = _stored_turns(exp, chosen)
    if "seed" in payload and payload.get("seed") is not None:
        seed = _optional_seed({"seed": payload.get("seed")})
    else:
        seed = _stored_seed(exp)
    agent = _stored_agent(exp)
    encounters, per, total, scaled = scale_plan(chosen, len(variants), scale=scale)
    return {
        "deck": deck_id,
        "title": _clean_name(exp.get("title")) or deck_id,
        "mod": mod_name,
        "plus": plus,
        "scale": scale,
        "scaled": scaled,
        "seed": seed,
        "agent": agent,
        "max_turns": turns,
        "encounters": [{"id": row["id"], "fights": int(row["fights"])} for row in encounters],
        "fights": per,
        "total_fights": total,
        "cap": MAX_FIGHTS_TOTAL,
        "min_n": MIN_N,
        "variants": variants,
        "skipped": skipped,
    }


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def fight_stats(rows):
    """逐场记录上的胜率、平均掉血、平均回合。缺字段的那一项不进平均。"""
    count = 0
    wins = 0
    hp = []
    turns = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        count += 1
        if row.get("result") == "win":
            wins += 1
        lost = _number(row.get("hp_lost"))
        if lost is not None:
            hp.append(lost)
        turn = _number(row.get("turns"))
        if turn is not None:
            turns.append(turn)
    return {
        "n": count,
        "wins": wins,
        "win_rate": (wins / count) if count else None,
        "hp_lost": (sum(hp) / len(hp)) if hp else None,
        "turns": (sum(turns) / len(turns)) if turns else None,
    }


def _delta(base, variant):
    if base is None or variant is None:
        return None
    return variant - base


def _intervals_overlap(left_lo, left_hi, right_lo, right_hi):
    if None in (left_lo, left_hi, right_lo, right_hi):
        return None
    return not (left_hi < right_lo or right_hi < left_lo)


def _effect(change, delta, higher_is_better):
    if delta is None:
        return None
    if delta == 0:
        return "flat"
    if change == "add":
        helpful = delta > 0 if higher_is_better else delta < 0
    else:
        helpful = delta < 0 if higher_is_better else delta > 0
    return "helps" if helpful else "hurts"


def impact_row(spec, baseline_fights, variant_fights):
    """变体减基线。``noisy`` 在样本小于 ``MIN_N`` 或 Wilson 区间重叠时为真。"""
    base = fight_stats(baseline_fights)
    variant = fight_stats(variant_fights)
    base_lo, base_hi = wilson_interval(base["wins"], base["n"])
    var_lo, var_hi = wilson_interval(variant["wins"], variant["n"])
    overlap = _intervals_overlap(base_lo, base_hi, var_lo, var_hi)
    sample = min_sample_fields(base["n"], variant["n"])
    if sample["sample_warning"]:
        reason = "too_small"
    elif overlap:
        reason = "wilson_overlap"
    else:
        reason = None
    delta_win = _delta(base["win_rate"], variant["win_rate"])
    delta_hp = _delta(base["hp_lost"], variant["hp_lost"])
    delta_turns = _delta(base["turns"], variant["turns"])
    change = spec.get("change") or "remove"
    return {
        "card_id": spec.get("card_id") or "",
        "upgrade": bool(spec.get("upgrade")),
        "change": change,
        "count": spec.get("count"),
        "baseline_count": spec.get("baseline_count"),
        "name": spec.get("name") or spec.get("card_id") or "",
        "name_zh": spec.get("name_zh") or "",
        "name_en": spec.get("name_en") or "",
        "run": spec.get("run") or spec.get("id") or "",
        "n": variant["n"],
        "n_baseline": base["n"],
        "wins": variant["wins"],
        "wins_baseline": base["wins"],
        "win_rate": variant["win_rate"],
        "win_rate_baseline": base["win_rate"],
        "hp_lost": variant["hp_lost"],
        "hp_lost_baseline": base["hp_lost"],
        "turns": variant["turns"],
        "turns_baseline": base["turns"],
        "delta_win": delta_win,
        "delta_hp_lost": delta_hp,
        "delta_turns": delta_turns,
        "win_effect": _effect(change, delta_win, True),
        "hp_effect": _effect(change, delta_hp, False),
        "win_ci_low": var_lo,
        "win_ci_high": var_hi,
        "baseline_ci_low": base_lo,
        "baseline_ci_high": base_hi,
        "ci_method": "wilson" if var_lo is not None and base_lo is not None else None,
        "wilson_overlap": overlap,
        "noisy": reason is not None,
        "noisy_reason": reason,
        **sample,
    }


def _baseline_block(spec, fights):
    stats = fight_stats(fights)
    if stats["n"] < 1:
        return None
    lo, hi = wilson_interval(stats["wins"], stats["n"])
    return {
        "run": spec.get("run") or spec.get("id") or "",
        **stats,
        "win_ci_low": lo,
        "win_ci_high": hi,
        "ci_method": "wilson" if lo is not None else None,
        **min_sample_fields(stats["n"]),
    }


def build_report(plan, outcomes, *, status, partial):
    """``outcomes`` 和 ``plan['variants']`` 对齐。每一项是 ``{fights, status, id}`` 或 None。"""
    variants = plan.get("variants") or []
    finished = []
    for spec, outcome in zip(variants, outcomes):
        if not isinstance(outcome, dict):
            finished.append(None)
            continue
        item = dict(spec)
        item["fights"] = outcome.get("fights") or []
        item["status"] = outcome.get("status") or ""
        item["run"] = outcome.get("id") or ""
        item["id"] = outcome.get("id") or ""
        finished.append(item)
    baseline_item = next((item for item in finished if item and item.get("change") == "baseline"), None)
    baseline_fights = baseline_item["fights"] if baseline_item else []
    rows = []
    if baseline_item and fight_stats(baseline_fights)["n"] > 0:
        for item in finished:
            if not item or item.get("change") in (None, "baseline"):
                continue
            if fight_stats(item["fights"])["n"] < 1:
                continue
            rows.append(impact_row(item, baseline_fights, item["fights"]))
    runs = []
    for spec, outcome in zip(variants, outcomes):
        runs.append({
            "id": (outcome or {}).get("id") or "",
            "role": spec.get("role"),
            "change": spec.get("change"),
            "card_id": spec.get("card_id") or "",
            "upgrade": bool(spec.get("upgrade")),
            "status": (outcome or {}).get("status") or "queued",
        })
    return {
        "ok": True,
        "method": "leave_one_out",
        "deck": plan.get("deck"),
        "title": plan.get("title") or "",
        "status": status,
        "partial": bool(partial),
        "plus": bool(plan.get("plus")),
        "scale": bool(plan.get("scale", True)),
        "scaled": bool(plan.get("scaled")),
        "seed": plan.get("seed"),
        "agent": plan.get("agent"),
        "max_turns": plan.get("max_turns"),
        "encounters": [row["id"] for row in plan.get("encounters") or []],
        "fights": plan.get("fights"),
        "total_fights": plan.get("total_fights"),
        "cap": plan.get("cap") or MAX_FIGHTS_TOTAL,
        "min_n": MIN_N,
        "baseline": _baseline_block(baseline_item, baseline_fights) if baseline_item else None,
        "rows": rows,
        "skipped": list(plan.get("skipped") or []),
        "runs": runs,
    }
