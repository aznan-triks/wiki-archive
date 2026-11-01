# T14 — Actions destructrices, double lancement et retours d'état

- **Priorité** : P1 (A06, A08) + P2 (A07, A09, C07, D45, B12) + P3 (A04) · **Axe** : A/C
- **Justification** : l'interface permet de lancer deux pipelines concurrents sur
  le même job, de supprimer des données sans confirmation réelle, et affiche des
  messages qui décrivent autre chose que ce qui vient de se passer.

## Preuve et conséquence

- **A08 (P1, reproduit)** : « ▶ Generate selection » reste actif pendant qu'un
  run tourne. (a) pendant un `scan` : `POST /generate` → `{"ok":true}` immédiat,
  **aucun** second processus, le job termine `scanned` sans sortie, et
  l'interface affiche « Generation started… » ; (b) pendant une **pause** : le
  même appel démarre un second `run.py` qui exécute l'étape 5 jusqu'au bout et
  passe le job à `done` alors que le processus suspendu existe encore (→ D47).
- **A06 (P1)** : supprimer un job, purger, et « New full dump » (qui supprime le
  dossier `dump/`, `run.py:242-250`) s'exécutent sans confirmation ; seule une
  suppression groupée affiche un toast d'annulation de 5 s (A07), qui **précède**
  l'action au lieu de la suivre et ne fonctionne pas après rechargement.
- **C07 (P2)** : trois canaux pour une même nature d'erreur — toast
  (`showToast`), bandeau (`buildBanner`), ligne de log — sans règle : une erreur
  d'API apparaît dans les trois ou dans aucun selon la route.
- **D45 (P2)** : le message de `run.py:276-277` conseille « delete the 'html'
  folder … and re-run extraction », alors que l'action UI correspondante
  (« Re-render output ») est masquée quand PDF n'est pas coché (A09).
- **B12 (P3)** : les lignes de la carte Files ont l'apparence de boutons
  (`cursor:pointer`, survol) mais ne font rien (`buildFiles`,
  `server.py:1563-1590`) — alors que I01 montre qu'aucun moyen d'ouvrir un
  fichier n'existe.
- **A04 (P3/P2)** : après `SCAN COMPLETE`, la barre de progression reste sur
  l'étape 4 (`Categories`) : le log affiche `✓ SCAN COMPLETE` (l.100) mais
  `PIPELINE COMPLETE` n'est jamais atteint en mode `scan` ; le client
  (`updateProgress`) ne reconnaît que la seconde chaîne.

## État actuel → état cible

- Une seule action destructive possible à la fois par job ; les boutons qui
  dépendent de l'état (`Generate`, `Pause`, `Delete`, `Purge`) sont désactivés
  (avec `title` explicatif) quand l'état ne le permet pas — et le serveur refuse
  aussi (409), pas seulement l'UI.
- Toute action destructive passe par une confirmation **récapitulative**
  (volume, nombre d'objets) ; l'annulation est un vrai `undo` (toast persistant
  10 s) ou n'existe pas.
- Un seul canal par nature : toast pour les actions ponctuelles, bandeau pour
  l'état du job, log pour le pipeline. Les erreurs d'API vont au bandeau **et**
  au toast (jamais silencieuses).
- `SCAN COMPLETE` met à jour la progression (étape 4 terminée, étape 5 « non
  demandée ») ; le libellé dépend du `PHASE`.
- Les lignes de fichier sont soit des liens (ouvrir/télécharger, cf. I01), soit
  des lignes neutres — pas des faux boutons.

## Cause racine et sites concernés

L'UI dérive son état du polling (`renderJob`, `updateProgress`) et non d'un
modèle d'actions ; les handlers serveur n'ont pas de garde d'état (un `generate`
pendant un `running` est accepté). Les retours sont dispersés (3 canaux, 2
formatages).
Sites : `server.py:1505-1520` (`buildBanner`, `buildActions`), `:1563-1590`
(`buildFiles`), `:1780-1814` (`updateGenInfo`, aperçu), `:1830-1905`
(`updateProgress`, `queueLog`), handlers `generate`/`pause`/`resume`/`stop`/
`purge`/`delete`, `run.py:100`, `:242-250`, `:276-277`.

