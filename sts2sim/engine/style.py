"""「模仿李日月轩」铁甲风格（免费规则版，套在 learned/StrongAgent 上）。

规则（根据公开直播风格整理的免费规则版）：
- 杂耍 JUGGLING：卡牌奖励/商店必拿（无上限）；火堆优先敲杂耍（拿固有）
- 攻击牌评分 ×1.3、防御牌 ×0.6；删牌先删防御
- 杂耍组件加分：ANGER SPITE BLUDGEON THRASH PERFECTED_STRIKE SETUP_STRIKE BOLAS OFFERING BLOODLETTING
  STOKE PILLAGE EXPECT_A_FIGHT（+TWIN_STRIKE POMMEL_STRIKE BREAKTHROUGH MIND_BLAST WHISTLE 小加分）
- 遗物：SNECKO_EYE / FAKE_SNECKO_EYE / BRIMSTONE / DOLLYS_MIRROR 优先
- 路线：精英收益调高、弱牌组惩罚减半（多冲精英）
- 出牌：手里有杂耍先打；杂耍生效时，本回合第 3 张攻击换成手里最强的可出攻击
用法：apply_lirixuan(agent) 原地改类（agent 需是 StrongAgent 系，例如 batch.make_agent("learned")）。
"""
from .agents import _name, card_cost, dvar

BOOST = {"ANGER": 1.2, "SPITE": 1.0, "BLUDGEON": 1.2, "THRASH": 1.0, "PERFECTED_STRIKE": 1.0, "SETUP_STRIKE": 1.0,
         "BOLAS": 1.0, "OFFERING": 1.0, "BLOODLETTING": 1.0, "STOKE": 1.0, "PILLAGE": 1.0, "EXPECT_A_FIGHT": 1.0,
         "TWIN_STRIKE": 0.5, "POMMEL_STRIKE": 0.5, "BREAKTHROUGH": 0.5, "MIND_BLAST": 0.5, "WHISTLE": 0.5}
RELICS = ["SNECKO_EYE", "FAKE_SNECKO_EYE", "BRIMSTONE", "DOLLYS_MIRROR"]
STAR = "JUGGLING"


def _id(x):
    for a in ("Card", "Model", "Relic"):
        x = getattr(x, a, x) if not hasattr(x, "Id") else x
    try:
        return x.Id.Entry
    except Exception:  # noqa
        return None


def _is_defend(card):
    e = card.Id.Entry
    return e.startswith("DEFEND")


