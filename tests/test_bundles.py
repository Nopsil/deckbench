"""可分享的结果包：导出 .deckbench.zip，再导入，对比数字不变。

校验清单和 SHA-256。改过的哈希、zip 路径穿越、对不上的 schema 都拒绝。
包里的文件只当数据写进测试目录，不执行。
"""
import hashlib
import io
import json
import os
import shutil
import zipfile

import pytest

from sts2sim.bundle import (
    SCHEMA,
    BundleError,
    export_bundle_json,
    export_compare_bytes,
    export_run_bytes,
    import_bundle_json,
    import_zip_bytes,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = {"x-lang": "en"}
SECRET = "SECRET-DO-NOT-LEAK"


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
    data = tmp_path / "data"
    root = data / "runs"
    root.mkdir(parents=True)
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(data))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    monkeypatch.setattr(paths, "DATA_DIR", str(data))
    monkeypatch.setattr(paths, "RUNS_DIR", str(root))
    return root


def _combat(root, rid, rows, title, *, preset="", shared=False):
    run = os.path.join(root, rid)
    out = os.path.join(run, "out")
    os.makedirs(out, exist_ok=True)
    params = {"preset": preset or "probe", "fights": len(rows), "agent": "heuristic", "seed": 1}
    if shared:
        params["shared_plan"] = True
    meta = {
        "id": rid, "kind": "combat", "title": title, "status": "done",
        "created": "2026-01-02T00:00:00+00:00",
        "params": params,
        "argv": ["python", "-c", SECRET],
    }
    with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle)
    with open(os.path.join(out, "raw.jsonl"), "w", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row) + "\n" for row in rows)
    return run


def _rows(wins, hp, turns, plays, room):
    rows = []
    for i in range(8):
        rows.append({
            "deck": "probe", "act": 1, "room": room, "result": "win" if i < wins else "loss",
            "turns": turns + (i % 2), "hp_lost": hp + (i % 3), "dmg_total": 10 + i,
            "cards": {"STRIKE": [plays, 10, 0, plays]},
        })
    return rows


def _names(archive):
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return zf.namelist()


def _member(archive, name):
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return zf.read(name)


def _manifest(archive):
    return json.loads(_member(archive, "manifest.json").decode("utf-8"))


def _compare(client, a, b):
    res = client.get("/api/runs/compare", headers=EN, params={"a": a, "b": b})
    assert res.status_code == 200, res.text[:400]
    body = res.json()
    return {"cells": body["cells"], "cards": body["cards"]}


