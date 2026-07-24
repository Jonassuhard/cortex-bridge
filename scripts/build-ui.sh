#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run typecheck
npm run lint
npm run build
printf '\nStatic UI built in %s/frontend/out\n' "$ROOT"
