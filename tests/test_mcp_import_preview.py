"""MCP 的导入摘要、目录批量摘要和种子预览：不启动游戏，用存档夹具和种子预览的桩。

没装 mcp 时，注册检查会跳过；函数本身不依赖这个包。
"""
import asyncio
import importlib.util
import json
import os
import sys

import pytest

from sts2sim.engine.seedpreview import PUBLIC_KEYS
from sts2sim.saveimport import load_path, summarize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "tests", "fixtures", "saves", "sample_history.run")
LIVE = os.path.join(ROOT, "tests", "fixtures", "saves", "sample_live.save")


def _load(name, filename):
    if name in sys.modules:
        return sys.modules[name]
    path = os.path.join(ROOT, "tools", filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mcp():
    return _load("deckbench_mcp_server_under_test", "mcp_server.py")


def _import_cli():
    return _load("deckbench_import_run_for_mcp", "import_run.py")


def _preview_cli():
    return _load("deckbench_seed_preview_for_mcp", "seed_preview.py")


def _tool_text(result):
    if isinstance(result, tuple):
        result = result[0]
    return "".join(getattr(block, "text", "") for block in result)


def test_import_save_matches_summary_and_cli(capsys):
    mcp = _mcp()
    cli = _import_cli()
    text = mcp.import_save(HIST)
    assert "\n" not in text
    doc = json.loads(text)
    assert doc == summarize(load_path(HIST))
    assert cli.main([HIST, "--summary"]) == 0
    assert json.loads(capsys.readouterr().out) == doc
    assert doc["ok"] is True and doc["read_only"] is True
    assert doc["seed"] == "SAMPLESEED01" and doc["ascension"] == 3
    assert doc["floor_reached"] == 3
    card_ids = [c["id"] for c in doc["highlights"]["cards"]]
    relic_ids = [r["id"] for r in doc["highlights"]["relics"]]
    assert "CARD.SAMPLE_PICK" in card_ids
    assert "RELIC.SAMPLE_CHEST" in relic_ids
    live = json.loads(mcp.import_save(LIVE))
    assert live["ok"] is True and live["seed"] == "LIVESEED0001"
    assert live["kind"] == "live_save"


def _tree_bytes(root):
    out = {}
    for dirpath, dirnames, names in os.walk(root):
        dirnames.sort()
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root)] = fh.read()
    return out


def test_import_history_batch_matches_cli_and_does_not_write(tmp_path, capsys):
    mcp = _mcp()
    cli = _import_cli()
    saves = tmp_path / "profile" / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "sample.run").write_bytes(open(HIST, "rb").read())
    (hist / "bad.run").write_text("not-json", encoding="utf-8")
    (hist / "notes.txt").write_text("ignore", encoding="utf-8")
    (saves / "current_run.save").write_bytes(open(LIVE, "rb").read())
    (saves / "progress.save").write_text("{}", encoding="utf-8")
    before = _tree_bytes(saves)
    fixture_before = {HIST: open(HIST, "rb").read(), LIVE: open(LIVE, "rb").read()}

    assert cli.main([str(saves), "--batch-summary"]) == 0
    array_text = capsys.readouterr().out
    assert mcp.import_history_batch(str(saves)) == array_text
    assert mcp.import_history_batch(str(hist), lines=False) == array_text
    rows = json.loads(array_text)
    assert rows == [
        {"file": "bad.run", "error": "not_json"},
        {
            "file": "sample.run",
            "seed": "SAMPLESEED01",
            "ascension": 3,
            "character": "Ironclad",
            "floors": 3,
            "result": "lost",
        },
    ]
    assert list(rows[1]) == ["file", "seed", "ascension", "character", "floors", "result"]
    assert list(rows[0]) == ["file", "error"]
    assert "highlights" not in array_text
    assert "LIVESEED" not in array_text
    assert "current_run.save" not in array_text

    assert cli.main([str(saves), "--batch-summary", "--lines"]) == 0
    lines_text = capsys.readouterr().out
    assert mcp.import_history_batch(str(hist), lines=True) == lines_text
    assert [json.loads(line) for line in lines_text.splitlines()] == rows
    assert lines_text.endswith("\n") and lines_text.count("\n") == len(rows)

    assert cli.main([HIST, "--batch-summary"]) == 0
    one = capsys.readouterr().out
    assert mcp.import_history_batch(HIST) == one
    assert json.loads(one)[0]["result"] == "lost" and "highlights" not in one

    assert cli.main([LIVE, "--batch-summary"]) == 0
    live = capsys.readouterr().out
    assert mcp.import_history_batch(LIVE) == live
    live_row = json.loads(live)[0]
    assert live_row["seed"] == "LIVESEED0001" and "result" not in live_row
    assert list(live_row) == ["file", "seed", "ascension", "character", "floors"]

    assert _tree_bytes(saves) == before
    assert open(HIST, "rb").read() == fixture_before[HIST]
    assert open(LIVE, "rb").read() == fixture_before[LIVE]


