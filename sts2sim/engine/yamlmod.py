"""YAML 数据 mod → 整局引擎（从你本机游戏生成的代码）。

用法：
    from sts2sim.engine import yamlmod
    chars = yamlmod.load("mods/claude_yaml")          # 返回 {角色 ID: 角色类}，并注册到 run.CHARACTERS
    from sts2sim.engine.run import play_run
    play_run("Claude", 10, "R0")

格式见 docs/MODDING.md 和 sts2sim/modfmt/schema.py。卡牌效果 = op 列表（和旧版 YAML 战斗模拟器同一套写法），
能力 / 遗物 = 触发器 + 模板；写不出来的再用 fullrun_hooks.py 里的 Python 函数（{op: py, fn: 名字}）。
所有效果都翻译成游戏自己的命令（DamageCmd / PowerCmd / CardPileCmd …），所以力量、易伤、人工制品等原版规则照常生效。
"""
import importlib.util
import math
import os
import re
import sys
import types

from ..rt.boot import game as G
from ..modfmt import schema as S
from ..modfmt.schema import ModFormatError

META = type(G.CardModel)
CUR = []                      # 表达式求值时的上下文栈（辅助函数用 CUR[-1] 取当前上下文）
_LOADED = {}                  # (路径, 变体) -> Mod
_ACTIVE = []                  # 已注册的 Mod（一个进程里可以注册多个不同的 mod）
_PLAY_NO = [0]


def _noctx():
    return G.ThrowingPlayerChoiceContext()


def _num(x):
    try:
        f = float(x)
    except Exception:  # noqa
        return x
    return int(f) if f == int(f) else f


# ---------------------------------------------------------------- 表达式
_CODE = {}


def _code(x):
    c = _CODE.get(x)
    if c is None:
        c = compile(str(x), "<mod 表达式>", "eval")
        _CODE[x] = c
    return c


def ev(x, ctx):
    if x is None or isinstance(x, (int, float, bool)):
        return x
    if not isinstance(x, str):
        return x
    ns = dict(ctx.mod.ns)
    ns.update(ctx.vars)
    ns["card"] = ctx.card
    ns.update(ctx.extra)
    ns.update(ctx.locals)
    ns["T"] = ctx.T
    ns["P"] = ctx.P
    CUR.append(ctx)
    try:
        return eval(_code(x), ns)
    except ModFormatError:
        raise
    except Exception as e:  # noqa
        raise ModRuntimeError(ctx, x, e) from None
    finally:
        CUR.pop()


class ModRuntimeError(Exception):
    def __init__(self, ctx, expr, e):
        where = ctx.where()
        super().__init__(f"{where}：表达式「{expr}」算不出来（{type(e).__name__}: {e}）/ "
                         f"{where}: expression '{expr}' failed ({type(e).__name__}: {e})")


def _cur():
    return CUR[-1]


def _cs():
    c = _cur()
    return c.cs


def _enemies_of(ctx):
    cs = ctx.cs
    if cs is None:
        return []
    if ctx.P is not None and ctx.P.Side != G.CombatSide.Player:
        return [ctx.player.Creature] if ctx.player is not None and ctx.player.Creature.IsAlive else []
    return [e for e in cs.HittableEnemies if e.IsAlive]


def _stacks(c, pid):
    if c is None:
        return 0
    cls = _cur().mod.power_cls(pid)
    p = c.GetPower(_g=(cls,))
    return int(p.Amount) if p is not None else 0


def _memory(c, pid):
    if c is None:
        return []
    p = c.GetPower(_g=(_cur().mod.power_cls(pid),))
    return list(getattr(p, "_ym_mem", [])) if p is not None else []


def _intent_damage(c=None):
    ctx = _cur()
    e = ctx.T if c is None else c
    if e is None or e.Side == G.CombatSide.Player:
        return 0
    tot = 0
    mv = e.Monster.NextMove if e.Monster is not None else None
    if mv is None:
        return 0
    for it in mv.Intents:
        if isinstance(it, G.AttackIntent):
            try:
                tot += int(it.GetTotalDamage(G.Seq([ctx.player.Creature]), e))
            except Exception:  # noqa
                pass
    return tot


def _attacking(c=None):
    e = _cur().T if c is None else c
    return bool(e is not None and e.Side != G.CombatSide.Player and e.Monster is not None and e.Monster.IntendsToAttack)


def _pile(kind):
    return list(getattr(G.PileType, kind).GetPile(_cur().player).Cards)


def _hand_has(cid):
    mod = _cur().mod
    want = mod.card_entry(cid)
    return any(x.Id.Entry == want for x in _pile("Hand"))


def _plays_this_turn():
    ctx = _cur()
    c = ctx.card
    if c is None:
        return 0
    st = ctx.state()
    return st["plays"].get((id(c), ctx.cs.RoundNumber), 0)


BASE = {
    "__builtins__": {}, "min": min, "max": max, "abs": abs, "int": int, "float": float, "floor": math.floor,
    "ceil": math.ceil, "round": round, "len": len, "sum": sum, "any": any, "all": all, "True": True, "False": False,
    "None": None, "list": list, "range": range, "sorted": sorted,
    "stacks": _stacks, "memory": _memory, "intent_damage": _intent_damage, "attacking": _attacking,
    "hand_size": lambda: len(_pile("Hand")), "draw_size": lambda: len(_pile("Draw")),
    "discard_size": lambda: len(_pile("Discard")), "exhaust_size": lambda: len(_pile("Exhaust")),
    "enemies": lambda: _enemies_of(_cur()), "n_enemies": lambda: len(_enemies_of(_cur())),
    "others": lambda: [e for e in _enemies_of(_cur()) if e is not _cur().T],
    "energy": lambda: int(_cur().player.PlayerCombatState.Energy),
    "block": lambda c=None: int((c if c is not None else _cur().P).Block),
    "hp": lambda c=None: int((c if c is not None else _cur().P).CurrentHp),
    "max_hp": lambda c=None: int((c if c is not None else _cur().P).MaxHp),
    "alive": lambda c=None: bool((c if c is not None else _cur().T) is not None and (c if c is not None else _cur().T).IsAlive),
    "hand_has": _hand_has, "turn": lambda: int(_cs().RoundNumber),
    "sum_stacks": lambda pid: sum(_stacks(e, pid) for e in _enemies_of(_cur())),
    "max_stacks": lambda pid: max([_stacks(e, pid) for e in _enemies_of(_cur())] or [0]),
    "count_with": lambda pid: sum(1 for e in _enemies_of(_cur()) if _stacks(e, pid) > 0),
    "plays_this_turn": _plays_this_turn,
}
S.EXPR_NAMES.update(k for k in BASE if k != "__builtins__")


