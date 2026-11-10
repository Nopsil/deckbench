"""单卡贡献：留一法的场数上限、Wilson 噪声标记，以及 HTTP / MCP。

变体走原来的战斗测试。卡组 id、遭遇、种子、回合上限不变。不改出牌。
"""
import json
import os
import time

import pytest

from sts2sim.cardimpact import (
    allocate_fights,
    build_report,
    fight_stats,
    impact_row,
    plan_ablation,
    scale_plan,
)
from sts2sim.deckpresets import DeckPresetError, list_cards
from sts2sim.stats import MIN_N, wilson_interval

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = {"x-lang": "en"}
SECRET = "SECRET-DO-NOT-LEAK"
QUICK = os.path.join(ROOT, "experiments", "quick.yaml")


def _fights(wins, losses, hp, turns):
    rows = []
    for _ in range(wins):
        rows.append({"result": "win", "hp_lost": hp, "turns": turns})
    for _ in range(losses):
        rows.append({"result": "loss", "hp_lost": hp + 4, "turns": turns + 2})
    return rows


def test_scale_keeps_the_cap_and_can_refuse():
    same, each, total, scaled = scale_plan([{"id": "DUMMY", "fights": 1, "act": 0}], 3)
    assert scaled is False and each == 1 and total == 3 and same[0]["act"] == 0

    shrunk, each, total, scaled = scale_plan([{"id": "DUMMY", "fights": 200}], 3, scale=True)
    assert scaled is True and each == 133 and total == 399 and shrunk[0]["fights"] == 133

    with pytest.raises(DeckPresetError) as refused:
        scale_plan([{"id": "DUMMY", "fights": 200}], 3, scale=False)
    assert refused.value.code == "too_many_fights" and refused.value.params["n"] == 400

    with pytest.raises(DeckPresetError) as impossible:
        scale_plan([{"id": "DUMMY", "fights": 1}], 401, scale=True)
    assert impossible.value.code == "too_many_fights"

    shared = allocate_fights([{"id": "A", "fights": 2}, {"id": "B", "fights": 1}], 2)
    assert [(row["id"], row["fights"]) for row in shared] == [("A", 1), ("B", 1)]


def test_impact_row_uses_wilson_and_flags_noise():
    baseline = _fights(40, 10, 10, 3)
    variant = _fights(20, 30, 12, 4)
    spec = {
        "card_id": "YIHESHI", "upgrade": False, "change": "remove",
        "count": 0, "baseline_count": 1, "name": "已核实", "name_zh": "已核实", "name_en": "Yiheshi",
        "run": "variant-1",
    }
    row = impact_row(spec, baseline, variant)
    base = fight_stats(baseline)
    other = fight_stats(variant)
    assert row["n"] == 50 and row["n_baseline"] == 50
    assert row["delta_win"] == pytest.approx(other["win_rate"] - base["win_rate"])
    assert row["delta_hp_lost"] == pytest.approx(other["hp_lost"] - base["hp_lost"])
    assert row["delta_turns"] == pytest.approx(other["turns"] - base["turns"])
    assert row["delta_win"] == pytest.approx(-0.4)
    assert row["win_effect"] == "helps" and row["hp_effect"] == "helps"
    blo, bhi = wilson_interval(base["wins"], base["n"])
    vlo, vhi = wilson_interval(other["wins"], other["n"])
    assert row["baseline_ci_low"] == blo and row["baseline_ci_high"] == bhi
    assert row["win_ci_low"] == vlo and row["win_ci_high"] == vhi
    assert row["ci_method"] == "wilson"
    assert row["wilson_overlap"] is False
    assert row["noisy"] is False and row["noisy_reason"] is None
    assert row["sample_warning"] is False and row["min_n"] == MIN_N

    added = dict(spec, change="add", run="variant-add")
    plus = impact_row(added, baseline, variant)
    assert plus["delta_win"] < 0 and plus["win_effect"] == "hurts"
    assert plus["delta_hp_lost"] > 0 and plus["hp_effect"] == "hurts"

    tiny = impact_row(spec, [{"result": "win", "hp_lost": 0, "turns": 1}], [{"result": "loss", "hp_lost": 5, "turns": 1}])
    assert tiny["n"] == 1 and tiny["noisy"] is True and tiny["noisy_reason"] == "too_small"
    assert tiny["sample_warning"] is True

    wide = impact_row(
        spec,
        [{"result": "win", "hp_lost": 1, "turns": 1}] * 40 + [{"result": "loss", "hp_lost": 2, "turns": 1}] * 10,
        [{"result": "win", "hp_lost": 1, "turns": 1}] * 39 + [{"result": "loss", "hp_lost": 2, "turns": 1}] * 11,
    )
    assert wide["n"] == 50 and wide["sample_warning"] is False
    assert wide["wilson_overlap"] is True and wide["noisy"] is True
    assert wide["noisy_reason"] == "wilson_overlap"


