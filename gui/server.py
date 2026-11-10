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
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import i18n, paths
from .backend import get_backend
from .changelog import ChangelogError, load_changelog
from .jobs import JobManager
from .modeditor import router as modeditor_router

backend = get_backend()
jobs = JobManager(backend)
app = FastAPI(title="DeckBench GUI")
app.include_router(modeditor_router)
T = i18n.t

_VALIDATION_TYPES = {
    "string_type": "api.type.string",
    "string_unicode": "api.type.string",
    "int_type": "api.type.integer",
    "int_parsing": "api.type.integer",
    "int_from_float": "api.type.integer",
    "bool_type": "api.type.boolean",
    "bool_parsing": "api.type.boolean",
    "float_type": "api.type.number",
    "float_parsing": "api.type.number",
    "dict_type": "api.type.object",
    "model_attributes_type": "api.type.object",
    "list_type": "api.type.array",
    "tuple_type": "api.type.array",
}


def _validation_message(exc):
    """校验失败时给一句能照着改的话。不回显输入，也不带异常文本。"""
    errors = list(exc.errors()) if hasattr(exc, "errors") else []
    if not errors:
        return T("api.err.bad_json")
    err = errors[0]
    typ = str(err.get("type") or "")
    if typ.startswith("json"):
        return T("api.err.bad_json")
    parts = [str(part) for part in (err.get("loc") or ())]
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    field = ".".join(parts) or "request"
    if typ == "missing":
        return T("api.err.missing", field=field)
    type_key = _VALIDATION_TYPES.get(typ)
    if type_key:
        return T("api.err.bad_type", field=field, expected=T(type_key))
    return T("api.err.bad_field", field=field)


@app.exception_handler(RequestValidationError)
async def _invalid_request(_request, exc):
    return JSONResponse(status_code=400, content={"detail": _validation_message(exc)})


async def _read_capped(file, limit, message):
    """按块读上传，超过 limit 就 400。不把超限的正文留在内存里。"""
    size = getattr(file, "size", None)
    if isinstance(size, int) and not isinstance(size, bool) and size > limit:
        raise HTTPException(400, message)
    chunks = []
    total = 0
    while True:
        block = await file.read(min(65536, limit - total + 1))
        if not block:
            break
        total += len(block)
        if total > limit:
            raise HTTPException(400, message)
        chunks.append(block)
    return b"".join(chunks)


@app.middleware("http")
async def lang_middleware(request, call_next):
    """前端每个请求带 x-lang（当前界面语言），错误信息等按它翻译。"""
    tok = i18n.set_request_lang(request.headers.get("x-lang"))
    try:
        return await call_next(request)
    finally:
        i18n._REQ_LANG.reset(tok)


# 这些类型的正文是 UTF-8 文本。text/* 上 Starlette 已经加过 charset 的不再重复。
_TEXTUAL_MEDIA = {
    "application/json",
    "application/javascript",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
}


def with_utf8_charset(content_type: str) -> str:
    """给 JSON 和文本响应补上 charset=utf-8。

    Windows PowerShell 5.1 在 Content-Type 没有 charset 时按 ISO-8859-1 解码，
    中文会变成乱码。zip、图片、octet-stream 这类二进制不加。
    """
    if not content_type or not content_type.strip():
        return content_type
    parts = [part.strip() for part in content_type.split(";") if part.strip()]
    if not parts:
        return content_type
    media = parts[0].lower()
    for param in parts[1:]:
        name, sep, _value = param.partition("=")
        if sep and name.lower() == "charset":
            return content_type
    textual = media.startswith("text/") or media in _TEXTUAL_MEDIA or media.endswith(("+json", "+xml"))
    if not textual:
        return content_type
    return content_type.rstrip() + "; charset=utf-8"


@app.middleware("http")
async def utf8_charset_middleware(_request, call_next):
    response = await call_next(_request)
    current = response.headers.get("content-type")
    if not current:
        return response
    fixed = with_utf8_charset(current)
    if fixed != current:
        response.headers["content-type"] = fixed
    return response


class StartReq(BaseModel):
    kind: str
    params: dict
    title: str | None = None
    lang: str | None = None


class SettingsReq(BaseModel):
    lang: str


class TitleReq(BaseModel):
    title: str


def _need(rid):
    m = jobs.get(rid)
    if not m:
        raise HTTPException(404, T("err.runNotFound"))
    return m


def _deck_http(err):
    """牌组接口的失败说明。不回显用户输入，也不带堆栈。"""
    code = err.code
    params = err.params or {}
    if code == "missing":
        return T("api.err.missing", field=params.get("field") or "request")
    if code == "bad_type":
        expected = T("api.type." + str(params.get("expected") or "string"))
        return T("api.err.bad_type", field=params.get("field") or "request", expected=expected)
    if code == "too_big":
        return T("deck.err.too_big", n=params.get("n") or 0)
    key = "deck.err." + code
    if i18n.has(key):
        kw = {}
        if "n" in params:
            kw["n"] = params["n"]
        return T(key, **kw)
    return T("deck.err.cards")


@app.get("/api/cards")
def cards(
    q: str = "",
    character: str = "",
    card_type: str = Query("", alias="type"),
    cost: str = "",
    rarity: str = "",
    mod: str = "",
    offset: int = 0,
    limit: int = 40,
):
    """只读牌池。分页，可按角色、类型、费用、稀有度和中英文名字搜索。"""
    from sts2sim.deckpresets import DeckPresetError, list_cards
    try:
        return list_cards(q, character, card_type, cost, rarity, mod, offset, limit)
    except DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err


