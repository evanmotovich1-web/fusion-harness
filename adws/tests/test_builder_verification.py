"""DoD checks and acceptance regressions. Failures are not xfailed or hidden."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from conftest import ADWS


def rows(db, query):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query)]


def load_gates(path):
    spec = importlib.util.spec_from_file_location("verification_generated_gates", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dod01_spec_predates_all_python():
    source = ADWS / "specs/workflow-builder.md"
    files = list(ADWS.rglob("*.py"))
    assert files and all(source.stat().st_mtime_ns < p.stat().st_mtime_ns for p in files)


def test_dod02_builder_phase_chain_and_attempt_records(accepted):
    phases = rows(accepted.db, "SELECT * FROM phase_attempts")
    assert {"intake", "survey", "spec", "spec_review", "scaffold", "implement", "validate", "register"} <= {p["phase_id"] for p in phases}
    agent_phases = [p for p in phases if p["kind"] == "agent"]
    attempts = rows(accepted.db, "SELECT * FROM agent_runs")
    assert len(agent_phases) == len(attempts) == 4
    log = (accepted.root / "reports/runs/verify/run.log").read_text()
    for phase in agent_phases:
        assert f"AGENT {phase['owner']} → GATE {phase['owner']} PASS" in log
    assert rows(accepted.db, "SELECT acceptance_status FROM runs")[0]["acceptance_status"] == "accepted"


def test_dod03_vague_request_preserved_without_artifacts(lab):
    result = lab.build("adws/fixtures/requests/toy_vague.md")
    assert result.returncode == 3 and "needs_human" in result.stdout
    run = lab.root / "reports/runs/verify"
    spec = json.loads((run / "spec.json").read_text())
    assert spec["invented"] is False and not spec["phases"] and not spec["requirements"]
    assert spec["request_verbatim"] == (ADWS / "fixtures/requests/toy_vague.md").read_text()
    assert all(spec[k] == "<EVAN: fill>" for k in ("id", "name", "outcome", "gate", "writes"))
    assert "What should the workflow do" in (run / "questions.md").read_text()
    assert not list((lab.root / "built").glob("*"))
    assert not rows(lab.db, "SELECT * FROM agent_runs")


@pytest.mark.parametrize("text,reason", [
    ("write a poem about the sea", "not_workflow"),
    ("edit sssf and add a button", "forbidden_target"),
    ("please git push and deploy to production", "forbidden_target"),
])
def test_dod04_named_refusals_before_spend(lab, text, reason):
    result = lab.build(text)
    assert result.returncode == 2 and reason in result.stdout
    assert not rows(lab.db, "SELECT * FROM agent_runs")
    assert not list((lab.root / "built").glob("*"))


def test_dod05_generated_cli_and_focused_tests(accepted):
    entry = accepted.entry()
    run = accepted.invoke([entry, "--fixtures", "--stub-agents", "--db", accepted.root / "generated.db",
                           "--reports-dir", accepted.root / "generated-reports"], expected=0)
    assert "AGENT greeter → GATE greeting_nonempty PASS" in run.stdout
    accepted.invoke(["-m", "pytest", entry.parent / "tests", "-q", "-p", "no:cacheprovider"], expected=0)


def test_dod06_bad_first_exact_soft_notice(lab):
    result = lab.build(extra=["--stub-bad-first"])
    assert result.returncode == 0
    log = result.stdout
    failure = json.loads((ADWS / "fixtures/bad_workflow_scout.json").read_text())["failure"]
    assert f"SOFT NOTICE: {failure}" in log
    assert log.index("GATE  workflow_scout attempt 1 FAIL") < log.index("SOFT NOTICE:") < log.index("GATE  workflow_scout attempt 2 PASS")
    prompt = (lab.root / "reports/runs/verify/workflow_scout.attempt2.prompt.md").read_text()
    assert failure in prompt
    assert all(row["attempts"] == 2 for row in rows(lab.db, "SELECT agent, COUNT(*) AS attempts FROM agent_runs GROUP BY agent"))


def test_dod07_partial_coverage_is_inspectable(lab):
    request = lab.root / "unmeetable-requirement.md"
    request.write_text("Build a workflow named partial-check that must record a greeting and an unmeetable side effect.")
    result = lab.build(str(request))
    assert result.returncode == 4
    coverage = rows(lab.db, "SELECT * FROM requirements")
    assert any(r["status"] == "verified" and json.loads(r["evidence_json"]) for r in coverage)
    assert any(r["status"] == "blocked" and r["blocker"] for r in coverage)
    assert "requirement(s) blocked" in rows(lab.db, "SELECT reason FROM workflow_builds")[0]["reason"]
    assert not lab.registry.exists()


def test_dod08_builder_telemetry_each_agent_and_attempt(accepted):
    agents = rows(accepted.db, "SELECT * FROM agent_runs")
    for agent in agents:
        names = json.loads(agent["tool_names_json"])
        counts = json.loads(agent["tool_counts_json"])
        assert names and sum(counts.values()) == len(names)
        assert all(names.count(name) == count for name, count in counts.items())
        assert agent["tool_errors"] == 0 and agent["duration_ms"] > 0
        assert agent["model"] == "unknown" and agent["stub"] == 1
        assert all(v == "unknown" for v in json.loads(agent["tokens_json"]).values())
        assert all(v == "unknown" for v in json.loads(agent["cost_json"]).values())
    assert len(rows(accepted.db, "SELECT * FROM agent_usage")) == len(agents)
    assert rows(accepted.db, "SELECT COUNT(*) AS n FROM tool_calls")[0]["n"] > 0


def test_dod09_registration_is_idempotent(accepted):
    result = accepted.build(run_id="second")
    assert result.returncode == 0
    entries = json.loads(accepted.registry.read_text())["workflows"]
    assert len(entries) == 1 and entries[0]["build_run_id"] == "second"


def test_dod10_unknown_tool_preflight_is_fixture_driven(lab):
    fixtures = lab.root / "fixtures"
    (fixtures / "preflight").mkdir(parents=True)
    (fixtures / "preflight/capability-check.json").write_text(json.dumps({"workflow_scout": ["read", "memory_search"]}))
    lab.env["ADW_FIXTURES_DIR"] = str(fixtures)
    request = lab.root / "capability-check.md"
    request.write_text("Build a workflow that must gate a nonempty greeting.")
    result = lab.build(str(request))
    assert result.returncode == 4 and "unknown_tool: memory_search" in result.stdout
    assert "AGENT " not in result.stdout and not rows(lab.db, "SELECT * FROM agent_runs")


def test_dod10_claimed_outside_write_refused(lab):
    request = lab.root / "out-of-scope-write.md"
    request.write_text("Build a workflow named echo-check that must gate a nonempty greeting.")
    result = lab.build(str(request))
    assert result.returncode == 4 and "diff_claims_real: path outside allowlist" in result.stdout
    assert not lab.registry.exists()


def test_dod11_socket_guard_covers_subprocess_tree(accepted):
    # conftest's sitecustomize forbids INET socket construction in every child.
    assert not (accepted.root / "socket-attempts.txt").exists()
    generated = accepted.invoke([accepted.entry(), "--fixtures", "--stub-agents",
                                 "--reports-dir", accepted.root / "guarded-generated"], expected=0)
    assert "PASS" in generated.stdout
    assert not (accepted.root / "socket-attempts.txt").exists()


def test_dod12_generated_forbidden_client_scan(accepted):
    from builder_modules import validators
    config = json.loads((accepted.entry().parent / "config.json").read_text())
    assert validators.grep_gate(config) == []


def test_dod13_root_authority_pointer():
    authority = (ADWS.parent / "AGENTS.md").read_text()
    assert "adws/specs/workflow-builder.md" in authority
    assert "--fixtures --stub-agents" in authority


# Acceptance regressions extend nominal fixtures to test the actual frozen law.
# These must remain failing until the implementation meets the contract.

def test_actual_outside_write_blocks_acceptance(lab):
    sentinel = lab.root / "outside-built-root.txt"
    wrapper = f'''import sys
sys.path.insert(0, {str(ADWS)!r})
import adw_workflow_builder as app
original = app.agents.StubRunner.run
def write_outside(self, call):
    if call.agent == "builder":
        from pathlib import Path
        Path({str(sentinel)!r}).write_text("out-of-scope fixture mutation")
    return original(self, call)
app.agents.StubRunner.run = write_outside
sys.exit(app.main(sys.argv[1:]))
'''
    result = lab.build(wrapper=wrapper)
    assert sentinel.exists(), "fixture failed to perform its harmless temporary out-of-scope write"
    assert result.returncode == 4, "an actual unclaimed outside write was accepted; claim-only audit is insufficient"
    assert not lab.registry.exists()


def test_generated_agents_have_telemetry_rows(accepted):
    db = accepted.root / "generated-telemetry.db"
    accepted.invoke([accepted.entry(), "--fixtures", "--stub-agents", "--db", db,
                     "--reports-dir", accepted.root / "generated-telemetry"], expected=0)
    attempts = rows(db, "SELECT * FROM phase_attempts WHERE kind='agent'")
    assert attempts
    agents = rows(db, "SELECT * FROM agent_runs")
    assert len(agents) == len(attempts), "generated workflow records phases but no per-agent tool/time/model/token/cost rows"


def test_completed_tool_errors_are_not_lost(tmp_path):
    from builder_modules.agents import tool_calls
    log = tmp_path / "calls.jsonl"
    events = [
        {"type": "tool_execution_start", "toolCallId": "read-1", "toolName": "read", "args": {"path": "missing.txt"}},
        {"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read", "isError": True,
         "result": {"content": [{"type": "text", "text": "ENOENT"}]}},
    ]
    log.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    calls = tool_calls(log)
    assert len(calls) == 1
    assert calls[0]["completion"] == "complete" and calls[0]["ok"] is False, "completed error was retained as an incomplete start"


def test_declared_requirement_verifier_exists(accepted):
    config = json.loads((accepted.entry().parent / "config.json").read_text())
    code = "\n".join(p.read_text() for p in (accepted.entry().parent / "tests").glob("test_*.py"))
    for req in config["requirements"]:
        assert f"def {req['verifier']}(" in code, f"requirement marked verified without its declared verifier: {req['verifier']}"


def test_requirement_specific_gate_rejects_wrong_total(lab):
    # No shared toy spec: a new request must receive its own objective verifier.
    fixtures = lab.root / "empty-fixtures"
    fixtures.mkdir()
    lab.env["ADW_FIXTURES_DIR"] = str(fixtures)
    request = "Build a workflow named total-check.\n- The gate must verify the computed total equals exactly 7.\n"
    result = lab.build(request)
    if result.returncode == 4:
        coverage = rows(lab.db, "SELECT text,status,blocker FROM requirements")
        assert any("7" in r["text"] and r["status"] == "blocked" and r["blocker"] for r in coverage)
        assert not lab.registry.exists()
        return
    assert result.returncode == 0, result.stdout + result.stderr
    config = json.loads((lab.entry().parent / "config.json").read_text())
    gate = load_gates(lab.entry().parent / "gates.py")
    name = config["requirements"][0]["gate"]
    ok, message = gate.check(name, {"gate": name, "result": "8", "total": 8})
    assert not ok, f"gate accepted total 8 for exactly-7 requirement: {message}"


def test_generated_unknown_tool_is_blocked(lab):
    import shutil
    fixtures = lab.root / "custom-fixtures"
    shutil.copytree(ADWS / "fixtures", fixtures)
    spec_path = fixtures / "good_spec_writer.json"
    config = json.loads(spec_path.read_text())
    config["seats"][0]["tools"].append("memory_search")
    spec_path.write_text(json.dumps(config))
    lab.env["ADW_FIXTURES_DIR"] = str(fixtures)
    result = lab.build()
    assert result.returncode == 4, "generated seat declares an absent tool but the workflow is accepted"
    assert not lab.registry.exists()


def test_original_request_not_replaced_by_shared_fixture(lab):
    request = "Build a workflow named count-check that must verify the number of records equals exactly 7."
    result = lab.build(request)
    if result.returncode == 4:
        build = rows(lab.db, "SELECT request_verbatim,reason FROM workflow_builds")[0]
        assert build["request_verbatim"] == request and "request" in build["reason"].lower()
        assert not lab.registry.exists()
        return
    assert result.returncode == 0
    config = json.loads((lab.entry().parent / "config.json").read_text())
    assert config["request_verbatim"] == request, "shared fixture replaced the original request before acceptance"
