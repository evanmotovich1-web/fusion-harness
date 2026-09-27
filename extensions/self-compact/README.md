# Standalone self-compaction

Load this extension in Pi (verified against installed Pi 0.84.4):

```bash
YOUR_WORKING_DIR=/Users/evanmotovich/fusion-harness
cd "$YOUR_WORKING_DIR"
pi -e "$YOUR_WORKING_DIR/extensions/self-compact/self-compact.ts"
```

The shorter directory form also works. Paste this as one line:

```bash
pi -e ./extensions/self-compact/
```

The directory resolves through `package.json`'s `main` entry. Keep it without an
`index.ts` entry: when Fusion Harness is installed as a Pi package, an index would
also be auto-discovered and conflict with the explicit `-e` directory launch.
Both commands above were verified with normal extension discovery enabled.

The agent can call `self_compaction({"note_to_self":"Goal… Completed… Paths… Tests… Next…"})`.
The note is saved in the Pi session before compaction. After tool results are persisted,
Pi compacts and automatically continues from the summary. `/self-compact [note]`
is the manual command and retry path. No other extension is required.

## Thresholds

| Flag | Default | Behavior |
| --- | --- | --- |
| `--compact-soft-at` | `250k` | Optional model-visible heads-up; tools remain available. |
| `--compact-at` | `350k` | Ask the agent to write its note and compact; ordinary tools remain available. |
| `--compact-buffer` | `50k` | Additional window capacity after warning; default force is `400k`. At force, only `self_compaction` may run. |
| `--compact-prompt` | Compaction file below | Exact literal replacement of the summary system prompt. |

The plural spellings `--compactions-soft-at` and `--compactions-at` also work.
Conflicting values across spellings are rejected. Counts accept whole tokens, `k`/`K`,
`m`/`M`, or percentages. A percentage buffer means percentage points of the model
window, not a percentage of the warning threshold. Zero buffer accepts `0`, `0k`,
`0m`, or `0%`. Malformed, nonintegral token, unsafe integer, out-of-order and >90%
hard thresholds are rejected. Invalid settings show an error and block tool execution;
Pi remains open so the user can correct launch settings. The extension does not exit
its embedding application.

On windows too small for 400k, omitted defaults scale proportionally to put force
at 90%. Explicit values retain their meaning and are validated against that window.
The widget shows the actual resolved token thresholds. Model changes re-resolve them.

```bash
# 20% soft, 50% warning, 60% forced
pi -e ./extensions/self-compact/self-compact.ts \
  --compact-soft-at 20% --compact-at 50% --compact-buffer 10%

# On a 1M-token model: 10%, 20%, 25%
pi -e ./extensions/self-compact/self-compact.ts \
  --compact-soft-at 100k --compact-at 200k --compact-buffer 50k

# Default 1M values expressed with mixed units: 250k, 350k, 400k
pi -e ./extensions/self-compact/self-compact.ts \
  --compact-soft-at 250k --compact-at 35% --compact-buffer 50k

# Immediate enforcement at warning
pi -e ./extensions/self-compact/self-compact.ts --compact-buffer 0

# Full replacement of the summary system prompt; note remains separate
pi -e ./extensions/self-compact/self-compact.ts \
  --compact-prompt 'Summarize current goal, completed work, exact paths, test results, and next actions. Do not reinvent completed work.'
```

## Meter and editable prompts

The bar contains 20 cells of 5% each. `#` is measured cached context, `=` is occupied
uncached context, `-` is unused capacity, `/` is soft, `!` is warning/force, and `|`
means warning and force share a cell (including a zero buffer). Markers remain visible
ahead of occupancy and overwrite that cell's fill. The numeric legend is authoritative
when thresholds fall in the same cell. Cached tokens still consume context capacity;
`#` is not a claim that a provider bills those tokens for free.

Example: 40% used, half cached, thresholds at 20/50/60%:

```text
[####/===--!-!-------] 40%
```

Prompts are loaded from the active project directory on each use:

- `.pi/self-compact/USER_SOFT_SELF_COMPACT.md`: optional soft notice.
- `.pi/self-compact/USER_PROMPT_SELF_COMPACT.md`: warning and hard cutoff.
- `.pi/self-compact/USER_PROMPT_COMPACTION_MESSAGE_.md`: replacement summary system prompt.

Notices expand `{{PERCENT}}`, `{{TOKENS}}`, `{{WINDOW}}`, `{{SOFT}}`, `{{WARNING}}`,
and `{{FORCE}}`. Missing/empty files use built-in fallbacks. The literal flag overrides
the compaction file exactly, including whitespace. Notes, previous summaries,
serialized conversation and manual compaction guidance go in the summary user message;
they do not alter that system prompt. The extension preserves Pi's cut point and usage.

At the hard cutoff an idle agent gets one automatic compaction attempt if it has not
requested one. Failure, cancellation or an empty/incomplete summary never falls back
silently to Pi's built-in prompt. Failed compaction retains the saved note and forced
block. Retry with the tool or manual command. Automatic attempts are bounded: if a
successful summary still exceeds the hard cutoff, automatic compaction pauses until
usage drops below warning or an explicit retry occurs. Choose practical thresholds
that leave room for a useful summary and the retained recent conversation.

## Verification

```bash
bun test extensions/self-compact/self-compact.test.ts
PI_AGENT_PACKAGE=/Users/evanmotovich/.local/lib/node_modules/@earendil-works/pi-coding-agent \
  node extensions/self-compact/verification/runtime-smoke.mjs
```

The runtime smoke uses the actual Pi loader, session, tool validation, compaction and
continuation with a deterministic in-process provider. It does not use credentials or
make model network requests. See `VERIFICATION.md` for results, launch variants,
the original loop failure and its fix, terminal evidence, and remaining limits.
