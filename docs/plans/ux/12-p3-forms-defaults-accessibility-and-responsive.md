# [P3] PLAN-UX-12 — Défauts de formulaires, de valeurs par défaut (`Plus` vs `50`), d'accessibilité (`<label>`, `delay=0`) et d'adaptation responsive

- **Type :** incohérence / UX / UI / finition
- **Preuve :**
  - *Confirmé à l'exécution* :
    1. `GET /api/settings` sur une installation fraîche retourne `{"max_files": 50, "notebooklm_plan": "plus", ...}` (`server.py:72, 88`). La page `⚙ Default settings` affiche simultanément **`Plus — 100 sources / notebook`** et **`Max files: 50`** (qui est la limite du plan **Free**).
    2. Dans `jsdom`, saisir `0` dans `#f-delay` (qui a pourtant `min="0"` à `server.py:1367`) et appeler `collectParams()` (`server.py:1395`) retourne `delay: 0.5` à cause de `parseFloat(...) || 0.5`.
    3. Activer puis quitter le mode `Manage` (`toggleManageMode()`, `server.py:1138-1152`) laisse `<div id="bulk-bar" class="bulk-bar"></div>` avec sa bordure et son padding visibles en bas de la sidebar.
  - *Déduit du code* :
    - `server.py:72, 88` (`DEFAULTS["max_files"] = 50` mais `load_settings()` initialise `data.setdefault("notebooklm_plan", "plus")`)
    - `server.py:1054-1058` (`loadPrefs()` et `savePrefs()` sont du code mort jamais appelé)
    - `server.py:1147-1153` (`renderBulkBar()` met `bar.className = "bulk-bar"` quand `manageMode` est vrai mais ne remet pas `bar.className = ""` quand `manageMode` est faux)
    - `server.py:1193-1215` (`requestDelete` désélectionne le job supprimé mais `Undo` ne restaure pas la sélection, et `cleanable` dans `renderBulkBar` compte encore les jobs en attente de suppression dans `pendingDel`)
    - `server.py:1262, 1283-1284, 1370-1379` (les cases `.opt-check` utilisent `<div class="opt-group opt-check"><input type="checkbox"><span>...</span></div>` au lieu de `<label>`, empêchant de cliquer sur le texte pour cocher/décocher)
    - `server.py:1321, 1395` (`parseFloat(...) || 0.5` transforme `0` en `0.5`)
    - `server.py:1346` (`#f-url` n'écoute pas la touche `Enter`)
    - `server.py:805-882` (aucune règle `@media` pour les fenêtres étroites / écran partagé côte à côte avec NotebookLM)
    - `README.md:82-115` (documente d'anciens boutons qui n'existent plus : `Create and run`, `Regenerate rendering`, `Restart`)

---

## Problème

Ce plan regroupe les défauts de cohérence des formulaires, d'ergonomie clavier/souris, de mise en page responsive et d'alignement de la documentation :

1. **Contradiction entre le plan NotebookLM (`Plus — 100`) et `Max files` (`50`) par défaut (`server.py:72, 88`) :**
   `DEFAULTS["max_files"]` vaut `50` (plan Free), mais `load_settings()` injecte `"notebooklm_plan": "plus"` (100 sources). Dans `⚙ Default settings`, l'utilisateur voit donc le menu déroulant sur `Plus — 100 sources` et le champ numérique à côté sur `50`.
2. **Impossibilité de régler `Delay` à `0` (`server.py:1321, 1395`) :**
   Le champ `Delay between API requests (s)` autorise `min="0"` (utile pour un wiki local ou auto-hébergé), mais `parseFloat(document.getElementById("f-delay")?.value) || 0.5` évalue `0 || 0.5` à `0.5`, écrasant silencieusement la saisie `0` de l'utilisateur.
3. **Cibles de clic minuscules sur toutes les cases à cocher d'options (`.opt-check`, Loi de Fitts) :**
   Contrairement aux cases de formats (`.fmt-check` qui utilise `<label>`), les 5 cases d'options (`Avoid duplicates`, `Include images`, `New full dump`, `Re-render output`, `Skip Internet Archive`) utilisent `<div class="opt-group opt-check"><input type="checkbox" .../><span>...</span></div>`. Cliquer sur le libellé texte ne coche pas la case : il faut viser le carré de `14px × 14px`.
4. **Absence de validation par la touche `Entrée` dans le champ URL (`#f-url`, `server.py:1346`) :**
   Après avoir collé l'URL d'un wiki dans `#f-url`, appuyer sur `Enter` ne lance pas l'action principale (`scanFromForm()`).
5. **Résidu visuel de la barre `Manage` et restauration incomplète sur `Undo` (`server.py:1149, 1193-1215`) :**
   - Quitter le mode `Manage` vide `bar.innerHTML` mais laisse `bar.className = "bulk-bar"`, affichant une boîte vide avec bordure et padding en bas de la sidebar.
   - Pendant les 5 secondes du toast `Undo`, le compteur `Clean up stopped/errored (N)` inclut encore les jobs déjà masqués dans `pendingDel`, et cliquer sur `Undo` ne re-sélectionne pas le job qui était affiché.
   - `loadPrefs()` / `savePrefs()` (`server.py:1054-1058`) est du code mort inutilisé.
6. **Absence d'adaptation aux fenêtres étroites (`< 768px`) :**
   Lorsqu'un utilisateur place la fenêtre Wiki Archive sur une moitié d'écran côte à côte avec NotebookLM sur l'autre moitié (`~650–750px` de large), la sidebar fixe de `270px` et la grille `.opts-grid` à 2 colonnes compriment les champs et tronquent les libellés.
7. **Documentation `README.md` obsolète sur les boutons de l'interface (`README.md:82-115`) :**
   Le `README.md` mentionne encore les boutons **`Create and run`**, **`Regenerate rendering`** et **`Restart`**, qui ont été remplacés par **`🔍 Step 1 — Scan the wiki`**, **`Do everything at once`**, **`Re-render output`**, **`⏸ Pause`** et **`▶ Resume`**.

---

## Impact utilisateur

- **Mineur à Modéré (P3/P4) :**
  - Incohérence visuelle immédiate dans `⚙ Default settings` (`Plus — 100` vs `50`).
  - Frustration au clic sur les cases à cocher et à la touche `Entrée` sur le champ URL.
  - Documentation `README.md` décalée par rapport aux boutons réellement présents à l'écran.

---

## Comportement actuel

1. `load_settings()` retourne `notebooklm_plan: "plus"` avec `max_files: 50`.
2. `delay = 0` est forcé à `0.5`.
3. Cliquer sur le texte d'une option `.opt-check` ne coche pas la case.
4. Appuyer sur `Enter` dans `#f-url` ne fait rien.
5. Quitter `Manage` laisse `.bulk-bar` visible à vide.
6. Aucune `@media` query n'adapte la grille sous `768px`.

---

## Comportement attendu

1. `load_settings()` déduit le plan par défaut de `max_files` (`"free"` pour `50`, `"plus"` pour `100`, `"pro"` pour `300`, `"custom"` sinon) afin que le plan et le nombre de fichiers soient toujours cohérents.
2. `delay = 0` est conservé tel quel (`const d = parseFloat(...); Number.isFinite(d) && d >= 0 ? d : 0.5`).
3. Les conteneurs `.opt-check` sont des `<label class="opt-group opt-check">` : cliquer n'importe où sur la ligne coche/décoche la case.
4. Appuyer sur `Enter` dans `#f-url` déclenche `scanFromForm()`.
5. Quitter `Manage` remet `bar.className = ""` ; `Undo` restaure le job précédemment sélectionné ; `loadPrefs`/`savePrefs` est supprimé.
6. Un bloc `@media (max-width: 768px)` passe `.opts-grid` et `.fmt-grid` sur 1 colonne et réduit la largeur de la sidebar ou empile la navigation proprement.
7. `README.md` reflète fidèlement les boutons actuels de l'interface.

---

## Cause probable

Évolutions successives de l'interface (ajout des plans NotebookLM, passage au workflow en 2 étapes Scan/Generate, ajout du mode Manage) sans passe de nettoyage final sur les détails de formulaire et la documentation.

---

## Zones concernées

- `server.py` :
  - lignes 86-90 (`load_settings`)
  - lignes 805-882 (ajout `@media (max-width: 768px)`)
  - lignes 1054-1058 (suppression de `loadPrefs`/`savePrefs`)
  - lignes 1147-1215 (`renderBulkBar`, `cleanupStoppedErrored`, `requestDelete`)
  - lignes 1262, 1283-1284, 1321, 1346, 1370-1379, 1395 (labels `.opt-check`, `delay=0`, `onkeydown` sur `#f-url`)
- `README.md` : lignes 82-115.
- `tests/test_server_config.py`.

---

## Points d'impact

- **Tests existants :** `tests/test_server_config.py` (aucune casse ; ajouter un test vérifiant la cohérence `notebooklm_plan` / `max_files` dans `load_settings()`).

---

## Plan d'action

1. **Aligner `notebooklm_plan` et `max_files` dans `server.py:86-90` :**
   - Dans `load_settings()`, calculer le défaut de `notebooklm_plan` à partir de `data["max_files"]` (`{50: "free", 100: "plus", 300: "pro"}.get(data.get("max_files"), "custom")`).
2. **Corriger `delay = 0`, les `<label class="opt-group opt-check">` et la touche `Enter` dans `server.py` :**
   - Dans `saveSettings()` (ligne 1321) et `collectParams()` (ligne 1395), remplacer `parseFloat(...) || 0.5` par `((v) => Number.isFinite(v) && v >= 0 ? v : 0.5)(parseFloat(...))`.
   - Remplacer `<div class="opt-group opt-check">...</div>` par `<label class="opt-group opt-check">...</label>` dans `buildSettingsPage` et `buildForm`.
   - Ajouter `onkeydown="if(event.key==='Enter'){event.preventDefault();scanFromForm();}"` sur `#f-url`.
3. **Nettoyer `renderBulkBar`, `requestDelete` et le code mort `loadPrefs`/`savePrefs` :**
   - Dans `renderBulkBar()` (ligne 1149) : `if (!manageMode) { bar.className = ""; bar.innerHTML = ""; return; }`, et filtrer `!pendingDel.has(j.id)` dans le calcul de `cleanable`.
   - Dans `requestDelete()` : mémoriser `const prevSelected = selectedId;` et dans `cancel()`, si `!selectedId && prevSelected`, appeler `selectJob(prevSelected)`.
   - Supprimer `loadPrefs` et `savePrefs` (lignes 1054-1058).
4. **Ajouter une règle `@media (max-width: 768px)` dans le CSS de `server.py` :**
   - Adapter `.app` (`flex-direction: column; overflow-y: auto;`), `.sidebar` (`width: 100%; max-height: 38vh; border-right: none; border-bottom: 1px solid var(--border);`), `.detail` (`padding: 1rem; overflow-y: visible;`) et `.opts-grid, .fmt-grid` (`grid-template-columns: 1fr;`).
5. **Mettre à jour `README.md` (lignes 82-115) :**
   - Remplacer les anciens noms de boutons (`Create and run`, `Regenerate rendering`, `Restart`) par les noms réels (`🔍 Step 1 — Scan the wiki`, `Do everything at once`, `Re-render output`, `⏸ Pause` / `▶ Resume`).

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas refondre le thème visuel ni ajouter de framework CSS.

---

## Contraintes

- Conserver toutes les valeurs de `DEFAULTS` dans `server.py:66-76`.

---

## Dépendances

- À exécuter en dernier après les plans P0–P2 touchant `server.py` (`PLAN-UX-03`, `PLAN-UX-07`, `PLAN-UX-08`, `PLAN-UX-11`).

---

## Critères d'acceptation

1. Sur une installation sans `settings.json`, `/api/settings` renvoie `"max_files": 50` et `"notebooklm_plan": "free"`.
2. Saisir `0` dans le champ `Delay` enregistre bien `0` (et non `0.5`).
3. Cliquer sur le texte d'une case `.opt-check` coche/décoche la case.
4. Quitter le mode `Manage` ne laisse aucune bordure/boîte vide en bas de la sidebar.
5. `python -m pytest` passe intégralement.

---

## Vérification

1. Vérifier en `jsdom` que `collectParams()` avec `#f-delay = "0"` renvoie `delay === 0` et que `renderBulkBar()` avec `manageMode = false` vide `bar.className`.
2. Exécuter `python -m pytest`.

---

## Risques

- Aucun risque.
