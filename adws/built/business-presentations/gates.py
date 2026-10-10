"""Requirement gates. A pass needs a nonempty result for the named gate."""

def gate_req_1_gate(output):
    if not isinstance(output, dict):
        return False, "req_1_gate: output must be an object"
    if output.get("gate") != "req_1_gate":
        return False, "req_1_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "req_1_gate: result must be a nonempty string"
    return True, "req_1_gate passed"

def gate_req_2_gate(output):
    if not isinstance(output, dict):
        return False, "req_2_gate: output must be an object"
    if output.get("gate") != "req_2_gate":
        return False, "req_2_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "req_2_gate: result must be a nonempty string"
    return True, "req_2_gate passed"

def gate_req_3_gate(output):
    if not isinstance(output, dict):
        return False, "req_3_gate: output must be an object"
    if output.get("gate") != "req_3_gate":
        return False, "req_3_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "req_3_gate: result must be a nonempty string"
    return True, "req_3_gate passed"

GATES = {
    "req_1_gate": gate_req_1_gate,
    "req_2_gate": gate_req_2_gate,
    "req_3_gate": gate_req_3_gate,
}

def check(name, output):
    fn = GATES.get(name)
    if fn is None:
        return False, f"unknown gate {name}"
    return fn(output)
