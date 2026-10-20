"""药水：与卡牌共用效果 op（YAML 的 effects），由 mod 的 potions.yaml 定义。

potions.yaml 例：
  - {id: FIRE_POTION, target: enemy, effects: [{op: damage, amount: 20, kind: power}]}
名字/稀有度/描述默认从 spire-codex potions.json 按 id 自动补全（catalog.py），mod 只需写效果。
使用：Combat.use_potion(i, target)；AI 在 base.Agent.use_potions 里决定何时喝。
"""
from .cards import CardDef, PlayCtx, run_effects

POTION_DEFS = {}


class PotionDef(CardDef):
    def __init__(self, raw, mod_name=""):
        raw = dict(raw)
        raw.setdefault("type", "药水")
        raw.setdefault("cost", 0)
        super().__init__(raw, mod_name)


def register_potions(lst, mod_name, catalog=None):
    for raw in lst or []:
        raw = dict(raw)
        if catalog is not None and raw["id"] in catalog:
            info = catalog[raw["id"]]
            raw.setdefault("name", info.get("name", raw["id"]))
            raw.setdefault("rarity", info.get("rarity", "普通"))
            raw.setdefault("text", info.get("description", ""))
        POTION_DEFS[raw["id"]] = PotionDef(raw, mod_name)


class _PotionCard:
    """让药水能走卡牌的效果解释器（PlayCtx 需要一张「卡」）。"""
    __slots__ = ("d", "upgraded", "vars", "base_name", "name", "id")

    def __init__(self, d):
        self.d = d
        self.upgraded = False
        self.vars = d.vars
        self.base_name = d.name
        self.name = d.name
        self.id = d.id


def use_potion(C, idx, target=None):
    P = C.player
    pid = P.potions.pop(idx)
    d = POTION_DEFS[pid]
    from .core import Card
    card = Card(d)
    ctx = PlayCtx(C, card, target, 0, free=True)
    C.push_attr("药水：" + d.name)
    if C.stats is not None:
        C.stats.rec("药水：" + d.name, plays=1, energy=0)
    C.say(f"使用药水 {d.name}" + (f" → {target.name}" if target is not None else ""))
    run_effects(ctx, d.effects)
    C.pop_attr()
    C.emit("potion_used", potion=pid)
