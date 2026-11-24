"""从本机反编译和中英本地化导出旧版战斗目录。

    python tools/export_legacy_codex.py --src <Core> --loc-eng <dir> --loc-zhs <dir> --out <dir> --dll sts2.dll

``python -m sts2sim.gamedata setup`` 在找得到本地化时会做同一件事，写到缓存的 legacy-codex/。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sts2sim.legacycodex import main

if __name__ == "__main__":
    sys.exit(main())
