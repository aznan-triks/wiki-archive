# [P1] PLAN-UX-05 — Algorithme de regroupement (`pack_files.py`) fusionnant des thèmes sans rapport (`Cities+Pistols`) et ignorant le mode sans API dans `run.py`

- **Type :** bug / fonctionnel / conception
- **Preuve :**
  - *Confirmé à l'exécution* :
    1. Exécution de `pack_files.pack()` avec `max_files=2` et `dedup=True` (valeur par défaut dans `server.py:70`) sur l'arbre type de `PLAN.md` : `Weapons` (contenant les sous-catégories `Pistols` [3 pages] et `Rifles` [3 pages], sans page directe) et `Locations` (contenant `Cities` [2 pages] et `Dungeons` [4 pages], sans page directe). Au lieu de produire `Weapons` et `Locations`, `pack_files.py` produit **`Cities+Pistols`** et **`Rifles+Dungeons`**.
    2. Exécution de `pack_files.pack()` sur une chaîne à 3 niveaux `Weapons` (3p) → `Pistols` (2p) → `Revolvers` (1p) + `Cooking` (1p) avec `max_files=2` : `Pistols` est absorbé dans `Weapons` et supprimé de `packed`, ce qui rend son enfant `Revolvers` orphelin et le fusionne avec `Cooking` en **`Revolvers+Cooking`**.
    3. Exécution de `scripts/run.py` en mode sans API (`api_url == ""`) avec un `categories.json` valide : l'étape 4 affiche `⚠ No API -- direct grouping without hierarchy (text mode)` mais n'écrit ni `category_groups.json` ni `category_tree.json`, et l'étape 5 affiche `⚠ category_groups.json not found -- everything goes into 'Misc'`.
  - *Déduit du code* :
    - `scripts/pack_files.py:98-103` (`dedup_groups()` retire toutes les catégories parentes n'ayant pas de pages propres)
    - `scripts/pack_files.py:111-130` (l'étape 2 itère dans l'ordre du dictionnaire au lieu d'un parcours ascendant, exige `if parent not in packed: continue`, et supprime `packed[child]` avant d'avoir traité les sous-catégories de `child`)
    - `scripts/pack_files.py:132-151` (l'étape 3 fusionne les deux plus petits groupes globaux avant même de tenter de fusionner des sous-catégories sœurs partageant un même parent)
    - `scripts/run.py:339-356` (`cat_groups.write_text(...)` est indenté dans le bloc `else:` **après `return 1`**, lignes 352-356)

---

## Problème

### 1. `pack_files.py` viole la spécification de regroupement sémantique (`PLAN.md` §B.2)
`PLAN.md` §B.2 spécifie :
- *"2. Bottom-up merge guided by the tree: walk the hierarchy; fold subcategories into their parent as long as the resulting file stays under NOTEBOOKLM_MAX_WORDS. This keeps thematic groupings (e.g. all 'Pistols' + 'Rifles' under a single 'Weapons' if it fits)."*
- *"3. If the file count still exceeds MAX_FILES: bin-packing of the smallest categories/branches together (merge the closest neighbors in the tree first, never unrelated themes at random)."*

Or l'implémentation actuelle dans `scripts/pack_files.py:98-151` échoue dans les deux cas courants :
1. **Parents vidés par `dedup=True` (cas général sur MediaWiki) :** lorsque `dedup=True` (activé par défaut), `dedup_groups()` affecte chaque page à sa catégorie la plus spécifique (les feuilles `Pistols`, `Rifles`, `Cities`, `Dungeons`). Les catégories mères `Weapons` et `Locations` n'ayant pas de pages directes ne figurent plus dans `packed`. À la ligne 115, `if parent not in packed: continue` saute alors `Weapons` et `Locations` ! Aucune fusion parent-enfant n'a lieu, et l'étape 3 fusionne par taille globale à travers tout le wiki (`Cities+Pistols`, `Rifles+Dungeons`).
2. **Parcours descendant (top-down) rendant les petits-enfants orphelins :** même lorsqu'un parent `Weapons` possède des pages directes, la boucle `for parent, node in nodes.items():` (ligne 114) fusionne `Pistols` dans `Weapons` et exécute `del packed["Pistols"]` **avant** que `Revolvers` (enfant de `Pistols`) ait été fusionné dans `Pistols`. Dès lors, `Pistols` n'est plus dans `packed`, `Weapons` ne connaît pas `Revolvers` comme enfant direct, et `Revolvers` est fusionné avec une catégorie sans rapport (`Revolvers+Cooking`).

### 2. Code mort après `return 1` dans `scripts/run.py:351-356` (mode sans API / `--index`)
Dans `scripts/run.py:339-356` :
```python
elif categories_file.exists():
    log("⚠ No API -- direct grouping without hierarchy (text mode)")
    page_cats = json.loads(categories_file.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for stem, cats in page_cats.items():
        for cat in (cats or [MISC_CATEGORY]):
            groups[cat].append(stem)
else:
    log(f"⚠ FAILURE: {categories_file} not found ...")
    return 1
    cat_groups.write_text(
        json.dumps({k: sorted(v) for k, v in groups.items()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"  {len(groups)} categories")
```
À cause de l'indentation de `cat_groups.write_text(...)` dans le `else:` après `return 1` :
- En mode sans API (`api_url == ""`), `category_groups.json` n'est **jamais écrit** sur le disque, et l'étape 5 déverse toutes les pages dans `Misc`.
- De plus, `category_tree.json` n'est pas écrit non plus dans cette branche, ce qui fait que `job.has_tree` vaut `False` et que l'interface ne affiche jamais le panneau de sélection de catégories après un scan en mode texte.

---

## Impact utilisateur

- **Majeur (P1) :**
  - Les fichiers générés pour NotebookLM mélangent des sujets sans aucun lien thématique (`Cities+Pistols.md`, `Revolvers+Cooking.md`) au lieu de regrouper les sous-catégories sous leur catégorie parente (`Weapons.md`, `Locations.md`), dégradant directement la qualité des réponses de NotebookLM et la lisibilité des fichiers.
  - Tout wiki archivé via `index.php` (sans `api.php`) perd 100 % de ses catégories et ne peut pas utiliser l'étape 2 (sélection de catégories).

---

## Comportement actuel

1. `pack_files.py` ignore les catégories parentes vidées par `dedup`, fusionne en ordre arbitraire (top-down), et fusionne des catégories de branches différentes avant même d'avoir regroupé les sous-catégories d'un même parent.
2. `run.py` n'écrit ni `category_groups.json` ni `category_tree.json` lorsque `api_url` est vide.

---

## Comportement attendu

1. Dans `pack_files.py`, le regroupement à l'étape 2 s'effectue **de bas en haut (bottom-up, par profondeur décroissante dans l'arbre)** :
   - Les feuilles sont d'abord repliées vers leur parent (même si le parent avait 0 page directe après `dedup` : si plusieurs enfants d'un même `parent` ou un enfant et son `parent` sont dans `packed` et que leur union respecte `max_words` / `max_pages`, ils fusionnent sous le nom `parent`, en commençant par les sous-arbres les plus profonds et les plus petits).
2. À l'étape 3 (si `len(packed) > max_files` persiste après épuisement des fusions parent-enfant), fusionner en priorité deux catégories partageant un ancêtre commun proche avant de fusionner les deux plus petites catégories globales.
3. Dans `scripts/run.py:339-356`, lorsque `api_url` est vide et que `categories_file.exists()` est vrai, écrire `category_groups.json` **et** `category_tree.json` (arbre plat où chaque catégorie est une racine avec son `total_pages` et `total_words` calculé depuis `page_words.json`).

---

## Cause probable

1. Dans `pack_files.py`, l'étape 2 a été écrite avec une simple boucle `for parent, node in nodes.items()` en supposant que `parent` était toujours présent dans `packed` après `dedup_groups()`.
2. Dans `scripts/run.py:346-356`, lors de l'ajout du bloc `else: return 1` au commit `507f869`, les lignes `cat_groups.write_text(...)` ont été indentées dans le `else:` au lieu de rester dans le `elif categories_file.exists():`.

---

## Zones concernées

- `scripts/pack_files.py` : lignes 111-151 (`pack()`).
- `scripts/run.py` : lignes 339-357 (étape 4 sans API).
- `tests/test_run_pipeline.py` et nouveau fichier ou tests dans `tests/test_build_categories.py`.

---

## Points d'impact

- **Appelants de `pack_files.pack()` :** `scripts/pack_files.py:176` (`main()`) et `server.py:562` (`_packing_preview`). Comme les deux partagent la même fonction `pack()`, l'aperçu UI et la génération réelle seront automatiquement alignés.
- **Tests existants :** aucun test existant ne teste `pack_files.py` directement (manque de couverture actuel).

---

## Plan d'action

1. **Corriger le mode sans API dans `scripts/run.py` (lignes 339-357) :**
   - Désindenter `cat_groups.write_text(...)` et `log(f"  {len(groups)} categories")` pour les remettre à la fin du bloc `elif categories_file.exists():`.
   - Dans ce même bloc `elif`, charger `page_words` (s'il existe) et écrire `tree_file` (`category_tree.json`) avec `roots = sorted(groups.keys())` et `nodes = {cat: {"children": [], "pages": sorted(stems), "total_pages": len(stems), "total_words": sum(page_words.get(s, 0) for s in stems)} for cat, stems in groups.items()}`.
2. **Corriger la fusion guidée par l'arbre dans `scripts/pack_files.py` (lignes 111-151) :**
   - Calculer la profondeur de chaque nœud de `nodes` depuis `tree.get("roots", [])` (BFS simple avec garde anti-cycle) et conserver un dictionnaire `active_children[parent]` des descendants directs (ou promus quand un enfant intermédiaire est absorbé).
   - Parcourir les parents par **profondeur décroissante (bottom-up)** :
     - Si `parent` est dans `packed` et qu'un `child` de `parent` est dans `packed`, les fusionner dans `packed[parent]` (si l'union ne dépasse pas `max_words`/`max_pages`) et promouvoir les enfants de `child` comme enfants de `parent`.
     - Si `parent` n'est pas dans `packed` (parce que `dedup` l'a vidé) mais qu'au moins deux enfants de `parent` sont dans `packed`, fusionner les deux plus petits enfants de `parent` sous le nom `parent` (tant que l'union respecte la limite), ce qui recrée `packed[parent]` et permet d'y replier les autres enfants de `parent`.
