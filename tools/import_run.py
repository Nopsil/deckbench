"""只读查看一份《杀戮尖塔 2》存档或历史记录（种子、路线、选牌、遗物）。

和 `python -m sts2sim.saveimport` 是同一个入口。格式说明见 docs/SAVE_FORMAT.md。
不写回游戏文件。

Read-only view of a Slay the Spire 2 save or run history. Same as
`python -m sts2sim.saveimport`. See docs/SAVE_FORMAT.md.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sts2sim.saveimport import main

if __name__ == "__main__":
    raise SystemExit(main())
