"""Loss timelines are recorded facts, bounded, and absent for wins and old rows."""
import json
import random

from sts2sim.ai.heuristic import HeuristicAgent
from sts2sim.cards import CardDef
from sts2sim.core import Card, Combat, Player
from sts2sim.enemies import Enemy
from sts2sim.fightcheck import FOES
from sts2sim.fighttrace import MAX_LOSS_TRACES, cap_loss_traces, pack, trace_status


def _mod():
    box = type("Mod", (), {})()
    box.cards = {}
    box.listeners = []
    box.hook_modules = []
    box.ai_values = {}
    return box


def _jab():
    return CardDef({
        "id": "JAB", "name": "Jab", "type": "攻击", "cost": 1, "target": "enemy",
        "vars": {"dmg": 6}, "effects": [{"op": "damage", "amount": "dmg"}],
    })


def _fight(hp, turns=6):
    player = Player("Hero", hp, 3, 5)
    player.draw_pile = [Card(_jab()) for _ in range(4)]
    rng = random.Random(1)
    enemy = Enemy(FOES[0], rng)
    combat = Combat(player, [enemy], _mod(), rng=rng, agent=HeuristicAgent(), max_turns=turns)
    combat.trace = []
    result = combat.run()
    return combat, result


def test_loss_trace_records_play_enemy_and_zero_hp():
    combat, result = _fight(10)
    assert result == "loss"
    trace = pack(combat, result)
    assert trace["result"] == "loss"
    kinds = [event["kind"] for event in trace["events"]]
    assert "play" in kinds
    assert "enemy" in kinds
    assert "turn_start" in kinds
    assert any(event.get("hp_zero") for event in trace["events"])
    assert trace["loss_turn"] == combat.turn
    play = next(event for event in trace["events"] if event["kind"] == "play")
    assert play["card"] == "JAB"
    enemy = next(event for event in trace["events"] if event["kind"] == "enemy")
    assert enemy["move"]
    assert enemy["hp"] > 0


def test_win_or_timeout_does_not_keep_a_trace_and_clone_does_not_record():
    combat, result = _fight(70, turns=1)
    assert result != "loss"
    assert pack(combat, result) is None
    parent = []
    combat.trace = parent
    cloned = combat.clone()
    assert cloned.trace is None
    assert cloned.is_sim is True
    cloned.player.hp = 1
    assert parent == []


def test_batch_keeps_only_a_bounded_number_of_loss_traces():
    rows = []
    for i in range(MAX_LOSS_TRACES + 3):
        rows.append({"result": "loss", "trace": {"version": 1, "result": "loss", "events": [{"kind": "end", "n": i}]}})
    rows.append({"result": "win"})
    capped = cap_loss_traces(rows)
    kept = [row for row in capped if isinstance(row.get("trace"), dict) and row["trace"].get("events")]
    omitted = [row for row in capped if isinstance(row.get("trace"), dict) and row["trace"].get("omitted") == "batch_cap"]
    assert len(kept) == MAX_LOSS_TRACES
    assert len(omitted) == 3
    assert "trace" not in capped[-1]
    assert trace_status({"result": "loss"}) == "no_trace"
    assert trace_status({"result": "win"}) == "not_a_loss"
    assert trace_status(capped[0]) == "ready"
    assert trace_status(omitted[0]) == "omitted"


