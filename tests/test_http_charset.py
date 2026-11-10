"""JSON and text responses name UTF-8.

Windows PowerShell 5.1 decodes a body as ISO-8859-1 when Content-Type has no
charset. Chinese in the packaged API smoke then shows up as mojibake.
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from gui.server import app, with_utf8_charset

ZHS = {"x-lang": "zhs"}


def _flat(res):
    return "".join(res.headers["content-type"].split()).lower()


def test_charset_is_added_only_for_text_and_json():
    assert with_utf8_charset("application/json") == "application/json; charset=utf-8"
    assert with_utf8_charset("Application/JSON") == "Application/JSON; charset=utf-8"
    assert with_utf8_charset("application/json; charset=utf-8") == "application/json; charset=utf-8"
    assert with_utf8_charset("text/html; charset=UTF-8") == "text/html; charset=UTF-8"
    assert with_utf8_charset("text/html") == "text/html; charset=utf-8"
    assert with_utf8_charset("text/event-stream") == "text/event-stream; charset=utf-8"
    assert with_utf8_charset("application/problem+json") == "application/problem+json; charset=utf-8"
    assert with_utf8_charset("application/yaml") == "application/yaml; charset=utf-8"
    assert with_utf8_charset("image/svg+xml") == "image/svg+xml; charset=utf-8"
    assert with_utf8_charset("application/zip") == "application/zip"
    assert with_utf8_charset("application/octet-stream") == "application/octet-stream"
    assert with_utf8_charset("image/png") == "image/png"
    assert with_utf8_charset("") == ""


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_json_and_html_responses_name_utf8(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert _flat(health) == "application/json;charset=utf-8"

    missing = client.get("/api/runs/missing-run", headers=ZHS)
    assert missing.status_code == 404
    assert _flat(missing) == "application/json;charset=utf-8"
    detail = "找不到这次测试".encode()
    assert detail in missing.content
    assert missing.json()["detail"] == "找不到这次测试"

    bad = client.post("/api/settings", headers={**ZHS, "content-type": "application/json"}, content=b"{}")
    assert bad.status_code == 400
    assert _flat(bad) == "application/json;charset=utf-8"
    assert "缺少".encode() in bad.content
    assert bad.headers["content-type"].lower().count("charset") == 1

    docs = client.get("/docs")
    assert docs.status_code == 200
    assert _flat(docs).startswith("text/html;")
    assert "charset=utf-8" in _flat(docs)
    assert docs.headers["content-type"].lower().count("charset") == 1


def test_zip_download_stays_binary(client):
    exported = client.get("/api/modeditor/export/claude_v34")
    assert exported.status_code == 200, exported.text[:300]
    ctype = exported.headers["content-type"].lower()
    assert ctype.startswith("application/zip")
    assert "charset" not in ctype
    assert exported.content[:2] == b"PK"
