"""卡牌定义（来自 YAML）和效果解释器。

一张卡的 YAML：
  - id: 已核实
    name: 已核实
    type: 攻击            # 攻击 / 技能 / 能力 / 状态 / 诅咒
    rarity: 基础
    cost: 1               # null = 不能被打出；"X" = X 费
    target: enemy         # enemy / all / self / random / none
    keywords: []          # exhaust 消耗 / ethereal 虚无 / retain 保留 / innate 固有 / unplayable 不能被打出
    vars: {dmg: 5, per: 2, cap: 4}
    upgrade: {vars: {dmg: 7, per: 3}, cost: 0, add: [retain], remove: [exhaust]}
    effects:
      - {op: damage, amount: "dmg + per*min(stacks(T,'FK'),cap)"}
      - {op: remove_power, power: FK, save: cleared}
    text: 原文说明（报告里显示）
  可选：can_play: hooks 函数名；cost_expr: 动态费用表达式；ai: {...} 给 AI 的提示。

效果 op（都可以带 if: 条件表达式）：
  damage        amount, hits=1, target=target|all|random|others|self|player, kind=attack|power|hp_loss, save
  block         amount
  apply         power, amount, target, secondary=false   （对敌人施加负面效果 / 给自己加能力）
  remove_power  power, amount（不写=全部）, target, save（实际移除层数存入局部变量）
  set_stacks    power, value, target, artifact_blocks=false, op（层数操作，不算施加/清除）
  draw          n
  energy        n
  lose_hp       amount（玩家自己）
  heal          amount
  add_card      card, n=1, to=hand|draw|discard, upgraded=false, free_turn=false
  set           name, value（局部变量）
  if            cond, then: [...], else: [...]
  foreach       target=all|others, do: [...]（循环内 T 是当前敌人）
  repeat        n, do: [...]
  exhaust_choice n=1, filter（AI 选择手牌消耗）
  discard_choice n=1
  return_to_hand（这张牌结算后回到手牌）
  end_turn
  py            fn（hooks.py 里的函数名，签名 fn(ctx, **参数)）
"""
from types import SimpleNamespace
from . import expr

KW_MAP = {"消耗": "exhaust", "虚无": "ethereal", "保留": "retain", "固有": "innate", "不能被打出": "unplayable"}


class CardDef:
    def __init__(self, raw, mod_name=""):
        self.raw = raw
        self.id = raw["id"]
        self.name = raw.get("name", self.id)
        self.type = raw.get("type", "技能")
        self.rarity = raw.get("rarity", "普通")
        self.mod = mod_name
        c = raw.get("cost", 1)
        self.cost_x = c == "X"
        self.cost = 0 if self.cost_x else c
        up = raw.get("upgrade") or {}
        self.cost_up = up.get("cost", self.cost)
        self.cost_expr = raw.get("cost_expr")
        self.target = raw.get("target", "none")
        kw = set(KW_MAP.get(k, k) for k in (raw.get("keywords") or []))
        if self.cost is None:
            kw.add("unplayable")
        self.kw = frozenset(kw)
        kwu = set(kw)
        for k in up.get("add", []) or []:
            kwu.add(KW_MAP.get(k, k))
        for k in up.get("remove", []) or []:
            kwu.discard(KW_MAP.get(k, k))
        self.kw_up = frozenset(kwu)
        self.vars = dict(raw.get("vars") or {})
        self.vars_up = dict(self.vars)
        self.vars_up.update(up.get("vars") or {})
        self.effects = raw.get("effects") or []
        self.effects_up = up.get("effects") or self.effects
        self.can_play = raw.get("can_play")
        self.text = raw.get("text", "")
        self.text_up = raw.get("text_up", "")
        self.tags = set(raw.get("tags") or [])
        self.archetype = raw.get("archetype", "")
        self.ai = raw.get("ai") or {}
        self.pool = raw.get("pool", True)
        self.hits_hint = raw.get("multi_hit", None)


class PlayCtx:
    """一次打出（含重放）的结算上下文。"""
    def __init__(self, combat, card, target, paid, free=False):
        self.combat = combat
        self.card = card
        self.target = target
        self.chosen_target = target
        self.paid = paid
        self.free = free
        self.vars = card.vars if card is not None else {}
        self.locals = {}
        self.return_to_hand = False
        self.force_exhaust = False
        self.end_turn = False
        self.replay_index = 0
        self.flags = {}
        self.extra_hits = 0


def _targets(ctx, spec):
    C = ctx.combat
    if spec in (None, "target"):
        t = ctx.target
        if t is None or (not t.is_player and not t.alive):
            # 原目标死亡：重放/后续效果改打随机敌人
            t = C.random_enemy() if ctx.card is not None and ctx.card.d.target == "enemy" else t
            ctx.target = t
        return [t] if t is not None else []
    if spec in ("self", "player"):
        return [C.player]
    if spec == "all":
        return C.alive_enemies()
    if spec == "others":
        return [e for e in C.alive_enemies() if e is not ctx.target]
    if spec == "random":
        e = C.random_enemy()
        return [e] if e else []
    if spec == "random_other":
        e = C.random_enemy(exclude=ctx.target)
        return [e] if e else []
    raise ValueError(f"未知目标 {spec}")


