"""局外决策交给 spire-mentor 的 PPO 网络（外部依赖，见 mentor.py 顶部说明）。

spire-mentor 的整局 AI = 战斗 MCTS + 局外 PPO（每角色一个 ONNX 网络，在它自己的仓库 sts2-pycli/data/ppo）。
它的 Python 绑定 `sts2_rs.ppo_wire_decide(state, surface, character)` 吃 SpireMentor 模组发给顾问的“bridge”消息：
  map_select / card_reward / rest_site / shop / event(Neow、先古之民遗物三选一)
这里把我们引擎的局面按模组 C# 的同样字段拼出这种消息（SimStateExtractor.ApplyEnvelope / SerializeMapGraph 等），
拿网络的 argmax 当决定。网络不覆盖或调用失败的决策 → 回退到我们自己的 learned 策略（StrongAgent）。
本文件不含任何游戏数据。
"""
import os

from ..rt.boot import game as G
from .mentor import lib

CHARS = {"IRONCLAD": "Ironclad", "SILENT": "Silent", "DEFECT": "Defect", "NECROBINDER": "Necrobinder", "REGENT": "Regent"}
ANCIENTS = {"OROBAS", "PAEL", "TEZCATARA", "NONUPEIPE", "TANX", "VAKUU"}


def _n(x):
    return str(getattr(x, "name", x)).split(".")[-1]


def _card(c):
    lvl = int(getattr(c, "CurrentUpgradeLevel", 0) or 0)
    if not lvl and getattr(c, "IsUpgraded", False):
        lvl = 1
    return {"id": c.Id.Entry, "upgrade_level": lvl, "upgraded": bool(lvl)}


def map_graph(st):
    m = st.Map
    nodes = []
    for mp in G._iter(m.GetAllMapPoints()):
        nodes.append({"col": int(mp.coord.col), "row": int(mp.coord.row), "type": _n(mp.PointType),
                      "children": [{"col": int(c.coord.col), "row": int(c.coord.row)} for c in G._iter(mp.Children)]})
    cur = st.CurrentMapCoord
    d = {"nodes": nodes, "current": {"col": int(cur.col), "row": int(cur.row)} if cur is not None else None}
    try:
        b = m.BossMapPoint
        bn = {"col": int(b.coord.col), "row": int(b.coord.row)}
        try:
            bn["id"] = st.Act.BossEncounter.Id.Entry
        except Exception:  # noqa
            pass
        d["boss"] = bn
    except Exception:  # noqa
        d["boss"] = None
    d["visited"] = [{"col": int(c.col), "row": int(c.row)} for c in G._iter(st.VisitedMapCoords)]
    return d


def run_state(st, p):
    pots = []
    for i, x in enumerate(p.PotionSlots):
        pots.append({"slot": i, "empty": True} if x is None else {"slot": i, "id": x.Id.Entry, "empty": False})
    return {"gold": int(p.Gold), "hp": int(p.Creature.CurrentHp), "max_hp": int(p.Creature.MaxHp),
            "potions": pots, "potion_slot_count": len(pots),
            "relics": [{"id": r.Id.Entry} for r in p.Relics],
            "master_deck": [_card(c) for c in p.Deck.Cards],
            "ascension": int(st.AscensionLevel), "character": p.Character.Id.Entry}


def envelope(msg, st, p):
    msg["map"] = msg.get("map") or map_graph(st)
    msg["act"] = int(st.CurrentActIndex) + 1
    msg["floor"] = int(st.TotalFloor)
    msg["game_version"] = "v0.111.0"
    msg["run_state"] = run_state(st, p)
    return msg


