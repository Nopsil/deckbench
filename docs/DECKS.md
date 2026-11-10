# 组牌 / Deck builder

[← 文档索引](INDEX.md) · [MCP](MCP.md) · [模组格式](MODDING.md)

侧栏「组牌」（`#/decks`）用来浏览模拟器已经认识的牌，组成一套牌，存成战斗预设。新建测试里选这份预设就能开打。不改模拟器的出牌、种子和 AI，也不改 `experiments/` 里的出厂预设、`mods/`、种子或已有配置。

*Deck builder (`#/decks`) browses the cards the simulator already knows, builds a deck, and saves a combat preset. New test can start that preset immediately. Simulator play, seeds and AI stay as they are. Shipped presets under `experiments/`, `mods/`, seeds and existing configs are not changed.*

## 牌池 / Card pool

牌来自模拟器启动时就会加载的 YAML：`sts2sim/builtin_cards.yaml`，以及 `mods/<名字>/cards.yaml`（还有界面用户 mod 目录里的同名文件）。不读取、也不分发游戏安装里的卡牌文本。一张牌带有 id、中文名、英文名、角色、类型、费用、稀有度和升级后费用。

英文名优先用卡面上的英文（`name` 本身是英文，或 `name_en`）。没有单独英文名时，用 id 拆开的词，例如 `CLAUDE_STRIKE` 显示成 `Claude Strike`，搜索 `Strike` 或中文名 `打击` 都能找到。官方本地化如果在本机游戏里读得到，会补上缺的中文或英文标题，只在内存里用。

