# 导入真实对局：存档格式 / Importing a real run

DeckBench 可以**只读**打开你自己电脑上的《杀戮尖塔 2》历史记录或当前存档，查看这一局的**种子、路线、选牌、遗物**。不写回游戏，仓库里也不放任何游戏文件、代码、数据或文本。下面是实现时核对过的格式，以及和「看起来像 STS1 的 `.run`」不一样、容易读错的地方。

*DeckBench can read your own Slay the Spire 2 run history or live save and show that run's seed, route, card picks and relics. It never writes the file back, and this repo ships no game files, code, data or text. These are the format notes from building the reader, including the places that do not look like a Slay the Spire 1 `.run` and are easy to get wrong.*

命令行 / CLI：`python -m sts2sim.saveimport <文件或文件夹>`（`python tools/import_run.py` 相同）。图形界面左侧 **「导入对局」**。

*GUI: **Import run** in the sidebar.*

## 文件在哪 / Where the files are

游戏按档案把存档放在配置目录里，不在安装目录里。

| | |
|---|---|
| Windows | `%AppData%\SlayTheSpire2\steam\<SteamID>\profile1\saves` |
| macOS | `~/Library/Application Support/SlayTheSpire2/steam/<SteamID>/profile1/saves` |
| Linux | `~/.local/share/SlayTheSpire2/steam/<SteamID>/profile1/saves` |
| Steam 云端副本 | `Steam/userdata/<Steam3ID>/2868840/remote/profile1/saves` |

*The Steam Cloud mirror uses the same layout under `userdata/<Steam3ID>/2868840/remote/`.*

- 档案是 `profile1`、`profile2`、`profile3`。开着模组打的局在 `modded/profileN/saves`，和原版不是同一个目录。
- `history/<开始时间>.run`：这一局已经结束（赢、输或放弃）。文件名是 Unix 秒，不是种子。
- `current_run.save`：单人、还在打。`current_run_mp.save`：多人、还在打。局结束时游戏会删掉当前存档，再写一条 history。所以**输了的局在 history 里，不在 current_run.save 里**。
- 旁边的 `.backup`，以及读失败后被改名的 `.MIG.corrupt` / `.VAL.corrupt`，只要里面还是完整 JSON，就可以读。
- `progress.save`、`settings.save`、`prefs.save`、`profile.save` **不是一局**。导入时会跳过或明确报错，不会当成路线去解析。

环境变量 `DECKBENCH_STS2_SAVES` 可以额外指一个目录（例如你复制备份的那个文件夹）。

*Profiles are `profile1`–`profile3`. Runs played with mods live under `modded/profileN/saves`. `history/<unix-seconds>.run` is a finished run (win, loss or abandon); the filename is the start time, not the seed. `current_run.save` / `current_run_mp.save` is the run still in progress — when the run ends the game deletes it and writes history, so a loss is in history, not in the live save. `.backup` and `.MIG.corrupt` / `.VAL.corrupt` are readable when the JSON inside is intact. `progress.save`, `settings.save`, `prefs.save` and `profile.save` are not runs. `DECKBENCH_STS2_SAVES` adds another folder to look in.*

## 两套 JSON，不是一套 / Two JSON shapes

两边都是 JSON，但字段对不上。不能把 `.run` 当成 `current_run.save` 读，反过来也不行。

| | 历史 `.run` | 当前存档 `current_run*.save` |
|---|---|---|
| 常见 `schema_version` | 9 这一代 | 14–16 这一代（还在涨） |
| 种子 | 顶层 `seed` 字符串 | `rng.seed` 字符串 |
| 玩家 | `id` + `character` | `net_id` + `character_id` |
| 幕 | 字符串 id 的数组 | `{id, rooms, saved_map?}` 对象的数组 |
| 胜负 | `win`、`was_abandoned` | 没有 `win`。`win_time > 0` 才是赢，否则当作还在打 |
| 路线 | `map_point_history` | 同一个字段，内容更全的往往是 history |
| 列坐标 | 没有 | `visited_map_coords`：`{col, row}`，而且通常**只有当前幕** |

*Both are JSON, and the fields do not line up. History (schema generation 9) has a top-level `seed` string, players as `id` + `character`, and `acts` as id strings. A live save (schema 14–16 and still moving) keeps the run seed in `rng.seed`, players as `net_id` + `character_id`, and `acts` as objects. It has no `win` boolean: `win_time > 0` means won, otherwise the file is the run in progress. Column coordinates exist only on the live save, as `{col, row}`, and usually only for the act you are in.*

