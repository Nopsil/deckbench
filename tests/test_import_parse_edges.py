"""存档解析里还没走到的形状：数字 ID、分类+条目、升级层数写成字符串、
非有限大数不会把整份记录打崩、摘要在路线没有生命时退回玩家身上的数。
"""
import json
import os

import pytest

from sts2sim.saveimport import (
    SaveImportError,
    batch_summary,
    load_path,
    parse_bytes,
    summarize,
)


def _history(**over):
    raw = {
        "seed": "EDGESEED01",
        "ascension": "3",
        "win": False,
        "players": [
            "skip-me",
            {
                "character": {"category": "CHARACTER", "entry": "SILENT"},
                "deck": [
                    {"id": 12},
                    {"id": 1.5},
                    {
                        "id": {"category": "CARD", "entry": "STRIKE"},
                        "current_upgrade": "2",
                        "enchantment": {"id": "ENCHANT.PLUS", "amount": "nope"},
                        "floor_added_to_deck": True,
                        "floor": "4",
                    },
                    {"id": {"category": "OTHER", "entry": "CARD.DOTTED"}},
                    {"id": "NONE.NONE"},
                    None,
                ],
                "relics": ["RELIC.RING", {"id": 7, "floor": "2"}],
                "potions": ["POTION.FIRE", {"potion": "POTION.BLOCK", "slot": "1"}],
                "current_hp": "40",
                "max_hp": 50,
                "gold": "-3",
            },
        ],
        "acts": "ACT.ONE",
        "visited_map_coords": [
            {"coord": {"col": "1", "row": 2}},
            "nope",
            {"col": 3},
        ],
        "map_point_history": [[{
            "map_point_type": "Monster",
            "player_stats": [{
                "player_id": "1",
                "damage_taken": "5",
                "card_choices": [
                    "CARD.A",
                    3,
                    {"card": {"id": "CARD.B"}, "was_picked": "yes"},
                ],
            }],
        }]],
    }
    raw.update(over)
    return raw


def test_ids_upgrades_choices_and_string_numbers():
    run = parse_bytes(json.dumps(_history()).encode("utf-8"), filename="edge.run")
    player = run["players"][0]
    assert player["id"] == 2
    assert player["character"] == "CHARACTER.SILENT"
    assert player["sim_character"] == "Silent"
    assert player["current_hp"] == 40 and player["gold"] == -3
    assert [c["id"] for c in player["deck"]] == ["12", "1.5", "CARD.STRIKE", "CARD.DOTTED"]
    strike = player["deck"][2]
    assert strike["upgraded"] is True
    assert strike["floor"] == 4
    assert strike["enchantment"] == {"id": "ENCHANT.PLUS", "amount": None}
    assert player["relics"] == [
        {"id": "RELIC.RING", "floor": None},
        {"id": "7", "floor": 2},
    ]
    assert player["potions"] == [
        {"id": "POTION.FIRE", "slot": None},
        {"id": "POTION.BLOCK", "slot": 1},
    ]
    assert run["acts"] == [{"index": 0, "id": "ACT.ONE", "map": None}]
    assert run["visited_map_coords"] == [{"col": 1, "row": 2}]
    picks = run["route"][0]["picks"][0]["cards"]
    assert [(c["id"], c["was_picked"]) for c in picks] == [("CARD.A", False), ("CARD.B", True)]
    assert run["route"][0]["stats"][0]["damage_taken"] == 5
    assert run["ascension"] == 3


def test_huge_finite_float_and_bad_payloads_do_not_crash():
    raw = _history()
    raw["players"][1]["max_hp"] = 1e308
    run = parse_bytes(json.dumps(raw).encode("utf-8"), filename="big.run")
    assert isinstance(run["players"][0]["max_hp"], int)
    assert run["players"][0]["max_hp"] > 10 ** 300

    with pytest.raises(SaveImportError) as odd:
        parse_bytes(b"\xff\xfe\x41", filename="odd.run")
    assert odd.value.code == "decode"
    with pytest.raises(SaveImportError) as nul:
        parse_bytes(b"\x00\x00not-a-save", filename="bin.run")
    assert nul.value.code == "not_json"
    with pytest.raises(SaveImportError) as blank:
        parse_bytes(b"   \n", filename="blank.run")
    assert blank.value.code == "not_json"


