"""生成代码的 `from sts2sim.rt.prelude import *` 入口：C# 运行库 + .NET/Godot/平台桩。"""
import math
import random as _pyrandom

from .cs import *  # noqa
from .cs import _lop, _len, _val, _sm, _Event, CsRegex, _int, _div, _mod, _nz, _isinst, _as, _is_type_or_eq, _eq, _str, _setattr_ret, _setitem_ret, _outcall, _init_obj, _generic, _Anon, _bases, _dispatch, _throw, _tmatch, _EmptyColl, _cast_uint, _cast_ulong, _cast_int, _cast_ushort, _cast_short, _cast_byte, _cast_sbyte, _inv, _params  # noqa
from .cs import G, CsObject, CsException, CsEnum, cs_enum, _int  # noqa
from .linq import *  # noqa
from .linq import Seq, HashSet, Dictionary, KeyValuePair, _iter, _Linq, _CInt, _LazyEnum  # noqa


class Task:
    CompletedTask = None

    @staticmethod
    def WhenAll(*a):
        return None

    @staticmethod
    def WhenAny(*a):
        return None

    @staticmethod
    def FromResult(x, **k):
        return x

    @staticmethod
    def Delay(*a):
        return None

    @staticmethod
    def Yield():
        return None

    @staticmethod
    def Run(f, *a):
        return f()


class _TcsTask:
    """非泛型 TaskCompletionSource.Task（或尚未完成的泛型 Task）：只提供 IsCompleted / Result 查询。"""
    __slots__ = ("_src",)

    def __init__(self, src):
        self._src = src

    @property
    def IsCompleted(self):
        return self._src._done

    @property
    def Result(self):
        return self._src._result

    def WaitAsync(self, *a, **k):
        return self


class TaskCompletionSource(CsObject):
    """同步执行模型。await tcs.Task：泛型且已完成 → 结果值；否则 → _TcsTask（可查 IsCompleted）。
    未完成时由 rt/patches.py 的回合循环挂起逻辑注册 _cont 续体。"""
    def __init__(self, *a, **k):
        self._generic = bool(k.get("_g"))
        self._done = False
        self._result = None
        self._cont = None

    @property
    def Task(self):
        if self._done and self._generic:
            return self._result
        return _TcsTask(self)

    def SetResult(self, *a):
        self.TrySetResult(*a)

    def TrySetResult(self, *a):
        if self._done:
            return False
        self._done = True
        self._result = (a[0] if a else None)
        cb, self._cont = self._cont, None
        if cb is not None:
            cb(self._result)
        return True

    def TrySetCanceled(self, *a):
        return True


class CancellationToken(CsObject):
    """同步执行下取消永不发生（战斗结束由驱动器检查 IsInProgress）。"""
    IsCancellationRequested = False

    def ThrowIfCancellationRequested(self):
        pass


CancellationToken.None_ = CancellationToken()


class TaskHelper:
    """异步调用已同步执行；RunSafely 的参数在求值时就已运行完毕。"""
    @staticmethod
    def RunSafely(t, *a):
        return t

    @staticmethod
    def WhenAny(*a):
        return None


class CancellationTokenSource(CsObject):
    def __init__(self, *a):
        self.Token = CancellationToken()
        self.IsCancellationRequested = False

    def Cancel(self):
        self.IsCancellationRequested = True

    def Dispose(self):
        pass


class Time:
    """Godot Time：模拟中无真实时间，计时恒为 0（只用于日志/动画计时）。"""
    @staticmethod
    def GetTicksMsec():
        return 0

    @staticmethod
    def GetTicksUsec():
        return 0


