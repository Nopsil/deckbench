"""决策说明日志：默认关闭；打开后同一颗种子的结果和随机数流不变。"""
import json
import os
import random
import subprocess
import sys

import pytest

from sts2sim import explain
from sts2sim.ai.beam import BeamAgent
from sts2sim.ai.heuristic import HeuristicAgent
from sts2sim.cards import CardDef
from sts2sim.core import Card, Combat, Player
from sts2sim.enemies import Enemy, MonsterDef
from sts2sim.potions import POTION_DEFS, PotionDef


class _Mod:
    listeners = []
    hook_modules = []
    cards = {}


def _register_potion():
    POTION_DEFS["TEST_POT"] = PotionDef({
        "id": "TEST_POT", "name": "试验药水", "target": "enemy",
        "effects": [{"op": "damage", "amount": 12, "kind": "power"}],
    })


def _fight(agent):
    Card._uid[0] = 0
    strike = CardDef({"id": "STRIKE", "name": "打击", "type": "攻击", "cost": 1, "target": "enemy",
                      "effects": [{"op": "damage", "amount": 8}]})
    defend = CardDef({"id": "DEFEND", "name": "防御", "type": "技能", "cost": 1, "target": "self",
                      "effects": [{"op": "block", "amount": 5}]})
    spin = CardDef({"id": "SPIN", "name": "乱击", "type": "攻击", "cost": 1, "target": "none",
                    "effects": [{"op": "damage", "amount": 4, "target": "random"}]})
    foes = []
    for name, hp in (("甲", 14), ("乙", 28)):
        raw = {"id": name, "name": name, "min_hp": hp, "max_hp": hp,
               "moves": [{"id": "HIT", "name": "打", "intent": "Attack",
                          "damage": {"normal": 7, "hit_count": 1}}]}
        foes.append(Enemy(MonsterDef(raw, name), random.Random(0)))
    player = Player("铁甲", 12, energy_per_turn=3, hand_size=5)
    player.potions = ["TEST_POT"]
    player.draw_pile = [Card(strike), Card(defend), Card(spin), Card(strike), Card(defend), Card(strike)]
    return Combat(player, foes, _Mod(), rng=random.Random(12345), agent=agent, max_turns=4)


def _fingerprint(combat):
    return {
        "result": combat.result,
        "turn": combat.turn,
        "hp": combat.player.hp,
        "block": combat.player.block,
        "potions": list(combat.player.potions),
        "enemies": [(e.name, e.hp, e.alive) for e in combat.enemies],
        "rng": combat.rng.getstate(),
        "clones": combat._clone_n,
        "cards": combat.stats.card,
    }


def _agent(cls):
    if cls is BeamAgent:
        return BeamAgent(width=2, depth=2)
    return cls()


def _run(agent_cls, on):
    explain.configure(on=on, reset=True)
    combat = _fight(_agent(agent_cls))
    combat.run()
    rows = explain.take()
    explain.configure(on=False, reset=True)
    return _fingerprint(combat), rows


@pytest.fixture(autouse=True)
def _explain_off():
    explain.configure(on=False, reset=True)
    yield
    explain.configure(on=False, reset=True)
    POTION_DEFS.pop("TEST_POT", None)


def test_off_records_nothing_and_same_seed_matches_on():
    _register_potion()
    for cls in (HeuristicAgent, BeamAgent):
        off, rows_off = _run(cls, False)
        on, rows_on = _run(cls, True)
        assert rows_off == []
        assert off == on
        kinds = {r["kind"] for r in rows_on}
        assert "play" in kinds
        assert "target" in kinds
        assert "potion" in kinds
        for row in rows_on:
            assert row["v"] == 1
            assert "candidates" in row
            assert len(row["candidates"]) <= 5 or any(c.get("picked") for c in row["candidates"])
            if row["chosen"] and isinstance(row["chosen"], dict) and row["chosen"].get("id") not in (None, "end_turn"):
                assert any(c.get("picked") for c in row["candidates"])


def test_publish_is_a_noop_when_off():
    explain.configure(on=False, reset=True)
    explain.publish([{"kind": "play", "chosen": {"id": "X", "score": 1}, "candidates": [{"id": "X", "score": 1}]}])
    assert explain.take() == []


def test_outer_decision_replaces_inner_scores():
    explain.configure(on=True, reset=True)
    with explain.scope():
        with explain.scope():
            explain.publish(explain.from_steps(
                [{"kind": "play", "id": "A", "score": 1}],
                {"kind": "play", "id": "A", "score": 1}))
        steps = [
            {"kind": "play", "id": "B", "target": "甲#0", "score": 2},
            {"kind": "play", "id": "C", "target": "乙#1", "score": 0.1},
        ]
        explain.publish(explain.from_steps(steps, {"kind": "play", "id": "B", "target": "甲#0", "score": 2}))
    rows = explain.take()
    assert [r["kind"] for r in rows] == ["play", "target"]
    assert rows[0]["chosen"]["id"] == "B"
    assert rows[0]["candidates"][0]["picked"] is True
    assert rows[1]["chosen"]["target"] == "甲#0"


