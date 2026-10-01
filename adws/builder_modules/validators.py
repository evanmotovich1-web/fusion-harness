"""Validators for a generated workflow. Fresh run after the last mutation."""

from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path

from .paths import ROOT
from .scaffold import destination, python_files

BANNED = (
    re.compile(r"\bgit\s"),
    re.compile(r"\brequests\b"),
    re.compile(r"\burllib\b"),
    re.compile(r"http\.client"),
    re.compile(r"https?://"),
)


def compile_python(spec: dict) -> list[str]:
    errors = []
    for path in python_files(spec):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"py_compile: {path.name}: {exc.msg}")
    return errors


def grep_gate(spec: dict) -> list[str]:
    errors = []
    for path in python_files(spec):
        text = path.read_text()
        for pattern in BANNED:
            if pattern.search(text):
                errors.append(f"grep-gate: {path.name} matches {pattern.pattern}")
    return errors


def run_generated(spec: dict, reports: Path, db: Path, bad_first: bool = False) -> tuple[int, str]:
    entry_rel = spec["artifacts"]["entrypoint"]
    entry = destination(spec, entry_rel)
    reports.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(entry), "--fixtures", "--stub-agents", "--db", str(db), "--reports-dir", str(reports)]
    if bad_first:
        argv.append("--stub-bad-first")
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=40, stdin=subprocess.DEVNULL, check=False)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def agent_gate_lines(log: str, spec: dict) -> list[str]:
    errors = []
    for phase in spec["phases"]:
        if phase.get("kind") != "agent":
            continue
        needle = f"AGENT {phase['owner']} → GATE {phase['gate']}"
        if needle not in log:
            errors.append(f"log missing {needle}")
    return errors


def bad_first_retried(log: str) -> list[str]:
    errors = []
    if "FAIL" not in log:
        errors.append("bad-first log has no FAIL")
    if "SOFT NOTICE:" not in log:
        errors.append("bad-first log has no SOFT NOTICE")
    if "result must be a nonempty string" not in log:
        errors.append("soft notice does not carry the gate failure text")
    if "PASS" not in log.split("SOFT NOTICE:")[-1]:
        errors.append("bad-first did not PASS after the soft notice")
    return errors


def pytest_python() -> str:
    """Prefer an interpreter that already has pytest. Does not install anything."""
    env = os.environ.get("ADW_PYTHON")
    candidates = [env, sys.executable, str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "homecare" / ".venv" / "bin" / "python")]
    for candidate in candidates:
        if not candidate:
            continue
        if candidate != sys.executable and not Path(candidate).is_file():
            continue
        probe = subprocess.run([candidate, "-c", "import pytest"], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL, check=False)
        if probe.returncode == 0:
            return candidate
    return sys.executable


def run_pytest(spec: dict) -> tuple[int, str]:
    tests = destination(spec, f"adws/built/{spec['id']}/tests/test_{spec['id'].replace('-', '_')}.py").parent
    proc = subprocess.run(
        [pytest_python(), "-m", "pytest", str(tests), "-v", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=45, stdin=subprocess.DEVNULL, check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def validate_tree(spec: dict, work: Path) -> list[str]:
    errors = compile_python(spec) + grep_gate(spec)
    code, log = run_generated(spec, work / "good", work / "good.db", bad_first=False)
    (work / "good.log").write_text(log)
    if code != 0:
        errors.append(f"generated stub run exited {code}")
    errors.extend(agent_gate_lines(log, spec))
    code, blog = run_generated(spec, work / "bad", work / "bad.db", bad_first=True)
    (work / "bad.log").write_text(blog)
    if code != 0:
        errors.append(f"generated bad-first run exited {code}")
    errors.extend(bad_first_retried(blog))
    pcode, plog = run_pytest(spec)
    (work / "pytest.log").write_text(plog)
    if pcode != 0:
        errors.append(f"pytest exited {pcode}: {plog[-500:]}")
    return errors
