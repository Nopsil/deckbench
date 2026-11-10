"""#/explain 走的 HTTP 接口。夹具日志，不新开模拟，不写文件。"""
import json
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from gui.server import app  # noqa: E402
from sts2sim.analysis import CLOSE_GAP, explain_fight_json  # noqa: E402

EN = {"x-lang": "en"}
ZH = {"x-lang": "zhs"}


@pytest.fixture
def allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    monkeypatch.setenv("DECKBENCH_ANALYSIS_ROOTS", "")
    monkeypatch.setenv("DECKBENCH_CACHE", str(tmp_path / "no-cache"))
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "no-mcp"))
    return tmp_path


@pytest.fixture
def client(allowed):
    with TestClient(app) as c:
        yield c


def _write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _row(seq, kind, seed, fight, floor, turn, chosen, candidates, **extra):
    row = {
        "v": 1, "seq": seq, "kind": kind, "seed": seed, "char": "Ironclad",
        "fight": fight, "floor": floor, "act": 1, "room": "Monster", "encounter": "ENCOUNTER.SAMPLE",
        "chosen": chosen, "candidates": candidates,
    }
    if turn is not None:
        row["turn"] = turn
    row.update(extra)
    return row


def _sample():
    strike = {"id": "STRIKE", "name": "STRIKE", "score": 3.2}
    defend_close = {"id": "DEFEND", "name": "DEFEND", "score": 3.0}
    bash = {"id": "BASH", "name": "BASH", "score": 8}
    defend_low = {"id": "DEFEND", "name": "DEFEND", "score": 1}
    tie_a = {"id": "STRIKE", "name": "STRIKE", "score": 2}
    tie_b = {"id": "DEFEND", "name": "DEFEND", "score": 2}
    only = {"id": "STRIKE", "name": "STRIKE", "score": 4}
    behind = {"id": "DEFEND", "name": "DEFEND", "score": 1}
    ahead = {"id": "BASH", "name": "BASH", "score": 2}
    rows = [
        _row(1, "play", "S", 1, 2, 1, strike, [strike, defend_close]),
        _row(2, "play", "S", 1, 2, 2, bash, [bash, defend_low]),
        _row(3, "play", "S", 1, 2, 3, tie_a, [tie_a, tie_b]),
        _row(4, "play", "S", 1, 2, 4, only, [only]),
        _row(5, "play", "S", 1, 2, 5, behind, [behind, ahead]),
        _row(6, "reward", "S", 1, 2, None, {"id": "skip", "name": "skip", "score": 4},
             [{"id": "STRIKE", "name": "STRIKE", "score": 3}, {"id": "skip", "name": "skip", "score": 4}]),
        _row(7, "shop", "S", 1, 2, None,
             [{"id": "A", "name": "A", "score": 5}, {"id": "B", "name": "B", "score": 4.8}],
             [{"id": "A", "name": "A", "score": 5}, {"id": "B", "name": "B", "score": 4.8},
              {"id": "C", "name": "C", "score": 4.7}]),
        _row(8, "play", "S", 2, 3, 1, {"id": "DEFEND", "name": "DEFEND", "score": 1},
             [{"id": "DEFEND", "name": "DEFEND", "score": 1}]),
        _row(9, "play", "OTHER", 1, 2, 1, {"id": "NO", "name": "NO", "score": 1},
             [{"id": "NO", "name": "NO", "score": 1}, {"id": "X", "name": "X", "score": 0}]),
    ]
    return rows


def _names(root):
    out = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames.sort()
        for name in sorted(names):
            out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return out


