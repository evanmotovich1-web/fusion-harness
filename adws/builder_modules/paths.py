"""Path roots. Writes stay inside adws/built/<name>/ and the run dir."""

from __future__ import annotations

import os
from pathlib import Path

ADWS = Path(__file__).resolve().parents[1]
ROOT = ADWS.parent
SPEC_PATH = ADWS / "specs" / "workflow-builder.md"
PATTERNS_PATH = ADWS / "specs" / "prior-adw-patterns.md"

KNOWN_TOOLS = frozenset({"read", "grep", "find", "ls", "write", "edit", "bash"})
PROMPT_FILES = ("system.md", "user.md", "soft_notice.md", "tools.json")
SEATS = ("workflow_scout", "spec_writer", "reviewer", "builder")
SEAT_TOOLS = {
    "workflow_scout": ["read", "grep", "find", "ls"],
    "spec_writer": ["read", "grep", "find", "ls", "write"],
    "reviewer": ["read", "grep", "ls", "write"],
    "builder": ["read", "grep", "find", "ls", "write", "edit", "bash"],
}
THINKING = frozenset({"off", "minimal", "low", "medium", "high", "xhigh", "max"})
DEFAULT_MODEL = "deepseek/deepseek-flash"


def prompts_dir() -> Path:
    return Path(os.environ.get("ADW_PROMPTS_DIR", ADWS / "prompts"))


def fixtures_dir() -> Path:
    return Path(os.environ.get("ADW_FIXTURES_DIR", ADWS / "fixtures"))


def built_root() -> Path:
    return Path(os.environ.get("ADW_BUILT_ROOT", ADWS / "built"))


def registry_path() -> Path:
    return Path(os.environ.get("ADW_REGISTRY_PATH", ADWS / "registry.json"))


def default_db() -> Path:
    return Path(os.environ.get("ADW_DB", ADWS / "data" / "adw.db"))


def model_name() -> str:
    return os.environ.get("ADW_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def thinking_name() -> str:
    value = os.environ.get("ADW_THINKING", "medium").strip() or "medium"
    return value if value in THINKING else "medium"


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def built_dir(workflow_id: str) -> Path:
    if not workflow_id or "/" in workflow_id or workflow_id in {".", ".."}:
        raise ValueError(f"refusing workflow id {workflow_id!r}")
    destination = (built_root() / workflow_id).resolve()
    if not inside(destination, built_root().resolve()):
        raise ValueError(f"workflow id escapes built root: {workflow_id}")
    return destination
