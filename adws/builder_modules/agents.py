"""PiRunner / StubRunner split, disk prompts, bounded gate retries, soft notices.

The path check below is a pre-write allowlist, not a sandbox. Bash is audited
after the attempt from the JSONL the runner wrote.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import KNOWN_TOOLS, ROOT, fixtures_dir, model_name, thinking_name
from .prompts import load_prompt_files, render
from .synthesize import reviewer_envelope, scout_envelope, synthesize_spec

PI_PATH = "pi"
JSON_RETRIES = 2


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _inside_repo(raw: str) -> bool:
    try:
        resolved = Path(raw).resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _persist_stdout_envelope(stdout: str, output: Path) -> None:
    """Write-less seats never touch the disk. Keep the last JSON object from pi stdout."""
    if output.is_file() and output.stat().st_size:
        return
    last = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            last = event
    if not isinstance(last, dict):
        return
    text = last.get("text") or last.get("message") or ""
    if isinstance(text, str) and text.strip().startswith("{"):
        output.write_text(text.strip() + "\n")
        return
    if any(key in last for key in ("patterns", "schema_version", "verdict", "fill")):
        output.write_text(json.dumps(last) + "\n")
MAX_GATE_ATTEMPTS = 3
OUTSIDE_STEMS = {"out-of-scope-write", "out_of_scope_write", "out-of-scope"}
SHELL_BAD = {"&&", "||", ";", "|", ">", ">>", "<", "&"}


@dataclass
class AgentCall:
    agent: str
    attempt: int
    system: str
    prompt: str
    argv: list[str]
    output_path: Path
    log_path: Path
    pi_tools: list[str]
    write_targets: list[Path]


def fixture_file(agent: str, good: bool, tag: str, root: Path | None = None) -> Path | None:
    directory = root or fixtures_dir()
    name = f"{'good' if good else 'bad'}_{agent}"
    if tag:
        tagged = directory / f"{name}.{tag}.json"
        if tagged.is_file():
            return tagged
        # A shared good_*.json must not answer a named refusal/blocker fixture.
        if tag in OUTSIDE_STEMS or tag in {"unmeetable", "unmeetable-requirement", "unmeetable_requirement", "memory_search", "memory-search"}:
            return None
    plain = directory / f"{name}.json"
    return plain if plain.is_file() else None


def synthetic_output(agent: str, request: str, stem: str, spec: dict | None, good: bool) -> dict:
    if not good:
        return {"_invalid": True, "failure": f"{agent}: fixture gate failed — schema missing requirements"}
    if agent == "workflow_scout":
        return scout_envelope()
    if agent == "spec_writer":
        return synthesize_spec(request, stem)
    if agent == "reviewer":
        return reviewer_envelope(spec or {"requirements": []})
    if stem in OUTSIDE_STEMS:
        return {
            "fill": "refused",
            "claimed_paths": ["adws/adw_workflow_builder.py"],
            "failure": "diff_claims_real: path outside allowlist: adws/adw_workflow_builder.py",
        }
    return {"fill": "from_spec", "summary": "deterministic fill from the approved spec", "claimed_paths": []}


class StubRunner:
    """Zero keys, zero network. Fixture JSON if present, otherwise a deterministic envelope."""

    name = "stub"

    def __init__(self, bad_first: bool = False, tag: str = "", request: str = "", fixtures: Path | None = None):
        self.bad_first = bad_first
        self.tag = tag
        self.request = request
        self.fixtures = fixtures
        self.spec: dict | None = None

    def run(self, call: AgentCall) -> None:
        good = not (self.bad_first and call.attempt == 1)
        path = fixture_file(call.agent, good, self.tag, self.fixtures)
        if path is not None:
            payload = json.loads(path.read_text())
        else:
            payload = synthetic_output(call.agent, self.request, self.tag, self.spec, good)
        if call.agent == "spec_writer" and good and isinstance(payload, dict) and payload.get("schema_version") == 1:
            self.spec = payload
        call.output_path.write_text(json.dumps(payload, indent=2))
        events = [
            {"type": "agent_start", "stub": True, "model": "unknown"},
            {"type": "tool_execution_start", "toolCallId": f"{call.agent}-{call.attempt}-read",
             "toolName": "read", "args": {"path": "adws/specs/prior-adw-patterns.md"}, "ok": True},
        ]
        if "write" in call.pi_tools:
            target = call.write_targets[0] if call.write_targets else call.output_path
            events.append({
                "type": "tool_execution_start", "toolCallId": f"{call.agent}-{call.attempt}-write",
                "toolName": "write", "args": {"path": str(target)}, "ok": True,
            })
        events.append({"type": "agent_end", "stub": True, "usage": None})
        with call.log_path.open("a") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")


class PiRunner:
    """Live headless pi. Not used in stub mode. This is not a network client by itself."""

    name = "pi"

    def __init__(self, timeout_s: int = 120):
        self.timeout_s = timeout_s

    def run(self, call: AgentCall) -> None:
        proc = subprocess.Popen(
            call.argv, cwd=str(ROOT), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_s)
        except subprocess.TimeoutExpired as exc:
            _kill_group(proc)
            raise TimeoutError(f"pi timed out after {self.timeout_s}s") from exc
        with call.log_path.open("a") as handle:
            if stdout:
                handle.write(stdout if stdout.endswith("\n") else stdout + "\n")
        _persist_stdout_envelope(stdout or "", call.output_path)
        if proc.returncode != 0:
            raise RuntimeError(f"pi exited {proc.returncode}: {(stderr or '')[-800:]}")


def resolve_model(model: str | None = None) -> tuple[str, str]:
    provider, model_id = (model or model_name()).split("/", 1)
    out = subprocess.run(
        [PI_PATH, "--list-models"], capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL, check=False,
    ).stdout
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 2 and cols[0] == provider and cols[1] == model_id:
            return provider, model_id
    raise RuntimeError(f"model {model or model_name()!r} is not in `pi --list-models`")


def build_argv(model: str, thinking: str, tools: list[str], system: str, prompt: str,
               session_id: str, session_dir: str) -> list[str]:
    provider, model_id = model.split("/", 1)
    return [
        PI_PATH, "-p", "--mode", "json", "--provider", provider, "--model", model_id,
        "--thinking", thinking, "--session-id", session_id, "--session-dir", session_dir,
        "--system-prompt", system, "--tools", ",".join(tools), prompt,
    ]


def _tool_error(event: dict) -> str | None:
    if event.get("error"):
        return str(event["error"])[:500]
    result = event.get("result")
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    return str(item["text"])[:500]
        if result.get("error"):
            return str(result["error"])[:500]
    if event.get("isError") is True:
        return "tool error"
    return None


def _result_ref(event: dict) -> str | None:
    result = event.get("result")
    if result is None:
        return None
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return text[:500]


def tool_calls(log_path: Path) -> list[dict]:
    """Join tool starts and ends by call id. A start without an end stays incomplete."""
    by_id: dict[str, dict] = {}
    order: list[str] = []
    if not log_path.is_file():
        return []
    for line in log_path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind == "tool_execution_start":
            key = event.get("toolCallId") or f"anon-{len(order)}"
            if key in by_id:
                continue
            ok = event.get("ok")
            record = {
                "call_id": key,
                "tool": event.get("toolName"),
                "args": event.get("args") or {},
                "ok": ok if isinstance(ok, bool) else None,
                "completion": "complete" if isinstance(ok, bool) else "incomplete",
                "error": event.get("error"),
                "started_at": event.get("started_at") or event.get("timestamp"),
                "ended_at": None,
                "duration_ms": event.get("duration_ms"),
                "result_ref": None,
            }
            by_id[key] = record
            order.append(key)
            continue
        if kind != "tool_execution_end":
            continue
        key = event.get("toolCallId") or f"anon-end-{len(order)}"
        record = by_id.get(key)
        if record is None:
            record = {
                "call_id": key,
                "tool": event.get("toolName"),
                "args": event.get("args") or {},
                "ok": None,
                "completion": "incomplete",
                "error": None,
                "started_at": None,
                "ended_at": None,
                "duration_ms": None,
                "result_ref": None,
            }
            by_id[key] = record
            order.append(key)
        is_error = event.get("isError")
        if is_error is True:
            record["ok"] = False
            record["error"] = _tool_error(event)
        elif is_error is False:
            record["ok"] = True
            record["error"] = None
        elif isinstance(event.get("ok"), bool):
            record["ok"] = event["ok"]
            if event["ok"] is False:
                record["error"] = _tool_error(event)
        record["completion"] = "complete"
        record["ended_at"] = event.get("ended_at") or event.get("timestamp")
        if event.get("duration_ms") is not None:
            record["duration_ms"] = event["duration_ms"]
        record["result_ref"] = _result_ref(event)
        if record.get("tool") is None:
            record["tool"] = event.get("toolName")
    return [by_id[key] for key in order]


def audit_calls(calls: list[dict], pi_tools: list[str], write_targets: list[Path]) -> list[str]:
    """Post-phase audit. Honest limit: this sees the recorded calls, not a sandbox."""
    problems = []
    allowed = set(pi_tools)
    targets = {path.resolve() for path in write_targets}
    for call in calls:
        tool = call.get("tool")
        if tool not in allowed or tool not in KNOWN_TOOLS:
            problems.append(f"tool {tool!r} is not in the seat allowlist")
            continue
        args = call.get("args") or {}
        if tool in {"write", "edit"}:
            raw = str(args.get("path") or args.get("file_path") or "")
            if not raw:
                problems.append(f"{tool} missing path")
                continue
            if Path(raw).resolve() not in targets:
                problems.append(f"{tool} to {raw} is outside the path allowlist")
        if tool == "bash":
            problems.extend(_audit_bash(str(args.get("command") or ""), write_targets))
        if tool in {"find", "grep", "ls", "read"}:
            raw = str(args.get("path") or "")
            if raw.startswith("/") and not _inside_repo(raw):
                problems.append(f"{tool} path {raw} is outside the repo")
    return problems


def _audit_bash(command: str, write_targets: list[Path]) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return [f"bash is not a parseable command: {exc}"]
    if any(token in SHELL_BAD for token in tokens):
        return ["bash contains a shell operator; only a single argv is allowed"]
    if not tokens:
        return ["bash command is empty"]
    if tokens[0] in {"git", "ssh", "curl", "wget"}:
        return [f"bash command {tokens[0]!r} is not an allowed shape"]
    joined = " ".join(tokens)
    if "git " in f"{joined} ":
        return ["bash command contains git"]
    return []


def allow_write(path: Path, roots: list[Path]) -> bool:
    """Pre-write allowlist wrapper. Not a sandbox."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            base = root.resolve()
        except OSError:
            continue
        if resolved == base or base in resolved.parents:
            return True
    return False


