# OpenCode ADW

Open [guide.html](guide.html) for the native commands and desk workflow. Toolkit [PR #28](https://github.com/evanmotovich1-web/fusion-harness/pull/28) and desk [PR #32](https://github.com/evanmotovich1-web/sssf/pull/32) are merged. The installed manifest records `~/code/fusion-opencode-adw/adws/built/opencode-adw/runtime.py` as the executing copy on this Mac. Keep that source checkout available, or reinstall from the new location after moving it.

## Dependencies and installation

Python 3 (standard library only), Git, and an authenticated `opencode` CLI with access to `openai/gpt-6.1-sol`. POSIX is required (`fcntl` and process groups). Context recovery uses the existing Fusion session bridge; capture requires the existing `vault-semantic` CLI and vault. No new memory service is installed.

From this directory:

```sh
python3 install.py
```

The installer writes only its native agent/command assets and manifest under `~/.config/opencode`; it preserves unrelated configuration and refuses to overwrite modified/unowned assets. It records this directory’s runtime path. For an explicitly selected runtime, use `--runtime /absolute/path/runtime.py`. Restart OpenCode, open its native agent picker, and select `opencode-adw`.

## CLI

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

The runner never auto-commits, pushes, merges, or deploys. This installation’s source publication had separate user authorization. Shell permissions are not an OS sandbox. Preserve unrelated work and read target-repository instructions. The OpenCode desk at <http://127.0.0.1:4617> requires an explicit target repository and supports build launches only. It runs alongside existing desks, with its own SSSF trace data; existing desks were not restarted or replaced. Recorded status covers this runner’s runs, not a fleet.

---
Governed by AGENTS.md — see the repository’s AGENTS.md and the target project’s instructions.
