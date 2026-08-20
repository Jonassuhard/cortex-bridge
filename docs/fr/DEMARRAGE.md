# Démarrage — de zéro à la première mission en 10 minutes

## Ce qu'il te faut

- un Mac avec [Google Chrome](https://www.google.com/chrome/) ;
- [Python 3.11+](https://www.python.org/downloads/macos/) et [Git](https://git-scm.com/download/mac) ;
- un compte ChatGPT (la connexion reste 100 % la tienne, dans ton Chrome).

Ollama est **optionnel** : l'exécuteur déterministe fonctionne sans.

## 1. Télécharger

```bash
git clone <url-du-repo> cortex-bridge
cd cortex-bridge
```

## 2. Installer (2 commandes)

```bash
./scripts/install.sh --dry-run --json
```

Lis le plan affiché (aucun `sudo`, rien de caché), puis approuve-le avec son hash :

```bash
./scripts/install.sh --approve-plan LE_HASH_AFFICHE --json
```

## 3. Charger l'extension Chrome (une seule fois)

```bash
scripts/install-extension.sh
```

Le script ouvre `chrome://extensions` et copie le chemin pour toi.
Reste 3 gestes : **Mode développeur** → **Charger l'extension non empaquetée** → **⌘V, Entrée**.

## 4. Lancer Cortex

**Par double-clic** : `Cortex Bridge.command` dans le Finder — la console démarre et l'interface s'ouvre.

Ou par commande :

```bash
scripts/cortex.sh start
open http://127.0.0.1:8420
```

Tu veux que Cortex démarre tout seul à chaque ouverture de session ?

```bash
scripts/install-autostart.sh
```

## 5. Vérifier que tout est en place

```bash
scripts/cortex.sh doctor
```

Chaque ligne te dit ✅ ce qui est prêt et → comment réparer ce qui manque.
L'écran d'accueil de l'interface fait la même vérification visuellement.

## Et ensuite ?

→ [Guide d'utilisation](UTILISATION.md) : connecter ChatGPT et lancer ta première mission.