def test_low_score_choice_stays_in_the_top_list():
    cands = [{"id": f"C{i}", "score": i} for i in range(8)]
    chosen = {"id": "C0", "score": 0}
    kept = explain.top(cands, chosen, n=3)
    assert [c["score"] for c in kept[:3]] == [7, 6, 5]
    assert kept[-1]["id"] == "C0" and kept[-1].get("picked") is True


def test_render_one_fight_and_cli(tmp_path):
    rows = [
        {"v": 1, "seq": 1, "kind": "play", "seed": "S", "fight": 1, "floor": 2, "turn": 1,
         "chosen": {"id": "STRIKE", "target": "甲#0", "score": 3.5},
         "candidates": [{"id": "STRIKE", "target": "甲#0", "score": 3.5, "picked": True},
                        {"id": "DEFEND", "score": 1.0}]},
        {"v": 1, "seq": 2, "kind": "target", "seed": "S", "fight": 1, "floor": 2, "turn": 1, "card": "STRIKE",
         "chosen": {"id": "STRIKE", "target": "甲#0", "score": 3.5},
         "candidates": [{"id": "STRIKE", "target": "甲#0", "score": 3.5, "picked": True},
                        {"id": "STRIKE", "target": "乙#1", "score": 1.2}]},
        {"v": 1, "seq": 3, "kind": "potion", "seed": "S", "fight": 1, "floor": 2, "turn": 1,
         "chosen": None, "candidates": [{"id": "TEST_POT", "score": 2.0}], "threshold": 12},
        {"v": 1, "seq": 4, "kind": "reward", "seed": "S", "floor": 2,
         "chosen": {"id": "skip", "score": 4}, "candidates": [{"id": "STRIKE", "score": 3}, {"id": "skip", "score": 4, "picked": True}],
         "threshold": 4},
        {"v": 1, "seq": 5, "kind": "play", "seed": "S", "fight": 2, "floor": 3, "turn": 1,
         "chosen": {"id": "DEFEND", "score": 1}, "candidates": [{"id": "DEFEND", "score": 1, "picked": True}]},
    ]
    text = explain.render_fight(rows, 0)
    assert "STRIKE" in text and "甲#0" in text
    assert "floor 3" not in text
    assert "奖励" in text
    path = tmp_path / "explain.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "fight.md"
    proc = subprocess.run([sys.executable, "tools/explain_fight.py", str(path), "--fight", "0", "--seed", "S", "--out", str(out)],
                          check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "STRIKE" in out.read_text(encoding="utf-8")
    missing = subprocess.run([sys.executable, "tools/explain_fight.py", str(path), "--fight", "9"],
                             check=False, capture_output=True, text=True)
    assert missing.returncode == 2


def test_sibling_path_and_env(monkeypatch):
    assert explain.sibling_path(None).endswith("explain.jsonl")
    assert explain.sibling_path("runs/out.jsonl").endswith("out.explain.jsonl")
    assert explain.sibling_path("reports/exp").endswith("explain.jsonl")
    monkeypatch.delenv("DECKBENCH_EXPLAIN", raising=False)
    assert explain.requested(False) is False
    assert explain.requested(True) is True
    monkeypatch.setenv("DECKBENCH_EXPLAIN", "1")
    assert explain.requested(False) is True


def test_runner_help_lists_explain():
    proc = subprocess.run([sys.executable, "-m", "sts2sim.runner", "--help"], check=False, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "--explain" in proc.stdout


def test_full_run_seed_unchanged_when_explain_is_on():
    pytest.importorskip("sts2sim.gen.game")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from sts2sim.engine.run import play_run
    import batch

    def once(on):
        explain.configure(on=on, reset=True)
        if on:
            explain.set_ctx(seed="EX1", char="Ironclad", asc=0)
        result = play_run("Ironclad", 0, "EX1", agent=batch.make_agent("heuristic", "EX1")).to_dict()
        rows = explain.take()
        explain.configure(on=False, reset=True)
        return result, rows

    off, rows_off = once(False)
    on, rows_on = once(True)
    for key in ("path", "combats", "picked", "floor", "victory"):
        assert off[key] == on[key], key
    assert rows_off == []
    assert any(r["kind"] == "play" for r in rows_on)
    assert any(r["kind"] == "reward" for r in rows_on)
