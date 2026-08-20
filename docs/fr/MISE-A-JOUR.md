# Mise à jour

## En une commande

```bash
scripts/update.sh
```

Le script :

1. récupère la dernière version du code (`git pull --ff-only`) ;
2. prépare le nouveau plan d'installation **sans rien appliquer** ;
3. t'affiche la commande d'approbation à copier-coller, par exemple :

```bash
./scripts/install.sh --approve-plan NOUVEAU_HASH --json
scripts/cortex.sh stop && scripts/cortex.sh start
```

Rien ne change sur ta machine sans cette approbation explicite — comme à
la première installation.

## Après la mise à jour

- **Extension Chrome** : si elle a changé, va sur `chrome://extensions` et
  clique le bouton **↻** de Cortex Bridge.
- **Vérification** : `scripts/cortex.sh doctor` doit être tout ✅.
- **Tes données** (réglages, historique, workspaces) vivent hors du dossier
  du projet (`CORTEX_HOME`) : une mise à jour ne les touche jamais.

## Si git pull refuse

Des modifications locales bloquent la mise à jour. Vois-les avec
`git status`, puis soit tu les conserves (`git stash`), soit tu demandes de
l'aide avec la sortie de `git status` sous la main.