def test_round_trip_compare_is_equal_and_collision_gets_a_new_id(client, runs):
    _combat(str(runs), "base", _rows(2, 12, 6, 1, "Monster"), "Baseline")
    _combat(str(runs), "changed", _rows(6, 4, 3, 4, "Monster"), "Changed")
    original = _compare(client, "base", "changed")

    exported = client.get("/api/runs/compare/bundle", headers=EN, params={"a": "base", "b": "changed"})
    assert exported.status_code == 200, exported.text[:400]
    assert exported.headers["content-type"].split(";")[0] == "application/zip"
    disposition = exported.headers["content-disposition"]
    assert "attachment;" in disposition.lower()
    assert disposition.endswith(".deckbench.zip") or ".deckbench.zip" in disposition
    blob = exported.content
    manifest = _manifest(blob)
    assert manifest["schema"] == SCHEMA
    assert manifest["format"] == "deckbench.bundle"
    assert manifest["kind"] == "compare"
    assert manifest["runs"] == ["base", "changed"]
    import sts2sim
    assert manifest["deckbench"] == sts2sim.__version__
    listed = {row["path"]: row for row in manifest["files"]}
    assert set(_names(blob)) == {"manifest.json", *listed}
    for path, row in listed.items():
        data = _member(blob, path)
        assert len(data) == row["bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
    assert b"report.html" in blob
    report = _member(blob, "report.html").decode("utf-8")
    assert "<html" in report.lower() and "<script" not in report.lower()
    assert "Baseline" in report and "Changed" in report
    assert SECRET.encode() not in blob
    assert b"argv" not in _member(blob, "runs/base/meta.json")

    shutil.rmtree(runs / "base")
    shutil.rmtree(runs / "changed")
    imported = client.post(
        "/api/bundles/import",
        headers=EN,
        files={"file": ("pair.deckbench.zip", blob, "application/zip")},
    )
    assert imported.status_code == 200, imported.text[:500]
    body = imported.json()
    assert body["ok"] is True and body["kind"] == "compare"
    assert [row["original_id"] for row in body["runs"]] == ["base", "changed"]
    assert [row["renamed"] for row in body["runs"]] == [False, False]
    assert [row["id"] for row in body["runs"]] == ["base", "changed"]
    again = _compare(client, "base", "changed")
    assert again == original
    listed_runs = client.get("/api/runs").json()
    by_id = {row["id"]: row for row in listed_runs}
    assert by_id["base"]["imported"] is True
    assert by_id["base"]["origin"]["source"] == "bundle"
    assert by_id["base"]["origin"]["deckbench"] == sts2sim.__version__
    assert by_id["base"]["origin"]["original_id"] == "base"
    assert by_id["base"]["status"] == "done"
    raw = (runs / "base" / "out" / "raw.jsonl").read_bytes()
    assert raw == _member(blob, "runs/base/raw.jsonl")

    second = client.post(
        "/api/bundles/import",
        headers=EN,
        files={"file": ("pair.deckbench.zip", blob, "application/zip")},
    )
    assert second.status_code == 200, second.text[:500]
    renamed = second.json()["runs"]
    assert all(row["renamed"] for row in renamed)
    assert renamed[0]["id"] != "base" and renamed[1]["id"] != "changed"
    collided = _compare(client, renamed[0]["id"], renamed[1]["id"])
    assert collided == original
    assert (runs / "base").is_dir() and (runs / renamed[0]["id"]).is_dir()


def test_single_run_bundle_keeps_the_preset_as_data(client, runs, tmp_path):
    preset = tmp_path / "data" / "presets"
    preset.mkdir(parents=True)
    text = "name: probe\ntitle: Probe deck\ndecks:\n  - id: probe\n"
    (preset / "probe.yaml").write_text(text, encoding="utf-8")
    _combat(str(runs), "solo", _rows(3, 5, 4, 2, "Elite"), "Solo")
    exported = client.get("/api/runs/solo/bundle", headers=EN)
    assert exported.status_code == 200, exported.text[:400]
    blob = exported.content
    assert _manifest(blob)["kind"] == "run"
    assert _member(blob, "runs/solo/preset.yaml") == text.encode("utf-8")
    assert b"!!python" not in blob
    shutil.rmtree(runs / "solo")
    poisoned = (text + "!!python/object/apply:os.system ['echo pwned']\n").encode("utf-8")
    # 预设字节原样进包。导入时不解析 YAML，所以标签还在文件里，没有被执行。
    blob = _swap_preset(blob, poisoned)
    imported = import_zip_bytes(blob, filename="solo.deckbench.zip")
    assert imported["runs"][0]["id"] == "solo"
    stored = (runs / "solo" / "preset.yaml").read_bytes()
    assert stored.startswith(b"name: probe")
    assert b"os.system" in stored
    assert not (tmp_path / "data" / "presets" / "solo.yaml").exists()


def _swap_preset(blob, new_preset):
    """换成另一份预设字节，并按新内容重算清单。用来证明导入不解析 YAML。"""
    import sts2sim
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        files = {name: zf.read(name) for name in zf.namelist() if name != "manifest.json"}
    files["runs/solo/preset.yaml"] = new_preset
    manifest = json.loads(_manifest_from(files, kind="run", runs=["solo"], version=sts2sim.__version__))
    return _zip_with(manifest, files)


def _manifest_from(files, *, kind, runs, version):
    listed = []
    for path in sorted(files):
        data = files[path]
        listed.append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return json.dumps({
        "format": "deckbench.bundle",
        "schema": SCHEMA,
        "deckbench": version,
        "kind": kind,
        "created": "2026-01-02T00:00:00+00:00",
        "runs": runs,
        "files": listed,
    }, ensure_ascii=False).encode("utf-8")


def _zip_with(manifest_doc, files):
    if isinstance(manifest_doc, dict):
        manifest_doc = json.dumps(manifest_doc, ensure_ascii=False).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_doc)
        for path in sorted(files):
            archive.writestr(path, files[path])
    return buf.getvalue()