def test_build_report_skips_a_variant_with_no_fights():
    plan = {
        "deck": "demo", "title": "Demo", "plus": False, "scale": True, "scaled": False,
        "seed": 1, "agent": "heuristic", "max_turns": 1,
        "encounters": [{"id": "DUMMY", "fights": 1}], "fights": 1, "total_fights": 2, "cap": 400,
        "variants": [
            {"role": "baseline", "change": "baseline", "card_id": "", "upgrade": False, "cards": ["A"]},
            {"role": "variant", "change": "remove", "card_id": "A", "upgrade": False,
             "count": 0, "baseline_count": 1, "name": "A", "name_zh": "", "name_en": "A"},
        ],
        "skipped": [],
    }
    doc = build_report(plan, [
        {"id": "base", "status": "done", "fights": [{"result": "win", "hp_lost": 0, "turns": 1}]},
        {"id": "gone", "status": "cancelled", "fights": []},
    ], status="cancelled", partial=True)
    assert doc["method"] == "leave_one_out"
    assert doc["baseline"]["n"] == 1 and doc["baseline"]["run"] == "base"
    assert doc["rows"] == []
    assert doc["partial"] is True
    assert [row["status"] for row in doc["runs"]] == ["done", "cancelled"]


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(data))
    monkeypatch.delenv("DECKBENCH_PRESETS_DIR", raising=False)
    return data


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app
    with TestClient(app) as running:
        yield running


def _payload(pid, cards=None, fights=1, turns=1, seed=1):
    return {
        "id": pid,
        "name": "Impact " + pid,
        "mod": "claude_v34",
        "seed": seed,
        "max_turns": turns,
        "encounters": [{"id": "DUMMY", "fights": fights}],
        "cards": cards or [
            {"id": "YIHESHI", "count": 1, "upgrade": False},
            {"id": "XIAOBENBEN", "count": 1, "upgrade": False},
        ],
    }


def _runs_dir(allowed, monkeypatch):
    from gui import paths
    runs = allowed / "runs"
    runs.mkdir(exist_ok=True)
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))
    return runs


def _wait(client, rid, timeout=180):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        res = client.get(f"/api/runs/{rid}/progress", headers=EN)
        assert res.status_code == 200, res.text
        assert "Traceback" not in res.text
        last = res.json()
        if last.get("status") not in ("running", "queued"):
            return last
        time.sleep(0.05)
    raise AssertionError(last)


def _detail(res):
    body = res.json()
    assert isinstance(body.get("detail"), str)
    assert "Traceback" not in res.text
    assert SECRET not in res.text
    return body["detail"]


def test_plan_scales_or_refuses_before_a_fight(client, allowed):
    cards = [
        {"id": cid, "count": 1, "upgrade": False}
        for cid in ("YIHESHI", "XIAOBENBEN", "DUOLUN", "JIHUA", "QINGQIAO")
    ]
    saved = client.post("/api/decks", headers=EN, json=_payload("bigdeck", cards, fights=80))
    assert saved.status_code == 200, saved.text
    with pytest.raises(DeckPresetError) as refused:
        plan_ablation("bigdeck", {"scale": False})
    assert refused.value.code == "too_many_fights"
    plan = plan_ablation("bigdeck", {"scale": True})
    assert plan["scaled"] is True
    assert plan["fights"] == 66 and plan["total_fights"] == 396
    assert len(plan["variants"]) == 6
    assert plan["variants"][0]["change"] == "baseline"
    catalog = {card["id"]: card for card in list_cards(q="YIHESHI", limit=20)["cards"]}
    known = catalog["YIHESHI"]
    row = next(item for item in plan["variants"] if item["card_id"] == "YIHESHI")
    assert row["name_zh"] == known["name_zh"] and row["name_en"] == known["name_en"]
    assert row["name"] == known["name"]

    alone = client.post("/api/decks", headers=EN, json=_payload(
        "onecard", [{"id": "YIHESHI", "count": 1, "upgrade": False}],
    ))
    assert alone.status_code == 200
    with pytest.raises(DeckPresetError) as empty:
        plan_ablation("onecard", {})
    assert empty.value.code == "ablation"


