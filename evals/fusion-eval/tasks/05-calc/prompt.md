Build `calc.py` in this repository (Python 3, standard library only).

Contract (exact):
- `evaluate(expr: str)` evaluates arithmetic with integers and decimals, `+ - * / **`, parentheses,
  unary minus/plus, and arbitrary whitespace. The result must equal what Python itself gives for the same
  valid expression: `/` is true division, `**` is right-associative and binds tighter than unary minus
  (`-2**2 == -4`, `2**3**2 == 512`), and integer-only expressions return `int` ("2*(3+4)" -> 14).
- Division by zero raises `ZeroDivisionError`. Any malformed input (empty, unbalanced parentheses,
  dangling operators, unknown characters or names) raises `ValueError`.
- You must write a real parser: do not use `eval`, `exec`, `compile`, or the `ast` module.

Also add your own tests. No network, no installs.
