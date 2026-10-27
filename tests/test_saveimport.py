"""对局记录 / 进行中存档的只读解析。夹具是虚构 ID，不是游戏文件。"""
import gzip
import json
import os
import sys

import pytest

from sts2sim.saveimport import (
    SaveImportError,
    candidate_roots,
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


def _history(**over):
    doc = {
        "schema_version": 9,
        "seed": "HISTORYSEED1",
        "ascension": 1,
        "win": False,
        "was_abandoned": False,
        "acts": ["ACT.SAMPLE_ONE"],
        "players": [{"id": 1, "character": "CHARACTER.IRONCLAD", "deck": [], "relics": [], "potions": []}],
        "map_point_history": [],
    }
    doc.update(over)
    return doc


def _live(**over):
    doc = {
        "schema_version": 16,
        "ascension": 0,
        "rng": {"seed": "LIVESEED0001"},
        "current_act_index": 0,
        "players": [{
            "net_id": 7, "character_id": "CHARACTER.SILENT", "current_hp": 54,
            "deck": [], "relics": [], "potions": [],
        }],
        "acts": [{"id": "ACT.SAMPLE_ONE"}],
        "map_point_history": [],
    }
    doc.update(over)
    return doc


def _utf16(payload, endian):
    text = payload.decode("utf-8")
    if endian == "le":
        return text.encode("utf-16")
    return b"\xfe\xff" + text.encode("utf-16-be")


def _codes(run):
    return [w["code"] for w in run["warnings"]]


def test_gzip_and_utf16_encodings(tmp_path):
    raw = open(HIST, "rb").read()
    live = open(LIVE, "rb").read()
    gz = parse_bytes(gzip.compress(raw), filename="h.run")
    assert gz["kind"] == "run_history" and gz["seed"] == "SAMPLESEED01"
    assert "gzip" in _codes(gz) and "utf16" not in _codes(gz)
    both = parse_bytes(gzip.compress(_utf16(raw, "le")), filename="h.run")
    assert _codes(both)[:2] == ["gzip", "utf16"]
    assert both["kind"] == "run_history" and both["schema_version"] == 9
    be = parse_bytes(_utf16(live, "be"), filename="current_run.save")
    assert be["kind"] == "live_save" and be["seed"] == "LIVESEED0001" and be["seed_source"] == "rng.seed"
    assert "utf16" in _codes(be) and "gzip" not in _codes(be)
    bom = parse_bytes(gzip.compress(b"\xef\xbb\xbf" + raw), filename="h.run")
    assert "gzip" in _codes(bom) and "bom" in _codes(bom) and bom["seed"] == "SAMPLESEED01"
    # UTF-16 without a BOM is full of NULs; that is binary, not a text save.
    with pytest.raises(SaveImportError) as naked:
        parse_bytes(raw.decode("utf-8").encode("utf-16-le"), filename="h.run")
    assert naked.value.code == "not_json"
    on_disk = tmp_path / "sample.run"
    on_disk.write_bytes(gzip.compress(raw))
    assert parse_path(str(on_disk))["seed"] == "SAMPLESEED01"
    save = tmp_path / "current_run.save"
    save.write_bytes(_utf16(live, "le"))
    got = parse_path(str(save))
    assert got["kind"] == "live_save" and got["filename"] == "current_run.save"
    # gzip does not turn a progress file into a run, and it is not reported as binary.
    with pytest.raises(SaveImportError) as progress:
        parse_bytes(gzip.compress(b'{"epochs":[1],"cards":[]}'), filename="x.run")
    assert progress.value.code == "not_a_run"


def test_corrupt_payloads_use_stable_error_codes(tmp_path, monkeypatch):
    samples = [
        (b"", "not_json"),
        (b" \n\t", "not_json"),
        (b'{"seed":', "not_json"),
        (b"[1, 2]", "not_object"),
        (b'{"hello": 1}', "unknown_shape"),
        (b"{}", "unknown_shape"),
        (b"\x00\x01\x02", "not_json"),
        (b'{"a": "\xff"}', "decode"),
        (b"\x1f\x8b\x08\x00bad", "not_json"),
        (json.dumps("not json").encode(), "not_json"),
    ]
    for payload, code in samples:
        with pytest.raises(SaveImportError) as err:
            parse_bytes(payload, filename="x.run")
        assert err.value.code == code, payload
    for name in ("progress.save", "prefs.save", "settings.save", "profile.save"):
        with pytest.raises(SaveImportError) as named:
            parse_bytes(b'{"volume": 1}', filename=name)
        assert named.value.code == "not_a_run"
    with pytest.raises(SaveImportError) as epochs:
        parse_bytes(b'{"epochs": [1], "cards": []}', filename="1.run")
    assert epochs.value.code == "not_a_run"
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 16)
    with pytest.raises(SaveImportError) as big:
        parse_bytes(b'{"seed":"ABCDEFGHIJKLMNOPQRSTUVWXYZ"}', filename="big.run")
    assert big.value.code == "too_big"
    with pytest.raises(SaveImportError) as missing:
        load_path(str(tmp_path / "no" / "such.run"))
    assert missing.value.code == "not_found"
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "progress.save").write_text("{}", encoding="utf-8")
    (empty / "notes.txt").write_text("no", encoding="utf-8")
    with pytest.raises(SaveImportError) as dire:
        load_path(str(empty))
    assert dire.value.code == "dir_empty" and dire.value.params["path"]
    with pytest.raises(SaveImportError) as notfile:
        parse_path(str(empty))
    assert notfile.value.code == "not_found"


