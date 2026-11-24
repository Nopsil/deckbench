# 本机游戏版本 / Local game version

DeckBench 不附带游戏文件。整局模拟用的是你本机 `python -m sts2sim.gamedata setup` 从自己的 `sts2.dll` 生成的缓存。下面是 **2026-11-21** 用一份真实安装生成并跑过的结果。换一份安装，角色和内容以那份 DLL 生成出来的 `ModelDb` 为准，不要把这一节的数字当成所有版本的清单。

*DeckBench ships no game files. A full run uses the cache `python -m sts2sim.gamedata setup` builds from your own `sts2.dll`. The rows below are from one real install, generated and executed on 2026-11-21. Another install follows whatever `ModelDb` that DLL generates. These counts are not a catalog for every version.*

## 跑过的安装 / The install that was executed

| | |
| --- | --- |
| 版本 / version | v0.113.1，分支 public-beta，Steam build **26660232** |
| `release_info.json` | commit `d09d48e5`（产品版本里的完整提交是 `d09d48e516cfd24314c1781f662787904f894aa8`），date `2026-11-14T02:31:11+00:00`，branch `v0.113.1` |
| 实际反编译并跑过的 DLL | Mac osx-arm64 `sts2.dll`，10,647,040 字节，SHA-256 `a671e9efb86a7b80405133105665867b053c787670d475b4347cf5ccc15cb5fb` |
| 同一 Steam build 的 Windows DLL | SHA-256 `62ecbe91093e1fa862de4329aac865209dcb297804caf0f0520d92d8c0b4a9c3`。二进制没有放到这台机器上，**没有**用它生成或开局 |
| 转译 | ilspycmd 9.1.0.7988，`translator_rev` 3。2622 个类型里 6 个类型有转译失败的成员，见下文 |

这不是 2026-11-14 那份 v0.113.0 / commit `16ac0fe3` / build 26625880，也不是仓库里曾经写过的 v0.111 验证。v0.111 的 DLL 这次没有重跑。

*This is not the 2026-11-14 v0.113.0 handoff (commit `16ac0fe3`, build 26625880), and it is not a re-run of the older v0.111 check. No v0.111 DLL was executed this time.*

## 角色 / Characters

`ModelDb.AllCharacters` 给出 6 个可玩角色，顺序是安装里的顺序：**Ironclad、Silent、Regent、Necrobinder、Defect、Fool**。

Fool 的 C# 类型是 `MegaCrit.Sts2.Core.Models.Characters.Fool`。本地化键是 `FOOL`（英文标题 The Fool，简体中文标题 愚者）。卡牌键 `THE_FOOL` 是另一张牌，不是这个角色。Deprived、DeprecatedCharacter、RandomCharacter、RotatingCharacter 在角色文件里，但不在 `AllCharacters` 里，界面不提供。

这一份生成结果里，Fool 的起始生命是模型自己的 `StartingHp`（读出来是 77），起始牌是 `STRIKE_FOOL`×5、`DEFEND_FOOL`×4、`FOOLISH_SHOT`，起始遗物是 `SONG_BOW`。这些数是跑起来时从模型读到的，不是写死在仓库里的表。

`tests/test_engine.py` 在这份缓存上 **9 项通过**：六个角色各一局进阶 10（种子是测试里原有的 `T1`），Defect 同一种子两局一致，Ironclad 进阶 0 和进阶 10 不是同一局，Silent 的 Gym 冒烟。另外六个角色在进阶 0、种子 `ASCSEED00001` / `EVENTSEED0001` / `FOOLSEED0001` 上各跑完一局，`error` 都是空的。Fool 的 `FOOLSEED0001` 与 `DETSEED00001` 各跑两遍，路径、战斗、选牌、层数、胜负、牌组、遗物一致。

*Fool's C# type is `MegaCrit.Sts2.Core.Models.Characters.Fool`. The localization key is `FOOL`. The card key `THE_FOOL` is a different card. On this generated cache, `tests/test_engine.py` passed 9 tests, including one ascension-10 run per playable character. Six characters also finished ascension 0 on three fixed seeds with `error` empty.*

## 模型数量和本地化 / Model counts and localization

本地化是从这份 Mac 安装的 `.pck` 解出的 eng / zhs 表，只在内存里对过 id，没有写进仓库。

