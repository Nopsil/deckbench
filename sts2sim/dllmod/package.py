"""定位一份已安装的 StS2 mod（清单 JSON + DLL），读元数据，能反编译就抽出 YAML。"""
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import zipfile

import yaml

from . import extract as E
from .metadata import read_assembly

GAME_DLL_NAMES = {"sts2.dll", "godotsharp.dll", "0harmony.dll"}
VANILLA_POOLS = {
    "IroncladCardPool": "Ironclad", "SilentCardPool": "Silent", "DefectCardPool": "Defect",
    "NecrobinderCardPool": "Necrobinder", "RegentCardPool": "Regent", "ColorlessCardPool": "Colorless",
    "SharedRelicPool": "shared relics", "SharedPotionPool": "shared potions",
}
_TARGET_YAML = {"AnyEnemy": "enemy", "Self": "self", "AllEnemies": "all", "RandomEnemy": "random"}
_SKIP_DIRS = {".git", "bin", "obj", "node_modules"}


class DllModError(Exception):
    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def list_installed(game_dir=None):
    """游戏 mods/ 目录里、带清单的 mod。找不到游戏就返回空列表。"""
    root = _mods_root(game_dir)
    if not root:
        return []
    out = []
    for _dir, manifest, _dll in _manifests_under(root):
        out.append({"id": manifest.get("id"), "name": manifest.get("name") or manifest.get("id"),
                    "version": manifest.get("version") or "", "author": manifest.get("author") or ""})
    return out


def import_installed(mod_id, decompile=True, lang=None, game_dir=None):
    """按游戏 mods/ 里的清单 id 导入。id 必须是已经列出来的那一个。"""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(mod_id or "")):
        raise DllModError("err.dllNone")
    root = _mods_root(game_dir)
    if not root:
        raise DllModError("err.dllNone")
    for folder, manifest, dll in _manifests_under(root):
        if manifest.get("id") == mod_id:
            return _build(folder, manifest, dll, decompile=decompile, lang=lang, game_dir=game_dir)
    raise DllModError("err.dllNone")


def import_path(path, decompile=True, lang=None, game_dir=None):
    """path：mod 目录、zip，或单个 DLL。返回 (mod 字典, 报告)。失败抛 DllModError。"""
    tmp = None
    try:
        src = path
        if os.path.isfile(path) and path.lower().endswith(".zip"):
            tmp = tempfile.mkdtemp(prefix="deckbench-dllmod-")
            try:
                _unzip(path, tmp)
            except zipfile.BadZipFile:
                shutil.rmtree(tmp, ignore_errors=True)
                raise DllModError("err.badZip")
            src = tmp
        elif os.path.isfile(path) and path.lower().endswith(".dll"):
            return _from_dll_file(path, decompile=decompile, lang=lang, game_dir=game_dir)
        if not os.path.isdir(src):
            raise DllModError("err.dllNone")
        found = _manifests_under(src)
        if len(found) > 1:
            raise DllModError("err.dllMany", ids=", ".join(m.get("id") or "?" for _d, m, _f in found))
        if found:
            folder, manifest, dll = found[0]
        else:
            dlls = _candidate_dlls(src)
            if len(dlls) != 1:
                raise DllModError("err.dllNone" if not dlls else "err.dllMany",
                                  ids=", ".join(os.path.basename(p) for p in dlls))
            dll = dlls[0]
            folder = os.path.dirname(dll)
            manifest = {"id": os.path.splitext(os.path.basename(dll))[0], "name": os.path.splitext(os.path.basename(dll))[0],
                        "has_dll": True}
        return _build(folder, manifest, dll, decompile=decompile, lang=lang, game_dir=game_dir)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _from_dll_file(path, decompile, lang, game_dir):
    base = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(os.path.abspath(path))
    manifest = {"id": base, "name": base, "has_dll": True}
    for _d, man, dll in _manifests_under(folder):
        if os.path.abspath(dll or "") == os.path.abspath(path) or man.get("id") == base:
            manifest = man
            break
    return _build(folder, manifest, path, decompile=decompile, lang=lang, game_dir=game_dir)


