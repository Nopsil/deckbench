"""校准匹配的边界：对不上就不拿别的层或别的遭遇来凑，坏数字不当成掉血。"""
import json
import math
import os

import pytest

from sts2sim.calibrate import CalibrateError, calibrate_paths, render_text, report


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


def _floor(floor, room, encounter, hp, picks=None, act=0, player_id=1):
    rooms = [{"room_type": room}]
    if encounter:
        rooms = [{"model_id": "ENCOUNTER." + encounter, "room_type": room}]
    item = {
        "floor": floor,
        "act_index": act,
        "type": room,
        "rooms": rooms,
        "stats": [{"player_id": player_id, "damage_taken": hp}] if hp is not None else [],
        "picks": [],
    }
    if picks:
        item["picks"] = [{
            "player_id": player_id,
            "cards": [{"id": "CARD." + card, "was_picked": True} for card in picks],
        }]
    return item


def _sim(**over):
    combat = {"floor": 2, "room": "Monster", "encounter": "FIGHT", "hp_lost": 4, "act": 0}
    for key in ("floor", "room", "encounter", "hp_lost", "act", "act_index"):
        if key in over:
            combat[key] = over.pop(key)
    row = {
        "seed": "SEED01",
        "char": "Ironclad",
        "asc": 0,
        "picked": [],
        "combats": [combat],
    }
    row.update(over)
    return row


def test_identity_rejects_disagreement_and_non_integers():
    with pytest.raises(CalibrateError) as mismatch:
        report(_run([], sim_character="Silent"), [])
    assert mismatch.value.code == "no_character"
    with pytest.raises(CalibrateError) as empty:
        report(_run([], players=[]), [])
    assert empty.value.code == "no_character"
    with pytest.raises(CalibrateError) as not_dict:
        report([], [])
    assert not_dict.value.code == "no_character"
    with pytest.raises(CalibrateError) as asc:
        report(_run([], ascension=True), [])
    assert asc.value.code == "no_ascension"
    with pytest.raises(CalibrateError) as half:
        report(_run([], ascension=2.5), [])
    assert half.value.code == "no_ascension"

    body = report(_run([_floor(2, "Monster", "FIGHT", 4)], ascension="3", seed="seedoi"), [
        _sim(ascension=3.0, asc=3, seed="SEED01", char="character.ironclad", character="Ironclad"),
    ])
    assert body["seed"] == "SEED01" and body["ascension"] == 3 and body["sim_matched"] == 1

    custom = _run([_floor(2, "Monster", "FIGHT", 1)], sim_character="MOD.CUSTOM")
    custom["players"] = [{"id": 1, "character": "MOD.CUSTOM"}]
    matched = report(custom, [_sim(char="CUSTOM", hp_lost=1)])
    assert matched["character"] == "CUSTOM" and matched["sim_matched"] == 1


def test_deck_path_ignores_other_players_and_rejects_a_broken_list():
    floor = _floor(2, "Monster", "FIGHT", 4, picks=["TAKE"])
    floor["picks"].append({
        "player_id": 2,
        "cards": [{"id": "CARD.OTHER", "was_picked": True}],
    })
    floor["picks"].append("nope")
    floor["picks"][0]["cards"].append({"id": "CARD.SKIP", "was_picked": False})
    floor["picks"][0]["cards"].append("CARD.RAW")
    body = report(_run([floor, "nope"]), [
        _sim(picked=[{"id": "CARD.TAKE"}]),
        _sim(picked=["TAKE", 1]),
        _sim(picked=[]),
    ])
    assert body["deck_path"] == ["TAKE"]
    assert body["sim_matched"] == 1
    assert body["excluded"] == {"deck_path": 2}
    assert body["fights"][-1]["floor"] is None and body["fights"][-1]["status"] == "unmatched"


def test_room_encounter_and_act_normalization():
    floor = _floor(2, "Room.Elite", "FIGHT", 6)
    body = report(_run([floor]), [_sim(room="elite", encounter="FIGHT", hp_lost=6)])
    fight = body["fights"][0]
    assert fight["status"] == "compared" and fight["room"] == "Elite" and fight["mean"] == 6

    omitted = report(_run([_floor(2, "Monster", "FIGHT", 4, act=1)]), [
        _sim(act=None, hp_lost=4),
    ])
    # 模拟没写幕时，不拿「幕对不上」把这场扔掉。写了并且不同，才是 act_mismatch。
    assert omitted["fights"][0]["status"] == "compared"
    named = report(_run([_floor(2, "Monster", "FIGHT", 4)]), [
        {"seed": "SEED01", "char": "Ironclad", "asc": 0, "picked": [], "combats": [{
            "floor": "2", "room": "Monster", "encounter": "EVENT.SHOP", "hp_lost": 4, "act": 0,
        }]},
    ])
    assert named["fights"][0]["reason"] == "missing_encounter"
    none_enc = report(_run([_floor(2, "Monster", "FIGHT", 4)]), [
        _sim(encounter="NONE", hp_lost=4),
    ])
    assert none_enc["fights"][0]["reason"] == "missing_encounter"

    quiet = _floor(3, "Event", None, None)
    unknown = {"floor": 4, "rooms": []}
    ambiguous = _floor(5, "Monster", "ONE", 1)
    ambiguous["rooms"].append({"room_type": "Elite", "model_id": "ENCOUNTER.TWO"})
    shop_fight = _floor(6, "Shop", None, 1)
    shop_fight["rooms"].append({"room_type": "Monster"})
    kinds = report(_run([quiet, unknown, ambiguous, shop_fight]), [])
    by_floor = {item["floor"]: item for item in kinds["fights"]}
    assert by_floor[3]["status"] == "not_a_fight" and by_floor[3]["room"] == "Event"
    assert by_floor[4]["reason"] == "unknown_floor"
    assert by_floor[5]["reason"] == "ambiguous_floor" and by_floor[5]["room"] is None
    assert by_floor[6]["reason"] == "ambiguous_floor" and by_floor[6]["room"] == "Monster"


