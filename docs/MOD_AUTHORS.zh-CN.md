# mod 作者入门

[← README](../README.md) · [文档索引](INDEX.md) · [English](MOD_AUTHORS.md) · [格式说明](MODDING.md)

这篇是从一份新检出的代码到能读的数字。示例 mod 在 `examples/spark/`，是 sts2sim 的 mod 格式（`sts2sim/modfmt`）写成的原创 YAML。它加了两张牌：**Arc** 和 **Lantern**，再加上整局检查所要求的那一小池（基础牌以外 2 张攻击、2 张技能、1 张能力，并且普通 / 罕见 / 稀有至少各一张）。文件夹里的卡牌文字是为这个示例写的。

下面的 bash 代码块就是 `tests/test_mod_authors.py` 在仓库根目录、同一个 shell 里按顺序跑的命令。样本故意只有 2 场。标成 `needs-game` 的代码块需要你自己的游戏安装，测试会跳过。这个仓库里没有游戏文件，示例里也没有。

Windows 的 PowerShell 先设这两个变量，后面的 `python` 行一样。如果没有 `python` 这个命令，用 `python3`。

```powershell
$env:STS2SIM_USER_MODS = "examples"
$env:OUT = "$env:TEMP\deckbench-spark"
```

## 安装

内部 Python 战斗引擎（`python -m sts2sim`）只需要这些 Python 依赖，不读游戏安装。

```bash
python -m pip install -r requirements.txt
```

生成本机游戏数据、图形界面，以及整局批量，都要先装好游戏并跑过 `python -m sts2sim.gamedata setup`。测试跳过这一步：

```bash needs-game
python -m sts2sim.gamedata setup
```

## 加载示例

战斗引擎按文件夹名找 mod：先看 `mods/`，再看环境变量 `STS2SIM_USER_MODS` 里的每个目录（用系统的路径分隔符隔开）。`examples/spark` 的文件夹名是 `spark`。

```bash
export OUT="${OUT:-/tmp/deckbench-spark}"
export STS2SIM_USER_MODS=examples
mkdir -p "$OUT"
```

```bash
python - <<'PY'
from sts2sim.modfmt.schema import load_mod_dir, validate
mod = load_mod_dir("examples/spark")
problems, warnings = validate(mod, fullrun=True)
if problems:
    raise SystemExit("\n".join(f"{w}: {en}" for w, _zh, en in problems))
print(mod["name"], "cards", ",".join(c["id"] for c in mod["cards"]), "warnings", len(warnings))
PY
```

`problems` 为空表示文件合法。警告是卡池大小的提醒（某一稀有度少于 3 张）。`cards.yaml` 里的类型用内部引擎认得的中文（`攻击` / `技能` / `能力`）。检查器也认 `Attack` / `Skill` / `Power`。

`MATCH` 写在文件里，是为了让你看到一条触发器。探针卡组没有装备它。YAML 的遗物和能力触发器在整局里才会跑，也就是下面标了 `needs-game` 的那一节。这一页的战斗只用卡牌上的伤害和格挡。

## 用 `--workers` 看胜率

`examples/spark/winrate.yaml` 打内置的训练木桩（`encounter: DUMMY`）。木桩有 9999 点生命，并且不攻击，所以只打一回合会超时。超时不算胜。`decks` 是空的，因此这个文件不会去要一场真的遭遇。木桩那一行写了 `fights: 2`。`--fights` 决定 `decks` 列表打几场；这里列表是空的，木桩仍然是 2 场。

`--workers 2` 是进程数，和 `--jobs` 是同一个开关。每场的随机数由种子、卡组、幕、房间和场次决定，所以进程数不改变结果。

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --out "$OUT/win"
```

```bash
python - <<'PY'
import json
import os
out = os.environ["OUT"]
path = os.path.join(out, "win", "raw.jsonl")
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
from sts2sim.stats import format_win_rate, win_rate_report
wins = sum(r.get("result") == "win" for r in rows)
print(format_win_rate(win_rate_report(wins, len(rows)), "text"), end="")
meta = json.load(open(os.path.join(out, "win", "meta.json"), encoding="utf-8"))
print("workers", meta["jobs"])
PY
```

怎么读这一行：

- `胜率 / win rate: 0/2` 是胜场除以场数。两场都超时，所以胜率是 0%。
- `Wilson 95% CI` 是区间。只有两场时这个区间很宽。整局的 `tools/batch.py` 打的是同一行。
- `样本不足，不能下结论 / sample too small to conclude: n=2 < 30` 表示有效场数少于 30。数字仍会打出来，但不能据此判断 Arc 强不强。
- `workers 2` 是写进 `meta.json` 的进程数。

该目录里的 `report.md` 是旧版战斗报告。第 6 节（对照本机怪物数据的覆盖率）在没有那份数据时略过，命令仍会跑完。那份数据从你的安装生成，不在这个仓库里。真的房间（`普通` / `精英` / `首领`）需要它；这个木桩样本不需要。

## 单卡 A/B

`examples/spark/ab.yaml` 用同一批种子打两遍：`spark_base`（Flick 和 Ward）和 `spark_arc`（把一张 Flick 换成 Arc）。B 减 A 就是这张牌。`decks.yaml` 里还有 `spark_lantern`，换法相同；这个样本不跑它。

```bash
python -m sts2sim examples/spark/ab.yaml --workers 2 --fights 2 --seed 1 --out "$OUT/ab"
```

```bash
python - <<'PY'
import json
import os
path = os.path.join(os.environ["OUT"], "ab", "raw.jsonl")
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
from sts2sim.stats import ab_win_report, format_ab

