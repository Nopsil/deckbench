"""C# 集合 + LINQ（立即求值）"""
import functools
from .cs import CsException, CsObject, InvalidOperationException  # noqa


class _CInt(int):
    """List.Count（属性）与 IEnumerable.Count(pred)（方法）共存"""

    def __new__(cls, n, src):
        o = int.__new__(cls, n)
        o._src = src
        return o

    def __call__(self, pred=None):
        if pred is None:
            return int(self)
        return sum(1 for x in self._src if pred(x))


def _key_cmp(a, b):
    try:
        return (a > b) - (a < b)
    except TypeError:
        return 0


class _Linq:
    """LINQ 方法 mixin，需要 __iter__"""

    def Where(self, f):
        return Seq(x for x in self if f(x))

    def Select(self, f):
        try:
            return Seq(f(x) for x in self)
        except TypeError as e:
            if "positional argument" not in str(e):
                raise
            return Seq(f(x, i) for i, x in enumerate(self))

    def SelectMany(self, f):
        out = Seq()
        for x in self:
            r = f(x)
            if r is not None:
                out.extend(r)
        return out

    def GetEnumerator(self):
        return CsEnumerator(self)

    def Any(self, f=None):
        if f is None:
            for _ in self:
                return True
            return False
        return any(f(x) for x in self)

    def All(self, f):
        return all(f(x) for x in self)

    def First(self, f=None):
        for x in self:
            if f is None or f(x):
                return x
        raise InvalidOperationException("Sequence contains no matching element")

    def FirstOrDefault(self, f=None, default=None):
        if f is not None and not callable(f):
            default, f = f, None
        for x in self:
            if f is None or f(x):
                return x
        return default

    def Last(self, f=None):
        r = [x for x in self if f is None or f(x)]
        if not r:
            raise InvalidOperationException("Sequence contains no elements")
        return r[-1]

    def LastOrDefault(self, f=None, default=None):
        if f is not None and not callable(f):
            default, f = f, None
        r = [x for x in self if f is None or f(x)]
        return r[-1] if r else default

    def Single(self, f=None):
        r = [x for x in self if f is None or f(x)]
        if len(r) != 1:
            raise InvalidOperationException("Sequence does not contain exactly one element")
        return r[0]

    def SingleOrDefault(self, f=None, default=None):
        if f is not None and not callable(f):
            default, f = f, None
        r = [x for x in self if f is None or f(x)]
        if len(r) > 1:
            raise InvalidOperationException("more than one")
        return r[0] if r else default

    def OrderBy(self, f, comparer=None):
        return _Ordered(list(self), [(f, False)])

    def OrderByDescending(self, f, comparer=None):
        return _Ordered(list(self), [(f, True)])

    def ToList(self):
        return Seq(self)

    def ToArray(self):
        return Seq(self)

    def AsEnumerable(self):
        return self

    def ToHashSet(self, *a):
        return HashSet(self)

    def ToDictionary(self, kf=None, vf=None):
        d = Dictionary()
        for x in self:
            if kf is None:      # .NET 8+ 重载：IEnumerable<KeyValuePair/(K,V)>.ToDictionary()（v0.111 用到）
                k, v = (x.Key, x.Value) if hasattr(x, "Key") else (x[0], x[1])
            else:
                k, v = kf(x), (vf(x) if vf else x)
            if k in d:
                raise CsException("duplicate key")
            d[k] = v
        return d

    def Sum(self, f=None):
        return sum((f(x) for x in self) if f else self)

    def Max(self, f=None):
        vals = [f(x) for x in self] if f else list(self)
        if not vals:
            raise InvalidOperationException("Sequence contains no elements")
        return max(vals)

    def Min(self, f=None):
        vals = [f(x) for x in self] if f else list(self)
        if not vals:
            raise InvalidOperationException("Sequence contains no elements")
        return min(vals)

    def Average(self, f=None):
        vals = [f(x) for x in self] if f else list(self)
        return sum(vals) / len(vals)

    def MaxBy(self, f):
        best = None
        bk = None
        for x in self:
            k = f(x)
            if best is None or k > bk:
                best, bk = x, k
        return best

    def MinBy(self, f):
        best = None
        bk = None
        for x in self:
            k = f(x)
            if best is None or k < bk:
                best, bk = x, k
        return best

    def Distinct(self, *a):
        seen, out = [], Seq()
        hs = set()
        for x in self:
            try:
                if x in hs:
                    continue
                hs.add(x)
            except TypeError:
                if x in seen:
                    continue
                seen.append(x)
            out.append(x)
        return out

    def DistinctBy(self, f):
        hs, out = set(), Seq()
        for x in self:
            k = f(x)
            if k in hs:
                continue
            hs.add(k)
            out.append(x)
        return out

    def Concat(self, other):
        out = Seq(self)
        if other is not None:
            out.extend(other)
        return out

    def Append(self, x):
        out = Seq(self)
        out.append(x)
        return out

    def Prepend(self, x):
        return Seq([x] + list(self))

    def Except(self, other):
        o = list(other)
        return Seq(x for x in self if x not in o).Distinct()

    def Intersect(self, other):
        o = list(other)
        return Seq(x for x in self if x in o).Distinct()

    def Union(self, other):
        return self.Concat(other).Distinct()

    def Contains(self, x, *a):
        for y in self:
            if y == x:
                return True
        return False

    def Take(self, n):
        return Seq(list(self)[:max(0, int(n))])

    def Skip(self, n):
        return Seq(list(self)[max(0, int(n)):])

    def TakeLast(self, n):
        l = list(self)
        return Seq(l[len(l) - int(n):] if n > 0 else [])

    def SkipLast(self, n):
        l = list(self)
        return Seq(l[:len(l) - int(n)] if n > 0 else l)

    def TakeWhile(self, f):
        out = Seq()
        for x in self:
            if not f(x):
                break
            out.append(x)
        return out

    def SkipWhile(self, f):
        out, skipping = Seq(), True
        for x in self:
            if skipping and f(x):
                continue
            skipping = False
            out.append(x)
        return out

    def GroupBy(self, kf, vf=None):
        groups = {}
        order = []
        for x in self:
            k = kf(x)
            if k not in groups:
                groups[k] = _Grouping(k)
                order.append(k)
            groups[k].append(vf(x) if vf else x)
        return Seq(groups[k] for k in order)

    def Aggregate(self, seed, f=None, rf=None):
        if f is None:
            it = iter(self)
            acc = next(it)
            for x in it:
                acc = seed(acc, x)
            return acc
        acc = seed
        for x in self:
            acc = f(acc, x)
        return rf(acc) if rf else acc

    def Zip(self, other, f=None):
        from .cs import CsTuple
        return Seq((f(a, b) if f else CsTuple((a, b), ("First", "Second"))) for a, b in zip(self, other))


    def Cast(self, t=None):
        return Seq(self)

    def ElementAt(self, i):
        return list(self)[int(i)]

    def ElementAtOrDefault(self, i):
        l = list(self)
        return l[int(i)] if 0 <= i < len(l) else None

    def DefaultIfEmpty(self, d=None):
        l = Seq(self)
        return l if l else Seq([d])

    def SequenceEqual(self, other):
        return list(self) == list(other)

    def Reverse(self):
        return Seq(reversed(list(self)))

    def CountBy(self, f):
        d = {}
        for x in self:
            k = f(x)
            d[k] = d.get(k, 0) + 1
        return Seq(KeyValuePair(k, v) for k, v in d.items())

    def Chunk(self, n):
        l = list(self)
        return Seq(Seq(l[i:i + n]) for i in range(0, len(l), n))

    def Index(self):
        return Seq(CsTupleLite((i, x)) for i, x in enumerate(self))

    def LongCount(self, f=None):
        return sum(1 for x in self if f is None or f(x))


