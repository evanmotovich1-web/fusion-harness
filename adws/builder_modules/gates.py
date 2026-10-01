"""Code gates for the builder's own seats. Agents do not grade themselves."""

from __future__ import annotations

from .paths import KNOWN_TOOLS, PATTERNS_PATH
from .spec_schema import validate_spec


def survey(output: dict) -> list[str]:
    if output.get("_invalid"):
        return [str(output.get("failure") or "survey: fixture gate failed")]
    errors = []
    patterns = output.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        errors.append("survey: at least one pattern is required")
        patterns = []
    for index, pattern in enumerate(patterns):
        if not isinstance(pattern, dict):
            errors.append(f"survey: patterns[{index}] must be an object")
            continue
        citation = str(pattern.get("citation") or "")
        if "prior-adw-patterns.md" not in citation:
            errors.append(f"survey: pattern {pattern.get('code')} citation must name prior-adw-patterns.md")
        if not pattern.get("code"):
            errors.append(f"survey: patterns[{index}] missing code")
    if not PATTERNS_PATH.is_file():
        errors.append("survey: prior-adw-patterns.md is not on disk")
    for tool in output.get("tools") or []:
        if tool not in KNOWN_TOOLS:
            errors.append(f"survey: tool {tool} is not in the known-tools registry")
    return errors


def exact_number(text: str) -> int | None:
    """Objective total/count constraint. None means this sentence is not that check."""
    import re
    match = re.search(r"\bexactly\s+(\d+)\b", text or "", re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"\bequals?\s+(\d+)\b", text or "", re.I)
    if match:
        return int(match.group(1))
    return None


def _same_request(left: str, right: str) -> bool:
    return " ".join((left or "").split()) == " ".join((right or "").split())


def spec_schema(output: dict, request: str | None = None) -> list[str]:
    if output.get("_invalid"):
        return [str(output.get("failure") or "schema missing requirements")]
    errors = [f"spec_schema: {item}" for item in validate_spec(output)]
    if request is not None and not _same_request(str(output.get("request_verbatim") or ""), request):
        errors.append("request mismatch: spec request_verbatim does not match the current verbatim request")
    from .preflight import generated_tool_blockers
    errors.extend(generated_tool_blockers(output))
    return errors


def verdict_consistent(output: dict, spec: dict | None) -> list[str]:
    if output.get("_invalid"):
        return [str(output.get("failure") or "verdict_consistent: fixture gate failed")]
    verdict = output.get("verdict")
    findings = output.get("findings") if isinstance(output.get("findings"), list) else []
    blocking = [f for f in findings if isinstance(f, dict) and f.get("status") in {"unmet", "blocking"}]
    if verdict == "approve" and blocking:
        texts = "; ".join(str(f.get("text") or f.get("status")) for f in blocking)
        return [f"verdict_consistent: approval may not coexist with unmet/blocking findings: {texts}"]
    if verdict not in {"approve", "reject"}:
        return ["verdict_consistent: verdict must be approve or reject"]
    if verdict == "reject" and not blocking:
        return ["verdict_consistent: rejection needs an unmet or blocking finding"]
    if spec and verdict == "approve":
        ids = {req.get("id") for req in spec.get("requirements") or []}
        met = {f.get("id") for f in findings if isinstance(f, dict) and f.get("status") == "met"}
        missing = ids - met
        if missing and findings:
            return [f"verdict_consistent: approve omitted requirements {sorted(missing)}"]
    return []


def diff_claims_real(output: dict, before: dict[str, str], after: dict[str, str], allow_root: str) -> list[str]:
    """Content-hash gate. Not a sandbox: it checks claims and the snapshot it was given."""
    errors = []
    claimed = output.get("claimed_paths") or output.get("files") or []
    if isinstance(claimed, dict):
        claimed = list(claimed)
    outside = []
    names = []
    for item in claimed:
        path = item.get("path") if isinstance(item, dict) else str(item)
        names.append(path)
        if allow_root not in path.replace("\\", "/") and not path.startswith(allow_root):
            outside.append(path)
    if outside:
        return [f"diff_claims_real: path outside allowlist: {outside[0]}"]
    if output.get("fill") == "refused":
        return [str(output.get("failure") or "diff_claims_real: builder refused the fill")]
    for path in names or list(after):
        if path not in after:
            errors.append(f"diff_claims_real: claimed path missing: {path}")
            continue
        if not after[path]:
            errors.append(f"diff_claims_real: claimed path empty: {path}")
            continue
        if before.get(path) == after[path]:
            errors.append(f"diff_claims_real: content hash unchanged: {path}")
    if not names and not after:
        errors.append("diff_claims_real: builder claimed no files")
    return errors
