# Utilisation — connecter ChatGPT et lancer une mission

## Connecter ChatGPT

1. Ouvre l'interface : http://127.0.0.1:8420
2. Clique **« Ouvrir et connecter ChatGPT »**.
3. Chrome s'ouvre (ou se met au premier plan) sur ChatGPT. Si tu n'es pas
   connecté, connecte-toi — c'est ta session, Cortex ne touche ni mot de passe
   ni CAPTCHA.
4. Le voyant passe à **« ChatGPT connecté »**.

> Cortex n'écrit **que sur les chats classiques**. Si ChatGPT t'ouvre une
> surface « Work », Cortex refuse (`WORK_SURFACE_REJECTED`) : reviens à un
> chat classique et relance.

## Lancer une mission

1. Choisis une conversation (ou **Nouvelle conversation**).
2. Écris ta demande dans le champ, comme un message ChatGPT normal.
3. Avant l'envoi, Cortex affiche un **pré-vol** : workspace, capacités,
   limites. Vérifie et confirme.
4. La boucle démarre : ChatGPT propose une décision → Cortex la valide →
   l'exécuteur local agit dans le workspace → Cortex vérifie la preuve →
   le rapport repart dans la conversation.

## Les approbations (le garde-fou central)

Par défaut, **aucune écriture ou commande ne part sans ton feu vert** :
la mission se met en pause « Approbation requise » et tu choisis :

- **Approuver une fois** — cette action seulement ;
- **approuver l'outil pour la mission** — dans les réglages d'approbation ;
- **Refuser** — la mission s'arrête proprement.

Le mode par défaut se change dans **Paramètres › Permissions**
(`workspace-write-with-approvals` recommandé).

## Lire le résultat

- La carte d'exécution montre chaque étape (décision, action, validation).
- **Voir le protocole** déplie l'échange technique complet pour audit.
- Le bouton **Historique** (barre latérale) liste toutes les missions
  passées, y compris les archives d'avant la v0.5.

## Si ChatGPT atteint sa limite d'utilisation

La mission se met en pause avec un message clair :
« ChatGPT a atteint sa limite d'utilisation… ». Attends la fin de la
limitation côté ChatGPT, puis appuie sur **Reprendre**. Rien n'est perdu.

## Arrêter

- **Annuler la mission** : bouton dans la carte d'exécution.
- **Tout arrêter** (urgence) : bouton STOP — chaque mission active se fige.
- **Arrêter la console** : `scripts/cortex.sh stop`.
