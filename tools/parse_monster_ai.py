"""从反编译的 C# 源码（Hexpion/Slay-the-spire-2 镜像）解析每个怪物的出招状态机。

用法：python tools/parse_monster_ai.py <镜像里 src/Core/Models/Monsters 目录>
输出：data/monster_ai.json —— {怪物ID: {states, initial, initial_expr, status_cards, source_file}}

只做语法层面的解析（正则 + 语句切分），解析不了的写进 "unparsed"，由 enemies.py 退回 spire-codex 的 attack_pattern。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEW_RE = re.compile(r'new (MoveState|RandomBranchState|ConditionalBranchState)\("([^"]+)"(?:,\s*(\w+))?')
INTENT_RE = re.compile(r'new (\w+)Intent\(([^()]*(?:\([^()]*\)[^()]*)*)\)')
STATUS_RE = re.compile(r'AddToCombatAndPreview<(\w+)>\([^,]+,\s*PileType\.(\w+),\s*([^,)]+)')


def snake(name):
    s = re.sub(r'(?<!^)(?=[A-Z])', '_', name).upper()
    return s


def split_args(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def body_of(src, start_pat):
    i = src.find(start_pat)
    if i < 0:
        return None
    j = src.find("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[j + 1:k]
    return None


def classify_args(args):
    """AddBranch 的各个重载 → (repeat, max_times, cooldown, weight_expr)。"""
    kinds = []
    for a in args:
        if a.startswith("MoveRepeatType."):
            kinds.append("rt")
        elif a.startswith("()"):
            kinds.append("lam")
        elif re.fullmatch(r'-?\d+', a):
            kinds.append("int")
        else:
            kinds.append("float")
    rep, mx, cd, w = "CanRepeatXTimes", None, 0, "1"
    k = tuple(kinds)
    if k == ("int", "rt", "lam") or k == ("int", "rt", "float"):
        cd, rep, w = int(args[0]), args[1].split(".")[1], args[2]
    elif k in (("int", "int", "lam"), ("int", "int", "float")):
        cd, mx, w = int(args[0]), int(args[1]), args[2]
    elif k in (("int", "lam"), ("int", "float")):
        mx, w = int(args[0]), args[1]
    elif k in (("rt", "float"), ("rt", "lam")):
        rep, w = args[0].split(".")[1], args[1]
    elif k == ("int", "rt"):
        cd, rep = int(args[0]), args[1].split(".")[1]
    elif k == ("int",):
        mx = int(args[0])
    elif k == ("rt",):
        rep = args[0].split(".")[1]
    else:
        return None
    if w.startswith("()"):
        w = w.split("=>", 1)[1].strip()
    return {"repeat": rep, "max_times": mx, "cooldown": cd, "weight": w}


def consts_of(src):
    consts = {}
    for cm in re.finditer(r'(?:private|public|protected)[^;{}=]*?\b(\w+)\s*=>\s*AscensionHelper\.GetValueIfAscension\([^,]+,\s*(-?\d+)m?,\s*(-?\d+)m?\)\s*;', src):
        consts[cm.group(1)] = int(cm.group(3))
    for cm in re.finditer(r'(?:private|public|protected)[^;{}=]*?\b(\w+)\s*=>\s*(-?\d+)m?\s*;', src):
        consts.setdefault(cm.group(1), int(cm.group(2)))
    for cm in re.finditer(r'const int (\w+)\s*=\s*(-?\d+)', src):
        consts.setdefault(cm.group(1), int(cm.group(2)))
    return consts


def _val(x, consts):
    x = x.strip().rstrip("m")
    if x.startswith("()"):
        x = x.split("=>", 1)[1].strip()
    if re.fullmatch(r'-?\d+', x):
        return int(x)
    return consts.get(x)


def code_move(st, fb, consts):
    """从意图构造参数 + 招式函数体推出招式数值（spire-codex 没有收录该招式时使用）。"""
    mv = {"damage": 0, "hits": 1, "block": 0, "powers": [], "heal": 0, "unknown": []}
    consts = dict(consts)
    for lm in re.finditer(r'int (\w+) = AscensionHelper\.GetValueIfAscension\([^,]+,\s*(-?\d+),\s*(-?\d+)\)', fb):
        consts[lm.group(1)] = int(lm.group(3))
    for lm in re.finditer(r'int (\w+) = (-?\d+);', fb):
        consts[lm.group(1)] = int(lm.group(2))
    for it in st.get("intents", []):
        args = split_args(it["args"])
        if it["type"] == "SingleAttack" and args:
            v = _val(args[0], consts)
            mv["damage"] = v or 0
            if v is None:
                mv["unknown"].append("damage:" + args[0])
        elif it["type"] == "MultiAttack" and len(args) >= 2:
            v, h = _val(args[0], consts), _val(args[1], consts)
            mv["damage"], mv["hits"] = v or 0, h or 1
            if v is None or h is None:
                mv["unknown"].append("multi:" + it["args"])
    bm = re.search(r'GainBlock\(base\.Creature,\s*([\w.]+)m?', fb)
    if bm:
        v = _val(bm.group(1), consts)
        mv["block"] = v or 0
        if v is None:
            mv["unknown"].append("block:" + bm.group(1))
    # v0.111：PowerCmd.Apply 多了首参 PlayerChoiceContext（new ThrowingPlayerChoiceContext() 等）
    for pm in re.finditer(r'PowerCmd\.Apply<(\w+?)Power>\((?:new \w*PlayerChoiceContext\(\)|choiceContext|ctx|context),\s*([^,]+),\s*([^,]+?),', fb):
        t = pm.group(2).strip()
        tgt = "self" if t == "base.Creature" else ("player" if "target" in t.lower() or "player" in t.lower() else "allies")
        v = _val(pm.group(3), consts)
        if v is None:
            mv["unknown"].append("power:" + pm.group(1) + ":" + pm.group(3))
            continue
        mv["powers"].append({"power_id": snake(pm.group(1)), "target": tgt, "amount": v})
    hm = re.search(r'CreatureCmd\.Heal\(base\.Creature,\s*([\w.]+)', fb)
    if hm:
        mv["heal"] = _val(hm.group(1), consts) or 0
    return mv


def parse_file(path):
    src = open(path, encoding="utf-8").read()
    cls = os.path.basename(path)[:-3]
    body = body_of(src, "GenerateMoveStateMachine()")
    if body is None:
        return None
    var = {}        # 变量/属性名 → 状态 ID
    states = {}
    unparsed = []
    order = []
    stmts = [s.strip() for s in body.split(";")]
    for s in stmts:
        s = re.sub(r'^\}\s*', '', s)
        s = re.sub(r'^(?:if \([^)]*\)|else)\s*\{\s*', '', s).strip()
        if not s or s.startswith("List<MonsterState>") or s.startswith("list.Add") or s.startswith("return") or s.startswith("}"):
            continue
        m = NEW_RE.search(s)
        if m:
            kind, sid, fn = m.group(1), m.group(2), m.group(3)
            st = {"kind": {"MoveState": "move", "RandomBranchState": "random", "ConditionalBranchState": "conditional"}[kind]}
            if st["kind"] == "move":
                st["fn"] = fn
                intents = []
                tail = s[m.end():]
                for im in INTENT_RE.finditer(tail):
                    intents.append({"type": im.group(1), "args": im.group(2)})
                st["intents"] = intents
                st["next"] = None
            else:
                st["branches"] = []
            states[sid] = st
            order.append(sid)
            head = s[:m.start()]
            for t in re.findall(r'([\w\.]+(?:\s+[\w\.]+)?)\s*=(?!=)', head):
                t = t.split()[-1]
                if t.endswith(".FollowUpState"):
                    src_var = t[:-len(".FollowUpState")]
                    if src_var in var:
                        states[var[src_var]]["next"] = sid
                    else:
                        unparsed.append(s)
                else:
                    var[t] = sid
            continue
        m = re.match(r'([\w\.]+)\.FollowUpState\s*=\s*(\w+)$', s)
        if m:
            a, b = m.group(1), m.group(2)
            if a in var and b in var:
                states[var[a]]["next"] = var[b]
            else:
                unparsed.append(s)
            continue
        m = re.match(r'(\w+)\.MustPerformOnceBeforeTransitioning\s*=\s*true$', s)
        if m and m.group(1) in var:
            states[var[m.group(1)]]["must_perform_once"] = True
            continue
        m = re.match(r'(\w+)\.AddBranch\((.*)\)$', s, re.S)
        if m and m.group(1) in var:
            args = split_args(m.group(2))
            tgt = var.get(args[0])
            info = classify_args(args[1:]) if tgt else None
            if info is None:
                unparsed.append(s)
                continue
            info["state"] = tgt
            states[var[m.group(1)]]["branches"].append(info)
            continue
        m = re.match(r'(\w+)\.AddState\((\w+),\s*\(\)\s*=>\s*(.*)\)$', s, re.S)
        if m and m.group(1) in var and m.group(2) in var:
            states[var[m.group(1)]]["branches"].append({"state": var[m.group(2)], "condition": m.group(3).strip()})
            continue
        m = re.match(r'(\w+) = (\w+)$', s)
        if m and m.group(2) in var:
            var[m.group(1)] = var[m.group(2)]
            continue
        m = re.match(r'(?:Monster|Move)State initialState\s*=\s*(.*)$', s, re.S)
        if m:
            var["__initial_expr"] = m.group(1)
            continue
        unparsed.append(s)
    # 初始状态
    rm = re.search(r'return new MonsterMoveStateMachine\((?:list|new [^(]+\((\w+)\)),\s*(.*)\);?\s*$', body.strip(), re.S)
    initial, initial_expr = None, None
    if rm:
        ie = rm.group(2).strip().rstrip(";").rstrip(")")
        if rm.group(2).strip().endswith(")") and ie.count("(") > ie.count(")"):
            ie = ie + ")"
        if ie in var:
            initial = var[ie]
        elif ie == "initialState" and "__initial_expr" in var:
            initial_expr = var["__initial_expr"]
        else:
            initial_expr = ie
        if initial_expr:
            # 把表达式里的变量名换成状态 ID
            for k in sorted(var, key=len, reverse=True):
                if not k.startswith("__"):
                    initial_expr = re.sub(r'\b%s\b' % re.escape(k), '"%s"' % var[k], initial_expr)
    if isinstance(initial_expr, str) and "MonsterMoveStateMachine" in initial_expr:
        ids = re.findall(r'"([^"]+)"', initial_expr)
        initial, initial_expr = ids[-1], None
    # (StarterMoveIdx % 3) switch { 0 => X, 1 => Y, _ => Z }
    sm = re.search(r'\((\w+) % 3\) switch\s*\{(.*?)\}', body, re.S)
    if sm:
        cases = re.findall(r'(?:\d+|_)\s*=>\s*(?:new MonsterMoveStateMachine\(list,\s*)?(\w+)', sm.group(2))
        if all(c in var for c in cases):
            initial, initial_expr = None, {"switch": sm.group(1), "cases": [var[c] for c in cases]}
            dm = re.search(r'if \(%s == -1\)\s*\{\s*return new MonsterMoveStateMachine\(list,\s*(\w+)\)' % sm.group(1), body)
            if dm and dm.group(1) in var:
                initial_expr["default"] = var[dm.group(1)]
    # 也有「if (...) return new MonsterMoveStateMachine(list, X);」的写法：取最后一个 return 作默认
    if initial is None and initial_expr is None:
        rets = re.findall(r'return new MonsterMoveStateMachine\(list,\s*(\w+)\)', body)
        if rets and rets[-1] in var:
            initial = var[rets[-1]]
    # 招式函数里塞的状态牌
    status = {}
    for sid, st in states.items():
        if st["kind"] != "move" or not st.get("fn"):
            continue
        fb = body_of(src, f"Task {st['fn']}(")
        if not fb:
            continue
        cards = []
        for sm in STATUS_RE.finditer(fb):
            cards.append({"card": snake(sm.group(1)), "pile": sm.group(2), "n": sm.group(3).strip()})
        if cards:
            status[sid] = cards
        sets = {}
        for am in re.finditer(r'\b(\w+)\s*=\s*(true|false)\s*;', fb):
            sets[am.group(1).lstrip("_")] = am.group(2) == "true"
        for am in re.finditer(r'\b(\w+)\+\+', fb):
            sets[am.group(1).lstrip("_")] = "++"
        if sets:
            st["sets"] = sets
        st["code_move"] = code_move(st, fb, consts_of(src))
        st["summons"] = False
        st["escapes"] = "CreatureCmd.Escape" in fb
    # 构造/字段默认值里的数字常量（状态牌数量常写成属性）
    consts = {}
    for cm in re.finditer(r'(?:private|public|protected)[^;{=]*?\b(\w+)\s*=>\s*(?:AscensionHelper\.GetValueIfAscension\([^,]+,\s*-?\d+,\s*(-?\d+)\)|(-?\d+))\s*;', src):
        consts[cm.group(1)] = int(cm.group(2) or cm.group(3))
    for cm in re.finditer(r'const int (\w+)\s*=\s*(-?\d+)', src):
        consts[cm.group(1)] = int(cm.group(2))
    fields = {}
    for fm in re.finditer(r'(?:private|public|protected|internal)\s+(?:static\s+)?(bool|int)\s+(_?\w+)\s*(?:=\s*(true|false|-?\d+))?\s*;', src):
        t, n, v = fm.groups()
        fields[n.lstrip("_")] = (v == "true") if t == "bool" else int(v or 0)
    for fm in re.finditer(r'public\s+(bool|int)\s+(\w+)\s*\{\s*get', src):
        fields.setdefault(fm.group(2), False if fm.group(1) == "bool" else 0)
    return {"class": cls, "fields": fields, "states": states, "order": order, "initial": initial, "initial_expr": initial_expr,
            "status_cards": status, "consts": consts, "unparsed": unparsed}


def main(src_dir):
    out = {}
    for f in sorted(os.listdir(src_dir)):
        if not f.endswith(".cs"):
            continue
        r = parse_file(os.path.join(src_dir, f))
        if r is None:
            continue
        out[snake(f[:-3])] = r
    path = os.path.join(os.environ.get("DECKBENCH_OUT") or os.path.join(ROOT, "data"), "monster_ai.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = {k: v["unparsed"] for k, v in out.items() if v["unparsed"]}
    noinit = [k for k, v in out.items() if not v["initial"] and not v["initial_expr"]]
    print(f"解析 {len(out)} 个怪物；有未解析语句 {len(bad)} 个；无初始状态 {len(noinit)} 个")
    for k, v in bad.items():
        print(" -", k, v[:2])
    print(" 无初始:", noinit)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: parse_monster_ai.py <decompiled Core/Models/Monsters dir>"))
