#!/usr/bin/env bash
# Start Time (Go) plugin server and register with Core (one command).
# Run from project root:  ./external_plugins/time-go/run.sh
# Requires: Core running, curl, Go.

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PLUGIN_DIR/../.run_logs"
mkdir -p "$LOG_DIR"
PIDFILE="$LOG_DIR/time-go.pid"
LOGFILE="$LOG_DIR/time-go.log"

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$OLD_PID" ] && [ "$OLD_PID" -eq "$OLD_PID" ] 2>/dev/null && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[time-go] Already running (PID $OLD_PID). Registering..."
    cd "$PLUGIN_DIR" && bash register.sh
    echo "Done."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "[time-go] Starting server on port 3112..."
cd "$PLUGIN_DIR"
go run . >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[time-go] Waiting for server..."
n=0
while [ $n -lt 20 ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3112/health" 2>/dev/null | grep -q 200; then
    break
  fi
  n=$((n + 1))
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[time-go] Timeout waiting for server. Check $LOGFILE" >&2
  exit 1
fi

echo "[time-go] Registering with Core..."
bash register.sh
echo "Done. Time (Go) plugin running (PID $(cat "$PIDFILE"))."