@app.get("/api/encounters")
def encounters(q: str = "", act: str = "", room: str = "", offset: int = 0, limit: int = 40):
    """只读遭遇名单。分页，可按幕和房间（normal / elite / boss）筛选。中文名和英文名都返回。"""
    from sts2sim.deckpresets import DeckPresetError, list_encounters
    try:
        return list_encounters(q, act, room, offset, limit)
    except DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err


@app.post("/api/decks")
async def save_deck(request: Request):
    """校验一套牌，写成用户预设。只写允许的预设目录，不覆盖出厂预设。"""
    from sts2sim import deckpresets as decks
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > decks.MAX_BYTES:
        raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
    chunks = []
    total = 0
    async for block in request.stream():
        if total + len(block) > decks.MAX_BYTES:
            raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
        chunks.append(block)
        total += len(block)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise HTTPException(400, T("deck.err.bad_json")) from None
    try:
        return decks.save_preset(payload)
    except decks.DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err


@app.post("/api/decks/head_to_head")
async def decks_head_to_head(request: Request):
    """两份用户预设打同一份遭遇、同一颗种子，打完返回两次测试的 id。

    不写 encounters / gauntlet / max_turns 时用第一份预设里存的。
    名单合计超过 400 场、预设对不上、类型不对，是 400，一句说明，没有堆栈。
    """
    from gui.headtohead import run_pair
    from sts2sim import deckpresets as decks

    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > decks.MAX_BYTES:
        raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
    chunks = []
    total = 0
    async for block in request.stream():
        if total + len(block) > decks.MAX_BYTES:
            raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
        chunks.append(block)
        total += len(block)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise HTTPException(400, T("deck.err.bad_json")) from None
    try:
        return await asyncio.to_thread(run_pair, payload)
    except decks.DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err


async def _deck_body(request):
    from sts2sim import deckpresets as decks
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > decks.MAX_BYTES:
        raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
    chunks = []
    total = 0
    async for block in request.stream():
        if total + len(block) > decks.MAX_BYTES:
            raise HTTPException(400, T("deck.err.too_big", n=decks.MAX_BYTES))
        chunks.append(block)
        total += len(block)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8")) if chunks else {}
    except (UnicodeError, json.JSONDecodeError):
        raise HTTPException(400, T("deck.err.bad_json")) from None
    return payload


@app.post("/api/decks/{deck_id}/card_impact")
async def start_card_impact(deck_id: str, request: Request):
    """对一份已保存的牌组做留一法。马上返回父任务 id 和每个变体的测试 id。

    全体变体合计最多 400 场。默认按比例缩小场数；``scale: false`` 时超限直接 400。
    进度和取消走原来的 ``/api/runs/<id>/progress`` 和 ``cancel``，id 用返回的父任务。
    """
    from gui.cardimpact import start as start_impact
    from sts2sim import deckpresets as decks
    payload = await _deck_body(request)
    if not isinstance(payload, dict):
        raise HTTPException(400, T("api.err.bad_type", field="body", expected=T("api.type.object")))
    try:
        return await asyncio.to_thread(start_impact, deck_id, payload)
    except decks.DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err


@app.get("/api/decks/{deck_id}/card_impact")
def deck_card_impact(deck_id: str):
    """这份牌组最近一次单卡贡献。还在跑时也返回，已经算完的行带上。"""
    from gui.cardimpact import result_for_deck
    from sts2sim import deckpresets as decks
    try:
        doc = result_for_deck(deck_id)
    except decks.DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err
    if doc is None:
        raise HTTPException(404, T("deck.impactNone"))
    return doc


@app.get("/api/runs/{rid}/card_impact")
def run_card_impact(rid: str):
    """某一次单卡贡献的结果。战斗测试 id 不是这个接口。"""
    from gui.cardimpact import result_for_run
    from sts2sim import deckpresets as decks
    try:
        doc = result_for_run(rid)
    except decks.DeckPresetError as err:
        raise HTTPException(400, _deck_http(err)) from err
    if doc is None:
        raise HTTPException(404, T("err.runNotFound"))
    return doc


@app.get("/api/catalog")
def catalog(refresh: bool = False, lang: str | None = None):
    try:
        return backend.catalog(refresh, lang=lang if lang in i18n.LANGS else None)
    except Exception as e:  # noqa
        raise HTTPException(500, str(e))


@app.get("/api/styles")
def styles(lang: str | None = None):
    """打法风格列表（id、名字、说明、能叠在哪些 AI 上）。"""
    from .backend import styles as _styles
    return _styles(lang if lang in i18n.LANGS else None)


@app.get("/api/runs")
def runs():
    return jobs.list()


def _compare_http(exc):
    if exc.code == "not_json":
        return T("err.compareBad", line=exc.params.get("line") or 1)
    if exc.code == "too_big":
        return T("imp.err.too_big")
    return T("err.compareNoData")


def _partial(meta):
    return bool(meta.get("partial") or meta.get("status") == "cancelled")


def _settled(meta):
    """打完，或者已经取消并留下部分结果。还在跑的不算。"""
    return meta.get("status") in ("done", "cancelled")


def _run_brief(meta):
    brief = {key: meta.get(key) for key in ("id", "kind", "title", "status", "created")}
    brief["partial"] = _partial(meta)
    return brief


