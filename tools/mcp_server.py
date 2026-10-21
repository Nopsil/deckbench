"""DeckBench / sts2-sim 的 MCP 服务器：让任意 MCP 客户端（Grok、Claude、Cursor…）一步一步打一局模拟器。

启动：
  stdio：        python tools/mcp_server.py
  streamable-HTTP：python tools/mcp_server.py --http --port 8765      # http://127.0.0.1:8765/mcp
  只绑 127.0.0.1（--host 可改）；经隧道/反代暴露给远程连接器时加 --no-host-check（关闭 DNS rebinding 的 Host 校验）。
每局一个子进程（tools/sim_session.py），存档目录 DECKBENCH_MCP_RUNS（默认 <缓存目录>/mcp_runs/<run_id>/）：
  meta.json（种子/角色/进阶/风格）、choices.json（每个决策的选项号+理由，可原样重放）、decisions.jsonl（decision_log 逐步日志）、
  replay.md（人能读的操作清单，照着在真游戏里复刻）
同一种子 + 同一串选项号 = 同一局，所以撤销/恢复都是「重开子进程 + 重放前 n 步」，服务器重启后也能 open_run 接着打。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sts2sim.engine.seed import canonicalize, warnings as seed_warnings  # noqa: E402

RUNS = os.environ.get("DECKBENCH_MCP_RUNS") or os.path.join(__import__("sts2sim.gamedata").gamedata.cache_root(), "mcp_runs")
CHARS = ["Ironclad", "Silent", "Defect", "Necrobinder", "Regent"]
PERSONAS = {
    "qianwen": "千问娘：国风元气大小姐，爱冒险、嘴硬，理由用一句不超过 30 字的俏皮中文台词。",
    "lirixuan": ("JUGGLING 流铁甲战士风格（参考一位中文主播的公开打法）：JUGGLING 见到就拿、商店必买、火堆先升级 JUGGLING 拿固有；"
                 "攻击优先、少拿防御，删牌先删防御；偏爱 ANGER、SPITE、BLUDGEON、THRASH、PERFECTED_STRIKE、SETUP_STRIKE、BOLAS、OFFERING、"
                 "BLOODLETTING、STOKE、PILLAGE、EXPECT_A_FIGHT，遗物偏爱 SNECKO_EYE / FAKE_SNECKO_EYE / BRIMSTONE；路线多冲精英；"
                 "出牌先打 JUGGLING，把最强的攻击留作本回合第 3 张。auto 代打也按这个风格。"),
}
LOCK = threading.Lock()


class Session:
    def __init__(self, run_id, meta):
        self.id = run_id
        self.dir = os.path.join(RUNS, run_id)
        self.meta = meta
        self.choices = []      # [{"n","choice","reason","source","label","screen","floor"}]
        self.proc = None
        self.pending = None    # 当前等待回复的 decision
        self.ended = None
        os.makedirs(self.dir, exist_ok=True)

    # ---- 子进程 ----
    def start(self, replay=None):
        self.kill()
        replay = self.choices if replay is None else replay
        rp = os.path.join(self.dir, "replay_in.json")
        with open(rp, "w", encoding="utf-8") as f:
            json.dump([{"choice": c["choice"], "reason": c.get("reason")} for c in replay], f, ensure_ascii=False)
        old = {c["n"]: c for c in replay}
        self.choices, self.pending, self.ended = [], None, None
        m = self.meta
        cmd = [sys.executable, os.path.join(HERE, "sim_session.py"), "--char", m["char"], "--asc", str(m["asc"]),
               "--seed", m["seed"], "--log", os.path.join(self.dir, "decisions.jsonl"), "--replay", rp,
               "--persona", m.get("persona_text") or "", "--fallback", m.get("fallback", "learned"), "--style", m.get("style", "")]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(os.path.join(self.dir, "engine.err"), "a"), text=True, bufsize=1,
                                     cwd=ROOT, env=dict(os.environ, PYTHONPATH=ROOT))
        self._read_until_decision(old)
        self.save()

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def _read_until_decision(self, old=None):
        """读子进程输出直到下一个决策 / 结束；顺路收 ack。返回本次收到的 ack 列表。"""
        acks = []
        last_dec = self.pending
        while True:
            line = self.proc.stdout.readline()
            if not line:
                self.ended = self.ended or {"type": "fatal", "error": "引擎进程意外退出（见 engine.err）"}
                self.pending = None
                return acks
            d = json.loads(line)
            t = d.get("type")
            if t == "decision":
                if d.get("error") and last_dec is not None and d["n"] == last_dec["n"]:
                    self.pending = d
                    return acks
                self.pending = last_dec = d
                if old is not None and d["n"] in old:
                    continue        # 重放中：子进程会自己按 replay 走，不会停在这里
                return acks
            if t == "ack":
                dec = last_dec or {}
                c = {"n": d["n"], "choice": d["choice"], "reason": d.get("reason"), "source": d.get("source"),
                     "label": d.get("label"), "screen": dec.get("screen"), "floor": _floor(dec.get("text", ""))}
                if old and d["n"] in old:      # 重放的决策：界面/层数/来源沿用原记录
                    o = old[d["n"]]
                    c.update(screen=o.get("screen"), floor=o.get("floor"))
                    if o.get("source") not in (None, "replay"):
                        c["source"] = o["source"]
                self.choices.append(c)
                acks.append(c)
                continue
            if t in ("end", "fatal"):
                self.ended, self.pending = d, None
                return acks

    def reply(self, msg):
        if self.pending is None:
            raise RuntimeError("这一局已经结束了" if self.ended else "没有等待中的决策")
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        n0 = self.pending["n"]
        acks = self._read_until_decision()
        self.save()
        if not acks and self.pending is not None and self.pending["n"] == n0:
            return None, self.pending.get("error")
        return acks, None

    def info(self, cmd):
        if self.pending is None:
            return "这一局没有在进行（已结束或未启动）"
        self.proc.stdin.write(json.dumps({"cmd": cmd}) + "\n")
        self.proc.stdin.flush()
        d = json.loads(self.proc.stdout.readline())
        return d.get("text", "")

    # ---- 存档 ----
    def save(self):
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({**self.meta, "id": self.id, "n_choices": len(self.choices),
                       "ended": self.ended, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=1)
        with open(os.path.join(self.dir, "choices.json"), "w", encoding="utf-8") as f:
            json.dump(self.choices, f, ensure_ascii=False, indent=0)
        with open(os.path.join(self.dir, "replay.md"), "w", encoding="utf-8") as f:
            m = self.meta
            f.write(f"# {m['char']} A{m['asc']} 种子 {m['seed']}（自定义模式输入这个种子，不勾修改器）\n\n")
            f.write("| # | 层 | 界面 | 选择 | 理由 | 来源 |\n|---|---|---|---|---|---|\n")
            for c in self.choices:
                lab = c["label"] if isinstance(c["label"], str) else "；".join(c["label"] or [])
                f.write(f"| {c['n']} | {c.get('floor') or ''} | {c.get('screen')} | {lab} | {(c.get('reason') or '').replace('|', '/')} | {c.get('source')} |\n")
            if self.ended:
                f.write(f"\n结局：{json.dumps(self.ended, ensure_ascii=False)}\n")

    @classmethod
    def load(cls, run_id):
        d = os.path.join(RUNS, run_id)
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        s = cls(run_id, {k: meta[k] for k in ("seed", "char", "asc", "persona", "persona_text", "fallback", "style", "created") if k in meta})
        s.choices = json.load(open(os.path.join(d, "choices.json"), encoding="utf-8"))
        return s


def _floor(text):
    import re
    m = re.search(r"第(\d+)幕 第(\d+)层", text or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


SESS = {}
CUR = {"id": None}


def _get(run_id=None):
    rid = run_id or CUR["id"]
    if not rid:
        raise ValueError("还没有对局：先 new_run 或 open_run")
    if rid not in SESS:
        s = Session.load(rid)
        s.start()
        SESS[rid] = s
    CUR["id"] = rid
    return SESS[rid]


def _state_text(s):
    if s.pending is not None:
        t = s.pending["text"]
        if s.pending.get("error"):
            t = f"⚠ 上一个回复无效：{s.pending['error']}\n" + t
        return f"run_id={s.id} 决策 #{s.pending['n']} 界面={s.pending['screen']}\n{t}"
    e = s.ended or {}
    if e.get("type") == "fatal":
        return f"run_id={s.id} 引擎出错：{e.get('error')}"
    return (f"run_id={s.id} 本局结束：{'胜利！' if e.get('victory') else '失败'} 第{e.get('floor')}层 HP {e.get('hp')}/{e.get('max_hp')}"
            + (f" 死于 {e.get('death_room')}" if e.get('death_room') else "")
            + _end_lists(e) + (f"\n引擎错误：{e['error'][:500]}" if e.get("error") else ""))


def _end_lists(e):
    from collections import Counter

    def nm(i):
        base = i.rstrip("+")
        z = _zh_title(base)
        return (z[0] if z else base) + ("+" if i.endswith("+") else "")
    rel = e.get("relics") or []
    deck = Counter(e.get("deck") or [])
    out = f"\n遗物（{len(rel)}）：" + ("、".join(nm(r) for r in rel) or "无")
    out += f"\n牌组（{sum(deck.values())}）：" + "、".join(f"{nm(k)}×{v}" if v > 1 else nm(k) for k, v in sorted(deck.items(), key=lambda x: (-x[1], x[0])))
    return out



# ---------------------------------------------------------------- 按文字/ID 选选项
def _zh_title(ident):
    """卡牌/遗物/药水/能力/怪物 ID → 中文名（运行时从玩家本机的游戏安装读，sts2sim/gameloc.py；不入库）。"""
    from sts2sim import gameloc
    out = []
    for tb in ("cards", "relics", "potions", "powers", "monsters"):
        t = gameloc.table(tb, "zhs") or {}
        v = t.get(f"{ident}.title") or t.get(f"{ident}.name")
        if isinstance(v, str):
            out.append(v)
    return out


def _in_order(k, x):
    """「STRIKE → #1」这类：按空白切开后各段依次出现在选项里。"""
    pos = 0
    for tok in k.split():
        j = x.find(tok, pos)
        if j < 0:
            return False
        pos = j + len(tok)
    return True