@pytest.mark.parametrize("shape,op,result", [
    ("history", "win", "won"),
    ("history", "lose", "lost"),
    ("history", "abandon", "abandoned"),
    ("history", "open", "in_progress"),
    ("live", "open", "in_progress"),
    ("live", "lose", "lost"),
    ("live", "win", "won"),
])
def test_result_flags_distinguish_live_and_history(shape, op, result):
    doc = _history() if shape == "history" else _live()
    if op == "win":
        doc.update(win=True, was_abandoned=True)
    elif op == "lose":
        doc.update(win=False, was_abandoned=False)
    elif op == "abandon":
        doc.update(win=False, was_abandoned=True)
    else:
        doc.pop("win", None)
        doc.pop("was_abandoned", None)
    filename = "1779550532.run" if shape == "history" else "current_run.save"
    run = parse_bytes(json.dumps(doc).encode(), filename=filename)
    assert run["result"] == result
    if shape == "history":
        assert run["kind"] == "run_history" and run["schema_version"] == 9
        assert "noRouteColumn" in _codes(run) and "liveInProgress" not in _codes(run)
        assert run["visited_map_coords"] == []
    else:
        assert run["kind"] == "live_save" and run["schema_version"] == 16
        assert "liveInProgress" in _codes(run) and "noRouteColumn" not in _codes(run)
        assert "seedFromRng" in _codes(run) and run["seed_source"] == "rng.seed"


def test_shape_follows_json_not_the_filename():
    live_named_run = parse_bytes(json.dumps(_live()).encode(), filename="1779550532.run")
    assert live_named_run["kind"] == "live_save" and live_named_run["result"] == "in_progress"
    hist_named_save = parse_bytes(json.dumps(_history()).encode(), filename="current_run.save")
    assert hist_named_save["kind"] == "run_history" and hist_named_save["result"] == "lost"
    assert hist_named_save["seed_source"] == "seed"
    bare = parse_bytes(json.dumps({
        "seed": "  ONLYSEED0001  ",
        "players": [{"character": "CHARACTER.SILENT"}],
    }).encode(), filename="x.run")
    assert bare["seed"] == "ONLYSEED0001" and bare["players"][0]["sim_character"] == "Silent"
    assert bare["route"] == [] and bare["players"][0]["deck"] == [] and bare["players"][0]["relics"] == []
    assert _codes(bare) == ["noRouteColumn"]
    missing = parse_bytes(json.dumps({
        "players": [{"character": "CHARACTER.IRONCLAD"}],
        "map_point_history": [],
    }).encode(), filename="x.run")
    assert missing["seed"] is None and missing["seed_source"] is None and "seedMissing" in _codes(missing)
    no_rng = _live()
    no_rng.pop("rng")
    nosed = parse_bytes(json.dumps(no_rng).encode(), filename="current_run.save")
    assert nosed["seed"] is None and "seedMissing" in _codes(nosed) and "seedFromRng" not in _codes(nosed)
    padded = _live()
    padded["rng"] = {"seed": "  LIVESEED0001  "}
    padded_run = parse_bytes(json.dumps(padded).encode(), filename="current_run.save")
    assert padded_run["seed"] == "LIVESEED0001" and padded_run["seed_source"] == "rng.seed"
    strings = _live()
    strings["acts"] = ["ACT.SAMPLE_ONE"]
    string_acts = parse_bytes(json.dumps(strings).encode(), filename="current_run.save")
    assert string_acts["kind"] == "live_save"
    assert "actsObjects" not in _codes(string_acts) and "mapUnparsed" not in _codes(string_acts)