class PpoNonCombat:
    """混入 StrongAgent 子类：局外决策用 spire-mentor PPO，失败回退 super()。"""
    ppo_surfaces = ("map_select", "card_reward", "rest_site", "shop", "event")

    def _ppo(self, surface, msg):
        st = self._run.state
        p = self.player
        ch = CHARS.get(p.Character.Id.Entry)
        ps = self.mstats.setdefault("ppo", {})
        k = ps.setdefault(surface, [0, 0])
        if ch is None or surface not in self.ppo_surfaces:
            k[1] += 1
            return None
        try:
            rs, _ = lib()
            r = rs.ppo_wire_decide(envelope(msg, st, p), surface, ch)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as e:  # noqa  （Rust panic 是 BaseException 的子类 PanicException）
            self.mstats.setdefault("ppo_err", {}).setdefault(f"{surface}:{type(e).__name__}", 0)
            self.mstats["ppo_err"][f"{surface}:{type(e).__name__}"] += 1
            r = None
        if r is None:
            k[1] += 1
            return None
        k[0] += 1
        i = int(r["argmax"])
        return r["actions"][i], r["responses"][i]

    # ---------- 地图 ----------
    def choose_map_point(self, points, run):
        nodes = [{"index": i, "type": _n(pt.PointType), "row": int(pt.coord.row), "col": int(pt.coord.col)}
                 for i, pt in enumerate(points)]
        r = self._ppo("map_select", {"type": "map_select", "nodes": nodes})
        if r is not None and r[1].get("action") == "choose":
            return points[int(r[1]["index"])]
        return super().choose_map_point(points, run)

    # ---------- 卡牌奖励 ----------
    def card_reward(self, cards, alternatives):
        cs = [(x.Card if hasattr(x, "Card") else x) for x in cards]
        if cs:
            r = self._ppo("card_reward", {"type": "card_reward", "cards": [_card(c) for c in cs], "can_skip": True})
            if r is not None:
                return cs[int(r[1]["index"])] if r[1].get("action") == "choose" else None
        return super().card_reward(cards, alternatives)

    # ---------- 休息 ----------
    def rest_option(self, options, run):
        ids = [str(o.OptionId).upper() for o in options]
        en = [i for i, o in enumerate(options) if getattr(o, "IsEnabled", True)]
        sel = [i for i in en if ids[i] in ("HEAL", "SMITH")]
        # 网络只学过 [rest, smith] 两个选项（REST_OPTION_LABELS）；有别的选项（铲子、举重…）就回退
        if len(sel) == 2 and len(en) == 2:
            sel.sort(key=lambda i: 0 if ids[i] == "HEAL" else 1)
            msg = {"type": "rest_site", "options": [{"index": j, "id": ids[i].lower(), "label": ids[i].lower(), "enabled": True}
                                                    for j, i in enumerate(sel)]}
            r = self._ppo("rest_site", msg)
            if r is not None:
                return sel[int(r[1]["index"])]
        else:
            self.mstats.setdefault("ppo", {}).setdefault("rest_site", [0, 0])[1] += 1
        return super().rest_option(options, run)

    # ---------- 商店：每次只买一件（驱动会反复调用直到不买） ----------
    def shop(self, inventory, run):
        p = self.player
        open_slot = any(x is None for x in p.PotionSlots)
        opts = [{"index": 0, "id": "leave_shop", "action": "leave_shop", "label": "Leave shop", "enabled": True}]
        ents = [None]
        purge = None
        for e in G._iter(inventory.AllEntries):
            if not (e.IsStocked and e.EnoughGold):
                continue
            if isinstance(e, G.MerchantCardEntry):
                if e.CreationResult is None:
                    continue
                kind, item = "buy_card", _card(e.CreationResult.Card)
            elif isinstance(e, G.MerchantRelicEntry):
                kind, item = "buy_relic", {"id": e.Model.Id.Entry}
            elif isinstance(e, G.MerchantPotionEntry):
                if not open_slot:
                    continue
                kind, item = "buy_potion", {"id": e.Model.Id.Entry}
            elif isinstance(e, G.MerchantCardRemovalEntry):
                kind, item, purge = "remove_card", None, int(e.Cost)
            else:
                continue
            o = {"index": len(opts), "id": kind, "action": kind, "label": kind, "enabled": True, "price": int(e.Cost)}
            if item is not None:
                o["item"] = item
            opts.append(o)
            ents.append(e)
        if len(opts) == 1:
            return []
        msg = {"type": "shop", "options": opts, "player_gold": int(p.Gold)}
        if purge is not None:
            msg["purge_cost"] = purge
        r = self._ppo("shop", msg)
        if r is None:
            return super().shop(inventory, run)
        act, resp = r
        e = ents[int(resp["index"])]
        if e is None:
            return []
        if act.get("action") == "shop_remove_card":
            deck = list(p.Deck.Cards)
            di = act.get("deck_idx")
            self._remove_target = deck[di] if isinstance(di, int) and 0 <= di < len(deck) else None
        return [e]

    def select_cards(self, options, min_sel, max_sel):
        t = getattr(self, "_remove_target", None)
        if t is not None:
            self._remove_target = None
            if any(o is t for o in options) and max_sel >= 1:
                return [t]
        return super().select_cards(options, min_sel, max_sel)

    # ---------- 事件：只接 Neow 和先古之民（选项是枚举 id / 遗物 id，不需要游戏文本） ----------
    def event_option(self, event, options, run):
        eid = event.Id.Entry
        if eid.upper() == "NEOW" or eid.upper() in ANCIENTS:
            hp = int(self.player.Creature.CurrentHp)
            opts = []
            for i, o in enumerate(options):
                d = {"index": i, "id": "choose_event_option", "action": "choose_event_option", "label": "", "description": "",
                     "enabled": not o.IsLocked, "event_id": eid, "text_key": str(getattr(o, "TextKey", "") or ""),
                     "relic_id": o.Relic.Id.Entry if getattr(o, "Relic", None) is not None else ""}
                wk = getattr(o, "WillKillPlayer", None)
                if callable(wk):
                    try:
                        d["will_kill_player"] = bool(wk(self.player))
                    except Exception:  # noqa
                        pass
                opts.append(d)
            r = self._ppo("event", {"type": "event", "options": opts})
            if r is not None and r[1].get("action") == "choose":
                return int(r[1]["index"])
        else:
            self.mstats.setdefault("ppo", {}).setdefault("event_other", [0, 0])[1] += 1
        return super().event_option(event, options, run)
