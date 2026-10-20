"""模拟器后端抽象层：界面只和 SimBackend 打交道。

第一期实现 LocalPythonBackend（本仓库的 Python 模拟器）；以后发布版的引擎（sts2-cli 分支，跑真实游戏 DLL）
只要实现同样的接口（catalog / build_command / summarize / ab）就能替换，界面不用改。
"""
import glob
import json
import os
import subprocess
import sys

import yaml

from . import metrics, paths

AGENTS_BATCH = [
    {"id": "heuristic", "name": "启发式（快）", "desc": "贪心逐动作模拟，最快；整局默认"},
    {"id": "learned", "name": "学习版 AI（推荐）", "desc": "强 AI + 自我对局学到的参数（CMA-ES），不搜索、速度同强 AI，Windows 可用"},
    {"id": "learned-search", "name": "学习版 AI（带搜索）", "desc": "学习版参数 + 精英/首领前瞻搜索；最强也最慢，仅 Linux/macOS"},
    {"id": "learned-boss", "name": "学习版 AI（只在首领战搜索）", "desc": "学习版参数，首领战用整场推演搜索；比全程搜索快，仅 Linux/macOS"},
    {"id": "strong-nosearch", "name": "强 AI（不搜索）", "desc": "首领感知的选牌/休息，单卡 A/B 常用（旧基线）"},
    {"id": "strong", "name": "强 AI（带搜索）", "desc": "最强也最慢"},
    {"id": "search", "name": "束搜索", "desc": "宽 6 深 1 的搜索 AI"},
]
if os.name == "nt":
    # 「搜索」类 AI 用 os.fork() 给游戏状态拍快照，Windows 没有 fork，只能用不搜索的两种
    AGENTS_BATCH = [a for a in AGENTS_BATCH if a["id"] in ("heuristic", "learned", "strong-nosearch")]
AGENTS_COMBAT = [
    {"id": "heuristic", "name": "启发式（快）", "desc": "贪心，不规划下回合"},
    {"id": "beam", "name": "束搜索", "desc": "宽 4 深 4，能找到需要铺引擎的组合，慢"},
]
CHAR_ZH = {"Ironclad": "铁甲战士", "Silent": "静默猎手", "Defect": "故障机器人", "Necrobinder": "亡灵契约师",
           "Regent": "储君", "Claude": "Claude娘"}
ROOMS = ["普通", "精英", "首领", "弱怪"]


class SimBackend:
    """后端接口。"""
    id = "base"
    name = "未命名后端"

    def capabilities(self):
        raise NotImplementedError

    def catalog(self, refresh=False):
        raise NotImplementedError

    def build_command(self, kind, params, run_dir):
        """返回 (argv, env, cwd)。kind: batch / combat。"""
        raise NotImplementedError

    def summarize(self, kind, run_dir):
        raise NotImplementedError

    def ab(self, kind, run_a, run_b):
        raise NotImplementedError


def worker_argv(*args):
    if paths.FROZEN:
        return [sys.executable, "--worker", *args]
    return [sys.executable, "-m", "gui.worker", *args]


def worker_env():
    env = dict(os.environ)
    gui_parent = os.path.dirname(paths.APP_DIR) if not paths.FROZEN else ""
    pp = [p for p in (paths.SIM_ROOT, gui_parent, env.get("PYTHONPATH", "")) if p]
    env["PYTHONPATH"] = os.pathsep.join(pp)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["STS2SIM_USER_MODS"] = paths.USER_MODS_DIR
    env["STS2SIM_ROOT"] = paths.SIM_ROOT
    return env


def _no_window():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


