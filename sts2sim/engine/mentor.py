"""spire-mentor（外部 Rust 引擎）做战斗搜索的桥接。

spire-mentor 不在本仓库里（它的仓库带游戏文本/数据），需要用户自己克隆并构建 Python 绑定：
  DECKBENCH_MENTOR_SITE = sts2_rs 所在的 site-packages（maturin develop 装好的 venv）
  DECKBENCH_MENTOR_PY = spire-mentor/sts2-pycli/python（用它的 sts2_hint.adapter 把状态转成线格式）
流程：我们的 CombatState → Sts2Headless combat_play 形状的 dict → sts2_hint.adapter.translate
     → sts2_rs.state_from_dict → sts2_rs.mcts_recommend → 映射回我们的动作。
任何牌/遗物/能力/怪物/药水不被识别（如 Claude娘 模组内容）就抛 Unsupported，调用方回退到自己的搜索。
"""
import os
import re
import sys

from ..rt.boot import game as G
from .combat import alive_enemies, hand

# spire-mentor 是外部依赖（其仓库含游戏数据，本项目不内置）：自行构建后用环境变量指向它
_DEF_SITE = os.environ.get("DECKBENCH_MENTOR_SITE", "")   # 装了 sts2_rs 的 site-packages
_DEF_PY = os.environ.get("DECKBENCH_MENTOR_PY", "")       # spire-mentor 的 sts2-pycli/python 目录


class Unsupported(Exception):
    pass


_M = {}


def lib():
    """懒加载 (sts2_rs, adapter)。不可用时抛 Unsupported。"""
    if "rs" in _M:
        if _M["rs"] is None:
            raise Unsupported("sts2_rs unavailable: " + _M["err"])
        return _M["rs"], _M["ad"]
    try:
        for p in (os.environ.get("STS2SIM_MENTOR_SITE", _DEF_SITE), os.environ.get("STS2SIM_MENTOR_PY", _DEF_PY)):
            if p and os.path.isdir(p) and p not in sys.path:
                sys.path.append(p)
        import logging
        logging.getLogger("sts2_hint").setLevel(logging.ERROR)
        import sts2_rs
        from sts2_hint import adapter
        _M.update(rs=sts2_rs, ad=adapter)
        _M["status_titles"] = {t.upper().replace(" ", "_"): t for t in adapter.STATUS_CARD_TITLES}
        _M["potions"] = frozenset(sts2_rs.list_registry_names("potion"))
    except Exception as e:  # noqa
        _M.update(rs=None, err=f"{type(e).__name__}: {e}")
        raise Unsupported("sts2_rs unavailable: " + _M["err"])
    return _M["rs"], _M["ad"]


def _n(x):
    try:
        return x.ToString() if hasattr(x, "ToString") else str(x)
    except Exception:  # noqa
        return str(x)


def _ename(x):
    s = str(getattr(x, "name", None) or x)
    return s.split(".")[-1]


def _safe(f, d=None):
    try:
        return f()
    except Exception:  # noqa
        return d


def _card(c, idx, in_hand=False):
    ec = c.EnergyCost
    CM = G.CostModifiers
    cost = _safe(lambda: ec.GetWithModifiers(CM.All), _safe(lambda: ec.Canonical, 0))
    costs_x = bool(_safe(lambda: ec.CostsX, False))
    base = -1 if costs_x else _safe(lambda: ec.GetWithModifiers(CM.Local))
    if isinstance(base, int) and base < 0:
        base = -1
    eff = _safe(lambda: ec.GetAmountToSpend(), cost)
    typ = _ename(c.Type)
    kws = set()
    for k in _safe(lambda: list(c.Keywords), []) or []:
        kws.add(_ename(k).lower())
    cid = c.Id.Entry
    out = {
        "index": idx, "id": cid, "type": typ,
        "cost": eff if isinstance(eff, int) else cost,
        "upgraded": bool(_safe(lambda: c.IsUpgraded, False)),
    }
    if isinstance(base, int):
        out["base_cost"] = base
    if typ in ("Status", "Curse"):
        out["name"] = _M["status_titles"].get(cid, cid)
    stats = {}
    for dv in _safe(lambda: list(c.DynamicVars.Values), []) or []:
        v = _safe(lambda: int(dv.BaseValue))
        if isinstance(v, int):
            stats[str(dv.Name).lower()] = v
    if stats:
        out["stats"] = stats
    en = _safe(lambda: c.Enchantment)
    if en is not None:
        out["enchantment"] = en.Id.Entry
        a = _safe(lambda: int(en.Amount), 0)
        if a:
            out["enchantment_amount"] = a
    af = _safe(lambda: c.Affliction)
    if af is not None:
        out["affliction"] = type(af).__name__
        out["affliction_stacks"] = _safe(lambda: int(af.Amount), 1)
    if in_hand:
        k = [x for x in ("retain", "ethereal", "innate", "sly") if x in kws]
        if "unplayable" in kws:
            k.append("unplayable")
        if k:
            out["keywords"] = k
        if _safe(lambda: bool(c.ShouldRetainThisTurn), False):
            out["will_retain"] = True
        if _safe(lambda: bool(c.IsSlyThisTurn), False):
            out["sly_this_turn"] = True
    return out


