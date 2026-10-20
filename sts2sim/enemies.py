"""敌人：从 spire-codex 的 monsters.json / encounters.json 建模。

- 血量：在 [min_hp, max_hp] 里均匀取整（普通难度，不算进阶）。
- 招式：damage.normal × hit_count，block，powers（self / player），heal。
- 意图：按 attack_pattern 的状态机走：
    move 状态 → next；random 状态按 weight 抽，支持 CannotRepeat / UseOnlyOnce；
    conditional 状态：SlotName 条件按站位匹配，其他条件取第一个分支（近似，见报告近似清单）；
    没有 next 的 move 状态 → 在所有 move 状态里均匀随机（近似）。
- 特殊：Status 意图往玩家弃牌堆加 1 张「晕眩」（近似，数据里没有塞牌数量）；
  Summon 意图不召唤（近似）；Escape 意图直接离场；Stun/Sleep 不行动。
"""
import json
import os
import re
from .core import Creature, Power, register_power

from . import gamedata as _gd

DATA_DIR = _gd.codex_dir()   # 不随仓库分发，见 gamedata.codex_dir

APPROX = {}   # 运行中遇到的近似：key -> 说明


def note(key, msg):
    APPROX.setdefault(key, msg)


class Move:
    __slots__ = ("id", "name", "intent", "damage", "hits", "block", "powers", "heal", "status", "sets", "summons", "src")

    def __init__(self, raw):
        self.id = raw["id"]
        self.name = raw.get("name", self.id)
        self.intent = raw.get("intent") or "Unknown"
        d = raw.get("damage") or {}
        self.damage = d.get("normal") or 0
        self.hits = d.get("hit_count") or 1
        self.block = raw.get("block") or 0
        self.powers = [(p["power_id"], p.get("target", "self"), p.get("amount", 1)) for p in (raw.get("powers") or [])]
        self.heal = raw.get("heal") or 0
        self.status = []      # [(卡牌ID, 牌堆, 张数)]：来自反编译代码
        self.sets = {}        # 招式函数里改写的怪物字段（如 HasBeetleCharged = true）
        self.summons = False
        self.src = raw.get("_src", "数据")

    def is_attack(self):
        return self.damage > 0


class MonsterDef:
    def __init__(self, raw, zh_name=None):
        self.id = raw["id"]
        self.name = zh_name or raw["name"]
        self.hp_missing = not raw.get("min_hp")
        self.min_hp = raw.get("min_hp") or 1
        self.max_hp = raw.get("max_hp") or self.min_hp
        self.moves = {m["id"]: Move(m) for m in raw.get("moves") or []}
        self.innate = [(p["power_id"], p.get("amount", 1)) for p in (raw.get("innate_powers") or [])]
        ap = raw.get("attack_pattern") or {}
        self.pattern_type = ap.get("type")
        self.states = {s["id"]: s for s in ap.get("states", [])}
        self.initial = ap.get("initial_move")
        self.move_states = [s for s in ap.get("states", []) if s["type"] == "move" and s.get("move_id") in self.moves]
        self.by_move = {}
        for s in self.move_states:
            self.by_move.setdefault(s["move_id"], s["id"])
        self.ai = None          # 反编译代码里的状态机（见 attach_code_ai）
        self.ai_source = "数据" if self.states else "缺失"
        self.ai_notes = []

    def attach_code_ai(self, ai, key):
        """用 data/monster_ai.json（tools/parse_monster_ai.py 从反编译 C# 解析）替换 spire-codex 的 attack_pattern。
        招式数值优先用 spire-codex（同源、经过校对），代码里有而数据没有的招式用代码推出的数值。"""
        codex_state_move = {sid: st.get("move_id") for sid, st in self.states.items()}
        states = {}
        notes = []
        for sid, st in ai["states"].items():
            st = dict(st)
            if st["kind"] == "move":
                mid = codex_state_move.get(sid) or (sid[:-5] if sid.endswith("_MOVE") else sid)
                if mid in self.moves:
                    mv = self.moves[mid]
                    cm = st.get("code_move") or {}
                    if not mv.powers and cm.get("powers"):
                        mv.powers = [(p["power_id"], p.get("target", "self"), p.get("amount", 1)) for p in cm["powers"]]
                    if not mv.block and cm.get("block"):
                        mv.block = cm["block"]
                else:
                    cm = st.get("code_move") or {}
                    raw = {"id": sid, "name": sid, "intent": " + ".join(i["type"] for i in st.get("intents", [])) or "Unknown",
                           "damage": {"normal": cm.get("damage", 0), "hit_count": cm.get("hits", 1)},
                           "block": cm.get("block", 0), "powers": cm.get("powers", []), "heal": cm.get("heal", 0), "_src": "代码"}
                    mv = Move(raw)
                    self.moves[sid] = mv
                    if cm.get("unknown"):
                        notes.append(f"招式 {sid} 有数值没解析出来：{cm['unknown']}")
                mv.status = [(c["card"], c["pile"], c["n"]) for c in ai.get("status_cards", {}).get(sid, [])]
                mv.sets = st.get("sets") or {}
                mv.summons = bool(st.get("summons")) or any(i["type"] == "Summon" for i in st.get("intents", []))
                if any(i["type"] == "Escape" for i in st.get("intents", [])):
                    mv.intent = "Escape"
                for i in st.get("intents", []):
                    if i["type"] == "Status" and i["args"].strip() and not mv.status:
                        mv.status = [("DAZED", "Discard", i["args"].strip())]
                st["move"] = mv
            states[sid] = st
        self.ai = {"states": states, "initial": ai.get("initial"), "initial_expr": ai.get("initial_expr"),
                   "fields": ai.get("fields", {}),
                   "consts": ai.get("consts", {}), "key": key}
        self.ai_source = "代码"
        self.ai_notes = notes


