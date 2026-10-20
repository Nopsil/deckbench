"""与角色无关的局外 AI（mod-ai）：用 spire-mentor 的 PPO 当老师，蒸馏成只看“通用特征”的学生网络。

学生不看牌/遗物 id，只看从我们引擎算出来的通用量：费用、伤害、格挡、抽牌、能量、施加的状态、关键词、稀有度、
牌组统计、HP、金币、地图路径统计……所以对模组角色（Claude娘 等）也能用。推理是纯 Python（无 numpy），Windows 可用。

覆盖的局外决策：卡牌奖励（含跳过）、地图路线、休息点（休息/锻造）、商店（每次买一件或离开）。
其它（事件、宝箱、锻造选牌、删牌选哪张、战斗）沿用 learned（StrongAgent）。

模式（ModAIAgent(mode=...)）：
  teacher  老师（PPO）做决定，同时记录学生特征 + 老师概率（采集数据）
  dagger   学生做决定，但记录老师在同一局面的概率（DAgger 第二轮数据）
  student  只用学生（不需要 spire-mentor）
本文件不含任何游戏数据。
"""
import json
import math
import os

from ..rt.boot import game as G
from .agents import _name, dvar, card_cost
from .strong import StrongAgent, card_power, _kw, _src_hits

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "modai_model.json")

# ---------------- 通用卡牌特征 ----------------
KNOWN = ["Damage", "Block", "Cards", "Energy", "Repeat", "Hits", "VulnerablePower", "WeakPower", "StrengthPower",
         "DexterityPower", "FocusPower", "PoisonPower", "DoomPower", "HpLoss", "Heal", "MaxHp", "Stars", "Forge",
         "Summon", "OstyDamage", "Shivs", "PlatingPower", "IntangiblePower", "VigorPower", "StrengthLoss", "ThornsPower"]
SCALE = {"Damage": 10, "Block": 10, "OstyDamage": 10, "HpLoss": 5, "Heal": 10, "MaxHp": 5}
CALC = ("CalculationBase", "CalculationExtra", "ExtraDamage", "CalculatedDamage", "CalculatedBlock", "CalculatedHits")
TYPES = ["Attack", "Skill", "Power", "Curse", "Status"]
RARS = ["Basic", "Common", "Uncommon", "Rare"]
KWS = ["Exhaust", "Ethereal", "Innate", "Retain", "Unplayable", "Sly"]
_CF = {}


def _vars(card):
    try:
        return [str(k) for k in card.DynamicVars._vars.keys()]
    except Exception:  # noqa
        return []


def card_feats(card):
    key = (card.Id.Entry, int(getattr(card, "CurrentUpgradeLevel", 0) or 0), bool(getattr(card, "IsUpgraded", False)))
    f = _CF.get(key)
    if f is not None:
        return f
    vs = _vars(card)
    v = lambda k: dvar(card, k)  # noqa
    tn, rar = _name(card.Type), _name(card.Rarity)
    kw = _kw(card)
    try:
        xcost = bool(card.EnergyCost.CostsX)
    except Exception:  # noqa
        xcost = False
    cost = 0.0 if xcost else float(card_cost(card))
    hits = max(1.0, v("Repeat"), v("Hits"), float(_src_hits(card)))
    tt = card.TargetType
    aoe = 1.0 if tt == G.TargetType.AllEnemies else 0.0
    rnd = 1.0 if tt == G.TargetType.RandomEnemy else 0.0
    dmg = max(v("Damage"), v("OstyDamage"))
    calc = 1.0 if any(k in vs for k in CALC) else 0.0
    other = [k for k in vs if k not in KNOWN and k not in CALC]
    other_pow = sum(1 for k in other if k.endswith("Power"))
    try:
        s, tags = card_power(card)
    except Exception:  # noqa
        s, tags = 0.0, set()
    f = [cost / 3.0, float(xcost), dmg * hits / 10.0, hits / 3.0, aoe, rnd, calc,
         min(len(other), 4) / 4.0, min(other_pow, 2) / 2.0,
         float(bool(getattr(card, "IsUpgraded", False))), s / 3.0,
         (dmg * hits * (1.5 if aoe else 1.0)) / max(1.0, cost) / 10.0, v("Block") / max(1.0, cost) / 10.0]
    f += [min(v(k), 30.0) / SCALE.get(k, 3.0) for k in KNOWN]
    f += [1.0 if tn == t else 0.0 for t in TYPES]
    f += [1.0 if rar == r else 0.0 for r in RARS]
    f += [1.0 if k in kw else 0.0 for k in KWS]
    f += [1.0 if t in tags else 0.0 for t in ("attack", "aoe", "scaling")]
    _CF[key] = f
    return f


