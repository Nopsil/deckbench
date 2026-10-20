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
    return {"slots": slots, "pool": pool, "random": rnd, "source": tag}


# 解析器处理不了、按 C# 手工转写的组成（alternatives = 候选的完整组成及权重）
# 解析器处理不了的少数遭遇不在仓库里手工转写（不分发游戏数据）；这些遭遇由 enemies.py 退回近似组成。
MANUAL = {}


def main(d):
    out = {}
    for f in sorted(os.listdir(d)):
        if f.endswith(".cs"):
            r = parse(os.path.join(d, f))
            if r is not None:
                out[snake(f[:-3])] = r
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
