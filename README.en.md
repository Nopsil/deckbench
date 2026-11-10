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
- **A desktop app, all on your PC**: pick settings with a few clicks, run with one button, live progress, chart reports and history. Runs stay on your PC and nothing is uploaded. The footer shows the version. **Check for updates** in About stays off until you click it, and then it only asks GitHub Releases. The footer and About also open **What's new** (`#/whatsnew`). Dismissing it is remembered for that version.
- **Deck head-to-head and card impact**: two saved presets can run the same encounters and open the comparison. One preset can run leave-one-out and show how each card changes win rate, HP lost and turns. The whole run stays within 400 fights.
- **Progress, cancel and parallel fights**: a long test shows how many fights are done. Cancel happens between fights; the fight already started finishes. Combat batches take `workers`, default 1, capped at the smaller of the CPU count and 8. Each fight keeps its seed.
- **Four languages**: English, 简体中文, 日本語 and 한국어, switchable in the app; game names (cards, characters, enemies) come from your own install in the same language.
- **Import a real run**: read a finished run or the in-progress save (seed, route, card picks, relics) without modifying it.
- **Calibrate a real run against simulations**: for the same seed, character and card-pick path, compare real HP lost in each fight with the simulated distribution. A floor that does not line up is unmatched; a neighbouring fight is not used in its place.
- **Seed preview**: given a seed, see the map, encounter mix and opening rewards without playing a full run.

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

## Why the AI played that

Off by default. When you turn it on, each card play, target choice, potion use, and reward or shop pick writes the candidates that were already scored (the top few, with scores, and which one was chosen) to a JSONL file next to that run's output. The flag does not draw random numbers, so a fixed seed plays the same whether it is on or off.

- Full runs: `python tools/batch.py --explain --out runs.jsonl` (or `DECKBENCH_EXPLAIN=1`) writes `runs.explain.jsonl`.
- Legacy fight experiments: `python -m sts2sim experiments/quick.yaml --explain`, or `explain: true` in the experiment YAML, writes `explain.jsonl` next to `raw.jsonl`.
- Read one fight: `python tools/explain_fight.py runs.explain.jsonl --fight 0`.

## Try 0.1.5 features

