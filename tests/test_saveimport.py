"""对局记录 / 进行中存档的只读解析。夹具是虚构 ID，不是游戏文件。"""
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from sts2sim.saveimport import (
    SaveImportError,
    discover,
    load_path,
    parse_bytes,
    parse_path,
    refuse_save_write,
    summarize,
    summary_json,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORT_RUN = os.path.join(ROOT, "tools", "import_run.py")
MCP_SERVER = os.path.join(ROOT, "tools", "mcp_server.py")

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "saves")
HIST = os.path.join(FIX, "sample_history.run")
LIVE = os.path.join(FIX, "sample_live.save")


def test_history_seed_route_picks_relics():
    run = parse_path(HIST)
    assert run["kind"] == "run_history"
    assert run["schema_version"] == 9
    assert run["seed"] == "SAMPLESEED01"
    assert run["ascension"] == 3
    assert run["result"] == "lost"
    assert run["sim_character"] == "Ironclad"
    assert run["killed_by_encounter"] == "ENCOUNTER.SAMPLE_BOSS"
    assert run["killed_by_event"] is None
    assert [a["id"] for a in run["acts"]] == ["ACT.SAMPLE_ONE", "ACT.SAMPLE_TWO"]
    assert [f["type"] for f in run["route"]] == ["Ancient", "Monster", "Boss"]
    assert [f["floor"] for f in run["route"]] == [1, 2, 3]
    assert run["route"][1]["act_index"] == 0 and run["route"][2]["act_index"] == 1
    picks = run["route"][1]["picks"][0]["cards"]
    assert [c["id"] for c in picks] == ["CARD.SAMPLE_PICK", "CARD.SAMPLE_SKIP"]
    assert [c["was_picked"] for c in picks] == [True, False]
    assert run["route"][1]["rooms"][0]["model_id"] == "ENCOUNTER.SAMPLE_FIGHT"
    p = run["players"][0]
    assert p["relics"][1] == {"id": "RELIC.SAMPLE_CHEST", "floor": 4}
    assert p["deck"][1]["upgraded"] is True
    assert p["deck"][1]["enchantment"] == {"id": "ENCHANT.SAMPLE", "amount": 2}
    assert any(w["code"] == "noRouteColumn" for w in run["warnings"])
    assert run["visited_map_coords"] == []


def test_live_save_seed_in_rng_and_map():
    run = parse_path(LIVE)
    assert run["kind"] == "live_save"
    assert run["seed"] == "LIVESEED0001"
    assert run["seed_source"] == "rng.seed"
    assert run["result"] == "in_progress"
    assert run["sim_character"] == "Silent"
    assert run["players"][0]["id"] == 7
    assert run["players"][0]["current_hp"] == 54
    assert run["visited_map_coords"] == [{"col": 2, "row": 1}, {"col": 1, "row": 2}]
    mp = run["acts"][0]["map"]
    assert mp["cols"] == 3
    assert mp["boss"] == {"col": 1, "row": 3}
    types = [n["type"] for row in mp["rows"] for n in row]
    assert types == ["Monster", "Elite"]
    assert any(w["code"] == "seedFromRng" for w in run["warnings"])
    assert any(w["code"] == "liveInProgress" for w in run["warnings"])
    assert not any(w["code"] == "actsObjects" for w in run["warnings"])


def test_pascal_and_camel_keys_and_flat_route():
    raw = {
        "SchemaVersion": 9,
        "Seed": "FLAT",
        "Win": True,
        "WasAbandoned": False,
        "Acts": ["ACT.SAMPLE_ONE"],
        "Players": [{"Id": 1, "Character": "CHARACTER.DEFECT", "Deck": ["CARD.SAMPLE_A"], "Relics": ["RELIC.SAMPLE"]}],
        "MapPointHistory": [
            {"MapPointType": "Shop", "PlayerStats": [], "Rooms": [{"TurnsTaken": 1}]},
        ],
    }
    run = parse_bytes(json.dumps(raw).encode(), filename="x.run")
    assert run["seed"] == "FLAT" and run["result"] == "won"
    assert run["sim_character"] == "Defect"
    assert run["route"][0]["type"] == "Shop"
    assert run["players"][0]["deck"][0]["id"] == "CARD.SAMPLE_A"
    assert run["players"][0]["relics"][0]["id"] == "RELIC.SAMPLE"


