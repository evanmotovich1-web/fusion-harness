# Hermes MCP — decision and install plan

Decision on which MCP servers to add to Hermes, grounded in the live Hermes CLI
(`hermes mcp catalog`, `hermes mcp list`) on top of the prior GitHub-only scout.

## Findings that change the scout's bottom line

- **F1** — Hermes runs a curated, "Nous-approved" MCP catalog (`hermes mcp catalog`, ~73 entries) with one-click `install` and `remove`. Third-party GitHub repos are the fallback, not the default.
- **F2** — Hermes currently has **zero** MCP servers configured (`hermes mcp list`).
- **F3** — Two scout needs are already covered by safer catalog entries:
  - `n8n` — "Manage and inspect n8n workflows from Hermes (stdio bridge, no public port)". Prefer this over `czlonkowski/n8n-mcp` (third-party, 22.8k stars but an external code path).
  - `twelve-data` — "Stocks, forex, and crypto market data from Twelve Data". Prefer this over `Alex2Yang97/yahoo-finance-mcp` (third-party, no security policy).
- **F4** — Obsidian is **not** in the catalog, so the vault connector still needs `cyanheads/obsidian-mcp-server` via `hermes mcp add --command`.
- **F5** — `robinhood` exists in the catalog but carries `orders` capability. Excluded from the first install (execution-grade trading surface, not research).

## Decision

- **D1 — Add Obsidian MCP first, read-only.** `cyanheads/obsidian-mcp-server`. Strong read-only switch and folder-scoped allowlists. Requires the Obsidian Local REST API plugin and env (API key, host, read-only) as a separate approval step; no credential is committed here.
- **D2 — Add n8n via the catalog entry, docs/manage posture only.** `hermes mcp install n8n`. No n8n instance URL or API credential until a specific need exists.
- **D3 — Run the single market-data experiment on the catalog's `twelve-data` entry, not the Yahoo MCP.** `hermes mcp install twelve-data`. Yahoo Finance MCP remains a fallback only if Yahoo-specific coverage is required, after validation.
- **D4 — Do not add now.** OpenBB (a `uv` data platform, not a one-command Hermes MCP), Composio and Activepieces (broad credential/action surface, later-stage), and the official Memory reference server (duplicates Hermes memory-graph + Obsidian).

## Commands

Install (gated — see `add.sh`):

```bash
hermes mcp add obsidian --command npx --args -y obsidian-mcp-server@latest
hermes mcp install n8n
hermes mcp install twelve-data
```

Then, per server, drop to the least-privilege tool set:

```bash
hermes mcp configure obsidian     # keep read/search/list; disable edit/write until approved
hermes mcp configure n8n          # docs/discovery only; disable instance-management tools
hermes mcp configure twelve-data  # read-only data tools only
hermes mcp test <name>            # verify each connection
```

Reverse any of them with `hermes mcp remove <name>`.

## Execution boundary

Nothing here installs automatically. `add.sh` refuses to write unless
`HERMES_MCP_APPROVED=1` is set, and `--dry-run` prints the commands without
running them. Obsidian env/credential configuration is a separate step and is
never stored in this repo.
