# ChatGPT supervisor protocol

Version: `desktop-supervisor.v1`

Ce fichier est la fiche de démarrage de chaque boucle Codex → ChatGPT. Il
décrit comment fournir un contexte utile au modèle de planification, comment
recevoir sa décision et comment rapporter l'exécution. Il ne donne jamais un
accès implicite à tout le disque.

## 1. Rôle des composants

```text
Codex (interface visible et superviseur)
  → conversation ChatGPT choisie (planification)
  → Cortex / outils locaux (contexte et exécution)
  → rapport vérifié dans la même conversation ChatGPT
```

- Codex prépare le paquet de contexte, choisit la conversation cible et
  observe la réponse.
- ChatGPT propose le chemin, mais ne peut pas déclarer qu'une action locale a
  réussi.
- Cortex exécute seulement des actions validées par sa politique et renvoie
  des preuves.
- Les demandes de fichiers, captures ou liens sont des demandes de contexte,
  pas une autorisation de lecture ou d'envoi.

## 2. Paquet de contexte à préparer

Avant chaque nouvelle boucle, Codex prépare un paquet limité. Il utilise la
conversation complète uniquement si l'utilisateur l'a demandé et si elle ne
contient pas de secrets ou de données privées hors sujet. Sinon, il envoie un
résumé fidèle et les extraits pertinents.

```yaml
protocol: desktop-supervisor.v1
goal: "Problème ou résultat à obtenir"
conversation:
  mode: relevant_excerpt # relevant_excerpt | full_with_consent
  text: "Demande et échanges pertinents, sans inventer"
facts:
  - value: "Fait observé"
    source: "commande, test, capture ou message"
    confidence: verified # verified | inferred | unclear
constraints:
  - "Ne pas utiliser d'API non autorisée"
  - "Ne pas sortir du workspace sélectionné"
available_context:
  - kind: file
    path: "src/example.ts"
    size_bytes: 1234
    sha256: "..."
    reason: "Pourquoi ce fichier peut être utile"
    transmission: proposal_required
  - kind: screenshot
    target: "fenêtre ou application explicitement sélectionnée"
    reason: "Pourquoi une image est nécessaire"
    transmission: proposal_required
  - kind: link
    url: "https://chatgpt.com/"
    reason: "Pourquoi ce lien est nécessaire"
    transmission: proposal_required
capabilities:
  - read_file
  - search_text
  - run_tests
  - apply_patch
missing_information: []
```

Règles de préparation :

- Les chemins sont relatifs au workspace et sont normalisés avant transmission.
- Les secrets, tokens, mots de passe, cookies, données personnelles et fichiers
  sans rapport sont retirés.
- Chaque fichier proposé affiche son chemin relatif, sa taille, son empreinte
  et sa raison.
- Une capture est limitée à la fenêtre ou à l'onglet demandé ; elle ne doit
  pas devenir une capture générale de l'écran.
- Un lien est fourni tel quel, sans scraper l'historique du navigateur.
- L'absence de preuve est écrite comme `unclear`, jamais transformée en fait.

## 3. Message à envoyer à ChatGPT

Le message suivant est le modèle de départ. Les valeurs entre crochets sont
remplacées par le paquet de contexte courant.

```text
Tu es le modèle de planification pour cette boucle de travail.

Je suis Codex, l'interface et l'opérateur local. Je peux lire ou exécuter les
éléments explicitement autorisés dans le paquet de contexte, puis te renvoyer
un rapport vérifié. Tu n'as pas accès au disque, aux applications ou aux
fichiers qui ne sont pas listés ici.

Analyse l'objectif et choisis le chemin le plus fiable. Ne prétends jamais
avoir lu un fichier ou exécuté une commande si le rapport ne le prouve pas.
Si une information manque, demande-la précisément : type, chemin relatif ou
cible, raison et niveau de nécessité. Tu peux demander d'autres informations
à Codex ; Codex te dira ensuite ce qui est disponible et ce qui peut être
transmis.

Règles :
- une seule action locale bornée par itération ;
- chemins relatifs au workspace uniquement ;
- aucune donnée privée ou secrète demandée par défaut ;
- aucun envoi de fichier, capture ou lien sans proposition et autorisation ;
- aucune commande destructive ou publication sans approbation explicite ;
- adapte la prochaine étape uniquement au rapport vérifié.

Paquet de contexte :
[PAQUET_DE_CONTEXTE]

Réponds avec exactement un bloc `cortex-decision` conforme à `cortex.v1`.
Utilise `REQUEST_CONTEXT` si tu as besoin d'une information en lecture seule,
`EXECUTE` pour une action locale autorisée, `COMPLETE` seulement avec des
preuves suffisantes, et `BLOCKED` si aucune voie sûre ne reste possible.
```

## 4. Boucle d'échange

