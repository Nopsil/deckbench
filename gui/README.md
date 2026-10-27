# DeckBench · 桌面界面（第一期）

给 DeckBench 套的本地图形界面：表单配置 → 一键运行 → 实时进度 → 报告 / 单卡 A/B / 历史记录。全部中文，只在本机运行（FastAPI 监听 127.0.0.1 随机端口）。

## 运行（开发模式）

```bash
.venv/bin/pip install -r requirements-gui.txt   # Windows: .venv\Scripts\pip ...；pywebview 可选：没有就用浏览器
.venv/bin/python -m gui.app              # 独立窗口（pywebview）
.venv/bin/python -m gui.app --browser    # 浏览器
.venv/bin/python -m gui.app --serve --port 8765   # 只开服务
cd gui/web && npm install && npm run build         # 改了前端后重新构建（dist/ 不进 git，第一次运行前和打包前都要先构建）
```

数据（每次测试的参数、日志、结果、上传的 mod）存在 `gui/.data/`（打包版是 exe 旁边的 `data/`），不进 git。

## 结构

- `backend.py`：**SimBackend** 抽象（catalog / build_command / summarize / ab）。第一期实现 `LocalPythonBackend`；以后发布版引擎（sts2-cli 分支，跑真实游戏 DLL）只要实现同样接口即可替换。
- `worker.py`：子进程。`batch` 复用 `tools/batch.py` 的 `_init/_one/force_cards_hook`（imap 逐局报进度；Windows 无 SIGALRM，去掉超时）；`combat` 复用 `sts2sim.runner` 的 `plan/_task` 和 `report.make_report`；`cards` 列卡牌/变体/起始牌组；`validate-mod` 用 ModSet 试加载上传的 mod。
- `modpatch.py`：运行时让 `modloader` 也能从用户 mod 目录加载（不改模拟器源码）。
- `metrics.py`：只从真实输出（runs.jsonl、cells.csv）算指标；配对差算法同 `tools/ab_card.py`。
- `jobs.py`：运行管理、日志、取消（杀整个进程树）、历史持久化。`server.py`：API + 静态前端。`app.py`：入口（窗口 / 浏览器 / 子进程模式）。
- `web/`：Vue 3 + Vite + Naive UI + ECharts。页面还有「导入对局」（只读解析玩家指出的 `.run` / `current_run.save`）和「种子预览」（不打完整一局）。
- 接口：`POST /api/import`、`POST /api/import/upload`、`GET /api/saves/discover`、`POST /api/seed-preview`。格式见 [docs/SAVE_FORMAT.md](../docs/SAVE_FORMAT.md)。
- `locales/<lang>.json` + `i18n.py` + `web/src/i18n.js`：界面多语言（zhs 简体中文默认/回退、en、ja、ko），前后端共用同一份扁平键翻译表；选择存在数据目录的 `settings.json`，第一次按系统语言。游戏里的名字（卡牌、角色、遭遇）不进翻译表，按所选语言从玩家自己的游戏安装读（`sts2sim/gameloc.py`，缺了回退 eng → zhs → ID）。加新文字时四个文件都要加同一个键，`tests/test_i18n.py` 会检查。
- `packaging/`：PyInstaller 打包（`DeckBench.spec`、`launcher.py`、`build.ps1`、图标、Windows API 冒烟测试）。模拟器源码以普通文件放在 exe 旁的 `sim/`；游戏相关代码首次运行时在本机从你自己的安装生成（见根目录 README），不打包、不分发。
- `tests_e2e.py`：Playwright 端到端测试 + 截图。

## 已知限制

- 整局批量只支持内置 Claude娘 v3.5（cards_v35 变体）和原版 5 角色；上传的 YAML mod 只用于战斗实验。
- Windows 上没有 fork，「强 AI（带搜索）」「束搜索」两种整局 AI 不可用（界面自动隐藏）。
- 「通用 AI（推荐，模组角色也能用）」= `modai`；「通用 AI（首领战搜索）」= `modai-boss`（用 fork，Windows 上隐藏）。
- 「新建测试 → 整局批量」可以填「指定游戏种子」：只打这一局，逐步决策日志写到该次运行目录的 `steps/`。
- 「spire-mentor 整局 AI（外部）」（`mentor-full`）和「spire-mentor 整局 AI＋事件」（`mentor-full-ev`）在「新建测试 → 整局批量」里。指向自己构建的 spire-mentor 之后才能选（环境变量、`mentor.local.json`，或旁边的 `mentor/` 目录），否则是灰色并带提示。打包版还要把 `python` 设成构建 `sts2_rs` 的解释器，界面会用它跑 `sim/gui` 里的工作进程，而不是用 exe 里的解释器。只支持原版 5 个角色；模组角色局外决策回退学习版，日志会写明。库加载失败则这次运行停止。见 [docs/DEVELOPER.md](../docs/DEVELOPER.md)。
  *`mentor-full` and `mentor-full-ev` are in New test → Full runs. They stay greyed out until your own spire-mentor build is configured (env, `mentor.local.json`, or a `mentor/` folder). The packaged app also needs `python` set to the interpreter that built `sts2_rs` and then runs the worker from `sim/gui`. Vanilla characters only; mod characters fall back out of combat and the log says so. If the library fails to import, the run stops.*
