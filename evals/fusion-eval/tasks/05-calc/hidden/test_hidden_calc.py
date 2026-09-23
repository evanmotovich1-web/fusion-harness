import re

import pytest

from _isolated import call, raises, source

VALID = ["2*(3+4)", "1 + 2 * 3", "(1 + 2) * 3", "7 / 2", "2/4", "-2**2", "2**3**2", "-(3 - 5) * 2", "+4", "10 - 4 - 3", "2 ** -1", "3.5 * 2", ".5 + 1", "((2))", "  8   /  4  ", "- - 3", "2*-3"]


@pytest.mark.parametrize("expr", VALID)
def test_matches_python(expr):
    expected = eval(expr)  # the oracle may use eval (in the trusted parent); the solution may not
    kind, got, type_name = call("calc", "evaluate", expr)
    assert kind == "ok"
    assert got == pytest.approx(expected)
    assert type_name == type(expected).__name__


def test_division_by_zero():
    assert raises("calc", "evaluate", "1/0") == "ZeroDivisionError"
    assert raises("calc", "evaluate", "5 / (2 - 2)") == "ZeroDivisionError"


@pytest.mark.parametrize("bad", ["", "   ", "(1+2", "1+2)", "1 +", "* 3", "2 3", "abc", "1 & 2", "__import__('os')"])
def test_malformed_raises_value_error(bad):
    assert raises("calc", "evaluate", bad) == "ValueError"


def test_real_parser_not_eval():
    text = source("calc.py")
    # Built-ins only: re.compile(...) or a method named .evaluate() are fine.
    assert not re.search(r"(?<![\w.])(eval|exec|compile|__import__)\s*\(", text)
    assert not re.search(r"^\s*(import\s+ast\b|from\s+ast\s+import)", text, re.M)
