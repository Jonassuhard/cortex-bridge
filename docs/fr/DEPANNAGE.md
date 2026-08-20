# Dépannage — qu'est-ce qu'il manque ?

Premier réflexe, toujours :

```bash
scripts/cortex.sh doctor
```

Chaque ligne ❌ ou ⚠️ est suivie d'une flèche **→** avec la réparation exacte.
Ci-dessous, les cas classiques.

## La console ne démarre pas / ne répond pas

| Symptôme | Cause | Solution |
|---|---|---|
| `scripts/cortex.sh status` dit « arrêté » | Console non lancée | `scripts/cortex.sh start` |
| « fiche processus périmée » | Ancienne instance morte sans se déclarer | `status` la nettoie tout seul, puis `start` |
| « le port 8420 est utilisé par un autre processus » | Une console lancée à la main (hors scripts) tourne encore | `kill <pid affiché>`, puis `scripts/cortex.sh start` |
| « dependencies are incomplete » | Installation jamais faite ou cassée | Rejoue le plan : `./scripts/install.sh --dry-run --json` puis `--approve-plan` |

## L'extension Chrome

| Symptôme | Cause | Solution |
|---|---|---|
| « Extension Chrome introuvable » au doctor | Extension pas chargée dans Chrome | `scripts/install-extension.sh` puis les 3 gestes affichés |
| « Extension à recharger » | Extension mise à jour côté disque | `chrome://extensions` › bouton **↻** sur Cortex Bridge |
| « Jumelage en attente » | Extension chargée mais jamais connectée | Dans l'interface Cortex : **Ouvrir et connecter ChatGPT** |

## ChatGPT

| Symptôme | Cause | Solution |
|---|---|---|
| « Connexion à ChatGPT requise » | Pas connecté dans Chrome | Connecte-toi dans l'onglet ChatGPT, puis réessaie |
| « Vérification humaine » | CAPTCHA Cloudflare | Termine-le à la main dans l'onglet, puis réessaie |
| « ChatGPT a atteint sa limite d'utilisation » | Quota ChatGPT épuisé | Attends la fin de la limitation, puis **Reprendre** la mission |
| `WORK_SURFACE_REJECTED` | La conversation est une surface **Work** | Cortex n'écrit que sur le chat classique : ouvre un chat classique et relance |

## Workspace

| Symptôme | Cause | Solution |
|---|---|---|
| « Workspace par défaut invalide » | Le dossier n'existe plus (ex. ancien chemin dans /tmp purgé par macOS) | Le défaut est maintenant auto-créé dans `~/cortex-workspaces` ; sinon choisis un dossier dans **Paramètres › Général** |

## Ollama (optionnel)

| Symptôme | Cause | Solution |
|---|---|---|
| « Aucun service Ollama détecté » | Application Ollama non lancée | Lance Ollama (tes modèles sur disque externe restent configurés) |
| « Modèle exécuteur introuvable » | Modèle pas installé | `ollama pull <nom>` ou change de modèle dans **Paramètres › Modèles** |

## Rien ne marche ?

Génère le rapport de diagnostic depuis **Paramètres › Diagnostics** et
partage-le : il ne contient ni identifiant ni contenu de conversation.