def test_tampered_hash_is_rejected_and_writes_nothing(client, runs):
    _combat(str(runs), "solo", _rows(3, 5, 4, 2, "Elite"), "Solo")
    blob = export_run_bytes("solo", lang="en")[0]
    before = set(os.listdir(runs))
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        files = {name: zf.read(name) for name in zf.namelist() if name != "manifest.json"}
        manifest = json.loads(zf.read("manifest.json"))
    raw = bytearray(files["runs/solo/raw.jsonl"])
    raw[0] = (raw[0] + 1) % 256
    files["runs/solo/raw.jsonl"] = bytes(raw)
    tampered = _zip_with(manifest, files)
    outside = runs.parent / "tampered-wrote.txt"
    with pytest.raises(BundleError) as caught:
        import_zip_bytes(tampered, filename="tampered.deckbench.zip")
    assert caught.value.code == "hash"
    assert set(os.listdir(runs)) == before
    assert not outside.exists()
    res = client.post(
        "/api/bundles/import",
        headers=EN,
        files={"file": ("tampered.deckbench.zip", tampered, "application/zip")},
    )
    assert res.status_code == 400
    detail = _detail(res)
    assert "SHA-256" in detail
    assert set(os.listdir(runs)) == before


def test_zip_slip_and_absolute_paths_are_rejected(runs, tmp_path):
    outside = tmp_path / "evil.txt"
    slip = tmp_path / "nested" / "evil.txt"
    absolute = "/tmp/deckbench-slip-not-created.txt"
    for name in ("../evil.txt", "runs/solo/../../evil.txt", absolute, "C:/evil.txt", "runs\\solo\\meta.json"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            info = zipfile.ZipInfo(name)
            archive.writestr(info, b"pwned")
            archive.writestr("manifest.json", b'{"schema": 1}')
        stored = zipfile.ZipFile(io.BytesIO(buf.getvalue())).namelist()
        with pytest.raises(BundleError) as caught:
            import_zip_bytes(buf.getvalue())
        assert caught.value.code == "zip_slip", (name, stored, caught.value.code)
        assert not outside.exists()
        assert not slip.exists()
        assert not os.path.exists(absolute)
    assert list(runs.iterdir()) == []


def test_extra_file_is_rejected_and_not_executed(runs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("manifest.json", b'{"schema": 1}')
        archive.writestr("pwn.py", b"import os\nos.system('echo pwned')\n")
    with pytest.raises(BundleError) as caught:
        import_zip_bytes(buf.getvalue())
    assert caught.value.code == "extra"
    assert list(runs.iterdir()) == []


def test_incompatible_schema_is_a_clear_message(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"schema": 2, "format": "deckbench.bundle"}).encode())
    res = client.post(
        "/api/bundles/import",
        headers=EN,
        files={"file": (SECRET + ".zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 400
    detail = _detail(res)
    assert "schema 2" in detail
    assert "schema 1" in detail
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"schema": "nope"}).encode())
    res = client.post(
        "/api/bundles/import",
        headers=EN,
        files={"file": ("x.deckbench.zip", bad.getvalue(), "application/zip")},
    )
    assert res.status_code == 400
    detail = _detail(res)
    assert "nope" not in detail
    assert "schema 1" in detail


def test_oversized_member_is_rejected(monkeypatch):
    monkeypatch.setattr("sts2sim.bundle.MAX_MEMBER", 32)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("manifest.json", b'{"schema": 1}')
        archive.writestr("report.html", b"x" * 64)
    with pytest.raises(BundleError) as caught:
        import_zip_bytes(buf.getvalue())
    assert caught.value.code == "too_big"


