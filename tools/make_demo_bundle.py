"""用现有的战斗工人生成内置示例结果包。

两场训练木桩（``encounter: DUMMY``，不读怪物数据）：一份是 ``save_preset``
写下的用户牌组，另一份是出厂探针 ``probe_noengine``。每场 2 次、1 回合。
然后用结果包的 compare 导出打成 ``.deckbench.zip``。胜率和牌面来自这次模拟，
不手写。

    python tools/make_demo_bundle.py
    python tools/make_demo_bundle.py --out /tmp/sample.deckbench.zip
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "gui", "demo", "sample.deckbench.zip")
DECK_ID = "demo-deck"
PROBE_ID = "demo-probe"
PRESET_ID = "demo_deck"


def _quiet_game_env():
    for key in list(os.environ):
        game = key.startswith(("DECKBENCH_GAME", "DECKBENCH_MENTOR_", "STS2SIM_MENTOR"))
        if game or key in ("DECKBENCH_LANG", "DECKBENCH_CODEX_DIR"):
            os.environ.pop(key, None)
    os.environ["DECKBENCH_MENTOR_NO_DEFAULTS"] = "1"


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _run_combat(backend, run_dir, params):
    os.makedirs(run_dir, exist_ok=True)
    argv, env, cwd = backend.build_command("combat", params, run_dir)
    started = time.time()
    proc = subprocess.run(
        argv, cwd=cwd, env=env, check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        raise subprocess.CalledProcessError(proc.returncode, argv, proc.stdout, proc.stderr)
    return time.time() - started


def _write_meta(run_dir, rid, title, params, secs, summary):
    from gui.jobs import _headline

    fights = summary.get("fights") if isinstance(summary, dict) else None
    total = int(fights) if isinstance(fights, int) else 0
    stamp = _now()
    meta = {
        "id": rid,
        "kind": "combat",
        "title": title,
        "status": "done",
        "created": stamp,
        "finished": stamp,
        "started_ts": time.time() - secs,
        "secs": round(secs, 3),
        "params": params,
        "lang": "en",
        "partial": False,
        "progress": {
            "done": total,
            "total": total,
            "encounter": "DUMMY",
            "encounter_name": "木桩",
        },
        "headline": _headline("combat", summary),
        "backend": "local-python",
    }
    path = os.path.join(run_dir, "meta.json")
    text = json.dumps(meta, ensure_ascii=False, indent=1) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def build(out_path):
    """跑两场木桩并写出 zip。返回 (字节数, 文件名)。"""
    data_dir = tempfile.mkdtemp(prefix="deckbench-demo-")
    os.environ["STS2SIM_GUI_DATA"] = data_dir
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from gui import paths
        from gui.backend import get_backend
        from sts2sim.deckpresets import save_preset

        paths.ensure_dirs()
        save_preset({
            "id": PRESET_ID,
            "name": "Demo deck",
            "mod": "claude_v34",
            "character": "claude",
            "cards": [
                {"id": "YIHESHI", "count": 1},
                {"id": "XIAOBENBEN", "count": 2},
            ],
            "encounters": [{"id": "DUMMY", "fights": 2}],
            "max_turns": 1,
            "seed": 1,
            "agent": "heuristic",
        })
        backend = get_backend()
        deck_params = {
            "preset": PRESET_ID,
            "title": "Demo deck",
            "seed": 1,
            "agent": "heuristic",
            "fights": 2,
        }
        probe_params = {
            "mods": ["claude_v34"],
            "decks": ["probe_noengine"],
            "custom": True,
            "rooms": [],
            "encounters": [{"id": "DUMMY", "fights": 2}],
            "max_turns": 1,
            "seed": 1,
            "agent": "heuristic",
            "fights": 2,
            "title": "Demo probe",
        }
        runs = (
            (DECK_ID, "Demo deck", deck_params),
            (PROBE_ID, "Demo probe", probe_params),
        )
        for rid, title, params in runs:
            folder = os.path.join(paths.RUNS_DIR, rid)
            secs = _run_combat(backend, folder, params)
            summary = backend.summarize("combat", folder)
            if not summary or not summary.get("fights"):
                raise SystemExit(f"{rid} produced no combat summary")
            _write_meta(folder, rid, title, params, secs, summary)
        from sts2sim.bundle import export_compare_bytes

        blob, filename = export_compare_bytes(DECK_ID, PROBE_ID, lang="en")
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(blob)
    os.replace(tmp, out_path)
    return len(blob), filename


def main(argv=None):
    _quiet_game_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="where to write the .deckbench.zip")
    args = parser.parse_args(argv)
    size, filename = build(args.out)
    print(json.dumps({"ok": True, "path": os.path.abspath(args.out), "filename": filename, "bytes": size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