From the repo root. The release notes (suitable as a GitHub Release body) are in [docs/RELEASE_0.1.5.md](docs/RELEASE_0.1.5.md).

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/seed_preview.py 7F3K9Q2ZB8MA --char Ironclad --asc 0 --neow first
python tools/import_dll_mod.py --list
python tools/import_dll_mod.py "/path/to/Slay the Spire 2/mods/MyMod" --out mods/my_mod
```

- The first line reads one run, read-only. The sample file uses fictional IDs and needs no game; point it at your own `history/*.run` or `current_run.save` instead. GUI: `#/import`, or `#/import?path=` to open one file.
- The second line shows the map, encounter queues and opening choices without a full AI run. It needs the data generated from your install. Act 2 and later are projections. GUI: `#/preview`, or `#/preview?seed=`.
- The last two lines turn a mod already installed in the game (manifest JSON + DLL) into YAML. The DLL is not executed. In the app: **Mod editor → Import game mod**.
- To screen recording seeds with `mentor-full`: the official package can run it, and does not ship spire-mentor. Put `mentor.local.json` next to the app (`site`, `py`, `python`). `python` is the interpreter that built `sts2_rs`. Do not use a win rate when fallback is about 100%. See [docs/DEVELOPER.md](docs/DEVELOPER.md).
- Release notes #59–#64: the browser smoke releases the Playwright event loop when that module finishes; two saved decks can run a head-to-head (`#/decks`); a long test shows progress and cancels between fights; leave-one-out card impact; the Windows package stamps the existing `0.1.5` and the update check stays manual; combat batches can set `workers` (default 1).
- #65–#67: What's new in the GUI, a 简体中文 / English switch, and a `.deckbench.zip` you can import on another DeckBench. With no game files, empty History can load demo data: a 30-fight head-to-head of two probe decks against the synthetic trio, not the training dummy, produced by the existing combat worker.

## Import a real run

Open **Import run** on the left. It reads a finished `history/*.run` or the in-progress `current_run.save` from your own game folder: seed, ascension, rooms visited, which card you picked on each floor, relics and the deck. It does not modify the save.
Command line: `python tools/import_run.py <file or folder>`. Where the files live, and how the two JSON shapes differ, is in [docs/SAVE_FORMAT.md](docs/SAVE_FORMAT.md).

## Calibrate a real run against simulations

Compare one imported run with simulations that share its **seed, character and card-pick path**. Each fight reports the real HP lost, the simulated mean, p10 and p90, and where the real value sits in that sample (midrank percentile). A real value outside the simulated p5–p95 band is flagged as a likely sim-model gap.

A floor matches a simulated fight only when the floor number, the combat room (normal / elite / boss) and the encounter id all agree. If the real floor has no encounter id, the encounter differs, or no simulated fight is on that floor, the row is `unmatched`. A neighbouring floor or a different encounter is not used instead. The pick path is the ordered `was_picked` cards, with a leading `CARD.` removed. The simulated `picked` list has to be that whole sequence; one extra or one missing card is a different path.

```bash
python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl
python tools/calibrate.py path/to/history/123.run path/to/runs.jsonl --json -
```

`POST /api/calibrate` takes `{"real","sim"}`. `sim` has to sit in an allowed directory (the same rule as `batch_run_summary`); `real` is one run file. MCP `calibrate(real, sim)` is read-only and is also on `--import-only`. It does not start a simulation and does not modify saves. The ids in the fixture are fictional. Matching rules, the percentile and the other endpoints are in [docs/CALIBRATION.md](docs/CALIBRATION.md).

**Calibration** in the sidebar (`#/calibrate`) picks an imported real run and a `runs.jsonl` in an allowed folder, or an uploaded file. The table shows floor, room, encounter, real HP lost, simulated mean / p10 / p90 and percentile, and highlights a likely sim gap. Unmatched floors are grey, with the reason. Each fight has a strip for the simulated band and the real value.

## Preview a seed

Open **Seed preview**. Enter a seed from the game (plus character and ascension) and see each act's map, how normals, elites and bosses are ordered, the opening choices and the rewards of the first normal fight — without an AI playing the whole run. Useful for picking a seed to record or for planning a route. Maps from act 2 on are projections; act 1 can be checked against a screenshot.
Command line: `python tools/seed_preview.py <seed> --char Ironclad --asc 0`. This needs the data DeckBench generates from your install.

## Make a mod without code (Mod editor)

Open **Mod editor** on the left. Fill in forms for a character (HP, energy, starting deck, starting relic), cards (pick effects from a menu, such as Deal damage, Apply a power or Draw cards, or use a template), powers and relics (when → what). **Check** points out problems in plain language.
Then, under **Test**, start a full-run batch or a one-card A/B (same seeds, starting deck vs starting deck + this card) with one click. Import and export zips to share mods.
The same YAML files also work from the command line: put them in `mods/` and run `python tools/batch.py --mod mods/my_mod --char MyHero --agent modai`. From install to the first commands (example mod, a tiny win-rate sample, a card A/B, and why a card was played): [docs/MOD_AUTHORS.md](docs/MOD_AUTHORS.md) ([中文](docs/MOD_AUTHORS.zh-CN.md)). Format reference: [docs/MODDING.md](docs/MODDING.md).

A mod already installed in the game does not have to be rewritten by hand first. In **Mod editor**, use **Import game mod** and pick that mod's zip (manifest JSON + DLL), or pick it from the dropdown of mods under the game's `mods/` folder. Cards we can read become a form. The DLL is not executed. Limits: [docs/DLL_MODS.md](docs/DLL_MODS.md).

## Let an AI assistant play step by step (MCP)

If you use an AI assistant that supports MCP, such as Claude or Cursor, you can have it play a run in the simulator itself: it can read the situation, pick options, explain its reasons, undo and retry, and at the end export a step list so you can play the same seed in the real game and follow along.
For now this only works from source: `pip install -r requirements-mcp.txt`, then `python tools/mcp_server.py`. Card names are read from your own game install at runtime. The same server can also read finished results without the GUI: `batch_run_summary` (win rate, Wilson interval, `sample_warning`), `card_ab` (a `p_value` for two result files you already have; it does not start a simulation), `explain_fight` (one fight from an `--explain` log, paged) and `calibrate` (real HP lost against simulations on the same card-pick path; a floor that does not line up is `unmatched`). Paths have to sit in an allowed directory. See [docs/MCP.md](docs/MCP.md).

## Reading results

- **Win rate**: the share of runs that beat the final boss, with a **Wilson 95% confidence interval**.
- **Average floor / act clear rates**: how far the AI gets on average, and how many runs cleared acts 1, 2 and 3. When win rates are very low (for example at high ascension), floors tell setups apart better.
- **Death causes**: which fight each run died in (which enemy / elite / boss), to help you find where your deck can't hold up.
- **Single-card A/B**: both groups use the same random seeds, and the only difference is that one card, so the gap is that card's effect. The win-rate gap also has a **two-proportion z-test p-value** (two-sided). The paired difference and its 95% interval are still reported.
- **Too few runs**: if either group has **fewer than 30** valid runs, the report says the sample is too small to conclude. The numbers are still printed; do not treat them as a verdict on the card.

On the command line this shows up in `python tools/batch.py`, `python tools/ab_card.py ... --format text` (or `markdown` / `json`), `python tools/ab_table.py <dir> --format markdown` (also `text` / `json`), and `python tools/ai_summary.py a.jsonl b.jsonl` (`--json` prints JSON; from the second file on, a p-value against the first). The report page and the A/B page show the Wilson interval, the p-value and the small-sample warning. The report and A/B HTTP APIs (`/api/runs/{id}/summary`, `/api/ab`) add these fields and keep the old ones. MCP `batch_run_summary` and `card_ab` return the same numbers without the GUI.

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

- [docs/INDEX.md](docs/INDEX.md): index of the docs (English and Chinese; the mod-author guide also has zh-CN). Calibration: [docs/CALIBRATION.md](docs/CALIBRATION.md). Continuous integration: [docs/CI.md](docs/CI.md). The coverage snapshot: [docs/COVERAGE.md](docs/COVERAGE.md).
- [docs/DEVELOPER.md](docs/DEVELOPER.md): command-line batch runs (all options), how the first-time data generation works, the optional spire-mentor AI, the legacy combat simulator, folder layout, tests (including Linux/macOS commands). CI itself is [docs/CI.md](docs/CI.md).
- Optional stronger AI: after you build the third-party [spire-mentor](https://github.com/tfriedel/spire-mentor) yourself, the official package can run `mentor-full` / `mentor-full-ev` (MCTS for fights, PPO for out-of-combat choices; base-game characters only) without rebuilding DeckBench. spire-mentor is not shipped with this project. On the Windows package, set `python` in `mentor.local.json` to the interpreter that built `sts2_rs`. It has a known loading problem with 19 new cards from v0.111 (SIDESTEP etc.), and we provide a small local patch. Smoke steps and packaging rules: [docs/DEVELOPER.md](docs/DEVELOPER.md#可选spire-mentor更强的-ai--optional-spire-mentor).
- [docs/MOD_AUTHORS.md](docs/MOD_AUTHORS.md) ([中文](docs/MOD_AUTHORS.zh-CN.md)): getting started for mod authors. The example is `examples/spark/`. The internal Python engine runs the tiny sample with no game install.
- [docs/MODDING.md](docs/MODDING.md): write your own mod in YAML + Python (cards, powers, relics, decks, experiments).
- [gui/README.md](gui/README.md): how the desktop app is structured and packaged.
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution rules (no game content of any kind).

## License

MIT, for our own code only; see [LICENSE](LICENSE).
