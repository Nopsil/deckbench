"""gameloc：从（合成的）Godot .pck 里读本地化表；不需要游戏。"""
import hashlib
import json
import struct

from sts2sim import gameloc


def _make_pck(path, files):
    names = list(files)
    def entries(offs):
        out = b""
        for n, off in zip(names, offs):
            nb = ("res://" + n).encode() + b"\0"
            b = files[n]
            out += struct.pack("<I", len(nb)) + nb + struct.pack("<QQ", off, len(b)) + hashlib.md5(b).digest() + struct.pack("<I", 0)
        return out
    head = 24 + 8 + 64 + 4 + len(entries([0] * len(names)))
    offs, o = [], head
    for n in names:
        offs.append(o)
        o += len(files[n])
    with open(path, "wb") as f:
        f.write(struct.pack("<6I", 0x43504447, 2, 4, 3, 0, 0) + struct.pack("<Q", 0) + b"\0" * 64
                + struct.pack("<I", len(names)) + entries(offs) + b"".join(files[n] for n in names))


def test_read_from_pck(tmp_path, monkeypatch):
    p = tmp_path / "game.pck"
    _make_pck(p, {"localization/eng/events.json": json.dumps({"X.title": "Hello"}).encode(),
                  "localization/zhs/cards.json": json.dumps({"A.title": "你好"}, ensure_ascii=False).encode(),
                  "images/other.png": b"\x89PNG"})
    monkeypatch.setenv("DECKBENCH_GAME_PCK", str(p))
    monkeypatch.delenv("DECKBENCH_GAME_LOC_ENG", raising=False)
    monkeypatch.delenv("DECKBENCH_GAME_LOC_ZHS", raising=False)
    gameloc._TABLES.clear(); gameloc._INDEX.clear()
    assert set(gameloc.read_pck_index(str(p))) == {("eng", "events"), ("zhs", "cards")}
    assert gameloc.table("events", "eng") == {"X.title": "Hello"}
    assert gameloc.table("cards", "zhs") == {"A.title": "你好"}
    assert gameloc.table("monsters", "zhs") is None
    gameloc._TABLES.clear(); gameloc._INDEX.clear()


def test_dir_override(tmp_path, monkeypatch):
    (tmp_path / "events.json").write_text(json.dumps({"K.title": "T"}), encoding="utf-8")
    monkeypatch.setenv("DECKBENCH_GAME_LOC_ENG", str(tmp_path))
    gameloc._TABLES.clear()
    assert gameloc.table("events", "eng") == {"K.title": "T"}
    gameloc._TABLES.clear()
