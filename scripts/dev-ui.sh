#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  "$ROOT/scripts/npmw" ci
fi
exec "$ROOT/scripts/npmw" run dev
