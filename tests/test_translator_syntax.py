"""转译器要能读 v0.113 反编译里新出现的语法。夹具是我们写的短例子，不是游戏源码。"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from cs2py_core import Ctx, Parser, lex


def _stmt(code):
    p = Parser(lex(textwrap.dedent(code).strip() + "\n"), Ctx(set(), set()))
    lines = p.statement()
    assert p.peek().k == "eof", p.peek()
    return "\n".join(lines)


def test_record_with_expression():
    got = _stmt("object r = src with { A = 1, B = 2 };")
    assert "_with(src, A=1, B=2)" in got


def test_property_pattern_binds_the_name():
    got = _stmt("if (!(src is Card { Type: 1 } card)) return n;")
    assert "_isinst" in got
    assert "card" in got
    assert ".Type" in got


def test_group_into_continues_the_query():
    got = _stmt("return (from x in xs where x > 0 group x by x into g orderby g.Key select g);")
    assert "GroupBy" in got
    assert "OrderBy" in got
    assert "into" not in got


def test_parameterless_delegate_accepts_the_argument_it_is_called_with():
    got = _stmt("X.M(delegate { });")
    assert "*_a" in got


def test_ref_local_is_the_value_itself():
    got = _stmt("int x = ((int)(ref val));")
    assert "val" in got
    assert "ref" not in got
