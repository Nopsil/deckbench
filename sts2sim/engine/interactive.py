"""交互式 agent：每个决策点把「局面文本 + 编号选项」交给外部（MCP 服务器 / 脚本 / 以后的 LLM），等它回一个选项号和理由。

- 每个决策都有编号 n（从 0 起）。外部回复 {"choice": i 或 [i,...], "reason": "..."} 或 {"auto": true}（交给内置 AI）。
- replay：启动时给一串历史回复，前 len(replay) 个决策直接按它走（用于撤销/恢复/断线重连）；整局对同一种子是确定的。
- 不问的决策（固定规则）：战斗/事件奖励里的金币、遗物、药水、卡牌奖励入口一律领取（卡牌奖励本身会问，可以跳过）。
"""
from ..rt.boot import game as G
from .agents import Agent, _caller_kind
from . import textstate as T
from .combat import alive_enemies  # noqa: F401

SCREEN_ZH = {"neow": "开局古神", "event": "事件", "map": "选路线", "card_reward": "卡牌奖励", "card_select": "选牌",
             "bundle": "选卡包", "rest": "休息处", "shop": "商店", "treasure": "宝箱遗物", "combat": "战斗"}
SELECT_KIND_ZH = {"upgrade": "选要升级的牌", "worst": "选要移除/失去的牌", "best": "选牌"}


class Decision(Exception):
    pass


