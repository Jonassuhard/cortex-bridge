#!/bin/bash
# ============================================================
# Cortex Bridge — switch the executor backend
# Toggles the Codex profile between the local Ollama config and
# whatever config was in place before (kept as a backup).
# Usage:  bash switch-executor.sh ollama | restore
# ============================================================
set -euo pipefail

PROFILE="${CODEX_HOME:-$HOME/.codex-cortex-bridge}"
BACKUP="$PROFILE/config.cloud.toml.bak"
CURRENT="$PROFILE/config.toml"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
  ollama)
    [ -f "$CURRENT" ] && cp "$CURRENT" "$BACKUP"
    cp "$SCRIPT_DIR/../configs/config.ollama.toml" "$CURRENT"
    echo "✅ Executor now routes to local Ollama (backup: $BACKUP)"
    ;;
  restore)
    if [ -f "$BACKUP" ]; then
      cp "$BACKUP" "$CURRENT"
      echo "✅ Previous config restored from $BACKUP"
    else
      echo "❌ No backup found at $BACKUP"
      exit 1
    fi
    ;;
  *)
    echo "Usage: bash switch-executor.sh ollama | restore"
    exit 1
    ;;
esac
