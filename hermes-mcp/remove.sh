#!/usr/bin/env bash
# Remove the MCP servers added by add.sh. Gated the same way.
#
#   ./remove.sh --dry-run
#   HERMES_MCP_APPROVED=1 ./remove.sh
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$DRY_RUN" -ne 1 && -z "${HERMES_MCP_APPROVED:-}" ]]; then
  echo "Refusing to run: set HERMES_MCP_APPROVED=1 to remove MCP servers, or use --dry-run." >&2
  exit 1
fi

command -v hermes >/dev/null 2>&1 || { echo "hermes not found on PATH" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}
has() { hermes mcp list 2>/dev/null | grep -qF "$1"; }

for name in obsidian n8n twelve-data; do
  if has "$name"; then
    run hermes mcp remove "$name"
  else
    printf '==> %s not configured; skipping\n' "$name"
  fi
done
