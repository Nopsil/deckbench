"""HTTP 和 MCP 的坏输入：越界路径、超限上传、坏 JSONL、缺字段、类型不对。

不新开模拟，不改种子。fastapi / httpx 没装时，HTTP 用例跳过；MCP 函数本身不依赖它们。
"""
import importlib.util
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "calibrate", "real.run")
SIMS = os.path.join(ROOT, "tests", "fixtures", "calibrate", "sims.jsonl")
SAMPLE = os.path.join(ROOT, "tests", "fixtures", "saves", "sample_history.run")
EN = {"x-lang": "en"}
SECRET = "SECRET-DO-NOT-LEAK"


def _load_mcp():
    name = "deckbench_mcp_hardening_under_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _no_trace(text):
    assert "Traceback" not in text
    assert "traceback" not in text.lower()
    assert SECRET not in text


def _detail(res):
    body = res.json()
    assert isinstance(body.get("detail"), str)
    _no_trace(res.text)
    return body["detail"]


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(data))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    monkeypatch.setenv("DECKBENCH_SAVE_ROOTS", str(tmp_path / "no-saves"))
    return data


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app
    with TestClient(app) as c:
        yield c


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _secret_jsonl():
    return json.dumps({
        "secret": SECRET, "floor": 1, "victory": True, "combats": [],
    }) + "\n"


def _jsonl_row():
    return (
        '{"seed":"S","floor":1,"act":0,"victory":true,'
        '"combats":[[1,"Monster","X",0,4,true,0]]}\n'
    )


def test_calibrate_still_reads_an_allowed_fixture(client, allowed):
    sim = allowed / "runs.jsonl"
    sim.write_bytes(_read_bytes(SIMS))
    res = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sim)})
    assert res.status_code == 200, res.text
    assert res.json()["read_only"] is True
    assert res.json()["gaps"] == [4]


def test_paths_outside_allowed_folders_are_400(client, allowed, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "runs.jsonl"
    secret.write_text(_secret_jsonl(), encoding="utf-8")
    sim = allowed / "runs.jsonl"
    sim.write_bytes(_read_bytes(SIMS))

    direct = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(secret)})
    assert direct.status_code == 400
    detail = _detail(direct)
    assert "outside the allowed folders" in detail

    nested = allowed / "nested"
    nested.mkdir()
    climbed = client.post(
        "/api/calibrate", headers=EN,
        json={"real": REAL, "sim": str(nested / ".." / ".." / "outside" / "runs.jsonl")},
    )
    assert climbed.status_code == 400
    assert "outside the allowed folders" in _detail(climbed)

    link = allowed / "escape.jsonl"
    link.symlink_to(secret)
    escaped = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(link)})
    assert escaped.status_code == 400
    assert "outside the allowed folders" in _detail(escaped)

    sibling = tmp_path / (allowed.name + "-not")
    sibling.mkdir()
    (sibling / "runs.jsonl").write_text(_jsonl_row(), encoding="utf-8")
    prefixed = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sibling / "runs.jsonl")})
    assert prefixed.status_code == 400
    _detail(prefixed)

    nul = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": "runs.jsonl\x00" + SECRET})
    assert nul.status_code == 400
    _detail(nul)


def test_import_batch_refuses_a_symlink_that_leaves_the_folder(client, tmp_path):
    folder = tmp_path / "saves"
    hist = folder / "history"
    hist.mkdir(parents=True)
    shutil.copy(SAMPLE, hist / "good.run")
    outside = tmp_path / "outside.run"
    outside.write_text(SECRET, encoding="utf-8")
    os.symlink(outside, hist / "evil.run")
    alias = hist / "alias.run"
    os.symlink("good.run", alias)

    res = client.post("/api/import/batch", headers=EN, json={"path": str(folder)})
    assert res.status_code == 400
    detail = _detail(res)
    assert "evil.run" in detail
    assert "link outside" in detail
    assert str(outside) not in detail

    os.remove(hist / "evil.run")
    ok = client.post("/api/import/batch", headers=EN, json={"path": str(folder)})
    assert ok.status_code == 200, ok.text
    assert "SAMPLESEED01" in ok.text
    assert SECRET not in ok.text