NCF = 13 + len(KNOWN) + len(TYPES) + len(RARS) + len(KWS) + 3


def deck_ctx(agent):
    p = agent.player
    st = agent._run.state
    deck = list(p.Deck.Cards)
    n = max(1, len(deck))
    cnt = {t: 0 for t in TYPES}
    basic = strike = 0
    sdmg = sblk = sdraw = sen = saoe = spow = sval = up = 0.0
    for c in deck:
        cf = card_feats(c)
        t = _name(c.Type)
        cnt[t] = cnt.get(t, 0) + 1
        if _name(c.Rarity) == "Basic":
            basic += 1
            if t == "Attack":
                strike += 1
        sdmg += cf[2]
        sblk += cf[13 + 1]
        sdraw += cf[13 + 2]
        sen += cf[13 + 3]
        saoe += cf[4] * (1 if cf[2] > 0 else 0)
        spow += cf[13 + len(KNOWN) + 2]
        sval += cf[10]
        up += cf[9]
    act = int(st.CurrentActIndex)
    hp, mhp = p.Creature.CurrentHp, max(1, p.Creature.MaxHp)
    return [act / 2.0, float(act == 0), float(act == 1), float(act == 2), int(st.TotalFloor) / 50.0,
            hp / mhp, mhp / 100.0, hp / 100.0, min(p.Gold, 600) / 300.0, int(st.AscensionLevel) / 10.0,
            n / 30.0, cnt["Attack"] / n, cnt["Skill"] / n, cnt["Power"] / n, (cnt["Curse"] + cnt["Status"]) / n,
            basic / n, strike / n, sdmg / n, sblk / n, sdraw / n, sen / n, saoe / 3.0, spow / 3.0, sval / n, up / n,
            sum(1 for x in p.PotionSlots if x is not None) / 3.0, len(list(p.Relics)) / 10.0]


NCTX = 27

# ---------------- 地图路径特征 ----------------
NODE = ["Monster", "Elite", "Unknown", "RestSite", "Shop", "Treasure", "Boss"]


def path_feats(pt):
    """从 pt 出发到首领的所有路径上，各类节点数的 (最小, 最大)。"""
    memo = {}

    def go(x):
        k = (int(x.coord.col), int(x.coord.row))
        if k in memo:
            return memo[k]
        t = _name(x.PointType)
        own = [1 if t == nt else 0 for nt in NODE[:6]]
        ch = list(x.Children)
        if not ch:
            r = (own, own, 0)
        else:
            subs = [go(c) for c in ch]
            r = ([own[i] + min(s[0][i] for s in subs) for i in range(6)],
                 [own[i] + max(s[1][i] for s in subs) for i in range(6)], 1 + max(s[2] for s in subs))
        memo[k] = r
        return r
    mn, mx, depth = go(pt)
    return [a / 4.0 for a in mn] + [a / 4.0 for a in mx] + [depth / 16.0]


NPF = 13

# ---------------- 各决策面的选项特征（ctx + 选项） ----------------


def opts_card_reward(agent, cards):
    ctx = deck_ctx(agent)
    ids = {}
    for c in agent.player.Deck.Cards:
        ids[c.Id.Entry] = ids.get(c.Id.Entry, 0) + 1
    X = [ctx + [0.0] + card_feats(c) + [min(ids.get(c.Id.Entry, 0), 3) / 3.0] for c in cards]
    X.append(ctx + [1.0] + [0.0] * NCF + [0.0])     # 跳过
    return X


def opts_map(agent, points):
    ctx = deck_ctx(agent)
    return [ctx + [1.0 if _name(pt.PointType) == t else 0.0 for t in NODE] + path_feats(pt) for pt in points]


