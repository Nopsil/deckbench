"""历史结果列：取消或导入、但已经有场次的测试显示胜率，并标上 run.partial。

零场次仍是破折号。四种语言的 run.partial 键都在。
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gui import i18n

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "gui" / "web" / "src" / "pages" / "History.vue"
HELPER = ROOT / "gui" / "web" / "src" / "historyResult.js"

_CASES = [
    ({"status": "cancelled", "kind": "combat", "partial": True, "imported": True,
      "headline": {"fights": 12, "win": 0.25}}, "partial", 12),
    ({"status": "cancelled", "kind": "combat", "headline": {"fights": 0, "win": 0}}, "dash", 0),
    ({"status": "cancelled", "kind": "combat", "partial": True}, "dash", 0),
    ({"status": "cancelled", "kind": "combat", "headline": {"fights": 4, "win": 0}}, "partial", 4),
    ({"status": "failed", "kind": "combat", "headline": {"fights": 3, "win": 0.5}}, "partial", 3),
    ({"status": "cancelled", "kind": "batch", "imported": True,
      "headline": {"n": 8, "win": 0.5}}, "partial", 8),
    ({"status": "done", "kind": "combat", "headline": {"fights": 10, "win": 1}}, "full", 10),
    ({"status": "running", "kind": "combat", "progress": {"done": 2, "total": 10},
      "headline": {"fights": 2, "win": 1}}, "progress", 2),
    ({"status": "queued", "kind": "batch", "headline": {"n": 0}}, "dash", 0),
]


def test_history_page_shows_partial_win_rate():
    src = PAGE.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    assert "historyResultMode" in src
    assert "from '../historyResult'" in src
    assert "t('run.partial')" in src
    assert "data-partial" in src
    assert "data-result" in src
    assert "data-win" in src
    assert "r.status !== 'done'" not in src
    assert "export function historyResultMode" in helper
    assert "export function finishedFights" in helper
    for lang in ("en", "zhs", "ja", "ko"):
        label = i18n.messages(lang)["run.partial"]
        assert isinstance(label, str) and label.strip()


def test_history_result_modes():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (
        "import { historyResultMode, finishedFights } from './gui/web/src/historyResult.js'\n"
        "const cases = JSON.parse(process.env.HIST_CASES)\n"
        "const out = cases.map((row) => ({ mode: historyResultMode(row), fights: finishedFights(row) }))\n"
        "process.stdout.write(JSON.stringify(out))\n"
    )
    env = os.environ.copy()
    env["HIST_CASES"] = json.dumps([row for row, _mode, _n in _CASES])
    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert len(got) == len(_CASES)
    for item, (_row, mode, fights) in zip(got, _CASES):
        assert item == {"mode": mode, "fights": fights}
