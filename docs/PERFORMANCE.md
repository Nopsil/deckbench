# 内部战斗引擎的耗时 / Internal fight-engine timing

[← 返回 README](../README.md) · [文档索引](INDEX.md)

`tools/bench.py` 给内部 Python 战斗引擎计时。不读游戏安装，也不用 `mods/vanilla`。样本有两块：

- **内部对战**：`sts2sim.fightcheck` 里的合成卡组（`start`、`burst`、`draw`）和合成怪物。种子是 `1000 + 序号 × 17`，和 `tests/test_sim_determinism.py` 用的是同一套算法。场数不一样：那份测试锁的是启发式 4 个种子 × 每套 2 场，以及束搜索 2 个种子 × 每套 1 场。`tools/bench.py` 的默认是启发式 6 个种子 × 3 套牌 × 每套 3 场 = **54 场**。混入窄束搜索是 6 个种子 × 3 套牌 × 1 场 ×（启发式 + 束搜索）= **36 场**。束搜索宽度 3、深度 2（`BeamAgent`）。
- **训练木桩**：`encounter: DUMMY`（9999 血、不攻击）。牌组是 `probe_A`、`probe_D`、`probe_noengine`，各 4 场，最多 4 回合，种子 1000，启发式。共 **12 场**。这三套牌不依赖仓库里没有的原版「打击 / 防御」。

*Times the internal Python fight engine. No game install and no `mods/vanilla`. Two batches: the synthetic decks and monsters in `sts2sim.fightcheck` (seeds `1000 + index × 17`, the same formula as `tests/test_sim_determinism.py`; the bench defaults are a larger count than the locked fixtures), and a training dummy (`encounter: DUMMY`, 9999 HP, no attack) on `probe_A`, `probe_D` and `probe_noengine`.*

```bash
python tools/bench.py
```

场/秒取 3 次墙钟的中位数，不含分析器。分阶段数字是同一次 `cProfile` 的自用时间（self time），加起来是那一次被分析的运行，不是上面的墙钟。分析器会把每次 Python 调用都拖慢，所以阶段秒数大于墙钟，只适合看份额。

*Fights/sec is the median of 3 wall-clock samples and does not include the profiler. The phase lines are self time from one `cProfile` pass; they sum to that profiled run, not to the wall-clock line. The profiler slows every Python call, so use the phase seconds as shares.*

阶段：

| 阶段 | 里面是什么 |
| --- | --- |
| dispatch | `emit` / `_fire`，事件分发 |
| clone | 前瞻用的战斗、生物、能力、牌的复制 |
| value | 局面估值、`score_delta`、意图伤害 |
| legal | 合法动作和费用 |
| resolve | 出牌、效果、启发式 / 束搜索自己的循环 |
| damage | 伤害、格挡、施加能力 |
| enemy | 回合开始 / 结束、敌人行动 |
| expr | 卡面表达式 |
| other | 其余 |

## 同一台机器上的前后 / Before and after on this machine

Python 3.12。数字会随机器变，前后是同一条命令、同一进程设置。

*Python 3.12. The absolute numbers move with the machine; before and after are the same command.*

| 样本 | 改前（`origin/main`，含 #37） | 改后（rebase 之后） |
| --- | --- | --- |
| 启发式 54 场 | 0.5795 s，**93.2 场/秒** | 0.5054 s，**106.9 场/秒** |
| 启发式 + 窄束搜索 36 场 | 0.6878 s，**52.3 场/秒** | 0.6112 s，**58.9 场/秒** |
| 训练木桩 12 场 | 0.1144 s，**104.9 场/秒** | 0.1012 s，**118.6 场/秒** |

启发式 54 场的分阶段自用时间：

| 阶段 | 改前 | 改后 |
| --- | --- | --- |
| dispatch | 0.510 s（29.4%） | 0.417 s（27.6%） |
| clone | 0.171 s（9.8%） | 0.180 s（11.9%） |
| value | 0.108 s（6.2%） | 0.104 s（6.9%） |
| legal | 0.028 s（1.6%） | 0.026 s（1.7%） |
| resolve | 0.162 s（9.3%） | 0.154 s（10.2%） |
| damage | 0.105 s（6.0%） | 0.102 s（6.7%） |
| enemy | 0.008 s（0.4%） | 0.007 s（0.5%） |
| expr | 0.033 s（1.9%） | 0.028 s（1.8%） |
| other | 0.613 s（35.3%） | 0.492 s（32.6%） |
| 合计（含分析器） | 1.735 s | 1.511 s |

混入束搜索的 36 场，分发从 0.609 s（29.6%）降到 0.508 s（27.7%），被分析的总自用时间从 2.058 s 降到 1.829 s。木桩 12 场改后的分发占 22.7%。

## 改了什么 / What changed

结果不变的前提下，热路径少做了这些事：

