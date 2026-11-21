"""卡牌编辑器的 HTTP 接口。读写用户 mod 目录，不执行上传的内容。"""
from __future__ import annotations

import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from sts2sim.customcards import (
    LIBRARY_FILE,
    CardLibraryError,
    blank,
    deck_rows_for,
    library_from_import,
    prepare_save,
    preset_id_for,
    public_schema,
    read_library_dir,
    validate_library,
)
from sts2sim.deckpresets import DeckPresetError, save_preset

from . import i18n, paths

_UPLOAD = File(...)
router = APIRouter(prefix="/api/custom-cards")
T = i18n.t
_MAX_UPLOAD = 1_000_000
_START = None


def set_starter(fn):
    """server.py 在 JobManager 建好之后把 start 传进来，避免环形导入。"""
    global _START
    _START = fn


def _http(exc):
    key = {
        "name": "cc.err.name",
        "py": "cc.err.py",
        "missing": "cc.err.missing",
        "read": "cc.err.read",
        "invalid": "cc.err.invalid",
        "import": "cc.err.import",
        "big": "cc.err.big",
        "deck": "cc.err.deck",
        "shipped": "cc.err.shipped",
        "refused": "cc.err.refused",
    }.get(exc.code, "cc.err.invalid")
    return T(key)


def _mods_root():
    """和牌组预设一样，请求时再读 STS2SIM_GUI_DATA。"""
    env = os.environ.get("STS2SIM_GUI_DATA")
    if isinstance(env, str) and env.strip() and "\x00" not in env:
        return os.path.join(env, "mods")
    return paths.USER_MODS_DIR


def _folder(name):
    if not isinstance(name, str):
        raise HTTPException(400, T("cc.err.name"))
    root = os.path.realpath(_mods_root())
    folder = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(folder) != root:
        raise HTTPException(400, T("cc.err.name"))
    shipped = os.path.join(paths.SIM_ROOT, "mods", name)
    if os.path.isdir(shipped):
        raise HTTPException(400, T("cc.err.shipped"))
    return folder


def _write(folder, files):
    os.makedirs(_mods_root(), exist_ok=True)
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(folder):
        if name.endswith(".py"):
            raise HTTPException(400, T("cc.err.py"))
    allowed = {"mod.yaml", "cards.yaml", "powers.yaml", "relics.yaml", "potions.yaml", LIBRARY_FILE}
    for name, text in files.items():
        if name not in allowed or not isinstance(text, str):
            raise HTTPException(400, T("cc.err.refused"))
        dest = os.path.join(folder, name)
        if os.path.islink(dest):
            raise HTTPException(400, T("cc.err.refused"))
        tmp = dest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, dest)


class LibraryBody(BaseModel):
    library: dict
    focus: str | None = None


@router.get("/schema")
def schema():
    return public_schema()


@router.get("/new")
def new_library():
    return blank()


@router.get("/libraries")
def libraries():
    root = _mods_root()
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, LIBRARY_FILE)):
            out.append({"name": name})
    return out


@router.get("/library/{name}")
def get_library(name: str):
    folder = _folder(name)
    if not os.path.isdir(folder):
        raise HTTPException(404, T("cc.err.missing"))
    try:
        return read_library_dir(folder)
    except CardLibraryError as exc:
        raise HTTPException(400, _http(exc)) from None


@router.post("/validate")
def validate(body: LibraryBody):
    checked = validate_library(body.library)
    return {"ok": checked["ok"], "problems": checked["problems"], "warnings": checked["warnings"],
            "library": checked["library"]}


@router.post("/save")
def save(body: LibraryBody):
    try:
        library, files, warnings = prepare_save(body.library)
    except CardLibraryError as exc:
        checked = validate_library(body.library)
        if checked["problems"]:
            return {"ok": False, "problems": checked["problems"], "warnings": checked["warnings"]}
        raise HTTPException(400, _http(exc)) from None
    folder = _folder(library["name"])
    _write(folder, files)
    return {"ok": True, "name": library["name"], "library": library, "problems": [], "warnings": warnings}


@router.post("/import")
async def import_library(file: UploadFile = _UPLOAD):
    data = await file.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(400, T("cc.err.big"))
    try:
        checked = library_from_import(file.filename or "", data)
    except CardLibraryError as exc:
        raise HTTPException(400, _http(exc)) from None
    checked["saved"] = False
    return checked


@router.post("/test")
def test_library(body: LibraryBody):
    """保存卡牌库，写成用户预设，并开一场已有的战斗测试。"""
    try:
        library, files, warnings = prepare_save(body.library)
        rows = deck_rows_for(library, body.focus)
        preset = preset_id_for(library["name"])
    except CardLibraryError as exc:
        checked = validate_library(body.library)
        if checked["problems"]:
            return {"ok": False, "problems": checked["problems"], "warnings": checked["warnings"]}
        raise HTTPException(400, _http(exc)) from None
    folder = _folder(library["name"])
    _write(folder, files)
    try:
        saved = save_preset({
            "id": preset,
            "name": library["title"],
            "mod": library["name"],
            "character": library["character"]["id"],
            "cards": rows,
            "encounters": [{"id": "DUMMY", "fights": library["fights"]}],
            "max_turns": library["max_turns"],
            "seed": library["seed"],
            "agent": "heuristic",
        })
    except DeckPresetError as exc:
        raise HTTPException(400, T("cc.err.deck")) from exc
    if _START is None:
        raise HTTPException(500, T("cc.err.invalid"))
    run = _START(
        "combat",
        {
            "preset": saved["id"],
            "fights": library["fights"],
            "seed": library["seed"],
            "agent": "heuristic",
            "workers": 1,
            "max_turns": library["max_turns"],
            "card_test_encounter": library["encounter"],
            "title": library["title"],
        },
        library["title"],
        lang=i18n.current(),
    )
    return {
        "ok": True,
        "name": library["name"],
        "preset": saved["id"],
        "run_id": run["id"],
        "warnings": warnings,
        "deck": rows,
        "encounter": library["encounter"],
        "library": library,
        "problems": [],
    }
