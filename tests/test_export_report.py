"""离线 HTML 报告：一次已完成的测试、可选的战斗对比、可选的校准 / 缺口分诊。

不新开模拟。HTML 自包含：内联 CSS、内联 SVG，没有 http(s):// 资源加载。
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = {"x-lang": "en"}
ZHS = {"x-lang": "zhs"}
SECRET = "SECRET-DO-NOT-LEAK"
GAP = os.path.join(ROOT, "tests", "fixtures", "gap_triage", "a_one.json")


def _no_trace(text):
    assert "Traceback" not in text
    assert "traceback" not in text.lower()
    assert SECRET not in text


def _detail(res):
    body = res.json()
    assert isinstance(body.get("detail"), str)
    _no_trace(res.text)
    return body["detail"]


def _flat(res):
    return "".join(res.headers["content-type"].split()).lower()


def assert_offline(html):
    """没有会去加载的网络地址，也没有外链脚本或样式。"""
    import re
    low = html.lower()
    assert "http://" not in low
    assert "https://" not in low
    assert "<script" not in low
    assert "<iframe" not in low
    assert "<link" not in low
    assert not re.search(r"""(?i)\b(?:src|href|poster|action)\s*=\s*['"]?\s*https?:""", html)
    assert not re.search(r"""(?i)url\(\s*['"]?\s*https?:""", html)
    assert not re.search(r"""(?i)@import\s+['"]\s*https?:""", html)
    assert "<svg" in low and "</svg>" in low
    assert "charset=utf-8" in low or 'charset="utf-8"' in low


def _batch(root, rid="batch-1", status="done"):
    run = os.path.join(root, rid)
    os.makedirs(run, exist_ok=True)
    meta = {
        "id": rid, "kind": "batch", "title": "Ironclad sample", "status": status,
        "created": "2026-01-02T00:00:00+00:00",
        "params": {"char": "Ironclad", "asc": 0, "n": 2, "agent": "heuristic", "seed": "SEED1"},
        "argv": [SECRET],
    }
    with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    rows = [
        {"floor": 3, "act": 0, "victory": True, "seconds": 2, "picked": ["STRIKE"],
         "combats": [[1, "Monster", "X", 0, 4, True, 0]]},
        {"floor": 1, "act": 0, "victory": False, "seconds": 1, "picked": ["DEFEND"],
         "death_room": [1, "Monster", "SAMPLE", 0],
         "combats": [[1, "Monster", "X", 0, 9, False, 0]]},
    ]
    with open(os.path.join(run, "runs.jsonl"), "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row) + "\n" for row in rows)
    return run


def _combat(root, rid, rows, title, status="done"):
    run = os.path.join(root, rid)
    out = os.path.join(run, "out")
    os.makedirs(out, exist_ok=True)
    meta = {
        "id": rid, "kind": "combat", "title": title, "status": status,
        "created": "2026-01-02T00:00:00+00:00",
        "params": {"preset": "probe", "fights": len(rows), "agent": "heuristic", "seed": 1},
    }
    with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    with open(os.path.join(out, "raw.jsonl"), "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row) + "\n" for row in rows)
    with open(os.path.join(out, "cells.csv"), "w", encoding="utf-8") as handle:
        handle.write("卡组id,卡组,阶段,幕,房间,场数,胜率%,战败%,超时%,平均回合,平均掉血,每回合输出,循环报警场数\n")
        handle.write("probe,Probe,,1,Monster,40,75.0,20.0,5.0,4.0,8.0,12.0,0\n")
    return run


def _fights(wins, timeouts, hp, turns, dmg, plays, room):
    rows = []
    for i in range(40):
        if i < timeouts:
            result = "timeout"
        elif i < timeouts + wins:
            result = "win"
        else:
            result = "loss"
        rows.append({
            "deck": "probe", "act": 1, "room": room, "result": result,
            "turns": turns + (i % 3), "hp_lost": hp + (i % 4), "dmg_total": dmg,
            "cards": {"STRIKE": [plays, dmg, 0, plays]},
        })
    return rows


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def runs(tmp_path, monkeypatch):
    from gui import paths
    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(paths, "RUNS_DIR", str(root))
    (tmp_path / "data").mkdir()
    return root


def _load_mcp():
    import importlib.util
    name = "deckbench_mcp_export_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_run_export_is_self_contained_html(client, runs):
    _batch(str(runs))
    en = client.get("/api/runs/batch-1/export.html", headers=EN)
    assert en.status_code == 200, en.text[:400]
    assert _flat(en) == "text/html;charset=utf-8"
    disposition = en.headers["content-disposition"]
    assert "attachment;" in disposition.lower()
    assert "deckbench-run-batch-1.html" in disposition
    assert "filename*=" in disposition.lower()
    html = en.content.decode("utf-8")
    assert_offline(html)
    assert "Finished run" in html
    assert "Win rate" in html
    assert "Ironclad sample" in html
    assert SECRET not in html
    assert 'lang="en"' in html

    zh = client.get("/api/runs/batch-1/export.html", headers=ZHS)
    assert zh.status_code == 200
    text = zh.content.decode("utf-8")
    assert_offline(text)
    assert "已完成的测试" in text
    assert "胜率" in text
    assert 'lang="zh-CN"' in text

    ja = client.get("/api/runs/batch-1/export.html", params={"lang": "ja"})
    assert "完了したテスト" in ja.content.decode("utf-8")
    ko = client.get("/api/runs/batch-1/export.html", params={"lang": "ko-KR"})
    assert "끝난 테스트" in ko.content.decode("utf-8")
    zh_cn = client.get("/api/runs/batch-1/export.html", params={"lang": "zh-CN"})
    assert "已完成的测试" in zh_cn.content.decode("utf-8")


def test_compare_export_and_calibration_share_one_file(client, runs, tmp_path):
    _combat(str(runs), "base", _fights(8, 4, 12, 6, 10, 1, "Monster"), "Baseline")
    _combat(str(runs), "changed", _fights(30, 1, 4, 3, 20, 4, "Monster"), "Changed")
    cal = tmp_path / "data" / "calibration.json"
    with open(GAP, "rb") as handle:
        cal.write_bytes(handle.read())

    compared = client.get("/api/runs/compare/export.html", headers=EN, params={"a": "base", "b": "changed"})
    assert compared.status_code == 200, compared.text[:400]
    assert _flat(compared) == "text/html;charset=utf-8"
    assert "deckbench-compare-base-changed.html" in compared.headers["content-disposition"]
    html = compared.content.decode("utf-8")
    assert_offline(html)
    assert "Run comparison" in html
    assert "Baseline" in html and "Changed" in html
    assert "STRIKE" in html
    assert "<svg" in html

    both = client.get(
        "/api/runs/base/export.html",
        headers=EN,
        params={"calibration": str(cal), "lang": "en"},
    )
    assert both.status_code == 200, both.text[:500]
    text = both.content.decode("utf-8")
    assert_offline(text)
    assert "Finished run" in text
    assert "Calibration" in text
    assert "Gap triage" in text
    assert "SAMPLE_ELITE" in text
    assert "sts2sim/" in text


def test_export_rejects_bad_input_without_a_stack(client, runs, tmp_path, monkeypatch):
    _batch(str(runs), status="running")
    _combat(str(runs), "base", _fights(8, 4, 12, 6, 10, 1, "Monster"), "Baseline")
    _combat(str(runs), "changed", _fights(30, 1, 4, 3, 20, 4, "Monster"), "Changed")
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "calibration.json"
    secret.write_text(json.dumps({"secret": SECRET, "ok": True}), encoding="utf-8")
    allowed = tmp_path / "data"
    bad = allowed / "bad.json"
    bad.write_text("{", encoding="utf-8")
    other = allowed / "other.json"
    other.write_text(json.dumps({"secret": SECRET, "ok": True}), encoding="utf-8")
    link = allowed / "escape.json"
    link.symlink_to(secret)

    missing = client.get("/api/runs/missing/export.html", headers=EN)
    assert missing.status_code == 404
    _no_trace(missing.text)

    climbed = client.get("/api/runs/../export.html", headers=EN)
    assert climbed.status_code == 404
    _no_trace(climbed.text)

    running = client.get("/api/runs/batch-1/export.html", headers=EN)
    assert running.status_code == 409
    assert "finished" in _detail(running).lower()

    lang = client.get("/api/runs/base/export.html", headers=EN, params=[("lang", "en"), ("lang", "zhs")])
    assert lang.status_code == 400
    assert "lang" in _detail(lang)
    assert "zhs" not in lang.text or "must be" in _detail(lang)

    nope = client.get("/api/runs/base/export.html", headers=EN, params={"lang": "nope"})
    assert nope.status_code == 400
    detail = _detail(nope)
    assert "zh-CN" in detail
    assert "nope" not in nope.text

    direct = client.get("/api/runs/base/export.html", headers=EN, params={"calibration": str(secret)})
    assert direct.status_code == 400
    assert "outside the allowed folders" in _detail(direct)

    escaped = client.get("/api/runs/base/export.html", headers=EN, params={"calibration": str(link)})
    assert escaped.status_code == 400
    assert "outside the allowed folders" in _detail(escaped)

    broken = client.get("/api/runs/base/export.html", headers=EN, params={"calibration": str(bad)})
    assert broken.status_code == 400
    assert "JSON" in _detail(broken)

    shape = client.get("/api/runs/base/export.html", headers=EN, params={"calibration": str(other)})
    assert shape.status_code == 400
    assert "calibration" in _detail(shape).lower()

    repeated = client.get("/api/runs/base/export.html", headers=EN, params=[("calibration", "a"), ("calibration", "b")])
    assert repeated.status_code == 400
    assert "calibration" in _detail(repeated)

    same = client.get("/api/runs/compare/export.html", headers=EN, params={"a": "base", "b": "base"})
    assert same.status_code == 400
    _no_trace(same.text)

    dup = client.get("/api/runs/compare/export.html", headers=EN, params=[("a", "base"), ("a", "changed"), ("b", "changed")])
    assert dup.status_code == 400
    assert "a" in _detail(dup)

    absent = client.get("/api/runs/compare/export.html", headers=EN, params={"b": "changed"})
    assert absent.status_code == 400
    assert "a" in _detail(absent).lower() or "Missing" in _detail(absent)

    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32)
    huge = allowed / "huge.json"
    huge.write_text("{" + ("x" * 40) + "}", encoding="utf-8")
    capped = client.get("/api/runs/base/export.html", headers=EN, params={"calibration": str(huge)})
    assert capped.status_code == 400
    assert "32" in _detail(capped) or "large" in _detail(capped).lower() or "big" in _detail(capped).lower()
    _no_trace(capped.text)


def test_markup_in_a_title_is_escaped():
    from sts2sim.htmlreport import render_html
    hostile = '"><script src="https://evil.example/a.js"></script>'
    html = render_html(lang="en", run={
        "meta": {"id": "x", "kind": "batch", "title": hostile, "status": "done", "params": {}},
        "summary": {"n": 1, "wins": 1, "win": 1.0, "survival": [{"floor": 1, "rate": 1}, {"floor": 2, "rate": 0.5}]},
    })
    assert "<script" not in html.lower()
    assert 'src="https://' not in html.lower()
    assert "&lt;script" in html


def test_mcp_and_cli_return_a_file(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(data))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    run = _batch(str(data / "runs"))
    cal = data / "calibration.json"
    with open(GAP, "rb") as handle:
        cal.write_bytes(handle.read())
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "note.json"
    secret.write_text(SECRET, encoding="utf-8")
    link = data / "escape.json"
    link.symlink_to(secret)

    mcp = _load_mcp()
    before = os.path.getsize(os.path.join(run, "runs.jsonl"))
    doc = json.loads(mcp.export_report(run="batch-1", calibration=str(cal), lang="en"))
    assert doc["ok"] is True, doc
    assert os.path.isfile(doc["path"])
    assert doc["path"].endswith(".html")
    with open(doc["path"], encoding="utf-8") as handle:
        text = handle.read()
    assert_offline(text)
    assert "Finished run" in text and "Gap triage" in text
    assert os.path.getsize(os.path.join(run, "runs.jsonl")) == before

    assert json.loads(mcp.export_report(run=None))["error"] == "bad_type"
    assert json.loads(mcp.export_report())["error"] == "need_input"
    missing_b = json.loads(mcp.export_report(a="batch-1"))
    assert missing_b["error"] == "missing" and missing_b["field"] == "b"
    assert json.loads(mcp.export_report(run=str(outside)))["error"] == "path_not_allowed"
    assert json.loads(mcp.export_report(calibration=str(link)))["error"] == "path_not_allowed"
    assert json.loads(mcp.export_report(lang="nope"))["error"] == "bad_lang"
    assert "nope" not in mcp.export_report(lang="nope")
    refused = json.loads(mcp.export_report(run="batch-1", out=str(data / "saves" / "out.html")))
    assert refused["error"] == "refuse_write"
    assert not os.path.exists(data / "saves" / "out.html")
    blocked = json.loads(mcp.export_report(run="batch-1", out=str(outside / "x.html")))
    assert blocked["error"] == "path_not_allowed"
    assert SECRET not in json.dumps(blocked)

    dest = tmp_path / "cli-report.html"
    env = os.environ.copy()
    env["STS2SIM_GUI_DATA"] = str(data)
    env["DECKBENCH_ANALYSIS_ROOTS"] = ""
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "tools.export_report", "--run", "batch-1", "--out", str(dest), "--lang", "zh-CN"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(dest)
    cli_html = dest.read_text(encoding="utf-8")
    assert_offline(cli_html)
    assert "已完成的测试" in cli_html
    assert "Traceback" not in proc.stderr

    bad = subprocess.run(
        [sys.executable, "-m", "tools.export_report", "--lang", "nope"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert bad.returncode == 2
    assert "Traceback" not in bad.stderr
    assert "zh-CN" in bad.stderr
    assert "nope" not in bad.stderr