@app.get("/api/runs/compare")
def runs_compare(request: Request):
    """两次已完成的战斗实验：格子差值和单卡使用/效率差值。不新开模拟。

    a、b 各是一次测试的 id。未知 id、同一个 id、重复或缺失的参数都是 400。
    胜率和超时用两比例 z 检验（并给出 Wilson 区间是否重叠）。
    平均回合、掉血、每回合输出和单卡使用次数在有逐场记录时用 Welch。
    """
    from sts2sim.runcompare import CompareError, compare_dirs

    query_a = request.query_params.getlist("a")
    query_b = request.query_params.getlist("b")
    if len(query_a) != 1:
        if not query_a:
            raise HTTPException(400, T("api.err.missing", field="a"))
        raise HTTPException(400, T("api.err.bad_type", field="a", expected=T("api.type.string")))
    if len(query_b) != 1:
        if not query_b:
            raise HTTPException(400, T("api.err.missing", field="b"))
        raise HTTPException(400, T("api.err.bad_type", field="b", expected=T("api.type.string")))
    a = query_a[0].strip()
    b = query_b[0].strip()
    if not a:
        raise HTTPException(400, T("api.err.missing", field="a"))
    if not b:
        raise HTTPException(400, T("api.err.missing", field="b"))
    if a == b:
        raise HTTPException(400, T("err.compareSame"))
    left = jobs.get(a)
    right = jobs.get(b)
    if not left or not right:
        raise HTTPException(400, T("err.compareUnknown"))
    if not _settled(left) or not _settled(right):
        raise HTTPException(400, T("err.abNotDone"))
    if left.get("kind") != right.get("kind"):
        raise HTTPException(400, T("err.abKind"))
    if left.get("kind") != "combat":
        raise HTTPException(400, T("err.compareCombat"))
    dir_a = jobs.run_dir(a)
    dir_b = jobs.run_dir(b)
    out_a = os.path.join(dir_a, "out") if dir_a else ""
    out_b = os.path.join(dir_b, "out") if dir_b else ""
    try:
        body = compare_dirs(out_a if os.path.isdir(out_a) else dir_a, out_b if os.path.isdir(out_b) else dir_b)
    except CompareError as exc:
        raise HTTPException(400, _compare_http(exc))
    body["ok"] = True
    body["read_only"] = True
    body["kind"] = "combat"
    body["partial"] = _partial(left) or _partial(right)
    body["a"] = _run_brief(left)
    body["b"] = _run_brief(right)
    return body


def _export_http(err):
    params = getattr(err, "params", None) or {}
    code = getattr(err, "code", "")
    if code == "bad_type":
        return T("api.err.bad_type", field=params.get("field") or "request", expected=T("api.type.string"))
    if code == "missing":
        return T("api.err.missing", field=params.get("field") or "request")
    if code == "bad_lang":
        return T("export.err.badLang")
    if code == "need_input":
        return T("export.err.need")
    if code == "no_result":
        return T("export.err.noResult")
    if code == "not_calibration":
        return T("gap.err.not_calibration")
    if code == "refuse_write":
        return T("exp.err.refuse_write", path=params.get("path") or "")
    return T("export.err.need")


def _export_lang(request):
    """?lang= 盖过请求头。重复的 lang、认不出的标记是 400，不回显原文。"""
    from sts2sim.htmlreport import ExportError, parse_lang
    values = request.query_params.getlist("lang")
    if len(values) > 1:
        raise HTTPException(400, T("api.err.bad_type", field="lang", expected=T("api.type.string")))
    try:
        chosen = parse_lang(values[0] if values else "")
    except ExportError as exc:
        raise HTTPException(400, _export_http(exc))
    if chosen:
        i18n.set_request_lang(chosen)
        return chosen
    return i18n.current()


def _optional_calibration(request):
    """可选的校准或分诊 JSON。路径规则和只读分析相同。"""
    from sts2sim.analysis import AnalysisError
    from sts2sim.htmlreport import ExportError, load_side_report
    values = request.query_params.getlist("calibration")
    if not values:
        return None, None
    if len(values) != 1:
        raise HTTPException(400, T("api.err.bad_type", field="calibration", expected=T("api.type.string")))
    text = values[0].strip()
    if not text:
        raise HTTPException(400, T("api.err.missing", field="calibration"))
    try:
        return load_side_report(text)
    except ExportError as exc:
        raise HTTPException(400, _export_http(exc))
    except AnalysisError as exc:
        raise HTTPException(400, _gap_analysis_http(exc))


def _html_file(document, filename):
    from sts2sim.htmlreport import content_disposition
    return HTMLResponse(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"content-disposition": content_disposition(filename)},
    )


def _bundle_status(err):
    """结果包的失败说明。不回显路径，也不带堆栈。"""
    from sts2sim.bundle import message
    code = getattr(err, "code", "")
    status = 400
    if code == "not_found" or code == "no_result":
        status = 404
    elif code == "not_done":
        status = 409
    return HTTPException(status, message(err))


def _zip_file(data, filename):
    from sts2sim.bundle import content_disposition
    return Response(
        content=data,
        media_type="application/zip",
        headers={"content-disposition": content_disposition(filename)},
    )


