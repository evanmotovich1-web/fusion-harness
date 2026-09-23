Build `wordstats.py` in this repository (Python 3, standard library only).

Contract (exact):
- `count(text: str) -> dict` returns `{"lines": ..., "words": ..., "chars": ...}` where
  lines = `len(text.splitlines())`, words = `len(text.split())`, chars = `len(text)` (characters, not bytes).
- CLI: `python wordstats.py [path]` prints exactly three lines:
  `Lines: N`, `Words: N`, `Characters: N`. With no path it reads stdin.
  Files are read as UTF-8. A missing or unreadable path prints an error to stderr and exits with code 2.

Also add your own tests and a short README usage section. No network, no installs.