def test_history_with_object_acts_warns():
    raw = json.loads(open(HIST, encoding="utf-8").read())
    raw["acts"] = [{"id": "ACT.SAMPLE_ONE", "saved_map": {"mystery": True}}]
    run = parse_bytes(json.dumps(raw).encode(), filename="obj.run")
    assert any(w["code"] == "actsObjects" for w in run["warnings"])
    assert any(w["code"] == "mapUnparsed" for w in run["warnings"])


def test_wrappers_and_rejections(tmp_path):
    raw = open(HIST, "rb").read()
    bom = parse_bytes(b"\xef\xbb\xbf" + raw, filename="b.run")
    assert bom["seed"] == "SAMPLESEED01" and any(w["code"] == "bom" for w in bom["warnings"])
    gz = parse_bytes(gzip.compress(raw), filename="g.run")
    assert gz["seed"] == "SAMPLESEED01" and any(w["code"] == "gzip" for w in gz["warnings"])
    u16 = parse_bytes(raw.decode().encode("utf-16"), filename="u.run")
    assert u16["seed"] == "SAMPLESEED01" and any(w["code"] == "utf16" for w in u16["warnings"])
    wrapped = parse_bytes(json.dumps(raw.decode()).encode(), filename="d.run")
    assert wrapped["seed"] == "SAMPLESEED01" and any(w["code"] == "doubleEncoded" for w in wrapped["warnings"])
    with pytest.raises(SaveImportError) as ei:
        parse_bytes(b"\x00\x01\x02not json", filename="bin.save")
    assert ei.value.code == "not_json"
    with pytest.raises(SaveImportError) as ep:
        parse_bytes(b'{"epochs": [1], "cards": []}', filename="progress.save")
    assert ep.value.code == "not_a_run"
    missing = tmp_path / "nope.run"
    with pytest.raises(SaveImportError) as en:
        parse_path(str(missing))
    assert en.value.code == "not_found"


def test_folder_and_discover(tmp_path, monkeypatch):
    saves = tmp_path / "steam" / "1" / "profile1" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1779550532.run").write_bytes(open(HIST, "rb").read())
    (hist / "1779550532.run.backup").write_bytes(open(HIST, "rb").read())
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read())
    (saves / "progress.save").write_text("{}", encoding="utf-8")
    (hist / "bad.run").write_text("not-json", encoding="utf-8")
    loaded = load_path(str(saves))
    assert loaded["kind"] == "folder"
    names = [e["file"] for e in loaded["entries"]]
    assert names.count("1779550532.run") == 1
    assert "1779550532.run.backup" not in names
    assert "progress.save" not in names
    assert "current_run.save" in names
    bad = next(e for e in loaded["entries"] if e["file"] == "bad.run")
    assert bad["error"]["code"] == "not_json"
    good = next(e for e in loaded["entries"] if e["file"] == "1779550532.run")
    assert good["run"]["seed"] == "SAMPLESEED01"
    # 指到 profile 目录或 history 目录同样能列出来
    assert load_path(str(saves.parent))["kind"] == "folder"
    assert any(e["run"]["seed"] == "SAMPLESEED01" for e in load_path(str(hist))["entries"] if "run" in e)

    monkeypatch.setenv("DECKBENCH_SAVE_ROOTS", str(tmp_path))
    hits = discover()
    assert any(h["path"] == str(saves) and h["history"] == 2 and h["has_current"] for h in hits)


