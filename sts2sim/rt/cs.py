"""C# 语义运行库：对象模型、枚举、重载分派、空值/类型辅助。"""
import enum
import math

G = {}   # 生成代码的全局命名空间（_finalize 时填入）


class CsMeta(type):
    @property
    def Name(cls):
        return getattr(cls, "_cs_name", cls.__name__)

    @property
    def FullName(cls):
        return cls.Name

    def IsSubclassOf(cls, other):
        return cls is not other and isinstance(other, type) and issubclass(cls, other)

    def IsAssignableFrom(cls, other):
        return isinstance(other, type) and issubclass(other, cls)

    def IsInstanceOfType(cls, obj):
        return isinstance(obj, cls)

    @property
    def BaseType(cls):
        for b in cls.__bases__:
            if b is not CsObject and isinstance(b, CsMeta):
                return b
        return None

    @property
    def IsAbstract(cls):
        return bool(getattr(cls, "_cs_abstract", False))

    def ToString(cls):
        return cls.Name

    def __repr__(cls):
        return f"<{cls.Name}>"


class CsObject(metaclass=CsMeta):
    def __init__(self, *a, **k):
        pass

    def GetType(self):
        return type(self)

    def ToString(self):
        return type(self).Name

    def Equals(self, other):
        return self == other

    def GetHashCode(self):
        return id(self)

    def __str__(self):
        try:
            return self.ToString()
        except Exception:  # noqa
            return object.__repr__(self)

    def __repr__(self):
        return f"<{type(self).Name} {self.__str__()}>" if type(self).ToString is not CsObject.ToString else object.__repr__(self)

    def MemberwiseClone(self):
        c = object.__new__(type(self))
        c.__dict__.update(self.__dict__)
        return c


class CsBroken(CsObject):
    """转译失败的类型"""
    def __init__(self, *a, **k):
        raise CsBrokenMember(f"类型 {type(self).Name} 转译失败")


class CsException(Exception):
    def __init__(self, *a, **k):
        super().__init__(*a)
        self.Message = a[0] if a else ""


class CsBrokenMember(CsException):
    pass


class CsNotImplemented(CsException):
    pass


for _n in ("InvalidOperationException", "ArgumentException", "ArgumentOutOfRangeException", "NotImplementedException",
           "NotSupportedException", "KeyNotFoundException", "IndexOutOfRangeException", "NullReferenceException",
           "InvalidCastException", "OperationCanceledException", "TaskCanceledException", "FormatException",
           "OverflowException", "DivideByZeroException", "ApplicationException", "SoftlockException",
           "SystemException", "TimeoutException", "InvalidDataException", "UnreachableException"):
    globals()[_n] = type(_n, (CsException,), {})


def _throw_if_null_or_empty(x, *a):
    if x is None or x == "":
        raise ArgumentException("null or empty")


ArgumentException.ThrowIfNullOrEmpty = staticmethod(_throw_if_null_or_empty)   # noqa: F821  (.NET 7+)


class ArgumentNullException(CsException):
    @staticmethod
    def ThrowIfNull(x, *a):
        if x is None:
            raise ArgumentNullException("null")


def _throw(*a):
    raise CsException(*a)


class cs_property:
    """C# 属性；无 setter 时赋值静默存入实例（基类构造器给被子类 getter 覆盖的属性赋值时）"""
    __slots__ = ("fget", "fset", "name")

    def __init__(self, fget, fset=None):
        self.fget = fget
        self.fset = fset
        self.name = fget.__name__[5:] if fget.__name__.startswith("_get_") else fget.__name__

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.fget(obj)

    def __set__(self, obj, value):
        if self.fset is not None:
            self.fset(obj, value)
        else:
            obj.__dict__["_ap_" + self.name] = value


class cs_sprop:
    """静态属性（类上访问即求值）"""
    __slots__ = ("fget",)

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, obj, objtype=None):
        return self.fget()