# ---------------------------------------------------------------- 结算上下文
class Ctx:
    __slots__ = ("mod", "player", "P", "card", "cp", "gctx", "T", "power", "vars", "extra", "locals", "stop", "label")

    def __init__(self, mod, player, P, card=None, cp=None, gctx=None, T=None, power=None, vars=None, extra=None, label=""):
        self.mod, self.player, self.P, self.card, self.cp, self.gctx, self.T = mod, player, P, card, cp, gctx, T
        self.power = power
        self.vars = vars or {}
        self.extra = extra or {}
        self.locals = {}
        self.stop = False
        self.label = label

    @property
    def cs(self):
        if self.P is not None:
            return self.P.CombatState
        return self.card.CombatState if self.card is not None else None

    def g(self):
        return self.gctx if self.gctx is not None else _noctx()

    def state(self):
        cs = self.cs
        s = getattr(cs, "_ym_state", None) if cs is not None else None
        if s is None:
            s = {"once": set(), "plays": {}, "count": {}}
            if cs is not None:
                cs._ym_state = s
        return s

    def where(self):
        return f"[{self.mod.name}] {self.label}"


def _player_turn(cs):
    try:
        return cs.CurrentSide == G.CombatSide.Player
    except Exception:  # noqa
        return True


def _targets(ctx, spec):
    if spec in (None, "target"):
        return [ctx.T] if ctx.T is not None else []
    if spec in ("self", "player"):
        return [ctx.P]
    es = _enemies_of(ctx)
    if spec == "all":
        return es
    if spec == "others":
        return [e for e in es if e is not ctx.T]
    if spec in ("random", "random_other"):
        if spec == "random_other":
            es = [e for e in es if e is not ctx.T]
        if not es:
            return []
        return [ctx.player.RunState.Rng.CombatTargets.NextItem(G.Seq(es))]
    raise ValueError(spec)


# ---------------------------------------------------------------- op 实现
def _hit(ctx, t, dmg, hits, kind):
    if t is None or not t.IsAlive:
        return
    if kind == "attack" and ctx.card is not None:
        cmd = G.DamageCmd.Attack(float(dmg)).FromCard(ctx.card, ctx.cp).Targeting(t)
        if hits > 1:
            cmd = cmd.WithHitCount(int(hits))
        cmd.Execute(ctx.g())
        return
    if dmg <= 0:
        return
    props = G.ValueProp.Unpowered | (G.ValueProp.Unblockable if kind == "hp_loss" else G.ValueProp.SkipHurtAnim)
    for _ in range(max(1, int(hits))):
        if not t.IsAlive:
            break
        G.CreatureCmd.Damage(ctx.g(), t, float(dmg), props, ctx.P, None, None)


def op_damage(ctx, eff):
    spec = eff.get("target", "target")
    kind = eff.get("kind") or ("attack" if ctx.card is not None else "unpowered")
    each = eff.get("each_hit")
    if kind == "attack" and ctx.card is not None and not each and spec in ("all", "random"):
        dmg = ev(eff["amount"], ctx)
        hits = int(ev(eff.get("hits", 1), ctx))
        cmd = G.DamageCmd.Attack(float(dmg)).FromCard(ctx.card, ctx.cp)
        if spec == "all":
            cmd = cmd.TargetingAllOpponents(ctx.cs)
            if hits > 1:
                cmd = cmd.WithHitCount(hits)
        else:
            cmd = cmd.TargetingRandomOpponents(ctx.cs).WithHitCount(hits)
        cmd.Execute(ctx.g())
        return
    for t in list(_targets(ctx, spec)):
        if t is None or not t.IsAlive:
            continue
        old = ctx.T
        ctx.T = t
        hits = int(ev(eff.get("hits", 1), ctx))
        dmg = ev(eff["amount"], ctx)
        if each:
            for _ in range(hits):
                if not t.IsAlive:
                    break
                _hit(ctx, t, dmg, 1, kind)
                run(ctx, each)
        else:
            _hit(ctx, t, dmg, hits, kind)
        ctx.T = old


def op_block(ctx, eff):
    n = ev(eff["amount"], ctx)
    if n is None or n <= 0:
        return
    c = ctx.card
    if c is not None:
        a = eff["amount"]
        if isinstance(a, str) and a in ctx.mod.card_vars(c) and isinstance(c.DynamicVars[a], G.BlockVar):
            G.CreatureCmd.GainBlock(ctx.P, c.DynamicVars[a], ctx.cp)
        else:
            G.CreatureCmd.GainBlock(ctx.P, G.BlockVar(float(n), G.ValueProp.Move), ctx.cp)
    else:
        G.CreatureCmd.GainBlock(ctx.P, G.BlockVar(float(n), G.ValueProp.Unpowered), None)


def _amount(t, cls):
    p = t.GetPower(_g=(cls,))
    return int(p.Amount) if p is not None else 0


def op_apply(ctx, eff):
    mod = ctx.mod
    pid = eff["power"]
    cls = mod.power_cls(pid)
    spec = eff.get("target", "target")
    multi = spec in ("all", "others")
    secondary = bool(eff.get("secondary", False))
    active = eff.get("active")
    is_mod = pid in mod.powers
    pmax = mod.powers[pid].get("max") if is_mod else None
    for t in list(_targets(ctx, spec)):
        if t is None or not t.IsAlive:
            continue
        old = ctx.T
        ctx.T = t
        n = ev(eff["amount"], ctx)
        ctx.T = old
        if n is None or n == 0 or (is_mod and n < 0):
            continue
        act = active if active is not None else _player_turn(ctx.cs)
        if not secondary and ctx.player is not None:
            n += mod.modify_apply(ctx.player, pid, t, n, act, ctx.card)
        if pmax is not None:
            n = min(n, int(pmax) - _amount(t, cls))
            if n <= 0:
                continue
        before = _amount(t, cls)
        G.PowerCmd.Apply(_noctx(), t, float(n), ctx.P, ctx.card, _g=(cls,))
        gained = _amount(t, cls) - before
        if eff.get("remember") is not None:
            p = t.GetPower(_g=(cls,))
            if p is not None:
                p._ym_mem = list(getattr(p, "_ym_mem", [])) + [ev(eff["remember"], ctx)]
        if gained > 0 and not secondary and ctx.player is not None:
            mod.fire(ctx.player, "power_applied", pid, t, gained, ctx.card, active=act, multi=multi)


def op_remove(ctx, eff):
    mod = ctx.mod
    pid = eff["power"]
    cls = mod.power_cls(pid)
    total = 0
    for t in list(_targets(ctx, eff.get("target", "target"))):
        if t is None:
            continue
        p = t.GetPower(_g=(cls,))
        if p is None:
            continue
        before = int(p.Amount)
        a = eff.get("amount")
        if a in (None, "all"):
            k = before
        else:
            old = ctx.T
            ctx.T = t
            k = min(int(ev(a, ctx)), before)
            ctx.T = old
        if k <= 0:
            continue
        if k >= before:
            G.PowerCmd.Remove(p)
        else:
            G.PowerCmd.ModifyAmount(_noctx(), p, float(-k), ctx.P, ctx.card)
        total += k
        if ctx.player is not None:
            mod.fire(ctx.player, "power_removed", pid, t, k, ctx.card)
    if eff.get("save"):
        ctx.locals[eff["save"]] = total


