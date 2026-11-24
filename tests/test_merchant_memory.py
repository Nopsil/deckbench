"""商店库存表：事件换上的库存和进店建的库存是同一张表。不需要游戏文件。"""
import pytest

from sts2sim.engine.merchant_memory import MerchantMemory


def test_set_inventory_is_what_get_returns():
    memory = MerchantMemory()
    player = object()
    inventory = object()
    memory.set(player, inventory)
    assert memory.get(player) is inventory


def test_a_later_set_replaces_the_shop_inventory():
    memory = MerchantMemory()
    player = object()
    first, second = object(), object()
    memory.set(player, first)
    memory.set(player, second)
    assert memory.get(player) is second


def test_clear_drops_the_inventory():
    memory = MerchantMemory()
    player = object()
    memory.set(player, object())
    memory.clear()
    with pytest.raises(KeyError):
        memory.get(player)