def _build(folder, manifest, dll, decompile, lang, game_dir):
    if not dll or not os.path.isfile(dll):
        raise DllModError("err.dllNone")
    if os.path.basename(dll).lower() in GAME_DLL_NAMES:
        raise DllModError("err.dllGame", name=os.path.basename(dll))
    try:
        info = read_assembly(dll)
    except RuntimeError as e:
        if str(e) == "dnfile":
            raise DllModError("err.dllNeedReader") from e
        raise DllModError("err.dllRead", err=e) from e
    except ValueError as e:
        raise DllModError("err.dllRead", err=e) from e
    if info.is_game:
        raise DllModError("err.dllGame", name=info.name)
    models = info.models()
    if not models:
        raise DllModError("err.dllEmpty")
    src_dir, dec_err = (None, None)
    if decompile:
        src_dir, dec_err = _decompile(dll, folder, manifest, game_dir)
    try:
        texts = _csharp_texts(src_dir) if src_dir else {}
        specs, regs, ordinal = E.parse_sources(texts) if texts else ({}, [], False)
        loc = _localization(folder, lang)
        mod, report = _to_mod(manifest, info, specs, regs, ordinal, loc, bool(texts), dec_err)
        return mod, report
    finally:
        if src_dir:
            shutil.rmtree(src_dir, ignore_errors=True)


def _to_mod(manifest, info, specs, regs, ordinal, loc, decompiled, dec_err):
    by_class = {}
    for t in info.models():
        by_class.setdefault(t["name"], t)
    for name in specs:
        by_class.setdefault(name, {"name": name, "kind": specs[name]["kind"]})
    power_ids = {}
    cards, powers, relics, potions, characters = [], [], [], [], []
    notes = []
    for name, meta in by_class.items():
        spec = specs.get(name)
        kind = (spec or meta).get("kind") or meta.get("kind")
        if not kind:
            continue
        if spec is None:
            spec = {"class_name": name, "kind": kind, "status": "inventory", "vars": {}, "effects": [],
                    "triggers": [], "keywords": [], "tags": [], "upgrade_vars": {}, "cost": None,
                    "type": None, "rarity": None, "target": None, "show": True, "stack": "Counter",
                    "power_type": "Buff", "hp": None, "energy": None, "gold": None, "starting_deck": []}
            ordinal_here = False
        else:
            ordinal_here = False
        entry = E.scream(name)
        title = _loc_name(loc, entry) or E.pretty(name)
        text = _loc_text(loc, entry)
        nz, ne = E.note_pair(spec["status"], ordinal and spec["status"] != "inventory", kind)
        if spec["status"] != "translated" or (ordinal and kind == "card" and spec.get("type") is None):
            notes.append({"where": entry, "zhs": nz, "en": ne})
        if kind == "card":
            cards.append(_card(spec, entry, title, text))
        elif kind == "power":
            power_ids[name] = entry
            powers.append(_power(spec, entry, title, text))
        elif kind == "relic":
            relics.append(_relic(spec, entry, title, text))
        elif kind == "potion":
            potions.append(_potion(spec, entry, title, text))
        elif kind == "character":
            characters.append((name, spec, title))
    _link_powers(cards, powers, relics, potions, power_ids)
    mod_id = _safe_name(manifest.get("id") or info.name)
    char_map = _characters(characters, cards, relics, specs)
    files = _yaml_files(mod_id, manifest.get("name") or mod_id, manifest.get("id") or mod_id, cards, powers, relics, potions, char_map)
    from ..modfmt import schema as S
    mod = S.load_mod_files(files)
    limitations = _limitations(decompiled, dec_err, ordinal, info.refs, manifest.get("dependencies") or [])
    report = {
        "mode": "decompiled" if decompiled else "metadata",
        "assembly": info.name,
        "manifest_id": manifest.get("id"),
        "initializer": info.initializers[0][1] if info.initializers else None,
        "references_harmony": any(r.lower() == "0harmony" for r in info.refs),
        "dependencies": list(manifest.get("dependencies") or []),
        "pools": [{"pool": p, "class": c, "vanilla": VANILLA_POOLS.get(p)} for p, c in regs],
        "cards": [{"id": c["id"], "class": c.get("class"), "status": _status_for(c, specs)} for c in cards],
        "decompile_error": dec_err,
        "limitations": [{"where": "", "zhs": z, "en": e} for z, e in limitations],
        "notes": notes,
    }
    mod["_dll_report"] = report
    return mod, report


