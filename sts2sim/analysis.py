"""只读分析已经跑完的结果，给 MCP 用。不新开模拟，不写文件。

路径必须落在允许的目录里（realpath，符号链接按目标算）：

- 界面数据目录：``STS2SIM_GUI_DATA``，否则 ``gui/.data``
- DeckBench 缓存（``DECKBENCH_CACHE``，否则用户缓存下的 ``deckbench``）及其 ``mcp_runs``
- ``DECKBENCH_ANALYSIS_ROOTS``：用 ``os.pathsep`` 分开的额外目录

存档树（``saves`` / ``history`` / ``SlayTheSpire2``、本机游戏数据根）和 ``.run`` / ``.save``
用 ``saveimport.refuse_save_write`` 的同一套规则拒绝，连读都不读。
"""
import json
import os

from sts2sim.explain import combat_groups, top
from sts2sim.saveimport import SaveImportError, refuse_save_write

_KINDS = ("play", "target", "potion", "reward", "shop")
_DECISION_KEYS = ("seq", "kind", "turn", "floor", "act", "room", "encounter", "fight", "card", "threshold", "note")
_MAX_LIMIT = 100


class AnalysisError(Exception):
    def __init__(self, code, **params):
        super().__init__(code)
        self.code = code
        self.params = params


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _realpath(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _under(path, root):
    path = os.path.normcase(_realpath(path))
    root = os.path.normcase(_realpath(root))
    if path == root:
        return True
    try:
        return os.path.normcase(os.path.commonpath([path, root])) == root
    except ValueError:
        return False


def allowed_roots():
    """当前进程可以读的目录。不存在的目录跳过，这里不创建。"""
    roots = []
    gui = os.environ.get("STS2SIM_GUI_DATA")
    if not gui:
        gui = os.path.join(_repo_root(), "gui", ".data")
    roots.append(gui)
    from sts2sim.gamedata import cache_root
    cache = cache_root()
    roots.append(cache)
    mcp = os.environ.get("DECKBENCH_MCP_RUNS") or os.path.join(cache, "mcp_runs")
    roots.append(mcp)
    extra = os.environ.get("DECKBENCH_ANALYSIS_ROOTS", "")
    if extra:
        roots.extend(p for p in extra.split(os.pathsep) if p)
    out = []
    seen = set()
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        key = os.path.normcase(_realpath(root))
        if key in seen:
            continue
        seen.add(key)
        out.append(_realpath(root))
    return out


def _matching_root(path):
    for root in allowed_roots():
        if _under(path, root):
            return root
    return None


def _touches_save(path):
    """和导入工具拒绝写入的是同一类路径。目录则检查它下面的一个 jsonl 名，不创建。"""
    probe = path if os.path.isfile(path) else os.path.join(path, "runs.jsonl")
    try:
        refuse_save_write(probe)
    except SaveImportError as e:
        if e.code == "refuse_write":
            return True
        raise
    return False


def resolve_read(path):
    """规范化后的可读路径。目录外、存档树、不存在，都是 AnalysisError，不读内容。"""
    if not isinstance(path, str) or not path.strip():
        raise AnalysisError("need_path")
    raw = os.path.abspath(os.path.expanduser(path.strip()))
    real = _realpath(raw)
    if _matching_root(real) is None:
        raise AnalysisError("path_not_allowed", path=real)
    if not os.path.exists(real):
        raise AnalysisError("not_found", path=real)
    if _touches_save(real):
        raise AnalysisError("refuse_write", path=real)
    if not os.path.isfile(real) and not os.path.isdir(real):
        raise AnalysisError("not_found", path=real)
    return real


def _dump(body):
    return json.dumps(body, ensure_ascii=False, indent=1) + "\n"


def _error_json(err):
    body = {"ok": False, "read_only": True, "error": err.code}
    for k, v in err.params.items():
        if v is None or isinstance(v, (str, int, float, bool)):
            body[k] = v
    return _dump(body)


def _call(fn, *args, **kwargs):
    try:
        return _dump(fn(*args, **kwargs))
    except AnalysisError as e:
        return _error_json(e)


def _load_jsonl(path):
    rows = []
    try:
        fh = open(path, "r", encoding="utf-8-sig")
    except OSError:
        raise AnalysisError("unreadable", path=path)
    with fh:
        try:
            for i, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    raise AnalysisError("not_json", path=path, line=i)
                if not isinstance(row, dict):
                    raise AnalysisError("not_json", path=path, line=i)
                rows.append(row)
        except UnicodeDecodeError:
            raise AnalysisError("not_json", path=path)
    return rows


def _metrics():
    try:
        from gui import metrics
    except ImportError:
        root = _repo_root()
        import sys
        if root not in sys.path:
            sys.path.insert(0, root)
        from gui import metrics
    return metrics


def _batch_file(path):
    found = resolve_read(path)
    if os.path.isdir(found):
        return resolve_read(os.path.join(found, "runs.jsonl"))
    return found


def _require_batch(rows, path):
    for i, row in enumerate(rows, 1):
        if row.get("error"):
            continue
        combats = row.get("combats")
        if "floor" not in row or "victory" not in row or not isinstance(combats, list):
            raise AnalysisError("not_batch", path=path, line=i)
        for c in combats:
            if not isinstance(c, (list, tuple)) or len(c) < 5:
                raise AnalysisError("not_batch", path=path, line=i)
    return rows


def _attach_rate(summary):
    """n 为 0 时图形界面摘要不带区间。这里仍用 stats.py 补上，不覆盖已有字段。"""
    from sts2sim.stats import format_win_rate, win_rate_report
    wins = summary.get("wins", 0) or 0
    n = summary.get("n", 0) or 0
    report = win_rate_report(wins, n)
    for key in ("wins", "n", "win"):
        report.pop(key, None)
    for key, value in report.items():
        summary.setdefault(key, value)
    if "win_rate_text" not in summary:
        summary["win_rate_text"] = format_win_rate(win_rate_report(wins, n), "text").rstrip("\n")
        summary["win_rate_markdown"] = format_win_rate(win_rate_report(wins, n), "markdown").rstrip("\n")
    return summary


def _summary_for(path):
    found = _batch_file(path)
    rows = _require_batch(_load_jsonl(found), found)
    try:
        summary = _metrics().batch_summary(rows)
    except (KeyError, TypeError, IndexError, ValueError):
        raise AnalysisError("not_batch", path=found)
    if not isinstance(summary, dict):
        raise AnalysisError("not_batch", path=found)
    return found, _attach_rate(summary)


def batch_run_summary(path):
    found, summary = _summary_for(path)
    return {"ok": True, "read_only": True, "path": found, "summary": summary}


def _wins_n(rows):
    ok = [r for r in rows if not r.get("error")]
    return sum(bool(r.get("victory")) for r in ok), len(ok)


def _pair_files(directory):
    names = sorted(os.listdir(directory))
    a_files = [n for n in names if n == "A.jsonl" or n.endswith("_A.jsonl")]
    b_files = [n for n in names if n == "B.jsonl" or n.endswith("_B.jsonl")]
    if len(a_files) == 1 and len(b_files) == 1:
        return (
            resolve_read(os.path.join(directory, a_files[0])),
            resolve_read(os.path.join(directory, b_files[0])),
        )
    if not a_files and not b_files:
        raise AnalysisError("need_b", path=directory)
    raise AnalysisError("ambiguous_pair", path=directory, n_a=len(a_files), n_b=len(b_files))


def _two_files(a, b):
    if not isinstance(b, str):
        raise AnalysisError("need_b")
    if not b.strip():
        found = resolve_read(a)
        if not os.path.isdir(found):
            raise AnalysisError("need_b", path=found)
        return _pair_files(found)
    return _batch_file(a), _batch_file(b)


def card_ab(a, b=""):
    from sts2sim.stats import ab_win_report
    path_a, path_b = _two_files(a, b)
    rows_a = _require_batch(_load_jsonl(path_a), path_a)
    rows_b = _require_batch(_load_jsonl(path_b), path_b)
    try:
        result = _metrics().batch_ab(rows_a, rows_b)
    except (KeyError, TypeError, IndexError, ValueError):
        raise AnalysisError("not_batch", path=path_a)
    if not isinstance(result, dict):
        raise AnalysisError("not_batch", path=path_a)
    wa, na = _wins_n(rows_a)
    wb, nb = _wins_n(rows_b)
    win_ab = ab_win_report(wa, na, wb, nb)
    return {
        "ok": True,
        "read_only": True,
        "a": path_a,
        "b": path_b,
        "p_value": win_ab.get("p_value"),
        "sample_warning": win_ab.get("sample_warning"),
        "win_ab": win_ab,
        "result": result,
    }


def _index(name, value, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AnalysisError(f"bad_{name}")
    return value


def _explain_file(path):
    found = resolve_read(path)
    if os.path.isfile(found):
        return found
    names = sorted(n for n in os.listdir(found) if n == "explain.jsonl" or n.endswith(".explain.jsonl"))
    if len(names) == 1:
        return resolve_read(os.path.join(found, names[0]))
    if not names:
        raise AnalysisError("not_explain", path=found)
    raise AnalysisError("ambiguous_explain", path=found, n=len(names))


def _decision(row):
    chosen = row.get("chosen")
    out = {}
    for key in _DECISION_KEYS:
        if row.get(key) is not None:
            out[key] = row[key]
    out["chosen"] = chosen
    out["candidates"] = top(row.get("candidates") or [], chosen)
    return out


def _where(row):
    out = {}
    for key in ("seed", "char", "deck", "act", "floor", "room", "encounter", "fight"):
        if row.get(key) is not None:
            out[key] = row[key]
    return out


def explain_fight(path, fight=0, seed="", offset=0, limit=20):
    if not isinstance(seed, str):
        raise AnalysisError("bad_seed")
    fight = _index("fight", fight, 0)
    offset = _index("offset", offset, 0)
    limit = min(_index("limit", limit, 1), _MAX_LIMIT)
    found = _explain_file(path)
    rows = _load_jsonl(found)
    if not any(r.get("kind") in _KINDS for r in rows):
        raise AnalysisError("not_explain", path=found)
    filtered = rows
    if seed:
        filtered = [r for r in rows if str(r.get("seed")) == seed]
    groups = combat_groups(filtered)
    if fight >= len(groups):
        if not groups and fight == 0:
            return {
                "ok": True, "read_only": True, "path": found, "fight": 0, "fight_count": 0,
                "seed": seed or None, "where": {}, "offset": offset, "limit": limit, "total": 0,
                "next_offset": None, "decisions": [],
            }
        raise AnalysisError("fight_out_of_range", fight=fight, fight_count=len(groups))
    _key, fight_rows = groups[fight]
    floor = fight_rows[0].get("floor")
    seed_v = fight_rows[0].get("seed")
    extra = []
    if floor is not None:
        extra = [r for r in filtered if r.get("kind") in ("reward", "shop")
                 and r.get("floor") == floor and r.get("seed") == seed_v]
    decisions = fight_rows + extra
    page = decisions[offset:offset + limit]
    nxt = offset + len(page)
    return {
        "ok": True,
        "read_only": True,
        "path": found,
        "fight": fight,
        "fight_count": len(groups),
        "seed": seed or None,
        "where": _where(fight_rows[0]),
        "offset": offset,
        "limit": limit,
        "total": len(decisions),
        "next_offset": nxt if nxt < len(decisions) else None,
        "decisions": [_decision(r) for r in page],
    }


def batch_run_summary_json(path):
    return _call(batch_run_summary, path)


def card_ab_json(a, b=""):
    return _call(card_ab, a, b)


def explain_fight_json(path, fight=0, seed="", offset=0, limit=20):
    return _call(explain_fight, path, fight, seed, offset, limit)
