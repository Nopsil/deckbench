"""胜率的 Wilson 区间、两比例 z 检验，以及样本太小时的警告。

批量整局和单卡 A/B 的文本、Markdown、JSON 都从这里取数，只追加字段，不改旧字段的含义。
Wilson 用 z=1.96（双侧 95%），和 Newcombe 1998 表 I 的 score 法（无连续性修正）对到小数点后四位。
两比例检验是合并比例的双侧 z 检验：H0 为两组胜率相同，diff 是 B − A。
任一组有效局数小于 MIN_N（30）时，数字照常给出，并标明不能下结论。
"""
import json
import math

MIN_N = 30
Z95 = 1.96


def wilson_interval(wins, n, z=Z95):
    """二项比例的 Wilson 区间，夹在 [0, 1]。n<=0 时返回 (None, None)。"""
    n = int(n)
    if n <= 0:
        return None, None
    wins = float(wins)
    p = wins / n
    z2 = z * z
    den = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / den
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def two_proportion_ztest(wins_a, n_a, wins_b, n_b):
    """合并比例的双侧两比例 z 检验。任一侧 n<=0 时 p 值和 z 为 None。

    两侧比例都是 0 或都是 1 时标准误为 0：差值是 0 则 p=1，否则 p=0、z 为 None
    （z 会是无穷，JSON 里不写 Infinity）。
    """
    n_a = float(n_a)
    n_b = float(n_b)
    out = {"diff": None, "z": None, "p_value": None, "se": None, "method": "two_proportion_z"}
    if n_a <= 0 or n_b <= 0:
        return out
    diff = wins_b / n_b - wins_a / n_a
    p = (float(wins_a) + float(wins_b)) / (n_a + n_b)
    var = p * (1.0 - p) * (1.0 / n_a + 1.0 / n_b)
    out["diff"] = diff
    if var <= 0.0:
        out["se"] = 0.0
        if diff == 0.0:
            out["z"] = 0.0
            out["p_value"] = 1.0
        else:
            out["p_value"] = 0.0
        return out
    se = math.sqrt(var)
    z = diff / se
    out["se"] = se
    out["z"] = z
    out["p_value"] = math.erfc(abs(z) / math.sqrt(2.0))
    return out


def _warning_text(n_a, n_b=None):
    if n_b is None:
        return f"样本不足，不能下结论 / sample too small to conclude: n={int(n_a)} < {MIN_N}"
    return (f"样本不足，不能下结论 / sample too small to conclude: "
            f"n={int(n_a)} and n={int(n_b)} < {MIN_N}")


def min_sample_fields(n_a, n_b=None):
    """n 小于 MIN_N 时 sample_warning 为真。n_b 缺省表示只有一组。"""
    small = int(n_a) < MIN_N or (n_b is not None and int(n_b) < MIN_N)
    return {
        "min_n": MIN_N,
        "sample_warning": small,
        "sample_warning_code": "n_below_minimum" if small else None,
        "sample_warning_text": _warning_text(n_a, n_b) if small else None,
    }


def win_rate_fields(wins, n):
    """加在已有胜率字段旁边。不含 wins / n / win，避免覆盖调用方的同名字段。"""
    lo, hi = wilson_interval(wins, n)
    return {
        "win_ci_low": lo,
        "win_ci_high": hi,
        "win_ci_method": "wilson" if lo is not None else None,
        **min_sample_fields(n),
    }


def win_rate_report(wins, n):
    n = int(n)
    wins = float(wins)
    rep = {
        "wins": wins,
        "n": n,
        "win": (wins / n) if n else None,
        **win_rate_fields(wins, n),
    }
    return rep


def proportion_compare_fields(wins_a, n_a, wins_b, n_b):
    """A/B 胜率（或其它 0/1 比例）上追加的字段：Wilson 区间、z、p 值、样本警告。"""
    test = two_proportion_ztest(wins_a, n_a, wins_b, n_b)
    a_lo, a_hi = wilson_interval(wins_a, n_a)
    b_lo, b_hi = wilson_interval(wins_b, n_b)
    return {
        "p_value": test["p_value"],
        "z": test["z"],
        "test": test["method"],
        "a_ci_low": a_lo,
        "a_ci_high": a_hi,
        "b_ci_low": b_lo,
        "b_ci_high": b_hi,
        "ci_method": "wilson" if a_lo is not None and b_lo is not None else None,
        **min_sample_fields(n_a, n_b),
    }