def _rest_extra(agent, run):
    deck = list(agent.player.Deck.Cards)
    gains = sorted((max(0.0, card_feats(c)[10]) + (1.0 if _name(c.Type) == "Power" else 0.0)
                    for c in deck if not getattr(c, "IsUpgraded", False) and _name(c.Type) not in ("Curse", "Status")),
                   reverse=True)
    nxt_boss = nxt_elite = 0.0
    rows = 0.0
    try:
        cur = run.state.CurrentMapPoint
        nxt = list(cur.Children)
        nxt_boss = float(any(_name(c.PointType) == "Boss" for c in nxt))
        nxt_elite = float(any(_name(c.PointType) == "Elite" for c in nxt))
        rows = path_feats(cur)[-1]
    except Exception:  # noqa
        pass
    return [nxt_boss, nxt_elite, rows, (gains[0] if gains else 0.0), sum(gains[:3]) / 3.0, len(gains) / 20.0]


def opts_rest(agent, run, kinds):
    ctx = deck_ctx(agent) + _rest_extra(agent, run)
    return [ctx + [1.0 if k == "HEAL" else 0.0, 1.0 if k == "SMITH" else 0.0] for k in kinds]


SHOPK = ["leave", "card", "relic", "potion", "remove"]


def opts_shop(agent, items):
    """items: [(kind, price, card_or_None, rarity_name_or_None)]"""
    ctx = deck_ctx(agent)
    gold = max(1, agent.player.Gold)
    ids = {}
    for c in agent.player.Deck.Cards:
        ids[c.Id.Entry] = ids.get(c.Id.Entry, 0) + 1
    X = []
    for kind, price, card, rar in items:
        x = ctx + [1.0 if kind == k else 0.0 for k in SHOPK] + [price / gold, price / 150.0]
        x += [1.0 if rar == r else 0.0 for r in ("Common", "Uncommon", "Rare", "Shop")]
        x += (card_feats(card) + [min(ids.get(card.Id.Entry, 0), 3) / 3.0]) if card is not None else [0.0] * (NCF + 1)
        X.append(x)
    return X


# ---------------- 学生网络（纯 Python 推理） ----------------
class Net:
    """每个决策面一个小 MLP：score(x) = w2·tanh(W1·norm(x)+b1)+ v·norm(x)；选项间 softmax。"""

    def __init__(self, d):
        self.mu, self.sd = d["mu"], d["sd"]
        self.W1, self.b1, self.w2, self.v = d["W1"], d["b1"], d["w2"], d["v"]

    def score(self, x):
        z = [(a - m) / s for a, m, s in zip(x, self.mu, self.sd)]
        out = sum(a * b for a, b in zip(self.v, z))
        for row, b, w in zip(self.W1, self.b1, self.w2):
            out += w * math.tanh(b + sum(a * c for a, c in zip(row, z)))
        return out


_MODEL = {}


def load_model(path=None):
    path = path or os.environ.get("DECKBENCH_MODAI_MODEL") or MODEL_PATH
    if path not in _MODEL:
        with open(path) as f:
            d = json.load(f)
        _MODEL[path] = {k: Net(v) for k, v in d["nets"].items()}
    return _MODEL[path]


def _softmax(s):
    m = max(s)
    e = [math.exp(a - m) for a in s]
    t = sum(e)
    return [a / t for a in e]


