"""Requirement gates. A pass needs a nonempty result for the named gate."""

def gate_greeting_nonempty(output):
    if not isinstance(output, dict):
        return False, "greeting_nonempty: output must be an object"
    if output.get("gate") != "greeting_nonempty":
        return False, "greeting_nonempty: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "greeting_nonempty: result must be a nonempty string"
    return True, "greeting_nonempty passed"

GATES = {
    "greeting_nonempty": gate_greeting_nonempty,
}

def check(name, output):
    fn = GATES.get(name)
    if fn is None:
        return False, f"unknown gate {name}"
    return fn(output)
