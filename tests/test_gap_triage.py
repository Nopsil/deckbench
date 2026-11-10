"""校准缺口分诊。夹具里的遭遇 ID 是虚构的，不启动游戏，不改模拟。"""
import importlib.util
import json
import os
import sys

from sts2sim.calibrate import calibrate_paths
from sts2sim.enemies import ENCOUNTER_SETUP, ROTATING_START
from sts2sim.gamedata import codex_dir

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "gap_triage")
REAL = os.path.join(ROOT, "tests", "fixtures", "calibrate", "real.run")
SIMS = os.path.join(ROOT, "tests", "fixtures", "calibrate", "sims.jsonl")
ONE = os.path.join(FIX, "a_one.json")
TWO = os.path.join(FIX, "b_two.json")
CATALOG = os.path.join(FIX, "catalog.json")


def _mod():
    name = "deckbench_gap_triage_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "gap_triage.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _read(path, binary=False):
    mode = "rb" if binary else "r"
    kwargs = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as fh:
        return fh.read()


def _snapshot(folder):
    out = {}
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            out[name] = _read(path, binary=True)
    return out


def _ids(rows):
    return [row["id"] for row in rows]


def _by_id(rows):
    return {row["id"]: row for row in rows}


def _section(text, title, nxt):
    return text.split(title, 1)[1].split(nxt, 1)[0]


def _fight(encounter, real, p5, p95, gap, room="Monster", floor=1, status="compared"):
    return {
        "floor": floor,
        "room": room,
        "encounter": encounter,
        "status": status,
        "real_hp_lost": real,
        "p5": p5,
        "p95": p95,
        "likely_sim_gap": gap,
    }


def _report(fights):
    return {
        "ok": True,
        "read_only": True,
        "v": 1,
        "alignment": "floor_room_encounter",
        "fights": fights,
    }


