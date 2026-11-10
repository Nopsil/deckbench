# 校准 / Calibration

[← 返回 README](../README.md) · [文档索引](INDEX.md) · [存档格式](SAVE_FORMAT.md) · [MCP](MCP.md)

把一份已经打完或正在打的真对局，和**同一颗种子、同一个角色、同一个进阶、同一条选牌路径**上的模拟局比每场战斗掉了多少血。不新开模拟，不改存档。实现在 `sts2sim/calibrate.py`，命令行是 `tools/calibrate.py`。

*Compare one imported run with simulations that share its seed, character, ascension and card-pick path. It does not start a simulation and does not modify saves. The implementation is `sts2sim/calibrate.py`; the command is `tools/calibrate.py`.*

## 命令行 / Command line

```bash
python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl
python tools/calibrate.py path/to/history/123.run path/to/runs.jsonl --json -
python tools/calibrate.py path/to/current_run.save path/to/run_dir --json /tmp/calibration.json
```

- 第一个参数是一份 `.run` 或 `current_run.save`（读法和 `python tools/import_run.py` 相同，走 `saveimport.load_path`）。目录不行，返回 `one_run`。
- 第二个参数是 `runs.jsonl`，或里面有这个文件的目录。命令行**不**限制这个路径必须在允许目录里。HTTP 和 MCP 会限制，见下面。
- 不写 `--json` 时，标准输出是 `render_text` 的文本。`--json -` 只打 JSON。`--json <路径>` 把同一份 JSON 写到那个文件，标准输出仍是文本。输出路径若会写进存档树、覆盖刚读的文件，或写成 `.run` / `.save`，`refuse_save_write` 拒绝，退出码 2。
- `--lang` 是错误信息的语言：`zhs`（默认）、`en`、`ja`、`ko`。失败时退出码 2。`--json -` 时错误 JSON 打在标准输出，说明打在标准错误。

*The first argument is one `.run` or `current_run.save` (the same reader as `import_run`). A folder is `one_run`. The second is `runs.jsonl` or a directory that contains it. The CLI does not require that sim path to sit in an allowed directory; HTTP and MCP do. Without `--json`, stdout is the text report. `--json -` prints only JSON. `--json <path>` writes that JSON and still prints the text. A destination inside a save tree, on top of the file just read, or named `.run` / `.save` is refused (`refuse_save_write`) and the process exits 2. `--lang` is `zhs` (default), `en`, `ja` or `ko`.*

夹具里的 ID 是虚构的，不需要游戏安装。

## 哪些模拟局留在样本里 / Which simulated runs stay in the sample

种子用 `sts2sim/engine/seed.py` 的 `canonicalize`：转大写、`O`→`0`、`I`→`1`、去首尾空格。空字符串不算有种子。

角色看模拟行的 `char` 和 `character`（两个都写了就必须收成同一个）。五个原版名字 `Ironclad`、`Silent`、`Defect`、`Necrobinder`、`Regent` 原样保留；`IRONCLAD`、`THEIRONCLAD` 这类也会收成这五个。认不出的名字留下最后一个点后面的那段。真对局用玩家的 `sim_character` 或 `character`，和局里的 `sim_character` 冲突时是 `no_character`。

进阶看 `asc` 和 `ascension`（两个都写了就必须是同一个整数）。布尔、`1.5` 这种非整数、对不上的两个字段，都不算整数。缺了进阶字段的存档经 `load_path` 导入后是 **0**（`saveimport.normalize` 里 `_int(...) or 0`），不是错误码 `no_ascension`。`no_ascension` 只出现在内存里的对局对象上，`ascension` 不是整数的时候。

选牌路径是真机每一层 `was_picked is True` 的牌，去掉 `CARD.` 前缀，按层排成一段。另一位玩家的牌（`player_id` 对不上）不算。模拟行的 `picked` 必须整段相同：多一张、少一张、或顺序不同都是 `deck_path`。`picked` 是空列表表示「没选牌」，这是一条合法路径。缺了 `picked` 字段则这条路径未知，不能拿来凑。

多人局（`players` 不止一位）是 `multiplayer`，不猜测是哪一位。没有种子是 `no_seed`，没有角色是 `no_character`。

一行模拟被排除的原因记在结果的 `excluded` 里，键只有这些，有计数才出现：`seed`、`character`、`ascension`、`deck_path`、`sim_error`（行上带 `error`）、`not_a_run`、`bad_combat`（`combats` 读不出来）。

