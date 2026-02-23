#!/usr/bin/env bash
# Start Quote (Node.js) plugin server and register with Core (one command).
# Run from project root:  ./external_plugins/quote-node/run.sh
# Requires: Core running, curl, Node.js.

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$PLUGIN_DIR/../.." && pwd)"
cd "$PLUGIN_DIR"

LOG_DIR="$PLUGIN_DIR/../.run_logs"
mkdir -p "$LOG_DIR"
PIDFILE="$LOG_DIR/quote-node.pid"
LOGFILE="$LOG_DIR/quote-node.log"

if [ ! -d "node_modules" ]; then
  echo "[quote-node] Installing npm dependencies..."
  npm install --no-fund --no-audit
fi

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$OLD_PID" ] && [ "$OLD_PID" -eq "$OLD_PID" ] 2>/dev/null && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[quote-node] Already running (PID $OLD_PID). Registering..."
    node register.js
    echo "Done."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "[quote-node] Starting server on port 3111..."
node server.js >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[quote-node] Waiting for server..."
n=0
while [ $n -lt 20 ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3111/health" 2>/dev/null | grep -q 200; then
    break
  fi
  n=$((n + 1))
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[quote-node] Timeout waiting for server. Check $LOGFILE" >&2
  exit 1
fi

echo "[quote-node] Registering with Core..."
node register.js
echo "Done. Quote (Node.js) plugin running (PID $(cat "$PIDFILE"))."
