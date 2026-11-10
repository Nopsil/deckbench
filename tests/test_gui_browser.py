"""图形界面的无头浏览器冒烟。pytest-playwright + Chromium。

没装 pytest-playwright，或没装 Chromium 时，整份跳过，所以
``python -m pytest -q tests`` 不会因为缺浏览器失败。
CI 的 Ubuntu 作业设置 ``DECKBENCH_BROWSER_REQUIRED=1``，缺了就失败而不是跳过。

服务从源码起（``python -m gui.app --serve``），绑一个空闲端口。不需要本机游戏数据：
卡牌目录用一份空缓存，遭遇名单用合成夹具（不是游戏文件），战斗实验用和安装包冒烟相同的训练木桩
（``claude_v34`` / ``probe_noengine`` / ``encounter: DUMMY`` / 1 回合）。
预设写在 ``experiments/browser_smoke.yaml``，测完就删，不进仓库。

*Headless browser smoke for the web GUI (pytest-playwright, Chromium).
The module is skipped when pytest-playwright or Chromium is missing, so
``python -m pytest -q tests`` still passes. The Ubuntu CI job sets
``DECKBENCH_BROWSER_REQUIRED=1`` and fails instead of skipping.
The server is ``python -m gui.app --serve`` on a free port. No local game
data: an empty card cache, a synthetic encounter fixture (not game files),
and the same training dummy as the package smoke
(``claude_v34`` / ``probe_noengine`` / ``encounter: DUMMY`` / one turn).*
"""
import atexit
import importlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIST_INDEX = ROOT / "gui" / "web" / "dist" / "index.html"
PRESET = ROOT / "experiments" / "browser_smoke.yaml"
ENCOUNTERS = ROOT / "tests" / "fixtures" / "encounters_min"
REAL_RUN = ROOT / "tests" / "fixtures" / "calibrate" / "real.run"
SIMS = ROOT / "tests" / "fixtures" / "calibrate" / "sims.jsonl"
PRESET_TEXT = """name: browser_smoke
title: Browser dummy smoke
mods: [claude_v34]
seed: 1
fights: 1
max_turns: 1
agent: heuristic
decks: []
extra:
  - {deck: probe_noengine, encounter: DUMMY, fights: 1, max_turns: 1, room: probe}
"""
# 主页面：标题，以及这一页上始终有的一句（不依赖有没有跑过测试）。
PAGES = (
    ("/#/new", "New test", "Combat test"),
    ("/#/run", "Running", "No test is running right now"),
    ("/#/report", "Report", "Pick a finished test"),
    ("/#/ab", "Single-card A/B", "Pick two tests to compare"),
    ("/#/compare", "Compare runs", "Pick two finished combat tests"),
    ("/#/history", "History", "Nothing here yet"),
    ("/#/import", "Import run", "Save path"),
    ("/#/preview", "Seed preview", "Which opening rewards"),
    ("/#/explain", "Decisions", "Explanation log"),
    ("/#/calibrate", "Calibration", "No comparison yet"),
    ("/#/mods", "Mod editor", "Open a mod or create a new one"),
    ("/#/decks", "Deck builder", "Card pool"),
    ("/#/whatsnew", "What's new", "战斗进程"),
)


def _required():
    return os.environ.get("DECKBENCH_BROWSER_REQUIRED") == "1"


def _load_playwright():
    names = ("pytest_playwright", "playwright.sync_api")
    if _required():
        for name in names:
            importlib.import_module(name)
        return
    for name in names:
        pytest.importorskip(name)


def _chromium_installed():
    from playwright.sync_api import Error, sync_playwright
    try:
        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).is_file()
    except (OSError, Error):
        return False


def _remove_preset():
    """删掉测试写的预设。只删这一份木桩，避免 test_i18n 把文件名当成翻译键。"""
    if not PRESET.is_file():
        return
    try:
        text = PRESET.read_text(encoding="utf-8")
    except OSError:
        return
    if "name: browser_smoke" in text and "probe_noengine" in text:
        PRESET.unlink(missing_ok=True)


_load_playwright()
_BROWSER_OK = _chromium_installed()
if not _BROWSER_OK and not _required():
    pytestmark = pytest.mark.skip(
        reason="Playwright Chromium is not installed (python -m playwright install chromium)",
    )

atexit.register(_remove_preset)


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _server_env(data, tmp):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("DECKBENCH_GAME", "DECKBENCH_MENTOR_", "STS2SIM_MENTOR")) or key == "DECKBENCH_LANG":
            env.pop(key, None)
    env["STS2SIM_GUI_DATA"] = str(data)
    env["DECKBENCH_CACHE"] = str(tmp / "deckbench-cache")
    env["DECKBENCH_ANALYSIS_ROOTS"] = str(data)
    env["DECKBENCH_MCP_RUNS"] = str(tmp / "no-mcp")
    env["DECKBENCH_CODEX_DIR"] = str(ENCOUNTERS)
    env["DECKBENCH_NO_DIALOG"] = "1"
    env["DECKBENCH_MENTOR_NO_DEFAULTS"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 只在这场浏览器测试里，在两场之间留空档，进度才来得及被看到。不改变出牌。
    env["DECKBENCH_FIGHT_GAP"] = "0.25"
    return env


def _write_card_cache(data):
    """空的卡牌缓存，版本和 mtime 让 catalog 不再去跑需要游戏数据的 cards 子进程。"""
    cache = data / "cache" / "cards.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "version": 2,
        "cards": [],
        "variants": [],
        "starters": {},
        "characters": ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent", "Claude"],
    }), encoding="utf-8")
    stamp = time.time() + 30
    os.utime(cache, (stamp, stamp))


