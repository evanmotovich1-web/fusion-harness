# Task: implement the approved spec inside the scaffold

- Request (verbatim — for context only; the spec below is what you implement):

{request}

- Batch (the approved WorkflowSpec):

{batch_json}

Fill every scaffolded file under `adws/built/<name>/` from the spec:
gate logic in `gates.py` (real schema/value checks per requirement, R5),
prompt bundles under `prompts/<seat>/`, good/bad fixtures under `fixtures/`,
tests, README. Claim every path you change.

Write the fill envelope (system.md schema) as JSON to:

{output_path}
