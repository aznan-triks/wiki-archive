# [P2] PLAN-UX-11 — Incohérences de la barre de progression (`#d-steps`), du terminal de logs et du chemin de sortie (`Copy path`)

- **Type :** bug / UX / UI
- **Preuve :**
  - *Confirmé à l'exécution* (via `jsdom` sur `server._HTML` et `TestClient` sur `server.py`) :
    1. Envoi des logs d'un scan terminé (`[1/5]`, `[2/5]`, `[4/5]`, `  ✓ SCAN COMPLETE -- ready for category selection`) à `flushLogs()` (`server.py:1915-1939`) :
       - `#step-3` (`4. Categories`) reste indéfiniment en classe `step active` (bleu) au lieu de `step done` (vert) car `flushLogs()` ne cherche que `"PIPELINE COMPLETE"` (ligne 1925) ;
       - `#step-2` (`3. Conversion`) passe en `step done` (vert) alors que l'étape 3 a été sautée pendant le scan ;
       - la ligne `"  ✓ SCAN COMPLETE"` reçoit la classe `l-def` (gris) au lieu de `l-ok` (vert) car `classifyLine` teste `line.startsWith("✓")` sans `.trimStart()` (alors que `run.py:55` préfixe `"  ✓ "`).
    2. En mode natif hors Docker (`HOST_PROJECT_DIR` vide, cas de `run.bat`), `job.out_path` (`server.py:129-135, 228`) vaut le chemin relatif `"data/output/<slug>"`, que l'Explorateur Windows refuse d'ouvrir lorsqu'on le colle dans la barre d'adresse comme demandé par l'UI (`"Paste this path into File Explorer"`).
  - *Déduit du code* :
    - `server.py:129-135` (`_host_path` retourne `rel` relatif dès que `HOST_PROJECT_DIR` est vide)
    - `server.py:404-406` (`JobManager.start()` efface tous les logs du scan précédent `job.logs.clear()` dès qu'on lance `Generate`)
    - `server.py:1615-1618` (`updateDetail` réécrit `filesEl.innerHTML = buildFiles(job)` toutes les 2 secondes sans vérifier si les fichiers ont changé, réinitialisant le bouton `"✓ Copied!"` et empêchant de sélectionner le texte)
    - `server.py:1915-1939` (`flushLogs` force `term.scrollTop = term.scrollHeight` même si l'utilisateur a remonté le terminal pour lire une erreur)

---

## Problème

Cinq défauts d'interface nuisent à la compréhension de l'avancement et à la récupération des fichiers générés :

### 1. Barre d'étapes (`#d-steps`) trompeuse pendant et après un `Scan` ou une `Erreur`
- `flushLogs()` (`server.py:1919-1926`) détecte `[4/5]` et met `#step-3` (`4. Categories`) en état `active` (bleu), et marque automatiquement `#step-0`, `#step-1`, `#step-2` (`3. Conversion`) en `done` (vert) — alors qu'en mode `Scan` (ou export `.md`/`.txt`), l'étape `3. Conversion` a été **sautée** (`↩ Skipped`) !
- Quand le scan se termine par `"  ✓ SCAN COMPLETE"`, `flushLogs()` ne cherche que `line.includes("PIPELINE COMPLETE")` (ligne 1925) : `#step-3` (`4. Categories`) reste bloqué en bleu (`active`) jusqu'au prochain tick de polling ou indéfiniment lors de la relecture des logs.
- Inversement, lorsqu'on clique dans la sidebar sur un job en statut `error`, `selectJob` appelle `renderDetail` (qui met l'étape en rouge `err`), puis `startLogStream` rejoue les logs dans `flushLogs()`, qui **écrase la classe `err` par `active` (bleu)** pendant 2 secondes, et si le crash a eu lieu avant `[1/5]`, aucune étape n'est marquée en rouge (`currentStep === -1`).

### 2. Coloration syntaxique des logs (`classifyLine`) en échec sur les bannières indentées
Dans `server.py:1901-1910` :
```javascript
if (line.startsWith("✓") || line.includes("COMPLETE")) return "l-ok";
if (line.startsWith("⚠") || line.includes("WARN") || line.includes("FALLBACK")) return "l-warn";
```
Or `scripts/run.py` indente de 2 espaces la plupart de ses messages (`"  ✓ Merge OK"`, `"  ⚠ Some PDFs failed"`, `"  ⚠ Cannot reach the API"`). Comme `line.startsWith("✓")` et `line.startsWith("⚠")` sont testés sans `line.trimStart()`, ces lignes perdent leur coloration verte/orange.

### 3. Défilement forcé du terminal (`scrollTop = scrollHeight`) et effacement des logs du scan lors du `Generate`
- Dans `flushLogs()` (`server.py:1928`), `term.scrollTop = term.scrollHeight` est exécuté à chaque ligne reçue, même si l'utilisateur a fait défiler le terminal vers le haut pour inspecter un avertissement.
- Dans `JobManager.start()` (`server.py:404-406`), lancer `phase="generate"` efface `job.logs` et supprime `job.log_file()`, faisant disparaître tout l'historique du scan.

### 4. `Copy path` fournit un chemin relatif inutilisable dans l'Explorateur Windows en mode natif (`run.bat`)
Dans `server.py:129-135` :
```python
def _host_path(rel: str) -> str:
    if not HOST_PROJECT_DIR:
        return rel
```
En installation native (`run.bat`, recommandée par le README), `HOST_PROJECT_DIR` n'est pas défini. `job.out_path` vaut donc `"data/output/wiki.play.eco"`.
Quand l'utilisateur suit la consigne affichée sous le bouton (`"Paste this path into File Explorer, then import the folder into NotebookLM"`), **l'Explorateur Windows rejette ce chemin relatif** car il ne connaît pas le dossier de travail du serveur Python. Or, hors Docker, `(_PROJECT_DIR / rel).resolve()` donne directement le vrai chemin absolu du système hôte (`C:\Users\...\wiki-archive\data\output\wiki.play.eco`).

### 5. Réécriture DOM de `#d-files` toutes les 2 secondes
Dans `updateDetail()` (`server.py:1615-1618`), `filesEl.innerHTML = buildFiles(job)` est ré-exécuté à chaque tick de polling (toutes les 2 s). Si l'utilisateur sélectionne le chemin à la souris ou clique sur `📂 Copy path`, le DOM est détruit et recréé moins de 2 secondes plus tard.

---

## Impact utilisateur

- **Modéré (P2) — Heuristique de Nielsen n° 1 (Visibilité de l'état du système) :**
  - Le bouton `📂 Copy path` échoue à ouvrir le dossier dans l'Explorateur Windows sur l'installation native recommandée (`run.bat`).
  - L'indicateur d'étapes affiche `3. Conversion` comme effectuée lors d'un simple scan ou d'un export Markdown, et laisse `4. Categories` en cours après la fin du scan.

---

## Comportement actuel

1. `_host_path()` renvoie un chemin relatif `"data/output/..."` dès que `HOST_PROJECT_DIR` est vide.
2. `flushLogs()` ignore `"SCAN COMPLETE"`, marque les étapes sautées comme `done`, écrase l'état `err` des jobs échoués, et force le scroll en bas.
3. `updateDetail()` écrase `#d-files` toutes les 2 secondes même si la liste des fichiers est identique.

---

## Comportement attendu

1. Dans `_host_path(rel: str)` (`server.py:129-135`) : si `HOST_PROJECT_DIR` est vide et que le serveur ne tourne pas dans un conteneur Docker (`not Path("/.dockerenv").exists()`), retourner `str((_PROJECT_DIR / rel).resolve())` (chemin absolu natif de l'OS, avec `\` sous Windows et `/` sous Linux/macOS).
2. Dans `flushLogs()` et `classifyLine()` (`server.py:1901-1939`) :
   - Tester `const t = line.trimStart();` dans `classifyLine`.
   - Si une ligne contient `"SCAN COMPLETE"`, marquer `#step-3` (`4. Categories`) comme `done`.
   - Si le job courant est en statut `error`, marquer `currentStep` (ou `0` si `currentStep === -1`) en `err` à la fin de `flushLogs()`.
   - Ne faire défiler automatiquement le terminal (`term.scrollTop = term.scrollHeight`) que si l'utilisateur était déjà proche du bas (`term.scrollHeight - term.scrollTop - term.clientHeight < 60`).
3. Dans `updateDetail()` (`server.py:1615-1618`) : ne réécrire `filesEl.innerHTML` que si la signature des fichiers (`JSON.stringify(job.files)`) a changé.
4. Dans `JobManager.start()` (`server.py:404-406`) : lorsque `phase == "generate"`, conserver les logs du scan et ajouter une ligne de séparation (`job.push("")`) au lieu d'effacer `job.logs` et `job.log_file()`.

---

## Cause probable

- `_host_path` a été écrit initialement pour Docker (`docker-compose.yml` qui définit `HOST_PROJECT_DIR`), sans penser qu'en mode natif (`run.bat`) `HOST_PROJECT_DIR` est vide alors que `_PROJECT_DIR.resolve()` est directement le chemin hôte.
- `flushLogs()` n'a pas été mis à jour lors de l'introduction de la bannière `SCAN COMPLETE`.

---

## Zones concernées

- `server.py` :
  - lignes 129-135 (`_host_path`)
  - lignes 404-406 (`JobManager.start` en phase `generate`)
  - lignes 1506-1516, 1610-1618 (`updateDetail`)
  - lignes 1901-1939 (`classifyLine`, `flushLogs`)

---

## Points d'impact

- **Appelants :** `Job.meta()` (`server.py:228`), `/api/settings` (`server.py:617-618`), UI logs et détails.
- **Tests existants :** `tests/test_server_config.py`.

---

## Plan d'action

1. **Retourner un chemin absolu natif dans `_host_path` hors Docker (`server.py:129-135`) :**
   - Si `not HOST_PROJECT_DIR` et `not Path("/.dockerenv").exists()`, retourner `str((_PROJECT_DIR / rel).resolve())`.
2. **Conserver l'historique du scan lors de `Generate` (`server.py:404-406`) :**
   - Dans `JobManager.start()`, n'effacer `job.logs` et `job.log_file()` que si `phase != "generate"`.
3. **Corriger `classifyLine`, `flushLogs` et `updateDetail` (`server.py:1506-1516, 1610-1618, 1901-1939`) :**
   - Utiliser `const t = line.trimStart()` dans `classifyLine`.
   - Dans `flushLogs()`, vérifier si l'utilisateur est en bas du terminal avant d'ajouter les lignes, puis :
     - sur `"SCAN COMPLETE"`, appeler `setStep(3, "done")` ;
     - si `allJobs[selectedId]?.status === "error"`, appeler `setStep(Math.max(0, currentStep), "err")`.
   - Dans `updateDetail()`, stocker `filesEl.dataset.sig = sig` (`JSON.stringify(job.files)`) et ne remplacer `filesEl.innerHTML` que si `filesEl.dataset.sig !== sig`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas ajouter de bibliothèque JS externe pour le terminal ou la gestion d'état.

---

## Contraintes

- En mode Docker avec `HOST_PROJECT_DIR` défini (ex. `C:\Users\alice\wiki-archive`), `_host_path` doit continuer à formater le chemin Windows avec `\` comme aujourd'hui.

---

## Dépendances

- Aucune dépendance bloquante.

---

## Critères d'acceptation

1. En exécution native (`HOST_PROJECT_DIR` vide, hors Docker), `job.out_path` est un chemin absolu résolu (`/home/.../data/output/<slug>` ou `C:\...\data\output\<slug>`).
2. À la fin d'un scan (`✓ SCAN COMPLETE`), l'étape `4. Categories` passe en vert (`done`) et la ligne `  ✓ SCAN COMPLETE` est colorée en vert (`l-ok`).
3. Pendant l'exécution d'un job, remonter la barre de défilement du terminal ne force plus le retour en bas à chaque nouvelle ligne.
4. Le bouton `📂 Copy path` garde son état `"✓ Copied!"` pendant 2 secondes sans être écrasé par `updateDetail()`.

---

## Vérification

1. Vérifier en `jsdom` le comportement de `flushLogs()` sur `SCAN COMPLETE` et sur un job en `error`.
2. Exécuter `python -m pytest`.

---

## Risques

- Faible : conserver les logs du scan lors de `phase == "generate"` ajoute quelques dizaines de lignes au fichier `run.log` (déjà borné à `maxlen=3000` en mémoire dans `deque`).
