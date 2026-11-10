# DeckBench 0.1.5

这一版对应更新日志里的「未发布（0.1.5）」。功能已经在 `main`：PR #4（合并提交 `a204bb4`）收进导入、种子预览、DLL→YAML 和 mentor-full 打包；#6–#26 补上本文、只读摘要、种子预览 JSON、history 批量摘要和安装包清单；#27–#39 补上 Wilson 区间、决策说明、`--workers`、`--mechanic-aware`、校准、mod 作者入门和内部战斗加速；#40 把更新日志对齐到 #39。其后按 `git log` 的合并顺序是 #41、#43、#42、#44、#45、#46、#47、#48、#49、#50、#51、#52：覆盖率、持续集成、坏输入、Windows 种子预览缓存、界面语言、Windows 安装包工作流、简体中文文档、打包脚本修复、缺口分诊、打包后的接口冒烟，以及 `charset=utf-8`。#53 把发布说明对齐到 #52。其后是 #54、#55、#56、#57、#58：界面浏览器冒烟、两次战斗对比、离线 HTML、组牌，以及遭遇选择和回合上限。#59 在浏览器冒烟结束时放开 Playwright 的事件循环。其后按合并顺序是 #60、#61、#62、#63、#64：两份牌组对打、测试进度和取消、单卡贡献、Windows 包使用已有版本号并可以手动检查更新、战斗批量的 workers。#65 是本版更新，#66 是侧栏的简体中文 / English 切换，#67 是可分享的 `.deckbench.zip` 结果包。这一分支在空的历史页加上「载入示例数据」（两场训练木桩和一份牌组预设，由现有战斗工人生成）。版本号仍是 `0.1.5`，只写在 `sts2sim.__version__`。`gui/web/package.json` 必须和它相同。Windows 打包从这里读取，不另起一个版本号。本文不改版本。文档目录在 [INDEX.md](INDEX.md)。

给两类人：已经把 mod 装进游戏、想先看数字的作者；想挑一条适合录像的种子、又不想先让 AI 把整局打完的玩家。

*These notes are the GitHub Release body for what the changelog lists as Unreleased (0.1.5). The features are on `main`: PR #4 (merge `a204bb4`) brought in import, seed preview, DLL→YAML and mentor-full packaging; #6–#26 added these notes, the read-only summary, seed-preview JSON, the history batch summary and the package manifest; #27–#39 added the Wilson interval, decision explanations, `--workers`, `--mechanic-aware`, calibration, the mod-author guide and a faster internal fight engine. #40 aligned the changelog through #39. After that, in `git log` merge order, #41, #43, #42, #44, #45, #46, #47, #48, #49, #50, #51 and #52 added coverage, CI, clear errors for bad input, the Windows seed-preview cache, the UI language, the Windows package workflow, 简体中文 docs, the packaging-script fixes, gap triage, the packaged API smoke, and `charset=utf-8`. #53 aligned these notes through #52. After that, #54, #55, #56, #57 and #58 added the GUI browser smoke, a comparison of two combat tests, offline HTML, the deck builder, and encounter choice with a turn cap. #59 releases the Playwright event loop when that browser module finishes. After that, in merge order, #60, #61, #62, #63 and #64 added a head-to-head for two saved decks, live progress and cancel, leave-one-out card impact, the Windows package stamping the existing version with a manual update check, and optional fight workers. #65 is What's new, #66 is the 简体中文 / English switch, and #67 is the shareable `.deckbench.zip` run bundle. This branch adds **Load demo data** on an empty History page (two training-dummy fights and one saved deck, produced by the existing combat worker). The version is still `0.1.5`, written only in `sts2sim.__version__`. `gui/web/package.json` must match it. The Windows packager reads that assignment and does not invent another number. This file does not bump it. Documentation index: [INDEX.md](INDEX.md).*

*Written for mod authors who already have a mod in the game, and for players picking a seed to record without first letting an AI play the whole run.*

仓库仍不含游戏文件、游戏代码或游戏文本。下面的命令都在仓库根目录运行。

---

## 中文

### 这一版有什么

- **只读导入真游戏的一局。** 打开你指出的 `history/*.run`，或正在打的 `current_run.save` / `current_run_mp.save`。目录、`.backup`、gzip、UTF-16 也认。界面显示种子、进阶、路线、每层选牌、遗物和牌组。不修改存档，不解密。
- **种子预览。** 给一个游戏种子、一个原版角色、进阶 0–10。不打完整的一局，列出每一幕地图、普通怪 / 精英 / 首领队列、开局选项，以及第一场普通战斗的奖励界面（那场战斗本身不打）。第 2 幕及以后标成「未打完上一幕的投影」。
- **DLL → YAML。** 读你已经写好的游戏 mod（清单 JSON + DLL），能反编译时把直线的伤害、格挡、抽牌、能量、治疗、施加能力翻成现有 YAML，再到模组编辑器里改、保存、整局试跑。DLL 不执行，游戏文件不复制进来。
- **官方安装包可以接上 `mentor-full` / `mentor-full-ev`。** 仍然不附带 spire-mentor。整局批量的 AI 列表里就有这两项；没配好时是灰的。不用为了接上它重编 DeckBench。

更细的字段、路径和缺口在 [SAVE_FORMAT.md](SAVE_FORMAT.md)、[DLL_MODS.md](DLL_MODS.md)、[MCP.md](MCP.md)、[MOD_AUTHORS.md](MOD_AUTHORS.md)（[简体中文](MOD_AUTHORS.zh-CN.md)）、[CALIBRATION.md](CALIBRATION.md)、[COMPARE.md](COMPARE.md)、[DECKS.md](DECKS.md)、[EXPORT.md](EXPORT.md)、[PERFORMANCE.md](PERFORMANCE.md)、[COVERAGE.md](COVERAGE.md)、[CI.md](CI.md)、[DEVELOPER.md](DEVELOPER.md)。Windows 安装包的说明在 [gui/packaging/README-win.txt](../gui/packaging/README-win.txt)（打进 zip 叫 `README.txt`）。全部文档的目录是 [INDEX.md](INDEX.md)。更新日志全文在仓库根目录的 [CHANGELOG.md](../CHANGELOG.md)。

