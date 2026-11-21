"""Custom-card library: schema reuse, no code execution, save/reopen, combat test."""
import os

import pytest
import yaml

from sts2sim.cards import OPS
from sts2sim.customcards import (
    blank,
    expand_effects,
    expr_names_cover_safe_calls,
    prepare_save,
    supported_ops,
    validate_library,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUICK = os.path.join(ROOT, "experiments", "quick.yaml")
EN = {"x-lang": "en"}


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


def test_supported_ops_match_the_combat_engine_without_py():
    assert "py" not in supported_ops()
    assert set(supported_ops()) == set(OPS) - {"py"}
    assert expr_names_cover_safe_calls() == []


def test_py_attribute_and_unknown_name_are_rejected():
    lib = blank()
    lib["cards"][0]["effects"] = [{"op": "py", "fn": "boom"}]
    refused = validate_library(lib)
    assert refused["ok"] is False
    assert any("py" in item["en"].lower() or "python" in item["en"].lower() for item in refused["problems"])

    lib = blank()
    lib["cards"][0]["effects"] = [{"op": "damage", "amount": "().__class__"}]
    refused = validate_library(lib)
    assert refused["ok"] is False
    assert any("attribute" in item["en"].lower() for item in refused["problems"])

    lib = blank()
    lib["cards"][0]["effects"] = [{"op": "damage", "amount": "draw_size"}]
    refused = validate_library(lib)
    assert refused["ok"] is False

    lib = blank()
    lib["hooks"] = "hooks.py"
    refused = validate_library(lib)
    assert refused["ok"] is False


def test_template_round_trip_keeps_the_form_and_expands_the_engine_file(tmp_path):
    lib = blank()
    lib["name"] = "spark_cards"
    lib["cards"][0]["effects"] = [{"template": "gain_power", "power": "STRENGTH", "amount": "dmg"}]
    checked = validate_library(lib)
    assert checked["ok"], checked["problems"]
    library, files, _warnings = prepare_save(lib)
    assert library["cards"][0]["effects"][0]["template"] == "gain_power"
    loaded = yaml.safe_load(files["cards.yaml"])
    assert loaded[0]["effects"] == [{"op": "apply", "power": "STRENGTH", "amount": "dmg", "target": "self"}]
    assert loaded[0]["type"] == "攻击"
    assert expand_effects([{"op": "block", "amount": 3}]) == [{"op": "block", "amount": 3}]
    folder = tmp_path / "spark_cards"
    folder.mkdir()
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    from sts2sim.customcards import read_library_dir
    again = read_library_dir(str(folder))
    assert again["cards"][0]["effects"][0]["template"] == "gain_power"
    assert again["cards"][0]["name"] == "Jab"
    assert again["character"]["hp"] == 70


def test_http_save_reopen_and_reject_code(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app

    before = _read(QUICK)
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    monkeypatch.delenv("DECKBENCH_PRESETS_DIR", raising=False)
    lib = blank()
    lib["name"] = "editor_cards"
    lib["title"] = "Editor cards"
    lib["cards"][0]["name"] = "Test Jab"
    with TestClient(app) as client:
        saved = client.post("/api/custom-cards/save", headers=EN, json={"library": lib})
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["ok"] is True
        assert body["library"]["cards"][0]["name"] == "Test Jab"
        opened = client.get("/api/custom-cards/library/editor_cards", headers=EN)
        assert opened.status_code == 200
        assert opened.json()["cards"][0]["name"] == "Test Jab"
        bad = blank()
        bad["name"] = "editor_cards"
        bad["cards"][0]["effects"] = [{"op": "py", "fn": "boom"}]
        refused = client.post("/api/custom-cards/validate", headers=EN, json={"library": bad})
        assert refused.status_code == 200
        assert refused.json()["ok"] is False
        assert "Traceback" not in refused.text
    assert _read(QUICK) == before
    engine = (tmp_path / "mods" / "editor_cards" / "cards.yaml").read_text(encoding="utf-8")
    assert "fn:" not in engine
    assert not (tmp_path / "mods" / "editor_cards" / "hooks.py").exists()


def test_import_refuses_python_and_does_not_execute(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import io
    import zipfile

    from fastapi.testclient import TestClient

    from gui.server import app

    monkeypatch.setenv("STS2SIM_GUI_DATA", str(tmp_path))
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as zf:
        zf.writestr("mod.yaml", "name: nope\n")
        zf.writestr("hooks.py", "raise SystemExit('ran')\n")
    with TestClient(app) as client:
        res = client.post(
            "/api/custom-cards/import",
            headers=EN,
            files={"file": ("mod.zip", blob.getvalue(), "application/zip")},
        )
    assert res.status_code == 400
    assert "Traceback" not in res.text
    assert "ran" not in res.text
    assert not (tmp_path / "mods" / "nope").exists()
