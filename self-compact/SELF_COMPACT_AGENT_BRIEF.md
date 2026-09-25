# Self-Compact Agent Brief

Use this brief to implement and verify a self-compaction workflow in **Claude Code**, **Codex CLI**, and **Pi** without reading forbidden project areas.

## Scope and safety rules

- Work only inside the current working directory (`YOUR_WORK_DIR`).
- Do not write deliverables outside `YOUR_WORK_DIR`.
- Do not read any file under `<PROJECT_ROOT>/spec` or `<PROJECT_ROOT>/app`.
- If either forbidden read happens by mistake, stop immediately and report it.
- Preserve unrelated user changes.

## Required verification behavior

- Verify a 20-cell progress display where each cell represents 5% of the context window.
- Cached context is rendered as `#` and is free.
- Visible/uncached context is rendered as `-`, `!`, or `!` depending on threshold state.
- For a 1,000,000-token model, token-based launch thresholds should move markers to 10%, 20%, and the configured force threshold exactly.

## Prompt engineering files

The editable prompt files live under:

- `YOUR_WORK_DIR/.pi/self-compact/USER_SOFT_SELF_COMPACT.md` — editable soft heads-up text.
- `YOUR_WORK_DIR/.pi/self-compact/USER_PROMPT_SELF_COMPACT.md` — stronger warning/compaction request text.
- `YOUR_WORK_DIR/.pi/self-compact/USER_PROMPT_COMPACTION_MESSAGE_.md` — replacement for the summary/compaction message.

## Compaction thresholds

All four flags must work:

- `--compactions-soft-at 20%` — optional heads-up; tools remain available.
- `--compactions-at 50%` — ask the agent to write its note and compact without forcing an immediate hard stop.
- `--compact-buffer 10%` — allow ten additional percentage points of model-window buffer before forced compaction.
- `--compact-prompt "..."` — replace the summary system prompt with literal text.

Threshold and buffer inputs must accept:

- whole token counts, e.g. `250000`
- `k` / `K` suffixes, e.g. `250k`, `350K`
- `m` / `M` suffixes, e.g. `1m`
- percentages, e.g. `20%`

Default threshold targets after testing:

- soft: `250k`
- warning: `350K`
- force: `400k`

Use lower amounts during tests so the workflow can be exercised quickly.

## Launch examples

Expected baseline launch:

```bash
pi -e "$YOUR_WORK_DIR/extensions/self-compact/self-compact.ts"
```

Expected default behavior:

- soft at `250k`
- warning at `350K`
- force at `400k`
- launch should prove mixed suffix parsing (`k`, `K`, and plain/percentage values where relevant)

Custom prompt launch example:

```bash
pi -e "$YOUR_WORK_DIR/extensions/self-compact/self-compact.ts" \
  --compact-prompt "summarize current goal, completed work, exact paths, test results, and next action"
```

Threshold launch example:

```bash
pi -e "$YOUR_WORK_DIR/extensions/self-compact/self-compact.ts" \
  --compactions-soft-at 20% \
  --compactions-at 50% \
  --compact-buffer 10%
```

## Agent-specific analysis

### Claude Code

Use Claude Code when editing several source and test files interactively. It should:

1. Read this brief first.
2. Confirm the forbidden read/write paths.
3. Locate the self-compact extension and tests without touching `<PROJECT_ROOT>/spec` or `<PROJECT_ROOT>/app`.
4. Implement flags and prompt-file behavior.
5. Run focused tests with small thresholds.
6. Report exact files changed and exact verification commands.

### Codex CLI

Use Codex CLI when you want a strict terminal-first implementation pass. It should:

1. Start from this brief as the contract.
2. Use shell commands to inspect only allowed paths.
3. Make small, reviewable diffs.
4. Verify parsing for token counts, `k`/`m` suffixes, percentages, and buffer math.
5. Print a concise final proof block with command output summaries.

### Pi

Use Pi when validating the actual extension launch path and compaction UX. It should:

1. Launch the extension through `pi -e ...`.
2. Validate defaults and CLI overrides.
3. Confirm the 20-cell meter behavior.
4. Confirm soft warning, warning compaction request, buffer, and compact prompt replacement.
5. Preserve normal tool availability at the soft threshold.

## Definition of done

- The self-compact extension accepts and applies all four flags.
- Default thresholds are installed as `250k`, `350K`, and `400k`.
- Token, suffix, and percentage parsing is tested.
- The 20-cell meter is verified at 5% increments.
- Prompt-file locations are correct and documented.
- Claude Code, Codex CLI, and Pi each have a clear usage path from this brief.
- No forbidden `spec` or `app` files were read.
