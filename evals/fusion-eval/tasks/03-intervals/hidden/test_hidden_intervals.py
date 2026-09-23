import pytest

from intervals import free_slots, merge


def test_merge_overlap_touch_and_order():
    assert merge([(8, 10), (1, 3), (2, 4), (4, 6)]) == [(1, 6), (8, 10)]
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]
    assert merge([(1, 10), (2, 3)]) == [(1, 10)]
    assert merge([]) == []


def test_merge_does_not_mutate_and_returns_tuples():
    data = [(5, 6), (1, 2)]
    result = merge(data)
    assert data == [(5, 6), (1, 2)]
    assert all(isinstance(item, tuple) for item in result)


def test_merge_rejects_reversed():
    with pytest.raises(ValueError):
        merge([(3, 1)])


def test_free_slots_basic_and_clipping():
    assert free_slots([(10, 12), (13, 14)], 9, 17) == [(9, 10), (12, 13), (14, 17)]
    assert free_slots([(7, 10), (16, 20)], 9, 17) == [(10, 16)]
    assert free_slots([], 9, 17) == [(9, 17)]
    assert free_slots([(8, 18)], 9, 17) == []


def test_free_slots_omits_zero_length_and_merges_first():
    assert free_slots([(9, 11), (11, 12), (12, 17)], 9, 17) == []
    assert free_slots([(10, 12), (11, 13)], 9, 17) == [(9, 10), (13, 17)]


def test_free_slots_rejects_bad_day():
    with pytest.raises(ValueError):
        free_slots([], 17, 9)
