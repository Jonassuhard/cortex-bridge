#!/usr/bin/env bash
# cortex — one command to run Cortex Bridge.
#
#   cortex start    Start the local console (background) and print the URL
#   cortex stop     Stop the console
#   cortex status   Show console / Ollama / WebBridge health at a glance
#   cortex logs     Tail the console log
#
# Everything stays on 127.0.0.1. No sudo, no external services.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8420}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
WEBBRIDGE_PORT="${WEBBRIDGE_PORT:-10086}"
DATA_DIR="$ROOT/console/data"
PID_FILE="$DATA_DIR/cortex.pid"
LOG_FILE="${CORTEX_LOG:-/tmp/cortex-console.log}"

_cmd="${1:-help}"

_port_pid() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

_check() { # name port url
  local name="$1" port="$2" url="$3"
  local pid; pid="$(_port_pid "$port")"
  if [ -n "$pid" ] && curl -sf --max-time 2 "$url" >/dev/null 2>&1; then
    printf '  ✅ %-11s running (127.0.0.1:%s, pid %s)\n' "$name" "$port" "$pid"
    return 0
  elif [ -n "$pid" ]; then
    printf '  ⚠️  %-11s port %s listens (pid %s) but health check failed\n' "$name" "$port" "$pid"
    return 1
  else
    printf '  ❌ %-11s not running (expected on 127.0.0.1:%s)\n' "$name" "$port"
    return 1
  fi
}

case "$_cmd" in
  start)
    existing="$(_port_pid "$PORT")"
    if [ -n "$existing" ]; then
      echo "Cortex Bridge console already running (pid $existing)."
      echo "→ http://127.0.0.1:$PORT"
      exit 0
    fi
    mkdir -p "$DATA_DIR"
    echo "Starting Cortex Bridge console…"
    ( cd "$ROOT/console" && nohup python3 server.py > "$LOG_FILE" 2>&1 & echo $! > "$PID_FILE" )
    for _ in $(seq 1 20); do
      if curl -sf --max-time 1 "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; then
        echo "✅ Console ready → http://127.0.0.1:$PORT"
        echo "   Logs: $LOG_FILE"
        exit 0
      fi
      sleep 0.5
    done
    echo "❌ Console did not become ready. Last log lines:" >&2
    tail -20 "$LOG_FILE" >&2 || true
    exit 1
    ;;

  stop)
    stopped=0
    if [ -f "$PID_FILE" ]; then
      pid="$(cat "$PID_FILE")"
      if [ -n "$pid" ] && kill "$pid" 2>/dev/null; then stopped=1; fi
      rm -f "$PID_FILE"
    fi
    pid="$(_port_pid "$PORT")"
    if [ -n "$pid" ]; then kill "$pid" 2>/dev/null && stopped=1; fi
    # Wait for the port to actually be released (SIGTERM is async).
    for _ in $(seq 1 20); do
      [ -z "$(_port_pid "$PORT")" ] && break
      sleep 0.5
    done
    pid="$(_port_pid "$PORT")"
    if [ -n "$pid" ]; then kill -9 "$pid" 2>/dev/null || true; sleep 1; fi
    if [ "$stopped" = "1" ]; then
      echo "✅ Cortex Bridge console stopped."
    else
      echo "Console was not running."
    fi
    ;;

  status)
    echo "Cortex Bridge status:"
    rc=0
    _check "Console" "$PORT" "http://127.0.0.1:$PORT/api/status" || rc=1
    _check "Ollama" "$OLLAMA_PORT" "http://127.0.0.1:$OLLAMA_PORT/api/tags" || rc=1
    _check "WebBridge" "$WEBBRIDGE_PORT" "http://127.0.0.1:$WEBBRIDGE_PORT/status" || rc=1
    if [ "$rc" = "0" ]; then
      echo "→ http://127.0.0.1:$PORT"
    else
      echo ""
      echo "Hints:"
      echo "  Console   → scripts/cortex.sh start"
      echo "  Ollama    → launch the Ollama app (models on your external drive stay configured)"
      echo "  WebBridge → open Chrome with the WebBridge extension enabled"
    fi
    exit "$rc"
    ;;

  logs)
    exec tail -f "$LOG_FILE"
    ;;

  help|--help|-h|*)
    sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    ;;
esac
