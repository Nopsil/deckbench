"""对局记录 / 进行中存档的只读解析。夹具是虚构 ID，不是游戏文件。"""
import gzip
import json
import os

import pytest

from sts2sim.saveimport import (
    SaveImportError,
    discover,
    load_path,
    parse_bytes,
    parse_path,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "saves")
HIST = os.path.join(FIX, "sample_history.run")
LIVE = os.path.join(FIX, "sample_live.save")


def test_history_seed_route_picks_relics():
    run = parse_path(HIST)
    assert run["kind"] == "run_history"
    assert run["schema_version"] == 9
    assert run["seed"] == "SAMPLESEED01"
    assert run["ascension"] == 3
    assert run["result"] == "lost"
    assert run["sim_character"] == "Ironclad"
    assert run["killed_by_encounter"] == "ENCOUNTER.SAMPLE_BOSS"
    assert run["killed_by_event"] is None
    assert [a["id"] for a in run["acts"]] == ["ACT.SAMPLE_ONE", "ACT.SAMPLE_TWO"]
    assert [f["type"] for f in run["route"]] == ["Ancient", "Monster", "Boss"]
    assert [f["floor"] for f in run["route"]] == [1, 2, 3]
    assert run["route"][1]["act_index"] == 0 and run["route"][2]["act_index"] == 1
    picks = run["route"][1]["picks"][0]["cards"]
    assert [c["id"] for c in picks] == ["CARD.SAMPLE_PICK", "CARD.SAMPLE_SKIP"]
    assert [c["was_picked"] for c in picks] == [True, False]
    assert run["route"][1]["rooms"][0]["model_id"] == "ENCOUNTER.SAMPLE_FIGHT"
    p = run["players"][0]
    assert p["relics"][1] == {"id": "RELIC.SAMPLE_CHEST", "floor": 4}
    assert p["deck"][1]["upgraded"] is True
    assert p["deck"][1]["enchantment"] == {"id": "ENCHANT.SAMPLE", "amount": 2}
    assert any(w["code"] == "noRouteColumn" for w in run["warnings"])
    assert run["visited_map_coords"] == []


def test_live_save_seed_in_rng_and_map():
    run = parse_path(LIVE)
    assert run["kind"] == "live_save"
    assert run["seed"] == "LIVESEED0001"
    assert run["seed_source"] == "rng.seed"
    assert run["result"] == "in_progress"
    assert run["sim_character"] == "Silent"
    assert run["players"][0]["id"] == 7
    assert run["players"][0]["current_hp"] == 54
    assert run["visited_map_coords"] == [{"col": 2, "row": 1}, {"col": 1, "row": 2}]
    mp = run["acts"][0]["map"]
    assert mp["cols"] == 3
    assert mp["boss"] == {"col": 1, "row": 3}
    types = [n["type"] for row in mp["rows"] for n in row]
    assert types == ["Monster", "Elite"]
    assert any(w["code"] == "seedFromRng" for w in run["warnings"])
    assert any(w["code"] == "liveInProgress" for w in run["warnings"])
    assert not any(w["code"] == "actsObjects" for w in run["warnings"])


def test_pascal_and_camel_keys_and_flat_route():
    raw = {
        "SchemaVersion": 9,
        "Seed": "FLAT",
        "Win": True,
        "WasAbandoned": False,
        "Acts": ["ACT.SAMPLE_ONE"],
        "Players": [{"Id": 1, "Character": "CHARACTER.DEFECT", "Deck": ["CARD.SAMPLE_A"], "Relics": ["RELIC.SAMPLE"]}],
        "MapPointHistory": [
            {"MapPointType": "Shop", "PlayerStats": [], "Rooms": [{"TurnsTaken": 1}]},
        ],
    }
    run = parse_bytes(json.dumps(raw).encode(), filename="x.run")
    assert run["seed"] == "FLAT" and run["result"] == "won"
    assert run["sim_character"] == "Defect"
    assert run["route"][0]["type"] == "Shop"
    assert run["players"][0]["deck"][0]["id"] == "CARD.SAMPLE_A"
    assert run["players"][0]["relics"][0]["id"] == "RELIC.SAMPLE"


def test_history_with_object_acts_warns():
    raw = json.loads(open(HIST, encoding="utf-8").read())
    raw["acts"] = [{"id": "ACT.SAMPLE_ONE", "saved_map": {"mystery": True}}]
    run = parse_bytes(json.dumps(raw).encode(), filename="obj.run")
    assert any(w["code"] == "actsObjects" for w in run["warnings"])
    assert any(w["code"] == "mapUnparsed" for w in run["warnings"])


