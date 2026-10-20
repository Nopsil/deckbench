"""决策接口 + 启发式整局 AI。

Agent 的每个方法对应游戏里一个需要玩家输入的点；默认实现是可读的启发式规则。
mod 可以继承 HeuristicAgent，或通过 `card_bias` 钩子（卡牌 Id → 加分函数）实现流派偏好。
"""
import random
import sys

from ..rt.boot import game as G
from .combat import alive_enemies
from .weights import W

RARITY_VALUE = {"Basic": 0.0, "Common": 3.0, "Uncommon": 5.0, "Rare": 7.0, "Ancient": 7.0, "Event": 4.0,
                "Token": 1.0, "Status": -6.0, "Curse": -10.0, "Quest": 0.0, "None": 0.0}


def _name(e):
    try:
        return e.name
    except AttributeError:
        return str(e)


def dvar(card, key):
    dv = card.DynamicVars
    try:
        if dv.ContainsKey(key):
            return float(dv._vars[key].BaseValue) if hasattr(dv, "_vars") else float(getattr(dv, key).BaseValue)
    except Exception:  # noqa
        return 0.0
    return 0.0


def incoming_damage(cs, player):
    total = 0
    pc = player.Creature
    for e in alive_enemies(cs):
        mv = e.Monster.NextMove if e.Monster is not None else None
        if mv is None:
            continue
        for it in mv.Intents:
            if isinstance(it, G.AttackIntent):
                try:
                    total += int(it.GetTotalDamage(G.Seq([pc]), e))
                except Exception:  # noqa
                    pass
    return total


def end_turn_hand_damage(player):
    """手牌里回合结束时会打自己的状态/诅咒牌（感染 Infection 3、灼伤 Burn 2、腐朽 Decay 2、凋零 Wither 3、毒素 Toxic 5…）
    造成的可格挡伤害之和。它们走 CreatureCmd.Damage（DamageVar，非 Unblockable），先吃格挡，所以算进“需要的格挡”。
    HpLossVar 那类（Regret / BadLuck / Beckon）是 Unblockable，格挡无用，不计。"""
    tot = 0.0
    for c in G.PileType.Hand.GetPile(player).Cards:
        try:
            if not c.HasTurnEndInHandEffect or _name(c.Type) not in ("Status", "Curse"):
                continue
        except Exception:  # noqa
            continue
        tot += dvar(c, "Damage")
    return int(tot)


def card_cost(card):
    try:
        return max(0, int(card.EnergyCost.GetResolved()))
    except Exception:  # noqa
        try:
            return max(0, int(card.EnergyCost.Canonical))
        except Exception:  # noqa
            return 1


_WORST_NAMES = ("TransformTo", "Transform", "RemoveFromDeck", "Exhaust", "Discard", "RemoveCard")
_BEST_NAMES = ("CloneCard", "Clone", "Enchant", "Duplicate")


def _prefs_kind(prefs):
    try:
        P = G.CardSelectorPrefs
        pr = prefs.Prompt
    except Exception:  # noqa
        return None
    if pr is P.TransformSelectionPrompt or pr is P.RemoveSelectionPrompt or pr is P.ExhaustSelectionPrompt \
            or pr is P.DiscardSelectionPrompt:
        return "worst"
    if pr is P.UpgradeSelectionPrompt:
        return "upgrade"
    if pr is P.EnchantSelectionPrompt:
        return "best"
    return None


