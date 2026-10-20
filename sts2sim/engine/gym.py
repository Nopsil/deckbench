"""Gym 风格接口：把整局模拟器的每个决策点暴露成 step()。

    from sts2sim.engine.gym import Sts2Env
    env = Sts2Env("Ironclad", ascension=10)
    obs, info = env.reset(seed="S1")
    while True:
        a = my_policy(obs)                 # obs["options"] 是本决策点的合法选项（描述字符串列表）
        obs, reward, done, info = env.step(a)
        if done: break

实现：引擎在后台线程里同步运行，GymAgent 在每个决策点把 (类型, 选项, 状态) 交给前台并阻塞等待动作。
游戏逻辑使用进程级单例（RunManager.Instance 等），所以一个进程同一时刻只能跑一个 Env；并行请用多进程。

决策类型（obs["type"]）与动作含义：
  combat        选 obs["options"] 中的下标（出牌/药水/结束回合）
  card_reward   下标；最后一个选项是“跳过”
  select_cards  下标列表（长度在 [min,max] 之间），或单个下标
  map           下标（下一个地图节点）
  rest          下标（休息处选项）
  shop          下标；最后一个选项是“离开”（可多次购买，每次一个 step）
  event         下标（事件选项）
  treasure      下标（宝箱遗物）
  bundle        下标（卷轴盒等“选一组牌”）
  take_reward   0=跳过 1=领取
`delegate` 参数可只把部分类型交给外部，其余用启发式 AI。
"""
import queue
import threading

from ..rt.boot import game as G
from .agents import HeuristicAgent, _name
from . import combat as C

ALL_KINDS = ("combat", "card_reward", "select_cards", "map", "rest", "shop", "event", "treasure", "bundle",
             "take_reward")


def _cid(c):
    try:
        return c.Id.Entry + ("+" if c.IsUpgraded else "")
    except Exception:  # noqa
        return str(c)


def describe_action(a, enemies=()):
    if a[0] == "end":
        return "end_turn"
    tgt = a[2]
    tname = None
    if tgt is not None:
        try:
            tname = tgt.Monster.Id.Entry if tgt.Monster is not None else "player"
            for i, e in enumerate(enemies):
                if e is tgt:
                    tname += f"#{i}"
        except Exception:  # noqa
            tname = "?"
    return f"{a[0]}:{_cid(a[1])}" + (f"@{tname}" if tname else "")


def observe(drv):
    """可序列化的状态摘要。"""
    p, st = drv.player, drv.state
    o = {}
    if p is None or st is None:
        return o
    cr = p.Creature
    o["player"] = {"hp": cr.CurrentHp, "max_hp": cr.MaxHp, "block": cr.Block, "gold": p.Gold,
                   "powers": [(pw.Id.Entry, int(pw.Amount)) for pw in cr.Powers]}
    o["floor"], o["act"], o["ascension"] = st.TotalFloor, st.CurrentActIndex, drv.ascension
    o["deck"] = [_cid(c) for c in p.Deck.Cards]
    o["relics"] = [r.Id.Entry for r in p.Relics]
    o["potions"] = [x.Id.Entry for x in p.Potions]
    cm = G.CombatManager.Instance
    if cm is not None and cm.IsInProgress:
        cs = cr.CombatState
        pcs = p.PlayerCombatState
        o["combat"] = {
            "round": cs.RoundNumber, "energy": int(pcs.Energy),
            "hand": [_cid(c) for c in C.hand(p)],
            "draw": len(list(G.PileType.Draw.GetPile(p).Cards)),
            "discard": len(list(G.PileType.Discard.GetPile(p).Cards)),
            "enemies": [{"id": e.Monster.Id.Entry if e.Monster is not None else "?", "hp": e.CurrentHp,
                         "max_hp": e.MaxHp, "block": e.Block,
                         "intent": [_name(it.IntentType) for it in (e.Monster.NextMove.Intents
                                    if e.Monster is not None and e.Monster.NextMove is not None else [])],
                         "incoming": HeuristicAgent._enemy_incoming(e, cr),
                         "powers": [(pw.Id.Entry, int(pw.Amount)) for pw in e.Powers]}
                        for e in C.alive_enemies(cs)],
        }
    return o


class _Stop(BaseException):
    pass


