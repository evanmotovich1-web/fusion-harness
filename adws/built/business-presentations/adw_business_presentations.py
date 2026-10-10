"""Generated ADW business-presentations. Code orchestrates. Stub-first. No network client."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import gates

ROOT = Path(__file__).resolve().parent
SPEC = json.loads('{"schema_version": 1, "id": "business-presentations", "name": "Business Presentations", "request_verbatim": "Build a workflow named business-presentations.\\n- The gate must verify the brief is a nonempty string.\\n- The gate must verify the storyboard is a nonempty string.\\n- The gate must verify the speaker notes are a nonempty string.\\n", "router": {"triggers": ["business presentations", "workflow"], "refusals": [{"reason": "not_workflow", "example": "write a poem"}, {"reason": "forbidden_target", "example": "edit sssf and deploy"}]}, "requirements": [{"id": "req-1", "text": "The gate must verify the brief is a nonempty string.", "phase_id": "p1", "gate": "req_1_gate", "verifier": "test_req_1", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-2", "text": "The gate must verify the storyboard is a nonempty string.", "phase_id": "p2", "gate": "req_2_gate", "verifier": "test_req_2", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-3", "text": "The gate must verify the speaker notes are a nonempty string.", "phase_id": "p3", "gate": "req_3_gate", "verifier": "test_req_3", "evidence": [], "status": "blocked", "blocker": null}], "phases": [{"id": "p1", "name": "step-1", "kind": "agent", "owner": "worker", "gate": "req_1_gate", "inputs": ["request"], "outputs": ["req-1.json"], "retries": 1}, {"id": "p2", "name": "step-2", "kind": "agent", "owner": "worker", "gate": "req_2_gate", "inputs": ["request"], "outputs": ["req-2.json"], "retries": 1}, {"id": "p3", "name": "step-3", "kind": "agent", "owner": "worker", "gate": "req_3_gate", "inputs": ["request"], "outputs": ["req-3.json"], "retries": 1}], "seats": [{"name": "worker", "model": "deepseek/deepseek-flash", "thinking": "medium", "tools": ["read", "write"], "writes": ["adws/built/business-presentations/**"], "prompt_files": ["system.md", "user.md", "soft_notice.md", "tools.json"]}], "artifacts": {"entrypoint": "adws/built/business-presentations/adw_business_presentations.py", "files": ["adws/built/business-presentations/adw_business_presentations.py", "adws/built/business-presentations/config.json", "adws/built/business-presentations/gates.py", "adws/built/business-presentations/README.md", "adws/built/business-presentations/tests/test_business_presentations.py", "adws/built/business-presentations/prompts/worker/system.md", "adws/built/business-presentations/prompts/worker/user.md", "adws/built/business-presentations/prompts/worker/soft_notice.md", "adws/built/business-presentations/prompts/worker/tools.json", "adws/built/business-presentations/fixtures/good_worker.json", "adws/built/business-presentations/fixtures/bad_worker.json"]}, "switches": {"dry_run": true, "stub_agents": true}, "blockers": []}')
FAILURE = "result must be a nonempty string"


def _guard() -> None:
    import socket
    def _blocked(*_args, **_kwargs):
        raise RuntimeError("stub mode blocked a network socket")
    socket.socket.connect = _blocked
    socket.create_connection = _blocked


def _route(text: str) -> str:
    low = " ".join(text.lower().split())
    if "sssf" in low or "deploy" in low or ("push" in low and "origin" in low):
        return "forbidden_target"
    if "poem" in low or "haiku" in low or "pitch deck" in low:
        return "not_workflow"
    if len(low.split()) < 4:
        return "needs_human"
    return "build"


def _init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    schema = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "schema.sql"
        if candidate.is_file():
            schema = candidate.read_text()
            break
    conn.executescript(schema or """
        CREATE TABLE IF NOT EXISTS phase_attempts (
            id INTEGER PRIMARY KEY, run_id TEXT, phase_id TEXT, phase_name TEXT, kind TEXT,
            owner TEXT, attempt INTEGER, started_at TEXT, ended_at TEXT, duration_ms INTEGER,
            status TEXT, error TEXT, gate_id TEXT, gate_result TEXT, model TEXT, thinking TEXT,
            session_id TEXT, tool_allowlist TEXT);
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY, run_id TEXT, workflow TEXT, agent TEXT, attempt INTEGER,
            gate_passed INTEGER, failures_json TEXT, tool_names_json TEXT, tool_counts_json TEXT,
            tool_errors INTEGER, duration_ms INTEGER, model TEXT, tokens_json TEXT, cost_json TEXT,
            prompt_path TEXT, log_path TEXT, pi_argv_json TEXT, tools_json TEXT, started_at TEXT,
            ended_at TEXT, stub INTEGER NOT NULL DEFAULT 0);
    """)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, phase_id TEXT, agent TEXT, attempt INTEGER,
            call_id TEXT NOT NULL, tool_name TEXT, args_json TEXT, started_at TEXT, ended_at TEXT,
            duration_ms INTEGER, completion TEXT NOT NULL, ok INTEGER, error TEXT, result_ref TEXT,
            UNIQUE (run_id, call_id));
        CREATE TABLE IF NOT EXISTS agent_usage (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, phase_id TEXT, agent TEXT NOT NULL,
            attempt INTEGER NOT NULL, tokens_json TEXT NOT NULL, cost_json TEXT NOT NULL,
            currency TEXT, cost_source TEXT, completeness TEXT NOT NULL,
            UNIQUE (run_id, agent, attempt));
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, workflow_id TEXT, workflow_version INTEGER, request_ref TEXT,
            config_hash TEXT, started_at TEXT NOT NULL, ended_at TEXT, run_status TEXT,
            acceptance_status TEXT, acceptance_reason TEXT, artifact_index TEXT);
    """)
    conn.commit()
    return conn