class Math:
    PI = math.pi
    E = math.e

    Sin = staticmethod(math.sin)
    Cos = staticmethod(math.cos)
    Tan = staticmethod(math.tan)
    Atan2 = staticmethod(math.atan2)
    Exp = staticmethod(math.exp)
    Log10 = staticmethod(math.log10)
    Log2 = staticmethod(math.log2)

    @staticmethod
    def Max(a, b):
        return a if a >= b else b

    @staticmethod
    def Min(a, b):
        return a if a <= b else b

    @staticmethod
    def Abs(a):
        return abs(a)

    @staticmethod
    def Clamp(x, lo, hi):
        return lo if x < lo else (hi if x > hi else x)

    @staticmethod
    def Floor(x):
        return float(math.floor(x + 1e-9)) if isinstance(x, float) else x

    @staticmethod
    def Ceiling(x):
        return float(math.ceil(x - 1e-9)) if isinstance(x, float) else x

    @staticmethod
    def Round(x, digits=0, mode=None):
        # .NET 默认银行家舍入（MidpointRounding.ToEven）
        if isinstance(digits, CsEnum) or (mode is None and not isinstance(digits, int)):
            mode, digits = digits, 0
        f = 10 ** int(digits)
        v = x * f
        if mode is not None and str(mode).endswith("AwayFromZero"):
            r = math.floor(abs(v) + 0.5 + 1e-9) * (1 if v >= 0 else -1)
        else:
            r = round(v)
        return float(r) / f

    @staticmethod
    def Truncate(x):
        return float(_int(x))

    @staticmethod
    def Sign(x):
        return (x > 0) - (x < 0)

    @staticmethod
    def Pow(a, b):
        return float(a) ** b

    @staticmethod
    def Sqrt(a):
        return math.sqrt(a)

    @staticmethod
    def Log(a, b=None):
        return math.log(a) if b is None else math.log(a, b)

    @staticmethod
    def Exp(a):
        return math.exp(a)


MathF = Math


class MidpointRounding:
    ToEven = "ToEven"
    AwayFromZero = "AwayFromZero"
    ToZero = "ToZero"


class Convert:
    @staticmethod
    def ToInt32(x):
        if isinstance(x, float):
            return int(round(x))
        return int(x)

    @staticmethod
    def ToDecimal(x):
        return float(x)

    @staticmethod
    def ToSingle(x):
        return float(x)

    @staticmethod
    def ToDouble(x):
        return float(x)

    @staticmethod
    def ToBoolean(x):
        return bool(x)

    @staticmethod
    def ToString(x):
        return str(x)


class Array:
    @staticmethod
    def Empty(*a, _g=None):
        return Seq()

    @staticmethod
    def IndexOf(arr, x):
        return Seq(arr).IndexOf(x)

    @staticmethod
    def Copy(src, dst, n):
        dst[:n] = src[:n]

    @staticmethod
    def Fill(arr, v):
        for i in range(len(arr)):
            arr[i] = v

    @staticmethod
    def Reverse(arr):
        arr.reverse()

    @staticmethod
    def Sort(arr, *a):
        arr.sort()


class Enum:
    @staticmethod
    def GetValues(t=None, _g=None):
        t = t if t is not None else _g[0]
        seen, out = set(), Seq()
        for m in t.__members__.values():
            if int(m) not in seen:
                seen.add(int(m))
                out.append(m)
        return out

    @staticmethod
    def GetNames(t):
        return Seq(t.__members__.keys())

    @staticmethod
    def Parse(t, s, *a):
        return t[s]

    @staticmethod
    def TryParse(t, s, *a):
        try:
            return (True, t[s])
        except KeyError:
            return (False, None)

    @staticmethod
    def IsDefined(t, v):
        return any(int(m) == int(v) for m in t.__members__.values())


class Activator:
    @staticmethod
    def CreateInstance(t=None, *a, _g=None):
        return (t if t is not None else _g[0])(*a)


class _KwString:
    Empty = ""

    @staticmethod
    def Join(sep, *items):
        if len(items) == 1 and not isinstance(items[0], str):
            items = items[0]
        return str(sep).join(_str(x) for x in items)  # noqa

    @staticmethod
    def IsNullOrEmpty(s):
        return not s

    @staticmethod
    def IsNullOrWhiteSpace(s):
        return not s or not s.strip()

    @staticmethod
    def Compare(a, b, *x):
        # 注：非 Ordinal 比较在 C# 中受文化影响；游戏逻辑中的比较均为 Ordinal 或 ASCII 标识符
        if a is None or b is None:
            return 0 if a is b else (-1 if a is None else 1)
        return (a > b) - (a < b)

    @staticmethod
    def Concat(*a):
        if len(a) == 1 and not isinstance(a[0], str):
            a = a[0]
        return "".join(_str(x) for x in a)  # noqa

    @staticmethod
    def Format(f, *a):
        return f


_kw_string = _KwString


