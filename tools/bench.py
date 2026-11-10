#!/usr/bin/env python3
"""Time the internal Python fight engine. No game install.

The batch is the synthetic decks and monsters in ``sts2sim.fightcheck``
(the same fixed seeds the determinism test locks) plus a short
training-dummy sample (``encounter: DUMMY``) on Claude probe decks.

Prints fights/sec from wall time, and a per-phase split from one profiled
pass. Phase times are self time, so the shares add up to the profiled run.
The profiler is not included in the fights/sec number.

    python tools/bench.py
    python tools/bench.py --seeds 4 --fights 1 --repeat 1
"""
import argparse
import cProfile
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sts2sim import fightcheck  # noqa: E402
from sts2sim.runner import _run_fight  # noqa: E402


# Self-time buckets. A function is the first phase whose names match.
PHASES = (
    ("dispatch", ("emit", "_fire", "_power_handlers", "_relic_handlers", "_mod_handlers", "_fn")),
    ("clone", ("clone", "_copy_card", "_clone_base", "_copy_value")),
    ("value", ("evaluate", "score_delta", "state_value", "mechanic_adjust", "resources",
               "incoming_damage", "predict_intent_damage")),
    ("legal", ("legal_actions", "card_cost", "_play_gate", "can_play")),
    ("resolve", ("play", "play_card", "run_effects", "op_damage", "op_apply", "op_block",
                 "op_draw", "op_if", "op_repeat", "best_action", "_expand", "_v", "play_turn")),
    ("damage", ("deal_damage", "calc_damage", "lose_hp", "gain_block", "apply_power", "kill")),
    ("enemy", ("enemy_phase", "take_turn", "choose_intent", "start_player_turn", "end_player_turn",
               "start_battle")),
    ("expr", ("ev", "_fast_name", "_blank_ns", "_ensure_base")),
)


def _phase(fn):
    for name, keys in PHASES:
        if fn in keys:
            return name
    return "other"


def _profile(fn):
    pr = cProfile.Profile()
    pr.enable()
    rows = fn()
    pr.disable()
    st = pstats.Stats(pr)
    totals = {name: 0.0 for name, _ in PHASES}
    totals["other"] = 0.0
    calls = 0
    for func, stat in st.stats.items():
        # (callcount, reccallcount, tottime, cumtime, callers)
        phase = _phase(func[2])
        totals[phase] += stat[2]
        calls += stat[0]
    return rows, totals, sum(totals.values()), calls


def _wall(fn, repeat):
    fn()  # warmup: load the mod, fill caches
    samples = []
    n = 0
    for _ in range(repeat):
        t0 = time.perf_counter()
        rows = fn()
        dt = time.perf_counter() - t0
        n = len(rows)
        samples.append(dt)
    samples.sort()
    mid = samples[len(samples) // 2]
    return n, mid, samples


def _internal(seeds, fights, agents):
    def run():
        return fightcheck.workload(seeds, fights, agents)
    return run


def _dummy(fights, turns):
    # These probe decks are the training-dummy rows. They do not use the
    # base-game strike/defend cards, which are not in this repository.
    decks = ("probe_A", "probe_D", "probe_noengine")

    def run():
        rows = []
        for deck in decks:
            for i in range(fights):
                rows.append(_run_fight(
                    ["claude_v34"], deck, 1, "探针", i, 1000,
                    "heuristic", turns, "DUMMY"))
        return rows
    return run


def _report(title, fn, repeat):
    n, mid, samples = _wall(fn, repeat)
    _rows, totals, prof_total, calls = _profile(fn)
    rate = n / mid if mid else 0.0
    print(f"{title}")
    print(f"  fights {n}   median {mid:.4f}s   {rate:.1f} fights/s"
          f"   samples {', '.join(f'{s:.4f}' for s in samples)}")
    if prof_total <= 0:
        print()
        return rate, mid, n
    print(f"  profiled self time {prof_total:.4f}s over {calls} calls")
    order = [name for name, _ in PHASES] + ["other"]
    for name in order:
        sec = totals[name]
        if sec <= 0:
            continue
        print(f"    {name:<10} {sec:.4f}s  {100.0 * sec / prof_total:5.1f}%")
    print()
    return rate, mid, n


def main():
    ap = argparse.ArgumentParser(description="Benchmark the internal fight engine (no game install).")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--fights", type=int, default=3, help="fights per deck per seed for the heuristic batch")
    ap.add_argument("--repeat", type=int, default=3, help="wall-clock samples; fights/sec uses the median")
    ap.add_argument("--dummy-fights", type=int, default=4)
    ap.add_argument("--dummy-turns", type=int, default=4)
    ap.add_argument("--skip-dummy", action="store_true")
    ap.add_argument("--skip-beam", action="store_true")
    args = ap.parse_args()
    print("internal Python fight engine (no game install)")
    print(f"repeat {args.repeat} (median)   heuristic seeds {args.seeds} fights/deck {args.fights}")
    print()
    _report(
        f"heuristic  seeds={args.seeds} fights/deck={args.fights} decks=start,burst,draw",
        _internal(args.seeds, args.fights, ("heuristic",)),
        args.repeat,
    )
    if not args.skip_beam:
        _report(
            f"mixed heuristic+beam  seeds={args.seeds} fights/deck=1",
            _internal(args.seeds, 1, ("heuristic", "beam")),
            args.repeat,
        )
    if not args.skip_dummy:
        _report(
            f"training dummy  decks=probe_A,probe_D,probe_noengine  "
            f"fights={args.dummy_fights} max_turns={args.dummy_turns}",
            _dummy(args.dummy_fights, args.dummy_turns),
            args.repeat,
        )


if __name__ == "__main__":
    main()
