"""HTTP 错误路径：导入、校准、种子预览、说明日志、运行和模组上传。

只断言已经翻译的 400/404/409/500，不新开模拟，不写进仓库。
"""
import io
import json
import os
import zipfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from gui import server  # noqa: E402
from gui.jobs import Job  # noqa: E402
from gui.server import app  # noqa: E402
from sts2sim.saveimport import SaveImportError  # noqa: E402

EN = {"x-lang": "en"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _detail(res):
    body = res.json()
    return body.get("detail") if isinstance(body, dict) else body


def _run_file(path, **over):
    raw = {
        "seed": "SEED01",
        "ascension": 0,
        "players": [{"id": 1, "character": "CHARACTER.IRONCLAD"}],
        "map_point_history": [],
    }
    raw.update(over)
    path.write_text(json.dumps(raw), encoding="utf-8")


def _job(tmp_path, rid, kind="batch", status="running"):
    folder = tmp_path / rid
    folder.mkdir()
    meta = {"id": rid, "kind": kind, "status": status, "title": "t", "params": {"n": 1}}
    server.jobs.jobs[rid] = Job(meta, str(folder))
    return rid


def test_import_error_codes_and_detail(client, tmp_path, monkeypatch):
    missing = client.post("/api/import", headers=EN, json={"path": str(tmp_path / "nope.run")})
    assert missing.status_code == 400 and _detail(missing).startswith("Path not found")

    array = tmp_path / "array.run"
    array.write_text("[1, 2]", encoding="utf-8")
    not_obj = client.post("/api/import", headers=EN, json={"path": str(array)})
    assert not_obj.status_code == 400 and "not an object" in _detail(not_obj)

    shape = tmp_path / "shape.run"
    shape.write_text('{"hello": 1}', encoding="utf-8")
    unknown = client.post("/api/import", headers=EN, json={"path": str(shape)})
    assert unknown.status_code == 400 and "does not look like a run" in _detail(unknown)

    progress = tmp_path / "progress.run"
    progress.write_text('{"epochs": 1, "cards_unlocked": []}', encoding="utf-8")
    not_run = client.post("/api/import", headers=EN, json={"path": str(progress)})
    assert not_run.status_code == 400 and "not one run" in _detail(not_run)

    odd = tmp_path / "odd.run"
    odd.write_bytes(b"\xff\xfe\x41")
    decoded = client.post("/api/import", headers=EN, json={"path": str(odd)})
    assert decoded.status_code == 400 and "UTF-8 or UTF-16" in _detail(decoded)

    broken = tmp_path / "broken.run"
    broken.write_text("{", encoding="utf-8")
    detail = client.post("/api/import", headers=EN, json={"path": str(broken)})
    text = _detail(detail)
    assert detail.status_code == 400 and "not a text JSON" in text and "(" in text and "{" not in text

    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 8)
    big = tmp_path / "big.run"
    big.write_text('{"seed": "TOO-BIG-FOR-THE-LIMIT"}', encoding="utf-8")
    too_big = client.post("/api/import", headers=EN, json={"path": str(big)})
    assert too_big.status_code == 400 and "32MB" in _detail(too_big)

    empty = tmp_path / "empty-dir"
    empty.mkdir()
    vacant = client.post("/api/import/batch", headers=EN, json={"path": str(empty)})
    assert vacant.status_code == 400 and "No .run or current_run.save" in _detail(vacant)

    upload = client.post(
        "/api/import/upload",
        headers=EN,
        files={"file": ("x.run", b"\xff\xfe\x41", "application/octet-stream")},
    )
    assert upload.status_code == 400 and "UTF-8 or UTF-16" in _detail(upload)
    huge = client.post(
        "/api/import/upload",
        headers=EN,
        files={"file": ("x.run", b"0123456789", "application/octet-stream")},
    )
    assert huge.status_code == 400 and "32MB" in _detail(huge)

    long = server._import_detail(SaveImportError("not_json", detail="{" + ("x" * 200) + "}"))
    assert long.endswith("...") and "{" not in long and "}" not in long
    assert len(long) == 163


