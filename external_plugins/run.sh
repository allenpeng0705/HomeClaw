#!/usr/bin/env bash
# Start all external plugin servers and register them with Core (one step).
# Run from project root after Core is running:  ./external_plugins/run.sh
# Or run specific plugins:  ./external_plugins/run.sh time companion quote-node
# Requires: curl, and for each plugin the runtime (python3, node, go, mvn).

set -e
CORE_URL="${CORE_URL:-http://127.0.0.1:9000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

LOG_DIR="${SCRIPT_DIR}/.run_logs"
mkdir -p "$LOG_DIR"

# Wait for a plugin's /health to return 200 (timeout 20s).
wait_for_health() {
  local port=$1
  local name=$2
  local url="http://127.0.0.1:${port}/health"
  local n=0
  while [ $n -lt 20 ]; do
    if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q 200; then
      return 0
    fi
    n=$((n + 1))
    sleep 1
  done
  echo "  $name: timeout waiting for port $port" >&2
  return 1
}

# Start one plugin server in background; write PID to .run_logs/<name>.pid and log to .run_logs/<name>.log.
run_plugin_background() {
  local name=$1
  local port=$2
  local start_cmd=$3
  local register_cmd=$4
  local pidfile="$LOG_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"

  if [ -f "$pidfile" ]; then
    local old_pid
    old_pid=$(cat "$pidfile" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$old_pid" ] && [ "$old_pid" -eq "$old_pid" ] 2>/dev/null && kill -0 "$old_pid" 2>/dev/null; then
      echo "[$name] Already running (PID $old_pid). Registering..."
      (eval "$register_cmd") || true
      return 0
    fi
    rm -f "$pidfile"
  fi

  echo "[$name] Starting server on port $port..."
  (eval "$start_cmd") >> "$logfile" 2>&1 &
  echo $! > "$pidfile"
  if ! wait_for_health "$port" "$name"; then
    echo "[$name] Server failed to become ready. Check $logfile" >&2
    return 1
  fi
  echo "[$name] Registering with Core..."
  (eval "$register_cmd") || true
}

run_time() {
  run_plugin_background "time" 3102 \
    "python -m external_plugins.time.server" \
    "python -m external_plugins.time.register"
}

run_companion() {
  run_plugin_background "companion" 3103 \
    "python -m external_plugins.companion.server" \
    "python -m external_plugins.companion.register"
}

run_quote_node() {
  local dir="$SCRIPT_DIR/quote-node"
  if [ ! -f "$dir/node_modules/.exists" ] 2>/dev/null && [ ! -d "$dir/node_modules" ]; then
    echo "[quote-node] Installing npm dependencies..."
    (cd "$dir" && npm install --no-fund --no-audit)
  fi
  run_plugin_background "quote-node" 3111 \
    "cd $dir && node server.js" \
    "cd $dir && node register.js"
}

run_time_go() {
  local dir="$SCRIPT_DIR/time-go"
  run_plugin_background "time-go" 3112 \
    "cd $dir && go run ." \
    "cd $dir && bash register.sh"
}

run_quote_java() {
  local dir="$SCRIPT_DIR/quote-java"
  run_plugin_background "quote-java" 3113 \
    "cd $dir && mvn -q compile exec:java -Dexec.mainClass=QuotePlugin" \
    "cd $dir && bash register.sh"
}

# Default: run all.
PLUGINS="${*:-time companion quote-node time-go quote-java}"
echo "Core URL: $CORE_URL"
echo "Plugins:  $PLUGINS"
echo "Logs:     $LOG_DIR/"
echo ""

for p in $PLUGINS; do
  case "$p" in
    time)        ( run_time ) || echo "[time] Failed (see above). Continuing." ;;
    companion)   ( run_companion ) || echo "[companion] Failed (see above). Continuing." ;;
    quote-node)  ( run_quote_node ) || echo "[quote-node] Failed (see above). Continuing." ;;
    time-go)     ( run_time_go ) || echo "[time-go] Failed (see above). Continuing." ;;
    quote-java)  ( run_quote_java ) || echo "[quote-java] Failed (see above). Continuing." ;;
    *)
      echo "Unknown plugin: $p (use: time, companion, quote-node, time-go, quote-java)" >&2
      exit 1
      ;;
  esac
done

echo ""
echo "Done. All requested plugins are running and registered. Stop servers by killing PIDs in $LOG_DIR/*.pid"
