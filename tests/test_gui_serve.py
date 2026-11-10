"""DeckBench --serve is the headless HTTP entry. It must not require a game install.

Opening the window still runs the game check. These tests do not bind the API
or start uvicorn.
"""
import os
import sys

import pytest

from gui import app


def test_serve_skips_game_setup(monkeypatch):
    seen = {}

    def serve(port, block=True):
        seen["port"] = port
        seen["block"] = block

    def game_check():
        seen["game"] = True

    monkeypatch.setattr(app, "serve", serve)
    monkeypatch.setattr(app, "_ensure_game_or_exit", game_check)
    monkeypatch.setattr(sys, "argv", ["DeckBench", "--serve", "--port", "18765"])
    app.main()
    assert seen["port"] == 18765
    assert seen["block"] is True
    assert "game" not in seen


def test_serve_records_game_dir_without_setup(monkeypatch):
    monkeypatch.delenv("DECKBENCH_GAME_DIR", raising=False)
    seen = {}

    def serve(port, block=True):
        seen["serve"] = port

    def game_check():
        raise AssertionError("game setup")

    monkeypatch.setattr(app, "serve", serve)
    monkeypatch.setattr(app, "_ensure_game_or_exit", game_check)
    monkeypatch.setattr(
        sys, "argv",
        ["DeckBench", "--game-dir", r"D:\Games\Example", "--serve", "--port", "9"],
    )
    app.main()
    assert seen["serve"] == 9
    assert os.environ["DECKBENCH_GAME_DIR"] == r"D:\Games\Example"


def test_window_still_requires_game(monkeypatch):
    def game_check():
        raise SystemExit(2)

    monkeypatch.setattr(app, "_ensure_game_or_exit", game_check)
    monkeypatch.setattr(sys, "argv", ["DeckBench"])
    with pytest.raises(SystemExit) as exc:
        app.main()
    assert exc.value.code == 2
