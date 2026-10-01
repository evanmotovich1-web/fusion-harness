# The verdict_consistent gate rejected the previous verdict

Gate failures (fix ONLY these):

{failures}

Checks the gate enforces:
- `verdict` is `approve` or `reject`.
- `approve` has no `unmet`/`blocking` finding, and covers every requirement
  id in the spec with a `met` finding.
- `reject` has at least one `unmet` or `blocking` finding naming a real
  requirement id.

Do not flip a verdict to pass the gate. Re-derive it from the spec and the
verbatim request, then write the corrected envelope to {output_path}.
