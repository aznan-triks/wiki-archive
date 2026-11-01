# Audit Fonctionnel, UX et Expérience Utilisateur — `wiki-archive`

**Date de l'audit :** 31 octobre 2026  
**Périmètre :** Ensemble du dépôt `wiki-archive` — Backend & UI Web (`server.py`), orchestrateur et scripts du pipeline (`scripts/*.py`), lanceurs (`run.bat`, `update.bat`, `Dockerfile`, `docker-compose.yml`), suite de tests (`tests/*.py`) et documentation (`README.md`, `PLAN.md`, `CHANGELOG.md`).

---

## 1. Compréhension du projet et méthodologie d'investigation

### 1.1 Objectif produit et promesse utilisateur
**Wiki Archive** est une application locale (Windows 10/11 en natif via `run.bat` ou multi-plateforme via Docker) permettant d'archiver l'intégralité d'un wiki **MediaWiki** et de produire des fichiers consolidés par catégorie (`.pdf`, `.md`, `.txt`), directement calibrés pour les limites d'ingestion de **Google NotebookLM** :
- plafond du nombre de sources par notebook (**50** en plan Free, **100** en Plus, **300** en Pro) ;
- plafond de **500 000 mots** et **500 pages PDF** par fichier source ;
- parcours en **2 étapes** :
  1. **Step 1 — Scan** : téléchargement du dump XML (`wikiteam3`), extraction et nettoyage HTML, construction de l'arbre de catégories et comptage des mots ;
  2. **Step 2 — Sélection & Génération** : exploration de l'arbre hiérarchique des catégories/sous-catégories avec aperçu temps réel du nombre de fichiers finaux (`pack_files.py`), puis génération des fichiers `.pdf`, `.md` ou `.txt` dans `data/output/<wiki-hostname>/`.

### 1.2 Méthodologie et niveaux de preuve
Chaque constat de cet audit est qualifié avec un niveau de preuve explicite :
- **Confirmé à l'exécution** : reproduit et vérifié par l'exécution directe :
  - de la suite de tests existante (`pytest` : 28/28 tests passants) ;
  - des scripts du pipeline (`scripts/run.py`, `detect_wiki.py`, `extract.py`, `build_categories.py`, `pack_files.py`, `clean_html.py`, `export_categories.py`, `merge_pdf.py`, `wiki_names.py`) sur des jeux de données représentatifs ;
  - des endpoints FastAPI (`server.py`) via `fastapi.testclient.TestClient` ;
  - de l'interface HTML/CSS/JS embarquée (`server._HTML`) via exécution DOM (`Node.js` + `jsdom`).
- **Déduit du code** : démontré par l'analyse statique croisée avec références exactes (`fichier:ligne`).
- **À vérifier** : points dépendant d'un environnement externe non présent dans le bac à sable (ex. rendu graphique natif GTK3 sous Windows 10/11).

---

## 2. Diagnostic global

