"""运行管理：每次测试一个文件夹 data/runs/<id>/（meta.json、run.log、输出），子进程按行读日志和进度。"""
import datetime as _dt
import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time

from . import i18n, paths

PROG = re.compile(r"^@@PROGRESS (.*)$")
DONE = re.compile(r"^@@DONE (.*)$")


def _runs_child(rid):
    """runs/<rid> 的真实路径。必须是单个路径段，并且解析后仍在 RUNS_DIR 里面。

    ``..``、带斜杠的 id、以及指到目录外的符号链接都返回 None，不读也不删。
    """
    if not isinstance(rid, str) or not rid or rid in (".", ".."):
        return None
    if "/" in rid or "\\" in rid or "\x00" in rid:
        return None
    root = os.path.realpath(paths.RUNS_DIR)
    path = os.path.realpath(os.path.join(root, rid))
    try:
        inside = os.path.normcase(os.path.commonpath([root, path])) == os.path.normcase(root)
    except ValueError:
        return None
    if not inside or os.path.normcase(path) == os.path.normcase(root):
        return None
    return path


def _now():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


CANCEL_NAME = "cancel.request"


def cancel_path(run_dir):
    return os.path.join(run_dir, CANCEL_NAME)


def cancel_requested(run_dir):
    return bool(run_dir) and os.path.isfile(cancel_path(run_dir))


def _elapsed(meta, now):
    status = meta.get("status")
    if status in ("running", "queued"):
        started = meta.get("started_ts")
        if isinstance(started, (int, float)) and not isinstance(started, bool):
            return round(max(0.0, now - float(started)), 3)
        return None
    secs = meta.get("secs")
    if isinstance(secs, (int, float)) and not isinstance(secs, bool):
        return round(max(0.0, float(secs)), 3)
    return None


def progress_view(meta, *, cancel_requested=False, now=None):
    """一次测试的进度。elapsed 用开始时间现算，不靠工人进程每秒回写。"""
    if not isinstance(meta, dict):
        return None
    prog = meta.get("progress") if isinstance(meta.get("progress"), dict) else {}
    try:
        done = int(prog.get("done") or 0)
    except (TypeError, ValueError):
        done = 0
    try:
        total = int(prog.get("total") or 0)
    except (TypeError, ValueError):
        total = 0
    status = meta.get("status") or ""
    partial = bool(meta.get("partial")) or status == "cancelled"
    moment = time.time() if now is None else now
    return {
        "id": meta.get("id"),
        "kind": meta.get("kind"),
        "status": status,
        "done": done,
        "total": total,
        "encounter": str(prog.get("encounter") or ""),
        "encounter_name": str(prog.get("encounter_name") or ""),
        "elapsed": _elapsed(meta, moment),
        "partial": partial,
        "cancel_requested": bool(cancel_requested) and status in ("running", "queued"),
    }