def tally(deck):
    group = [r for r in rows if r["deck"] == deck]
    return sum(r.get("result") == "win" for r in group), len(group)

base_w, base_n = tally("spark_base")
arc_w, arc_n = tally("spark_arc")
print(format_ab(ab_win_report(base_w, base_n, arc_w, arc_n), "text"), end="")
PY
```

怎么读这一段。它和 `tools/ab_card.py --format text` 用的是同一个格式化函数：

- 每一边各有自己的 `Wilson 95% CI`。
- `两比例 z 检验 / two-proportion z-test` 是合并比例的双侧 z 检验。`p=` 是「两边胜率相同」的 p 值。`B − A` 是 Arc 的胜率减去基线胜率。整局还会另外打配对差；这一行是两组胜率的边际检验。
- 在这只木桩上两边都是 0/2，所以差是 0%，`p=1.0000`。
- `n=2 and n=2 < 30` 是样本不足警告。只要有一边有效场数少于 30 就会写，p 很小的时候也写。出现警告就不要下结论。

有了本机游戏数据之后，同一份 mod 的整局命令是测试会跳过的那一块。`--force SPARK_ARC` 是 [MODDING.md](MODDING.md) 里的 id 写法：前缀 `Spark` 加上卡牌 id `ARC`。模组编辑器会显示游戏登记的 id；如果运行说找不到这张牌，用编辑器里的那串。`--n 200` 是一个警告会安静下来的起点（分界是 30）。它仍是 AI 的胜率，用来在同一套设置下比较，不是玩家的胜率。

```bash needs-game
python tools/batch.py --mod examples/spark --char Wick --asc 0 --n 200 --agent modai --workers 2
python tools/ab_card.py --mod examples/spark --char Wick --asc 0 --n 200 --agent modai --workers 2 --force SPARK_ARC --format text
```

## AI 为什么打出这张牌

`--explain` 把 `explain.jsonl` 写在报告旁边。它记的是 AI 当时已经算好的候选，不多抽随机数。`--workers` 可以开着；每场战斗仍带着自己的行。

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --explain --out "$OUT/explain"
python tools/explain_fight.py "$OUT/explain/explain.jsonl" --fight 0
```

`tools/explain_fight.py --fight 0` 把第一场打成 Markdown（从 0 开始数；可以先用 `--seed` 过滤）。这套牌的第一段 **出牌 / play** 选的是 **Arc**。下面的表是手里其他牌和它们的分数。`←` 标出实际打出的那张。选 Arc 是因为打出之后的局面分数高于 Flick 和 Ward。同一回合后面几段接着打 Flick，直到能量用完；最后一段是回合结束。

## 可选的 `--mechanic-aware`

默认关，不写这个旗标就是关。`--mechanic-aware` 打开启发式对荆棘、受击加格挡、多只敌人总伤害的修正。`--no-mechanic-aware` 保持关闭。打开之后，`--explain` 的候选 `note` 可以写成 `thorns:`、`armour` 或 `incoming:`。

训练木桩没有荆棘，也不攻击，所以这个样本的说明里没有这几个词，打出的牌和不开旗标时一样。等战斗里真有这些机制时再打开。真的遭遇需要本机怪物数据；测试不跑那些。

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --mechanic-aware --explain --out "$OUT/mechanic"
python tools/explain_fight.py "$OUT/mechanic/explain.jsonl" --fight 0
```

```bash
python - <<'PY'
import json
import os
meta = json.load(open(os.path.join(os.environ["OUT"], "mechanic", "meta.json"), encoding="utf-8"))
print("mechanic_aware", meta["exp"]["agent_kw"]["mechanic_aware"])
PY
```

`mechanic_aware True` 是记在实验上的旗标。上面的说明 Markdown 就是在读这一步为什么选这张牌。

## 不要放进仓库的东西

提交你自己的卡牌文字和数值。不要加游戏文件、导出的表，或抄来的卡牌文字。[CONTRIBUTING.md](../CONTRIBUTING.md) 是这条规则。更大的 mod 怎么写见 [MODDING.md](MODDING.md)。
