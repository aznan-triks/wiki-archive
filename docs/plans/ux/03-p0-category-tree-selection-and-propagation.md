# [P0] PLAN-UX-03 — Sélection partielle dans l'arbre de catégories supprimant les pages directes des catégories parentes et occultant les cycles / `Misc`

- **Type :** bug / fonctionnel / UX
- **Preuve :**
  - *Confirmé à l'exécution* :
    1. Simulation de l'arbre UI (`server.py:1622-1779`) avec `Weapons` (40 pages directes) → `Pistols` (30 pages directes) → `Revolvers` (10 pages) + `SemiAuto` (20 pages). Lorsque l'utilisateur décoche uniquement `Revolvers` (10 pages sur 100), `nodeState` passe à `{Weapons: 1, Pistols: 1, Revolvers: 0, SemiAuto: 2}`, et `selectedCats()` renvoie uniquement `['SemiAuto']` : **les 70 pages directes de `Weapons` et `Pistols` sont perdues**.
    2. Si `Pistols` n'a qu'une seule sous-catégorie (`Revolvers`), décocher `Revolvers` fait passer `nodeState["Pistols"]` et `nodeState["Weapons"]` à **`0` (totalement décochés)** (`st.every(s => s === 0)` à `server.py:1641`), affichant `0 / 3 categories selected`.
    3. Inversement, si `Weapons` était conservé tel quel depuis `category_groups.json` (qui stocke l'union pré-propagée `full_pages`), `pack_files.py` exporterait encore les pages de `Revolvers` (pourtant décochée) à l'intérieur de `Weapons`.
    4. Sur deux catégories en cycle `Weapons ↔ Equipment`, `build_categories.py:170` calcule `roots = []`, et l'UI affiche `"No root category."`.
  - *Déduit du code* :
    - `server.py:1636-1643` (`recomputeAncestors` calcule l'état d'un parent uniquement via `st.every(s => s === 0) ? 0 : 1` sans tenir compte des pages directes du parent)
    - `server.py:1777-1779` (`selectedCats()` filtre `s === 2`, excluant tout parent en état `1`)
    - `server.py:555-557` (`_packing_preview`) et `scripts/run.py:370-378` (filtrent `category_groups.json` pré-propagé par `k in sel` et forcent `add_divers = False`)
    - `scripts/build_categories.py:131-143, 167-186` (`roots` exclut tout nœud ayant un parent, et les pages sans catégorie ne figurent ni dans `category_groups.json` ni dans `category_tree.json`)

---

## Problème

L'outil de sélection par catégories et sous-catégories (Workstream D de `PLAN.md` : *"pouvoir scanner le wiki pour désélectionner ce que je ne veux pas, organisé en catégories et sous-catégories"*) souffre de quatre défauts structurels qui faussent la sélection dès que l'utilisateur décoche une sous-catégorie :

### 1. Décocher une sous-catégorie supprime toutes les pages directes de ses catégories parentes
Dans MediaWiki, une catégorie parente (ex. `Weapons`) possède souvent à la fois des **pages directes** (ex. `Weapons_Overview`, `Damage_Mechanics`) et des **sous-catégories** (`Pistols`, `Rifles`).
Dans `server.py` :
- Lorsque l'utilisateur décoche `Pistols`, `recomputeAncestors()` (`server.py:1636-1643`) met `nodeState["Weapons"] = 1` (état indéterminé `cb.indeterminate = true`).
- Or `selectedCats()` (`server.py:1777-1779`) ne renvoie que les catégories où `nodeState === 2` (`Object.entries(nodeState).filter(([, s]) => s === 2)`).
- Toutes les catégories ancêtres en état `1` sont donc exclues de `selectedCats()`, et **toutes leurs pages directes disparaissent de l'aperçu et des fichiers générés**.
- Pire encore : si une catégorie parente `Weapons` n'a qu'**une seule** sous-catégorie `Pistols` (en plus de ses 50 pages directes), décocher `Pistols` rend `st.every(s => s === 0)` vrai (`server.py:1641`) et met `nodeState["Weapons"] = 0` (case totalement décochée !). Il est **impossible** dans l'interface de garder `Weapons` tout en excluant son unique sous-catégorie `Pistols`.

### 2. Contradiction avec la pré-propagation dans `category_groups.json`
`scripts/build_categories.py:131-143` écrit dans `category_groups.json` l'ensemble `full_pages[cat]`, c'est-à-dire l'union des pages directes de `cat` **et de toutes ses sous-catégories descendantes** avant toute sélection utilisateur.
Ainsi, si l'on incluait simplement les ancêtres en état `1` dans `category_groups.json`, `groups["Weapons"]` contiendrait encore toutes les pages de `Pistols` (pourtant décochée !), et décocher une sous-catégorie n'aurait aucun effet.
Pour que la désélection d'une sous-catégorie fonctionne réellement, la propagation parent ← enfant doit n'agréger que les **catégories sélectionnées**, à partir des pages directes déjà stockées dans `category_tree.json` (`tree["nodes"][cat]["pages"]`).

### 3. Les pages non catégorisées (`Misc`) sont invisibles dans l'arbre et supprimées dès qu'on clique sur `▶ Generate selection`
- `build_categories.py` n'inclut pas `Misc` (pages ayant `cats == []` dans `categories.json`) dans `category_tree.json` ni dans `category_groups.json`.
- Dans `scripts/run.py:370-378`, dès que `selection.json` existe (c'est-à-dire dès que l'utilisateur clique sur le bouton principal **`▶ Generate selection`**, même en laissant 100 % des catégories cochées !), `run.py` force `add_divers = False`.
- Toutes les pages non catégorisées du wiki sont alors silencieusement omises, sans que l'utilisateur ait jamais vu de ligne `Misc (Uncategorized)` dans l'arbre ni pu choisir de la conserver ou de la décocher.

### 4. Les cycles entre catégories de haut niveau produisent `roots = []` (`"No root category."`)
Dans `scripts/build_categories.py:167-170` :
```python
roots = sorted(c for c in all_cats if c not in all_child_cats and c in full_pages)
```
Sur de nombreux wikis MediaWiki, des catégories de haut niveau se référencent mutuellement (`Category:Browse` ⊂ `Category:Main` ⊂ `Category:Browse`). Toute composante connexe dépourvue de nœud de degré entrant nul est absente de `roots` et donc totalement invisible dans l'arbre UI (qui affiche `"No root category."` si toutes les racines sont dans un cycle).

---

## Impact utilisateur

- **Critique (P0) :** la fonctionnalité phare de sélection/désélection de sous-catégories détruit silencieusement les articles des catégories parentes, empêche de décocher une sous-catégorie unique sans décocher son parent, supprime les pages `Misc` dès qu'on clique sur `▶ Generate selection`, et masque les branches cycliques.

---

## Comportement actuel

1. Décocher une sous-catégorie exclut tous ses ancêtres de `selectedCats()` et supprime leurs pages directes.
2. Décocher l'unique sous-catégorie d'un parent décoche totalement le parent (`nodeState = 0`).
3. Cliquer sur `▶ Generate selection` (même avec tout coché) supprime `Misc`, tandis que `Generate all` inclut `Misc` et efface `selection.json`.
4. Une composante cyclique sans nœud de degré entrant 0 n'apparaît pas dans `roots`.

---

## Comportement attendu

1. Décocher une sous-catégorie `Sub` retire uniquement les pages de `Sub` (et de ses descendants décochés), tout en **conservant les pages directes** de ses catégories parentes (`Weapons`, `Pistols`) ainsi que leurs autres sous-catégories restées cochées.
2. Si l'utilisateur décoche `Sub` alors que son parent `Parent` possède des pages directes, `Parent` passe à l'état partiel (`1` / indéterminé) et ses pages directes restent incluses ; si l'utilisateur clique ensuite sur la case de `Parent`, il peut basculer tout `Parent` (pages directes + enfants) entre décoché (`0`) et coché (`2`).
3. Les pages non catégorisées (s'il en existe dans `categories.json`) apparaissent dans `category_tree.json` et `category_groups.json` sous la racine `MISC_CATEGORY` (`Misc`), avec leur nombre de pages et de mots, pour que l'utilisateur puisse les voir et les cocher/décocher comme n'importe quelle catégorie.
4. Si des catégories de `full_pages` ne sont atteignables depuis aucune racine de `roots` (composantes cycliques), `build_categories.py` sélectionne déterministement la catégorie la plus large (`total_pages` max) de chaque composante non couverte et l'ajoute à `roots`.

---

## Cause probable

Le modèle de sélection a été conçu comme un simple filtre sur les clés de `category_groups.json` (`{k: v for k, v in groups.items() if k in sel}`) en supposant que seules les feuilles de l'arbre contenaient des pages et que le graphe de catégories était une forêt sans cycles.

---

## Zones concernées

- `scripts/build_categories.py` : lignes 117-189 (ajout de `MISC_CATEGORY` pour les pages sans catégorie de `page_cats`, et couverture des composantes cycliques dans `roots`).
- `scripts/pack_files.py` : ajout d'une fonction utilitaire `filter_groups_by_selection(groups, tree, selection)` (partagée entre `server.py` et `scripts/run.py` — principe SSOT/DRY).
- `server.py` :
  - lignes 555-558 (`_packing_preview` utilisant `pack_files.filter_groups_by_selection`)
  - lignes 687-700 (`get_category_tree` : remplacer `node.pop("pages", None)` par `node["direct_pages"] = len(node.pop("pages", []))` pour que le client sache si un parent a des pages directes sans alourdir le JSON)
  - lignes 1636-1643, 1702-1710, 1732-1739, 1777-1795 (logique tri-state `recomputeAncestors` et `selectedCats` côté UI)
- `scripts/run.py` : lignes 340-345, 368-379 (utilisation de `filter_groups_by_selection`).
- `tests/test_build_categories.py`.

---

## Points d'impact

- **Appelants :** `_packing_preview` (`server.py:530`), `run.py` étape 4.5 (`scripts/run.py:370`), UI arbre (`server.py:1622-1840`).
- **Tests existants :**
  - `tests/test_build_categories.py:55-82` : dans `test_hierarchy_propagation_and_tree`, `P1` et `P2` ont tous deux une catégorie, donc `Misc` est vide et n'est pas ajouté (`roots == ["Weapons"]` reste inchangé).
  - `tests/test_export_categories.py` et `tests/test_merge_pdf.py` : continuent à tester le fallback `ADD_DIVERS` lorsque `export_categories.py` ou `merge_pdf.py` est appelé isolément en ligne de commande.
- **Risque de casse :** les fichiers `category_tree.json` déjà générés dans d'anciens jobs ont déjà la clé `"pages"` sur chaque nœud (`build_categories.py:180`), donc la reconstruction des groupes filtrés fonctionne même sans re-scanner les jobs existants.

---

## Plan d'action

1. **Dans `scripts/build_categories.py` (lignes 117-186) :**
   - Importer `MISC_CATEGORY` depuis `wiki_names`.
   - Recenser les pages de `page_cats` dont la liste de catégories est vide (`if not cats: direct_pages[MISC_CATEGORY].add(stem)` et ajouter `MISC_CATEGORY` à `all_cats`). Ainsi, `Misc` est présent dans `category_groups.json` et dans `category_tree.json` uniquement lorsqu'il existe réellement des pages sans catégorie.
   - Après le calcul initial de `roots` (ligne 170), parcourir les catégories accessibles depuis `roots` via `direct_subcats` ; tant qu'il reste des catégories dans `full_pages` non atteintes (cycles au sommet), ajouter à `roots` celle qui a le plus grand `len(full_pages[c])` (à égalité, par ordre alphabétique) et marquer ses descendants comme atteints.
2. **Dans `scripts/pack_files.py` :**
   - Ajouter une fonction pure `filter_groups_by_selection(groups: dict[str, list[str]], tree: dict, selection: list[str] | set[str] | None) -> dict[str, list[str]]` :
     - Si `selection is None`, retourner `groups`.
     - Si `tree` contient `"nodes"` avec les listes `"pages"` (pages directes) : pour chaque catégorie `cat` présente dans `selection`, ses pages retenues sont l'union de `direct_pages[cat]` et, récursivement, des `direct_pages[desc]` uniquement pour les descendants `desc` **qui sont eux aussi dans `selection`**.
     - De plus, pour toute catégorie ancêtre `anc` non présente dans `selection` mais ayant au moins un descendant dans `selection` **et** ayant ses propres `direct_pages[anc]` (ou mieux : en incluant dans `selection` côté UI toute catégorie en état `2` ou `1` et en ne propageant que vers les enfants en état `1` ou `2`), chaque catégorie retenue ne contient que ses pages directes et celles de ses sous-catégories effectivement retenues.
     - Si une catégorie retenue n'a finalement aucune page (ni directe ni issue d'enfants retenus), l'omettre du dictionnaire retourné.
3. **Dans `server.py` et `scripts/run.py` :**
   - Dans `get_category_tree` (`server.py:698-699`), remplacer `node.pop("pages", None)` par `node["direct_pages"] = len(node.pop("pages", []) or [])`.
   - Dans `recomputeAncestors` (`server.py:1636-1643`), si un parent a `node.direct_pages > 0` et que tous ses enfants sont à `0`, mettre le parent à `1` (partiel, car ses pages directes sont toujours sélectionnées) au lieu de `0`.
   - Dans `selectedCats()` (`server.py:1777-1779`), retourner les catégories où `nodeState[c] === 2 || nodeState[c] === 1` (toute catégorie totalement ou partiellement cochée reste active pour ses pages directes et ses sous-catégories actives).
   - Dans `updateGenInfo()` (`server.py:1780-1785`), afficher le compteur clair (`X / Y categories selected`, et mentionner `incl. N partial` si des parents sont en état `1`).
   - Dans `_packing_preview` (`server.py:555-558`) et `scripts/run.py:370-378`, appeler `pack_files.filter_groups_by_selection(groups, tree, sel)` au lieu de `{k: v for k, v in groups.items() if k in sel}`.
4. **Tests (`tests/test_build_categories.py`) :**
   - Ajouter un test de cycle `A ↔ B` vérifiant que `roots` n'est pas vide.
   - Ajouter un test avec une page sans catégorie vérifiant que `Misc` apparaît dans `category_tree.json`.
   - Ajouter un test unitaire de `filter_groups_by_selection` vérifiant que décocher `Revolvers` sous `Weapons -> Pistols -> Revolvers` conserve les pages directes de `Weapons` et `Pistols` tout en excluant strictement les pages de `Revolvers`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas afficher les articles individuels comme feuilles dans l'arbre UI (l'arbre doit rester léger sur les wikis de 10 000 pages).

