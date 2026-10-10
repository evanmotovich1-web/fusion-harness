Build a workflow named session-brief.
- The gate must verify the brief file exists and is a nonempty string.
- The gate must verify the brief is at most 80 lines.
- The gate must verify every bullet cites a source id or is marked unverified.
- The gate must verify a missing brief file fails with the error brief-missing.
- When --db is set, the workflow must read that sqlite file and write the brief from its session rows.
- Fixture mode must pass without a live database.
- The router must judge only the --request string. A --db path must not be a forbidden target.
