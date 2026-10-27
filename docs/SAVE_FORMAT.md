# 对局记录与种子预览 / Run history and seed preview

[← 返回 README](../README.md) · [开发者文档](DEVELOPER.md)

DeckBench 0.1.5 可以**只读**打开你自己电脑上的《杀戮尖塔 2》对局记录，也可以在不打完整一局的情况下预览一个种子的地图和遭遇。
仓库里**没有**游戏存档、游戏文本或游戏代码。下面的字段名来自公开的存档结构（社区解析器和存档修复工具的说明），解析器对认不出的键保持沉默。
*DeckBench 0.1.5 can read a run file you point it at, and can preview a seed's map and encounters without playing the run. This repository ships no game saves, text or code. Field names below follow the publicly described save shape; unknown keys are ignored.*

## 文件在哪 / Where the files are

游戏用 Godot 的 `user://`，目录名是 `SlayTheSpire2`（不是 `Godot/app_userdata`）。

| 系统 | 根目录 |
|---|---|
| Windows | `%APPDATA%\SlayTheSpire2\` |
| Linux | `~/.local/share/SlayTheSpire2\` |
| Linux（Flatpak Steam） | `~/.var/app/com.valvesoftware.Steam/data/SlayTheSpire2\` |
| macOS | `~/Library/Application Support/SlayTheSpire2\` |

每个 Steam 账号下面：

```text
steam/<steam64>/
  profile.save                      当前用的是哪个档位
  profile1/  profile2/  profile3/   原版三个档位
  modded/profile1/ ...              开了 mod 时的档位
    saves/
      history/<unix 秒>.run         打完（胜、负、放弃）的一局。纯文本 JSON
      history/<unix 秒>.run.backup  有时有一份副本
      current_run.save              正在打的单人局。死掉或通关后游戏会删掉它
      current_run_mp.save           正在打的多人局（只在主机上）
      current_run.save.backup
      progress.save                 解锁和统计，不是一局
      prefs.save                    这个档位的偏好
