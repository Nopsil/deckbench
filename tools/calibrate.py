"""对照一份真对局和同一条选牌路径上的模拟掉血。不新开模拟，不改存档。

  python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl
  python tools/calibrate.py path/to/history/123.run path/to/runs.jsonl --json -
  python tools/calibrate.py path/to/current_run.save path/to/run_dir --json /tmp/calibration.json

真对局用和 import_run 相同的只读解析。模拟文件是整局 runs.jsonl（或含它的目录），
命令行可以指向你给出的路径。HTTP 和 MCP 的模拟路径仍限制在允许的目录里。

只保留种子、角色、进阶和选牌序列都相同的模拟局。每一场战斗给出真机失去的生命、
模拟的均值、p10、p90，以及真值的百分位。真值在 p5–p95 之外标成疑似模拟缺口。
层数、房间和遭遇对不上时记 unmatched，不用别的层来凑。

Compare one imported run with simulations that share its seed, character,
ascension and card-pick path. A floor that does not match on floor, room and
encounter is unmatched. ``--json -`` prints only the JSON report.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from sts2sim.analysis import AnalysisError  # noqa: E402
from sts2sim.calibrate import (  # noqa: E402
    CalibrateError,
    calibrate_paths,
    render_text,
)
from sts2sim.saveimport import SaveImportError, refuse_save_write  # noqa: E402


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def _dump(payload, fh):
    json.dump(payload, fh, ensure_ascii=False, indent=1)
    fh.write("\n")


def _error_payload(err):
    body = {"ok": False, "read_only": True, "error": err.code}
    for key, value in getattr(err, "params", {}).items():
        if value is None or isinstance(value, (str, int, float, bool)):
            body[key] = value
    return body


def _message(err, lang):
    try:
        from gui import i18n
    except ImportError:
        return err.code
    params = getattr(err, "params", {})
    if isinstance(err, CalibrateError):
        prefixes = ("cal.err.",)
    elif isinstance(err, SaveImportError):
        prefixes = ("imp.err.",)
    else:
        prefixes = ("exp.err.",)
    for prefix in prefixes:
        key = prefix + err.code
        if i18n.has(key, lang):
            return i18n.t(key, lang, **params)
    return err.code


def _fail(err, lang, json_stdout):
    if json_stdout:
        _dump(_error_payload(err), sys.stdout)
    print(_message(err, lang), file=sys.stderr)


def main(argv=None):
    _configure_stdio()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("real", help="一份 .run / current_run.save")
    ap.add_argument("sim", help="runs.jsonl，或含有 runs.jsonl 的目录")
    ap.add_argument("--json", default="", help="写出报告 JSON。- 表示只打到标准输出")
    ap.add_argument("--lang", default="zhs", choices=["zhs", "en", "ja", "ko"])
    args = ap.parse_args(argv)
    try:
        body = calibrate_paths(args.real, args.sim, restricted=False)
    except (CalibrateError, SaveImportError, AnalysisError) as err:
        _fail(err, args.lang, json_stdout=(args.json == "-"))
        return 2
    if args.json == "-":
        _dump(body, sys.stdout)
        return 0
    if args.json:
        try:
            dest = refuse_save_write(args.json, args.real)
        except SaveImportError as err:
            _fail(err, args.lang, json_stdout=False)
            return 2
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            _dump(body, fh)
    sys.stdout.write(render_text(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
