"""FastAPI 本地服务（只监听 127.0.0.1）：API + 前端静态文件。"""
import asyncio
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import yaml
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import paths
from .backend import get_backend
from .jobs import JobManager

backend = get_backend()
jobs = JobManager(backend)
app = FastAPI(title="DeckBench GUI")


class StartReq(BaseModel):
    kind: str
    params: dict
    title: str | None = None


class TitleReq(BaseModel):
    title: str


def _need(rid):
    m = jobs.get(rid)
    if not m:
        raise HTTPException(404, "找不到这次测试")
    return m


@app.get("/api/catalog")
def catalog(refresh: bool = False):
    try:
        return backend.catalog(refresh)
    except Exception as e:  # noqa
        raise HTTPException(500, str(e))


@app.get("/api/runs")
def runs():
    return jobs.list()


@app.post("/api/runs")
def start(req: StartReq):
    if req.kind not in ("batch", "combat"):
        raise HTTPException(400, "未知类型")
    p = req.params
    if req.kind == "combat" and not p.get("preset") and not p.get("decks"):
        raise HTTPException(400, "至少选一个卡组")
    return jobs.start(req.kind, p, req.title)


@app.get("/api/runs/{rid}")
def run(rid: str):
    return _need(rid)


@app.patch("/api/runs/{rid}")
def rename(rid: str, req: TitleReq):
    _need(rid)
    return jobs.rename(rid, req.title)


@app.delete("/api/runs/{rid}")
def delete(rid: str):
    _need(rid)
    try:
        jobs.delete(rid)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/runs/{rid}/cancel")
def cancel(rid: str):
    _need(rid)
    return {"ok": jobs.cancel(rid)}


@app.post("/api/runs/{rid}/rerun")
def rerun(rid: str):
    m = _need(rid)
    t = m.get("title") or ""
    return jobs.start(m["kind"], m["params"], (t + "（重跑）") if t else None)


@app.get("/api/runs/{rid}/summary")
def summary(rid: str):
    m = _need(rid)
    if m.get("status") != "done":
        raise HTTPException(409, "这次测试还没有完成")
    return {"meta": m, "summary": backend.summarize(m["kind"], jobs.run_dir(rid))}


@app.get("/api/runs/{rid}/report")
def report(rid: str):
    _need(rid)
    f = os.path.join(jobs.run_dir(rid), "out", "report.md")
    if not os.path.exists(f):
        raise HTTPException(404, "这次测试没有生成 report.md")
    return {"markdown": open(f, encoding="utf-8").read()}


FILES = {"runs.jsonl", "run.log", "experiment.yaml", "report.md", "cells.csv", "cards.csv", "encounters.csv", "raw.jsonl"}


@app.get("/api/runs/{rid}/files/{name}")
def runfile(rid: str, name: str):
    _need(rid)
    if name not in FILES:
        raise HTTPException(404)
    d = jobs.run_dir(rid)
    for f in (os.path.join(d, name), os.path.join(d, "out", name)):
        if os.path.exists(f):
            return FileResponse(f, filename=name)
    raise HTTPException(404)


@app.post("/api/runs/{rid}/open")
def open_folder(rid: str):
    _need(rid)
    d = jobs.run_dir(rid)
    try:
        if os.name == "nt":
            os.startfile(d)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])
    except Exception as e:  # noqa
        return {"ok": False, "path": d, "error": str(e)}
    return {"ok": True, "path": d}


@app.get("/api/runs/{rid}/log")
def log(rid: str, since: int = 0):
    _need(rid)
    lines, n = jobs.log_lines(rid, since)
    return {"lines": lines, "next": n, "meta": jobs.get(rid)}


@app.get("/api/runs/{rid}/stream")
async def stream(rid: str, since: int = 0):
    _need(rid)

    async def gen():
        pos = since
        last_prog = None
        while True:
            lines, n = jobs.log_lines(rid, pos)
            pos = n
            m = jobs.get(rid) or {}
            prog = json.dumps(m.get("progress"))
            if lines or prog != last_prog:
                last_prog = prog
                yield "data: " + json.dumps({"lines": lines, "next": pos, "progress": m.get("progress"),
                                             "status": m.get("status")}, ensure_ascii=False) + "\n\n"
            if m.get("status") not in ("running", "queued"):
                yield "data: " + json.dumps({"lines": [], "next": pos, "progress": m.get("progress"), "status": m.get("status"),
                                             "final": True, "meta": m}, ensure_ascii=False) + "\n\n"
                return
            await asyncio.sleep(0.4)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/ab")
def ab(a: str, b: str):
    ma, mb = _need(a), _need(b)
    if ma["kind"] != mb["kind"]:
        raise HTTPException(400, "两次测试类型不同（整局批量 vs 战斗实验），不能对比")
    if ma.get("status") != "done" or mb.get("status") != "done":
        raise HTTPException(400, "两次测试都要已完成")
    return {"kind": ma["kind"], "a": ma, "b": mb, "result": backend.ab(ma["kind"], jobs.run_dir(a), jobs.run_dir(b))}


# ---------------------------------------------------------------- mod 上传
NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")


