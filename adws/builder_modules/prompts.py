"""Load the four prompt files from disk on every call. Never cache them."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import PROMPT_FILES, prompts_dir


def load_prompt_files(agent: str, directory: Path | None = None) -> dict:
    folder = (directory or prompts_dir()) / agent
    missing = [name for name in PROMPT_FILES if not (folder / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{folder}: missing {missing}")
    files = {name: (folder / name).read_text() for name in PROMPT_FILES}
    files["tools"] = json.loads(files.pop("tools.json"))
    if "pi_tools" not in files["tools"] or "writes" not in files["tools"]:
        raise ValueError(f"{folder}/tools.json needs pi_tools and writes")
    return files


def render(template: str, values: dict) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text
