"""两次已完成的战斗实验：格子差值、显著性、单卡使用和效率。不新开模拟。"""
import json
import os

import pytest

from sts2sim.report import ratio
from sts2sim.runcompare import compare_dirs
from sts2sim.stats import two_proportion_ztest, welch_ttest, wilson_interval

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = {"x-lang": "en"}
SECRET = "SECRET-DO-NOT-LEAK"


def _fights(n, wins, timeouts, hp, turns, dmg, plays, room="Monster", deck="probe", card="STRIKE"):
    rows = []
    for i in range(n):
        if i < timeouts:
            result = "timeout"
        elif i < timeouts + wins:
            result = "win"
        else:
            result = "loss"
        rows.append({
            "deck": deck,
            "act": 1,
            "room": room,
            "result": result,
            "turns": turns + (i % 3),
            "hp_lost": hp + (i % 4),
            "dmg_total": dmg,
            "cards": {card: [plays, dmg, 0, plays]},
        })
    return rows


def _write_raw(folder, rows):
    os.makedirs(folder, exist_ok=True)
    text = "".join(json.dumps(row) + "\n" for row in rows)
    path = os.path.join(folder, "raw.jsonl")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _meta(rid, kind="combat", status="done", title="T"):
    return {
        "id": rid, "kind": kind, "title": title, "status": status,
        "created": "2026-01-02T00:00:00+00:00", "params": {},
    }