def test_fixture_ranks_optimistic_and_pessimistic_and_points_at_engine_code():
    mod = _mod()
    before = _snapshot(FIX)
    body = mod.analyze([FIX], CATALOG)
    after = _snapshot(FIX)
    assert after == before
    assert body["ok"] is True and body["read_only"] is True and body["v"] == 1
    assert body["codex"] is os.path.isfile(os.path.join(codex_dir(), "eng_monsters.json"))
    assert body["counts"] == {
        "compared": 10,
        "gaps": 7,
        "optimistic": 3,
        "pessimistic": 3,
        "unknown_direction": 1,
        "unmatched": 1,
        "not_a_fight": 1,
    }
    assert _ids(body["encounters"]["optimistic"]) == ["SAMPLE_ELITE", "SAMPLE_WIDE"]
    assert _ids(body["encounters"]["pessimistic"]) == ["SAMPLE_BARE", "SAMPLE_GLOOM", "SAMPLE_FIGHT"]
    assert "SAMPLE_EDGE" not in _ids(body["encounters"]["optimistic"])
    assert "SAMPLE_EDGE" not in _ids(body["encounters"]["pessimistic"])
    edge = _by_id(body["encounters"]["all"])["SAMPLE_EDGE"]
    assert edge["unknown_direction"] == 1 and edge["optimistic"] == 0 and edge["pessimistic"] == 0
    assert "SAMPLE_BOSS" not in _by_id(body["encounters"]["all"])
    elite = _by_id(body["encounters"]["all"])["SAMPLE_ELITE"]
    assert elite["optimistic"] == 2 and elite["compared"] == 2
    assert elite["powers"] == ["CONSTRICT", "SUCK"]
    assert elite["mechanics"] == ["summon_skipped"]
    assert elite["monsters"] == ["SAMPLE_STRANGLER"]
    wide = _by_id(body["encounters"]["all"])["SAMPLE_WIDE"]
    assert wide["rooms"] == ["Elite", "Monster"]
    assert "back_attack_always" in wide["mechanics"]
    assert _ids(body["by_power"]) == [
        "CONSTRICT",
        "SUCK",
        "summon_skipped",
        "NOT_A_REAL_POWER",
        "status_card",
        "THORNS",
        "BACK_ATTACK_LEFT",
        "back_attack_always",
    ]
    assert _ids(body["top_gaps"]) == [
        "CONSTRICT",
        "SUCK",
        "summon_skipped",
        "NOT_A_REAL_POWER",
        "status_card",
        "SAMPLE_BARE",
        "THORNS",
        "BACK_ATTACK_LEFT",
        "back_attack_always",
    ]
    powers = _by_id(body["by_power"])
    constrict = powers["CONSTRICT"]
    assert constrict["kind"] == "power" and constrict["label_zh"] == "紧缠" and constrict["label_en"] == "Constrict"
    assert constrict["lean"] == "optimistic" and constrict["optimistic"] == 2 and constrict["compared"] == 2
    assert constrict["code"][0]["file"] == "sts2sim/powers_enemy.py"
    assert constrict["code"][0]["symbol"] == "Constrict"
    source = _read(os.path.join(ROOT, "sts2sim", "powers_enemy.py")).splitlines()
    assert "class Constrict" in source[constrict["code"][0]["line"] - 1]
    suck = powers["SUCK"]
    assert suck["code"][0]["file"] == "sts2sim/powers_enemy.py" and suck["code"][0]["symbol"] == "Suck"
    missing = powers["NOT_A_REAL_POWER"]
    assert missing["unimplemented"] is True
    assert missing["code"][0]["file"] == "sts2sim/enemies.py"
    assert missing["code"][0]["symbol"] == "take_turn"
    assert "unimplemented" in missing["code"][0]["note"]
    thorns = powers["THORNS"]
    assert thorns["label_zh"] == "荆棘"
    assert thorns["lean"] == "pessimistic" and thorns["pessimistic"] == 1 and thorns["compared"] == 2
    assert [item["symbol"] for item in thorns["code"]] == ["Thorns", "mechanic_adjust"]
    assert thorns["code"][0]["file"] == "sts2sim/powers.py"
    assert thorns["code"][1]["file"] == "sts2sim/ai/base.py"
    assert "mechanic_aware" in thorns["code"][1]["note"]
    bare = _by_id(body["top_gaps"])["SAMPLE_BARE"]
    assert bare["kind"] == "encounter"
    assert [item["file"] for item in bare["code"]] == [
        "sts2sim/powers_enemy.py",
        "sts2sim/powers.py",
        "sts2sim/enemies.py",
    ]
    assert any("skip.json" in note for note in body["notes"])
    assert not any("catalog.json" in note for note in body["notes"])
    text = mod.render_markdown(body, top=10)
    assert "模拟偏乐观" in text and "too optimistic" in text
    assert "sts2sim/powers_enemy.py" in text and "mechanic_adjust" in text
    assert "SAMPLE_ELITE" in text and "2/2 (100%)" in text
    assert "1/3 (33.3%)" in text
    opt = _section(
        text,
        "## 模拟最常偏乐观的遭遇 / Encounters where the sim is most often too optimistic",
        "## 模拟最常偏悲观的遭遇",
    )
    assert "SAMPLE_ELITE" in opt and "SAMPLE_WIDE" in opt
    short = mod.render_markdown(body, top=1)
    opt_short = _section(
        short,
        "## 模拟最常偏乐观的遭遇 / Encounters where the sim is most often too optimistic",
        "## 模拟最常偏悲观的遭遇",
    )
    assert "SAMPLE_ELITE" in opt_short and "SAMPLE_WIDE" not in opt_short
    assert "还有 1 条没列出" in opt_short


