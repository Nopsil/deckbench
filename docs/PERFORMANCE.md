# 内部战斗引擎的耗时 / Internal fight-engine timing

[← 返回 README](../README.md) · [文档索引](INDEX.md)

`tools/bench.py` 给内部 Python 战斗引擎计时。不读游戏安装，也不用 `mods/vanilla`。样本有两块：

- **内部对战**：`sts2sim.fightcheck` 里的合成卡组和合成怪物（和固定种子的确定性测试是同一批种子）。启发式默认是 6 个种子 × 3 套牌 × 每套 3 场 = **54 场**。混入窄束搜索是 6 个种子 × 3 套牌 × 1 场 ×（启发式 + 束搜索）= **36 场**。束搜索宽度 3、深度 2。
- **训练木桩**：`encounter: DUMMY`（9999 血、不攻击）。牌组是 `probe_A`、`probe_D`、`probe_noengine`，各 4 场，最多 4 回合，种子 1000，启发式。共 **12 场**。这三套牌不依赖仓库里没有的原版「打击 / 防御」。

*Times the internal Python fight engine. No game install and no `mods/vanilla`. Two batches: the synthetic decks and monsters in `sts2sim.fightcheck` (the same fixed seeds as the determinism test), and a training dummy (`encounter: DUMMY`, 9999 HP, no attack) on `probe_A`, `probe_D` and `probe_noengine`.*

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
- Claude 模组里每次出牌和估值都会读的 `STS2SIM_FANJI`、`STS2SIM_FLQ`、`STS2SIM_GRANT`、`STS2SIM_FANJI_AI`、`STS2SIM_FENLEIQI`，按当前值缓存。环境变量改了，下一次读取用新值。默认仍是关反击、`flat` 分类器。

没有改默认 AI、没有改种子，也没有改「每场随机数只由种子决定」。前瞻仍按原来的 `_clone_n * 7919 + turn` 播种。

*Handlers are stored on the instance, so dispatch does not look the class dict up on every listener. A bare expression name is returned in the same lookup order as `eval`, without compiling. `calc_damage` uses the same strength / vigor / weak / vulnerable / intangible checks as `amt` and `has`. `dict` / `list` / `set` values in fight data are copied directly. The Claude mod caches the environment switches it reads on every play and still notices when the variable changes. Default AI, seeds, and the per-fight RNG rule are unchanged.*

固定种子的胜负、回合、掉血、出牌、敌人血量和能力层数与改前逐字段相同。`tests/test_sim_determinism.py` 把启发式和束搜索的记录再打一遍，并和改前写下的 `tests/fixtures/fight_seeds.json`、`tests/fixtures/fight_seeds_beam.json` 比较。同一组种子打两遍也必须相同。

*Fixed-seed win/loss, turns, HP, cards played, enemy HP and power stacks match field for field. `tests/test_sim_determinism.py` replays the heuristic and beam records against `tests/fixtures/fight_seeds.json` and `tests/fixtures/fight_seeds_beam.json`, and runs each batch twice.*