class cs_broken:
    def __init__(self, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        raise CsBrokenMember(f"成员 {self.name} 转译失败")


class CsEnum(enum.IntFlag, boundary=enum.KEEP):
    def __getattr__(self, n):
        # 视觉/本地化扩展方法（ToLocString、GetLocKey…）在模拟器中不存在
        if any(w in n for w in ("Loc", "Title", "Description", "Dialogue", "Sfx", "Vfx", "Icon", "Color", "Path", "Text")):
            from .prelude import Dummy
            return lambda *a, **k: Dummy("loc")
        raise AttributeError(n)

    def HasFlag(self, f):
        return (int(self) & int(f)) == int(f)

    def ToString(self, *a):
        return self.name if self.name is not None else str(int(self))

    def __str__(self):
        return self.ToString()

    def CompareTo(self, o):
        return (int(self) > int(o)) - (int(self) < int(o))

    def __hash__(self):
        return int.__hash__(self)


def cs_enum(name, vals):
    if not vals:
        vals = [("_Empty", 0)]
    e = CsEnum(name, vals)
    e._cs_name = name
    return e


def _bases(*bs):
    bs = [b for b in bs if b is not None]
    out = []
    for b in bs:
        if any(o is not b and issubclass(o, b) for o in bs):
            continue
        if b in out:
            continue
        out.append(b)
    if not out:
        out = [CsObject]
    # MRO 尝试
    try:
        type("_probe", tuple(out), {})
    except TypeError:
        out = [out[0]]
    return tuple(out)


# ---------------------------------------------------------------- 重载分派
_NUM = {"int", "decimal", "float", "double", "long", "uint", "short", "byte", "ulong", "sbyte", "ushort", "Int32",
        "Decimal", "Single", "Double", "Int64"}
_SEQ = {"IEnumerable", "IReadOnlyList", "List", "IList", "ICollection", "IReadOnlyCollection", "HashSet", "ISet",
        "IReadOnlySet", "Seq", "Array", "Span", "ReadOnlySpan", "Queue", "Stack"}
_FUNC = {"Func", "Action", "Predicate", "Comparison", "Delegate"}


def _tmatch(v, t):
    if t in ("out", "object", "T", "var", "dynamic") or t is None:
        return 2 if t != "object" else 1
    if v is None:
        return 0 if (t in _NUM or t == "bool") else 1
    if type(v).__name__ == "Dummy":
        return 1
    if t in _NUM:
        return 2 if (isinstance(v, (int, float)) and not isinstance(v, (bool, enum.Enum))) else 0
    if t == "bool":
        return 2 if isinstance(v, bool) else 0
    if t in ("string", "str", "String"):
        return 2 if isinstance(v, str) else 0
    if t in _FUNC:
        return 2 if (callable(v) and not isinstance(v, type) and not isinstance(v, CsObject)) else 0
    if t.endswith(">") and "<" in t:
        bt, el = t[:-1].split("<", 1)
        if not (isinstance(v, (list, tuple, set, frozenset)) or hasattr(v, "__iter__")) or isinstance(v, str):
            return 0
        ecls = G.get(el)
        if isinstance(ecls, type) and not hasattr(v, "__next__"):
            try:
                first = next(iter(v), None)
            except TypeError:
                first = None
            if first is not None:
                return 3 if isinstance(first, ecls) else 0
        return 2
    if t.endswith("[]") or t in _SEQ:
        return 2 if isinstance(v, (list, tuple, set, frozenset)) or hasattr(v, "__next__") else 0
    if t == "Type":
        return 2 if isinstance(v, type) else 0
    cls = G.get(t)
    if isinstance(cls, type):
        if isinstance(v, cls):
            return 3
        if issubclass(cls, enum.Enum):
            return 0
        if isinstance(v, (int, float, str, bool)):
            return 0
        return 0
    return 1   # 未知类型（泛型参数/外部类型）


def _dispatch(cls, self, name, a, k):
    if self is not None and name != "__init__" and not isinstance(self, cls):
        # 实例/静态同名重载：Cls.M(x, y) 调到实例包装器时 self 其实是第一个实参（v0.111 CombatManager.AfterCreatureAdded）
        a = (self,) + tuple(a)
        self = None
    rows = cls.__dict__.get("_ovl_" + name)
    if rows is None:
        for c in cls.__mro__:
            rows = c.__dict__.get("_ovl_" + name)
            if rows is not None:
                break
    n = len(a) + len(k) - (1 if "_g" in k else 0)
    best, best_score = None, -1
    kn = [x for x in k if x != "_g"]
    for row in rows:
        vname, pts, ngp, nreq, varargs = row[:5]
        pnames = row[5] if len(row) > 5 else None
        total = ngp + len(pts)
        if n < ngp + nreq or (n > total and not varargs):
            continue
        score = 0
        ok = True
        for i, v in enumerate(a[ngp:]):
            if i >= len(pts):
                break
            m = _tmatch(v, pts[i])
            if m == 0:
                ok = False
                break
            score += m
        if ok and kn and pnames is not None:
            for kk in kn:
                if kk not in pnames:
                    ok = False
                    break
                j = pnames.index(kk)
                if j < len(a) - ngp:
                    ok = False
                    break
                m = _tmatch(k[kk], pts[j])
                if m == 0:
                    ok = False
                    break
                score += m
            if ok:
                # 未提供的必选参数
                given = set(range(len(a) - ngp)) | {pnames.index(kk) for kk in kn}
                for j in range(nreq):
                    if j not in given:
                        ok = False
                        break
        if ok and score > best_score:
            best, best_score = vname, score
    if best is None:
        raise CsException(f"没有匹配的重载 {cls.Name}.{name} args={[type(x).__name__ for x in a]}")
    if name == "__init__":
        return cls.__dict__[best](self, *a, **k)
    if self is None:
        return getattr(cls, best)(*a, **k)
    return getattr(self, best)(*a, **k)


# ---------------------------------------------------------------- 数值/空值/类型
def _int(x):
    if isinstance(x, int):
        return int(x)
    if x is None:
        return None
    if isinstance(x, str):
        return ord(x[0]) if len(x) == 1 else int(x)
    if x >= 0:
        return int(x + 1e-9)
    return -int(-x + 1e-9)


def _div(a, b):
    if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool):
        if b == 0:
            raise DivideByZeroException()  # noqa
        q = abs(a) // abs(b)
        return q if (a >= 0) == (b >= 0) else -q
    if b == 0:
        if isinstance(a, float) or isinstance(b, float):
            # IEEE：浮点除零得 ±Infinity / NaN（C# float/double 语义）
            return float("nan") if a == 0 else (float("inf") if a > 0 else float("-inf"))
        raise DivideByZeroException()  # noqa  decimal 除零
    return a / b