@app.get("/api/runs/compare/export.html")
def runs_compare_export(request: Request):
    """两次已完成的战斗实验，写成一份离线 HTML。不新开模拟。

    可选 calibration 是一份校准 JSON 或已经分诊好的 JSON，写进同一份文件。
    """
    from sts2sim.htmlreport import export_filename, render_html
    lang = _export_lang(request)
    body = runs_compare(request)
    calibration, gap = _optional_calibration(request)
    document = render_html(lang=lang, comparison=body, calibration=calibration, gap=gap)
    left = (body.get("a") or {}).get("id") or "a"
    right = (body.get("b") or {}).get("id") or "b"
    return _html_file(document, export_filename(a=str(left), b=str(right)))


@app.get("/api/runs/compare/bundle")
def runs_compare_bundle(request: Request):
    """两次已完成的战斗实验，打成一个 .deckbench.zip。不新开模拟。

    两边都是同一份对打（shared_plan）时，清单的 kind 是 head_to_head。
    """
    from sts2sim.bundle import BundleError, export_compare_bytes
    _export_lang(request)
    query_a = request.query_params.getlist("a")
    query_b = request.query_params.getlist("b")
    if len(query_a) != 1 or len(query_b) != 1:
        field = "a" if len(query_a) != 1 else "b"
        if not (query_a if field == "a" else query_b):
            raise HTTPException(400, T("api.err.missing", field=field))
        raise HTTPException(400, T("api.err.bad_type", field=field, expected=T("api.type.string")))
    try:
        data, filename = export_compare_bytes(query_a[0], query_b[0], lang=i18n.current())
    except BundleError as err:
        raise _bundle_status(err) from None
    return _zip_file(data, filename)


@app.post("/api/runs")
def start(req: StartReq):
    if req.kind not in ("batch", "combat"):
        raise HTTPException(400, T("err.unknownKind"))
    p = req.params
    if req.kind == "combat" and not p.get("preset") and not p.get("decks"):
        raise HTTPException(400, T("err.needDeck"))
    try:
        return jobs.start(req.kind, p, req.title, lang=req.lang or i18n.current())
    except ValueError as e:      # 例如 mod 名字不对 / 找不到
        raise HTTPException(400, str(e))


@app.get("/api/runs/{rid}")
def run(rid: str):
    return _need(rid)


@app.get("/api/runs/{rid}/progress")
def run_progress(rid: str):
    """这一次测试打到第几场、当前遭遇、已经用了多久。轮询即可。不新开模拟。"""
    _need(rid)
    view = jobs.progress(rid)
    if not view:
        raise HTTPException(404, T("err.runNotFound"))
    return view


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
    if m.get("kind") == "card_impact":
        from gui.cardimpact import start as start_impact
        from sts2sim.deckpresets import DeckPresetError
        params = m.get("params") if isinstance(m.get("params"), dict) else {}
        payload = params.get("request") if isinstance(params.get("request"), dict) else {}
        try:
            return start_impact(params.get("deck") or "", payload)
        except DeckPresetError as err:
            raise HTTPException(400, _deck_http(err)) from err
    t = m.get("title") or ""
    return jobs.start(m["kind"], m["params"], (t + T("err.rerunSuffix")) if t else None, lang=i18n.current())


@app.get("/api/runs/{rid}/summary")
def summary(rid: str):
    m = _need(rid)
    if not _settled(m):
        raise HTTPException(409, T("err.notDone"))
    return {"meta": m, "summary": backend.summarize(m["kind"], jobs.run_dir(rid))}


@app.get("/api/runs/{rid}/export.html")
def run_export(rid: str, request: Request):
    """一次已完成的测试，写成一份离线 HTML。不新开模拟。

    可选 calibration 把校准或缺口分诊写进同一份文件。
    """
    from sts2sim.htmlreport import export_filename, render_html
    lang = _export_lang(request)
    meta = _need(rid)
    if not _settled(meta):
        raise HTTPException(409, T("err.notDone"))
    summary = backend.summarize(meta.get("kind"), jobs.run_dir(rid))
    if not summary:
        raise HTTPException(404, T("export.err.noResult"))
    calibration, gap = _optional_calibration(request)
    document = render_html(
        lang=lang, run={"meta": meta, "summary": summary}, calibration=calibration, gap=gap,
    )
    return _html_file(document, export_filename(run_id=rid))


@app.get("/api/runs/{rid}/bundle")
def run_bundle(rid: str, request: Request):
    """一次已完成的测试，打成一个 .deckbench.zip。单卡贡献把子测试一并装进去。

    不新开模拟，不执行包里的文件。
    """
    from sts2sim.bundle import BundleError, export_run_bytes
    _export_lang(request)
    try:
        data, filename = export_run_bytes(rid, lang=i18n.current())
    except BundleError as err:
        raise _bundle_status(err) from None
    return _zip_file(data, filename)


@app.post("/api/bundles/import")
async def import_bundle(file: UploadFile = File(...)):
    """上传一个 .deckbench.zip，校验清单和哈希后写成测试目录。

    不执行包里的任何文件。schema 对不上、哈希不对、路径越界或超限都是 400。
    编号冲突时换一个新编号。导进来的测试标记为 imported。
    """
    from sts2sim.bundle import MAX_UPLOAD, BundleError, import_zip_bytes
    data = await _read_capped(file, MAX_UPLOAD, T("bundle.err.tooBig"))
    try:
        return import_zip_bytes(data, filename=file.filename or "")
    except BundleError as err:
        raise _bundle_status(err) from None


