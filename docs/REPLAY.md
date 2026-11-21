# 失败回放 / Loss replay

一场已经结束、并且 `result` 是 `loss` 的战斗，可以看模拟器当时写下的时间线。侧栏「失败回放」（`#/replay`）。运行页和报告页在战斗测试完成后也有入口。

*A finished fight whose `result` is `loss` can show the timeline the simulator wrote at the time. Loss replay is `#/replay`. The run page and the report page link it once a combat test has settled.*

## 记下了什么 / What is recorded

只在 `Combat.trace` 是一个列表时记录。AI 前瞻用的副本把 `trace` 设成 `None`，所以搜索不记事件，也不多抽随机数。胜利、超时不写入结果。

*Recording happens only when `Combat.trace` is a list. The copy used for AI lookahead sets `trace` to `None`, so a search does not record events and does not draw extra random numbers. A win or a timeout is not stored.*

一条失败时间线（`trace.version` 是 1）里的事件：

| kind | 内容 |
| --- | --- |
| `turn_start` | 这一回合开始时的生命、格挡、能量、手牌张数、双方能力层数、敌人意图 |
| `play` | 打出的牌 id、名字、目标、支付的能量、剩余能量 |
| `damage` | 来源、目标、伤害、格挡掉的部分、实际失去的生命、剩余生命。玩家生命到 0 时 `hp_zero` 为 true |
| `hp_loss` | 不经过这次攻击结算的失去生命（例如牌上的 `lose_hp`、中毒） |
| `block` | 获得的格挡 |
| `power` / `power_blocked` | 层数变化，或被抵消 |
| `enemy` | 敌人名字、招式 id、意图。没行动时 `skipped` 是 `asleep`、`stunned` 或 `no_move` |
| `potion` | 药水名字 |
| `end` | 这场的 `result`，以及结束时的快照 |

*`turn_start` is HP, block, energy, hand size, power stacks and the enemy intent at the start of the turn. `play` is the card id, name, target, energy paid and energy left. `damage` is source, target, amount, the part blocked, HP lost and HP left. `hp_zero` is true when that hit set the player's HP to 0. `hp_loss` is HP lost outside that hit (a card's `lose_hp`, or poison). `block` is block gained. `power` / `power_blocked` is a stack change, or a stack that was prevented. `enemy` is the enemy name, move id and intent. When they do not act, `skipped` is `asleep`, `stunned` or `no_move`. `potion` is the potion name. `end` is the fight's `result` and a snapshot.*

`loss_turn` 是记录结束时的回合。页面写「记录到的失败在第 N 回合」，并标出 `hp_zero` 的那一条。这是记录里的事实，不是原因。

*`loss_turn` is the turn when the record ended. The page says the recorded loss is on turn N and marks the `hp_zero` event. That is a fact in the record. It is not a cause.*

## 没有时间线的时候 / When there is no timeline

| status | 含义 |
| --- | --- |
| `no_trace` | 这场是失败，但这份结果是开始记录之前保存的 |
| `not_a_loss` | 不是失败（胜利或超时） |
| `omitted` | 这一场失败超过了保存上限 |
| `empty` | 没有事件 |

* `no_trace`: the fight is a loss, and the result was saved before recording started. `not_a_loss`: a win or a timeout. `omitted`: this loss is past the cap. `empty`: there are no events.*

一次测试保留前 **12** 场失败的完整时间线，每场最多 **240** 条事件。再长就截断并标 `truncated`。第 13 场起的失败只留 `omitted: batch_cap`。

*One test keeps full timelines for the first 12 losses, at most 240 events each. A longer fight is cut and marked `truncated`. From the 13th loss, the row keeps `omitted: batch_cap`.*

接口：`GET /api/runs/<id>/fights`，`GET /api/runs/<id>/trace/<index>`。还在跑是 409。整局是 400，因为整局没有这条时间线。未知 id 是 404。正文没有堆栈。

*The routes are `GET /api/runs/<id>/fights` and `GET /api/runs/<id>/trace/<index>`. A test that is still running is 409. A full run is 400, because a full run has no timeline. An unknown id is 404. The body has no stack trace.*

时间线在 `raw.jsonl` 的失败行上。取消留下的已打完场次仍能读。对比、导出和结果包不另写一种文件；导入旧包时这些行没有 `trace`。`SYN_BRUTE` 只在卡牌测试里可选，打不到的遭遇不会凭空造一条时间线。

*The timeline sits on the loss row in `raw.jsonl`. Fights that finished before a cancel can still be read. Compare, export and bundles do not add a new file. An older imported bundle has no `trace` on those rows. `SYN_BRUTE` is only offered by the card test. An encounter the simulator cannot run does not get an invented timeline.*
