#!/usr/bin/env bash
# Cortex Bridge — démarrage par double-clic.
#
# Double-clique ce fichier dans le Finder : la console démarre, Chrome s'ouvre
# sur l'interface Cortex avec le bon profil, et les étapes suivantes sont
# affichées. Aucune commande à taper.
set -euo pipefail

cd "$(dirname "$0")"

# Allow the same launcher to expose diagnostics without attempting a start.
if [ "$#" -gt 0 ]; then
  exec scripts/cortex.sh "$@"
fi

echo "Cortex Bridge — démarrage…"
if scripts/cortex.sh go; then
  echo
  echo "✅ Cortex Bridge est prêt. Tu peux fermer cette fenêtre Terminal."
  echo "   Pour tout vérifier plus tard : scripts/cortex.sh doctor"
else
  status=$?
  echo
  echo "❌ Le démarrage a échoué (code $status)."
  echo "   Diagnostic détaillé : double-clique avec l'argument doctor, ou exécute :"
  echo "   scripts/cortex.sh doctor"
  if [ "$status" -eq 3 ]; then
    echo "   Le volume de stockage chiffré requis n'est pas monté ou n'est pas visible."
    echo "   Monte/déverrouille l'image configurée, puis relance Cortex."
  fi
  read -r -p "Appuie sur Entrée pour fermer…" || true
  exit "$status"
fi
