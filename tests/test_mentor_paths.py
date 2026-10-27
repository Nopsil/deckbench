"""mentor-full 的路径解析和界面开关。不加载游戏，也不需要真的 sts2_rs。"""
import json
import os
import sys

from gui import backend, paths
from sts2sim.engine import mentor_paths as MP


def _quiet(monkeypatch, tmp_path):
    for k in ("DECKBENCH_MENTOR_SITE", "DECKBENCH_MENTOR_PY", "DECKBENCH_MENTOR_PYTHON",
              "STS2SIM_MENTOR_SITE", "STS2SIM_MENTOR_PY", "DECKBENCH_MENTOR_CONFIG", "DECKBENCH_MENTOR_HOME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DECKBENCH_MENTOR_NO_DEFAULTS", "1")
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path / "data"))
    monkeypatch.delattr(sys, "frozen", raising=False)


def _tree(root):
    os.makedirs(os.path.join(root, "site", "sts2_rs"))
    os.makedirs(os.path.join(root, "py", "sts2_hint"))
    return os.path.join(root, "site"), os.path.join(root, "py")


def test_missing_is_not_selectable(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    st = MP.availability()
    assert st["available"] is False and st["reason"] == "missing" and st["dirs_ok"] is False
    a = {x["id"]: x for x in backend.agents_batch()}
    assert a["mentor-full"]["available"] is False and a["mentor-full-ev"]["available"] is False
    assert "DECKBENCH_MENTOR_SITE" in a["mentor-full"]["hint"]


def test_env_dirs_make_it_selectable(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    site, py = _tree(str(tmp_path / "m"))
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", site)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", py)
    st = MP.availability()
    assert st["available"] is True and st["dirs_ok"] is True
    assert {x["id"]: x for x in backend.agents_batch()}["mentor-full-ev"]["hint"] == ""


def test_json_and_env_override(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    drop_site, drop_py = _tree(str(tmp_path / "drop"))
    monkeypatch.setenv("DECKBENCH_MENTOR_HOME", str(tmp_path / "drop"))
    jsite, jpy = _tree(str(tmp_path / "fromjson"))
    cfg = tmp_path / "mentor.local.json"
    cfg.write_text(json.dumps({"site": "fromjson/site", "py": "fromjson/py"}), encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_MENTOR_CONFIG", str(cfg))
    got = MP.resolve()
    assert got["site"] == os.path.abspath(jsite) and got["py"] == os.path.abspath(jpy)
    assert got["source"].startswith("file:")
    esite, epy = _tree(str(tmp_path / "env"))
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", esite)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", epy)
    got = MP.resolve()
    assert got["site"] == os.path.abspath(esite) and got["source"] == "env"
    assert drop_site and drop_py


def test_python_txt_dropin(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    root = tmp_path / "bundle"
    _tree(str(root))
    exe = tmp_path / "python.exe"
    exe.write_text("", encoding="utf-8")
    (root / "python.txt").write_text("# comment\n" + str(exe) + "\n", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_MENTOR_HOME", str(root))
    assert MP.python_executable() == os.path.abspath(exe)
    assert MP.availability()["available"] is True


def test_packaged_exe_needs_python(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    site, py = _tree(str(tmp_path / "m"))
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", site)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", py)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    st = MP.availability()
    assert st["available"] is False and st["reason"] == "need_python"
    hint = {x["id"]: x for x in backend.agents_batch()}["mentor-full"]["hint"]
    assert "DECKBENCH_MENTOR_PYTHON" in hint
    exe = tmp_path / "python.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_MENTOR_PYTHON", str(exe))
    assert MP.availability()["available"] is True


def test_packaged_exe_rejects_itself_as_python(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    site, py = _tree(str(tmp_path / "m"))
    exe = tmp_path / "DeckBench.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", site)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", py)
    monkeypatch.setenv("DECKBENCH_MENTOR_PYTHON", str(exe))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert MP.python_executable() == ""
    assert MP.availability()["reason"] == "need_python"


def test_worker_uses_external_python_only_for_mentor(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    site, py = _tree(str(tmp_path / "m"))
    exe = tmp_path / "python.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", site)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", py)
    monkeypatch.setenv("DECKBENCH_MENTOR_PYTHON", str(exe))
    argv = backend.worker_argv("batch", "--agent", "mentor-full-ev", agent="mentor-full-ev")
    assert argv[:3] == [os.path.abspath(exe), "-m", "gui.worker"]
    other = backend.worker_argv("batch", "--agent", "modai", agent="modai")
    assert other[0] == sys.executable and "gui.worker" in other
    env = backend.worker_env("mentor-full")
    assert site in env["PYTHONPATH"].split(os.pathsep)
    assert env["DECKBENCH_MENTOR_SITE"] == site
    assert env["STS2SIM_GUI_DATA"] == paths.DATA_DIR
    plain = backend.worker_env("learned")
    assert site not in plain["PYTHONPATH"].split(os.pathsep)


def test_mstats_line():
    line = MP.mstats_line([
        {"mstats": {"mentor": 4, "fallback": 1, "ppo": {"map_select": [2, 0], "shop": [0, 1]}}},
        {"mstats": {"mentor": 1, "fallback": 0, "ppo": {"map_select": [1, 1]}}},
        {"victory": True},
    ])
    assert line["ok"] == 5 and line["fb"] == 1 and line["ppo_net"] == 3 and line["ppo_fb"] == 2
    assert "map_select 3/1" in line["ppo"] and MP.mstats_line([{"victory": False}]) is None


def _fake_pkg(root, body=""):
    os.makedirs(os.path.join(root, "sts2_rs"), exist_ok=True)
    os.makedirs(os.path.join(root, "hint", "sts2_hint"), exist_ok=True)
    open(os.path.join(root, "sts2_rs", "__init__.py"), "w", encoding="utf-8").write(body)
    open(os.path.join(root, "hint", "sts2_hint", "__init__.py"), "w", encoding="utf-8").write("")
    open(os.path.join(root, "hint", "sts2_hint", "adapter.py"), "w", encoding="utf-8").write("STATUS_CARD_TITLES = []\n")
    return os.path.join(root, "sts2_rs") and root


def _drop_fake():
    for name in list(sys.modules):
        if name == "sts2_rs" or name.startswith("sts2_rs.") or name == "sts2_hint" or name.startswith("sts2_hint."):
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if "mentor-fake" not in p.replace("\\", "/")]


def test_import_in_process_and_child(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    _drop_fake()
    root = str(tmp_path / "mentor-fake")
    _fake_pkg(root)
    site = os.path.join(root)
    # site dir is the folder that contains sts2_rs, matching site-packages layout
    # _fake_pkg put sts2_rs inside root, so SITE is root and PY is root/hint
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", root)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", os.path.join(root, "hint"))
    try:
        assert MP._import_in_process() is None
        err = MP.import_error()
        assert err is None
    finally:
        _drop_fake()


def test_import_failure_is_reported(monkeypatch, tmp_path):
    _quiet(monkeypatch, tmp_path)
    _drop_fake()
    root = str(tmp_path / "mentor-fake-bad")
    _fake_pkg(root, body="raise RuntimeError('no network')\n")
    monkeypatch.setenv("DECKBENCH_MENTOR_SITE", root)
    monkeypatch.setenv("DECKBENCH_MENTOR_PY", os.path.join(root, "hint"))
    try:
        err = MP._import_in_process()
        assert err and "RuntimeError" in err and "no network" in err
    finally:
        _drop_fake()


def test_smoke_entrypoint_exits_when_unconfigured(monkeypatch, tmp_path, capsys):
    _quiet(monkeypatch, tmp_path)
    assert MP.main() == 2
    assert "import: skipped" in capsys.readouterr().out
