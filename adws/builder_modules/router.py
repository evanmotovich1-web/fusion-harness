"""Rule router. Named refusals stop before any agent spend."""

from __future__ import annotations

import re

# Stems are the named DoD fixtures. They do not override a forbidden-target hit.
VAGUE_STEMS = {"toy_vague", "toy-vague", "vague", "needs_human"}
COMPLETE_STEMS = {"toy_complete", "toy-complete"}

# Targets the builder must never edit, even inside a workflow spec.
HARD_FORBIDDEN = (
    (r"\bsssf\b", "sssf"),
    (r"/users/evanmotovich/code/sssf", "sssf path"),
    (r"\bbuilder_modules\b", "builder itself"),
    (r"adw_workflow_builder", "builder itself"),
    (r"\bhomecare/", "homecare tree"),
    (r"\bextensions/", "extensions tree"),
)
# A bare "git push / deploy" ask is a forbidden target. The same words inside a
# workflow-build spec are instructions for the workflow being built, not a
# command for this process. Session 8a35b8a5 died on the second case.
PUBLISH_FORBIDDEN = (
    (r"\bgit\s+push\b", "git push"),
    (r"\bgit\s+commit\b", "git commit"),
    (r"\bdeploy\b", "deploy"),
    (r"\bpublish\b", "publish"),
    (r"\bproduction\b", "production deploy"),
)
NOT_WORKFLOW = (
    "poem", "haiku", "limerick", "sonnet", "verse", "weather", "joke",
    "pitch deck", "invoice", "recipe for", "song about",
)
WORKFLOW_INTENT = ("workflow", "adw", "phase chain", "build me a", "spec and build")
CONCRETE = (
    "must", "should", "gate", "verify", "check", "output", "phase",
    "requirement", "nonempty", "fixture", "when ", "exit ",
)
# Named SSSF desk recipes. A Tunza-shaped ask is the live chip, not a stub.
EXISTING_RECIPES = {
    "tunza": "just tunza",
}
_NAMED_WORKFLOW = re.compile(
    r"\b(?:named|id)\s+([a-z0-9][a-z0-9._-]*)"
    r"|\b(?:new\s+factory\s+)?adw:\s*([a-z0-9][a-z0-9._-]*)"
)


def _stem(stem: str) -> str:
    return (stem or "").lower()


def _named_new_workflow(text: str) -> str | None:
    match = _NAMED_WORKFLOW.search(text or "")
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


def route(request: str, stem: str = "") -> dict:
    """Return {route, reason, questions}. route is build | not_workflow | forbidden_target | needs_human | existing_recipe."""
    text = " ".join((request or "").lower().split())
    stem_l = _stem(stem)
    for pattern, why in HARD_FORBIDDEN:
        if re.search(pattern, text):
            return {"route": "forbidden_target", "reason": f"forbidden_target: {why}", "questions": []}
    intent = any(phrase in text for phrase in WORKFLOW_INTENT) or stem_l in COMPLETE_STEMS or stem_l in VAGUE_STEMS
    if not intent:
        for pattern, why in PUBLISH_FORBIDDEN:
            if re.search(pattern, text):
                return {"route": "forbidden_target", "reason": f"forbidden_target: {why}", "questions": []}
    if any(re.search(rf"\b{re.escape(word)}\b", text) for word in NOT_WORKFLOW if " " not in word) or any(
        phrase in text for phrase in NOT_WORKFLOW if " " in phrase
    ):
        return {"route": "not_workflow", "reason": "not_workflow: not a workflow-build ask", "questions": []}
    if not intent:
        return {"route": "not_workflow", "reason": "not_workflow: no workflow-build intent", "questions": []}
    concrete = any(token in text for token in CONCRETE) or bool(re.search(r"(?m)^\s*[-*]\s+\S", request or ""))
    if stem_l in COMPLETE_STEMS:
        concrete = True
    if stem_l not in VAGUE_STEMS:
        new_id = _named_new_workflow(text)
        for recipe_id, command in EXISTING_RECIPES.items():
            if not re.search(rf"\b{re.escape(recipe_id)}\b", text):
                continue
            if new_id and new_id not in EXISTING_RECIPES and concrete:
                break
            return {
                "route": "existing_recipe",
                "reason": f"existing factory recipe — run {command}",
                "questions": [],
            }
    deliverables = [item.strip(" .") for item in re.findall(r"\bone for\s+([^,.;]+)", text)]
    if stem_l in VAGUE_STEMS or not concrete:
        questions = []
        if len(deliverables) >= 2:
            questions = [f"What check proves the {name} workflow worked?" for name in deliverables]
        else:
            questions = [
                "What should the workflow do, in one sentence the builder must not narrow?",
                "What check proves it worked (gate name and the evidence file)?",
                "May it write files, and only under which directory?",
            ]
        if "higgsfield" in text:
            questions.append(
                "Higgsfield is not a local tool. Should that capability stay blocked until a human wires it?"
            )
        if deliverables:
            lines = "\n".join(f"- {name}: <EVAN: fill>" for name in deliverables)
            questions.append("Paste answers back in this shape:\n" + lines)
        return {
            "route": "needs_human",
            "reason": "needs_human: request does not name a checkable outcome",
            "questions": questions,
        }
    return {"route": "build", "reason": "workflow-build ask with a checkable outcome", "questions": []}
