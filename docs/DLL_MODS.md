# 导入游戏 mod 的 DLL / Importing a game mod DLL

[← 写 mod](MODDING.md) · [开发者文档](DEVELOPER.md)

DeckBench 最初用来给一套原创内容（Claude娘）做数值测试。作者如果已经有一份装在游戏里的 mod，不应该为了试数字再把每张牌手写成 YAML。这一页是现在能走的路，以及为什么不能把 DLL 原样执行。

*DeckBench started as a place to test numbers for one original mod. If you already have a mod installed in the game, you should not have to hand-write every card as YAML just to try the numbers. This page is the path that works today, and why the DLL cannot be executed as-is.*

## 为什么不能直接跑 DLL / Why the DLL cannot just be run

整局模拟跑的是你本机 `sts2.dll` 转译出来的 Python，不是游戏的 .NET 运行时，也没有 Godot。社区 mod 是对着游戏程序集编译的 C#：

- 卡牌是 `CardModel` 的子类，数值在构造函数和 `CanonicalVars` / `OnPlay` 里
- 启动用清单 JSON（`id`、`has_dll`、`dependencies`…）加上同名 DLL，入口是 `ModInitializer`
- 很多 mod 还会 `PatchAll`（Harmony）、加载自己的 `.pck`、依赖 BaseLib

这些调用打在游戏的 CLR 类型上。Python 端口里没有那些类型的真实实例，Harmony 补丁也不会打过来。把 `sts2.dll` 和 mod DLL 放进进程里执行，等于再做一个无头版游戏，而且仓库不能带任何游戏文件。

所以这一版做的是**读取** DLL，而不是运行它。

*Full runs execute the Python translation of your local game assembly, not the game's .NET runtime, and not Godot. A community mod is C# compiled against the game: cards subclass the game's card model, a manifest JSON plus a same-named DLL is the loader contract, and the entry point is an initializer attribute. Many mods also patch with Harmony, ship a `.pck`, and depend on BaseLib. Those calls target the live CLR. The Python port does not host those objects, and Harmony does not apply to it. Loading the game assembly and the mod in-process would be a second headless game, and this repo ships no game files. This version reads the DLL. It does not run it.*

## 现在能做什么 / What works now

1. 找到 mod 文件夹。游戏是这样装的：`<游戏>/mods/<Id>/<Id>.json` 和 `<Id>.dll`（`.pck` 可有可无）。
2. 用元数据列出卡牌、能力、遗物、药水、角色类，以及 `ModInitializer` 指向的方法名。这一步不执行代码。
3. 如果本机有和首次生成同一套的 ilspycmd，并且找得到你的游戏安装，就只反编译**这个 mod 的 DLL**（用游戏目录做引用，用完即删）。引用在时，枚举会是名字；引用不在时，ilspy 会把枚举打成数字，那些数字**不会**被猜成攻击/稀有度/关键词。
4. 直线效果翻成现有 YAML：伤害、格挡、抽牌、能量、治疗、`PowerCmd.Apply<某个能力>`、升级时加减的数值、关键词（名字，不是数字）、遗物稀有度、能力的回合开始/结束和战斗开始。
5. 在模组编辑器里打开。你看提示，改错的地方，再保存。保存之后和手写 YAML 走同一条整局试跑。

*1. Find the mod folder the game loads: `<game>/mods/<Id>/<Id>.json` and `<Id>.dll` (a `.pck` is optional). 2. Metadata lists card, power, relic, potion and character classes, plus the initializer method. Nothing is executed. 3. If ilspycmd is installed the same way as first-run setup, and your game install can be found, only that mod DLL is decompiled (the game directory is a reference, and the output is deleted). With references, enums stay names. Without them, the decompiler prints numbers, and those numbers are not guessed into attack/rarity/keywords. 4. Straight-line effects become the existing YAML: damage, block, draw, energy, heal, apply-power, upgrade deltas, keywords given by name, relic rarity, and turn-start / turn-end / combat-start triggers. 5. The mod editor opens the result. Read the notes, fix what is wrong, then save. After that it is the same full-run test as hand-written YAML.*

## 已支持的直线效果 / Supported straight-line effects

| C# | YAML |
|---|---|
| `DamageCmd.Attack`（`WithHitCount`、`TargetingAll*`、`TargetingRandom*`） | `damage`（`hits`、`target: all` / `random`） |
| `CreatureCmd.GainBlock` | `block` |
| `CardPileCmd.Draw` | `draw` |
| `PlayerCmd.GainEnergy` / `LoseEnergy` | `energy` |
| `CreatureCmd.Heal` | `heal` |
| `PowerCmd.Apply<T>` | `apply`（类名 → id，如 `StrengthPower` → `STRENGTH`） |
| `DynamicVars.X.UpgradeValueBy` / `EnergyCost.UpgradeBy` | `upgrade.vars` / `upgrade.cost` |
| `CardKeyword.Name`（名字，不是数字） | `keywords` |
| `RelicRarity.Name` | 遗物 `rarity` |
| `AfterTurnStart` / `AfterTurnEnd` / `BeforeCombat`（及同类钩子） | `turn_start` / `turn_end` / `battle_start` |