def _bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def test_card_impact_endpoint_and_mcp_match_on_a_dummy(client, allowed, monkeypatch):
    from tools import mcp_server as mcp
    before = _bytes(QUICK)
    runs = _runs_dir(allowed, monkeypatch)
    saved = client.post("/api/decks", headers=EN, json=_payload("impactd", fights=1, turns=1, seed=7))
    assert saved.status_code == 200, saved.text

    missing = client.get("/api/decks/impactd/card_impact", headers=EN)
    assert missing.status_code == 404 and "Traceback" not in missing.text

    bad = client.post("/api/decks/impactd/card_impact", headers=EN, json={"plus": "yes"})
    assert bad.status_code == 400 and "boolean" in _detail(bad).lower()
    leaked = client.post("/api/decks/impactd/card_impact", headers=EN, json={"path": SECRET})
    assert leaked.status_code == 400
    _detail(leaked)
    unknown = client.post("/api/decks/nosuchdeck/card_impact", headers=EN, json={})
    assert unknown.status_code == 400
    _detail(unknown)
    climbed = client.post("/api/decks/1bad/card_impact", headers=EN, json={})
    assert climbed.status_code == 400
    _detail(climbed)

    res = client.post("/api/decks/impactd/card_impact", headers=EN, json={"plus": False, "seed": 7})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and body["status"] == "running"
    assert body["scaled"] is False and body["total_fights"] == 3 and body["fights"] == 1
    assert body["seed"] == 7 and body["max_turns"] == 1 and body["encounters"] == ["DUMMY"]
    assert [row["change"] for row in body["runs"]] == ["baseline", "remove", "remove"]
    ids = {row["change"] + ":" + row["card_id"]: row["id"] for row in body["runs"]}
    assert len(set(ids.values())) == 3
    progress = _wait(client, body["id"])
    assert progress["status"] == "done" and progress["partial"] is False
    assert progress["done"] == 3 and progress["total"] == 3

    doc = client.get("/api/decks/impactd/card_impact", headers=EN)
    assert doc.status_code == 200, doc.text
    report = doc.json()
    same = client.get(f"/api/runs/{body['id']}/card_impact", headers=EN)
    assert same.status_code == 200 and same.json()["rows"] == report["rows"]
    assert report["method"] == "leave_one_out" and report["status"] == "done"
    assert len(report["rows"]) == 2
    for row in report["rows"]:
        assert row["n"] == 1 and row["n_baseline"] == 1
        assert row["noisy"] is True and row["noisy_reason"] == "too_small"
        assert row["ci_method"] == "wilson"
        assert row["delta_win"] == pytest.approx(row["win_rate"] - row["win_rate_baseline"])
        assert row["delta_hp_lost"] == pytest.approx(row["hp_lost"] - row["hp_lost_baseline"])
        assert row["delta_turns"] == pytest.approx(row["turns"] - row["turns_baseline"])
        known = next(
            card for card in list_cards(q=row["card_id"], mod="claude_v34", limit=20)["cards"]
            if card["id"] == row["card_id"]
        )
        assert row["name"] == known["name"] and row["name_zh"] == known["name_zh"]
        lo, hi = wilson_interval(row["wins"], row["n"])
        assert row["win_ci_low"] == lo and row["win_ci_high"] == hi

    from sts2sim.runner import _seed
    base_exp = json.loads(json.dumps(_yaml(runs / ids["baseline:"] / "experiment.yaml")))
    cut = next(row for row in body["runs"] if row["card_id"] == "YIHESHI")
    cut_exp = _yaml(runs / cut["id"] / "experiment.yaml")
    assert base_exp["seed"] == cut_exp["seed"] == 7
    assert base_exp["decks"] == cut_exp["decks"] == ["impactd"]
    assert base_exp["extra"][0]["encounter"] == cut_exp["extra"][0]["encounter"] == "DUMMY"
    assert base_exp["extra"][0]["max_turns"] == cut_exp["extra"][0]["max_turns"] == 1
    assert _seed(7, "impactd", base_exp["extra"][0]["act"], base_exp["extra"][0]["room"], 0, "DUMMY") == _seed(
        7, "impactd", cut_exp["extra"][0]["act"], cut_exp["extra"][0]["room"], 0, "DUMMY",
    )
    base_cards = (runs / ids["baseline:"] / "user_mods" / "impactd" / "decks.yaml").read_text(encoding="utf-8")
    cut_cards = (runs / cut["id"] / "user_mods" / "impactd" / "decks.yaml").read_text(encoding="utf-8")
    assert "YIHESHI" in base_cards and "XIAOBENBEN" in base_cards
    assert "YIHESHI" not in cut_cards and "XIAOBENBEN" in cut_cards

    child = client.get(f"/api/runs/{cut['id']}/card_impact", headers=EN)
    assert child.status_code == 400 and "card-impact" in _detail(child).lower()
    exported = client.get(f"/api/runs/{body['id']}/export.html", headers=EN)
    assert exported.status_code == 200, exported.text
    assert "YIHESHI" in exported.text and "Too small" in exported.text
    assert "Traceback" not in exported.text
    assert _bytes(QUICK) == before

    mcp_saved = client.post("/api/decks", headers=EN, json=_payload("mcpimpact", seed=4, turns=1))
    assert mcp_saved.status_code == 200
    started = json.loads(mcp.card_impact("mcpimpact", plus=False, max_turns=1, seed=4))
    assert started["ok"] is True and started["total_fights"] == 3
    assert _wait(client, started["id"])["status"] == "done"
    fetched = json.loads(mcp.card_impact(job=started["id"]))
    assert fetched["ok"] is True and len(fetched["rows"]) == 2
    assert "Traceback" not in json.dumps(fetched)
    child_id = next(row["id"] for row in started["runs"] if row["change"] == "remove")
    same_deck = json.loads(mcp.card_impact(job=child_id))
    assert same_deck["ok"] is False and same_deck["error"] == "not_impact"
    absent = json.loads(mcp.card_impact(job="missing-impact"))
    assert absent["ok"] is False and absent["error"] == "not_found"
    broken = json.loads(mcp.card_impact("mcpimpact", encounters="{"))
    assert broken["ok"] is False and broken["error"] == "bad_json"


