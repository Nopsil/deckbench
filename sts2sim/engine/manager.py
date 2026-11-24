"""RunManager 单机移植（对照 src/Core/Runs/RunManager.cs 逐方法翻译）。

只去掉：存档、联网、回放、校验和、UI/音乐/过场。保留：建局初始化、进阶效果、房间/地图生成、
进房（含房间类型掷骰、黑名单）、换幕、事件内战斗（房间栈）、胜负判定。
同步器（事件/休息处/奖励/宝箱/一次性）使用转译的真实类，网络服务换成单机桩。
"""
from ..rt.boot import game as G
from ..rt.prelude import Dummy, _Event
from .merchant_memory import MerchantMemory


def ascension_manager(level, game_mode=None):
    """v0.113.1 的构造是 (GameMode, level)。更早的生成代码只有 level。按形参个数调用，不改关卡含义。"""
    ctor = G.AscensionManager.__init__
    if getattr(ctor, "__code__", None) is not None and ctor.__code__.co_argcount >= 3:
        if game_mode is None:
            game_mode = G.GameMode.Standard
        return G.AscensionManager(game_mode, level)
    return G.AscensionManager(level)


class NetService:
    """NetSingleplayerGameService 的最小替身。"""
    Type = G.NetGameType.Singleplayer
    NetId = 1
    IsConnected = True
    Platform = None

    def SendMessage(self, *a, **k):
        pass

    def RegisterMessageHandler(self, *a, **k):
        pass

    def UnregisterMessageHandler(self, *a, **k):
        pass

    def __getattr__(self, n):
        return Dummy("NetService." + n)


class EventCombatSync:
    """单机事件战。

    生成代码里的 EventCombatSynchronizer 在联机目录，没被转译，原来是个空对象。
    选项调用 ReadyToEnterCombat 时什么都不发生，战斗选项看起来选了，实际没进房。
    """

    def __init__(self, player_collection, run_state):
        self._run = run_state
        self._states = [None] * len(list(G._iter(player_collection.Players)))
        self._canonical_event = None
        self.MutableEncounterForLayout = None
        self.CombatStateForLayout = None

    def InitializeForEvent(self, local_event):
        self._canonical_event = local_event.CanonicalInstance
        if local_event.LayoutType != G.EventLayoutType.Combat:
            return
        canonical = local_event.CanonicalEncounter
        if canonical is None:
            raise G.InvalidOperationException(f"Canonical encounter is not set for event {local_event.Id}")
        encounter = canonical.ToMutable()
        encounter.GenerateMonstersWithSlots(self._run)
        combat = self._combat_state(encounter)
        for player in G._iter(self._run.Players):
            combat.AddPlayer(player)
        for pair in G._iter(combat.Encounter.MonstersWithSlots):
            monster, slot = (pair.Item1, pair.Item2) if hasattr(pair, "Item1") else pair
            combat.AddCreature(combat.CreateCreature(monster, G.CombatSide.Enemy, slot))
        self.MutableEncounterForLayout = encounter
        self.CombatStateForLayout = combat

    def ReadyToEnterCombat(self, canonical_encounter, player, extra_rewards, should_resume_after_combat):
        slot = int(self._run.GetPlayerSlotIndex(player))
        if self._states[slot] is not None:
            raise G.InvalidOperationException("player is already ready to enter event combat")
        self._states[slot] = (canonical_encounter, extra_rewards, bool(should_resume_after_combat))
        if all(state is not None for state in self._states):
            self._enter()

    def _enter(self):
        if self._canonical_event is None:
            raise G.InvalidOperationException("GenerateInternalCombatState must be called before EnterCombat")
        canonical, _, resume = self._states[0]
        for state in self._states:
            if bool(state[2]) != bool(resume) or state[0] is not canonical:
                raise G.InvalidOperationException("event combat votes disagree")
        if self.CombatStateForLayout is not None:
            combat = self.CombatStateForLayout
        else:
            combat = self._combat_state(canonical.ToMutable())
        room = G.CombatRoom(combat)
        room.ShouldCreateCombat = self._canonical_event.LayoutType != G.EventLayoutType.Combat
        room.ShouldResumeParentEventAfterCombat = resume
        room.ParentEventId = self._canonical_event.Id
        for _, rewards, _ in self._states:
            for reward in G._iter(rewards):
                room.AddExtraReward(reward.Player, reward)
        G.RunManager.Instance.EnterRoomWithoutExitingCurrentRoom(
            room, self._canonical_event.LayoutType != G.EventLayoutType.Combat)

    def ResetState(self):
        if self.CombatStateForLayout is not None:
            for creature in list(G._iter(self.CombatStateForLayout.Creatures)):
                self.CombatStateForLayout.RemoveCreature(creature)
        self._canonical_event = None
        self.MutableEncounterForLayout = None
        self.CombatStateForLayout = None
        self._states = [None] * len(self._states)

    def _combat_state(self, encounter):
        run = self._run
        return G.CombatState(encounter, run, run.Modifiers, run.BadgeModels, run.RunModels, run.Dominion)


