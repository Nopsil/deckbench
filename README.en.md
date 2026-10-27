[简体中文](README.md) | **English** | [日本語](README.ja.md) | [한국어](README.ko.md)

# DeckBench

**A deck test bench: without opening the game, an AI plays hundreds or thousands of runs and tells you the win rate, how far you get, what kills you, and whether a card is actually strong.**
An unofficial balance-testing tool for Slay the Spire 2 mod authors and players.

> **Languages:** the app is available in English, 简体中文, 日本語 and 한국어. It starts in your system's language, and you can switch at any time from the language menu at the bottom left (your choice is remembered). Card, character and enemy names follow the same language and are read from your own game install.

> **⚠️ Disclaimer**
> - **Unofficial**: fan-made; not affiliated with, endorsed or sponsored by Mega Crit.
> - **Ships no game data**: no game files, code or data in this repo. Everything game-related is generated on your own PC from your own install and bound to it (regenerated if the install changes or updates).
> - **Needs your own copy of the game**: Steam stable or public beta. The program exits with an error if it can't find the game.
> - **Game-asset PRs are rejected**: no game code, data, text or art (see [CONTRIBUTING.md](CONTRIBUTING.md)).
> - **Misuse is the misuser's responsibility**: anyone who uses this project to redistribute game code or files is solely responsible, not the authors.
> - **License scope**: [LICENSE](LICENSE) (MIT) covers only our own code and grants no license to any game code, data, art or trademarks.
> - Slay the Spire 2 is a trademark of Mega Crit; the name is used only to say which game this works with.
> - Contact: **nopsil@hotmail.com** (rights holders: please reach out, we'll respond promptly).
>
> <details><summary><b>免责声明（中文）</b></summary>
>
> - **非官方**：粉丝制作，与 Mega Crit 无关，未获其认可或赞助。
> - **不含任何游戏数据**：仓库里没有游戏文件、游戏代码或游戏数据。需要的内容只在你自己电脑上、从你自己的游戏安装生成，并绑定这份安装（换了或更新了就要重新生成）。
> - **需要你自己的正版游戏**：Steam 正式版或公开测试版（beta）都行。找不到游戏时程序会报错退出。
> - **不接受游戏资源**：含游戏代码、数据、文本或美术的 PR 一律拒绝（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。
> - **滥用责任自负**：任何人利用本项目分发游戏代码或文件，责任由其本人承担，与作者无关。
> - **许可范围**：[LICENSE](LICENSE)（MIT）只覆盖我们自己写的代码，不授予任何游戏代码、数据、美术或商标的许可。
> - Slay the Spire 2 是 Mega Crit 的商标，这里提到游戏名只是为了说明适用于哪款游戏。
> - 联系方式：**nopsil@hotmail.com**（版权方有任何问题请联系，我们会尽快处理）
>
> </details>

## What it does

- **Win rate and how far you get**: pick a character, an ascension level and an AI, and let it play full runs on its own (map, fights, rewards, shops, events) — hundreds at a time. You get the win rate, the average floor reached, and the clear rate for each act.
- **Death causes**: see which enemies and which fights kill you most often, so you can quickly spot your deck's weak points.
- **Single-card A/B**: same seeds, one group with a card added and one without — see directly how much that one card changes the win rate and floors reached.
- **Test your own mod**: a sample mod is built in (Claude娘, original content), and you can upload your own YAML mod for combat tests.
- **A desktop app, all on your PC**: pick settings with a few clicks, run with one button, live progress, chart reports and history. Nothing goes online and nothing is uploaded.
- **Four languages**: English, 简体中文, 日本語 and 한국어, switchable in the app; game names (cards, characters, enemies) come from your own install in the same language.

## Getting started (Windows)

### Easiest: the packaged app

1. Install Slay the Spire 2 on Steam (stable or beta both work).
2. Go to the [Releases page](https://github.com/Nopsil/deckbench/releases), download `DeckBench-<version>-win64.zip`, and **unzip the whole thing** into a folder (for example `D:\DeckBench`).
3. Double-click `DeckBench.exe`. On the first launch a "please wait" message appears while it generates data from your game — about 1–2 minutes — and then the app opens by itself.
   **No need to install Python or .NET** (the decompiler is already bundled in the `decompiler` folder).
4. If the game is installed somewhere other than the default location, open PowerShell in that folder and run this once:
   `.\DeckBench.exe --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"`. After that, just double-click as usual.

### Run from source

**One-time setup**

1. **Install the game**: install Slay the Spire 2 on Steam (stable or beta both work).
2. **Install Python 3.11 or newer**: download it from [python.org](https://www.python.org/downloads/) and **tick "Add python.exe to PATH"** during setup.
3. **Install the .NET 9 SDK**: download the SDK from [dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/9.0) (used to read the game files on your PC).
4. **Install Node.js (LTS)**: download it from [nodejs.org](https://nodejs.org/) (only needed the first time the interface is built).
5. **Install ilspycmd**: open a **new** PowerShell window and run:
   ```powershell
   dotnet tool install -g ilspycmd --version 9.1.0.7988
   ```
6. **Download DeckBench**: on this page click **Code → Download ZIP** and unzip it to, say, `D:\deckbench` (or `git clone` it if you use git).

**Install and launch**

Open PowerShell in the `D:\deckbench` folder (Shift + right-click on an empty spot in the folder → "Open PowerShell window here", or run `cd D:\deckbench` first), then run these in order:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-gui.txt
cd gui\web; npm install; npm run build; cd ..\..
.venv\Scripts\python -m gui.app
```

The first three lines only need to be run once. After that, every time you want to use it, just run the last line in this folder:
```powershell
.venv\Scripts\python -m gui.app
```

**On the first launch** it finds your Steam game automatically and generates the data it needs on your PC. This takes about **1–2 minutes** (the window won't appear yet during this time, so please be patient). Later launches are fast. The app opens in its own window; if that window can't open, it falls back to your browser.

**Can't find the game?** If the game is installed somewhere other than the default location, tell it where the game folder is (replace with your own path):

```powershell
.venv\Scripts\python -m sts2sim.gamedata setup --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

Or set an environment variable before launching (only applies to the current window):
```powershell
$env:DECKBENCH_GAME_DIR = "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

Linux/macOS: see [docs/DEVELOPER.md](docs/DEVELOPER.md).

## Which AI to pick

- **General AI (recommended, works with mod characters)**: the one to use in most cases. Card picks, rest sites and shops are handled by a small network that only looks at generic numbers (cost, damage, block, rarity…) and doesn't know specific card names, so **it works with your own mod characters too**. It's as fast as the learned AI (1–2 seconds per run) and works on Windows. In our tests it gets 1–4 floors further on average than the learned AI.
- **Learned AI**: the previous recommendation, same speed; useful for comparison.
- **The two spire-mentor full-run AI options**: stronger on the 5 base-game characters, for seed screening. They are in the official package, but spire-mentor itself is not: build it yourself and add `mentor.local.json` next to the app (the Windows package also needs `python` set to the interpreter that built it). Until then the two entries stay greyed out. See [docs/DEVELOPER.md](docs/DEVELOPER.md).

## Play a real game seed

In **New test → Full runs**, fill in **Game seed** with the seed shown in the game (for example `7F3K9Q2ZB8MA`). The AI then plays just that one run and records every decision, which you can look through on the results page.
Lowercase letters, and the letters O and I, are converted to uppercase and the digits 0 and 1 automatically, just like the game does. Command line: `python tools/batch.py --char Silent --seed 7F3K9Q2ZB8MA --log-dir steps`.

## Make a mod without code (Mod editor)

Open **Mod editor** on the left. Fill in forms for a character (HP, energy, starting deck, starting relic), cards (pick effects from a menu, such as Deal damage, Apply a power or Draw cards, or use a template), powers and relics (when → what). **Check** points out problems in plain language.
Then, under **Test**, start a full-run batch or a one-card A/B (same seeds, starting deck vs starting deck + this card) with one click. Import and export zips to share mods.
The same YAML files also work from the command line: put them in `mods/` and run `python tools/batch.py --mod mods/my_mod --char MyHero --agent modai`. Format reference: [docs/MODDING.md](docs/MODDING.md).

## Let an AI assistant play step by step (MCP)

If you use an AI assistant that supports MCP, such as Claude or Cursor, you can have it play a run in the simulator itself: it can read the situation, pick options, explain its reasons, undo and retry, and at the end export a step list so you can play the same seed in the real game and follow along.
For now this only works from source: `pip install -r requirements-mcp.txt`, then `python tools/mcp_server.py`. Card names are read from your own game install at runtime. See [docs/MCP.md](docs/MCP.md).

## Reading results

- **Win rate**: the share of runs that beat the final boss.
- **Average floor / act clear rates**: how far the AI gets on average, and how many runs cleared acts 1, 2 and 3. When win rates are very low (for example at high ascension), floors tell setups apart better.
- **Death causes**: which fight each run died in (which enemy / elite / boss), to help you find where your deck can't hold up.
- **Single-card A/B**: both groups use the same random seeds, and the only difference is that one card, so the gap is that card's effect. With few runs the gap jumps around; the more runs, the more you can trust it.

**Important**: the AI is not a skilled human player, so these numbers are **not real player win rates**. They're good for **comparing things under the same settings** (new card vs. old card, before vs. after a number change, your character vs. a base-game character), not as an absolute measure of strength.

## FAQ

**"找不到游戏安装 / Game install not found"**
Make sure the game is installed in Steam, then point to the game folder (`...\steamapps\common\Slay the Spire 2`) with `--game-dir` or `DECKBENCH_GAME_DIR` as shown above.

**The game updated / I switched to the beta branch**
The generated data is bound to your game files as they were; once the files change, the old data is no longer used. The app regenerates it automatically on the next launch (again 1–2 minutes), or you can run it by hand:
`.venv\Scripts\python -m sts2sim.gamedata setup`

**Why are "Strong AI (with search)" and "Learned AI (with search)" missing on Windows?**
The search-based AIs need the system's fork feature, which Windows doesn't have, so the app hides them automatically. On Windows, use **General AI (recommended, works with mod characters)**, which doesn't need search.

**Why do I need my own copy of the game?**
We can't and won't distribute any of the game's content. DeckBench only reads your own game on your PC to simulate its rules, so it can't work without a legit copy.

**`npm` errors with "running scripts is disabled"**
Replace `npm` with `npm.cmd` in the commands (for example `npm.cmd install; npm.cmd run build`).

**ilspycmd not found / says ilspycmd is required**
After installing the .NET 9 SDK, open a **new** PowerShell window, run the `dotnet tool install` line, then start DeckBench again.

## Advanced

- [docs/DEVELOPER.md](docs/DEVELOPER.md): command-line batch runs (all options), how the first-time data generation works, the optional spire-mentor AI, the legacy combat simulator, folder layout, tests (including Linux/macOS commands).
- Optional stronger AI: after you build the third-party [spire-mentor](https://github.com/tfriedel/spire-mentor) yourself, the official package can run `mentor-full` / `mentor-full-ev` (MCTS for fights, PPO for out-of-combat choices; base-game characters only) without rebuilding DeckBench. spire-mentor is not shipped with this project. On the Windows package, set `python` in `mentor.local.json` to the interpreter that built `sts2_rs`. It has a known loading problem with 19 new cards from v0.111 (SIDESTEP etc.), and we provide a small local patch. Smoke steps and packaging rules: [docs/DEVELOPER.md](docs/DEVELOPER.md#可选spire-mentor更强的-ai--optional-spire-mentor).
- [docs/MODDING.md](docs/MODDING.md): write your own mod in YAML + Python (cards, powers, relics, decks, experiments).
- [gui/README.md](gui/README.md): how the desktop app is structured and packaged.
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution rules (no game content of any kind).

## License

MIT, for our own code only; see [LICENSE](LICENSE).
