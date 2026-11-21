# 自定义卡牌 / Custom cards

侧栏「自定义卡牌」（`#/cards`）编写战斗引擎能跑的牌，保存，重新打开，并测试一套含这张牌的牌组。不编译 mod DLL，也不执行导入的文件。

*Custom cards (`#/cards`) writes a card the combat engine can run, saves it, opens it again, and tests a deck that contains it. It does not build a mod DLL, and it does not execute an imported file.*

版本号仍是 `0.1.5`。出厂预设、`mods/` 和播种方式不改。

*The version is still `0.1.5`. Shipped presets, `mods/` and the seeding are unchanged.*

## 保存的是什么 / What is saved

库名是文件夹名，写在界面数据目录的 `mods/<name>/`。`library.json` 是编辑器重新打开时用的表。`cards.yaml` 和 `mod.yaml` 是战斗引擎读的同一份数据：模板已经展开成 op，类型写成引擎认得的「攻击 / 技能 / 能力」。角色只有生命和能量，用来打这场测试。

*The library name is the folder, under `mods/<name>/` in the GUI data directory. `library.json` is the form the editor reopens. `cards.yaml` and `mod.yaml` are what the combat engine reads: templates are expanded to ops, and the type is the engine's 攻击 / 技能 / 能力. The character is HP and energy for this test.*

字段和 `sts2sim/modfmt/schema.py` 的卡牌是同一套。效果菜单来自 `schema.OPS` 和 `schema.TEMPLATES`，去掉 `py`。

*The fields are the card fields in `sts2sim/modfmt/schema.py`. The effect menu is `schema.OPS` and `schema.TEMPLATES`, without `py`.*

## 检查会拒绝什么 / What check refuses

- `py` 效果，以及 `hooks.py` / `fullrun_hooks`。导入的 zip 里只要有 `.py` 或 `.dll` 就整份拒绝。
- 表达式里的属性访问（例如 `().__class__`）、不在战斗引擎里的函数，以及整局引擎才有的名字（例如 `draw_size`）。数字、这张牌 `vars` 里的名字，以及 `sts2sim/expr.py` 里已有的函数可以用。
- 库名不是字母开头、或超过 28 个字符。这个长度是为了测试预设的 id（`<name>_try`）仍能放进现有的预设 id。

*A `py` effect, and `hooks.py` / `fullrun_hooks`. A zip that contains a `.py` or a `.dll` is refused as a whole. Attribute access in an expression (for example `().__class__`), a function the combat engine does not have, and a name that exists only in the full-run engine (for example `draw_size`). A number, a name in this card's `vars`, and a function already in `sts2sim/expr.py` are accepted. A library name that does not start with a letter, or that is longer than 28 characters. That length keeps the test preset id (`<name>_try`) inside the existing preset id.*

警告，仍可保存：

- `once` 会留下，但战斗测试每次打出都会结算。
- 能力 id 不是战斗引擎里已实现的能力时，测试只记层数，不跑触发器。

*Warnings, and the card can still be saved: `once` is kept, but the combat test resolves the effect on every play. A power id the combat engine does not implement only stores stacks. It does not run a trigger.*

## 测试 / The test

「测试这套牌」用现有的用户预设和 `POST /api/runs`（`kind: combat`）。遭遇只有两个：

- `DUMMY`：训练木桩。不攻击。只有牌组自己扣血才会失败。
- `SYN_BRUTE`：`sts2sim.fightcheck` 里的那只合成蛮兵。不是游戏遭遇，也不出现在遭遇名单里。

*Test this deck uses the existing user preset and `POST /api/runs` (`kind: combat`). There are two encounters. `DUMMY` is the training dummy. It does not attack, so the fight is a loss only when the deck spends HP. `SYN_BRUTE` is the synthetic brute in `sts2sim.fightcheck`. It is not a game encounter and it is not on the encounter list.*

一场测试最多 8 场，回合上限 1–30。种子是预设上已有的那个整数，播种函数没有改。

*One test is at most 8 fights. Max turns is 1–30. The seed is the integer the preset already stores. The seeding function is unchanged.*

组牌页仍能看到这些牌，因为它们在用户 mod 的 `cards.yaml` 里。整局试跑仍用「模组编辑器」。这一页不编辑能力触发器或遗物。

*Deck builder can see the cards, because they are in the user mod's `cards.yaml`. A full-run test is still the Mod editor. This page does not edit power triggers or relics.*
