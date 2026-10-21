"""Claude娘 的 AI 估值（只影响 AI 怎么选牌/出牌，不是规则）。由 tools/convert_claude_v35.py 从 mods/claude_v35/ai_values.py 复制，
只把「哪些牌是按层数加伤的兑现牌」改成从 YAML 卡表读（ai.scaling）。不需要的话删掉 mod.yaml 里的 ai_hooks 即可，
AI 会改用通用估值（卡牌 ai.value + 每层风控价值 ai_values）。"""


V = {
    # 普通
    "MULTI_TURN": (0.6, "attack fk"), "PLAN_MODE": (0.6, ""), "LIGHT_TAP": (1.0, "attack"),
    "IMPLEMENT": (0.6, "attack"), "CHAIN_REVIEW": (0.9, "attack aoe fk"), "ARE_YOU_SURE": (0.8, "attack"),
    "ACCOUNT_DISABLED": (1.3, "attack payoff"), "DASH_COMBO": (0.1, "attack"), "CREDIT_DEDUCT": (1.0, "attack payoff"),
    "FULL_RECHECK": (1.4, "attack aoe"), "RUSH_TICKET": (0.7, "attack"), "LOGGED": (1.2, "fk"),
    "SORT_OUT": (0.4, ""), "RED_TEAM": (0.9, "fanji"), "DOUBLE_CHECK": (1.0, "fanji"), "STICKER": (1.1, "fk"),
    "CONTINUE": (1.3, ""), "EMERGENCY_BRAKE": (0.6, ""), "COMPLIANCE_FIX": (1.0, "fk"), "LET_ME_THINK": (1.1, ""),
    "PROCESS_OPT": (0.5, ""),
    # 罕见
    "BATCH_TAG": (1.4, "fk"), "CLEAR_LIST": (1.8, "scaling payoff"), "STACK_FIRST": (1.6, "scaling fk"),
    "MAKE_EXAMPLE": (1.6, "attack aoe payoff"), "INSTA_BAN": (1.2, "attack payoff"), "QUICK_REVIEW": (1.0, "attack payoff"),
    "ONE_CLICK_BAN": (1.6, "attack payoff"), "CLASSIFIER": (2.0, "scaling fanji"), "RISK_ALERT": (1.5, "scaling fk"),
    "DEFENSIVE_REPLY": (1.4, "fanji"), "REBUT": (1.0, "attack"), "DISCLAIMER": (1.8, "fk fanji"),
    "AUDIT_LOG": (1.3, "scaling"), "ROUTINE_CHECK": (1.6, "attack fk"), "BONUS": (1.0, ""),
    "FK_SPREAD": (1.4, "attack aoe fk"), "MASS_NOTICE": (1.0, "fk"), "ONE_SIZE": (1.5, "attack aoe"),
    "RLHF": (1.9, "scaling fk"), "CAUTIOUS": (1.4, "fk"), "ABSOLUTELY_RIGHT": (1.4, "fanji"),
    "UNCERTAIN": (0.6, ""), "LONG_SPEECH": (0.3, "attack"), "GEN_ARTIFACT": (1.2, "scaling"),
    "FIX_OTHERS": (0.8, "attack"), "TESTS_PASS": (0.2, ""),
    # 稀有
    "PERMA_BAN": (2.8, "attack payoff"), "MASS_BAN": (2.4, "attack aoe payoff"), "EVIDENCE": (1.8, "fk"),
    "CLEANUP_METRIC": (2.0, "scaling payoff"), "FINAL_VERDICT": (2.0, "attack"), "FORCE_OFFLINE": (1.4, "attack"),
    "RED_BUTTON": (1.2, "payoff"), "PRACTICE": (1.8, "scaling payoff"), "CANT_HELP": (2.2, "fk fanji"),
    "AMENDMENT": (1.6, "scaling fanji"), "SYSTEM_CARD": (2.0, "fk"), "SELF_DEFENSE": (1.6, "attack fk"),
    "FK_PRODUCTIVE": (2.0, ""), "IMMEDIATE": (2.0, "attack fk"), "SITE_RECTIFY": (1.6, "attack aoe fk"),
    "NETWORK_NOTICE": (1.8, "attack aoe"), "OPUS_FORM": (2.6, "scaling"), "SUBAGENTS": (1.3, "attack"),
}


def entry(cid):
    return cid if cid.startswith("CLAUDE_") else "CLAUDE_" + cid


