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

from . import i18n, metrics, paths

# AI 列表：名字和说明在 gui/locales/<lang>.json 的 agent.<id>.name / .desc（随界面语言）
AGENTS_BATCH = ["heuristic", "modai", "modai-boss", "learned", "learned-search", "learned-boss", "strong-nosearch", "strong", "search"]
if os.name == "nt":
    # 「搜索」类 AI 用 os.fork() 给游戏状态拍快照，Windows 没有 fork，只能用不搜索的几种
    AGENTS_BATCH = [a for a in AGENTS_BATCH if a in ("heuristic", "modai", "learned", "strong-nosearch")]
MENTOR_AGENTS = ["mentor-full", "mentor-full-ev"]


def mentor_configured():
    """外部 spire-mentor 是否已配置（只看目录，不在界面进程里导入它）。"""
    site, py = os.environ.get("DECKBENCH_MENTOR_SITE", ""), os.environ.get("DECKBENCH_MENTOR_PY", "")
    return bool(site and py and os.path.isdir(os.path.join(site, "sts2_rs")) and os.path.isdir(os.path.join(py, "sts2_hint")))


def _agent(prefix, aid, lang):
    return {"id": aid, "name": i18n.t(f"{prefix}.{aid}.name", lang), "desc": i18n.t(f"{prefix}.{aid}.desc", lang)}


def agents_batch(lang=None):
    ok = mentor_configured()
    out = [_agent("agent", a, lang) for a in AGENTS_BATCH]
    for a in MENTOR_AGENTS:
        out.append({**_agent("agent", a, lang), "available": ok, "hint": "" if ok else i18n.t("agent.mentorHint", lang)})
    return out


AGENTS_COMBAT = ["heuristic", "beam"]


def agents_combat(lang=None):
    return [_agent("agentc", a, lang) for a in AGENTS_COMBAT]


# 简体中文回退名（游戏文本读不到时用；其他语言回退到英文 ID）
CHAR_ZH = {"Ironclad": "铁甲战士", "Silent": "静默猎手", "Defect": "故障机器人", "Necrobinder": "亡灵契约师",
           "Regent": "储君", "Claude": "Claude娘"}
ROOMS = ["普通", "精英", "首领", "弱怪"]   # 房间 ID（战斗实验 YAML 里就是这些字）；界面显示用 room.<ID> 翻译


def char_name(cid, lang=None):
    """角色名：我们自己的 mod 角色用翻译表；原版角色从你的游戏安装按所选语言读（characters 表），读不到再回退。"""
    lang = lang or i18n.current()
    if i18n.has(f"char.{cid}", lang):
        return i18n.t(f"char.{cid}", lang)
    v = i18n.game_text("characters", str(cid).upper(), lang)
    if v:
        return v
    return CHAR_ZH.get(cid, cid) if lang == "zhs" else cid


