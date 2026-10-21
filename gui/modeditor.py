"""模组编辑器（界面里填表做 YAML 数据 mod）的后端接口。

mod 的内容以「规范化后的字典」在前后端之间传（sts2sim/modfmt/schema.py 的 load_mod_files 结果），
保存时用 dump_mod_dir 写回 YAML。自带的 mods/ 只读：打开后只能「另存为」到你自己的 mod 文件夹（界面数据目录/mods）。
"""
import asyncio
import io
import json
import os
import re
import shutil
import zipfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import i18n, paths
from .backend import mod_check, mod_dir

router = APIRouter(prefix="/api/modeditor")
T = i18n.t
NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,40}$")


def S():
    from sts2sim.modfmt import schema
    return schema


def _spec(table):
    out = {}
    for name, params in table.items():
        out[name] = [{"name": k, "kind": v[0], "required": bool(v[1]), "default": v[2] if len(v) > 2 else None}
                     for k, v in params.items()]
    return out


@router.get("/schema")
def schema():
    s = S()
    return {"ops": _spec(s.OPS), "templates": _spec(s.TEMPLATES), "triggers": _spec(s.TRIGGERS),
            "trigger_templates": {k: {"on": on, "params": _spec({"x": p})["x"]} for k, (on, p) in s.TRIGGER_TEMPLATES.items()},
            "target_specs": list(s.TARGET_SPECS), "once": list(s.ONCE), "rarities": list(s.RARITIES), "types": list(s.TYPES),
            "targets": list(s.TARGETS), "keywords": list(s.KEYWORDS), "relic_rarities": list(s.RELIC_RARITIES),
            "expr_names": sorted(s.EXPR_NAMES)}


def _is_fullrun(meta):
    return bool(meta.get("characters")) and any(isinstance(v, dict) and v.get("starting_deck")
                                                for v in (meta.get("characters") or {}).values())


@router.get("/mods")
def mods():
    import yaml
    out = []
    for base, user in ((paths.USER_MODS_DIR, True), (os.path.join(paths.SIM_ROOT, "mods"), False)):
        if not os.path.isdir(base):
            continue
        for n in sorted(os.listdir(base)):
            f = os.path.join(base, n, "mod.yaml")
            if not os.path.isfile(f) or not NAME_RE.match(n):
                continue
            try:
                meta = yaml.safe_load(open(f, encoding="utf-8")) or {}
            except Exception:  # noqa
                meta = {}
            if any(m["id"] == n for m in out):
                continue
            out.append({"id": n, "title": meta.get("title") or meta.get("name") or n, "user": user,
                        "fullrun": _is_fullrun(meta), "characters": list((meta.get("characters") or {}))})
    return out


def _public(m):
    m = dict(m)
    m.pop("meta", None)
    m.pop("_dir", None)
    return m


@router.get("/mod/{name}")
def get_mod(name: str):
    try:
        d = mod_dir(name)
        m = S().load_mod_dir(d)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except S().ModFormatError as e:
        raise HTTPException(400, e.text("zhs" if i18n.current() == "zhs" else "en"))
    m = _public(m)
    m["readonly"] = not d.startswith(os.path.abspath(paths.USER_MODS_DIR))
    return m


@router.get("/new")
def new_mod():
    """空白模板：一个角色、两张基础牌、一个初始遗物。"""
    return {"name": "my_mod", "title": "My mod", "prefix": "MyMod", "readonly": False,
            "characters": {"MyHero": {"id": "MyHero", "name": "My Hero", "hp": 75, "energy": 3, "gold": 99,
                                      "starting_deck": ["STRIKE×5", "DEFEND×5"], "relics": ["LUCKY_COIN"]}},
            "cards": [
                {"id": "STRIKE", "name": "Strike", "type": "Attack", "rarity": "Basic", "cost": 1, "target": "AnyEnemy",
                 "keywords": [], "vars": {"dmg": 6}, "upgrade": {"vars": {"dmg": 9}}, "effects": [{"op": "damage", "amount": "dmg"}],
                 "text": "Deal {dmg} damage.", "pool": True},
                {"id": "DEFEND", "name": "Defend", "type": "Skill", "rarity": "Basic", "cost": 1, "target": "Self",
                 "keywords": [], "vars": {"blk": 5}, "upgrade": {"vars": {"blk": 8}}, "effects": [{"op": "block", "amount": "blk"}],
                 "text": "Gain {blk} Block.", "pool": True},
                {"id": "BIG_HIT", "name": "Big Hit", "type": "Attack", "rarity": "Common", "cost": 2, "target": "AnyEnemy",
                 "keywords": [], "vars": {"dmg": 14}, "upgrade": {"vars": {"dmg": 18}}, "effects": [{"op": "damage", "amount": "dmg"}],
                 "text": "Deal {dmg} damage.", "pool": True},
                {"id": "SHIELD_UP", "name": "Shield Up", "type": "Skill", "rarity": "Uncommon", "cost": 1, "target": "Self",
                 "keywords": [], "vars": {"blk": 9}, "upgrade": {"vars": {"blk": 12}}, "effects": [{"op": "block", "amount": "blk"}, {"op": "draw", "n": 1}],
                 "text": "Gain {blk} Block. Draw 1 card.", "pool": True},
                {"id": "FINISHER", "name": "Finisher", "type": "Attack", "rarity": "Rare", "cost": 3, "target": "AllEnemies",
                 "keywords": ["Exhaust"], "vars": {"dmg": 24}, "upgrade": {"vars": {"dmg": 30}},
                 "effects": [{"op": "damage", "amount": "dmg", "target": "all"}], "text": "Deal {dmg} damage to ALL enemies. Exhaust.", "pool": True},
            ],
            "powers": [],
            "relics": [{"id": "LUCKY_COIN", "name": "Lucky Coin", "rarity": "Starter", "pool": False, "vars": {},
                        "triggers": [{"template": "at_battle_start", "do": [{"op": "block", "amount": 4}]}],
                        "text": "At the start of each combat, gain 4 Block."}],
            "potions": [], "helpers": {}, "ai_values": {}, "variants": {}, "files": {}}


