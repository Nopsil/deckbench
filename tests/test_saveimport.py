"""真实对局导入：用合成 JSON 覆盖存档格式里容易读错的地方。不需要游戏，也不含游戏数据。"""
import gzip
import json
import os

import pytest

from sts2sim.saveimport import (
    ERR_CODES, POINT_TYPES, WARN_CODES, SaveImportError, format_text, main, open_path, parse_bytes, parse_obj,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "saves")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def test_history_seed_route_picks_relics():
    run = parse_bytes(_load("history_run.json").encode(), "history_run.json")
    assert run["kind"] == "history"
    assert run["schema_version"] == 9
    assert run["seed"] == "seed0o"
    assert run["seed_canonical"] == "SEED00"  # 大写，o→0，和游戏 / DeckBench 的种子规则一样
    assert run["result"] == "lost"
    assert run["killed_by"] == "ENCOUNTER.END"
    assert run["game_mode"] == "standard"
    assert run["platform"] == "steam"
    assert run["acts"] == ["ACT.FIRST", "ACT.SECOND"]
    assert [s["floor"] for s in run["route"]] == [1, 2]
    assert [s["act"] for s in run["route"]] == [0, 1]
    assert run["route"][0]["type"] == "ancient"
    assert run["route"][0]["rooms"][0]["id"] == "EVENT.HELLO"
    assert run["route"][1]["type"] == "monster"
    assert run["route"][1]["rooms"][0]["monsters"] == ["MONSTER.BLOB"]
    assert run["route"][0]["coord"] is None  # 历史记录没有列坐标

    hero = run["players"][0]
    assert hero["character"] == "CHARACTER.HERO"
    assert hero["id"] == "1"
    assert [(r["id"], r["floor"]) for r in hero["relics"]] == [("RELIC.START", 1), ("RELIC.MID", 3)]
    assert hero["deck"][0]["upgrade"] == 2
    assert hero["deck"][0]["enchantment"]["id"] == "ENCHANTMENT.EXAMPLE"

    ancient = run["route"][0]["players"][0]
    assert ancient["id"] == "1"
    assert ancient["ancient"][0] == {"id": "RELIC.MID", "picked": True, "inferred": True}
    assert ancient["ancient"][1]["id"] == "RELIC.SKIP" and ancient["ancient"][1]["picked"] is False
    assert ancient["relic_choices"][0]["picked"] is True

    fight = run["route"][1]["players"][0]
    picked = {c["id"]: c for c in fight["card_choices"]}
    assert picked["CARD.ALPHA"]["picked"] is True
    assert picked["CARD.ALPHA"]["floor"] == 2
    assert picked["CARD.GAMMA"]["picked"] is False
    assert picked["CARD.GAMMA"]["floor"] is None  # 没选的牌经常没有 floor_added_to_deck
    assert fight["cards_removed"][0]["id"] == "CARD.BASIC"
    # 另一名玩家的选牌不能混进来
    assert all(c["id"] != "CARD.OTHER" for c in fight["card_choices"])
    other = run["route"][0]["players"][1]
    assert other["card_choices"][0]["id"] == "CARD.OTHER"

    text = format_text(run, 0)
    assert "seed: seed0o" in text
    assert "seed_canonical: SEED00" in text
    assert "EVENT.HELLO" in text and "ENCOUNTER.END" in text
    assert "*CARD.ALPHA" in text and "-CARD.GAMMA" in text
    assert "CARD.OTHER" not in text
    assert "RELIC.START" in text and "floor 3" in text
    text_other = format_text(run, 1)
    assert "CARD.OTHER" in text_other
    assert "CARD.ALPHA" not in text_other.split("picks:")[1]


def test_live_save_uses_run_seed_not_player_rng_and_keeps_steam_id():
    run = parse_bytes(_load("live_run.json").encode(), "current_run.save")
    assert run["kind"] == "live"
    assert run["result"] == "in_progress"
    assert run["seed"] == "ABCDEFGHJKLM"
    assert run["seed_canonical"] == "ABCDEFGHJKLM"
    blob = json.dumps(run)
    assert "2189922105" not in blob  # 玩家 rng.seed 是计数器用的数字，不是对局种子
    assert run["players"][0]["id"] == "76561198000000001"
    assert isinstance(json.loads(blob)["players"][0]["id"], str)
    assert run["players"][0]["character"] == "CHARACTER.HERO"
    assert run["platform"] == "steam"
    # 坐标只贴到当前幕（第二幕），而且键是 col/row
    assert run["route"][0]["coord"] is None
    assert run["route"][1]["coord"] == {"col": 2, "row": 0}
    assert any(w["code"] == "coords_partial" and w["act"] == 2 for w in run["warnings"])
    # 选牌里的 ModelId 对象 {category, entry}
    choices = run["route"][0]["players"][0]["card_choices"]
    assert choices[1]["id"] == "CARD.BETA" and choices[1]["picked"] is False
    # 认得出的 saved_map：点 + 边
    assert run["maps"][0]["act"] == 0
    assert run["maps"][0]["points"][0]["children"] == [{"col": 1, "row": 1}]
    assert run["maps"][0]["points"][1]["type"] == "shop"
    assert all(not p["visited"] for p in run["maps"][0]["points"])


