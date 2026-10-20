# Claude娘 v3.5 → 新引擎（整局）移植

- `design_v35.json`：由 `tools/extract_v35.py` 从设计文档（只读）抽出的
  86 张卡（4 张初始专属/基础 + 82 张奖励池）与遗物表。**这是唯一的数值来源**；简化变体（如宪法分类器改为反击 +3/+5）
  只改这里或 `variants` 覆盖表，不改实现代码。
- 状态：**已接入新引擎（可跑整局）**。69 张牌（4 基础 + 21 普通 + 26 罕见 + 18 稀有）已实现；17 张复杂牌暂未实现、
  不进入奖励池（见 `cards_v35.py` 末尾清单）。（scripts/v35_data.py 只有 .pyc，所以从设计文档表格抽取。）

## v3.5.1 默认值（2026-10-20，用户批准）
- 已核实：每层 +3、最多 +16（升级 +4 / +20）；小本本记下了：5 伤（升级 7）；初始生命 80（`cards_v35.STARTING_HP`）。
- 依据：`reports/cashin_ab.md`（定稿行 `per3cap16_nbdmg5_hp80`）。现在不带变体跑出的结果和该行逐局一致（已抽查 80 局）。
- `--variant v35_orig` 还原 v3.5 原值（小本本 3 伤、已核实 +2/+8、生命 75），和改动前的默认值逐局一致；
  `cashin_ab.md` 里的单项实验是在 v3.5 上做的，复现时写 `v35_orig+ver_cap16` 这样。
- `tools/parity_v35.py` 默认用 `v35_orig` 跟旧引擎（v3.5 原值）对拍。

```python
import sys; sys.path.insert(0, "mods")
from claude_v35 import claude as CL
CL.load()                       # 或 CL.load(variant="classifier_flat")
from sts2sim.engine.run import play_run
play_run("Claude", 10, "R0")
```
批量：`python3 tools/batch.py --char Claude --asc 10 --n 200 --agent strong-nosearch [--variant classifier_flat]`

## 文件
- `cards_v35.py`：卡牌数据表（名称/类型/稀有度/费用/目标/数值/升级/关键词/效果函数名）。**改数值或做简化变体只动这里**，
  `VARIANTS` 是覆盖表（例：`classifier_flat` = 宪法分类器改为反击伤害固定 +3，升级 +5）。
- `claude.py`：风控事件契约（give/clear/set_fk）、【反击】、宪法（口袋版）遗物、各牌效果、生成 CardModel 子类、角色与卡池注册。
- `ai_values.py`：AI 估值表（选牌估值 MOD_POWER、出牌修正 PLAY_ADJUST、风控层数价值 POWER_VALUE）。属于 AI 近似，不是规则。
- 测试：`tests/test_claude_v35.py` 校验每段攻击的结算顺序（宪法 +2 → 免责声明 +1 → 反伤 1+⌊层/2⌋ → 层数 −1）。

## 近似 / 未实现
- 17 张复杂牌未实现、不进奖励池：摸鱼被抓、连带责任、甩锅、风控连坐制、画个ASCII盾牌、写个小脚本、Claude Code启动、MCP、
  长上下文、数据留存政策、流程自动化、一人违规全员连坐、金门大桥、重构整个项目、好主意我照做、Ctrl+Z、深度思考。
- 「我来帮你梳理一下」自动选看到的 3 张里估值最高的一张（不询问 AI）。
- 「强制下线」的减费（每清除 10 层 −1）未实现。
- 角色药水池为空（只会出通用药水）；角色遗物池只有初始遗物「宪法」（只会出通用遗物）。
- 「多轮对话」按 3 次独立攻击结算。
- 初始 HP 75、金币 99（设计文档未给出时的假设）。
- 远古事件遗物「积灰的典籍」：Claude 没有远古稀有度的牌，改为从稀有牌中抽一张。
- 尚未与旧引擎（mods/claude_v34）做单场对拍。

## 实现计划
1. 效果原语（每张牌 1~2 个）：deal(n, hits, target)、block(n)、apply_fk(n, target/all)、clear_fk(target, cap)、
   gain_fanji(1)、draw(n)、energy(n)、weak/vuln(n)，以及按风控层数缩放的 scale(fk, per, cap)。
   每张牌 = 原语列表 + 升级差值，写成 Python 数据表 `cards_v35.py`（由 design_v35.json 半自动生成，再人工校对）。
2. 用原语生成转译后游戏 `CardModel` 的子类（CanonicalVars/OnPlay/OnUpgrade 调用 DamageCmd、CreatureCmd.GainBlock、
   PowerCmd.Apply、CardPileCmd.Draw 等游戏命令），注册进 ModelDb，并新增角色 / 卡池 / 遗物池。
3. 风控 FK = PowerModel 子类，按 v3.5 风控事件契约实现：给予 / 清除 / 层数操作三类分开；
   主动给予与被动给予分开（遗物 / 敌方回合）；人工制品拦截；RLHF 只修正数量。
   【反击】= 玩家 PowerModel：按段结算（先挂层、再反伤 1+⌊FK/2⌋（Unpowered）、再减 1 层 FK），
   回合开始 -1 层，上限 3 层；宪法分类器倍率（向下取整）→ 宪法修正案（向上取整）。
4. 剩下约 15 张复杂牌手写（重放、Ctrl+Z、MCP、深度思考、长上下文、数据留存政策、金门大桥等）。
5. 验收：在旧引擎（mods/claude_v34，规则重叠的部分）上用固定战斗对拍，再跑 A10/A0 整局，和原版角色用同一个 AI 比较。

## 对拍与单卡 A/B
- `.venv/bin/python tools/parity_v35.py [--only CID,...]`：和旧引擎（mods/claude_v34，v3.5 规则开关）逐场景对拍，
  1518 个场景中 1436 个一致，其余差异见 reports/full_run/report.md §11.1（都是旧引擎的 v3.4 数值、随机目标或对拍方法本身的问题）。
- `PYTHONPATH=. python3 tools/ab_card.py --char Claude --asc 0 --n 400 --force CLAUDE_PERMA_BAN --replace CLAUDE_STRIKE`：
  强制入组的单卡 A/B（同种子配对）。
- AI 估值模式：`STS2SIM_CLAUDE_AI=deck`（默认，按牌组估计每层风控价值 + 选牌协同）/ `flat`（每层固定 1.2）/ `nobias` / `nolv`。
