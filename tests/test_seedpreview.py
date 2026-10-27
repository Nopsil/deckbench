"""种子预览：不启动游戏就能测分布和报错；有本机缓存时再跑一条真预览。"""
import os
import subprocess
import sys

import pytest

from sts2sim.engine.seedpreview import (
    PreviewError,
    assemble,
    distribution,
    format_text,
    map_counts,
    preview,
    seed_warning_codes,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "tests", "fixtures", "saves", "sample_history.run")


def test_distribution_and_map_counts():
    rooms = [{
        "act": "ACT.SAMPLE_ONE",
        "boss": "ENCOUNTER.SAMPLE_BOSS",
        "second_boss": None,
        "ancient": "EVENT.SAMPLE_START",
        "normal": ["ENCOUNTER.A", "ENCOUNTER.A", "ENCOUNTER.B"],
        "elite": ["ENCOUNTER.E"],
        "events": ["EVENT.SAMPLE"],
    }]
    dist = distribution(rooms)
    assert dist[0]["normal_counts"] == [{"id": "ENCOUNTER.A", "n": 2}, {"id": "ENCOUNTER.B", "n": 1}]
    assert dist[0]["boss"] == "ENCOUNTER.SAMPLE_BOSS"
    mp = {"cols": 2, "boss": {"col": 0, "row": 3},
          "rows": [[{"col": 0, "row": 1, "type": "Monster"}, {"col": 1, "row": 1, "type": "Unknown"}]]}
    assert map_counts(mp)["Monster"] == 1
    assert map_counts(mp)["Boss"] == 1
    assert map_counts(mp)["Unknown"] == 1


def test_assemble_hides_relic_queue_and_normalizes_seed():
    res = assemble(
        "abcdef", "ABCDEF", seed_warning_codes("abcdef", "ABCDEF"),
        "Ironclad", 0, ["ACT.SAMPLE_ONE"],
        [{"act_index": 0, "act": "ACT.SAMPLE_ONE", "rows": [], "cols": 0, "boss": None, "confidence": "act_entry"}],
        [{"act": "ACT.SAMPLE_ONE", "boss": "ENCOUNTER.SAMPLE_BOSS", "normal": ["ENCOUNTER.A"], "elite": []}],
        "EVENT.SAMPLE_START",
        [{"index": 0, "key": "EVENT.SAMPLE.OPT", "id": "OPT", "locked": False}],
        {},
        {"starting": ["RELIC.SAMPLE_START"], "shared_queue": [], "character_queue": []},
    )
    assert res["seed"] == "ABCDEF"
    assert any(w["code"] == "seedNormalized" for w in res["warnings"])
    assert any(w["code"] == "relicQueueHidden" for w in res["warnings"])
    assert res["distribution"][0]["normal"] == ["ENCOUNTER.A"]
    assert "unknown_nodes" in res["limits"]
    text = format_text(res, "en")
    assert "ABCDEF" in text
    assert "ENCOUNTER.SAMPLE_BOSS" in text
    assert "RELIC.SAMPLE_START" in text


def test_preview_without_engine_is_a_clear_error():
    try:
        import sts2sim.gen.game  # noqa: F401
    except ModuleNotFoundError:
        with pytest.raises(PreviewError) as ei:
            preview("ABCDEFGHJKLM", "Ironclad", 0)
        assert ei.value.code == "no_engine"
    else:
        res = preview("ABCDEFGHJKLM", "Ironclad", 0, neow="none")
        assert res["seed"] == "ABCDEFGHJKLM"
        assert res["maps"] and res["distribution"]
        assert res["maps"][0]["confidence"] == "act_entry"


def test_rejects_bad_input():
    with pytest.raises(PreviewError) as e1:
        preview("", "Ironclad", 0)
    assert e1.value.code == "need_seed"
    with pytest.raises(PreviewError) as e2:
        preview("ABC", "NotACharacter", 0)
    assert e2.value.code == "bad_char"
    with pytest.raises(PreviewError) as e3:
        preview("ABC", "Ironclad", 99)
    assert e3.value.code == "bad_asc"


def test_import_cli_on_sample():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "import_run.py"), HIST, "--lang", "en"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "SAMPLESEED01" in r.stdout
    assert "CARD.SAMPLE_PICK" in r.stdout
    assert "RELIC.SAMPLE_CHEST" in r.stdout
    assert "ENCOUNTER.SAMPLE_FIGHT" in r.stdout


def test_preview_cli_exits_cleanly_without_engine():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "seed_preview.py"), "ABCDEFGHJKLM", "--lang", "en", "--neow", "none"],
                       cwd=ROOT, capture_output=True, text=True)
    try:
        import sts2sim.gen.game  # noqa: F401
        has_engine = True
    except ModuleNotFoundError:
        has_engine = False
    if has_engine:
        assert r.returncode == 0, r.stderr
        assert "ABCDEFGHJKLM" in r.stdout
    else:
        assert r.returncode == 2
        assert r.stderr.strip()
