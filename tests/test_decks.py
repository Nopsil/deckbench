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
    assert body["max_turns"] == 1
    assert "max_turns: 1" in text
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


CODEX = os.path.join(ROOT, "tests", "fixtures", "encounters_min")


@pytest.fixture
def codex(monkeypatch):
    """合成遭遇，不是游戏数据。用来核对名单和连战都来自模拟器自己的 encounter_pool。"""
    monkeypatch.setenv("DECKBENCH_CODEX_DIR", CODEX)
    from sts2sim import deckpresets
    from sts2sim import enemies as sim_enemies
    sim_enemies._DB.clear()
    deckpresets._CODEX["path"] = None
    deckpresets._ENC_CACHE["sig"] = None
    deckpresets._ENC_CACHE["rows"] = None
    yield CODEX
    sim_enemies._DB.clear()
    deckpresets._CODEX["path"] = None
    deckpresets._ENC_CACHE["sig"] = None
    deckpresets._ENC_CACHE["rows"] = None


def _encounters(body):
    return [row["id"] for row in body["encounters"]]


def test_encounters_without_a_codex_list_only_the_dummy(client, allowed, monkeypatch, tmp_path):
    monkeypatch.setenv("DECKBENCH_CODEX_DIR", str(tmp_path / "no-codex"))
    from sts2sim import deckpresets
    from sts2sim import enemies as sim_enemies
    sim_enemies._DB.clear()
    deckpresets._ENC_CACHE["sig"] = None
    deckpresets._ENC_CACHE["rows"] = None
    before = _read(QUICK)
    page = client.get("/api/encounters", headers=EN)
    assert page.status_code == 200, page.text
    body = page.json()
    assert _encounters(body) == ["DUMMY"]
    assert body["probe"]["id"] == "DUMMY"
    assert body["probe"]["name_zh"] == "木桩"
    assert body["probe"]["name_en"] == "Training dummy"
    assert body["gauntlets"] == []
    from sts2sim.deckpresets import full_fight_turns
    assert body["full_turns"] == full_fight_turns()
    assert body["full_turns"] > 1
    assert body["turn_limit"] >= body["full_turns"]
    assert body["total"] == 1
    assert not (allowed / "presets").exists()
    assert _read(QUICK) == before
    assert "Traceback" not in page.text


def test_encounter_list_filters_names_and_builds_gauntlets_from_the_sim(client, codex):
    from sts2sim import enemies as sim_enemies
    page = client.get("/api/encounters", headers=EN, params={"limit": 2, "offset": 0})
    assert page.status_code == 200, page.text
    first = page.json()
    assert first["limit"] == 2 and first["offset"] == 0 and first["total"] > 2
    assert len(first["encounters"]) == 2
    nxt = client.get("/api/encounters", headers=EN, params={"limit": 2, "offset": 2})
    assert nxt.json()["encounters"][0]["id"] != first["encounters"][0]["id"]

    elites = client.get("/api/encounters", headers=ZHS, params={"act": "1", "room": "elite", "limit": 50})
    assert elites.status_code == 200
    body = elites.json()
    pool = [row["id"] for row in sim_enemies.encounter_pool(1, "精英")]
    assert _encounters(body) == pool == ["NIB_ELITE_A", "NIB_ELITE_B"]
    row = body["encounters"][0]
    assert row["name_zh"] == "小钉精英甲" and row["name_en"] == "Nib Elite A"
    assert row["act"] == 1 and row["room"] == "elite"
    assert "NIB_WEAK" not in _encounters(body) and "NIB_SKIP" not in _encounters(body)

    chinese = client.get("/api/encounters", params={"q": "精英乙", "limit": 20})
    assert _encounters(chinese.json()) == ["NIB_ELITE_B"]
    english = client.get("/api/encounters", params={"q": "Nib Patrol", "limit": 20})
    assert _encounters(english.json()) == ["NIB_NORMAL"]
    bosses = client.get("/api/encounters", params={"room": "首领", "limit": 20})
    assert _encounters(bosses.json()) == ["NIB_BOSS"]
    act2 = client.get("/api/encounters", params={"act": "2", "room": "Monster", "limit": 20})
    assert act2.json()["encounters"] == []
    act2_elite = client.get("/api/encounters", params={"act": 2, "room": "ELITE", "limit": 20})
    assert _encounters(act2_elite.json()) == ["NIB_ACT2"]

    gauntlet = next(item for item in body["gauntlets"] if item["id"] == "act1_elite")
    assert [item["id"] for item in gauntlet["encounters"]] == pool
    assert all(item["id"] != "act1_weak" for item in body["gauntlets"])
    assert "NIB_SKIP" not in {row["id"] for item in body["gauntlets"] for row in item["encounters"]}
    assert "NIB_WEAK" not in {row["id"] for item in body["gauntlets"] for row in item["encounters"]}


