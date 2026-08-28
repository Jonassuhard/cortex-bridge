#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_CORTEX_HOME="${CORTEX_HOME:-$HOME/.local/share/cortex-bridge}"
if CORTEX_HOME="$(
  CORTEX_HOME="$RAW_CORTEX_HOME" bash "$ROOT/scripts/cortex.sh" runtime-home
)"; then
  :
else
  status=$?
  exit "$status"
fi
export CORTEX_HOME
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$CORTEX_HOME/browser-cache}"
export PYTHONPATH="$ROOT/console:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON_BIN:-$CORTEX_HOME/venv/bin/python}"
PORT="${PORT:-8420}"
if [ ! -x "$PYTHON" ]; then
  echo "Cortex Bridge runtime is not installed. Run scripts/install.sh --dry-run --json first." >&2
  exit 1
fi
if ! "$PYTHON" -c 'import fastapi,uvicorn,playwright,websockets'; then
  echo "Cortex Bridge dependencies are incomplete. Re-run the approved installer plan." >&2
  exit 1
fi
CORTEX_HOME="$CORTEX_HOME" PYTHON_BIN="$PYTHON" \
  bash "$ROOT/scripts/cortex.sh" storage-check
cd "$ROOT/console"
export PORT CORTEX_HOME
exec "$PYTHON" server.py