def op_set_stacks(ctx, eff):
    cls = ctx.mod.power_cls(eff["power"])
    for t in list(_targets(ctx, eff.get("target", "target"))):
        if t is None or not t.IsAlive:
            continue
        old = ctx.T
        ctx.T = t
        new = ev(eff["value"], ctx)
        ctx.T = old
        cur = _amount(t, cls)
        new = int(max(0, new))
        if new == cur:
            continue
        p = t.GetPower(_g=(cls,))
        if p is None:
            G.PowerCmd.Apply(_noctx(), t, float(new), ctx.P, ctx.card, _g=(cls,))
        elif new == 0:
            G.PowerCmd.Remove(p)
        else:
            G.PowerCmd.ModifyAmount(_noctx(), p, float(new - cur), ctx.P, ctx.card)


def op_draw(ctx, eff):
    n = ev(eff["n"], ctx)
    if n and n > 0:
        G.CardPileCmd.Draw(ctx.g(), float(n), ctx.player)


def op_energy(ctx, eff):
    n = ev(eff["n"], ctx)
    if n and n > 0:
        G.PlayerCmd.GainEnergy(float(n), ctx.player)
    elif n and n < 0:
        G.PlayerCmd.LoseEnergy(float(-n), ctx.player)


def op_lose_hp(ctx, eff):
    for t in _targets(ctx, eff.get("target", "self")):
        n = ev(eff["amount"], ctx)
        if t is not None and t.IsAlive and n > 0:
            G.CreatureCmd.Damage(ctx.g(), t, float(n), G.ValueProp.Unblockable | G.ValueProp.Unpowered, ctx.P, None, None)


def op_heal(ctx, eff):
    n = ev(eff["amount"], ctx)
    if n > 0:
        G.CreatureCmd.Heal(ctx.P, float(n))


_PILES = {"hand": "Hand", "draw": "Draw", "discard": "Discard"}


def op_add_card(ctx, eff):
    cls = ctx.mod.card_cls(eff["card"])
    n = int(ev(eff.get("n", 1), ctx))
    up = bool(ev(eff.get("upgraded", False), ctx))
    pile = getattr(G.PileType, _PILES[eff.get("to", "hand")])
    for _ in range(n):
        card = ctx.cs.CreateCard(G.ModelDb.Card(_g=(cls,)), ctx.player)
        if up:
            card.UpgradeInternal()
        G.CardPileCmd.AddGeneratedCardToCombat(card, pile, ctx.player)


def op_set(ctx, eff):
    ctx.locals[eff["name"]] = ev(eff["value"], ctx)


def op_if(ctx, eff):
    run(ctx, (eff.get("then") or []) if ev(eff["cond"], ctx) else (eff.get("else") or []))


def op_foreach(ctx, eff):
    for t in list(_targets(ctx, eff.get("target", "all"))):
        if t is None or not t.IsAlive:
            continue
        old = ctx.T
        ctx.T = t
        run(ctx, eff["do"])
        ctx.T = old
        if ctx.stop:
            return


def op_repeat(ctx, eff):
    for _ in range(int(ev(eff["n"], ctx))):
        run(ctx, eff["do"])
        if ctx.stop:
            return


def _choose_from_hand(ctx, n, prompt):
    c = ctx.card
    pr = c.SelectionScreenPrompt if c is not None else prompt
    sel = G.CardSelectCmd.FromHand(prefs=G.CardSelectorPrefs(pr, int(n)), context=ctx.g(), player=ctx.player,
                                   filter=(lambda x: x is not c), source=c)
    if int(n) == 1:
        one = sel.FirstOrDefault()
        return [one] if one is not None else []
    return [x for x in G._iter(sel) if x is not None]


def op_exhaust_choice(ctx, eff):
    picks = _choose_from_hand(ctx, ev(eff.get("n", 1), ctx), G.CardSelectorPrefs.ExhaustSelectionPrompt)
    for x in picks:
        G.CardCmd.Exhaust(ctx.g(), x)
    if eff.get("save"):
        ctx.locals[eff["save"]] = len(picks)


def op_discard_choice(ctx, eff):
    for x in _choose_from_hand(ctx, ev(eff.get("n", 1), ctx), G.CardSelectorPrefs.DiscardSelectionPrompt):
        G.CardCmd.Discard(ctx.g(), x)


def op_pick_from_pile(ctx, eff):
    """从抽牌堆顶 look 张（或弃牌堆 / 消耗堆全部）里挑 n 张放入手牌（近似：自动挑“最好”的——非基础、费用高的优先）。"""
    kind = {"draw": "Draw", "discard": "Discard", "exhaust": "Exhaust"}[eff.get("pile", "draw")]
    pile = list(getattr(G.PileType, kind).GetPile(ctx.player).Cards)
    if kind == "Draw":
        pile = pile[:int(ev(eff.get("look", 3), ctx))]
    pile = [x for x in pile if x is not ctx.card]
    good = [x for x in pile if G.CardType.Status != x.Type and G.CardType.Curse != x.Type] or pile
    for _ in range(int(ev(eff.get("n", 1), ctx))):
        if not good:
            break
        best = max(good, key=lambda x: (x.Rarity != G.CardRarity.Basic, int(x.EnergyCost.Canonical)))
        good.remove(best)
        G.CardPileCmd.Add(best, G.PileType.Hand)


def op_exhaust_hand(ctx, eff):
    k = 0
    for x in list(G.PileType.Hand.GetPile(ctx.player).Cards):
        if x is ctx.card:
            continue
        G.CardCmd.Exhaust(ctx.g(), x)
        k += 1
    if eff.get("save"):
        ctx.locals[eff["save"]] = k


def op_return(ctx, eff):
    if ctx.card is not None:
        ctx.card._ym_return = True


def op_end_turn(ctx, eff):
    G.PlayerCmd.EndTurn(ctx.player, False)
    ctx.stop = True


def op_py(ctx, eff):
    fn = ctx.mod.py_fn(eff["fn"])
    params = {k: v for k, v in eff.items() if k not in S.EFFECT_COMMON and k != "fn"}
    fn(ctx, **params)


OPS = {"damage": op_damage, "block": op_block, "apply": op_apply, "remove_power": op_remove, "set_stacks": op_set_stacks,
       "draw": op_draw, "energy": op_energy, "lose_hp": op_lose_hp, "heal": op_heal, "add_card": op_add_card,
       "set": op_set, "if": op_if, "foreach": op_foreach, "repeat": op_repeat, "exhaust_choice": op_exhaust_choice,
       "discard_choice": op_discard_choice, "pick_from_pile": op_pick_from_pile, "exhaust_hand": op_exhaust_hand,
       "return_to_hand": op_return, "end_turn": op_end_turn, "py": op_py}


def _once_key(ctx, kind):
    cs = ctx.cs
    rnd = cs.RoundNumber if cs is not None else 0
    owner = ctx.card if ctx.card is not None and ctx.power is None else ctx.power
    oname = type(owner).__name__ if owner is not None else ctx.label
    if kind == "turn":
        return ("turn", oname, rnd)
    if kind == "turn_instance":
        return ("ti", id(owner), rnd)
    if kind == "card_play":
        c = ctx.extra.get("_card_obj") or ctx.card
        return ("cp", oname, id(c), getattr(c, "_ym_play_no", 0))
    if kind == "attacker_turn":
        return ("at", oname, id(owner), id(ctx.T), rnd, int(cs.CurrentSide) if cs is not None else 0)
    if kind == "combat":
        return ("c", oname, id(owner))
    raise ValueError(kind)


