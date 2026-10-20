"""加载转译后的游戏代码，注入手写基础设施（RunManager 桩、补丁），初始化 ModelDb。
用法：from sts2sim.rt.boot import game  （game 即生成模块）"""
import sys

sys.setrecursionlimit(20000)

from . import prelude  # noqa: E402
from .prelude import Dummy, FINALIZE_ERRORS  # noqa: E402
from ..gen import game  # noqa: E402

g = game.__dict__


class _NetService:
    Type = game.NetGameType.Singleplayer
    IsConnected = True


class _SyncQueue:
    """动作队列同步器：单机模拟中入队即同步执行。"""
    CombatState = None
    log = None

    def RequestEnqueue(self, action):
        if self.log is not None:
            self.log.append(action)
        action.ExecuteAction()

    def SetCombatState(self, s):
        self.CombatState = s

    def __getattr__(self, n):
        return Dummy("ActionQueueSynchronizer." + n)


class _Executor:
    CurrentlyRunningAction = None
    IsPaused = False

    def __init__(self):
        self.AfterActionExecuted = prelude._Event()
        self.FinishedExecutingActions = prelude._Event()

    def Pause(self):
        pass

    def Unpause(self):
        pass

    def __getattr__(self, n):
        return Dummy("ActionExecutor." + n)


class _RunManagerImpl:
    """RunManager 单机桩：只保留模拟需要的状态；同步器/回放/校验全部吸收。"""

    def __init__(self):
        self.NetService = _NetService()
        self.IsSinglePlayerOrFakeMultiplayer = True
        self.IsSingleplayerOrFakeMultiplayer = True
        self.IsInProgress = True
        self.state = None
        self.ascension = 0
        self.ActionQueueSynchronizer = _SyncQueue()
        self.ActionExecutor = _Executor()
        for n in ("PlayerChoiceSynchronizer", "RewardSynchronizer", "EventSynchronizer", "ChecksumTracker", "TreasureRoomRelicSynchronizer", "ActionQueueSet",
                  "OneOffSynchronizer", "ActChangeSynchronizer", "RestSiteSynchronizer", "MapSelectionSynchronizer",
                  "History", "AscensionManager"):
            setattr(self, n, Dummy("RunManager." + n))
        self.RoomExited = prelude._Event()
        self.ended = None
        self.WinTime = 0
        self.RunTime = 0

    def HasAscension(self, level):
        st = self.state
        a = st.AscensionLevel if st is not None else self.ascension
        return int(a) >= int(level)

    def OnEnded(self, isVictory=False, *a, **k):
        """原版：结束本局并生成存档；模拟器只记录结果。"""
        self.ended = bool(isVictory)
        return None

    def DebugOnlyGetState(self):
        return self.state

    def WriteReplay(self, *a, **k):
        pass

    def GetLocalCharacterEnergyIconPrefix(self, *a):
        return ""

    def ApplyAscensionEffects(self, *a):
        pass


class RunManager:
    Instance = _RunManagerImpl()


game.RunManager = RunManager
g["RunManager"] = RunManager
prelude.G["RunManager"] = RunManager


class _DTO:
    @staticmethod
    def ToUnixTimeSeconds():
        return 1700000000

    @staticmethod
    def ToUnixTimeMilliseconds():
        return 1700000000000


class DateTimeOffset:
    Now = _DTO()
    UtcNow = _DTO()


game.DateTimeOffset = DateTimeOffset

# 转译代码引用但未转译的名字（网络消息、UI、格式化器…）：集合接口映射到 Seq，其余吸收为 Dummy
import os as _os  # noqa: E402
_und = _os.path.join(_os.path.dirname(game.__file__), "undefined.txt")
if _os.path.exists(_und):
    for _n in open(_und, encoding="utf-8").read().split():
        if _n in g:
            continue
        if _n in ("List", "IEnumerable", "IList", "IReadOnlyList"):
            g[_n] = prelude.Seq
        else:
            g[_n] = Dummy(_n)

from . import patches  # noqa: E402,F401

# ModelDb 初始化（游戏启动时执行），然后重跑依赖它的静态初始化
_failed = [e[1] for e in FINALIZE_ERRORS if e[0] == "static"]
del FINALIZE_ERRORS[:]
game.ModelDb.Init()
game.ModelDb.InitIds()
for _n in _failed:
    try:
        g[_n]._static_init()
    except Exception as _e:  # noqa
        FINALIZE_ERRORS.append(("static2", _n, repr(_e)[:200]))

# 单机：本地玩家 NetId 固定为 1（Player.CreateForNewRun 的 netId 参数）
game.LocalContext.NetId = 1