def _stop(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)


def _read_log(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return ""


def _get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return json.load(res)


def _wait_health(proc, base, log_path, timeout=40):
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited {proc.returncode}\n{_read_log(log_path)}")
        try:
            body = _get_json(base + "/api/health", timeout=1)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = str(exc)
            time.sleep(0.1)
            continue
        if body.get("ok"):
            return body
        last = str(body)
        time.sleep(0.1)
    raise RuntimeError(f"server did not become healthy ({last})\n{_read_log(log_path)}")


@pytest.fixture(scope="module", autouse=True)
def _release_playwright_event_loop(playwright, browser):
    """这个模块结束后关掉同步 Playwright。

    ``sync_playwright()`` 在主线程上把事件循环标成正在运行（``asyncio._set_running_loop``），
    pytest-playwright 的 session 夹具要到全部测试结束才 ``stop()``。
    后面的 MCP 注册测试用 ``asyncio.run`` 调工具，循环还标着就会报
    ``asyncio.run() cannot be called from a running event loop``。
    单独跑那份测试时循环没人占，所以能过。这里在浏览器冒烟结束时先关掉浏览器和驱动，
    不靠重排测试，也不跳过。
    """
    yield
    browser.close()
    playwright.stop()


@pytest.fixture(scope="module")
def gui_server(tmp_path_factory):
    if not _BROWSER_OK:
        pytest.fail("Playwright Chromium is not installed (python -m playwright install chromium)")
    if not DIST_INDEX.is_file():
        pytest.fail("gui/web/dist is missing. From gui/web: npm ci && npm run build")
    tmp = tmp_path_factory.mktemp("gui-browser")
    data = tmp / "data"
    data.mkdir()
    _write_card_cache(data)
    shutil.copyfile(SIMS, data / "sims.jsonl")
    PRESET.write_text(PRESET_TEXT, encoding="utf-8")
    log_path = tmp / "server.log"
    log_fh = log_path.open("w", encoding="utf-8")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "gui.app", "--serve", "--port", str(port)],
        cwd=ROOT,
        env=_server_env(data, tmp),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(proc, base, log_path)
        catalog = _get_json(base + "/api/catalog?lang=en", timeout=60)
        ids = [item["id"] for item in catalog.get("experiments") or []]
        if "browser_smoke" not in ids:
            raise RuntimeError(f"catalog is missing browser_smoke: {ids}\n{_read_log(log_path)}")
        yield SimpleNamespace(
            base=base,
            data=data,
            real=str(REAL_RUN),
            sim=str(data / "sims.jsonl"),
            log_path=log_path,
        )
    finally:
        _stop(proc)
        log_fh.close()
        _remove_preset()


@pytest.fixture
def gui(page, gui_server):
    from playwright.sync_api import expect
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(
        "try { if (!localStorage.getItem('ui.lang')) localStorage.setItem('ui.lang', 'en'); } catch (e) {}"
    )
    errors = []

    def on_pageerror(exc):
        errors.append(f"pageerror: {exc}")

    def on_console(msg):
        if msg.type != "error":
            return
        loc = msg.location or {}
        errors.append(f"{msg.text} ({loc.get('url', '')}:{loc.get('lineNumber', '')})")

    page.on("pageerror", on_pageerror)
    page.on("console", on_console)
    page.set_default_timeout(20_000)
    return SimpleNamespace(page=page, errors=errors, expect=expect, **gui_server.__dict__)


def _assert_clean(gui, where):
    assert not gui.errors, f"{where}: {gui.errors}"


def _save_shot(page, name):
    targets = [ROOT / "test-results" / "gui-smoke" / name]
    artifacts = Path("/opt/cursor/artifacts")
    if artifacts.is_dir():
        targets.append(artifacts / name)
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)


def _open(gui, route, heading, landmark):
    gui.page.goto(gui.base + route, wait_until="domcontentloaded")
    gui.expect(gui.page.locator("h1")).to_have_text(heading)
    gui.expect(gui.page.get_by_text(landmark, exact=True).first).to_be_visible()
    gui.page.wait_for_timeout(300)
    _assert_clean(gui, route)


def test_main_pages_load_without_console_errors(gui):
    for route, heading, landmark in PAGES:
        _open(gui, route, heading, landmark)
        if route == "/#/calibrate":
            assert gui.page.locator("[data-page='calibrate']").count() == 1
    gui.page.goto(gui.base + "/#/explain", wait_until="domcontentloaded")
    gui.expect(gui.page.locator("h1")).to_have_text("Decisions")
    gui.expect(gui.page.get_by_text("No explanation log opened", exact=True)).to_be_visible()
    _assert_clean(gui, "/#/explain")


def _switch_lang(gui, label):
    page = gui.page
    page.locator(".lang .n-select").click()
    page.locator(".n-base-select-option").filter(has_text=label).click()


