DeckBench（牌组测试台）Windows 版
================================

不进游戏，让 AI 自动打几百上千局，告诉你胜率、能打到第几层、死在哪、某张卡强不强。
非官方粉丝工具，与 Mega Crit 无关。

使用方法
--------
1. 先在 Steam 里安装《杀戮尖塔 2》（正式版或公开测试版都行）。必须是你自己的游戏。
2. 把整个压缩包解压到一个文件夹（例如 D:\DeckBench），不要只拿出 exe。
3. 双击 DeckBench.exe。
   第一次启动会弹出「请稍候」提示，从你电脑上的游戏生成需要的数据，大约 1–2 分钟，完成后界面自动打开。
   不需要另外安装 Python 或 .NET。
4. 找不到游戏时会弹窗提示。游戏装在非默认位置的话，在 DeckBench 文件夹里打开 PowerShell 运行一次：
   .\DeckBench.exe --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
   （换成你自己的游戏路径；之后直接双击即可，游戏更新后再次启动会自动重新生成。）

生成的数据保存在 %LOCALAPPDATA%\deckbench\，只属于你这份游戏安装，请勿分发。
你的测试记录保存在本文件夹的 data\ 里。

可选：更强的整局 AI（spire-mentor，不在这个压缩包里）
------------------------------------------------
「新建测试 → 整局批量」里有两项「spire-mentor 整局 AI」。本压缩包不含它的程序、模型或数据。
要用它筛种子：自己构建 spire-mentor，然后在本文件夹（DeckBench.exe 旁边）新建 mentor.local.json，
写上 site、py、python 三个路径。python 必须是构建 sts2_rs 的那个 python.exe。
重新打开 DeckBench 后这两项才能点。只适合 5 个原版角色。
跑完看日志里的回退比例；几乎全部回退时，不要用那次胜率做判断。
步骤、冒烟命令和原因见源码文档 docs/DEVELOPER.md。不要把 mentor.local.json 或构建结果发给别人。

免责声明：本软件不含任何游戏文件、代码或数据；需要你自己的正版游戏。任何人利用本项目分发游戏代码或文件，
责任由其本人承担，与作者无关。LICENSE（MIT）只覆盖我们自己的代码，不授予任何游戏代码、数据、美术或商标的许可。
Slay the Spire 2 是 Mega Crit 的商标。第三方组件见 THIRD-PARTY-NOTICES.txt。
联系：nopsil@hotmail.com    源码与说明：https://github.com/Nopsil/deckbench

--------------------------------------------------------------------------------
DeckBench for Windows

An unofficial deck test bench: the AI plays hundreds or thousands of runs and tells you the win rate, how far you get,
what kills you, and whether a card is strong. Fan-made; not affiliated with Mega Crit.

1. Install Slay the Spire 2 on Steam (stable or public beta). You need your own copy.
2. Extract the whole zip to a folder (e.g. D:\DeckBench).
3. Double-click DeckBench.exe. The first launch shows a "please wait" box while it generates data from your own
   install (about 1-2 minutes); the app opens when done. No Python or .NET installation needed.
4. If the game isn't found, run once in PowerShell inside the folder (then just double-click from then on):
   .\DeckBench.exe --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"

Generated data lives in %LOCALAPPDATA%\deckbench\ and is bound to your install - do not redistribute it.

Optional stronger full-run AI (spire-mentor, not in this zip)
-------------------------------------------------------------
New test → Full runs lists two "spire-mentor" agents. This zip does not include that program, its models, or its data.
To screen seeds with it, build spire-mentor yourself and add mentor.local.json next to DeckBench.exe with site, py, and python.
python must be the python.exe that built sts2_rs. Restart DeckBench; the two entries stay grey until then.
Base-game characters only. If the log shows almost every decision falling back, do not trust that win rate.
Steps, the smoke command, and why the exe cannot load the library itself are in docs/DEVELOPER.md in the source tree.
Do not send mentor.local.json or your build to anyone else.

Disclaimer: ships no game files, code or data; requires your own copy. Anyone who misuses this project to redistribute
game code or files is solely responsible. LICENSE (MIT) covers only our own code and grants no license to game code,
data, art or trademarks. Slay the Spire 2 is a trademark of Mega Crit. Third-party components: THIRD-PARTY-NOTICES.txt.
Contact: nopsil@hotmail.com
