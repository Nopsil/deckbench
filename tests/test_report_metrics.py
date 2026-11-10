"""报告和整局指标：编码、空行、0 回合胜场、偶数局的中位数。"""
import json

from gui.metrics import batch_summary
from sts2sim.report import _load, make_report


def _row(**over):
    row = {
        "floor": 1, "act": 0, "victory": False, "combats": [], "seed": "S",
    }
    row.update(over)
    return row


def test_even_sample_median_floor_is_the_middle_not_the_upper_value():
    rows = [
        _row(floor=1, seed="a"),
        _row(floor=2, seed="b"),
        _row(floor=3, seed="c"),
        _row(floor=10, seed="d"),
    ]
    summary = batch_summary(rows)
    assert summary["median_floor"] == 2.5
    assert summary["avg_floor"] == 4
    odd = batch_summary([_row(floor=1, seed="a"), _row(floor=2, seed="b"), _row(floor=10, seed="c")])
    assert odd["median_floor"] == 2


class _Card:
    def __init__(self, name):
        self.name = name
        self.mod = "mod"
        self.type = "攻击"


class _Mods:
    decks = {"d": {"name": "模组·甲", "stage": "成型", "acts": [1]}}
    cards = {"打击": _Card("打击")}
    hook_modules = []


def _stub_coverage(monkeypatch):
    from sts2sim import catalog
    monkeypatch.setattr(catalog, "coverage", lambda M: {
        "monsters": [], "monster_summary": {}, "encounters": [], "encounter_summary": {},
        "intent_moves": 0, "lambdas": (0, 0),
        "relics": {"total": 0, "implemented": [], "starter_total": 0, "starter_impl": [],
                   "starter_all": [], "mod_only": []},
        "potions": {"total": 0, "implemented": []},
        "powers": {"total": 0, "implemented": [], "enemy_used": [], "enemy_used_impl": [], "mod_only": []},
    })
    monkeypatch.setattr(catalog, "coverage_md", lambda cov: "")
    monkeypatch.setattr(catalog, "write_csvs", lambda cov, out: None)
    monkeypatch.setattr(catalog, "monsters_table_md", lambda cov: "")


def test_zero_turn_wins_are_not_shown_as_a_held_out_loss(tmp_path, monkeypatch):
    _stub_coverage(monkeypatch)
    row = {
        "deck": "d", "act": 1, "room": "普通", "result": "win", "turns": 0, "hp_lost": 0,
        "dmg_total": 0, "cards": {"打击": [1, 6, 0, 1]}, "max_actions": 1, "enc_name": "甲",
    }
    meta = {"exp": {"name": "edge", "title": "边界", "decks": ["d"], "rooms": ["普通"],
                    "seed": 1, "fights": 1}, "n_tasks": 1, "jobs": 1, "wall_secs": 0.2}
    (tmp_path / "raw.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    (tmp_path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    path = make_report(str(tmp_path), _Mods())
    text = open(path, encoding="utf-8").read()
    assert "模组·甲" in text and "打击" in text
    assert "100% / 0.0 /" in text
    assert "100% / 撑" not in text


def test_report_load_keeps_non_ascii_names_across_blank_lines_bom_and_utf16(tmp_path):
    row = {"deck": "模组", "cards": {"打击": [1, 6, 0, 1]}, "enc_name": "甲"}
    body = json.dumps(row, ensure_ascii=False) + "\n\n"
    meta = {"exp": {"decks": ["模组"]}}

    utf8 = tmp_path / "utf8"
    utf8.mkdir()
    (utf8 / "raw.jsonl").write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    (utf8 / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    rows, loaded = _load(str(utf8))
    assert rows[0]["cards"]["打击"] == [1, 6, 0, 1]
    assert loaded["exp"]["decks"] == ["模组"]

    wide = tmp_path / "utf16"
    wide.mkdir()
    (wide / "raw.jsonl").write_bytes(body.encode("utf-16"))
    (wide / "meta.json").write_bytes(json.dumps(meta, ensure_ascii=False).encode("utf-16"))
    rows, _meta = _load(str(wide))
    assert list(rows[0]["cards"]) == ["打击"]
    assert rows[0]["deck"] == "模组"
