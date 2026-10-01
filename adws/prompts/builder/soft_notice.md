# The diff_claims_real gate rejected the previous fill

Gate failures (fix ONLY these):

{failures}

Checks the gate enforces:
- every `claimed_paths` entry is under `adws/built/<name>/`;
- every claimed path exists, is nonempty, and its content hash changed this
  attempt;
- no path outside the allowlist was touched;
- the fill envelope has `fill` = `from_spec` (or `refused` with a concrete
  failure).

Do not widen writes. Do not claim unchanged files. Write the corrected
envelope to {output_path}.
