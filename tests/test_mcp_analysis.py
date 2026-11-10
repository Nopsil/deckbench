"""MCP 只读分析：批量摘要、单卡 A/B、一场战斗的说明日志。不启动游戏，不写结果文件。"""
import asyncio
import importlib.util
import json
import os
import sys

import pytest

from gui import metrics
from sts2sim.analysis import batch_run_summary_json, card_ab_json, explain_fight_json
from sts2sim.stats import ab_win_report, wilson_interval

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_mcp():
    name = "deckbench_mcp_server_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_text(result):
    if isinstance(result, tuple):
        result = result[0]
    return "".join(getattr(block, "text", "") for block in result)


def _runs(n, wins, seed0=0):
    rows = []
    for i in range(n):
        rows.append({
            "seed": f"S{seed0 + i}", "floor": 1 + (i % 5), "act": 0,
            "victory": i < wins, "combats": [[1, "Monster", "X", 0, 4, True, 0]],
            "seconds": 0.1,
        })
    return rows


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _tree_bytes(root):
    out = {}
    for dirpath, dirnames, names in os.walk(root):
        dirnames.sort()
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            if os.path.isfile(path) and not os.path.islink(path):
                with open(path, "rb") as fh:
                    out[os.path.relpath(path, root)] = fh.read()
    return out


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(root))
    return root


def test_batch_summary_matches_gui_and_wilson_and_does_not_write(allowed):
    run_dir = allowed / "run1"
    run_dir.mkdir()
    rows = _runs(100, 30)
    rows.append({"seed": "bad", "error": "x"})
    _write_jsonl(run_dir / "runs.jsonl", rows)
    before = _tree_bytes(allowed)
    text = _load_mcp().batch_run_summary(str(run_dir))
    assert text == batch_run_summary_json(str(run_dir / "runs.jsonl"))
    assert text.endswith("\n")
    doc = json.loads(text)
    assert doc["ok"] is True and doc["read_only"] is True
    assert doc["path"] == os.path.realpath(str(run_dir / "runs.jsonl"))
    summary = doc["summary"]
    expect = metrics.batch_summary(rows)
    assert summary["n_total"] == 101 and summary["n"] == 100 and summary["errors"] == 1
    assert summary["wins"] == 30 and summary["win"] == pytest.approx(expect["win"])
    lo, hi = wilson_interval(30, 100)
    assert summary["win_ci_low"] == pytest.approx(lo) and summary["win_ci_high"] == pytest.approx(hi)
    assert summary["win_ci_low"] == pytest.approx(expect["win_ci_low"])
    assert summary["win_ci_method"] == "wilson"
    assert summary["sample_warning"] is False
    assert summary["sample_warning_text"] is None
    assert "Wilson 95% CI" in summary["win_rate_text"]
    assert _tree_bytes(allowed) == before

    small = json.loads(batch_run_summary_json(str(_write_small(allowed))))
    assert small["summary"]["n"] == 10 and small["summary"]["wins"] == 2
    assert small["summary"]["sample_warning"] is True
    assert small["summary"]["sample_warning_code"] == "n_below_minimum"
    assert "不能下结论" in small["summary"]["win_rate_text"]


def _write_small(allowed):
    path = allowed / "small.jsonl"
    _write_jsonl(path, _runs(10, 2))
    return path


def test_empty_batch_still_reports_sample_warning(allowed):
    path = allowed / "empty.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    before = path.read_bytes()
    doc = json.loads(batch_run_summary_json(str(path)))
    assert doc["summary"]["n_total"] == 0 and doc["summary"]["n"] == 0
    assert doc["summary"]["sample_warning"] is True
    assert doc["summary"]["win_ci_low"] is None
    assert path.read_bytes() == before


