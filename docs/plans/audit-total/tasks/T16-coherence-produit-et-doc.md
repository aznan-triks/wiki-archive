# T16 — Cohérence produit : plans, valeurs par défaut, vocabulaire et docs

- **Priorité** : P2 (C01, C02, C04, C05, A03, A05, B08, B09) + P3/P4 (C03, C09,
  A18, G15, A09) · **Axe** : C/A/B/G
- **Justification** : le produit et sa documentation ne disent pas la même chose
  sur le nombre de fichiers, la déduplication, le vocabulaire et les boutons. Ces
  écarts ne cassent rien, mais ils font prendre de mauvaises décisions
  d'archivage (choisir « Plus » pour 300 fichiers qui n'existeront jamais).

## Preuve et conséquence

- **C02 (P2)** : `NOTEBOOKLM_PLANS` (`server.py:76`) = free 50 / plus 100 / pro
  300 / ultra 600 ; `DEFAULTS.max_files = 50` avec
  `notebooklm_plan = "plus"` (`server.py:58-75`) : le plan sélectionné par défaut
  autorise 100 sources, la valeur appliquée est 50. Aucune indication de la
  relation entre les deux champs.
- **C03 (P3)** : `PLAN.md` indique « Plus = 300 », l'interface 100 (vérifié) :
  deux sources de vérité pour la même constante externe.
- **C01 (P2)** : « Max words per file » n'existe pas au niveau du job
  (`NOTEBOOKLM_MAX_WORDS` est global, `run.py:143`) alors que « Max files » est
  par job : deux réglages de même nature, deux portées.
- **C05 (P2)** : la déduplication est active (`DEDUP` défaut `true` côté
  serveur) et **réécrit la sortie** : mesuré `Deduplication: 8 -> 6` sur un
  wiki de 8 pages / 6 catégories, alors que le README promet « a page appears in
  every file of its categories ». Les deux ne peuvent pas être vrais.
- **C04 (P2)** : le vocabulaire diverge — README « dump/pipeline/job », UI
  « Archive/Run/Task », logs « job » ; **A03** : trois modèles mentaux
  concurrents pour le même parcours (URL → job → run) ; **A05** : deux jobs sur
  le même wiki sont indiscernables dans la liste (aucun horodatage visible, même
  nom).
