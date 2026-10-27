# DeckBench 0.1.5

这一版对应更新日志里的「未发布（0.1.5）」。功能已经在 `main`：PR #4（合并提交 `a204bb4`）收进导入、种子预览、DLL→YAML 和 mentor-full 打包；#6–#13 补上本文、界面文案、只读摘要、`--json` / `--cache`，以及不引用本机游戏 DLL 的夹具测试。版本号本来就是 `0.1.5`（`sts2sim.__version__`、`gui/web/package.json`、`gui/packaging/build.ps1` 的默认 `-Version`），本文不改版本。

给两类人：已经把 mod 装进游戏、想先看数字的作者；想挑一条适合录像的种子、又不想先让 AI 把整局打完的玩家。

*These notes are the GitHub Release body for what the changelog lists as Unreleased (0.1.5). The features are on `main`: PR #4 (merge `a204bb4`) brought in import, seed preview, DLL→YAML and mentor-full packaging; #6–#13 added these notes, the UI copy, the read-only summary, `--json` / `--cache`, and fixture tests that do not reference a local game DLL. The version is already `0.1.5` (`sts2sim.__version__`, `gui/web/package.json`, the default `-Version` in `gui/packaging/build.ps1`). This file does not bump it.*

*Written for mod authors who already have a mod in the game, and for players picking a seed to record without first letting an AI play the whole run.*

仓库仍不含游戏文件、游戏代码或游戏文本。下面的命令都在仓库根目录运行。

---

## 中文

### 这一版有什么

- **只读导入真游戏的一局。** 打开你指出的 `history/*.run`，或正在打的 `current_run.save` / `current_run_mp.save`。目录、`.backup`、gzip、UTF-16 也认。界面显示种子、进阶、路线、每层选牌、遗物和牌组。不修改存档，不解密。
- **种子预览。** 给一个游戏种子、一个原版角色、进阶 0–10。不打完整的一局，列出每一幕地图、普通怪 / 精英 / 首领队列、开局选项，以及第一场普通战斗的奖励界面（那场战斗本身不打）。第 2 幕及以后标成「未打完上一幕的投影」。
- **DLL → YAML。** 读你已经写好的游戏 mod（清单 JSON + DLL），能反编译时把直线的伤害、格挡、抽牌、能量、治疗、施加能力翻成现有 YAML，再到模组编辑器里改、保存、整局试跑。DLL 不执行，游戏文件不复制进来。
- **官方安装包可以接上 `mentor-full` / `mentor-full-ev`。** 仍然不附带 spire-mentor。整局批量的 AI 列表里就有这两项；没配好时是灰的。不用为了接上它重编 DeckBench。

更细的字段、路径和缺口在 [SAVE_FORMAT.md](SAVE_FORMAT.md)、[DLL_MODS.md](DLL_MODS.md)、[DEVELOPER.md](DEVELOPER.md)。更新日志全文在仓库根目录的 [CHANGELOG.md](../CHANGELOG.md)。

### 试一下