class _KwDecimal:
    MaxValue = 7.9e28
    MinValue = -7.9e28

    @staticmethod
    def Truncate(x):
        return float(_int(x))

    @staticmethod
    def Floor(x):
        return float(math.floor(x + 1e-9))

    @staticmethod
    def Ceiling(x):
        return float(math.ceil(x - 1e-9))

    @staticmethod
    def Round(x, *a):
        return Math.Round(x, *a)

    @staticmethod
    def ToInt32(x):
        return _int(x)

    @staticmethod
    def Max(a, b):
        return a if a >= b else b

    @staticmethod
    def Min(a, b):
        return a if a <= b else b

    @staticmethod
    def Abs(x):
        return abs(x)


_kw_decimal = _KwDecimal


class _KwInt:
    MaxValue = 2 ** 31 - 1
    MinValue = -2 ** 31

    @staticmethod
    def Max(a, b):
        return max(a, b)

    @staticmethod
    def Parse(s):
        return int(s)


_kw_int = _KwInt


class _KwFloat:
    MaxValue = 3.4e38
    MinValue = -3.4e38
    Epsilon = 1e-45
    PositiveInfinity = math.inf


_kw_float = _KwFloat
_kw_double = _KwFloat


class _KwObject:
    @staticmethod
    def Equals(a, b):
        return a == b

    @staticmethod
    def ReferenceEquals(a, b):
        return a is b


_kw_object = _KwObject


class _KwChar:
    @staticmethod
    def ToUpperInvariant(c):
        return c.upper()

    @staticmethod
    def IsDigit(c):
        return c.isdigit()

    @staticmethod
    def IsUpper(c):
        return c.isupper()


_kw_char = _KwChar


class _KwBool:
    @staticmethod
    def Parse(s):
        return s.lower() == "true"


_kw_bool = _KwBool


# ---------------------------------------------------------------- 通用“吸收”桩：任意属性/调用都返回自身
class Dummy:
    __slots__ = ("_name",)

    def __init__(self, name="dummy"):
        object.__setattr__(self, "_name", name)

    def __getattr__(self, n):
        return Dummy(self._name + "." + n)

    def __setattr__(self, n, v):
        pass

    def __call__(self, *a, **k):
        return Dummy(self._name + "()")

    def __bool__(self):
        return False

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __iadd__(self, o):
        return self

    def __isub__(self, o):
        return self

    def __add__(self, o):
        return o if isinstance(o, str) else self

    def __abs__(self):
        return self

    def __neg__(self):
        return self

    def __sub__(self, o):
        return self

    __rsub__ = __mul__ = __rmul__ = __truediv__ = __rtruediv__ = __sub__

    def __lt__(self, o):
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def __float__(self):
        return 0.0

    def __int__(self):
        return 0

    def __radd__(self, o):
        return o if isinstance(o, str) else self

    def __eq__(self, o):
        return o is self

    def __hash__(self):
        return id(self)

    def __repr__(self):
        return f"<Dummy {self._name}>"


class Vector2I:
    """Godot Vector2I（部分小游戏/格子逻辑会用到）。"""
    __slots__ = ("X", "Y")

    def __init__(self, x=0, y=0):
        self.X, self.Y = int(x), int(y)

    def __eq__(self, o):
        return isinstance(o, Vector2I) and o.X == self.X and o.Y == self.Y

    def __ne__(self, o):
        return not self.__eq__(o)

    def __hash__(self):
        return hash((self.X, self.Y))

    def __add__(self, o):
        return Vector2I(self.X + o.X, self.Y + o.Y)

    def __sub__(self, o):
        return Vector2I(self.X - o.X, self.Y - o.Y)

    def Equals(self, o):
        return self.__eq__(o)

    def GetHashCode(self):
        return hash((self.X, self.Y))

    def ToString(self):
        return f"({self.X}, {self.Y})"

    def __repr__(self):
        return f"Vector2I({self.X}, {self.Y})"


Vector2I.Zero = Vector2I(0, 0)
Vector2I.One = Vector2I(1, 1)
Vector2I.Up = Vector2I(0, -1)
Vector2I.Down = Vector2I(0, 1)
Vector2I.Left = Vector2I(-1, 0)
Vector2I.Right = Vector2I(1, 0)


class TestMode:
    IsOn = False
    IsOff = True

    @staticmethod
    def AssertOn():
        pass