def test_route_players_and_saved_map_edges():
    doc = _history(
        seed="ROUTESEED001",
        players=[{
            "character": {"entry": "DEFECT"},
            "deck": [
                "CARD.SAMPLE_A",
                {"id": "CARD.SAMPLE_B", "floor_added_to_deck": "2", "is_upgraded": True,
                 "enchantment": {"id": "ENCHANT.SAMPLE", "amount": "nope"}},
                {"id": "CARD.SAMPLE_C", "upgrade_level": "2"},
                "NONE.NONE",
            ],
            "relics": ["RELIC.SAMPLE", {"id": "NONE.NONE"}, {"relic": "RELIC.BOX", "floor": 4}],
            "potions": [{"id": "POTION.SAMPLE", "slot": "1"}, "POTION.OTHER"],
        }, {"id": 9, "character": "Necrobinder"}],
        acts=["ACT.ONE", "ACT.TWO"],
        map_point_history=[
            [
                {"mapPointType": "Ancient", "playerStats": [], "rooms": [{"turnsTaken": 1}]},
                {"map_point_type": "monster", "player_stats": [{
                    "player_id": 1, "current_hp": 40, "max_hp": 70, "current_gold": 12, "damage_taken": 5,
                    "card_choices": [
                        {"card": {"id": "CARD.TAKE"}, "was_picked": True},
                        "CARD.BARE",
                    ],
                    "potion_choices": [{"choice": "POTION.SAMPLE", "was_picked": False}],
                    "relic_choices": [{"relic": {"id": "RELIC.OFFER"}, "picked": 1}],
                }], "rooms": [{
                    "model_id": "ENCOUNTER.SAMPLE_FIGHT",
                    "monster_ids": ["MONSTER.SAMPLE", "NONE.NONE"],
                    "turns_taken": 3,
                    "room_type": "Monster",
                }]},
            ],
            [{"point_type": "MAP.Shop", "rooms": [{"turns_taken": 0}]}],
        ],
        modifiers=["MODIFIER.SAMPLE", {"id": "NONE.NONE"}, {"id": "MODIFIER.OTHER"}],
        killed_by_event="NONE.NONE",
        build_id=12,
        game_mode="standard",
        future_key={"ignored": True},
    )
    doc.pop("ascension")
    doc["ascension_level"] = 4
    run = parse_bytes(json.dumps(doc).encode(), filename="route.run")
    assert run["ascension"] == 4 and run["build_id"] is None and run["game_mode"] == "standard"
    assert run["killed_by_event"] is None
    assert run["sim_character"] == "Defect"
    assert [p["id"] for p in run["players"]] == [1, 9]
    assert [p["sim_character"] for p in run["players"]] == ["Defect", "Necrobinder"]
    deck = run["players"][0]["deck"]
    assert [c["id"] for c in deck] == ["CARD.SAMPLE_A", "CARD.SAMPLE_B", "CARD.SAMPLE_C"]
    assert deck[1]["floor"] == 2 and deck[1]["upgraded"] is True
    assert deck[1]["enchantment"] == {"id": "ENCHANT.SAMPLE", "amount": None}
    assert deck[2]["upgraded"] is True
    relics = run["players"][0]["relics"]
    assert relics == [{"id": "RELIC.SAMPLE", "floor": None}, {"id": "RELIC.BOX", "floor": 4}]
    assert run["players"][0]["potions"] == [
        {"id": "POTION.SAMPLE", "slot": 1}, {"id": "POTION.OTHER", "slot": None},
    ]
    assert [m["id"] for m in run["modifiers"]] == ["MODIFIER.SAMPLE", "MODIFIER.OTHER"]
    assert [(f["floor"], f["act_index"], f["index_in_act"], f["type"]) for f in run["route"]] == [
        (1, 0, 1, "Ancient"), (2, 0, 2, "monster"), (3, 1, 1, "Shop"),
    ]
    fight = run["route"][1]
    assert fight["act"] == "ACT.ONE"
    assert fight["stats"] == [{"player_id": 1, "current_hp": 40, "max_hp": 70, "gold": 12, "damage_taken": 5}]
    assert fight["picks"][0]["cards"][0]["was_picked"] is True
    assert fight["picks"][0]["cards"][1] == {"id": "CARD.BARE", "was_picked": False}
    assert fight["potion_picks"][0]["potions"][0]["was_picked"] is False
    assert fight["relic_picks"][0]["relics"][0]["was_picked"] is True
    assert fight["rooms"][0]["monster_ids"] == ["MONSTER.SAMPLE"]
    shop = run["route"][2]["rooms"][0]
    assert shop["model_id"] is None and shop["turns_taken"] == 0
    assert _codes(run) == ["noRouteColumn"]

    rows = {"rows": [[{"col": 0, "row": 1, "type": "Shop"}]], "cols": 1, "boss": {"col": 0, "row": 3}}
    live = _live(
        visited_map_coords=[{"col": 1, "row": 2}, {"coord": {"col": "3", "row": "4"}}, {"col": None, "row": 1}, "nope"],
        acts=[
            {"id": "ACT.ONE", "saved_map": rows},
            {"id": "ACT.TWO", "saved_map": {"points": [
                {"coord": {"col": 0, "row": 1}, "point_type": "Monster",
                 "children": [{"col": 1, "row": 2}, {"coord": {"col": 2, "row": 2}}]},
                {"coord": {"col": 1, "row": 3}, "point_type": "Boss", "children": []},
            ]}},
            {"id": "ACT.BAD", "saved_map": {"mystery": True}},
            {"id": "ACT.EMPTY", "saved_map": {}},
            {"id": "ACT.NONE", "saved_map": {"points": []}},
        ],
    )
    parsed = parse_bytes(json.dumps(live).encode(), filename="current_run.save")
    assert parsed["visited_map_coords"] == [{"col": 1, "row": 2}, {"col": 3, "row": 4}]
    assert parsed["acts"][0]["map"] == rows
    grid = parsed["acts"][1]["map"]
    assert grid["boss"] == {"col": 1, "row": 3}
    assert grid["rows"][0][0]["children"] == [[1, 2], [2, 2]]
    assert grid["cols"] == 2
    assert "mapUnparsed" not in [w["code"] for w in parsed["warnings"] if w.get("act") in ("ACT.ONE", "ACT.TWO", "ACT.EMPTY")]
    unparsed = [w["act"] for w in parsed["warnings"] if w["code"] == "mapUnparsed"]
    assert unparsed == ["ACT.BAD", "ACT.NONE"]
    assert "actsObjects" not in _codes(parsed)
    mixed = _history()
    mixed["acts"] = ["ACT.SAMPLE_ONE", {"id": "ACT.SAMPLE_TWO", "saved_map": {"mystery": True}}]
    mix = parse_bytes(json.dumps(mixed).encode(), filename="mix.run")
    assert {"actsMixed", "actsObjects", "mapUnparsed"} <= set(_codes(mix))


