"""#/calibrate 走的 HTTP 接口。夹具对局，不新开模拟，不写文件。

fastapi / httpx 没装时整份跳过。
"""
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from gui.server import app  # noqa: E402
from sts2sim.calibrate import calibrate_paths  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "tests", "fixtures", "calibrate", "real.run")
SIMS = os.path.join(ROOT, "tests", "fixtures", "calibrate", "sims.jsonl")
PAGE = os.path.join(ROOT, "gui", "web", "src", "pages", "Calibrate.vue")
EN = {"x-lang": "en"}
ZH = {"x-lang": "zhs"}
FIELDS = (
    "floor", "room", "encounter", "real_hp_lost", "mean", "p10", "p90",
    "percentile", "likely_sim_gap", "status", "reason",
)


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


def _only_here(path):
    def roots():
        return [str(path)]
    return roots


def _files(root):
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, names in os.walk(root):
        dirnames.sort()
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                out[rel] = ("link", os.readlink(path))
            elif os.path.isfile(path):
                with open(path, "rb") as fh:
                    out[rel] = ("file", fh.read())
    return out


def test_page_lists_the_table_the_gap_flag_and_the_strip():
    src = open(PAGE, encoding="utf-8").read()
    main = open(os.path.join(ROOT, "gui", "web", "src", "main.js"), encoding="utf-8").read()
    nav = open(os.path.join(ROOT, "gui", "web", "src", "App.vue"), encoding="utf-8").read()
    assert "/calibrate" in main and "Calibrate" in main
    assert "nav.calibrate" in nav and "/calibrate" in nav
    for key in (
        "cal.floor", "cal.room", "cal.encounter", "cal.realHp", "cal.mean",
        "cal.p10", "cal.p90", "cal.percentile", "cal.gap", "cal.band",
    ):
        assert key in src
    assert "likely_sim_gap" in src
    assert "unmatched" in src
    assert "<svg" in src and "cal.reason." in src
    assert "/api/calibrate/upload" in src
    assert "/api/calibrate/reals" in src and "/api/calibrate/sims" in src
    assert 'data-section="gap-triage"' in src
    assert "/api/gap_triage" in src
    assert "data-gap-side=\"optimistic\"" in src
    assert "data-gap-side=\"pessimistic\"" in src
    assert "data-gap-side=\"power\"" in src
    for key in (
        "cal.triageTitle", "cal.triageOptimistic", "cal.triagePessimistic",
        "cal.triageByPower", "cal.triageCode", "cal.triageReadOnly",
    ):
        assert key in src


def test_compare_returns_the_table_fields_and_does_not_write(client, allowed):
    sim = allowed / "runs.jsonl"
    sim.write_bytes(open(SIMS, "rb").read())
    before_real = open(REAL, "rb").read()
    before_sim = sim.read_bytes()
    before_tree = _files(allowed)
    res = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(sim)})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["read_only"] is True
    by = {row["floor"]: row for row in body["fights"]}
    for row in body["fights"]:
        for key in FIELDS:
            assert key in row
    elite = by[4]
    assert elite["likely_sim_gap"] is True
    assert elite["room"] == "Elite" and elite["encounter"] == "SAMPLE_ELITE"
    assert elite["real_hp_lost"] == 50 and elite["mean"] == 20
    assert elite["p10"] == 4 and elite["p90"] == 36 and elite["percentile"] == 100
    monster = by[2]
    assert monster["likely_sim_gap"] is False and monster["real_hp_lost"] == 10
    assert monster["p10"] == 4 and monster["p90"] == 36
    assert by[5]["status"] == "unmatched" and by[5]["reason"] == "missing_hp"
    assert by[6]["status"] == "unmatched" and by[6]["reason"] == "missing_encounter"
    assert by[1]["status"] == "not_a_fight"
    assert open(REAL, "rb").read() == before_real
    assert sim.read_bytes() == before_sim
    assert _files(allowed) == before_tree


