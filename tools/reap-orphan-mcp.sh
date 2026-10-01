#!/bin/sh
# Kill MCP servers whose parent session is gone (reparented to launchd, ppid 1).
# Servers with a live parent are never touched. Dry run unless --kill is passed.
set -eu
pattern='local_server --workspace|graphify\.serve|vault_semantic\.py mcp'
mode=${1:-}
ps -axo pid=,ppid=,command= | awk -v pat="$pattern" '$2 == 1 && $0 ~ pat { print $1 }' | while read -r pid; do
	if [ "$mode" = "--kill" ]; then
		kill "$pid" && echo "killed $pid"
	else
		echo "would kill $pid: $(ps -o command= -p "$pid" | cut -c1-120)"
	fi
done