def ab_win_report(wins_a, n_a, wins_b, n_b):
    """给文本 / Markdown / JSON 的胜率 A/B。diff 是 B 的胜率减 A 的胜率（边际差）。

    界面上的配对差仍放在原来的 diff 字段里，这里不拿这个 diff 去覆盖它。
    """
    test = two_proportion_ztest(wins_a, n_a, wins_b, n_b)
    return {
        "a": win_rate_report(wins_a, n_a),
        "b": win_rate_report(wins_b, n_b),
        "diff": test["diff"],
        **proportion_compare_fields(wins_a, n_a, wins_b, n_b),
    }


def _pct(x):
    if x is None:
        return "—"
    return f"{100.0 * x:.1f}%"


def _fmt_p(p):
    if p is None:
        return "—"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}"


def _fmt_z(z):
    if z is None:
        return "—"
    return f"{z:+.3f}"


def format_win_rate(rep, kind="text"):
    """同一次胜率报告的文本、Markdown 或 JSON。kind 为 json 时返回字符串。"""
    if kind == "json":
        return json.dumps(rep, ensure_ascii=False, indent=1) + "\n"
    n = rep.get("n") or 0
    wins = rep.get("wins")
    if kind == "markdown":
        lines = [
            "| 胜率 | 局数 | Wilson 95% 下限 | Wilson 95% 上限 | 样本 |",
            "|---|---|---|---|---|",
            f"| {_pct(rep.get('win'))} | {int(wins) if wins is not None else 0}/{n} | "
            f"{_pct(rep.get('win_ci_low'))} | {_pct(rep.get('win_ci_high'))} | "
            f"{'不足，不能下结论' if rep.get('sample_warning') else '够'} |",
        ]
        if rep.get("sample_warning_text"):
            lines += ["", "> " + rep["sample_warning_text"]]
        return "\n".join(lines) + "\n"
    wins_i = int(wins) if wins is not None else 0
    if not n or rep.get("win") is None:
        body = "胜率 / win rate: 0/0"
    else:
        body = (f"胜率 / win rate: {wins_i}/{n} = {_pct(rep.get('win'))}  "
                f"Wilson 95% CI {_pct(rep.get('win_ci_low'))}–{_pct(rep.get('win_ci_high'))}")
    if rep.get("sample_warning_text"):
        return body + "\n" + rep["sample_warning_text"] + "\n"
    return body + "\n"


def format_ab(rep, kind="text"):
    """单卡（或两组）胜率 A/B：文本、Markdown 或 JSON。"""
    if kind == "json":
        return json.dumps(rep, ensure_ascii=False, indent=1) + "\n"
    a, b = rep.get("a") or {}, rep.get("b") or {}
    if kind == "markdown":
        lines = [
            "| 组 | 胜 | 局数 | 胜率 | Wilson 95% |",
            "|---|---|---|---|---|",
            f"| A | {int(a.get('wins') or 0)} | {a.get('n') or 0} | {_pct(a.get('win'))} | "
            f"{_pct(a.get('win_ci_low'))}–{_pct(a.get('win_ci_high'))} |",
            f"| B | {int(b.get('wins') or 0)} | {b.get('n') or 0} | {_pct(b.get('win'))} | "
            f"{_pct(b.get('win_ci_low'))}–{_pct(b.get('win_ci_high'))} |",
            "",
            f"两比例 z 检验 / two-proportion z-test (B − A): z={_fmt_z(rep.get('z'))}  "
            f"p={_fmt_p(rep.get('p_value'))}  diff={_pct(rep.get('diff'))}",
        ]
        if rep.get("sample_warning_text"):
            lines += ["", "> " + rep["sample_warning_text"]]
        return "\n".join(lines) + "\n"
    lines = [
        "胜率 / win rate  "
        f"A {int(a.get('wins') or 0)}/{a.get('n') or 0} = {_pct(a.get('win'))} "
        f"(Wilson 95% CI {_pct(a.get('win_ci_low'))}–{_pct(a.get('win_ci_high'))})  "
        f"B {int(b.get('wins') or 0)}/{b.get('n') or 0} = {_pct(b.get('win'))} "
        f"(Wilson 95% CI {_pct(b.get('win_ci_low'))}–{_pct(b.get('win_ci_high'))})",
        f"两比例 z 检验 / two-proportion z-test: z={_fmt_z(rep.get('z'))}  "
        f"p={_fmt_p(rep.get('p_value'))}  (B − A = {_pct(rep.get('diff'))})",
    ]
    if rep.get("sample_warning_text"):
        lines.append(rep["sample_warning_text"])
    return "\n".join(lines) + "\n"
