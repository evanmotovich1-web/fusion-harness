#!/usr/bin/env python3
"""ADW workflow builder. Code orchestrates; four seats fill envelopes.

    python adws/adw_workflow_builder.py --request "<text or path>" [--fixtures] [--stub-agents]
        [--stub-bad-first] [--db PATH] [--reports-dir PATH] [--max-revisions N]

Exit codes: 0 accepted · 2 refused · 3 needs_human · 4 blocked.
Stub mode opens no network client. Path checks are an allowlist plus a post-phase
audit, not a sandbox. This file does not commit, push, or deploy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ADWS = Path(__file__).resolve().parent
if str(ADWS) not in sys.path:
    sys.path.insert(0, str(ADWS))

from builder_modules import agents, gates, preflight, registry, scaffold, telemetry, validators  # noqa: E402
from builder_modules.db import now_iso, open_db  # noqa: E402
from builder_modules.paths import (  # noqa: E402
    ADWS as ADWS_ROOT,
    built_dir,
    default_db,
    model_name,
    thinking_name,
)
from builder_modules.prompts import load_prompt_files  # noqa: E402
from builder_modules.router import route  # noqa: E402
from builder_modules.spec_schema import validate_spec  # noqa: E402

MAX_VALIDATE_FIXES = 3


def needs_human_spec(request: str) -> dict:
    """Blocked intake spec. Marks unknowns; does not invent a workflow."""
    return {
        "schema_version": 1,
        "status": "needs_human",
        "request_verbatim": request,
        "invented": False,
        "id": "<EVAN: fill>",
        "name": "<EVAN: fill>",
        "outcome": "<EVAN: fill>",
        "gate": "<EVAN: fill>",
        "writes": "<EVAN: fill>",
        "requirements": [],
        "phases": [],
        "note": "Refused to invent a business workflow. Unknowns stay <EVAN: fill>.",
    }


def install_socket_guard() -> None:
    import socket

    def blocked(*_args, **_kwargs):
        raise RuntimeError("stub mode blocked a network socket")

    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked  # type: ignore[assignment]


def load_request(raw: str) -> tuple[str, str, str]:
    text = (raw or "").strip()
    # A slash inside a sentence ("excel/presentation") is not a missing file.
    # Only a path-shaped argument that does not exist is a refusal.
    path_like = text.startswith(("/", "./", "../")) or (
        " " not in text and text.endswith((".md", ".txt", ".json"))
    )
    candidates = [Path(text), Path.cwd() / text, ADWS_ROOT / text, ADWS_ROOT / "fixtures" / "requests" / Path(text).name]
    if path_like or ("/" in text and " " not in text):
        for path in candidates:
            try:
                if path.is_file():
                    return path.read_text(), str(path), path.stem
            except OSError:
                continue
        if path_like:
            raise FileNotFoundError(text)
    return text, "argv", ""


def source_hashes() -> dict[str, str]:
    paths = [ADWS_ROOT / "adw_workflow_builder.py", *sorted((ADWS_ROOT / "builder_modules").glob("*.py"))]
    paths += sorted((ADWS_ROOT / "specs").glob("*.md"))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


class Run:
    def __init__(self, args, request: str, ref: str, stem: str):
        self.args = args
        self.request = request
        self.ref = ref
        self.stem = stem
        self.run_id = args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{hashlib.sha256(request.encode()).hexdigest()[:6]}"
        reports_dir = args.reports_dir or os.environ.get("ADW_REPORTS_DIR") or ""
        reports = Path(reports_dir) if reports_dir else ADWS_ROOT / "reports"
        self.dir = reports / "runs" / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.dir / "run.log"
        self.db_path = Path(args.db) if args.db else default_db()
        self.conn = open_db(self.db_path)
        self.model = model_name()
        self.thinking = thinking_name()
        self.stub = bool(args.stub_agents or args.fixtures)
        self.lines: list[str] = []
        digest = hashlib.sha256(request.encode()).hexdigest()
        telemetry.start_run(self.conn, self.run_id, ref, digest)
        telemetry.abandon_other_running(self.conn, self.run_id)

    def log(self, line: str) -> None:
        stamped = f"[{time.strftime('%H:%M:%S')}] {line}"
        print(stamped, flush=True)
        self.lines.append(stamped)
        with self.log_path.open("a") as handle:
            handle.write(stamped + "\n")

    def code(self, phase_id: str, name: str, gate_id: str, status: str, detail: str = "", duration_ms: int | None = None) -> None:
        self.log(f"CODE {name}: {detail}" if detail else f"CODE {name}")
        self.log(f"CODE {name} → GATE {gate_id} {'PASS' if status == 'passed' else 'FAIL'}")
        telemetry.phase_attempt(
            self.conn, self.run_id, phase_id, name, "code", "code", 1, now_iso(), duration_ms, status,
            None if status == "passed" else detail, gate_id, status, model="unknown", thinking="unknown",
        )
        telemetry.code_op(
            self.conn, self.run_id, phase_id, name, ["code", name], str(self.dir), duration_ms,
            0 if status == "passed" else 1, status == "passed", "", "",
        )

    def finish(self, code: int, status: str, reason: str, spec: dict | None = None, built: str | None = None) -> int:
        verified = blocked = 0
        if spec:
            for req in spec.get("requirements") or []:
                evidence = list(req.get("evidence") or [])
                if req.get("status") == "verified":
                    verified += 1
                    evidence.append(self.run_id)
                else:
                    blocked += 1
                telemetry.requirement_row(self.conn, self.run_id, req, evidence)
        telemetry.workflow_build(
            self.conn, self.run_id, status, reason, self.request,
            spec.get("id") if spec else None, spec.get("name") if spec else None, 1 if spec else None, built,
        )
        acceptance = "accepted" if code == 0 else status
        telemetry.finish_run(
            self.conn, self.run_id, status, acceptance, reason, [str(self.log_path)],
            spec.get("id") if spec else None, 1 if spec else None,
        )
        report = [
            f"# {status}",
            "",
            f"reason: {reason}",
            f"exit: {code}",
            "",
            "## Request",
            "",
            self.request,
            "",
        ]
        if spec:
            report += ["## Requirements", ""]
            for req in spec["requirements"]:
                report.append(f"- {req['id']}: {req.get('status')} gate={req.get('gate')} blocker={req.get('blocker')}")
        if status == "needs_human":
            hold = needs_human_spec(self.request)
            (self.dir / "spec.json").write_text(json.dumps(hold, indent=2) + "\n")
            report += [
                "", "## Spec", "",
                "Unknowns stay `<EVAN: fill>`. No workflow id, phase, gate, or business fact was invented.",
                "", "```json", json.dumps(hold, indent=2), "```",
            ]
        (self.dir / "report.md").write_text("\n".join(report) + "\n")
        self.log(f"DONE {status} exit={code}")
        self.conn.close()
        return code


def record_agent(run: Run, phase_id: str, name: str, agent: str, result: agents.PhaseResult, _started: float) -> None:
    log_path = run.dir / f"{agent}.jsonl"
    tokens = json.loads(telemetry.unknown_tokens())
    cost = json.loads(telemetry.unknown_cost())
    model = "unknown" if run.stub else run.model
    tools = load_prompt_files(agent)["tools"]
    history = result.history or [agents.AttemptRecord(result.attempts, result.passed, result.failures, [], None)]
    for item in history:
        telemetry.phase_attempt(
            run.conn, run.run_id, phase_id, name, "agent", agent, item.attempt, now_iso(), item.duration_ms,
            "passed" if item.passed else "failed", None if item.passed else "; ".join(item.failures),
            agent, "PASS" if item.passed else "FAIL", model=model, thinking=run.thinking,
            session_id=f"{run.run_id}-{agent}", tools=list(tools.get("pi_tools") or []),
        )
        telemetry.agent_run(
            run.conn, run.run_id, agent, item.attempt, item.passed, item.failures, item.calls, item.duration_ms,
            model, tokens, cost, str(run.dir / f"{agent}.attempt{item.attempt}.prompt.md"), str(log_path), [],
            tools, run.stub,
        )
        telemetry.tool_call_rows(run.conn, run.run_id, phase_id, agent, item.attempt, item.calls)
        telemetry.usage(run.conn, run.run_id, phase_id, agent, item.attempt, tokens, cost, "unknown")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a workflow ADW from a request")
    parser.add_argument("--request", required=True)
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--stub-agents", action="store_true")
    parser.add_argument("--stub-bad-first", action="store_true")
    parser.add_argument("--db", default="")
    parser.add_argument("--reports-dir", default="")
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--run-id", default="")
    # The SSSF desk appends this to every launch. Ignore it and the click dies
    # before intake. When set, it is the run id so the desk row and this run match.
    parser.add_argument("--adw-id", default="")
    args = parser.parse_args(argv)
    if args.adw_id and not args.run_id:
        args.run_id = args.adw_id
    if args.stub_agents or args.fixtures:
        install_socket_guard()
    try:
        request, ref, stem = load_request(args.request)
    except FileNotFoundError as exc:
        print(f"REFUSED: request file not found: {exc}", flush=True)
        return 2
    before_sources = source_hashes()
    run = Run(args, request, ref, stem)
    decision = route(request, stem)
    run.code("intake", "intake", "route", "passed", decision["reason"])
    (run.dir / "route.json").write_text(json.dumps(decision, indent=2) + "\n")
    if decision["route"] == "needs_human":
        (run.dir / "questions.md").write_text(
            "\n".join(f"- {q} `<EVAN: fill>`" for q in decision["questions"]) + "\n"
        )
        run.log("REFUSED needs_human — unknowns marked <EVAN: fill>; no facts invented; no agent spend")
        return run.finish(3, "needs_human", decision["reason"])
    if decision["route"] == "existing_recipe":
        run.log(
            f"EXISTING RECIPE {decision['reason']} — live desk chip; no agent spend"
        )
        return run.finish(0, "accepted", decision["reason"])
    if decision["route"] != "build":
        run.log(f"REFUSED {decision['route']} — no agent spend")
        return run.finish(2, "refused", decision["reason"])
    blockers = preflight.check_seats(stem)
    if blockers:
        run.log("PREFLIGHT " + blockers[0])
        run.code("preflight", "preflight", "known_tools", "failed", blockers[0])
        return run.finish(4, "blocked", blockers[0])
    if not run.stub:
        try:
            agents.resolve_model(run.model)
        except Exception as exc:  # noqa: BLE001 — preflight must stop before spend
            run.code("preflight", "preflight", "model_catalog", "failed", str(exc))
            return run.finish(4, "blocked", f"preflight: {exc}")

    runner = agents.StubRunner(args.stub_bad_first, stem, request) if run.stub else agents.PiRunner()
    phase = agents.PhaseRunner(runner, run.dir, run.log, request, stem, run.model, run.thinking, run.stub)

    started = time.perf_counter()
    scout = phase.run("workflow_scout", {"request": request}, [run.dir / "workflow_scout.output.json"], gates.survey)
    record_agent(run, "survey", "survey", "workflow_scout", scout, started)
    if not scout.passed or not scout.output:
        return run.finish(4, "blocked", "survey gate exhausted: " + "; ".join(scout.failures))

    spec = None
    revisions = 0
    notice = ""
    while True:
        started = time.perf_counter()
        batch = {"request": request, "patterns": scout.output.get("patterns"), "notice": notice}
        written = phase.run(
            "spec_writer", batch, [run.dir / "spec_writer.output.json"],
            lambda output, current=request: gates.spec_schema(output, current),
        )
        record_agent(run, "spec", "spec", "spec_writer", written, started)
        if not written.passed or not written.output:
            return run.finish(4, "blocked", "spec_schema exhausted: " + "; ".join(written.failures))
        spec = written.output
        if hasattr(runner, "spec"):
            runner.spec = spec
        approved = False
        for _round in range(1, 4):
            started = time.perf_counter()
            verdict = phase.run(
                "reviewer", {"spec": spec}, [run.dir / "reviewer.output.json"],
                lambda output, current=spec: gates.verdict_consistent(output, current),
            )
            record_agent(run, "spec_review", "spec_review", "reviewer", verdict, started)
            if verdict.passed and verdict.output and verdict.output.get("verdict") == "approve":
                approved = True
                break
            if revisions >= args.max_revisions:
                return run.finish(4, "blocked", "spec review bounds exhausted", spec)
            revisions += 1
            findings = (verdict.output or {}).get("findings") or verdict.failures
            notice = json.dumps(findings)
            run.log(f"SOFT NOTICE: spec revision {revisions}: {notice}")
            break
        if approved:
            break

    errors = validate_spec(spec)
    errors.extend(item for item in gates.spec_schema(spec, request) if item not in errors)
    if errors:
        reason = next((item for item in errors if "request mismatch" in item or "unknown_tool" in item), "spec_schema: " + "; ".join(errors))
        return run.finish(4, "blocked", reason, spec)
    capability = preflight.generated_tool_blockers(spec)
    if capability:
        return run.finish(4, "blocked", capability[0], spec)
    (run.dir / "spec.json").write_text(json.dumps(spec, indent=2) + "\n")

    started_fill = time.perf_counter()
    scaffold.write_scaffold(spec)
    run.code("scaffold", "scaffold", "py_compile", "passed", f"{len(spec['artifacts']['files'])} files",
             int((time.perf_counter() - started_fill) * 1000))
    compile_errors = validators.compile_python(spec)
    if compile_errors:
        return run.finish(4, "blocked", "; ".join(compile_errors), spec)

    allow = built_dir(spec["id"])
    implement_ok = False
    envelope = None
    for _fix in range(MAX_VALIDATE_FIXES):
        before = scaffold.snapshot(spec)
        started = time.perf_counter()
        built = phase.run(
            "builder", {"spec": spec}, [allow / "README.md"], gates_for_builder(before, allow),
        )
        record_agent(run, "implement", "implement", "builder", built, started)
        envelope = built.output or {}
        unclaimed = [item for item in built.failures if "unclaimed write" in item]
        if unclaimed:
            run.log(f"GATE  diff_claims_real FAIL: {unclaimed[0]}")
            _preserve(run, spec)
            return run.finish(4, "blocked", unclaimed[0], spec)
        outside = _outside_claim(envelope, spec["id"])
        if outside:
            run.log(f"GATE  diff_claims_real FAIL: {outside}")
            run.log(f"SOFT NOTICE: {outside}")
            if run.stem in agents.OUTSIDE_STEMS or _fix + 1 == MAX_VALIDATE_FIXES:
                _preserve(run, spec)
                return run.finish(4, "blocked", outside, spec)
            continue
        if not built.passed and envelope.get("fill") == "refused":
            if run.stem in agents.OUTSIDE_STEMS:
                _preserve(run, spec)
                return run.finish(4, "blocked", "; ".join(built.failures), spec)
            continue
        scaffold.write_fill(spec)
        after = scaffold.snapshot(spec)
        claim_errors = gates.diff_claims_real(envelope, before, after, f"adws/built/{spec['id']}")
        if claim_errors:
            run.log("SOFT NOTICE: " + " | ".join(claim_errors))
            continue
        run.log("AGENT builder → GATE diff_claims_real PASS")
        implement_ok = True
        break
    if not implement_ok:
        _preserve(run, spec)
        return run.finish(4, "blocked", "diff_claims_real exhausted", spec)

    if source_hashes() != before_sources:
        _preserve(run, spec)
        return run.finish(4, "blocked", "builder source or spec files changed during the run", spec)

    work = run.dir / "validate"
    last_errors: list[str] = []
    for _fix in range(MAX_VALIDATE_FIXES):
        started = time.perf_counter()
        last_errors = validators.validate_tree(spec, work)
        duration = int((time.perf_counter() - started) * 1000)
        status = "passed" if not last_errors else "failed"
        run.code("validate", "validate", "fresh_verification", status, "; ".join(last_errors)[:500], duration)
        if not last_errors:
            break
        run.log("SOFT NOTICE: " + " | ".join(last_errors))
        scaffold.write_fill(spec)
    if last_errors:
        _preserve(run, spec)
        return run.finish(4, "blocked", "validate exhausted: " + "; ".join(last_errors), spec)

    _prove_requirements(spec, _pytest_log(run))
    blocked = [req for req in spec["requirements"] if req.get("blocker")]
    verified = [req for req in spec["requirements"] if not req.get("blocker")]
    for req in verified:
        req["status"] = "verified"
        req["evidence"] = [f"validate:{run.run_id}"]
    for req in blocked:
        req["status"] = "blocked"
    (built_dir(spec["id"]) / "config.json").write_text(json.dumps(spec, indent=2) + "\n")
    # The status stamp is a write. Acceptance requires a validate pass after it.
    stamp_errors = validators.validate_tree(spec, run.dir / "validate-after-stamp")
    run.code("validate_stamp", "validate_stamp", "fresh_verification", "passed" if not stamp_errors else "failed",
             "; ".join(stamp_errors)[:500])
    if stamp_errors:
        _preserve(run, spec)
        return run.finish(4, "blocked", "validate after status stamp failed: " + "; ".join(stamp_errors), spec)
    if blocked:
        _preserve(run, spec)
        return run.finish(4, "blocked", f"{len(blocked)} requirement(s) blocked; {len(verified)} verified", spec)
    registry.register(spec, run.run_id, len(verified), 0)
    run.code("register", "register", "registry", "passed", spec["id"])
    return run.finish(0, "accepted", "validate green and every requirement verified", spec, str(built_dir(spec["id"])))


def gates_for_builder(before: dict, allow: Path):
    def _gate(output: dict) -> list[str]:
        if output.get("_invalid"):
            return [str(output.get("failure") or "builder: fixture gate failed")]
        if output.get("fill") == "refused" or _outside_claim(output, allow.name):
            return [str(output.get("failure") or f"diff_claims_real: path outside allowlist: {allow}")]
        if output.get("fill") not in {None, "from_spec"} and "contents" not in output and "claimed_paths" not in output:
            return ["builder envelope missing fill"]
        return []
    return _gate


def _outside_claim(output: dict, workflow_id: str) -> str:
    prefix = f"adws/built/{workflow_id}/"
    claimed = output.get("claimed_paths") or []
    for item in claimed:
        path = item.get("path") if isinstance(item, dict) else str(item)
        if path and not str(path).startswith(prefix):
            return f"diff_claims_real: path outside allowlist: {path}"
    return ""


def _pytest_log(run: Run) -> str:
    chunks = []
    for path in (run.dir / "validate" / "pytest.log", run.dir / "validate-after-stamp" / "pytest.log"):
        if path.is_file():
            chunks.append(path.read_text())
    return "\n".join(chunks)


def _prove_requirements(spec: dict, pytest_log: str) -> None:
    """Verified means the declared verifier ran. Unsupported totals stay blocked."""
    root = built_dir(spec["id"])
    test_path = root / "tests" / f"test_{spec['id'].replace('-', '_')}.py"
    test_code = test_path.read_text() if test_path.is_file() else ""
    gate_src = (root / "gates.py").read_text() if (root / "gates.py").is_file() else ""
    for req in spec.get("requirements") or []:
        if req.get("blocker"):
            req["status"] = "blocked"
            continue
        expected = gates.exact_number(str(req.get("text") or ""))
        if expected is not None and str(expected) not in gate_src:
            req["status"] = "blocked"
            req["blocker"] = (
                f"unsupported semantics: gate {req.get('gate')} does not verify the total equals exactly {expected}"
            )
            continue
        verifier = str(req.get("verifier") or "")
        if f"def {verifier}(" not in test_code or verifier not in pytest_log:
            req["status"] = "blocked"
            req["blocker"] = f"verifier {verifier or '<missing>'} was not executed"
            continue
        req["status"] = "verified"
        req["evidence"] = [f"pytest:{verifier}"]


def _preserve(run: Run, spec: dict) -> None:
    snap = run.dir / "built-snapshot"
    root = built_dir(spec["id"])
    if root.exists():
        if snap.exists():
            shutil.rmtree(snap)
        shutil.copytree(root, snap)
        scaffold.remove_built(spec)


if __name__ == "__main__":
    sys.exit(main())
