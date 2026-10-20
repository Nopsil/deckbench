"""PyInstaller 入口。模拟器源码以普通 .py 文件放在 exe 旁边的 sim/ 文件夹（不打进 exe），启动时加入 sys.path。"""
import os
import sys

if getattr(sys, "frozen", False):
    # 无控制台窗口的 exe 没有 stdout/stderr：写到 data/app.log，避免 uvicorn 日志报错
    _app = os.path.dirname(os.path.abspath(sys.executable))
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(os.path.join(_app, "data"), exist_ok=True)
        _log = open(os.path.join(_app, "data", "app.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _log
        if sys.stderr is None:
            sys.stderr = _log

from gui import paths  # noqa: E402

paths.setup_sys_path()

import multiprocessing  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from gui.app import main
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        traceback.print_exc()   # 打包版写到 data/app.log
        raise