3. **Ajouter des tests automatisés :**
   - Tester `pack_files.pack()` sur le cas `Weapons` (`Pistols` + `Rifles`) et `Locations` (`Cities` + `Dungeons`) avec `dedup=True, max_files=2` → doit retourner `{"Weapons": [...], "Locations": [...]}` (et jamais `Cities+Pistols`).
   - Tester `pack_files.pack()` sur la chaîne à 3 niveaux `Weapons -> Pistols -> Revolvers` + `Cooking` avec `max_files=2` → doit retourner `{"Weapons": [...], "Cooking": [...]}` (et jamais `Revolvers+Cooking`).
   - Tester `run.py` en mode sans API (`api_url=""`) → doit écrire `category_groups.json` et `category_tree.json` et exporter un fichier par catégorie (et non tout dans `Misc`).

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas introduire d'algorithme complexe de clustering NLP/embeddings : l'arbre de catégories MediaWiki existant suffit intégralement.

---

## Contraintes

- `pack_files.pack()` doit rester déterministe et rapide (< 100 ms sur un arbre de 3 000 catégories, car elle est appelée par `/api/jobs/{id}/preview_packing` à chaque clic dans l'arbre avec un debounce de 350 ms).

---

## Dépendances

- **À traiter après :** `PLAN-UX-03` (qui ajoute `filter_groups_by_selection` dans `scripts/pack_files.py`).

---

## Critères d'acceptation

1. Sur un wiki ayant `Weapons` (`Pistols`, `Rifles`) et `Locations` (`Cities`, `Dungeons`) sans pages directes dans les racines, `pack(..., max_files=2, dedup=True)` produit exactement `Weapons` et `Locations`.
2. Sur une hiérarchie à 3 niveaux `Weapons -> Pistols -> Revolvers` et une catégorie isolée `Cooking`, `pack(..., max_files=2, dedup=True)` regroupe `Weapons`, `Pistols` et `Revolvers` sous `Weapons` et laisse `Cooking` séparé.
3. En mode sans API (`config.json` sans clé `api`), l'étape 4 de `run.py` écrit `category_groups.json` et `category_tree.json`, et l'étape 5 génère un fichier par catégorie au lieu d'un unique fichier `Misc`.

---

## Vérification

1. Exécuter `python -m pytest`.
2. Vérifier dans l'aperçu `/api/jobs/{id}/preview_packing` que la réduction de `max_files` regroupe bien les sous-catégories sous leur catégorie mère.

---

## Risques

- Sur un DAG comportant des cycles dans `nodes[cat]["children"]`, le calcul de profondeur doit utiliser un ensemble `visited` pour éviter toute boucle infinie.