@app.post("/api/demo/load")
def load_demo_data():
    """把内置示例结果包导入。和上传导入同一条校验路径，不执行包里的文件。"""
    from gui.demo import DemoError, load_builtin
    from sts2sim.bundle import BundleError

    try:
        return load_builtin()
    except DemoError:
        raise HTTPException(404, T("demo.missing")) from None
    except BundleError as err:
        raise _bundle_status(err) from None


@app.get("/api/runs/{rid}/report")
def report(rid: str):
    _need(rid)
    d = jobs.run_dir(rid)
    f = os.path.join(d, "out", "report.md") if d else ""
    if not d or not os.path.exists(f):
        raise HTTPException(404, T("err.noReport"))
    return {"markdown": open(f, encoding="utf-8").read()}


FILES = {"runs.jsonl", "run.log", "experiment.yaml", "report.md", "cells.csv", "cards.csv", "encounters.csv", "raw.jsonl"}


@app.get("/api/runs/{rid}/files/{name}")
def runfile(rid: str, name: str):
    _need(rid)
    if name not in FILES:
        raise HTTPException(404)
    d = jobs.run_dir(rid)
    if not d:
        raise HTTPException(404)
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
        raise HTTPException(400, T("err.abKind"))
    if ma.get("status") != "done" or mb.get("status") != "done":
        raise HTTPException(400, T("err.abNotDone"))
    return {"kind": ma["kind"], "a": ma, "b": mb, "result": backend.ab(ma["kind"], jobs.run_dir(a), jobs.run_dir(b))}


# ---------------------------------------------------------------- mod 上传
NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")


@app.post("/api/mods/upload")
async def upload_mod(file: UploadFile = File(...)):
    data = await _read_capped(file, 50 * 1024 * 1024, T("err.tooBig"))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, T("err.badZip"))
    names = [n for n in zf.namelist() if not n.endswith("/")]
    for n in names:
        if n.startswith("/") or ".." in n.replace("\\", "/").split("/"):
            raise HTTPException(400, T("err.unsafePath", path=n))
    ymls = sorted((n for n in names if n.replace("\\", "/").split("/")[-1] == "mod.yaml"), key=lambda n: n.count("/"))
    if not ymls:
        raise HTTPException(400, T("err.noModYaml"))
    prefix = ymls[0][: -len("mod.yaml")]
    try:
        meta = yaml.safe_load(zf.read(ymls[0]).decode("utf-8")) or {}
    except Exception as e:  # noqa
        raise HTTPException(400, T("err.modYamlParse", err=e))
    name = str(meta.get("name") or "").strip()
    if not NAME_RE.match(name):
        raise HTTPException(400, T("err.modName"))
    if os.path.isdir(os.path.join(paths.SIM_ROOT, "mods", name)):
        raise HTTPException(400, T("err.modNameTaken", name=name))
    problems = []
    for key in ("cards", "decks", "potions"):
        for f in meta.get(key, []) or []:
            if prefix + f not in names:
                problems.append(T("err.listedMissing", key=key, file=f))
            else:
                try:
                    yaml.safe_load(zf.read(prefix + f).decode("utf-8"))
                except Exception as e:  # noqa
                    problems.append(T("err.badYaml", file=f, err=e))
    if meta.get("hooks") and prefix + meta["hooks"] not in names:
        problems.append(T("err.hooksMissing", file=meta["hooks"]))
    if not meta.get("decks"):
        problems.append(T("err.noDecks"))
    if problems:
        raise HTTPException(400, T("sep.problems").join(problems))
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
            raise HTTPException(400, T("err.modLoadFailed") + "\n" + res.get("error", ""))
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
        raise HTTPException(404, T("err.onlyUserMods"))
    shutil.rmtree(d)
    return {"ok": True}


class ImportPathReq(BaseModel):
    model_config = ConfigDict(strict=True)
    path: str


class ImportBatchReq(BaseModel):
    """path 必填。lines 只跟命令行对齐，不改变 HTTP 的正文形状。"""
    model_config = ConfigDict(strict=True)
    path: str | None = None
    lines: bool = False


class PreviewReq(BaseModel):
    seed: str = ""
    char: str = "Ironclad"
    asc: int = 0
    neow: str = "first"


class ExplainPathReq(BaseModel):
    model_config = ConfigDict(strict=True)
    path: str


class ExplainFightReq(BaseModel):
    model_config = ConfigDict(strict=True)
    path: str
    seed: str = ""
    fight: int = 0
    offset: int = 0
    limit: int = 20


class CalibrateReq(BaseModel):
    model_config = ConfigDict(strict=True)
    real: str = ""
    sim: str = ""


def _import_detail(err):
    """解析器附带的一行原因。不进成功响应，只接在已经翻译的错误后面。"""
    raw = (getattr(err, "params", None) or {}).get("detail")
    if not raw:
        return ""
    text = " ".join(str(raw).split()).replace("{", "(").replace("}", ")")
    if len(text) > 160:
        text = text[:160] + "..."
    return text


def _import_http(err):
    p = getattr(err, "params", None) or {}
    if err.code == "not_found":
        msg = T("imp.err.not_found", path=p.get("path", ""))
    elif err.code == "not_json":
        msg = T("imp.err.not_json")
    elif err.code == "not_object":
        msg = T("imp.err.not_object")
    elif err.code == "unknown_shape":
        msg = T("imp.err.unknown_shape")
    elif err.code == "not_a_run":
        msg = T("imp.err.not_a_run")
    elif err.code == "too_big":
        msg = T("imp.err.too_big")
    elif err.code == "path_not_allowed":
        msg = T("imp.err.path_not_allowed", path=p.get("path", ""))
    elif err.code == "decode":
        msg = T("imp.err.decode")
    elif err.code == "dir_empty":
        msg = T("imp.err.dir_empty", path=p.get("path", ""))
    else:
        msg = T("imp.err.unknown_shape")
    extra = _import_detail(err)
    if extra and extra not in msg:
        return T("imp.err.withDetail", text=msg, detail=extra)
    return msg


