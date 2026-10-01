# Live desk verification (item 7) — 2026-10-01 05:42 UTC

Started the real entrypoint bounded, curled it, terminated it, and confirmed the
port closed and no process left running:

- launch: `python3 adws/server.py --port 8797` (same command `just desk-adw` expands to;
  `just -n desk-adw` prints `python3 adws/server.py --port 8797`)
- server banner: `adws desk: http://127.0.0.1:8797/  (registry /Users/evanmotovich/fusion-harness/adws/registry.json; db /Users/evanmotovich/fusion-harness/adws/data/adw.db; Ctrl-C to stop)`
- shutdown: SIGTERM, process exited with code -15; a follow-up request to
  127.0.0.1:8797 was refused, and `pgrep -fl adws/server.py` returned nothing.
- no outbound network: every request above is loopback; the seat check runs the local
  `pi auth check --no-refresh --provider google-vertex` (exit code only).

## curl -s http://127.0.0.1:8797/  (first lines)

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workflow Builder Desk</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>Workflow Builder Desk</h1>
  <p id="status" class="muted">Loading…</p>
</header>
<main>
```

The page contains the three status sections: workflows with status pills,
"In progress" (needs human · running · queued), and the display-only "Seats" table.

## curl -s http://127.0.0.1:8797/api/workflows

```json
{
  "schema_version": 1,
  "workflows": [
    {
      "id": "echo-check",
      "name": "Echo Check",
      "version": 1,
      "entrypoint": "adws/built/echo-check/adw_echo_check.py",
      "spec_path": "adws/built/echo-check/config.json",
      "built_at": "2026-10-01T05:40:00+00:00",
      "build_run_id": "echo-check-rebuild",
      "status": "validated",
      "acceptance": {
        "requirements_total": 1,
        "verified": 1,
        "blocked": 0
      },
      "source_request": "Build a workflow named echo-check that must gate a greeting is a nonempty string.",
      "desk_status": "verified"
    }
  ],
  "incomplete": [
    {
      "source": "build",
      "status": "needs_human",
      "run_id": "e2e-vague",
      "workflow_id": null,
      "reason": "needs_human: request does not name a checkable outcome",
      "created_at": "2026-10-01T00:50:21+00:00"
    }
  ],
  "seats": [
    {
      "name": "gemini-oauth",
      "role": "Main",
      "provider_model": "google-vertex/gemini-3.7-flash",
      "stack": ".pi/fusion-harness/model-stack-gemini-oauth.yaml",
      "recipe": "just fusion-gemini",
      "display_only": true,
      "status": "not_ready",
      "checks": {
        "stack_file": true,
        "adc_credentials": false,
        "env_google_cloud_project": false,
        "env_google_cloud_location": false,
        "pi_auth_check": "failed"
      },
      "tokens": "unknown",
      "cost": "unknown",
      "note": "ADC OAuth: gcloud auth application-default login; Vertex is billed. Not configured yet on this machine."
    }
  ]
}
```

## What was actually seen

- **echo-check** (the registered generated workflow): `desk_status` **verified**, derived
  from real registry data — registry status `validated`, acceptance
  {requirements_total: 1, verified: 1, blocked: 0}, built by run
  `echo-check-rebuild` at 2026-10-01T05:40:00+00:00.
- **Gemini OAuth seat**: `status` **not_ready** — real checks this run:
  stack_file=True, adc_credentials=False
  (gcloud ADC login absent), env_google_cloud_project=False,
  env_google_cloud_location=False,
  pi_auth_check=failed. It cannot render `verified` while the
  login is absent; after `gcloud auth application-default login` plus
  `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` in `.env`, a desk refresh recomputes it.
- **Tokens and cost**: the string `"unknown"` everywhere provider data is absent — never 0.
- **Incomplete lane**: 1 item(s) from real state
  (needs_human (e2e-vague)).
- Response scanned: no credential values present (checks expose booleans and the
  provider key name only).
