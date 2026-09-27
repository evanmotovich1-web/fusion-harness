# Standalone self-compaction implementation plan

Written before implementation in this session. Status: planned.

## Variables and boundaries

- PROJECT_ROOT / YOUR_WORKING_DIR: `/Users/evanmotovich/fusion-harness`.
- PLAN_DIR: `/Users/evanmotovich/fusion-harness/self-compact/plans`.
- PI_AGENT_DOCS_DIR: `/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent/docs` (installed Pi 0.84.4).
- Only change `extensions/self-compact/`, `.pi/self-compact/`, and this plan directory. Preserve existing work elsewhere. Never read `specs/` or `apps/`. Keep verification artifacts and temporary fixtures inside YOUR_WORKING_DIR. No commit, push or deploy.
- The local `prompt.plan` is an unfinished outline; no executable `/plan` command was found. This document supplies the requested plan/build/verify workflow.

## Current evidence

Existing untracked implementation has parsers, defaults, a manual command and mocked tests. It lacks an agent tool and model-visible notices, renders occupied and free cells identically, hides future markers, permits read tools at force, and uses appended instructions instead of a replacement summary system prompt. Installed Pi exposes `session_before_compact`, `modelRegistry.complete`, `convertToLlm`, `serializeConversation`, tool registration, session entries and context usage. Use these public APIs without another extension.

## Resolved contract

1. Register `self_compaction(note_to_self)` with a required nonempty note. Persist the note as a Pi custom entry, schedule compaction after the tool result settles, and resume the agent after successful tool-initiated compaction. Manual `/self-compact [note]` remains available.
2. Canonical flags: `--compact-soft-at`, `--compact-at`, `--compact-buffer`, `--compact-prompt`; keep plural aliases for compatibility. Reject malformed, unsafe integer, fractional token, conflicting alias, out-of-order and over-cap settings. Accept zero buffer including unit forms. Resolve percentages against the active model window. Default 1M thresholds: 250k/350k/400k. On smaller windows scale only omitted defaults to fit a 90% hard limit and validate the result; document this behavior.
3. Soft notice and warning reach the model once per escalation cycle with live values. Ordinary tools remain available until force. At force every ordinary tool is blocked; self_compaction remains available. Recheck usage at tool_call to enforce crossings during turns. Forced idle fallback supports unattended continuation. Failures remain visible; avoid unbounded automatic retry loops.
4. Show exactly 20 five-percent cells: cached `#`, occupied uncached `=`, free `-`, soft `/`, warning/force `!`, coincident warning/force `|`. Always render markers, including ahead of occupancy. Cache is measured display-only, never subtracted from context. Percent/token legends remove cell-rounding ambiguity.
5. Editable prompt files remain at the three requested `.pi/self-compact/` paths. Soft/warning templates get live values. The literal compact flag replaces the summarizer system prompt exactly; otherwise use the compaction file then fallback. Put saved note, previous summary and serialized conversation in the user message, independently of the system prompt. Preserve Pi's cut point, tokensBefore, usage and abort signal. Empty/error/aborted summaries cancel without native fallback silently overriding the chosen prompt.
6. Reset transient state/cache on session/model transitions; avoid stale callbacks and duplicate concurrent compactions. Keep ordinary Pi session history/compaction ownership intact.

## Build steps (execute in order)

1. Repair threshold parsing/default resolution and add boundary tests.
2. Repair the meter and prompt separation; verify 40%/half cached, 20/50/60%, 100k/200k/+50k on 1M, zero buffer, and unknown usage.
3. Add tool, model notices, persistence, enforcement and lifecycle management. Add mocked tests for busy turns, failure/abort, model/session reset and continuation.
4. Implement custom summarization through Pi's public hook and test exact system prompt, file precedence, preserved note/history/cut point/usage and cancellation.
5. Update editable templates and add standalone README with commands and limitations. Run a real isolated Pi loader/CLI probe with no remote provider. If feasible use a local deterministic provider to exercise a real compact-and-continue session without credentials.

## Verification / definition of done

- Run only focused self-compact tests; fix failures and rerun affected checks. Use fixtures under the workdir, not outside it.
- Real installed Pi loads only the target extension; tool and all flags register. Check defaults, percentage, token, mixed-unit, zero-buffer, custom-prompt and invalid configurations.
- Test all meter fixtures and model-visible prompts, full forced tool block, saved note, exact replacement summary prompt, cancellation, concurrency and resumed work.
- Record exact commands, exit codes, test counts and any unverified live-provider/terminal claims in `extensions/self-compact/VERIFICATION.md`.
- All final implementation artifacts remain inside YOUR_WORKING_DIR. The latest task's output confinement overrides older vault-writeback instructions: retain durable findings locally, with no vault mutation during this task.

## Execution record

Status: built and verified in this session. All five build steps completed in the
specified scope. Existing extension/prompt files were updated after this plan was
saved. Added an automatic-loop guard after the low-threshold runtime case exposed
repeated compaction without enough context reduction. Strict checking also corrected
session transition hooks to Pi 0.84's `session_start` reasons.

Final evidence: `extensions/self-compact/VERIFICATION.md` and
`extensions/self-compact/verification/results.json`: 63/63 focused tests, strict
TypeScript check, eight actual-Pi offline runtime variants, CLI flag discovery, and
PTY widget startup. Every final automated check exited 0. Live remote-provider
quality/latency and prolonged autonomous operation remain unmeasured. No unrelated
files, vault notes, commits, or deployments were changed.
