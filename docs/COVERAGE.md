# 覆盖率 / Coverage

这次用 `pytest-cov` 量的是 `sts2sim`、`gui`、`tools`。不需要本机游戏安装。整局引擎（`sts2sim/engine/` 里依赖生成缓存的部分）和转译器在这张表里仍是 0%，因为现有测试不加载它们；这次没有改它们的出牌、种子或 AI。

*Measured with pytest-cov over `sts2sim`, `gui`, and `tools`, with no game install. The full-run engine modules that need a generated cache, and the translators, stay at 0% because the existing tests do not load them. This pass does not change their plays, seeds, or AI choices.*

```bash
pip install -r requirements.txt pytest pytest-cov fastapi httpx python-multipart
python -m pytest tests --cov=sts2sim --cov=gui --cov=tools --cov-report=term-missing
```

| | Statements | Covered | Coverage |
|---|---:|---:|---:|
| Before these tests | 25274 | 8678 | 34.3% |
| After | 25285 | 9118 | 36.1% |

语句数增加是因为修边界时加了几行。测试：原来收集 241 个；现在 `271 passed, 16 skipped`（跳过的仍是要本机数据或可选依赖的用例）。

*The statement count went up by the lines added for the edge fixes. Tests: 241 collected before; now 271 passed and 16 skipped (the skips are still the cases that need a local install or an optional dependency).*

## 最容易算错的地方 / Least-covered risky areas

下面五块是这次补测试的地方。数字是该文件的语句覆盖率。

*These five areas are what the new tests cover. The percentages are statement coverage for that file.*

| Area | Modules | Before | After |
|---|---|---:|---:|
| Card effect resolution | `sts2sim/cards.py`（效果 op、打出、重放） | 72.9% | 95.5% |
| | `sts2sim/core.py`（伤害、格挡、施加、事件） | 83.2% | 89.4% |
| | `sts2sim/expr.py` | 71.2% | 76.2% |
| Powers / relic hooks | `sts2sim/powers.py` | 65.5% | 95.1% |
| | `sts2sim/powers_enemy.py` | 56.1% | 99.3% |
| | `sts2sim/relics.py` | 91.3% | 100% |
| Import parsing | `sts2sim/saveimport.py` | 92.0% | 95.7% |
| Calibration matching | `sts2sim/calibrate.py` | 83.4% | 95.1% |
| HTTP error paths | `gui/server.py` | 54.2% | 72.7% |

测试文件：`tests/test_card_effects.py`、`tests/test_power_relic_hooks.py`、`tests/test_import_parse_edges.py`、`tests/test_calibrate_matching.py`、`tests/test_http_errors.py`。

### 卡牌结算

覆盖了目标（全体、其他、随机其他、原目标已死就改打还活着的）、多段和额外段、`each_hit`、条件、循环、选择消耗/弃牌、`end_turn` 停下后面的效果、回手、消耗、能力牌离手、X 费、重放时清掉 `set` 出来的局部变量、格挡（敏捷和脆弱）、抽牌、治疗上限、过量扣血、加牌时手牌已满、动态费用和 `can_play`。药水走同一套解释器。

剩下的多半是随机池空了、`foreach` 里目标已死、以及 `block` 显式 `from_card: false`。多段伤害在战斗已经分出胜负之后是否还继续打，这次没有改，避免动到固定种子的战斗结果。

*Covered target selection (all, others, random other, retarget when the chosen enemy is dead), multi-hit and extra hits, `each_hit`, if, loops, exhaust and discard choices, `end_turn` stopping later effects, return, exhaust, powers leaving the hand, X-cost, clearing `set` locals on a replay, block with dexterity and frail, draw, the heal cap, overkill, adding a card into a full hand, cost expressions, and `can_play`. Potions use the same interpreter.*

*What is left is mostly an empty random pool, a dead target inside `foreach`, and an explicit `from_card: false` on block. Whether a multi-hit keeps resolving after the fight already has a result was not changed, so fixed-seed fight results stay as they are.*

### 能力 / 遗物钩子

力量、虚弱、易伤、无实体、荆棘、滑溜、难以杀灭、硬化外壳、覆甲、蜷身、胆小、盾墙、壁垒、仪式（敌人自己施加的那个回合不加力量；领地意识不加这个跳过）、活力、激怒、恶魔形态、毒雾、下回合能量/抽牌/格挡、不能抽牌、火焰屏障、沉睡、熟睡，以及敌人的紧缠、纸伤、缩小、缓慢、吮吸、缠结、柔嫩、昏眩、烟雾、恶咒、蜂房、埋地、逃脱、天罚、蟹之怒、饥饿、后方攻击。遗物覆盖了濒死拉回 1 点生命、改费用、施加前加层、人工制品先于 `modify_apply`、克隆不共享 `data`。