def _install_run(root, rid, rows, **meta):
    run = os.path.join(root, rid)
    out = os.path.join(run, "out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_meta(rid, **meta)))
    if rows is not None:
        _write_raw(out, rows)
    return run


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app
    with TestClient(app) as c:
        yield c


def test_different_decks_on_the_same_room_line_up(tmp_path):
    """卡组 id 不同、幕和房间相同、每一侧只有一套牌时，仍然给出 B−A。同一侧两套牌就不猜。"""
    left = tmp_path / "left"
    right = tmp_path / "right"
    mixed = tmp_path / "mixed"
    _write_raw(str(left), _fights(4, 1, 0, 3, 2, 5, 1, deck="decka", card="YIHESHI"))
    _write_raw(str(right), _fights(4, 3, 0, 1, 2, 9, 2, deck="deckb", card="YIHESHI"))
    body = compare_dirs(str(left), str(right))
    assert len(body["cells"]) == 1
    cell = body["cells"][0]
    assert cell["deck_id"] == "decka/deckb"
    assert cell["deck"] == "decka / deckb"
    assert cell["act"] == 1 and cell["room"] == "Monster"
    assert cell["metrics"]["win"]["delta"] == pytest.approx(0.5)
    assert any(row["card"] == "YIHESHI" and row["deck_id"] == "decka/deckb" for row in body["cards"])
    _write_raw(str(mixed), _fights(2, 1, 0, 1, 1, 1, 1, deck="decka") + _fights(2, 1, 0, 1, 1, 1, 1, deck="deckc"))
    assert compare_dirs(str(mixed), str(right))["cells"] == []


def test_welch_matches_a_known_student_t():
    """[1..5] 对 [3..7]，t=2、df=8，双侧 p 约 0.0805。"""
    report = welch_ttest([1, 2, 3, 4, 5], [3, 4, 5, 6, 7])
    assert report["method"] == "welch"
    assert report["diff"] == pytest.approx(2.0)
    assert report["t"] == pytest.approx(2.0)
    assert report["df"] == pytest.approx(8.0)
    assert report["p_value"] == pytest.approx(0.080516237957, abs=1e-8)
    assert report["p_value"] > 0.05
    flat = welch_ttest([1, 1, 1], [2, 2, 2])
    assert flat["p_value"] == 0.0 and flat["t"] is None
    same = welch_ttest([4, 4], [4, 4])
    assert same["p_value"] == 1.0 and same["diff"] == 0.0
    assert welch_ttest([1], [2, 3])["p_value"] is None


def test_raw_cells_use_ztest_and_welch_and_card_deltas(tmp_path):
    a_rows = _fights(40, 4, 10, 18, 8, 8, 1) + _fights(4, 4, 0, 1, 1, 9, 3, room="探针", card="PROBE")
    b_rows = _fights(40, 28, 0, 5, 3, 30, 2) + _fights(4, 0, 4, 9, 2, 1, 1, room="探针", card="PROBE")
    _write_raw(tmp_path / "a", a_rows)
    _write_raw(tmp_path / "b", b_rows)
    before = (tmp_path / "a" / "raw.jsonl").read_bytes()
    body = compare_dirs(str(tmp_path / "a"), str(tmp_path / "b"))
    assert (tmp_path / "a" / "raw.jsonl").read_bytes() == before
    assert body["sources"] == {"a": "raw", "b": "raw"}
    monster = next(cell for cell in body["cells"] if cell["room"] == "Monster")
    probe = next(cell for cell in body["cells"] if cell["room"] == "探针")
    win = monster["metrics"]["win"]
    timeout = monster["metrics"]["timeout"]
    hp = monster["metrics"]["hp_loss"]
    turns = monster["metrics"]["turns"]
    dpt = monster["metrics"]["dpt"]
    z = two_proportion_ztest(4, 40, 28, 40)
    assert win["delta"] == pytest.approx(z["diff"])
    assert win["p_value"] == pytest.approx(z["p_value"])
    assert win["method"] == "two_proportion_z"
    assert win["significant"] is True
    assert win["wilson_overlap"] is False
    lo_a, hi_a = wilson_interval(4, 40)
    assert win["a_ci_low"] == pytest.approx(lo_a) and win["a_ci_high"] == pytest.approx(hi_a)
    assert win["sample_warning"] is False
    assert timeout["a"] == pytest.approx(0.25) and timeout["b"] == pytest.approx(0.0)
    assert timeout["significant"] is True and timeout["delta"] < 0
    assert hp["method"] == "welch" and hp["significant"] is True and hp["delta"] < 0
    assert turns["method"] == "welch" and turns["delta"] < 0
    assert dpt["method"] == "welch" and dpt["delta"] > 0
    assert probe["metrics"]["win"]["k_a"] == 4
    names = [card["card"] for card in body["cards"]]
    assert names == ["STRIKE"]
    strike = body["cards"][0]
    assert strike["a_per_fight"] == pytest.approx(1.0)
    assert strike["b_per_fight"] == pytest.approx(2.0)
    assert strike["usage_delta"] == pytest.approx(1.0)
    assert strike["usage_method"] == "welch" and strike["usage_significant"] is True
    expect_a = ratio(8 * 40, 0, 40, 40)
    expect_b = ratio(30 * 40, 0, 80, 80)
    assert strike["a_efficiency"] == pytest.approx(expect_a)
    assert strike["b_efficiency"] == pytest.approx(expect_b)
    assert strike["efficiency_delta"] == pytest.approx(expect_b - expect_a)

    small_a = _fights(10, 1, 0, 10, 4, 5, 1)
    small_b = _fights(10, 8, 0, 3, 3, 12, 1)
    _write_raw(tmp_path / "small-a", small_a)
    _write_raw(tmp_path / "small-b", small_b)
    small = compare_dirs(str(tmp_path / "small-a"), str(tmp_path / "small-b"))
    assert small["cells"][0]["metrics"]["win"]["sample_warning"] is True
    assert small["cells"][0]["metrics"]["hp_loss"]["sample_warning"] is True


def test_csv_only_returns_deltas_without_a_welch_p_value(tmp_path):
    header = "卡组id,卡组,阶段,幕,房间,场数,胜率%,战败%,超时%,循环报警场数,平均回合,胜场平均回合,平均掉血,胜场平均掉血,每回合输出,单回合动作≥40场数,最大单回合动作数\n"
    cards = "卡组id,卡组,卡牌/来源,总使用次数,每场使用,每次伤害,每次格挡,每次付费,效率倍数(原版中位=1)\n"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "cells.csv").write_text(
        header + "d,甲,,1,Monster,40,25.0,65.0,10.0,0,5.0,,12.0,,3.0,0,1\n", encoding="utf-8-sig",
    )
    (tmp_path / "b" / "cells.csv").write_text(
        header + "d,甲,,1,Monster,40,50.0,50.0,0.0,0,4.0,,8.0,,6.0,0,1\n", encoding="utf-8-sig",
    )
    (tmp_path / "a" / "cards.csv").write_text(
        cards + "d,甲,打击,40,1.00,6.0,0.0,1.00,0.75\n", encoding="utf-8",
    )
    (tmp_path / "b" / "cards.csv").write_text(
        cards + "d,甲,打击,80,2.00,8.0,0.0,1.00,1.00\n", encoding="utf-8",
    )
    body = compare_dirs(str(tmp_path / "a"), str(tmp_path / "b"))
    assert body["sources"] == {"a": "csv", "b": "csv"}
    cell = body["cells"][0]
    assert cell["deck"] == "甲"
    win = cell["metrics"]["win"]
    assert win["a"] == pytest.approx(0.25) and win["b"] == pytest.approx(0.5)
    assert win["delta"] == pytest.approx(0.25) and win["method"] == "two_proportion_z"
    hp = cell["metrics"]["hp_loss"]
    assert hp["a"] == pytest.approx(12.0) and hp["b"] == pytest.approx(8.0)
    assert hp["delta"] == pytest.approx(-4.0)
    assert hp["method"] == "means_only" and hp["p_value"] is None and hp["significant"] is None
    assert cell["metrics"]["turns"]["delta"] == pytest.approx(-1.0)
    assert cell["metrics"]["dpt"]["delta"] == pytest.approx(3.0)
    assert cell["metrics"]["timeout"]["delta"] == pytest.approx(-0.1)
    card = body["cards"][0]
    assert card["card"] == "打击"
    assert card["usage_delta"] == pytest.approx(1.0)
    assert card["usage_method"] == "means_only" and card["usage_significant"] is None
    assert card["efficiency_delta"] == pytest.approx(0.25)