def _preview_http(err):
    p = err.params
    if err.code == "need_seed":
        return T("prev.err.need_seed")
    if err.code == "bad_asc":
        return T("prev.err.bad_asc")
    if err.code == "bad_char":
        return T("prev.err.bad_char", char=p.get("char", ""))
    if err.code == "bad_neow":
        return T("prev.err.bad_neow")
    if err.code == "no_engine":
        return T("prev.err.no_engine", err=p.get("err", ""))
    if err.code == "cache_in_repo":
        return T("prev.err.cache_in_repo", path=p.get("path", ""))
    return T("prev.err.failed", err=err.code)


_GAP_KEYS = {"reports", "report", "paths", "catalog", "min_compared"}


def _gap_mod():
    """tools 不是包。和测试一样按文件加载，避免改模拟器的导入路径。"""
    name = "deckbench_gap_triage_api"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    import importlib.util
    path = os.path.join(paths.SIM_ROOT, "tools", "gap_triage.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gap_type_expected(field):
    if field in ("reports", "report", "request"):
        return "api.type.object_or_array"
    if field == "paths":
        return "api.type.array"
    if field.startswith("paths."):
        return "api.type.string"
    if field == "catalog":
        return "api.type.string"
    if field == "min_compared":
        return "api.type.integer"
    if field.startswith("reports."):
        return "api.type.object"
    return "api.type.object"


def _gap_http(err):
    p = getattr(err, "params", None) or {}
    code = err.code
    if code == "bad_type":
        field = p.get("field") or "request"
        return T("api.err.bad_type", field=field, expected=T(_gap_type_expected(field)))
    if code == "need_input":
        return T("gap.err.need_input")
    if code == "not_calibration":
        return T("gap.err.not_calibration")
    if code == "not_json":
        return T("gap.err.not_json", path=p.get("path", ""))
    if code == "too_big":
        return T("imp.err.too_big")
    if code == "not_found":
        return T("gap.err.not_found", path=p.get("path", ""))
    if code == "bad_catalog":
        return T("gap.err.bad_catalog", path=p.get("path", ""))
    return T("gap.err.failed", err=code)


def _gap_analysis_http(err):
    p = getattr(err, "params", None) or {}
    code = err.code
    if code == "path_not_allowed":
        return T("exp.err.path_not_allowed", path=p.get("path", ""))
    if code == "refuse_write":
        return T("exp.err.refuse_write", path=p.get("path", ""))
    if code == "not_found":
        return T("gap.err.not_found", path=p.get("path", ""))
    if code == "need_path":
        return T("gap.err.need_input")
    if code == "too_big":
        return T("imp.err.too_big")
    if code == "not_json":
        return T("gap.err.not_json", path=p.get("path", ""))
    return T("gap.err.failed", err=code)


async def _body_capped(request, limit):
    """JSON 正文超过 limit 就 400。超限的那一块不留下来。"""
    chunks = []
    total = 0
    async for block in request.stream():
        if total + len(block) > limit:
            raise HTTPException(400, T("imp.err.too_big"))
        chunks.append(block)
        total += len(block)
    return b"".join(chunks)


def _calibrate_http(err):
    p = getattr(err, "params", None) or {}
    code = err.code
    if code == "need_real":
        return T("cal.err.need_real")
    if code == "need_sim":
        return T("cal.err.need_sim")
    if code == "one_run":
        return T("cal.err.one_run")
    if code == "multiplayer":
        return T("cal.err.multiplayer")
    if code == "no_seed":
        return T("cal.err.no_seed")
    if code == "no_character":
        return T("cal.err.no_character")
    if code == "no_ascension":
        return T("cal.err.no_ascension")
    if code == "not_found":
        return T("cal.err.not_found", path=p.get("path", ""))
    return T("exp.err.failed", err=code)


def _explain_http(err):
    p = getattr(err, "params", None) or {}
    path = p.get("path", "")
    code = err.code
    if code == "need_path":
        return T("exp.err.need_path")
    if code == "path_not_allowed":
        return T("exp.err.path_not_allowed", path=path)
    if code == "not_found":
        return T("exp.err.not_found", path=path)
    if code == "refuse_write":
        return T("exp.err.refuse_write", path=path)
    if code == "not_explain":
        return T("exp.err.not_explain", path=path)
    if code == "ambiguous_explain":
        return T("exp.err.ambiguous_explain", n=p.get("n", 0), path=path)
    if code == "not_json":
        return T("exp.err.not_json", line=p.get("line", "?"))
    if code == "too_big":
        return T("imp.err.too_big")
    if code == "unreadable":
        return T("exp.err.unreadable", path=path)
    if code == "bad_fight":
        return T("exp.err.bad_fight")
    if code == "bad_offset":
        return T("exp.err.bad_offset")
    if code == "bad_limit":
        return T("exp.err.bad_limit")
    if code == "bad_seed":
        return T("exp.err.bad_seed")
    if code == "fight_out_of_range":
        return T("exp.err.fight_out_of_range", fight=p.get("fight", 0), fight_count=p.get("fight_count", 0))
    return T("exp.err.failed", err=code)


@app.post("/api/import")
def import_save(req: ImportPathReq):
    """只读解析玩家指出的 .run / current_run.save / 存档目录。"""
    from sts2sim.saveimport import SaveImportError, load_path
    try:
        return load_path(req.path)
    except SaveImportError as e:
        raise HTTPException(400, _import_http(e))


@app.post("/api/import/batch")
def import_batch(req: ImportBatchReq):
    """只读目录批量摘要，和 import_run.py --batch-summary 同一份行。不写存档。

    成功时返回一个 JSON 数组（application/json）。元素来自
    sts2sim.saveimport.batch_summary，键和命令行相同。lines 为 true 时仍是
    这个数组：每个对象就是命令行 --lines 的一行，不改成 NDJSON。
    没给路径、空目录，以及其他 SaveImportError，是 HTTP 400。
    """
    from sts2sim.saveimport import SaveImportError, batch_summary, load_path
    # req.lines 不改变正文：命令行 --lines 是 NDJSON，这里两种取值都返回下面的数组。
    path = req.path if isinstance(req.path, str) else ""
    if not path.strip():
        raise HTTPException(400, _import_http(SaveImportError("not_found", path=path)))
    try:
        return batch_summary(load_path(path))
    except SaveImportError as e:
        raise HTTPException(400, _import_http(e))


@app.post("/api/calibrate")
def calibrate_report(req: CalibrateReq):
    """真对局对照同一条选牌路径上的模拟掉血。只读，不新开模拟。

    real 是一份 .run / .save（和 /api/import 同一套解析）。sim 是 runs.jsonl
    或含它的目录，路径规则和说明日志相同。对不上的层在 fights 里是 unmatched。
    """
    from sts2sim.analysis import AnalysisError
    from sts2sim.calibrate import CalibrateError, calibrate_paths
    from sts2sim.saveimport import SaveImportError
    try:
        return calibrate_paths(req.real, req.sim, restricted=True)
    except SaveImportError as e:
        raise HTTPException(400, _import_http(e))
    except AnalysisError as e:
        raise HTTPException(400, _explain_http(e))
    except CalibrateError as e:
        raise HTTPException(400, _calibrate_http(e))


@app.get("/api/calibrate/reals")
def calibrate_reals():
    """常见位置里已导入的 history/*.run 和 current_run.save。只列路径，不读内容。"""
    from sts2sim.calibrate import list_imported_runs
    return list_imported_runs()


@app.get("/api/calibrate/sims")
def calibrate_sims():
    """允许目录里的 runs.jsonl。只列路径，不读内容，不写文件。"""
    from sts2sim.calibrate import list_sim_files
    return list_sim_files()


@app.post("/api/calibrate/upload")
async def calibrate_upload(real: str = Form(""), file: UploadFile = File(...)):
    """浏览器选中的 runs.jsonl 只在内存里和一份真对局对照。不写盘，不新开模拟。

    real 和 /api/calibrate 一样，是一份 .run / .save。file 是 jsonl 正文，
    不要求落在允许目录里。返回的 sim_path 只是上传时的文件名。
    """
    from sts2sim.analysis import AnalysisError
    from sts2sim.calibrate import CalibrateError, calibrate_rows, parse_sim_bytes
    from sts2sim.saveimport import MAX_BYTES, SaveImportError
    data = await _read_capped(file, MAX_BYTES, T("imp.err.too_big"))
    try:
        body = calibrate_rows(real, parse_sim_bytes(data))
    except SaveImportError as e:
        raise HTTPException(400, _import_http(e))
    except AnalysisError as e:
        raise HTTPException(400, _explain_http(e))
    except CalibrateError as e:
        raise HTTPException(400, _calibrate_http(e))
    name = os.path.basename(str(file.filename or "upload.jsonl").replace("\\", "/"))
    if not name or name in (".", ".."):
        name = "upload.jsonl"
    body["sim_path"] = name
    return body


@app.post("/api/gap_triage")
async def gap_triage_report(request: Request):
    """把一份或多份校准结果按遭遇和敌人能力排成缺口。只读，不新开模拟。

    正文可以是 POST /api/calibrate 返回的那一份 JSON、这样的 JSON 组成的数组，
    或 ``{"reports","paths","catalog","min_compared"}``。paths 和 catalog 的路径
    规则与只读分析相同。类型不对、缺了输入、坏 JSON、超限、目录外的路径都是 400。
    """
    from sts2sim.analysis import AnalysisError
    from sts2sim.saveimport import MAX_BYTES
    mod = _gap_mod()
    raw = await _body_capped(request, MAX_BYTES)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, T("api.err.bad_json"))
    if not text.strip():
        raise HTTPException(400, T("api.err.bad_json"))
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        raise HTTPException(400, T("api.err.bad_json"))
    try:
        if isinstance(payload, list):
            body = mod.run_triage(reports=payload, restricted=True)
        elif isinstance(payload, dict) and any(key in payload for key in _GAP_KEYS):
            if "reports" in payload:
                reports = payload.get("reports")
            elif "report" in payload:
                reports = payload.get("report")
            else:
                reports = None
            body = mod.run_triage(
                reports=reports,
                paths=payload.get("paths") if "paths" in payload else None,
                catalog=payload.get("catalog") if "catalog" in payload else "",
                min_compared=payload.get("min_compared") if "min_compared" in payload else 1,
                restricted=True,
            )
        elif isinstance(payload, dict) and not payload:
            raise mod.TriageError("need_input")
        elif isinstance(payload, dict) and mod._is_report(payload):
            body = mod.run_triage(reports=[payload], restricted=True)
        elif isinstance(payload, dict):
            raise mod.TriageError("not_calibration")
        else:
            raise mod.TriageError("bad_type", field="request")
    except mod.TriageError as exc:
        raise HTTPException(400, _gap_http(exc))
    except AnalysisError as exc:
        raise HTTPException(400, _gap_analysis_http(exc))
    return body