def test_gzip_bom_and_utf16():
    raw = _load("history_run.json").encode()
    gz = parse_bytes(gzip.compress(raw), "x.run")
    assert gz["seed"] == "seed0o"
    assert any(w["code"] == "gzip" for w in gz["warnings"])
    bom = parse_bytes(b"\xef\xbb\xbf" + raw, "x.run")
    assert bom["seed"] == "seed0o"
    assert any(w["code"] == "bom" for w in bom["warnings"])
    u16 = parse_bytes(raw.decode().encode("utf-16"), "x.run")
    assert u16["result"] == "lost"
    assert any(w["code"] == "utf16" for w in u16["warnings"])


def test_flat_history_grid_map_and_numeric_seed():
    flat = {
        "seed": "FLATSEED0001",
        "win": True,
        "players": [{"id": 7, "character": "CHARACTER.HERO", "deck": [], "relics": [{"id": "RELIC.START", "floor_added_to_deck": 1}]}],
        "acts": ["ACT.FIRST"],
        "map_point_history": [
            {"map_point_type": "rest_site", "rooms": [{"turns_taken": 1}], "player_stats": [{"player_id": 7, "rest_site_choices": ["REST"]}]},
        ],
    }
    run = parse_obj(flat, filename="flat.run")
    assert any(w["code"] == "flat_history" for w in run["warnings"])
    assert run["route"][0]["type"] == "rest_site"
    assert run["route"][0]["players"][0]["rest"] == ["REST"]
    assert run["result"] == "won"

    grid = {
        "seed": "GRIDSEED0001",
        "win": False,
        "was_abandoned": True,
        "players": [{"character": "CHARACTER.HERO", "id": 1, "deck": [], "relics": []}],
        "acts": [{"id": "ACT.FIRST", "saved_map": {"grid": [
            [{"type": "monster", "children": [1]}, None],
            [None, {"type": "elite"}],
        ]}}],
        "map_point_history": [],
        "visited_map_coords": [],
    }
    g = parse_obj(grid, filename="grid.save")
    assert g["result"] == "abandoned"
    pts = {(p["col"], p["row"]): p for p in g["maps"][0]["points"]}
    assert pts[(0, 0)]["type"] == "monster"
    assert pts[(0, 0)]["children"] == [{"col": 1, "row": 1}]
    assert pts[(1, 1)]["type"] == "elite"
    assert (1, 0) not in pts

    unknown = {
        "rng": {"seed": "UNKNOWNMAP01", "counters": {}},
        "players": [{"net_id": 3, "character_id": "CHARACTER.HERO", "deck": [], "relics": []}],
        "acts": [{"id": "ACT.FIRST", "saved_map": {"blob": 1}}],
        "map_point_history": [[]],
        "win_time": 0,
    }
    u = parse_obj(unknown, filename="current_run.save")
    assert any(w["code"] == "map_unknown" for w in u["warnings"])
    assert u["maps"] == []
    assert u["kind"] == "live"

    num = {
        "players": [{"net_id": 3, "character_id": "CHARACTER.HERO", "deck": [], "relics": [], "rng": {"seed": 99}}],
        "rng": {"seed": 12345, "counters": {}},
        "map_point_history": [[]],
        "win_time": 0,
    }
    n = parse_obj(num, filename="current_run.save")
    assert n["seed"] == "12345"
    assert any(w["code"] == "seed_numeric_only" for w in n["warnings"])


def test_rejects_progress_truncated_and_does_not_write(tmp_path):
    progress = tmp_path / "progress.save"
    progress.write_text(json.dumps({"epochs": ["EPOCH.EXAMPLE"], "card_pools": []}), encoding="utf-8")
    with pytest.raises(SaveImportError) as ei:
        parse_bytes(progress.read_bytes(), "progress.save")
    assert ei.value.code == "not_run"
    with pytest.raises(SaveImportError) as ej:
        parse_bytes(b"{", "broken.run")
    assert ej.value.code == "json"
    with pytest.raises(SaveImportError) as ee:
        parse_bytes(b"   \n", "empty.run")
    assert ee.value.code == "empty"

    good = tmp_path / "history" / "1700000000.run"
    good.parent.mkdir()
    payload = _load("history_run.json").encode()
    good.write_bytes(payload)
    (tmp_path / "history" / "broken.run").write_text("{", encoding="utf-8")
    (tmp_path / "history" / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "history" / "progress.save").write_text("{}", encoding="utf-8")
    before = good.read_bytes()
    names = sorted(p.name for p in (tmp_path / "history").iterdir())
    index = open_path(str(tmp_path / "history"))
    assert good.read_bytes() == before
    assert sorted(p.name for p in (tmp_path / "history").iterdir()) == names
    ok = [r for r in index["runs"] if not r.get("error")]
    bad = [r for r in index["runs"] if r.get("error")]
    assert [r["filename"] for r in ok] == ["1700000000.run"]
    assert ok[0]["seed"] == "seed0o"
    assert any(r["filename"] == "broken.run" and r["error"] == "json" for r in bad)
    assert all(r["filename"] != "progress.save" for r in index["runs"])
    assert all(r["filename"] != "notes.txt" for r in index["runs"])


