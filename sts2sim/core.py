"""战斗核心：生物、能力、卡牌实例、牌堆、事件总线、伤害/格挡/能力结算、回合流程。

事件总线：combat.emit(name, **payload) 会依次调用
  玩家遗物 → 玩家能力 → 各敌人能力 → mod 全局监听（hooks.py 里的 on_<事件名> 函数）
上名为 on_<事件名>(combat, ev) 的方法。ev 是一个 SimpleNamespace，可以读写字段
（例如 modify_apply 事件里改 ev.amount 就能修改本次施加的层数）。

常用事件（payload 字段）：
  battle_start()                       战斗开始（第一回合抽牌前）
  turn_start(side, creature)           side='player'：玩家回合开始、抽牌前；side='enemy'：每个敌人行动前
  after_draw_turn()                    玩家回合开始抽完牌后
  turn_end(side, creature)             玩家回合结束（弃牌前）/敌人回合结束
  card_drawn(card)
  before_play(card, ctx) / after_play(card, ctx)
  modify_play_count(card, ctx, count)  可改 ev.count 实现重放
  damage_add(src, target, amount, kind, card) / damage_mul(...)   可改 ev.amount
  attacked(attacker, target, damage, unblocked, card)             攻击命中后（每段）
  damage_taken(target, amount, src, kind)                         实际失去生命后
  modify_apply(target, pid, amount, source, active, secondary, multi)  施加前修正层数
  power_applied(target, pid, delta, source, active, secondary, multi)  实际增加正层数后
  power_blocked(target, pid, source)                               被人工制品抵消
  power_removed(target, pid, removed, source, active)              实际移除正层数后
  stacks_changed(target, pid, delta, op)                           层数操作（转移/复制/翻倍/设值）
  block_gained(creature, amount)
  card_exhausted(card) / shuffle() / enemy_died(enemy)
  modify_cost(card, cost)              可改 ev.cost
  before_block_clear(creature, keep)   玩家回合开始清空格挡前，可改 ev.keep
"""
import copy
import random
from types import SimpleNamespace

ACTION_CAP_DEFAULT = 200


class LoopAlarm(Exception):
    pass


# ---------------------------------------------------------------- 能力
POWER_TYPES = {}


def register_power(cls):
    POWER_TYPES[cls.id] = cls
    return cls


class Power:
    id = "POWER"
    name = "能力"
    kind = "buff"          # buff / debuff
    ai_value = 0.0         # 启发式 AI 估值：每层价值（玩家身上为正收益，敌人身上的负面效果为玩家收益）
    decays = False         # 回合结束时 -1（易伤、虚弱、脆弱）
    can_go_negative = False

    def __init__(self, owner, amount=0, src=None, **params):
        self.owner = owner
        self.amount = amount
        self.src = src            # 归因名（通常是来源卡名）
        self.data = dict(params)

    def clone(self, owner):
        p = copy.copy(self)
        p.owner = owner
        p.data = dict(self.data)
        return p

    def __repr__(self):
        return f"{self.id}({self.amount})"


class GenericPower(Power):
    """数据里出现、但没有实现效果的能力：只记录层数（列入近似清单）。"""
    def __init__(self, owner, amount=0, src=None, pid="UNKNOWN", **params):
        super().__init__(owner, amount, src, **params)
        self.id = pid
        self.name = pid


# ---------------------------------------------------------------- 生物
class Creature:
    is_player = False

    def __init__(self, name, hp, max_hp=None):
        self.name = name
        self.hp = hp
        self.max_hp = max_hp or hp
        self.block = 0
        self.powers = {}
        self.alive = True
        self.slot = 0

    def amt(self, pid):
        p = self.powers.get(pid)
        return p.amount if p else 0

    def has(self, pid):
        p = self.powers.get(pid)
        return bool(p and p.amount != 0)

    def _clone_base(self, new):
        new.powers = {k: p.clone(new) for k, p in self.powers.items()}
        return new


