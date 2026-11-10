"""POST /api/gap_triage 和命令行读的是同一份汇总。不新开模拟，不写校准 JSON。"""
import importlib.util
import json
import os
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from gui.server import app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "gap_triage")
REAL = os.path.join(ROOT, "tests", "fixtures", "calibrate", "real.run")
SIMS = os.path.join(ROOT, "tests", "fixtures", "calibrate", "sims.jsonl")
EN = {"x-lang": "en"}


def _mod():
    name = "deckbench_gap_triage_api_test"
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", "gap_triage.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _ids(rows):
    return [row["id"] for row in rows]


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    monkeypatch.setenv("DECKBENCH_SAVE_ROOTS", str(tmp_path / "no-saves"))
    return tmp_path


@pytest.fixture
def client(allowed):
    with TestClient(app) as c:
        yield c


def test_restricted_false_matches_the_cli_on_the_fixture_directory():
    mod = _mod()
    cli = mod.analyze([FIX], os.path.join(FIX, "catalog.json"))
    body = mod.run_triage(
        paths=[FIX], catalog=os.path.join(FIX, "catalog.json"), restricted=False,
    )
    assert body["counts"] == cli["counts"]
    assert _ids(body["encounters"]["optimistic"]) == _ids(cli["encounters"]["optimistic"])
    assert _ids(body["encounters"]["pessimistic"]) == _ids(cli["encounters"]["pessimistic"])
    assert _ids(body["by_power"]) == _ids(cli["by_power"])
    assert _ids(body["top_gaps"]) == _ids(cli["top_gaps"])
    assert body["notes"] == cli["notes"]


def test_http_ranks_fixture_json_and_inline_reports_the_same_way(client, allowed):
    mod = _mod()
    folder = allowed / "gaps"
    folder.mkdir()
    names = ("a_one.json", "b_two.json", "catalog.json", "skip.json")
    for name in names:
        target = folder / name
        target.write_text(_read(os.path.join(FIX, name)), encoding="utf-8")
    before = {name: (folder / name).read_bytes() for name in names}
    catalog = str(folder / "catalog.json")
    cli = mod.analyze([str(folder / "a_one.json"), str(folder / "b_two.json")], catalog)

    by_path = client.post(
        "/api/gap_triage", headers=EN,
        json={"paths": [str(folder / "a_one.json"), str(folder / "b_two.json")], "catalog": catalog},
    )
    assert by_path.status_code == 200, by_path.text
    body = by_path.json()
    assert body["ok"] is True and body["read_only"] is True
    assert body["counts"] == cli["counts"]
    assert _ids(body["encounters"]["optimistic"]) == ["SAMPLE_ELITE", "SAMPLE_WIDE"]
    assert _ids(body["by_power"]) == _ids(cli["by_power"])
    constrict = next(row for row in body["by_power"] if row["id"] == "CONSTRICT")
    assert constrict["lean"] == "optimistic"
    assert constrict["code"][0]["file"] == "sts2sim/powers_enemy.py"
    assert constrict["code"][0]["symbol"] == "Constrict"

    reports = [json.loads(_read(os.path.join(FIX, name))) for name in ("a_one.json", "b_two.json")]
    inline = client.post(
        "/api/gap_triage", headers=EN, json={"reports": reports, "catalog": catalog},
    )
    assert inline.status_code == 200, inline.text
    assert inline.json()["counts"] == body["counts"]
    assert _ids(inline.json()["by_power"]) == _ids(body["by_power"])
    assert any(item["name"] == "request" for item in inline.json()["sources"])
    assert {name: (folder / name).read_bytes() for name in names} == before


def _bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_http_accepts_the_calibrate_response_as_the_whole_body(client, allowed):
    sim = allowed / "runs.jsonl"
    sim.write_bytes(_bytes(SIMS))
    before = _bytes(REAL)
    cal = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sim)})
    assert cal.status_code == 200, cal.text
    report = cal.json()
    as_field = client.post("/api/gap_triage", headers=EN, json={"reports": report})
    bare = client.post("/api/gap_triage", headers=EN, json=report)
    listed = client.post("/api/gap_triage", headers=EN, json=[report])
    assert as_field.status_code == 200, as_field.text
    assert bare.status_code == 200, bare.text
    assert listed.status_code == 200, listed.text
    for res in (as_field, bare, listed):
        body = res.json()
        assert body["read_only"] is True
        assert _ids(body["encounters"]["optimistic"]) == ["SAMPLE_ELITE"]
        assert body["encounters"]["pessimistic"] == []
        code = body["encounters"]["optimistic"][0]["code"]
        assert [item["file"] for item in code] == [
            "sts2sim/powers_enemy.py",
            "sts2sim/powers.py",
            "sts2sim/enemies.py",
        ]
    assert _bytes(REAL) == before
    assert sim.read_bytes() == _bytes(SIMS)


def test_mcp_json_matches_http_for_one_report(allowed):
    mod = _mod()
    path = os.path.join(ROOT, "tools", "mcp_server.py")
    spec = importlib.util.spec_from_file_location("deckbench_mcp_gap_under_test", path)
    mcp = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mcp
    spec.loader.exec_module(mcp)
    report = json.loads(_read(os.path.join(FIX, "a_one.json")))
    text = mcp.gap_triage(reports=json.dumps(report))
    body = json.loads(text)
    direct = mod.run_triage(reports=[report], restricted=True)
    assert body["ok"] is True and body["read_only"] is True
    assert body["counts"] == direct["counts"]
    assert _ids(body["encounters"]["optimistic"]) == _ids(direct["encounters"]["optimistic"])
    assert "Traceback" not in text
