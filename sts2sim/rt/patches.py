"""对生成代码的手写覆盖（C# 语义无法从源码自动得到的少数函数）。每一项都注明原因。"""
import functools

from ..gen import game


def _det_hash(s):
    # StringHelper.GetDeterministicHashCode：C# char 运算是整数，Python 需 ord；按 int32 溢出语义
    num = 352654597
    num2 = num
    i = 0
    n = len(s)
    while i < n:
        num = ((num << 5) + num ^ ord(s[i])) & 0xFFFFFFFF
        if i == n - 1:
            break
        num2 = ((num2 << 5) + num2 ^ ord(s[i + 1])) & 0xFFFFFFFF
        i += 2
    r = (num + num2 * 1566083941) & 0xFFFFFFFF
    return r - (1 << 32) if r >= (1 << 31) else r


# v0.111：GetDeterministicHashCode 改为 XxHash64(UTF-8, seed 0) → ulong；旧算法改名 GetDeterministicHashCodeOld（存档迁移/“old”种子用）
_P1, _P2, _P3, _P4, _P5 = (0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63,
                           0x27D4EB2F165667C5)
_M64 = 0xFFFFFFFFFFFFFFFF


def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & _M64


def _round(acc, lane):
    acc = (acc + lane * _P2) & _M64
    return (_rotl(acc, 31) * _P1) & _M64


def _merge(acc, val):
    acc ^= _round(0, val)
    return (acc * _P1 + _P4) & _M64


@functools.lru_cache(maxsize=65536)
def _xxh64(s):
    b = s.encode("utf-8")
    n = len(b)
    i = 0
    if n >= 32:
        v1, v2, v3, v4 = (_P1 + _P2) & _M64, _P2, 0, (-_P1) & _M64
        while i + 32 <= n:
            v1 = _round(v1, int.from_bytes(b[i:i + 8], "little"))
            v2 = _round(v2, int.from_bytes(b[i + 8:i + 16], "little"))
            v3 = _round(v3, int.from_bytes(b[i + 16:i + 24], "little"))
            v4 = _round(v4, int.from_bytes(b[i + 24:i + 32], "little"))
            i += 32
        h = (_rotl(v1, 1) + _rotl(v2, 7) + _rotl(v3, 12) + _rotl(v4, 18)) & _M64
        h = _merge(h, v1)
        h = _merge(h, v2)
        h = _merge(h, v3)
        h = _merge(h, v4)
    else:
        h = _P5
    h = (h + n) & _M64
    while i + 8 <= n:
        h ^= _round(0, int.from_bytes(b[i:i + 8], "little"))
        h = (_rotl(h, 27) * _P1 + _P4) & _M64
        i += 8
    if i + 4 <= n:
        h ^= (int.from_bytes(b[i:i + 4], "little") * _P1) & _M64
        h = (_rotl(h, 23) * _P2 + _P3) & _M64
        i += 4
    while i < n:
        h ^= (b[i] * _P5) & _M64
        h = (_rotl(h, 11) * _P1) & _M64
        i += 1
    h ^= h >> 33
    h = (h * _P2) & _M64
    h ^= h >> 29
    h = (h * _P3) & _M64
    h ^= h >> 32
    return h


game.StringHelper.GetDeterministicHashCode = staticmethod(_xxh64)
game.StringHelper.GetDeterministicHashCodeOld = staticmethod(_det_hash)


# ---- 同步执行模型下的玩家选择上下文 ----
# 原版用 Task/TaskCompletionSource 在等待玩家选择时挂起动作并联网同步；
# 模拟器中所有 async 调用都是同步执行，选择由 CardSelectCmd.Selector 当场给出，故这些等待全部为空操作。
def _assign_and_wait(self, task):
    src = self.Source
    if src is not None:
        src.InvokeExecutionFinished()
    self.Task = task
    return True


def _wait_no_assign(self, task):
    return True


def _noop(self, *a, **k):
    return None


