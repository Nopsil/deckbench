"""固定种子的战斗结果：加速前后逐字段相同，并且不随进程数变化。"""
import os

from sts2sim import fightcheck

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEUR = os.path.join(ROOT, "tests", "fixtures", "fight_seeds.json")
BEAM = os.path.join(ROOT, "tests", "fixtures", "fight_seeds_beam.json")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_heuristic_seeds_match_recorded_output():
    rows = fightcheck.workload(4, 2, ("heuristic",))
    assert fightcheck.canonical(rows) == _read(HEUR)


def test_beam_seeds_match_recorded_output():
    rows = fightcheck.workload(2, 1, ("beam",))
    assert fightcheck.canonical(rows) == _read(BEAM)


def test_worker_count_matches_serial_for_several_seeds():
    serial = fightcheck.workload(3, 2, ("heuristic",), workers=1)
    parallel = fightcheck.workload(3, 2, ("heuristic",), workers=2)
    assert fightcheck.canonical(serial) == fightcheck.canonical(parallel)
    beam_serial = fightcheck.workload(2, 1, ("beam",), workers=1)
    beam_parallel = fightcheck.workload(2, 1, ("beam",), workers=2)
    assert beam_serial == beam_parallel
