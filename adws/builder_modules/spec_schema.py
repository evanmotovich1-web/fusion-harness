"""WorkflowSpec v1. Unknown keys are fatal. Status starts blocked."""

from __future__ import annotations

import re
from typing import Any

from .paths import PROMPT_FILES, THINKING

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
TOP = {"schema_version", "id", "name", "request_verbatim", "router", "requirements", "phases", "seats", "artifacts", "switches", "blockers"}
ROUTER_KEYS = {"triggers", "refusals"}
REFUSAL_KEYS = {"reason", "example"}
REQ_KEYS = {"id", "text", "phase_id", "gate", "verifier", "evidence", "status", "blocker"}
PHASE_KEYS = {"id", "name", "kind", "owner", "gate", "inputs", "outputs", "retries"}
SEAT_KEYS = {"name", "model", "thinking", "tools", "writes", "prompt_files"}
ART_KEYS = {"entrypoint", "files"}
SWITCH_KEYS = {"dry_run", "stub_agents"}


def _unknown(raw: dict, allowed: set[str], where: str, errors: list[str]) -> None:
    for key in raw:
        if key not in allowed:
            errors.append(f"{where}: unknown key {key!r}")


def canonical_entrypoint(workflow_id: str) -> str:
    return f"adws/built/{workflow_id}/adw_{workflow_id.replace('-', '_')}.py"


def required_files(spec: dict) -> list[str]:
    wid = spec["id"]
    root = f"adws/built/{wid}"
    files = [
        canonical_entrypoint(wid),
        f"{root}/config.json",
        f"{root}/gates.py",
        f"{root}/README.md",
        f"{root}/tests/test_{wid.replace('-', '_')}.py",
    ]
    for seat in spec.get("seats") or []:
        name = seat.get("name")
        for prompt in PROMPT_FILES:
            files.append(f"{root}/prompts/{name}/{prompt}")
        files.append(f"{root}/fixtures/good_{name}.json")
        files.append(f"{root}/fixtures/bad_{name}.json")
    return files