不需要游戏就能看导入长什么样（夹具 ID 是虚构的，不是游戏文件）：

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` 打出 JSON 摘要（种子、角色、进阶、到达层、牌和遗物要点），不打开图形界面。MCP 工具 `import_save(path)` 返回同一份；没有本机游戏数据时用 `python tools/mcp_server.py --import-only`。

换成你自己的存档：`python tools/import_run.py <文件或目录>`。常见位置是 `%APPDATA%\SlayTheSpire2\steam\<steam64>\profile1\saves`（Linux / macOS 见 SAVE_FORMAT.md）。打完留下来的是 `history/*.run`；`current_run.save` 在死亡或通关后会被游戏删掉。

图形界面左侧 **导入对局**。地址 `#/import` 打开这一页；`#/import?path=` 后面直接带文件路径。打开目录时列出批量摘要。本机接口：`POST /api/import`（正文 `{"path":"..."}`）、`POST /api/import/batch-summary`、`POST /api/import/upload`、`GET /api/saves/discover`。

先看种子再决定要不要拿去录像（需要已经跑过 `python -m sts2sim.gamedata setup`，否则说明原因并以退出码 2 停下，不猜地图）：

```bash
python tools/seed_preview.py 7F3K9Q2ZB8MA --char Ironclad --asc 0 --neow first
```

`--char` 只能是原版五个：`Ironclad`、`Silent`、`Defect`、`Necrobinder`、`Regent`。`--neow` 取 `first`（默认，第一个没锁的）、`all`、`none` 或选项序号。`--json out.json`（`--json -` 只打到标准输出）、`--lang en` 可选。`--cache` 按规范化种子、角色、进阶和 `neow` 把同一份 v1 JSON 留在本机（默认 `DECKBENCH_CACHE/seed-preview`），不进仓库、不进安装包。

图形界面 **种子预览**：`#/preview`，或 `#/preview?seed=7F3K9Q2ZB8MA`。接口 `POST /api/seed-preview`，正文 `{"seed","char","asc","neow"}`。没生成本机数据时有单独说明；每一幕标成「进幕」「投影」或「未生成」；开局奖励是三个按钮。导入页会说明读不开的文件。这些文案在四种语言的 `gui/locales/` 里。

`tools/seed_probe.py` 仍是 MCP 画当前地图用的探针，不是这一页的入口。

已经装在游戏里的 mod：

```bash
python tools/import_dll_mod.py --list
python tools/import_dll_mod.py "/path/to/Slay the Spire 2/mods/MyMod" --out mods/my_mod
```

`--no-decompile` 只列类型。`--json` 打印报告。图形界面在 **模组编辑器 → 导入游戏 mod**（zip 里只要那一个 mod 目录，或从游戏 `mods/` 的下拉框选）。保存之前不会写进界面自己的 mod 目录。试跑：`python tools/batch.py --mod mods/my_mod --char MyHero --agent modai --n 20`。

要用 `mentor-full` 筛种子：自己构建 [spire-mentor](https://github.com/tfriedel/spire-mentor)，在 `DeckBench.exe` 旁边（或仓库根目录、数据目录）放 `mentor.local.json`，不要放进发布 zip，也不要发给别人：

```json
{
  "site": "C:\\path\\to\\venv\\Lib\\site-packages",
  "py": "C:\\path\\to\\spire-mentor\\sts2-pycli\\python",
  "python": "C:\\path\\to\\venv\\Scripts\\python.exe"
}
```

`python` 必须是构建 `sts2_rs` 的那个 `python.exe`。环境变量 `DECKBENCH_MENTOR_SITE`、`DECKBENCH_MENTOR_PY`、`DECKBENCH_MENTOR_PYTHON` 会覆盖这份 json，源码和打包版都能用。改完重启。冒烟要看到 `import: ok`：

```bash
python -m sts2sim.engine.mentor_paths
```

然后再打铁甲战士 1 局（源码、Linux/macOS：`python tools/batch.py --char Ironclad --asc 0 --n 1 --procs 1 --agent mentor-full-ev --seed 7F3K9Q2ZB8MA`）。Windows 打包版用界面把局数设成 1，或按 DEVELOPER.md 用 `python -m gui.worker`。

### 用的时候注意

**导入。** 打完的 `.run` 和进行中的 `current_run.save` 不是同一种 JSON。打完的记录没有地图列号，所以路线有层数和房间类型，没有左右位置。认不出的文件会停下来说明；看起来像加密或损坏时不会尝试解密。`progress.save` 是解锁和统计，不是一局。

**种子预览。** 和真游戏对照的前提：全解锁、不是教程局、没有自定义修改器。第 1 幕地图是进幕时生成的，可以拿截图对。第 2 幕及以后是「如果现在进入这一幕」生成的，中间没有把上一幕打完，只有地图随机流不被战斗消耗时才和实机一致。问号节点走进去才掷点，预览不提前掷。遭遇队列是开局排好的抽取顺序，不是地图上从左到右的位置。遗物袋顺序读不到时，只列出开局遗物，不替你选宝箱。

**DLL。** 有分支、循环、选项或自定义命令的方法，效果留空并标明，不会写成「每次都发动」。Harmony、Godot 场景、`.pck` 里的图不进模拟。没有反编译到方法体时，类还在列表里，但是占位，检查不会通过。没有游戏程序集做引用时，枚举数字不会被猜成攻击、稀有度或关键词。只加进铁甲战士等原版卡池的牌，不会自动变成一个新角色。导进来的数字没有和真游戏逐张对过；比强弱之前，先用同一套种子打一小批，核对一场战斗。反编译临时目录用完删除。不要把含有你不打算公开的文本的导入文件夹提交进这个仓库。仓库里的 DLL 夹具是合成的；反编译夹具时不会把本机游戏 DLL 加进引用。导入你自己的 mod 时仍然使用本机安装。

**mentor-full。** 只支持原版 5 个角色。模组角色的局外决策回退学习版，日志会写明。库加载失败时这一次运行会停下来，不再整局静默改用学习版。跑完看战斗回退比例和 PPO 的「网络/回退」次数；回退接近 100% 时不要拿这批胜率做种子筛选。v0.111 的 19 张新牌（SIDESTEP 等）在上游有一个已知的读取问题，本地补丁在 `docs/patches/spire-mentor-v0111-cards.patch`（只改 spire-mentor 自己的代码）。打包脚本会把 `gui/*.py` 复制到 `sim/gui`；`audit.ps1` 拒绝把 `.onnx`、`sts2_rs`、`sts2_hint`、`champions.toml` 打进 zip。

---

## English

### What's in 0.1.5

- **Read-only import of a real run.** Point it at a finished `history/*.run`, or an in-progress `current_run.save` / `current_run_mp.save`. A folder, `.backup`, gzip and UTF-16 are accepted too. You get the seed, ascension, route, per-floor card picks, relics and deck. Saves are not modified and not decrypted.
- **Seed preview.** A game seed, one base-game character, ascension 0–10. Without playing the run: each act's map, the normal / elite / boss queues, the opening choices, and the reward screen of the first normal fight (that fight is not played). Act 2 and later are labeled as projections that skip playing the previous act.
- **DLL → YAML.** Read a game mod you already built (manifest JSON + DLL). When decompilation works, straight-line damage, block, draw, energy, heal and apply-power become the existing YAML, which you then edit, save and run in the mod editor. The DLL is not executed. Game files are not copied in.
- **The official package can run `mentor-full` / `mentor-full-ev`.** It still does not ship spire-mentor. Both agents are in the full-run AI list and stay greyed out until configured. You do not rebuild DeckBench to attach them.

Field-level detail, paths and known gaps: [SAVE_FORMAT.md](SAVE_FORMAT.md), [DLL_MODS.md](DLL_MODS.md), [DEVELOPER.md](DEVELOPER.md). The full changelog is [CHANGELOG.md](../CHANGELOG.md).

### Try it

Import works without the game. The fixture uses fictional IDs, not a game file:

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` prints a JSON summary (seed, character, ascension, floor reached, card and relic highlights) without the GUI. MCP `import_save(path)` returns the same summary; without local game data use `python tools/mcp_server.py --import-only`.

Your own save: `python tools/import_run.py <file or folder>`. On Windows that is often `%APPDATA%\SlayTheSpire2\steam\<steam64>\profile1\saves` (Linux / macOS paths are in SAVE_FORMAT.md). What remains after a finished run is `history/*.run`. The game deletes `current_run.save` on death or victory.

GUI: **Import run** on the left. `#/import` opens the page; `#/import?path=` opens one file directly. A folder also lists the batch summary. Local API: `POST /api/import` with `{"path":"..."}`, `POST /api/import/batch-summary`, `POST /api/import/upload`, `GET /api/saves/discover`.

Preview a seed before you record it. This needs data already generated with `python -m sts2sim.gamedata setup`. With no local game logic the tool explains, exits 2, and does not invent a map:

```bash
python tools/seed_preview.py 7F3K9Q2ZB8MA --char Ironclad --asc 0 --neow first
```

`--char` is one of `Ironclad`, `Silent`, `Defect`, `Necrobinder`, `Regent`. `--neow` is `first` (default: the first unlocked choice), `all`, `none`, or an option index. Optional: `--json out.json` (`--json -` prints only that JSON), `--lang en`. `--cache` stores the same v1 JSON locally, keyed by canonical seed, character, ascension and `neow` (default `DECKBENCH_CACHE/seed-preview`). It is not committed or packaged.

GUI: **Seed preview** at `#/preview`, or `#/preview?seed=7F3K9Q2ZB8MA`. API: `POST /api/seed-preview` with `{"seed","char","asc","neow"}`. Missing local game data gets its own explanation. Each act is marked Act entry, Projected, or Not generated. Opening rewards are three buttons. Import explains a file it cannot read. That copy lives in `gui/locales/` for all four languages.

`tools/seed_probe.py` stays the probe MCP uses to draw the current map. It is not this page's entry point.

A mod already installed in the game:

```bash
python tools/import_dll_mod.py --list
python tools/import_dll_mod.py "/path/to/Slay the Spire 2/mods/MyMod" --out mods/my_mod
```

`--no-decompile` lists types only. `--json` prints the report. In the app: **Mod editor → Import game mod** (a zip of that one mod folder, or the dropdown of the game's `mods/`). Nothing is written into the app's mod folder until you save. Then: `python tools/batch.py --mod mods/my_mod --char MyHero --agent modai --n 20`.

To screen seeds with `mentor-full`, build [spire-mentor](https://github.com/tfriedel/spire-mentor) yourself and add `mentor.local.json` next to `DeckBench.exe` (or at the repo root, or in the data folder). It is gitignored. Do not put it in the release zip, and do not send it to anyone:

```json
{
  "site": "C:\\path\\to\\venv\\Lib\\site-packages",
  "py": "C:\\path\\to\\spire-mentor\\sts2-pycli\\python",
  "python": "C:\\path\\to\\venv\\Scripts\\python.exe"
}
```

`python` must be the `python.exe` that built `sts2_rs`. `DECKBENCH_MENTOR_SITE`, `DECKBENCH_MENTOR_PY` and `DECKBENCH_MENTOR_PYTHON` override this file, from source and from the package. Restart after changing them. Smoke check — you want `import: ok`:

```bash
python -m sts2sim.engine.mentor_paths
```

Then one Ironclad run (source, Linux/macOS: `python tools/batch.py --char Ironclad --asc 0 --n 1 --procs 1 --agent mentor-full-ev --seed 7F3K9Q2ZB8MA`). On the Windows package, set the run count to 1 in the GUI, or use `python -m gui.worker` as in DEVELOPER.md.

### Practical limits

**Import.** A finished `.run` and a live `current_run.save` are different JSON. Finished history has no map column, so the route has floors and room types, not left/right position. A file we cannot read stops with an explanation. If it looks encrypted or corrupt, DeckBench does not try to decrypt it. `progress.save` is unlocks and stats, not a run.

**Seed preview.** Match it to the real game only with full unlocks, not a tutorial run, and no custom modifiers. The act 1 map is what `CreateMap` builds on entering the act; check it against a screenshot. Act 2+ is generated as if you entered that act now, without playing the previous act. It matches the live game only when combat does not consume the map's random stream. Unknown (`?`) nodes are not rolled until you walk into them. Encounter queues are the draw order rolled at the start, not left-to-right positions on the map. If the relic-bag order is not on the engine object, the preview lists starting relics only and does not pick chests for you.

**DLL.** Methods with branches, loops, choices or custom commands keep a blank effect and a note. A conditional effect is not imported as always-on. Harmony, Godot scenes and pictures inside a `.pck` are not simulated. Without a method body the class is listed as a placeholder and Check will not pass. Enum numbers are not guessed into attack, rarity or keywords when the game assembly was not a decompiler reference. Cards registered only into a base character's pool do not become a new character. Imported numbers are not matched card-by-card against the live game; play a small shared-seed batch and check one fight before you compare balance. Decompiler output is deleted. Do not commit an imported folder if it holds text you do not want to publish. The DLL fixture in the repo is synthetic. Decompiling that fixture does not add a local game DLL as a reference. Importing your own mod still uses the local install.

**mentor-full.** Vanilla characters only. On a mod character, out-of-combat decisions fall back to the learned AI and the log says so. If the library fails to import, that run stops instead of silently scoring the learned AI for the whole run. After a run, read the combat fallback rate and the PPO net/fallback counts. Do not screen seeds when fallback is about 100%. Nineteen v0.111 cards (SIDESTEP and the rest) hit a known upstream loader bug; the code-only local patch is `docs/patches/spire-mentor-v0111-cards.patch`. The packager copies `gui/*.py` to `sim/gui`. `audit.ps1` rejects `.onnx`, `sts2_rs`, `sts2_hint` and `champions.toml` in the zip.