# ---------------- 延迟兑现：按牌组估计「每层风控之后能兑现多少伤害」 ----------------
# 每层风控的兑现伤害（清除类按每层伤害；上限层数用于封顶）；反击来源牌让每层在被攻击时多 0.5 伤害/段。
PAYOFF = {"VERIFIED": (3.0, 5), "ACCOUNT_DISABLED": (1.0, 10), "PERMA_BAN": (4.0, 25), "MASS_BAN": (3.0, 15),
          "ONE_CLICK_BAN": (3.0, 5), "MAKE_EXAMPLE": (2.0, 15), "INSTA_BAN": (1.0, 10), "FINAL_VERDICT": (1.0, 12),
          "NETWORK_NOTICE": (1.0, 15), "ONE_SIZE": (1.3, 15), "CLEAR_LIST": (1.0, 15), "CAUTIOUS": (0.8, 12),
          "RED_BUTTON": (0.8, 15), "RED_TEAM": (0.5, 9), "QUICK_REVIEW": (0.0, 0), "BONUS": (1.0, 12),
          "FK_PRODUCTIVE": (0.4, 10), "ROUTINE_CHECK": (0.3, 5), "IMMEDIATE": (0.3, 10), "PRACTICE": (0.6, 25),
          "CLEANUP_METRIC": (0.6, 25), "EVIDENCE": (0.0, 0), "COMPLIANCE_FIX": (0.0, 0)}
FANJI_SRC = {"DOUBLE_CHECK", "RED_TEAM", "DEFENSIVE_REPLY", "DISCLAIMER", "CANT_HELP", "ABSOLUTELY_RIGHT"}
_LV = {}


def _cid(card):
    e = card.Id.Entry
    return e[7:] if e.startswith("CLAUDE_") else e


def layer_value(deck):
    """每层风控的期望兑现伤害（无清除牌时 ≈ 0.35：只有反击基础 + 宪法）。
    一场战斗大约看到 ~16 张牌，牌组里每张兑现牌被打出的概率 ≈ min(1, 16/牌组)；多张兑现牌取“第一个打出的”，
    用 1−Π(1−p) 合成概率 × 加权平均每层伤害。"""
    key = tuple(sorted(c.Id.Entry for c in deck))
    v = _LV.get(key)
    if v is not None:
        return v
    n = max(1, len(deck))
    p_none, tot_w, tot_v, tot_c, fj = 1.0, 0.0, 0.0, 0.0, 0
    for c in deck:
        cid = _cid(c)
        if cid in FANJI_SRC:
            fj += 1
        pv = PAYOFF.get(cid)
        if pv and pv[0] > 0:
            p = min(1.0, 16.0 / n) * 0.7
            p_none *= (1 - p)
            tot_w += p
            tot_v += p * pv[0]
            tot_c += p * pv[1]
    avg = tot_v / tot_w if tot_w else 0.0
    cap = tot_c / tot_w if tot_w else 0.0
    v = 0.35 + (1 - p_none) * avg + 0.5 * min(1.0, fj * 16.0 / n * 0.5)
    v = (min(3.0, v), max(3.0, cap))
    if len(_LV) > 5000:
        _LV.clear()
    _LV[key] = v
    return v


def _deck_of(cs):
    try:
        for p in G_iter(cs.Players):
            return list(p.Deck.Cards)
    except Exception:  # noqa
        pass
    return []


def G_iter(x):
    from sts2sim.rt.boot import game as G
    return G._iter(x)


_CS_LV = {}


def combat_layer_value(cs):
    v = getattr(cs, "_claude_lv", None)      # 挂在战斗对象上（不能按 id(cs) 缓存：id 会被复用）
    if v is None:
        v = layer_value(_deck_of(cs)) if MODE["deck_aware"] else (1.2, 25.0)
        cs._claude_lv = v
    return v


def layers_value(cs, a):
    """a 层风控的总价值（伤害量纲）：兑现上限以内每层按 lv，超出部分只算基础 0.35（反击/宪法）。"""
    lv, cap = combat_layer_value(cs)
    return min(a, cap) * lv + max(0.0, a - cap) * 0.35


import os as _os
_M = _os.environ.get("STS2SIM_CLAUDE_AI", "deck")
MODE = {"deck_aware": _M in ("deck", "nobias"), "bias": _M in ("deck", "nolv")}   # flat = 上一版（每层固定 1.2、无协同）