def test_import_and_preview_api():
    pytest.importorskip("fastapi")
    pytest.importorskip("python_multipart")
    from fastapi.testclient import TestClient
    from gui.server import app
    client = TestClient(app)
    up = client.post("/api/import/upload", headers={"x-lang": "en"},
                     files={"file": ("sample_history.run", open(HIST, "rb"), "application/octet-stream")})
    assert up.status_code == 200, up.text
    assert up.json()["run"]["seed"] == "SAMPLESEED01"
    assert up.json()["run"]["route"][1]["picks"][0]["cards"][0]["was_picked"] is True
    missing = client.post("/api/import", headers={"x-lang": "en"}, json={"path": "/no/such/run.run"})
    assert missing.status_code == 400 and "Path not found" in missing.json()["detail"]
    bad = client.post("/api/seed-preview", headers={"x-lang": "en"}, json={"seed": "", "char": "Ironclad", "asc": 0})
    assert bad.status_code == 400 and "seed" in bad.json()["detail"].lower()
    got = client.post("/api/import", headers={"x-lang": "en"}, json={"path": HIST})
    assert got.status_code == 200
    assert got.json()["run"]["players"][0]["relics"][1]["id"] == "RELIC.SAMPLE_CHEST"
    folder = client.post("/api/import", headers={"x-lang": "en"}, json={"path": FIX})
    assert folder.status_code == 200
    assert any(e.get("run", {}).get("seed") == "SAMPLESEED01" for e in folder.json()["entries"])
    junk = client.post("/api/import/upload", headers={"x-lang": "en"},
                       files={"file": ("broken.run", b"{not json", "application/octet-stream")})
    assert junk.status_code == 400
    detail = junk.json()["detail"]
    assert isinstance(detail, str) and "JSON" in detail and "Expecting" in detail
    settings = client.post("/api/import/upload", headers={"x-lang": "en"},
                           files={"file": ("settings.save", b'{"lang":"en"}', "application/octet-stream")})
    assert settings.status_code == 400 and "not one run" in settings.json()["detail"]


def test_abandoned_and_multiplayer_second_player():
    raw = {
        "seed": "MP",
        "win": False,
        "was_abandoned": True,
        "acts": ["ACT.SAMPLE_ONE"],
        "players": [
            {"id": 1, "character": "CHARACTER.REGENT", "deck": [], "relics": [], "potions": []},
            {"id": 2, "character": "CHARACTER.NECROBINDER", "deck": [], "relics": [{"id": "RELIC.SAMPLE"}], "potions": []},
        ],
        "map_point_history": [],
    }
    run = parse_bytes(json.dumps(raw).encode(), filename="mp.run")
    assert run["result"] == "abandoned"
    assert [p["sim_character"] for p in run["players"]] == ["Regent", "Necrobinder"]
    assert run["players"][1]["relics"][0]["id"] == "RELIC.SAMPLE"
    summary = summarize(run)
    assert summary["read_only"] is True
    assert summary["characters"] == ["Regent", "Necrobinder"]
    assert summary["character"] == "Regent"
    assert summary["floor_reached"] == 0
    assert summary["result"] == "abandoned"
    assert summary["highlights"]["relics"][0]["id"] == "RELIC.SAMPLE"
    assert summary["highlights"]["relics"][0]["player"] == 2


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _tree(root):
    found = {}
    for dirpath, _, files in os.walk(root):
        for name in files:
            p = os.path.join(dirpath, name)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            found[os.path.relpath(p, root)] = _sha(p)
    return found


def test_summary_history_and_live_highlights():
    hist = summarize(parse_path(HIST))
    wrapped = summarize(load_path(HIST))
    assert hist == wrapped
    assert hist["ok"] is True and hist["read_only"] is True
    assert hist["kind"] == "run_history"
    assert hist["seed"] == "SAMPLESEED01"
    assert hist["character"] == "Ironclad"
    assert hist["character_id"] == "CHARACTER.IRONCLAD"
    assert hist["ascension"] == 3
    assert hist["floor_reached"] == 3
    assert hist["result"] == "lost"
    assert hist["hp"] == 0 and hist["max_hp"] == 80 and hist["gold"] == 20
    assert hist["killed_by"] == "ENCOUNTER.SAMPLE_BOSS"
    cards = hist["highlights"]["cards"]
    assert [c["id"] for c in cards] == ["CARD.SAMPLE_PICK"]
    assert cards[0]["upgraded"] is True
    assert cards[0]["enchantment"] == "ENCHANT.SAMPLE"
    assert cards[0]["enchantment_amount"] == 2
    assert cards[0]["floor"] == 2
    assert hist["highlights"]["deck_size"] == 2
    relics = hist["highlights"]["relics"]
    assert [r["id"] for r in relics] == ["RELIC.SAMPLE_CHEST", "RELIC.SAMPLE_START"]
    assert relics[0]["floor"] == 4
    assert hist["highlights"]["picks"][0]["picked"] == ["CARD.SAMPLE_PICK"]
    assert hist["highlights"]["picks"][0]["offered"] == ["CARD.SAMPLE_PICK", "CARD.SAMPLE_SKIP"]
    assert "noRouteColumn" in hist["warnings"]

    live = json.loads(summary_json(LIVE))
    assert live["kind"] == "live_save"
    assert live["seed"] == "LIVESEED0001"
    assert live["character"] == "Silent"
    assert live["ascension"] == 0
    assert live["floor_reached"] == 1
    assert live["result"] == "in_progress"
    assert live["hp"] == 54 and live["gold"] == 140
    assert [c["id"] for c in live["highlights"]["cards"]] == ["CARD.SAMPLE_DEFEND"]
    assert live["highlights"]["relics"][0]["id"] == "RELIC.SAMPLE_RING"


