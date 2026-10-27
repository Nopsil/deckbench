"""种子预览：不打完整的一局，打印地图、遭遇分布和开局奖励。

  python tools/seed_preview.py 7F3K9Q2ZB8MA --char Ironclad --asc 0
  python tools/seed_preview.py 7F3K9Q2ZB8MA --neow all --json out.json --lang en
  python tools/seed_preview.py 7F3K9Q2ZB8MA --json - --cache

需要你自己的游戏安装已经在本机生成过模拟数据（python -m sts2sim.gamedata setup）。
不模拟战斗。`--json` 写出稳定的 v1 文档（字段见 docs/SAVE_FORMAT.md）。
`--cache` 把同一份结果留在本机，按种子、角色、进阶、开局选项索引，不进仓库。
限制见输出末尾，说明见 docs/SAVE_FORMAT.md 的「种子预览」一节。
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from sts2sim.engine.seedpreview import CHARS, PreviewError, format_text, preview, public_document  # noqa: E402


def _emit_json(doc, fp):
    json.dump(public_document(doc), fp, ensure_ascii=False, indent=1)
    fp.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seed")
    ap.add_argument("--char", default="Ironclad", choices=CHARS)
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--neow", default="first", help="first（第一个没锁的）/ all / none / 选项序号")
    ap.add_argument("--json", metavar="FILE",
                    help="把稳定的预览 JSON（v1）写到文件；- 表示只把 JSON 打到标准输出")
    ap.add_argument("--cache", nargs="?", const="", default=None, metavar="DIR",
                    help="可选的本机缓存。按规范化种子、角色、进阶、neow 存结果。"
                         "不写目录时用 DECKBENCH_CACHE/seed-preview。不要把缓存提交进仓库。")
    ap.add_argument("--lang", default="zhs", choices=["zhs", "en", "ja", "ko"])
    a = ap.parse_args(argv)
    try:
        res = preview(a.seed, a.char, a.asc, neow=a.neow,
                      use_cache=a.cache is not None, cache_dir=a.cache or None)
    except PreviewError as e:
        from gui import i18n
        key = "prev.err." + e.code
        msg = i18n.t(key, a.lang, **e.params) if i18n.has(key, a.lang) else e.code
        print(msg, file=sys.stderr)
        return 2
    if a.json == "-":
        _emit_json(res, sys.stdout)
        return 0
    print(format_text(res, a.lang))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            _emit_json(res, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
