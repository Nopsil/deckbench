# 导出报告 / Export a report

[← 文档索引](INDEX.md) · [对比](COMPARE.md) · [校准](CALIBRATION.md) · [MCP](MCP.md)

把已经跑完的结果写成**一份 HTML 文件**。CSS 和 SVG 图表都写在文件里，没有要去加载的网络地址。双击用浏览器打开即可，不需要 DeckBench 还在运行。可以放进作品集。不新开模拟，不改种子，不改 AI。

*A finished result becomes one HTML file. The CSS and the SVG charts are in the file, and nothing in it asks the browser to load a network address. Double-click it to open it offline, without DeckBench running. It is meant to be shared in a portfolio. It does not start a simulation, and it does not change seeds or AI.*

一份文件里可以有这三段里的一段或几段：

- 一次已完成的测试（整局 `runs.jsonl`，或战斗实验的 `cells.csv` / `raw.jsonl`）。数字和报告页、`GET /api/runs/<id>/summary` 是同一套。单卡贡献的父任务另带一张表：每种牌是变体减去基线的胜率、掉血和回合，并标明样本太小或 Wilson 区间重叠。
- 两次已完成的战斗实验的对比。数字和 `GET /api/runs/compare` 是同一套：格子上的胜率、超时、回合、掉血、每回合输出，以及单卡使用和效率。
- 一份校准 JSON（`tools/calibrate.py --json` 或 `POST /api/calibrate`），以及由它算出的缺口分诊。已经分诊好的 JSON 也可以。

*One file can hold any of these, alone or together:*

- *One finished test (a full-run `runs.jsonl`, or a combat test's `cells.csv` / `raw.jsonl`). The numbers are the same as the report page and `GET /api/runs/<id>/summary`. A card-impact parent also includes a table: for each card, the variant minus the baseline for win rate, HP lost and turns, with a too-small or overlapping-Wilson flag.*
- *A comparison of two finished combat tests. The numbers are the same as `GET /api/runs/compare`: win rate, timeout, turns, HP loss and damage per turn per cell, plus per-card usage and efficiency.*
- *A calibration JSON (`tools/calibrate.py --json` or `POST /api/calibrate`), plus the gap triage computed from it. A triage JSON that was already written is accepted too.*

文案跟界面语言走：简体中文（zh-CN）、English、日本語、한국어。卡牌和遭遇的 ID 不翻译。

*The words follow the UI language: 简体中文 (zh-CN), English, 日本語, 한국어. Card and encounter ids are not translated.*

## 界面 / Pages

报告页（`#/report/<id>`）和运行页（`#/run/<id>`，测试已经完成时）有「导出报告」。对比页（`#/compare`）选好两次之后也有。点下去下载的就是这份 HTML。语言和侧栏里当前的选择一致。

*The report page (`#/report/<id>`) and the run page (`#/run/<id>`, once the test is done) have **Export report**. **Compare runs** (`#/compare`) has it after two tests are chosen. The download is this HTML file. The language is the one selected in the sidebar.*

## HTTP

`GET /api/runs/<id>/export.html`

`GET /api/runs/compare/export.html?a=<id>&b=<id>`

可选的查询参数 `calibration` 是允许目录里的一份校准 JSON 或分诊 JSON，写进同一份文件。`lang` 可以是 `zh-CN`、`en`、`ja`、`ko`（也认 `zhs` / `zh-CN` / `en-US` / `ja-JP` / `ko-KR`）。不写 `lang` 时用请求头 `x-lang`，和界面别的请求一样。

*Optional query `calibration` is a calibration JSON or a triage JSON in an allowed folder, included in the same file. `lang` may be `zh-CN`, `en`, `ja`, or `ko` (`zhs`, `zh-CN`, `en-US`, `ja-JP`, and `ko-KR` are accepted too). With no `lang`, the `x-lang` header is used, the same as the other UI requests.*

响应是 `Content-Type: text/html; charset=utf-8`，并带 `Content-Disposition` 文件名（`deckbench-run-….html` 或 `deckbench-compare-….html`）。

未知 id 是 404。还在跑是 409。已经取消、并且结果文件还在的测试可以导出，页面上写明是部分结果（`partial`）。没有结果文件是 404。对比的未知 id、同一个 id、重复或类型不对的参数是 400。校准路径在允许目录外、符号链接跳出去、超过 32MB、坏 JSON、不是校准也不是分诊，都是 400。正文是一句说明，没有堆栈。

*The response is `Content-Type: text/html; charset=utf-8`, with a `Content-Disposition` filename (`deckbench-run-….html` or `deckbench-compare-….html`).*

*An unknown id is 404. A test that is still running is 409. A cancelled test whose result files are still there can be exported, and the page says the result is partial. No result file is 404. For a comparison, an unknown id, the same id twice, or a repeated or wrong-typed parameter is 400. A calibration path outside an allowed folder, a symlink that escapes, a file over 32MB, broken JSON, or a file that is neither a calibration nor a triage is 400. The body is one sentence and has no stack trace.*

## 命令行 / Command line

```sh
python -m tools.export_report --run <id 或目录> --out report.html --lang zh-CN
python -m tools.export_report --a <id> --b <id> --out compare.html --lang en
python -m tools.export_report --run <id> --calibration calibration.json --out report.html
```

`--out -` 把 HTML 打到标准输出。不写 `--out` 时，文件落在界面数据目录的 `exports/`。成功时标准输出是文件路径。失败写到标准错误，退出码 2，没有堆栈。

*`--out -` prints the HTML on standard output. With no `--out`, the file is written under `exports/` in the GUI data directory. On success, standard output is the file path. On failure, the message goes to standard error, the exit code is 2, and there is no stack trace.*

路径规则和 `batch_run_summary` 相同：界面数据目录、DeckBench 缓存、`DECKBENCH_ANALYSIS_ROOTS`。存档树和 `.run` / `.save` 拒绝写入。

*Paths follow `batch_run_summary`: the GUI data directory, the DeckBench cache, and `DECKBENCH_ANALYSIS_ROOTS`. Writing into a save tree or a `.run` / `.save` file is refused.*

## MCP

`export_report(run, a, b, calibration, out, lang)` 返回 JSON。成功时 `path` 是写好的 HTML。`--import-only` 也提供这个工具。失败是 `{"ok": false, "error": "..."}`，例如 `need_input`、`bad_type`、`bad_lang`、`missing`、`no_result`、`not_calibration`、`path_not_allowed`、`refuse_write`、`not_found`、`not_done`。

*`export_report(run, a, b, calibration, out, lang)` returns JSON. On success, `path` is the HTML file that was written. `--import-only` exposes this tool too. A failure is `{"ok": false, "error": "..."}`, for example `need_input`, `bad_type`, `bad_lang`, `missing`, `no_result`, `not_calibration`, `path_not_allowed`, `refuse_write`, `not_found`, or `not_done`.*
