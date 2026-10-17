# OpenCode ADW

Open [guide.html](guide.html) for the native commands and workspace workflow. The installed manifest at `~/.config/opencode/opencode-adw-install.json` records the executing runtime and workspace paths. Keep those source checkouts available, or reinstall after moving them.

## Dependencies and installation

Python 3 (standard library only), Git, and an authenticated `opencode` CLI with access to `openai/gpt-6.1-sol`. POSIX is required (`fcntl` and process groups). Context recovery uses the existing Fusion session bridge; capture requires the existing `vault-semantic` CLI and vault. No new memory service is installed.

From this directory:

```sh
python3 install.py --workspace-root /absolute/path/to/sssf
```

The installer stages its native agents, commands, plugin and manifest under `~/.config/opencode`; it preserves unrelated configuration and refuses to overwrite modified/unowned assets. It records this directory’s runtime path. For an explicitly selected runtime, use `--runtime /absolute/path/runtime.py`. The operator reports successful V2 installation and a native status tool call on 2.0.32 (see verification limits below); copying assets alone is not proof of tool availability. Do not restart a shared service as part of staging.

## CLI

### Native Team and Auto repository routing

Choose `opencode-team` in OpenCode or run `/oc-team`, then describe the task and
acceptance criteria. The plugin attaches Router, Planner, Test designer, Builder
and Reviewer children to the invoking conversation. Visible members use the
`@opencode-` prefix. Only Builder edits the target repository.

The workspace at <http://127.0.0.1:4617/opencode> defaults to Native Team and Auto
repository selection. Manual repository selection is under Advanced. Routing uses
an explicit target, exact project name/path, genuine native context, or bounded
Jev semantic selection; ambiguity returns one question before building. Web tasks
do not inherit the workspace server's repository. Router displays its actual
code/Jev execution, not a fabricated chat-model call.

CLI equivalent: `python3 runtime.py run --mode team --repo auto --request 'TASK'`.
Supply `--check` for project checks and role-model flags for model selection.
See [TEAM-BUILD.md](TEAM-BUILD.md) for session ownership and routing evidence.

### Deep build with Jev

Choose **Deep build · Jev** at <http://127.0.0.1:4617/opencode>, or use `/oc-deep`.
The runner adds a read-only Planner and independent Test designer before Builder.
It writes executable acceptance tests outside the target repository and freezes
their hashes, then runs those tests, operator checks and a fresh Reviewer.
Jev recommends focus and repair steps through the existing TypeSafe client.
Uncertain valid advice requests one additional independent review per decision
point; it never fabricates higher confidence or overrides failing checks.

`--planner-model` and `--testdesigner-model` select the extra role models.
`--max-repairs` defaults to one and is bounded to zero through two. Generated
tests, all attempts, Jev receipts and consultations stay in the private run folder.
See [DEEP-BUILD.md](DEEP-BUILD.md) for the contract. Extra tokens are spent on
observable plans, tests and bounded corrections; increased token count alone is
not an improvement claim. This mode is installed locally; it requires the current
workspace and a configured TypeSafe connection.

Replace `/absolute/path/to/repo` and the request/check with the intended target and criteria:

```sh
python3 runtime.py run --repo /absolute/path/to/repo \
  --request 'Implement the requested change' --check 'python3 -B -m unittest -v'
python3 runtime.py takeover --repo /absolute/path/to/repo \
  --request 'Continue the requested change' --check 'python3 -B -m unittest -v'
python3 runtime.py run --mode review --repo /absolute/path/to/repo \
  --request 'Review the current implementation against these requirements'
python3 runtime.py status --adw-id ocadw-live-20261014
```

Repeat `--check` for additional checks. Omitted checks are `SKIPPED`. `--timeout` defaults to 180 seconds per subprocess; the runtime itself does not impose a whole-pipeline deadline. `--model` explicitly overrides the default without silent fallback. The SSSF wrapper has a separate whole-pipeline deadline; see its `app_docs/opencode-adw.md`.

Runs save `report.json`, `handoff.md`, events, and process receipts under `~/.local/share/opencode-adw/runs/<id>/`. Build runs execute worker → checks → fresh read-only reviewer → report/handoff. Review mode omits the worker. Worker and reviewer use independent sessions on the same model. PASS requires reviewer evidence and no unresolved findings; the runner checks repository state for reviewer changes.

Capture is an explicit publication step to the existing semantic vault, separate from execution:

```sh
python3 runtime.py capture --adw-id YOUR_RUN_ID
```

It records bounded metadata and a capture receipt, with repeat-success protection. Native command assets request this step after a run. Capture of `ocadw-live-20261014` returned `CAPTURED` in the recorded smoke report.

## Tests and evidence

### V2 compatibility repair state (2026-10-17)

The operator reports the earlier V2 repair installed globally under explicit authorization;
the model-identity correction below is source-only, pending operator reinstall and retry.
The source plugin uses
`@opencode/plugin` / `Plugin.define`, JSON Schema tool registration, `signal`,
and the invoking session's API location (never the plugin's location). The source
native transport uses V2 data envelopes, `/api/session`, asynchronous prompt
admission and context/idle polling, model/agent selection, and interrupt. Linked
children are created at their parent's location, then explicitly moved to the
routed repo and rechecked without changing parentID or permissions. Non-building
isolated 2.0.32 API probes verified this ancestry and movement in both directions.