# ---------------- Agent ----------------
class ModAIAgent(StrongAgent):
    """局外：学生网络（或老师 PPO）；战斗：StrongAgent（learned 参数，可选首领整场推演）。"""
    name = "modai"

    # 默认不接管路线：学生路线在原版角色上和 learned 持平，但会让出牌弱的模组角色多打精英（Claude娘 A0 −0.3、A10 −0.9 层）
    DEFAULT_SURFACES = ("card_reward", "rest", "shop")

    def __init__(self, seed=0, mode="student", surfaces=DEFAULT_SURFACES, log=None,
                 model=None, **kw):
        super().__init__(seed=seed, **kw)
        self.mode = mode
        self.surfaces = set(surfaces)
        self.logbuf = log            # list，采集模式下每个决策追加一条
        self.nets = load_model(model) if mode in ("student", "dagger") and self.surfaces else {}
        self.mstats = {"mentor": 0, "fallback": 0, "reasons": {}, "mcts_sec": 0.0, "modai": {}}
        if mode in ("teacher", "dagger"):
            from .mentor_full import PpoNonCombat
            self._teacher = PpoNonCombat

    def _stat(self, s, k):
        d = self.mstats["modai"].setdefault(s, [0, 0])
        d[k] += 1

    def _teacher_probs(self, surface, msg, n, mapper):
        """调 PPO，返回长度 n 的概率（按我们的选项顺序）；不可用返回 None。"""
        from .mentor_full import envelope, CHARS
        from .mentor import lib
        ch = CHARS.get(self.player.Character.Id.Entry)
        if ch is None:
            return None
        try:
            rs, _ = lib()
            r = rs.ppo_wire_decide(envelope(msg, self._run.state, self.player), surface, ch)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:  # noqa
            return None
        if r is None:
            return None
        probs = [0.0] * n
        pr = r.get("probs") or r.get("probabilities")
        for i, resp in enumerate(r["responses"]):
            j = mapper(r["actions"][i], resp)
            if j is not None and 0 <= j < n:
                probs[j] += float(pr[i]) if pr is not None else (1.0 if i == int(r["argmax"]) else 0.0)
        t = sum(probs)
        if t <= 0:
            return None
        j = mapper(r["actions"][int(r["argmax"])], r["responses"][int(r["argmax"])])
        return [p / t for p in probs], j, r

    def _decide(self, surface, X, teacher):
        """返回所选下标；None = 回退 StrongAgent。teacher: () -> (probs, argmax_idx, raw) or None"""
        if surface not in self.surfaces:
            return None
        tp = None
        if self.mode in ("teacher", "dagger"):
            tp = teacher()
            if tp is not None and self.logbuf is not None:
                self.logbuf.append({"s": surface, "X": [[round(a, 4) for a in x] for x in X], "p": [round(a, 4) for a in tp[0]],
                                    "a": tp[1], "char": self.player.Character.Id.Entry, "asc": int(self._run.state.AscensionLevel)})
        if self.mode == "teacher":
            if tp is None or tp[1] is None:
                self._stat(surface, 1)
                return None
            self._stat(surface, 0)
            return tp[1]
        net = self.nets.get(surface)
        if net is None:
            self._stat(surface, 1)
            return None
        self._stat(surface, 0)
        s = [net.score(x) for x in X]
        return max(range(len(s)), key=lambda i: s[i])

    # ---------- 卡牌奖励 ----------
    def card_reward(self, cards, alternatives):
        from .mentor_full import _card
        cs = [(x.Card if hasattr(x, "Card") else x) for x in cards]
        if not cs:
            return super().card_reward(cards, alternatives)
        n = len(cs)

        def mapper(act, resp):
            return int(resp["index"]) if resp.get("action") == "choose" else n

        i = self._decide("card_reward", opts_card_reward(self, cs),
                         lambda: self._teacher_probs("card_reward", {"type": "card_reward", "cards": [_card(c) for c in cs],
                                                                      "can_skip": True}, n + 1, mapper))
        if i is None:
            return super().card_reward(cards, alternatives)
        return cs[i] if i < n else None

    # ---------- 地图 ----------
    def choose_map_point(self, points, run):
        if len(points) <= 1:
            return super().choose_map_point(points, run)
        nodes = [{"index": i, "type": _name(pt.PointType), "row": int(pt.coord.row), "col": int(pt.coord.col)}
                 for i, pt in enumerate(points)]

        def mapper(act, resp):
            return int(resp["index"]) if resp.get("action") == "choose" else None

        i = self._decide("map", opts_map(self, points),
                         lambda: self._teacher_probs("map_select", {"type": "map_select", "nodes": nodes}, len(points), mapper))
        return points[i] if i is not None else super().choose_map_point(points, run)

    # ---------- 休息 ----------
    def rest_option(self, options, run):
        ids = [str(o.OptionId).upper() for o in options]
        en = [i for i, o in enumerate(options) if getattr(o, "IsEnabled", True)]
        sel = [i for i in en if ids[i] in ("HEAL", "SMITH")]
        if len(sel) == 2:
            sel.sort(key=lambda i: 0 if ids[i] == "HEAL" else 1)
            if len(en) == 2:
                msg = {"type": "rest_site", "options": [{"index": j, "id": ids[i].lower(), "label": ids[i].lower(), "enabled": True}
                                                        for j, i in enumerate(sel)]}
                teacher = lambda: self._teacher_probs("rest_site", msg, 2, lambda a, r: int(r["index"]))  # noqa
            else:
                teacher = lambda: None  # noqa  网络只学过 [rest, smith]
            j = self._decide("rest", opts_rest(self, run, ["HEAL", "SMITH"]), teacher)
            if j is not None:
                return sel[j]
        return super().rest_option(options, run)

    # ---------- 商店 ----------
    def shop(self, inventory, run):
        from .mentor_full import _card
        p = self.player
        open_slot = any(x is None for x in p.PotionSlots)
        opts = [{"index": 0, "id": "leave_shop", "action": "leave_shop", "label": "Leave shop", "enabled": True}]
        ents, items = [None], [("leave", 0.0, None, None)]
        purge = None
        for e in G._iter(inventory.AllEntries):
            if not (e.IsStocked and e.EnoughGold):
                continue
            card = rar = None
            if isinstance(e, G.MerchantCardEntry):
                if e.CreationResult is None:
                    continue
                card = e.CreationResult.Card
                kind, item, k2 = "buy_card", _card(card), "card"
            elif isinstance(e, G.MerchantRelicEntry):
                kind, item, k2 = "buy_relic", {"id": e.Model.Id.Entry}, "relic"
                rar = _name(getattr(e.Model, "Rarity", ""))
            elif isinstance(e, G.MerchantPotionEntry):
                if not open_slot:
                    continue
                kind, item, k2 = "buy_potion", {"id": e.Model.Id.Entry}, "potion"
            elif isinstance(e, G.MerchantCardRemovalEntry):
                kind, item, k2, purge = "remove_card", None, "remove", int(e.Cost)
            else:
                continue
            o = {"index": len(opts), "id": kind, "action": kind, "label": kind, "enabled": True, "price": int(e.Cost)}
            if item is not None:
                o["item"] = item
            opts.append(o)
            ents.append(e)
            items.append((k2, float(e.Cost), card, rar))
        if len(opts) == 1:
            return []
        msg = {"type": "shop", "options": opts, "player_gold": int(p.Gold)}
        if purge is not None:
            msg["purge_cost"] = purge

        def mapper(act, resp):
            return int(resp["index"])

        i = self._decide("shop", opts_shop(self, items), lambda: self._teacher_probs("shop", msg, len(opts), mapper))
        if i is None:
            return super().shop(inventory, run)
        e = ents[i]
        return [] if e is None else [e]


