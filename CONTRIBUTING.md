# Contributing / 贡献指南

Thanks for helping! / 欢迎贡献！

## Hard rule: no game content / 硬性规定：不接受任何游戏内容

Pull requests that add or contain any of the following **will be rejected**:

- game files or binaries (`sts2.dll`, `.pck`, any file copied from the install)
- decompiled or transpiled game code (e.g. `sts2sim/gen/game.py`), or code mechanically generated from it
- extracted game data: card / relic / potion / monster / encounter tables, numbers dumped from the game,
  localization text, card or relic descriptions
- official art, icons, audio, fonts, or logos; trademarks in project or package names

以下内容的 PR **一律拒绝**：游戏文件或二进制（`sts2.dll`、`.pck`、任何从安装目录复制的文件）；反编译 / 转译得到的
游戏代码或由其机械生成的代码；从游戏中提取的数据（卡牌 / 遗物 / 药水 / 怪物 / 遭遇表、导出的数值、本地化文本、
卡面描述）；官方美术、图标、音频、字体、Logo；以及在项目或包名中使用商标。

Anything game-derived must be **generated locally** from the user's own install by
`python -m sts2sim.gamedata setup` and stays in the local cache. If your change needs new game-derived data,
extend the local generator instead of committing the data.

需要新的游戏派生数据时，请扩展本机生成器（`sts2sim/gamedata.py` / `tools/`），而不是提交数据本身。

## OK to contribute / 欢迎的内容

- simulator / AI / GUI code, your own mods (original cards and text you wrote), tests that don't need game data
- 模拟器、AI、界面代码；你自己原创的 mod（自己写的卡牌和文字）；不依赖游戏数据的测试

By contributing you agree your contribution is licensed under the MIT license in `LICENSE` (our own code only).
提交贡献即表示你同意以 `LICENSE` 中的 MIT 许可（仅限我们自己的代码）发布你的贡献。

## Checks / 检查

```bash
python -m pytest -q tests        # tests needing a local install are skipped automatically
```
