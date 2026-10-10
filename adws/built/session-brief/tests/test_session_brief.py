import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import gates


def _load():
    path = ROOT / "adw_session_brief.py"
    spec = importlib.util.spec_from_file_location("adw_session_brief", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_good_gate():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = raw["results"]["brief_exists_nonempty_gate"]
    ok, message = gates.check("brief_exists_nonempty_gate", sample)
    assert ok, message


def test_bad_gate_names_the_failure():
    raw = json.loads((ROOT / "fixtures" / "bad_brief_writer.json").read_text())
    ok, message = gates.check("brief_exists_nonempty_gate", raw["results"]["brief_exists_nonempty_gate"])
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


def test_workflow_identity():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("workflow_identity_gate") or raw
    ok, message = gates.check("workflow_identity_gate", sample)
    assert ok, message


def test_brief_exists_nonempty():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("brief_exists_nonempty_gate") or raw
    ok, message = gates.check("brief_exists_nonempty_gate", sample)
    assert ok, message


def test_brief_line_bound():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("brief_line_bound_gate") or raw
    ok, message = gates.check("brief_line_bound_gate", sample)
    assert ok, message


def test_brief_citation():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("brief_citation_gate") or raw
    ok, message = gates.check("brief_citation_gate", sample)
    assert ok, message


def test_brief_missing_error():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("brief_missing_error_gate") or raw
    ok, message = gates.check("brief_missing_error_gate", sample)
    assert ok, message


def test_db_session_rows():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("db_session_rows_gate") or raw
    ok, message = gates.check("db_session_rows_gate", sample)
    assert ok, message


def test_fixture_mode():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("fixture_mode_gate") or raw
    ok, message = gates.check("fixture_mode_gate", sample)
    assert ok, message


def test_request_only_router():
    raw = json.loads((ROOT / "fixtures" / "good_brief_writer.json").read_text())
    sample = (raw.get("results") or {}).get("request_only_router_gate") or raw
    ok, message = gates.check("request_only_router_gate", sample)
    assert ok, message
