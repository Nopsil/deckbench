"""通用能力（以 spire-codex powers.json 的官方描述为准；数值不确定处在 doc 里注明）。

伤害/格挡相关的力量、敏捷、易伤、虚弱、脆弱、人工制品、无实体、滑溜、难以杀灭、硬化外壳
在 core.Combat 里直接结算（速度考虑），这里只登记类型与 AI 估值，以及有回合触发的能力。
"""
from .core import Power, register_power


@register_power
class Strength(Power):
    id = "STRENGTH"; name = "力量"; kind = "buff"; ai_value = 3.0; can_go_negative = True


@register_power
class Dexterity(Power):
    id = "DEXTERITY"; name = "敏捷"; kind = "buff"; ai_value = 2.5; can_go_negative = True


@register_power
class Vulnerable(Power):
    id = "VULNERABLE"; name = "易伤"; kind = "debuff"; ai_value = 2.5; decays = True


@register_power
class Weak(Power):
    id = "WEAK"; name = "虚弱"; kind = "debuff"; ai_value = 2.0; decays = True


@register_power
class Frail(Power):
    id = "FRAIL"; name = "脆弱"; kind = "debuff"; ai_value = 1.5; decays = True


@register_power
class Artifact(Power):
    id = "ARTIFACT"; name = "人工制品"; kind = "buff"


@register_power
class Intangible(Power):
    id = "INTANGIBLE"; name = "无实体"; kind = "buff"

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)


@register_power
class Plating(Power):
    """覆甲：在拥有者回合结束时获得 X 格挡，回合开始时 -1。"""
    id = "PLATING"; name = "覆甲"; kind = "buff"

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            C.gain_block(self.owner, self.amount, from_card=False)

    def on_turn_start(self, C, ev):
        if ev.creature is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)


@register_power
class Thorns(Power):
    id = "THORNS"; name = "荆棘"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.target is self.owner and ev.attacker is not None and ev.attacker.alive and ev.attacker is not self.owner:
            C.push_attr(self.src or "荆棘")
            C.deal_damage(self.owner, ev.attacker, self.amount, "power")
            C.pop_attr()


@register_power
class Ritual(Power):
    """RitualPower.cs：敌人给自己施加的那个回合结束时不触发（WasJustAppliedByEnemy）。"""
    id = "RITUAL"; name = "仪式"; kind = "buff"

    def on_power_applied(self, C, ev):
        if ev.target is self.owner and ev.pid == self.id and not self.owner.is_player:
            self.data["just"] = True

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            if self.data.pop("just", False):
                return
            C.apply_power(self.owner, "STRENGTH", self.amount, source=("enemy", self.owner))


@register_power
class Territorial(Ritual):
    id = "TERRITORIAL"; name = "领地意识"

    def on_power_applied(self, C, ev):
        pass


@register_power
class HighVoltage(Ritual):
    id = "HIGH_VOLTAGE"; name = "高电压"

    def on_power_applied(self, C, ev):
        pass


@register_power
class Vigor(Power):
    id = "VIGOR"; name = "活力"; kind = "buff"

    def on_after_play(self, C, ev):
        if self.owner.is_player and ev.card.type == "攻击":
            self.owner.powers.pop(self.id, None)


@register_power
class Poison(Power):
    """中毒：拥有者回合开始时失去等量生命，然后 -1。"""
    id = "POISON"; name = "中毒"; kind = "debuff"; ai_value = 1.0

    def on_turn_start(self, C, ev):
        if ev.creature is self.owner:
            C.push_attr(self.src or "中毒")
            C.lose_hp(self.owner, self.amount, C.player, "hp_loss")
            if C.stats is not None and not self.owner.is_player:
                C.stats.rec(self.src or "中毒", dmg=min(self.amount, max(0, self.owner.hp + self.amount)))
            C.pop_attr()
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)


@register_power
class CurlUp(Power):
    """蜷身：第一次受到攻击伤害时获得 X 格挡（每场一次）。"""
    id = "CURL_UP"; name = "蜷身"; kind = "buff"

    def on_damage_taken(self, C, ev):
        if ev.target is self.owner and ev.kind == "attack":
            C.gain_block(self.owner, self.amount, from_card=False)
            self.owner.powers.pop(self.id, None)


@register_power
class Skittish(Power):
    """胆小：每回合第一次被命中时获得 X 格挡。"""
    id = "SKITTISH"; name = "胆小"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.target is self.owner and not self.data.get("used"):
            self.data["used"] = True
            C.gain_block(self.owner, self.amount, from_card=False)

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.data["used"] = False


@register_power
class Enrage(Power):
    """激怒：玩家每打出一张技能牌，获得 X 力量（描述写 2；层数按数据）。"""
    id = "ENRAGE"; name = "激怒"; kind = "buff"

    def on_after_play(self, C, ev):
        if ev.card.type == "技能" and self.owner.alive:
            C.apply_power(self.owner, "STRENGTH", self.amount or 2, source=("enemy", self.owner))


@register_power
class HardenedShell(Power):
    id = "HARDENED_SHELL"; name = "硬化外壳"; kind = "buff"

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.data["lost"] = 0


