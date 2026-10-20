"""C# → Python 转译器（只覆盖 StS2 反编译模型代码用到的子集）。

把 Models/{Cards,Powers,Relics,Potions,Orbs,...}/*.cs 的整个类（字段、属性、方法、构造参数）翻成 Python 类，
运行时 API（DamageCmd、PowerCmd、CardPileCmd…、CardModel/PowerModel 基类）由 sts2sim/rt 提供。
规则：
  - await 去掉；async 方法 → 普通函数；Task.CompletedTask → None
  - 泛型实参前置：PowerCmd.Apply<VulnerablePower>(a, b) → PowerCmd.Apply(VulnerablePower, a, b)
  - out 参数：方法返回 (返回值, out1, ...)；调用处 f(x, out var v) → _outcall 辅助
  - 视觉/音效语句（VfxCmd、SfxCmd、N* 节点、Cmd.Wait、TriggerAnim…）丢弃
  - base.X / 裸成员名 → self.X；同名覆盖方法里的 base.M() → super().M()
用法： python tools/cs2py.py <Core目录> <输出目录> [子目录...]
"""
import os
import re
import sys
import json

OPS = [">>=", "<<=", "??=", "?.", "??", "=>", "==", "!=", "<=", ">=", "&&", "||", "++", "--", "+=", "-=", "*=", "/=",
       "%=", "&=", "|=", "^=", "<<", "::"]
KEYWORDS_TYPES = {"int", "decimal", "float", "double", "long", "bool", "string", "uint", "byte", "object", "void", "var",
                  "short", "ulong", "char", "dynamic"}
PY_RESERVED = {"from", "in", "is", "lambda", "pass", "def", "class", "global", "with", "yield", "print", "None", "not",
               "and", "or", "del", "exec", "nonlocal", "assert", "raise", "except", "import", "elif", "True", "False",
               "async", "await", "type", "list", "len", "id", "str", "max", "min", "sum", "any", "all", "range", "set", "dict"}


class Tok:
    __slots__ = ("k", "v", "ln")

    def __init__(self, k, v, ln=0):
        self.k, self.v, self.ln = k, v, ln

    def __repr__(self):
        return f"{self.k}:{self.v}"


def lex(src):
    import bisect
    out = []
    i, n = 0, len(src)
    nls = [m.start() for m in re.finditer("\n", src)]

    def Tok(k, v):
        return _Tok(k, v, bisect.bisect(nls, i) + 1)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "#":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == '"' or (c in "$@" and i + 1 < n and src[i + 1] in '"$@'):
            j = i
            interp = False
            verb = False
            while src[j] in "$@":
                interp |= src[j] == "$"
                verb |= src[j] == "@"
                j += 1
            j += 1
            buf = []
            depth = 0
            while j < n:
                ch = src[j]
                if interp and ch == "{":
                    if j + 1 < n and src[j + 1] == "{":
                        buf.append("{"); j += 2; continue
                    depth += 1
                elif interp and ch == "}" and depth:
                    depth -= 1
                elif ch == "\\" and not verb:
                    buf.append(src[j:j + 2]); j += 2; continue
                elif ch == '"' and depth == 0:
                    if verb and j + 1 < n and src[j + 1] == '"':
                        buf.append('\\"'); j += 2; continue
                    break
                buf.append(ch)
                j += 1
            out.append(Tok("istr" if interp else "str", "".join(buf)))
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            j += 2 if src[j] == "\\" else 1
            out.append(Tok("str", src[i + 1:j]))
            i = j + 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            m = re.match(r"0[xX][0-9a-fA-F]+|\d*\.?\d+(?:[eE][+-]?\d+)?[mMfFdDuUlL]*", src[i:])
            out.append(Tok("num", m.group(0)))
            i += len(m.group(0))
            continue
        if c.isalpha() or c == "_" or c == "@":
            m = re.match(r"@?[A-Za-z_][A-Za-z0-9_]*", src[i:])
            out.append(Tok("id", m.group(0).lstrip("@")))
            i += len(m.group(0))
            continue
        for op in OPS:
            if src.startswith(op, i):
                out.append(Tok("op", op))
                i += len(op)
                break
        else:
            out.append(Tok("op", c))
            i += 1
    out.append(Tok("eof", ""))
    return out


_Tok = Tok


class Unsupported(Exception):
    pass


class _AssignSignal(Exception):
    def __init__(self, left, op, right, post=False):
        self.left, self.op, self.right, self.post = left, op, right, post


class _DropSignal(Exception):
    pass


KNOWN_MODELS = set()
GLOBAL_TYPES = set()
DROP_IDS = {"VfxCmd", "SfxCmd", "SaveManager", "Color", "Colors", "Vector2", "Tween", "GD",
            "Godot", "PreloadManager", "AudioManager", "TalkCmd", "ThinkCmd", "NGame", "Log", "Callable", "SceneHelper",
            "HoverTipFactory", "ImageHelper", "LocString", "Logger", "ScreenShake", "Shake", "ShakeStrength",
            "ShakeDuration", "FastModeType", "NodePath", "StringName", "Engine", "DisplayServer", "Input"}
DROP_METHODS = {"TriggerAnim", "Wait", "PlayVfx", "PlaySfx", "SetAnimation", "PlayAnimation", "Preview",
                "ShowCardSelection", "Flash", "Shake", "PlayOnCreature", "PlayOnCreatureCenter",
                "UpdateDisplay", "InvokeDisplayAmountChanged", "StartPulsing", "StopPulsing", "PlaySpineAnimation"}


def is_node_name(v):
    return re.match(r"^N[A-Z][a-z]", v) is not None


class Ctx:
    def __init__(self, cls_members, base_members, cur_method=None):
        self.cls_members = cls_members
        self.base_members = base_members
        self.cur_method = cur_method
        self.scopes = [set()]
        self.pre = []
        self.tmp_n = 0
        self.out_params = []
        self.dropped_locals = set()
        self.pending_out = []

    def push(self):
        self.scopes.append(set())

    def pop(self):
        self.scopes.pop()

    def declare(self, name):
        self.scopes[-1].add(name)

    def is_local(self, name):
        return any(name in s for s in self.scopes)

    def tmp(self, p="_t"):
        self.tmp_n += 1
        return f"{p}{self.tmp_n}"


def pyname(n):
    return n + "_" if n in PY_RESERVED else n