def test_folder_encodings_backups_and_truncation(tmp_path, monkeypatch):
    saves = tmp_path / "steam" / "1" / "profile1" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1779550532.run").write_bytes(gzip.compress(open(HIST, "rb").read()))
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read().decode("utf-8").encode("utf-16"))
    (saves / "progress.save").write_text(json.dumps({"epochs": [1]}), encoding="utf-8")
    (hist / "corrupt.run").write_bytes(b"\x1f\x8bnot-gzip")
    doc = load_path(str(saves))
    by = {e["file"]: e for e in doc["entries"]}
    assert "progress.save" not in by
    history = by["1779550532.run"]
    assert history["role"] == "history" and history["run"]["kind"] == "run_history"
    assert history["run"]["schema_version"] == 9 and history["run"]["result"] == "lost"
    assert "gzip" in _codes(history["run"]) and "noRouteColumn" in _codes(history["run"])
    assert "seedFromRng" not in _codes(history["run"]) and "liveInProgress" not in _codes(history["run"])
    assert history["run"]["visited_map_coords"] == []
    live = by["current_run.save"]["run"]
    assert live["kind"] == "live_save" and live["schema_version"] == 16 and live["result"] == "in_progress"
    assert live["seed_source"] == "rng.seed" and live["visited_map_coords"]
    assert "utf16" in _codes(live) and "liveInProgress" in _codes(live) and "actsObjects" not in _codes(live)
    assert "noRouteColumn" not in _codes(live)
    assert by["corrupt.run"]["error"]["code"] == "not_json"

    (hist / "1.run").write_text(json.dumps(_history(seed="ONE")), encoding="utf-8")
    (hist / "1.run.backup").write_text(json.dumps(_history(seed="HIDDEN")), encoding="utf-8")
    (hist / "2.run.bak").write_text(json.dumps(_history(seed="BAK")), encoding="utf-8")
    (hist / "notes.txt").write_text("ignore", encoding="utf-8")
    (saves / "current_run_mp.save").write_text(json.dumps(_live(rng={"seed": "MPSEED000001"})), encoding="utf-8")
    listed = {e["file"]: e for e in load_path(str(hist))["entries"]}
    assert "1.run.backup" not in listed and "notes.txt" not in listed and "progress.save" not in listed
    assert listed["1.run"]["run"]["seed"] == "ONE"
    assert listed["2.run.bak"]["role"] == "history" and listed["2.run.bak"]["run"]["seed"] == "BAK"
    assert listed["current_run_mp.save"]["role"] == "current_mp"
    assert listed["current_run_mp.save"]["run"]["kind"] == "live_save"
    assert listed["current_run_mp.save"]["run"]["seed"] == "MPSEED000001"
    os.remove(saves / "current_run.save")
    (saves / "current_run.save.backup").write_text(json.dumps(_live()), encoding="utf-8")
    backup = {e["file"]: e for e in load_path(str(saves))["entries"]}["current_run.save.backup"]
    assert backup["role"] == "current" and backup["run"]["kind"] == "live_save"
    assert "backup" in _codes(backup["run"]) and "liveInProgress" in _codes(backup["run"])

    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "a.run").write_text(json.dumps(_history(seed="LOOSE")), encoding="utf-8")
    (loose / "a.txt").write_text("no", encoding="utf-8")
    (loose / "progress.save").write_text("{}", encoding="utf-8")
    loose_doc = load_path(str(loose))
    assert [e["file"] for e in loose_doc["entries"]] == ["a.run"]
    assert loose_doc["entries"][0]["role"] == "history" and loose_doc["entries"][0]["run"]["seed"] == "LOOSE"

    monkeypatch.setattr("sts2sim.saveimport.MAX_FILES", 2)
    capped = load_path(str(saves))
    assert any(w["code"] == "truncated" and w["n"] == 2 for w in capped["warnings"])
    assert len(capped["entries"]) == 2