game.HookPlayerChoiceContext.AssignTaskAndWaitForPauseOrCompletion = _assign_and_wait
game.HookPlayerChoiceContext.WaitForPauseOrCompletionWithoutAssigningTask = _wait_no_assign
# v0.111 HookPlayerChoiceContext.WaitForCompletion：同步模型下任务已完成（Task 恒为 None），空操作
game.HookPlayerChoiceContext.WaitForCompletion = _noop
# v0.111 新增 BranchingPlayerChoiceContext（CardModel.OnPlayWrapper 用）：任务已同步执行完，同样空操作
game.BranchingPlayerChoiceContext.AssignTaskAndWaitForPauseOrCompletion = _wait_no_assign
for _c in (game.HookPlayerChoiceContext, game.GameActionPlayerChoiceContext, game.BlockingPlayerChoiceContext,
           game.BranchingPlayerChoiceContext):
    _c.SignalPlayerChoiceBegun = _noop
    _c.SignalPlayerChoiceEnded = _noop

# CombatStateTracker：原版只在下一帧刷新 UI 显示（TestMode 下整段跳过），模拟器同样跳过。
game.CombatStateTracker.NotifyCombatStateChanged = _noop

# NetCombatCardDb：联网用的卡牌编号表，靠 CardPile.ContentsChanged 事件登记；
# 部分界面事件在模拟器中不触发，这里改为按需登记（编号只用于网络同步，不影响逻辑）。
_orig_get_card_id = game.NetCombatCardDb.GetCardId


def _get_card_id(self, card):
    self.IdCardIfNecessary(card)
    return _orig_get_card_id(self, card)


game.NetCombatCardDb.GetCardId = _get_card_id

# 纯视觉方法（转译后只剩节点操作的残骸）
game.ReattachPower.DoFadeOutOnAllSegments = _noop


# ---- 性能：地图路径剪枝里的纯函数，改为等价的原生 Python 实现（输出字符串/字典内容与原版逐字一致）----
def _segment_key(segment):
    seg = list(segment)
    a, b = seg[0].coord, seg[-1].coord
    if a.row == 0:
        head = f"{a.row}-{b.col},{b.row}-"
    else:
        head = f"{a.col},{a.row}-{b.col},{b.row}-"
    return head + ",".join(str(int(p.PointType)) for p in seg)


def _add_segments(path, segments):
    P = list(path)
    n = len(P)
    MPP = game.MapPathPruning
    for i in range(n - 1):
        sp = P[i]
        if not (len(sp.Children) > 1 or sp.coord.row == 0):
            continue
        for j in range(2, n - i):
            ep = P[i + j]
            if len(ep.parents) >= 2:
                arr = game.Seq(P[i:i + j + 1])
                key = _segment_key(arr)
                if not segments.ContainsKey(key):
                    segments[key] = game.Seq([arr])
                elif not MPP.AnyOverlappingSegments(segments[key], arr):
                    segments[key].Add(arr)


game.MapPathPruning.GenerateSegmentKey = staticmethod(_segment_key)
game.MapPathPruning.AddSegmentsToDictionary = staticmethod(_add_segments)


# ---- 性能：CombatState.IterateHookListeners / Contains（每个钩子都会枚举一遍全部模型）----
# 与原版逐项等价：同样的收集顺序、同样的 Contains 判定，只是去掉了转译层的属性/类型分派开销。
_KIND_ORDER = (("power", "PowerModel"), ("relic", "RelicModel"), ("potion", "PotionModel"), ("card", "CardModel"),
               ("affl", "AfflictionModel"), ("ench", "EnchantmentModel"), ("orb", "OrbModel"),
               ("monster", "MonsterModel"), ("true", "AchievementModel"), ("true", "ModifierModel"),
               ("true", "MultiplayerScalingModel"))
_KIND_CACHE = {}


def _kind(t):
    k = _KIND_CACHE.get(t)
    if k is None:
        k = "bad"
        for name, cls in _KIND_ORDER:
            if issubclass(t, getattr(game, cls)):
                k = name
                break
        _KIND_CACHE[t] = k
    return k


def _cs_contains(self, model):
    k = _kind(type(model))
    if k == "power":
        o = model.Owner
        if o.CombatState is None:
            return False
        p = o.Player
        return True if p is None else p.IsActiveForHooks
    if k in ("relic", "potion", "card"):
        return (not model.HasBeenRemovedFromState) and model.Owner.IsActiveForHooks
    if k in ("affl", "ench"):
        if not model.HasCard:
            return False
        c = model.Card
        return (not c.HasBeenRemovedFromState) and c.Owner.IsActiveForHooks
    if k == "orb":
        return (not model.HasBeenRemovedFromState) and model.Owner.IsActiveForHooks
    if k == "monster":
        return model.Creature.CombatState is not None
    if k == "true":
        return True
    return _orig_cs_contains(self, model)


