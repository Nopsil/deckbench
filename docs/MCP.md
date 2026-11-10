# MCP 对战模式 / MCP play mode

[← 返回 README](../README.md) · [文档索引](INDEX.md) · [存档格式](SAVE_FORMAT.md)

让支持 MCP 的 AI 助手（Claude、Cursor、Grok 等）通过 `tools/mcp_server.py` 在模拟器里**一步一步**打一局：看局面、选选项、写理由、撤销重来，最后导出一份操作清单，可以照着在真游戏里用同一个种子复刻。

*Lets any MCP client play a seeded run step by step: read the state, pick options with a reason, undo, and export a replay list you can follow in the real game with the same seed.*

## 准备 / Setup（从源码运行 / from source）
```sh
pip install -r requirements-mcp.txt          # 多装一个 mcp>=1.20,<2
python -m sts2sim.gamedata setup             # 和平时一样，先从你自己的游戏生成本地数据
python tools/mcp_server.py                   # stdio
python tools/mcp_server.py --http --port 8765   # streamable-HTTP → http://127.0.0.1:8765/mcp
```
- 只绑 `127.0.0.1`（`--host` / `DECKBENCH_MCP_HOST` 可改，`--port` / `DECKBENCH_MCP_PORT`）。经隧道或反代给远程连接器用时加 `--no-host-check`。
- stdio 客户端配置示例：`{"mcpServers":{"deckbench":{"command":"python","args":["<仓库路径>/tools/mcp_server.py"]}}}`
- 每局的记录放在 `DECKBENCH_MCP_RUNS`（默认在 DeckBench 缓存目录下的 `mcp_runs/`）。
- 局面里的中文卡名/说明在运行时从**你本机的游戏安装**读取，只在内存里用，不随本项目分发；读不到时显示内部 ID。

