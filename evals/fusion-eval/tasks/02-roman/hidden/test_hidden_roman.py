import pytest

from roman import from_roman, to_roman


@pytest.mark.parametrize("n,s", [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (90, "XC"), (400, "CD"), (1994, "MCMXCIV"), (2024, "MMXXIV"), (3999, "MMMCMXCIX")])
def test_known_values(n, s):
    assert to_roman(n) == s
    assert from_roman(s) == n


def test_round_trip_all():
    assert all(from_roman(to_roman(n)) == n for n in range(1, 4000))


@pytest.mark.parametrize("bad", [0, -1, 4000, 2.5, "10", True])
def test_to_roman_rejects(bad):
    with pytest.raises(ValueError):
        to_roman(bad)


@pytest.mark.parametrize("bad", ["", "iv", "IIII", "VV", "IC", "MMMM", "ABC", "XM", "VX"])
def test_from_roman_rejects(bad):
    with pytest.raises(ValueError):
        from_roman(bad)
