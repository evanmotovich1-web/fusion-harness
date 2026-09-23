from _isolated import _child, raises, value


def test_merge_overlap_touch_and_order():
    assert value("intervals", "merge", [(8, 10), (1, 3), (2, 4), (4, 6)]) == [(1, 6), (8, 10)]
    assert value("intervals", "merge", [(1, 3), (3, 5)]) == [(1, 5)]
    assert value("intervals", "merge", [(1, 10), (2, 3)]) == [(1, 10)]
    assert value("intervals", "merge", []) == []


def test_merge_does_not_mutate_and_returns_tuples():
    out = _child("""
import intervals
data = [(5, 6), (1, 2)]
result = intervals.merge(data)
_emit({"data": _enc(data), "result": _enc(result), "all_tuples": all(isinstance(x, tuple) for x in result)})
""")
    assert out["data"] == [{"__tuple__": [5, 6]}, {"__tuple__": [1, 2]}]
    assert out["all_tuples"] is True


def test_merge_rejects_reversed():
    assert raises("intervals", "merge", [(3, 1)]) == "ValueError"


def test_free_slots_basic_and_clipping():
    assert value("intervals", "free_slots", [(10, 12), (13, 14)], 9, 17) == [(9, 10), (12, 13), (14, 17)]
    assert value("intervals", "free_slots", [(7, 10), (16, 20)], 9, 17) == [(10, 16)]
    assert value("intervals", "free_slots", [], 9, 17) == [(9, 17)]
    assert value("intervals", "free_slots", [(8, 18)], 9, 17) == []


def test_free_slots_omits_zero_length_and_merges_first():
    assert value("intervals", "free_slots", [(9, 11), (11, 12), (12, 17)], 9, 17) == []
    assert value("intervals", "free_slots", [(10, 12), (11, 13)], 9, 17) == [(9, 10), (13, 17)]


def test_free_slots_rejects_bad_day():
    assert raises("intervals", "free_slots", [], 17, 9) == "ValueError"
