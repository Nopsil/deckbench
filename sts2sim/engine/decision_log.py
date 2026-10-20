"""单局逐步决策日志（JSON Lines）：给以后的 Grok 预演和真游戏复刻用。

用法：agent = DecisionLogger(inner_agent, path_or_file, agent_name="learned")，再照常交给 RunDriver。
每次 agent 做决定写一行：
  {"v":1,"seq":12,"seed":"…","char":"Ironclad","asc":0,"act":1,"floor":3,"screen":"map",
   "hp":70,"max_hp":80,"gold":120,"options":[…],"choice":…,"choice_i":1,"agent":"learned","reason":null, …}
screen 取值：neow / event / map / card_reward / reward / card_select / bundle / rest / shop / treasure / combat
  - combat 额外带 round、energy、hand、enemies（id/hp/block/意图），options 是合法动作的文字形式
  - reason：内层 agent 若设置了 last_reason 属性就记下来（Grok agent 用），否则 null
包装是透明的：其余属性/方法原样转发给内层 agent。
"""
import json
import time

from ..rt.boot import game as G


def _n(e):
    try:
        return e.name
    except AttributeError:
        return str(e).split(".")[-1]


def card_id(c):
    c = getattr(c, "Card", c) if not isinstance(c, G.CardModel) else c   # CardCreationResult → CardModel
    try:
        return c.Id.Entry + ("+" if c.IsUpgraded else "")
    except Exception:  # noqa
        return str(c)


def _creature(cr, cs=None):
    if cr is None:
        return None
    try:
        if cr.Monster is not None:
            idx = None
            if cs is not None:
                try:
                    idx = [e for e in cs.Enemies].index(cr)
                except ValueError:
                    pass
            return f"{cr.Monster.Id.Entry}#{idx}" if idx is not None else cr.Monster.Id.Entry
    except Exception:  # noqa
        pass
    return "player"


def _model_id(x):
    for path in (("CreationResult", "Card"), ("Model",), ("Relic",), ("Potion",), ()):
        o = x
        try:
            for p in path:
                o = getattr(o, p)
            if o is not None and hasattr(o, "Id"):
                return card_id(o) if isinstance(o, G.CardModel) else o.Id.Entry
        except Exception:  # noqa
            continue
    return type(x).__name__


def describe_action(a, cs=None):
    if a[0] == "end":
        return "end_turn"
    t = _creature(a[2], cs) if len(a) > 2 else None
    what = card_id(a[1]) if a[0] == "play" else a[1].Id.Entry
    return f"{a[0]} {what}" + (f" -> {t}" if t else "")


def describe_reward(r):
    d = {"kind": type(r).__name__}
    try:
        if isinstance(r, G.CardReward):
            d["cards"] = [card_id(c) for c in r.Cards]
        elif isinstance(r, G.GoldReward):
            d["gold"] = int(r.Amount)
        elif isinstance(r, G.PotionReward):
            d["potion"] = r.Potion.Id.Entry if r.Potion is not None else None
        elif isinstance(r, G.RelicReward):
            rl = getattr(r, "_relic", None) or getattr(r, "_predeterminedRelic", None)
            d["relic"] = rl.Id.Entry if rl is not None else None
    except Exception:  # noqa
        pass
    return d


def intents(e):
    out = []
    try:
        mv = e.Monster.NextMove
        for it in mv.Intents:
            x = {"type": type(it).__name__.replace("Intent", "")}
            if isinstance(it, G.AttackIntent):
                try:
                    x["dmg"] = int(it.GetTotalDamage(G.Seq([G.RunManager.Instance.State.Players[0].Creature]), e))
                except Exception:  # noqa
                    pass
            out.append(x)
    except Exception:  # noqa
        pass
    return out


