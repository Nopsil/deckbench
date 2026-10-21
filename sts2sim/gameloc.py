"""运行时从玩家本机的游戏安装读官方本地化文本（eng / zhs / jpn / kor 等，看安装里有哪些），只在内存里用，不写进仓库、不打包。

文本来源（按顺序）：
  DECKBENCH_GAME_LOC_ENG / _ZHS / _JPN / _KOR       直接指向含 events.json 等表的目录（可选）
  DECKBENCH_GAME_PCK                                 游戏的 .pck 文件（可选）
  否则：已生成数据所绑定的那份安装（gamedata 的 manifest）或自动检测到的安装里的 .pck
.pck 是 Godot 资源包（未加密的 v2/v3 格式）；我们只读 localization/<语言>/<表>.json 这几项。
找不到时返回 None，调用方会回退（中文名回退成 ID，事件 PPO 回退到我们自己的策略）。

Official localization (eng/zhs/jpn/kor…) read at runtime from the player's own install, kept in memory only; never committed or shipped.
"""
import hashlib
import json
import os
import struct

_TABLES = {}      # (lang, table) -> dict | None
_INDEX = {}       # pck path -> {(lang, table): (offset, size, md5)}
_LANG_ENV = {"eng": "DECKBENCH_GAME_LOC_ENG", "zhs": "DECKBENCH_GAME_LOC_ZHS",
             "jpn": "DECKBENCH_GAME_LOC_JPN", "kor": "DECKBENCH_GAME_LOC_KOR"}


def read_pck_index(path):
    """返回 {(语言, 表名): (offset, size, md5)}，只含 localization/<lang>/<table>.json。"""
    out = {}
    with open(path, "rb") as f:
        def rd(fmt):
            return struct.unpack(fmt, f.read(struct.calcsize(fmt)))
        magic, ver, _a, _b, _c, flags = rd("<6I")
        if magic != 0x43504447 or ver not in (2, 3) or flags & 1:
            raise ValueError("not an unencrypted Godot PCK v2/v3")
        base, = rd("<Q")
        if ver == 3:
            d, = rd("<Q")
            f.seek(d)
        else:
            f.seek(64, 1)
        n, = rd("<I")
        for _ in range(n):
            ln, = rd("<I")
            name = f.read(ln).rstrip(b"\0").decode("utf-8", "replace")
            off, size = rd("<QQ")
            md5 = f.read(16)
            eflags, = rd("<I")
            parts = name[6:].split("/") if name.startswith("res://") else name.split("/")
            if len(parts) == 3 and parts[0] == "localization" and parts[2].endswith(".json") and not eflags:
                out[(parts[1], parts[2][:-5])] = (base + off, size, md5)
    return out


def find_pck():
    p = os.environ.get("DECKBENCH_GAME_PCK")
    if p and os.path.isfile(p):
        return p
    from . import gamedata
    dll = None
    try:
        mf = os.path.join(json.load(open(gamedata._current_file(), encoding="utf-8"))["cache_dir"], "manifest.json")
        dll = json.load(open(mf, encoding="utf-8")).get("dll_path")
    except Exception:  # noqa
        pass
    if not dll or not os.path.isfile(dll):
        dll = gamedata.find_dll()
    if not dll:
        return None
    d = os.path.dirname(dll)
    for _ in range(4):   # sts2.dll 在 data_*/ 子目录里，.pck 在游戏根目录
        try:
            pcks = [os.path.join(d, x) for x in os.listdir(d) if x.lower().endswith(".pck")]
        except OSError:
            pcks = []
        if pcks:
            return max(pcks, key=os.path.getsize)
        d = os.path.dirname(d)
    return None


def table(name, lang="eng"):
    """本地化表 dict（键 → 文本），没有就 None。"""
    k = (lang, name)
    if k in _TABLES:
        return _TABLES[k]
    t = None
    d = os.environ.get(_LANG_ENV.get(lang, "DECKBENCH_GAME_LOC_" + lang.upper()), "")
    try:
        if d:
            with open(os.path.join(d, name + ".json"), encoding="utf-8") as f:
                t = json.load(f)
        else:
            p = find_pck()
            if p:
                if p not in _INDEX:
                    _INDEX[p] = read_pck_index(p)
                e = _INDEX[p].get(k)
                if e:
                    with open(p, "rb") as f:
                        f.seek(e[0])
                        data = f.read(e[1])
                    if hashlib.md5(data).digest() == e[2]:
                        t = json.loads(data.decode("utf-8-sig"))
    except Exception:  # noqa
        t = None
    _TABLES[k] = t
    return t


def available(lang="eng"):
    return table("events", lang) is not None


def languages():
    """安装里有本地化表的语言代码集合（读 .pck 索引；读不到返回空集合）。"""
    try:
        p = find_pck()
        if not p:
            return set()
        if p not in _INDEX:
            _INDEX[p] = read_pck_index(p)
        return {lang for lang, _t in _INDEX[p]}
    except Exception:  # noqa
        return set()
