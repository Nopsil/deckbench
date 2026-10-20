"""把 spire-codex 里还没实现的遗物 / 药水 / 能力批量导出成 YAML 桩，供逐个补效果。

用法：python tools/import_codex.py            → data/stubs/{relics,potions,powers}_todo.yaml
每个桩带官方中文名、描述、稀有度/池子，effects 留空；实现后挪进 mod 的 potions.yaml，
或在 hooks.py 用 @register_relic / @register_power 写成类（名字描述可用 catalog.codex_index 自动补全）。
"""
import os
import sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sts2sim.modloader import ModSet  # noqa: E402
from sts2sim.catalog import codex_index, coverage  # noqa: E402


def main():
    M = ModSet(["vanilla"])
    cov = coverage(M)
    os.makedirs(os.path.join(ROOT, "data", "stubs"), exist_ok=True)
    for kind, impl in (("relics", cov["relics"]["implemented"]), ("potions", cov["potions"]["implemented"]),
                       ("powers", cov["powers"]["implemented"])):
        idx = codex_index(kind)
        todo = []
        for k, v in idx.items():
            if k in impl:
                continue
            todo.append({"id": k, "name": v.get("name"), "rarity": v.get("rarity") or v.get("type"),
                         "pool": v.get("pool"), "text": (v.get("description") or "").replace("\n", " "), "effects": []})
        path = os.path.join(ROOT, "data", "stubs", f"{kind}_todo.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 未实现的 {kind}：{len(todo)} 个（由 tools/import_codex.py 生成）\n")
            yaml.safe_dump(todo, f, allow_unicode=True, sort_keys=False, width=200)
        print(kind, "未实现", len(todo), "→", path)


if __name__ == "__main__":
    main()
