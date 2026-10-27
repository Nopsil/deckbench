"""种子预览：不启动游戏就能测分布、JSON 和本机缓存；有本机游戏逻辑时再跑一条真预览。"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from sts2sim.engine import seedpreview
from sts2sim.engine.seedpreview import (
    PUBLIC_KEYS,
    PreviewError,
    assemble,
    canonicalize,
    distribution,
    format_text,
    map_counts,
    preview,
    public_document,
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


def _sample(spec):
    """虚构 ID。测 JSON / 缓存时不碰游戏。"""
    return assemble(
        spec["raw"], spec["canon"], seed_warning_codes(spec["raw"], spec["canon"]),
        spec["char"], spec["asc"], ["ACT.SAMPLE_ONE"],
        [{
            "act_index": 0, "act": "ACT.SAMPLE_ONE", "confidence": "act_entry", "cols": 2,
            "boss": {"col": 0, "row": 3, "label": "drop-me"},
            "rows": [[{"col": 0, "row": 1, "type": "Monster", "children": [[1, 2]], "name": "drop-me"}]],
            "counts": {"Monster": 1, "Boss": 1}, "leak": "drop-me",
        }],
        [{
            "act": "ACT.SAMPLE_ONE", "boss": "ENCOUNTER.SAMPLE_BOSS", "second_boss": None,
            "ancient": "EVENT.SAMPLE_START", "normal": ["ENCOUNTER.A", "ENCOUNTER.A"],
            "elite": ["ENCOUNTER.E"], "events": ["EVENT.SAMPLE"], "title": "drop-me",
        }],
        "EVENT.SAMPLE_START",
        [{"index": 0, "key": "EVENT.SAMPLE.OPT", "id": "OPT", "locked": False, "text": "drop-me"}],
        {"0": {
            "encounter": "ENCOUNTER.A", "gold": 10, "deck": ["CARD.SAMPLE"],
            "relics": ["RELIC.SAMPLE_START"], "potions": [],
            "rewards": [{"kind": "CardReward", "cards": ["CARD.SAMPLE"], "flavor": "drop-me"}],
            "note": "drop-me",
        }},
        {"starting": ["RELIC.SAMPLE_START"], "shared_queue": [], "character_queue": [], "extra": ["drop-me"]},
    )


def _load_cli():
    path = os.path.join(ROOT, "tools", "seed_preview.py")
    name = "seed_preview_cli_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_public_document_is_a_stable_schema():
    spec = {"raw": "abcdef", "canon": "ABCDEF", "char": "Silent", "asc": 3, "neow": "none"}
    doc = public_document(_sample(spec))
    assert list(doc) == list(PUBLIC_KEYS)
    assert doc["v"] == 1
    assert doc["seed"] == "ABCDEF"
    assert doc["character"] == "Silent"
    assert doc["ascension"] == 3
    assert doc["maps"][0]["rows"][0][0] == {"col": 0, "row": 1, "type": "Monster", "children": [[1, 2]]}
    assert "name" not in doc["maps"][0]["rows"][0][0]
    assert "leak" not in doc["maps"][0]
    assert "label" not in doc["maps"][0]["boss"]
    assert "title" not in doc["rooms"][0]
    assert "text" not in doc["neow_options"][0]
    assert doc["neow_options"][0]["id"] == "OPT"
    assert "flavor" not in doc["after_neow"]["0"]["rewards"][0]
    assert "note" not in doc["after_neow"]["0"]
    assert doc["after_neow"]["0"]["rewards"][0]["cards"] == ["CARD.SAMPLE"]
    assert doc["relics"] == {"starting": ["RELIC.SAMPLE_START"], "shared_queue": [], "character_queue": []}
    assert "extra" not in doc["relics"]
    blob = json.dumps(doc, ensure_ascii=False)
    assert "drop-me" not in blob
    again = json.loads(json.dumps(public_document(doc), ensure_ascii=False, indent=1))
    assert again == json.loads(json.dumps(doc, ensure_ascii=False, indent=1))


def test_bad_neow_does_not_touch_the_engine(monkeypatch):
    def boom(spec):
        raise AssertionError("engine should not run")
    monkeypatch.setattr(seedpreview, "_generate", boom)
    with pytest.raises(PreviewError) as e:
        preview("ABCDEFGHJKLM", "Ironclad", 0, neow="nope")
    assert e.value.code == "bad_neow"


def test_no_engine_does_not_write_a_cache(tmp_path, monkeypatch):
    def explode():
        raise ModuleNotFoundError("sts2sim.gen.game")
    monkeypatch.setattr(seedpreview, "_load_game", explode)
    with pytest.raises(PreviewError) as e:
        preview("ABCDEFGHJKLM", "Ironclad", 0, neow="none", use_cache=True, cache_dir=str(tmp_path))
    assert e.value.code == "no_engine"
    assert e.value.params["err"]
    assert list(tmp_path.iterdir()) == []


def test_cache_is_keyed_by_seed_char_asc_neow_and_skips_the_engine(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake(spec):
        calls["n"] += 1
        return _sample(spec)

    monkeypatch.setattr(seedpreview, "_generate", fake)
    first = preview("abcdef", "Silent", "1", neow="all", use_cache=True, cache_dir=str(tmp_path))
    assert calls["n"] == 1
    assert first["seed_input"] == "abcdef"
    assert first["seed"] == "ABCDEF"
    assert any(w["code"] == "seedNormalized" for w in first["warnings"])
    assert list(first) == list(PUBLIC_KEYS)

    def boom(spec):
        raise AssertionError("cached preview should not load the engine")
    monkeypatch.setattr(seedpreview, "_generate", boom)
    second = preview("ABCDEF", "Silent", 1, neow="all", use_cache=True, cache_dir=str(tmp_path))
    assert second["seed_input"] == "ABCDEF"
    assert second["seed"] == "ABCDEF"
    assert not any(w["code"] == "seedNormalized" for w in second["warnings"])
    assert any(w["code"] == "relicQueueHidden" for w in second["warnings"])
    assert second["distribution"][0]["normal_counts"][0] == {"id": "ENCOUNTER.A", "n": 2}

    files = [p for p in tmp_path.iterdir() if p.suffix == ".json"]
    assert len(files) == 1
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["cache_v"] == 1
    assert payload["key"] == {"seed": "ABCDEF", "char": "Silent", "asc": 1, "neow": "all"}
    assert payload["preview"]["character"] == "Silent"
    assert "drop-me" not in files[0].read_text(encoding="utf-8")
    assert os.path.commonpath([os.path.abspath(ROOT), os.path.abspath(files[0])]) != os.path.abspath(ROOT)

    monkeypatch.setattr(seedpreview, "_generate", fake)
    preview("ABCDEF", "Silent", 1, neow="none", use_cache=True, cache_dir=str(tmp_path))
    preview("ABCDEF", "Defect", 1, neow="all", use_cache=True, cache_dir=str(tmp_path))
    preview("ABCDEF", "Silent", 2, neow="all", use_cache=True, cache_dir=str(tmp_path))
    preview("ZZZZZZZZZZZZ", "Silent", 1, neow="all", use_cache=True, cache_dir=str(tmp_path))
    assert calls["n"] == 5
    assert len(list(tmp_path.glob("*.json"))) == 5


def test_corrupt_cache_is_rebuilt(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake(spec):
        calls["n"] += 1
        return _sample(spec)

    monkeypatch.setattr(seedpreview, "_generate", fake)
    preview("ABCDEFGHJKLM", use_cache=True, cache_dir=str(tmp_path))
    path = next(tmp_path.glob("*.json"))
    path.write_text("{", encoding="utf-8")
    preview("ABCDEFGHJKLM", use_cache=True, cache_dir=str(tmp_path))
    assert calls["n"] == 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["key"]["asc"] = 9
    path.write_text(json.dumps(payload), encoding="utf-8")
    preview("ABCDEFGHJKLM", use_cache=True, cache_dir=str(tmp_path))
    assert calls["n"] == 3
    assert json.loads(path.read_text(encoding="utf-8"))["key"]["asc"] == 0


def test_cache_inside_the_repo_is_refused(monkeypatch):
    def boom(spec):
        raise AssertionError("refused cache must not generate")
    monkeypatch.setattr(seedpreview, "_generate", boom)
    inside = os.path.join(ROOT, "seed-preview-cache")
    with pytest.raises(PreviewError) as e:
        preview("ABCDEFGHJKLM", use_cache=True, cache_dir=inside)
    assert e.value.code == "cache_in_repo"
    assert not os.path.exists(inside)


def test_default_cache_dir_stays_outside_the_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "user-cache"))
    from sts2sim.engine.seedpreview import default_cache_dir
    d = default_cache_dir()
    assert os.path.basename(d) == "seed-preview"
    assert os.path.commonpath([os.path.abspath(ROOT), os.path.abspath(d)]) != os.path.abspath(ROOT)
    calls = {"n": 0}

    def fake(spec):
        calls["n"] += 1
        return _sample(spec)

    monkeypatch.setattr(seedpreview, "_generate", fake)
    preview("ABCDEFGHJKLM", "Ironclad", 0, "first", use_cache=True)
    stored = list((tmp_path / "user-cache" / "seed-preview").glob("*.json"))
    assert len(stored) == 1 and calls["n"] == 1


def test_cli_json_schema_and_cache_without_engine(tmp_path, monkeypatch, capsys):
    calls = {"n": 0}

    def fake(spec):
        calls["n"] += 1
        return _sample(spec)

    monkeypatch.setattr(seedpreview, "_generate", fake)
    cli = _load_cli()
    out = tmp_path / "preview.json"
    cache = tmp_path / "cache"
    argv = ["abcdEFGHJKLM", "--char", "Defect", "--asc", "2", "--neow", "none",
            "--json", str(out), "--cache", str(cache), "--lang", "en"]
    assert cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "Character" in text
    data = json.loads(out.read_text(encoding="utf-8"))
    assert list(data) == list(PUBLIC_KEYS)
    assert data["v"] == 1
    assert data["character"] == "Defect"
    assert data["ascension"] == 2
    assert data["seed"] == canonicalize("abcdEFGHJKLM")
    assert "drop-me" not in out.read_text(encoding="utf-8")
    assert cli.main(argv) == 0
    assert calls["n"] == 1
    capsys.readouterr()
    assert cli.main(["abcdEFGHJKLM", "--char", "Defect", "--asc", "2", "--neow", "none",
                     "--json", "-", "--cache", str(cache), "--lang", "en"]) == 0
    stdout = capsys.readouterr().out
    assert stdout.lstrip().startswith("{")
    piped = json.loads(stdout)
    assert piped["v"] == 1 and piped["character"] == "Defect"
    assert "Character" not in stdout
    assert calls["n"] == 1


def test_cli_json_not_written_when_engine_missing(tmp_path, monkeypatch, capsys):
    cli = _load_cli()

    def boom(*args, **kwargs):
        raise PreviewError("no_engine", err="missing")

    monkeypatch.setattr(cli, "preview", boom)
    out = tmp_path / "preview.json"
    cache = tmp_path / "cache"
    rc = cli.main(["ABCDEFGHJKLM", "--lang", "en", "--json", str(out), "--cache", str(cache)])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert "Local game logic" in captured.err
    assert not out.exists()
    assert not cache.exists()


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
