# DeckBench 0.1.5

这一版对应更新日志里的「未发布（0.1.5）」。功能已经在 `main`：PR #4（合并提交 `a204bb4`）收进导入、种子预览、DLL→YAML 和 mentor-full 打包；#6–#26 补上本文、只读摘要、种子预览 JSON、history 批量摘要和安装包清单；#27–#39 补上 Wilson 区间、决策说明、`--workers`、`--mechanic-aware`、校准、mod 作者入门和内部战斗加速。版本号仍是 `0.1.5`（`sts2sim.__version__`、`gui/web/package.json`、`gui/packaging/build.ps1` 的默认 `-Version`），本文不改版本。文档目录在 [INDEX.md](INDEX.md)。

给两类人：已经把 mod 装进游戏、想先看数字的作者；想挑一条适合录像的种子、又不想先让 AI 把整局打完的玩家。

*These notes are the GitHub Release body for what the changelog lists as Unreleased (0.1.5). The features are on `main`: PR #4 (merge `a204bb4`) brought in import, seed preview, DLL→YAML and mentor-full packaging; #6–#26 added these notes, the read-only summary, seed-preview JSON, the history batch summary and the package manifest; #27–#39 added the Wilson interval, decision explanations, `--workers`, `--mechanic-aware`, calibration, the mod-author guide and a faster internal fight engine. The version is still `0.1.5` (`sts2sim.__version__`, `gui/web/package.json`, the default `-Version` in `gui/packaging/build.ps1`). This file does not bump it. Documentation index: [INDEX.md](INDEX.md).*

*Written for mod authors who already have a mod in the game, and for players picking a seed to record without first letting an AI play the whole run.*

仓库仍不含游戏文件、游戏代码或游戏文本。下面的命令都在仓库根目录运行。

---

## 中文

### 这一版有什么

- **只读导入真游戏的一局。** 打开你指出的 `history/*.run`，或正在打的 `current_run.save` / `current_run_mp.save`。目录、`.backup`、gzip、UTF-16 也认。界面显示种子、进阶、路线、每层选牌、遗物和牌组。不修改存档，不解密。
- **种子预览。** 给一个游戏种子、一个原版角色、进阶 0–10。不打完整的一局，列出每一幕地图、普通怪 / 精英 / 首领队列、开局选项，以及第一场普通战斗的奖励界面（那场战斗本身不打）。第 2 幕及以后标成「未打完上一幕的投影」。
- **DLL → YAML。** 读你已经写好的游戏 mod（清单 JSON + DLL），能反编译时把直线的伤害、格挡、抽牌、能量、治疗、施加能力翻成现有 YAML，再到模组编辑器里改、保存、整局试跑。DLL 不执行，游戏文件不复制进来。
- **官方安装包可以接上 `mentor-full` / `mentor-full-ev`。** 仍然不附带 spire-mentor。整局批量的 AI 列表里就有这两项；没配好时是灰的。不用为了接上它重编 DeckBench。

更细的字段、路径和缺口在 [SAVE_FORMAT.md](SAVE_FORMAT.md)、[DLL_MODS.md](DLL_MODS.md)、[MCP.md](MCP.md)、[MOD_AUTHORS.md](MOD_AUTHORS.md)（[简体中文](MOD_AUTHORS.zh-CN.md)）、[PERFORMANCE.md](PERFORMANCE.md)、[DEVELOPER.md](DEVELOPER.md)。全部文档的目录是 [INDEX.md](INDEX.md)。更新日志全文在仓库根目录的 [CHANGELOG.md](../CHANGELOG.md)。

### 试一下

