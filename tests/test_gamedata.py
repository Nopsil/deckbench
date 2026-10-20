"""首次运行 / 缓存绑定逻辑（不需要游戏文件：用假的 sts2.dll）。"""
import json
import os

import pytest

from sts2sim import gamedata as gd


@pytest.fixture
def env(tmp_path, monkeypatch):
    game = tmp_path / "steamapps" / "common" / gd.GAME_FOLDER
    bin_dir = game / "data_sts2_windows_x86_64"
    bin_dir.mkdir(parents=True)
    (bin_dir / gd.DLL).write_bytes(b"fake dll v1")
    cache = tmp_path / "cache"
    monkeypatch.setenv("DECKBENCH_CACHE", str(cache))
    monkeypatch.setenv("DECKBENCH_GAME_DIR", str(game))
    return game, bin_dir / gd.DLL, cache


def _fake_cache(dll, cache):
    d = cache / "x"
    d.mkdir(parents=True)
    json.dump({"format": gd.FORMAT, "dll_path": str(dll), "dll_sha256": gd.sha256(str(dll))}, open(d / "manifest.json", "w"))
    json.dump({"cache_dir": str(d)}, open(cache / "current.json", "w"))
    return str(d)


def test_find_dll_nested(env):
    game, dll, _ = env
    assert gd.find_dll() == str(dll)


def test_no_install_is_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "c"))
    monkeypatch.setenv("DECKBENCH_GAME_DIR", str(tmp_path / "nope"))
    assert gd.find_dll() is None
    with pytest.raises(gd.GameDataError, match="Game install not found"):
        gd.verify()
    with pytest.raises(SystemExit) as e:
        gd.require()
    assert e.value.code == 2


def test_found_but_not_generated(env):
    with pytest.raises(gd.GameDataError, match="not generated"):
        gd.verify()


def test_cache_bound_to_install_hash(env):
    game, dll, cache = env
    d = _fake_cache(dll, cache)
    assert gd.verify() == d
    dll.write_bytes(b"fake dll v2")           # 游戏更新 / 换了文件 → 拒绝加载
    with pytest.raises(gd.GameDataError, match="refusing"):
        gd.verify()


def test_cache_refuses_when_install_removed(env):
    game, dll, cache = env
    _fake_cache(dll, cache)
    os.remove(dll)
    with pytest.raises(gd.GameDataError, match="gone"):
        gd.verify()


def test_repo_ships_no_generated_game_code():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gen = os.path.join(root, "sts2sim", "gen")
    assert sorted(f for f in os.listdir(gen) if not f.startswith("__pycache__")) == ["__init__.py"]
    assert not os.path.exists(os.path.join(root, "data", "monster_ai.json"))