_orig_cs_contains = game.CombatState.Contains


def _cs_iter_hook_listeners(self):
    def _gen():
        lst = []
        app, ext = lst.append, lst.extend
        for creature in list(self._allies) + list(self._enemies):
            ext(creature.Powers)
            player = creature.Player
            if player is None:
                app(creature.Monster)
                continue
            if not player.IsActiveForHooks:
                continue
            for r in player.Relics:
                if not r.IsMelted:
                    app(r)
            for p in player.PotionSlots:
                if p is not None:
                    app(p)
            pcs = player.PlayerCombatState
            if pcs is None:
                continue
            ext(pcs.OrbQueue.Orbs)
            for pile in pcs.AllPiles:
                for c in list(pile.Cards):
                    app(c)
                    a = c.Affliction
                    if a is not None:
                        app(a)
                    e = c.Enchantment
                    if e is not None:
                        app(e)
        ext(self.Modifiers)
        if self.MultiplayerScalingModel is not None:
            app(self.MultiplayerScalingModel)
        for item in lst:
            if _cs_contains(self, item):
                yield item
        for item2 in game._iter(game.ModHelper.IterateAllCombatStateSubscribers(self)):
            yield item2
    return game._LazyEnum(_gen)


game.CombatState.Contains = _cs_contains
game.CombatState.IterateHookListeners = _cs_iter_hook_listeners


# ---- 重载分派：PowerCmd.Remove(null) ----
# C# 里 PowerCmd.Remove(creature.GetPower<T>()) 的静态类型是 PowerModel，传 null 时走 Remove(PowerModel)（空操作）；
# Python 运行时按值分派，None 会落到第一个重载 Remove(Creature) 而崩溃。泛型调用（带 _g）才是 Remove<T>(Creature)。
_orig_power_remove = game.PowerCmd.Remove


def _power_remove(*a, **k):
    if a and a[0] is None and not k.get("_g"):
        return None
    return _orig_power_remove(*a, **k)


game.PowerCmd.Remove = staticmethod(_power_remove)

# PunchOff 事件：PunchEachOther 是纯动画循环（while 未取消: 播放动画），同步执行时会死循环
game.PunchOff.PunchEachOther = lambda self: None

# Crusher / Rocket（第 3 幕 Boss 组合）的 Background 是动画节点属性，转译后为 None；招式里会调用它的动画方法
game.Crusher.Background = game.Dummy("vis")
game.Rocket.Background = game.Dummy("vis")

# TheBomb：PowerCmd.Apply 在战斗结束中/目标不能获得能力时返回 null，原版对返回值直接 .SetDamage（异步任务里的异常被吞掉）。
_orig_bomb_onplay = game.TheBomb.OnPlay


def _bomb_onplay(self, choiceContext, cardPlay):
    try:
        return _orig_bomb_onplay(self, choiceContext, cardPlay)
    except AttributeError as e:
        if "SetDamage" not in str(e):
            raise


game.TheBomb.OnPlay = _bomb_onplay


# ---- v0.111 回合循环（CombatManager.StartCombatInternal 的 while 循环 + TaskCompletionSource 信号）----
# 原版：回合循环是一个长期运行的 async 任务，在 await EndTurnSignalSource.Task 处挂起等玩家结束回合。
# 模拟器同步执行：在 AwaitTurnEndAndSwitchSides 处抛 _Suspend 跳出循环，并把“循环剩余部分”注册为
# EndTurnSignalSource 的续体；玩家结束回合（SetReadyToEndTurn → TrySetResult）时同步继续执行，
# 与旧版（v0.10x）SetReadyToEndTurn 内联执行 AfterAllPlayersReadyToEndTurn 的时序一致。
class _Suspend(BaseException):
    pass


_CM = game.CombatManager


def _await_tail(self, ts, sig):
    if not ts.IsInProgress:
        return None
    self.AfterAllPlayersReadyToEndTurn(ts, sig)
    if not ts.IsInProgress:
        return None
    begin = ts.BeginEnemyTurnSignalSource
    if begin is None or not begin._done:
        # 单机下 ReadyToBeginEnemyTurnAction 会在上一步里同步设置结果；没有就当作挂起
        if begin is not None:
            begin._cont = lambda act: _resume(self, ts, lambda: _begin_tail(self, ts, act))
        raise _Suspend()
    return _begin_tail(self, ts, begin._result)


