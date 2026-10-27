"""读 .NET 程序集的元数据（类型、基类、程序集引用、ModInitializer）。不执行代码。"""
import os

GAME_ASSEMBLIES = {"sts2", "godotsharp", "0harmony"}
MODEL_BASES = {"CardModel": "card", "PowerModel": "power", "RelicModel": "relic",
               "PotionModel": "potion", "CharacterModel": "character"}
_ABSTRACT = 0x00000080


def _s(item):
    if item is None:
        return ""
    v = getattr(item, "value", None)
    if isinstance(v, str):
        return v
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(item)


def _ser_string(blob, i):
    if i >= len(blob):
        return None, i
    b0 = blob[i]
    if b0 < 0x80:
        n, i = b0, i + 1
    elif b0 < 0xC0 and i + 1 < len(blob):
        n = ((b0 & 0x3F) << 8) | blob[i + 1]
        i += 2
    else:
        return None, i
    raw = blob[i:i + n]
    return raw.decode("utf-8", "replace"), i + n


def _attr_string(blob):
    """Custom attribute blob 里的第一个字符串参数。prolog 必须是 0x0001。"""
    if not blob or len(blob) < 4 or blob[0] != 0x01 or blob[1] != 0x00:
        return None
    text, _i = _ser_string(blob, 2)
    return text or None


class AssemblyInfo:
    def __init__(self, name, refs, types, initializers):
        self.name = name
        self.refs = refs
        self.types = types
        self.initializers = initializers

    @property
    def is_game(self):
        return self.name.lower() in GAME_ASSEMBLIES

    def models(self):
        return [t for t in self.types if t["kind"]]


def read_assembly(path):
    try:
        import dnfile
    except ImportError as e:
        raise RuntimeError("dnfile") from e
    try:
        pe = dnfile.dnPE(path)
    except Exception as e:  # noqa
        raise ValueError(str(e)) from e
    if pe.net is None or pe.net.mdtables is None:
        raise ValueError("not a .NET assembly")
    tables = pe.net.mdtables
    asm_rows = tables.Assembly.rows if tables.Assembly else []
    name = _s(asm_rows[0].Name) if asm_rows else os.path.splitext(os.path.basename(path))[0]
    refs = []
    if tables.AssemblyRef:
        refs = [_s(r.Name) for r in tables.AssemblyRef.rows]
    types = []
    if tables.TypeDef:
        for row in tables.TypeDef.rows:
            tname = _s(row.TypeName)
            if not tname or tname.startswith("<") or "<>" in tname or tname.startswith("_003C"):
                continue
            base, base_ns = _base(row)
            flags = getattr(row, "Flags", 0) or 0
            try:
                abstract = bool(int(flags) & _ABSTRACT)
            except (TypeError, ValueError):
                abstract = False
            types.append({
                "name": tname, "namespace": _s(row.TypeNamespace), "base": base, "base_ns": base_ns,
                "kind": None if abstract else MODEL_BASES.get(base), "abstract": abstract,
            })
    initializers = []
    if tables.CustomAttribute:
        for row in tables.CustomAttribute.rows:
            target = getattr(row.Type, "row", None)
            if target is None:
                continue
            cls = getattr(getattr(target, "Class", None), "row", None)
            cname = _s(getattr(cls, "TypeName", None)) if cls is not None else _s(getattr(target, "TypeName", None))
            if cname != "ModInitializerAttribute":
                continue
            parent = getattr(row.Parent, "row", None)
            pname = _s(getattr(parent, "TypeName", None)) if parent is not None else ""
            blob = getattr(row.Value, "value", None)
            method = _attr_string(bytes(blob) if blob is not None else b"")
            if pname and method:
                initializers.append((pname, method))
    return AssemblyInfo(name, refs, types, initializers)


def _base(row):
    ext = getattr(row, "Extends", None)
    target = getattr(ext, "row", None) if ext is not None else None
    if target is None:
        return None, None
    return _s(getattr(target, "TypeName", None)) or None, _s(getattr(target, "TypeNamespace", None)) or None