class CsTupleLite(tuple):
    @property
    def Item1(self):
        return self[0]

    @property
    def Item2(self):
        return self[1]


class Seq(_Linq, list):
    """List<T> / T[] / IEnumerable<T>"""
    __slots__ = ()

    def __init__(self, it=()):
        if it is None:
            it = ()
        elif isinstance(it, int):
            it = ()
        list.__init__(self, it)

    @property
    def Count(self):
        return _CInt(len(self), self)

    @property
    def Length(self):
        return len(self)

    def Add(self, x):
        self.append(x)

    def AddRange(self, xs):
        self.extend(list(xs))

    def Insert(self, i, x):
        self.insert(int(i), x)

    def InsertRange(self, i, xs):
        self[int(i):int(i)] = list(xs)

    def Remove(self, x):
        for i, y in enumerate(self):
            if y is x or y == x:
                del self[i]
                return True
        return False

    def RemoveAt(self, i):
        del self[int(i)]

    def RemoveRange(self, i, n):
        del self[int(i):int(i) + int(n)]

    def RemoveAll(self, f):
        keep = [x for x in self if not f(x)]
        n = len(self) - len(keep)
        self[:] = keep
        return n

    def Clear(self):
        del self[:]

    def IndexOf(self, x, *a):
        for i, y in enumerate(self):
            if y is x or y == x:
                return i
        return -1

    def LastIndexOf(self, x):
        for i in range(len(self) - 1, -1, -1):
            if self[i] == x:
                return i
        return -1

    def Find(self, f):
        for x in self:
            if f(x):
                return x
        return None

    def FindLast(self, f):
        for x in reversed(self):
            if f(x):
                return x
        return None

    def FindIndex(self, *a):
        f = a[-1]
        start = int(a[0]) if len(a) > 1 else 0
        for i in range(start, len(self)):
            if f(self[i]):
                return i
        return -1

    def FindLastIndex(self, f):
        for i in range(len(self) - 1, -1, -1):
            if f(self[i]):
                return i
        return -1

    def FindAll(self, f):
        return Seq(x for x in self if f(x))

    def Exists(self, f):
        return any(f(x) for x in self)

    def TrueForAll(self, f):
        return all(f(x) for x in self)

    def ForEach(self, f):
        for x in list(self):
            f(x)

    def Sort(self, cmp=None, *a):
        if cmp is None:
            if len(self) and hasattr(self[0], "CompareTo") and not isinstance(self[0], (int, float, str)):
                self.sort(key=functools.cmp_to_key(lambda x, y: x.CompareTo(y)))
            else:
                self.sort()
        elif hasattr(cmp, "Compare"):
            self.sort(key=functools.cmp_to_key(cmp.Compare))
        else:
            self.sort(key=functools.cmp_to_key(cmp))

    def GetRange(self, i, n):
        return Seq(self[int(i):int(i) + int(n)])

    def CopyTo(self, arr, i=0):
        arr[i:i + len(self)] = self

    def AsReadOnly(self):
        return self

    def Peek(self):
        return self[0]

    def GetEnumerator(self):
        return CsEnumerator(self)

    def ToString(self):
        return "List"

    def __hash__(self):
        return id(self)

    def __eq__(self, o):
        return self is o

    def __ne__(self, o):
        return self is not o


