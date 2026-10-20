"""敌人专属能力（按 spire-codex powers.json 官方描述 + 反编译 Powers/*.cs 实现；不确定处在 doc 里注明）。"""
from .core import Power, register_power


def _alive_owner(p):
    return p.owner is not None and p.owner.alive


@register_power
class Constrict(Power):
    """紧缠（玩家身上）：施加者存活时，你的回合结束受到 X 点伤害。"""
    id = "CONSTRICT"; name = "紧缠"; kind = "debuff"; ai_value = 1.5

    def on_turn_end(self, C, ev):
        if ev.side == "player" and ev.creature is self.owner:
            if any(e.m.id == "SLITHERING_STRANGLER" for e in C.alive_enemies()):
                C.deal_damage(None, self.owner, self.amount, "power")


@register_power
class PaperCuts(Power):
    """纸伤难愈：它对你造成未被格挡的伤害时，你失去 X 点最大生命。"""
    id = "PAPER_CUTS"; name = "纸伤难愈"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.attacker is self.owner and ev.target is C.player and ev.unblocked > 0:
            P = C.player
            P.max_hp = max(1, P.max_hp - self.amount)
            P.hp = min(P.hp, P.max_hp)


@register_power
class Shrink(Power):
    """缩小：攻击伤害减少 30%。"""
    id = "SHRINK"; name = "缩小"; kind = "debuff"

    def on_damage_mul(self, C, ev):
        if ev.src is self.owner and ev.kind == "attack":
            ev.amount *= 0.7


@register_power
class Slow(Power):
    """缓慢：你本回合每打出一张牌，它本回合受到的攻击伤害 +10%。"""
    id = "SLOW"; name = "缓慢"; kind = "debuff"

    def on_damage_mul(self, C, ev):
        if ev.target is self.owner and ev.kind == "attack" and ev.src is not None and ev.src.is_player:
            ev.amount *= 1 + 0.1 * len(C.cards_played_turn)


@register_power
class Suck(Power):
    """吮吸：每次造成未被格挡的伤害，获得 X 点力量。"""
    id = "SUCK"; name = "吮吸"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.attacker is self.owner and ev.target is C.player and ev.unblocked > 0:
            C.apply_power(self.owner, "STRENGTH", self.amount, source=("enemy", self.owner))


class _ThisTurn(Power):
    kind = "debuff"; ai_value = 3.0

    def on_turn_end(self, C, ev):
        if ev.side == "player" and ev.creature is self.owner:
            self.owner.powers.pop(self.id, None)


@register_power
class Tangled(_ThisTurn):
    """缠结：本回合攻击牌费用 +1。"""
    id = "TANGLED"; name = "缠结"

    def on_modify_cost(self, C, ev):
        if ev.card.type == "攻击" and ev.cost is not None:
            ev.cost += self.amount


@register_power
class Tender(_ThisTurn):
    """柔嫩：本回合你每打出一张牌，失去 1 力量和 1 敏捷。"""
    id = "TENDER"; name = "柔嫩"

    def on_after_play(self, C, ev):
        C.apply_power(self.owner, "STRENGTH", -1, source=("enemy", None))
        C.apply_power(self.owner, "DEXTERITY", -1, source=("enemy", None))


@register_power
class Ringing(_ThisTurn):
    """昏眩：本回合你只能打出 1 张牌。"""
    id = "RINGING"; name = "昏眩"

    def on_can_play(self, C, ev):
        if len(C.cards_played_turn) >= 1:
            ev.ok = False


@register_power
class Smoggy(Power):
    """烟雾弥漫：每回合你只能打出 1 张技能牌。"""
    id = "SMOGGY"; name = "烟雾弥漫"; kind = "debuff"; ai_value = 3.0

    def on_can_play(self, C, ev):
        if ev.card.type == "技能" and any(c.type == "技能" for c in C.cards_played_turn):
            ev.ok = False