def run_effects(ctx, effects):
    C = ctx.combat
    for eff in effects:
        if C.result is not None:
            return
        cond = eff.get("if")
        if cond is not None and not expr.ev(cond, ctx):
            continue
        op = eff["op"]
        f = OPS.get(op)
        if f is None:
            raise ValueError(f"未知 op: {op}（卡 {ctx.card.id if ctx.card else '?'}）")
        f(ctx, eff)
        if ctx.end_turn:
            return


def _with_T(ctx, t):
    old = ctx.target
    ctx.target = t
    return old


def op_damage(ctx, eff):
    C = ctx.combat
    spec = eff.get("target", "target")
    hits_expr = eff.get("hits", 1)
    total = 0
    kind = eff.get("kind", "attack" if (ctx.card is not None and ctx.card.type == "攻击") else "power")
    src = C.player
    if spec in ("random",):
        hits = int(expr.ev(hits_expr, ctx))
        if hits > 1:
            hits += ctx.extra_hits
            ctx.extra_hits = 0
        for _ in range(hits):
            e = C.random_enemy()
            if e is None:
                break
            old = _with_T(ctx, e)
            amt = expr.ev(eff["amount"], ctx)
            total += C.deal_damage(src, e, amt, kind, ctx.card, ctx)
            ctx.target = old
    else:
        tgts = _targets(ctx, spec)
        multi_target = spec not in ("target", None)
        for t in tgts:
            if t is None or not t.alive:
                continue
            old = _with_T(ctx, t) if multi_target else None
            hits = int(expr.ev(hits_expr, ctx))
            if hits > 1:
                hits += ctx.extra_hits
            for _ in range(hits):
                if not t.alive:
                    break
                amt = expr.ev(eff["amount"], ctx)
                total += C.deal_damage(src, t, amt, kind, ctx.card, ctx)
                if eff.get("each_hit"):
                    run_effects(ctx, eff["each_hit"])
            if multi_target:
                ctx.target = old
        if int(expr.ev(hits_expr, ctx)) > 1:
            ctx.extra_hits = 0
    if eff.get("save"):
        ctx.locals[eff["save"]] = total


def op_block(ctx, eff):
    ctx.combat.gain_block(ctx.combat.player, expr.ev(eff["amount"], ctx), from_card=eff.get("from_card", True))


def _source(ctx):
    if ctx.card is not None:
        return ("card", ctx.card)
    return ctx.flags.get("source", ("power", None))


def op_apply(ctx, eff):
    C = ctx.combat
    spec = eff.get("target", "target")
    multi = eff.get("multi", spec in ("all", "others"))
    for t in _targets(ctx, spec):
        if t is None or not t.alive:
            continue
        old = _with_T(ctx, t)
        n = int(expr.ev(eff["amount"], ctx))
        d = C.apply_power(t, eff["power"], n, source=_source(ctx), secondary=eff.get("secondary", False),
                          multi=multi, src_name=eff.get("src_name") or (ctx.card.base_name if ctx.card else None),
                          **(eff.get("params") or {}))
        ctx.target = old
        if eff.get("save"):
            ctx.locals[eff["save"]] = ctx.locals.get(eff["save"], 0) + d


def op_remove(ctx, eff):
    C = ctx.combat
    total = 0
    for t in _targets(ctx, eff.get("target", "target")):
        if t is None:
            continue
        n = eff.get("amount")
        n = None if n in (None, "all") else int(expr.ev(n, ctx))
        total += C.remove_power(t, eff["power"], n, source=_source(ctx))
    if eff.get("save"):
        ctx.locals[eff["save"]] = total


def op_set_stacks(ctx, eff):
    C = ctx.combat
    for t in _targets(ctx, eff.get("target", "target")):
        if t is None:
            continue
        old = _with_T(ctx, t)
        v = expr.ev(eff["value"], ctx)
        ctx.target = old
        C.set_stacks(t, eff["power"], v, op=eff.get("op_name", "set"), artifact_blocks=eff.get("artifact_blocks", False))


def op_draw(ctx, eff):
    ctx.combat.draw(int(expr.ev(eff["n"], ctx)))


def op_energy(ctx, eff):
    ctx.combat.player.energy += int(expr.ev(eff["n"], ctx))


def op_lose_hp(ctx, eff):
    C = ctx.combat
    C.lose_hp(C.player, int(expr.ev(eff["amount"], ctx)), None, "hp_loss")