有的旧笔记把当前存档写成 `saves/run/` 下的二进制包。2026 年公开工具真正读到的、也是这里接受的，是 UTF-8 JSON。文件有时是 gzip（魔数 `1f 8b`），有时带 UTF-8 BOM，偶尔是 UTF-16。解压和去 BOM 都在内存里做。**不是 JSON 就停下来报错**，不去猜二进制布局。

*Some older notes describe the live save as a binary packet under `saves/run/`. What public tools actually load in 2026, and what this reader accepts, is UTF-8 JSON — sometimes gzip, sometimes with a UTF-8 BOM, occasionally UTF-16. Unpacking happens in memory. Anything that is not JSON is an error; we do not guess a binary layout.*

我们不按 `schema_version` 写死分支，只按形状认：多出来的字段忽略，缺的字段留空。

*We do not branch on a fixed `schema_version`. Extra fields are ignored; missing fields stay empty.*

## 种子 / Seed

- 历史记录用顶层 `seed`。
- 当前存档用 **`rng.seed`（字符串）**。`players[].rng.seed` 是这个玩家自己的计数器，是一个**整数**，不是游戏里那一串种子。把它显示成种子是错的。
- 只有数字、没有字符串时，会照实显示并加一条警告，不会假装它是那串字母种子。
- 另外给出规范化结果：转大写、`O→0`、`I→1`、去掉首尾空格。这和游戏、也和 DeckBench「指定游戏种子」用的是同一条规则（`sts2sim/engine/seed.py`）。界面上的「复制种子」复制的是规范化后的字符串，可以直接贴进新建测试。

*History uses the top-level `seed`. A live save uses the string `rng.seed`. `players[].rng.seed` is that player's own counter, an integer, and is not the seed shown in the game. If the file only has a number, we show it and warn, instead of pretending it is the lettered seed. The normalized form (uppercase, O→0, I→1, trimmed) matches the game and DeckBench's game-seed field. Copy seed copies that normalized string.*

## 路线 / Route

`map_point_history` 是**幕的列表，幕里面才是走过的点**，不是一条平的层列表。有的导出文件把幕这一层拍平了，我们会当成单独一幕并警告。

每个点有 `map_point_type`（见过的写法：`monster`、`elite`、`rest_site` / `RestSite`、`shop`、`treasure`、`boss`、`ancient`、`unknown`、`event`）和 `rooms[]`（`model_id`、`room_type`、`monster_ids`、`turns_taken`）。休息处、商店常常没有 `model_id`。

我们的「第 N 层」是按访问顺序从 1 数的。卡牌和遗物上的 `floor_added_to_deck` **原样保留**，不拿来重算层号——遗物也用这个名字，而且没选中的牌经常根本没有这个字段。

历史记录**没有你走的那一列**。当前存档的 `visited_map_coords` 是 `{col, row}`（不是 `{x, y}`）。幕切换时这份列表会被清掉，所以它通常只对得上**当前幕**的点数。对得上才标到路线上；对不上就警告，不硬贴。

`acts[].saved_map` 是生成出来的整张地图，字段名不稳定。目前认两种：

- `points[]`：每项有 `coord: {col, row}`、`point_type`（或 `map_point_type`）、`children`
- `grid` / `rows`：二维格子，空位是 `null`，`children` 里的整数当成**下一行的列号**

认不出就只显示路线顺序，并警告。地图涂鸦 `map_drawings`（base64 + gzip 的二进制）与种子、路线、选牌无关，不解析。

*The outer list of `map_point_history` is acts; the inner list is the points visited in that act. A flattened export is treated as one act, with a warning. `floor` in our view is visit order starting at 1. `floor_added_to_deck` is copied as stored (relics use that same field name; unpicked cards often omit it) and is not used to renumber the route. History has no column. Live `visited_map_coords` are `{col, row}` and usually only match the current act, because the list is cleared on an act change. `saved_map` is accepted as a point list (`coord`, `point_type`, `children`) or a `grid` / `rows` of cells (integer children mean columns on the next row). Any other shape keeps the route order and warns. `map_drawings` is ignored.*

## 选牌 / Card picks