def _mod(a, b):
    if isinstance(a, int) and isinstance(b, int):
        return int(math.fmod(a, b))
    return math.fmod(a, b)


def _nz(a, fb):
    return a if a is not None else fb()


def _isinst(x, t):
    if t is None:
        return False
    if isinstance(t, type):
        return isinstance(x, t)
    if isinstance(t, tuple):
        return isinstance(x, t)
    return x == t


def _as(x, t):
    try:
        return x if isinstance(x, t) else None
    except TypeError:
        return x


def _is_type_or_eq(x, t):
    if isinstance(t, type) and not isinstance(t, enum.EnumMeta):
        return isinstance(x, t)
    return x == t


def _eq(a, b):
    return a == b


def _str(x, *fmt):
    if x is None:
        return ""
    if fmt and fmt[0]:
        f = fmt[0]
        try:
            if f.startswith(":"):
                spec = f[1:]
                c = spec[:1].upper()
                digits = int(spec[1:]) if spec[1:].isdigit() else None
                if c == "F" and isinstance(x, (int, float)):
                    return f"{float(x):.{2 if digits is None else digits}f}"
                if c == "N" and isinstance(x, (int, float)):
                    return f"{float(x):,.{2 if digits is None else digits}f}"
                if c == "D" and isinstance(x, int):
                    return str(x).zfill(digits or 0)
                if c == "P" and isinstance(x, (int, float)):
                    return f"{float(x) * 100:.{2 if digits is None else digits}f} %"
                if spec.startswith("0") and isinstance(x, (int, float)):
                    return f"{float(x):.{spec.count('0', spec.find('.')) if '.' in spec else 0}f}"
            elif f.startswith(","):
                w = int(f[1:].split(":")[0])
                r = _str(x)
                return r.rjust(w) if w > 0 else r.ljust(-w)
        except Exception:  # noqa
            pass
    if isinstance(x, bool):
        return "True" if x else "False"
    if isinstance(x, float) and x == int(x):
        return str(int(x))
    if hasattr(x, "ToString") and not isinstance(x, (int, float, str)):
        try:
            r = x.ToString()
            if isinstance(r, str):
                return r
        except TypeError:
            pass
    return str(x)