class _Ordered(Seq):
    __slots__ = ("_src", "_keys")

    def __init__(self, src, keys):
        self._src = src
        self._keys = keys
        def cmp(a, b):
            for (f, desc) in self._keys:
                c = _key_cmp(f(a), f(b))
                if c:
                    return -c if desc else c
            return 0
        Seq.__init__(self, sorted(src, key=functools.cmp_to_key(cmp)))

    def ThenBy(self, f, *a):
        return _Ordered(self._src, self._keys + [(f, False)])

    def ThenByDescending(self, f, *a):
        return _Ordered(self._src, self._keys + [(f, True)])


class _Grouping(Seq):
    __slots__ = ("Key",)

    def __init__(self, k):
        Seq.__init__(self)
        self.Key = k


_FREE = object()


class _Slots:
    """.NET HashSet/Dictionary 的枚举顺序：按槽位；删除后的空槽按后进先出被新元素复用。"""
    __slots__ = ("keys", "idx", "free")

    def __init__(self):
        self.keys, self.idx, self.free = [], {}, []

    def add(self, k):
        if k in self.idx:
            return False
        if self.free:
            i = self.free.pop()
            self.keys[i] = k
        else:
            i = len(self.keys)
            self.keys.append(k)
        self.idx[k] = i
        return True

    def remove(self, k):
        i = self.idx.pop(k, None)
        if i is None:
            return False
        self.keys[i] = _FREE
        self.free.append(i)
        return True

    def clear(self):
        self.keys.clear()
        self.idx.clear()
        self.free.clear()

    def ordered(self):
        return [k for k in self.keys if k is not _FREE]


