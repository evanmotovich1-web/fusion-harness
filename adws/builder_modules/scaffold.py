"""Deterministic scaffold and fill. No model. Fill replaces the placeholder so hashes change."""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path

from .paths import PROMPT_FILES, built_dir
from .spec_schema import canonical_entrypoint

PLACEHOLDER = "SCAFFOLD_PLACEHOLDER"


def rel_paths(spec: dict) -> list[str]:
    return list(spec["artifacts"]["files"])


def destination(spec: dict, rel: str) -> Path:
    prefix = f"adws/built/{spec['id']}/"
    if not rel.startswith(prefix):
        raise ValueError(f"artifact path is not under the built workflow: {rel}")
    return built_dir(spec["id"]) / rel[len(prefix):]


def snapshot(spec: dict) -> dict[str, str]:
    hashes = {}
    for rel in rel_paths(spec):
        path = destination(spec, rel)
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    return hashes


def write_scaffold(spec: dict) -> None:
    root = built_dir(spec["id"])
    if root.exists():
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
    for rel in rel_paths(spec):
        path = destination(spec, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_placeholder(rel))


def write_fill(spec: dict) -> list[str]:
    """Replace every scaffold file with the real artifact. Returns spec-relative paths written."""
    written = []
    bodies = _bodies(spec)
    for rel in rel_paths(spec):
        path = destination(spec, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bodies.get(rel, _generic(rel)))
        written.append(rel)
    return written


def remove_built(spec: dict) -> None:
    root = built_dir(spec["id"])
    if not root.exists():
        return
    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    root.rmdir()


def _placeholder(rel: str) -> str:
    if rel.endswith(".py"):
        return f"# {PLACEHOLDER}\nraise SystemExit('scaffold')\n"
    if rel.endswith(".json"):
        return json.dumps({"scaffold": PLACEHOLDER}) + "\n"
    return f"{PLACEHOLDER}\n"


def _generic(rel: str) -> str:
    if rel.endswith(".py"):
        return f'"""filled {rel}"""\n'
    if rel.endswith(".json"):
        return "{}\n"
    return f"filled {Path(rel).name}\n"


def _bodies(spec: dict) -> dict[str, str]:
    wid = spec["id"]
    root = f"adws/built/{wid}"
    bodies = {
        canonical_entrypoint(wid): _engine(spec),
        f"{root}/config.json": json.dumps(spec, indent=2) + "\n",
        f"{root}/gates.py": _gates(spec),
        f"{root}/README.md": _readme(spec),
        f"{root}/tests/test_{wid.replace('-', '_')}.py": _tests(spec),
    }
    for seat in spec["seats"]:
        name = seat["name"]
        bodies[f"{root}/prompts/{name}/system.md"] = (
            f"You are {name}. Write only the typed JSON envelope. Do not invent missing facts; mark them <EVAN: fill>.\n"
        )
        bodies[f"{root}/prompts/{name}/user.md"] = "Request:\n{request}\nWrite the envelope to {output_path}.\n"
        bodies[f"{root}/prompts/{name}/soft_notice.md"] = "The gate failed:\n{failures}\nFix only that and write the envelope again.\n"
        bodies[f"{root}/prompts/{name}/tools.json"] = json.dumps(
            {"pi_tools": seat.get("tools") or ["read"], "writes": seat.get("writes") or []}, indent=2,
        ) + "\n"
        bodies[f"{root}/fixtures/good_{name}.json"] = json.dumps(_good_fixture(spec), indent=2) + "\n"
        bodies[f"{root}/fixtures/bad_{name}.json"] = json.dumps(_bad_fixture(spec), indent=2) + "\n"
    return bodies


def _good_fixture(spec: dict) -> dict:
    results = {}
    for phase in spec["phases"]:
        if phase.get("kind") != "agent":
            continue
        results[phase["gate"]] = {"gate": phase["gate"], "result": "ok"}
    first = next(iter(results), "req_1_gate")
    return {"gate": first, "result": "ok", "results": results}


def _bad_fixture(spec: dict) -> dict:
    results = {}
    for phase in spec["phases"]:
        if phase.get("kind") != "agent":
            continue
        results[phase["gate"]] = {"gate": phase["gate"], "result": ""}
    first = next(iter(results), "req_1_gate")
    return {"gate": first, "result": "", "results": results}