_DB = {}


def load_db():
    if _DB:
        return _DB
    try:
        _gd.require_codex()
    except _gd.GameDataError as e:
        raise SystemExit(str(e))
    eng = json.load(open(os.path.join(DATA_DIR, "eng_monsters.json"), encoding="utf-8"))
    zh = {x["id"]: x["name"] for x in json.load(open(os.path.join(DATA_DIR, "zhs_monsters.json"), encoding="utf-8"))}
    _DB["monsters"] = {x["id"]: MonsterDef(x, zh.get(x["id"])) for x in eng}
    enc = json.load(open(os.path.join(DATA_DIR, "eng_encounters.json"), encoding="utf-8"))
    zhe = {x["id"]: x["name"] for x in json.load(open(os.path.join(DATA_DIR, "zhs_encounters.json"), encoding="utf-8"))}
    for e in enc:
        e["zh_name"] = zhe.get(e["id"], e["name"])
    _DB["encounters"] = enc
    comp_path = _gd.data_path("encounter_monsters.json")   # 本机首次运行时从你的安装生成
    _DB["compositions"] = json.load(open(comp_path, encoding="utf-8")) if comp_path else {}
    ai_path = _gd.data_path("monster_ai.json")
    if ai_path:
        ai = json.load(open(ai_path, encoding="utf-8"))
        keys = sorted(ai, key=len, reverse=True)
        for mid, md in _DB["monsters"].items():
            k = mid if mid in ai else next((a for a in keys if mid.startswith(a)), None)
            if k:
                md.attach_code_ai(ai[k], k)
    return _DB


ROOM = {"普通": ("Monster", False), "弱怪": ("Monster", True), "精英": ("Elite", False), "首领": ("Boss", False)}


def encounter_pool(act, room):
    """act: 1/2/3；room: 普通/弱怪/精英/首领。返回该幕（含两个第1幕地区）所有遭遇。"""
    db = load_db()
    rt, weak = ROOM[room]
    out = []
    for e in db["encounters"]:
        if not e.get("act") or not e["act"].startswith(f"Act {act}"):
            continue
        if e["room_type"] != rt or bool(e.get("is_weak")) != weak:
            continue
        if not e["monsters"] or any(m["id"] not in db["monsters"] for m in e["monsters"]):
            continue
        ids = possible_monsters(e)
        if any(i not in db["monsters"] for i in ids):
            note(f"缺怪物:{e['id']}", f"遭遇「{e['zh_name']}」的组成里有 spire-codex 没收录的怪物 {[i for i in ids if i not in db['monsters']]}：整场遭遇不参与模拟。")
            continue
        if any(db["monsters"][i].hp_missing for i in ids):
            note(f"缺血量:{e['id']}", f"遭遇「{e['zh_name']}」（{e['id']}）里有敌人没有血量数据，整场遭遇不参与模拟。")
            continue
        out.append(e)
    return out


