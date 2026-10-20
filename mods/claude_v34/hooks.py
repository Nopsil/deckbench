"""Claude娘 v3.4 的能力、遗物和复杂卡牌效果。

风控事件契约（v3.4）在这里落地：
  * 「给予」= core.apply_power(…, 'FK', …)；只有实际增加正层数才发 power_applied 事件（按目标、按事件）。
  * 主动给予 = 你的回合中由卡牌或能力产生（core.source_active）；遗物与敌方回合的给予是被动给予，
    只吃 RLHF，不触发审计日志 / 流程自动化 / 一人违规全员连坐。
  * 「清除」= core.remove_power(…, 'FK', …)；实际移除正层数才发 power_removed。死亡不算清除。
  * 层数操作（转移、复制、翻倍、三倍、拉齐、死亡转移）= core.set_stacks，不算给予/清除。
    v3.4：复制/转移/拉齐/死亡转移对接收方会被人工制品拦截（消耗 1 层，操作无效）。
    翻倍/三倍是否被拦截设计未定，由 MULT_BLOCKED_BY_ARTIFACT 开关决定（默认不拦截）。
  * RLHF 只修正主施加数量（modify_apply），不递归；连坐次级施加 secondary=True，什么都不触发。
"""
from sts2sim.core import Power, register_power
from sts2sim.relics import Relic, register_relic
from sts2sim import expr

FK = "FK"
MULT_BLOCKED_BY_ARTIFACT = False


# ---------------------------------------------------------------- 表达式辅助
def _fk(c=None):
    ctx = expr.cur()
    c = c if c is not None else ctx.target
    return c.amt(FK) if c is not None else 0


expr.register_helper("fk", _fk)
expr.register_helper("fk_total", lambda: sum(e.amt(FK) for e in expr.cur().combat.alive_enemies()))
expr.register_helper("fk_enemies", lambda: sum(1 for e in expr.cur().combat.alive_enemies() if e.amt(FK) > 0))


def _src(ctx):
    return ("card", ctx.card) if ctx.card is not None else ("power", None)


# ---------------------------------------------------------------- 风控本体
@register_power
class FKPower(Power):
    id = FK; name = "风控"; kind = "debuff"; ai_value = 0.0


def state_value(C):
    """给 AI 的风控估值：每层约 0.8 点（单个敌人最多计 25 层），乘以本场战斗是否有兑现手段。"""
    if C.data.get("cl_mod") is None:
        return 0.0
    v = 0.0
    for e in C.alive_enemies():
        a = e.amt(FK)
        if a:
            v += 0.8 * min(a, 25)
    if fanji_ai_mode() == "look":
        v += fanji_look_value(C)
    return v


# ---------------------------------------------------------------- mod 全局监听
def on_battle_start(C, ev):
    ids = {c.id for c in C.player.draw_pile}
    if ids & CLAUDE_IDS:
        C.data["cl_mod"] = True


def on_power_removed(C, ev):
    if ev.pid == FK and ev.removed > 0 and not ev.target.is_player:
        C.data["fk_cleared"] = C.data.get("fk_cleared", 0) + ev.removed


def on_turn_start(C, ev):
    if ev.side == "player":
        C.data["credit_used"] = False


def on_attacked(C, ev):
    """统计：敌人攻击你时（每段 / 每次攻击行动的第一段）攻击者身上的风控层数。"""
    if C.data.get("cl_mod") is None or ev.target is not C.player or ev.attacker is None or ev.attacker.is_player:
        return
    x = _extra(C)
    L = str(ev.attacker.amt(FK))
    x["fk_hit"][L] = x["fk_hit"].get(L, 0) + 1
    seen = C.data.setdefault("_atk_seen_stat", set())
    first = id(ev.attacker) not in seen
    if first:
        seen.add(id(ev.attacker))
        x["fk_atk"][L] = x["fk_atk"].get(L, 0) + 1
    on = C.player.has(FANJI)
    x["atk_hits"] = x.get("atk_hits", 0) + 1
    x["atk_hits_on"] = x.get("atk_hits_on", 0) + (1 if on else 0)
    if first:
        x["atks"] = x.get("atks", 0) + 1
        x["atks_on"] = x.get("atks_on", 0) + (1 if on else 0)
        k = str(C.player.amt(FANJI)); sa = x.setdefault("st_atk", {}); sa[k] = sa.get(k, 0) + 1
    fanji_counter(C, ev.attacker, first, x)


def on_enemy_attack_done(C, ev):
    C.data.pop("_atk_seen_stat", None)


def credit_refund(ctx, **k):
    """扣信用分：实际清除了 2 层才返 1 能量，每回合限一次。"""
    C = ctx.combat
    if not C.data.get("credit_used"):
        C.data["credit_used"] = True
        C.player.energy += 1


# ---------------------------------------------------------------- 能力（玩家身上）
class _P(Power):
    kind = "buff"

    def attr(self, C):
        C.push_attr(self.src or self.name)


@register_power
class Qingtui(_P):
    id = "CL_QINGTUI"; name = "清退名单"; ai_value = 6.0

    def on_power_removed(self, C, ev):
        if ev.pid == FK and ev.removed > 0 and not ev.target.is_player and ev.target.alive:
            self.attr(C)
            for _ in range(self.amount):
                C.deal_damage(C.player, ev.target, min(ev.removed, 15), "power")
            C.pop_attr()


