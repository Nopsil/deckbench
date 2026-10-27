[简体中文](README.md) | [English](README.en.md) | **日本語** | [한국어](README.ko.md)

# DeckBench

**デッキのテストベンチ：ゲームを起動しなくても、AI が数百〜数千回のランを自動でプレイし、勝率・到達階層・死因・あるカードが本当に強いのかを教えてくれます。**
Slay the Spire 2 の Mod 作者とプレイヤー向けの、非公式バランステストツールです。

> **表示言語：** アプリは日本語・English・简体中文・한국어 に対応しています。最初は OS の言語で起動し、左下の言語メニューからいつでも切り替えられます（選んだ言語は保存されます）。カード・キャラクター・敵の名前も同じ言語で、あなた自身のゲームのインストールから読み込みます。

> **⚠️ 免責事項**
> - **非公式**：ファンによる制作物であり、Mega Crit とは無関係で、同社の承認・後援も受けていません。
> - **ゲームデータは一切含みません**：このリポジトリにはゲームファイル、ゲームのコード、ゲームデータは含まれていません。必要なものはすべて、あなた自身の PC 上で、あなた自身のゲームのインストールから生成され、そのインストールに紐付けられます（ゲームを入れ替えたり更新したりした場合は再生成されます）。
> - **ご自身の正規版ゲームが必要です**：Steam の通常版でも公開ベータ版でも構いません。ゲームが見つからない場合、プログラムはエラーを出して終了します。
> - **ゲームのリソースは受け付けません**：ゲームのコード、データ、テキスト、アートを含む PR はすべてお断りします（[CONTRIBUTING.md](CONTRIBUTING.md) を参照）。
> - **悪用は自己責任です**：本プロジェクトを利用してゲームのコードやファイルを配布した場合、その責任はすべて本人が負い、作者は一切関与しません。
> - **ライセンスの範囲**：[LICENSE](LICENSE)（MIT）が対象とするのは私たちが書いたコードのみで、ゲームのコード、データ、アート、商標についてはいかなるライセンスも付与しません。
> - Slay the Spire 2 は Mega Crit の商標です。ここでゲーム名を挙げているのは、どのゲーム向けのツールかを示すためだけです。
> - 連絡先：**nopsil@hotmail.com**（権利者の方で何か問題があればご連絡ください。速やかに対応します）
>
> <details><summary><b>Disclaimer (English)</b></summary>
>
> - **Unofficial**: fan-made; not affiliated with, endorsed or sponsored by Mega Crit.
> - **Ships no game data**: no game files, code or data in this repo. Everything game-related is generated on your own PC from your own install and bound to it (regenerated if the install changes or updates).
> - **Needs your own copy of the game**: Steam stable or public beta. The program exits with an error if it can't find the game.
> - **Game-asset PRs are rejected**: no game code, data, text or art (see [CONTRIBUTING.md](CONTRIBUTING.md)).
> - **Misuse is the misuser's responsibility**: anyone who uses this project to redistribute game code or files is solely responsible, not the authors.
> - **License scope**: [LICENSE](LICENSE) (MIT) covers only our own code and grants no license to any game code, data, art or trademarks.
> - Slay the Spire 2 is a trademark of Mega Crit; the name is used only to say which game this works with.
> - Contact: **nopsil@hotmail.com** (rights holders: please reach out, we'll respond promptly).
>
> </details>

## できること

- **勝率とどこまで進めるか**：キャラクター、アセンションのレベル、AI を選ぶと、AI が 1 回のランを最後まで自動でプレイします（マップ、戦闘、報酬、ショップ、イベント）。一度に数百ランを回して、勝率、平均到達階層、各アクトの突破率を確認できます。
- **死因の分析**：どの敵・どの戦闘でいちばん多く倒れているかを集計し、デッキの弱点をすぐに見つけられます。
- **カード単体の A/B テスト**：同じシードで、あるカードを入れたグループと入れないグループを比べ、そのカードで勝率と到達階層がどれだけ変わるかを直接確認できます。
- **自作 Mod のテスト**：サンプル Mod（Claude娘、オリジナルコンテンツ）を内蔵しているほか、自作の YAML Mod をアップロードして戦闘テストもできます。
- **GUI アプリ、すべてローカルで完結**：クリックで設定、ワンクリックで実行、リアルタイムの進捗表示、グラフ付きレポート、履歴。ネットには接続せず、何もアップロードしません。
- **4 つの表示言語**：日本語・English・简体中文・한국어。アプリ内で切り替えられ、カード・キャラクター・敵の名前もあなたのゲームから同じ言語で読み込みます。
- **実際のランを読み込む**：終わったランか進行中のセーブを読み取り専用で開き、シード、ルート、カード選択、レリックを見られます。
- **シードプレビュー**：シードを入れると、フルランをプレイせずにマップ、敵の分布、序盤報酬を見られます。

## はじめかた（Windows）

### いちばん簡単：パッケージ版をダウンロード

1. Steam で Slay the Spire 2 をインストールしておきます（通常版でもベータ版でも OK）。
2. [Releases ページ](https://github.com/Nopsil/deckbench/releases) から `DeckBench-<バージョン>-win64.zip` をダウンロードし、フォルダ（例：`D:\DeckBench`）に**丸ごと展開**します。
3. `DeckBench.exe` をダブルクリックします。初回起動時は「お待ちください」という表示が出て、ゲームからデータを生成します（1〜2 分ほど）。終わると画面が自動で開きます。
   **Python や .NET のインストールは不要です**（逆コンパイラは `decompiler` フォルダに同梱済み）。
4. ゲームを既定以外の場所にインストールしている場合は、そのフォルダで PowerShell を開き、一度だけ次を実行します：
   `.\DeckBench.exe --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"`。以降はダブルクリックだけで起動できます。

### ソースから実行する

**最初に一度だけやる準備**

1. **ゲームをインストール**：Steam で Slay the Spire 2 をインストールします（通常版でもベータ版でも OK）。
2. **Python 3.11 以降をインストール**：[python.org](https://www.python.org/downloads/) からダウンロードし、インストール時に **「Add python.exe to PATH」にチェック**を入れます。
3. **.NET 9 SDK をインストール**：[dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/9.0) から SDK をダウンロードしてインストールします（あなたの PC 上でゲームファイルを読み込むために使います）。
4. **Node.js（LTS 版）をインストール**：[nodejs.org](https://nodejs.org/) からダウンロードしてインストールします（初回に画面をビルドするときだけ使います）。
5. **ilspycmd をインストール**：**新しく** PowerShell のウィンドウを開いて、次を実行します：
   ```powershell
   dotnet tool install -g ilspycmd --version 9.1.0.7988
   ```
6. **DeckBench をダウンロード**：このページの **Code → Download ZIP** をクリックし、例えば `D:\deckbench` に展開します（git を使える方は `git clone` でも OK）。

**インストールと起動**

`D:\deckbench` フォルダで PowerShell を開き（フォルダ内の何もないところで Shift を押しながら右クリック →「PowerShell ウィンドウをここで開く」、または先に `cd D:\deckbench` を実行）、次を順番に実行します：

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-gui.txt
cd gui\web; npm install; npm run build; cd ..\..
.venv\Scripts\python -m gui.app
```

最初の 3 行は一度だけ実行すれば OK です。次回からは、このフォルダで最後の 1 行を実行するだけです：
```powershell
.venv\Scripts\python -m gui.app
```

**初回起動時**は Steam のゲームを自動で見つけ、必要なデータをあなたの PC 上で生成します。**1〜2 分**ほどかかります（その間はまだウィンドウが表示されないので、少しお待ちください）。2 回目以降はすぐに起動します。画面は専用のウィンドウで開きます。ウィンドウが開けない場合は、自動的にブラウザで開きます。

**ゲームが見つからない？** ゲームを既定以外の場所にインストールしている場合は、ゲームのフォルダを指定してください（パスはご自身のものに置き換えてください）：

```powershell
.venv\Scripts\python -m sts2sim.gamedata setup --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

または、起動前に環境変数を設定します（今のウィンドウでのみ有効）：
```powershell
$env:DECKBENCH_GAME_DIR = "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

Linux/macOS の場合は [docs/DEVELOPER.md](docs/DEVELOPER.md) を参照してください。

## どの AI を選ぶ？

- **「汎用 AI（おすすめ・Mod キャラでも使える）」**：ほとんどの場合はこれがおすすめです。カード選択・休憩所・ショップは小さなニューラルネットが担当し、コスト・ダメージ・ブロック・レアリティなどの汎用的な数値だけを見て、個々のカード名は見ません。そのため**自作の Mod キャラクターでも使えます**。速度は学習版と同じ（1 ランあたり 1〜2 秒）で、Windows でも使えます。私たちのテストでは、学習版より平均 1〜4 階層多く進みました。
- **「学習版 AI」**：前のバージョンでのおすすめです。速度は同じなので、比較用に使えます。
- **「spire-mentor フルラン AI」の 2 つ**：いちばん強いですが、サードパーティの spire-mentor をご自身でビルドする必要があり、ベースゲームの 5 キャラクターにしか対応していません。詳しくは [docs/DEVELOPER.md](docs/DEVELOPER.md) を参照してください。

## ゲームのシードで遊ばせる

「新規テスト → フルラン一括」で **「ゲームのシード指定」** に、ゲーム内に表示されるシード（例：`7F3K9Q2ZB8MA`）を入力すると、AI はその 1 ランだけをプレイし、各ステップで何を選んだかを記録します。記録は結果ページで確認できます。
小文字、英字の O と I は、ゲームと同じルールで自動的に大文字、数字の 0 と 1 に変換されます。コマンドラインの場合：`python tools/batch.py --char Silent --seed 7F3K9Q2ZB8MA --log-dir steps`。

## 実際のランを読み込む

左の **「ランを読み込む」** で、終わったラン（`history/*.run`）か進行中のセーブ（`current_run.save`）を読み取り専用で開けます。シード、アセンション、通った部屋、各階で選んだカード、レリック、デッキが見えます。セーブは変更しません。
コマンドライン：`python tools/import_run.py <ファイルまたはフォルダー>`。場所と 2 種類の JSON の違いは [docs/SAVE_FORMAT.md](docs/SAVE_FORMAT.md)（中国語・英語）。

## シードを先に見る

左の **「シードプレビュー」** にゲームのシード（キャラクターとアセンションも）を入れると、AI にフルランをプレイさせずに、各アクトのマップ、通常敵・エリート・ボスの並び、開始時の選択肢、最初の通常戦闘の報酬が見られます。録画するシード選びやルート計画に使えます。アクト 2 以降のマップは投影です。アクト 1 はゲームのスクリーンショットと照合できます。
コマンドライン：`python tools/seed_preview.py <シード> --char Ironclad --asc 0`。自分のインストールからデータを生成済みである必要があります。

## コードを書かずに MOD を作る（MODエディター）

左の **「MODエディター」** で、キャラクター（HP・エネルギー・初期デッキ・初期レリック）、カード（効果はメニューから選ぶ：ダメージを与える、パワーを付与、カードを引く…またはテンプレート）、パワーとレリック（「いつ → 何を」）をフォームで作れます。**「チェック」** で問題点をわかりやすく表示します。
**「テスト」** からワンクリックでフルラン一括、または 1 枚 A/B（同じシードで 初期デッキ と 初期デッキ＋このカード を比較）を実行できます。zip の読み込み・書き出しで共有もできます。
同じ YAML ファイルは `mods/` に置けばコマンドラインでも動きます：`python tools/batch.py --mod mods/my_mod --char MyHero --agent modai`。形式の説明は [docs/MODDING.md](docs/MODDING.md)（中国語・英語）。

## AI アシスタントに 1 手ずつプレイさせる（MCP）

Claude や Cursor など MCP に対応した AI アシスタントを使っているなら、シミュレーターの中で実際に 1 ラン遊ばせることができます。盤面を見て、選択肢を選び、理由を書き、やり直しもできます。最後に操作リストを書き出せるので、同じシードで実際のゲームをその通りにプレイできます。
現在はソースからの実行のみ対応しています：`pip install -r requirements-mcp.txt` のあと `python tools/mcp_server.py`。カード名は実行時にあなた自身のゲームのインストールから読み込みます。詳しくは [docs/MCP.md](docs/MCP.md) を参照してください。

## 結果の見かた

- **勝率**：最終ボスを倒せたランの割合です。
- **平均到達階層 / 各アクトの突破率**：AI が平均で何階まで進めたか、第 1・2・3 アクトを突破したランがどれだけあるか。勝率がとても低いとき（高アセンションなど）は、階層のほうが差がわかりやすくなります。
- **死因**：各ランがどの戦闘（どの敵 / エリート / ボス）で倒れたか。デッキが耐えられない場面を見つけるのに役立ちます。
- **カード単体の A/B**：2 つのグループは同じ乱数シードを使い、違いはそのカード 1 枚だけなので、差がそのままそのカードの影響になります。ラン数が少ないと差はブレやすく、ラン数が多いほど信頼できます。

**大切なこと**：AI は人間の上級者ではないので、これらの数字は**実際のプレイヤーの勝率ではありません**。**同じ設定の中で比べる**（新カード vs 旧カード、数値調整の前 vs 後、自作キャラ vs ベースゲームのキャラ）のには向いていますが、絶対的な強さの指標としては使えません。

## よくある質問

**「找不到游戏安装 / Game install not found」と表示される**
Steam でゲームがインストールされているか確認し、上記の `--game-dir` または `DECKBENCH_GAME_DIR` でゲームのフォルダ（`...\steamapps\common\Slay the Spire 2`）を指定してください。

**ゲームがアップデートされた / ベータブランチに切り替えた**
生成したデータは、その時点のゲームファイルに紐付いています。ファイルが変わると古いデータは使われません。アプリは次回起動時に自動で再生成します（同じく 1〜2 分）。手動で実行することもできます：
`.venv\Scripts\python -m sts2sim.gamedata setup`

**Windows で「強い AI（探索あり）」と「学習版 AI（探索あり）」が出てこないのはなぜ？**
探索付きの AI には OS の fork 機能が必要ですが、Windows にはないため、画面では自動的に非表示になります。Windows では探索を使わない **「汎用 AI（おすすめ・Mod キャラでも使える）」** がおすすめです。

**なぜ自分のゲームが必要なの？**
私たちはゲームの内容を一切配布できませんし、配布もしません。DeckBench はあなたの PC 上であなた自身のゲームを読み込み、そのルールをシミュレートするだけなので、正規版のゲームがないと使えません。

**`npm` で「スクリプトの実行が無効」というエラーが出る**
コマンド中の `npm` を `npm.cmd` に置き換えてください（例：`npm.cmd install; npm.cmd run build`）。

**ilspycmd が見つからない / ilspycmd が必要と表示される**
.NET 9 SDK をインストールしたら、PowerShell のウィンドウを**新しく開き直して**から `dotnet tool install` の行を実行し、DeckBench を起動し直してください。

## さらに詳しく

- [docs/DEVELOPER.md](docs/DEVELOPER.md)：コマンドラインでの一括実行（全オプション）、初回データ生成の仕組み、オプションの spire-mentor AI、旧版の戦闘シミュレーター、フォルダ構成、テスト（Linux/macOS 用コマンドを含む）。
- オプションのより強い AI：サードパーティの [spire-mentor](https://github.com/tfriedel/spire-mentor) をご自身でビルドすると、`mentor-full` が使えます（戦闘は MCTS、戦闘外の判断は PPO ネットワークが担当。ベースゲームの 5 キャラクターのみ対応）。spire-mentor は本プロジェクトには同梱されていません。v0.111 で追加された 19 枚の新カード（SIDESTEP など）の読み込みに既知の問題があり、小さなローカルパッチを用意しています。詳しくは [docs/DEVELOPER.md](docs/DEVELOPER.md#可选spire-mentor更强的-ai--optional-spire-mentor) を参照してください。
- [docs/MODDING.md](docs/MODDING.md)：YAML + Python で自分の Mod を作る方法（カード、パワー、レリック、デッキ、実験）。
- [gui/README.md](gui/README.md)：GUI アプリの構成とパッケージ化。
- [CONTRIBUTING.md](CONTRIBUTING.md)：コントリビュートのルール（ゲームのコンテンツは一切受け付けません）。

## ライセンス

MIT。対象は私たちが書いたコードのみです。詳しくは [LICENSE](LICENSE) を参照してください。