def test_summary_prefers_notable_cards_and_caps():
    plain = [{"id": f"CARD.PLAIN{i}", "floor_added_to_deck": 0} for i in range(41)]
    raw = {
        "seed": "CAP",
        "win": False,
        "acts": ["ACT.SAMPLE_ONE"],
        "players": [{"id": 1, "character": "CHARACTER.IRONCLAD", "deck": plain, "relics": [
            {"id": "RELIC.START", "floor_added_to_deck": 0},
            {"id": "RELIC.LATE", "floor_added_to_deck": 9},
            {"id": "RELIC.LATE", "floor_added_to_deck": 9},
        ]}],
        "map_point_history": [[{"map_point_type": "Monster", "player_stats": [], "rooms": []}]],
    }
    capped = summarize(parse_bytes(json.dumps(raw).encode(), filename="cap.run"))
    assert capped["floor_reached"] == 1
    assert len(capped["highlights"]["cards"]) == 40
    assert capped["highlights"]["cards_truncated"] is True
    assert capped["highlights"]["deck_size"] == 41
    assert [r["id"] for r in capped["highlights"]["relics"]] == ["RELIC.LATE", "RELIC.LATE", "RELIC.START"]

    plain.append({"id": "CARD.RARE", "floor_added_to_deck": 3, "current_upgrade": 1})
    raw["players"][0]["deck"] = plain
    picked = summarize(parse_bytes(json.dumps(raw).encode(), filename="rare.run"))
    assert [c["id"] for c in picked["highlights"]["cards"]] == ["CARD.RARE"]
    assert picked["highlights"]["cards_truncated"] is False
    assert picked["highlights"]["deck_size"] == 42

    picks = []
    for n in range(1, 26):
        picks.append({
            "map_point_type": "Monster",
            "player_stats": [{"player_id": 1, "card_choices": [
                {"card": {"id": f"CARD.F{n}"}, "was_picked": True},
            ]}],
            "rooms": [],
        })
    raw["map_point_history"] = [picks]
    raw["players"][0]["deck"] = [{"id": "CARD.RARE", "floor_added_to_deck": 3}]
    long = summarize(parse_bytes(json.dumps(raw).encode(), filename="long.run"))
    assert long["floor_reached"] == 25
    assert long["highlights"]["picks_truncated"] is True
    assert len(long["highlights"]["picks"]) == 20
    assert long["highlights"]["picks"][-1]["floor"] == 25
    assert long["highlights"]["picks"][-1]["picked"] == ["CARD.F25"]


def test_summary_floor_from_visited_coords_when_route_empty():
    raw = {
        "ascension": 2,
        "pre_finished_room": None,
        "rng": {"seed": "COORDS"},
        "visited_map_coords": [{"col": 0, "row": 0}, {"col": 1, "row": 1}, {"col": 2, "row": 2}],
        "players": [{"net_id": 1, "character_id": "CHARACTER.DEFECT", "deck": [], "relics": []}],
        "map_point_history": [],
        "acts": ["ACT.SAMPLE_ONE"],
    }
    summary = summarize(parse_bytes(json.dumps(raw).encode(), filename="current_run.save"))
    assert summary["kind"] == "live_save"
    assert summary["seed"] == "COORDS"
    assert summary["character"] == "Defect"
    assert summary["ascension"] == 2
    assert summary["floor_reached"] == 3
    assert summary["highlights"]["deck_size"] == 0


