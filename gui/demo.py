"""载入仓库里打好的示例结果包。

包是 ``tools/make_demo_bundle.py`` 用现有战斗工人跑出来的，走和
``POST /api/bundles/import`` 相同的 ``import_zip_bytes``。不执行包里的文件。
"""
from __future__ import annotations

import os
import sys

from sts2sim.bundle import MAX_UPLOAD, BundleError, import_zip_bytes

from . import paths

NAME = "sample.deckbench.zip"


class DemoError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def bundle_path():
    """开发目录、PyInstaller 包、以及打包后 ``sim/gui/demo`` 里的那一份。"""
    found = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        found.append(os.path.join(meipass, "demo", NAME))
    found.append(os.path.join(paths.APP_DIR, "demo", NAME))
    found.append(os.path.join(paths.SIM_ROOT, "gui", "demo", NAME))
    seen = set()
    for path in found:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and not os.path.islink(path):
            return path
    return ""


def load_builtin():
    """读内置 zip，校验清单和哈希后写成测试目录。"""
    path = bundle_path()
    if not path:
        raise DemoError("missing")
    try:
        size = os.path.getsize(path)
    except OSError as err:
        raise DemoError("missing") from err
    if size > MAX_UPLOAD:
        raise BundleError("too_big")
    with open(path, "rb") as handle:
        data = handle.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise BundleError("too_big")
    return import_zip_bytes(data, filename=os.path.basename(path))
