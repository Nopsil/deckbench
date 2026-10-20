"""转译前对反编译 C# 源码打的结构化补丁（主要消除反编译器产生的 goto）。
每个补丁：(相对路径, 正则, 替换)。语义保持与原代码一致，只去掉视觉相关分支。"""
import re

PATCHES = [
    # （v0.111：CardPileCmd.Add 已无 goto，满手进弃牌堆是原生逻辑，旧补丁删除）
    # RewardsCmd.OfferForRoomEnd
    ("Commands/RewardsCmd.cs",
     r"\t\tRewardsSet rewardsSet;\n\t\tif \(room is CombatRoom combatRoom\)\n.*?IL_00b[0-9a-f]:\n",
     "\t\tRewardsSet rewardsSet;\n\t\tif (room is CombatRoom combatRoom && combatRoom.Encounter != null && !combatRoom.Encounter.ShouldGiveRewards)\n"
     "\t\t{\n\t\t\trewardsSet = new RewardsSet(player).EmptyForRoom(room);\n\t\t}\n\t\telse\n\t\t{\n"
     "\t\t\trewardsSet = new RewardsSet(player).WithRewardsFromRoom(room);\n\t\t}\n"),
    # Hook.ModifyDamage：多目标预览判定
    ("Hooks/Hook.cs",
     r"\t\tbool flag = target == null && previewMode == CardPreviewMode.MultiCreatureTargeting;\n.*?\t\tgoto IL_00bf;\n\t\tIL_00bf:\n\t\tbool flag4 = flag2;\n",
     "\t\tbool flag2 = target == null && previewMode == CardPreviewMode.MultiCreatureTargeting && cardSource != null"
     " && ((int)cardSource.TargetType == 3 || (int)cardSource.TargetType == 4) && cardSource.Pile != null"
     " && (cardSource.Pile.Type == PileType.Hand || cardSource.Pile.Type == PileType.Play);\n\t\tbool flag4 = flag2;\n"),
    ("Hooks/Hook.cs",
     r"\t\treturn Math.Max\(0m, num\);\n\t\tIL_00bb:\n\t\tflag2 = flag3;\n\t\tgoto IL_00bf;\n",
     "\t\treturn Math.Max(0m, num);\n"),
    # v0.111 FoulPotion.PassesCustomUsabilityCheck：商店/假商人判定的 goto 链 → 结构化
    ("Models/Potions/FoulPotion.cs",
     r"\t\t\tif \(currentRoom is MerchantRoom\)\n.*?\t\t\tIL_0040:\n\t\t\tflag = true;\n\t\t\tgoto IL_0046;\n",
     "\t\t\tbool flag = currentRoom is MerchantRoom || (currentRoom is EventRoom eventRoom && eventRoom.CanonicalEvent is FakeMerchant);\n"
     "\t\t\tif (flag)\n\t\t\t{\n\t\t\t\treturn GetFoulPotionMerchantTarget(currentRoom).button != null;\n\t\t\t}\n\t\t\treturn false;\n"),
    # （v0.111 CombatManager 的 InlineArray 集合表达式改由 apply_global 通用处理）
    # v0.111 BowlbugsNormal.AllPossibleMonsters：集合表达式 [.. keys, BowlbugRock]
    ("Models/Encounters/BowlbugsNormal.cs",
     r"\tpublic override IEnumerable<MonsterModel> AllPossibleMonsters\n\t\{\n.*?\n\t\}\n",
     "\tpublic override IEnumerable<MonsterModel> AllPossibleMonsters => _workerValidCounts.Keys.Concat(new MonsterModel[1] { ModelDb.Monster<BowlbugRock>() });\n"),
    # v0.111 DoomPower：静态/实例同名重载 GetDoomedCreatures，实例方法里的无限定调用要显式 this.
    ("Models/Powers/DoomPower.cs", r"await DoomKill\(GetDoomedCreatures\(side\)\);", "await DoomKill(this.GetDoomedCreatures(side));"),
    ("Models/Powers/DoomPower.cs", r"await DoomKill\(GetDoomedCreatures\(side\)\);", "await DoomKill(this.GetDoomedCreatures(side));"),  # 第二处（AfterSideTurnEnd）
    ("Models/Powers/DoomPower.cs", r"= GetDoomedCreatures\(base\.Owner\.Side\);", "= this.GetDoomedCreatures(base.Owner.Side);"),
    # v0.111 GoldAxe：C# 9 lambda 弃元参数 (CardModel _, Creature? _)
    ("Models/Cards/GoldAxe.cs", r"\(CardModel _, Creature\? _\)", "(CardModel _a, Creature? _b)"),
    # v0.111 CombatManager：Dictionary<Player,int>.GetValueOrDefault(player) 的默认值是 0（Python 字典不知道值类型）
    ("Combat/CombatManager.cs", r"_cardOrPotionEffectDepth\.GetValueOrDefault\(player\)", None),
    # v0.111 TreasureRoom.DoExtraRewardsIfNeeded：同步模型里 Task 恒为 null，去掉“本地任务为空”断言
    ("Rooms/TreasureRoom.cs",
     r"\t\tif \(localTask == null\)\n\t\t\{\n\t\t\tthrow new InvalidOperationException\([^\n]*\);\n\t\t\}\n", ""),
    # v0.111 CardModel.CardScope：((ICardScope)(expr)) 接口强转被误转成调用
    ("Models/CardModel.cs", r"\(\(ICardScope\)\(_owner\?\.Creature\.CombatState\)\)", "(_owner?.Creature.CombatState)"),
]


