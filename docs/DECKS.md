# 组牌 / Deck builder

[← 文档索引](INDEX.md) · [MCP](MCP.md) · [模组格式](MODDING.md)

侧栏「组牌」（`#/decks`）用来浏览模拟器已经认识的牌，组成一套牌，勾选要打的遭遇，存成战斗预设。新建测试里选这份预设就能开打，自定义战斗也可以直接勾选遭遇。存好的预设还可以做留一法，看每张牌对胜率、掉血和回合的影响。不改模拟器的出牌、种子和 AI，也不改 `experiments/` 里的出厂预设、`mods/`、种子或已有配置。

*Deck builder (`#/decks`) browses the cards the simulator already knows, builds a deck, ticks the encounters it should run, and saves a combat preset. New test can start that preset immediately, and a custom combat test can tick encounters too. A saved preset can also run leave-one-out, to see how each card moves win rate, HP lost and turns. Simulator play, seeds and AI stay as they are. Shipped presets under `experiments/`, `mods/`, seeds and existing configs are not changed.*

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

## 遭遇 / Encounters

`GET /api/encounters` 只读，分页。名单是模拟器自己会打的遭遇：`encounter_pool` 按幕和房间（普通 / 精英 / 首领）筛过、怪物和血量都在的那些。训练木桩 `DUMMY` 始终算模拟器认识的遭遇，没有本机怪物数据时名单里只有它。弱怪、组成里缺怪物、或者没有血量的遭遇不出现。不改遭遇数据，也不写文件。

* `GET /api/encounters` is read-only and paginated. The list is the encounters the simulator itself would run: what `encounter_pool` keeps for an act and a normal, elite, or boss room, after monsters and hit points are present. The training dummy `DUMMY` is always an encounter the simulator knows. With no local monster codex, the list is only that dummy. Weak fights, encounters with a missing monster, and encounters with no hit points are left out. Encounter data is not modified, and nothing is written.*

| 参数 | 作用 |
| --- | --- |
| `q` | 子串，同时匹配中文名、英文名和 id。最长 80 |
| `act` | `1`、`2` 或 `3` |
| `room` | `normal` / `elite` / `boss`，也认 `普通` / `精英` / `首领` 和 `Monster` / `Elite` / `Boss` |
| `offset` / `limit` | 分页。`limit` 为 1–200，默认 40 |

返回 `total`、`offset`、`limit`、`encounters`（每条有 `id`、`name_zh`、`name_en`、`act`、`room`）、`probe`（训练木桩）、`acts`、`rooms`、`gauntlets`，以及 `full_turns`（出厂整场回合上限）和 `turn_limit`（允许的最大回合，200）。连战不是另一份名单：`act1_elite` 就是第 1 幕精英里 `encounter_pool` 返回的全部遭遇，第 2、3 幕和普通、首领同样现算。空的连战不出现。`offset` 不是整数、`limit` 超出 1–200、幕或房间不对、筛选里带 `..` 或空字节，是 400，一句说明，没有堆栈。

