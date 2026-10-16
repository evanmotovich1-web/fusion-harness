# Automatic repository routing and native OpenCode Team

User-facing entry: visible primary `opencode-team`, command `/oc-team`, and a
simple workspace whose repository defaults to **Auto — let Router choose**.
All existing task modes remain available. `team` is the Deep pipeline with a
repository Router and real native parent/child sessions, not a second pipeline.

## Repository contract

`repo_router.resolve(request, *, context_directory=None, explicit_repo=None,
receipt_dir, workspace_root=None)` returns an object with `status` (`resolved`
or `needs_clarification`), `selected_repo` (absolute Git root or null), `method`,
`candidates`, `question`, and `receipt_path`. Preserve actual Jev model,
confidence, probabilities and usage when semantic selection was used.

Use the installed workspace's existing deadline-bounded discovery implementation.
The installer manifest records `workspace_root`; an environment override is
allowed. No duplicate whole-disk crawler. Collapse worktrees of the same Git
repository into one project candidate. Prefer a matching active native context
or installed workspace for that project, otherwise its canonical checkout.
Validate the actual selected Git root. Respect known retired/read-only projects;
automatic build routing must not revive the retired trading bot.

Resolution order: explicit manual override; unique explicit full path/name in the
task; actual native-project context; then relevant candidate metadata and typed
Jev selection. Metadata is bounded public project-purpose text, never credentials,
raw environment files or private transcripts. Use the existing Jev client via a
new public `jev_bridge.select_repository(...)`, not another HTTP/auth stack.
Uncertain/no-match/multiple-project choices return one concise question and real
candidate choices. No model work or source writes start before resolution.

CLI `--repo auto` (and omitted repo) enables routing. `--routing-context none`
disables cwd inference: the SSSF launcher MUST use this for web tasks, because the
server's own checkout is not the user's intended repo. Native plugin passes its
actual tool-context directory. Existing explicit `--repo PATH` remains supported.
Create the private run receipt before routing; unresolved runs retain a terminal
FAILED report with routing diagnostics and no builder invocation.

## Native team contract

`native_team.NativeTeam(repo, folder, *, server_url=None, parent_session_id=None,
parent_directory=None)` is a context manager. It starts an owned loopback
`opencode serve` only when no existing server is supplied; otherwise it leaves the
existing interactive server alive. It creates or verifies an actual parent session.
`command(role, label, model, prompt, timeout)` creates a fresh child session and
returns an argv to invoke this module's API helper. `finish_child(label, stage)`
checks observed session identity. `abort_active()` and `close()` abort only owned
child sessions and stop only an owned server. `snapshot()` returns native parent,
children, role/model/state/session IDs; no auth values.

Use public session APIs. POST session with `parentID` supports cross-project
children; verified on OpenCode 1.19.0. Stage invocation uses native session-message
API, not CLI subagent fallback. Serialize actual returned text/tool/step parts into
the existing JSONL event shape so evidence and tokens remain inspectable.
`router_note(routing)` creates an honestly labeled Router child and records its
code/Jev decision with `noReply:true`; it does not invent a chat-model inference.
All chat roles still execute in independent sessions with existing permissions.

`team` mode uses these native sessions and invokes the existing Deep engine.
Add CLI `--native-server-url`, `--parent-session`, `--parent-directory` for native
plugin calls. CLI/web calls without them create their own native parent, retained
in OpenCode's session history. Preserve structured team evidence in `report.team`.
Handle cancellation/timeouts by aborting native children, including when attached
to an interactive server; never terminate that interactive server.

## Native plugin and visibility

Install a local plugin exposing `opencode_team`, whose tool context supplies the
real `sessionID` and `directory`; PluginInput supplies `serverUrl`. It invokes the
runtime with those values and `--mode team --repo auto` by default. Runtime entry
must not recursively invoke this tool from a worker. Return actual run/team IDs
and outcomes. Cancellation must stop the owned child run and its native children.

Expose the four existing role agents in autocomplete (`hidden:false`). Preserve
their `mode:all` for old CLI compatibility: installed OpenCode 1.19.0 CLI silently
falls back to its default agent for `mode:subagent`, verified by a live probe.
Team mode's public API transport can address roles directly without that fallback.
The visible Router is read-only and delegates to the actual code/Jev resolver.

The Team view shows real routing, selected repository, role/model/session state
and handoff evidence. Before execution, label roles as configured, not active.
Never claim commits, pushes, merges, model diversity or parallel execution from a
team declaration. Only Builder writes; publishing future task changes still needs
its own authorization. This dispatch authorizes publishing the feature itself.

---
Governed by AGENTS.md — see the repository and target-project instructions.
