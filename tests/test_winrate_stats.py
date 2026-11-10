"""胜率 Wilson 区间、两比例 z 检验、样本不足警告。已知数值不靠把公式再写一遍。

Wilson 95%（z=1.96）对照 Newcombe 1998, Statistics in Medicine 17:857–872，表 I 方法 3
（score，无连续性修正），四位小数：
  81/263 → 0.2553, 0.3662
  15/148 → 0.0624, 0.1605
   0/20 → 0.0000, 0.1611
   1/29 → 0.0061, 0.1718

两比例：30/100 对 45/100，合并比例 0.375，
  se = sqrt(0.375*0.625*(1/100+1/100)) = 0.068465319688
  z = 0.15 / se = 2.190890230021
  双侧 p = erfc(|z|/sqrt(2)) = 0.028459736916
"""
import json
import os
import re
import sys

import pytest

from gui.metrics import batch_ab, batch_summary, combat_ab
from sts2sim.stats import (
    MIN_N,
    ab_win_report,
    format_ab,
    format_win_rate,
    two_proportion_ztest,
    wilson_interval,
    win_rate_report,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ab_table  # noqa: E402
import ai_summary  # noqa: E402


NEWCOMBE = (
    (81, 263, 0.2553, 0.3662),
    (15, 148, 0.0624, 0.1605),
    (0, 20, 0.0000, 0.1611),
    (1, 29, 0.0061, 0.1718),
)


def test_wilson_matches_newcombe_1998_table_i():
    for wins, n, lo, hi in NEWCOMBE:
        got_lo, got_hi = wilson_interval(wins, n)
        assert round(got_lo, 4) == lo
        assert round(got_hi, 4) == hi
        assert 0.0 <= got_lo <= got_hi <= 1.0


def test_two_proportion_30_of_100_vs_45_of_100():
    got = two_proportion_ztest(30, 100, 45, 100)
    assert got["method"] == "two_proportion_z"
    assert got["diff"] == pytest.approx(0.15)
    assert got["se"] == pytest.approx(0.068465319688, abs=1e-12)
    assert got["z"] == pytest.approx(2.190890230021, abs=1e-12)
    assert got["p_value"] == pytest.approx(0.028459736916, abs=1e-12)


def test_two_proportion_edges_and_minimum_sample():
    same = two_proportion_ztest(0, 50, 0, 50)
    assert same["z"] == 0.0 and same["p_value"] == 1.0
    # 0% 对 100% 时合并比例不是 0 或 1，z 有限；标准误为 0 只出现在两组都全胜或都全负。
    apart = two_proportion_ztest(0, 50, 50, 50)
    assert apart["diff"] == pytest.approx(1.0)
    assert apart["z"] == pytest.approx(10.0)
    assert apart["p_value"] < 1e-15
    empty = two_proportion_ztest(0, 0, 1, 10)
    assert empty["p_value"] is None and empty["z"] is None

    small = win_rate_report(2, 10)
    assert small["sample_warning"] is True
    assert small["sample_warning_code"] == "n_below_minimum"
    assert small["min_n"] == MIN_N == 30
    assert "n=10 < 30" in small["sample_warning_text"]
    assert round(small["win_ci_low"], 4) == 0.0567
    assert round(small["win_ci_high"], 4) == 0.5098

    enough = win_rate_report(30, 100)
    assert enough["sample_warning"] is False
    assert enough["sample_warning_text"] is None
    assert enough["win_ci_low"] == pytest.approx(0.21894753866228117, abs=1e-12)
    assert enough["win_ci_high"] == pytest.approx(0.39585038432811953, abs=1e-12)
    boundary = win_rate_report(0, 30)
    assert boundary["sample_warning"] is False
    assert win_rate_report(0, 29)["sample_warning"] is True


def test_text_markdown_and_json_include_interval_pvalue_and_warning():
    one = win_rate_report(2, 10)
    text = format_win_rate(one, "text")
    md = format_win_rate(one, "markdown")
    parsed = json.loads(format_win_rate(one, "json"))
    assert "Wilson 95% CI 5.7%–51.0%" in text
    assert "样本不足，不能下结论" in text and "sample too small to conclude" in text
    assert "Wilson 95%" in md and "不足，不能下结论" in md and "5.7%" in md
    assert parsed["win_ci_method"] == "wilson"
    assert parsed["sample_warning"] is True
    assert parsed["win_ci_low"] == pytest.approx(one["win_ci_low"])

    ab = ab_win_report(2, 10, 8, 10)
    ab_text = format_ab(ab, "text")
    ab_md = format_ab(ab, "markdown")
    ab_json = json.loads(format_ab(ab, "json"))
    assert "Wilson 95% CI" in ab_text and "two-proportion z-test" in ab_text
    assert "p=" in ab_text and "n=10 and n=10 < 30" in ab_text
    assert "两比例 z 检验" in ab_md and "不足" in ab_md
    assert ab_json["test"] == "two_proportion_z"
    assert ab_json["diff"] == pytest.approx(0.6)
    assert ab_json["p_value"] == pytest.approx(ab["p_value"])
    assert ab_json["a"]["win_ci_low"] == pytest.approx(ab["a"]["win_ci_low"])
    assert "diff" in ab_json and "z" in ab_json

    large = format_ab(ab_win_report(30, 100, 45, 100), "text")
    assert "p=0.0285" in large
    assert "不能下结论" not in large


def _runs(n, wins, seed0=0):
    rows = []
    for i in range(n):
        rows.append({
            "seed": f"S{seed0 + i}", "floor": 1 + (i % 5), "act": 0,
            "victory": i < wins, "combats": [[1, "Monster", "X", 0, 4, True, 0]],
            "seconds": 0.1,
        })
    return rows


def test_batch_summary_keeps_old_fields_and_adds_wilson():
    rows = _runs(100, 30)
    rows.append({"seed": "bad", "error": "x", "victory": False, "floor": 0, "act": 0, "combats": []})
    summary = batch_summary(rows)
    assert summary["n_total"] == 101
    assert summary["n"] == 100
    assert summary["errors"] == 1
    assert summary["wins"] == 30
    assert summary["win"] == pytest.approx(0.3)
    assert summary["avg_floor"] == pytest.approx(sum(1 + (i % 5) for i in range(100)) / 100)
    assert "median_floor" in summary and "survival" in summary and "death_by_encounter" in summary
    assert summary["win_ci_method"] == "wilson"
    assert summary["win_ci_low"] == pytest.approx(0.21894753866228117, abs=1e-12)
    assert summary["win_ci_high"] == pytest.approx(0.39585038432811953, abs=1e-12)
    assert summary["sample_warning"] is False
    assert "Wilson 95% CI 21.9%–39.6%" in summary["win_rate_text"]
    assert "Wilson 95%" in summary["win_rate_markdown"]

    small = batch_summary(_runs(10, 2))
    assert small["wins"] == 2 and small["n"] == 10
    assert small["sample_warning"] is True
    assert small["sample_warning_code"] == "n_below_minimum"
    assert "不能下结论" in small["win_rate_text"]
    assert batch_summary([{"error": "x"}]) == {"n_total": 1, "n": 0, "errors": 1}


def test_batch_ab_adds_pvalue_without_dropping_paired_fields():
    a = _runs(100, 30)
    b = _runs(100, 45)
    result = batch_ab(a, b)
    assert set(result) >= {"a", "b", "rows", "win_ab_text", "win_ab_markdown"}
    win = next(r for r in result["rows"] if r["key"] == "win")
    for key in ("a", "b", "diff", "ci95", "n", "paired", "differ", "significant", "pct"):
        assert key in win
    assert win["a"] == pytest.approx(0.3)
    assert win["b"] == pytest.approx(0.45)
    assert isinstance(win["significant"], bool)
    assert win["test"] == "two_proportion_z"
    assert win["p_value"] == pytest.approx(0.028459736916, abs=1e-12)
    assert win["z"] == pytest.approx(2.190890230021, abs=1e-12)
    assert win["ci_method"] == "wilson"
    assert win["a_ci_low"] == pytest.approx(0.218947538662, abs=1e-9)
    assert win["sample_warning"] is False
    assert "p=0.0285" in result["win_ab_text"]
    assert "two-proportion z-test" in result["win_ab_markdown"]
    floor = next(r for r in result["rows"] if r["key"] == "floor")
    assert "p_value" not in floor
    assert floor["sample_warning"] is False
    assert "diff" in floor and "significant" in floor

    tiny = batch_ab(_runs(10, 2), _runs(10, 8))
    tiny_win = next(r for r in tiny["rows"] if r["key"] == "win")
    assert tiny_win["p_value"] is not None
    assert tiny_win["sample_warning"] is True
    assert "不能下结论" in tiny["win_ab_text"]


def test_combat_ab_keeps_interval_and_adds_pooled_pvalue():
    cell = lambda win, n: {
        "deck_id": "d", "deck": "甲", "act": 1, "room": "普通", "win": win, "n": n,
        "turns": 3.0, "hp_loss": 10.0,
    }
    row = combat_ab({"cells": [cell(30.0, 100)]}, {"cells": [cell(45.0, 100)]})["rows"][0]
    for key in ("deck", "act", "room", "a", "b", "diff", "ci95", "significant", "na", "nb",
                "a_turns", "b_turns", "a_loss", "b_loss"):
        assert key in row
    assert row["significant"] is True
    assert row["p_value"] == pytest.approx(0.028459736916, abs=1e-9)
    assert row["test"] == "two_proportion_z"
    small = combat_ab({"cells": [cell(30.0, 10)]}, {"cells": [cell(45.0, 10)]})["rows"][0]
    assert small["sample_warning"] is True
    assert small["ci95"] > 0


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_ab_table_and_ai_summary_surface_the_same_numbers(tmp_path, capsys, monkeypatch):
    base = tmp_path / "base.jsonl"
    var = tmp_path / "card.jsonl"
    _write_jsonl(base, _runs(100, 30))
    _write_jsonl(var, _runs(100, 45))

    monkeypatch.setattr(sys, "argv", ["ab_table.py", str(tmp_path), "--format", "markdown"])
    ab_table.main()
    md = capsys.readouterr().out
    assert "胜率 (Wilson 95%)" in md
    assert "21.9%–39.6%" in md and "35.6%–54.8%" in md
    assert "0.0285" in md and "够" in md and "不足" not in md

    monkeypatch.setattr(sys, "argv", ["ab_table.py", str(tmp_path), "--format", "text"])
    ab_table.main()
    text = capsys.readouterr().out
    assert "Wilson 95% CI" in text and "胜率差 p=0.0285" in text

    monkeypatch.setattr(sys, "argv", ["ab_table.py", str(tmp_path), "--format", "json"])
    ab_table.main()
    payload = json.loads(capsys.readouterr().out)
    card = next(x for x in payload if x["name"] == "card")
    assert card["win"] == pytest.approx(0.45)
    assert card["wins"] == 45
    assert card["p_value"] == pytest.approx(0.028459736916, abs=1e-12)
    assert card["test"] == "two_proportion_z"
    assert card["d"] is not None and "floor" in card and "boss1" in card
    base_row = next(x for x in payload if x["baseline"])
    assert "p_value" not in base_row
    assert base_row["win_ci_method"] == "wilson"

    small_dir = tmp_path / "small"
    small_dir.mkdir()
    _write_jsonl(small_dir / "base.jsonl", _runs(10, 2))
    _write_jsonl(small_dir / "card.jsonl", _runs(10, 8))
    monkeypatch.setattr(sys, "argv", ["ab_table.py", str(small_dir), "--format", "text"])
    ab_table.main()
    warned = capsys.readouterr().out
    assert "不能下结论" in warned and "n=10 and n=10 < 30" in warned

    left = tmp_path / "a.jsonl"
    right = tmp_path / "b.jsonl"
    _write_jsonl(left, _runs(100, 30))
    _write_jsonl(right, _runs(100, 45))
    monkeypatch.setattr(sys, "argv", ["ai_summary.py", str(left), str(right), "--deaths", "0"])
    ai_summary.main()
    summary_md = capsys.readouterr().out
    assert "Wilson 95% CI" in summary_md
    assert "two-proportion z-test" in summary_md and "p=0.0285" in summary_md

    monkeypatch.setattr(sys, "argv", ["ai_summary.py", str(left), str(right), "--json", "--deaths", "0"])
    ai_summary.main()
    dumped = json.loads(capsys.readouterr().out)
    assert dumped[0]["ci"][0] == pytest.approx(dumped[0]["win_ci_low"])
    assert dumped[0]["wins"] == 30 and dumped[0]["win"] == pytest.approx(0.3)
    assert dumped[1]["p_value_vs_first"] == pytest.approx(0.028459736916, abs=1e-12)
    assert dumped[1]["test_vs_first"] == "two_proportion_z"
    assert dumped[0]["sample_warning"] is False
    assert "deaths" in dumped[0] and "floor" in dumped[0]

    tiny = tmp_path / "tiny.jsonl"
    _write_jsonl(tiny, _runs(10, 2))
    monkeypatch.setattr(sys, "argv", ["ai_summary.py", str(tiny), "--deaths", "1"])
    ai_summary.main()
    tiny_out = capsys.readouterr().out
    assert "不足，不能下结论" in tiny_out
    assert "n=10 < 30" in tiny_out


def test_gui_views_show_wilson_pvalue_and_sample_warning():
    """报告页和 A/B 页要把接口里的区间、p 值、样本警告画出来，四种语言都有对应的键。"""
    report = open(os.path.join(ROOT, "gui", "web", "src", "pages", "Report.vue"), encoding="utf-8").read()
    ab = open(os.path.join(ROOT, "gui", "web", "src", "pages", "AB.vue"), encoding="utf-8").read()
    for name in ("win_ci_low", "win_ci_high", "sample_warning", "rep.wilson", "rep.sampleSmall"):
        assert name in report
    for name in ("win_ci_low", "win_ci_high", "p_value", "sample_warning", "_ci_low", "_ci_high",
                 "ab.sideWin", "ab.wilson", "ab.pValue", "ab.sampleSmall", "ab.sampleSmallAny"):
        assert name in ab
    keys = (
        "rep.wilson", "rep.sampleSmall", "ab.sideWin", "ab.wilson", "ab.pValue", "ab.pValueLabel",
        "ab.sampleSmall", "ab.sampleSmallAny", "ab.tooSmallTag",
    )
    placeholders = {
        "rep.wilson": {"lo", "hi"},
        "rep.sampleSmall": {"n", "min"},
        "ab.sideWin": {"win", "lo", "hi"},
        "ab.wilson": {"lo", "hi"},
        "ab.pValue": {"p"},
        "ab.pValueLabel": set(),
        "ab.sampleSmall": {"na", "nb", "min"},
        "ab.sampleSmallAny": {"min"},
        "ab.tooSmallTag": set(),
    }
    for lang in ("zhs", "en", "ja", "ko"):
        table = json.load(open(os.path.join(ROOT, "gui", "locales", f"{lang}.json"), encoding="utf-8"))
        for key in keys:
            assert key in table and table[key].strip()
            assert set(re.findall(r"\{(\w+)\}", table[key])) == placeholders[key]