def test_card_ab_matches_stats_and_gui_without_simulating(allowed, monkeypatch):
    a_dir = allowed / "A"
    b_dir = allowed / "B"
    a_dir.mkdir()
    b_dir.mkdir()
    rows_a, rows_b = _runs(100, 30), _runs(100, 45)
    _write_jsonl(a_dir / "runs.jsonl", rows_a)
    _write_jsonl(b_dir / "runs.jsonl", rows_b)
    pair = allowed / "pair"
    pair.mkdir()
    _write_jsonl(pair / "card_A.jsonl", rows_a)
    _write_jsonl(pair / "card_B.jsonl", rows_b)
    before = _tree_bytes(allowed)
    loaded = set(sys.modules)

    text = _load_mcp().card_ab(str(a_dir), str(b_dir))
    doc = json.loads(text)
    paired = json.loads(card_ab_json(str(pair)))
    report = ab_win_report(30, 100, 45, 100)
    assert doc["ok"] is True and doc["read_only"] is True
    assert doc["p_value"] == pytest.approx(report["p_value"])
    assert paired["p_value"] == pytest.approx(doc["p_value"])
    assert doc["p_value"] == pytest.approx(0.028459736916, abs=1e-12)
    assert doc["sample_warning"] is False and paired["sample_warning"] is False
    assert doc["win_ab"]["p_value"] == pytest.approx(doc["p_value"])
    assert doc["win_ab"]["test"] == "two_proportion_z"
    assert paired["a"].endswith("card_A.jsonl") and paired["b"].endswith("card_B.jsonl")
    gui = metrics.batch_ab(rows_a, rows_b)
    win = next(r for r in doc["result"]["rows"] if r["key"] == "win")
    gui_win = next(r for r in gui["rows"] if r["key"] == "win")
    assert win["p_value"] == pytest.approx(gui_win["p_value"])
    assert win["diff"] == pytest.approx(gui_win["diff"])
    assert "ci95" in win and win["paired"] is True
    assert "p=0.0285" in doc["result"]["win_ab_text"]
    assert not any(name == "batch" or name.endswith(".batch") for name in set(sys.modules) - loaded)

    direct = json.loads(_load_mcp().card_ab(str(a_dir / "runs.jsonl"), str(b_dir / "runs.jsonl")))
    assert direct["p_value"] == pytest.approx(doc["p_value"])
    assert direct["a"].endswith(os.path.join("A", "runs.jsonl"))
    assert _tree_bytes(allowed) == before

    small_a = allowed / "small_a.jsonl"
    small_b = allowed / "small_b.jsonl"
    _write_jsonl(small_a, _runs(10, 2))
    _write_jsonl(small_b, _runs(10, 8))
    small = json.loads(card_ab_json(str(small_a), str(small_b)))
    assert small["p_value"] is not None and small["sample_warning"] is True
    assert "不能下结论" in small["result"]["win_ab_text"]
    assert small["win_ab"]["sample_warning_code"] == "n_below_minimum"


def test_explain_fight_pages_top_candidates_for_one_fight(allowed):
    rows = []
    for i, score in enumerate((3.0, 1.0, 8.0)):
        cands = [{"id": f"C{n}", "score": n} for n in range(8)]
        cands.append({"id": "PICK", "score": score})
        rows.append({
            "v": 1, "seq": i + 1, "kind": "play", "seed": "S", "fight": 1, "floor": 2, "turn": i + 1,
            "chosen": {"id": "PICK", "score": score}, "candidates": cands,
        })
    rows.append({
        "v": 1, "seq": 4, "kind": "reward", "seed": "S", "floor": 2,
        "chosen": {"id": "skip", "score": 4},
        "candidates": [{"id": "STRIKE", "score": 3}, {"id": "skip", "score": 4}],
    })
    rows.append({
        "v": 1, "seq": 5, "kind": "play", "seed": "S", "fight": 2, "floor": 3, "turn": 1,
        "chosen": {"id": "DEFEND", "score": 1},
        "candidates": [{"id": "DEFEND", "score": 1}, {"id": "OTHER", "score": 2}],
    })
    rows.append({
        "v": 1, "seq": 6, "kind": "play", "seed": "OTHER", "fight": 1, "floor": 2, "turn": 1,
        "chosen": {"id": "NO", "score": 1}, "candidates": [{"id": "NO", "score": 1}],
    })
    log = allowed / "runs.explain.jsonl"
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    log.write_text("\ufeff" + text, encoding="utf-8")
    before = log.read_bytes()

    doc = json.loads(_load_mcp().explain_fight(str(allowed), fight=0, seed="S", offset=1, limit=1))
    assert doc == json.loads(explain_fight_json(str(log), 0, "S", 1, 1))
    assert doc["ok"] is True and doc["read_only"] is True
    assert doc["fight"] == 0 and doc["fight_count"] == 2
    assert doc["total"] == 4 and doc["offset"] == 1 and doc["limit"] == 1
    assert doc["next_offset"] == 2
    assert doc["where"]["floor"] == 2 and doc["where"]["seed"] == "S"
    assert [d["seq"] for d in doc["decisions"]] == [2]
    cands = doc["decisions"][0]["candidates"]
    assert [c["score"] for c in cands[:5]] == [7, 6, 5, 4, 3]
    assert cands[-1]["id"] == "PICK" and cands[-1]["picked"] is True
    assert len(cands) == 6
    assert doc["decisions"][0]["turn"] == 2

    reward = json.loads(explain_fight_json(str(log), fight=0, seed="S", offset=3, limit=20))
    assert [d["kind"] for d in reward["decisions"]] == ["reward"]
    assert reward["next_offset"] is None
    assert reward["decisions"][0]["candidates"][0]["id"] == "skip"

    second = json.loads(explain_fight_json(str(log), fight=1, seed="S"))
    assert second["total"] == 1 and second["decisions"][0]["floor"] == 3
    assert "PICK" not in json.dumps(second["decisions"])

    wide = json.loads(explain_fight_json(str(log), fight=0, seed="S", limit=1000))
    assert wide["limit"] == 100 and wide["total"] == 4 and len(wide["decisions"]) == 4
    assert log.read_bytes() == before


