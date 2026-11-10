"""战斗测试的进度和取消。

多场训练木桩在两场之间停下。已经打完的场次留下，状态是 cancelled，并标明 partial。
对比和导出走这些结果时不抛栈。不改模拟器的出牌。
"""
import json
import threading
import time

import pytest

EN = {"x-lang": "en"}


def _payload(pid):
    return {
        "id": pid,
        "name": "Progress deck",
        "mod": "claude_v34",
        "max_turns": 1,
        "encounters": [{"id": "DUMMY", "fights": 24}],
        "cards": [
            {"id": "YIHESHI", "count": 1, "upgrade": False},
            {"id": "XIAOBENBEN", "count": 1, "upgrade": False},
        ],
    }


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
    with TestClient(app) as c:
        yield c


def _runs_dir(allowed, monkeypatch):
    from gui import paths
    runs = allowed / "runs"
    runs.mkdir()
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))
    return runs


def _wait(client, rid, timeout=120):
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


def _other(runs):
    run = runs / "other-done"
    out = run / "out"
    out.mkdir(parents=True)
    meta = {
        "id": "other-done", "kind": "combat", "title": "Other", "status": "done",
        "created": "2026-01-02T00:00:00+00:00", "params": {}, "partial": False,
    }
    (run / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    row = {
        "deck": "other", "act": 1, "room": "探针", "encounter": "DUMMY", "enc_name": "木桩",
        "result": "win", "turns": 1, "hp_lost": 0, "dmg_total": 1, "cards": {},
    }
    (out / "raw.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    return run


def test_progress_and_cancel_mid_batch(client, allowed, monkeypatch):
    from gui.server import jobs
    from tools import mcp_server as mcp

    monkeypatch.setenv("DECKBENCH_FIGHT_GAP", "0.2")
    runs = _runs_dir(allowed, monkeypatch)
    _other(runs)
    saved = client.post("/api/decks", headers=EN, json=_payload("progdeck"))
    assert saved.status_code == 200, saved.text
    started = client.post("/api/runs", headers=EN, json={
        "kind": "combat",
        "title": "progress cancel",
        "params": {"preset": "progdeck", "fights": 1, "seed": 3, "agent": "heuristic", "procs": 1},
    })
    assert started.status_code == 200, started.text
    rid = started.json()["id"]

    errors = []
    stop = threading.Event()

    def hit():
        while not stop.is_set():
            view = jobs.progress(rid)
            if not isinstance(view, dict):
                errors.append(view)
                return
            if view["done"] > view["total"] and view["total"]:
                errors.append(view)
                return
            elapsed = view.get("elapsed")
            if elapsed is not None and elapsed < 0:
                errors.append(view)
                return
            time.sleep(0.01)

    threads = [threading.Thread(target=hit) for _ in range(3)]
    for thread in threads:
        thread.start()

    seen = None
    deadline = time.time() + 90
    while time.time() < deadline:
        seen = client.get(f"/api/runs/{rid}/progress", headers=EN).json()
        if seen["status"] not in ("running", "queued"):
            break
        if 1 <= seen["done"] < seen["total"] and seen["encounter"] == "DUMMY" and seen["total"] >= 24:
            break
        time.sleep(0.02)
    assert seen is not None
    assert seen["status"] == "running", seen
    assert seen["done"] >= 1 and seen["total"] >= 24 and seen["done"] < seen["total"]
    assert seen["encounter"] == "DUMMY"
    assert isinstance(seen["elapsed"], (int, float)) and seen["elapsed"] >= 0
    assert seen["partial"] is False

    early = client.get("/api/runs/compare", headers=EN, params={"a": rid, "b": "other-done"})
    assert early.status_code == 400, early.text
    assert "Traceback" not in early.text
    running_export = client.get(f"/api/runs/{rid}/export.html", headers=EN)
    assert running_export.status_code == 409
    assert "Traceback" not in running_export.text

    live = json.loads(mcp.run_progress(rid))
    assert live["ok"] is True and live["done"] >= 1 and live["id"] == rid
    cancelled = json.loads(mcp.cancel_run(rid))
    assert cancelled["ok"] is True and cancelled["cancel_requested"] is True
    assert "Traceback" not in json.dumps(cancelled)

    final = _wait(client, rid)
    stop.set()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert not errors, errors

    assert final["status"] == "cancelled", final
    assert final["partial"] is True
    assert 1 <= final["done"] < final["total"]
    meta = json.loads((runs / rid / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "cancelled" and meta["partial"] is True
    rows = [
        json.loads(line)
        for line in (runs / rid / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == final["done"]
    assert all(row["encounter"] == "DUMMY" for row in rows)
    report = (runs / rid / "out" / "report.md").read_text(encoding="utf-8")
    assert "Partial result" in report or "部分结果" in report

    compared = client.get("/api/runs/compare", headers=EN, params={"a": rid, "b": "other-done"})
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert body["partial"] is True
    assert body["a"]["partial"] is True and body["a"]["status"] == "cancelled"
    assert "Traceback" not in compared.text
    exported = client.get(f"/api/runs/{rid}/export.html", headers=EN)
    assert exported.status_code == 200, exported.text
    assert "Partial result" in exported.text
    assert "Traceback" not in exported.text

    missing = client.get("/api/runs/no-such-run/progress", headers=EN)
    assert missing.status_code == 404
    assert "Traceback" not in missing.text
    climbed = json.loads(mcp.run_progress("../nope"))
    assert climbed["ok"] is False and climbed["error"] == "bad_type"
    assert ".." not in json.dumps(climbed)
    unknown = json.loads(mcp.cancel_run("missing-run"))
    assert unknown["ok"] is False and unknown["error"] == "not_found"
    again = json.loads(mcp.cancel_run(rid))
    assert again["ok"] is False and again["error"] == "not_running"