class HashSet(_Linq):
    def __init__(self, it=(), *a):
        self._s = _Slots()
        if it is None or isinstance(it, int) or (hasattr(it, "Equals") and hasattr(it, "GetHashCode") and not hasattr(it, "__iter__")):
            it = ()
        for x in it:
            self._s.add(x)

    def __iter__(self):
        return iter(self._s.ordered())

    def __len__(self):
        return len(self._s.idx)

    def __contains__(self, x):
        return x in self._s.idx

    def __bool__(self):
        return True

    @property
    def Count(self):
        return _CInt(len(self._s.idx), self)

    def Add(self, x):
        return self._s.add(x)

    def add(self, x):
        self._s.add(x)

    def Remove(self, x):
        return self._s.remove(x)

    def discard(self, x):
        self._s.remove(x)

    def Contains(self, x, *a):
        return x in self._s.idx

    def Clear(self):
        self._s.clear()

    def UnionWith(self, xs):
        for x in list(xs):
            self._s.add(x)

    def ExceptWith(self, xs):
        for x in list(xs):
            self._s.remove(x)

    def IntersectWith(self, xs):
        keep = set(xs)
        for x in self._s.ordered():
            if x not in keep:
                self._s.remove(x)

    def SymmetricExceptWith(self, xs):
        for x in list(dict.fromkeys(xs)):
            if not self._s.remove(x):
                self._s.add(x)

    def IsSubsetOf(self, xs):
        o = set(xs)
        return all(x in o for x in self._s.idx)

    def IsSupersetOf(self, xs):
        return all(x in self._s.idx for x in xs)

    def IsProperSubsetOf(self, xs):
        o = set(xs)
        return self.IsSubsetOf(o) and len(o) > len(self)

    def Overlaps(self, xs):
        return any(x in self._s.idx for x in xs)

    def SetEquals(self, xs):
        o = set(xs)
        return o == set(self._s.idx)

    def RemoveWhere(self, f):
        r = [x for x in self._s.ordered() if f(x)]
        for x in r:
            self._s.remove(x)
        return len(r)

    def CopyTo(self, arr, i=0):
        for j, x in enumerate(self._s.ordered()):
            arr[i + j] = x

    def __hash__(self):
        return id(self)

    def __eq__(self, o):
        return self is o


class KeyValuePair:
    __slots__ = ("Key", "Value")

    def __init__(self, k, v):
        self.Key, self.Value = k, v

    def __iter__(self):
        yield self.Key
        yield self.Value

    def Deconstruct(self, *outs):
        if outs:
            return (None, self.Key, self.Value)
        return (self.Key, self.Value)


class Dictionary(dict):
    def __init__(self, it=None, *a):
        dict.__init__(self)
        self._s = _Slots()
        if isinstance(it, Dictionary):
            for k in it._okeys():
                self[k] = dict.__getitem__(it, k)
        elif isinstance(it, dict):
            for k, v in it.items():
                self[k] = v
        elif it is not None and not isinstance(it, int) and hasattr(it, "__iter__"):
            for kv in it:
                if isinstance(kv, KeyValuePair):
                    self[kv.Key] = kv.Value
                else:
                    k, v = kv
                    self[k] = v

    def __setitem__(self, k, v):
        self._s.add(k)
        dict.__setitem__(self, k, v)

    def __delitem__(self, k):
        dict.__delitem__(self, k)
        self._s.remove(k)

    def clear(self):
        dict.clear(self)
        self._s.clear()

    def pop(self, k, *d):
        if k in self:
            v = dict.__getitem__(self, k)
            del self[k]
            return v
        if d:
            return d[0]
        raise KeyError(k)

    def setdefault(self, k, d=None):
        if k not in self:
            self[k] = d
        return dict.__getitem__(self, k)

    def update(self, other=(), **kw):
        items = other.items() if hasattr(other, "items") else other
        for k, v in items:
            self[k] = v
        for k, v in kw.items():
            self[k] = v

    def _okeys(self):
        return self._s.ordered()

    def keys(self):
        return self._s.ordered()

    def values(self):
        return [dict.__getitem__(self, k) for k in self._s.ordered()]

    def items(self):
        return [(k, dict.__getitem__(self, k)) for k in self._s.ordered()]

    def __getitem__(self, k):
        try:
            return dict.__getitem__(self, k)
        except KeyError:
            raise KeyNotFoundException(str(k))  # noqa

    @property
    def Count(self):
        return _CInt(len(self), list(self.items()))

    @property
    def Keys(self):
        return Seq(self.keys())

    @property
    def Values(self):
        return Seq(self.values())

    def Add(self, k, v):
        if k in self:
            raise CsException(f"duplicate key {k}")
        self[k] = v

    def TryAdd(self, k, v):
        if k in self:
            return False
        self[k] = v
        return True

    def ContainsKey(self, k):
        return k in self

    def ContainsValue(self, v):
        return v in self.values()

    def Remove(self, k, *a):
        if a:   # Remove(key, out value)
            if k in self:
                v = dict.__getitem__(self, k)
                del self[k]
                return (True, v)
            return (False, None)
        if k in self:
            del self[k]
            return True
        return False

    def TryGetValue(self, k, out=None):
        if k in self:
            return (True, dict.__getitem__(self, k))
        return (False, None)

    def GetValueOrDefault(self, k, d=None):
        return self.get(k, d)

    def Clear(self):
        self.clear()

    def __iter__(self):
        return iter(self._pairs())

    def _pairs(self):
        return [KeyValuePair(k, v) for k, v in self.items()]

    def __getattr__(self, n):
        if n in _Linq.__dict__:
            return getattr(Seq(self._pairs()), n)
        raise AttributeError(n)

    def __hash__(self):
        return id(self)

    def __eq__(self, o):
        return self is o


