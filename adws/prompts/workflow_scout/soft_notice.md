# The survey gate rejected the previous envelope

Gate failures (fix ONLY these; keep everything else):

{failures}

Checks the gate enforces:
- `patterns` is a non-empty list; every entry has `code`, `citation`, `why`.
- every `citation` names `prior-adw-patterns.md` and its section.
- every tool in `tools` is in the known registry
  (`read, grep, find, ls, write, edit, bash`); an absent tool becomes a risk
  and a preflight blocker, not a capability (R1).

Write the corrected envelope as JSON to {output_path}.
