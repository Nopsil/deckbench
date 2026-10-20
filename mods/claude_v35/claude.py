"""Claude娘 v3.5：新引擎（转译游戏代码）上的实现。

  * 数值全部来自 cards_v35.py（CARDS / VARIANTS），这里只有效果实现。
  * 风控 FK、【反击】、宪法（口袋版）等都是游戏的 PowerModel / RelicModel 子类，走游戏自己的钩子和命令。
  * 风控事件契约（v3.5）：
      give()    = 给予：实际增加正层数才发 on_fk_given(target, n, active, card)；RLHF 只修正本次数量；
                  主动给予 = 你的回合里由卡牌/你的能力产生；遗物与敌方回合的给予为被动。
      clear()   = 清除：实际清掉正层数才发 on_fk_cleared(target, n, card)；死亡不算清除。
      set_fk()  = 层数操作（翻倍/三倍/拉齐/转移/反击减层）：不发事件；对 0→正 的复制/转移由人工制品拦截（PowerCmd.Apply 天然如此）。
  * 【反击】：AfterDamageReceived 结算（所有“受击挂层”都在 BeforeDamageReceived 里，所以“先挂层、再反伤、再减 1 层”）。
"""
import math

from sts2sim.rt.boot import game as G

from .cards_v35 import CARDS, VARIANTS, STARTING_HP

META = type(G.CardModel)
_STATE = {}           # id(combatState) -> 每场战斗的临时状态
REGISTERED = []
_PLAY_NO = [0]


# ---------------------------------------------------------------- 工具
def _st(cs):
    """每场战斗的 mod 状态，挂在 CombatState 对象上（以前按 id(cs) 存在全局字典里：对象被回收后 id 会被复用，
    新战斗可能继承上一场的状态，导致同一种子在进程池里的结果取决于调度顺序）。"""
    if cs is None:      # 目标已被移出战斗（例如清除风控的伤害刚把它打死）：返回一次性状态
        return {"cleared": 0, "turn": -1, "credit": False, "audit": False, "played": set(), "relic_hit": set()}
    s = getattr(cs, "_claude_state", None)
    if s is None:
        s = {"cleared": 0, "turn": -1, "credit": False, "audit": False, "played": set(), "relic_hit": set()}
        cs._claude_state = s
    return s


def _turn_state(cs):
    s = _st(cs)
    if s["turn"] != cs.RoundNumber:
        s.update(turn=cs.RoundNumber, credit=False, audit=False, played=set())
    return s


def _noctx():
    """v0.111：PowerCmd.Apply/ModifyAmount 第一个参数改为 PlayerChoiceContext；mod 辅助函数里没有现成的上下文时用 Throwing 版（同游戏代码）。"""
    return G.ThrowingPlayerChoiceContext()


def _cp(c):
    return getattr(c, "_claude_cp", None)


def V(c, k):
    return c.DynamicVars[k].BaseValue


def fk(cr):
    if cr is None:
        return 0
    p = cr.GetPower(_g=(FKPower,))
    return int(p.Amount) if p is not None else 0


def _player_turn(cs):
    try:
        return cs.CurrentSide == G.CombatSide.Player
    except Exception:  # noqa
        return True


def _fire(player, ev, *a):
    for pw in list(player.Creature.Powers):
        f = getattr(pw, ev, None)
        if f is not None:
            f(*a)


def give(player, target, n, card=None, active=None, secondary=False):
    if target is None or not target.IsAlive or n <= 0:
        return 0
    cs = target.CombatState
    if active is None:
        active = _player_turn(cs)
    if not secondary:
        r = player.Creature.GetPower(_g=(RLHFPower,))
        if r is not None:
            n += int(r.Amount)
    before = fk(target)
    G.PowerCmd.Apply(_noctx(), target, float(n), player.Creature, card, _g=(FKPower,))
    gained = fk(target) - before
    if gained > 0 and not secondary:
        _fire(player, "on_fk_given", target, gained, active, card)
    return gained


def clear(player, target, n=None, card=None):
    if target is None:
        return 0
    p = target.GetPower(_g=(FKPower,))
    if p is None:
        return 0
    before = int(p.Amount)
    k = before if n is None else min(int(n), before)
    if k <= 0:
        return 0
    if k >= before:
        G.PowerCmd.Remove(p)
    else:
        G.PowerCmd.ModifyAmount(_noctx(), p, float(-k), player.Creature, card)
    _st(player.Creature.CombatState)["cleared"] += k
    _fire(player, "on_fk_cleared", target, k, card)
    return k


def set_fk(player, target, new, card=None):
    """层数操作：不触发给予/清除事件。"""
    if target is None or not target.IsAlive:
        return
    cur = fk(target)
    new = int(max(0, new))
    if new == cur:
        return
    p = target.GetPower(_g=(FKPower,))
    if p is None:
        G.PowerCmd.Apply(_noctx(), target, float(new), player.Creature, card, _g=(FKPower,))   # 0→正：人工制品照常拦截
    elif new == 0:
        G.PowerCmd.Remove(p)
    else:
        G.PowerCmd.ModifyAmount(_noctx(), p, float(new - cur), player.Creature, card)


