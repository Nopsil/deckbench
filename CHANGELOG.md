# 更新日志 / Changelog

## 未发布（0.1.5） / Unreleased (0.1.5)

这些功能已经在 `main`（PR #4，以及随后的 #6–#13）。版本号是 `0.1.5`（`sts2sim.__version__`、界面 `package.json`、Windows 打包脚本的默认 `-Version`）。发布说明在 `docs/RELEASE_0.1.5.md`。

*These features are on `main` (PR #4, then #6–#13). The version is `0.1.5` (`sts2sim.__version__`, the GUI `package.json`, and the default `-Version` in the Windows packager). Release notes: `docs/RELEASE_0.1.5.md`.*

- **对局目录的批量摘要**：`python tools/import_run.py <目录> --batch-summary` 把 history 里每一局打成稳定 JSON（种子、进阶、角色、层数，有胜负或放弃才写 `result`）。`--lines` 改成每行一局。读不开的文件带上错误码，不中断，也不改存档。见 `docs/SAVE_FORMAT.md`。
  *Folder batch summary: `python tools/import_run.py <folder> --batch-summary` prints stable JSON for each history run (seed, ascension, character, floors, and `result` when the run ended). `--lines` prints one object per line. Unreadable files keep their error code; nothing is written back to the save folder. See `docs/SAVE_FORMAT.md`.*
- **导入页显示目录批量摘要**：打开存档目录或 `history` 目录时，「导入对局」多一张只读表（种子、角色、层数、结果）。`POST /api/import/batch-summary`（正文 `{"path":"..."}`）返回和 `--batch-summary` 相同的 JSON 数组，不改存档。
  *Import run shows a folder batch summary: opening a save folder or a `history` folder adds a read-only table (seed, character, floors, result). `POST /api/import/batch-summary` with `{"path":"..."}` returns the same JSON array as `--batch-summary` and does not modify saves.*
- **种子预览的 JSON 和本机缓存**：`python tools/seed_preview.py --json 文件` 写出稳定的 v1 文档（`--json -` 只打到标准输出）。可选 `--cache [目录]` 按规范化种子、角色、进阶、`neow` 把结果留在本机（默认 `DECKBENCH_CACHE/seed-preview`）。缓存含游戏派生 ID，不进仓库、不进安装包；目录指到仓库里会拒绝。没有引擎时仍然说明原因并退出，不编地图。说明见 `docs/SAVE_FORMAT.md`。
  *Seed preview JSON and a local cache: `python tools/seed_preview.py --json FILE` writes the stable v1 document (`--json -` prints only that JSON). Optional `--cache [DIR]` stores a result locally, keyed by canonical seed, character, ascension and `neow` (default `DECKBENCH_CACHE/seed-preview`). The cache holds game-derived ids and is not committed or packaged; a directory inside the repository is refused. With no engine it still explains and exits instead of inventing a map. See `docs/SAVE_FORMAT.md`.*

- **MCP 也能要种子预览**：对战服务器的 `seed_preview(seed, character, ascension, neow, cache, cache_dir)` 返回和 `tools/seed_preview.py --json -` 相同的稳定 v1 JSON。`neow` 仍是 `first` / `all` / `none` / 序号。资源 `deckbench://seed-preview/v1` 只列字段顺序，不生成地图。`--import-only` 仍然只有 `import_save`。没有引擎或选择器不合法时返回 JSON 错误，不编地图。`import_save` 和 `import_run.py --summary` 仍是同一份摘要（单局或存档目录）。
  *MCP can request a seed preview: `seed_preview` on the play server returns the same stable v1 JSON as `tools/seed_preview.py --json -`. `neow` stays `first` / `all` / `none` / an index. Resource `deckbench://seed-preview/v1` lists the field order and does not generate a map. `--import-only` is still only `import_save`. A missing engine or a bad selector returns a JSON error instead of an invented map. `import_save` is still the same summary as `import_run.py --summary` for one file or a save folder.*

- **官方安装包可以接上 `mentor-full` / `mentor-full-ev`（仍然不附带 spire-mentor）**。整局批量的 AI 列表里就有这两项（原版 5 个角色；模组角色局外决策回退学习版，日志会写明）。没配好时是灰的。Windows 打包版的 `DeckBench.exe` 加载不了你自己编译的 `sts2_rs`，所以要在 exe 旁边放 `mentor.local.json`（或设环境变量），把 `python` 指到**构建 sts2_rs 的那个 python.exe**；界面会用它跑安装包里的 `sim/gui`，不用自己重编 DeckBench。库加载失败会停下，不再整局静默改用学习版；跑完日志里有战斗回退比例和 PPO 网络/回退次数，接近 100% 回退时不要拿来做种子筛选。冒烟：`python -m sts2sim.engine.mentor_paths`（要看到 `import: ok`），然后铁甲战士 1 局。说明见 `docs/DEVELOPER.md`。打包脚本会把 `gui/*.py` 复制到 `sim/gui`；`audit.ps1` 拒绝把 `.onnx`、`sts2_rs`、`sts2_hint`、`champions.toml` 打进 zip。
  *The official package can run `mentor-full` / `mentor-full-ev` without a DeckBench rebuild, and still does not ship spire-mentor. Both agents are in the full-run AI list (vanilla characters; mod characters fall back out of combat and the log says so) and stay greyed out until configured. The packaged exe cannot load your `sts2_rs`; put `mentor.local.json` next to the exe and point `python` at the interpreter that built it. The app then runs `sim/gui` with that Python. If the library fails to import, the run stops instead of silently scoring the learned AI. The log prints combat fallback and PPO net/fallback counts — do not screen seeds when fallback is ~100%. Smoke: `python -m sts2sim.engine.mentor_paths` (`import: ok`), then one Ironclad run. See `docs/DEVELOPER.md`. The packager copies our GUI code to `sim/gui`; `audit.ps1` rejects `.onnx`, `sts2_rs`, `sts2_hint` and `champions.toml` in the zip.*
- **导入已经写好的游戏 mod DLL**：模组编辑器的「导入游戏 mod」，或 `python tools/import_dll_mod.py <游戏的 mods/某个mod>`。读作者自己的清单 JSON 和 DLL，能反编译时把直线的伤害、格挡、抽牌、施加能力翻成现有的 YAML，再在编辑器里改、保存、整局试跑。DLL 不执行，游戏文件不复制进来。认不出的分支和 Harmony 补丁会标明，不会猜成「每次都发动」。说明和限制见 `docs/DLL_MODS.md`。
  *Import a game mod DLL you already built: Mod editor → Import game mod, or `python tools/import_dll_mod.py <the game's mods/ThatMod>`. Reads the author's manifest JSON and DLL and, when decompilation works, turns straight-line damage, block, draw and apply-power into the existing YAML so you can edit, save and run it. The DLL is not executed and game files are not copied in. Branches and Harmony patches are flagged instead of being guessed as always-on. See `docs/DLL_MODS.md`.*
- **导入真游戏的一局**：只读打开你指出的 `history/*.run` 或正在打的 `current_run.save` / `current_run_mp.save`（也认目录、`.backup`、gzip、UTF-16）。显示种子、进阶、路线、每层选牌、遗物和牌组。图形界面「导入对局」，地址 `#/import?path=` 可以直接打开一份存档；命令行 `python tools/import_run.py <文件或目录>`；`POST /api/import`、`POST /api/import/upload`、`GET /api/saves/discover`。不修改存档，不解密。截断的 gzip 记成读不开（`not_json`），不再抛出 `EOFError`。格式和已知缺口（打完的记录没有地图列号、进行中存档和历史记录不是同一种 JSON）写在 `docs/SAVE_FORMAT.md`。夹具 `tests/fixtures/saves/sample_history.run` 用虚构 ID，不是游戏文件。
  *Import a real run: read-only open of a `history/*.run` or an in-progress `current_run.save` / `current_run_mp.save` (also a folder, `.backup`, gzip, UTF-16). Shows seed, ascension, route, per-floor card picks, relics and deck. GUI **Import run** (`#/import?path=` opens one file directly); CLI `python tools/import_run.py`; `POST /api/import`, `POST /api/import/upload`, `GET /api/saves/discover`. Does not modify or decrypt saves. A truncated gzip is reported as unreadable (`not_json`) instead of raising `EOFError`. Format and known gaps (finished history has no map column; live saves and history are different JSON) are in `docs/SAVE_FORMAT.md`. The sample fixture uses fictional IDs, not a game file.*
- **对局摘要给外部代理**：`python tools/import_run.py <文件> --summary` 把种子、角色、进阶、到达层、牌和遗物要点打成 JSON，不打开图形界面。MCP 工具 `import_save(path)` 返回同一份摘要；没有本机游戏数据时用 `python tools/mcp_server.py --import-only`。`--json` 拒绝写进存档目录。见 `docs/SAVE_FORMAT.md`、`docs/MCP.md`。
  *Run summary for an external agent: `python tools/import_run.py <file> --summary` prints seed, character, ascension, floor reached, and card/relic highlights as JSON, without the GUI. MCP `import_save(path)` returns the same summary; without local game data use `python tools/mcp_server.py --import-only`. `--json` refuses to write inside a save folder. See `docs/SAVE_FORMAT.md` and `docs/MCP.md`.*
- **种子预览**：给一个游戏种子（原版角色、进阶），不打完整的一局，显示每一幕地图、普通/精英/首领队列、开局选项，以及第一场普通战斗的奖励。第 2 幕及以后的地图标成「未打完上一幕的投影」。命令行 `python tools/seed_preview.py`（`--neow first|all|none|序号`，默认 `first`）；图形界面「种子预览」（`#/preview?seed=`）；接口是 `POST /api/seed-preview`。没有本机游戏逻辑时说明原因并退出，不猜地图。`tools/seed_probe.py` 仍是 MCP 画当前地图用的探针，没有改成这一页的入口。说明见 `docs/SAVE_FORMAT.md`。
  *Seed preview: given a game seed (base character, ascension), show each act's map, normal/elite/boss queues, opening choices and the first normal-fight rewards without playing the run. Act 2+ maps are marked as projections that skip playing the previous act. CLI `python tools/seed_preview.py` (`--neow first|all|none|<index>`, default `first`); GUI **Seed preview** (`#/preview?seed=`); API `POST /api/seed-preview`. With no local game logic it explains and exits instead of inventing a map. `tools/seed_probe.py` stays the probe MCP uses for the current map; it is not this page's entry point. See `docs/SAVE_FORMAT.md`.*
- **种子预览的 JSON 和本机缓存**：`python tools/seed_preview.py --json 文件` 写出稳定的 v1 文档（`--json -` 只打到标准输出）。可选 `--cache [目录]` 按规范化种子、角色、进阶、`neow` 把结果留在本机（默认 `DECKBENCH_CACHE/seed-preview`）。缓存含游戏派生 ID，不进仓库、不进安装包；目录指到仓库里会拒绝。没有引擎时仍然说明原因并退出，不编地图。说明见 `docs/SAVE_FORMAT.md`。
  *Seed preview JSON and a local cache: `python tools/seed_preview.py --json FILE` writes the stable v1 document (`--json -` prints only that JSON). Optional `--cache [DIR]` stores a result locally, keyed by canonical seed, character, ascension and `neow` (default `DECKBENCH_CACHE/seed-preview`). The cache holds game-derived ids and is not committed or packaged; a directory inside the repository is refused. With no engine it still explains and exits instead of inventing a map. See `docs/SAVE_FORMAT.md`.*
- **种子预览和导入对局的界面**：没生成本机游戏数据时，种子预览用单独的说明，而不是只丢一行错误。每一幕地图标明「进幕」「投影」或「未生成」。开局奖励用三个按钮选范围（第一个没锁的、每一个、不看），并写明各自算什么。导入页对读不开、损坏或不是对局的文件给出原因；目录里坏掉的文件逐个标出来。`#/preview?seed=` 和 `#/import?path=` 仍可直接打开。合并种子预览 JSON 时，四种语言丢掉的润色键（`prev.noEngineTitle`、`imp.emptyTitle` 等）已经补回 `gui/locales/` 的 zhs、en、ja、ko；后来的键（例如 `prev.err.cache_in_repo`）还在。
  *GUI for seed preview and import: missing local game data gets its own explanation. Each act map is marked Act entry, Projected, or Not generated. Opening rewards use three buttons (first unlocked, every choice, skip) with a line saying what each one computes. Import explains unreadable, corrupt, or non-run files, and marks each bad file in a folder. `#/preview?seed=` and `#/import?path=` still open directly. Keys the seed-preview JSON merge dropped from all four languages (`prev.noEngineTitle`, `imp.emptyTitle`, and the rest) are back in `gui/locales/` for zhs, en, ja and ko. Later keys such as `prev.err.cache_in_repo` stay.*
- **DLL 夹具，反编译不碰真游戏 DLL**：`tests/fixtures/dllmod/` 是合成的 C# 和 base64 DLL，不是游戏文件。夹具反编译测试清掉 `DECKBENCH_GAME_DIR`，并把 `gamedata.find_dll` 固定成找不到安装，所以本机有游戏也不会把真 `sts2.dll` 加进 ilspycmd 的引用。导入一份真 mod 时，仍然会用本机安装（找得到的话）。
  *DLL fixtures, and fixture decompile stays off the real game DLL: `tests/fixtures/dllmod/` is synthetic C# plus a base64 DLL, not a game file. The fixture decompile test clears `DECKBENCH_GAME_DIR` and stubs `gamedata.find_dll` so a local install is not passed to ilspycmd as a reference. Importing a real mod still uses the local install when one is present.*
- **发布说明**：`docs/RELEASE_0.1.5.md`（中英，可作 GitHub Release 正文）。四种语言的 README 加了试 0.1.5 功能的命令。`mentor-full` 的环境变量对源码和打包版都生效，写在 `docs/DEVELOPER.md`。
  *Release notes: `docs/RELEASE_0.1.5.md` (Chinese and English, usable as a GitHub Release body). Each README has a short "try 0.1.5" section. The `mentor-full` environment variables apply from source and from the package; see `docs/DEVELOPER.md`.*

## 未发布（0.1.4） / Unreleased (0.1.4)

- **界面多语言**：图形界面支持简体中文、English、日本語、한국어。第一次打开跟着系统语言走（中文 → 简体中文，日语 → 日本語，韩语 → 한국어，其他 → English），左下角随时切换，选择保存在数据目录的 `settings.json`。按钮、提示、报告图表、运行日志、错误信息都会翻译；卡牌、角色、遭遇的名字按所选语言从你自己的游戏安装读（游戏里没有该语言就依次回退英文、中文，最后显示 ID），仍然不随项目分发任何游戏文本。战斗实验的完整 report.md（旧版战斗模拟器生成）暂时只有中文。
  *UI languages: the desktop app now speaks 简体中文, English, 日本語 and 한국어. It starts in your system language and can be switched from the bottom-left menu; the choice is saved in `settings.json` in the data folder. Buttons, hints, report charts, run logs and error messages are translated; card, character and encounter names are read in the same language from your own game install (falling back to English, then Chinese, then the ID), and still no game text is shipped. The legacy combat simulator's full report.md is Chinese only for now.*
- 翻译表在 `gui/locales/<语言>.json`（前后端共用）；`tests/test_i18n.py` 检查每个键四种语言都有、占位符一致、代码里用到的键都存在。`sts2sim/gameloc.py` 支持任意语言代码（`DECKBENCH_GAME_LOC_JPN` / `_KOR` 等覆盖），新增 `languages()`。
  *Translations live in `gui/locales/<lang>.json`, shared by the web UI and the Python backend; `tests/test_i18n.py` checks every key exists in every language with matching placeholders. `gameloc` accepts any language code and gains `languages()`.*
- 说明页（四种语言）去掉了「界面只有中文」的提示，改为说明语言切换，界面按钮名直接用对应语言。
  *READMEs: dropped the "interface is Chinese only" note and now describe the language switch, quoting on-screen labels in each README's own language.*
- **整局也能用 YAML mod，不用写代码**：同一种 YAML 格式（旧 mod 照样能用）现在可以直接跑整局——批量、单卡 A/B、指定种子、各种 AI（推荐通用 AI）。能写角色（生命、能量、起始牌组、初始遗物）、按稀有度的卡池、卡牌（效果用 op 列表或模板）、能力、遗物、模组药水；能力和遗物用「什么时候 → 做什么」的触发器。格式有错时用大白话（中英）一次列出全部问题。命令行 `tools/batch.py --mod <文件夹>`、`tools/ab_card.py --mod …`。说明见 `docs/MODDING.md`。
  *YAML mods in full runs, no code: the same YAML format (old mods still work) now runs full runs: batch, one-card A/B, game seeds, every AI. Characters, card pools by rarity, cards (op lists or templates), powers, relics and mod potions, with when → what triggers for powers and relics. Format errors are listed all at once in plain Chinese/English. CLI: `--mod <folder>` for `tools/batch.py` and `tools/ab_card.py`. See `docs/MODDING.md`.*
- **图形界面「模组编辑器」**：填表做角色、卡牌（效果搭建器，也可以直接写 YAML）、能力、遗物；检查；导入 / 导出 zip；一键整局试跑和单卡 A/B。四种语言。
  *GUI **Mod editor**: forms for character, cards (effect builder or raw YAML), powers and relics; check; import/export zip; one-click full-run test and one-card A/B. All four languages.*
- `mods/claude_yaml/`：Claude娘 v3.5 的 YAML 数据版（`tools/convert_claude_v35.py` 自动转换）。86 张设计牌里 81 张是纯 YAML（69 张自动转换 + 12 张按设计手写，`--variant new_cards`），5 张需要 Python。和手写 Python 版逐张牌对拍 70/70 一致，通用 AI 各 300 局 A0 / A10 每个种子结果完全相同。
  *`mods/claude_yaml/`: Claude娘 v3.5 as data. 81 of 86 design cards in pure YAML (69 converted automatically, 12 written from the design text), 5 need Python. Identical to the Python port card by card (70/70) and seed by seed over 300 `modai` runs at A0 and A10.*
- YAML 角色的卡池太小时（比如某事件一次要 8 张不重复的普通牌），奖励改为允许重复而不是整局报错；原版角色不受影响。
  *For YAML characters with small pools, reward generation allows repeats instead of crashing the run; base characters are unaffected.*

- **打法风格可以切换**：AI 上面可以再叠一层「打法风格」，先有「标准」（不加规则）和「杂耍流」（优先拿杂耍 JUGGLING，偏好多段攻击和反直觉的组合，攻击优先、多冲精英；要学习版 / 通用 AI / 强 AI 这类 AI）。图形界面「新建测试 → 整局批量」多了「打法风格」下拉框（指定种子单局也能用），运行记录、报告和历史里会显示用的风格；命令行 `tools/batch.py --style`、`tools/ab_card.py --style`；MCP `new_run(style=…)` 和新工具 `list_styles`。原来的风格 id 改名为中性的 `juggler`。
  *Switchable play styles: an optional rule layer on top of the AI. Ships with Standard (no rules) and Juggler (always takes Juggling, favors multi-hit attacks and counter-intuitive combos, attacks over block, more elites; needs a learned/general/strong AI). New "Play style" dropdown in New Test → Full runs (also for a single game seed); the style is shown in the run page, report and history. CLI `--style` for `tools/batch.py` and `tools/ab_card.py`; MCP `new_run(style=…)` and `list_styles`. The previous style id was renamed to the neutral `juggler`.*

## 0.1.3 (2026-10)

- **修复：宝箱遗物从来没有真正拿到手。** 真游戏是在界面里发放宝箱遗物的，模拟器没有那个界面，所以以前所有模拟（批量、图形界面）里选了宝箱遗物也不会进遗物栏。现在默认修好（批量、图形界面、MCP 都一样）。**之前版本测出的胜率和层数都是在没有宝箱遗物的情况下测的**，会偏低，和新版本的数字不能直接比较；本说明下面引用的 AI 对比数字也是修复前测的。只为复现旧数字时可设 `DECKBENCH_TREASURE_FIX=0`。
  *Fix: treasure-room relics were never actually obtained. The game grants them through a UI element the simulator lacked, so in every earlier simulation (batch, GUI) the chosen chest relic never reached the relic bar. Now fixed and on by default everywhere (batch, GUI, MCP). **Win rates and floors measured with earlier versions were measured without chest relics** and are not directly comparable; the AI comparison numbers quoted below were also measured before the fix. Set `DECKBENCH_TREASURE_FIX=0` only to reproduce old numbers.*
- MCP：`act` 可以用 `option=` 按选项文字/ID 选（例 `option="JUGGLING"`、`option="跳过"`），比选项号稳定；一局结束时列出全部遗物和牌组。
  *MCP: `act(option=...)` picks by option text or ID; the end-of-run summary lists every relic and the full deck.*
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