```

游戏内控制台 `open saves` 会打开 `steam/<steam64>/`。
Steam 云缓存在 `<Steam>/userdata/<id>/2868840/`，和本地目录是两份；死掉时游戏会把 `current_run.save` 从本地和云上一起删掉。**留下来的是 `history/*.run`。**

文件名是 **Unix 秒**，不是毫秒。论坛里有人说毫秒，例子 `1779550532.run` 其实是 2026 年的秒级时间戳。`.run.backup` 先去掉 `.backup` 再去掉 `.run` 才是这个数字。

`DECKBENCH_SAVE_ROOTS`（用系统的路径分隔符拼多个目录）会额外拿来查找，方便存档不在默认位置时用。

## 两种 JSON，不要混 / Two JSON shapes

两边都是 JSON，**没有看到加密**（至少到公开说明里的 RunHistory schema 9、SerializableRun schema 16）。
如果文件不是文本 JSON（大量 NUL、解不开的 gzip），导入会停下来并说明：可能是损坏，或者以后的版本改成了加密。DeckBench **不会尝试解密**。

| | 已结束的 `.run`（RunHistory） | 进行中的 `current_run.save`（SerializableRun） |
|---|---|---|
| `schema_version` | 常见是 9 | 常见是 14–16，游戏读入时还会再迁移 |
| `seed` | 顶层字符串 | 经常只在 `rng.seed` |
| `acts` | 字符串数组，如幕的模型 ID | 对象数组 `{id, rooms, saved_map?}` |
| `players` | `{id, character, deck, relics, potions}` | `{net_id, character_id, current_hp, gold, deck, relics, rng, ...}` |
| `map_point_history` | 有。外层是幕，内层是这一幕走过的点 | 同样的结构 |
| 地图列号 | **没有** | `visited_map_coords` 是 `{col, row}`；`acts[].saved_map` 有时有整张图 |
| 结局 | `win` / `was_abandoned` | 进行中通常没有 `win` |

键名大小写不敏感：`map_point_history`、`mapPointHistory`、`MapPointHistory` 都认。缺了的列表当成空的（游戏有「空集合就不写」的习惯）。

### 路线、选牌、遗物 / Route, picks, relics

`map_point_history[幕][点]`：

- `map_point_type`：`Ancient`、`Monster`、`Elite`、`Boss`、`RestSite`、`Shop`、`Treasure`、`Unknown`（也见过小写）
- `rooms`：遭遇房带 `model_id`、`monster_ids`、`turns_taken`、`room_type`；事件房通常只有 `model_id` 和 `turns_taken`；商店/休息/宝箱可能只剩 `turns_taken`
- `player_stats[]`：这一层结束时的生命、金币，以及
  - `card_choices[]`：`{card: {id, ...}, was_picked}`
  - `potion_choices[]`：`{choice, was_picked}`
  - 如果以后出现 `relic_choices`，同样读取

模型 ID 是字符串，形如 `CARD.…`、`RELIC.…`、`ENCOUNTER.…`、`EVENT.…`、`ACT.…`、`CHARACTER.…`。`NONE.NONE` 当成没有。
牌的升级不保证有单独字段；看到 `current_upgrade` / `is_upgraded` / `upgrade_level` 大于 0 就记成升级。附魔是 `{id, amount}`。
遗物获得层数的字段名叫 `floor_added_to_deck`（和牌同一个名字）。

**列号是缺口。** 打完的 `.run` 只记「第几层、什么类型、发生了什么」，不记地图上的左右位置。进行中存档的 `saved_map` 我们只认两种形状：`{points:[{coord:{col,row}, point_type, children}]}`，或者已经是 `{rows, cols, boss}`。对不上就显示路线表，并写一条「地图没有画出来」，不猜枚举顺序。

多人局 `players` 有多项，都列出来。加入的客机自己的电脑上通常没有 `current_run_mp.save`。

## 怎么试 / How to try

不需要安装游戏。夹具 `tests/fixtures/saves/sample_history.run` 用的是虚构 ID（`CARD.SAMPLE_PICK` 这种），只为了演示解析，**不是**游戏数据。

```bash
python tools/import_run.py tests/fixtures/saves/sample_history.run
python tools/import_run.py tests/fixtures/saves/sample_history.run --lang en --json /tmp/run.json
python tools/import_run.py tests/fixtures/saves/sample_live.save --lang en
python tools/import_run.py --discover
```

图形界面左侧 **导入对局**：贴路径、选文件，或点「查找本机存档」。只读，不会改你的存档。
接口（只监听本机）：

- `POST /api/import`，正文 `{"path": "..."}` 
- `POST /api/import/upload`，表单字段 `file`
- `GET /api/saves/discover`

测试：`tests/test_saveimport.py`。

## 种子预览 / Seed preview

给定种子、原版角色、进阶 0–10，生成：

- 每一幕的地图（格子类型和连线）
- 每一幕的普通怪 / 精英队列、首领、第二首领（进阶会开双首领时）、古神
- 开局选项，以及选完之后**第一场普通战斗的奖励界面**（不把那场战斗打完）
- 开局已经拿到的遗物；如果引擎把遗物袋的列表放在字段上，也显示抽取顺序

这和 `tools/seed_probe.py` 是同一条本机游戏逻辑，**不是**再模拟一整局 AI。没有本机生成过游戏逻辑时会直接说明，退出码 2。

```bash
python tools/seed_preview.py 7F3K9Q2ZB8MA --char Ironclad --asc 0
python tools/seed_preview.py 7F3K9Q2ZB8MA --neow all --json /tmp/preview.json --lang en
```

图形界面 **种子预览**，或 `POST /api/seed-preview`，正文 `{"seed","char","asc","neow"}`。`neow` 取 `first`（默认，第一个没锁的）、`all`、`none` 或序号。

和真游戏对照时的前提（和种子探针相同）：

- 全解锁。新档的幕和卡池可能不同。
- 不是教程局。
- 没有自定义修改器。
- 问号节点走进去才掷点，预览不提前掷。
- **第 1 幕地图**是进幕时 `CreateMap` 的结果，可以拿游戏截图对。
- **第 2 幕及以后**是「如果现在进入这一幕」生成的，中间没有把上一幕打完。只有地图随机流不被战斗消耗时才和实机一致，界面上标成投影。
- 遭遇队列是开局就排好的抽取顺序，不是地图上从左到右的位置。
- 遗物袋顺序读不到时，只列出开局遗物，并写明原因。不会替你选宝箱。

测试：`tests/test_seedpreview.py`。没有本机游戏缓存时，预览测试只检查分布、报错和命令行退出码；有缓存时会真的生成一局预览。
