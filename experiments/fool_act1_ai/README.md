# 愚者 v0.113.1 一幕 Boss：出牌决策对照

模拟器结果不是真机通关。本模拟器把第三幕 Boss 打死记为胜，没有建筑师房。下面的数字都是同一份 Mac osx-arm64 `sts2.dll`（SHA-256 `a671e9efb86a7b80405133105665867b053c787670d475b4347cf5ccc15cb5fb`，v0.113.1 build 26660232）在本机缓存上跑出来的。

基线提交是 PR #76 的头 `4c658753b1eb2b932b23b14d637d87df17623c35`（事件战、假商人、catch 绑定）。本分支从这一点拉出，没有改那条 PR，也没有改 `main`。选牌加分试过，调参集上没有留下。

## 结论

留出的 120 颗种子上，`learned` 进阶 0：

| | 有效局 | 超时 | 出错 | 总胜 | 总胜 Wilson 95% | 一幕通过 | 一幕 Wilson 95% | 第 17 层 Boss 死亡 | 平均层 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: |
| 基线 | 120 | 0 | 0 | 0 | 0.0%–3.1% | 24 | 13.8%–28.0% | 58 | 18.05 |
| 本次 | 120 | 0 | 0 | 0 | 0.0%–3.1% | 34 | 21.0%–37.0% | 69 | 20.43 |

同一颗种子配对（本次 − 基线），10000 次 bootstrap，95% 区间：

- 胜负差：0。120 对都是负。
- 一幕通过差：+8.3 个百分点（13 局变好、3 局变差、104 局相同），区间 +2.5 到 +15.0 个百分点，不含 0。
- 层数差：+2.38 层，区间 +1.18 到 +3.59。
- 第 17 层 Boss 死亡差：+9.2 个百分点（死亡变多）。更多局活到了 Boss，所以死在这一层的计数上升；通过数仍然增加。

`heuristic` 用同一 120 颗种子：胜都是 0/120。一幕通过 10 → 20（配对 +8.3 个百分点，区间 +1.7 到 +15.0）。平均层 14.72 → 16.73。超时 0，出错 0。

总胜率没有提高。一幕通过率和平均层数提高了，而且配对区间不含 0。这不是挑种子的结果：留出种子在看优化结果之前就写进 `seeds_test.txt`。

## 改了什么

愚者的箭只有空槽才能射出去，射空槽伤害是 0。瞄准加在下一支箭上，射完就清掉。幻影（Vantom）的滑溜把每段命中的生命伤害封顶为 1，并剥一层。原来的打分把预览伤害当成真实掉血，沉重射击在 8 层滑溜上看起来像一击必杀，还会把起始 6 点瞄准射掉。

留下的改动：

- 滑溜存在时，按「每段最多 1 点生命、多余段数才按原伤害」重算这一下的价值。格挡仍按原伤害拆。这是所有角色对滑溜的计分，不是只改愚者。
- 愚者：没有空箭槽不射。滑溜还没剥完、手里还有别的攻击、这一下的段数打不穿滑溜时，不把带瞄准的射击打出去。
- 滑溜剥开之后，有瞄准就优先打瞄准倍率更高的射击（沉重射击先于愚蠢射击）。能量够覆盖「先瞄准、再射击」时先打 0 费或低费的即时瞄准，不打会花光能量的 X 费。
- 本幕首领会滑溜时，愚者的 `HitCount` 算进多段加分。调参集上更宽的选牌加分（瞄准、箭袋、压悲伤）没有提高一幕通过率，没有留下。

## 调参集（没有拿来报最终胜率）

`seeds_tune.txt`，32 颗，`random.Random(20261124)`，和留出集不相交。`learned`，进阶 0，出错都是 0。

| 变体 | 胜 | 一幕通过 | 第 17 层 Boss 死亡 | 平均层 |
| --- | ---: | ---: | ---: | ---: |
| 基线 | 1 | 10 | 15 | 19.19 |
| 只加选牌分（瞄准/箭袋/沉重，压悲伤），尚未改滑溜计分 | 0 | 9 | 16 | 20.12 |
| 选牌分 + 滑溜计分 | 0 | 8 | 18 | 19.81 |
| 选牌分 + 滑溜计分 + 射击顺序 | 0 | 8 | 18 | 19.38 |
| 只改战斗计分和射击顺序 | 3 | 13 | 14 | 22.59 |
| 战斗改动 + 只惩罚生成悲伤/条件回能 | 2 | 12 | 14 | 22.09 |

按一幕通过和胜局留下「只改战斗」。惩罚悲伤的那一档更低，没有叠加进最终代码。留出集在这之后才跑，只跑了这一档对基线。

## 复现

缓存和 DLL 只留在本机，不要提交。进阶 0，角色 `Fool`，超时 learned 180 秒、heuristic 120 秒。进程数不改变同一颗种子的结果。

```bash
export DECKBENCH_CACHE=/tmp/deckbench-cache DECKBENCH_GAME_DIR=/tmp/sts2-install
# 基线：git checkout 4c658753b1eb2b932b23b14d637d87df17623c35 -- sts2sim/engine/agents.py sts2sim/engine/strong.py
# 并且不要加载 sts2sim/engine/fool_ai.py 里的调用（该提交没有这些调用）
SEEDS=$(paste -sd, experiments/fool_act1_ai/seeds_test.txt)
PYTHONPATH=. python3 tools/batch.py --char Fool --asc 0 --agent learned \
  --seed "$SEEDS" --procs 4 --timeout 180 --out /tmp/fool-holdout-learned.jsonl
PYTHONPATH=. python3 tools/batch.py --char Fool --asc 0 --agent heuristic \
  --seed "$SEEDS" --procs 4 --timeout 120 --out /tmp/fool-holdout-heuristic.jsonl
```

种子生成（已经写在两个 txt 里，不要重抽）：

```python
import random
chars = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
def make(seed, n):
    rng = random.Random(seed)
    out, seen = [], set()
    while len(out) < n:
        s = "".join(rng.choice(chars) for _ in range(12))
        if s not in seen:
            seen.add(s); out.append(s)
    return out
# make(20261124, 32) 调参，make(20261125, 120) 留出
```

`results/*.jsonl` 是每局一行的压缩记录（胜负、层、幕、出错、死亡房、秒数），不是完整战斗日志。
