"""战斗批量的进程数。

默认 1，和一场接一场相同。上限是 ``min(cpu_count, 8)``。
大于 1 时用 spawn 的进程池：Windows 和 PyInstaller 都走同一条路。
每场仍用自己的种子。结果按原来的场次顺序写回。

连战是一条链：同一个种子里的遭遇按顺序打，不同种子可以同时打。
"""
import itertools
import math
import multiprocessing
import os
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

MAX_WORKERS = 8


class WorkersError(ValueError):
    """workers / procs 不是从 1 起的整数。"""

    def __init__(self, field):
        self.field = field
        super().__init__(field)


def worker_cap():
    """这一台机器允许的最多进程。至少 1，至多 8。"""
    cpus = os.cpu_count() or 1
    return max(1, min(int(cpus), MAX_WORKERS))


def checked_workers(value, field="workers"):
    """省略是 1。大于上限时收到上限。0、负数、布尔和小数都拒绝。"""
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkersError(field)
    return min(value, worker_cap())


def workers_from_params(params):
    """请求里的 workers。没写时沿用旧的 procs。两个都没写是 1。"""
    if not isinstance(params, dict):
        return checked_workers(None)
    if "workers" in params and params.get("workers") is not None:
        return checked_workers(params.get("workers"), "workers")
    if "procs" in params and params.get("procs") is not None:
        return checked_workers(params.get("procs"), "procs")
    return checked_workers(None)


def support_spawn():
    """spawn 子进程在 Windows 和 PyInstaller 里去跑工作函数，不再开一次界面。

    非 Windows 的打包程序里 ``multiprocessing.freeze_support`` 什么也不做，
    所以这里再调 spawn 自己的入口。普通启动时命令行没有 ``--multiprocessing-fork``，调用是空的。
    """
    import multiprocessing
    import multiprocessing.spawn

    multiprocessing.freeze_support()
    if getattr(sys, "frozen", False):
        multiprocessing.spawn.freeze_support()


def combat_initializer():
    """每个 spawn 出来的进程自己把模拟器路径和用户 mod 补丁装上。"""
    from gui import paths

    paths.setup_sys_path()
    from gui import modpatch

    modpatch.apply()


def combat_task(task):
    """打一场，并带回这一场新记下的近似说明。

    近似按场次顺序合并时，先出现的说明留下，和单进程里 ``setdefault`` 一样。
    """
    from sts2sim import enemies as EN
    from sts2sim.runner import _task

    before = set(EN.APPROX)
    result = _task(task)
    delta = [(key, EN.APPROX[key]) for key in EN.APPROX if key not in before]
    return result, delta


