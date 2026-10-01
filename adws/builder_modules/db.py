"""SQLite open/init. Schema file is the source of truth."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .paths import ADWS

SCHEMA_PATH = ADWS / "data" / "schema.sql"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    init(conn)
    return conn