def test_calibrate_error_codes(client, tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    sim = allowed / "runs.jsonl"
    sim.write_text('{"seed":"SEED01","char":"Ironclad","asc":0,"picked":[],"combats":[]}\n', encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", str(allowed))
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path / "gui-data"))
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "cache"))

    blank = client.post("/api/calibrate", headers=EN, json={"real": "  ", "sim": str(sim)})
    assert blank.status_code == 400 and "real run" in _detail(blank).lower()
    need_sim = client.post("/api/calibrate", headers=EN, json={"real": str(sim), "sim": ""})
    assert need_sim.status_code == 400 and "simulated runs" in _detail(need_sim).lower()

    multi = tmp_path / "multi.run"
    _run_file(multi, players=[
        {"id": 1, "character": "CHARACTER.IRONCLAD"},
        {"id": 2, "character": "CHARACTER.SILENT"},
    ])
    res = client.post("/api/calibrate", headers=EN, json={"real": str(multi), "sim": str(sim)})
    assert res.status_code == 400 and "multiplayer" in _detail(res).lower()

    no_seed = tmp_path / "noseed.run"
    _run_file(no_seed, seed=None)
    res = client.post("/api/calibrate", headers=EN, json={"real": str(no_seed), "sim": str(sim)})
    assert res.status_code == 400 and "no seed" in _detail(res).lower()

    no_char = tmp_path / "nochar.run"
    _run_file(no_char, players=[{"id": 1}])
    res = client.post("/api/calibrate", headers=EN, json={"real": str(no_char), "sim": str(sim)})
    assert res.status_code == 400 and "no character" in _detail(res).lower()

    no_asc = tmp_path / "noasc.run"
    _run_file(no_asc)
    raw = json.loads(no_asc.read_text(encoding="utf-8"))
    raw.pop("ascension")
    no_asc.write_text(json.dumps(raw), encoding="utf-8")
    # 导入把缺省的进阶写成 0。no_ascension 是内存里的对局才会走到的错误，这里只核对文案。
    res = client.post("/api/calibrate", headers=EN, json={"real": str(no_asc), "sim": str(sim)})
    assert res.status_code == 200 and res.json()["ascension"] == 0
    from sts2sim.calibrate import CalibrateError
    assert "no ascension" in server._calibrate_http(CalibrateError("no_ascension")).lower()

    junk = tmp_path / "junk.run"
    junk.write_text("{", encoding="utf-8")
    res = client.post("/api/calibrate", headers=EN, json={"real": str(junk), "sim": str(sim)})
    assert res.status_code == 400 and "not a text JSON" in _detail(res)

    gone = client.post("/api/calibrate", headers=EN, json={"real": str(multi), "sim": str(allowed / "missing.jsonl")})
    assert gone.status_code == 400 and "Path not found" in _detail(gone)

    save_sim = allowed / "notes.run"
    save_sim.write_text("{}\n", encoding="utf-8")
    refused = client.post("/api/calibrate", headers=EN, json={"real": str(multi), "sim": str(save_sim)})
    assert refused.status_code == 400 and "save folder" in _detail(refused).lower()


def test_preview_and_explain_error_codes(client, tmp_path, monkeypatch):
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    preview = {"seed": "ABCDEFGHJKLM", "char": "Ironclad", "asc": 0, "neow": "first"}

    empty = client.post("/api/seed-preview", headers=EN, json={**preview, "seed": "  "})
    assert empty.status_code == 400 and "Enter a seed" in _detail(empty)
    bad_asc = client.post("/api/seed-preview", headers=EN, json={**preview, "asc": 99})
    assert bad_asc.status_code == 400 and "0 to 10" in _detail(bad_asc)
    bad_char = client.post("/api/seed-preview", headers=EN, json={**preview, "char": "Nope"})
    assert bad_char.status_code == 400 and "Nope" in _detail(bad_char)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("sts2sim.engine.seedpreview.preview", _boom)
    failed = client.post("/api/seed-preview", headers=EN, json=preview)
    assert failed.status_code == 400
    assert "RuntimeError" in _detail(failed) and "boom" in _detail(failed)
    assert "not generated yet" not in _detail(failed)

    log = tmp_path / "runs.explain.jsonl"
    log.write_text(json.dumps({
        "v": 1, "seq": 1, "kind": "play", "seed": "S", "char": "Ironclad",
        "fight": 1, "floor": 2, "act": 1, "room": "Monster", "encounter": "ENCOUNTER.SAMPLE",
        "turn": 1, "chosen": {"id": "STRIKE", "score": 1}, "candidates": [{"id": "STRIKE", "score": 1}],
    }) + "\n", encoding="utf-8")
    late = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "fight": -1})
    assert late.status_code == 400 and "starting at 0" in _detail(late)
    offset = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "offset": -1})
    assert offset.status_code == 400 and "Offset" in _detail(offset)


