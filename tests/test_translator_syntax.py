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


def test_catch_binds_the_exception_name():
    got = _stmt("try { Go(); } catch (Exception ex) { Use(ex.Message); throw; }")
    assert "except Exception as ex:" in got
    assert "ex.Message" in got
    assert "self.ex" not in got


def test_typed_catches_keep_order_and_reraise_the_rest():
    got = _stmt(
        "try { Go(); } "
        "catch (OperationCanceledException ex) { throw; } "
        "catch (Exception ex2) { Save(ex2); throw; }"
    )
    assert "except Exception as _caught:" in got
    assert got.index("_isinst(_caught, OperationCanceledException)") < got.index("ex2 = _caught")
    assert "elif True:" in got
    assert "else:" not in got
    assert got.strip().endswith("raise")


def test_specific_catch_does_not_swallow_other_exceptions():
    got = _stmt("try { Wait(); } catch (TimeoutException) { return; }")
    assert "_isinst(_caught, TimeoutException)" in got
    assert "else:" in got
    assert got.strip().endswith("raise")


def test_bare_catch_does_not_invent_a_name():
    got = _stmt("try { Go(); } catch { return 1; }")
    assert "except Exception:" in got
    assert " as " not in got