def test_run_id_cannot_read_outside_the_runs_folder(client, tmp_path, monkeypatch):
    from gui import paths
    from gui.server import jobs
    runs = tmp_path / "runs"
    runs.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "meta.json").write_text(
        json.dumps({"id": "link", "title": SECRET, "status": "done"}), encoding="utf-8",
    )
    (outside / "run.log").write_text(SECRET, encoding="utf-8")
    os.symlink(outside, runs / "link")
    (tmp_path / "meta.json").write_text(json.dumps({"id": "..", "title": SECRET}), encoding="utf-8")
    (tmp_path / "run.log").write_text(SECRET, encoding="utf-8")
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))

    assert jobs.get("..") is None
    assert jobs.get("../outside") is None
    assert jobs.run_dir("..") is None
    assert jobs.log_lines("..") == ([], 0)
    listed = client.get("/api/runs", headers=EN)
    assert listed.status_code == 200
    _no_trace(listed.text)
    opened = client.get("/api/runs/link", headers=EN)
    assert opened.status_code == 404
    _no_trace(opened.text)
    log = client.get("/api/runs/link/log", headers=EN)
    assert log.status_code == 404
    _no_trace(log.text)


def test_uploads_over_the_cap_are_400(client, monkeypatch):
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 8)
    blob = b"12345678" + SECRET.encode("utf-8")
    cal = client.post(
        "/api/calibrate/upload", headers=EN, data={"real": REAL},
        files={"file": ("runs.jsonl", blob, "application/octet-stream")},
    )
    assert cal.status_code == 400
    assert "32" in _detail(cal)
    imp = client.post(
        "/api/import/upload", headers=EN,
        files={"file": ("note.run", blob, "application/octet-stream")},
    )
    assert imp.status_code == 400
    assert "32" in _detail(imp)


def test_upload_filename_is_only_a_basename(client, allowed):
    res = client.post(
        "/api/calibrate/upload", headers=EN, data={"real": REAL},
        files={"file": ("../../etc/passwd", _read_bytes(SIMS), "application/octet-stream")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["sim_path"] == "passwd"
    assert ".." not in res.json()["sim_path"]
    assert not (allowed / "passwd").exists()


def test_malformed_jsonl_is_400_with_the_line_number(client, allowed):
    sim = allowed / "runs.jsonl"
    sim.write_text('{"seed":"A"}\n{nope\n', encoding="utf-8")
    res = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sim)})
    assert res.status_code == 400
    assert _detail(res) == "Line 2 is not JSON."

    number = client.post(
        "/api/calibrate/upload", headers=EN, data={"real": REAL},
        files={"file": ("runs.jsonl", b"1\n", "application/octet-stream")},
    )
    assert number.status_code == 400
    assert _detail(number) == "Line 1 is not JSON."

    array = client.post(
        "/api/calibrate/upload", headers=EN, data={"real": REAL},
        files={"file": ("runs.jsonl", b"[]\n", "application/octet-stream")},
    )
    assert array.status_code == 400
    assert "Line 1" in _detail(array)


def test_oversized_jsonl_on_disk_is_400_without_reading_it_into_the_message(client, allowed, monkeypatch):
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 16)
    sim = allowed / "runs.jsonl"
    sim.write_bytes(b"{" + SECRET.encode("utf-8"))
    res = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sim)})
    assert res.status_code == 400
    assert "32" in _detail(res)


def test_missing_fields_are_400(client):
    cal = client.post("/api/calibrate", headers=EN, json={})
    assert cal.status_code == 400
    assert "real run" in _detail(cal).lower()

    batch = client.post("/api/import/batch", headers=EN, json={})
    assert batch.status_code == 400
    assert _detail(batch).startswith("Path not found")

    blank = client.post("/api/import/batch", headers=EN, json={"path": "  ", "lines": False})
    assert blank.status_code == 400
    assert "Path not found" in _detail(blank)

    upload = client.post("/api/calibrate/upload", headers=EN, data={"real": ""},
                         files={"file": ("runs.jsonl", b"{}\n", "application/octet-stream")})
    assert upload.status_code == 400
    assert "real run" in _detail(upload).lower()

    missing_file = client.post("/api/calibrate/upload", headers=EN, data={"real": REAL})
    assert missing_file.status_code == 400
    detail = _detail(missing_file)
    assert "file" in detail.lower()

    missing_path = client.post("/api/explain", headers=EN, json={})
    assert missing_path.status_code == 400
    assert "path" in _detail(missing_path).lower()


