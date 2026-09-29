#!/usr/bin/env bash
# Add the approved Hermes MCP servers with a least-privilege posture.
# See DECISION.md. Writes nothing unless you approve explicitly:
#
#   ./add.sh --dry-run          # print commands, no writes
#   HERMES_MCP_APPROVED=1 ./add.sh
#
# Idempotent: servers already present are skipped. No credentials are embedded.
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$DRY_RUN" -ne 1 && -z "${HERMES_MCP_APPROVED:-}" ]]; then
  echo "Refusing to run: set HERMES_MCP_APPROVED=1 to add MCP servers, or use --dry-run." >&2
  exit 1
fi

command -v hermes >/dev/null 2>&1 || { echo "hermes not found on PATH" >&2; exit 1; }

say() { printf '==> %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}
has() { hermes mcp list 2>/dev/null | grep -qF "$1"; }

# 1. Obsidian — read-only vault access (custom stdio; not in the catalog).
if has obsidian; then
  say "obsidian already present; skipping"
else
  run hermes mcp add obsidian --command npx --args -y obsidian-mcp-server@latest
fi

# 2. n8n — catalog bridge; docs/manage posture, no instance URL or credential yet.
if has n8n; then
  say "n8n already present; skipping"
else
  run hermes mcp install n8n
fi

# 3. twelve-data — catalog market-data (the single read-only data experiment).
if has twelve-data; then
  say "twelve-data already present; skipping"
else
  run hermes mcp install twelve-data
fi

say "Done. Next steps (see DECISION.md):"
say "  hermes mcp configure obsidian|n8n|twelve-data   # least-privilege tool set"
say "  hermes mcp test obsidian|n8n|twelve-data        # verify each connection"