def test_run_fight_keeps_a_loss_trace_for_the_synthetic_brute(tmp_path, monkeypatch):
    import yaml

    from sts2sim.customcards import blank, prepare_save
    from sts2sim.runner import _MODSETS, run_fight

    lib = blank()
    lib["name"] = "trace_cards"
    lib["character"]["hp"] = 10
    _library, files, _warnings = prepare_save(lib)
    files["mod.yaml"] = files["mod.yaml"].rstrip() + "\ndecks:\n- decks.yaml\n"
    files["decks.yaml"] = yaml.safe_dump([{
        "id": "jab_deck", "name": "Jab", "character": "Hero", "stage": "custom",
        "acts": [1], "cards": ["JAB×4"],
    }], allow_unicode=True)
    folder = tmp_path / "mods" / "trace_cards"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    monkeypatch.setenv("STS2SIM_USER_MODS", str(tmp_path / "mods"))
    _MODSETS.clear()
    out = run_fight(["trace_cards"], "jab_deck", 1, "probe", 0, 1, encounter_id="SYN_BRUTE", max_turns=8)
    assert out["result"] == "loss"
    assert out["encounter"] == "SYN_BRUTE"
    assert out["trace"]["result"] == "loss"
    assert any(event.get("kind") == "enemy" for event in out["trace"]["events"])
    assert any(event.get("hp_zero") for event in out["trace"]["events"])
    _MODSETS.clear()


def test_replay_api_reads_a_saved_loss_and_an_old_row(tmp_path, monkeypatch):
    pytest_http()
    from fastapi.testclient import TestClient

    from gui.server import app

    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    run = tmp_path / "runs" / "loss-1" / "out"
    run.mkdir(parents=True)
    combat, result = _fight(10)
    assert result == "loss"
    trace = pack(combat, result)
    rows = [
        {"deck": "old", "encounter": "DUMMY", "result": "loss", "turns": 2, "hp_left": 0},
        {"deck": "new", "encounter": "SYN_BRUTE", "enc_name": "蛮兵", "result": "loss",
         "turns": trace["turns"], "hp_left": 0, "trace": trace},
    ]
    with open(run / "raw.jsonl", "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    meta = {
        "id": "loss-1", "kind": "combat", "status": "done", "title": "loss",
        "params": {}, "created": "2026-11-21T00:00:00",
    }
    (tmp_path / "runs" / "loss-1" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    # JobManager reads paths.RUNS_DIR, which is fixed at import. Point the lookup at this folder
    # by calling the reader directly, then the HTTP route with a patched run dir.
    from gui import replay
    listed = replay.list_fights(str(tmp_path / "runs" / "loss-1"))
    assert [row["trace"] for row in listed["fights"]] == ["no_trace", "ready"]
    loaded = replay.load_trace(str(tmp_path / "runs" / "loss-1"), 1)
    assert loaded["status"] == "ready"
    assert any(event.get("hp_zero") for event in loaded["trace"]["events"])
    old = replay.load_trace(str(tmp_path / "runs" / "loss-1"), 0)
    assert old["status"] == "no_trace"
    assert old["trace"] is None

    from gui import paths
    monkeypatch.setattr(paths, "RUNS_DIR", str(tmp_path / "runs"))
    with TestClient(app) as client:
        missing = client.get("/api/runs/does-not-exist/fights", headers={"x-lang": "en"})
        assert missing.status_code == 404
        assert "Traceback" not in missing.text
        listed_http = client.get("/api/runs/loss-1/fights", headers={"x-lang": "en"})
        assert listed_http.status_code == 200, listed_http.text
        assert [row["trace"] for row in listed_http.json()["fights"]] == ["no_trace", "ready"]
        traced = client.get("/api/runs/loss-1/trace/1", headers={"x-lang": "en"})
        assert traced.status_code == 200
        assert traced.json()["status"] == "ready"
        assert any(event.get("hp_zero") for event in traced.json()["trace"]["events"])
        batch = {
            "id": "batch-1", "kind": "batch", "status": "done", "title": "batch",
            "params": {}, "created": "2026-11-21T00:00:00",
        }
        batch_dir = tmp_path / "runs" / "batch-1"
        batch_dir.mkdir()
        (batch_dir / "meta.json").write_text(json.dumps(batch), encoding="utf-8")
        refused = client.get("/api/runs/batch-1/fights", headers={"x-lang": "en"})
        assert refused.status_code == 400
        assert "Traceback" not in refused.text


def pytest_http():
    import pytest
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
