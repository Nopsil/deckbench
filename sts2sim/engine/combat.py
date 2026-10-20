"""战斗驱动：在真实 CombatManager 回合循环之上，向 agent 暴露合法动作并执行。

动作（元组）：
  ("play", card, target)    出牌（target 为 Creature 或 None），走 CardModel.TryManualPlay → PlayCardAction
  ("potion", potion, target) 使用药水，走 PotionModel.EnqueueManualUse → UsePotionAction
  ("end",)                  结束回合，走 EndPlayerTurnAction → PlayerCmd.EndTurn → 敌方回合 → 下一回合开始
"""
from ..rt.boot import game as G

MAX_ACTIONS_PER_TURN = 150
MAX_ROUNDS = 80
MAX_SAME_CARD = 12


class CombatStats:
    __slots__ = ("rounds", "cards_played", "hp_before", "hp_after", "won", "loop_alarm")

    def __init__(self):
        self.rounds = 0
        self.cards_played = []
        self.hp_before = 0
        self.hp_after = 0
        self.won = False
        self.loop_alarm = False


def cm():
    return G.CombatManager.Instance


def hand(player):
    return list(G.PileType.Hand.GetPile(player).Cards)


def alive_enemies(cs):
    return [e for e in cs.Enemies if e.IsAlive]


def is_play_phase(player):
    """v0.111 起出牌阶段按玩家记录（PlayerCombatState.Phase），CombatManager.IsPlayPhase 已删除。"""
    pcs = player.PlayerCombatState
    return pcs is not None and pcs.Phase == G.PlayerTurnPhase.Play and not cm().EndingPlayerTurnPhaseOne


def card_targets(card, cs, player):
    tt = card.TargetType
    TT = G.TargetType
    if tt == TT.AnyEnemy:
        return [e for e in alive_enemies(cs) if card.IsValidTarget(e)]
    if tt == TT.AnyAlly:
        return [c for c in cs.PlayerCreatures if c.IsAlive and c is not player.Creature and card.IsValidTarget(c)]
    return [None]


def potion_targets(potion, cs, player):
    TT = G.TargetType
    tt = potion.TargetType
    if tt == TT.AnyEnemy:
        return alive_enemies(cs)
    if tt in (TT.AnyPlayer, TT.Self):
        return [player.Creature]
    if tt == TT.AnyAlly:
        return [c for c in cs.PlayerCreatures if c.IsAlive and c is not player.Creature] or [None]
    return [None]


def legal_actions(cs, player, include_potions=True):
    acts = []
    if not cm().IsInProgress or not is_play_phase(player):
        return acts
    for c in hand(player):
        try:
            if not c.CanPlay():
                continue
        except Exception:  # noqa
            continue
        for t in card_targets(c, cs, player):
            acts.append(("play", c, t))
    if include_potions:
        for p in list(player.Potions):
            if p.Usage in (G.PotionUsage.CombatOnly, G.PotionUsage.AnyTime) and not p.IsQueued:
                for t in potion_targets(p, cs, player):
                    acts.append(("potion", p, t))
    acts.append(("end",))
    return acts


def execute(action, cs, player):
    kind = action[0]
    if kind == "play":
        return action[1].TryManualPlay(action[2])
    if kind == "potion":
        action[1].EnqueueManualUse(action[2])
        return True
    if kind == "end":
        G.RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(G.EndPlayerTurnAction(player, player.PlayerCombatState.TurnNumber))
        # v0.111：NEndTurnButton 用玩家自己的 TurnNumber（额外回合时 ≠ RoundNumber，旧写法会被忽略→死循环）
        return True
    raise ValueError(action)


def run_combat(room, player, agent, stats=None):
    """驱动一场已开始（room.Enter 已调用）的战斗直到结束。返回 CombatStats。"""
    st = stats or CombatStats()
    cs = room.CombatState
    st.hp_before = player.Creature.CurrentHp
    agent.on_combat_start(cs, player, room)
    n_in_turn, last_round = 0, cs.RoundNumber
    per_card = {}   # 同一张牌本回合打出次数：0 费自抽循环（如 逃脱计划 在抽牌堆/弃牌堆为空时抽回自己）在原版里也是合法的无限循环，
                    # 玩家会主动停手；这里每张牌每回合最多打 MAX_SAME_CARD 次。
    stuck_ends, last_turn = 0, None
    while cm().IsInProgress and not player.Creature.IsDead:
        if cs.RoundNumber != last_round:
            last_round, n_in_turn = cs.RoundNumber, 0
            per_card = {}
        if cs.RoundNumber > MAX_ROUNDS:
            st.loop_alarm = "rounds"
            break   # 超长战斗按失败处理（报告中计入 loop_alarm）
        acts = legal_actions(cs, player)
        if not acts:
            break
        if per_card:
            acts = [x for x in acts if x[0] != "play" or per_card.get(id(x[1]), 0) < MAX_SAME_CARD]
        if n_in_turn >= MAX_ACTIONS_PER_TURN:
            st.loop_alarm = "actions:" + ",".join(st.cards_played[-6:])
            a = ("end",)
        else:
            a = agent.combat_action(cs, player, acts)
        n_in_turn += 1
        if a[0] == "play":
            st.cards_played.append(a[1].Id.Entry)
            per_card[id(a[1])] = per_card.get(id(a[1]), 0) + 1
        ok = execute(a, cs, player)
        if a[0] == "end":
            tn = (cs.RoundNumber, player.PlayerCombatState.TurnNumber)
            stuck_ends = stuck_ends + 1 if tn == last_turn else 0
            last_turn = tn
            if stuck_ends >= 20:      # 结束回合没有推进：不再空转，按失败处理
                st.loop_alarm = "end_turn_stuck"
                break
        if not ok and a[0] != "end":
            # 打不出（目标失效等）：避免死循环，直接结束回合
            execute(("end",), cs, player)
    st.rounds = cs.RoundNumber
    st.hp_after = player.Creature.CurrentHp
    st.won = (not player.Creature.IsDead) and not alive_enemies(cs)
    return st


def _n(e):
    try:
        return e.name
    except AttributeError:
        return str(e)
