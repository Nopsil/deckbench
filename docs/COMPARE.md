# 对比两次战斗实验 / Compare two combat tests

[← 文档索引](INDEX.md) · [MCP](MCP.md)

已经跑完的两次战斗实验可以按格子和按卡看差值。差值是 B 减 A。不新开模拟，不改种子，也不改 AI。

*Two finished combat tests can be compared per cell and per card. A delta is B minus A. This does not start a simulation, and it does not change seeds or AI.*

单卡 A/B 页（`#/ab`，`GET /api/ab`）仍然是整局或格子胜率的配对对照。这一页专门看战斗实验的格子指标和单卡使用、效率。

*The single-card A/B page (`#/ab`, `GET /api/ab`) is still the paired win-rate comparison. This page is the combat-test cell metrics and the per-card usage and efficiency.*

## 界面 / Page

侧栏「对比两次」（`#/compare`）。只列出已完成的战斗实验。选基线 A 和改过的 B。历史页里勾选两次之后，「格子差值」打开同一页。

表上每一行是一个格子的一项指标：胜率、超时、平均回合、掉血、每回合输出。下面一张表是单卡的每场使用次数和效率倍数。绿色是有利的方向（胜率、每回合输出、效率更高；超时、回合、掉血更低；单卡使用次数是 B 打得更多）。红色是相反的方向。星号表示 5% 的检验看出了差别。任一侧少于 30 场时，数字仍在，并标成样本太小。

*The sidebar entry is **Compare runs** (`#/compare`). The lists contain finished combat tests only. Pick baseline A and changed run B. On History, checking two rows and choosing **Cell deltas** opens the same page.*

*Each row is one metric of one cell: win rate, timeout, average turns, HP loss, damage per turn. A second table is uses per fight and efficiency. Green is the favorable direction (higher win rate, damage per turn and efficiency; lower timeout, turns and HP loss; card usage is green when B plays the card more). Red is the other direction. A star means the 5% test found a difference. Below 30 fights on either side, the numbers stay and the row is marked too small to conclude.*

## HTTP

`GET /api/runs/compare?a=<id>&b=<id>`

`a` 和 `b` 是界面里一次测试的 id。未知 id、同一个 id、缺了参数、同一个参数写了两次，都是 400，正文是一句说明，没有堆栈。两次都要已完成，而且都是战斗实验。

*`a` and `b` are GUI test ids. An unknown id, the same id twice, a missing parameter, or the same parameter twice is a 400 with one sentence and no stack trace. Both tests must be finished combat tests.*

返回的 `cells[].metrics` 里，每一项有 `a`、`b`、`delta`（B − A）、`method`、`p_value`、`significant`。胜率和超时的 `method` 是 `two_proportion_z`，比例在 0 到 1 之间，并带 Wilson 区间和 `wilson_overlap`（两个区间重叠则为 true）。`significant` 为 true 表示双侧 p < 0.05。平均回合、`hp_loss`、`dpt` 在有逐场记录时 `method` 是 `welch`；只有 `cells.csv` 的平均数时 `method` 是 `means_only`，`significant` 为 null。

`cards[]` 有 `usage_delta`（每场使用，B − A）和 `efficiency_delta`（效率倍数，B − A）。使用次数在有逐场记录时同样用 Welch。效率倍数是合计伤害和格挡之后的比值，和报告里的 `cards.csv` 同一公式，只给差。

*In `cells[].metrics`, each entry has `a`, `b`, `delta` (B − A), `method`, `p_value` and `significant`. Win rate and timeout use `two_proportion_z`. Those rates are fractions from 0 to 1, with Wilson intervals and `wilson_overlap` (true when the two intervals overlap). `significant` is true when the two-sided p-value is below 0.05. Average turns, `hp_loss` and `dpt` use `welch` when every fight was recorded. When only the averages in `cells.csv` exist, `method` is `means_only` and `significant` is null.*

*`cards[]` has `usage_delta` (uses per fight, B − A) and `efficiency_delta` (efficiency, B − A). Usage uses Welch when per-fight counts were recorded. Efficiency is the ratio of total damage and block, the same formula as `cards.csv` in the report, and only the delta is returned.*

数字来自 `sts2sim/stats.py`（Wilson、两比例 z 检验、Welch）和 `sts2sim/runcompare.py`。探针房间的单卡不计入，和战斗报告一致。

*The numbers come from `sts2sim/stats.py` (Wilson, the two-proportion z-test, Welch) and `sts2sim/runcompare.py`. Cards played only in a probe room are left out, matching the combat report.*

两套牌的 id 不一样时，同一个（卡组，幕，房间）对不上。这时如果这一幕、这一房间在每一侧都只有一套牌，就按幕和房间配对，格子上写成「A 的卡组 / B 的卡组」。这一侧有不止一套牌就不配，避免猜错。组牌对打走的就是这条，见 [DECKS.md](DECKS.md)。同一套牌的对比仍按卡组 id 对齐，数字不变。

*When the deck ids differ, no (deck, act, room) key is shared. If that act and room has one deck on each side, the cells line up by act and room and the deck column reads "A's deck / B's deck". A side with more than one deck in that cell is left unpaired, so nothing is guessed. Deck head-to-head uses this path. See [DECKS.md](DECKS.md). A comparison of the same deck id still lines up by deck id, and those numbers stay the same.*

## MCP

`compare_runs(a, b)` 返回同一份 `cells` 和 `cards`。`a`、`b` 可以是界面测试 id，或结果目录，或其中的 `raw.jsonl` / `cells.csv`。路径规则和 `batch_run_summary` 相同。`--import-only` 也提供这个工具。失败是 JSON：`{"ok": false, "read_only": true, "error": "..."}`，例如 `same_run`、`bad_type`、`not_found`、`not_done`、`not_combat`、`no_data`、`not_json`。

*`compare_runs(a, b)` returns the same `cells` and `cards`. `a` and `b` may be a GUI test id, a result directory, or a `raw.jsonl` / `cells.csv` inside one. Paths follow `batch_run_summary`. `--import-only` exposes this tool too. A failure is JSON: `{"ok": false, "read_only": true, "error": "..."}`, for example `same_run`, `bad_type`, `not_found`, `not_done`, `not_combat`, `no_data` or `not_json`.*
