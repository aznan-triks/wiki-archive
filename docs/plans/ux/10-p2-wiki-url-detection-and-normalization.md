# [P2] PLAN-UX-10 — Détection d'URL MediaWiki (`detect_wiki.py`) en échec sur les URLs copiées avec accents (`%C3%89`), sous-pages ou sans `https://`

- **Type :** bug / fonctionnel / UX
- **Preuve :**
  - *Confirmé à l'exécution* :
    1. `detect_wiki.extract_base("https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e")` retourne `"https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e"` (ne retire ni `%C3%89p%C3%A9e` ni `/wiki/` car `last[0]` vaut `'%'`, donc `last[0].isupper()` vaut `False`). La sonde cherche ensuite `/wiki/%C3%89p%C3%A9e/api.php`, échoue en 404, et rejette le wiki avec `"ERROR: this site does not appear to be a MediaWiki wiki"`.
    2. `detect_wiki.extract_base("https://finalstandtwo.fandom.com/wiki/Weapons/Pistols")` retourne `"https://finalstandtwo.fandom.com/wiki/Weapons"` (ne retire que `/Pistols` et laisse `/wiki/Weapons`).
    3. `wiki_names.wiki_slug("wiki.play.eco/en/Eco_Wiki")` (URL collée sans `https://`) retourne `"unknown-wiki"` car `urlparse("wiki.play.eco/...").hostname` vaut `None`.
  - *Déduit du code* :
    - `scripts/detect_wiki.py:67-93` (`extract_base` n'appelle pas `urllib.parse.unquote`, ne coupe pas sur le segment `"wiki"` / `"index.php"` lorsqu'il y a une sous-page, et n'ajoute pas `https://` si l'URL n'a pas de schéma)
    - `scripts/wiki_names.py:37-40` (`wiki_slug` appelle `urlparse(url).hostname` sans normaliser le schéma `https://`)
    - `server.py:1346` (`<input type="text" id="f-url" placeholder="https://wiki.example.com/..." />` accepte toute chaîne sans normalisation du schéma)

---

## Problème

Le README (`README.md:57`) et le placeholder de l'interface (`server.py:1346`) promettent à l'utilisateur :
> *"Paste any URL from the wiki (homepage, article, etc.) — the script automatically detects the API."*

Or, dans trois cas très fréquents lorsqu'un utilisateur copie-colle une URL depuis son navigateur, la détection échoue :

### 1. URL d'article contenant un caractère accentué ou non-ASCII encodé en `%XX`
Quand un utilisateur francophone (ou non-anglophone) copie l'URL d'un article commençant par une lettre accentuée depuis la barre d'adresse de Chrome/Firefox/Edge (ex. `https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e` ou `https://.../wiki/%C3%80_propos`), le navigateur fournit l'URL encodée en pourcentage.
Dans `scripts/detect_wiki.py:81` :
```python
if "_" in last or (last and last[0].isupper() and "." not in last):
    parts = parts[:-1]
```
Comme `last` commence par `'%'` (et non par une majuscule) et ne contient pas `'_'` s'il s'agit d'un seul mot, la condition est `False` !
`extract_base()` ne retire ni le titre de l'article ni `/wiki/`, et `detect()` teste des chemins absurdes comme `.../wiki/%C3%89p%C3%A9e/api.php` avant d'échouer avec :
> `ERROR: this site does not appear to be a MediaWiki wiki. Likely cause: the site is a modern web application (SPA)...`

### 2. URL de sous-page (`/wiki/Catégorie/Sous-page` ou `/wiki/Weapons/Pistols`)
De nombreux wikis utilisent des sous-pages MediaWiki contenant un `/`. Comme `extract_base()` ne retire qu'un seul segment (`parts = parts[:-1]`), `https://example.fandom.com/wiki/Weapons/Pistols` devient `https://example.fandom.com/wiki/Weapons`, conservant `/wiki/Weapons` dans la base et faisant échouer la détection de `/api.php` sur les wikis où le script path est à la racine ou dans `/w`.

### 3. URL collée sans schéma `https://` (ex. `wiki.play.eco/en/Eco_Wiki`)
Si l'utilisateur saisit ou colle `wiki.play.eco` ou `wiki.play.eco/en/Eco_Wiki` sans `https://` :
- `wiki_names.wiki_slug()` renvoie `"unknown-wiki"` ;
- `detect_wiki.extract_base()` renvoie `"://"` et échoue immédiatement.

---

## Impact utilisateur

- **Modéré (P2) — Heuristique de Nielsen n° 5 (Prévention des erreurs) :**
  - L'utilisateur colle une URL parfaitement valide d'un wiki MediaWiki (article accentué, sous-page ou domaine sans `https://`) et reçoit un diagnostic erroné affirmant que le site est une SPA non supportée.

---

## Comportement actuel

1. `extract_base("https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e")` → `"https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e"`.
2. `extract_base("https://example.com/wiki/A/B")` → `"https://example.com/wiki/A"`.
3. `wiki_slug("wiki.play.eco")` → `"unknown-wiki"`.

---

## Comportement attendu

1. Si l'URL ne commence pas par `http://` ou `https://`, préfixer automatiquement `https://` (dans `wiki_names.py`, `detect_wiki.py` et `server.py`).
2. Dans `extract_base(url)` :
   - Décoder chaque segment avec `urllib.parse.unquote` pour inspecter ses caractères réels (`%C3%89p%C3%A9e` → `Épée`, où `'É'.isupper()` est `True`).
   - Si l'un des marqueurs d'article MediaWiki (`"wiki"`, `"index.php"`, `"load.php"`, `"api.php"`) apparaît dans `parts`, tronquer `parts` immédiatement **avant** la première occurrence de ce marqueur (ce qui gère d'un coup `/wiki/Épée`, `/wiki/Weapons/Pistols`, `/w/index.php/Main_Page`, `/en/wiki/Sub/Page` → base `/en` ou `/w` ou `""`).
   - Sinon (ex. `https://wiki.play.eco/en/Eco_Wiki` où le préfixe est une langue `/en/`), appliquer l'heuristique de titre d'article sur les segments décodés en fin de chemin.

---

## Cause probable

`extract_base()` a été écrit en testant uniquement deux URLs simples en anglais (`https://wiki.play.eco/en/Eco_Wiki` et `https://finalstandtwo.fandom.com/wiki/Final_Stand_2_Wiki`) sans tester les titres encodés en `%XX`, les sous-pages avec `/` ni les URLs sans schéma.

---

## Zones concernées

- `scripts/detect_wiki.py` : lignes 67-93 (`extract_base`).
- `scripts/wiki_names.py` : lignes 37-40 (`wiki_slug`).
- `server.py` : ligne 336 (`JobManager.create` : normaliser `url.strip()` avec `https://` si absent).
- `tests/test_wiki_names.py`.

---

## Points d'impact

- **Appelants :** `scripts/run.py:211` (appelle `detect_wiki.py`), `server.py` et `scripts/run.py:164` (appellent `wiki_slug`).
- **Tests existants :** `tests/test_wiki_names.py:29-39` (continueront de passer ; ajouter les nouveaux cas).

---

## Plan d'action

1. **Normaliser les URLs sans schéma dans `scripts/wiki_names.py` et `server.py` :**
   - Dans `wiki_names.wiki_slug(url: str)` : faire `u = url.strip()`, et si `u` est non vide et `"://" not in u`, préfixer `"https://" + u` avant `urlparse(u)`.
   - Dans `server.py::JobManager.create()` : normaliser `url = url.strip()`, et si `url and "://" not in url`, `url = "https://" + url`.
2. **Fiabiliser `extract_base(url: str)` dans `scripts/detect_wiki.py` (lignes 67-93) :**
   - Importer `unquote` depuis `urllib.parse`.
   - Si `"://" not in url`, préfixer `"https://"`.
   - Découper `parts = [p for p in parsed.path.split("/") if p]`.
   - Si l'un des segments appartient à `_ARTICLE_PREFIXES` (`{"wiki", "index.php", "load.php", "api.php"}`), couper `parts` à l'indice de ce segment (`idx = next(i for i, p in enumerate(parts) if p.lower() in _ARTICLE_PREFIXES); parts = parts[:idx]`).
   - Sinon, retirer le dernier segment si `unquote(parts[-1])` ressemble à un titre d'article (`"_" in last_decoded or (last_decoded and last_decoded[0].isupper() and "." not in last_decoded)`).
3. **Ajouter des tests unitaires dans `tests/test_wiki_names.py` :**
   - Tester `extract_base` sur :
     - `"https://fr.wikipedia.org/wiki/%C3%89p%C3%A9e"` → `"https://fr.wikipedia.org"`
     - `"https://finalstandtwo.fandom.com/wiki/Weapons/Pistols"` → `"https://finalstandtwo.fandom.com"`
     - `"https://wiki.play.eco/en/Eco_Wiki"` → `"https://wiki.play.eco/en"`
     - `"https://wiki.example.com/w/index.php/Main_Page"` → `"https://wiki.example.com/w"`
     - `"wiki.play.eco/en/Eco_Wiki"` → `"https://wiki.play.eco/en"`
   - Tester `wiki_slug("wiki.play.eco/en/Eco_Wiki") == "wiki.play.eco"`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas effectuer de requêtes réseau supplémentaires lors de `extract_base` (cette fonction doit rester pure et instantanée).

---

## Contraintes

- Préserver le comportement exact sur les wikis multi-langues comme `https://wiki.play.eco/en/Eco_Wiki` (qui doit retourner `"https://wiki.play.eco/en"`).

---

## Dépendances

- Aucune dépendance avec les autres plans.

---

## Critères d'acceptation

1. `extract_base` extrait correctement la base pour les URLs contenant `%XX`, les sous-pages `/wiki/A/B`, les chemins `/w/index.php/Page`, les préfixes de langue `/en/Page`, et les URLs sans `https://`.
2. `wiki_slug("wiki.play.eco/en/Eco_Wiki")` retourne `"wiki.play.eco"`.
3. `python -m pytest` passe intégralement.

---

## Vérification

1. Exécuter `pytest tests/test_wiki_names.py`.

---

## Risques

- Très faible : si un wiki est hébergé sur un sous-dossier qui s'appelle littéralement `/wiki/` tout en ayant son `api.php` dans `/wiki/api.php` (ex. `https://awakening.wiki/wiki/api.php`), `detect()` dans `detect_wiki.py:100` teste déjà `[base, f"{base}/w", f"{base}/wiki", origin, f"{origin}/w", f"{origin}/wiki"]` ! Donc couper avant `/wiki/` dans `extract_base` permet justement à `detect()` de tester à la fois `origin`, `origin/w` et `origin/wiki` sans être pollué par `/Weapons/Pistols` ou `/%C3%89p%C3%A9e`.
