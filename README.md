# DeckBench

> **⚠️ 免责声明 / Disclaimer**
>
> - **非官方**：本项目是粉丝制作的非官方工具，与 Mega Crit 无任何关联，也未获其认可或赞助。
>   **Unofficial**: a fan-made tool. Not affiliated with, endorsed by, or sponsored by Mega Crit.
> - **不包含任何游戏数据**：仓库和发布包里没有任何游戏文件、游戏代码或游戏数据。游戏相关内容只会在你本机、从你自己的游戏安装转换生成，并绑定到该安装（记录安装路径和文件哈希，不匹配就拒绝加载）。
>   **Ships no game data**: no game files, code or data are included. Everything game-related is converted locally from *your own* installation and bound to it (install path + file hash; refuses to load on mismatch).
> - **需要你自己的正版游戏**：必须已购买并安装游戏（Steam 正式版或公开测试分支）。找不到安装时程序会报错退出。
>   **Requires your own copy of the game** (Steam stable or public beta). The program exits with an error if no install is found.
> - **不接受游戏资源**：任何包含游戏代码、数据、文本或美术的 PR 都会被拒绝（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。
>   **Game-asset PRs are rejected** (see [CONTRIBUTING.md](CONTRIBUTING.md)).
> - **责任自负**：任何人滥用本项目来分发游戏代码或文件，责任完全由其本人承担，与作者无关。
>   Anyone who misuses this project to redistribute game code or files is solely responsible for doing so; the authors are not.
> - **许可范围**：[LICENSE](LICENSE)（MIT）只覆盖贡献者自己编写的代码，不授予任何游戏代码、数据、美术或商标的许可。
>   **License scope**: [LICENSE](LICENSE) (MIT) covers only contributors' own code and grants no license to any game code, data, art or trademarks.
> - Slay the Spire 2 是 Mega Crit 的商标；本项目提及游戏名称仅为说明兼容性。/ Slay the Spire 2 is a trademark of Mega Crit; the name is used only to describe compatibility.
> - 联系 / Contact: **TODO-CONTACT-EMAIL**（版权方如有任何问题请联系，我们会尽快处理 / rights holders: please reach out and we will respond promptly）

给《杀戮尖塔 2》mod 作者用的**非官方**平衡测试工具：不进游戏，让 AI 自动打成百上千局，给出胜率、到达层数、死因、单卡贡献和 A/B 对比。
An unofficial balance-testing bench for Slay the Spire 2 mod authors: AI plays thousands of runs/fights and reports win rate, floors reached, death causes, per-card impact and A/B comparisons.

- **整局模拟（主引擎）**：在本机从你的游戏安装转译出的游戏逻辑上跑完整的一局（地图、战斗、奖励、商店、事件），支持进阶等级、多种 AI。
- **YAML 战斗模拟器（旧版）**：用 YAML + Python 钩子写卡牌，单场战斗大批量测试（需要额外的本机数据，见下文）。
- **桌面界面**：本地图形界面（FastAPI + Vue，pywebview 窗口），见 [gui/README.md](gui/README.md)。
- 示例 mod：Claude娘（`mods/claude_v34`、`mods/claude_v35`，原创内容）。

