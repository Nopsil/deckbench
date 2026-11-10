# 结果包 / Run bundles

[← 文档索引](INDEX.md) · [导出报告](EXPORT.md) · [对比](COMPARE.md) · [MCP](MCP.md)

把已经跑完的结果打成**一个 `.deckbench.zip`**，拷到另一台机器，再导入。导入之后出现在测试列表里，也能参与对比。不新开模拟，不改种子，不改 AI。包里的文件只当数据来读，**不会执行**。

*A finished result becomes one `.deckbench.zip`. Copy it to another machine and import it. The imported tests show up in the run list and can be compared. It does not start a simulation, and it does not change seeds or AI. Files in the bundle are data. Nothing in the bundle is executed.*

## 包里有什么 / What is in the file

清单是 `manifest.json`：

- `format` 固定是 `deckbench.bundle`
- `schema` 当前是 `1`
- `deckbench` 是打包时的 `sts2sim.__version__`
- `kind` 是 `run`、`compare`、`head_to_head` 或 `card_impact`
- `runs` 是包里的测试编号，按这个顺序
- `files` 列出其余每个文件的相对路径、字节数和 SHA-256

*The manifest is `manifest.json`:*

- *`format` is `deckbench.bundle`*
- *`schema` is `1`*
- *`deckbench` is `sts2sim.__version__` at the time the zip was written*
- *`kind` is `run`, `compare`, `head_to_head`, or `card_impact`*
- *`runs` lists the test ids, in that order*
- *`files` lists every other file: relative path, size in bytes, and SHA-256*

其余文件：

- `report.html`：和「导出报告」同一份离线 HTML（见 [EXPORT.md](EXPORT.md)）。CSS 和 SVG 都在文件里。
- `runs/<id>/meta.json`：这次测试的记录。命令行 `argv` 不放进包。
- `runs/<id>/raw.jsonl`：战斗实验的逐场记录。整局测试则是 `runs/<id>/runs.jsonl`。
- `runs/<id>/preset.yaml`：这次用过的牌组预设。没有预设就省略。这是一份 YAML 文本，导入时不解析、不装进可运行的预设目录。
- `runs/<id>/card_impact.json`：单卡贡献的结果表。只有这种任务才有。

*The other files:*

- *`report.html`: the same offline HTML as Export report (see [EXPORT.md](EXPORT.md)). The CSS and the SVG charts are in the file.*
- *`runs/<id>/meta.json`: the test record. The command line `argv` is left out.*
- *`runs/<id>/raw.jsonl`: every fight of a combat test. A full run uses `runs/<id>/runs.jsonl` instead.*
- *`runs/<id>/preset.yaml`: the deck preset that test used, when it had one. It is YAML text. Import does not parse it and does not install it as a runnable preset.*
- *`runs/<id>/card_impact.json`: the card-impact table. Only that kind of job has it.*

单卡贡献的包里，第一个编号是父任务，后面是每个变体。对比和对打的包里是两场战斗实验。对打（两边都标了 `shared_plan`）的 `kind` 是 `head_to_head`，文件布局和对比相同。

*In a card-impact bundle the first id is the parent and the rest are the variants. A compare bundle and a head-to-head bundle each hold two combat tests. A head-to-head (both sides stored `shared_plan`) uses `kind` `head_to_head` and the same layout as a compare.*

版本号只作记录。换了一版 DeckBench 仍然能导入，只要 `schema` 还是 1。`schema` 不是 1 时拒绝，说明里写明当前只读 schema 1。

*The version is recorded, not a gate. A bundle from another DeckBench release still imports while `schema` is 1. Any other schema is refused, and the message says this DeckBench only reads schema 1.*

## 界面 / Pages

历史页有「导入结果包」。运行页（测试已经结束时）、报告页和对比页（选好两次之后）有「下载结果包」。点下去得到的就是这个 zip。

*History has **Import bundle**. The run page (once the test has finished), the report page, and **Compare runs** (after two tests are chosen) have **Download bundle**. The download is this zip.*

导入之后，测试带 `imported: true` 和 `origin`：来源是 `bundle`，打包时的 DeckBench 版本，原来的编号，导入时间，以及上传的文件名。状态仍是原来的 `done` 或 `cancelled`，所以列表和对比跟本地测试一样。原来的编号已经在用时，换一个新编号，界面会说明。

