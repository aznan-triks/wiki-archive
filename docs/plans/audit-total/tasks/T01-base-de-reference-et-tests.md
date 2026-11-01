# T01 — Base de référence et tests de caractérisation

- **Priorité** : P2 (prérequis de tous les autres plans)
- **Axe** : D (tests), transverse
- **Constats couverts** : D38
- **Justification** : la suite actuelle (28 tests, verts) ne couvre aucun des
  défauts P0/P1 de cet audit. Corriger sans filet rend toute régression invisible.

## Preuve et conséquence

`python -m pytest -q` → 28 passés (7 fichiers ; inventaire en annexe du rapport).
Aucun test ne couvre : le mode texte sans API (D01), la sortie partagée entre
jobs (D02), les collisions de `page_stem` (D03), la parité aperçu/résultat (D07),
la sélection et `ADD_DIVERS` (C14), les paramètres invalides (D08), le cycle de
vie du serveur (D14-D19). Trois pertes de données reproductibles coexistent avec
une suite verte : la suite protège le passé, pas le présent.

## État actuel → état cible

- Actuel : 28 tests unitaires par sous-processus, entrées fabriquées à la main,
  aucun serveur de wiki simulé (le seul test d'intégration force
  `PHASE=generate` avec un HTML écrit dans le test).
- Cible : 35+ tests dont 7 tests de caractérisation (un par défaut P0/P1), un
  harnais réutilisable, exécution < 15 s, aucun accès réseau sortant.

## Cause racine et sites concernés

Le harnais manque : `tests/conftest.py` n'insère que `scripts/` dans `sys.path`.
Un faux wiki MediaWiki local (≈ 120 lignes de `ThreadingHTTPServer`) et un *stub*
`wikiteam3dumpgenerator` sur le `PATH` suffisent — ils ont permis de reproduire
D01, D03 et D44 pendant cet audit.

## Référence (à réutiliser)

- `tests/conftest.py` (insertion de `sys.path`)
- `tests/test_run_pipeline.py::_env()` (environnement isolé par test)
- `tests/test_extract_fallback.py` (motif « faux serveur API local » à généraliser)
- Alternative écartée : `pytest-httpserver` (dépendance nouvelle pour 120 lignes).

## Plan d'action

1. `tests/fakewiki.py` : `ThreadingHTTPServer` répondant à
   `action=query&meta=siteinfo`, `action=query&list=categorymembers`,
   `action=parse` et `/dump.xml` ; contenu piloté par `PAGES`/`CATS` passés au
   constructeur ; port éphémère (`port=0`), arrêt en fixture.
2. `tests/conftest.py` : fixtures `fakewiki` (URL de base) et `stub_wikiteam`
   (écrit un exécutable `wikiteam3dumpgenerator` dans `tmp_path/bin` qui copie
   `/dump.xml`, et préfixe le `PATH` de l'environnement du test).
3. Sept tests de caractérisation, marqués `xfail(strict=True)` **tant que le
   correctif n'est pas livré**, dé-marqués par le plan correspondant :
   `test_text_mode_writes_one_file_per_category` (D01) ·
   `test_two_jobs_same_wiki_do_not_share_output` (D02) ·
   `test_colliding_page_titles_both_extracted` (D03) ·
   `test_preview_matches_generated_file_count` (D07) ·
   `test_selection_drops_uncategorized_only_with_notice` (C14) ·
   `test_invalid_params_rejected_with_400` (D08) ·
   `test_partial_extraction_is_completed` (D44).
4. Documenter dans `tests/README` (ou docstring de `conftest.py`) comment lancer
   un seul test et pourquoi `xfail(strict=True)`.

## Points d'impact

`tests/` uniquement. `requirements-dev.txt` inchangé (stdlib seulement).

## Régression

Aucune : ajout de fichiers. Les 28 tests existants doivent rester verts
(critère d'acceptation explicite).

## Actions humaines requises

Aucune.

## Dépendances

Aucune. **À exécuter avant tous les autres plans.**

## Non-objectifs

- Ne pas réécrire les tests existants ni viser un pourcentage de couverture.
- Ne pas simuler `requests` quand un vrai serveur local suffit.

## Critères d'acceptation

1. `python -m pytest -q` → 35+ tests, les 28 précédents toujours verts.
2. Les 7 tests de caractérisation échouent sur le code actuel (prouvant le
   défaut) et passent après T02, T03, T04, T05, T08, T11.
3. Durée < 15 s, aucun accès réseau sortant.

## Vérification et repli

`git revert` du commit `tests/` en cas de problème. Aucun risque de données.