def _once_ok(ctx, kind):
    if not kind:
        return True
    key = _once_key(ctx, kind)
    st = ctx.state()
    if key in st["once"]:
        return False
    st["once"].add(key)
    return True


def run(ctx, effects):
    for eff in effects:
        if ctx.stop:
            return
        cond = eff.get("if")
        if cond is not None and not ev(cond, ctx):
            continue
        if eff.get("once") and not _once_ok(ctx, eff["once"]):
            continue
        OPS[eff["op"]](ctx, eff)


def compile_effects(effects):
    """展开模板（递归），返回只含基础 op 的列表。"""
    out = []
    for eff in effects or []:
        name = eff.get("template") or eff.get("op")
        if name in S.TEMPLATES:
            out += compile_effects(S.expand_template(eff))
            continue
        e = dict(eff)
        e["op"] = name
        e.pop("template", None)
        for k in ("then", "else", "do", "each_hit"):
            if k in e and e[k] is not None:
                e[k] = compile_effects(e[k])
        out.append(e)
    return out


# ---------------------------------------------------------------- 名字工具
def _camel(cid, prefix=""):
    s = str(cid)
    if prefix and s.upper().startswith(prefix.upper() + "_"):
        s = s[len(prefix) + 1:]
    return prefix + "".join(w[:1].upper() + w[1:].lower() for w in re.split(r"[^0-9A-Za-z]+", s) if w)


def _game_power_cls(pid):
    s = str(pid)
    cands = [s] if s.endswith("Power") else []
    cands.append(_camel(s) + "Power")
    if s.upper().endswith("_POWER"):
        cands.append(_camel(s[:-6]) + "Power")
    for n in cands:
        c = getattr(G, n, None)
        if isinstance(c, type) and issubclass(c, G.PowerModel):
            return c
    return None


def _game_model(name, base):
    for n in (str(name), _camel(name)):
        c = getattr(G, n, None)
        if isinstance(c, type) and issubclass(c, base):
            return c
    return None


def _prop(v):
    f = (lambda self: v) if not callable(v) else v
    return f, G.cs_property(f)