class ModBody(BaseModel):
    mod: dict
    old_name: str | None = None


def _norm(mod):
    """前端发来的字典 → 写成文件再读回（保证和从文件加载的完全一样）。"""
    s = S()
    mod = dict(mod)
    for k, v in (("cards", []), ("powers", []), ("relics", []), ("potions", []), ("characters", {}), ("files", {})):
        mod.setdefault(k, v)
    for c in mod["cards"]:
        c.setdefault("upgrade", {})
        c["upgrade"].setdefault("vars", {})
        c.setdefault("keywords", [])
        c.setdefault("vars", {})
        c.setdefault("effects", [])
    files = s.dump_mod_dir(mod)
    keep = json.dumps(mod.get("variants") or {}, ensure_ascii=False)
    for rel, text in (mod.get("files") or {}).items():
        # 变体用到的文件、Python 钩子：原样保留
        if rel not in files and (rel.endswith(".py") or rel in keep):
            files[rel] = text
    return files, s.load_mod_files(files)


def _problems(mod):
    s = S()
    pr, wr = s.validate(mod, fullrun=True)
    pair = lambda xs: [{"where": w, "zhs": zh, "en": en} for w, zh, en in xs]  # noqa
    return pair(pr), pair(wr)


@router.post("/validate")
def validate(body: ModBody):
    try:
        _files, m = _norm(body.mod)
    except S().ModFormatError as e:
        return {"ok": False, "problems": [{"where": w, "zhs": zh, "en": en} for w, zh, en in e.problems], "warnings": []}
    except Exception as e:  # noqa
        return {"ok": False, "problems": [{"where": "", "zhs": str(e), "en": str(e)}], "warnings": []}
    pr, wr = _problems(m)
    return {"ok": not pr, "problems": pr, "warnings": wr}


@router.post("/save")
async def save(body: ModBody):
    name = str(body.mod.get("name") or "")
    if not NAME_RE.match(name):
        raise HTTPException(400, T("err.modName"))
    if os.path.isdir(os.path.join(paths.SIM_ROOT, "mods", name)):
        raise HTTPException(400, T("me.err.builtinName", name=name))
    try:
        files, m = _norm(body.mod)
    except S().ModFormatError as e:
        raise HTTPException(400, e.text("zhs" if i18n.current() == "zhs" else "en"))
    dst = os.path.join(paths.USER_MODS_DIR, name)
    if body.old_name != name and os.path.isdir(dst):
        raise HTTPException(400, T("err.modNameTaken", name=name))
    os.makedirs(paths.USER_MODS_DIR, exist_ok=True)
    tmp = dst + ".saving"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    for rel, text in files.items():
        fp = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.replace(tmp, dst)
    pr, wr = _problems(m)
    res = {"ok": not pr, "name": name, "problems": pr, "warnings": wr, "cards": {}, "characters": list(m["characters"])}
    if not pr:   # 真注册一遍（子进程），拿到每张牌的游戏 ID（单卡 A/B 要用）
        chk = await asyncio.to_thread(mod_check, dst, True)
        res.update(ok=chk.get("ok", False), problems=chk.get("problems", []), cards=chk.get("cards", {}))
    return res


@router.get("/export/{name}")
def export(name: str):
    try:
        d = mod_dir(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _dn, fn in os.walk(d):
            for f in fn:
                if f == "gui_meta.json" or f.endswith((".pyc",)):
                    continue
                full = os.path.join(dp, f)
                z.write(full, os.path.join(name, os.path.relpath(full, d)).replace(os.sep, "/"))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"content-disposition": f'attachment; filename="{name}.zip"'})


@router.post("/import")
async def import_zip(file: UploadFile = File(...)):
    """读一个 YAML mod 压缩包 → 返回内容给编辑器（不保存；按「保存」才写到你的 mod 文件夹）。"""
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, T("err.tooBig"))
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, T("err.badZip"))
    for n in zf.namelist():
        if n.startswith("/") or ".." in n.replace("\\", "/").split("/"):
            raise HTTPException(400, T("err.unsafePath", path=n))
    try:
        m = S().load_mod_zip(data)
    except S().ModFormatError as e:
        raise HTTPException(400, e.text("zhs" if i18n.current() == "zhs" else "en"))
    except UnicodeDecodeError:
        raise HTTPException(400, T("me.err.notUtf8"))
    m = _public(m)
    m["readonly"] = False
    pr, wr = _problems(S().load_mod_files(S().dump_mod_dir(m) | {k: v for k, v in m["files"].items() if k.endswith(".py")})) \
        if m.get("characters") else ([], [])
    m["_check"] = {"problems": pr, "warnings": wr}
    return m


@router.delete("/mod/{name}")
def delete(name: str):
    if not NAME_RE.match(name):
        raise HTTPException(400, T("err.modName"))
    d = os.path.join(paths.USER_MODS_DIR, name)
    if not os.path.isdir(d):
        raise HTTPException(404, T("err.onlyUserMods"))
    shutil.rmtree(d)
    return {"ok": True}


@router.get("/check/{name}")
async def check(name: str):
    try:
        d = mod_dir(name)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return await asyncio.to_thread(mod_check, d, True)