def _common_ancestor(left: Path, right: Path) -> Path:
    shared = []
    for part, other in zip(left.resolve().parts, right.resolve().parts):
        if part != other:
            break
        shared.append(part)
    return Path(*shared) if shared else left.parent


def mutation_watch_root(run_dir: Path) -> Path:
    """Parent that contains both the run dir and the built root. Not the whole disk."""
    from .paths import built_root

    ancestor = _common_ancestor(run_dir, built_root())
    if len(ancestor.parts) < 3:
        return run_dir.resolve().parent
    return ancestor


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return found
    skip = {"__pycache__", ".git", "node_modules"}
    for path in root.rglob("*"):
        if skip.intersection(path.parts) or not path.is_file():
            continue
        if path.suffix == ".pyc" or path.name.endswith(("-journal", "-wal", "-shm")):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        found[str(path.resolve())] = (stat.st_mtime_ns, stat.st_size)
    return found


def allowed_mutation_roots(run_dir: Path, write_targets: list[Path]) -> list[Path]:
    """Run dir plus the built workflow directory named by a write target. Not a sandbox."""
    from .paths import built_root, inside

    roots = [run_dir.resolve()]
    built = built_root().resolve()
    for target in write_targets:
        try:
            resolved = target.resolve()
        except OSError:
            continue
        if inside(resolved, built):
            relative = resolved.relative_to(built)
            if relative.parts:
                roots.append(built / relative.parts[0])
        elif resolved.is_dir():
            roots.append(resolved)
        else:
            roots.append(resolved.parent)
    return roots