选牌**不在顶层**。在 `map_point_history[幕][点].player_stats[]` 里，每个玩家一条：

```json
"card_choices": [
  {"card": {"id": "CARD.EXAMPLE", "floor_added_to_deck": 2, "current_upgrade_level": 0}, "was_picked": true},
  {"card": {"id": "CARD.OTHER"}, "was_picked": false}
]
```

同一层上的好几次奖励会接在同一个数组里，文件不标记每一次弹窗的边界，所以按文件顺序显示，不擅自拆组。

id 多半是 `CARD.EXAMPLE` 这种字符串。也见过 `{ "category": "CARD", "entry": "EXAMPLE" }`，会拼回 `CARD.EXAMPLE`。

遗物选项是另一套：`relic_choices[]` 用 `choice` + `was_picked`。古遗物又是一套：`ancient_choice[]` 的键是 PascalCase 的 `TextKey`，布尔值叫 `was_chosen`，而且值是**不带 `RELIC.` 的短名**。我们补上 `RELIC.` 并标成推断出来的。商店买的遗物可能只出现在 `bought_relics`（id 字符串列表）里。

多人时每个点的 `player_stats` 有多条，用 `player_id` 对上玩家，不会把别人的选牌画到你的路线上。

*Picks are not a top-level list. They live on `player_stats[]` of each map point: `{card: {id, ...}, was_picked}`. Several rewards on one point are concatenated with no screen boundaries, so they stay in file order. Ids are usually prefixed strings; `{category, entry}` objects are joined back into that string. Relic offers use `choice` + `was_picked`. Ancient offers use PascalCase `TextKey`, `was_chosen`, and a short name with no `RELIC.` prefix — that prefix is added and marked inferred. Shop relics may only show up in `bought_relics`. Co-op stats are matched by `player_id`.*

## 遗物和玩家 id / Relics and player ids

最终遗物栏是 `players[].relics`：`{id, floor_added_to_deck}`。牌组、药水同理（药水用 `slot_index`）。附魔 `enchantment` 有时是对象 `{id, amount}`，有时是字符串。

玩家 id 经常是 Steam64，大于 2^53。Python 读 JSON 时还是整数，但交给浏览器之前必须是**字符串**，否则页面上的 id 会变掉。视图里的 `id` 一律是十进制字符串。

`platform_type` 有时是整数（`0` 无、`1` Steam），有时是 `"Steam"` / `"none"`。`game_mode` 有时是 `"Standard"`，有时是 `"standard"`。

*The final relic bar is `players[].relics` as `{id, floor_added_to_deck}`. Enchantments are sometimes an object, sometimes a string. Steam64 ids are larger than 2^53, so every player id in the view is a decimal string — a JSON number would be corrupted in the browser. `platform_type` may be an int or a string. `game_mode` may be `Standard` or `standard`.*

## 名字从哪来 / Where display names come from

界面优先显示 id。你的游戏安装在的时候，再按当前界面语言从本机的本地化表里查名字（和卡牌、角色、遭遇一样，查不到就留 id）。这些文字不进仓库。

*The UI shows ids. When your install is present, names are read from its localization for the current UI language, the same way card and character names already work. That text is never committed.*

## 故意不做的事 / What this does not do

- 不修改、不删除、不「修复」存档。读文件用的是只读打开。
- 不把 history 拼回一个能读档的 `current_run.save`。那要一份同版本的存档当模板，而且商店和抽牌的随机序列恢复不了。
- 不解析 `progress.save` 里的解锁进度。

*Nothing is written or deleted (files are opened read-only). History is not rebuilt into a loadable live save — that needs a same-version template and still would not restore shop and draw RNG. `progress.save` unlocks are out of scope.*

## 怎么自己跑一遍 / Reproduce

合成样例在 `tests/fixtures/saves/`（`CARD.ALPHA`、`RELIC.START` 这种名字是编的，不是游戏数据）：

```bash
python -m sts2sim.saveimport tests/fixtures/saves/history_run.json
python -m sts2sim.saveimport tests/fixtures/saves/live_run.json --json
python -m pytest -q tests/test_saveimport.py
```

*The fixtures under `tests/fixtures/saves/` use made-up ids, not game data. The history sample's seed `seed0o` normalizes to `SEED00`. The live sample's run seed is the string on `rng.seed`; the number on the player rng must not appear as the seed, and the Steam id must survive as a string.*
