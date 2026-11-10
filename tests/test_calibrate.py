"""真对局和模拟掉血的校准。夹具 ID 是虚构的，不启动游戏，不写结果。"""
import importlib.util
import json
import os
import sys

import pytest

from sts2sim.calibrate import CalibrateError, calibrate_json, calibrate_paths, report
from sts2sim.saveimport import load_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "calibrate", "real.run")
SIMS = os.path.join(ROOT, "tests", "fixtures", "calibrate", "sims.jsonl")


def _cli():
    name = "deckbench_calibrate_cli_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "calibrate.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(route, **over):
    run = {
        "seed": "SEED01",
        "ascension": 0,
        "sim_character": "Ironclad",
        "players": [{"id": 1, "sim_character": "Ironclad", "character": "CHARACTER.IRONCLAD"}],
        "route": route,
    }
    run.update(over)
    return run


def _floor(floor, room, encounter, hp, picks=None, act=0):
    rooms = [{"room_type": room}]
    if encounter:
        rooms = [{"model_id": "ENCOUNTER." + encounter, "room_type": room}]
    item = {
        "floor": floor,
        "act_index": act,
        "type": room,
        "rooms": rooms,
        "stats": [{"player_id": 1, "damage_taken": hp}] if hp is not None else [{"player_id": 1, "current_hp": 40}],
        "picks": [],
    }
    if picks:
        item["picks"] = [{
            "player_id": 1,
            "cards": [{"id": "CARD." + card, "was_picked": True} for card in picks],
        }]
    return item


def _sim(hp, floor=2, encounter="FIGHT", room="Monster", picked=None, act=0, **over):
    row = {
        "seed": "SEED01",
        "char": "Ironclad",
        "asc": 0,
        "picked": list(picked or []),
        "combats": [[floor, room, encounter, 1, hp, True, act]],
    }
    row.update(over)
    return row


def _by_floor(body):
    return {item["floor"]: item for item in body["fights"]}


def test_fixture_distribution_gap_and_unmatched_floors():
    run = load_path(REAL)["run"]
    rows = [json.loads(line) for line in open(SIMS, encoding="utf-8") if line.strip()]
    before = open(REAL, "rb").read()
    body = report(run, rows)
    assert open(REAL, "rb").read() == before
    assert body["ok"] is True and body["read_only"] is True and body["v"] == 1
    assert body["seed"] == "SAMPLESEED01" and body["character"] == "Ironclad" and body["ascension"] == 0
    assert body["deck_path"] == ["SAMPLE_PICK"]
    assert body["deck_path_rule"] == "exact_picked_cards"
    assert body["alignment"] == "floor_room_encounter"
    assert body["percentile_method"] == "midrank" and body["sim_percentile_method"] == "linear"
    assert body["gap_band"] == [5, 95]
    assert body["sim_rows"] == 10 and body["sim_matched"] == 6
    assert body["excluded"] == {"seed": 1, "character": 1, "ascension": 1, "deck_path": 1}
    fights = _by_floor(body)
    assert fights[1]["status"] == "not_a_fight" and fights[1]["room"] == "Ancient"
    assert fights[3]["status"] == "not_a_fight" and fights[3]["room"] == "Shop"
    monster = fights[2]
    assert monster["status"] == "compared" and monster["reason"] is None
    assert monster["encounter"] == "SAMPLE_FIGHT" and monster["real_hp_lost"] == 10
    assert monster["sim_n"] == 5 and monster["mean"] == 20
    assert monster["p10"] == 4 and monster["p90"] == 36
    assert monster["p5"] == 2 and monster["p95"] == 38
    assert monster["percentile"] == 30
    assert monster["outside_p5_p95"] is False and monster["likely_sim_gap"] is False
    elite = fights[4]
    assert elite["real_hp_lost"] == 50 and elite["sim_n"] == 5 and elite["mean"] == 20
    assert elite["percentile"] == 100
    assert elite["outside_p5_p95"] is True and elite["likely_sim_gap"] is True
    boss = fights[5]
    assert boss["status"] == "unmatched" and boss["reason"] == "missing_hp"
    assert boss["real_hp_lost"] is None and boss["sim_n"] is None and boss["likely_sim_gap"] is False
    bare = fights[6]
    assert bare["status"] == "unmatched" and bare["reason"] == "missing_encounter"
    assert bare["real_hp_lost"] == 4 and bare["mean"] is None
    assert body["gaps"] == [4] and body["unmatched"] == [5, 6]
    assert "999" not in json.dumps(body)


