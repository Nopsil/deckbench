"""First-run local generation of game-derived code/data, bound to the player's own install.

本项目不分发任何游戏文件、游戏数据或由游戏代码生成的代码。首次运行时从玩家本机已安装的游戏
（Steam 正式版或公开测试分支）里读取 sts2.dll，在本机反编译并转译成 Python，写入本机缓存。
缓存记录安装路径和 sts2.dll 的 SHA-256；每次加载都会重新校验，不匹配就拒绝加载。

    python -m sts2sim.gamedata setup [--game-dir PATH]   # 生成 / 重新生成
    python -m sts2sim.gamedata status                     # 查看当前缓存

环境变量：
    DECKBENCH_GAME_DIR   游戏安装目录（或直接含 sts2.dll 的目录），覆盖自动检测
    DECKBENCH_CACHE      缓存根目录（默认 %LOCALAPPDATA%/deckbench 或 ~/.cache/deckbench）
"""
import datetime
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
GAME_FOLDER = "Slay the Spire 2"        # Steam 安装目录名（仅用于在本机查找安装）
DLL = "sts2.dll"
FORMAT = 2

# 转译范围（与 tools/gen_game.sh 相同）
RELS = ("Commands Hooks Entities Combat MonsterMoves Factories Odds Rewards Map Random ValueProps Localization Models "
        "CardSelection Context Rooms Runs GameActions Helpers Events Exceptions Extensions Unlocks Timeline "
        "Multiplayer/Game/NetGameType.cs Multiplayer/Game/NetGameTypeExtensions.cs Multiplayer/Game/EventSynchronizer.cs "
        "Multiplayer/Game/RestSiteSynchronizer.cs Multiplayer/Game/RewardSynchronizer.cs Multiplayer/Game/OneOffSynchronizer.cs "
        "Multiplayer/Game/TreasureRoomRelicSynchronizer.cs Multiplayer/Game/RewardsSetSynchronizer.cs "
        "Modding/ModHelper.cs TestSupport/TestRngInjector.cs TestSupport/CardRewardSelection.cs "
        "Nodes/CommonUi/CardPreviewStyle.cs Animation/AnimState.cs").split()
EXCLUDE = ["RunManager", "MegaRandom"]


class GameDataError(RuntimeError):
    pass


NOT_FOUND_HELP = (
    "找不到游戏安装 / Game install not found.\n"
    "本工具不包含任何游戏文件，需要你自己已购买并安装的游戏（Steam 正式版或公开测试分支均可）。\n"
    "This tool ships no game files; it needs your own installed copy of the game (stable or public beta).\n"
    "  1) 安装游戏 / install the game via Steam\n"
    "  2) python -m sts2sim.gamedata setup --game-dir \"<...>/steamapps/common/" + GAME_FOLDER + "\"\n"
    "     或设置环境变量 / or set DECKBENCH_GAME_DIR")


# ---------------------------------------------------------------- 路径
def cache_root():
    env = os.environ.get("DECKBENCH_CACHE")
    if env:
        return env
    if os.name == "nt":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "deckbench")
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "deckbench")


def _steam_roots():
    roots = []
    if os.name == "nt":
        for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), r"C:\Program Files (x86)", r"C:\Program Files"):
            if pf:
                roots.append(os.path.join(pf, "Steam"))
        try:
            import winreg  # noqa
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            roots.insert(0, winreg.QueryValueEx(k, "SteamPath")[0])
        except Exception:
            pass
    else:
        for p in ("~/.steam/steam", "~/.local/share/Steam", "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
                  "~/Library/Application Support/Steam"):
            roots.append(os.path.expanduser(p))
    libs = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        libs.append(r)
        vdf = os.path.join(r, "steamapps", "libraryfolders.vdf")
        if os.path.exists(vdf):
            import re
            for m in re.finditer(r'"path"\s+"([^"]+)"', open(vdf, encoding="utf-8", errors="replace").read()):
                libs.append(m.group(1).replace("\\\\", "\\"))
    out = []
    for l in libs:
        if l not in out:
            out.append(l)
    return out


