"""种子预览：不启动游戏也能测的部分（分布、文本、API 形状、命令行）。
有本机引擎时再跑一局真正的预览（neow=none，不打完一整局）。"""
import importlib.util
import json
import subprocess
import sys

import pytest

from sts2sim.engine.seedpreview import (
    CHARS, POINT_TYPES, assemble, parse_args_values, preview, relic_ids, render, render_map,
    room_counts, tally, warning_codes, PreviewError, main,
)

ROOT = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))

MAP = {
    "cols": 3,
    "boss": {"col": 1, "row": 3},
    "rows": [
        [
            {"col": 0, "row": 1, "type": "Monster", "children": [[0, 2], [1, 2]]},
            {"col": 2, "row": 1, "type": "Unknown", "children": [[1, 2]]},
        ],
        [
            {"col": 0, "row": 2, "type": "Elite", "children": [[1, 3]]},
            {"col": 1, "row": 2, "type": "Shop", "children": [[1, 3]]},
        ],
    ],
}
ROOMS = [{
    "act": "ACT_A",
    "normal": ["SLIME", "SLIME", "LOUSE"],
    "elite": ["GREMLIN"],
    "events": ["BIG_FISH"],
    "boss": "BOSS_A",
    "second_boss": None,
    "ancient": "ANCIENT_A",
}]
OPTIONS = [{"index": 0, "key": "NEOW.RELIC", "id": "RELIC", "locked": False}]
START = {"relics": ["BURNING"], "deck": ["STRIKE"], "gold": 99}
AFTER = {"0": {"encounter": "SLIME", "rewards": [
    {"kind": "CardReward", "cards": ["POMMEL_STRIKE"]},
    {"kind": "GoldReward", "gold": 15},
    {"kind": "PotionReward", "potion": "FIRE_POTION"},
    {"kind": "RelicReward", "relic": "ANCHOR"},
]}}


def _res(lang="en", seed="7f3k9q2zb8ma"):
    return assemble(seed, "Ironclad", 0, MAP, ROOMS, "NEOW", OPTIONS, START, AFTER, lang)


def test_room_and_encounter_distribution():
    counts = {x["type"]: x["count"] for x in room_counts(MAP)}
    assert counts == {"Monster": 1, "Unknown": 1, "Elite": 1, "Shop": 1, "Boss": 1}
    t = tally(["SLIME", "SLIME", "LOUSE"])
    assert t["order"] == ["SLIME", "SLIME", "LOUSE"]
    assert t["counts"] == [{"id": "SLIME", "count": 2}, {"id": "LOUSE", "count": 1}]
    res = _res()
    act = res["distribution"]["acts"][0]
    assert act["boss"] == "BOSS_A"
    assert act["normal"]["order"][0] == "SLIME"
    assert res["notable"]["relics"] == ["BURNING"]
    assert res["notable"]["deck"] == ["STRIKE"]
    assert res["notable"]["gold"] == 99
    assert res["v"] == 2 and res["seed"] == "7F3K9Q2ZB8MA"
    assert any(w["code"] == "normalized" for w in res["warning_codes"])


def test_summary_has_map_fights_and_rewards():
    en = _res("en")["summary"]
    assert "[M]" in en and "[E]" in en and "[?]" in en and "[$]" in en
    assert "BOSS_A" in en and "SLIME" in en and "GREMLIN" in en
    assert "BURNING" in en and "ANCHOR" in en and "POMMEL_STRIKE" in en and "FIRE_POTION" in en
    assert "15" in en
    assert "1. SLIME" in en and "2. SLIME" in en and "3. LOUSE" in en
    assert "种子" not in en and "sp.head" not in en
    zh = _res("zhs")["summary"]
    assert "种子" in zh and "[怪]" in zh and "[精]" in zh and "首领" in zh
    assert "シード" in _res("ja")["summary"]
    assert "시드" in _res("ko")["summary"]
    for lang in ("en", "zhs", "ja", "ko"):
        text = _res(lang)["summary"]
        assert "sp.mapTitle" not in text and "sp.firstReward" not in text


def test_render_map_links_and_boss_row():
    text = render_map(MAP, "en")
    assert "B" in text.splitlines()[0]
    assert "|" in text or "/" in text
    assert render_map({"cols": 0, "rows": []}, "en") == ""


def test_names_from_install_tables(monkeypatch):
    def fake(table, key, lang=None, field="title"):
        return {
            ("encounters", "SLIME"): "Slimes",
            ("encounters", "BOSS_A"): "The Boss",
            ("relics", "BURNING"): "Burning",
            ("relics", "ANCHOR"): "Anchor",
            ("cards", "STRIKE"): "Strike",
            ("cards", "POMMEL_STRIKE"): "Pommel",
            ("acts", "ACT_A"): "Overgrowth",
            ("potions", "FIRE_POTION"): "Fire",
            ("ancients", "NEOW"): "Neow",
        }.get((table, key))
    monkeypatch.setattr("gui.i18n.game_text", fake)
    res = _res("en")
    assert res["labels"]["encounters"]["SLIME"] == "Slimes"
    assert res["labels"]["relics"]["ANCHOR"] == "Anchor"
    assert "Slimes (SLIME)" in res["summary"]
    assert "Anchor (ANCHOR)" in res["summary"]
    assert "Overgrowth (ACT_A)" in res["summary"]