def validate_spec(raw: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["WorkflowSpec must be a JSON object"]
    _unknown(raw, TOP, "spec", errors)
    if raw.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    wid = raw.get("id")
    if not isinstance(wid, str) or not ID_RE.match(wid):
        errors.append("id must match ^[a-z0-9][a-z0-9-]{0,62}$")
        wid = "invalid"
    if not isinstance(raw.get("name"), str) or not raw.get("name", "").strip():
        errors.append("name is required")
    if not isinstance(raw.get("request_verbatim"), str) or not raw.get("request_verbatim", "").strip():
        errors.append("request_verbatim is required")
    router = raw.get("router")
    if not isinstance(router, dict):
        errors.append("router must be an object")
        router = {}
    else:
        _unknown(router, ROUTER_KEYS, "router", errors)
        if not isinstance(router.get("triggers"), list) or not router.get("triggers"):
            errors.append("router.triggers must be a non-empty list")
        for item in router.get("refusals") or []:
            if not isinstance(item, dict):
                errors.append("router.refusals entries must be objects")
                continue
            _unknown(item, REFUSAL_KEYS, "router.refusals", errors)
            if item.get("reason") not in {"not_workflow", "forbidden_target", "needs_human"}:
                errors.append("router.refusals.reason must be a named refusal")
    reqs = raw.get("requirements")
    phases = raw.get("phases")
    seats = raw.get("seats")
    if not isinstance(reqs, list) or not reqs:
        errors.append("requirements must be a non-empty list")
        reqs = []
    if not isinstance(phases, list) or not phases:
        errors.append("phases must be a non-empty list")
        phases = []
    if not isinstance(seats, list) or not seats:
        errors.append("seats must be a non-empty list")
        seats = []
    phase_ids = []
    seat_names = []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            errors.append(f"phases[{index}] must be an object")
            continue
        _unknown(phase, PHASE_KEYS, f"phases[{index}]", errors)
        phase_ids.append(phase.get("id"))
        if phase.get("kind") not in {"code", "agent"}:
            errors.append(f"phases[{index}].kind must be code|agent")
        if not phase.get("gate"):
            errors.append(f"phases[{index}] must name a gate")
        if phase.get("kind") == "agent" and not phase.get("owner"):
            errors.append(f"phases[{index}] agent phase needs an owner seat")
        if not isinstance(phase.get("retries"), int):
            errors.append(f"phases[{index}].retries must be an integer")
    seat_names = []
    for index, seat in enumerate(seats):
        if not isinstance(seat, dict):
            errors.append(f"seats[{index}] must be an object")
            continue
        _unknown(seat, SEAT_KEYS, f"seats[{index}]", errors)
        seat_names.append(seat.get("name"))
        model = seat.get("model")
        if not isinstance(model, str) or model.count("/") != 1:
            errors.append(f"seats[{index}].model must be provider/id")
        if seat.get("thinking") not in THINKING:
            errors.append(f"seats[{index}].thinking is invalid")
        files = seat.get("prompt_files")
        if sorted(files or []) != sorted(PROMPT_FILES):
            errors.append(f"seats[{index}] must declare the 4 prompt files")
        if not isinstance(seat.get("tools"), list) or not seat.get("tools"):
            errors.append(f"seats[{index}].tools must be a non-empty list")
    seen = set()
    for index, req in enumerate(reqs):
        if not isinstance(req, dict):
            errors.append(f"requirements[{index}] must be an object")
            continue
        _unknown(req, REQ_KEYS, f"requirements[{index}]", errors)
        rid = req.get("id")
        if rid in seen:
            errors.append(f"requirement id {rid} repeated")
        seen.add(rid)
        phase = next((item for item in phases if isinstance(item, dict) and item.get("id") == req.get("phase_id")), None)
        if phase is None:
            errors.append(f"requirement {rid} phase_id is not a phase")
        elif req.get("gate") != phase.get("gate"):
            errors.append(f"requirement {rid} gate does not match its phase gate")
        if req.get("status") not in {"verified", "blocked"}:
            errors.append(f"requirement {rid} status must be verified|blocked")
        if req.get("status") != "blocked":
            errors.append(f"requirement {rid} must start blocked; only validate sets verified")
        if not req.get("gate") or not req.get("verifier"):
            errors.append(f"requirement {rid} needs gate and verifier")
        if not isinstance(req.get("evidence"), list):
            errors.append(f"requirement {rid}.evidence must be a list")
        blocker = req.get("blocker")
        if blocker is not None and not isinstance(blocker, str):
            errors.append(f"requirement {rid}.blocker must be a string or null")
    for phase in phases:
        if isinstance(phase, dict) and phase.get("kind") == "agent" and phase.get("owner") not in seat_names:
            errors.append(f"agent phase {phase.get('id')} owner {phase.get('owner')} is not a seat")
    if _cyclic(phases):
        errors.append("phase graph is cyclic")
    artifacts = raw.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts must be an object")
    else:
        _unknown(artifacts, ART_KEYS, "artifacts", errors)
        if isinstance(wid, str) and ID_RE.match(wid) and artifacts.get("entrypoint") != canonical_entrypoint(wid):
            errors.append(f"entrypoint must be {canonical_entrypoint(wid)}")
        files = artifacts.get("files")
        if not isinstance(files, list) or not files:
            errors.append("artifacts.files must be a non-empty list")
        elif isinstance(wid, str) and ID_RE.match(wid):
            missing = [item for item in required_files(raw) if item not in files]
            if missing:
                errors.append("artifacts.files missing " + ", ".join(missing))
    switches = raw.get("switches")
    if not isinstance(switches, dict):
        errors.append("switches must be an object")
    else:
        _unknown(switches, SWITCH_KEYS, "switches", errors)
        if switches.get("dry_run") is not True or switches.get("stub_agents") is not True:
            errors.append("switches.dry_run and switches.stub_agents must default true")
    if not isinstance(raw.get("blockers"), list):
        errors.append("blockers must be a list")
    return errors


def _cyclic(phases: list) -> bool:
    ids = [p.get("id") for p in phases if isinstance(p, dict)]
    edges: dict[str, list[str]] = {i: [] for i in ids if isinstance(i, str)}
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        for item in phase.get("inputs") or []:
            if item in edges and phase.get("id") in edges:
                edges[item].append(phase["id"])
    visiting, seen = set(), set()

    def walk(node: str) -> bool:
        if node in visiting:
            return True
        if node in seen:
            return False
        visiting.add(node)
        if any(walk(nxt) for nxt in edges.get(node, [])):
            return True
        visiting.remove(node)
        seen.add(node)
        return False

    return any(walk(node) for node in edges)