def test_encounter_query_errors_are_400(client, codex):
    bad = client.get("/api/encounters", headers=EN, params={"offset": "no"})
    assert bad.status_code == 400
    assert "offset" in _detail(bad) and "integer" in _detail(bad)
    huge = client.get("/api/encounters", headers=EN, params={"limit": 0})
    assert huge.status_code == 400
    _detail(huge)
    over = client.get("/api/encounters", headers=EN, params={"limit": 201})
    assert over.status_code == 400
    _detail(over)
    act = client.get("/api/encounters", headers=EN, params={"act": "9"})
    assert act.status_code == 400
    _detail(act)
    room = client.get("/api/encounters", headers=EN, params={"room": "weak"})
    assert room.status_code == 400
    _detail(room)
    climbed = client.get("/api/encounters", headers=EN, params={"room": "../elite"})
    assert climbed.status_code == 400
    assert ".." not in climbed.text
    _detail(climbed)
    nul = client.get("/api/encounters", headers=EN, params={"q": "a\x00b"})
    assert nul.status_code == 400
    _detail(nul)
    secret = client.get("/api/encounters", headers=EN, params={"act": SECRET})
    assert secret.status_code == 400
    assert SECRET not in secret.text
    assert "Traceback" not in secret.text


def test_save_two_encounters_and_run_them(client, allowed, codex):
    before_quick = _read(QUICK)
    before_decks = _read(SHIPPED_DECKS)
    payload = _payload("twodeck")
    payload["encounters"] = [
        {"id": "NIB_ELITE_A", "fights": 1},
        {"id": "NIB_ELITE_B", "fights": 2},
    ]
    res = client.post("/api/decks", headers=EN, json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    from sts2sim.deckpresets import full_fight_turns
    cap = full_fight_turns()
    assert body["encounters"] == ["NIB_ELITE_A", "NIB_ELITE_B"]
    assert body["fights"] == 3
    assert body["max_turns"] == cap and cap > 1
    saved = (allowed / "presets" / "twodeck.yaml").read_text(encoding="utf-8")
    assert "NIB_ELITE_A" in saved and "NIB_ELITE_B" in saved
    assert "DUMMY" not in saved
    assert "rooms: []" in saved
    assert f"max_turns: {cap}" in saved
    assert os.path.dirname(QUICK) not in res.text
    assert _read(QUICK) == before_quick
    assert _read(SHIPPED_DECKS) == before_decks

    from gui.backend import LocalPythonBackend
    run = allowed / "run-two"
    run.mkdir()
    argv, env, cwd = LocalPythonBackend().build_command(
        "combat",
        {"preset": "twodeck", "fights": 1, "seed": 1, "agent": "heuristic", "procs": 1},
        str(run),
    )
    experiment = (run / "experiment.yaml").read_text(encoding="utf-8")
    assert "user_deck" not in experiment
    assert "NIB_ELITE_A" in experiment and "NIB_ELITE_B" in experiment
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    fights = [json.loads(line) for line in (run / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["encounter"] for row in fights] == ["NIB_ELITE_A", "NIB_ELITE_B", "NIB_ELITE_B"]
    assert fights[0]["enc_name"] == "小钉精英甲"
    decided = [row for row in fights if row["result"] in ("win", "loss")]
    assert len(decided) * 2 >= len(fights)
    assert any(row["result"] != "timeout" for row in fights)
    assert fights[0]["deck"] == "twodeck"
    assert _read(QUICK) == before_quick


def test_gauntlet_save_and_custom_run_use_the_sim_pool(client, allowed, codex):
    payload = _payload("gauntlet")
    payload["gauntlet"] = "act1_elite"
    payload["fights"] = 1
    res = client.post("/api/decks", headers=ZHS, json=payload)
    assert res.status_code == 200, res.text
    from sts2sim.deckpresets import full_fight_turns
    assert res.json()["encounters"] == ["NIB_ELITE_A", "NIB_ELITE_B"]
    assert res.json()["max_turns"] == full_fight_turns()
    text = (allowed / "presets" / "gauntlet.yaml").read_text(encoding="utf-8")
    assert text.index("NIB_ELITE_A") < text.index("NIB_ELITE_B")
    assert "DUMMY" not in text

    from gui.backend import LocalPythonBackend
    run = allowed / "custom-two"
    run.mkdir()
    argv, env, cwd = LocalPythonBackend().build_command(
        "combat",
        {
            "mods": ["claude_v34"],
            "decks": ["probe_noengine"],
            "rooms": ["普通", "精英"],
            "gauntlet": "act1_elite",
            "max_turns": 1,
            "fights": 1,
            "seed": 1,
            "agent": "heuristic",
            "procs": 1,
        },
        str(run),
    )
    experiment = (run / "experiment.yaml").read_text(encoding="utf-8")
    assert "rooms: []" in experiment or "rooms: []\n" in experiment
    assert "NIB_ELITE_A" in experiment and "NIB_ELITE_B" in experiment
    assert "普通" not in experiment.split("extra:", 1)[-1]
    proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    fights = [json.loads(line) for line in (run / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["encounter"] for row in fights] == ["NIB_ELITE_A", "NIB_ELITE_B"]
    assert all(row["deck"] == "probe_noengine" for row in fights)


def test_encounter_save_rejects_bad_input_without_echoing_it(client, allowed, codex, monkeypatch):
    before_quick = _read(QUICK)
    unknown = client.post("/api/decks", headers=EN, json=_payload(cards=[{"id": "YIHESHI", "count": 1, "upgrade": False}], pid="badenc") | {
        "encounters": [{"id": SECRET, "fights": 1}],
    })
    assert unknown.status_code == 400
    _detail(unknown)
    assert SECRET not in unknown.text
    assert not (allowed / "presets" / "badenc.yaml").exists()

    climbed = client.post("/api/decks", headers=EN, json={
        **_payload("climbenc"),
        "encounters": [{"id": "../NIB_ELITE_A", "fights": 1}],
    })
    assert climbed.status_code == 400
    _detail(climbed)
    assert "NIB_ELITE_A" not in climbed.text

    nul = client.post("/api/decks", headers=EN, json={
        **_payload("nulenc"),
        "encounters": [{"id": "NIB\x00ELITE", "fights": 1}],
    })
    assert nul.status_code == 400
    _detail(nul)

    typed = client.post("/api/decks", headers=EN, json={**_payload("typedenc"), "encounters": SECRET})
    assert typed.status_code == 400
    detail = _detail(typed)
    assert "encounters" in detail
    assert SECRET not in typed.text

    flag = client.post("/api/decks", headers=EN, json={
        **_payload("flagenc"),
        "encounters": [{"id": "DUMMY", "fights": True}],
    })
    assert flag.status_code == 400
    assert "integer" in _detail(flag)
    assert "true" not in flag.text.lower()

    zero = client.post("/api/decks", headers=EN, json={
        **_payload("zeroenc"),
        "encounters": [{"id": "DUMMY", "fights": 0}],
    })
    assert zero.status_code == 400
    assert "1" in _detail(zero)

    empty = client.post("/api/decks", headers=EN, json={**_payload("emptyenc"), "encounters": []})
    assert empty.status_code == 400
    _detail(empty)

    missing_g = client.post("/api/decks", headers=EN, json={**_payload("gbad"), "gauntlet": "act1_weak"})
    assert missing_g.status_code == 400
    assert "act1_weak" not in missing_g.text
    _detail(missing_g)

    path_g = client.post("/api/decks", headers=EN, json={**_payload("gpath"), "gauntlet": "../act1_elite"})
    assert path_g.status_code == 400
    _detail(path_g)

    monkeypatch.setattr("sts2sim.deckpresets.MAX_ENCOUNTERS", 1)
    too_many = client.post("/api/decks", headers=EN, json={
        **_payload("manyenc"),
        "encounters": [{"id": "NIB_ELITE_A", "fights": 1}, {"id": "NIB_ELITE_B", "fights": 1}],
    })
    assert too_many.status_code == 400
    assert "1" in _detail(too_many)
    monkeypatch.setattr("sts2sim.deckpresets.MAX_ENCOUNTERS", 40)
    short = client.post("/api/decks", headers=EN, json={
        **_payload("shortenc"),
        "encounters": [{"id": "NIB_ELITE_A", "fights": 1}],
        "max_turns": 4,
    })
    assert short.status_code == 200, short.text
    assert short.json()["max_turns"] == 4
    assert "max_turns: 4" in (allowed / "presets" / "shortenc.yaml").read_text(encoding="utf-8")

    zero_turns = client.post("/api/decks", headers=EN, json={**_payload("turn0"), "max_turns": 0})
    assert zero_turns.status_code == 400
    assert "1" in _detail(zero_turns)
    huge_turns = client.post("/api/decks", headers=EN, json={**_payload("turnbig"), "max_turns": 201})
    assert huge_turns.status_code == 400
    assert "200" in _detail(huge_turns)
    bad_turns = client.post("/api/decks", headers=EN, json={**_payload("turnbad"), "max_turns": SECRET})
    assert bad_turns.status_code == 400
    assert "max_turns" in _detail(bad_turns)
    assert SECRET not in bad_turns.text
    assert not (allowed / "presets" / "turnbig.yaml").exists()

    monkeypatch.setattr("sts2sim.deckpresets.MAX_FIGHTS_TOTAL", 1)
    too_fights = client.post("/api/decks", headers=EN, json={
        **_payload("fightenc"),
        "encounters": [{"id": "NIB_ELITE_A", "fights": 1}, {"id": "DUMMY", "fights": 1}],
    })
    assert too_fights.status_code == 400
    assert "1" in _detail(too_fights)
    assert not (allowed / "presets" / "fightenc.yaml").exists()
    assert _read(QUICK) == before_quick

    from gui.backend import LocalPythonBackend
    run = allowed / "bad-custom"
    run.mkdir()
    try:
        LocalPythonBackend().build_command(
            "combat",
            {
                "mods": ["claude_v34"],
                "decks": ["probe_noengine"],
                "rooms": ["普通"],
                "encounters": [{"id": SECRET, "fights": 1}],
                "max_turns": 1,
                "fights": 1,
                "seed": 1,
                "agent": "heuristic",
                "procs": 1,
            },
            str(run),
        )
    except ValueError as exc:
        assert SECRET not in str(exc)
    else:
        raise AssertionError("bad encounter was accepted")


def test_mcp_lists_encounters_and_saves_them(allowed, codex):
    from tools import mcp_server as mcp
    listed = json.loads(mcp.list_encounters(q="精英甲", act="1", room="elite", limit=20))
    assert listed["ok"] is True and listed["read_only"] is True
    assert [row["id"] for row in listed["encounters"]] == ["NIB_ELITE_A"]
    assert any(item["id"] == "act1_elite" for item in listed["gauntlets"])
    bad = json.loads(mcp.list_encounters(offset="no"))
    assert bad["ok"] is False and bad["read_only"] is True and bad["error"] == "bad_type"
    assert "Traceback" not in json.dumps(bad)
    refused = json.loads(mcp.list_encounters(room="../elite"))
    assert refused["ok"] is False and refused["error"] == "query"
    assert ".." not in json.dumps(refused)

    payload = _payload("mcpenc")
    payload["gauntlet"] = "act1_elite"
    payload["encounters"] = [{"id": "DUMMY", "fights": 1}]
    saved = json.loads(mcp.save_deck(json.dumps(payload)))
    assert saved["ok"] is True
    assert saved["encounters"] == ["NIB_ELITE_A", "NIB_ELITE_B", "DUMMY"]
    text = (allowed / "presets" / "mcpenc.yaml").read_text(encoding="utf-8")
    assert "NIB_ELITE_A" in text and "DUMMY" in text
    assert SECRET not in json.dumps(saved)

    missing = json.loads(mcp.save_deck(json.dumps({**_payload("mcpbad"), "encounters": [{"id": SECRET, "fights": 1}]})))
    assert missing["ok"] is False and missing["error"] == "unknown_encounter"
    assert SECRET not in json.dumps(missing)
    assert not (allowed / "presets" / "mcpbad.yaml").exists()


def _h2h_body(pid, seed, turns, name=None):
    body = _payload(pid)
    body["name"] = name or pid
    body["seed"] = seed
    body["max_turns"] = turns
    body["encounters"] = [{"id": "DUMMY", "fights": 1}]
    return body


def _runs_dir(allowed, monkeypatch):
    from gui import paths
    runs = allowed / "runs"
    runs.mkdir(exist_ok=True)
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))
    return runs


def _experiment(runs, rid):
    import yaml
    text = (runs / rid / "experiment.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def test_head_to_head_plan_uses_the_first_preset_unless_overridden(client, allowed, codex):
    from sts2sim.deckpresets import DeckPresetError, head_to_head_plan
    saved_a = client.post("/api/decks", headers=EN, json={
        **_payload("plana"),
        "name": "Plan A",
        "seed": 11,
        "max_turns": 6,
        "encounters": [{"id": "NIB_ELITE_A", "fights": 2}],
    })
    assert saved_a.status_code == 200, saved_a.text
    saved_b = client.post("/api/decks", headers=EN, json=_h2h_body("planb", 3, 1, "Plan B"))
    assert saved_b.status_code == 200, saved_b.text
    plan = head_to_head_plan({"a": "plana", "b": "planb"})
    assert plan["seed"] == 11 and plan["max_turns"] == 6
    assert plan["encounters"] == [{"id": "NIB_ELITE_A", "fights": 2}]
    assert plan["fights"] == 2
    overridden = head_to_head_plan({
        "a": "plana",
        "b": "planb",
        "seed": 5,
        "max_turns": 2,
        "encounters": [{"id": "DUMMY", "fights": 1}],
    })
    assert overridden["seed"] == 5 and overridden["max_turns"] == 2
    assert overridden["encounters"] == [{"id": "DUMMY", "fights": 1}]
    try:
        head_to_head_plan({"a": "plana", "b": "plana"})
    except DeckPresetError as err:
        assert err.code == "same_deck"
    else:
        raise AssertionError("the same preset was accepted")
    assert codex


def test_head_to_head_rejects_bad_input_before_a_run(client, allowed, monkeypatch):
    before_quick = _read(QUICK)
    runs = _runs_dir(allowed, monkeypatch)
    client.post("/api/decks", headers=EN, json=_h2h_body("goodh", 1, 1, "Good"))
    same = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh", "b": "goodh"})
    assert same.status_code == 400
    assert _detail(same) == "Pick two different presets."
    missing = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh"})
    assert missing.status_code == 400
    assert "b" in _detail(missing)
    typed = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh", "b": 2})
    assert typed.status_code == 400
    assert "b" in _detail(typed)
    unknown = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh", "b": "nosuchdeck"})
    assert unknown.status_code == 400
    _detail(unknown)
    climbed = client.post("/api/decks/head_to_head", headers=EN, json={"a": "../quick", "b": "goodh"})
    assert climbed.status_code == 400
    assert ".." not in climbed.text
    leaked = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh", "b": "nosuchdeck", "path": SECRET})
    assert leaked.status_code == 400
    assert SECRET not in leaked.text and "Traceback" not in leaked.text
    other = client.post("/api/decks", headers=EN, json=_h2h_body("otherh", 1, 1, "Other"))
    assert other.status_code == 200, other.text
    turns = client.post("/api/decks/head_to_head", headers=EN, json={"a": "goodh", "b": "otherh", "max_turns": 0})
    assert turns.status_code == 400
    assert "1" in _detail(turns)
    monkeypatch.setattr("sts2sim.deckpresets.MAX_FIGHTS_TOTAL", 1)
    capped = client.post("/api/decks/head_to_head", headers=EN, json={
        "a": "goodh",
        "b": "otherh",
        "encounters": [{"id": "DUMMY", "fights": 2}],
    })
    assert capped.status_code == 400
    assert "1" in _detail(capped)
    assert list(runs.iterdir()) == []
    assert _read(QUICK) == before_quick
    broken = client.post("/api/decks/head_to_head", headers={**EN, "content-type": "application/json"}, content=b"{")
    assert broken.status_code == 400
    assert "Traceback" not in broken.text


def test_head_to_head_runs_both_decks_and_compares(client, allowed, monkeypatch):
    before_quick = _read(QUICK)
    before_names = set(os.listdir(os.path.join(ROOT, "experiments")))
    runs = _runs_dir(allowed, monkeypatch)
    left = client.post("/api/decks", headers=EN, json=_h2h_body("h2ha", 11, 4, "Head A"))
    right = client.post("/api/decks", headers=EN, json=_h2h_body("h2hb", 99, 1, "Head B"))
    assert left.status_code == 200 and right.status_code == 200
    res = client.post("/api/decks/head_to_head", headers=EN, json={"a": "h2ha", "b": "h2hb"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["seed"] == 11 and body["max_turns"] == 4
    assert body["encounters"] == ["DUMMY"] and body["fights"] == 1
    assert body["compare"] == f"/#/compare?a={body['a']}&b={body['b']}"
    assert "Traceback" not in res.text
    exp_a = _experiment(runs, body["a"])
    exp_b = _experiment(runs, body["b"])
    assert exp_a["seed"] == exp_b["seed"] == 11
    assert exp_a["max_turns"] == exp_b["max_turns"] == 4
    assert exp_a["decks"] == ["h2ha"] and exp_b["decks"] == ["h2hb"]
    assert [row["encounter"] for row in exp_a["extra"]] == ["DUMMY"]
    assert [row["encounter"] for row in exp_b["extra"]] == ["DUMMY"]
    assert exp_a["extra"][0]["max_turns"] == exp_b["extra"][0]["max_turns"] == 4
    raw_a = json.loads((runs / body["a"] / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines()[0])
    raw_b = json.loads((runs / body["b"] / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert raw_a["encounter"] == raw_b["encounter"] == "DUMMY"
    assert raw_a["deck"] == "h2ha" and raw_b["deck"] == "h2hb"
    compared = client.get("/api/runs/compare", headers=EN, params={"a": body["a"], "b": body["b"]})
    assert compared.status_code == 200, compared.text
    cells = compared.json()["cells"]
    assert cells and cells[0]["deck_id"] == "h2ha/h2hb"
    assert cells[0]["room"] == "probe"
    assert _read(QUICK) == before_quick
    assert set(os.listdir(os.path.join(ROOT, "experiments"))) == before_names


def test_mcp_head_to_head_matches_the_endpoint(client, allowed, monkeypatch):
    from tools import mcp_server as mcp
    runs = _runs_dir(allowed, monkeypatch)
    assert client.post("/api/decks", headers=EN, json=_h2h_body("mcpa", 4, 1, "MCP A")).status_code == 200
    assert client.post("/api/decks", headers=EN, json=_h2h_body("mcpb", 8, 9, "MCP B")).status_code == 200
    doc = json.loads(mcp.head_to_head("mcpa", "mcpb", max_turns=2, seed=6))
    assert doc["ok"] is True
    assert doc["seed"] == 6 and doc["max_turns"] == 2 and doc["encounters"] == ["DUMMY"]
    assert doc["compare"].startswith("/#/compare?a=")
    exp_a = _experiment(runs, doc["a"])
    exp_b = _experiment(runs, doc["b"])
    assert exp_a["seed"] == exp_b["seed"] == 6
    assert exp_a["extra"][0]["max_turns"] == 2
    same = json.loads(mcp.head_to_head("mcpa", "mcpa"))
    assert same["ok"] is False and same["error"] == "same_deck"
    assert "Traceback" not in json.dumps(same)
    bad = json.loads(mcp.head_to_head("mcpa", "mcpb", encounters="{"))
    assert bad["ok"] is False and bad["error"] == "bad_json"
    typed = json.loads(mcp.head_to_head("mcpa", "mcpb", encounters=12))
    assert typed["ok"] is False and typed["error"] == "bad_type" and typed["field"] == "encounters"