class Enemy(Creature):
    def __init__(self, mdef, rng, slot=0):
        hp = rng.randint(mdef.min_hp, max(mdef.min_hp, mdef.max_hp))
        super().__init__(mdef.name, hp)
        self.m = mdef
        self.slot = slot
        self.state = None
        self.intent = None
        self.last_move = None
        self.used_once = set()
        self.data = {}
        self.flags = {}          # 遭遇设定的字段（IsFront、ScreamFirst、StarterMoveIdx…）+ 招式改写的字段
        self.state_log = []      # 反编译状态机：已记录的招式状态（用于 CannotRepeat 等）
        self.cur = None
        self.performed_first = False
        self.performed_cur = False

    def clone(self):
        import copy
        new = copy.copy(self)
        self._clone_base(new)
        new.used_once = set(self.used_once)
        new.data = dict(self.data)
        new.flags = dict(self.flags)
        new.state_log = list(self.state_log)
        return new

    # ----- 反编译状态机（与 MonsterMoveStateMachine.cs 同语义）
    def flag(self, name, default=KeyError):
        k = name.lstrip("_").lower()
        for f, v in self.flags.items():
            if f.lstrip("_").lower() == k:
                return v
        if self.m.ai:
            for f, v in self.m.ai.get("fields", {}).items():
                if f.lower() == k:
                    return v
        if default is KeyError:
            raise KeyError(name)
        return default

    def _cs_env(self, C):
        e = self
        alive = [x for x in C.enemies if x.alive]
        env = {
            "HP": e.hp, "MAXHP": e.max_hp, "ROUND": C.turn,
            "HAS": lambda pid: e.has(pid), "SLOT": lambda n: _slot_index(n) == e.slot,
            "GetAllyCount": len([x for x in alive if x is not e]),
            "CanFabricate": len(alive) < 4, "CanLay": len(alive) <= 3,
            "CanSummon": False,
            "HasAmalgamDied": not any(x.m.id == "TORCH_HEAD_AMALGAM" for x in alive),
            "true": True, "false": False,
        }
        return env

    def cs_eval(self, expr, C):
        """把状态机里的 C# lambda（条件/权重）翻译成 Python 求值；认不出的标识符抛 KeyError。"""
        if expr in (None, ""):
            return 1
        x = str(expr).strip()
        if re.fullmatch(r"-?\d+(\.\d+)?f?", x):
            return float(x.rstrip("f"))
        x = re.sub(r"\(\(\w+\)base\.Creature\.Monster\)\.", "", x)
        x = x.replace("base.Creature.MaxHp / 2", "(MAXHP // 2)")
        x = x.replace("base.Creature.CurrentHp", "HP").replace("base.Creature.MaxHp", "MAXHP")
        x = re.sub(r"base\.Creature\.HasPower<(\w+)Power>\(\)", lambda m: 'HAS("%s")' % _snake(m.group(1)), x)
        x = re.sub(r'base\.Creature\.SlotName == "(\w+)"', r'SLOT("\1")', x)
        x = x.replace("base.CombatState.RoundNumber", "ROUND")
        x = re.sub(r"(\d+(?:\.\d+)?)f\b", r"\1", x)
        x = re.sub(r"\b(\w+)\(\)", r"\1", x)
        x = x.replace("&&", " and ").replace("||", " or ")
        x = re.sub(r"!(?!=)", " not ", x)
        m = re.fullmatch(r"\((.*)\)\s*\?\s*(.+?)\s*:\s*(.+)", x.strip())
        if m:
            x = "((%s) if (%s) else (%s))" % (m.group(2), m.group(1), m.group(3))
        env = self._cs_env(C)

        class NS(dict):
            def __missing__(ns, k):
                return self.flag(k)
        ns = NS(env)
        return eval(x, {"__builtins__": {}}, ns)

    def _ai_initial(self, C):
        ai = self.m.ai
        init, ie = ai["initial"], ai["initial_expr"]
        if init is None and isinstance(ie, dict):
            idx = self.flag(ie["switch"], None)
            if idx is None or idx == -1:
                if ie.get("default"):
                    init = ie["default"]
                else:
                    note(f"开场招:{self.m.id}", f"{self.m.name}（{self.m.id}）的开场招由遭遇随机分配，遭遇里没有设定时按站位轮换。")
                    init = ie["cases"][self.slot % len(ie["cases"])]
            else:
                cases = ie["cases"]
                init = cases[idx % 3] if idx % 3 < len(cases) - 1 else cases[-1]
        elif init is None and ie:
            ids = re.findall(r'"([^"]+)"', ie)
            cm = re.match(r"\(?\s*(!?)\s*(\w+)\s*\?", ie)
            val = bool(self.flag(cm.group(2), False)) if cm else False
            if cm and cm.group(1):
                val = not val
            init = ids[0] if val else ids[1]
        return init

    def _ai_next(self, sid, C):
        ai = self.m.ai
        st = ai["states"][sid]
        if st["kind"] == "move":
            return st.get("next")
        br = st["branches"]
        if st["kind"] == "conditional":
            for b in br:
                try:
                    ok = self.cs_eval(b["condition"], C)
                except Exception:
                    note(f"条件:{self.m.id}", f"{self.m.name}（{self.m.id}）条件「{b['condition'][:60]}」无法求值：当作不成立。")
                    ok = False
                if ok:
                    return b["state"]
            note(f"条件兜底:{self.m.id}", f"{self.m.name}（{self.m.id}）的条件分支没有一个成立：取第一个分支。")
            return br[0]["state"]
        # random
        ws = []
        for b in br:
            ws.append(self._branch_weight(b, C))
        tot = sum(ws)
        if tot <= 0:
            note(f"权重:{self.m.id}", f"{self.m.name}（{self.m.id}）随机分支权重全为 0：均匀随机。")
            return C.rng.choice(br)["state"]
        r = C.rng.random() * tot
        for b, w in zip(br, ws):
            r -= w
            if r <= 0 and w > 0:
                return b["state"]
        return [b for b, w in zip(br, ws) if w > 0][-1]["state"]

    def _branch_weight(self, b, C):
        log = self.state_log
        sid = b["state"]
        rep = b.get("repeat", "CanRepeatXTimes")
        num = 1.0
        if rep == "UseOnlyOnce":
            if sid in log:
                num = 0.0
        elif rep != "CanRepeatForever":
            n2 = 1 if rep == "CannotRepeat" else (b.get("max_times") or 1)
            num = 1.0 if len(log) < n2 else 0.0
            k = 0
            while len(log) >= n2 and k < n2 and len(log) - k > 0:
                if log[len(log) - 1 - k] != sid:
                    num = 1.0
                    break
                k += 1
        cd = b.get("cooldown") or 0
        if cd > 0 and sid in log[-cd:]:
            return 0.0
        try:
            w = float(self.cs_eval(b.get("weight", "1"), C))
        except Exception:
            note(f"权重式:{self.m.id}", f"{self.m.name}（{self.m.id}）权重「{b.get('weight')}」无法求值：按 1。")
            w = 1.0
        return num * w

    def _ai_set(self, sid):
        self.cur = sid
        self.performed_cur = False
        self.intent = self.m.ai["states"][sid]["move"] if sid and self.m.ai["states"][sid]["kind"] == "move" else None

    def stun(self, next_state=None):
        self.data["stunned"] = True
        if next_state:
            self.data["after_stun"] = next_state

    def _ai_roll(self, C, first=False):
        ai = self.m.ai
        if not first and "_stun_resume" in self.data:
            sid = self.data.pop("_stun_resume")
            if sid in ai["states"] and ai["states"][sid]["kind"] == "move":
                self._ai_set(sid)
                self.state_log.append(sid)
                self.performed_first = True
                return
            if sid in ai["states"]:
                self.cur = sid
            self.performed_first = True
        if first:
            sid = self._ai_initial(C)
            self._ai_set(sid)
            if ai["states"][sid]["kind"] == "move":
                self.state_log.append(sid)
                return
        st = ai["states"][self.cur]
        if not first and st["kind"] == "move":
            if st.get("must_perform_once") and not self.performed_cur:
                return
            if not self.performed_first:
                return
        logged = None
        for _ in range(64):
            nxt = self._ai_next(self.cur, C)
            if not nxt:
                nxt = self._ai_initial(C)
            self._ai_set(nxt)
            if ai["states"][nxt]["kind"] == "move":
                logged = nxt
                break
        if logged:
            self.state_log.append(logged)

    def force_ai_state(self, sid):
        self._ai_set(sid)

    def intent_bonus(self):
        return 0

    def intent_is_attack(self):
        return self.intent is not None and self.intent.is_attack() and not self.data.get("stunned")

    # ----- 状态机
    def _slot_name_match(self, cond):
        names = ["first", "second", "third", "fourth"]
        for i, n in enumerate(names):
            if f'"{n}"' in cond:
                return i == self.slot
        for i in range(1, 5):
            if f'"wriggler{i}"' in cond:
                return i - 1 == self.slot % 4
        return None

    def _resolve(self, sid, C, depth=0):
        m = self.m
        if depth > 8:
            return self._random_move_state(C)
        if sid is None:
            return self._random_move_state(C)
        s = m.states.get(sid)
        if s is None:
            if sid in m.by_move:
                return m.by_move[sid]
            return self._random_move_state(C)
        if s["type"] == "move":
            if s.get("move_id") not in m.moves:
                return self._random_move_state(C)
            return sid
        branches = s.get("branches") or []
        if not branches:
            note(f"空分支:{m.id}", f"{m.name}（{m.id}）的 {s['type']} 状态 {sid} 没有分支数据：在所有招式里均匀随机。")
            return self._random_move_state(C)
        if s["type"] == "random":
            cands = []
            for b in branches:
                mid = b.get("move_id")
                st = m.by_move.get(mid) or (mid if mid in m.states else None)
                if st is None:
                    continue
                rep = b.get("repeat")
                if rep == "CannotRepeat" and mid == self.last_move:
                    continue
                if rep == "UseOnlyOnce" and mid in self.used_once:
                    continue
                cands.append((st, b.get("weight", 1.0) or 1.0))
            if not cands:
                return self._random_move_state(C)
            tot = sum(w for _, w in cands)
            r = C.rng.random() * tot
            for st, w in cands:
                r -= w
                if r <= 0:
                    return self._resolve(st, C, depth + 1)
            return self._resolve(cands[-1][0], C, depth + 1)
        # conditional
        for b in branches:
            cond = b.get("condition", "")
            ok = self._slot_name_match(cond)
            if ok is True:
                return self._resolve(b.get("move_id"), C, depth + 1)
        for b in branches:
            if self._slot_name_match(b.get("condition", "")) is None:
                note(f"条件:{m.id}", f"{m.name}（{m.id}）的条件分支「{b.get('condition','')[:50]}」无法求值：取第一个非站位分支。")
                return self._resolve(b.get("move_id"), C, depth + 1)
        return self._resolve(branches[0].get("move_id"), C, depth + 1)

    def _random_move_state(self, C):
        L = [s["id"] for s in self.m.move_states if not s.get("must_perform_once")
             and self.m.moves[s["move_id"]].intent not in ("Escape",) and s["move_id"] not in ("DEAD", "REATTACH")]
        if not L:
            L = [s["id"] for s in self.m.move_states]
        if not L:
            return None
        return C.rng.choice(L)

    def setup(self, C):
        for pid, amt in self.m.innate:
            C.apply_power(self, pid, amt, source=("enemy", self))
        if self.m.innate:
            for pid, _ in self.m.innate:
                if pid not in IMPLEMENTED:
                    note(f"能力:{pid}", f"敌人固有能力 {pid}（{self.m.name}）没有实现效果，只记层数。")
        if not self.m.states:
            # 没有状态机：按招式顺序循环
            self.data["cycle"] = 0
        self.choose_intent(C, first=True)

    def choose_intent(self, C, first=False):
        m = self.m
        if m.ai:
            self._ai_roll(C, first)
            return
        if not m.moves:
            self.intent = None
            return
        if not m.states:
            if not first:
                self.data["cycle"] = (self.data.get("cycle", 0) + 1) % len(m.moves)
            self.intent = list(m.moves.values())[self.data.get("cycle", 0)]
            return
        if first:
            sid = self._resolve(m.initial, C)
        else:
            if self.data.pop("force_state", None):
                sid = self.data.pop("force_state_id")
            else:
                cur = m.states.get(self.state) if self.state else None
                nxt = cur.get("next") if cur else None
                if cur is not None and not nxt:
                    note(f"无next:{m.id}", f"{m.name}（{m.id}）的招式 {cur.get('move_id')} 之后没有写下一步：在所有招式里均匀随机。")
                sid = self._resolve(nxt, C)
        self.state = sid
        self.intent = m.moves[m.states[sid]["move_id"]] if sid else None

    def take_turn(self, C):
        mv = self.intent
        if not self.m.ai and (self.has("ASLEEP") or self.has("SLUMBER")):
            return
        if self.data.pop("stunned", False):
            # CreatureCmd.Stun：本回合不行动，之后接指定招式（没有指定则接原本要出的招）
            self.data["_stun_resume"] = self.data.pop("after_stun", None) or self.cur or "__keep__"
            return
        if mv is None:
            return
        self.last_move = mv.id
        self.used_once.add(mv.id)
        self.performed_first = True
        self.performed_cur = True
        for k, v in (mv.sets or {}).items():
            self.flags[k] = self.flag(k, 0) + 1 if v == "++" else v
        if mv.intent == "Escape":
            self.alive = False
            if not C.alive_enemies():
                C.result = "win"
            return
        if mv.damage:
            for _ in range(mv.hits):
                if not C.player.alive or not self.alive:
                    break
                C.deal_damage(self, C.player, mv.damage, "attack")
                if C.result:
                    return
            C.emit("enemy_attack_done", enemy=self, move=mv)
        if mv.block:
            C.gain_block(self, mv.block, from_card=False)
        if mv.heal:
            self.hp = min(self.max_hp, self.hp + mv.heal)
        for pid, tgt, amt in mv.powers:
            if tgt == "allies":
                for o in C.alive_enemies():
                    if o is not self:
                        C.apply_power(o, pid, amt, source=("enemy", self))
                continue
            if tgt == "player":
                if pid not in IMPLEMENTED:
                    note(f"能力:{pid}", f"敌人对玩家施加的 {pid}（{self.m.name}·{mv.name}）没有实现效果，只记层数。")
                C.apply_power(C.player, pid, amt, source=("enemy", self))
            else:
                if pid not in IMPLEMENTED:
                    note(f"能力:{pid}", f"敌人自身能力 {pid}（{self.m.name}·{mv.name}）没有实现效果，只记层数。")
                C.apply_power(self, pid, amt, source=("enemy", self))
        if mv.status:
            for cid, pile, n in mv.status:
                k = n if isinstance(n, int) else (int(n) if str(n).lstrip("-").isdigit() else self.m.ai["consts"].get(str(n)) if self.m.ai else None)
                if k is None:
                    note(f"状态牌数:{self.m.id}", f"{self.m.name} 塞 {cid} 的张数「{n}」无法求值：按 1 张。")
                    k = 1
                if cid not in C.mod.cards:
                    note(f"状态牌:{cid}", f"状态牌 {cid} 没有实现：改塞「晕眩」。")
                    cid = "DAZED"
                to = {"Discard": "discard", "Hand": "hand", "Draw": "draw"}.get(pile, "discard")
                C.add_card(cid, to=to, n=k)
        elif "Status" in mv.intent:
            note("状态牌", "Status 意图：数据里没有塞入的状态牌种类与数量，统一往玩家弃牌堆加 1 张「晕眩」（不能被打出、虚无）。")
            if "DAZED" in C.mod.cards:
                C.add_card("DAZED", to="discard")
        if "Summon" in mv.intent or mv.summons:
            note("召唤", "召唤类招式只执行其中的伤害/格挡/能力部分，不生成新敌人（v0.2 实现）。")


