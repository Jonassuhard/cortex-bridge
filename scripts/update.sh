#!/usr/bin/env bash
# Cortex Bridge — mise à jour en une commande.
#
#   scripts/update.sh
#
# Étapes : récupère la dernière version du code, prépare le nouveau plan
# d'installation, puis te donne LA commande d'approbation à copier-coller.
# Rien n'est appliqué sans ton approbation explicite (comme à l'installation).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "1/3 — Récupération de la dernière version…"
if ! git pull --ff-only; then
  echo "❌ git pull a échoué (modifications locales ?)." >&2
  echo "   Vois l'état avec : git status" >&2
  exit 1
fi

echo "2/3 — Préparation du plan d'installation…"
PLAN_JSON="$(./scripts/install.sh --dry-run --json)"
PLAN_HASH="$(printf '%s' "$PLAN_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["plan_hash"])')"

echo "3/3 — Plan prêt. Pour terminer la mise à jour, copie-colle :"
echo
echo "   ./scripts/install.sh --approve-plan $PLAN_HASH --json"
echo "   scripts/cortex.sh stop && scripts/cortex.sh start"
echo
echo "Puis dans Chrome : chrome://extensions › bouton ↻ sur Cortex Bridge"
echo "(nécessaire seulement si l'extension a changé)."
echo
echo "Vérification finale : scripts/cortex.sh doctor"
