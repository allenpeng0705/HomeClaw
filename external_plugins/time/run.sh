#!/usr/bin/env bash
# Start Time plugin server and register with Core (one command).
# Run from project root:  ./external_plugins/time/run.sh
# Requires: Core running, curl, Python.

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.run_logs" && pwd)"
mkdir -p "$LOG_DIR"
PIDFILE="$LOG_DIR/time.pid"
LOGFILE="$LOG_DIR/time.log"

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$OLD_PID" ] && [ "$OLD_PID" -eq "$OLD_PID" ] 2>/dev/null && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[time] Already running (PID $OLD_PID). Registering..."
    python -m external_plugins.time.register
    echo "Done."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "[time] Starting server on port 3102..."
python -m external_plugins.time.server >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[time] Waiting for server..."
n=0
while [ $n -lt 20 ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3102/health" 2>/dev/null | grep -q 200; then
    break
  fi
  n=$((n + 1))
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[time] Timeout waiting for server. Check $LOGFILE" >&2
  exit 1
fi

echo "[time] Registering with Core..."
python -m external_plugins.time.register
echo "Done. Time plugin running (PID $(cat "$PIDFILE"))."
