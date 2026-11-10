"""战斗批量的 workers：默认 1，和多进程的逐场结果相同，连战不在一条种子里并行。

不改模拟器的出牌和种子。训练木桩不需要本机游戏数据。
"""
import json
import os
import time

import pytest

from gui.fightworkers import (
    WorkersError,
    chain_links,
    checked_workers,
    fight_chain,
    probe_task,
    run_indexed,
    worker_cap,
)

EN = {"x-lang": "en"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODEX = os.path.join(ROOT, "tests", "fixtures", "encounters_min")

EXP = """name: workers_probe
title: workers probe
mods: [claude_v34]
seed: 11
fights: 1
max_turns: 1
agent: heuristic
rooms: []
decks: [probe_noengine]
extra:
  - {{deck: probe_noengine, encounter: DUMMY, fights: {n}, max_turns: 1, act: 1, room: "探针"}}
"""

CHAIN = """name: workers_chain
title: workers chain
mods: [claude_v34]
seed: 11
fights: 1
max_turns: 1
agent: heuristic
rooms: []
decks: [probe_noengine]
extra:
  - {{deck: probe_noengine, encounter: DUMMY, fights: 3, max_turns: 1, act: 1, room: "探针"}}
  - {{deck: probe_noengine, encounter: DUMMY, fights: 3, max_turns: 1, act: 1, room: "精英"}}
"""


def _task(deck, idx, enc):
    return ((["claude_v34"], deck, 1, "精英", idx, 1), {"encounter_id": enc})


def _stable(path):
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.pop("secs", None)
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


def _run_combat(exp_path, out, workers, chain=False):
    from gui.worker import main
    argv = ["combat", str(exp_path), "--workers", str(workers), "--out", str(out)]
    if chain:
        argv.append("--chain")
    main(argv)


def test_workers_default_to_one_and_cap_at_eight_or_the_cpu_count():
    assert checked_workers(None) == 1
    assert checked_workers(1) == 1
    cap = worker_cap()
    assert 1 <= cap <= 8
    assert cap == min(os.cpu_count() or 1, 8)
    assert checked_workers(10_000) == cap
    assert checked_workers(cap) == cap
    for bad in (0, -3, True, False, 1.5, "4"):
        with pytest.raises(WorkersError):
            checked_workers(bad)


def test_chain_links_follow_one_seed_across_encounters():
    tasks = [
        _task("deck", 0, "A"),
        _task("deck", 1, "A"),
        _task("deck", 0, "B"),
        _task("deck", 1, "B"),
    ]
    nxt, ready = chain_links(tasks)
    assert ready == [0, 1]
    assert nxt == {0: 2, 1: 3}


def test_gauntlet_chain_stays_ordered_inside_one_seed(tmp_path):
    """两个种子可以重叠。同一条种子里，后一场要等前一场结束。"""
    folder = tmp_path / "slots"
    folder.mkdir()

    def task(idx, enc):
        return (
            (["claude_v34"], "deck", 1, "精英", idx, 1),
            {"encounter_id": enc, "folder": str(folder), "delay": 0.35},
        )

    tasks = [task(0, "A"), task(1, "A"), task(0, "B"), task(1, "B")]
    ordered, _approx = run_indexed(probe_task, tasks, 2, chain=True)
    assert set(ordered) == {0, 1, 2, 3}

    def load(idx, enc):
        return json.loads((folder / f"{idx}-{enc}.json").read_text(encoding="utf-8"))

    a0, b0 = load(0, "A"), load(0, "B")
    a1, b1 = load(1, "A"), load(1, "B")
    assert a0["end"] <= b0["start"] + 0.05
    assert a1["end"] <= b1["start"] + 0.05
    assert a0["start"] < a1["end"] and a1["start"] < a0["end"]


def test_parallel_dummy_fights_match_serial_bytes(tmp_path):
    """同一批木桩，workers=1 和 workers=2 的 raw.jsonl 除每场用时外逐字节相同。"""
    exp = tmp_path / "exp.yaml"
    exp.write_text(EXP.format(n=6), encoding="utf-8")
    out1 = tmp_path / "w1"
    out2 = tmp_path / "w2"
    _run_combat(exp, out1, 1)
    _run_combat(exp, out2, 2)
    left = _stable(out1 / "raw.jsonl")
    right = _stable(out2 / "raw.jsonl")
    assert left == right
    rows = [json.loads(line) for line in left.splitlines()]
    assert len(rows) == 6
    assert [row["encounter"] for row in rows] == ["DUMMY"] * 6


def test_parallel_gauntlet_chain_matches_serial_bytes(tmp_path):
    """连战按种子串起来之后，进程数仍不改变逐场记录和顺序。"""
    exp = tmp_path / "chain.yaml"
    exp.write_text(CHAIN.format(), encoding="utf-8")
    out1 = tmp_path / "c1"
    out2 = tmp_path / "c2"
    _run_combat(exp, out1, 1, chain=True)
    _run_combat(exp, out2, 2, chain=True)
    assert _stable(out1 / "raw.jsonl") == _stable(out2 / "raw.jsonl")
    rows = [
        json.loads(line)
        for line in (out1 / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["room"] for row in rows] == ["探针", "探针", "探针", "精英", "精英", "精英"]


def test_saved_gauntlet_is_chained_and_a_single_dummy_is_not(tmp_path, monkeypatch):
    monkeypatch.setenv("DECKBENCH_CODEX_DIR", CODEX)
    from sts2sim import deckpresets
    from sts2sim import enemies as sim_enemies
    sim_enemies._DB.clear()
    deckpresets._CODEX["path"] = None
    deckpresets._ENC_CACHE["sig"] = None
    deckpresets._ENC_CACHE["rows"] = None
    try:
        from gui.backend import LocalPythonBackend
        backend = LocalPythonBackend()
        chained = tmp_path / "gauntlet"
        chained.mkdir()
        argv, _env, _cwd = backend.build_command("combat", {
            "mods": ["claude_v34"],
            "decks": ["probe_noengine"],
            "rooms": ["普通"],
            "gauntlet": "act1_elite",
            "max_turns": 1,
            "fights": 2,
            "seed": 1,
            "agent": "heuristic",
            "workers": 99,
        }, str(chained))
        assert "--chain" in argv
        assert argv[argv.index("--workers") + 1] == str(worker_cap())
        plain = tmp_path / "dummy"
        plain.mkdir()
        argv, _env, _cwd = backend.build_command("combat", {
            "mods": ["claude_v34"],
            "decks": ["probe_noengine"],
            "encounters": [{"id": "DUMMY", "fights": 4}],
            "max_turns": 1,
            "fights": 1,
            "seed": 1,
            "agent": "heuristic",
        }, str(plain))
        assert "--chain" not in argv
        assert argv[argv.index("--workers") + 1] == "1"
        assert fight_chain({"gauntlet": "act1_elite"}, {"rooms": [], "extra": [
            {"encounter": "NIB_ELITE_A"}, {"encounter": "NOT_A_REAL_ONE"},
        ]}) is True
    finally:
        sim_enemies._DB.clear()
        deckpresets._CODEX["path"] = None
        deckpresets._ENC_CACHE["sig"] = None
        deckpresets._ENC_CACHE["rows"] = None


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from gui.server import app
    with TestClient(app) as c:
        yield c


def test_http_rejects_bad_workers_and_cancel_still_partial(client, tmp_path, monkeypatch):
    from gui import paths
    data = tmp_path / "data"
    runs = data / "runs"
    runs.mkdir(parents=True)
    monkeypatch.setenv("STS2SIM_GUI_DATA", str(data))
    monkeypatch.setenv("DECKBENCH_FIGHT_GAP", "0.2")
    monkeypatch.setattr(paths, "RUNS_DIR", str(runs))
    saved = client.post("/api/decks", headers=EN, json={
        "id": "workdeck",
        "name": "Workers",
        "mod": "claude_v34",
        "max_turns": 1,
        "encounters": [{"id": "DUMMY", "fights": 8}],
        "cards": [
            {"id": "YIHESHI", "count": 1, "upgrade": False},
            {"id": "XIAOBENBEN", "count": 1, "upgrade": False},
        ],
    })
    assert saved.status_code == 200, saved.text
    bad = client.post("/api/runs", headers=EN, json={
        "kind": "combat",
        "params": {"preset": "workdeck", "fights": 1, "seed": 1, "agent": "heuristic", "workers": True},
    })
    assert bad.status_code == 400
    assert "Traceback" not in bad.text
    zero = client.post("/api/runs", headers=EN, json={
        "kind": "combat",
        "params": {"preset": "workdeck", "fights": 1, "seed": 1, "agent": "heuristic", "workers": 0},
    })
    assert zero.status_code == 400 and "workers" in zero.text
    started = client.post("/api/runs", headers=EN, json={
        "kind": "combat",
        "title": "parallel cancel",
        "params": {"preset": "workdeck", "fights": 1, "seed": 5, "agent": "heuristic", "workers": 2},
    })
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["argv"][body["argv"].index("--workers") + 1] == "2"
    rid = body["id"]
    seen = None
    deadline = time.time() + 90
    while time.time() < deadline:
        seen = client.get(f"/api/runs/{rid}/progress", headers=EN).json()
        if seen["status"] not in ("running", "queued") or (1 <= seen["done"] < seen["total"]):
            break
        time.sleep(0.05)
    assert seen["status"] == "running", seen
    assert 1 <= seen["done"] < seen["total"]
    cancelled = client.post(f"/api/runs/{rid}/cancel", headers=EN)
    assert cancelled.status_code == 200 and cancelled.json()["ok"] is True
    final = None
    deadline = time.time() + 60
    while time.time() < deadline:
        final = client.get(f"/api/runs/{rid}/progress", headers=EN).json()
        if final["status"] not in ("running", "queued"):
            break
        time.sleep(0.05)
    assert final["status"] == "cancelled", final
    assert final["partial"] is True
    assert 1 <= final["done"] < final["total"]
    rows = [
        json.loads(line)
        for line in (runs / rid / "out" / "raw.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == final["done"]
    assert all(row["encounter"] == "DUMMY" for row in rows)
