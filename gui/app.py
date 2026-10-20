"""桌面入口：python -m gui.app            —— 独立窗口（pywebview）
           python -m gui.app --browser  —— 用浏览器打开（没有 pywebview 时也会退回这里）
           python -m gui.app --serve --port 8765  —— 只开服务（测试用）
打包后的 exe 也走这里；exe --worker ... 用来跑模拟（子进程）。"""
import multiprocessing
import os
import socket
import sys
import threading
import time

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui import paths  # noqa: E402

paths.setup_sys_path()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def serve(port, block=True):
    import uvicorn
    from gui.server import app, jobs
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    if block:
        try:
            server.run()
        finally:
            jobs.shutdown()
        return server
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    return server


RUNTIMECONFIG = {"runtimeOptions": {"tfm": "net6.0", "rollForward": "LatestMajor",
                                    "framework": {"name": "Microsoft.WindowsDesktop.App", "version": "6.0.0"}}}


def _clr_kwargs(kind):
    if kind != "coreclr":
        return {}
    import json
    paths.ensure_dirs()
    f = os.path.join(paths.CACHE_DIR, "webview.runtimeconfig.json")
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(RUNTIMECONFIG, fh)
    return {"runtime_config": f}


def _probe_clr(kind):
    """在子进程里试加载 .NET（pywebview 的 Windows 窗口靠 pythonnet + WinForms）；失败不影响主进程。"""
    import subprocess
    argv = [sys.executable, "--probe-clr", kind] if paths.FROZEN else [sys.executable, "-m", "gui.app", "--probe-clr", kind]
    try:
        p = subprocess.run(argv, capture_output=True, timeout=30, creationflags=0x08000000)
        return p.returncode == 0
    except Exception:
        return False


def _setup_clr():
    """Windows：.NET Framework（netfx）优先，不行再用 .NET 6+ 桌面运行时（coreclr）；都不行返回 False（改用浏览器）。"""
    if os.name != "nt":
        return True
    import pythonnet
    for kind in ("netfx", "coreclr"):
        if _probe_clr(kind):
            pythonnet.load(kind, **_clr_kwargs(kind))
            return True
    return False


_WAIT_TITLE = "DeckBench - 首次运行 / First run"


def _please_wait():
    """Windows：生成数据期间显示一个「请稍候」提示框，生成结束后自动关闭。返回关闭函数。"""
    msg = ("正在从你本机的游戏安装生成数据，大约 1–2 分钟，请稍候……\n完成后界面会自动打开。\n\n"
           "Generating data from your own game install (about 1–2 minutes)...\nThe app will open automatically when done.")
    print(msg, flush=True)
    if os.name != "nt":
        return lambda: None
    import ctypes
    u32 = ctypes.windll.user32
    t = threading.Thread(target=lambda: u32.MessageBoxW(None, msg, _WAIT_TITLE, 0x40 | 0x40000), daemon=True)
    t.start()

    def close():
        for _ in range(20):
            h = u32.FindWindowW(None, _WAIT_TITLE)
            if h:
                u32.PostMessageW(h, 0x0010, 0, 0)   # WM_CLOSE
                return
            if not t.is_alive():
                return
            time.sleep(0.1)
    return close


def _ensure_game_or_exit():
    """必须有玩家自己安装的游戏：首次运行在本机生成数据；找不到安装就提示并退出。"""
    from sts2sim import gamedata
    try:
        gamedata.verify()
        return
    except gamedata.GameDataError:
        pass
    close = lambda: None  # noqa: E731
    try:
        if gamedata.find_dll() is not None or gamedata._previous_game_dir():
            close = _please_wait()
        gamedata.ensure()
    except Exception as e:  # noqa  — GameDataError 或生成过程中的意外错误，都给出可读提示
        close()
        if not isinstance(e, gamedata.GameDataError):
            import traceback
            traceback.print_exc()
        msg = str(e) if isinstance(e, gamedata.GameDataError) else (
            f"生成数据失败 / failed to generate data: {e!r}\n请把 data\\app.log 发给作者 / please send data\\app.log to the author.")
        print(msg, file=sys.stderr, flush=True)
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, msg, "DeckBench", 0x10)
            except Exception:
                pass
        sys.exit(2)
    close()


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("--worker", "--probe-clr"):
        # 子进程：出错时把堆栈写到 stderr 并以非 0 退出（打包的无窗口 exe 否则会弹出「Unhandled exception」对话框并卡住）
        try:
            if argv[0] == "--worker":
                from gui import worker
                worker.main(argv[1:])
            else:
                import pythonnet
                pythonnet.load(argv[1], **_clr_kwargs(argv[1]))
                import clr
                clr.AddReference("System.Windows.Forms")
        except SystemExit:
            raise
        except BaseException:
            import traceback
            traceback.print_exc()
            try:
                sys.stderr.flush()
                sys.stdout.flush()
            except Exception:
                pass
            os._exit(1)
        return
    _ensure_game_or_exit()
    port = free_port()
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--serve" in argv:
        print(f"http://127.0.0.1:{port}/", flush=True)
        serve(port)
        return
    url = f"http://127.0.0.1:{port}/"
    server = serve(port, block=False)
    use_browser = "--browser" in argv
    if not use_browser:
        try:
            if not _setup_clr():
                raise RuntimeError("no usable .NET runtime for the window")
            import webview
        except Exception as e:  # noqa
            print(f"独立窗口不可用（{e}），改用浏览器打开", file=sys.stderr, flush=True)
            use_browser = True
    if not use_browser:
        try:
            webview.create_window("DeckBench", url, width=1360, height=860, min_size=(1100, 700),
                                  background_color="#131315")
            webview.start()
        except Exception as e:  # noqa
            print(f"独立窗口启动失败（{e}），改用浏览器打开", file=sys.stderr, flush=True)
            use_browser = True
    if use_browser:
        import webbrowser
        webbrowser.open(url)
        print(f"界面已在浏览器打开：{url}（关闭这个窗口即退出）", flush=True)
        # 浏览器模式没有窗口可关：页面每 5 秒 ping 一次，关掉页面 90 秒后自动退出
        from gui.server import LAST_PING
        t0 = time.time()
        try:
            while True:
                time.sleep(2)
                last = LAST_PING[0] or t0
                if time.time() - last > 90 and time.time() - t0 > 120:
                    break
        except KeyboardInterrupt:
            pass
    from gui.server import jobs
    jobs.shutdown()
    server.should_exit = True


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
