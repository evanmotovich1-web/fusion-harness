# MCP add decision

Status: recommend only. Nothing was installed. No `hermes mcp add` was run.
Other fusion lanes were not inspected (lane contract).

## Decision

Add two servers on Evan approval. Add nothing else in this pass.

| Code | Candidate | Verdict | First posture |
| --- | --- | --- | --- |
| D1 | cyanheads/obsidian-mcp-server | ADD | Read-only. Folder-scoped allowlists. No full-vault expose. |
| D2 | czlonkowski/n8n-mcp | ADD | Documentation-only. No n8n URL. No API credential. |
| D3 | OpenBB-finance/OpenBB | DEFER | Research platform, not a one-command Hermes MCP. |
| D4 | Alex2Yang97/yahoo-finance-mcp | DEFER | Fast Hermes bridge, unofficial, no security policy. Exploratory only if later approved. |
| D5 | ComposioHQ/composio | DO NOT ADD | HIGH. Brokers credentials and actions across many apps. |
| D6 | activepieces/activepieces | DO NOT ADD | HIGH. Second automation plane plus connector execution. |
| D7 | modelcontextprotocol/servers Memory | DO NOT ADD | Reference/educational. Duplicates Hermes and Obsidian memory. |

## Why this cut

Obsidian is the only candidate that maps onto vault work with typed denials, a global read-only switch, and folder allowlists. n8n-MCP is the only automation add that can stay useful without instance control if it stays in documentation mode.

Market data is a later experiment, not a first install. OpenBB is the stronger long-term substrate but it is a venv/platform install, not an MCP tap. Yahoo Finance MCP is the shorter Hermes path and the weaker trust story. Neither is required to start.

Composio and Activepieces expand permission surface before there is a named connector use case. The Memory reference server is not a production memory store.

## Approval sequence if Evan says yes

1. Obsidian MCP, read-only, approved folders only. Local REST API plugin and env config are separate approvals. No credential in this file.
2. n8n-MCP with documentation tools only. `MCP_MODE` stays non-management.

Stop there. Revisit D3/D4 only with a named research task and independent price/timestamp checks. Revisit D5/D6 only with one low-impact app and least-privilege scopes.

## Do not run until Evan approves

Obsidian:

```bash
hermes mcp add obsidian --command 'npx -y obsidian-mcp-server@latest'
```

n8n documentation-only:

```bash
hermes mcp add n8n --command 'env MCP_MODE=stdio LOG_LEVEL=error DISABLE_CONSOLE_OUTPUT=true npx n8n-mcp'
```

Do not store credentials, REST tokens, or remote MCP URLs in this vault or repo.

## Ranked scout (source)

Research used GitHub API metadata and repository documentation. Public web search was unavailable in the scout run. No candidate repository code was downloaded or run here.

### 1. cyanheads/obsidian-mcp-server — ADD (D1)

- GitHub: https://github.com/cyanheads/obsidian-mcp-server
- MCP for reading, searching, editing, tagging, and managing Obsidian notes through the Local REST API plugin.
- Maturity: 674 stars; last pushed 2026-08-22; Apache-2.0; active changelog; standard security policy.
- Fit: structured vault access with folder-scoped read/write paths.
- RISK: MED. Handles an Obsidian API credential and can write. Read-only mode, folder scopes, typed denials, and a published security policy reduce that.

### 2. czlonkowski/n8n-mcp — ADD (D2)

- GitHub: https://github.com/czlonkowski/n8n-mcp
- n8n knowledge and management MCP: discover nodes, validate configs, build workflows, optionally manage an instance.
- Maturity: 22,819 stars; last pushed 2026-08-31; MIT; self-hosting, hardening, read-only, audit, and deployment docs; standard security policy.
- Fit: workflow construction without execution power if documentation-only.
- RISK: MED. Management mode can create, modify, test, and run workflows. Keep API scope off.

### 3. OpenBB-finance/OpenBB — DEFER (D3)

- GitHub: https://github.com/OpenBB-finance/OpenBB
- Financial-data platform with normalized access across providers.
- Maturity: 72,583 stars; last pushed 2026-07-30; 7,491 forks; extensive docs; standard security policy; GitHub reports no asserted SPDX license.
- Fit: strongest mature research substrate for fundamentals, macro, and provider abstraction.
- RISK: MED. Provider credentials, licensing, rate limits, and point-in-time correctness vary. Not a one-command Hermes MCP.
- Separate-env eval only, if later approved:

```bash
uv venv .venv-openbb && . .venv-openbb/bin/activate && uv pip install openbb
```

### 4. Alex2Yang97/yahoo-finance-mcp — DEFER (D4)

- GitHub: https://github.com/Alex2Yang97/yahoo-finance-mcp
- MCP for Yahoo Finance quotes, history, company data, statements, options, and news.
- Maturity: 345 stars; last pushed 2026-08-30; MIT; documented `uvx` entrypoint; no standard security policy found.
- Fit: shortest Hermes path to market-research queries without a paid provider.
- RISK: MED. Unofficial third-party bridge. Treat as exploratory, not execution-grade.
- Later Hermes test only, if approved:

```bash
hermes mcp add yahoo-finance --command 'uvx --from git+https://github.com/Alex2Yang97/yahoo-finance-mcp yahoo-finance-mcp'
```

### 5. ComposioHQ/composio — DO NOT ADD (D5)

- GitHub: https://github.com/ComposioHQ/composio
- Agent integration layer: 1,000+ app toolkits, auth, tool search, sandboxed workbenches.
- Maturity: 30,003 stars; last pushed 2026-09-01; MIT; standard security policy.
- RISK: HIGH. Value comes from brokering credentials and actions across many services.

### 6. activepieces/activepieces — DO NOT ADD (D6)

- GitHub: https://github.com/activepieces/activepieces
- Open-source automation with AI agents, workflows, and roughly 400 MCP-capable connectors.
- Maturity: 24,169 stars; last pushed 2026-09-02; 4,126 forks; docs and standard security policy; GitHub reports no asserted SPDX license.
- RISK: HIGH. Connector credentials plus workflow execution. Do not add a second automation platform before n8n needs are clear.

### 7. modelcontextprotocol/servers Memory — DO NOT ADD (D7)

- GitHub: https://github.com/modelcontextprotocol/servers
- Official MCP reference collection. Local Memory server is a basic persistent knowledge graph.
- Maturity: 90,007 stars; last pushed 2026-08-31; official MCP org; standard security policy.
- RISK: MED. Maintainers describe these as educational reference implementations, not production servers.

## Out of scope this pass

- Running any install command
- Saving credentials or remote MCP URLs
- Installing OpenBB into this lane
- Changing fusion-harness TypeScript or Pi stack YAML
