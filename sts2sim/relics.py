"""遗物基类与注册表。mod 在 hooks.py 里用 @register_relic 定义遗物类。"""
import copy

RELIC_TYPES = {}


def register_relic(cls):
    RELIC_TYPES[cls.id] = cls
    return cls


class Relic:
    id = "RELIC"
    name = "遗物"

    def __init__(self):
        self.data = {}

    def clone(self):
        r = copy.copy(self)
        r.data = dict(self.data)
        return r

    def src(self):
        return ("relic", self)


def make_relic(rid):
    if rid not in RELIC_TYPES:
        raise KeyError(f"未注册的遗物 {rid}（请在 mod 的 hooks.py 里用 @register_relic 实现）")
    return RELIC_TYPES[rid]()