@app.post("/api/mods/upload")
async def upload_mod(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件太大（上限 50 MB）")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "不是有效的 zip 文件")
    names = [n for n in zf.namelist() if not n.endswith("/")]
    for n in names:
        if n.startswith("/") or ".." in n.replace("\\", "/").split("/"):
            raise HTTPException(400, f"zip 里有不安全的路径：{n}")
    ymls = sorted((n for n in names if n.replace("\\", "/").split("/")[-1] == "mod.yaml"), key=lambda n: n.count("/"))
    if not ymls:
        raise HTTPException(400, "zip 里找不到 mod.yaml（格式见 README「给新 mod 写内容」）")
    prefix = ymls[0][: -len("mod.yaml")]
    try:
        meta = yaml.safe_load(zf.read(ymls[0]).decode("utf-8")) or {}
    except Exception as e:  # noqa
        raise HTTPException(400, f"mod.yaml 解析失败：{e}")
    name = str(meta.get("name") or "").strip()
    if not NAME_RE.match(name):
        raise HTTPException(400, "mod.yaml 的 name 只能用英文字母、数字、下划线（1–40 个字符）")
    if os.path.isdir(os.path.join(paths.SIM_ROOT, "mods", name)):
        raise HTTPException(400, f"「{name}」和内置 mod 重名，请改 name")
    problems = []
    for key in ("cards", "decks", "potions"):
        for f in meta.get(key, []) or []:
            if prefix + f not in names:
                problems.append(f"{key} 里列出的 {f} 不在 zip 里")
            else:
                try:
                    yaml.safe_load(zf.read(prefix + f).decode("utf-8"))
                except Exception as e:  # noqa
                    problems.append(f"{f} 不是有效的 YAML：{e}")
    if meta.get("hooks") and prefix + meta["hooks"] not in names:
        problems.append(f"hooks 文件 {meta['hooks']} 不在 zip 里")
    if not meta.get("decks"):
        problems.append("没有 decks：战斗实验需要至少一个卡组")
    if problems:
        raise HTTPException(400, "；".join(problems))
    tmp = tempfile.mkdtemp(prefix="mod_", dir=paths.CACHE_DIR)
    try:
        for n in names:
            if n.startswith(prefix):
                rel = n[len(prefix):]
                dst = os.path.join(tmp, *rel.replace("\\", "/").split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(zf.read(n))
        dst = os.path.join(paths.USER_MODS_DIR, name)
        replaced = os.path.isdir(dst)
        backup = None
        if replaced:
            backup = dst + ".bak"
            shutil.rmtree(backup, ignore_errors=True)
            os.replace(dst, backup)
        shutil.move(tmp, dst)
        # 试加载：先单独加载；失败再带上原版（很多 mod 的卡组会用到原版牌）
        res, deps = None, []
        for d in ([], ["vanilla"]):
            res = await asyncio.to_thread(backend.validate_mod, name, d)
            if res.get("ok"):
                deps = d
                break
        if not res.get("ok"):
            shutil.rmtree(dst, ignore_errors=True)
            if backup:
                os.replace(backup, dst)
            raise HTTPException(400, "模拟器加载失败：\n" + res.get("error", ""))
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        json.dump({"deps": deps, "uploaded_name": file.filename}, open(os.path.join(dst, "gui_meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        return {"ok": True, "name": name, "title": meta.get("title") or name, "deps": deps, "replaced": replaced, **res}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.delete("/api/mods/{name}")
def delete_mod(name: str):
    if not NAME_RE.match(name):
        raise HTTPException(400)
    d = os.path.join(paths.USER_MODS_DIR, name)
    if not os.path.isdir(d):
        raise HTTPException(404, "只能删除自己上传的 mod")
    shutil.rmtree(d)
    return {"ok": True}


LAST_PING = [0.0]


class ClientLog(BaseModel):
    level: str = "error"
    msg: str


@app.post("/api/clientlog")
def clientlog(x: ClientLog):
    """前端错误写到 data/client.log，方便排查打包版的界面问题。"""
    import datetime
    paths.ensure_dirs()
    with open(os.path.join(paths.DATA_DIR, "client.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} [{x.level}] {x.msg[:4000]}\n")
    return {"ok": True}


@app.get("/api/ping")
def ping():
    import time
    LAST_PING[0] = time.time()
    return {"ok": True}


def _sim_version():
    """sts2sim.__version__（直接读源文件，不导入模拟器）。"""
    try:
        with open(os.path.join(paths.SIM_ROOT, "sts2sim", "__init__.py"), encoding="utf-8") as f:
            m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
        return m.group(1) if m else "?"
    except OSError:
        return "?"


@app.get("/api/version")
def version():
    return {"name": "DeckBench", "version": _sim_version()}


@app.get("/api/health")
def health():
    return {"ok": True, "version": _sim_version(), "sim_root": paths.SIM_ROOT, "data_dir": paths.DATA_DIR, "frozen": paths.FROZEN}


if os.path.isdir(paths.WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(paths.WEB_DIST, "assets")), name="assets")

    @app.get("/{full:path}")
    def spa(full: str):
        f = os.path.join(paths.WEB_DIST, full)
        if full and os.path.isfile(f) and os.path.abspath(f).startswith(os.path.abspath(paths.WEB_DIST)):
            return FileResponse(f)
        return FileResponse(os.path.join(paths.WEB_DIST, "index.html"))
else:
    @app.get("/")
    def nodist():
        return JSONResponse({"error": "前端还没构建：cd gui/web && npm install && npm run build"})
