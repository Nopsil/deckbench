# 本机游戏版本 / Local game version

DeckBench 不附带游戏文件。整局模拟用的是你本机 `python -m sts2sim.gamedata setup` 从自己的 `sts2.dll` 生成的缓存。下面是 **2026-11-24** 用同一份 Mac v0.113.1 安装重新生成并实际执行过的结果。换一份安装，角色和内容以那份 DLL 生成出来的 `ModelDb` 为准。这些数字不是所有版本的清单，模拟器跑通也不等于和真机客户端逐项对齐。

*DeckBench ships no game files. A full run uses the cache `python -m sts2sim.gamedata setup` builds from your own `sts2.dll`. The rows below were generated from the same Mac v0.113.1 install and executed on 2026-11-24. Another install follows whatever `ModelDb` that DLL generates. A simulator run finishing is not client-by-client parity.*

## 跑过的安装 / The install that was executed

| | |
| --- | --- |
| 版本 / version | v0.113.1，分支 public-beta，Steam build **26660232** |
| `release_info.json` | commit `d09d48e5`（产品版本里的完整提交是 `d09d48e516cfd24314c1781f662787904f894aa8`），date `2026-11-14T02:31:11+00:00`，branch `v0.113.1` |
| 实际反编译并跑过的 DLL | Mac osx-arm64 `sts2.dll`，10,647,040 字节，SHA-256 `a671e9efb86a7b80405133105665867b053c787670d475b4347cf5ccc15cb5fb` |
| 同一 Steam build 的 Windows DLL | SHA-256 `62ecbe91093e1fa862de4329aac865209dcb297804caf0f0520d92d8c0b4a9c3`。二进制没有放到这台机器上，**没有**用它生成或开局 |
| 转译 | ilspycmd 9.1.0.7988，`translator_rev` 4。`catch (Type name)` 会绑定这个名字；更窄的 `catch` 不再把后面的分支一起吞掉。2622 个类型里 6 个类型仍有转译失败的成员，见下文 |

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

只有本地化、程序集里没有对应类型的牌和遗物，模拟器不会生成，也不标成已支持。

*Cards and relics that exist only as localization strings, with no type in this assembly, are not simulated and are not marked supported.*

## 这次实际执行过的 / Executed this pass

强制进入 `AllEvents` 的 62 个事件（规范模型，不是可变克隆）。每个选项在一局新的愚者、进阶 0 上点过。事件战在修复前不会进房；下面的战斗数字是修复之后单独复测的。

| 范围 | 结果 |
| --- | --- |
| 62 个事件进房 | 61 个直接进房。`FAKE_MERCHANT` 修复前抛 `AttributeError`（没有 `SetMerchantInventory`），修复后进房并摆出 6 件有库存的遗物 |
| 选项 | 130 个初始选项都调用了对应函数且没有抛错。`THE_FUTURE_OF_POTIONS` 在 0 瓶药水时是 0 个选项；另测了先拿到 2 瓶愚者药水再进房，出现 2 个选项，选第一个后药水从 2 变成 1，事件结束 |
| 事件战 | `BATTLEWORN_DUMMY` 三个设置都打完对应遭遇（V1/V2/V3，各 4 回合，胜）并结束事件。`DENSE_VEGETATION` 的战斗、`PUNCH_OFF` 的战斗、`THE_LANTERN_KEY` 的战斗都会进入战斗房。起始牌组打后面三场会阵亡，这是这副牌打输了，不是进房失败 |
| 愚者牌 | 牌池 90 张都在 `SLIMES_WEAK` 里尝试打出。89 张打出且不抛错。`ENRAPTURE` 是多人专用、目标是友方，单机没有目标，所以不能打出 |
| 愚者遗物 / 药水 | 遗物池 8 个（含起始 `SONG_BOW`）各进了一场战斗并结束一回合，不抛错。`Fool4Epoch` 的 3 瓶药水都能获得并在战斗里使用 |
| 瞄准 | 进战斗时 `AIM_POWER` 是 6。`FOOLISH_SHOT` 基础伤害 15，打在没有格挡的敌人身上掉 21 点生命 |
| 整局 | 愚者进阶 0 种子 `FOOLSEED0001`、`FOOLSEED0002`，进阶 1 种子 `ASCSEED00001`，进阶 10 种子 `FOOLSEED0001`，`error` 都是空的。四局都没赢。这只说明这些种子能跑完，不说明机制和客户端一致 |

