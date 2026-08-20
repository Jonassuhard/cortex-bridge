#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  "$ROOT/scripts/npmw" ci
fi
"$ROOT/scripts/npmw" run typecheck
"$ROOT/scripts/npmw" run lint
"$ROOT/scripts/npmw" run build
"$ROOT/scripts/normalize-static-output.py" "$ROOT/frontend/out"
printf '\nStatic UI built in %s/frontend/out\n' "$ROOT"