def test_different_floor_is_not_used_in_place_of_the_real_one():
    run = _run([_floor(2, "Monster", "FIGHT", 10)])
    body = report(run, [_sim(99, floor=1, encounter="FIGHT")])
    fight = body["fights"][0]
    assert fight["status"] == "unmatched" and fight["reason"] == "no_sim_fight"
    assert fight["real_hp_lost"] == 10 and fight["sim_n"] is None and fight["percentile"] is None
    assert body["sim_matched"] == 1


def test_encounter_room_and_act_mismatches_stay_unmatched():
    run = _run([_floor(2, "Monster", "FIGHT", 8)])
    wrong_enc = report(run, [_sim(1, encounter="OTHER")])
    assert wrong_enc["fights"][0]["reason"] == "encounter_mismatch"
    assert wrong_enc["fights"][0]["mean"] is None
    wrong_room = report(run, [_sim(1, room="Elite", encounter="FIGHT")])
    assert wrong_room["fights"][0]["reason"] == "room_mismatch"
    wrong_act = report(run, [_sim(1, act=1)])
    assert wrong_act["fights"][0]["reason"] == "act_mismatch"


def test_missing_encounter_is_not_filled_from_the_room_type():
    run = _run([_floor(2, "Monster", None, 3)])
    body = report(run, [_sim(3, encounter="FIGHT")])
    fight = body["fights"][0]
    assert fight["status"] == "unmatched" and fight["reason"] == "missing_encounter"
    assert fight["real_hp_lost"] == 3 and fight["sim_n"] is None


def test_deck_path_must_match_exactly_and_seed_is_canonical():
    run = _run([_floor(2, "Monster", "FIGHT", 4, picks=["TAKE"])], seed="sampleoseed")
    longer = _sim(100, encounter="FIGHT", picked=["TAKE", "EXTRA"], seed="SAMPLE0SEED")
    same = _sim(4, encounter="FIGHT", picked=["CARD.TAKE"], seed="SAMPLE0SEED")
    other = _sim(100, encounter="FIGHT", picked=["TAKE"], seed="NOPE")
    body = report(run, [longer, same, other])
    assert body["seed"] == "SAMPLE0SEED" and body["deck_path"] == ["TAKE"]
    assert body["sim_matched"] == 1 and body["excluded"] == {"deck_path": 1, "seed": 1}
    fight = body["fights"][0]
    assert fight["status"] == "compared" and fight["sim_n"] == 1 and fight["mean"] == 4
    assert fight["percentile"] == 50 and fight["likely_sim_gap"] is False
    assert fight["p5"] == 4 and fight["p95"] == 4


def test_single_sample_outside_the_point_band_is_a_gap():
    run = _run([_floor(2, "Monster", "FIGHT", 8)])
    body = report(run, [_sim(7)])
    fight = body["fights"][0]
    assert fight["sim_n"] == 1 and fight["mean"] == 7 and fight["p5"] == 7 and fight["p95"] == 7
    assert fight["percentile"] == 100 and fight["likely_sim_gap"] is True
    assert body["gaps"] == [2]


