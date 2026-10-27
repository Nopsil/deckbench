"""命令行：python -m sts2sim.dllmod <mod 目录|zip|dll> [--out 文件夹]

读作者自己的 mod DLL，写成 DeckBench 的 YAML。不执行 DLL，不复制游戏文件。
"""
import argparse
import json
import os
import sys

from .package import DllModError, import_path, list_installed


def main(argv=None):
    p = argparse.ArgumentParser(description="Import an installed StS2 mod DLL into a DeckBench YAML mod")
    p.add_argument("path", nargs="?", help="mod folder, zip, or DLL")
    p.add_argument("--out", help="write the YAML mod into this folder")
    p.add_argument("--no-decompile", action="store_true", help="only list types from metadata")
    p.add_argument("--list", action="store_true", help="list mods in the local game install")
    p.add_argument("--json", action="store_true", help="print the machine-readable report")
    p.add_argument("--lang", default=None, help="preferred localization language code (eng, zhs, jpn, kor)")
    a = p.parse_args(argv)
    if a.list:
        rows = list_installed()
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        elif not rows:
            print("没有在本机游戏的 mods/ 里找到带清单的 mod。\nNo manifest mods found under the local game's mods/ folder.")
        else:
            for r in rows:
                print(f"{r['id']}\t{r.get('name') or ''}\t{r.get('version') or ''}")
        return 0
    if not a.path:
        p.error("path is required unless --list")
    try:
        mod, report = import_path(a.path, decompile=not a.no_decompile, lang=a.lang)
    except DllModError as e:
        print(e.key, e.params or "", file=sys.stderr)
        return 2
    if a.out:
        from ..modfmt.schema import dump_mod_dir
        os.makedirs(a.out, exist_ok=True)
        dump_mod_dir(mod, a.out)
        print(a.out)
    if a.json:
        print(json.dumps({"name": mod.get("name"), "title": mod.get("title"),
                          "cards": [c.get("id") for c in mod.get("cards") or []],
                          "report": report}, ensure_ascii=False, indent=1))
    else:
        _print_human(mod, report)
    return 0


def _print_human(mod, report):
    print(f"{mod.get('title')} ({mod.get('name')})  [{report.get('mode')}]")
    print(f"cards {len(mod.get('cards') or [])}  powers {len(mod.get('powers') or [])}  relics {len(mod.get('relics') or [])}")
    for n in report.get("notes") or []:
        print(f"- {n.get('where')}: {n.get('en')}")
    print("---")
    for lim in report.get("limitations") or []:
        print(lim.get("en"))


if __name__ == "__main__":
    sys.exit(main())