def test_wrong_types_are_400_and_do_not_echo_the_value(client, tmp_path):
    token = "TYPE-TOKEN-SHOULD-NOT-ECHO"
    path = client.post("/api/import/batch", headers=EN, json={"path": 12, "lines": False})
    assert path.status_code == 400
    detail = _detail(path)
    assert "path" in detail and "string" in detail
    assert "12" not in detail

    lines = client.post("/api/import/batch", headers=EN, json={"path": str(tmp_path), "lines": token})
    assert lines.status_code == 400
    detail = _detail(lines)
    assert "lines" in detail and "boolean" in detail
    assert token not in lines.text

    real = client.post("/api/calibrate", headers=EN, json={"real": {"no": token}, "sim": "runs.jsonl"})
    assert real.status_code == 400
    detail = _detail(real)
    assert "real" in detail and "string" in detail
    assert token not in real.text

    fight = client.post("/api/explain/fight", headers=EN, json={"path": str(tmp_path), "fight": token})
    assert fight.status_code == 400
    detail = _detail(fight)
    assert "fight" in detail and "integer" in detail
    assert token not in fight.text

    broken = client.post(
        "/api/calibrate", headers={**EN, "content-type": "application/json"}, content=b"{",
    )
    assert broken.status_code == 400
    assert "JSON" in _detail(broken)

    zh = client.post(
        "/api/import/batch",
        headers={"x-lang": "zhs", "content-type": "application/json"},
        content=b"not-json",
    )
    assert zh.status_code == 400
    assert "JSON" in _detail(zh)
    assert "Traceback" not in zh.text


def test_mcp_tools_return_structured_errors(allowed, tmp_path, monkeypatch):
    mcp = _load_mcp()
    outside = tmp_path / "outside.jsonl"
    outside.write_text(_secret_jsonl(), encoding="utf-8")
    link = allowed / "escape.jsonl"
    link.symlink_to(outside)
    bad = allowed / "bad.jsonl"
    bad.write_text("{nope\n", encoding="utf-8")
    short = allowed / "short.jsonl"
    short.write_text('{"victory": true}\n', encoding="utf-8")
    huge = allowed / "huge.jsonl"
    huge.write_bytes(b"{" + (SECRET.encode("utf-8") * 4))

    def load(text):
        body = json.loads(text)
        assert body["ok"] is False
        _no_trace(text)
        return body

    assert load(mcp.batch_run_summary(str(outside)))["error"] == "path_not_allowed"
    assert load(mcp.batch_run_summary(str(link)))["error"] == "path_not_allowed"
    assert load(mcp.batch_run_summary(str(allowed / ".." / outside.name)))["error"] == "path_not_allowed"
    assert load(mcp.batch_run_summary(None))["error"] == "need_path"
    assert load(mcp.batch_run_summary("runs.jsonl\x00" + SECRET))["error"] == "path_not_allowed"
    broken = load(mcp.batch_run_summary(str(bad)))
    assert broken["error"] == "not_json" and broken["line"] == 1
    assert load(mcp.batch_run_summary(str(short)))["error"] == "not_batch"
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32)
    assert load(mcp.batch_run_summary(str(huge)))["error"] == "too_big"
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32 * 1024 * 1024)
    assert load(mcp.card_ab(123))["error"] == "need_path"
    assert load(mcp.explain_fight(str(bad), fight=1.5))["error"] == "bad_fight"
    assert load(mcp.explain_fight(str(bad), seed=1))["error"] == "bad_seed"

    missing = load(mcp.import_save(None))
    assert missing["error"] == "not_found" and missing["read_only"] is True
    assert load(mcp.import_save(12))["error"] == "not_found"
    lines = load(mcp.import_history_batch(str(outside), lines="yes"))
    assert lines["error"] == "bad_type" and lines["field"] == "lines"
    assert load(mcp.calibrate(None, None))["error"] == "need_real"
    assert load(mcp.calibrate(REAL, str(link)))["error"] == "path_not_allowed"
    assert load(mcp.calibrate(REAL, str(bad)))["error"] == "not_json"

    folder = tmp_path / "saves"
    hist = folder / "history"
    hist.mkdir(parents=True)
    target = tmp_path / "leak.run"
    target.write_text(SECRET, encoding="utf-8")
    os.symlink(target, hist / "evil.run")
    escaped = load(mcp.import_history_batch(str(folder)))
    assert escaped["error"] == "path_not_allowed"
    assert escaped.get("path") == "evil.run"
    assert str(target) not in json.dumps(escaped)

    assert load(mcp.gap_triage(reports=None))["error"] == "bad_type"
    assert load(mcp.gap_triage(paths=str(outside)))["error"] == "bad_type"
    assert load(mcp.gap_triage(paths=[str(link)]))["error"] == "path_not_allowed"
    assert load(mcp.gap_triage(paths=[str(bad)]))["error"] == "not_json"
    assert load(mcp.gap_triage())["error"] == "need_input"
    assert load(mcp.gap_triage(min_compared="no"))["error"] == "bad_type"
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32)
    assert load(mcp.gap_triage(paths=[str(huge)]))["error"] == "too_big"
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32 * 1024 * 1024)

    preview = load(mcp.seed_preview("ABCDEFGHJKLM", cache="yes"))
    assert preview["error"] == "bad_type" and preview["field"] == "cache"
    cache_dir = json.loads(mcp.seed_preview("ABCDEFGHJKLM", cache=True, cache_dir=3))
    assert cache_dir["ok"] is False and cache_dir["error"] == "bad_type"
    assert cache_dir["field"] == "cache_dir"


