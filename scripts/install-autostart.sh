#!/usr/bin/env bash
# Cortex Bridge — démarrage automatique à l'ouverture de session (optionnel).
#
# Installe un LaunchAgent macOS qui lance la console Cortex à chaque connexion.
# Usage :
#   scripts/install-autostart.sh           → activer le démarrage automatique
#   scripts/install-autostart.sh --remove  → désactiver
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.cortex-bridge.console"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "${1:-}" = "--remove" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✅ Démarrage automatique désactivé. La console ne se lancera plus toute seule."
  exit 0
fi

if [ ! -x "$ROOT/scripts/cortex.sh" ]; then
  echo "❌ scripts/cortex.sh introuvable — es-tu dans le dossier du projet ?" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT/scripts/cortex.sh</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/cortex-bridge-autostart.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/cortex-bridge-autostart.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

cat <<EOF
✅ Démarrage automatique activé.
   La console Cortex se lancera à chaque ouverture de session,
   et l'interface reste sur http://127.0.0.1:8420

   Pour désactiver : scripts/install-autostart.sh --remove
EOF
