"""spire-codex 数据目录：遗物 / 药水 / 能力 / 怪物 / 遭遇的批量索引与实现覆盖率。

设计目标：原版内容「先导入、后实现」。
- codex_index(kind) 给出 {ID: 官方条目}（中文名、描述、稀有度、池子），mod/原版实现时只写效果，名字描述自动补全；
- coverage() 把官方全集和当前已注册的实现（POWER_TYPES / RELIC_TYPES / POTION_DEFS / 敌人状态机）对比，报告里列覆盖率；
- tools/import_codex.py 可以把还没实现的条目批量导出成 YAML 桩（方便 v0.2 逐个补效果）。
"""
import json
import os
from collections import Counter

from . import gamedata as _gd

DATA = _gd.codex_dir()   # 不随仓库分发
_IDX = {}


def codex_index(kind, lang="zhs"):
    key = (kind, lang)
    if key not in _IDX:
        path = os.path.join(DATA, f"{lang}_{kind}.json")
        _IDX[key] = {x["id"]: x for x in json.load(open(path, encoding="utf-8"))} if os.path.exists(path) else {}
    return _IDX[key]


def _pct(a, b):
    return f"{a}/{b}（{100 * a / max(1, b):.0f}%）"


def _pattern_kind(md):
    if not md.ai:
        return md.pattern_type or "—"
    kinds = {st["kind"] for st in md.ai["states"].values()}
    moves = [st for st in md.ai["states"].values() if st["kind"] == "move"]
    parts = []
    if "random" in kinds:
        reps = {b.get("repeat") for st in md.ai["states"].values() for b in st.get("branches", []) if st["kind"] == "random"}
        parts.append("概率选择" + ("（不能连续同招）" if "CannotRepeat" in reps else "") + ("（限连续次数）" if "CanRepeatXTimes" in reps else ""))
    if "conditional" in kinds:
        parts.append("条件分支")
    if not parts:
        parts.append("固定循环" if all(st.get("next") for st in moves) else "固定序列")
    if md.ai.get("initial_expr"):
        parts.append("开场招由遭遇设定")
    if any(st.get("must_perform_once") for st in moves):
        parts.append("击晕/强制招")
    return "、".join(parts)


def coverage(M=None):
    """返回覆盖率数据（dict），供报告使用。M：已加载的 ModSet（用于统计 mod 注册的实现）。"""
    from .core import POWER_TYPES
    from .relics import RELIC_TYPES
    from .potions import POTION_DEFS
    from . import enemies as EN
    db = EN.load_db()
    out = {}
    # ---- 敌人（只统计出现在第1-3幕遭遇里的）
    encs = [e for e in db["encounters"] if e.get("act") and e["act"][:5] in ("Act 1", "Act 2", "Act 3")]
    used = set()
    for e in encs:
        used.update(EN.possible_monsters(e))
    mons = []
    for mid in sorted(used):
        md = db["monsters"].get(mid)
        if md is None:
            mons.append({"id": mid, "name": mid, "intent": "缺失", "moves": 0, "notes": ["spire-codex 没有这个怪物"]})
            continue
        notes = list(md.ai_notes)
        moves = list(md.moves.values())
        n_code_moves = sum(1 for mv in moves if mv.src == "代码")
        summons = [mv.id for mv in moves if mv.summons or "Summon" in (mv.intent or "")]
        unimpl = sorted({pid for mv in moves for pid, _, _ in mv.powers if pid not in POWER_TYPES} |
                        {pid for pid, _ in md.innate if pid not in POWER_TYPES})
        if md.hp_missing:
            notes.append("没有血量数据")
        if summons:
            notes.append(f"召唤招式只结算数值部分：{','.join(summons)}")
        if unimpl:
            notes.append(f"未实现的能力（只记层数）：{','.join(unimpl)}")
        if n_code_moves:
            notes.append(f"{n_code_moves} 个招式数值取自代码（spire-codex 未收录）")
        n_lam = n_lam_ok = 0
        if md.ai_source == "代码":
            import random as _r
            fe = EN.Enemy(md, _r.Random(0))

            class _FC:
                enemies = [fe]
                turn = 1
            for st in md.ai["states"].values():
                for b in st.get("branches", []):
                    for key in ("condition", "weight"):
                        x = b.get(key)
                        if x is None or str(x).strip() in ("1", "1f"):
                            continue
                        n_lam += 1
                        try:
                            fe.cs_eval(x, _FC)
                            n_lam_ok += 1
                        except Exception:
                            notes.append(f"条件/权重无法求值：{x}")
            src = "代码" if not summons and not unimpl and not md.hp_missing and n_lam == n_lam_ok else "代码+近似"
        else:
            src = md.ai_source
        mons.append({"id": mid, "name": md.name, "intent": src, "moves": len(moves), "notes": notes,
                     "lambdas": n_lam, "lambdas_ok": n_lam_ok, "pattern": _pattern_kind(md)})
    out["monsters"] = mons
    out["monster_summary"] = Counter(m["intent"] for m in mons)
    # ---- 遭遇
    rows = []
    for e in encs:
        ci = EN.composition_info(e) or {}
        ids = EN.possible_monsters(e)
        status = "可模拟"
        why = ""
        if any(i not in db["monsters"] for i in ids):
            status, why = "缺失", "组成里有 spire-codex 未收录的怪物"
        elif any(db["monsters"][i].hp_missing for i in ids):
            status, why = "缺失", "有怪物没有血量数据"
        elif any(m["intent"] == "代码+近似" for m in mons if m["id"] in ids):
            status = "可模拟（含近似）"
        rows.append({"id": e["id"], "name": e["zh_name"], "act": e["act"][:5], "room": e["room_type"], "weak": bool(e.get("is_weak")),
                     "composition": ci.get("source", "数据（去重列表）"), "status": status, "why": why})
    out["encounters"] = rows
    out["encounter_summary"] = Counter(r["status"] for r in rows)
    # ---- 意图（招式级）
    tot = sum(m["moves"] for m in mons)
    out["intent_moves"] = tot
    out["lambdas"] = (sum(m.get("lambdas", 0) for m in mons), sum(m.get("lambdas_ok", 0) for m in mons))
    # ---- 遗物/药水/能力
    relics = codex_index("relics")
    pot = codex_index("potions")
    pw = codex_index("powers")
    starters = [r for r in relics.values() if r.get("rarity_key") == "Starter" or r.get("rarity") == "初始遗物"]
    out["relics"] = {"total": len(relics), "implemented": sorted(k for k in relics if k in RELIC_TYPES),
                     "starter_total": len(starters), "starter_impl": sorted(r["id"] for r in starters if r["id"] in RELIC_TYPES),
                     "starter_all": sorted(r["id"] for r in starters),
                     "mod_only": sorted(k for k in RELIC_TYPES if k not in relics)}
    out["potions"] = {"total": len(pot), "implemented": sorted(k for k in pot if k in POTION_DEFS)}
    enemy_used = set()
    for mid in used:
        md = db["monsters"].get(mid)
        if md:
            enemy_used.update(pid for mv in md.moves.values() for pid, _, _ in mv.powers)
            enemy_used.update(pid for pid, _ in md.innate)
    out["powers"] = {"total": len(pw), "implemented": sorted(k for k in pw if k in POWER_TYPES),
                     "enemy_used": sorted(enemy_used), "enemy_used_impl": sorted(k for k in enemy_used if k in POWER_TYPES),
                     "mod_only": sorted(k for k in POWER_TYPES if k not in pw)}
    return out


