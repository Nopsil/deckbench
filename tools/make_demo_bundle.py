"""用现有的战斗工人生成内置示例结果包。

没有本机游戏数据时，仓库里能分出胜负的遭遇是 ``sts2sim.fightcheck`` 的合成怪物
（蛮兵、术士、荆棘），不是训练木桩，也不是游戏遭遇。脚本把这三只写成临时
codex，再让 ``gui.worker combat`` 打两套出厂探针：

- ``probe_noengine``（探针·无引擎）
- ``probe_D``（探针·路线D）

各 30 场，回合上限是出厂实验的整场上限（30）。场次下标 0–29 走工人自己的
种子。两边 ``shared_plan``，所以包的 kind 是 ``head_to_head``。胜率、掉血和
回合都来自这次模拟，不手写。

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

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "gui", "demo", "sample.deckbench.zip")
LEFT_ID = "demo-noengine"
RIGHT_ID = "demo-routed"
ENCOUNTER_ID = "SYN_TRIO"
FIGHTS = 30
ROOM = "精英"


def _quiet_game_env():
    for key in list(os.environ):
        game = key.startswith(("DECKBENCH_GAME", "DECKBENCH_MENTOR_", "STS2SIM_MENTOR"))
        if game or key in ("DECKBENCH_LANG", "DECKBENCH_CODEX_DIR"):
            os.environ.pop(key, None)
    os.environ["DECKBENCH_MENTOR_NO_DEFAULTS"] = "1"


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _move_raw(move):
    raw = {"id": move.id, "name": move.name, "intent": move.intent}
    if move.damage:
        raw["damage"] = {"normal": move.damage, "hit_count": move.hits}
    if move.block:
        raw["block"] = move.block
    if move.powers:
        raw["powers"] = [
            {"power_id": power, "target": target, "amount": amount}
            for power, target, amount in move.powers
        ]
    return raw


def _write_codex(folder):
    """把 fightcheck 里已有的合成怪物写成工人能读的 codex。不另编数值。"""
    from sts2sim.fightcheck import FOES

    monsters = []
    for defin in FOES:
        moves = [_move_raw(move) for move in defin.moves.values()]
        monsters.append({
            "id": defin.id,
            "name": defin.name,
            "min_hp": defin.min_hp,
            "max_hp": defin.max_hp,
            "moves": moves,
            "innate_powers": [
                {"power_id": power, "amount": amount} for power, amount in defin.innate
            ],
            "attack_pattern": {"type": "cycle"},
        })
    encounter = {
        "id": ENCOUNTER_ID,
        "name": "Synthetic trio",
        "act": "Act 1",
        "room_type": "Elite",
        "is_weak": False,
        "monsters": [{"id": "BRUTE"}, {"id": "HEX"}, {"id": "THORN"}],
    }
    _dump(folder, "eng_monsters.json", monsters)
    _dump(folder, "zhs_monsters.json", [{"id": row["id"], "name": row["name"]} for row in monsters])
    _dump(folder, "eng_encounters.json", [encounter])
    _dump(folder, "zhs_encounters.json", [{"id": ENCOUNTER_ID, "name": "蛮兵、术士、荆棘"}])


def _dump(folder, name, payload):
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.write("\n")


def _experiment(name, title, deck):
    return {
        "name": name,
        "title": title,
        "mods": ["claude_v34"],
        "seed": 1,
        "fights": 1,
        "max_turns": 30,
        "agent": "heuristic",
        "rooms": [],
        "decks": [],
        "extra": [{
            "deck": deck,
            "encounter": ENCOUNTER_ID,
            "fights": FIGHTS,
            "max_turns": 30,
            "act": 1,
            "room": ROOM,
        }],
    }


def _run_combat(run_dir, exp):
    from gui.backend import worker_argv, worker_env

    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "experiment.yaml")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(exp, handle, allow_unicode=True, sort_keys=False)
    argv = worker_argv("combat", path, "--workers", "1", "--out", os.path.join(run_dir, "out"))
    env = worker_env()
    started = time.time()
    proc = subprocess.run(
        argv, cwd=ROOT, env=env, check=False, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        raise subprocess.CalledProcessError(proc.returncode, argv, proc.stdout, proc.stderr)
    return time.time() - started


def _first_row(run_dir):
    path = os.path.join(run_dir, "out", "raw.jsonl")
    with open(path, encoding="utf-8") as handle:
        line = handle.readline()
    return json.loads(line)


def _write_meta(run_dir, rid, title, deck, secs, summary):
    from gui.jobs import _headline

    row = _first_row(run_dir)
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
        "params": {
            "mods": ["claude_v34"],
            "decks": [deck],
            "encounters": [{"id": ENCOUNTER_ID, "fights": FIGHTS}],
            "max_turns": 30,
            "seed": 1,
            "agent": "heuristic",
            "fights": FIGHTS,
            "title": title,
            "shared_plan": True,
        },
        "lang": "en",
        "partial": False,
        "progress": {
            "done": total,
            "total": total,
            "encounter": str(row.get("encounter") or ""),
            "encounter_name": str(row.get("enc_name") or ""),
        },
        "headline": _headline("combat", summary),
        "backend": "local-python",
    }
    path = os.path.join(run_dir, "meta.json")
    text = json.dumps(meta, ensure_ascii=False, indent=1) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _require_outcomes(run_dirs):
    results = set()
    hp = []
    for folder in run_dirs:
        path = os.path.join(folder, "out", "raw.jsonl")
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                results.add(row.get("result"))
                hp.append(row.get("hp_lost") or 0)
    if "win" not in results or "loss" not in results:
        raise SystemExit("demo fights did not both win and lose: " + ",".join(sorted(map(str, results))))
    if not any(hp):
        raise SystemExit("demo fights lost no HP")


def build(out_path):
    """跑两套探针对合成三人组，写出 head-to-head 结果包。返回 (字节数, 文件名)。"""
    data_dir = tempfile.mkdtemp(prefix="deckbench-demo-")
    codex = os.path.join(data_dir, "codex")
    os.makedirs(codex, exist_ok=True)
    os.environ["STS2SIM_GUI_DATA"] = data_dir
    os.environ["DECKBENCH_CODEX_DIR"] = codex
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from gui import paths
        from gui.backend import get_backend

        paths.ensure_dirs()
        _write_codex(codex)
        backend = get_backend()
        runs = (
            (LEFT_ID, "探针·无引擎", "probe_noengine"),
            (RIGHT_ID, "探针·路线D", "probe_D"),
        )
        folders = []
        for rid, title, deck in runs:
            folder = os.path.join(paths.RUNS_DIR, rid)
            secs = _run_combat(folder, _experiment(rid, title, deck))
            summary = backend.summarize("combat", folder)
            if not summary or summary.get("fights") != FIGHTS:
                raise SystemExit(f"{rid} produced no {FIGHTS}-fight summary")
            _write_meta(folder, rid, title, deck, secs, summary)
            folders.append(folder)
        _require_outcomes(folders)
        from sts2sim.bundle import export_compare_bytes

        blob, filename = export_compare_bytes(LEFT_ID, RIGHT_ID, lang="en")
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    if len(blob) > 1024 * 1024:
        raise SystemExit(f"demo bundle is {len(blob)} bytes")
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
    print(json.dumps({
        "ok": True, "path": os.path.abspath(args.out), "filename": filename, "bytes": size,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
