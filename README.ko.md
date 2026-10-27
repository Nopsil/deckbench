[简体中文](README.md) | [English](README.en.md) | [日本語](README.ja.md) | **한국어**

# DeckBench

**덱 테스트 벤치: 게임을 켜지 않아도 AI가 수백~수천 판을 자동으로 플레이하고, 승률, 몇 층까지 가는지, 어디서 죽는지, 어떤 카드가 정말 센지 알려 줍니다.**
Slay the Spire 2 모드 제작자와 플레이어를 위한 비공식 밸런스 테스트 도구입니다.

> **언어:** 프로그램은 한국어, English, 简体中文, 日本語를 지원합니다. 처음에는 운영체제 언어로 시작하고, 왼쪽 아래 언어 메뉴에서 언제든 바꿀 수 있습니다(고른 언어는 저장됩니다). 카드, 캐릭터, 적 이름도 같은 언어로, 여러분이 설치한 게임에서 읽어 옵니다.

> **⚠️ 면책 조항**
> - **비공식**: 팬이 만든 도구로, Mega Crit과 관련이 없으며 Mega Crit의 승인이나 후원을 받지 않았습니다.
> - **게임 데이터를 일절 포함하지 않음**: 이 저장소에는 게임 파일, 게임 코드, 게임 데이터가 없습니다. 필요한 내용은 모두 여러분의 PC에서, 여러분이 설치한 게임으로부터 생성되며 그 설치본에 묶입니다(게임을 바꾸거나 업데이트하면 다시 생성됩니다).
> - **본인 소유의 정품 게임 필요**: Steam 정식 버전이나 공개 베타 버전 모두 됩니다. 게임을 찾지 못하면 프로그램은 오류를 띄우고 종료됩니다.
> - **게임 리소스는 받지 않음**: 게임 코드, 데이터, 텍스트, 아트가 들어간 PR은 모두 거절합니다([CONTRIBUTING.md](CONTRIBUTING.md) 참고).
> - **악용 시 책임은 본인에게**: 누구든 이 프로젝트를 이용해 게임 코드나 파일을 배포한다면 그 책임은 전적으로 본인에게 있으며, 제작자와는 무관합니다.
> - **라이선스 범위**: [LICENSE](LICENSE)(MIT)는 저희가 직접 작성한 코드에만 적용되며, 게임 코드, 데이터, 아트, 상표에 대해서는 어떠한 라이선스도 부여하지 않습니다.
> - Slay the Spire 2는 Mega Crit의 상표이며, 여기서 게임 이름을 언급하는 것은 어떤 게임용 도구인지 밝히기 위해서일 뿐입니다.
> - 연락처: **nopsil@hotmail.com** (권리자분께서 문제가 있으시면 연락 주세요. 신속하게 처리하겠습니다)
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

## 할 수 있는 것

- **승률과 진행도 측정**: 캐릭터, 승천 단계, AI를 고르면 AI가 한 판을 끝까지 자동으로 플레이합니다(지도, 전투, 보상, 상점, 이벤트). 한 번에 수백 판을 돌려 승률, 평균 도달 층수, 막별 통과율을 볼 수 있습니다.
- **사망 원인 분석**: 어떤 적, 어떤 전투에서 가장 많이 죽는지 집계해서 덱의 약점을 빠르게 찾을 수 있습니다.
- **카드 한 장 A/B 테스트**: 같은 시드로 한쪽은 특정 카드를 넣고, 다른 쪽은 넣지 않고 돌려서, 그 카드 한 장이 승률과 층수를 얼마나 바꾸는지 바로 확인할 수 있습니다.
- **직접 만든 모드 테스트**: 예시 모드(Claude娘, 오리지널 콘텐츠)가 들어 있고, 직접 만든 YAML 모드를 올려서 전투 테스트를 돌릴 수도 있습니다.
- **그래픽 화면, 모든 작업은 내 PC에서**: 클릭으로 설정, 버튼 한 번으로 실행, 실시간 진행 상황, 그래프 보고서, 기록 보기까지. 인터넷에 연결하지 않고 아무것도 업로드하지 않습니다.
- **4가지 언어**: 한국어, English, 简体中文, 日本語. 프로그램 안에서 바꿀 수 있고, 카드·캐릭터·적 이름도 설치된 게임에서 같은 언어로 읽어 옵니다.

## 시작하기 (Windows)

### 가장 쉬운 방법: 패키지 버전 다운로드

