"""界面多语言：翻译表齐全（每个键四种语言都有、占位符一致）、代码里用到的键都存在、
游戏名字按所选语言从（合成的）游戏 .pck 读并回退 eng → zhs。不需要游戏。"""
import glob
import json
import os
import re

import pytest

from gui import backend, i18n
from sts2sim import gameloc
from test_gameloc import _make_pck

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOC = os.path.join(ROOT, "gui", "locales")
LANGS = ["zhs", "en", "ja", "ko"]


def _load(lang):
    with open(os.path.join(LOC, f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def test_every_key_in_every_language():
    """zhs / en / ja / ko 的键集合必须相同。某一种语言少键或多键都失败。"""
    tables = {lang: _load(lang) for lang in LANGS}
    union = set.union(*(set(t) for t in tables.values()))
    assert len(union) > 300
    gaps = {lang: sorted(union - set(t)) for lang, t in tables.items()}
    gaps = {lang: missing for lang, missing in gaps.items() if missing}
    for lang, t in tables.items():
        empty = [k for k, v in t.items() if not isinstance(v, str) or (not v.strip() and k != "sep.list")]
        assert not empty, (lang, empty)
    assert not gaps, gaps


def test_placeholders_match():
    tables = {lang: _load(lang) for lang in LANGS}
    for k, zh in tables["zhs"].items():
        want = set(re.findall(r"\{(\w+)\}", zh))
        for lang in LANGS[1:]:
            assert set(re.findall(r"\{(\w+)\}", tables[lang][k])) == want, (lang, k)


def test_python_and_web_use_same_table():
    assert sorted(i18n.LANGS) == sorted(LANGS)
    for lang in LANGS:
        assert i18n.messages(lang) == _load(lang)
    src = open(os.path.join(ROOT, "gui", "web", "src", "i18n.js"), encoding="utf-8").read()
    for lang in LANGS:
        assert f"../../locales/{lang}.json" in src


def _code_files():
    web = glob.glob(os.path.join(ROOT, "gui", "web", "src", "**", "*.vue"), recursive=True)
    web += glob.glob(os.path.join(ROOT, "gui", "web", "src", "*.js"))
    return web + glob.glob(os.path.join(ROOT, "gui", "*.py"))


def test_keys_used_in_code_exist():
    zh = _load("zhs")
    used = set()
    for f in _code_files():
        s = open(f, encoding="utf-8").read()
        used |= set(re.findall(r"""(?<![\w.])(?:t|T|i18n\.t)\(\s*['"]([A-Za-z][\w.-]*\.[\w.-]+)['"]""", s))
    missing = sorted(k for k in used if k not in zh and not k.endswith("."))
    assert not missing, missing
    # 动态拼出来的键
    dyn = [f"page.{p}.{x}" for p in ("new", "run", "report", "ab", "history", "import", "preview", "mods") for x in ("title", "sub")]
    dyn += [f"imp.result.{s}" for s in ("won", "lost", "abandoned", "in_progress")]
    dyn += [f"imp.warn.{c}" for c in (
        "gzip", "utf16", "bom", "doubleEncoded", "seedFromRng", "seedMissing", "noRouteColumn",
        "mapUnparsed", "actsMixed", "actsObjects", "backup", "liveInProgress", "truncated")]
    dyn += [f"mp.{c}" for c in ("Monster", "Elite", "Unknown", "Shop", "RestSite", "Treasure", "Boss", "Ancient", "Unassigned")]
    dyn += [f"prev.limit.{c}" for c in (
        "full_unlocks", "not_tutorial", "no_modifiers", "unknown_nodes", "later_act_maps_projected", "rewards_no_combat")]
    dyn += [f"prev.confidence.{c}" for c in ("act_entry", "projected", "failed")]
    dyn += [f"prev.badge.{c}" for c in ("act_entry", "projected", "failed")]
    dyn += [f"prev.neowHint.{c}" for c in ("first", "all", "none", "index")]
    dyn += [f"prev.warn.{c}" for c in ("seedNormalized", "seedCharset", "seedLength", "relicQueueHidden")]
    dyn += [f"status.{s}" for s in ("running", "done", "failed", "cancelled", "interrupted", "queued")]
    dyn += [f"metric.{k}" for k in ("floor", "boss1", "act2", "act3", "win")]
    dyn += [f"room.{r}" for r in backend.ROOMS + ["Monster", "Elite", "Boss", "Event", "_unrecorded", "探针"]]
    for a in backend.AGENTS_BATCH + backend.MENTOR_AGENTS:
        dyn += [f"agent.{a}.name", f"agent.{a}.desc"]
    for a in backend.AGENTS_COMBAT:
        dyn += [f"agentc.{a}.name", f"agentc.{a}.desc"]
    dyn += [f"preset.{os.path.basename(f)[:-5]}" for f in glob.glob(os.path.join(ROOT, "experiments", "*.yaml"))]
    dyn += _parser_locale_keys()
    assert not [k for k in dyn if k not in zh], [k for k in dyn if k not in zh]


def _src(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def _parser_locale_keys():
    """存档导入 / 种子预览 / DLL 导入把错误码拼成翻译键。键不在 gui 源码里写成字面量。"""
    save = _src("sts2sim/saveimport.py")
    preview = _src("sts2sim/engine/seedpreview.py")
    dll = _src(os.path.join("sts2sim", "dllmod", "package.py"))
    keys = [f"imp.err.{c}" for c in re.findall(r'SaveImportError\(\s*"([A-Za-z0-9_]+)"', save)]
    keys += [f"imp.warn.{c}" for c in re.findall(r'\{"code":\s*"([A-Za-z0-9_]+)"', save)]
    keys += [f"prev.err.{c}" for c in re.findall(r'PreviewError\(\s*"([A-Za-z0-9_]+)"', preview)]
    keys += re.findall(r'DllModError\(\s*"(err\.[A-Za-z0-9_]+)"', dll)
    return keys


def test_no_chinese_left_in_web_templates():
    """界面文字都走翻译表：.vue/.js 里除了注释和中文 ID（房间/阶段），不应再有中文。"""
    allowed = {"普通", "精英", "首领", "弱怪", "探针", "起始"}
    bad = []
    for f in _code_files():
        if not f.endswith((".vue", ".js")) or f.endswith("i18n.js"):
            continue
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            code = re.sub(r"//.*$|/\*.*?\*/|<!--.*?-->", "", line)
            for w in re.findall(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]+", code):
                if w not in allowed:
                    bad.append(f"{os.path.basename(f)}:{i}: {w}")
    assert not bad, bad[:20]


def test_normalize_and_game_lang_fallback():
    assert i18n.normalize("zh-CN") == "zhs" and i18n.normalize("zh_Hans_CN") == "zhs"
    assert i18n.normalize("ja_JP") == "ja" and i18n.normalize("ko-KR") == "ko"
    assert i18n.normalize("de-DE") == "en" and i18n.normalize("") == "en"
    assert i18n.game_langs("ja") == ["jpn", "eng", "zhs"]
    assert i18n.game_langs("en") == ["eng", "zhs"]
    assert i18n.game_langs("zhs") == ["zhs", "eng"]


def test_t_format_and_fallback():
    assert i18n.t("chip.nRuns", "en", n=5) == "5 runs"
    assert i18n.t("chip.nRuns", "ko", n=5) == "5판"
    assert i18n.t("no.such.key", "ja") == "no.such.key"
    assert i18n.tr("room.", "精英", "en") == "Elite"
    assert i18n.tr("room.", "unknown-room", "en") == "unknown-room"
    assert i18n.join(["a", "b"], "en") == "a, b" and i18n.join(["a", "b"], "zhs") == "a、b"


@pytest.fixture
def fake_game(tmp_path, monkeypatch):
    """合成 .pck：日文缺 B 卡、韩文表不存在；角色和遭遇只有英文。内容是占位文字，不是游戏文本。"""
    j = lambda d: json.dumps(d, ensure_ascii=False).encode()  # noqa: E731
    p = tmp_path / "game.pck"
    _make_pck(p, {
        "localization/eng/cards.json": j({"CARD_A.title": "Alpha", "CARD_B.title": "Beta"}),
        "localization/jpn/cards.json": j({"CARD_A.title": "アルファ"}),
        "localization/zhs/cards.json": j({"CARD_A.title": "甲", "CARD_B.title": "乙"}),
        "localization/eng/characters.json": j({"HERO.title": "The Hero"}),
        "localization/eng/encounters.json": j({"ENC_X.title": "Enc X"}),
        "localization/jpn/encounters.json": j({"ENC_X.title": "遭遇 X"}),
    })
    monkeypatch.setenv("DECKBENCH_GAME_PCK", str(p))
    for lang in ("ENG", "ZHS", "JPN", "KOR"):
        monkeypatch.delenv(f"DECKBENCH_GAME_LOC_{lang}", raising=False)
    gameloc._TABLES.clear()
    gameloc._INDEX.clear()
    yield p
    gameloc._TABLES.clear()
    gameloc._INDEX.clear()


def test_game_names_follow_language(fake_game):
    assert gameloc.languages() == {"eng", "jpn", "zhs"}
    b = backend.LocalPythonBackend()
    assert b.card_names(["CARD_A", "CARD_B", "NOPE"], "ja") == {"CARD_A": "アルファ", "CARD_B": "Beta"}
    assert b.card_names(["CARD_A", "CARD_B"], "ko") == {"CARD_A": "Alpha", "CARD_B": "Beta"}   # 没有 kor → eng
    assert b.card_names(["CARD_A"], "zhs") == {"CARD_A": "甲"}
    assert b.encounter_names("ja")["ENC_X"] == "遭遇 X"
    assert b.encounter_names("ko")["ENC_X"] == "Enc X"
    assert backend.char_name("Hero", "ja") == "The Hero"            # 日文缺 → 英文
    assert backend.char_name("Nobody", "en") == "Nobody"            # 都没有 → ID
    assert backend.char_name("Claude", "en") == "Claude娘"          # 我们自己的 mod 角色走翻译表


def test_agents_follow_language():
    en = {a["id"]: a for a in backend.agents_batch("en")}
    ja = {a["id"]: a for a in backend.agents_batch("ja")}
    assert en["modai"]["name"].startswith("General AI")
    assert ja["learned"]["name"] == "学習版 AI"
    assert "DECKBENCH_MENTOR_SITE" in ja["mentor-full"]["hint"] or ja["mentor-full"]["available"]


def test_settings_roundtrip(tmp_path, monkeypatch):
    from gui import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DECKBENCH_LANG", raising=False)
    assert i18n.saved_lang() is None
    i18n.save_settings(lang="ko")
    assert i18n.saved_lang() == "ko" and i18n.current() == "ko"
    tok = i18n.set_request_lang("ja")
    try:
        assert i18n.current() == "ja"
    finally:
        i18n._REQ_LANG.reset(tok)
    monkeypatch.setenv("DECKBENCH_LANG", "en-US")
    assert i18n.current() == "en"


def test_server_settings_and_errors(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from gui import paths
    monkeypatch.setattr(paths, "DATA_DIR", str(tmp_path))
    from gui import server
    c = TestClient(server.app)
    assert c.get("/api/settings").json()["lang"] is None
    assert c.post("/api/settings", json={"lang": "ja"}).json()["lang"] == "ja"
    assert c.get("/api/settings").json()["lang"] == "ja"
    assert c.post("/api/settings", json={"lang": "xx"}).status_code == 400
    r = c.get("/api/runs/nope", headers={"x-lang": "en"})
    assert r.status_code == 404 and r.json()["detail"] == "Test not found"
    r = c.get("/api/runs/nope", headers={"x-lang": "ko"})
    assert r.json()["detail"] == "이 테스트를 찾을 수 없습니다"
