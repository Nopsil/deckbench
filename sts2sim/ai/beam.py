"""单回合束搜索 AI：在本回合内搜索出牌序列（宽度 width、深度 depth），
按序列结束时的局面估值选最好的序列，执行它的第一步，然后重新搜索。
比启发式慢约一个数量级，用来对照启发式 AI 是否打得太笨。日后可在这里换成 MCTS。"""
from ..core import LoopAlarm
from .. import explain
from .base import Agent, _step, evaluate, resources


class BeamAgent(Agent):
    name = "beam"

    def __init__(self, width=4, depth=4):
        self.width = width
        self.depth = depth

    def _expand(self, C):
        acts = C.legal_actions()
        out = []
        hand = C.player.hand
        enemies = C.enemies
        paid_of = C._legal_paid
        plays = C.data.get("_plays", 0) + 1
        paid0 = C.data.get("_paid", 0)
        bonus0 = C.data.get("_bonus", 0)
        for i, t in acts:
            card = hand[i]
            sim = C.clone()
            sim.data["_plays"] = plays
            sim.data["_paid"] = paid0 + paid_of[i]
            ti = None if t is None else enemies.index(t)
            try:
                sim.play(i, None if ti is None else sim.enemies[ti])
            except LoopAlarm:
                sim.data["_loopish"] = True
            sim.data["_bonus"] = bonus0 + card.d.ai.get("bonus", 0)
            out.append(((i, t), sim))
        return out

    def _v(self, C0, n0, e0, sim):
        n1, e1 = resources(sim)
        return evaluate(sim) + 1.5 * (n1 - n0 + sim.data.get("_plays", 0)) + 2.0 * (e1 - e0 + sim.data.get("_paid", 0)) + sim.data.get("_bonus", 0)

    def best_action(self, C):
        n0, e0 = resources(C)
        base_v = evaluate(C)
        first = self._expand(C)
        log = explain.enabled()
        if not first:
            if log:
                self._explain_rows = []
                self._explain_best = None
            return None, 0
        beam = []
        best_v, best_a = -1e18, None
        best_for = {} if log else None
        for a, sim in first:
            v = self._v(C, n0, e0, sim) + (50 if sim.data.get("_loopish") else 0)
            beam.append((v, a, sim))
            if v > best_v:
                best_v, best_a = v, a
            if log:
                best_for[a] = v
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
                    if log and v > best_for.get(a0, -1e18):
                        best_for[a0] = v
            if not nb:
                break
            beam = nb
        if log:
            rows = []
            for a, v in best_for.items():
                i, t = a
                card = C.player.hand[i]
                rows.append(_step(C, "play", card.id, card.name, t, v - base_v, hand=i))
            self._explain_rows = rows
            self._explain_best = best_a
        return best_a, best_v - base_v

    def _log_play(self, C, act, played):
        rows = getattr(self, "_explain_rows", None)
        if not rows and not played:
            return
        if played and act is not None:
            i, t = act
            card = C.player.hand[i]
            chosen = _step(C, "play", card.id, card.name, t, None, hand=i)
        else:
            chosen = {"kind": "end", "id": "end_turn"}
        explain.publish(explain.from_steps(rows or [], chosen, turn=C.turn, threshold=0.05))

    def play_turn(self, C):
        C.data["_plays"] = 0
        C.data["_paid"] = 0
        C.data["_bonus"] = 0
        while C.result is None:
            if C.data.pop("_force_end_turn", False):
                break
            a, s = self.best_action(C)
            if a is None or s <= 0.05:
                if explain.enabled():
                    self._log_play(C, a, False)
                break
            if explain.enabled():
                self._log_play(C, a, True)
            C.play(*a)
        C.data.pop("_plays", None)
        C.data.pop("_paid", None)
        C.data.pop("_bonus", None)