@register_power
class Plow(Power):
    """横冲直撞：生命第一次降到 X 及以下时被击晕并失去全部力量（仪式兽）。"""
    id = "PLOW"; name = "横冲直撞"; kind = "debuff"

    def on_damage_taken(self, C, ev):
        o = self.owner
        if ev.target is o and o.alive and o.hp <= self.amount:
            o.powers.pop("STRENGTH", None)
            o.powers.pop(self.id, None)
            st = [s["id"] for s in o.m.move_states if s.get("must_perform_once")]
            o.data["stunned"] = False
            if o.m.ai:
                cs = [k for k, v in o.m.ai["states"].items() if v.get("must_perform_once")]
                if cs:
                    o.force_ai_state(cs[0])
            elif st:
                o.data["force_state"] = True
                o.data["force_state_id"] = st[0]
                o.state = st[0]
                o.intent = o.m.moves[o.m.states[st[0]]["move_id"]]


@register_power
class Shriek(Power):
    """尖叫：生命第一次降到 X 及以下时被击晕（跳过下一次行动）。"""
    id = "SHRIEK"; name = "尖叫"; kind = "debuff"

    def on_damage_taken(self, C, ev):
        o = self.owner
        if ev.target is o and o.alive and o.hp <= self.amount:
            o.data["stunned"] = True
            o.powers.pop(self.id, None)