class Job:
    def __init__(self, meta, run_dir):
        self.meta = meta
        self.dir = run_dir
        self.lines = []
        self.proc = None
        self.cancelled = False
        self.lock = threading.Lock()

    def save(self):
        tmp = os.path.join(self.dir, "meta.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(self.dir, "meta.json"))


class JobManager:
    def __init__(self, backend):
        self.backend = backend
        self.jobs = {}
        paths.ensure_dirs()
        # 上次没跑完就关掉的，标记为中断
        for m in self.list():
            if m.get("status") in ("running", "queued"):
                child = _runs_child(m.get("id"))
                if child is None:
                    continue
                m["status"] = "interrupted"
                m["error"] = i18n.t("jobs.interrupted")
                with open(os.path.join(child, "meta.json"), "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False, indent=1)

    # ---------------- 历史
    def list(self):
        out = []
        if not os.path.isdir(paths.RUNS_DIR):
            return out
        for d in os.listdir(paths.RUNS_DIR):
            child = _runs_child(d)
            if child is None:
                continue
            f = os.path.join(child, "meta.json")
            if os.path.exists(f):
                loaded = None
                try:
                    with open(f, encoding="utf-8") as fh:
                        loaded = json.load(fh)
                except (OSError, ValueError, TypeError):
                    loaded = None
                if isinstance(loaded, dict):
                    out.append(loaded)
        out.sort(key=lambda m: m.get("created", ""), reverse=True)
        return out

    def get(self, rid):
        if isinstance(rid, str) and rid in self.jobs:
            return self.jobs[rid].meta
        child = _runs_child(rid)
        if child is None:
            return None
        f = os.path.join(child, "meta.json")
        if not os.path.exists(f):
            return None
        return json.load(open(f, encoding="utf-8"))

    def run_dir(self, rid):
        d = _runs_child(rid)
        return d if d and os.path.isdir(d) else None

    def log_lines(self, rid, since=0):
        j = self.jobs.get(rid) if isinstance(rid, str) else None
        if j:
            with j.lock:
                return j.lines[since:], len(j.lines)
        child = _runs_child(rid)
        if child is None:
            return [], 0
        f = os.path.join(child, "run.log")
        if not os.path.exists(f):
            return [], 0
        lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        return lines[since:], len(lines)

    def delete(self, rid):
        import shutil
        j = self.jobs.get(rid)
        if j and j.meta["status"] == "running":
            raise RuntimeError(i18n.t("jobs.cancelFirst"))
        d = self.run_dir(rid)
        if d:
            shutil.rmtree(d)
        self.jobs.pop(rid, None)

    def rename(self, rid, title):
        d = self.run_dir(rid)
        m = self.get(rid)
        m["title"] = title
        if rid in self.jobs:
            self.jobs[rid].meta["title"] = title
            self.jobs[rid].save()
        else:
            json.dump(m, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return m

    # ---------------- 运行
    def start(self, kind, params, title=None, lang=None):
        rid = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
        d = os.path.join(paths.RUNS_DIR, rid)
        os.makedirs(d)
        meta = {"id": rid, "kind": kind, "title": title or params.get("title") or "", "params": params,
                "backend": self.backend.id, "status": "running", "created": _now(), "started_ts": time.time(),
                "progress": {"done": 0, "total": int(params.get("n") or 0)}}
        j = Job(meta, d)
        argv, env, cwd = self.backend.build_command(kind, params, d)
        lang = lang if lang in i18n.LANGS else i18n.current()
        env = dict(env)
        env["DECKBENCH_LANG"] = lang      # 工作进程的日志用开始运行时的界面语言
        env["DECKBENCH_CANCEL_FILE"] = cancel_path(d)
        meta["lang"] = lang
        meta["argv"] = argv
        j.save()
        self.jobs[rid] = j
        threading.Thread(target=self._run, args=(j, argv, env, cwd), daemon=True).start()
        return meta

    def wait(self, rid, timeout=900):
        """等到这次测试离开 running / queued。超时仍返回当时的 meta，不另开模拟。"""
        deadline = time.monotonic() + timeout
        while True:
            meta = self.get(rid)
            if not isinstance(meta, dict):
                return None
            if meta.get("status") not in ("running", "queued"):
                return meta
            if time.monotonic() >= deadline:
                return meta
            time.sleep(0.05)

    def _run(self, j, argv, env, cwd):
        logf = open(os.path.join(j.dir, "run.log"), "w", encoding="utf-8")
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        else:
            kw["start_new_session"] = True
        try:
            j.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", bufsize=1, **kw)
            for line in j.proc.stdout:
                line = line.rstrip("\n")
                m = PROG.match(line)
                if m:
                    try:
                        p = json.loads(m.group(1))
                        prog = {
                            "done": int(p["done"]),
                            "total": int(p["total"]),
                            "encounter": str(p.get("encounter") or ""),
                            "encounter_name": str(p.get("encounter_name") or ""),
                        }
                    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                        prog = None
                    if prog is not None:
                        with j.lock:
                            if j.cancelled or cancel_requested(j.dir):
                                prog["cancel_requested"] = True
                            j.meta["progress"] = prog
                            j.save()
                    continue
                if DONE.match(line):
                    continue
                with j.lock:
                    j.lines.append(line)
                logf.write(line + "\n")
                logf.flush()
            rc = j.proc.wait()
        except Exception as e:  # noqa
            rc = -1
            with j.lock:
                j.lines.append(i18n.t("jobs.startFailed", j.meta.get("lang"), err=e))
            logf.write(i18n.t("jobs.startFailed", j.meta.get("lang"), err=e) + "\n")
        logf.close()
        stopped = cancel_requested(j.dir)
        summary = None
        summary_error = None
        with j.lock:
            stopped = bool(j.cancelled or stopped)
            kind = j.meta.get("kind")
            run_dir = j.dir
        if stopped or rc == 0:
            try:
                summary = self.backend.summarize(kind, run_dir)
            except Exception as exc:  # noqa: BLE001
                summary_error = str(exc)
        with j.lock:
            j.meta["finished"] = _now()
            j.meta["secs"] = time.time() - j.meta["started_ts"]
            if stopped:
                j.meta["status"] = "cancelled"
                j.meta["partial"] = True
                if summary_error:
                    j.meta["headline"] = {"error": summary_error, "partial": True}
                else:
                    j.meta["headline"] = _headline(j.meta["kind"], summary)
                    j.meta["headline"]["partial"] = True
                msg = i18n.t("jobs.cancelled", j.meta.get("lang"), done=j.meta.get("progress", {}).get("done", 0),
                             total=j.meta.get("progress", {}).get("total", "?"))
                j.lines.append(msg)
                with open(os.path.join(j.dir, "run.log"), "a", encoding="utf-8") as handle:
                    handle.write(msg + "\n")
            elif rc == 0:
                j.meta["status"] = "done"
                j.meta["partial"] = False
                if summary_error:
                    j.meta["headline"] = {"error": summary_error}
                else:
                    j.meta["headline"] = _headline(j.meta["kind"], summary)
            else:
                j.meta["status"] = "failed"
                j.meta["error"] = "\n".join(j.lines[-15:])
            j.save()

    def progress(self, rid):
        if not isinstance(rid, str) or not rid:
            return None
        j = self.jobs.get(rid)
        if j is not None:
            with j.lock:
                requested = bool(j.cancelled) or cancel_requested(j.dir)
                return progress_view(j.meta, cancel_requested=requested)
        meta = self.get(rid)
        if not isinstance(meta, dict):
            return None
        child = self.run_dir(rid)
        requested = cancel_requested(child) if child else False
        prog = meta.get("progress") if isinstance(meta.get("progress"), dict) else {}
        return progress_view(meta, cancel_requested=requested or bool(prog.get("cancel_requested")))

    def cancel(self, rid):
        """让工人在两场之间停下。不杀进程，已经打完的场次会写下来。"""
        if not isinstance(rid, str) or not rid:
            return False
        j = self.jobs.get(rid)
        meta = None
        if j is not None:
            with j.lock:
                meta = j.meta
        else:
            meta = self.get(rid)
        if not isinstance(meta, dict) or meta.get("status") not in ("running", "queued"):
            return False
        folder = j.dir if j is not None else self.run_dir(rid)
        if not folder:
            return False
        with open(cancel_path(folder), "w", encoding="utf-8") as handle:
            handle.write("1\n")
        if j is not None:
            with j.lock:
                j.cancelled = True
                prog = dict(j.meta.get("progress") or {})
                prog["cancel_requested"] = True
                j.meta["progress"] = prog
                j.save()
        return True

    def _kill(self, j):
        if not j.proc or j.proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(j.proc.pid)], capture_output=True,
                               creationflags=0x08000000)
            else:
                os.killpg(j.proc.pid, signal.SIGTERM)
        except Exception:
            j.proc.kill()

    def shutdown(self):
        for _rid, j in list(self.jobs.items()):
            if j.proc and j.proc.poll() is None:
                self.cancel(j.meta.get("id"))
                self._kill(j)


def _headline(kind, s):
    if not s:
        return {}
    if kind == "batch":
        return {k: s.get(k) for k in ("n", "errors", "avg_floor", "boss1", "act2", "win")}
    return {"fights": s.get("fights"), "win": s.get("win"), "cells": len(s.get("cells") or [])}
