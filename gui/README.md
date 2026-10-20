# DeckBench · 桌面界面（第一期）

给 DeckBench 套的本地图形界面：表单配置 → 一键运行 → 实时进度 → 报告 / 单卡 A/B / 历史记录。全部中文，只在本机运行（FastAPI 监听 127.0.0.1 随机端口）。

## 运行（开发模式）

```bash
.venv/bin/pip install fastapi uvicorn python-multipart pywebview   # pywebview 可选：没有就用浏览器
.venv/bin/python -m gui.app              # 独立窗口（pywebview）
.venv/bin/python -m gui.app --browser    # 浏览器
.venv/bin/python -m gui.app --serve --port 8765   # 只开服务
cd gui/web && npm install && npm run build         # 改了前端后重新构建（dist/ 不进 git，打包前先构建）
```

数据（每次测试的参数、日志、结果、上传的 mod）存在 `gui/.data/`（打包版是 exe 旁边的 `data/`），不进 git。

## 结构

- `backend.py`：**SimBackend** 抽象（catalog / build_command / summarize / ab）。第一期实现 `LocalPythonBackend`；以后发布版引擎（sts2-cli 分支，跑真实游戏 DLL）只要实现同样接口即可替换。
- `worker.py`：子进程。`batch` 复用 `tools/batch.py` 的 `_init/_one/force_cards_hook`（imap 逐局报进度；Windows 无 SIGALRM，去掉超时）；`combat` 复用 `sts2sim.runner` 的 `plan/_task` 和 `report.make_report`；`cards` 列卡牌/变体/起始牌组；`validate-mod` 用 ModSet 试加载上传的 mod。
- `modpatch.py`：运行时让 `modloader` 也能从用户 mod 目录加载（不改模拟器源码）。
- `metrics.py`：只从真实输出（runs.jsonl、cells.csv）算指标；配对差算法同 `tools/ab_card.py`。
- `jobs.py`：运行管理、日志、取消（杀整个进程树）、历史持久化。`server.py`：API + 静态前端。`app.py`：入口（窗口 / 浏览器 / 子进程模式）。
- `web/`：Vue 3 + Vite + Naive UI + ECharts。
- `packaging/`：PyInstaller 打包（`DeckBench.spec`、`launcher.py`、`build.ps1`、图标、Windows API 冒烟测试）。模拟器源码以普通文件放在 exe 旁的 `sim/`；游戏相关代码首次运行时在本机从你自己的安装生成（见根目录 README），不打包、不分发。
- `tests_e2e.py`：Playwright 端到端测试 + 截图。

## 已知限制

- 整局批量只支持内置 Claude娘 v3.5（cards_v35 变体）和原版 5 角色；上传的 YAML mod 只用于战斗实验。
- Windows 上没有 fork，「强 AI（带搜索）」「束搜索」两种整局 AI 不可用（界面自动隐藏）。
