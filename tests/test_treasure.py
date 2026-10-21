"""宝箱遗物真的进遗物栏（真游戏在 UI 节点里发放，模拟器补上）；DECKBENCH_TREASURE_FIX=0 = 旧行为。"""
import os
import sys

import pytest

pytest.importorskip("sts2sim.gen.game")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from sts2sim.engine.run import play_run  # noqa: E402


def _run(seed, flag, monkeypatch):
    import batch
    monkeypatch.setenv("DECKBENCH_TREASURE_FIX", flag)
    return play_run("Ironclad", 0, seed, agent=batch.make_agent("learned", seed)).to_dict()


def test_treasure_relic_obtained(monkeypatch):
    for seed in ("R0", "R1", "R3", "R4"):
        new = _run(seed, "1", monkeypatch)
        if not any("Treasure" in str(p) for p in new["path"]):
            continue
        old = _run(seed, "0", monkeypatch)
        # 进第一个宝箱之前两局完全一样；修复后多出宝箱遗物（之后的路线可能不同，所以只比"新多出来的遗物"）
        assert set(new["relics"]) - set(old["relics"]), (seed, new["relics"], old["relics"])
        return
    pytest.skip("这些种子都没走到宝箱")