def _status_for(card, specs):
    for spec in specs.values():
        if spec.get("class_name") == card.get("class"):
            return spec.get("status")
    return "inventory"


def _card(spec, entry, title, text):
    known = spec.get("type") and spec.get("rarity") and spec.get("target") and spec.get("cost") is not None
    rarity = spec.get("rarity") or "UNKNOWN"
    pool = True
    if spec.get("show") is False or rarity in ("Basic", "Token", "Status", "Curse"):
        pool = False
    up = {}
    if spec.get("upgrade_vars"):
        up["vars"] = spec["upgrade_vars"]
    if spec.get("upgrade_cost") is not None:
        up["cost"] = spec["upgrade_cost"]
    d = {"id": entry, "name": title, "class": spec["class_name"], "type": spec.get("type") or "UNKNOWN",
         "rarity": rarity, "cost": spec.get("cost") if spec.get("cost") is not None else 1,
         "target": _TARGET_YAML.get(spec.get("target") or "", "self") if known or spec.get("target") else "UNKNOWN",
         "keywords": [k.lower() for k in spec.get("keywords") or []], "tags": spec.get("tags") or [],
         "vars": spec.get("vars") or {}, "effects": _clean_effects(spec.get("effects") or []),
         "upgrade": up, "text": text or "", "pool": pool}
    if not known:
        d["type"] = spec.get("type") or "UNKNOWN"
        d["rarity"] = spec.get("rarity") or "UNKNOWN"
        d["target"] = _TARGET_YAML.get(spec.get("target") or "", "UNKNOWN") if spec.get("target") else "UNKNOWN"
    return d


def _clean_effects(effects):
    return [{k: v for k, v in e.items() if v is not None} for e in effects]


def _link_powers(cards, powers, relics, potions, power_ids):
    def fix(eff):
        if not isinstance(eff, dict):
            return
        cls = eff.pop("power_class", None)
        if cls:
            eff["power"] = power_ids.get(cls) or E.scream(cls[:-5] if cls.endswith("Power") else cls)
        for k in ("then", "else", "do", "each_hit"):
            for sub in eff.get(k) or []:
                fix(sub)
    for group in (cards, potions):
        for item in group:
            for eff in item.get("effects") or []:
                fix(eff)
    for group in (powers, relics):
        for item in group:
            for tr in item.get("triggers") or []:
                for eff in tr.get("do") or []:
                    fix(eff)


def _power(spec, entry, title, text):
    stack = "Single" if str(spec.get("stack")).lower() == "single" else "Counter"
    kind = "Debuff" if str(spec.get("power_type")).lower() == "debuff" else "Buff"
    return {"id": entry, "name": title, "class": spec["class_name"], "type": kind, "stack": stack,
            "vars": spec.get("vars") or {}, "triggers": spec.get("triggers") or [], "text": text or ""}


def _relic(spec, entry, title, text):
    rarity = spec.get("rarity") or "Common"
    d = {"id": entry, "name": title, "class": spec["class_name"], "rarity": rarity,
         "vars": spec.get("vars") or {}, "triggers": spec.get("triggers") or [], "text": text or ""}
    if rarity == "Starter":
        d["pool"] = False
    return d


def _potion(spec, entry, title, text):
    return {"id": entry, "name": title, "class": spec["class_name"], "rarity": spec.get("rarity") or "Common",
            "target": _TARGET_YAML.get(spec.get("target") or "", "self"), "vars": spec.get("vars") or {},
            "effects": _clean_effects(spec.get("effects") or []), "text": text or ""}


