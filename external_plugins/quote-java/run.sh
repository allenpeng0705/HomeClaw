#!/usr/bin/env bash
# Start Quote (Java) plugin server and register with Core (one command).
# Run from project root:  ./external_plugins/quote-java/run.sh
# Requires: Core running, curl, JDK 11+, Maven.

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PLUGIN_DIR/../.run_logs"
mkdir -p "$LOG_DIR"
PIDFILE="$LOG_DIR/quote-java.pid"
LOGFILE="$LOG_DIR/quote-java.log"

if [ -f "$PIDFILE" ]; then
  OLD_PID=$(cat "$PIDFILE" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$OLD_PID" ] && [ "$OLD_PID" -eq "$OLD_PID" ] 2>/dev/null && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[quote-java] Already running (PID $OLD_PID). Registering..."
    cd "$PLUGIN_DIR" && bash register.sh
    echo "Done."
    exit 0
  fi
  rm -f "$PIDFILE"
fi

echo "[quote-java] Starting server on port 3113..."
cd "$PLUGIN_DIR"
mvn -q compile exec:java -Dexec.mainClass=QuotePlugin >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "[quote-java] Waiting for server..."
n=0
while [ $n -lt 20 ]; do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:3113/health" 2>/dev/null | grep -q 200; then
    break
  fi
  n=$((n + 1))
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[quote-java] Timeout waiting for server. Check $LOGFILE" >&2
  exit 1
fi

echo "[quote-java] Registering with Core..."
bash register.sh
echo "Done. Quote (Java) plugin running (PID $(cat "$PIDFILE"))."