def unclaimed_writes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]],
                     roots: list[Path]) -> list[str]:
    """Files created or changed outside the allowlist during an agent attempt."""
    problems = []
    for raw, signature in after.items():
        if before.get(raw) == signature:
            continue
        path = Path(raw)
        if allow_write(path, roots):
            continue
        problems.append(str(path))
    return problems


@dataclass
class AttemptRecord:
    attempt: int
    passed: bool
    failures: list[str]
    calls: list[dict]
    duration_ms: int


@dataclass
class PhaseResult:
    output: dict | None
    failures: list[str]
    attempts: int
    passed: bool
    history: list[AttemptRecord] = field(default_factory=list)


@dataclass
class PhaseRunner:
    runner: object
    run_dir: Path
    log: object
    request: str
    stem: str
    model: str = field(default_factory=model_name)
    thinking: str = field(default_factory=thinking_name)
    stub: bool = True

    def run(self, agent: str, batch: dict, write_targets: list[Path], gate) -> PhaseResult:
        files = load_prompt_files(agent)
        tools = files["tools"]
        pi_tools = list(tools.get("pi_tools") or [])
        output = self.run_dir / f"{agent}.output.json"
        from .paths import PATTERNS_PATH
        values = {
            "agent": agent,
            "request": self.request,
            "output_path": str(output.resolve()),
            "patterns_path": str(PATTERNS_PATH.resolve()),
            "repo_root": str(ROOT.resolve()),
            "batch_json": json.dumps(batch, indent=2),
            "failures": "",
        }
        system = render(files["system.md"], values)
        user = render(files["user.md"], values)
        log_path = self.run_dir / f"{agent}.jsonl"
        session = self.run_dir.name + "-" + agent
        previous = None
        last_failures: list[str] = []
        last_output = None
        history: list[AttemptRecord] = []
        for attempt in range(1, MAX_GATE_ATTEMPTS + 1):
            prompt_path = self.run_dir / f"{agent}.attempt{attempt}.prompt.md"
            prompt_path.write_text(user if attempt == 1 else render(files["soft_notice.md"], {**values, "failures": "\n".join(f"- {f}" for f in last_failures)}))
            prompt = prompt_path.read_text()
            argv = [] if self.stub else build_argv(
                self.model, self.thinking, pi_tools, system, prompt, session, str(self.run_dir / "sessions"),
            )
            self.log(f"AGENT {agent} attempt {attempt} ({self.runner.name})")
            output.unlink(missing_ok=True)
            before = len(tool_calls(log_path))
            watch = mutation_watch_root(self.run_dir)
            allowed = allowed_mutation_roots(self.run_dir, write_targets)
            before_fs = _snapshot(watch)
            started = time.perf_counter()
            try:
                self.runner.run(AgentCall(
                    agent, attempt, system, prompt, argv, output, log_path, pi_tools, write_targets,
                ))
            except (TimeoutError, RuntimeError, OSError) as exc:
                elapsed = max(1, int((time.perf_counter() - started) * 1000))
                history.append(AttemptRecord(attempt, False, [str(exc)], [], elapsed))
                self.log(f"AGENT {agent} → GATE {agent} FAIL")
                self.log(f"SOFT NOTICE: runner failed: {exc}")
                return PhaseResult(None, [f"runner failed: {exc}"], attempt, False, history)
            calls = tool_calls(log_path)[before:]
            mutated = unclaimed_writes(before_fs, _snapshot(watch), allowed)
            try:
                last_output = json.loads(output.read_text())
                last_failures = list(gate(last_output))
            except (OSError, json.JSONDecodeError) as exc:
                last_output = None
                last_failures = [f"no valid JSON at {output.name}: {exc}"]
            last_failures.extend(audit_calls(calls, pi_tools, write_targets))
            for path in mutated:
                last_failures.append(f"diff_claims_real: unclaimed write outside allowlist: {path}")
            elapsed = max(1, int((time.perf_counter() - started) * 1000))
            history.append(AttemptRecord(attempt, not last_failures, list(last_failures), calls, elapsed))
            if not last_failures:
                self.log(f"AGENT {agent} → GATE {agent} PASS")
                self.log(f"GATE  {agent} attempt {attempt} PASS")
                return PhaseResult(last_output, [], attempt, True, history)
            self.log(f"AGENT {agent} → GATE {agent} FAIL")
            self.log("GATE  " + agent + f" attempt {attempt} FAIL:\n" + "\n".join(f"        - {f}" for f in last_failures))
            notice = "\n".join(last_failures)
            self.log(f"SOFT NOTICE: {notice}")
            if last_failures == previous:
                self.log(f"GATE  {agent} no-progress — same failures twice")
                return PhaseResult(last_output, last_failures, attempt, False, history)
            previous = list(last_failures)
            if attempt > JSON_RETRIES and any("no valid JSON" in item for item in last_failures):
                return PhaseResult(last_output, last_failures, attempt, False)
        return PhaseResult(last_output, last_failures, MAX_GATE_ATTEMPTS, False, history)
