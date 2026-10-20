"""单回合束搜索 AI：在本回合内搜索出牌序列（宽度 width、深度 depth），
按序列结束时的局面估值选最好的序列，执行它的第一步，然后重新搜索。
比启发式慢约一个数量级，用来对照启发式 AI 是否打得太笨。日后可在这里换成 MCTS。"""
from ..core import LoopAlarm
from .base import Agent, evaluate, resources


class BeamAgent(Agent):
    name = "beam"

    def __init__(self, width=4, depth=4):
        self.width = width
        self.depth = depth

    def _expand(self, C):
        out = []
        for i, t in C.legal_actions():
            sim = C.clone()
            sim.data["_plays"] = C.data.get("_plays", 0) + 1
            sim.data["_paid"] = C.data.get("_paid", 0) + (C.card_cost(C.player.hand[i]) or 0)
            ti = None if t is None else C.enemies.index(t)
            try:
                sim.play(i, None if ti is None else sim.enemies[ti])
            except LoopAlarm:
                sim.data["_loopish"] = True
            sim.data["_bonus"] = C.data.get("_bonus", 0) + C.player.hand[i].d.ai.get("bonus", 0)
            out.append(((i, t), sim))
        return out

    def _v(self, C0, n0, e0, sim):
        n1, e1 = resources(sim)
        return evaluate(sim) + 1.5 * (n1 - n0 + sim.data.get("_plays", 0)) + 2.0 * (e1 - e0 + sim.data.get("_paid", 0)) + sim.data.get("_bonus", 0)

    def best_action(self, C):
        n0, e0 = resources(C)
        base_v = evaluate(C)
        first = self._expand(C)
        if not first:
            return None, 0
        beam = []
        best_v, best_a = -1e18, None
        for a, sim in first:
            v = self._v(C, n0, e0, sim) + (50 if sim.data.get("_loopish") else 0)
            beam.append((v, a, sim))
            if v > best_v:
                best_v, best_a = v, a
        for _ in range(self.depth - 1):
            beam.sort(key=lambda x: -x[0])
            beam = beam[: self.width]
            nb = []
            for v0, a0, s0 in beam:
                if s0.result is not None or s0.data.get("_force_end_turn") or s0.data.get("_loopish"):
                    continue
                for _a, s1 in self._expand(s0):
                    v = self._v(C, n0, e0, s1)
                    nb.append((v, a0, s1))
                    if v > best_v:
                        best_v, best_a = v, a0
            if not nb:
                break
            beam = nb
        return best_a, best_v - base_v

    def play_turn(self, C):
        C.data["_plays"] = 0
        C.data["_paid"] = 0
        C.data["_bonus"] = 0
        while C.result is None:
            if C.data.pop("_force_end_turn", False):
                break
            a, s = self.best_action(C)
            if a is None or s <= 0.05:
                break
            C.play(*a)
        C.data.pop("_plays", None)
        C.data.pop("_paid", None)
        C.data.pop("_bonus", None)
