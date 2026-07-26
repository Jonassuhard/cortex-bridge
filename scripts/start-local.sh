#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8420}"
cd "$ROOT/console"
"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" -m playwright install chromium
export PORT
exec "$PYTHON_BIN" server.py