def test_http_compare_and_bad_inputs(client, tmp_path, monkeypatch):
    from gui import paths
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))
    _install_run(str(runs), "base", _fights(40, 4, 8, 16, 7, 8, 1), title="Baseline")
    _install_run(str(runs), "changed", _fights(40, 26, 0, 4, 3, 24, 2), title="Changed")
    _install_run(str(runs), "batch", [], kind="batch", title="Batch")
    _install_run(str(runs), "running", _fights(4, 1, 0, 1, 1, 1, 1), status="running", title="Running")
    _install_run(str(runs), "empty", None, title="Empty")

    ok = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "changed"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["ok"] is True and body["read_only"] is True and body["kind"] == "combat"
    assert body["a"]["id"] == "base" and body["b"]["title"] == "Changed"
    direct = compare_dirs(str(runs / "base" / "out"), str(runs / "changed" / "out"))
    assert body["cells"] == direct["cells"]
    assert body["cards"] == direct["cards"]
    assert "Traceback" not in ok.text

    same = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "base"})
    assert same.status_code == 400
    assert same.json()["detail"] == "Pick two different tests."
    assert "Traceback" not in same.text

    unknown = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": SECRET})
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "One or both tests were not found."
    assert SECRET not in unknown.text and "Traceback" not in unknown.text

    missing = client.get("/api/runs/compare", headers=EN, params={"a": "base"})
    assert missing.status_code == 400
    assert "b" in missing.json()["detail"].lower()
    assert "Traceback" not in missing.text

    repeated = client.get("/api/runs/compare?a=base&a=changed&b=changed", headers=EN)
    assert repeated.status_code == 400
    detail = repeated.json()["detail"]
    assert "a" in detail and "string" in detail
    assert "Traceback" not in repeated.text and "changed" not in detail

    zh = client.get("/api/runs/compare", headers={"x-lang": "zhs"}, params={"a": "missing-a", "b": "missing-b"})
    assert zh.status_code == 400
    assert "找不到" in zh.json()["detail"]
    assert "Traceback" not in zh.text

    kind = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "batch"})
    assert kind.status_code == 400
    assert "different types" in kind.json()["detail"]

    both_batch = _install_run(str(runs), "batch2", [], kind="batch")
    assert both_batch
    batches = client.get("/api/runs/compare", headers=EN, params={"a": "batch", "b": "batch2"})
    assert batches.status_code == 400
    assert "combat" in batches.json()["detail"].lower()

    running = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "running"})
    assert running.status_code == 400
    assert "finished" in running.json()["detail"].lower()

    empty = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "empty"})
    assert empty.status_code == 400
    assert "no combat cells" in empty.json()["detail"].lower()
    assert "Traceback" not in empty.text

    bad = runs / "changed" / "out" / "raw.jsonl"
    bad.write_text("{" + SECRET + "\n", encoding="utf-8")
    broken = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "changed"})
    assert broken.status_code == 400
    assert broken.json()["detail"] == "The combat results are not valid JSON (line 1)."
    assert SECRET not in broken.text and "Traceback" not in broken.text

    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 16)
    huge = runs / "base" / "out" / "raw.jsonl"
    huge.write_bytes(b"{" + SECRET.encode("utf-8"))
    oversized = client.get("/api/runs/compare", headers=EN, params={"a": "base", "b": "changed"})
    assert oversized.status_code == 400
    assert "32" in oversized.json()["detail"]
    assert SECRET not in oversized.text