def test_min_compared_drops_single_fight_encounters():
    mod = _mod()
    body = mod.analyze([ONE, TWO], CATALOG, min_compared=2)
    assert _ids(body["encounters"]["optimistic"]) == ["SAMPLE_ELITE", "SAMPLE_WIDE"]
    assert _ids(body["encounters"]["pessimistic"]) == ["SAMPLE_FIGHT"]
    assert "NOT_A_REAL_POWER" not in _ids(body["top_gaps"])
    assert "SAMPLE_BARE" not in _ids(body["top_gaps"])
    assert "CONSTRICT" in _ids(body["top_gaps"])
    assert "THORNS" in _ids(body["top_gaps"])


def test_same_file_twice_is_counted_once_and_boundaries_are_not_outside():
    mod = _mod()
    once = mod.analyze([ONE, ONE])
    assert once["counts"]["compared"] == 3
    assert once["counts"]["optimistic"] == 1
    assert once["counts"]["pessimistic"] == 1
    reports = [_report([
        _fight("SAMPLE_ON_P95", 12, 4, 12, True),
        _fight("SAMPLE_BOOL", True, 0, 1, True),
        _fight("SAMPLE_NAN", float("nan"), 0, 1, True),
        _fight("SAMPLE_BOTH", 5, 10, 1, True),
        _fight("SAMPLE_FLAGGED_UNMATCHED", 99, 0, 1, True, status="unmatched"),
        _fight("SAMPLE_INSIDE", 5, 0, 9, False),
    ])]
    body = mod.triage_reports(reports, catalog=mod.empty_catalog())
    rows = _by_id(body["encounters"]["all"])
    assert rows["SAMPLE_ON_P95"]["unknown_direction"] == 1
    assert rows["SAMPLE_ON_P95"]["optimistic"] == 0
    assert rows["SAMPLE_BOOL"]["unknown_direction"] == 1
    assert rows["SAMPLE_NAN"]["unknown_direction"] == 1
    assert rows["SAMPLE_BOTH"]["unknown_direction"] == 1
    assert "SAMPLE_FLAGGED_UNMATCHED" not in rows
    assert body["counts"]["unmatched"] == 1
    assert rows["SAMPLE_INSIDE"]["gaps"] == 0 and rows["SAMPLE_INSIDE"]["compared"] == 1
    assert body["encounters"]["optimistic"] == []
    assert body["encounters"]["pessimistic"] == []


def test_engine_start_flags_are_mechanics_without_a_catalog():
    mod = _mod()
    setup = next(iter(ENCOUNTER_SETUP))
    rotating = next(iter(ROTATING_START))
    body = mod.triage_reports([_report([
        _fight(setup, 40, 0, 5, True, room="Elite"),
        _fight(rotating, 1, 4, 9, True),
    ])], catalog=mod.empty_catalog())
    rows = _by_id(body["encounters"]["all"])
    assert "encounter_setup" in rows[setup]["mechanics"]
    assert any(
        item["file"] == "sts2sim/enemies.py" and item["symbol"] == "ENCOUNTER_SETUP"
        for item in rows[setup]["code"]
    )
    assert "rotating_start" in rows[rotating]["mechanics"]
    assert any(item["symbol"] == "ROTATING_START" for item in rows[rotating]["code"])
    assert rows[setup]["lean"] == "optimistic"
    assert rows[rotating]["lean"] == "pessimistic"