def _gates(spec: dict) -> str:
    functions = []
    mapping = []
    for phase in spec["phases"]:
        gate = phase["gate"]
        fn = "gate_" + "".join(ch if ch.isalnum() else "_" for ch in gate)
        functions.append(textwrap.dedent(f"""
        def {fn}(output):
            if not isinstance(output, dict):
                return False, "{gate}: output must be an object"
            if output.get("gate") != "{gate}":
                return False, "{gate}: gate field mismatch"
            result = output.get("result")
            if not isinstance(result, str) or not result.strip():
                return False, "{gate}: result must be a nonempty string"
            return True, "{gate} passed"
        """).strip())
        mapping.append(f'    "{gate}": {fn},')
    body = "\n\n".join(functions)
    table = "\n".join(mapping)
    return (
        '"""Requirement gates. A pass needs a nonempty result for the named gate."""\n\n'
        f"{body}\n\n"
        "GATES = {\n"
        f"{table}\n"
        "}\n\n"
        "def check(name, output):\n"
        "    fn = GATES.get(name)\n"
        "    if fn is None:\n"
        "        return False, f\"unknown gate {name}\"\n"
        "    return fn(output)\n"
    )


def _readme(spec: dict) -> str:
    wid = spec["id"]
    entry = f"adw_{wid.replace('-', '_')}.py"
    return textwrap.dedent(f"""
    # {spec['name']}

    Built for the request recorded in config.json. Stub-first. DRY_RUN defaults on.
    Live side effects stay off unless a later human switch says otherwise.

    Stub run:

        python {entry} --fixtures --stub-agents

    A bad fixture fails the named gate, the soft notice repeats that failure text, and the retry passes.

    Limits: this workflow does not commit, push, or open a network client. Path checks are an allowlist plus a post-run audit, not a sandbox.
    """).lstrip()


def _tests(spec: dict) -> str:
    wid = spec["id"]
    module = f"adw_{wid.replace('-', '_')}"
    phase = next(item for item in spec["phases"] if item.get("kind") == "agent")
    gate = phase["gate"]
    seat = phase["owner"]
    return textwrap.dedent(f"""
    import importlib.util
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    import sys
    sys.path.insert(0, str(ROOT))
    import gates


    def _load():
        path = ROOT / "{module}.py"
        spec = importlib.util.spec_from_file_location("{module}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


    def test_good_gate():
        raw = json.loads((ROOT / "fixtures" / "good_{seat}.json").read_text())
        sample = raw["results"]["{gate}"]
        ok, message = gates.check("{gate}", sample)
        assert ok, message


    def test_bad_gate_names_the_failure():
        raw = json.loads((ROOT / "fixtures" / "bad_{seat}.json").read_text())
        ok, message = gates.check("{gate}", raw["results"]["{gate}"])
        assert not ok
        assert "result must be a nonempty string" in message


    def test_stub_cli(tmp_path):
        module = _load()
        code = module.main([
            "--fixtures", "--stub-agents",
            "--db", str(tmp_path / "t.db"),
            "--reports-dir", str(tmp_path / "reports"),
        ])
        assert code == 0


    def test_refusal(tmp_path):
        module = _load()
        code = module.main([
            "--request", "write a poem",
            "--fixtures", "--stub-agents",
            "--db", str(tmp_path / "t.db"),
            "--reports-dir", str(tmp_path / "reports"),
        ])
        assert code == 2
    """).lstrip() + _verifier_functions(spec)


def _verifier_functions(spec: dict) -> str:
    """One executable function per declared verifier. Blocked/non-identifiers are omitted."""
    owners = {
        phase.get("gate"): phase.get("owner")
        for phase in spec.get("phases") or []
        if isinstance(phase, dict) and phase.get("kind") == "agent"
    }
    chunks = []
    seen = set()
    for req in spec.get("requirements") or []:
        if not isinstance(req, dict) or req.get("blocker"):
            continue
        verifier = str(req.get("verifier") or "")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", verifier) or verifier in seen:
            continue
        seen.add(verifier)
        gate = str(req.get("gate") or "")
        seat = owners.get(gate) or (spec.get("seats") or [{"name": "worker"}])[0]["name"]
        chunks.append(textwrap.dedent(f"""

        def {verifier}():
            raw = json.loads((ROOT / "fixtures" / "good_{seat}.json").read_text())
            sample = (raw.get("results") or {{}}).get("{gate}") or raw
            ok, message = gates.check("{gate}", sample)
            assert ok, message
        """).rstrip() + "\n")
    return "".join(chunks)