- 每个能力、遗物在创建时带上一份类的 `on_*` 表。分发时直接查这张表，不再每次对类字典做一次查找。没有这个事件的对象仍然不调用。顺序还是遗物 → 玩家能力（先快照）→ 每个存活敌人的能力（先快照）→ mod 监听。前面一组新加上的能力，后面的组这次事件看得到；同一组里新加上的，这次看不到。
- 表达式如果只是一个名字（卡牌 `vars` 里的 `dmg` 这类），直接按和 `eval` 相同的顺序取值，不编译、不复制命名空间。带运算符的表达式仍走原来的编译缓存。
- `calc_damage` 读力量、活力、虚弱、易伤、无实体时用和 `amt` / `has` 相同的判断，不再为每次判断多调用一层方法。
- 复制战斗的 `data` 时，`dict` / `list` / `set` 直接 `copy()`。别的带 `copy` 方法的对象仍调用它。嵌套容器仍是浅拷贝。
- Claude 模组（`mods/claude_v34/hooks.py`）里 `STS2SIM_FANJI`、`STS2SIM_FLQ`、`STS2SIM_GRANT`、`STS2SIM_FENLEIQI` 按当前值缓存：环境变量改了，下一次读取用新值。`STS2SIM_FANJI_AI` 没有这层缓存，每次直接读。默认是 `STS2SIM_FANJI=off`、`STS2SIM_FLQ=flat`、`STS2SIM_FENLEIQI=v34`。

没有改默认 AI、没有改种子，也没有改「每场随机数只由种子决定」。前瞻仍按原来的 `_clone_n * 7919 + turn` 播种。

*Handlers are stored on the instance, so dispatch does not look the class dict up on every listener. A bare expression name is returned in the same lookup order as `eval`, without compiling. `calc_damage` uses the same strength / vigor / weak / vulnerable / intangible checks as `amt` and `has`. `dict` / `list` / `set` values in fight data are copied directly. The Claude mod caches `STS2SIM_FANJI`, `STS2SIM_FLQ`, `STS2SIM_GRANT` and `STS2SIM_FENLEIQI`, and reads `STS2SIM_FANJI_AI` every time. Defaults stay `off`, `flat` and `v34`. Default AI, seeds, and the per-fight RNG rule are unchanged.*

固定种子的胜负、回合、掉血、出牌、敌人血量和能力层数与改前逐字段相同。`tests/test_sim_determinism.py` 把启发式和束搜索的记录再打一遍，并和改前写下的 `tests/fixtures/fight_seeds.json`、`tests/fixtures/fight_seeds_beam.json` 比较。同一组种子打两遍也必须相同。

## 界面战斗的 workers / GUI fight workers

新建测试、组牌预设、连战、对打和单卡贡献的 `workers` 默认是 1。大于 1 时，界面工作进程用 spawn 的 `ProcessPoolExecutor` 打独立的场次，再按原来的下标写回 `raw.jsonl`。计时是 `meta.json` 里的 `wall_secs`（战斗循环，不含后面写报告）。机器是 4 核、Python 3.12。样本是 `claude_v34` 的 `probe_noengine` 打训练木桩 `DUMMY`，种子 11。不读游戏安装。

*GUI fight batches default to `workers` 1. Above 1, the GUI worker uses a spawned `ProcessPoolExecutor` for independent fights and writes `raw.jsonl` back in the original index order. The clock is `wall_secs` in `meta.json` (the fight loop, not the report written afterwards). The machine is 4 cores, Python 3.12. The sample is `claude_v34` deck `probe_noengine` against the training dummy `DUMMY`, seed 11. No game install.*

| 样本 | workers=1 | workers=4 |
| --- | --- | --- |
| 启发式，200 场，1 回合 | 0.172 秒，**1163 场/秒** | 0.359 秒，**557 场/秒** |
| 束搜索，200 场，8 回合 | 2.362 秒，**84.7 场/秒** | 0.902 秒，**222 场/秒** |

启发式那 200 场太短，开 4 个进程的时间比战斗本身长，所以更慢。束搜索每场更贵，4 个进程大约是 2.6 倍。两组的 `raw.jsonl` 去掉每场 `secs` 之后一致。出厂实验和模拟器的播种没有改。

*Those 200 heuristic fights are shorter than starting four processes, so four workers is slower there. Beam fights cost more, and four workers are about 2.6× faster. Both pairs of `raw.jsonl` match once per-fight `secs` is removed. Shipped experiments and the simulator's seeding are unchanged.*

*Fixed-seed win/loss, turns, HP, cards played, enemy HP and power stacks match field for field. `tests/test_sim_determinism.py` replays the heuristic and beam records against `tests/fixtures/fight_seeds.json` and `tests/fixtures/fight_seeds_beam.json`, and runs each batch twice.*
