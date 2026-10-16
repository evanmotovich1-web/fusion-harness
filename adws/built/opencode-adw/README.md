# OpenCode ADW

Open [guide.html](guide.html) for the native commands and workspace workflow. The installed manifest at `~/.config/opencode/opencode-adw-install.json` records the executing runtime and workspace paths. Keep those source checkouts available, or reinstall after moving them.

## Dependencies and installation

Python 3 (standard library only), Git, and an authenticated `opencode` CLI with access to `openai/gpt-6.1-sol`. POSIX is required (`fcntl` and process groups). Context recovery uses the existing Fusion session bridge; capture requires the existing `vault-semantic` CLI and vault. No new memory service is installed.

From this directory:

```sh
python3 install.py --workspace-root /absolute/path/to/sssf
```

The installer writes its native agents, commands, plugin and manifest under `~/.config/opencode`; it preserves unrelated configuration and refuses to overwrite modified/unowned assets. It records this directory’s runtime path. For an explicitly selected runtime, use `--runtime /absolute/path/runtime.py`. Restart OpenCode, open its native agent picker, and select `opencode-team`.

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

From this directory, run the controlled runtime tests:

```sh
python3 -B -m unittest discover -s tests -v
```

Recorded live evidence: [smoke report](file:///Users/evanmotovich/.local/share/opencode-adw/runs/ocadw-live-20261014/report.json), n=1 synthetic run, three arithmetic tests passed, reviewer PASS. This is not a broad quality or speed benchmark.

## Boundaries

The runner never auto-commits, pushes, merges, or deploys. Source publication needs separate user authorization. Shell permissions are not an OS sandbox. Preserve unrelated work and read target-repository instructions. The OpenCode workspace supports Auto routing and manual targets, Team, Deep, build, review and takeover workflows. Recorded status covers this runner’s runs, not a fleet.

---
Governed by AGENTS.md — see the repository’s AGENTS.md and the target project’s instructions.