*Strength, weak, vulnerable, intangible, thorns, slippery, hard to kill, hardened shell, plating, curl up, skittish, rampart, barricade, ritual (no strength on the turn an enemy applies it to itself; territorial does not skip), vigor, enrage, demon form, noxious fumes, next-turn energy/draw/block, no-draw, flame barrier, asleep, slumber, and the enemy powers constrict, paper cuts, shrink, slow, suck, tangled, tender, ringing, smoggy, hex, hive, burrowed, escape, nemesis, crab rage, ravenous, and back attack. Relics cover a lethal hit stopped at 1 HP, a cost change, extra stacks before apply, artifact consuming a debuff before `modify_apply`, and clone not sharing `data`.*

### 导入解析

数字和 `1.5` 这种 id、`{category, entry}`、升级层数写成 `"2"`、附魔数量不是整数、字符串金币、布尔层数跳过、坏的 UTF-16、带 NUL 的头、只有首领的地图、`profile/saves/history` 和松散目录、摘要在路线没有生命时退回玩家、附魔算作要点、多人遗物带上玩家 id。

*Numeric and `1.5` ids, `{category, entry}`, an upgrade count of `"2"`, a non-integer enchantment amount, string gold, a boolean floor skipped, bad UTF-16, a NUL header, a boss-only map, `profile/saves/history` and a loose folder, summary HP falling back to the player, an enchantment counting as a highlight, and a multiplayer relic carrying the player id.*

### 校准匹配

角色或进阶对不上、不是整数的进阶、选牌忽略另一位玩家和没选的牌、`Room.Elite` / `elite`、模拟没写幕时仍可对上、`EVENT.` 和 `NONE` 不算遭遇、事件房、未知层、两种战斗房或商店地图配上怪物房、NaN / 布尔 / 字符串掉血、`act` 和 `act_index` 互相矛盾、理由打平时按固定顺序、线性 p10/p90 和 midrank、模拟全是错误或种子不同。缺了进阶的存档导入后是 0，不是 `no_ascension`（那条是内存里的对局）。

*Character or ascension mismatch, a non-integer ascension, picks ignoring another player and cards that were not taken, `Room.Elite` / `elite`, a simulated fight with no act still matching, `EVENT.` and `NONE` not counting as an encounter, an event room, an unknown floor, two combat rooms or a shop map plus a monster room, NaN / bool / string HP, disagreeing `act` and `act_index`, a tie broken by the fixed reason order, linear p10/p90 and midrank, and a pool that is all errors or the wrong seed. A save with no ascension field imports as 0, not `no_ascension` (that code is for an in-memory run).*

### HTTP 错误路径

导入的 not object / unknown shape / not a run / 坏编码 / 太大 / 空目录 / 带上解析详情（花括号换成括号、超长截断）。校准的缺路径、多人、没种子、没角色、坏 JSON、模拟文件不在允许目录、`.run` 被拒绝。种子预览的空种子、进阶、角色，以及预览函数抛错时的 400（不是「还没有本机游戏逻辑」）。说明日志的负的 fight / offset。运行接口的未知类型、没卡组、404、未完成 409、没有 report、类型不同的 A/B、还在跑就删除。模组 zip 的坏包、路径穿越、没有 mod.yaml、名字不合法、列出的文件缺失、YAML 坏了、没有卡组。

*Import: not an object, unknown shape, not a run, bad encoding, too big, empty folder, and a parser detail with braces swapped for parentheses and a long detail truncated. Calibration: blank paths, multiplayer, no seed, no character, broken JSON, a sim file outside the allowed folders, a `.run` refused. Seed preview: empty seed, ascension, character, and a preview function that raises (a 400, not the missing-engine message). Explain: a negative fight or offset. Runs: unknown kind, no deck, 404, 409 while unfinished, no report, an A/B of different kinds, delete while running. Mod zips: not a zip, a path that escapes, no mod.yaml, a bad name, a listed file missing, bad YAML, no decks.*

还没覆盖、也没有改行为的部分：成功上传模组、真正开跑、日志流、`open` 文件夹。`sts2sim/potions.py` 的注册函数（按图鉴填名字）仍是 65%。

*Still uncovered, and left as they are: a successful mod upload, actually starting a run, the log stream, and opening a folder. `sts2sim/potions.py` stays at 65% on the catalog registration helper.*

## 这次修的边界 / Edge bugs fixed

这些都不是默认的一击结算，也不改种子或 AI 的选择。

*None of these is the default single resolution, and none of them changes seeds or AI choices.*