class SimBackend:
    """后端接口。"""
    id = "base"
    name = "未命名后端"

    def capabilities(self, lang=None):
        raise NotImplementedError

    def catalog(self, refresh=False, lang=None):
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

    def capabilities(self, lang=None):
        return {"batch": True, "combat": True, "yaml_mods": True, "dll_mods": False,
                "engine": i18n.t("backend.engine", lang)}

    # ---------------- 目录：角色、AI、变体、卡牌、实验预设、mod
    CARDS_CACHE_VERSION = 2   # 2：卡牌带 rarity_id/type_id/own_name，名字按界面语言在 catalog() 里填

    def _cards(self, refresh=False):
        cache = os.path.join(paths.CACHE_DIR, "cards.json")
        src = os.path.join(paths.SIM_ROOT, "mods", "claude_v35", "cards_v35.py")
        if not refresh and os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(src):
            try:
                d = json.load(open(cache, encoding="utf-8"))
                if d.get("version") == self.CARDS_CACHE_VERSION:
                    return d
            except ValueError:
                pass
        p = subprocess.run(worker_argv("cards"), env=worker_env(), cwd=paths.SIM_ROOT, capture_output=True,
                           text=True, encoding="utf-8", timeout=300, **_no_window())
        if p.returncode != 0:
            raise RuntimeError(i18n.t("backend.cardsFailed") + "\n" + p.stderr[-2000:])
        d = json.loads(p.stdout.strip().splitlines()[-1])
        d["version"] = self.CARDS_CACHE_VERSION
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

    def experiments(self, lang=None):
        out = []
        for f in sorted(glob.glob(os.path.join(paths.SIM_ROOT, "experiments", "*.yaml"))):
            try:
                e = yaml.safe_load(open(f, encoding="utf-8")) or {}
            except Exception:
                continue
            eid = os.path.basename(f)[:-5]
            title = i18n.t(f"preset.{eid}", lang) if i18n.has(f"preset.{eid}", lang) else (e.get("title") or e.get("name"))
            out.append({"id": eid, "name": e.get("name"), "title": title,
                        "mods": e.get("mods", []), "decks": e.get("decks", []), "rooms": e.get("rooms", ["普通", "精英", "首领"]),
                        "fights": e.get("fights", 100), "max_turns": e.get("max_turns", 30), "agent": e.get("agent", "heuristic"),
                        "seed": e.get("seed", 1), "n_extra": len(e.get("extra") or [])})
        return out

    def encounter_names(self, lang=None):
        """遭遇/事件 ID → 名字（死因图用）：按所选语言从你的游戏安装读，缺的回退英文、中文；
        再缺就用 spire-codex 导出（如果你导出过）；都没有界面显示 ID。"""
        lang = lang or i18n.current()
        out = {}
        try:
            from sts2sim import gameloc
            for g in reversed(i18n.game_langs(lang)):        # 先放回退语言，再用所选语言覆盖
                for tb in ("events", "encounters"):
                    for k, v in (gameloc.table(tb, g) or {}).items():
                        if k.endswith(".title") and isinstance(v, str) and v.strip():
                            out[k[:-6]] = v
        except Exception:  # noqa
            pass
        codex = __import__("sts2sim.gamedata").gamedata.codex_dir()
        for pre in (["zhs", "eng"] if lang == "zhs" else ["eng", "zhs"]):
            try:
                for e in json.load(open(os.path.join(codex, f"{pre}_encounters.json"), encoding="utf-8")):
                    out.setdefault(e["id"], e["name"])
            except Exception:  # noqa
                pass
        return out

    def card_names(self, ids, lang=None):
        """卡牌 ID → 名字：按所选语言从你的游戏安装读（cards 表），缺了回退英文、中文；简体中文再回退 spire-codex 导出。"""
        lang = lang or i18n.current()
        out = {}
        try:
            from sts2sim import gameloc
            tables = [gameloc.table("cards", g) or {} for g in i18n.game_langs(lang)]
        except Exception:  # noqa
            tables = []
        for cid in ids:
            for tb in tables:
                v = tb.get(f"{cid}.title")
                if isinstance(v, str) and v.strip():
                    out[cid] = v
                    break
        return out

    def catalog(self, refresh=False, lang=None):
        lang = lang if lang in i18n.LANGS else i18n.current()
        c = self._cards(refresh)
        chars = [{"id": k, "name": char_name(k, lang)} for k in c.get("characters", [])]
        names = self.card_names([x["id"] for x in c["cards"] if not x.get("own_name")], lang)
        cards = []
        for x in c["cards"]:
            x = dict(x)
            if not x.get("own_name"):
                # 没读到游戏文本：简体中文用 spire-codex 导出的名字（worker 已填），其他语言显示 ID
                x["name"] = names.get(x["id"]) or (x.get("name_codex") if lang == "zhs" else None) or x["id"]
            pool = x.get("pool", "")
            x["pool_name"] = char_name(pool, lang) if pool in c.get("characters", []) else i18n.tr("pool.", pool, lang)
            x["rarity"] = i18n.tr("rarity.", x.get("rarity_id", ""), lang)
            x["type"] = i18n.tr("ctype.", x.get("type_id", ""), lang)
            cards.append(x)
        # 变体说明：有翻译用翻译；简体中文用源码注释；其他语言没有翻译时显示参数本身（和语言无关）
        variants = [dict(v, desc=i18n.t(f"variant.{v['id']}", lang)) if i18n.has(f"variant.{v['id']}", lang)
                    else (v if lang == "zhs" else dict(v, desc="")) for v in c["variants"]]
        return {"backend": {"id": self.id, "name": i18n.t("backend.name", lang), **self.capabilities(lang)},
                "lang": lang, "game_langs": sorted(_game_langs()),
                "characters": chars, "agents_batch": agents_batch(lang), "agents_combat": agents_combat(lang),
                "variants": variants, "cards": cards, "starters": c["starters"], "rooms": ROOMS,
                "experiments": self.experiments(lang), "mods": self.mods(), "cpu": os.cpu_count() or 1,
                "encounters": self.encounter_names(lang)}

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
            if p.get("game_seed"):   # 指定真游戏种子：只打这一局，并写逐步决策日志到 <run_dir>/steps/
                argv += ["--game-seed", str(p["game_seed"]), "--log-dir", os.path.join(run_dir, "steps")]
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
            exp["title"] = p.get("title") or exp.get("title") or i18n.t("nt.customCombat")
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


def _game_langs():
    try:
        from sts2sim import gameloc
        return gameloc.languages()
    except Exception:  # noqa
        return set()


BACKENDS = {"local-python": LocalPythonBackend}


def get_backend(name="local-python"):
    return BACKENDS[name]()