def candidate_dirs(game_dir=None):
    if game_dir:
        return [game_dir]
    if os.environ.get("DECKBENCH_GAME_DIR"):
        return [os.environ["DECKBENCH_GAME_DIR"]]
    return [os.path.join(l, "steamapps", "common", GAME_FOLDER) for l in _steam_roots()]


def find_dll(game_dir=None):
    """在安装目录里找 sts2.dll（Godot .NET 游戏一般在 data_*_* 子目录下）。找不到返回 None。"""
    for d in candidate_dirs(game_dir):
        if not os.path.isdir(d):
            continue
        if os.path.isfile(os.path.join(d, DLL)):
            return os.path.abspath(os.path.join(d, DLL))
        base = d.rstrip(os.sep).count(os.sep)
        for dp, dn, fn in os.walk(d):
            if dp.count(os.sep) - base >= 3:
                dn[:] = []
            if DLL in fn:
                return os.path.abspath(os.path.join(dp, DLL))
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _current_file():
    return os.path.join(cache_root(), "current.json")


# ---------------------------------------------------------------- 校验 / 加载
def verify():
    """返回已校验的缓存目录；缓存不存在、安装不见了或 sts2.dll 变了就抛 GameDataError。"""
    cf = _current_file()
    if not os.path.exists(cf):
        dll = find_dll()
        if dll is None:
            raise GameDataError(NOT_FOUND_HELP)
        raise GameDataError(f"已找到游戏 / found game: {dll}\n但还没生成本地数据 / local data not generated yet.\n"
                            "运行 / run:  python -m sts2sim.gamedata setup")
    cur = json.load(open(cf, encoding="utf-8"))
    d = cur.get("cache_dir", "")
    mf = os.path.join(d, "manifest.json")
    if not os.path.exists(mf):
        raise GameDataError(f"缓存损坏 / cache missing: {d}\n运行 / run:  python -m sts2sim.gamedata setup")
    m = json.load(open(mf, encoding="utf-8"))
    dll = m.get("dll_path")
    if not dll or not os.path.isfile(dll):
        raise GameDataError(f"缓存绑定的游戏安装不存在了 / the install this cache is bound to is gone: {dll}\n" + NOT_FOUND_HELP)
    if sha256(dll) != m.get("dll_sha256"):
        raise GameDataError("游戏已更新或文件不匹配，拒绝加载旧缓存 / game files changed; refusing to load stale cache.\n"
                            "重新生成 / regenerate:  python -m sts2sim.gamedata setup")
    if m.get("format") != FORMAT:
        raise GameDataError("缓存格式过旧 / cache format outdated. Run: python -m sts2sim.gamedata setup")
    return d


def ensure(interactive=True):
    """GUI / 首次运行：缓存可用就返回；找到了游戏但没生成就自动生成；找不到游戏就抛 GameDataError。"""
    try:
        return verify()
    except GameDataError:
        game_dir = None
        if find_dll() is None:
            game_dir = _previous_game_dir()   # 之前用 --game-dir 指定过的安装（例如游戏更新后自动重新生成）
            if game_dir is None or find_dll(game_dir) is None:
                raise GameDataError(NOT_FOUND_HELP)
        if interactive:
            print("首次运行：从你本机的游戏安装生成数据（几分钟）/ first run: generating data from your install ...", flush=True)
        return setup(game_dir)


def _previous_game_dir():
    try:
        d = json.load(open(_current_file(), encoding="utf-8"))["cache_dir"]
        return json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8")).get("game_dir")
    except Exception:
        return None


def require():
    """命令行入口用：校验失败时打印说明并退出（退出码 2）。"""
    try:
        return verify()
    except GameDataError as e:
        sys.stderr.write(str(e) + "\n")
        raise SystemExit(2)


def data_path(name):
    """本地生成的数据文件（monster_ai.json、encounter_monsters.json 等）。未生成时返回 None。"""
    try:
        p = os.path.join(verify(), name)
    except GameDataError:
        return None
    return p if os.path.exists(p) else None


def codex_dir():
    """旧版 YAML 战斗模拟器需要的 spire-codex 格式 JSON（eng_/zhs_ monsters、encounters、cards…）。
    不随仓库分发：由你用第三方工具 spire-codex 从自己的安装导出，放到 DECKBENCH_CODEX_DIR 或 data/spire-codex/（已 gitignore）。"""
    return os.environ.get("DECKBENCH_CODEX_DIR") or os.path.join(ROOT, "data", "spire-codex")