### 试一下

不需要游戏就能看导入长什么样（夹具 ID 是虚构的，不是游戏文件）：

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` 打出 JSON 摘要（种子、角色、进阶、到达层、牌和遗物要点），不打开图形界面。MCP 工具 `import_save(path)` 返回同一份。`import_history_batch(path, lines=false)` 返回和命令行 `--batch-summary` 相同的 JSON（`lines` 为 true 时和 `--lines` 一样，每局一行）：只读，跳过 `current_run.save`，读不开的文件保留 `SaveImportError` 的 code，路径不存在或目录是空的返回 `ok: false`。没有本机游戏数据时用 `python tools/mcp_server.py --import-only`。它提供 `import_save`、`import_history_batch`，以及 `batch_run_summary`、`card_ab`、`compare_runs`、`explain_fight`、`calibrate`、`gap_triage`、`export_report`、`list_cards`、`list_encounters`、`save_deck`。没有对战工具，也没有 `seed_preview`。说明见 [MCP.md](MCP.md)。

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

### #41–#52

版本号仍是 0.1.5。`git log` 上的合并顺序是 #41、#43、#42、#44、#45、#46、#47、#48、#49、#50、#51、#52。

- **覆盖率。** 补了卡牌结算、能力 / 遗物钩子、存档解析、校准匹配和 HTTP 错误路径的测试。快照和五处边界写在 [COVERAGE.md](COVERAGE.md)：X 费牌被重放时仍用这次付出的能量；对没有活着的目标施加能力并 `save` 时记下 0；`{category, entry}` 拼成 `CATEGORY.ENTRY`（只有 entry 时仍用 entry）；摘要遇到路线里的非对象不再抛错；缺了运行目录时报告接口返回 404，模组 zip 里列出的文件缺失时返回说明而不是 `TypeError`。普通打出、固定种子和 AI 的选择不变。
- **持续集成。** GitHub Actions 在 Ubuntu 和 Windows 上用 Python 3.11 与 3.12 跑完整的 pytest（安装 fastapi、httpx 和 python-multipart，图形界面测试会执行），把 pytest-cov 写进作业摘要，并用 ruff 检查。需要本机游戏安装的测试仍然跳过。见 [CI.md](CI.md)。
- **坏输入是说得清的错误。** `POST /api/import/batch`、`POST /api/calibrate`、`POST /api/calibrate/upload` 以及只读 MCP 工具：目录外的路径、符号链接跳出去、超过 32MB 的上传、坏掉的 JSONL 行、缺字段、类型不对，都是 4xx 或 `{"ok": false, "error": ...}`，正文里没有堆栈。不改模拟、种子和 AI。
- **Windows 上的种子预览缓存。** 读和写都允许共享删除，`os.replace` 遇到拒绝访问会短暂停一下再试。读者仍只看到完整的旧文件或完整的新文件。mod 作者指南的 bash 示例在 Windows 上改用 Git Bash；没装就跳过。`python -m sts2sim --workers` 的工作进程不会再次进入入口。
- **界面语言默认跟浏览器。** 侧栏的简体中文 / English（日本語、한국어仍在同一菜单）记在这个浏览器的 `localStorage`，优先于数据目录的 `settings.json`。没有记住的选择时用 `navigator.language`。决策说明和校准用同一套文案。卡牌和遭遇的 ID 原样显示。
- **Windows 安装包可以在 Actions 里打出来并核对，不发布。** `.github/workflows/windows-package.yml` 在手动运行或推送 `v*` 标签时，于 `windows-latest` 走现有的 `build.ps1`（`-Version 0.1.5`）。打完对目录跑 `dry_check.py --app`，对 zip 跑 `audit.ps1`（运行器没有游戏，不做安装目录哈希对照）。再用 zip 里的 `sim/` 跑 `python -m sts2sim --help`，以及一场不需要游戏的木桩（`claude_v34` 的 `probe_noengine`，`encounter: DUMMY`）。zip 只作为 Actions artifact 上传，不创建 GitHub Release。步骤在 [DEVELOPER.md](DEVELOPER.md#windows-打包版--building-the-windows-package)，工作流说明在 [CI.md](CI.md)。打进包里的说明是 [gui/packaging/README-win.txt](../gui/packaging/README-win.txt)。
- **简体中文文档。** 校准、持续集成、覆盖率快照、性能样本和合成 DLL 夹具是中英对照，并收进 [INDEX.md](INDEX.md)。mod 作者入门仍是英文 [MOD_AUTHORS.md](MOD_AUTHORS.md) 加简体中文 [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md)。
- **打包脚本能在 Windows PowerShell 5.1 里跑。** `gui/packaging` 里带中文的 `build.ps1`、`audit.ps1`、`win_api_test.ps1` 是带 BOM 的 UTF-8。没有 BOM 时，多字节字符会吞掉引号，`build.ps1` 报 “The string is missing the terminator”。纯 ASCII 的 `.ps1` 可以不带 BOM。反编译器工程 `ilspycmd-host.csproj` 的 XML 注释不再含有 `--`（原先的 `--version` / `--self-contained` 让 MSBuild 报 MSB4025）。`dry_check.py` 会拒绝这两种问题。
- **缺口分诊。** `python tools/gap_triage.py` 读一份或多份 `tools/calibrate.py --json` 的结果，按遭遇和敌人能力 / 机制汇总 `likely_sim_gap`。真机掉血高于 p95 是模拟偏乐观，低于 p5 是偏悲观。Markdown 指向 `sts2sim/powers_enemy.py`、`sts2sim/powers.py`、`sts2sim/enemies.py`，荆棘再指向可选的 `mechanic_adjust`。`POST /api/gap_triage` 和只读 MCP `gap_triage`（`--import-only` 也有）返回同一份汇总。侧栏「校准」（`#/calibrate`）在对照表下面列出这两侧和建议查看的源文件。不改模拟、种子和 AI。见 [CALIBRATION.md](CALIBRATION.md)。
- **打包后的 HTTP 冒烟，以及 UTF-8。** 命令行冒烟之后，`gui/packaging/smoke_api.ps1` 解压刚打好的 zip，启动包里的 `DeckBench.exe --serve`（不开窗口），等到 `GET /api/health`，再经 `POST /api/runs` 打一场木桩，然后关掉进程。冒烟日志作为 artifact 上传。`--serve` 不再因为还没有本机游戏数据而退出；要游戏的接口仍返回原来的说明。双击打开窗口仍会先检查游戏。JSON 以及 text/html 等文本响应带 `charset=utf-8`。冒烟自己按 UTF-8 读响应字节，并核对训练木桩的 `enc_name` 仍是「木桩」，summary 里的卡组名也是中文。见 [CI.md](CI.md)。

