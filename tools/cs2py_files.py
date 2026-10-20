"""cs2py_files: 整文件 C# → Python 转译（多类型/枚举/接口/重载/构造/泛型/扩展方法）。
在 cs2py_core 的表达式/语句解析器之上构建。所有生成类放进同一个全局命名空间（C# 按简单名互相引用）。"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cs2py_core as core  # noqa: E402
from cs_patches import apply_patches  # noqa: E402
from cs2py_core import (lex, Parser, Ctx, Unsupported, _AssignSignal, _DropSignal, pyname, KEYWORDS_TYPES,  # noqa
                        _default_for, _is_literal, _split_targs)

MODS = ("public", "private", "protected", "internal", "static", "override", "virtual", "abstract", "sealed", "async",
        "readonly", "const", "new", "extern", "unsafe", "volatile", "partial", "required", "file", "ref", "fixed")
TYPE_KW = ("class", "struct", "interface", "enum", "record", "delegate")
SKIP_MEMBER_RE = re.compile(r"HoverTip|Vfx|Sfx|Portrait|Anim$|Animation|Visual(?!CardPool)|Spine|Scene|Bestiary|"
                            r"Icon|Image|Texture|Material|Sound|Audio|Glow|Banner|Overlay|LocString|Flavor|"
                            r"ExtraRunAssetPaths|FlashSfx|_locTable|L10N|Color$|Tween|Shake|OnEnqueuePlayVfx|"
                            r"AssetPaths|Dialogue|^locTable$|Shader|Particles|Godot")
SKIP_TYPES = ("Texture2D", "Color", "PackedScene", "CompressedTexture2D", "LocString", "Material", "ShaderMaterial",
              "Node", "Node2D", "Control", "Vector2", "Tween", "AudioStream")


class TInfo:
    """pass-1 类型信息"""
    def __init__(self, name, kind, outer=None):
        self.name = name
        self.kind = kind
        self.outer = outer
        self.pyname = name if outer is None else f"{outer.pyname}__{name}"
        self.bases = []          # 简单名
        self.base_targs = []     # 第一个基类的泛型实参（字符串）
        self.gparams = []
        self.members = set()
        self.statics = set()
        self.nested = {}
        self.file = None


TYPES = {}       # 顶层简单名 -> TInfo
EVENT_NAMES = set()
TYPES_ALT = {}   # 重名类型（不同命名空间）：name -> [TInfo]，pyname 加目录后缀
ALL_TYPES = []
DUPES = []


def skip_balanced(p, open_, close):
    depth = 0
    while True:
        t = p.next()
        if t.k == "eof":
            return
        if t.v == open_:
            depth += 1
        elif t.v == close:
            depth -= 1
            if depth == 0:
                return


def skip_attrs(p):
    while p.at("["):
        skip_balanced(p, "[", "]")


def read_mods(p):
    mods = set()
    while p.peek().k == "id" and p.peek().v in MODS and not (p.peek().v == "new" and p.at("(", 1)):
        mods.add(p.next().v)
    return mods


def read_gparams(p):
    gp = []
    if p.at("<"):
        p.next()
        while not p.at(">"):
            t = p.next()
            if t.k == "id" and t.v not in ("in", "out"):
                gp.append(t.v)
        p.next()
    return gp


def skip_member_tokens(p):
    """跳过一个成员（到 ; 或配平的 }），用于 pass-1"""
    depth = 0
    par = 0
    while True:
        t = p.next()
        if t.k == "eof":
            return
        if t.v in ("(", "["):
            par += 1
        elif t.v in (")", "]"):
            par -= 1
        elif t.v == "{":
            depth += 1
        elif t.v == "}":
            depth -= 1
            if depth == 0 and par == 0 and (p.at(".") or p.at(")") or p.at(",") or p.at("?.")):
                continue
            if depth == 0 and par == 0:
                if p.at(";"):
                    p.next()
                elif p.at("="):
                    while not p.at(";"):
                        p.next()
                    p.next()
                return
            if depth < 0:
                p.i -= 1
                return
        elif t.v == ";" and depth == 0 and par == 0:
            return


def parse_type_header(p, kind):
    """在 class/struct/... 关键字之后：名字、泛型、主构造、基类。返回 (name, gparams, prim_params_tokens_start, bases, base_targs)"""
    name = p.next().v
    gp = read_gparams(p)
    prim = None
    if p.at("("):
        prim = p.i
        skip_balanced(p, "(", ")")
    bases, btargs = [], []
    p.base_args_i = None
    if p.accept(":"):
        first = True
        while not (p.at("{") or p.at("where") or p.at(";")):
            ty = p._type()
            b = re.sub(r"<.*>", "", ty).split(".")[-1]
            bases.append(b)
            if first:
                gm = re.match(r"[\w.]+<(.+)>$", ty)
                if gm:
                    btargs = _split_targs(gm.group(1))
                if p.at("("):   # 主构造基类实参
                    p.base_args_i = p.i
                    skip_balanced(p, "(", ")")
            first = False
            p.accept(",")
    while p.at("where"):
        while not (p.at("{") or p.at(";")):
            p.next()
    return name, gp, prim, bases, btargs


def scan_types(p, outer, fname):
    """pass-1：扫描当前层的类型声明（文件顶层或类体内）。p 停在类型体 '{' 之后时调用 scan_body。"""
    res = []
    while True:
        t = p.peek()
        if t.k == "eof" or t.v == "}":
            return res
        if t.v in ("using",) and outer is None:
            while not p.at(";"):
                p.next()
            p.next()
            continue
        if t.v == "namespace":
            p.next()
            while not (p.at(";") or p.at("{")):
                p.next()
            if p.accept("{"):
                res += scan_types(p, outer, fname)
                p.expect("}")
            else:
                p.next()
            continue
        skip_attrs(p)
        mods = read_mods(p)
        if p.peek().v in TYPE_KW:
            kind = p.next().v
            if kind == "record" and p.peek().v in ("class", "struct"):
                p.next()
            if kind == "delegate":
                while not p.at(";"):
                    p.next()
                p.next()
                continue
            name, gp, prim, bases, btargs = parse_type_header(p, kind)
            ti = TInfo(name, kind, outer)
            ti.file = fname
            ti.mods = mods
            ti.gparams = gp
            ti.bases = bases
            ti.base_targs = btargs
            ti.base_args_i = getattr(p, "base_args_i", None)
            ALL_TYPES.append(ti)
            if outer is None:
                if name in TYPES:
                    DUPES.append((name, fname, TYPES[name].file))
                    ti.pyname = name + "_" + os.path.basename(os.path.dirname(fname))
                    TYPES_ALT.setdefault(name, []).append(ti)
                else:
                    TYPES[name] = ti
            else:
                outer.nested[name] = ti
            if prim is not None:
                q = p.i
                p.i = prim + 1
                while not p.at(")"):
                    skip_attrs(p)
                    p.try_type()
                    ti.members.add(p.next().v)
                    if p.accept("="):
                        p.expr(0)
                    p.accept(",")
                p.i = q
            ti.toks = p.t
            ti.prim_i = prim
            if p.accept(";"):
                ti.body_i = None
                continue
            ti.body_i = p.i
            p.expect("{")
            if kind == "enum":
                while not p.at("}"):
                    skip_attrs(p)
                    ti.members.add(p.next().v)
                    while not (p.at(",") or p.at("}")):
                        p.next()
                    p.accept(",")
                p.expect("}")
            else:
                scan_body(p, ti, fname)
                p.expect("}")
            p.accept(";")
            continue
        if outer is None:
            # 顶层杂项（global using 等）
            p.next()
            continue
        return res


def scan_body(p, ti, fname):
    while not p.at("}"):
        if p.peek().k == "eof":
            return
        s = p.i
        skip_attrs(p)
        mods = read_mods(p)
        if p.peek().v in TYPE_KW:
            p.i = s
            scan_types(p, ti, fname)
            continue
        if p.at("event"):
            p.next()
            p.try_type()
            nm = p.next().v
            EVENT_NAMES.add(nm)
            ti.members.add(nm)
            if "static" in mods:
                ti.statics.add(nm)
            skip_member_tokens(p)
            continue
        if p.at(ti.name) and p.at("(", 1):   # ctor
            p.next()
            skip_member_tokens(p)
            continue
        if p.at("~"):
            skip_member_tokens(p)
            continue
        ty = p.try_type()
        if ty is None:
            skip_member_tokens(p)
            continue
        if p.at("operator") or p.at("implicit") or p.at("explicit"):
            skip_member_tokens(p)
            continue
        if p.at("this") and p.at("[", 1):
            ti.members.add("__getitem__")
            skip_member_tokens(p)
            continue
        if p.peek().k != "id":
            skip_member_tokens(p)
            continue
        nm = p.next().v
        while p.at(".") and p.peek(1).k == "id":
            p.next()
            nm = p.next().v
        ti.members.add(nm)
        if "static" in mods or "const" in mods:
            ti.statics.add(nm)
        # 多变量字段声明 a = 1, b = 2;
        if not p.at("(") and not p.at("<") and not p.at("{") and not p.at("=>"):
            depth = 0
            while True:
                t = p.next()
                if t.k == "eof":
                    break
                if t.v in ("(", "[", "{"):
                    depth += 1
                elif t.v in (")", "]", "}"):
                    depth -= 1
                elif t.v == "," and depth == 0 and p.peek().k == "id":
                    nm2 = p.peek().v
                    ti.members.add(nm2)
                    if "static" in mods or "const" in mods:
                        ti.statics.add(nm2)
                elif t.v == ";" and depth == 0:
                    break
            continue
        skip_member_tokens(p)


def lookup_type(name):
    return TYPES.get(name)


def chain(ti, seen=None):
    """ti 及其基类链（只含已知类型）"""
    seen = seen or set()
    while ti is not None and id(ti) not in seen:
        seen.add(id(ti))
        yield ti
        nxt = None
        for b in ti.bases:
            bt = find_type_from(ti, b)
            if bt is not None and bt.kind != "interface":
                nxt = bt
                break
        ti = nxt


def iface_chain(ti):
    out = []
    for c in chain(ti):
        out.append(c)
        for b in c.bases:
            bt = find_type_from(c, b)
            if bt is not None and bt.kind == "interface":
                out.append(bt)
    return out


def find_type_from(ti, name):
    """在 ti 的嵌套/外层/基类嵌套中查找类型名"""
    o = ti
    while o is not None:
        if name in o.nested:
            return o.nested[name]
        for b in o.bases:
            bt = TYPES.get(b)
            if bt is not None and bt is not o and name in bt.nested:
                return bt.nested[name]
        o = o.outer
    if name in TYPES_ALT:
        d = os.path.dirname(ti.file or "")
        for alt in TYPES_ALT[name]:
            if os.path.dirname(alt.file) == d:
                return alt
    return TYPES.get(name)


def find_member(ti, v):
    for c in iface_chain(ti):
        if v in c.members:
            return c
    return None


class Ctx2(Ctx):
    def __init__(self, cur, static=False, gparams=(), cur_method=None):
        members = set()
        for c in iface_chain(cur):
            members |= c.members
        super().__init__(members, set(), cur_method=cur_method)
        self.cur = cur
        self.static = static
        self.mgparams = set(gparams)


class P2(Parser):
    def _resolve(self, v):
        c = self.ctx
        if not isinstance(c, Ctx2):
            return super()._resolve(v)
        if c.is_local(v) or v in c.mgparams:
            return pyname(v)
        if v in core.DROP_IDS or (core.is_node_name(v) and v not in core.KNOWN_MODELS and find_type_from(c.cur, v) is None):
            raise _DropSignal()
        if v in c.dropped_locals:
            raise _DropSignal()
        cur = c.cur
        if v in cur.gparams and not c.static:
            return "self._g_" + v
        # Color Color：Type.Member 形式且 Member 属于该类型时优先类型
        if self.at(".") and self.peek(1).k == "id":
            tt = find_type_from(cur, v)
            if tt is not None and self.peek(1).v in tt.members and \
                    (find_member(cur, v) is None or tt.kind == "enum" or self.peek(1).v in tt.statics
                     or tt.nested.get(self.peek(1).v) is not None):
                return tt.pyname
        owner = find_member(cur, v)
        if owner is not None:
            if v in owner.statics or c.static:
                return owner.pyname + "." + pyname(v)
            return "self." + pyname(v)
        o = cur.outer
        while o is not None:
            ow = find_member(o, v)
            if ow is not None:
                return ow.pyname + "." + pyname(v)
            o = o.outer
        tt = find_type_from(cur, v)
        if tt is not None:
            return tt.pyname
        if v in ("GetType", "ToString", "Equals", "GetHashCode", "MemberwiseClone") and not c.static:
            return "self." + v
        return pyname(v)

    def _type_ref(self, ty):
        base = re.sub(r"<.*>", "", ty).replace("[]", "").rstrip("?")
        base = base.split(".")[-1]
        if base in KEYWORDS_TYPES:
            return {"int": "int", "decimal": "float", "float": "float", "double": "float", "long": "int",
                    "bool": "bool", "string": "str", "object": "object", "uint": "int", "byte": "int"}.get(base, "object")
        c = self.ctx
        if isinstance(c, Ctx2):
            if base in c.mgparams:
                return base
            if base in c.cur.gparams:
                return "object" if c.static else "self._g_" + base
            parts = re.sub(r"<.*>", "", ty).replace("[]", "").rstrip("?").split(".")
            if len(parts) >= 2 and base in TYPES_ALT:
                seg = parts[-2]
                for cand in [TYPES.get(base)] + TYPES_ALT[base]:
                    if cand is not None and os.path.basename(os.path.dirname(cand.file)) == seg:
                        return cand.pyname
            tt = find_type_from(c.cur, base)
            if tt is not None:
                return tt.pyname
        return base


def params2(p):
    """返回 [(name, type, default_expr, kind)]，kind in ('', 'out', 'params', 'this')"""
    p.expect("(")
    res = []
    while not p.at(")"):
        kind = ""
        while True:
            if p.at("["):
                skip_balanced(p, "[", "]")
                continue
            if p.peek().v in ("this", "params", "ref", "scoped", "out", "readonly") or \
                    (p.at("in") and p.peek(1).k == "id"):
                v = p.next().v
                if v in ("this", "params", "out"):
                    kind = v
                continue
            break
        s = p.i
        ty = p.try_type()
        if not (p.peek().k == "id"):
            p.i = s
            ty = "object"
        nm = p.next().v
        d = None
        if p.accept("="):
            d = p.expr(0)
        res.append((nm, ty or "object", d, kind))
        p.accept(",")
    p.expect(")")
    return res


_orig_new = Parser._new


def _p2_new(self):
    r = _orig_new(self)
    c = self.ctx
    if isinstance(c, Ctx2):
        m = re.match(r"^(_init_obj\()?(\w+)\(", r)
        if m:
            tt = find_type_from(c.cur, m.group(2))
            if tt is not None and tt.pyname != m.group(2):
                r = r[:m.start(2)] + tt.pyname + r[m.end(2):]
    return r


P2._new = _p2_new


def ind(lines, n=1):
    return ["    " * n + l for l in lines]


class Member:
    pre = ()
    mods = ()
    static = False

    def __init__(self, kind, name, **kw):
        self.kind = kind
        self.name = name
        self.__dict__.update(kw)


class TypeTr:
    """pass-2：翻译一个类型（不含嵌套，嵌套类型单独翻译）"""

    def __init__(self, toks, ti):
        self.toks = toks
        self.ti = ti
        self.errors = []
        self.extensions = []   # (target_type, method_name)

    def mkp(self, i, static=False, gparams=(), cur_method=None):
        p = P2(self.toks, Ctx2(self.ti, static, gparams, cur_method))
        p.i = i
        return p

    def body_with_pre(self, p, body):
        pre = []
        for pr in p.ctx.pre:
            pre += ["    " + l for l in pr]
        p.ctx.pre = []
        return pre + body

    def expr_body(self, p, is_void):
        try:
            e = p.expr(0)
            p.expect(";")
            return ["    " + (e if is_void else p._ret(e))]
        except _AssignSignal as a:
            p.accept(";")
            return ["    " + p._assign_line(a)]
        except _DropSignal:
            while not p.at(";"):
                p.next()
            p.next()
            return ["    return None"]

    def parse_members(self):
        ti = self.ti
        p = self.mkp(ti.body_i)
        p.expect("{")
        out = []
        while not p.at("}"):
            if p.peek().k == "eof":
                break
            s = p.i
            try:
                m = self.member(p)
                if m is not None:
                    out += m if isinstance(m, list) else [m]
            except (Unsupported, IndexError, _AssignSignal, _DropSignal, KeyError, ValueError, TypeError,
                    AttributeError, RecursionError) as e:
                self.errors.append(f"{type(e).__name__}: {str(e)[:100]} L{self.toks[s].ln}-{self.toks[min(p.i, len(self.toks) - 1)].ln}")
                p.i = s
                skip_attrs(p)
                read_mods(p)
                if p.peek().v in TYPE_KW:
                    self._skip_type(p)
                else:
                    nm = self._guess_name(s)
                    skip_member_tokens(p)
                    if nm:
                        out.append(Member("broken", nm))
        return out

    def _guess_name(self, s):
        t = self.toks
        i = s
        while i < len(t) and t[i].v not in ("(", "=", ";", "{", "=>"):
            i += 1
        return t[i - 1].v if i > s and t[i - 1].k == "id" else None

    def _skip_type(self, p):
        while not (p.at("{") or p.at(";")):
            p.next()
        if p.at(";"):
            p.next()
            return
        skip_balanced(p, "{", "}")
        p.accept(";")

    def member(self, p):
        ti = self.ti
        self._regex = None
        while p.at("["):
            if p.peek(1).v == "GeneratedRegex" and p.peek(3).k == "str":
                self._regex = p.peek(3).v
            skip_balanced(p, "[", "]")
        mods = read_mods(p)
        static = "static" in mods or "const" in mods
        if p.peek().v in TYPE_KW:
            if p.peek().v == "delegate":
                while not p.at(";"):
                    p.next()
                p.next()
                return None
            self._skip_type(p)
            return None
        if p.at("event"):
            p.next()
            p.try_type()
            nm = p.next().v
            skip_member_tokens(p)
            return Member("field", nm, init="_Event()", static=static)
        if p.at("~"):
            skip_member_tokens(p)
            return None
        if p.at(ti.name) and p.at("(", 1):
            p.next()
            return self.ctor(p, static)
        ty = p.try_type()
        if ty is None:
            raise Unsupported(f"成员类型 {p.peek().v}")
        if p.at("operator") or p.at("implicit") or p.at("explicit"):
            skip_member_tokens(p)
            return None
        if p.at("this") and p.at("[", 1):
            return self.indexer(p, ty)
        nm = p.next().v
        while p.at(".") and p.peek(1).k == "id":
            p.next()
            nm = p.next().v
        base_ty = re.sub(r"<.*>", "", ty).split(".")[-1].rstrip("?")
        path_like = re.search(r"Paths?$", nm) and "string" in ty.lower()
        logic_ret = base_ty in ("bool", "int", "decimal") and (p.at("(") or p.at("<")) and "Glow" not in nm
        if not logic_ret and (path_like or SKIP_MEMBER_RE.search(nm) or "IHoverTip" in ty or base_ty in SKIP_TYPES or core.is_node_name(base_ty)):
            is_method = p.at("(") or p.at("<")
            skip_member_tokens(p)
            mm = Member("skip", nm, method=is_method, static=static)
            SKIPPED.append((ti.name, nm, ty))
            mm.ret_self = (base_ty == ti.name and not static)
            mm.loc = base_ty in ("LocString", "AncientDialogueSet", "MerchantDialogueSet")
            mm.coll = (base_ty in ("List", "IEnumerable", "IReadOnlyList", "HashSet", "IList", "ICollection",
                                   "IReadOnlyCollection", "Dictionary", "IReadOnlyDictionary") or ty.endswith("[]"))
            return mm
        gps = read_gparams(p) if p.at("<") else []
        if p.at("("):
            return self.method(p, nm, ty, mods, gps)
        p.ctx = Ctx2(ti, static, (), nm)
        if p.at("=>"):
            p.next()
            body = self.expr_body(p, False)
            return Member("prop", nm, getter=self.body_with_pre(p, body), setter=None, static=static, mods=mods)
        if p.at("{"):
            return self.prop(p, nm, ty, mods, static)
        decls = [(nm, None)]
        while True:
            if p.accept("="):
                try:
                    e = p.expr(0)
                except _DropSignal:
                    depth = 0
                    while not ((p.at(";") or p.at(",")) and depth == 0):
                        t = p.next()
                        depth += t.v in ("(", "{", "[")
                        depth -= t.v in (")", "}", "]")
                    e = "None"
                decls[-1] = (decls[-1][0], e)
            if p.accept(","):
                decls.append((p.next().v, None))
                continue
            break
        p.expect(";")
        pre = self.body_with_pre(p, [])
        res = []
        for n, e in decls:
            val = e if e is not None else _default_for(ty)
            res.append(Member("field", n, init=val, static=static, pre=pre))
        return res

    def _declare_params(self, ctx, ps):
        for (n, t, d, k) in ps:
            ctx.declare(n)

    def _sig(self, ps, self_arg=True, lead=()):
        parts = (["self"] if self_arg else [])
        for (n, t, d, k) in ps:
            if k == "out":
                parts.append(pyname(n))
                continue
            if k == "params":
                parts.append("*" + pyname(n))
            else:
                parts.append(pyname(n) + (f"={d}" if d is not None else ""))
        if lead:
            parts.append("_g=None")
        return ", ".join(parts)

    def ctor(self, p, static):
        ti = self.ti
        ctx = Ctx2(ti, static, (), "__ctor__")
        p.ctx = ctx
        ps = params2(p)
        self._declare_params(ctx, ps)
        chain_kind, chain_args = None, None
        if p.accept(":"):
            chain_kind = p.next().v
            chain_args = p.call_args()
        body = []
        if p.at("{"):
            body = p.block_lines(1)
        elif p.at("=>"):
            p.next()
            body = self.expr_body(p, True)
        else:
            p.expect(";")
        body = [l for l in self.body_with_pre(p, body) if l.strip() and l.strip() != "pass"]
        if static:
            return Member("sctor", "__sctor__", body=body)
        return Member("ctor", "__init__", params=ps, chain=chain_kind, chain_args=chain_args, body=body)

    def method(self, p, nm, ty, mods, gps):
        ti = self.ti
        static = "static" in mods
        ctx = Ctx2(ti, static, gps, nm)
        p.ctx = ctx
        ps = params2(p)
        self._declare_params(ctx, ps)
        outs = [pyname(n) for (n, t, d, k) in ps if k == "out"]
        ctx.out_params = outs
        while p.at("where"):
            while not (p.at("{") or p.at("=>") or p.at(";")):
                p.next()
        if p.at(";"):
            p.next()
            if self._regex is not None:
                return Member("method", nm, params=ps, gparams=gps, static=static, ext=None,
                              body=[f"    return CsRegex({self._regex!r})"], mods=mods, rtype=ty)
            return Member("abstract", nm)
        if p.at("=>"):
            p.next()
            body = self.expr_body(p, ty == "void" or ty == "Task")
        else:
            body = p.block_lines(1)
        body = self.body_with_pre(p, body)
        if any(re.match(r"\s*yield\b", l) for l in body):
            body = ["    def _gen():"] + ["    " + l for l in body] + ["    return _LazyEnum(_gen)"]
        init_out = ["    " + o + " = None" for o in outs]
        tail = ["    return (None, " + ", ".join(outs) + ")"] if outs else []
        ext = None
        if static and ps and ps[0][3] == "this":
            ext = re.sub(r"<.*>", "", ps[0][1]).split(".")[-1].rstrip("?")
        return Member("method", nm, params=ps, gparams=gps, static=static, ext=ext,
                      body=init_out + (body or ["    pass"]) + tail, mods=mods, rtype=ty)

    def prop(self, p, nm, ty, mods, static):
        ctx = p.ctx
        if "abstract" in mods:
            skip_balanced(p, "{", "}")
            return Member("abstract", nm)
        p.next()
        getter = setter = None
        auto = True
        while not p.at("}"):
            skip_attrs(p)
            while p.peek().v in ("private", "protected", "internal", "public", "readonly"):
                p.next()
            acc = p.next().v
            if p.at(";"):
                p.next()
                continue
            auto = False
            ctx.push()
            if acc in ("set", "init"):
                ctx.declare("value")
            if p.at("=>"):
                p.next()
                body = self.expr_body(p, acc != "get")
            else:
                body = p.block_lines(1)
            ctx.pop()
            body = self.body_with_pre(p, body)
            if any(re.match(r"\s*yield\b", l) for l in body):
                body = ["    def _gen():"] + ["    " + l for l in body] + ["    return _LazyEnum(_gen)"]
            if acc == "get":
                getter = body or ["    return None"]
            else:
                setter = body or ["    pass"]
        p.expect("}")
        init = None
        if p.accept("="):
            try:
                init = p.expr(0)
            except _DropSignal:
                while not p.at(";"):
                    p.next()
                init = "None"
            p.expect(";")
        if auto:
            val = init if init is not None else _default_for(ty)
            return Member("autoprop", nm, init=val, static=static, mods=mods, pre=self.body_with_pre(p, []))
        return Member("prop", nm, getter=getter or ["    return None"], setter=setter, static=static, mods=mods)

    def indexer(self, p, ty):
        p.next()
        ctx = Ctx2(self.ti, False, (), "__getitem__")
        p.ctx = ctx
        p.expect("[")
        ps = []
        while not p.at("]"):
            p.try_type()
            n = p.next().v
            ps.append(n)
            ctx.declare(n)
            p.accept(",")
        p.expect("]")
        res = []
        if p.at("=>"):
            p.next()
            body = self.body_with_pre(p, self.expr_body(p, False))
            return [Member("rawmethod", "__getitem__", sig="self, " + ", ".join(ps), body=body)]
        p.expect("{")
        while not p.at("}"):
            acc = p.next().v
            ctx.push()
            if acc == "set":
                ctx.declare("value")
            if p.at("=>"):
                p.next()
                body = self.expr_body(p, acc != "get")
            else:
                body = p.block_lines(1)
            ctx.pop()
            body = self.body_with_pre(p, body)
            if acc == "get":
                res.append(Member("rawmethod", "__getitem__", sig="self, " + ", ".join(ps), body=body))
            else:
                res.append(Member("rawmethod", "__setitem__", sig="self, " + ", ".join(ps) + ", value", body=body))
        p.expect("}")
        return res

    # ---------------------------------------------------------------- emission
    def known_bases(self):
        res = []
        for b in self.ti.bases:
            bt = find_type_from(self.ti, b)
            if bt is not None and bt is not self.ti:
                res.append(bt)
        return res

    def base_class(self):
        for bt in self.known_bases():
            if bt.kind not in ("interface",):
                return bt
        return None


_SEQ_NAMES = {"IEnumerable", "IReadOnlyList", "List", "IList", "ICollection", "IReadOnlyCollection", "HashSet", "ISet",
              "IReadOnlySet"}


def _seq_elem(t):
    m = re.fullmatch(r"(?:[\w.]+\.)?(\w+)<([\w.]+)\??>\??", t.strip())
    if m and m.group(1) in _SEQ_NAMES:
        return m.group(2).split(".")[-1]
    return None


SKIPPED = []


def sig_key(name, ps):
    ts = []
    for (n, t, d, k) in ps:
        if k == "out":
            ts.append("out")
            continue
        b = re.sub(r"<.*>", "", t).split(".")[-1].replace("[]", "Arr").rstrip("?")
        el = _seq_elem(t)
        ts.append(re.sub(r"\W", "", b) + (("Of" + el) if el else ""))
    return f"{name}__{'_'.join(ts) or 'v'}"


def ptypes(ps):
    res = []
    for (n, t, d, k) in ps:
        if k == "out":
            res.append(("out", False, "out"))
            continue
        bt = re.sub(r"<.*>", "", t).split(".")[-1].rstrip("?")
        el = _seq_elem(t)
        if el:
            bt += "<" + el + ">"
        res.append(("object" if k == "params" else bt, d is not None, k))
    return res


def emit_enum(ti):
    p = P2(ti.toks, Ctx(set(), set()))
    p.i = ti.body_i
    p.expect("{")
    vals = []
    env = {}
    k = 0
    while not p.at("}"):
        skip_attrs(p)
        en = p.next().v
        if p.accept("="):
            raw = []
            while not (p.at(",") or p.at("}")):
                raw.append(p.next().v)
            src = re.sub(r"(\d)[uUlL]+\b", r"\1", " ".join(raw))
            src = re.sub(r"\b(\w+)\.(\w+)\b", r"\2", src)
            try:
                k = int(eval(src, {}, dict(env)))
            except Exception:
                k = k
        env[en] = k
        vals.append((pyname(en), k))
        k += 1
        p.accept(",")
    return [f"{ti.pyname} = cs_enum({ti.name!r}, {vals!r})"]


def overloaded_names(ti, MEMBERS):
    """chain(ti) 中出现过多个定义的方法名"""
    cnt = {}
    for c in chain(ti):
        seen = {}
        for m in MEMBERS.get(id(c), []):
            if m.kind == "method":
                seen.setdefault(m.name, set()).add(sig_key(m.name, m.params))
        for n, ks in seen.items():
            cnt.setdefault(n, set()).update(ks)
    return {n for n, ks in cnt.items() if len(ks) > 1}


def emit_class(tr, members, MEMBERS, EXT):
    ti = tr.ti
    py = ti.pyname
    kb = [bt.pyname for bt in tr.known_bases()]
    bc = tr.base_class()
    head = f"class {py}(*_bases({', '.join(kb)})):" if kb else f"class {py}(CsObject):"
    L = [head, f"    _cs_name = {ti.name!r}"]
    if ti.kind == "record":
        L.append("    _cs_record = True")
    if "abstract" in getattr(ti, "mods", ()) or ti.kind == "interface":
        L.append("    _cs_abstract = True")
    sinit = []
    fi = []
    ovl = overloaded_names(ti, MEMBERS)
    has_inst_fields = False
    base_members = set()
    if bc is not None:
        for c in iface_chain(bc):
            base_members |= c.members
    for m in members:
        if m.kind in ("field", "autoprop"):
            if m.static:
                if not m.pre and _is_literal(m.init):
                    L.append(f"    {pyname(m.name)} = {m.init}")
                else:
                    L.append(f"    {pyname(m.name)} = None")
                    sinit += list(m.pre) + [f"    {py}.{pyname(m.name)} = {m.init}"]
            elif m.kind == "autoprop" and ("override" in m.mods or m.name in base_members):
                n = pyname(m.name)
                L += [f"    def _get_{m.name}(self):", f"        return self.__dict__.get('_ap_{m.name}')",
                      f"    def _set_{m.name}(self, value):", f"        self.__dict__['_ap_{m.name}'] = value",
                      f"    {n} = property(_get_{m.name}, _set_{m.name})"]
                fi += list(m.pre) + [f"    self.__dict__['_ap_{m.name}'] = {m.init}"]
                has_inst_fields = True
            else:
                fi += list(m.pre) + [f"    self.{pyname(m.name)} = {m.init}"]
                has_inst_fields = True
        elif m.kind == "prop":
            n = pyname(m.name)
            if m.static:
                L += [f"    def _get_{m.name}():"] + ind(m.getter)
                L.append(f"    {n} = cs_sprop(_get_{m.name})")
            else:
                L += [f"    def _get_{m.name}(self):"] + ind(m.getter)
                if m.setter:
                    L += [f"    def _set_{m.name}(self, value):"] + ind(m.setter)
                    L.append(f"    {n} = cs_property(_get_{m.name}, _set_{m.name})")
                else:
                    L.append(f"    {n} = cs_property(_get_{m.name})")
        elif m.kind == "skip":
            if m.method:
                rv = "self" if getattr(m, "ret_self", False) else ("Dummy('loc')" if getattr(m, "loc", False) else "None")
                L.append(f"    def {pyname(m.name)}(self, *a, **k): return {rv}")
            elif getattr(m, "loc", False):
                L.append(f"    {pyname(m.name)} = Dummy('loc')")
            elif getattr(m, "coll", False):
                L.append(f"    {pyname(m.name)} = _EmptyColl()")
            else:
                L.append(f"    {pyname(m.name)} = None")
        elif m.kind == "broken":
            L.append(f"    {pyname(m.name)} = cs_broken({py + '.' + m.name!r})")
        elif m.kind == "rawmethod":
            L += [f"    def {m.name}({m.sig}):"] + ind(m.body)
        elif m.kind == "sctor":
            sinit += m.body
    # methods
    groups = {}
    for m in members:
        if m.kind == "method":
            groups.setdefault(m.name, []).append(m)
    for name, ms in groups.items():
        for m in ms:
            fname = sig_key(name, m.params) if name in ovl else pyname(name)
            lead = list(m.gparams)
            pro = [f"    {g} = _g[{i}] if _g else None" for i, g in enumerate(lead)]
            if m.static:
                L += ["    @staticmethod", f"    def {fname}({tr._sig(m.params, False, lead)}):"] + ind(pro + m.body)
            else:
                L += [f"    def {fname}({tr._sig(m.params, True, lead)}):"] + ind(pro + m.body)
            if m.ext:
                EXT.append((m.ext, name, py, fname))
        if name in ovl:
            st = all(m.static for m in ms)
            if st:
                L += ["    @staticmethod", f"    def {pyname(name)}(*a, **k):",
                      f"        return _dispatch({py}, None, {name!r}, a, k)"]
            else:
                L += [f"    def {pyname(name)}(self, *a, **k):",
                      f"        return _dispatch({py}, self, {name!r}, a, k)"]
    # overload tables (own + inherited variants)
    for name in sorted(ovl):
        rows = []
        seen = set()
        for c in chain(ti):
            for m in MEMBERS.get(id(c), []):
                if m.kind == "method" and m.name == name:
                    k = sig_key(name, m.params)
                    if k not in seen:
                        seen.add(k)
                        rows.append((k, [x[0] for x in ptypes(m.params)], 0,
                                     sum(1 for x in ptypes(m.params) if not x[1] and x[2] != "params"),
                                     any(x[2] == "params" for x in ptypes(m.params)),
                                     tuple(pyname(x[0]) for x in m.params)))
        if any(m.name == name for m in members if m.kind == "method"):
            L.append(f"    _ovl_{name} = {rows!r}")
            # 基类里该名字没有重载 → 基类方法名是普通名；为继承来的变体补一个别名
            own_keys = {sig_key(name, m.params) for m in members if m.kind == "method" and m.name == name}
            for c in list(chain(ti))[1:]:
                if name in overloaded_names(c, MEMBERS):
                    continue
                for m in MEMBERS.get(id(c), []):
                    if m.kind == "method" and m.name == name:
                        k2 = sig_key(name, m.params)
                        if k2 in own_keys:
                            continue
                        own_keys.add(k2)
                        if m.static:
                            L += ["    @staticmethod", f"    def {k2}(*a, **k):",
                                  f"        return {c.pyname}.{pyname(name)}(*a, **k)"]
                        else:
                            L += [f"    def {k2}(self, *a, **k):",
                                  f"        return {c.pyname}.{pyname(name)}(self, *a, **k)"]
    # ctors
    ctors = [m for m in members if m.kind == "ctor"]
    gp = list(ti.gparams)
    prim = prim_params(ti)
    btargs = []
    if bc is not None and ti.base_targs:
        pp = P2(ti.toks, Ctx2(ti))
        btargs = [pp._type_ref(a) for a in ti.base_targs]
    if fi:
        L += ["    def _fi(self):"] + ind(fi)
    def ctor_body(m):
        b = [f"    self._g_{g} = _g[{i}] if _g else None" for i, g in enumerate(gp)] + [f"    self.{pyname(n)} = {pyname(n)}" for n in prim]
        if m is not None and m.chain == "this":
            b.append(f"    {py}.__init__(self, {', '.join(([m.chain_args] if m.chain_args else []) + (['_g=_g'] if gp else []))})")
        else:
            if bc is not None:
                args = ([m.chain_args] if (m is not None and m.chain == "base" and m.chain_args) else [])
                if m is None and getattr(ti, "base_args_i", None) is not None:
                    pb = P2(ti.toks, Ctx2(ti))
                    for n in prim:
                        pb.ctx.declare(n)
                    pb.i = ti.base_args_i
                    ba = pb.call_args()
                    if ba:
                        args.append(ba)
                if btargs:
                    args.append(f"_g=({', '.join(btargs)},)")
                b.append(f"    {bc.pyname}.__init__(self{''.join(', ' + a for a in args)})")
            if fi:
                b.append(f"    {py}._fi(self)")
        b = b + (m.body if m is not None else [])
        return b or ["    pass"]
    is_struct = ti.kind == "struct" or (ti.kind == "record" and "struct" in getattr(ti, "mods", ()))
    if is_struct and ctors and all(m.params for m in ctors) and not gp:
        # C# 结构体总有隐式无参构造（default）；ilspycmd 9 不还原主构造函数时，显式构造器会挡住 MapCoord() 之类的调用
        for i, m in enumerate(ctors):
            L += [f"    def _ctor_o{i}({tr._sig(m.params, True, gp)}):"] + ind(ctor_body(m))
        L += ["    def _ctor_default(self):"] + ind(ctor_body(None))
        if len(ctors) == 1:
            L += ["    def __init__(self, *a, **k):", "        if a or k:", "            self._ctor_o0(*a, **k)",
                  "        else:", "            self._ctor_default()"]
        else:
            rows = []
            for i, m in enumerate(ctors):
                pt = ptypes(m.params)
                rows.append((f"_ctor_o{i}", [x[0] for x in pt], 0,
                             sum(1 for x in pt if not x[1] and x[2] != "params"), any(x[2] == "params" for x in pt),
                             tuple(pyname(x[0]) for x in m.params)))
            L.append(f"    _ovl___init__ = {rows!r}")
            L += ["    def __init__(self, *a, **k):", "        if not a and not k:", "            self._ctor_default()",
                  "        else:", f"            _dispatch({py}, self, '__init__', a, k)"]
    elif len(ctors) == 1:
        m = ctors[0]
        L += [f"    def __init__({tr._sig(m.params, True, gp)}):"] + ind(ctor_body(m))
    elif len(ctors) > 1:
        rows = []
        for i, m in enumerate(ctors):
            L += [f"    def _ctor_o{i}({tr._sig(m.params, True, gp)}):"] + ind(ctor_body(m))
            pt = ptypes(m.params)
            rows.append((f"_ctor_o{i}", [x[0] for x in pt], 0,
                         sum(1 for x in pt if not x[1] and x[2] != "params"), any(x[2] == "params" for x in pt),
                         tuple(pyname(x[0]) for x in m.params)))
        L.append(f"    _ovl___init__ = {rows!r}")
        L += ["    def __init__(self, *a, **k):", f"        _dispatch({py}, self, '__init__', a, k)"]
    elif fi or gp or prim or btargs:
        L += [f"    def __init__({', '.join(['self'] + [pyname(n) + '=None' for n in prim] + (['_g=None'] if gp else []))}):"] + ind(ctor_body(None))
    if sinit:
        L += ["    @staticmethod", "    def _static_init():"] + ind(sinit)
    if EVENT_NAMES:
        rx = re.compile(r"\.(" + "|".join(sorted(EVENT_NAMES)) + r") = None$")
        L = [rx.sub(r".\1 = _Event()", l) for l in L]
    return L


def prim_params(ti):
    if getattr(ti, "prim_i", None) is None:
        return []
    p = P2(ti.toks, Ctx(set(), set()))
    p.i = ti.prim_i + 1
    res = []
    while not p.at(")"):
        skip_attrs(p)
        p.try_type()
        res.append(p.next().v)
        if p.accept("="):
            p.expr(0)
        p.accept(",")
    return res


def run(core_dir, out_path, rels, exclude=(), report_path=None):
    files = []
    for r in rels:
        full = os.path.join(core_dir, r)
        if full.endswith(".cs"):
            files.append(full)
            continue
        for dp, dn, fn in os.walk(full):
            for f in sorted(fn):
                if f.endswith(".cs"):
                    files.append(os.path.join(dp, f))
    files = sorted(set(files))
    # pass 1
    for f in files:
        src = open(f, encoding="utf-8-sig").read()
        src = apply_patches(os.path.relpath(f, core_dir), src)
        toks = lex(src)
        p = P2(toks, Ctx(set(), set()))
        try:
            scan_types(p, None, os.path.relpath(f, core_dir))
        except Exception as e:  # noqa
            print("SCAN FAIL", f, type(e).__name__, e)
    excl = set(exclude)
    for t in ALL_TYPES:
        if t.kind == "struct" or (t.kind == "record" and "struct" in getattr(t, "mods", ())):
            core.STRUCT_MAP.setdefault(t.name, t.pyname)
        if t.kind == "enum":
            core.ENUM_MAP.setdefault(t.name, t.pyname)
    core.KNOWN_MODELS |= set(TYPES)
    core.GLOBAL_TYPES |= set(TYPES)
    todo = [t for t in ALL_TYPES if t.kind != "delegate" and _root(t).name not in excl]
    # pass 2a: members
    MEMBERS, TRS = {}, {}
    for ti in todo:
        if ti.kind == "enum":
            continue
        if ti.body_i is None:
            TRS[id(ti)] = TypeTr(ti.toks, ti)
            MEMBERS[id(ti)] = []
            continue
        tr = TypeTr(ti.toks, ti)
        try:
            MEMBERS[id(ti)] = tr.parse_members()
        except Exception as e:  # noqa
            tr.errors.append(f"FATAL {type(e).__name__}: {e}")
            MEMBERS[id(ti)] = []
        TRS[id(ti)] = tr
    # pass 2b: emit
    EXT, chunks, report = [], {}, {}
    for ti in todo:
        if ti.kind == "enum":
            code = emit_enum(ti) if ti.body_i is not None else [f"{ti.pyname} = cs_enum({ti.name!r}, [])"]
        else:
            tr = TRS[id(ti)]
            try:
                code = emit_class(tr, MEMBERS[id(ti)], MEMBERS, EXT)
            except Exception as e:  # noqa
                tr.errors.append(f"EMIT {type(e).__name__}: {e}")
                code = [f"class {ti.pyname}(CsBroken):", f"    _cs_name = {ti.name!r}"]
            if tr.errors:
                report[ti.pyname] = {"file": ti.file, "errors": tr.errors}
        # 语法检查
        try:
            compile("\n".join(code), ti.pyname, "exec")
        except SyntaxError as e:
            report.setdefault(ti.pyname, {"file": ti.file, "errors": []})["errors"].append(f"SYNTAX {e.msg} L{e.lineno}: {code[e.lineno - 1][:120] if e.lineno and e.lineno <= len(code) else ''}")
            code = [f"class {ti.pyname}(CsBroken):", f"    _cs_name = {ti.name!r}"]
        deps = [find_type_from(ti, b).pyname for b in ti.bases if find_type_from(ti, b) is not None
                and find_type_from(ti, b) is not ti and _root(find_type_from(ti, b)).name not in excl]
        chunks[ti.pyname] = (deps, code, ti)
    # topo
    order, state = [], {}
    def visit(n):
        if state.get(n) == 2 or n not in chunks:
            return
        if state.get(n) == 1:
            return
        state[n] = 1
        for d in chunks[n][0]:
            visit(d)
        state[n] = 2
        order.append(n)
    for n in chunks:
        if chunks[n][2].kind == "enum":
            visit(n)
    for n in chunks:
        visit(n)
    out = ["# 自动生成：tools/cs2py_files.py —— 请勿手改", "from sts2sim.rt.prelude import *  # noqa", ""]
    for n in order:
        out += chunks[n][1] + [""]
    nested = [(t.outer.pyname, t.name, t.pyname) for t in todo if t.outer is not None]
    out.append(f"_ORDER = {order!r}")
    out.append(f"_NESTED = {nested!r}")
    out.append(f"_EXT = {EXT!r}")
    out.append(f"_DUPES = {DUPES!r}")
    out.append("_finalize(globals(), _ORDER, _NESTED, _EXT)")
    _txt = "\n".join(out) + "\n"
    # struct 构造器里的 this = default; → 重置字段
    _txt = re.sub(r"(?m)^(\s*)self = ([A-Za-z_]\w*)\(\)$", r"\1getattr(\2, '_fi', lambda s: None)(self)", _txt)
    # params 参数：Python *args 是 tuple → Seq；单个数组实参按 C# 语义展开
    def _pfix(m):
        ind, line, nm = m.group(1), m.group(0), m.group(2)
        if "**" in line:
            return line
        return f"{line}\n{ind}    {nm} = _params({nm})"
    _txt = re.sub(r"(?m)^(\s*)def \w+\([^\n]*?\*(?!\*)(\w+)[^\n]*\):$", _pfix, _txt)
    # 同名不同命名空间的类型（如 Relics.PaelsLegion 与 Monsters.PaelsLegion）：按限定名/上下文选对变体
    for (dn, dfile, pfile) in DUPES:
        dns = dfile.split("/")[-2]
        dpy = dn + "_" + dns
        _txt = re.sub(r"MegaCrit\.Sts2\.Core\.Models\.(\w+)\." + dn + r"\b",
                      lambda m: dpy if m.group(1) == dns else dn, _txt)
        if dns == "Relics":
            _txt = re.sub(r"(Relic[\w.]*\([^()]*_g=\()" + dn + r"(,\))", r"\g<1>" + dpy + r"\2", _txt)
    # 委托 .Target（闭包所属对象）：Python lambda 无此概念，静态检查恒为 False
    _txt = re.sub(r"_isinst\((\w+)\.Target, AbstractModel\)", "False", _txt)
    open(out_path, "w").write(_txt)
    if report_path:
        json.dump(report, open(report_path, "w"), ensure_ascii=False, indent=1)
        with open(report_path.replace(".json", "_skipped.tsv"), "w") as f:
            for row in SKIPPED:
                f.write("\t".join(row) + "\n")
    nerr = sum(1 for v in report.values() if v["errors"])
    print(f"types={len(todo)} with_errors={nerr} dupes={len(DUPES)} ext={len(EXT)} lines={len(out)}")
    return report


def _root(ti):
    while ti.outer is not None:
        ti = ti.outer
    return ti


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("core")
    ap.add_argument("out")
    ap.add_argument("--rels", nargs="+", required=True)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--report")
    a = ap.parse_args()
    sys.setrecursionlimit(10000)
    run(a.core, a.out, a.rels, a.exclude, a.report)