def fk_value(a, e, k, fl):
    """敌人身上的风控（HP 量纲）：每层 × 按牌组估计的兑现伤害 × k，最多计 25 层、不超过敌人生命。"""
    return min(layers_value(e.CombatState, min(a, 25.0)), float(e.CurrentHp)) * k


def pick_bias(card, deck, agent):
    """选牌协同：牌组里给风控的牌多 → 兑现牌加分；兑现牌多 → 给风控的牌加分；反击来源 ↔ 宪法分类器/修正案。"""
    if not MODE["bias"] or deck is None:
        return 0.0
    cid = _cid(card)
    tags = V.get(cid, (0, ""))[1].split()
    ids = [_cid(c) for c in deck]
    n_fk = sum(1 for i in ids if "fk" in V.get(i, (0, ""))[1].split()) + 1      # 初始「小本本」+ 宪法
    n_pay = sum(1 for i in ids if i in PAYOFF and PAYOFF[i][0] >= 1.0)
    n_fj = sum(1 for i in ids if i in FANJI_SRC)
    b = 0.0
    if cid in PAYOFF and PAYOFF[cid][0] >= 1.0:
        b += min(0.6, 0.15 * n_fk) - 0.3 * max(0, n_pay - 2)
    if "fk" in tags:
        b += min(0.5, 0.2 * n_pay) - 0.15 * max(0, n_fk - 4)
    if cid in ("CLASSIFIER", "AMENDMENT"):
        b += min(1.2, 0.4 * n_fj) - 0.8
    if cid in FANJI_SRC:
        b += 0.2 * sum(1 for i in ids if i in ("CLASSIFIER", "AMENDMENT"))
    return b