def _setattr_ret(obj, name, v):
    setattr(obj, name, v)
    return v


def _setitem_ret(obj, idx, v):
    obj[idx] = v
    return v


class _OutSentinel:
    def __repr__(self):
        return "OUT"


OUT = _OutSentinel()


def _outcall(r):
    # 带 out 参数的调用约定返回 (返回值, out1, out2, ...)；运行时里未实现 out 的方法只返回值
    if isinstance(r, tuple) and not isinstance(r, CsTuple):
        return r
    return (r, None, None, None, None)


def _init_obj(obj, **kw):
    for k, v in kw.items():
        setattr(obj, k, v)
    return obj


def _generic(f, *targs):
    return lambda *a, **k: f(*a, _g=targs, **k)


class _Anon:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __eq__(self, o):
        return isinstance(o, _Anon) and o.__dict__ == self.__dict__

    def __hash__(self):
        return hash(tuple(sorted(self.__dict__.items(), key=lambda kv: kv[0])))


class CsTuple(tuple):
    def __new__(cls, items, names=()):
        t = super().__new__(cls, items)
        t._names = names
        return t

    def CompareTo(self, other):
        for a, b in zip(self, other):
            if hasattr(a, "CompareTo") and not isinstance(a, (int, float, str)):
                c = a.CompareTo(b)
            else:
                c = (a > b) - (a < b)
            if c:
                return c
        return 0

    def __getattr__(self, n):
        if n.startswith("Item") and n[4:].isdigit():
            return self[int(n[4:]) - 1]
        names = tuple.__getattribute__(self, "_names")
        if n in names:
            return self[names.index(n)]
        raise AttributeError(n)


class Array2D:
    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.d = [None] * (self.w * self.h)

    def __getitem__(self, ij):
        i, j = ij
        return self.d[i * self.h + j]

    def __setitem__(self, ij, v):
        i, j = ij
        self.d[i * self.h + j] = v

    def GetLength(self, dim):
        return self.w if dim == 0 else self.h

    def __iter__(self):
        return iter(self.d)


# ---------------------------------------------------------------- 字符串/可空值成员
def _len(x):
    if isinstance(x, (str, list, tuple)):
        return len(x)
    return x.Length


_PRIM = (int, float, bool, str)


def _val(x):
    """Nullable<T>.Value：值本身；对有 Value 成员的对象（KeyValuePair 等）取成员。"""
    if isinstance(x, _PRIM) or isinstance(x, enum.Enum):
        return x
    try:
        return x.Value
    except AttributeError:
        if x is None:
            raise
        return x


def _cs_split(s, *a):
    seps = []
    for x in a:
        if isinstance(x, str):
            seps.append(x)
        elif isinstance(x, (list, tuple)):
            seps += [y for y in x if isinstance(y, str)]
    if not seps:
        return s.split()
    import re as _re
    parts = _re.split("|".join(_re.escape(x) for x in seps), s)
    remove_empty = any(isinstance(x, int) and not isinstance(x, bool) and int(x) & 1 for x in a if not isinstance(x, str))
    return [p for p in parts if p] if remove_empty else parts


_STR_IMPL = {
    "StartsWith": lambda s, x, *a: s.startswith(x),
    "EndsWith": lambda s, x, *a: s.endswith(x),
    "ToLowerInvariant": lambda s: s.lower(),
    "ToUpperInvariant": lambda s: s.upper(),
    "ToLower": lambda s, *a: s.lower(),
    "ToUpper": lambda s, *a: s.upper(),
    "Trim": lambda s, *a: s.strip(*[c for c in a if isinstance(c, str)]) if a else s.strip(),
    "TrimStart": lambda s, *a: s.lstrip(*a),
    "TrimEnd": lambda s, *a: s.rstrip(*a),
    "Split": _cs_split,
    "Substring": lambda s, i, n=None: s[int(i):] if n is None else s[int(i):int(i) + int(n)],
    "Replace": lambda s, a, b: s.replace(a, b if b is not None else ""),
    "PadLeft": lambda s, n, c=" ": s.rjust(int(n), c),
    "PadRight": lambda s, n, c=" ": s.ljust(int(n), c),
    "Contains": lambda s, x, *a: x in s,
    "IndexOf": lambda s, x, *a: s.find(x),
    "LastIndexOf": lambda s, x, *a: s.rfind(x),
    "CompareTo": lambda s, o: (s > o) - (s < o),
    "Equals": lambda s, o, *a: s == o,
    "GetHashCode": lambda s: hash(s),
}
_NUM_IMPL = {
    "CompareTo": lambda s, o: (s > o) - (s < o),
    "Equals": lambda s, o: s == o,
    "GetHashCode": lambda s: hash(s),
    "GetValueOrDefault": lambda s, d=None: s,
}