def probe_task(task):
    """测试用：记下这一场的开始和结束，不打战斗。"""
    import json

    folder = task[1]["folder"]
    idx = task[0][4]
    enc = str(task[1].get("encounter_id") or "")
    delay = float(task[1].get("delay") or 0)
    started = time.time()
    if delay:
        time.sleep(delay)
    ended = time.time()
    path = os.path.join(folder, f"{idx}-{enc}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"idx": idx, "encounter": enc, "start": started, "end": ended}, handle)
    return {"idx": idx, "encounter": enc}


def chain_links(tasks):
    """连战：同一套牌、同一个场次序号是一条链，链上的遭遇按计划里的顺序。

    返回 ``(下一场, 一开始就能打的下标)``。不同的序号彼此独立。
    """
    buckets = {}
    order = []
    for pos, task in enumerate(tasks):
        key = (task[0][1], task[0][4])
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(pos)
    nxt = {}
    ready = []
    for key in order:
        positions = buckets[key]
        ready.append(positions[0])
        for left, right in itertools.pairwise(positions):
            nxt[left] = right
    return nxt, ready


def fight_chain(params, exp):
    """这场测试是不是连战。

    房间表还在时，每场仍是独立的格子，不串成链。
    只剩 extra、而且遭遇顺序刚好是某一条连战，或者请求写了 gauntlet，才串起来。
    """
    if not isinstance(exp, dict):
        return False
    if exp.get("rooms"):
        return False
    extra = exp.get("extra") or []
    if not isinstance(extra, list) or len(extra) < 2:
        return False
    ids = []
    for row in extra:
        if not isinstance(row, dict):
            return False
        eid = row.get("encounter")
        if not isinstance(eid, str) or not eid.strip():
            return False
        ids.append(eid.strip())
    if isinstance(params, dict):
        named = params.get("gauntlet")
        if isinstance(named, str) and named.strip():
            return True
    return _matches_gauntlet(ids)


def _matches_gauntlet(ids):
    if len(ids) < 2:
        return False
    from sts2sim.deckpresets import DeckPresetError, _gauntlet_list, playable_encounters

    try:
        groups = _gauntlet_list(playable_encounters())
    except (OSError, DeckPresetError, RuntimeError, ValueError, KeyError, TypeError):
        return False
    for group in groups:
        members = [row.get("id") for row in group.get("encounters") or []]
        if members == ids:
            return True
    return False


def _gap():
    raw = os.environ.get("DECKBENCH_FIGHT_GAP") or ""
    try:
        gap = float(raw)
    except ValueError:
        return 0.0
    if math.isnan(gap) or gap < 0:
        return 0.0
    return min(gap, 2.0)


def _cancelled(cancel):
    if cancel is None:
        return False
    return bool(cancel())


def _merge_approx(ordered):
    """按场次下标合并近似说明。先出现的留下。"""
    merged = {}
    for pos in range(len(ordered)):
        payload = ordered.get(pos)
        if not isinstance(payload, tuple) or len(payload) != 2:
            continue
        for key, text in payload[1] or []:
            merged.setdefault(key, text)
    return merged


def _unwrap(payload):
    if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[1], list):
        return payload[0]
    return payload


def run_indexed(fn, tasks, workers, *, chain=False, on_each=None, initializer=None, cancel=None):
    """按计划下标跑完。返回 ``(结果字典, 近似说明)``。

    workers 为 1，或同时只能有一条在飞，就在本进程里打，不开进程池。
    取消之后不再派发。已经派发的打完再返回。
    """
    tasks = list(tasks)
    if chain:
        nxt, ready = chain_links(tasks)
    else:
        nxt, ready = {}, list(range(len(tasks)))
    width = min(max(1, int(workers or 1)), len(ready) or 1)
    ordered = {}

    def finish(pos, payload):
        ordered[pos] = payload
        if on_each is not None:
            on_each(pos, _unwrap(payload), len(ordered))

    if width <= 1 or not tasks:
        while ready and not _cancelled(cancel):
            pos = ready.pop(0)
            finish(pos, fn(tasks[pos]))
            gap = _gap()
            if gap and not _cancelled(cancel):
                time.sleep(gap)
            if not _cancelled(cancel) and pos in nxt:
                ready.append(nxt[pos])
        return ordered, _merge_approx(ordered)

    ctx = multiprocessing.get_context("spawn")
    executor = ProcessPoolExecutor(max_workers=width, mp_context=ctx, initializer=initializer)
    pending = {}
    try:
        def submit():
            while ready and len(pending) < width and not _cancelled(cancel):
                pos = ready.pop(0)
                pending[executor.submit(fn, tasks[pos])] = pos

        submit()
        while pending:
            done, _pending = wait(tuple(pending), timeout=0.05, return_when=FIRST_COMPLETED)
            if not done:
                if not _cancelled(cancel):
                    submit()
                continue
            for fut in done:
                pos = pending.pop(fut)
                finish(pos, fut.result())
                if not _cancelled(cancel) and pos in nxt:
                    ready.append(nxt[pos])
            gap = _gap()
            if gap and not _cancelled(cancel):
                time.sleep(gap)
            if not _cancelled(cancel):
                submit()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return ordered, _merge_approx(ordered)
