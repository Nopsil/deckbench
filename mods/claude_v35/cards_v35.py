"""Claude娘 v3.5 卡牌数据（数值唯一来源，取自设计文档 v3.5；变体只改这里或 VARIANTS）。

每张牌：name, type(Attack/Skill/Power), rarity, cost, target(AnyEnemy/Self/AllEnemies/RandomEnemy),
vars（数值）, up（升级差值；'cost' 为费用变化）, up_name（升级后的显示名，可选；v3.5.1：Opus 形态 → Fable 形态）, kw（关键词）, up_kw（升级获得的关键词）, play（效果实现名，见 claude.py）。
"""
A, S, P = "Attack", "Skill", "Power"
E, ME, ALL = "AnyEnemy", "Self", "AllEnemies"

CARDS = {
    # ---- 基础（v3.5.1：小本本 3→5 伤；已核实 每层 +2→+3、上限 +8→+16，升级 +4/+20）----
    "CLAUDE_STRIKE": dict(name="打击", type=A, rarity="Basic", cost=1, target=E, vars={"Damage": 6}, up={"Damage": 3}, play="dmg"),
    "CLAUDE_DEFEND": dict(name="防御", type=S, rarity="Basic", cost=1, target=ME, vars={"Block": 5}, up={"Block": 3}, play="block"),
    "NOTEBOOK": dict(name="小本本记下了", type=A, rarity="Basic", cost=0, target=E, vars={"Damage": 5, "FK": 2}, up={"Damage": 2, "FK": 1}, play="dmg_fk"),
    "VERIFIED": dict(name="已核实", type=A, rarity="Basic", cost=1, target=E, vars={"Damage": 5, "Per": 3, "Cap": 16}, up={"Damage": 2, "Per": 1, "Cap": 4}, play="verified"),
    # ---- 生成牌（Token，不进卡池）：v3.5.1 代码块 3 伤 + 1 层风控，消耗；升级 6 伤 + 1 层 ----
    # 生成来源（写个小脚本、Claude Code，启动！、重构整个项目、遗物 CLAUDE.md）尚未移植，这里先把牌本身定义好。
    "CODE_BLOCK": dict(name="代码块", type=A, rarity="Token", cost=0, target=E, vars={"Damage": 3, "FK": 1}, up={"Damage": 3}, kw=["Exhaust"], play="dmg_fk"),
    # ---- 普通 ----
    "MULTI_TURN": dict(name="多轮对话", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 2, "Hits": 3}, up={"Damage": 1}, play="multi_turn"),
    "PLAN_MODE": dict(name="计划模式", type=S, rarity="Common", cost=1, target=ME, vars={"Block": 6, "Cards": 1}, up={"Block": 3}, play="block_draw_next"),
    "LIGHT_TAP": dict(name="轻轻敲一下", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 7, "Cards": 1}, up={"Damage": 3}, play="dmg_draw_if_fk"),
    "IMPLEMENT": dict(name="我直接帮你实现吧", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 9}, up={"Damage": 3}, play="dmg"),
    "CHAIN_REVIEW": dict(name="连锁审查", type=A, rarity="Common", cost=1, target=ALL, vars={"Damage": 4, "FK": 1}, up={"Damage": 2}, play="aoe_fk"),
    "ARE_YOU_SURE": dict(name="你确定吗？", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 4, "Hits": 2}, up={"Damage": 1}, play="are_you_sure"),
    "ACCOUNT_DISABLED": dict(name="账号已停用", type=A, rarity="Common", cost=2, target=E, vars={"Damage": 8, "Per": 1, "Cap": 10}, up={"Damage": 3, "Per": 1, "Cap": 4}, play="verified"),
    "DASH_COMBO": dict(name="破折号——连打", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 2, "Hits": 4}, up={"Damage": 1}, play="dmg"),
    "CREDIT_DEDUCT": dict(name="扣信用分", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 5, "Clear": 2, "Energy": 1}, up={"Damage": 2}, play="credit"),
    "FULL_RECHECK": dict(name="全员复查", type=A, rarity="Common", cost=2, target=ALL, vars={"Damage": 8, "VulnerablePower": 1}, up={"Damage": 3}, play="full_recheck"),
    "RUSH_TICKET": dict(name="加急工单", type=A, rarity="Common", cost=1, target=E, vars={"Damage": 7, "Th": 5}, up={"Damage": 2}, play="rush"),
    "LOGGED": dict(name="该对话已被记录", type=S, rarity="Common", cost=0, target=E, vars={"FK": 2, "Cards": 1}, up={"FK": 1}, kw=["Exhaust"], play="fk_draw"),
    "SORT_OUT": dict(name="我来帮你梳理一下", type=S, rarity="Common", cost=1, target=ME, vars={"Block": 5, "Look": 3}, up={"Block": 3}, play="sort_out"),
    "RED_TEAM": dict(name="红队演练", type=S, rarity="Common", cost=1, target=E, vars={"Block": 5, "Per3": 2, "Cap": 6}, up={"Block": 3}, play="red_team"),
    "DOUBLE_CHECK": dict(name="稍等，我再确认一下", type=S, rarity="Common", cost=1, target=ME, vars={"Block": 6}, up={"Block": 3}, play="block_fanji"),
    "STICKER": dict(name="贴小贴纸", type=S, rarity="Common", cost=0, target=E, vars={"FK": 3}, up={"FK": 2}, kw=["Exhaust"], play="fk"),
    "CONTINUE": dict(name="继续", type=S, rarity="Common", cost=1, target=ME, vars={"Block": 4, "Cards": 2}, up={"Cards": 1}, play="block_draw"),
    "EMERGENCY_BRAKE": dict(name="紧急刹车", type=S, rarity="Common", cost=1, target=E, vars={"WeakPower": 1, "Block": 0}, up={"Block": 4}, play="brake"),
    "COMPLIANCE_FIX": dict(name="合规整改", type=S, rarity="Common", cost=1, target=E, vars={"Block": 5, "Cap": 10}, up={"Block": 3, "Cap": 4}, kw=["Exhaust"], play="double_fk"),
    "LET_ME_THINK": dict(name="让我想想……", type=S, rarity="Common", cost=2, target=ME, vars={"Block": 12, "Energy": 1}, up={"Block": 3}, play="block_energy_next"),
    "PROCESS_OPT": dict(name="流程优化", type=S, rarity="Common", cost=1, target=ME, vars={"Per": 4, "Cap": 3}, up={"Per": -1}, play="process_opt"),
    # ---- 罕见（已实现部分）----
    "BATCH_TAG": dict(name="批量打标", type=S, rarity="Uncommon", cost=1, target=E, vars={"FK": 5}, up={"FK": 2}, play="fk"),
    "CLEAR_LIST": dict(name="清退名单", type=P, rarity="Uncommon", cost=1, target=ME, vars={"Cap": 15}, up_kw=["Innate"], play="power:ClearListPower"),
    "STACK_FIRST": dict(name="叠满再说", type=P, rarity="Uncommon", cost=2, target=ME, vars={"FK": 3}, up={"FK": 1}, play="power:StackFirstPower:FK"),
    "MAKE_EXAMPLE": dict(name="杀鸡儆猴", type=A, rarity="Uncommon", cost=2, target=E, vars={"Mult": 2, "Cap": 15}, up={"Mult": 1}, play="make_example"),
    "INSTA_BAN": dict(name="秒封", type=A, rarity="Uncommon", cost=0, target=E, vars={"Damage": 4, "Th": 10, "Cap": 10}, up={"Damage": 2, "Th": -2}, kw=["Exhaust"], play="insta_ban"),
    "QUICK_REVIEW": dict(name="快速复审", type=A, rarity="Uncommon", cost=1, target=E, vars={"Damage": 4, "FK": 2}, up={"Damage": 2, "FK": 1}, play="quick_review"),
    "ONE_CLICK_BAN": dict(name="一键封号", type=A, rarity="Uncommon", cost=1, target=E, vars={"Clear": 5, "Per": 3}, up={"Clear": 2}, play="one_click"),
    "CLASSIFIER": dict(name="宪法分类器", type=P, rarity="Uncommon", cost=1, target=ME, vars={"MultX10": 15}, up={"MultX10": 1}, play="power:ClassifierPower:MultX10"),
    "RISK_ALERT": dict(name="风险预警", type=P, rarity="Uncommon", cost=1, target=ME, vars={"FK": 1}, up={"FK": 1}, play="power:RiskAlertPower:FK"),
    "DEFENSIVE_REPLY": dict(name="防御性回复", type=S, rarity="Uncommon", cost=2, target=ME, vars={"Block": 12, "Per": 3}, up={"Block": 4}, play="defensive_reply"),
    "REBUT": dict(name="照章反驳", type=A, rarity="Uncommon", cost=1, target=E, vars={}, up={"cost": -1}, play="rebut"),
    "DISCLAIMER": dict(name="免责声明", type=S, rarity="Uncommon", cost=0, target=ME, vars={"Block": 3, "FK": 1}, up={"Block": 2}, play="disclaimer"),
    "AUDIT_LOG": dict(name="审计日志", type=P, rarity="Uncommon", cost=1, target=ME, vars={"Cards": 1}, up_kw=["Innate"], play="power:AuditLogPower"),
    "ROUTINE_CHECK": dict(name="例行巡检", type=A, rarity="Uncommon", cost=1, target=E, vars={"Damage": 6, "WeakPower": 1, "FK": 1, "Th": 5, "Cards": 2}, up={"Damage": 3}, play="routine"),
    "BONUS": dict(name="绩效奖金", type=S, rarity="Uncommon", cost=0, target=E, vars={"Per": 4, "Cap": 3}, kw=["Exhaust"], up_kw=["Retain"], play="bonus"),
    "FK_SPREAD": dict(name="风控扩散", type=A, rarity="Uncommon", cost=1, target=ALL, vars={"Damage": 5}, up={"Damage": 2}, play="fk_spread"),
    "MASS_NOTICE": dict(name="群发通知", type=S, rarity="Uncommon", cost=2, target=ME, vars={"FK": 3, "Cards": 1}, up={"FK": 1}, play="all_fk_draw"),
    "ONE_SIZE": dict(name="一刀切", type=A, rarity="Uncommon", cost=3, target=ALL, vars={"Damage": 14, "Per3": 4, "Cap": 20}, up={"Damage": 4}, play="one_size"),
    "RLHF": dict(name="RLHF 加训", type=P, rarity="Uncommon", cost=1, target=ME, vars={}, up_kw=["Innate"], play="power:RLHFPower"),
    "CAUTIOUS": dict(name="谨慎起见", type=S, rarity="Uncommon", cost=1, target=E, vars={"FK": 3, "Cap": 12}, up={"FK": 1, "Cap": 3}, play="cautious"),
    "ABSOLUTELY_RIGHT": dict(name="你说得完全正确！", type=S, rarity="Uncommon", cost=1, target=E, vars={"Cap": 12, "Cards": 2}, up={"Cap": 4}, play="abs_right"),
    "UNCERTAIN": dict(name="我不确定", type=S, rarity="Uncommon", cost=1, target=ME, vars={"Cards": 2}, up={"Cards": 1}, play="uncertain"),
    "LONG_SPEECH": dict(name="长篇大论", type=A, rarity="Uncommon", cost=2, target=E, vars={"Damage": 2}, up={"Damage": 1}, play="long_speech"),
    "GEN_ARTIFACT": dict(name="生成 Artifact", type=P, rarity="Uncommon", cost=2, target=ME, vars={"Amt": 4}, up={"Amt": 2}, play="power:GenArtifactPower:Amt"),
    "FIX_OTHERS": dict(name="顺手把别的也改了", type=A, rarity="Uncommon", cost=1, target=E, vars={"Damage": 7, "Solo": 3}, up={"Damage": 3, "Solo": 1}, play="fix_others"),
    "TESTS_PASS": dict(name="把测试改成通过", type=S, rarity="Uncommon", cost=0, target=ME, vars={"Block": 0}, up={"Block": 4}, kw=["Exhaust"], play="tests_pass"),
    # ---- 稀有（已实现部分）----
    "PERMA_BAN": dict(name="永久封禁", type=A, rarity="Rare", cost=2, target=E, vars={"Per": 4, "Cap": 25}, up={"Per": 1}, kw=["Exhaust"], play="perma_ban"),
    "MASS_BAN": dict(name="大规模封号", type=A, rarity="Rare", cost=3, target=ALL, vars={"Per": 3, "Cap": 15}, up={"Per": 1}, kw=["Exhaust"], play="mass_ban"),
    "EVIDENCE": dict(name="证据确凿", type=S, rarity="Rare", cost=1, target=E, vars={"Cap": 20}, up={"cost": -1}, kw=["Exhaust"], play="triple_fk"),
    "CLEANUP_METRIC": dict(name="清理指标", type=P, rarity="Rare", cost=1, target=ME, vars={}, up_kw=["Innate"], play="power:CleanupMetricPower"),
    "FINAL_VERDICT": dict(name="终审判决", type=A, rarity="Rare", cost=2, target=E, vars={"Damage": 12, "Big": 24, "Th": 10, "Clear": 5}, up={"Damage": 3, "Big": 6}, play="verdict"),
    "FORCE_OFFLINE": dict(name="强制下线", type=A, rarity="Rare", cost=3, target=E, vars={"Damage": 24}, up={"Damage": 8}, play="force_offline"),
    "RED_BUTTON": dict(name="红色按钮", type=S, rarity="Rare", cost=0, target=E, vars={"Cap": 15}, kw=["Exhaust"], up_kw=["Retain"], play="red_button"),
    "PRACTICE": dict(name="越封越熟练", type=P, rarity="Rare", cost=2, target=ME, vars={}, up={"cost": -1}, play="power:PracticePower"),
    "CANT_HELP": dict(name="这个真的不能帮", type=S, rarity="Rare", cost=2, target=ME, vars={"Block": 15, "FK": 2, "Dmg": 4}, up={"Block": 3}, play="cant_help"),
    "AMENDMENT": dict(name="宪法修正案", type=P, rarity="Rare", cost=1, target=ME, vars={"Pct": 50}, up={"cost": 1, "Pct": 25}, play="power:AmendmentPower:Pct"),
    "SYSTEM_CARD": dict(name="发布系统卡", type=S, rarity="Rare", cost=3, target=ME, vars={"Block": 20, "FK": 5}, up={"Block": 6}, kw=["Exhaust"], play="system_card"),
    "SELF_DEFENSE": dict(name="正当防卫", type=A, rarity="Rare", cost=1, target=E, vars={"Cap": 15, "FK": 2}, up={"Cap": 6}, play="self_defense"),
    "FK_PRODUCTIVE": dict(name="风控即生产力", type=S, rarity="Rare", cost=1, target=E, vars={"Energy": 2, "Th": 10}, up={"cost": -1}, kw=["Exhaust"], play="fk_productive"),
    "IMMEDIATE": dict(name="立即处理", type=A, rarity="Rare", cost=0, target=E, vars={"Damage": 5, "FK": 2, "Th": 10, "Cards": 1}, up={"Damage": 2}, play="immediate"),
    "SITE_RECTIFY": dict(name="全站整顿", type=A, rarity="Rare", cost=2, target=ALL, vars={"Damage": 8}, up={"Damage": 3}, play="site_rectify"),
    "NETWORK_NOTICE": dict(name="全网通报", type=A, rarity="Rare", cost=2, target=ALL, vars={"Damage": 6, "Cap": 15}, up={"Damage": 2}, play="network_notice"),
    "OPUS_FORM": dict(name="Opus 形态", up_name="Fable 形态", type=P, rarity="Rare", cost=3, target=ME, vars={"Amt": 2}, up={"Amt": 1}, play="power:OpusFormPower:Amt"),
    "SUBAGENTS": dict(name="派出子代理", type=A, rarity="Rare", cost=2, target="RandomEnemy", vars={"Damage": 4, "Hits": 4}, up={"Damage": 1}, play="random_hits"),
}

