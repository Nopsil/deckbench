"""PlannerAgent：整回合规划的出牌 AI（不需要 fork，Windows 可用；也是搜索 AI 的推演策略）。

旧的启发式每一步只挑“分数/费用”最高的单张牌，常见毛病：该挡不挡、格挡溢出、打会复活的幻影/小怪、
对 Slippery（每段伤害封顶 1）照常估伤害。这里每个决策点枚举本回合手牌的可行组合（能量预算内），
用一个近似模型给“打完这些牌、敌人行动之后”的局面打分，选最优组合里优先级最高的那张先打，打完重新规划
（抽牌/生成牌之后手牌会变）。

近似模型（等效 HP 量纲）：
  * 本回合掉血 = max(0, 未被击杀的敌人来袭伤害 − 格挡)（虚弱/击杀会减少来袭）；
  * 伤害价值 k = 平均来袭 / 我方每回合输出（缩短战斗省下的血）；击杀奖励 = 省下它今后的伤害；
  * 小怪（MINION，首领活着）和幻影（ILLUSION，会复活）的伤害不计“推进战斗”；
  * Slippery：每段先剥一层、只造成 1 点；
  * 易伤/力量在同一组合里对之后的攻击生效；能力/抽牌/能量/负面效果用与启发式相同的估值。
"""
from ..rt.boot import game as G
from .agents import _name, dvar, card_cost, PLAY_ADJUST
from .combat import alive_enemies, cm
from .strong import StrongAgent

MAX_NODES = 1500


def _powers(c):
    try:
        return {p.Id.Entry: float(p.Amount) for p in c.Powers}
    except Exception:  # noqa
        return {}