def test_import_history_batch_errors_match_cli(tmp_path, capsys, monkeypatch):
    mcp = _mcp()
    cli = _import_cli()

    missing = tmp_path / "nope"
    assert cli.main([str(missing), "--batch-summary", "--lang", "en"]) == 2
    captured = capsys.readouterr()
    assert captured.out
    assert mcp.import_history_batch(str(missing)) == captured.out
    assert mcp.import_history_batch(str(missing), lines=True) == captured.out
    body = json.loads(captured.out)
    assert body["ok"] is False and body["read_only"] is True and body["error"] == "not_found"
    assert not missing.exists()

    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main([str(empty), "--batch-summary"]) == 2
    empty_out = capsys.readouterr().out
    assert mcp.import_history_batch(str(empty)) == empty_out
    assert json.loads(empty_out)["error"] == "dir_empty"
    assert list(empty.iterdir()) == []

    only = tmp_path / "only-live"
    only.mkdir()
    live_bytes = open(LIVE, "rb").read()
    (only / "current_run.save").write_bytes(live_bytes)
    assert cli.main([str(only), "--batch-summary"]) == 0
    blank = capsys.readouterr().out
    assert mcp.import_history_batch(str(only)) == blank
    assert json.loads(blank) == []
    assert cli.main([str(only), "--batch-summary", "--lines"]) == 0
    assert capsys.readouterr().out == ""
    assert mcp.import_history_batch(str(only), lines=True) == ""
    assert (only / "current_run.save").read_bytes() == live_bytes

    bad = tmp_path / "bad.run"
    bad.write_bytes(b"\x00\x01")
    before_bad = bad.read_bytes()
    assert cli.main([str(bad), "--batch-summary", "--lines", "--lang", "en"]) == 2
    err = capsys.readouterr().out
    assert mcp.import_history_batch(str(bad), lines=True) == err
    assert json.loads(err)["error"] == "not_json" and json.loads(err)["read_only"] is True
    assert bad.read_bytes() == before_bad

    cap = tmp_path / "capped" / "history"
    cap.mkdir(parents=True)
    (cap / "a.run").write_bytes(open(HIST, "rb").read())
    (cap / "b.run").write_bytes(open(HIST, "rb").read())
    monkeypatch.setattr("sts2sim.saveimport.MAX_FILES", 1)
    assert cli.main([str(cap), "--batch-summary"]) == 0
    capped = capsys.readouterr().out
    assert mcp.import_history_batch(str(cap)) == capped
    capped_rows = json.loads(capped)
    assert len(capped_rows) == 2
    assert capped_rows[0]["file"] == "a.run" and capped_rows[0]["seed"] == "SAMPLESEED01"
    assert capped_rows[1] == {"error": "truncated", "n": 1}
    assert list(capped_rows[1]) == ["error", "n"]