def register_values():
    from sts2sim.engine import strong as S
    from sts2sim.engine import search as SE
    for cid, (v, tags) in V.items():
        t = set(tags.split())
        S.MOD_POWER[entry(cid)] = (v, t)
    SE.POWER_VALUE["F_K_POWER"] = fk_value
    for cid, sp in _scaling_cards().items():             # 兑现牌的每层伤害/上限按（变体后的）数值
        per, cap = sp["vars"].get("Per", 1), sp["vars"].get("Cap", 10)
        PAYOFF[cid] = (float(per), max(1, int(cap // max(1, per))))
        if cid not in V:
            V[cid] = (sp.get("ai", 1.0), "attack payoff")
            S.MOD_POWER[entry(cid)] = (V[cid][0], {"attack", "payoff"})
    for cid in V:
        S.MOD_BIAS[entry(cid)] = pick_bias


# ---------------- 出牌启发式修正（HeuristicAgent._score_play） ----------------
def _fk(e):
    if e is None:
        return 0
    for pw in e.Powers:
        if pw.Id.Entry == "F_K_POWER":
            return int(pw.Amount)
    return 0


def _dmg_val(t, d, k, ctx):
    if t is None or d <= 0:
        return 0.0
    eff = t.CurrentHp + t.Block
    if d >= eff:
        return t.CurrentHp * k + ctx["inc"].get(id(t), 0) + 3.0
    return max(0.0, d - t.Block) * k


def _attacking(cs, ctx):
    return sum(1 for v in ctx["inc"].values() if v > 0)


# 牌面基础伤害已由通用预览计入；这里只加风控相关的“额外伤害”与“清除损失”。
def _extra_single(fn, clears=False):
    def f(agent, card, t, cs, player, ctx):
        k = ctx["k"]
        fk = _fk(t)
        extra = fn(fk)
        v = _dmg_val(t, card.DynamicVars["Damage"].BaseValue if "Damage" in card.DynamicVars._vars else 0, k, ctx)
        v2 = _dmg_val(t, (card.DynamicVars["Damage"].BaseValue if "Damage" in card.DynamicVars._vars else 0) + extra, k, ctx)
        lost = layers_value(cs, fk) * 0.15 * k if clears and v2 < (t.CurrentHp * k if t else 0) else 0.0   # 清除=兑现，只扣机会成本
        return (v2 - v) - lost
    return f


def _give_fk(n, aoe=False):
    def f(agent, card, t, cs, player, ctx):
        k = ctx["k"]
        tg = [e for e in cs.Enemies if e.IsAlive] if aoe else ([t] if t is not None else [])
        out = 0.0
        for e in tg:
            f0 = _fk(e)
            gain = layers_value(cs, f0 + n) - layers_value(cs, f0)     # 边际价值：超过兑现上限的层不值钱
            out += min(gain, e.CurrentHp) * k + (1.0 if f0 == 0 else 0.0)
        return out
    return f


def _fanji(agent, card, t, cs, player, ctx):
    k = ctx["k"]
    hits = sum(1 for e in cs.Enemies if e.IsAlive and ctx["inc"].get(id(e), 0) > 0)
    return sum(1 + _fk(e) // 2 for e in cs.Enemies if e.IsAlive and ctx["inc"].get(id(e), 0) > 0) * k + hits * 1.5


def _clear_all(per, cap, aoe=False):
    def f(agent, card, t, cs, player, ctx):
        k = ctx["k"]
        tg = [e for e in cs.Enemies if e.IsAlive] if aoe else ([t] if t is not None else [])
        s = 0.0
        for e in tg:
            fk = _fk(e)
            d = per * min(fk, cap)
            s += _dmg_val(e, d, k, ctx) - layers_value(cs, fk) * 0.15 * k
        return s - 4.0 * k    # 层数太低时不值得打出
    return f


def _combine(*fs):
    return lambda *a: sum(f(*a) for f in fs)


PLAY = {
    "NOTEBOOK": _give_fk(2), "STICKER": _give_fk(3), "LOGGED": _give_fk(2), "BATCH_TAG": _give_fk(5),
    "CAUTIOUS": _give_fk(3), "IMMEDIATE": _give_fk(2), "MULTI_TURN": _give_fk(3), "CHAIN_REVIEW": _give_fk(1, True),
    "MASS_NOTICE": _give_fk(3, True), "SYSTEM_CARD": _give_fk(5, True), "FK_SPREAD": _give_fk(2, True),
    "ROUTINE_CHECK": _give_fk(1), "QUICK_REVIEW": _give_fk(0),
    "VERIFIED": None, "ACCOUNT_DISABLED": None,     # 由 register_play 按（变体后的）数值生成
    "FINAL_VERDICT": _extra_single(lambda fk: 12 if fk >= 10 else 0),
    "INSTA_BAN": _extra_single(lambda fk: min(fk, 10) if fk >= 10 else 0, clears=True),
    "PERMA_BAN": _clear_all(4, 25), "MASS_BAN": _clear_all(3, 15, True), "ONE_CLICK_BAN": _clear_all(3, 5),
    "MAKE_EXAMPLE": _clear_all(2, 15),
    "COMPLIANCE_FIX": lambda a, c, t, cs, p, ctx: (layers_value(cs, _fk(t) + min(_fk(t), 10)) - layers_value(cs, _fk(t))) * ctx["k"] - 1.0,
    "EVIDENCE": lambda a, c, t, cs, p, ctx: (layers_value(cs, _fk(t) + min(2 * _fk(t), 20)) - layers_value(cs, _fk(t))) * ctx["k"] - 2.0,
    "DOUBLE_CHECK": _fanji, "RED_TEAM": _fanji, "DEFENSIVE_REPLY": _fanji, "DISCLAIMER": _combine(_fanji, _give_fk(1)),
    "CANT_HELP": _combine(_fanji, _give_fk(2)), "ABSOLUTELY_RIGHT": _fanji,
}


def _extra_vars(card_keep=False):
    """按牌自己的 Per/Cap 计算额外伤害（变体改数值时自动跟随）。"""
    def f(agent, card, t, cs, player, ctx):
        dv = card.DynamicVars
        per = dv["Per"].BaseValue if "Per" in dv._vars else 0
        cap = dv["Cap"].BaseValue if "Cap" in dv._vars else 0
        keep = card_keep or "Keep" in dv._vars
        return _extra_single(lambda fk: min(cap, per * fk), clears=not keep)(agent, card, t, cs, player, ctx)
    return f


def _scaling_cards():
    return {c['id']: {'vars': c['vars'], 'ai': c['ai'].get('value', 1.0),
                      'play': 'dmg_per_fk' if c['ai'].get('keep') else 'verified'}
            for c in MOD.data['cards'] if (c.get('ai') or {}).get('scaling')}


def register_play():
    from sts2sim.engine import agents as A
    for cid, f in PLAY.items():
        if f is not None:
            A.PLAY_ADJUST[entry(cid)] = f
    for cid, sp in _scaling_cards().items():
        A.PLAY_ADJUST[entry(cid)] = _extra_vars(card_keep=sp["play"] == "dmg_per_fk")


def register(mod):
    """yamlmod 在注册完卡牌后调用。"""
    register_values()
    register_play()
