"""StrongAgent：在 SearchAgent（战斗前瞻）基础上重写局外决策。

借鉴 StS1 的 Bottled AI（xaved88/bottled_ai）等机器人的做法：
  * 选牌：给每张牌估一个与角色无关的“卡牌强度”（按游戏自带的动态数值折算成“每能量的打击当量”），
    再加上牌组层面的边际修正：第 1 幕缺前期伤害 / 缺群伤 / 缺成长、同流派协同、重复张惩罚、牌组越厚门槛越高（要敢跳过）。
  * 删牌：诅咒 > 状态 > 打击 > 防御。
  * 路线：第 1 幕前期少打精英；按 HP 估算路线收益，休息处按 HP 决定休息还是升级。
  * 商店：先删牌，再买高价值牌和遗物，有空药水栏且便宜时买药水。
  * 战斗：精英和 Boss 用更深的前瞻（2 回合、更宽）；普通怪 1 回合。
"""
from ..rt.boot import game as G
from .agents import _name, dvar, card_cost
from .search import SearchAgent
from .combat import alive_enemies
from .weights import W

TAGS = {
    "str": ("StrengthPower", "VigorPower", "StrengthPerVulnerable", "Colossus", "DemonForm"),
    "block": ("PlatingPower", "DexterityPower", "BlockNextTurn", "Blur", "ThornsPower"),
    "poison": ("PoisonPower", "PoisonPerTurn", "EnvenomPower", "OutbreakPower", "CorrosiveWave", "Accelerant"),
    "shiv": ("Shivs", "CalculatedShivs", "AccuracyPower", "PhantomBladesPower"),
    "orb": ("FocusPower",),
    "doom": ("DoomPower",),
    "osty": ("Summon", "OstyDamage"),
    "star": ("Stars", "Forge", "StarsPerTurn", "CalculatedForge", "BlockForStars"),
}


def _kw(card):
    try:
        return {_name(k) for k in card.Keywords}
    except Exception:  # noqa
        return set()


_HITS = {}


def _src_hits(card):
    """很多多段攻击的段数写死在 OnPlay 里（WithHitCount(2)），从转译源码里读出来。"""
    t = type(card)
    if t not in _HITS:
        import inspect
        import re
        n = 1
        try:
            src = inspect.getsource(t.OnPlay) if "OnPlay" in t.__dict__ else ""
            m = re.search(r"WithHitCount\((\d+)\)", src)
            if m:
                n = int(m.group(1))
        except Exception:  # noqa
            pass
        _HITS[t] = n
    return _HITS[t]


# 少量手工修正（参考 StS1 机器人的优先级表思路：数值看不出来的条件牌/引擎牌）
OVERRIDE = {
    "PACTS_END": -5.0, "GRAND_FINALE": -13.0, "BOUNCING_FLASK": 2.0, "CORRUPTION": 3.0, "BARRICADE": 1.5, "DEMON_FORM": 1.0, "FEED": 1.0,
    "FIEND_FIRE": 1.5, "TEAR_ASUNDER": 1.0, "DOMINATE": 0.8, "WRAITH_FORM": 2.0, "AFTERIMAGE": 1.0,
    "ECHO_FORM": 2.0, "BLACK_HOLE": 0.5, "CATALYST": 1.0, "MALAISE": 1.0, "ADRENALINE": 1.0,
}


# Mod 可注册的卡牌估值：Id.Entry -> (强度, 标签集合)。模组角色的牌通常无法从通用变量看出强度
#（例如 Claude娘 的「风控」体系），由模组提供与原版同一量纲的估值表（0 ≈ 打击）。
MOD_POWER = {}
# Mod 可注册的选牌协同偏置：Id.Entry -> f(card, deck, agent) -> 加分（与 card_bias 叠加）
MOD_BIAS = {}


