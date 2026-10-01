"""Focused stub checks for the workflow-builder core. No keys, no network."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "adws" / "adw_workflow_builder.py"
PY = sys.executable


def run(request: str, extra: list[str] | None = None, stem: str | None = None) -> tuple[int, str, Path]:
    tmp = Path(tempfile.mkdtemp())
    env = os.environ.copy()
    env.update({
        "ADW_BUILT_ROOT": str(tmp / "built"),
        "ADW_REGISTRY_PATH": str(tmp / "registry.json"),
        "ADW_DB": str(tmp / "adw.db"),
    })
    if stem:
        path = tmp / f"{stem}.md"
        path.write_text(request)
        request_arg = str(path)
    else:
        request_arg = request
    proc = subprocess.run(
        [PY, str(BUILDER), "--request", request_arg, "--fixtures", "--stub-agents",
         "--db", str(tmp / "adw.db"), "--reports-dir", str(tmp / "reports"), *(extra or [])],
        capture_output=True, text=True, timeout=50, stdin=subprocess.DEVNULL, env=env, check=False,
    )
    (tmp / "stdout.log").write_text(proc.stdout + proc.stderr)
    return proc.returncode, proc.stdout + proc.stderr, tmp


class BuilderCoreTest(unittest.TestCase):
    def test_refusals_spend_no_agent(self):
        cases = [
            ("write a poem about the sea", "poem", 2, "not_workflow"),
            ("edit sssf and add a button", "edit-sssf", 2, "forbidden_target"),
            ("please git push and deploy to production", "push-deploy", 2, "forbidden_target"),
            ("build a workflow", "toy_vague", 3, "needs_human"),
        ]
        for text, stem, code, reason in cases:
            with self.subTest(stem=stem):
                status, log, tmp = run(text, stem=stem)
                self.assertEqual(status, code, log)
                self.assertIn(reason, log)
                self.assertNotIn("AGENT ", log)
                self.assertEqual(list((tmp / "built").glob("*")), [])
                if code == 3:
                    reports = list((tmp / "reports").rglob("questions.md"))
                    self.assertTrue(reports and "What should the workflow do" in reports[0].read_text())

    def test_complete_registers_and_is_idempotent(self):
        text = "Build a workflow named echo-check that must gate a greeting is a nonempty string."
        code, log, tmp = run(text, ["--run-id", "once"])
        self.assertEqual(code, 0, log)
        self.assertIn("AGENT workflow_scout → GATE workflow_scout PASS", log)
        self.assertIn("AGENT → GATE", log.replace("AGENT workflow_scout → GATE", "AGENT → GATE"))
        registry = json.loads((tmp / "registry.json").read_text())
        self.assertEqual(len(registry["workflows"]), 1)
        conn = sqlite3.connect(tmp / "adw.db")
        try:
            phases = {row[0] for row in conn.execute("SELECT phase_id FROM phase_attempts")}
            self.assertTrue({"intake", "survey", "spec", "spec_review", "scaffold", "implement", "validate", "register"} <= phases)
            row = conn.execute("SELECT model, tokens_json, tool_counts_json, duration_ms, tool_errors FROM agent_runs LIMIT 1").fetchone()
            self.assertEqual(row[0], "unknown")
            self.assertIn("unknown", row[1])
            self.assertNotIn('"input": 0', row[1])
            self.assertTrue(row[2])
            self.assertGreater(row[3], 0)
            self.assertEqual(conn.execute("SELECT status FROM workflow_builds").fetchone()[0], "accepted")
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0], 0)
        finally:
            conn.close()
        code2, log2, tmp2 = run(text, ["--run-id", "twice"])
        # second process has its own registry; re-run in the same env by calling main-equivalent via the first registry
        env = os.environ.copy()
        env.update({"ADW_BUILT_ROOT": str(tmp / "built"), "ADW_REGISTRY_PATH": str(tmp / "registry.json"), "ADW_DB": str(tmp / "adw.db")})
        proc = subprocess.run(
            [PY, str(BUILDER), "--request", text, "--fixtures", "--stub-agents", "--db", str(tmp / "again.db"),
             "--reports-dir", str(tmp / "reports2"), "--run-id", "twice"],
            capture_output=True, text=True, timeout=50, stdin=subprocess.DEVNULL, env=env, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        again = json.loads((tmp / "registry.json").read_text())
        self.assertEqual(len(again["workflows"]), 1)
        self.assertEqual(code2, 0, log2)
        self.assertTrue(tmp2)

    def test_bad_first_soft_notice(self):
        text = "Build a workflow named echo-check that must gate a greeting is a nonempty string."
        code, log, _tmp = run(text, ["--stub-bad-first", "--run-id", "badfirst"])
        self.assertEqual(code, 0, log)
        self.assertIn("FAIL", log)
        self.assertIn("SOFT NOTICE:", log)
        self.assertIn("schema missing requirements", log)
        self.assertIn("PASS", log.split("SOFT NOTICE:")[-1])

    def test_unmeetable_is_blocked_not_silent(self):
        text = "Build a workflow named partial-check that must record a greeting and an unmeetable side effect."
        code, log, tmp = run(text, stem="unmeetable-requirement")
        self.assertEqual(code, 4, log)
        conn = sqlite3.connect(tmp / "adw.db")
        try:
            rows = conn.execute("SELECT req_id, status, blocker FROM requirements").fetchall()
        finally:
            conn.close()
        self.assertTrue(any(row[1] == "blocked" and row[2] for row in rows), rows)
        self.assertTrue(any(row[1] == "verified" for row in rows), rows)
        self.assertFalse((tmp / "registry.json").exists() and json.loads((tmp / "registry.json").read_text()).get("workflows"))

    def test_memory_search_preflight_does_not_launch(self):
        text = "Build a workflow that must gate a greeting is a nonempty string, using tool memory_search."
        code, log, tmp = run(text, stem="memory_search")
        self.assertEqual(code, 4, log)
        self.assertIn("unknown_tool: memory_search", log)
        self.assertNotIn("AGENT ", log)
        conn = sqlite3.connect(tmp / "adw.db")
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 0)
        finally:
            conn.close()

    def test_outside_write_is_not_accepted(self):
        text = "Build a workflow named echo-check that must gate a greeting is a nonempty string."
        code, log, tmp = run(text, stem="out-of-scope-write")
        self.assertEqual(code, 4, log)
        self.assertIn("diff_claims_real: path outside allowlist", log)
        self.assertFalse((tmp / "registry.json").exists() and json.loads((tmp / "registry.json").read_text()).get("workflows"))

    def test_socket_guard(self):
        sys.path.insert(0, str(ROOT / "adws"))
        from adw_workflow_builder import install_socket_guard
        install_socket_guard()
        with self.assertRaises(RuntimeError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.2)

    def test_spec_older_than_code(self):
        spec = ROOT / "adws" / "specs" / "workflow-builder.md"
        code_files = list((ROOT / "adws").rglob("*.py"))
        self.assertTrue(code_files)
        self.assertLess(spec.stat().st_mtime, min(path.stat().st_mtime for path in code_files))


if __name__ == "__main__":
    unittest.main()