def test_run_job_and_catalog_errors(client, tmp_path):
    unknown = client.post("/api/runs", headers=EN, json={"kind": "nope", "params": {}})
    assert unknown.status_code == 400 and "Unknown test type" in _detail(unknown)
    need = client.post("/api/runs", headers=EN, json={"kind": "combat", "params": {}})
    assert need.status_code == 400 and "at least one deck" in _detail(need)
    missing = client.get("/api/runs/missing", headers=EN)
    assert missing.status_code == 404 and "not found" in _detail(missing).lower()

    try:
        running = _job(tmp_path, "cov-run", status="running")
        other = _job(tmp_path, "cov-combat", kind="combat", status="done")
        done = _job(tmp_path, "cov-done", status="done")
        summary = client.get(f"/api/runs/{running}/summary", headers=EN)
        assert summary.status_code == 409 and "hasn't finished" in _detail(summary)
        report = client.get(f"/api/runs/{done}/report", headers=EN)
        assert report.status_code == 404 and "report.md" in _detail(report)
        bad_file = client.get(f"/api/runs/{done}/files/secret.txt", headers=EN)
        assert bad_file.status_code == 404
        kind = client.get(f"/api/ab?a={done}&b={other}", headers=EN)
        assert kind.status_code == 400 and "different types" in _detail(kind)
        early = client.get(f"/api/ab?a={running}&b={done}", headers=EN)
        assert early.status_code == 400 and "must be finished" in _detail(early)
        delete = client.delete(f"/api/runs/{running}", headers=EN)
        assert delete.status_code == 400 and "cancel it first" in _detail(delete)
    finally:
        for rid in ("cov-run", "cov-combat", "cov-done"):
            server.jobs.jobs.pop(rid, None)

    def _down(*args, **kwargs):
        raise RuntimeError("catalog down")

    server.backend.catalog = _down
    try:
        failed = client.get("/api/catalog", headers=EN)
        assert failed.status_code == 500 and "catalog down" in _detail(failed)
    finally:
        del server.backend.catalog


def test_mod_upload_rejects_bad_archives(client):
    def _post(buf, name="mod.zip"):
        return client.post("/api/mods/upload", headers=EN, files={"file": (name, buf.getvalue(), "application/zip")})

    raw = io.BytesIO(b"not a zip")
    bad = _post(raw)
    assert bad.status_code == 400 and "valid zip" in _detail(bad)

    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, "w") as zf:
        zf.writestr("../evil.txt", b"x")
    escaped = _post(unsafe)
    assert escaped.status_code == 400 and "Unsafe path" in _detail(escaped)

    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("readme.txt", b"hi")
    no_yaml = _post(empty)
    assert no_yaml.status_code == 400 and "mod.yaml" in _detail(no_yaml)

    named = io.BytesIO()
    with zipfile.ZipFile(named, "w") as zf:
        zf.writestr("mod.yaml", b"name: bad name\n")
    bad_name = _post(named)
    assert bad_name.status_code == 400 and "letters, digits and underscores" in _detail(bad_name)

    listed = io.BytesIO()
    with zipfile.ZipFile(listed, "w") as zf:
        zf.writestr("mod.yaml", b"name: CovMod\ndecks: [decks.yaml]\ncards: [cards.yaml]\n")
        zf.writestr("cards.yaml", b":\n  - [\n")
    problems = _post(listed)
    assert problems.status_code == 400
    text = _detail(problems)
    assert "decks.yaml" in text and "not valid YAML" in text and "No decks" not in text

    nodecks = io.BytesIO()
    with zipfile.ZipFile(nodecks, "w") as zf:
        zf.writestr("mod.yaml", b"name: CovMod\n")
    missing_decks = _post(nodecks)
    assert missing_decks.status_code == 400 and "at least one deck" in _detail(missing_decks)

    removed = client.delete("/api/mods/bad-name", headers=EN)
    assert removed.status_code == 400
