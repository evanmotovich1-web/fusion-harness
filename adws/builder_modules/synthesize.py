"""Deterministic WorkflowSpec used when a seat fixture is absent. Not a model."""

from __future__ import annotations

import re

from .gates import exact_number
from .paths import PROMPT_FILES, model_name, thinking_name
from .spec_schema import canonical_entrypoint, required_files

UNMEETABLE_STEMS = {"unmeetable", "unmeetable-requirement", "unmeetable_requirement"}


def slug(text: str, fallback: str = "request-workflow") -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    value = value[:63].strip("-")
    return value or fallback


def synthesize_spec(request: str, stem: str = "") -> dict:
    named = re.search(r"(?:named|called|id[:=])\s+([a-zA-Z0-9][a-zA-Z0-9-]{0,62})", request or "")
    wid = slug(named.group(1) if named else (stem if stem and stem not in UNMEETABLE_STEMS else ""), "request-workflow")
    bullets = re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+(.+)$", request or "")
    if not bullets:
        first = " ".join((request or "").split())
        bullets = [first[:240] or "check the workflow output"]
    reqs, phases = [], []
    for index, text in enumerate(bullets, 1):
        gate = f"req_{index}_gate"
        expected = exact_number(text)
        blocker = None
        if expected is not None:
            blocker = (
                f"unsupported semantics: no objective gate verifies the total equals exactly {expected}; "
                "refusing a nonempty-string stand-in"
            )
        reqs.append({
            "id": f"req-{index}",
            "text": text.strip(),
            "phase_id": f"p{index}",
            "gate": gate,
            "verifier": f"test_req_{index}",
            "evidence": [],
            "status": "blocked",
            "blocker": blocker,
        })
        phases.append({
            "id": f"p{index}",
            "name": f"step-{index}",
            "kind": "agent",
            "owner": "worker",
            "gate": gate,
            "inputs": ["request"],
            "outputs": [f"req-{index}.json"],
            "retries": 1,
        })
    if slug(stem) in {slug(s) for s in UNMEETABLE_STEMS} or re.search(r"\bunmeetable\b", request or "", re.I):
        reqs.append({
            "id": f"req-{len(reqs)+1}",
            "text": "unmeetable requirement recorded from the request",
            "phase_id": phases[-1]["id"],
            "gate": phases[-1]["gate"],
            "verifier": "recorded-blocker",
            "evidence": [],
            "status": "blocked",
            "blocker": "unmeetable: no local executor can satisfy this requirement",
        })
    spec = {
        "schema_version": 1,
        "id": wid,
        "name": wid.replace("-", " ").title(),
        "request_verbatim": request,
        "router": {
            "triggers": [wid.replace("-", " "), "workflow"],
            "refusals": [
                {"reason": "not_workflow", "example": "write a poem"},
                {"reason": "forbidden_target", "example": "edit sssf and deploy"},
            ],
        },
        "requirements": reqs,
        "phases": phases,
        "seats": [{
            "name": "worker",
            "model": model_name(),
            "thinking": thinking_name(),
            "tools": ["read", "write"],
            "writes": [f"adws/built/{wid}/**"],
            "prompt_files": list(PROMPT_FILES),
        }],
        "artifacts": {"entrypoint": canonical_entrypoint(wid), "files": []},
        "switches": {"dry_run": True, "stub_agents": True},
        "blockers": [],
    }
    spec["artifacts"]["files"] = required_files(spec)
    return spec


def scout_envelope() -> dict:
    return {
        "patterns": [
            {
                "code": "P1",
                "citation": "adws/specs/prior-adw-patterns.md#pattern-catalog",
                "why": "code orchestrates; the agent only fills a typed envelope",
            },
            {
                "code": "M5",
                "citation": "adws/specs/prior-adw-patterns.md#this-repositorys-marketing-workflow",
                "why": "named refusals at the front door, before spend",
            },
        ],
        "tools": ["read", "grep", "find", "ls"],
        "risks": ["do not inherit automatic commit or push"],
    }


def reviewer_envelope(spec: dict) -> dict:
    return {
        "verdict": "approve",
        "findings": [{"id": req["id"], "status": "met", "text": "mapped to a phase and a gate"} for req in spec.get("requirements", [])],
        "summary": "every requirement is mapped or explicitly blocked",
    }