1. Codex lit ce fichier et construit le paquet de contexte.
2. Codex envoie le message à la conversation ChatGPT cible.
3. Codex lit exactement une décision `cortex-decision`.
4. Cortex valide l'identité de mission, l'itération, l'outil et les chemins.
5. Pour `REQUEST_CONTEXT`, Cortex réalise uniquement l'action de lecture
   autorisée et construit un rapport.
6. Pour `EXECUTE`, Cortex applique la politique d'approbation, exécute une
   seule action et valide son résultat.
7. Codex renvoie le bloc `cortex-report` dans la même conversation.
8. La boucle continue jusqu'à `COMPLETE`, `BLOCKED`, une limite de budget ou
   une approbation manquante.

Le protocole `cortex.v1` déjà présent dans le dépôt porte les décisions et les
rapports. `REQUEST_CONTEXT` est actuellement limité aux outils de lecture
seule. La transmission réelle de fichiers, de captures et de liens vers une
conversation ChatGPT de l'application desktop nécessite une capacité de
pièce jointe exposée par cette application ; elle ne doit pas être simulée par
un simple texte disant que le fichier a été envoyé.

### 4.1 Demande de contexte dans une conversation

Pour demander un élément précis à Codex, ChatGPT peut ajouter un unique bloc
`cortex-context-request` dans sa réponse :

````text
```cortex-context-request
{"protocol":"cortex-context-request.v1","requestId":"ctx-123","summary":"Vérifier le résultat","items":[{"id":"file-1","kind":"file","reason":"Lire le rapport","path":"reports/result.txt"}]}
```
````

Les types acceptés sont `file`, `screenshot` et `link`. Un fichier doit être
relatif au workspace, un lien doit être `http` ou `https`, et une capture doit
cibler `current_chatgpt` ou `current_conversation`. Cortex affiche alors une
carte d'autorisation ; chaque bouton déclenche une approbation séparée via
`POST /api/chat/approve-context`. La simple présence du bloc ne déclenche
aucun envoi. Un bloc mal formé, dupliqué ou dangereux reste du texte visible
et n'est pas interprété.

## 5. Niveaux d'automatisation

| Niveau | Autorisé sans nouvelle question | Approbation requise |
| --- | --- | --- |
| Lecture | statut, tests, diff, métadonnées non sensibles du workspace | aucun accès hors workspace |
| Contexte | fichier, capture, lien explicitement identifié | oui, élément par élément |
| Exécution | lecture seule et tests bornés | écriture selon la politique du dépôt |
| Risque élevé | rien par défaut | suppression, secrets, publication, message externe, commande destructive |

Le fait que ChatGPT demande un élément ne constitue jamais une autorisation
de le transmettre. Codex vérifie la demande, le périmètre et la confidentialité
avant de proposer l'élément.

## 6. Contrat de rapport vers ChatGPT

Chaque rapport doit distinguer :

- ce qui a été demandé ;
- ce qui a été réellement exécuté ;
- la commande ou l'outil utilisé ;
- le résultat et le code de sortie ;
- les fichiers effectivement modifiés ;
- les validations passées ou échouées ;
- les éléments encore inconnus ;
- la prochaine action sûre.

Un rapport ne doit jamais contenir de secret, de token, de mot de passe, de
contenu privé sans nécessité ou de chemin personnel absolu.

## 7. État d'implémentation dans Cortex Bridge 0.6.1

Déjà disponible :

- boucle mission `cortex.v1` et rapports idempotents ;
- état `REQUEST_CONTEXT` avec outils en lecture seule ;
- contrôle des chemins relatifs et de la politique d'exécution ;
- séparation entre décision ChatGPT, action locale et preuve.
- constructeur `desktop-supervisor.v1` avec redaction, bornes, déduplication
  et validation des éléments ;
- formatters purs `render_supervisor_prompt` et `render_supervisor_report` :
  le premier rappelle la limite de pièce jointe desktop, le second sépare
  actions exécutées, preuves, inconnues et prochaine action sûre ;
- injection optionnelle du paquet validé dans le contrat d'une mission, sans
  persistance du transcript brut.
- parseur UI `cortex-context-request.v1` et carte d'approbation par élément ;
- endpoint d'approbation reconfinant les fichiers au workspace et bornant les
  liens/captures avant d'appeler le transport ChatGPT existant.

À implémenter pour le mode desktop complet :

- sélection et persistance d'un identifiant de conversation ChatGPT de
  l'application Codex ;
- capture contrôlée du paquet de contexte depuis la conversation Codex ;
- canal de pièce jointe réellement supporté par l'application desktop ;
- reprise après réponse périmée, conversation fermée ou transport indisponible ;
- tests de confidentialité prouvant qu'aucun fichier hors périmètre n'est
  transmis.

Ce fichier est une spécification opératoire. Il ne transforme pas à lui seul
une capacité non exposée par l'application desktop en capacité disponible.