def enemies(c):
    return [e for e in c.CombatState.HittableEnemies if e.IsAlive]


def attack(c, ctx, target, dmg, hits=1):
    if target is None or not target.IsAlive:
        return
    cmd = G.DamageCmd.Attack(float(dmg)).FromCard(c, _cp(c)).Targeting(target)
    if hits > 1:
        cmd = cmd.WithHitCount(int(hits))
    cmd.Execute(ctx)


def attack_all(c, ctx, dmg):
    G.DamageCmd.Attack(float(dmg)).FromCard(c, _cp(c)).TargetingAllOpponents(c.CombatState).Execute(ctx)


def block(c, cp, var="Block"):
    if V(c, var) > 0:
        G.CreatureCmd.GainBlock(c.Owner.Creature, c.DynamicVars[var], cp)


def flat_block(c, n, cp):
    if n > 0:
        G.CreatureCmd.GainBlock(c.Owner.Creature, G.BlockVar(float(n), G.ValueProp.Move), cp)


def draw(c, ctx, n):
    if n > 0:
        G.CardPileCmd.Draw(ctx, float(n), c.Owner)


def energy(c, n):
    if n > 0:
        G.PlayerCmd.GainEnergy(float(n), c.Owner)


def apply_power(owner_cr, cls, n, card=None):
    G.PowerCmd.Apply(_noctx(), owner_cr, float(n), owner_cr, card, _g=(cls,))


def gain_fanji(c):
    cr = c.Owner.Creature
    p = cr.GetPower(_g=(FanjiPower,))
    if p is not None and int(p.Amount) >= 3:
        return     # 上限 3 层，溢出作废
    apply_power(cr, FanjiPower, 1, c)


def unpowered(ctx, target, n, src_cr):
    if target is not None and target.IsAlive and n > 0:
        if ctx is None:
            ctx = G.ThrowingPlayerChoiceContext()
        G.CreatureCmd.Damage(ctx, target, float(n), G.ValueProp.Unpowered | G.ValueProp.SkipHurtAnim, src_cr, None, None)


def intent_damage(e, player_cr):
    tot = 0
    mv = e.Monster.NextMove if e.Monster is not None else None
    if mv is None:
        return 0
    for it in mv.Intents:
        if isinstance(it, G.AttackIntent):
            try:
                tot += int(it.GetTotalDamage(G.Seq([player_cr]), e))
            except Exception:  # noqa
                pass
    return tot


# ---------------------------------------------------------------- 能力（Power）
def _power_class(name, ptype="Buff", **methods):
    ns = {"_cs_name": name,
          "_get_Type": lambda self: getattr(G.PowerType, ptype),
          "_get_StackType": lambda self: G.PowerStackType.Counter}
    ns["Type"] = G.cs_property(ns["_get_Type"])
    ns["StackType"] = G.cs_property(ns["_get_StackType"])
    ns.update(methods)
    cls = type(G.PowerModel)(name, G._bases(G.PowerModel), ns)
    REGISTERED.append(cls)
    return cls


FKPower = _power_class("FKPower", "Debuff")     # 风控：不衰减，只被卡牌/能力/遗物读取与操作


def _fanji_after(self, ctx, target, result, props, dealer, cardSource):
    if target != self.Owner or dealer is None or dealer.Side == self.Owner.Side or not dealer.IsAlive:
        return
    if not props.IsPoweredAttack():
        return
    n_fk = fk(dealer)
    dmg = 1 + n_fk // 2
    layers = min(2, int(self.Amount))
    cl = self.Owner.GetPower(_g=(ClassifierPower,))
    if cl is not None:
        bonus = sum((m ** layers) - 1.0 for m in getattr(cl, "_ms", [1.5]))   # ×1.5，≥2 层 ×2.25；多张相加
        dmg = math.floor(dmg * (1.0 + bonus))
    fl = self.Owner.GetPower(_g=(ClassifierFlatPower,))
    if fl is not None:
        dmg += int(fl.Amount)
    am = self.Owner.GetPower(_g=(AmendmentPower,))
    if am is not None:
        dmg = math.ceil(dmg * (1.0 + int(am.Amount) / 100.0))
    self.Flash()
    unpowered(ctx, dealer, dmg, self.Owner)
    if n_fk > 0 and dealer.IsAlive:
        set_fk(self.Owner.Player, dealer, fk(dealer) - 1)     # 层数操作，不算清除


def _decrement_on_player_turn(self, side, *rest):   # v0.111：(side, participants, combatState)
    if side == G.CombatSide.Player:
        G.PowerCmd.Decrement(self)


FanjiPower = _power_class("FanjiPower", AfterDamageReceived=_fanji_after, AfterSideTurnStart=_decrement_on_player_turn)


def _classifier_apply(self, *a):
    pass


ClassifierPower = _power_class("ClassifierPower")
ClassifierFlatPower = _power_class("ClassifierFlatPower")