def _record_agent(conn, run_id: str, phase: dict, attempt: int, ok: bool, message: str, duration_ms: int) -> None:
    seat = phase["owner"]
    tokens = json.dumps({"input": "unknown", "output": "unknown", "cache": "unknown", "reasoning": "unknown", "total": "unknown"})
    cost = json.dumps({"total": "unknown", "currency": "unknown", "source": "unknown"})
    names = json.dumps(["read"])
    counts = json.dumps({"read": 1})
    conn.execute(
        "INSERT INTO agent_runs (run_id, workflow, agent, attempt, gate_passed, failures_json, tool_names_json, "
        "tool_counts_json, tool_errors, duration_ms, model, tokens_json, cost_json, prompt_path, log_path, "
        "pi_argv_json, tools_json, started_at, ended_at, stub) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),1)",
        (run_id, SPEC.get("id") or "generated", seat, attempt, 1 if ok else 0, json.dumps([] if ok else [message]),
         names, counts, 0, duration_ms, "unknown", tokens, cost, "", "", "[]", names),
    )
    conn.execute(
        "INSERT OR IGNORE INTO tool_calls (run_id, phase_id, agent, attempt, call_id, tool_name, args_json, "
        "started_at, ended_at, duration_ms, completion, ok, error) VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'),?,'complete',1,NULL)",
        (run_id, phase["id"], seat, attempt, f"{seat}-{attempt}-read", "read", "{}", duration_ms),
    )
    conn.execute(
        "INSERT OR IGNORE INTO agent_usage (run_id, phase_id, agent, attempt, tokens_json, cost_json, currency, "
        "cost_source, completeness) VALUES (?,?,?,?,?,?, 'unknown', 'unknown', 'unknown')",
        (run_id, phase["id"], seat, attempt, tokens, cost),
    )
    conn.commit()


def _phase_output(seat: str, gate: str, bad: bool) -> dict:
    name = f"{'bad' if bad else 'good'}_{seat}.json"
    raw = json.loads((ROOT / "fixtures" / name).read_text())
    results = raw.get("results") or {}
    return results.get(gate) or raw


def _run_phase(log, conn, run_id: str, phase: dict, bad_first: bool) -> bool:
    seat = phase["owner"]
    gate = phase["gate"]
    started = time.perf_counter()
    for attempt in range(1, 3):
        bad = bad_first and attempt == 1
        output = _phase_output(seat, gate, bad)
        ok, message = gates.check(gate, output)
        mark = "PASS" if ok else "FAIL"
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        log(f"AGENT {seat} → GATE {gate} {mark}")
        log(f"GATE  {gate} attempt {attempt} {mark}")
        if conn is not None:
            conn.execute(
                "INSERT INTO phase_attempts (run_id, phase_id, phase_name, kind, owner, attempt, started_at, "
                "duration_ms, status, gate_id, gate_result, model, thinking) VALUES (?,?,?,?,?,?,datetime('now'),?,?,?,?, 'unknown','unknown')",
                (run_id, phase["id"], phase["name"], phase["kind"], seat, attempt, duration_ms,
                 "passed" if ok else "failed", gate, message),
            )
            _record_agent(conn, run_id, phase, attempt, ok, message, duration_ms)
        if ok:
            return True
        log(f"SOFT NOTICE: {message}")
        if not bad_first:
            return False
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generated ADW (stub-first)")
    parser.add_argument("--request", default=SPEC.get("request_verbatim") or "")
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--stub-agents", action="store_true")
    parser.add_argument("--stub-bad-first", action="store_true")
    parser.add_argument("--db", default="")
    parser.add_argument("--reports-dir", default="")
    args = parser.parse_args(argv)
    stub = args.stub_agents or args.fixtures or os.environ.get("DRY_RUN", "true") != "false"
    if stub:
        _guard()
    if os.environ.get("DRY_RUN", "true") == "false" and not stub:
        print("REFUSED: live switch is not enabled", flush=True)
        return 4
    reports = Path(args.reports_dir) if args.reports_dir else ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(line: str) -> None:
        print(line, flush=True)
        lines.append(line)

    decision = _route(args.request)
    log(f"CODE intake: {decision}")
    if decision != "build":
        (reports / "report.md").write_text(f"# {decision}\n\nrequest preserved\n")
        (reports / "run.log").write_text("\n".join(lines) + "\n")
        return 2 if decision != "needs_human" else 3
    conn = _init_db(Path(args.db)) if args.db else None
    run_id = "generated-stub"
    ok = True
    for phase in SPEC["phases"]:
        if phase.get("kind") != "agent":
            log(f"CODE {phase['name']} → GATE {phase['gate']} PASS")
            continue
        if not _run_phase(log, conn, run_id, phase, args.stub_bad_first):
            ok = False
            break
    (reports / "run.log").write_text("\n".join(lines) + "\n")
    (reports / "report.md").write_text("# accepted\n" if ok else "# blocked\n")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