@register_power
class Imbalanced(Power):
    """失衡（ImbalancedPower.cs）：它的攻击有一段被完全格挡 → 被击晕；盛碗虫（石）改为进入「失衡」状态（下一招 DIZZY）。"""
    id = "IMBALANCED"; name = "失衡"; kind = "debuff"

    def on_attacked(self, C, ev):
        o = self.owner
        if ev.attacker is o and ev.damage > 0 and ev.unblocked == 0:
            if o.m.ai and "IsOffBalance" in o.m.ai.get("fields", {}):
                o.flags["IsOffBalance"] = True
            elif not o.data.get("stunned"):
                o.stun()


@register_power
class Soar(Power):
    """翱翔：落地前受到的伤害减少 50%。近似：在拥有者下一次行动结束后落地。"""
    id = "SOAR"; name = "翱翔"; kind = "buff"

    def on_damage_mul(self, C, ev):
        if ev.target is self.owner:
            ev.amount *= 0.5

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            if self.data.get("armed"):
                self.owner.powers.pop(self.id, None)
            else:
                self.data["armed"] = True


@register_power
class Flutter(Power):
    """振翅：受到的攻击伤害减少 50%；被攻击 X 次后击晕（近似：击晕后移除振翅）。"""
    id = "FLUTTER"; name = "振翅"; kind = "buff"

    def on_damage_mul(self, C, ev):
        if ev.target is self.owner and ev.kind == "attack":
            ev.amount *= 0.5

    def on_attacked(self, C, ev):
        if ev.target is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)
                self.owner.data["stunned"] = True