def test_summary_folder_and_missing_path(tmp_path):
    saves = tmp_path / "profile" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1.run").write_bytes(open(HIST, "rb").read())
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read())
    (hist / "bad.run").write_text("not-json", encoding="utf-8")
    before = _tree(tmp_path)
    doc = json.loads(summary_json(str(saves)))
    assert _tree(tmp_path) == before
    assert doc["kind"] == "folder" and doc["read_only"] is True
    assert doc["count"] == 2
    seeds = {e["seed"] for e in doc["entries"]}
    assert seeds == {"SAMPLESEED01", "LIVESEED0001"}
    assert doc["failures"][0]["error"] == "not_json"
    missing = json.loads(summary_json(str(tmp_path / "nope.run")))
    assert missing["ok"] is False and missing["error"] == "not_found" and missing["read_only"] is True
    assert missing["path"] == os.path.abspath(os.path.join(str(tmp_path), "nope.run"))
    assert _tree(tmp_path) == before


def test_refuse_write_into_save_tree_and_save_shaped_name(tmp_path):
    saves = tmp_path / "SlayTheSpire2" / "steam" / "1" / "profile1" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    src = hist / "1779550532.run"
    src.write_bytes(open(HIST, "rb").read())
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read())
    before = _tree(tmp_path)
    with pytest.raises(SaveImportError) as e:
        refuse_save_write(str(saves / "summary.json"), str(src))
    assert e.value.code == "refuse_write"
    with pytest.raises(SaveImportError) as e2:
        refuse_save_write(str(tmp_path / "copy.run"), str(src))
    assert e2.value.code == "refuse_write"
    with pytest.raises(SaveImportError) as e3:
        refuse_save_write(str(src), str(src))
    assert e3.value.code == "refuse_write"
    allowed = refuse_save_write(str(tmp_path / "summary.json"), str(src))
    assert allowed == os.path.realpath(tmp_path / "summary.json")
    assert _tree(tmp_path) == before
    link = tmp_path / "link.json"
    try:
        os.symlink(saves / "out.json", link)
    except OSError:
        pytest.skip("symlinks are not available")
    with pytest.raises(SaveImportError) as e4:
        refuse_save_write(str(link), str(src))
    assert e4.value.code == "refuse_write"
    assert not (saves / "out.json").exists()
    assert _tree(tmp_path) == before


def _run_import(*args):
    return subprocess.run([sys.executable, IMPORT_RUN, *args], cwd=ROOT, capture_output=True, text=True)


def test_summary_cli_prints_json_and_does_not_touch_saves(tmp_path):
    before_repo = (_sha(HIST), _sha(LIVE))
    shown = _run_import(HIST, "--summary")
    assert shown.returncode == 0, shown.stderr
    data = json.loads(shown.stdout)
    assert data["seed"] == "SAMPLESEED01"
    assert data["character"] == "Ironclad"
    assert data["ascension"] == 3
    assert data["floor_reached"] == 3
    assert data["highlights"]["relics"][0]["id"] == "RELIC.SAMPLE_CHEST"
    assert (_sha(HIST), _sha(LIVE)) == before_repo

    saves = tmp_path / "SlayTheSpire2" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    src = hist / "1.run"
    src.write_bytes(open(HIST, "rb").read())
    snap = _tree(tmp_path)
    inside = saves / "summary.json"
    blocked = _run_import(str(src), "--summary", "--json", str(inside), "--lang", "en")
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["error"] == "refuse_write"
    assert "Refusing to write inside a save folder" in blocked.stderr
    assert not inside.exists()
    assert _tree(tmp_path) == snap

    outside = tmp_path / "summary.json"
    ok = _run_import(str(src), "--summary", "--json", str(outside))
    assert ok.returncode == 0, ok.stderr
    assert json.loads(outside.read_text(encoding="utf-8"))["seed"] == "SAMPLESEED01"
    assert json.loads(ok.stdout)["floor_reached"] == 3
    assert src.read_bytes() == open(HIST, "rb").read()
    shaped = _run_import(str(src), "--json", str(tmp_path / "copy.save"))
    assert shaped.returncode == 2
    assert not (tmp_path / "copy.save").exists()
    assert _tree(saves) == {os.path.relpath(src, saves): _sha(src)}


