# Task: review this WorkflowSpec against the verbatim request

- Request (verbatim — the ground truth):

{request}

- Batch (the spec under review):

{batch_json}

Check, requirement by requirement:
- the requirement sentence appears, untouched, as a `requirements[]` entry;
- it maps to a phase, a named gate and a verifier, or an explicit blocker;
- the gate checks real content for that requirement (R5), the phase's owner
  is a declared seat, and nothing the request asked for was narrowed or
  dropped (A1/A2, R10).

Write the verdict envelope (system.md schema) as JSON to:

{output_path}