@register_power
class PainfulStabs(Power):
    """疼痛戳刺：每次你受到它未被格挡的攻击伤害，往弃牌堆加 1 张伤口。"""
    id = "PAINFUL_STABS"; name = "疼痛戳刺"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.attacker is self.owner and ev.target is C.player and ev.unblocked > 0:
            C.add_card("WOUND", to="discard")


IMPLEMENTED = {"SOAR", "FLUTTER", "PAINFUL_STABS", "STRENGTH", "DEXTERITY", "VULNERABLE", "WEAK", "FRAIL", "ARTIFACT", "INTANGIBLE", "PLATING", "THORNS",
               "RITUAL", "TERRITORIAL", "HIGH_VOLTAGE", "VIGOR", "POISON", "CURL_UP", "SKITTISH", "ENRAGE",
               "HARDENED_SHELL", "RAMPART", "ASLEEP", "SLUMBER", "MINION", "SLIPPERY", "HARD_TO_KILL", "PLOW",
               "SHRIEK", "IMBALANCED", "ILLUSION", "REATTACH"}
from . import powers_enemy as _pe  # noqa: E402
IMPLEMENTED |= set(_pe.IMPLEMENTED_HERE)


# 遭遇里对怪物字段的设定（来自反编译 Encounters/*.cs 的 GenerateMonsters）
ENCOUNTER_SETUP = {
    "CHOMPERS_NORMAL": {1: {"ScreamFirst": True}},
    "TUNNELER_NORMAL": {0: {"ScreamFirst": True}},
    "NIBBITS_NORMAL": {0: {"IsFront": True}},
    "NIBBITS_WEAK": {0: {"IsAlone": True}},
    "TOADPOLES_WEAK": {0: {"IsFront": True}, 1: {"IsFront": False}},
    "INKLETS_NORMAL": {1: {"MiddleInklet": True}},
    "THE_KIN_BOSS": {0: {"StartsWithDance": True}},
}
# 开场招按 base.Rng.NextInt(3) 起点轮换的遭遇：字段名、固定值覆盖
ROTATING_START = {
    "DECIMILLIPEDE_ELITE": ("StarterMoveIdx", {}),
    "SCROLLS_OF_BITING_NORMAL": ("StarterMoveIdx", {3: 2}),
    "SCROLLS_OF_BITING_WEAK": ("StarterMoveIdx", {}),
    "TWO_TAILED_RATS_NORMAL": ("StarterMoveIndex", {}),
    "CORPSE_SLUGS_NORMAL": ("StarterMoveIdx", {}),
    "CORPSE_SLUGS_WEAK": ("StarterMoveIdx", {}),
}