不需要游戏就能看一份缺口分诊（夹具里的遭遇 ID 是虚构的）：

```bash
python tools/gap_triage.py tests/fixtures/gap_triage --catalog tests/fixtures/gap_triage/catalog.json
```

### #54–#58

版本号仍是 0.1.5。`git log` 上的合并顺序是 #54、#55、#56、#57、#58。

- **界面在 Ubuntu 的持续集成里用无头浏览器冒烟。** 单独的作业（不进现有的 pytest 矩阵）用 pytest-playwright 的 Chromium 打开从源码起的 `python -m gui.app --serve`。没有本机游戏数据：测试写一份空的卡牌缓存，战斗实验用和安装包冒烟相同的训练木桩（`claude_v34` 的 `probe_noengine`，`encounter: DUMMY`，1 回合）。检查主页面（含 `#/calibrate` 和「决策说明」）没有控制台错误，简体中文 / English 切换会改可见文案并写进 `localStorage` 的 `ui.lang`，这场木桩能从界面点到完成，以及用校准夹具渲染缺口分诊。同一份冒烟也打开「对比两次」、导出和组牌；那三样记在下面。没装 Playwright 或 Chromium 时，`python -m pytest -q tests` 会跳过这些测试。`DECKBENCH_BROWSER_REQUIRED=1` 时缺了就失败。失败时上传截图和 trace。不改模拟、种子和 AI。见 [CI.md](CI.md)。
- **可以并排看两次已经跑完的战斗实验差在哪。** `GET /api/runs/compare?a=<id>&b=<id>` 按卡组、幕、房间对齐，给出胜率、超时、平均回合、掉血、每回合输出的 B−A，以及单卡每场使用次数和效率倍数的差。胜率和超时用两比例 z 检验，并附 Wilson 区间是否重叠；平均回合、掉血、每回合输出和单卡使用次数在 `raw.jsonl` 有逐场记录时用 Welch。只有 `cells.csv` 里的平均数时，差值照给，显著性留空。侧栏「对比两次」（`#/compare`）用绿色和红色标出方向，星号标出 5% 的检验有差别。只读 MCP `compare_runs`（`--import-only` 也有）返回同一份数。未知 id、同一个 id、重复或类型不对的参数是 400，正文里没有堆栈。不改模拟、种子和 AI。见 [COMPARE.md](COMPARE.md)。
- **可以把已经跑完的结果导出成一份自包含的 HTML。** `GET /api/runs/<id>/export.html` 导出一次已完成的测试。`GET /api/runs/compare/export.html?a=<id>&b=<id>` 导出两次战斗实验的对比（和 `GET /api/runs/compare` 同一份数）。可选的 `calibration` 把一份校准 JSON，或已经分诊好的 JSON，写进同一份文件；校准结果会附上由它算出的缺口分诊。CSS 和 SVG 都在文件里，没有要去加载的网络地址。响应是 `text/html; charset=utf-8`，并带文件名。文案跟界面语言走：简体中文、English、日本語、한국어。报告页、运行页（完成后）和「对比两次」有「导出报告」。命令行是 `python -m tools.export_report`。MCP `export_report`（`--import-only` 也有）把这份 HTML 写到允许的目录并返回 `path`，不新开模拟。未知 id、还没跑完、目录外的路径、符号链接跳出去、超限或坏 JSON，是 4xx 或 `{"ok": false, "error": ...}`，正文里没有堆栈。不改模拟、种子和 AI。见 [EXPORT.md](EXPORT.md)。
- **图形界面可以组一套牌，并存成马上能打的战斗预设。** 侧栏「组牌」（`#/decks`）列出模拟器已经认识的牌（内置状态牌和各 mod 的 `cards.yaml`）。可以按角色、类型、费用、稀有度筛选，并用中文名、英文名（卡面或游戏安装里已经有的标题；没有就不编）和 id 搜索。加入或移出牌，改张数和是否升级。旁边显示张数、费用曲线（SVG）和攻击 / 技能 / 能力的比例。`GET /api/cards` 只读、分页（`limit` 最大 200）。`POST /api/decks` 用模拟器自己的组牌规则校验，然后只在用户预设目录写一份和 `experiments/*.yaml` 相同的战斗预设。不覆盖出厂预设，不改 `mods/`、种子或已有配置。`..`、空字节、目录外、符号链接跳出去、超限、缺字段、类型不对都是 400，正文没有堆栈。新建测试选中这份预设就能开打。MCP `list_cards`（只读）和 `save_deck`（只写用户预设；`--import-only` 也有）。不改模拟、种子和 AI。见 [DECKS.md](DECKS.md)。
- **组牌预设可以选择要打哪些遭遇。** `#/decks` 和新建测试的自定义战斗都可以勾选多种遭遇，并为每种设场数。`GET /api/encounters` 只读、分页，可按幕（1/2/3）和房间（normal / elite / boss，也认中文）筛选，每条同时给简体中文名和英文名。名单用模拟器自己的 `encounter_pool`：普通、精英、首领里怪物和血量都在的遭遇。训练木桩 `DUMMY` 始终在，没有本机怪物数据时只有它。连战（例如第 1 幕全部精英，`act1_elite`）从这份名单现算，不另写一份遭遇表。`POST /api/decks` 和 MCP `save_deck` 接受 `encounters`（`id` / `fights`）和 `gauntlet`。都不写时仍是一场训练木桩（1 回合）。遭遇必须是模拟器会打的，每种 1–100 场，一份预设最多 40 种、合计最多 400 场。`max_turns` 可以自己写（1–200，和新建测试的最大回合同一上限）。不写时，只有训练木桩是 1 回合；只要有别的遭遇，就用出厂 `experiments/*.yaml` 顶层的整场回合上限。新建测试里勾选时用这一页的最大回合数，并只打勾选的遭遇。MCP `list_encounters` 只读（`--import-only` 也有）。不改模拟、种子、AI、出厂预设或配置。见 [DECKS.md](DECKS.md)。

