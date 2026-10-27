"""界面里的 mentor-full：没配置 spire-mentor 时不可选（不需要生成的游戏代码）。"""
import os

from gui import backend


def test_mentor_full_greyed_out_without_config(monkeypatch):
    monkeypatch.setenv("DECKBENCH_MENTOR_NO_DEFAULTS", "1")
    monkeypatch.setenv("STS2SIM_GUI_DATA", "no-such-mentor-data")
    monkeypatch.delenv("DECKBENCH_MENTOR_SITE", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_PY", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_PYTHON", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_CONFIG", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_HOME", raising=False)
    a = {x["id"]: x for x in backend.agents_batch()}["mentor-full"]
    assert a["available"] is False and "DECKBENCH_MENTOR_SITE" in a["hint"]


def test_mentor_full_available_when_dirs_exist(monkeypatch, tmp_path):
    os.makedirs(tmp_path / "site" / "sts2_rs")
    os.makedirs(tmp_path / "py" / "sts2_hint")
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", str(tmp_path / "site"))
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", str(tmp_path / "py"))
    a = {x["id"]: x for x in backend.agents_batch()}["mentor-full"]
    assert a["available"] is True and a["hint"] == ""


def test_mentor_full_ev_listed(monkeypatch):
    monkeypatch.setenv("DECKBENCH_MENTOR_NO_DEFAULTS", "1")
    monkeypatch.setenv("STS2SIM_GUI_DATA", "no-such-mentor-data")
    monkeypatch.delenv("DECKBENCH_MENTOR_SITE", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_CONFIG", raising=False)
    monkeypatch.delenv("DECKBENCH_MENTOR_HOME", raising=False)
    a = {x["id"]: x for x in backend.agents_batch()}["mentor-full-ev"]
    assert a["available"] is False


def test_modai_listed_and_windows_hides_fork_agents(monkeypatch):
    ids = [x["id"] for x in backend.agents_batch()]
    assert "modai" in ids
    import importlib
    monkeypatch.setattr(os, "name", "nt")
    b2 = importlib.reload(backend)
    try:
        ids = [x["id"] for x in b2.agents_batch()]
        assert "modai" in ids and "modai-boss" not in ids and "learned-search" not in ids
    finally:
        monkeypatch.undo()
        importlib.reload(backend)
