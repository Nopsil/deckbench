"""Structured combat timeline, recorded only when ``Combat.trace`` is a list.

AI clones set ``trace`` to ``None`` before they play, so a search does not
record and does not draw extra random numbers. A win or a timeout is not
stored. A loss keeps a bounded event list. A batch keeps that list for the
first few losses only.

The events are what the fight wrote down. They do not identify a cause.
"""
from __future__ import annotations

MAX_EVENTS = 240
MAX_LOSS_TRACES = 12
TRACE_VERSION = 1

_SKIPPED = frozenset({None, "asleep", "stunned", "no_move"})


def emit(combat, kind, **fields):
    """Append one event. No-op during a search, or once the fight is full."""
    if combat is None or combat.is_sim or combat.trace is None:
        return
    if len(combat.trace) >= MAX_EVENTS:
        combat._trace_truncated = True
        return
    row = {"kind": kind, "turn": int(combat.turn), "phase": combat.phase or ""}
    for key, value in fields.items():
        if value is not None:
            row[key] = value
    combat.trace.append(row)


def _powers(creature):
    out = {}
    for pid, power in creature.powers.items():
        amount = int(power.amount)
        if amount:
            out[str(pid)] = amount
    return out


def _intent(enemy):
    move = getattr(enemy, "intent", None)
    if move is None:
        return None, None, None
    return str(move.id), str(move.name), str(move.intent)


def snapshot(combat):
    """HP, block, energy and power stacks at this moment. No cards, no guess."""
    player = combat.player
    enemies = []
    for enemy in combat.enemies:
        move_id, move_name, intent = _intent(enemy)
        row = {
            "name": enemy.name,
            "id": str(getattr(getattr(enemy, "m", None), "id", "") or ""),
            "hp": max(0, int(enemy.hp)),
            "max_hp": int(enemy.max_hp),
            "block": int(enemy.block),
            "alive": bool(enemy.alive),
            "powers": _powers(enemy),
        }
        if move_id:
            row["move"] = move_id
        if move_name:
            row["move_name"] = move_name
        if intent:
            row["intent"] = intent
        enemies.append(row)
    return {
        "player": {
            "name": player.name,
            "hp": max(0, int(player.hp)),
            "max_hp": int(player.max_hp),
            "block": int(player.block),
            "energy": int(player.energy),
            "hand": len(player.hand),
            "powers": _powers(player),
        },
        "enemies": enemies,
    }


def note_turn(combat):
    emit(combat, "turn_start", state=snapshot(combat))


def note_play(combat, card, target, paid):
    emit(
        combat, "play",
        card=str(card.id),
        name=str(card.name),
        upgraded=bool(card.upgraded),
        target=None if target is None else str(target.name),
        paid=int(paid),
        energy=int(combat.player.energy),
    )


def note_potion(combat, name, target):
    emit(
        combat, "potion",
        name=str(name),
        target=None if target is None else str(target.name),
    )


def note_damage(combat, src, target, amount, blocked, lost, kind):
    player_target = bool(getattr(target, "is_player", False))
    emit(
        combat, "damage",
        src=None if src is None else str(getattr(src, "name", "") or ""),
        target=str(getattr(target, "name", "") or ""),
        player_target=player_target,
        amount=int(amount),
        blocked=int(blocked),
        lost=int(lost),
        hp_after=max(0, int(target.hp)),
        block_after=int(target.block),
        hit=str(kind),
        hp_zero=bool(player_target and target.hp <= 0),
    )


def note_hp_loss(combat, target, lost, kind):
    player_target = bool(getattr(target, "is_player", False))
    emit(
        combat, "hp_loss",
        target=str(getattr(target, "name", "") or ""),
        player_target=player_target,
        lost=int(lost),
        hp_after=max(0, int(target.hp)),
        hit=str(kind),
        hp_zero=bool(player_target and target.hp <= 0),
    )


def note_block(combat, creature, amount):
    emit(
        combat, "block",
        target=str(creature.name),
        player_target=bool(creature.is_player),
        amount=int(amount),
        block_after=int(creature.block),
    )


def note_power(combat, target, pid, delta, total, blocked=False):
    emit(
        combat, "power_blocked" if blocked else "power",
        target=str(target.name),
        player_target=bool(target.is_player),
        power=str(pid),
        delta=int(delta),
        total=int(total),
    )


def note_enemy(combat, enemy, skipped):
    if skipped not in _SKIPPED:
        skipped = "no_move"
    move_id, move_name, intent = _intent(enemy)
    emit(
        combat, "enemy",
        name=str(enemy.name),
        id=str(getattr(getattr(enemy, "m", None), "id", "") or ""),
        move=move_id,
        move_name=move_name,
        intent=intent,
        skipped=skipped,
        hp=max(0, int(enemy.hp)),
        block=int(enemy.block),
    )


def note_end(combat):
    emit(combat, "end", result=str(combat.result or ""), state=snapshot(combat))


def pack(combat, result):
    """A loss trace, or ``None`` when this fight should not store one."""
    if result != "loss" or combat is None or combat.trace is None:
        return None
    events = list(combat.trace[:MAX_EVENTS])
    return {
        "version": TRACE_VERSION,
        "result": "loss",
        "turns": int(combat.turn),
        "truncated": bool(getattr(combat, "_trace_truncated", False) or len(combat.trace) > MAX_EVENTS),
        "events": events,
        "loss_turn": int(combat.turn),
    }


def cap_loss_traces(rows):
    """Keep full traces on the first losses. Later losses keep a short marker."""
    kept = 0
    out = []
    for row in rows:
        row = dict(row)
        trace = row.get("trace")
        if isinstance(trace, dict) and trace.get("result") == "loss" and not trace.get("omitted"):
            if kept >= MAX_LOSS_TRACES:
                row["trace"] = {
                    "version": TRACE_VERSION,
                    "result": "loss",
                    "omitted": "batch_cap",
                    "turns": trace.get("turns"),
                    "loss_turn": trace.get("loss_turn"),
                }
            else:
                kept += 1
        out.append(row)
    return out


def trace_status(row):
    """Why a fight row can or cannot be replayed. ``row`` is one raw.jsonl object."""
    if not isinstance(row, dict):
        return "empty"
    result = row.get("result")
    trace = row.get("trace")
    if not isinstance(trace, dict):
        if result == "loss":
            return "no_trace"
        return "not_a_loss"
    if trace.get("omitted"):
        return "omitted"
    events = trace.get("events")
    if isinstance(events, list) and events:
        return "ready"
    return "empty"