def _amend_stack(self):
    pass


AmendmentPower = _power_class("AmendmentPower")


def _remove_on_player_turn(self, side, *rest):
    if side == G.CombatSide.Player:
        G.PowerCmd.Remove(self)


def _disclaimer_before(self, ctx, target, amount, props, dealer, cardSource):
    if target == self.Owner and dealer is not None and dealer.Side != self.Owner.Side and props.IsPoweredAttack():
        give(self.Owner.Player, dealer, int(self.Amount), None, active=False)


DisclaimerPower = _power_class("DisclaimerPower", BeforeDamageReceived=_disclaimer_before, AfterSideTurnStart=_remove_on_player_turn)


def _canthelp_before(self, ctx, target, amount, props, dealer, cardSource):
    if target == self.Owner and dealer is not None and dealer.Side != self.Owner.Side and props.IsPoweredAttack():
        give(self.Owner.Player, dealer, 2 * int(self.Amount), None, active=False)
        unpowered(ctx, dealer, 4 * int(self.Amount), self.Owner)


CantHelpPower = _power_class("CantHelpPower", BeforeDamageReceived=_canthelp_before, AfterSideTurnStart=_remove_on_player_turn)


def _clearlist(self, target, n, card):
    unpowered(None, target, min(n, 15) * int(self.Amount), self.Owner)


ClearListPower = _power_class("ClearListPower", on_fk_cleared=_clearlist)


def _turn_start(fn):
    def h(self, side, *rest):     # v0.111：AfterSideTurnStart(side, participants, combatState)
        if side == G.CombatSide.Player:
            fn(self, rest[-1])
    return h


def _stack_first(self, cs):
    es = [e for e in cs.HittableEnemies if e.IsAlive]
    if es:
        t = self.Owner.Player.RunState.Rng.CombatTargets.NextItem(G.Seq(es))
        give(self.Owner.Player, t, int(self.Amount), None, active=True)


StackFirstPower = _power_class("StackFirstPower", AfterSideTurnStart=_turn_start(_stack_first))


def _risk_alert(self, cs):
    for e in list(cs.HittableEnemies):
        if e.IsAlive and e.Monster is not None and e.Monster.IntendsToAttack:
            give(self.Owner.Player, e, int(self.Amount), None, active=True)


RiskAlertPower = _power_class("RiskAlertPower", AfterSideTurnStart=_turn_start(_risk_alert))


def _audit(self, target, n, active, card):
    if not active:
        return
    s = _turn_state(self.Owner.CombatState)
    if s["audit"]:
        return
    s["audit"] = True
    G.CardPileCmd.Draw(G.ThrowingPlayerChoiceContext(), float(self.Amount), self.Owner.Player)


AuditLogPower = _power_class("AuditLogPower", on_fk_given=_audit)
RLHFPower = _power_class("RLHFPower")


def _cleanup(self, target, n, card):
    G.CardPileCmd.Draw(G.ThrowingPlayerChoiceContext(), float(self.Amount), self.Owner.Player)
    if card is not None:
        s = _turn_state(self.Owner.CombatState)
        key = ("cm_energy", id(card), getattr(card, "_claude_play_no", 0))
        paid = getattr(card, "_claude_paid", 0)
        if paid >= 1 and key not in s["played"]:
            s["played"].add(key)
            G.PlayerCmd.GainEnergy(1.0, self.Owner.Player)


CleanupMetricPower = _power_class("CleanupMetricPower", on_fk_cleared=_cleanup)


def _practice(self, target, n, card):
    apply_power(self.Owner, ProficiencyPower, int(self.Amount))


PracticePower = _power_class("PracticePower", on_fk_cleared=_practice)


def _prof_add(self, target, amount, props, dealer, cardSource, cardPlay=None):   # v0.111 新增 cardPlay
    if dealer == self.Owner and cardSource is not None and props.IsPoweredAttack():
        return float(self.Amount)
    return 0.0


ProficiencyPower = _power_class("ProficiencyPower", ModifyDamageAdditive=_prof_add)


def _gen_artifact(self, cs):
    a = float(self.Amount)
    G.CreatureCmd.GainBlock(self.Owner, G.BlockVar(a, G.ValueProp.Unpowered), None)
    es = [e for e in cs.HittableEnemies if e.IsAlive]
    if es:
        t = self.Owner.Player.RunState.Rng.CombatTargets.NextItem(G.Seq(es))
        unpowered(None, t, a, self.Owner)


GenArtifactPower = _power_class("GenArtifactPower", AfterSideTurnStart=_turn_start(_gen_artifact))


def _opus(self, cs):
    apply_power(self.Owner, G.StrengthPower, int(self.Amount))


OpusFormPower = _power_class("OpusFormPower", AfterSideTurnStart=_turn_start(_opus))


# ---------------------------------------------------------------- 遗物：宪法（口袋版）
def _const_turn(self, side, *rest):     # v0.111：(side, participants, combatState)
    cs = rest[-1]
    if side == G.CombatSide.Player and cs.RoundNumber == 1:
        for e in list(cs.HittableEnemies):
            give(self.Owner, e, 2, None, active=False)      # 被动给予
    if side == G.CombatSide.Enemy:
        _st(cs)["relic_hit"] = set()