class DecisionLogger:
    def __init__(self, inner, out, agent_name=None, meta=None):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_f", open(out, "w", encoding="utf-8") if isinstance(out, str) else out)
        object.__setattr__(self, "_name", agent_name or getattr(inner, "name", type(inner).__name__))
        object.__setattr__(self, "_meta", dict(meta or {}))
        object.__setattr__(self, "_seq", 0)
        object.__setattr__(self, "_run", None)

    # 透明转发
    def __getattr__(self, k):
        return getattr(self._inner, k)

    def __setattr__(self, k, v):
        setattr(self._inner, k, v)

    def close(self):
        try:
            self._f.flush()
            if self._f not in (None,) and hasattr(self._f, "name"):
                self._f.close()
        except Exception:  # noqa
            pass

    # ---- 记录 ----
    def _ctx(self):
        d = {}
        run = self._run
        try:
            st = run.state
            p = run.player
            d.update(act=int(st.CurrentActIndex) + 1, floor=int(st.TotalFloor), hp=int(p.Creature.CurrentHp),
                     max_hp=int(p.Creature.MaxHp), gold=int(p.Gold))
            room = st.CurrentRoom
            d["room"] = type(room).__name__.replace("Room", "") if room is not None else None
        except Exception:  # noqa
            pass
        return d

    def _log(self, screen, options, choice, choice_i=None, **extra):
        seq = self._seq + 1
        object.__setattr__(self, "_seq", seq)
        row = {"v": 1, "seq": seq, "t_ms": int(time.time() * 1000), **self._meta, **self._ctx(), "screen": screen,
               "options": options, "choice": choice, "choice_i": choice_i, "agent": self._name,
               "reason": getattr(self._inner, "last_reason", None)}
        for k in ("last_n", "last_source"):
            if hasattr(self._inner, k):
                row[k[5:]] = getattr(self._inner, k)
        row.update(extra)
        try:
            object.__setattr__(self._inner, "last_reason", None) if hasattr(self._inner, "last_reason") else None
        except Exception:  # noqa
            pass
        self._f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self._f.flush()

    # ---- 包装的决策点 ----
    def on_run_start(self, player, run):
        object.__setattr__(self, "_run", run)
        try:
            self._meta.setdefault("seed", run.seed)
            self._meta.setdefault("char", run.character if isinstance(run.character, str) else str(run.character))
            self._meta.setdefault("asc", run.ascension)
        except Exception:  # noqa
            pass
        return self._inner.on_run_start(player, run)

    def combat_action(self, cs, player, acts):
        a = self._inner.combat_action(cs, player, acts)
        opts = [describe_action(x, cs) for x in acts]
        try:
            i = next(k for k, x in enumerate(acts) if x is a or tuple(x) == tuple(a))
        except StopIteration:
            i = None
        try:
            hand = [card_id(c) for c in G.PileType.Hand.GetPile(player).Cards]
            en = [{"id": _creature(e, cs), "hp": int(e.CurrentHp), "block": int(e.Block), "intents": intents(e)}
                  for e in cs.Enemies if e.IsAlive]
            extra = dict(round=int(cs.RoundNumber), energy=int(player.PlayerCombatState.Energy),
                         block=int(player.Creature.Block), hand=hand, enemies=en)
        except Exception:  # noqa
            extra = {}
        self._log("combat", opts, describe_action(a, cs), i, **extra)
        return a

    def choose_map_point(self, points, run):
        pt = self._inner.choose_map_point(points, run)
        opts = [{"col": int(p.coord.col), "row": int(p.coord.row), "type": _n(p.PointType)} for p in points]
        i = next((k for k, p in enumerate(points) if p is pt), None)
        self._log("map", opts, opts[i] if i is not None else None, i)
        return pt

    def event_option(self, event, options, run):
        i = self._inner.event_option(event, options, run)
        opts = [{"key": o.TextKey, "locked": bool(o.IsLocked)} for o in options]
        ev = event.Id.Entry if event is not None else None
        screen = "neow" if isinstance(event, G.AncientEventModel) else "event"
        self._log(screen, opts, opts[i]["key"] if i is not None and 0 <= i < len(opts) else None, i, event=ev)
        return i

    def card_reward(self, cards, alternatives):
        r = self._inner.card_reward(cards, alternatives)
        opts = [card_id(c) for c in cards]
        alts = [str(getattr(a, "OptionId", type(a).__name__)) for a in alternatives or []]
        if r is None:
            ch, i = "skip", None
        elif isinstance(r, G.CardModel):
            i = next((k for k, c in enumerate(cards) if c is r or getattr(c, "Card", None) is r), None)
            ch = card_id(r)
        else:
            ch, i = str(getattr(r, "OptionId", type(r).__name__)), None
        self._log("card_reward", opts, ch, i, alternatives=alts)
        return r

    def take_reward(self, reward):
        ok = self._inner.take_reward(reward)
        self._log("reward", [describe_reward(reward)], bool(ok), 0 if ok else None)
        return ok

    def select_cards(self, options, min_sel, max_sel):
        res = self._inner.select_cards(options, min_sel, max_sel)
        opts = [card_id(c) for c in options]
        res_l = list(res) if res is not None else []
        idx = [k for k, c in enumerate(options) if any(c is x for x in res_l)]
        self._log("card_select", opts, [card_id(c) for c in res_l], idx, min=int(min_sel), max=int(max_sel))
        return res

    def choose_bundle(self, bundles):
        i = self._inner.choose_bundle(bundles)
        opts = [[card_id(c) for c in b] for b in bundles]
        self._log("bundle", opts, opts[i] if i is not None and 0 <= i < len(opts) else None, i)
        return i

    def rest_option(self, options, run):
        i = self._inner.rest_option(options, run)
        opts = [str(getattr(o, "OptionId", type(o).__name__)) for o in options]
        self._log("rest", opts, opts[i] if i is not None and 0 <= i < len(opts) else None, i)
        return i

    def shop(self, inventory, run):
        buys = list(self._inner.shop(inventory, run) or [])
        stock = []
        try:
            for e in list(inventory.CardEntries) + list(inventory.RelicEntries) + list(inventory.PotionEntries):
                if e.IsStocked:
                    stock.append({"id": _model_id(e), "cost": int(e.Cost)})
            if inventory.CardRemovalEntry is not None and inventory.CardRemovalEntry.IsStocked:
                stock.append({"id": "CARD_REMOVAL", "cost": int(inventory.CardRemovalEntry.Cost)})
        except Exception:  # noqa
            pass
        want = []
        for e in buys:
            want.append("CARD_REMOVAL" if e is getattr(inventory, "CardRemovalEntry", None) else _model_id(e))
        self._log("shop", stock, want, None)
        return buys

    def treasure_relic(self, relics, run):
        i = self._inner.treasure_relic(relics, run)
        opts = [r.Id.Entry for r in relics]
        self._log("treasure", opts, opts[i] if i is not None and 0 <= i < len(opts) else None, i)
        return i