def test_catalog_from_records_unions_powers_and_summon():
    mod = _mod()
    monsters = [
        {
            "id": "MONSTER.SAMPLE_STRANGLER",
            "innate_powers": [{"power_id": "CONSTRICT", "amount": 2}],
            "moves": [{"intent": "Summon", "powers": [{"power_id": "SUCK", "target": "self"}]}],
        },
        {
            "id": "SAMPLE_OTHER",
            "innate_powers": [{"power_id": "THORNS"}],
            "moves": [{"intent": "Status"}],
        },
    ]
    encounters = [
        {"id": "ENCOUNTER.SAMPLE_PACK", "monsters": [{"id": "SAMPLE_STRANGLER"}]},
        {"id": "SAMPLE_ONLY", "monsters": [{"id": "MONSTER.SAMPLE_OTHER"}]},
    ]
    compositions = {"SAMPLE_PACK": {"alternatives": [[1, ["SAMPLE_STRANGLER", "SAMPLE_OTHER"]]]}}
    catalog = mod.catalog_from_records(monsters, encounters, compositions)
    pack = catalog["encounters"]["SAMPLE_PACK"]
    assert pack["powers"] == ["CONSTRICT", "SUCK", "THORNS"]
    assert pack["mechanics"] == ["summon_skipped", "status_card"]
    assert pack["monsters"] == ["SAMPLE_STRANGLER", "SAMPLE_OTHER"]
    only = catalog["encounters"]["SAMPLE_ONLY"]
    assert only["powers"] == ["THORNS"]
    assert only["mechanics"] == ["status_card"]


def test_existing_calibrate_fixture_elite_is_optimistic(tmp_path):
    mod = _mod()
    before_real = _read(REAL, binary=True)
    before_sims = _read(SIMS, binary=True)
    report = calibrate_paths(REAL, SIMS, restricted=False)
    dest = tmp_path / "calibration.json"
    dest.write_text(json.dumps(report), encoding="utf-8")
    body = mod.analyze([str(dest)])
    assert _read(REAL, binary=True) == before_real
    assert _read(SIMS, binary=True) == before_sims
    assert _ids(body["encounters"]["optimistic"]) == ["SAMPLE_ELITE"]
    assert body["encounters"]["pessimistic"] == []
    elite = _by_id(body["encounters"]["all"])["SAMPLE_ELITE"]
    assert elite["optimistic"] == 1 and elite["powers"] == [] and elite["mechanics"] == []
    fight = _by_id(body["encounters"]["all"])["SAMPLE_FIGHT"]
    assert fight["gaps"] == 0 and fight["monsters"] == ["SAMPLE"]
    text = mod.render_markdown(body)
    assert "SAMPLE_ELITE" in text and "sts2sim/powers_enemy.py" in text
    assert "sts2sim/enemies.py" in text


def test_cli_json_out_and_refusals(tmp_path, capsys):
    mod = _mod()
    out = tmp_path / "triage.md"
    js = tmp_path / "triage.json"
    code = mod.main([ONE, TWO, "--catalog", CATALOG, "--out", str(out), "--json", str(js), "--top", "2"])
    assert code == 0
    assert "SAMPLE_ELITE" in out.read_text(encoding="utf-8")
    loaded = json.loads(js.read_text(encoding="utf-8"))
    assert loaded["counts"]["optimistic"] == 3
    captured = capsys.readouterr()
    assert "Sim-gap triage" in captured.out
    assert captured.err == ""

    code = mod.main([ONE, "--json", "-"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["read_only"] is True and payload["counts"]["compared"] == 3
    assert "Sim-gap triage" not in captured.out

    missing = mod.main([os.path.join(FIX, "missing.json")])
    captured = capsys.readouterr()
    assert missing == 2 and "Not found" in captured.err

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert mod.main([str(broken)]) == 2
    captured = capsys.readouterr()
    assert "Not JSON" in captured.err

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "skip.json").write_text(_read(os.path.join(FIX, "skip.json")), encoding="utf-8")
    assert mod.main([str(empty)]) == 2

    refused = mod.main([ONE, "--out", str(tmp_path / "out.run")])
    captured = capsys.readouterr()
    assert refused == 2 and "Refusing to write" in captured.err

    bad_catalog = tmp_path / "catalog.json"
    bad_catalog.write_text("[]", encoding="utf-8")
    assert mod.main([ONE, "--catalog", str(bad_catalog)]) == 2
    captured = capsys.readouterr()
    assert "catalog" in captured.err.lower() or "名册" in captured.err
