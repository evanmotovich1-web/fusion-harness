"""registry.json writer. Idempotent by id + version. Never hand-edited by agents."""

from __future__ import annotations

import json
from pathlib import Path

from .db import now_iso
from .paths import registry_path
from .spec_schema import canonical_entrypoint


def load(path: Path | None = None) -> dict:
    target = path or registry_path()
    if not target.is_file():
        return {"schema_version": 1, "workflows": []}
    raw = json.loads(target.read_text())
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("workflows"), list):
        raise ValueError(f"registry is not schema_version 1: {target}")
    return raw


def register(spec: dict, run_id: str, verified: int, blocked: int, path: Path | None = None) -> dict:
    target = path or registry_path()
    raw = load(target)
    entry = {
        "id": spec["id"],
        "name": spec["name"],
        "version": 1,
        "entrypoint": canonical_entrypoint(spec["id"]),
        "spec_path": f"adws/built/{spec['id']}/config.json",
        "built_at": now_iso(),
        "build_run_id": run_id,
        "status": "validated" if blocked == 0 else "blocked",
        "acceptance": {
            "requirements_total": verified + blocked,
            "verified": verified,
            "blocked": blocked,
        },
        "source_request": spec.get("request_verbatim") or "",
    }
    workflows = [item for item in raw["workflows"] if not (item.get("id") == entry["id"] and item.get("version") == 1)]
    workflows.append(entry)
    raw["workflows"] = workflows
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".{run_id}.tmp")
    tmp.write_text(json.dumps(raw, indent=2) + "\n")
    tmp.replace(target)
    return entry
