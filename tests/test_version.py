"""Project version and the optional GitHub release check.

The version number is ``sts2sim.__version__`` (0.1.5). These tests do not
bump it, and they do not call GitHub: the network is a fake ``fetch``.
"""
import json
import os
import urllib.error
import urllib.request

import pytest

from sts2sim.version import (
    RELEASES_LATEST,
    RELEASES_PAGE,
    canonical_semver,
    check_latest,
    compare_semver,
    read_project_version,
    version_info_text,
    windows_file_version,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_project_version_is_the_existing_number():
    init = os.path.join(ROOT, "sts2sim", "__init__.py")
    with open(init, encoding="utf-8") as handle:
        text = handle.read()
    assert '__version__ = "0.1.5"' in text
    assert read_project_version(ROOT) == "0.1.5"
    with open(os.path.join(ROOT, "gui", "web", "package.json"), encoding="utf-8") as handle:
        pkg = json.load(handle)
    assert pkg["version"] == "0.1.5"


def test_semver_order():
    assert compare_semver("0.1.5", "0.1.5") == 0
    assert compare_semver("0.1.5", "v0.1.5") == 0
    assert compare_semver("0.1.5+local", "0.1.5") == 0
    assert compare_semver("0.1.9", "0.1.10") == -1
    assert compare_semver("0.1.10", "0.1.9") == 1
    assert compare_semver("0.1.5", "0.2.0") == -1
    assert compare_semver("1.0.0", "0.9.9") == 1
    assert compare_semver("0.1.5-rc.1", "0.1.5") == -1
    assert compare_semver("0.1.5", "0.1.5-rc.1") == 1
    assert compare_semver("0.1.5-rc.1", "0.1.5-rc.2") == -1
    assert compare_semver("0.1.5-alpha", "0.1.5-alpha.1") == -1
    assert compare_semver("0.1.5-alpha.1", "0.1.5-alpha.beta") == -1
    assert compare_semver("0.1.5-alpha", "0.1.5-beta") == -1
    assert canonical_semver("v0.1.5+build.7") == "0.1.5"
    with pytest.raises(ValueError):
        compare_semver("0.1", "0.1.5")
    with pytest.raises(ValueError):
        compare_semver("01.2.3", "0.1.5")
    with pytest.raises(ValueError):
        compare_semver("latest", "0.1.5")


def test_windows_file_version_and_pyinstaller_text():
    assert windows_file_version("0.1.5") == "0.1.5.0"
    assert windows_file_version("v1.2.3-rc.1") == "1.2.3.0"
    text = version_info_text("0.1.5")
    assert "filevers=(0, 1, 5, 0)" in text
    assert "prodvers=(0, 1, 5, 0)" in text
    assert "StringStruct('ProductVersion', '0.1.5')" in text
    assert "StringStruct('FileVersion', '0.1.5.0')" in text
    assert text.isascii()
    compile(text, "<version-info>", "exec")


def _release(tag, url=None, status=200):
    body = json.dumps({
        "tag_name": tag,
        "html_url": url or f"https://github.com/Nopsil/deckbench/releases/tag/{tag}",
    }).encode()

    def fetch(got_url, timeout):
        assert got_url == RELEASES_LATEST
        assert timeout > 0
        return status, {}, body

    return fetch


def test_check_latest_compares_without_calling_the_network():
    same = check_latest(current="0.1.5", fetch=_release("v0.1.5"))
    assert same["ok"] is True and same["status"] == "up_to_date"
    assert same["current"] == "0.1.5" and same["latest"] == "0.1.5"
    assert same["message"] == "Up to date."

    newer = check_latest(current="0.1.5", fetch=_release("v0.2.0"))
    assert newer["status"] == "update_available" and newer["latest"] == "0.2.0"
    assert newer["message"] == "New version 0.2.0 available."
    assert newer["html_url"] == "https://github.com/Nopsil/deckbench/releases/tag/v0.2.0"

    older = check_latest(current="0.1.5", fetch=_release("v0.1.4"))
    assert older["status"] == "up_to_date" and older["latest"] == "0.1.4"

    pre = check_latest(current="0.1.5-rc.1", fetch=_release("v0.1.5"))
    assert pre["status"] == "update_available"

    current = check_latest(fetch=_release("v0.1.5"))
    assert current["current"] == "0.1.5" and current["status"] == "up_to_date"


def test_check_latest_rejects_a_non_github_link():
    fetched = check_latest(
        current="0.1.5",
        fetch=_release("v0.2.0", url="https://evil.example/phish"),
    )
    assert fetched["status"] == "update_available"
    assert fetched["html_url"] == RELEASES_PAGE


def test_check_latest_offline_rate_limit_and_missing_release():
    def offline(url, timeout):
        raise urllib.error.URLError("no route")

    def timed_out(url, timeout):
        raise TimeoutError("timed out")

    off = check_latest(current="0.1.5", fetch=offline)
    assert off["ok"] is False and off["status"] == "offline"
    assert check_latest(current="0.1.5", fetch=timed_out)["status"] == "offline"

    def limited(url, timeout):
        return 403, {"X-RateLimit-Remaining": "0"}, b'{"message":"API rate limit exceeded"}'

    hit = check_latest(current="0.1.5", fetch=limited)
    assert hit["ok"] is False and hit["status"] == "rate_limited"
    assert "rate limit" in hit["message"].lower()

    def again(url, timeout):
        return 429, {}, b"secondary rate limit"

    assert check_latest(current="0.1.5", fetch=again)["status"] == "rate_limited"

    def missing(url, timeout):
        return 404, {}, b'{"message":"Not Found"}'

    none = check_latest(current="0.1.5", fetch=missing)
    assert none["status"] == "not_published" and none["ok"] is False

    def broken(url, timeout):
        return 200, {}, b"not-json"

    assert check_latest(current="0.1.5", fetch=broken)["status"] == "error"

    def bad_tag(url, timeout):
        return 200, {}, json.dumps({"tag_name": "nightly"}).encode()

    assert check_latest(current="0.1.5", fetch=bad_tag)["status"] == "error"

    def server(url, timeout):
        return 500, {}, b"nope"

    assert check_latest(current="0.1.5", fetch=server)["status"] == "error"


def test_version_endpoint_matches_the_project_and_does_not_call_github(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    def boom(*_args, **_kwargs):
        raise AssertionError("GitHub was contacted")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    from gui.server import app

    with TestClient(app) as client:
        res = client.get("/api/version")
        assert res.status_code == 200
        assert res.json() == {"name": "DeckBench", "version": "0.1.5"}
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.1.5"


def test_update_endpoint_uses_the_mocked_release(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app

    def fetch(url, timeout):
        assert url == RELEASES_LATEST
        return 200, {}, json.dumps({
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/Nopsil/deckbench/releases/tag/v9.9.9",
        }).encode()

    monkeypatch.setattr("sts2sim.version.default_fetch", fetch)
    with TestClient(app) as client:
        res = client.post("/api/updates/check")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "update_available"
    assert body["current"] == "0.1.5" and body["latest"] == "9.9.9"
    assert body["html_url"].startswith("https://github.com/Nopsil/deckbench/")


def test_update_endpoint_reports_rate_limit(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app

    def fetch(url, timeout):
        return 429, {}, b'{"message":"API rate limit exceeded"}'

    monkeypatch.setattr("sts2sim.version.default_fetch", fetch)
    with TestClient(app) as client:
        res = client.post("/api/updates/check")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False and body["status"] == "rate_limited"


def test_gui_checks_for_updates_only_from_the_button():
    with open(os.path.join(ROOT, "gui", "web", "src", "App.vue"), encoding="utf-8") as handle:
        src = handle.read()
    assert "/api/updates/check" in src
    assert "method: 'POST'" in src
    mounted = src.split("onMounted(() => {", 1)[1].split("onUnmounted", 1)[0]
    assert "updates" not in mounted
    assert "/api/version" in mounted


def test_read_version_script_prints_the_project_version():
    import subprocess
    import sys
    script = os.path.join(ROOT, "gui", "packaging", "read_version.py")
    got = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, check=True)
    assert got.stdout.strip() == "0.1.5"


def test_mcp_check_update_is_optional_and_uses_the_same_result(monkeypatch):
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return 200, {}, json.dumps({
            "tag_name": "v0.1.5",
            "html_url": "https://github.com/Nopsil/deckbench/releases/tag/v0.1.5",
        }).encode()

    monkeypatch.setattr("sts2sim.version.default_fetch", fetch)
    from tools import mcp_server
    try:
        import mcp
    except ImportError:
        mcp = None
    if mcp is not None:
        mcp_server.build_import()
        assert calls == []
    doc = json.loads(mcp_server.check_update())
    assert doc["status"] == "up_to_date" and doc["latest"] == "0.1.5"
    assert calls == [RELEASES_LATEST]