*Seeds go through `canonicalize` (uppercase, `O`→`0`, `I`→`1`, trim). Character reads `char` and `character`; if both are set they must map to one name. The five vanilla names stay as written; `IRONCLAD` and `THEIRONCLAD` map to them; anything else keeps the segment after the last dot. Ascension reads `asc` and `ascension` and both must be the same integer. A bool or a non-integer such as `1.5` is not an integer. A save with no ascension field imports as **0**, not `no_ascension` (that code is for an in-memory run whose `ascension` is not an integer). The pick path is the ordered cards with `was_picked is True`, with a `CARD.` prefix removed. Another player's picks are ignored. `picked` must be that same sequence; an empty list means no card was taken, and a missing `picked` field is not a path. More than one player is `multiplayer`. `excluded` counts dropped sim rows under `seed`, `character`, `ascension`, `deck_path`, `sim_error`, `not_a_run` and `bad_combat`.*

## 一场战斗怎么对上 / How one fight matches

真机这一层要能定成唯一的战斗房：`Monster`、`Elite` 或 `Boss`，并且恰好一个遭遇 ID。房间字符串会去掉最后一个点之前的部分，再只留字母、转小写。所以 `Room.Elite` 和 `elite` 都是 `Elite`。认得的别名：

| 写成 | 收成 |
| --- | --- |
| `monster` | Monster |
| `elite` | Elite |
| `boss` | Boss |
| `ancient` | Ancient |
| `restsite`、`rest` | RestSite |
| `shop`、`merchant` | Shop |
| `treasure` | Treasure |
| `unknown`、`unassigned` | Unknown |
| `event` | Event |

`Combat` 这种含糊名字不映射。一层上出现两种战斗房，或地图类型是商店 / 休息点 / 事件 / 宝箱 / 远古而房间里又有一场战斗，是 `ambiguous_floor`，不用其中一间去凑。一层上有两个不同的遭遇 ID 是 `ambiguous_encounter`。

遭遇 ID 会去掉 `ENCOUNTER.` 前缀。`EVENT.`、`ACT.`、以及 `NONE` / `NONE.NONE` / `NULL` / `?` / `UNKNOWN` 不算遭遇。没有遭遇 ID 的战斗房是 `missing_encounter`。休息点、商店、宝箱、事件、远古是 `not_a_fight`，不参加掉血比较。

模拟里同一场的写法有两种：

- 对象：`floor`、`room` 或 `room_type`、`encounter`、`hp_lost`。幕用 `act_index`；只有 `act` 时用 `act`。两个都写了但整数不同，整行 `combats` 算 `bad_combat`。
- 数组（整局 `runs.jsonl` 的写法，`sts2sim/engine/run.py` 记的那一串）：下标 0 层、1 房间、2 遭遇、4 掉血；长度大于 6 时下标 6 是幕序号。下标 3（回合数）、5（是否打赢）、7（循环警报）校准不读。

模拟这场没有写幕（`act` 是空）时，仍可以和真机对上。写了幕且和真机 `act_index` 不同，这一条不用；样本里每条都因此对不上时，原因是 `act_mismatch`。同一层、同一房间、同一遭遇在一条模拟局里出现不止一次，是 `ambiguous_sim`。掉血不是有限数字（布尔、字符串、NaN）时，这条模拟的掉血当没写，原因可以是 `sim_hp_missing`。

没有任何一条模拟留在样本里时，每个战斗层用同一个原因：`no_sim_rows`、`sim_error`、`not_a_run`、`seed`、`character`、`ascension`、`deck_path` 或 `bad_combat`。有样本但这一层对不上时，原因按出现次数；次数打平则按固定顺序：`ambiguous_sim`、`encounter_mismatch`、`room_mismatch`、`act_mismatch`、`missing_encounter`、`sim_hp_missing`、`no_sim_fight`。不改用旁边的层或别的遭遇来凑。

*A real floor matches only when it is exactly one of Monster / Elite / Boss and exactly one encounter id. `Room.Elite` and `elite` both become `Elite`. The name `Combat` is not mapped. Two combat rooms, or a shop / rest / event / treasure / ancient map point that also has a combat room, is `ambiguous_floor`. Two encounter ids is `ambiguous_encounter`. An `EVENT.` or `ACT.` id, or `NONE` / `NULL` / `?` / `UNKNOWN`, is not an encounter. Rest, shop, treasure, event and ancient floors are `not_a_fight`. A sim fight is a dict (`floor`, `room` or `room_type`, `encounter`, `hp_lost`, and `act_index` or `act`) or the list the full-run engine writes: index 0 floor, 1 room, 2 encounter, 4 HP lost, and index 6 the act when present. A sim fight with no act still matches. A sim fight whose act disagrees does not; if every row fails that way the reason is `act_mismatch`. A bool, string or NaN HP loss is missing. When several reasons tie, the fixed order above wins. Another floor is never used to fill a gap.*

