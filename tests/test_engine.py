"""新引擎（转译游戏代码）的基本测试：整局能跑完、确定性、Gym 冒烟。"""
import pytest

pytest.importorskip("sts2sim.gen.game")

from sts2sim.engine.run import play_run  # noqa: E402
from sts2sim.engine.gym import Sts2Env  # noqa: E402

CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]


@pytest.mark.parametrize("char", CHARS)
def test_full_run_completes(char):
    r = play_run(char, 10, "T1")
    assert r.error is None
    assert r.floor >= 1 and r.path
    for c in r.combats:
        assert len(c) == 8 and not c[7], c   # 不应触发安全阀


def test_deterministic_same_process():
    a = play_run("Defect", 0, "T2").to_dict()
    b = play_run("Defect", 0, "T2").to_dict()
    for k in ("path", "combats", "picked", "floor", "victory"):
        assert a[k] == b[k], k


def test_ascension_changes_run():
    a = play_run("Ironclad", 0, "T3")
    b = play_run("Ironclad", 10, "T3")
    assert a.path[0][3] != b.path[0][3] or a.path != b.path   # A10 起始 HP/路径不同


def test_gym_smoke():
    env = Sts2Env("Silent", ascension=10)
    obs, _ = env.reset("T4")
    seen, done, n = set(), False, 0
    while not done and n < 3000:
        seen.add(obs["type"])
        obs, r, done, info = env.step(0 if obs["type"] != "take_reward" else 1)
        n += 1
    assert done and r in (1.0, -1.0) and "combat" in seen
    env.close()
