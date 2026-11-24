"""愚者（Fool）决策修正。只在当前角色是 Fool 时生效，不改其他角色的估值。

出牌侧：没有空箭槽的射击打出也不造成伤害；滑溜把每段生命伤害封顶为 1，这时把瞄准射进去等于浪费。
有瞄准且滑溜已剥开时，先打倍率更高的射击，能量够就先上瞄准再射。
选牌加分（多拿瞄准、少拿悲伤）在固定调参种子上没有提高一幕通过率，这里不加。
"""
import inspect

from .agents import card_cost, dvar

_SRC = {}


def is_fool(player):
    ch = getattr(player, "Character", None)
    if ch is None:
        return False
    return getattr(ch, "_cs_name", type(ch).__name__) == "Fool"


def is_shoot(card):
    tags = getattr(card, "Tags", None)
    if tags is None:
        return False
    try:
        return any(getattr(t, "name", "") == "Shoot" for t in tags)
    except TypeError:
        return False


def costs_x(card):
    cost = getattr(card, "EnergyCost", None)
    if cost is None:
        return False
    return bool(getattr(cost, "CostsX", False))


def _method_source(card, name):
    key = (type(card), name)
    src = _SRC.get(key)
    if src is None:
        fn = getattr(type(card), name, None)
        try:
            src = inspect.getsource(fn) if fn is not None else ""
        except (OSError, TypeError):
            src = ""
        _SRC[key] = src
    return src


def immediate_aim(card):
    """打出后立刻获得的瞄准。回合开始才给瞄准的能力牌不算。"""
    if getattr(getattr(card, "Type", None), "name", "") == "Power":
        return 0.0
    aim = dvar(card, "AimPower")
    if aim <= 0:
        return 0.0
    src = _method_source(card, "OnPlay")
    if "AimPower" not in src:
        return 0.0
    return aim


def arrows_available(player):
    try:
        from ..rt.boot import game as G
        return int(G.ArrowCmd.GetAvailableArrowCount(player))
    except (TypeError, ValueError, AttributeError):
        return 1


def _energy(player):
    state = getattr(player, "PlayerCombatState", None)
    if state is None:
        return 0
    try:
        return int(state.Energy)
    except (TypeError, ValueError):
        return 0


def player_aim(player):
    creature = getattr(player, "Creature", None)
    powers = getattr(creature, "Powers", None)
    if powers is None:
        return 0.0
    total = 0.0
    try:
        items = list(powers)
    except TypeError:
        return 0.0
    for pw in items:
        entry = getattr(getattr(pw, "Id", None), "Entry", "")
        if entry == "AIM_POWER":
            try:
                total += float(pw.Amount)
            except (TypeError, ValueError):
                pass
    return total


def _max_slippery(cs):
    best = 0
    enemies = getattr(cs, "Enemies", None)
    if enemies is None:
        return 0
    try:
        items = list(enemies)
    except TypeError:
        return 0
    for enemy in items:
        if not getattr(enemy, "IsAlive", True):
            continue
        for pw in getattr(enemy, "Powers", ()):
            if getattr(getattr(pw, "Id", None), "Entry", "") == "SLIPPERY_POWER":
                try:
                    best = max(best, int(pw.Amount))
                except (TypeError, ValueError):
                    pass
    return best


def _shot_hits(card):
    return max(1.0, dvar(card, "HitCount"), dvar(card, "Repeat"))


def defer_aimed_shot(card, player, cs):
    """瞄准还在、滑溜没剥完时，手里有别的攻击就先别射。射一会把瞄准整层打掉，伤害仍是 1。"""
    if not is_shoot(card) or player_aim(player) <= 0:
        return False
    slip = _max_slippery(cs)
    if slip <= 0 or _shot_hits(card) > slip:
        return False
    state = getattr(player, "PlayerCombatState", None)
    hand = getattr(getattr(state, "Hand", None), "Cards", None)
    if hand is None:
        return False
    try:
        cards = list(hand)
    except TypeError:
        return False
    for other in cards:
        if other is card:
            continue
        if getattr(getattr(other, "Type", None), "name", "") == "Attack" and not is_shoot(other):
            return True
    return False


def reject_whiff(card, player):
    """没有空箭槽时射击牌打出去伤害是 0。"""
    return is_shoot(card) and arrows_available(player) <= 0


def prefer_aimed_shot(best, acts, player, cs):
    """有瞄准且滑溜已经剥开时，先打瞄准倍率更高的射击（沉重射击优于愚蠢射击）。"""
    if not best or best[0] != "play" or not is_shoot(best[1]):
        return None
    if player_aim(player) <= 0 or arrows_available(player) <= 0:
        return None
    if _max_slippery(cs) > 0:
        return None
    energy = _energy(player)
    chosen = None
    chosen_key = None
    for act in acts:
        if act[0] != "play" or not is_shoot(act[1]):
            continue
        if costs_x(act[1]) or card_cost(act[1]) > energy:
            continue
        mult = dvar(act[1], "AimMultiplier")
        if mult <= 0:
            mult = 1.0
        key = (mult, dvar(act[1], "Damage"))
        if chosen_key is None or key > chosen_key:
            chosen_key = key
            chosen = act
    if chosen is None or chosen[1] is best[1]:
        return None
    return chosen


def aim_before_shot(best, acts, player):
    """能量够先上瞄准再射击时，先打瞄准。格挡优先的决策不改。"""
    if not best or best[0] != "play" or not is_shoot(best[1]):
        return None
    if arrows_available(player) <= 0:
        return None
    energy = _energy(player)
    shot_cost = card_cost(best[1])
    chosen = None
    chosen_key = None
    for act in acts:
        if act[0] != "play":
            continue
        aim = immediate_aim(act[1])
        if aim <= 0:
            continue
        if costs_x(act[1]):
            # X 费会花光能量，这一回合就射不了还可能没格挡。
            continue
        cost = card_cost(act[1])
        if cost + shot_cost > energy:
            continue
        key = (aim, -cost)
        if chosen_key is None or key > chosen_key:
            chosen_key = key
            chosen = act
    return chosen
