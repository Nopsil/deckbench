"""RunManager 单机移植（对照 src/Core/Runs/RunManager.cs 逐方法翻译）。

只去掉：存档、联网、回放、校验和、UI/音乐/过场。保留：建局初始化、进阶效果、房间/地图生成、
进房（含房间类型掷骰、黑名单）、换幕、事件内战斗（房间栈）、胜负判定。
同步器（事件/休息处/奖励/宝箱/一次性）使用转译的真实类，网络服务换成单机桩。
"""
from ..rt.boot import game as G
from ..rt.prelude import Dummy, _Event


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
        self.AscensionManager = G.AscensionManager(0)
        self.RunLobby = None
        self.RunStarted = _Event()
        self.RoomEntered = _Event()
        self.RoomExited = _Event()
        self.ActEntered = _Event()
        self.ended = None
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

    def DebugOnlyGetState(self):
        return self.State

    def WriteReplay(self, *a, **k):
        pass

    def GetLocalCharacterEnergyIconPrefix(self, *a):
        return ""

    def OnEnded(self, isVictory=False, *a, **k):
        self.ended = bool(isVictory)
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
        self.AscensionManager = G.AscensionManager(state.AscensionLevel)
        self.InitializeNewRun()
        self.GenerateRooms()

    def InitializeNewRun(self):
        st = self.State
        st.SharedRelicGrabBag.Populate(G.ModelDb.RelicPool(_g=(G.SharedRelicPool,)).GetUnlockedRelics(st.UnlockState), st.Rng.UpFront)
        for player in G._iter(st.Players):
            player.PopulateRelicGrabBagIfNecessary(st.Rng.UpFront)
        st.ExtraFields.StartedWithNeow = st.UnlockState.IsEpochRevealed(_g=(G.NeowEpoch,))
        for modifier in G._iter(st.Modifiers):
            modifier.OnRunCreated(st)
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
