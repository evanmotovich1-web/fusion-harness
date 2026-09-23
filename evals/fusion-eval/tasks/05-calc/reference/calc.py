import re

_TOKEN = re.compile(r"\s*(?:(\d+\.\d*|\.\d+|\d+)|(\*\*|[-+*/()]))")


def _tokens(expr):
    pos, out = 0, []
    expr = expr.rstrip()
    while pos < len(expr):
        match = _TOKEN.match(expr, pos)
        if not match:
            raise ValueError(f"unexpected input at {pos}: {expr[pos:]!r}")
        number, op = match.groups()
        out.append(("num", float(number) if "." in number else int(number)) if number else ("op", op))
        pos = match.end()
    return out


def evaluate(expr):
    if not isinstance(expr, str):
        raise ValueError("expression must be a string")
    tokens = _tokens(expr)
    if not tokens:
        raise ValueError("empty expression")
    index = 0

    def peek():
        return tokens[index] if index < len(tokens) else (None, None)

    def take():
        nonlocal index
        token = peek()
        index += 1
        return token

    def expression():
        value = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            right = term()
            value = value + right if op == "+" else value - right
        return value

    def term():
        value = unary()
        while peek() in (("op", "*"), ("op", "/")):
            op = take()[1]
            right = unary()
            value = value * right if op == "*" else value / right
        return value

    def unary():
        if peek() in (("op", "-"), ("op", "+")):
            op = take()[1]
            value = unary()
            return -value if op == "-" else +value
        return power()

    def power():
        base = atom()
        if peek() == ("op", "**"):
            take()
            return base ** unary()
        return base

    def atom():
        kind, value = take()
        if kind == "num":
            return value
        if (kind, value) == ("op", "("):
            inner = expression()
            if take() != ("op", ")"):
                raise ValueError("unbalanced parentheses")
            return inner
        raise ValueError(f"unexpected token {value!r}")

    result = expression()
    if index != len(tokens):
        raise ValueError(f"unexpected trailing input {peek()[1]!r}")
    return result
