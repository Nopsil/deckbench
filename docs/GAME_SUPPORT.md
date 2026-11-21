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

## 明确没做或没测 / Not done, or not tested

- Windows 那份 DLL 没有跑。
- 旧版 YAML 战斗模拟器仍要当前的 spire-codex（`eng_`/`zhs_` 的 monsters、encounters、relics、potions、powers）。这次没有用旧缓存里的 codex。setup 会在缓存里写出 `monster_ai.json`（这份安装 119 条）和 `encounter_monsters.json`（90 条），那是给旧战斗模拟器用的解析结果，**没有**拿它跑旧战斗测试，也不随仓库分发。
- 商店没买的商品不会写入地图历史。买下来的牌、遗物和药水走游戏自己的购买函数。
- mentor 的神经网络仍只覆盖原来那 5 个角色。Fool 的局外决策会按现有逻辑回退，不把 Fool 说成 mentor 已支持。
- 没有逐张牌、逐个遗物、逐瓶药水对过真游戏。进阶 10 的测试只证明这些种子能跑完且不报错，不证明每个新机制都和客户端一致。