# ---------------------------------------------------------------- mod
class Mod:
    def __init__(self, data, variant=None):
        self.data = data
        self.name = data["name"]
        self.prefix = data.get("prefix") or _camel(self.name)
        self.variant = variant
        self.cards = {c["id"]: c for c in data["cards"]}
        self.powers = {p["id"]: p for p in data["powers"]}
        self.relics = {r["id"]: r for r in data["relics"]}
        self.potions = {p["id"]: p for p in data["potions"]}
        self.card_classes = {}
        self.power_classes = {}
        self.relic_classes = {}
        self.potion_classes = {}
        self.char_classes = {}
        self.registered = []
        self._pcache = {}
        self.py = None
        self.ns = dict(BASE)

    # ---- 查找
    def power_cls(self, pid):
        c = self._pcache.get(pid)
        if c is None:
            c = self.power_classes.get(pid) or _game_power_cls(pid)
            if c is None:
                raise ModFormatError([(f"[{self.name}]", f"找不到能力「{pid}」：这个 mod 里没有定义，游戏里也没有叫这个名字的能力",
                                       f"power '{pid}' not found in this mod or in the game")])
            self._pcache[pid] = c
        return c

    def card_cls(self, cid):
        c = self.card_classes.get(cid) or _game_model(cid, G.CardModel)
        if c is None:
            raise ModFormatError([(f"[{self.name}]", f"找不到卡牌「{cid}」", f"card '{cid}' not found")])
        return c

    def card_entry(self, cid):
        if cid in self.card_classes:
            return G.ModelDb.GetId(self.card_classes[cid]).Entry
        return str(cid)

    def card_vars(self, c):
        return type(c)._ym_varnames

    def py_fn(self, name):
        f = getattr(self.py, name, None) if self.py is not None else None
        if f is None:
            raise ModFormatError([(f"[{self.name}]", f"fullrun_hooks 里找不到函数 {name}", f"function {name} not found in fullrun_hooks")])
        return f

    # ---- 事件：给予 / 清除能力（只有 mod 的 op 会发）
    def _listeners(self, player):
        for pw in list(player.Creature.Powers):
            yield pw
        for r in list(player.Relics):
            yield r

    def fire(self, player, kind, pid, target, n, card, active=True, multi=False):
        for m in self._listeners(player):
            hs = getattr(m, "_ym_ev_" + kind, None)
            if hs:
                for h in hs:
                    h(m, pid, target, n, card, active, multi)

    def modify_apply(self, player, pid, target, n, active, card):
        add = 0
        for m in self._listeners(player):
            hs = getattr(m, "_ym_ev_modify_apply", None)
            if hs:
                for h in hs:
                    add += h(m, pid, target, n, active, card)
        return add

    # ---- 构建
    def build(self):
        self._load_python()
        for pid, p in self.powers.items():
            self._make_power(p)
        for rid, r in self.relics.items():
            self._make_relic(r)
        for pid, p in self.potions.items():
            self._make_potion(p)
        for cid, c in self.cards.items():
            self._make_card(c)
        for cid, ch in self.data["characters"].items():
            self._make_char(ch)
        self._check_refs()
        for t in self.registered:
            G.ModelDb.Inject(t)
            id_ = G.ModelDb.GetId(t)
            G.ModelDb._contentById[id_].InitId(id_)
        chars = [G.ModelDb.Character(_g=(c,)) for c in self.char_classes.values()]
        orig = G.ModelDb._get_AllCharacters

        def all_chars():
            s = orig()
            for c in chars:
                s.Add(c)
            return s
        G.ModelDb.AllCharacters = G.cs_sprop(all_chars)
        G.ModelDb._get_AllCharacters = all_chars
        for attr in ("_allCards", "_allCardPools", "_allCharacterCardPools", "_allRelics", "_allRelicPools",
                     "_allPotions", "_allPotionPools", "_allCharacterPotionPools", "_allCharacterRelicPools"):
            if hasattr(G.ModelDb, attr):
                setattr(G.ModelDb, attr, None)
        from . import run as R
        for cid, cls in self.char_classes.items():
            R.CHARACTERS[cid] = cls
        _patch_ancient_fallbacks()
        self._register_ai()
        _ACTIVE.append(self)
        return dict(self.char_classes)

    def _load_python(self):
        for h in (self.data.get("helpers") or {}).items():
            sig, body = h
            name = re.split(r"[ (]", sig.strip())[0]
            args = re.findall(r"\(([^)]*)\)", sig)
            args = args[0] if args else ""
            self.ns[name] = eval(f"lambda {args}: ({body})", self.ns)
        fn = self.data.get("fullrun_hooks")
        if fn:
            self.py = self._exec_py(fn)
            for k, f in (getattr(self.py, "HELPERS", None) or {}).items():
                self.ns[k] = f
            for k, f in (getattr(self.py, "OPS", None) or {}).items():
                OPS[k] = f

    def _exec_py(self, fn):
        files = self.data.get("files") or {}
        src = files.get(fn)
        d = self.data.get("_dir")
        if src is None and d:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                src = f.read()
        if src is None:
            raise ModFormatError([(f"[{self.name}]", f"找不到 {fn}", f"{fn} not found")])
        mname = f"deckbench_mod_{self.name}_{os.path.splitext(fn)[0]}"
        m = types.ModuleType(mname)
        m.__file__ = os.path.join(d or "", fn)
        m.MOD = self
        m.G = G
        sys.modules[mname] = m
        exec(compile(src, m.__file__, "exec"), m.__dict__)
        return m

    def _check_refs(self):
        probs = []
        for c in self.data["cards"]:
            for eff in _walk(c["_ops"] + (c["_ops_up"] or [])):
                for k in ("power",):
                    if eff.get(k) is not None and eff[k] not in self.power_classes and _game_power_cls(eff[k]) is None:
                        probs.append((f"card {c['id']}", f"能力「{eff[k]}」在这个 mod 和游戏里都找不到（游戏自带的写法例：WEAK、VULNERABLE、STRENGTH）",
                                      f"power '{eff[k]}' not found in this mod or the game (built-in examples: WEAK, VULNERABLE, STRENGTH)"))
                if eff.get("op") == "add_card" and eff["card"] not in self.card_classes and _game_model(eff["card"], G.CardModel) is None:
                    probs.append((f"card {c['id']}", f"卡牌「{eff['card']}」找不到", f"card '{eff['card']}' not found"))
        for ch in self.data["characters"].values():
            for rid in ch["relics"]:
                if rid not in self.relic_classes and _game_model(rid, G.RelicModel) is None:
                    probs.append((f"character {ch['id']}", f"初始遗物「{rid}」在这个 mod 和游戏里都找不到", f"starting relic '{rid}' not found"))
        if probs:
            raise ModFormatError(probs)

    # ---- 能力
    def _class_name(self, spec, suffix, kind):
        if spec.get("class"):
            return spec["class"]
        n = _camel(spec["id"], self.prefix if kind == "card" else "")
        if kind == "card":
            return n if n.startswith(self.prefix) else self.prefix + n
        return self.prefix + n + suffix

    def _triggers(self, spec):
        trs = []
        for t in spec["triggers"]:
            t = S.expand_trigger(t)
            t = dict(t)
            t["do"] = compile_effects(t.get("do"))
            trs.append(t)
        return trs

    def _make_power(self, p):
        mod = self
        name = self._class_name(p, "Power", "power")
        ptype, stack = p["type"], p["stack"]
        ns = {"_cs_name": name, "_get_Type": lambda self: getattr(G.PowerType, ptype),
              "_get_StackType": lambda self: getattr(G.PowerStackType, stack), "_ym_spec": p, "_ym_mod": self}
        ns["Type"] = G.cs_property(ns["_get_Type"])
        ns["StackType"] = G.cs_property(ns["_get_StackType"])
        pvars = {k: _num(v) for k, v in p["vars"].items()}

        def mk(selfp, T=None, gctx=None, extra=None, label=""):
            cr = selfp.Owner
            v = dict(pvars)
            v["amount"] = int(selfp.Amount)
            return Ctx(mod, cr.Player if cr.Player is not None else _any_player(cr), cr, None, None, gctx, T, selfp, v, extra,
                       f"power {p['id']} {label}")
        _install_triggers(ns, self._triggers(p), mk, owner_kind="power", decay=p.get("decay"), expire=p.get("expire"))
        cls = type(G.PowerModel)(name, G._bases(G.PowerModel), ns)
        self.power_classes[p["id"]] = cls
        self.registered.append(cls)

    # ---- 遗物
    def _make_relic(self, r):
        mod = self
        name = self._class_name(r, "", "relic")
        rr = r["rarity"]
        rvars = {k: _num(v) for k, v in r["vars"].items()}

        def rarity(self):
            return getattr(G.RelicRarity, rr)
        ns = {"_cs_name": name, "_get_Rarity": rarity, "Rarity": G.cs_property(rarity), "_ym_spec": r, "_ym_mod": self}

        def mk(selfr, T=None, gctx=None, extra=None, label=""):
            pl = selfr.Owner
            return Ctx(mod, pl, pl.Creature, None, None, gctx, T, selfr, dict(rvars), extra, f"relic {r['id']} {label}")
        _install_triggers(ns, self._triggers(r), mk, owner_kind="relic")
        cls = type(G.RelicModel)(name, G._bases(G.RelicModel), ns)
        self.relic_classes[r["id"]] = cls
        self.registered.append(cls)

    # ---- 药水
    def _make_potion(self, p):
        mod = self
        name = self._class_name(p, "Potion", "potion")
        ops = compile_effects(p["effects"])
        tt = p["target"]
        rar = p["rarity"]
        pvars = {k: _num(v) for k, v in p["vars"].items()}

        def use(selfp, choiceContext, target):
            pl = selfp.Owner
            ctx = Ctx(mod, pl, pl.Creature, None, None, choiceContext, target, selfp, dict(pvars), None, f"potion {p['id']}")
            run(ctx, ops)
        ns = {"_cs_name": name, "_get_Rarity": lambda self: getattr(G.PotionRarity, rar),
              "_get_Usage": lambda self: G.PotionUsage.CombatOnly, "_get_TargetType": lambda self: getattr(G.TargetType, tt),
              "OnUse": use, "_ym_spec": p}
        for k in ("Rarity", "Usage", "TargetType"):
            ns[k] = G.cs_property(ns["_get_" + k])
        cls = type(G.PotionModel)(name, G._bases(G.PotionModel), ns)
        self.potion_classes[p["id"]] = cls
        self.registered.append(cls)

    # ---- 卡牌
    def _make_card(self, spec):
        mod = self
        name = self._class_name(spec, "", "card")
        vars_ = {k: _num(v) for k, v in spec["vars"].items()}
        upv = spec["upgrade"]["vars"]
        deltas = {k: _num(upv[k]) - vars_[k] for k in upv if _num(upv[k]) != vars_.get(k)}
        cost = spec["cost"]
        cost_i = -1 if cost is None else int(cost)
        up_cost = spec["upgrade"].get("cost")
        kws = [getattr(G.CardKeyword, k) for k in spec["keywords"] if k != "Replay"]
        up_add = [getattr(G.CardKeyword, k) for k in spec["upgrade"]["add"] if k != "Replay"]
        up_rm = [getattr(G.CardKeyword, k) for k in spec["upgrade"]["remove"] if k != "Replay"]
        spec["_ops"] = compile_effects(spec["effects"])
        spec["_ops_up"] = compile_effects(spec["upgrade"]["effects"]) if spec["upgrade"].get("effects") is not None else None
        ops, ops_up = spec["_ops"], spec["_ops_up"]
        ctype, crar, ctgt = spec["type"], spec["rarity"], spec["target"]
        varnames = tuple(vars_)
        ctors = {"Damage": lambda v: G.DamageVar(float(v), G.ValueProp.Move),
                 "Block": lambda v: G.BlockVar(float(v), G.ValueProp.Move),
                 "Cards": lambda v: G.CardsVar(int(v)), "Energy": lambda v: G.EnergyVar(int(v))}

        def canon_vars(self):
            return G.Seq([ctors[k](v) if k in ctors else G.DynamicVar(k, float(v)) for k, v in vars_.items()])

        def canon_kw(self):
            return G.HashSet(kws)

        def on_play(self, ctx, cp):
            _PLAY_NO[0] += 1
            self._ym_play_no = _PLAY_NO[0]
            try:
                self._ym_paid = int(self.EnergyCost.GetResolved())
            except Exception:  # noqa
                self._ym_paid = 0
            v = {k: _num(self.DynamicVars[k].BaseValue) for k in varnames}
            v["upgraded"] = bool(self.IsUpgraded)
            c = Ctx(mod, self.Owner, self.Owner.Creature, self, cp, ctx, cp.Target, None, v, None, f"card {spec['id']}")
            st = c.state()
            key = (id(self), c.cs.RoundNumber)
            st["plays"][key] = st["plays"].get(key, 0) + 1
            run(c, ops_up if (ops_up is not None and self.IsUpgraded) else ops)

        def on_upgrade(self):
            for k, d in deltas.items():
                self.DynamicVars[k].UpgradeValueBy(float(d))
            if up_cost is not None and up_cost != cost and cost is not None:
                self.EnergyCost.UpgradeBy(int(up_cost) - int(cost))
            for k in up_add:
                self.AddKeyword(k)
            for k in up_rm:
                self.RemoveKeyword(k)

        def init(self):
            G.CardModel.__init__(self, cost_i, getattr(G.CardType, ctype), getattr(G.CardRarity, crar), getattr(G.TargetType, ctgt))

        def after_played(self, context, cardPlay):
            if getattr(self, "_ym_return", False) and cardPlay.Card is self:
                self._ym_return = False
                G.CardPileCmd.Add(self, G.PileType.Hand)

        up_name = spec["upgrade"].get("name")

        def display_name(self):
            return up_name if (up_name and self.IsUpgraded) else spec["name"]

        ns = {"_cs_name": name, "_get_CanonicalVars": canon_vars, "CanonicalVars": G.cs_property(canon_vars),
              "_get_ModName": display_name, "ModName": G.cs_property(display_name),
              "_get_ClaudeName": display_name, "ClaudeName": G.cs_property(display_name),
              "AfterCardPlayed": after_played, "OnPlay": on_play, "OnUpgrade": on_upgrade, "__init__": init,
              "_ym_spec": spec, "_ym_id": spec["id"], "_ym_varnames": varnames, "_ym_mod": self,
              "_claude_spec": {"name": spec["name"], **({"up_name": up_name} if up_name else {})}, "_claude_id": spec["id"]}
        if kws:
            ns["_get_CanonicalKeywords"] = canon_kw
            ns["CanonicalKeywords"] = G.cs_property(canon_kw)
        tags = [getattr(G.CardTag, t) for t in spec.get("tags") or [] if hasattr(G.CardTag, t)]
        if tags:
            ns["_get_CanonicalTags"] = lambda self: G.HashSet(tags)
            ns["CanonicalTags"] = G.cs_property(ns["_get_CanonicalTags"])
        cls = META(name, G._bases(G.CardModel), ns)
        self.card_classes[spec["id"]] = cls
        self.registered.append(cls)

    # ---- 角色
    def _make_char(self, ch):
        cid = ch["id"]
        cname = ch.get("class") or (self.prefix + _camel(cid) if not _camel(cid).startswith(self.prefix) else _camel(cid)) + "Character"
        if ch.get("class"):
            cname = ch["class"]
        base = _game_model(ch.get("base") or "Ironclad", G.CharacterModel) or G.Ironclad
        pool_cards = [self.card_classes[c["id"]] for c in self.data["cards"] if c["pool"] and c["rarity"] not in ("Token", "Status", "Curse")]
        relics = [self.relic_classes[r["id"]] for r in self.data["relics"] if r.get("pool", True)]
        potions = list(self.potion_classes.values())
        deck = []
        for item in ch["starting_deck"]:
            c, n, up = S.parse_deck_item(item)
            deck += [(self.card_classes[c], up)] * n
        srel = [self.relic_classes.get(r) or _game_model(r, G.RelicModel) for r in ch["relics"]]
        pre = cname.replace("Character", "") if cname.endswith("Character") else cname

        def _cls(name, basecls, **members):
            ns = {"_cs_name": name}
            for k, v in members.items():
                if k.startswith("P_"):
                    g, pr = _prop(v)
                    ns["_get_" + k[2:]] = g
                    ns[k[2:]] = pr
                else:
                    ns[k] = v
            c = type(basecls)(name, G._bases(basecls), ns)
            self.registered.append(c)
            return c
        pfx = ch.get("pool_prefix") or (self.prefix if not ch.get("class") else re.sub(r"(Chan|Character)$", "", cname))
        CardPool = _cls(pfx + "CardPool", G.CardPoolModel, P_Title=self.prefix.lower(), P_EnergyColorName="ironclad",
                        P_IsColorless=False,
                        GenerateAllCards=lambda self: G.Seq([G.ModelDb.Card(_g=(c,)) for c in pool_cards]),
                        FilterThroughEpochs=lambda self, unlockState, cards: cards.ToList())
        RelicPool = _cls(pfx + "RelicPool", G.RelicPoolModel, P_EnergyColorName="ironclad",
                         GenerateAllRelics=lambda self: G.Seq([G.ModelDb.Relic(_g=(r,)) for r in relics]),
                         GetUnlockedRelics=lambda self, unlockState: self.AllRelics.ToList())
        PotionPool = _cls(pfx + "PotionPool", G.PotionPoolModel, P_EnergyColorName="ironclad",
                          GenerateAllPotions=lambda self: G.Seq([G.ModelDb.Potion(_g=(p,)) for p in potions]),
                          GetUnlockedPotions=lambda self, unlockState: G.Seq([G.ModelDb.Potion(_g=(p,)) for p in potions]))
        hp, gold, energy = int(ch["hp"]), int(ch.get("gold", 99)), int(ch.get("energy", 3))

        def starting_deck(self):
            out = []
            for c, up in deck:
                m = G.ModelDb.Card(_g=(c,))
                out.append(m)
            return G.Seq(out)
        members = dict(P_StartingHp=hp, P_StartingGold=gold,
                       P_CardPool=lambda self: G.ModelDb.CardPool(_g=(CardPool,)),
                       P_PotionPool=lambda self: G.ModelDb.PotionPool(_g=(PotionPool,)),
                       P_RelicPool=lambda self: G.ModelDb.RelicPool(_g=(RelicPool,)),
                       P_StartingDeck=starting_deck,
                       P_StartingRelics=lambda self: G.Seq([G.ModelDb.Relic(_g=(r,)) for r in srel]),
                       P_UnlocksAfterRunAs=None)
        if energy != 3:
            members["P_MaxEnergy"] = energy
        Char = _cls(cname, base, **members)
        Char._ym_mod = self
        self.char_classes[cid] = Char
        _YAML_CHARS.add(Char)

    # ---- AI
    def _register_ai(self):
        from . import strong as SG
        from . import search as SE
        for c in self.data["cards"]:
            ai = c.get("ai") or {}
            if "value" in ai:
                ent = G.ModelDb.GetId(self.card_classes[c["id"]]).Entry
                tags = ai.get("tags") or ""
                SG.MOD_POWER[ent] = (float(ai["value"]), set(tags.split() if isinstance(tags, str) else tags))
        for pid, per in (self.data.get("ai_values") or {}).items():
            if pid in self.power_classes:
                ent = G.ModelDb.GetId(self.power_classes[pid]).Entry
                per = float(per)
                if per:
                    SE.POWER_VALUE[ent] = (lambda per: lambda a, e, k, fl: min(a * per, float(e.CurrentHp)) * k)(per)
        fn = self.data.get("ai_hooks")
        if fn:
            m = self._exec_py(fn)
            if hasattr(m, "register"):
                m.register(self)


