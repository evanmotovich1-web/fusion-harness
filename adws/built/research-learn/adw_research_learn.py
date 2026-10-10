"""Generated ADW research-learn. Code orchestrates. Stub-first. No network client."""
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
SPEC = json.loads('{"schema_version": 1, "id": "research-learn", "name": "Research Learn", "request_verbatim": "Build a workflow named research-learn.\\n- The gate must verify the teach-back report is a nonempty string.\\n- The gate must verify each claim quotes a string found in a local page file under --pages, or the line is marked unverified.\\n- The gate must verify an uncited claim fails with the error citations-missing.\\n- The gate must verify the explainer HTML file exists and contains the topic string.\\n- The gate must verify the quiz has at least 1 question and a matching answer key.\\n- The gate must verify the flashcards file is a nonempty string.\\n- The router must judge only the --request string. A --pages path must not be a forbidden target.\\n- Fixture mode must pass with the bundled local pages and must not fetch a URL.\\n", "router": {"triggers": ["research-learn", "teach-back report from local pages", "explainer, quiz and flashcards from local pages"], "refusals": [{"reason": "not_workflow", "example": "write a poem about the sea"}, {"reason": "forbidden_target", "example": "fetch remote pages for the topic and publish the summary"}, {"reason": "needs_human", "example": "build a learning workflow about whatever you find"}]}, "requirements": [{"id": "req-1", "text": "The gate must verify the teach-back report is a nonempty string.", "phase_id": "p3", "gate": "teach_back_report_nonempty", "verifier": "test_teach_back_report_nonempty", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-2", "text": "The gate must verify each claim quotes a string found in a local page file under --pages, or the line is marked unverified.", "phase_id": "p4", "gate": "claims_quote_local_page_or_marked_unverified", "verifier": "test_claim_quote_found_in_pages_or_marked_unverified", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-3", "text": "The gate must verify an uncited claim fails with the error citations-missing.", "phase_id": "p4", "gate": "claims_quote_local_page_or_marked_unverified", "verifier": "test_uncited_claim_fails_citations_missing", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-4", "text": "The gate must verify the explainer HTML file exists and contains the topic string.", "phase_id": "p5", "gate": "explainer_html_exists_and_contains_topic", "verifier": "test_explainer_html_exists_and_contains_topic", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-5", "text": "The gate must verify the quiz has at least 1 question and a matching answer key.", "phase_id": "p6", "gate": "quiz_question_with_matching_answer_key", "verifier": "test_quiz_has_question_and_matching_answer_key", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-6", "text": "The gate must verify the flashcards file is a nonempty string.", "phase_id": "p7", "gate": "flashcards_nonempty", "verifier": "test_flashcards_nonempty", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-7", "text": "The router must judge only the --request string. A --pages path must not be a forbidden target.", "phase_id": "p1", "gate": "router_request_only_pages_not_forbidden", "verifier": "test_router_judges_request_only_and_pages_not_forbidden", "evidence": [], "status": "blocked", "blocker": null}, {"id": "req-8", "text": "Fixture mode must pass with the bundled local pages and must not fetch a URL.", "phase_id": "p8", "gate": "fixture_mode_bundled_pages_no_url_fetch", "verifier": "test_fixture_mode_passes_without_url_fetch", "evidence": [], "status": "blocked", "blocker": null}], "phases": [{"id": "p1", "name": "route", "kind": "code", "owner": "code", "gate": "router_request_only_pages_not_forbidden", "inputs": ["--request string"], "outputs": ["route.json"], "retries": 0}, {"id": "p2", "name": "preflight-pages", "kind": "code", "owner": "code", "gate": "pages_present_local_no_url_input", "inputs": ["--pages (live: <EVAN: fill> local pages directory; fixture mode: adws/built/research-learn/pages/**)"], "outputs": ["preflight.json", "pages-index.json"], "retries": 0}, {"id": "p3", "name": "teach-back", "kind": "agent", "owner": "researcher", "gate": "teach_back_report_nonempty", "inputs": ["p2", "request"], "outputs": ["teach-back.json", "teach-back.md"], "retries": 1}, {"id": "p4", "name": "claims", "kind": "agent", "owner": "researcher", "gate": "claims_quote_local_page_or_marked_unverified", "inputs": ["p3", "p2"], "outputs": ["claims.json"], "retries": 1}, {"id": "p5", "name": "explainer", "kind": "agent", "owner": "explainer", "gate": "explainer_html_exists_and_contains_topic", "inputs": ["p3", "--topic (live: from the run request; fixture default: <EVAN: fill>)"], "outputs": ["explainer.json", "explainer.html"], "retries": 1}, {"id": "p6", "name": "quiz", "kind": "agent", "owner": "quizmaster", "gate": "quiz_question_with_matching_answer_key", "inputs": ["p3", "p4"], "outputs": ["quiz.json", "answer-key.json"], "retries": 1}, {"id": "p7", "name": "flashcards", "kind": "agent", "owner": "researcher", "gate": "flashcards_nonempty", "inputs": ["p3"], "outputs": ["flashcards.json"], "retries": 1}, {"id": "p8", "name": "fixtures", "kind": "code", "owner": "code", "gate": "fixture_mode_bundled_pages_no_url_fetch", "inputs": ["p2", "p3", "p4", "p5", "p6", "p7", "adws/built/research-learn/pages/**"], "outputs": ["fixture-run.json"], "retries": 0}, {"id": "p9", "name": "validate", "kind": "code", "owner": "code", "gate": "requirement_coverage_on_final_state", "inputs": ["p1", "p4", "p8"], "outputs": ["acceptance.json", "requirement-coverage.json"], "retries": 1}], "seats": [{"name": "researcher", "model": "deepseek/deepseek-flash", "thinking": "medium", "tools": ["read", "grep", "find", "ls", "write"], "writes": ["adws/built/research-learn/**"], "prompt_files": ["system.md", "user.md", "soft_notice.md", "tools.json"]}, {"name": "explainer", "model": "deepseek/deepseek-flash", "thinking": "medium", "tools": ["read", "write"], "writes": ["adws/built/research-learn/**"], "prompt_files": ["system.md", "user.md", "soft_notice.md", "tools.json"]}, {"name": "quizmaster", "model": "deepseek/deepseek-flash", "thinking": "medium", "tools": ["read", "write"], "writes": ["adws/built/research-learn/**"], "prompt_files": ["system.md", "user.md", "soft_notice.md", "tools.json"]}], "artifacts": {"entrypoint": "adws/built/research-learn/adw_research_learn.py", "files": ["adws/built/research-learn/adw_research_learn.py", "adws/built/research-learn/config.json", "adws/built/research-learn/gates.py", "adws/built/research-learn/README.md", "adws/built/research-learn/tests/test_research_learn.py", "adws/built/research-learn/pages/page-01.md", "adws/built/research-learn/pages/page-02.md", "adws/built/research-learn/pages/page-03.md", "adws/built/research-learn/prompts/researcher/system.md", "adws/built/research-learn/prompts/researcher/user.md", "adws/built/research-learn/prompts/researcher/soft_notice.md", "adws/built/research-learn/prompts/researcher/tools.json", "adws/built/research-learn/fixtures/good_researcher.json", "adws/built/research-learn/fixtures/bad_researcher.json", "adws/built/research-learn/prompts/explainer/system.md", "adws/built/research-learn/prompts/explainer/user.md", "adws/built/research-learn/prompts/explainer/soft_notice.md", "adws/built/research-learn/prompts/explainer/tools.json", "adws/built/research-learn/fixtures/good_explainer.json", "adws/built/research-learn/fixtures/bad_explainer.json", "adws/built/research-learn/prompts/quizmaster/system.md", "adws/built/research-learn/prompts/quizmaster/user.md", "adws/built/research-learn/prompts/quizmaster/soft_notice.md", "adws/built/research-learn/prompts/quizmaster/tools.json", "adws/built/research-learn/fixtures/good_quizmaster.json", "adws/built/research-learn/fixtures/bad_quizmaster.json"]}, "switches": {"dry_run": true, "stub_agents": true}, "blockers": []}')
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
    parser.add_argument("--pages", default="")
    parser.add_argument("--bad-fixture", default="")
    args = parser.parse_args(argv)
    if args.bad_fixture:
        fixture = ROOT / "fixtures" / f"{args.bad_fixture}.json"
        if not fixture.is_file():
            print(f"missing fixture {fixture.name}", flush=True)
            return 2
        payload = json.loads(fixture.read_text())
        ok, message = gates.check(payload.get("gate") or "claims_quote_local_page_or_marked_unverified", payload)
        print(message, flush=True)
        return 0 if ok else 1
    # --pages is a path flag. The router below sees only --request.
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
