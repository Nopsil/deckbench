"""只读导入真游戏的一局记录或进行中存档，打印种子、路线、选牌和遗物。

  python tools/import_run.py tests/fixtures/saves/sample_history.run
  python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
  python tools/import_run.py tests/fixtures/saves/sample_history.run --summary --json /tmp/summary.json
  python tools/import_run.py "%APPDATA%\\SlayTheSpire2\\steam\\<id>\\profile1\\saves"
  python tools/import_run.py --discover

`--summary` 把短 JSON 打到标准输出（种子、角色、进阶、到达层、牌和遗物要点），不写存档。
`--json` 只会写到你指出的路径，而且拒绝写进存档目录、覆盖刚读的文件，或写成 .run / .save。
不修改存档，不解密。格式说明见 docs/SAVE_FORMAT.md。
夹具里的 ID 是虚构的，用来演示解析，不是游戏数据。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from sts2sim.saveimport import SaveImportError, discover, load_path, refuse_save_write, summarize  # noqa: E402


def _t(lang):
    from gui import i18n

    def t(key, **kw):
        return i18n.t(key, lang, **kw)
    return t, i18n


def _warn_lines(warnings, lang):
    t, i18n = _t(lang)
    lines = []
    for w in warnings or []:
        code = w.get("code") if isinstance(w, dict) else None
        if code and i18n.has("imp.warn." + code, lang):
            lines.append(t("imp.warn." + code, **{k: v for k, v in w.items() if k != "code"}))
        elif isinstance(w, dict) and w.get("text"):
            lines.append(str(w["text"]))
        elif code:
            lines.append(code)
    return lines


def render_run(run, lang="zhs"):
    t, i18n = _t(lang)
    lines = []
    if run.get("filename"):
        lines.append(t("imp.text.file", file=run["filename"]))
    lines.append(t("imp.text.head", seed=run.get("seed") or t("common.none"),
                   char=i18n.join([p.get("character") or t("common.none") for p in run.get("players") or []], lang) or t("common.none"),
                   asc=run.get("ascension"),
                   result=t("imp.result." + run["result"]) if run.get("result") else t("common.none"),
                   schema=run.get("schema_version") if run.get("schema_version") is not None else t("common.none")))
    for w in _warn_lines(run.get("warnings"), lang):
        lines.append(t("imp.text.warn", text=w))
    acts = i18n.join([a.get("id") or "" for a in run.get("acts") or []], lang)
    if acts:
        lines.append(t("imp.text.acts", acts=acts))
    if run.get("killed_by_encounter") or run.get("killed_by_event"):
        lines.append(t("imp.text.killed", enc=run.get("killed_by_encounter") or t("common.none"),
                       ev=run.get("killed_by_event") or t("common.none")))
    lines.append(t("imp.text.route"))
    if not run.get("route"):
        lines.append("  " + t("common.none"))
    for fl in run.get("route") or []:
        rooms = i18n.join([r.get("model_id") or r.get("room_type") or "" for r in fl.get("rooms") or [] if r.get("model_id") or r.get("room_type")], lang)
        picked = []
        offered = []
        for group in fl.get("picks") or []:
            for c in group.get("cards") or []:
                offered.append(c.get("id"))
                if c.get("was_picked"):
                    picked.append(c.get("id"))
        extra = ""
        if offered:
            extra = "  " + t("imp.text.pickLine", picked=i18n.join(picked, lang) or t("imp.skipped"),
                             offered=i18n.join([x for x in offered if x], lang))
        lines.append(t("imp.text.floor", n=fl.get("floor"), act=(fl.get("act_index") or 0) + 1,
                       typ=fl.get("type") or t("common.none"), rooms=rooms or t("common.none")) + extra)
    lines.append(t("imp.text.relics"))
    any_relic = False
    for p in run.get("players") or []:
        for r in p.get("relics") or []:
            any_relic = True
            floor = t("imp.floorAdded", floor=r["floor"]) if r.get("floor") is not None else ""
            who = f"P{p.get('id')} " if len(run.get("players") or []) > 1 else ""
            lines.append(f"  {who}{r.get('id')}{floor}")
    if not any_relic:
        lines.append("  " + t("imp.noRelics"))
    lines.append(t("imp.text.deck"))
    any_card = False
    for p in run.get("players") or []:
        for c in p.get("deck") or []:
            any_card = True
            mark = "+" if c.get("upgraded") else ""
            floor = t("imp.floorAdded", floor=c["floor"]) if c.get("floor") is not None else ""
            ench = (" " + t("imp.enchant", id=c["enchantment"]["id"])) if c.get("enchantment") else ""
            who = f"P{p.get('id')} " if len(run.get("players") or []) > 1 else ""
            lines.append(f"  {who}{c.get('id')}{mark}{floor}{ench}")
    if not any_card:
        lines.append("  " + t("imp.noDeck"))
    return "\n".join(lines)


def render_folder(doc, lang="zhs", full=False):
    t, _i18n = _t(lang)
    lines = [t("imp.text.folder", path=doc.get("path"), n=len(doc.get("entries") or []))]
    for w in _warn_lines(doc.get("warnings"), lang):
        lines.append(t("imp.text.warn", text=w))
    for e in doc.get("entries") or []:
        if "run" in e:
            run = e["run"]
            lines.append(t("imp.text.row", file=e.get("file"), seed=run.get("seed") or "—",
                           char=(run.get("players") or [{}])[0].get("character") or "—",
                           asc=run.get("ascension"), result=t("imp.result." + run["result"]) if run.get("result") else "—",
                           floors=len(run.get("route") or [])))
            if full:
                lines.append(render_run(run, lang))
                lines.append("")
        else:
            err = e.get("error") or {}
            lines.append(t("imp.text.bad", file=e.get("file"), code=err.get("code")))
    return "\n".join(lines)


def _dump(payload, fh):
    json.dump(payload, fh, ensure_ascii=False, indent=1)
    fh.write("\n")


def _error_payload(err):
    body = {"ok": False, "read_only": True, "error": err.code}
    for k, v in err.params.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            body[k] = v
    return body


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="一个 .run / current_run.save，或存档目录")
    ap.add_argument("--json", help="把解析结果写成 JSON（拒绝写进存档目录）")
    ap.add_argument("--summary", action="store_true",
                    help="向标准输出打印短 JSON 摘要（种子、角色、进阶、到达层、牌和遗物要点），不写存档")
    ap.add_argument("--list", action="store_true", help="目录只打印一行摘要")
    ap.add_argument("--discover", action="store_true", help="在常见位置查找存档目录（不读取内容）")
    ap.add_argument("--lang", default="zhs", choices=["zhs", "en", "ja", "ko"])
    a = ap.parse_args(argv)
    try:
        if a.discover:
            rows = discover()
            if a.json:
                dest = refuse_save_write(a.json, None)
                with open(dest, "w", encoding="utf-8") as f:
                    _dump(rows, f)
            if a.summary:
                _dump({"ok": True, "read_only": True, "kind": "discover", "roots": rows}, sys.stdout)
                return 0
            t, _ = _t(a.lang)
            if not rows:
                print(t("imp.discoverEmpty"))
            for row in rows:
                print(t("imp.discoverFound", n=row.get("history")) + "  " + row["path"])
            return 0
        if not a.path:
            ap.error("path")
        doc = load_path(a.path)
        summary = summarize(doc) if a.summary else None
        if a.json:
            dest = refuse_save_write(a.json, a.path)
            with open(dest, "w", encoding="utf-8") as f:
                _dump(summary if summary is not None else doc, f)
    except SaveImportError as e:
        t, i18n = _t(a.lang)
        key = "imp.err." + e.code
        msg = t(key, **e.params) if i18n.has(key, a.lang) else e.code
        if a.summary:
            _dump(_error_payload(e), sys.stdout)
        print(msg, file=sys.stderr)
        return 2
    if a.summary:
        _dump(summary, sys.stdout)
        return 0
    if doc["kind"] == "run":
        print(render_run(doc["run"], a.lang))
    else:
        print(render_folder(doc, a.lang, full=not a.list))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