def _power(p):
    d = {"id": p.Id.Entry, "name": p.Id.Entry, "amount": int(p.Amount)}
    da = _safe(lambda: int(p.DisplayAmount))
    if da is not None:
        d["display_amount"] = da
    vs = {}
    for dv in _safe(lambda: list(p.DynamicVars.Values), []) or []:
        v = _safe(lambda: int(dv.BaseValue))
        if isinstance(v, int):
            vs[str(dv.Name)] = v
    if vs:
        d["vars"] = vs
    return d


def _enemy(e, i, player):
    m = e.Monster
    d = {"index": i, "name": f"{m.Id.Entry}.name", "hp": int(e.CurrentHp), "max_hp": int(e.MaxHp),
         "block": int(e.Block), "powers": [_power(p) for p in e.Powers]}
    nm = _safe(lambda: m.NextMove)
    ints = []
    if nm is not None:
        d["move_state"] = _safe(lambda: nm.Id)
        targets = [player.Creature]
        for it in _safe(lambda: list(nm.Intents), []) or []:
            x = {"type": _ename(it.IntentType)}
            if isinstance(it, G.AttackIntent):
                dmg = _safe(lambda: int(it.GetSingleDamage(targets, e)))
                if dmg is not None:
                    x["damage"] = dmg
                    x["hits"] = max(1, _safe(lambda: int(it.Repeats), 1))
            ints.append(x)
    d["intents"] = ints
    return d


def _rng(run_state, player):
    r = run_state.Rng
    c = {
        "up_front": r.UpFront._counter, "shuffle": r.Shuffle._counter,
        "combat_card_generation": r.CombatCardGeneration._counter,
        "combat_potion_generation": r.CombatPotionGeneration._counter,
        "combat_card_selection": r.CombatCardSelection._counter,
        "combat_energy_costs": r.CombatEnergyCosts._counter,
        "combat_targets": r.CombatTargets._counter, "monster_ai": r.MonsterAi._counter,
        "niche": r.Niche._counter, "combat_orbs": r.CombatOrbGeneration._counter,
    }
    pr = _safe(lambda: player.PlayerRng)
    if pr is not None:
        c.update(rewards=pr.Rewards._counter, shops=pr.Shops._counter, transformations=pr.Transformations._counter)
    return {"run_seed": int(r.Seed), "counters": c}


