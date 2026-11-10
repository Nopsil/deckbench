"""出牌 AI 接口与通用局面估值。

Agent 需要实现：
  play_turn(combat)                       打完自己的一个回合（反复调用 combat.play(i, target)）
  choose_cards(combat, purpose, options, n, ctx) -> list   卡牌效果里的选牌界面
     purpose: exhaust / discard / retrieve / discover / retain / pick_top
mod 可以在 hooks.py 里定义 state_value(combat) 给局面加分（例如给 Claude娘 的风控层数估值），
以及 card_worth(card) 给选牌界面用。
"""
from ..core import POWER_TYPES
from .. import explain

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


def _copy_note(chosen, rows):
    """被选中的那一步如果算过修正，把 note 带到说明日志的 chosen 上。"""
    for row in rows or []:
        if (row.get("id") == chosen.get("id") and row.get("hand") == chosen.get("hand")
                and row.get("target") == chosen.get("target") and row.get("note")):
            chosen["note"] = row["note"]
            return chosen
    return chosen


def _step(C, kind, ident, name, target, score, value=None, hand=None):
    step = {"kind": kind, "id": ident, "name": name, "score": score}
    if target is not None:
        try:
            step["target"] = f"{target.name}#{C.enemies.index(target)}"
        except ValueError:
            step["target"] = getattr(target, "name", None)
    if value is not None:
        step["value"] = value
    if hand is not None:
        step["hand"] = hand
    return step


def resources(C):
    """可在本回合继续使用的资源：可打出的手牌数、能量。"""
    P = C.player
    n = 0
    for c in P.hand:
        if not c.has_kw("unplayable") and c.printed_cost() is not None:
            n += 1
    return n, P.energy


def score_delta(C0, C1, paid, base_v=None, res0=None):
    """动作的得分：局面估值差 + 净资源收益（抽到的牌、回的能量）。花掉的能量不扣分，
    这样 AI 会把能量用完；排序时再按费用做轻微的效率修正。
    base_v / res0 是同一决策里已经算过的 evaluate(C0) 和 resources(C0)，数值与现算相同。"""
    v = evaluate(C1) - (evaluate(C0) if base_v is None else base_v)
    if res0 is None:
        n0, e0 = resources(C0)
    else:
        n0, e0 = res0
    n1, e1 = resources(C1)
    v += 1.5 * (n1 - n0 + 1) + 2.0 * (e1 - e0 + paid)
    return v


def as_bool(v, default=True):
    """构造参数里的开关。YAML 的 true/false、以及 ``false`` / ``0`` / ``off`` 这类字符串都认。"""
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(v)


# 高于「这一步就打赢」的 1e6：本回合能量够先格挡再攻击时，多段让路给格挡。
# 格挡打出之后这项变成 0，下一决策仍会收下能结束战斗的攻击。
THORNS_SEQUENCE = 2_000_000
# 非致命地打在已有格挡的身上时，压过「拆格挡」带来的那点估值，改去打还没格挡的。
ARMOUR_SEQUENCE = 250
# 总意图伤害还没被格挡盖住、手里又有格挡牌时，纯攻击让路。低于打赢一场的 1e6。
INCOMING_SEQUENCE = 500
UNKNOWN_DRAW_PER_HP = 0.25


def _effects(card):
    d = card.d
    return d.effects_up if card.upgraded else d.effects


