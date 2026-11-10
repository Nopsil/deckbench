"""GET /api/changelog parses the latest CHANGELOG.md section as text.

The body is JSON, not HTML. A ``<script>`` or a ``javascript:`` link in the
file stays text. The Windows package copies ``CHANGELOG.md`` into the
PyInstaller bundle and next to the exe.
"""
import json
import os
import sys

import pytest

from gui.changelog import (
    ChangelogError,
    load_changelog,
    parse_changelog,
    safe_href,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")


def _plain(spans):
    out = []
    for span in spans or []:
        kind = span.get("t")
        if kind in ("text", "code"):
            out.append(span.get("s") or "")
        elif span.get("c"):
            out.append(_plain(span["c"]))
    return "".join(out)


def _walk(blocks, found):
    for block in blocks:
        found.append(block)
        if block.get("kind") == "ul":
            for item in block.get("items") or []:
                _walk(item.get("blocks") or [], found)


def _hrefs(node, out):
    if isinstance(node, dict):
        if node.get("t") == "link":
            out.append(node.get("href"))
        for value in node.values():
            _hrefs(value, out)
    elif isinstance(node, list):
        for value in node:
            _hrefs(value, out)


def test_latest_section_is_015_and_stops_before_014():
    parsed = load_changelog("0.1.5", CHANGELOG)
    assert parsed["version"] == "0.1.5"
    assert parsed["heading"].startswith("未发布（0.1.5）")
    assert "Unreleased (0.1.5)" in parsed["heading"]
    blocks = []
    _walk(parsed["blocks"], blocks)
    text = json.dumps(parsed, ensure_ascii=False)
    headings = [
        _plain(block["spans"])
        for block in blocks
        if block.get("kind") == "h" and block.get("level") == 3
    ]
    assert headings[0] == "本版更新"
    for title in ("中英切换", "战斗进程", "版本号和检查更新", "单卡贡献", "测试进度和取消", "组牌对打"):
        assert title in headings
    assert "界面多语言" not in text
    assert "未发布（0.1.4）" not in text
    assert "<id>" in text
    assert all(not str(href).lower().startswith("javascript:") for href in _collect(parsed))


def _collect(parsed):
    found = []
    _hrefs(parsed, found)
    return found


def test_html_and_javascript_links_stay_text():
    sample = """## Dangerous

See <script>alert(1)</script> and <img src=x onerror=alert(1)>.

- <b>nope</b> [click](javascript:alert(1))
  [ok](https://github.com/Nopsil/deckbench/releases)

[bad](data:text/html,hi)

## 未发布（0.1.4） / Unreleased (0.1.4)

not this section
"""
    parsed = parse_changelog(sample)
    parsed["version"] = "0.1.5"
    text = json.dumps(parsed, ensure_ascii=False)
    assert "<script>alert(1)</script>" in text
    assert "onerror=alert(1)" in text
    assert "not this section" not in text
    hrefs = _collect(parsed)
    assert hrefs == ["https://github.com/Nopsil/deckbench/releases"]
    assert "javascript:" not in json.dumps(hrefs)
    assert safe_href("javascript:alert(1)") is None
    assert safe_href("data:text/html,hi") is None
    assert safe_href("https://example.test/a") == "https://example.test/a"
    blocks = []
    _walk(parsed["blocks"], blocks)
    kinds = {block["kind"] for block in blocks}
    assert kinds <= {"p", "h", "ul", "pre"}


def test_missing_and_oversized_changelog(tmp_path):
    missing = tmp_path / "nope.md"
    with pytest.raises(ChangelogError):
        load_changelog("0.1.5", str(missing))
    big = tmp_path / "CHANGELOG.md"
    big.write_bytes(b"## Big\n\n" + b"x" * (2_000_001))
    with pytest.raises(ChangelogError):
        load_changelog("0.1.5", str(big))


def test_frozen_bundle_is_preferred(tmp_path, monkeypatch):
    from gui import paths
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "CHANGELOG.md").write_text("## Bundled\n\nHello from the package.\n", encoding="utf-8")
    beside = tmp_path / "app"
    beside.mkdir()
    (beside / "CHANGELOG.md").write_text("## Beside\n\nnope\n", encoding="utf-8")
    monkeypatch.setattr(paths, "FROZEN", True)
    monkeypatch.setattr(paths, "APP_DIR", str(beside))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    got = load_changelog("0.1.5")
    assert got["heading"] == "Bundled"
    assert got["version"] == "0.1.5"
    assert "Hello from the package." in json.dumps(got, ensure_ascii=False)
    assert "nope" not in json.dumps(got)


def test_api_changelog_is_json_without_a_stack():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app

    with TestClient(app) as client:
        res = client.get("/api/changelog")
    assert res.status_code == 200
    assert "json" in res.headers["content-type"]
    assert "text/html" not in res.headers["content-type"]
    body = res.json()
    assert body["version"] == "0.1.5"
    assert "战斗进程" in json.dumps(body, ensure_ascii=False)
    raw = res.text.lower()
    assert "<script" not in raw
    assert "traceback" not in raw


def test_api_changelog_missing_file_has_no_stack(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.changelog import ChangelogError
    from gui.server import app

    def boom(version, path=None):
        raise ChangelogError("missing /secret/CHANGELOG.md")

    monkeypatch.setattr("gui.server.load_changelog", boom)
    with TestClient(app) as client:
        res = client.get("/api/changelog", headers={"x-lang": "en"})
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert detail == "The changelog could not be read."
    assert "secret" not in detail
    assert "Traceback" not in res.text


def test_gui_renders_changelog_as_text_not_html():
    web = os.path.join(ROOT, "gui", "web", "src")
    for rel in (
        "pages/WhatsNew.vue",
        "components/ChangelogBlocks.vue",
        "components/Spans.vue",
        "App.vue",
    ):
        with open(os.path.join(web, rel), encoding="utf-8") as handle:
            text = handle.read()
        assert "v-html" not in text, rel
    with open(os.path.join(web, "App.vue"), encoding="utf-8") as handle:
        app = handle.read()
    assert "whatsnew.dismissed." in app
    assert "/whatsnew" in app
    assert 'data-testid="whatsnew-panel"' in app
    assert 'data-testid="whatsnew-footer"' in app
    assert 'data-testid="whatsnew-about"' in app
    with open(os.path.join(web, "main.js"), encoding="utf-8") as handle:
        main = handle.read()
    assert "path: '/whatsnew'" in main


def test_package_bundles_changelog_and_ps1_keeps_its_bom():
    with open(os.path.join(ROOT, "gui", "packaging", "DeckBench.spec"), encoding="utf-8") as handle:
        spec = handle.read()
    assert "CHANGELOG.md" in spec
    assert "_changelog_source" in spec
    build_path = os.path.join(ROOT, "gui", "packaging", "build.ps1")
    with open(build_path, "rb") as handle:
        raw = handle.read()
    assert raw.startswith(b"\xef\xbb\xbf")
    build = raw.decode("utf-8-sig")
    assert 'Copy-Item (Join-Path $Repo "CHANGELOG.md") (Join-Path $src "CHANGELOG.md")' in build
    assert 'Copy-Item (Join-Path $Repo "CHANGELOG.md") (Join-Path $app "CHANGELOG.md")' in build
    manifest_path = os.path.join(ROOT, "gui", "packaging", "ship-manifest.txt")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = handle.read()
    assert "app/CHANGELOG.md" in manifest
