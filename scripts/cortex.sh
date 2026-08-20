#!/usr/bin/env bash
# Ownership-safe lifecycle for the local Cortex Bridge console.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8420}"
CORTEX_HOME="${CORTEX_HOME:-$HOME/.local/share/cortex-bridge}"
case "$CORTEX_HOME" in
  /*) ;;
  *) echo "CORTEX_HOME must be absolute" >&2; exit 2 ;;
esac
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$CORTEX_HOME/browser-cache}"
export PYTHONPATH="$ROOT/console:$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [ -n "${PYTHON_BIN:-}" ]; then
  PYTHON="$PYTHON_BIN"
elif [ -x "$CORTEX_HOME/venv/bin/python" ]; then
  PYTHON="$CORTEX_HOME/venv/bin/python"
else
  PYTHON="python3"
fi

PIDS_DIR="$CORTEX_HOME/pids"
LOGS_DIR="$CORTEX_HOME/logs"
PID_RECORD="$PIDS_DIR/console.json"
LOG_FILE="${CORTEX_LOG:-$LOGS_DIR/console.log}"
START_LOCK="$PIDS_DIR/start.lock"
OWNERSHIP="$ROOT/console/process_ownership.py"
COMMAND="${1:-help}"
OUTPUT_MODE="${2:-}"

_ownership_status() {
  "$PYTHON" "$OWNERSHIP" status \
    --record "$PID_RECORD" --port "$PORT"
}

_json_field() {
  local payload="$1" field="$2"
  "$PYTHON" -c 'import json,sys; value=json.loads(sys.argv[1]).get(sys.argv[2]); print("" if value is None else value)' "$payload" "$field"
}

_port_pid() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1 || true
}

_status_text() {
  local payload="$1" state pid reason
  state="$(_json_field "$payload" state)"
  pid="$(_json_field "$payload" pid)"
  reason="$(_json_field "$payload" reason)"
  case "$state" in
    owned)
      printf 'Cortex Bridge fonctionne : http://127.0.0.1:%s (pid %s)\n' "$PORT" "$pid"
      ;;
    stopped)
      printf 'Cortex Bridge est arrêté.\nPour le lancer : scripts/cortex.sh start\n'
      ;;
    stale)
      printf 'Aucune instance active : la fiche processus était périmée et a été nettoyée.\nPour lancer : scripts/cortex.sh start\n'
      ;;
    foreign)
      printf 'Le port %s est utilisé par un autre processus :\n' "$PORT"
      "$PYTHON" -c '
import json, sys
payload = json.loads(sys.argv[1])
commands = payload.get("listener_commands") or {}
for pid in payload.get("listener_pids") or []:
    command = commands.get(str(pid)) or commands.get(pid) or ""
    print(f"  pid {pid} : {command or chr(63)}")
' "$payload"
      printf "Si c'est une console Cortex lancée à la main : kill <pid>, puis scripts/cortex.sh start\n"
      ;;
    *)
      printf 'État du serveur incertain : %s (%s)\n' "$state" "$reason"
      ;;
  esac
}

case "$COMMAND" in
  start)
    mkdir -p "$PIDS_DIR" "$LOGS_DIR"
    if ! mkdir "$START_LOCK" 2>/dev/null; then
      echo "Cortex Bridge start is already in progress." >&2
      exit 1
    fi
    trap 'rmdir "$START_LOCK" 2>/dev/null || true' EXIT
    if ! "$PYTHON" -c 'import fastapi,uvicorn,playwright,websockets'; then
      echo "Cortex Bridge runtime dependencies are incomplete. Re-run the approved installer plan." >&2
      exit 1
    fi
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    if [ "$state" = "owned" ]; then
      _status_text "$status_json"
      exit 0
    fi
    if [ "$state" = "foreign" ]; then
      echo "Refusing to start: port $PORT is owned by a foreign process." >&2
      exit 1
    fi
    if [ "$state" != "stopped" ] && [ "$state" != "stale" ]; then
      echo "Refusing to start: process ownership state is $state." >&2
      exit 1
    fi
    if [ "$state" = "stale" ] && [ -n "$(_port_pid)" ]; then
      echo "Refusing to start: stale identity and an unverified listener on port $PORT." >&2
      exit 1
    fi

    instance_token="$($PYTHON -c 'import secrets; print(secrets.token_urlsafe(32))')"
    (
      cd "$ROOT/console"
      CORTEX_HOME="$CORTEX_HOME" PORT="$PORT" CORTEX_INSTANCE_TOKEN="$instance_token" \
        nohup "$PYTHON" server.py >>"$LOG_FILE" 2>&1 &
      echo "$!" > "$PIDS_DIR/launch.pid"
    )
    pid="$(tr -cd '0-9' < "$PIDS_DIR/launch.pid")"
    for _attempt in $(seq 1 40); do
      if curl -sf --max-time 1 "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1 \
        && [ "$(_port_pid)" = "$pid" ]; then
        "$PYTHON" "$OWNERSHIP" capture \
          --record "$PID_RECORD" --pid "$pid" --port "$PORT" --token="$instance_token" >/dev/null
        rm -f "$PIDS_DIR/launch.pid"
        echo "Cortex Bridge ready: http://127.0.0.1:$PORT"
        echo "Logs: $LOG_FILE"
        exit 0
      fi
      sleep 0.25
    done
    echo "Cortex Bridge did not become ready; launch pid was $pid. No unverified process was signalled." >&2
    exit 1
    ;;

  stop)
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    if [ "$state" = "stopped" ]; then
      echo "Cortex Bridge is stopped."
      exit 0
    fi
    if [ "$state" != "owned" ]; then
      echo "Refusing to stop: process state is $state, not owned." >&2
      exit 1
    fi
    pid="$(_json_field "$status_json" pid)"
    kill -TERM "$pid"
    for _attempt in $(seq 1 40); do
      status_json="$(_ownership_status)"
      state="$(_json_field "$status_json" state)"
      if [ "$state" = "stopped" ] || { [ "$state" = "stale" ] && [ -z "$(_port_pid)" ]; }; then
        rm -f "$PID_RECORD"
        echo "Cortex Bridge stopped."
        exit 0
      fi
      if [ "$state" = "foreign" ]; then
        echo "Cortex owner exited but a foreign listener now owns port $PORT; no further signal sent." >&2
        exit 1
      fi
      sleep 0.25
    done
    echo "Owned process did not stop within 10 seconds; no force-kill was attempted." >&2
    exit 1
    ;;

  status)
    status_json="$(_ownership_status)"
    state="$(_json_field "$status_json" state)"
    # A stale record whose process and listener are both gone only creates
    # confusion: clean it up so the next start never sees it.
    if [ "$state" = "stale" ] && [ -z "$(_port_pid)" ]; then
      rm -f "$PID_RECORD"
    fi
    if [ "$OUTPUT_MODE" = "--json" ]; then
      printf '%s\n' "$status_json"
    else
      _status_text "$status_json"
    fi
    [ "$state" = "owned" ]
    ;;

  doctor)
    if [ -n "$OUTPUT_MODE" ]; then
      exec "$PYTHON" "$ROOT/console/installer.py" doctor "$OUTPUT_MODE"
    fi
    exec "$PYTHON" "$ROOT/console/installer.py" doctor
    ;;

  logs)
    exec tail -f "$LOG_FILE"
    ;;

  help|--help|-h|*)
    echo "Usage: scripts/cortex.sh {start|stop|status [--json]|doctor [--json]|logs}"
    ;;
esac