@register_power
class Hex(Power):
    """恶咒（玩家身上）：施加者存活时，你的所有牌拥有虚无。实现：回合结束时把手牌当作虚无消耗。"""
    id = "HEX"; name = "恶咒"; kind = "debuff"; ai_value = 4.0

    def on_turn_end(self, C, ev):
        if ev.side == "player" and ev.creature is self.owner:
            if not any(e.m.id == "SPECTRAL_KNIGHT" for e in C.alive_enemies()):
                return
            P = self.owner
            for c in list(P.hand):
                if not (c.has_kw("retain") or c.tmp == "retain"):
                    P.hand.remove(c)
                    C.exhaust(c)


@register_power
class PersonalHive(Power):
    """人体蜂房：每次被攻击命中，往你的抽牌堆加 1 张晕眩。"""
    id = "PERSONAL_HIVE"; name = "人体蜂房"; kind = "buff"

    def on_attacked(self, C, ev):
        if ev.target is self.owner and ev.attacker is not None and ev.attacker.is_player:
            C.add_card("DAZED", to="draw")


@register_power
class Burrowed(Power):
    """埋地：格挡不会在它的回合开始时移除；格挡被打光则被击晕（并失去埋地）。"""
    id = "BURROWED"; name = "埋地"; kind = "buff"

    def on_enemy_block_clear(self, C, ev):
        if ev.creature is self.owner:
            ev.keep = 10 ** 6

    def on_attacked(self, C, ev):
        o = self.owner
        if ev.target is o and o.block <= 0 and ev.damage > 0 and o.alive:
            o.powers.pop(self.id, None)
            if hasattr(o, "stun"):
                o.stun()


@register_power
class EscapeArtist(Power):
    """逃脱大师：X 回合后离开战斗（不算击杀）。"""
    id = "ESCAPE_ARTIST"; name = "逃脱大师"; kind = "buff"

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            self.amount -= 1
            if self.amount <= 0:
                self.owner.alive = False
                if not C.alive_enemies():
                    C.result = "win"


@register_power
class Nemesis(Power):
    """天罚：每两个回合结束时获得 1 层无实体。"""
    id = "NEMESIS"; name = "天罚"; kind = "buff"

    def on_turn_end(self, C, ev):
        if ev.creature is self.owner:
            self.data["n"] = self.data.get("n", 0) + 1
            if self.data["n"] % 2 == 0:
                C.apply_power(self.owner, "INTANGIBLE", 1, source=("enemy", self.owner))


@register_power
class CrabRage(Power):
    """蟹之怒：有盟友死亡时获得 6 力量和 99 格挡。"""
    id = "CRAB_RAGE"; name = "蟹之怒"; kind = "buff"

    def on_enemy_died(self, C, ev):
        if ev.enemy is not self.owner and self.owner.alive:
            C.apply_power(self.owner, "STRENGTH", 6, source=("enemy", self.owner))
            self.owner.block += 99


@register_power
class Ravenous(Power):
    """饥饿：有其他敌人死亡时吃下尸体：本回合被击晕，获得 X 点力量。"""
    id = "RAVENOUS"; name = "饥饿"; kind = "buff"

    def on_enemy_died(self, C, ev):
        o = self.owner
        if ev.enemy is not o and o.alive:
            C.apply_power(o, "STRENGTH", max(1, self.amount), source=("enemy", o))
            if hasattr(o, "stun"):
                o.stun()


@register_power
class BackAttack(Power):
    """后方攻击：伤害 +50%（近似：始终视为从后方攻击）。"""
    id = "BACK_ATTACK_LEFT"; name = "后方攻击"; kind = "buff"

    def on_damage_mul(self, C, ev):
        if ev.src is self.owner and ev.kind == "attack":
            ev.amount *= 1.5


@register_power
class BackAttackR(BackAttack):
    id = "BACK_ATTACK_RIGHT"


IMPLEMENTED_HERE = ["CONSTRICT", "PAPER_CUTS", "SHRINK", "SLOW", "SUCK", "TANGLED", "TENDER", "RINGING", "SMOGGY", "HEX",
                    "PERSONAL_HIVE", "BURROWED", "ESCAPE_ARTIST", "NEMESIS", "CRAB_RAGE", "RAVENOUS", "BACK_ATTACK_LEFT",
                    "BACK_ATTACK_RIGHT"]
