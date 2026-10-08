# Self-compaction verification — 2026-09-25

## Current record — 2026-09-30

Refreshed after the uncommitted API lease and session-lookup changes in `api.py` and `test_api.py`. This section is the current SHA and test count. Sections below are the 2026-09-25 and 2026-09-26 record and still say 63 tests. `verify.py` was not re-run on 2026-09-30 because it rewrites logs outside the two files this refresh is allowed to change. The running LaunchAgent was not restarted. Nothing was committed.

| Item | Result |
| --- | --- |
| `extensions/self-compact/self-compact.ts` SHA-256 | `8c54a26da482f8e60c05e4860723a09175d1464dd940b399e0eab78cf7402bfd` |
| `bun test extensions/self-compact/self-compact.test.ts` | Exit 0; **64 passed, 0 failed**, 128 `expect()` calls, one file. Bun 1.4.0. |
| `python3 extensions/self-compact/test_api.py -v` | Exit 0; **6 passed, 0 failed**, 3.054s. Re-run against the landed `api.py`. |

The TypeScript SHA-256 was recomputed from the working tree and matches the pin carried from the prior self-compact.ts check. `verification/results.json` stores that hash, the current `self-compact.test.ts`, `api.py`, and `test_api.py` hashes, and these counts. Prompt-file hashes were recomputed and are unchanged. The `checks` array in that JSON is still the 2026-09-26 `verify.py` snapshot.

The implementation plan was saved at
`self-compact/plans/2026-09-25-standalone-compaction.md` before this session's code
changes. An older untracked extension and plan already existed; this work completed
and corrected that implementation. `prompt.plan` contained an unfinished outline,
so there was no executable `/plan` command to invoke. Its requested plan/build/verify
sequence was carried out explicitly.

All changes and verification artifacts are inside `/Users/evanmotovich/fusion-harness`.
No file contents under `specs/` or `apps/` were read. Unrelated dirty files were left
alone. Nothing was committed, pushed or deployed.

## Final checks

Full focused verification command (exit **0**):

```bash
PI_AGENT_PACKAGE=/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent \
TSC_JS=/Users/evanmotovich/.bun/install/cache/typescript@5.9.3@@@1/lib/tsc.js \
python3 extensions/self-compact/verification/verify.py
```

| Check | Result |
| --- | --- |
| `bun test extensions/self-compact/self-compact.test.ts` | Exit 0; **63 passed, 0 failed**, 124 assertions, one file. |
| TypeScript 5.9.3 strict no-emit check against installed Pi declarations | Exit 0. |
| Real Pi 0.84.4 loader/session, defaults | Exit 0; exactly one extension, one summary, automatic continuation. |
| Percentage flags: 20% / 50% / +10% | Exit 0; resolved 200k / 500k / 600k. |
| Token flags with plural aliases: 100k / 200k / +50k | Exit 0; markers 10% / 20% / 25% on a 1M window. |
| Mixed flags: 250k / 35% / +50k | Exit 0; resolved 250k / 350k / 400k. |
| Zero buffer | Exit 0; warning and force coincide, `|` rendered. |
| Literal `compact-prompt=EXACT_LITERAL` | Exit 0; provider receives that exact system prompt; saved note is separate. |
| Invalid threshold | Exit 0 for rejection assertion; invalid config is displayed and tool execution is blocked. |
| Very low thresholds: 10 / 20 / +10 tokens | Exit 0; one summary, continuation, then explicit automatic-compaction pause because retained context exceeds cutoff. |
| Isolated `pi ... -e .../self-compact.ts --help` | Exit 0; all four flags and two aliases present. |

`verification/results.json` contains exact argv/exit results and SHA-256 hashes of the
implementation, tests and prompt files. `verification/unit.txt`, `runtime-0.txt`
through `runtime-7.txt`, `types.txt` and `cli-help.txt` hold outputs.

The runtime probe uses the actual installed extension loader, schema/tool execution,
Pi session entries, custom summary hook, cut point, and resumed agent. Its deterministic
in-process provider asserts prompt precedence, saved note, persisted tool result,
one summary, and summary visibility after continuation. No remote model is called.

## Terminal check

Launched Pi in a PTY, with an isolated agent directory and only this extension:

```bash
PI_CODING_AGENT_DIR=/Users/evanmotovich/fusion-harness/extensions/self-compact/verification/.cli \
pi --no-extensions --no-skills --no-prompt-templates --no-themes \
  --no-context-files --no-session \
  -e /Users/evanmotovich/fusion-harness/extensions/self-compact/self-compact.ts \
  --provider anthropic --model claude-sonnet-4-5 \
  --compact-soft-at 20% --compact-at 50% --compact-buffer 10%
```

Selected trust for this session only. Observed the real terminal widget:

