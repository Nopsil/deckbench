"""游戏种子：和真游戏一样的规范化。

真游戏（v0.111）：
  - 随机生成的种子：12 位，字符集 0-9 A-H J-N P-Z（SeedHelper.GetRandomSeed，没有 I 和 O）
  - 自定义模式手输的种子：SeedHelper.CanonicalizeSeed —— 转大写、O→0、I→1、去首尾空格，然后原样使用
  - 之后 Rng(StringHelper.GetDeterministicHashCode(seed))（v0.111 = XxHash64），引擎里已一致
我们内部的批量种子 R0、R1… 也是普通种子字符串（规范化后不变），所以 --seed R5 和批量里的 R5 是同一局。
"""
SEED_CHARS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
SEED_LEN = 12


def canonicalize(seed):
    """= SeedHelper.CanonicalizeSeed（C#：ToUpperInvariant → Replace('O','0') → Replace('I','1') → Trim）。"""
    return str(seed).upper().replace("O", "0").replace("I", "1").strip()


def warnings(raw, canon=None):
    canon = canonicalize(raw) if canon is None else canon
    w = []
    if raw != canon:
        w.append(f"种子已按游戏规则规范化：{raw!r} → {canon!r}")
    bad = sorted({c for c in canon if c not in SEED_CHARS})
    if bad:
        w.append(f"含随机种子字符集以外的字符 {bad}（自定义模式手输可以，但游戏随机生成的种子不会有）")
    elif len(canon) != SEED_LEN:
        w.append(f"长度 {len(canon)}，游戏随机生成的种子是 {SEED_LEN} 位")
    return w
