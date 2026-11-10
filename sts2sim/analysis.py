"""只读分析已经跑完的结果，给 MCP 和决策说明页用。不新开模拟，不写文件。

路径必须落在允许的目录里（realpath，符号链接按目标算）：

- 界面数据目录：``STS2SIM_GUI_DATA``，否则 ``gui/.data``
- DeckBench 缓存（``DECKBENCH_CACHE``，否则用户缓存下的 ``deckbench``）及其 ``mcp_runs``
- ``DECKBENCH_ANALYSIS_ROOTS``：用 ``os.pathsep`` 分开的额外目录

存档树（``saves`` / ``history`` / ``SlayTheSpire2``、本机游戏数据根）和 ``.run`` / ``.save``
用 ``saveimport.refuse_save_write`` 的同一套规则拒绝，连读都不读。
"""
import json
import os

from sts2sim.explain import combat_groups, num, top
from sts2sim.saveimport import SaveImportError, refuse_save_write

_KINDS = ("play", "target", "potion", "reward", "shop")
_DECISION_KEYS = ("seq", "kind", "turn", "floor", "act", "room", "encounter", "fight", "card", "threshold", "note")
_MAX_LIMIT = 100
# 选中项和次高分的差不超过这个值，界面标成「分差很小」。绝对分差，四种 AI 的分数都能用。
CLOSE_GAP = 0.5
_LOG_SKIP = {"saves", "history", "SlayTheSpire2", "node_modules", ".git", "__pycache__"}
_LOG_LIMIT = 200
_LOG_DEPTH = 6


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
    shown = path.strip().split("\x00", 1)[0]
    if "\x00" in path:
        raise AnalysisError("path_not_allowed", path=shown)
    try:
        raw = os.path.abspath(os.path.expanduser(path.strip()))
        real = _realpath(raw)
    except (TypeError, ValueError, OSError):
        raise AnalysisError("path_not_allowed", path=shown)
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
    from sts2sim.saveimport import MAX_BYTES
    rows = []
    try:
        if os.path.getsize(path) > MAX_BYTES:
            raise AnalysisError("too_big", path=path)
        fh = open(path, "r", encoding="utf-8-sig")
    except AnalysisError:
        raise
    except OSError:
        raise AnalysisError("unreadable", path=path)
    with fh:
        try:
            for i, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, RecursionError):
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


def _prepare_explain(path):
    found = _explain_file(path)
    rows = _load_jsonl(found)
    if not any(r.get("kind") in _KINDS for r in rows):
        raise AnalysisError("not_explain", path=found)
    return found, rows


def _filtered_rows(rows, seed):
    if seed:
        return [r for r in rows if str(r.get("seed")) == seed]
    return rows


def _fight_bundle(filtered, fight):
    """一场战斗的行，加上同一层的奖励和商店。和 explain_fight 用的是同一段。"""
    groups = combat_groups(filtered)
    if fight >= len(groups):
        return groups, None, []
    _key, fight_rows = groups[fight]
    floor = fight_rows[0].get("floor")
    seed_v = fight_rows[0].get("seed")
    extra = []
    if floor is not None:
        extra = [r for r in filtered if r.get("kind") in ("reward", "shop")
                 and r.get("floor") == floor and r.get("seed") == seed_v]
    return groups, fight_rows, fight_rows + extra


def explain_fight(path, fight=0, seed="", offset=0, limit=20):
    if not isinstance(seed, str):
        raise AnalysisError("bad_seed")
    fight = _index("fight", fight, 0)
    offset = _index("offset", offset, 0)
    limit = min(_index("limit", limit, 1), _MAX_LIMIT)
    found, rows = _prepare_explain(path)
    filtered = _filtered_rows(rows, seed)
    groups, fight_rows, decisions = _fight_bundle(filtered, fight)
    if fight_rows is None:
        if not groups and fight == 0:
            return {
                "ok": True, "read_only": True, "path": found, "fight": 0, "fight_count": 0,
                "seed": seed or None, "where": {}, "offset": offset, "limit": limit, "total": 0,
                "next_offset": None, "decisions": [],
            }
        raise AnalysisError("fight_out_of_range", fight=fight, fight_count=len(groups))
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


def _seed_label(row):
    seed = row.get("seed")
    if seed is None:
        return None
    return str(seed)


def _run_entry(seed, char, filtered):
    groups = combat_groups(filtered)
    fights = []
    for i, (_key, fight_rows) in enumerate(groups):
        _groups, _rows, decisions = _fight_bundle(filtered, i)
        turns = []
        for row in fight_rows:
            turn = row.get("turn")
            if turn is not None and turn not in turns:
                turns.append(turn)
        fights.append({
            "fight": i,
            "where": _where(fight_rows[0]),
            "decisions": len(decisions),
            "turns": turns,
        })
    return {"seed": seed, "char": char, "fights": fights}


