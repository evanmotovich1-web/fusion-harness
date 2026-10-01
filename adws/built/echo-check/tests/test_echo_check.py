import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
import gates


def _load():
    path = ROOT / "adw_echo_check.py"
    spec = importlib.util.spec_from_file_location("adw_echo_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_good_gate():
    raw = json.loads((ROOT / "fixtures" / "good_greeter.json").read_text())
    sample = raw["results"]["greeting_nonempty"]
    ok, message = gates.check("greeting_nonempty", sample)
    assert ok, message


def test_bad_gate_names_the_failure():
    raw = json.loads((ROOT / "fixtures" / "bad_greeter.json").read_text())
    ok, message = gates.check("greeting_nonempty", raw["results"]["greeting_nonempty"])
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


def test_greeting_nonempty():
    raw = json.loads((ROOT / "fixtures" / "good_greeter.json").read_text())
    sample = (raw.get("results") or {}).get("greeting_nonempty") or raw
    ok, message = gates.check("greeting_nonempty", sample)
    assert ok, message
