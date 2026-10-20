"""战斗内前瞻搜索：用 os.fork() 把整个游戏进程当作“状态快照”。

游戏状态里有大量类级单例和闭包，没法 deepcopy；但 fork 出的子进程自带一份完整拷贝（写时复制），
在子进程里试走一个候选动作，再用启发式把这回合打完、让敌人行动，然后给局面打分，
最后通过管道把分数传回父进程。父进程的状态不受影响。

近似：子进程沿用同一个随机数状态，所以前瞻能看到本回合的抽牌结果和敌人的随机行为（轻微“透视”）。
这是有意为之的取舍，报告中已列出。
"""
import os
import struct

from ..rt.boot import game as G
from .agents import HeuristicAgent, _name, card_cost, end_turn_hand_damage
from .combat import alive_enemies, legal_actions, execute, cm

_F = struct.Struct("d")


# Mod 可注册的敌方能力估值：Id.Entry -> f(层数, 敌人, k, fight_len) -> 价值（HP 量纲）
POWER_VALUE = {}


class SearchAgent(HeuristicAgent):
    name = "search"

    def __init__(self, seed=0, width=6, depth=1, **kw):
        super().__init__(seed=seed, **kw)
        self.width = width          # 每个决策点最多展开的候选数（按启发式分数取前 N，外加“结束回合”）
        self.depth = depth          # 前瞻的回合数（1 = 打完本回合 + 敌人回合）
        self.forks = 0
        self._in_child = False

    # ---------- 局面估值 ----------
    def _value(self, cs, player, base):
        pc = player.Creature
        en = alive_enemies(cs)
        if pc.IsDead:
            # 死了也区分“差一点打赢”和“完全打不动”（整场推演时有用）
            return -10000.0 - sum(e.CurrentHp + e.Block for e in en) * 2.0
        hp = pc.CurrentHp
        pot = sum(1 for x in player.PotionSlots if x is not None)
        v = hp * 1.0 + (pc.MaxHp - base["maxhp"]) * 1.2 + (pot - base["potions"]) * 6.0
        if not en:
            return 1000.0 + v
        k, fl = base["k"], base["fight_len"]
        for e in en:
            v -= (e.CurrentHp + e.Block * 0.5) * k
            v -= base["avg_inc"] * 0.6 / max(1, len(en))
            for pw in e.Powers:
                a = float(pw.Amount)
                ent = pw.Id.Entry
                if ent in POWER_VALUE:
                    v += POWER_VALUE[ent](a, e, k, fl)
                elif ent in ("POISON_POWER", "DOOM_POWER"):
                    v += min(a, e.CurrentHp) * k * (1.0 if ent == "POISON_POWER" else 0.8)
                elif pw.TypeForCurrentAmount == G.PowerType.Debuff:
                    v += min(abs(a), 4.0) * 1.2 * fl
                elif ent == "STRENGTH_POWER":
                    v -= a * 1.5 * fl
        v += base["dead_bonus"] * (base["n_enemies"] - len(en))
        for pw in pc.Powers:
            a = float(pw.Amount)
            if pw.TypeForCurrentAmount == G.PowerType.Debuff:
                v -= min(abs(a), 4.0) * 1.0 * fl
            else:
                v += min(abs(a), 6.0) * 1.5 * fl
        v += pc.Block * 0.3
        return v

    def _base(self, cs, player):
        en = alive_enemies(cs)
        pc = player.Creature
        inc = sum(self._enemy_incoming(e, pc) for e in en)
        ehp = float(sum(e.CurrentHp + e.Block for e in en)) or 1.0
        avg_inc = max(5.0, float(inc), 4.0 + 2.0 * cs.RoundNumber)
        return {"maxhp": pc.MaxHp, "potions": sum(1 for x in player.PotionSlots if x is not None),
                "k": max(0.25, min(1.3, avg_inc * 1.6 / ehp)), "fight_len": min(2.5, ehp / 35.0 + 0.2),
                "avg_inc": avg_inc, "n_enemies": len(en), "dead_bonus": avg_inc * 0.5}

    # ---------- 子进程里的推演 ----------
    def _rollout(self, cs, player, first, base):
        r0 = cs.RoundNumber
        execute(first, cs, player)
        n = 0
        cap = 200 if self.depth < 20 else 1500
        while cm().IsInProgress and not player.Creature.IsDead and n < cap:
            if cs.RoundNumber >= r0 + self.depth:
                break
            acts = legal_actions(cs, player)
            if not acts:
                break
            a = self.rollout_action(cs, player, acts)
            if not execute(a, cs, player) and a[0] != "end":
                execute(("end",), cs, player)
            n += 1
        return self._value(cs, player, base)

    def _eval_fork(self, cs, player, act, base):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:   # 子进程
            os.close(r)
            val = -5000.0
            try:
                self._in_child = True
                val = self._rollout(cs, player, act, base)
            except BaseException:  # noqa
                try:
                    val = self._value(cs, player, base)
                except BaseException:  # noqa
                    pass
            try:
                os.write(w, _F.pack(val))
            finally:
                os._exit(0)
        os.close(w)
        data = b""
        while len(data) < 8:
            chunk = os.read(r, 8 - len(data))
            if not chunk:
                break
            data += chunk
        os.close(r)
        os.waitpid(pid, 0)
        self.forks += 1
        return _F.unpack(data)[0] if len(data) == 8 else -5000.0

    # ---------- 决策 ----------
    def rollout_action(self, cs, player, acts):
        """推演策略（子类可换成更强的无 fork 策略，如 PlannerAgent.plan_action）。"""
        return HeuristicAgent.combat_action(self, cs, player, acts)

    def combat_action(self, cs, player, acts):
        if self._in_child or len(acts) <= 1:
            return self.rollout_action(cs, player, acts)
        heur = self.rollout_action(cs, player, acts)
        # 候选去重（同名同升级同费用同目标的牌等价）
        seen, cands = set(), []
        for a in acts:
            if a[0] == "end":
                key = ("end",)
            else:
                t = a[2]
                key = (a[0], a[1].Id.Entry, getattr(a[1], "IsUpgraded", False),
                       card_cost(a[1]) if a[0] == "play" else 0, id(t) if t is not None else None)
            if key not in seen:
                seen.add(key)
                cands.append(a)
        if len(cands) <= 1:
            return cands[0]
        # 只展开启发式排序前 width 个（药水只在启发式想用时才展开）+ 结束回合 + 启发式首选
        ctx_scores = []
        for a in cands:
            if a[0] == "play":
                try:
                    s = self._quick_score(a, cs, player)
                except Exception:  # noqa
                    s = 0.0
                ctx_scores.append((s, a))
        ctx_scores.sort(key=lambda x: -x[0])
        pool = [a for _, a in ctx_scores[: self.width]]
        if heur not in pool:
            pool.append(heur)
        if heur[0] != "potion":
            for a in cands:
                if a[0] == "potion" and self._score_potion(a[1], a[2], cs, player, 0, player.Creature.CurrentHp) > 0:
                    pool.append(a)
                    break
        endact = acts[-1]
        if endact not in pool:
            pool.append(endact)
        base = self._base(cs, player)
        best, bv = heur, None
        for a in pool:
            v = self._eval_fork(cs, player, a, base)
            if a is heur:
                v += 0.25      # 平分时偏向启发式首选
            if bv is None or v > bv:
                best, bv = a, v
        return best

    def _quick_score(self, a, cs, player):
        pc = player.Creature
        en = alive_enemies(cs)
        inc = {id(e): self._enemy_incoming(e, pc) for e in en}
        incoming = sum(inc.values())
        ehp = float(sum(e.CurrentHp + e.Block for e in en)) or 1.0
        avg_inc = max(4.0, float(incoming))
        ctx = {"inc": inc, "need": max(0, incoming + end_turn_hand_damage(player) - pc.Block), "k": max(0.2, min(1.3, avg_inc * 1.6 / ehp)),
               "ehp": ehp, "avg_inc": avg_inc, "slip": {}}
        return self._score_play(a[1], a[2], cs, player, ctx)
