"""Read-only repository routing. All project filesystem IO runs in owned children.

Discovery is delegated to SSSF's deadline-bounded helper; this is not a crawler.
Only bounded public purpose metadata and opaque IDs cross the Jev boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import threading
import time

import jev_bridge

_DISCOVERY_LOCK = threading.Lock()
_CAP = 2 * 1024 * 1024
_SELF = os.path.abspath(__file__)


def _events(argv, payload=None, timeout=7):
    """Bounded JSONL capture; keep complete events even if a later stat blocks."""
    proc = None
    events, pending, total = [], b"", 0
    deadline = time.monotonic() + timeout
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                start_new_session=True, bufsize=0,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                                     "GIT_OPTIONAL_LOCKS": "0"})
        if payload is not None:
            # Payloads are small (catalog metadata is streamed back, not sent in).
            proc.stdin.write(json.dumps(payload).encode())
            proc.stdin.close()
        os.set_blocking(proc.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(proc.stdout.fileno(), min(65536, _CAP - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > _CAP:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    events.append(json.loads(line))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                pass
            proc.stdout.close()
    return events


def _workspace(workspace_root=None):
    if workspace_root is not None:
        return os.path.abspath(os.path.expanduser(str(workspace_root)))
    override = os.environ.get("OPENCODE_ADW_WORKSPACE_ROOT")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    # Fixed installer metadata only. Reading it is bounded with the same worker.
    events = _events([sys.executable, "-B", _SELF, "--manifest"], timeout=1)
    return events[0] if events and isinstance(events[0], str) else os.path.expanduser("~/code/sssf")


def _module(workspace):
    return os.path.join(workspace, "adws", "adw_modules", "opencode_discovery.py")


def status(workspace_root=None):
    workspace = _workspace(workspace_root)
    probe = _events([sys.executable, "-B", _SELF, "--probe", _module(workspace)], timeout=1)
    available = bool(probe and probe[0] is True)
    semantic = jev_bridge.status()
    return dict(available=available, semantic_configured=semantic["configured"],
                reason=semantic["reason"] if available else "discovery_unavailable")


def _discover(workspace):
    with _DISCOVERY_LOCK:
        events = _events([sys.executable, "-B", _SELF, "--discover", _module(workspace)], timeout=7)
    return events[0] if events and isinstance(events[0], dict) else {"repos": [], "truncated": True}


def _catalog(repos, request, preferred):
    # Order known contexts and exact names before the raw database, allowing useful
    # partial results if an unrelated filesystem mount blocks metadata collection.
    observed = {r["path"]: r.get("is_worktree") is True for r in repos[:1000]
                if isinstance(r, dict) and isinstance(r.get("path"), str)}
    paths = list(dict.fromkeys([p for p in preferred if p] + list(observed)))
    task_paths = _task_paths(request)
    paths.sort(key=lambda p: (p not in preferred,
                             not (p in task_paths or _mentioned(request, os.path.basename(p))),
                             observed.get(p, False)))
    return _events([sys.executable, "-B", _SELF, "--catalog"],
                   dict(paths=paths, discovered_roots=list(observed), request=request), timeout=6)


def _manual(path):
    """Probe only the supplied directory, without discovery or purpose reads."""
    return _events([sys.executable, "-B", _SELF, "--manual"], dict(path=path), timeout=1.5)


def _mentioned(request, name):
    return bool(name and re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w.-])", request, re.I))


def _task_paths(request):
    """Lexical intent only: never stat or read a path supplied in task text.

    Quoting preserves spaces. Single-component endpoints such as /health do not
    imply a repository unless introduced by 'repo' or 'repository'.
    """
    paths = []
    for match in re.finditer(r'''"([^"\n]+)"|'([^'\n]+)'|([^\s"']+)''', request):
        token = next(v for v in match.groups() if v is not None).rstrip(",;.!?)")
        if not token.startswith(("/", "~/")) and not re.match(r"[A-Za-z]:\\", token):
            continue
        intent = re.search(r"\brepo(?:sitory)?\s*$", request[:match.start()], re.I)
        supported = re.match(r"/(?:Users|home|private|tmp|var)/|~/|[A-Za-z]:\\", token)
        components = len([part for part in token.split("/") if part])
        if intent or supported or components >= 2:
            paths.append(os.path.normpath(os.path.expanduser(token)))
    return list(dict.fromkeys(paths))


def _exact_candidates(request, candidates):
    """Return checkout-specific matches before generic project aliases."""
    paths = _task_paths(request)
    if paths:
        matches = []
        for path in paths:
            found = [(c, p) for c in candidates for p in
                     dict.fromkeys([c["canonical_checkout"], *c["paths"]])
                     if path == p or path.startswith(p + os.sep)]
            if not found:
                return [], "unknown_explicit_path"
            # A nested Git root is more specific than its enclosing checkout.
            longest = max(len(p) for _, p in found)
            matches.extend(dict(c, selected_repo=p) for c, p in found if len(p) == longest)
        unique = {(c["id"], c["selected_repo"]): c for c in matches}
        return list(unique.values()), None
    # A remaining slash-prefixed token is an endpoint, not a bare-name alias.
    alias_request = re.sub(r'''(?<![\w])(?:~/|/)[^\s"']+''', " ", request)
    exact = []
    for candidate in candidates:
        aliases = [a for a in candidate["aliases"] if _mentioned(alias_request, a)]
        if not aliases:
            continue
        # The canonical project name is deliberately generic. A distinct linked
        # checkout basename, however, names that checkout rather than its group.
        specific = [p for p in candidate["paths"] if os.path.basename(p) != candidate["name"]
                    and os.path.basename(p) in aliases]
        exact.extend([dict(candidate, selected_repo=p) for p in specific] or [candidate])
    return exact, None


def _blocked(path):
    parts = re.split(r"[/\\]", path.lower())
    return any(p in {"archive", "archives", "archived", "parked", "retired",
                     "tradingview-mcp-jackson"} or p.startswith(("archive-", "retired-", "parked-"))
               for p in parts)


def _groups(rows, context, workspace):
    groups = {}
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("root", "common", "canonical")):
            continue
        if _blocked(row["root"]) or _blocked(row["canonical"]):
            continue
        group = groups.setdefault(row["common"], dict(
            id="project_" + hashlib.sha256(row["common"].encode()).hexdigest()[:16],
            name=os.path.basename(row["canonical"]), canonical_checkout=row["canonical"],
            paths=[], aliases=[], description="", selected_repo=row["canonical"]))
        if row["root"] not in group["paths"]:
            group["paths"].append(row["root"])
        for alias in (os.path.basename(row["root"]), group["name"]):
            if alias not in group["aliases"]:
                group["aliases"].append(alias)
        if not group["description"]:
            group["description"] = row.get("description", "")[:400]
    for group in groups.values():
        for preferred in (context, workspace):
            if preferred:
                # Resolve context symlinks through already-observed child output,
                # never through a potentially blocked parent filesystem lookup.
                observed = next((r["root"] for r in rows if r.get("input") == preferred), preferred)
                matches = [p for p in group["paths"] if observed == p or observed.startswith(p + os.sep)]
                if matches:
                    group["selected_repo"] = max(matches, key=len)
                    break
    return list(groups.values())


def _public(candidate):
    def text(value):
        # Never send local paths, assignment-shaped secrets or hash blobs.
        value = re.sub(r"(?<!\w)(?:~?/|[A-Za-z]:\\)\S+", "", value)
        return _clean(value).replace("/", " ").replace("\\", " ")[:400]
    return dict(id=candidate["id"], name=text(candidate["name"]),
                description=text(candidate["description"]),
                aliases=[text(a) for a in candidate["aliases"][:24]])


def resolve(request, *, context_directory=None, explicit_repo=None, receipt_dir, workspace_root=None):
    """Resolve automatically, or return one question and genuine project choices."""
    if not isinstance(request, str) or not request.strip() or len(request) > 32000:
        raise ValueError("request must be bounded nonempty text")
    folder = Path(receipt_dir).expanduser()
    if not folder.is_absolute() or folder.name != "routing":
        raise ValueError("receipt_dir must be an absolute run/routing directory")
    if folder.is_symlink() or folder.parent.is_symlink():
        raise jev_bridge.JevError("receipt_error")
    context = os.path.abspath(os.path.expanduser(str(context_directory))) if context_directory else None
    manual = explicit_repo is not None and str(explicit_repo).lower() != "auto"
    catalog_source = "explicit_git_probe" if manual else None
    semantic = None
    reason = None
    requested_path = resolved_git_root = None
    if manual:
        path = os.path.abspath(os.path.expanduser(str(explicit_repo)))
        requested_path = path
        rows = _manual(path)
        resolved_git_root = next((r["root"] for r in rows if r.get("input") == path), None)
        candidates = _groups(rows, path, None)
        # Preserve CLI compatibility: any actual directory inside a worktree is
        # accepted, but the result and core lock always use its actual Git root.
        valid = resolved_git_root is not None
        chosen = candidates[0] if valid and len(candidates) == 1 else None
        method = "explicit"
    else:
        workspace = _workspace(workspace_root)
        catalog_source = _module(workspace)
        discovery = _discover(workspace)
        rows = _catalog(discovery.get("repos", []), request, [context, workspace])
        candidates = _groups(rows, context, workspace)
        exact, path_error = _exact_candidates(request, candidates)
        chosen, method = None, "unresolved"
        if _mentioned(request, "tradingview-mcp-jackson"):
            method, reason = "excluded", "retired_read_only"
        elif path_error:
            method, reason = "unresolved", path_error
        elif len(exact) == 1:
            chosen, method = exact[0], "exact"
        elif len(exact) > 1:
            candidates, method = exact, "ambiguous"
        else:
            actual_context = next((r["root"] for r in rows if context is not None
                                   and r.get("input") == context), context)
            active = [c for c in candidates if actual_context and any(
                actual_context == p or actual_context.startswith(p + os.sep) for p in c["paths"])]
            if len(active) == 1:
                chosen, method = active[0], "context"
            elif candidates:
                # Relevance is retrieval only, never a fuzzy deterministic choice.
                words = set(re.findall(r"[a-z0-9]{3,}", request.lower()))
                def relevance(c):
                    return len(words & set(re.findall(r"[a-z0-9]{3,}",
                               (c["name"] + " " + c["description"]).lower())))
                candidates = sorted(candidates, key=lambda c: (-relevance(c), c["id"]))[:12]
                method = "semantic"
                try:
                    semantic = jev_bridge.select_repository(request, [_public(c) for c in candidates],
                                                            receipt_dir=folder.parent / "jev")
                    if semantic["status"] == "selected":
                        chosen = next((c for c in candidates if c["id"] == semantic["selected_id"]), None)
                except jev_bridge.JevError as exc:
                    reason = exc.reason
    if chosen:
        # Revalidate the final path in a bounded worker, including the canonical
        # checkout if only a linked worktree was present in the discovered catalog.
        verified = _manual(chosen["selected_repo"]) if manual else _catalog([], "", [chosen["selected_repo"]])
        root = next((r["root"] for r in verified if r.get("is_root")
                     and r.get("input") == chosen["selected_repo"]), None)
        if root is None or _blocked(root):
            chosen = None
            reason = "invalid_git_root"
        else:
            chosen = dict(chosen, selected_repo=root)
    candidates = ([chosen] + [c for c in candidates if c["id"] != chosen["id"]])[:12] if chosen else candidates[:12]
    choices = "; ".join(c["name"] + " (" + c["selected_repo"] + ")" for c in candidates)
    result = dict(status="resolved" if chosen else "needs_clarification",
                  selected_repo=chosen["selected_repo"] if chosen else None,
                  method=method, candidates=candidates,
                  question=None if chosen else "Which repository should handle this task? " +
                  ("Choose: " + choices if choices else "Provide an active Git repository root."),
                  receipt_path=None)
    if semantic is not None:
        result["jev"] = semantic
        result.update({k: semantic[k] for k in ("confidence", "probabilities", "model_requested",
                      "model_resolved", "input_tokens", "output_tokens", "elapsed_ms")})
    payload = dict(result, catalog_source=catalog_source, reason=reason,
                   request_sha256=hashlib.sha256(request.encode()).hexdigest())
    if manual:
        payload.update(requested_path=requested_path, resolved_git_root=resolved_git_root)
    else:
        payload["catalog_status"] = next((r for r in rows if r.get("event") == "catalog_status"),
                                         dict(complete=False, reason="worker_incomplete"))
    result["receipt_path"] = jev_bridge._private_receipt(folder, "repo-route", payload)
    return result


def _clean(text):
    lines, fenced = [], False
    for line in text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or re.search(r"\b\w+\s*=|[a-fA-F0-9]{32,}|(?:/Users/|/home/|https?://)|"
                               r"(?i:api[_ -]?key|secret|password|bearer|access[_ -]?token)", line):
            continue
        lines.append(line.strip().lstrip("# "))
    return " ".join(lines)[:400]


def _purpose(root):
    pieces = []
    if (root / "adws/adw_desk.py").is_file():
        pieces.append("ADW workspace UI")
    if (root / "adws/built/opencode-adw/runtime.py").is_file():
        pieces.append("ADW workflow engine")
    for name in ("README.md", "package.json"):
        try:
            with (root / name).open(encoding="utf-8") as stream:
                raw = stream.read(8192)
            if name == "package.json":
                raw = json.loads(raw).get("description", "")
            else:
                # First public heading/paragraph only, never arbitrary task files.
                raw = "\n\n".join(raw.split("\n\n")[:2])
            if isinstance(raw, str):
                pieces.append(_clean(raw))
        except (OSError, ValueError, UnicodeError):
            pass
    return " ".join(pieces)[:400]


def _git_metadata(path, deadline):
    """Worker-only Git reads; the outer process group also bounds filesystem IO."""
    def git(*args):
        return subprocess.run(["git", "-C", path, "rev-parse", *args],
                              capture_output=True, text=True, check=True,
                              timeout=min(.4, max(.01, deadline - time.monotonic()))).stdout.strip()
    root = Path(git("--show-toplevel")).resolve()
    common = Path(git("--path-format=absolute", "--git-common-dir")).resolve()
    # A submodule's gitdir lives under its parent's .git/modules, but its
    # canonical checkout is still the submodule, not that metadata directory.
    canonical = common.parent if common.name == ".git" else root
    return dict(input=path, root=str(root), common=str(common), canonical=str(canonical),
                is_root=Path(path).resolve() == root, description="", acquisition="git_rev_parse")


def _local_git_metadata(path):
    """Worker-only retrieval hint for discovery-observed roots, never authority.

    Empty/malformed .git entries are not roots. Linked worktrees share commondir;
    gitfiles without commondir (including submodules) retain their own checkout.
    The selected checkout must separately pass _git_metadata before execution.
    """
    def small(file):
        with file.open(encoding="utf-8") as stream:
            value = stream.read(4097)
        if len(value) > 4096 or "\x00" in value:
            raise ValueError("invalid Git metadata")
        return value.strip()

    root = Path(path).resolve()
    dotgit = root / ".git"
    if dotgit.is_dir():
        gitdir = dotgit.resolve()
    else:
        value = small(dotgit)
        if not value.startswith("gitdir: ") or "\n" in value:
            raise ValueError("invalid gitfile")
        gitdir = (root / value[len("gitdir: "):]).resolve()
    head = small(gitdir / "HEAD")
    if not re.fullmatch(r"ref: refs/[^\s]+|[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", head):
        raise ValueError("invalid HEAD")
    common_file = gitdir / "commondir"
    linked = common_file.is_file()
    if linked:
        value = small(common_file)
        if not value or "\n" in value:
            raise ValueError("invalid commondir")
        common = (gitdir / value).resolve()
    else:
        common = gitdir
    if not (common / "objects").is_dir() or not (common / "refs").is_dir():
        raise ValueError("incomplete Git metadata")
    canonical = common.parent if linked and common.name == ".git" else root
    return dict(input=path, root=str(root), common=str(common), canonical=str(canonical),
                is_root=True, description="", acquisition="local_git_metadata")


def _catalog_rows(data, emit, *, budget_s=5):
    """Worker-only catalog projection; stream roots before project-purpose IO."""
    deadline = time.monotonic() + budget_s
    observed = set(data.get("discovered_roots", []))
    projects = {}
    examined = 0
    complete = True
    for path in data["paths"][:1002]:
        if time.monotonic() >= deadline:
            complete = False
            break
        if not os.path.isabs(path) or _blocked(path):
            continue
        examined += 1
        try:
            row = None
            if path in observed:
                try:
                    row = _local_git_metadata(path)
                except (OSError, ValueError, UnicodeError):
                    pass
            if row is None:
                row = _git_metadata(path, deadline)
            emit(row)
            prior = projects.get(row["common"])
            # Prefer the main checkout's purpose, regardless of discovery order.
            if prior is None or row["root"] == row["canonical"]:
                projects[row["common"]] = row
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            continue
    described = 0
    for row in projects.values():
        if time.monotonic() >= deadline:
            complete = False
            break
        emit(dict(row, description=_purpose(Path(row["root"]))))
        described += 1
    emit(dict(event="catalog_status", complete=complete, examined_paths=examined,
              projects=len(projects), described_projects=described))


def _worker():
    """Private stdio helper: all slow local metadata access is killable as a group."""
    def emit(value):
        print(json.dumps(value), flush=True)
    mode = sys.argv[1]
    if mode == "--manifest":
        for path in (Path(__file__).parent / "opencode-adw-install.json",
                     Path.home() / ".config/opencode/opencode-adw-install.json"):
            try:
                with path.open() as stream:
                    value = json.loads(stream.read(65536)).get("workspace_root")
                if isinstance(value, str) and value:
                    emit(os.path.abspath(os.path.expanduser(value)))
                    return
            except (OSError, ValueError):
                pass
    elif mode == "--probe":
        emit(Path(sys.argv[2]).is_file())
    elif mode == "--discover":
        import importlib.util
        path = Path(sys.argv[2])
        spec = importlib.util.spec_from_file_location("_adw_repository_discovery", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        # Source execution preserves the actual __file__ for discovery_argv and
        # its sibling opencode_desk import in the subsequent stdio worker.
        exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
        emit(module.discover(Path.home()))
    elif mode == "--manual":
        data = json.load(sys.stdin)
        try:
            # git -C itself rejects files and nonexistent/non-Git directories.
            emit(_git_metadata(data["path"], time.monotonic() + 1))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    elif mode == "--catalog":
        data = json.load(sys.stdin)
        _catalog_rows(data, emit)


if __name__ == "__main__":
    _worker()