def _caller_kind():
    """从调用栈判断这次选牌的用途（选择器接口本身不带用途）。
    顺序：① 选择提示（prefs.Prompt 是 变形/移除/消耗/弃牌/升级 的标准提示）；② 入口函数名（FromDeckForRemoval 等）；
    ③ 通用入口（FromDeckGeneric/FromSimpleGrid）时，看调用它的游戏函数之后用到了什么命令（TransformTo/RemoveFromDeck → 最差；
    CloneCard/Enchant → 最好）。事件里“交出一张牌”的选择以前会默认选最好的牌，这是错的。"""
    f = sys._getframe(2)
    g = f
    for _ in range(14):
        if g is None:
            break
        if g.f_code.co_name.startswith("From") and "prefs" in g.f_locals:
            k = _prefs_kind(g.f_locals["prefs"])
            if k:
                return k
            if g.f_code.co_name in ("FromDeckGeneric", "FromSimpleGrid") and g.f_back is not None:
                up = g.f_back
                if up.f_code.co_name.startswith("From"):
                    up = up.f_back
                names = set(up.f_code.co_names) if up is not None else set()
                if any(n in names for n in _WORST_NAMES):
                    return "worst"
                if "Upgrade" in names and not any(n in names for n in _BEST_NAMES):
                    return "upgrade"
        g = g.f_back
    for _ in range(12):
        if f is None:
            break
        n = f.f_code.co_name
        if n.startswith("From") or n in ("GetSelectedCards",):
            if "Removal" in n or "Transformation" in n or "Discard" in n or n == "FromHand":
                return "worst"
            if "Upgrade" in n:
                return "upgrade"
            if "Enchantment" in n:
                return "best"
            if n.startswith("From"):
                return "best"
        f = f.f_back
    return "best"


class Agent:
    """接口（全部可覆盖）。"""
    name = "base"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.player = None

    def on_run_start(self, player, run):
        self.player = player

    def on_combat_start(self, cs, player, room):
        pass

    def combat_action(self, cs, player, acts):
        return acts[-1]

    def select_cards(self, options, min_sel, max_sel):
        return list(options)[:min_sel]

    def card_reward(self, cards, alternatives):
        return None

    def take_reward(self, reward):
        return True

    def choose_map_point(self, points, run):
        return points[0]

    def rest_option(self, options, run):
        return 0

    def shop(self, inventory, run):
        return []

    def event_option(self, event, options, run):
        enabled = [i for i, o in enumerate(options) if not o.IsLocked]
        return enabled[0] if enabled else 0

    def treasure_relic(self, relics, run):
        return 0 if relics else None

    def choose_bundle(self, bundles):
        return 0


# Mod 可注册的出牌估值修正：Id.Entry -> f(agent, card, target, cs, player, ctx) -> 额外价值（等效 HP，费用折算前）
PLAY_ADJUST = {}


