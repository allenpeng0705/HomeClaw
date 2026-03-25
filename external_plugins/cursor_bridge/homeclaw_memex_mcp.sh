#!/usr/bin/env sh
# HomeClaw bundled memex MCP — safe to use when MCP config cannot set cwd.
# Repo root = parent of external_plugins/.
_bridge_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
_root=$(CDPATH= cd -- "$_bridge_dir/../.." && pwd)
cd "$_root" || exit 1
exec python3 -m external_plugins.cursor_bridge.memex_mcp "$@"