## Référence à réutiliser

- `Job.is_running()` et `STEPS` (`server.py:109-117`) donnent déjà l'état
  nécessaire aux gardes.
- `showToast` existe (avec annulation) : à conserver, en corrigeant la sémantique.
- `merge_report.json` contient déjà les volumes nécessaires aux confirmations.

## Plan d'action

1. Serveur : garde d'état explicite dans `generate`, `scan`, `resume`
   (`if job.is_running(): 409 {"error":"job is running"}`) ; `delete`/`purge`
   passent par T07 (arrêt puis suppression).
2. Serveur : `GET /api/jobs/{id}` (T08) inclut `can: {generate, pause, resume,
   stop, purge, delete}` ; l'UI **désactive** en conséquence (source unique).
3. UI : confirmation récapitulative (`showConfirm({title, body, danger})`) pour
   `delete`, `bulk_delete`, `purge`, `New full dump` ; volume lu depuis
   `GET /disk`.
4. UI : corriger le toast d'annulation (A07) — soit un `undo` réel sur 10 s avec
   appel différé, soit suppression du bouton (KISS : le retirer).
5. UI : un seul canal par nature — `notifyError` (bandeau + toast), `notifyInfo`
   (toast), log = pipeline seulement ; documenter la règle en tête du bloc JS.
6. `updateProgress` : accepter `SCAN COMPLETE` (fin d'étape 4, étape 5 «
   ignorée ») et `PIPELINE COMPLETE`.
7. `buildFiles` : transformer chaque ligne en `<a href="/api/jobs/{id}/files/
   {name}" download>` **si** I01 est livré ; sinon neutraliser le style (pas de
   `cursor:pointer`). Décision : livrer I01 (route de téléchargement, 15 lignes,
   lecture seule confinée au dossier du job) — recommandé.
8. `run.py:276-277` : message corrigé (« relancez la génération ») une fois le
   bouton visible hors PDF (A09/T16).

## Points d'impact

`server.py` (handlers + JS `buildActions`, `buildFiles`, `updateProgress`,
`showToast`), `scripts/run.py` (message), `tests/` (nouveau test des gardes
d'état : `generate` sur job `running` → 409).

## Régression

Aucune fonctionnelle : les actions restent disponibles dans les mêmes états
valides. Régression **assumée** : un utilisateur qui relançait « Generate »
pendant un run pour « tout reprendre » devra désormais arrêter puis relancer —
c'est le comportement sûr (le précédent produisait deux writers sur le même
dossier, cf. D02). Livrer I01 ajoute une route de lecture : confinée par
`Path(name).name` et vérification d'appartenance au dossier du job (pas de
traversée).

## Actions humaines requises

Décision : livrer le téléchargement de fichiers (I01) maintenant, ou neutraliser
le style des lignes. Recommandation : livrer (débloque le parcours « récupérer
mon PDF », aujourd'hui impossible sans accès au disque).

## Dépendances

T07 (gardes d'état cohérentes), T08 (`can`), T03 (chemins), T11 (aperçu).

## Non-objectifs

- Pas de journal d'audit des actions.
- Pas de confirmation en deux étapes pour chaque suppression (une seule
  confirmation récapitulative suffit).

## Critères d'acceptation

1. « Generate » désactivé pendant un run ; appel direct → 409.
2. Suppression d'un job → dialogue récapitulatif avec le volume ; annulation
   possible avant exécution.
3. `SCAN COMPLETE` → barre à 4/5 avec « étape 5 : non demandée ».
4. Une erreur d'API produit exactement un bandeau + un toast, jamais trois
   canaux divergents.
5. Si I01 livré : clic sur un fichier → téléchargement ; nom hors dossier → 404.

## Vérification et repli

Rejouer A08 (double génération), A07 (toast), A04 (scan) sur le faux wiki.
Repli : `git revert` par point.