*All 62 events were force-entered on a fresh Fool ascension-0 run, and each initial option was invoked. Event combats did not start before the adapter fix; the combat rows above are from a retest after that fix. 89 of 90 Fool cards were played in `SLIMES_WEAK` without raising. `ENRAPTURE` is multiplayer-only and targets an ally, so a solo fight has no legal target. The 8 Fool relics and 3 Fool potions were triggered without raising. Starting Aim is 6, and `FOOLISH_SHOT` (15 base) removed 21 life from an unblocked enemy. Four Fool runs finished with an empty `error` and no victory.*

## 数值核对 / Numbers checked against this DLL

下面的预期来自这份 Mac DLL 转译出来的模型变量和方法，不是真机客户端录像。`tests/test_v01131_numbers.py` 在有缓存时会锁住这些数。

| 项 | 依据（生成代码里的变量） | 预期 | 实测 |
| --- | --- | --- | --- |
| 愚人一击 | 伤害 15，起始瞄准 6，射完扣光 | 21，瞄准变 0，箭槽 1→0，贯穿计数 3 | 一致 |
| 没箭再射 | `ShootArrowAtTarget` 没有箭就不攻击 | 伤害 0，牌仍然打出 | 一致 |
| 箭袋后再射两支 | 箭袋 +1 槽；第一击把瞄准扣光 | 21，然后 15 | 一致 |
| 连射 | 伤害 3，段数 3，整次只消耗 1 支箭 | 27，瞄准变 0 | 一致 |
| 重射 | 伤害 20，瞄准乘 2 | 32 | 一致 |
| 打死目标 | 目标死亡时拔箭 | 箭回到可用 | 一致 |
| 贯穿 3 段 | 有力量的攻击每段把计数减 1 | 打击各 6 伤，第三下把箭拔回 | 一致 |
| 哇爆 | 伤害 14；本回合打过啾或叽则打两段 | 14，打过哇啾之后 28 | 一致 |
| 哇啾 + 暴和弦 / 曲径 | 第一张哇额外造成层数伤害，第一张啾额外给层数格挡 | 8 伤 7 格挡，第二张只有 3 伤 3 格挡 | 一致 |
| 哇啾叽 + 摇篮曲 7 | 牌面 9 伤 9 格挡；这一张同时算三种旋律 | 9 伤，16 格挡，旋律数 3 | 一致 |
| 振作 / 生长 | 2 悲伤 + 2 喜悦；每张悲伤 4 层伸展后消耗 | 伸展 8，手里不再有悲伤 | 一致 |
| 倦怠 | 能力 2 层，悲伤张数先加 1；抽牌 5+2 | 下一手 8 张，其中 1 张悲伤 | 一致 |
| 箭术 | 下一次己方回合开始 +4 瞄准 | 6 变成 10 | 一致 |
| 图章戒指 | `GoldVar(888)`，拿到立刻加金币 | +888 | 一致 |
| 密林硬闯 | 掉 8 血，金币是 61 到 99 的掷数 | 生命和金币按掷数变化 | 一致 |
| 这个还是那个（朴素） | 掉 6 血，金币是 41 到 68 的掷数 | 按掷数变化 | 一致 |
| 深渊浴场浸泡 | 最大生命 +2（当前生命跟着加），再受 3 点伤害 | 77/77 变成 76/79 | 一致 |
| 远古进房 | `BeforeEventStarted` 把缺少的生命补满 | 6 点生命进 Darv 后变成满血 | 一致 |
| 召唤铃 | 往牌组加 1 张 `CURSE_OF_THE_BELL` | 诅咒数 0→1，不是整副牌复制 | 一致 |
| 破旧假人，时限内打死 | 时限能力从 3 开始；没超时就给奖励 | 立刻杀死会拿到 1 瓶药水，事件结束，战斗只记 1 场 | 一致 |

