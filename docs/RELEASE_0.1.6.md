# DeckBench 0.1.6

DeckBench 0.1.6 于 2026-11-21 发布。Windows 下载文件名是 `DeckBench-0.1.6-win64.zip`。

这一版在 0.1.5 之后加上两块：界面里的自定义卡牌编辑器和失败回放，以及整局模拟对本机当前《杀戮尖塔2》安装的适配。仓库和安装包仍然不含游戏 DLL、完整本地化或反编译正文。

*DeckBench 0.1.6 was released on 2026-11-21. The Windows download is `DeckBench-0.1.6-win64.zip`.*

*After 0.1.5 this adds two pieces: a GUI custom-card editor and loss replay, and full-run adaptation to the Slay the Spire 2 install on your machine. The repository and the package still do not contain the game DLL, full localization, or decompiled bodies.*

这一版**不是**真机通关，也**不是**游戏全部内容都已支持。模拟跑完只说明生成出来的 Python 在这些种子上没有报错。

*This release is not a cleared run in the real game, and it is not support for every piece of game content. A finished simulation only means the generated Python reported no error on those seeds.*

## 已经验证的范围 / What was actually checked

- **Mac 真实 DLL，生成并整局跑过。** v0.113.1 public-beta，Steam build 26660232，commit `d09d48e516cfd24314c1781f662787904f894aa8`。osx-arm64 `sts2.dll` SHA-256 `a671e9efb86a7b80405133105665867b053c787670d475b4347cf5ccc15cb5fb`。可玩角色来自生成代码的 `ModelDb.AllCharacters`：Ironclad、Silent、Regent、Necrobinder、Defect、Fool。Fool 的本地化键是 `FOOL`（The Fool / 愚者）。卡牌键 `THE_FOOL` 是另一张牌。这份缓存上 `tests/test_engine.py` 9 项通过，包括六个角色各一局进阶 10。六个角色在进阶 0 的三颗固定种子上也跑完，`error` 为空。
- **Windows CI 通过，Windows 游戏 DLL 没有跑。** GitHub 上 Ubuntu 与 Windows 的 pytest，以及 Ubuntu 的 Playwright，在包含这些改动的提交上通过。同一次 Steam build 的 Windows `sts2.dll` SHA-256 是 `62ecbe91093e1fa862de4329aac865209dcb297804caf0f0520d92d8c0b4a9c3`，二进制没有用于生成或开局。
- **自定义卡牌和失败回放。** 可以在界面里写战斗引擎能执行的牌，保存后再打开，并用训练木桩或合成蛮兵测一套含这张牌的牌组。失败的战斗可以看当时记下的回合时间线。这两块不读取游戏 DLL。

*A real Mac DLL was decompiled, translated, and used for full runs: v0.113.1 public-beta, Steam build 26660232, commit `d09d48e516cfd24314c1781f662787904f894aa8`, osx-arm64 `sts2.dll` SHA-256 `a671e9efb86a7b80405133105665867b053c787670d475b4347cf5ccc15cb5fb`. Playable characters come from `ModelDb.AllCharacters`: Ironclad, Silent, Regent, Necrobinder, Defect, Fool. Fool's localization key is `FOOL`. The card key `THE_FOOL` is a different card. On that cache, `tests/test_engine.py` passed 9 tests, including ascension 10 for each of the six characters. The six characters also finished ascension 0 on three fixed seeds with an empty `error`. Windows and Ubuntu pytest, and Ubuntu Playwright, passed on the commit that contains this work. The Windows `sts2.dll` for the same Steam build (SHA-256 `62ecbe91093e1fa862de4329aac865209dcb297804caf0f0520d92d8c0b4a9c3`) was not used to generate or play a run. The custom-card editor and loss replay do not read the game DLL.*

## 没有验证、不要当成支持 / Not verified, and not support

- 旧的 YAML 战斗模拟器仍然需要一份**当前**的 spire-codex（`eng_` / `zhs_` 的 monsters、encounters、relics、potions、powers）。这次没有用旧缓存里的 codex，也没有拿解析出的 `monster_ai.json` 去打旧战斗测试。
- mentor 的神经网络仍只覆盖原来的五个角色。Fool 的局外决策按原有逻辑回退，不表示 mentor 已支持 Fool。
- 事件、卡牌、遗物、药水没有逐项和客户端对齐。进阶 0 的几局里实际进入过的事件包括 `NEOW`、`ROOM_FULL_OF_CHEESE`、`JUNGLE_MAZE_ADVENTURE`、`SELF_HELP_BOOK`、`WOOD_CARVINGS`、`WHISPERING_HOLLOW`。其余没有逐个打过。本地化里有类型对不上的牌和遗物，没有标成已支持。
- `PlayerChoiceResult.FromNetData`（多人选牌反序列化）、能量图标，以及几处本地化 / JSON 序列化成员仍然转译失败。
- 商店里没买的商品不写入地图历史。已经买下的物品走游戏自己的购买函数。
- v0.111 的 DLL 这次没有重跑。

*The legacy YAML combat simulator still needs a current spire-codex (`eng_` / `zhs_` monsters, encounters, relics, potions, powers). The old codex cache was not used, and the parsed `monster_ai.json` was not battle-tested on that simulator. Mentor networks still cover only the previous five characters. Fool falls back for out-of-combat choices; that is not mentor support for Fool. Events, cards, relics and potions were not checked one by one against the client. Ascension-0 runs did enter `NEOW`, `ROOM_FULL_OF_CHEESE`, `JUNGLE_MAZE_ADVENTURE`, `SELF_HELP_BOOK`, `WOOD_CARVINGS` and `WHISPERING_HOLLOW`. The rest were not each played. Localization strings with no matching type are not marked supported. `PlayerChoiceResult.FromNetData`, the energy-icon lookup, and a few localization / JSON serializer members still fail to translate. Unbought shop goods are not written into map history. A v0.111 DLL was not re-run.*

## 升级时要做的一件事 / One step after you upgrade

旧的 DeckBench 缓存没有 `translator_rev` 3，会被拒绝。用你自己的安装重新生成，不要分发生成结果：

```bash
python -m sts2sim.gamedata setup
```

*An older DeckBench cache has no `translator_rev` 3 and is refused. Regenerate from your own install. Do not redistribute the result:*

```bash
python -m sts2sim.gamedata setup
```

更细的计数和限制在 [GAME_SUPPORT.md](GAME_SUPPORT.md)。自定义卡牌见 [CUSTOM_CARDS.md](CUSTOM_CARDS.md)。失败回放见 [REPLAY.md](REPLAY.md)。