### #59–#64

版本号仍是 0.1.5。`git log` 上的合并顺序是 #59、#60、#61、#62、#63、#64。

- **浏览器冒烟结束时放开事件循环。** pytest-playwright 的同步驱动会把主线程的事件循环标成正在运行，要到整个 pytest 会话结束才 `stop()`。界面冒烟和后面的 MCP 注册测试在同一个进程里时，后者的 `asyncio.run` 会报还在运行的循环；单独跑那份测试则能过。`tests/test_gui_browser.py` 在这个模块结束时关掉浏览器并停掉驱动。不靠重排测试，也不跳过。不改模拟、种子和 AI。
- **两份保存的牌组可以打同一份遭遇再看对比。** `#/decks` 上选卡组 A 和卡组 B。`POST /api/decks/head_to_head` 用已有的战斗测试各跑一遍。不另外指定时，遭遇、回合上限和种子都用第一份预设里存的。名单仍是最多 40 种遭遇、合计最多 400 场。两场都打完后，页面打开 `#/compare`。MCP `head_to_head`（`--import-only` 也有）做同一件事。同一份预设、未知 id、类型不对、回合不在 1–200、超过 400 场，是 400 或 `{"ok": false, "error": ...}`，正文没有堆栈。不改模拟器的出牌、播种和 AI，也不改出厂预设。见 [DECKS.md](DECKS.md)。
- **长测试可以看见打到第几场，也可以在两场之间取消。** `GET /api/runs/<id>/progress` 返回打完的场次、计划场次、当前遭遇和用时。`POST /api/runs/<id>/cancel` 和 MCP `cancel_run` 不杀进程：正在打的那场打完，还没开始的不再派发，状态是 `cancelled`，`partial` 为 true。打完的场次留在结果里，报告写明是部分结果。对比和导出读这些结果；还在跑的仍是 400 / 409。新建测试、`#/decks` 和对打面板有进度条和取消。见 [DECKS.md](DECKS.md)、[COMPARE.md](COMPARE.md)、[EXPORT.md](EXPORT.md)、[MCP.md](MCP.md)。
- **一份保存的牌组可以看每张牌是在帮胜率还是在拖后腿。** `POST /api/decks/<id>/card_impact` 做留一法：基线，加上每种牌少一张；`plus` 为真时再多一张。遭遇、种子、回合上限和卡组 id 都相同。全体合计不超过 400 场，默认按比例缩小场数。马上返回父任务 id。进度和取消用上面那一套，id 用父任务。结果是变体减基线的胜率、平均掉血、平均回合，以及 Wilson 区间。样本小于 30，或两侧区间重叠，`noisy` 为真。离线 HTML 带上同一张表。MCP `card_impact`（`--import-only` 也有）。不改模拟器的出牌、种子和 AI。见 [DECKS.md](DECKS.md)。
- **Windows 安装包用仓库里已有的版本号，并且可以手动查一次更新。** 版本号仍是 `0.1.5`，只写在 `sts2sim.__version__`。细节在下面的「版本号和检查更新」。
- **新建测试、组牌预设、连战、对打和单卡贡献可以同时打多场。** `workers` 省略时是 1。上限是 `min(cpu_count, 8)`。用的是 spawn 进程（Windows 和 PyInstaller 里都先走 `freeze_support`）。每场种子不变，结果文件仍按原来的场次顺序写。连战不在一条种子里面并行。取消仍是上面的规则。整局批量原来的进程滑块不动。这一台 4 核、Python 3.12 的机器上，200 场训练木桩（1 回合，启发式）workers=1 是 0.172 秒（1163 场/秒），workers=4 是 0.359 秒（557 场/秒）；同一份木桩改成束搜索、8 回合，200 场从 2.362 秒（84.7 场/秒）降到 0.902 秒（222 场/秒）。两边的 `raw.jsonl` 除每场用时外一致。见 [DECKS.md](DECKS.md)、[PERFORMANCE.md](PERFORMANCE.md)。

### 本版更新

- **界面有一页「本版更新」。** `#/whatsnew`，页脚和「关于」都能打开。内容是 [CHANGELOG.md](../CHANGELOG.md) 最新的一节。`GET /api/changelog` 在服务端解析成文本结构，界面按文本绘制，不把文件内容当成 HTML。关掉小面板之后，这个浏览器的 `localStorage` 按版本记住（`whatsnew.dismissed.` 加上版本号）。不联网。Windows 包把 `CHANGELOG.md` 打进 PyInstaller，并在程序旁边留一份。打包脚本仍是纯 ASCII，或带 BOM 的 UTF-8。不改模拟、种子和 AI。

### 中英切换

- **侧栏可以在简体中文和 English 之间切换。** 同一菜单里仍有日本語和한국어。选择记在 `localStorage` 的 `ui.lang`。没有记住的选择时，`navigator.language` 以 `zh` 开头就是简体中文（页面 `lang` 为 `zh-CN`），其他没有单独目录的语言是 English。界面句子在 `gui/locales/en.json` 与 `gui/locales/zhs.json`，键必须两边都有。卡牌、遭遇、遗物和原版角色只显示模拟器已经读到的标题，否则用原来的 id 或卡面上的名字。离线 HTML 的 `lang` 参数可以指定语言。不改模拟、种子和 AI。见 [DECKS.md](DECKS.md)、[EXPORT.md](EXPORT.md)、[CI.md](CI.md)。

### 结果包

