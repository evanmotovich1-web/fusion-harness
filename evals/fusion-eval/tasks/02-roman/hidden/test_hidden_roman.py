import pytest

from _isolated import _child, raises, value


@pytest.mark.parametrize("n,s", [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (90, "XC"), (400, "CD"), (1994, "MCMXCIV"), (2024, "MMXXIV"), (3999, "MMMCMXCIX")])
def test_known_values(n, s):
    assert value("roman", "to_roman", n) == s
    assert value("roman", "from_roman", s) == n


def _canonical(n):
    # Parent-side oracle: the expected numeral is computed here, never trusted from the child.
    out = []
    for v, s in [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def test_round_trip_all():
    # One child returns every numeral and every parse; the parent checks both against its own oracle.
    out = _child("""
import roman
numerals = [roman.to_roman(n) for n in range(1, 4000)]
_emit({"numerals": numerals, "parsed": [roman.from_roman(_canonical_numeral) for _canonical_numeral in numerals]})
""")
    assert out["numerals"] == [_canonical(n) for n in range(1, 4000)]
    assert out["parsed"] == list(range(1, 4000))


@pytest.mark.parametrize("bad", [0, -1, 4000, 2.5, "10", True])
def test_to_roman_rejects(bad):
    assert raises("roman", "to_roman", bad) == "ValueError"


@pytest.mark.parametrize("bad", ["", "iv", "IIII", "VV", "IC", "MMMM", "ABC", "XM", "VX"])
def test_from_roman_rejects(bad):
    assert raises("roman", "from_roman", bad) == "ValueError"