def test_warnings_and_validation():
    assert warning_codes("7F3K9Q2ZB8MA") == []
    assert warning_codes("abc")[0]["code"] == "normalized"
    assert any(w["code"] == "length" for w in warning_codes("ABC"))
    # O/I 会先被规范化成 0/1，所以用规范化之后仍然非法的字符
    assert any(w["code"] == "charset" for w in warning_codes("AB*"))
    with pytest.raises(PreviewError) as e:
        parse_args_values("  ", "Ironclad", 0, "all")
    assert e.value.key == "sp.badSeed"
    with pytest.raises(PreviewError) as e:
        parse_args_values("ABC", "Nope", 0, "all")
    assert e.value.key == "sp.badChar"
    with pytest.raises(PreviewError) as e:
        parse_args_values("ABC", "Ironclad", 11, "none")
    assert e.value.key == "sp.badAsc"
    assert set(CHARS) == {"Ironclad", "Silent", "Defect", "Necrobinder", "Regent"}
    assert "Boss" in POINT_TYPES


class _Id:
    def __init__(self, entry):
        self.Entry = entry


class _Relic:
    def __init__(self, entry):
        self.Id = _Id(entry)


class _Bag:
    def __init__(self, ids):
        self._relics = [_Relic(i) for i in ids]


def test_glyphs_and_room_names_in_every_language():
    from gui import i18n
    for lang in ("zhs", "en", "ja", "ko"):
        for typ in POINT_TYPES:
            g = i18n.t(f"sp.glyph.{typ}", lang)
            assert g and not g.startswith("sp."), (lang, typ, g)
            assert i18n.has(f"room.{typ}", lang)


def test_relic_ids_reads_bag_without_claiming_draw_order():
    assert relic_ids(_Bag(["ANCHOR", "HORN"])) == ["ANCHOR", "HORN"]
    assert relic_ids(None) == []
    assert relic_ids(object()) == []


def test_cli_prints_summary_and_json(monkeypatch, capsys, tmp_path):
    def fake(seed, char="Ironclad", asc=0, neow="all", lang=None):
        parse_args_values(seed, char, asc, neow)
        return assemble(seed, char, asc, MAP, ROOMS, "NEOW", OPTIONS, START, AFTER, lang or "en")
    monkeypatch.setattr("sts2sim.engine.seedpreview.preview", fake)
    outp = tmp_path / "preview.json"
    rc = main(["7F3K9Q2ZB8MA", "--char", "Silent", "--asc", "0", "--neow", "none", "--lang", "en", "--json", str(outp)])
    assert rc == 0
    assert "SLIME" in capsys.readouterr().out
    data = json.loads(outp.read_text(encoding="utf-8"))
    assert data["character"] == "Silent"
    assert data["distribution"]["acts"][0]["elite"]["order"] == ["GREMLIN"]
    assert data["after_neow"]["0"]["rewards"][3]["relic"] == "ANCHOR"


def test_seed_probe_script_keeps_map_helpers():
    path = __import__("os").path.join(ROOT, "tools", "seed_probe.py")
    spec = importlib.util.spec_from_file_location("seed_probe_cli", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod._map) and callable(mod.render_map)
    r = subprocess.run([sys.executable, path, "-h"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "--neow" in r.stdout and "--lang" in r.stdout


def test_api_validation_and_shape(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from gui import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    from gui import server

    c = TestClient(server.app)
    bad = c.get("/api/seed-preview", params={"seed": "ABC", "char": "Nope"}, headers={"x-lang": "en"})
    assert bad.status_code == 400 and "Nope" in bad.json()["detail"]
    empty = c.get("/api/seed-preview", params={"seed": "  "}, headers={"x-lang": "zhs"})
    assert empty.status_code == 400 and "种子" in empty.json()["detail"]
    asc = c.get("/api/seed-preview", params={"seed": "ABC", "asc": 99}, headers={"x-lang": "ja"})
    assert asc.status_code == 400 and "アセンション" in asc.json()["detail"]

    def fake(seed, char="Ironclad", asc=0, neow="all", lang=None):
        return assemble(seed, char, asc, MAP, ROOMS, "NEOW", OPTIONS, START, AFTER, lang or "en")

    monkeypatch.setattr("sts2sim.engine.seedpreview.preview", fake)
    ok = c.post("/api/seed-preview", json={"seed": "7f3k9q2zb8ma", "char": "Defect", "asc": 2, "neow": "none"},
                headers={"x-lang": "ko"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["seed"] == "7F3K9Q2ZB8MA" and body["character"] == "Defect"
    assert body["map"]["cols"] == 3
    assert body["distribution"]["map_rooms"]
    assert body["notable"]["relics"] == ["BURNING"]
    assert "ANCHOR" in body["summary"] and "시드" in body["summary"]
    got = c.get("/api/seed-preview", params={"seed": "7F3K9Q2ZB8MA", "neow": "none", "lang": "en"})
    assert got.status_code == 200 and "Seed " in got.json()["summary"]


def test_api_reports_missing_install(monkeypatch):
    """没有本机引擎时接口说明原因；有引擎时这条改由 test_live_preview 覆盖。"""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    try:
        import sts2sim.gen.game  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        pytest.skip("engine is installed; live preview covers this path")
    from fastapi.testclient import TestClient
    from gui import server
    c = TestClient(server.app)
    r = c.get("/api/seed-preview", params={"seed": "7F3K9Q2ZB8MA", "char": "Ironclad", "neow": "none"},
              headers={"x-lang": "en"})
    assert r.status_code == 503
    assert "game data" in r.json()["detail"].lower() or "setup" in r.json()["detail"]


def test_live_preview():
    pytest.importorskip("sts2sim.gen.game")
    r = preview("7F3K9Q2ZB8MA", "Ironclad", 0, neow="none", lang="en")
    assert r["map"]["rows"] and r["map"]["boss"]
    assert r["distribution"]["acts"] and r["distribution"]["acts"][0]["boss"]
    assert r["notable"]["relics"] and r["notable"]["deck"]
    assert r["summary"] and "sp.head" not in r["summary"]