## 工具 / Tools
| 工具 | 说明 |
|---|---|
| `new_run(seed, character, ascension, persona, style)` | 种子按游戏规则规范化（大写、O→0、I→1）；persona 可选：`qianwen`、`juggler`（杂耍流说明，同时把 style 设成 `juggler`），或任意一段风格描述；style 是 `auto` 代打用的打法风格：`standard`（默认）或 `juggler`（杂耍流：优先拿杂耍 JUGGLING，偏好多段攻击和反直觉的组合） |
| `list_styles()` | 列出可用的打法风格 |
| `get_state()` | 楼层/生命/金币/遗物/药水/牌组 + 当前界面 + 战斗（能量、手牌、敌人生命/意图/能力）+ 带编号的合法选项 |
| `act(option_index, reason, indices, option)` | 执行一个选项；多选界面用 `indices`；`option` 可以写选项文字或 ID（如 `JUGGLING`、`跳过`），比选项号稳定；非法选项返回错误并保持原状 |
| `auto(steps, until)` | 交给内置 AI 代打；`until`：`combat_end` / `floor` / `screen:<名字>` |
| `get_map()` / `get_deck()` | 文字地图（含当前位置）/ 牌组 |
| `undo(steps)` / `restore(step)` | 回退几步 / 回到第 step 个决策之前 |
| `get_log(last)` / `export_log()` | 决策日志；导出 decisions.jsonl + replay.md |
| `list_runs()` / `open_run(run_id)` | 列出 / 重新打开以前的局 |
| `import_save(path)` | 只读导入一个 `.run` / `current_run.save` / 存档目录，返回 JSON 摘要（`seed`、`character`、`ascension`、`floor_reached`、`highlights.cards`、`highlights.relics`；目录是 `kind: folder`）。不开始模拟，不写存档。失败也是 JSON（`ok: false`） |
| `import_history_batch(path, lines=false)` | 只读扫描存档目录或单个记录，返回和 `python tools/import_run.py <目录> --batch-summary` 相同的稳定 JSON。默认一个数组；`lines` 为 true 时每局一行（`--lines`）。键顺序：`file`、`seed`、`ascension`、`character`、`floors`，有胜负或放弃才有 `result`（`won` / `lost` / `abandoned`）。读不开的 history 文件带 `error` 码，不中断。目录里的 `current_run.save` 不进结果。不写存档。失败也是 JSON（`ok: false`） |
| `seed_preview(seed, character, ascension, neow, cache, cache_dir)` | 不打一局。返回和 `tools/seed_preview.py --json -` 相同的稳定 v1 JSON。`neow`：`first`（默认，第一个没锁的）/ `all` / `none` / 序号文本（如 `"2"`），是选择器本身。`cache` 可选，把同一份 JSON 留在本机（目录不能在仓库里）。参数不合法或没有本机游戏逻辑时返回 `{"ok": false, "error": ...}`，不编地图 |
| `batch_run_summary(path)` | 只读一份已经跑完的整局结果。`path` 是 `runs.jsonl`，或含有它的运行目录。返回和报告页 / `GET /api/runs/{id}/summary` 相同的摘要：胜率、Wilson 95% 区间（`win_ci_low` / `win_ci_high`）、`sample_warning`。数字来自 `sts2sim/stats.py`。有效局数少于 30 时 `sample_warning` 为 true，数字仍给出。不新开模拟，不写文件 |
| `card_ab(a, b="")` | 只读比较两组已经跑完的整局结果（单卡 A/B）。`a`、`b` 各是一份 jsonl 或含 `runs.jsonl` 的目录。`b` 留空时，`a` 必须是目录，且里面恰好一对 `*_A.jsonl` 与 `*_B.jsonl`（或 `A.jsonl` 与 `B.jsonl`）。顶层 `p_value` 和 `win_ab` 来自 `sts2sim/stats.py`（和 `ab_card.py --format json` 同一份胜率对照）。`result` 和 `GET /api/ab` 相同，配对差还在。不新开模拟，不写文件 |
| `compare_runs(a, b)` | 只读比较两次已经跑完的战斗实验。`a`、`b` 是界面测试 id，或结果目录，或其中的 `raw.jsonl` / `cells.csv`。格子按卡组、幕、房间对齐，给出胜率、超时、平均回合、掉血、每回合输出的 B−A，以及单卡每场使用和效率倍数的差。胜率和超时的显著性是两比例 z 检验，并附 Wilson 区间是否重叠；逐场的连续指标用 Welch。和 `GET /api/runs/compare`、`#/compare` 是同一套数。不新开模拟，不写文件。见 [COMPARE.md](COMPARE.md) |
| `explain_fight(path, fight=0, seed="", offset=0, limit=20)` | 只读 `--explain` 写的 JSONL（`explain.jsonl`、`*.explain.jsonl`，或只含其中一份的目录）。`fight` 是按 `seed` 过滤后的第几场，从 0 开始。每一条决策带 `chosen` 和按分数从高到低的候选（最多 5 条，选中的那条即使分低也会留下）；同一层的奖励和商店接在这场战斗后面。`offset` / `limit` 分页，`limit` 最大 100。不新开模拟，不写文件 |
| `calibrate(real, sim)` | 只读对照一份真对局和同一条选牌路径上的模拟掉血。`real` 是 `.run` / `current_run.save`（读法和 `import_save` 相同）。`sim` 是 `runs.jsonl` 或含它的目录，路径规则与 `batch_run_summary` 相同。只保留种子、角色、进阶和 `picked` 序列都一致的模拟局。每场战斗有 `real_hp_lost`、`mean`、`p10`、`p90`、`percentile`；真值在 p5–p95 之外时 `likely_sim_gap` 为 true。层数、房间和遭遇对不上则 `status` 为 `unmatched`，不改用别的层。不新开模拟，不写文件。规则见 [CALIBRATION.md](CALIBRATION.md) |
| `gap_triage(reports="", paths=None, catalog="", min_compared=1)` | 只读汇总一份或多份校准 JSON。`reports` 是 `calibrate` 或 `POST /api/calibrate` 的 JSON 文本（一个对象或数组）。`paths` 是这些 JSON 的文件或目录，路径规则与 `batch_run_summary` 相同。真机掉血高于 p95 排成模拟偏乐观，低于 p5 排成模拟偏悲观，按遭遇和敌人能力 / 机制排名，`code` 指向源文件。不新开模拟，不写文件。见 [CALIBRATION.md](CALIBRATION.md) |
| `export_report(run="", a="", b="", calibration="", out="", lang="")` | 把一次已完成的测试、可选的两次战斗对比、可选的校准或缺口分诊写成一份离线 HTML（内联 CSS 和 SVG，不访问网络），并返回 `path`。`lang` 可以是 `zh-CN` / `en` / `ja` / `ko`。见 [EXPORT.md](EXPORT.md) |
| `list_cards(q="", character="", card_type="", cost="", rarity="", mod="", offset=0, limit=40)` | 只读列出模拟器已经认识的牌。`q` 同时搜中文名、英文名和 id。`card_type` 是 `Attack` / `Skill` / `Power` / `Status` / `Curse`（也认中文）。`cost` 是 `0`、`1`、`X` 或 `none`。分页，`limit` 最大 200。不写文件。见 [DECKS.md](DECKS.md) |
| `list_encounters(q="", act="", room="", offset=0, limit=40)` | 只读列出模拟器会打的遭遇。`q` 同时搜中文名、英文名和 id。`act` 是 `1` / `2` / `3`。`room` 是 `normal` / `elite` / `boss`（也认中文和 `Monster` / `Elite` / `Boss`）。返回 `name_zh`、`name_en`，以及用同一份遭遇池拼出的 `gauntlets`（例如 `act1_elite` 是第 1 幕全部精英）。没有怪物数据时只有训练木桩 `DUMMY`。分页，`limit` 最大 200。不写文件。见 [DECKS.md](DECKS.md) |
| `save_deck(deck)` | `deck` 是 JSON 对象：`id`、`name`、`mod`、`cards`（`id` / `count` / `upgrade`），可选 `encounters`（`id` / `fights`）、`gauntlet`（例如 `act1_elite`）和 `max_turns`（1–200）。不写 `max_turns` 时，只有训练木桩是 1 回合，有别的遭遇则用出厂实验的整场回合上限。校验后只在用户预设目录写一份和 `experiments/*.yaml` 相同的战斗预设。不覆盖出厂预设，不改 `mods/`、种子或配置。见 [DECKS.md](DECKS.md) |
| `head_to_head(a, b, encounters="", gauntlet="", max_turns=None, seed=None)` | 两份已保存的用户预设各打一遍已有的战斗测试。同一份遭遇、同一个回合上限、同一颗种子。省略时用预设 `a` 里存的。名单合计最多 400 场。成功返回两次测试的 id 和 `compare`（`/#/compare?a=&b=`）。训练木桩不需要本机游戏数据。见 [DECKS.md](DECKS.md) |

