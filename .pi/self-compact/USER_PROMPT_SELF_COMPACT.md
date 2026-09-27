# Compaction requested (editable)

Context is at {{PERCENT}}% ({{TOKENS}} of {{WINDOW}} tokens; warning threshold
{{WARNING}}; forced fence at {{FORCE}}).

Call self_compaction(note_to_self) soon. Include:

- Current goal in one sentence.
- Exact paths already changed or read that matter.
- Test/verification results so far (commands and exit status).
- The single next action.

Do not reinvent completed work. Ordinary tools remain available below the hard cutoff of {{FORCE}} tokens.
At or above that cutoff only self_compaction is available until compaction succeeds.