def make_modai_agent(seed=0, mode="student", boss_search=False, **kw):
    from .weights import load_learned
    load_learned()
    if boss_search:
        kw = dict(kw, boss_search=True)
        kw.setdefault("boss_width", 8)
        kw.setdefault("boss_depth", 99)
    return ModAIAgent(seed=seed, mode=mode, search=False, **kw)


# ======================================================================
# 战斗：把 spire-mentor MCTS 的出牌蒸馏成通用的“动作打分”网络
# ======================================================================
from .combat import alive_enemies, hand  # noqa: E402

ROOMS = ["Monster", "Elite", "Boss"]


def combat_ctx_feats(agent, cs, player, ctx):
    pc = player.Creature
    en = alive_enemies(cs)
    pcs = player.PlayerCombatState
    try:
        energy = float(pcs.Energy)
    except Exception:  # noqa
        energy = 0.0
    try:
        draw, disc = len(list(pcs.DrawPile.Cards)), len(list(pcs.DiscardPile.Cards))
    except Exception:  # noqa
        draw = disc = 0
    inc = float(sum(ctx["inc"].values()))
    ehp = ctx["ehp"]
    act = 0
    try:
        act = int(agent._run.state.CurrentActIndex)
    except Exception:  # noqa
        pass
    return [energy / 3.0, len(hand(player)) / 10.0, draw / 20.0, disc / 20.0,
            pc.CurrentHp / max(1, pc.MaxHp), pc.CurrentHp / 80.0, pc.Block / 20.0, ctx["need"] / 20.0, inc / 30.0,
            min(cs.RoundNumber, 15) / 10.0, len(en) / 3.0, ehp / 150.0, min(5.0, ehp / max(4.0, ctx["avg_inc"])) / 5.0,
            ctx["k"], sum(1 for x in player.PotionSlots if x is not None) / 3.0, act / 2.0] + \
        [1.0 if agent.room_kind == r else 0.0 for r in ROOMS]


