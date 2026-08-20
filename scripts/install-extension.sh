#!/usr/bin/env bash
# Cortex Bridge — assistant de chargement de l'extension Chrome.
#
# Chrome interdit d'installer une extension locale à la place de l'utilisateur.
# Ce script fait tout ce qui est automatisable :
#   1. copie le chemin de l'extension dans le presse-papiers ;
#   2. ouvre chrome://extensions dans Chrome ;
#   3. affiche les 3 gestes restants.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTENSION_DIR="$ROOT/chrome-extension"

if [ ! -f "$EXTENSION_DIR/manifest.json" ]; then
  echo "❌ Extension introuvable : $EXTENSION_DIR/manifest.json" >&2
  echo "   Es-tu bien dans le dossier du projet Cortex Bridge ?" >&2
  exit 1
fi

if ! [ -d "/Applications/Google Chrome.app" ]; then
  echo "❌ Google Chrome n'est pas installé dans /Applications." >&2
  echo "   Installe-le : https://www.google.com/chrome/" >&2
  exit 1
fi

printf '%s' "$EXTENSION_DIR" | pbcopy
open -a "Google Chrome" "chrome://extensions" || open "chrome://extensions"

cat <<EOF
✅ Presque fini — 3 gestes dans la page Chrome qui vient de s'ouvrir :

  1. Active le « Mode développeur » (interrupteur en haut à droite).
  2. Clique « Charger l'extension non empaquetée ».
  3. Colle le chemin (déjà copié pour toi) : ⌘V puis Entrée.

     $EXTENSION_DIR

Ensuite, dans Cortex (http://127.0.0.1:8420) :
  → clique « Ouvrir et connecter ChatGPT ».

Pour vérifier que tout est en place : scripts/cortex.sh doctor
EOF
