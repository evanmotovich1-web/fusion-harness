#!/usr/bin/env python3
"""Private, offline, incremental index of local coding-agent conversations."""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path.home() / ".local/share/fusion-harness/session-build.sqlite"
# Bump whenever filtering, redaction, attribution, or truncation semantics change
# so every existing source row is rebuilt under the new rules.
INDEX_VERSION = "6"
SCHEMA_VERSION = 1
ROOTS = {
    "claude": "~/.claude/projects/**/*.jsonl",
    "codex": "~/.codex/sessions/**/*.jsonl",
    "pi": "~/.pi/agent/sessions/**/*.jsonl",
    "claude_history": "~/.claude/history.jsonl",
    "codex_history": "~/.codex/history.jsonl",
    "hermes": "~/.hermes/state.db",
    "vault_digest": "~/code/second-brain/sessions/**/*.md",
}
SECRET_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^\s,'\";]{8,}|"
    r"(?:bearer\s+)[A-Za-z0-9._~+/-]{12,})"
)
WRAPPER_RE = re.compile(r"<\s*(system-reminder|local-command-caveat|environment_context|permissions|skills_instructions)\b[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
TOOL_ENVELOPE_RE = re.compile(r"^\s*\[(?:external_agent_tool_call|external_agent_tool_result|tool_call|tool_result)(?:\b|:|\])", re.I)

# Byte ceilings are UTF-8 bytes. Truncation splits on the byte boundary and drops
# any partial trailing code point, so truncated text always stays valid UTF-8.
MAX_TEXT_BYTES = 256 * 1024        # stored text per message/digest, measured AFTER redaction
MAX_LINE_BYTES = 4 * 1024 * 1024   # larger JSONL lines are skipped as parse errors
MAX_QUERY_BYTES = 4 * 1024         # search/brief query and query echo
MAX_BRIEF_TEXT_BYTES = 10_000      # outbound brief text (bridge enforces the same cap)
MAX_ERROR_BYTES = 500              # surfaced per-source error detail
BRIEF_MAX_HITS = 8                 # a brief may carry at most eight hits


def redact(value: str) -> str:
    return SECRET_RE.sub("[REDACTED]", value)


def truncate_utf8(value: str, limit: int) -> tuple[str, bool]:
    raw = value.encode("utf-8", "replace")
    if len(raw) <= limit:
        return value, False
    return raw[:limit].decode("utf-8", "ignore"), True


def excerpt(value: str, limit: int = 420) -> str:
    value = redact(re.sub(r"\s+", " ", value)).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def sanitize_path(value, home: str | None = None) -> str:
    """Display form of a source path: `~/...` under the home directory, and never
    the username. Storage keeps canonical absolute paths; only display and
    outbound surfaces use this form."""
    text = str(value)
    home = home or str(Path.home())
    if text == home:
        return "~"
    if text.startswith(home + os.sep):
        text = "~" + text[len(home):]
    username = Path(home).name
    if username:
        text = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(username) + r"(?![A-Za-z0-9_])", "user", text)
    return text


def text_parts(content) -> list[str]:
    if isinstance(content, str):
        clean = WRAPPER_RE.sub("", content).strip()
        return [clean] if clean and not TOOL_ENVELOPE_RE.match(clean) else []
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("text", "input_text", "output_text"):
                text = part.get("text")
                if isinstance(text, str):
                    out.extend(text_parts(text))
        return out
    return []


