"""把一份已经装好的 StS2 mod（清单 JSON + DLL）读成 DeckBench 的 YAML。

不执行 DLL，也不复制游戏文件。用法和限制见 docs/DLL_MODS.md。

  python tools/import_dll_mod.py --list
  python tools/import_dll_mod.py "C:/path/to/Slay the Spire 2/mods/MyMod" --out mods/my_mod
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sts2sim.dllmod.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