class _Random:
    """System.Random 等价物（非逐位一致，见 README 近似说明）"""
    __slots__ = ("_r",)

    def __init__(self, seed=None):
        self._r = _pyrandom.Random(seed)

    def Next(self, a=None, b=None):
        if a is None:
            return self._r.randrange(0, 2 ** 31 - 1)
        if b is None:
            return self._r.randrange(0, int(a)) if a > 0 else 0
        return self._r.randrange(int(a), int(b)) if b > a else int(a)

    def NextDouble(self):
        return self._r.random()

    def NextSingle(self):
        return self._r.random()

    def NextInt64(self, *a):
        return self.Next(*a)


Random = _Random


_M64 = 0xFFFFFFFFFFFFFFFF


def _rotl64(x, k):
    return ((x << k) | (x >> (64 - k))) & _M64


import struct as _struct


def _f32(x):
    return _struct.unpack("f", _struct.pack("f", x))[0]


class MegaRandom:
    """MegaCrit.Sts2.Core.Random.MegaRandom（v0.111 起游戏的 PRNG：splitmix64 播种 + xoshiro256**）。
    手写、逐位一致：转译器不支持 ulong 溢出语义，故从生成代码中排除（gen_game.sh --exclude MegaRandom）。"""
    __slots__ = ("_s0", "_s1", "_s2", "_s3")

    def __init__(self, seed=0):
        if isinstance(seed, int):
            self.Reinitialise(seed)
        else:
            self.Reinitialise(seed)

    @staticmethod
    def Splitmix64(x):
        x = (x + 11400714819323198485) & _M64
        n = x
        n = ((n ^ (n >> 30)) * 13787848793156543929) & _M64
        n = ((n ^ (n >> 27)) * 10723151780598845931) & _M64
        return x, n ^ (n >> 31)

    def Reinitialise(self, seed):
        if isinstance(seed, int):
            x = int(seed) & _M64
            x, self._s0 = MegaRandom.Splitmix64(x)
            x, self._s1 = MegaRandom.Splitmix64(x)
            x, self._s2 = MegaRandom.Splitmix64(x)
            x, self._s3 = MegaRandom.Splitmix64(x)
        else:
            self._s0 = int(seed.state0) & _M64
            self._s1 = int(seed.state1) & _M64
            self._s2 = int(seed.state2) & _M64
            self._s3 = int(seed.state3) & _M64

    def _next(self):
        s0, s1, s2, s3 = self._s0, self._s1, self._s2, self._s3
        result = (_rotl64((s1 * 5) & _M64, 7) * 9) & _M64
        t = (s1 << 17) & _M64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl64(s3, 45)
        self._s0, self._s1, self._s2, self._s3 = s0, s1, s2, s3
        return result

    NextULong = _next

    def NextDouble(self):
        return float(self._next() >> 11) * 1.1102230246251565E-16

    def NextFloat(self):
        return _f32(float(self._next() >> 40) * _f32(5.9604645E-08))

    def NextInt(self):
        return self._next() >> 33

    def NextUInt(self):
        return self._next() & 0xFFFFFFFF

    def NextBool(self):
        return (self._next() & 0x8000000000000000) != 0

    def Next(self, a, b=None):
        if b is None:
            if a < 1:
                raise ValueError("maxValue must be > 0")
            return int(self.NextDouble() * float(a))
        if a >= b:
            raise ValueError("maxValue must be > minValue")
        return int(self.NextDouble() * float(int(b) - int(a))) + int(a)

    def FillSerializableState(self, rng):
        rng.state0, rng.state1, rng.state2, rng.state3 = self._s0, self._s1, self._s2, self._s3


class Mathf:
    """Godot Mathf（float 运算；Round/RoundToInt 与 Godot C# 一致：Math.Round 银行家舍入）。"""
    Pi = math.pi
    Tau = math.tau
    Atan2 = staticmethod(math.atan2)
    Sin = staticmethod(math.sin)
    Cos = staticmethod(math.cos)
    Sqrt = staticmethod(math.sqrt)

    @staticmethod
    def Log(x, b=None):
        # Godot Mathf.Log 是自然对数（v0.111 Infested/Enlarge 招式用来算缩放，只影响视觉）
        return math.log(x) if b is None else math.log(x, b)

    @staticmethod
    def Pow(a, b):
        return float(a) ** float(b)

    @staticmethod
    def Max(a, b):
        return a if a >= b else b

    @staticmethod
    def Min(a, b):
        return a if a <= b else b

    @staticmethod
    def Clamp(x, lo, hi):
        return lo if x < lo else (hi if x > hi else x)

    @staticmethod
    def Abs(x):
        return abs(x)

    @staticmethod
    def FloorToInt(x):
        return int(math.floor(x))

    @staticmethod
    def CeilToInt(x):
        return int(math.ceil(x))

    @staticmethod
    def Round(x):
        return float(round(x))

    @staticmethod
    def RoundToInt(x):
        return int(round(x))

    @staticmethod
    def Lerp(a, b, t):
        return a + (b - a) * t


