"""内置示例结果包：脚本重新跑模拟生成，导入走普通结果包路径，对比能读。"""
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = os.path.join(ROOT, "gui", "demo", "sample.deckbench.zip")
SCRIPT = os.path.join(ROOT, "tools", "make_demo_bundle.py")


def _raw_rows(path):
    found = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.endswith("/raw.jsonl"):
                continue
            rows = []
            for line in archive.read(name).decode("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row.pop("secs", None)
                rows.append(row)
            found[name] = rows
    return found


def _member(path, name):
    with zipfile.ZipFile(path) as archive:
        return archive.read(name)


def test_shipped_demo_is_a_head_to_head_against_the_synthetic_trio():
    assert os.path.getsize(SHIPPED) < 1024 * 1024
    manifest = json.loads(_member(SHIPPED, "manifest.json"))
    assert manifest["format"] == "deckbench.bundle"
    assert manifest["schema"] == 1
    assert manifest["kind"] == "head_to_head"
    assert manifest["runs"] == ["demo-noengine", "demo-routed"]
    preset = _member(SHIPPED, "runs/demo-noengine/preset.yaml").decode("utf-8")
    assert "probe_noengine" in preset and "SYN_TRIO" in preset
    other = _member(SHIPPED, "runs/demo-routed/preset.yaml").decode("utf-8")
    assert "probe_D" in other
    rows = _raw_rows(SHIPPED)
    assert set(rows) == {"runs/demo-noengine/raw.jsonl", "runs/demo-routed/raw.jsonl"}
    results = set()
    hp = []
    for group in rows.values():
        assert len(group) == 30
        for row in group:
            assert row["encounter"] == "SYN_TRIO"
            assert row["enc_name"] == "蛮兵、术士、荆棘"
            assert row["result"] in ("win", "loss", "timeout")
            assert row["turns"] >= 1
            assert row["cards"]
            results.add(row["result"])
            hp.append(row["hp_lost"])
    assert "win" in results and "loss" in results
    assert any(value > 0 for value in hp)


def test_regenerated_demo_imports_and_matches_the_fights(tmp_path, monkeypatch):
    dest = tmp_path / "sample.deckbench.zip"
    proc = subprocess.run(
        [sys.executable, SCRIPT, "--out", str(dest)],
        cwd=ROOT, check=False, capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert _raw_rows(dest) == _raw_rows(SHIPPED)

    from gui import paths
    from sts2sim.bundle import import_zip_bytes
    from sts2sim.runcompare import compare_dirs

    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "RUNS_DIR", str(root))
    body = import_zip_bytes(dest.read_bytes(), filename="sample.deckbench.zip")
    assert body["ok"] is True
    assert body["kind"] == "head_to_head"
    assert [row["original_id"] for row in body["runs"]] == ["demo-noengine", "demo-routed"]
    assert all(row["kind"] == "combat" and row["imported"] for row in body["runs"])
    left = root / body["runs"][0]["id"] / "out"
    right = root / body["runs"][1]["id"] / "out"
    compared = compare_dirs(str(left), str(right))
    cell = compared["cells"][0]
    assert cell["room"] == "精英"
    assert cell["n_a"] == 30 and cell["n_b"] == 30
    win = cell["metrics"]["win"]
    hp = cell["metrics"]["hp_loss"]
    turns = cell["metrics"]["turns"]
    assert win["delta"] not in (None, 0)
    assert hp["delta"] not in (None, 0)
    assert turns["delta"] not in (None, 0)
    assert win["sample_warning"] is False


def test_load_demo_endpoint_and_mcp_use_the_bundle_import(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui import paths
    from gui.server import app
    from tools.mcp_server import load_demo

    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "RUNS_DIR", str(root))
    with TestClient(app) as client:
        res = client.post("/api/demo/load", headers={"x-lang": "en"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and len(body["runs"]) == 2
    assert {row["original_id"] for row in body["runs"]} == {"demo-noengine", "demo-routed"}

    again = json.loads(load_demo())
    assert again["ok"] is True
    assert all(row["renamed"] for row in again["runs"])


def test_second_demo_load_keeps_the_preset_on_reexport(tmp_path, monkeypatch):
    """载入两次（编号冲突后换新 id）再导出，预设字节还在，对比和 zh-CN 报告也能读。"""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui import paths
    from gui.server import app
    from sts2sim.runcompare import compare_dirs

    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "RUNS_DIR", str(root))
    with TestClient(app) as client:
        first = client.post("/api/demo/load", headers={"x-lang": "en"})
        assert first.status_code == 200, first.text
        second = client.post("/api/demo/load", headers={"x-lang": "zh-CN"})
        assert second.status_code == 200, second.text
        rows = second.json()["runs"]
        assert all(row["renamed"] for row in rows)
        assert {row["original_id"] for row in rows} == {"demo-noengine", "demo-routed"}
        ids = {row["original_id"]: row["id"] for row in rows}
        compared = client.get(
            "/api/runs/compare",
            headers={"x-lang": "zh-CN"},
            params={"a": ids["demo-noengine"], "b": ids["demo-routed"]},
        )
        assert compared.status_code == 200, compared.text
        win = compared.json()["cells"][0]["metrics"]["win"]
        assert win["n_a"] == 30 and win["n_b"] == 30 and win["delta"] not in (None, 0)
        html = client.get(
            f"/api/runs/{ids['demo-noengine']}/export.html",
            params={"lang": "zh-CN"},
        )
        assert html.status_code == 200, html.text[:400]
        assert "charset=utf-8" in html.headers["content-type"]
        assert '<html lang="zh-CN">' in html.text
        assert "自包含" in html.text
        bundled = client.get(
            f"/api/runs/{ids['demo-noengine']}/bundle",
            params={"lang": "zh-CN"},
        )
        assert bundled.status_code == 200, bundled.text[:400]
        with zipfile.ZipFile(io.BytesIO(bundled.content)) as archive:
            packed = archive.read(f"runs/{ids['demo-noengine']}/preset.yaml")
            report = archive.read("report.html").decode("utf-8")
        assert packed == _member(SHIPPED, "runs/demo-noengine/preset.yaml")
        assert '<html lang="zh-CN">' in report and "自包含" in report
    left = root / ids["demo-noengine"] / "out"
    right = root / ids["demo-routed"] / "out"
    again = compare_dirs(str(left), str(right))["cells"][0]["metrics"]["win"]["delta"]
    assert again == win["delta"]


def test_missing_demo_bundle_is_a_sentence(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui import demo
    from gui.server import app

    monkeypatch.setattr(demo, "bundle_path", lambda: "")
    with TestClient(app) as client:
        res = client.post("/api/demo/load", headers={"x-lang": "en"})
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert detail == "This install does not include the sample bundle."
    assert "Traceback" not in detail
    missing = json.loads(__import__("tools.mcp_server", fromlist=["load_demo"]).load_demo())
    assert missing["ok"] is False and missing["error"] == "missing"
    assert missing["message"] == detail