`runtime.py` uses process cwd instead of removed `run --dir`. Both installer and
runtime select the real executable explicitly (default `~/.opencode/bin/opencode`;
installer `--opencode`, runtime `OPENCODE_ADW_OPENCODE`), never the bootstrap PATH
wrapper. Native persisted V2 message handling has offline regression coverage.
The operator reports successful real worker/reviewer execution in run
`20261017-001112-053bbd3a`, using separate CLI worker/reviewer sessions on
`openai/gpt-6.1-sol`, validating actual CLI/model use, with 241 tests passing.
This does not establish native Team transport build acceptance.

The CLI parser explicitly supports V2 `start` / `finish` lifecycle envelopes
(no `part` required), `text` and `reasoning` (string `part.text`), `tool_use` (completed tool
state without an error), and `error` (always fatal). It also supports the
`step_start` / `step_finish` envelopes used by existing legacy CLI fixtures and
the native transport normalization; these require object parts, with object
`tokens` on `step_finish`. Non-error events require a nonblank `sessionID`;
lifecycle events do not replace required text or relax session independence.
Reasoning is validated and retained in raw events only, never used as answer text,
reviewer JSON, or short human summaries.
Unknown types and malformed supported envelopes fail even alongside valid text.
The raw event stream is retained in `.events.jsonl`, and rejected object
envelopes remain in stage errors. `tests/test_cli_events.py` covers this source
contract, including harmless V2 start/finish envelopes; the tests themselves are
not live CLI receipts. Doctor supports exactly 2.0.32; later versions block.

Real isolated validation passed on 2.0.32: the global staged plugin became active
in both project locations after asynchronous loader initialization. The real V2
SDK catalog exposed `opencode_team`, and its registered executor returned status
with exit code 0 from native sessions in both projects, without model inference.
That isolated evidence alone is not a model-selected tool call or global activation.
Only installer-managed assets and a separate local diagnostic plugin were needed;
no speculative configuration documents remain. No denied SDK/config/vault paths
were reread. The supplied SDK guide and local public OpenAPI were used.
The operator subsequently installed with the existing installer and reports an
actual native `opencode_team` status call for run `20261017-001112-053bbd3a`
returning exit 0, plus live doctor `PROBES_PASSED` in the repository and vault
project locations on 2.0.32. No restart was performed. These operator-supplied
results were not rerun during publication cleanup. The subsequent native Team build
`20261017-002219-e0a6ea34` failed `NATIVE_AGENT_MODEL_MISMATCH` after worker execution.
The operator's metadata-only probe found persisted `openai/gpt-6.1-sol` with an
extra `variant: default`. The source validator now compares provider and model ID
exactly, and variant exactly when present in the internal expected reference,
ignoring unrelated metadata. Public model selection remains `provider/model`;
no per-role variant flags were added. Native Team build acceptance remains unmet
until an operator retry succeeds.

Compatibility tests use `tests/fixtures/opencode-2.0.32-contract.json`, a small
sanitized excerpt of the public API schema observed on 2026-10-16. It retains
the properties and success responses required by `doctor.v2_contract`, with
public schema references, not the complete OpenAPI document. No machine paths,
secrets or raw run receipts are included. Local `compatibility-runs/` diagnostic
artifacts are excluded from publication and are not required distribution files.

Read-only health check after an **operator-performed** OpenCode update:

```sh
python3 doctor.py --opencode "$HOME/.opencode/bin/opencode" \
  --project /absolute/path/to/project-one --project /absolute/path/to/project-two
python3 install.py --check
```

The installer does not select health-check projects: the manifest records
`health_check: null`, an incomplete `health_check_template`, and
`health_check_required_arguments`. Replace both project placeholders with distinct
existing directories before running the template; `--project` is required twice.
Neither `--workspace-root` nor installation implies a runnable or passed check.

Doctor has evidence only for 2.0.32; all other versions require investigation.
It checks CLI flags, required public V2 API shapes and project-scoped loader state, not real native tool
discovery or execution. `PROBES_PASSED` is not end-to-end acceptance. Failed probes
exit nonzero without writes, retries, upgrades, permission changes, reloads, or
service restarts. No update hook was exposed by the inspected `upgrade --help`;
none was installed. Use this manual check after updates rather than assuming an
automatic hook exists. Recovery is deliberately limited to a read-only ownership
preflight. The operator-reported installation and native status call above do
not establish compatibility with arbitrary future updates.

Locally modified or unowned installed assets block installation; never force
overwrite them. Activation is not performed by doctor, and requires no promise
of compatibility with arbitrary future versions.

From this directory, run the controlled runtime tests:

```sh
python3 -B -m unittest discover -s tests -v
```

Recorded live evidence: [smoke report](file:///Users/evanmotovich/.local/share/opencode-adw/runs/ocadw-live-20261014/report.json), n=1 synthetic run, three arithmetic tests passed, reviewer PASS. This is not a broad quality or speed benchmark.

## Boundaries

The runner never auto-commits, pushes, merges, or deploys. Source publication needs separate user authorization. Shell permissions are not an OS sandbox. Preserve unrelated work and read target-repository instructions. The OpenCode workspace supports Auto routing and manual targets, Team, Deep, build, review and takeover workflows. Recorded status covers this runner’s runs, not a fleet.

---
Governed by AGENTS.md — see the repository’s AGENTS.md and the target project’s instructions.