1. Steam에서 Slay the Spire 2를 설치합니다(정식 버전이든 베타든 상관없습니다).
2. [Releases 페이지](https://github.com/Nopsil/deckbench/releases)에서 `DeckBench-<버전>-win64.zip`을 받아 폴더(예: `D:\DeckBench`)에 **통째로 압축을 풉니다**.
3. `DeckBench.exe`를 더블클릭합니다. 처음 실행할 때는 「잠시 기다려 주세요」 안내가 뜨고 게임에서 데이터를 생성합니다. 1~2분 정도 걸리며, 끝나면 화면이 자동으로 열립니다.
   **Python이나 .NET을 설치할 필요가 없습니다**(디컴파일러가 `decompiler` 폴더에 이미 들어 있습니다).
4. 게임을 기본 위치가 아닌 곳에 설치했다면, 그 폴더에서 PowerShell을 열고 한 번만 실행해 주세요:
   `.\DeckBench.exe --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"`. 그다음부터는 더블클릭만 하면 됩니다.

### 소스에서 실행하기

**처음 한 번만 하는 준비**

1. **게임 설치**: Steam에서 Slay the Spire 2를 설치합니다(정식 버전이든 베타든 상관없습니다).
2. **Python 3.11 이상 설치**: [python.org](https://www.python.org/downloads/)에서 받아 설치하고, 설치할 때 **「Add python.exe to PATH」에 체크**합니다.
3. **.NET 9 SDK 설치**: [dotnet.microsoft.com](https://dotnet.microsoft.com/download/dotnet/9.0)에서 SDK를 받아 설치합니다(내 PC에서 게임 파일을 읽는 데 씁니다).
4. **Node.js(LTS 버전) 설치**: [nodejs.org](https://nodejs.org/)에서 받아 설치합니다(처음 화면을 빌드할 때만 씁니다).
5. **ilspycmd 설치**: PowerShell 창을 **새로** 열고 다음을 실행합니다:
   ```powershell
   dotnet tool install -g ilspycmd --version 9.1.0.7988
   ```
6. **DeckBench 다운로드**: 이 페이지에서 **Code → Download ZIP**을 누르고, 예를 들어 `D:\deckbench`에 압축을 풉니다(git을 쓸 줄 안다면 `git clone`도 됩니다).

**설치하고 실행하기**

`D:\deckbench` 폴더에서 PowerShell을 열고(폴더 안 빈 곳에서 Shift를 누른 채 우클릭 → 「여기에 PowerShell 창 열기」, 또는 먼저 `cd D:\deckbench` 실행), 다음을 차례대로 실행합니다:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-gui.txt
cd gui\web; npm install; npm run build; cd ..\..
.venv\Scripts\python -m gui.app
```

앞의 세 줄은 한 번만 실행하면 됩니다. 그 뒤로는 쓸 때마다 이 폴더에서 마지막 줄만 실행하면 됩니다:
```powershell
.venv\Scripts\python -m gui.app
```

**처음 실행할 때**는 Steam 게임을 자동으로 찾아서 필요한 데이터를 내 PC에서 생성합니다. **1~2분** 정도 걸립니다(이 동안은 아직 창이 뜨지 않으니 조금만 기다려 주세요). 그다음부터는 금방 켜집니다. 화면은 별도 창으로 열리며, 창을 열 수 없으면 자동으로 브라우저에서 엽니다.

**게임을 못 찾나요?** 게임을 기본 위치가 아닌 곳에 설치했다면 게임 폴더 위치를 알려 주세요(경로는 본인 것으로 바꾸세요):

```powershell
.venv\Scripts\python -m sts2sim.gamedata setup --game-dir "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

또는 실행하기 전에 환경 변수를 설정해도 됩니다(현재 창에서만 적용):
```powershell
$env:DECKBENCH_GAME_DIR = "D:\SteamLibrary\steamapps\common\Slay the Spire 2"
.venv\Scripts\python -m gui.app
```

Linux/macOS는 [docs/DEVELOPER.md](docs/DEVELOPER.md)를 참고하세요.

## 어떤 AI를 고를까

- **「범용 AI (추천, 모드 캐릭터도 사용 가능)」**: 대부분의 경우 이걸 추천합니다. 카드 선택, 휴식처, 상점은 작은 신경망이 맡는데, 비용·피해량·방어도·희귀도 같은 일반적인 수치만 보고 개별 카드 이름은 모릅니다. 그래서 **직접 만든 모드 캐릭터에도 쓸 수 있습니다**. 속도는 학습형 AI와 같고(한 판에 1~2초) Windows에서도 됩니다. 저희 테스트에서는 학습형 AI보다 평균 1~4층 더 갔습니다.
- **「학습형 AI」**: 이전 버전의 추천 AI입니다. 속도가 같아서 비교용으로 쓸 수 있습니다.
- **「spire-mentor 풀런 AI」 두 가지**: 가장 강하지만, 서드파티 프로그램인 spire-mentor를 직접 빌드해야 하고 기본 캐릭터 5명만 지원합니다. 자세한 내용은 [docs/DEVELOPER.md](docs/DEVELOPER.md)를 참고하세요.

## 게임 시드로 돌려 보기

「새 테스트 → 풀런 일괄」에서 **「게임 시드 지정」** 칸에 게임에 표시되는 시드(예: `7F3K9Q2ZB8MA`)를 넣으면, AI가 그 한 판만 플레이하면서 매 단계 무엇을 골랐는지 기록합니다. 기록은 결과 페이지에서 볼 수 있습니다.
소문자, 알파벳 O와 I는 게임 규칙대로 자동으로 대문자, 숫자 0과 1로 바뀝니다. 명령줄: `python tools/batch.py --char Silent --seed 7F3K9Q2ZB8MA --log-dir steps`.

## 내가 한 런 보기

왼쪽 **「런 가져오기」**에서 내 기록(`history`의 `.run`)이나 진행 중인 `current_run.save` / `current_run_mp.save`를 열면, 그 런의 시드, 지나온 경로, 고른 카드, 유물을 볼 수 있습니다. 지정한 파일만 읽으며 게임 세이브는 바꾸지 않습니다. `saves` 폴더를 가리키면 안의 런을 목록에서 고를 수 있습니다.

명령줄: `python -m sts2sim.saveimport <파일 또는 폴더>`. 형식 설명은 [docs/SAVE_FORMAT.md](docs/SAVE_FORMAT.md)(중국어·영어).

## 코드 없이 모드 만들기 (모드 편집기)

왼쪽 **「모드 편집기」**에서 캐릭터(체력, 에너지, 시작 덱, 시작 유물), 카드(효과는 메뉴에서 선택: 피해 주기, 파워 부여, 카드 뽑기… 또는 템플릿), 파워와 유물(「언제 → 무엇을」)을 양식으로 만들 수 있습니다. **「검사」**를 누르면 문제를 쉬운 말로 알려 줍니다.
**「테스트」**에서 클릭 한 번으로 전체 런 일괄 실행이나 카드 하나 A/B(같은 시드로 시작 덱 vs 시작 덱+이 카드)를 돌릴 수 있습니다. zip 가져오기/내보내기로 공유할 수 있습니다.
같은 YAML 파일은 `mods/`에 넣으면 명령줄에서도 동작합니다: `python tools/batch.py --mod mods/my_mod --char MyHero --agent modai`. 형식 설명은 [docs/MODDING.md](docs/MODDING.md)(중국어·영어).

## AI 비서에게 한 수씩 플레이시키기 (MCP)

Claude나 Cursor처럼 MCP를 지원하는 AI 비서를 쓰고 있다면, 시뮬레이터 안에서 직접 한 판을 플레이하게 할 수 있습니다. 상황을 보고, 선택지를 고르고, 이유를 적고, 되돌려서 다시 할 수도 있습니다. 마지막에는 조작 목록을 내보낼 수 있어서, 같은 시드로 실제 게임에서 그대로 따라 할 수 있습니다.
지금은 소스에서 실행할 때만 됩니다: `pip install -r requirements-mcp.txt` 다음에 `python tools/mcp_server.py`. 카드 이름은 실행할 때 여러분이 설치한 게임에서 읽어 옵니다. 자세한 내용은 [docs/MCP.md](docs/MCP.md)를 참고하세요.

## 결과 보는 법

- **승률**: 최종 보스를 잡은 판의 비율입니다.
- **평균 층수 / 막별 통과율**: AI가 평균 몇 층까지 갔는지, 1·2·3막을 통과한 판이 얼마나 되는지입니다. 승률이 아주 낮을 때(예: 높은 승천)는 층수로 보는 편이 차이가 더 잘 드러납니다.
- **사망 원인**: 각 판이 어떤 전투(어떤 적 / 엘리트 / 보스)에서 죽었는지 보여 줘서, 덱이 버티지 못하는 지점을 찾는 데 도움이 됩니다.
- **카드 한 장 A/B**: 두 그룹은 같은 랜덤 시드를 쓰고 차이는 그 카드 한 장뿐이라, 결과 차이가 곧 그 카드의 영향입니다. 판 수가 적으면 차이가 들쭉날쭉하고, 판 수가 많을수록 믿을 만합니다.

**중요**: AI는 실력 좋은 사람 플레이어가 아니므로 이 숫자들은 **실제 플레이어의 승률이 아닙니다**. **같은 설정 안에서 서로 비교할 때**(새 카드 vs 옛 카드, 수치 조정 전 vs 후, 내 캐릭터 vs 기본 캐릭터) 쓰기 좋고, 절대적인 실력 지표로 보기에는 맞지 않습니다.

## 자주 묻는 질문

**「找不到游戏安装 / Game install not found」라고 나와요**
Steam에 게임이 설치되어 있는지 확인한 다음, 위에서 설명한 `--game-dir`이나 `DECKBENCH_GAME_DIR`로 게임 폴더(`...\steamapps\common\Slay the Spire 2`)를 지정해 주세요.

**게임이 업데이트됐어요 / 베타 브랜치로 바꿨어요**
생성된 데이터는 그때의 게임 파일에 묶여 있어서, 파일이 바뀌면 예전 데이터는 더 이상 쓰지 않습니다. 다음에 실행할 때 자동으로 다시 생성하며(역시 1~2분), 직접 실행할 수도 있습니다:
`.venv\Scripts\python -m sts2sim.gamedata setup`

**Windows에서는 왜 「강한 AI (탐색 포함)」와 「학습형 AI (탐색 포함)」가 안 보이나요?**
탐색을 쓰는 AI는 운영체제의 fork 기능이 필요한데 Windows에는 없어서, 화면에서 자동으로 숨겨집니다. Windows에서는 탐색이 필요 없는 **「범용 AI (추천, 모드 캐릭터도 사용 가능)」를** 추천합니다.

**왜 꼭 내 게임이 있어야 하나요?**
저희는 게임의 어떤 내용도 배포할 수 없고, 배포하지도 않습니다. DeckBench는 내 PC에서 내 게임을 읽어 그 규칙을 시뮬레이션할 뿐이라서, 정품 게임이 없으면 쓸 수 없습니다.

**`npm`에서 「스크립트를 실행할 수 없습니다」 오류가 나요**
명령어의 `npm`을 `npm.cmd`로 바꿔 주세요(예: `npm.cmd install; npm.cmd run build`).

**ilspycmd를 찾을 수 없다 / ilspycmd가 필요하다고 나와요**
.NET 9 SDK를 설치한 뒤에는 PowerShell 창을 **새로 열고** `dotnet tool install` 줄을 실행한 다음, DeckBench를 다시 실행하세요.

## 더 알아보기

- [docs/DEVELOPER.md](docs/DEVELOPER.md): 명령줄 일괄 실행(전체 옵션), 첫 데이터 생성의 내부 원리, 선택 사항인 spire-mentor AI, 구버전 전투 시뮬레이터, 폴더 구조, 테스트(Linux/macOS 명령 포함).
- 선택 사항인 더 강한 AI: 서드파티 [spire-mentor](https://github.com/tfriedel/spire-mentor)를 직접 빌드하면 `mentor-full`을 쓸 수 있습니다(전투는 MCTS, 전투 밖 결정은 PPO 신경망이 담당하며 기본 캐릭터 5명만 지원). spire-mentor는 이 프로젝트에 포함되어 있지 않습니다. v0.111에서 추가된 새 카드 19장(SIDESTEP 등)을 읽을 때 알려진 문제가 있어서, 작은 로컬 패치를 제공합니다. 자세한 내용은 [docs/DEVELOPER.md](docs/DEVELOPER.md#可选spire-mentor更强的-ai--optional-spire-mentor)를 참고하세요.
- [docs/MODDING.md](docs/MODDING.md): YAML + Python으로 나만의 모드 만들기(카드, 파워, 유물, 덱, 실험).
- [gui/README.md](gui/README.md): 그래픽 화면의 구조와 패키징.
- [CONTRIBUTING.md](CONTRIBUTING.md): 기여 안내(게임 콘텐츠는 일절 받지 않습니다).

## 라이선스

MIT이며, 저희가 직접 작성한 코드에만 적용됩니다. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
