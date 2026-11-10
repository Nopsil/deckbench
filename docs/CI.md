# 持续集成 / Continuous integration

[← 返回 README](../README.md) · [文档索引](INDEX.md) · [覆盖率快照](COVERAGE.md) · [测试](DEVELOPER.md#测试--tests)

GitHub Actions 工作流在 `.github/workflows/ci.yml`，名字是 `CI`。推送到 `main` 和任意 pull request 都会跑。`contents` 权限是只读。同一分支上新的一次运行会取消还没跑完的那次。这里不改工作流文件，只记下它现在做什么。

*The workflow file is `.github/workflows/ci.yml`, named `CI`. It runs on a push to `main` and on every pull request, with read-only `contents`. A newer run on the same ref cancels the one still going. This page describes that file; it does not change it.*

这个工作流不准备游戏安装，所以要本机游戏或本机生成缓存的测试仍会跳过。它不上传覆盖率，也没有发布步骤。

## ruff

作业 `ruff` 在 `ubuntu-latest` 上跑，限时 15 分钟。Python 3.12，安装的是 `ruff==0.17.4`，然后执行 `ruff check .`。

规则在 `ruff.toml`：`target-version` 是 `py311`，`preview` 关掉，用 ruff 的默认规则集。已经存在的问题按文件写在 `lint.per-file-ignores` 里，所以当前树不用为了这些旧问题改写。没有列进这张表的文件按全套规则检查；某个文件没有列出的规则码仍然会失败。文件头写明不要再加一条全局 `lint.ignore`。

本地同样是：

```bash
python -m pip install ruff==0.17.4
ruff check .
```

*Job `ruff` uses `ubuntu-latest`, Python 3.12, `ruff==0.17.4`, and `ruff check .`, with a 15 minute limit. `ruff.toml` sets `target-version = "py311"`, turns preview off, and keeps the default rule set. Existing findings are listed per file under `lint.per-file-ignores`. A file that is not listed is checked in full.*

## pytest

作业 `test` 的矩阵是 `ubuntu-latest` 和 `windows-latest`，Python `3.11` 和 `3.12`。一个格子失败不会取消其余格子。每个格子限时 30 分钟。环境变量 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。

安装步骤升级 pip，然后安装 `requirements.txt`，再加上 `fastapi`、`httpx`、`python-multipart`、`pytest-cov`。图形界面的测试因此会执行，不是整包跳过。

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt fastapi httpx python-multipart pytest-cov
python -m pytest tests --cov=sts2sim --cov=gui --cov=tools --cov-report=term-missing --cov-report=json:coverage.json
```

覆盖范围是 `sts2sim`、`gui`、`tools`。终端报告带未覆盖行号；JSON 写到该作业工作目录里的 `coverage.json`。

*The test matrix is Ubuntu and Windows, Python 3.11 and 3.12, `fail-fast: false`, 30 minutes each, with `PYTHONUTF8` and `PYTHONIOENCODING` set. Dependencies are `requirements.txt` plus fastapi, httpx, python-multipart and pytest-cov, so the GUI tests run. Coverage is `sts2sim`, `gui` and `tools`, as a terminal report and as `coverage.json`.*

## 作业摘要里的覆盖率 / Coverage in the job summary

测试步骤之后，无论 pytest 成功还是失败，都会跑：

```bash
python .github/scripts/coverage_summary.py coverage.json
```

脚本读 pytest-cov 的 JSON，按包加总 `sts2sim`、`gui`、`tools`（路径里对不上这三份的归到 `other`，只有语句数大于 0 才列出）。表的列是 Package、Statements、Covered、Missing、Coverage，最后一行是 JSON 里的 `totals`。百分比是 `covered / statements`，保留一位小数；语句数为 0 时写 `n/a`。

`GITHUB_STEP_SUMMARY` 有值时，这段 Markdown 追加到作业摘要。没有这个环境变量时打到标准输出，所以本地也能看。找不到 `coverage.json` 时摘要是一行「Coverage report was not produced.」。什么都不上传。

[COVERAGE.md](COVERAGE.md) 里的百分比是补测试那一次记下的快照，不是这张每次作业重新算的表。

*After pytest, `.github/scripts/coverage_summary.py` always runs. It sums statement coverage for `sts2sim`, `gui` and `tools` (anything else is `other`) and appends a Markdown table to the job summary. With `GITHUB_STEP_SUMMARY` unset it prints the same table. Nothing is uploaded. The percentages in [COVERAGE.md](COVERAGE.md) are an earlier snapshot, not this per-job table.*

## Windows 安装包 / Windows package

安装包工作流是 `.github/workflows/windows-package.yml`，不是上面的 `CI`。手动运行，或推送名字以 `v` 开头的标签时，在 `windows-latest` 上打包。核对和命令行冒烟之后，`gui/packaging/smoke_api.ps1` 把 `DeckBench-0.1.5-win64.zip` 解到临时目录，用 `DeckBench.exe --serve` 无界面启动，等 `GET /api/health`，再通过 `POST /api/runs` 打一场不需要游戏的木桩（`claude_v34` 的 `probe_noengine`，`encounter: DUMMY`，1 回合）。响应按 UTF-8 字节读取，并核对 `enc_name`。然后结束进程。任一步失败，工作流失败。冒烟日志作为 Actions artifact 上传。不创建 GitHub Release。打包细节见 [DEVELOPER.md](DEVELOPER.md)。

*The package workflow is `.github/workflows/windows-package.yml`, separate from `CI` above. A manual run or a `v*` tag builds it on `windows-latest`. After the package check and the CLI smoke, `gui/packaging/smoke_api.ps1` extracts `DeckBench-0.1.5-win64.zip`, starts `DeckBench.exe --serve` with no window, waits for `GET /api/health`, runs one training-dummy fight that does not need a game through `POST /api/runs` (`claude_v34` deck `probe_noengine`, `encounter: DUMMY`, one turn), reads the response bytes as UTF-8, checks `enc_name`, and stops the process. A failed step fails the workflow. The smoke log is uploaded as an Actions artifact. The workflow does not create a GitHub Release. Packaging details are in [DEVELOPER.md](DEVELOPER.md).*