| 种类 | 生成的 `ModelDb` | eng 表里的 id | 两边都有 | 只有本地化、没有类型 |
| --- | ---: | ---: | ---: | ---: |
| 可玩角色 | 6 | 11（多出来的是 DEPRECATED / DEPRIVED / LOCKED / RANDOM / ROTATING） | 6 | 5 个非可玩键 |
| 牌 | 717 | 745 | 717 | 28 |
| 遗物 | 316 | 324 | 316 | 8 |
| 药水 | 69 | 69 | 69 | 0 |
| 事件（`AllEvents`） | 62 | 68 | 62 | 6 个占位键：DEPRECATED_EVENT、ERROR、GENERIC、MOCK_EVENT_MODEL、PROCEED、SHARED_EVENT_INFO |
| 遭遇 | 85 | — | — | — |
| 能力 | 322 | — | — | — |
| 远古 | 8（NEOW、OROBAS、PAEL、TEZCATARA、NONUPEIPE、TANX、VAKUU、DARV） | — | — | — |

只有本地化、程序集里没有对应类型的牌和遗物，模拟器不会生成，也不标成已支持。事件房走生成代码。进阶 0 的几局里实际进入过的事件 id 包括 `NEOW`、`ROOM_FULL_OF_CHEESE`、`JUNGLE_MAZE_ADVENTURE`、`SELF_HELP_BOOK`、`WOOD_CARVINGS`、`WHISPERING_HOLLOW`。战斗 id 包括 `SHRINKER_BEETLE_WEAK`、`SLIMES_WEAK`、`BYGONE_EFFIGY_ELITE` 等。没有把 62 个事件逐个打一遍。

*Cards and relics that exist only as localization strings, with no type in this assembly, are not simulated and are not marked supported. A handful of event and encounter ids were entered during ascension-0 runs. The other events were not each played.*

## 转译失败、仍不能当支持 / Members that did not translate

这 6 个类型有成员变成 `cs_broken`。调用到它们会抛错，不能算支持：

- `PlayerChoiceResult.FromNetData`：多人联机选牌结果的反序列化。单机开局用的其它 `From*` 能生成。
- `EnergyIconHelper.GetPool`：能量图标，不是战斗数值。
- `LocManager` 的格式化加载，以及三个 JSON 序列化上下文的 `GetTypeInfo`：本地化文本另从你的 `.pck` 或 `DECKBENCH_GAME_LOC_*` 读，不靠这几个失败成员。

## 旧版 YAML 战斗模拟器 / Legacy YAML combat simulator

同一份 Mac `sts2.dll` 和从 `.pck` 解出的 eng / zhs 表，用 `python -m sts2sim.gamedata setup` 里的导出（也可以 `python -m sts2sim.legacycodex`）写进缓存的 `legacy-codex/`。`codex_stamp.json` 记着 format 1、`dll_sha256`、版本 `v0.113.1`、commit `d09d48e5`。已经校验过的缓存不会再去读没盖戳的 `data/spire-codex/`。要故意用别的目录，设置 `DECKBENCH_CODEX_DIR`；那份目录若带戳且哈希和当前 DLL 不同，加载会拒绝。这些 JSON 不进仓库。

*The same Mac `sts2.dll` and the eng / zhs tables from the `.pck` were exported by the step inside `python -m sts2sim.gamedata setup` (or `python -m sts2sim.legacycodex`) into `legacy-codex/` in the cache. `codex_stamp.json` records format 1, the DLL SHA-256, version `v0.113.1` and commit `d09d48e5`. A verified cache does not read an unstamped `data/spire-codex/`. `DECKBENCH_CODEX_DIR` points somewhere else on purpose; a stamp whose hash is not this DLL is refused. The JSON is not in the repository.*

| 种类 | 这次写出的目录 | 说明 |
| --- | ---: | --- |
| 怪物 | 122 | 跳过 `Deprecated*` / `Mock*`。没有自己状态机的子类沿基类抄出招和血量 |
| 遭遇 | 90 | 跳过 `DeprecatedEncounter`。80 个挂在幕上，10 个没有幕（事件战，不进普通/精英/首领池） |
| 牌 | 716 | 跳过 `DeprecatedCard`。整局引擎的 `AllCards` 是 717 |
| 遗物 | 316 | 和 `ModelDb` 的 316 一致 |
| 药水 | 67 | `Models/Potions` 里 68 个类型去掉 `DeprecatedPotion`。`Mocks` 目录没进。整局引擎数过 69 |
| 能力 | 308 | 只来自 `Models/Powers`。整局引擎的能力数是 322 |
| 角色 | 9，其中可玩 6 | `IsPlayable => false` 的不标成可玩。可玩的是 Ironclad、Silent、Regent、Necrobinder、Defect、Fool |

