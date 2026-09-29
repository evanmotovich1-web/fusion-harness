# Partial English rewrite workflow

Run the frozen control-plane regressions from the repository root:

```sh
python3 -B research/ai-saas-100/cases/001/tests/run.py
```

Python standard library only. `workflow.py` validates text, strength and protected facts, creates a structured rewrite prompt, and provides literal-fact output auditing. It has no model backend. Valid inputs return `blocked_inference`, not rewritten text. The CLI reads JSON on stdin and exits 3 when inference is blocked, or 2 for invalid input.

The 20 passing local assertions establish validation and fail-closed behavior only. Fifteen valid-input cases produce no rewritten text. No semantic score, model baseline, detector result or original-product comparison exists. Response-auditing code was not tested with real model output.

Fixtures were frozen before implementation, but all were visible to the builder. Do not describe them as held-out tests. Complete authorized model execution, independent semantic scoring and hidden evaluation before seeking acceptance. Public-page evidence is in ../research/ and ../evidence.json. Pricing and adoption claims are vendor claims, not verified revenue or customers.
