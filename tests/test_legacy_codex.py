"""旧版战斗目录：合成夹具，不读游戏安装。"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import parse_encounters
import parse_monster_ai

from sts2sim import catalog, enemies
from sts2sim import gamedata as gd
from sts2sim.legacycodex import export_tree, fight_character, load_loc_pair, normal_int

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "legacy_min")
SHA = "ab" * 32


def _tables(lang):
    folder = os.path.join(FIXTURE, "loc", lang)
    out = {}
    for name in os.listdir(folder):
        if name.endswith(".json"):
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                out[name[:-5]] = json.load(handle)
    return out


@pytest.fixture
def exported(tmp_path, monkeypatch):
    monkeypatch.delenv("DECKBENCH_CODEX_DIR", raising=False)
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "empty-cache"))
    monkeypatch.setenv("DECKBENCH_GAME_DIR", str(tmp_path / "no-game"))
    out = tmp_path / "codex"
    stamp = export_tree(FIXTURE, _tables("eng"), _tables("zhs"), str(out), SHA,
                        {"version": "v9", "branch": "fixture", "commit": "abc"})
    enemies._DB.clear()
    catalog._IDX.clear()
    monkeypatch.setenv("DECKBENCH_CODEX_DIR", str(out))
    yield out, stamp
    enemies._DB.clear()
    catalog._IDX.clear()


def test_dread_suffix_keeps_the_non_ascension_number():
    expr = "AscensionHelper.GetValueIfAscension(AscensionLevel.ToughEnemies, 20, 12) + (AscensionHelper.IsDread() ? 4 : 0)"
    assert normal_int(expr) == 12
    with open(os.path.join(FIXTURE, "Models", "Monsters", "Knight.cs"), encoding="utf-8") as handle:
        src = handle.read()
    assert parse_monster_ai.consts_of(src)["Slam"] == 5
    parsed = parse_monster_ai.parse_file(os.path.join(FIXTURE, "Models", "Monsters", "Knight.cs"))
    assert parsed["states"]["SLAM_MOVE"]["code_move"]["damage"] == 5


def test_subclass_without_a_machine_inherits_the_parent():
    ai = parse_monster_ai.parse_dir(os.path.join(FIXTURE, "Models", "Monsters"))
    assert ai["SQUIRE"]["inherited_from"] == "KNIGHT"
    assert "SLAM_MOVE" in ai["SQUIRE"]["states"]


def test_new_encounter_shapes():
    parsed = parse_encounters.parse_dir(os.path.join(FIXTURE, "Models", "Encounters"))
    assert parsed["NIB_WEAK"]["slots"] == [["NIB"]]
    assert parsed["NIB_WEAK"]["source"] == "代码"
    assert parsed["NEST_EVENT"]["slots"] == [["NIB"], ["NIB"], ["NIB"]]
    assert parsed["PAIR_NORMAL"]["source"] == "代码"
    assert parsed["PAIR_NORMAL"]["slots"] == [["NIB"]]
    weights = parsed["SIDES_NORMAL"]["alternatives"]
    assert weights[0] == [1.0, ["NIB", "KNIGHT"]]
    assert abs(sum(row[0] for row in weights) - 2) < 1e-9
    assert ["SQUIRE", "SQUIRE", "KNIGHT"] in [row[1] for row in weights]


def test_export_stamp_names_and_straight_line_cards(exported):
    folder, stamp = exported
    assert stamp["format"] == 1
    assert stamp["dll_sha256"] == SHA
    assert stamp["playable_characters"] == ["MIME"]
    assert stamp["straight_line_cards"] == 3
    with open(folder / "eng_monsters.json", encoding="utf-8") as handle:
        monsters = {row["id"]: row for row in json.load(handle)}
    nib = monsters["NIB"]
    assert nib["min_hp"] == 12 and nib["max_hp"] == 14
    assert nib["moves"][0]["damage"]["normal"] == 4
    assert nib["moves"][0]["name"] == "Poke"
    assert "dread" not in json.dumps(nib)
    assert monsters["SQUIRE"]["name"] == "Knight"
    assert monsters["SQUIRE"]["min_hp"] == 30
    assert monsters["SQUIRE"]["moves"][0]["damage"]["normal"] == 5
    with open(folder / "zhs_monsters.json", encoding="utf-8") as handle:
        zh = {row["id"]: row for row in json.load(handle)}
    assert zh["NIB"]["name"] == "小戳"
    assert zh["SQUIRE"]["name"] == "骑士"
    assert zh["NIB"]["min_hp"] == 12
    with open(folder / "eng_cards.json", encoding="utf-8") as handle:
        cards = {row["id"]: row for row in json.load(handle)}
    assert cards["JAB"]["effects_status"] == "straight_line"
    assert cards["JAB"]["vars"]["dmg"] == 6
    assert cards["JAB"]["upgrade"]["vars"]["dmg"] == 9
    assert cards["JAB"]["pool"] == "MIME"
    assert cards["SHOT"]["from_arrow"] is True
    assert cards["SHOT"]["tags"] == ["arrow"]
    assert cards["SHOT"]["vars"]["dmg"] == 9
    assert cards["HEX"]["effects_status"] == "index_only"
    assert "effects" not in cards["HEX"]
    with open(folder / "zhs_characters.json", encoding="utf-8") as handle:
        mime = json.load(handle)[0]
    assert mime["name"] == "哑剧"
    assert mime["hp"] == 40
    assert mime["energy_source"] == "default"
    assert mime["starting_deck"] == ["JAB", "WARD", "SHOT"]
    assert mime["starting_relics"] == ["RIBBON"]
    with open(folder / "eng_relics.json", encoding="utf-8") as handle:
        ribbon = json.load(handle)[0]
    assert ribbon["rarity_key"] == "Starter"
    assert ribbon["combat_start"] == [{"power_id": "AIM", "amount": 2}]
    with open(folder / "eng_encounters.json", encoding="utf-8") as handle:
        encounters = {row["id"]: row for row in json.load(handle)}
    assert encounters["NIB_WEAK"]["act"] == "Act 1 Meadow"
    assert encounters["NIB_WEAK"]["is_weak"] is True
    assert encounters["NIB_WEAK"]["room_type"] == "Monster"
    assert encounters["NEST_EVENT"]["act"] is None
    assert catalog.codex_index("relics")["RIBBON"]["name"] == "丝带"
    assert catalog.codex_index("powers")["AIM"]["name"] == "瞄准"


def test_unknown_monster_field_still_loads(exported):
    folder, _stamp = exported
    path = folder / "eng_monsters.json"
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    rows[0]["dread_bonus"] = 4
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle)
    enemies._DB.clear()
    db = enemies.load_db()
    assert "NIB" in db["monsters"]
    weak = [row["id"] for row in enemies.encounter_pool(1, "弱怪")]
    normal = {row["id"] for row in enemies.encounter_pool(1, "普通")}
    assert weak == ["NIB_WEAK"]
    assert normal == {"PAIR_NORMAL", "SIDES_NORMAL"}
    assert "NEST_EVENT" not in normal


def test_mime_deck_fights_the_weak_encounter_twice(exported):
    folder, _stamp = exported
    first = fight_character(str(folder), "MIME", "NIB_WEAK", seed=3, max_turns=8)
    second = fight_character(str(folder), "MIME", "NIB_WEAK", seed=3, max_turns=8)
    assert first["result"] == "win"
    assert first == second
    assert first["skipped"] == []


def test_stamp_must_match_the_verified_dll(exported, tmp_path, monkeypatch):
    _folder, _stamp = exported
    game = tmp_path / "game"
    game.mkdir()
    dll = game / "sts2.dll"
    dll.write_bytes(b"fixture-dll")
    cache = tmp_path / "cache"
    slot = cache / "slot"
    slot.mkdir(parents=True)
    digest = gd.sha256(str(dll))
    with open(slot / "manifest.json", "w", encoding="utf-8") as handle:
        json.dump({"format": gd.FORMAT, "translator_rev": gd.TRANSLATOR_REV,
                   "dll_path": str(dll), "dll_sha256": digest}, handle)
    with open(cache / "current.json", "w", encoding="utf-8") as handle:
        json.dump({"cache_dir": str(slot)}, handle)
    monkeypatch.setenv("DECKBENCH_CACHE", str(cache))
    monkeypatch.setenv("DECKBENCH_GAME_DIR", str(game))
    with pytest.raises(gd.GameDataError, match="different sts2.dll"):
        gd.require_codex()
    monkeypatch.delenv("DECKBENCH_CODEX_DIR")
    assert gd.codex_dir() == str(slot / "legacy-codex")
    with pytest.raises(gd.GameDataError, match="not found"):
        gd.require_codex()


def test_explicit_unstamped_dir_still_loads(exported, tmp_path, monkeypatch):
    folder, _stamp = exported
    os.remove(folder / "codex_stamp.json")
    enemies._DB.clear()
    assert gd.require_codex() == str(folder)
    assert enemies.load_db()["monsters"]["NIB"].min_hp == 12


def test_outdated_stamp_is_refused(exported):
    folder, _stamp = exported
    path = folder / "codex_stamp.json"
    with open(path, encoding="utf-8") as handle:
        stamp = json.load(handle)
    stamp["format"] = 99
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(stamp, handle)
    with pytest.raises(gd.GameDataError, match="stamp"):
        gd.require_codex()


def test_load_loc_pair_reads_env_dirs(monkeypatch):
    monkeypatch.setenv("DECKBENCH_GAME_LOC_ENG", os.path.join(FIXTURE, "loc", "eng"))
    monkeypatch.setenv("DECKBENCH_GAME_LOC_ZHS", os.path.join(FIXTURE, "loc", "zhs"))
    eng, zhs = load_loc_pair()
    assert eng["cards"]["JAB.title"] == "Jab"
    assert zhs["characters"]["MIME.title"] == "哑剧"
