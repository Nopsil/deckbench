"""把作者自己的 StS2 mod DLL 读成 DeckBench 已经会跑的 YAML mod。

不执行 DLL，不复制游戏文件。能反编译时，把直线效果翻成 YAML；否则只列出类型。
说明见 docs/DLL_MODS.md。
"""
from .package import DllModError, import_installed, import_path, list_installed

__all__ = ["DllModError", "import_installed", "import_path", "list_installed"]
