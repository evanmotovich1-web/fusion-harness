---
description: Run a bounded build, explicit checks and a fresh independent review.
agent: opencode-adw
---

Run OpenCode ADW in build mode for this request: $ARGUMENTS

Identify the target repository and appropriate explicit focused checks. Invoke @PYTHON@ @RUNTIME@ run --repo <target> --request <complete request> --check <check command>. Shell-quote each argument. Read the resulting report and handoff. File the factual result with capture --adw-id <id>. Report the actual state and paths. Changes remain uncommitted.

---
Governed by AGENTS.md — see the target project's instructions.
