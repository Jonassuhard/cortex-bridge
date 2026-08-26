#!/usr/bin/env bash
# Cortex Bridge — démarrage par double-clic.
#
# Double-clique ce fichier dans le Finder : la console démarre, Chrome s'ouvre
# sur l'interface Cortex avec le bon profil, et les étapes suivantes sont
# affichées. Aucune commande à taper.
set -euo pipefail

cd "$(dirname "$0")"

echo "Cortex Bridge — démarrage…"
if scripts/cortex.sh go; then
  echo
  echo "✅ Cortex Bridge est prêt. Tu peux fermer cette fenêtre Terminal."
  echo "   Pour tout vérifier plus tard : scripts/cortex.sh doctor"
else
  echo
  echo "❌ Le démarrage a échoué. Lance scripts/cortex.sh doctor pour voir ce qui manque."
  read -r -p "Appuie sur Entrée pour fermer…" || true
  exit 1
fi
