# 持续集成 / Continuous integration

[← 返回 README](../README.md) · [文档索引](INDEX.md) · [覆盖率快照](COVERAGE.md) · [测试](DEVELOPER.md#测试--tests)

GitHub Actions 工作流在 `.github/workflows/ci.yml`，名字是 `CI`。推送到 `main` 和任意 pull request 都会跑。`contents` 权限是只读。同一分支上新的一次运行会取消还没跑完的那次。这一页记下工作流现在做什么。

*The workflow file is `.github/workflows/ci.yml`, named `CI`. It runs on a push to `main` and on every pull request, with read-only `contents`. A newer run on the same ref cancels the one still going. This page describes what that file does now.*

这个工作流不准备游戏安装，所以要本机游戏或本机生成缓存的测试仍会跳过。它不上传覆盖率，也没有发布步骤。界面的无头浏览器冒烟是另一个作业，只在 Ubuntu 上跑，不改上面的 pytest 矩阵。

*A local game install is not prepared, so tests that need one still skip. Coverage is not uploaded, and there is no publish step. The headless GUI browser smoke is a separate Ubuntu-only job. It does not change the pytest matrix above.*

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

## 界面浏览器冒烟 / GUI browser smoke

作业 `gui-browser` 只在 `ubuntu-latest` 上跑，不在 pytest 的操作系统 / Python 矩阵里。限时 30 分钟。`contents` 仍是只读；这一作业另外有 `actions: write`，用来在失败时上传 artifact。环境变量 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，以及 `DECKBENCH_BROWSER_REQUIRED=1`（浏览器没装好就失败，而不是跳过）。

Python 3.12。安装 `requirements-gui.txt` 和 `pytest-playwright==0.7.2`，然后 `python -m playwright install --with-deps chromium`。Node.js 用当前 LTS，在 `gui/web` 里 `npm ci && npm run build`（`dist/` 不进仓库，服务读的是这份构建结果）。然后：

```bash
python -m pytest -q tests/test_gui_browser.py --browser chromium --screenshot only-on-failure --tracing retain-on-failure
```

服务是源码里的 `python -m gui.app --serve`，绑一个空闲端口，不需要本机游戏。测试写一份空的卡牌缓存，这样目录接口不用去跑需要游戏数据的卡牌子进程。战斗实验的预设和 Windows 安装包冒烟一样：`claude_v34`、卡组 `probe_noengine`、`encounter: DUMMY`、1 回合。预设只在测试期间写到 `experiments/browser_smoke.yaml`，结束就删。

`tests/test_gui_browser.py` 检查这些：主页面能打开且没有控制台错误（含 `#/calibrate` 和「决策说明」`#/explain`）；侧栏的简体中文（zh-CN）/ English 会换掉可见文案，选择写在 `localStorage` 的 `ui.lang`（`zhs` / `en`），刷新后还在；从界面点一场木桩，状态到完成；用 `tests/fixtures/calibrate/` 的样例对局和 `runs.jsonl` 打开校准页，缺口分诊一节能画出 `SAMPLE_ELITE`。

没装 pytest-playwright 或 Chromium 时，这份测试在收集阶段就跳过。矩阵作业不装它们，所以那里的 `python -m pytest tests` 不会因为缺浏览器失败。

失败时把 `test-results/`（pytest-playwright 的截图和 trace）用 `actions/upload-artifact@v7` 上传，名字是 `gui-browser-smoke`，保留 14 天。没有这些文件时上传步骤不失败。成功不上传。

*Job `gui-browser` runs only on `ubuntu-latest`. It is not part of the pytest OS / Python matrix. The limit is 30 minutes. `contents` stays read-only; this job also has `actions: write` so it can upload an artifact on failure. `PYTHONUTF8`, `PYTHONIOENCODING`, and `DECKBENCH_BROWSER_REQUIRED=1` are set (a missing browser fails the job instead of skipping).*

*Python 3.12. It installs `requirements-gui.txt` and `pytest-playwright==0.7.2`, then `python -m playwright install --with-deps chromium`. Node.js is the current LTS. `gui/web` runs `npm ci && npm run build` (`dist/` is not committed; the server reads that build). The pytest command is above.*

*The server is `python -m gui.app --serve` from source, on a free port, with no local game. The test writes an empty card cache so the catalog does not launch the card subprocess that needs game data. The combat preset matches the Windows package smoke: `claude_v34`, deck `probe_noengine`, `encounter: DUMMY`, one turn. The preset file `experiments/browser_smoke.yaml` exists only while the test runs.*

*`tests/test_gui_browser.py` checks that the main pages open with no console errors (including `#/calibrate` and Decisions, `#/explain`); the sidebar 简体中文 (zh-CN) / English switch changes the visible strings and stores the choice in `localStorage` `ui.lang` (`zhs` / `en`) across a reload; a dummy fight started from the GUI reaches done; and the calibration page opened on `tests/fixtures/calibrate/` renders gap triage with `SAMPLE_ELITE`.*

*Without pytest-playwright or Chromium the module is skipped at collection. The matrix job does not install them, so `python -m pytest tests` there does not fail for a missing browser.*

*On failure, `test-results/` (pytest-playwright screenshots and traces) is uploaded with `actions/upload-artifact@v7` as `gui-browser-smoke`, kept for 14 days. A missing directory does not fail that step. A green run uploads nothing.*

## Windows 安装包 / Windows package

安装包工作流是 `.github/workflows/windows-package.yml`，不是上面的 `CI`。手动运行，或推送名字以 `v` 开头的标签时，在 `windows-latest` 上打包。核对和命令行冒烟之后，`gui/packaging/smoke_api.ps1` 把 `DeckBench-0.1.5-win64.zip` 解到临时目录，用 `DeckBench.exe --serve` 无界面启动，等 `GET /api/health`，再通过 `POST /api/runs` 打一场不需要游戏的木桩（`claude_v34` 的 `probe_noengine`，`encounter: DUMMY`，1 回合）。响应按 UTF-8 字节读取，并核对 `enc_name`。然后结束进程。任一步失败，工作流失败。冒烟日志作为 Actions artifact 上传。不创建 GitHub Release。打包细节见 [DEVELOPER.md](DEVELOPER.md)。

*The package workflow is `.github/workflows/windows-package.yml`, separate from `CI` above. A manual run or a `v*` tag builds it on `windows-latest`. After the package check and the CLI smoke, `gui/packaging/smoke_api.ps1` extracts `DeckBench-0.1.5-win64.zip`, starts `DeckBench.exe --serve` with no window, waits for `GET /api/health`, runs one training-dummy fight that does not need a game through `POST /api/runs` (`claude_v34` deck `probe_noengine`, `encounter: DUMMY`, one turn), reads the response bytes as UTF-8, checks `enc_name`, and stops the process. A failed step fails the workflow. The smoke log is uploaded as an Actions artifact. The workflow does not create a GitHub Release. Packaging details are in [DEVELOPER.md](DEVELOPER.md).*