def test_catalog_and_page_match_explain_fight_and_do_not_write(client, allowed):
    log = allowed / "runs.explain.jsonl"
    _write(log, _sample())
    before = log.read_bytes()
    names = _names(allowed)

    opened = client.post("/api/explain", headers=EN, json={"path": str(log)})
    assert opened.status_code == 200, opened.text
    catalog = opened.json()
    assert catalog["ok"] is True and catalog["read_only"] is True
    assert catalog["path"] == str(log.resolve())
    assert [r["seed"] for r in catalog["runs"]] == ["S", "OTHER"]
    assert catalog["runs"][0]["char"] == "Ironclad"
    fights = catalog["runs"][0]["fights"]
    assert [f["fight"] for f in fights] == [0, 1]
    assert fights[0]["where"]["floor"] == 2 and fights[0]["where"]["encounter"] == "ENCOUNTER.SAMPLE"
    assert fights[0]["turns"] == [1, 2, 3, 4, 5]
    raw0 = json.loads(explain_fight_json(str(log), 0, "S"))
    raw1 = json.loads(explain_fight_json(str(log), 1, "S"))
    assert fights[0]["decisions"] == raw0["total"] == 7
    assert fights[1]["decisions"] == raw1["total"] == 1
    assert "NO" not in json.dumps(raw0["decisions"])

    page = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "seed": "S", "fight": 0, "offset": 0, "limit": 20})
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["read_only"] is True and body["close_gap"] == CLOSE_GAP == 0.5
    assert body["total"] == raw0["total"] and body["offset"] == 0 and body["next_offset"] is None
    assert [d["seq"] for d in body["decisions"]] == [d["seq"] for d in raw0["decisions"]]
    for got, want in zip(body["decisions"], raw0["decisions"]):
        for key, value in want.items():
            assert got[key] == value
        assert "margin" in got and "close" in got

    close, clear, tie, only, behind, reward, shop = body["decisions"]
    assert close["margin"] == pytest.approx(0.2) and close["close"] is True
    assert close["runner_up"]["id"] == "DEFEND"
    assert clear["margin"] == pytest.approx(7) and clear["close"] is False
    assert tie["margin"] == pytest.approx(0) and tie["close"] is True
    assert only["margin"] is None and only["close"] is False and only["runner_up"] is None
    assert behind["margin"] == pytest.approx(-1) and behind["close"] is False
    assert reward["kind"] == "reward" and reward["margin"] == pytest.approx(1)
    assert shop["kind"] == "shop" and shop["margin"] == pytest.approx(0.1) and shop["close"] is True
    assert shop["runner_up"]["id"] == "C" and shop["chosen_score"] == pytest.approx(4.8)

    second = client.post("/api/explain/fight", headers=EN, json={"path": str(allowed), "seed": "OTHER", "fight": 0})
    assert second.status_code == 200, second.text
    assert second.json()["decisions"][0]["chosen"]["id"] == "NO"
    assert "STRIKE" not in json.dumps(second.json()["decisions"])

    assert log.read_bytes() == before
    assert _names(allowed) == names


def test_fight_page_reuses_explain_fight_pagination(client, allowed):
    log = allowed / "explain.jsonl"
    _write(log, _sample())
    raw = json.loads(explain_fight_json(str(log), fight=0, seed="S", offset=1, limit=1))
    res = client.post("/api/explain/fight", headers=EN, json={
        "path": str(log), "seed": "S", "fight": 0, "offset": 1, "limit": 1,
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["offset"] == 1 and body["limit"] == 1 and body["next_offset"] == 2 and body["total"] == raw["total"]
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["seq"] == raw["decisions"][0]["seq"] == 2
    assert body["decisions"][0]["candidates"] == raw["decisions"][0]["candidates"]
    assert body["decisions"][0]["close"] is False

    wide = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "seed": "S", "fight": 0, "limit": 1000})
    assert wide.status_code == 200
    assert wide.json()["limit"] == 100 and len(wide.json()["decisions"]) == 7


def test_paths_outside_allowed_roots_and_save_trees_are_refused(client, allowed):
    outside = allowed.parent / "outside-explain.jsonl"
    outside.write_text('{"secret":"do-not-read","kind":"play","chosen":{"id":"A","score":1},"candidates":[]}\n', encoding="utf-8")
    outside_bytes = outside.read_bytes()
    sentinel = b"SENTINEL-save-bytes"
    save = allowed / "sample.run"
    save.write_bytes(sentinel)
    hist = allowed / "history"
    hist.mkdir()
    hidden = hist / "x.explain.jsonl"
    hidden.write_text('{"kind":"play","secret":"save-tree","chosen":{"id":"A","score":1},"candidates":[]}\n', encoding="utf-8")
    link = allowed / "escape.explain.jsonl"
    link.symlink_to(outside)
    before = _names(allowed)

    denied = client.post("/api/explain", headers=EN, json={"path": str(outside)})
    assert denied.status_code == 400
    assert denied.json()["detail"].startswith("This path is outside the allowed folders")
    assert "do-not-read" not in denied.text
    zh = client.post("/api/explain", headers=ZH, json={"path": str(outside)})
    assert zh.status_code == 400
    assert zh.json()["detail"].startswith("这个路径不在允许的目录里")

    escaped = client.post("/api/explain/fight", headers=EN, json={"path": str(link)})
    assert escaped.status_code == 400
    assert escaped.json()["detail"].startswith("This path is outside the allowed folders")
    assert "do-not-read" not in escaped.text

    refused = client.post("/api/explain", headers=EN, json={"path": str(save)})
    assert refused.status_code == 400
    assert refused.json()["detail"].startswith("Refusing to read inside a save folder")
    assert b"SENTINEL" not in refused.content
    assert save.read_bytes() == sentinel

    listed = client.get("/api/explain/logs", headers=EN)
    assert listed.status_code == 200, listed.text
    paths = [item["path"] for item in listed.json()["logs"]]
    assert listed.json()["read_only"] is True
    assert str(hidden.resolve()) not in paths
    assert "save-tree" not in listed.text
    assert str(link.resolve()) not in paths
    assert all(not p.endswith(".run") for p in paths)

    assert outside.read_bytes() == outside_bytes
    assert _names(allowed) == before


