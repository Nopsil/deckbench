# MCP 对战模式 / MCP play mode

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
| `seed_preview(seed, character, ascension, neow, cache, cache_dir)` | 不打一局。返回和 `tools/seed_preview.py --json -` 相同的稳定 v1 JSON。`neow`：`first`（默认，第一个没锁的）/ `all` / `none` / 序号文本（如 `"2"`），是选择器本身。`cache` 可选，把同一份 JSON 留在本机（目录不能在仓库里）。参数不合法或没有本机游戏逻辑时返回 `{"ok": false, "error": ...}`，不编地图 |

`import_save` 和 `python tools/import_run.py <path> --summary` 是同一份摘要（`sts2sim/saveimport.py` 的 `summarize`；命令行多缩进，对象相同）。没有本机游戏数据时，对战服务仍会退出；改跑 `python tools/mcp_server.py --import-only`（只有 `import_save`）或上面的命令行。

`seed_preview` 只在对战服务器上（需要已经生成本机游戏逻辑，和 `new_run` 一样）。成功时没有 `ok` 字段，就是那份 v1 文档：`v`、`seed_input`、`seed`、`warnings`、`character`、`ascension`、`acts`、`maps`、`rooms`、`distribution`、`ancient`、`neow_options`、`after_neow`、`relics`、`limits`。可选 `cache=true` 按规范化种子、角色、进阶和 `neow` 选择器写入 `cache_dir`（空着则用 `DECKBENCH_CACHE/seed-preview`），不进仓库。

*Seed preview is the same stable v1 document as `python tools/seed_preview.py <seed> --json -`. `neow` is `first`, `all`, `none`, or a decimal index such as `"2"`. It does not start a run. A bad selector or a missing local engine returns `{"ok": false, "error": "..."}` instead of an invented map. `--import-only` stays import-only.*

## 资源 / Resources
| 资源 | 说明 |
|---|---|
| `deckbench://seed-preview/v1` | 预览 JSON 的字段顺序、`neow` 取值和角色列表。不生成地图，不读游戏 |

格式见 [SAVE_FORMAT.md](SAVE_FORMAT.md)。

同一种子 + 同一串选择 = 同一局，所以撤销/恢复是「重开 + 重放」；服务器重启后也能 `open_run` 接着打。
奖励里的金币/药水/遗物默认全拿，不算决策；宝箱遗物会真正进遗物栏（0.1.3 修复）。一局结束时列出全部遗物和牌组。`auto` 用的 AI 内部随机状态不随撤销回滚，撤销后再 `auto` 可能走出不同的路线。

测试：`python tools/mcp_e2e.py`（stdio）或 `python tools/mcp_e2e.py --http-url http://127.0.0.1:8765/mcp`。