def test_paths_outside_allowed_dirs_and_save_trees_are_refused(allowed, tmp_path):
    mcp = _load_mcp()
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"secret":"do-not-read","floor":1,"victory":true,"combats":[[1,"Monster","X",0,4]]}\n', encoding="utf-8")
    outside_bytes = outside.read_bytes()
    sentinel = "SENTINEL-save-bytes"
    save_dir = allowed / "history"
    save_dir.mkdir()
    save_file = save_dir / "x.jsonl"
    save_file.write_text(sentinel, encoding="utf-8")
    run_file = allowed / "sample.run"
    run_file.write_bytes(b"\x00" + sentinel.encode("utf-8"))
    link = allowed / "escape.jsonl"
    link.symlink_to(outside)
    repo_file = os.path.join(ROOT, "sts2sim", "analysis.py")
    before = _tree_bytes(allowed)

    denied = json.loads(mcp.batch_run_summary(str(outside)))
    assert denied["ok"] is False and denied["read_only"] is True and denied["error"] == "path_not_allowed"
    assert "do-not-read" not in json.dumps(denied)
    assert outside.read_bytes() == outside_bytes

    escaped = json.loads(mcp.explain_fight(str(link)))
    assert escaped["error"] == "path_not_allowed"
    assert "do-not-read" not in json.dumps(escaped)
    assert "def batch_run_summary" not in json.dumps(escaped)

    climbed = json.loads(mcp.card_ab(str(allowed / ".." / outside.name)))
    assert climbed["error"] == "path_not_allowed"

    repo = json.loads(mcp.batch_run_summary(repo_file))
    assert repo["error"] == "path_not_allowed"
    assert "refuse_save_write" not in json.dumps(repo)

    refused = json.loads(mcp.batch_run_summary(str(save_file)))
    assert refused["error"] == "refuse_write" and refused["read_only"] is True
    assert sentinel not in json.dumps(refused)
    run_refused = json.loads(mcp.explain_fight(str(run_file)))
    assert run_refused["error"] == "refuse_write"
    assert sentinel not in json.dumps(run_refused)

    missing = allowed / "nope.jsonl"
    assert json.loads(mcp.batch_run_summary(str(missing)))["error"] == "not_found"
    assert not missing.exists()
    assert json.loads(mcp.batch_run_summary(str(tmp_path / "missing-outside.jsonl")))["error"] == "path_not_allowed"
    assert json.loads(mcp.batch_run_summary("  "))["error"] == "need_path"
    assert _tree_bytes(allowed) == before
    assert outside.read_bytes() == outside_bytes


