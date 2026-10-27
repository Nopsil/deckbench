"""#/import 和 #/preview 走的 HTTP 接口。夹具和内存桩，不需要本机游戏安装。"""
import os
import sys
import types

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from gui.server import app  # noqa: E402
from sts2sim.engine.seedpreview import LIMITS, PUBLIC_KEYS  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "saves")
HIST = os.path.join(FIX, "sample_history.run")
LIVE = os.path.join(FIX, "sample_live.save")
EN = {"x-lang": "en"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _post_import(client, path):
    return client.post("/api/import", headers=EN, json={"path": path})


def _upload(client, path):
    name = os.path.basename(path)
    with open(path, "rb") as f:
        return client.post("/api/import/upload", headers=EN, files={"file": (name, f, "application/octet-stream")})


def test_import_fixture_run_and_save_summaries(client):
    """导入页读的摘要：路径和上传都要给出同一份 .run / .save。"""
    pytest.importorskip("python_multipart")
    by_path = _post_import(client, HIST)
    assert by_path.status_code == 200, by_path.text
    uploaded = _upload(client, HIST)
    assert uploaded.status_code == 200, uploaded.text
    for body in (by_path.json(), uploaded.json()):
        assert body["v"] == 1 and body["kind"] == "run"
        run = body["run"]
        assert run["kind"] == "run_history" and run["schema_version"] == 9
        assert run["seed"] == "SAMPLESEED01" and run["sim_character"] == "Ironclad"
        assert run["ascension"] == 3 and run["result"] == "lost"
        assert run["killed_by_encounter"] == "ENCOUNTER.SAMPLE_BOSS"
        assert [a["id"] for a in run["acts"]] == ["ACT.SAMPLE_ONE", "ACT.SAMPLE_TWO"]
        assert [f["floor"] for f in run["route"]] == [1, 2, 3]
        assert [f["type"] for f in run["route"]] == ["Ancient", "Monster", "Boss"]
        picks = run["route"][1]["picks"][0]["cards"]
        assert [c["id"] for c in picks] == ["CARD.SAMPLE_PICK", "CARD.SAMPLE_SKIP"]
        assert [c["was_picked"] for c in picks] == [True, False]
        assert run["route"][1]["rooms"][0]["model_id"] == "ENCOUNTER.SAMPLE_FIGHT"
        player = run["players"][0]
        assert player["character"] == "CHARACTER.IRONCLAD"
        assert player["relics"][1] == {"id": "RELIC.SAMPLE_CHEST", "floor": 4}
        assert player["deck"][1]["id"] == "CARD.SAMPLE_PICK" and player["deck"][1]["upgraded"] is True
        assert any(w["code"] == "noRouteColumn" for w in run["warnings"])

    live_path = _post_import(client, LIVE)
    assert live_path.status_code == 200, live_path.text
    live_up = _upload(client, LIVE)
    assert live_up.status_code == 200, live_up.text
    for body in (live_path.json(), live_up.json()):
        assert body["kind"] == "run"
        run = body["run"]
        assert run["kind"] == "live_save" and run["schema_version"] == 16
        assert run["seed"] == "LIVESEED0001" and run["seed_source"] == "rng.seed"
        assert run["result"] == "in_progress" and run["sim_character"] == "Silent"
        assert run["players"][0]["current_hp"] == 54
        assert run["players"][0]["relics"][0]["id"] == "RELIC.SAMPLE_RING"
        assert run["visited_map_coords"] == [{"col": 2, "row": 1}, {"col": 1, "row": 2}]
        mp = run["acts"][0]["map"]
        assert mp["boss"] == {"col": 1, "row": 3}
        assert [n["type"] for row in mp["rows"] for n in row] == ["Monster", "Elite"]
        assert any(w["code"] == "seedFromRng" for w in run["warnings"])
        assert any(w["code"] == "liveInProgress" for w in run["warnings"])

    missing = _post_import(client, os.path.join(FIX, "no-such.run"))
    assert missing.status_code == 400
    assert missing.json()["detail"].startswith("Path not found")


def _block_engine(monkeypatch):
    monkeypatch.setitem(sys.modules, "sts2sim.rt.boot", None)


class _Ident:
    def __init__(self, entry):
        self.Entry = entry


class _Probe:
    def _rooms(self, state):
        return [{
            "act": "ACT.SAMPLE_ONE", "boss": "ENCOUNTER.SAMPLE_BOSS", "second_boss": None,
            "ancient": "EVENT.SAMPLE_START", "normal": ["ENCOUNTER.A", "ENCOUNTER.A"],
            "elite": ["ENCOUNTER.E"], "events": [],
        }, {
            "act": "ACT.SAMPLE_TWO", "boss": "ENCOUNTER.SAMPLE_BOSS2", "second_boss": None,
            "ancient": None, "normal": [], "elite": [], "events": [],
        }]

    def _map(self, game, state):
        return {
            "cols": 2, "boss": {"col": 0, "row": 2},
            "rows": [[{"col": 0, "row": 1, "type": "Monster", "children": [[1, 2]]},
                      {"col": 1, "row": 1, "type": "Unknown", "children": []}]],
        }

    def _build(self, char, asc, canon, neow=None):
        return object(), {
            "ancient": "EVENT.SAMPLE_START",
            "options": ["EVENT.SAMPLE.LOCKED", "EVENT.SAMPLE.FIRST"],
            "locked": [True, False],
        }, object()

    def _rewards(self, game, driver):
        return {"encounter": "ENCOUNTER.A", "rewards": [{"cards": ["CARD.SAMPLE"], "gold": 12, "kind": "card"}]}


def _use_stub(monkeypatch):
    boot = types.ModuleType("sts2sim.rt.boot")
    boot.game = object()
    monkeypatch.setitem(sys.modules, "sts2sim.rt.boot", boot)

    class _Mgr:
        def SetActInternal(self, i):
            return None

    driver = type("D", (), {})()
    driver.state = type("S", (), {"Acts": [type("A", (), {"Id": _Ident("ACT.SAMPLE_ONE")})(),
                                            type("A", (), {"Id": _Ident("ACT.SAMPLE_TWO")})()],
                                   "SharedRelicGrabBag": None})()
    driver.player = type("P", (), {"Relics": [type("R", (), {"Id": _Ident("RELIC.SAMPLE_START")})()]})()
    driver.mgr = _Mgr()
    driver._create = lambda: None
    monkeypatch.setattr("sts2sim.engine.seedpreview._tools", lambda: _Probe())
    monkeypatch.setattr("sts2sim.engine.seedpreview._fresh", lambda char, asc, seed: driver)


def test_seed_preview_reports_missing_engine(client, monkeypatch):
    """没有本机游戏逻辑时，预览页拿到的是翻译过的 400，不是 500。"""
    _block_engine(monkeypatch)
    body = {"seed": "ABCDEFGHJKLM", "char": "Ironclad", "asc": 0, "neow": "first"}
    blocked = client.post("/api/seed-preview", headers=EN, json=body)
    assert blocked.status_code == 400, blocked.text
    detail = blocked.json()["detail"]
    assert detail.startswith("Local game logic is not generated yet")
    assert "import of sts2sim.rt.boot halted" in detail
    again = client.post("/api/seed-preview", headers=EN, json=body)
    assert again.status_code == 400 and again.json()["detail"] == detail
    zhs = client.post("/api/seed-preview", headers={"x-lang": "zhs"}, json=body)
    assert zhs.status_code == 400 and zhs.json()["detail"].startswith("还没有本机的游戏逻辑")


def test_seed_preview_stub_json_matches_the_page(client, monkeypatch):
    """预览页绑定的字段：地图置信度、遭遇计数、开局奖励、遗物和 limits。"""
    _use_stub(monkeypatch)
    res = client.post("/api/seed-preview", headers=EN, json={
        "seed": "abcdefghjklm", "char": "Ironclad", "asc": 0, "neow": "first",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == set(PUBLIC_KEYS)
    assert body["v"] == 1
    assert body["seed_input"] == "abcdefghjklm" and body["seed"] == "ABCDEFGHJKLM"
    assert body["character"] == "Ironclad" and body["ascension"] == 0
    assert body["acts"] == ["ACT.SAMPLE_ONE", "ACT.SAMPLE_TWO"]
    assert any(w["code"] == "seedNormalized" for w in body["warnings"])
    assert body["maps"][0]["confidence"] == "act_entry"
    assert body["maps"][1]["confidence"] == "projected"
    assert body["maps"][0]["rows"][0][0] == {"col": 0, "row": 1, "type": "Monster", "children": [[1, 2]]}
    assert body["maps"][0]["counts"]["Monster"] == 1
    assert body["maps"][0]["counts"]["Boss"] == 1
    assert body["maps"][0]["boss"] == {"col": 0, "row": 2}
    dist = body["distribution"][0]
    assert dist["boss"] == "ENCOUNTER.SAMPLE_BOSS"
    assert dist["normal"] == ["ENCOUNTER.A", "ENCOUNTER.A"]
    assert dist["normal_counts"] == [{"id": "ENCOUNTER.A", "n": 2}]
    assert dist["elite"] == ["ENCOUNTER.E"]
    assert body["ancient"] == "EVENT.SAMPLE_START"
    assert body["neow_options"][0]["locked"] is True
    assert body["neow_options"][1]["id"] == "FIRST" and body["neow_options"][1]["locked"] is False
    assert set(body["after_neow"]) == {"1"}
    reward = body["after_neow"]["1"]
    assert reward["encounter"] == "ENCOUNTER.A"
    assert reward["rewards"] == [{"cards": ["CARD.SAMPLE"], "gold": 12, "kind": "card"}]
    assert body["relics"]["starting"] == ["RELIC.SAMPLE_START"]
    assert body["relics"]["shared_queue"] == [] and body["relics"]["character_queue"] == []
    assert body["limits"] == list(LIMITS)
    assert "later_act_maps_projected" in body["limits"]

    none = client.post("/api/seed-preview", headers=EN, json={
        "seed": "ABCDEFGHJKLM", "char": "Silent", "asc": 10, "neow": "none",
    })
    assert none.status_code == 200, none.text
    skipped = none.json()
    assert skipped["character"] == "Silent" and skipped["ascension"] == 10
    assert skipped["after_neow"] == {}
    assert skipped["seed"] == "ABCDEFGHJKLM"


def _tree_bytes(root):
    out = {}
    for dirpath, dirnames, names in os.walk(root):
        dirnames.sort()
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = fh.read()
    return out


def _post_batch(client, path):
    return client.post("/api/import/batch-summary", headers=EN, json={"path": path})


def test_import_folder_batch_summary_matches_cli_shape(client, tmp_path):
    """文件夹导入的批量摘要与 --batch-summary 同形。夹具即可，不安装游戏，也不写盘。"""
    import shutil

    saves = tmp_path / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    shutil.copy(HIST, hist / "sample_history.run")
    (hist / "bad.run").write_bytes(b"\x00nope")
    shutil.copy(LIVE, saves / "current_run.save")
    before = _tree_bytes(saves)
    fixture_before = _tree_bytes(FIX)

    page = open(os.path.join(os.path.dirname(__file__), "..", "gui", "web", "src", "pages", "ImportRun.vue"), encoding="utf-8").read()
    assert "/api/import/batch-summary" in page
    for key in ("imp.batch", "imp.floors", "imp.batchEmpty", "imp.noResult"):
        assert key in page

    rows = [
        {"file": "bad.run", "error": "not_json"},
        {
            "file": "sample_history.run",
            "seed": "SAMPLESEED01",
            "ascension": 3,
            "character": "Ironclad",
            "floors": 3,
            "result": "lost",
        },
    ]
    for path in (str(saves), str(hist)):
        got = _post_batch(client, path)
        assert got.status_code == 200, got.text
        assert got.json() == rows
    assert list(rows[1]) == ["file", "seed", "ascension", "character", "floors", "result"]
    assert list(rows[0]) == ["file", "error"]
    assert all(row.get("file") != "current_run.save" for row in rows)
    folder = _post_import(client, str(saves))
    assert folder.status_code == 200 and folder.json()["kind"] == "folder"
    assert _tree_bytes(saves) == before

    one = _post_batch(client, HIST)
    assert one.status_code == 200, one.text
    assert one.json() == [rows[1] | {"file": "sample_history.run"}]
    assert one.json()[0]["result"] == "lost"
    live = _post_batch(client, LIVE)
    assert live.status_code == 200, live.text
    assert live.json() == [{
        "file": "sample_live.save",
        "seed": "LIVESEED0001",
        "ascension": 0,
        "character": "Silent",
        "floors": 1,
    }]
    assert "result" not in live.json()[0]
    assert _tree_bytes(FIX) == fixture_before

    only = tmp_path / "only-live"
    only.mkdir()
    shutil.copy(LIVE, only / "current_run.save")
    empty_rows = _post_batch(client, str(only))
    assert empty_rows.status_code == 200, empty_rows.text
    assert empty_rows.json() == []

    missing = _post_batch(client, str(tmp_path / "no-such"))
    assert missing.status_code == 400
    assert missing.json()["detail"].startswith("Path not found")
    bare = tmp_path / "empty-dir"
    bare.mkdir()
    bare_res = _post_batch(client, str(bare))
    assert bare_res.status_code == 400
    assert "No .run" in bare_res.json()["detail"]
    assert _tree_bytes(saves) == before
