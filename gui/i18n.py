"""界面语言（Python 侧）：和前端共用 gui/locales/<lang>.json（扁平键）。

- 界面语言：zhs（简体中文，默认/回退）、en、ja、ko
- 游戏里的名字（卡牌、角色、遭遇…）不在翻译表里：运行时按所选语言从玩家自己的游戏安装读（sts2sim/gameloc.py），
  该语言缺某个键就依次回退英文 eng、简体中文 zhs，最后显示 ID。
- 选择保存在 <数据目录>/settings.json；第一次没有选择时按系统语言（中文→zhs、日语→ja、韩语→ko、其他→en）。

UI language for our own strings (shared with the web UI); game names follow the same language from the player's install.
"""
import contextvars
import json
import locale
import os
import sys

LANGS = ("zhs", "en", "ja", "ko")
DEFAULT = "zhs"
# 界面语言 → 游戏 .pck 里 localization/<code>/ 的语言代码
GAME_LANG = {"zhs": "zhs", "en": "eng", "ja": "jpn", "ko": "kor"}
LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

_MSG = {}
_REQ_LANG = contextvars.ContextVar("deckbench_lang", default=None)


def normalize(s):
    """任意语言标记（zh-CN / zh_Hans / ja_JP / ko-KR / en-US / jpn …）→ 界面语言；认不出 → en。"""
    s = str(s or "").strip().lower().replace("_", "-")
    if not s:
        return "en"
    if s in LANGS:
        return s
    if s.startswith("zh") or s in ("chinese", "chs"):
        return "zhs"
    if s.startswith("ja") or s in ("jpn", "japanese"):
        return "ja"
    if s.startswith("ko") or s in ("kor", "korean"):
        return "ko"
    return "en"


def messages(lang):
    if lang not in _MSG:
        try:
            with open(os.path.join(LOCALES_DIR, f"{lang}.json"), encoding="utf-8") as f:
                _MSG[lang] = json.load(f)
        except (OSError, ValueError):
            _MSG[lang] = {}
    return _MSG[lang]


# ---------------------------------------------------------------- 当前语言
def _settings_file():
    from . import paths
    return os.path.join(paths.DATA_DIR, "settings.json")


def load_settings():
    try:
        with open(_settings_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    d = load_settings()
    d.update(kw)
    f = _settings_file()
    os.makedirs(os.path.dirname(f), exist_ok=True)
    tmp = f + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, f)
    return d


def saved_lang():
    v = load_settings().get("lang")
    return v if v in LANGS else None


def os_lang():
    """系统界面语言（原始标记，比如 zh-CN / ja-JP）；拿不到返回 ''。"""
    if os.name == "nt":
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return locale.windows_locale.get(lcid, "")
        except Exception:  # noqa
            pass
    for k in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(k)
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            return v.split(":")[0].split(".")[0]
    try:
        v = locale.getlocale()[0]
        return v or ""
    except Exception:  # noqa
        return ""


def set_request_lang(lang):
    """服务器每个请求开头调用（前端在请求头 x-lang 里带当前语言）。"""
    return _REQ_LANG.set(lang if lang in LANGS else None)


def current():
    """请求头 > 环境变量 DECKBENCH_LANG（工作进程）> 保存的选择 > 系统语言。"""
    v = _REQ_LANG.get()
    if v:
        return v
    v = os.environ.get("DECKBENCH_LANG")
    if v:
        return normalize(v)
    try:
        v = saved_lang()
    except Exception:  # noqa
        v = None
    if v:
        return v
    o = os_lang()
    return normalize(o) if o else DEFAULT


def t(key, lang=None, **kw):
    lang = lang or current()
    s = messages(lang).get(key)
    if s is None:
        s = messages(DEFAULT).get(key, key)
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s


def has(key, lang=None):
    return key in messages(lang or current()) or key in messages(DEFAULT)


def tr(prefix, value, lang=None):
    """有翻译就翻译 prefix+value，没有就原样返回（房间这类以中文做 ID 的值）。"""
    k = f"{prefix}{value}"
    return t(k, lang) if has(k, lang) else value


def join(items, lang=None):
    return t("sep.list", lang).join(str(x) for x in items)


# ---------------------------------------------------------------- 游戏文本（从玩家自己的安装读）
def game_langs(lang):
    """查游戏文本时依次尝试的语言代码：所选语言 → eng → zhs（去重）。"""
    out = []
    for g in (GAME_LANG.get(lang, "eng"), "eng", "zhs"):
        if g not in out:
            out.append(g)
    return out


def game_text(table, key, lang=None, field="title"):
    """游戏本地化表里的 <key>.<field>，按 game_langs 回退；都没有返回 None。"""
    try:
        from sts2sim import gameloc
    except Exception:  # noqa
        return None
    for g in game_langs(lang or current()):
        try:
            tb = gameloc.table(table, g)
        except Exception:  # noqa
            tb = None
        if tb:
            v = tb.get(f"{key}.{field}")
            if isinstance(v, str) and v.strip():
                return v
    return None


if __name__ == "__main__":   # python -m gui.i18n  → 打印探测到的系统语言
    print(os_lang(), "->", normalize(os_lang()), file=sys.stdout)