_YAML_CHARS = set()


def _walk(effs):
    for e in effs or []:
        yield e
        for k in ("then", "else", "do", "each_hit"):
            yield from _walk(e.get(k))


def _any_player(cr):
    try:
        for p in G._iter(cr.CombatState.Players):
            return p
    except Exception:  # noqa
        return None


def _install_triggers(ns, trs, mk, owner_kind, decay=None, expire=None):
    """把触发器装成游戏钩子方法。mk(self, T, gctx, extra, label) -> Ctx。"""
    by = {}
    for t in trs:
        by.setdefault(t["on"], []).append(t)

    def owner_cr(selfm):
        return selfm.Owner if owner_kind == "power" else selfm.Owner.Creature

    def fire_list(selfm, lst, T=None, gctx=None, extra=None):
        for t in lst:
            c = mk(selfm, T, gctx, extra, t["on"])
            if t.get("if") is not None and not ev(t["if"], c):
                continue
            if t.get("once") and not _once_ok(c, t["once"]):
                continue
            run(c, t["do"])

    ts, te = by.get("turn_start", []), by.get("turn_end", [])
    if ts or decay == "turn_start" or expire == "turn_start":
        def after_turn_start(selfm, side, *rest):
            if side != owner_cr(selfm).Side:
                return
            fire_list(selfm, ts)
            if owner_kind == "power":
                if expire == "turn_start":
                    G.PowerCmd.Remove(selfm)
                elif decay == "turn_start":
                    G.PowerCmd.Decrement(selfm)
        ns["AfterSideTurnStart"] = after_turn_start
    if te or decay == "turn_end" or expire == "turn_end":
        def before_turn_end(selfm, choiceContext, side, *rest):
            if side != owner_cr(selfm).Side:
                return
            fire_list(selfm, te, gctx=choiceContext)
            if owner_kind == "power":
                if expire == "turn_end":
                    G.PowerCmd.Remove(selfm)
                elif decay == "turn_end":
                    G.PowerCmd.Decrement(selfm)
        ns["BeforeSideTurnEnd"] = before_turn_end
    if by.get("battle_start"):
        lst = by["battle_start"]

        def before_combat(selfm):
            fire_list(selfm, lst)
        ns["BeforeCombatStart"] = before_combat
    att = by.get("attacked", [])
    for timing, hook in (("before", "BeforeDamageReceived"), ("after", "AfterDamageReceived")):
        lst = [t for t in att if t.get("timing", "after") == timing]
        if not lst:
            continue

        def on_dmg(selfm, ctx, target, amount, props, dealer, cardSource, _lst=lst, _timing=timing):
            me = owner_cr(selfm)
            if target != me or dealer is None or dealer.Side == me.Side or not dealer.IsAlive:
                return
            if not props.IsPoweredAttack():
                return
            ex = {"damage": _num(amount) if _timing == "before" else _num(getattr(amount, "UnblockedDamage", 0))}
            fire_list(selfm, _lst, T=dealer, gctx=ctx, extra=ex)
        ns[hook] = on_dmg
    cp = by.get("card_played", [])
    if cp:
        def after_card_played(selfm, choiceContext, cardPlay):
            card = cardPlay.Card
            me = owner_cr(selfm)
            if card is None or card.Owner is None or card.Owner.Creature is not me:
                return
            for t in cp:
                ct = t.get("card_type", "any")
                if ct != "any" and card.Type != getattr(G.CardType, ct):
                    continue
                every = int(t.get("every", 1) or 1)
                if every > 1:
                    cnt = getattr(selfm, "_ym_count", {})
                    k = id(t)
                    cnt[k] = cnt.get(k, 0) + 1
                    selfm._ym_count = cnt
                    if cnt[k] % every:
                        continue
                c = mk(selfm, cardPlay.Target, choiceContext, {"_card_obj": card, "card_paid": getattr(card, "_ym_paid", 0)}, "card_played")
                if t.get("if") is not None and not ev(t["if"], c):
                    continue
                if t.get("once") and not _once_ok(c, t["once"]):
                    continue
                run(c, t["do"])
        ns["AfterCardPlayed"] = after_card_played
    sr = by.get("stacks_reach", [])
    if sr and owner_kind == "power":
        def after_amount(selfm, choiceContext, power, amount, applier, cardSource):
            if power is not selfm or getattr(selfm, "_ym_busy", False):
                return
            for t in sr:
                n = int(t["n"])
                if int(selfm.Amount) >= n:
                    selfm._ym_busy = True
                    try:
                        c = mk(selfm, None, choiceContext, None, "stacks_reach")
                        if t.get("if") is None or ev(t["if"], c):
                            run(c, t["do"])
                        r = t.get("reset", "subtract")
                        if r == "remove":
                            G.PowerCmd.Remove(selfm)
                        elif r == "subtract":
                            G.PowerCmd.ModifyAmount(_noctx(), selfm, float(-n), selfm.Owner, None)
                    finally:
                        selfm._ym_busy = False
        ns["AfterPowerAmountChanged"] = after_amount
    for kind in ("power_applied", "power_removed"):
        lst = by.get(kind, [])
        if not lst:
            continue

        def make_h(t):
            def h(selfm, pid, target, n, card, active, multi):
                if t.get("power") and t["power"] != pid:
                    return
                if t.get("active_only") and not active:
                    return
                c = mk(selfm, target, None, {"n": n, "active": active, "multi": multi, "_card_obj": card,
                                             "card_paid": getattr(card, "_ym_paid", 0) if card is not None else 0}, t["on"])
                c.card = None
                c.extra["card"] = card
                if t.get("if") is not None and not ev(t["if"], c):
                    return
                if t.get("once") and not _once_ok(c, t["once"]):
                    return
                run(c, t["do"])
            return h
        ns["_ym_ev_" + kind] = [make_h(t) for t in lst]
    ma = by.get("modify_apply", [])
    if ma:
        def make_m(t):
            def h(selfm, pid, target, n, active, card):
                if t["power"] != pid:
                    return 0
                c = mk(selfm, target, None, {"n": n, "active": active}, "modify_apply")
                if t.get("if") is not None and not ev(t["if"], c):
                    return 0
                if t.get("once") and not _once_ok(c, t["once"]):
                    return 0
                return int(ev(t["add"], c))
            return h
        ns["_ym_ev_modify_apply"] = [make_m(t) for t in ma]
    md = by.get("modify_damage", [])
    if md:
        adds = [t for t in md if t.get("add") is not None]
        mults = [t for t in md if t.get("mult") is not None]

        def ok(selfm, dealer, cardSource, props):
            return dealer == owner_cr(selfm) and cardSource is not None and props.IsPoweredAttack()
        if adds:
            def mod_add(selfm, target, amount, props, dealer, cardSource, cardPlay=None):
                if not ok(selfm, dealer, cardSource, props):
                    return 0.0
                tot = 0.0
                for t in adds:
                    c = mk(selfm, target, None, {"damage": _num(amount)}, "modify_damage")
                    if t.get("if") is None or ev(t["if"], c):
                        tot += float(ev(t["add"], c))
                return tot
            ns["ModifyDamageAdditive"] = mod_add
        if mults:
            def mod_mul(selfm, target, amount, props, dealer, cardSource, cardPlay=None):
                if not ok(selfm, dealer, cardSource, props):
                    return 1.0
                m = 1.0
                for t in mults:
                    c = mk(selfm, target, None, {"damage": _num(amount)}, "modify_damage")
                    if t.get("if") is None or ev(t["if"], c):
                        m *= float(ev(t["mult"], c))
                return m
            ns["ModifyDamageMultiplicative"] = mod_mul
    mb = by.get("modify_block", [])
    if mb:
        def mod_block(selfm, target, block, props, cardSource, cardPlay=None):
            if target != owner_cr(selfm) or cardSource is None:
                return 0.0
            tot = 0.0
            for t in mb:
                c = mk(selfm, None, None, {"damage": 0}, "modify_block")
                if t.get("if") is None or ev(t["if"], c):
                    tot += float(ev(t["add"], c))
            return tot
        ns["ModifyBlockAdditive"] = mod_block
    ed = by.get("enemy_died", [])
    if ed:
        def after_death(selfm, choiceContext, creature, *rest):
            if creature.Side == owner_cr(selfm).Side:
                return
            fire_list(selfm, ed, T=creature, gctx=choiceContext)
        ns["AfterDeath"] = after_death
    ex = by.get("card_exhausted", [])
    if ex:
        def after_exhaust(selfm, choiceContext, card, causedByEthereal=False):
            if card.Owner is None or card.Owner.Creature is not owner_cr(selfm):
                return
            fire_list(selfm, ex, gctx=choiceContext, extra={"_card_obj": card})
        ns["AfterCardExhausted"] = after_exhaust
    pc = by.get("play_count", [])
    if pc:
        def mod_play_count(selfm, card, target, playCount):
            if card is None or card.Owner is None or card.Owner.Creature is not owner_cr(selfm):
                return playCount
            for t in pc:
                ct = t.get("card_type", "Attack")
                if ct != "any" and card.Type != getattr(G.CardType, ct):
                    continue
                c = mk(selfm, target, None, {"_card_obj": card}, "play_count")
                if t.get("if") is not None and not ev(t["if"], c):
                    continue
                if t.get("once") and not _once_ok(c, t["once"]):
                    continue
                playCount += int(t.get("extra", 1))
            return playCount
        ns["ModifyCardPlayCount"] = mod_play_count


