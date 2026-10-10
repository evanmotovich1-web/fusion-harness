import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import gates


def _load():
    path = ROOT / "adw_business_presentations.py"
    spec = importlib.util.spec_from_file_location("adw_business_presentations", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_good_gate():
    raw = json.loads((ROOT / "fixtures" / "good_worker.json").read_text())
    sample = raw["results"]["req_1_gate"]
    ok, message = gates.check("req_1_gate", sample)
    assert ok, message


def test_bad_gate_names_the_failure():
    raw = json.loads((ROOT / "fixtures" / "bad_worker.json").read_text())
    ok, message = gates.check("req_1_gate", raw["results"]["req_1_gate"])
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


def test_req_1():
    raw = json.loads((ROOT / "fixtures" / "good_worker.json").read_text())
    sample = (raw.get("results") or {}).get("req_1_gate") or raw
    ok, message = gates.check("req_1_gate", sample)
    assert ok, message


def test_req_2():
    raw = json.loads((ROOT / "fixtures" / "good_worker.json").read_text())
    sample = (raw.get("results") or {}).get("req_2_gate") or raw
    ok, message = gates.check("req_2_gate", sample)
    assert ok, message


def test_req_3():
    raw = json.loads((ROOT / "fixtures" / "good_worker.json").read_text())
    sample = (raw.get("results") or {}).get("req_3_gate") or raw
    ok, message = gates.check("req_3_gate", sample)
    assert ok, message
