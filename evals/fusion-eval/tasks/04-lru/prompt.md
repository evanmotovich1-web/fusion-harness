Build `lru.py` in this repository (Python 3, standard library only).

Contract (exact):
- `class LRUCache(capacity: int)`; a capacity below 1 raises `ValueError`.
- `get(key, default=None)` returns the value (marking the key most recently used) or `default` if absent.
- `put(key, value)` inserts or updates (an update also marks it most recently used). When inserting a new key
  beyond capacity, evict the least recently used key.
- `len(cache)` is the number of stored keys; `key in cache` works and does **not** change recency.
- `keys()` returns a list ordered from least to most recently used.

Also add your own tests. No network, no installs.
