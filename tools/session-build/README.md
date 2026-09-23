# Local session corpus

`session_build.py` builds a private, offline SQLite FTS5 index of coding-agent
conversations on this Mac. Python 3 and SQLite FTS5 are the only requirements.

```sh
python3 tools/session-build/session_build.py index --json
python3 tools/session-build/session_build.py coverage --json
python3 tools/session-build/session_build.py search --json --limit 8 'agent layout'
python3 tools/session-build/session_build.py brief --json --limit 8 'build a useful coding agent system'
python3 tools/session-build/session_build.py brief --json --include-agent-digests 'agent digests'
```

Put `--db /absolute/path.sqlite` before the command to choose another index.
The default is `~/.local/share/fusion-harness/session-build.sqlite`, created
with mode `0600` under a `0700` parent, with every write transaction —
including the transient rollback journal — scoped by a private `0077` umask.
Indexing is incremental by file size and modification time (plus the Hermes
WAL). A same-size copy with a restored mtime is skipped as unchanged; that is
a documented limitation of the fingerprint. The database stays on this
machine; the script makes no network calls.

## Response schema

Every JSON response carries `schema_version: 1`. A hit has `source`, `path`,
`ordinal`, `session_id`, `role`, `actor_origin`, `excerpt`, and a finite
`score`. Coverage reports per-lane `discovered_files`, `indexed_files`,
`parsed_events`, `indexed_messages`, `excluded_events`, `parse_errors`,
`source_errors`, `errors`, `truncated_messages`, and a `status` of `absent`,
`indexed`, or `partial`. `parse_errors` counts malformed records;
`errors`/`source_errors` count files that failed wholesale (with sanitized
detail in the `errors` list, bounded to 500 bytes after redaction). Coverage
compares the database against a fresh discovery pass: after deleting or moving
source files, run `index` again to reconcile — stale rows surface as
`indexed_files` above `discovered_files` and a non-`indexed` status until then.

## Robustness and limits

Malformed input never aborts a run. Non-object JSON lines, non-dict `message`
or `payload` values, oversized lines (over 4 MiB), and non-scalar session ids
are counted per line as `excluded` plus `parse_errors`; the rest of the file,
its lane, and the run continue. One giant line is drained bounded — it can
neither exhaust memory nor desynchronize line ordinals.

Byte ceilings, all UTF-8 and truncation-safe: stored text per message or digest
is capped at 256 KiB measured after redaction (`truncated_messages` in
coverage counts the cuts); queries and query echoes at 4 KiB; hit excerpts at
420 characters; brief text at 10,000 bytes; surfaced error detail at 500
bytes. A brief carries at most eight hits.

## Redaction and privacy

Common API-key/token patterns are redacted before text enters `documents` and
the FTS index — storage, not just display. Redaction is applied again to
excerpts, query echoes, and errors as defense in depth, so a planted secret is
absent from storage, search, and briefs. Pattern matching cannot prove the
absence of every secret; keep the DB and brief output private.

Displayed and outbound paths are sanitized: paths under the home directory
become `~/...`, and the username never appears elsewhere in a displayed path.
Storage keeps canonical absolute paths as private local state. Vault digest
session ids use the sanitized path form because they travel in hits.

## Sources and attribution

Raw sources are Claude Code project JSONL (including `subagents/`), Codex
rollout JSONL, Pi sessions JSONL, and Hermes `state.db` opened read-only.
Claude and Codex history JSONL provide user prompts only when the matching
transcript is absent — deduplicated by filename stems, trailing-UUID Codex
names, and every session id actually observed inside transcripts. Observed ids
persist per source, so suppression survives incremental runs that skip
unchanged files. History entries without their own session id get a
per-entry key; they never inherit the previous entry's session and never
collapse into one another. The second-brain `sessions/**/*.md` digests are
indexed as a separate `vault_digest` synthesis lane with bounded reads; they
are not counted as raw messages and have `actor_origin=actor_unknown`. Tool
output, tool calls, system/developer messages, and wrapper text are excluded
from raw sources.

Top-level Claude Code and Codex sessions have `actor_origin=human_direct`.
Delegated sessions have `actor_origin=delegated_agent` — Claude via the
`subagents/` path, `agentId`, or `isSidechain`; Codex only via a truthy
`source.subagent` marker (a present-but-null marker proves nothing); their
user-role messages are agent task prompts, not attributed to Evan. Pi headers
do not prove who initiated a session, so Pi sessions are `actor_unknown` —
including headerless or truncated files — unless the path or cwd explicitly
marks a delegated workspace. Hermes sessions without a parent are also
`actor_unknown`. Briefs rank direct user turns before assistant turns, direct
conversations ahead of delegated messages and derived digests, include a
second source family when available, and omit automated `sessions/agents/`
digests unless `--include-agent-digests` is passed. Search deduplicates by
session and includes a sanitized source path and JSONL line number or Hermes
message id.

`INDEX_VERSION` is bumped whenever filtering, redaction, attribution, or
truncation semantics change, forcing every source row to rebuild under the
new rules.

Coverage names other discovered agent products whose local transcript bodies
have not been verified (Cursor, Claude Desktop, ZCode, OpenCode, Grok) and
does not count SQLite projections of Codex rollouts as additional sessions.

Run focused fixtures with:

```sh
python3 -m unittest discover -s tools/session-build -p 'test_*.py' -v
```

Tests use temporary fixtures only; they never index or inspect real session
files.