界面上这些原因用 `gui/locales/zhs.json` 的 `cal.reason.*`：

| `reason` | 简体中文 |
| --- | --- |
| `unknown_floor` | 这一层读不出来 |
| `ambiguous_floor` | 这一层的房间类型不清楚 |
| `ambiguous_encounter` | 这一层有不止一个遭遇 |
| `missing_encounter` | 没有遭遇 ID |
| `no_sim_fight` | 模拟里没有这一层的战斗 |
| `ambiguous_sim` | 模拟里有不止一场对得上 |
| `encounter_mismatch` | 遭遇对不上 |
| `room_mismatch` | 房间对不上 |
| `act_mismatch` | 幕对不上 |
| `sim_hp_missing` | 模拟没有记下掉血 |
| `ambiguous_hp` | 真机掉血无法确定 |
| `missing_hp` | 真机没有记下掉血 |
| `no_sim_rows` | 没有模拟局 |
| `sim_error` | 模拟行是错误 |
| `not_a_run` | 不是一局模拟 |
| `seed` | 种子不同 |
| `character` | 角色不同 |
| `ascension` | 进阶不同 |
| `deck_path` | 选牌路径不同 |
| `bad_combat` | 模拟战斗读不出来 |

## 掉血数字 / HP-lost numbers

对得上的层，`status` 是 `compared`。`sim_n` 是用了几条模拟掉血。`mean` 是算术平均。`p5`、`p10`、`p90`、`p95` 是线性插值：排序后的下标 = 百分数 / 100 × (n − 1)；只有一条时就是那个数。结果里的 `sim_percentile_method` 是 `linear`。

真值的 `percentile` 是 midrank：`100 × (小于真值的个数 + 0.5 × 等于真值的个数) / n`。`percentile_method` 是 `midrank`。

真值 **小于** `p5` 或 **大于** `p95` 时，`outside_p5_p95` 和 `likely_sim_gap` 都是 true。落在两端点上不算外面。`gap_band` 是 `[5, 95]`。`gaps` 是这些层的层号。对不上的层号在 `unmatched` 里。

*A compared fight reports `sim_n`, the arithmetic `mean`, and linear `p5` / `p10` / `p90` / `p95` (`index = percent/100 × (n−1)`; one sample is that sample). `percentile` is the midrank `100 × (count below + 0.5 × count equal) / n`. `likely_sim_gap` is true only when the real value is strictly outside p5–p95.*

## JSON 里有什么 / What the JSON contains

成功时 `ok` 和 `read_only` 都是 true，`v` 是 1。紧接在 `v` 后面是 `real_path` 和（除了上传）`sim_path`。还有 `seed`、`character`、`ascension`、`deck_path`、`deck_path_rule`（固定 `exact_picked_cards`）、`alignment`（固定 `floor_room_encounter`）、上面的百分位字段、`sim_rows`、`sim_matched`、`excluded`、`gaps`、`unmatched`、`fights`。

每一场有 `floor`、`act_index`、`room`、`encounter`、`status`（`compared` / `unmatched` / `not_a_fight`）、`reason`、`real_hp_lost`。对得上的场再加 `sim_n`、`mean`、`p10`、`p90`、`p5`、`p95`、`percentile`、`outside_p5_p95`、`likely_sim_gap`。对不上的场这些模拟数字是 null，`likely_sim_gap` 是 false。

## 界面和 HTTP / GUI and HTTP

侧栏「校准」是 `#/calibrate`（`gui/web/src/pages/Calibrate.vue`）。`#/calibrate?real=<路径>&sim=<路径>` 会填上这两个值；两个都有就立刻比较。