def to_headless(cs, player, room_kind="Monster", with_rng=True):
    """我们的战斗状态 → Sts2Headless combat_play 形状（sts2_hint.adapter.translate 的输入）。"""
    lib()
    pcs = player.PlayerCombatState
    P = G.PileType
    h = hand(player)
    n = len(h)
    cards = {}

    def pile(pt, start, in_hand=False):
        out = []
        for j, c in enumerate(list(pt.GetPile(player).Cards)):
            out.append(_card(c, start + j, in_hand))
        return out
    hand_d = pile(P.Hand, 0, True)
    draw = pile(P.Draw, n)
    disc = pile(P.Discard, n + len(draw))
    exh = pile(P.Exhaust, n + len(draw) + len(disc))
    alive = alive_enemies(cs)
    dead = [e for e in cs.Enemies if not e.IsAlive and _safe(lambda: e.Monster is not None, False)]
    pots = []
    for p in list(player.PotionSlots):
        if p is None:
            pots.append(None)
        else:
            pots.append({"id": p.Id.Entry})
    st = {
        "type": "decision", "decision": "combat_play",
        "context": {"room_type": {"Elite": "Elite", "Boss": "Boss"}.get(room_kind, "Monster")},
        "round": int(cs.RoundNumber), "energy": int(pcs.Energy), "max_energy": int(pcs.MaxEnergy),
        "hand": hand_d, "draw_pile": draw, "discard_pile": disc, "exhaust_pile": exh,
        "enemies": [_enemy(e, i, player) for i, e in enumerate(alive)],
        "dead_enemies": [_enemy(e, len(alive) + i, player) for i, e in enumerate(dead) if _revives(e)],
        "player": {"hp": int(player.Creature.CurrentHp), "max_hp": int(player.Creature.MaxHp),
                   "block": int(player.Creature.Block), "gold": int(player.Gold),
                   "relics": [{"id": r.Id.Entry, "name": r.Id.Entry,
                               **({"counter": int(r.DisplayAmount)} if _safe(lambda: r.ShowCounter, False) else {})}
                              for r in player.Relics if not _pickup_only(r)],
                   "potions": []},
        "player_powers": [_power(p) for p in player.Creature.Powers],
        "game_version": "v0.111.0",
    }
    oq = _safe(lambda: pcs.OrbQueue)
    if oq is not None and player.Character.Id.Entry == "DEFECT" or (oq is not None and _safe(lambda: len(list(oq.Orbs)), 0)):
        orbs = []
        for o in list(oq.Orbs):
            t = type(o).__name__.replace("Orb", "")
            orbs.append({"type": t, "passive": int(_safe(lambda: o.PassiveVal, 0)), "evoke": int(_safe(lambda: o.EvokeVal, 0))})
        st["orbs"] = orbs
        st["orb_slots"] = int(_safe(lambda: oq.Capacity, len(orbs)))
    if player.Character.Id.Entry == "REGENT":
        st["stars"] = int(_safe(lambda: pcs.Stars, 0))
    osty = _safe(lambda: player.Osty)
    if osty is not None:
        st["osty"] = {"hp": int(osty.CurrentHp), "max_hp": int(osty.MaxHp), "block": int(osty.Block), "alive": bool(osty.IsAlive)}
    elif player.Character.Id.Entry == "NECROBINDER":
        st["osty"] = {"alive": False}
    if with_rng:
        rs = _safe(lambda: player.RunState)
        if rs is not None:
            st["rng"] = _rng(rs, player)
    return st, pots, alive


_PICKUP_ONLY = {"_get_Rarity", "_get_HasUponPickupEffect", "AfterObtained", "_get_CanonicalVars", "IsAllowed",
                "_get_ExtraHoverTips", "_get_HoverTips", "Rarity", "HasUponPickupEffect", "CanonicalVars",
                "ExtraHoverTips", "HoverTips", "_cs_name"}


def _pickup_only(r):
    """只有拾取效果、对战斗无影响的遗物（如 DOWSING_ROD、NEOWS_SACRIFICE）不传给 spire-mentor。"""
    d = set(type(r).__dict__) - {k for k in type(r).__dict__ if k.startswith("__")}
    return bool(d) and d <= _PICKUP_ONLY


def _revives(e):
    return any(p.Id.Entry in ("ILLUSION_POWER", "REATTACH_POWER", "ADAPTABLE_POWER") for p in e.Powers)


def to_wire(cs, player, room_kind="Monster", ascension=0, seed=0):
    rs, ad = lib()
    st, pots, alive = to_headless(cs, player, room_kind)
    cls = _ename(player.Character.Id.Entry).capitalize() if False else None
    char = {"IRONCLAD": "Ironclad", "SILENT": "Silent", "DEFECT": "Defect", "NECROBINDER": "Necrobinder",
            "REGENT": "Regent"}.get(player.Character.Id.Entry)
    if char is None:
        raise Unsupported(f"character {player.Character.Id.Entry}")
    ad.reset_drop_counts()
    try:
        w = ad.translate(st, character=char, seed=seed, ascension=ascension)
    except Exception as e:  # noqa
        raise Unsupported(f"translate: {e}")
    drops = ad.drop_counts()
    if drops:
        reg = ad._registry_power_names()
        bad = [q["id"] for q in st["player_powers"] + [x for e in st["enemies"] + st["dead_enemies"] for x in e["powers"]]
               if q["id"] not in reg and q["id"].removesuffix("_POWER") not in reg]
        rreg = ad._registry_names("relic")
        bad += [r["id"] for r in st["player"]["relics"] if r["id"] not in rreg]
        raise Unsupported(f"dropped {drops} {bad}")
    wp = []
    for p in pots:
        if p is None:
            wp.append(None)
        elif p["id"] in _M["potions"]:
            wp.append(p["id"])
        else:
            raise Unsupported(f"potion {p['id']}")
    w["player"]["potions"] = wp
    w["game_version"] = "v0.111.0"
    return w, alive