*Cards come from the YAML the simulator already loads: `sts2sim/builtin_cards.yaml` and `mods/<name>/cards.yaml` (and the same files under the GUI's user-mod folder). Game-install card text is not read into the repository and is not shipped. Each card has an id, a Chinese name, an English name, a character, a type, a cost, a rarity and an upgraded cost.*

*The English name is the card's own English (`name` when it is English, or `name_en`). When there is no separate English name, the words in the id are used, so `CLAUDE_STRIKE` shows as `Claude Strike` and a search for `Strike` or the Chinese name `打击` both find it. Official localization fills a missing Chinese or English title when a local game install can be read. That text stays in memory.*

`GET /api/cards` 只读，分页。

| 参数 | 作用 |
| --- | --- |
| `q` | 子串，同时匹配中文名、英文名、显示名和 id。最长 80 |
| `character` | 角色 id，例如 `claude` |
| `type` | `Attack` / `Skill` / `Power` / `Status` / `Curse`，也认中文类型 |
| `cost` | `0`、`1`、`2`…、`X`（X 费）或 `none`（不能打出） |
| `rarity` | `Basic` / `Common` / `Uncommon` / `Rare` 等，也认中文稀有度 |
| `mod` | 模组文件夹名 |
| `offset` / `limit` | 分页。`limit` 为 1–200，默认 40 |

返回 `total`、`offset`、`limit`、`cards`，以及筛选用的 `characters`、`types`、`rarities`、`costs`、`mods`。费用、类型不对、`offset` 不是整数、筛选里带 `..` 或空字节，是 400，一句说明，没有堆栈。

*`GET /api/cards` is read-only and paginated. `q` matches the Chinese name, the English name, the display name and the id (80 characters). `character` is a character id such as `claude`. `type` is `Attack`, `Skill`, `Power`, `Status` or `Curse` (Chinese type names are accepted). `cost` is `0`, `1`, `2`, …, `X`, or `none`. `rarity` is `Basic`, `Common`, `Uncommon`, `Rare`, and the rest (Chinese rarity names are accepted). `mod` is the mod folder name. `offset` / `limit` page the list; `limit` is 1–200 and defaults to 40. The body has `total`, `offset`, `limit`, `cards`, and the filter lists `characters`, `types`, `rarities`, `costs`, `mods`. A bad cost or type, a non-integer `offset`, or `..` or a null byte in a filter is a 400 with one sentence and no stack trace.*

## 保存 / Save

`POST /api/decks` 的 JSON：

```json
{
  "id": "mydeck",
  "name": "My deck",
  "mod": "claude_v34",
  "cards": [
    {"id": "YIHESHI", "count": 1, "upgrade": true},
    {"id": "XIAOBENBEN", "count": 2, "upgrade": false}
  ]
}
```

`character` 可以不写。模组只有一个角色时用那一个。`cards` 里同一张牌、同一种升级会合并。每张最多 15 张，一共最多 60 张。

校验走模拟器自己的 `ModSet`：模组要存在，角色要在这个模组里，每张牌要能被 `find_card` 找到（这套 mod 或内置状态牌），拼出来的 `id`、`id+`、`id×张数` 要能被 `parse_deck` 读懂。通过之后只写用户预设目录里的 `<id>.yaml`（默认是界面数据目录下的 `presets/`，也就是 `STS2SIM_GUI_DATA/presets`）。文件格式和 `experiments/*.yaml` 相同：`mods`、`decks`、`rooms`、`seed`、`agent`，另外 `rooms` 为空，`extra` 里一场 `encounter: DUMMY` 的训练木桩。这样没有本机怪物数据也能从新建测试开打。文件里多一个 `user_deck`，只给界面在这次测试自己的目录里生成临时 mod 用；交给模拟器的那份实验 YAML 会拿掉它。

*The `character` field can be omitted. A mod with one character uses that character. Copies of the same card and the same upgrade are merged. At most 15 of one card, and 60 cards in the deck.*

*Validation uses the simulator's own `ModSet`: the mod has to exist, the character has to belong to it, each card has to be found by `find_card` (that mod, or a built-in status card), and the `id` / `id+` / `id×count` line has to survive `parse_deck`. The only file written is `<id>.yaml` in the user presets folder (by default `presets/` under the GUI data directory, `STS2SIM_GUI_DATA/presets`). The shape matches `experiments/*.yaml`: `mods`, `decks`, `rooms`, `seed`, `agent`. `rooms` is empty, and `extra` is one training-dummy fight with `encounter: DUMMY`, so New test can start it without a local monster codex. `user_deck` in that file is only for the GUI, which builds a temporary mod inside that one run's folder. The experiment YAML handed to the simulator does not include `user_deck`.*

下面这些直接拒绝，不写出厂文件，正文里没有堆栈，也不回显提交的原文：

- id 不是「字母开头，只含字母、数字、下划线」
- id 已经是 `experiments/*.yaml` 或 `mods/` 里的一个模组
- `..`、斜杠、空字节，或正文里带 `path` / `filename` 一类字段
- 预设目录的真实路径不在界面数据目录里，或落在 `experiments/`、`mods/` 上
- 目标文件是符号链接，或目录本身是跳出去的符号链接
- 正文超过 64KB、不是 JSON、缺字段、类型不对
- 牌不存在、张数不在 1–15、角色不对

同一 id 再存一次会更新用户自己的那一份，不会去碰出厂预设。

*These are refused. Shipped files are not written. The body has no stack trace and does not echo the submitted value:*

- *an id that does not start with a letter, or that contains anything other than letters, digits and underscores*
- *an id that is already an `experiments/*.yaml` preset or a folder under `mods/`*
- *`..`, a slash, a null byte, or a `path` / `filename` field in the body*
- *a presets directory whose real path is outside the GUI data directory, or inside `experiments/` or `mods/`*
- *a target that is a symlink, or a presets directory that is a symlink pointing out*
- *a body over 64KB, a body that is not JSON, a missing field, or a wrong type*
- *an unknown card, a count outside 1–15, or a character the mod does not have*

*Saving the same id again replaces that user preset. Shipped presets stay untouched.*

界面上张数、费用曲线和攻击 / 技能 / 能力的比例随编辑更新。费用曲线是页面里的 SVG，不请求网络。存好之后，新建测试的预设下拉里会出现「名称 (id)」。选中它再开始，打的就是那一场木桩。

*On the page, size, the cost curve and the attack / skill / power split follow the deck as you edit. The curve is an SVG in the page. It does not load anything from the network. After a save, New test's preset list shows "name (id)". Choosing it and starting runs that one dummy fight.*

## MCP

`list_cards` 和 `GET /api/cards` 是同一份牌。成功时 `ok` 和 `read_only` 都是 true。`save_deck(deck)` 的 `deck` 是上面的 JSON 文本（也可以是对象）。成功时 `ok` 为 true，并带 `file`（只有文件名）。两条在 `--import-only` 里也有，因为它们不需要本机游戏数据。失败是 `{"ok": false, "error": "..."}`，不抛异常。

*`list_cards` is the same list as `GET /api/cards`. On success `ok` and `read_only` are both true. `save_deck(deck)` takes the JSON above as text (or as an object). On success `ok` is true and `file` is the file name only. Both tools are on `--import-only`, because they do not need a local game install. A failure is `{"ok": false, "error": "..."}` and does not raise.*