def card_power(card):
    """返回 (强度, 标签集合)。0 ≈ 打击；正数越大越好。"""
    mp = MOD_POWER.get(card.Id.Entry)
    if mp is not None:
        return mp[0], set(mp[1])
    tn = _name(card.Type)
    rar = _name(card.Rarity)
    if tn == "Curse" or rar == "Curse":
        return -6.0, set()
    if tn == "Status" or rar == "Status":
        return -3.0, set()
    v = lambda k: dvar(card, k)  # noqa
    kw = _kw(card)
    if "Unplayable" in kw:
        return -3.0, set()
    try:
        xcost = bool(card.EnergyCost.CostsX)
    except Exception:  # noqa
        xcost = False
    cost = 2.0 if xcost else float(card_cost(card))
    calc = (v("CalculationBase") + v("ExtraDamage") * 4.0 + v("CalculationExtra") * 2.0) if v("CalculatedDamage") else 0.0
    dmg = max(v("Damage"), v("OstyDamage"), calc)
    hits = max(1.0, v("Repeat"), 2.0 if "CalculatedHits" in getattr(card.DynamicVars, "_vars", {}) else 1.0,
               float(_src_hits(card)))
    if xcost:
        hits *= 3.0
    tt = card.TargetType
    aoe = tt == G.TargetType.AllEnemies
    d = dmg * hits * (1.5 if aoe else 0.9 if tt == G.TargetType.RandomEnemy else 1.0)
    blk = v("Block") or (v("CalculationBase") if v("CalculatedBlock") else 0.0)
    base = d / 6.0 + blk / 5.0 * 0.85
    base += v("Cards") * 0.9 + v("Energy") * 1.3 + v("Stars") * 0.6 + v("Forge") * 0.1 + v("Summon") * 0.25
    base += v("VulnerablePower") * 0.6 + v("WeakPower") * 0.55 + v("PoisonPower") * 0.3 + v("DoomPower") * 0.12
    base += v("Shivs") * 0.6 + v("PlatingPower") * 0.45 + v("VigorPower") * 0.15 + v("StrengthLoss") * 0.2
    base += v("IntangiblePower") * 3.0 + v("Heal") * 0.1 + v("MaxHp") * 0.3
    base -= v("HpLoss") * 0.12
    if tn == "Power":
        base += v("StrengthPower") * 1.8 + v("DexterityPower") * 1.4 + v("FocusPower") * 1.8 + v("ThornsPower") * 0.4
        base += 1.6   # 未识别的持续效果
    else:
        base += v("StrengthPower") * 0.6 + v("DexterityPower") * 0.5 + v("FocusPower") * 0.6
    if base <= 0.05:
        base = 1.0 + cost   # 无法从数值看出强度的特殊牌：按费用给中性估值
    s = base - cost * 1.0 + OVERRIDE.get(card.Id.Entry, 0.0)
    s += {"Uncommon": 0.35, "Rare": 0.7}.get(rar, 0.0)
    if "Exhaust" in kw and tn != "Power":
        s -= 0.15
    if "Ethereal" in kw:
        s -= 0.3
    if "Innate" in kw or "Retain" in kw:
        s += 0.15
    if aoe and d > 0:
        s += 0.2
    tags = {t for t, keys in TAGS.items() if any(v(k) for k in keys)}
    if tn == "Power":
        tags.add("scaling")
    if aoe and d > 0:
        tags.add("aoe")
    if d > 0:
        tags.add("attack")
    return s, tags


def basic_value(card):
    e = card.Id.Entry
    if e.startswith("STRIKE"):
        return -1.0
    if e.startswith("DEFEND"):
        return -0.6
    return None


