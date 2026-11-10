import os
import sys

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:  # pytest-playwright 没装时，下面的浏览器夹具不会被用到
    class PlaywrightError(Exception):
        pass

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sts2sim import gamedata  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 旧版 YAML 战斗模拟器的测试需要本机数据（不随仓库分发）：
#   - spire-codex 格式的怪物/遭遇 JSON（DECKBENCH_CODEX_DIR 或 data/spire-codex/）
#   - 原版对照组 mods/vanilla/（自己从游戏里整理，已 gitignore）
# 整局引擎的测试需要 `python -m sts2sim.gamedata setup` 生成的本机缓存，没有时自动 skip。
LEGACY = ["test_claude.py", "test_intents.py", "test_shensu.py"]
_legacy_ok = (os.path.exists(os.path.join(gamedata.codex_dir(), "eng_monsters.json"))
              and os.path.isdir(os.path.join(ROOT, "mods", "vanilla")))
collect_ignore = [] if _legacy_ok else LEGACY


@pytest.fixture(scope="session")
def browser(launch_browser):
    """和 pytest-playwright 一样起一个浏览器，但关掉驱动之后再 close 不算失败。

    同步 Playwright 把事件循环标成正在运行，一直占到 session 结束。
    ``tests/test_gui_browser.py`` 在自己的模块结束时关掉驱动，好让后面的
    ``asyncio.run``（MCP 工具注册）还能用。这次 session 收尾时浏览器已经关过，
    循环也停了，再 close 会报 Event loop is closed。
    """
    instance = launch_browser()
    yield instance
    try:
        instance.close()
    except PlaywrightError as exc:
        text = str(exc)
        if "already stopped" in text or "Event loop is closed" in text or "has been closed" in text:
            return
        raise
