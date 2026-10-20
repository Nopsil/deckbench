# 写自己的 mod / Writing your own mod

[← 返回 README](../README.md) · [开发者文档](DEVELOPER.md)

这份指南讲怎么用 **YAML + 少量 Python 钩子** 给 DeckBench 的 **YAML 战斗模拟器** 写卡牌、能力、遗物、卡组和实验。
写好的 mod 可以放在 `mods/<名字>/`，也可以打成 zip 在图形界面里上传（界面里只用于战斗实验）。
示例：`gui/examples/demo_mod/`（最小示例）、`mods/claude_v34/`（完整角色）。

*How to write cards, powers, relics, decks and experiments for the YAML combat simulator with YAML plus small Python hooks. Put mods in `mods/<name>/` or upload a zip in the GUI (combat experiments only). Examples: `gui/examples/demo_mod/`, `mods/claude_v34/`.*

> 注意：只写你自己原创的内容。不要把游戏原版卡牌的文字、数值表或美术放进 mod 再提交到本仓库（见 [CONTRIBUTING.md](../CONTRIBUTING.md)）。
> 要和原版角色对比，需要本机的原版对照组 `mods/vanilla/`，见 [DEVELOPER.md · 旧版 YAML 战斗模拟器](DEVELOPER.md#旧版-yaml-战斗模拟器--legacy-yaml-combat-simulator)。

## 写一个 mod / Writing a mod

1. 建 `mods/<名字>/mod.yaml`：

```yaml
name: my_mod
title: 我的 mod
cards: [cards.yaml]
decks: [decks.yaml]
potions: [potions.yaml]        # 可选
hooks: hooks.py                # 可选：自定义能力、遗物、py 效果
characters:
  hero: {name: 新角色, hp: 75, energy: 3, relics: [MY_RELIC]}
```

2. 卡表 `cards.yaml`（每张一项）：

```yaml
- id: MY_STRIKE
  name: 新打击
  type: 攻击            # 攻击 / 技能 / 能力 / 状态 / 诅咒
  rarity: 普通
  cost: 1               # null = 不能被打出；"X" = X 费
  target: enemy         # enemy / self / none / all
  keywords: [exhaust]   # exhaust ethereal retain innate unplayable replay
  vars: {d: 7}
  upgrade: {vars: {d: 10}, cost: 0, add: [retain]}
  effects:
    - {op: damage, amount: d}
    - {op: apply, power: WEAK, amount: 1}
    - {op: draw, n: 1, if: "hand_size() < 5"}
  ai: {bonus: 0}        # 可选：给启发式 AI 的额外分（难以即时估值的引擎牌）
```

效果 op：`damage`（amount、hits、target: target/all/random/others/self、kind）、`block`、`apply`、`remove_power`、`set_stacks`、
`draw`、`energy`、`lose_hp`、`heal`、`add_card`、`set`、`if`、`foreach`、`repeat`、`exhaust_choice`、`discard_choice`、
`return_to_hand`、`end_turn`、`py`（调用 hooks.py 里的函数）。
表达式可用：卡牌 vars 与局部变量、`T`（目标）、`P`（玩家）、`C`、`card`、`ctx`、`stacks(T,'ID')`、`intent_damage`、`attacking`、
`hand_size`、`n_enemies`、`energy`、`block`、`hand_has`、`turn`，以及 mod 用 `expr.register_helper` 注册的函数（Claude娘：`fk`、`fk_total`、`fk_enemies`）。

3. 能力 / 遗物写在 hooks.py：

```python
from sts2sim.core import Power, register_power
from sts2sim.relics import Relic, register_relic

@register_power
class MyPower(Power):
    id = "MY_POWER"; name = "我的能力"; kind = "buff"; ai_value = 3.0
    def on_after_play(self, C, ev):
        if ev.card.type == "攻击":
            C.gain_block(self.owner, self.amount)

@register_relic
class MyRelic(Relic):
    id = "MY_RELIC"; name = "我的遗物"
    def on_battle_start(self, C, ev):
        C.apply_power(C.player, "STRENGTH", 1, source=self.src())
```

hooks.py 里还可以定义 `state_value(C)`（给 AI 的局面估值加分，例如「每层风控值 0.8」）、`card_worth(C, card)`、`APPROX_NOTES`（写进报告近似清单）。

4. 卡组 `decks.yaml`：

```yaml
- {id: hero_a2, name: 新角色·示例, character: hero, stage: 第2幕, acts: [2], auto_upgrade: 3,
   cards: [打击×4, 防御×4, 新打击+, 痛击], relics: [MY_RELIC], potions: [FIRE_POTION]}
- {id: probe_x, name: 探针·某循环, character: hero, stage: 循环探针, acts: [1], expect: 不应无限, cards: [...]}
```

`名×N` 表示 N 张、`名+` 表示升级；`auto_upgrade: N` 自动升级前 N 张非基础牌；`expect` 写「允许的有引擎无限」或「不应无限」，报告会自动判定。

5. 实验 `experiments/xxx.yaml`：`mods`、`decks`、`rooms`（普通/精英/首领/弱怪）、`fights`、`seed`、`agent`、`groups`（报告分组）、
`extra`（探针：指定卡组打木桩 `DUMMY` 或指定遭遇）、`summary_md`（插到报告开头的结论）。


## 事件总线（钩子）/ Event bus (hooks)

`combat.emit("事件名", **参数)` 依次调用 遗物 → 玩家能力 → 敌人能力 → 各 mod 的 hooks 模块 上的 `on_<事件名>(C, ev)`，
钩子可以改 `ev` 上的字段（例如 `ev.amount`、`ev.cost`、`ev.ok`）。常用事件：
`battle_start`、`turn_start(side, creature)`、`turn_end`、`card_drawn`、`before_play`、`after_play`、`modify_play_count`（重放）、
`damage_add` / `damage_mul`（伤害修正）、`attacked`（每段攻击结算后，带 unblocked）、`damage_taken`、
`modify_apply` / `power_applied` / `power_removed`（能力施加，带 active/secondary/multi 标记）、`block_gained`、`card_exhausted`、
`modify_cost`、`can_play`、`modify_turn_draw`、`enemy_died`、`player_would_die`、`potion_used`。