def scalar_text(value, fallback: str) -> str:
    """Coerce a record field to a usable identifier, or keep the fallback.
    Non-scalar shapes (dicts, lists, bools) never become session ids."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return fallback


def pi_origin(path: Path, cwd: str = "") -> str:
    # Pi's session header has no human/delegation field. Only explicit child
    # workspace markers justify delegated attribution; everything else is unknown.
    evidence = (str(path) + " " + cwd).lower()
    markers = ("/subagents/", "factory-prompt-council", "-lanes-lane-", "-lanes-builder-contract-")
    return "delegated_agent" if any(marker in evidence for marker in markers) else "actor_unknown"


@contextmanager
def private_umask():
    """Scope every file SQLite creates during a write transaction (including the
    transient rollback journal) to 0600, regardless of the ambient umask."""
    old_umask = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(old_umask)


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with private_umask():
        conn = sqlite3.connect(db)
    os.chmod(db, 0o600)
    with private_umask():
        conn.executescript("""
          PRAGMA journal_mode=DELETE;
          CREATE TABLE IF NOT EXISTS sources (
            path TEXT PRIMARY KEY, lane TEXT NOT NULL, fingerprint TEXT NOT NULL,
            status TEXT NOT NULL, events INTEGER NOT NULL DEFAULT 0,
            indexed INTEGER NOT NULL DEFAULT 0, excluded INTEGER NOT NULL DEFAULT 0,
            parse_errors INTEGER NOT NULL DEFAULT 0, error TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY, source_path TEXT NOT NULL, lane TEXT NOT NULL,
            session_id TEXT NOT NULL, ordinal INTEGER NOT NULL, role TEXT NOT NULL,
            actor_origin TEXT NOT NULL, text TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS docs_source ON documents(source_path);
          CREATE INDEX IF NOT EXISTS docs_session ON documents(session_id);
          CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(text, content='documents', content_rowid='id');
        """)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sources)")}
        if "truncated" not in columns:
            conn.execute("ALTER TABLE sources ADD COLUMN truncated INTEGER NOT NULL DEFAULT 0")
        if "session_ids" not in columns:
            conn.execute("ALTER TABLE sources ADD COLUMN session_ids TEXT NOT NULL DEFAULT '[]'")
        conn.commit()
    return conn


def replace_source(conn, path, lane, fingerprint, records, events, excluded, parse_errors=0, error=None,
                   truncated=0, session_ids=()):
    ids = [r[0] for r in conn.execute("SELECT id FROM documents WHERE source_path=?", (path,))]
    for doc_id in ids:
        conn.execute("INSERT INTO documents_fts(documents_fts, rowid, text) SELECT 'delete', id, text FROM documents WHERE id=?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE source_path=?", (path,))
    inserted = 0
    for session_id, ordinal, role, actor_origin, body in records:
        if not body.strip():
            continue
        cur = conn.execute("INSERT INTO documents(source_path,lane,session_id,ordinal,role,actor_origin,text) VALUES(?,?,?,?,?,?,?)",
                           (path, lane, session_id, ordinal, role, actor_origin, body))
        conn.execute("INSERT INTO documents_fts(rowid,text) VALUES(?,?)", (cur.lastrowid, body))
        inserted += 1
    conn.execute("""INSERT INTO sources(path,lane,fingerprint,status,events,indexed,excluded,parse_errors,error,truncated,session_ids)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                    lane=excluded.lane,fingerprint=excluded.fingerprint,status=excluded.status,
                    events=excluded.events,indexed=excluded.indexed,excluded=excluded.excluded,
                    parse_errors=excluded.parse_errors,
                    error=excluded.error,truncated=excluded.truncated,session_ids=excluded.session_ids,
                    updated_at=CURRENT_TIMESTAMP""",
                 (path, lane, fingerprint, "error" if error else "ok", events, inserted, excluded, parse_errors, error,
                  truncated, json.dumps(sorted(session_ids))))


def fingerprint(path: Path) -> str:
    # Size + mtime (+ Hermes WAL) only: a same-size copy with a restored mtime is
    # skipped as unchanged. Documented limitation of the incremental index.
    s = path.stat()
    mark = f"v{INDEX_VERSION}:{s.st_size}:{s.st_mtime_ns}"
    if path.name == "state.db":
        wal = Path(str(path) + "-wal")
        if wal.exists():
            w = wal.stat()
            mark += f":wal:{w.st_size}:{w.st_mtime_ns}"
    return mark


def iter_lines(path: Path, limit: int = MAX_LINE_BYTES):
    """Yield (ordinal, text, oversized) for each JSONL line, byte-bounded. A line
    whose content exceeds `limit` yields text=None after draining its remainder,
    so one giant line can neither exhaust memory nor desynchronize ordinals."""
    ordinal = 0
    with path.open("rb") as raw:
        while True:
            chunk = raw.readline(limit + 1)
            if not chunk:
                return
            ordinal += 1
            content = chunk[:-1] if chunk.endswith(b"\n") else chunk
            if len(content) > limit:
                while not chunk.endswith(b"\n"):
                    more = raw.readline(limit + 1)
                    if not more:
                        break
                    chunk = more
                yield ordinal, None, True
                continue
            yield ordinal, content.decode("utf-8", "replace"), False


def rows_from_jsonl(path: Path, lane: str, transcript_sessions: set[str]):
    """Returns (rows, events, excluded, parse_errors, observed_session_ids).
    Malformed top-level and nested records are counted and isolated per line —
    never fatal to the file, the lane, or the run."""
    rows = []
    events = excluded = parse_errors = 0
    session_id = path.stem
    observed: set[str] = set()
    # Attribution defaults. Pi headers prove nothing about initiation, so Pi is
    # actor_unknown until an explicit delegated marker appears. Claude Code and
    # Codex top-level sessions are interactively human-driven by design.
    if lane == "pi":
        actor_origin = "actor_unknown"
    else:
        actor_origin = "delegated_agent" if "/subagents/" in str(path) else "human_direct"
    codex_actor = actor_origin
    for ordinal, line, oversized in iter_lines(path):
        events += 1
        if oversized:
            excluded += 1
            parse_errors += 1
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError, RecursionError):
            excluded += 1
            parse_errors += 1
            continue
        if not isinstance(obj, dict):
            excluded += 1
            parse_errors += 1
            continue
        role = None
        body = []
        if lane == "claude":
            typ = obj.get("type")
            if typ in ("user", "assistant"):
                role = typ
                msg = obj.get("message")
                msg = msg if isinstance(msg, dict) else {}
                body = text_parts(msg.get("content"))
                observed_id = scalar_text(obj.get("sessionId"), "")
                if observed_id:
                    session_id = observed_id
                    # Only top-level transcripts suppress history fallbacks.
                    if "/subagents/" not in str(path):
                        transcript_sessions.add(observed_id)
                        observed.add(observed_id)
                if obj.get("agentId") or obj.get("isSidechain") or "/subagents/" in str(path):
                    actor_origin = "delegated_agent"
        elif lane == "codex":
            payload = obj.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if obj.get("type") == "session_meta":
                observed_id = scalar_text(payload.get("id") or payload.get("session_id"), "")
                if observed_id:
                    session_id = observed_id
                    transcript_sessions.add(observed_id)
                    observed.add(observed_id)
                source = payload.get("source")
                # A present-but-empty subagent marker proves nothing.
                if isinstance(source, dict) and source.get("subagent"):
                    codex_actor = "delegated_agent"
            elif obj.get("type") == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    body = text_parts(payload.get("content"))
        elif lane == "pi":
            if obj.get("type") == "session":
                session_id = scalar_text(obj.get("id"), session_id)
                cwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) else ""
                actor_origin = pi_origin(path, cwd)
            elif obj.get("type") == "message":
                msg = obj.get("message")
                msg = msg if isinstance(msg, dict) else {}
                role = msg.get("role")
                if role in ("user", "assistant"):
                    body = text_parts(msg.get("content"))
        elif lane in ("claude_history", "codex_history"):
            raw_id = obj.get("sessionId")
            if not isinstance(raw_id, (str, int, float)) or isinstance(raw_id, bool):
                raw_id = obj.get("session_id")
            # Entries without their own id get a per-entry key; they never stick
            # to the previous entry's session and never collapse together.
            session_id = scalar_text(raw_id, f"{path.stem}:{ordinal}")
            role = "user"
            body = text_parts(obj.get("display") if lane == "claude_history" else obj.get("text"))
            actor_origin = "evan_history_fallback"
            if session_id in transcript_sessions:
                role = None
        if role in ("user", "assistant") and body:
            rows.append((session_id, ordinal, role, codex_actor if lane == "codex" else actor_origin, "\n".join(body)))
        else:
            excluded += 1
    return rows, events, excluded, parse_errors, sorted(observed)


def hermes_rows(path: Path):
    uri = "file:" + str(path) + "?mode=ro"
    source = sqlite3.connect(uri, uri=True)
    try:
        source.execute("PRAGMA query_only=ON")
        sessions = {row[0]: (row[1], row[2]) for row in source.execute("SELECT id,source,parent_session_id FROM sessions")}
        rows = []
        events = excluded = 0
        for msg_id, sid, role, content in source.execute("SELECT id,session_id,role,content FROM messages ORDER BY id"):
            events += 1
            if role not in ("user", "assistant") or not isinstance(content, str):
                excluded += 1
                continue
            source_name, parent = sessions.get(sid, ("unknown", None))
            actor = "delegated_agent" if parent or source_name == "subagent" else "actor_unknown"
            body = "\n".join(text_parts(content))
            if body:
                rows.append((sid, msg_id, role, actor, body))
            else:
                excluded += 1
        return rows, events, excluded, 0
    finally:
        source.close()


def vault_rows(path: Path):
    with path.open("rb") as raw:
        blob = raw.read(MAX_TEXT_BYTES + 1)  # bounded read; the storage funnel truncates after redaction
    body = blob.decode("utf-8", "replace")
    rows = [(sanitize_path(str(path)), 1, "synthesis", "actor_unknown", body)] if body.strip() else []
    return rows, 1, 0 if rows else 1, 0


def discover(roots=ROOTS):
    for lane, pattern in roots.items():
        for path in sorted(glob.glob(os.path.expanduser(pattern), recursive=True)):
            if Path(path).is_file():
                yield lane, Path(path)


# Transcript lanes must finish before history lanes so observed session ids are
# known when fallback entries are parsed. History suppression also persists
# across runs via sources.session_ids for fingerprint-unchanged files.
LANE_PRIORITY = {"claude": 0, "codex": 1, "pi": 2, "hermes": 3, "vault_digest": 4,
                 "claude_history": 5, "codex_history": 6}


def index(conn, roots=ROOTS):
    sources = list(discover(roots))
    sources.sort(key=lambda item: LANE_PRIORITY.get(item[0], 7))
    transcript_sessions = set()
    # A history entry is a fallback only when its full transcript is absent.
    for lane, path in sources:
        if lane == "claude" and "/subagents/" not in str(path):
            transcript_sessions.add(path.stem)
        elif lane == "codex":
            # Codex filenames end in the UUID session id.
            match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})$", path.stem)
            if match:
                transcript_sessions.add(match.group(1))
    processed = unchanged = failed = 0
    for lane, path in sources:
        key = str(path)
        try:
            mark = fingerprint(path)
            previous = conn.execute("SELECT fingerprint,status,session_ids FROM sources WHERE path=?", (key,)).fetchone()
            if previous is not None and previous[0] == mark and previous[1] == "ok":
                try:
                    transcript_sessions.update(json.loads(previous[2] or "[]"))
                except (ValueError, TypeError):
                    pass
                unchanged += 1
                continue
            observed_ids: list[str] = []
            if lane == "hermes":
                rows, events, excluded, parse_errors = hermes_rows(path)
            elif lane == "vault_digest":
                rows, events, excluded, parse_errors = vault_rows(path)
            else:
                rows, events, excluded, parse_errors, observed_ids = rows_from_jsonl(path, lane, transcript_sessions)
            keyed_rows = []
            truncated_count = 0
            for sid, ordinal, role, actor, body in rows:
                namespace = "claude" if lane == "claude_history" else "codex" if lane == "codex_history" else lane
                suffix = "child:" + path.stem if actor == "delegated_agent" and lane == "claude" else sid
                # Storage funnel: redact BEFORE searchable storage, then truncate.
                safe_body, was_truncated = truncate_utf8(redact(body), MAX_TEXT_BYTES)
                if was_truncated:
                    truncated_count += 1
                keyed_rows.append((namespace + ":" + suffix, ordinal, role, actor, safe_body))
            with private_umask(), conn:
                replace_source(conn, key, lane, mark, keyed_rows, events, excluded, parse_errors,
                               truncated=truncated_count, session_ids=observed_ids)
            transcript_sessions.update(observed_ids)
            processed += 1
        except (OSError, sqlite3.Error, ValueError) as exc:
            detail, _ = truncate_utf8(redact(type(exc).__name__ + ": " + str(exc)), MAX_ERROR_BYTES)
            with private_umask(), conn:
                replace_source(conn, key, lane, "error", [], 0, 0, 0, detail)
            failed += 1
    # Remove vanished files, so coverage and search reflect current local sources.
    present = {str(path) for _, path in sources}
    for (old_path,) in conn.execute("SELECT path FROM sources").fetchall():
        if old_path not in present:
            with private_umask(), conn:
                ids = conn.execute("SELECT id,text FROM documents WHERE source_path=?", (old_path,)).fetchall()
                for doc_id, body in ids:
                    conn.execute("INSERT INTO documents_fts(documents_fts,rowid,text) VALUES('delete',?,?)", (doc_id, body))
                conn.execute("DELETE FROM documents WHERE source_path=?", (old_path,))
                conn.execute("DELETE FROM sources WHERE path=?", (old_path,))
    return {"schema_version": SCHEMA_VERSION, "processed": processed, "unchanged": unchanged,
            "failed": failed, "coverage": coverage(conn, roots)}


def coverage(conn, roots=ROOTS):
    lanes = {}
    for lane, pattern in roots.items():
        matches = [p for p in glob.glob(os.path.expanduser(pattern), recursive=True) if Path(p).is_file()]
        row = conn.execute("""SELECT count(*),sum(events),sum(indexed),sum(excluded),sum(parse_errors),sum(status='error'),sum(truncated)
                              FROM sources WHERE lane=?""", (lane,)).fetchone()
        lanes[lane] = {"discovered_files": len(matches), "indexed_files": row[0] or 0,
                       "parsed_events": row[1] or 0, "indexed_messages": row[2] or 0,
                       "excluded_events": row[3] or 0, "parse_errors": row[4] or 0,
                       "source_errors": row[5] or 0,
                       "errors": row[5] or 0,
                       "truncated_messages": row[6] or 0,
                       "status": "absent" if not matches else "indexed" if row[0] == len(matches) and not row[5] else "partial"}
    errors = [dict(path=sanitize_path(path), error=truncate_utf8(redact(error or ""), MAX_ERROR_BYTES)[0])
              for path, error in conn.execute("SELECT path,error FROM sources WHERE status='error' ORDER BY path")]
    return {"schema_version": SCHEMA_VERSION, "lanes": lanes, "errors": errors,
            "unsupported_source_lanes": ["Cursor, Claude Desktop, ZCode, OpenCode, Grok: no separately verified local transcript bodies", "Codex thread_history_1.sqlite and state_5.sqlite: projections, not additional transcripts", "non-JSONL attachments and tool outputs"],
            "total_indexed_messages": sum(v["indexed_messages"] for lane, v in lanes.items() if lane != "vault_digest"),
            "total_derived_documents": lanes.get("vault_digest", {}).get("indexed_messages", 0)}


def source_family(hit):
    return hit["source"].removesuffix("_history")


def search(conn, query, limit=8, include_agent_digests=True):
    query, _ = truncate_utf8(query, MAX_QUERY_BYTES)
    terms = re.findall(r"[\w-]{2,}", query, re.U)[:12]
    if not terms or limit <= 0:
        return []
    expression = " OR ".join('"' + term.replace('"', '') + '"' for term in terms)
    # FTS BM25 alone favors long automated digests. Retrieve each provenance
    # tier separately, then rank direct conversation evidence before synthesis.
    candidates = []
    tiers = (
        ("human_direct", "user", "raw"),
        ("human_direct", "assistant", "raw"),
        ("evan_history_fallback", "user", "raw"),
        ("actor_unknown", "user", "raw"),
        ("actor_unknown", "assistant", "raw"),
        ("delegated_agent", "user", "raw"),
        ("delegated_agent", "assistant", "raw"),
        ("actor_unknown", "synthesis", "digest"),
    )
    for actor, role, source_type in tiers:
        condition = " AND d.lane='vault_digest'" if source_type == "digest" else " AND d.lane!='vault_digest'"
        if source_type == "digest" and not include_agent_digests:
            condition += " AND d.source_path NOT LIKE '%/sessions/agents/%'"
        rows = conn.execute("""SELECT d.source_path,d.lane,d.session_id,d.ordinal,d.role,d.actor_origin,
                             snippet(documents_fts,0,'','',' … ',45) AS preview,
                             bm25(documents_fts) AS rank FROM documents_fts
                             JOIN documents d ON d.id=documents_fts.rowid
                             WHERE documents_fts MATCH ? AND d.actor_origin=? AND d.role=?""" + condition +
                            " ORDER BY rank LIMIT ?", (expression, actor, role, min(max(limit * 40, 160), 1000))).fetchall()
        candidates.extend(rows)
    ranked = []
    seen = set()
    for path, lane, sid, ordinal, role, actor, body, rank in candidates:
        if sid in seen:
            continue
        seen.add(sid)
        score = -rank if isinstance(rank, (int, float)) and math.isfinite(rank) else 0.0
        ranked.append({"source": lane, "path": sanitize_path(path), "ordinal": ordinal, "session_id": sid,
                       "role": role, "actor_origin": actor, "excerpt": excerpt(body), "score": round(score, 5)})
    hits = ranked[:limit]
    if limit > 1 and len(hits) == limit and len({source_family(hit) for hit in hits}) == 1:
        second_family = next((hit for hit in ranked[limit:] if source_family(hit) != source_family(hits[0])), None)
        if second_family:
            hits[-1] = second_family
    return hits


def brief(conn, query, limit=8, roots=ROOTS, include_agent_digests=False):
    limit = max(1, min(limit, BRIEF_MAX_HITS))
    bounded_query, _ = truncate_utf8(query, MAX_QUERY_BYTES)
    hits = search(conn, query, limit, include_agent_digests=include_agent_digests)
    cov = coverage(conn, roots)
    lines = [f"Session evidence for: {excerpt(bounded_query, 120)}", f"Indexed messages: {cov['total_indexed_messages']}"]
    for hit in hits:
        lines.append(f"- [{hit['source']} {hit['actor_origin']} {hit['role']}] {hit['excerpt']} ({hit['path']}:{hit['ordinal']})")
    if not hits:
        lines.append("No matching session evidence found.")
    text, _ = truncate_utf8("\n".join(lines), MAX_BRIEF_TEXT_BYTES)
    return {"schema_version": SCHEMA_VERSION, "query": redact(bounded_query), "text": text, "coverage": cov, "hits": hits}


def main(argv=None, roots=ROOTS):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="private local SQLite index")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("index", "coverage", "search", "brief"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--json", action="store_true")
        if name in ("search", "brief"):
            cmd.add_argument("--limit", type=int, default=8)
            if name == "brief":
                cmd.add_argument("--include-agent-digests", action="store_true", help="include automated sessions/agents/ vault digests")
            cmd.add_argument("query", nargs="?" if name == "brief" else None, default="coding agents" if name == "brief" else None)
    args = parser.parse_args(argv)
    conn = connect(args.db)
    try:
        if args.command == "index":
            result = index(conn, roots)
        elif args.command == "coverage":
            result = coverage(conn, roots)
        elif args.command == "search":
            result = {"schema_version": SCHEMA_VERSION, "query": redact(truncate_utf8(args.query, MAX_QUERY_BYTES)[0]),
                      "hits": search(conn, args.query, args.limit), "coverage": coverage(conn, roots)}
        else:
            result = brief(conn, args.query, args.limit, roots, args.include_agent_digests)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "brief":
            print(result["text"])
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
