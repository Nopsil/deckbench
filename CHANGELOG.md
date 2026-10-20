# 更新日志 / Changelog

## 0.1.3 (2026-10)

- 新 AI「通用 AI（推荐，模组角色也能用）」（`modai`）：选牌、休息、商店交给一个只看通用数值、不看卡名的小网络，**模组角色也能用**，速度同学习版，Windows 可用。测试中原版角色平均多走约 1.5–4 层，Claude娘 A0 16.8 → 20.2 层。模型文件只有网络权重。`modai-boss`（加首领战推演）在 Windows 上隐藏。
  *New "General AI" (`modai`, recommended): a small character-agnostic network for card rewards, rest sites and shops (generic numbers only, no card names), so it works for mod characters; same speed as the learned AI, works on Windows. Weights-only model file. `modai-boss` is hidden on Windows.*
- 指定游戏种子：「新建测试 → 整局批量」可以填游戏里的种子（自动按游戏规则转大写、O→0、I→1），只打这一局并记录每一步的决策。命令行 `tools/batch.py --seed … --log-dir …`。
  *Play a real game seed: enter it in New Test (normalized like the game) to play that one run with a per-step decision log. CLI: `--seed`, `--log-dir`.*
- MCP 对战模式（从源码运行，可选 `requirements-mcp.txt`）：`tools/mcp_server.py` 让支持 MCP 的 AI 助手一步一步打一局，可撤销、恢复、导出操作清单。卡牌中文名运行时从你自己的游戏安装读取，不随项目分发。见 `docs/MCP.md`。
  *MCP play mode (from source, optional `requirements-mcp.txt`): `tools/mcp_server.py` lets MCP clients play a seeded run step by step with undo/restore/export. Card names are read from your own install at runtime and never shipped.*
- 可选的 spire-mentor AI：新增 `mentor-full-ev`（普通事件和锻造/删牌/变形/附魔选牌也交给它的 PPO，首领/精英战 4000 次模拟）；`--boss-sims` / `--elite-sims`。A10（每角色 60 局）：`mentor-full` 0/300 → `mentor-full-ev` 5/300。事件的英文文本运行时从你的游戏安装读取。
  *Optional spire-mentor agent `mentor-full-ev` (PPO also for regular events and out-of-combat card picks; 4000 sims in boss/elite fights) and `--boss-sims` / `--elite-sims`. A10 over 300 runs: 0 → 5 wins. Event text is read from your install at runtime.*
- 新模块 `sts2sim/gameloc.py`：从你的游戏 `.pck` 里读官方英文/中文本地化，只在内存里用（可用 `DECKBENCH_GAME_PCK`、`DECKBENCH_GAME_LOC_ENG` / `_ZHS` 覆盖）。
  *New `sts2sim/gameloc.py`: reads official English/Chinese localization from your own `.pck` at runtime, in memory only.*

## 0.1.2 (2026-10)

- 新 AI `mentor-full`（可选，需要自己构建外部的 spire-mentor）：战斗用它的 MCTS，选牌/路线/商店/休息/Neow 用它的 PPO 网络；Rust 端出错（panic）时回退到我们的 AI，不中断运行。只支持原版 5 个角色，模组角色回退学习版 AI。`tools/batch.py --agent mentor-full` 会打印局外决策统计。
  *New optional `mentor-full` agent (requires building the external spire-mentor yourself): its MCTS for combat and its PPO networks for card rewards, map, shop, rest and Neow. Rust panics are caught and fall back to our AI. Vanilla characters only; mod characters fall back to the learned AI.*
- 图形界面：配置了 spire-mentor 时可在整局批量里选这个 AI，否则显示为灰色并带提示。
  *GUI: the agent is selectable when spire-mentor is configured, greyed out with a hint otherwise.*
- 文档：怎样指向 spire-mentor 和它的 PPO 网络；上游在 v0.111 的 19 张新牌（SIDESTEP 等）上的读取问题，以及一个很小的本地补丁（`docs/patches/`，不含游戏数据）。
  *Docs: how to point at spire-mentor and its PPO networks; the known upstream loader bug for 19 v0.111 cards (SIDESTEP etc.) and a small code-only local patch in `docs/patches/`.*

## 0.1.1 (2026-10)

- 修复：从抽牌堆选牌时（如 Cleanse、Foregone Conclusion）候选牌的顺序和游戏不一致。游戏按“稀有度、卡牌 ID”排序，我们的排序在稀有度相同时没有按 ID 排。现在和真实游戏一致。
  *Fix: card choices from the draw pile (e.g. Cleanse, Foregone Conclusion) are now ordered like the game (rarity, then card ID). Ties on rarity used to keep pile order.*
- 首次运行的反编译临时文件不再写到系统 TEMP（常在 C: 盘），改为缓存目录下的 `tmp\`，可用 `DECKBENCH_TEMP` 指定。
  *First-run decompile scratch files now go to `<cache>/tmp` (or `DECKBENCH_TEMP`) instead of the system TEMP.*
- spire-mentor 桥接（可选，外部依赖）：药水按已装备的槽位映射；跳过只在拾取时生效的遗物；最优动作在我们这边不合法时改用下一个；回退原因写明是哪张牌 / 哪个遗物 ID。`tools/batch.py` 新增 `--agent mentor-mcts / mentor-boss` 和 `--sims`。
  *spire-mentor bridge (optional, external): potions mapped by filled slots; pickup-only relics skipped; falls back to the next-ranked legal move; fallback reasons name the card / relic ID. `tools/batch.py` gains `--agent mentor-mcts / mentor-boss` and `--sims`.*

- 界面：新建测试默认铁甲战士 A0；侧边栏显示版本号；去掉卡片上的开发者路径。
  *GUI: New Test defaults to Ironclad A0; the sidebar shows the version; developer paths removed from the cards.*

## 0.1.0 (2026-10)

- 首个公开预览版。 / *First public preview.*