class Player(Creature):
    is_player = True

    def __init__(self, name, hp, energy_per_turn=3, hand_size=5, orb_slots=0):
        super().__init__(name, hp)
        self.energy = 0
        self.energy_per_turn = energy_per_turn
        self.draw_per_turn = hand_size
        self.hand, self.draw_pile, self.discard, self.exhaust_pile = [], [], [], []
        self.orb_slots = orb_slots
        self.potions = []        # 药水 ID 列表（见 potions.py）

    def clone(self):
        new = copy.copy(self)
        self._clone_base(new)
        new.potions = list(self.potions)
        new.hand = [copy.copy(c) for c in self.hand]
        new.draw_pile = [copy.copy(c) for c in self.draw_pile]
        new.discard = [copy.copy(c) for c in self.discard]
        new.exhaust_pile = [copy.copy(c) for c in self.exhaust_pile]
        return new

    def intent_is_attack(self):
        return False


# ---------------------------------------------------------------- 卡牌实例
class Card:
    __slots__ = ("d", "upgraded", "uid", "cost_turn", "cost_delta", "cost_set", "free_turn", "played_turn", "tmp")
    _uid = [0]

    def __init__(self, d, upgraded=False):
        self.d = d
        self.upgraded = upgraded
        Card._uid[0] += 1
        self.uid = Card._uid[0]
        self.cost_turn = None   # 本回合费用覆盖
        self.cost_delta = 0     # 永久费用修正
        self.cost_set = None    # 永久设定费用
        self.free_turn = False
        self.played_turn = -1   # 本实例最近一次被打出的回合（「本回合第一次打出」判定）
        self.tmp = None

    @property
    def id(self):
        return self.d.id

    @property
    def name(self):
        return self.d.name + ("+" if self.upgraded else "")

    @property
    def base_name(self):
        return self.d.name

    @property
    def type(self):
        return self.d.type

    @property
    def vars(self):
        return self.d.vars_up if self.upgraded else self.d.vars

    @property
    def keywords(self):
        return self.d.kw_up if self.upgraded else self.d.kw

    def has_kw(self, k):
        return k in self.keywords

    def printed_cost(self):
        return self.d.cost_up if self.upgraded else self.d.cost

    def __repr__(self):
        return self.name


# ---------------------------------------------------------------- 战斗统计
class Stats:
    def __init__(self):
        self.card = {}   # name -> [plays, damage, block, energy_paid]
        self.alarms = []

    def rec(self, name, plays=0, dmg=0, blk=0, energy=0):
        r = self.card.get(name)
        if r is None:
            r = self.card[name] = [0, 0, 0, 0]
        r[0] += plays
        r[1] += dmg
        r[2] += blk
        r[3] += energy