def _characters(chars, cards, relics, specs):
    out = {}
    by_class = {c.get("class"): c["id"] for c in cards}
    for name, spec, title in chars:
        deck = []
        counts = {}
        for cls in spec.get("starting_deck") or []:
            cid = by_class.get(cls)
            if not cid:
                continue
            counts[cid] = counts.get(cid, 0) + 1
        for cid, n in counts.items():
            deck.append(cid if n == 1 else f"{cid}×{n}")
        if not deck:
            continue
        rel = [r["id"] for r in relics if r.get("rarity") == "Starter"]
        cid = E.scream(name)
        if cid.endswith("_CHARACTER"):
            cid = cid[:-10] or cid
        out[cid] = {"name": title, "hp": spec.get("hp") if spec.get("hp") is not None else 75,
                    "energy": spec.get("energy") if spec.get("energy") is not None else 3,
                    "gold": spec.get("gold") if spec.get("gold") is not None else 99,
                    "starting_deck": deck, "relics": rel, "class": name}
    return out


def _yaml_files(mod_id, title, prefix, cards, powers, relics, potions, characters):
    meta = {"name": mod_id, "title": title, "prefix": re.sub(r"[^0-9A-Za-z_]", "", prefix) or mod_id}
    files = {}
    if characters:
        meta["characters"] = characters
    if cards:
        meta["cards"] = ["cards.yaml"]
        files["cards.yaml"] = yaml.safe_dump(cards, allow_unicode=True, sort_keys=False, width=120)
    if powers:
        meta["powers"] = ["powers.yaml"]
        files["powers.yaml"] = yaml.safe_dump(powers, allow_unicode=True, sort_keys=False, width=120)
    if relics:
        meta["relics"] = ["relics.yaml"]
        files["relics.yaml"] = yaml.safe_dump(relics, allow_unicode=True, sort_keys=False, width=120)
    if potions:
        meta["mod_potions"] = ["potions.yaml"]
        files["potions.yaml"] = yaml.safe_dump(potions, allow_unicode=True, sort_keys=False, width=120)
    files["mod.yaml"] = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=120)
    return files


def _limitations(decompiled, dec_err, ordinal, refs=(), dependencies=()):
    out = [
        ("这个 DLL 没有被执行。Harmony 补丁、Godot 场景和 .pck 里的画面都不会进模拟器。",
         "This DLL is not executed. Harmony patches, Godot scenes and visuals inside a .pck are not applied."),
        ("只有能对上模拟器动作的直线效果会保留。分支、选项和自定义命令留空，并在下面标明，避免把「有条件才发动」写成「每次都发动」。",
         "Only straight-line effects that map onto simulator actions are kept. Branches, choices and custom commands are left blank and listed below, so a conditional effect is not imported as if it always happens."),
        ("导进来的数值是起点，不是和游戏逐条对过的结果。拿去比强弱之前，先用一小批对局核对一场战斗。",
         "Imported numbers are a starting point, not a line-by-line match against the game. Before comparing balance, check one fight with a small batch."),
    ]
    if not decompiled:
        extra = " " + dec_err if dec_err else ""
        out.append(("没有读到方法体（找不到反编译器，或找不到你本机的游戏来解析引用）。牌还在列表里，但费用、类型和效果不能拿来测试。"
                    "装好和首次生成同一套工具后再导一次。不会把游戏文件复制进 DeckBench。" + extra,
                    "Method bodies were not read (no decompiler, or your local game install was not found to resolve references). "
                    "Cards are listed, but cost, type and effects are not safe to test. Install the same tools as first-run setup and import again. "
                    "Game files are not copied into DeckBench." + extra))
    elif ordinal:
        out.append(("反编译时没有用游戏程序集做引用，有的枚举被写成了数字。这些数字没有拿来猜类型或关键词。找到游戏安装后重新导入。",
                    "The decompiler had no game assembly for references, so some enums came out as numbers. Those numbers were not guessed into types or keywords. Import again once your install is found."))
    if any(str(r).lower() == "0harmony" for r in refs):
        out.append(("这个 DLL 引用了 Harmony。补丁方法不会作用到模拟器上，被补丁改过的原版牌也不会跟着变。",
                    "This DLL references Harmony. Patch methods are not applied to the simulator, and base-game cards those patches change stay unchanged."))
    deps = [str(d) for d in dependencies if str(d).strip()]
    if deps:
        joined = ", ".join(deps)
        out.append((f"清单里的依赖（{joined}）不会被展开。依赖里的辅助函数如果出现在效果里，这张牌会标成不完整。",
                    f"Dependencies listed in the manifest ({joined}) are not expanded. If an effect calls a helper from one of them, that card is marked incomplete."))
    return out


