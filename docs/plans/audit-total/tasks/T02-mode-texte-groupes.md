# T02 — Mode texte : produire réellement un fichier par catégorie

- **Priorité** : P0 · **Axe** : D · **Constats couverts** : D01
- **Justification** : la promesse centrale du produit (« one file per category »)
  n'est pas tenue dans le mode de repli documenté, et le job est marqué réussi.

## Preuve et conséquence

Faux wiki, `dump/config.json` sans `api`, 7 pages HTML, `categories.json`
présent → `run3.log` : `⚠ No API -- direct grouping without hierarchy (text
mode)`, puis `⚠ …/category_groups.json not found -- everything goes into 'Misc'`
et `✓ PIPELINE COMPLETE` (code de sortie 0). Sortie : **un seul** `Misc.md` de
759 octets au lieu de 5 fichiers. Reproduit deux fois.

## État actuel → état cible

- Actuel : `scripts/run.py:339-356`. La branche `elif categories_file.exists():`
  construit `groups` (l.341-345) puis **rien** : les instructions d'écriture
  (l.352-356) sont indentées dans la branche `else` (l.346-351), après
  `return 1` (l.351) → code mort. `category_groups.json` n'est jamais créé.
- Cible : quel que soit le mode, `{job_dir}/category_groups.json` existe avant
  l'étape 5 ; si l'étape 5 le trouve absent, elle échoue avec un message qui
  désigne l'étape 4 (et non « tout dans Misc »).

## Cause racine et sites concernés

Indentation erronée lors d'une refonte : le `return 1` du `else` a été inséré
avant le bloc d'écriture, qui appartenait à l'ancienne branche `elif`.
Site unique (une fonction), mais la donnée `cat_groups` est définie en amont
(`run.py:315-316`), ce qui masque l'oubli à la lecture.

## Plan d'action

1. Sortir les lignes 352-356 du `else` et les placer après le `if/elif/else`,
   sous `if not cat_groups.exists():`.
2. Adapter le log : `  {len(groups)} categories (no hierarchy — text mode)`.
3. Avant l'étape 5, garde-fou : `if not cat_groups.exists(): log("⚠ FAILURE:
   grouping file missing (step 4)"); return 1`.
4. Dé-marquer `test_text_mode_writes_one_file_per_category` (T01).

## Référence à réutiliser

Le bloc `cat_groups.write_text(json.dumps({k: sorted(v) …}))` est correct : le
déplacer, ne pas le réécrire. `defaultdict` est déjà importé (`run.py:19`).

## Points d'impact

`scripts/run.py` uniquement. Format identique à celui de `build_categories.py`
(`{cat: [stem]}`) → `pack_files.py`, `export_categories.py`, `merge_pdf.py`
inchangés. En mode texte `category_tree.json` reste absent : la sélection de
catégories (T11) n'est pas disponible, le log doit le dire explicitement.

## Régression

Aucune. Preuve : le bloc déplacé est une écriture pure sans effet de bord ;
`groups` n'est utilisé nulle part ailleurs (`grep -n "groups" scripts/run.py`) ;
`tests/test_run_pipeline.py` utilise `PHASE=generate` et ne traverse pas cette
branche ; un test de non-régression est ajouté par T01.

## Actions humaines requises

Aucune.

## Dépendances

T01 avant. T11 ensuite si l'on veut la sélection en mode texte.

## Non-objectifs

- Ne pas reconstruire la hiérarchie de catégories sans API (impossible sans
  sous-catégories).
- Ne pas rendre `export_categories.py` tolérant à un fichier manquant.

## Critères d'acceptation

1. Mode texte → un fichier par catégorie (5 fichiers sur le faux wiki), aucun
   `Misc` fourre-tout, `category_groups.json` présent.
2. Fichier manquant → échec explicite, jamais `PIPELINE COMPLETE`.
3. Test de T01 vert.

## Vérification et repli

`PHASE=all` sans API sur le faux wiki puis `ls data/output/*/*/` (5 fichiers).
Repli : `git revert` (une fonction touchée).