`if` / 循环 / 选项 / 还不认识的命令整段留空。覆盖这些映射的合成源码在 `tests/fixtures/dllmod/`（核心五类）和 `tests/fixtures/dllmod/extra/`（上表其余项）。ilspycmd 仍是可选的。

*A branch, loop, choice, or unmapped command blanks that method. Synthetic coverage lives in `tests/fixtures/dllmod/` (the core five types) and `tests/fixtures/dllmod/extra/` (the rest of this table). ilspycmd stays optional.*

## 作者怎么试 / How to try it

图形界面：左侧 **模组编辑器**。

- **导入游戏 mod**：选一个 zip。zip 里是一个 mod 目录（清单 JSON + DLL）。不要把游戏本身打进去。
- 如果 DeckBench 找得到游戏，下拉框里会列出 `mods/` 下带清单的 mod，点一个即可。

命令行（在仓库根目录，`PYTHONPATH` 含仓库根，或直接用下面这句）：

```bash
python tools/import_dll_mod.py --list
python tools/import_dll_mod.py "/path/to/Slay the Spire 2/mods/MyMod" --out /tmp/mymod
python tools/batch.py --mod /tmp/mymod --char MyHero --agent modai --n 20
```

`--no-decompile` 只列类型，不反编译。`--json` 打印报告。导入结果先给编辑器（或 `--out` 的文件夹），按保存才会进界面的 mod 目录。

*Desktop app: **Mod editor** on the left. **Import game mod** takes a zip of one mod folder (manifest JSON + DLL). Do not zip the game itself. If DeckBench can see the install, the dropdown lists manifest mods under `mods/`. Command line, from the repo root:*

```bash
python tools/import_dll_mod.py --list
python tools/import_dll_mod.py "/path/to/Slay the Spire 2/mods/MyMod" --out /tmp/mymod
python tools/batch.py --mod /tmp/mymod --char MyHero --agent modai --n 20
```

*`--no-decompile` lists types only. `--json` prints the report. Nothing is saved into the app's mod folder until you press Save (or pass `--out`).*

## 已知限制 / Known limitations

- DLL 不执行。Harmony、Godot 场景、`.pck` 里的图都不进模拟。
- 有 `if` / 循环 / 选项 / 自定义命令的方法，效果留空，并标明。不会把「有时才发动」写成「每次都发动」。
- 没有反编译到方法体时，类还在列表里，但类型是占位，检查不会通过，不能拿去跑。
- 没有游戏程序集做引用时，枚举数字不猜测。找到游戏安装后重新导入。
- 施加的原版能力按类名转成模拟器能找到的 id（`StrengthPower` → `STRENGTH`）。对不上时，编辑器里改成游戏里的 id。
- 只加在铁甲战士等原版卡池里的牌，不会自动变成一个新角色。要整局试跑，就在编辑器里建角色、起始牌组，或把牌放进你自己的角色。
- 导进来的数字没有和真游戏逐张对过。比强弱之前，先用同一套种子打一小批，核对一场战斗。
- 仓库和安装包都不含游戏文件。反编译的临时目录用完删除。请不要把导入出的、带有你不打算公开的文本的文件夹提交进这个仓库。

*The DLL is not executed. Harmony, Godot scenes and pictures inside a `.pck` are not simulated. Methods with branches, loops, choices or custom commands keep a blank effect and a note, so a conditional effect is not imported as always-on. Without a method body, the class is listed but its type is a placeholder and Check will not pass. Enum numbers are not guessed when the game assembly was not a reference; import again after the install is found. A base-game power is mapped from its class name (`StrengthPower` → `STRENGTH`); if that misses, edit the id. Cards registered only into a base character's pool do not become a new character — add a character and a starting deck in the editor before a full run. Imported numbers are not matched card-by-card against the live game; check one fight on a shared seed before you compare balance. The repo and the package contain no game files. Decompiler output is deleted. Do not commit an imported folder if it holds text you do not want to publish.*

## 以后 / Later

下一段才是「更接近真 DLL」：把反编译出的 mod C# 送进现有的 `cs2py` 转译器，注册到本机的 `ModelDb` 上，仍然不跑 Harmony 和 Godot。转译器是按游戏版本打补丁的，mod 里常见的源生成器、BaseLib 辅助函数和补丁方法现在过不了。这一版先把能安全变成 YAML 的部分跑通，避免在没有游戏文件的情况下假装整份 DLL 已经在模拟器里执行。

*The next step toward running the real DLL is to send the decompiled mod C# through the existing translator and register it on the local model database, still without Harmony or Godot. That translator is patched per game version, and source generators, BaseLib helpers and patch methods that mods use do not pass through it today. This version ships the part that can safely become YAML, rather than pretending the whole DLL is already running inside the simulator without any game files.*
