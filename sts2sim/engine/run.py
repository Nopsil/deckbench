"""整局驱动：建局 → 每幕地图 → 房间交互（战斗/事件/休息/商店/宝箱）→ Boss → 下一幕 → 胜负。

房间本身的逻辑（遭遇生成、奖励、事件选项效果、休息处选项、商店库存/价格、宝箱遗物）全部是转译的游戏代码；
这里只负责“玩家点了什么”，决策委托给 agent。
"""
import os
import zlib
import time

from ..rt.boot import game as G
from ..rt.prelude import Dummy
from . import combat as C
from .manager import SimRunManager, RunOver

CHARACTERS = {"Ironclad": G.Ironclad, "Silent": G.Silent, "Defect": G.Defect,
              "Necrobinder": G.Necrobinder, "Regent": G.Regent}


class Selector(G.CsObject):
    """CardSelectCmd.Selector（ICardSelector）：把选牌请求转给 agent。"""

    def __init__(self, agent):
        self.agent = agent

    def GetSelectedCards(self, options, minSelect, maxSelect):
        opts = list(options)
        res = self.agent.select_cards(opts, int(minSelect), int(maxSelect))
        return G.Seq(res)

    def GetSelectedCardReward(self, options, alternatives):
        r = self.agent.card_reward(list(options), list(alternatives) if alternatives is not None else [])
        # v0.111：返回 CardRewardSelection{card, alternative}（旧版直接返回 CardModel 或 null）
        if isinstance(r, G.CardRewardSelection):
            return r
        sel = G.CardRewardSelection()
        if r is not None and isinstance(r, G.CardRewardAlternative):
            sel.alternative = r
        else:
            sel.card = r
        return sel


class RunResult:
    def __init__(self):
        self.victory = False
        self.floor = 0
        self.act = 0
        self.death_room = None
        self.hp = 0
        self.max_hp = 0
        self.gold = 0
        self.deck = []
        self.relics = []
        self.picked = []       # 卡牌奖励选择（Id）
        self.skipped = 0
        self.combats = []      # (楼层, 房间类型, 遭遇Id, 回合, 掉血, 胜, 幕序号0起, 是否触发安全阀)
        self.path = []         # (楼层, 房间, 进入时HP, 最大HP, 金币)
        self.loop_alarm = False
        self.error = None
        self.seconds = 0.0

    def to_dict(self):
        return dict(self.__dict__)