```text
self-compact [----/-----!-!-------] [0% used] soft 20% (200000) · warning 50%
(500000) · force 60% (600000)
OK
```

Exited using Ctrl+D, exit 0, without submitting a model prompt. Pi emitted an optional
`fd` download warning (`fetch failed`) in the isolated config. It did not prevent
extension loading or widget rendering. No global config or tool installation changed.
Cache/occupied cells and all three levels are covered by deterministic rendering and
lifecycle tests; the PTY check verifies initial widget placement and threshold display.

## Failures found and fixed

- The initial extremely-low-threshold runtime probe repeatedly compacted because its
  generated summary still exceeded the configured hard cutoff. Stopped that owned test
  process, added a guard requiring context relief before another automatic attempt,
  and reran the same runtime case successfully. Explicit retry remains available.
- Strict typing caught a missing terminal `return` in the parser and outdated session
  event names. Pi 0.84 emits `session_start` with `reason: new/resume/fork`; state reset
  now uses that public event. Final strict check passes.
- The first verification-script import used CommonJS resolution against an ESM-only
  package export. Corrected the fixture import; all runtime variants pass.

## Limits

No paid/live remote-provider compaction was performed, so provider quality, latency,
actual cache billing and multi-hour autonomous behavior are not measured here. The
summary uses the current Pi model and its configured authentication when launched
normally. Compaction is lossy; Pi retains its normal recent-context cut point.
A deliberately unusable threshold can require changing launch settings or explicitly
retrying after the automatic guard pauses. There are no remaining failures in the
focused checks above. The repository-wide suite was not run.

## Follow-up: directory launch fixed — 2026-09-26

Reproduced the user's directory command in RPC startup mode: `pi -e
./extensions/self-compact/ --mode rpc` (with isolated config and discovery disabled)
exited **1** with `Cannot find module .../extensions/self-compact`.
`--help` alone hid this load failure and exited 0; help output is not startup proof.

Added `index.ts` forwarding the standalone extension's default export. Actual Pi
RPC startup now passes for both `./extensions/self-compact/` and the explicit
`self-compact.ts` file. Each returned successful `get_commands`, included the
`self-compact` command, produced empty stderr, and exited **0** after stdin closed.
Evidence: `verification/directory-launch-after.json`.

The real-Pi offline compaction-and-resume probe also passed through the directory
entry point (exit **0**, one loaded extension, one summary, automatic continuation,
zero extension errors):

```bash
PI_AGENT_PACKAGE=/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent \
SELF_COMPACT_EXTENSION=extensions/self-compact \
node extensions/self-compact/verification/runtime-smoke.mjs
```

Those isolated checks missed a normal-discovery conflict; the index.ts approach
was superseded by the correction below.

## Correction: duplicate registration with normal discovery — 2026-09-26

Reproduced the exact reported duplicate tool and six flag errors, exit 1, with
normal user configuration. Fusion Harness is installed as a global Pi package;
the new index.ts was discovered in addition to the explicit directory argument.
Evidence: `verification/normal-discovery-before.json`.

Removed our index.ts and added package.json with main `./self-compact.ts`. Explicit
directory imports work without opting into Pi's index-based auto-discovery.
Global settings and other extension source files were not changed.

Verified both directory and file paths with normal discovery, using RPC
`get_commands` and flags `--no-session --no-context-files`: each returned exactly
one self-compact command, empty stderr and exit 0. Evidence:
`verification/normal-discovery-after.json`.

Also ran the exact interactive command `pi -e ./extensions/self-compact/` with
normal user settings and no isolation flags: Pi 0.84.4 opened with the self-compact
widget and OK status. The selected 272k model displayed scaled defaults
153000/214200/244800 tokens. Closed with Ctrl+D, exit 0; no model prompt submitted.

Reran the focused Bun suite: 63 passed, 0 failed, 124 assertions. Reran actual-Pi
offline compact-and-resume through the directory: one extension, one summary,
resumed true, no extension errors, exit 0. No live-provider compaction claim.

## Current checkout recheck — 2026-09-26

Reran `PI_AGENT_PACKAGE=/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent TSC_JS=/Users/evanmotovich/.bun/install/cache/typescript@5.9.3@@@1/lib/tsc.js python3 extensions/self-compact/verification/verify.py` from the repository root. Exit 0: 63 tests passed, 0 failed, 124 assertions; strict TypeScript passed; all eight actual-Pi offline runtime variants and CLI flag discovery passed. `verification/results.json` and the adjacent logs were refreshed by that run.

Reran `pi -e ./extensions/self-compact/ --no-session --no-context-files --mode rpc` with normal discovery. Exit 0; startup emitted the self-compact widget with `OK` and scaled 153000/214200/244800 token thresholds on the selected 272k model. No model prompt was submitted in this startup check. No implementation change was needed.
