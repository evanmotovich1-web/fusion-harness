#!/usr/bin/env python3
"""Loopback control and telemetry API for Pi self-compaction.

Only session hashes, measured usage, thresholds, and command state are stored.
Conversation text and summaries never cross this API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE = Path(os.environ.get("SELF_COMPACT_DB", Path.home() / ".cache/self-compact/sessions.sqlite"))
TOKEN = Path(os.environ.get("SELF_COMPACT_TOKEN_FILE", Path.home() / ".config/self-compact/token"))
SESSION = re.compile(r"^/v1/sessions/([0-9a-f]{32,64})(?:/(compact|claim|result))?$")
MAX_BODY = 1024


def db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=3)
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, used INTEGER, window INTEGER, soft INTEGER,
        warning INTEGER, force INTEGER, level TEXT, request INTEGER NOT NULL DEFAULT 0,
        result TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    return conn


def token(path: Path, create: bool = False) -> str:
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_hex(32) + "\n")
    value = path.read_text().strip()
    if len(value) != 64 or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("invalid self-compact API token")
    if path.stat().st_mode & 0o077:
        raise PermissionError("self-compact API token must be private")
    return value


def update(session_id: str, data: dict, path: Path = STATE) -> dict:
    fields = {"used", "window", "soft", "warning", "force", "level"}
    if set(data) != fields or any(type(data[k]) is not int or data[k] < 0 for k in fields - {"level"}):
        raise ValueError("invalid telemetry")
    if data["level"] not in {"ok", "soft", "warning", "forced"} or not 0 < data["window"] <= 10_000_000:
        raise ValueError("invalid telemetry")
    if not 0 < data["soft"] < data["warning"] <= data["force"] <= data["window"]:
        raise ValueError("invalid thresholds")
    with db(path) as conn:
        conn.execute("""INSERT INTO sessions (id, used, window, soft, warning, force, level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET used=excluded.used, window=excluded.window,
            soft=excluded.soft, warning=excluded.warning, force=excluded.force,
            level=excluded.level, updated_at=CURRENT_TIMESTAMP""",
            (session_id, *(data[k] for k in ("used", "window", "soft", "warning", "force", "level"))))
    return {"ok": True}


def sessions(path: Path = STATE) -> list[dict]:
    with db(path) as conn:
        rows = conn.execute("SELECT id, used, window, level, request, result, updated_at "
                            "FROM sessions ORDER BY updated_at DESC LIMIT 100").fetchall()
    return [dict(zip(("id", "used", "window", "level", "request", "result", "updated_at"), row)) for row in rows]


def command(session_id: str, action: str, data: dict, path: Path = STATE) -> dict:
    with db(path) as conn:
        exists = conn.execute("SELECT request FROM sessions WHERE id=?", (session_id,)).fetchone()
        if exists is None:
            return {"ok": False, "error": "unknown session"}
        if action == "compact":
            if data:
                raise ValueError("compact takes no body fields")
            conn.execute("UPDATE sessions SET request=1, result=NULL WHERE id=?", (session_id,))
        elif action == "claim":
            if data:
                raise ValueError("claim takes no body fields")
            if exists[0] == 1:
                conn.execute("UPDATE sessions SET request=2 WHERE id=?", (session_id,))
                return {"ok": True, "compact": True}
            return {"ok": True, "compact": False}
        elif action == "result":
            if set(data) != {"status"} or data["status"] not in {"completed", "failed"}:
                raise ValueError("invalid result")
            conn.execute("UPDATE sessions SET request=0, result=? WHERE id=?", (data["status"], session_id))
        else:
            raise ValueError("unknown action")
    return {"ok": True}


def make_server(host: str = "127.0.0.1", port: int = 8787, state: Path = STATE,
                token_file: Path = TOKEN) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("self-compact API must bind to loopback")
    secret = token(token_file, create=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def send(self, code: int, body: dict) -> None:
            encoded = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def authorized(self) -> bool:
            if secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + secret):
                return True
            self.send(401, {"ok": False, "error": "unauthorized"})
            return False

        def do_GET(self) -> None:
            if not self.authorized():
                return
            if self.path == "/v1/sessions":
                self.send(200, {"ok": True, "sessions": sessions(state)})
                return
            match = SESSION.fullmatch(self.path)
            if match and match[2] is None:
                row = next((row for row in sessions(state) if row["id"] == match[1]), None)
                self.send(200 if row else 404, {"ok": bool(row), "session": row})
                return
            self.send(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            if not self.authorized():
                return
            match = SESSION.fullmatch(self.path)
            if not match:
                self.send(404, {"ok": False, "error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= MAX_BODY:
                    raise ValueError("invalid request size")
                data = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(data, dict):
                    raise ValueError("expected object")
                result = command(match[1], match[2], data, state) if match[2] else update(match[1], data, state)
                self.send(200 if result["ok"] else 404, result)
            except (ValueError, TypeError):
                self.send(400, {"ok": False, "error": "invalid request"})

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    make_server(args.host, args.port).serve_forever()


if __name__ == "__main__":
    main()
