#!/usr/bin/env bash
# Start Friends plugin server and register with Core (one command).
# Run from project root:  ./external_plugins/friends/run.sh
# Requires: Core running, curl, Python.

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.run_logs" && pwd)"
mkdir -p "$LOG_DIR"
PIDFILE="$LOG_DIR/friends.pid"
LOGFILE="$LOG_DIR/friends.log"
PORT="${FRIENDS_PORT:-3103}"

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$OLD_PID" ] && [ "$OLD_PID" -eq "$OLD_PID" ] 2>/dev/null && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[friends] Already running (PID $OLD_PID). Registering..."
    python -m external_plugins.friends.register
    echo "Done."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "[friends] Starting server on port $PORT..."
python -m external_plugins.friends.server >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[friends] Waiting for server..."
n=0
while [ $n -lt 20 ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/health" 2>/dev/null | grep -q 200; then
    break
  fi
  n=$((n + 1))
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[friends] Timeout waiting for server. Check $LOGFILE" >&2
  exit 1
fi

echo "[friends] Registering with Core..."
python -m external_plugins.friends.register
echo "Done. Friends plugin running (PID $(cat "$PIDFILE"))."
