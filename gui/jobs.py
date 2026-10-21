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


def _now():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


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
                m["status"] = "interrupted"
                m["error"] = i18n.t("jobs.interrupted")
                with open(os.path.join(paths.RUNS_DIR, m["id"], "meta.json"), "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False, indent=1)

    # ---------------- 历史
    def list(self):
        out = []
        if not os.path.isdir(paths.RUNS_DIR):
            return out
        for d in os.listdir(paths.RUNS_DIR):
            f = os.path.join(paths.RUNS_DIR, d, "meta.json")
            if os.path.exists(f):
                try:
                    out.append(json.load(open(f, encoding="utf-8")))
                except Exception:
                    pass
        out.sort(key=lambda m: m.get("created", ""), reverse=True)
        return out

    def get(self, rid):
        if rid in self.jobs:
            return self.jobs[rid].meta
        f = os.path.join(paths.RUNS_DIR, rid, "meta.json")
        if not os.path.exists(f):
            return None
        return json.load(open(f, encoding="utf-8"))

    def run_dir(self, rid):
        d = os.path.join(paths.RUNS_DIR, os.path.basename(rid))
        return d if os.path.isdir(d) else None

    def log_lines(self, rid, since=0):
        j = self.jobs.get(rid)
        if j:
            with j.lock:
                return j.lines[since:], len(j.lines)
        f = os.path.join(paths.RUNS_DIR, rid, "run.log")
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
        meta["lang"] = lang
        meta["argv"] = argv
        j.save()
        self.jobs[rid] = j
        threading.Thread(target=self._run, args=(j, argv, env, cwd), daemon=True).start()
        return meta

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
                        j.meta["progress"] = {"done": p["done"], "total": p["total"]}
                    except Exception:
                        pass
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
        j.meta["finished"] = _now()
        j.meta["secs"] = time.time() - j.meta["started_ts"]
        if j.cancelled:
            j.meta["status"] = "cancelled"
            msg = i18n.t("jobs.cancelled", j.meta.get("lang"), done=j.meta.get("progress", {}).get("done", 0),
                         total=j.meta.get("progress", {}).get("total", "?"))
            with j.lock:
                j.lines.append(msg)
            with open(os.path.join(j.dir, "run.log"), "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        elif rc == 0:
            j.meta["status"] = "done"
            try:
                s = self.backend.summarize(j.meta["kind"], j.dir)
                j.meta["headline"] = _headline(j.meta["kind"], s)
            except Exception as e:  # noqa
                j.meta["headline"] = {"error": str(e)}
        else:
            j.meta["status"] = "failed"
            j.meta["error"] = "\n".join(j.lines[-15:])
        j.save()

    def cancel(self, rid):
        j = self.jobs.get(rid)
        if not j or not j.proc or j.proc.poll() is not None:
            return False
        j.cancelled = True
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(j.proc.pid)], capture_output=True,
                               creationflags=0x08000000)
            else:
                os.killpg(j.proc.pid, signal.SIGTERM)
        except Exception:
            j.proc.kill()
        return True

    def shutdown(self):
        for rid, j in list(self.jobs.items()):
            if j.proc and j.proc.poll() is None:
                self.cancel(rid)


def _headline(kind, s):
    if not s:
        return {}
    if kind == "batch":
        return {k: s.get(k) for k in ("n", "errors", "avg_floor", "boss1", "act2", "win")}
    return {"fights": s.get("fights"), "win": s.get("win"), "cells": len(s.get("cells") or [])}