def test_mcp_compare_runs_matches_dirs_and_rejects_bad_input(tmp_path, monkeypatch):
    import importlib.util
    import sys

    name = "deckbench_mcp_compare_under_test"
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)

    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(root))
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path / "gui-data"))
    a_rows = _fights(40, 5, 2, 12, 6, 10, 1)
    b_rows = _fights(40, 24, 0, 4, 3, 20, 2)
    _write_raw(root / "A", a_rows)
    _write_raw(root / "B", b_rows)
    before = {
        os.path.relpath(dirpath, root): names
        for dirpath, _dirs, names in os.walk(root)
    }
    text = mod.compare_runs(str(root / "A"), str(root / "B"))
    doc = json.loads(text)
    direct = compare_dirs(str(root / "A"), str(root / "B"))
    assert doc["ok"] is True and doc["read_only"] is True
    assert doc["cells"] == direct["cells"] and doc["cards"] == direct["cards"]
    assert doc["cells"][0]["metrics"]["win"]["significant"] is True
    assert doc["cells"][0]["metrics"]["hp_loss"]["method"] == "welch"
    walked = {
        os.path.relpath(dirpath, root): names
        for dirpath, _dirs, names in os.walk(root)
    }
    assert walked == before

    gui = tmp_path / "gui-data"
    _install_run(str(gui / "runs"), "ida", a_rows, title="A")
    _install_run(str(gui / "runs"), "idb", b_rows, title="B")
    by_id = json.loads(mod.compare_runs("ida", "idb"))
    assert by_id["ok"] is True
    assert by_id["cells"][0]["metrics"]["win"]["p_value"] == pytest.approx(
        doc["cells"][0]["metrics"]["win"]["p_value"],
    )

    def load(raw):
        body = json.loads(raw)
        assert body["ok"] is False and body["read_only"] is True
        assert "Traceback" not in raw
        assert SECRET not in raw
        return body

    assert load(mod.compare_runs(1, str(root / "B")))["error"] == "bad_type"
    assert load(mod.compare_runs(str(root / "A"), None))["error"] == "bad_type"
    assert load(mod.compare_runs("ida", "ida"))["error"] == "same_run"
    assert load(mod.compare_runs(str(root / "A"), str(root / "A")))["error"] == "same_run"
    assert load(mod.compare_runs("missing-run", "other-run"))["error"] == "not_found"
    outside = tmp_path / "outside"
    outside.mkdir()
    _write_raw(outside, a_rows)
    (outside / "raw.jsonl").write_text(SECRET, encoding="utf-8")
    assert load(mod.compare_runs(str(outside), str(root / "B")))["error"] == "path_not_allowed"
    running = gui / "runs" / "later"
    _install_run(str(running.parent), "later", a_rows, status="running")
    assert load(mod.compare_runs("later", "idb"))["error"] == "not_done"
    _install_run(str(gui / "runs"), "full", [], kind="batch")
    assert load(mod.compare_runs("full", "idb"))["error"] == "not_combat"
