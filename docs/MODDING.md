# 写自己的 mod / Writing your own mod

[← 返回 README](../README.md) · [开发者文档](DEVELOPER.md)

这份指南讲怎么用 YAML 写卡牌、能力、遗物和角色。前半部分是**整局用的 YAML mod**（新，不用写代码，图形界面里也能填表做）；
后半部分是旧版 **YAML 战斗模拟器** 的写法（YAML + 少量 Python 钩子，卡组和实验）。
示例：`gui/examples/demo_mod/`（最小示例）、`mods/claude_v34/`（完整角色）。

*How to write cards, powers, relics and characters in YAML. The first part covers YAML mods for full runs (new; no code, also doable with forms in the GUI); the second part is the legacy YAML combat simulator (YAML plus small Python hooks, decks and experiments). Examples: `mods/claude_yaml/` (full runs), `gui/examples/demo_mod/`, `mods/claude_v34/` (combat simulator).*

> 注意：只写你自己原创的内容。不要把游戏原版卡牌的文字、数值表或美术放进 mod 再提交到本仓库（见 [CONTRIBUTING.md](../CONTRIBUTING.md)）。
> 要和原版角色对比，需要本机的原版对照组 `mods/vanilla/`，见 [DEVELOPER.md · 旧版 YAML 战斗模拟器](DEVELOPER.md#旧版-yaml-战斗模拟器--legacy-yaml-combat-simulator)。

## 整局用的 YAML mod（新） / YAML mods for full runs (new)

从 0.1.4 起，同一种 YAML 格式**也能直接在整局模拟里用**：批量整局、单卡 A/B、指定种子、各种 AI（推荐「通用 AI」`modai`）都认。不用写 Python，也不用编译 DLL。
旧的 YAML mod（只给战斗实验用的）照样能用，新加的键旧模拟器会忽略。完整示例：`mods/claude_yaml/`（Claude娘 v3.5 的数据版）。
不想写文件也可以用图形界面的 **「模组编辑器」** 填表，见下文。

*Since 0.1.4 the same YAML format also runs in full-run simulation: batch runs, one-card A/B, game seeds and every AI (the character-agnostic `modai` is recommended). No Python and no DLL needed. Old combat-only YAML mods still work; the legacy simulator ignores the new keys. Full example: `mods/claude_yaml/`. Prefer forms? Use the GUI's **Mod editor** (below).*

### 最小例子 / Minimal example

`mods/my_mod/mod.yaml`：

```yaml
name: my_mod
prefix: MyMod                  # 游戏里的 ID = 前缀 + 你写的 ID，避免和别的 mod 撞名
characters:
  MyHero:
    name: 我的角色
    hp: 75
    energy: 3
    gold: 99
    starting_deck: [STRIKE×5, DEFEND×5]
    relics: [LUCKY_COIN]
cards: [cards.yaml]
powers: [powers.yaml]          # 也可以直接在这里写列表
relics: [relics.yaml]
```

`cards.yaml`（字段和旧格式一样，中英文写法都认：`type: 攻击` 或 `Attack`，`rarity: 普通` 或 `Common`）：

```yaml
- {id: STRIKE, type: 攻击, rarity: 基础, cost: 1, target: enemy, vars: {dmg: 6}, upgrade: {vars: {dmg: 9}},
   effects: [{op: damage, amount: dmg}]}
- id: CHARGE_UP
  type: 能力
  rarity: 罕见
  cost: 1
  target: self
  vars: {n: 3}
  effects: [{template: gain_power, power: STEADY, amount: n}]
```

`powers.yaml` / `relics.yaml`：能力和遗物用「触发器」写——**什么时候**（`on:` 或模板）+ **做什么**（`do:` 里的效果，和卡牌效果一样）：

```yaml
# powers.yaml
- id: STEADY
  type: buff                   # buff / debuff
  stack: counter               # counter 按层数叠加 / single 只有有没有
  decay: turn_end              # 可选：拥有者回合开始(turn_start)/结束(turn_end)时减 1 层
  triggers:
    - {template: at_turn_start, do: [{op: block, amount: amount}]}   # amount = 当前层数
# relics.yaml
- id: LUCKY_COIN
  rarity: 初始
  triggers:
    - {template: at_battle_start, do: [{op: block, amount: 4}]}
```

（上面只列了两张牌。真要跑整局，还得按下面的卡池要求把牌补齐。）

整局还有几条卡池要求，检查时会用大白话告诉你：普通 / 罕见 / 稀有每种至少 1 张（建议 3 张以上，否则选牌奖励会出现重复）；商店要能摆出 2 张攻击、2 张技能、1 张能力（不算基础牌）。

*Rules checked for full runs (with plain-language messages): at least one Common, Uncommon and Rare card (3+ recommended, or rewards repeat cards); the shop needs 2 Attacks, 2 Skills and 1 Power outside Basic.*

### 效果（op） / Effects

每个效果都可以加 `if:`（条件表达式）和 `once:`（`turn` 每回合一次 · `turn_instance` 每张牌每回合一次 · `card_play` 每次打出一次 · `attacker_turn` 每个攻击者每回合一次 · `combat` 每场一次）。

| op | 参数 | 说明 |
|---|---|---|
| `damage` | amount, hits, target, kind (attack/unpowered/hp_loss), each_hit | 造成伤害 |
| `block` | amount | 获得格挡 |
| `apply` | power, amount, target, secondary, active, remember | 施加能力（`remember` 让这层记住一个数，供 `memory()` 读） |
| `remove_power` | power, amount, target, save | 移除能力，`save` 把移除的层数存成变量 |
| `set_stacks` | power, value, target | 把层数设成某个值 |
| `draw` / `energy` / `heal` | n / n / amount | 抽牌 / 获得能量 / 回血 |
| `lose_hp` | amount, target | 失去生命 |
| `add_card` | card, n, to (hand/draw/discard), upgraded | 加牌 |
| `set` | name, value | 记一个局部变量 |
| `if` / `foreach` / `repeat` | cond, then, else / target, do / n, do | 条件、对每个敌人、重复 |
| `exhaust_choice` / `discard_choice` | n, save | 让玩家（AI）选手牌消耗 / 丢弃 |
| `pick_from_pile` | pile, look, n | 从牌堆看几张挑几张 |
| `exhaust_hand` / `return_to_hand` / `end_turn` | | 消耗整个手牌 / 这张牌回手 / 结束回合 |
| `py` | fn | 调用 `fullrun_hooks` 里的 Python 函数（逃生口） |

`target` 可以是 `target`（选中的敌人）、`self`、`all`、`others`、`random`、`random_other`。

### 模板 / Templates

卡牌效果模板（写 `{template: 名字, ...}`，会展开成上面的 op）：

| 模板 | 参数 | 意思 |
|---|---|---|
| `scaled_damage` | base, power, per, cap, hits, on | 伤害 = base + min(cap, per × 某能力层数) |
| `cash_in` | power, per, cap, target, save | 清掉某能力的层数，每层换 per 点伤害 |
| `gain_power` | power, amount | 自己获得能力 |
| `multiply_stacks` | power, times, cap, target | 层数翻倍（最多加 cap） |
| `if_stacks` | power, at_least, on, then, else | 层数够了就…… |

触发器（能力 / 遗物的 `triggers:`），模板写法：

| 模板 | 参数 | 意思 |
|---|---|---|
| `at_turn_start` / `at_turn_end` / `at_battle_start` | do | 回合开始 / 结束 / 战斗开始时 |
| `every_n_cards` | n, card_type, do | 每打出 N 张（某类）牌 |
| `stacks_reach` | n, reset, do | 层数到 N 时（之后减 N / 清空 / 保留） |
| `on_attacked` | timing (before/after), do | 被攻击时（`T` 是攻击者） |
| `thorns` | amount | 反伤 |
| `bonus_damage` / `bonus_block` | add | 攻击伤害 / 格挡 +X |
| `boost_apply` | power, add | 施加某能力时多加几层 |
| `on_power_applied` / `on_power_removed` | power, active_only, do | 某能力被施加 / 清掉时 |
| `on_enemy_died` | do | 敌人死亡时 |
| `replay_first` | card_type | 每回合第一张（某类）牌打两次 |

原始触发器（`on:`）：`turn_start`、`turn_end`、`battle_start`、`attacked`、`card_played`、`stacks_reach`、`power_applied`、`power_removed`、`enemy_died`、`card_exhausted`、`modify_damage`（add/mult）、`modify_block`、`modify_apply`、`play_count`。

### 表达式 / Expressions

数值可以写数字、`vars` 里的名字或算式。可用：`T`（目标）、`P`（玩家）、`amount`（能力层数 / 触发数值）、`upgraded`、
`stacks(谁, '能力ID')`、`memory(谁, '能力ID')`、`intent_damage(谁)`、`attacking(谁)`、`hand_size()`、`draw_size()`、`discard_size()`、
`exhaust_size()`、`enemies()`、`others()`、`n_enemies()`、`energy()`、`block(谁)`、`hp(谁)`、`max_hp(谁)`、`alive(谁)`、`hand_has('ID')`、
`turn()`、`sum_stacks('ID')`、`max_stacks('ID')`、`count_with('ID')`、`plays_this_turn()`，以及 `min max abs int floor ceil round len sum any all`。
`helpers:` 可以给常用算式起名字，例如 `"fk(x)": "stacks(x, 'FK')"`。

### 其他键 / Other keys

- `ai: {value: 2}`（卡牌）：AI 选牌时的估值；不写就让通用 AI 自己估。`ai_values: {能力ID: 每层价值}`：AI 估局面时每层能力值多少。
- `variants:`：同一个 mod 的数值变体（改某些牌的 vars / cost、`hp`、`starting_deck`、`energy`、`add_cards`），跑的时候 `--variant 名字`。
- 逃生口：`fullrun_hooks: hooks_fullrun.py` 里的函数可以用 `{op: py, fn: 名字}` 调用；`ai_hooks:` 可以注册更细的 AI 估值。旧的 `hooks:`（给战斗模拟器的）整局不会加载，检查时会提醒。
- `tags: [Strike]` / `[Defend]`：游戏里有些遗物 / 事件要找角色的「打击」「防御」基础牌。没写时，第一张基础攻击牌自动当打击、第一张基础技能牌当防御。
- 暂不支持：X 费牌、起始牌组里写 `+`（会提醒，给普通版）。

### 怎么跑 / Running it

```bash
python tools/batch.py --mod mods/my_mod --char MyHero --asc 0 --n 200 --agent modai
python tools/ab_card.py --mod mods/my_mod --char MyHero --n 400 --agent modai --force MY_MOD_CHARGE_UP
```

`--force` 用游戏里的 ID（前缀转成大写下划线 + 你的 ID，例如前缀 `MyMod` + `CHARGE_UP` → `MY_MOD_CHARGE_UP`；模组编辑器的单卡 A/B 会自动换算）。格式有错时，命令会先列出所有问题再退出，不会跑一半才报错。

### 图形界面：模组编辑器 / GUI: Mod editor

左侧「模组编辑器」：
- **打开 / 新建 / 导入 zip / 导出 zip**。自带的示例 mod 只读，改个文件夹名再保存就是你自己的一份（存在界面数据目录的 `mods/` 下）。
- **角色**：生命、能量、金币、起始牌组（选牌 + 张数）、初始遗物，下面显示卡池各稀有度有几张。
- **卡牌**：名字、类型、稀有度、费用、目标、关键词、数值（普通 / 升级两列）、描述，以及**效果搭建器**：一行一个效果，从下拉菜单选「造成伤害」「施加能力」或模板，参数按需出现；也可以切到 YAML 直接写。
- **能力 / 遗物**：同样用「什么时候 → 做什么」的触发器搭建器。
- **检查**：把问题和提醒用大白话列出来；**保存**时自动检查。
- **试跑**：一键「整局试跑」（选角色、进阶、局数、AI），或者「单卡 A/B」（同一批种子跑起始牌组 vs 起始牌组 + 这张牌），结果在「报告」「单卡 A/B」页面看。

*The Mod editor page: open/new/import/export zip (built-in examples are read-only: rename and save to get your own copy); forms for the character, cards (with an effect builder: one row per effect, picked from a menu, or edit as YAML), powers and relics (when → what triggers); Check lists problems in plain language; Test runs a full-run batch or a one-card A/B with one click.*

### Claude娘 数据版 / Claude娘 as data

`mods/claude_yaml/` 由 `tools/convert_claude_v35.py` 从手写的 Python 版自动生成：设计稿 86 张牌里，69 张从 Python 版自动转成纯 YAML（大多数是 op，部分用模板），另有 12 张按设计文字手写成 YAML（`--variant new_cards` 启用，个别是近似），共 81 张；5 张需要游戏里还没有的机制（发现式选牌、回合末保留手牌、保留格挡、「只能第一张打出」、撤销出牌），留给 Python。
和手写 Python 版对拍：70 张牌（含 1 张衍生牌）× 普通 / 升级 × 3 个种子，每张打出后的局面完全一样（`tools/parity_yaml.py`）；通用 AI 各 300 局，A0 / A10 每个种子的结果（层数、牌组、遗物）都一模一样。

*`mods/claude_yaml/` is generated from the hand-written Python port: of 86 design cards, 69 convert automatically to pure YAML, 12 more are written in YAML from the design text (`--variant new_cards`, a few approximate), 5 need mechanics the engine doesn't expose yet. Parity with the Python port: all 70 cards identical after play in fixed states (`tools/parity_yaml.py`), and 300 `modai` runs each at A0 and A10 identical seed by seed.*

## 旧版战斗模拟器的 mod / Mods for the legacy combat simulator

### 写一个 mod / Writing a mod

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


### 事件总线（钩子）/ Event bus (hooks)

`combat.emit("事件名", **参数)` 依次调用 遗物 → 玩家能力 → 敌人能力 → 各 mod 的 hooks 模块 上的 `on_<事件名>(C, ev)`，
钩子可以改 `ev` 上的字段（例如 `ev.amount`、`ev.cost`、`ev.ok`）。常用事件：
`battle_start`、`turn_start(side, creature)`、`turn_end`、`card_drawn`、`before_play`、`after_play`、`modify_play_count`（重放）、
`damage_add` / `damage_mul`（伤害修正）、`attacked`（每段攻击结算后，带 unblocked）、`damage_taken`、
`modify_apply` / `power_applied` / `power_removed`（能力施加，带 active/secondary/multi 标记）、`block_gained`、`card_exhausted`、
`modify_cost`、`can_play`、`modify_turn_draw`、`enemy_died`、`player_would_die`、`potion_used`。