NCC = 19
NAF = 3 + 6 + NCF + 12


def combat_opts(agent, cs, player, acts):
    """返回 (X, 启发式分数)。"""
    ctx = agent._make_ctx(cs, player)
    base = combat_ctx_feats(agent, cs, player, ctx)
    hp = player.Creature.CurrentHp
    en = alive_enemies(cs)
    try:
        energy = float(player.PlayerCombatState.Energy)
    except Exception:  # noqa
        energy = 0.0
    hs = []
    for a in acts:
        if a[0] == "play":
            s = agent._score_play(a[1], a[2], cs, player, ctx)
            if s < 0.03:
                s = 0.0
        elif a[0] == "potion":
            s = agent._score_potion(a[1], a[2], cs, player, ctx["need"], hp)
            if s < 0.9:
                s = 0.0
        else:
            s = 0.0
        hs.append(s)
    mx = max(hs) if hs else 0.0
    best = max(range(len(hs)), key=lambda i: hs[i]) if mx > 0 else len(acts) - 1
    order = sorted(range(len(hs)), key=lambda i: -hs[i])
    rank = {i: r for r, i in enumerate(order)}
    lo = min(en, key=lambda e: e.CurrentHp) if en else None
    hi = max(en, key=lambda e: ctx["inc"].get(id(e), 0)) if en else None
    X = []
    for i, a in enumerate(acts):
        kind = a[0]
        f = [1.0 if kind == "play" else 0.0, 1.0 if kind == "potion" else 0.0, 1.0 if kind == "end" else 0.0,
             min(hs[i], 20.0) / 5.0, hs[i] / mx if mx > 0 else 0.0, 1.0 if i == best else 0.0, 1.0 if hs[i] > 0 else 0.0,
             rank[i] / max(1, len(acts)), math.log1p(hs[i])]
        if kind == "play":
            c, t = a[1], a[2]
            cf = card_feats(c)
            dmg, hits, blk = agent._preview(c, t)
            cost = float(card_cost(c))
            tt_enemy = t is not None and t in en
            eff = (t.CurrentHp + t.Block) if tt_enemy else 0
            ex = [cost / max(1.0, energy), (energy - cost) / 3.0, dmg * hits / 20.0, blk / 20.0,
                  1.0 if tt_enemy and dmg * hits >= eff > 0 else 0.0,
                  (t.CurrentHp / max(1, t.MaxHp)) if tt_enemy else 0.0,
                  (ctx["inc"].get(id(t), 0) / 20.0) if tt_enemy else 0.0,
                  1.0 if tt_enemy and ctx.get("minion") and id(t) in ctx["minion"] else 0.0,
                  1.0 if t is lo and tt_enemy else 0.0, 1.0 if t is hi and tt_enemy else 0.0,
                  min(blk, ctx["need"]) / 20.0, (t.Block / 20.0) if tt_enemy else 0.0]
        else:
            cf = [0.0] * NCF
            ex = [0.0] * 12
        X.append(base + f + cf + ex)
    return X, hs


class _Unmapped(Exception):
    pass


def mcts_labels(agent, cs, player, acts, sims=1000, seed=0):
    """调 spire-mentor MCTS，返回 (每个我们动作的 q 或 None, visits, 最优下标)；不支持抛 Unsupported。"""
    from . import mentor as M
    rs, _ = M.lib()
    asc = getattr(getattr(agent, "_run", None), "ascension", 0)
    w, alive = M.to_wire(cs, player, agent.room_kind, asc, seed)
    try:
        s = rs.state_from_dict(w)
    except Exception as e:  # noqa
        raise M.Unsupported(f"state_from_dict: {str(e)[:120]}")
    r = rs.mcts_recommend(s, sims=sims, threads=1, seed=seed)
    q = [None] * len(acts)
    vis = [0] * len(acts)
    best = None
    idx = {id(a): i for i, a in enumerate(acts)}
    for x in r["actions"]:
        try:
            a = M.map_action(x["action"], player, acts, alive)
        except M.Unsupported:
            continue
        i = idx.get(id(a))
        if i is None:
            continue
        qq = float(x.get("q", 0.0))
        if q[i] is None or qq > q[i]:
            q[i] = qq
        vis[i] += int(x.get("visits", 0))
        if x.get("is_best"):
            best = i
    if best is None:
        cand = [i for i in range(len(acts)) if q[i] is not None]
        if not cand:
            raise M.Unsupported("no mappable action")
        best = max(cand, key=lambda i: q[i])
    return q, vis, best