class PlannerMixin:
    """可混入任何 HeuristicAgent 子类：提供 plan_action(cs, player, acts)。"""

    # ---------- 每场战斗的统计 ----------
    def _cstats(self, cs, player):
        st = getattr(self, "_pl_stats", None)
        if st is None or st["cs"] is not cs:
            en = list(cs.Enemies)
            st = self._pl_stats = {"cs": cs, "round": -1, "inc": [], "ehp0": None, "dealt": []}
        if st["round"] != cs.RoundNumber:
            st["round"] = cs.RoundNumber
            tot = sum(max(0, e.CurrentHp) for e in cs.Enemies)
            if st["ehp0"] is not None:
                st["dealt"].append(max(0, st["ehp0"] - tot))
            st["ehp0"] = tot
            st["inc"].append(sum(self._enemy_incoming(e, player.Creature) for e in alive_enemies(cs)))
        return st

    def _dpt(self, st, player):
        try:
            emax = int(player.PlayerCombatState.MaxEnergy)
        except Exception:  # noqa
            emax = 3
        prior = 4.0 * emax
        d = st["dealt"]
        if not d:
            return prior
        obs = sum(d) / len(d)
        w = min(1.0, len(d) / 3.0)
        return max(5.0, (1 - w) * prior + w * obs)

    # ---------- 单张牌的效果（每个决策点缓存） ----------
    def _card_info(self, card, cs, player, ctx):
        key = id(card)
        ci = ctx["cards"].get(key)
        if ci is not None:
            return ci
        tt = card.TargetType
        en = ctx["en"]
        per = {}
        if tt == G.TargetType.AnyEnemy:
            tgts = [e for e in en if card.IsValidTarget(e)]
        else:
            tgts = [None]
        pv_t = {}
        for t in (en if tt == G.TargetType.AllEnemies else tgts):
            d, h, b = self._preview(card, t)
            pv_t[id(t) if t is not None else None] = (d, h, b)
        if not pv_t:
            pv_t[None] = self._preview(card, None)
        anyv = next(iter(pv_t.values()))
        v = lambda k: dvar(card, k)  # noqa
        ci = {"card": card, "cost": card_cost(card), "tt": tt, "tgts": tgts, "pv": pv_t, "blk": anyv[2],
              "energy": v("Energy"), "cards": v("Cards"), "type": _name(card.Type),
              "vuln": v("VulnerablePower"), "weak": v("WeakPower"), "str": v("StrengthPower") if _name(card.Type) != "Power" else 0.0}
        try:
            ci["xcost"] = bool(card.EnergyCost.CostsX)
        except Exception:  # noqa
            ci["xcost"] = False
        if ci["xcost"]:
            ci["cost"] = ctx["energy"]
        ci["misc"] = self._misc_value(card, cs, player, ctx, ci)
        ctx["cards"][key] = ci
        return ci

    def _misc_value(self, card, cs, player, ctx, ci):
        """伤害/格挡/易伤/虚弱以外的价值（与 HeuristicAgent._score_play 同一套估值，按剩余回合缩放）。"""
        tn = ci["type"]
        v = lambda key: dvar(card, key)  # noqa
        T = ctx["T"]
        fl = min(3.0, T)
        k = ctx["k"]
        s = 0.0
        if tn == "Power":
            s += (5.0 if cs.RoundNumber <= 2 else 3.0 if cs.RoundNumber <= 4 else 1.5) * min(2.0, 0.3 + T / 3.0)
        s += (v("StrengthPower") * 2.0 + v("DexterityPower") * 2.0 + v("FocusPower") * 2.5) * fl
        s += v("PoisonPower") * k * 1.6 + v("DoomPower") * 0.8 * k + v("PlatingPower") * 1.2 * fl
        s += v("Cards") * 1.6 + v("Summon") * 1.2 + v("Forge") * 0.8 + v("Stars") * 1.2
        s += v("Shivs") * 3.0 * k + v("VigorPower") * 0.8 * k + v("ThornsPower") * 0.8 * fl
        s -= v("HpLoss") * 0.9
        if v("StrengthLoss"):
            s += v("StrengthLoss") * 1.2 * fl
        if ci["energy"]:
            s += 0.3 * ci["energy"]   # 能量本身在预算里体现，这里只给一点“灵活性”
        adj = PLAY_ADJUST.get(card.Id.Entry)
        if adj is not None:
            t = ci["tgts"][0] if ci["tgts"] else None
            try:
                s += adj(self, card, t, cs, player, ctx)
            except Exception:  # noqa
                pass
        d0 = max(x[0] for x in ci["pv"].values())
        if s == 0.0 and d0 <= 0 and ci["blk"] <= 0 and not ci["vuln"] and not ci["weak"]:
            s = 1.5 if tn in ("Skill", "Power") else 0.3   # 看不出效果的牌：略正
        if tn in ("Status", "Curse"):
            s = 0.4
        s += self.card_value(card) * 0.05
        return s

    # ---------- 组合估值 ----------
    def _eval_plan(self, plan, ctx):
        """plan: [(ci, target)]，按执行顺序。返回 (价值, 目标列表)。"""
        en = ctx["en"]
        hp = {id(e): float(e.CurrentHp) for e in en}
        blk = {id(e): float(e.Block) for e in en}
        slip = dict(ctx["slip"])
        vul = {id(e): ctx["vul"][id(e)] for e in en}
        weak = {id(e): ctx["weak0"][id(e)] for e in en}
        strg = 0.0
        my_blk = 0.0
        val = 0.0
        tg_out = []
        for ci, t in plan:
            # 目标选择（单体攻击：在剩余敌人里挑边际价值最高的）
            if ci["tt"] == G.TargetType.AnyEnemy:
                if t is None:
                    best, bv = None, None
                    for e in ci["tgts"]:
                        if hp[id(e)] <= 0:
                            continue
                        g = self._hit_value(ci, e, ctx, hp, blk, slip, vul, strg, dry=True)
                        if ci["vuln"] and not vul[id(e)]:
                            g += 0.5 * ctx["k"] * ctx["dpt"] * 0.5 * (1.0 if ctx["prio"][id(e)] > 0 else 0.3)
                        if ci["weak"] and not weak[id(e)]:
                            g += 0.25 * ctx["inc"][id(e)]
                        if bv is None or g > bv:
                            best, bv = e, g
                    t = best if best is not None else (ci["tgts"][0] if ci["tgts"] else None)
                tg_out.append(t)
                targets = [t] if t is not None else []
            elif ci["tt"] == G.TargetType.AllEnemies:
                tg_out.append(None)
                targets = [e for e in en if hp[id(e)] > 0]
            elif ci["tt"] == G.TargetType.RandomEnemy:
                tg_out.append(None)
                alive = [e for e in en if hp[id(e)] > 0]
                targets = alive[:1]
            else:
                tg_out.append(t)
                targets = []
            d_any = max(x[0] for x in ci["pv"].values())
            if d_any > 0:
                for e in targets:
                    val += self._hit_value(ci, e, ctx, hp, blk, slip, vul, strg, dry=False)
            for e in targets:
                if ci["vuln"] and not vul[id(e)]:
                    vul[id(e)] = ci["vuln"]
                    val += min(ci["vuln"], 3) * 0.5 * ctx["k"] * ctx["dpt"] * 0.35 * (1.0 if ctx["prio"][id(e)] > 0 else 0.3)
                if ci["weak"]:
                    if not weak[id(e)]:
                        weak[id(e)] = ci["weak"]
                    val += min(ci["weak"], 3) * 0.25 * ctx["inc_avg_e"].get(id(e), 0.0) * 0.6
            if ci["tt"] not in (G.TargetType.AnyEnemy, G.TargetType.AllEnemies, G.TargetType.RandomEnemy):
                if ci["vuln"] or ci["weak"]:
                    for e in en:
                        if hp[id(e)] > 0:
                            if ci["vuln"] and not vul[id(e)]:
                                vul[id(e)] = ci["vuln"]
                                val += min(ci["vuln"], 3) * 0.5 * ctx["k"] * ctx["dpt"] * 0.25
                            if ci["weak"] and not weak[id(e)]:
                                weak[id(e)] = ci["weak"]
                                val += min(ci["weak"], 3) * 0.25 * ctx["inc_avg_e"].get(id(e), 0.0) * 0.6
            strg += ci["str"]
            my_blk += ci["blk"]
            val += ci["misc"]
        # 敌方回合：未死敌人的来袭（本回合新挂的虚弱 ×0.75）
        inc = 0.0
        for e in en:
            if hp[id(e)] > 0:
                x = ctx["inc"][id(e)]
                if weak[id(e)] and not ctx["weak0"][id(e)]:
                    x *= 0.75
                inc += x
        cur_blk = ctx["blk0"]
        need = max(0.0, inc - cur_blk)
        loss = max(0.0, need - my_blk)
        val -= loss * ctx["hpw"]
        val += max(0.0, my_blk - need) * ctx["over_blk"]
        return val, tg_out

    def _hit_value(self, ci, e, ctx, hp, blk, slip, vul, strg, dry):
        i = id(e)
        if hp[i] <= 0:
            return 0.0
        pv = ci["pv"].get(i) or ci["pv"].get(None) or (0.0, 1.0, 0.0)
        d, h = pv[0], pv[1]
        if d <= 0:
            return 0.0
        if strg:
            d += strg * (1.5 if (vul[i] and not ctx["vul"][i]) or ctx["vul"][i] else 1.0)
        if vul[i] and not ctx["vul"][i]:
            d *= 1.5
        h = int(max(1, round(h)))
        s = slip.get(i, 0)
        tot = 0.0
        for _ in range(h):
            if s > 0:
                tot += 1.0
                s -= 1
            else:
                tot += d
        b = blk[i]
        through = max(0.0, tot - b)
        nb = max(0.0, b - tot)
        new_hp = hp[i] - through
        pr = ctx["prio"][i]
        k = ctx["k"]
        v = 0.0
        if new_hp <= 0:
            v += ctx["inc"][i] + 2.0     # 本回合不再挨它打
            v += (hp[i] * k + ctx["inc_avg_e"].get(i, 0.0) * 0.8) * pr
            v += 1.0
        else:
            v += through * k * pr + min(tot, b) * 0.3 * k * pr
        v += 0.3 * h * k * pr
        if slip.get(i, 0):
            v += min(h, slip[i]) * 2.0 * pr
        if not dry:
            hp[i] = new_hp
            blk[i] = nb
            if slip.get(i, 0):
                slip[i] = s
        return v

    # ---------- 枚举 ----------
    def _priority(self, ci):
        """同一组合内的执行顺序：能量/抽牌 → 能力 → 力量/易伤/虚弱 → 攻击 → 格挡。"""
        tn = ci["type"]
        if ci["energy"] > 0 and ci["cost"] == 0:
            return 0
        if ci["cards"] > 0:
            return 1
        if tn == "Power":
            return 2
        if ci["str"] or ci["vuln"] or ci["weak"]:
            return 3
        if max(x[0] for x in ci["pv"].values()) > 0:
            return 4
        return 5

    def plan_action(self, cs, player, acts):
        pc = player.Creature
        en = alive_enemies(cs)
        if not en:
            return ("end",) if acts[-1][0] == "end" else acts[-1]
        st = self._cstats(cs, player)
        inc = {id(e): float(self._enemy_incoming(e, pc)) for e in en}
        hist = st["inc"]
        avg_inc = max(4.0, sum(hist) / len(hist)) if hist else 4.0
        dpt = self._dpt(st, player)
        leaders = [e for e in en if "MINION_POWER" not in _powers(e)]
        prio, slip, vul, weak0 = {}, {}, {}, {}
        for e in en:
            pw = _powers(e)
            p = 1.0
            if "ILLUSION_POWER" in pw:
                p = 0.0
            elif "MINION_POWER" in pw and leaders:
                p = 0.25
            prio[id(e)] = p
            slip[id(e)] = int(pw.get("SLIPPERY_POWER", 0))
            vul[id(e)] = pw.get("VULNERABLE_POWER", 0.0)
            weak0[id(e)] = pw.get("WEAK_POWER", 0.0)
        ehp = float(sum((e.CurrentHp + e.Block) * prio[id(e)] for e in en)) or 1.0
        T = max(1.0, ehp / dpt)
        k = max(0.15, min(1.6, avg_inc * 0.9 / dpt))
        inc_avg_e = {}
        n_att = max(1, sum(1 for e in en if inc[id(e)] > 0))
        for e in en:
            inc_avg_e[id(e)] = max(inc[id(e)], avg_inc / max(1, len(en)) if prio[id(e)] > 0 else inc[id(e)])
        try:
            energy = int(player.PlayerCombatState.Energy)
        except Exception:  # noqa
            energy = 3
        pws = _powers(pc)
        over = 0.05
        if "BARRICADE_POWER" in pws or "BLUR_POWER" in pws:
            over = 0.5
        ctx = {"en": en, "inc": inc, "k": k, "dpt": dpt, "T": T, "prio": prio, "slip": slip, "vul": vul,
               "weak0": weak0, "inc_avg_e": inc_avg_e, "blk0": float(pc.Block), "hpw": 1.0, "over_blk": over,
               "cards": {}, "energy": energy, "need": max(0, sum(inc.values()) - pc.Block), "ehp": ehp,
               "avg_inc": avg_inc, "slip_raw": slip}
        # 低血量：掉血更痛（避免被打死）
        hp = pc.CurrentHp
        need = ctx["need"]
        if need >= hp:
            ctx["hpw"] = 3.0
        elif need >= hp * 0.5:
            ctx["hpw"] = 1.5
        # 候选牌（去重：同 id/升级/费用 的牌等价）
        plays = [a for a in acts if a[0] == "play"]
        groups = {}
        for a in plays:
            c = a[1]
            key = (c.Id.Entry, bool(getattr(c, "IsUpgraded", False)), card_cost(c))
            g = groups.setdefault(key, {"cards": [], "acts": {}})
            if c not in g["cards"]:
                g["cards"].append(c)
            g["acts"].setdefault(id(c), []).append(a)
        items = []
        for key, g in groups.items():
            try:
                ci = self._card_info(g["cards"][0], cs, player, ctx)
            except Exception:  # noqa
                continue
            items.append((ci, len(g["cards"]), g))
        items.sort(key=lambda x: self._priority(x[0]))
        best = {"v": 0.0, "plan": []}
        # 空组合（直接结束回合）
        v0, _ = self._eval_plan([], ctx)
        best["v"] = v0
        nodes = [0]

        def dfs(i, energy_left, chosen):
            if nodes[0] > MAX_NODES:
                return
            nodes[0] += 1
            if chosen:
                plan = sorted(chosen, key=lambda x: self._priority(x[0]))
                v, tg = self._eval_plan([(c, None) for c, _ in plan], ctx)
                if v > best["v"] + 1e-6:
                    best["v"] = v
                    best["plan"] = [(c, t) for (c, _), t in zip(plan, tg)]
            for j in range(i, len(items)):
                ci, cnt, g = items[j]
                used = sum(1 for c, _ in chosen if c is ci)
                if used >= cnt:
                    continue
                cost = ci["cost"]
                if cost > energy_left:
                    continue
                chosen.append((ci, g))
                dfs(j, energy_left - cost + ci["energy"], chosen)
                chosen.pop()
        dfs(0, energy, [])
        # 药水：危险时/精英首领开局（沿用启发式规则），在规划之前用
        for a in acts:
            if a[0] == "potion" and self._score_potion(a[1], a[2], cs, player, ctx["need"] - best_block(best["plan"]), hp) >= 0.9:
                return a
        if not best["plan"]:
            return acts[-1]
        ci, t = best["plan"][0]
        # 找对应动作
        for a in plays:
            c = a[1]
            if (c.Id.Entry, bool(getattr(c, "IsUpgraded", False)), card_cost(c)) == \
                    (ci["card"].Id.Entry, bool(getattr(ci["card"], "IsUpgraded", False)), ci["cost"] if not ci["xcost"] else card_cost(c)):
                if t is None or a[2] is t:
                    return a
        for a in plays:
            if a[1] is ci["card"]:
                return a
        return acts[-1]


def best_block(plan):
    return sum(ci["blk"] for ci, _ in plan)


class PlannerAgent(PlannerMixin, StrongAgent):
    """局外 = StrongAgent；局内 = 整回合规划（无 fork）。search=True 时精英/首领等关键决策点仍用 fork 前瞻，
    推演策略换成规划器。"""
    name = "planner"

    def __init__(self, seed=0, search=False, **kw):
        super().__init__(seed=seed, search=search, **kw)

    def combat_action(self, cs, player, acts):
        if len(acts) <= 1:
            return acts[0]
        if self.search and not self._in_child and (not self.selective or self._consequential(cs, player, acts)):
            from .search import SearchAgent
            return SearchAgent.combat_action(self, cs, player, acts)
        return self.plan_action(cs, player, acts)

    def rollout_action(self, cs, player, acts):
        return self.plan_action(cs, player, acts)