def _split_targs(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class Parser:
    def __init__(self, toks, ctx):
        self.t = toks
        self.i = 0
        self.ctx = ctx

    def peek(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def at(self, v, k=0):
        t = self.peek(k)
        return t.v == v and t.k in ("op", "id")

    def next(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def expect(self, v):
        t = self.next()
        if t.v != v:
            raise Unsupported(f"期望 {v} 得到 {t.v} @{self.i}")
        return t

    def accept(self, v):
        if self.at(v):
            self.i += 1
            return True
        return False

    # ---------------- 类型
    def try_type(self):
        s = self.i
        try:
            return self._type()
        except (Unsupported, IndexError):
            self.i = s
            return None

    def _type(self):
        t = self.peek()
        if t.k == "op" and t.v == "(":
            self.next()
            self._type()
            if self.peek().k == "id" and (self.at(",", 1) or self.at(")", 1)):
                self.next()
            while self.accept(","):
                self._type()
                if self.peek().k == "id" and (self.at(",", 1) or self.at(")", 1)):
                    self.next()
            self.expect(")")
            ty = "tuple"
        elif t.k == "id" and t.v not in ("new", "return", "await", "true", "false", "null", "this", "base", "typeof"):
            self.next()
            name = t.v
            if name == "global" and self.at("::"):
                self.next()
                name = self.next().v
            while self.at(".") and self.peek(1).k == "id":
                self.next()
                name += "." + self.next().v
            if self.at("<"):
                s = self.i
                self.next()
                args = []
                ok = True
                while True:
                    a = self.try_type()
                    if a is None:
                        ok = False
                        break
                    args.append(a)
                    if self.accept(","):
                        continue
                    if self.accept(">"):
                        break
                    ok = False
                    break
                if not ok:
                    self.i = s
                else:
                    name += "<" + ",".join(args) + ">"
            ty = name
        else:
            raise Unsupported("不是类型")
        while True:
            if self.at("?") and (self.at("[", 1) and (self.at("]", 2) or self.at(",", 2))):
                self.next()
            elif self.at("?") and not self._looks_ternary():
                self.next()
                if not ty.endswith("?"):
                    ty += "?"
            elif self.at("[") and self.at("]", 1):
                self.next(); self.next()
                ty += "[]"
            elif self.at("[") and self.at(",", 1):
                self.next()
                while self.accept(","):
                    pass
                self.expect("]")
                ty += "[,]"
            else:
                break
        return ty

    def _looks_ternary(self):
        n1, n2 = self.peek(1), self.peek(2)
        if n1.k == "id" and n2.v in ("=", ";", ",", ")", "in", "{", "=>", "(", "<"):
            return False
        if n1.v in (">", ",", ")", "["):
            return False
        return True

    def _type_ref(self, ty):
        base = re.sub(r"<.*>", "", ty).replace("[]", "").rstrip("?")
        base = base.split(".")[-1]
        if base in KEYWORDS_TYPES:
            return {"int": "int", "decimal": "float", "float": "float", "double": "float", "long": "int",
                    "bool": "bool", "string": "str", "object": "object"}.get(base, "object")
        return base

    # ---------------- 表达式
    BINP = {"??": 3, "||": 4, "&&": 5, "|": 6, "^": 7, "&": 8, "==": 9, "!=": 9, "<": 10, ">": 10, "<=": 10,
            ">=": 10, "is": 10, "as": 10, "<<": 11, "+": 12, "-": 12, "*": 13, "/": 13, "%": 13}
    ASSIGN = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "??=", "<<=", ">>="}

    def expr(self, minp=0):
        left = self.unary()
        while True:
            t = self.peek()
            v = t.v
            if t.k not in ("op", "id"):
                break
            if v in self.ASSIGN and t.k == "op" and minp <= 1:
                self.next()
                right = self.expr(1)
                raise _AssignSignal(left, v, right)
            if v == "?" and t.k == "op" and minp <= 2:
                self.next()
                a = self.expr(0)
                self.expect(":")
                b = self.expr(2)
                left = f"({a} if {left} else {b})"
                continue
            if v == ">" and self.at(">", 1) and minp <= 11:
                self.next(); self.next()
                r = self.expr(12)
                left = f"({left} >> {r})"
                continue
            p = self.BINP.get(v)
            if p is None or p < minp or (t.k == "id" and v not in ("is", "as")):
                break
            self.next()
            if v == "is":
                left = self._is(left)
                continue
            if v == "as":
                ty = self._type()
                left = f"_as({left}, {self._type_ref(ty)})"
                continue
            right = self.expr(p + 1)
            if v == "??":
                left = f"_nz({left}, lambda: {right})"
            elif v == "&&":
                left = f"({left} and {right})"
            elif v == "||":
                left = f"({left} or {right})"
            elif v == "/":
                left = f"_div({left}, {right})"
            elif v == "%":
                left = f"_mod({left}, {right})"
            elif v in ("==", "!=") and (right == "None" or left == "None"):
                o = left if right == "None" else right
                left = f"({o} is {'not ' if v == '!=' else ''}None)"
            elif v in ("==", "!="):
                left = f"({left} {v} {right})"
            elif (left.startswith("(None if (") or right.startswith("(None if (")) and v in ("+", "-", "*", "<", ">", "<=", ">="):
                left = f"_lop({v!r}, {left}, {right})"
            else:
                left = f"({left} {v} {right})"
        return left

    def _is(self, left):
        neg = False
        if self.accept("not"):
            neg = True
        if self.at("null"):
            self.next()
            return f"({left} is {'not ' if neg else ''}None)"
        if self.peek().k in ("num", "str") or self.at("true") or self.at("false"):
            lit = self.primary()
            return f"({left} {'!=' if neg else '=='} {lit})"
        if self.at("{"):
            self.expect("{"); self.expect("}")
            if self.peek().k == "id" and self.peek().v not in ("when", "or", "and", "select", "where", "orderby", "group", "into", "let", "join", "on", "equals", "by", "ascending", "descending"):
                nm = self.next().v
                self.ctx.declare(nm)
                return f"(({pyname(nm)} := {left}) is not None)"
            return f"({left} is not None)"
        ty = self._type()
        tr = self._type_ref(ty)
        res = f"_isinst({left}, {tr})"
        if self.peek().k == "id" and self.peek().v not in ("when", "or", "and", "select", "where", "orderby", "group", "into", "let", "join", "on", "equals", "by", "ascending", "descending"):
            nm = self.next().v
            self.ctx.declare(nm)
            res = f"_isinst(({pyname(nm)} := {left}), {tr})"
        if neg:
            res = f"(not {res})"
        return res

    def unary(self):
        t = self.peek()
        if t.k == "op":
            if t.v == "!":
                self.next()
                return f"(not {self.unary()})"
            if t.v == "-":
                self.next()
                return f"(-{self.unary()})"
            if t.v == "+":
                self.next()
                return self.unary()
            if t.v == "~":
                self.next()
                return f"(~{self.unary()})"
            if t.v == "^":
                self.next()
                return f"(-{self.unary()})"
            if t.v in ("++", "--"):
                self.next()
                target = self.unary()
                raise _AssignSignal(target, "+=" if t.v == "++" else "-=", "1")
            if t.v == "(":
                c = self._try_cast()
                if c is not None:
                    return c
        if t.k == "id" and t.v == "await":
            self.next()
            return self.unary()
        return self.postfix(self.primary())

    def _try_cast(self):
        s = self.i
        self.next()
        ty = self.try_type()
        if ty is None or not self.at(")"):
            self.i = s
            return None
        self.next()
        nt = self.peek()
        base = re.sub(r"<.*>", "", ty).rstrip("?")
        last = base.split(".")[-1]
        is_kw = base in KEYWORDS_TYPES
        ok = False
        if ty == "tuple" and nt.v == "(":
            ok = True
        elif is_kw and (nt.k in ("id", "num", "str", "istr") or nt.v in ("(", "-", "!")):
            ok = True
        elif nt.k in ("id", "num", "str", "istr") and nt.v not in ("is", "as", "and", "or", "switch", "when") \
                and re.match(r"^[A-Z]", last or "x") and not self.ctx.is_local(last):
            ok = True
        elif nt.v == "(" and re.match(r"^[A-Z][a-z]", last or "x") and not self.ctx.is_local(last) \
                and last not in self.ctx.cls_members:
            ok = True
        elif nt.v == "(" and (last in getattr(self.ctx, "mgparams", ()) or re.fullmatch(r"T([A-Z]\w*)?", last or "")) \
                and not self.ctx.is_local(last):
            ok = True   # 泛型参数强转 (T)(expr)
        if not ok:
            self.i = s
            return None
        inner = self.unary()
        if base in ("uint", "ulong", "int", "ushort", "short", "byte", "sbyte"):
            return f"_cast_{base}({inner})"
        if base == "long":
            return f"_int({inner})"
        if base in ("decimal", "float", "double"):
            return f"float({inner})"
        return inner

    def _lambda_ahead(self):
        t = self.peek()
        if t.k == "id" and self.at("=>", 1):
            return True
        if t.v == "(":
            depth = 0
            j = self.i
            while j < len(self.t):
                v = self.t[j].v
                if v == "(":
                    depth += 1
                elif v == ")":
                    depth -= 1
                    if depth == 0:
                        return self.t[j + 1].v == "=>"
                elif v in (";", "{", "}"):
                    return False
                j += 1
        return False

    def _lambda(self):
        params = []
        if self.peek().k == "id" and self.at("=>", 1):
            params.append(self.next().v)
        else:
            self.expect("(")
            while not self.at(")"):
                s = self.i
                self.try_type()
                if self.peek().k == "id" and (self.at(",", 1) or self.at(")", 1)):
                    params.append(self.next().v)
                else:
                    self.i = s
                    params.append(self.next().v)
                self.accept(",")
            self.expect(")")
        self.expect("=>")
        return self._lambda_body(params)

    def _lambda_body(self, params):
        self.ctx.push()
        for p in params:
            self.ctx.declare(p)
        ps = ", ".join(pyname(p) for p in params)
        if self.at("{"):
            name = self.ctx.tmp("_fn")
            saved = self.ctx.pre
            self.ctx.pre = []
            body = self.block_lines(indent=1)
            inner_pre = self.ctx.pre
            self.ctx.pre = saved
            self.ctx.pop()
            outer = set().union(*self.ctx.scopes) - set(params)
            assigned = set()
            for l in body:
                m = re.match(r"^\s{4}(\w+) (?:[-+*/|&]?=) ", l)
                if m and m.group(1) in {pyname(o) for o in outer}:
                    assigned.add(m.group(1))
            if assigned:
                body = ["    nonlocal " + ", ".join(sorted(assigned))] + body
            pre_l = []
            for p in inner_pre:
                pre_l += ["    " + l for l in p]
            self.ctx.pre.append([f"def {name}({ps}):"] + pre_l + (body or ["    pass"]))
            return name
        saved = self.ctx.pre
        self.ctx.pre = []
        try:
            e = self.expr_or_assign(0)
        finally:
            inner_pre = self.ctx.pre
            self.ctx.pre = saved
        self.ctx.pop()
        if inner_pre:
            # 表达式 lambda 体里有被提升的语句 lambda：外层也提升为 def，内层 def 才能看到外层参数
            name = self.ctx.tmp("_fn")
            pre_l = []
            for p in inner_pre:
                pre_l += ["    " + l for l in p]
            self.ctx.pre.append([f"def {name}({ps}):"] + pre_l + [f"    return {e}"])
            return name
        return f"(lambda {ps}: {e})"

    def _interp(self, raw):
        import copy as _copy
        out = []
        for is_expr, text, fmt in _split_interp(raw):
            if not is_expr:
                out.append(repr(text.replace('\\"', '"')))
                continue
            sub = _copy.copy(self)
            sub.t = lex(text)
            sub.i = 0
            try:
                e = sub.expr(0)
            except Unsupported:
                e = repr("{" + text + "}")   # 无法解析的内插（仅见于日志文本）
            if fmt:
                out.append(f"_str({e}, {fmt!r})")
            else:
                out.append(f"_str({e})")
        if not out:
            return "''"
        return "(" + " + ".join(out) + ")"

    def primary(self):
        t = self.next()
        if t.k == "num":
            v = t.v
            low = v.lower()
            if low.startswith("0x"):
                return str(int(low, 16))
            suf = re.sub(r"^[0-9.eE+-]+", "", v)
            num = v[:len(v) - len(suf)] if suf else v
            if any(ch in suf.lower() for ch in "mfd") or "." in num:
                return repr(float(num))
            return num
        if t.k == "str":
            return repr(t.v.replace('\\"', '"'))
        if t.k == "istr":
            return self._interp(t.v)
        if t.k == "eof":
            raise Unsupported("意外结尾")
        v = t.v
        if t.k == "op":
            if v == "(":
                self.i -= 1
                if self._lambda_ahead():
                    return self._lambda()
                self.next()
                names = []
                if self.peek().k == "id" and self.at(":", 1):
                    names.append(self.next().v); self.next()
                e = self.expr_or_assign(0)
                if self.at(","):
                    items = [e]
                    while self.accept(","):
                        if self.peek().k == "id" and self.at(":", 1):
                            names.append(self.next().v); self.next()
                        items.append(self.expr(0))
                    self.expect(")")
                    if names:
                        return f"CsTuple(({', '.join(items)},), {tuple(names)!r})"
                    return "CsTuple((" + ", ".join(items) + ",))"
                self.expect(")")
                return f"({e})"
            if v == "[":
                items = []
                while not self.at("]"):
                    items.append(self.expr(0))
                    self.accept(",")
                self.expect("]")
                return "Seq([" + ", ".join(items) + "])"
            raise Unsupported(f"表达式里意外的 {v}")
        if v == "async" and (self._lambda_ahead() or self.at("delegate")):
            return self.primary()
        if self.at("=>"):
            self.i -= 1
            return self._lambda()
        if v == "true":
            return "True"
        if v == "false":
            return "False"
        if v == "null":
            return "None"
        if v in ("this", "base"):
            if v == "base" and self.at(".") and self.peek(1).k == "id":
                nm = self.peek(1).v
                if nm == self.ctx.cur_method or (nm in self.ctx.cls_members and self.at("(", 2)):
                    self.next(); self.next()
                    return f"super().{pyname(nm)}"
            return "self"
        if v == "from" and self.peek().k == "id" and self.at("in", 1):
            return self._query()
        if v == "delegate":
            params = []
            if self.at("("):
                self.next()
                while not self.at(")"):
                    s = self.i
                    self.try_type()
                    if self.peek().k == "id":
                        params.append(self.next().v)
                    else:
                        self.i = s
                        params.append(self.next().v)
                    self.accept(",")
                self.expect(")")
            return self._lambda_body(params)
        if v == "new":
            return self._new()
        if v == "typeof":
            self.expect("(")
            ty = self._type()
            self.expect(")")
            return self._type_ref(ty)
        if v == "nameof":
            self.expect("(")
            e = []
            depth = 1
            while depth:
                tt = self.next()
                if tt.v == "(":
                    depth += 1
                elif tt.v == ")":
                    depth -= 1
                    if not depth:
                        break
                e.append(tt.v)
            return repr(e[-1] if e else "")
        if v == "default":
            if self.at("("):
                self.next()
                ty = self._type()
                self.expect(")")
                return _default_for(ty)
            return "None"
        if v in ("checked", "unchecked"):
            self.expect("(")
            e = self.expr(0)
            self.expect(")")
            return e
        if v in KEYWORDS_TYPES and self.at(".") and not self.ctx.is_local(v):
            self.next()
            m = self.next().v
            return {"MaxValue": "999999999", "MinValue": "-999999999"}.get(m, f"_kw_{v}.{m}")
        if v == "global" and self.at("::"):
            self.next()
            v = self.next().v
        if v == "throw":
            self.expr(0)
            return "_throw()"
        targs = self._try_generic_args()
        name = self._resolve(v)
        if targs is not None:
            return (name, targs)
        return name

    def _query(self):
        var = self.next().v
        self.expect("in")
        src = self.expr(0)
        self.ctx.push()
        self.ctx.declare(var)
        v = pyname(var)
        cur = f"Seq({src})"
        while True:
            if self.at("where"):
                self.next()
                c = self.expr(0)
                cur = f"{cur}.Where(lambda {v}: {c})"
            elif self.at("orderby"):
                self.next()
                keys = [self.expr(0)]
                desc = self.accept("descending")
                self.accept("ascending")
                while self.accept(","):
                    keys.append(self.expr(0))
                    self.accept("descending")
                    self.accept("ascending")
                k = keys[0] if len(keys) == 1 else "(" + ", ".join(keys) + ",)"
                cur = f"{cur}.{'OrderByDescending' if desc else 'OrderBy'}(lambda {v}: {k})"
            elif self.at("let"):
                raise Unsupported("let 查询")
            elif self.at("select"):
                self.next()
                e = self.expr(0)
                cur = cur if e == v else f"{cur}.Select(lambda {v}: {e})"
                break
            elif self.at("group"):
                self.next()
                e = self.expr(0)
                self.expect("by")
                k = self.expr(0)
                cur = f"{cur}.GroupBy(lambda {v}: {k}, lambda {v}: {e})"
                break
            else:
                raise Unsupported("查询语法")
        self.ctx.pop()
        return f"({cur})"

    def _try_generic_args(self):
        if not self.at("<"):
            return None
        s = self.i
        self.next()
        args = []
        while True:
            a = self.try_type()
            if a is None:
                self.i = s
                return None
            args.append(a)
            if self.accept(","):
                continue
            if self.accept(">"):
                break
            self.i = s
            return None
        if self.at("(") or self.at(".") or self.at(")") or self.at(";") or self.at(","):
            return [self._type_ref(a) for a in args]
        self.i = s
        return None

    def _resolve(self, v):
        c = self.ctx
        if c.is_local(v):
            return pyname(v)
        if v in DROP_IDS or (is_node_name(v) and v not in KNOWN_MODELS):
            raise _DropSignal()
        if v in GLOBAL_TYPES and self.at(".") and v not in c.cls_members:
            return v
        if v in c.dropped_locals:
            raise _DropSignal()
        if v in c.cls_members or v in c.base_members:
            return "self." + pyname(v)
        if v in DROP_IDS or (is_node_name(v) and v not in KNOWN_MODELS):
            raise _DropSignal()
        return pyname(v)

    # ---------------- new / 调用 / 后缀
    def _new(self):
        if self.at("{"):
            self.next()
            kv = []
            while not self.at("}"):
                if self.peek().k == "id" and self.at("=", 1):
                    nm = self.next().v; self.next()
                    kv.append(f"{pyname(nm)}={self.expr(0)}")
                else:
                    e = self.expr(0)
                    kv.append(f"{re.split(r'[.]', e)[-1]}={e}")
                self.accept(",")
            self.expect("}")
            return f"_Anon({', '.join(kv)})"
        if self.at("("):
            j, depth = self.i, 0
            while j < len(self.t):
                if self.t[j].v == "(":
                    depth += 1
                elif self.t[j].v == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j + 1 < len(self.t) and self.t[j + 1].v == "[":
                self.i = j + 1
                self.next()
                size = None if self.at("]") else self.expr(0)
                self.expect("]")
                if self.at("{"):
                    return "Seq(" + self._coll_init() + ")"
                return f"Seq([None] * _int({size}))"
        if self.at("("):
            args = self.call_args()
            init = self._obj_init() if self.at("{") else ""
            return f"_new_target({args}{init})"
        if self.at("["):
            self.next(); self.expect("]")
            return "Seq(" + self._coll_init() + ")"
        ty = self._type_noarray()
        if self.at("["):
            self.next()
            size = None if self.at("]") else self.expr(0)
            if self.at("]") and self.at("[", 1) and self.at("]", 2):
                self.next(); self.next(); self.next()
                if self.at("{"):
                    return "Seq(" + self._coll_init() + ")"
                return f"Seq([None] * _int({size}))"
            if self.at(","):
                dims = [size]
                while self.accept(","):
                    dims.append(self.expr(0))
                self.expect("]")
                return f"Array2D({', '.join(dims)})"
            self.expect("]")
            if self.at("{"):
                return "Seq(" + self._coll_init() + ")"
            return f"Seq([None] * _int({size}))"
        base = re.sub(r"<.*>", "", ty).split(".")[-1]
        gm = re.match(r"[\w.]+<(.+)>$", ty)
        targs = [self._type_ref(a) for a in _split_targs(gm.group(1))] if gm else []
        args = self.call_args() if self.at("(") else ""
        if "ReadOnlySingleElementList" in base:
            return f"Seq([{args}])"
        if "ReadOnlyArray" in base or "ReadOnlyList" in base:
            return f"Seq({args})"
        if base in ("List", "HashSet", "Queue", "Stack", "Collection", "LinkedList", "SortedSet"):
            kind = "HashSet" if base in ("HashSet", "SortedSet") else ("Cs" + base if base in ("Queue", "Stack") else "Seq")
            res = f"{kind}({args})" if args and not re.fullmatch(r"\d+", args) else f"{kind}()"
            if self.at("{"):
                res = f"{kind}({self._coll_init()})"
            return res
        if base in ("Dictionary", "SortedDictionary"):
            if self.at("{"):
                items = self._coll_init()
                return f"{base}({items})"
            return f"{base}()"
        allargs = ", ".join(x for x in (args, (f"_g=({', '.join(targs)},)" if targs else "")) if x)
        res = f"{pyname(base)}({allargs})"
        if self.at("{"):
            res = f"_init_obj({res}{self._obj_init()})"
        return res

    def _type_noarray(self):
        name = self.next().v
        if name == "global" and self.at("::"):
            self.next()
            name = self.next().v
        while self.at(".") and self.peek(1).k == "id":
            self.next()
            name += "." + self.next().v
        if self.at("<"):
            depth = 0
            parts = []
            while True:
                tt = self.next()
                parts.append(tt.v)
                if tt.v == "<":
                    depth += 1
                elif tt.v == ">":
                    depth -= 1
                    if depth == 0:
                        break
            name += "".join(parts)
        if self.at("?"):
            self.next()
        return name

    def _coll_init(self):
        self.expect("{")
        items = []
        while not self.at("}"):
            if self.at("{"):
                self.next()
                k = self.expr(0)
                self.expect(",")
                val = self.expr(0)
                self.expect("}")
                items.append(f"({k}, {val})")
            elif self.at("[") :
                self.next()
                k = self.expr(0)
                self.expect("]")
                self.expect("=")
                items.append(f"({k}, {self.expr(0)})")
            else:
                items.append(self.expr(0))
            self.accept(",")
        self.expect("}")
        return "[" + ", ".join(items) + "]"

    def _obj_init(self):
        self.expect("{")
        kv = []
        while not self.at("}"):
            if self.peek().k == "id" and self.at("=", 1):
                k = self.next().v
                self.next()
                kv.append(f"{pyname(k)}={self.expr(0)}")
            else:
                kv.append(f"_item={self.expr(0)}")
            self.accept(",")
        self.expect("}")
        return (", " + ", ".join(kv)) if kv else ""

    def _skip_braces(self):
        depth = 0
        while True:
            t = self.next()
            if t.k == "eof":
                return
            if t.v == "{":
                depth += 1
            elif t.v == "}":
                depth -= 1
                if depth == 0:
                    return

    def call_args(self):
        self.expect("(")
        args = []
        while not self.at(")"):
            if self.peek().k == "id" and self.at(":", 1):
                nm = self.next().v
                self.next()
                args.append(f"{pyname(nm)}={self._arg()}")
            else:
                args.append(self._arg())
            if not self.accept(","):
                break
        self.expect(")")
        # C# 里非末尾的命名参数一定在自己的位置上：后面还有位置参数时去掉名字
        last_pos = max((i for i, a in enumerate(args) if not re.match(r"^\w+=(?!=)", a)), default=-1)
        args = [re.sub(r"^\w+=(?!=)", "", a) if i < last_pos else a for i, a in enumerate(args)]
        return ", ".join(args)

    def _arg(self):
        if self.at("out"):
            self.next()
            s = self.i
            ty = self.try_type()
            if not (self.peek().k == "id" and (self.at(",", 1) or self.at(")", 1))):
                self.i = s
            if self.at("_"):
                self.next()
                self.ctx.pending_out.append(None)   # 弃元：占位以保持 out 序号
                return "OUT"
            nm = self.next().v
            self.ctx.declare(nm)
            self.ctx.pending_out.append(pyname(nm))
            return "OUT"
        if self.at("ref") or (self.at("in") and self.peek(1).k == "id"):
            self.next()
        s = self.i
        pre_n = len(self.ctx.pre)
        po = list(self.ctx.pending_out)
        try:
            return self.expr_or_assign(0)
        except _DropSignal:
            # 视觉参数（HoverTip 等）：只替换这个参数，调用本身保留
            del self.ctx.pre[pre_n:]
            self.ctx.pending_out = po
            self.i = s
            depth = 0
            while True:
                t = self.peek()
                if t.k == "eof":
                    break
                if depth == 0 and t.v in (",", ")"):
                    break
                if t.v in ("(", "[", "{"):
                    depth += 1
                elif t.v in (")", "]", "}"):
                    depth -= 1
                self.next()
            return "Dummy('vis')"

    def postfix(self, left):
        guards = []
        res = self._postfix_inner(left, guards)
        if guards and isinstance(res, str):
            for (tmp, lhs) in reversed(guards):
                res = f"(None if ({tmp} := {lhs}) is None else {res})"
        return res

    def _postfix_inner(self, left, guards):
        while True:
            if isinstance(left, tuple):
                name, targs = left
                if self.at("("):
                    po_before = list(self.ctx.pending_out)
                    self.ctx.pending_out = []
                    args = self.call_args()
                    allargs = ", ".join(([args] if args else []) + ([f"_g=({', '.join(targs)},)"] if targs else []))
                    left = self._wrap_out(f"{name}({allargs})")
                    self.ctx.pending_out = po_before + self.ctx.pending_out
                    continue
                left = f"_generic({name}, {', '.join(targs)})"
                continue
            t = self.peek()
            if t.v == "." and self.peek(1).k == "id":
                self.next()
                nm = self.next().v
                if nm in DROP_METHODS and self.at("("):
                    raise _DropSignal()
                if nm == "ToString" and self.at("("):
                    self.call_args()
                    left = f"_str({left})"
                    continue
                if nm == "GetType" and self.at("("):
                    self.call_args()
                    left = f"type({left})"
                    continue
                if nm == "Invoke" and isinstance(left, str):
                    left = f"_inv({left})"
                    continue
                targs = self._try_generic_args()
                acc = self._acc(left, nm) if targs is None else f"{left}.{pyname(nm)}"
                left = (acc, targs) if targs is not None else acc
                continue
            if t.v == "?." and self.peek(1).k == "id":
                self.next()
                nm = self.next().v
                if nm in DROP_METHODS and self.at("("):
                    raise _DropSignal()
                targs = self._try_generic_args()
                tmp = self.ctx.tmp("_s")
                guards.append((tmp, left if isinstance(left, str) else f"_generic({left[0]}, {', '.join(left[1])})"))
                if nm == "Invoke" and targs is None:
                    left = f"_inv({tmp})"
                    continue
                acc = self._acc(tmp, nm) if targs is None else f"{tmp}.{pyname(nm)}"
                left = (acc, targs) if targs is not None else acc
                continue
            if t.v == "?." and self.peek(1).v == "[":
                self.next(); self.next()
                idx = self.expr(0)
                self.expect("]")
                tmp = self.ctx.tmp("_s")
                guards.append((tmp, left))
                left = f"{tmp}[{idx}]"
                continue
            if t.v == "(":
                po_before = list(self.ctx.pending_out)
                self.ctx.pending_out = []
                args = self.call_args()
                left = self._wrap_out(f"{left}({args})")
                self.ctx.pending_out = po_before
                continue
            if t.v == "[":
                self.next()
                idx = self.expr(0)
                while self.accept(","):
                    idx += ", " + self.expr(0)
                self.expect("]")
                left = f"{left}[{idx}]"
                continue
            if t.v in ("++", "--"):
                self.next()
                raise _AssignSignal(left, "+=" if t.v == "++" else "-=", "1", post=True)
            if t.v == "!" and self.peek(1).v in (".", ")", ";", ",", "?.", "[", "]"):
                self.next()
                continue
            if t.k == "id" and t.v == "switch":
                self.next()
                left = self._switch_expr(left)
                continue
            break
        return left

    STR_METHODS = {"StartsWith", "EndsWith", "ToLowerInvariant", "ToUpperInvariant", "ToLower", "ToUpper", "Trim",
                   "TrimStart", "TrimEnd", "Split", "Substring", "Replace", "PadLeft", "PadRight", "Contains",
                   "IndexOf", "LastIndexOf", "CompareTo", "Equals", "GetHashCode"}

    def _acc(self, obj, nm):
        if not isinstance(obj, str) or obj == "self":
            return f"{obj}.{pyname(nm)}"
        if nm == "Length":
            return f"_len({obj})"
        if nm == "HasValue":
            return f"({obj} is not None)"
        if nm == "Value":
            return f"_val({obj})"
        if nm == "GetValueOrDefault" and self.at("("):
            return f"_sm({obj}, 'GetValueOrDefault')"
        if nm in self.STR_METHODS and self.at("("):
            return f"_sm({obj}, {nm!r})"
        return f"{obj}.{pyname(nm)}"

    def _wrap_out(self, call):
        po = self.ctx.pending_out
        if po:
            self.ctx.pending_out = []
            if all(n is None for n in po):
                return f"_outcall({call})[0]"
            tmp = self.ctx.tmp("_o")
            assigns = ", ".join(f"({n} := {tmp}[{i + 1}])" for i, n in enumerate(po) if n is not None)
            return f"(({tmp} := _outcall({call})), {assigns}, {tmp}[0])[-1]"
        return call

    def _switch_expr(self, subj):
        self.expect("{")
        arms = []
        default = "None"
        tmp = self.ctx.tmp("_sw")
        self.ctx.push()
        self.ctx.declare(tmp)
        while not self.at("}"):
            if self.at("_") and self.at("=>", 1):
                self.next(); self.next()
                default = self.expr(0)
            else:
                pat = self._pattern(tmp)
                if self.at("when"):
                    self.next()
                    pat = f"({pat} and {self.expr(0)})"
                self.expect("=>")
                arms.append((pat, self.expr(0)))
            self.accept(",")
        self.expect("}")
        self.ctx.pop()
        res = default
        for pat, val in reversed(arms):
            res = f"({val} if {pat} else {res})"
        return f"(lambda {tmp}: {res})({subj})"

    def _pattern(self, subj):
        if self.peek().v in ("<", ">", "<=", ">="):
            op = self.next().v
            return f"({subj} {op} {self.unary()})"
        if self.at("not"):
            self.next()
            return f"(not {self._pattern(subj)})"
        if self.at("("):
            self.next()
            r = self._pattern(subj)
            self.expect(")")
            res = r
        else:
            t = self.peek()
            if t.k in ("num", "str") or self.at("true") or self.at("false") or self.at("null") or self.at("-"):
                lit = self.unary()
                res = f"({subj} is None)" if lit == "None" else f"_eq({subj}, {lit})"
            else:
                e = self.postfix(self.primary())
                if self.peek().k == "id" and self.peek().v not in ("when", "or", "and", "select", "where", "orderby", "group", "into", "let", "join", "on", "equals", "by", "ascending", "descending"):
                    nm = self.next().v
                    self.ctx.declare(nm)
                    res = f"_isinst(({pyname(nm)} := {subj}), {e})"
                elif self.at("{"):
                    self._skip_braces()
                    res = f"_isinst({subj}, {e})"
                else:
                    res = f"_is_type_or_eq({subj}, {e})"
        if self.at("or"):
            self.next()
            res = f"({res} or {self._pattern(subj)})"
        elif self.at("and"):
            self.next()
            res = f"({res} and {self._pattern(subj)})"
        return res

    # ---------------- 语句
    def block_lines(self, indent=0):
        self.expect("{")
        self.ctx.push()
        lines, hoisted = [], []
        while not self.at("}"):
            if self.peek().k == "eof":
                raise Unsupported("块没有结束")
            st = self.statement()
            # C# 局部函数可在声明前调用：整块 def 提升到块首
            if st and st[0].startswith("def ") and all(l.startswith("    ") for l in st[1:]):
                hoisted += st
            else:
                lines += st
        lines = hoisted + lines
        self.expect("}")
        self.ctx.pop()
        pad = "    " * indent
        return [pad + l for l in lines]

    def body_or_stmt(self):
        if self.at("{"):
            ls = self.block_lines(1)
        else:
            self.ctx.push()
            ls = ["    " + l for l in self.statement()]
            self.ctx.pop()
        return ls or ["    pass"]

    def statement(self):
        s = self.i
        pre_n = len(self.ctx.pre)
        po = list(self.ctx.pending_out)
        try:
            lines = self._statement()
        except _DropSignal:
            del self.ctx.pre[pre_n:]
            self.ctx.pending_out = po
            self.i = s
            self._skip_statement()
            return ["pass  # 视觉"]
        pre = self.ctx.pre[pre_n:]
        del self.ctx.pre[pre_n:]
        out = []
        for p in pre:
            out += p
        return out + lines

    def _skip_statement(self):
        t = self.peek()
        decl = None
        s = self.i
        ty = self.try_type()
        if ty and self.peek().k == "id" and self.at("=", 1):
            decl = self.peek().v
        self.i = s
        if t.v in ("if", "for", "foreach", "while", "using", "lock"):
            self.next()
            self._skip_parens()
            self._skip_stmt_or_block()
            while t.v == "if" and self.at("else"):
                self.next()
                if self.at("if"):
                    self.next()
                    self._skip_parens()
                self._skip_stmt_or_block()
            return
        depth = 0
        while True:
            tt = self.next()
            if tt.k == "eof":
                return
            if tt.v in ("(", "{", "["):
                depth += 1
            elif tt.v in (")", "}", "]"):
                depth -= 1
            elif tt.v == ";" and depth == 0:
                break
        if decl:
            self.ctx.dropped_locals.add(decl)

    def _skip_parens(self):
        self.expect("(")
        depth = 1
        while depth:
            t = self.next()
            if t.v == "(":
                depth += 1
            elif t.v == ")":
                depth -= 1

    def _skip_stmt_or_block(self):
        if self.at("{"):
            self._skip_braces()
        else:
            self._skip_statement()

    def _statement(self):
        t = self.peek()
        v = t.v
        if t.k == "op" and v == "{":
            return self.block_lines(0) or ["pass"]
        if t.k == "op" and v == ";":
            self.next()
            return []
        if t.k == "id" and v == "await" and self.at("using", 1):
            self.next()
            t = self.peek()
            v = t.v
        if t.k == "id":
            if v == "if":
                return self._if()
            if v == "return":
                self.next()
                if self.accept(";"):
                    return [self._ret("None")]
                try:
                    e = self.expr(0)
                except _AssignSignal:
                    raise Unsupported("return 里赋值")
                self.expect(";")
                return [self._ret(e)]
            if v == "foreach":
                self.next()
                self.expect("(")
                self.ctx.push()
                if self.at("var") and self.at("(", 1):
                    self.next(); self.next()
                    names = []
                    while not self.at(")"):
                        names.append(self.next().v)
                        self.accept(",")
                    self.expect(")")
                    for n in names:
                        self.ctx.declare(n)
                    var = "(" + ", ".join(pyname(n) for n in names) + ")"
                else:
                    s = self.i
                    self.try_type()
                    if not (self.peek().k == "id" and self.at("in", 1)):
                        self.i = s
                    nm = self.next().v
                    self.ctx.declare(nm)
                    var = pyname(nm)
                self.expect("in")
                coll = self.expr(0)
                self.expect(")")
                body = self.body_or_stmt()
                self.ctx.pop()
                return [f"for {var} in _iter({coll}):"] + body
            if v == "for":
                return self._for()
            if v == "while":
                self.next()
                self.expect("(")
                c = self.expr(0)
                self.expect(")")
                return [f"while {c}:"] + self.body_or_stmt()
            if v == "do":
                self.next()
                body = self.body_or_stmt()
                self.expect("while")
                self.expect("(")
                c = self.expr(0)
                self.expect(")")
                self.expect(";")
                if any(l.strip() == "continue" for l in body):
                    raise Unsupported("do-while continue")
                return ["while True:"] + body + [f"    if not ({c}):", "        break"]
            if v == "break":
                self.next(); self.expect(";")
                return ["break"]
            if v == "continue":
                self.next(); self.expect(";")
                return ["continue"]
            if v == "throw":
                self.next()
                if self.accept(";"):
                    return ["raise"]
                while not self.at(";"):
                    self.next()
                self.expect(";")
                return ["raise CsException()"]
            if v == "yield":
                self.next()
                if self.accept("break"):
                    self.expect(";")
                    return ["return"]
                self.expect("return")
                e = self.expr(0)
                self.expect(";")
                return [f"yield {e}"]
            if v == "goto":
                raise Unsupported("goto")
            if v in ("using", "lock", "fixed") and self.at("(", 1):
                self.next()
                self.expect("(")
                s = self.i
                ty = self.try_type()
                lines = []
                if ty and self.peek().k == "id" and self.at("=", 1):
                    nm = self.next().v
                    self.next()
                    e = self.expr(0)
                    self.ctx.declare(nm)
                    lines.append(f"{pyname(nm)} = {e}")
                else:
                    self.i = s
                    e = self.expr(0)
                    lines.append(f"_ = {e}")
                self.expect(")")
                return lines + [l[4:] for l in self.body_or_stmt()]
            if v == "using":
                self.next()
            if v == "try":
                self.next()
                body = self.body_or_stmt()
                lines = ["try:"] + body
                n0 = len(lines)
                while self.at("catch"):
                    self.next()
                    if self.at("("):
                        self._skip_parens()
                    if self.at("when"):
                        self.next()
                        self._skip_parens()
                    lines += ["except Exception:"] + self.body_or_stmt()
                if self.at("finally"):
                    self.next()
                    lines += ["finally:"] + self.body_or_stmt()
                if len(lines) == n0:
                    lines += ["finally:", "    pass"]
                return lines
            if v == "switch":
                return self._switch_stmt()
            if v == "const":
                self.next()
        # 局部函数
        s = self.i
        while self.peek().v in ("async", "static", "unsafe"):
            self.next()
        ty = self.try_type()
        if ty is not None and self.peek().k == "id" and self.at("(", 1):
            j = self.i + 1
            depth = 0
            while True:
                tv = self.t[j].v
                if tv == "(":
                    depth += 1
                elif tv == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if self.t[j + 1].v in ("{", "=>"):
                nm = self.next().v
                params, outs, defaults = self._params()
                self.ctx.declare(nm)
                self.ctx.push()
                for p in params:
                    self.ctx.declare(p)
                if self.at("=>"):
                    self.next()
                    e = self.expr(0)
                    self.expect(";")
                    body = ["    return " + e]
                else:
                    body = self.block_lines(1)
                self.ctx.pop()
                return [f"def {pyname(nm)}({', '.join(defaults)}):"] + (body or ["    pass"])
        self.i = s
        # 局部变量
        if self.at("var") and self.at("(", 1):
            self.next(); self.next()
            names = []
            while not self.at(")"):
                names.append(self.next().v)
                self.accept(",")
            self.expect(")")
            self.expect("=")
            e = self.expr(0)
            self.expect(";")
            for n in names:
                self.ctx.declare(n)
            return ["(" + ", ".join(pyname(n) for n in names) + f",) = {e}"]
        ty = self.try_type()
        if ty is not None and self.peek().k == "id" and self.peek(1).v in ("=", ";", ","):
            lines = []
            while True:
                nm = self.next().v
                if self.accept("="):
                    try:
                        e = self.expr(0)
                    except _AssignSignal as a:
                        lines.append(self._assign_line(a))
                        e = a.left
                    if e == "None" and self.t[self.i - 1].v == "default":
                        e = _default_for(ty)
                else:
                    e = _default_for(ty)
                self.ctx.declare(nm)
                lines.append(f"{pyname(nm)} = {e}")
                if not self.accept(","):
                    break
            self.expect(";")
            return lines
        self.i = s
        try:
            e = self.expr(0)
            self.expect(";")
            return [e]
        except _AssignSignal as a:
            if self.at(";"):
                self.next()
            else:
                raise Unsupported("赋值后面不是分号")
            return [self._assign_line(a)]

    def _assign_expr(self, a):
        left, op, right = a.left, a.op, a.right
        m = re.fullmatch(r"_(val|len)\((.+)\)", left)
        if m:
            left = m.group(2) + (".Value" if m.group(1) == "val" else ".Length")
        if op != "=":
            bop = op[:-1]
            if bop == "??":
                right = f"_nz({left}, lambda: {right})"
            elif bop == "/":
                right = f"_div({left}, {right})"
            elif bop == "%":
                right = f"_mod({left}, {right})"
            else:
                right = f"({left} {bop} {right})"
        if re.fullmatch(r"[A-Za-z_]\w*", left):
            return f"({left} := {right})"
        m = re.fullmatch(r"(.+)\.([A-Za-z_]\w*)", left)
        if m and not left.startswith("_safe("):
            return f"_setattr_ret({m.group(1)}, {m.group(2)!r}, {right})"
        m = re.fullmatch(r"(.+)\[(.+)\]", left)
        if m:
            return f"_setitem_ret({m.group(1)}, {m.group(2)}, {right})"
        raise Unsupported("表达式内赋值")

    def expr_or_assign(self, minp=0):
        try:
            return self.expr(minp)
        except _AssignSignal as a:
            if getattr(a, "post", False):
                raise
            return self._assign_expr(a)

    def _assign_line(self, a):
        left, op, right = a.left, a.op, a.right
        mt = re.fullmatch(r"CsTuple\(\((.*)\)\)", left)
        if mt:
            left = "(" + mt.group(1) + ")"
        m = re.fullmatch(r"_(val|len)\((.+)\)", left)
        if m:
            left = m.group(2) + (".Value" if m.group(1) == "val" else ".Length")
        if left.startswith("_safe("):
            raise Unsupported("?. 赋值")
        if op == "??=":
            return f"if {left} is None: {left} = {right}"
        if op == "/=":
            return f"{left} = _div({left}, {right})"
        if op == "%=":
            return f"{left} = _mod({left}, {right})"
        return f"{left} {op} {right}"

    def _ret(self, e):
        if self.ctx.out_params:
            return f"return ({e}, {', '.join(self.ctx.out_params)})"
        return f"return {e}"

    def _if(self):
        self.expect("if")
        self.expect("(")
        c = self.expr(0)
        self.expect(")")
        lines = [f"if {c}:"] + self.body_or_stmt()
        while self.at("else"):
            self.next()
            if self.at("if"):
                self.next()
                self.expect("(")
                pn = len(self.ctx.pre)
                c2 = self.expr(0)
                self.expect(")")
                if len(self.ctx.pre) > pn:
                    pre = self.ctx.pre[pn:]
                    del self.ctx.pre[pn:]
                    inner = []
                    for p in pre:
                        inner += ["    " + l for l in p]
                    body = self.body_or_stmt()
                    rest = []
                    if self.at("else"):
                        # 把剩下的 else 链作为嵌套
                        self.i -= 0
                    lines += ["else:"] + inner + [f"    if {c2}:"] + ["    " + l for l in body]
                    if self.at("else"):
                        self.next()
                        if self.at("if"):
                            sub = self._if()
                        else:
                            sub = ["if True:"] + self.body_or_stmt()
                        lines += ["    else:"] + ["        " + l for l in sub]
                    break
                lines += [f"elif {c2}:"] + self.body_or_stmt()
            else:
                lines += ["else:"] + self.body_or_stmt()
                break
        return lines

    def _for(self):
        self.expect("for")
        self.expect("(")
        self.ctx.push()
        init = []
        var = None
        if not self.at(";"):
            s = self.i
            ty = self.try_type()
            if ty is not None and self.peek().k == "id" and self.at("=", 1):
                var = self.next().v
                self.next()
                start = self.expr(0)
                self.ctx.declare(var)
                init.append(f"{pyname(var)} = {start}")
                while self.accept(","):
                    nm = self.next().v
                    self.expect("=")
                    self.ctx.declare(nm)
                    init.append(f"{pyname(nm)} = {self.expr(0)}")
            else:
                self.i = s
                try:
                    init.append(self.expr(0))
                except _AssignSignal as a:
                    init.append(self._assign_line(a))
        self.expect(";")
        cond = "True" if self.at(";") else self.expr(0)
        self.expect(";")
        steps = []
        while not self.at(")"):
            try:
                steps.append(self.expr(0))
            except _AssignSignal as a:
                steps.append(self._assign_line(a))
            self.accept(",")
        self.expect(")")
        body = self.body_or_stmt()
        self.ctx.pop()
        if var and len(init) == 1 and len(steps) == 1 and steps[0] == f"{pyname(var)} += 1":
            m = re.fullmatch(r"\(" + re.escape(pyname(var)) + r" < (.+)\)", cond)
            body_txt = "\n".join(body)
            if m and not re.search(r"\b" + re.escape(pyname(var)) + r" [-+*/]?= ", body_txt):
                start = init[0].split(" = ", 1)[1]
                return [f"for {pyname(var)} in range(_int({start}), _int({m.group(1)})):"] + body
        if any(l.strip() == "continue" for l in body):
            fl = self.ctx.tmp("_first")
            return init + [f"{fl} = True", "while True:", f"    if not {fl}:"] + ["        " + s for s in steps] + \
                [f"    {fl} = False", f"    if not ({cond}):", "        break"] + body
        return init + [f"while {cond}:"] + body + ["    " + s for s in steps]

    def _switch_stmt(self):
        self.expect("switch")
        self.expect("(")
        subj = self.expr(0)
        self.expect(")")
        self.expect("{")
        tmp = self.ctx.tmp("_sw")
        self.ctx.declare(tmp)
        lines = [f"{tmp} = {subj}"]
        first = True
        sections = []
        while not self.at("}"):
            conds = []
            is_default = False
            while self.at("case") or self.at("default"):
                if self.at("default"):
                    self.next(); self.expect(":")
                    is_default = True
                    continue
                self.next()
                pat = self._pattern(tmp)
                if self.at("when"):
                    self.next()
                    pat = f"({pat} and {self.expr(0)})"
                self.expect(":")
                conds.append(pat)
            body = []
            self.ctx.push()
            while not (self.at("case") or self.at("default") or self.at("}")):
                body += self.statement()
            self.ctx.pop()
            while body and body[-1].strip() == "break":
                body.pop()
            if any(l.strip() == "break" for l in body):
                raise Unsupported("switch 中间 break")
            body = ["    " + l for l in body] or ["    pass"]
            sections.append((conds, is_default, body))
        self.expect("}")
        # C# 的 default 可以写在任意位置，语义上总是最后匹配
        ordered = [x for x in sections if not (x[1] or not x[0])] + [x for x in sections if (x[1] or not x[0])]
        for conds, is_default, body in ordered:
            if is_default or not conds:
                lines += (["else:"] if not first else ["if True:"]) + body
            else:
                lines += [("if " if first else "elif ") + " or ".join(conds) + ":"] + body
            first = False
        return lines

    def _params(self):
        self.expect("(")
        params, outs, defaults = [], [], []
        while not self.at(")"):
            while self.peek().v in ("this", "params", "ref", "scoped") or self.at("[") or (self.at("in") and self.peek(1).k == "id"):
                if self.at("["):
                    while not self.at("]"):
                        self.next()
                    self.next()
                    continue
                self.next()
            is_out = False
            if self.at("out"):
                self.next()
                is_out = True
            s = self.i
            self.try_type()
            if not (self.peek().k == "id"):
                self.i = s
            nm = self.next().v
            d = None
            if self.accept("="):
                d = self.expr(0)
            if is_out:
                outs.append(pyname(nm))
            else:
                params.append(nm)
                defaults.append(pyname(nm) + (f"={d}" if d is not None else ""))
            self.accept(",")
        self.expect(")")
        return params, outs, defaults


STRUCT_MAP = {}
ENUM_MAP = {}


def _split_interp(raw):
    """把内插字符串内容拆成 [(is_expr, text, fmt)]。'{{' 已在词法阶段折叠为 '{'。"""
    parts, buf, i, n = [], [], 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch == "{":
            depth, j = 1, i + 1
            while j < n and depth:
                if raw[j] in "{([":
                    depth += 1
                elif raw[j] in "})]":
                    depth -= 1
                elif raw[j] == '"':
                    k = raw.find('"', j + 1)
                    j = k if k > 0 else j
                j += 1
            inner = raw[i + 1:j - 1]
            if buf:
                parts.append((False, "".join(buf), None))
                buf = []
            # 顶层 ':' 或 ',' 是格式/对齐
            d, cut = 0, None
            for k, c2 in enumerate(inner):
                if c2 in "([{":
                    d += 1
                elif c2 in ")]}":
                    d -= 1
                elif c2 in ":," and d == 0 and "?" not in inner[:k]:
                    cut = k
                    break
            if cut is not None:
                parts.append((True, inner[:cut], inner[cut:]))
            else:
                parts.append((True, inner, None))
            i = j
            continue
        if ch == "}" and i + 1 < n and raw[i + 1] == "}":
            buf.append("}")
            i += 2
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append((False, "".join(buf), None))
    return parts


def _default_for(ty):
    if ty and ty.endswith("?"):
        return "None"       # Nullable<T> 的默认值是 null（例如 UsePotionAction.TargetId: uint?；以前错给成 0）
    if ty and not ty.endswith("?"):
        sb = re.sub(r"<.*>", "", ty).split(".")[-1]
        if sb in STRUCT_MAP:
            return STRUCT_MAP[sb] + "()"
        if sb in ENUM_MAP:
            return ENUM_MAP[sb] + "(0)"
    b = re.sub(r"<.*>", "", ty or "").rstrip("?")
    if b in ("int", "decimal", "float", "double", "long", "uint"):
        return "0"
    if b == "bool":
        return "False"
    return "None"


def _is_literal(v):
    return re.fullmatch(r"-?[\d.]+|'.*'|\".*\"|True|False|None", v) is not None