def _sm(obj, name):
    if isinstance(obj, str):
        f = _STR_IMPL[name]
        return lambda *a: f(obj, *a)
    if isinstance(obj, (int, float)):
        f = _NUM_IMPL.get(name)
        if f is not None:
            return lambda *a: f(obj, *a)
    if obj is None and name == "GetValueOrDefault":
        return lambda d=0: d
    return getattr(obj, name)


class _Event:
    """C# event：+= / -= / Invoke"""
    __slots__ = ("hs",)

    def __init__(self):
        self.hs = []

    def __iadd__(self, h):
        self.hs.append(h)
        return self

    def __isub__(self, h):
        if h in self.hs:
            self.hs.remove(h)
        return self

    def Invoke(self, *a):
        for h in list(self.hs):
            h(*a)

    def __call__(self, *a):
        self.Invoke(*a)

    def __bool__(self):
        return bool(self.hs)


class CsRegex:
    def __init__(self, pat, *a):
        import re as _re
        try:
            pat = pat.encode("latin-1", "backslashreplace").decode("unicode_escape")
        except Exception:  # noqa
            pass
        self.special = None
        if "\\G(?!^)" in pat:
            pat = pat.replace("([A-Za-z0-9]|\\G(?!^))", "(?<=[A-Za-z0-9])()")
        self.rx = _re.compile(pat)

    def Replace(self, s, rep, *a):
        if callable(rep):
            return self.rx.sub(lambda m: rep(m), s)
        import re as _re
        r = _re.sub(r"\$(\d+)", r"\\\1", rep)
        return self.rx.sub(r, s)

    def IsMatch(self, s):
        return self.rx.search(s) is not None

    def Match(self, s):
        return self.rx.search(s)


import operator as _operator
_LOPS = {"+": _operator.add, "-": _operator.sub, "*": _operator.mul, "<": _operator.lt, ">": _operator.gt,
         "<=": _operator.le, ">=": _operator.ge}


def _lop(op, a, b):
    """C# 可空提升运算：任一侧 null → 算术得 null，比较得 false"""
    if a is None or b is None:
        return False if op in ("<", ">", "<=", ">=") else None
    return _LOPS[op](a, b)


class _EmptyColl:
    """被跳过的视觉集合成员：读取总是得到新的空列表，写入被忽略。"""
    def __get__(self, obj, owner=None):
        from .linq import Seq
        return Seq()

    def __set__(self, obj, v):
        pass



# ---- 显式整数转换（C# unchecked 语义：截断后按位宽回绕）----
def _wrap(x, bits, signed):
    v = _int(x)
    if v is None:
        return None
    m = (1 << bits) - 1
    v &= m
    if signed and v >= (1 << (bits - 1)):
        v -= (1 << bits)
    return v


def _cast_uint(x):
    return _wrap(x, 32, False)


def _cast_ulong(x):
    return _wrap(x, 64, False)


def _cast_int(x):
    return _wrap(x, 32, True)


def _cast_ushort(x):
    return _wrap(x, 16, False)


def _cast_short(x):
    return _wrap(x, 16, True)


def _cast_byte(x):
    return _wrap(x, 8, False)


def _cast_sbyte(x):
    return _wrap(x, 8, True)


def _inv(f):
    """委托调用：C# event 对象取其 Invoke，普通 Python 函数原样返回。"""
    return getattr(f, "Invoke", f)


def _params(t):
    """C# params T[]：单个数组/列表实参直接作为数组，否则把可变参数打包成数组。"""
    from .linq import Seq
    if len(t) == 1 and isinstance(t[0], list):
        return t[0]
    return Seq(t)