---

## Contraintes

- Conserver la compatibilité ascendante avec les fichiers `category_tree.json` déjà présents sur le disque.
- Ne pas dupliquer la logique de filtrage entre `server.py` et `scripts/run.py` : elle doit résider dans `scripts/pack_files.py`.

---

## Dépendances

- **À traiter avant :** `PLAN-UX-05` (algorithme de regroupement `pack_files.py`, qui consomme les groupes filtrés).

---

## Critères d'acceptation

1. Dans une hiérarchie `Weapons` (pages directes `W1`) → `Pistols` (pages directes `P1`) → `Revolvers` (`R1`), décocher `Revolvers` dans l'arbre conserve `W1` et `P1` et exclut `R1` aussi bien dans l'aperçu `/preview_packing` que dans les fichiers générés.
2. Si `Pistols` n'a qu'un seul enfant `Revolvers` mais possède des pages directes `P1`, décocher `Revolvers` laisse `Pistols` en état indéterminé (`1`) et non décoché (`0`).
3. Un wiki contenant des pages sans catégorie affiche `Misc` dans l'arbre de sélection.
4. Un wiki dont les catégories principales forment un cycle (`A ↔ B`) affiche au moins une racine dans l'arbre au lieu de `"No root category."`.

---

## Vérification

1. Exécuter `python -m pytest`.
2. Créer un arbre de test avec cycles, pages directes sur les parents et pages orphelines (`Misc`), décocher une feuille dans l'UI, vérifier l'aperçu et les fichiers générés.

---

## Risques

- Lors de la restauration d'une sélection sauvegardée (`loadTree` dans `server.py:1702-1708`), appeler `setDescendants(c, 2)` sur un parent en état `1` recocherait ses enfants décochés ! Dans `loadTree`, lorsque `saved` est chargé, il faut initialiser `nodeState[c] = 2` uniquement pour chaque `c` de `saved`, puis appeler `recomputeAncestors` pour calculer les états `1` des parents, **sans** appeler `setDescendants(c, 2)` qui écraserait les sous-catégories volontairement exclues de `saved`.