def _safe_name(s):
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(s or "mod")).strip("_") or "mod"
    if not s[0].isalpha():
        s = "m_" + s
    return s[:40]


def _mods_root(game_dir=None):
    from .. import gamedata
    dll = gamedata.find_dll(game_dir)
    if not dll:
        return None
    d = os.path.dirname(dll)
    for _ in range(5):
        cand = os.path.join(d, "mods")
        if os.path.isdir(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _manifests_under(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if not fn.lower().endswith(".json"):
                continue
            path = os.path.join(dirpath, fn)
            man = _read_manifest(path)
            if not man:
                continue
            dll = _dll_for(dirpath, man)
            if man.get("has_dll") is False and not dll:
                continue
            out.append((dirpath, man, dll))
    return out


def _read_manifest(path):
    try:
        if os.path.getsize(path) > 1_000_000:
            return None
        data = json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("id"), str):
        return None
    if not any(k in data for k in ("has_dll", "has_pck", "dependencies", "affects_gameplay")):
        return None
    return data


def _dll_for(folder, manifest):
    mid = manifest.get("id") or ""
    named = os.path.join(folder, mid + ".dll")
    if os.path.isfile(named):
        return named
    dlls = _candidate_dlls(folder, recursive=False)
    return dlls[0] if len(dlls) == 1 else None


def _candidate_dlls(root, recursive=True):
    out = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if fn.lower().endswith(".dll") and fn.lower() not in GAME_DLL_NAMES:
                    out.append(os.path.join(dirpath, fn))
    else:
        for fn in os.listdir(root):
            if fn.lower().endswith(".dll") and fn.lower() not in GAME_DLL_NAMES:
                out.append(os.path.join(root, fn))
    return sorted(out)


def _csharp_texts(src_dir):
    out = {}
    for dirpath, _dns, filenames in os.walk(src_dir):
        for fn in filenames:
            if not fn.endswith(".cs"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                out[path] = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
    return out


def _decompile(dll, folder, manifest, game_dir):
    from .. import gamedata
    ilspy, refs = gamedata._find_ilspy()
    if not ilspy:
        return None, "ilspycmd not found"
    out = tempfile.mkdtemp(prefix="deckbench-dllsrc-")
    argv = [ilspy, "-p", "--nested-directories", "-o", out]
    net = refs or gamedata._net9_dir()
    if net:
        argv += ["-r", net]
    for d in _ref_dirs(dll, folder, manifest, game_dir):
        argv += ["-r", d]
    argv.append(dll)
    env = dict(os.environ)
    env.setdefault("DOTNET_ROLL_FORWARD", "Major")
    if not env.get("DOTNET_ROOT") and net:
        root = net
        for _ in range(3):
            root = os.path.dirname(root)
        if os.path.isdir(os.path.join(root, "shared")):
            env["DOTNET_ROOT"] = root
    try:
        import subprocess
        kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE, "env": env, "timeout": 180, "text": True}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000
        p = subprocess.run(argv, **kw)
    except (OSError, subprocess.TimeoutExpired) as e:
        shutil.rmtree(out, ignore_errors=True)
        return None, str(e)
    if p.returncode != 0 or not _csharp_texts(out):
        err = (p.stderr or "")[-500:]
        shutil.rmtree(out, ignore_errors=True)
        return None, err or f"ilspycmd exited {p.returncode}"
    return out, None


def _ref_dirs(dll, folder, manifest, game_dir):
    from .. import gamedata
    dirs = []
    game = gamedata.find_dll(game_dir)
    if game:
        dirs.append(os.path.dirname(game))
    dirs.append(os.path.dirname(os.path.abspath(dll)))
    if folder:
        dirs.append(folder)
    root = _mods_root(game_dir)
    for dep in manifest.get("dependencies") or []:
        if not root or not isinstance(dep, str):
            continue
        for cand in (os.path.join(root, dep), os.path.join(root, dep, dep)):
            if os.path.isdir(cand):
                dirs.append(cand)
    seen, out = set(), []
    for d in dirs:
        d = os.path.abspath(d)
        if d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def _localization(folder, prefer):
    """{lang: {ENTRY.title: text}}，只读这个 mod 自己的 json / .pck。"""
    tables = {}
    for dirpath, _d, filenames in os.walk(folder):
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            low = fn.lower()
            if low.endswith(".json"):
                key = _loc_parts(path.replace("\\", "/"))
                if key:
                    _merge_loc(tables, key, _load_json(path))
            elif low.endswith(".pck"):
                try:
                    for lang, table, data in _pck_loc(path):
                        _merge_loc(tables, (lang, table), data)
                except (OSError, ValueError):
                    continue
    flat = {}
    for (lang, _table), data in tables.items():
        if isinstance(data, dict):
            flat.setdefault(lang, {}).update({str(k): v for k, v in data.items() if isinstance(v, str)})
    flat["_prefer"] = prefer
    return flat


def _loc_parts(path):
    parts = path.split("/")
    if "localization" not in parts:
        return None
    i = parts.index("localization")
    if i + 2 >= len(parts) or not parts[i + 2].endswith(".json"):
        return None
    return parts[i + 1], parts[i + 2][:-5]


def _load_json(path):
    try:
        if os.path.getsize(path) > 2_000_000:
            return None
        return json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return None


def _merge_loc(tables, key, data):
    if isinstance(data, dict):
        tables.setdefault(key, {}).update(data)


def _pck_loc(path):
    with open(path, "rb") as f:
        magic, ver, _a, _b, _c, flags = struct.unpack("<6I", f.read(24))
        if magic != 0x43504447 or ver not in (2, 3) or flags & 1:
            raise ValueError("not an unencrypted pck")
        base, = struct.unpack("<Q", f.read(8))
        if ver == 3:
            d, = struct.unpack("<Q", f.read(8))
            f.seek(d)
        else:
            f.seek(64, 1)
        n, = struct.unpack("<I", f.read(4))
        entries = []
        for _ in range(n):
            ln, = struct.unpack("<I", f.read(4))
            name = f.read(ln).rstrip(b"\0").decode("utf-8", "replace")
            off, size = struct.unpack("<QQ", f.read(16))
            md5 = f.read(16)
            eflags, = struct.unpack("<I", f.read(4))
            entries.append((name, base + off, size, md5, eflags))
        for name, off, size, md5, eflags in entries:
            if eflags or size > 2_000_000 or "localization" not in name or not name.endswith(".json"):
                continue
            key = _loc_parts(name.replace("\\", "/"))
            if not key:
                continue
            f.seek(off)
            data = f.read(size)
            if hashlib.md5(data).digest() != md5:
                continue
            try:
                obj = json.loads(data.decode("utf-8-sig"))
            except ValueError:
                continue
            yield key[0], key[1], obj


def _loc_name(loc, entry):
    return _loc_field(loc, entry, "title") or _loc_field(loc, entry, "name")


def _loc_text(loc, entry):
    return _loc_field(loc, entry, "description") or ""


def _loc_field(loc, entry, field):
    prefer = loc.get("_prefer")
    order = [prefer, "eng", "zhs", "jpn", "kor"]
    order += [k for k in loc if isinstance(k, str) and not k.startswith("_")]
    for lang in order:
        table = loc.get(lang)
        if not isinstance(table, dict):
            continue
        for key in (f"{entry}.{field}", f"{entry}.{field.upper()}"):
            if table.get(key):
                return table[key]
    return None


def _unzip(path, dest):
    with zipfile.ZipFile(path) as zf:
        for n in zf.namelist():
            rel = n.replace("\\", "/")
            if rel.startswith("/") or ".." in rel.split("/"):
                raise DllModError("err.unsafePath", path=n)
        zf.extractall(dest)