def test_cli_file_and_folder(tmp_path, capsys):
    src = os.path.join(FIX, "history_run.json")
    assert main([src]) == 0
    out = capsys.readouterr().out
    assert "seed: seed0o" in out and "RELIC.MID" in out and "*CARD.ALPHA" in out
    assert main([src, "--json", "--player", "2"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["players"][1]["character"] == "CHARACTER.OTHER"
    assert main([src, "--player", "9"]) == 1
    err = capsys.readouterr().err
    assert "bad_player" in err
    folder = tmp_path / "saves"
    folder.mkdir()
    (folder / "a.run").write_bytes(_load("history_run.json").encode())
    assert main([str(folder)]) == 0
    listed = capsys.readouterr().out
    assert "a.run" in listed and "seed0o" in listed
    assert main([str(tmp_path / "missing.run")]) == 1
    assert "not_found" in capsys.readouterr().err


def test_apply_names_is_optional_and_local():
    from sts2sim.saveimport import apply_names
    run = parse_bytes(_load("history_run.json").encode(), "history_run.json")
    assert "name" not in run["players"][0]["deck"][0]
    apply_names(run, lambda mid: "Called " + mid if mid == "CARD.ALPHA" else None)
    assert run["players"][0]["deck"][0]["name"] == "Called CARD.ALPHA"
    assert "name" not in run["players"][0]["relics"][0]


def test_api_open_upload_and_suggest(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from gui import paths, server

    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    c = TestClient(server.app)
    listed = c.get("/api/saves/suggest")
    assert listed.status_code == 200 and "folders" in listed.json()

    src = os.path.join(FIX, "history_run.json")
    opened = c.post("/api/saves/open", json={"path": src}, headers={"x-lang": "en"})
    assert opened.status_code == 200
    run = opened.json()["run"]
    assert opened.json()["type"] == "run"
    assert run["seed"] == "seed0o" and run["seed_canonical"] == "SEED00"
    assert run["players"][0]["relics"][0]["id"] == "RELIC.START"
    assert run["route"][1]["players"][0]["card_choices"][0]["id"] == "CARD.ALPHA"

    dest = tmp_path / "saves"
    (dest / "history").mkdir(parents=True)
    (dest / "history" / "1700000000.run").write_bytes(open(src, "rb").read())
    (dest / "current_run.save").write_bytes(open(os.path.join(FIX, "live_run.json"), "rb").read())
    (dest / "progress.save").write_text("{}", encoding="utf-8")
    folder = c.post("/api/saves/open", json={"path": str(dest)}, headers={"x-lang": "en"})
    assert folder.status_code == 200 and folder.json()["type"] == "index"
    names = {item["filename"] for item in folder.json()["runs"]}
    assert names == {"1700000000.run", "current_run.save"}
    live = next(item for item in folder.json()["runs"] if item["filename"] == "current_run.save")
    assert live["seed"] == "ABCDEFGHJKLM" and "2189922105" not in json.dumps(live)

    with open(src, "rb") as f:
        uploaded = c.post(
            "/api/saves/upload",
            files={"file": ("history.run", f, "application/octet-stream")},
            headers={"x-lang": "en"},
        )
    assert uploaded.status_code == 200
    assert uploaded.json()["run"]["route"][0]["type"] == "ancient"
    assert uploaded.json()["run"]["players"][0]["id"] == "1"

    missing = c.post("/api/saves/open", json={"path": str(tmp_path / "nope.run")}, headers={"x-lang": "en"})
    assert missing.status_code == 400 and "No such path" in missing.json()["detail"]
    prog = tmp_path / "progress.save"
    prog.write_text("{}", encoding="utf-8")
    bad = c.post("/api/saves/open", json={"path": str(prog)}, headers={"x-lang": "en"})
    assert bad.status_code == 400 and "not a run" in bad.json()["detail"]


def test_warning_and_point_codes_have_translations():
    loc = os.path.join(ROOT, "gui", "locales")
    for lang in ("zhs", "en", "ja", "ko"):
        table = json.load(open(os.path.join(loc, lang + ".json"), encoding="utf-8"))
        for code in WARN_CODES:
            assert f"imp.warn.{code}" in table
        for code in ERR_CODES:
            assert f"imp.err.{code}" in table
        for code in POINT_TYPES:
            assert f"imp.point.{code}" in table
            assert f"imp.letter.{code}" in table
