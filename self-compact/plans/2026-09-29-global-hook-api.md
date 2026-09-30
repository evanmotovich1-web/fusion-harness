# Global self-compaction hook and API plan

## End state

The existing Pi self-compaction extension loads once in ordinary Pi sessions and in every governed Factory Pi seat. A local API reports session context usage and accepts compaction requests. Requests carry only a session identifier and optional note, not conversation text. Native Pi hooks continue to own the actual summary and recovery behavior. Claude and Codex need separate runtime adapters because Pi's compaction hook cannot control their sessions.

## Steps

1. Preserve the current `self-compact.ts` lifecycle. Add tests for a global load with normal extension discovery and for Factory's `--no-extensions` path. Avoid loading the extension twice.
2. Build a local loopback API with a private token, bounded request bodies, `GET /v1/sessions`, `GET /v1/sessions/{id}`, and `POST /v1/sessions/{id}/compact`. Store only usage, threshold state, command state, and timestamps. The API queues a request; the Pi extension claims it and calls its existing compaction path.
3. Add a small Pi adapter that publishes measured usage from `ctx.getContextUsage()`, polls pending requests while the session is alive, and records success or failure. Keep the extension functional when the API is down.
4. Install the Pi extension globally through the normal Pi discovery directory. In Factory, pin the extension explicitly in the sealed composition so `--no-extensions` seats still load it. Keep Factory's tool and permission gates unchanged.
5. Add Claude and Codex adapters only where their installed runtimes expose measured context usage and a documented compaction operation. Otherwise report those as unsupported instead of claiming universal automatic compaction.
6. Run focused unit tests, a real Pi loader smoke without a paid model, and a Factory argv/composition test. Inspect installed configuration and API status before claiming live coverage.

## Boundaries

No conversation text, API token, or credentials enter API logs. Never infer context usage from message count. No full repository suites or paid provider calls. Work from isolated worktrees and preserve the dirty source checkouts. Do not read `specs/*` or `apps/*`. Global installation follows source checks; no push or Factory live pin without the existing operator gate.