def coverage_md(cov):
    """覆盖率 → Markdown（报告用）。"""
    L = []
    A = L.append
    ms = cov["monster_summary"]
    n = len(cov["monsters"])
    A(f"- **敌人（第1-3幕遭遇里出现的 {n} 种）**：意图逻辑来自反编译代码且无近似 {_pct(ms.get('代码', 0), n)}；"
      f"代码 + 近似（召唤/未实现能力/缺血量）{_pct(ms.get('代码+近似', 0), n)}；只有 spire-codex 数据 {ms.get('数据', 0)}；缺失 {ms.get('缺失', 0)}。招式共 {cov['intent_moves']} 个；状态机里的条件/权重表达式 {_pct(cov['lambdas'][1], cov['lambdas'][0])} 可直接求值。")
    es = cov["encounter_summary"]
    ne = len(cov["encounters"])
    A(f"- **遭遇（第1-3幕 {ne} 个）**：可模拟 {_pct(es.get('可模拟', 0), ne)}；可模拟但含近似 {_pct(es.get('可模拟（含近似）', 0), ne)}；缺失 {_pct(es.get('缺失', 0), ne)}。")
    r = cov["relics"]
    A(f"- **遗物**：spire-codex 共 {r['total']} 个，已实现 {_pct(len(r['implemented']), r['total'])}；初始遗物 {_pct(len(r['starter_impl']), r['starter_total'])}"
      f"（未实现：{', '.join(x for x in r['starter_all'] if x not in r['starter_impl']) or '无'}）；mod 自带遗物 {len(r['mod_only'])} 个。")
    p = cov["potions"]
    A(f"- **药水**：共 {p['total']} 种，已实现 {_pct(len(p['implemented']), p['total'])}（v0.1 实验里的卡组都不带药水，接口和 AI 用药逻辑已就绪）。")
    w = cov["powers"]
    A(f"- **能力**：spire-codex 共 {w['total']} 个，已实现 {_pct(len(w['implemented']), w['total'])}；其中敌人会用到的 {_pct(len(w['enemy_used_impl']), len(w['enemy_used']))}；mod 自带能力 {len(w['mod_only'])} 个。")
    return "\n".join(L)


def write_csvs(cov, out_dir):
    import csv
    with open(os.path.join(out_dir, "coverage_monsters.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["怪物ID", "中文名", "意图逻辑来源", "出招结构", "招式数", "说明"])
        for m in cov["monsters"]:
            w.writerow([m["id"], m["name"], m["intent"], m.get("pattern", ""), m["moves"], "；".join(m["notes"])])
    with open(os.path.join(out_dir, "coverage_encounters.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["遭遇ID", "中文名", "幕", "房间", "弱怪", "组成来源", "状态", "原因"])
        for r in cov["encounters"]:
            w.writerow([r["id"], r["name"], r["act"], r["room"], r["weak"], r["composition"], r["status"], r["why"]])


def monsters_table_md(cov):
    L = ["| 怪物 | 意图逻辑来源 | 出招结构 | 招式数 | 近似/说明 |", "|-|-|-|-|-|"]
    for m in sorted(cov["monsters"], key=lambda x: (x["intent"] != "代码+近似", x["id"])):
        L.append(f"| {m['name']}（{m['id']}） | {m['intent']} | {m.get('pattern', '')} | {m['moves']} | {'；'.join(m['notes']) or '—'} |")
    return "\n".join(L)
