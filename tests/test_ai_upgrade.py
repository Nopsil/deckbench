"""AI 升级：可调参数、学习版参数文件、多目标威胁、规划器能跑。"""
import json
import os
import sys

import pytest

pytest.importorskip("sts2sim.gen.game")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from sts2sim.engine import weights as WM  # noqa: E402
from sts2sim.engine.run import play_run, RunDriver  # noqa: E402


def test_weights_defaults_and_scale_cover_same_keys():
    assert set(WM.DEFAULTS) == set(WM.SCALE)


def test_default_weights_reproduce_strong_agent():
    import batch
    WM.set_weights({})
    a = play_run("Ironclad", 0, "T7", agent=batch.make_agent("strong-nosearch", "T7")).to_dict()
    WM.set_weights(dict(WM.DEFAULTS))
    b = play_run("Ironclad", 0, "T7", agent=batch.make_agent("strong-nosearch", "T7")).to_dict()
    assert a["path"] == b["path"] and a["picked"] == b["picked"]


def test_learned_weights_file_and_agent():
    import batch
    p = WM.LEARNED
    if not os.path.exists(p):
        pytest.skip("data/ai_weights.json 还没生成")
    d = json.load(open(p, encoding="utf-8"))
    assert set(d["weights"]) <= set(WM.DEFAULTS)
    try:
        r = play_run("Silent", 0, "T8", agent=batch.make_agent("learned", "T8"))
        assert r.error is None and r.floor >= 1
    finally:
        WM.set_weights({})


def test_multi_threat_in_range():
    import batch
    ag = batch.make_agent("strong-nosearch", "R1")
    d = RunDriver("Ironclad", 0, "R1", agent=ag)
    d._create()
    f = ag.multi_threat()
    assert 0.0 < f <= 1.0


def test_planner_agent_runs():
    import batch
    r = play_run("Defect", 0, "T9", agent=batch.make_agent("planner", "T9"))
    assert r.error is None and r.floor >= 1
