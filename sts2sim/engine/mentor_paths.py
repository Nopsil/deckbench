"""spire-mentor 装在哪：环境变量、mentor.local.json，或程序旁边的 mentor/ 目录。

本文件不导入游戏、不导入 sts2_rs。官方安装包不带 spire-mentor（它的仓库含游戏文本和数据）。
打包版的 DeckBench.exe 也加载不了用户自己编译的 sts2_rs，所以整局批量会改用
mentor.local.json 里的 python（构建 sts2_rs 的那个 CPython）来跑工作进程。

查找顺序（后面的非空项覆盖前面的）：
  1. <程序目录>/mentor/  （site/sts2_rs、py/sts2_hint，可选 python.txt）
  2. <数据目录>/mentor.local.json，然后 <程序目录>/mentor.local.json
  3. DECKBENCH_MENTOR_CONFIG 指向的 json
  4. 环境变量 DECKBENCH_MENTOR_SITE / _PY / _PYTHON
     （旧名 STS2SIM_MENTOR_SITE / _PY 仍可用，正式名字优先）

DECKBENCH_MENTOR_NO_DEFAULTS=1 时不读程序目录和默认数据目录（测试用）。
"""
import json
import os
import shutil
import subprocess
import sys

VANILLA = ("Ironclad", "Silent", "Defect", "Necrobinder", "Regent")
_KEYS = ("site", "py", "python")
_ALIASES = {"mentor_site": "site", "mentor_py": "py", "mentor_python": "python"}