class StrongAgent(SearchAgent):
    name = "strong"

    def __init__(self, seed=0, width=5, depth=1, elite_width=8, elite_depth=2, search=True, selective=True,
                 boss_aware=True, boss_search=False, boss_width=None, boss_depth=None, **kw):
        super().__init__(seed=seed, width=width, depth=depth, **kw)
        self.boss_aware = boss_aware          # 按本幕首领调整选牌/休息
        self.boss_search = boss_search        # 不搜索模式下，只在首领战里开搜索
        self.search = search
        self.selective = selective
        self.base_width, self.base_depth = width, depth
        self.elite_width, self.elite_depth = elite_width, elite_depth
        # 首领战单独的搜索宽度/深度（深度 ≥ 20 = 每个候选都用快速策略一直打到战斗结束，即蒙特卡洛整场推演）
        self.boss_width = boss_width or elite_width
        self.boss_depth = boss_depth or elite_depth
        self._pcache = {}

    # ---------- 战斗：精英/Boss 深搜 ----------
    def on_combat_start(self, cs, player, room):
        super().on_combat_start(cs, player, room)
        if self.room_kind == "Boss":
            self.width, self.depth = self.boss_width, self.boss_depth
        elif self.room_kind == "Elite":
            self.width, self.depth = self.elite_width, self.elite_depth
        else:
            self.width, self.depth = self.base_width, self.base_depth

    def _consequential(self, cs, player, acts):
        """只在“有意义”的决策点搜索：精英/Boss、来袭伤害高、手里有能力牌或可用药水。"""
        if self.room_kind in ("Elite", "Boss"):
            return True
        pc = player.Creature
        inc = sum(self._enemy_incoming(e, pc) for e in alive_enemies(cs))
        if inc - pc.Block >= max(8, pc.CurrentHp * 0.2):
            return True
        for a in acts:
            if a[0] == "potion":
                return True
            if a[0] == "play" and _name(a[1].Type) == "Power":
                return True
        return False

    def combat_action(self, cs, player, acts):
        from .agents import HeuristicAgent
        if not self.search and self.boss_search and self.room_kind == "Boss":
            return super().combat_action(cs, player, acts)
        if not self.search or (self.selective and not self._in_child and not self._consequential(cs, player, acts)):
            return HeuristicAgent.combat_action(self, cs, player, acts)
        return super().combat_action(cs, player, acts)

    # ---------- 牌的价值 ----------
    def _power(self, card):
        key = (card.Id.Entry, bool(getattr(card, "IsUpgraded", False)))
        r = self._pcache.get(key)
        if r is None:
            r = self._pcache[key] = card_power(card)
        return r

    def card_value(self, card, deck=None):
        b = basic_value(card) if _name(card.Rarity) == "Basic" else None
        if b is not None:
            return b
        s, _ = self._power(card)
        if getattr(card, "IsUpgraded", False):
            s += 0.3
        bias = self.card_bias.get(card.Id.Entry)
        if bias is not None:
            s += bias(card, deck, self) if callable(bias) else bias
        mb = MOD_BIAS.get(card.Id.Entry)
        if mb is not None:
            s += mb(card, deck, self)
        return s

    def _deck_profile(self, deck):
        prof = {"n": len(deck), "attack_power": 0.0, "aoe": 0, "scaling": 0, "tags": {}, "ids": {}}
        for c in deck:
            if _name(c.Type) in ("Curse", "Status"):
                continue
            s, tags = self._power(c)
            prof["ids"][c.Id.Entry] = prof["ids"].get(c.Id.Entry, 0) + 1
            if basic_value(c) is not None and _name(c.Rarity) == "Basic":
                continue
            if "attack" in tags:
                prof["attack_power"] += max(0.0, s + 1.0)
            prof["aoe"] += "aoe" in tags
            prof["scaling"] += "scaling" in tags
            for t in tags:
                prof["tags"][t] = prof["tags"].get(t, 0) + 1
        return prof

    # ---------- 首领感知 ----------
    BOSS_TRAITS = {"VANTOM": {"multihit"}}     # Slippery：每段命中剥一层“伤害封顶 1”，多段攻击更有效

    def boss_profile(self):
        """本幕首领（开幕即已知）：总生命、是否多单位、特性。缓存到幕切换。"""
        try:
            st = self._run.state
            act = st.CurrentActIndex
        except Exception:  # noqa
            return None
        bp = getattr(self, "_boss", None)
        if bp is not None and bp["act"] == act:
            return bp
        try:
            enc = st.Act.BossEncounter
            mons = list(G._iter(enc.AllPossibleMonsters))
            hp = sum(int(m.MaxInitialHp) for m in mons)
            traits = set()
            for m in mons:
                traits |= self.BOSS_TRAITS.get(m.Id.Entry, set())
            bp = {"act": act, "id": enc.Id.Entry, "hp": hp, "multi": len(mons) > 1, "traits": traits}
        except Exception:  # noqa
            bp = {"act": act, "id": "?", "hp": 200 + 150 * act, "multi": False, "traits": set()}
        self._boss = bp
        return bp

    def big_multi_elite(self):
        """本幕（或下一幕，第 1 幕后半段起）是否有 ≥3 只怪的精英（异蛙寄生虫 5、花园幽灵鳗 4、千足虫/骑士 3）。0/1。"""
        try:
            st = self._run.state
            act = st.CurrentActIndex
        except Exception:  # noqa
            return 0.0
        c = getattr(self, "_bme", None)
        if c is not None and c[0] == act:
            return c[1]
        f = 0.0
        try:
            for e in G._iter(st.Act.AllEliteEncounters):
                try:
                    n = max(len(list(G._iter(e.AllPossibleMonsters))), len(list(e.Slots or [])))
                except Exception:  # noqa
                    n = len(list(e.Slots or []))
                if n >= 3:
                    f = 1.0
        except Exception:  # noqa
            pass
        self._bme = (act, f)
        return f

    def multi_threat(self):
        """本幕“多目标”威胁：精英/普通遭遇里多只怪（含召唤，如异蛙寄生虫的 4 只扭动虫）的比例，0–1。缓存到幕切换。"""
        try:
            st = self._run.state
            act = st.CurrentActIndex
        except Exception:  # noqa
            return 0.0
        mt = getattr(self, "_mt", None)
        if mt is not None and mt[0] == act:
            return mt[1]
        try:
            encs = list(G._iter(st.Act.AllEliteEncounters)) + list(G._iter(st.Act.AllRegularEncounters))
            el = list(G._iter(st.Act.AllEliteEncounters))
            def multi(e):
                try:
                    return _multi(e)
                except Exception:  # noqa  （个别遭遇的 AllPossibleMonsters 转译不完整）
                    return len(list(e.Slots or [])) > 1

            def _multi(e):
                return max(len(list(G._iter(e.AllPossibleMonsters))), len(list(e.Slots or []))) > 1
            f = 0.6 * (sum(map(multi, el)) / max(1, len(el))) + 0.4 * (sum(map(multi, encs)) / max(1, len(encs)))
        except Exception:  # noqa
            f = 0.0
        self._mt = (act, f)
        return f

    def _boss_bias(self, card, tags, p):
        bp = self.boss_profile() if self.boss_aware else None
        if bp is None:
            return 0.0
        b = 0.0
        need = bp["hp"] / 40.0          # 约 6–7 回合打完首领所需的“攻击强度”
        if "attack" in tags and p["attack_power"] < need:
            b += min(0.6, 0.15 * (need - p["attack_power"]))
        if bp["multi"] and "aoe" in tags and p["aoe"] < 2:
            b += 0.4
        if "multihit" in bp["traits"]:
            hits = max(1.0, dvar(card, "Repeat"), float(_src_hits(card)), dvar(card, "Hits"))
            if hits >= 2:
                b += 0.5
        return b

    def marginal(self, card, deck, act=None):
        if act is None:
            try:
                act = self._run.state.CurrentActIndex
            except Exception:  # noqa
                act = 0
        s = self.card_value(card, deck)
        _, tags = self._power(card)
        p = self._deck_profile(deck)
        if "attack" in tags and act == 0 and p["attack_power"] < 6.0:
            s += W["d_atk1"]          # 第 1 幕：前期伤害不足时优先攻击牌（打精英）
        if "attack" in tags and p["attack_power"] < 4.0 + 4.0 * act:
            s += W["d_atk"]          # Boss 需要足够的单体输出（第 1 幕 Boss 150~200 HP）
        if "aoe" in tags and p["aoe"] < 2:
            s += (W["d_aoe"] + W["d_aoe_threat"] * self.multi_threat() + W["d_aoe_elite"] * self.big_multi_elite()) \
                * (1.0 if p["aoe"] == 0 else W["d_aoe2"])
        if "scaling" in tags and p["scaling"] < 2 and act >= 0:
            s += W["d_scal"] + 0.2 * act
        syn = sum(p["tags"].get(t, 0) for t in tags if t not in ("attack", "scaling", "aoe"))
        s += min(1.5, W["d_syn"] * syn)
        dup = p["ids"].get(card.Id.Entry, 0)
        s -= W["d_dup"] * dup
        s += self._boss_bias(card, tags, p)
        return s

    def _threshold(self, deck):
        return W["d_thr0"] + W["d_thr_slope"] * max(0, len(deck) - 14)

    def on_run_start(self, player, run):
        super().on_run_start(player, run)
        self._run = run

    def card_reward(self, cards, alternatives):
        deck = list(self.player.Deck.Cards) if self.player else []
        best, bv = None, -99.0
        for r in cards:
            c = r.Card if hasattr(r, "Card") else r
            m = self.marginal(c, deck)
            if m > bv:
                best, bv = c, m
        return best if bv >= self._threshold(deck) else None

    def choose_bundle(self, bundles):
        deck = list(self.player.Deck.Cards) if self.player else []
        return max(range(len(bundles)), key=lambda i: sum(self.marginal(c, deck) for c in bundles[i]))

    def select_cards(self, options, min_sel, max_sel):
        from .agents import _caller_kind
        opts = list(options)
        kind = _caller_kind()
        if kind == "upgrade":
            def gain(c):
                if getattr(c, "IsUpgraded", False):
                    return -10.0
                s, tags = self._power(c)
                g = 0.5 + max(0.0, s) * 0.3 + (1.0 if _name(c.Type) == "Power" else 0.0)
                if _name(c.Rarity) == "Basic":
                    g -= 0.6
                return g
            opts.sort(key=lambda c: -gain(c))
            return opts[:max(min_sel, min(1, max_sel))]
        if kind == "worst":
            opts.sort(key=lambda c: self.card_value(c))
            return opts[:min_sel] if min_sel > 0 else []
        opts.sort(key=lambda c: -self.card_value(c))
        return opts[:max(min_sel, min(1, max_sel))]

    # ---------- 地图 ----------
    def choose_map_point(self, points, run):
        p = self.player
        st = run.state
        act = st.CurrentActIndex
        deck = list(p.Deck.Cards)
        prof = self._deck_profile(deck)
        strength = prof["attack_power"] + prof["scaling"] * 1.5 + act * 3.0
        hp0 = p.Creature.CurrentHp / max(1, p.Creature.MaxHp)
        gold = p.Gold
        memo = {}
        cost = {"Monster": 0.10 + 0.03 * act, "Elite": W["m_elite_cost"] + 0.05 * act, "Unknown": 0.04 + 0.01 * act,
                "Boss": 0.40}
        if strength < 5.0:
            cost["Elite"] += W["m_weak_elite"]   # 牌组太弱：精英更危险
        gain = {"Monster": 3.5, "Elite": W["m_elite_gain"], "Treasure": 7.0, "Unknown": W["m_unknown"], "Shop": 0.0, "RestSite": 0.0, "Boss": 0.0}

        def node_val(pt, hp):
            t = _name(pt.PointType)
            g = gain.get(t, 0.0)
            hp2 = hp - cost.get(t, 0.0)
            if t == "Elite" and act == 0 and pt.coord.row < 5:
                g -= 4.0
            if t == "RestSite":
                if hp < 0.55:
                    hp2 = min(1.0, hp + 0.3)
                    g = 2.5
                else:
                    g = W["m_rest_upg"]
            elif t == "Shop":
                g = 5.0 if gold >= 150 else 2.0 if gold >= 90 else 0.5
            if hp2 <= 0.15:
                g -= 30.0 * (0.15 - hp2) / 0.15 + 12.0
            return g, hp2

        def best(pt, hp):
            key = (pt.coord.col, pt.coord.row, round(hp * 20))
            if key in memo:
                return memo[key]
            g, hp2 = node_val(pt, hp)
            ch = list(pt.Children)
            r = g + (max(best(c, hp2) for c in ch) if ch else hp2 * 25.0)
            memo[key] = r
            return r

        return max(points, key=lambda pt: (best(pt, hp0), self.rng.random()))

    # ---------- 休息 ----------
    def rest_option(self, options, run):
        p = self.player
        hp = p.Creature.CurrentHp / max(1, p.Creature.MaxHp)
        ids = [str(o.OptionId).upper() for o in options]
        heal = next((i for i, s in enumerate(ids) if "HEAL" in s), None)
        smith = next((i for i, s in enumerate(ids) if "SMITH" in s), None)
        danger = boss_next = False
        try:
            cur = run.state.CurrentMapPoint
            nxt = list(cur.Children)
            danger = any(_name(c.PointType) in ("Boss", "Elite") for c in nxt)
            boss_next = any(_name(c.PointType) == "Boss" for c in nxt)
        except Exception:  # noqa
            pass
        if heal is not None and (hp < W["r_heal"] or (danger and hp < W["r_danger"])):
            return heal
        if heal is not None and boss_next and self.boss_aware:
            # 首领战平均掉 35–50 HP：除非生命足以扛过首领战，否则回血
            bp = self.boss_profile()
            exp_loss = 0.25 + 0.0008 * (bp["hp"] if bp else 250)
            if hp - exp_loss < 0.45:
                return heal
        if smith is not None:
            return smith
        return heal if heal is not None else 0

    # ---------- 商店 ----------
    def shop(self, inventory, run):
        p = self.player
        deck = list(p.Deck.Cards)
        buys = []
        rem = inventory.CardRemovalEntry
        if rem is not None and rem.IsStocked:
            buys.append(rem)
        for e in inventory.RelicEntries:
            if e.IsStocked:
                buys.append(e)
        cards = []
        for e in inventory.CardEntries:
            if e.IsStocked and e.CreationResult is not None:
                m = self.marginal(e.CreationResult.Card, deck)
                if m >= self._threshold(deck) + W["s_margin"]:
                    cards.append((m, e))
        cards.sort(key=lambda x: -x[0])
        buys += [e for _, e in cards[:2]]
        empty = sum(1 for x in p.PotionSlots if x is None)
        if empty:
            for e in inventory.PotionEntries:
                if e.IsStocked and e.Cost <= 75 and empty > 0:
                    buys.append(e)
                    empty -= 1
        return buys