- `POST /api/calibrate`，正文 `{"real","sim"}`。`sim` 必须在允许目录里，规则和 MCP `batch_run_summary` 相同（界面数据目录、DeckBench 缓存、`DECKBENCH_MCP_RUNS`、`DECKBENCH_ANALYSIS_ROOTS`）。`real` 是一份对局文件，不走那份允许目录名单。
- `POST /api/calibrate/upload`，表单字段 `real` 和 `file`。`file` 是 jsonl 正文，只在内存里读，不要求先落在允许目录。返回的 `sim_path` 只是上传文件名，不是磁盘路径。空行跳过；一行必须是一个 JSON 对象。超过 32MB（`saveimport.MAX_BYTES`）拒绝。
- `GET /api/calibrate/reals` 只列 `discover()` 找到的 `history/*.run`、`current_run.save`、`current_run_mp.save` 的路径，不读内容。最多 200 条，多出来 `truncated` 为 true。
- `GET /api/calibrate/sims` 只列允许目录里名为 `runs.jsonl` 的文件。目录遍历不跟随符号链接，解析后跳出去的路径也不收，并且不创建目录。跳过名为 `saves`、`history`、`SlayTheSpire2`、`node_modules`、`.git`、`__pycache__` 以及点开头的目录。目录深度达到 6 就不再进入子目录（这一层里的 `runs.jsonl` 仍会列出）。同样最多 200 条。

失败是 HTTP 400，正文没有堆栈。校准自己的码：`need_real`、`need_sim`、`one_run`、`multiplayer`、`no_seed`、`no_character`、`no_ascension`、`not_found`。读存档的错误和导入接口同一套；模拟路径不被允许、符号链接跳出去、坏 JSONL，和只读分析同一套（`path_not_allowed`、`not_json`、`too_big` 等）。

表的列是层、房间、遭遇、真机掉血、mean、p10、p90、百分位、是否疑似缺口、模拟区间。色条是 p10–p90，细线是 p5–p95，圆点是真值（`cal.legend`）。疑似缺口的行高亮。`unmatched` 和 `not_a_fight` 是灰色，并写明原因。卡牌和遭遇 ID 不进翻译表，原样显示。

*Sidebar **Calibration** is `#/calibrate`. `#/calibrate?real=&sim=` fills both and compares when both are set. `POST /api/calibrate` takes `{"real","sim"}`; `sim` must sit in an allowed directory (the same roots as `batch_run_summary`) and `real` is one run file. `POST /api/calibrate/upload` reads the jsonl in memory (32MB cap) and sets `sim_path` to the upload name only. `GET /api/calibrate/reals` and `GET /api/calibrate/sims` list paths only, 200 at most. The strip draws p10–p90 as the band, p5–p95 as the thin line, and the real value as the mark. Unmatched and not-a-fight rows are grey.*

## MCP / MCP

`calibrate(real, sim)` 返回和上面相同的 JSON 文本。失败也是 JSON（`ok: false`），不抛异常。`sim` 受允许目录限制；`real` 的读法和 `import_save` 相同。`python tools/mcp_server.py --import-only` 也提供这个工具。不新开模拟，不写文件。

*MCP `calibrate(real, sim)` returns the same JSON, including `ok: false` on failure. It is on `--import-only`. The sim path is restricted; `real` is read like `import_save`.*

## 缺口分诊 / Gap triage

`python tools/gap_triage.py` 读一份或多份上面的校准 JSON（`tools/calibrate.py --json` 写下的那种），把 `likely_sim_gap` 按遭遇 ID、以及这场遭遇涉及到的敌人能力 / 机制汇总。不新开模拟，不改种子，不改 AI，也不改校准 JSON。

*Gap triage reads one or more calibration JSON files (what `tools/calibrate.py --json` writes) and totals `likely_sim_gap` by encounter id and by the enemy power or mechanic involved. It does not start a simulation, and it does not change seeds, AI, or the calibration JSON.*

```bash
python tools/calibrate.py tests/fixtures/calibrate/real.run tests/fixtures/calibrate/sims.jsonl --json /tmp/calibration.json
python tools/gap_triage.py /tmp/calibration.json
python tools/gap_triage.py a.json b.json --catalog tests/fixtures/gap_triage/catalog.json --out triage.md
python tools/gap_triage.py tests/fixtures/gap_triage --catalog tests/fixtures/gap_triage/catalog.json --json -
```