def mcts_action(cs, player, acts, room_kind="Monster", ascension=0, sims=1000, threads=1, seed=0, **kw):
    """返回 (我们的动作, 信息)。不支持时抛 Unsupported。"""
    rs, _ = lib()
    w, alive = to_wire(cs, player, room_kind, ascension, seed)
    try:
        s = rs.state_from_dict(w)
    except Exception as e:  # noqa
        raise Unsupported(f"state_from_dict: {str(e)[:200]}")
    r = rs.mcts_recommend(s, sims=sims, threads=threads, seed=seed, **kw)
    best = next((x for x in r["actions"] if x.get("is_best")), None)
    if best is None:
        raise Unsupported("no recommendation")
    try:
        return map_action(best["action"], player, acts, alive), best
    except Unsupported as e:
        # 最优动作在我们这边被挡掉（多为 combat.py 的 MAX_SAME_CARD 防死循环限制）：按 Q 排名取下一个能映射的动作
        for x in r["actions"]:
            if x is best:
                continue
            try:
                return map_action(x["action"], player, acts, alive), dict(x, alt_of=str(e))
            except Unsupported:
                pass
        raise


def map_action(a, player, acts, alive):
    kind = a.get("action")
    if kind == "end_turn":
        for x in acts:
            if x[0] == "end":
                return x
    h = hand(player)
    ti = a.get("target_index")
    tgt = alive[ti] if isinstance(ti, int) and 0 <= ti < len(alive) else None
    if kind == "play":
        card = h[a["card_index"]]
        for x in acts:
            if x[0] == "play" and x[1] is card and (tgt is None or x[2] is tgt or x[2] is None):
                return x
        inacts = any(x[0] == "play" and x[1] is card for x in acts)
        raise Unsupported(f"unmappable play {card.Id.Entry} canplay={_safe(card.CanPlay, None)} inacts={inacts} tgt={tgt is not None}")
    if kind in ("potion", "drink_potion"):
        slots = [p for p in player.PotionSlots if p is not None]   # sts2_rs 把空槽压缩掉了
        pot = slots[a["slot"]]
        for x in acts:
            if x[0] == "potion" and x[1] is pot and (tgt is None or x[2] is tgt or x[2] is None):
                return x
        raise Unsupported(f"unmappable potion {a}")
    raise Unsupported(f"unknown action {a}")


def make_mentor_agent(seed=0, sims=1000, threads=1, fallback_search=True, mentor_rooms=None, **kw):
    """局外 = learned（StrongAgent）；战斗 = spire-mentor MCTS，不支持时回退到 learned-search（或 learned）。"""
    from .strong import StrongAgent

    class MentorAgent(StrongAgent):
        name = "mentor-mcts"

        def __init__(self):
            super().__init__(seed=seed, search=fallback_search, **kw)
            self.sims, self.threads = sims, threads
            self.mentor_rooms = mentor_rooms      # None = 所有战斗；或 {"Boss"} 等
            self.mstats = {"mentor": 0, "fallback": 0, "reasons": {}, "mcts_sec": 0.0}
            self._k = 0

        def combat_action(self, cs, player, acts):
            if not self._in_child and (self.mentor_rooms is None or self.room_kind in self.mentor_rooms):
                import time
                self._k += 1
                t = time.perf_counter()
                try:
                    a, info = mcts_action(cs, player, acts, self.room_kind, getattr(getattr(self, "_run", None), "ascension", 0),
                                       sims=self.sims, threads=self.threads, seed=(seed * 7919 + self._k) & 0xFFFFFFFF)
                    self.mstats["mentor"] += 1
                    if "alt_of" in info:
                        self.mstats["alt"] = self.mstats.get("alt", 0) + 1
                    self.mstats["mcts_sec"] += time.perf_counter() - t
                    return a
                except Unsupported as e:
                    self.mstats["fallback"] += 1
                    r = re.sub(r"\d+", "#", str(e))[:80]
                    self.mstats["reasons"][r] = self.mstats["reasons"].get(r, 0) + 1
            return super().combat_action(cs, player, acts)

    return MentorAgent()
