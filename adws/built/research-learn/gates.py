"""Requirement gates. A pass needs a nonempty result for the named gate."""
from pathlib import Path

def gate_router_request_only_pages_not_forbidden(output):
    if not isinstance(output, dict):
        return False, "router_request_only_pages_not_forbidden: output must be an object"
    if output.get("gate") != "router_request_only_pages_not_forbidden":
        return False, "router_request_only_pages_not_forbidden: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "router_request_only_pages_not_forbidden: result must be a nonempty string"
    return True, "router_request_only_pages_not_forbidden passed"

def gate_pages_present_local_no_url_input(output):
    if not isinstance(output, dict):
        return False, "pages_present_local_no_url_input: output must be an object"
    if output.get("gate") != "pages_present_local_no_url_input":
        return False, "pages_present_local_no_url_input: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "pages_present_local_no_url_input: result must be a nonempty string"
    return True, "pages_present_local_no_url_input passed"

def gate_teach_back_report_nonempty(output):
    if not isinstance(output, dict):
        return False, "teach_back_report_nonempty: output must be an object"
    if output.get("gate") != "teach_back_report_nonempty":
        return False, "teach_back_report_nonempty: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "teach_back_report_nonempty: result must be a nonempty string"
    return True, "teach_back_report_nonempty passed"

def _page_texts():
    root = Path(__file__).resolve().parent / "pages"
    texts = []
    if not root.is_dir():
        return texts
    for path in sorted(root.iterdir()):
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return texts


def gate_claims_quote_local_page_or_marked_unverified(output):
    if not isinstance(output, dict):
        return False, "claims_quote_local_page_or_marked_unverified: output must be an object"
    if output.get("gate") != "claims_quote_local_page_or_marked_unverified":
        return False, "claims_quote_local_page_or_marked_unverified: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "claims_quote_local_page_or_marked_unverified: result must be a nonempty string"
    claims = output.get("claims")
    if not isinstance(claims, list):
        return True, "claims_quote_local_page_or_marked_unverified passed"
    pages = _page_texts()
    for claim in claims:
        if not isinstance(claim, dict):
            return False, "citations-missing"
        mark = str(claim.get("mark") or "").lower()
        if claim.get("unverified") is True or "unverified" in mark:
            continue
        quote = str(claim.get("quote") or "")
        if not quote or not any(quote in page for page in pages):
            return False, "citations-missing"
    return True, "claims_quote_local_page_or_marked_unverified passed"

def gate_explainer_html_exists_and_contains_topic(output):
    if not isinstance(output, dict):
        return False, "explainer_html_exists_and_contains_topic: output must be an object"
    if output.get("gate") != "explainer_html_exists_and_contains_topic":
        return False, "explainer_html_exists_and_contains_topic: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "explainer_html_exists_and_contains_topic: result must be a nonempty string"
    return True, "explainer_html_exists_and_contains_topic passed"

def gate_quiz_question_with_matching_answer_key(output):
    if not isinstance(output, dict):
        return False, "quiz_question_with_matching_answer_key: output must be an object"
    if output.get("gate") != "quiz_question_with_matching_answer_key":
        return False, "quiz_question_with_matching_answer_key: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "quiz_question_with_matching_answer_key: result must be a nonempty string"
    return True, "quiz_question_with_matching_answer_key passed"

def gate_flashcards_nonempty(output):
    if not isinstance(output, dict):
        return False, "flashcards_nonempty: output must be an object"
    if output.get("gate") != "flashcards_nonempty":
        return False, "flashcards_nonempty: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "flashcards_nonempty: result must be a nonempty string"
    return True, "flashcards_nonempty passed"

def gate_fixture_mode_bundled_pages_no_url_fetch(output):
    if not isinstance(output, dict):
        return False, "fixture_mode_bundled_pages_no_url_fetch: output must be an object"
    if output.get("gate") != "fixture_mode_bundled_pages_no_url_fetch":
        return False, "fixture_mode_bundled_pages_no_url_fetch: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "fixture_mode_bundled_pages_no_url_fetch: result must be a nonempty string"
    return True, "fixture_mode_bundled_pages_no_url_fetch passed"

def gate_requirement_coverage_on_final_state(output):
    if not isinstance(output, dict):
        return False, "requirement_coverage_on_final_state: output must be an object"
    if output.get("gate") != "requirement_coverage_on_final_state":
        return False, "requirement_coverage_on_final_state: gate field mismatch"
    result = output.get("result")
    if not isinstance(result, str) or not result.strip():
        return False, "requirement_coverage_on_final_state: result must be a nonempty string"
    return True, "requirement_coverage_on_final_state passed"

GATES = {
    "router_request_only_pages_not_forbidden": gate_router_request_only_pages_not_forbidden,
    "pages_present_local_no_url_input": gate_pages_present_local_no_url_input,
    "teach_back_report_nonempty": gate_teach_back_report_nonempty,
    "claims_quote_local_page_or_marked_unverified": gate_claims_quote_local_page_or_marked_unverified,
    "explainer_html_exists_and_contains_topic": gate_explainer_html_exists_and_contains_topic,
    "quiz_question_with_matching_answer_key": gate_quiz_question_with_matching_answer_key,
    "flashcards_nonempty": gate_flashcards_nonempty,
    "fixture_mode_bundled_pages_no_url_fetch": gate_fixture_mode_bundled_pages_no_url_fetch,
    "requirement_coverage_on_final_state": gate_requirement_coverage_on_final_state,
}

def check(name, output):
    fn = GATES.get(name)
    if fn is None:
        return False, f"unknown gate {name}"
    return fn(output)
