#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8420}"
cd "$ROOT/console"
if ! "$PYTHON_BIN" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pip install -r requirements.txt
fi
export PORT
exec "$PYTHON_BIN" server.py