# ---------------------------------------------------------------- 战斗
class Combat:
    def __init__(self, player, enemies, mod, rng=None, agent=None, max_turns=30, action_cap=ACTION_CAP_DEFAULT):
        self.player = player
        self.enemies = enemies
        for i, e in enumerate(enemies):
            e.slot = i
        self.mod = mod                    # ModSet（卡表、钩子）
        self.rng = rng or random.Random(0)
        self.agent = agent
        self.max_turns = max_turns
        self.action_cap = action_cap
        self.relics = []
        self.turn = 0
        self.phase = "setup"              # setup / player / enemy
        self.data = {}                    # mod 自由使用的战斗级状态（需可浅拷贝的简单值或容器）
        self.stats = Stats()
        self.is_sim = False
        self.actions_this_turn = 0
        self.cards_played_turn = []       # 本回合打出的卡（实例）
        self.play_stack = []              # 正在结算的 PlayCtx
        self.attr = []                    # 归因栈
        self.result = None
        self._clone_n = 0
        self.log = None                   # list 时记录文字日志
        self.loop_alarm = None

    # ---------- 复制（AI 前瞻用）
    def clone(self):
        new = copy.copy(self)
        new.player = self.player.clone()
        emap = {}
        new.enemies = []
        for e in self.enemies:
            ne = e.clone()
            emap[id(e)] = ne
            new.enemies.append(ne)
        new.relics = [r.clone() for r in self.relics]
        new.data = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in self.data.items()}
        self._clone_n += 1
        new.rng = random.Random(self._clone_n * 7919 + self.turn)
        new.stats = None
        new.is_sim = True
        new.log = None
        new.cards_played_turn = list(self.cards_played_turn)
        new.play_stack = []
        new.attr = []
        return new

    def say(self, msg):
        if self.log is not None:
            self.log.append(f"[T{self.turn}{'P' if self.phase=='player' else 'E'}] {msg}")

    # ---------- 查询
    def alive_enemies(self):
        return [e for e in self.enemies if e.alive]

    def enemy_index(self, e):
        return self.enemies.index(e)

    def other_enemies(self, e):
        return [x for x in self.enemies if x.alive and x is not e]

    def random_enemy(self, exclude=None):
        L = [e for e in self.enemies if e.alive and e is not exclude]
        return self.rng.choice(L) if L else None

    # ---------- 事件
    def listeners(self):
        for r in self.relics:
            yield r
        for p in list(self.player.powers.values()):
            yield p
        for e in self.enemies:
            if e.alive:
                for p in list(e.powers.values()):
                    yield p
        for m in self.mod.listeners:
            yield m

    def emit(self, name, **kw):
        ev = SimpleNamespace(**kw)
        meth = "on_" + name
        for obj in self.listeners():
            f = getattr(obj, meth, None)
            if f is not None:
                if obj.__class__.__name__ == "module":
                    f(self, ev)
                else:
                    f(self, ev)
        return ev

    # ---------- 归因
    def cur_attr(self):
        return self.attr[-1] if self.attr else "其他"

    def push_attr(self, name):
        self.attr.append(name)

    def pop_attr(self):
        self.attr.pop()

    # ---------- 伤害
    def calc_damage(self, src, target, base, kind="attack", card=None, ctx=None):
        amount = base
        if kind == "attack" and src is not None:
            amount += src.amt("STRENGTH")
            if src.is_player and card is not None:
                amount += src.amt("VIGOR")
            ev = self.emit("damage_add", src=src, target=target, amount=amount, kind=kind, card=card, ctx=ctx)
            amount = ev.amount
            amount = float(amount)
            if src.has("WEAK"):
                amount *= 0.75
            if target.has("VULNERABLE"):
                amount *= 1.5
            ev = self.emit("damage_mul", src=src, target=target, amount=amount, kind=kind, card=card, ctx=ctx)
            amount = ev.amount
        amount = int(amount)
        if target.has("INTANGIBLE"):
            amount = min(amount, 1)
        return max(0, amount)

    def predict_intent_damage(self, enemy):
        mv = enemy.intent
        if not enemy.alive or mv is None or not mv.damage or enemy.data.get("stunned") \
                or (not getattr(enemy.m, "ai", None) and (enemy.has("ASLEEP") or enemy.has("SLUMBER"))):
            return 0
        per = self.calc_damage(enemy, self.player, mv.damage + enemy.intent_bonus(), "attack")
        return per * mv.hits

    def incoming_damage(self):
        return sum(self.predict_intent_damage(e) for e in self.alive_enemies())

    def deal_damage(self, src, target, base, kind="attack", card=None, ctx=None, precalc=False):
        """kind: attack（攻击伤害，吃力量/虚弱/易伤）、power（能力/遗物造成的伤害）、hp_loss（失去生命，无视格挡）。"""
        if not target.alive:
            return 0
        dmg = base if precalc else self.calc_damage(src, target, base, kind, card, ctx)
        blocked = 0
        if kind != "hp_loss":
            blocked = min(target.block, dmg)
            target.block -= blocked
        unblocked = dmg - blocked
        if target.is_player and unblocked > 0 and kind != "hp_loss":
            osty = self.data.get("osty_hp", 0)
            if osty > 0 and kind == "attack":
                a = min(osty, unblocked)
                self.data["osty_hp"] = osty - a
                unblocked -= a
        lost = self.lose_hp(target, unblocked, src, kind)
        if kind == "attack" and src is not None:
            self.emit("attacked", attacker=src, target=target, damage=dmg, unblocked=unblocked, card=card)
        if src is not None and src.is_player and not target.is_player and self.stats is not None:
            self.stats.rec(self.cur_attr(), dmg=lost)
        if self.log is not None and lost + blocked > 0:
            self.say(f"{src.name if src else '?'} → {target.name} {dmg}（格挡{blocked}，失去{lost}）")
        return lost

    def lose_hp(self, target, amount, src=None, kind="attack"):
        if amount <= 0 or not target.alive:
            return 0
        if target.has("SLIPPERY"):
            amount = 1
            target.powers["SLIPPERY"].amount -= 1
            if target.powers["SLIPPERY"].amount <= 0:
                del target.powers["SLIPPERY"]
        if target.has("HARD_TO_KILL"):
            amount = min(amount, target.amt("HARD_TO_KILL"))
        if target.has("HARDENED_SHELL"):
            p = target.powers["HARDENED_SHELL"]
            left = max(0, p.amount - p.data.get("lost", 0))
            amount = min(amount, left)
            p.data["lost"] = p.data.get("lost", 0) + amount
        lost = min(amount, target.hp)
        target.hp -= amount
        if lost > 0:
            self.emit("damage_taken", target=target, amount=lost, src=src, kind=kind)
        if target.hp <= 0 and target.alive:
            self.kill(target)
        return lost

    def kill(self, c):
        if c.is_player:
            ev = self.emit("player_would_die")
            if c.hp > 0:
                return
            c.alive = False
            self.result = "loss"
            return
        if c.has("ILLUSION") or c.has("REATTACH"):
            # 近似：幻象/接续——若还有其他同伴存活，按数据复活；否则正常死亡
            others = [e for e in self.alive_enemies() if e is not c and not e.has("MINION")]
            if others and not c.data.get("revived"):
                c.data["revived"] = True
                c.hp = c.max_hp if c.has("ILLUSION") else 25
                return
        c.alive = False
        c.block = 0
        self.emit("enemy_died", enemy=c)
        # 爪牙：领导者全部死亡后离场
        leaders = [e for e in self.enemies if e.alive and not e.has("MINION")]
        if not leaders:
            for e in self.enemies:
                if e.alive:
                    e.alive = False
        if not self.alive_enemies():
            self.result = "win"

    # ---------- 格挡
    def gain_block(self, c, amount, from_card=True):
        amount = int(amount)
        if from_card and c.is_player:
            amount += c.amt("DEXTERITY")
            if c.has("FRAIL"):
                amount = int(amount * 0.75)
            ev = self.emit("block_mod", creature=c, amount=amount)
            amount = ev.amount
        amount = max(0, int(amount))
        if amount <= 0:
            return 0
        c.block += amount
        if c.is_player and self.stats is not None:
            self.stats.rec(self.cur_attr(), blk=amount)
        self.emit("block_gained", creature=c, amount=amount)
        return amount

    # ---------- 能力
    def make_power(self, target, pid, amount, src=None, **params):
        cls = POWER_TYPES.get(pid)
        if cls is None:
            return GenericPower(target, amount, src, pid=pid, **params)
        return cls(target, amount, src, **params)

    def source_active(self, source):
        return self.phase == "player" and source is not None and source[0] in ("card", "power")

    def apply_power(self, target, pid, amount, source=None, secondary=False, multi=False, src_name=None, **params):
        """施加能力。source=(类别, 对象)，类别：card / power / relic / enemy / op。
        负面效果会被人工制品抵消。返回实际增加的层数。"""
        if not target.alive or amount == 0:
            return 0
        cls = POWER_TYPES.get(pid)
        kind = cls.kind if cls else ("debuff" if pid in ("WEAK", "VULNERABLE", "FRAIL", "POISON") else "buff")
        active = self.source_active(source)
        if kind == "debuff" and amount > 0 and target.has("ARTIFACT"):
            target.powers["ARTIFACT"].amount -= 1
            if target.powers["ARTIFACT"].amount <= 0:
                del target.powers["ARTIFACT"]
            self.emit("power_blocked", target=target, pid=pid, source=source)
            self.say(f"人工制品抵消了 {target.name} 的 {pid}")
            return 0
        if not secondary:
            ev = self.emit("modify_apply", target=target, pid=pid, amount=amount, source=source,
                           active=active, secondary=secondary, multi=multi)
            amount = ev.amount
        if amount == 0:
            return 0
        p = target.powers.get(pid)
        if p is None:
            p = self.make_power(target, pid, 0, src_name or self.cur_attr(), **params)
            target.powers[pid] = p
        elif params:
            p.data.update(params)
        before = p.amount
        p.amount += amount
        if not p.can_go_negative and p.amount < 0:
            p.amount = 0
        delta = p.amount - before
        if p.amount == 0 and pid not in ("STRENGTH", "DEXTERITY"):
            del target.powers[pid]
        if delta > 0:
            self.say(f"{target.name} +{delta} {pid}（共{p.amount}）")
            self.emit("power_applied", target=target, pid=pid, delta=delta, source=source,
                      active=active, secondary=secondary, multi=multi)
        return delta

    def remove_power(self, target, pid, n=None, source=None):
        """移除 n 层（None=全部）。返回实际移除的正层数，>0 时触发 power_removed。"""
        p = target.powers.get(pid)
        if p is None or p.amount <= 0:
            return 0
        removed = p.amount if n is None else min(n, p.amount)
        p.amount -= removed
        if p.amount <= 0:
            del target.powers[pid]
        if removed > 0:
            self.say(f"{target.name} 清除 {removed} {pid}")
            self.emit("power_removed", target=target, pid=pid, removed=removed, source=source,
                      active=self.source_active(source))
        return removed

    def set_stacks(self, target, pid, value, op="set", artifact_blocks=False):
        """层数操作：直接改层数，不算施加/清除。artifact_blocks=True 时，若会增加层数且目标有人工制品，
        消耗 1 层人工制品、本次操作无效。返回层数变化。"""
        if not target.alive:
            return 0
        before = target.amt(pid)
        value = max(0, int(value))
        if value > before and artifact_blocks and target.has("ARTIFACT"):
            target.powers["ARTIFACT"].amount -= 1
            if target.powers["ARTIFACT"].amount <= 0:
                del target.powers["ARTIFACT"]
            self.emit("power_blocked", target=target, pid=pid, source=("op", op))
            return 0
        if value == before:
            return 0
        if value == 0:
            target.powers.pop(pid, None)
        else:
            p = target.powers.get(pid)
            if p is None:
                p = self.make_power(target, pid, 0, self.cur_attr())
                target.powers[pid] = p
            p.amount = value
        self.emit("stacks_changed", target=target, pid=pid, delta=value - before, op=op)
        return value - before

    # ---------- 牌堆
    def shuffle_discard(self):
        P = self.player
        self.rng.shuffle(P.discard)
        P.draw_pile = P.discard + P.draw_pile  # 牌堆顶 = 列表末尾
        P.discard = []
        self.emit("shuffle")

    def draw(self, n):
        P = self.player
        got = []
        if P.has("NO_DRAW") and self.phase == "player" and self.data.get("_drawing_turn") is not True:
            return got
        for _ in range(int(n)):
            if len(P.hand) >= 10:
                break
            if not P.draw_pile:
                if not P.discard:
                    break
                self.shuffle_discard()
            c = P.draw_pile.pop()
            P.hand.append(c)
            got.append(c)
            self.emit("card_drawn", card=c)
        return got

    def make_card(self, cid, upgraded=False):
        return Card(self.mod.cards[cid], upgraded)

    def add_card(self, cid, to="hand", upgraded=False, n=1, free_turn=False):
        P = self.player
        out = []
        for _ in range(int(n)):
            c = self.make_card(cid, upgraded)
            if free_turn:
                c.cost_turn = 0
            if to == "hand":
                if len(P.hand) >= 10:
                    P.discard.append(c)
                else:
                    P.hand.append(c)
            elif to == "draw":
                P.draw_pile.insert(self.rng.randint(0, len(P.draw_pile)), c)
            elif to == "draw_top":
                P.draw_pile.append(c)
            elif to == "discard":
                P.discard.append(c)
            out.append(c)
        return out

    def exhaust(self, card, from_list=None):
        if from_list is not None and card in from_list:
            from_list.remove(card)
        self.player.exhaust_pile.append(card)
        self.emit("card_exhausted", card=card)

    def discard_from_hand(self, card):
        self.player.hand.remove(card)
        self.player.discard.append(card)
        self.emit("card_discarded", card=card)

    # ---------- 费用 / 可打出
    def card_cost(self, card):
        d = card.d
        if card.cost_turn is not None:
            cost = card.cost_turn
        elif card.cost_set is not None:
            cost = card.cost_set
        else:
            cost = card.printed_cost()
            if cost is None:
                return None
            if d.cost_expr:
                from . import expr
                ctx = SimpleNamespace(vars=card.vars, locals={}, target=None, combat=self, card=card)
                cost = expr.ev(d.cost_expr, ctx)
            cost += card.cost_delta
        ev = self.emit("modify_cost", card=card, cost=cost)
        return max(0, ev.cost)

    def can_play(self, card):
        if card.has_kw("unplayable") or card.printed_cost() is None:
            return False
        cost = self.card_cost(card)
        if cost is None:
            return False
        if card.d.cost_x:
            cost = 0
        if cost > self.player.energy:
            return False
        if card.d.can_play is not None:
            if not self.mod.call(card.d.can_play, self, card):
                return False
        ev = self.emit("can_play", card=card, ok=True)
        return ev.ok

    def needs_target(self, card):
        return card.d.target in ("enemy",)

    def legal_actions(self):
        acts = []
        for i, c in enumerate(self.player.hand):
            if not self.can_play(c):
                continue
            if self.needs_target(c):
                for e in self.alive_enemies():
                    acts.append((i, e))
            else:
                acts.append((i, None))
        return acts

    def use_potion(self, idx, target=None):
        from .potions import use_potion
        return use_potion(self, idx, target)

    # ---------- 打出
    def play(self, hand_index, target=None, free=False):
        from .cards import play_card
        card = self.player.hand[hand_index]
        self.actions_this_turn += 1
        if self.actions_this_turn > self.data.get("_max_actions", 0):
            self.data["_max_actions"] = self.actions_this_turn
        if self.actions_this_turn > self.action_cap:
            raise LoopAlarm()
        return play_card(self, card, target, free=free)

    # ---------- 回合
    def start_battle(self):
        self.phase = "setup"
        P = self.player
        # 固有牌放到牌堆顶
        innate = [c for c in P.draw_pile if c.has_kw("innate")]
        rest = [c for c in P.draw_pile if not c.has_kw("innate")]
        self.rng.shuffle(rest)
        P.draw_pile = rest + innate
        for e in self.enemies:
            e.setup(self)
        self.emit("battle_start")

    def start_player_turn(self):
        P = self.player
        self.turn += 1
        self.phase = "player"
        self.actions_this_turn = 0
        self.cards_played_turn = []
        for e in self.alive_enemies():
            if e.intent is None:
                e.choose_intent(self)
        keep = 0
        if P.has("BARRICADE"):
            keep = P.block
        ev = self.emit("before_block_clear", creature=P, keep=keep)
        P.block = min(P.block, max(0, ev.keep))
        P.energy = P.energy_per_turn
        self.emit("turn_start", side="player", creature=P)
        n = P.draw_per_turn + self.data.pop("_extra_draw_next", 0)
        ev = self.emit("modify_turn_draw", n=n)
        self.data["_drawing_turn"] = True
        self.draw(ev.n)
        self.data["_drawing_turn"] = False
        self.emit("after_draw_turn")

    def end_player_turn(self):
        P = self.player
        self.emit("turn_end", side="player", creature=P)
        # 灼伤/感染/毒素：回合结束时在手牌中则受到伤害
        for c in list(P.hand):
            n = c.d.raw.get("end_turn_in_hand_damage")
            if n and P.alive:
                self.push_attr(c.base_name)
                self.deal_damage(None, P, n, "power")
                self.pop_attr()
        if self.result:
            return
        # 回合结束弃牌
        keep_all = self.data.get("_keep_hand", False)
        retained = []
        for c in list(P.hand):
            if c.has_kw("ethereal"):
                P.hand.remove(c)
                self.exhaust(c)
                continue
            if c.has_kw("retain") or c.tmp == "retain":
                c.tmp = None
                retained.append(c)
                continue
            if keep_all and c.type not in ("状态", "诅咒"):
                retained.append(c)
                continue
            P.hand.remove(c)
            P.discard.append(c)
        P.hand = retained
        for c in P.hand + P.discard + P.draw_pile + P.exhaust_pile:
            c.cost_turn = None
        for pid in ("VULNERABLE", "WEAK", "FRAIL"):
            p = P.powers.get(pid)
            if p and not p.data.get("fresh"):
                p.amount -= 1
                if p.amount <= 0:
                    del P.powers[pid]
            elif p:
                p.data["fresh"] = False
        for pid in [k for k, p in P.powers.items() if p.data.get("this_turn")]:
            del P.powers[pid]

    def enemy_phase(self):
        self.phase = "enemy"
        for e in list(self.enemies):
            if not e.alive or self.result:
                continue
            ev = self.emit("enemy_block_clear", creature=e, keep=0)
            e.block = min(e.block, ev.keep)
            self.emit("turn_start", side="enemy", creature=e)
            if not e.alive:
                continue
            e.take_turn(self)
            if self.result:
                return
            if e.alive:
                self.emit("turn_end", side="enemy", creature=e)
                for pid in ("VULNERABLE", "WEAK", "FRAIL"):
                    p = e.powers.get(pid)
                    if p:
                        if p.data.get("fresh"):
                            p.data["fresh"] = False
                        else:
                            p.amount -= 1
                            if p.amount <= 0:
                                del e.powers[pid]
        for e in self.alive_enemies():
            e.choose_intent(self)
        self.emit("round_end")

    def run(self):
        """完整打一场。返回 result（win / loss / timeout）。"""
        self.start_battle()
        while self.result is None:
            if self.turn >= self.max_turns:
                self.result = "timeout"
                break
            self.start_player_turn()
            if self.result:
                break
            try:
                if self.player.potions and hasattr(self.agent, "use_potions"):
                    self.agent.use_potions(self)
                self.agent.play_turn(self)
            except LoopAlarm:
                seq = [c.name for c in self.cards_played_turn[-12:]]
                self.loop_alarm = {"turn": self.turn, "tail": seq,
                                   "cards": sorted(set(c.base_name for c in self.cards_played_turn))}
                if self.stats is not None:
                    self.stats.alarms.append(self.loop_alarm)
                self.result = "loop"
                break
            if self.result:
                break
            self.end_player_turn()
            self.enemy_phase()
        return self.result
