# 开发者文档 / Developer guide

[← 返回 README](../README.md) · [写 mod](MODDING.md)

普通使用请看 [README](../README.md)。这里是命令行、内部原理和开发相关内容。命令同时给出 Windows（PowerShell）和 Linux/macOS 两种写法。
*For everyday use see the README. This page covers the command line, internals and development; commands are shown for both Windows (PowerShell) and Linux/macOS.*

- [安装（命令行）](#安装命令行--setup-command-line)
- [首次运行：本机生成的原理](#首次运行本机生成的原理--how-first-run-generation-works)
- [命令行整局批量运行](#命令行整局批量运行--full-run-batches-from-the-command-line)
- [可选：spire-mentor](#可选spire-mentor更强的-mcts-战斗-ai-optional-spire-mentor)
- [旧版 YAML 战斗模拟器](#旧版-yaml-战斗模拟器--legacy-yaml-combat-simulator)
- [目录结构](#目录结构--layout)
- [测试](#测试--tests)
- [Claude娘专用工具](#claude娘示例-mod专用工具--claude-mod-tools)
- [Windows 打包版](#windows-打包版--building-the-windows-package)
- [已知限制](#已知限制--known-limitations)

## 安装（命令行） / Setup (command line)

需要 Python 3.11+、.NET 9 SDK、ilspycmd；图形界面另需 Node.js（构建前端）。

```bash
# Linux/macOS
python3 -m venv .venv
.venv/bin/pip install -r requirements-gui.txt        # 只用命令行可以只装 requirements.txt
dotnet tool install -g ilspycmd --version 9.1.0.7988
.venv/bin/python -m sts2sim.gamedata setup           # 或 --game-dir "<...>/steamapps/common/Slay the Spire 2"
(cd gui/web && npm install && npm run build)         # 图形界面前端（只需一次，改了前端再构建）
.venv/bin/python -m gui.app                          # --browser 用浏览器；--serve --port 8765 只开服务
```
```powershell
# Windows
python -m venv .venv
.venv\Scripts\pip install -r requirements-gui.txt
dotnet tool install -g ilspycmd --version 9.1.0.7988
.venv\Scripts\python -m sts2sim.gamedata setup
cd gui\web; npm install; npm run build; cd ..\..
.venv\Scripts\python -m gui.app
```

`numpy` 只有模仿学习（`--agent imitation`、`tools/imitate.py`）和调参（`tools/tune_cma.py`）需要：`pip install numpy`。

## 首次运行：本机生成的原理 / How first-run generation works

`python -m sts2sim.gamedata setup`（GUI 每次启动都会先检查，缺失或不匹配时自动执行；`tools/batch.py` 只检查，不自动生成）：

1. **找安装**：`--game-dir` → 环境变量 `DECKBENCH_GAME_DIR` → 自动检测 Steam 库（含 `libraryfolders.vdf` 里的其他库）。
   在安装目录里找 `sts2.dll`。**找不到就打印说明并退出（退出码 2）**。
2. **本机反编译**：用 ilspycmd 把你自己的 `sts2.dll` 反编译到临时目录（用完即删）。
3. **转译**：`tools/cs2py_files.py`（+ `tools/cs_patches.py` 的结构化补丁）把游戏逻辑转成 Python `game.py`；
   `tools/parse_monster_ai.py`、`tools/parse_encounters.py` 解析怪物出招状态机和遭遇组成（供旧版战斗模拟器用）。
4. **写入本机缓存并绑定安装**：`%LOCALAPPDATA%\deckbench\<哈希>\`（Linux/macOS：`~/.cache/deckbench/`，可用 `DECKBENCH_CACHE` 改），
   `manifest.json` 记录安装路径和 `sts2.dll` 的 SHA-256。每次加载（`import sts2sim.gen.game`）都会重新校验：
   安装不见了或文件变了（例如游戏更新）就**拒绝加载**，提示重新生成。缓存里有 `DO_NOT_REDISTRIBUTE.txt`——**请勿分发缓存内容**。

正式版和 Steam 公开测试分支（beta）都支持：生成的内容就是你当前安装的那个版本（`release_info.json` 的版本/分支会记进 manifest）。


图形界面启动时：缓存有效就直接用；无效（第一次、游戏更新、换分支）就先自动检测安装，检测不到再用上次 `--game-dir` 记下的路径重新生成；都找不到就提示并退出（退出码 2，Windows 上弹窗）。

```text
python -m sts2sim.gamedata setup [--game-dir PATH] [--keep-src]   # 生成；--keep-src 保留本机反编译源码（调试用，仍在缓存里，请勿分发）
python -m sts2sim.gamedata status                                 # 查看当前缓存绑定的安装、哈希、版本
```

环境变量 / environment variables：`DECKBENCH_GAME_DIR`（游戏目录）、`DECKBENCH_CACHE`（缓存根目录）、`DECKBENCH_TEMP`（反编译临时目录，默认是缓存根目录下的 `tmp\`，不用系统 TEMP / decompile scratch dir, defaults to `<cache>/tmp`, not the system TEMP）。

## 命令行整局批量运行 / Full-run batches from the command line

`tools/batch.py` 在本机生成的游戏逻辑上跑完整的一局。需要把仓库根目录加进 `PYTHONPATH`。
**只支持 Linux/macOS**（每局超时用了 `SIGALRM`）；Windows 请用图形界面（它自带不依赖 `SIGALRM` 的批量运行器），或在 WSL 里运行。

```bash
# Linux/macOS
PYTHONPATH=. .venv/bin/python tools/batch.py --char Ironclad --asc 10 --n 100 --agent learned --out ironclad.jsonl
PYTHONPATH=. .venv/bin/python tools/batch.py --char Claude --asc 10 --n 100 --agent learned --out claude.jsonl
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--char` | `Ironclad` | 角色（原版 5 角色的类名，或 `Claude` = 示例 mod Claude娘 v3.5） |
| `--asc` | `10` | 进阶等级 |
| `--n` / `--start` | `20` / `0` | 跑多少局 / 从第几号种子开始（种子 `R<start>`…） |
| `--procs` | CPU 核数 | 并行进程数 |
| `--out` | 无 | 每局结果写成 JSONL |
| `--agent` | `heuristic` | `heuristic`（快）、`modai`（推荐，通用 AI，模组角色也能用）、`modai-boss`（+ 首领战推演，仅 Linux/macOS）、`learned`、`learned-search`、`learned-boss`、`strong`、`strong-nosearch`、`planner`、`planner-search`、`search`、`imitation`、`mentor-mcts`、`mentor-boss`、`mentor-full`、`mentor-full-ev`（需外部 spire-mentor） |
| `--sims` | 1000 | `mentor-*` 每个决策的 MCTS 模拟次数 |
| `--boss-sims` / `--elite-sims` | 同 `--sims`（`mentor-full-ev` 为 4000） | `mentor-*` 首领 / 精英战每步的模拟次数 |
| `--seed` | 空 | 真游戏种子（逗号分隔可多个；按游戏规则转大写、O→0、I→1）；给了就忽略 `--n/--start` |
| `--log-dir` | 空 | 每局一个逐步决策日志 JSONL（`<角色>_A<进阶>_<种子>.jsonl`） |
| `--style` | `standard` | 打法风格：`standard`（标准，不加规则）、`juggler`（杂耍流：优先拿杂耍 JUGGLING，偏好多段攻击和反直觉的组合；要 `strong` / `learned` / `planner` / `imitation` / `modai` / `mentor` 系 AI）。`tools/ab_card.py` 也有 `--style` |
| `--force-pick` / `--force-pick-first` | 空 | 见到这些牌就拿；战斗里先打 |
| `--width` / `--depth` | `6` / `1` | `search` AI 的搜索宽度/深度 |
| `--variant` | 无 | Claude娘简化变体（`mods/claude_v35/cards_v35.py` 的 `VARIANTS` 键） |
| `--force` | 空 | 强制加入起始牌组的牌，逗号分隔，`ID+` 为升级版（单卡 A/B 用） |
| `--replace` | 空 | 同时从起始牌组移除的牌，逗号分隔 |
| `--no-boss-aware` | 关 | 关闭首领感知（选牌/休息） |
| `--boss-search` | 关 | `strong-nosearch` 下只在首领战开搜索 |
| `--timeout` | heuristic 60，其余 900 | 每局秒数上限 |

宝箱遗物：0.1.3 起真正进遗物栏（以前的版本没有，所以旧的胜率/层数偏低）；`DECKBENCH_TREASURE_FIX=0` 恢复旧行为，只用于复现旧数字。

带搜索的 AI（`strong`、`search`、`learned-search`、`learned-boss`、`planner-search`、`modai-boss`）用 `os.fork()` 给游戏状态拍快照，只能在 Linux/macOS 上用。

其他工具：`tools/ab_card.py`（同种子单卡 A/B：`--force`、`--replace`、`--variant`、`--base-variant`…）、`tools/boss_bench.py`（首领战基准）、
`tools/tune_cma.py`（CMA-ES 自我对局调参 → `data/ai_weights.json`）、`tools/imitate.py`（模仿学习 → `data/imitation_model.json`）、
`tools/trace_run.py`（单局逐步追踪）、`tools/ai_eval.sh` / `tools/ai_summary.py`（AI 对比）。Gym 接口：`from sts2sim.engine.gym import Sts2Env`（见模块文档字符串）。

## 可选：spire-mentor（更强的 AI）/ Optional: spire-mentor

[spire-mentor](https://github.com/tfriedel/spire-mentor)（MIT，Rust）是第三方的游戏重写 + AI。它的仓库包含游戏文本和提取的数据，所以**本项目不内置、不分发它的任何东西**（代码、网络、数据都不带）。
需要的话请自己克隆并按它的说明用 maturin 构建 Python 绑定 `sts2_rs`。
*spire-mentor is an external, third-party dependency. Its repository contains game text/data, so DeckBench ships nothing from it (no code, networks or data). Clone and build it yourself.*

四个 AI（`tools/batch.py --agent …`）：

| AI | 战斗 | 局外（选牌、路线、商店、休息、Neow/先古之民） |
|---|---|---|
| `mentor-mcts` | spire-mentor MCTS（`--sims`，默认 1000） | 我们的 learned |
| `mentor-boss` | 只有首领战用 MCTS | 我们的 learned |
| `mentor-full` | spire-mentor MCTS | spire-mentor 的 PPO 网络（每角色一个 ONNX）；其他事件、宝箱、锻造选牌仍用 learned |
| `mentor-full-ev` | spire-mentor MCTS，首领/精英 4000 模拟 | 同上，另外普通事件、锻造/删牌/变形/附魔选牌也用 PPO；宝箱和局外药水仍用 learned |

- 统计会打印 MCTS 决策数与回退比例；`mentor-full` 还会打印每类局外决策“网络/回退”的次数。
- 遇到 spire-mentor 不认识的牌/遗物/怪物、调用出错，或者 Rust 端 panic（例如找不到 PPO 网络），都会**回退到我们自己的 AI**，不会中断批量运行。
- **只支持原版 5 个角色。** 模组角色（如 Claude娘）的局外决策和不认识的战斗都会回退到 learned AI。
  *Only the 5 vanilla characters are supported; mod characters (e.g. Claude) fall back to the learned AI.*
- 参考（每角色 60 局，种子 R0–R59）：A0 `mentor-full` 胜率 23–63%，约 25–55 秒/局（单进程）。
  A10：`mentor-full` 0/300；`mentor-full-ev` 5/300（Ironclad 2、Defect 3，其余 0），平均层数每个角色都更高，约 50–130 秒/局。
- `mentor-full-ev` 的普通事件需要英文选项文本：运行时从**你本机的游戏安装**（游戏目录里的 `.pck`）读取，只在内存里用，不写盘、不分发（`sts2sim/gameloc.py`）。
  读不到时这些事件回退到 learned。可选覆盖：`DECKBENCH_GAME_PCK=<.pck 路径>`，或 `DECKBENCH_GAME_LOC_ENG` / `DECKBENCH_GAME_LOC_ZHS` 指向含 `events.json` 等表的目录。
  *`mentor-full-ev` reads the English event option text from your own install's `.pck` at runtime (memory only, never written or shipped); without it those events fall back to the learned AI.*

**配置 / Setup**：三种写法都可以。环境变量覆盖 json，json 覆盖 `mentor/` 目录。官方安装包**不包含**这些文件；没有配置时界面里两项是灰的。

1. 环境变量（改完要重新启动 DeckBench）：

```bash
# Linux/macOS
export DECKBENCH_MENTOR_SITE=/path/to/venv/lib/python3.13/site-packages   # 装了 sts2_rs 的 site-packages
export DECKBENCH_MENTOR_PY=/path/to/spire-mentor/sts2-pycli/python        # 它的 sts2_hint 包所在目录
export DECKBENCH_MENTOR_PYTHON=/path/to/venv/bin/python                    # 打包版必填；源码版建议填
```
```powershell
# Windows PowerShell
$env:DECKBENCH_MENTOR_SITE = "C:\path\to\venv\Lib\site-packages"
$env:DECKBENCH_MENTOR_PY = "C:\path\to\spire-mentor\sts2-pycli\python"
$env:DECKBENCH_MENTOR_PYTHON = "C:\path\to\venv\Scripts\python.exe"
```

2. `mentor.local.json`（仓库根目录、exe 旁边，或数据目录 `gui/.data` / exe 旁的 `data`）。相对路径相对 json 文件本身。此文件已 gitignore，不要放进发布 zip。

```json
{
  "site": "C:\\path\\to\\venv\\Lib\\site-packages",
  "py": "C:\\path\\to\\spire-mentor\\sts2-pycli\\python",
  "python": "C:\\path\\to\\venv\\Scripts\\python.exe"
}
```

3. 程序目录下的 `mentor/`：`mentor/site/sts2_rs/`、`mentor/py/sts2_hint/`，可选 `mentor/python.txt`（一行，指向 python.exe）。这个目录同样不要放进发布 zip。

`python` 必须是**构建 sts2_rs 的那个 CPython**（`python.exe`，不要用 `pythonw.exe`）。源码运行时不填也能用当前解释器；**Windows 打包版必须填**，见下面「打包版」。

**`mentor-full` 的 PPO 网络**：它们在 spire-mentor 仓库的 `sts2-pycli/data/ppo/`（`champions.toml` + 每角色的 `.onnx`）。
`sts2_rs` 按**编译时**的路径找它们：`<构建时的 sts2-rs 目录>/../sts2-pycli/data/ppo`。所以请在完整的 spire-mentor 克隆里构建，构建后不要移动或删除这个目录。
找不到网络时 Rust 会 panic，我们会捕获并把局外决策回退到 learned（统计里的 `errors` 会显示出来）。
上游另有 `STS2_RUNAI_PPO=<model.onnx>` 只能指定一个网络（所有角色共用），一般不需要。
*The PPO networks live in spire-mentor's `sts2-pycli/data/ppo/`; `sts2_rs` locates them via its compile-time path `<sts2-rs>/../sts2-pycli/data/ppo`, so build inside a full checkout and keep that directory in place. If they are missing, the Rust panic is caught and non-combat decisions fall back to the learned AI.*

**图形界面 / GUI**：「新建测试 → 整局批量 → AI」里有「spire-mentor 整局 AI（外部）」和「spire-mentor 整局 AI＋事件」。目录齐了才能选；没配置时是灰的，并写明缺什么。打包版还要能找到 `python`，否则同样是灰的（提示里会要 `DECKBENCH_MENTOR_PYTHON`）。
只支持原版 5 个角色。选了模组角色会在日志里提醒：局外决策回退到学习版。Windows 上回退时不使用搜索（没有 `os.fork()`）。
库完全加载失败时，这一次运行会**停下来**并写明原因，不会再静默整局改用学习版（认不出的单张牌 / 单次决策仍然回退，日志里有回退比例）。
*In the GUI both agents are listed under New test → Full runs. They stay greyed out until the directories exist; the packaged app also stays greyed out until `python` points at the interpreter that built `sts2_rs`. Mod characters are warned in the log. If the library fails to import, the run stops instead of silently scoring the learned AI; unknown individual cards still fall back, and the log prints the fallback rate.*

**打包版（不用自己重编 DeckBench）/ Windows package, no DeckBench rebuild**：
`DeckBench.exe` 是 PyInstaller 打出来的，加载不了你用 maturin 编的 `sts2_rs`（解释器不是同一个）。官方 zip **仍然不附带** spire-mentor 的代码、`.pyd`、ONNX 或数据。要用这个 AI 做种子筛选：

1. 自己按 spire-mentor 的说明构建 `sts2_rs`（在完整克隆里构建，好让它按编译路径找到 `sts2-pycli/data/ppo`）。不要把构建结果打进 DeckBench 的 zip，也不要发给别人。
2. 在 exe 旁边放上面的 `mentor.local.json`，`python` 指向该 venv 的 `python.exe`。
3. 重新打开 DeckBench。界面会用那个 Python 跑 `sim/gui` 里的工作进程（打包脚本会把我们自己的 `gui/*.py` 放到 `sim/gui`，所以玩家不用再编一次 DeckBench）。游戏缓存仍在 `%LOCALAPPDATA%\deckbench`，和双击 exe 共用。
4. 选原版角色、`mentor-full` 或 `mentor-full-ev`。跑完看日志：战斗回退比例、以及 `PPO 网络/回退`。回退接近 100% 时不要拿这批胜率做筛选（网络没找到，或牌不认识）。

*The packaged exe cannot load a maturin-built `sts2_rs`. The zip still ships none of spire-mentor. Point `mentor.local.json` at your venv's `python.exe`; the app then runs our worker (`sim/gui`, copied at package time) under that interpreter. Shared cache: `%LOCALAPPDATA%\deckbench`. If the log shows ~100% fallback, do not use the win rate for seed screening.*

**冒烟 / Smoke**（先确认加载，再打 1 局；没有配置时第一步就应失败，退出码 2）：

```bash
# Linux/macOS，仓库根目录
PYTHONPATH=. python -m sts2sim.engine.mentor_paths
PYTHONPATH=. python tools/batch.py --char Ironclad --asc 0 --n 1 --procs 1 --agent mentor-full-ev --seed 7F3K9Q2ZB8MA
```
```powershell
# Windows 源码，或官方 zip 解压后的文件夹（把路径换成你的）
$env:PYTHONPATH = "D:\DeckBench\sim"          # 源码则是仓库根，例如 D:\deckbench
$env:STS2SIM_ROOT = $env:PYTHONPATH
$env:DECKBENCH_MENTOR_SITE = "C:\spire-mentor\.venv\Lib\site-packages"
$env:DECKBENCH_MENTOR_PY = "C:\spire-mentor\sts2-pycli\python"
& "C:\spire-mentor\.venv\Scripts\python.exe" -m sts2sim.engine.mentor_paths
& "C:\spire-mentor\.venv\Scripts\python.exe" -m gui.worker batch --char Ironclad --asc 0 --n 1 --procs 1 --agent mentor-full-ev --game-seed 7F3K9Q2ZB8MA --out "$env:TEMP\mentor-smoke.jsonl"
```

`mentor_paths` 打印 `import: ok` 且退出码 0 才算接上。接着那一局的日志里应有 mentor 决策数，以及 PPO 的「网络/回退」次数；网络侧不应全是 0。`tools/batch.py` 仍只支持 Linux/macOS（用了 `SIGALRM`）；Windows 用上面的 `python -m gui.worker`，或直接在界面里把局数设成 1。
*Smoke: `python -m sts2sim.engine.mentor_paths` must print `import: ok` and exit 0. Then one Ironclad run; the log should show mentor decisions and non-zero PPO net counts. `tools/batch.py` stays Linux/macOS-only; on Windows use `python -m gui.worker` or one run in the GUI.*

**已知上游问题：v0.111 的 19 张新牌（SIDESTEP 等）/ Known upstream bug: 19 v0.111 cards**
spire-mentor 已经实现了这些牌，但 `state_from_dict` 查牌 id 时只查 `CardId::all()`（v0.107.1 的牌表），漏了 `CardId::V0111_ONLY`，
所以只要牌组里有这些牌，每次战斗决策都会报 `UnsupportedStateError` 并回退到我们的 AI（Silent 约 5.5%、Ironclad 约 3.8% 的战斗决策）。
我们有一个很小的本地补丁 [`docs/patches/spire-mentor-v0111-cards.patch`](patches/spire-mentor-v0111-cards.patch)（只改 spire-mentor 自己的代码，两处加 `.chain(CardId::V0111_ONLY.iter())`，不含游戏文本或数据）。
在你的 spire-mentor 克隆里 `cd sts2-rs && git apply <补丁>`，再重新构建 `sts2_rs`；打补丁后回退降到约 0.2–0.3%。
*spire-mentor implements these cards, but `state_from_dict` only searches `CardId::all()` (the v0.107.1 set) and misses `CardId::V0111_ONLY`, so decks with them fall back to our AI. A tiny code-only patch (no game text/data) is in `docs/patches/spire-mentor-v0111-cards.patch`: apply it in your spire-mentor checkout (`cd sts2-rs && git apply …`) and rebuild.*

## 通用 AI（modai）/ General AI

`--agent modai`：选牌（含跳过）、休息点、商店由一个与角色无关的小网络决定（`sts2sim/engine/modai.py`，纯 Python 推理，Windows 可用）；路线和出牌用 learned。
网络只看通用数值（费用、伤害、格挡、抽牌、能量、状态、关键词、稀有度、牌组统计、生命、金币…），**不看牌/遗物 ID**，所以模组角色也能用。
它是用 spire-mentor 的 PPO 当老师、在原版 5 个角色的本机对局上蒸馏出来的；`data/modai_model.json` 只有网络权重和特征归一化参数（约 200 KB），不含任何游戏数据。
`DECKBENCH_MODAI_MODEL=<json>` 换模型。参考（R0–R59，每格 60 局）：原版五角色平均层数 A0 19.5 → 23.8（0 → 4 胜）、A10 13.1 → 14.5；Claude娘 A0 16.8 → 20.2、A10 13.0 → 14.2。
*`modai`: a character-agnostic network for card rewards, rest sites and shops (generic numeric features only, no card/relic IDs), distilled from spire-mentor's PPO on vanilla characters; the model file holds weights only.*

## MCP 对战模式 / MCP play mode

见 [docs/MCP.md](MCP.md)：`tools/mcp_server.py`（stdio 或 streamable-HTTP），每局一个子进程，可撤销/恢复/导出。需要 `pip install -r requirements-mcp.txt`。

## 旧版 YAML 战斗模拟器 / Legacy YAML combat simulator

单场战斗大批量测试：卡牌用 YAML + Python 钩子写（见 [MODDING.md](MODDING.md)），实验配置在 `experiments/*.yaml`。

运行（`python -m sts2sim <实验.yaml>`）需要两样不随仓库分发的本机数据：
  - spire-codex 格式的怪物/遭遇/卡牌 JSON（`eng_*.json`、`zhs_*.json`）：用第三方工具 spire-codex 从你自己的安装导出，
    放到 `data/spire-codex/` 或用 `DECKBENCH_CODEX_DIR` 指定；
  - 原版对照组 `mods/vanilla/`（原版卡牌的 YAML 写法，自行整理；已 gitignore）。
  缺少时会报错退出；整局模拟和 GUI 的整局功能不受影响。界面里卡牌名称在没有这份数据时显示为 ID。


```bash
# Linux/macOS
.venv/bin/python -m sts2sim experiments/quick.yaml                  # 冒烟：约 250 场，几秒
.venv/bin/python -m sts2sim experiments/claude_v34.yaml --fights 300 --jobs 8 --seed 20261020
.venv/bin/python -m sts2sim experiments/claude_v34.yaml --fights 50 --agent beam   # 束搜索 AI
```
```powershell
# Windows
.venv\Scripts\python -m sts2sim experiments\quick.yaml
```

参数：`--fights`（每格场数）、`--jobs`（并行进程）、`--seed`、`--agent`（`heuristic` / `beam`）、`--out`（输出目录，默认 `reports/<实验名>/`）。
输出：`report.md`（中文报告）、`cells.csv`、`cards.csv`、`encounters.csv`、`coverage_*.csv`、`raw.jsonl`、`meta.json`。
同一个种子、同样的参数 → 完全相同的结果（与并行数无关）。

### 敌人数据从哪来 / Where enemy behaviour comes from

- 出招逻辑：`tools/parse_monster_ai.py` 从**本机反编译**的 `Models/Monsters/*.cs` 解析出招状态机（MoveState、RandomBranchState 的权重 / 不可重复 / 最多连续 N 次 / 冷却、ConditionalBranchState 的条件、开场招），首次生成时写进本机缓存的 `monster_ai.json`。
- 遭遇组成：`tools/parse_encounters.py` 解析 `Models/Encounters/*.cs` 的 `GenerateMonsters()`，写进缓存的 `encounter_monsters.json`；解析不了的少数遭遇退回近似组成。
- 招式数值、名字：来自你本机导出的 spire-codex 格式 JSON（见上）；它漏掉的招式数值由代码推出。
- AI 读取意图：`C.predict_intent_damage(enemy)` = 意图伤害 × 段数，含力量/虚弱/易伤，击晕或沉睡时为 0。
- 覆盖率：每份报告第 6 节 + `coverage_*.csv`；`tools/import_codex.py` 可把还没实现的遗物/药水/能力导出成本机 YAML 桩（`data/stubs/`，已 gitignore，不要提交）。

### 已知限制（旧版）

- 单场战斗、满血开局；不模拟地图/选卡/商店/事件，成型卡组是手写的约 15 张 + 自动升级。
- 召唤不生成新敌人；少数敌人能力只记层数；随机数和游戏不同，同种子出招不会逐招一致（分布和约束一致）。
- 启发式 AI 是贪心的，不会为下回合规划；需要先铺引擎的组合可以换束搜索 AI（`--agent beam`）。

## 目录结构 / Layout

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

## 测试 / Tests

```bash
.venv/bin/python -m pytest -q tests          # Linux/macOS
```
```powershell
.venv\Scripts\python -m pytest -q tests     # Windows
```

- 不需要游戏：`tests/test_gamedata.py`（找安装、缓存绑定/拒绝加载、仓库里没有生成代码）。
- 需要本机生成的缓存（没有时自动 skip）：`test_engine.py`、`test_ai_upgrade.py`、`test_claude_v35.py`、`test_status_damage.py`。
- 需要旧版模拟器的本机数据（spire-codex JSON + `mods/vanilla/`，没有时不收集）：`test_claude.py`、`test_intents.py`、`test_shensu.py`。
- 图形界面端到端：`gui/tests_e2e.py`（Playwright，先 `python -m gui.app --serve --port 8765`）。

## Claude娘（示例 mod）专用工具 / Claude-mod tools

- `tools/sync_claude_text.py <设计脚本目录>`：只读导入设计数据（v34_data.py），把卡面文字写进 `mods/claude_v34/cards.yaml`，
  并核对每张卡的类型/稀有度/费用与设计一致；同时更新 `tests/fixtures/claude_v34_design.json`（测试用快照）。改效果请改 `cards_src.yaml` 再同步。
- 风控契约（主动/被动给予、次级施加、RLHF 只改数值不递归、人工制品拦截给予与复制、层数操作不算给予/清除、清理指标每张牌最多返 1 能量、扣信用分每回合一次…）
  全部写在 `mods/claude_v34/hooks.py`，对应测试在 `tests/test_claude.py`。


## Windows 打包版 / Building the Windows package

```powershell
# 1) 自包含反编译器（只需一次；需要 .NET 9 SDK，可以在任何系统上交叉发布 win-x64）
dotnet tool install -g ilspycmd --version 9.1.0.7988
dotnet publish gui\packaging\decompiler\ilspycmd-host.csproj -c Release -r win-x64 --self-contained -o <decompiler 目录> -p:IlspyToolDir=<ilspycmd 工具目录 tools\net8.0\any>
# 2) 打包（Python 3.12 venv 里装 requirements-gui.txt + pyinstaller；需要 Node.js）
powershell -ExecutionPolicy Bypass -File gui\packaging\build.ps1 -Work <工作目录> -Py <venv>\Scripts\python.exe -Decompiler <decompiler 目录> -Version 0.1.3
# 3) 审计：确认包里没有任何游戏文件/数据/生成代码（可选：与游戏安装、本机缓存逐文件比对哈希）
powershell -ExecutionPolicy Bypass -File gui\packaging\audit.ps1 -Path <工作目录>\DeckBench-0.1.3-win64.zip -GameDir "<游戏目录>" -Cache "$env:LOCALAPPDATA\deckbench"
```

- `build.ps1` 只打包 **git 跟踪的文件**（`git ls-files`），所以本机生成的 `game.py`、缓存等不可能混进去；临时文件/缓存都放在 `-Work` 目录。
- 自带的反编译器是**未修改的** ilspycmd 9.1.0.7988（MIT）加一个很小的启动器（`gui/packaging/decompiler/`），连同 .NET 9 运行时自包含发布，
  玩家不需要安装 .NET SDK。`sts2sim/gamedata.py` 查找顺序：`DECKBENCH_ILSPY` → exe 旁的 `decompiler\` → 系统里的 `ilspycmd`。
  它生成的 `game.py` 与 SDK 版 ilspycmd 生成的逐字节一致。
- 第三方声明：`gui/packaging/THIRD-PARTY-NOTICES.txt` + `gui/packaging/notices/`，打包时一起放进 zip。
- 打包版参数：`DeckBench.exe --game-dir <游戏目录>`（之后会记住）、`--browser`、`--serve --port N`；环境变量 `DECKBENCH_NO_DIALOG=1` 关闭弹窗（自动化测试用）。
- `sim/gui`：我们自己的界面 Python（不含 `web/`、不含 `packaging/`），给玩家本机的 CPython 跑 `mentor-full` / `mentor-full-ev`。不要把 `sts2_rs`、`sts2_hint`、`.onnx`、`champions.toml` 或 `mentor.local.json` 放进 zip。`audit.ps1` 会拒收这些路径和扩展名。
  *`sim/gui` is our own UI code so the player's CPython can run the mentor agents. Do not put `sts2_rs`, `sts2_hint`, `.onnx`, `champions.toml` or `mentor.local.json` in the zip; `audit.ps1` rejects them.*

## 已知限制 / Known limitations

- 模拟结果只适合在同一套假设下横向比较，不是真实胜率。
- 首次生成需要 .NET 9 SDK + ilspycmd；转译器针对 v0.111 系列验证过，游戏大版本更新后可能需要更新转译器/补丁（`tools/cs2py_*.py`、`tools/cs_patches.py`、`sts2sim/rt/patches.py`）。
- Windows 上没有 fork，带搜索的 AI 不可用；`tools/batch.py` 命令行只支持 Linux/macOS。
- 图形界面第一次生成数据时（1–2 分钟）只有一个「请稍候」提示框，没有进度条。
- 和真实游戏 DLL 的对拍（第三方无头工具 sts2-cli，100 场幕 1 战斗逐步对照）：0.1.1 里 97 场完全一致。剩下 3 场都是储君的 Tyranny / Foregone Conclusion：
  游戏在**玩家回合开始时**要求选牌（`AfterPlayerTurnStart` / `BeforeHandDraw`），我们的引擎会正确给出选牌；sts2-cli 的 `end_turn` 在等待新回合时不处理这种待选状态，
  当成卡死，最后强制结束（它自己的日志里先打出了同样数量的候选牌，再报 “EndTurn stuck … forcing game_over”）。这是 sts2-cli 的问题，不是模拟器的。
  *Parity vs the real DLL (via the third-party headless tool sts2-cli, 100 act-1 fights, step by step): 97/100 identical in 0.1.1. The other 3 are Regent's Tyranny / Foregone Conclusion,
  which ask for a card choice at the start of the player's turn. We surface that choice correctly; sts2-cli's `end_turn` treats the pending choice as a deadlock and forces game over
  (its own log shows the same number of options first). This is an sts2-cli limitation, not a simulator bug.*

## 打法风格 / Play styles

打法风格是叠在 AI 上的一层规则，注册表在 `sts2sim/engine/style.py` 的 `STYLES`：每个风格有四种语言的名字和说明、`apply` 函数（`None` = 不改 AI）、能叠在哪些 AI 上（AI id 前缀）。批量（`--style`）、单卡 A/B、图形界面（「新建测试 → 整局批量」的「打法风格」下拉框、`GET /api/styles`、运行参数 `style`）和 MCP（`new_run(style=…)`、`list_styles`）都从这里读。每局结果 JSONL 里有 `style` 字段。

加一个新风格：写一个 mixin（参考 `JugglerMixin`）和 `apply_xxx(agent)`，在 `STYLES` 里加一项，再把 id 加进 `tools/batch.py` 的 `STYLE_IDS`；`tests/test_style.py` 会检查两边一致，并检查 `standard` 和不加风格的结果完全相同。

*Play styles are a rule layer on top of an AI, registered in `STYLES` in `sts2sim/engine/style.py` (names/descriptions in four languages, an `apply` function, compatible AI prefixes). Batch `--style`, `ab_card.py --style`, the GUI dropdown / `GET /api/styles` / run param `style`, and MCP `new_run(style=…)` / `list_styles` all read it. Each run record has a `style` field.*
