"""让 sts2sim.modloader 也能从界面的「用户 mod」目录加载 mod（不改模拟器源码，运行时打补丁）。"""
import os


def apply(user_mods_dir=None):
    user_mods_dir = user_mods_dir or os.environ.get("STS2SIM_USER_MODS")
    if not user_mods_dir:
        return
    from sts2sim import modloader as ML
    if getattr(ML.ModSet, "_gui_patched", False):
        return
    orig = ML.ModSet._load_mod
    builtin = ML.MODS_DIR

    def _load_mod(self, name):
        if not os.path.isdir(os.path.join(builtin, name)) and os.path.isdir(os.path.join(user_mods_dir, name)):
            ML.MODS_DIR = user_mods_dir
            try:
                return orig(self, name)
            finally:
                ML.MODS_DIR = builtin
        return orig(self, name)

    ML.ModSet._load_mod = _load_mod
    ML.ModSet._gui_patched = True
