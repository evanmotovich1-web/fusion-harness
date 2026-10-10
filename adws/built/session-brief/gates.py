"""Requirement gates. A pass needs a nonempty result for the named gate."""

def gate_workflow_identity_gate(output):
    if not isinstance(output, dict):
        return False, "workflow_identity_gate: output must be an object"
    if output.get("gate") != "workflow_identity_gate":
        return False, "workflow_identity_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "workflow_identity_gate: result must be a nonempty string"
    return True, "workflow_identity_gate passed"

def gate_db_session_rows_gate(output):
    if not isinstance(output, dict):
        return False, "db_session_rows_gate: output must be an object"
    if output.get("gate") != "db_session_rows_gate":
        return False, "db_session_rows_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "db_session_rows_gate: result must be a nonempty string"
    return True, "db_session_rows_gate passed"

def gate_brief_exists_nonempty_gate(output):
    if not isinstance(output, dict):
        return False, "brief_exists_nonempty_gate: output must be an object"
    if output.get("gate") != "brief_exists_nonempty_gate":
        return False, "brief_exists_nonempty_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "brief_exists_nonempty_gate: result must be a nonempty string"
    return True, "brief_exists_nonempty_gate passed"

def gate_brief_line_bound_gate(output):
    if not isinstance(output, dict):
        return False, "brief_line_bound_gate: output must be an object"
    if output.get("gate") != "brief_line_bound_gate":
        return False, "brief_line_bound_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "brief_line_bound_gate: result must be a nonempty string"
    return True, "brief_line_bound_gate passed"

def gate_brief_citation_gate(output):
    if not isinstance(output, dict):
        return False, "brief_citation_gate: output must be an object"
    if output.get("gate") != "brief_citation_gate":
        return False, "brief_citation_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "brief_citation_gate: result must be a nonempty string"
    return True, "brief_citation_gate passed"

def gate_brief_missing_error_gate(output):
    if not isinstance(output, dict):
        return False, "brief_missing_error_gate: output must be an object"
    if output.get("gate") != "brief_missing_error_gate":
        return False, "brief_missing_error_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "brief_missing_error_gate: result must be a nonempty string"
    return True, "brief_missing_error_gate passed"

def gate_fixture_mode_gate(output):
    if not isinstance(output, dict):
        return False, "fixture_mode_gate: output must be an object"
    if output.get("gate") != "fixture_mode_gate":
        return False, "fixture_mode_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "fixture_mode_gate: result must be a nonempty string"
    return True, "fixture_mode_gate passed"

def gate_request_only_router_gate(output):
    if not isinstance(output, dict):
        return False, "request_only_router_gate: output must be an object"
    if output.get("gate") != "request_only_router_gate":
        return False, "request_only_router_gate: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "request_only_router_gate: result must be a nonempty string"
    return True, "request_only_router_gate passed"

GATES = {
    "workflow_identity_gate": gate_workflow_identity_gate,
    "db_session_rows_gate": gate_db_session_rows_gate,
    "brief_exists_nonempty_gate": gate_brief_exists_nonempty_gate,
    "brief_line_bound_gate": gate_brief_line_bound_gate,
    "brief_citation_gate": gate_brief_citation_gate,
    "brief_missing_error_gate": gate_brief_missing_error_gate,
    "fixture_mode_gate": gate_fixture_mode_gate,
    "request_only_router_gate": gate_request_only_router_gate,
}

def check(name, output):
    fn = GATES.get(name)
    if fn is None:
        return False, f"unknown gate {name}"
    return fn(output)