def test_discover_stubs_skip_logs_and_do_not_read(tmp_path, monkeypatch):
    present = tmp_path / "present"
    present.mkdir()
    missing = tmp_path / "missing"
    afile = tmp_path / "file.txt"
    afile.write_text("x", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_SAVE_ROOTS", os.pathsep.join([
        str(present), str(present), str(missing), str(afile), "",
    ]))
    roots = candidate_roots()
    assert roots.count(os.path.abspath(str(present))) == 1
    assert os.path.abspath(str(missing)) not in roots
    assert os.path.abspath(str(afile)) not in roots

    root = tmp_path / "library"
    saves = root / "steam" / "99" / "profile1" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1.run").write_text("not-json", encoding="utf-8")
    (hist / "1.run.backup").write_text("{}", encoding="utf-8")
    (saves / "current_run_mp.save").write_bytes(b"\x00binary")
    for hidden in (root / "logs" / "saves" / "history", root / "replay" / "saves" / "history"):
        hidden.mkdir(parents=True)
        (hidden / "9.run").write_text("{}", encoding="utf-8")
    modded = root / "modded" / "profile2" / "saves"
    (modded / "history").mkdir(parents=True)
    (modded / "history" / "3.run").write_text("{}", encoding="utf-8")
    (modded / "history" / "4.run").write_text("{}", encoding="utf-8")
    (modded / "current_run.save").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sts2sim.saveimport.candidate_roots", lambda: [str(root)])
    hits = {os.path.abspath(h["path"]): h for h in discover()}
    assert set(hits) == {os.path.abspath(str(saves)), os.path.abspath(str(modded))}
    assert hits[os.path.abspath(str(saves))]["history"] == 1
    assert hits[os.path.abspath(str(saves))]["has_current"] is True
    assert hits[os.path.abspath(str(modded))]["history"] == 2
    assert hits[os.path.abspath(str(modded))]["has_current"] is True