### Ce qui est réussi
- **Architecture sobre et autonome** : application monopage sans chaîne de build front-end lourde, serveur FastAPI léger avec flux de logs SSE temps réel, persistance JSON atomique (`_atomic_write`), et gestion propre des arbres de sous-processus via `psutil` (`_suspend_tree`, `_resume_tree`, `_terminate_tree`).
- **Idée produit très pertinente** : le découpage en deux temps (*Scan* → *Sélection dans l'arbre avec aperçu du packing NotebookLM* → *Génération*) répond exactement au besoin d'un utilisateur qui veut exclure le bruit d'un wiki (changelogs, traductions, archives) et respecter le quota de sources de NotebookLM.

### Ce qui casse l'expérience aujourd'hui (Constats P0 / P1)
Malgré les correctifs récents documentés dans `CHANGELOG.md`, **plusieurs parcours nominaux échouent ou corrompent silencieusement les données produites** :

1. **Le parcours nominal par défaut (Scan → Generate en PDF) échoue à 100 % (`[P0] PLAN-UX-01`)** : l'étape 3 (`convert.py`) est sautée à la fois en phase `scan` **et** en phase `generate` (`scripts/run.py:298`). Un utilisateur qui suit les deux boutons principaux de l'interface (`🔍 Step 1 — Scan the wiki` puis `▶ Generate selection`) avec le format par défaut (`PDF`) obtient systématiquement `⚠ FAILURE: pipeline produced 0 output files`.
2. **Tous les articles ayant un espace ou un accent dans leur titre sont exclus de leur PDF de catégorie (`[P0] PLAN-UX-02`)** : `run.py::flatten()` (`scripts/run.py:75-97`) renomme les PDF en ASCII avec des underscores (`Assault_Rifle.pdf`, `Epee.pdf`), alors que `category_groups.json` utilise `wiki_names.page_stem()` (`"Assault Rifle"`, `"Épée"`). Dans `merge_pdf.py:49-53`, la jointure échoue sur 100 % des titres multi-mots ou accentués, les déversant tous dans `Misc.pdf` (ou les supprimant totalement en mode sélection).
3. **Décocher une seule sous-catégorie dans l'arbre supprime toutes les pages directes de ses catégories parentes (`[P0] PLAN-UX-03`)** : `recomputeAncestors` passe tous les ancêtres à l'état `1` (ou `0` s'il n'y a qu'un enfant), et `selectedCats()` ne retient que `nodeState === 2`. De plus, les pages sans catégorie (`Misc`) sont absentes de l'arbre et supprimées dès qu'on clique sur `▶ Generate selection`, et les cycles de catégories au sommet produisent `"No root category."`.
4. **Supprimer un job en erreur détruit les fichiers finaux du job réussi sur le même wiki (`[P0] PLAN-UX-04`)** : `JobManager.delete()` supprime inconditionnellement `data/output/<wiki_slug>/`, partagé entre tous les jobs d'un même domaine. Cliquer sur `🧹 Clean up stopped/errored` efface le travail terminé d'un autre job du même wiki.
5. **Le regroupement automatique (`pack_files.py`) fusionne des thèmes sans rapport (`Cities+Pistols`) et le mode sans API perd toutes les catégories (`[P1] PLAN-UX-05`)** : avec `dedup=True` (défaut), `dedup_groups()` vide les catégories mères de leurs pages, ce qui fait sauter l'étape 2 (`if parent not in packed: continue`) et déclenche des fusions globales arbitraires à l'étape 3. Dans `run.py:352`, `cat_groups.write_text` est indenté après `return 1` (code mort).
6. **La reprise (`Resume`) est cassée sur les étapes 1 et 2 et peut tout effacer (`[P1] PLAN-UX-06`)** : `run.py:276` saute l'extraction HTML dès qu'un seul fichier `.html` existe (`html_count > 0`), `run.py:205` saute `--resume` sur un dump XML partiel, et les flags `clean` / `rerender` restent actifs dans `job.params` (effaçant tout lors d'un `Resume`).
7. **L'interface perd ses boutons d'action après une erreur ou une purge (`[P1] PLAN-UX-07`) et ignore les réglages modifiés à l'étape 2 (`[P1] PLAN-UX-08`)**.

---

## 3.Causes communes et récurrences systémiques

Plutôt que des bugs isolés, l'audit met en évidence **trois causes racines communes** :

### Cause commune A — Transition inachevée du pipeline monolithique (`all`) vers le flux en 2 phases (`scan` → `generate`)
Le découpage récent en `scan` et `generate` (`PLAN.md` Workstream D) a été greffé sur un orchestrateur conçu pour s'exécuter d'un seul tenant :
- L'étape 3 (`convert.py`) a été désactivée pendant `scan` mais aussi pendant `generate` (`PLAN-UX-01`).
- `JobManager.resume()` relance toujours `phase="all"` et efface les logs du scan lors du passage à `generate` (`PLAN-UX-06`, `PLAN-UX-11`).
- Le formulaire de configuration (`#d-form`) et le panneau de génération (`#d-gen`) ne partagent pas leur cycle de sauvegarde (`PLAN-UX-08`).
- Le parseur de logs du front-end (`flushLogs`) ne connaît toujours que `"PIPELINE COMPLETE"` et ignore `"SCAN COMPLETE"` (`PLAN-UX-11`).

### Cause commune B — Ruptures de la source unique de vérité (SSOT) sur le nommage et la hiérarchie des catégories
- **Nommage des fichiers :** cohabitation entre `wiki_names.page_stem()` (Unicode + espaces), `run.py::flatten()` (ASCII + underscores) et `wiki_names.cat_stem()` (troncature aveugle à 80 caractères écrasant le suffixe `(part N)` de `pack_files.py`) (`PLAN-UX-02`).
- **Hiérarchie des catégories :** `build_categories.py` pré-calcule l'union descendante complète (`full_pages`) dans `category_groups.json`. Dès lors, ni la désélection partielle dans l'arbre UI (`PLAN-UX-03`), ni la fusion ascendante après déduplication dans `pack_files.py` (`PLAN-UX-05`) ne peuvent fonctionner correctement sans repartir des pages directes de `category_tree.json`.
- **Cycle de vie du dossier de sortie :** `data/output/<wiki_slug>/` est indexé par domaine alors que la suppression (`delete`) et l'affichage (`files`) sont gérés par job (`PLAN-UX-04`).

### Cause commune C — Mise à jour incrémentale du DOM (`updateDetail`) asymétrique
Pour éviter de recréer le DOM toutes les 2 secondes pendant le polling (`refresh()`), `updateDetail()` patche certains éléments, mais :
- ne gère que la transition `running → canGenerate(job)` et oublie les transitions `running → error/stopped` ainsi que `done → purged` (`PLAN-UX-07`) ;
- réécrit en revanche `#d-files` toutes les 2 secondes sans diff (`PLAN-UX-11`).

---

## 4. Synthèse de l'évaluation selon les axes fonctionnels et UX

| Axe d'audit | État constaté | Plans associés |
|---|---|---|
| **1. Parcours utilisateur de bout en bout** | Le parcours nominal `Scan → Generate` échoue en PDF (`0 output files`). En `Do everything at once`, les articles avec espaces/accents tombent dans `Misc.pdf`. | `PLAN-UX-01`, `PLAN-UX-02` |
| **2. États d'interface** | Écran vide d'actions après `running → error/stopped` ; panneau `#d-gen` maintenu visible après `Free up space` alors que les fichiers intermédiaires n'existent plus. | `PLAN-UX-07` |
| **3. Formulaires et saisies** | Contradiction `Plus — 100` vs `Max files: 50` par défaut ; `delay = 0` écrasé par `0.5` ; `scanFromForm` autorise 0 format ; `Reconfigure` non sauvegardé au `Generate`. | `PLAN-UX-08`, `PLAN-UX-12` |
| **4. Navigation et architecture de l'information** | Bouton `▶ Resume` annoncé dans les logs (`"You can restart it via Resume"`) mais absent de l'UI pour les jobs `stopped`/`error`. | `PLAN-UX-07` |
| **5. Retours système (Feedback)** | `#step-3` bloqué en `active` après `SCAN COMPLETE` ; étape `3. Conversion` marquée `done` alors qu'elle est sautée ; scroll forcé du terminal ; `Copy path` relatif inutilisable dans l'Explorateur Windows en mode natif. | `PLAN-UX-11` |
| **6. Cohérence et lisibilité** | `.opt-check` non cliquable sur le texte (contrairement à `.fmt-check`) ; barre `.bulk-bar` fantôme après fermeture de `Manage` ; `README.md` citant d'anciens boutons. | `PLAN-UX-12` |
| **7. Accessibilité et usage réel** | Cases à cocher de 14×14 px sans `<label>` ; absence de validation par `Entrée` sur `#f-url` ; aucune règle `@media` pour l'usage en demi-écran côte à côte avec NotebookLM. | `PLAN-UX-12` |
| **8. Cas limites et conditions dégradées** | Échec de `detect_wiki.py` sur les URLs avec accents (`%C3%89`), sous-pages (`/wiki/A/B`) ou sans `https://` ; `roots = []` sur les cycles de catégories ; reprise HTML/XML cassée ; écrasement inter-jobs de `data/output/<slug>`. | `PLAN-UX-03`, `PLAN-UX-04`, `PLAN-UX-06`, `PLAN-UX-10` |
| **9. Pertinence fonctionnelle et valeur utilisateur** | Décocher une sous-catégorie détruit les pages directes des parents ; `pack_files.py` fusionne `Cities+Pistols` ; doublon `# Title` et bruit `Categories:` dans tous les `.md` ; `NAMESPACES` ignoré par `extract.py`. | `PLAN-UX-03`, `PLAN-UX-05`, `PLAN-UX-09` |
| **10. Qualité et maintenabilité du code** | Code mort après `return 1` (`run.py:352-356`) ; fonctions mortes `loadPrefs`/`savePrefs` (`server.py:1054-1058`) ; `flatten()` redondant et destructeur face à `wiki_names.py`. | `PLAN-UX-02`, `PLAN-UX-05`, `PLAN-UX-12` |

---

## 5. Références et standards mobilisés

- **Heuristiques d'utilisabilité de Jakob Nielsen (Nielsen Norman Group)** :
  - *#1 Visibilité de l'état du système* (barre de progression `#d-steps`, aperçu des fichiers fusionnés `preview.groups`) ;
  - *#3 Contrôle et liberté de l'utilisateur* (reprise `Resume` réelle après `Stop`, préservation du scroll terminal, restauration de la sélection après `Undo`) ;
  - *#5 Prévention des erreurs* (protection des fichiers finaux lors de la suppression d'un autre job du même wiki, désactivation automatique des flags destructifs `clean`/`rerender` après usage, validation des formats avant `Scan`) ;
  - *#9 Aide à la reconnaissance, au diagnostic et à la récupération des erreurs* (maintien du formulaire et du bouton `Retry`/`Resume` après erreur, Fail Fast dans `convert.py`).
- **W3C WAI-ARIA Authoring Practices Guide (APG) — Treeview & Tri-State Checkboxes** :
  - Distinction entre la sélection d'un nœud parent possédant son propre contenu (`direct_pages`) et l'état d'agrégation de ses nœuds enfants (`nodeState = 1` / `indeterminate`).
- **Loi de Fitts & Loi de Jakob** :
  - Association systématique `<label>` ↔ `<input type="checkbox">` pour offrir une zone de clic sur toute la largeur du libellé et soumission du champ principal (`#f-url`) via la touche `Entrée`.

---

## 6. Liste priorisée des plans d'action et ordre d'exécution recommandé

Chaque plan est documenté dans un fichier autonome sous `docs/plans/ux/` et dimensionné pour être exécuté **en une seule session** par un agent d'implémentation.

### Tableau récapitulatif des plans

| Priorité | ID | Titre | Fichier du plan | Fichiers du projet impactés | Dépendances |
|---|---|---|---|---|---|
| **P0** | `PLAN-UX-01` | Conversion PDF ignorée dans le parcours en 2 étapes (Scan → Generate) et après purge du cache PDF | `docs/plans/ux/01-p0-pdf-conversion-in-generate-phase.md` | `scripts/run.py`, `scripts/convert.py`, `tests/test_run_pipeline.py` | Aucune (Exécuter en #1) |
| **P0** | `PLAN-UX-02` | Perte des articles à espaces ou accents dans les PDF (`flatten`) et écrasement des catégories tronquées (`cat_stem`) | `docs/plans/ux/02-p0-pdf-stem-mismatch-and-filename-collisions.md` | `scripts/run.py`, `scripts/wiki_names.py`, `scripts/merge_pdf.py`, `scripts/export_categories.py`, `tests/*` | Après `PLAN-UX-01` |
| **P0** | `PLAN-UX-03` | Sélection partielle dans l'arbre de catégories supprimant les pages directes des catégories parentes et occultant les cycles / `Misc` | `docs/plans/ux/03-p0-category-tree-selection-and-propagation.md` | `scripts/build_categories.py`, `scripts/pack_files.py`, `scripts/run.py`, `server.py`, `tests/test_build_categories.py` | Après `PLAN-UX-02` |
| **P0** | `PLAN-UX-04` | Destruction des fichiers générés d'un autre job partageant le même wiki et écrasement destructif avant génération | `docs/plans/ux/04-p0-shared-output-dir-data-loss.md` | `server.py`, `scripts/run.py`, `tests/test_server_config.py`, `tests/test_run_pipeline.py` | Après `PLAN-UX-01`, `PLAN-UX-02` |
| **P1** | `PLAN-UX-05` | Algorithme de regroupement (`pack_files.py`) fusionnant des thèmes sans rapport (`Cities+Pistols`) et ignorant le mode sans API dans `run.py` | `docs/plans/ux/05-p1-packing-algorithm-and-no-api-categories.md` | `scripts/pack_files.py`, `scripts/run.py`, `tests/*` | Après `PLAN-UX-03` |
| **P1** | `PLAN-UX-06` | Reprise (`Resume`) défectueuse : étape 2 sautée dès 1 fichier HTML, dump XML partiel non repris, et flags `clean`/`rerender` persistants qui effacent tout | `docs/plans/ux/06-p1-broken-resume-and-sticky-destructive-flags.md` | `scripts/run.py`, `scripts/extract.py`, `server.py`, `tests/*` | Après `PLAN-UX-04`, `PLAN-UX-05` |
| **P1** | `PLAN-UX-07` | Impasse UX après erreur, arrêt ou purge de stockage (`updateDetail`) et absence du bouton `Resume` promis par les logs | `docs/plans/ux/07-p1-ui-state-transitions-and-recovery-actions.md` | `server.py`, `tests/test_server_config.py` | Après `PLAN-UX-06` |
| **P1** | `PLAN-UX-08` | Déconnexion entre le panneau de génération (Étape 2) et les options de format / `Max files` (`Reconfigure`) | `docs/plans/ux/08-p1-step2-generation-options-and-reconfigure-sync.md` | `server.py`, `tests/test_server_config.py` | Après `PLAN-UX-03`, `PLAN-UX-07` |
| **P2** | `PLAN-UX-09` | Titre `<h1>` dupliqué dans tous les exports Markdown, pied de page `Categories:` non nettoyé et `NAMESPACES` ignoré à l'extraction | `docs/plans/ux/09-p2-markdown-duplicate-h1-and-extract-namespaces.md` | `scripts/extract.py`, `scripts/clean_html.py`, `scripts/export_categories.py`, `scripts/merge_pdf.py`, `tests/*` | Indépendant (après `PLAN-UX-02`, `PLAN-UX-06`) |
| **P2** | `PLAN-UX-10` | Détection d'URL MediaWiki (`detect_wiki.py`) en échec sur les URLs copiées avec accents (`%C3%89`), sous-pages ou sans `https://` | `docs/plans/ux/10-p2-wiki-url-detection-and-normalization.md` | `scripts/detect_wiki.py`, `scripts/wiki_names.py`, `server.py`, `tests/test_wiki_names.py` | Indépendant (après `PLAN-UX-02`) |
| **P2** | `PLAN-UX-11` | Incohérences de la barre de progression (`#d-steps`), du terminal de logs et du chemin de sortie (`Copy path`) | `docs/plans/ux/11-p2-progress-steps-logs-and-output-path-ux.md` | `server.py`, `tests/test_server_config.py` | Après `PLAN-UX-07`, `PLAN-UX-08` |
| **P3** | `PLAN-UX-12` | Défauts de formulaires, de valeurs par défaut (`Plus` vs `50`), d'accessibilité (`<label>`, `delay=0`) et d'adaptation responsive | `docs/plans/ux/12-p3-forms-defaults-accessibility-and-responsive.md` | `server.py`, `README.md`, `tests/test_server_config.py` | En dernier (après `PLAN-UX-11`) |

### Ordre séquentiel recommandé (zéro conflit de merge)
Pour éviter tout conflit d'édition sur `scripts/run.py` et `server.py`, il est recommandé d'exécuter les plans dans l'ordre strict :
`PLAN-UX-01` → `PLAN-UX-02` → `PLAN-UX-03` → `PLAN-UX-04` → `PLAN-UX-05` → `PLAN-UX-06` → `PLAN-UX-07` → `PLAN-UX-08` → `PLAN-UX-09` → `PLAN-UX-10` → `PLAN-UX-11` → `PLAN-UX-12`.

---

## 7. Limites de l'audit

1. **Environnement d'exécution Linux vs Windows 10/11 natif :** les scripts batch (`run.bat`, `update.bat`) et l'installation du runtime GTK3 sous Windows ont été audités par inspection statique du code (`Déduit du code`). Le pipeline Python, WeasyPrint, `pikepdf`, FastAPI et le DOM/JS de l'interface (`server._HTML`) ont en revanche été intégralement exécutés et testés en conditions réelles dans le bac à sable.
2. **Accès réseau externe restreint :** le bac à sable n'autorisant pas les requêtes vers des wikis publics arbitraires (`fandom.com`, `wikipedia.org`), le comportement de `detect_wiki.py`, `extract.py` et `build_categories.py` a été vérifié à l'exécution via des réponses HTTP et dumps XML simulés reproduisant fidèlement les formats MediaWiki (`export-0.10`, `export-0.11`, `action=parse`, `list=categorymembers`).
