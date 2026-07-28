#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then PYTHON=python3; fi

"$PYTHON" -m unittest discover -s tests -v
"$PYTHON" -m py_compile \
  console/chat.py \
  console/settings.py \
  console/server.py \
  console/missions.py \
  orchestration/loop.py \
  transport/chatgpt_web/adapter.py \
  transport/chatgpt_web/fixture.py

if command -v node >/dev/null 2>&1; then
  "$PYTHON" - <<'PY'
from pathlib import Path
import re
source = Path("frontend/fallback/index.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script(?:[^>]*)>(.*?)</script>", source, re.S)
if not scripts:
    raise SystemExit("fallback contains no JavaScript")
Path("/tmp/cortex-bridge-fallback.js").write_text("\n".join(scripts), encoding="utf-8")
PY
  node --check /tmp/cortex-bridge-fallback.js
fi

if [[ -d frontend/node_modules ]]; then
  (cd frontend && npm audit --audit-level=high && npm run test:unit && npm run test:coverage && npm run typecheck && npm run lint && npm run build && npm run test:e2e && npm run test:a11y)
else
  printf '\nFrontend dependencies are not installed; skipped TypeScript/ESLint.\n'
fi

"$PYTHON" scripts/verify-runtime.py --json
if [[ -x scripts/check-public-privacy.sh ]]; then scripts/check-public-privacy.sh; fi