def test_head_to_head_and_card_impact_bundle(client, runs):
    _combat(str(runs), "left", _rows(2, 8, 5, 1, "Monster"), "Head A", shared=True)
    _combat(str(runs), "right", _rows(5, 3, 4, 2, "Monster"), "Head B", shared=True)
    blob, _name = export_compare_bytes("left", "right", lang="en")
    assert _manifest(blob)["kind"] == "head_to_head"

    parent = runs / "impact"
    parent.mkdir()
    child_a = "impact-a"
    child_b = "impact-b"
    _combat(str(runs), child_a, _rows(2, 9, 5, 1, "Elite"), "Baseline card")
    _combat(str(runs), child_b, _rows(4, 4, 4, 3, "Elite"), "Without one")
    doc = {
        "ok": True, "method": "leave_one_out", "id": "impact", "job": "impact",
        "deck": "probe", "status": "done", "partial": False,
        "baseline": {"run": child_a, "n": 8, "win_rate": 0.25},
        "rows": [{"run": child_b, "card_id": "STRIKE", "delta_win": 0.25, "noisy": True}],
        "runs": [
            {"id": child_a, "role": "baseline", "change": "baseline", "status": "done"},
            {"id": child_b, "role": "variant", "change": "remove", "card_id": "STRIKE", "status": "done"},
        ],
    }
    (parent / "card_impact.json").write_text(json.dumps(doc), encoding="utf-8")
    (parent / "meta.json").write_text(json.dumps({
        "id": "impact", "kind": "card_impact", "title": "Impact job", "status": "done",
        "created": "2026-01-02T00:00:00+00:00", "params": {"deck": "probe", "preset": "probe", "seed": 1},
    }), encoding="utf-8")
    exported = client.get("/api/runs/impact/bundle", headers=EN)
    assert exported.status_code == 200, exported.text[:400]
    packed = _manifest(exported.content)
    assert packed["kind"] == "card_impact"
    assert packed["runs"][0] == "impact"
    assert "runs/impact-a/raw.jsonl" in _names(exported.content)
    assert "runs/impact-b/raw.jsonl" in _names(exported.content)
    for rid in ("impact", child_a, child_b):
        shutil.rmtree(runs / rid)
    imported = import_zip_bytes(exported.content, filename="impact.deckbench.zip")
    assert [row["renamed"] for row in imported["runs"]] == [False, False, False]
    saved = json.loads((runs / "impact" / "card_impact.json").read_text(encoding="utf-8"))
    assert saved["rows"][0]["delta_win"] == 0.25
    assert saved["runs"][0]["id"] == child_a
    assert saved["baseline"]["run"] == child_a
    assert (runs / child_b / "out" / "raw.jsonl").is_file()


def test_mcp_export_and_import_round_trip(runs, tmp_path):
    _combat(str(runs), "base", _rows(2, 12, 6, 1, "Monster"), "Baseline")
    _combat(str(runs), "changed", _rows(6, 4, 3, 4, "Monster"), "Changed")
    dest = tmp_path / "data" / "exports" / "pair.deckbench.zip"
    doc = json.loads(export_bundle_json(a="base", b="changed", out=str(dest), lang="en"))
    assert doc["ok"] is True and doc["path"] == str(dest.resolve())
    assert dest.is_file()
    shutil.rmtree(runs / "base")
    shutil.rmtree(runs / "changed")
    imported = json.loads(import_bundle_json(str(dest)))
    assert imported["ok"] is True
    assert [row["id"] for row in imported["runs"]] == ["base", "changed"]
    refused = json.loads(export_bundle_json(run="base", out=str(tmp_path / "data" / "saves" / "out.deckbench.zip")))
    assert refused["ok"] is False and refused["error"] == "refuse_write"
    assert "Traceback" not in refused["message"]
    missing = json.loads(import_bundle_json(str(tmp_path / "missing.deckbench.zip")))
    assert missing["ok"] is False and missing["error"] in ("not_found", "path_not_allowed")
    assert "message" in missing and "Traceback" not in missing["message"]
