import re
from pathlib import Path

import pytest

import calc
from calc import evaluate

VALID = ["2*(3+4)", "1 + 2 * 3", "(1 + 2) * 3", "7 / 2", "2/4", "-2**2", "2**3**2", "-(3 - 5) * 2", "+4", "10 - 4 - 3", "2 ** -1", "3.5 * 2", ".5 + 1", "((2))", "  8   /  4  ", "- - 3", "2*-3"]


@pytest.mark.parametrize("expr", VALID)
def test_matches_python(expr):
    expected = eval(expr)  # the oracle may use eval; the solution may not
    got = evaluate(expr)
    assert got == pytest.approx(expected)
    assert type(got) is type(expected)


def test_division_by_zero():
    with pytest.raises(ZeroDivisionError):
        evaluate("1/0")
    with pytest.raises(ZeroDivisionError):
        evaluate("5 / (2 - 2)")


@pytest.mark.parametrize("bad", ["", "   ", "(1+2", "1+2)", "1 +", "* 3", "2 3", "abc", "1 & 2", "__import__('os')"])
def test_malformed_raises_value_error(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


def test_real_parser_not_eval():
    source = Path(calc.__file__).read_text(encoding="utf-8")
    # Built-ins only: re.compile(...) or a method named .evaluate() are fine.
    assert not re.search(r"(?<![\w.])(eval|exec|compile|__import__)\s*\(", source)
    assert not re.search(r"^\s*(import\s+ast\b|from\s+ast\s+import)", source, re.M)
