"""YAML 数据 mod 的格式定义、读取与校验（不依赖游戏代码，图形界面 / 测试 / 整局引擎共用）。

整局引擎的注册在 sts2sim/engine/yamlmod.py；旧版 YAML 战斗模拟器仍用 sts2sim/modloader.py 读同一套文件。
"""
from .schema import (load_mod_dir, load_mod_files, validate, ModFormatError, OPS, TEMPLATES, TRIGGERS,  # noqa: F401
                     norm_rarity, norm_type, norm_target, norm_keyword, dump_mod_dir)
