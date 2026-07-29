#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORTEX_HOME="${CORTEX_HOME:-$HOME/.local/share/cortex-bridge}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$CORTEX_HOME/browser-cache}"
PYTHON="${PYTHON_BIN:-$CORTEX_HOME/venv/bin/python}"
PORT="${PORT:-8420}"
if [ ! -x "$PYTHON" ]; then
  echo "Cortex Bridge runtime is not installed. Run scripts/install.sh --dry-run --json first." >&2
  exit 1
fi
if ! PYTHONPATH="$ROOT/console:$ROOT" "$PYTHON" -c 'import fastapi,uvicorn,playwright'; then
  echo "Cortex Bridge dependencies are incomplete. Re-run the approved installer plan." >&2
  exit 1
fi
cd "$ROOT/console"
export PORT CORTEX_HOME
exec "$PYTHON" server.py