def test_language_toggle_persists_in_local_storage(gui):
    """切到简体中文后，新建测试、运行、对比、组牌、校准、关于和本版更新的文案都变，刷新仍是 zh-CN。"""
    page = gui.page
    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("New test")
    gui.expect(page.locator("html")).to_have_attribute("lang", "en")
    assert page.evaluate("localStorage.getItem('ui.lang')") == "en"

    _switch_lang(gui, "简体中文")
    gui.expect(page.locator("h1")).to_have_text("新建测试")
    gui.expect(page.get_by_text("战斗实验", exact=True).first).to_be_visible()
    gui.expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
    assert page.evaluate("localStorage.getItem('ui.lang')") == "zhs"
    gui.expect(page.get_by_test_id("whatsnew-footer")).to_have_text("本版更新")
    gui.expect(page.get_by_test_id("whatsnew-dismiss")).to_have_text("关闭")
    _save_shot(page, "gui-new-zh-CN.png")

    page.get_by_test_id("about-version").click()
    gui.expect(page.get_by_test_id("about-dialog").get_by_text("检查更新", exact=True)).to_be_visible()
    gui.expect(page.get_by_text("关于 DeckBench", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    gui.expect(page.get_by_test_id("about-dialog")).to_be_hidden()

    zh_pages = (
        ("/#/run", "运行中", "现在没有正在运行的测试"),
        ("/#/compare", "对比两次", "选择两次已完成的战斗实验"),
        ("/#/decks", "组牌", "牌池"),
        ("/#/calibrate", "校准", "真对局"),
    )
    for route, heading, landmark in zh_pages:
        page.goto(gui.base + route, wait_until="domcontentloaded")
        gui.expect(page.locator("h1")).to_have_text(heading)
        gui.expect(page.get_by_text(landmark, exact=True).first).to_be_visible()
        gui.expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
        assert page.evaluate("localStorage.getItem('ui.lang')") == "zhs"
        _assert_clean(gui, route)
    gui.expect(page.get_by_text("对照", exact=True).first).to_be_visible()
    _save_shot(page, "gui-calibrate-zh-CN.png")
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("卡组 A 对卡组 B", exact=True)).to_be_visible()
    gui.expect(page.get_by_text("单卡贡献", exact=True).first).to_be_visible()
    gui.expect(page.get_by_text("对打", exact=True).first).to_be_visible()
    _save_shot(page, "gui-decks-zh-CN.png")
    page.goto(gui.base + "/#/compare", wait_until="domcontentloaded")
    _save_shot(page, "gui-compare-zh-CN.png")

    page.reload(wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("对比两次")
    assert page.evaluate("localStorage.getItem('ui.lang')") == "zhs"
    gui.expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
    gui.expect(page.get_by_text("选择两次已完成的战斗实验", exact=True).first).to_be_visible()

    _switch_lang(gui, "English")
    gui.expect(page.locator("h1")).to_have_text("Compare runs")
    gui.expect(page.get_by_text("Pick two finished combat tests", exact=True).first).to_be_visible()
    assert page.evaluate("localStorage.getItem('ui.lang')") == "en"
    gui.expect(page.locator("html")).to_have_attribute("lang", "en")

    page.reload(wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("Compare runs")
    assert page.evaluate("localStorage.getItem('ui.lang')") == "en"
    _assert_clean(gui, "language")


def test_empty_history_loads_demo_and_compare_works(gui):
    """空的历史页载入内置示例。两套探针对合成三人组的对打出现，对比能打开。"""
    page = gui.page
    page.goto(gui.base + "/#/history", wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("History")
    gui.expect(page.get_by_text("Nothing here yet")).to_be_visible()
    button = page.locator("[data-action='load-demo']")
    gui.expect(button).to_be_visible()
    gui.expect(button).to_have_text("Load demo data")
    button.click()
    gui.expect(page.get_by_text("Loaded 2 sample test(s).")).to_be_visible()
    gui.expect(page.get_by_text("探针·无引擎", exact=True).first).to_be_visible()
    gui.expect(page.get_by_text("探针·路线D", exact=True).first).to_be_visible()
    listed = _get_json(gui.base + "/api/runs")
    by_title = {row.get("title"): row for row in listed}
    deck = by_title["探针·无引擎"]
    probe = by_title["探针·路线D"]
    assert deck["kind"] == "combat" and deck["status"] == "done"
    assert probe["kind"] == "combat" and probe["status"] == "done"
    assert deck.get("imported") is True and probe.get("imported") is True
    query = urlencode({"a": deck["id"], "b": probe["id"]})
    page.goto(gui.base + "/#/compare?" + query, wait_until="domcontentloaded")
    gui.expect(page.locator("[data-page='compare']")).to_be_visible()
    gui.expect(page.locator("[data-table='cells']")).to_be_visible(timeout=30_000)
    _save_shot(page, "demo-compare.png")
    _assert_clean(gui, "demo")


def _run_log_tail(data):
    logs = sorted((data / "runs").glob("*/run.log"))
    if not logs:
        return ""
    try:
        return logs[-1].read_text(encoding="utf-8", errors="replace")[-2000:]
    except OSError:
        return ""


def test_dummy_combat_from_the_gui_reaches_done(gui):
    page = gui.page
    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Combat test", exact=True).first).to_be_visible()
    page.locator("button.mode").filter(has_text="Combat test").click()
    gui.expect(page.get_by_text("Test source", exact=True)).to_be_visible()
    page.locator(".form .n-select").filter(has_text="(quick)").click()
    page.locator(".n-base-select-option").filter(has_text="browser_smoke").click()
    gui.expect(page.locator(".form .n-select").filter(has_text="browser_smoke")).to_be_visible()
    gui.expect(page.get_by_text("Browser dummy smoke", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Start", exact=True).click()
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_url("**/#/run/*", timeout=120_000)
        page.get_by_role("button", name="View report").wait_for(timeout=120_000)
    except PlaywrightTimeout as exc:
        raise AssertionError(
            "dummy combat did not reach done\n" + _run_log_tail(gui.data)
        ) from exc
    gui.expect(page.locator(".n-tag").filter(has_text="Done")).to_be_visible()
    gui.expect(page.get_by_text("preset browser_smoke", exact=True)).to_be_visible()
    _save_shot(page, "gui-combat-done.png")
    _assert_clean(gui, "combat")


def _combat_rows(wins, timeouts, hp_base, turns_base, dmg, plays, room):
    rows = []
    for i in range(40):
        if i < timeouts:
            result = "timeout"
        elif i < timeouts + wins:
            result = "win"
        else:
            result = "loss"
        rows.append({
            "deck": "probe",
            "act": 1,
            "room": room,
            "result": result,
            "turns": turns_base + (i % 3),
            "hp_lost": hp_base + (i % 4),
            "dmg_total": dmg,
            "cards": {"STRIKE": [plays, dmg, 0, plays]},
        })
    return rows


def _write_combat_run(data, rid, title, rows):
    run = data / "runs" / rid
    out = run / "out"
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": rid,
        "kind": "combat",
        "title": title,
        "status": "done",
        "created": "2026-01-02T00:00:00+00:00",
        "params": {},
    }
    (run / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    text = "".join(json.dumps(row) + "\n" for row in rows)
    (out / "raw.jsonl").write_text(text, encoding="utf-8")


def test_compare_page_highlights_cell_deltas(gui):
    base = _combat_rows(2, 10, 20, 8, 8, 1, "Monster") + _combat_rows(30, 0, 4, 3, 36, 1, "Elite")
    changed = _combat_rows(30, 0, 4, 3, 36, 4, "Monster") + _combat_rows(2, 10, 20, 8, 8, 4, "Elite")
    _write_combat_run(gui.data, "cmp-a", "Baseline cells", base)
    _write_combat_run(gui.data, "cmp-b", "Changed cells", changed)
    page = gui.page
    query = urlencode({"a": "cmp-a", "b": "cmp-b"})
    page.goto(gui.base + "/#/compare?" + query, wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("Compare runs")
    gui.expect(page.locator("[data-page='compare']")).to_be_visible()
    cells = page.locator("[data-table='cells']")
    gui.expect(cells).to_be_visible(timeout=30_000)
    gui.expect(cells.locator("tr[data-metric='win'][data-sig='1']").first).to_be_visible()
    gui.expect(cells.locator("td.good").first).to_be_visible()
    gui.expect(cells.locator("td.bad").first).to_be_visible()
    gui.expect(cells.locator(".sig").first).to_have_text("significant")
    gui.expect(page.locator("[data-table='cards']").get_by_text("STRIKE", exact=True).first).to_be_visible()
    cells.scroll_into_view_if_needed()
    _save_shot(page, "gui-compare.png")
    _assert_clean(gui, "compare")


def test_gap_triage_renders_sample_calibration(gui):
    page = gui.page
    query = urlencode({"real": gui.real, "sim": gui.sim})
    page.goto(gui.base + "/#/calibrate?" + query, wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("Calibration")
    triage = page.locator("#gap-triage")
    gui.expect(triage).to_be_visible(timeout=30_000)
    gui.expect(triage.get_by_role("heading", name="Gap triage")).to_be_visible()
    gui.expect(triage.get_by_text(
        "Read-only. It does not start a simulation and does not change seeds or AI.",
        exact=True,
    )).to_be_visible()
    gui.expect(triage.locator("[data-gap-side='optimistic']").get_by_text("SAMPLE_ELITE")).to_be_visible()
    gui.expect(triage.get_by_text("No likely gaps on this side.", exact=True)).to_be_visible()
    gui.expect(triage.get_by_text("sts2sim/enemies.py")).to_be_visible()
    triage.scroll_into_view_if_needed()
    _save_shot(page, "gui-gap-triage.png")
    _assert_clean(gui, "gap-triage")


def _offline(html):
    low = html.lower()
    assert "http://" not in low
    assert "https://" not in low
    assert "<script" not in low
    assert "<link" not in low
    assert "<iframe" not in low
    assert "<svg" in low


def test_export_buttons_download_offline_html(gui):
    """运行页和对比页的「导出报告」点下去，得到一份离线 HTML。"""
    base = _combat_rows(2, 10, 20, 8, 8, 1, "Monster") + _combat_rows(30, 0, 4, 3, 36, 1, "Elite")
    changed = _combat_rows(30, 0, 4, 3, 36, 4, "Monster") + _combat_rows(2, 10, 20, 8, 8, 4, "Elite")
    _write_combat_run(gui.data, "exp-a", "Export baseline", base)
    _write_combat_run(gui.data, "exp-b", "Export changed", changed)
    cells = gui.data / "runs" / "exp-a" / "out" / "cells.csv"
    cells.write_text(
        "卡组id,卡组,阶段,幕,房间,场数,胜率%,战败%,超时%,平均回合,平均掉血,每回合输出,循环报警场数\n"
        "probe,Probe,,1,Monster,40,75.0,20.0,5.0,4.0,8.0,12.0,0\n",
        encoding="utf-8",
    )
    page = gui.page
    page.goto(gui.base + "/#/run/exp-a", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Done", exact=True).first).to_be_visible()
    export = page.locator("[data-action='export']")
    gui.expect(export).to_be_visible()
    with page.expect_download() as caught:
        export.click()
    saved = gui.data / "export-run.html"
    caught.value.save_as(str(saved))
    html = saved.read_text(encoding="utf-8")
    _offline(html)
    assert "Export baseline" in html
    page.goto(saved.as_uri())
    gui.expect(page.locator("h1")).to_be_visible()
    _save_shot(page, "export-report.png")

    query = urlencode({"a": "exp-a", "b": "exp-b"})
    page.goto(gui.base + "/#/compare?" + query, wait_until="domcontentloaded")
    gui.expect(page.locator("[data-table='cells']")).to_be_visible(timeout=30_000)
    with page.expect_download() as caught:
        page.locator("[data-action='export']").click()
    compared = gui.data / "export-compare.html"
    caught.value.save_as(str(compared))
    other = compared.read_text(encoding="utf-8")
    _offline(other)
    assert "Run comparison" in other
    _assert_clean(gui, "export")


def test_bundle_download_and_import(gui):
    """运行页下载结果包，历史页再导入。编号冲突时换成新编号，并标成已导入。"""
    base = _combat_rows(2, 10, 20, 8, 8, 1, "Monster") + _combat_rows(30, 0, 4, 3, 36, 1, "Elite")
    _write_combat_run(gui.data, "bundle-a", "Bundle baseline", base)
    (gui.data / "runs" / "bundle-a" / "out" / "cells.csv").write_text(
        "卡组id,卡组,阶段,幕,房间,场数,胜率%,战败%,超时%,平均回合,平均掉血,每回合输出,循环报警场数\n"
        "probe,Probe,,1,Monster,40,75.0,20.0,5.0,4.0,8.0,12.0,0\n",
        encoding="utf-8",
    )
    page = gui.page
    page.goto(gui.base + "/#/run/bundle-a", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Done", exact=True).first).to_be_visible()
    bundle = page.locator("[data-action='bundle']")
    gui.expect(bundle).to_be_visible()
    with page.expect_download() as caught:
        bundle.click()
    saved = gui.data / "bundle-run.deckbench.zip"
    caught.value.save_as(str(saved))
    assert saved.stat().st_size > 32
    import zipfile
    with zipfile.ZipFile(saved) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert "manifest.json" in names and "report.html" in names
    assert "runs/bundle-a/meta.json" in names and "runs/bundle-a/raw.jsonl" in names
    assert manifest["schema"] == 1 and manifest["kind"] == "run"
    assert manifest["deckbench"]
    report = None
    with zipfile.ZipFile(saved) as archive:
        report = archive.read("report.html").decode("utf-8")
    _offline(report)
    assert "Bundle baseline" in report

    page.goto(gui.base + "/#/history", wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("History")
    gui.expect(page.get_by_role("button", name="Import bundle")).to_be_visible()
    gui.expect(page.get_by_text("Bundle baseline", exact=True).first).to_be_visible()
    page.locator("[data-action='import-bundle-file']").set_input_files(str(saved))
    gui.expect(page.get_by_text("Imported 1 test(s).")).to_be_visible()
    gui.expect(page.get_by_text("Imported", exact=True).first).to_be_visible()
    listed = _get_json(gui.base + "/api/runs")
    imported = [row for row in listed if row.get("imported") and row.get("origin", {}).get("original_id") == "bundle-a"]
    assert len(imported) == 1
    assert imported[0]["id"] != "bundle-a"
    assert imported[0]["status"] == "done"
    assert imported[0]["kind"] == "combat"
    _save_shot(page, "bundle-imported.png")

    changed = _combat_rows(30, 0, 4, 3, 36, 4, "Monster") + _combat_rows(2, 10, 20, 8, 8, 4, "Elite")
    _write_combat_run(gui.data, "bundle-b", "Bundle changed", changed)
    query = urlencode({"a": "bundle-a", "b": "bundle-b"})
    page.goto(gui.base + "/#/compare?" + query, wait_until="domcontentloaded")
    gui.expect(page.locator("[data-table='cells']")).to_be_visible(timeout=30_000)
    with page.expect_download() as caught:
        page.locator("[data-action='bundle']").click()
    compared = gui.data / "bundle-compare.deckbench.zip"
    caught.value.save_as(str(compared))
    with zipfile.ZipFile(compared) as archive:
        compare_manifest = json.loads(archive.read("manifest.json"))
    assert compare_manifest["kind"] == "compare"
    assert compare_manifest["runs"] == ["bundle-a", "bundle-b"]
    _assert_clean(gui, "bundle")


def test_deck_builder_saves_a_preset_and_starts_a_dummy_run(gui):
    """组一套小牌组，存成预设，再从新建测试用它打一场木桩。"""
    page = gui.page
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("Deck builder")
    gui.expect(page.locator("[data-page='decks']")).to_be_visible()
    gui.expect(page.get_by_text("Card pool", exact=True)).to_be_visible()

    search = page.locator("[data-deck='search'] input")
    search.fill("YIHESHI")
    first = page.locator("[data-card='claude_v34:YIHESHI']")
    gui.expect(first).to_be_visible()
    first.locator("[data-add]").click()
    search.fill("XIAOBENBEN")
    second = page.locator("[data-card='claude_v34:XIAOBENBEN']")
    gui.expect(second).to_be_visible()
    second.locator("[data-add]").click()
    row = page.locator("[data-deck-card='claude_v34:XIAOBENBEN']")
    row.locator("[data-inc]").click()
    gui.expect(row.locator("[data-count]")).to_have_text("2")
    gui.expect(page.locator("[data-deck='size']")).to_have_text("3")
    gui.expect(page.locator("[data-deck='curve']")).to_be_visible()
    gui.expect(page.locator("[data-deck='split']")).to_be_visible()

    page.locator("[data-deck='id'] input").fill("browserdeck")
    page.locator("[data-deck='name'] input").fill("Browser deck")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset browserdeck")
    saved = (gui.data / "presets" / "browserdeck.yaml").read_text(encoding="utf-8")
    assert "YIHESHI" in saved
    assert "XIAOBENBEN×2" in saved or "XIAOBENBEN" in saved
    assert "encounter: DUMMY" in saved
    _save_shot(page, "gui-decks.png")
    _assert_clean(gui, "decks")

    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Combat test", exact=True).first).to_be_visible()
    page.locator("button.mode").filter(has_text="Combat test").click()
    gui.expect(page.get_by_text("Test source", exact=True)).to_be_visible()
    page.locator(".form .n-select").filter(has_text="(quick)").click()
    page.locator(".n-base-select-option").filter(has_text="browserdeck").click()
    gui.expect(page.get_by_text("Browser deck", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Start", exact=True).click()
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_url("**/#/run/*", timeout=120_000)
        page.get_by_role("button", name="View report").wait_for(timeout=120_000)
    except PlaywrightTimeout as exc:
        raise AssertionError(
            "saved deck dummy did not reach done\n" + _run_log_tail(gui.data)
        ) from exc
    gui.expect(page.locator(".n-tag").filter(has_text="Done")).to_be_visible()
    gui.expect(page.get_by_text("preset browserdeck", exact=True)).to_be_visible()
    _assert_clean(gui, "deck-run")


def test_deck_builder_saves_two_encounters_and_runs_them(gui):
    """勾选两场遭遇（第 1 幕精英连战），存成预设，再从新建测试打完。"""
    page = gui.page
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.locator("[data-page='decks']")).to_be_visible()
    gui.expect(page.locator("[data-gauntlet='act1_elite']")).to_be_visible()
    page.locator("[data-gauntlet='act1_elite']").click()
    gui.expect(page.locator("[data-selected='NIB_ELITE_A']")).to_be_visible()
    gui.expect(page.locator("[data-selected='NIB_ELITE_B']")).to_be_visible()
    gui.expect(page.locator("[data-selected='DUMMY']")).to_have_count(0)

    search = page.locator("[data-deck='search'] input")
    search.fill("YIHESHI")
    first = page.locator("[data-card='claude_v34:YIHESHI']")
    gui.expect(first).to_be_visible()
    first.locator("[data-add]").click()
    search.fill("XIAOBENBEN")
    second = page.locator("[data-card='claude_v34:XIAOBENBEN']")
    gui.expect(second).to_be_visible()
    second.locator("[data-add]").click()

    page.locator("[data-deck='id'] input").fill("twoenc")
    page.locator("[data-deck='name'] input").fill("Two encounters")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset twoenc")
    saved = (gui.data / "presets" / "twoenc.yaml").read_text(encoding="utf-8")
    from sts2sim.deckpresets import full_fight_turns
    cap = full_fight_turns()
    assert cap > 1
    gui.expect(page.locator("[data-deck='turns']")).to_have_value(str(cap))
    assert "NIB_ELITE_A" in saved and "NIB_ELITE_B" in saved
    assert "DUMMY" not in saved
    assert f"max_turns: {cap}" in saved
    _save_shot(page, "deck-encounters.png")
    _assert_clean(gui, "two-encounters")

    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Combat test", exact=True).first).to_be_visible()
    page.locator("button.mode").filter(has_text="Combat test").click()
    page.locator(".form .n-select").filter(has_text="(quick)").click()
    page.locator(".n-base-select-option").filter(has_text="twoenc").click()
    gui.expect(page.get_by_text("Two encounters", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Start", exact=True).click()
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_url("**/#/run/*", timeout=120_000)
        page.get_by_role("button", name="View report").wait_for(timeout=120_000)
    except PlaywrightTimeout as exc:
        raise AssertionError(
            "two-encounter deck did not reach done\n" + _run_log_tail(gui.data)
        ) from exc
    gui.expect(page.locator(".n-tag").filter(has_text="Done")).to_be_visible()
    rid = page.url.rstrip("/").split("/run/")[-1]
    raw_path = gui.data / "runs" / rid / "out" / "raw.jsonl"
    fights = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["encounter"] for row in fights] == ["NIB_ELITE_A", "NIB_ELITE_B"]
    assert fights[0]["enc_name"] == "小钉精英甲"
    decided = [row for row in fights if row["result"] in ("win", "loss")]
    assert decided and len(decided) * 2 >= len(fights)
    _assert_clean(gui, "two-encounter-run")


def test_deck_head_to_head_opens_compare(gui):
    """存两套牌，对打一场木桩，直接落到对比页，两场都在。"""
    page = gui.page
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.locator("[data-page='decks']")).to_be_visible()
    search = page.locator("[data-deck='search'] input")
    search.fill("YIHESHI")
    first = page.locator("[data-card='claude_v34:YIHESHI']")
    gui.expect(first).to_be_visible()
    first.locator("[data-add]").click()
    search.fill("XIAOBENBEN")
    second = page.locator("[data-card='claude_v34:XIAOBENBEN']")
    gui.expect(second).to_be_visible()
    second.locator("[data-add]").click()
    page.locator("[data-deck='id'] input").fill("h2ha")
    page.locator("[data-deck='name'] input").fill("Head A")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset h2ha")
    page.locator("[data-deck='id'] input").fill("h2hb")
    page.locator("[data-deck='name'] input").fill("Head B")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset h2hb")

    page.locator("[data-deck='h2h']").scroll_into_view_if_needed()
    page.locator("[data-deck='h2h-a'] .n-base-selection").click()
    option_a = page.locator(".n-base-select-option").filter(has_text="Head A").last
    gui.expect(option_a).to_be_visible()
    option_a.click()
    page.keyboard.press("Escape")
    page.locator("[data-deck='h2h-b'] .n-base-selection").click()
    option_b = page.locator(".n-base-select-option").filter(has_text="Head B").last
    gui.expect(option_b).to_be_visible()
    option_b.click()
    gui.expect(page.locator("[data-deck='h2h-run'] button")).to_be_enabled()
    page.locator("[data-deck='h2h-run'] button").click()
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_url("**/#/compare?*", timeout=180_000)
    except PlaywrightTimeout as exc:
        raise AssertionError("head-to-head did not open compare\n" + _run_log_tail(gui.data)) from exc
    gui.expect(page.locator("[data-page='compare']")).to_be_visible()
    gui.expect(page.locator("h1")).to_have_text("Compare runs")
    gui.expect(page.get_by_text("A · Head A", exact=True)).to_be_visible()
    gui.expect(page.get_by_text("B · Head B", exact=True)).to_be_visible()
    gui.expect(page.locator("[data-table='cells']")).to_be_visible(timeout=30_000)
    gui.expect(page.get_by_text("Head A / Head B").first).to_be_visible()
    _save_shot(page, "head-to-head.png")
    _assert_clean(gui, "head-to-head")


def test_multi_fight_run_shows_progress_then_cancel(gui):
    """多场木桩：进度会往前走，取消后页面停在 cancelled，并标明部分结果。"""
    page = gui.page
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.locator("[data-page='decks']")).to_be_visible()
    search = page.locator("[data-deck='search'] input")
    search.fill("YIHESHI")
    first = page.locator("[data-card='claude_v34:YIHESHI']")
    gui.expect(first).to_be_visible()
    first.locator("[data-add]").click()
    fights = page.locator("[data-fights='DUMMY']")
    fights.fill("30")
    fights.press("Tab")
    gui.expect(page.locator("[data-enc-total]")).to_contain_text("30")
    page.locator("[data-deck='id'] input").fill("progdeck")
    page.locator("[data-deck='name'] input").fill("Progress deck")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset progdeck")

    page.evaluate(
        """() => {
          localStorage.setItem('nt.kind', 'combat');
          localStorage.setItem('nt.form', JSON.stringify({
            b: {},
            c: {
              source: 'preset', preset: 'progdeck', procs: 1, fights: 1, seed: 1,
              agent: 'heuristic', mods: ['vanilla'], decks: [], encounters: [],
              rooms: ['普通', '精英', '首领'], max_turns: 1
            }
          }));
        }"""
    )
    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.get_by_text("Combat test", exact=True).first).to_be_visible()
    page.locator("button.mode").filter(has_text="Combat test").click()
    gui.expect(page.get_by_text("Progress deck", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Start", exact=True).click()
    bar = page.locator("[data-progress]")
    gui.expect(bar).to_be_visible()
    gui.expect(bar.locator("[data-action='cancel']")).to_be_visible()
    page.wait_for_function(
        """() => {
          const el = document.querySelector('[data-progress-done]');
          return el && Number(el.textContent) >= 1;
        }""",
        timeout=90_000,
    )
    first_done = int(page.locator("[data-progress-done]").inner_text())
    page.wait_for_function(
        """(n) => {
          const el = document.querySelector('[data-progress-done]');
          return el && Number(el.textContent) > n;
        }""",
        arg=first_done,
        timeout=90_000,
    )
    gui.expect(page.locator("[data-progress-encounter]")).to_have_attribute("data-encounter", "DUMMY")
    gui.expect(page.locator("[data-progress-total]")).to_have_text("30")
    _save_shot(page, "run-progress.png")
    bar.locator("[data-action='cancel']").click()
    gui.expect(bar).to_have_attribute("data-status", "cancelled", timeout=90_000)
    gui.expect(bar).to_have_attribute("data-partial", "1")
    gui.expect(bar.get_by_text("Partial.", exact=True)).to_be_visible()
    _save_shot(page, "run-cancelled.png")
    runs = list((gui.data / "runs").glob("*/meta.json"))
    assert runs
    meta = json.loads(max(runs, key=lambda path: path.stat().st_mtime).read_text(encoding="utf-8"))
    assert meta["status"] == "cancelled" and meta["partial"] is True
    raw = (gui.data / "runs" / meta["id"] / "out" / "raw.jsonl").read_text(encoding="utf-8")
    done = len([line for line in raw.splitlines() if line.strip()])
    assert 1 <= done < 30
    _assert_clean(gui, "progress-cancel")


def test_deck_card_impact_shows_a_sortable_table(gui):
    """两张牌对训练木桩做留一法，组牌页上出现可排序的差值表，并标明样本太小。"""
    page = gui.page
    page.goto(gui.base + "/#/decks", wait_until="domcontentloaded")
    gui.expect(page.locator("[data-page='decks']")).to_be_visible()
    search = page.locator("[data-deck='search'] input")
    search.fill("YIHESHI")
    first = page.locator("[data-card='claude_v34:YIHESHI']")
    gui.expect(first).to_be_visible()
    first.locator("[data-add]").click()
    search.fill("XIAOBENBEN")
    second = page.locator("[data-card='claude_v34:XIAOBENBEN']")
    gui.expect(second).to_be_visible()
    second.locator("[data-add]").click()
    page.locator("[data-deck='id'] input").fill("impactdeck")
    page.locator("[data-deck='name'] input").fill("Impact deck")
    page.locator("[data-deck='save'] button").click()
    gui.expect(page.locator("[data-deck='saved']")).to_have_text("Saved preset impactdeck")

    panel = page.locator("[data-deck='impact']")
    panel.scroll_into_view_if_needed()
    button = page.locator("[data-deck='impact-run'] button")
    if not button.is_enabled():
        page.locator("[data-deck='impact-deck'] .n-base-selection").click()
        option = page.locator(".n-base-select-option").filter(has_text="Impact deck").last
        gui.expect(option).to_be_visible()
        option.click()
    gui.expect(button).to_be_enabled()
    button.click()
    table = page.locator("[data-table='card-impact']")
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        gui.expect(table).to_be_visible(timeout=180_000)
        gui.expect(page.locator("[data-impact-row]")).to_have_count(2, timeout=180_000)
    except PlaywrightTimeout as exc:
        raise AssertionError("card impact table did not appear\n" + _run_log_tail(gui.data)) from exc
    gui.expect(page.locator("[data-impact-status='done']")).to_be_visible()
    gui.expect(page.locator("[data-card='YIHESHI']")).to_be_visible()
    gui.expect(page.locator("[data-card='XIAOBENBEN']")).to_be_visible()
    gui.expect(page.locator("[data-change='remove']")).to_have_count(2)
    gui.expect(page.locator("[data-noisy-reason='too_small']")).to_have_count(2)
    gui.expect(page.get_by_text("Too small", exact=True).first).to_be_visible()
    gui.expect(table).to_have_attribute("data-sort-key", "delta_win")
    page.locator("[data-sort='delta_hp_lost']").click()
    gui.expect(table).to_have_attribute("data-sort-key", "delta_hp_lost")
    gui.expect(table).to_have_attribute("data-sort-dir", "desc")
    page.locator("[data-sort='delta_win']").click()
    gui.expect(table).to_have_attribute("data-sort-key", "delta_win")
    table.scroll_into_view_if_needed()
    _save_shot(page, "card-impact.png")
    _assert_clean(gui, "card-impact")


def test_whatsnew_panel_opens_dismisses_and_stays_dismissed(gui):
    """本版更新：打开、关掉、刷新之后仍然关掉。关于和页脚都能再打开这一页。"""
    reported = _get_json(gui.base + "/api/changelog")
    version = reported["version"]
    assert version
    page = gui.page
    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    panel = page.get_by_test_id("whatsnew-panel")
    gui.expect(panel).to_be_visible()
    gui.expect(panel).to_contain_text(f"What's new in {version}")
    gui.expect(panel).to_contain_text("示例数据")
    _save_shot(page, "whatsnew-panel.png")
    page.get_by_test_id("whatsnew-dismiss").click()
    gui.expect(panel).to_have_count(0)
    key = f"whatsnew.dismissed.{version}"
    assert page.evaluate("(key) => localStorage.getItem(key)", key) == "1"

    page.reload(wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("New test")
    gui.expect(page.get_by_test_id("whatsnew-panel")).to_have_count(0)
    assert page.evaluate("(key) => localStorage.getItem(key)", key) == "1"

    page.get_by_test_id("whatsnew-footer").click()
    gui.expect(page.locator("h1")).to_have_text("What's new")
    notes = page.get_by_test_id("whatsnew-notes")
    gui.expect(notes).to_contain_text("战斗进程")
    gui.expect(notes).to_contain_text("组牌对打")
    html = notes.inner_html().lower()
    assert "<script" not in html
    assert "javascript:" not in html
    assert notes.locator("img").count() == 0
    _save_shot(page, "whatsnew-page.png")

    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.get_by_test_id("whatsnew-panel")).to_have_count(0)
    page.get_by_test_id("about-version").click()
    page.get_by_test_id("whatsnew-about").click()
    gui.expect(page.locator("h1")).to_have_text("What's new")
    gui.expect(page.get_by_test_id("whatsnew-notes")).to_be_visible()
    _assert_clean(gui, "whatsnew")


def test_about_shows_the_version_and_an_update_check(gui):
    """页脚和关于里显示 GET /api/version。检查更新只有点击才发，而且不打到 GitHub。"""
    reported = _get_json(gui.base + "/api/version")
    assert reported["name"] == "DeckBench"
    version = reported["version"]
    assert version
    page = gui.page
    page.goto(gui.base + "/#/new", wait_until="domcontentloaded")
    gui.expect(page.locator("h1")).to_have_text("New test")
    footer = page.get_by_test_id("about-version")
    gui.expect(footer).to_have_text(f"DeckBench v{version}")
    seen = []
    page.on("request", lambda req: seen.append(req.url))
    footer.click()
    dialog = page.get_by_test_id("about-dialog")
    gui.expect(dialog).to_be_visible()
    gui.expect(dialog).to_contain_text(version)
    gui.expect(page.get_by_test_id("check-updates")).to_have_text("Check for updates")
    assert not any("/api/updates/check" in url or "api.github.com" in url for url in seen)

    state = {
        "ok": True,
        "status": "up_to_date",
        "current": version,
        "latest": version,
        "html_url": "https://github.com/Nopsil/deckbench/releases/latest",
    }

    def fulfill(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(state))

    page.route("**/api/updates/check", fulfill)
    page.get_by_test_id("check-updates").click()
    gui.expect(page.get_by_test_id("update-result")).to_have_text("Up to date.")
    state.update({
        "status": "update_available",
        "latest": "9.9.9",
        "html_url": "https://github.com/Nopsil/deckbench/releases/tag/v9.9.9",
    })
    page.get_by_test_id("check-updates").click()
    result = page.get_by_test_id("update-result")
    gui.expect(result).to_contain_text("New version 9.9.9 available.")
    gui.expect(result.get_by_role("link")).to_have_attribute(
        "href", "https://github.com/Nopsil/deckbench/releases/tag/v9.9.9",
    )
    assert not any("api.github.com" in url for url in seen)
    _save_shot(page, "about-version.png")
    _assert_clean(gui, "about")
