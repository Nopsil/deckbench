"""内置示例结果包：脚本重新跑模拟生成，导入走普通结果包路径，对比能读。"""
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


def test_shipped_demo_is_a_compare_bundle_of_dummy_fights():
    manifest = json.loads(_member(SHIPPED, "manifest.json"))
    assert manifest["format"] == "deckbench.bundle"
    assert manifest["schema"] == 1
    assert manifest["kind"] == "compare"
    assert manifest["runs"] == ["demo-deck", "demo-probe"]
    preset = _member(SHIPPED, "runs/demo-deck/preset.yaml").decode("utf-8")
    assert "user_deck:" in preset
    assert "YIHESHI" in preset and "XIAOBENBEN" in preset
    assert "encounter: DUMMY" in preset
    rows = _raw_rows(SHIPPED)
    assert set(rows) == {"runs/demo-deck/raw.jsonl", "runs/demo-probe/raw.jsonl"}
    for group in rows.values():
        assert len(group) == 2
        for row in group:
            assert row["encounter"] == "DUMMY"
            assert row["enc_name"] == "木桩"
            assert row["result"] in ("win", "loss", "timeout")
            assert row["cards"]


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
    assert body["kind"] == "compare"
    assert [row["original_id"] for row in body["runs"]] == ["demo-deck", "demo-probe"]
    assert all(row["kind"] == "combat" and row["imported"] for row in body["runs"])
    left = root / body["runs"][0]["id"] / "out"
    right = root / body["runs"][1]["id"] / "out"
    compared = compare_dirs(str(left), str(right))
    assert compared["cells"]
    assert any(cell.get("encounter") == "DUMMY" or cell.get("room") == "probe" for cell in compared["cells"])


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
    assert {row["original_id"] for row in body["runs"]} == {"demo-deck", "demo-probe"}

    again = json.loads(load_demo())
    assert again["ok"] is True
    assert all(row["renamed"] for row in again["runs"])


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