# 全局补丁（所有文件）：ilspycmd 9 把 [GeneratedRegex] 的 partial 方法展开成对生成器类的引用，还原成 partial 声明
_GEN_REGEX = re.compile(
    r"(\t*)(\[GeneratedRegex\([^\n]*\)\]\n)\t*\[GeneratedCode\([^\n]*\)\]\n"
    r"\t*((?:private|public|internal)(?: static)?) Regex (\w+)\(\)\n\t*\{\n\t*return _003CRegexGenerator[^\n]*;\n\t*\}\n")


# ilspycmd 9 对主构造函数（C# 12）的反编译：赋值语句后面跟 base._002Ector(...)，还原成 : base(...)
_PRIMARY_CTOR = re.compile(
    r"(?m)^(\t+)((?:public|internal|protected|private) \w+\([^)\n]*\))\n\1\{\n((?:\1\t[^\n]*\n)*?)\1\tbase\._002Ector\(([^\n]*)\);\n\1\}\n")


_NEW_NULLABLE = re.compile(r"new [A-Za-z_][\w.]*\?\(")


def _strip_new_nullable(src):
    """new T?(x) → (x)：可空包装在 Python 里就是值本身（ilspycmd 9 在三元表达式里会这样输出）"""
    out, i = [], 0
    while True:
        m = _NEW_NULLABLE.search(src, i)
        if not m:
            out.append(src[i:])
            return "".join(out)
        j, depth = m.end(), 1
        while depth and j < len(src):
            c = src[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == '"':
                j += 1
                while j < len(src) and src[j] != '"':
                    j += 2 if src[j] == "\\" else 1
            j += 1
        out.append(src[i:m.start()])
        out.append("(" + src[m.end():j - 1] + ")")
        i = j


def apply_global(src):
    if "?(" in src:
        src = _strip_new_nullable(src)
    # ilspycmd 输出 C# 8 using 声明（using Godot.FileAccess f = ...;），转译器只认 using (...) 语句；模拟里不需要 Dispose → 普通局部变量
    src = re.sub(r"(?m)^(\s+)using ((?:[\w.]+)(?:<[^>=]*>)?\??) (\w+) =", r"\1\2 \3 =", src)
    # 集合表达式降级出的 InlineArrayN<T> 缓冲区 → 普通数组
    if "InlineArray" in src:
        src = re.sub(r"global::_003C_003Ey__InlineArray(\d+)<([^<>]+(?:<[^<>]+>)?)> (\w+) = default\([^;]*\);",
                     r"\2[] \3 = new \2[\1];", src)
        src = re.sub(r"global::_003CPrivateImplementationDetails_003E\.InlineArrayElementRef<[^()]*>\(ref (\w+), (\d+)\)", r"\1[\2]", src)
        src = re.sub(r"global::_003CPrivateImplementationDetails_003E\.InlineArrayAs(?:ReadOnly)?Span<[^()]*>\((?:in|ref) (\w+), \d+\)", r"\1", src)
    src = _PRIMARY_CTOR.sub(lambda m: f"{m.group(1)}{m.group(2)}\n{m.group(1)}\t: base({m.group(4)})\n{m.group(1)}{{\n{m.group(3)}{m.group(1)}}}\n", src)
    return _GEN_REGEX.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)} partial Regex {m.group(4)}();\n", src)


def apply_patches(rel, src):
    rel = rel.replace("\\", "/")
    src = apply_global(src)
    for (f, pat, rep) in PATCHES:
        if f == rel:
            if rep is None and "GetValueOrDefault" in pat:
                new, n = re.subn(pat, "_cardOrPotionEffectDepth.GetValueOrDefault(player, 0)", src)
                if n == 0:
                    print(f"[cs_patches] 补丁未命中: {f} {pat[:60]!r}")
                src = new
                continue
            fn = lambda m: rep
            new, n = re.subn(pat, fn, src, count=1, flags=re.S)
            if n == 0:
                print(f"[cs_patches] 补丁未命中: {f} {pat[:60]!r}")
            src = new
    return src