不需要游戏就能看导入长什么样（夹具 ID 是虚构的，不是游戏文件）：

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` 打出 JSON 摘要（种子、角色、进阶、到达层、牌和遗物要点），不打开图形界面。MCP 工具 `import_save(path)` 返回同一份。`import_history_batch(path, lines=false)` 返回和命令行 `--batch-summary` 相同的 JSON（`lines` 为 true 时和 `--lines` 一样，每局一行）：只读，跳过 `current_run.save`，读不开的文件保留 `SaveImportError` 的 code，路径不存在或目录是空的返回 `ok: false`。没有本机游戏数据时用 `python tools/mcp_server.py --import-only`。它提供 `import_save`、`import_history_batch`，以及只读的 `batch_run_summary`、`card_ab`、`explain_fight`、`calibrate`。没有对战工具，也没有 `seed_preview`。说明见 [MCP.md](MCP.md)。

换成你自己的存档：`python tools/import_run.py <文件或目录>`。常见位置是 `%APPDATA%\SlayTheSpire2\steam\<steam64>\profile1\saves`（Linux / macOS 见 SAVE_FORMAT.md）。打完留下来的是 `history/*.run`；`current_run.save` 在死亡或通关后会被游戏删掉。

图形界面左侧 **导入对局**。地址 `#/import` 打开这一页；`#/import?path=` 后面直接带文件路径。本机接口：`POST /api/import`（正文 `{"path":"..."}`）、`POST /api/import/upload`、`GET /api/saves/discover`。

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

### #27–#39

版本号仍是 0.1.5。下面这些已经在 `main`。

- **胜率带 Wilson 区间，对比带 p 值。** 胜率给出 Wilson 95% 置信区间（z=1.96）。两组胜率的对比给出合并比例的双侧两比例 z 检验；原来的配对差和 95% 区间还在。任一组有效局数少于 30，文本、Markdown 和 JSON 写「样本不足，不能下结论」，数字仍给出。命令行：`tools/batch.py` 的文本行，`tools/ab_card.py --format text|markdown|json`，`tools/ab_table.py --format markdown|text|json`，`tools/ai_summary.py`（`--json` 打 JSON；两个及以上文件时相对第一个文件给 p 值）。图形界面的报告页和 A/B 页显示区间、p 值和样本不足警告。`GET /api/runs/{id}/summary` 和 `GET /api/ab` 只追加字段（含 `win_ci_low` / `win_ci_high` / `p_value` / `sample_warning`）。
- **可选的决策说明。** 默认关。打开后，出牌、选目标、喝药水、选奖励和商店会把当时已经算好的前几名候选追加到 JSONL。关着时不组装候选、不抽随机数。整局：`python tools/batch.py --explain`（或 `DECKBENCH_EXPLAIN=1`），文件是 `--out` 旁边的 `*.explain.jsonl`。旧版战斗实验：`python -m sts2sim <实验.yaml> --explain`，或实验 YAML 的 `explain: true`，文件是报告目录里的 `explain.jsonl`。读一场：`python tools/explain_fight.py <日志> --fight 0`。图形界面侧栏「决策说明」（`#/explain`）按种子和战斗分页，分差在 0.5 以内标成「分差很小」。阅读走 MCP 同一个 `explain_fight`，不写文件。
- **MCP 只读分析。** `batch_run_summary(path)`、`card_ab(a, b)`、`explain_fight(...)`、`calibrate(real, sim)`。不新开模拟，不写文件。模拟结果的路径必须在界面数据目录、DeckBench 缓存、`DECKBENCH_MCP_RUNS` 或 `DECKBENCH_ANALYSIS_ROOTS` 里。`calibrate` 的 `real` 是要读的 `.run` / `.save`，读法和 `import_save` 相同。见 [MCP.md](MCP.md)。
- **`--workers`。** `tools/batch.py` 和 `tools/ab_card.py` 上等同 `--procs`（两个都给时以 `--workers` 为准）。`python -m sts2sim` 上等同 `--jobs`。进程数不改变一场战斗的随机数。
- **`--mechanic-aware` 默认关。** 构造参数 `mechanic_aware=True`、实验 YAML 的 `agent_kw: {mechanic_aware: true}`，或 `--mechanic-aware`（`--no-mechanic-aware` 仍表示关）。打开后，启发式和束搜索计入荆棘、受击加格挡和多只敌人的总伤害。`--explain` 的候选 `note` 写 `thorns:`、`armour`、`incoming:`。关着时固定种子与原来相同。
- **mod 作者入门。** [MOD_AUTHORS.md](MOD_AUTHORS.md) 和 [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md) 用原创示例 `examples/spark`（Arc 和 Lantern）走安装、`STS2SIM_USER_MODS`、小样本胜率、单卡 A/B、`--explain` 和可选的 `--mechanic-aware`。需要本机游戏的命令在指南里标成 `needs-game`。仓库里没有游戏文件。
- **校准：真对局对照同一条选牌路径上的模拟掉血。** `python tools/calibrate.py <对局> <runs.jsonl>` 只保留种子、角色、进阶和选牌序列都相同的模拟局。每一场给出真机失去的生命、模拟的 mean / p10 / p90，以及真值的百分位；真值在 p5–p95 之外标成疑似模拟缺口。层数、房间或遭遇对不上，或真机没有这场的遭遇 ID / 掉血，记 `unmatched`，不改用别的层。`POST /api/calibrate` 和只读 MCP `calibrate` 返回同一份 JSON。侧栏「校准」（`#/calibrate`）选一份导入的真对局，再选允许目录里的 `runs.jsonl`，或上传一份（`POST /api/calibrate/upload`，只在内存里读）。每场一条小条：粗段是 p10–p90，细线是 p5–p95，竖线是真值。对不上的层是灰色，并写明原因。不新开模拟，不改存档。
- **内部战斗再加速，固定种子逐字段不变。** `python tools/bench.py` 报告场/秒和分阶段耗时，不需要游戏安装。同一台机器、同一套固定种子，对照已含校准报告的 `main`：启发式 54 场约 93.2 → 106.9 场/秒，启发式加窄束搜索 36 场约 52.3 → 58.9 场/秒，训练木桩 12 场约 104.9 → 118.6 场/秒。样本和改了什么见 [PERFORMANCE.md](PERFORMANCE.md)。更早一次字段拷贝的数字（Claude 模组样本，约 62.5 → 92.7 场/秒）仍写在仓库根的 README「性能」一节，那是另一套样本。
- **导入页的目录摘要。** 打开存档目录或 `history` 时，「导入对局」用已有的 `POST /api/import/batch` 列出每个文件：ok、skipped（进行中的 `current_run.save` / `current_run_mp.save`）、error（带 `SaveImportError` 的原因）。合计是这三种状态的数量，以及胜、负、放弃、未记胜负的局数。单个 `.run` / `.save` 和上传文件仍只显示这一局。不改存档。
- **几处边界。** 过量伤害把生命停在 0。中毒按实际失去的生命计入。存档里的 `NaN` / `Infinity` 当成这个字段没有。Windows 上 `Sample.run` 与 `sample.run.backup` 视为同一局，发现存档时也认 `Current_Run.save`。报告能读 UTF-8 BOM 和 UTF-16。`import_run` / `seed_preview` 的标准输出按 UTF-8 写。其余条目在 [CHANGELOG.md](../CHANGELOG.md)。

不需要游戏就能看校准长什么样（夹具 ID 是虚构的）：

```bash
python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl
python tools/bench.py
```

`examples/spark` 的小样本命令写在 [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md)，由 `tests/test_mod_authors.py` 在内部 Python 引擎上跑完。

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

Field-level detail, paths and known gaps: [SAVE_FORMAT.md](SAVE_FORMAT.md), [DLL_MODS.md](DLL_MODS.md), [MCP.md](MCP.md), [MOD_AUTHORS.md](MOD_AUTHORS.md) ([简体中文](MOD_AUTHORS.zh-CN.md)), [PERFORMANCE.md](PERFORMANCE.md), [DEVELOPER.md](DEVELOPER.md). The index of every doc is [INDEX.md](INDEX.md). The full changelog is [CHANGELOG.md](../CHANGELOG.md).

### Try it

Import works without the game. The fixture uses fictional IDs, not a game file:

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` prints a JSON summary (seed, character, ascension, floor reached, card and relic highlights) without the GUI. MCP `import_save(path)` returns the same summary. `import_history_batch(path, lines=false)` returns the same JSON as the CLI `--batch-summary` (`lines` true matches `--lines`, one object per line): read-only, skips `current_run.save`, keeps `SaveImportError` codes on unreadable files, and returns `ok: false` JSON when the path is missing or the folder is empty. Without local game data, `python tools/mcp_server.py --import-only` exposes `import_save`, `import_history_batch`, and the read-only tools `batch_run_summary`, `card_ab`, `explain_fight` and `calibrate`. It still has no play tools and no `seed_preview`. See [MCP.md](MCP.md).

Your own save: `python tools/import_run.py <file or folder>`. On Windows that is often `%APPDATA%\SlayTheSpire2\steam\<steam64>\profile1\saves` (Linux / macOS paths are in SAVE_FORMAT.md). What remains after a finished run is `history/*.run`. The game deletes `current_run.save` on death or victory.

GUI: **Import run** on the left. `#/import` opens the page; `#/import?path=` opens one file directly. Local API: `POST /api/import` with `{"path":"..."}`, `POST /api/import/upload`, `GET /api/saves/discover`.

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

### #27–#39

The version is still 0.1.5. These are on `main`.

- **Win rates carry a Wilson interval, and a comparison carries a p-value.** The interval is a Wilson 95% confidence interval (z=1.96). A win-rate comparison adds a pooled two-sided two-proportion z-test. The existing paired difference and 95% interval stay. If either group has fewer than 30 valid runs, text, Markdown and JSON say the sample is too small to conclude; the numbers are still reported. CLI: the `tools/batch.py` text line, `tools/ab_card.py --format text|markdown|json`, `tools/ab_table.py --format markdown|text|json`, and `tools/ai_summary.py` (`--json` for JSON; two or more files get a p-value against the first). The report page and the A/B page show the interval, the p-value and the small-sample warning. `GET /api/runs/{id}/summary` and `GET /api/ab` only add fields (including `win_ci_low` / `win_ci_high` / `p_value` / `sample_warning`).
- **Optional decision explanations.** Off by default. When on, each card play, target choice, potion use, and reward or shop pick appends the candidates already scored to a JSONL file. While off it does not build candidate lists or draw random numbers. Full runs: `python tools/batch.py --explain` (or `DECKBENCH_EXPLAIN=1`) writes `*.explain.jsonl` beside `--out`. Legacy fight experiments: `python -m sts2sim <experiment.yaml> --explain`, or `explain: true` in the experiment YAML, writes `explain.jsonl` in the report directory. Read one fight: `python tools/explain_fight.py <log> --fight 0`. **Decisions** in the sidebar (`#/explain`) pages one seed and one fight. A gap of 0.5 or less is marked as a close call. Reading goes through the same `explain_fight` the MCP tool uses, and the page does not write.
- **Read-only MCP analysis.** `batch_run_summary(path)`, `card_ab(a, b)`, `explain_fight(...)` and `calibrate(real, sim)`. They do not start a simulation and do not write. A simulated-result path has to sit in the GUI data directory, the DeckBench cache, `DECKBENCH_MCP_RUNS` or `DECKBENCH_ANALYSIS_ROOTS`. `calibrate`'s `real` argument is the `.run` / `.save` to read, the same way `import_save` reads it. See [MCP.md](MCP.md).
- **`--workers`.** On `tools/batch.py` and `tools/ab_card.py` it is the same as `--procs` (`--workers` wins if both are set). On `python -m sts2sim` it is the same as `--jobs`. The process count does not change a fight's RNG.
- **`--mechanic-aware` is off by default.** Turn it on with `mechanic_aware=True`, `agent_kw: {mechanic_aware: true}` in the experiment YAML, or `--mechanic-aware` (`--no-mechanic-aware` still means off). When on, heuristic and beam count thorns, block gained when hit, and the sum of incoming damage. `--explain` candidate notes read `thorns:`, `armour` and `incoming:`. While off, a fixed seed matches the previous result.
- **Mod-author getting started.** [MOD_AUTHORS.md](MOD_AUTHORS.md) and [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md) walk through the original `examples/spark` mod (Arc and Lantern): install, `STS2SIM_USER_MODS`, a tiny win-rate sample, a card A/B, `--explain`, and optional `--mechanic-aware`. Commands that need a local game are tagged `needs-game` in the guide. The repository contains no game files.
- **Calibration: real HP lost against simulations on the same card-pick path.** `python tools/calibrate.py <run> <runs.jsonl>` keeps simulated runs with the same seed, character, ascension and card-pick sequence. Each fight reports real HP lost, the simulated mean / p10 / p90, and the percentile of the real value. A real value outside p5–p95 is flagged as a likely sim-model gap. A floor whose number, room or encounter does not line up, or that has no encounter id or no recorded HP lost, is `unmatched` and is not filled from another floor. `POST /api/calibrate` and the read-only MCP tool `calibrate` return the same JSON. **Calibration** (`#/calibrate`) takes an imported real run and a `runs.jsonl` from an allowed folder, or an uploaded file (`POST /api/calibrate/upload`, read in memory). A strip on each fight draws p10–p90 as the band, p5–p95 as a thin line, and the real value as a mark. Unmatched floors are grey, with the reason. It does not start a simulation and does not modify saves.
- **Another speedup of the internal fight engine, with field-identical fixed-seed results.** `python tools/bench.py` reports fights/sec and per-phase time, with no game install. On the same machine and the same fixed seeds, against `main` that already includes the calibration report: heuristic 54 fights about 93.2 → 106.9 fights/s, heuristic plus a narrow beam 36 fights about 52.3 → 58.9 fights/s, training dummy 12 fights about 104.9 → 118.6 fights/s. The sample and the changes are in [PERFORMANCE.md](PERFORMANCE.md). An earlier field-copy measurement (a Claude-mod sample, about 62.5 → 92.7 fights/s) stays in the README performance section. That is a different sample.
- **The import page lists a folder.** Opening a save folder or `history` uses the existing `POST /api/import/batch`. Each file is ok, skipped (an in-progress `current_run.save` / `current_run_mp.save`), or error with the `SaveImportError` reason. Totals count those statuses, plus won, lost, abandoned and runs with no recorded result. A single `.run` / `.save` and an uploaded file stay on the single-run view. Saves are not modified.
- **A few edges.** Overkill stops at 0 HP. Poison counts the HP actually lost. `NaN` / `Infinity` in a save is a missing field. On Windows, `Sample.run` and `sample.run.backup` are the same run, and discovery sees `Current_Run.save`. Reports read a UTF-8 BOM and UTF-16. `import_run` / `seed_preview` write stdout as UTF-8. The rest is in [CHANGELOG.md](../CHANGELOG.md).

Calibration can be looked at without the game. The fixture uses fictional IDs:

```bash
python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl
python tools/bench.py
```

The `examples/spark` commands are in [MOD_AUTHORS.md](MOD_AUTHORS.md). `tests/test_mod_authors.py` runs them on the internal Python engine.

### Practical limits

**Import.** A finished `.run` and a live `current_run.save` are different JSON. Finished history has no map column, so the route has floors and room types, not left/right position. A file we cannot read stops with an explanation. If it looks encrypted or corrupt, DeckBench does not try to decrypt it. `progress.save` is unlocks and stats, not a run.

**Seed preview.** Match it to the real game only with full unlocks, not a tutorial run, and no custom modifiers. The act 1 map is what `CreateMap` builds on entering the act; check it against a screenshot. Act 2+ is generated as if you entered that act now, without playing the previous act. It matches the live game only when combat does not consume the map's random stream. Unknown (`?`) nodes are not rolled until you walk into them. Encounter queues are the draw order rolled at the start, not left-to-right positions on the map. If the relic-bag order is not on the engine object, the preview lists starting relics only and does not pick chests for you.

**DLL.** Methods with branches, loops, choices or custom commands keep a blank effect and a note. A conditional effect is not imported as always-on. Harmony, Godot scenes and pictures inside a `.pck` are not simulated. Without a method body the class is listed as a placeholder and Check will not pass. Enum numbers are not guessed into attack, rarity or keywords when the game assembly was not a decompiler reference. Cards registered only into a base character's pool do not become a new character. Imported numbers are not matched card-by-card against the live game; play a small shared-seed batch and check one fight before you compare balance. Decompiler output is deleted. Do not commit an imported folder if it holds text you do not want to publish. The DLL fixture in the repo is synthetic. Decompiling that fixture does not add a local game DLL as a reference. Importing your own mod still uses the local install.

**mentor-full.** Vanilla characters only. On a mod character, out-of-combat decisions fall back to the learned AI and the log says so. If the library fails to import, that run stops instead of silently scoring the learned AI for the whole run. After a run, read the combat fallback rate and the PPO net/fallback counts. Do not screen seeds when fallback is about 100%. Nineteen v0.111 cards (SIDESTEP and the rest) hit a known upstream loader bug; the code-only local patch is `docs/patches/spire-mentor-v0111-cards.patch`. The packager copies `gui/*.py` to `sim/gui`. `audit.ps1` rejects `.onnx`, `sts2_rs`, `sts2_hint` and `champions.toml` in the zip.
