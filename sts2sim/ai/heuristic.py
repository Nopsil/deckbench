"""启发式 AI：对每个合法动作（卡 × 目标）复制战斗、实际结算一次，用局面估值打分，贪心选最高。
不偷看牌堆：估值只看手牌数量与公开信息。"""
from ..core import LoopAlarm
from .base import Agent, score_delta


class HeuristicAgent(Agent):
    name = "heuristic"

    def __init__(self, threshold=0.05, cost_weight=0.6):
        self.threshold = threshold
        self.cost_weight = cost_weight

    def best_action(self, C):
        acts = C.legal_actions()
        if not acts:
            return None, 0
        best, best_rank, best_s = None, -1e18, 0
        for i, t in acts:
            card = C.player.hand[i]
            paid = C.card_cost(card) or 0
            sim = C.clone()
            ti = None if t is None else C.enemies.index(t)
            try:
                sim.play(i, None if ti is None else sim.enemies[ti])
                s = score_delta(C, sim, paid)
            except LoopAlarm:
                s = 50
            s += card.d.ai.get("bonus", 0)   # mod 作者可在卡表里写 ai: {bonus: N} 提示难以即时估值的牌
            rank = s - self.cost_weight * paid
            if rank > best_rank:
                best, best_rank, best_s = (i, t), rank, s
        return best, best_s

    def play_turn(self, C):
        while C.result is None:
            if C.data.pop("_force_end_turn", False):
                break
            act, s = self.best_action(C)
            if act is None or s <= self.threshold:
                break
            C.play(*act)