class CombatDistill:
    """混入 ModAIAgent 之前：combat_mode = learned | teacher | dagger | student。"""

    def _combat_init(self, combat_mode, sims, clog, seed):
        self.combat_mode = combat_mode
        self.csims = sims
        self.clog = clog
        self._cseed = seed
        self._ck = 0
        if combat_mode in ("student", "dagger") and "combat" not in self.nets:
            self.nets = dict(self.nets, **{k: v for k, v in load_model(getattr(self, "_model_path", None)).items()})

    def combat_action(self, cs, player, acts):
        cm_ = getattr(self, "combat_mode", "learned")
        if cm_ == "learned" or self._in_child or len(acts) <= 1:
            return super().combat_action(cs, player, acts)
        from . import mentor as M
        X, hs = combat_opts(self, cs, player, acts)
        lab = None
        if cm_ in ("teacher", "dagger"):
            self._ck += 1
            try:
                lab = mcts_labels(self, cs, player, acts, sims=self.csims, seed=(self._cseed * 7919 + self._ck) & 0xFFFFFFFF)
            except M.Unsupported:
                lab = None
            if lab is not None and self.clog is not None:
                self.clog.append({"s": "combat", "X": [[round(a, 4) for a in x] for x in X], "q": lab[0], "v": lab[1],
                                  "a": lab[2], "h": max(range(len(hs)), key=lambda i: hs[i]) if max(hs) > 0 else len(acts) - 1,
                                  "char": player.Character.Id.Entry, "room": self.room_kind,
                                  "asc": int(self._run.state.AscensionLevel)})
        st = self.mstats.setdefault("combat", [0, 0])
        if cm_ == "teacher":
            if lab is None:
                st[1] += 1
                return super().combat_action(cs, player, acts)
            st[0] += 1
            return acts[lab[2]]
        net = self.nets.get("combat")
        if net is None:
            st[1] += 1
            return super().combat_action(cs, player, acts)
        st[0] += 1
        s = [net.score(x) for x in X]
        b = max(range(len(s)), key=lambda i: s[i])
        gate = getattr(self, "cgate", 0.0)
        if gate > 0:
            # 只有学生明显更偏好别的动作时才改启发式的选择（启发式 = combat_opts 里记的 best）
            h = max(range(len(hs)), key=lambda i: hs[i]) if max(hs) > 0 else len(acts) - 1
            if b != h and s[b] - s[h] < gate:
                if len(st) < 3:
                    st.append(0)
                st[2] += 1
                return acts[h]
        return acts[b]


def make_modai_agent2(seed=0, mode="student", combat_mode="learned", sims=1000, clog=None, boss_search=False, model=None,
                      cgate=0.0, **kw):
    """mode = 局外（teacher/dagger/student/learned）；combat_mode = 出牌（learned/teacher/dagger/student）。"""
    from .weights import load_learned
    load_learned()
    if boss_search:
        kw = dict(kw, boss_search=True)
        kw.setdefault("boss_width", 8)
        kw.setdefault("boss_depth", 99)

    class Agent2(CombatDistill, ModAIAgent):
        pass
    surfaces = kw.pop("surfaces", ModAIAgent.DEFAULT_SURFACES)
    if mode == "learned":
        surfaces = ()
        mode = "student"
    ag = Agent2.__new__(Agent2)
    ag._model_path = model
    ModAIAgent.__init__(ag, seed=seed, mode=mode, surfaces=surfaces, model=model, search=False, **kw)
    ag._combat_init(combat_mode, sims, clog, seed)
    ag.cgate = float(os.environ.get("DECKBENCH_MODAI_GATE", cgate))
    return ag