def op_heal(ctx, eff):
    P = ctx.combat.player
    P.hp = min(P.max_hp, P.hp + int(expr.ev(eff["amount"], ctx)))


def op_add_card(ctx, eff):
    ctx.combat.add_card(eff["card"], to=eff.get("to", "hand"), upgraded=bool(expr.ev(eff.get("upgraded", False), ctx)),
                        n=int(expr.ev(eff.get("n", 1), ctx)), free_turn=eff.get("free_turn", False))


def op_set(ctx, eff):
    ctx.locals[eff["name"]] = expr.ev(eff["value"], ctx)


def op_if(ctx, eff):
    if expr.ev(eff["cond"], ctx):
        run_effects(ctx, eff.get("then") or [])
    else:
        run_effects(ctx, eff.get("else") or [])


def op_foreach(ctx, eff):
    for t in list(_targets(ctx, eff.get("target", "all"))):
        if t is None or not t.alive:
            continue
        old = _with_T(ctx, t)
        run_effects(ctx, eff["do"])
        ctx.target = old


def op_repeat(ctx, eff):
    for _ in range(int(expr.ev(eff["n"], ctx))):
        run_effects(ctx, eff["do"])


def op_exhaust_choice(ctx, eff):
    C = ctx.combat
    n = int(expr.ev(eff.get("n", 1), ctx))
    opts = [c for c in C.player.hand]
    picks = C.agent.choose_cards(C, "exhaust", opts, n, ctx) if opts else []
    for c in picks:
        C.player.hand.remove(c)
        C.exhaust(c)
    if eff.get("save"):
        ctx.locals[eff["save"]] = len(picks)


def op_discard_choice(ctx, eff):
    C = ctx.combat
    n = int(expr.ev(eff.get("n", 1), ctx))
    opts = list(C.player.hand)
    picks = C.agent.choose_cards(C, "discard", opts, n, ctx) if opts else []
    for c in picks:
        C.discard_from_hand(c)


def op_return(ctx, eff):
    ctx.return_to_hand = True


def op_end_turn(ctx, eff):
    ctx.end_turn = True


def op_py(ctx, eff):
    params = {k: v for k, v in eff.items() if k not in ("op", "fn", "if")}
    ctx.combat.mod.call(eff["fn"], ctx, **params)


OPS = {
    "damage": op_damage, "block": op_block, "apply": op_apply, "remove_power": op_remove,
    "set_stacks": op_set_stacks, "draw": op_draw, "energy": op_energy, "lose_hp": op_lose_hp, "heal": op_heal,
    "add_card": op_add_card, "set": op_set, "if": op_if, "foreach": op_foreach, "repeat": op_repeat,
    "exhaust_choice": op_exhaust_choice, "discard_choice": op_discard_choice, "return_to_hand": op_return,
    "end_turn": op_end_turn, "py": op_py,
}


def register_op(name, fn):
    OPS[name] = fn


def play_card(C, card, target, free=False, from_hand=True):
    P = C.player
    cost = C.card_cost(card)
    if card.d.cost_x:
        paid = P.energy
    else:
        paid = 0 if free else cost
    P.energy -= paid
    if from_hand and card in P.hand:
        P.hand.remove(card)
    ctx = PlayCtx(C, card, target, paid, free)
    if card.d.cost_x:
        ctx.locals["X"] = paid
    C.play_stack.append(ctx)
    C.push_attr(card.base_name)
    first_this_turn = card.played_turn != C.turn
    ctx.locals["first_play_this_turn"] = first_this_turn
    card.played_turn = C.turn
    C.cards_played_turn.append(card)
    if C.stats is not None:
        C.stats.rec(card.base_name, plays=1, energy=paid)
    C.say(f"打出 {card.name}" + (f" → {target.name}" if target is not None else "") + f"（付{paid}，剩{P.energy}）")
    C.emit("before_play", card=card, ctx=ctx)
    ev = C.emit("modify_play_count", card=card, ctx=ctx, count=1)
    effects = card.d.effects_up if card.upgraded else card.d.effects
    for i in range(max(1, ev.count)):
        ctx.replay_index = i
        if i > 0:
            ctx.target = ctx.chosen_target
            ctx.locals = {"first_play_this_turn": first_this_turn}
        run_effects(ctx, effects)
        if C.result is not None or ctx.end_turn:
            break
    C.pop_attr()
    C.play_stack.pop()
    # 去向
    if card.type == "能力":
        pass
    elif ctx.return_to_hand and not (card.has_kw("exhaust") or ctx.force_exhaust):
        if len(P.hand) < 10:
            P.hand.append(card)
        else:
            P.discard.append(card)
    elif card.has_kw("exhaust") or ctx.force_exhaust:
        C.exhaust(card)
    else:
        P.discard.append(card)
    C.emit("after_play", card=card, ctx=ctx)
    if ctx.end_turn:
        C.data["_force_end_turn"] = True
    return ctx