*After import, the test has `imported: true` and `origin`: source `bundle`, the DeckBench version that packed it, the original id, the import time, and the uploaded file name. The status stays `done` or `cancelled`, so the list and compare treat it like a local test. When the original id is already in use, the copy gets a new id, and the page says so.*

## HTTP

`GET /api/runs/<id>/bundle`

`GET /api/runs/compare/bundle?a=<id>&b=<id>`

`POST /api/bundles/import`，表单字段 `file` 是这个 zip。

可选的查询参数 `lang` 决定包里那份 HTML 的语言，取值和导出报告相同（`zh-CN`、`en`、`ja`、`ko`）。不写时用请求头 `x-lang`。

*Optional query `lang` chooses the language of the HTML inside the zip, the same values as the report export (`zh-CN`, `en`, `ja`, `ko`). With no `lang`, the `x-lang` header is used.*

下载的响应是 `Content-Type: application/zip`，并带 `Content-Disposition` 文件名（`deckbench-run-….deckbench.zip`、`deckbench-compare-….deckbench.zip`、`deckbench-h2h-….deckbench.zip` 或 `deckbench-impact-….deckbench.zip`）。

导入成功时正文是 JSON：`ok`、`kind`、`schema`、`deckbench`，以及 `runs`（`id`、`original_id`、`kind`、`renamed`、`imported`）。

*A download is `Content-Type: application/zip`, with a `Content-Disposition` filename (`deckbench-run-….deckbench.zip`, `deckbench-compare-….deckbench.zip`, `deckbench-h2h-….deckbench.zip`, or `deckbench-impact-….deckbench.zip`).*

*A successful import is JSON: `ok`, `kind`, `schema`, `deckbench`, and `runs` (`id`, `original_id`, `kind`, `renamed`, `imported`).*

未知 id 是 404。还在跑是 409。没有结果文件是 404。同一个 id、不是战斗实验、重复或类型不对的参数是 400。哈希对不上、清单无效、多出来的文件、缺了必要文件、schema 不是 1、路径里有 `..` 或绝对路径或反斜杠、单个文件超过 16MB、整个包超过 32MB，都是 400。正文是一句说明，没有堆栈。

*An unknown id is 404. A test that is still running is 409. No result file is 404. The same id twice, a test that is not a combat test, or a repeated or wrong-typed parameter is 400. A hash that does not match, an invalid manifest, an extra file, a missing required file, a schema other than 1, a path with `..` or an absolute path or a backslash, a member over 16MB, or a bundle over 32MB is 400. The body is one sentence and has no stack trace.*

## MCP

`export_bundle(run, a, b, out, lang)` 返回 JSON。成功时 `path` 是写好的 zip。`out` 留空则写到界面数据目录的 `exports/`。`--import-only` 也提供这个工具。

`import_bundle(path)` 读允许目录里的一个 zip，返回导入的测试编号。路径规则和 `batch_run_summary` 相同。失败是 `{"ok": false, "error": "...", "message": "..."}`。`message` 是一句说明。schema 不对时 `error` 是 `schema`，`message` 里写明当前只读 schema 1。

*`export_bundle(run, a, b, out, lang)` returns JSON. On success, `path` is the zip that was written. With no `out`, the file is written under `exports/` in the GUI data directory. `--import-only` exposes this tool too.*

*`import_bundle(path)` reads a zip in an allowed folder and returns the imported test ids. Paths follow `batch_run_summary`. A failure is `{"ok": false, "error": "...", "message": "..."}`. `message` is one sentence. An incompatible schema has `error` `schema`, and `message` says this DeckBench only reads schema 1.*

失败码还有 `hash`、`zip_slip`、`too_big`、`manifest`、`not_bundle`、`extra`、`incomplete`、`not_found`、`not_done`、`no_result`、`path_not_allowed`、`refuse_write`。不留下半截目录。

*Other failure codes are `hash`, `zip_slip`, `too_big`, `manifest`, `not_bundle`, `extra`, `incomplete`, `not_found`, `not_done`, `no_result`, `path_not_allowed`, and `refuse_write`. A failed import does not leave a partial run folder.*
