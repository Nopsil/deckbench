"""种子预览的命令行入口（实现在 sts2sim.engine.seedpreview）。

不跑完整一局：打印第 1 幕地图、普通/精英/首领的出场顺序、开局就能确定的奖励。
名字按 --lang（默认跟界面语言）从你自己的游戏安装读，不随项目分发。

  python tools/seed_probe.py 7F3K9Q2ZB8MA --char Ironclad --asc 0
  python tools/seed_probe.py 7F3K9Q2ZB8MA --char Silent --neow none --lang en --json out.json

MCP 的地图文本也从这里的 render_map / _map 取。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from sts2sim.engine.seedpreview import main, read_map as _map, render_map  # noqa: E402

__all__ = ["main", "_map", "render_map"]

if __name__ == "__main__":
    raise SystemExit(main())