def _literal_int(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def _max_int(v):
    """从表达式文本里取出现过的最大整数。不求值、不抽随机数。"""
    if not isinstance(v, str):
        return None
    best = None
    cur = ""
    for ch in v:
        if ch.isdigit():
            cur += ch
        elif cur:
            best = max(best or 0, int(cur))
            cur = ""
    if cur:
        best = max(best or 0, int(cur))
    return best


def _number(card, v, default=None):
    """公开数值：字面量、卡牌 vars 里的名字，否则表达式里的最大整数。不求值。"""
    n = _literal_int(v)
    if n is not None:
        return n
    if isinstance(v, str):
        key = v.strip()
        if key in card.vars:
            n = _literal_int(card.vars[key])
            if n is not None:
                return n
        n = _max_int(v)
        if n is not None:
            return n
    return default


def _attack_hits(card):
    """打在同一个目标上的攻击段数。没有攻击伤害就是 0。不打出牌、不抽随机数。"""
    hits = _hit_sum(card, _effects(card))
    if hits and card.d.hits_hint and hits < 2:
        hits = 2
    return hits


def _hit_sum(card, effects):
    hits = 0
    for eff in effects or []:
        op = eff.get("op")
        if op == "damage" and eff.get("kind", "attack") not in ("hp_loss", "power"):
            h = _number(card, eff.get("hits", 1), default=1) or 1
            hits += max(1, h)
        elif op == "repeat":
            n = _number(card, eff.get("n", 1), default=1) or 1
            hits += max(1, n) * _hit_sum(card, eff.get("do"))
        elif op in ("foreach", "if"):
            for key in ("do", "then", "else"):
                hits += _hit_sum(card, eff.get(key))
    return hits


def _spreads(card):
    if card.d.target in ("all", "random"):
        return True

    def walk(effects):
        for eff in effects or []:
            op = eff.get("op")
            if op == "damage" and eff.get("target") in ("all", "random"):
                return True
            if op == "foreach":
                return True
            if op in ("repeat", "if"):
                for key in ("do", "then", "else"):
                    if walk(eff.get(key)):
                        return True
        return False

    return walk(_effects(card))


def _block_total(card):
    total = 0
    for eff in _effects(card) or []:
        if eff.get("op") != "block":
            continue
        n = _number(card, eff.get("amount", 0))
        if n:
            total += n
    return total


def _hand_block(C, skip_uid):
    """手里另一张打得出的格挡牌：(格挡点数, 费用)。只看印上去的费用和 vars，不发 modify_cost。"""
    best_amt, best_cost = 0, None
    for c in C.player.hand:
        if skip_uid is not None and c.uid == skip_uid:
            continue
        if getattr(c.d, "cost_x", False):
            continue
        amt = _block_total(c)
        if amt <= 0:
            continue
        cost = c.printed_cost()
        if cost is None or cost > C.player.energy:
            continue
        if best_cost is None or amt > best_amt:
            best_amt, best_cost = amt, cost
    return best_amt, best_cost


def _faces_thorns(C, card, target):
    alive = C.alive_enemies()
    if not alive:
        return False
    if _spreads(card):
        return any(e.amt("THORNS") > 0 for e in alive)
    return target is not None and getattr(target, "alive", False) and target.amt("THORNS") > 0


def _was_hit(e0, e1):
    if e1 is None:
        return False
    if not e1.alive:
        return True
    if e1.hp < e0.hp or e1.block < e0.block:
        return True
    sk0 = e0.powers.get("SKITTISH")
    sk1 = e1.powers.get("SKITTISH")
    return bool(sk0 and not sk0.data.get("used") and sk1 and sk1.data.get("used"))


def _attacking_enemies(C):
    n = 0
    for e in C.alive_enemies():
        mv = getattr(e, "intent", None)
        if mv is not None and getattr(mv, "damage", 0) and not e.data.get("stunned"):
            n += 1
    return n


def mechanic_adjust(C, sim, card, target, paid=0):
    """荆棘、受击加格挡、多敌人总伤害的出牌修正。

    只读这一步已经打出来的模拟结果和公开信息（段数、vars、牌堆张数）。
    不抽随机数，也不看牌堆里具体是哪张牌。返回 (要从分数里减去的值, 说明)。
    说明写进 ``--explain`` 候选的 ``note``：``thorns:N``、``armour``、``incoming:总伤害>格挡``。
    """
    if card is None or sim is None:
        return 0.0, ""
    hits = _attack_hits(card)
    if hits <= 0 and card.type != "攻击":
        return 0.0, ""
    notes = []
    pen = 0.0
    block_amt, block_cost = _hand_block(C, card.uid)

    if hits >= 2 and _faces_thorns(C, card, target):
        hp_loss = max(0, C.player.hp - sim.player.hp)
        blocked = max(0, C.player.block - sim.player.block)
        taken = hp_loss + blocked
        can_both = block_amt > 0 and block_cost is not None and C.player.energy >= paid + block_cost
        lethal = hp_loss >= C.player.hp > 0
        if taken > 0 and block_amt > 0 and hp_loss > 0 and (can_both or lethal):
            pen += THORNS_SEQUENCE + taken
            notes.append(f"thorns:{int(taken)}")

    if hits > 0 or card.type == "攻击":
        armoured = False
        for e0, e1 in zip(C.enemies, sim.enemies):
            if not e0.alive or e0.block <= 0 or not _was_hit(e0, e1):
                continue
            if not e1.alive:
                continue
            if any(o.alive and o is not e0 and o.block <= 0 for o in C.enemies):
                pen += ARMOUR_SEQUENCE + e0.block
                armoured = True
        if armoured:
            notes.append("armour")

    if (hits > 0 or card.type == "攻击") and sim.result != "win" and sim.player.block <= C.player.block:
        inc0 = C.incoming_damage()
        inc1 = sim.incoming_damage()
        short = inc1 - sim.player.block
        if inc1 >= inc0 and short > 0 and inc0 > C.player.block and block_amt > 0:
            unseen = len(C.player.draw_pile) + len(C.player.discard)
            n_atk = _attacking_enemies(C)
            extra = short * (UNKNOWN_DRAW_PER_HP if unseen else 0.0)
            if n_atk >= 2:
                extra += short * 0.15 * (n_atk - 1)
            pen += INCOMING_SEQUENCE + extra
            bit = f"incoming:{int(inc0)}>{int(C.player.block)}"
            if n_atk >= 2:
                bit += f"x{n_atk}"
            if unseen:
                bit += "+unknown"
            notes.append(bit)
    return pen, ";".join(notes)


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
            log = explain.enabled()
            scored = [] if log else None
            floor = best_s
            base_v = evaluate(C)
            res0 = resources(C)
            for j, pid in enumerate(C.player.potions):
                d = POTION_DEFS.get(pid)
                if d is None:
                    continue
                tgts = C.alive_enemies() if d.target == "enemy" else [None]
                for t in tgts:
                    sim = C.clone()
                    ti = None if t is None else C.enemies.index(t)
                    sim.use_potion(j, None if ti is None else sim.enemies[ti])
                    sc = score_delta(C, sim, 0, base_v=base_v, res0=res0) - 1.5
                    if log:
                        scored.append(_step(C, "potion", pid, getattr(d, "name", pid), t, sc))
                    if sc > best_s:
                        best, best_s = (j, t), sc
            if log and scored:
                chosen = None
                if best is not None:
                    j, t = best
                    pid = C.player.potions[j]
                    d = POTION_DEFS.get(pid)
                    chosen = _step(C, "potion", pid, getattr(d, "name", pid) if d else pid, t, best_s)
                explain.publish(explain.from_steps(scored, chosen, turn=C.turn, threshold=floor))
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
