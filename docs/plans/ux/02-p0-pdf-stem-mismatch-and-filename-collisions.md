# [P0] PLAN-UX-02 — Perte des articles à espaces ou accents dans les PDF (`flatten`) et écrasement des catégories tronquées (`cat_stem`)

- **Type :** bug / fonctionnel
- **Preuve :**
  - *Confirmé à l'exécution* :
    1. Création de 3 PDF unitaires (`Pistol.pdf`, `Assault Rifle.pdf`, `Épée.pdf`) via `wiki_names.page_stem()` et d'un `category_groups.json` `{"Weapons": ["Pistol", "Assault Rifle", "Épée"]}`. Après appel à `run.flatten(pdf_dir, flat_dir, ".pdf")` puis `scripts/merge_pdf.py`, `flat_dir` contient `['Assault_Rifle.pdf', 'Pistol.pdf', 'Epee.pdf']`. `merge_pdf.py` ne trouve que `Pistol` dans `Weapons.pdf` (1 article) et rejette `Assault_Rifle.pdf` et `Epee.pdf` dans `Misc.pdf` (ou les supprime totalement lorsque `ADD_DIVERS=false` en mode sélection).
    2. Appel à `wiki_names.cat_stem()` sur deux parties d'une catégorie longue (`"... (part 1)"` et `"... (part 2)"` de plus de 72 caractères) : les deux retournent exactement la même chaîne de 80 caractères, provoquant l'écrasement silencieux de la partie 1 par la partie 2 sur le disque.
  - *Déduit du code* :
    - `scripts/wiki_names.py:24-34` (`page_stem` conserve `\w` Unicode et `\s` espaces ; `cat_stem` tronque à `[:80]`)
    - `scripts/run.py:75-97` (`flatten()` normalise en `NFKD` ASCII et remplace tout caractère hors `[A-Za-z0-9._-]` — dont les espaces — par `_`)
    - `scripts/run.py:404-405` (appelle `flatten(pdf_dir, flat_dir, ".pdf")` avant `merge_pdf.py`)
    - `scripts/merge_pdf.py:36-65` (compare `stem in available` où `stem` vient de `page_stem` et `available` vient de `flat_dir`)
    - `scripts/pack_files.py:78` (nomme les découpages `f"{name} (part {i + 1})"`)
    - `scripts/export_categories.py:216, 224` (écrit `out_dir / f"{cat_stem(cat)}{EXT[fmt]}"` sans vérifier les collisions de noms de fichiers)

---

## Problème

Deux ruptures dans les règles de nommage corrompent silencieusement les fichiers produits :

### 1. `run.py::flatten()` détruit la correspondance avec `wiki_names.page_stem()` pour tous les PDF
`CHANGELOG.md` documente la création de `scripts/wiki_names.py` comme source unique de vérité (`page_stem`) partagée entre `extract.py`, `build_categories.py`, `export_categories.py` et `merge_pdf.py`.
Or :
- `wiki_names.page_stem("Assault Rifle")` renvoie `"Assault Rifle"` (avec espace) et `wiki_names.page_stem("Épée")` renvoie `"Épée"` (avec accents).
- `convert.py` lit `html/*.html` et écrit à plat dans `pdf/` avec exactement le même stem (`pdf/Assault Rifle.pdf`, `pdf/Épée.pdf`).
- Mais à l'étape 5, `scripts/run.py:404` appelle `flatten(pdf_dir, flat_dir, ".pdf")` (`scripts/run.py:75-97`), vestige d'une ancienne architecture bash (`flatten.sh`), qui :
  1. duplique inutilement tous les PDF sur le disque (`pdf/` → `flat/`) ;
  2. supprime tous les accents (`NFKD` → ASCII) ;
  3. remplace tous les espaces par `_` (`re.sub(r"[^A-Za-z0-9._-]", "_", flat)`).
