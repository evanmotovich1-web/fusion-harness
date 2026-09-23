import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import session_build as sb


def write_jsonl(path, objects):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(obj) + "\n" for obj in objects))


class SessionBuildTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "private" / "index.sqlite"
        self.conn = sb.connect(self.db)
        self.addCleanup(self.conn.close)
        self.roots = {
            "claude": str(self.root / "claude" / "**/*.jsonl"),
            "codex": str(self.root / "codex" / "**/*.jsonl"),
            "pi": str(self.root / "pi" / "**/*.jsonl"),
            "claude_history": str(self.root / "claude-history.jsonl"),
            "codex_history": str(self.root / "codex-history.jsonl"),
            "hermes": str(self.root / "state.db"),
            "vault_digest": str(self.root / "vault" / "**/*.md"),
        }

    def test_claude_child_and_history_fallback(self):
        write_jsonl(self.root / "claude" / "session-one.jsonl", [
            {"type": "user", "sessionId": "session-one", "message": {"content": "Evan asks for agent layout"}},
            {"type": "assistant", "sessionId": "session-one", "message": {"content": [{"type": "text", "text": "I will build the layout"}, {"type": "tool_use", "input": "SECRET_TOOL"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "SECRET_RESULT"}]}},
        ])
        write_jsonl(self.root / "claude" / "subagents" / "child.jsonl", [
            {"type": "user", "sessionId": "session-one", "message": {"content": "Review agent layout"}},
            {"type": "assistant", "sessionId": "session-one", "message": {"content": "Layout review complete"}},
        ])
        write_jsonl(self.root / "claude-history.jsonl", [
            {"sessionId": "session-one", "display": "duplicate prompt"},
            {"sessionId": "missing-session", "display": "fallback only prompt"},
        ])
        sb.index(self.conn, self.roots)
        docs = self.conn.execute("SELECT session_id,role,actor_origin,text FROM documents ORDER BY id").fetchall()
        self.assertEqual(len(docs), 5)
        self.assertFalse(any("SECRET" in d[3] or "duplicate" in d[3] for d in docs))
        self.assertEqual({d[2] for d in docs if "Review agent" in d[3]}, {"delegated_agent"})
        self.assertEqual({d[2] for d in docs if "Evan asks" in d[3]}, {"human_direct"})
        self.assertEqual({d[2] for d in docs if "fallback only" in d[3]}, {"evan_history_fallback"})
        self.assertEqual(len(sb.search(self.conn, "layout", 10)), 2)

    def test_codex_and_pi_only_user_assistant_text(self):
        write_jsonl(self.root / "codex" / "rollout-123.jsonl", [
            {"type": "session_meta", "payload": {"id": "123", "source": {"subagent": {"thread_spawn": {}}}}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Inspect provider boundary"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Boundary inspected"}]}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "output": "PRIVATE_OUTPUT"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "[external_agent_tool_result] PRIVATE_WRAPPED"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "PRIVATE_SYSTEM"}]}},
        ])
        write_jsonl(self.root / "pi" / "session.jsonl", [
            {"type": "session", "id": "pi-id"},
            {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Build Pi workflow"}]}},
            {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Workflow built"}]}},
            {"type": "message", "message": {"role": "toolResult", "content": [{"type": "text", "text": "PRIVATE_TOOL"}]}},
        ])
        sb.index(self.conn, self.roots)
        docs = self.conn.execute("SELECT lane,actor_origin,text FROM documents").fetchall()
        self.assertEqual(len(docs), 4)
        self.assertEqual({d[1] for d in docs if d[0] == "codex"}, {"delegated_agent"})
        self.assertFalse(any("PRIVATE" in d[2] for d in docs))
        self.assertEqual(sb.coverage(self.conn, self.roots)["lanes"]["pi"]["excluded_events"], 2)

    def test_hermes_parent_attribution_incremental_and_secret_redaction(self):
        source = sqlite3.connect(self.root / "state.db")
        source.executescript("""
          CREATE TABLE sessions(id TEXT, source TEXT, parent_session_id TEXT);
          CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, content TEXT);
          INSERT INTO sessions VALUES('h-main','cli',NULL),('h-child','subagent','h-main');
          INSERT INTO messages VALUES(1,'h-main','user','Plan runtime');
          INSERT INTO messages VALUES(2,'h-child','user','Review runtime');
          INSERT INTO messages VALUES(3,'h-child','assistant','Found token=supersecret1234');
          INSERT INTO messages VALUES(4,'h-main','tool','PRIVATE_TOOL');
        """)
        source.commit()
        source.close()
        first = sb.index(self.conn, self.roots)
        second = sb.index(self.conn, self.roots)
        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(sb.coverage(self.conn, self.roots)["lanes"]["hermes"]["parsed_events"], 4)
        hits = sb.search(self.conn, "runtime", 5)
        self.assertEqual({h["actor_origin"] for h in hits}, {"actor_unknown", "delegated_agent"})
        self.assertNotIn("supersecret1234", sb.brief(self.conn, "token", roots=self.roots)["text"])
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)

    def test_malformed_line_counted_and_source_removed(self):
        file = self.root / "pi" / "bad.jsonl"
        file.parent.mkdir()
        file.write_text("invalid json\n" + json.dumps({"type": "message", "message": {"role": "user", "content": "valid prompt"}}) + "\n")
        sb.index(self.conn, self.roots)
        cov = sb.coverage(self.conn, self.roots)["lanes"]["pi"]
        self.assertEqual((cov["parsed_events"], cov["parse_errors"], cov["indexed_messages"]), (2, 1, 1))
        file.unlink()
        sb.index(self.conn, self.roots)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM documents").fetchone()[0], 0)

    def test_vault_digest_is_derived_not_raw_message(self):
        digest = self.root / "vault" / "project" / "day.md"
        digest.parent.mkdir(parents=True)
        digest.write_text("# Session digest\nThe agent layout was repaired.")
        sb.index(self.conn, self.roots)
        cov = sb.coverage(self.conn, self.roots)
        self.assertEqual(cov["total_indexed_messages"], 0)
        self.assertEqual(cov["total_derived_documents"], 1)
        hit = sb.search(self.conn, "layout")[0]
        self.assertEqual((hit["source"], hit["role"], hit["actor_origin"]),
                         ("vault_digest", "synthesis", "actor_unknown"))

    def test_brief_prefers_direct_conversations_and_diverse_sources(self):
        write_jsonl(self.root / "claude" / "direct.jsonl", [
            {"type": "user", "sessionId": "direct", "message": {"content": "Build blockers proof agents"}},
            {"type": "assistant", "sessionId": "direct", "message": {"content": "The blockers need evidence"}},
        ])
        write_jsonl(self.root / "codex" / "rollout-other.jsonl", [
            {"type": "session_meta", "payload": {"id": "other", "source": "cli"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Proof for coding agents"}]}},
        ])
        for n in range(8):
            digest = self.root / "vault" / "sessions" / "agents" / f"auto-{n}.md"
            digest.parent.mkdir(parents=True, exist_ok=True)
            digest.write_text(("build blockers proof agents " * 20).strip())
        sb.index(self.conn, self.roots)
        result = sb.brief(self.conn, "build blockers proof agents", limit=5, roots=self.roots)
        self.assertEqual({h["source"] for h in result["hits"]}, {"claude", "codex"})
        self.assertEqual({h["actor_origin"] for h in result["hits"]}, {"human_direct"})
        self.assertEqual(len(result["hits"]), 2)
        requested = sb.brief(self.conn, "build blockers proof agents", limit=5, roots=self.roots, include_agent_digests=True)
        self.assertTrue(any("/sessions/agents/" in h["path"] for h in requested["hits"]))

    def test_pi_origin_requires_explicit_delegation_evidence(self):
        write_jsonl(self.root / "pi" / "normal" / "session.jsonl", [
            {"type": "session", "id": "normal", "cwd": "/Users/example/project"},
            {"type": "message", "message": {"role": "user", "content": "Review agent work"}},
        ])
        write_jsonl(self.root / "pi" / "factory-prompt-council-abc" / "session.jsonl", [
            {"type": "session", "id": "child", "cwd": "/private/tmp/factory-prompt-council-abc"},
            {"type": "message", "message": {"role": "user", "content": "Review agent work"}},
        ])
        sb.index(self.conn, self.roots)
        actors = dict(self.conn.execute("SELECT session_id,actor_origin FROM documents"))
        self.assertEqual(actors["pi:normal"], "actor_unknown")
        self.assertEqual(actors["pi:child"], "delegated_agent")

    def test_direct_user_turns_rank_before_assistant_turns(self):
        write_jsonl(self.root / "claude" / "human.jsonl", [
            {"type": "user", "sessionId": "human", "message": {"content": "Build agents with proof"}},
        ])
        write_jsonl(self.root / "claude" / "agent.jsonl", [
            {"type": "assistant", "sessionId": "agent", "message": {"content": "Build agents with proof " * 10}},
        ])
        sb.index(self.conn, self.roots)
        hits = sb.search(self.conn, "build agents proof", limit=2)
        self.assertEqual([h["role"] for h in hits], ["user", "assistant"])

    # ── F1: non-dict top-level JSON lines are counted, never fatal ──
    def test_f1_nondict_json_lines_are_counted_not_fatal(self):
        write_jsonl(self.root / "claude" / "shapes.jsonl", [
            ["array"], 42, "string", None, True,
            {"type": "user", "sessionId": "shapes", "message": {"content": "survivor prompt"}},
        ])
        write_jsonl(self.root / "claude" / "later.jsonl", [
            {"type": "user", "sessionId": "later", "message": {"content": "later prompt"}},
        ])
        result = sb.index(self.conn, self.roots)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["schema_version"], 1)
        cov = sb.coverage(self.conn, self.roots)["lanes"]["claude"]
        self.assertEqual((cov["parsed_events"], cov["parse_errors"], cov["indexed_messages"]), (7, 5, 2))

    # ── F2: nested non-dict shapes are excluded without crashing ──
    def test_f2_nested_nondict_shapes_are_excluded(self):
        write_jsonl(self.root / "claude" / "bad-message.jsonl", [
            {"type": "user", "message": "plain string"},
            {"type": "user", "message": {"content": 123}},
        ])
        write_jsonl(self.root / "codex" / "bad-payload.jsonl", [
            {"type": "response_item", "payload": [1, 2]},
        ])
        write_jsonl(self.root / "pi" / "bad-message.jsonl", [
            {"type": "message", "message": "plain string"},
        ])
        result = sb.index(self.conn, self.roots)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM documents").fetchone()[0], 0)
        cov = sb.coverage(self.conn, self.roots)["lanes"]
        self.assertEqual(cov["claude"]["excluded_events"], 2)
        self.assertEqual(cov["codex"]["excluded_events"], 1)
        self.assertEqual(cov["pi"]["excluded_events"], 1)

    # ── F3: headerless Pi sessions are actor_unknown, never human_direct ──
    def test_f3_pi_without_session_header_is_actor_unknown(self):
        write_jsonl(self.root / "pi" / "headerless.jsonl", [
            {"type": "message", "message": {"role": "user", "content": "orphan prompt"}},
        ])
        sb.index(self.conn, self.roots)
        rows = self.conn.execute("SELECT actor_origin FROM documents").fetchall()
        self.assertEqual(rows, [("actor_unknown",)])

    # ── F4: history dedup uses observed session ids, persisting across runs ──
    def test_f4_history_dedup_uses_observed_session_ids_incrementally(self):
        write_jsonl(self.root / "claude" / "abc.jsonl", [
            {"type": "user", "sessionId": "s1", "message": {"content": "real transcript prompt"}},
        ])
        write_jsonl(self.root / "claude-history.jsonl", [
            {"sessionId": "s1", "display": "history duplicate suppressed"},
            {"sessionId": "s2", "display": "history fallback kept"},
        ])
        sb.index(self.conn, self.roots)
        texts = [r[0] for r in self.conn.execute("SELECT text FROM documents")]
        self.assertTrue(any("real transcript" in t for t in texts))
        self.assertFalse(any("suppressed" in t for t in texts))
        self.assertTrue(any("fallback kept" in t for t in texts))
        second = sb.index(self.conn, self.roots)
        self.assertEqual(second["unchanged"], 2)
        texts = [r[0] for r in self.conn.execute("SELECT text FROM documents")]
        self.assertFalse(any("suppressed" in t for t in texts))

    # ── F5: history entries without ids keep distinct identities ──
    def test_f5_history_entries_without_session_id_stay_distinct(self):
        write_jsonl(self.root / "claude-history.jsonl", [
            {"display": "zeta plan one"},
            {"display": "zeta plan two"},
        ])
        write_jsonl(self.root / "codex-history.jsonl", [
            {"text": "zeta plan three"},
            {"text": "zeta plan four"},
        ])
        sb.index(self.conn, self.roots)
        hits = sb.search(self.conn, "zeta", 10)
        self.assertEqual(len(hits), 4)
        self.assertEqual(len({h["session_id"] for h in hits}), 4)

    # ── F6: secrets are redacted before searchable storage ──
    def test_f6_secrets_redacted_before_searchable_storage(self):
        write_jsonl(self.root / "claude" / "secret.jsonl", [
            {"type": "assistant", "sessionId": "secret", "message": {"content": "found token=supersecret1234 in logs"}},
        ])
        sb.index(self.conn, self.roots)
        stored = self.conn.execute("SELECT text FROM documents").fetchone()[0]
        self.assertNotIn("supersecret1234", stored)
        self.assertIn("[REDACTED]", stored)
        self.assertEqual(sb.search(self.conn, "supersecret1234", 5), [])
        # The redactor consumes the whole token=... match, so "token" is gone;
        # the marker itself is what remains searchable.
        self.assertIn("[REDACTED]", sb.search(self.conn, "REDACTED", 5)[0]["excerpt"])

    # ── F7: displayed paths are sanitized; the username never leaks ──
    def test_f7_displayed_paths_are_sanitized(self):
        self.assertEqual(sb.sanitize_path("/Users/alice/proj/x.jsonl", home="/Users/alice"), "~/proj/x.jsonl")
        self.assertEqual(sb.sanitize_path("/Users/alice", home="/Users/alice"), "~")
        self.assertEqual(sb.sanitize_path("/tmp/alice-lane/x.md", home="/Users/alice"), "/tmp/user-lane/x.md")
        digest = self.root / "vault" / "day.md"
        digest.parent.mkdir(parents=True)
        digest.write_text("quartz milestone")
        not_a_db = self.root / "hermes-target.txt"
        not_a_db.write_text("not a database")
        roots = dict(self.roots, hermes=str(not_a_db))
        sb.index(self.conn, roots)
        hit = sb.search(self.conn, "quartz", 5)[0]
        self.assertEqual(hit["path"], sb.sanitize_path(str(digest)))
        self.assertEqual(hit["session_id"], "vault_digest:" + sb.sanitize_path(str(digest)))
        self.assertNotIn(Path.home().name, hit["path"])
        cov = sb.coverage(self.conn, roots)
        self.assertEqual(cov["errors"][0]["path"], sb.sanitize_path(str(not_a_db)))

    # ── F8: sources.indexed always equals actual documents rows ──
    def test_f8_indexed_counts_match_documents(self):
        write_jsonl(self.root / "claude" / "count.jsonl", [
            {"type": "user", "sessionId": "count", "message": {"content": "   "}},
            {"type": "user", "sessionId": "count", "message": {"content": "real prompt"}},
        ])
        sb.index(self.conn, self.roots)
        rows = self.conn.execute(
            "SELECT s.path, s.indexed, count(d.id) FROM sources s "
            "LEFT JOIN documents d ON d.source_path = s.path GROUP BY s.path").fetchall()
        self.assertTrue(rows)
        for _, indexed, actual in rows:
            self.assertEqual(indexed, actual)

    # ── F9: re-indexing a modified file leaves no ghost FTS rows ──
    def test_f9_modified_file_reindexes_without_ghost_rows(self):
        file = self.root / "pi" / "mod.jsonl"
        file.parent.mkdir(parents=True)
        file.write_text(json.dumps({"type": "message", "message": {"role": "user", "content": "alpha prompt"}}) + "\n")
        sb.index(self.conn, self.roots)
        file.write_text(json.dumps({"type": "message", "message": {"role": "user", "content": "omega prompt"}}) + "\n")
        os.utime(file, (0, 0))  # same byte length, different mtime
        result = sb.index(self.conn, self.roots)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(sb.search(self.conn, "alpha", 5), [])
        self.assertEqual(len(sb.search(self.conn, "omega", 5)), 1)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM documents").fetchone()[0], 1)

    # ── F10: write transactions run under a private umask ──
    def test_f10_private_umask_scoped_and_db_mode(self):
        before = os.umask(0o022)
        try:
            with sb.private_umask():
                current = os.umask(0o077)
                self.assertEqual(current, 0o077)
                os.umask(current)
            self.assertEqual(os.umask(0o022), 0o022)
        finally:
            os.umask(before)
        write_jsonl(self.root / "claude" / "u.jsonl", [
            {"type": "user", "sessionId": "u", "message": {"content": "umask prompt"}},
        ])
        sb.index(self.conn, self.roots)
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)

    # ── F11: vanished vault digests are fully removed ──
    def test_f11_vanished_vault_digest_removed(self):
        digest = self.root / "vault" / "day.md"
        digest.parent.mkdir(parents=True)
        digest.write_text("removable digest")
        sb.index(self.conn, self.roots)
        self.assertEqual(sb.coverage(self.conn, self.roots)["total_derived_documents"], 1)
        digest.unlink()
        sb.index(self.conn, self.roots)
        cov = sb.coverage(self.conn, self.roots)
        self.assertEqual(cov["total_derived_documents"], 0)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM documents").fetchone()[0], 0)
        self.assertEqual(cov["lanes"]["vault_digest"]["indexed_files"], 0)

    # ── F12: a codex subagent marker must be truthy to attribute delegation ──
    def test_f12_codex_subagent_marker_requires_truthy_value(self):
        write_jsonl(self.root / "codex" / "null-marker.jsonl", [
            {"type": "session_meta", "payload": {"id": "nullmark", "source": {"subagent": None}}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "null marker prompt"}]}},
        ])
        write_jsonl(self.root / "codex" / "real-marker.jsonl", [
            {"type": "session_meta", "payload": {"id": "realmark", "source": {"subagent": {"thread_spawn": {}}}}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "real marker prompt"}]}},
        ])
        sb.index(self.conn, self.roots)
        actors = dict(self.conn.execute("SELECT session_id,actor_origin FROM documents"))
        self.assertEqual(actors["codex:nullmark"], "human_direct")
        self.assertEqual(actors["codex:realmark"], "delegated_agent")

    # ── F13: oversized lines are skipped as parse errors; survivors index ──
    def test_f13_oversized_lines_skipped_and_survivors_indexed(self):
        file = self.root / "pi" / "giants.jsonl"
        file.parent.mkdir(parents=True)
        huge = b"x" * (sb.MAX_LINE_BYTES + 10)
        valid = json.dumps({"type": "message", "message": {"role": "user", "content": "giant survivor"}}).encode()
        file.write_bytes(huge + b"\n" + valid + b"\n" + huge)  # last line has no trailing newline
        sb.index(self.conn, self.roots)
        cov = sb.coverage(self.conn, self.roots)["lanes"]["pi"]
        self.assertEqual((cov["parsed_events"], cov["parse_errors"], cov["indexed_messages"]), (3, 2, 1))
        self.assertEqual(len(sb.search(self.conn, "survivor", 5)), 1)

    # ── F14: coverage reports documented drift after deletion, before re-index ──
    def test_f14_coverage_reports_documented_drift_after_deletion(self):
        file = self.root / "claude" / "drift.jsonl"
        write_jsonl(file, [{"type": "user", "sessionId": "drift", "message": {"content": "drift prompt"}}])
        sb.index(self.conn, self.roots)
        file.unlink()
        lane = sb.coverage(self.conn, self.roots)["lanes"]["claude"]
        # Documented drift: discovery sees no files while stale rows remain.
        self.assertEqual(lane["discovered_files"], 0)
        self.assertEqual(lane["indexed_files"], 1)
        self.assertEqual(lane["status"], "absent")

    # ── C4: stored text is bounded, valid UTF-8, and truncation is counted ──
    def test_truncation_bounded_and_counted(self):
        big = "spread " * 40_000  # 280,000 bytes > 256 KiB
        write_jsonl(self.root / "claude" / "big.jsonl", [
            {"type": "user", "sessionId": "big", "message": {"content": big}},
        ])
        sb.index(self.conn, self.roots)
        stored = self.conn.execute("SELECT text FROM documents").fetchone()[0]
        self.assertLessEqual(len(stored.encode("utf-8")), sb.MAX_TEXT_BYTES)
        stored.encode("utf-8")  # raises if truncation broke UTF-8
        cov = sb.coverage(self.conn, self.roots)["lanes"]["claude"]
        self.assertEqual(cov["truncated_messages"], 1)
        result = sb.brief(self.conn, "spread", roots=self.roots)
        self.assertLessEqual(len(result["text"].encode("utf-8")), sb.MAX_BRIEF_TEXT_BYTES)

    # ── C2: schema_version on every response; brief hits are capped at eight ──
    def test_response_schema_version_and_brief_hit_cap(self):
        write_jsonl(self.root / "claude" / "cap.jsonl", [
            {"type": "user", "sessionId": f"cap{n}", "message": {"content": f"capstone prompt {n}"}}
            for n in range(12)
        ])
        sb.index(self.conn, self.roots)
        self.assertEqual(sb.index(self.conn, self.roots)["schema_version"], 1)
        self.assertEqual(sb.coverage(self.conn, self.roots)["schema_version"], 1)
        result = sb.brief(self.conn, "capstone", limit=20, roots=self.roots)
        self.assertEqual(result["schema_version"], 1)
        self.assertLessEqual(len(result["hits"]), sb.BRIEF_MAX_HITS)

    # ── C2: the CLI search response carries schema_version (fixture roots only) ──
    def test_cli_search_response_carries_schema_version(self):
        write_jsonl(self.root / "claude" / "cli.jsonl", [
            {"type": "user", "sessionId": "cli", "message": {"content": "cli smoke prompt"}},
        ])
        sb.index(self.conn, self.roots)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = sb.main(["--db", str(self.db), "search", "--json", "--limit", "3", "smoke"], roots=self.roots)
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn("hits", payload)
        self.assertIn("coverage", payload)


if __name__ == "__main__":
    unittest.main()