class LocalPythonBackend(SimBackend):
    id = "local-python"
    name = "内置 Python 模拟器"

    def __init__(self):
        self._catalog = None

    def capabilities(self):
        return {"batch": True, "combat": True, "yaml_mods": True, "dll_mods": False,
                "engine": "公测版 v0.111.0 转译引擎（整局）+ YAML 战斗模拟器"}

    # ---------------- 目录：角色、AI、变体、卡牌、实验预设、mod
    def _cards(self, refresh=False):
        cache = os.path.join(paths.CACHE_DIR, "cards.json")
        src = os.path.join(paths.SIM_ROOT, "mods", "claude_v35", "cards_v35.py")
        if not refresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
            return json.load(open(cache, encoding="utf-8"))
        p = subprocess.run(worker_argv("cards"), env=worker_env(), cwd=paths.SIM_ROOT, capture_output=True,
                           text=True, encoding="utf-8", timeout=300, **_no_window())
        if p.returncode != 0:
            raise RuntimeError("读取卡牌列表失败：\n" + p.stderr[-2000:])
        d = json.loads(p.stdout.strip().splitlines()[-1])
        os.makedirs(paths.CACHE_DIR, exist_ok=True)
        json.dump(d, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
        return d

    def mods(self):
        out = []
        for base, user in ((os.path.join(paths.SIM_ROOT, "mods"), False), (paths.USER_MODS_DIR, True)):
            for f in sorted(glob.glob(os.path.join(base, "*", "mod.yaml"))):
                d = os.path.dirname(f)
                try:
                    meta = yaml.safe_load(open(f, encoding="utf-8")) or {}
                except Exception as e:  # noqa
                    meta = {"_error": str(e)}
                decks = []
                for df in meta.get("decks", []) or []:
                    try:
                        for dk in yaml.safe_load(open(os.path.join(d, df), encoding="utf-8")) or []:
                            decks.append({"id": dk.get("id"), "name": dk.get("name", dk.get("id")), "character": dk.get("character"),
                                          "stage": dk.get("stage", ""), "acts": dk.get("acts", [1]), "expect": dk.get("expect"),
                                          "mod": os.path.basename(d), "n_cards": len(dk.get("cards", []))})
                    except Exception:
                        pass
                gm = {}
                if os.path.exists(os.path.join(d, "gui_meta.json")):
                    try:
                        gm = json.load(open(os.path.join(d, "gui_meta.json"), encoding="utf-8"))
                    except Exception:
                        pass
                out.append({"id": os.path.basename(d), "deps": gm.get("deps", []), "title": meta.get("title") or meta.get("name") or os.path.basename(d),
                            "user": user, "decks": decks,
                            "characters": {k: (v or {}).get("name", k) for k, v in (meta.get("characters") or {}).items()},
                            "n_card_files": len(meta.get("cards", []) or []), "hooks": bool(meta.get("hooks"))})
        return out

    def experiments(self):
        out = []
        for f in sorted(glob.glob(os.path.join(paths.SIM_ROOT, "experiments", "*.yaml"))):
            try:
                e = yaml.safe_load(open(f, encoding="utf-8")) or {}
            except Exception:
                continue
            out.append({"id": os.path.basename(f)[:-5], "name": e.get("name"), "title": e.get("title") or e.get("name"),
                        "mods": e.get("mods", []), "decks": e.get("decks", []), "rooms": e.get("rooms", ["普通", "精英", "首领"]),
                        "fights": e.get("fights", 100), "max_turns": e.get("max_turns", 30), "agent": e.get("agent", "heuristic"),
                        "seed": e.get("seed", 1), "n_extra": len(e.get("extra") or [])})
        return out

    def encounter_names(self):
        f = os.path.join(__import__("sts2sim.gamedata").gamedata.codex_dir(), "zhs_encounters.json")
        try:
            return {e["id"]: e["name"] for e in json.load(open(f, encoding="utf-8"))}
        except Exception:
            return {}

    def catalog(self, refresh=False):
        c = self._cards(refresh)
        chars = [{"id": k, "name": CHAR_ZH.get(k, k)} for k in c.get("characters", [])]
        return {"backend": {"id": self.id, "name": self.name, **self.capabilities()},
                "characters": chars, "agents_batch": AGENTS_BATCH, "agents_combat": AGENTS_COMBAT,
                "variants": c["variants"], "cards": c["cards"], "starters": c["starters"], "rooms": ROOMS,
                "experiments": self.experiments(), "mods": self.mods(), "cpu": os.cpu_count() or 1,
                "encounters": self.encounter_names()}

    # ---------------- 运行
    def build_command(self, kind, params, run_dir):
        p = params
        if kind == "batch":
            out = os.path.join(run_dir, "runs.jsonl")
            argv = worker_argv("batch", "--char", str(p.get("char", "Claude")), "--asc", str(int(p.get("asc", 0))),
                               "--n", str(int(p.get("n", 20))), "--start", str(int(p.get("start", 0))),
                               "--procs", str(int(p.get("procs") or os.cpu_count() or 1)), "--agent", p.get("agent", "heuristic"),
                               "--variant", "+".join(p.get("variants") or []), "--force", ",".join(p.get("force") or []),
                               "--replace", ",".join(p.get("replace") or []), "--out", out)
            return argv, worker_env(), paths.SIM_ROOT
        if kind == "combat":
            exp = {}
            if p.get("preset"):
                exp = yaml.safe_load(open(os.path.join(paths.SIM_ROOT, "experiments", p["preset"] + ".yaml"), encoding="utf-8"))
            if not p.get("preset") or p.get("custom"):
                exp.update({"mods": p["mods"], "decks": p["decks"], "rooms": p.get("rooms") or ["普通", "精英", "首领"],
                            "max_turns": int(p.get("max_turns", 30))})
                exp.pop("groups", None)
                exp.pop("extra", None)
                exp.pop("summary_md", None)
            exp["name"] = exp.get("name") or "gui_" + os.path.basename(run_dir)
            exp["title"] = p.get("title") or exp.get("title") or "自定义战斗实验"
            exp["seed"] = int(p.get("seed", exp.get("seed", 1)))
            exp["fights"] = int(p.get("fights", exp.get("fights", 50)))
            exp["agent"] = p.get("agent") or exp.get("agent", "heuristic")
            ef = os.path.join(run_dir, "experiment.yaml")
            yaml.safe_dump(exp, open(ef, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
            argv = worker_argv("combat", ef, "--jobs", str(int(p.get("procs") or os.cpu_count() or 1)),
                               "--out", os.path.join(run_dir, "out"))
            return argv, worker_env(), paths.SIM_ROOT
        raise ValueError(kind)

    def summarize(self, kind, run_dir):
        if kind == "batch":
            f = os.path.join(run_dir, "runs.jsonl")
            return metrics.batch_summary(metrics.load_jsonl(f)) if os.path.exists(f) else None
        if kind == "combat":
            d = os.path.join(run_dir, "out")
            return metrics.combat_summary(d) if os.path.isdir(d) else None
        return None

    def ab(self, kind, run_a, run_b):
        if kind == "batch":
            return metrics.batch_ab(metrics.load_jsonl(os.path.join(run_a, "runs.jsonl")),
                                    metrics.load_jsonl(os.path.join(run_b, "runs.jsonl")))
        return metrics.combat_ab(metrics.combat_summary(os.path.join(run_a, "out")),
                                 metrics.combat_summary(os.path.join(run_b, "out")))

    def validate_mod(self, name, deps):
        p = subprocess.run(worker_argv("validate-mod", name, "--deps", ",".join(deps), "--user-mods", paths.USER_MODS_DIR),
                           env=worker_env(), cwd=paths.SIM_ROOT, capture_output=True, text=True, encoding="utf-8",
                           timeout=300, **_no_window())
        if p.returncode != 0:
            return {"ok": False, "error": (p.stderr or p.stdout)[-3000:]}
        return json.loads(p.stdout.strip().splitlines()[-1])


BACKENDS = {"local-python": LocalPythonBackend}


def get_backend(name="local-python"):
    return BACKENDS[name]()