- **可以把已经跑完的结果打成一个 `.deckbench.zip`，再在另一台 DeckBench 里导回来。** `GET /api/runs/<id>/bundle` 导出一次测试。`GET /api/runs/compare/bundle?a=<id>&b=<id>` 导出两次战斗实验；两边都是同一份对打时，清单的 `kind` 是 `head_to_head`。清单写 `sts2sim.__version__`、schema 版本（当前是 1）和每个文件的 SHA-256。读写都是二进制。`POST /api/bundles/import` 和 MCP `import_bundle` 校验清单和哈希，不执行包里的文件。导进来的测试带 `imported` 和 `origin`，出现在列表里，也能对比。见 [BUNDLES.md](BUNDLES.md)。

### 示例数据

- **没有游戏文件时，空的历史页可以载入一份自带的小样本。** `python tools/make_demo_bundle.py` 用现有的战斗工人打两场训练木桩（`encounter: DUMMY`）：一份用户牌组（`YIHESHI`、`XIAOBENBEN×2`）和出厂探针 `probe_noengine`，各 2 场、1 回合。zip 在 `gui/demo/sample.deckbench.zip`，格式和 #67 的 compare 包相同，并带上那份 `preset.yaml`。历史页没有记录时点「载入示例数据」。`POST /api/demo/load` 和 MCP `load_demo` 走同一条 `import_zip_bytes`。Windows 包带上这份 zip。不编造牌面或胜率。见 [BUNDLES.md](BUNDLES.md)。

### 版本号和检查更新

版本号仍是 0.1.5。唯一的数字在 `sts2sim.__version__`。Windows 包的 zip 名、exe 文件版本、反编译器的程序集版本、`VERSION.txt`、`GET /api/version` 和界面页脚都用这个数。页脚点开「关于」可以看到版本，也可以从页脚或「关于」打开「本版更新」。里面的「检查更新」默认不跑：只有点击才查询 GitHub 上 `Nopsil/deckbench` 的最新 Release，用 semver 比较。离线或速率限制时给出说明，不上传任何内容。可选的 MCP 工具 `check_update` 也是只有调用时才联网。

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

Field-level detail, paths and known gaps: [SAVE_FORMAT.md](SAVE_FORMAT.md), [DLL_MODS.md](DLL_MODS.md), [MCP.md](MCP.md), [MOD_AUTHORS.md](MOD_AUTHORS.md) ([简体中文](MOD_AUTHORS.zh-CN.md)), [CALIBRATION.md](CALIBRATION.md), [COMPARE.md](COMPARE.md), [DECKS.md](DECKS.md), [EXPORT.md](EXPORT.md), [PERFORMANCE.md](PERFORMANCE.md), [COVERAGE.md](COVERAGE.md), [CI.md](CI.md), [DEVELOPER.md](DEVELOPER.md). The note copied into the Windows zip is [gui/packaging/README-win.txt](../gui/packaging/README-win.txt). The index of every doc is [INDEX.md](INDEX.md). The full changelog is [CHANGELOG.md](../CHANGELOG.md).

### Try it

