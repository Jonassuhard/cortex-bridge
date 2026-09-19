# Cortex Bridge 0.6.5 — plan fusionné ChatGPT ↔ Codex

## Décision d’architecture

Cortex n’est pas une seconde interface de travail. C’est un harnais compact :

- **ChatGPT** comprend le problème, demande le contexte utile, propose le plan
  et vérifie les résultats.
- **Codex/Luna** reste l’opérateur : il voit le dépôt, lit les fichiers,
  exécute les actions autorisées et rapporte les preuves.
- **Cortex** prépare le contexte, contrôle les permissions, conserve les
  versions transmises, journalise les échanges et évite les pertes silencieuses.
- **L’utilisateur** reste l’autorité pour les données sensibles, les actions externes,
  les suppressions et la publication.

La boucle cible est :

```text
demande → contexte initial borné → question ChatGPT
       → demande de complément → sélection vérifiée
       → action Codex/Luna → preuves (diff, tests, logs, captures)
       → rapport ChatGPT → validation ou étape suivante
```

La conversation ChatGPT utilisée pour cette revue confirme cette répartition.
Elle confirme aussi qu’un accès à une conversation dans l’application Codex ne
constitue pas une API publique que Cortex pourrait appeler seul après la fin de
la session.

## Livraisons et critères d’acceptation

### P0 — intégrité du contexte (livré dans ce candidat)

- Un résultat structuré ne peut plus être coupé à 4 000 caractères sans signal.
- Une lecture plafonnée expose la **limite effective** et `truncated: true`.
- Les extensions de code et les archives ZIP sont admises lorsque leur type est
  explicite.
- Les ZIP refusent les chemins absolus, `..`, séparateurs inversés, entrées
  chiffrées, liens symboliques et doublons.
- Tests de régression dédiés et suite complète verte.

**Historique :** `883b447a`, 854 tests Python annoncés le 14 septembre.
La validation de release a été rétractée le 19 septembre ; voir la
[correction des preuves](verification/evidence-correction-2026-09-19.md).

### P0 — canal de transmission honnête (partiellement livré)

- Le paquet de contexte est préparé, borné, hashé et journalisé.
- La préparation n’est jamais présentée comme une pièce jointe effectivement
  reçue par ChatGPT.
- Toute absence de canal d’attachement ou de réception est visible dans le
  rapport.

**Reste :** sceller un aller-retour avec un exécuteur externe réellement
  autorisé, sans transformer une observation navigateur en preuve d’API.

### P1 — compléments et versions

- Pagination des gros fichiers et des lots de contexte.
- Référence de version par fichier : taille, SHA-256, date et chemin relatif.
- Refus de réutiliser une source modifiée depuis le premier envoi.
- Images transmises comme images réelles quand le canal le permet, avec aperçu
  et approbation sinon.
- Rapport standard : actions, commandes, diff, tests, erreurs et captures.

**Critère :** un test où l’information décisive est à la fin d’un gros fichier,
où une image est nécessaire, puis où la source change avant la seconde étape.

### P1 — boucle superviseur/opérateur

- Un message initial explique le rôle de ChatGPT, le périmètre et les limites.
- ChatGPT peut demander un fichier, une plage, une capture ou un lien.
- Cortex transforme la demande en proposition structurée.
- L’opérateur approuve, refuse ou ajuste élément par élément.
- Après chaque action, l’opérateur renvoie une preuve vérifiable et non « fait ».
- La boucle s’arrête sur erreur, demande hors périmètre, ambiguïté ou absence de
  réception ; elle ne renvoie pas automatiquement en boucle.

### P2 — mesure et produit

- Benchmark sur les mêmes tâches : qualité, durée, nombre de tours ChatGPT,
  volume transmis, interventions humaines et taux d’échec.
- Comparaison avec opérateur seul et ChatGPT seul.
- Budget de messages et stratégie de repli documentés ; aucune promesse
  d’équivalence automatique avec Codex Ultra.
- Documentation d’installation compacte, diagnostic et procédure de reprise.

## Résultats historiques annoncés le 14 septembre 2026

- Backend : 854 tests PASS.
- Frontend : 214 tests unitaires PASS.
- Extension : 138 tests PASS.
- Navigateur : 27 tests PASS.
- Accessibilité : 4 tests PASS.
- Build, typecheck, lint contract et static output : PASS historique.
- Privacy : le contrôle du 19 septembre a invalidé le PASS précédent.
- Manifest `docs/verification/v0.6.5.json` : preuve rétractée, release non validée.
- Aller-retour texte Cortex → ChatGPT → Cortex observé : `REÇU`.

## Ce qui n’est pas déclaré comme validé

- Mission complète avec un exécuteur externe réel (Luna/Freebuff).
- Installation, doctor et désinstallation sur un compte macOS réellement propre.
- Pièce jointe desktop automatisée par une API publique Cortex.
- Upload d’une capture réellement consommée par ChatGPT dans ce candidat.
- Équivalence de qualité ou de quota avec Codex/Astra.

Ces points restent des gates distinctes. Le verdict de release est désormais
`EVIDENCE_INVALIDATED`. Une absence de test ne démontre pas un blocage juridique.

## Ordre d’exécution recommandé

1. Conserver les corrections P0 et leur manifest de preuve.
2. Exécuter le test source modifiée + pagination + image avec un opérateur
   autorisé ; conserver les traces brutes.
3. Exécuter une mission externe courte, puis une mission mini-site ; ne compter
   que les résultats observés.
4. Refaire le cycle install/doctor/reinstall/uninstall dans un environnement
   macOS propre.
5. Recalculer le manifest, faire relire le diff et seulement ensuite proposer
   le push de `main`.
