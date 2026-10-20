"""风格偏好（不花钱的规则版）：在任意 agent 外面套一层「看到某些牌就一定拿」。

例：模仿 B 站主播 李日月轩 的铁甲：杂耍（JUGGLING）见到就拿。
  ForcePickAgent(inner, picks={"JUGGLING"}, shop=True)
- 卡牌奖励里有 picks 中的牌 → 直接拿（多张时按 picks 顺序）
- shop=True：商店里有且买得起 → 先买它，再按内层 agent 的清单买
其余决定全部交给内层 agent（属性/方法透明转发）。
"""


def _cid(x):
    c = getattr(x, "Card", x)
    try:
        return c.Id.Entry
    except Exception:  # noqa
        return None


def _hp(inner):
    try:
        c = inner.player.Creature
        return c.CurrentHp / max(1, c.MaxHp)
    except Exception:  # noqa
        return 1.0


class ForcePickAgent:
    """upgrade=True：火堆有未升级的 picks 牌且 HP≥45% → 锻造，锻造选牌优先它。
    play_first=True：战斗里能打出 picks 牌就先打（其余出牌交给内层，例如 MCTS）。"""

    def __init__(self, inner, picks, shop=True, upgrade=True, play_first=False):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_picks", [p.upper() for p in picks])
        object.__setattr__(self, "_shop", shop)
        object.__setattr__(self, "forced", 0)
        object.__setattr__(self, "_upgrade", upgrade)
        object.__setattr__(self, "_play_first", play_first)

    def __getattr__(self, k):
        return getattr(self._inner, k)

    def __setattr__(self, k, v):
        setattr(self._inner, k, v)

    def card_reward(self, cards, alternatives):
        for want in self._picks:
            for r in cards:
                if _cid(r) == want:
                    object.__setattr__(self, "forced", self.forced + 1)
                    self._inner.last_reason = f"风格规则：见到 {want} 就拿"
                    return getattr(r, "Card", r)
        return self._inner.card_reward(cards, alternatives)

    def shop(self, inventory, run):
        buys = list(self._inner.shop(inventory, run) or [])
        if self._shop:
            for e in inventory.CardEntries:
                try:
                    if e.IsStocked and e.EnoughGold and e.CreationResult is not None and _cid(e.CreationResult) in self._picks:
                        object.__setattr__(self, "forced", self.forced + 1)
                        buys = [e] + [b for b in buys if b is not e]
                        break
                except Exception:  # noqa
                    pass
        return buys

    def _raw_pick(self, c):
        return _cid(c) in self._picks and not getattr(c, "IsUpgraded", False)

    def select_cards(self, options, min_sel, max_sel):
        if self._upgrade and max_sel >= 1:
            from .agents import _caller_kind
            opts = list(options)
            star = [c for c in opts if self._raw_pick(c)]
            if star and _caller_kind() == "upgrade":
                rest = [c for c in (self._inner.select_cards(options, min_sel, max_sel) or []) if c is not star[0]]
                return ([star[0]] + rest)[:max(min_sel, 1)]
        return self._inner.select_cards(options, min_sel, max_sel)

    def rest_option(self, options, run):
        if self._upgrade:
            try:
                ids = [str(o.OptionId).upper() for o in options]
                smith = next((i for i, o in enumerate(options) if "SMITH" in ids[i] and getattr(o, "IsEnabled", True)), None)
                if smith is not None and _hp(self._inner) >= 0.45 and any(self._raw_pick(c) for c in self._inner.player.Deck.Cards):
                    self._inner.last_reason = "风格规则：先敲杂耍（固有）"
                    return smith
            except Exception:  # noqa
                pass
        return self._inner.rest_option(options, run)

    def combat_action(self, cs, player, acts):
        if self._play_first:
            for a in acts:
                if a[0] == "play" and _cid(a[1]) in self._picks:
                    return a
        return self._inner.combat_action(cs, player, acts)