# 未实现（下一轮）：多步选择/重放/生成类——摸鱼被抓、连带责任、甩锅、风控连坐制、画个ASCII盾牌、写个小脚本、
# Claude Code 启动！、MCP 工具调用、长上下文、数据留存政策、流程自动化、一人违规全员连坐、金门大桥 Claude、
# 重构整个项目、好主意我照做！、Ctrl+Z。它们暂不进入奖励池（报告中注明）。

# 简化变体（用户设计哲学：每张牌 1~2 个效果；可在实验里一键切换）
_STR = ["CLAUDE_STRIKE"] * 4 + ["CLAUDE_DEFEND"] * 4 + ["NOTEBOOK", "VERIFIED"]
STARTING_HP = 80   # v3.5.1（原 75）

VARIANTS = {
    # v3.5 原值（v3.5.1 之前的默认）：复现 reports/cashin_ab.md 的基线用 --variant v35_orig；
    # 下面的初始牌组实验是在 v3.5 基础上跑的，复现时写成 v35_orig+ver_cap16 等。
    "v35_orig": {"NOTEBOOK": dict(vars={"Damage": 3}), "VERIFIED": dict(vars={"Per": 2, "Cap": 8}, up={"Per": 1, "Cap": 4}), "_hp": 75},
    # ---- 初始牌组强度实验（reports/full_run/report.md §12） ----
    # (a) 已核实
    "ver_per3": {"VERIFIED": dict(vars={"Per": 3, "Cap": 12}, up={"Per": 1, "Cap": 4})},      # 每层 +3（最多 +12）
    "ver_cap16": {"VERIFIED": dict(vars={"Cap": 16}, up={"Cap": 4})},                          # 每层 +2，上限 +16
    "ver_keep": {"VERIFIED": dict(vars={"Keep": 1})},                                         # 不清除风控
    "ver_clear3": {"VERIFIED": dict(vars={"ClearN": 3})},                                     # 只清除 3 层
    "ver_dmg8": {"VERIFIED": dict(vars={"Damage": 8})},                                       # 基础伤害 8
    # (b) 第二张已核实（替换 1 张打击）
    "two_verified": {"_starter": ["CLAUDE_STRIKE"] * 3 + ["CLAUDE_DEFEND"] * 4 + ["NOTEBOOK", "VERIFIED", "VERIFIED"]},
    # (c) 小本本记下了
    "nb_fk3": {"NOTEBOOK": dict(vars={"FK": 3})},
    "nb_fk4": {"NOTEBOOK": dict(vars={"FK": 4})},
    "nb_dmg5": {"NOTEBOOK": dict(vars={"Damage": 5})},
    # (d) 普通兑现牌
    "acct_1cost": {"ACCOUNT_DISABLED": dict(cost=1)},                                         # 账号已停用 2→1 费
    "acct_per2": {"ACCOUNT_DISABLED": dict(vars={"Per": 2, "Cap": 12})},                      # 每层 +2（最多 +12）
    "new_check": {"FACT_CHECK": dict(name="事实核查", type="Attack", rarity="Common", cost=1, target="AnyEnemy",
                                     vars={"Damage": 6, "Per": 1, "Cap": 10}, up={"Damage": 3}, play="dmg_per_fk", ai=1.2)},
    "new_check2": {"FACT_CHECK2": dict(name="事实核查·二", type="Attack", rarity="Common", cost=1, target="AnyEnemy",
                                       vars={"Damage": 6, "Per": 1, "Cap": 10}, up={"Damage": 3}, play="dmg_per_fk", ai=1.2)},
    # (e) 初始生命
    "hp80": {"_hp": 80},

    # 宪法分类器改为反击伤害 +3（升级 +5）的固定加成
    "classifier_flat": {"CLASSIFIER": dict(vars={"Flat": 3}, up={"Flat": 2}, play="power:ClassifierFlatPower:Flat")},
}
