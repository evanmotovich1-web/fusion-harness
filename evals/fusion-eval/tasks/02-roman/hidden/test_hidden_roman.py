import pytest

from _isolated import _child, raises, value


@pytest.mark.parametrize("n,s", [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (90, "XC"), (400, "CD"), (1994, "MCMXCIV"), (2024, "MMXXIV"), (3999, "MMMCMXCIX")])
def test_known_values(n, s):
    assert value("roman", "to_roman", n) == s
    assert value("roman", "from_roman", s) == n


def test_round_trip_all():
    # One child for all 3999 round trips; the parent checks the returned numbers.
    out = _child("""
import roman
_emit([roman.from_roman(roman.to_roman(n)) for n in range(1, 4000)])
""")
    assert out == list(range(1, 4000))


@pytest.mark.parametrize("bad", [0, -1, 4000, 2.5, "10", True])
def test_to_roman_rejects(bad):
    assert raises("roman", "to_roman", bad) == "ValueError"


@pytest.mark.parametrize("bad", ["", "iv", "IIII", "VV", "IC", "MMMM", "ABC", "XM", "VX"])
def test_from_roman_rejects(bad):
    assert raises("roman", "from_roman", bad) == "ValueError"