@app.post("/api/import/upload")
async def import_upload(file: UploadFile = File(...)):
    """浏览器选中的存档只在内存里解析，不写回游戏目录。"""
    from sts2sim.saveimport import MAX_BYTES, SaveImportError, parse_bytes
    data = await _read_capped(file, MAX_BYTES, T("imp.err.too_big"))
    try:
        run = parse_bytes(data, filename=file.filename or "upload.run")
    except SaveImportError as e:
        raise HTTPException(400, _import_http(e))
    return {"v": 1, "kind": "run", "run": run}


@app.get("/api/saves/discover")
def saves_discover():
    """常见位置里的存档目录。只列路径，不读内容。"""
    from sts2sim.saveimport import discover
    return {"roots": discover()}


@app.get("/api/explain/logs")
def explain_logs():
    """允许目录里的 --explain 日志。只列路径，不读内容，不写文件。"""
    from sts2sim.analysis import explain_logs as _logs
    return _logs()


@app.post("/api/explain")
def explain_open(req: ExplainPathReq):
    """一份日志里的种子和战斗。只读，路径规则和 MCP explain_fight 相同。"""
    from sts2sim.analysis import AnalysisError, explain_catalog
    try:
        return explain_catalog(req.path)
    except AnalysisError as e:
        raise HTTPException(400, _explain_http(e))