`import_save` 和 `python tools/import_run.py <path> --summary` 是同一份摘要（`sts2sim/saveimport.py` 的 `summarize`；命令行多缩进，对象相同）。没有本机游戏数据时，对战服务仍会退出；改跑 `python tools/mcp_server.py --import-only`（`import_save`、`import_history_batch`，以及下面的只读分析，含 `calibrate` 和 `gap_triage`；还有 `list_cards`、`list_encounters`、`save_deck` 和 `head_to_head`；没有对战工具，也没有 `seed_preview`）或上面的命令行。`head_to_head` 会用已有的战斗测试开两场，其余工具不开模拟。

`import_history_batch` 和 `python tools/import_run.py <目录> --batch-summary` 是同一份文本（行来自 `sts2sim/saveimport.py` 的 `batch_summary`；`lines=true` 对应 `--lines`）。它不带 `import_save` 那种牌和遗物要点。路径不存在或目录里没有对局文件时，返回 `{"ok": false, "read_only": true, "error": "..."}`。

*`import_history_batch` is the same JSON as `python tools/import_run.py <folder> --batch-summary`. `lines` true prints one object per line. It does not start a run and does not write into saves. `--import-only` exposes this tool next to `import_save`.*

`seed_preview` 只在对战服务器上（需要已经生成本机游戏逻辑，和 `new_run` 一样）。成功时没有 `ok` 字段，就是那份 v1 文档：`v`、`seed_input`、`seed`、`warnings`、`character`、`ascension`、`acts`、`maps`、`rooms`、`distribution`、`ancient`、`neow_options`、`after_neow`、`relics`、`limits`。可选 `cache=true` 按规范化种子、角色、进阶和 `neow` 选择器写入 `cache_dir`（空着则用 `DECKBENCH_CACHE/seed-preview`），不进仓库。

*Seed preview is the same stable v1 document as `python tools/seed_preview.py <seed> --json -`. `neow` is `first`, `all`, `none`, or a decimal index such as `"2"`. It does not start a run. A bad selector or a missing local engine returns `{"ok": false, "error": "..."}` instead of an invented map. `--import-only` does not expose `seed_preview`.*

## 只读分析已有结果 / Read results without the GUI

`batch_run_summary`、`card_ab`、`compare_runs`、`explain_fight`、`calibrate`、`gap_triage` 不打开图形界面，也不新开一局模拟。`compare_runs` 和 `GET /api/runs/compare` 读的是已经写好的战斗结果（`raw.jsonl`，或 `cells.csv` / `cards.csv`），按格子和单卡给差值。胜率和 A/B 的区间、p 值、样本警告都从 `sts2sim/stats.py` 来，和 `tools/batch.py` 的胜率行、`tools/ab_card.py --format json`、报告页、`GET /api/ab` 是同一套数。说明日志是 `--explain` 已经写好的 JSONL（`tools/explain_fight.py` 读的那种），这里按一场战斗把决策分页返回，不重新打分。`calibrate` 和 `python tools/calibrate.py`、`POST /api/calibrate` 是同一份对照：真机掉血对模拟的 mean / p10 / p90 / percentile，p5–p95 之外标 `likely_sim_gap`，对不上的层是 `unmatched`。`gap_triage` 和 `python tools/gap_triage.py`、`POST /api/gap_triage` 是同一份汇总：把这些 `likely_sim_gap` 按遭遇和敌人能力排成偏乐观或偏悲观。`export_report` 把上面这些已经算好的结果写成一份离线 HTML，并返回 `path`。它会写这一个文件，不新开模拟。见 [EXPORT.md](EXPORT.md)。`list_cards`、`list_encounters` 和 `save_deck` 是组牌，不在这一节，见 [DECKS.md](DECKS.md)。`--import-only` 也提供这三条。

