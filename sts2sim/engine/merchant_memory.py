"""单机商店库存表。不依赖游戏程序集，事件和进店走同一张表。"""


class MerchantMemory:
    def __init__(self):
        self._inv = {}

    def set(self, player, inventory):
        self._inv[id(player)] = inventory

    def get(self, player):
        return self._inv[id(player)]

    def clear(self):
        self._inv.clear()