Import works without the game. The fixture uses fictional IDs, not a game file:

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en
python tools/import_run.py tests/fixtures/saves/sample_history.run --summary
python tools/import_run.py --discover
```

`--summary` prints a JSON summary (seed, character, ascension, floor reached, card and relic highlights) without the GUI. MCP `import_save(path)` returns the same summary. `import_history_batch(path, lines=false)` returns the same JSON as the CLI `--batch-summary` (`lines` true matches `--lines`, one object per line): read-only, skips `current_run.save`, keeps `SaveImportError` codes on unreadable files, and returns `ok: false` JSON when the path is missing or the folder is empty. Without local game data, `python tools/mcp_server.py --import-only` exposes `import_save`, `import_history_batch`, and `batch_run_summary`, `card_ab`, `compare_runs`, `explain_fight`, `calibrate`, `gap_triage`, `export_report`, `list_cards`, `list_encounters` and `save_deck`. It still has no play tools and no `seed_preview`. See [MCP.md](MCP.md).

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

### #41–#52

The version is still 0.1.5. Merge order on `git log` is #41, #43, #42, #44, #45, #46, #47, #48, #49, #50, #51, #52.

- **Coverage.** Tests now cover card-effect resolution, power and relic hooks, save parsing, calibration matching, and HTTP error paths. The snapshot and five edge bugs are in [COVERAGE.md](COVERAGE.md): a replayed X-cost card keeps the energy paid for that play; applying a power with `save` and no living target records 0; `{category, entry}` becomes `CATEGORY.ENTRY` (an entry alone is still just the entry); a summary no longer crashes on a non-object route step; a missing run folder is a 404, and a mod zip that lists a missing file returns that explanation instead of a `TypeError`. A normal play, a fixed seed, and AI choices are unchanged.
- **Continuous integration.** GitHub Actions runs the full pytest suite on Ubuntu and Windows with Python 3.11 and 3.12 (fastapi, httpx, and python-multipart installed so the GUI tests run), writes a pytest-cov summary on the job, and runs ruff. Tests that need a local game install still skip. See [CI.md](CI.md).
- **Bad input is a clear error.** `POST /api/import/batch`, `POST /api/calibrate`, `POST /api/calibrate/upload` and the read-only MCP tools answer a path outside an allowed folder, a symlink that escapes, an upload over 32MB, a broken JSONL line, a missing field or a wrong type with a 4xx or `{"ok": false, "error": ...}`, and the body has no stack trace. Simulation, seeds and AI are unchanged.
- **The seed-preview cache on Windows.** Reads and writes allow shared delete, and `os.replace` waits briefly and retries on access denied. A reader still sees a complete old file or a complete new file. The mod-author guide's bash samples use Git Bash on Windows, and skip when it is missing. A worker for `python -m sts2sim --workers` does not enter the entry point again.
- **The UI language follows the browser.** The sidebar 简体中文 / English switch (日本語 and 한국어 stay in the same menu) is stored in this browser's `localStorage` and wins over `settings.json`. With no saved choice it follows `navigator.language`. Decisions and Calibration use the same strings. Card and encounter ids are shown as stored.
- **The Windows package can be built and checked on Actions without publishing it.** `.github/workflows/windows-package.yml` runs on a manual dispatch or a `v*` tag, on `windows-latest`, through the existing `build.ps1` (`-Version 0.1.5`). It then runs `dry_check.py --app` on the built directory and `audit.ps1` on the zip (the runner has no game, so there is no install-directory hash compare). From `sim/` inside the zip it runs `python -m sts2sim --help` and one training-dummy fight (`claude_v34` deck `probe_noengine`, `encounter: DUMMY`). The zip is only an Actions artifact. The workflow does not create a GitHub Release. Steps: [DEVELOPER.md](DEVELOPER.md#windows-打包版--building-the-windows-package). The workflow write-up is [CI.md](CI.md). The note that ships in the zip is [gui/packaging/README-win.txt](../gui/packaging/README-win.txt).
- **简体中文 docs.** Calibration, CI, the coverage snapshot, the performance sample and the synthetic DLL fixture note are Chinese and English, and they are listed in [INDEX.md](INDEX.md). The mod-author guide is still English [MOD_AUTHORS.md](MOD_AUTHORS.md) plus 简体中文 [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md).
- **The packaging scripts run on Windows PowerShell 5.1.** `build.ps1`, `audit.ps1` and `win_api_test.ps1` under `gui/packaging` contain Chinese and are UTF-8 with a BOM. Without the BOM a multibyte character can swallow a quote, and `build.ps1` failed with “The string is missing the terminator”. A pure ASCII `.ps1` may omit the BOM. The XML comment in `ilspycmd-host.csproj` no longer contains `--` (the old `--version` / `--self-contained` text made MSBuild report MSB4025). `dry_check.py` rejects both kinds of problem.
- **Gap triage.** `python tools/gap_triage.py` reads one or more `tools/calibrate.py --json` results and totals `likely_sim_gap` by encounter and by the enemy power or mechanic involved. Real HP lost above p95 means the sim was too optimistic; below p5 means too pessimistic. The Markdown points at `sts2sim/powers_enemy.py`, `sts2sim/powers.py` and `sts2sim/enemies.py`, and Thorns also points at the optional `mechanic_adjust`. `POST /api/gap_triage` and the read-only MCP tool `gap_triage` (also on `--import-only`) return the same summary. **Calibration** (`#/calibrate`) lists both sides under the comparison table, with the suggested source files. Simulation, seeds and AI are unchanged. See [CALIBRATION.md](CALIBRATION.md).
- **A packaged HTTP smoke test, and UTF-8.** After the CLI smoke, `gui/packaging/smoke_api.ps1` extracts the new zip, starts the packaged `DeckBench.exe --serve` with no window, waits for `GET /api/health`, runs one training-dummy fight through `POST /api/runs`, and stops the process. The smoke log is an artifact. `--serve` no longer exits when local game data is missing; routes that need the game still return the same explanation. Opening the window still checks for the game. JSON responses, and text responses such as text/html, send `charset=utf-8`. The smoke reads the response bytes as UTF-8 and checks that the training dummy's `enc_name` is still 「木桩」, and that the deck name in the summary is Chinese. See [CI.md](CI.md).

Gap triage can be looked at without the game. Encounter ids in the fixture are fictional:

```bash
python tools/gap_triage.py tests/fixtures/gap_triage --catalog tests/fixtures/gap_triage/catalog.json
```

### #54–#58

The version is still 0.1.5. Merge order on `git log` is #54, #55, #56, #57, #58.