def _gap_report(encounter="SAMPLE_ELITE"):
    return {
        "ok": True,
        "v": 1,
        "alignment": "floor_room_encounter",
        "fights": [{
            "floor": 1,
            "room": "Monster",
            "encounter": encounter,
            "status": "compared",
            "real_hp_lost": 20,
            "p5": 0,
            "p95": 5,
            "likely_sim_gap": True,
        }],
    }


def test_gap_triage_rejects_bad_input(client, allowed, tmp_path, monkeypatch):
    token = "TYPE-TOKEN-SHOULD-NOT-ECHO"
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "calibration.json"
    secret.write_text(json.dumps({"secret": SECRET, "ok": True}), encoding="utf-8")
    good = allowed / "calibration.json"
    good.write_text(json.dumps(_gap_report()), encoding="utf-8")

    missing = client.post("/api/gap_triage", headers=EN, json={})
    assert missing.status_code == 400
    assert "calibration" in _detail(missing).lower()

    zh = client.post("/api/gap_triage", headers={"x-lang": "zhs"}, json={})
    assert zh.status_code == 400
    assert _detail(zh) != _detail(missing)
    assert "校准" in _detail(zh)

    broken = client.post(
        "/api/gap_triage", headers={**EN, "content-type": "application/json"}, content=b"{",
    )
    assert broken.status_code == 400
    assert "JSON" in _detail(broken)

    reports = client.post("/api/gap_triage", headers=EN, json={"reports": token})
    assert reports.status_code == 400
    detail = _detail(reports)
    assert "reports" in detail and "object" in detail and "array" in detail
    assert token not in reports.text

    paths = client.post("/api/gap_triage", headers=EN, json={"paths": 12})
    assert paths.status_code == 400
    detail = _detail(paths)
    assert "paths" in detail and "array" in detail
    assert "12" not in detail

    bad_item = client.post("/api/gap_triage", headers=EN, json={"paths": [{"no": token}]})
    assert bad_item.status_code == 400
    detail = _detail(bad_item)
    assert "paths.0" in detail and "string" in detail
    assert token not in bad_item.text

    listed = client.post("/api/gap_triage", headers=EN, json={"reports": [token]})
    assert listed.status_code == 400
    detail = _detail(listed)
    assert "reports.0" in detail and "object" in detail
    assert token not in listed.text

    catalog = client.post(
        "/api/gap_triage", headers=EN, json={"reports": _gap_report(), "catalog": {"no": token}},
    )
    assert catalog.status_code == 400
    detail = _detail(catalog)
    assert "catalog" in detail and "string" in detail
    assert token not in catalog.text

    minimum = client.post(
        "/api/gap_triage", headers=EN, json={"reports": _gap_report(), "min_compared": token},
    )
    assert minimum.status_code == 400
    detail = _detail(minimum)
    assert "min_compared" in detail and "integer" in detail
    assert token not in minimum.text

    flag = client.post(
        "/api/gap_triage", headers=EN, json={"reports": _gap_report(), "min_compared": True},
    )
    assert flag.status_code == 400
    assert "integer" in _detail(flag)

    direct = client.post("/api/gap_triage", headers=EN, json={"paths": [str(secret)]})
    assert direct.status_code == 400
    assert "outside the allowed folders" in _detail(direct)

    link = allowed / "escape.json"
    link.symlink_to(secret)
    escaped = client.post("/api/gap_triage", headers=EN, json={"paths": [str(link)]})
    assert escaped.status_code == 400
    assert "outside the allowed folders" in _detail(escaped)

    pack = allowed / "pack"
    pack.mkdir()
    os.symlink(secret, pack / "linked.json")
    escaped_dir = client.post("/api/gap_triage", headers=EN, json={"paths": [str(pack)]})
    assert escaped_dir.status_code == 400
    assert "outside the allowed folders" in _detail(escaped_dir)
    assert SECRET not in escaped_dir.text

    nested = allowed / "nested"
    nested.mkdir()
    climbed = client.post(
        "/api/gap_triage", headers=EN,
        json={"paths": [str(nested / ".." / ".." / "outside" / "calibration.json")]},
    )
    assert climbed.status_code == 400
    assert "outside the allowed folders" in _detail(climbed)

    sibling = tmp_path / (allowed.name + "-not")
    sibling.mkdir()
    (sibling / "calibration.json").write_text(json.dumps(_gap_report()), encoding="utf-8")
    prefixed = client.post("/api/gap_triage", headers=EN, json={"paths": [str(sibling / "calibration.json")]})
    assert prefixed.status_code == 400
    _detail(prefixed)

    nul = client.post("/api/gap_triage", headers=EN, json={"paths": ["calibration.json\x00" + SECRET]})
    assert nul.status_code == 400
    _detail(nul)

    bad = allowed / "bad.json"
    bad.write_text("{", encoding="utf-8")
    malformed = client.post("/api/gap_triage", headers=EN, json={"paths": [str(bad)]})
    assert malformed.status_code == 400
    assert "not JSON" in _detail(malformed)

    note = allowed / "note.run"
    note.write_text(SECRET, encoding="utf-8")
    refused = client.post("/api/gap_triage", headers=EN, json={"paths": [str(note)]})
    assert refused.status_code == 400
    assert SECRET not in refused.text

    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 16)
    huge = allowed / "huge.json"
    huge.write_bytes(b"{" + SECRET.encode("utf-8"))
    oversized = client.post("/api/gap_triage", headers=EN, json={"paths": [str(huge)]})
    assert oversized.status_code == 400
    assert "32" in _detail(oversized)

    posted = client.post(
        "/api/gap_triage",
        headers={**EN, "content-type": "application/json"},
        content=b"{" + SECRET.encode("utf-8"),
    )
    assert posted.status_code == 400
    assert "32" in _detail(posted)
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 32 * 1024 * 1024)

    crafted = _gap_report()
    crafted["real_path"] = str(secret)
    leaked = client.post("/api/gap_triage", headers=EN, json={"reports": crafted})
    assert leaked.status_code == 200, leaked.text
    assert SECRET not in leaked.text

    mixed = client.post("/api/gap_triage", headers=EN, json={"reports": [_gap_report(), {"secret": SECRET}]})
    assert mixed.status_code == 200, mixed.text
    assert SECRET not in mixed.text
    assert mixed.json()["counts"]["optimistic"] == 1

    ok = client.post("/api/gap_triage", headers=EN, json={"paths": [str(good)]})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["read_only"] is True
    assert body["encounters"]["optimistic"][0]["id"] == "SAMPLE_ELITE"
    assert any(item["file"] == "sts2sim/powers_enemy.py" for item in body["encounters"]["optimistic"][0]["code"])