- 重放 X 费牌时，第二次结算把 `X` 清掉了，表达式会 `NameError`。现在第二次仍用这次付出的能量；`set` 出来的局部变量照旧清掉。
- 对没有活着的目标 `apply` 并 `save` 时不写变量，后面的表达式会 `NameError`。现在记下 0。有目标时合计方式和原来一样。
- `{category, entry}` 只留下 entry，`category.entry` 那段代码走不到。现在两者都在、entry 不带点时拼成 `CATEGORY.ENTRY`。只有 entry（例如已有测试里的 `{"entry": "DEFECT"}`）仍是 entry。
- `summarize` 碰到路线里的非对象会在 `_vitals` 里抛 `AttributeError`。现在跳过。
- 运行目录已经不在时，`GET /api/runs/{id}/report` 在拼路径时 500。现在是 404。模组 zip 列出的文件缺失时，`t(..., key=...)` 和参数名撞车，变成 `TypeError`。现在返回原来的「文件不在 zip 里」。

## 按模块 / Per module

语句覆盖率，含 0% 的未加载模块。空的 `__init__.py` 省略。

*Statement coverage, including modules the tests never load. Empty `__init__.py` files are omitted.*

| Coverage | Statements | Missed | Module |
|---:|---:|---:|---|
| 0.0% | 178 | 178 | `gui/app.py` |
| 0.0% | 19 | 19 | `gui/modpatch.py` |
| 0.0% | 125 | 125 | `gui/tests_e2e.py` |
| 0.0% | 304 | 304 | `gui/worker.py` |
| 0.0% | 2 | 2 | `sts2sim/__main__.py` |
| 0.0% | 49 | 49 | `sts2sim/dllmod/__main__.py` |
| 0.0% | 533 | 533 | `sts2sim/engine/agents.py` |
| 0.0% | 130 | 130 | `sts2sim/engine/combat.py` |
| 0.0% | 212 | 212 | `sts2sim/engine/decision_log.py` |
| 0.0% | 182 | 182 | `sts2sim/engine/gym.py` |
| 0.0% | 234 | 234 | `sts2sim/engine/imitate.py` |
| 0.0% | 240 | 240 | `sts2sim/engine/interactive.py` |
| 0.0% | 282 | 282 | `sts2sim/engine/manager.py` |
| 0.0% | 338 | 338 | `sts2sim/engine/mentor.py` |
| 0.0% | 276 | 276 | `sts2sim/engine/mentor_full.py` |
| 0.0% | 33 | 33 | `sts2sim/engine/mentor_text.py` |
| 0.0% | 537 | 537 | `sts2sim/engine/modai.py` |
| 0.0% | 389 | 389 | `sts2sim/engine/planner.py` |
| 0.0% | 84 | 84 | `sts2sim/engine/prefs.py` |
| 0.0% | 248 | 248 | `sts2sim/engine/run.py` |
| 0.0% | 174 | 174 | `sts2sim/engine/search.py` |
| 0.0% | 441 | 441 | `sts2sim/engine/strong.py` |
| 0.0% | 191 | 191 | `sts2sim/engine/textstate.py` |
| 0.0% | 16 | 16 | `sts2sim/engine/weights.py` |
| 0.0% | 1149 | 1149 | `sts2sim/engine/yamlmod.py` |
| 0.0% | 297 | 297 | `sts2sim/rt/patches.py` |
| 0.0% | 82 | 82 | `tools/ab_card.py` |
| 0.0% | 15 | 15 | `tools/ai_compare.py` |
| 0.0% | 93 | 93 | `tools/bench.py` |
| 0.0% | 88 | 88 | `tools/boss_bench.py` |
| 0.0% | 160 | 160 | `tools/convert_claude_v35.py` |
| 0.0% | 1648 | 1648 | `tools/cs2py_core.py` |
| 0.0% | 1110 | 1110 | `tools/cs2py_files.py` |
| 0.0% | 54 | 54 | `tools/cs_patches.py` |
| 0.0% | 29 | 29 | `tools/explain_fight.py` |
| 0.0% | 30 | 30 | `tools/extract_v35.py` |
| 0.0% | 64 | 64 | `tools/imitate.py` |
| 0.0% | 25 | 25 | `tools/import_codex.py` |
| 0.0% | 6 | 6 | `tools/import_dll_mod.py` |
| 0.0% | 74 | 74 | `tools/mcp_e2e.py` |
| 0.0% | 276 | 276 | `tools/parity_v35.py` |
| 0.0% | 104 | 104 | `tools/parity_yaml.py` |
| 0.0% | 80 | 80 | `tools/parse_encounters.py` |
| 0.0% | 281 | 281 | `tools/parse_monster_ai.py` |
| 0.0% | 215 | 215 | `tools/seed_probe.py` |
| 0.0% | 83 | 83 | `tools/sim_session.py` |
| 0.0% | 51 | 51 | `tools/sync_claude_text.py` |
| 0.0% | 47 | 47 | `tools/trace_run.py` |
| 0.0% | 111 | 111 | `tools/tune_cma.py` |
| 0.0% | 30 | 30 | `tools/undefined_names.py` |
| 5.1% | 99 | 94 | `sts2sim/rt/boot.py` |
| 7.7% | 310 | 286 | `tools/batch.py` |
| 8.6% | 151 | 138 | `sts2sim/catalog.py` |
| 22.0% | 404 | 315 | `tools/mcp_server.py` |
| 22.4% | 174 | 135 | `sts2sim/runner.py` |
| 23.8% | 202 | 154 | `sts2sim/engine/style.py` |
| 26.9% | 509 | 372 | `sts2sim/rt/cs.py` |
| 29.2% | 614 | 435 | `sts2sim/enemies.py` |
| 31.1% | 177 | 122 | `gui/jobs.py` |
| 31.9% | 226 | 154 | `gui/packaging/dry_check.py` |
| 36.7% | 746 | 472 | `sts2sim/rt/linq.py` |
| 37.0% | 235 | 148 | `gui/modeditor.py` |
| 45.1% | 284 | 156 | `sts2sim/gamedata.py` |
| 51.6% | 281 | 136 | `gui/backend.py` |
| 55.0% | 685 | 308 | `sts2sim/rt/prelude.py` |
| 57.4% | 129 | 55 | `sts2sim/modloader.py` |
| 65.0% | 40 | 14 | `sts2sim/potions.py` |
| 67.2% | 415 | 136 | `sts2sim/explain.py` |
| 67.7% | 93 | 30 | `sts2sim/gameloc.py` |
| 68.2% | 22 | 7 | `gui/paths.py` |
| 69.4% | 497 | 152 | `sts2sim/dllmod/package.py` |
| 71.8% | 149 | 42 | `gui/metrics.py` |
| 72.7% | 488 | 133 | `gui/server.py` |
| 73.0% | 315 | 85 | `sts2sim/report.py` |
| 76.2% | 80 | 19 | `sts2sim/expr.py` |
| 78.8% | 593 | 126 | `sts2sim/modfmt/schema.py` |
| 81.3% | 337 | 63 | `sts2sim/ai/base.py` |
| 84.0% | 94 | 15 | `sts2sim/dllmod/metadata.py` |
| 85.4% | 130 | 19 | `gui/i18n.py` |
| 87.2% | 78 | 10 | `tools/calibrate.py` |
| 87.2% | 596 | 76 | `sts2sim/dllmod/extract.py` |
| 88.2% | 553 | 65 | `sts2sim/engine/seedpreview.py` |
| 88.9% | 407 | 45 | `sts2sim/analysis.py` |
| 89.0% | 254 | 28 | `sts2sim/engine/mentor_paths.py` |
| 89.4% | 715 | 76 | `sts2sim/core.py` |
| 91.1% | 179 | 16 | `tools/import_run.py` |
| 91.7% | 48 | 4 | `tools/seed_preview.py` |
| 93.1% | 72 | 5 | `sts2sim/ai/heuristic.py` |
| 93.3% | 15 | 1 | `sts2sim/engine/seed.py` |
| 94.3% | 87 | 5 | `tools/ab_table.py` |
| 95.1% | 223 | 11 | `sts2sim/powers.py` |
| 95.1% | 493 | 24 | `sts2sim/calibrate.py` |
| 95.5% | 286 | 13 | `sts2sim/cards.py` |
| 95.7% | 799 | 34 | `sts2sim/saveimport.py` |
| 96.0% | 99 | 4 | `tools/ai_summary.py` |
| 96.2% | 105 | 4 | `sts2sim/stats.py` |
| 96.7% | 122 | 4 | `sts2sim/ai/beam.py` |
| 98.8% | 81 | 1 | `sts2sim/fightcheck.py` |
| 99.3% | 139 | 1 | `sts2sim/powers_enemy.py` |
| 100.0% | 1 | 0 | `sts2sim/__init__.py` |
| 100.0% | 4 | 0 | `sts2sim/ai/__init__.py` |
| 100.0% | 2 | 0 | `sts2sim/dllmod/__init__.py` |
| 100.0% | 5 | 0 | `sts2sim/gen/__init__.py` |
| 100.0% | 1 | 0 | `sts2sim/modfmt/__init__.py` |
| 100.0% | 23 | 0 | `sts2sim/relics.py` |

