# MCP additions — decision record

Date: 2026-09-02
Input: MCP server scout report (7 ranked candidates, GitHub-metadata research only)
Scope: Evan's Hermes MCP stack. Approval-gated — nothing here is installed or run.
Note: pi (this repo's harness) intentionally ships no built-in MCP; these additions
target Hermes, not the fusion-harness runtime.

## Decision

Follow the report's own approval sequence and stop after phase 3.

| Ref | Candidate | Disposition | Phase |
|---|---|---|---|
| D1 | cyanheads/obsidian-mcp-server | ADD — read-only, folder-scoped | 1 |
| D2 | czlonkowski/n8n-mcp | ADD — documentation-only mode | 2 |
| D3 | Alex2Yang97/yahoo-finance-mcp | ADD — research-only market-data experiment | 3 |
| D4 | OpenBB-finance/OpenBB | DEFER — platform, not a Hermes MCP; evaluate in a separate environment | — |
| D5 | ComposioHQ/composio | REJECT for now — HIGH risk, no named connector use case | — |
| D6 | activepieces/activepieces | REJECT for now — duplicates n8n role, HIGH risk | — |
| D7 | modelcontextprotocol/server-memory | DEFER — reference-grade, duplicates Hermes/Obsidian memory | — |

## Rationale

- D1 obsidian: strongest fit per report (vault access with real controls). Start
  read-only with reads scoped to approved folders. Prerequisites are separate
  approval steps: Obsidian Local REST API plugin + environment configuration.
  No credential in any file here.
- D2 n8n: docs-only mode (`MCP_MODE=stdio`, no n8n instance URL, no API key)
  improves workflow construction without granting execution power.
- D3 yahoo-finance: chosen over OpenBB (D4) as the single market-data experiment
  because it is a direct Hermes MCP via `uvx` — fastest signal. Outputs are
  exploratory only; verify prices, timestamps, adjustments, and options fields
  before any reliance. OpenBB remains the long-term research substrate if the
  experiment proves the workflow.
- D5/D6: both are HIGH risk per the report and add breadth Evan has no named use
  case for. Revisit only with a specific connector requirement and a
  least-privilege plan; never authorize broad credential bundles.
- D7: maintainers describe it as an educational reference implementation and it
  overlaps existing memory. If tested at all: isolated, non-sensitive data only.

## Rules

1. Nothing runs until Evan explicitly approves each phase.
2. Exact commands live in `mcp-additions.json` under `command`, copied verbatim
   from the scout report.
3. Credential-bearing values (Obsidian API key, n8n URL/key, Composio/Activepieces
   MCP URLs) are entered at approval time only and never saved to this repo.
4. Each addition is independently reversible: remove the entry from Hermes before
   dropping it (verify the exact `hermes mcp` removal subcommand at that time).
