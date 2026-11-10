# -*- mode: python ; coding: utf-8 -*-
# 构建：在 build 目录里运行  pyinstaller --noconfirm DeckBench.spec
# 目录结构：src/gui（界面包）、src/launcher.py、sim/（模拟器源码，构建后复制到 dist/DeckBench/sim）
import ast
import os
import sys

HERE = os.path.abspath(SPECPATH)
SIM = os.path.join(HERE, "..", "sim")


def scan_stdlib_imports(root):
    """扫描模拟器源码里用到的标准库模块，作为 hiddenimports（模拟器源码本身不打包，所以 PyInstaller 看不到这些导入）。"""
    found = set()
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.endswith(".py"):
                continue
            try:
                tree = ast.parse(open(os.path.join(dp, f), encoding="utf-8").read())
            except Exception:
                continue
            for n in ast.walk(tree):
                names = []
                if isinstance(n, ast.Import):
                    names = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                    names = [n.module]
                for m in names:
                    if m.split(".")[0] in sys.stdlib_module_names or m.split(".")[0] == "yaml":
                        found.add(m)
    return sorted(found)


hidden = scan_stdlib_imports(SIM) + [
    "gui.worker", "gui.fightworkers", "gui.server", "gui.backend", "gui.jobs", "gui.metrics", "gui.modpatch", "gui.i18n",
    "dnfile", "pefile",
    "multiprocessing.pool", "multiprocessing.popen_spawn_win32", "multiprocessing.popen_spawn_posix",
    "concurrent.futures", "concurrent.futures.process", "importlib.util", "statistics", "csv", "zlib",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "multipart", "python_multipart",
]
hidden = [h for h in hidden if h not in ("signal",)] + ["signal"]

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[HERE],
    datas=[(os.path.join(HERE, "gui", "web", "dist"), "gui_web"),
           (os.path.join(HERE, "gui", "locales"), os.path.join("gui", "locales"))],   # 界面翻译表（gui/i18n.py 读）
    hiddenimports=hidden,
    excludes=["tkinter", "sts2sim", "claude_v35", "batch", "v34_data", "cs2py_core", "cs_patches", "parse_monster_ai", "helpers",
              "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
# file_version_info.txt is written by build.ps1 from sts2sim.__version__ (write_version_info.py).
_version_file = os.path.join(HERE, "file_version_info.txt")
_exe_kwargs = {}
if sys.platform == "win32":
    if not os.path.isfile(_version_file):
        raise SystemExit("file_version_info.txt is missing; build.ps1 writes it from sts2sim.__version__")
    _exe_kwargs["version"] = _version_file
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DeckBench", console=False,
          icon=os.path.join(HERE, "icon.ico"), upx=False, **_exe_kwargs)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DeckBench")
