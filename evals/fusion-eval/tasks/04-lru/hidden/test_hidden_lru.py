import pytest

from lru import LRUCache


def test_capacity_validation():
    for bad in (0, -1):
        with pytest.raises(ValueError):
            LRUCache(bad)


def test_eviction_order_and_get_refreshes():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert "b" not in cache
    assert cache.keys() == ["a", "c"]


def test_update_refreshes_and_does_not_grow():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    assert len(cache) == 2
    cache.put("c", 3)
    assert cache.get("a") == 10
    assert cache.get("b") is None


def test_default_and_contains_does_not_touch_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("zzz", "dflt") == "dflt"
    assert "a" in cache
    cache.put("c", 3)
    assert cache.keys() == ["b", "c"]


def test_capacity_one():
    cache = LRUCache(1)
    cache.put(1, "x")
    cache.put(2, "y")
    assert cache.keys() == [2]
    assert len(cache) == 1