*`q` matches the Chinese name, the English name and the id (80 characters). `act` is `1`, `2` or `3`. `room` is `normal`, `elite` or `boss` (Chinese room names and `Monster` / `Elite` / `Boss` are accepted). `offset` / `limit` page the list; `limit` is 1–200 and defaults to 40. The body has `total`, `offset`, `limit`, `encounters` (each with `id`, `name_zh`, `name_en`, `act`, `room`), `probe` (the training dummy), `acts`, `rooms`, `gauntlets`, `full_turns` (the shipped full-fight cap) and `turn_limit` (the highest cap that can be saved, 200). A gauntlet is not a second roster: `act1_elite` is every Act 1 elite `encounter_pool` returns, and the same is built for acts 2 and 3 and for normal fights and bosses. An empty gauntlet is omitted. A non-integer `offset`, a `limit` outside 1–200, a bad act or room, or `..` or a null byte in a filter is a 400 with one sentence and no stack trace.*

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
  ],
  "encounters": [
    {"id": "DUMMY", "fights": 1},
    {"id": "SOME_ELITE", "fights": 2}
  ]
}
```

`encounters` 和 `gauntlet` 都可以不写。都不写时仍是一场训练木桩（`encounter: DUMMY`，1 场，1 回合）。`encounters` 里每一项是 `{id, fights}`，也可以只写遭遇 id。`fights` 是这种遭遇打几场，1 到 100 的整数。`gauntlet` 取上面的连战 id，例如 `act1_elite`；可选的顶层 `fights` 是这一组里每种遭遇的场数，默认 1。两组一起给时，连战先展开，同 id 的显式项再盖过场数。同一份预设最多 40 种遭遇、合计最多 400 场。

`max_turns` 是这一份预设里每一场的回合上限，写在文件顶层，也写进 `extra` 的每一行（模拟器打额外遭遇时用的是这一行自己的 `max_turns`）。不写时：名单里只有训练木桩，就是 1 回合；只要有一场不是木桩，就用出厂 `experiments/*.yaml` 顶层共用的那个整场上限（它们不一致时取出现最多的；和 `run_fight` 的默认打平则用默认）。自己写的话必须是 1 到 200 的整数，和新建测试里最大回合的上限一样。超过、不是整数，是 400，一句说明，没有堆栈。

*`encounters` and `gauntlet` can both be omitted. Omitting both is still one training-dummy fight (`encounter: DUMMY`, one fight, one turn). Each `encounters` item is `{id, fights}`, or just an encounter id. `fights` is how many times that encounter is fought, a whole number from 1 to 100. `gauntlet` is one of the ids above, such as `act1_elite`. Optional top-level `fights` is the count for each encounter in that gauntlet, and defaults to 1. When both are sent, the gauntlet is expanded first and an explicit item with the same id replaces its fight count. One preset holds at most 40 encounters and 400 fights in total.*

*`max_turns` is the turn cap for every fight in the preset. It is stored at the top of the file and on each `extra` row, because the simulator uses the row's own `max_turns` for an extra encounter. When it is omitted, a dummy-only list is 1 turn. Any other encounter uses the full-fight cap shared by the top-level `max_turns` of the shipped `experiments/*.yaml` files (the value that appears most often when they differ; a tie with the `run_fight` default uses that default). An explicit value has to be a whole number from 1 to 200, the same ceiling as max turns on New test. Past that ceiling, or not an integer, is a 400 with one sentence and no stack trace.*

`character` 可以不写。模组只有一个角色时用那一个。`cards` 里同一张牌、同一种升级会合并。每张最多 15 张，一共最多 60 张。

校验走模拟器自己的规则。牌：模组要存在，角色要在这个模组里，每张牌要能被 `find_card` 找到（这套 mod 或内置状态牌），拼出来的 `id`、`id+`、`id×张数` 要能被 `parse_deck` 读懂。遭遇：id 必须是 `DUMMY`，或者 `encounter_pool` 会拿去打的那一场；连战也只从这份池子展开。通过之后只写用户预设目录里的 `<id>.yaml`（默认是界面数据目录下的 `presets/`，也就是 `STS2SIM_GUI_DATA/presets`）。文件格式和 `experiments/*.yaml` 相同：`mods`、`decks`、`rooms`、`seed`、`agent`，另外 `rooms` 为空，`extra` 里每种勾选的遭遇一行（`encounter`、`fights`、`max_turns`、幕和房间）。模拟器本来就会按 `extra` 打这些遭遇，出牌、种子和 AI 都不改。没有本机怪物数据时仍可以只打训练木桩。文件里多一个 `user_deck`，只给界面在这次测试自己的目录里生成临时 mod 用；交给模拟器的那份实验 YAML 会拿掉它。

*The `character` field can be omitted. A mod with one character uses that character. Copies of the same card and the same upgrade are merged. At most 15 of one card, and 60 cards in the deck.*

*Validation uses the simulator's own rules. For cards, the mod has to exist, the character has to belong to it, each card has to be found by `find_card` (that mod, or a built-in status card), and the `id` / `id+` / `id×count` line has to survive `parse_deck`. For encounters, the id has to be `DUMMY` or an encounter `encounter_pool` would actually run; a gauntlet expands from that same pool. The only file written is `<id>.yaml` in the user presets folder (by default `presets/` under the GUI data directory, `STS2SIM_GUI_DATA/presets`). The shape matches `experiments/*.yaml`: `mods`, `decks`, `rooms`, `seed`, `agent`. `rooms` is empty, and `extra` has one row per ticked encounter (`encounter`, `fights`, `max_turns`, act and room). The simulator already runs those `extra` rows. Play, seeds and AI are unchanged. With no local monster codex the preset can still be the training dummy alone. `user_deck` in that file is only for the GUI, which builds a temporary mod inside that one run's folder. The experiment YAML handed to the simulator does not include `user_deck`.*

下面这些直接拒绝，不写出厂文件，正文里没有堆栈，也不回显提交的原文：

- id 不是「字母开头，只含字母、数字、下划线」
- id 已经是 `experiments/*.yaml` 或 `mods/` 里的一个模组
- `..`、斜杠、空字节，或正文里带 `path` / `filename` 一类字段
- 预设目录的真实路径不在界面数据目录里，或落在 `experiments/`、`mods/` 上
- 目标文件是符号链接，或目录本身是跳出去的符号链接
- 正文超过 64KB、不是 JSON、缺字段、类型不对
- 牌不存在、张数不在 1–15、角色不对
- 遭遇不在模拟器会打的名单里、场数不在 1–100、超过 40 种或合计超过 400 场、连战 id 对不上或那一组是空的、回合上限不在 1–200

同一 id 再存一次会更新用户自己的那一份，不会去碰出厂预设。

*These are refused. Shipped files are not written. The body has no stack trace and does not echo the submitted value:*

- *an id that does not start with a letter, or that contains anything other than letters, digits and underscores*
- *an id that is already an `experiments/*.yaml` preset or a folder under `mods/`*
- *`..`, a slash, a null byte, or a `path` / `filename` field in the body*
- *a presets directory whose real path is outside the GUI data directory, or inside `experiments/` or `mods/`*
- *a target that is a symlink, or a presets directory that is a symlink pointing out*
- *a body over 64KB, a body that is not JSON, a missing field, or a wrong type*
- *an unknown card, a count outside 1–15, or a character the mod does not have*
- *an encounter the simulator would not run, a fight count outside 1–100, more than 40 encounters or 400 fights in total, a gauntlet id that does not match or is empty, or a turn cap outside 1–200*

*Saving the same id again replaces that user preset. Shipped presets stay untouched.*

界面上张数、费用曲线和攻击 / 技能 / 能力的比例随编辑更新。费用曲线是页面里的 SVG，不请求网络。遭遇列表可以按幕和房间筛选，勾选几种并给每种设场数。连战按钮（例如第 1 幕精英）用上面的 `gauntlets` 一次勾上那一组。存好之后，新建测试的预设下拉里会出现「名称 (id)」。选中它再开始，打的就是勾选的那些遭遇；没改过选择时仍是一场木桩。

组牌页上可以改最大回合。只留着训练木桩时显示 1；勾了别的遭遇、又没自己改过，就显示 `GET /api/encounters` 返回的 `full_turns`（出厂整场上限）。新建测试的自定义战斗里也可以勾选遭遇、给每种设场数，或点同一个连战。勾了之后这次测试打这些遭遇，不再从房间里随机抽；最大回合数用这一页上的设置。

*On the page, size, the cost curve and the attack / skill / power split follow the deck as you edit. The curve is an SVG in the page. It does not load anything from the network. The encounter list filters by act and room. Tick several and set the fights on each one. A gauntlet button (for example Act 1 elites) ticks that whole group from `gauntlets`. After a save, New test's preset list shows "name (id)". Choosing it and starting runs the encounters you ticked. Leaving the selection alone is still one dummy fight.*

*The deck builder has a max-turns field. A dummy-only preset shows 1. After another encounter is ticked, and the field has not been edited, it shows `full_turns` from `GET /api/encounters` (the shipped full-fight cap). New test's custom combat can tick encounters, set fights on each one, or use the same gauntlet. With any ticked, that test runs those encounters instead of drawing at random from the rooms, and each fight uses the max turns on that page.*

## MCP

`list_cards` 和 `GET /api/cards` 是同一份牌。`list_encounters` 和 `GET /api/encounters` 是同一份遭遇，含 `gauntlets`。成功时 `ok` 和 `read_only` 都是 true。`save_deck(deck)` 的 `deck` 是上面的 JSON 文本（也可以是对象），可以带 `encounters` 和 `gauntlet`。成功时 `ok` 为 true，并带 `file`（只有文件名）和 `encounters`。三条在 `--import-only` 里也有，因为它们不需要本机游戏数据；没有怪物数据时遭遇名单只有训练木桩。失败是 `{"ok": false, "error": "..."}`，不抛异常。

*`list_cards` is the same list as `GET /api/cards`. `list_encounters` is the same list as `GET /api/encounters`, including `gauntlets`. On success `ok` and `read_only` are both true. `save_deck(deck)` takes the JSON above as text (or as an object), including optional `encounters` and `gauntlet`. On success `ok` is true, `file` is the file name only, and `encounters` lists the ids. All three tools are on `--import-only`, because they do not need a local game install. With no monster codex the encounter list is only the training dummy. A failure is `{"ok": false, "error": "..."}` and does not raise.*

## 对打 / Head-to-head

组牌页上「卡组 A 对卡组 B」选两份已经保存的用户预设。`POST /api/decks/head_to_head` 用界面已有的战斗测试各跑一遍：同一份遭遇、同一个回合上限、同一颗种子。不写 `encounters` / `gauntlet` / `max_turns` / `seed` 时，用第一份预设（A）里存的那些。自己写了才覆盖。名单的规则和保存预设一样：遭遇必须是模拟器会打的，每种 1–100 场，最多 40 种，合计最多 400 场。两套牌各打这一份名单。种子写进两份实验的 `seed`，战斗仍走 `sts2sim.runner` 原来的播种（种子、卡组、幕、房间、场次、遭遇一起算），不另写一套随机。

请求在两场都**开始**之后就返回，不等它们打完。正文有 `status: "running"`、`a`、`b`（两次测试的 id）、`seed`、`max_turns`、`encounters`、`fights` 和 `compare`（`/#/compare?a=&b=`）。页面上是进度条和「取消两边」。`GET /api/runs/<id>/progress` 看每一侧打完几场、当前遭遇和用时。两场都变成 `done` 之后才打开对比。对比仍是原来的格子和单卡差值。两套牌的 id 不一样，所以格子按幕和房间配对（这一侧只有一套牌时）；同一侧有不止一套牌就不猜。见 [COMPARE.md](COMPARE.md)。

同一份预设选两次、预设不存在、不是用户预设、`..`、空字节、类型不对、回合不在 1–200、超过 400 场，都是 400，一句说明，没有堆栈，也不回显提交的原文。不改出厂预设、`mods/`、种子算法或 AI。

MCP `head_to_head(a, b, encounters="", gauntlet="", max_turns=None, seed=None)` 做同一件事，也是马上返回。`encounters` 是上面的 JSON 数组文本。成功的 JSON 和 HTTP 相同。失败是 `{"ok": false, "error": "..."}`，不抛异常。`--import-only` 也有这个工具：训练木桩不需要本机游戏数据，真正开打用的仍是原来的战斗测试。进度和取消是 `run_progress` / `cancel_run`。

## 单卡贡献 / Card impact

组牌页上「单卡贡献」选一份已经保存的用户预设。`POST /api/decks/<id>/card_impact` 用已有的战斗测试做留一法：先打基线，再对每一种牌（同一 id、同一种升级算一种）打一份少一张的变体。`plus: true` 时再为每种牌打一份多一张的变体；已经有 15 张的不再加，记在 `skipped` 里，原因是 `count`。遭遇、种子、回合上限和卡组 id 都和基线相同。卡组 id 不变，所以 `sts2sim.runner` 原来的播种（种子、卡组、幕、房间、场次、遭遇）不变。不另写一套出牌。

全体变体合计最多 400 场，和一份预设自己的上限是同一个数。默认 `scale: true`：放不下就按原来的场数比例缩小每种遭遇（最大余数法），所有变体共用缩小后的那一份名单。`scale: false`，或者缩到每个变体 1 场仍超过 400，是 400，`too_many_fights`，一句说明，没有堆栈，也不开跑。拿掉一张就会把牌组打空（牌组里只剩这一张）是 `ablation`。

请求在变体都**排队**之后就返回，不等打完。正文有 `id` / `job`（父任务）、`runs`（基线和每个变体的测试 id）、`status: "running"`、`seed`、`max_turns`、`encounters`、`fights`（每个变体的场数）、`total_fights`、`scaled`。进度和取消用父任务 id：`GET /api/runs/<id>/progress`、`POST /api/runs/<id>/cancel`。取消不杀进程。正在打的那场打完，还没开始的变体不再派发。状态是 `cancelled`，`partial` 为 true。

`GET /api/decks/<id>/card_impact` 是这份牌组最近一次的结果。`GET /api/runs/<job>/card_impact` 是某一次父任务的结果，跑完或还在跑都可以读。每一行是变体减基线：`delta_win`、`delta_hp_lost`、`delta_turns`，以及 `n`。胜率带 Wilson 95% 区间。任一侧局数小于 30（`sample_warning`），`noisy_reason` 是 `too_small`；局数够了但两侧 Wilson 区间重叠，是 `wilson_overlap`。两种都让 `noisy` 为真。牌的名字来自模拟器已经加载的牌面，不另编。拿掉一张时，胜率差为负表示这张牌在帮胜率，掉血差为正表示它在少掉血。多一张时方向相反。`win_effect` / `hp_effect` 是 `helps`、`hurts` 或 `flat`。

`#/decks` 上是进度条、取消，和一张按差值排序的表。跑完的父任务在运行页上也能看到这张表。`GET /api/runs/<id>/export.html` 把同一张表写进离线 HTML。见 [EXPORT.md](EXPORT.md)。

MCP `card_impact(deck, job="", plus=false, scale=true, encounters="", gauntlet="", max_turns=None, seed=None)` 做同一件事。不写 `job` 就开跑并马上返回。写了 `job` 就只读那一次的结果。失败是 `{"ok": false, "error": "..."}`，不抛异常。`--import-only` 也有这个工具。训练木桩不需要本机游戏数据。

*Deck builder has **Card impact**. Pick one saved user preset. `POST /api/decks/<id>/card_impact` runs leave-one-out with the combat test that already exists: the baseline, then one variant per unique card (the same id and the same upgrade) with one copy removed. `plus: true` also runs one extra copy of each card. A card already at 15 copies is not increased; it is listed in `skipped` with reason `count`. Encounters, seed, turn cap and deck id match the baseline. The deck id does not change, so `sts2sim.runner` keeps its existing seeding (seed, deck, act, room, index and encounter together). There is no second play implementation.*

*Every variant together is at most 400 fights, the same cap as one preset. The default `scale: true` shrinks each encounter in proportion to its original fight count (largest remainder) when the total would not fit. Every variant shares that shorter list. `scale: false`, or a list that still exceeds 400 at one fight per variant, is a 400, `too_many_fights`, one sentence, no stack trace, and no run is started. A deck that would be empty after removing its only card is `ablation`.*

*The request returns once the variants are **queued**. It does not wait for them to finish. The body has `id` / `job` (the parent), `runs` (the baseline and each variant), `status: "running"`, `seed`, `max_turns`, `encounters`, `fights` (fights per variant), `total_fights` and `scaled`. Progress and cancel use the parent id: `GET /api/runs/<id>/progress` and `POST /api/runs/<id>/cancel`. Cancel does not kill the process. The fight in progress finishes, and variants that have not started are not dispatched. The status is `cancelled` and `partial` is true.*

*`GET /api/decks/<id>/card_impact` is the latest result for that deck. `GET /api/runs/<job>/card_impact` is one parent run, finished or still going. Each row is the variant minus the baseline: `delta_win`, `delta_hp_lost`, `delta_turns`, and `n`. Win rate includes a Wilson 95% interval. If either side has fewer than 30 fights (`sample_warning`), `noisy_reason` is `too_small`. If both sides are large enough and the Wilson intervals overlap, it is `wilson_overlap`. Either one sets `noisy`. Card names come from the cards the simulator already loaded. They are not invented. After a removal, a negative win-rate delta means the card was helping win rate, and a positive HP-lost delta means it was saving hit points. An added copy reads the other way. `win_effect` / `hp_effect` is `helps`, `hurts` or `flat`.*

*`#/decks` shows a progress bar, Cancel, and a table sortable by delta. A finished parent also shows the table on the run page. `GET /api/runs/<id>/export.html` writes the same table into the offline HTML. See [EXPORT.md](EXPORT.md).*

*MCP `card_impact(deck, job="", plus=false, scale=true, encounters="", gauntlet="", max_turns=None, seed=None)` does the same thing. Omit `job` to start and return immediately. Pass `job` to read that result and not start another run. A failure is `{"ok": false, "error": "..."}` and does not raise. `--import-only` exposes this tool too. A training dummy does not need a local game install.*

## 进度和取消 / Progress and cancel

新建测试、组牌预设、连战、对打和单卡贡献都可以是几百场。页面不再干等。单卡贡献的进度和取消用返回的父任务 id。`GET /api/runs/<id>/progress` 返回 `done`、`total`、`encounter`、`encounter_name`、`elapsed`（秒）、`status`、`partial`。轮询即可。新建测试（`#/new`）、组牌（`#/decks`）和对打面板上有进度条和取消。运行页（`#/run/<id>`）也显示当前遭遇。

`POST /api/runs/<id>/cancel` 和 MCP `cancel_run` 不杀进程。工人在两场之间停下：正在打的那场打完，还没开始的不再派发。状态记成 `cancelled`，`partial` 为 true。打完的场次留在 `raw.jsonl` 或 `runs.jsonl` 里，报告开头写明是部分结果。对比和导出读这些结果，不抛栈；还在跑的仍是 400 / 409。见 [COMPARE.md](COMPARE.md)、[EXPORT.md](EXPORT.md)、[MCP.md](MCP.md)。

*Deck builder has **Deck A vs deck B**. Pick two saved user presets. `POST /api/decks/head_to_head` runs each one with the combat test the GUI already uses: the same encounters, the same turn cap, and the same seed. Omit `encounters`, `gauntlet`, `max_turns` and `seed` to keep what the first preset (A) stored. An override uses the same rules as saving a preset: an encounter the simulator runs, 1–100 fights each, at most 40 encounters, and at most 400 fights in total. Each deck runs that list. The seed is written on both experiments. Fights still use `sts2sim.runner`'s existing seeding (seed, deck, act, room, index, encounter together). There is no second random source.*

*The request returns as soon as both tests have **started**. It does not wait for them to finish. The body has `status: "running"`, `a` and `b` (the two test ids), `seed`, `max_turns`, `encounters`, `fights` and `compare` (`/#/compare?a=&b=`). The page shows a progress bar and **Cancel both**. `GET /api/runs/<id>/progress` is how far each side has got, the current encounter, and the elapsed time. The comparison opens when both are `done`. It is still the existing cell and card deltas. The two deck ids differ, so a cell lines up by act and room when that side has one deck there. More than one deck on a side is not guessed. See [COMPARE.md](COMPARE.md).*

*The same preset twice, an unknown id, a preset that is not a saved user deck, `..`, a null byte, a wrong type, a turn cap outside 1–200, or more than 400 fights is a 400 with one sentence and no stack trace. The submitted text is not echoed. Shipped presets, `mods/`, the seeding, and the AI are unchanged.*

*MCP `head_to_head(a, b, encounters="", gauntlet="", max_turns=None, seed=None)` does the same thing and also returns immediately. `encounters` is the JSON array above, as text. Success is the same JSON as HTTP. A failure is `{"ok": false, "error": "..."}` and does not raise. `--import-only` exposes this tool too. A training dummy does not need a local game install. The fights themselves are still the existing combat test. Progress and cancel are `run_progress` / `cancel_run`.*

## Progress and cancel

*New test, a saved deck, a gauntlet, a head-to-head and a card impact can be hundreds of fights. The page does not sit and wait. Card impact progress and cancel use the parent id from the response. `GET /api/runs/<id>/progress` returns `done`, `total`, `encounter`, `encounter_name`, `elapsed` (seconds), `status` and `partial`. Polling is enough. **New test** (`#/new`), **Deck builder** (`#/decks`) and the head-to-head panel show a progress bar and Cancel. The run page (`#/run/<id>`) shows the current encounter too.*

*`POST /api/runs/<id>/cancel` and MCP `cancel_run` do not kill the process. The worker stops between fights: the one in progress finishes, and fights that have not started are not dispatched. The status is `cancelled` and `partial` is true. Finished fights stay in `raw.jsonl` or `runs.jsonl`, and the report says the result is partial. Compare and export read those results and do not raise. A test that is still running is still a 400 / 409. See [COMPARE.md](COMPARE.md), [EXPORT.md](EXPORT.md) and [MCP.md](MCP.md).*