G.EventCombatSynchronizer = EventCombatSync


class MerchantSync:
    """单机商店库存。

    v0.113.1 把库存从 MerchantRoom 挪到 MerchantSynchronizer，而那个类型在联机目录里，不在转译范围内。
    这里只做它进店时的单机分支：普通局用 CreateForNormalMerchant，Blitz 用 CreateForBlitzMerchant。
    """

    def __init__(self):
        self._memory = MerchantMemory()

    def OnMerchantEntered(self, inventories=None):
        if inventories is not None:
            return
        st = G.RunManager.Instance.State
        blitz = getattr(st, "GameMode", None) == getattr(G.GameMode, "Blitz", None)
        create = G.MerchantInventory.CreateForBlitzMerchant if blitz else G.MerchantInventory.CreateForNormalMerchant
        for player in G._iter(st.Players):
            self.SetMerchantInventory(player, create(player))

    def SetMerchantInventory(self, player, inventory):
        """假商人等事件会换掉这一层的库存。之后购买和 GetInventoryFor 都看这一份。"""
        self._memory.set(player, inventory)

    def GetInventoryFor(self, player):
        return self._memory.get(player)

    def GetLocalInventory(self):
        st = G.RunManager.Instance.State
        me = G.LocalContext.GetMe(st)
        return self.GetInventoryFor(me)

    def OnMerchantExited(self):
        # 真游戏还会把没买的商品写进地图历史。整局结果用的是已经入手的牌和遗物，这里只清掉这一店的库存。
        self._memory.clear()


class SyncQueue:
    """ActionQueueSynchronizer：入队即同步执行（单机无排队竞争）。"""
    CombatState = None

    def __init__(self):
        self.log = None

    def RequestEnqueue(self, action):
        if self.log is not None:
            self.log.append(action)
        action.ExecuteAction()

    def RequestEnqueueHookAction(self, action):
        action.ExecuteAction()

    def SetCombatState(self, s):
        self.CombatState = s

    def __getattr__(self, n):
        return Dummy("ActionQueueSynchronizer." + n)


class Executor:
    CurrentlyRunningAction = None
    IsPaused = False

    def __init__(self):
        self.AfterActionExecuted = _Event()
        self.FinishedExecutingActions = _Event()
        self.JustBeforeActionFinishedExecuting = _Event()

    def Pause(self):
        pass

    def Unpause(self):
        pass

    def __getattr__(self, n):
        return Dummy("ActionExecutor." + n)


class RunOver(Exception):
    """整局结束（胜或负）时从深层调用栈跳出。"""
    def __init__(self, victory):
        super().__init__("victory" if victory else "defeat")
        self.victory = victory