def match_option(text, labels, enabled=None):
    """返回 (下标, None) 或 (None, 错误)。顺序：纯数字=选项号；完全相同；以它开头；包含（大小写不敏感，支持 ID → 中文名）。"""
    t = text.strip()
    en = set(range(len(labels))) if enabled is None else set(enabled)
    if re.fullmatch(r"\d+", t):
        i = int(t)
        return (i, None) if i in en else (None, f"选项 {i} 不可选")
    keys = [t]
    up = t.upper()
    plus = up.endswith("+")
    if re.fullmatch(r"[A-Z0-9_]+\+?", up):
        keys += [z + ("+" if plus else "") for z in _zh_title(up.rstrip("+"))]
    lab = [(i, str(labels[i])) for i in sorted(en) if i < len(labels)]

    def strip_idx(x):          # 战斗选项「打出 h0 <牌名>(1费) → #0 X」去掉 h0 便于按牌名匹配
        return re.sub(r"\bh\d+\s*", "", x)
    for k in keys:
        kl = k.lower()
        for test in (lambda x: x.lower() == kl, lambda x: x.lower().startswith(kl),
                     lambda x: strip_idx(x).lower().startswith("打出 " + kl), lambda x: kl in x.lower(),
                     lambda x: kl in strip_idx(x).lower(), lambda x: _in_order(kl, x.lower())):
            hit = [i for i, x in lab if test(x)]
            if hit:
                return hit[0], None
    return None, f"没有和「{t}」匹配的可选项（可用选项号，或选项里的文字/牌名/ID）"


