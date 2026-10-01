"""Preflight before spend. A named-but-absent tool is a blocker, not a surprise."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import KNOWN_TOOLS, SEATS, fixtures_dir, prompts_dir
from .prompts import load_prompt_files

MEMORY_STEMS = {"memory_search", "memory-search"}


def generated_tool_blockers(spec: dict) -> list[str]:
    """Unknown tools on a generated seat or phase block before that workflow runs."""
    blockers = []
    if not isinstance(spec, dict) or spec.get("_invalid"):
        return blockers
    for seat in spec.get("seats") or []:
        if not isinstance(seat, dict):
            continue
        name = seat.get("name") or "seat"
        for tool in seat.get("tools") or []:
            if tool not in KNOWN_TOOLS:
                blockers.append(f"preflight: unknown_tool: {tool} on {name} (not installed; no agent launch)")
                break
    for phase in spec.get("phases") or []:
        if not isinstance(phase, dict):
            continue
        owner = phase.get("owner") or phase.get("id") or "phase"
        for tool in phase.get("tools") or []:
            if tool not in KNOWN_TOOLS:
                blockers.append(f"preflight: unknown_tool: {tool} on {owner} (not installed; no agent launch)")
                break
    return blockers


def check_seats(stem: str = "", fixture_root: Path | None = None) -> list[str]:
    blockers = []
    root = fixture_root or fixtures_dir()
    overlay = _overlay(stem, root)
    for seat in SEATS:
        try:
            files = load_prompt_files(seat, prompts_dir())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append(f"preflight: {seat}: {exc}")
            continue
        tools = list(files["tools"].get("pi_tools") or [])
        if seat in overlay:
            tools = list(overlay[seat])
        unknown = [tool for tool in tools if tool not in KNOWN_TOOLS]
        if unknown:
            blockers.append(f"preflight: unknown_tool: {unknown[0]} on {seat} (not installed; no agent launch)")
        for pattern in files["tools"].get("writes") or []:
            text = str(pattern)
            if text.startswith("/") or ".." in text or text.startswith("homecare") or "sssf" in text:
                blockers.append(f"preflight: write pattern {text} is outside the allowlist")
    if stem in MEMORY_STEMS and not any("memory_search" in item for item in blockers):
        blockers.append("preflight: unknown_tool: memory_search on workflow_scout (not installed; no agent launch)")
    return blockers


def _overlay(stem: str, root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    candidates = [
        root / "preflight" / f"{stem}.json",
        root / f"preflight_{stem}.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        raw = json.loads(path.read_text())
        if isinstance(raw, dict) and "pi_tools" in raw and "seat" in raw:
            found[str(raw["seat"])] = list(raw["pi_tools"])
        elif isinstance(raw, dict):
            for seat, tools in raw.items():
                if isinstance(tools, list):
                    found[str(seat)] = tools
    return found