def test_log_list_finds_explain_files_only(client, allowed):
    _write(allowed / "explain.jsonl", _sample()[:1])
    _write(allowed / "runs.explain.jsonl", _sample()[:1])
    (allowed / "runs.jsonl").write_text('{"floor":1,"victory":true,"combats":[]}\n', encoding="utf-8")
    nested = allowed / "runs" / "r1"
    nested.mkdir(parents=True)
    _write(nested / "explain.jsonl", _sample()[:1])
    before = _names(allowed)

    res = client.get("/api/explain/logs", headers=EN)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True and body["read_only"] is True and body["truncated"] is False
    names = sorted(item["name"] for item in body["logs"])
    assert names == ["explain.jsonl", "explain.jsonl", "runs.explain.jsonl"]
    assert all(item["path"].endswith(item["name"]) for item in body["logs"])
    assert not any(item["name"] == "runs.jsonl" for item in body["logs"])
    assert _names(allowed) == before

    opened = client.post("/api/explain", headers=EN, json={"path": str(nested)})
    assert opened.status_code == 200, opened.text
    assert opened.json()["path"].endswith(os.path.join("r1", "explain.jsonl"))
    assert opened.json()["runs"][0]["seed"] == "S"


def test_bad_logs_stay_errors_and_do_not_write(client, allowed):
    junk = allowed / "junk.explain.jsonl"
    junk.write_text("{not-json}\n", encoding="utf-8")
    plain = allowed / "plain.jsonl"
    plain.write_text('{"floor": 1}\n', encoding="utf-8")
    many = allowed / "many"
    many.mkdir()
    _write(many / "a.explain.jsonl", _sample()[:1])
    _write(many / "b.explain.jsonl", _sample()[:1])
    good = allowed / "explain.jsonl"
    _write(good, _sample()[:1])
    before = _names(allowed)

    broken = client.post("/api/explain", headers=EN, json={"path": str(junk)})
    assert broken.status_code == 400
    assert broken.json()["detail"] == "Line 1 is not JSON."
    zh = client.post("/api/explain", headers=ZH, json={"path": str(junk)})
    assert zh.json()["detail"] == "第 1 行不是 JSON。"

    not_log = client.post("/api/explain/fight", headers=EN, json={"path": str(plain)})
    assert not_log.status_code == 400
    assert not_log.json()["detail"].startswith("This is not an --explain decision log")

    amb = client.post("/api/explain", headers=EN, json={"path": str(many)})
    assert amb.status_code == 400
    assert "2 explanation logs" in amb.json()["detail"]

    missing = client.post("/api/explain", headers=EN, json={"path": ""})
    assert missing.status_code == 400
    assert missing.json()["detail"] == "Enter the path to an explanation log."

    late = client.post("/api/explain/fight", headers=EN, json={"path": str(good), "fight": 3})
    assert late.status_code == 400
    assert late.json()["detail"].startswith("No fight 3")
    bad_limit = client.post("/api/explain/fight", headers=EN, json={"path": str(good), "limit": 0})
    assert bad_limit.status_code == 400
    assert bad_limit.json()["detail"] == "Page size must be at least 1."
    assert _names(allowed) == before


def test_candidate_mechanic_notes_are_kept_for_the_page(client, allowed):
    """thorns:N / armour / incoming:... 写在候选 note 上，分页结果原样带上，不另打分。"""
    log = allowed / "explain.jsonl"
    strike = {"id": "STRIKE", "name": "STRIKE", "score": 3.2, "note": "thorns:16"}
    defend = {"id": "DEFEND", "name": "DEFEND", "score": 3.0, "note": "armour"}
    bash = {"id": "BASH", "name": "BASH", "score": 1.0, "note": "incoming:20>0x2+unknown"}
    _write(log, [_row(1, "play", "S", 1, 2, 1, strike, [strike, defend, bash])])
    before = log.read_bytes()
    res = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "seed": "S", "fight": 0})
    assert res.status_code == 200, res.text
    decision = res.json()["decisions"][0]
    notes = {c["id"]: c.get("note") for c in decision["candidates"]}
    assert notes["STRIKE"] == "thorns:16"
    assert notes["DEFEND"] == "armour"
    assert notes["BASH"] == "incoming:20>0x2+unknown"
    assert decision["chosen"]["note"] == "thorns:16"
    assert decision["candidates"][0]["picked"] is True
    assert log.read_bytes() == before


def test_unseeded_log_is_one_run(client, allowed):
    log = allowed / "explain.jsonl"
    _write(log, [{
        "v": 1, "seq": 1, "kind": "play", "floor": 1, "turn": 1,
        "chosen": {"id": "STRIKE", "score": 1.1},
        "candidates": [{"id": "STRIKE", "score": 1.1}, {"id": "DEFEND", "score": 1.0}],
    }])
    opened = client.post("/api/explain", headers=EN, json={"path": str(log)})
    assert opened.status_code == 200, opened.text
    runs = opened.json()["runs"]
    assert len(runs) == 1 and runs[0]["seed"] is None and len(runs[0]["fights"]) == 1
    page = client.post("/api/explain/fight", headers=EN, json={"path": str(log), "seed": "", "fight": 0})
    assert page.status_code == 200, page.text
    decision = page.json()["decisions"][0]
    assert decision["margin"] == pytest.approx(0.1) and decision["close"] is True
    assert page.json()["seed"] is None