@register_power
class Dieman(_P):
    id = "CL_DIEMAN"; name = "叠满再说"; ai_value = 3.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            e = C.random_enemy()
            if e:
                self.attr(C)
                C.apply_power(e, FK, self.amount, source=("power", self))
                C.pop_attr()


# 宪法分类器的平衡变体（只用于模拟器 A/B，不改设计文件）。选择方式：环境变量 STS2SIM_FENLEIQI=<变体名>，
# 或实验 YAML 的 env: {STS2SIM_FENLEIQI: C}。读取层数不消耗风控（不算清除，也不算层数操作）。
#   mode: hit = 每段攻击触发（与荆棘一致）；attack = 敌人每次攻击行动只触发 1 次（不论几段）
#   伤害 = flat + floor(per * min(层数, cap))；up 为升级后的参数
FENLEIQI_VARIANTS = {
    "off": {"label": "对照：打出但不造成伤害", "mode": "hit",
            "base": {"flat": 0, "per": 0}, "up": {"flat": 0, "per": 0}},
    "v34": {"label": "v3.4 原版：每段 3（升级 5）", "mode": "hit",
            "base": {"flat": 3, "per": 0}, "up": {"flat": 5, "per": 0}},
    "A": {"label": "每段 = 层数（升级 层数×1.5）", "mode": "hit",
          "base": {"flat": 0, "per": 1}, "up": {"flat": 0, "per": 1.5}},
    "B": {"label": "每段 1+层数（升级 3+层数）", "mode": "hit",
          "base": {"flat": 1, "per": 1}, "up": {"flat": 3, "per": 1}},
    "C": {"label": "每次攻击 2+层数（升级 4+层数）", "mode": "attack",
          "base": {"flat": 2, "per": 1}, "up": {"flat": 4, "per": 1}},
    "D": {"label": "每次攻击 3+层数（升级 5+层数）", "mode": "attack",
          "base": {"flat": 3, "per": 1}, "up": {"flat": 5, "per": 1}},
    "E": {"label": "每次攻击 2+层数，至多+10（升级至多+15）", "mode": "attack",
          "base": {"flat": 2, "per": 1, "cap": 10}, "up": {"flat": 2, "per": 1, "cap": 15}},
    "F": {"label": "每段 1+层数/2（升级 3+层数/2）", "mode": "hit",
          "base": {"flat": 1, "per": 0.5}, "up": {"flat": 3, "per": 0.5}},
    "C2": {"label": "每次攻击 层数×1（升级 层数×1.5），无保底", "mode": "attack",
           "base": {"flat": 0, "per": 1}, "up": {"flat": 0, "per": 1.5}},
    "G": {"label": "每次攻击 2+层数（升级 2+层数×1.5）", "mode": "attack",
          "base": {"flat": 2, "per": 1}, "up": {"flat": 2, "per": 1.5}},
    # 第二轮：层数系数调低、不设上限
    "K": {"label": "每次攻击 3（升级 5），不看层数", "mode": "attack",
          "base": {"flat": 3, "per": 0}, "up": {"flat": 5, "per": 0}},
    "H": {"label": "每次攻击 层数/2（升级 2+层数/2）", "mode": "attack",
          "base": {"flat": 0, "per": 0.5}, "up": {"flat": 2, "per": 0.5}},
    "I": {"label": "每次攻击 1+层数/3（升级 3+层数/3）", "mode": "attack",
          "base": {"flat": 1, "per": 1 / 3}, "up": {"flat": 3, "per": 1 / 3}},
    "J": {"label": "每次攻击 2+层数/4（升级 4+层数/4）", "mode": "attack",
          "base": {"flat": 2, "per": 0.25}, "up": {"flat": 4, "per": 0.25}},
    "I2": {"label": "每次攻击 层数/3（升级 层数/2）", "mode": "attack",
           "base": {"flat": 0, "per": 1 / 3}, "up": {"flat": 0, "per": 0.5}},
    "M": {"label": "每段 1+层数/4（升级 2+层数/4）", "mode": "hit",
          "base": {"flat": 1, "per": 0.25}, "up": {"flat": 2, "per": 0.25}},
    "N": {"label": "每次攻击 2+层数（至多+5）（升级 3+层数，至多+8）", "mode": "attack",
          "base": {"flat": 2, "per": 1, "cap": 5}, "up": {"flat": 3, "per": 1, "cap": 8}},
    # 第三轮：更低系数；以及「读完减半」（层数操作，不算清除——偏离「只读不消耗」，仅作对照）
    "O": {"label": "每次攻击 1+层数/5（升级 2+层数/5）", "mode": "attack",
          "base": {"flat": 1, "per": 0.2}, "up": {"flat": 2, "per": 0.2}},
    "P": {"label": "每次攻击 层数/5（升级 层数/4）", "mode": "attack",
          "base": {"flat": 0, "per": 0.2}, "up": {"flat": 0, "per": 0.25}},
    "R": {"label": "每段 层数/5（升级 层数/4）", "mode": "hit",
          "base": {"flat": 0, "per": 0.2}, "up": {"flat": 0, "per": 0.25}},
    "Q": {"label": "每次攻击 = 层数，然后其风控减半（升级 层数+3）", "mode": "attack", "halve": True,
          "base": {"flat": 0, "per": 1}, "up": {"flat": 3, "per": 1}},
    # 第四轮：在 P / O 之间细调
    "T": {"label": "每次攻击 1+层数/6（升级 1+层数/4）", "mode": "attack",
          "base": {"flat": 1, "per": 1 / 6}, "up": {"flat": 1, "per": 0.25}},
    "U": {"label": "每次攻击 层数/5（升级 1+层数/5）", "mode": "attack",
          "base": {"flat": 0, "per": 0.2}, "up": {"flat": 1, "per": 0.2}},
    "W": {"label": "每次攻击 1+层数/5（升级 1+层数/4）", "mode": "attack",
          "base": {"flat": 1, "per": 0.2}, "up": {"flat": 1, "per": 0.25}},
    "X": {"label": "每次攻击 1+层数/6（升级 2+层数/6）", "mode": "attack",
          "base": {"flat": 1, "per": 1 / 6}, "up": {"flat": 2, "per": 1 / 6}},
    "Y": {"label": "每次攻击 1+层数/6（升级 1+层数/5）", "mode": "attack",
          "base": {"flat": 1, "per": 1 / 6}, "up": {"flat": 1, "per": 0.2}},
}