class HeuristicAgent(Agent):
    """启发式：意图感知的出牌 + 简单路线/奖励/商店/休息策略。card_bias 由 mod 注入（流派偏好）。"""
    name = "heuristic"

    def __init__(self, seed=0, card_bias=None, skip_threshold=4.0):
        super().__init__(seed)
        self.card_bias = card_bias or {}
        self.skip_threshold = skip_threshold
        self.room_kind = None

    # ---------- 卡牌价值 ----------
    def card_value(self, card, deck=None):
        v = RARITY_VALUE.get(_name(card.Rarity), 0.0)
        tn = _name(card.Type)
        if tn == "Power":
            v += 1.5
        if card.IsUpgraded if hasattr(card, "IsUpgraded") else False:
            v += 1.0
        if _name(card.Rarity) == "Basic":
            e = card.Id.Entry
            v += -1.0 if (e.startswith("STRIKE") or e.startswith("DEFEND")) else 2.0
        b = self.card_bias.get(card.Id.Entry)
        if b is not None:
            v += b(card, deck, self) if callable(b) else b
        return v

    # ---------- 战斗 ----------
    def on_combat_start(self, cs, player, room):
        self.room_kind = _name(room.RoomType)

    @staticmethod
    def _preview(card, target):
        """用游戏自己的预览计算（力量/易伤/虚弱/遗物等钩子都算进去）。返回 (伤害, 段数, 格挡)。"""
        dv = card.DynamicVars
        try:
            card.UpdateDynamicVarPreview(G.CardPreviewMode.None_, target, dv)
        except Exception:  # noqa
            pass
        def pv(k):
            try:
                if dv.ContainsKey(k):
                    v = dv._vars[k]
                    x = v.PreviewValue
                    return float(x if x is not None else v.BaseValue)
            except Exception:  # noqa
                return 0.0
            return 0.0
        dmg = pv("CalculatedDamage") or pv("Damage") or pv("OstyDamage")
        hits = max(1.0, pv("CalculatedHits") or pv("Repeat") or 1.0)
        blk = pv("CalculatedBlock") or pv("Block")
        return dmg, hits, blk

    @staticmethod
    def _enemy_incoming(e, pc):
        mv = e.Monster.NextMove if e.Monster is not None else None
        tot = 0
        if mv is None:
            return 0
        for it in mv.Intents:
            if isinstance(it, G.AttackIntent):
                try:
                    tot += int(it.GetTotalDamage(G.Seq([pc]), e))
                except Exception:  # noqa
                    pass
        return tot

    def _score_play(self, card, target, cs, player, ctx):
        """价值以“等效 HP”计：格挡 1 点 ≈ 少掉 1 HP；伤害 1 点 ≈ 缩短战斗省下的 k HP；击杀 ≈ 省下它本回合的伤害。"""
        tn = _name(card.Type)
        cost = card_cost(card)
        en = alive_enemies(cs)
        k = ctx["k"] * W["c_k"]
        dmg, hits, blk = self._preview(card, target)
        s = 0.0
        tt = card.TargetType
        if dmg > 0:
            if tt == G.TargetType.AllEnemies:
                tgts = en
            elif tt == G.TargetType.RandomEnemy:
                tgts = en[:1]
            else:
                tgts = [target] if target is not None else en[:1]
            for t in tgts:
                d = dmg * hits
                if tt == G.TargetType.AllEnemies and t is not target:
                    d = self._preview(card, t)[0] * hits
                eff = t.CurrentHp + t.Block
                mprio = W["c_minion"] if (ctx.get("minion") and id(t) in ctx["minion"]) else 1.0
                if d >= eff:
                    s += (t.CurrentHp * k * mprio + ctx["inc"].get(id(t), 0) * 1.0 + 3.0) * W["c_kill"]
                else:
                    s += max(0.0, d - t.Block) * k + min(d, t.Block) * 0.4 * k
                s += 0.4 * hits * k   # 每段命中（触发命中效果）
                slip = ctx["slip"].get(id(t), 0)
                if slip:
                    s += min(hits, slip) * 2.5   # Slippery：每段命中剥一层“伤害封顶为 1”
        if blk > 0:
            need = ctx["need"]
            s += min(blk, need) * W["c_blk"] + max(0.0, blk - need) * W["c_blk_over"]
            ctx_used = min(blk, need)
        rnd = cs.RoundNumber
        long_fight = self.room_kind in ("Elite", "Boss")
        ehp = ctx["ehp"]
        if tn == "Power":
            s += W["c_power"] * (6.0 if rnd <= 2 else 3.0 if rnd <= 4 else 1.0) * (1.5 if long_fight else 1.0) * min(2.0, ehp / 40.0 + 0.3)
        v = lambda key: dvar(card, key)  # noqa
        if v("VulnerablePower") and len(en):
            s += W["c_vuln"] * min(v("VulnerablePower"), 3) * 2.5 * k * min(1.5, ehp / 30.0)
        if v("WeakPower"):
            inc = ctx["inc"].get(id(target), 0) if target is not None else sum(ctx["inc"].values())
            s += W["c_weak"] * min(v("WeakPower"), 3) * max(inc, ctx["avg_inc"] * 0.5) * 0.25
        fight_len = min(2.5, ehp / 35.0 + 0.2)
        s += W["c_scal"] * (v("StrengthPower") * 2.5 + v("DexterityPower") * 2.5 + v("FocusPower") * 2.5) * fight_len
        s += v("PoisonPower") * 1.0 * k * 2 + v("DoomPower") * 0.8 * k + v("PlatingPower") * 1.5 * fight_len
        s += v("Cards") * W["c_draw"] + v("Energy") * W["c_energy"] + v("Summon") * 1.2 + v("Forge") * 0.8 + v("Stars") * 1.2
        s += v("Shivs") * 2.5 * k + v("VigorPower") * 0.8 + v("ThornsPower") * 1.0 * fight_len
        s -= v("HpLoss") * 0.8
        if v("StrengthLoss") and target is not None:
            s += v("StrengthLoss") * 1.5 * fight_len
        adj = PLAY_ADJUST.get(card.Id.Entry)
        if adj is not None:
            s += adj(self, card, target, cs, player, ctx)
        if s == 0.0:
            s = 2.0 if tn in ("Skill", "Power") else 0.4
        if tn in ("Status", "Curse"):
            s = 0.3
        s += self.card_value(card) * 0.05
        return s / (cost + 0.5)

    def combat_action(self, cs, player, acts):
        ctx = self._make_ctx(cs, player)
        hp = player.Creature.CurrentHp
        best, best_s = acts[-1], 0.0
        for a in acts:
            if a[0] == "play":
                s = self._score_play(a[1], a[2], cs, player, ctx)
                if s < 0.03:
                    continue
            elif a[0] == "potion":
                s = self._score_potion(a[1], a[2], cs, player, ctx["need"], hp)
                if s < 0.9:
                    continue
            else:
                continue
            if s > best_s:
                best, best_s = a, s
        return best

    def _make_ctx(self, cs, player):
        pc = player.Creature
        en = alive_enemies(cs)
        inc = {id(e): self._enemy_incoming(e, pc) for e in en}
        incoming = sum(inc.values())
        st = getattr(self, "_inc_hist", None)
        if st is None or st[0] is not cs:
            st = self._inc_hist = [cs, -1, []]
        if st[1] != cs.RoundNumber:
            st[1] = cs.RoundNumber
            st[2].append(incoming)
        avg_inc = max(4.0, sum(st[2]) / len(st[2]))
        ehp = float(sum(e.CurrentHp + e.Block for e in en)) or 1.0
        k = max(0.2, min(1.3, avg_inc * 1.6 / ehp))
        slip = {}
        leaders = [e for e in en if not any(pw.Id.Entry == "MINION_POWER" for pw in e.Powers)]
        minion = {id(e) for e in en if leaders and any(pw.Id.Entry in ("MINION_POWER", "ILLUSION_POWER") for pw in e.Powers)}
        for e in en:
            for pw in e.Powers:
                if pw.Id.Entry == "SLIPPERY_POWER":
                    slip[id(e)] = int(pw.Amount)
        ctx = {"inc": inc, "need": max(0, incoming + end_turn_hand_damage(player) - pc.Block), "k": k, "ehp": ehp,
               "avg_inc": avg_inc, "slip": slip, "minion": minion}
        return ctx

    def _score_potion(self, potion, target, cs, player, need_block, hp):
        dangerous = need_block >= hp * W["p_danger"] or hp <= player.Creature.MaxHp * W["p_lowhp"]
        important = self.room_kind in ("Elite", "Boss") and cs.RoundNumber <= 2
        if dangerous or important:
            return 6.0
        return 0.0

    # ---------- 选牌 ----------
    def select_cards(self, options, min_sel, max_sel):
        opts = list(options)
        kind = _caller_kind()
        if kind == "upgrade":
            key = lambda c: -(self.card_value(c) + (5 if not c.IsUpgraded else -10))  # noqa
            opts.sort(key=key)
            return opts[:max(min_sel, min(1, max_sel))]
        if kind == "worst":
            opts.sort(key=lambda c: self.card_value(c))
            return opts[:min_sel] if min_sel > 0 else []
        opts.sort(key=lambda c: -self.card_value(c))
        n = max(min_sel, min(1, max_sel))
        return opts[:n]

    def card_reward(self, cards, alternatives):
        deck = list(self.player.Deck.Cards) if self.player else []
        best, bv = None, -99.0
        for r in cards:
            c = r.Card if hasattr(r, "Card") else r
            v = self.card_value(c, deck)
            if v > bv:
                best, bv = c, v
        thresh = self.skip_threshold + max(0, len(deck) - 22) * 0.25
        return best if bv >= thresh - 3.0 else None

    # ---------- 地图 ----------
    # 粗略 HP 模型（占最大 HP 比例）：普通怪/精英的期望损失，休息恢复 30%
    MAP_COST = {"Monster": 0.11, "Elite": 0.27, "Boss": 0.35, "Unknown": 0.04}
    MAP_GAIN = {"Monster": 4.0, "Elite": 11.0, "Treasure": 7.0, "Unknown": 3.0, "Shop": 0.0, "RestSite": 0.0, "Boss": 0.0}

    def choose_map_point(self, points, run):
        p = self.player
        hp0 = p.Creature.CurrentHp / max(1, p.Creature.MaxHp)
        gold = p.Gold
        memo = {}

        def node_val(pt, hp):
            t = _name(pt.PointType)
            g = self.MAP_GAIN.get(t, 0.0)
            hp2 = hp - self.MAP_COST.get(t, 0.0) * (1.0 + 0.15 * run.state.CurrentActIndex)
            if t == "RestSite":
                if hp < 0.6:
                    hp2 = min(1.0, hp + 0.3)
                    g = 2.0
                else:
                    g = 5.0   # 升级
            elif t == "Shop":
                g = 4.0 if gold >= 120 else 1.0
            if hp2 <= 0.12:
                g -= 40.0 * (0.12 - hp2) / 0.12 + 15.0
            return g, hp2

        def best(pt, hp):
            key = (pt.coord.col, pt.coord.row, round(hp * 20))
            if key in memo:
                return memo[key]
            g, hp2 = node_val(pt, hp)
            ch = list(pt.Children)
            r = g + (max(best(c, hp2) for c in ch) if ch else hp2 * 20.0)
            memo[key] = r
            return r

        return max(points, key=lambda pt: (best(pt, hp0), self.rng.random()))

    # ---------- 休息处 ----------
    def rest_option(self, options, run):
        p = self.player
        hp_frac = p.Creature.CurrentHp / max(1, p.Creature.MaxHp)
        ids = [str(o.OptionId) for o in options]
        def find(key):
            for i, s in enumerate(ids):
                if key in s.upper():
                    return i
            return None
        heal, smith = find("HEAL"), find("SMITH")
        boss_next = False
        try:
            cur = run.state.CurrentMapPoint
            boss_next = any(_name(c.PointType) == "Boss" for c in cur.Children)
        except Exception:  # noqa
            pass
        if heal is not None and (hp_frac < 0.55 or (boss_next and hp_frac < 0.8)):
            return heal
        if smith is not None:
            return smith
        return heal if heal is not None else (0 if options else None)

    # ---------- 商店 ----------
    def shop(self, inventory, run):
        """返回本次要买的条目（按顺序尝试）。"""
        buys = []
        rem = inventory.CardRemovalEntry
        if rem is not None and rem.IsStocked:
            buys.append(rem)
        for e in inventory.RelicEntries:
            if e.IsStocked:
                buys.append(e)
        for e in inventory.CardEntries:
            if e.IsStocked and e.CreationResult is not None and self.card_value(e.CreationResult.Card) >= 6.0:
                buys.append(e)
        return buys

    def event_option(self, event, options, run):
        p = self.player
        enabled = [i for i, o in enumerate(options) if not o.IsLocked]
        if not enabled:
            return 0
        def risky(o):
            f = getattr(o, "WillKillPlayer", None)
            if f is None:
                return False
            try:
                # 用“HP 低于一半时是否致命”近似这项代价
                return bool(f(p)) or p.Creature.CurrentHp < p.Creature.MaxHp * 0.4
            except Exception:  # noqa
                return False
        safe = [i for i in enabled if not risky(options[i])]
        pool = safe or enabled
        relic = [i for i in pool if getattr(options[i], "Relic", None) is not None]
        if relic and self.rng.random() < 0.7:
            return self.rng.choice(relic)
        return self.rng.choice(pool)

    def treasure_relic(self, relics, run):
        return 0 if relics else None

    def choose_bundle(self, bundles):
        deck = list(self.player.Deck.Cards) if self.player else []
        return max(range(len(bundles)), key=lambda i: sum(self.card_value(c, deck) for c in bundles[i]))
