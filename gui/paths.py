"""路径：开发模式下模拟器根目录 = gui 的上一级；打包后 = 可执行文件旁边的 sim/ 文件夹。"""
import os
import sys

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    SIM_ROOT = os.environ.get("STS2SIM_ROOT") or os.path.join(APP_DIR, "sim")
    WEB_DIST = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "gui_web")
    DATA_DIR = os.environ.get("STS2SIM_GUI_DATA") or os.path.join(APP_DIR, "data")
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    SIM_ROOT = os.environ.get("STS2SIM_ROOT") or os.path.dirname(APP_DIR)
    WEB_DIST = os.path.join(APP_DIR, "web", "dist")
    DATA_DIR = os.environ.get("STS2SIM_GUI_DATA") or os.path.join(APP_DIR, ".data")

RUNS_DIR = os.path.join(DATA_DIR, "runs")
USER_MODS_DIR = os.path.join(DATA_DIR, "mods")
CACHE_DIR = os.path.join(DATA_DIR, "cache")


def setup_sys_path():
    """让模拟器包、tools/、mods/ 可导入（worker 子进程和 multiprocessing 子进程都要调用）。"""
    for p in (os.path.join(SIM_ROOT, "mods"), os.path.join(SIM_ROOT, "tools"), SIM_ROOT):
        if p not in sys.path:
            sys.path.insert(0, p)


def ensure_dirs():
    for d in (RUNS_DIR, USER_MODS_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
