"""卡表里的数值表达式求值。

YAML 里的 amount/cond 等字段可以写数字，也可以写 Python 表达式字符串，例如
"dmg + 2*min(stacks(T,'FK'), 4)"。表达式可用的名字：
  - 卡牌的 vars（升级后自动替换）以及本次结算中 set 出来的局部变量
  - T 当前目标（敌人或玩家），P 玩家，C 战斗对象，card 当前卡牌
  - 内置辅助函数（见 BASE）和各 mod 在 hooks.py 里用 register_helper 注册的函数
求值前解释器会把当前上下文放进 CUR，辅助函数可以通过 cur() 取到。
"""
import math

_CACHE = {}
CUR = [None]
HELPERS = {}


def cur():
    return CUR[0]


def register_helper(name, fn):
    HELPERS[name] = fn
    return fn


def _stacks(c, pid):
    return c.amt(pid) if c is not None else 0


def _intent(c=None):
    """目标当前意图对玩家的攻击总伤害（含多段、力量、虚弱、易伤修正后的预计值）。"""
    ctx = cur()
    c = c if c is not None else ctx.target
    if c is None or c.is_player:
        return 0
    return ctx.combat.predict_intent_damage(c)


def _attacking(c=None):
    ctx = cur()
    c = c if c is not None else ctx.target
    return bool(c is not None and not c.is_player and c.intent_is_attack())


BASE = {
    "min": min, "max": max, "abs": abs, "int": int, "floor": math.floor, "ceil": math.ceil,
    "len": len, "sum": sum, "any": any, "all": all, "True": True, "False": False, "None": None,
    "stacks": _stacks,
    "intent_damage": _intent,
    "attacking": _attacking,
    "hand_size": lambda: len(cur().combat.player.hand),
    "n_enemies": lambda: len(cur().combat.alive_enemies()),
    "energy": lambda: cur().combat.player.energy,
    "block": lambda c=None: (c or cur().combat.player).block,
    "hand_has": lambda cid: any(x.id == cid for x in cur().combat.player.hand),
    "turn": lambda: cur().combat.turn,
}


def ev(x, ctx, extra=None):
    if isinstance(x, (int, float, bool)) or x is None:
        return x
    if not isinstance(x, str):
        return x
    code = _CACHE.get(x)
    if code is None:
        code = compile(x, "<expr>", "eval")
        _CACHE[x] = code
    ns = dict(BASE)
    ns.update(HELPERS)
    ns.update(ctx.vars)
    ns.update(ctx.locals)
    ns["T"] = ctx.target
    ns["P"] = ctx.combat.player
    ns["C"] = ctx.combat
    ns["card"] = ctx.card
    ns["ctx"] = ctx
    if extra:
        ns.update(extra)
    prev = CUR[0]
    CUR[0] = ctx
    try:
        return eval(code, {"__builtins__": {}}, ns)
    finally:
        CUR[0] = prev