def explain_catalog(path):
    """一份日志里有哪些种子、每个种子有哪些战斗。场次序号和 explain_fight 的 fight 相同。"""
    found, rows = _prepare_explain(path)
    labels = []
    chars = {}
    for row in rows:
        if row.get("kind") not in _KINDS:
            continue
        label = _seed_label(row)
        if label not in labels:
            labels.append(label)
            chars[label] = row.get("char") if isinstance(row.get("char"), str) else None
        elif chars.get(label) is None and isinstance(row.get("char"), str):
            chars[label] = row.get("char")
    concrete = [label for label in labels if label]
    if concrete:
        runs = [_run_entry(label, chars.get(label), _filtered_rows(rows, label)) for label in concrete]
    else:
        runs = [_run_entry(None, chars.get(None), rows)]
    return {"ok": True, "read_only": True, "path": found, "runs": runs}


def _option_key(item):
    return (item.get("id"), item.get("target"), item.get("hand"))


def _score_of(item):
    if not isinstance(item, dict) or "score" not in item:
        return None
    return num(item.get("score"))


def decision_margin(decision):
    """选中分数减去其余候选里的最高分。没有第二名或缺分数时 margin 为 None。

    close 为真表示绝对分差不超过 CLOSE_GAP（含打平，以及略低于次高的改写）。
    """
    chosen = decision.get("chosen")
    cands = [c for c in (decision.get("candidates") or []) if isinstance(c, dict)]
    if isinstance(chosen, list):
        chosen_list = [c for c in chosen if isinstance(c, dict)]
    elif isinstance(chosen, dict):
        chosen_list = [chosen]
    else:
        chosen_list = []
    chosen_keys = set()
    for item in chosen_list:
        if item.get("id") is None and item.get("kind") == "end":
            continue
        chosen_keys.add(_option_key(item))
    scores = []
    for item in chosen_list:
        score = _score_of(item)
        if score is None:
            key = _option_key(item)
            for cand in cands:
                if _option_key(cand) == key:
                    score = _score_of(cand)
                    if score is not None:
                        break
        if score is not None:
            scores.append(score)
    chosen_score = min(scores) if scores else None
    runner = None
    runner_score = None
    for cand in cands:
        if cand.get("picked") or _option_key(cand) in chosen_keys:
            continue
        score = _score_of(cand)
        if score is None:
            continue
        if runner_score is None or score > runner_score:
            runner = cand
            runner_score = score
    runner_up = None
    if runner is not None:
        runner_up = {}
        for key in ("id", "name", "target", "hand"):
            if runner.get(key) is not None:
                runner_up[key] = runner[key]
        runner_up["score"] = runner_score
    if chosen_score is None or runner_up is None:
        return {"margin": None, "close": False, "runner_up": runner_up, "chosen_score": chosen_score}
    margin = num(chosen_score - runner_score)
    return {
        "margin": margin,
        "close": margin is not None and abs(margin) <= CLOSE_GAP,
        "runner_up": runner_up,
        "chosen_score": chosen_score,
    }


def explain_page(path, fight=0, seed="", offset=0, limit=20):
    """explain_fight 的一页，每条决策加上和次高分的差距。不重新读文件格式，不写。"""
    doc = explain_fight(path, fight, seed, offset, limit)
    out = dict(doc)
    out["close_gap"] = CLOSE_GAP
    annotated = []
    for decision in doc["decisions"]:
        item = dict(decision)
        item.update(decision_margin(decision))
        annotated.append(item)
    out["decisions"] = annotated
    return out


def explain_logs():
    """允许的目录里已有的说明日志。只列路径，不读内容，不创建目录。"""
    logs = []
    seen = set()
    truncated = False
    for root in allowed_roots():
        if truncated:
            break
        for dirpath, dirnames, names in os.walk(root, followlinks=False):
            rel = os.path.relpath(dirpath, root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth >= _LOG_DEPTH:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if d not in _LOG_SKIP and not d.startswith(".")]
            for name in sorted(names):
                if name != "explain.jsonl" and not name.endswith(".explain.jsonl"):
                    continue
                try:
                    real = resolve_read(os.path.join(dirpath, name))
                except AnalysisError:
                    continue
                if not os.path.isfile(real) or real in seen:
                    continue
                seen.add(real)
                logs.append({"path": real, "name": os.path.basename(real)})
                if len(logs) >= _LOG_LIMIT:
                    truncated = True
                    break
            if truncated:
                break
    logs.sort(key=lambda item: item["path"])
    return {"ok": True, "read_only": True, "logs": logs, "truncated": truncated}


def batch_run_summary_json(path):
    return _call(batch_run_summary, path)


def card_ab_json(a, b=""):
    return _call(card_ab, a, b)


def explain_fight_json(path, fight=0, seed="", offset=0, limit=20):
    return _call(explain_fight, path, fight, seed, offset, limit)
