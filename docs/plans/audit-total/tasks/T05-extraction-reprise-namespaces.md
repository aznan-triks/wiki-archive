# T05 — Extraction : espace de noms, reprise réelle et résilience réseau

- **Priorité** : P1 · **Axe** : D · **Constats couverts** : D05, D44, D45, D06,
  D39, D40
- **Justification** : trois défauts distincts font qu'une archive peut être
  partielle sans que rien ne le signale, et qu'un incident réseau fait perdre
  20 minutes de travail.

## Preuve et conséquence

- **D05** : `scripts/extract.py:33` fige `KEEP_NS = {"0"}` ; l'option
  « Namespaces » est transmise au dump (`run.py:231-238`) mais jamais à
  l'extraction. `NAMESPACES=0,14` → seules les pages de l'espace 0 sont
  extraites ; `NAMESPACES=10` seul → 0 page et échec « wrong namespaces? ».
- **D44** : `run.py:273-277` saute **toute** l'extraction dès qu'un fichier HTML
  existe (`elif html_count > 0`). Reproduit : 2 HTML sur 8 →
  `↩ Step already complete -- skipped (2 HTML files already present)` puis, faute
  de `categories.json`, échec avec le conseil « delete the 'html' folder ».
  Si `categories.json` existe (sauvegardé tous les 50 articles), le run continue
  et produit une archive de 2 pages sur 8, marquée `done`.
- **D45** : le conseil donné renvoie à une action inexistante côté UI (le
  « Re-render » est masqué sauf PDF, cf. A09) ; la seule alternative visible est
  « New full dump » (re-téléchargement complet).
- **D06** : `build_categories.py:59-76` ne réessaie jamais. Reproduit : 3
  catégories en timeout sur 4 → `sys.exit(1)` après 20 s, tout le scan perdu.
- **D39/D40** : le dump est considéré complet dès qu'un `.xml` existe
  (`run.py:204-207`) ; et la validité de la reprise dépend d'une nouvelle
  détection d'URL (`run.py:242-250`), qui peut différer et provoquer la
  suppression du dossier `dump/`.

## État actuel → état cible

- `KEEP_NS` dérivé de `NAMESPACES` (défaut `{"0"}`), cohérent avec le dump.
- L'étape 2 est **toujours** appelée (elle sait reprendre page à page) ou sautée
  seulement si `nb_html == nb_pages(XML)`.
- Un marqueur de fin de dump (`dump/.complete` écrit par le stub/`wikiteam3`, ou
  vérification `config.json`) conditionne le skip de l'étape 1 ; la comparaison
  d'URL porte sur l'hôte + le chemin de base, jamais sur `--api`/`--index`.
- Les récupérations d'API (catégories, pages) réessaient 3 fois avec backoff
  (1 s, 2 s, 4 s) et ne font échouer l'étape qu'après épuisement, en listant les
  éléments en échec.
- L'UI propose une action « Re-extraire (conserve le dump) » visible quel que
  soit le format.

## Cause racine et sites concernés

Trois causes communes : (1) les options de l'interface ne descendent pas jusqu'au
script concerné (`NAMESPACES` → `extract.py`) ; (2) la reprise est raisonnée au
niveau du dossier (« au moins un fichier ») au lieu de l'unité de travail (la
page) ; (3) aucun mécanisme de réessai partagé entre `detect_wiki.py`,
`extract.py` et `build_categories.py`.

## Référence à réutiliser

`extract.py:234-253` contient déjà la reprise page à page (`if outfile.exists()`)
et `extract.py:238-242` la récupération de catégories manquantes avec respect du
`DELAY` : c'est le comportement à généraliser, pas à réécrire.
`wikiteam3` reçoit déjà `--resume` (`run.py:246-248`).

## Plan d'action

1. `extract.py` : lire `NAMESPACES` (`os.getenv("NAMESPACES","0")`), en faire un
   `set` et remplacer `KEEP_NS` ; journaliser les espaces conservés.
2. `run.py` : remplacer le test `html_count > 0` par une comparaison
   `html_count >= page_count(xml_file)` (compter les `<page>` de l'XML, déjà
   parcouru en flux) ; si l'appel est nécessaire, l'exécuter (il est idempotent).
3. `run.py` : écrire/lire `dump/.complete` (le stub de test et un `post-hook`
   après `wikiteam3`) ; ne skipper l'étape 1 que si ce marqueur existe.
4. `run.py:242-250` : comparer `urlparse(saved).netloc + path` au lieu de la
   chaîne complète ; archiver l'ancien dump (`dump.bak/`) au lieu de le
   supprimer.
5. `build_categories.py` + `extract.py` : petite fonction `fetch_json(url, params,
   retries=3)` dans un module partagé (`scripts/net.py`) avec backoff ; l'utiliser
   dans les deux scripts (et dans `detect_wiki.py` pour la sonde).
6. UI : ajouter « Re-extraire (conserve le dump) » dans la carte Actions
   (déclenche `POST /api/jobs/{id}/generate`? non : un nouveau
   `POST /api/jobs/{id}/reextract` qui met `rerender=true` et lance `phase=all`).
   À défaut, exposer la case `rerender` hors du bloc PDF (A09, T16).
7. Dé-marquer `test_partial_extraction_is_completed` (T01).

## Points d'impact

`scripts/extract.py`, `scripts/run.py`, `scripts/build_categories.py`,
`scripts/detect_wiki.py`, éventuellement `scripts/net.py` (nouveau),
`server.py` (route + bouton), `tests/test_extract_fallback.py`,
`tests/test_build_categories.py`, `tests/test_run_pipeline.py`.

## Régression

Aucune : (a) `NAMESPACES` par défaut `0` → comportement identique ; (b) appeler
`extract.py` quand tout existe est un parcours d'XML sans écriture (vérifié :
`outfile.exists()` → compteur `resumed`) ; (c) les réessais ne changent que les
cas d'échec transitoire ; (d) le skip du dump reste possible via le marqueur.
Point d'attention : `test_build_categories.py::test_api_error_aborts_the_scan`
devra vérifier l'abandon **après** les tentatives (le test sera plus lent :
utiliser `retries=1` via env).

## Actions humaines requises

Aucune.

## Dépendances

T01 (tests) avant. T07 (écritures atomiques) conseillé avant le point 5 (le
marqueur `.complete` doit être écrit atomiquement).

## Non-objectifs

- Ne pas implémenter un système de file d'attente/retry générique côté serveur.
- Ne pas rendre la reprise dépendante d'une base de données.

## Critères d'acceptation

1. `NAMESPACES=0,14` → les pages de l'espace 14 sont extraites ; `0` inchangé.
2. 2 HTML sur 8 → le run extrait les 6 manquantes (`6 new + 2 resumed`) et
   produit une archive de 8 pages.
3. Une catégorie qui échoue deux fois puis réussit → scan réussi, log des
   tentatives ; un échec définitif → code 1 **après** 3 tentatives.
4. Un dump sans marqueur `.complete` est repris (log « reprise du dump »), jamais
   supprimé.
5. Test de T01 vert.

## Vérification et repli

Rejouer les scénarios du faux wiki (extraction partielle, panne temporaire de
l'API de catégories simulée par un compteur). Repli : `git revert` par étape
(les 6 points sont indépendants).
