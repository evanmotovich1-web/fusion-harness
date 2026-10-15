---
description: Independent evidence-backed review without a builder or source edits.
agent: opencode-adw
---

Review the current implementation against these requirements: $ARGUMENTS

Resolve the target repo, then invoke @PYTHON@ @RUNTIME@ run --mode review --repo <target> --request <requirements>. Add a --check only when the user requests that exact check and it is side-effect-free. Read the actual verdict and evidence; state skipped checks. Capture the bounded result. Do not repair during a review-only run.

---
Governed by AGENTS.md — see the target project's instructions.
