# [P1] PLAN-UX-08 — Déconnexion entre le panneau de génération (Étape 2) et les options de format / `Max files` (`Reconfigure`)

- **Type :** bug / UX / fonctionnel
- **Preuve :**
  - *Confirmé à l'exécution* (via `jsdom` sur `server._HTML`) :
    - Ouverture de `Reconfigure / re-scan` (`toggleReconfigure()`), modification des formats ou de `Max files` dans `#d-form`, puis clic sur `▶ Generate selection` (`doGenerate(jobId)` à `server.py:1823`) : `doGenerate` envoie `POST /api/jobs/{id}/generate` avec `formats: null` sans jamais lire ni sauvegarder `#d-form`. Les modifications de l'utilisateur sont totalement ignorées.
    - De plus, `scanFromForm()` (`server.py:1419`) n'effectue aucune validation sur `collectFormats() === "none"`, autorisant un scan complet avec 0 format sélectionné qui échouera ensuite à la génération.
  - *Déduit du code* :
    - `server.py:1532-1556` (`buildGenPanel` n'affiche ni les formats d'export ni `Max files`, et son lien `Reconfigure / re-scan` ouvre `#d-form` qui ne contient que les boutons `Scan the wiki` et `Do everything at once`, sans bouton `Save`)
    - `server.py:1823-1840` (`doGenerate` et `doGenerateAll` n'appellent pas `ensureJob()` et n'envoient jamais les paramètres modifiés dans `#d-form`)
    - `server.py:570-577` et `1780-1806` (`_packing_preview` calcule et renvoie la liste détaillée `groups: [{"name": ..., "pages": ..., "words": ...}]`, mais `updateGenInfo` l'ignore complètement)
    - `server.py:1376-1377` (`f-rerender` porte la classe `pdf-opt`, ce qui cache la case `Re-render output` dès que `PDF` est décoché, alors que `scripts/run.py:190-193` utilise `RERENDER` pour supprimer `html_dir` et ré-extraire le HTML aussi bien pour Markdown que pour Texte)

---

## Problème

Une fois le scan terminé (Étape 2 — `Choose which categories to keep, then generate your files`), l'expérience de configuration et d'aperçu de la génération présente quatre défauts majeurs :

### 1. Modifications dans `Reconfigure` silencieusement ignorées par `Generate`
À l'étape 2 (`#d-gen`), l'utilisateur voit un lien `Reconfigure / re-scan` (`toggleReconfigure()`, `server.py:1554, 1559-1561`) qui affiche le formulaire `#d-form` en dessous du panneau de génération.
S'il ouvre ce formulaire pour changer de format (ex. cocher `Markdown (.md)` au lieu de `PDF`), ajuster le plafond `Max files` (ex. passer de `50` à `20`) ou décocher `Avoid duplicates`, puis clique sur **`▶ Generate selection`** ou **`Generate all`** :
- `doGenerate()` (`server.py:1823-1831`) et `doGenerateAll()` (`server.py:1833-1840`) envoient directement `POST /api/jobs/{id}/generate` sans jamais appeler `PATCH /api/jobs/{id}` (`ensureJob()`) !
- Le formulaire `#d-form` n'ayant pas non plus de bouton `Save`, les seules actions de `#d-form` sont `🔍 Step 1 — Scan the wiki` (qui relance un scan inutile) et `Do everything at once`.
- Résultat : le job génère les fichiers avec les **anciens** formats et l'ancien `Max files`, ignorant tout ce que l'utilisateur vient de cocher sous ses yeux.

### 2. L'aperçu (`preview_packing`) ignore les modifications de `Max files` / `Avoid duplicates` et masque le détail des regroupements (`preview.groups`)
- Le serveur (`_packing_preview`, `server.py:570-577`) calcule et renvoie dans la réponse JSON la liste exacte des fichiers qui seront créés (`groups: [{"name": k, "pages": len(v), "words": ...}]`, ex. `Weapons+Armor (42 pages, 85k words)`).
- Or `updateGenInfo()` (`server.py:1780-1806`) n'affiche que le compteur global (`"→ ~12 output files (3 merges)"`) sans permettre à l'utilisateur de voir **quelles** catégories vont être fusionnées ensemble avant de lancer la génération.
- En outre, modifier `Max files` ou `Avoid duplicates` dans `#d-form` ne déclenche pas `schedulePreview()`.

### 3. Validation tardive des formats (`export_formats === "none"`)
- `startFromForm()` (`server.py:1424`) refuse de lancer si `collectFormats() === "none"` (`showToast("Check at least one export format...")`), mais `scanFromForm()` (`server.py:1419`) ne vérifie **pas** `collectFormats() === "none"`.
- L'utilisateur peut donc décocher tous les formats, lancer un scan complet de 20 minutes, puis voir `Generate` échouer ou générer avec un format vide.

### 4. `Re-render output` caché à tort quand `PDF` est décoché
- Dans `server.py:1376`, le conteneur de `#f-rerender` a la classe `pdf-opt`, que `syncFormVisibility()` (`server.py:1388-1391`) masque dès que la case `PDF` est décochée.
- Or dans `scripts/run.py:190-193`, `RERENDER=true` supprime `html_dir`, `categories_file`, `cat_groups` et `out_dir` afin de ré-extraire le HTML et de régénérer les sorties — ce qui est tout aussi nécessaire pour régénérer les exports `.md` et `.txt` après un changement de nettoyage HTML que pour les `.pdf`.

---

## Impact utilisateur

- **Majeur (P1) — Heuristique de Nielsen n° 1 (Visibilité de l'état du système) et n° 5 (Prévention des erreurs) :**
  - L'utilisateur ne peut pas changer le format de sortie (`.pdf` → `.md`) ni `Max files` à l'étape 2 et cliquer sur `Generate selection` sans que ses choix soient ignorés.
  - Il voit `"3 merges"` dans l'aperçu sans pouvoir vérifier quelles catégories sont fusionnées.

---

## Comportement actuel

1. `doGenerate` et `doGenerateAll` ignorent l'état courant des champs de `#d-form` lorsqu'il est ouvert.
2. `_packing_preview` lit uniquement `job.params` (jamais les valeurs en cours d'édition dans `#d-form`) et le client ignore `preview.groups`.
3. `scanFromForm()` accepte `export_formats === "none"`.
4. `#f-rerender` disparaît quand seuls `.md` ou `.txt` sont cochés.

---

## Comportement attendu

1. Si `#d-form` est présent et visible lorsque l'utilisateur clique sur `▶ Generate selection` ou `Generate all`, `doGenerate` / `doGenerateAll` vérifie qu'au moins un format est coché et sauvegarde d'abord les paramètres du formulaire via `ensureJob()` avant d'appeler `/api/jobs/{id}/generate`.
2. Lorsque l'utilisateur modifie `Max files`, `NotebookLM Plan`, `Avoid duplicates` ou les formats dans `#d-form` alors que `#d-gen` est visible, `ensureJob()` (ou le passage de `max_files` et `dedup` à `preview_packing`) met à jour l'aperçu en direct (`schedulePreview()`).
3. Dans `#gen-info` (`updateGenInfo`), lorsque `preview.groups` est présent, afficher un `<details>` repliable (`"View planned output files (N)"`) listant les noms des fichiers prévus avec leur nombre de pages et de mots (données déjà renvoyées par `/api/jobs/{id}/preview_packing`).
4. `scanFromForm()` vérifie `if (collectFormats() === "none")` au même titre que `startFromForm()`.
5. Retirer la classe `pdf-opt` du conteneur de `#f-rerender` (`server.py:1376`) pour que `Re-render output` reste accessible quel que soit le format d'export choisi.

---

## Cause probable

Le panneau `#d-gen` a été ajouté au-dessus de `#d-form` sans relier ses boutons `doGenerate` / `doGenerateAll` à la fonction de sauvegarde `ensureJob()` de `#d-form`.

---

## Zones concernées

- `server.py` :
  - lignes 530-577 (`_packing_preview` et `PreviewRequest` : accepter optionnellement `max_files` et `dedup` dans le corps de la requête ou sauvegarder avant aperçu)
  - ligne 1376 (retrait de `pdf-opt` sur `#f-rerender`)
  - lignes 1418-1422 (`scanFromForm` : validation `collectFormats() === "none"`)
  - lignes 1780-1840 (`updateGenInfo`, `doGenerate`, `doGenerateAll`)

---

## Points d'impact

- **Appelants :** `scanFromForm`, `doGenerate`, `doGenerateAll`, `runPreview`, `updateGenInfo` dans `server.py`.
- **API :** `POST /api/jobs/{job_id}/preview_packing` (`PreviewRequest` peut accepter `max_files: int | None = None` et `dedup: bool | None = None` de façon rétrocompatible).
- **Tests existants :** `tests/test_server_config.py`.

---

## Plan d'action

1. **Valider les formats dès `scanFromForm()` (`server.py:1418-1422`) :**
   - Ajouter `if (collectFormats() === "none") { showToast("Check at least one export format (PDF, Markdown or Text).", {type:"warn"}); return; }` au début de `scanFromForm()`.
2. **Synchroniser `#d-form` lors de `doGenerate` et `doGenerateAll` (`server.py:1823-1840`) :**
   - Au début de `doGenerate(jobId)` et `doGenerateAll(jobId)`, si `document.getElementById("f-url")` existe dans le DOM (c.-à-d. que `#d-form` a été ouvert via `Reconfigure`), vérifier `collectFormats() !== "none"` et appeler `await ensureJob()` pour persister `export_formats`, `max_files`, `dedup`, etc. dans `job.params` avant d'envoyer `POST /api/jobs/${jobId}/generate`.
3. **Relier `Max files` et `Avoid duplicates` à l'aperçu et afficher `preview.groups` (`server.py:530-577, 1363-1373, 1780-1816`) :**
   - Étendre `PreviewRequest` avec `max_files: int | None = None` et `dedup: bool | None = None`, pris en compte par `_packing_preview(job, req.selection, req.max_files, req.dedup)`.
   - Dans `runPreview()`, lire `#f-max-files` et `#f-dedup` s'ils sont présents dans le DOM (sinon utiliser `job.params`), et déclencher `schedulePreview(jobId)` sur `onchange` de `#f-max-files`, `#f-plan` et `#f-dedup`.
   - Dans `updateGenInfo(jobId, preview)` (`server.py:1780-1806`), si `preview && preview.groups && preview.groups.length`, ajouter un bloc `<details style="margin-top:.35rem"><summary style="cursor:pointer;color:var(--accent)">Preview ${preview.groups.length} planned file(s)</summary>...</details>` affichant chaque fichier prévu (`name`, `pages`, `words`).
4. **Rendre `Re-render output` disponible pour tous les formats (`server.py:1376`) :**
   - Remplacer `<div class="opt-group opt-check pdf-opt">` par `<div class="opt-group opt-check">` sur la ligne de `#f-rerender`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas dupliquer tous les champs de `#d-form` en double dans `#d-gen` (garder un seul formulaire `#d-form` et s'assurer que ses valeurs sont automatiquement prises en compte).

---

## Contraintes

- Conserver la rétrocompatibilité de `POST /api/jobs/{job_id}/preview_packing` lorsque seul `{"selection": [...]}` est envoyé.

---

## Dépendances

- Indépendant ; se combine idéalement après `PLAN-UX-03` et `PLAN-UX-05` qui fiabilisent les données renvoyées par `_packing_preview`.

---

## Critères d'acceptation

1. Sur un job scanné (`scanned`), cliquer sur `Reconfigure / re-scan`, cocher `Markdown (.md)`, changer `Max files` à `10`, puis cliquer directement sur `▶ Generate selection` sauvegarde les nouveaux paramètres et génère bien des fichiers `.md` plafonnés à 10 fichiers.
2. Décocher les 3 formats et cliquer sur `🔍 Step 1 — Scan the wiki` affiche un avertissement toast et ne lance pas le scan.
3. L'aperçu sous l'arbre de catégories permet de déplier la liste des fichiers prévus (`preview.groups`).
4. Décocher `PDF` laisse la case `Re-render output` visible.

---

## Vérification

1. Vérifier en `jsdom` que `doGenerate` persiste les changements de `#d-form` via `PATCH /api/jobs/{id}` avant d'appeler `/generate`.
2. Exécuter `python -m pytest`.

---

## Risques

- Aucun risque de régression sur les parcours existants.
