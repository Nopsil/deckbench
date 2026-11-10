"""启发式 AI：对每个合法动作（卡 × 目标）复制战斗、实际结算一次，用局面估值打分，贪心选最高。
不偷看牌堆：估值只看手牌数量与公开信息。"""
from ..core import LoopAlarm
from .. import explain
from .base import Agent, _step, evaluate, resources, score_delta


class HeuristicAgent(Agent):
    name = "heuristic"

    def __init__(self, threshold=0.05, cost_weight=0.6):
        self.threshold = threshold
        self.cost_weight = cost_weight

    def best_action(self, C):
        acts = C.legal_actions()
        if not acts:
            return None, 0
        log = explain.enabled()
        rows = [] if log else None
        base_v = evaluate(C)
        res0 = resources(C)
        paid_of = C._legal_paid
        hand = C.player.hand
        enemies = C.enemies
        best, best_rank, best_s = None, -1e18, 0
        for i, t in acts:
            card = hand[i]
            paid = paid_of[i]
            sim = C.clone()
            ti = None if t is None else enemies.index(t)
            try:
                sim.play(i, None if ti is None else sim.enemies[ti])
                s = score_delta(C, sim, paid, base_v=base_v, res0=res0)
            except LoopAlarm:
                s = 50
            s += card.d.ai.get("bonus", 0)   # mod 作者可在卡表里写 ai: {bonus: N} 提示难以即时估值的牌
            rank = s - self.cost_weight * paid
            if log:
                rows.append(_step(C, "play", card.id, card.name, t, rank, value=s, hand=i))
            if rank > best_rank:
                best, best_rank, best_s = (i, t), rank, s
        if log:
            self._explain_rows = rows
            self._explain_best = best
        return best, best_s

    def _log_play(self, C, act, played):
        rows = getattr(self, "_explain_rows", None)
        if not rows:
            return
        if played and act is not None:
            i, t = act
            card = C.player.hand[i]
            chosen = _step(C, "play", card.id, card.name, t, None, hand=i)
        else:
            chosen = {"kind": "end", "id": "end_turn"}
        explain.publish(explain.from_steps(rows, chosen, turn=C.turn, threshold=self.threshold))

    def play_turn(self, C):
        while C.result is None:
            if C.data.pop("_force_end_turn", False):
                break
            act, s = self.best_action(C)
            if act is None or s <= self.threshold:
                if explain.enabled():
                    self._log_play(C, act, False)
                break
            if explain.enabled():
                self._log_play(C, act, True)
            C.play(*act)