def test_real_zero_can_fall_outside_p5_and_a_boundary_value_stays_inside():
    wide = [0, 10, 20, 30, 40]
    run = _run([_floor(2, "Monster", "FIGHT", 0)])
    body = report(run, [_sim(hp) for hp in wide])
    fight = body["fights"][0]
    assert fight["p5"] == 2 and fight["real_hp_lost"] == 0
    assert fight["percentile"] == 10 and fight["likely_sim_gap"] is True
    edge = _run([_floor(2, "Monster", "FIGHT", 5)])
    inside = report(edge, [_sim(0), _sim(100)])
    hit = inside["fights"][0]
    assert hit["p5"] == 5 and hit["p95"] == 95
    assert hit["outside_p5_p95"] is False and hit["percentile"] == 50 and hit["mean"] == 50


def test_ambiguous_real_floor_and_ambiguous_sim_fight_are_not_guessed():
    floor = _floor(2, "Monster", "ONE", 6)
    floor["rooms"].append({"model_id": "ENCOUNTER.TWO", "room_type": "Monster"})
    body = report(_run([floor]), [_sim(6, encounter="ONE")])
    assert body["fights"][0]["reason"] == "ambiguous_encounter"
    assert body["fights"][0]["sim_n"] is None
    doubled = _sim(1)
    doubled["combats"] = [doubled["combats"][0], [2, "Monster", "FIGHT", 1, 9, True, 0]]
    ambiguous = report(_run([_floor(2, "Monster", "FIGHT", 1)]), [doubled])
    assert ambiguous["fights"][0]["reason"] == "ambiguous_sim"
    assert ambiguous["sim_matched"] == 1 and ambiguous["fights"][0]["mean"] is None


def test_missing_pick_list_bad_combat_and_empty_file_are_named():
    run = _run([_floor(2, "Monster", "FIGHT", 1, picks=["TAKE"])])
    missing = dict(_sim(1, picked=["TAKE"]))
    del missing["picked"]
    bad = _sim(1, picked=["TAKE"])
    bad["combats"] = [[2, "Monster"]]
    body = report(run, [missing, bad, {"seed": "SEED01", "error": "timeout", "combats": []}])
    assert body["sim_matched"] == 0
    assert body["excluded"] == {"deck_path": 1, "bad_combat": 1, "sim_error": 1}
    assert body["fights"][0]["reason"] == "bad_combat"
    empty = report(run, [])
    assert empty["fights"][0]["reason"] == "no_sim_rows" and empty["unmatched"] == [2]


def test_multiplayer_missing_seed_and_ambiguous_hp_are_not_assigned():
    with pytest.raises(CalibrateError) as multi:
        report(_run([], players=[
            {"id": 1, "sim_character": "Ironclad"},
            {"id": 2, "sim_character": "Silent"},
        ]), [])
    assert multi.value.code == "multiplayer"
    with pytest.raises(CalibrateError) as seed:
        report(_run([], seed=None), [])
    assert seed.value.code == "no_seed"
    floor = _floor(2, "Monster", "FIGHT", 1)
    floor["stats"] = [
        {"player_id": 1, "damage_taken": 1},
        {"player_id": 1, "damage_taken": 9},
    ]
    body = report(_run([floor]), [_sim(4)])
    assert body["fights"][0]["reason"] == "ambiguous_hp"
    assert body["fights"][0]["real_hp_lost"] is None and body["fights"][0]["mean"] is None