def _snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _slot_index(name):
    order = ["first", "second", "third", "fourth", "fifth"]
    if name in order:
        return order.index(name)
    m = re.match(r"[a-z]+(\d+)$", name)
    if m:
        return int(m.group(1)) - 1
    return {"front": 0, "back": 1}.get(name, -1)


def composition_info(enc):
    db = load_db()
    return db["compositions"].get(enc["id"])


def possible_monsters(enc):
    ci = composition_info(enc)
    if not ci or ci.get("source") == "缺失":
        return [m["id"] for m in enc["monsters"]]
    ids = set()
    for _, comp in ci.get("alternatives") or []:
        ids.update(comp)
    for sl in ci.get("slots") or []:
        ids.update(sl)
    if ci.get("pool"):
        ids.update(ci["pool"]["options"])
    return sorted(ids)


def compose(enc, rng):
    """按反编译 GenerateMonsters() 的组成抽出本场怪物 ID 列表（站位顺序）。"""
    ci = composition_info(enc)
    if not ci or ci.get("source") == "缺失":
        note(f"组成:{enc['id']}", f"遭遇「{enc['zh_name']}」没有解析出代码组成：按 spire-codex 的去重怪物列表各 1 只。")
        return [m["id"] for m in enc["monsters"]]
    if ci.get("alternatives"):
        tot = sum(w for w, _ in ci["alternatives"])
        r = rng.random() * tot
        for w, comp in ci["alternatives"]:
            r -= w
            if r <= 0:
                return list(comp)
        return list(ci["alternatives"][-1][1])
    ids = [rng.choice(sl) for sl in ci["slots"]]
    if ci.get("pool"):
        cnt = {}
        for _ in range(ci["pool"]["n"]):
            opts = [k for k, mx in ci["pool"]["options"].items() if cnt.get(k, 0) < mx]
            k = rng.choice(opts)
            cnt[k] = cnt.get(k, 0) + 1
            ids.append(k)
    return ids


def build_encounter(enc, rng):
    db = load_db()
    out = [Enemy(db["monsters"][mid], rng, slot=i) for i, mid in enumerate(compose(enc, rng))]
    for i, fl in ENCOUNTER_SETUP.get(enc["id"], {}).items():
        if i < len(out):
            out[i].flags.update(fl)
    if enc["id"] in ROTATING_START:
        field, fixed = ROTATING_START[enc["id"]]
        r = rng.randrange(3)
        for i, e in enumerate(out):
            e.flags[field] = fixed.get(i, (r + i) % 3)
    return out