*These tools do not open the GUI and do not start a simulation. `compare_runs` reads combat results that were already written (`raw.jsonl`, or `cells.csv` / `cards.csv`) and returns the same cell and card deltas as `GET /api/runs/compare`. Win-rate intervals, the A/B p-value and the small-sample warning come from `sts2sim/stats.py`, the same numbers as the `tools/batch.py` win-rate line, `tools/ab_card.py --format json`, the report page and `GET /api/ab`. The explanation log is the JSONL `--explain` already wrote (what `tools/explain_fight.py` reads); one fight is returned a page of decisions at a time, without scoring again. `calibrate` is the same report as `python tools/calibrate.py` and `POST /api/calibrate`: real HP lost against the simulated mean / p10 / p90 / percentile, `likely_sim_gap` outside p5–p95, and `unmatched` when a floor does not line up. `gap_triage` is the same summary as `python tools/gap_triage.py` and `POST /api/gap_triage`: those `likely_sim_gap` rows ranked by encounter and by enemy power, too optimistic or too pessimistic. `export_report` writes those finished numbers into one offline HTML file and returns `path`. It writes that one file and does not start a simulation. See [EXPORT.md](EXPORT.md). `list_cards`, `list_encounters` and `save_deck` build a deck; they are not part of this section. See [DECKS.md](DECKS.md). `--import-only` exposes them too.*

路径按真实路径算（符号链接看目标）。允许读的目录只有：

- 界面数据目录：`STS2SIM_GUI_DATA`，没设就是 `gui/.data`（一次测试在 `runs/<id>/runs.jsonl`）
- DeckBench 缓存（`DECKBENCH_CACHE`，否则是用户缓存下的 `deckbench`）以及其中的 `mcp_runs`（或 `DECKBENCH_MCP_RUNS`）
- `DECKBENCH_ANALYSIS_ROOTS`：额外目录，用系统的路径分隔符分开。`tools/batch.py --out` 和旁边的 `*.explain.jsonl` 放在哪，就把那个目录加进来

以下直接拒绝，不读内容，也不创建文件：

- 上面这些目录以外的路径（`..` 或符号链接跳出去也算）
- 存档树：路径上名叫 `saves`、`history`、`SlayTheSpire2` 的目录，以及本机游戏数据根；还有 `.run` / `.save`。规则和导入工具拒绝写入时相同（`saveimport.refuse_save_write`）

失败也是 JSON：`{"ok": false, "read_only": true, "error": "..."}`（`export_report` 的失败不带 `read_only`）。`error` 有 `path_not_allowed`、`refuse_write`、`not_found`、`not_json`、`not_batch`、`not_explain`、`need_b`、`ambiguous_pair`、`fight_out_of_range`。除 `export_report` 外，成功时 `ok` 和 `read_only` 都是 true。`export_report` 成功时 `ok` 为 true，并多一个 `path`，那一份 HTML 写在允许的目录里。

*`--import-only` exposes these tools next to the importers, including `calibrate` and `gap_triage`. It still has no play tools and no `seed_preview`. A simulated-result path is allowed only inside the GUI data directory, the DeckBench cache (including `mcp_runs`), or `DECKBENCH_ANALYSIS_ROOTS`. Anything else, including a symlink that escapes, is `path_not_allowed`. Save trees and `.run` / `.save` files are `refuse_write`, the same rule as the import tools. `calibrate`'s `real` argument is the run file itself and is read like `import_save`; its `sim` argument follows the rule above. `gap_triage` paths follow the same rule. Failures are JSON (`ok: false`, `read_only: true`) and nothing is written. `export_report` is the exception: on success it returns `path` and writes that one HTML file inside an allowed folder.*

## 资源 / Resources
| 资源 | 说明 |
|---|---|
| `deckbench://seed-preview/v1` | 预览 JSON 的字段顺序、`neow` 取值和角色列表。不生成地图，不读游戏 |

格式见 [SAVE_FORMAT.md](SAVE_FORMAT.md)。

同一种子 + 同一串选择 = 同一局，所以撤销/恢复是「重开 + 重放」；服务器重启后也能 `open_run` 接着打。
奖励里的金币/药水/遗物默认全拿，不算决策；宝箱遗物会真正进遗物栏（0.1.3 修复）。一局结束时列出全部遗物和牌组。`auto` 用的 AI 内部随机状态不随撤销回滚，撤销后再 `auto` 可能走出不同的路线。

测试：`python tools/mcp_e2e.py`（stdio）或 `python tools/mcp_e2e.py --http-url http://127.0.0.1:8765/mcp`。