@register_power
class Rampart(Power):
    """盾墙：玩家回合开始时，拥有者获得 25 格挡（原文数值）。"""
    id = "RAMPART"; name = "盾墙"; kind = "buff"

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            C.gain_block(self.owner, 25, from_card=False)


@register_power
class Asleep(Power):
    """沉睡（AsleepPower.cs）：受到未被格挡的伤害 → 失去覆甲、被击晕，下一招接 SLASH_MOVE；
    自己回合结束层数 -1，到 0 苏醒。招式本身由状态机（HasPower<AsleepPower> 条件）决定。"""
    id = "ASLEEP"; name = "沉睡"; kind = "buff"
    wake_state = "SLASH_MOVE"

    def on_damage_taken(self, C, ev):
        if ev.target is self.owner and ev.amount > 0 and self.id in self.owner.powers:
            o = self.owner
            o.powers.pop("PLATING", None)
            o.powers.pop(self.id, None)
            if hasattr(o, "stun"):
                o.stun(self.wake_state if getattr(o.m, "ai", None) and self.wake_state in o.m.ai["states"] else None)

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)
                self.owner.powers.pop("PLATING", None)


@register_power
class Slumber(Asleep):
    """熟睡（SlumberPower.cs）：每次受到未被格挡的伤害层数 -1，到 0 时被击晕、下一招接 ROLL_OUT_MOVE；回合结束 -1，到 0 苏醒。"""
    id = "SLUMBER"; name = "熟睡"
    wake_state = "ROLL_OUT_MOVE"

    def on_damage_taken(self, C, ev):
        if ev.target is self.owner and ev.amount > 0 and self.id in self.owner.powers:
            self.amount -= 1
            if self.amount <= 0:
                o = self.owner
                o.powers.pop(self.id, None)
                if hasattr(o, "stun"):
                    o.stun(self.wake_state if getattr(o.m, "ai", None) and self.wake_state in o.m.ai["states"] else None)

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.powers.pop(self.id, None)


@register_power
class Barricade(Power):
    id = "BARRICADE"; name = "壁垒"; kind = "buff"; ai_value = 10


@register_power
class Minion(Power):
    id = "MINION"; name = "爪牙"; kind = "buff"


@register_power
class Slippery(Power):
    id = "SLIPPERY"; name = "滑溜"; kind = "buff"


@register_power
class HardToKill(Power):
    id = "HARD_TO_KILL"; name = "难以杀灭"; kind = "buff"


# ---------- 玩家常用临时能力（mod 通用）
@register_power
class NextTurnEnergy(Power):
    id = "NEXT_ENERGY"; name = "下回合能量"; kind = "buff"; ai_value = 4.0

    def on_turn_start(self, C, ev):
        if ev.side == "player" and self.owner.is_player:
            C.push_attr(self.src or self.name)
            self.owner.energy += self.amount
            C.pop_attr()
            self.owner.powers.pop(self.id, None)


@register_power
class NextTurnDraw(Power):
    id = "NEXT_DRAW"; name = "下回合抽牌"; kind = "buff"; ai_value = 2.0

    def on_modify_turn_draw(self, C, ev):
        ev.n += self.amount
        self.owner.powers.pop(self.id, None)


@register_power
class NextTurnBlock(Power):
    id = "NEXT_BLOCK"; name = "下回合格挡"; kind = "buff"; ai_value = 0.8

    def on_turn_start(self, C, ev):
        if ev.side == "player" and self.owner.is_player:
            C.push_attr(self.src or self.name)
            C.gain_block(self.owner, self.amount, from_card=False)
            C.pop_attr()
            self.owner.powers.pop(self.id, None)


@register_power
class NoDraw(Power):
    """本回合不能再抽牌（战斗专注）。"""
    id = "NO_DRAW"; name = "不能抽牌"; kind = "debuff"

    def on_turn_end(self, C, ev):
        if ev.side == "player":
            self.owner.powers.pop(self.id, None)


@register_power
class TempThorns(Power):
    """本回合受到攻击时反伤（火焰屏障）。"""
    id = "FLAME_BARRIER"; name = "火焰屏障"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.target is self.owner and ev.attacker is not None and ev.attacker.alive:
            C.push_attr(self.src or self.name)
            C.deal_damage(self.owner, ev.attacker, self.amount, "power")
            C.pop_attr()

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            self.owner.powers.pop(self.id, None)


@register_power
class DemonForm(Power):
    id = "DEMON_FORM"; name = "恶魔形态"; kind = "buff"; ai_value = 6.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            C.push_attr(self.src or self.name)
            C.apply_power(self.owner, "STRENGTH", self.amount, source=("power", self))
            C.pop_attr()


@register_power
class NoxiousFumes(Power):
    id = "NOXIOUS_FUMES"; name = "毒雾"; kind = "buff"; ai_value = 5.0

    def on_turn_start(self, C, ev):
        if ev.side == "player":
            for e in C.alive_enemies():
                C.apply_power(e, "POISON", self.amount, source=("power", self), multi=True, src_name=self.src)