@app.post("/api/explain/fight")
def explain_fight_page(req: ExplainFightReq):
    """一场战斗的一页决策。阅读和分页走 analysis.explain_fight，这里只补分差。不写文件。"""
    from sts2sim.analysis import AnalysisError, explain_page
    try:
        return explain_page(req.path, req.fight, req.seed, req.offset, req.limit)
    except AnalysisError as e:
        raise HTTPException(400, _explain_http(e))


@app.post("/api/seed-preview")
async def seed_preview(req: PreviewReq):
    """地图、遭遇队列、开局奖励。不打战斗。没有本机游戏逻辑时返回说明。"""
    from sts2sim.engine.seedpreview import PreviewError, preview
    try:
        return await asyncio.to_thread(preview, req.seed, req.char, req.asc, req.neow)
    except PreviewError as e:
        raise HTTPException(400, _preview_http(e))
    except Exception as e:  # noqa
        raise HTTPException(400, T("prev.err.failed", err=f"{type(e).__name__}: {e}"))


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
    """sts2sim.__version__（读源文件，不导入模拟器，也不访问网络）。"""
    try:
        from sts2sim.version import read_project_version
        return read_project_version(paths.SIM_ROOT)
    except (OSError, ValueError):
        return "?"


@app.get("/api/settings")
def get_settings():
    """界面语言：lang = 保存的选择（没选过为 null）；os_lang = 系统语言（第一次启动用它定默认语言）。"""
    return {"lang": i18n.saved_lang(), "os_lang": i18n.os_lang(), "langs": list(i18n.LANGS)}


@app.post("/api/settings")
def post_settings(req: SettingsReq):
    if req.lang not in i18n.LANGS:
        raise HTTPException(400, T("err.badLang"))
    paths.ensure_dirs()
    i18n.save_settings(lang=req.lang)
    return {"ok": True, "lang": req.lang}


@app.get("/api/version")
def version():
    return {"name": "DeckBench", "version": _sim_version()}


@app.get("/api/changelog")
def changelog():
    """最新一节更新日志，解析成文本结构。不返回 HTML，也不读网络。"""
    try:
        return load_changelog(_sim_version())
    except ChangelogError:
        raise HTTPException(404, T("err.noChangelog")) from None


@app.post("/api/updates/check")
def updates_check():
    """手动检查 GitHub Releases。启动时不调用，界面只有点击按钮才打到这里。"""
    from sts2sim.version import check_latest
    return check_latest(current=_sim_version())


@app.get("/api/health")
def health():
    return {"ok": True, "version": _sim_version(), "sim_root": paths.SIM_ROOT, "data_dir": paths.DATA_DIR, "frozen": paths.FROZEN}


if os.path.isdir(paths.WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(paths.WEB_DIST, "assets")), name="assets")

    @app.get("/{full:path}")
    def spa(full: str):
        # 未知的 /api 保持 404。否则前端构建之后，折叠过的路径会拿到 index.html。
        if full == "api" or full.startswith("api/"):
            raise HTTPException(404, "Not Found")
        f = os.path.join(paths.WEB_DIST, full)
        if full and os.path.isfile(f) and os.path.abspath(f).startswith(os.path.abspath(paths.WEB_DIST)):
            return FileResponse(f)
        return FileResponse(os.path.join(paths.WEB_DIST, "index.html"))
else:
    @app.get("/")
    def nodist():
        return JSONResponse({"error": "web UI not built / 前端还没构建: cd gui/web && npm install && npm run build"})