class CollectionsMarshal:
    @staticmethod
    def SetCount(lst, n):
        n = int(n)
        if len(lst) < n:
            lst.extend([None] * (n - len(lst)))
        else:
            del lst[n:]

    @staticmethod
    def AsSpan(lst):
        return lst


class AppendInterpolatedStringHandler(CsObject):
    """StringBuilder 的内插处理器：直接写入目标 StringBuilder。"""
    def __init__(self, lit=0, n=0, sb=None, *a):
        self._sb = sb

    def AppendLiteral(self, s):
        self._sb.Append(s)

    def AppendFormatted(self, x, *a):
        self._sb.Append(_str(x, *([":" + a[-1]] if a and isinstance(a[-1], str) else [])))


class StringBuilder(CsObject):
    def __init__(self, *a):
        self.parts = [str(a[0])] if a and isinstance(a[0], str) else []

    def Append(self, x, *a):
        if isinstance(x, AppendInterpolatedStringHandler):
            return self   # 内容已由处理器写入
        if a and isinstance(x, str) and len(a) == 1 and isinstance(a[0], int):
            x = x * a[0]   # Append(char, repeatCount)
        self.parts.append(_str(x))  # noqa
        return self

    def AppendLine(self, x=""):
        self.parts.append(_str(x) + "\n")  # noqa
        return self

    def ToString(self):
        return "".join(self.parts)

    @property
    def Length(self):
        return sum(len(p) for p in self.parts)


class EqualityComparer:
    Default = Dummy("EqualityComparer.Default")


class Comparer:
    Default = None

    @staticmethod
    def Create(f):
        class _C:
            Compare = staticmethod(f)
        return _C()


class StringComparer:
    Ordinal = None
    OrdinalIgnoreCase = None


class StringComparison:
    Ordinal = 4
    OrdinalIgnoreCase = 5
    InvariantCulture = 2


class BindingFlags:
    Instance = 4
    Public = 16
    NonPublic = 32
    Static = 8
    DeclaredOnly = 2


class Type(CsObject):
    pass


class Lazy(CsObject):
    def __init__(self, f, *a):
        self._f = f
        self._v = None
        self._done = False

    @property
    def Value(self):
        if not self._done:
            self._v = self._f()
            self._done = True
        return self._v


class Interlocked:
    @staticmethod
    def Increment(x):
        return x + 1


# 平台/存档/成就/遥测：全部吸收
for _n in ("SaveUtil", "AchievementsUtil", "PlatformUtil", "SentryService", "JsonMetadataServices",
           "JsonEncodedText", "JsonSerializer", "Unsafe", "RuntimeHelpers", "IdAnonymizer", "ResourceLoader",
           "ReleaseInfoManager", "AchievementsHelper", "PlayerHurtVignetteHelper", "DirAccess", "OS",
           "LogType", "Log", "Logger", "MegaCrit", "System", "StatsManager", "TestRngInjector", "DateTimeOffset", "DateTime",
           "TimeSpan", "Regex", "Engine", "NGame", "CreatureAnimator", "SaveManager", "LocManager", "AtlasManager",
           "ModManager", "Achievement", "NetLoadingHandle", "PeerInputSynchronizer", "VfxDuration", "FastModeType",
           "Vector2", "Node", "StringName", "Texture2D", "LocString", "SavedProperties",
           "AchievementMetric", "EpochMetric", "MegaInput", "Assembly", "Encoding", "HttpClient", "CompareOptions",
           "JsonPropertyInfoValues", "JsonParameterInfoValues", "JsonObjectInfoValues", "JsonCollectionInfoValues",
           "JsonStringEnumConverter", "JsonSerializerOptions", "JsonConverterFactory",
           "EChatRoomEnterResponse", "NeowEpoch", "SerializableCard", "SerializableReward", "SerializableRelic",
           "SerializablePotion", "SerializableDynamicVar", "SerializableRunRngSet", "SerializablePlayerRngSet",
           "SerializableRelicGrabBag", "SerializableUnlockState", "SerializableExtraPlayerFields",
           "SerializablePlayerOddsSet", "SerializableRunOddsSet", "SerializableRoom", "SerializableRoomSet",
           "SerializableExtraRunFields", "SerializableActMap", "UnlockStateSave", "ActiveScreenContext",
           "IHoverTip", "HoverTipFactory", "CrystalSphereMinigame", "NFakeMerchant", "UpgradeDisplay"):
    globals()[_n] = Dummy(_n)