def require_codex():
    d = codex_dir()
    if not os.path.exists(os.path.join(d, "eng_monsters.json")):
        raise GameDataError(
            f"旧版 YAML 战斗模拟器需要本机导出的怪物/遭遇数据，未找到 / legacy combat simulator data not found: {d}\n"
            "见 README「旧版战斗模拟器」/ see README 'Legacy combat simulator'. 整局模拟不受影响 / full-run engine is unaffected.")
    return d


# ---------------------------------------------------------------- 生成
def _bundled_decompiler_dir():
    """打包版（Windows exe）自带的自包含反编译器目录：<exe 目录>/decompiler/（含 .NET 运行时，不需要装 .NET SDK）。"""
    cands = [os.path.join(os.path.dirname(ROOT), "decompiler")]
    if getattr(sys, "frozen", False):
        cands.insert(0, os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "decompiler"))
    for d in cands:
        for exe in ("ilspycmd-host.exe", "ilspycmd-host"):
            if os.path.isfile(os.path.join(d, exe)):
                return d, os.path.join(d, exe)
    return None, None


def _find_ilspy():
    """返回 (可执行文件, 框架引用目录或 None)。优先：DECKBENCH_ILSPY → 自带反编译器 → 系统里的 ilspycmd。"""
    env = os.environ.get("DECKBENCH_ILSPY")
    if env and os.path.exists(env):
        return env, os.environ.get("DECKBENCH_ILSPY_REFS") or None
    d, exe = _bundled_decompiler_dir()
    if exe:
        return exe, d          # 自包含发布目录里就是 .NET 9 运行时程序集，可直接作框架引用
    for c in (shutil.which("ilspycmd"), os.path.expanduser("~/.dotnet/tools/ilspycmd"),
              os.path.expanduser("~/.dotnet/tools/ilspycmd.exe")):
        if c and os.path.exists(c):
            return c, None
    return None, None


def _net9_dir():
    roots = [os.environ.get("DOTNET_ROOT"), os.path.expanduser("~/.dotnet"), r"C:\Program Files\dotnet",
             "/usr/share/dotnet", "/usr/lib/dotnet", "/usr/local/share/dotnet"]
    for r in roots:
        if r:
            hits = sorted(glob.glob(os.path.join(r, "shared", "Microsoft.NETCore.App", "9.*")))
            if hits:
                return hits[-1]
    return None


ILSPY_HELP = (
    "需要反编译器 ilspycmd 才能在本机读取你的游戏 / ilspycmd is required to read your game locally.\n"
    "打包版自带反编译器（decompiler 文件夹），请确认解压完整 / the packaged app ships one in the 'decompiler' folder; re-extract the zip.\n"
    "源码版 / source version:\n"
    "  1) 安装 .NET 9 SDK / install the .NET 9 SDK: https://dotnet.microsoft.com/download/dotnet/9.0\n"
    "  2) dotnet tool install -g ilspycmd --version 9.1.0.7988")


def _run(argv, **kw):
    print("  $", " ".join(argv[:4]), "..." if len(argv) > 4 else "", flush=True)
    if os.name == "nt":
        kw.setdefault("creationflags", 0x08000000)   # CREATE_NO_WINDOW：打包版不弹黑色控制台
    p = subprocess.run(argv, **kw)
    if p.returncode != 0:
        raise GameDataError(f"命令失败 / command failed ({p.returncode}): {argv[0]}")


