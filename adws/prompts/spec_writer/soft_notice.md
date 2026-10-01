# The spec_schema gate rejected the previous WorkflowSpec

Gate failures (fix ONLY these; keep the rest of the spec):

{failures}

Checks the gate enforces:
- parses against WorkflowSpec v1; unknown keys are fatal.
- every requirement: unique id, `status` starts `blocked`, `gate` equals its
  phase's gate, `verifier` present, `blocker` string or null.
- every agent phase's `owner` is a declared seat; every seat declares the 4
  prompt files and tools from the known registry.
- `artifacts.entrypoint` is `adws/built/<id>/adw_<id_underscored>.py` and
  `artifacts.files` covers the required file set.
- `switches.dry_run` and `switches.stub_agents` are true.
- phase graph is acyclic.

Keep `request_verbatim` untouched. Write the corrected spec JSON to {output_path}.