class SimRunManager:
    """RunManager.Instance 的替代。driver 提供需要玩家决策的房间交互（战斗、事件、休息处…）。"""

    def __init__(self, driver=None):
        self.driver = driver
        self.NetService = NetService()
        self.State = None
        self.ascension = 0
        self.ActionQueueSynchronizer = SyncQueue()
        self.ActionExecutor = Executor()
        for n in ("ChecksumTracker", "ActionQueueSet", "MapSelectionSynchronizer", "ActChangeSynchronizer", "History",
                  "CombatStateSynchronizer", "RunLocationTargetedBuffer", "CombatReplayWriter", "FlavorSynchronizer",
                  "InputSynchronizer", "HoveredModelTracker", "PlayerChoiceSynchronizer"):
            setattr(self, n, Dummy("RunManager." + n))
        self.EventSynchronizer = Dummy("RunManager.EventSynchronizer")
        self.RestSiteSynchronizer = Dummy("RunManager.RestSiteSynchronizer")
        self.RewardSynchronizer = Dummy("RunManager.RewardSynchronizer")
        self.RewardsSetSynchronizer = Dummy("RunManager.RewardsSetSynchronizer")
        self.OneOffSynchronizer = Dummy("RunManager.OneOffSynchronizer")
        self.TreasureRoomRelicSynchronizer = Dummy("RunManager.TreasureRoomRelicSynchronizer")
        self.MerchantSynchronizer = MerchantSync()
        self.AscensionManager = ascension_manager(0)
        self.RunLobby = None
        self.RunStarted = _Event()
        self.RoomEntered = _Event()
        self.RoomExited = _Event()
        self.ActEntered = _Event()
        self.ended = None
        self.HasRunEnded = False
        self.WinTime = 0
        self.RunTime = 0
        self.IsAbandoned = False
        self.IsCleaningUp = False
        self.ForceDiscoveryOrderModifications = False
        self.ShouldSave = False
        self.DailyTime = None

    # ---- 属性 ----
    @property
    def IsInProgress(self):
        return self.State is not None

    @property
    def IsSinglePlayerOrFakeMultiplayer(self):
        return self.State is not None

    @property
    def IsSingleplayerOrFakeMultiplayer(self):   # v0.111 改名
        return self.State is not None

    @property
    def IsGameOver(self):
        return self.State is not None and self.State.IsGameOver

    def HasAscension(self, level):
        st = self.State
        a = st.AscensionLevel if st is not None else self.ascension
        return int(a) >= int(level)

    def IsDread(self):
        """v0.113.1：部分怪物数值看是不是 Dread 模式。普通局不是。"""
        st = self.State
        if st is None:
            return False
        return getattr(st, "GameMode", None) == getattr(G.GameMode, "Dread", None)

    def DebugOnlyGetState(self):
        return self.State

    def WriteReplay(self, *a, **k):
        pass

    def GetLocalCharacterEnergyIconPrefix(self, *a):
        return ""

    def OnEnded(self, isVictory=False, *a, **k):
        self.ended = bool(isVictory)
        self.HasRunEnded = True
        return None

    # ---- 建局（SetUpNewSinglePlayer + InitializeShared + InitializeNewRun + GenerateRooms）----
    def SetUpNewSingleplayer(self, state):   # v0.111 改名（原 SetUpNewSinglePlayer）
        return self.SetUpNewSinglePlayer(state)

    def SetUpNewSinglePlayer(self, state):
        if self.State is not None:
            raise G.CsException("State is already set.")
        self.State = state
        net, buf = self.NetService, Dummy("RunLocationTargetedBuffer")
        self.EventSynchronizer = G.EventSynchronizer(buf, net, state, state, 1, state.Rng.Seed)
        self.RewardSynchronizer = G.RewardSynchronizer(buf, net, state, 1)
        self.RewardsSetSynchronizer = G.RewardsSetSynchronizer(buf, net, state, 1)
        self.RestSiteSynchronizer = G.RestSiteSynchronizer(buf, net, state, 1, None)
        self.OneOffSynchronizer = G.OneOffSynchronizer(buf, net, state, 1)
        self.TreasureRoomRelicSynchronizer = G.TreasureRoomRelicSynchronizer(
            state, 1, self.ActionQueueSynchronizer, state.SharedRelicGrabBag, state.Rng.TreasureRoomRelics)
        self.AscensionManager = ascension_manager(state.AscensionLevel, getattr(state, "GameMode", None))
        self._install_card_selector(state)
        self.InitializeNewRun()

    def _install_card_selector(self, state):
        """v0.113.1：选牌走 RunManager.CardSelectorStack。更早的生成代码没有这个类，静态栈已在建局时压好。"""
        cls = getattr(G, "CardSelectorStack", None)
        if not isinstance(cls, type):
            return
        self.CardSelectorStack = cls(state)
        sel = getattr(self.driver, "selector", None)
        if sel is None:
            return
        for player in G._iter(state.Players):
            self.CardSelectorStack.PushSelector(player, sel)
        self.GenerateRooms()

    def InitializeNewRun(self):
        st = self.State
        st.SharedRelicGrabBag.Populate(G.ModelDb.RelicPool(_g=(G.SharedRelicPool,)).GetUnlockedRelics(st.UnlockState), st.Rng.UpFront)
        for player in G._iter(st.Players):
            player.PopulateRelicGrabBagIfNecessary(st.Rng.UpFront)
        st.ExtraFields.StartedWithNeow = st.UnlockState.IsEpochRevealed(_g=(G.NeowEpoch,))
        for modifier in G._iter(st.Modifiers):
            modifier.OnRunCreated(st)
        # v0.113.1：RunState 自带 RunModel（例如多人缩放）。不调用 OnRunCreated 时 RunState 是空的。
        for run_model in G._iter(getattr(st, "RunModels", None) or []):
            run_model.OnRunCreated(st)
        for player in G._iter(st.Players):
            self.ApplyAscensionEffects(player)

    def ApplyAscensionEffects(self, player):
        self.AscensionManager.ApplyEffectsTo(player)

    def GenerateRooms(self):
        st = self.State
        lst = st.UnlockState.SharedAncients.ToList().UnstableShuffle(st.Rng.UpFront)
        for act in list(st.Acts)[1:]:
            count = st.Rng.UpFront.NextInt(lst.Count + 1)
            sub = lst.Take(count).ToList()
            lst = lst.Except(sub).ToList()
            act.SetSharedAncientSubset(sub)
        n = st.Acts.Count
        for i in range(n):
            act = st.Acts[i]
            act.GenerateRooms(st.Rng.UpFront, st.UnlockState, st.Players.Count > 1)
            # ShouldApplyTutorialModifications：TestMode 下为 False；模拟“老玩家”（全部解锁），不做新手发现顺序调整
            if i == n - 1 and self.AscensionManager.HasLevel(G.AscensionLevel.DoubleBoss):
                boss_id = act.BossEncounter.Id
                second = st.Rng.UpFront.NextItem(act.AllBossEncounters.Where(lambda e: e.Id != boss_id))
                act.SetSecondBossEncounter(second)

    def FinalizeStartingRelics(self):
        for player in G._iter(self.State.Players):
            for relic in G._iter(list(player.Relics)):
                relic.AfterObtained()

    def Launch(self):
        G.LocalContext.NetId = 1
        self.RunStarted.Invoke(self.State)
        return self.State

    # ---- 地图与换幕 ----
    def GenerateMap(self):
        st = self.State
        map2 = st.Act.CreateMap(st, replaceTreasureWithElites=False)
        mp = G.Hook.ModifyGeneratedMap(st, map2, st.CurrentActIndex)
        G.Hook.AfterMapGenerated(st, mp, st.CurrentActIndex)
        if not st.ExtraFields.StartedWithNeow and st.CurrentActIndex == 0:
            mp.StartingMapPoint.PointType = G.MapPointType.Monster
        st.Map = mp
        st.RemoveStaleVisitedMapCoords(mp)

    def SetActInternal(self, act_index):
        st = self.State
        st.CurrentActIndex = act_index
        st.ClearVisitedMapCoordsDebug()
        st.Odds.UnknownMapPoint.ResetToBase()
        self.GenerateMap()

    def EnterAct(self, act_index):
        st = self.State
        self.ExitCurrentRooms()
        self.SetActInternal(act_index)
        if act_index == 0 and st.ExtraFields.StartedWithNeow:
            self.EnterMapCoord(st.Map.StartingMapPoint.coord)
        else:
            self.EnterRoomInternal(G.MapRoom())
            self.ActEntered.Invoke()
        G.Hook.AfterActEntered(st)

    def EnterNextAct(self):
        st = self.State
        if st.CurrentActIndex >= st.Acts.Count - 1:
            # 最终 Boss 已击败：原版进入 TheArchitect 事件房后 WinRun；模拟器直接判胜
            self.OnEnded(isVictory=True)
            raise RunOver(True)
        self.EnterAct(st.CurrentActIndex + 1)

    # ---- 进房 ----
    def EnterMapCoord(self, coord):
        st = self.State
        if not st.AddVisitedMapCoord(coord):
            return None
        point = st.Map.GetPoint(coord)
        return self.EnterMapPointInternal(coord.row + 1, point.PointType, None)

    def EnterMapPointInternal(self, act_floor, point_type, pre_finished_room):
        st = self.State
        st.ActFloor = act_floor
        self.ExitCurrentRooms()
        if point_type == G.MapPointType.Unknown and pre_finished_room is not None:
            room_type = G.RoomType.Monster
        else:
            cur = st.CurrentMapPoint
            children = cur.Children if cur is not None else G.HashSet()
            blacklist = build_blacklist(st.CurrentMapPointHistoryEntry, children)
            room_type = self.RollRoomTypeFor(point_type, blacklist)
        room = pre_finished_room if pre_finished_room is not None else self.CreateRoom(room_type, point_type)
        if pre_finished_room is None:
            st.AppendToMapPointHistory(point_type, room.RoomType, room.ModelId)
        self.EnterRoom(room)
        return room

    def CreateRoom(self, room_type, map_point_type=None, model=None):
        st = self.State
        RT = G.RoomType
        if room_type in (RT.Monster, RT.Elite, RT.Boss):
            enc = model if model is not None else st.Act.PullNextEncounter(room_type).ToMutable()
            return G.CombatRoom(enc, st)
        if room_type == RT.Treasure:
            return G.TreasureRoom(st.CurrentActIndex)
        if room_type == RT.Shop:
            return G.MerchantRoom()
        if room_type == RT.Event:
            if model is None:
                model = st.Act.PullAncient() if map_point_type == G.MapPointType.Ancient else st.Act.PullNextEvent(st)
            return G.EventRoom(model)
        if room_type == RT.RestSite:
            return G.RestSiteRoom()
        if room_type == RT.Map:
            return G.MapRoom()
        raise G.CsException(f"Unexpected RoomType: {room_type}")

    def RollRoomTypeFor(self, point_type, blacklist):
        MPT, RT = G.MapPointType, G.RoomType
        st = self.State
        if point_type == MPT.Unknown:
            return st.Odds.UnknownMapPoint.Roll(blacklist, st)
        return {MPT.Unassigned: RT.Unassigned, MPT.Shop: RT.Shop, MPT.Treasure: RT.Treasure,
                MPT.RestSite: RT.RestSite, MPT.Monster: RT.Monster, MPT.Elite: RT.Elite, MPT.Boss: RT.Boss,
                MPT.Ancient: RT.Event}[point_type]

    def ExitCurrentRooms(self):
        while self.State.CurrentRoomCount > 0:
            self.ExitCurrentRoom()

    def ExitCurrentRoom(self):
        room = self.State.PopCurrentRoom()
        room.Exit(self.State)
        self.RoomExited.Invoke()
        return room

    def EnterRoom(self, room):
        self.ExitCurrentRooms()
        self.EnterRoomInternal(room)

    def EnterRoomInternal(self, room, is_restoring=False):
        st = self.State
        pre = False
        if not is_restoring:
            if isinstance(room, (G.CombatRoom, G.EventRoom)) and room.IsPreFinished:
                pre = True
        run_external = not (is_restoring or pre)
        st.PushRoom(room)
        if run_external and not isinstance(room, G.MapRoom):
            G.Hook.BeforeRoomEntered(st, room)
        room.Enter(st, is_restoring)
        if run_external and st.CurrentRoomCount == 1:
            st.Act.MarkRoomVisited(room.RoomType)
        self.RoomEntered.Invoke()
        # 需要玩家决策的房间交给驱动器（原版由 UI 驱动）
        if self.driver is not None and not is_restoring:
            self.driver.on_room_entered(room)

    def EnterRoomWithoutExitingCurrentRoom(self, room, fadeToBlack=False):
        st = self.State
        e = st.CurrentMapPointHistoryEntry
        if e is not None:
            e.Rooms.Add(_init_entry(room))
        self.EnterRoomInternal(room)

    def ProceedFromTerminalRewardsScreen(self):
        st = self.State
        if st.CurrentRoomCount > 1:
            cur = st.CurrentRoom
            if isinstance(cur, G.CombatRoom) and cur.ShouldResumeParentEventAfterCombat:
                exited = self.ExitCurrentRoom()
                st.CurrentRoom.Resume(exited, st)
                return
            self.ExitCurrentRoom()


def build_blacklist(prev_entry, next_points):
    """RunManager.BuildRoomTypeBlacklist"""
    hs = G.HashSet()
    nxt = list(next_points)
    if (prev_entry is not None and prev_entry.HasRoomOfType(G.RoomType.Shop)) or \
            (len(nxt) > 0 and all(p.PointType == G.MapPointType.Shop for p in nxt)):
        hs.Add(G.RoomType.Shop)
    return hs


def _init_entry(room):
    e = G.MapPointRoomHistoryEntry()
    e.RoomType = room.RoomType
    e.ModelId = room.ModelId
    return e