class RunDriver:
    def __init__(self, character, ascension=10, seed="SEED", agent=None, modifiers=None, setup_hooks=()):
        from .agents import HeuristicAgent
        self.character = character
        self.ascension = ascension
        self.seed = str(seed)
        self.agent = agent or HeuristicAgent(seed=zlib.crc32(str(self.seed).encode()) & 0xFFFF)
        self.result = RunResult()
        self.setup_hooks = list(setup_hooks)
        self.mgr = None
        self.player = None
        self.state = None

    # ---------- 建局 ----------
    def _create(self):
        mgr = SimRunManager(driver=self)
        G.RunManager.Instance = mgr
        self.mgr = mgr
        G.LocalContext.NetId = 1
        G.CombatManager.Instance = G.CombatManager()
        sel = Selector(self.agent)
        G.CardSelectCmd._selectorStack.Clear()
        G.CardSelectCmd._selectorStack.Push(sel)
        ch_cls = CHARACTERS.get(self.character) if isinstance(self.character, str) else self.character
        ch = G.ModelDb.Character(_g=(ch_cls,))
        player = G.Player.CreateForNewRun(ch, G.UnlockState.all_, 1)
        # v0.111 StartRunLobby.BeginRunLocally: rng = new Rng(XxHash64(seed), "act_selection")；
        # ActModel.GetRandomList：每个幕序号在已解锁幕中 rng.NextItem（假定全部幕已发现）
        rng = G.Rng(G.StringHelper.GetDeterministicHashCode(self.seed), "act_selection")
        acts = []
        for group in G.ModelDb.ActsByIndex:
            cands = G.Seq([a for a in group if a.IsUnlocked(G.UnlockState.all_)])
            acts.append(rng.NextItem(cands))
        state = G.RunState.CreateForNewRun(G.Seq([player]), G.Seq([a.ToMutable() for a in acts]), G.Seq(),
                                           G.GameMode.Standard, self.ascension, self.seed)
        for h in self.setup_hooks:
            h(state, player)
        mgr.SetUpNewSinglePlayer(state)
        self.player, self.state = player, state
        self.agent.on_run_start(player, self)
        mgr.FinalizeStartingRelics()
        mgr.Launch()

    def play(self):
        t0 = time.time()
        r = self.result
        try:
            self._create()
            self.mgr.EnterAct(0)
            while True:
                self._advance()
        except RunOver as e:
            r.victory = e.victory
        except Exception as e:  # noqa
            import traceback
            r.error = f"{type(e).__name__}: {e}\n" + "".join(traceback.format_exc().splitlines(True)[-12:])
        st, p = self.state, self.player
        if st is not None:
            r.floor = st.TotalFloor
            r.act = st.CurrentActIndex
            r.hp, r.max_hp, r.gold = p.Creature.CurrentHp, p.Creature.MaxHp, p.Gold
            r.deck = [c.Id.Entry + ("+" if c.IsUpgraded else "") for c in p.Deck.Cards]
            r.relics = [x.Id.Entry for x in p.Relics]
        r.seconds = time.time() - t0
        return r

    # ---------- 地图推进 ----------
    def _advance(self):
        st = self.state
        cur = st.CurrentMapPoint
        if cur is None:
            pts = [st.Map.StartingMapPoint]
        else:
            pts = list(cur.Children)
            if not pts:
                # 本幕 Boss 已打完
                if st.Map.SecondBossMapPoint is not None and cur.coord != st.Map.SecondBossMapPoint.coord \
                        and cur.PointType == G.MapPointType.Boss:
                    pts = [st.Map.SecondBossMapPoint]
                else:
                    self.mgr.EnterNextAct()
                    return
        pts.sort(key=lambda p: (p.coord.col, p.coord.row))
        pt = self.agent.choose_map_point(pts, self) if len(pts) > 1 else pts[0]
        self.mgr.EnterMapCoord(pt.coord)

    # ---------- 房间交互 ----------
    def on_room_entered(self, room):
        st, p = self.state, self.player
        self.result.path.append((st.TotalFloor, type(room).__name__.replace("Room", ""), p.Creature.CurrentHp, p.Creature.MaxHp, p.Gold))
        if isinstance(room, G.CombatRoom):
            self._combat(room)
        elif isinstance(room, G.EventRoom):
            self._event(room)
        elif isinstance(room, G.RestSiteRoom):
            self._rest(room)
        elif isinstance(room, G.MerchantRoom):
            self._shop(room)
        elif isinstance(room, G.TreasureRoom):
            self._treasure(room)

    def _combat(self, room):
        p, st = self.player, self.state
        hp0 = p.Creature.CurrentHp
        stats = C.run_combat(room, p, self.agent)
        enc = room.Encounter.Id.Entry if room.Encounter is not None else "?"
        self.result.combats.append((st.TotalFloor, C._n(room.RoomType), enc, stats.rounds, hp0 - p.Creature.CurrentHp, stats.won,
                                     st.CurrentActIndex, stats.loop_alarm))
        if stats.loop_alarm:
            self.result.loop_alarm = True
        if not stats.won or p.Creature.IsDead:
            self.result.death_room = (st.TotalFloor, C._n(room.RoomType), enc)
            raise RunOver(False)
        # 战斗奖励（原版由 NCombatRoom 在 CombatWon 后弹出奖励界面）
        G.RewardsCmd.OfferForRoomEnd(p, room)
        self.mgr.ProceedFromTerminalRewardsScreen()

    def offer_rewards(self, rewards_set):
        """替代 RewardsSet.Offer 里的 NRewardsScreen：逐个领取（agent 决定是否领取）。"""
        taken_linked = set()
        for reward in list(rewards_set.Rewards):
            parent = reward.ParentRewardSet
            if parent is not None:
                if id(parent) in taken_linked:
                    continue
            if not self.agent.take_reward(reward):
                continue   # 未领的奖励在 SkipLocalRewardsSet 时统一 OnSkipped（v0.111 语义）
            before = {id(c) for c in self.player.Deck.Cards}
            ok = _select_reward(rewards_set, reward)
            if parent is not None and ok:
                taken_linked.add(id(parent))
            if isinstance(reward, G.CardReward):
                new = [c for c in self.player.Deck.Cards if id(c) not in before]
                if new:
                    self.result.picked += [c.Id.Entry for c in new]
                else:
                    self.result.skipped += 1

    def _event(self, room):
        sync = self.mgr.EventSynchronizer
        guard = 0
        while True:
            ev = sync.GetLocalEvent()
            if ev is None or ev.IsFinished or self.state.CurrentRoom is not room:
                break
            opts = list(ev.CurrentOptions)
            if not opts:
                break
            idx = self.agent.event_option(ev, opts, self)
            sync.ChooseLocalOption(idx)
            guard += 1
            if guard > 30:
                break
        if self.player.Creature.IsDead:
            self.result.death_room = (self.state.TotalFloor, "Event", room.CanonicalEvent.Id.Entry)
            raise RunOver(False)

    def _rest(self, room):
        sync = self.mgr.RestSiteSynchronizer
        for _ in range(4):
            opts = list(sync.GetLocalOptions())
            if not opts:
                break
            i = self.agent.rest_option(opts, self)
            if i is None:
                break
            ok = sync.ChooseLocalOption(i)
            if ok:
                break

    def _shop(self, room):
        inv = room.GetLocalInventory()   # v0.111：每个玩家一份商店库存
        for _ in range(12):
            bought = False
            for e in self.agent.shop(inv, self):
                if e.IsStocked and e.EnoughGold:
                    if e.OnTryPurchaseWrapper(inv):
                        bought = True
            if not bought:
                break

    def _treasure(self, room):
        room.DoNormalRewards()
        room.DoExtraRewardsIfNeeded()
        sync = self.mgr.TreasureRoomRelicSynchronizer
        relics = sync.CurrentRelics
        if relics is not None and len(list(relics)) > 0:
            rl = list(relics)
            i = self.agent.treasure_relic(rl, self)
            sync.PickRelicLocally(i)
            # 真游戏里宝箱遗物是在 UI 节点（NTreasureRoomRelicCollection）的 RelicsAwarded 回调里发放的：RelicCmd.Obtain(relic.ToMutable(), player)；
            # 无头模拟没有这个节点，这里补上（单机 = 只有自己投票，拿到所选那件）。默认开启；DECKBENCH_TREASURE_FIX=0 = 旧行为（宝箱遗物不入手，只用于复现旧数字）
            if i is not None and 0 <= int(i) < len(rl) and os.environ.get("DECKBENCH_TREASURE_FIX", "1") != "0":
                G.RelicCmd.Obtain(rl[int(i)].ToMutable(), self.player)