`monster_ai.json` 123 条（含 4 条从基类继承），没有未解析语句。`encounter_monsters.json` 90 条：82 条组成固定，7 条随机，1 条是空的 `DEPRECATED_ENCOUNTER`。先前解析成「缺失」的 `SLIMES_WEAK`、`OVICOPTER_NORMAL`、`DENSE_VEGETATION_EVENT_ENCOUNTER`、`SLITHERING_STRANGLER_NORMAL` 现在有组成。第 1 幕池把 Overgrowth 和 Underdocks 都算进 Act 1（弱怪 8、普通 22、精英 6、首领 6）。第 2 幕普通/精英/首领是 10 / 3 / 3，第 3 幕是 9 / 3 / 3。

直译进旧战斗效果的牌是 148 张（只有 OnPlay 里的伤害和格挡）。愚者 90 张里 26 张是这种。其余只进双语索引。

愚者这条是目录里读出来的，不是写死的：生命 77，能量 3（角色没覆盖 `MaxEnergy`，用的是默认 3），金币 99，起始牌 `STRIKE_FOOL`×5（6，升级 9）、`DEFEND_FOOL`×4（5，升级 8）、`FOOLISH_SHOT`（15，升级 20，标记 `arrow`），起始遗物 `SONG_BOW` 在战斗开始施加 6 层 `AIM`。单独打一发：有弓时愚蠢射击打 21 然后瞄准清掉；没有弓是 15；打击仍是 6，瞄准还在。旧模拟器没有箭袋，这张牌不检查还有没有箭。

种子 7、最多 12 回合，同一场打两遍，结果相同。都是赢：

| 遭遇 | 回合 | 剩余生命 |
| --- | ---: | ---: |
| `NIBBITS_WEAK` | 3 | 69 |
| `NIBBITS_NORMAL` | 7 | 63 |
| `SLIMES_WEAK` | 3 | 74 |
| `OVICOPTER_NORMAL` | 7 | 56 |
| `DENSE_VEGETATION_EVENT_ENCOUNTER` | 6 | 58 |
| `SLITHERING_STRANGLER_NORMAL` | 5 | 56 |
| `BYGONE_EFFIGY_ELITE` | 7 | 15 |
| `SHRINKER_BEETLE_WEAK` | 2 | 77 |
| `CULTISTS_NORMAL` | 7 | 58 |
| `THE_KIN_BOSS` | 3 | 42 |

`NIBBITS_NORMAL` 前四回合两边分别是 SLICE/HISS/BUTT/SLICE 和 HISS/BUTT/SLICE/HISS。`CULTISTS_NORMAL` 先 INCANTATION，再四次 DARK_STRIKE。这是旧模拟器的出招，不是客户端逐招回放。

*Fool's row is what the export read: 77 HP, energy 3 because `MaxEnergy` is not overridden, 99 gold, the starter deck and `SONG_BOW` applying 6 Aim. With the bow, Foolish Shot hit for 21 and Aim cleared; without it the hit was 15; Strike stayed 6 and Aim stayed. There is no quiver, so the card does not check for an arrow. Ten encounters at seed 7 were each won twice with the same result. Nibbit and cultist intent lines matched the sequences already used by the legacy tests. That is this simulator's move picker, not a client replay.*

仍不支持，或只是近似：

- 血量和招式用的是非进阶、非 Dread 的数。`IsDread() ? N : 0` 不加进去。
- 箭袋、多段箭的瞄准（只加在第一段上然后清掉）、召唤新敌人，都不模拟。
- 568 张牌、绝大多数遗物、全部药水，以及不是「进战斗施加一层能力」这种形状的遗物，只有索引。
- `SLIMES_WEAK` 的两只小史莱姆按每个位置独立抽，真代码是不放回。随机组成用的是模拟器自己的随机数。
- 没有挂在幕上的事件战不进 `encounter_pool`，只能按遭遇 id 打。
- 本地化没有自己的名字时，沿基类找，再不行就显示 id。
- Windows 那份 DLL 没有用来导出或打这些战斗。

*Still unsupported or approximate: numbers are non-ascension and non-Dread; no quiver; Aim on a multi-hit arrow card applies to the first hit and then clears; summons do not spawn; 568 cards, nearly all relics and every potion are index-only; the two small slimes in `SLIMES_WEAK` are drawn independently; event encounters with no act stay out of `encounter_pool`; a missing name walks the base class and otherwise stays the id. The Windows DLL was not used for this export or these fights.*

## 明确没做或没测 / Not done, or not tested

- Windows 那份 DLL 没有跑。
- 商店没买的商品不会写入地图历史。买下来的牌、遗物和药水走游戏自己的购买函数。
- mentor 的神经网络仍只覆盖原来那 5 个角色。Fool 的局外决策会按现有逻辑回退，不把 Fool 说成 mentor 已支持。
- 没有逐张牌、逐个遗物、逐瓶药水对过真游戏。进阶 10 的测试只证明这些种子能跑完且不报错，不证明每个新机制都和客户端一致。