def _patch_ancient_fallbacks():
    """模组卡池没有「远古」稀有度的牌时：古代事件遗物「积灰的典籍」改为从稀有牌中抽（近似）。"""
    orig = G.DustyTome.SetupForPlayer
    if getattr(orig, "_ym", False):
        return

    def setup(self, player):
        if type(player.Character) not in _YAML_CHARS:
            return orig(self, player)
        cards = G.Seq(player.Character.CardPool.AllCards)
        anc = cards.Where(lambda c: c.Rarity == G.CardRarity.Ancient)
        items = anc if anc.Any() else cards.Where(lambda c: c.Rarity == G.CardRarity.Rare)
        self.AncientCard = player.PlayerRng.Rewards.NextItem(items).Id
    setup._ym = True
    G.DustyTome.SetupForPlayer = setup


# ---------------------------------------------------------------- 入口
def apply_variant(data, variant):
    """variants: {名字: {cards: {ID: {vars: {...}, cost: n, ...}}, hp: n, starting_deck: [...], add_cards: [文件]}}；多个用 + 连接。"""
    if not variant:
        return data
    import copy
    d = copy.deepcopy(data)
    for v in variant.split("+"):
        if v not in d.get("variants", {}):
            raise ModFormatError([(f"[{d['name']}]", f"没有叫「{v}」的变体（有：{', '.join(d.get('variants', {})) or '无'}）",
                                   f"no variant named '{v}' (available: {', '.join(d.get('variants', {})) or 'none'})")])
        over = d["variants"][v] or {}
        byid = {c["id"]: c for c in d["cards"]}
        for f in over.get("add_cards") or []:
            raw = S._y(d["files"][f], f) or []
            for c in raw:
                nc = S._norm_card(c)
                if nc["id"] in byid:
                    d["cards"][d["cards"].index(byid[nc["id"]])] = nc
                else:
                    d["cards"].append(nc)
                byid[nc["id"]] = nc
        for cid, o in (over.get("cards") or {}).items():
            if cid not in byid:
                nc = S._norm_card(dict(o, id=cid))
                d["cards"].append(nc)
                byid[cid] = nc
                continue
            c = byid[cid]
            for k, val in o.items():
                if k == "vars":
                    c["vars"].update(val)
                elif k == "upgrade":
                    up = val or {}
                    c["upgrade"]["vars"].update(up.get("vars") or {})
                    for kk in ("cost", "effects", "name"):
                        if kk in up:
                            c["upgrade"][kk] = up[kk]
                elif k == "keywords":
                    c["keywords"] = S._kw_list(val)
                elif k in ("type", "rarity", "target"):
                    c[k] = {"type": S.norm_type, "rarity": S.norm_rarity, "target": S.norm_target}[k](val)
                else:
                    c[k] = val
        for ch in d["characters"].values():
            if "hp" in over:
                ch["hp"] = int(over["hp"])
            if "starting_deck" in over:
                ch["starting_deck"] = list(over["starting_deck"])
            if "energy" in over:
                ch["energy"] = int(over["energy"])
    return d


def load(src, variant=None, strict=True):
    """注册一个 YAML mod。src：文件夹路径，或 load_mod_files 的结果。返回 {角色 ID: 角色类}。"""
    if isinstance(src, str):
        key = (os.path.abspath(src), variant or "")
        if key in _LOADED:
            return dict(_LOADED[key].char_classes)
        data = S.load_mod_dir(src)
    else:
        data = src
        key = (data.get("_dir") or data["name"], variant or "")
        if key in _LOADED:
            return dict(_LOADED[key].char_classes)
    data = apply_variant(data, variant)
    problems, _warnings = S.validate(data, fullrun=True)
    if problems and strict:
        raise ModFormatError(problems)
    mod = Mod(data, variant)
    chars = mod.build()
    _LOADED[key] = mod
    return chars


def loaded():
    return list(_ACTIVE)


def find_mod_for_char(char):
    for m in _ACTIVE:
        if char in m.char_classes:
            return m
    return None