def play_run(character, ascension=10, seed="SEED", agent=None, **kw):
    return RunDriver(character, ascension, seed, agent, **kw).play()


def _select_reward(rewards_set, reward):
    """v0.111：领取走 RewardsSetSynchronizer.SelectLocalReward（内部 Reward.SelectUnsynchronized，原 OnSelectWrapper）。"""
    sync = getattr(rewards_set, "_synchronizer", None)
    if sync is not None and not isinstance(sync, Dummy):
        return sync.SelectLocalReward(reward)
    return reward.SelectUnsynchronized()


def _offer(self):
    """RewardsSet.Offer（v0.111）：与原版相同，只把 NRewardsScreen 换成驱动器的逐项领取。
    v0.111 删除了 Hook.BeforeRewardsOffered（改为 GenerateWithoutOffering 里的 Hook.ModifyRewards），
    并新增 RewardsSetSynchronizer 记录奖励组的完成/跳过。"""
    if self.Player.Creature.IsDead:
        return None
    self.GenerateWithoutOffering()
    is_terminal = isinstance(self.Room, G.CombatRoom)
    sync = getattr(self, "_synchronizer", None)
    if sync is not None and not isinstance(sync, Dummy):
        sync.BeginRewardsSet(self)
    if self.Rewards.Count <= 0 and not is_terminal and not self._allowEmptyRewards:
        return None
    drv = getattr(G.RunManager.Instance, "driver", None)
    if drv is not None:
        drv.offer_rewards(self)
    else:
        for reward in list(self.Rewards):
            _select_reward(self, reward)
    # 没领完的奖励组：等同于玩家点“继续”离开（SkipLocalRewardsSet → 未领的 OnSkipped）
    if sync is not None and not isinstance(sync, Dummy) and not sync.IsRewardsSetCompleted(self):
        sync.SkipLocalRewardsSet()


G.RewardsSet.Offer = _offer


def _choose_bundle(player, bundles):
    """CardSelectCmd.FromChooseABundleScreen：原版此处没有 Selector 分支（UI 直接选），这里交给 agent。"""
    if G.CombatManager.Instance.IsEnding:
        return G.Seq()
    bl = list(bundles)
    if not bl:
        return G.Seq()
    G.RunManager.Instance.PlayerChoiceSynchronizer.ReserveChoiceId(player)
    drv = getattr(G.RunManager.Instance, "driver", None)
    i = drv.agent.choose_bundle([list(b) for b in bl]) if drv is not None else 0
    return bl[i if i is not None else 0]


G.CardSelectCmd.FromChooseABundleScreen = staticmethod(_choose_bundle)