def repo_or_app_dir():
    """开发时是仓库根；打包后是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def _data_dirs():
    env = os.environ.get("STS2SIM_GUI_DATA")
    if env:
        return [env]
    if os.environ.get("DECKBENCH_MENTOR_NO_DEFAULTS") == "1":
        return []
    if getattr(sys, "frozen", False):
        return [os.path.join(repo_or_app_dir(), "data")]
    return [os.path.join(repo_or_app_dir(), "gui", ".data")]


def _skip_defaults():
    return os.environ.get("DECKBENCH_MENTOR_NO_DEFAULTS") == "1"


def dropin_roots():
    roots = []
    home = os.environ.get("DECKBENCH_MENTOR_HOME", "").strip()
    if home:
        roots.append(home)
    if not _skip_defaults():
        roots.append(os.path.join(repo_or_app_dir(), "mentor"))
    for d in _data_dirs():
        roots.append(os.path.join(d, "mentor"))
    out = []
    for r in roots:
        if r and r not in out:
            out.append(r)
    return out


def config_files():
    files = []
    if not _skip_defaults():
        files.append(os.path.join(repo_or_app_dir(), "mentor.local.json"))
    for d in _data_dirs():
        files.append(os.path.join(d, "mentor.local.json"))
    extra = os.environ.get("DECKBENCH_MENTOR_CONFIG", "").strip()
    if extra:
        files.append(extra)
    out = []
    for f in files:
        if f and f not in out:
            out.append(f)
    return out


def _abs(value, base):
    value = os.path.expanduser(str(value or "").strip())
    if not value:
        return ""
    if not os.path.isabs(value):
        value = os.path.join(base, value)
    return os.path.normpath(value)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    base = os.path.dirname(os.path.abspath(path))
    out = {}
    for k, v in d.items():
        key = _ALIASES.get(k, k)
        if key in _KEYS and isinstance(v, (str, os.PathLike)):
            out[key] = _abs(v, base)
    return out


def _python_txt(root):
    path = os.path.join(root, "python.txt")
    try:
        lines = open(path, encoding="utf-8-sig").read().splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            return _abs(line, root)
    return ""


def _overlay(cfg, incoming, source):
    changed = False
    for k in _KEYS:
        v = incoming.get(k) or ""
        if v:
            cfg[k] = v
            changed = True
    if changed:
        cfg["source"] = source
    return cfg


def resolve():
    """返回 {site, py, python, source}。目录可以还不存在，调用方再检查。"""
    cfg = {"site": "", "py": "", "python": "", "source": ""}
    for root in dropin_roots():
        site = os.path.join(root, "site")
        py = os.path.join(root, "py")
        if not os.path.isdir(os.path.join(py, "sts2_hint")):
            alt = os.path.join(root, "python")
            if os.path.isdir(os.path.join(alt, "sts2_hint")):
                py = alt
        if os.path.isdir(os.path.join(site, "sts2_rs")) and os.path.isdir(os.path.join(py, "sts2_hint")):
            _overlay(cfg, {"site": os.path.abspath(site), "py": os.path.abspath(py), "python": _python_txt(root)}, "dropin:" + os.path.abspath(root))
    for f in config_files():
        d = _read_json(f)
        if d:
            _overlay(cfg, d, "file:" + os.path.abspath(f))
    env = {
        "site": os.environ.get("STS2SIM_MENTOR_SITE", ""),
        "py": os.environ.get("STS2SIM_MENTOR_PY", ""),
    }
    _overlay(cfg, {k: _abs(v, os.getcwd()) for k, v in env.items()}, "env")
    _overlay(cfg, {
        "site": _abs(os.environ.get("DECKBENCH_MENTOR_SITE", ""), os.getcwd()),
        "py": _abs(os.environ.get("DECKBENCH_MENTOR_PY", ""), os.getcwd()),
        "python": _abs(os.environ.get("DECKBENCH_MENTOR_PYTHON", ""), os.getcwd()),
    }, "env")
    return cfg


def dirs_ok(cfg=None):
    cfg = cfg or resolve()
    return bool(cfg.get("site") and cfg.get("py")
                and os.path.isdir(os.path.join(cfg["site"], "sts2_rs"))
                and os.path.isdir(os.path.join(cfg["py"], "sts2_hint")))


def python_executable(cfg=None):
    """构建了 sts2_rs 的 CPython。不是文件、或就是打包版 exe 自己，则返回空串。"""
    cfg = cfg or resolve()
    raw = cfg.get("python") or ""
    if not raw:
        return ""
    path = raw if os.path.isfile(raw) else (shutil.which(raw) or "")
    if not path or not os.path.isfile(path):
        return ""
    path = os.path.abspath(path)
    if getattr(sys, "frozen", False) and os.path.normcase(path) == os.path.normcase(os.path.abspath(sys.executable)):
        return ""
    return path


def path_entries(cfg=None):
    cfg = cfg or resolve()
    out = []
    for k in ("site", "py"):
        p = cfg.get(k) or ""
        if p and os.path.isdir(p) and p not in out:
            out.append(p)
    return out


def apply_env(env, cfg=None):
    """把解析出的绝对路径写进子进程环境，并把 site/py 加到 PYTHONPATH 末尾（不盖过我们自己的包）。"""
    cfg = cfg or resolve()
    env["DECKBENCH_MENTOR_SITE"] = cfg.get("site") or ""
    env["DECKBENCH_MENTOR_PY"] = cfg.get("py") or ""
    py = python_executable(cfg)
    if py:
        env["DECKBENCH_MENTOR_PYTHON"] = py
    extra = [p for p in path_entries(cfg) if p not in (env.get("PYTHONPATH") or "").split(os.pathsep)]
    if extra:
        env["PYTHONPATH"] = os.pathsep.join([p for p in (env.get("PYTHONPATH"), *extra) if p])
    return env


def availability():
    """界面用：只看目录和（打包版）python 路径，不加载 sts2_rs。"""
    cfg = resolve()
    ok = dirs_ok(cfg)
    py = python_executable(cfg)
    frozen = bool(getattr(sys, "frozen", False))
    if not ok:
        reason = "missing"
        available = False
    elif frozen and not py:
        reason = "need_python"
        available = False
    else:
        reason = ""
        available = True
    return {"available": available, "reason": reason, "dirs_ok": ok, "python": py, "frozen": frozen, "cfg": cfg}


def add_paths(cfg=None):
    for p in path_entries(cfg):
        if p not in sys.path:
            sys.path.append(p)


def _import_in_process():
    """在当前解释器里 import sts2_rs 和 sts2_hint.adapter。成功返回 None，失败返回短错误。"""
    if not dirs_ok():
        return "sts2_rs / sts2_hint directories not found"
    add_paths()
    try:
        import sts2_rs  # noqa: F401
        from sts2_hint import adapter  # noqa: F401
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa  Rust 的 PanicException 是 BaseException
        return f"{type(e).__name__}: {e}"
    return None


def _ensure_src_on_env(env):
    """子进程要能 import sts2sim（测试和没设 PYTHONPATH 的命令行）。我们的目录放在最前。"""
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.dirname(pkg)
    pp = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    if os.path.isdir(os.path.join(src, "sts2sim")) and src not in pp:
        pp.insert(0, src)
    env["PYTHONPATH"] = os.pathsep.join(pp)
    return env


def import_error():
    """父进程用：另起一个解释器试加载，避免在 fork 出工作进程之前把 Rust 运行时载入本进程。

    目录都没有时不启动子进程。打包版 exe 不能 `python -c`（那会再开一个界面），改在本进程里试。
    成功返回 None。
    """
    cfg = resolve()
    if not dirs_ok(cfg):
        src = cfg.get("source") or "(none)"
        return (f"sts2_rs / sts2_hint directories not found (source {src}). "
                "Set DECKBENCH_MENTOR_SITE and DECKBENCH_MENTOR_PY, or mentor.local.json. "
                "See docs/DEVELOPER.md.")
    if getattr(sys, "frozen", False):
        return _import_in_process()
    env = _ensure_src_on_env(apply_env(dict(os.environ), cfg))
    code = ("from sts2sim.engine.mentor_paths import _import_in_process\n"
            "import sys\n"
            "err = _import_in_process()\n"
            "if err:\n"
            "    sys.stdout.write(err)\n"
            "    raise SystemExit(3)\n")
    try:
        proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"{type(e).__name__}: {e}"
    if proc.returncode == 0:
        return None
    msg = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return msg or f"import check exited {proc.returncode}"


def explain_import_failure(err):
    return ("spire-mentor 加载失败，批量已停止（不会静默改用学习版 AI）。\n"
            "spire-mentor failed to load; the batch stopped (it will not silently fall back to the learned AI).\n"
            f"{err}\n"
            "检查 / check: python -m sts2sim.engine.mentor_paths\n"
            "说明 / docs: docs/DEVELOPER.md\n")


def mstats_line(rows):
    """把每局的 mstats 收成一行数字。没有 mentor 统计就返回 None。"""
    ms = []
    for r in rows or []:
        m = r.get("mstats") if isinstance(r, dict) else None
        if isinstance(m, dict) and "mentor" in m:
            ms.append(m)
    if not ms:
        return None
    ok = sum(int(m.get("mentor") or 0) for m in ms)
    fb = sum(int(m.get("fallback") or 0) for m in ms)
    net = fb_n = 0
    acc = {}
    for m in ms:
        for k, v in (m.get("ppo") or {}).items():
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                a = acc.setdefault(str(k), [0, 0])
                a[0] += int(v[0])
                a[1] += int(v[1])
                net += int(v[0])
                fb_n += int(v[1])
    ppo = ", ".join(f"{k} {a[0]}/{a[1]}" for k, a in sorted(acc.items())) or "-"
    return {"ok": ok, "fb": fb, "pct": f"{fb / max(1, ok + fb):.1%}", "ppo": ppo,
            "ppo_net": net, "ppo_fb": fb_n}


def main():
    st = availability()
    cfg = st["cfg"]
    print(f"configured: {'yes' if st['dirs_ok'] else 'no'}")
    print(f"selectable: {'yes' if st['available'] else 'no'} ({st['reason'] or 'ok'})")
    print(f"frozen: {'yes' if st['frozen'] else 'no'}")
    print(f"source: {cfg.get('source') or '(none)'}")
    print(f"site: {cfg.get('site') or '(empty)'}")
    print(f"py: {cfg.get('py') or '(empty)'}")
    print(f"python: {st['python'] or '(empty)'}")
    if not st["dirs_ok"]:
        print("import: skipped")
        print("DeckBench does not ship spire-mentor. Point SITE/PY at your own build, or add mentor.local.json.")
        print("说明：安装包不含 spire-mentor。请指向你自己的构建，或写 mentor.local.json。见 docs/DEVELOPER.md。")
        return 2
    err = _import_in_process()
    if err:
        print("import: FAIL")
        print(err)
        return 2
    print("import: ok")
    if st["frozen"] and not st["python"]:
        print("Packaged DeckBench.exe still cannot run this agent until DECKBENCH_MENTOR_PYTHON is set.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