def _import_cli():
    import importlib.util
    name = "deckbench_import_run_cli"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "import_run.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_import_cli_errors_discover_and_kind_text(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    # JSON 不能写进直接放着 .run / .save 的目录。样本文件放在子目录里。
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    out = tmp_path / "out.json"
    assert cli.main([HIST, "--json", str(out), "--lang", "en"]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["kind"] == "run" and doc["run"]["kind"] == "run_history" and doc["run"]["schema_version"] == 9

    bad = scratch / "bad.run"
    bad.write_bytes(b"\x00\x01")
    assert cli.main([str(bad), "--lang", "en"]) == 2
    assert "not a text JSON" in capsys.readouterr().err
    assert cli.main([str(scratch / "missing.run"), "--lang", "en"]) == 2
    assert "Path not found" in capsys.readouterr().err
    prefs = scratch / "prefs.save"
    prefs.write_text("{}", encoding="utf-8")
    assert cli.main([str(prefs), "--lang", "en"]) == 2
    assert "not one run" in capsys.readouterr().err
    with pytest.raises(SystemExit) as missing_arg:
        cli.main(["--lang", "en"])
    assert missing_arg.value.code == 2

    gz = scratch / "h.run"
    gz.write_bytes(gzip.compress(open(HIST, "rb").read()))
    assert cli.main([str(gz), "--lang", "en"]) == 0
    gz_out = capsys.readouterr().out
    assert "SAMPLESEED01" in gz_out and "gzip-compressed" in gz_out and "Lost" in gz_out
    assert "no map column" in gz_out and "in-progress save" not in gz_out
    u16 = scratch / "current_run.save"
    u16.write_bytes(open(LIVE, "rb").read().decode("utf-8").encode("utf-16"))
    assert cli.main([str(u16), "--lang", "en"]) == 0
    live_out = capsys.readouterr().out
    assert "LIVESEED0001" in live_out and "In progress" in live_out and "Schema 16" in live_out
    assert "UTF-16" in live_out and "No top-level seed" in live_out
    assert "in-progress save" in live_out and "no map column" not in live_out

    saves = tmp_path / "saves"
    (saves / "history").mkdir(parents=True)
    (saves / "history" / "1.run").write_bytes(open(HIST, "rb").read())
    assert cli.main([str(saves), "--lang", "en"]) == 0
    assert "picked " in capsys.readouterr().out
    assert cli.main([str(saves), "--list", "--lang", "en"]) == 0
    listed = capsys.readouterr().out
    assert "SAMPLESEED01" in listed and "picked " not in listed

    root = tmp_path / "library"
    found = root / "profile1" / "saves"
    (found / "history").mkdir(parents=True)
    (found / "history" / "1.run").write_text("{}", encoding="utf-8")
    (found / "history" / "2.run").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sts2sim.saveimport.candidate_roots", lambda: [str(root)])
    assert cli.main(["--discover", "--lang", "en"]) == 0
    discovered = capsys.readouterr().out
    assert "2 finished runs" in discovered and os.path.abspath(str(found)) in discovered
    dest = tmp_path / "roots.json"
    assert cli.main(["--discover", "--json", str(dest), "--lang", "en"]) == 0
    rows = json.loads(dest.read_text(encoding="utf-8"))
    assert rows[0]["history"] == 2 and rows[0]["has_current"] is False
    monkeypatch.setattr("sts2sim.saveimport.candidate_roots", lambda: [])
    assert cli.main(["--discover", "--lang", "en"]) == 0
    assert "No save folder" in capsys.readouterr().out


def test_import_api_encodings_discover_and_errors(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("python_multipart")
    from fastapi.testclient import TestClient
    from gui.server import app
    client = TestClient(app)
    headers = {"x-lang": "en"}
    raw = open(HIST, "rb").read()
    live = open(LIVE, "rb").read()
    up = client.post("/api/import/upload", headers=headers, files={
        "file": ("sample.run", gzip.compress(raw), "application/octet-stream")})
    assert up.status_code == 200, up.text
    body = up.json()["run"]
    assert body["kind"] == "run_history" and body["seed"] == "SAMPLESEED01"
    assert "gzip" in _codes(body)
    up16 = client.post("/api/import/upload", headers=headers, files={
        "file": ("current_run.save", live.decode("utf-8").encode("utf-16"), "application/octet-stream")})
    assert up16.status_code == 200, up16.text
    live_body = up16.json()["run"]
    assert live_body["kind"] == "live_save" and live_body["seed_source"] == "rng.seed"
    assert "utf16" in _codes(live_body) and "noRouteColumn" not in _codes(live_body)
    bad = client.post("/api/import/upload", headers=headers, files={"file": ("x.run", b"\x00nope", "application/octet-stream")})
    assert bad.status_code == 400 and "not a text JSON" in bad.json()["detail"]
    prefs = client.post("/api/import/upload", headers=headers, files={"file": ("prefs.save", b"{}", "application/octet-stream")})
    assert prefs.status_code == 400 and "not one run" in prefs.json()["detail"]
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 8)
    huge = client.post("/api/import/upload", headers=headers, files={
        "file": ("big.run", b'{"seed":"TOO-BIG"}', "application/octet-stream")})
    assert huge.status_code == 400 and "too large" in huge.json()["detail"].lower()
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32 * 1024 * 1024)
    opened = client.post("/api/import", headers=headers, json={"path": LIVE})
    assert opened.status_code == 200
    assert opened.json()["kind"] == "run" and opened.json()["run"]["kind"] == "live_save"
    assert opened.json()["run"]["result"] == "in_progress"
    hist = client.post("/api/import", headers=headers, json={"path": HIST})
    assert hist.json()["run"]["kind"] == "run_history" and hist.json()["run"]["result"] == "lost"
    empty = tmp_path / "empty"
    empty.mkdir()
    dire = client.post("/api/import", headers=headers, json={"path": str(empty)})
    assert dire.status_code == 400 and "No .run" in dire.json()["detail"]
    root = tmp_path / "library"
    found = root / "profile1" / "saves"
    (found / "history").mkdir(parents=True)
    (found / "history" / "1.run").write_text("{}", encoding="utf-8")
    (found / "current_run.save").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sts2sim.saveimport.candidate_roots", lambda: [str(root)])
    disc = client.get("/api/saves/discover", headers=headers)
    assert disc.status_code == 200
    hit = next(h for h in disc.json()["roots"] if h["path"] == os.path.abspath(str(found)))
    assert hit["history"] == 1 and hit["has_current"] is True
