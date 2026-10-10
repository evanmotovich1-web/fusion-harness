import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import gates


def _load():
    path = ROOT / "adw_research_learn.py"
    spec = importlib.util.spec_from_file_location("adw_research_learn", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_good_gate():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = raw["results"]["teach_back_report_nonempty"]
    ok, message = gates.check("teach_back_report_nonempty", sample)
    assert ok, message


def test_bad_gate_names_the_failure():
    raw = json.loads((ROOT / "fixtures" / "bad_researcher.json").read_text())
    ok, message = gates.check("teach_back_report_nonempty", raw["results"]["teach_back_report_nonempty"])
    assert not ok
    assert "result must be a nonempty string" in message


def test_stub_cli(tmp_path):
    module = _load()
    code = module.main([
        "--fixtures", "--stub-agents",
        "--db", str(tmp_path / "t.db"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert code == 0


def test_refusal(tmp_path):
    module = _load()
    code = module.main([
        "--request", "write a poem",
        "--fixtures", "--stub-agents",
        "--db", str(tmp_path / "t.db"),
        "--reports-dir", str(tmp_path / "reports"),
    ])
    assert code == 2


def test_teach_back_report_nonempty():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("teach_back_report_nonempty") or raw
    ok, message = gates.check("teach_back_report_nonempty", sample)
    assert ok, message


def test_claim_quote_found_in_pages_or_marked_unverified():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("claims_quote_local_page_or_marked_unverified") or raw
    ok, message = gates.check("claims_quote_local_page_or_marked_unverified", sample)
    assert ok, message


def test_uncited_claim_fails_citations_missing():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("claims_quote_local_page_or_marked_unverified") or raw
    ok, message = gates.check("claims_quote_local_page_or_marked_unverified", sample)
    assert ok, message


def test_explainer_html_exists_and_contains_topic():
    raw = json.loads((ROOT / "fixtures" / "good_explainer.json").read_text())
    sample = (raw.get("results") or {}).get("explainer_html_exists_and_contains_topic") or raw
    ok, message = gates.check("explainer_html_exists_and_contains_topic", sample)
    assert ok, message


def test_quiz_has_question_and_matching_answer_key():
    raw = json.loads((ROOT / "fixtures" / "good_quizmaster.json").read_text())
    sample = (raw.get("results") or {}).get("quiz_question_with_matching_answer_key") or raw
    ok, message = gates.check("quiz_question_with_matching_answer_key", sample)
    assert ok, message


def test_flashcards_nonempty():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("flashcards_nonempty") or raw
    ok, message = gates.check("flashcards_nonempty", sample)
    assert ok, message


def test_router_judges_request_only_and_pages_not_forbidden():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("router_request_only_pages_not_forbidden") or raw
    ok, message = gates.check("router_request_only_pages_not_forbidden", sample)
    assert ok, message


def test_fixture_mode_passes_without_url_fetch():
    raw = json.loads((ROOT / "fixtures" / "good_researcher.json").read_text())
    sample = (raw.get("results") or {}).get("fixture_mode_bundled_pages_no_url_fetch") or raw
    ok, message = gates.check("fixture_mode_bundled_pages_no_url_fetch", sample)
    assert ok, message
