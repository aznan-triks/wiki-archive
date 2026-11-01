# T11 — Aperçu et sélection : une seule vérité sur « ce qui sera produit »

- **Priorité** : P1 (D07) + P2 (C14, D30) · **Axe** : D/C
- **Constats couverts** : D07, C14, D30
- **Justification** : l'aperçu est présenté comme « same logic as generation »
  dans le code, et le README promet qu'une page apparaît dans chaque fichier de
  ses catégories. Les deux affirmations sont fausses, dans le sens qui coûte des
  données (pages manquantes non annoncées).

## Preuve et conséquence

- **D07 (P1)** : même job, même sélection — `POST /preview_packing` →
  `{"file_count": 4}` ; fichiers réellement produits : **5** (`BigTable`, `Misc`,
  `Pistols`, `Rifles`, `Weapons`). Cause : l'aperçu ne compte que
  `category_groups.json` (`server.py:530-579`) alors que `MISC_CATEGORY` est
  ajouté **au moment de l'écriture** (`export_categories.py:189-193`,
  `merge_pdf.py:64-68`).
- **C14 (P2)** : `selection: ["Weapons"]` → sortie `Weapons.md/.txt`
  seulement ; la page non catégorisée « Empty » disparaît, et `Misc` n'est pas
  produite, sans avertissement. L'arbre affiche « 4 / 4 catégories sélectionnées »
  (`build_categories.py:167-187` n'a pas de nœud pour ces pages ;
  `run.py:370-379` met `add_divers=False` dès qu'un fichier de sélection existe).
- **D30** : `selection: ["Nope","Weapons"]` → `file_count: 1`, aucune mention de
  « Nope » (filtre muet dans `server.py:558-560` et `run.py:370-379`).

## État actuel → état cible

Un seul calcul de regroupement, utilisé par l'aperçu **et** par la génération,
exposant explicitement :

```
{"file_count": 5,
 "files": [{"name": "Weapons", "categories": [...], "pages": 39, "words": 41_200}],
 "misc": {"pages": 1, "words": 900, "included": true},
 "unknown": [],
 "warnings": ["1 page sans catégorie sera ajoutée à 'Misc'"]}
```

- L'aperçu appelle le **même** chemin de code que la génération
  (`pack_files.build_packing(groups, max_files)`) puis applique le même ajout de
  `Misc`, sans écrire de fichiers.
- La sélection est un sous-ensemble de l'arbre **+ un nœud virtuel « Misc »**
  sélectionnable comme les autres (défaut : coché).
- Les noms inconnus sont renvoyés dans `unknown` et affichés.

## Cause racine et sites concernés

Trois implémentations divergentes de « quels fichiers seront produits » :
(1) `_packing_preview` côté serveur (aperçu), (2) `run.py:360-399` (sélection +
`add_divers`), (3) `export_categories.py` / `merge_pdf.py` (ajout de `Misc` à
l'écriture). Aucune n'est la source de vérité ; l'aperçu est une ré-implémentation
partielle, sans les pages non catégorisées.

## Référence à réutiliser

- `pack_files.build_groups()` / `pack_files.pack()` sont déjà partagés par
  `run.py` (génération) : l'aperçu doit les appeler.
- `MISC_CATEGORY` est déjà une constante de `export_categories.py` ; la remonter
  dans `pack_files.py` pour que les trois chemins la voient.
- `page_words.json` est déjà lu par l'aperçu (`server.py:530-556`) : la
  volumétrie par fichier est donc à portée.

## Plan d'action

1. `pack_files.py` : exposer `build_packing(groups, max_files, misc_pages) ->
   list[dict]` (nom, catégories, stems) et `MISC_CATEGORY` ; `pack()` devient un
   adaptateur.
2. `server.py:_packing_preview` : lire `category_groups.json` + calculer le
   groupe `Misc` (pages de `categories.json` dont la liste de catégories est vide)
   puis appeler `build_packing` ; renvoyer `files`, `misc`, `unknown`, `warnings`.
3. `run.py:360-399` : utiliser le même `build_packing` ; `ADD_DIVERS` disparaît
   (le nœud « Misc » de la sélection décide) — conserver la variable
   d'environnement en compatibilité (`ADD_DIVERS=1` ⇒ Misc cochée).
4. `build_categories.py` : ajouter un nœud racine virtuel
   `"__misc__"` (libellé « Pages sans catégorie ») avec son compteur, dans
   `category_tree.json`, marqué `virtual: true`.
5. JS (`renderJob`, arbre) : afficher ce nœud (icône différente, non
   « catégorie »), l'inclure dans le compteur de sélection, et afficher
   `unknown`/`warnings` dans le bandeau de génération (`updateGenInfo`).
6. `export_categories.py` / `merge_pdf.py` : recevoir le groupe `Misc` calculé
   en amont (l'ajout à l'écriture devient une simple lecture) pour que
   génération et aperçu ne puissent plus diverger.
7. Dé-marquer `test_preview_matches_generated_file_count` et
   `test_selection_drops_uncategorized_only_with_notice` (T01).

## Points d'impact

`scripts/pack_files.py`, `scripts/build_categories.py`, `scripts/run.py`,
`scripts/export_categories.py`, `scripts/merge_pdf.py`, `server.py`
(`_packing_preview`, handlers `generate`/`preview_packing`), JS, README
(§« Selection », §« 5-step pipeline »). Tests : `test_run_pipeline.py`,
`test_build_categories.py`, `test_merge_pdf.py`, `test_export_categories.py`.

## Régression

Aucune sur le résultat quand **aucune** sélection n'est active (les pages non
catégorisées étaient déjà incluses via `Misc`) : la sortie est identique, seul le
compteur de l'aperçu change (4 → 5, ce qui est la correction).
Régression **assumée** : avec une sélection active, `Misc` est désormais cochée
par défaut (alors qu'elle était silencieusement exclue) — le nombre de fichiers
produits augmente de 1 pour les utilisateurs qui sélectionnent des catégories.
Justification : les pages exclues aujourd'hui disparaissent sans avertissement ;
le défaut sûr est de les inclure, et l'utilisateur peut décocher « Pages sans
catégorie ».

## Actions humaines requises

Valider la régression assumée (Misc cochée par défaut dans une sélection).

## Dépendances

T01, T03 (chemins), T12 (le calcul doit être assez rapide pour l'aperçu : même
fonction, donc F01 doit être corrigé avant ou en même temps, sinon l'aperçu
devient plus lent qu'aujourd'hui).

## Non-objectifs

- Pas d'aperçu « page par page » (liste des 20 000 titres) : la volumétrie et les
  compteurs suffisent.
- Pas de prévisualisation du contenu texte (hors périmètre).

## Critères d'acceptation

1. Sur le job de l'audit : `preview_packing` → `file_count: 5`, identique aux 5
   fichiers produits (comparaison automatique dans le test).
2. Sélection `["Weapons"]` → `Misc.md` produite (ou `included:false` si
   décochée, avec `warnings` non vide).
3. Sélection avec un nom inconnu → `unknown: ["Nope"]` affiché dans l'UI.
4. L'arbre affiche « Pages sans catégorie : 1 » et le compteur global la compte.

## Vérification et repli

Comparer `preview_packing.files[].name` à `os.listdir(out_dir)` sur trois
scénarios (sans sélection, sélection partielle, sélection + Misc décochée).
Repli : `git revert` par point.