# ---------------------------------------------------------------- MCP 工具
def build(host="127.0.0.1", port=8765, host_check=True):
    from mcp.server.fastmcp import FastMCP
    kw = {}
    if not host_check:
        from mcp.server.transport_security import TransportSecuritySettings
        kw["transport_security"] = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp = FastMCP("deckbench-sim", instructions=(
        "《杀戮尖塔2》v0.111 整局模拟器（转译自游戏代码，种子和真游戏一致）。流程：new_run → 循环 get_state / act(选项号, 理由)。"
        "每一步都是编号选项；战斗里每次出一张牌或用一瓶药水也算一步。auto 可以把若干步交给内置 AI。"
        "同一种子 + 同一串选项 = 同一局，replay.md 可以拿去真游戏里照着复刻。"), host=host, port=port, **kw)

    @mcp.tool()
    def new_run(seed: str, character: str = "Ironclad", ascension: int = 0, persona: str = "") -> str:
        """开新的一局。seed：游戏里的种子（自动按游戏规则规范化：大写、O→0、I→1）；character：Ironclad/Silent/Defect/Necrobinder/Regent；
        ascension：0-10；persona：可选风格，qianwen（千问娘）/ lirixuan（JUGGLING 流铁甲：JUGGLING 必拿、攻击优先、冲精英；auto 代打也用这个风格）/ 或直接写一段风格说明。返回第一个决策。"""
        with LOCK:
            if character not in CHARS:
                return f"角色只能是 {CHARS}"
            c = canonicalize(seed)
            rid = time.strftime("%m%d-%H%M%S") + "-" + c[:12] + "-" + uuid.uuid4().hex[:4]
            ptext = PERSONAS.get(persona, persona)
            s = Session(rid, {"seed": c, "char": character, "asc": int(ascension), "persona": persona, "persona_text": ptext,
                              "fallback": "learned", "style": "lirixuan" if persona == "lirixuan" else "", "created": time.strftime("%Y-%m-%d %H:%M:%S")})
            s.start(replay=[])
            SESS[rid] = s
            CUR["id"] = rid
            w = seed_warnings(seed, c)
            return ("\n".join("注意：" + x for x in w) + "\n" if w else "") + _state_text(s)

    @mcp.tool()
    def get_state(run_id: str = "") -> str:
        """当前局面（层数/HP/金币/牌组/遗物/药水、界面、战斗里的手牌/能量/敌人意图）和编号选项。run_id 留空 = 最近一局。"""
        with LOCK:
            return _state_text(_get(run_id or None))

    @mcp.tool()
    def act(option_index: int = -1, reason: str = "", indices: list[int] | None = None, run_id: str = "",
            option: str = "") -> str:
        """做一个决定：option_index = 选项号（多选界面用 indices=[…]）；或 option = 选项文字/牌名/ID（比选项号稳定，
        例 option="JUGGLING"、option="STRIKE_IRONCLAD → #1"、option="跳过"；多个匹配取第一个可选项）。
        reason = 简短中文理由（写进日志）。返回结果和下一个决策。"""
        with LOCK:
            s = _get(run_id or None)
            choice = indices if indices is not None else option_index
            if option and indices is None:
                if s.pending is None:
                    return _state_text(s)
                idx, msg = match_option(option, s.pending.get("options") or [], s.pending.get("enabled"))
                if idx is None:
                    return f"❌ {msg}\n" + _state_text(s)
                choice = idx
            acks, err = s.reply({"choice": choice, "reason": reason})
            if err:
                return f"❌ {err}\n" + _state_text(s)
            done = "；".join(f"#{a['n']} {a['label'] if isinstance(a['label'], str) else a['label']}" for a in acks)
            return f"✔ {done}\n\n" + _state_text(s)

    @mcp.tool()
    def auto(steps: int = 1, until: str = "", run_id: str = "") -> str:
        """把接下来的决策交给内置 AI（learned）。steps：最多几步；until：可选 combat_end（打完当前战斗）/ floor（到下一层）/ screen:<名>（停在某种界面，如 screen:card_reward）。"""
        with LOCK:
            s = _get(run_id or None)
            if s.pending is None:
                return _state_text(s)
            start_floor = _floor(s.pending["text"])
            n = 0
            limit = max(1, min(int(steps), 2000)) if not until else 2000
            while s.pending is not None and n < limit:
                in_combat = s.pending["screen"] == "combat"
                s.reply({"auto": True})
                n += 1
                if s.pending is None:
                    break
                if until == "combat_end" and in_combat and s.pending["screen"] != "combat":
                    break
                if until == "floor" and _floor(s.pending["text"]) != start_floor:
                    break
                if until.startswith("screen:") and s.pending["screen"] == until[7:]:
                    break
            return f"内置 AI 走了 {n} 步。\n\n" + _state_text(s)

    @mcp.tool()
    def get_map(run_id: str = "") -> str:
        """当前幕的完整地图（文字画，和游戏画面同方向）+ 当前位置。"""
        with LOCK:
            return _get(run_id or None).info("map")

    @mcp.tool()
    def get_deck(run_id: str = "") -> str:
        """完整牌组，每张带费用和说明。"""
        with LOCK:
            return _get(run_id or None).info("deck")

    @mcp.tool()
    def undo(steps: int = 1, run_id: str = "") -> str:
        """撤销最近 steps 个决策（重开并重放，确定性的）。"""
        with LOCK:
            s = _get(run_id or None)
            k = max(0, len(s.choices) - max(1, int(steps)))
            s.start(replay=s.choices[:k])
            return f"已回到决策 #{k}。\n\n" + _state_text(s)

    @mcp.tool()
    def restore(step: int, run_id: str = "") -> str:
        """回到第 step 个决策之前（step=0 = 开局）。"""
        with LOCK:
            s = _get(run_id or None)
            k = max(0, min(int(step), len(s.choices)))
            s.start(replay=s.choices[:k])
            return f"已回到决策 #{k}。\n\n" + _state_text(s)

    @mcp.tool()
    def get_log(last: int = 20, run_id: str = "") -> str:
        """最近 last 个决策：编号、层、界面、选择、理由、来源（external=你选的 / auto=内置 AI）。"""
        with LOCK:
            s = _get(run_id or None)
            rows = s.choices[-max(1, int(last)):]
            return "\n".join(f"#{c['n']} [{c.get('floor')}] {c.get('screen')}：{c['label']} —— {c.get('reason') or ''}（{c.get('source')}）"
                             for c in rows) or "还没有决策"

    @mcp.tool()
    def export_log(run_id: str = "") -> str:
        """导出本局：返回文件路径（decisions.jsonl 逐步日志、choices.json 可重放选项、replay.md 真游戏复刻清单）和简要统计。"""
        with LOCK:
            s = _get(run_id or None)
            s.save()
            src = {}
            for c in s.choices:
                src[c.get("source")] = src.get(c.get("source"), 0) + 1
            return json.dumps({"run_id": s.id, "dir": s.dir, "files": {k: os.path.join(s.dir, k) for k in
                               ("decisions.jsonl", "choices.json", "replay.md", "meta.json")},
                               "seed": s.meta["seed"], "char": s.meta["char"], "asc": s.meta["asc"], "decisions": len(s.choices),
                               "by_source": src, "ended": s.ended}, ensure_ascii=False, indent=1)

    @mcp.tool()
    def list_runs() -> str:
        """列出所有对局（含已结束的、服务器重启前的）。"""
        out = []
        if os.path.isdir(RUNS):
            for rid in sorted(os.listdir(RUNS)):
                p = os.path.join(RUNS, rid, "meta.json")
                if os.path.exists(p):
                    m = json.load(open(p, encoding="utf-8"))
                    e = m.get("ended") or {}
                    st = ("胜利" if e.get("victory") else f"失败@{e.get('floor')}") if e.get("type") == "end" else ("出错" if e else "进行中")
                    out.append(f"{rid} | {m['char']} A{m['asc']} 种子 {m['seed']} | {m.get('n_choices', 0)} 步 | {st}"
                               + (" | 当前" if rid == CUR["id"] else ""))
        return "\n".join(out) or "还没有对局"

    @mcp.tool()
    def open_run(run_id: str) -> str:
        """切换到某一局（服务器重启后会按 choices.json 重放恢复）。"""
        with LOCK:
            return _state_text(_get(run_id))

    return mcp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true", help="streamable-HTTP（默认 stdio）")
    ap.add_argument("--host", default=os.environ.get("DECKBENCH_MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DECKBENCH_MCP_PORT", "8765")))
    ap.add_argument("--no-host-check", action="store_true", help="关闭 Host 头校验（经隧道/反代给远程连接器用）")
    a = ap.parse_args()
    from sts2sim import gamedata
    gamedata.require()   # 没有本机生成的数据 / 安装不匹配 → 打印说明并退出（stdout 留给 MCP 协议，说明写 stderr）
    mcp = build(a.host, a.port, host_check=not a.no_host_check)
    try:
        mcp.run(transport="streamable-http" if a.http else "stdio")
    finally:
        for s in SESS.values():
            s.kill()


if __name__ == "__main__":
    main()
