#!/usr/bin/env python3
"""Workflow-builder desk UI — localhost only.

    python adws/server.py [--port 8797]

GET  /                     static UI from adws/ui/
GET  /api/workflows        registry entries (builder-written, unchanged) + derived
                           desk_status (verified|blocked|incomplete from real data),
                           incomplete items (needs_human/running builds + queued
                           requests) and a display-only seats lane (Gemini OAuth)
GET  /api/builds           build rows + per-agent telemetry summary + queued files
GET  /api/builds/<run_id>  one build: phases, per-agent tools/time/model/tokens/cost,
                           tool-call rollups, requirements coverage
POST /api/builds           {"request": "...", "run": false|true} — queues a build request
                           file under adws/queue/ for the builder; run=true also runs the
                           builder on it synchronously, stub mode only
POST /api/launch           {"id": "workflow-id"} — runs a registered workflow
                           with --fixtures --stub-agents, synchronously, bounded

No auth tokens, no external network: the server binds 127.0.0.1, never makes an
outbound connection, and the only mutations are the two POSTs above. Launch and
build runs are stub-only; live switches do not exist here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ADWS = Path(__file__).resolve().parent
if str(ADWS) not in sys.path:
    sys.path.insert(0, str(ADWS))

from builder_modules import registry as registry_mod  # noqa: E402
from builder_modules.paths import ADWS as ADWS_ROOT, ROOT, built_root, default_db, registry_path  # noqa: E402

UI_DIR = ADWS_ROOT / "ui"
DEFAULT_PORT = 8797
BODY_LIMIT = 100_000          # bytes; larger POSTs are refused before parsing
REQUEST_TEXT_LIMIT = 20_000   # chars kept in a queued request file
WF_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
BUILD_TIMEOUT_S = 55          # builder stub run bound (tests use less)
LAUNCH_TIMEOUT_S = 40         # generated-workflow stub run bound


def queue_dir() -> Path:
    return Path(os.environ.get("ADW_QUEUE_DIR", ADWS_ROOT / "queue"))


def launch_reports_dir() -> Path:
    return Path(os.environ.get("ADW_LAUNCH_REPORTS", ADWS_ROOT / "reports" / "launches"))


def launch_db_path() -> Path:
    return Path(os.environ.get("ADW_LAUNCH_DB", ADWS_ROOT / "data" / "launches.db"))


# ── read-side helpers ────────────────────────────────────────────────────────
def _registry_raw() -> dict:
    """registry.json per request, exactly as written by the builder (its only writer).
    A missing or invalid registry is reported, never faked."""
    path = registry_path()
    if not path.is_file():
        return {"schema_version": 1, "workflows": [],
                "note": "registry not written yet — no build has been accepted"}
    try:
        return registry_mod.load(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"schema_version": 1, "workflows": [], "error": f"registry unreadable: {exc}"}


def _desk_status(entry: dict) -> str:
    """Real-data status label for a registry entry. verified only when the registry
    says validated AND every requirement verified AND none blocked."""
    acceptance = entry.get("acceptance") or {}
    total = acceptance.get("requirements_total") or 0
    verified = acceptance.get("verified") or 0
    blocked = acceptance.get("blocked") or 0
    if entry.get("status") == "blocked" or blocked > 0:
        return "blocked"
    if entry.get("status") == "validated" and total > 0 and verified == total and blocked == 0:
        return "verified"
    return "incomplete"


def _incomplete_payload() -> list[dict]:
    """Work-in-progress items from real state only: needs_human build rows, runs still
    marked running (a builder that died mid-run), and queued-but-unconsumed requests."""
    items: list[dict] = []
    seen: set[str] = set()
    conn = _open_telemetry()
    if conn is not None:
        try:
            for row in conn.execute(
                    "SELECT run_id, workflow_id, reason, created_at FROM workflow_builds "
                    "WHERE status='needs_human' ORDER BY id DESC LIMIT 50"):
                if row["run_id"] not in seen:
                    seen.add(row["run_id"])
                    items.append({"source": "build", "status": "needs_human", "run_id": row["run_id"],
                                  "workflow_id": row["workflow_id"], "reason": row["reason"],
                                  "created_at": row["created_at"]})
            for row in conn.execute(
                    "SELECT run_id, workflow_id, started_at FROM runs "
                    "WHERE run_status='running' ORDER BY started_at DESC LIMIT 50"):
                if row["run_id"] not in seen:
                    seen.add(row["run_id"])
                    items.append({"source": "build", "status": "running", "run_id": row["run_id"],
                                  "workflow_id": row["workflow_id"], "reason": "run never finished",
                                  "created_at": row["started_at"]})
        finally:
            conn.close()
    for queued in _queued_payload():
        items.append({"source": "queue", "status": "queued", "file": queued["file"],
                      "reason": queued["request_preview"], "created_at": queued["created_at"]})
    return items


# ── seats: display-only model lanes, status from real local state ───────────
SEAT_AUTH_TTL_S = 30
_seat_auth_cache: dict[str, tuple[float, str]] = {}
_seat_auth_lock = threading.Lock()


def _seat_auth_check(provider: str) -> str:
    """Bounded, cached `pi auth check --no-refresh --provider <p>`. Local check only;
    the result is the exit status alone ('ok' | 'failed' | 'unavailable'). No token
    value is ever read or returned."""
    now = time.monotonic()
    with _seat_auth_lock:
        cached = _seat_auth_cache.get(provider)
        if cached and cached[0] > now:
            return cached[1]
    try:
        proc = subprocess.run(["pi", "auth", "check", "--no-refresh", "--provider", provider],
                              capture_output=True, text=True, timeout=10,
                              stdin=subprocess.DEVNULL, check=False)
        result = "ok" if proc.returncode == 0 else "failed"
    except (OSError, subprocess.TimeoutExpired):
        result = "unavailable"
    with _seat_auth_lock:
        _seat_auth_cache[provider] = (time.monotonic() + SEAT_AUTH_TTL_S, result)
    return result


def _gemini_seat_status() -> dict:
    """Gemini OAuth seat (stack .pi/fusion-harness/model-stack-gemini-oauth.yaml).
    Display-only, never launchable from the desk. Status is recomputed per request;
    'verified' requires EVERY check to hold, so an absent login can never show it.
    Only key NAMES and booleans are used — never credential values."""
    stack = ROOT / ".pi" / "fusion-harness" / "model-stack-gemini-oauth.yaml"
    adc = Path(os.environ.get("ADW_ADC_CREDENTIALS",
                              str(Path.home() / ".config" / "gcloud" / "application_default_credentials.json")))
    project_set = bool(os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip())
    location_set = bool(os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip())
    auth = _seat_auth_check("google-vertex")
    checks = {"stack_file": stack.is_file(),
              "adc_credentials": adc.is_file(),          # existence only, never read
              "env_google_cloud_project": project_set,   # presence only, value never exposed
              "env_google_cloud_location": location_set,
              "pi_auth_check": auth}
    ready = (checks["stack_file"] and checks["adc_credentials"] and project_set
             and location_set and auth == "ok")
    return {
        "name": "gemini-oauth", "role": "Main",
        "provider_model": "google-vertex/gemini-3.7-flash",
        "stack": ".pi/fusion-harness/model-stack-gemini-oauth.yaml",
        "recipe": "just fusion-gemini",
        "display_only": True,
        "status": "verified" if ready else "not_ready",
        "checks": checks,
        "tokens": "unknown", "cost": "unknown",
        "note": "ADC OAuth: gcloud auth application-default login; Vertex is billed. Not configured yet on this machine.",
    }


def workflows_payload() -> dict:
    """Registry entries (builder-written, unchanged) + derived desk_status, plus
    real-state incomplete items and the display-only seats lane."""
    payload = _registry_raw()
    payload["workflows"] = [{**entry, "desk_status": _desk_status(entry)}
                            for entry in payload.get("workflows", [])]
    payload["incomplete"] = _incomplete_payload()
    payload["seats"] = [_gemini_seat_status()]
    return payload


def _open_telemetry() -> sqlite3.Connection | None:
    path = default_db()
    if not path.is_file():
        return None
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _agent_summary(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    """Per agent: attempts, gate outcome, tool rollup from tool_calls (one row per call),
    duration, model, thinking, tokens and cost with 'unknown' preserved."""
    rows = conn.execute(
        "SELECT agent, attempt, gate_passed, duration_ms, model, tokens_json, cost_json, stub "
        "FROM agent_runs WHERE run_id=? ORDER BY agent, attempt", (run_id,)).fetchall()
    calls = conn.execute(
        "SELECT agent, tool_name, ok, completion FROM tool_calls WHERE run_id=?", (run_id,)).fetchall()
    thinking = {r["agent"]: r["thinking"] for r in conn.execute(
        "SELECT owner AS agent, thinking FROM phase_attempts WHERE run_id=? AND kind='agent'", (run_id,))}
    rollup: dict[str, dict] = {}
    for call in calls:
        agent = call["agent"] or "?"
        entry = rollup.setdefault(agent, {"tools": {}, "tool_calls": 0, "tool_errors": 0, "incomplete": 0})
        entry["tool_calls"] += 1
        if call["tool_name"]:
            entry["tools"][call["tool_name"]] = entry["tools"].get(call["tool_name"], 0) + 1
        if call["ok"] == 0:
            entry["tool_errors"] += 1
        if call["completion"] == "incomplete":
            entry["incomplete"] += 1
    by_agent: dict[str, list] = {}
    for row in rows:
        by_agent.setdefault(row["agent"], []).append(row)
    summary = []
    for agent, attempts in by_agent.items():
        last = attempts[-1]
        try:
            tokens = json.loads(last["tokens_json"] or "null")
        except json.JSONDecodeError:
            tokens = None
        try:
            cost = json.loads(last["cost_json"] or "null")
        except json.JSONDecodeError:
            cost = None
        roll = rollup.get(agent, {"tools": {}, "tool_calls": 0, "tool_errors": 0, "incomplete": 0})
        summary.append({
            "agent": agent,
            "attempts": len(attempts),
            "gate_passed": bool(last["gate_passed"]),
            "duration_ms": sum(a["duration_ms"] or 0 for a in attempts) or None,
            "model": last["model"] or "unknown",
            "thinking": thinking.get(agent) or "unknown",
            "tools": roll["tools"],
            "tool_calls": roll["tool_calls"],
            "tool_errors": roll["tool_errors"],
            "incomplete_calls": roll["incomplete"],
            "tokens": tokens,
            "cost": cost,
            "stub": bool(last["stub"]),
        })
    return summary


def _queued_payload() -> list[dict]:
    directory = queue_dir()
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(errors="replace")
        out.append({"file": path.name, "created_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime)),
            "request_preview": " ".join(text.split())[:160], "size": len(text)})
    return out


def builds_payload() -> dict:
    conn = _open_telemetry()
    if conn is None:
        return {"builds": [], "queued": _queued_payload(),
                "note": "no telemetry db yet — run the builder once"}
    try:
        builds = []
        for row in conn.execute(
                "SELECT b.run_id, b.workflow_id, b.name, b.status, b.reason, b.request_verbatim, "
                "b.built_path, b.created_at, r.run_status, r.acceptance_status "
                "FROM workflow_builds b LEFT JOIN runs r ON r.run_id = b.run_id "
                "ORDER BY b.id DESC LIMIT 100"):
            item = dict(row)
            item["agents"] = _agent_summary(conn, row["run_id"])
            builds.append(item)
        return {"builds": builds, "queued": _queued_payload()}
    finally:
        conn.close()


def build_detail(run_id: str) -> dict | None:
    conn = _open_telemetry()
    if conn is None:
        return None
    try:
        build = conn.execute("SELECT * FROM workflow_builds WHERE run_id=?", (run_id,)).fetchone()
        if build is None:
            return None
        phases = [dict(r) for r in conn.execute(
            "SELECT phase_id, phase_name, kind, owner, attempt, status, error, gate_id, gate_result, "
            "duration_ms, model, thinking FROM phase_attempts WHERE run_id=? ORDER BY id", (run_id,))]
        requirements = [dict(r) for r in conn.execute(
            "SELECT req_id, text, phase_id, gate, verifier, status, blocker FROM requirements "
            "WHERE run_id=? ORDER BY id", (run_id,))]
        tool_calls = [dict(r) for r in conn.execute(
            "SELECT agent, tool_name, ok, completion, duration_ms FROM tool_calls "
            "WHERE run_id=? ORDER BY id LIMIT 500", (run_id,))]
        code_ops = [dict(r) for r in conn.execute(
            "SELECT phase_id, name, argv_json, duration_ms, return_code, passed FROM code_operations "
            "WHERE run_id=? ORDER BY id LIMIT 200", (run_id,))]
        usage = [dict(r) for r in conn.execute(
            "SELECT agent, attempt, tokens_json, cost_json, completeness FROM agent_usage "
            "WHERE run_id=? ORDER BY id", (run_id,))]
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return {
            "build": dict(build),
            "run": dict(run) if run else None,
            "phases": phases,
            "agents": _agent_summary(conn, run_id),
            "requirements": requirements,
            "tool_calls": tool_calls,
            "code_operations": code_ops,
            "agent_usage": usage,
        }
    finally:
        conn.close()


# ── write-side: the two POSTs ───────────────────────────────────────────────
def queue_build(request_text: str) -> dict:
    text = request_text.strip()
    if not text:
        raise ValueError("request text is empty")
    if len(text) > REQUEST_TEXT_LIMIT:
        raise ValueError(f"request longer than {REQUEST_TEXT_LIMIT} chars")
    directory = queue_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(text.encode()).hexdigest()[:8]
    path = directory / f"{stamp}-{digest}.md"
    path.write_text(text + "\n")
    return {"queued": True, "file": str(path), "name": path.name,
            "consume": f"python adws/adw_workflow_builder.py --request {path} --fixtures --stub-agents"}


def run_builder_stub(request_path: Path) -> dict:
    """Synchronous stub-only builder run on a queued file. Bounded, no network."""
    argv = [sys.executable, str(ADWS_ROOT / "adw_workflow_builder.py"),
            "--request", str(request_path), "--fixtures", "--stub-agents",
            "--db", str(default_db())]
    started = time.perf_counter()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=BUILD_TIMEOUT_S,
                          stdin=subprocess.DEVNULL, cwd=str(ROOT), check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"exit": proc.returncode, "duration_ms": int((time.perf_counter() - started) * 1000),
            "log_tail": out[-2000:]}


def launch_stub(workflow_id: str) -> tuple[int, dict]:
    if not WF_ID_RE.match(workflow_id or ""):
        return 400, {"error": "invalid workflow id"}
    reg = _registry_raw()
    entry = next((w for w in reg.get("workflows", []) if w.get("id") == workflow_id), None)
    if entry is None:
        return 404, {"error": f"workflow {workflow_id!r} is not in the registry"}
    if entry.get("status") != "validated":
        return 409, {"error": f"workflow {workflow_id!r} status is {entry.get('status')!r}, not 'validated'"}
    entry_rel = str(entry.get("entrypoint") or "").replace("\\", "/")
    prefix = "adws/built/"
    if not entry_rel.startswith(prefix):
        return 400, {"error": "entrypoint is not a built-workflow path"}
    built = built_root().resolve()
    entry_path = (built / entry_rel[len(prefix):]).resolve()
    if built not in entry_path.parents:
        return 400, {"error": "entrypoint is not inside the built root"}
    if not entry_path.is_file():
        return 404, {"error": f"entrypoint missing: {entry_rel} (built tree was removed — rebuild it)"}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    reports = launch_reports_dir() / f"{workflow_id}-{stamp}"
    argv = [sys.executable, str(entry_path), "--fixtures", "--stub-agents",
            "--db", str(launch_db_path()), "--reports-dir", str(reports)]
    started = time.perf_counter()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=LAUNCH_TIMEOUT_S,
                              stdin=subprocess.DEVNULL, cwd=str(ROOT), check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + " … launch timed out"
        exit_code = -1
    return 200, {"launched": workflow_id, "mode": "stub", "exit": exit_code,
                 "duration_ms": int((time.perf_counter() - started) * 1000),
                 "reports_dir": str(reports), "log_tail": out[-2000:]}


# ── handler ─────────────────────────────────────────────────────────────────
def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(UI_DIR), **kwargs)

        def _send_json(self, status: int, payload: dict) -> None:
            body = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > BODY_LIMIT:
                raise ValueError("missing or oversized body")
            raw = self.rfile.read(length)
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("body must be a JSON object")
            return parsed

        def do_GET(self):  # noqa: N802 — http.server API
            path = self.path.split("?", 1)[0]
            if path == "/api/workflows":
                self._send_json(200, workflows_payload())
            elif path == "/api/builds":
                self._send_json(200, builds_payload())
            elif path.startswith("/api/builds/"):
                run_id = path[len("/api/builds/"):].strip("/")
                if not re.match(r"^[\w.-]{1,80}$", run_id):
                    self._send_json(400, {"error": "invalid run id"})
                    return
                detail = build_detail(run_id)
                if detail is None:
                    self._send_json(404, {"error": f"no build {run_id!r}"})
                else:
                    self._send_json(200, detail)
            elif path.startswith("/api/"):
                self._send_json(404, {"error": "unknown endpoint"})
            else:
                super().do_GET()

        def do_POST(self):  # noqa: N802 — http.server API
            path = self.path.split("?", 1)[0]
            try:
                body = self._body()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send_json(400, {"error": f"bad request body: {exc}"})
                return
            if path == "/api/builds":
                request_text = body.get("request")
                if not isinstance(request_text, str) or not request_text.strip():
                    self._send_json(400, {"error": "field 'request' must be a non-empty string"})
                    return
                try:
                    queued = queue_build(request_text)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                if body.get("run") is True:
                    queued["build"] = run_builder_stub(Path(queued["file"]))
                self._send_json(200, queued)
            elif path == "/api/launch":
                workflow_id = body.get("id")
                if not isinstance(workflow_id, str):
                    self._send_json(400, {"error": "field 'id' must be a workflow id string"})
                    return
                status, payload = launch_stub(workflow_id)
                self._send_json(status, payload)
            else:
                self._send_json(404, {"error": "unknown endpoint"})

        def log_message(self, fmt, *args):  # quiet
            pass

    return Handler


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    server = ThreadingHTTPServer((host, port), make_handler())
    print(f"adws desk: http://{host}:{port}/  (registry {registry_path()}; db {default_db()}; Ctrl-C to stop)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Workflow-builder desk UI (localhost only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        print("REFUSED: the desk binds 127.0.0.1 only", flush=True)
        return 2
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
