"""打法风格（sts2sim/engine/style.py 的 STYLES）：注册表、命令行/界面一致；standard 和不加风格结果完全相同；
juggler 同一种子结果可复现。注册表部分不需要游戏；整局部分需要本机生成的游戏代码。"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sts2sim.engine import style as ST  # noqa: E402

LANGS = ["zhs", "en", "ja", "ko"]


def test_registry_shape():
    assert list(ST.STYLES)[0] == ST.DEFAULT == "standard"
    assert ST.STYLES["standard"]["apply"] is None
    for sid, s in ST.STYLES.items():
        for lang in LANGS:
            assert s["name"][lang].strip() and s["desc"][lang].strip(), (sid, lang)
    assert ST.STYLES["juggler"]["apply"] is ST.apply_juggler


def test_cli_choices_match_registry():
    import batch
    assert batch.STYLE_IDS == list(ST.STYLES)


def test_resolve_and_compat():
    assert ST.resolve("") == ST.resolve(None) == "standard"
    assert ST.resolve(" Juggler ") == "juggler"
    for bad in ("nope", "old-id"):
        with pytest.raises(ValueError):
            ST.resolve(bad)
    assert ST.compatible("standard", "heuristic")
    assert ST.compatible("juggler", "learned") and ST.compatible("juggler", "modai") and ST.compatible("juggler", "mentor-full-ev")
    assert not ST.compatible("juggler", "heuristic") and not ST.compatible("juggler", "search")
    with pytest.raises(ValueError):
        ST.apply_style(None, "juggler", "heuristic")
    sentinel = object()
    assert ST.apply_style(sentinel, "standard", "heuristic") is sentinel


def test_registry_does_not_boot_game():
    """图形界面进程只读注册表：导入 style.py 不能把游戏运行时拉进来。"""
    code = ("import sys, json; from sts2sim.engine import style as S; S.list_styles('en');"
            "print(json.dumps(sorted(m for m in sys.modules if m.startswith('sts2sim'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == ["sts2sim", "sts2sim.engine", "sts2sim.engine.style"]


def test_gui_backend_styles_and_command(tmp_path):
    from gui import backend
    ids = [s["id"] for s in backend.styles("ja")]
    assert ids == list(ST.STYLES)
    be = backend.LocalPythonBackend()
    argv, _env, _cwd = be.build_command("batch", {"char": "Ironclad", "agent": "learned", "style": "juggler"}, str(tmp_path))
    assert argv[argv.index("--style") + 1] == "juggler"
    argv, _env, _cwd = be.build_command("batch", {"char": "Ironclad", "agent": "heuristic"}, str(tmp_path))
    assert argv[argv.index("--style") + 1] == "standard"
    with pytest.raises(ValueError):
        be.build_command("batch", {"char": "Ironclad", "agent": "heuristic", "style": "juggler"}, str(tmp_path))
    with pytest.raises(ValueError):
        be.build_command("batch", {"char": "Ironclad", "agent": "learned", "style": "old-id"}, str(tmp_path))


# ---------------------------------------------------------------- 整局（需要生成的游戏代码）
SEEDS = ["T1", "T2", "T3"]


def _play(agent, seed, style=None):
    pytest.importorskip("sts2sim.gen.game")
    import batch
    from sts2sim.engine.run import play_run
    old = dict(batch.AGENT)
    batch.AGENT.clear()
    batch.AGENT.update({"name": agent, "kw": {}, **({"style": style} if style is not None else {})})
    try:
        ag = batch.build_agent(seed)
        d = play_run("Ironclad", 0, seed, agent=ag).to_dict()
    finally:
        batch.AGENT.clear()
        batch.AGENT.update(old)
    d.pop("secs", None)
    d.pop("time", None)
    d.pop("seconds", None)
    return json.dumps(d, sort_keys=True, default=str), ag


@pytest.mark.parametrize("seed", SEEDS)
def test_standard_equals_no_style(seed):
    a, _ = _play("strong-nosearch", seed)
    b, _ = _play("strong-nosearch", seed, "standard")
    c, _ = _play("strong-nosearch", seed, "")
    assert a == b == c


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_juggler_reproducible(seed):
    a, ag = _play("strong-nosearch", seed, "juggler")
    b, _ = _play("strong-nosearch", seed, "juggler")
    assert a == b
    assert type(ag).__name__.startswith("Juggler") and ag.style == "juggler"


def test_juggler_changes_play():
    """juggler 真的在改决策（不是空壳）：几个种子里至少一局和标准不同。"""
    diff = [_play("strong-nosearch", s)[0] != _play("strong-nosearch", s, "juggler")[0] for s in SEEDS[:2]]
    assert any(diff)
