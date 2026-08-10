#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ -x "$PYTHON" ]]; then
  PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")"
else
  PYTHON="$(command -v python3)"
fi

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
  node --test chrome-extension/tests/extension.test.mjs
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
  (
    cd frontend
    "$ROOT/scripts/npmw" audit --audit-level=high
    "$ROOT/scripts/npmw" run test:unit
    "$ROOT/scripts/npmw" run test:coverage
    "$ROOT/scripts/npmw" run typecheck
    "$ROOT/scripts/npmw" run lint
    "$ROOT/scripts/npmw" run build
    "$PYTHON" "$ROOT/scripts/normalize-static-output.py" "$ROOT/frontend/out"
    "$ROOT/scripts/npmw" run test:e2e
    "$ROOT/scripts/npmw" run test:a11y
  )
else
  printf '\nFrontend dependencies are not installed; skipped TypeScript/ESLint.\n'
fi

"$PYTHON" scripts/verify-runtime.py --json
if [[ -x scripts/check-public-privacy.sh ]]; then
  scripts/check-public-privacy.sh \
    --markers tests/fixtures/privacy/ci-markers.txt \
    --fingerprints scripts/privacy-fingerprints.json \
    --url-allowlist scripts/public-url-allowlist.txt
fi
"$PYTHON" scripts/verify-release-evidence.py docs/verification/v0.5.0.json
