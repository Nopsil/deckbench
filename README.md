# DeckBench · 牌组测试台

**牌组测试台：不进游戏，让 AI 自动打几百上千局，告诉你胜率、能打到第几层、死在哪、某张卡强不强。**
给《杀戮尖塔 2》mod 作者和玩家用的非官方平衡测试工具。

*A deck test bench for Slay the Spire 2: without opening the game, an AI plays hundreds or thousands of runs and tells you the win rate, how far you get, what kills you, and whether a card is actually strong. Unofficial, for mod authors and players.*

> **⚠️ 免责声明**
> - **非官方**：粉丝制作，与 Mega Crit 无关，未获其认可或赞助。
> - **不含任何游戏数据**：仓库里没有游戏文件、游戏代码或游戏数据。需要的内容只在你自己电脑上、从你自己的游戏安装生成，并绑定这份安装（换了或更新了就要重新生成）。
> - **需要你自己的正版游戏**：Steam 正式版或公开测试版（beta）都行。找不到游戏时程序会报错退出。
> - **不接受游戏资源**：含游戏代码、数据、文本或美术的 PR 一律拒绝（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。
> - **滥用责任自负**：任何人利用本项目分发游戏代码或文件，责任由其本人承担，与作者无关。
> - **许可范围**：[LICENSE](LICENSE)（MIT）只覆盖我们自己写的代码，不授予任何游戏代码、数据、美术或商标的许可。
> - Slay the Spire 2 是 Mega Crit 的商标，这里提到游戏名只是为了说明适用于哪款游戏。
> - 联系方式：**nopsil@hotmail.com**（版权方有任何问题请联系，我们会尽快处理）
>
> <details><summary><b>Disclaimer (English)</b></summary>
>
> - **Unofficial**: fan-made; not affiliated with, endorsed or sponsored by Mega Crit.
> - **Ships no game data**: no game files, code or data in this repo. Everything game-related is generated on your own PC from your own install and bound to it (regenerated if the install changes or updates).
> - **Needs your own copy of the game**: Steam stable or public beta. The program exits with an error if it can't find the game.
> - **Game-asset PRs are rejected**: no game code, data, text or art (see [CONTRIBUTING.md](CONTRIBUTING.md)).
> - **Misuse is the misuser's responsibility**: anyone who uses this project to redistribute game code or files is solely responsible, not the authors.
> - **License scope**: [LICENSE](LICENSE) (MIT) covers only our own code and grants no license to any game code, data, art or trademarks.
> - Slay the Spire 2 is a trademark of Mega Crit; the name is used only to say which game this works with.
> - Contact: **nopsil@hotmail.com** (rights holders: please reach out, we'll respond promptly).
>
> </details>

## 能做什么 / What it does

- **测胜率和能走多远**：选角色、进阶等级和 AI，让它自动打完整的一局（地图、战斗、奖励、商店、事件），一次几百局，看胜率、平均到第几层、各幕通过率。
- **看死因**：统计在哪种怪、哪场战斗死得最多，快速找到卡组的短板。
- **单卡 A/B**：同样的种子，一组加某张卡、一组不加，直接看这张卡让胜率和层数变了多少。
- **测你自己的 mod**：内置示例 mod（Claude娘，原创内容），也可以上传自己写的 YAML mod 跑战斗测试。
- **图形界面，全在本机**：点选参数、一键运行、实时进度、图表报告、历史记录，不联网也不上传任何东西。

*Win rate and floors reached for full runs at any ascension; death causes; same-seed single-card A/B tests; test your own mods; a local desktop app with charts and history (nothing is uploaded).*

## 开始使用（Windows） / Getting started (Windows)

> 打包好的 .exe（下载即用）**计划中**，以后会放在 Releases 页面；现在需要按下面的步骤装一次环境。
> *A ready-to-run .exe is planned for the Releases page; for now, set it up once with the steps below.*

**一次性准备 / One-time setup**

1. **装好游戏**：Steam 里安装《杀戮尖塔 2》（正式版或 beta 都行）。
2. **装 Python 3.11 或更新版本**：从 [python.org](https://www.python.org/downloads/) 下载安装，安装时**勾选「Add python.exe to PATH」**。
3. **装 .NET 9 SDK**：从 [dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/9.0) 下载 SDK 安装（用来在你电脑上读取游戏文件）。
4. **装 Node.js（LTS 版）**：从 [nodejs.org](https://nodejs.org/) 下载安装（只在第一次构建界面时用）。
5. **装 ilspycmd**：打开一个**新的** PowerShell 窗口，运行：
   ```powershell
   dotnet tool install -g ilspycmd --version 9.1.0.7988
   ```
6. **下载 DeckBench**：在本页面点 **Code → Download ZIP**，解压到比如 `D:\deckbench`（会用 git 的也可以 `git clone`）。

**安装并启动 / Install and launch**

在 `D:\deckbench` 文件夹里打开 PowerShell（在文件夹空白处按住 Shift 右键 →「在此处打开 PowerShell 窗口」，或者先运行 `cd D:\deckbench`），依次运行：

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-gui.txt
cd gui\web; npm install; npm run build; cd ..\..
.venv\Scripts\python -m gui.app
```

前三行只需要运行一次。以后每次使用，只要在这个文件夹里运行最后一行：
```powershell
.venv\Scripts\python -m gui.app
```

**第一次启动**会自动找到你的 Steam 游戏，并在你电脑上生成需要的数据，大约 **1–2 分钟**（这段时间窗口还没出现，请耐心等）。之后启动就很快了。界面会在独立窗口打开；如果窗口打不开，会自动改用浏览器打开。

**找不到游戏？** 如果游戏装在非默认位置，告诉它游戏文件夹在哪（换成你自己的路径）：

```powershell
.venv\Scripts\python -m sts2sim.gamedata setup --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

或者在启动前设置环境变量（只对当前窗口有效）：
```powershell
$env:DECKBENCH_GAME_DIR = "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

*Install the game, Python 3.11+ (tick "Add to PATH"), .NET 9 SDK, Node.js LTS and ilspycmd; download the ZIP; run the four commands above in PowerShell inside the folder. The first launch generates data from your game in about 1–2 minutes. If your game is in a non-default Steam library, pass `--game-dir` as shown or set `DECKBENCH_GAME_DIR`. Linux/macOS: see [docs/DEVELOPER.md](docs/DEVELOPER.md).*

## 怎么看结果 / Reading results

- **胜率**：打赢最终首领的局数占比。
- **平均层数 / 各幕通过率**：AI 平均能走到第几层、有多少局过了第 1、2、3 幕。胜率很低时（比如高进阶），看层数更有区分度。
- **死因**：每局死在哪场战斗（哪种怪 / 精英 / 首领），帮你找到卡组扛不住的地方。
- **单卡 A/B**：两组用同样的随机种子，唯一区别是那张卡，所以差值就是这张卡的影响；样本少时差值会抖，局数越多越可信。

**重要**：AI 不是真人高手，这些数字**不是真实玩家的胜率**。它们适合在**同一套设置下互相比较**（新卡 vs 旧卡、改数值前 vs 改后、你的角色 vs 原版角色），不适合当成绝对水平。

*Win rate = runs that beat the final boss; floors / act clear rates show how far the AI gets (more useful when win rates are low); death causes show which fights kill you; single-card A/B uses identical seeds so the difference is the card's effect. These are not real player win rates: compare results only under the same settings.*

## 常见问题 / FAQ

**提示「找不到游戏安装 / Game install not found」**
确认游戏已在 Steam 里装好，然后用上面的 `--game-dir` 或 `DECKBENCH_GAME_DIR` 指向游戏文件夹（`...\steamapps\common\Slay the Spire 2`）。
*Make sure the game is installed, then point to it with `--game-dir` or `DECKBENCH_GAME_DIR`.*

**游戏更新了 / 切换了 beta 分支**
生成的数据绑定在你当时的游戏文件上，文件变了就不会再用旧数据。图形界面下次启动时会自动重新生成（同样 1–2 分钟）；也可以手动运行：
`.venv\Scripts\python -m sts2sim.gamedata setup`
*Data is bound to your game files; after an update the app regenerates it on next launch, or run the command above.*

**为什么 Windows 上没有「强 AI（带搜索）」「学习版 AI（带搜索）」？**
带搜索的 AI 需要系统的 fork 功能，Windows 没有，所以界面里会自动隐藏。Windows 上推荐用 **「学习版 AI（推荐）」**，它不需要搜索。
*Search-based AIs need `fork()`, which Windows lacks; use "learned" (recommended) on Windows.*

**为什么必须有自己的游戏？**
我们不能也不会分发游戏的任何内容。DeckBench 只在你电脑上读取你自己的游戏来模拟它的规则，所以没有正版游戏就没法用。
*We can't and won't redistribute any game content; DeckBench reads your own install locally to simulate the game.*

**`npm` 报错「禁止运行脚本」**
把命令里的 `npm` 换成 `npm.cmd`（例如 `npm.cmd install; npm.cmd run build`）。
*If PowerShell blocks `npm`, use `npm.cmd` instead.*

**ilspycmd 找不到 / 提示需要 ilspycmd**
装完 .NET 9 SDK 后要**新开**一个 PowerShell 窗口再运行 `dotnet tool install` 那一行，然后重新启动 DeckBench。
*Open a new PowerShell window after installing the .NET 9 SDK, run the `dotnet tool install` line, then relaunch.*

## 进阶 / Advanced

- [docs/DEVELOPER.md](docs/DEVELOPER.md)：命令行批量运行（全部参数）、首次生成的内部原理、可选的 spire-mentor AI、旧版战斗模拟器、目录结构、测试（含 Linux/macOS 命令）。
- [docs/MODDING.md](docs/MODDING.md)：用 YAML + Python 写自己的 mod（卡牌、能力、遗物、卡组、实验）。
- [gui/README.md](gui/README.md)：图形界面的结构和打包。
- [CONTRIBUTING.md](CONTRIBUTING.md)：贡献须知（不接受任何游戏内容）。

## License

MIT，仅限我们自己的代码，详见 [LICENSE](LICENSE)。*MIT for our own code only; see [LICENSE](LICENSE).*