def test_cli_text_json_directory_and_refusals(tmp_path, capsys):
    cli = _cli()
    real_before = open(REAL, "rb").read()
    assert cli.main([REAL, SIMS]) == 0
    text = capsys.readouterr().out
    assert "likely sim gap" in text and "missing_hp" in text and "missing_encounter" in text
    assert "999" not in text and "SAMPLE_PICK" in text
    assert open(REAL, "rb").read() == real_before

    assert cli.main([REAL, SIMS, "--json", "-"]) == 0
    raw = capsys.readouterr().out
    assert raw.startswith("{")
    doc = json.loads(raw)
    assert doc["gaps"] == [4] and doc["fights"][1]["percentile"] == 30
    assert doc["real_path"] == os.path.realpath(REAL)
    assert doc["sim_path"] == os.path.realpath(SIMS)

    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "runs.jsonl").write_text(open(SIMS, encoding="utf-8").read(), encoding="utf-8")
    dest = tmp_path / "out" / "calibration.json"
    assert cli.main([REAL, str(folder), "--json", str(dest)]) == 0
    saved = json.loads(dest.read_text(encoding="utf-8"))
    assert saved["sim_path"] == os.path.realpath(str(folder / "runs.jsonl"))
    assert "inside p5–p95" in capsys.readouterr().out

    history = tmp_path / "history"
    history.mkdir()
    assert cli.main([REAL, SIMS, "--json", str(history / "out.json"), "--lang", "en"]) == 2
    err = capsys.readouterr()
    assert not (history / "out.json").exists()
    assert "Refusing to write" in err.err

    missing = tmp_path / "no-such.jsonl"
    assert cli.main([REAL, str(missing), "--lang", "en"]) == 2
    assert "not found" in capsys.readouterr().err.lower()


def test_cli_rejects_a_multiplayer_run(tmp_path, capsys):
    path = tmp_path / "two.run"
    path.write_text(json.dumps({
        "seed": "SEED01",
        "ascension": 0,
        "players": [
            {"id": 1, "character": "CHARACTER.IRONCLAD"},
            {"id": 2, "character": "CHARACTER.SILENT"},
        ],
        "map_point_history": [],
    }), encoding="utf-8")
    sim = tmp_path / "runs.jsonl"
    sim.write_text('{"seed":"SEED01","char":"Ironclad","asc":0,"picked":[],"combats":[]}\n', encoding="utf-8")
    assert _cli().main([str(path), str(sim), "--lang", "en", "--json", "-"]) == 2
    out = capsys.readouterr()
    assert json.loads(out.out)["error"] == "multiplayer"
    assert "multiplayer" in out.err.lower()


def test_restricted_sim_path_and_http_and_mcp(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    sim = allowed / "runs.jsonl"
    sim.write_text(open(SIMS, encoding="utf-8").read(), encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(allowed))
    before = sim.read_bytes()
    body = calibrate_paths(REAL, str(allowed))
    assert body["sim_matched"] == 6 and body["gaps"] == [4]
    assert sim.read_bytes() == before
    text = calibrate_json(REAL, str(sim))
    assert json.loads(text)["fights"][3]["likely_sim_gap"] is True

    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(tmp_path / "elsewhere"))
    (tmp_path / "elsewhere").mkdir()
    refused = json.loads(calibrate_json(REAL, str(sim)))
    assert refused["ok"] is False and refused["read_only"] is True
    assert refused["error"] == "path_not_allowed"
    save_sim = allowed / "notes.run"
    save_sim.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(allowed))
    blocked = json.loads(calibrate_json(REAL, str(save_sim)))
    assert blocked["error"] == "refuse_write"

    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from gui.server import app

    with TestClient(app) as client:
        ok = client.post("/api/calibrate", headers={"x-lang": "en"}, json={"real": REAL, "sim": str(allowed)})
        assert ok.status_code == 200, ok.text
        assert ok.json()["unmatched"] == [5, 6]
        assert ok.json()["fights"][1]["p90"] == 36
        missing = client.post("/api/calibrate", headers={"x-lang": "en"}, json={"real": "", "sim": str(sim)})
        assert missing.status_code == 400 and "real run" in missing.text.lower()
        folder = client.post(
            "/api/calibrate",
            headers={"x-lang": "en"},
            json={"real": os.path.join(ROOT, "tests", "fixtures", "saves"), "sim": str(sim)},
        )
        assert folder.status_code == 400 and "one run file" in folder.text.lower()

    name = "deckbench_mcp_calibrate_under_test"
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(allowed))
    same = mod.calibrate(REAL, str(sim))
    assert same == calibrate_json(REAL, str(sim))
    assert json.loads(same)["read_only"] is True
    assert sim.read_bytes() == before
