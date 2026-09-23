Build `intervals.py` in this repository (Python 3, standard library only).

Contract (exact):
- `merge(intervals)` takes a list of `(start, end)` integer pairs and returns a new list of tuples,
  sorted by start, with overlapping **and touching** intervals merged: `[(1, 3), (3, 5)] -> [(1, 5)]`.
  Any pair with `start > end` raises `ValueError`. The input list must not be mutated. Empty input returns `[]`.
- `free_slots(busy, day_start, day_end)` returns the gaps inside `[day_start, day_end]` not covered by the
  merged busy intervals, as a sorted list of tuples. Busy intervals may extend outside the day (clip them).
  Zero-length gaps are omitted. `day_start > day_end` raises `ValueError`.

Also add your own tests. No network, no installs.