- **B08/B09 (P2)** : dans les `.md` générés, le titre de l'article est dupliqué
  (titre de section + titre H1 de la page) ; le pied « Categories: A | B » du
  wiki est conservé, ce qui ajoute du bruit à chaque article pour NotebookLM
  (source d'ancrage inutile).
- **A18 (P3)** : le README documente des boutons qui n'existent pas
  (« Export », « Download ») ; **G15 (P4)** : `PLAN.md` décrit comme « à faire »
  un travail déjà livré.
- **A09 (P2)** : « Re-render output » est masqué sauf si PDF est coché, alors que
  l'action concerne tous les formats.

## État actuel → état cible

- Une seule table de plans (une constante), lue par l'UI **et** la documentation
  (le README cite la constante, pas une valeur recopiée).
- Choisir un plan **propose** `max_files` (avec possibilité de le modifier) et
  l'UI montre la relation (« Plan Plus : 100 sources — 50 utilisées »).
- `notebooklm_max_words` devient un réglage par job comme `max_files`.
- La déduplication est **désactivée par défaut** (chaque page apparaît dans
  chaque fichier de ses catégories, conformément au README) et, si activée,
  affichée comme une option explicite avec son effet mesuré (« -2 pages
  dupliquées »).
- Vocabulaire unique : « job » partout (UI, README, logs) ; « run » réservé à une
  exécution d'un job.
- Dans les `.md` : un seul titre par article (supprimer le H1 dupliqué) et pas de
  pied « Categories: » (ou en commentaire HTML).
- README et `PLAN.md` alignés sur l'interface réelle.

## Cause racine et sites concernés

Trois sources de vérité qui ne se parlent pas : constantes du serveur
(`DEFAULTS`, `NOTEBOOKLM_PLANS`), documentation (README, `PLAN.md`), et
comportement des scripts (`DEDUP` appliqué dans `run.py`). Aucune n'est générée
depuis les autres, et aucun test ne vérifie la cohérence.
Sites : `server.py:58-76`, `:1259-1300` (formulaire), `:1336-1400`
(`buildForm`), `run.py:143`, `:390-399` (`DEDUP`), `export_categories.py`
(footers/titres), `README.md`, `PLAN.md`.

## Référence à réutiliser

- `NOTEBOOKLM_PLANS` et `DEFAULTS` sont déjà exposés par `GET /api/settings` :
  l'UI peut s'y brancher au lieu de recopier les nombres.
- `clean_html.py` retire déjà des éléments du HTML : le pied « Categories: » peut
  y être traité (une ligne de plus), avec un test.
- `tests/test_server_config.py` vérifie déjà `DEFAULTS`/`NOTEBOOKLM_PLANS` : y
  ajouter l'assertion de cohérence `DEFAULTS.max_files ==
  NOTEBOOKLM_PLANS[DEFAULTS.notebooklm_plan]`.

## Plan d'action

1. `server.py` : `DEFAULTS["max_files"] = NOTEBOOKLM_PLANS["plus"]` (100) ou
   `DEFAULTS["notebooklm_plan"] = "free"` — **décision humaine** (voir plus bas) ;
   rendre le choix du plan dans l'UI piloté par la constante exposée.
2. `buildForm` : sur changement de plan, proposer `max_files` (champ modifiable,
   mention « valeur conseillée par le plan »).
3. `run.py` : `notebooklm_max_words` lu par job (`job.json` → `NOTEBOOKLM_MAX_WORDS`
   d'environnement) ; ajouter le champ correspondant au formulaire (C01).
4. `DEDUP` : défaut `false` ; si `true`, journaliser `Deduplication: N -> M` et
   l'afficher dans l'aperçu (aujourd'hui seul le log le dit).
5. `clean_html.py` : supprimer le pied `Categories:` et le H1 dupliqué quand il
   répète le titre (comparaison normalisée) ; tests dans
   `tests/test_export_categories.py`/`test_merge_pdf.py`.
6. Vocabulaire : remplacer « Archive/Run/Task » par « Job » dans le HTML
   (`buildBanner`, `buildActions`) ; lister les libellés dans une constante
   `LABELS` pour éviter la re-divergence.
7. README : corriger la liste des boutons (A18), citer `NOTEBOOKLM_PLANS` au lieu
   de recopier les nombres ; `PLAN.md` : marquer livré/dépassé (G15), ou le
   déplacer dans `docs/archive/`.
8. `A09` : afficher « Re-render output » quel que soit le format coché.
9. Test de cohérence : `DEFAULTS.max_files == NOTEBOOKLM_PLANS[DEFAULTS.notebooklm_plan]`
   et présence des libellés `LABELS` dans le HTML servi.

## Points d'impact

`server.py` (constantes, formulaire, bannière, actions), `scripts/run.py`,
`scripts/clean_html.py`, `README.md`, `PLAN.md`, `tests/test_server_config.py`,
`tests/test_export_categories.py`.

## Régression

- **`max_files` par défaut passe de 50 à 100** (ou le plan par défaut passe à
  `free`) : **régression assumée** pour les utilisateurs qui comptaient sur 50
  par défaut — mais les deux valeurs se contredisaient, et une sortie de 100
  fichiers reste sous la limite du plan affiché. Documenter dans le CHANGELOG.
- **`DEDUP` par défaut à `false`** : plus de pages dans certains fichiers (jusqu'à
  +33 % de volume mesuré sur le wiki de test : 6 → 8 fichiers équivalents) →
  **régression assumée**, avec justification : le README promet l'inclusion dans
  toutes les catégories, et la déduplication est le comportement qui surprend.
  Échappatoire : case « dédupliquer » visible dans les réglages.
- **Suppression du pied `Categories:`** : contenu produit modifié → régression
  assumée (bruit retiré), réversible par réglage `KEEP_CATEGORY_FOOTER=1`.

## Actions humaines requises

1. Choisir entre : `max_files` par défaut = 100 (plan « plus ») **ou** plan par
   défaut = « free » (50). Recommandation : `max_files` = valeur du plan
   (100) — l'utilisateur qui choisit « plus » doit obtenir ce que le plan promet.
2. Valider le passage de `DEDUP` à `false` par défaut (impact sur le volume et la
   durée des PDF).

## Dépendances

T01 (tests). T11 (aperçu) pour afficher l'effet de la déduplication.

## Non-objectifs

- Pas de refonte de la navigation (A03 est traité par le vocabulaire et la
  hiérarchie des cartes, pas par un nouvel écran).
- Pas de renommage des jobs (I08, P4) : hors périmètre de ce plan, mais A05 est
  atténué par l'affichage de la date de création et du nombre de pages.

## Critères d'acceptation

1. `GET /api/settings` renvoie `max_files` cohérent avec le plan sélectionné, et
   la documentation cite la constante (aucun nombre recopié).
2. Changer de plan dans l'UI met à jour `max_files` (modifiable ensuite).
3. `max_words` est réglable par job.
4. Sur le wiki de test, `DEDUP=false` → 8 pages réparties dans 6 fichiers (chaque
   page dans chacune de ses catégories) ; `DEDUP=true` → `Deduplication: N -> M`
   affiché dans l'aperçu.
5. Les `.md` générés ne contiennent plus de pied `Categories:` ni de titre
   dupliqué (test automatisé).
6. README : chaque bouton cité existe dans le HTML servi (test de `grep`).

## Vérification et repli

Rejouer `run2` sur le faux wiki et diffuser les `.md` avant/après ; `grep` des
libellés. Repli : `git revert` point par point ; les changements de défaut sont
réversibles par variable d'environnement.
