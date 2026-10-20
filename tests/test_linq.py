"""LINQ 排序键比较（不需要生成的游戏代码）。"""
from sts2sim.rt.linq import Seq


class Id:
    def __init__(self, e):
        self.e = e

    def CompareTo(self, o):
        return (self.e > o.e) - (self.e < o.e)


def test_orderby_tuple_key_uses_compareto_on_ties():
    items = [(1, Id("STRIKE")), (0, Id("ZAP")), (1, Id("DEFEND")), (1, Id("BODYGUARD"))]
    out = Seq(items).OrderBy(lambda t: (t[0], t[1]))
    assert [t[1].e for t in out] == ["ZAP", "BODYGUARD", "DEFEND", "STRIKE"]


def test_orderby_none_first_and_stable():
    out = Seq([3, None, 1, 1]).OrderBy(lambda x: x)
    assert list(out) == [None, 1, 1, 3]