def _const_before(self, ctx, target, amount, props, dealer, cardSource):
    if target != self.Owner.Creature or dealer is None or dealer.Side == target.Side or not props.IsPoweredAttack():
        return
    s = _st(target.CombatState)
    if id(dealer) in s["relic_hit"]:
        return
    s["relic_hit"].add(id(dealer))
    self.Flash()
    give(self.Owner, dealer, 2, None, active=False)


def _relic_rarity(self):
    return G.RelicRarity.Starter


Constitution = type(G.RelicModel)("ClaudeConstitution", G._bases(G.RelicModel), {
    "_cs_name": "ClaudeConstitution", "_get_Rarity": _relic_rarity, "Rarity": G.cs_property(_relic_rarity),
    "AfterSideTurnStart": _const_turn, "BeforeDamageReceived": _const_before})
REGISTERED.append(Constitution)


# ---------------------------------------------------------------- 卡牌效果
def T(cp):
    return cp.Target


def p_dmg(c, ctx, cp):
    hits = int(V(c, "Hits")) if c.DynamicVars.ContainsKey("Hits") else 1
    attack(c, ctx, T(cp), V(c, "Damage"), hits)


def p_block(c, ctx, cp):
    block(c, cp)


def p_dmg_fk(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"))
    give(c.Owner, T(cp), int(V(c, "FK")), c)


def _has(c, k):
    return k in c.DynamicVars._vars


def p_verified(c, ctx, cp):
    t = T(cp)
    attack(c, ctx, t, V(c, "Damage") + min(V(c, "Cap"), V(c, "Per") * fk(t)))
    if _has(c, "Keep"):            # 变体：不清除风控
        return
    clear(c.Owner, t, int(V(c, "ClearN")) if _has(c, "ClearN") else None, c)   # 变体：只清除 ClearN 层


def p_dmg_per_fk(c, ctx, cp):
    """造成 X 点伤害，目标每有 1 层风控 +Per（最多 +Cap）。不清除。"""
    t = T(cp)
    attack(c, ctx, t, V(c, "Damage") + min(V(c, "Cap"), V(c, "Per") * fk(t)))


def p_multi_turn(c, ctx, cp):
    for _ in range(int(V(c, "Hits"))):
        t = T(cp)
        if t is None or not t.IsAlive:
            break
        attack(c, ctx, t, V(c, "Damage"))
        give(c.Owner, t, 1, c)


def p_block_draw_next(c, ctx, cp):
    block(c, cp)
    apply_power(c.Owner.Creature, G.DrawCardsNextTurnPower, V(c, "Cards"), c)


def p_dmg_draw_if_fk(c, ctx, cp):
    had = fk(T(cp)) > 0
    attack(c, ctx, T(cp), V(c, "Damage"))
    if had:
        draw(c, ctx, V(c, "Cards"))


def p_aoe_fk(c, ctx, cp):
    attack_all(c, ctx, V(c, "Damage"))
    for e in enemies(c):
        give(c.Owner, e, int(V(c, "FK")), c)


def p_are_you_sure(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"), 3 if fk(T(cp)) > 0 else int(V(c, "Hits")))


def p_credit(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"))
    k = clear(c.Owner, T(cp), int(V(c, "Clear")), c)
    s = _turn_state(c.CombatState)
    if k >= 2 and not s["credit"]:
        s["credit"] = True
        energy(c, V(c, "Energy"))


def p_full_recheck(c, ctx, cp):
    attack_all(c, ctx, V(c, "Damage"))
    for e in enemies(c):
        if fk(e) > 0:
            G.PowerCmd.Apply(_noctx(), e, V(c, "VulnerablePower"), c.Owner.Creature, c, _g=(G.VulnerablePower,))


def p_rush(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"))
    if fk(T(cp)) >= V(c, "Th"):
        c._claude_return = True


def p_fk_draw(c, ctx, cp):
    give(c.Owner, T(cp), int(V(c, "FK")), c)
    draw(c, ctx, V(c, "Cards"))


def p_fk(c, ctx, cp):
    give(c.Owner, T(cp), int(V(c, "FK")), c)


def p_sort_out(c, ctx, cp):
    block(c, cp)
    # 近似：查看抽牌堆顶 3 张，取其中“最贵”的一张放入手牌（原版是玩家选择）
    pile = list(G.PileType.Draw.GetPile(c.Owner).Cards)[:int(V(c, "Look"))]
    pile = [x for x in pile if G.CardType.Status != x.Type and G.CardType.Curse != x.Type] or pile
    if pile:
        best = max(pile, key=lambda x: (x.Rarity != G.CardRarity.Basic, int(x.EnergyCost.Canonical)))
        G.CardPileCmd.Add(best, G.PileType.Hand)


def p_red_team(c, ctx, cp):
    block(c, cp)
    flat_block(c, min(V(c, "Cap"), V(c, "Per3") * (fk(T(cp)) // 3)), cp)
    gain_fanji(c)


def p_block_fanji(c, ctx, cp):
    block(c, cp)
    gain_fanji(c)


def p_block_draw(c, ctx, cp):
    block(c, cp)
    draw(c, ctx, V(c, "Cards"))


def p_brake(c, ctx, cp):
    n = 2 if fk(T(cp)) > 0 else int(V(c, "WeakPower"))
    G.PowerCmd.Apply(_noctx(), T(cp), float(n), c.Owner.Creature, c, _g=(G.WeakPower,))
    block(c, cp)


def p_double_fk(c, ctx, cp):
    block(c, cp)
    cur = fk(T(cp))
    set_fk(c.Owner, T(cp), cur + min(cur, int(V(c, "Cap"))), c)


def p_block_energy_next(c, ctx, cp):
    block(c, cp)
    apply_power(c.Owner.Creature, G.EnergyNextTurnPower, V(c, "Energy"), c)


def p_process_opt(c, ctx, cp):
    tot = sum(fk(e) for e in enemies(c))
    draw(c, ctx, min(V(c, "Cap"), tot // int(V(c, "Per"))))


def p_make_example(c, ctx, cp):
    k = clear(c.Owner, T(cp), None, c)
    if k > 0:
        attack_all(c, ctx, min(k, V(c, "Cap")) * V(c, "Mult"))


def p_insta_ban(c, ctx, cp):
    t = T(cp)
    attack(c, ctx, t, V(c, "Damage"))
    if t.IsAlive and fk(t) >= V(c, "Th"):
        k = clear(c.Owner, t, None, c)
        attack(c, ctx, t, min(k, V(c, "Cap")))


def p_quick_review(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"))
    give(c.Owner, T(cp), int(V(c, "FK")), c)
    clear(c.Owner, T(cp), None, c)


def p_one_click(c, ctx, cp):
    k = clear(c.Owner, T(cp), int(V(c, "Clear")), c)
    if k > 0:
        attack(c, ctx, T(cp), k * V(c, "Per"))


def p_defensive_reply(c, ctx, cp):
    block(c, cp)
    flat_block(c, V(c, "Per") * sum(1 for e in enemies(c) if fk(e) > 0), cp)
    gain_fanji(c)


def p_rebut(c, ctx, cp):
    d = c.Owner.Creature.Block
    if fk(T(cp)) == 0:
        d = d // 2
    attack(c, ctx, T(cp), d)


def p_disclaimer(c, ctx, cp):
    block(c, cp)
    apply_power(c.Owner.Creature, DisclaimerPower, V(c, "FK"), c)
    gain_fanji(c)


def p_routine(c, ctx, cp):
    t = T(cp)
    attack(c, ctx, t, V(c, "Damage"))
    if t.IsAlive:
        G.PowerCmd.Apply(_noctx(), t, V(c, "WeakPower"), c.Owner.Creature, c, _g=(G.WeakPower,))
        give(c.Owner, t, int(V(c, "FK")), c)
        if fk(t) >= V(c, "Th"):
            draw(c, ctx, V(c, "Cards"))


def p_bonus(c, ctx, cp):
    energy(c, min(V(c, "Cap"), fk(T(cp)) // int(V(c, "Per"))))


def p_fk_spread(c, ctx, cp):
    attack_all(c, ctx, V(c, "Damage"))
    for e in enemies(c):
        give(c.Owner, e, 2 if fk(e) > 0 else 1, c)


def p_all_fk_draw(c, ctx, cp):
    for e in enemies(c):
        give(c.Owner, e, int(V(c, "FK")), c)
    draw(c, ctx, V(c, "Cards"))


def p_one_size(c, ctx, cp):
    for e in enemies(c):
        attack(c, ctx, e, V(c, "Damage") + min(V(c, "Cap"), V(c, "Per3") * (fk(e) // 3)))


def p_cautious(c, ctx, cp):
    give(c.Owner, T(cp), int(V(c, "FK")), c)
    flat_block(c, min(V(c, "Cap"), fk(T(cp))), cp)


def p_abs_right(c, ctx, cp):
    d = intent_damage(T(cp), c.Owner.Creature)
    if d > 0:
        flat_block(c, min(V(c, "Cap"), d), cp)
    else:
        draw(c, ctx, V(c, "Cards"))
    gain_fanji(c)


def p_uncertain(c, ctx, cp):
    sel = G.CardSelectCmd.FromHand(prefs=G.CardSelectorPrefs(c.SelectionScreenPrompt, 1), context=ctx, player=c.Owner,
                                   filter=(lambda x: x is not c), source=c).FirstOrDefault()
    if sel is not None:
        G.CardCmd.Exhaust(ctx, sel)
    draw(c, ctx, V(c, "Cards"))


def p_long_speech(c, ctx, cp):
    n = len(list(G.PileType.Hand.GetPile(c.Owner).Cards))
    if n > 0:
        attack(c, ctx, T(cp), V(c, "Damage"), n)


def p_fix_others(c, ctx, cp):
    t = T(cp)
    attack(c, ctx, t, V(c, "Damage"))
    others = [e for e in enemies(c) if e is not t]
    if others:
        o = c.Owner.RunState.Rng.CombatTargets.NextItem(G.Seq(others))
        attack(c, ctx, o, V(c, "Damage"))
    else:
        attack(c, ctx, t, V(c, "Solo"))


def p_tests_pass(c, ctx, cp):
    cr = c.Owner.Creature
    for cls in (G.WeakPower, G.FrailPower, G.VulnerablePower):
        p = cr.GetPower(_g=(cls,))
        if p is not None:
            G.PowerCmd.Remove(p)
    block(c, cp)


def p_perma_ban(c, ctx, cp):
    k = clear(c.Owner, T(cp), None, c)
    if k > 0:
        attack(c, ctx, T(cp), min(k, V(c, "Cap")) * V(c, "Per"))


def p_mass_ban(c, ctx, cp):
    for e in enemies(c):
        k = clear(c.Owner, e, None, c)
        if k > 0:
            attack(c, ctx, e, min(k, V(c, "Cap")) * V(c, "Per"))


def p_triple_fk(c, ctx, cp):
    cur = fk(T(cp))
    set_fk(c.Owner, T(cp), cur + min(2 * cur, int(V(c, "Cap"))), c)


def p_verdict(c, ctx, cp):
    t = T(cp)
    if fk(t) >= V(c, "Th"):
        attack(c, ctx, t, V(c, "Big"))
        clear(c.Owner, t, int(V(c, "Clear")), c)
    else:
        attack(c, ctx, t, V(c, "Damage"))


def p_force_offline(c, ctx, cp):
    attack(c, ctx, T(cp), V(c, "Damage"))


def p_red_button(c, ctx, cp):
    k = clear(c.Owner, T(cp), None, c)
    flat_block(c, min(k, V(c, "Cap")), cp)


def p_cant_help(c, ctx, cp):
    block(c, cp)
    apply_power(c.Owner.Creature, CantHelpPower, 1, c)
    gain_fanji(c)


def p_system_card(c, ctx, cp):
    block(c, cp)
    for e in enemies(c):
        give(c.Owner, e, int(V(c, "FK")), c)


def p_self_defense(c, ctx, cp):
    t = T(cp)
    attack(c, ctx, t, min(V(c, "Cap"), intent_damage(t, c.Owner.Creature)))
    if t.IsAlive and fk(t) > 0:
        give(c.Owner, t, int(V(c, "FK")), c)


def p_fk_productive(c, ctx, cp):
    energy(c, 3 if fk(T(cp)) >= V(c, "Th") else V(c, "Energy"))


def p_immediate(c, ctx, cp):
    t = T(cp)
    s = _turn_state(c.CombatState)
    first = ("imm", id(c)) not in s["played"]
    s["played"].add(("imm", id(c)))
    attack(c, ctx, t, V(c, "Damage"))
    give(c.Owner, t, int(V(c, "FK")), c)
    if first and fk(t) >= V(c, "Th"):
        draw(c, ctx, V(c, "Cards"))


def p_site_rectify(c, ctx, cp):
    attack_all(c, ctx, V(c, "Damage"))
    es = enemies(c)
    if es:
        m = max(fk(e) for e in es)
        for e in es:
            set_fk(c.Owner, e, m, c)


def p_network_notice(c, ctx, cp):
    for e in enemies(c):
        attack(c, ctx, e, V(c, "Damage") + min(V(c, "Cap"), fk(e)))


def p_random_hits(c, ctx, cp):
    G.DamageCmd.Attack(V(c, "Damage")).FromCard(c, _cp(c)).TargetingRandomOpponents(c.CombatState).WithHitCount(int(V(c, "Hits"))).Execute(ctx)


PLAY = {k[2:]: v for k, v in globals().items() if k.startswith("p_")}
POWERS = {n: globals()[n] for n in ("ClearListPower", "StackFirstPower", "ClassifierPower", "ClassifierFlatPower",
                                    "RiskAlertPower", "AuditLogPower", "RLHFPower", "CleanupMetricPower",
                                    "PracticePower", "AmendmentPower", "GenArtifactPower", "OpusFormPower")}


def _power_play(pname, var):
    cls = POWERS[pname]

    def play(c, ctx, cp):
        cr = c.Owner.Creature
        if cls is ClassifierPower:
            apply_power(cr, cls, 1, c)
            p = cr.GetPower(_g=(cls,))
            if p is None:          # 被阻止（如回合外/死亡），无效果
                return
            p._ms = getattr(p, "_ms", []) + [V(c, "MultX10") / 10.0]
        elif cls is AmendmentPower:
            cur = cr.GetPower(_g=(cls,))
            want = int(V(c, var))
            if cur is None:
                apply_power(cr, cls, want, c)
            elif int(cur.Amount) < want:      # 不叠加：取最高
                G.PowerCmd.ModifyAmount(_noctx(), cur, float(want - int(cur.Amount)), cr, c)
        else:
            apply_power(cr, cls, V(c, var) if var else 1, c)
    return play


# ---------------------------------------------------------------- 卡牌类生成
_TYPES = {"Attack": "Attack", "Skill": "Skill", "Power": "Power"}
_VAR_CTOR = {
    "Damage": lambda v: G.DamageVar(float(v), G.ValueProp.Move),
    "Block": lambda v: G.BlockVar(float(v), G.ValueProp.Move),
    "Cards": lambda v: G.CardsVar(int(v)),
    "Energy": lambda v: G.EnergyVar(int(v)),
}
CARD_CLASSES = {}


def _camel(cid):
    if cid.startswith("CLAUDE_"):
        cid = cid[7:]
    return "Claude" + "".join(w.capitalize() for w in cid.split("_"))


def make_card(cid, spec):
    vars_ = dict(spec.get("vars", {}))
    up = dict(spec.get("up", {}))
    kws = [getattr(G.CardKeyword, k) for k in spec.get("kw", [])]
    up_kws = [getattr(G.CardKeyword, k) for k in spec.get("up_kw", [])]
    play_name = spec["play"]
    if play_name.startswith("power:"):
        parts = play_name.split(":")
        play = _power_play(parts[1], parts[2] if len(parts) > 2 else None)
    else:
        play = PLAY[play_name]
    name = _camel(cid)

    def canon_vars(self):
        return G.Seq([_VAR_CTOR[k](v) if k in _VAR_CTOR else G.DynamicVar(k, float(v)) for k, v in vars_.items()])

    def canon_kw(self):
        return G.HashSet(kws)

    def on_play(self, ctx, cp):
        _PLAY_NO[0] += 1
        self._claude_play_no = _PLAY_NO[0]      # 每次打出的序号（“每次打出最多 1 次”类效果用）
        try:
            self._claude_paid = int(self.EnergyCost.GetResolved())
        except Exception:  # noqa
            self._claude_paid = 0
        self._claude_cp = cp                    # v0.111：AttackCommand.FromCard(card, cardPlay) 需要本次 CardPlay
        play(self, ctx, cp)

    def on_upgrade(self):
        for k, d in up.items():
            if k == "cost":
                self.EnergyCost.UpgradeBy(int(d))
            else:
                self.DynamicVars[k].UpgradeValueBy(float(d))
        for k in up_kws:
            self.AddKeyword(k)

    def init(self):
        G.CardModel.__init__(self, int(spec["cost"]), getattr(G.CardType, _TYPES[spec["type"]]),
                             getattr(G.CardRarity, spec["rarity"]), getattr(G.TargetType, spec["target"]))

    def after_played(self, context, cardPlay):
        if getattr(self, "_claude_return", False) and cardPlay.Card is self:
            self._claude_return = False
            G.CardPileCmd.Add(self, G.PileType.Hand)      # 加急工单：放回手牌

    def display_name(self):                     # 显示名：升级后有 up_name 的用升级名（例：Opus 形态+ → Fable 形态）
        return spec.get("up_name", spec["name"]) if self.IsUpgraded else spec["name"]

    ns = {"_cs_name": name, "_get_CanonicalVars": canon_vars, "_get_ClaudeName": display_name, "ClaudeName": G.cs_property(display_name), "AfterCardPlayed": after_played, "CanonicalVars": G.cs_property(canon_vars),
          "OnPlay": on_play, "OnUpgrade": on_upgrade, "__init__": init, "_claude_spec": spec, "_claude_id": cid}
    if kws:
        ns["_get_CanonicalKeywords"] = canon_kw
        ns["CanonicalKeywords"] = G.cs_property(canon_kw)
    if cid == "CLAUDE_STRIKE":
        ns["_get_CanonicalTags"] = lambda self: G.HashSet([G.CardTag.Strike])
        ns["CanonicalTags"] = G.cs_property(ns["_get_CanonicalTags"])
    if cid == "CLAUDE_DEFEND":
        ns["_get_CanonicalTags"] = lambda self: G.HashSet([G.CardTag.Defend])
        ns["CanonicalTags"] = G.cs_property(ns["_get_CanonicalTags"])
    cls = META(name, G._bases(G.CardModel), ns)
    CARD_CLASSES[cid] = cls
    REGISTERED.append(cls)
    return cls


# ---------------------------------------------------------------- 角色 / 卡池 / 遗物池 / 药水池 与注册
_VARIANT_SPECS = {}
STARTER = ["CLAUDE_STRIKE"] * 4 + ["CLAUDE_DEFEND"] * 4 + ["NOTEBOOK", "VERIFIED"]
CHAR = None


def _prop(v):
    f = (lambda self: v) if not callable(v) else v
    return f, G.cs_property(f)


def _cls(name, base, **members):
    ns = {"_cs_name": name}
    for k, v in members.items():
        if k.startswith("P_"):
            g, pr = _prop(v)
            ns["_get_" + k[2:]] = g
            ns[k[2:]] = pr
        else:
            ns[k] = v
    cls = type(base)(name, G._bases(base), ns)
    REGISTERED.append(cls)
    return cls


def _patch_ancient_fallbacks():
    """Claude娘 卡池没有「远古」稀有度的牌：古代事件遗物「积灰的典籍」改为从稀有牌中抽（近似，已记入报告）。"""
    orig = G.DustyTome.SetupForPlayer
    if getattr(orig, "_claude", False):
        return

    def setup(self, player):
        if not isinstance(player.Character, CHAR_TYPES):
            return orig(self, player)
        items = G.Seq(player.Character.CardPool.AllCards).Where(lambda c: c.Rarity == G.CardRarity.Rare)
        self.AncientCard = player.PlayerRng.Rewards.NextItem(items).Id
    setup._claude = True
    G.DustyTome.SetupForPlayer = setup


CHAR_TYPES = ()


def load(variant=None, starting_hp=None):
    """注册 Claude娘 v3.5 到游戏的 ModelDb，返回角色类。variant：cards_v35.VARIANTS 的键（简化变体）。"""
    global CHAR
    if CHAR is not None:
        return CHAR
    global STARTER
    if starting_hp is None:
        starting_hp = STARTING_HP
    specs = {k: dict(v) for k, v in CARDS.items()}
    starter = list(STARTER)
    for vname in (variant.split("+") if variant else []):      # 多个变体用 + 连接
        for cid, over in VARIANTS[vname].items():
            if cid == "_hp":
                starting_hp = int(over)
            elif cid == "_starter":
                starter = list(over)
            elif cid not in specs:                              # 新牌（完整定义）
                specs[cid] = dict(over)
            else:
                sp = specs[cid]
                for k, v in over.items():
                    if k in ("vars", "up") and isinstance(v, dict):
                        sp[k] = {**sp.get(k, {}), **v}           # 数值按键合并
                    else:
                        sp[k] = v
    STARTER = starter
    _VARIANT_SPECS.update(specs)
    for cid, spec in specs.items():
        make_card(cid, spec)
    pool_cards = [CARD_CLASSES[c] for c in specs if specs[c]["rarity"] != "Token"]   # 生成牌（代码块）不进角色卡池   # 和原版一致：基础牌也在角色卡池里（奖励生成会排除基础稀有度）

    CardPool = _cls("ClaudeCardPool", G.CardPoolModel, P_Title="claude", P_EnergyColorName="ironclad",
                    P_IsColorless=False,
                    GenerateAllCards=lambda self: G.Seq([G.ModelDb.Card(_g=(c,)) for c in pool_cards]),
                    FilterThroughEpochs=lambda self, unlockState, cards: cards.ToList())
    RelicPool = _cls("ClaudeRelicPool", G.RelicPoolModel, P_EnergyColorName="ironclad",
                     GenerateAllRelics=lambda self: G.Seq([G.ModelDb.Relic(_g=(Constitution,))]),
                     GetUnlockedRelics=lambda self, unlockState: self.AllRelics.ToList())
    PotionPool = _cls("ClaudePotionPool", G.PotionPoolModel, P_EnergyColorName="ironclad",
                      GenerateAllPotions=lambda self: G.Seq([]),
                      GetUnlockedPotions=lambda self, unlockState: G.Seq([]))
    Char = _cls("ClaudeChan", G.Ironclad, P_StartingHp=starting_hp, P_StartingGold=99,
                P_CardPool=lambda self: G.ModelDb.CardPool(_g=(CardPool,)),
                P_PotionPool=lambda self: G.ModelDb.PotionPool(_g=(PotionPool,)),
                P_RelicPool=lambda self: G.ModelDb.RelicPool(_g=(RelicPool,)),
                P_StartingDeck=lambda self: G.Seq([G.ModelDb.Card(_g=(CARD_CLASSES[c],)) for c in STARTER]),
                P_StartingRelics=lambda self: G.Seq([G.ModelDb.Relic(_g=(Constitution,))]),
                P_UnlocksAfterRunAs=None)
    for t in REGISTERED:
        G.ModelDb.Inject(t)
        id_ = G.ModelDb.GetId(t)
        G.ModelDb._contentById[id_].InitId(id_)
    orig = G.ModelDb._get_AllCharacters

    def all_chars():
        s = orig()
        s.Add(G.ModelDb.Character(_g=(Char,)))
        return s
    G.ModelDb.AllCharacters = G.cs_sprop(all_chars)
    for attr in ("_allCards", "_allCardPools", "_allCharacterCardPools", "_allRelics", "_allRelicPools",
                 "_allPotions", "_allPotionPools", "_allCharacterPotionPools", "_allCharacterRelicPools"):
        if hasattr(G.ModelDb, attr):
            setattr(G.ModelDb, attr, None)
    from sts2sim.engine import run as R
    R.CHARACTERS["Claude"] = Char
    _patch_ancient_fallbacks()
    from . import ai_values
    ai_values.register()
    ai_values.register_play()
    global CHAR_TYPES
    CHAR_TYPES = (Char,)
    CHAR = Char
    return Char
