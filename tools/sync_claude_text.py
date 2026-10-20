"""从 Claude娘 设计数据（v34_data.py）同步卡面文字，并核对类型/稀有度/费用。

用法：python tools/sync_claude_text.py /path/to/claude-mod/v34/scripts
输出：mods/claude_v34/cards.yaml（cards_src.yaml + text/text_up），tests/fixtures/claude_v34_design.json（测试用快照）。
不会修改设计目录里的任何文件。
"""
import json
import os
import sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(src):
    sys.dont_write_bytecode = True
    sys.path.insert(0, src)
    cwd = os.getcwd()
    os.chdir(src)
    import v34_data as d  # noqa
    os.chdir(cwd)
    design = {}
    for r in d.cards:
        design.setdefault(r[0], {"name": r[0], "rarity": r[1], "type": r[2], "cost": r[3], "text": r[4], "text_up": r[5], "archetype": r[6]})
    for m in d.mech:
        if m[0].startswith("代码块"):
            design["代码块"] = {"name": "代码块", "rarity": "生成", "type": "攻击", "cost": 0, "text": m[1], "text_up": "", "archetype": ""}
        if m[0].startswith("请稍后再试"):
            design["请稍后再试"] = {"name": "请稍后再试", "rarity": "状态", "type": "状态", "cost": None, "text": m[1], "text_up": "", "archetype": ""}
    relics = [{"name": r[0], "rarity": r[1], "archetype": r[2], "text": r[3]} for r in d.relics]
    src_cards = yaml.safe_load(open(os.path.join(ROOT, "mods/claude_v34/cards_src.yaml"), encoding="utf-8"))
    problems = []
    for c in src_cards:
        x = design.get(c["name"])
        if x is None:
            problems.append(f"设计里没有 {c['name']}")
            continue
        c["text"] = x["text"]
        c["text_up"] = x["text_up"]
        c["archetype"] = x["archetype"]
        if x["type"] != c["type"]:
            problems.append(f"{c['name']} 类型 {c['type']} ≠ 设计 {x['type']}")
        if x["rarity"] != c["rarity"]:
            problems.append(f"{c['name']} 稀有度 {c['rarity']} ≠ 设计 {x['rarity']}")
        if x["cost"] != c.get("cost"):
            problems.append(f"{c['name']} 费用 {c.get('cost')} ≠ 设计 {x['cost']}")
    names = {c["name"] for c in src_cards}
    for n in design:
        if n not in names and n not in ("打击", "防御"):
            problems.append(f"卡表缺 {n}")
    with open(os.path.join(ROOT, "mods/claude_v34/cards.yaml"), "w", encoding="utf-8") as f:
        f.write("# 由 tools/sync_claude_text.py 生成：效果来自 cards_src.yaml，text/text_up 来自设计 v3.4。改效果请改 cards_src.yaml 后重新同步。\n")
        yaml.safe_dump(src_cards, f, allow_unicode=True, sort_keys=False, width=200)
    json.dump({"cards": list(design.values()), "relics": relics, "n_rows": len(d.cards)},
              open(os.path.join(ROOT, "tests/fixtures/claude_v34_design.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"同步 {len(src_cards)} 张卡；问题 {len(problems)} 条")
    for p in problems:
        print(" -", p)
    return problems


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: sync_claude_text.py <claude-mod v34/scripts dir>"))