def test_wrappers_and_rejections(tmp_path):
    raw = open(HIST, "rb").read()
    bom = parse_bytes(b"\xef\xbb\xbf" + raw, filename="b.run")
    assert bom["seed"] == "SAMPLESEED01" and any(w["code"] == "bom" for w in bom["warnings"])
    gz = parse_bytes(gzip.compress(raw), filename="g.run")
    assert gz["seed"] == "SAMPLESEED01" and any(w["code"] == "gzip" for w in gz["warnings"])
    u16 = parse_bytes(raw.decode().encode("utf-16"), filename="u.run")
    assert u16["seed"] == "SAMPLESEED01" and any(w["code"] == "utf16" for w in u16["warnings"])
    wrapped = parse_bytes(json.dumps(raw.decode()).encode(), filename="d.run")
    assert wrapped["seed"] == "SAMPLESEED01" and any(w["code"] == "doubleEncoded" for w in wrapped["warnings"])
    with pytest.raises(SaveImportError) as ei:
        parse_bytes(b"\x00\x01\x02not json", filename="bin.save")
    assert ei.value.code == "not_json"
    with pytest.raises(SaveImportError) as ep:
        parse_bytes(b'{"epochs": [1], "cards": []}', filename="progress.save")
    assert ep.value.code == "not_a_run"
    missing = tmp_path / "nope.run"
    with pytest.raises(SaveImportError) as en:
        parse_path(str(missing))
    assert en.value.code == "not_found"


def test_folder_and_discover(tmp_path, monkeypatch):
    saves = tmp_path / "steam" / "1" / "profile1" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1779550532.run").write_bytes(open(HIST, "rb").read())
    (hist / "1779550532.run.backup").write_bytes(open(HIST, "rb").read())
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read())
    (saves / "progress.save").write_text("{}", encoding="utf-8")
    (hist / "bad.run").write_text("not-json", encoding="utf-8")
    loaded = load_path(str(saves))
    assert loaded["kind"] == "folder"
    names = [e["file"] for e in loaded["entries"]]
    assert names.count("1779550532.run") == 1
    assert "1779550532.run.backup" not in names
    assert "progress.save" not in names
    assert "current_run.save" in names
    bad = next(e for e in loaded["entries"] if e["file"] == "bad.run")
    assert bad["error"]["code"] == "not_json"
    good = next(e for e in loaded["entries"] if e["file"] == "1779550532.run")
    assert good["run"]["seed"] == "SAMPLESEED01"
    # 指到 profile 目录或 history 目录同样能列出来
    assert load_path(str(saves.parent))["kind"] == "folder"
    assert any(e["run"]["seed"] == "SAMPLESEED01" for e in load_path(str(hist))["entries"] if "run" in e)

    monkeypatch.setenv("DECKBENCH_SAVE_ROOTS", str(tmp_path))
    hits = discover()
    assert any(h["path"] == str(saves) and h["history"] == 2 and h["has_current"] for h in hits)


def test_import_and_preview_api():
    pytest.importorskip("fastapi")
    pytest.importorskip("python_multipart")
    from fastapi.testclient import TestClient
    from gui.server import app
    client = TestClient(app)
    up = client.post("/api/import/upload", headers={"x-lang": "en"},
                     files={"file": ("sample_history.run", open(HIST, "rb"), "application/octet-stream")})
    assert up.status_code == 200, up.text
    assert up.json()["run"]["seed"] == "SAMPLESEED01"
    assert up.json()["run"]["route"][1]["picks"][0]["cards"][0]["was_picked"] is True
    missing = client.post("/api/import", headers={"x-lang": "en"}, json={"path": "/no/such/run.run"})
    assert missing.status_code == 400 and "Path not found" in missing.json()["detail"]
    bad = client.post("/api/seed-preview", headers={"x-lang": "en"}, json={"seed": "", "char": "Ironclad", "asc": 0})
    assert bad.status_code == 400 and "seed" in bad.json()["detail"].lower()
    got = client.post("/api/import", headers={"x-lang": "en"}, json={"path": HIST})
    assert got.status_code == 200
    assert got.json()["run"]["players"][0]["relics"][1]["id"] == "RELIC.SAMPLE_CHEST"
    folder = client.post("/api/import", headers={"x-lang": "en"}, json={"path": FIX})
    assert folder.status_code == 200
    assert any(e.get("run", {}).get("seed") == "SAMPLESEED01" for e in folder.json()["entries"])
    junk = client.post("/api/import/upload", headers={"x-lang": "en"},
                       files={"file": ("broken.run", b"{not json", "application/octet-stream")})
    assert junk.status_code == 400
    detail = junk.json()["detail"]
    assert isinstance(detail, str) and "JSON" in detail and "Expecting" in detail
    settings = client.post("/api/import/upload", headers={"x-lang": "en"},
                           files={"file": ("settings.save", b'{"lang":"en"}', "application/octet-stream")})
    assert settings.status_code == 400 and "not one run" in settings.json()["detail"]


def test_abandoned_and_multiplayer_second_player():
    raw = {
        "seed": "MP",
        "win": False,
        "was_abandoned": True,
        "acts": ["ACT.SAMPLE_ONE"],
        "players": [
            {"id": 1, "character": "CHARACTER.REGENT", "deck": [], "relics": [], "potions": []},
            {"id": 2, "character": "CHARACTER.NECROBINDER", "deck": [], "relics": [{"id": "RELIC.SAMPLE"}], "potions": []},
        ],
        "map_point_history": [],
    }
    run = parse_bytes(json.dumps(raw).encode(), filename="mp.run")
    assert run["result"] == "abandoned"
    assert [p["sim_character"] for p in run["players"]] == ["Regent", "Necrobinder"]
    assert run["players"][1]["relics"][0]["id"] == "RELIC.SAMPLE"