- Quand `merge_pdf.py` s'exécute sur `flat_dir`, `available` contient `"Assault_Rifle"` et `"Epee"`, tandis que `category_groups.json` contient `"Assault Rifle"` et `"Épée"`.
- **Résultat :** `if stem in available:` échoue pour **100 % des articles dont le titre comporte un espace (la majorité des articles d'un wiki !) ou un caractère accentué/non-latin**.
  - Si `ADD_DIVERS=true` (génération complète), tous ces articles sont déversés à tort dans `Misc.pdf` (d'où la ligne du `README.md:196` : *"Many uncategorized files → huge Misc.pdf"*).
  - Si `ADD_DIVERS=false` (génération depuis une sélection de catégories), **tous les articles contenant un espace ou un accent disparaissent purement et simplement des PDF générés**.

### 2. Troncature et collisions dans `cat_stem()` (`pack_files.py`, `export_categories.py`, `merge_pdf.py`)
- Lorsque `pack_files.py:78` découpe une catégorie dépassant 500 000 mots, il nomme les entrées `"{name} (part 1)"`, `"{name} (part 2)"`.
- `wiki_names.cat_stem()` (`scripts/wiki_names.py:30-34`) transforme `"Weapons (part 1)"` en `"Weapons__part_1_"` (double underscore et underscore final disgracieux, incohérent avec `"Weapons_part1"` de `merge_pdf.py:76`), et surtout tronque à `safe[:80]`.
- Si le nom de la catégorie (ou d'une fusion `Cat1+Cat2+...`) dépasse 72 caractères, le suffixe `(part 1)` / `(part 2)` se trouve au-delà du 80e caractère et est tronqué : toutes les parties produisent le même nom de fichier et s'écrasent mutuellement dans `export_categories.py` et `merge_pdf.py`.
- De même, deux catégories distinctes ne différant que par de la ponctuation (ex. `"A / B"` et `"A : B"`) produisent le même `cat_stem` et la seconde écrase la première.

---

## Impact utilisateur

- **Critique (P0) — Corruption et perte silencieuse de données :**
  - Dans tout export PDF, les catégories ne contiennent que les articles dont le titre est un mot unique en ASCII pur (ex. `Pistol`), tandis que tous les articles à plusieurs mots (`Assault Rifle`, `Main Page`, `Heavy Armor`) ou accentués sont soit relégués dans `Misc.pdf`, soit perdus.
  - Le stockage disque intermédiaire des PDF est doublé inutilement (`job_dir/pdf` + `job_dir/flat`).
  - Les catégories longues découpées en plusieurs parties perdent toutes leurs parties sauf la dernière.

---

## Comportement actuel

1. `run.py` copie `pdf/*.pdf` vers `flat/*.pdf` en altérant les noms de fichiers (ASCII + underscores), ce qui casse la jointure avec `category_groups.json` dans `merge_pdf.py`.
2. `pack_files.py` génère des suffixes ` (part N)` qui deviennent `__part_N_` via `cat_stem()` et sont perdus au-delà de 80 caractères.
3. `export_categories.py` et `merge_pdf.py` écrivent sur `out_dir / f"{stem_name}..."` en écrasant tout fichier déjà créé au cours de la même exécution si deux catégories partagent le même `cat_stem`.

---

## Comportement attendu

1. `merge_pdf.py` lit directement `pdf_dir` (`{job_dir}/pdf`) sans étape `flatten` intermédiaire : les stems des fichiers `.pdf` produits par `convert.py` correspondent exactement aux stems de `category_groups.json` produits par `page_stem()`.
2. Les articles contenant des espaces (`"Assault Rifle"`) ou des caractères Unicode (`"Épée"`) sont correctement inclus dans le PDF de leur catégorie (et non dans `Misc.pdf`).
3. `cat_stem()` normalise proprement les suffixes de découpage (`(part N)` → `_partN`), conserve toujours le suffixe `_partN` même lorsque la base est tronquée à 80 caractères, et évite les underscores finaux.
4. En cas de collision résiduelle entre deux catégories distinctes aboutissant au même `cat_stem`, un suffixe numérique (`_2`, `_3`) est ajouté pour qu'aucun fichier de catégorie n'en écrase un autre.

---

## Cause probable

1. `flatten()` (`scripts/run.py:75-97`) est la traduction littérale en Python de l'ancien script `scripts/flatten.sh` supprimé lors du nettoyage documenté dans `CHANGELOG.md:72-76`. Lors de l'unification des règles de nommage dans `wiki_names.py`, `flatten()` a été oublié entre `convert.py` et `merge_pdf.py`.
2. `cat_stem()` a été écrit sans tenir compte des suffixes ` (part N)` introduits par `pack_files.py`.

---

## Zones concernées

- `scripts/run.py` : lignes 75-97 (`flatten()`), ligne 161 (`flat_dir`), lignes 188, 192, 396, 404-405.
- `server.py` : lignes 384-386 (`purge` incluant `jd / "flat"`), ligne 574 (`splits` dans `_packing_preview`).
- `scripts/wiki_names.py` : lignes 30-34 (`cat_stem()`).
- `scripts/merge_pdf.py` : lignes 26-30, 70-76, 84-98.
- `scripts/export_categories.py` : lignes 212-227.
- `tests/test_merge_pdf.py`, `tests/test_wiki_names.py`, `tests/test_export_categories.py`.

---

## Points d'impact

- **Appelants de `flatten()` :** uniquement `scripts/run.py:404` (aucun test ni autre script ne l'appelle).
- **Appelants de `cat_stem()` :** `scripts/export_categories.py:216`, `scripts/merge_pdf.py:75`, `tests/test_wiki_names.py:19-26`.
- **Tests existants à vérifier/adapter :**
  - `tests/test_wiki_names.py:19-22` vérifie `wiki_names.cat_stem("Weapons & Gadgets") == "Weapons___Gadgets"` et `len(wiki_names.cat_stem("a" * 200)) == 80` — ces assertions doivent continuer à passer.
  - `tests/test_merge_pdf.py` passe déjà un dossier de PDF à `merge_pdf.py` (l'interface CLI `merge_pdf.py <pdf_dir> <out_dir> [max_pages] [groups.json]` ne change pas).
- **Stockage existant :** conserver `jd / "flat"` dans `server.py:384-386` (`purge`) ne gêne pas (`if t.exists(): shutil.rmtree`), ce qui permet de nettoyer d'anciens jobs ayant encore un dossier `flat/`.

---

## Plan d'action

1. **Supprimer le passage par `flatten()` dans `scripts/run.py` :**
   - Supprimer la fonction `flatten()` (`scripts/run.py:75-97`) et l'import inutilisé `unicodedata` (`scripts/run.py:18`).
   - À l'étape 5 (`scripts/run.py:402-405`), passer directement `str(pdf_dir)` à `merge_pdf.py` au lieu de `str(flat_dir)`.
2. **Préserver les suffixes `(part N)` dans `scripts/wiki_names.py::cat_stem()` :**
   - Détecter si `cat` se termine par ` (part <N>)` ou `_part<N>` (ex. regex `r"\s*\(part\s+(\d+)\)\s*$"`).
   - Normaliser ce suffixe en `f"_part{n}"` et tronquer la base à `80 - len(suffix)` caractères avant d'y concaténer `suffix`, afin que `len(cat_stem(cat)) <= 80` reste garanti tout en rendant impossible l'écrasement entre `part 1` et `part 2` et en unifiant le nommage avec `merge_pdf.py` (`Weapons_part1.md`, `Weapons_part1.pdf`).
3. **Empêcher l'écrasement en cas de collision de `cat_stem` dans `scripts/export_categories.py` et `scripts/merge_pdf.py` :**
   - Tenir un ensemble `used_stems: set[str]` au cours de la boucle d'export ; si `stem_name` a déjà été utilisé par une autre catégorie dans la même exécution, numéroter `f"{stem_name[:76]}_{i}"`.
4. **Ajouter les tests de non-régression :**
   - Dans `tests/test_merge_pdf.py` : tester la fusion d'articles ayant des espaces et des accents dans leur titre (`"Assault Rifle"`, `"Épée"`) et vérifier qu'ils atterrissent dans `Weapons.pdf` et non dans `Misc.pdf`.
   - Dans `tests/test_wiki_names.py` et `tests/test_export_categories.py` : tester `cat_stem` sur deux parties d'un nom de catégorie de 90 caractères (`"... (part 1)"` et `"... (part 2)"`) et vérifier que les deux fichiers `.md` distincts sont produits.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas modifier `wiki_names.page_stem()` (sinon tous les jobs existants ayant déjà extrait `html/*.html` et `categories.json` deviendraient incompatibles).

---

## Contraintes

- Conserver la compatibilité avec les tests existants de `tests/test_wiki_names.py` (`cat_stem("Weapons & Gadgets") == "Weapons___Gadgets"`, longueur max `<= 80`).
- Conserver `jd / "flat"` dans la liste de nettoyage de `server.py::purge` et `run.py` (`clean`/`rerender`) pour purger d'éventuels anciens dossiers `flat/`.

---

## Dépendances

- Indépendant en code ; complète directement `PLAN-UX-01` pour que l'export PDF de bout en bout soit fonctionnel.

---

## Critères d'acceptation

1. Un wiki contenant les articles `"Pistol"`, `"Assault Rifle"` et `"Épée"` dans la catégorie `"Weapons"` produit un unique fichier `Weapons.pdf` contenant les 3 articles (et aucun `Misc.pdf`).
2. Deux tranches d'une catégorie de plus de 80 caractères (`"<85 chars> (part 1)"` et `"<85 chars> (part 2)"`) produisent deux fichiers distincts `..._part1.md` et `..._part2.md` sans écrasement.
3. Aucun dossier `flat/` n'est créé lors de l'étape 5.
4. `python -m pytest` passe sans erreur.

---

## Vérification

1. Exécuter `pytest tests/test_wiki_names.py tests/test_merge_pdf.py tests/test_export_categories.py`.
2. Rejouer le scénario d'intégration avec des titres multi-mots et accentués en export `pdf,md,txt` et vérifier que les mêmes articles figurent dans `Weapons.pdf`, `Weapons.md` et `Weapons.txt`.

---

## Risques

- Très faible : `convert.py` écrit déjà à plat dans `pdf_dir` (`out_dir / f.with_suffix(".pdf").name`), donc `pdf_dir` ne contient jamais de sous-dossiers.