## 快速开始 / Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 1) 本机反编译需要 .NET 9 SDK + ilspycmd / local decompilation needs .NET 9 SDK + ilspycmd
dotnet tool install -g ilspycmd --version 9.1.0.7988
# 2) 首次运行：从你自己的安装生成本机数据（几分钟）/ first run: generate local data from your install
.venv/bin/python -m sts2sim.gamedata setup            # 自动找 Steam 安装 / auto-detects the Steam install
.venv/bin/python -m sts2sim.gamedata setup --game-dir "D:/SteamLibrary/steamapps/common/Slay the Spire 2"
.venv/bin/python -m sts2sim.gamedata status
# 3) 跑整局 / run full games
PYTHONPATH=. .venv/bin/python tools/batch.py --char Ironclad --asc 10 --n 100 --agent learned --out x.jsonl
PYTHONPATH=. .venv/bin/python tools/batch.py --char Claude --asc 10 --n 100 --agent learned --out claude.jsonl
# 4) 界面 / GUI（首次启动会自动执行第 2 步）
.venv/bin/python -m gui.app
# 测试 / tests（需要本机安装的测试会自动跳过）
.venv/bin/python -m pytest -q tests
```

## 首次运行：本机生成 / First run: local generation

`python -m sts2sim.gamedata setup`（GUI 首次启动时自动执行）：

1. **找安装**：`--game-dir` → 环境变量 `DECKBENCH_GAME_DIR` → 自动检测 Steam 库（含 `libraryfolders.vdf` 里的其他库）。
   在安装目录里找 `sts2.dll`。**找不到就打印说明并退出（退出码 2）**。
2. **本机反编译**：用 ilspycmd 把你自己的 `sts2.dll` 反编译到临时目录（用完即删）。
3. **转译**：`tools/cs2py_files.py`（+ `tools/cs_patches.py` 的结构化补丁）把游戏逻辑转成 Python `game.py`；
   `tools/parse_monster_ai.py`、`tools/parse_encounters.py` 解析怪物出招状态机和遭遇组成（供旧版战斗模拟器用）。
4. **写入本机缓存并绑定安装**：`%LOCALAPPDATA%\deckbench\<哈希>\`（Linux/macOS：`~/.cache/deckbench/`，可用 `DECKBENCH_CACHE` 改），
   `manifest.json` 记录安装路径和 `sts2.dll` 的 SHA-256。每次加载（`import sts2sim.gen.game`）都会重新校验：
   安装不见了或文件变了（例如游戏更新）就**拒绝加载**，提示重新生成。缓存里有 `DO_NOT_REDISTRIBUTE.txt`——**请勿分发缓存内容**。

正式版和 Steam 公开测试分支（beta）都支持：生成的内容就是你当前安装的那个版本（`release_info.json` 的版本/分支会记进 manifest）。

## 可选外部依赖 / Optional external dependencies

- **spire-mentor（更强的 MCTS 战斗 AI，`--agent mentor-mcts` / `mentor-boss`）**：它的仓库包含游戏数据，所以**不内置**。
  需要的话请自己克隆并按其说明构建 `sts2_rs`，然后设置：
  `DECKBENCH_MENTOR_SITE=<装了 sts2_rs 的 site-packages>`、`DECKBENCH_MENTOR_PY=<spire-mentor 的 sts2-pycli/python 目录>`。
  未配置时这些 AI 会报错或回退到 `learned-search`，其他功能不受影响。
- **旧版 YAML 战斗模拟器**（`python -m sts2sim <实验.yaml>`）需要两样不随仓库分发的本机数据：
  - spire-codex 格式的怪物/遭遇/卡牌 JSON（`eng_*.json`、`zhs_*.json`）：用第三方工具 spire-codex 从你自己的安装导出，
    放到 `data/spire-codex/` 或用 `DECKBENCH_CODEX_DIR` 指定；
  - 原版对照组 `mods/vanilla/`（原版卡牌的 YAML 写法，自行整理；已 gitignore）。
  缺少时会报错退出；整局模拟和 GUI 的整局功能不受影响。界面里卡牌名称在没有这份数据时显示为 ID。

## 目录 / Layout

```
sts2sim/gamedata.py  首次运行：找安装、本机反编译+转译、缓存绑定与校验
sts2sim/gen/         只有 __init__.py：从本机缓存加载 game.py（仓库里没有生成代码）
sts2sim/rt/          转译代码的运行时（C#/LINQ 语义、少量手写覆盖）
sts2sim/engine/      整局驱动、Gym 接口、AI（heuristic / strong / learned / planner / search / imitation / mentor 桥接）
sts2sim/*.py         旧版 YAML 战斗模拟器（core、cards、powers、enemies、runner、report…）
mods/                示例 mod：Claude娘 v3.4（YAML）、v3.5（整局引擎）
tools/               转译器 cs2py_*、解析器、batch.py、调参 tune_cma.py、A/B 工具
gui/                 桌面界面（后端 + Vue 前端 + PyInstaller 打包脚本）
data/                我们自己训练的 AI 参数（ai_weights*.json、imitation_model.json）
tests/               单元测试
```

## 旧版 YAML 战斗模拟器：事件总线

`combat.emit("事件名", **参数)` 依次调用 遗物 → 玩家能力 → 敌人能力 → 各 mod 的 hooks 模块 上的 `on_<事件名>(C, ev)`，
钩子可以改 `ev` 上的字段（例如 `ev.amount`、`ev.cost`、`ev.ok`）。常用事件：
`battle_start`、`turn_start(side, creature)`、`turn_end`、`card_drawn`、`before_play`、`after_play`、`modify_play_count`（重放）、
`damage_add` / `damage_mul`（伤害修正）、`attacked`（每段攻击结算后，带 unblocked）、`damage_taken`、
`modify_apply` / `power_applied` / `power_removed`（能力施加，带 active/secondary/multi 标记）、`block_gained`、`card_exhausted`、
`modify_cost`、`can_play`、`modify_turn_draw`、`enemy_died`、`player_would_die`、`potion_used`。

## 给新 mod 写内容

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

## Claude娘 专用工具

- `tools/sync_claude_text.py <设计脚本目录>`：只读导入设计数据（v34_data.py），把卡面文字写进 `mods/claude_v34/cards.yaml`，
  并核对每张卡的类型/稀有度/费用与设计一致；同时更新 `tests/fixtures/claude_v34_design.json`（测试用快照）。改效果请改 `cards_src.yaml` 再同步。
- 风控契约（主动/被动给予、次级施加、RLHF 只改数值不递归、人工制品拦截给予与复制、层数操作不算给予/清除、清理指标每张牌最多返 1 能量、扣信用分每回合一次…）
  全部写在 `mods/claude_v34/hooks.py`，对应测试在 `tests/test_claude.py`。


## 已知限制 / Known limitations

- 模拟结果只适合在同一套假设下横向比较（新卡 vs 原版、改前 vs 改后），不是真实胜率。
- 首次生成需要 .NET 9 SDK + ilspycmd；转译器针对 v0.111 系列验证过，游戏大版本更新后可能需要更新转译器/补丁。
- Windows 上没有 fork，带搜索的 AI（`strong`、`learned-search`）不可用。

## License

MIT for our own code only — see [LICENSE](LICENSE) for the scope note. 本仓库代码以 MIT 许可发布，范围仅限我们自己的代码。