def _load_mcp_server():
    name = "deckbench_mcp_server_under_test"
    spec = importlib.util.spec_from_file_location(name, MCP_SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mcp_import_save_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKBENCH_MCP_RUNS", str(tmp_path / "mcp_runs"))
    saves = tmp_path / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    src = hist / "1.run"
    src.write_bytes(open(HIST, "rb").read())
    before = _tree(tmp_path)
    mod = _load_mcp_server()
    data = json.loads(mod.import_save(str(src)))
    assert data["ok"] is True and data["read_only"] is True
    assert data["seed"] == "SAMPLESEED01"
    assert data["character"] == "Ironclad"
    assert data["ascension"] == 3
    assert data["floor_reached"] == 3
    assert data["highlights"]["cards"][0]["id"] == "CARD.SAMPLE_PICK"
    assert not (tmp_path / "mcp_runs").exists()
    assert _tree(tmp_path) == before
    missing = json.loads(mod.import_save(str(tmp_path / "missing.run")))
    assert missing["ok"] is False and missing["error"] == "not_found"
    assert _tree(tmp_path) == before


def test_import_only_mcp_skips_game_check(monkeypatch):
    mod = _load_mcp_server()

    class Dummy:
        def run(self, transport):
            raise SystemExit(0)

    monkeypatch.setattr(mod, "build_import", lambda *a, **k: Dummy())
    monkeypatch.setattr(mod, "build", lambda *a, **k: (_ for _ in ()).throw(AssertionError("play server started")))
    import sts2sim.gamedata as gamedata
    monkeypatch.setattr(gamedata, "require", lambda: (_ for _ in ()).throw(SystemExit(2)))
    with pytest.raises(SystemExit) as ei:
        mod.main(["--import-only"])
    assert ei.value.code == 0
    with pytest.raises(SystemExit) as ed:
        mod.main([])
    assert ed.value.code == 2


def test_mcp_help_mentions_import_save():
    r = subprocess.run([sys.executable, MCP_SERVER, "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "--import-only" in r.stdout
    assert "import_save" in r.stdout


def test_import_only_stdio_returns_summary():
    pytest.importorskip("mcp", reason="optional dependency: pip install -r requirements-mcp.txt")
    import asyncio

    before = _sha(HIST)

    async def scenario():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(
            command=sys.executable, args=[MCP_SERVER, "--import-only"], env=dict(os.environ), cwd=ROOT)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                names = [t.name for t in (await session.list_tools()).tools]
                assert names == ["import_save"], names
                result = await session.call_tool("import_save", {"path": HIST})
                text = "".join(getattr(c, "text", "") for c in result.content)
                assert not result.isError, text
                return json.loads(text)

    data = asyncio.run(scenario())
    assert data["read_only"] is True
    assert data["seed"] == "SAMPLESEED01"
    assert data["character"] == "Ironclad"
    assert data["ascension"] == 3
    assert data["floor_reached"] == 3
    assert data["highlights"]["cards"][0]["id"] == "CARD.SAMPLE_PICK"
    assert _sha(HIST) == before


def test_mcp_registers_import_save_when_sdk_present():
    pytest.importorskip("mcp", reason="optional dependency: pip install -r requirements-mcp.txt")
    mod = _load_mcp_server()
    server = mod.build_import()
    names = _mcp_tool_names(server)
    if not names:
        pytest.skip("this mcp build does not expose a tool list on FastMCP; import_save() is covered directly")
    assert "import_save" in names
    play = mod.build()
    play_names = _mcp_tool_names(play)
    assert "import_save" in play_names
    assert "new_run" in play_names


def _mcp_tool_names(server):
    manager = getattr(server, "_tool_manager", None)
    if manager is not None and hasattr(manager, "list_tools"):
        listed = manager.list_tools()
        return [getattr(t, "name", None) for t in listed]
    for attr in ("_tools", "tools"):
        raw = getattr(server, attr, None)
        if isinstance(raw, dict):
            return list(raw)
    return []
