"""把一次测试（或一次对比、对打、单卡贡献）打成一个 .deckbench.zip，再原样导回来。

包里是数据：清单、meta.json、raw.jsonl（整局则是 runs.jsonl）、有的话再加牌组预设，
以及 #56 那份离线 HTML。清单写 DeckBench 版本（``sts2sim.__version__``）、schema 版本，
和每个文件的 SHA-256。

导入只校验清单和哈希，然后把结果写成普通的测试目录。不执行包里的任何内容，
不把预设装进可运行的预设目录，不打开 HTML。路径上有 ``..``、绝对路径、
反斜杠、超限，都拒绝。schema 不是本程序能读的版本时，说明里写明当前只读哪一版。

编号已经存在时换一个新编号。导进来的测试带 ``imported`` 和 ``origin``，
状态仍是原来的 done / cancelled，所以列表和对比跟本地测试一样。

A shareable ``.deckbench.zip``. The manifest records ``sts2sim.__version__``,
the schema version, and a SHA-256 of every other file. Import checks those
hashes and writes run folders. Nothing in the bundle is executed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import zipfile

SCHEMA = 1
FORMAT = "deckbench.bundle"
MAX_UPLOAD = 32 * 1024 * 1024
MAX_MEMBER = 16 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_MEMBERS = 512
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_MEMBER = re.compile(
    r"^(?:manifest\.json|report\.html|"
    r"runs/(?P<id>[A-Za-z0-9][A-Za-z0-9._-]{0,80})/"
    r"(?:meta\.json|raw\.jsonl|runs\.jsonl|preset\.yaml|card_impact\.json))$"
)
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_KINDS = {"run", "compare", "head_to_head", "card_impact"}
_RUN_KINDS = {"batch", "combat", "card_impact"}
_META_KEYS = (
    "id", "kind", "title", "status", "created", "finished", "started_ts", "secs",
    "params", "lang", "partial", "progress", "headline", "backend",
)
_ID_KEYS = {"id", "run", "job"}
_SAVE_PARTS = {"saves", "history", "slaythespire2"}


class BundleError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def message(err, lang=None):
    """给人看的一句说明。不带回显的路径，也不带堆栈。"""
    from gui import i18n
    code = getattr(err, "code", "") or "manifest"
    params = getattr(err, "params", None) or {}
    if code == "schema":
        schema = params.get("schema")
        if isinstance(schema, int) and not isinstance(schema, bool) and 0 <= schema <= 9999:
            return i18n.t("bundle.err.schema", lang, schema=schema, supported=SCHEMA)
        return i18n.t("bundle.err.schemaBad", lang)
    if code == "hash":
        return i18n.t("bundle.err.hash", lang)
    if code == "zip_slip":
        return i18n.t("bundle.err.slip", lang)
    if code == "too_big":
        return i18n.t("bundle.err.tooBig", lang)
    if code == "manifest":
        return i18n.t("bundle.err.manifest", lang)
    if code == "not_bundle":
        return i18n.t("bundle.err.kind", lang)
    if code == "incomplete":
        return i18n.t("bundle.err.incomplete", lang)
    if code == "extra":
        return i18n.t("bundle.err.extra", lang)
    if code == "need_input":
        return i18n.t("bundle.err.need", lang)
    if code == "not_done":
        return i18n.t("err.notDone", lang)
    if code == "not_found":
        return i18n.t("err.runNotFound", lang)
    if code == "no_result":
        return i18n.t("export.err.noResult", lang)
    if code == "same_run":
        return i18n.t("err.compareSame", lang)
    if code == "not_combat":
        return i18n.t("err.compareCombat", lang)
    if code == "missing":
        return i18n.t("api.err.missing", lang, field=params.get("field") or "request")
    if code == "bad_type":
        return i18n.t(
            "api.err.bad_type", lang,
            field=params.get("field") or "request",
            expected=i18n.t("api.type.string", lang),
        )
    if code == "bad_lang":
        return i18n.t("export.err.badLang", lang)
    if code == "path_not_allowed":
        return i18n.t("exp.err.path_not_allowed", lang, path="")
    if code == "refuse_write":
        return i18n.t("exp.err.refuse_write", lang, path="")
    if code == "not_json":
        return i18n.t("err.compareBad", lang, line=params.get("line") or 1)
    return i18n.t("bundle.err.manifest", lang)


def content_disposition(filename):
    """attachment，带 ASCII 文件名和 UTF-8 的 filename*。"""
    ascii_name = "".join(ch if ch.isascii() and ch not in '"\\' else "-" for ch in filename)
    ascii_name = ascii_name.strip(".-") or "deckbench-run.deckbench.zip"
    if not ascii_name.lower().endswith(".zip"):
        ascii_name += ".deckbench.zip"
    from urllib.parse import quote
    return "attachment; filename=\"" + ascii_name + "\"; filename*=UTF-8''" + quote(filename, safe="")


def bundle_filename(kind, run_ids):
    if kind == "compare" and len(run_ids) >= 2:
        stem = "deckbench-compare-" + _slug(run_ids[0]) + "-" + _slug(run_ids[1])
    elif kind == "head_to_head" and len(run_ids) >= 2:
        stem = "deckbench-h2h-" + _slug(run_ids[0]) + "-" + _slug(run_ids[1])
    elif kind == "card_impact" and run_ids:
        stem = "deckbench-impact-" + _slug(run_ids[0])
    elif run_ids:
        stem = "deckbench-run-" + _slug(run_ids[0])
    else:
        stem = "deckbench-run"
    return stem[:120] + ".deckbench.zip"


def export_run_bytes(rid, lang=""):
    """一次已结束的测试。单卡贡献会把子测试一并装进去。返回 (zip 字节, 文件名)。"""
    chosen = _choose_lang(lang)
    meta, _folder = _load_job(rid)
    if meta.get("kind") == "card_impact":
        ids = _impact_family(meta)
        kind = "card_impact"
    else:
        ids = [meta["id"]]
        kind = "run"
    files = {}
    for one in ids:
        files.update(_run_files(one))
    files["report.html"] = _html_for(ids[0] if kind == "card_impact" else rid, chosen)
    return _pack(files, kind=kind, run_ids=ids), bundle_filename(kind, ids)


def export_compare_bytes(a, b, lang=""):
    """两次已结束的战斗实验。两边都标了 shared_plan 时，清单 kind 是 head_to_head。"""
    chosen = _choose_lang(lang)
    left_id, right_id = _compare_ids(a, b)
    left, _left_dir = _load_job(left_id)
    right, _right_dir = _load_job(right_id)
    if left.get("kind") != "combat" or right.get("kind") != "combat":
        raise BundleError("not_combat")
    kind = "head_to_head" if _shared(left) and _shared(right) else "compare"
    files = {}
    files.update(_run_files(left_id))
    files.update(_run_files(right_id))
    files["report.html"] = _html_compare(left, right, chosen)
    ids = [left_id, right_id]
    return _pack(files, kind=kind, run_ids=ids), bundle_filename(kind, ids)


def import_zip_bytes(data, *, filename=""):
    """校验后写入测试目录。失败时不留下半截目录，也不执行包里的文件。"""
    members = _read_zip(data)
    manifest = _manifest(members)
    _check_hashes(members, manifest)
    plan = _plan(members, manifest)
    return _install(plan, manifest, filename=filename)


def export_bundle_json(run="", a="", b="", out="", lang=""):
    """MCP。成功时 path 是写好的 zip。失败也是 JSON，没有堆栈。"""
    try:
        _strings(run=run, a=a, b=b, out=out, lang=lang if isinstance(lang, str) else None)
        if not isinstance(lang, str):
            raise BundleError("bad_type", field="lang")
        data, filename = _export_choice(run, a, b, lang)
        path = _write_out(out, filename, data)
    except BundleError as err:
        return _error_json(err)
    body = {"ok": True, "path": path, "filename": filename, "bytes": len(data)}
    return json.dumps(body, ensure_ascii=False) + "\n"


def import_bundle_json(path):
    """MCP。path 必须在允许的目录里。读完只写测试目录，不执行。"""
    try:
        if not isinstance(path, str) or "\x00" in path:
            raise BundleError("bad_type", field="path")
        from sts2sim.analysis import AnalysisError, resolve_read
        try:
            real = resolve_read(path)
        except AnalysisError as err:
            raise BundleError(err.code, **err.params) from err
        if not os.path.isfile(real):
            raise BundleError("not_bundle")
        try:
            size = os.path.getsize(real)
        except OSError as err:
            raise BundleError("not_found") from err
        if size > MAX_UPLOAD:
            raise BundleError("too_big")
        with open(real, "rb") as handle:
            data = handle.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise BundleError("too_big")
        body = import_zip_bytes(data, filename=os.path.basename(real))
    except BundleError as err:
        return _error_json(err)
    return json.dumps(body, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- 打包
def _export_choice(run, a, b, lang):
    left = a.strip()
    right = b.strip()
    if left or right:
        if not left or not right:
            raise BundleError("missing", field="b" if left else "a")
        return export_compare_bytes(left, right, lang=lang)
    if run.strip():
        return export_run_bytes(run.strip(), lang=lang)
    raise BundleError("need_input")


def _strings(**values):
    for field, value in values.items():
        if value is None:
            raise BundleError("bad_type", field=field)
        if not isinstance(value, str) or "\x00" in value:
            raise BundleError("bad_type", field=field)


def _choose_lang(lang):
    from sts2sim.htmlreport import ExportError, parse_lang
    if not isinstance(lang, str) or "\x00" in lang:
        raise BundleError("bad_type", field="lang")
    try:
        chosen = parse_lang(lang)
    except ExportError as err:
        raise BundleError(err.code, **err.params) from err
    from gui import i18n
    return chosen or i18n.current()


def _slug(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text or "")).strip("-.")
    return cleaned[:40] or "run"


def _jobs():
    from gui.server import jobs
    return jobs


def _load_job(rid):
    if not isinstance(rid, str) or not _ID.fullmatch(rid):
        raise BundleError("not_found")
    meta = _jobs().get(rid)
    folder = _jobs().run_dir(rid)
    if not isinstance(meta, dict) or not folder:
        raise BundleError("not_found")
    if meta.get("status") not in ("done", "cancelled"):
        raise BundleError("not_done")
    if meta.get("kind") not in _RUN_KINDS:
        raise BundleError("no_result")
    return meta, folder


def _shared(meta):
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    return bool(params.get("shared_plan"))


def _compare_ids(a, b):
    if not isinstance(a, str) or "\x00" in a:
        raise BundleError("bad_type", field="a")
    if not isinstance(b, str) or "\x00" in b:
        raise BundleError("bad_type", field="b")
    left, right = a.strip(), b.strip()
    if not left:
        raise BundleError("missing", field="a")
    if not right:
        raise BundleError("missing", field="b")
    if left == right:
        raise BundleError("same_run")
    return left, right


def _impact_family(meta):
    folder = _jobs().run_dir(meta["id"])
    path = os.path.join(folder, "card_impact.json")
    if not os.path.isfile(path):
        raise BundleError("no_result")
    try:
        doc = json.loads(_read_capped(path, MAX_MEMBER).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise BundleError("no_result") from err
    if not isinstance(doc, dict):
        raise BundleError("no_result")
    ids = [meta["id"]]
    seen = {meta["id"]}
    for child in _child_ids(doc):
        if child in seen:
            continue
        seen.add(child)
        child_meta, _folder = _load_job(child)
        if child_meta.get("kind") != "combat":
            raise BundleError("incomplete")
        ids.append(child)
    if len(ids) < 2:
        raise BundleError("incomplete")
    return ids


def _child_ids(doc):
    found = []
    for row in doc.get("runs") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            found.append(row["id"])
    for row in doc.get("rows") or []:
        if isinstance(row, dict) and isinstance(row.get("run"), str):
            found.append(row["run"])
    baseline = doc.get("baseline")
    if isinstance(baseline, dict) and isinstance(baseline.get("run"), str):
        found.append(baseline["run"])
    return found


def _run_files(rid):
    meta, folder = _load_job(rid)
    kind = meta.get("kind")
    files = {f"runs/{rid}/meta.json": _meta_bytes(meta)}
    if kind == "combat":
        raw = _find_raw(folder)
        if raw is None:
            raise BundleError("no_result")
        files[f"runs/{rid}/raw.jsonl"] = raw
    elif kind == "batch":
        path = os.path.join(folder, "runs.jsonl")
        if not os.path.isfile(path):
            raise BundleError("no_result")
        files[f"runs/{rid}/runs.jsonl"] = _read_inside(path, folder, MAX_MEMBER)
    elif kind == "card_impact":
        path = os.path.join(folder, "card_impact.json")
        if not os.path.isfile(path):
            raise BundleError("no_result")
        files[f"runs/{rid}/card_impact.json"] = _read_inside(path, folder, MAX_MEMBER)
    else:
        raise BundleError("no_result")
    preset = _preset_bytes(meta, folder)
    if preset is not None:
        files[f"runs/{rid}/preset.yaml"] = preset
    return files


def _find_raw(folder):
    for path in (os.path.join(folder, "out", "raw.jsonl"), os.path.join(folder, "raw.jsonl")):
        if os.path.isfile(path) and not os.path.islink(path):
            return _read_inside(path, folder, MAX_MEMBER)
    return None


def _read_inside(path, root, limit):
    real = os.path.realpath(path)
    root_real = os.path.realpath(root)
    try:
        inside = os.path.normcase(os.path.commonpath([root_real, real])) == os.path.normcase(root_real)
    except ValueError:
        inside = False
    if not inside:
        raise BundleError("no_result")
    return _read_capped(real, limit)


def _read_capped(path, limit):
    """按字节读。不用文本模式，避免 Windows 把 ``\\n`` 换成 ``\\r\\n`` 之后哈希对不上。"""
    try:
        size = os.path.getsize(path)
    except OSError as err:
        raise BundleError("no_result") from err
    if size > limit:
        raise BundleError("too_big")
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise BundleError("too_big")
    return data


def _meta_bytes(meta):
    public = _public_meta(meta)
    return (json.dumps(public, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _public_meta(meta):
    """导出的 meta 只留结果需要的字段。命令行 argv 不进包。"""
    out = {}
    for key in _META_KEYS:
        if key not in meta:
            continue
        if key == "title":
            out["title"] = _title(meta.get("title"))
            continue
        if key == "error":
            continue
        out[key] = _json_safe(meta.get(key))
    if isinstance(meta.get("error"), str) and "Traceback" not in meta["error"]:
        text = meta["error"].strip().splitlines()[0][:240]
        if text:
            out["error"] = text
    if meta.get("imported") is True:
        out["imported"] = True
    if isinstance(meta.get("origin"), dict):
        out["origin"] = _json_safe(meta["origin"])
    out["id"] = meta.get("id")
    out["kind"] = meta.get("kind")
    out["status"] = meta.get("status")
    return out


def _title(value):
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\x00", " ").split())
    return text[:200]


def _json_safe(value, depth=0):
    if depth > 8:
        raise BundleError("too_big")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BundleError("manifest")
        return value
    if isinstance(value, str):
        if "\x00" in value or len(value) > 8000:
            raise BundleError("too_big")
        return value
    if isinstance(value, list):
        if len(value) > 400:
            raise BundleError("too_big")
        return [_json_safe(item, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 120:
            raise BundleError("too_big")
        out = {}
        for key, item in value.items():
            if not isinstance(key, str) or "\x00" in key or len(key) > 80:
                raise BundleError("manifest")
            out[key] = _json_safe(item, depth + 1)
        return out
    raise BundleError("manifest")


def _preset_bytes(meta, folder):
    """牌组预设是数据。读不到就省略，不因此失败。符号链接跳出去的不读。"""
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    preset = params.get("preset")
    if isinstance(preset, str) and _ID.fullmatch(preset.strip()):
        found = _preset_file(preset.strip())
        if found is not None:
            return found
    exp = os.path.join(folder, "experiment.yaml")
    if os.path.isfile(exp) and not os.path.islink(exp):
        try:
            return _read_inside(exp, folder, 1024 * 1024)
        except BundleError:
            return None
    return None


def _preset_file(preset_id):
    from gui import paths
    roots = []
    try:
        from sts2sim.deckpresets import DeckPresetError, presets_dir
        roots.append(presets_dir(create=False))
    except (DeckPresetError, OSError):
        pass
    roots.append(os.path.join(paths.SIM_ROOT, "experiments"))
    name = preset_id + ".yaml"
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        real = os.path.realpath(path)
        root_real = os.path.realpath(root)
        try:
            inside = os.path.normcase(os.path.commonpath([root_real, real])) == os.path.normcase(root_real)
        except ValueError:
            inside = False
        if not inside or os.path.normcase(real) == os.path.normcase(root_real):
            continue
        try:
            return _read_capped(real, 1024 * 1024)
        except BundleError:
            return None
    return None


def _html_for(rid, lang):
    meta, folder = _load_job(rid)
    from gui.backend import get_backend
    summary = get_backend().summarize(meta.get("kind"), folder)
    if not summary:
        raise BundleError("no_result")
    from sts2sim.htmlreport import render_html
    text = render_html(lang=lang, run={"meta": meta, "summary": summary})
    return text.encode("utf-8")


def _html_compare(left, right, lang):
    from sts2sim.runcompare import CompareError, compare_dirs
    left_dir = _jobs().run_dir(left["id"])
    right_dir = _jobs().run_dir(right["id"])
    out_a = os.path.join(left_dir, "out")
    out_b = os.path.join(right_dir, "out")
    try:
        body = compare_dirs(out_a if os.path.isdir(out_a) else left_dir, out_b if os.path.isdir(out_b) else right_dir)
    except CompareError as err:
        raise BundleError(err.code, **err.params) from err
    body["ok"] = True
    body["read_only"] = True
    body["kind"] = "combat"
    body["partial"] = bool(left.get("partial") or left.get("status") == "cancelled" or right.get("partial") or right.get("status") == "cancelled")
    body["a"] = _brief(left)
    body["b"] = _brief(right)
    from sts2sim.htmlreport import render_html
    return render_html(lang=lang, comparison=body).encode("utf-8")


def _brief(meta):
    brief = {key: meta.get(key) for key in ("id", "kind", "title", "status", "created")}
    brief["partial"] = bool(meta.get("partial") or meta.get("status") == "cancelled")
    return brief


def _pack(files, *, kind, run_ids):
    import sts2sim
    listed = []
    for path in sorted(files):
        data = files[path]
        if not isinstance(data, (bytes, bytearray)):
            raise BundleError("manifest")
        listed.append({
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
    manifest = {
        "format": FORMAT,
        "schema": SCHEMA,
        "deckbench": sts2sim.__version__,
        "kind": kind,
        "created": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs": list(run_ids),
        "files": listed,
    }
    blob = (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _writestr(archive, "manifest.json", blob)
        for path in sorted(files):
            _writestr(archive, path, bytes(files[path]))
    data = buf.getvalue()
    if len(data) > MAX_UPLOAD:
        raise BundleError("too_big")
    return data


def _writestr(archive, name, data):
    info = zipfile.ZipInfo(filename=name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


# ---------------------------------------------------------------- 读包
def _read_zip(data):
    if not isinstance(data, (bytes, bytearray)):
        raise BundleError("not_bundle")
    raw = bytes(data)
    if not raw or len(raw) > MAX_UPLOAD:
        raise BundleError("too_big" if raw else "not_bundle")
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as err:
        raise BundleError("not_bundle") from err
    members = {}
    total = 0
    try:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise BundleError("too_big")
        for info in infos:
            name = _member_name(info)
            if name in members:
                raise BundleError("manifest")
            if info.flag_bits & 0x1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise BundleError("not_bundle")
            if info.file_size > MAX_MEMBER or info.file_size < 0:
                raise BundleError("too_big")
            if total + info.file_size > MAX_TOTAL:
                raise BundleError("too_big")
            try:
                with archive.open(info, "r") as handle:
                    blob = _read_member(handle)
            except (zipfile.BadZipFile, RuntimeError, OSError) as err:
                raise BundleError("not_bundle") from err
            if len(blob) != info.file_size and info.file_size and len(blob) > MAX_MEMBER:
                raise BundleError("too_big")
            total += len(blob)
            if total > MAX_TOTAL:
                raise BundleError("too_big")
            members[name] = blob
    finally:
        archive.close()
    if "manifest.json" not in members:
        raise BundleError("manifest")
    return members


def _zip_name_fields(info):
    """原始名和规范化名都要看。

    Windows 上 ``ZipInfo`` 会把反斜杠换成 ``/`` 再放进 ``filename``，
    ``orig_filename`` 仍是包里的原字符串。只看 ``filename`` 时，
    ``runs\\solo\\meta.json`` 会变成合法成员，后面才因清单不合格变成 ``not_bundle``。
    """
    found = []
    for attr in ("orig_filename", "filename"):
        value = getattr(info, attr, None)
        if isinstance(value, bytes):
            value = value.decode("utf-8", "surrogateescape")
        if isinstance(value, str) and value not in found:
            found.append(value)
    return found


def _unsafe_zip_name(name):
    """反斜杠、``..``、绝对路径、盘符。在清单和允许名单之前判定。"""
    if not isinstance(name, str) or not name or "\x00" in name:
        return True
    if "\\" in name or ":" in name or name.startswith(("/", "\\")):
        return True
    parts = name.split("/")
    return any(part in ("", ".", "..") for part in parts)


def _member_name(info):
    mode = (getattr(info, "external_attr", 0) >> 16) & 0o170000
    if mode == 0o120000:
        raise BundleError("zip_slip")
    names = _zip_name_fields(info)
    if not names or any(_unsafe_zip_name(name) or len(name) > 180 for name in names):
        raise BundleError("zip_slip")
    name = info.filename
    if not isinstance(name, str) or not _MEMBER.fullmatch(name):
        raise BundleError("extra")
    return name


def _read_member(handle):
    chunks = []
    total = 0
    while True:
        block = handle.read(65536)
        if not block:
            break
        total += len(block)
        if total > MAX_MEMBER:
            raise BundleError("too_big")
        chunks.append(block)
    return b"".join(chunks)


def _manifest(members):
    blob = members.get("manifest.json")
    if blob is None or len(blob) > 1024 * 1024:
        raise BundleError("manifest")
    try:
        doc = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise BundleError("manifest") from err
    if not isinstance(doc, dict):
        raise BundleError("manifest")
    schema = doc.get("schema")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != SCHEMA:
        shown = schema if isinstance(schema, int) and not isinstance(schema, bool) else None
        raise BundleError("schema", schema=shown)
    if doc.get("format") != FORMAT:
        raise BundleError("not_bundle")
    if doc.get("kind") not in _KINDS:
        raise BundleError("manifest")
    version = doc.get("deckbench")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise BundleError("manifest")
    runs = doc.get("runs")
    if not isinstance(runs, list) or not runs or len(runs) > 400:
        raise BundleError("manifest")
    if any(not isinstance(item, str) or not _ID.fullmatch(item) for item in runs):
        raise BundleError("manifest")
    if len(set(runs)) != len(runs):
        raise BundleError("manifest")
    files = doc.get("files")
    if not isinstance(files, list) or not files or len(files) > MAX_MEMBERS:
        raise BundleError("manifest")
    seen = set()
    cleaned = []
    for row in files:
        if not isinstance(row, dict):
            raise BundleError("manifest")
        path = row.get("path")
        digest = row.get("sha256")
        size = row.get("bytes")
        if not isinstance(path, str) or not _MEMBER.fullmatch(path) or path == "manifest.json":
            raise BundleError("manifest")
        if path in seen:
            raise BundleError("manifest")
        seen.add(path)
        if not isinstance(digest, str) or not _HEX.fullmatch(digest):
            raise BundleError("manifest")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > MAX_MEMBER:
            raise BundleError("manifest")
        cleaned.append({"path": path, "sha256": digest, "bytes": size})
    if "report.html" not in seen:
        raise BundleError("incomplete")
    doc = dict(doc)
    doc["files"] = cleaned
    doc["runs"] = list(runs)
    return doc


def _check_hashes(members, manifest):
    listed = {row["path"]: row for row in manifest["files"]}
    names = set(members) - {"manifest.json"}
    if names != set(listed):
        extra = names - set(listed)
        missing = set(listed) - names
        if extra:
            raise BundleError("extra")
        if missing:
            raise BundleError("incomplete")
        raise BundleError("manifest")
    for path, row in listed.items():
        blob = members[path]
        if len(blob) != row["bytes"] or hashlib.sha256(blob).hexdigest() != row["sha256"]:
            raise BundleError("hash")


def _plan(members, manifest):
    """按清单把每个测试的文件配好。缺了 meta 或结果文件就是 incomplete。"""
    by_id = {rid: {} for rid in manifest["runs"]}
    for row in manifest["files"]:
        path = row["path"]
        if path == "report.html":
            continue
        match = _MEMBER.fullmatch(path)
        rid = match.group("id") if match else None
        if rid not in by_id:
            raise BundleError("incomplete")
        by_id[rid][path.rsplit("/", 1)[-1]] = members[path]
    runs = []
    for rid in manifest["runs"]:
        files = by_id[rid]
        if "meta.json" not in files:
            raise BundleError("incomplete")
        try:
            meta = json.loads(files["meta.json"].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as err:
            raise BundleError("manifest") from err
        if not isinstance(meta, dict):
            raise BundleError("manifest")
        if meta.get("id") != rid or meta.get("kind") not in _RUN_KINDS:
            raise BundleError("manifest")
        if meta.get("status") not in ("done", "cancelled"):
            raise BundleError("not_done")
        kind = meta["kind"]
        if kind == "combat" and "raw.jsonl" not in files:
            raise BundleError("incomplete")
        if kind == "batch" and "runs.jsonl" not in files:
            raise BundleError("incomplete")
        if kind == "card_impact" and "card_impact.json" not in files:
            raise BundleError("incomplete")
        runs.append({"id": rid, "meta": meta, "files": files})
    kind = manifest["kind"]
    if kind == "run" and (len(runs) != 1 or runs[0]["meta"]["kind"] == "card_impact"):
        raise BundleError("manifest")
    if kind in ("compare", "head_to_head") and (len(runs) != 2 or any(row["meta"]["kind"] != "combat" for row in runs)):
        raise BundleError("manifest")
    if kind == "card_impact":
        if len(runs) < 2 or runs[0]["meta"]["kind"] != "card_impact":
            raise BundleError("manifest")
        if any(row["meta"]["kind"] != "combat" for row in runs[1:]):
            raise BundleError("manifest")
    return {"runs": runs, "report": members["report.html"]}


def _install(plan, manifest, *, filename):
    from gui import paths
    root = os.path.realpath(paths.RUNS_DIR)
    os.makedirs(root, exist_ok=True)
    id_map = {}
    claimed = []
    reserved = set()
    try:
        for row in plan["runs"]:
            new_id, folder, renamed = _claim(row["id"], reserved, root)
            reserved.add(new_id)
            id_map[row["id"]] = new_id
            claimed.append((row, new_id, folder, renamed))
        installed = []
        for row, new_id, folder, renamed in claimed:
            _write_run(folder, row, new_id, id_map, manifest, plan["report"], filename)
            installed.append({
                "id": new_id,
                "original_id": row["id"],
                "kind": row["meta"].get("kind"),
                "renamed": renamed,
                "imported": True,
            })
    except (BundleError, OSError, ValueError, UnicodeError):
        for _row, _new_id, folder, _renamed in claimed:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    return {
        "ok": True,
        "kind": manifest["kind"],
        "schema": SCHEMA,
        "deckbench": manifest.get("deckbench") or "",
        "runs": installed,
    }


def _claim(preferred, reserved, root):
    candidates = []
    if preferred not in reserved and not os.path.lexists(os.path.join(root, preferred)):
        candidates.append(preferred)
    for _ in range(8):
        if not candidates:
            stem = preferred[:48].rstrip("-.") or "run"
            candidates.append(stem + "-" + secrets.token_hex(2))
        rid = candidates.pop(0)
        if rid in reserved or not _ID.fullmatch(rid) or os.path.lexists(os.path.join(root, rid)):
            continue
        folder = os.path.join(root, rid)
        try:
            os.makedirs(folder)
        except FileExistsError:
            continue
        real = os.path.realpath(folder)
        try:
            inside = os.path.normcase(os.path.commonpath([root, real])) == os.path.normcase(root)
        except ValueError:
            inside = False
        if not inside or os.path.normcase(real) == os.path.normcase(root):
            shutil.rmtree(folder, ignore_errors=True)
            raise BundleError("zip_slip")
        return rid, real, rid != preferred
    raise BundleError("manifest")


def _write_run(folder, row, new_id, id_map, manifest, report, filename):
    """只写固定的文件名。内容是 JSON 或原始字节，不加载、不执行。"""
    meta = _public_meta(row["meta"])
    meta["id"] = new_id
    meta["imported"] = True
    origin = {
        "source": "bundle",
        "schema": SCHEMA,
        "deckbench": manifest.get("deckbench") or "",
        "bundle_kind": manifest.get("kind") or "",
        "original_id": row["id"],
        "imported_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    cleaned = _upload_name(filename)
    if cleaned:
        origin["filename"] = cleaned
    previous = row["meta"].get("origin")
    if isinstance(previous, dict):
        kept = {}
        for key in ("source", "schema", "deckbench", "bundle_kind", "original_id", "imported_at"):
            if key in previous and isinstance(previous[key], (str, int)) and not isinstance(previous[key], bool):
                kept[key] = previous[key]
        if kept:
            origin["previous"] = kept
    meta["origin"] = origin
    if not isinstance(meta.get("headline"), dict):
        filled = _fill_headline(meta.get("kind"), row["files"])
        if filled:
            meta["headline"] = filled
    _write_bytes(os.path.join(folder, "meta.json"), (json.dumps(meta, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    files = row["files"]
    if "raw.jsonl" in files:
        _write_bytes(os.path.join(folder, "out", "raw.jsonl"), files["raw.jsonl"])
    if "runs.jsonl" in files:
        _write_bytes(os.path.join(folder, "runs.jsonl"), files["runs.jsonl"])
    if "preset.yaml" in files:
        _write_bytes(os.path.join(folder, "preset.yaml"), files["preset.yaml"])
    if "card_impact.json" in files:
        rewritten = _rewrite_ids(json.loads(files["card_impact.json"].decode("utf-8")), id_map)
        _write_bytes(
            os.path.join(folder, "card_impact.json"),
            (json.dumps(rewritten, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
        )
    _write_bytes(os.path.join(folder, "report.html"), report)


def _rewrite_ids(node, id_map, key=None):
    if isinstance(node, dict):
        return {name: _rewrite_ids(value, id_map, name) for name, value in node.items()}
    if isinstance(node, list):
        return [_rewrite_ids(value, id_map, key) for value in node]
    if isinstance(node, str) and key in _ID_KEYS and node in id_map:
        return id_map[node]
    return node


def _fill_headline(kind, files):
    """列表上的胜率摘要。只数已经校验过的 JSON，不开模拟。原来的 headline 还在时不走这里。"""
    try:
        if kind == "combat" and "raw.jsonl" in files:
            return _combat_headline(files["raw.jsonl"])
        if kind == "batch" and "runs.jsonl" in files:
            return _batch_headline(files["runs.jsonl"])
    except (UnicodeError, json.JSONDecodeError, ValueError):
        return None
    return None


def _jsonl_rows(blob):
    rows = []
    for line in blob.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _combat_headline(blob):
    rows = _jsonl_rows(blob)
    if not rows:
        return None
    wins = 0
    for row in rows:
        if row.get("result") == "win" or row.get("victory") is True:
            wins += 1
    return {"fights": len(rows), "win": wins / len(rows), "cells": 0}


def _batch_headline(blob):
    rows = _jsonl_rows(blob)
    if not rows:
        return None
    wins = sum(1 for row in rows if row.get("victory") is True)
    return {"n": len(rows), "win": wins / len(rows)}


def _upload_name(filename):
    base = os.path.basename(str(filename or "").replace("\\", "/"))
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in "\x00/\\")
    return cleaned[:80]


def _write_bytes(path, data):
    """按字节写。文本模式会在 Windows 上改换行，清单里的 SHA-256 就不再跨平台。"""
    if isinstance(data, str):
        raise BundleError("manifest")
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)


def _write_out(out, filename, data):
    if not isinstance(out, str) or "\x00" in out:
        raise BundleError("bad_type", field="out")
    text = out.strip()
    from sts2sim.analysis import _gui_data_root
    if not text:
        root = _gui_data_root()
        os.makedirs(root, exist_ok=True)
        folder = os.path.join(root, "exports")
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, filename)
    else:
        dest = os.path.abspath(os.path.expanduser(text))
        if os.path.isdir(dest):
            dest = os.path.join(dest, filename)
        elif not dest.lower().endswith(".zip"):
            dest += ".deckbench.zip"
    _reject_save(dest)
    from sts2sim.saveimport import SaveImportError, refuse_save_write
    try:
        dest = refuse_save_write(dest)
    except SaveImportError as err:
        raise BundleError("refuse_write") from err
    if not _under_allowed(dest):
        raise BundleError("path_not_allowed")
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = dest + ".tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, dest)
    except OSError as err:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise BundleError("refuse_write") from err
    return os.path.realpath(dest)


def _reject_save(dest):
    parts = {part.lower() for part in dest.split(os.sep)}
    if parts & _SAVE_PARTS:
        raise BundleError("refuse_write")


def _under_allowed(dest):
    from sts2sim.analysis import _matching_root
    probe = dest if os.path.exists(dest) else os.path.dirname(dest)
    while probe and probe != os.path.dirname(probe):
        if os.path.isdir(probe) and _matching_root(probe):
            return True
        probe = os.path.dirname(probe)
    return False


def _error_json(err):
    body = {"ok": False, "error": err.code, "message": message(err)}
    schema = (err.params or {}).get("schema")
    if isinstance(schema, int) and not isinstance(schema, bool):
        body["schema"] = schema
        body["supported"] = SCHEMA
    return json.dumps(body, ensure_ascii=False) + "\n"
