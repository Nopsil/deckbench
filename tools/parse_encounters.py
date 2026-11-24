"""从反编译 Encounters/*.cs 的 GenerateMonsters() 解析遭遇的真实怪物组成（spire-codex 的 encounters.json 只列了去重后的怪物种类）。

输出 data/encounter_monsters.json：{遭遇ID: {"slots": [[可能的怪物ID, ...], ...], "random": bool, "source": "代码"/"近似"}}
每个位置是候选列表：长度 1 = 固定；>1 = 代码里用 Rng 二选一/多选一（模拟时均匀抽取，近似）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from parse_monster_ai import body_of, snake, split_args  # noqa


def _lists(src):
    """静态候选列表/计数字典：名字 → [怪物ID] 或 {怪物ID: 上限}。"""
    out = {}
    for m in re.finditer(r'(\w+)\s*(?:=>|=)\s*new MonsterModel\[\d*\]\s*\{(.*?)\};', src, re.S):
        out[m.group(1)] = [snake(x) for x in re.findall(r'Monster<(\w+)>', m.group(2))]
    for m in re.finditer(r'Dictionary<MonsterModel, int> (\w+) = new Dictionary<MonsterModel, int>\s*\{(.*?)\n\t\};', src, re.S):
        out[m.group(1)] = {snake(a): int(b) for a, b in re.findall(r'Monster<(\w+)>\(\),\s*(\d+)', m.group(2))}
    return out


def _slot_of(expr, var, lists):
    mm = re.match(r'\s*ModelDb\.Monster<(\w+)>', expr)
    if mm:
        return [snake(mm.group(1))]
    mm = re.match(r'\s*base\.Rng\.NextItem\((\w+)\)', expr)
    if mm and isinstance(lists.get(mm.group(1)), list):
        return list(lists[mm.group(1)])
    v = expr.split(".")[0].strip()
    return var.get(v)


def _paren_groups(body, needle):
    """needle 结尾停在要读的左括号上。返回每一处括号里的文本。"""
    out = []
    start = 0
    while True:
        j = body.find(needle, start)
        if j < 0:
            break
        i = j + len(needle) - 1
        if i >= len(body) or body[i] != "(":
            start = j + 1
            continue
        depth = 0
        for k in range(i, len(body)):
            if body[k] == "(":
                depth += 1
            elif body[k] == ")":
                depth -= 1
                if depth == 0:
                    out.append(body[i + 1:k])
                    start = k + 1
                    break
        else:
            break
    return out


def _assign_map(body, lists):
    assigns = {}
    for match in re.finditer(r'(\w+)\s*=\s*(\w+)\.ToList\(\)', body):
        opts = lists.get(match.group(2))
        if isinstance(opts, list):
            assigns[match.group(1)] = list(opts)
    for match in re.finditer(r'(\w+)\s*=\s*(?:\([^)]*\)\s*)?ModelDb\.Monster<(\w+)>', body):
        assigns[match.group(1)] = [snake(match.group(2))]
    for match in re.finditer(r'(\w+)\s*=\s*(?:\(\w+\))?base\.Rng\.NextItem\((\w+)\)', body):
        opts = lists.get(match.group(2))
        if isinstance(opts, list):
            assigns[match.group(1)] = list(opts)
        elif isinstance(assigns.get(match.group(2)), list):
            assigns[match.group(1)] = list(assigns[match.group(2)])
    return assigns


def _resolve_name(name, lists, assigns):
    if isinstance(lists.get(name), list):
        return list(lists[name])
    if isinstance(assigns.get(name), list):
        return list(assigns[name])
    return None


def _expr_slot(expr, lists, assigns):
    expr = expr.strip()
    if "NextItem" in expr:
        match = re.search(r'NextItem\((\w+)\)', expr)
        return _resolve_name(match.group(1), lists, assigns) if match else None
    match = re.search(r'ModelDb\.Monster<(\w+)>', expr)
    if match:
        return [snake(match.group(1))]
    match = re.match(r'(\w+)\.ToMutable\(\)', expr)
    if match:
        return assigns.get(match.group(1))
    if re.fullmatch(r'\w+', expr):
        return assigns.get(expr)
    return None


def _tuple_slots(body, lists):
    assigns = _assign_map(body, lists)
    slots = []
    for inner in _paren_groups(body, ".Add("):
        if not inner.startswith("("):
            continue
        inner = inner[1:].removesuffix(")")
        first = split_args(inner)[0] if inner.strip() else ""
        slot = _expr_slot(first, lists, assigns)
        if not slot:
            return None
        slots.append(slot)
    return slots


def _slot_count(src):
    match = re.search(r'string\[(\d+)\]', src)
    return int(match.group(1)) if match else 0


def _brace_block(text, open_at):
    depth = 0
    for k in range(open_at, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:k], k + 1
    return None, None


def _case_comps(case, lists):
    tokens = []
    for match in re.finditer(r'ModelDb\.Monster<(\w+)>|NextItem\((\w+)\)', case):
        if match.group(1):
            tokens.append([snake(match.group(1))])
            continue
        opts = lists.get(match.group(2))
        if not isinstance(opts, list):
            return None
        tokens.append(list(opts))
    if not tokens:
        return None
    comps = [[]]
    for opts in tokens:
        comps = [row + [opt] for row in comps for opt in opts]
    return comps


def _switch_alternatives(body, lists):
    match = re.search(r'\bswitch\s*\(', body)
    if not match:
        return None
    brace = body.find("{", match.end())
    if brace < 0:
        return None
    block, end = _brace_block(body, brace)
    if block is None:
        return None
    tail = [snake(name) for name in re.findall(r'ModelDb\.Monster<(\w+)>', body[end:])]
    alts = []
    for case in re.split(r'\bcase\s+[\w.]+\s*:', block)[1:]:
        case = case.split("break;", 1)[0]
        comps = _case_comps(case, lists)
        if not comps:
            continue
        # 每个 case 先等权，case 里面的组合再平分。这样「三选一，再在组里抽」不会被组合数量淹没。
        share = 1 / len(comps)
        for comp in comps:
            alts.append([share, comp + tail])
    return alts or None


def _fallback(src, body, lists):
    """v0.113.1 里几种旧正则盖不住的 GenerateMonsters。"""
    slots = _tuple_slots(body, lists)
    if slots:
        if re.search(r'foreach\s*\([^)]*\bSlots\b', body) and len(slots) == 1:
            count = _slot_count(src)
            if count:
                slots = [list(slots[0]) for _ in range(count)]
        random_comp = "Rng" in body or any(len(slot) != 1 for slot in slots)
        return {"slots": slots, "pool": None, "random": random_comp or "Rng" in body,
                "source": "代码(随机组成)" if random_comp else "代码"}
    alts = _switch_alternatives(body, lists)
    if alts:
        return {"slots": [], "pool": None, "random": True, "source": "代码(随机组成)", "alternatives": alts}
    return None


def parse(path):
    src = open(path, encoding="utf-8").read()
    b = body_of(src, "GenerateMonsters()")
    if b is None:
        return None
    lists = _lists(src)
    var = {}
    for m in re.finditer(r'(\w+) (\w+) = \(\w+\)ModelDb\.Monster<(\w+)>\(\)\.ToMutable\(\)', b):
        var[m.group(2)] = [snake(m.group(3))]
    for m in re.finditer(r'MonsterModel (\w+) = \((.*?)\);\n', b):
        var[m.group(1)] = [snake(x) for x in re.findall(r'ModelDb\.Monster<(\w+)>', m.group(2))]
    slots, ok, pool = [], True, None
    # 1) 数组 / 单元素列表
    rm = re.search(r'\[\d*\]\s*\{(.*)\}\s*\)', b, re.S)
    sm = re.search(r'ReadOnlySingleElementList<[^>]*>\>?\(\((.*)\)\);', b, re.S)
    if rm:
        for tup in re.findall(r'\(([^()]*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)[^()]*)*)\)\s*,?', rm.group(1)):
            r = _slot_of(split_args(tup)[0], var, lists)
            ok &= bool(r)
            slots.append(r or [])
    elif sm:
        r = _slot_of(split_args(sm.group(1))[0], var, lists)
        ok &= bool(r)
        slots.append(r or [])
    else:
        # 2) span[i] = (...) 逐个赋值
        for t in re.findall(r'span\[\w+\] = \((.*?)\);', b):
            r = _slot_of(split_args(t)[0], var, lists)
            ok &= bool(r)
            slots.append(r or [])
        # 3) for 循环按计数字典抽
        lm = re.search(r'for \(int i = 0; i < (\d+); i\+\+\).*?(\w+ValidCounts)', b, re.S)
        if lm and isinstance(lists.get(lm.group(2)), dict):
            pool = {"n": int(lm.group(1)), "options": lists[lm.group(2)]}
        if not slots and not pool:
            ok = False
    rnd = "Rng" in b
    if not ok:
        tag = "缺失"
    elif pool or any(len(x) > 1 for x in slots):
        tag = "代码(随机组成)"
    else:
        tag = "代码"
    result = {"slots": slots, "pool": pool, "random": rnd, "source": tag}
    if tag == "缺失":
        alt = _fallback(src, b, lists)
        if alt:
            return alt
    return result


# 解析器处理不了、按 C# 手工转写的组成（alternatives = 候选的完整组成及权重）
# 解析器处理不了的少数遭遇不在仓库里手工转写（不分发游戏数据）；这些遭遇由 enemies.py 退回近似组成。
MANUAL = {}


def parse_dir(directory):
    out = {}
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".cs"):
            continue
        parsed = parse(os.path.join(directory, name))
        if parsed is not None:
            out[snake(name[:-3])] = parsed
    return out


def main(d):
    out = parse_dir(d)
    for k, v in MANUAL.items():
        out[k] = {"slots": [], "pool": None, "random": True, "source": "代码(手工转写)", **v}
    json.dump(out, open(os.path.join(os.environ.get("DECKBENCH_OUT") or os.path.join(ROOT, "data"), "encounter_monsters.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(out), Counter(v["source"] for v in out.values()))
    for k, v in out.items():
        if v["source"] != "代码":
            print(" ", k, v["source"], v["slots"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: parse_encounters.py <decompiled Core/Models/Encounters dir>"))