def test_upload_matches_the_path_report_without_an_allowed_sim_path(client, allowed, tmp_path):
    outside = tmp_path.parent / "calibrate-outside"
    outside.mkdir(exist_ok=True)
    stray = outside / "sims.jsonl"
    stray.write_bytes(open(SIMS, "rb").read())
    before = _files(allowed)
    before_real = open(REAL, "rb").read()
    res = client.post(
        "/api/calibrate/upload",
        headers=EN,
        data={"real": REAL},
        files={"file": ("sims.jsonl", stray.read_bytes(), "application/octet-stream")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    direct = calibrate_paths(REAL, str(stray), restricted=False)
    assert body["fights"] == direct["fights"]
    assert body["sim_matched"] == direct["sim_matched"]
    assert body["gaps"] == [4] and body["unmatched"] == [5, 6]
    assert body["sim_path"] == "sims.jsonl"
    assert {row["floor"]: row for row in body["fights"]}[4]["likely_sim_gap"] is True
    refused = client.post("/api/calibrate", headers=EN, json={"real": REAL, "sim": str(stray)})
    assert refused.status_code == 400
    assert open(REAL, "rb").read() == before_real
    assert stray.read_bytes() == open(SIMS, "rb").read()
    assert _files(allowed) == before
    assert not (outside / "sims.jsonl.upload").exists()


def test_upload_errors_stay_translated_and_write_nothing(client, allowed, monkeypatch):
    missing = client.post(
        "/api/calibrate/upload",
        headers=EN,
        data={"real": ""},
        files={"file": ("runs.jsonl", b"{}\n", "application/octet-stream")},
    )
    assert missing.status_code == 400 and "real run" in missing.text.lower()
    zh = client.post(
        "/api/calibrate/upload",
        headers=ZH,
        data={"real": ""},
        files={"file": ("runs.jsonl", b"{}\n", "application/octet-stream")},
    )
    assert zh.status_code == 400 and "真对局" in zh.text
    broken = client.post(
        "/api/calibrate/upload",
        headers=EN,
        data={"real": REAL},
        files={"file": ("runs.jsonl", b"not-json\n", "application/octet-stream")},
    )
    assert broken.status_code == 400 and "not JSON" in broken.text
    folder = client.post(
        "/api/calibrate/upload",
        headers=EN,
        data={"real": os.path.join(ROOT, "tests", "fixtures", "saves")},
        files={"file": ("runs.jsonl", open(SIMS, "rb").read(), "application/octet-stream")},
    )
    assert folder.status_code == 400 and "one run file" in folder.text.lower()
    monkeypatch.setattr("sts2sim.saveimport.MAX_BYTES", 4)
    huge = client.post(
        "/api/calibrate/upload",
        headers=EN,
        data={"real": REAL},
        files={"file": ("runs.jsonl", b"12345", "application/octet-stream")},
    )
    assert huge.status_code == 400 and "32" in huge.text
    assert _files(allowed) == {}


def test_real_and_sim_lists_are_paths_only(client, allowed, monkeypatch):
    game = allowed / "SlayTheSpire2"
    hist = game / "saves" / "history"
    hist.mkdir(parents=True)
    run = hist / "sample.run"
    run.write_bytes(open(REAL, "rb").read())
    (hist / "notes.txt").write_text("nope", encoding="utf-8")
    (hist / "sample.run.backup").write_text("{}", encoding="utf-8")
    current = game / "saves" / "current_run.save"
    current.write_bytes(open(REAL, "rb").read())
    junk = allowed / "not-a-run.run"
    junk.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sts2sim.saveimport.candidate_roots", _only_here(game))
    before = run.read_bytes()
    listed = client.get("/api/calibrate/reals", headers=EN)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["read_only"] is True
    paths = {item["path"] for item in body["runs"]}
    assert os.path.realpath(run) in paths
    assert os.path.realpath(current) in paths
    assert all(set(item) == {"path", "name"} for item in body["runs"])
    assert run.read_bytes() == before
    assert os.path.realpath(junk) not in paths

    sim = allowed / "batch" / "runs.jsonl"
    sim.parent.mkdir()
    sim.write_bytes(open(SIMS, "rb").read())
    (allowed / "sims.jsonl").write_bytes(open(SIMS, "rb").read())
    hidden = allowed / "history"
    hidden.mkdir()
    (hidden / "runs.jsonl").write_text("{}\n", encoding="utf-8")
    outside = allowed.parent / "runs.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    link_dir = allowed / "linked"
    link_dir.mkdir()
    os.symlink(outside, link_dir / "runs.jsonl")
    sims = client.get("/api/calibrate/sims", headers=EN)
    assert sims.status_code == 200, sims.text
    found = {item["path"] for item in sims.json()["sims"]}
    assert os.path.realpath(sim) in found
    assert os.path.realpath(allowed / "sims.jsonl") not in found
    assert os.path.realpath(hidden / "runs.jsonl") not in found
    assert os.path.realpath(outside) not in found
    assert sim.read_bytes() == open(SIMS, "rb").read()