路径上的金币和生命是**进房时**记的，房间里拿到的戒指、治疗要到下一行才出现。

## 四条种子 / Four seeds

用愚者、进阶 0、沿第一选项走，并把战斗立刻结束，只为了看地图和资源。这不是当时那次实验的 AI，也不是真机。

- `H10JAE5MB36Y`：第 34 层是远古 `NONUPEIPE`。它的选项里有图章戒指（`SignetRing`，立刻 +888）和 looming fruit（最大生命 +31，并且当前生命跟着加）。这条路径拿到的是 looming fruit，生命 84/84→115/115，金币没有跳 888。若另一条路径在约 122 金时拿了图章戒指，下一层进房记录就会是 1010。122+888=1010，对得上遗物变量，不是把金币乘错。
- `LCB7CXRC4SAT`：远古进房会把生命补满。二幕 Boss 后如果最大生命是 79、当前是 6，下一场远古在进房时就会变成 79/79。这是 `AncientEventModel.BeforeEventStarted`，不是战斗结束时偷偷回满。这条种子用第一选项走到第 6 层就结束了，没有复现到二幕 Boss。
- `T6GKA6T0ZVYD`：破旧假人只进了一次战斗房（`BATTLEWORN_DUMMY_EVENT_V1_ENCOUNTER`），然后事件结束。以前重复点，是因为战斗同步器是空的，选项停在原页，驱动又选了一次。现在一选就进战斗。假人的时限是 3，超时逃脱会记成战斗结束但没有奖励；时限内杀死才会给药水。
- `QX01MYN3V1G8`：牌组没有被复制。起始 5 张打击、4 张防御还在计数里。诅咒在 Darv 之后从 0 变成 1，遗物里有召唤铃，铃只加一张 `CURSE_OF_THE_BELL`。

## 已知限制或不支持 / Known limits

- `FAKE_MERCHANT` 是自定义界面。库存能建出来。买东西和扔腐化药水要 `NFakeMerchant` 节点，模拟器没有这个界面，所以不会买、也不会因此进 `FAKE_MERCHANT_EVENT_ENCOUNTER`。
- `PunchOff.PunchEachOther` 仍是空函数。原来的循环只播动画，同步执行会卡死。
- 6 个类型仍有 `cs_broken` 成员，调用会抛错：`PlayerChoiceResult.FromNetData`（多人选牌反序列化）、`EnergyIconHelper.GetPool`（能量图标）、`LocManager` 的格式化加载，以及三个 JSON 序列化上下文的 `GetTypeInfo`。单机战斗不靠这几个成员。
- 商店没买的商品仍然不写入地图历史。
- mentor 的神经网络仍只覆盖原来那 5 个角色。Fool 的局外决策会回退，不把 Fool 说成 mentor 已支持。
- Windows 那份 DLL（SHA-256 `62ecbe91093e1fa862de4329aac865209dcb297804caf0f0520d92d8c0b4a9c3`）没有在这台机器上生成或开局。

## 仍未覆盖 / Not covered

- 没有把 90 张愚者牌、8 个遗物、3 瓶药水的数值和客户端逐条对过。上面「数值核对」只覆盖表里那几条，而且依据是这份 DLL 的生成代码，不是真机录像。
- 130 个选项里，只有上面点名的事件战和药水交易对过状态变化。其余选项只确认调用没有抛错。
- 深渊浴场的「继续浸泡」被连续选了 8 次都没有抛错，没有把「离开」那条分支单独当战斗来测。
- 旧版 YAML 战斗模拟器这次没有跑。setup 仍会写出 `monster_ai.json`（119 条）和 `encounter_monsters.json`（90 条），不随仓库分发。
