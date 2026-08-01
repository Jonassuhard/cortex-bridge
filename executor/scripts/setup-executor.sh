#!/usr/bin/env bash
# Produces a consent plan only. It never starts Ollama, accepts terms or pulls a model.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODEL="${2:-gpt-oss:20b}"
exec "$ROOT/scripts/install.sh" --dry-run --json --with-ollama-model "$MODEL"