- 一场战斗要 `status` 是 `compared` 才进分母。`unmatched` 和 `not_a_fight` 只计数，不参与排名。
- `likely_sim_gap` 为真，并且真机掉血 **高于** 这一场的 `p95`：模拟偏乐观（真机掉得更多）。**低于** `p5`：模拟偏悲观（真机掉得更少）。落在 `p5` 或 `p95` 上不算外面；标记为真但数字对不上时，方向记成不明，不进两侧的排名。
- 同一遭遇在多份报告里的对上的场次相加。排名先看这一侧的场次 / 对上的场次，再看场次，最后看 ID。`--min-compared`（默认 1）少于此数的遭遇不进排名。`--top`（默认 10）只截 Markdown，JSON 仍是完整排名。
- 能力从三处拼，同名只留一次：`--catalog` 名册、报告里 `real_path` 还读得开时那份真对局的 `monster_ids`、以及本机已经导出的怪物 / 遭遇数据（没有就跳过，不报错）。`sts2sim/enemies.py` 里写好的 `ENCOUNTER_SETUP` / `ROTATING_START` 会标成开场字段机制。`BACK_ATTACK_LEFT` / `BACK_ATTACK_RIGHT` 额外标成「后方攻击始终按背后结算」。
- 名册是一份 JSON 对象。`encounters` 和 `monsters` 的值可以带 `powers`、`mechanics`、`monsters`。能力 ID 用引擎里的写法，例如 `CONSTRICT`、`THORNS`。机制名用 `summon_skipped`、`status_card`、`conditional_branch`、`encounter_setup`、`rotating_start`、`back_attack_always`。夹具 `tests/fixtures/gap_triage/` 里的遭遇 ID 是虚构的。
- Markdown 里每个能力指向实现它的类：敌人专属能力在 `sts2sim/powers_enemy.py`，双方都会用到的（含荆棘）在 `sts2sim/powers.py`，意图、召唤不生成新敌人、Status 塞晕眩和开场字段在 `sts2sim/enemies.py`。名册里有、源码里没有的能力，指向 `enemies.py` 里「没实现就只记层数」的 `take_turn`。荆棘再加一条 `sts2sim/ai/base.py` 的 `mechanic_adjust`（可选，默认关；开关在 `sts2sim/ai/heuristic.py` 的 `mechanic_aware`）。
- 目录参数只读这一层的 `*.json`。不是校准报告的对象跳过；坏 JSON、找不到的路径、写成 `.run` / `.save` 的输出，退出码 2。`--json -` 只打汇总 JSON。`--json <路径>` 写 JSON，标准输出仍是 Markdown。

*A fight counts only when `status` is `compared`. `unmatched` and `not_a_fight` are counted and are not ranked. `likely_sim_gap` with real HP lost above that fight's `p95` means the sim was too optimistic (the real fight lost more). Below `p5` means too pessimistic (the real fight lost less). A value on `p5` or `p95` is not outside. A flag whose numbers do not decide a side is an unknown direction and is left out of both rankings. Fights for one encounter add across reports. Rank is that side's fights over compared fights, then the count, then the id. `--min-compared` (default 1) leaves smaller encounters out of the ranking. `--top` (default 10) trims the Markdown only; the JSON keeps the full ranking. Powers are the union of the `--catalog` file, monster ids on a `real_path` that can still be read, and a local monster/encounter export when one is present (missing data is skipped). `ENCOUNTER_SETUP` / `ROTATING_START` in `sts2sim/enemies.py` are tagged as start-flag mechanics. `BACK_ATTACK_LEFT` / `BACK_ATTACK_RIGHT` are also tagged as back attack always counting as from behind. The catalog is one JSON object; `encounters` and `monsters` may list `powers`, `mechanics` and `monsters`. Power ids are the engine ids, such as `CONSTRICT` and `THORNS`. Mechanic names are `summon_skipped`, `status_card`, `conditional_branch`, `encounter_setup`, `rotating_start` and `back_attack_always`. Encounter ids in `tests/fixtures/gap_triage/` are fictional. The Markdown points each power at the class that implements it: enemy-only powers in `sts2sim/powers_enemy.py`, powers used on either side (including Thorns) in `sts2sim/powers.py`, and intents, summon-not-adding-enemies, Status-adds-Dazed and start flags in `sts2sim/enemies.py`. A catalog power with no class points at `take_turn` in `enemies.py`, where an unimplemented power only stores stacks. Thorns also points at `mechanic_adjust` in `sts2sim/ai/base.py` (optional, off by default; the switch is `mechanic_aware` in `sts2sim/ai/heuristic.py`). A directory argument reads `*.json` in that directory only. A JSON object that is not a calibration report is skipped. Broken JSON, a missing path, or an output named `.run` / `.save` exits 2. `--json -` prints only the summary JSON. `--json <path>` writes that JSON and still prints the Markdown.*
