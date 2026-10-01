# Desk integration (task 4.b) — 2026-10-01 00:53 UTC

Recipes added to `justfile` (appended after `compound-fusion5`; `fusion-gemini` untouched):

```just
desk-adw PORT="8797":
    python3 adws/server.py --port {{PORT}}

[positional-arguments]
adw-builder *ARGS:
    python3 adws/adw_workflow_builder.py "$@"
```

Start the desk with `just desk-adw` → http://127.0.0.1:8797/ . `adw-builder` passes every
argument through, so the desk's queue files are consumed with the same path the UI wrote.

Live verification below ran against the real `adws/registry.json` (echo-check, validated,
built by 4.a), the real `adws/data/adw.db`, and the real `adws/built/echo-check/`. The
queued request file was removed after the builder consumed it; its verbatim content is
recorded in step 2. An earlier partial verification pass (run id `desk-integration`) proved
the same endpoints; this file records the clean full pass (`desk-integration-2`).

## 1. curl -s http://127.0.0.1:8797/api/workflows  (live registry from 4.a)

```
{
  "schema_version": 1,
  "workflows": [
    {
      "id": "echo-check",
      "name": "Echo Check",
      "version": 1,
      "entrypoint": "adws/built/echo-check/adw_echo_check.py",
      "spec_path": "adws/built/echo-check/config.json",
      "built_at": "2026-10-01T00:52:45+00:00",
      "build_run_id": "desk-integration",
      "status": "validated",
      "acceptance": {
        "requirements_total": 1,
        "verified": 1,
        "blocked": 0
      },
      "source_request": "Build a workflow named echo-check that must gate a greeting is a nonempty string."
    }
  ]
}
```

## 2. curl -s -X POST http://127.0.0.1:8797/api/builds -H 'Content-Type: application/json' -d '{"request": "Build a workflow named echo-check …", …}'

```
{
  "queued": true,
  "file": "/Users/evanmotovich/fusion-harness/adws/queue/20260930-205316-5c7b8500.md",
  "name": "20260930-205316-5c7b8500.md",
  "consume": "python adws/adw_workflow_builder.py --request /Users/evanmotovich/fusion-harness/adws/queue/20260930-205316-5c7b8500.md --fixtures --stub-agents"
}


queue file on disk (/Users/evanmotovich/fusion-harness/adws/queue/20260930-205316-5c7b8500.md):
---
Build a workflow named echo-check that must gate a greeting is a nonempty string.
---
```

## 3. just adw-builder --request adws/queue/20260930-205316-5c7b8500.md --fixtures --stub-agents  (exit 0; last 10 lines)

```
[20:53:16] GATE  builder attempt 1 PASS
[20:53:16] AGENT builder → GATE diff_claims_real PASS
[20:53:17] CODE validate
[20:53:17] CODE validate → GATE fresh_verification PASS
[20:53:17] CODE validate_stamp
[20:53:17] CODE validate_stamp → GATE fresh_verification PASS
[20:53:17] CODE register: echo-check
[20:53:17] CODE register → GATE registry PASS
[20:53:17] DONE accepted exit=0
python3 adws/adw_workflow_builder.py "$@"
```

## 4. curl -s http://127.0.0.1:8797/api/builds  (run desk-integration-2 from the queue-consumed build)