from .cs import KeyNotFoundException  # noqa: E402


def _skey(k):
    if hasattr(k, "CompareTo") and not isinstance(k, (int, float, str)):
        return functools.cmp_to_key(lambda a, b: a.CompareTo(b))(k)
    return k


class SortedDictionary(Dictionary):
    """SortedDictionary：按键有序枚举（字符串键为 Ordinal 序，与 Python 一致）。"""
    def _sorted(self):
        return sorted(dict.keys(self), key=_skey)

    def __iter__(self):
        return iter(self._pairs())

    def _pairs(self):
        return [KeyValuePair(k, dict.__getitem__(self, k)) for k in self._sorted()]

    @property
    def Keys(self):
        return Seq(self._sorted())

    @property
    def Values(self):
        return Seq(dict.__getitem__(self, k) for k in self._sorted())


class Queue(Seq):
    def Enqueue(self, x):
        self.append(x)

    def Dequeue(self):
        return self.pop(0)

    def TryDequeue(self, out=None):
        if self:
            return (True, self.pop(0))
        return (False, None)

    def Peek(self):
        return self[0]


class Stack(Seq):
    """C# Stack：内部按压栈顺序存放，枚举为后进先出。"""
    def __iter__(self):
        return list.__reversed__(self)

    def TryPeek(self, out=None):
        if len(self):
            return (True, list.__getitem__(self, -1))
        return (False, None)

    def Push(self, x):
        self.append(x)

    def Pop(self):
        return self.pop()

    def Peek(self):
        return self[-1]

    def TryPop(self, out=None):
        if self:
            return (True, self.pop())
        return (False, None)


class CsEnumerator:
    """IEnumerator：MoveNext/Current/Dispose（也可直接当 Python 迭代器用）。"""
    __slots__ = ("_it", "Current")

    def __init__(self, src):
        self._it = iter(src)
        self.Current = None

    def MoveNext(self):
        try:
            self.Current = next(self._it)
            return True
        except StopIteration:
            return False

    def Dispose(self):
        pass

    def Reset(self):
        raise NotImplementedError

    def __iter__(self):
        return self._it

    def __next__(self):
        return next(self._it)


class _LazyEnum(_Linq):
    """C# 迭代器方法（yield return）的返回值：每次枚举都重新执行、按需产出（惰性）。"""
    __slots__ = ("_f",)

    def __init__(self, f):
        self._f = f

    def __iter__(self):
        return iter(self._f())

    def __len__(self):
        return sum(1 for _ in self._f())

    def __getitem__(self, i):
        return Seq(self._f())[i]

    def __bool__(self):
        return True

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return getattr(Seq(self._f()), n)


def _iter(x):
    if x is None:
        raise CsException("foreach over null")
    if isinstance(x, Dictionary):
        return x._pairs()
    if isinstance(x, dict):
        return [KeyValuePair(k, v) for k, v in x.items()]
    if isinstance(x, (list, tuple, set, frozenset)):
        return list(x)
    return x


class Enumerable:
    @staticmethod
    def Range(a, n):
        return Seq(range(int(a), int(a) + int(n)))

    @staticmethod
    def Repeat(x, n):
        return Seq([x] * int(n))

    @staticmethod
    def Empty(*a):
        return Seq()


# 为 Python 内建 list/tuple 也提供 LINQ（某些路径会拿到原生列表）
def seqify(x):
    return x if isinstance(x, _Linq) else Seq(x)



def _strip_g(cls):
    import inspect
    for n, f in list(cls.__dict__.items()):
        if n.startswith("__") or not callable(f) or isinstance(f, (staticmethod, classmethod, property)):
            continue
        try:
            if "_g" in inspect.signature(f).parameters:
                continue
        except (TypeError, ValueError):
            continue
        def mk(f):
            def w(*a, _g=None, **k):
                return f(*a, **k)
            w.__name__ = f.__name__
            return w
        setattr(cls, n, mk(f))


def _OfType(self, t=None, _g=None):
    t = t if t is not None else _g[0]
    return Seq(x for x in self if isinstance(x, t))


_Linq.OfType = _OfType
for _c in (_Linq, Seq, HashSet, Dictionary, Queue, Stack):
    _strip_g(_c)


CsQueue = Queue
CsStack = Stack
