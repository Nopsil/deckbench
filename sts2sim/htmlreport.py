"""把已经跑完的结果写成一份自包含的 HTML。

页面里的 CSS 和 SVG 都写在文件里。没有脚本，没有会去访问网络的地址。
双击用浏览器打开即可。不新开模拟，不改种子，不改 AI。

一份报告可以包含：

- 一次已完成的测试（整局或战斗实验）
- 两次战斗实验的格子 / 单卡对比（和 ``GET /api/runs/compare`` 同一份数）
- 一份校准结果，以及由它算出的缺口分诊（或一份已经分诊好的 JSON）

A finished run, an optional combat comparison, and an optional calibration or
gap-triage result become one offline HTML file. Inline CSS, inline SVG, no
network loads.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys

from sts2sim.analysis import AnalysisError, _gui_data_root, _is_run_id, resolve_read

_SAVE_PARTS = ("saves", "history", "slaythespire2")
_COMBAT_FILES = ("raw.jsonl", "cells.csv", "cards.csv")
_HTML_LANG = {"zhs": "zh-CN", "en": "en", "ja": "ja", "ko": "ko"}
_METRIC_KEY = {
    "win": "cmp.win",
    "timeout": "cmp.timeout",
    "turns": "cmp.turns",
    "hp_loss": "cmp.hpLoss",
    "dpt": "cmp.dpt",
}
_HIGHER = {"win", "dpt", "efficiency", "usage"}
_LOWER = {"timeout", "turns", "hp_loss"}
_CELL_METRICS = ("win", "timeout", "turns", "hp_loss", "dpt")
_ROW_CAP = 80
_CARD_CAP = 40
_FIGHT_CAP = 40
_BAR_CAP = 12


class ExportError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def parse_lang(raw):
    """空字符串表示用当前界面语言。认不出的标记是 bad_lang，不回显原文。

    和请求头 x-lang 共用 gui.i18n.request_lang。
    """
    if not isinstance(raw, str) or "\x00" in raw:
        raise ExportError("bad_type", field="lang")
    from gui import i18n
    chosen = i18n.request_lang(raw)
    if raw.strip() and not chosen:
        raise ExportError("bad_lang", field="lang")
    return chosen


def export_filename(run_id="", a="", b="", calibration=False):
    if a or b:
        stem = "deckbench-compare-" + _slug(a) + "-" + _slug(b)
    elif run_id:
        stem = "deckbench-run-" + _slug(run_id)
    elif calibration:
        stem = "deckbench-calibration"
    else:
        stem = "deckbench-report"
    return stem[:96] + ".html"


def content_disposition(filename):
    """attachment，带 ASCII 文件名和 UTF-8 的 filename*。"""
    ascii_name = "".join(ch if ch.isascii() and ch not in '"\\' else "-" for ch in filename)
    ascii_name = ascii_name.strip(".-") or "deckbench-report.html"
    if not ascii_name.lower().endswith(".html"):
        ascii_name += ".html"
    from urllib.parse import quote
    return "attachment; filename=\"" + ascii_name + "\"; filename*=UTF-8''" + quote(filename, safe="")


def render_html(*, lang, run=None, comparison=None, calibration=None, gap=None):
    """返回完整的 HTML 文本。四段都空着是 need_input。"""
    from gui import i18n
    lang = lang if lang in i18n.LANGS else i18n.current()
    parts = []
    if run:
        parts.append(_run_section(run, lang))
    if comparison:
        parts.append(_compare_section(comparison, lang))
    if calibration:
        parts.append(_cal_section(calibration, lang))
    if gap:
        parts.append(_gap_section(gap, lang))
    if not parts:
        raise ExportError("need_input")
    title = _page_title(run, comparison, calibration, lang)
    html_lang = _HTML_LANG.get(lang, "en")
    body = (
        "<header><div class=\"mark\" aria-hidden=\"true\"></div><div>"
        "<p class=\"brand\">DeckBench</p>"
        "<h1>" + _esc(title) + "</h1>"
        "<p class=\"lead\">" + _esc(_t(lang, "export.offline")) + "</p>"
        "<p class=\"lead faint\">" + _esc(_t(lang, "export.generated")) + "</p>"
        "</div></header><main>"
        + "".join(parts)
        + "</main><footer>" + _esc(_t(lang, "export.footer")) + "</footer>"
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"" + html_lang + "\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"generator\" content=\"DeckBench\">\n"
        "<meta name=\"referrer\" content=\"no-referrer\">\n"
        "<title>" + _esc(title) + "</title>\n<style>\n" + _CSS + "</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


def load_run(token):
    """界面测试 id，或允许目录里的运行目录 / runs.jsonl / 战斗输出。"""
    if not isinstance(token, str) or not token.strip() or "\x00" in token:
        raise ExportError("bad_type", field="run")
    text = token.strip()
    if _is_run_id(text):
        candidate = os.path.join(_gui_data_root(), "runs", text)
        if os.path.isdir(candidate):
            return _run_from_dir(resolve_read(candidate))
        if not os.path.exists(text):
            raise AnalysisError("not_found", path=text)
    real = resolve_read(text)
    if os.path.isdir(real):
        return _run_from_dir(real)
    return _run_from_file(real)


def load_side_report(path):
    """校准 JSON → (校准, 分诊)。已经是分诊 JSON → (None, 分诊)。"""
    doc = _read_json_file(path)
    if _is_calibration(doc):
        return doc, _triage_one(doc)
    if _is_gap(doc):
        return None, doc
    raise ExportError("not_calibration")


def write_export(run="", a="", b="", calibration="", out="", lang="", *, restricted_out=True):
    """写出 HTML，返回 (绝对路径, 文件名)。失败不留半截文件。"""
    html_text, filename, sources = build_html(
        run=run, a=a, b=b, calibration=calibration, lang=lang,
    )
    dest = _destination(out, filename, restricted=restricted_out, sources=sources)
    tmp = dest + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(html_text)
        os.replace(tmp, dest)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ExportError("refuse_write", path=os.path.basename(dest))
    return os.path.realpath(dest), filename


def build_html(run="", a="", b="", calibration="", lang=""):
    """校验参数并渲染。返回 (html, filename, 读过的源路径)。"""
    run, a, b, calibration, lang = _check_args(run, a, b, calibration, lang)
    if not run and not a and not b and not calibration:
        raise ExportError("need_input")
    if bool(a) != bool(b):
        raise ExportError("missing", field="b" if a else "a")
    from gui import i18n
    chosen = lang or i18n.current()
    run_payload = load_run(run) if run else None
    comparison = _load_compare(a, b) if a and b else None
    sources = []
    cal_doc = None
    gap_doc = None
    if calibration:
        real = resolve_read(calibration.strip())
        cal_doc, gap_doc = load_side_report(real)
        sources.append(real)
    if run_payload is None and comparison is None and cal_doc is None and gap_doc is None:
        raise ExportError("need_input")
    text = render_html(
        lang=chosen, run=run_payload, comparison=comparison, calibration=cal_doc, gap=gap_doc,
    )
    run_id = ""
    if run_payload:
        run_id = str((run_payload.get("meta") or {}).get("id") or run)
    filename = export_filename(run_id=run_id, a=a, b=b, calibration=bool(cal_doc or gap_doc) and not run_id and not a)
    return text, filename, sources


def export_report_json(run="", a="", b="", calibration="", out="", lang=""):
    """MCP 用。成功时 JSON 里的 path 是写好的 HTML。失败也是 JSON，没有堆栈。"""
    try:
        path, filename = write_export(
            run=run, a=a, b=b, calibration=calibration, out=out, lang=lang, restricted_out=True,
        )
    except (ExportError, AnalysisError) as err:
        return _error_json(err)
    body = {"ok": True, "path": path, "filename": filename}
    return json.dumps(body, ensure_ascii=False) + "\n"


def main(argv=None):
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="", help="已完成的测试 id，或运行目录 / runs.jsonl / 战斗输出")
    parser.add_argument("--a", default="", help="对比的基线。和 --b 一起用")
    parser.add_argument("--b", default="", help="对比的另一份。差值是 B − A")
    parser.add_argument("--calibration", default="", help="校准 JSON，或已经分诊好的 JSON")
    parser.add_argument("--lang", default="", help="zhs / en / ja / ko，或 zh-CN / en-US / ja / ko")
    parser.add_argument("--out", default="", help="写出的 .html。- 表示只打到标准输出。缺省写到界面数据目录的 exports/")
    args = parser.parse_args(argv)
    try:
        if args.out == "-":
            text, _filename, _sources = build_html(
                run=args.run, a=args.a, b=args.b, calibration=args.calibration, lang=args.lang,
            )
            sys.stdout.write(text)
            return 0
        path, _filename = write_export(
            run=args.run, a=args.a, b=args.b, calibration=args.calibration,
            out=args.out, lang=args.lang, restricted_out=False,
        )
    except (ExportError, AnalysisError) as err:
        print(_cli_message(err, args.lang), file=sys.stderr)
        return 2
    sys.stdout.write(path + "\n")
    return 0


# ---------------------------------------------------------------- 读结果
def _check_args(run, a, b, calibration, lang):
    checked = []
    for field, value in (("run", run), ("a", a), ("b", b), ("calibration", calibration), ("out_lang", lang)):
        if not isinstance(value, str) or "\x00" in value:
            name = "lang" if field == "out_lang" else field
            raise ExportError("bad_type", field=name)
        checked.append(value.strip())
    run_s, a_s, b_s, cal_s, lang_s = checked
    chosen = parse_lang(lang_s)
    return run_s, a_s, b_s, cal_s, chosen or ""


def _run_from_file(real):
    base = os.path.basename(real).lower()
    folder = os.path.dirname(real)
    if base == "runs.jsonl":
        return _batch_payload(folder, real, _read_meta(folder))
    if base in _COMBAT_FILES:
        run_dir = os.path.dirname(folder) if os.path.basename(folder) == "out" else folder
        return _combat_payload(folder, run_dir, _read_meta(run_dir))
    raise ExportError("no_result")


def _run_from_dir(real):
    if os.path.isfile(real):
        return _run_from_file(real)
    meta = _read_meta(real)
    kind = meta.get("kind")
    if kind == "card_impact":
        return _impact_payload(real, meta)
    out = os.path.join(real, "out")
    has_combat = os.path.isdir(out) or any(os.path.isfile(os.path.join(real, name)) for name in _COMBAT_FILES)
    has_batch = os.path.isfile(os.path.join(real, "runs.jsonl"))
    if kind == "combat" or (has_combat and kind != "batch"):
        folder = out if os.path.isdir(out) else real
        return _combat_payload(folder, real, meta)
    if kind == "batch" or has_batch:
        return _batch_payload(real, os.path.join(real, "runs.jsonl"), meta)
    if meta:
        raise ExportError("no_result")
    raise AnalysisError("not_found", path=real)


def _read_meta(run_dir):
    path = os.path.join(run_dir, "meta.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            meta = json.loads(handle.read())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _marked_partial(value):
    if not isinstance(value, dict):
        return False
    return bool(value.get("partial") or value.get("status") == "cancelled")


def _ensure_done(meta):
    status = meta.get("status") if isinstance(meta, dict) else None
    if isinstance(status, str) and status not in ("done", "cancelled"):
        raise AnalysisError("not_done", field="run")


def _guard_size(path):
    from sts2sim import saveimport
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise AnalysisError("not_found", path=path) from exc
    if size > saveimport.MAX_BYTES:
        raise AnalysisError("too_big", path=path)


def _batch_payload(run_dir, jsonl, meta):
    _ensure_done(meta)
    if not os.path.isfile(jsonl):
        raise ExportError("no_result")
    _guard_size(jsonl)
    from gui.metrics import batch_summary, load_jsonl
    try:
        rows = load_jsonl(jsonl)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError("not_json", path=jsonl) from exc
    summary = batch_summary(rows)
    if not isinstance(summary, dict):
        raise ExportError("no_result")
    meta = dict(meta or {})
    meta.setdefault("kind", "batch")
    meta.setdefault("id", os.path.basename(run_dir))
    meta.setdefault("status", "done")
    return {"meta": meta, "summary": summary}


def _impact_payload(run_dir, meta):
    _ensure_done(meta)
    path = os.path.join(run_dir, "card_impact.json")
    if not os.path.isfile(path):
        raise ExportError("no_result")
    _guard_size(path)
    try:
        with open(path, encoding="utf-8") as handle:
            summary = json.loads(handle.read())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportError("no_result") from exc
    if not isinstance(summary, dict):
        raise ExportError("no_result")
    meta = dict(meta or {})
    meta.setdefault("kind", "card_impact")
    meta.setdefault("id", os.path.basename(run_dir.rstrip(os.sep)) or "card-impact")
    meta.setdefault("status", summary.get("status") or "done")
    return {"meta": meta, "summary": summary}


def _combat_payload(out_dir, run_dir, meta):
    _ensure_done(meta)
    present = [name for name in _COMBAT_FILES if os.path.isfile(os.path.join(out_dir, name))]
    if not present:
        raise ExportError("no_result")
    for name in present:
        _guard_size(os.path.join(out_dir, name))
    from gui.metrics import combat_summary
    summary = combat_summary(out_dir)
    if not isinstance(summary, dict):
        raise ExportError("no_result")
    meta = dict(meta or {})
    meta.setdefault("kind", "combat")
    meta.setdefault("id", os.path.basename(run_dir.rstrip(os.sep)) or "combat")
    meta.setdefault("status", "done")
    return {"meta": meta, "summary": summary}


def _load_compare(a, b):
    from sts2sim.analysis import compare_runs
    return compare_runs(a, b)


def _read_json_file(path):
    from sts2sim import saveimport
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ExportError("bad_type", field="calibration")
    real = resolve_read(path.strip())
    if not os.path.isfile(real):
        raise ExportError("not_calibration")
    try:
        size = os.path.getsize(real)
    except OSError as exc:
        raise AnalysisError("not_found", path=real) from exc
    if size > saveimport.MAX_BYTES:
        raise AnalysisError("too_big", path=real)
    try:
        with open(real, encoding="utf-8-sig") as handle:
            doc = json.load(handle)
    except UnicodeDecodeError as exc:
        raise AnalysisError("not_json", path=real) from exc
    except json.JSONDecodeError as exc:
        raise AnalysisError("not_json", path=real) from exc
    except OSError as exc:
        raise AnalysisError("not_found", path=real) from exc
    if not isinstance(doc, dict):
        raise ExportError("not_calibration")
    return doc


def _is_calibration(doc):
    fights = doc.get("fights")
    if not isinstance(fights, list):
        return False
    return "sim_matched" in doc or "deck_path" in doc or doc.get("alignment") == "floor_room_encounter"


def _is_gap(doc):
    counts = doc.get("counts")
    return isinstance(counts, dict) and "compared" in counts and isinstance(doc.get("by_power"), list)


def _triage_one(doc):
    mod = _gap_mod()
    try:
        return mod.triage_reports([doc])
    except mod.TriageError as exc:
        raise ExportError(exc.code, **getattr(exc, "params", {})) from exc


def _gap_mod():
    import importlib.util
    name = "deckbench_gap_triage_export"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "gap_triage.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _destination(out, filename, *, restricted, sources):
    if not isinstance(out, str) or "\x00" in out:
        raise ExportError("bad_type", field="out")
    text = out.strip()
    if text == "-":
        raise ExportError("bad_type", field="out")
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
        elif not dest.lower().endswith(".html"):
            dest += ".html"
    _reject_save_parts(dest)
    from sts2sim.saveimport import SaveImportError, refuse_save_write
    try:
        dest = refuse_save_write(dest)
    except SaveImportError as exc:
        raise ExportError("refuse_write", path=os.path.basename(dest)) from exc
    if restricted and not _under_allowed(dest):
        raise AnalysisError("path_not_allowed", path=dest)
    for src in sources:
        if src and os.path.isfile(src) and os.path.realpath(src) == os.path.realpath(dest):
            raise ExportError("refuse_write", path=os.path.basename(dest))
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return dest


def _reject_save_parts(dest):
    parts = [part.lower() for part in dest.split(os.sep)]
    if any(part in _SAVE_PARTS for part in parts):
        raise ExportError("refuse_write", path=os.path.basename(dest))


def _under_allowed(dest):
    from sts2sim.analysis import _matching_root
    probe = dest if os.path.exists(dest) else os.path.dirname(dest)
    while probe and probe != os.path.dirname(probe):
        if os.path.isdir(probe) and _matching_root(probe):
            return True
        probe = os.path.dirname(probe)
    return False


def _error_json(err):
    body = {"ok": False, "error": getattr(err, "code", "failed")}
    for key, value in getattr(err, "params", {}).items():
        if value is None or isinstance(value, (str, int, float, bool)):
            body[key] = value
    return json.dumps(body, ensure_ascii=False) + "\n"


def _cli_message(err, lang_raw):
    from gui import i18n
    try:
        lang = parse_lang(lang_raw) if lang_raw else None
    except ExportError:
        lang = None
    lang = lang or i18n.current()
    code = getattr(err, "code", "")
    params = getattr(err, "params", {}) or {}
    if isinstance(err, ExportError):
        if code == "bad_lang":
            return _t(lang, "export.err.badLang")
        if code == "need_input":
            return _t(lang, "export.err.need")
        if code == "no_result":
            return _t(lang, "export.err.noResult")
        if code == "not_calibration":
            return _t(lang, "gap.err.not_calibration")
        if code == "missing":
            return _t(lang, "api.err.missing", field=params.get("field") or "request")
        if code == "bad_type":
            return _t(lang, "api.err.bad_type", field=params.get("field") or "request", expected=_t(lang, "api.type.string"))
        if code == "refuse_write":
            return _t(lang, "exp.err.refuse_write", path=params.get("path") or "")
    if code == "path_not_allowed":
        return _t(lang, "exp.err.path_not_allowed", path=params.get("path") or "")
    if code == "not_found":
        return _t(lang, "exp.err.not_found", path=params.get("path") or "")
    if code == "not_json":
        return _t(lang, "gap.err.not_json", path=params.get("path") or "")
    if code == "too_big":
        return _t(lang, "imp.err.too_big")
    if code == "not_done":
        return _t(lang, "err.notDone")
    if code == "not_combat":
        return _t(lang, "err.compareCombat")
    if code == "same_run":
        return _t(lang, "err.compareSame")
    if code == "no_data":
        return _t(lang, "err.compareNoData")
    return code or "failed"


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------- 页面
def _t(lang, key, **kwargs):
    from gui import i18n
    return i18n.t(key, lang, **kwargs)


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _plain(value, digits=2):
    number = _num(value)
    if number is None:
        return "—"
    if digits == 0:
        return str(round(number))
    return f"{number:.{digits}f}"


def _pct(value):
    number = _num(value)
    if number is None:
        return "—"
    return f"{number * 100:.1f}%"


def _signed_pct(value):
    number = _num(value)
    if number is None:
        return "—"
    return f"{number * 100:+.1f}%"


def _signed_plain(value):
    number = _num(value)
    if number is None:
        return "—"
    return f"{number:+.2f}"


def _clip(text, limit):
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _slug(text):
    raw = str(text or "")
    out = []
    for ch in raw:
        if ch.isascii() and (ch.isalnum() or ch in "._-"):
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out).strip(".-")
    return (slug or "report")[:40]


def _secs(value, lang):
    number = _num(value)
    if number is None:
        return "—"
    seconds = round(number)
    if seconds < 60:
        return _t(lang, "fmt.secs", s=seconds)
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return _t(lang, "fmt.minSecs", m=minutes, s=seconds)
    hours, minutes = divmod(minutes, 60)
    return _t(lang, "fmt.hourMins", h=hours, m=minutes)


def _room(value, lang):
    from gui import i18n
    return i18n.tr("room.", value, lang)


def _page_title(run, comparison, calibration, lang):
    base = _t(lang, "export.pageTitle")
    if run:
        title = _run_title(run.get("meta") or {})
        if title:
            return base + " — " + title
    if comparison:
        left = _side_name(comparison.get("a"), "A")
        right = _side_name(comparison.get("b"), "B")
        return base + " — " + left + " / " + right
    if isinstance(calibration, dict) and calibration.get("seed"):
        return base + " — " + str(calibration.get("seed"))
    return base


def _run_title(meta):
    title = meta.get("title") if isinstance(meta, dict) else None
    if isinstance(title, str) and title.strip():
        return title.strip()
    ident = meta.get("id") if isinstance(meta, dict) else None
    return str(ident) if ident else ""


def _side_name(side, fallback):
    if isinstance(side, dict):
        title = side.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        ident = side.get("id")
        if ident:
            return str(ident)
    if isinstance(side, str) and side.strip():
        return os.path.basename(side.rstrip("/\\")) or fallback
    return fallback


def _section(anchor, title, inner):
    return "<section id=\"" + anchor + "\"><h2>" + _esc(title) + "</h2>" + inner + "</section>"


def _stats(pairs):
    cards = []
    for label, value in pairs:
        cards.append(
            "<div class=\"stat\"><div class=\"k\">" + _esc(label) + "</div><div class=\"v\">"
            + _esc(value) + "</div></div>"
        )
    return "<div class=\"stats\">" + "".join(cards) + "</div>"


def _chips(items):
    spans = ["<span class=\"chip\">" + _esc(item) + "</span>" for item in items if item]
    if not spans:
        return ""
    return "<div class=\"chips\">" + "".join(spans) + "</div>"


def _note(text, warn=False):
    cls = "note warn" if warn else "note"
    return "<p class=\"" + cls + "\">" + _esc(text) + "</p>"


def _table(headers, rows):
    head = "".join("<th>" + _esc(cell) + "</th>" for cell in headers)
    body = []
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, tuple):
                text, cls = cell
                cells.append("<td class=\"" + _esc(cls) + "\">" + _esc(text) + "</td>")
            else:
                cells.append("<td>" + _esc(cell) + "</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return "<div class=\"scroll\"><table><thead><tr>" + head + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"


def _run_section(run, lang):
    meta = run.get("meta") if isinstance(run.get("meta"), dict) else {}
    summary = run.get("summary") if isinstance(run.get("summary"), dict) else {}
    kind = meta.get("kind")
    inner = ["<h3>" + _esc(_run_title(meta) or _t(lang, "export.sectionRun")) + "</h3>"]
    if _marked_partial(meta):
        inner.append(_note(_t(lang, "export.partial")))
    inner.append(_chips(_run_chips(meta, lang)))
    if kind == "card_impact" or summary.get("method") == "leave_one_out":
        inner.append(_impact_block(summary, lang))
    elif kind == "combat":
        inner.append(_combat_block(summary, lang))
    else:
        inner.append(_batch_block(summary, lang))
    return _section("run", _t(lang, "export.sectionRun"), "".join(inner))


def _run_chips(meta, lang):
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    kind = meta.get("kind")
    chips = []
    if kind in ("batch", "combat", "card_impact"):
        chips.append(_t(lang, "kind." + kind))
    if params.get("char"):
        chips.append(str(params.get("char")))
    if kind == "batch" and params.get("asc") is not None:
        chips.append("A" + str(params.get("asc")))
    if kind == "batch" and params.get("n") is not None:
        chips.append(_t(lang, "chip.nRuns", n=params.get("n")))
    if params.get("agent"):
        chips.append(str(params.get("agent")))
    if params.get("preset") or (kind == "card_impact" and params.get("deck")):
        chips.append(_t(lang, "chip.preset", id=params.get("preset") or params.get("deck")))
    if params.get("fights") is not None and kind == "combat":
        chips.append(_t(lang, "chip.perCell", n=params.get("fights")))
    seed = params.get("game_seed") or params.get("seed")
    if seed is not None and seed != "":
        chips.append(_t(lang, "chip.seed", s=seed))
    if meta.get("created"):
        chips.append(str(meta.get("created")))
    return chips


def _impact_name(row, lang):
    if not isinstance(row, dict):
        return ""
    if lang == "zhs":
        text = row.get("name_zh") or row.get("name") or row.get("card_id") or ""
    else:
        text = row.get("name_en") or row.get("name") or row.get("card_id") or ""
    text = str(text)
    if row.get("upgrade") and text and not text.endswith("+"):
        text += "+"
    return text


def _impact_change(row, lang):
    change = row.get("change")
    if change == "add":
        return _t(lang, "deck.impactAdd")
    if change == "remove":
        return _t(lang, "deck.impactRemove")
    return str(change or "")


def _impact_flag(row, lang):
    if not row.get("noisy"):
        return "—"
    if row.get("noisy_reason") == "wilson_overlap":
        return _t(lang, "deck.impactOverlap")
    return _t(lang, "deck.impactTooSmall")


def _impact_effect(code, lang):
    if code == "helps":
        return _t(lang, "deck.impactHelps")
    if code == "hurts":
        return _t(lang, "deck.impactHurts")
    if code == "flat":
        return _t(lang, "deck.impactFlat")
    return ""


def _impact_block(summary, lang):
    parts = ["<h3>" + _esc(_t(lang, "export.impactTitle")) + "</h3>"]
    parts.append(_note(_t(lang, "export.impactNote", min=summary.get("min_n") or 30)))
    if summary.get("scaled"):
        parts.append(_note(_t(
            lang, "deck.impactScaled", n=summary.get("fights") or 0, cap=summary.get("cap") or 400,
        ), warn=True))
    baseline = summary.get("baseline") if isinstance(summary.get("baseline"), dict) else None
    if baseline:
        parts.append(_stats([
            (_t(lang, "deck.impactN"), str(baseline.get("wins")) + " / " + str(baseline.get("n"))),
            (_t(lang, "cmp.win"), _pct(baseline.get("win_rate"))),
            (_t(lang, "cmp.hpLoss"), _plain(baseline.get("hp_lost"), 1)),
            (_t(lang, "cmp.turns"), _plain(baseline.get("turns"), 1)),
        ]))
    rows = [row for row in (summary.get("rows") or []) if isinstance(row, dict)]
    rows.sort(key=lambda row: (_num(row.get("delta_win")) is None, -(_num(row.get("delta_win")) or 0)))
    body = []
    for row in rows:
        win = _signed_pct(row.get("delta_win"))
        effect = _impact_effect(row.get("win_effect"), lang)
        if effect:
            win = win + " (" + effect + ")"
        hp = _signed_plain(row.get("delta_hp_lost"))
        hp_effect = _impact_effect(row.get("hp_effect"), lang)
        if hp_effect:
            hp = hp + " (" + hp_effect + ")"
        body.append([
            _impact_name(row, lang),
            _impact_change(row, lang),
            str(row.get("n") if row.get("n") is not None else "—"),
            win,
            hp,
            _signed_plain(row.get("delta_turns")),
            _impact_flag(row, lang),
        ])
    parts.append(_table([
        _t(lang, "deck.impactCard"),
        _t(lang, "deck.impactChange"),
        _t(lang, "deck.impactN"),
        _t(lang, "deck.impactDeltaWin"),
        _t(lang, "deck.impactDeltaHp"),
        _t(lang, "deck.impactDeltaTurns"),
        _t(lang, "deck.impactNoisy"),
    ], body) if body else _note(_t(lang, "deck.impactEmpty")))
    return "".join(parts)


def _batch_block(summary, lang):
    parts = []
    wins = summary.get("wins")
    count = summary.get("n")
    stats = [
        (_t(lang, "rep.winRate"), _pct(summary.get("win"))),
        (_t(lang, "rep.avgFloor"), _plain(summary.get("avg_floor"))),
        (_t(lang, "metric.boss1"), _pct(summary.get("boss1"))),
        (_t(lang, "metric.act2"), _pct(summary.get("act2"))),
        (_t(lang, "metric.act3"), _pct(summary.get("act3"))),
        (_t(lang, "common.elapsed"), _secs(summary.get("avg_secs"), lang)),
    ]
    parts.append(_stats(stats))
    sub = []
    if wins is not None and count is not None:
        sub.append(_t(lang, "rep.xOfN", x=wins, n=count))
    if summary.get("win_ci_low") is not None and summary.get("win_ci_high") is not None:
        sub.append(_t(lang, "rep.wilson", lo=_pct(summary.get("win_ci_low")), hi=_pct(summary.get("win_ci_high"))))
    if summary.get("median_floor") is not None:
        sub.append(_t(
            lang, "rep.medianMax",
            med=_plain(summary.get("median_floor"), 1),
            max=_plain(summary.get("max_floor"), 0),
        ))
    if summary.get("errors"):
        sub.append(_t(lang, "rep.errorsN", n=summary.get("errors")))
    if sub:
        parts.append(_note(" · ".join(sub)))
    if summary.get("sample_warning"):
        parts.append(_note(_t(lang, "rep.sampleSmall", n=count, min=summary.get("min_n")), warn=True))
    survival = [row for row in (summary.get("survival") or []) if isinstance(row, dict)]
    parts.append(_chart_block(_t(lang, "rep.survival"), _line_chart(
        [(row.get("floor"), _num(row.get("rate")) or 0) for row in survival],
        _t(lang, "rep.survival"),
        percent=True,
    )))
    parts.append(_chart_block(_t(lang, "rep.deathRoom"), _hbar(
        [(_room(row.get("name"), lang), _num(row.get("count")) or 0) for row in _rows(summary.get("death_by_room"))],
        _t(lang, "rep.deathRoom"),
        "#E06C6C",
        integer=True,
    )))
    parts.append(_chart_block(_t(lang, "rep.deathEnc"), _hbar(
        [(row.get("name"), _num(row.get("count")) or 0) for row in _rows(summary.get("death_by_encounter"))],
        _t(lang, "rep.deathEnc"),
        "#E3B47E",
        integer=True,
    )))
    parts.append(_chart_block(_t(lang, "rep.hpLoss"), _hbar(
        [(
            _room(row.get("room"), lang) + " " + _t(lang, "rep.actN", n=row.get("act")),
            _num(row.get("avg")) or 0,
        ) for row in _rows(summary.get("hp_loss"))],
        _t(lang, "rep.hpLoss"),
        "#7FA7C9",
    )))
    parts.append(_chart_block(_t(lang, "rep.topPicks"), _hbar(
        [(row.get("id"), _num(row.get("count")) or 0) for row in _rows(summary.get("top_picks"))],
        _t(lang, "rep.topPicks"),
        "#D97757",
        integer=True,
    )))
    return "".join(parts)


def _combat_block(summary, lang):
    cells = [row for row in (summary.get("cells") or []) if isinstance(row, dict)]
    best = None
    for row in cells:
        win = _num(row.get("win"))
        if win is None:
            continue
        if best is None or win > best[0]:
            best = (win, row)
    best_text = "—"
    if best:
        row = best[1]
        best_text = f"{best[0]:.1f}% · {row.get('deck') or ''} · {_room(row.get('room'), lang)}"
    parts = [_stats([
        (_t(lang, "rep.totalFights"), _plain(summary.get("fights"), 0)),
        (_t(lang, "rep.overallWin"), _pct(summary.get("win"))),
        (_t(lang, "rep.bestCell"), best_text),
        (_t(lang, "rep.simTime"), _secs(summary.get("wall_secs"), lang)),
    ])]
    if summary.get("win_ci_low") is not None and summary.get("win_ci_high") is not None:
        parts.append(_note(_t(lang, "rep.wilson", lo=_pct(summary.get("win_ci_low")), hi=_pct(summary.get("win_ci_high")))))
    if summary.get("sample_warning"):
        parts.append(_note(_t(lang, "rep.sampleSmall", n=summary.get("fights"), min=summary.get("min_n")), warn=True))
    parts.append(_note(_t(lang, "rep.cellsSub", n=len(cells))))
    bars = []
    for row in cells[:_BAR_CAP]:
        win = _num(row.get("win"))
        if win is None:
            continue
        label = f"{row.get('deck') or ''} · {_room(row.get('room'), lang)}"
        bars.append((label, win))
    parts.append(_chart_block(_t(lang, "export.winBars"), _hbar(bars, _t(lang, "export.winBars"), "#D97757", suffix="%")))
    headers = [
        _t(lang, "col.deck"), _t(lang, "col.act"), _t(lang, "col.room"),
        _t(lang, "col.fights"), _t(lang, "col.win"), _t(lang, "cmp.turns"),
        _t(lang, "cmp.hpLoss"), _t(lang, "cmp.dpt"),
    ]
    shown, more = _cap(cells, _ROW_CAP)
    rows = []
    for row in shown:
        win = _num(row.get("win"))
        rows.append([
            row.get("deck") or row.get("deck_id") or "",
            row.get("act") if row.get("act") is not None else "—",
            _room(row.get("room"), lang),
            _plain(row.get("n"), 0),
            "—" if win is None else f"{win:.1f}%",
            _plain(row.get("turns")),
            _plain(row.get("hp_loss")),
            _plain(row.get("dpt")),
        ])
    parts.append("<h3>" + _esc(_t(lang, "rep.cellDetail")) + "</h3>")
    parts.append(_table(headers, rows) if rows else _note(_t(lang, "cmp.noCells")))
    if more:
        parts.append(_note(_t(lang, "export.truncated", n=_ROW_CAP)))
    return "".join(parts)


def _compare_section(body, lang):
    left = _side_name(body.get("a"), "A")
    right = _side_name(body.get("b"), "B")
    inner = [_note(_t(lang, "cmp.hint"))]
    if body.get("partial") or _marked_partial(body.get("a")) or _marked_partial(body.get("b")):
        inner.append(_note(_t(lang, "export.partial")))
    inner.append(
        "<div class=\"sides\"><div class=\"side\"><span class=\"tag\">A</span>"
        + _esc(left) + "</div><div class=\"side b\"><span class=\"tag b\">B</span>"
        + _esc(right) + "</div></div>"
    )
    cell_rows = []
    deltas = []
    for cell in body.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        metrics = cell.get("metrics") if isinstance(cell.get("metrics"), dict) else {}
        deck = cell.get("deck") or cell.get("deck_id") or ""
        room = _room(cell.get("room"), lang)
        act = cell.get("act")
        win = metrics.get("win") if isinstance(metrics.get("win"), dict) else None
        if win and _num(win.get("delta")) is not None:
            deltas.append((f"{deck} · {room}", _num(win.get("delta"))))
        for key in _CELL_METRICS:
            metric = metrics.get(key)
            if not isinstance(metric, dict):
                continue
            cell_rows.append(_metric_row(deck, act, room, key, metric, lang))
    inner.append(_chart_block(_t(lang, "export.deltaChart"), _diverge(deltas[:_BAR_CAP], _t(lang, "export.deltaChart"))))
    inner.append("<h3>" + _esc(_t(lang, "cmp.cells")) + "</h3>")
    shown, more = _cap(cell_rows, _ROW_CAP)
    if shown:
        inner.append(_table([
            _t(lang, "col.deck"), _t(lang, "col.act"), _t(lang, "col.room"),
            _t(lang, "cmp.metric"), "A", "B", _t(lang, "cmp.delta"), "",
        ], shown))
    else:
        inner.append(_note(_t(lang, "cmp.noCells")))
    if more:
        inner.append(_note(_t(lang, "export.truncated", n=_ROW_CAP)))
    card_rows = []
    for card in body.get("cards") or []:
        if isinstance(card, dict):
            card_rows.append(_card_row(card, lang))
    inner.append("<h3>" + _esc(_t(lang, "cmp.cards")) + "</h3>")
    shown_cards, more_cards = _cap(card_rows, _CARD_CAP)
    if shown_cards:
        inner.append(_table([
            _t(lang, "col.deck"), _t(lang, "cmp.card"),
            "A " + _t(lang, "cmp.usage"), "B " + _t(lang, "cmp.usage"),
            _t(lang, "cmp.usage") + " Δ",
            "A " + _t(lang, "cmp.efficiency"), "B " + _t(lang, "cmp.efficiency"),
            _t(lang, "cmp.efficiency") + " Δ", "",
        ], shown_cards))
    else:
        inner.append(_note(_t(lang, "cmp.noCards")))
    if more_cards:
        inner.append(_note(_t(lang, "export.truncated", n=_CARD_CAP)))
    return _section("compare", _t(lang, "export.sectionCompare"), "".join(inner))


def _metric_row(deck, act, room, key, metric, lang):
    delta = metric.get("delta")
    significant = metric.get("significant")
    tone = _tone(key, delta, significant)
    bits = [_sig_text(significant, lang)]
    if metric.get("p_value") is not None:
        bits.append(_t(lang, "ab.pValue", p=_p(metric.get("p_value"))))
    if metric.get("sample_warning"):
        bits.append(_t(lang, "ab.tooSmallTag"))
    mark = _t(lang, "cmp.sigMark") if significant is True else ""
    return [
        deck,
        act if act is not None else "—",
        room,
        _t(lang, _METRIC_KEY.get(key, key)),
        _metric_value(key, metric.get("a")),
        _metric_value(key, metric.get("b")),
        (_delta_text(key, delta) + ((" " + mark) if mark else ""), "delta " + tone),
        " · ".join(bit for bit in bits if bit),
    ]


def _card_row(card, lang):
    usage_delta = card.get("usage_delta")
    significant = card.get("usage_significant")
    tone = _tone("usage", usage_delta, significant)
    eff = card.get("efficiency_delta")
    eff_tone = _tone("efficiency", eff, eff not in (None, 0))
    bits = [_sig_text(significant, lang)]
    if card.get("usage_p_value") is not None:
        bits.append(_t(lang, "ab.pValue", p=_p(card.get("usage_p_value"))))
    if card.get("sample_warning"):
        bits.append(_t(lang, "ab.tooSmallTag"))
    mark = _t(lang, "cmp.sigMark") if significant is True else ""
    return [
        card.get("deck") or card.get("deck_id") or "",
        card.get("card") or "",
        _plain(card.get("a_per_fight")),
        _plain(card.get("b_per_fight")),
        (_delta_text("usage", usage_delta) + ((" " + mark) if mark else ""), "delta " + tone),
        _plain(card.get("a_efficiency")),
        _plain(card.get("b_efficiency")),
        (_delta_text("efficiency", eff), "delta " + eff_tone),
        " · ".join(bit for bit in bits if bit),
    ]


def _metric_value(key, value):
    if key in ("win", "timeout"):
        return _pct(value)
    return _plain(value)


def _delta_text(key, delta):
    number = _num(delta)
    if number is None:
        return "—"
    percent = key in ("win", "timeout")
    shown = number * 100 if percent else number
    sign = "+" if shown > 0 else ("−" if shown < 0 else "±")
    digits = 1 if percent else 2
    body = sign + f"{abs(shown):.{digits}f}"
    return body + (" pp" if percent else "")


def _tone(metric, delta, significant):
    if significant is not True:
        return ""
    number = _num(delta)
    if number is None or number == 0:
        return ""
    if metric in _HIGHER:
        return "good" if number > 0 else "bad"
    if metric in _LOWER:
        return "good" if number < 0 else "bad"
    return ""


def _sig_text(significant, lang):
    if significant is True:
        return _t(lang, "ab.sig")
    if significant is False:
        return _t(lang, "ab.notSig")
    return "—"


def _p(value):
    number = _num(value)
    if number is None:
        return "—"
    if number < 0.0001:
        return f"{number:.2e}"
    return f"{number:.4f}"


def _cal_section(doc, lang):
    from gui import i18n
    matched = doc.get("sim_matched")
    rows = doc.get("sim_rows")
    gaps = doc.get("gaps") if isinstance(doc.get("gaps"), list) else []
    unmatched = doc.get("unmatched") if isinstance(doc.get("unmatched"), list) else []
    inner = [_note(_t(lang, "cal.readOnly"))]
    bits = []
    if doc.get("character"):
        bits.append(str(doc.get("character")))
    if doc.get("ascension") is not None:
        bits.append("A" + str(doc.get("ascension")))
    if doc.get("seed"):
        bits.append(_t(lang, "chip.seed", s=doc.get("seed")))
    inner.append(_chips(bits))
    if matched is not None or rows is not None:
        inner.append(_note(_t(
            lang, "cal.summary",
            matched=matched if matched is not None else 0,
            rows=rows if rows is not None else 0,
            gaps=len(gaps),
            unmatched=len(unmatched),
        )))
    deck = doc.get("deck_path") if isinstance(doc.get("deck_path"), list) else []
    if deck:
        inner.append(_note(_t(lang, "cal.deck") + ": " + i18n.join(deck, lang)))
    inner.append(_note(_t(lang, "cal.legend")))
    fights = [row for row in (doc.get("fights") or []) if isinstance(row, dict)]
    shown, more = _cap(fights, _FIGHT_CAP)
    inner.append(_band_chart(shown, lang))
    headers = [
        _t(lang, "cal.floor"), _t(lang, "cal.room"), _t(lang, "cal.encounter"),
        _t(lang, "cal.realHp"), _t(lang, "cal.mean"), _t(lang, "cal.p10"),
        _t(lang, "cal.p90"), _t(lang, "cal.percentile"), _t(lang, "cal.gap"),
    ]
    table_rows = []
    for fight in shown:
        status = fight.get("status")
        gap = _t(lang, "cal.gapYes") if fight.get("likely_sim_gap") else _t(lang, "cal.gapNo")
        if status != "compared":
            reason = fight.get("reason") or status or ""
            reason_text = _t(lang, "cal.reason." + reason) if reason and i18n.has("cal.reason." + str(reason), lang) else str(reason or "—")
            gap = reason_text
        table_rows.append([
            fight.get("floor") if fight.get("floor") is not None else "—",
            _room(fight.get("room"), lang),
            fight.get("encounter") or "—",
            _plain(fight.get("real_hp_lost"), 1),
            _plain(fight.get("mean"), 1),
            _plain(fight.get("p10"), 1),
            _plain(fight.get("p90"), 1),
            _plain(fight.get("percentile"), 1),
            gap,
        ])
    inner.append(_table(headers, table_rows) if table_rows else _note(_t(lang, "cal.emptyTitle")))
    if more:
        inner.append(_note(_t(lang, "export.truncated", n=_FIGHT_CAP)))
    return _section("calibration", _t(lang, "export.sectionCal"), "".join(inner))


def _gap_section(doc, lang):
    counts = doc.get("counts") if isinstance(doc.get("counts"), dict) else {}
    inner = [_note(_t(lang, "cal.triageReadOnly"))]
    inner.append(_note(_t(
        lang, "cal.triageCounts",
        compared=counts.get("compared") or 0,
        gaps=counts.get("gaps") or 0,
        optimistic=counts.get("optimistic") or 0,
        pessimistic=counts.get("pessimistic") or 0,
    )))
    encounters = doc.get("encounters") if isinstance(doc.get("encounters"), dict) else {}
    inner.append("<h3>" + _esc(_t(lang, "cal.triageOptimistic")) + "</h3>")
    inner.append(_gap_encounter_table(encounters.get("optimistic"), "optimistic", lang))
    inner.append("<h3>" + _esc(_t(lang, "cal.triagePessimistic")) + "</h3>")
    inner.append(_gap_encounter_table(encounters.get("pessimistic"), "pessimistic", lang))
    inner.append("<h3>" + _esc(_t(lang, "cal.triageByPower")) + "</h3>")
    inner.append(_gap_power_table(doc.get("by_power"), lang))
    return _section("gap", _t(lang, "export.sectionGap"), "".join(inner))


def _gap_label(row, lang):
    if not isinstance(row, dict):
        return ""
    if lang == "zhs" and row.get("label_zh"):
        return str(row.get("label_zh"))
    if row.get("label_en"):
        return str(row.get("label_en"))
    return str(row.get("id") or "")


def _gap_code(row):
    bits = []
    for item in row.get("code") or []:
        if not isinstance(item, dict):
            continue
        file_name = item.get("file") or ""
        line = item.get("line")
        symbol = item.get("symbol") or ""
        text = file_name
        if line:
            text += ":" + str(line)
        if symbol:
            text += " " + str(symbol)
        if text:
            bits.append(text)
    return " · ".join(bits)


def _ratio(count, total, lang):
    count_n = _num(count) or 0
    total_n = _num(total) or 0
    pct = 0 if total_n <= 0 else 100 * count_n / total_n
    return _t(lang, "cal.triageRatio", count=int(count_n), total=int(total_n), pct=f"{pct:.0f}")


def _gap_encounter_table(rows, direction, lang):
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    if not rows:
        return _note(_t(lang, "cal.triageEmpty"))
    shown, more = _cap(rows, _BAR_CAP)
    body = []
    for row in shown:
        body.append([
            row.get("id") or "",
            _plain(row.get("compared"), 0),
            _ratio(row.get(direction), row.get("compared"), lang),
            _gap_code(row),
        ])
    table = _table([
        _t(lang, "cal.triageEncounter"), _t(lang, "cal.triageCompared"),
        _t(lang, "cal.triageOptimisticCol" if direction == "optimistic" else "cal.triagePessimisticCol"),
        _t(lang, "cal.triageCode"),
    ], body)
    if more:
        table += _note(_t(lang, "export.truncated", n=_BAR_CAP))
    return table


def _gap_power_table(rows, lang):
    rows = [row for row in (rows or []) if isinstance(row, dict) and (row.get("optimistic") or row.get("pessimistic"))]
    if not rows:
        return _note(_t(lang, "cal.triageNoPower"))
    shown, more = _cap(rows, _BAR_CAP)
    body = []
    for row in shown:
        kind = row.get("kind") or ""
        kind_text = _t(lang, "cal.triageKind." + kind) if kind else ""
        lean = row.get("lean") or ""
        lean_text = _t(lang, "cal.triageLean." + lean) if lean else ""
        body.append([
            kind_text,
            _gap_label(row, lang),
            _plain(row.get("compared"), 0),
            lean_text,
            _ratio(row.get("optimistic") if lean != "pessimistic" else row.get("pessimistic"), row.get("compared"), lang),
            _gap_code(row),
        ])
    table = _table([
        _t(lang, "cal.triageKind"), _t(lang, "cal.triageName"), _t(lang, "cal.triageCompared"),
        _t(lang, "cal.triageLean"), _t(lang, "cal.triageRate"), _t(lang, "cal.triageCode"),
    ], body)
    if more:
        table += _note(_t(lang, "export.truncated", n=_BAR_CAP))
    return table


def _rows(value):
    return [row for row in (value or []) if isinstance(row, dict)]


def _cap(rows, limit):
    if len(rows) <= limit:
        return rows, False
    return rows[:limit], True


def _chart_block(title, svg):
    if not svg:
        return ""
    return "<h3>" + _esc(title) + "</h3>" + svg


# ---------------------------------------------------------------- SVG
def _line_chart(points, title, percent=False):
    usable = [(label, value) for label, value in points if _num(value) is not None]
    if len(usable) < 2:
        return ""
    width, height = 680, 220
    left, right, top, bottom = 44, 12, 16, 28
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for _label, value in usable]
    peak = max(values) if values else 1
    if percent:
        peak = 1
    peak = peak or 1
    coords = []
    step = plot_w / (len(usable) - 1)
    for index, (_label, value) in enumerate(usable):
        x = left + step * index
        y = top + plot_h - (max(value, 0) / peak) * plot_h
        coords.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{coords[0][0]:.1f},{top + plot_h:.1f} " + line + f" {coords[-1][0]:.1f},{top + plot_h:.1f}"
    labels = []
    last = len(usable) - 1
    for index in {0, last // 2, last}:
        x, _y = coords[index]
        labels.append(
            f'<text x="{x:.1f}" y="{height - 8}" text-anchor="middle" class="tick">{_esc(usable[index][0])}</text>'
        )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">'
        f"<title>{_esc(title)}</title>"
        f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" class="axis"/>'
        f'<polygon points="{area}" fill="#D97757" fill-opacity="0.22"/>'
        f'<polyline points="{line}" fill="none" stroke="#D97757" stroke-width="2.5"/>'
        + "".join(labels) + "</svg>"
    )


def _hbar(rows, title, color, integer=False, suffix=""):
    usable = []
    for label, value in rows:
        number = _num(value)
        if number is None:
            continue
        usable.append((label, number))
    if not usable:
        return ""
    usable = usable[:_BAR_CAP]
    width = 680
    label_w, right, row_h, top = 188, 78, 26, 8
    height = top + row_h * len(usable) + 8
    peak = max(value for _label, value in usable) or 1
    bar_w = width - label_w - right
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f"<title>{_esc(title)}</title>",
    ]
    for index, (label, value) in enumerate(usable):
        y = top + index * row_h
        frac = 0 if peak <= 0 else max(value, 0) / peak
        drawn = round(frac * bar_w, 1)
        shown = str(round(value)) if integer else f"{value:.1f}"
        if suffix:
            shown += suffix
        parts.append(
            f'<text x="0" y="{y + 16}" class="tick">{_esc(_clip(label, 24))}</text>'
            f'<rect x="{label_w}" y="{y + 5}" width="{drawn}" height="14" rx="3" fill="{color}"/>'
            f'<text x="{label_w + bar_w + 8}" y="{y + 16}" class="tick">{_esc(shown)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _diverge(rows, title):
    usable = [(label, value) for label, value in rows if _num(value) is not None and value != 0]
    if not usable:
        return ""
    width = 680
    label_w, row_h, top = 200, 26, 8
    height = top + row_h * len(usable) + 8
    bar_w = width - label_w - 16
    span = max(abs(value) for _label, value in usable) or 0.01
    mid = label_w + bar_w / 2
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f"<title>{_esc(title)}</title>",
        f'<line x1="{mid:.1f}" y1="{top}" x2="{mid:.1f}" y2="{height - 6}" class="axis"/>',
    ]
    for index, (label, value) in enumerate(usable):
        y = top + index * row_h
        half = (value / span) * (bar_w / 2)
        if half >= 0:
            x, drawn, color = mid, half, "#8FBF8F"
        else:
            x, drawn, color = mid + half, -half, "#E06C6C"
        shown = _delta_text("win", value)
        parts.append(
            f'<text x="0" y="{y + 16}" class="tick">{_esc(_clip(label, 26))}</text>'
            f'<rect x="{x:.1f}" y="{y + 5}" width="{max(drawn, 1):.1f}" height="14" rx="3" fill="{color}"/>'
            f'<text x="{width - 4}" y="{y + 16}" text-anchor="end" class="tick">{_esc(shown)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _band_chart(fights, lang):
    rows = []
    for fight in fights:
        if fight.get("status") != "compared":
            continue
        real = _num(fight.get("real_hp_lost"))
        p10 = _num(fight.get("p10"))
        p90 = _num(fight.get("p90"))
        if real is None or p10 is None or p90 is None:
            continue
        rows.append((fight, real, _num(fight.get("p5")), p10, p90, _num(fight.get("p95"))))
    if not rows:
        return ""
    width = 680
    label_w, row_h, top, right = 168, 28, 8, 16
    height = top + row_h * len(rows) + 8
    peak = 1
    for _fight, real, p5, _p10, _p90, p95 in rows:
        for value in (real, p5, p95):
            if value is not None:
                peak = max(peak, value)
    peak *= 1.05
    bar_w = width - label_w - right
    title = _t(lang, "cal.band")
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f"<title>{_esc(title)}</title>",
    ]
    for index, (fight, real, p5, p10, p90, p95) in enumerate(rows):
        y = top + index * row_h
        label = f"{fight.get('floor')} {_room(fight.get('room'), lang)}"

        def x_of(value, _peak=peak, _bar=bar_w, _left=label_w):
            if value is None:
                return None
            return _left + max(0, min(value, _peak)) / _peak * _bar

        thin_a, thin_b = x_of(p5 if p5 is not None else p10), x_of(p95 if p95 is not None else p90)
        band_a, band_b = x_of(p10), x_of(p90)
        mark = x_of(real)
        color = "#E06C6C" if fight.get("likely_sim_gap") else "#EDE9E3"
        parts.append(f'<text x="0" y="{y + 17}" class="tick">{_esc(_clip(label, 20))}</text>')
        if thin_a is not None and thin_b is not None and thin_b >= thin_a:
            parts.append(
                f'<line x1="{thin_a:.1f}" y1="{y + 14}" x2="{thin_b:.1f}" y2="{y + 14}" stroke="#6E6A64" stroke-width="2"/>'
            )
        if band_a is not None and band_b is not None and band_b >= band_a:
            parts.append(
                f'<rect x="{band_a:.1f}" y="{y + 8}" width="{max(band_b - band_a, 2):.1f}" height="12" rx="3" fill="#7FA7C9"/>'
            )
        if mark is not None:
            parts.append(f'<circle cx="{mark:.1f}" cy="{y + 14}" r="4.5" fill="{color}"/>')
    parts.append("</svg>")
    return "".join(parts)


_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #131315; color: #EDE9E3;
  font: 15px/1.5 "Segoe UI", "PingFang SC", "Hiragino Sans", "Yu Gothic UI", "Malgun Gothic", "Noto Sans CJK SC", sans-serif;
}
header, main, footer { width: min(980px, calc(100% - 32px)); margin: 0 auto; }
header { display: flex; gap: 16px; align-items: flex-start; padding: 36px 0 8px; }
.mark { width: 18px; height: 42px; margin-top: 8px; border-radius: 9px; background: #D97757; flex: none; }
.brand { margin: 0; letter-spacing: 0.14em; text-transform: uppercase; color: #D97757; font-size: 12px; font-weight: 700; }
h1 { margin: 4px 0 8px; font-size: 32px; line-height: 1.15; font-weight: 720; }
h2 { margin: 28px 0 12px; font-size: 22px; }
h3 { margin: 18px 0 8px; font-size: 15px; font-weight: 650; color: #D6D1CA; }
.lead { margin: 0 0 6px; color: #C8C2B8; }
.faint, .note { color: #9C978F; }
.note { margin: 8px 0; font-size: 13.5px; }
.note.warn { color: #E3B47E; }
section { background: #1E1E22; border: 1px solid #2E2E34; border-radius: 16px; padding: 8px 18px 18px; margin: 16px 0; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 12px; }
.stat { background: #25252A; border-radius: 12px; padding: 12px 12px 10px; }
.stat .k { color: #9C978F; font-size: 12px; }
.stat .v { font-size: 22px; font-weight: 700; margin-top: 4px; word-break: break-word; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.chip { background: #2A2A30; color: #D6D1CA; border-radius: 999px; padding: 3px 10px; font-size: 12.5px; }
.chart { width: 100%; height: auto; display: block; margin: 4px 0 8px; }
.tick { fill: #9C978F; font-size: 12px; font-family: inherit; }
.axis { stroke: #3A3A42; stroke-width: 1; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th { text-align: left; color: #9C978F; font-weight: 600; font-size: 12px; padding: 8px 8px; border-bottom: 1px solid #2E2E34; }
td { padding: 8px; border-bottom: 1px solid #26262B; vertical-align: top; }
tr:last-child td { border-bottom: none; }
td.delta { font-variant-numeric: tabular-nums; }
td.good { color: #8FBF8F; font-weight: 700; }
td.bad { color: #E06C6C; font-weight: 700; }
.sides { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 12px 0; }
.side { background: #25252A; border-radius: 12px; padding: 12px; }
.side.b { outline: 1px solid rgba(217, 119, 87, 0.45); }
.tag { display: inline-grid; place-items: center; width: 22px; height: 22px; margin-right: 8px; border-radius: 6px; background: #3A3A42; font-weight: 800; font-size: 12px; }
.tag.b { background: #D97757; color: #17171A; }
footer { color: #6E6A64; font-size: 12.5px; padding: 8px 0 36px; }
@media print {
  body { background: #fff; color: #1b1b1b; }
  section, .stat, .side { background: #fff; border-color: #ddd; }
  .tick { fill: #444; }
  h1, h2, h3, .lead { color: #1b1b1b; }
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
