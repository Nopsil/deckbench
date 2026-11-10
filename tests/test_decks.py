"""牌组页的 HTTP / MCP：只读牌池，预设只写用户目录。

坏 id、目录外、符号链接、超限、缺字段、类型不对都是 4xx 或 ok:false，正文没有堆栈。
不改出厂预设、mods、种子和 AI。
"""
import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = {"x-lang": "en"}
ZHS = {"x-lang": "zhs"}
SECRET = "SECRET-DO-NOT-LEAK"
QUICK = os.path.join(ROOT, "experiments", "quick.yaml")
SHIPPED_DECKS = os.path.join(ROOT, "mods", "claude_v34", "decks.yaml")


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _detail(res):
    body = res.json()
    assert isinstance(body.get("detail"), str)
    assert "Traceback" not in res.text
    assert SECRET not in res.text
    return body["detail"]


def _payload(pid="tdeck", cards=None):
    return {
        "id": pid,
        "name": "Test deck",
        "mod": "claude_v34",
        "cards": cards or [
            {"id": "YIHESHI", "count": 1, "upgrade": True},
            {"id": "XIAOBENBEN", "count": 2, "upgrade": False},
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


def test_cards_are_filtered_in_both_languages(client):
    page = client.get("/api/cards", headers=EN, params={"limit": 2, "offset": 0})
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["limit"] == 2 and body["offset"] == 0
    assert body["total"] > 2
    assert len(body["cards"]) == 2
    nxt = client.get("/api/cards", headers=EN, params={"limit": 2, "offset": 2})
    assert nxt.json()["cards"][0]["id"] != body["cards"][0]["id"]

    zh = client.get("/api/cards", headers=ZHS, params={"q": "已核实", "limit": 50})
    assert zh.status_code == 200
    assert any(card["id"] == "YIHESHI" and card["name_zh"] == "已核实" for card in zh.json()["cards"])
    en = client.get("/api/cards", headers=EN, params={"q": "Yiheshi", "limit": 50})
    assert any(card["id"] == "YIHESHI" for card in en.json()["cards"])
    strike = client.get("/api/cards", params={"q": "Strike", "limit": 50})
    assert any(card["id"] == "CLAUDE_STRIKE" and "打击" in (card["name_zh"] or card["name"]) for card in strike.json()["cards"])
    chinese = client.get("/api/cards", params={"q": "打击", "limit": 50})
    assert any(card["id"] == "CLAUDE_STRIKE" for card in chinese.json()["cards"])

    narrowed = client.get("/api/cards", params={
        "character": "claude", "type": "Attack", "cost": "0", "rarity": "Basic", "limit": 200,
    })
    ids = [card["id"] for card in narrowed.json()["cards"]]
    assert "XIAOBENBEN" in ids
    assert "CLAUDE_STRIKE" not in ids
    assert all(card["character"] == "claude" and card["cost"] == 0 for card in narrowed.json()["cards"])


def test_card_query_errors_are_400(client):
    bad = client.get("/api/cards", headers=EN, params={"offset": "no"})
    assert bad.status_code == 400
    assert "offset" in _detail(bad)
    assert "integer" in _detail(bad)
    huge = client.get("/api/cards", headers=EN, params={"limit": 0})
    assert huge.status_code == 400
    _detail(huge)
    climbed = client.get("/api/cards", headers=EN, params={"character": "../claude"})
    assert climbed.status_code == 400
    _detail(climbed)
    nul = client.get("/api/cards", headers=EN, params={"q": "a\x00b"})
    assert nul.status_code == 400
    _detail(nul)


def test_save_writes_only_a_user_preset_and_can_run(client, allowed):
    before_quick = _read(QUICK)
    before_decks = _read(SHIPPED_DECKS)
    before_names = set(os.listdir(os.path.join(ROOT, "experiments")))
    res = client.post("/api/decks", headers=EN, json=_payload())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["id"] == "tdeck"
    assert body["file"] == "tdeck.yaml"
    assert os.path.dirname(QUICK) not in res.text
    saved = allowed / "presets" / "tdeck.yaml"
    assert saved.is_file()
    text = saved.read_text(encoding="utf-8")
    assert "YIHESHI+" in text
    assert "XIAOBENBEN×2" in text
    assert "encounter: DUMMY" in text
    assert "rooms: []" in text
    assert _read(QUICK) == before_quick
    assert _read(SHIPPED_DECKS) == before_decks
    assert set(os.listdir(os.path.join(ROOT, "experiments"))) == before_names

    from gui.backend import LocalPythonBackend
    backend = LocalPythonBackend()
    ids = [item["id"] for item in backend.experiments("en")]
    assert "tdeck" in ids
    assert "quick" in ids

    run = allowed / "run"
    run.mkdir()
    argv, env, cwd = backend.build_command(
        "combat",
        {"preset": "tdeck", "fights": 1, "seed": 1, "agent": "heuristic", "procs": 1},
        str(run),
    )
    assert os.path.realpath(env["STS2SIM_USER_MODS"]) == os.path.realpath(str(run / "user_mods"))
    assert (run / "user_mods" / "tdeck" / "decks.yaml").is_file()
    experiment = (run / "experiment.yaml").read_text(encoding="utf-8")
    assert "user_deck" not in experiment
    assert "DUMMY" in experiment
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    raw = (run / "out" / "raw.jsonl").read_text(encoding="utf-8")
    fight = json.loads(raw.splitlines()[0])
    assert fight["deck"] == "tdeck"
    assert fight["encounter"] == "DUMMY"
    assert _read(QUICK) == before_quick


def test_save_rejects_path_tricks_and_bad_types(client, allowed, tmp_path, monkeypatch):
    before_quick = _read(QUICK)
    shipped = client.post("/api/decks", headers=EN, json=_payload("quick"))
    assert shipped.status_code == 400
    assert "shipped" in _detail(shipped).lower() or "another id" in _detail(shipped).lower()

    climbed = client.post("/api/decks", headers=EN, json=_payload("../quick"))
    assert climbed.status_code == 400
    _detail(climbed)

    nul = client.post("/api/decks", headers=EN, json=_payload("deck\x00id"))
    assert nul.status_code == 400
    _detail(nul)

    outside = tmp_path / "outside.yaml"
    outside.write_text(SECRET, encoding="utf-8")
    presets = allowed / "presets"
    presets.mkdir()
    link = presets / "linked.yaml"
    link.symlink_to(outside)
    linked = client.post("/api/decks", headers=EN, json=_payload("linked"))
    assert linked.status_code == 400
    _detail(linked)
    assert outside.read_text(encoding="utf-8") == SECRET

    escaped = tmp_path / "escaped"
    escaped.mkdir()
    os.remove(link)
    presets.rmdir()
    presets.symlink_to(escaped, target_is_directory=True)
    jumped = client.post("/api/decks", headers=EN, json=_payload("jump"))
    assert jumped.status_code == 400
    _detail(jumped)
    assert list(escaped.iterdir()) == []
    presets.unlink()

    sibling = tmp_path / (allowed.name + "-not")
    sibling.mkdir()
    monkeypatch.setenv("DECKBENCH_PRESETS_DIR", str(sibling))
    prefixed = client.post("/api/decks", headers=EN, json=_payload("prefixed"))
    assert prefixed.status_code == 400
    _detail(prefixed)
    assert not any(sibling.iterdir())
    monkeypatch.delenv("DECKBENCH_PRESETS_DIR")

    monkeypatch.setenv("DECKBENCH_PRESETS_DIR", os.path.join(ROOT, "experiments"))
    into_shipped = client.post("/api/decks", headers=EN, json=_payload("intoexp"))
    assert into_shipped.status_code == 400
    _detail(into_shipped)
    monkeypatch.delenv("DECKBENCH_PRESETS_DIR")

    path_field = client.post("/api/decks", headers=EN, json={**_payload("fielded"), "path": str(outside)})
    assert path_field.status_code == 400
    assert str(outside) not in path_field.text
    _detail(path_field)

    wrong = client.post("/api/decks", headers=EN, json={**_payload(), "cards": SECRET})
    assert wrong.status_code == 400
    detail = _detail(wrong)
    assert "cards" in detail
    assert SECRET not in wrong.text

    missing = client.post("/api/decks", headers=EN, json={})
    assert missing.status_code == 400
    assert "id" in _detail(missing)
    zh = client.post("/api/decks", headers=ZHS, json={})
    assert zh.status_code == 400
    assert _detail(zh) != _detail(missing)
    assert "id" in _detail(zh)

    broken = client.post("/api/decks", headers={**EN, "content-type": "application/json"}, content=b"{")
    assert broken.status_code == 400
    assert "JSON" in _detail(broken)

    unknown = client.post("/api/decks", headers=EN, json=_payload(cards=[{"id": "NOT_A_CARD", "count": 1, "upgrade": False}]))
    assert unknown.status_code == 400
    _detail(unknown)

    monkeypatch.setattr("sts2sim.deckpresets.MAX_BYTES", 32)
    huge = client.post("/api/decks", headers=EN, json=_payload())
    assert huge.status_code == 400
    assert "32" in _detail(huge)
    assert _read(QUICK) == before_quick


def test_mcp_list_and_save(allowed):
    from tools import mcp_server as mcp
    listed = json.loads(mcp.list_cards(q="已核实", limit=20))
    assert listed["ok"] is True and listed["read_only"] is True
    assert any(card["id"] == "YIHESHI" for card in listed["cards"])
    bad = json.loads(mcp.list_cards(offset="no"))
    assert bad["ok"] is False and bad["read_only"] is True and bad["error"] == "bad_type"
    assert "Traceback" not in json.dumps(bad)

    saved = json.loads(mcp.save_deck(json.dumps(_payload("mcpdeck"))))
    assert saved["ok"] is True
    assert saved["file"] == "mcpdeck.yaml"
    assert (allowed / "presets" / "mcpdeck.yaml").is_file()
    assert SECRET not in json.dumps(saved)

    refused = json.loads(mcp.save_deck(json.dumps(_payload("../quick"))))
    assert refused["ok"] is False
    assert refused["error"] in ("path", "bad_id")
    assert "Traceback" not in json.dumps(refused)
    typed = json.loads(mcp.save_deck(12))
    assert typed["ok"] is False and typed["error"] == "bad_type"
    assert "12" not in json.dumps(typed)
