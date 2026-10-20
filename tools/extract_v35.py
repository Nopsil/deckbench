"""从 Claude娘 v3.5 设计文档（只读）抽取卡牌/遗物表，写成 mods/claude_v35/design_v35.json。
用法：python3 tools/extract_v35.py <path/to/Claude娘_卡牌设计.md>"""
import json
import re
import sys

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "mods/claude_v35/design_v35.json"
sec, rows = None, {"cards": [], "relics": [], "starter": []}
RAR = {"基础": "Basic", "普通": "Common", "罕见": "Uncommon", "稀有": "Rare"}
for line in open(src, encoding="utf-8"):
    m = re.match(r"## 卡牌：(\S+?)（", line)
    if m:
        sec = ("card", m.group(1)); continue
    if line.startswith("## 遗物"):
        sec = ("relic", None); continue
    if line.startswith("## 初始卡组"):
        sec = ("starter", None); continue
    if line.startswith("## "):
        sec = None; continue
    if not sec or not line.startswith("|") or line.startswith("|-") or line.startswith("|名称") or line.startswith("|分类"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if sec[0] == "card" and len(cells) >= 7:
        name, typ, cost, eff, upg, arch, note = cells[:7]
        if sec[1] == "基础" and any(r["name"] == name and r["rarity"] == "Basic" for r in rows["cards"]):
            continue
        rows["cards"].append({"name": name, "rarity": RAR.get(sec[1], sec[1]), "type": typ, "cost": cost,
                              "effect": eff, "upgrade": upg, "archetype": arch, "note": note})
    elif sec[0] in ("relic", "starter"):
        rows["relics" if sec[0] == "relic" else "starter"].append(cells)
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from collections import Counter
print(len(rows["cards"]), Counter(r["rarity"] for r in rows["cards"]), "relic rows", len(rows["relics"]))
