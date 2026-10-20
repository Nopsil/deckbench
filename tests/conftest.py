import os
import sys
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