def test_boss_only_map_parses_and_a_point_without_coords_is_skipped():
    raw = _history()
    raw["acts"] = [{"id": "ACT.ONE", "saved_map": {"points": [
        {"coord": {"col": 1, "row": 2}, "point_type": "Boss"},
        {"row": 0},
    ]}}]
    run = parse_bytes(json.dumps(raw).encode("utf-8"), filename="map.run")
    mp = run["acts"][0]["map"]
    assert mp["boss"] == {"col": 1, "row": 2}
    assert mp["rows"] == []
    assert mp["cols"] == 2
    assert not any(w["code"] == "mapUnparsed" for w in run["warnings"])


def test_profile_and_loose_folder_only_keep_run_files(tmp_path):
    body = json.dumps(_history())
    profile = tmp_path / "profile"
    hist = profile / "saves" / "history"
    hist.mkdir(parents=True)
    (hist / "a.run").write_text(body, encoding="utf-8")
    (profile / "notes.json").write_text("{}", encoding="utf-8")
    loaded = load_path(str(profile))
    assert [e["file"] for e in loaded["entries"]] == ["a.run"]

    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "notes.json").write_text("{}", encoding="utf-8")
    (loose / "nested").mkdir()
    (loose / "b.run").write_text(body, encoding="utf-8")
    loose_doc = load_path(str(loose))
    assert [e["file"] for e in loose_doc["entries"]] == ["b.run"]
    assert os.path.isdir(loose / "nested")


def test_summary_falls_back_to_the_player_and_keeps_enchantments():
    run = {
        "kind": "run_history",
        "filename": "a.run",
        "seed": "S",
        "ascension": 0,
        "result": "won",
        "players": [
            {
                "id": 1,
                "sim_character": "Silent",
                "character": "CHARACTER.SILENT",
                "current_hp": 11,
                "max_hp": 70,
                "gold": 4,
                "deck": [
                    {"id": "CARD.A", "upgraded": False, "floor": 0,
                     "enchantment": {"id": "ENCHANT.V", "amount": 2}},
                    {"id": "CARD.B", "upgraded": False, "floor": None, "enchantment": None},
                ],
                "relics": [
                    {"id": "RELIC.R", "floor": 3},
                    {"id": "RELIC.S", "floor": None},
                ],
            },
            {
                "id": 2,
                "sim_character": "Ironclad",
                "character": "CHARACTER.IRONCLAD",
                "deck": [],
                "relics": [{"id": "RELIC.T", "floor": 1}],
            },
        ],
        "route": [
            "nope",
            {
                "floor": 1,
                "type": "Monster",
                "stats": [{"damage_taken": 3}],
                "picks": [
                    "nope",
                    {"player_id": 1, "cards": [
                        {"id": "CARD.A", "was_picked": True},
                        {"id": ""},
                        "x",
                    ]},
                ],
            },
        ],
        "visited_map_coords": [],
        "acts": [{"id": "ACT.ONE"}, {"id": ""}, "nope"],
        "warnings": [{"code": "seedMissing"}, {"nope": 1}, "x"],
    }
    summary = summarize(run)
    assert summary["hp"] == 11 and summary["max_hp"] == 70 and summary["gold"] == 4
    assert summary["characters"] == ["Silent", "Ironclad"]
    assert summary["acts"] == ["ACT.ONE"]
    cards = summary["highlights"]["cards"]
    assert cards[0]["id"] == "CARD.A"
    assert cards[0]["enchantment"] == "ENCHANT.V" and cards[0]["enchantment_amount"] == 2
    assert all(c["id"] != "CARD.B" for c in cards)
    relics = summary["highlights"]["relics"]
    assert relics[0] == {"id": "RELIC.R", "floor": 3, "player": 1}
    assert {"id": "RELIC.T", "floor": 1, "player": 2} in relics
    pick = summary["highlights"]["picks"][0]
    assert pick["picked"] == ["CARD.A"] and pick["offered"] == ["CARD.A"] and pick["player"] == 1
    assert summary["warnings"] == ["seedMissing"]
    assert summary["floor_reached"] == 1

    rows = batch_summary(run)
    assert rows[0]["result"] == "won" and rows[0]["character"] == "Silent"
    folder = summarize({
        "kind": "folder",
        "path": "/tmp/saves",
        "entries": [
            "nope",
            {"file": "a.run", "role": "history", "run": run},
            {"file": "bad.run", "role": "history", "error": {"code": "not_json"}},
        ],
        "warnings": [{"code": "truncated"}, "x"],
    })
    assert folder["count"] == 1 and folder["failures"][0]["error"] == "not_json"
    assert folder["warnings"] == ["truncated"]
    with pytest.raises(SaveImportError) as not_obj:
        summarize([])
    assert not_obj.value.code == "not_object"
    with pytest.raises(SaveImportError) as shape:
        summarize({"kind": "nope"})
    assert shape.value.code == "unknown_shape"