def test_bad_numbers_conflicts_and_reason_ties():
    floor = _floor(2, "Monster", "FIGHT", 4)
    nan = _sim(hp_lost=float("nan"))
    boolean = _sim()
    boolean["combats"] = [{"floor": 2, "room": "Monster", "encounter": "FIGHT", "hp_lost": True, "act": 0}]
    text_hp = _sim()
    text_hp["combats"] = [{"floor": 2, "room": "Monster", "encounter": "FIGHT", "hp_lost": "4", "act": 0}]
    disagree = _sim()
    disagree["combats"] = [{"floor": 2, "room": "Monster", "encounter": "FIGHT", "hp_lost": 4,
                            "act": 0, "act_index": 1}]
    body = report(_run([floor]), [nan, boolean, text_hp, disagree, "nope", {"error": "timeout"}])
    assert body["sim_matched"] == 3
    assert body["fights"][0]["reason"] == "sim_hp_missing"
    assert body["excluded"]["bad_combat"] == 1
    assert body["excluded"]["not_a_run"] == 1
    assert body["excluded"]["sim_error"] == 1

    both_names = _sim(char="Ironclad", character="Silent")
    both_asc = _sim(asc=0, ascension=1)
    split = report(_run([floor]), [both_names, both_asc])
    assert split["sim_matched"] == 0
    assert split["excluded"] == {"character": 1, "ascension": 1}

    room = _sim(room="Elite")
    missing = _sim(floor=9)
    tied = report(_run([floor]), [room, missing])
    assert tied["fights"][0]["reason"] == "room_mismatch"

    owned = _floor(2, "Monster", "FIGHT", 4)
    owned["stats"] = [
        {"player_id": 2, "damage_taken": 9},
        {"player_id": 1, "damage_taken": 4},
    ]
    picked = report(_run([owned]), [_sim(hp_lost=4)])
    assert picked["fights"][0]["status"] == "compared" and picked["fights"][0]["real_hp_lost"] == 4
    flag = _floor(2, "Monster", "FIGHT", True)
    assert report(_run([flag]), [_sim(hp_lost=4)])["fights"][0]["reason"] == "missing_hp"


def test_float_samples_and_pool_reasons():
    floor = _floor(2, "Monster", "FIGHT", 0)
    body = report(_run([floor]), [_sim(hp_lost=0.0), _sim(hp_lost=1.0)])
    fight = body["fights"][0]
    assert fight["mean"] == 0.5 and fight["sim_n"] == 2
    assert fight["likely_sim_gap"] is True
    text = render_text(body)
    assert "0.5" in text and "FIGHT" in text

    one = report(_run([floor]), [_sim(hp_lost=4.0)])
    assert one["fights"][0]["mean"] == 4 and isinstance(one["fights"][0]["mean"], int)

    wide = report(_run([_floor(2, "Monster", "FIGHT", 10)]), [_sim(hp_lost=hp) for hp in (0, 10, 30)])
    assert wide["fights"][0]["p10"] == 2
    assert wide["fights"][0]["p90"] == 26
    assert wide["fights"][0]["percentile"] == 50

    empty_errors = report(_run([floor]), [{"error": "a"}, "nope"])
    assert empty_errors["fights"][0]["reason"] == "not_a_run"
    only_errors = report(_run([floor]), [{"error": "a"}, {"error": "b"}])
    assert only_errors["fights"][0]["reason"] == "sim_error"
    wrong_seed = report(_run([floor]), [_sim(seed="OTHER")])
    assert wrong_seed["fights"][0]["reason"] == "seed"


def test_paths_need_both_files_and_unrestricted_missing(tmp_path):
    real = tmp_path / "one.run"
    real.write_text(json.dumps({
        "seed": "SEED01",
        "ascension": 0,
        "players": [{"id": 1, "character": "CHARACTER.IRONCLAD"}],
        "map_point_history": [],
    }), encoding="utf-8")
    missing = tmp_path / "nope.jsonl"
    with pytest.raises(CalibrateError) as need_sim:
        calibrate_paths(str(real), "  ", restricted=False)
    assert need_sim.value.code == "need_sim"
    with pytest.raises(CalibrateError) as gone:
        calibrate_paths(str(real), str(missing), restricted=False)
    assert gone.value.code == "not_found"
    assert os.path.basename(gone.value.params["path"]) == "nope.jsonl"
