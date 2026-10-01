# Task: write the WorkflowSpec v1 for this request

- Request (verbatim, never narrowed):

{request}

- Batch (survey patterns with citations, and any reviewer notice):

{batch_json}

Use the survey's cited patterns (P/M/F/R/A codes from
`adws/specs/prior-adw-patterns.md`) to choose phase shape, gates, seats and
tools. Map every requirement sentence to a phase + gate + verifier, or record
an explicit blocker. Mark unknowns `<EVAN: fill>`.

Write the WorkflowSpec JSON to:

{output_path}

Unknown keys are fatal. The code gate parses this against the frozen schema
before anything is built.
