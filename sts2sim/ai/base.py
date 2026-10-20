"""出牌 AI 接口与通用局面估值。

Agent 需要实现：
  play_turn(combat)                       打完自己的一个回合（反复调用 combat.play(i, target)）
  choose_cards(combat, purpose, options, n, ctx) -> list   卡牌效果里的选牌界面
     purpose: exhaust / discard / retrieve / discover / retain / pick_top
mod 可以在 hooks.py 里定义 state_value(combat) 给局面加分（例如给 Claude娘 的风控层数估值），
以及 card_worth(card) 给选牌界面用。
"""
from ..core import POWER_TYPES

RARITY_WORTH = {"基础": 1.0, "普通": 2.0, "罕见": 3.0, "稀有": 4.0, "状态": -10.0, "诅咒": -10.0}


def card_worth(C, card):
    for m in C.mod.hook_modules:
        f = getattr(m, "card_worth", None)
        if f is not None:
            v = f(C, card)
            if v is not None:
                return v
    w = card.d.ai.get("worth")
    if w is not None:
        return w
    if card.has_kw("unplayable"):
        return -10.0
    return RARITY_WORTH.get(card.d.rarity, 2.0) + (0.5 if card.upgraded else 0)


def power_value(C, p, on_player):
    v = C.mod.ai_values.get(p.id)
    if v is None:
        v = getattr(p, "ai_value", 0.0) or 0.0
    return v


ENEMY_BUFF_VALUE = {"SLIPPERY": 4.0, "PLATING": 1.0, "ARTIFACT": 2.0, "THORNS": 1.0, "INTANGIBLE": 8.0, "RITUAL": 3.0,
                    "HARD_TO_KILL": 0.0, "CURL_UP": 0.5, "VIGOR": 1.0}


def resources(C):
    """可在本回合继续使用的资源：可打出的手牌数、能量。"""
    P = C.player
    n = 0
    for c in P.hand:
        if not c.has_kw("unplayable") and c.printed_cost() is not None:
            n += 1
    return n, P.energy


def score_delta(C0, C1, paid):
    """动作的得分：局面估值差 + 净资源收益（抽到的牌、回的能量）。花掉的能量不扣分，
    这样 AI 会把能量用完；排序时再按费用做轻微的效率修正。"""
    v = evaluate(C1) - evaluate(C0)
    n0, e0 = resources(C0)
    n1, e1 = resources(C1)
    v += 1.5 * (n1 - n0 + 1) + 2.0 * (e1 - e0 + paid)
    return v


def evaluate(C):
    """局面估值（越大越好）。只用公开信息：敌人血量/格挡/意图/能力、自己血量/格挡/能力。
    手牌与能量不在这里估值（见 score_delta）。"""
    if C.result == "win":
        return 1e6 + C.player.hp * 10
    if C.result == "loss" or not C.player.alive:
        return -1e6
    P = C.player
    v = 0.0
    alive = C.alive_enemies()
    total_hp = 0
    for e in C.enemies:
        if not e.alive:
            v += 25.0
            continue
        total_hp += e.hp
        v -= e.hp + 0.5 * e.block
        for p in e.powers.values():
            if p.kind == "debuff" and p.id != "POISON":
                pv = power_value(C, p, False)
                if pv:
                    v += pv * min(p.amount, 3)
            elif p.id == "POISON":
                v += min(e.hp, p.amount * (p.amount + 1) / 2) * 0.7
            elif p.id == "STRENGTH":
                v -= 2.0 * p.amount
            else:
                bv = ENEMY_BUFF_VALUE.get(p.id)
                if bv:
                    v -= bv * min(p.amount, 5)
    inc = C.incoming_damage()
    unblocked = max(0, inc - P.block)
    osty = C.data.get("osty_hp", 0)
    unblocked = max(0, unblocked - osty)
    hp_after = P.hp - unblocked
    if hp_after <= 0:
        v -= 500
    w_hp = 1.2 + 0.8 * (1 - P.hp / max(1, P.max_hp))
    v += (P.hp - unblocked) * w_hp
    v += 0.05 * max(0, P.block - inc)
    v += 0.6 * osty
    late = 1.0 if total_hp > 25 else 0.25
    for p in P.powers.values():
        pv = power_value(C, p, True)
        if pv:
            v += pv * p.amount * (late if p.kind == "buff" else 1.0) * (1 if p.kind == "buff" else -1)
    for m in C.mod.hook_modules:
        f = getattr(m, "state_value", None)
        if f is not None:
            v += f(C)
    return v


POTION_THRESHOLD = 12.0    # 药水是一次性资源：估值收益要超过这个值才喝（或者不喝就会死）


class Agent:
    name = "base"

    def use_potions(self, C):
        """回合开始时逐瓶评估：复制战斗喝一次，收益 ≥ 阈值、或本回合将被打死时喝。"""
        from ..potions import POTION_DEFS
        changed = True
        while changed and C.player.potions and C.result is None:
            changed = False
            danger = C.incoming_damage() - C.player.block >= C.player.hp
            room_bonus = 0.0 if C.data.get("_room") in ("精英", "首领") else 6.0
            best, best_s = None, POTION_THRESHOLD + room_bonus
            if danger:
                best_s = 0.5
            for j, pid in enumerate(C.player.potions):
                d = POTION_DEFS.get(pid)
                if d is None:
                    continue
                tgts = C.alive_enemies() if d.target == "enemy" else [None]
                for t in tgts:
                    sim = C.clone()
                    ti = None if t is None else C.enemies.index(t)
                    sim.use_potion(j, None if ti is None else sim.enemies[ti])
                    sc = score_delta(C, sim, 0) - 1.5
                    if sc > best_s:
                        best, best_s = (j, t), sc
            if best is not None:
                C.use_potion(*best)
                changed = True

    def play_turn(self, C):
        raise NotImplementedError

    def choose_cards(self, C, purpose, options, n, ctx=None):
        opts = list(options)
        if purpose in ("exhaust", "discard"):
            opts.sort(key=lambda c: card_worth(C, c))
        else:
            opts.sort(key=lambda c: -card_worth(C, c))
        return opts[:n]
