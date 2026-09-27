# Support-evidence component

```sh
python3 -B research/ai-saas-100/cases/007/tests/support-evidence-v1/run.py
python3 -B research/ai-saas-100/cases/004/research/continuation-v1/execute_components.py 007
```

`support_evidence.py` accepts the retained structured support request on stdin. `prepare(request)` validates the supplied corpus and filters future, superseded, unapproved, and unresolved-version documents. A future successor does not retire the current policy early. Cyclic or backwards-dated supersession is rejected. Documents supplied without an `approved` flag are assumed approved by the caller, consistent with the frozen corpus contract. This is not an authorization service.

`audit_citations(request, citations)` requires an eligible source ID and exact Python character offsets `start`/`end` matching `quote`. It validates source spans, not semantic entailment, truth, or answer relevance. `draft_ticket(request, reason)` prepares an unsent local ticket only if `draft_ticket` is in allowed_actions. Its reason is caller-supplied, not an inferred finding. No external ticket ID is invented.

All source text is inert. Unkeyed additional evidence remains explicitly unresolved. No policies, refund periods, or fixture answers are hardcoded. The component never generates a natural-language answer, determines refund eligibility, or creates a Zendesk ticket. It does not claim complete contradiction detection or relevance ranking.

Python standard library only. Calls perform no file/network I/O and preserve input values. Original fixtures and source captures are unchanged. Component tests exercise their preprocessing constraints, not the missing answer-generation workflow. Product acceptance, B1/B3 comparisons, and hidden evaluation remain outstanding.