class GymAgent(HeuristicAgent):
    name = "gym"

    def __init__(self, env, delegate=ALL_KINDS, seed=0):
        super().__init__(seed=seed)
        self.env = env
        self.delegate = set(delegate)
        self.drv = None

    def on_run_start(self, player, run):
        super().on_run_start(player, run)
        self.drv = run

    def _ask(self, kind, options, extra=None):
        req = {"type": kind, "options": options, "state": observe(self.drv) if self.drv else {}}
        if extra:
            req.update(extra)
        self.env._to_env.put(("decision", req))
        a = self.env._to_engine.get()
        if a is _Stop:
            raise _Stop()
        return a

    @staticmethod
    def _idx(a, n):
        if isinstance(a, (list, tuple)):
            a = a[0] if a else 0
        a = int(a)
        return max(0, min(n - 1, a))

    def combat_action(self, cs, player, acts):
        if "combat" not in self.delegate:
            return super().combat_action(cs, player, acts)
        return acts[self._idx(self._ask("combat", [describe_action(a, C.alive_enemies(cs)) for a in acts]), len(acts))]

    def card_reward(self, cards, alternatives):
        if "card_reward" not in self.delegate:
            return super().card_reward(cards, alternatives)
        cs = [r.Card if hasattr(r, "Card") else r for r in cards]
        i = self._idx(self._ask("card_reward", [_cid(c) for c in cs] + ["skip"]), len(cs) + 1)
        return cs[i] if i < len(cs) else None

    def select_cards(self, options, min_sel, max_sel):
        if "select_cards" not in self.delegate or not options:
            return super().select_cards(options, min_sel, max_sel)
        opts = list(options)
        a = self._ask("select_cards", [_cid(c) for c in opts], {"min": min_sel, "max": max_sel})
        idx = a if isinstance(a, (list, tuple)) else [a]
        sel = []
        for i in idx:
            i = int(i)
            if 0 <= i < len(opts) and opts[i] not in sel:
                sel.append(opts[i])
        if len(sel) < min_sel:
            sel += [c for c in opts if c not in sel][:min_sel - len(sel)]
        return sel[:max_sel] if max_sel >= 0 else sel

    def choose_map_point(self, points, run):
        if "map" not in self.delegate:
            return super().choose_map_point(points, run)
        desc = [f"{_name(pt.PointType)}@{pt.coord.col},{pt.coord.row}" for pt in points]
        return points[self._idx(self._ask("map", desc), len(points))]

    def rest_option(self, options, run):
        if "rest" not in self.delegate:
            return super().rest_option(options, run)
        return self._idx(self._ask("rest", [str(o.OptionId) for o in options]), len(options))

    def shop(self, inventory, run):
        if "shop" not in self.delegate:
            return super().shop(inventory, run)
        entries = []
        if inventory.CardRemovalEntry is not None and inventory.CardRemovalEntry.IsStocked:
            entries.append(("remove_card", inventory.CardRemovalEntry))
        for e in inventory.CardEntries:
            if e.IsStocked and e.CreationResult is not None:
                entries.append(("card:" + _cid(e.CreationResult.Card), e))
        for e in inventory.RelicEntries:
            if e.IsStocked:
                entries.append(("relic:" + e.Model.Id.Entry if getattr(e, "Model", None) is not None else "relic", e))
        for e in inventory.PotionEntries:
            if e.IsStocked:
                entries.append(("potion", e))
        entries = [(d, e) for d, e in entries if e.EnoughGold]
        if not entries:
            return []
        i = self._idx(self._ask("shop", [f"{d} ({e.Cost}g)" for d, e in entries] + ["leave"]), len(entries) + 1)
        return [entries[i][1]] if i < len(entries) else []

    def event_option(self, event, options, run):
        if "event" not in self.delegate:
            return super().event_option(event, options, run)
        desc = [f"{o.TextKey}{' [locked]' if o.IsLocked else ''}" for o in options]
        return self._idx(self._ask("event", desc, {"event": event.Id.Entry}), len(options))

    def treasure_relic(self, relics, run):
        if "treasure" not in self.delegate or not relics:
            return super().treasure_relic(relics, run)
        return self._idx(self._ask("treasure", [r.Id.Entry for r in relics]), len(relics))

    def choose_bundle(self, bundles):
        if "bundle" not in self.delegate:
            return super().choose_bundle(bundles)
        return self._idx(self._ask("bundle", [",".join(_cid(c) for c in b) for b in bundles]), len(bundles))

    def take_reward(self, reward):
        if "take_reward" not in self.delegate:
            return super().take_reward(reward)
        return bool(self._idx(self._ask("take_reward", ["skip", "take:" + type(reward).__name__]), 2))


class Sts2Env:
    def __init__(self, character="Ironclad", ascension=10, delegate=ALL_KINDS, **run_kw):
        self.character, self.ascension, self.delegate, self.run_kw = character, ascension, delegate, run_kw
        self._thread = None
        self.result = None

    def _engine(self, seed):
        from .run import RunDriver
        try:
            agent = GymAgent(self, self.delegate)
            drv = RunDriver(self.character, self.ascension, seed, agent=agent, **self.run_kw)
            res = drv.play()
            self._to_env.put(("done", res))
        except _Stop:
            pass
        except BaseException as e:  # noqa
            self._to_env.put(("error", e))

    def reset(self, seed="SEED"):
        self.close()
        self._to_env, self._to_engine = queue.Queue(), queue.Queue()
        self.result = None
        self._thread = threading.Thread(target=self._engine, args=(str(seed),), daemon=True)
        self._thread.start()
        obs, _, done, info = self._next()
        return obs, info

    def _next(self):
        kind, payload = self._to_env.get()
        if kind == "decision":
            return payload, 0.0, False, {}
        if kind == "done":
            self.result = payload
            r = 1.0 if payload.victory else -1.0
            return {"type": "done", "options": [], "state": {}}, r, True, {"result": payload.to_dict()}
        raise payload

    def step(self, action):
        if self._thread is None or self.result is not None:
            raise RuntimeError("call reset() first")
        self._to_engine.put(action)
        return self._next()

    def close(self):
        if self._thread is not None and self._thread.is_alive() and self.result is None:
            self._to_engine.put(_Stop)
            self._thread.join(timeout=10)
        self._thread = None
