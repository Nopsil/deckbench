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
| `new_run(seed, character, ascension, persona)` | 种子按游戏规则规范化（大写、O→0、I→1）；persona 可选：`qianwen`、`lirixuan`（JUGGLING 流铁甲风格，`auto` 代打也用这个风格），或任意一段风格描述 |
| `get_state()` | 楼层/生命/金币/遗物/药水/牌组 + 当前界面 + 战斗（能量、手牌、敌人生命/意图/能力）+ 带编号的合法选项 |
| `act(option_index, reason, indices)` | 执行一个选项；多选界面用 `indices`；非法选项返回错误并保持原状 |
| `auto(steps, until)` | 交给内置 AI 代打；`until`：`combat_end` / `floor` / `screen:<名字>` |
| `get_map()` / `get_deck()` | 文字地图（含当前位置）/ 牌组 |
| `undo(steps)` / `restore(step)` | 回退几步 / 回到第 step 个决策之前 |
| `get_log(last)` / `export_log()` | 决策日志；导出 decisions.jsonl + replay.md |
| `list_runs()` / `open_run(run_id)` | 列出 / 重新打开以前的局 |

同一种子 + 同一串选择 = 同一局，所以撤销/恢复是「重开 + 重放」；服务器重启后也能 `open_run` 接着打。
奖励里的金币/药水/遗物默认全拿，不算决策。`auto` 用的 AI 内部随机状态不随撤销回滚，撤销后再 `auto` 可能走出不同的路线。

测试：`python tools/mcp_e2e.py`（stdio）或 `python tools/mcp_e2e.py --http-url http://127.0.0.1:8765/mcp`。