class LiXuanMixin:
    style = "lirixuan"
    swap3 = True       # 第 3 张攻击换成最强攻击（MCTS 战斗时关闭，交给搜索）

    # ---- 牌的价值 ----
    def card_value(self, card, deck=None):
        s = super().card_value(card, deck)
        e = card.Id.Entry
        if e == STAR:
            return s + 10.0
        if _is_defend(card):
            return -1.6                         # 比打击（-1.0）更差 → 删牌先删防
        t = _name(card.Type)
        if t == "Attack":
            s = s * 1.3 if s > 0 else s + 0.3
        elif t == "Skill":
            if dvar(card, "Block") > 0:
                s = s * 0.6 if s > 0 else s - 0.3
        return s + BOOST.get(e, 0.0)

    def marginal(self, card, deck, act=None):
        if card.Id.Entry == STAR:
            return 100.0                        # 杂耍永远不嫌多
        return super().marginal(card, deck, act)

    def card_reward(self, cards, alternatives):
        cs = [getattr(x, "Card", x) for x in cards]
        for c in cs:
            if c.Id.Entry == STAR:              # 覆盖 PPO：见杂耍就拿
                self.forced = getattr(self, "forced", 0) + 1
                self.last_reason = "杂耍永远不嫌多"
                return c
        r = super().card_reward(cards, alternatives)
        if hasattr(self, "_ppo"):
            # mentor-full：PPO 跳过或拿了防御技能时，若有杂耍组件/攻击，改拿（攻哈 / 懦夫才防）
            weak = r is None or (_name(r.Type) != "Attack" and dvar(r, "Block") > 0)
            if weak:
                boost = [c for c in cs if c.Id.Entry in BOOST]
                if boost:
                    r = max(boost, key=lambda c: BOOST[c.Id.Entry])
                    self.last_reason = "攻哈：杂耍组件"
        return r

    def select_cards(self, options, min_sel, max_sel):
        from .agents import _caller_kind
        if _caller_kind() == "upgrade":
            opts = list(options)
            star = [c for c in opts if c.Id.Entry == STAR and not getattr(c, "IsUpgraded", False)]
            if star and max_sel >= 1:
                rest = [c for c in super().select_cards(options, min_sel, max_sel) if c is not star[0]]
                return ([star[0]] + rest)[:max(min_sel, 1)]
        return super().select_cards(options, min_sel, max_sel)

    def rest_option(self, options, run):
        r = super().rest_option(options, run)
        try:
            ids = [str(o.OptionId).upper() for o in options]
            smith = next((i for i, s in enumerate(ids) if "SMITH" in s), None)
            hp = self.player.Creature.CurrentHp / max(1, self.player.Creature.MaxHp)
            raw = any(c.Id.Entry == STAR and not c.IsUpgraded for c in self.player.Deck.Cards)
            if smith is not None and raw and hp >= 0.45:
                return smith                    # 先敲杂耍
        except Exception:  # noqa
            pass
        return r

    # ---- 商店 / 遗物 ----
    def shop(self, inventory, run):
        buys = list(super().shop(inventory, run) or [])
        front = []
        for e in inventory.CardEntries:
            try:
                if e.IsStocked and getattr(e, "EnoughGold", True) and e.CreationResult is not None and _id(e.CreationResult) == STAR:
                    front.append(e)
                    self.forced = getattr(self, "forced", 0) + 1
                    break
            except Exception:  # noqa
                pass
        for e in inventory.RelicEntries:
            try:
                if e.IsStocked and getattr(e, "EnoughGold", True) and _id(e) in RELICS:
                    front.append(e)
            except Exception:  # noqa
                pass
        return front + [b for b in buys if all(b is not f for f in front)]

    def treasure_relic(self, relics, run):
        for i, r in enumerate(relics or []):
            if _id(r) in RELICS:
                return i
        return super().treasure_relic(relics, run)

    # ---- 路线：多冲精英 ----
    def choose_map_point(self, points, run):
        from .weights import W
        old = (W["m_elite_gain"], W["m_weak_elite"])
        W["m_elite_gain"] = old[0] + 2.5
        W["m_weak_elite"] = old[1] * 0.5
        try:
            return super().choose_map_point(points, run)
        finally:
            W["m_elite_gain"], W["m_weak_elite"] = old

    # ---- 出牌 ----
    def on_combat_start(self, cs, player, room):
        self._jt = (None, 0)
        return super().on_combat_start(cs, player, room)

    def _jug_stacks(self, player):
        try:
            for p in player.Creature.Powers:
                if "JUGGLING" in p.Id.Entry:
                    return int(p.Amount)
        except Exception:  # noqa
            pass
        return 0

    def combat_action(self, cs, player, acts):
        rnd = getattr(cs, "RoundNumber", None)
        key, n_atk = getattr(self, "_jt", (None, 0))
        if key != rnd:
            n_atk = 0
        plays = [a for a in acts if a[0] == "play"]
        star = next((a for a in plays if a[1].Id.Entry == STAR), None)
        a = None
        if star is not None:
            a = star                                     # 一张杂耍先出
        if a is None:
            a = super().combat_action(cs, player, acts)
            if (self.swap3 and a is not None and a[0] == "play" and _name(a[1].Type) == "Attack" and n_atk == 2
                    and self._jug_stacks(player) > 0):
                atks = [x for x in plays if _name(x[1].Type) == "Attack"]
                def strength(x):
                    try:
                        s, _ = self._power(x[1])
                    except Exception:  # noqa
                        s = 0.0
                    return s + 0.5 * card_cost(x[1])
                best = max(atks, key=strength)
                if strength(best) > strength(a) + 0.3:
                    a = best                             # 第 3 张攻击 = 最想复制的那张
        if a is not None and a[0] == "play" and _name(a[1].Type) == "Attack":
            n_atk += 1
        self._jt = (rnd, n_atk)
        return a


def apply_lirixuan(agent):
    cls = type(agent)
    agent.__class__ = type("LiXuan" + cls.__name__, (LiXuanMixin, cls), {})
    agent.forced = 0
    if hasattr(agent, "_ppo") or hasattr(agent, "mstats"):
        agent.swap3 = False                     # mentor：出牌全交给 MCTS（只保留「杂耍先出」）
    return agent
