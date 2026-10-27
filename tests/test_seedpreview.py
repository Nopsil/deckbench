"""种子预览：不启动游戏就能测分布和报错；有本机缓存时再跑一条真预览。"""
import json
import os
import subprocess
import sys

import pytest

from sts2sim.engine.seedpreview import (
    PreviewError,
    _neow_indexes,
    assemble,
    distribution,
    format_text,
    map_counts,
    peek_relics,
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


def test_neow_selector_accepts_first_all_none_and_index():
    options = [
        {"index": 0, "locked": True},
        {"index": 1, "locked": False},
        {"index": 2, "locked": False},
    ]
    assert _neow_indexes("first", options) == [1]
    assert _neow_indexes("all", options) == [0, 1, 2]
    assert _neow_indexes("none", options) == []
    assert _neow_indexes(None, options) == []
    assert _neow_indexes("2", options) == [2]
    assert _neow_indexes(0, options) == [0]
    assert _neow_indexes(" 1 ", options) == [1]
    assert _neow_indexes("first", [{"index": 0, "locked": True}]) == [0]
    assert _neow_indexes("first", []) == []
    assert _neow_indexes("all", []) == []
    for bad in ("nope", "1.5", "None", "", "first "):
        with pytest.raises(PreviewError) as err:
            _neow_indexes(bad, options)
        assert err.value.code == "bad_neow"


def test_seed_warning_codes_and_visible_relic_bags():
    assert seed_warning_codes("abcdefghjklm", "ABCDEFGHJKLM") == [
        {"code": "seedNormalized", "raw": "abcdefghjklm", "canon": "ABCDEFGHJKLM"}]
    assert seed_warning_codes("abcdef", "ABCDEF") == [
        {"code": "seedNormalized", "raw": "abcdef", "canon": "ABCDEF"},
        {"code": "seedLength", "n": 6, "want": 12}]
    assert seed_warning_codes("ABC", "ABC") == [{"code": "seedLength", "n": 3, "want": 12}]
    mixed = seed_warning_codes("ab!", "AB!")
    assert any(w["code"] == "seedNormalized" for w in mixed)
    charset = next(w for w in mixed if w["code"] == "seedCharset")
    assert charset["chars"] == "!"
    assert not any(w["code"] == "seedLength" for w in mixed)
    assert seed_warning_codes("ABCDEFGHJKLM", "ABCDEFGHJKLM") == []

    class Ident:
        def __init__(self, entry):
            self.Entry = entry

    class Relic:
        def __init__(self, entry):
            self.Id = Ident(entry)

    class Bag:
        def __init__(self, ids):
            self._relics = [Relic(i) for i in ids]

    player = type("P", (), {"Relics": [Relic("RELIC.START")], "RelicGrabBag": Bag(["RELIC.CHAR"])})()
    state = type("S", (), {"SharedRelicGrabBag": Bag(["RELIC.SHARED"])})()
    got = peek_relics(state, player)
    assert got == {"starting": ["RELIC.START"], "shared_queue": ["RELIC.SHARED"], "character_queue": ["RELIC.CHAR"]}
    res = assemble("A", "A", [], "Ironclad", 0, [], [], [], None, [], {}, got)
    assert not any(w["code"] == "relicQueueHidden" for w in res["warnings"])


@pytest.mark.parametrize("seed,char,asc,code", [
    ("   ", "Ironclad", 0, "need_seed"),
    ("ABC", "ironclad", 0, "bad_char"),
    ("ABC", "Ironclad", -1, "bad_asc"),
    ("ABC", "Ironclad", 11, "bad_asc"),
    ("ABC", "Ironclad", "no", "bad_asc"),
])
def test_preview_rejects_before_the_engine(seed, char, asc, code):
    with pytest.raises(PreviewError) as err:
        preview(seed, char, asc, neow="all")
    assert err.value.code == code


class _Ident:
    def __init__(self, entry):
        self.Entry = entry


class _Act:
    def __init__(self, entry):
        self.Id = _Ident(entry)


class _Relic:
    def __init__(self, entry):
        self.Id = _Ident(entry)


class _Mgr:
    def __init__(self, fail_act):
        self.fail_act = fail_act

    def SetActInternal(self, i):
        if self.fail_act is not None and i == self.fail_act:
            raise RuntimeError("map boom")


class _Driver:
    def __init__(self, fail_act=None):
        self.state = type("S", (), {"Acts": [_Act("ACT.SAMPLE_ONE"), _Act("ACT.SAMPLE_TWO")], "SharedRelicGrabBag": None})()
        self.player = type("P", (), {"Relics": [_Relic("RELIC.SAMPLE_START")]})()
        self.mgr = _Mgr(fail_act)

    def _create(self):
        return None


class _Probe:
    def __init__(self):
        self.calls = []

    def _rooms(self, state):
        return [
            {"act": "ACT.SAMPLE_ONE", "boss": "ENCOUNTER.SAMPLE_BOSS", "second_boss": None,
             "ancient": "EVENT.SAMPLE_START", "normal": ["ENCOUNTER.A", "ENCOUNTER.A"], "elite": ["ENCOUNTER.E"], "events": []},
            {"act": "ACT.SAMPLE_TWO", "boss": "ENCOUNTER.SAMPLE_BOSS2", "second_boss": "ENCOUNTER.SAMPLE_BOSS3",
             "ancient": None, "normal": [], "elite": [], "events": []},
        ]

    def _map(self, game, state):
        return {"cols": 2, "boss": {"col": 0, "row": 2},
                "rows": [[{"col": 0, "row": 1, "type": "Monster"}, {"col": 1, "row": 1, "type": "Unknown"}]]}

    def _build(self, char, asc, canon, neow=None):
        self.calls.append(neow)
        keys = ["EVENT.SAMPLE.LOCKED", "EVENT.SAMPLE.FIRST", "EVENT.SAMPLE.SECOND"]
        locked = [True, False, False]
        return object(), {"ancient": "EVENT.SAMPLE_START", "options": keys, "locked": locked}, object()

    def _rewards(self, game, driver):
        return {"encounter": "ENCOUNTER.A", "rewards": [{"cards": ["CARD.SAMPLE"], "gold": 10}]}


def _use_stub(monkeypatch, fail_act=None):
    import types
    probe = _Probe()
    boot = types.ModuleType("sts2sim.rt.boot")
    boot.game = object()
    monkeypatch.setitem(sys.modules, "sts2sim.rt.boot", boot)
    monkeypatch.setattr("sts2sim.engine.seedpreview._tools", lambda: probe)
    monkeypatch.setattr("sts2sim.engine.seedpreview._fresh", lambda char, asc, seed: _Driver(fail_act))
    return probe


def _block_engine(monkeypatch):
    monkeypatch.setitem(sys.modules, "sts2sim.rt.boot", None)


def test_stubbed_preview_applies_neow_without_a_game(monkeypatch):
    _use_stub(monkeypatch)
    none = preview("oooooooooooo", "Silent", 10, neow="none")
    assert none["seed"] == "000000000000" and none["ascension"] == 10 and none["character"] == "Silent"
    assert any(w["code"] == "seedNormalized" for w in none["warnings"])
    assert not any(w["code"] in ("seedCharset", "seedLength") for w in none["warnings"])
    assert none["after_neow"] == {}
    assert none["maps"][0]["confidence"] == "act_entry"
    assert none["maps"][1]["confidence"] == "projected"
    assert none["maps"][0]["counts"]["Monster"] == 1 and none["maps"][0]["counts"]["Boss"] == 1
    assert none["relics"]["starting"] == ["RELIC.SAMPLE_START"]
    assert any(w["code"] == "relicQueueHidden" for w in none["warnings"])
    assert "later_act_maps_projected" in none["limits"]
    assert none["distribution"][0]["normal_counts"][0] == {"id": "ENCOUNTER.A", "n": 2}
    text = format_text(none, "en")
    assert "000000000000" in text and "Projected without playing the previous act" in text
    assert "After choice" not in text

    first = preview("ABCDEFGHJKLM", "Ironclad", "0", neow="first")
    assert first["ascension"] == 0 and set(first["after_neow"]) == {"1"}
    assert first["after_neow"]["1"]["encounter"] == "ENCOUNTER.A"
    chosen = preview("ABCDEFGHJKLM", "Defect", 0, neow="2")
    assert set(chosen["after_neow"]) == {"2"}
    every = preview("ABCDEFGHJKLM", "Regent", 0, neow="all")
    assert set(every["after_neow"]) == {"0", "1", "2"}
    with pytest.raises(PreviewError) as bad:
        preview("ABCDEFGHJKLM", "Necrobinder", 0, neow="nope")
    assert bad.value.code == "bad_neow"


def test_stubbed_preview_keeps_the_other_act_when_one_map_fails(monkeypatch):
    _use_stub(monkeypatch, fail_act=1)
    res = preview("ABCDEFGHJKLM", "Ironclad", 0, neow="none")
    assert res["maps"][0]["confidence"] == "act_entry" and res["maps"][0]["rows"]
    assert res["maps"][1]["confidence"] == "failed" and "map boom" in res["maps"][1]["error"]
    assert len(res["distribution"]) == 2 and res["acts"] == ["ACT.SAMPLE_ONE", "ACT.SAMPLE_TWO"]


def test_no_engine_error_is_deterministic(monkeypatch):
    _block_engine(monkeypatch)
    seen = []
    for _ in range(2):
        with pytest.raises(PreviewError) as err:
            preview("ABCDEFGHJKLM", "Silent", 0, neow="all")
        seen.append((err.value.code, err.value.params["err"]))
    assert seen[0] == seen[1] == (
        "no_engine", "import of sts2sim.rt.boot halted; None in sys.modules")


def _preview_cli():
    import importlib.util
    name = "deckbench_seed_preview_cli"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "seed_preview.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_preview_cli_rejects_bad_args_before_the_engine(capsys):
    cli = _preview_cli()
    with pytest.raises(SystemExit) as missing:
        cli.main([])
    assert missing.value.code == 2
    with pytest.raises(SystemExit) as char:
        cli.main(["ABCDEFGHJKLM", "--char", "Nope", "--lang", "en"])
    assert char.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err and "Nope" in err
    with pytest.raises(SystemExit) as asc:
        cli.main(["ABCDEFGHJKLM", "--asc", "no", "--lang", "en"])
    assert asc.value.code == 2
    assert cli.main(["", "--lang", "en"]) == 2
    assert "Enter a seed first." in capsys.readouterr().err
    assert cli.main(["ABCDEFGHJKLM", "--asc", "99", "--lang", "en"]) == 2
    assert "Ascension must be from 0 to 10." in capsys.readouterr().err
    assert cli.main(["ABCDEFGHJKLM", "--asc", "-1", "--neow", "all", "--lang", "en"]) == 2
    assert "Ascension must be from 0 to 10." in capsys.readouterr().err


def test_preview_cli_neow_with_stub(tmp_path, monkeypatch, capsys):
    cli = _preview_cli()
    probe = _use_stub(monkeypatch)
    assert cli.main(["ABCDEFGHJKLM", "--neow", "first", "--lang", "en"]) == 0
    first = capsys.readouterr().out
    assert "After choice [1]" in first and "After choice [0]" not in first
    assert "(locked)" in first and "FIRST" in first
    assert probe.calls == [None, 1]
    assert cli.main(["ABCDEFGHJKLM", "--neow", "all", "--lang", "en"]) == 0
    every = capsys.readouterr().out
    assert "After choice [0]" in every and "After choice [1]" in every and "After choice [2]" in every
    assert cli.main(["ABCDEFGHJKLM", "--neow", "none", "--lang", "en"]) == 0
    assert "After choice" not in capsys.readouterr().out
    out = tmp_path / "preview.json"
    assert cli.main(["ABCDEFGHJKLM", "--neow", "2", "--json", str(out), "--lang", "en"]) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert set(saved["after_neow"]) == {"2"}
    assert "ABCDEFGHJKLM" in capsys.readouterr().out
    missing = tmp_path / "no.json"
    assert cli.main(["ABCDEFGHJKLM", "--neow", "nope", "--json", str(missing), "--lang", "en"]) == 2
    assert "first, all, none, or an index" in capsys.readouterr().err
    assert not missing.exists()


def test_preview_cli_no_engine_message_is_stable(monkeypatch, capsys):
    cli = _preview_cli()
    _block_engine(monkeypatch)
    assert cli.main(["ABCDEFGHJKLM", "--neow", "all", "--lang", "en"]) == 2
    first = capsys.readouterr().err
    assert cli.main(["ABCDEFGHJKLM", "--neow", "none", "--lang", "en"]) == 2
    second = capsys.readouterr().err
    assert first == second
    assert "Local game logic is not generated yet" in first
    assert "import of sts2sim.rt.boot halted; None in sys.modules" in first


def test_preview_api_validates_neow_and_no_engine(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from gui.server import app
    client = TestClient(app)
    headers = {"x-lang": "en"}

    def post(**body):
        return client.post("/api/seed-preview", headers=headers, json=body)

    _block_engine(monkeypatch)
    blocked = post(seed="ABCDEFGHJKLM", char="Ironclad", asc=0, neow="nope")
    assert blocked.status_code == 400
    assert "Local game logic is not generated yet" in blocked.json()["detail"]
    assert "bad_neow" not in blocked.json()["detail"]
    again = post(seed="ABCDEFGHJKLM", char="Ironclad", asc=0, neow="first")
    assert again.status_code == 400 and again.json()["detail"] == blocked.json()["detail"]

    _use_stub(monkeypatch)
    for neow, keys in (("first", {"1"}), ("all", {"0", "1", "2"}), ("none", set()), ("2", {"2"})):
        res = post(seed="ABCDEFGHJKLM", char="Ironclad", asc=0, neow=neow)
        assert res.status_code == 200, (neow, res.text)
        assert set(res.json()["after_neow"]) == keys
    bad = post(seed="ABCDEFGHJKLM", char="Ironclad", asc=0, neow="nope")
    assert bad.status_code == 400 and "first, all, none, or an index" in bad.json()["detail"]
    asc = post(seed="ABCDEFGHJKLM", char="Ironclad", asc=11, neow="none")
    assert asc.status_code == 400 and "Ascension must be from 0 to 10." in asc.json()["detail"]
    char = post(seed="ABCDEFGHJKLM", char="ironclad", asc=0, neow="none")
    assert char.status_code == 400 and "ironclad" in char.json()["detail"]
    empty = post(seed="   ", char="Ironclad", asc=0, neow="all")
    assert empty.status_code == 400 and "Enter a seed first." in empty.json()["detail"]
    high = post(seed="oooooooooooo", char="Silent", asc=10, neow="none")
    assert high.status_code == 200 and high.json()["seed"] == "000000000000" and high.json()["ascension"] == 10