```
{
  "run_id": "desk-integration-2",
  "workflow_id": "echo-check",
  "name": "Echo Check",
  "status": "accepted",
  "reason": "validate green and every requirement verified",
  "request_verbatim": "Build a workflow named echo-check that must gate a greeting is a nonempty string.\n",
  "built_path": "/Users/evanmotovich/fusion-harness/adws/built/echo-check",
  "created_at": "2026-10-01T00:53:17+00:00",
  "run_status": "accepted",
  "acceptance_status": "accepted",
  "agents": [
    {
      "agent": "builder",
      "attempts": 1,
      "gate_passed": true,
      "duration_ms": 1,
      "model": "unknown",
      "thinking": "medium",
      "tools": {
        "read": 1,
        "write": 1
      },
      "tool_calls": 2,
      "tool_errors": 0,
      "incomplete_calls": 0,
      "tokens": {
        "input": "unknown",
        "output": "unknown",
        "cache": "unknown",
        "reasoning": "unknown",
        "total": "unknown"
      },
      "cost": {
        "total": "unknown",
        "currency": "unknown",
        "source": "unknown"
      },
      "stub": true
    },
    {
      "agent": "reviewer",
      "attempts": 1,
      "gate_passed": true,
      "duration_ms": 1,
      "model": "unknown",
      "thinking": "medium",
      "tools": {
        "read": 1,
        "write": 1
      },
      "tool_calls": 2,
      "tool_errors": 0,
      "incomplete_calls": 0,
      "toke

per-agent rollup:
[
  {
    "agent": "builder",
    "attempts": 1,
    "tools": {
      "read": 1,
      "write": 1
    },
    "tool_calls": 2,
    "tool_errors": 0,
    "duration_ms": 1,
    "model": "unknown"
  },
  {
    "agent": "reviewer",
    "attempts": 1,
    "tools": {
      "read": 1,
      "write": 1
    },
    "tool_calls": 2,
    "tool_errors": 0,
    "duration_ms": 1,
    "model": "unknown"
  },
  {
    "agent": "spec_writer",
    "attempts": 1,
    "tools": {
      "read": 1,
      "write": 1
    },
    "tool_calls": 2,
    "tool_errors": 0,
    "duration_ms": 1,
    "model": "unknown"
  },
  {
    "agent": "workflow_scout",
    "attempts": 1,
    "tools": {
      "read": 1
    },
    "tool_calls": 1,
    "tool_errors": 0,
    "duration_ms": 1,
    "model": "unknown"
  }
]
```

## 5. curl -s -X POST http://127.0.0.1:8797/api/launch -H 'Content-Type: application/json' -d '{"id": "echo-check"}'

```
{
  "launched": "echo-check",
  "mode": "stub",
  "exit": 0,
  "duration_ms": 39,
  "reports_dir": "/Users/evanmotovich/fusion-harness/adws/reports/launches/echo-check-20260930-205317"
}

log_tail:
---
CODE intake: build
AGENT greeter → GATE greeting_nonempty PASS
GATE  greeting_nonempty attempt 1 PASS
---
```

## 6. sqlite adws/data/launches.db — phase_attempts rows written by the stub launch

```
[
  {
    "run_id": "generated-stub",
    "phase_id": "p1",
    "phase_name": "greet",
    "kind": "agent",
    "owner": "greeter",
    "attempt": 1,
    "status": "passed",
    "gate_id": "greeting_nonempty",
    "gate_result": "greeting_nonempty passed",
    "model": "unknown"
  },
  {
    "run_id": "generated-stub",
    "phase_id": "p1",
    "phase_name": "greet",
    "kind": "agent",
    "owner": "greeter",
    "attempt": 1,
    "status": "passed",
    "gate_id": "greeting_nonempty",
    "gate_result": "greeting_nonempty passed",
    "model": "unknown"
  }
]
```

## 7. adws/registry.json after the queue-consumed re-build (idempotent: one echo-check entry)

```
{
  "schema_version": 1,
  "workflows": [
    {
      "id": "echo-check",
      "name": "Echo Check",
      "version": 1,
      "entrypoint": "adws/built/echo-check/adw_echo_check.py",
      "spec_path": "adws/built/echo-check/config.json",
      "built_at": "2026-10-01T00:53:17+00:00",
      "build_run_id": "desk-integration-2",
      "status": "validated",
      "acceptance": {
        "requirements_total": 1,
        "verified": 1,
        "blocked": 0
      },
      "source_request": "Build a workflow named echo-check that must gate a greeting is a nonempty string."
    }
  ]
}
```

All checks passed: workflows listed from the live registry; the POSTed request landed
in `adws/queue/` and was consumed by `just adw-builder` (exit 0, accepted); the stub launch
exited 0 with `AGENT greeter → GATE greeting_nonempty PASS` and wrote visible run rows into
`adws/data/launches.db`.