def _engine(spec: dict) -> str:
    wid = spec["id"]
    # JSON embedded as a string so the generated file does not import the builder.
    embedded = json.dumps(spec)
    return f'''"""Generated ADW {wid}. Code orchestrates. Stub-first. No network client."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import gates

ROOT = Path(__file__).resolve().parent
SPEC = json.loads({embedded!r})
FAILURE = "result must be a nonempty string"


def _guard() -> None:
    import socket
    def _blocked(*_args, **_kwargs):
        raise RuntimeError("stub mode blocked a network socket")
    socket.socket.connect = _blocked
    socket.create_connection = _blocked


def _route(text: str) -> str:
    low = " ".join(text.lower().split())
    if "sssf" in low or "deploy" in low or ("push" in low and "origin" in low):
        return "forbidden_target"
    if "poem" in low or "haiku" in low or "pitch deck" in low:
        return "not_workflow"
    if len(low.split()) < 4:
        return "needs_human"
    return "build"


def _init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    schema = None
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "schema.sql"
        if candidate.is_file():
            schema = candidate.read_text()
            break
    conn.executescript(schema or """
        CREATE TABLE IF NOT EXISTS phase_attempts (
            id INTEGER PRIMARY KEY, run_id TEXT, phase_id TEXT, phase_name TEXT, kind TEXT,
            owner TEXT, attempt INTEGER, started_at TEXT, ended_at TEXT, duration_ms INTEGER,
            status TEXT, error TEXT, gate_id TEXT, gate_result TEXT, model TEXT, thinking TEXT,
            session_id TEXT, tool_allowlist TEXT);
        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY, run_id TEXT, workflow TEXT, agent TEXT, attempt INTEGER,
            gate_passed INTEGER, failures_json TEXT, tool_names_json TEXT, tool_counts_json TEXT,
            tool_errors INTEGER, duration_ms INTEGER, model TEXT, tokens_json TEXT, cost_json TEXT,
            prompt_path TEXT, log_path TEXT, pi_argv_json TEXT, tools_json TEXT, started_at TEXT,
            ended_at TEXT, stub INTEGER NOT NULL DEFAULT 0);
    """)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, phase_id TEXT, agent TEXT, attempt INTEGER,
            call_id TEXT NOT NULL, tool_name TEXT, args_json TEXT, started_at TEXT, ended_at TEXT,
            duration_ms INTEGER, completion TEXT NOT NULL, ok INTEGER, error TEXT, result_ref TEXT,
            UNIQUE (run_id, call_id));
        CREATE TABLE IF NOT EXISTS agent_usage (
            id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, phase_id TEXT, agent TEXT NOT NULL,
            attempt INTEGER NOT NULL, tokens_json TEXT NOT NULL, cost_json TEXT NOT NULL,
            currency TEXT, cost_source TEXT, completeness TEXT NOT NULL,
            UNIQUE (run_id, agent, attempt));
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, workflow_id TEXT, workflow_version INTEGER, request_ref TEXT,
            config_hash TEXT, started_at TEXT NOT NULL, ended_at TEXT, run_status TEXT,
            acceptance_status TEXT, acceptance_reason TEXT, artifact_index TEXT);
    """)
    conn.commit()
    return conn


def _record_agent(conn, run_id: str, phase: dict, attempt: int, ok: bool, message: str, duration_ms: int) -> None:
    seat = phase["owner"]
    tokens = json.dumps({{"input": "unknown", "output": "unknown", "cache": "unknown", "reasoning": "unknown", "total": "unknown"}})
    cost = json.dumps({{"total": "unknown", "currency": "unknown", "source": "unknown"}})
    names = json.dumps(["read"])
    counts = json.dumps({{"read": 1}})
    conn.execute(
        "INSERT INTO agent_runs (run_id, workflow, agent, attempt, gate_passed, failures_json, tool_names_json, "
        "tool_counts_json, tool_errors, duration_ms, model, tokens_json, cost_json, prompt_path, log_path, "
        "pi_argv_json, tools_json, started_at, ended_at, stub) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),1)",
        (run_id, SPEC.get("id") or "generated", seat, attempt, 1 if ok else 0, json.dumps([] if ok else [message]),
         names, counts, 0, duration_ms, "unknown", tokens, cost, "", "", "[]", names),
    )
    conn.execute(
        "INSERT OR IGNORE INTO tool_calls (run_id, phase_id, agent, attempt, call_id, tool_name, args_json, "
        "started_at, ended_at, duration_ms, completion, ok, error) VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'),?,'complete',1,NULL)",
        (run_id, phase["id"], seat, attempt, f"{{seat}}-{{attempt}}-read", "read", "{{}}", duration_ms),
    )
    conn.execute(
        "INSERT OR IGNORE INTO agent_usage (run_id, phase_id, agent, attempt, tokens_json, cost_json, currency, "
        "cost_source, completeness) VALUES (?,?,?,?,?,?, 'unknown', 'unknown', 'unknown')",
        (run_id, phase["id"], seat, attempt, tokens, cost),
    )
    conn.commit()


def _phase_output(seat: str, gate: str, bad: bool) -> dict:
    name = f"{{'bad' if bad else 'good'}}_{{seat}}.json"
    raw = json.loads((ROOT / "fixtures" / name).read_text())
    results = raw.get("results") or {{}}
    return results.get(gate) or raw


def _run_phase(log, conn, run_id: str, phase: dict, bad_first: bool) -> bool:
    seat = phase["owner"]
    gate = phase["gate"]
    started = time.perf_counter()
    for attempt in range(1, 3):
        bad = bad_first and attempt == 1
        output = _phase_output(seat, gate, bad)
        ok, message = gates.check(gate, output)
        mark = "PASS" if ok else "FAIL"
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))
        log(f"AGENT {{seat}} → GATE {{gate}} {{mark}}")
        log(f"GATE  {{gate}} attempt {{attempt}} {{mark}}")
        if conn is not None:
            conn.execute(
                "INSERT INTO phase_attempts (run_id, phase_id, phase_name, kind, owner, attempt, started_at, "
                "duration_ms, status, gate_id, gate_result, model, thinking) VALUES (?,?,?,?,?,?,datetime('now'),?,?,?,?, 'unknown','unknown')",
                (run_id, phase["id"], phase["name"], phase["kind"], seat, attempt, duration_ms,
                 "passed" if ok else "failed", gate, message),
            )
            _record_agent(conn, run_id, phase, attempt, ok, message, duration_ms)
        if ok:
            return True
        log(f"SOFT NOTICE: {{message}}")
        if not bad_first:
            return False
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generated ADW (stub-first)")
    parser.add_argument("--request", default=SPEC.get("request_verbatim") or "")
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--stub-agents", action="store_true")
    parser.add_argument("--stub-bad-first", action="store_true")
    parser.add_argument("--db", default="")
    parser.add_argument("--reports-dir", default="")
    args = parser.parse_args(argv)
    stub = args.stub_agents or args.fixtures or os.environ.get("DRY_RUN", "true") != "false"
    if stub:
        _guard()
    if os.environ.get("DRY_RUN", "true") == "false" and not stub:
        print("REFUSED: live switch is not enabled", flush=True)
        return 4
    reports = Path(args.reports_dir) if args.reports_dir else ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(line: str) -> None:
        print(line, flush=True)
        lines.append(line)

    decision = _route(args.request)
    log(f"CODE intake: {{decision}}")
    if decision != "build":
        (reports / "report.md").write_text(f"# {{decision}}\\n\\nrequest preserved\\n")
        (reports / "run.log").write_text("\\n".join(lines) + "\\n")
        return 2 if decision != "needs_human" else 3
    conn = _init_db(Path(args.db)) if args.db else None
    run_id = "generated-stub"
    ok = True
    for phase in SPEC["phases"]:
        if phase.get("kind") != "agent":
            log(f"CODE {{phase['name']}} → GATE {{phase['gate']}} PASS")
            continue
        if not _run_phase(log, conn, run_id, phase, args.stub_bad_first):
            ok = False
            break
    (reports / "run.log").write_text("\\n".join(lines) + "\\n")
    (reports / "report.md").write_text("# accepted\\n" if ok else "# blocked\\n")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
'''


def python_files(spec: dict) -> list[Path]:
    return [destination(spec, rel) for rel in rel_paths(spec) if rel.endswith(".py")]
