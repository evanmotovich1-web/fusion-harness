-- Workflow-builder telemetry. Idempotent. Shared by the builder and generated workflows.
-- Absent provider data is stored as the text 'unknown', never as a fake zero.

CREATE TABLE IF NOT EXISTS workflow_builds (
    id                INTEGER PRIMARY KEY,
    run_id            TEXT NOT NULL,
    workflow_id       TEXT,
    name              TEXT,
    version           INTEGER,
    status            TEXT NOT NULL,          -- accepted | refused | needs_human | blocked
    reason            TEXT,
    request_verbatim  TEXT,
    built_path        TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id               INTEGER PRIMARY KEY,
    run_id           TEXT NOT NULL,
    workflow         TEXT NOT NULL,
    agent            TEXT NOT NULL,
    attempt          INTEGER NOT NULL,
    gate_passed      INTEGER,
    failures_json    TEXT,
    tool_names_json  TEXT,
    tool_counts_json TEXT,
    tool_errors      INTEGER,                 -- NULL when the log was not observed
    duration_ms      INTEGER,                 -- NULL when not measured
    model            TEXT,                    -- configured id, or 'unknown'
    tokens_json      TEXT,                    -- buckets are 'unknown' when the provider did not report
    cost_json        TEXT,
    prompt_path      TEXT,
    log_path         TEXT,
    pi_argv_json     TEXT,
    tools_json       TEXT,
    started_at       TEXT,
    ended_at         TEXT,
    stub             INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    workflow_id       TEXT,
    workflow_version  INTEGER,
    request_ref       TEXT,
    config_hash       TEXT,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    run_status        TEXT,
    acceptance_status TEXT,
    acceptance_reason TEXT,
    artifact_index    TEXT
);

CREATE TABLE IF NOT EXISTS phase_attempts (
    id            INTEGER PRIMARY KEY,
    run_id        TEXT NOT NULL,
    phase_id      TEXT NOT NULL,
    phase_name    TEXT NOT NULL,
    kind          TEXT NOT NULL,              -- code | agent
    owner         TEXT NOT NULL,
    attempt       INTEGER NOT NULL,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    duration_ms   INTEGER,
    status        TEXT NOT NULL,
    error         TEXT,
    gate_id       TEXT,
    gate_result   TEXT,
    model         TEXT,
    thinking      TEXT,
    session_id    TEXT,
    tool_allowlist TEXT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id              INTEGER PRIMARY KEY,
    run_id          TEXT NOT NULL,
    phase_id        TEXT,
    agent           TEXT,
    attempt         INTEGER,
    call_id         TEXT NOT NULL,
    tool_name       TEXT,
    args_json       TEXT,                     -- sanitized
    started_at      TEXT,
    ended_at        TEXT,
    duration_ms     INTEGER,
    completion      TEXT NOT NULL,            -- complete | incomplete
    ok              INTEGER,                  -- NULL when unknown
    error           TEXT,
    result_ref      TEXT,
    UNIQUE (run_id, call_id)
);

CREATE TABLE IF NOT EXISTS code_operations (
    id           INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL,
    phase_id     TEXT,
    operation_id TEXT NOT NULL,
    name         TEXT NOT NULL,
    argv_json    TEXT,
    cwd          TEXT,
    duration_ms  INTEGER,
    return_code  INTEGER,
    passed       INTEGER,
    stdout_ref   TEXT,
    stderr_ref   TEXT,
    stdout_hash  TEXT,
    stderr_hash  TEXT
);

CREATE TABLE IF NOT EXISTS agent_usage (
    id            INTEGER PRIMARY KEY,
    run_id        TEXT NOT NULL,
    phase_id      TEXT,
    agent         TEXT NOT NULL,
    attempt       INTEGER NOT NULL,
    tokens_json   TEXT NOT NULL,
    cost_json     TEXT NOT NULL,
    currency      TEXT,
    cost_source   TEXT,
    completeness  TEXT NOT NULL,              -- unknown | partial | complete
    UNIQUE (run_id, agent, attempt)
);

CREATE TABLE IF NOT EXISTS requirements (
    id           INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL,
    req_id       TEXT NOT NULL,
    text         TEXT NOT NULL,
    phase_id     TEXT,
    gate         TEXT,
    verifier     TEXT,
    status       TEXT NOT NULL,               -- verified | blocked
    blocker      TEXT,
    evidence_json TEXT,
    UNIQUE (run_id, req_id)
);