FINALIZE_ERRORS = []


def _finalize(g, order, nested, ext):
    G.update(g)
    for (outer, name, py) in nested:
        try:
            setattr(g[outer], name, g[py])
        except Exception as e:  # noqa
            FINALIZE_ERRORS.append(("nested", outer, name, repr(e)))
    seq_targets = {"IEnumerable", "IReadOnlyList", "List", "IList", "ICollection", "IReadOnlyCollection", "T",
                   "HashSet", "ISet", "Array", "Span", "IReadOnlySet"}
    for (tt, name, py, fname) in ext:
        fn = g[py].__dict__.get(fname)
        fn = fn.__func__ if isinstance(fn, staticmethod) else fn
        if fn is None:
            continue
        targets = []
        if tt in seq_targets or tt.endswith("[]"):
            targets = [_Linq]
        elif isinstance(g.get(tt), type):
            targets = [g[tt]]
        for t in targets:
            if name not in t.__dict__ and not hasattr(t, name):
                try:
                    setattr(t, name, fn)
                except Exception as e:  # noqa
                    FINALIZE_ERRORS.append(("ext", tt, name, repr(e)))
    for n in order:
        cls = g.get(n)
        d = getattr(cls, "__dict__", {})
        if isinstance(cls, type) and d.get("_cs_record") and "Equals" not in d:
            def _rec_eq(self, o):
                return self is o or (type(o) is type(self) and self.__dict__ == o.__dict__)
            def _rec_hash(self):
                try:
                    return hash(tuple(self.__dict__.items()))
                except TypeError:
                    return id(self)
            cls.__eq__ = _rec_eq
            cls.__hash__ = _rec_hash
            cls.__ne__ = lambda self, o: not _rec_eq(self, o)
        elif isinstance(cls, type) and ("Equals" in d or "Equals__object" in d):
            def _mk(cls):
                def __eq__(self, o):
                    if self is o:
                        return True
                    if o is None:
                        return False
                    r = self.Equals(o)
                    return bool(r)
                def __hash__(self):
                    if "GetHashCode" in type(self).__dict__ or hasattr(type(self), "GetHashCode") and type(self).GetHashCode is not CsObject.GetHashCode:
                        return hash(self.GetHashCode())
                    return id(self)
                cls.__eq__ = __eq__
                cls.__hash__ = __hash__
                cls.__ne__ = lambda self, o: not __eq__(self, o)
            _mk(cls)
    for n in order:
        cls = g.get(n)
        si = getattr(cls, "__dict__", {}).get("_static_init")
        if si is not None:
            try:
                si.__func__()
            except Exception as e:  # noqa
                FINALIZE_ERRORS.append(("static", n, repr(e)[:200]))


__all__ = [n for n in list(globals()) if not n.startswith("__")]


class Lock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def Enter(self):
        pass

    def Exit(self):
        pass

    def EnterScope(self):
        return self

    def Dispose(self):
        pass


__all__ = [n for n in list(globals()) if not n.startswith("__")]


class ModelIdSerializationCache:
    """网络序列化 id：这里用名字排序前的出现顺序给稳定整数（仅用于排序/确定性）"""
    _cat = {}
    _ent = {}

    @staticmethod
    def GetNetIdForCategory(c):
        return ModelIdSerializationCache._cat.setdefault(c, len(ModelIdSerializationCache._cat))

    @staticmethod
    def GetNetIdForEntry(e):
        return ModelIdSerializationCache._ent.setdefault(e, len(ModelIdSerializationCache._ent))


__all__ = [n for n in list(globals()) if not n.startswith("__")]


class HashCode:
    @staticmethod
    def Combine(*a):
        return hash(tuple(a))


__all__ = [n for n in list(globals()) if not n.startswith("__")]
