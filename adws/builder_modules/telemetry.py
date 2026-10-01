"""Telemetry writers. Missing provider numbers stay 'unknown', never 0."""

from __future__ import annotations

import json
from typing import Any

from .db import now_iso

UNKNOWN_TOKENS = {
    "input": "unknown",
    "output": "unknown",
    "cache": "unknown",
    "reasoning": "unknown",
    "total": "unknown",
}
UNKNOWN_COST = {"total": "unknown", "currency": "unknown", "source": "unknown"}


def unknown_tokens() -> str:
    return json.dumps(UNKNOWN_TOKENS)


def unknown_cost() -> str:
    return json.dumps(UNKNOWN_COST)


def start_run(conn, run_id: str, request_ref: str, config_hash: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_id, request_ref, config_hash, started_at, run_status, acceptance_status) "
        "VALUES (?,?,?,?, 'running', 'pending')",
        (run_id, request_ref, config_hash, now_iso()),
    )
    conn.commit()


def finish_run(conn, run_id: str, run_status: str, acceptance: str, reason: str, artifacts: list[str],
               workflow_id: str | None = None, version: int | None = None) -> None:
    conn.execute(
        "UPDATE runs SET ended_at=?, run_status=?, acceptance_status=?, acceptance_reason=?, "
        "artifact_index=?, workflow_id=?, workflow_version=? WHERE run_id=?",
        (now_iso(), run_status, acceptance, reason, json.dumps(artifacts), workflow_id, version, run_id),
    )
    conn.commit()


def phase_attempt(conn, run_id: str, phase_id: str, name: str, kind: str, owner: str, attempt: int,
                  started: str, duration_ms: int | None, status: str, error: str | None, gate_id: str,
                  gate_result: str, model: str = "unknown", thinking: str = "unknown",
                  session_id: str | None = None, tools: list[str] | None = None) -> None:
    conn.execute(
        "INSERT INTO phase_attempts (run_id, phase_id, phase_name, kind, owner, attempt, started_at, ended_at, "
        "duration_ms, status, error, gate_id, gate_result, model, thinking, session_id, tool_allowlist) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, phase_id, name, kind, owner, attempt, started, now_iso(), duration_ms, status, error, gate_id,
         gate_result, model, thinking, session_id, json.dumps(tools or [])),
    )
    conn.commit()


def agent_run(conn, run_id: str, agent: str, attempt: int, passed: bool, failures: list[str],
              calls: list[dict], duration_ms: int | None, model: str, tokens: dict, cost: dict,
              prompt_path: str, log_path: str, argv: list[str], tools: dict, stub: bool) -> None:
    names = [c.get("tool") for c in calls]
    counts: dict[str, int] = {}
    errors = 0
    observed = bool(calls) or True  # log was parsed; zero calls is observed, not missing
    for call in calls:
        tool = str(call.get("tool") or "unknown")
        counts[tool] = counts.get(tool, 0) + 1
        if call.get("ok") is False:
            errors += 1
    conn.execute(
        "INSERT INTO agent_runs (run_id, workflow, agent, attempt, gate_passed, failures_json, tool_names_json, "
        "tool_counts_json, tool_errors, duration_ms, model, tokens_json, cost_json, prompt_path, log_path, "
        "pi_argv_json, tools_json, started_at, ended_at, stub) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "workflow_builder", agent, attempt, int(passed), json.dumps(failures), json.dumps(names),
         json.dumps(counts), errors if observed else None, duration_ms, model or "unknown",
         json.dumps(tokens), json.dumps(cost), prompt_path, log_path, json.dumps(argv), json.dumps(tools),
         now_iso(), now_iso(), int(stub)),
    )
    conn.commit()


def tool_call_rows(conn, run_id: str, phase_id: str, agent: str, attempt: int, calls: list[dict]) -> None:
    for index, call in enumerate(calls):
        call_id = str(call.get("call_id") or f"{agent}-{attempt}-{index}")
        ok = call.get("ok")
        completion = call.get("completion") or ("complete" if ok is not None else "incomplete")
        conn.execute(
            "INSERT OR IGNORE INTO tool_calls (run_id, phase_id, agent, attempt, call_id, tool_name, args_json, "
            "started_at, ended_at, duration_ms, completion, ok, error, result_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, phase_id, agent, attempt, call_id, call.get("tool"), json.dumps(_sanitize(call.get("args") or {})),
             call.get("started_at"), call.get("ended_at"), call.get("duration_ms"), completion,
             None if ok is None else int(bool(ok)), call.get("error"), call.get("result_ref")),
        )
    conn.commit()


def code_op(conn, run_id: str, phase_id: str, name: str, argv: list[str], cwd: str, duration_ms: int | None,
            return_code: int | None, passed: bool, stdout_hash: str, stderr_hash: str) -> None:
    conn.execute(
        "INSERT INTO code_operations (run_id, phase_id, operation_id, name, argv_json, cwd, duration_ms, "
        "return_code, passed, stdout_hash, stderr_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, phase_id, f"{phase_id}:{name}:{now_iso()}", name, json.dumps(argv), cwd, duration_ms,
         return_code, int(passed), stdout_hash, stderr_hash),
    )
    conn.commit()


def usage(conn, run_id: str, phase_id: str, agent: str, attempt: int, tokens: dict, cost: dict,
          completeness: str) -> None:
    """One row per attempt, including attempts whose gate failed. Never insert a second row."""
    conn.execute(
        "INSERT OR IGNORE INTO agent_usage (run_id, phase_id, agent, attempt, tokens_json, cost_json, currency, "
        "cost_source, completeness) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, phase_id, agent, attempt, json.dumps(tokens), json.dumps(cost),
         str(cost.get("currency", "unknown")), str(cost.get("source", "unknown")), completeness),
    )
    conn.commit()


def requirement_row(conn, run_id: str, req: dict, evidence: list[str]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO requirements (run_id, req_id, text, phase_id, gate, verifier, status, blocker, evidence_json) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, req["id"], req["text"], req.get("phase_id"), req.get("gate"), req.get("verifier"),
         req.get("status") or "blocked", req.get("blocker"), json.dumps(evidence)),
    )
    conn.commit()


def workflow_build(conn, run_id: str, status: str, reason: str, request: str, workflow_id: str | None = None,
                   name: str | None = None, version: int | None = None, built_path: str | None = None) -> None:
    conn.execute(
        "INSERT INTO workflow_builds (run_id, workflow_id, name, version, status, reason, request_verbatim, "
        "built_path, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, workflow_id, name, version, status, reason, request, built_path, now_iso()),
    )
    conn.commit()


def _sanitize(args: dict) -> dict:
    redacted = {}
    for key, value in args.items():
        if key.lower() in {"key", "token", "authorization", "api_key", "password"}:
            redacted[key] = "<redacted>"
        else:
            text = value if isinstance(value, str) else json.dumps(value)
            redacted[key] = text[:500]
    return redacted


def counts_for(conn, run_id: str, agent: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT tool_counts_json, tool_errors, duration_ms, model, tokens_json, cost_json FROM agent_runs "
        "WHERE run_id=? AND agent=? ORDER BY attempt DESC LIMIT 1",
        (run_id, agent),
    ).fetchone()
    return dict(row) if row else {}