def test_card_impact_cancel_leaves_a_partial_export(client, allowed, monkeypatch):
    monkeypatch.setenv("DECKBENCH_FIGHT_GAP", "0.2")
    runs = _runs_dir(allowed, monkeypatch)
    saved = client.post("/api/decks", headers=EN, json=_payload("cancelimpact", fights=12, turns=1, seed=2))
    assert saved.status_code == 200, saved.text
    res = client.post("/api/decks/cancelimpact/card_impact", headers=EN, json={})
    assert res.status_code == 200, res.text
    job = res.json()["id"]
    deadline = time.time() + 60
    seen = None
    while time.time() < deadline:
        seen = client.get(f"/api/runs/{job}/progress", headers=EN).json()
        if seen.get("done", 0) >= 1 or seen.get("status") not in ("running", "queued"):
            break
        time.sleep(0.05)
    assert seen and seen.get("done", 0) >= 1, seen
    cancelled = client.post(f"/api/runs/{job}/cancel", headers=EN)
    assert cancelled.status_code == 200 and cancelled.json()["ok"] is True
    final = _wait(client, job)
    assert final["status"] == "cancelled" and final["partial"] is True
    assert final["done"] < final["total"]
    report = client.get(f"/api/runs/{job}/card_impact", headers=EN)
    assert report.status_code == 200 and report.json()["partial"] is True
    exported = client.get(f"/api/runs/{job}/export.html", headers=EN)
    assert exported.status_code == 200
    assert "Partial result" in exported.text
    assert (runs / job / "card_impact.json").is_file()


def test_combat_rejects_a_card_that_is_not_in_the_preset(client, allowed, monkeypatch):
    _runs_dir(allowed, monkeypatch)
    saved = client.post("/api/decks", headers=EN, json=_payload("guarded"))
    assert saved.status_code == 200, saved.text
    res = client.post("/api/runs", headers=EN, json={
        "kind": "combat",
        "params": {
            "preset": "guarded",
            "deck_cards": ["CLAUDE_STRIKE"],
            "fights": 1,
            "procs": 1,
        },
    })
    assert res.status_code == 400
    assert "Traceback" not in res.text
    assert "CLAUDE_STRIKE" not in res.text


def _yaml(path):
    import yaml
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)