def _begin_tail(self, ts, act):
    if not ts.IsInProgress:
        return None
    self.AfterAllPlayersReadyToBeginEnemyTurn(ts)
    return act


def _await_turn_end(self, ts):
    if not ts.IsInProgress or ts.State.CurrentSide != game.CombatSide.Player:
        return None
    src, begin = ts.EndTurnSignalSource, ts.BeginEnemyTurnSignalSource
    if src is None or begin is None:
        return None
    if src._done:
        return _await_tail(self, ts, src._result)
    src._cont = lambda sig: _resume(self, ts, lambda: _await_tail(self, ts, sig))
    raise _Suspend()


def _loop(self, ts, act):
    while ts.IsLive:
        if ts.State.CurrentSide == game.CombatSide.Player:
            self.StartTurn(ts)
            act = _await_turn_end(self, ts)
        else:
            self.StartTurn(ts, act)
            act = None


def _resume(self, ts, first):
    try:
        act = first()
        _loop(self, ts, act)
    except _Suspend:
        pass


_orig_start_combat_internal = _CM.StartCombatInternal


def _run_turn_loop_after(self, previousTurnLoopTask):
    ts = self._turnState
    if ts is None:
        return None
    try:
        _orig_start_combat_internal(self, ts)
    except _Suspend:
        pass
    return None


_CM.AwaitTurnEndAndSwitchSides = _await_turn_end
_CM.RunTurnLoopAfter = _run_turn_loop_after


# v0.111 CardPileCmd.Add 读取 GetTweenForCardsChangingPiles(...).Item1：视觉桩需返回 TestMode 分支的 (null, false)
game.CardPileCmd.GetTweenForCardsChangingPiles = staticmethod(lambda *a, **k: game.CsTuple((None, False)))


# 本地化：模拟器不加载 loc 表（LocManager.Instance 为 None）；需要文字的地方（如 v0.111 事件 CalculateVars 里
# 把菜名写进 StringVar）只拿 key 当文本，不影响逻辑
def _loc_text(self, *a, **k):
    return f"{self.LocTable}.{self.LocEntryKey}"


game.LocString.GetFormattedText = _loc_text
game.LocString.GetRawText = _loc_text


# CardCmd.PreviewCardPileAdd 只是 UI 预览，但它的实参里常常是 await CardPileCmd.Add(...)（真正把牌加进牌堆）。
# 以前转译器把整条语句当视觉丢掉了（愤怒不复制、Neow 遗物不给牌……，6 月版就有这个错），现在保留实参、预览本身为空操作。
game.CardCmd.PreviewCardPileAdd = staticmethod(lambda *a, **k: None)


# 卡牌存档往返（PaelsTooth / ArchaicTooth 在局内用 ToSerializable/FromSerializable 暂存卡）：
# 模拟器不加载存档系统（SaveUtil/SerializableCard 是 Dummy），这里用轻量记录代替，语义同 CardModel.FromSerializable。
class _SerCard:
    __slots__ = ("Id", "CurrentUpgradeLevel", "FloorAddedToDeck", "ench_id", "ench_amount")


def _card_to_ser(self):
    s = _SerCard()
    s.Id = self.Id
    s.CurrentUpgradeLevel = self.CurrentUpgradeLevel
    s.FloorAddedToDeck = self.FloorAddedToDeck
    e = self.Enchantment
    s.ench_id = e.Id if e is not None else None
    s.ench_amount = e.Amount if e is not None else 0
    return s


def _card_from_ser(save):
    if not isinstance(save, _SerCard):
        raise TypeError("FromSerializable: 只支持模拟器内的 _SerCard")
    card = game.ModelDb.GetById(save.Id, _g=(game.CardModel,)).ToMutable()
    if save.FloorAddedToDeck is not None:
        card.FloorAddedToDeck = save.FloorAddedToDeck
    if save.ench_id is not None:
        card.EnchantInternal(game.ModelDb.GetById(save.ench_id, _g=(game.EnchantmentModel,)).ToMutable(), save.ench_amount)
        card.Enchantment.ModifyCard()
        card.FinalizeUpgradeInternal()
    for _ in range(int(save.CurrentUpgradeLevel)):
        card.UpgradeInternal()
        card.FinalizeUpgradeInternal()
    return card


game.CardModel.ToSerializable = _card_to_ser
game.CardModel.FromSerializable = staticmethod(_card_from_ser)
