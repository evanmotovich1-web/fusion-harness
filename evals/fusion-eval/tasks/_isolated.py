"""Isolated calls into the solution under test.

The grading pytest process NEVER imports the solution. Every call runs in a fresh
child interpreter (`python -I`) that only returns plain data; the assertions run
here, in the trusted parent. On macOS the child also runs under sandbox-exec
(FH_EVAL_SANDBOX_PROFILE) with deny-by-default file access: it can read only the OS,
Python, its solution folder and a private temp folder, and has no network — so no
stored copy of the answers is reachable.

Known limit: the child is the solution's own process, so a property the child itself
reports (e.g. "the input was not mutated") could be faked by code that tampers with
this module's child runtime. Returned VALUES can only be right by computing them.
A second result line (e.g. printed from an atexit hook) fails the call outright.
"""
import json
import os
import subprocess
import sys

SOLUTION_DIR = os.environ["FH_EVAL_SOLUTION_DIR"]
PROFILE = os.environ.get("FH_EVAL_SANDBOX_PROFILE", "")
CHILD_TMP = os.environ.get("FH_EVAL_CHILD_TMP", "")
MARK = "@@FH_EVAL_RESULT@@"

# Child side: encode tuples explicitly so the parent can tell tuples from lists.
_PRELUDE = f"""
import json, sys
sys.path.insert(0, {SOLUTION_DIR!r})
def _enc(v):
    if isinstance(v, tuple): return {{"__tuple__": [_enc(x) for x in v]}}
    if isinstance(v, list): return [_enc(x) for x in v]
    if isinstance(v, dict): return {{"__dict__": [[_enc(k), _enc(x)] for k, x in v.items()]}}
    if isinstance(v, bool) or v is None or isinstance(v, (int, float, str)): return v
    return {{"__repr__": repr(v), "__type__": type(v).__name__}}
def _dec(v):
    if isinstance(v, list): return [_dec(x) for x in v]
    if isinstance(v, dict):
        if "__tuple__" in v: return tuple(_dec(x) for x in v["__tuple__"])
        if "__dict__" in v: return {{_dec(k): _dec(x) for k, x in v["__dict__"]}}
    return v
def _emit(obj):
    sys.stdout.flush()
    sys.__stdout__.write("\\n" + {MARK!r} + json.dumps(obj) + "\\n")
    sys.__stdout__.flush()
"""


def _enc(v):
    """Parent side: encode arguments so tuples/dicts reach the child with their real types."""
    if isinstance(v, tuple):
        return {"__tuple__": [_enc(x) for x in v]}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    if isinstance(v, dict):
        return {"__dict__": [[_enc(k), _enc(x)] for k, x in v.items()]}
    return v


def _dec(v):
    if isinstance(v, list):
        return [_dec(x) for x in v]
    if isinstance(v, dict):
        if "__tuple__" in v:
            return tuple(_dec(x) for x in v["__tuple__"])
        if "__dict__" in v:
            return {_dec(k): _dec(x) for k, x in v["__dict__"]}
        return v
    return v


def _command(args):
    cmd = [sys.executable, "-I", *args]
    if PROFILE and os.path.exists("/usr/bin/sandbox-exec"):
        cmd = ["/usr/bin/sandbox-exec", "-f", PROFILE, *cmd]
    return cmd


def _env():
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": os.environ.get("LANG", "C.UTF-8")}
    if CHILD_TMP:
        env["TMPDIR"] = CHILD_TMP
    return env


def _child(body, timeout=30):
    result = subprocess.run(_command(["-c", _PRELUDE + body]), capture_output=True, text=True, timeout=timeout, cwd=SOLUTION_DIR, env=_env())
    lines = [line for line in result.stdout.splitlines() if line.startswith(MARK)]
    if len(lines) != 1:
        raise AssertionError(f"expected exactly one result from the solution child, got {len(lines)} (exit {result.returncode}): {result.stderr[-600:]}")
    return json.loads(lines[0][len(MARK):])


def call(module, func, *args):
    """module.func(*args) in an isolated child → ("ok", value) or ("raises", ExceptionTypeName)."""
    out = _child(f"""
args = _dec(json.loads({json.dumps(json.dumps(_enc(list(args))))}))
try:
    import importlib
    value = getattr(importlib.import_module({module!r}), {func!r})(*args)
    _emit({{"ok": True, "value": _enc(value), "type": type(value).__name__}})
except BaseException as error:
    _emit({{"ok": False, "raises": type(error).__name__}})
""")
    return ("ok", _dec(out["value"]), out["type"]) if out["ok"] else ("raises", out["raises"])


def value(module, func, *args):
    """The returned value (fails the test if the call raised)."""
    kind, *rest = call(module, func, *args)
    assert kind == "ok", f"{module}.{func}{args!r} raised {rest[0]}"
    return rest[0]


def raises(module, func, *args):
    """The exception type name raised, or None."""
    kind, *rest = call(module, func, *args)
    return rest[0] if kind == "raises" else None


def script(module, factory, ctor_args, ops):
    """Build module.factory(*ctor_args) then apply ops [(method, args)] in ONE child; returns per-op results."""
    out = _child(f"""
import importlib
ops = _dec(json.loads({json.dumps(json.dumps(_enc(ops)))}))
results = []
try:
    obj = getattr(importlib.import_module({module!r}), {factory!r})(*_dec(json.loads({json.dumps(json.dumps(_enc(list(ctor_args))))})))
except BaseException as error:
    _emit({{"ctor_raises": type(error).__name__}}); raise SystemExit
for method, args in ops:
    try:
        if method == "__len__": v = len(obj)
        elif method == "__contains__": v = args[0] in obj
        else: v = getattr(obj, method)(*args)
        results.append(["ok", _enc(v)])
    except BaseException as error:
        results.append(["raises", type(error).__name__])
_emit({{"results": results}})
""")
    if "ctor_raises" in out:
        return ("ctor_raises", out["ctor_raises"])
    return [(kind, _dec(v)) for kind, v in out["results"]]


def run_file(filename, args=(), stdin=""):
    """Run a solution script as a CLI in an isolated child → CompletedProcess (text)."""
    # A missing script must fail, not "exit 2" by accident (python's own can't-open-file code).
    assert os.path.isfile(os.path.join(SOLUTION_DIR, filename)), f"solution file {filename} is missing"
    return subprocess.run(_command([os.path.join(SOLUTION_DIR, filename), *args]), input=stdin, capture_output=True, text=True, timeout=30, cwd=SOLUTION_DIR, env=_env())


def source(filename):
    """Read a solution file's text without importing it."""
    with open(os.path.join(SOLUTION_DIR, filename), encoding="utf-8") as handle:
        return handle.read()
