# [P2] PLAN-UX-09 — Titre `<h1>` dupliqué dans tous les exports Markdown, pied de page `Categories:` non nettoyé et `NAMESPACES` ignoré à l'extraction

- **Type :** bug / fonctionnel / qualité des exports
- **Preuve :**
  - *Confirmé à l'exécution* :
    - Exécution de `extract.wrap_html("Sword", "<p>A sharp blade.</p>", ["Weapons", "Melee"])` suivi de `export_categories._render_md()` : le Markdown produit est :
      ```markdown
      # Sword

      # Sword

      A sharp blade.

      Categories: Weapons, Melee
      ```
      Le titre `# Sword` est écrit **deux fois de suite**, et la ligne de bruit `Categories: Weapons, Melee` n'est pas supprimée par `clean_html.py`.
    - Exécution de `merge_pdf.py` : le paramètre `max_pages` (`scripts/merge_pdf.py:84`) teste `len(files) <= max_pages` (nombre d'articles HTML/PDF) au lieu du nombre réel de pages PDF (`len(pdf.pages)`).
  - *Déduit du code* :
    - `scripts/extract.py:201, 208` (`wrap_html` écrit `<h1>{title}</h1>` sans `html.escape(title)` et `<div style="...">Categories: ...</div>` sans `class="catlinks"`)
    - `scripts/clean_html.py:13-22, 34-43` (`NOISE_SELECTORS` cherche `.catlinks`, et `title_text(soup)` lit `h1` sans le retirer du DOM)
    - `scripts/export_categories.py:135-138, 204-206` (`_render_md` convertit `body` — qui contient encore `<h1>` — en Markdown puis préfixe une seconde fois `f"# {title}\n\n{content}"`)
    - `scripts/extract.py:34` (`KEEP_NS = {"0"}` et `NS_MW = "http://www.mediawiki.org/xml/export-0.11/"` sont codés en dur : le paramètre `NAMESPACES` passé à l'étape 1 dans `run.py:222` n'est jamais transmis à `extract.py`, qui jette tout namespace != `"0"`, et tout wiki MediaWiki exportant en schéma `export-0.10` produit 0 page)
    - `scripts/merge_pdf.py:84-96` (`if len(files) <= max_pages:` compte le nombre de fichiers d'articles au lieu du nombre de pages PDF)

---

## Problème

Quatre défauts dans la chaîne d'extraction et d'export dégradent la qualité et l'exactitude des fichiers générés pour NotebookLM :

### 1. Tous les articles des fichiers `.md` ont leur titre `# Title` en double et conservent le pied de page `Categories:`
- Dans `scripts/extract.py:201-208`, `wrap_html(title, body_html, categories)` enveloppe chaque article avec :
  - `<h1>{title}</h1>` en tête du `<body>` ;
  - `<div style="margin-top:2em;..."><small>Categories: ...</small></div>` en pied de page, **sans la classe `catlinks`**.
- Lors de l'export Markdown (`scripts/export_categories.py:135-138, 204-206`) :
  - `_ch.clean_soup(soup)` supprime `.catlinks`, mais comme le `<div>` de `wrap_html` n'a pas la classe `catlinks`, le pied de page `Categories: ...` reste dans tous les articles `.md` et `.txt`.
  - `_ch.title_text(soup)` extrait le texte du `<h1>`, mais **laisse le nœud `<h1>` dans le `<body>`**.
  - `_md_lib(str(body), heading_style="ATX")` convertit ce `<h1>` en `# {title}`, puis la ligne 138 retourne `f"# {title}\n\n{content}"`.
  - **100 % des articles générés en Markdown commencent donc par `# Titre\n\n# Titre`** (en contradiction directe avec `PLAN.md` §C : *"Strictly 1 `# Article Title` per page"*).

### 2. `extract.py` ignore le paramètre utilisateur `NAMESPACES` et plante sur les schémas XML MediaWiki `!= 0.11`
- Dans l'interface web (`server.py:1257, 1361`) et `scripts/run.py:173, 222`, l'utilisateur peut configurer `Namespaces` (ex. `0, 4, 14` pour inclure les pages Projet ou Catégorie). `run.py` passe bien `--namespaces` à `wikiteam3dumpgenerator` à l'étape 1.
- Mais à l'étape 2, `scripts/extract.py:34` code en dur **`KEEP_NS = {"0"}`** ! Toutes les pages des namespaces autres que `0` téléchargées à l'étape 1 sont silencieusement ignorées à la ligne 222 (`if ns not in KEEP_NS: elem.clear(); continue`).
- De plus, `scripts/extract.py:33` code en dur `NS_MW = "http://www.mediawiki.org/xml/export-0.11/"`. Les wikis MediaWiki légèrement plus anciens exportent avec `export-0.10` : `extract.py` ne matche alors aucune balise `<page>` et produit `0 HTML files`.

### 3. Absence d'échappement HTML du titre dans `wrap_html`
Dans `scripts/extract.py:205-208`, `<title>{title}</title>` et `<h1>{title}</h1>` injectent `title` sans `html.escape(title)`. Un titre d'article contenant `<` ou `&` produit du HTML mal formé.

### 4. `merge_pdf.py` découpe selon le nombre d'articles (`len(files)`) au lieu du nombre de pages PDF
Dans `scripts/merge_pdf.py:84`, le paramètre `max_pages` (500 par défaut) est comparé à `len(files)` (le nombre d'articles unitaires) au lieu de la somme des pages PDF (`len(src.pages)`). Or 400 articles de 3 pages font 1 200 pages PDF dans un seul fichier, dépassant la limite de pages par PDF de NotebookLM.

---

## Impact utilisateur

- **Modéré à Majeur (P2) :**
  - Les fichiers Markdown (`.md`) contiennent tous un doublon `# Titre` / `# Titre` et des pieds de page `Categories:` parasites sur chaque article.
  - Le champ `Namespaces` proposé dans l'UI et les paramètres par défaut ne fonctionne pas (tout namespace hors `0` est perdu).
  - Les PDF de catégories contenant de longs articles peuvent dépasser la limite de 500 pages de NotebookLM.

---

## Comportement actuel

1. `_render_md` génère deux fois `# {title}` par article et conserve `Categories: ...`.
2. `extract.py` filtre uniquement `KEEP_NS = {"0"}` et le namespace XML `export-0.11`.
3. `merge_pdf.py` découpe les PDF par lots de `max_pages` fichiers d'articles au lieu de `max_pages` pages PDF.

---

## Comportement attendu

1. Chaque article dans un fichier `.md` commence par un unique `# {title}` et ne contient pas le pied de page `Categories: ...`.
2. `extract.py` lit `NAMESPACES` (depuis la variable d'environnement `NAMESPACES`, par défaut `"0,14"` en filtrant `"14"` uniquement pour les articles si non demandé ou en acceptant tous les namespaces demandés par l'utilisateur hors catégories vides) et détecte les balises XML par leur nom local (`page`, `title`, `ns`, `revision`, `text`) quelle que soit la version `export-0.x` du schéma MediaWiki.
3. `wrap_html` échappe `title` et les noms de catégories avec `html.escape`, et ajoute `class="catlinks"` sur le `<div>` des catégories.
4. `merge_pdf.py` comptabilise le nombre réel de pages PDF (`len(src.pages)`) lors de la fusion et ouvre une nouvelle partie (`_part2.pdf`, etc.) dès que l'ajout d'un article ferait dépasser `max_pages` pages PDF.

---

## Cause probable

1. Lors du remplacement du parseur maison par `markdownify` dans `export_categories.py` (`PLAN.md` §C), l'auteur a conservé le préfixe manuel `f"# {title}\n\n{content}"` alors que `markdownify` convertissait déjà le `<h1>` présent dans `<body>`.
2. `KEEP_NS = {"0"}` et `export-0.11` ont été écrits pour un wiki unique lors du prototypage initial.

---

## Zones concernées

- `scripts/extract.py` : lignes 19, 33-34, 200-224.
- `scripts/clean_html.py` : lignes 34-43.
- `scripts/export_categories.py` : lignes 135-138, 202-206.
- `scripts/merge_pdf.py` : lignes 58-98.
- `tests/test_export_categories.py`, `tests/test_extract_fallback.py`, `tests/test_merge_pdf.py`.

---

## Points d'impact

- **Tests existants :**
  - `tests/test_export_categories.py` : vérifier qu'un HTML contenant `<h1>Title</h1>` ne produit qu'un seul `# Title` dans le `.md`.
  - `tests/test_merge_pdf.py:42-50` (`test_splits_when_exceeding_max_pages`) : dans ce test, chaque PDF unitaire fait 1 page (`make_pdf` crée 1 page) et `max_pages=2` avec 5 articles → que l'on compte en pages PDF ou en articles de 1 page, 5 pages avec `max_pages=2` donne toujours 3 fichiers (`Big_part1.pdf`, `Big_part2.pdf`, `Big_part3.pdf`), donc le test existant continuera de passer tout en gérant désormais les articles multi-pages !

---

## Plan d'action

1. **Supprimer le doublon `<h1>` et nettoyer `Categories:` (`scripts/extract.py`, `scripts/export_categories.py`) :**
   - Dans `scripts/extract.py:201-208`, utiliser `html.escape(title)` et ajouter `class="catlinks"` au `<div ...>` du pied de page des catégories.
   - Dans `scripts/clean_html.py:13-22`, ajouter un filtre ou dans `scripts/export_categories.py:204-205`, après `title = _ch.title_text(soup, fallback=stem)`, supprimer le premier `<h1>` du `soup` (`h1 = soup.find("h1"); if h1: h1.decompose()`) ainsi que tout `<div style=...>` final commençant par `"Categories:"` (pour les fichiers HTML déjà extraits avant ce correctif).
2. **Prendre en compte `NAMESPACES` et tous les schémas XML MediaWiki dans `scripts/extract.py` :**
   - Construire `KEEP_NS` à partir de `os.environ.get("NAMESPACES", "0")` (en gardant par défaut `"0"`, et en incluant tout namespace explicitement demandé par l'utilisateur ; si `"14"` fait partie de la valeur par défaut `"0, 14"` uniquement pour `wikiteam3`, conserver `"0"` par défaut et ajouter les autres namespaces demandés hors `"14"` sauf si explicitement voulu).
   - Remplacer le préfixe fixe `{http://www.mediawiki.org/xml/export-0.11/}` par une fonction helper `_local(tag: str) -> str` (`tag.rsplit("}", 1)[-1]`) afin de supporter `export-0.10`, `export-0.11` et un XML sans namespace.
3. **Découper les PDF selon le nombre réel de pages dans `scripts/merge_pdf.py` (lignes 58-98) :**
   - Lors de la fusion d'une catégorie, accumuler les pages dans un `pikepdf.Pdf.new()` courant en suivant `current_pages += len(src.pages)` ; si `current_pages > 0 and current_pages + len(src.pages) > max_pages`, sauvegarder la tranche courante et ouvrir une nouvelle tranche (un article unique faisant déjà plus de `max_pages` pages à lui seul est conservé dans sa propre tranche sans être perdu).
4. **Ajouter les tests unitaires :**
   - Dans `tests/test_export_categories.py` : vérifier que le `.md` produit à partir d'un HTML issu de `wrap_html` contient exactement une seule occurrence de `# Title` et ne contient pas `Categories:`.
   - Dans `tests/test_merge_pdf.py` : vérifier que 2 articles de 3 pages chacun avec `max_pages=4` sont découpés en `Cat_part1.pdf` (3 pages) et `Cat_part2.pdf` (3 pages).

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas réécrire le convertisseur Markdown ni changer le format des séparateurs entre articles.

---

## Contraintes

- Conserver la compatibilité avec les fichiers HTML déjà extraits sur le disque (qui ont `<h1>` et `<div><small>Categories: ...</small></div>` sans `class="catlinks"`).

---

## Dépendances

- Aucune dépendance bloquante (peut être exécuté en parallèle ou après les plans P0/P1).

---

## Critères d'acceptation

1. Un fichier `.md` exporté par `export_categories.py` à partir d'un HTML généré par `extract.py` contient exactement un `# <Titre>` par article et aucune ligne `Categories:`.
2. Un dump XML utilisant le namespace `http://www.mediawiki.org/xml/export-0.10/` est extrait sans erreur par `extract.py`.
3. `merge_pdf.py` découpe une catégorie dès que le cumul des pages PDF dépasse `max_pages`.
4. `python -m pytest` passe intégralement.

---

## Vérification

1. Exécuter `pytest tests/test_export_categories.py tests/test_extract_fallback.py tests/test_merge_pdf.py`.

---

## Risques

- Aucun risque identifié.
