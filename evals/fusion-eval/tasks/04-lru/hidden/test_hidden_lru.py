from _isolated import script


def test_capacity_validation():
    for bad in (0, -1):
        assert script("lru", "LRUCache", [bad], []) == ("ctor_raises", "ValueError")


def test_eviction_order_and_get_refreshes():
    r = script("lru", "LRUCache", [2], [["put", ["a", 1]], ["put", ["b", 2]], ["get", ["a"]], ["put", ["c", 3]], ["__contains__", ["b"]], ["keys", []]])
    assert r[2] == ("ok", 1)
    assert r[4] == ("ok", False)
    assert r[5] == ("ok", ["a", "c"])


def test_update_refreshes_and_does_not_grow():
    r = script("lru", "LRUCache", [2], [["put", ["a", 1]], ["put", ["b", 2]], ["put", ["a", 10]], ["__len__", []], ["put", ["c", 3]], ["get", ["a"]], ["get", ["b"]]])
    assert r[3] == ("ok", 2)
    assert r[5] == ("ok", 10)
    assert r[6] == ("ok", None)


def test_default_and_contains_does_not_touch_recency():
    r = script("lru", "LRUCache", [2], [["put", ["a", 1]], ["put", ["b", 2]], ["get", ["zzz", "dflt"]], ["__contains__", ["a"]], ["put", ["c", 3]], ["keys", []]])
    assert r[2] == ("ok", "dflt")
    assert r[3] == ("ok", True)
    assert r[5] == ("ok", ["b", "c"])


def test_capacity_one():
    r = script("lru", "LRUCache", [1], [["put", [1, "x"]], ["put", [2, "y"]], ["keys", []], ["__len__", []]])
    assert r[2] == ("ok", [2])
    assert r[3] == ("ok", 1)
