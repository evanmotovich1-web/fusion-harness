Build `roman.py` in this repository (Python 3, standard library only).

Contract (exact):
- `to_roman(n: int) -> str` for 1..3999 inclusive, canonical subtractive form (4 = "IV", 1994 = "MCMXCIV").
  Anything else (0, negatives, >3999, non-int, bool) raises `ValueError`.
- `from_roman(s: str) -> int` accepts only canonical uppercase numerals for 1..3999 and raises `ValueError`
  for anything else: empty, lowercase, invalid symbols, non-canonical forms such as "IIII", "VV", "IC", "MMMM".
- For every n in 1..3999: `from_roman(to_roman(n)) == n`.

Also add your own tests. No network, no installs.