def setup(game_dir=None, keep_src=False):
    dll = find_dll(game_dir)
    if dll is None:
        raise GameDataError(NOT_FOUND_HELP)
    bin_dir = os.path.dirname(dll)
    print("游戏 / game:", dll, flush=True)
    digest = sha256(dll)
    rel = {}
    ri = os.path.join(bin_dir, "release_info.json")
    if os.path.exists(ri):
        try:
            rel = json.load(open(ri, encoding="utf-8"))
        except Exception:
            rel = {}
    print("版本 / version:", rel.get("version", "?"), "branch:", rel.get("branch", "?"), "sha256:", digest[:16], flush=True)
    ilspy, refs = _find_ilspy()
    if ilspy is None:
        raise GameDataError(ILSPY_HELP)
    out_dir = os.path.join(cache_root(), digest[:16])
    tmp_out = out_dir + ".tmp"
    shutil.rmtree(tmp_out, ignore_errors=True)
    os.makedirs(tmp_out)
    src = tempfile.mkdtemp(prefix="deckbench-src-")
    try:
        argv = [ilspy, "-p", "--nested-directories", "-o", src]
        net9 = refs or _net9_dir()
        if net9:
            argv += ["-r", net9]
        else:
            print("警告：没找到 .NET 9 运行时，反编译质量可能下降 / warning: .NET 9 runtime not found", flush=True)
        argv += ["-r", bin_dir, dll]
        print("[1/3] 本机反编译 / decompiling locally ...", flush=True)
        _run(argv, stdout=subprocess.DEVNULL)
        core = os.path.join(src, "MegaCrit", "Sts2", "Core")
        if not os.path.isdir(core):
            raise GameDataError("反编译结果里没有预期的命名空间 / unexpected decompiler output layout")
        print("[2/3] 转译 / transpiling ...", flush=True)
        # 进程内调用（打包后的 exe 里 sys.executable 不是 python）
        if TOOLS not in sys.path:
            sys.path.insert(0, TOOLS)
        import cs2py_files  # noqa
        lim = sys.getrecursionlimit()
        sys.setrecursionlimit(max(lim, 10000))
        try:
            cs2py_files.run(core, os.path.join(tmp_out, "game.py"), RELS, EXCLUDE, os.path.join(tmp_out, "game_report.json"))
        finally:
            sys.setrecursionlimit(lim)
        import undefined_names  # noqa
        with open(os.path.join(tmp_out, "undefined.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(undefined_names.compute(os.path.join(tmp_out, "game.py"))) + "\n")
        print("[3/3] 解析怪物 / 遭遇 / parsing monsters & encounters ...", flush=True)
        old = os.environ.get("DECKBENCH_OUT")
        os.environ["DECKBENCH_OUT"] = tmp_out
        try:
            for mod, sub in (("parse_monster_ai", "Monsters"), ("parse_encounters", "Encounters")):
                try:
                    import contextlib
                    import io
                    with contextlib.redirect_stdout(io.StringIO()):
                        __import__(mod).main(os.path.join(core, "Models", sub))
                except Exception as e:  # noqa
                    print(f"  警告：{mod} 失败（只影响旧版 YAML 战斗模拟器）/ warning: {mod} failed: {e}", flush=True)
        finally:
            if old is None:
                os.environ.pop("DECKBENCH_OUT", None)
            else:
                os.environ["DECKBENCH_OUT"] = old
        if keep_src:
            shutil.copytree(src, os.path.join(tmp_out, "src"))
    finally:
        shutil.rmtree(src, ignore_errors=True)
    manifest = {"format": FORMAT, "game_dir": game_dir or os.path.dirname(dll), "dll_path": dll, "dll_sha256": digest,
                "release_info": rel, "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "note": "Generated locally from your own install. Do not redistribute. / 由你本机安装生成，请勿分发。"}
    json.dump(manifest, open(os.path.join(tmp_out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(tmp_out, "DO_NOT_REDISTRIBUTE.txt"), "w", encoding="utf-8").write(manifest["note"] + "\n")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp_out, out_dir)
    json.dump({"cache_dir": out_dir}, open(_current_file(), "w", encoding="utf-8"))
    print("完成 / done:", out_dir, flush=True)
    return out_dir


def status():
    try:
        d = verify()
    except GameDataError as e:
        print("未就绪 / not ready:\n" + str(e))
        return 1
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    print(json.dumps({k: m[k] for k in ("dll_path", "dll_sha256", "release_info", "generated_at")}, ensure_ascii=False, indent=1))
    print("cache:", d)
    return 0


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m sts2sim.gamedata")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="从本机安装生成数据 / generate from your install")
    s.add_argument("--game-dir")
    s.add_argument("--keep-src", action="store_true", help="保留本机反编译源码（调试用）")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return status()
    try:
        setup(a.game_dir, a.keep_src)
    except GameDataError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