def test_import_save_folder_and_errors_stay_json(tmp_path):
    mcp = _mcp()
    saves = tmp_path / "saves"
    hist = saves / "history"
    hist.mkdir(parents=True)
    (hist / "1.run").write_bytes(open(HIST, "rb").read())
    (hist / "bad.run").write_text("not-json", encoding="utf-8")
    doc = json.loads(mcp.import_save(str(saves)))
    assert doc["ok"] is True and doc["kind"] == "folder" and doc["read_only"] is True
    assert doc["count"] == 1 and doc["entries"][0]["seed"] == "SAMPLESEED01"
    assert doc["failures"][0]["error"] == "not_json"
    missing = json.loads(mcp.import_save(str(tmp_path / "nope.run")))
    assert missing["ok"] is False and missing["read_only"] is True and missing["error"] == "not_found"
    assert missing["path"] == os.path.abspath(str(tmp_path / "nope.run"))
    empty = tmp_path / "empty"
    empty.mkdir()
    blank = json.loads(mcp.import_save(str(empty)))
    assert blank["ok"] is False and blank["error"] == "dir_empty"


def test_seed_preview_schema_lists_stable_fields():
    mcp = _mcp()
    body = json.loads(mcp.seed_preview_schema())
    assert body["keys"] == list(PUBLIC_KEYS)
    assert body["v"] == 1
    assert body["neow"][:3] == ["first", "all", "none"]
    assert body["character"] == ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]
    assert body["ascension"] == {"min": 0, "max": 10}


def test_seed_preview_rejects_before_the_engine():
    mcp = _mcp()
    assert json.loads(mcp.seed_preview(""))["error"] == "need_seed"
    bad_char = json.loads(mcp.seed_preview("ABC", character="Nope"))
    assert bad_char["ok"] is False and bad_char["error"] == "bad_char" and bad_char["char"] == "Nope"
    assert json.loads(mcp.seed_preview("ABC", ascension=99))["error"] == "bad_asc"
    assert json.loads(mcp.seed_preview("ABC", neow="nope"))["error"] == "bad_neow"
    assert "maps" not in json.loads(mcp.seed_preview("ABC", neow="nope"))


def test_seed_preview_without_engine_is_json(monkeypatch):
    from test_seedpreview import _block_engine
    _block_engine(monkeypatch)
    body = json.loads(_mcp().seed_preview("ABCDEFGHJKLM", neow="all"))
    assert body["ok"] is False and body["error"] == "no_engine"
    assert body["err"]


def test_seed_preview_matches_cli_json_and_neow_selector(monkeypatch, capsys):
    from test_seedpreview import _use_stub
    _use_stub(monkeypatch)
    mcp = _mcp()
    cli = _preview_cli()
    stored = []

    def forbid_cache(*_a, **_k):
        stored.append(True)
        raise AssertionError("default preview must not write a cache")

    monkeypatch.setattr("sts2sim.engine.seedpreview.cache_store", forbid_cache)
    for neow, keys in (("first", {"1"}), ("all", {"0", "1", "2"}), ("none", set()), ("2", {"2"})):
        assert cli.main(["ABCDEFGHJKLM", "--char", "Ironclad", "--asc", "0", "--neow", neow, "--json", "-"]) == 0
        cli_text = capsys.readouterr().out
        tool_text = mcp.seed_preview("ABCDEFGHJKLM", character="Ironclad", ascension=0, neow=neow)
        assert tool_text == cli_text
        doc = json.loads(tool_text)
        assert list(doc) == list(PUBLIC_KEYS)
        assert "ok" not in doc
        assert set(doc["after_neow"]) == keys
        assert doc["seed"] == "ABCDEFGHJKLM" and doc["v"] == 1
        node = doc["maps"][0]["rows"][0][0]
        assert set(node) == {"col", "row", "type"}
        assert set(doc["neow_options"][0]) == {"index", "key", "id", "locked"}
        assert set(doc["relics"]) == {"starting", "shared_queue", "character_queue"}
    assert stored == []
    normalized = json.loads(mcp.seed_preview("oooooooooooo", character="Silent", ascension=10, neow="none"))
    assert normalized["seed"] == "000000000000" and normalized["character"] == "Silent"
    assert normalized["ascension"] == 10 and normalized["after_neow"] == {}


