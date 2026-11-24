"""事件页停住时不要反复点同一个已经执行过的选项。不需要游戏文件。"""
from types import SimpleNamespace

from sts2sim.engine.event_flow import same_chosen_page


def test_a_page_of_already_chosen_options_is_stuck():
    option = SimpleNamespace(WasChosen=True)
    assert same_chosen_page([id(option)], [option])


def test_a_new_page_is_not_stuck():
    first = SimpleNamespace(WasChosen=True)
    second = SimpleNamespace(WasChosen=False)
    assert not same_chosen_page([id(first)], [second])


def test_an_unchosen_option_on_the_same_page_is_not_stuck():
    chosen = SimpleNamespace(WasChosen=True)
    other = SimpleNamespace(WasChosen=False)
    assert not same_chosen_page([id(chosen), id(other)], [chosen, other])
