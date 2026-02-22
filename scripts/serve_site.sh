#!/usr/bin/env bash
# Serve the site/ folder (static files for promoting HomeClaw).
# Usage: ./scripts/serve_site.sh [port]
# Default port: 8080. Set PORT=3000 ./scripts/serve_site.sh to override.
# Used by systemd service homeclaw-site.service (see docs/site-service-and-cloudflare-tunnel.md).

set -e
REPO_ROOT="${HOMECLAW_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="${PORT:-9999}"
SITE_DIR="${REPO_ROOT}/site"
if [[ ! -d "$SITE_DIR" ]]; then
  echo "Error: site directory not found at $SITE_DIR" >&2
  exit 1
fi
exec python3 -m http.server "$PORT" --directory "$SITE_DIR"