def test_seed_preview_cache_keeps_the_selector(tmp_path, monkeypatch):
    from test_seedpreview import _use_stub
    _use_stub(monkeypatch)
    mcp = _mcp()
    text = mcp.seed_preview("ABCDEFGHJKLM", neow="first", cache=True, cache_dir=str(tmp_path))
    doc = json.loads(text)
    assert set(doc["after_neow"]) == {"1"}
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["key"] == {"seed": "ABCDEFGHJKLM", "char": "Ironclad", "asc": 0, "neow": "first"}
    assert list(payload["preview"]) == list(PUBLIC_KEYS)
    refused = json.loads(mcp.seed_preview("ABCDEFGHJKLM", neow="none", cache=True, cache_dir=ROOT))
    assert refused["ok"] is False and refused["error"] == "cache_in_repo"
    assert not list(tmp_path.glob("*.tmp"))


def test_server_registers_preview_and_import_only_stays_import(monkeypatch):
    pytest.importorskip("mcp")
    from test_seedpreview import _use_stub
    _use_stub(monkeypatch)
    mcp = _mcp()
    play = mcp.build()
    tools = {t.name: t for t in play._tool_manager.list_tools()}
    names = [t.name for t in play._tool_manager.list_tools()]
    for name in ("new_run", "import_save", "import_history_batch", "seed_preview", "list_styles", "act"):
        assert name in names
    i = names.index("import_save")
    assert names[i:i + 3] == ["import_save", "import_history_batch", "seed_preview"]
    batch_params = tools["import_history_batch"].parameters
    assert batch_params["required"] == ["path"]
    assert set(batch_params["properties"]) >= {"path", "lines"}
    assert batch_params["properties"]["lines"].get("type") == "boolean"
    assert "batch-summary" in tools["import_history_batch"].description
    assert "result" in tools["import_history_batch"].description
    params = tools["seed_preview"].parameters
    assert params["required"] == ["seed"]
    assert set(params["properties"]) >= {"seed", "character", "ascension", "neow", "cache", "cache_dir"}
    assert "first" in tools["seed_preview"].description
    assert "after_neow" in tools["seed_preview"].description
    uris = [str(r.uri) for r in play._resource_manager.list_resources()]
    assert uris == [mcp.SEED_PREVIEW_RESOURCE]
    blocks = asyncio.run(play.read_resource(mcp.SEED_PREVIEW_RESOURCE))
    assert json.loads(blocks[0].content)["keys"] == list(PUBLIC_KEYS)

    preview = json.loads(_tool_text(asyncio.run(play.call_tool("seed_preview", {
        "seed": "ABCDEFGHJKLM", "character": "Defect", "ascension": 0, "neow": "2",
    }))))
    assert preview["character"] == "Defect" and set(preview["after_neow"]) == {"2"}
    assert list(preview) == list(PUBLIC_KEYS)
    saved = json.loads(_tool_text(asyncio.run(play.call_tool("import_save", {"path": HIST}))))
    assert saved["seed"] == "SAMPLESEED01" and saved["ok"] is True
    batched = _tool_text(asyncio.run(play.call_tool("import_history_batch", {"path": HIST})))
    assert batched == mcp.import_history_batch(HIST)
    assert json.loads(batched)[0]["seed"] == "SAMPLESEED01" and "highlights" not in batched
    lined = _tool_text(asyncio.run(play.call_tool("import_history_batch", {"path": HIST, "lines": True})))
    assert lined == mcp.import_history_batch(HIST, lines=True)
    assert json.loads(lined)["result"] == "lost"

    only = mcp.build_import()
    only_names = [t.name for t in only._tool_manager.list_tools()]
    assert only_names == ["import_save", "import_history_batch"]
    assert "new_run" not in only_names and "seed_preview" not in only_names
    assert only._resource_manager.list_resources() == []
    only_text = _tool_text(asyncio.run(only.call_tool("import_history_batch", {"path": HIST, "lines": True})))
    assert only_text == mcp.import_history_batch(HIST, lines=True)