def test_bad_inputs_stay_json_and_do_not_write(allowed):
    mcp = _load_mcp()
    bad = allowed / "bad.jsonl"
    bad.write_text('{"floor": 1}\n', encoding="utf-8")
    explain = allowed / "explain.jsonl"
    explain.write_text('{"kind":"play","seed":"S","floor":1,"chosen":{"id":"A","score":1},"candidates":[]}\n', encoding="utf-8")
    junk = allowed / "junk.jsonl"
    junk.write_text("{not-json}\n", encoding="utf-8")
    pair = allowed / "many"
    pair.mkdir()
    (pair / "one_A.jsonl").write_text("{}\n", encoding="utf-8")
    (pair / "two_A.jsonl").write_text("{}\n", encoding="utf-8")
    (pair / "one_B.jsonl").write_text("{}\n", encoding="utf-8")
    (allowed / "also.explain.jsonl").write_text("{}\n", encoding="utf-8")
    before = _tree_bytes(allowed)

    assert json.loads(mcp.batch_run_summary(str(explain)))["error"] == "not_batch"
    assert json.loads(mcp.explain_fight(str(bad)))["error"] == "not_explain"
    broken = json.loads(mcp.explain_fight(str(junk)))
    assert broken["error"] == "not_json" and broken["line"] == 1
    assert json.loads(mcp.card_ab(str(bad)))["error"] == "need_b"
    assert json.loads(mcp.explain_fight(str(explain), fight=3))["error"] == "fight_out_of_range"
    assert json.loads(mcp.explain_fight(str(explain), fight=-1))["error"] == "bad_fight"
    assert json.loads(mcp.explain_fight(str(explain), fight=True))["error"] == "bad_fight"
    assert json.loads(mcp.explain_fight(str(explain), offset=-1))["error"] == "bad_offset"
    assert json.loads(mcp.explain_fight(str(explain), limit=0))["error"] == "bad_limit"

    amb = json.loads(mcp.card_ab(str(pair)))
    assert amb["error"] == "ambiguous_pair" and amb["n_a"] == 2 and amb["n_b"] == 1
    assert json.loads(mcp.explain_fight(str(allowed)))["error"] == "ambiguous_explain"
    assert _tree_bytes(allowed) == before


def test_gui_data_dir_is_allowed_without_an_extra_root(tmp_path, monkeypatch):
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    monkeypatch.delenv("DECKBENCH_ANALYSIS_ROOTS", raising=False)
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    _write_jsonl(run / "runs.jsonl", _runs(30, 30))
    before = _tree_bytes(tmp_path)
    doc = json.loads(batch_run_summary_json(str(run)))
    assert doc["ok"] is True and doc["summary"]["wins"] == 30
    assert doc["summary"]["sample_warning"] is False
    assert doc["summary"]["win_ci_method"] == "wilson"
    assert _tree_bytes(tmp_path) == before


def test_server_registers_analysis_tools_on_play_and_import_only():
    pytest.importorskip("mcp")
    mcp = _load_mcp()
    play = mcp.build()
    names = [t.name for t in play._tool_manager.list_tools()]
    assert names[-6:] == ["batch_run_summary", "card_ab", "compare_runs", "explain_fight", "calibrate", "gap_triage"]
    tools = {t.name: t for t in play._tool_manager.list_tools()}
    assert tools["batch_run_summary"].parameters["required"] == ["path"]
    assert "sample_warning" in tools["batch_run_summary"].description
    assert "Wilson" in tools["batch_run_summary"].description
    ab = tools["card_ab"].parameters
    assert ab["required"] == ["a"]
    assert "b" in ab["properties"] and "p_value" in tools["card_ab"].description
    cmp_tool = tools["compare_runs"].parameters
    assert cmp_tool["required"] == ["a", "b"]
    assert "Welch" in tools["compare_runs"].description
    assert "Wilson" in tools["compare_runs"].description
    ex = tools["explain_fight"].parameters
    assert ex["required"] == ["path"]
    assert set(ex["properties"]) >= {"path", "fight", "seed", "offset", "limit"}
    assert "offset" in tools["explain_fight"].description
    assert "p10" in tools["calibrate"].description and "unmatched" in tools["calibrate"].description
    assert "likely_sim_gap" in tools["calibrate"].description
    assert tools["calibrate"].parameters["required"] == ["real", "sim"]
    gap = tools["gap_triage"].parameters
    assert "reports" in gap["properties"] and "paths" in gap["properties"]
    assert "optimistic" in tools["gap_triage"].description
    assert "p95" in tools["gap_triage"].description and "likely_sim_gap" in tools["gap_triage"].description
    assert "new_run" in names and "seed_preview" in names

    only = mcp.build_import()
    only_names = [t.name for t in only._tool_manager.list_tools()]
    assert only_names == [
        "import_save", "import_history_batch", "batch_run_summary", "card_ab", "compare_runs",
        "explain_fight", "calibrate", "gap_triage",
    ]
    assert "seed_preview" not in only_names and "new_run" not in only_names