class InteractiveAgent(Agent):
    name = "interactive"

    def __init__(self, io, replay=(), fallback=None, persona=None, seed=0):
        super().__init__(seed)
        self.io = io                    # io(decision_dict) -> reply dict（阻塞）
        self.replay = list(replay)
        self.fb = fallback
        self.persona = persona
        self.n = 0
        self.run = None
        self.last_reason = None
        self.last_source = None
        self.last_n = None

    # ---- 同步内置 AI 的状态 ----
    def on_run_start(self, player, run):
        self.player, self.run = player, run
        if self.fb is not None:
            self.fb.on_run_start(player, run)

    def on_combat_start(self, cs, player, room):
        if self.fb is not None:
            self.fb.on_combat_start(cs, player, room)

    # ---- 核心 ----
    def _ask(self, screen, body, labels, enabled=None, multi=None, auto=None):
        """labels：选项文字；enabled：可选的下标集合；multi=(min,max) 多选；auto()：内置 AI 的答案（下标或下标列表）。"""
        enabled = set(range(len(labels))) if enabled is None else set(enabled)
        n = self.n
        self.n += 1
        if n < len(self.replay):
            rep = self.replay[n]
        else:
            rep = None
        err = None
        while True:
            if rep is None:
                d = {"n": n, "screen": screen, "screen_zh": SCREEN_ZH.get(screen, screen),
                     "text": self._text(screen, body, labels, enabled, multi), "options": labels,
                     "enabled": sorted(enabled), "multi": list(multi) if multi else None, "error": err}
                rep = self.io(d)
            ch, why = self._resolve(rep, labels, enabled, multi, auto)
            if ch is not None or (multi and ch == []):
                break
            err, rep = why, None
            if n < len(self.replay):      # 历史回复不合法（不应发生）：改问外部
                self.replay = self.replay[:n]
        self.last_reason = rep.get("reason") or (f"auto:{getattr(self.fb, 'name', 'ai')}" if rep.get("auto") else None)
        self.last_source = "auto" if rep.get("auto") else ("replay" if n < len(self.replay) else "external")
        self.last_n = n
        self.io({"ack": n, "choice": ch, "reason": self.last_reason, "source": self.last_source, "label":
                 ([labels[i] for i in ch] if isinstance(ch, list) else labels[ch])})
        return ch

    def _resolve(self, rep, labels, enabled, multi, auto):
        if rep.get("auto"):
            if auto is None:
                return None, "这个决策不支持 auto"
            ch = auto()
            if multi:
                return [i for i in ch], None
            return (ch if ch in enabled else min(enabled)), None
        c = rep.get("choice")
        if multi:
            if isinstance(c, int):
                c = [c]
            if not isinstance(c, list) or any(not isinstance(i, int) for i in c):
                return None, "这里要多选：choice 给下标列表"
            mn, mx = multi
            if len(set(c)) != len(c) or not (mn <= len(c) <= mx) or any(i not in enabled for i in c):
                return None, f"要选 {mn}～{mx} 个不重复的可选下标"
            return c, None
        if isinstance(c, list) and len(c) == 1:
            c = c[0]
        if not isinstance(c, int) or c not in enabled:
            return None, f"非法选项 {c!r}，可选：{sorted(enabled)}"
        return c, None

    def _text(self, screen, body, labels, enabled, multi):
        L = []
        if self.persona:
            L.append("【风格】" + self.persona)
        L.append(f"【{SCREEN_ZH.get(screen, screen)}】决策 #{self.n - 1}")
        try:
            L.append(T.header(self.run))
        except Exception:  # noqa
            pass
        if body:
            L.append(body)
        L.append("选项" + (f"（多选 {multi[0]}～{multi[1]} 个）" if multi else "") + "：")
        for i, s in enumerate(labels):
            L.append(f"  {i}) {s}" + ("" if i in enabled else "  [不可选]"))
        return "\n".join(L)

    # ---- 各决策点 ----
    def combat_action(self, cs, player, acts):
        labels = [T.action_label(a, cs, player) for a in acts]

        def auto():
            a = self.fb.combat_action(cs, player, acts)
            return next((i for i, x in enumerate(acts) if x is a or tuple(x) == tuple(a)), len(acts) - 1)
        i = self._ask("combat", T.combat_block(cs, player), labels, auto=auto if self.fb else None)
        return acts[i]

    def choose_map_point(self, points, run):
        labels = []
        for p in points:
            kids = "、".join(T.POINT_ZH.get(T._n(c.PointType), T._n(c.PointType)) for c in p.Children)
            labels.append(f"第{int(p.coord.row)}行 第{int(p.coord.col)}列 {T.POINT_ZH.get(T._n(p.PointType), T._n(p.PointType))}"
                          + (f"（之后可去：{kids}）" if kids else ""))

        def auto():
            pt = self.fb.choose_map_point(points, run)
            return next(i for i, p in enumerate(points) if p is pt)
        i = self._ask("map", "（完整地图用 get_map 查看；第 0 列 = 最左）", labels, auto=auto if self.fb else None)
        return points[i]

    def event_option(self, event, options, run):
        eid = event.Id.Entry if event is not None else "?"
        screen = "neow" if isinstance(event, G.AncientEventModel) else "event"
        labels = [self._event_label(event, o) for o in options]
        enabled = [i for i, o in enumerate(options) if not o.IsLocked]
        body = f"事件：{T.zh('events', eid) or T.zh('ancients', eid) or eid}"
        try:
            desc = T.loc("events").get(f"{eid}.pages.INITIAL.description")
            if desc and screen == "event":
                body += "\n" + T.render_text(desc, event)[:300]
        except Exception:  # noqa
            pass

        def auto():
            return self.fb.event_option(event, options, run)
        return self._ask(screen, body, labels, enabled=enabled or [0], auto=auto if self.fb else None)

    def _event_label(self, event, o):
        key = str(o.TextKey or "")
        title = T.loc("events").get(key + ".title") or T.loc("ancients").get(key + ".title")
        desc = T.loc("events").get(key + ".description") or T.loc("ancients").get(key + ".description")
        rel = getattr(o, "Relic", None)
        if rel is not None:
            rid = rel.Id.Entry
            title = title or T.zh("relics", rid) or rid
            desc = desc or T.zh("relics", rid, "description")
            model = rel
        else:
            model = event
        title = T.render_text(title or key.rsplit(".", 1)[-1], model)
        d = T.render_text(desc or "", model)
        return title + (f"：{d}" if d else "") + ("（锁定）" if o.IsLocked else "")

    def card_reward(self, cards, alternatives):
        cl = [getattr(r, "Card", r) for r in cards]
        alts = list(alternatives or [])
        labels = [T.card_line(c) for c in cl]
        alts = [a for a in alts if str(getattr(a, "OptionId", "")).lower() != "skip"]   # 跳过 = 返回 None（和其它 agent 一致）
        for a in alts:
            oid = str(getattr(a, "OptionId", "alt"))
            labels.append("（特殊）" + (T.loc("card_reward_ui").get(f"OPTION_{oid.upper()}.name") or oid))
        labels.append("跳过")

        def auto():
            r = self.fb.card_reward(cards, alternatives)
            if r is None:
                return len(labels) - 1
            for i, c in enumerate(cl):
                if c is r or getattr(r, "Card", None) is c:
                    return i
            for k, a in enumerate(alts):
                if a is r:
                    return len(cl) + k
            return len(labels) - 1
        i = self._ask("card_reward", None, labels, auto=auto if self.fb else None)
        if i < len(cl):
            return cl[i]
        if i < len(cl) + len(alts):
            return alts[i - len(cl)]
        return None

    def take_reward(self, reward):
        self.last_reason = "固定规则：奖励全部领取"
        self.last_source, self.last_n = "rule", None
        return True

    def select_cards(self, options, min_sel, max_sel):
        opts = list(options)
        kind = _caller_kind()
        labels = [T.card_line(c) for c in opts]
        mn, mx = int(min_sel), int(max_sel)
        mx = min(mx, len(opts))
        mn = min(mn, mx)

        def auto():
            res = list(self.fb.select_cards(options, min_sel, max_sel) or [])
            return [i for i, c in enumerate(opts) if any(c is x for x in res)]
        idx = self._ask("card_select", SELECT_KIND_ZH.get(kind, "选牌") + f"（{kind}）", labels, multi=(mn, mx),
                        auto=auto if self.fb else None)
        return [opts[i] for i in idx]

    def choose_bundle(self, bundles):
        labels = [" + ".join(T.card_line(c, desc=False) for c in b) for b in bundles]

        def auto():
            return self.fb.choose_bundle(bundles)
        return self._ask("bundle", None, labels, auto=auto if self.fb else None)

    def rest_option(self, options, run):
        labels = []
        for o in options:
            oid = str(getattr(o, "OptionId", type(o).__name__))
            nm = T.loc("rest_site_ui").get(f"OPTION_{oid}.name") or oid
            ds = T.render_text(T.loc("rest_site_ui").get(f"OPTION_{oid}.description") or "", o)
            labels.append(nm + (f"：{ds}" if ds else ""))
        labels.append("离开（什么都不做）")

        def auto():
            r = self.fb.rest_option(options, run)
            return len(options) if r is None else r
        i = self._ask("rest", None, labels, auto=auto if self.fb else None)
        return None if i == len(options) else i

    def shop(self, inventory, run):
        entries, labels, enabled = [], [], []
        groups = [("卡牌", list(inventory.CardEntries)), ("遗物", list(inventory.RelicEntries)),
                  ("药水", list(inventory.PotionEntries))]
        rem = inventory.CardRemovalEntry
        for gname, es in groups:
            for e in es:
                if not e.IsStocked:
                    continue
                if gname == "卡牌" and e.CreationResult is not None:
                    what = T.card_line(e.CreationResult.Card)
                else:
                    m = getattr(e, "Model", None) or getattr(e, "Relic", None) or getattr(e, "Potion", None)
                    what = T.relic_name(m) if gname == "遗物" else T.potion_name(m)
                    try:
                        tbl = "relics" if gname == "遗物" else "potions"
                        ds = T.render_text(T.zh(tbl, m.Id.Entry, "description") or "", m)
                        what += f"：{ds}" if ds else ""
                    except Exception:  # noqa
                        pass
                entries.append(e)
                labels.append(f"买{gname} {what} — {int(e.Cost)} 金")
        if rem is not None and rem.IsStocked:
            entries.append(rem)
            labels.append(f"移除一张牌 — {int(rem.Cost)} 金")
        for i, e in enumerate(entries):
            try:
                if e.EnoughGold:
                    enabled.append(i)
            except Exception:  # noqa
                pass
        labels.append("离开商店")
        enabled.append(len(entries))

        def auto():
            buys = list(self.fb.shop(inventory, run) or [])
            for b in buys:
                for i, e in enumerate(entries):
                    if e is b and i in enabled:
                        return i
            return len(entries)
        i = self._ask("shop", "（每次买一样；买完会再问，选「离开商店」结束）", labels, enabled=enabled,
                      auto=auto if self.fb else None)
        return [] if i == len(entries) else [entries[i]]

    def treasure_relic(self, relics, run):
        labels = [T.relic_name(r) + "：" + T.render_text(T.zh("relics", r.Id.Entry, "description") or "", r) for r in relics]

        def auto():
            return self.fb.treasure_relic(relics, run) or 0
        return self._ask("treasure", None, labels, auto=auto if self.fb else None)