- **The GUI gets a headless browser smoke on Ubuntu CI.** A separate job (not part of the existing pytest matrix) opens `python -m gui.app --serve` from source with pytest-playwright's Chromium. No local game data: the test writes an empty card cache, and the combat test uses the same training dummy as the package smoke (`claude_v34` deck `probe_noengine`, `encounter: DUMMY`, one turn). It checks that the main pages (including `#/calibrate` and Decisions) load with no console errors, that the 简体中文 / English switch changes the visible strings and stores the choice in `localStorage` `ui.lang`, that the dummy fight can be started from the GUI and reaches done, and that gap triage renders from the calibration fixture. The same smoke also opens Compare runs, export, and the deck builder; those three are the next entries. `python -m pytest -q tests` skips these tests when Playwright or Chromium is missing. `DECKBENCH_BROWSER_REQUIRED=1` fails instead of skipping. Screenshots and traces are uploaded on failure. Simulation, seeds and AI are unchanged. See [CI.md](CI.md).
- **Two finished combat tests can be compared side by side.** `GET /api/runs/compare?a=<id>&b=<id>` lines them up by deck, act and room and returns B−A for win rate, timeout, average turns, HP loss and damage per turn, plus per-card uses per fight and efficiency. Significance for win rate and timeout is the two-proportion z-test, with whether the Wilson intervals overlap. Average turns, HP loss, damage per turn and per-card usage use Welch's t-test when `raw.jsonl` has every fight. Averages that exist only in `cells.csv` still produce a delta, with significance left empty. **Compare runs** (`#/compare`) colors a favorable delta green and an unfavorable one red, with a star when the 5% test finds a difference. The read-only MCP tool `compare_runs` (also on `--import-only`) returns the same numbers. An unknown id, the same id twice, or a repeated or wrong-typed parameter is a 400 with no stack trace. Simulation, seeds and AI are unchanged. See [COMPARE.md](COMPARE.md).
- **A finished result can be exported as one self-contained HTML file.** `GET /api/runs/<id>/export.html` exports one finished test. `GET /api/runs/compare/export.html?a=<id>&b=<id>` exports a comparison of two combat tests (the same numbers as `GET /api/runs/compare`). Optional `calibration` includes a calibration JSON, or a triage JSON that was already written, in the same file; a calibration also adds the gap triage computed from it. The CSS and the SVG charts are in the file, and nothing in it loads from the network. The response is `text/html; charset=utf-8` with a filename. The words follow the UI language: 简体中文, English, 日本語, 한국어. The report page, the run page once a test is done, and **Compare runs** have **Export report**. The command is `python -m tools.export_report`. The MCP tool `export_report` (also on `--import-only`) writes that HTML inside an allowed folder and returns `path`. It does not start a simulation. An unknown id, a test that is not finished, a path outside an allowed folder, a symlink that escapes, an oversized file, or broken JSON is a 4xx or `{"ok": false, "error": ...}`, with no stack trace. Simulation, seeds and AI are unchanged. See [EXPORT.md](EXPORT.md).
- **The GUI can build a deck and save it as a combat preset you can run immediately.** **Deck builder** (`#/decks`) lists the cards the simulator already knows (built-in status cards and each mod's `cards.yaml`). Filter by character, type, cost and rarity, and search the Chinese name, the English name when the card or the install already has one, and the id. Add or remove cards, change counts and upgrades. Size, an SVG cost curve and the attack / skill / power split update as you edit. `GET /api/cards` is read-only and paginated (`limit` at most 200). `POST /api/decks` checks the deck with the simulator's own rules and writes one combat preset, in the same shape as `experiments/*.yaml`, only in the user presets folder. It does not overwrite shipped presets, and it does not change `mods/`, seeds or existing configs. `..`, a null byte, a path outside that folder, a symlink that escapes, an oversized body, a missing field or a wrong type is a 400 with no stack trace. New test lists the preset, and choosing it starts the run. MCP `list_cards` (read-only) and `save_deck` (writes only a user preset; also on `--import-only`). Simulation, seeds and AI are unchanged. See [DECKS.md](DECKS.md).
- **A deck preset can choose which encounters it runs.** **Deck builder** and a custom combat test can tick several encounters and set the fights for each one. `GET /api/encounters` is read-only and paginated. Filter by act (1/2/3) and room (normal / elite / boss, Chinese names accepted). Each row has a 简体中文 name and an English name. The list is the simulator's own `encounter_pool`: normal, elite and boss encounters whose monsters and hit points are present. The training dummy `DUMMY` is always included, and it is the only row when there is no local monster codex. A gauntlet (for example every Act 1 elite, `act1_elite`) is built from that list, not from a separate roster. `POST /api/decks` and MCP `save_deck` take `encounters` (`id` / `fights`) and `gauntlet`. Omitting both is still one training-dummy fight (1 turn). An encounter has to be one the simulator runs, each one is 1–100 fights, and a preset holds at most 40 encounters and 400 fights in total. `max_turns` can be set (1–200, the same ceiling as max turns on New test). When it is omitted, a dummy-only preset is 1 turn, and any other encounter uses the full-fight cap from the top of the shipped `experiments/*.yaml` files. A custom test uses the page's max turns and runs only the ticked encounters. MCP `list_encounters` is read-only (also on `--import-only`). Simulation, seeds, AI, shipped presets and configs are unchanged. See [DECKS.md](DECKS.md).

### #59–#64

The version is still 0.1.5. Merge order on `git log` is #59, #60, #61, #62, #63, #64.

- **The browser smoke releases the event loop when that module finishes.** pytest-playwright's sync driver marks the main-thread loop as running and does not `stop()` until the whole pytest session ends. When the GUI smoke and the later MCP registration test share a process, that test's `asyncio.run` reports a loop that is still running. The same test passes on its own. `tests/test_gui_browser.py` closes the browser and stops the driver at the end of the module. It does not reorder tests and it does not skip. Simulation, seeds and AI are unchanged.
- **Two saved decks can run the same encounters and open the comparison.** **Deck builder** (`#/decks`) picks deck A and deck B. `POST /api/decks/head_to_head` runs each with the combat test that already exists. Omit the overrides and the encounters, turn cap and seed are the ones stored on the first preset. The list is still at most 40 encounters and 400 fights in total. When both tests are finished the page opens `#/compare`. MCP `head_to_head` (also on `--import-only`) does the same thing. The same preset twice, an unknown id, a wrong type, a turn cap outside 1–200, or more than 400 fights is a 400 or `{"ok": false, "error": ...}`, with no stack trace. Simulator play, seeding, AI and shipped presets stay as they are. See [DECKS.md](DECKS.md).
- **A long test shows how many fights are done, and it can be cancelled between fights.** `GET /api/runs/<id>/progress` returns fights done, the planned total, the current encounter and the elapsed time. `POST /api/runs/<id>/cancel` and MCP `cancel_run` do not kill the process: the fight in progress finishes, fights that have not started are not dispatched, the status is `cancelled` and `partial` is true. Finished fights stay in the result files, and the report says the result is partial. Compare and export read those results. A test that is still running is still a 400 / 409. New test, `#/decks` and the head-to-head panel have a progress bar and Cancel. See [DECKS.md](DECKS.md), [COMPARE.md](COMPARE.md), [EXPORT.md](EXPORT.md) and [MCP.md](MCP.md).
- **A saved deck can show which cards help or hurt.** `POST /api/decks/<id>/card_impact` runs leave-one-out: the baseline, plus one copy removed from each unique card, and one extra copy when `plus` is true. Encounters, seed, turn cap and deck id stay the same. The whole ablation stays within 400 fights. The default scales fight counts down. The response returns the parent id immediately. Progress and cancel are the ones above, using the parent id. The result is the variant-minus-baseline win rate, average HP lost and average turns, with a Wilson interval. `noisy` is true when a side has fewer than 30 fights or the two intervals overlap. The offline HTML includes the same table. MCP `card_impact` (also on `--import-only`). Simulator play, seeds and AI are unchanged. See [DECKS.md](DECKS.md).
- **The Windows package uses the version the repository already has, and updates are a manual check.** The version is still `0.1.5`, written only in `sts2sim.__version__`. The details are under Version and update check below.
- **New test, a saved deck, a gauntlet, a head-to-head and a card impact can run fights at the same time.** Omitting `workers` is 1. The cap is `min(cpu_count, 8)`. The pool is spawned (`freeze_support` on Windows and in the PyInstaller package). Per-fight seeds stay the same, and result files stay in the original fight order. A gauntlet is not parallel inside one seed. Cancel is still the rule above. The existing process slider for full runs is unchanged. On this 4-core Python 3.12 machine, 200 training-dummy fights (1 turn, heuristic) took 0.172 s with workers=1 (1163 fights/s) and 0.359 s with workers=4 (557 fights/s). The same dummy with the beam agent and 8 turns, 200 fights, went from 2.362 s (84.7 fights/s) to 0.902 s (222 fights/s). The two `raw.jsonl` files match aside from per-fight time. See [DECKS.md](DECKS.md) and [PERFORMANCE.md](PERFORMANCE.md).

### What's new

- **The GUI has a What's new page.** `#/whatsnew` is linked from the footer and from About. It shows the latest section of [CHANGELOG.md](../CHANGELOG.md). `GET /api/changelog` parses that section on the server into text, and the page draws the text without treating the file as HTML. Dismissing the small panel is stored in this browser's `localStorage`, keyed by version (`whatsnew.dismissed.` plus the version). It does not use the network. The Windows package puts `CHANGELOG.md` in the PyInstaller bundle and leaves a copy beside the program. Packaging scripts stay pure ASCII, or UTF-8 with a BOM. Simulation, seeds and AI are unchanged.

### 简体中文 and English

- **The sidebar switches between 简体中文 and English.** 日本語 and 한국어 stay in the same menu. The choice is `ui.lang` in `localStorage`. With no saved choice, a `navigator.language` that starts with `zh` is 简体中文 (the page `lang` is `zh-CN`). A language without its own catalog is English. UI sentences are in `gui/locales/en.json` and `gui/locales/zhs.json`, and a key has to exist on both sides. Card, encounter, relic and character names are shown only when the simulator has already loaded a title. Otherwise the existing id or the name on the card is used. Offline HTML accepts a `lang` parameter. Simulation, seeds and AI are unchanged. See [DECKS.md](DECKS.md), [EXPORT.md](EXPORT.md) and [CI.md](CI.md).

### Run bundles

- **A finished result can be packed into one `.deckbench.zip` and imported on another DeckBench.** `GET /api/runs/<id>/bundle` exports one test. `GET /api/runs/compare/bundle?a=<id>&b=<id>` exports two combat tests; when both sides are the same head-to-head, the manifest `kind` is `head_to_head`. The manifest records `sts2sim.__version__`, the schema version (currently 1), and a SHA-256 of each file. Reads and writes are binary. `POST /api/bundles/import` and MCP `import_bundle` check the manifest and the hashes and do not execute anything in the bundle. An imported test is marked `imported`, keeps `origin`, shows up in the run list, and can be compared. See [BUNDLES.md](BUNDLES.md).

### Demo data

- **With no game files, an empty History page can load a built-in sample.** `python tools/make_demo_bundle.py` runs two training-dummy fights with the existing combat worker (`encounter: DUMMY`): one saved deck (`YIHESHI`, `XIAOBENBEN×2`) and the shipped probe `probe_noengine`, 2 fights and 1 turn each. The zip is `gui/demo/sample.deckbench.zip`, the same compare-bundle format as #67, including that `preset.yaml`. Empty History has **Load demo data**. `POST /api/demo/load` and MCP `load_demo` use the same `import_zip_bytes`. The Windows package includes the zip. Card text and win rates are not invented. See [BUNDLES.md](BUNDLES.md).

### Version and update check

The version is still 0.1.5. The only copy of that number is `sts2sim.__version__`. The Windows zip name, the exe file version, the decompiler assembly version, `VERSION.txt`, `GET /api/version` and the GUI footer all use it. The footer opens About, which shows the version. The footer and About also open What's new. **Check for updates** does not run on its own: a click asks the public GitHub API for the latest `Nopsil/deckbench` release and compares semver. Offline and rate-limit responses are explanations, and nothing is uploaded. The optional MCP tool `check_update` also waits until it is called.

### Practical limits

**Import.** A finished `.run` and a live `current_run.save` are different JSON. Finished history has no map column, so the route has floors and room types, not left/right position. A file we cannot read stops with an explanation. If it looks encrypted or corrupt, DeckBench does not try to decrypt it. `progress.save` is unlocks and stats, not a run.

**Seed preview.** Match it to the real game only with full unlocks, not a tutorial run, and no custom modifiers. The act 1 map is what `CreateMap` builds on entering the act; check it against a screenshot. Act 2+ is generated as if you entered that act now, without playing the previous act. It matches the live game only when combat does not consume the map's random stream. Unknown (`?`) nodes are not rolled until you walk into them. Encounter queues are the draw order rolled at the start, not left-to-right positions on the map. If the relic-bag order is not on the engine object, the preview lists starting relics only and does not pick chests for you.

**DLL.** Methods with branches, loops, choices or custom commands keep a blank effect and a note. A conditional effect is not imported as always-on. Harmony, Godot scenes and pictures inside a `.pck` are not simulated. Without a method body the class is listed as a placeholder and Check will not pass. Enum numbers are not guessed into attack, rarity or keywords when the game assembly was not a decompiler reference. Cards registered only into a base character's pool do not become a new character. Imported numbers are not matched card-by-card against the live game; play a small shared-seed batch and check one fight before you compare balance. Decompiler output is deleted. Do not commit an imported folder if it holds text you do not want to publish. The DLL fixture in the repo is synthetic. Decompiling that fixture does not add a local game DLL as a reference. Importing your own mod still uses the local install.

**mentor-full.** Vanilla characters only. On a mod character, out-of-combat decisions fall back to the learned AI and the log says so. If the library fails to import, that run stops instead of silently scoring the learned AI for the whole run. After a run, read the combat fallback rate and the PPO net/fallback counts. Do not screen seeds when fallback is about 100%. Nineteen v0.111 cards (SIDESTEP and the rest) hit a known upstream loader bug; the code-only local patch is `docs/patches/spire-mentor-v0111-cards.patch`. The packager copies `gui/*.py` to `sim/gui`. `audit.ps1` rejects `.onnx`, `sts2_rs`, `sts2_hint` and `champions.toml` in the zip.
