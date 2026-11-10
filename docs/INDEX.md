# 文档索引 / Documentation index

仓库里的说明都从这里链出去。`docs/` 里多数页是中文和英文写在同一份文件里。mod 作者入门是两份：英文和简体中文。README 有四种语言。Windows 安装包的说明在 `gui/packaging/`：打进 zip 的 `README-win.txt`、第三方声明，以及 `ship-manifest.txt`。

*Every guide in the repository is linked from here. Most pages under `docs/` are Chinese and English in one file. The mod-author guide is two files, English and 简体中文. The README exists in four languages. The Windows package notes live under `gui/packaging/`: `README-win.txt` (copied into the zip), the third-party notices, and `ship-manifest.txt`.*

## docs/

| 文档 | 语言 | 内容 |
| --- | --- | --- |
| [RELEASE_0.1.5.md](RELEASE_0.1.5.md) | 中文、English | 0.1.5 发布说明，可作 GitHub Release 正文。覆盖已合并的 #4 与 #6–#58（#40 对齐到 #39，#53 对齐到 #52；其后是 #54–#58：界面浏览器冒烟、战斗对比、离线 HTML、组牌、遭遇选择） |
| [MOD_AUTHORS.md](MOD_AUTHORS.md) | English | mod 作者入门。示例 `examples/spark/`（Arc、Lantern）。内部 Python 引擎，不需要游戏安装 |
| [MOD_AUTHORS.zh-CN.md](MOD_AUTHORS.zh-CN.md) | 简体中文 | 同一份入门的简体中文 |
| [MODDING.md](MODDING.md) | 中文 + English | YAML mod 的格式：整局，以及旧版战斗模拟器 |
| [DLL_MODS.md](DLL_MODS.md) | 中文 + English | 把已经写好的游戏 mod DLL 读成 YAML。DLL 不执行 |
| [SAVE_FORMAT.md](SAVE_FORMAT.md) | 中文 + English | 对局记录的两种 JSON、批量摘要、种子预览 |
| [CALIBRATION.md](CALIBRATION.md) | 中文 + English | 真对局对照同一条选牌路径上的模拟掉血：匹配规则、百分位、界面和 HTTP、MCP，以及缺口分诊（`tools/gap_triage.py`、`POST /api/gap_triage`、校准页） |
| [COMPARE.md](COMPARE.md) | 中文 + English | 两次已完成的战斗实验：格子胜率、超时、回合、掉血、每回合输出，以及单卡使用和效率。`GET /api/runs/compare`、MCP `compare_runs`、界面 `#/compare` |
| [DECKS.md](DECKS.md) | 中文 + English | 组牌页：搜索模拟器牌池，勾选遭遇或一场连战（例如第 1 幕全部精英），保存成和 `experiments/*.yaml` 一样的用户预设。没选遭遇时仍是一场训练木桩。两份预设可以对打（同一份遭遇、同一颗种子）。一份预设可以做留一法，看每张牌对胜率、掉血和回合的影响，全体不超过 400 场。长测试有进度和取消，部分结果可以对比和导出。战斗批量可以设 `workers`（默认 1，上限 `min(cpu_count, 8)`）。`GET /api/cards`、`GET /api/encounters`、`POST /api/decks`、`POST /api/decks/head_to_head`、`POST /api/decks/<id>/card_impact`、`GET /api/runs/<id>/progress`、MCP `list_cards` / `list_encounters` / `save_deck` / `head_to_head` / `card_impact` / `run_progress` / `cancel_run`、界面 `#/decks` |
| [EXPORT.md](EXPORT.md) | 中文 + English | 把已完成的测试、可选的战斗对比、可选的校准 / 缺口分诊写成一份离线 HTML。`GET /api/runs/<id>/export.html`、`GET /api/runs/compare/export.html`、MCP `export_report`、`python -m tools.export_report` |
| [MCP.md](MCP.md) | 中文 + English | MCP 对战，以及 `import_save`、`import_history_batch`、`batch_run_summary`、`card_ab`、`compare_runs`、`explain_fight`、`calibrate`、`gap_triage`、`export_report`、`list_cards`、`list_encounters`、`save_deck`、`head_to_head`、`run_progress`、`cancel_run`、可选的 `check_update` |
| [PERFORMANCE.md](PERFORMANCE.md) | 中文 + English | `python tools/bench.py` 的样本、场/秒和内部战斗引擎改了什么 |
| [COVERAGE.md](COVERAGE.md) | 中文 + English | 补测试那一次的语句覆盖率快照，以及当时修的五处边界 |
| [CI.md](CI.md) | 中文 + English | GitHub Actions：Ubuntu / Windows、Python 3.11 与 3.12、pytest-cov 作业摘要、ruff 0.17.4；Ubuntu 上单独的 Playwright 界面冒烟；Windows 安装包工作流、接口冒烟，以及响应的 `charset=utf-8` |
| [DEVELOPER.md](DEVELOPER.md) | 中文 + English | 命令行、首次生成、spire-mentor、旧版战斗模拟器、目录、测试。[Windows 打包](DEVELOPER.md#windows-打包版--building-the-windows-package) 含 `dry_check.py`、带 BOM 的 `.ps1`、csproj 注释、从 `sts2sim.__version__` 读取的版本号，和 Actions 工作流。持续集成的说明在 [CI.md](CI.md) |
| [patches/spire-mentor-v0111-cards.patch](patches/spire-mentor-v0111-cards.patch) | — | 打在你自己的 spire-mentor 克隆上的代码补丁。不含游戏文本或数据 |

## 仓库根和界面 / Root and the desktop app

| 文档 | 语言 | 内容 |
| --- | --- | --- |
| [CHANGELOG.md](../CHANGELOG.md) | 中文 + English | 更新日志。0.1.5 一节对齐 `main` 上的 #4 与 #6–#58 |
| [README.md](../README.md) | 中文为主，段落附 English | 安装和使用 |
| [README.en.md](../README.en.md) | English | 同一份说明的英文 |
| [README.ja.md](../README.ja.md) | 日本語 | 同一份说明的日文 |
| [README.ko.md](../README.ko.md) | 한국어 | 同一份说明的韩文 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | English + 中文 | 贡献须知。不接受任何游戏内容 |
| [gui/README.md](../gui/README.md) | 中文 | 桌面界面的开发运行、结构和打包 |
| [gui/packaging/README-win.txt](../gui/packaging/README-win.txt) | 中文 + English | 打进 Windows zip 的 `README.txt`：解压、第一次启动、可选的 mentor-full |
| [gui/packaging/THIRD-PARTY-NOTICES.txt](../gui/packaging/THIRD-PARTY-NOTICES.txt) | 中文 + English | 安装包里的第三方声明。许可证全文在 `gui/packaging/notices/` |
| [gui/packaging/ship-manifest.txt](../gui/packaging/ship-manifest.txt) | — | 0.1.5 安装包要带上的路径。`dry_check.py` 和 `audit.ps1` 对照这份清单 |
| [mods/claude_v35/README.md](../mods/claude_v35/README.md) | 中文 | 示例 mod Claude娘 v3.5 接到整局引擎时的说明 |
| [tests/fixtures/dllmod/README.md](../tests/fixtures/dllmod/README.md) | 中文 + English | DLL 导入夹具是合成的，不是游戏文件 |