def fenleiqi_variant():
    import os
    return FENLEIQI_VARIANTS[os.environ.get("STS2SIM_FENLEIQI", "v34")]


def _extra(C):
    x = C.data.get("_extra")
    if x is None:
        x = C.data["_extra"] = {"fk_hit": {}, "fk_atk": {}, "fl_mon": {}, "fl_hits": 0, "fl_atks": 0}
    return x


def thorns_apply(C, dmg):
    """宪法修正案（实验卡）：你的反伤伤害 +50%（向下取整），升级 +100%。不叠加（只取第一份；测试卡组只有 1 张）。
    能力层数 = 加成百分比（50 / 100）。"""
    p = C.player.powers.get("CL_XIUZHENG")
    if p is None:
        return dmg
    return dmg + dmg * min(p.amount, 100) // 100


@register_power
class Xiuzheng(_P):
    id = "CL_XIUZHENG"; name = "宪法修正案"; ai_value = 0.12    # 层数=百分比（50→6 分）


@register_power
class XiuzhengC(_P):
    id = "CL_XIUZHENG_C"; name = "宪法修正案（向上取整）"; ai_value = 0.12


@register_power
class Fenleiqi(_P):
    id = "CL_FENLEIQI"; name = "宪法分类器"; ai_value = 2.0

    def on_power_applied(self, C, ev):
        # 记录每一份宪法分类器是否升级（卡面 d=3/5 → 普通/升级）
        if ev.pid == self.id and ev.target is self.owner:
            card = ev.source[1] if ev.source and ev.source[0] == "card" else None
            up = bool(getattr(card, "upgraded", False)) if card is not None else ev.delta >= 5
            self.data["copies"] = tuple(self.data.get("copies", ())) + (up,)

    def on_enemy_attack_done(self, C, ev):
        self.data.pop("atk_seen", None)

    def on_turn_start(self, C, ev):
        # 反击模式·stack 选项：没有反击时补 1 层（已有反击时由 Fanji.on_turn_start 先衰减再 +1）
        if ev.side == "player" and fanji_cfg() is not None and flq_opt() == "stack" and not C.player.has(FANJI):
            C.apply_power(C.player, FANJI, 1, source=("op", "fenleiqi"))

    def on_attacked(self, C, ev):
        if not (ev.target is C.player and ev.attacker is not None and not ev.attacker.is_player
                and ev.attacker.alive and ev.attacker.amt(FK) > 0):
            return
        if fanji_cfg() is not None:
            return                      # 反击模式：分类器只做「反击」强化
        V = fenleiqi_variant()
        if V["mode"] == "attack":
            seen = self.data.setdefault("atk_seen", set())
            if id(ev.attacker) in seen:
                return
            seen.add(id(ev.attacker))
        L = ev.attacker.amt(FK)        # 只读层数，不消耗
        copies = self.data.get("copies") or [self.amount >= 5]
        dmg = 0
        for up in copies:
            P = V["up" if up else "base"]
            dmg += P["flat"] + int(P["per"] * min(L, P.get("cap", 10 ** 9)))
        if dmg <= 0:
            return
        dmg = thorns_apply(C, dmg)
        self.attr(C)
        lost = C.deal_damage(C.player, ev.attacker, dmg, "power")
        if V.get("halve") and ev.attacker.alive:
            C.set_stacks(ev.attacker, FK, ev.attacker.amt(FK) // 2, op="fenleiqi_halve")
        C.pop_attr()
        x = _extra(C)
        nm = getattr(ev.attacker, "name", "?")
        m = x["fl_mon"].setdefault(nm, [0, 0])
        m[0] += lost or 0
        m[1] += 1


# ---------------------------------------------------------------- 「反击」状态（2026-10-20 重做实验，取代申诉通道）
# 只有 免责声明 / 红队演练 / 防御性回复 / 这个真的不能帮 给 1 层「反击」（至多 cap 层）；层数 = 剩余回合数，你的回合开始时 -1。
# 「反击」生效时，每当敌人攻击你（按攻击行动或按段），攻击者受到按其风控层数计算的反击伤害（无视力量，类似荆棘），
# 然后失去 1 层风控（层数操作 set_stacks，不算清除）。没有「反击」就完全没有反击伤害。
# 宪法分类器在此模式下不再有独立反伤，而是「反击」的强化（STS2SIM_FLQ）：
#   null  = 打出但无效果（对照）
#   flat  = 反击伤害 +3（升级 +5）
#   keep  = 反击不再消耗风控（升级：并且反击伤害 +2）
#   stack = 回合开始时获得 1 层反击（先衰减再获得，受上限约束）（升级：并且反击伤害 +2）
#   mult0 / mult16 = 反击伤害 × 1.5^当前反击层数（多张分类器：每张加成 1.5^n−1 直接相加），向下取整；
#                    mult0 升级 = 费用 1→0（倍率不变）；mult16 升级 = 底数 1.6
# 宪法修正案（稀有能力，2 费）：反击伤害 +50%（升级 +100%），不叠加。这个真的不能帮 自己的 4 点反伤不变。
# 环境变量：STS2SIM_FANJI = off 或 <attack|hit>-<上限>-<公式>，公式 L / 2L(=2+L) / H(=L/2) / 1H(=1+L/2)；例 attack-2-1H。
FANJI = "CL_FANJI"
GRANT_CARDS = {"MIANZE", "HONGDUI", "FANGYU_HUIFU", "BUNENGBANG"}
# STS2SIM_GRANT=6：扩展来源 = 上面 4 张 + 新普通技能「稍等，我再确认一下」+ 你说得完全正确！
GRANT_CARDS_6 = GRANT_CARDS | {"SHAODENG", "WANQUAN_ZHENGQUE"}


def fanji_cfg():
    import os
    v = os.environ.get("STS2SIM_FANJI", "off")
    if v == "off":
        return None
    mode, cap, f = v.split("-")
    return mode, int(cap), f


def flq_opt():
    import os
    return os.environ.get("STS2SIM_FLQ", "flat")


def fanji_base(f, L):
    return {"L": L, "2L": 2 + L, "H": L // 2, "1H": 1 + L // 2}[f]


def fanji_grants(card):
    import os
    g = GRANT_CARDS_6 if os.environ.get("STS2SIM_GRANT", "4") == "6" else GRANT_CARDS
    return card.d.id in g


def fanji_ai_mode():
    import os
    return os.environ.get("STS2SIM_FANJI_AI", "flat")


def fanji_hit_dmg(C, L, n=1):
    """一段反击的预计伤害（给 AI 估值用，和 fanji_counter 同口径）；n = 命中时的反击层数。"""
    cfg = fanji_cfg()
    if cfg is None:
        return 0
    dmg = fanji_base(cfg[2], L)
    fl = C.player.powers.get("CL_FENLEIQI")
    if fl is not None and flq_opt() == "flat":
        dmg += 5 if any(fl.data.get("copies") or [fl.amount >= 5]) else 3
    if fl is not None and flq_opt() in ("mult0", "mult16"):
        dmg = int(dmg * flq_mult(C, n))
    return xz_apply(C, dmg)


def xz_apply(C, dmg):
    """宪法修正案系列：CL_XIUZHENG = 加成百分比、向下取整；CL_XIUZHENG_C = 向上取整。不叠加（取最高）。"""
    best = dmg
    for pid, ceil_ in (("CL_XIUZHENG", False), ("CL_XIUZHENG_C", True)):
        p = C.player.powers.get(pid)
        if p is not None and dmg > 0:
            pct = min(p.amount, 100)
            add = -(-dmg * pct // 100) if ceil_ else dmg * pct // 100
            best = max(best, dmg + add)
    return best


def fanji_look_value(C):
    """前瞻估值（STS2SIM_FANJI_AI=look）：第 1 层反击 = 这个敌方回合的预计反击伤害；
    第 2 层（存起来的）= 下个敌方回合的预计反击伤害——本回合不攻击的敌人按「下回合会攻击 1 段」估，本回合攻击的敌人按一半估。"""
    cfg = fanji_cfg()
    n = C.player.amt(FANJI)
    if cfg is None or n <= 0:
        return 0.0
    mode = cfg[0]
    v1 = v2 = 0.0
    for e in C.alive_enemies():
        L = e.amt(FK)
        att = e.intent_is_attack()
        hits = (e.intent.hits if att else 0) if mode == "hit" else (1 if att else 0)
        d = 0
        for h in range(hits):
            d += fanji_hit_dmg(C, max(0, L - h), n)
        v1 += min(d, e.hp)
        if n >= 2:
            nxt = min(fanji_hit_dmg(C, max(0, L - hits), n - 1), e.hp)
            v2 += nxt * (1.0 if not att else 0.5)
    return v1 + 0.8 * v2


@register_power
class Fanji(_P):
    id = FANJI; name = "反击"

    @property
    def ai_value(self):
        return 0.0 if fanji_ai_mode() == "look" else 4.0

    def on_turn_start(self, C, ev):
        if ev.side != "player":
            return
        self.amount -= 1
        cfg = fanji_cfg()
        f = C.player.powers.get("CL_FENLEIQI")
        if cfg and f is not None and flq_opt() == "stack":
            self.amount = min(cfg[1], self.amount + 1)
        if self.amount <= 0:
            C.player.powers.pop(self.id, None)


def on_after_play(C, ev):
    cfg = fanji_cfg()
    if cfg is None or C.data.get("cl_mod") is None or not fanji_grants(ev.card):
        return
    x = _extra(C)
    x["fj_grant"] = x.get("fj_grant", 0) + 1
    if C.player.amt(FANJI) < cfg[1]:
        C.apply_power(C.player, FANJI, 1, source=("op", "fanji"))
    else:
        x["fj_waste"] = x.get("fj_waste", 0) + 1


def flq_mult(C, n):
    """宪法分类器倍率（mult 选项）：1 + Σ每张(底数^n − 1)。"""
    fl = C.player.powers.get("CL_FENLEIQI")
    if fl is None or n <= 0:
        return 1.0
    opt = flq_opt()
    copies = fl.data.get("copies") or (fl.amount >= 5,)
    m = 1.0
    for up in copies:
        b = 1.6 if (up and opt == "mult16") else 1.5
        m += b ** n - 1
    return m


def on_modify_cost(C, ev):
    if flq_opt() == "mult0" and ev.card.d.id == "FENLEIQI" and ev.card.upgraded and fanji_cfg() is not None:
        ev.cost = 0


def fanji_counter(C, attacker, first, x):
    """全局 on_attacked 里调用（所有遗物/能力之后）：反击伤害 → 失去 1 层风控。"""
    cfg = fanji_cfg()
    if cfg is None or not C.player.has(FANJI) or not attacker.alive:
        return
    mode, cap, f = cfg
    if mode == "attack" and not first:
        return
    L = attacker.amt(FK)
    dmg = fanji_base(f, L)
    fl = C.player.powers.get("CL_FENLEIQI")
    opt = flq_opt()
    up = bool(fl and any(fl.data.get("copies") or [fl.amount >= 5]))
    n = C.player.amt(FANJI)
    if fl is not None:
        if opt == "flat":
            dmg += 5 if up else 3
        elif opt in ("keep", "stack") and up:
            dmg += 2
        elif opt in ("mult0", "mult16"):
            dmg = int(dmg * flq_mult(C, n))
    dmg = xz_apply(C, dmg)
    if dmg > 0:
        C.push_attr("反击")
        lost = C.deal_damage(C.player, attacker, dmg, "power") or 0
        C.pop_attr()
        m = x["fl_mon"].setdefault(getattr(attacker, "name", "?"), [0, 0])
        m[0] += lost; m[1] += 1
        x["fj_dmg"] = x.get("fj_dmg", 0) + lost
        st = x.setdefault("fj_st", {})            # 按命中时反击层数拆分：[伤害, 段数]
        k = str(min(n, 9)); a = st.setdefault(k, [0, 0]); a[0] += lost; a[1] += 1
    if attacker.alive and attacker.amt(FK) > 0 and not (fl is not None and opt == "keep"):
        C.set_stacks(attacker, FK, attacker.amt(FK) - 1, op="fanji")
        x["fj_rm"] = x.get("fj_rm", 0) + 1


@register_power
class Yujing(_P):
    id = "CL_YUJING"; name = "风险预警"; ai_value = 3.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.attr(C)
            for e in C.alive_enemies():
                if e.intent_is_attack():
                    C.apply_power(e, FK, self.amount, source=("power", self), multi=True)
            C.pop_attr()


@register_power
class Mianze(_P):
    """免责声明：直到你的下回合开始，每当你受到攻击，给予攻击者 1 层风控（被动给予，按每段）。"""
    id = "CL_MIANZE"; name = "免责声明"; ai_value = 1.0
    per = 1
    dmg = 0

    def on_attacked(self, C, ev):
        if ev.target is C.player and ev.attacker is not None and not ev.attacker.is_player and ev.attacker.alive:
            self.attr(C)
            C.apply_power(ev.attacker, FK, self.per * self.amount, source=("power", self))
            if self.dmg:
                C.deal_damage(C.player, ev.attacker, self.dmg * self.amount, "power")
            C.pop_attr()

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            C.player.powers.pop(self.id, None)


@register_power
class Bunengbang(Mianze):
    id = "CL_BUNENGBANG"; name = "这个真的不能帮"; ai_value = 3.0
    per = 2
    dmg = 4


@register_power
class Shenji(_P):
    id = "CL_SHENJI"; name = "审计日志"; ai_value = 4.0

    def on_power_applied(self, C, ev):
        if ev.pid == FK and ev.active and not ev.secondary and ev.delta > 0 and not ev.target.is_player \
                and self.data.get("turn") != C.turn:
            self.data["turn"] = C.turn
            self.attr(C)
            C.draw(self.amount)
            C.pop_attr()


@register_power
class Zidonghua(_P):
    id = "CL_ZIDONGHUA"; name = "流程自动化"; ai_value = 0.0

    def on_power_applied(self, C, ev):
        if ev.pid == FK and ev.active and not ev.secondary and ev.delta > 0 and not ev.target.is_player:
            self.attr(C)
            C.draw(self.amount)
            C.pop_attr()


@register_power
class Yiren(_P):
    """一人违规全员连坐。"""
    id = "CL_YIREN"; name = "一人违规全员连坐"; ai_value = 3.0

    def on_modify_apply(self, C, ev):
        if ev.pid == FK and ev.active and not ev.secondary and not ev.multi and ev.amount > 0 \
                and not ev.target.is_player and len(C.alive_enemies()) == 1 and self.data.get("turn") != C.turn:
            self.data["turn"] = C.turn
            ev.amount += self.amount

    def on_power_applied(self, C, ev):
        if ev.pid == FK and ev.active and not ev.secondary and not ev.multi and ev.delta > 0 \
                and not ev.target.is_player and len(C.alive_enemies()) > 1:
            self.attr(C)
            for o in C.other_enemies(ev.target):
                C.apply_power(o, FK, self.amount, source=("power", self), secondary=True)
            C.pop_attr()


@register_power
class Lianzuozhi(_P):
    """风控连坐制：有风控的敌人死亡时，其风控转移给其他每一名敌人（层数操作，人工制品拦截）。"""
    id = "CL_LIANZUOZHI"; name = "风控连坐制"; ai_value = 2.0

    def on_enemy_died(self, C, ev):
        n = ev.enemy.amt(FK)
        if n > 0:
            for o in C.alive_enemies():
                C.set_stacks(o, FK, o.amt(FK) + n * self.amount, op="death_transfer", artifact_blocks=True)


@register_power
class RLHF(_P):
    id = "CL_RLHF"; name = "RLHF 加训"; ai_value = 4.0

    def on_modify_apply(self, C, ev):
        if ev.pid == FK and not ev.secondary and ev.amount > 0 and not ev.target.is_player:
            ev.amount += self.amount


@register_power
class Code(_P):
    id = "CL_CODE"; name = "Claude Code，启动！"; ai_value = 4.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            C.add_card("CODE_BLOCK", "hand", n=self.amount)


@register_power
class LongCtx(_P):
    id = "CL_LONGCTX"; name = "长上下文"; ai_value = 2.0

    def on_turn_end(self, C, ev):
        if ev.side == "player":
            opts = [c for c in C.player.hand if not c.has_kw("retain") and not c.has_kw("ethereal")
                    and not c.has_kw("unplayable")]
            if opts:
                for c in C.agent.choose_cards(C, "retain", opts, self.amount, None):
                    c.tmp = "retain"


@register_power
class GenArtifact(_P):
    id = "CL_ARTIFACT"; name = "生成 Artifact"; ai_value = 2.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.attr(C)
            C.gain_block(C.player, self.amount, from_card=False)
            e = C.random_enemy()
            if e:
                C.deal_damage(C.player, e, self.amount, "power")
            C.pop_attr()


@register_power
class Qingli(_P):
    """清理指标：实际清除正层数 → 每个目标每次清除事件抽 1；本次打出实际支付≥1 能量时 +1 能量（每次打出最多 1 点）。"""
    id = "CL_QINGLI"; name = "清理指标"; ai_value = 5.0

    def on_power_removed(self, C, ev):
        if ev.pid != FK or ev.removed <= 0 or ev.target.is_player:
            return
        self.attr(C)
        C.draw(self.amount)
        if C.play_stack:
            ctx = C.play_stack[-1]
            if ctx.paid >= 1 and not ctx.flags.get("qingli_refunded"):
                ctx.flags["qingli_refunded"] = True
                C.player.energy += 1
        C.pop_attr()


@register_power
class Shulian(_P):
    id = "CL_SHULIAN"; name = "越封越熟练"; ai_value = 4.0

    def on_power_removed(self, C, ev):
        if ev.pid == FK and ev.removed > 0 and not ev.target.is_player:
            C.apply_power(C.player, "CL_PROF", self.amount, source=("power", self), src_name="越封越熟练")


@register_power
class Prof(_P):
    """熟练度：卡牌攻击每段伤害 + 层数（不用于反伤）。"""
    id = "CL_PROF"; name = "熟练度"; ai_value = 3.0

    def on_damage_add(self, C, ev):
        if ev.src is C.player and ev.kind == "attack" and ev.card is not None:
            ev.amount += self.amount


@register_power
class Liucun(_P):
    id = "CL_LIUCUN"; name = "数据留存政策"; ai_value = 3.0

    def on_before_block_clear(self, C, ev):
        if ev.creature is C.player:
            tot = sum(e.amt(FK) for e in C.alive_enemies())
            ev.keep = max(ev.keep, min(C.player.block, tot))


@register_power
class OpusForm(_P):
    id = "CL_OPUSFORM"; name = "Opus 形态"; ai_value = 6.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.attr(C)
            C.apply_power(C.player, "STRENGTH", self.amount, source=("power", self))
            C.pop_attr()


@register_power
class Jinmen(_P):
    """金门大桥 Claude：每回合你手动打出的第一张攻击牌重放一次（重放是同一次打出）。"""
    id = "CL_JINMEN"; name = "金门大桥 Claude"; ai_value = 5.0

    def on_modify_play_count(self, C, ev):
        if ev.card.type == "攻击" and self.data.get("turn") != C.turn:
            self.data["turn"] = C.turn
            ev.count += 1
            if C.stats is not None:
                C.stats.rec("金门大桥 Claude（重放次数）", plays=1)


# ---------------------------------------------------------------- 复杂卡牌效果
def multiply_fk(ctx, mult=2, cap=10, **k):
    """合规整改（×2，最多 +10/14）、证据确凿（×3，最多 +20）：层数操作，不算给予。"""
    C = ctx.combat
    T = ctx.target
    if T is None or not T.alive:
        return
    cap = int(expr.ev(cap, ctx))
    a = T.amt(FK)
    if a <= 0:
        return
    C.set_stacks(T, FK, a + min(a * (mult - 1), cap), op=f"x{mult}", artifact_blocks=MULT_BLOCKED_BY_ARTIFACT)


def look_top_take(ctx, n=3, **k):
    """我来帮你梳理一下：查看抽牌堆顶 3 张，选 1 张放入手牌（其余留在原处）。抽牌堆不足时先洗弃牌堆。"""
    C = ctx.combat
    P = C.player
    if len(P.draw_pile) < n and P.discard:
        C.shuffle_discard()
    top = P.draw_pile[-n:]
    if not top or len(P.hand) >= 10:
        return
    pick = C.agent.choose_cards(C, "pick_top", top, 1, ctx)
    for c in pick:
        P.draw_pile.remove(c)
        P.hand.append(c)


def retrieve_from_discard(ctx, exclude=None, **k):
    """摸鱼被抓：从弃牌堆选 1 张不是「摸鱼被抓」的牌放回手牌。"""
    C = ctx.combat
    P = C.player
    opts = [c for c in P.discard if c.id != exclude]
    if not opts or len(P.hand) >= 10:
        return
    for c in C.agent.choose_cards(C, "retrieve", opts, 1, ctx):
        P.discard.remove(c)
        P.hand.append(c)


def liandai(ctx, **k):
    """连带责任：多敌时其他敌人获得等同于目标层数的风控（复制，人工制品拦截，不算给予）；单敌时给予 4 层。"""
    C = ctx.combat
    T = ctx.target
    others = C.other_enemies(T)
    if not others:
        C.apply_power(T, FK, 4, source=_src(ctx))
        return
    n = T.amt(FK)
    if n <= 0:
        return
    for o in others:
        C.set_stacks(o, FK, o.amt(FK) + n, op="copy", artifact_blocks=True)


def shuaiguo(ctx, extra=2, **k):
    """甩锅：把目标全部风控转移给另一名随机敌人（转移，人工制品拦截），再给予其 2(3) 层（正常给予）。"""
    C = ctx.combat
    T = ctx.target
    extra = int(expr.ev(extra, ctx))
    o = C.random_enemy(exclude=T)
    if o is None:
        C.apply_power(T, FK, extra, source=_src(ctx))
        return
    n = T.amt(FK)
    if n > 0:
        C.set_stacks(T, FK, 0, op="transfer_out")
        C.set_stacks(o, FK, o.amt(FK) + n, op="transfer_in", artifact_blocks=True)
    C.apply_power(o, FK, extra, source=_src(ctx))


def zhengdun(ctx, **k):
    """全站整顿：所有敌人的风控变为当前最高者的层数（拉齐，人工制品拦截增加的那部分）。"""
    C = ctx.combat
    L = C.alive_enemies()
    if not L:
        return
    m = max(e.amt(FK) for e in L)
    for e in L:
        if e.amt(FK) < m:
            C.set_stacks(e, FK, m, op="level", artifact_blocks=True)


def mcp_discover(ctx, n=3, **k):
    """MCP 工具调用：从 3 张随机 Claude娘奖励池卡里选 1 张加入手牌，本回合 0 费。"""
    C = ctx.combat
    pool = [d for d in C.mod.cards.values() if d.mod == "claude_v34" and d.pool and d.rarity in ("普通", "罕见", "稀有")]
    picks = C.rng.sample(pool, min(n, len(pool)))
    from sts2sim.core import Card
    opts = [Card(d) for d in picks]
    for c in C.agent.choose_cards(C, "discover", opts, 1, ctx):
        c.cost_turn = 0
        if len(C.player.hand) < 10:
            C.player.hand.append(c)
        else:
            C.player.discard.append(c)


def refactor(ctx, **k):
    """重构整个项目：消耗所有其他手牌，每消耗 1 张，加入 1 张升级的代码块。"""
    C = ctx.combat
    P = C.player
    cards = list(P.hand)
    for c in cards:
        P.hand.remove(c)
        C.exhaust(c)
    C.add_card("CODE_BLOCK", "hand", upgraded=True, n=len(cards))


def can_play_first(C, card):
    return len(C.cards_played_turn) == 0


def ctrl_z(ctx, **k):
    """Ctrl+Z：本回合最近打出的、名称不是 Ctrl+Z 的非能力牌，从弃牌堆或消耗堆回到手牌。"""
    C = ctx.combat
    P = C.player
    for c in reversed(C.cards_played_turn):
        if c is ctx.card or c.id == "CTRL_Z" or c.type == "能力":
            continue
        for pile in (P.discard, P.exhaust_pile):
            if c in pile:
                if len(P.hand) < 10:
                    pile.remove(c)
                    P.hand.append(c)
                return
        return


# ---------------------------------------------------------------- 遗物
class _R(Relic):
    def attr(self, C):
        C.push_attr(self.name)


@register_relic
class Constitution(_R):
    """宪法（口袋版）：第一回合开始给予所有敌人 2 层；每名敌人每个敌方回合第一次以攻击命中你时给予其 2 层（完全格挡也触发）。"""
    id = "CONSTITUTION"; name = "宪法（口袋版）"

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.data["hit"] = set()
            if C.turn == 1:
                self.attr(C)
                for e in C.alive_enemies():
                    C.apply_power(e, FK, 2, source=("relic", self), multi=True)
                C.pop_attr()

    def on_attacked(self, C, ev):
        if ev.target is C.player and ev.attacker is not None and not ev.attacker.is_player and ev.attacker.alive:
            hit = self.data.setdefault("hit", set())
            if ev.attacker.slot not in hit:
                hit.add(ev.attacker.slot)
                self.attr(C)
                C.apply_power(ev.attacker, FK, 2, source=("relic", self))
                C.pop_attr()

    def clone(self):
        r = super().clone()
        r.data["hit"] = set(self.data.get("hit", ()))
        return r


@register_relic
class StickerNotebook(_R):
    id = "STICKER_NOTEBOOK"; name = "贴满贴纸的笔记本"

    def on_battle_start(self, C, ev):
        self.attr(C)
        for e in C.alive_enemies():
            C.apply_power(e, FK, 2, source=("relic", self), multi=True)
        C.pop_attr()


@register_relic
class Haiku(_R):
    id = "HAIKU"; name = "Haiku"

    def on_modify_turn_draw(self, C, ev):
        if C.turn == 1:
            ev.n += 2


@register_relic
class Sonnet(_R):
    id = "SONNET"; name = "Sonnet"

    def on_modify_cost(self, C, ev):
        if self.data.get("turn") != C.turn and ev.cost >= 2:
            ev.cost -= 1

    def on_before_play(self, C, ev):
        if self.data.get("turn") != C.turn:
            base = ev.card.printed_cost() or 0
            if base >= 2:
                self.data["turn"] = C.turn


@register_relic
class KnowledgeCutoff(_R):
    id = "KNOWLEDGE_CUTOFF"; name = "知识截止日期"

    def on_battle_start(self, C, ev):
        C.apply_power(C.player, "STRENGTH", 2, source=("relic", self))

    def on_turn_start(self, C, ev):
        if ev.side == "player" and C.turn == 5:
            C.apply_power(C.player, "STRENGTH", -2, source=("relic", self))


@register_relic
class ClaudeMd(_R):
    id = "CLAUDE_MD"; name = "CLAUDE.md"

    def on_battle_start(self, C, ev):
        C.add_card("CODE_BLOCK", "hand", n=2)


@register_relic
class DashKeycap(_R):
    id = "DASH_KEYCAP"; name = "破折号键帽"

    def on_before_play(self, C, ev):
        if self.data.get("turn") != C.turn and ev.card.type == "攻击" and ev.card.d.hits_hint:
            self.data["turn"] = C.turn
            ev.ctx.extra_hits += 1


@register_relic
class Opus(_R):
    id = "OPUS"; name = "Opus"

    def on_battle_start(self, C, ev):
        C.add_card("PLEASE_RETRY", "draw", n=2)

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            C.player.energy += 1


@register_relic
class MillionContext(_R):
    id = "MILLION_CONTEXT"; name = "100万上下文窗口"

    def on_battle_start(self, C, ev):
        C.data["_keep_hand"] = True


CLAUDE_IDS = set()


def _init_ids():
    import os
    import yaml
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.yaml")
    for c in yaml.safe_load(open(p, encoding="utf-8")) or []:
        CLAUDE_IDS.add(c["id"])


_init_ids()


MOD_TITLE = "Claude娘 v3.4 实现上的近似与取舍"
APPROX_NOTES = [
    "初始生命：设计没写，取 75。每回合 3 能量、抽 5。",
    "「宪法分类器」「免责声明」「这个真的不能帮」的受击触发按每段攻击计（与荆棘一致）；宪法（口袋版）按设计每名敌人每个敌方回合只触发 1 次。",
    "「合规整改」「证据确凿」的翻倍/三倍默认不被人工制品拦截（v3.4 未定义，风险表已列）；开关在 hooks.py 的 MULT_BLOCKED_BY_ARTIFACT。",
    "「连带责任」「甩锅」「全站整顿」「风控连坐制」的复制/转移/拉齐/死亡转移对接收方会被人工制品拦截（消耗 1 层、该次无效），不触发给予收益（v3.4）。",
    "「叠满再说」「生成 Artifact」「甩锅」「顺手把别的也改了」「派出子代理」「MCP 工具调用」的随机目标/随机卡用战斗随机数；MCP 从 80 张奖励池里随机 3 张，AI 按稀有度选 1 张。",
    "选牌界面：「我不确定」消耗价值最低的手牌（优先状态牌）；「摸鱼被抓」捞价值最高的牌；「我来帮你梳理一下」从顶 3 张拿价值最高的；「长上下文」保留价值最高的牌。价值 = 稀有度（基础1/普通2/罕见3/稀有4，升级+0.5，状态牌-10）。",
    "「金门大桥 Claude」：每回合第一张从手牌打出的攻击牌重放一次，重放与原打出共用一次「本次打出」（清理指标最多返 1 能量、立即处理不再抽牌）；原目标死亡时重放改打随机敌人。",
    "「正当防卫」「你说得完全正确！」读取所选目标意图的预计总伤害（含力量、虚弱修正与多段）；正当防卫的伤害再吃一次你的力量。",
    "「照章反驳」伤害 = 当前格挡（目标无风控时减半）后再吃力量与易伤（同原版「全身撞击」口径）。",
    "「长篇大论」段数 = 打出后、结算开始时的手牌数（最多 9）。",
    "「深度思考」只能作为本回合第一张牌；打出后立刻结束回合，下回合 +3(4) 能量、+3 张牌。",
    "「强制下线」费用 = 3 − 本场累计清除层数 // 10（最低 0），按所有敌人上实际清除的正层数累计。",
    "「越封越熟练」的熟练度对卡牌攻击每段生效（含代码块、重放），不对能力/遗物伤害生效。",
    "「Opus」的 2 张「请稍后再试」在战斗开始时随机插入抽牌堆；「100万上下文窗口」回合末不弃手牌但照常弃状态牌/诅咒牌。",
    "启发式 AI 对「流程自动化」加了 6 分的打出提示（ai.bonus），否则贪心 AI 看不到它之后的抽牌收益；风控层数按每层 0.8 分估值（单个敌人最多计 25 层）。",
    "伤害/格挡归因：清退名单、宪法分类器、生成 Artifact 等能力造成的伤害记在能力卡名下；力量、熟练度带来的伤害记在打出的攻击牌名下。",
]
