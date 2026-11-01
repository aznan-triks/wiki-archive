# [P1] PLAN-UX-07 — Impasse UX après erreur, arrêt ou purge de stockage (`updateDetail`) et absence du bouton `Resume` promis par les logs

- **Type :** bug / UX / UI
- **Preuve :**
  - *Confirmé à l'exécution* (via `jsdom` sur `server._HTML`) :
    1. Lorsqu'un job en cours (`running`) passe à `error` ou `stopped` (avec `has_tree: false`), l'appel de `updateDetail(job)` par le polling (`refresh()`) vide `#d-actions` (`actions: ""`) et laisse `#d-form` vide (`form len: 0`) : l'utilisateur n'a plus **aucun bouton d'action ni formulaire** à l'écran.
    2. Lorsqu'un job terminé (`done`, `has_tree: true`) exécute `purge(jobId, 'intermediate')` (`Free up space`), `canGenerate(job)` passe à `false`, la bannière affiche `"Intermediate data purged -- Run a new scan to regenerate"`, mais `updateDetail(job)` laisse le panneau `#d-gen` (`▶ Generate selection`) visible (`genDisplay: "block"`) et garde le formulaire `#d-form` caché (`formDisplay: "none"`).
  - *Déduit du code* :
    - `server.py:520` (`job.push("⏹ Stopped. You can restart it via Resume.")`)
    - `server.py:1518-1527` (`buildActions(job)` ne rend le bouton `▶ Resume` que si `job.status === "paused"`, jamais pour `stopped` ni `error`)
    - `server.py:1474-1495` (`renderDetail` ne peuple `#d-form` que si `!isActive && !genVisible`, c'est-à-dire pas pendant `running`)
    - `server.py:1597-1619` (`updateDetail` ne gère que la transition vers `canGenerate(job) === true` et ne gère jamais la transition vers `!isActive && !canGenerate(job)` ni la perte de `canGenerate(job)` après une purge)
    - `server.py:400-409, 456-464` (`start()` ne vérifie que `if job.status == "running":` et ignore `paused`, et `stop()` passe le statut à `stopped` avant la fin réelle du processus dans `_kill`)

---

## Problème

Quatre incohérences d'état entre le backend (`JobManager`) et la mise à jour incrémentale du DOM (`updateDetail`) piègent l'utilisateur dans des écrans sans issue :

### 1. Écran vide d'actions lorsqu'un job passe de `Running` à `Error` ou `Stopped`
Lorsque l'utilisateur lance un job (`Scan` ou `Do everything at once`), `selectJob()` appelle `renderDetail(job)` pendant que `job.status === "running"`. À cet instant, `isActive` est vrai, donc `renderDetail` (`server.py:1487-1495`) met `formEl.innerHTML = ""` et cache `#d-form`.
Quand le job échoue (ex. URL invalide, erreur réseau) ou que l'utilisateur clique sur `⏹ Stop` avant la fin du scan (`has_tree === false`), le tick de polling suivant appelle `updateDetail(job)` (`server.py:1597-1619`) :
- `updateDetail` met à jour le badge (`Error` / `Stopped`) et vide `#d-actions` (`buildActions(job)` retourne `""`),
- **mais `updateDetail` ne reconstruit jamais `#d-form` !**
- L'utilisateur se retrouve devant un écran bloqué : plus aucun bouton dans `#d-actions`, pas d'arbre `#d-gen`, et pas de formulaire `#d-form` pour modifier l'URL ou relancer, tant qu'il ne désélectionne pas puis re-sélectionne manuellement le job dans la sidebar.

### 2. Promesse mensongère `"You can restart it via Resume"` dans les logs
Quand l'utilisateur clique sur `⏹ Stop`, le backend écrit dans le terminal (`server.py:520`) :
> `⏹ Stopped. You can restart it via Resume.`

Et l'endpoint `POST /api/jobs/{job_id}/resume` (`server.py:442-454`) gère effectivement `if job.status in ("stopped", "error"): self.start(job_id)`.
Pourtant, dans l'interface (`buildActions(job)`, `server.py:1518-1527`), le bouton `▶ Resume` n'existe **que** pour `job.status === "paused"` ! Pour `stopped` et `error`, `buildActions(job)` ne renvoie que le bouton `🗑` (Supprimer). L'utilisateur cherche donc en vain le bouton `Resume` que le message vient de lui indiquer.

### 3. Après `Free up space` (`purge('intermediate')`), l'UI affiche un panneau `Generate` cassé et cache le bouton `Scan`
Lorsqu'un utilisateur clique sur **`Free up space (keep final files)`** (`purge(job.id, 'intermediate')`), le backend supprime `dump/`, `html/`, `pdf/` et `category_tree.json` (`has_tree` passe à `false`).
Au `refresh()` suivant, `updateDetail(job)` (`server.py:1597-1619`) :
- met à jour la bannière qui dit : *"Intermediate data purged -- Run a new scan to regenerate"* ;
- mais **ne cache jamais `#d-gen`** (qui n'est mis à jour que si `canGenerate(job)` devient vrai, ligne 1606) et **n'affiche jamais `#d-form`** !
L'utilisateur garde sous les yeux le vieux panneau `#d-gen` avec `▶ Generate selection` (qui plante immédiatement s'il clique dessus) et n'a pas accès au bouton `🔍 Step 1 — Scan the wiki` pourtant réclamé par la bannière.

### 4. Course critique (race condition) entre `Stop` / `Pause` et un nouveau `Start`
- Dans `server.py:402`, `start()` vérifie `if job.status == "running": return`, mais ne bloque pas `job.status == "paused"`. Si un job en pause est relancé via `scan` ou `generate`, un second sous-processus `run.py` démarre pendant que le premier reste suspendu en mémoire.
- Dans `server.py:456-464`, `stop()` met `job.status = "stopped"` immédiatement, avant la fin du thread `_kill` (jusqu'à 4 s). Si l'utilisateur clique sur `Resume` dans cet intervalle, le bloc `finally:` de l'ancien thread `_run` (`server.py:517-523`) écrase `job._proc = None` et envoie `__END__` au flux de logs du nouveau run.

---

## Impact utilisateur

- **Majeur (P1) — Heuristique de Nielsen n° 9 (Aider l'utilisateur à reconnaître, diagnostiquer et récupérer des erreurs) et n° 3 (Contrôle et liberté de l'utilisateur) :**
  - En cas d'erreur de saisie d'URL ou d'arrêt manuel, l'interface perd ses contrôles de reprise/correction.
  - Le message système invite explicitement à cliquer sur un bouton `Resume` qui n'existe pas à l'écran.
  - Le nettoyage d'espace disque (`Free up space`) laisse l'interface dans un état contradictoire qui pousse à déclencher un crash.

---

## Comportement actuel

1. `updateDetail(job)` ne synchronise ni la disparition de `#d-gen` ni l'apparition de `#d-form` lorsque `job.status` quitte `running`/`paused` ou lorsque `canGenerate(job)` devient `false`.
2. `buildActions(job)` n'affiche aucun bouton de reprise pour `stopped` ou `error`.
3. `start()` ignore les processus en état `paused` et `stop()` entre en concurrence avec `_run()` pendant l'arrêt du sous-processus.

---

## Comportement attendu

1. Dans `updateDetail(job)`, synchroniser systématiquement `#d-gen` et `#d-form` :
   - Si `canGenerate(job)` passe de `true` à `false` (ex. après `purge('intermediate')`), vider et cacher `#d-gen` (`genEl.style.display = "none"; genEl.innerHTML = ""; _treeJobId = null;`).
   - Si `!isActive && !canGenerate(job)` et que `#d-form` est vide, construire et afficher `#d-form` (`formEl.style.display = "block"; formEl.innerHTML = buildForm(job); syncFormVisibility();`).
2. Dans `buildActions(job)` (`server.py:1518-1527`) :
   - Pour `job.status === "stopped"` : afficher le bouton `▶ Resume` (`jobAction('${job.id}','resume')`).
   - Pour `job.status === "error"` : afficher le bouton `🔄 Retry / Resume` (`jobAction('${job.id}','resume')`).
3. Dans `JobManager` (`server.py:400-523`) :
   - Si `start()` est appelé alors que `job.status == "paused"` (ou que `job._proc` est encore vivant), tuer proprement l'ancien arbre de processus (`self._kill(job)`) avant de lancer le nouveau thread.
   - Dans `_run()`, utiliser une référence locale `proc` et ne remettre `job._proc = None` dans `finally:` que si `job._proc is proc`.

---

## Cause probable

`updateDetail()` a été écrit pour éviter de recréer le DOM toutes les 2 secondes pendant le polling (`refresh()`), mais seules les transitions positives (`running` → `scanned`/`done` avec `canGenerate(job) === true`) ont été implémentées, en oubliant les transitions vers `error`, `stopped` et `purged`.

---

## Zones concernées

- `server.py` :
  - lignes 400-409, 456-464, 502-523 (`JobManager.start`, `stop`, `_run`)
  - lignes 1518-1527 (`buildActions`)
  - lignes 1597-1619 (`updateDetail`)
- `tests/test_server_config.py`.

---

## Points d'impact

- **Appelants :** `refresh()` (`server.py:1079`), `jobAction()` (`server.py:1430`), `purge()` (`server.py:1866`).
- **Tests existants :** `tests/test_server_config.py` (aucune régression ; ajouter un test sur le cycle `stop` / `resume`).
- **Risque de casse :** dans `updateDetail(job)`, ne reconstruire `#d-form` que lorsque `formEl.innerHTML === ""` afin de ne jamais écraser les champs que l'utilisateur est en train de modifier toutes les 2 secondes pendant le polling !

---

## Plan d'action

1. **Compléter `updateDetail(job)` dans `server.py` (lignes 1597-1619) :**
   - Calculer `const isActive = ["running", "paused"].includes(job.status);` et `const genVisible = canGenerate(job);`.
   - Si `!genVisible && genEl.style.display !== "none"`, vider et masquer `genEl` (`genEl.style.display = "none"; genEl.innerHTML = ""; _treeJobId = null;`).
   - Si `!isActive && !genVisible && !formEl.innerHTML`, afficher et peupler `formEl` (`formEl.style.display = "block"; formEl.innerHTML = buildForm(job); syncFormVisibility();`).
2. **Ajouter le bouton `▶ Resume` / `🔄 Retry` dans `buildActions(job)` (`server.py:1518-1527`) :**
   - Lorsque `job.status === "stopped"`, ajouter `<button class="btn btn-primary btn-sm" onclick="jobAction('${job.id}','resume')">▶ Resume</button>`.
   - Lorsque `job.status === "error"`, ajouter `<button class="btn btn-ghost btn-sm" onclick="jobAction('${job.id}','resume')" title="Retry from last completed step">🔄 Retry</button>`.
3. **Sécuriser `JobManager.start()` et `_run()` (`server.py:400-523`) :**
   - Dans `start()`, si `job._proc is not None`, appeler `self._kill(job)` avant de lancer le nouveau thread.
   - Dans `_run()`, dans le bloc `finally:`, vérifier `if job._proc is proc:` avant de faire `job._proc = None` et `job.push("__END__")`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas remplacer `updateDetail()` par `renderDetail()` à chaque tick de polling de 2 s (cela détruirait le focus clavier dans les inputs et l'état d'ouverture de l'arbre de catégories).

---

## Contraintes

- Ne jamais réécrire `formEl.innerHTML` si `formEl.innerHTML` est déjà non vide (pour préserver la saisie en cours de l'utilisateur).

---

## Dépendances

- Complète directement `PLAN-UX-06` (reprise `Resume` côté backend).

---

## Critères d'acceptation

1. Lorsqu'un job en cours (`running`) passe à `error` ou `stopped` sans arbre de catégories, le formulaire `#d-form` et le bouton `▶ Resume` / `🔄 Retry` apparaissent automatiquement sans avoir à changer de job dans la sidebar.
2. Après un clic sur `Free up space (keep final files)` (`purge('intermediate')`), le panneau `#d-gen` disparaît immédiatement et le formulaire `#d-form` (`🔍 Step 1 — Scan the wiki`) s'affiche à la place.
3. Cliquer sur `⏹ Stop` puis immédiatement sur `▶ Resume` ne coupe pas le flux de logs du nouveau run.

---

## Vérification

1. Simuler en `jsdom` (ou dans le navigateur) les transitions `running → error`, `running → stopped` et `done → purge('intermediate')` via `updateDetail(job)` et vérifier la présence de `#d-form` et des boutons dans `#d-actions`.
2. Exécuter `python -m pytest`.

---

## Risques

- Faible : la garde `if (!formEl.innerHTML)` garantit que `#d-form` n'est injecté qu'une seule fois lors de la transition d'état et n'est pas réinitialisé lors des appels suivants de `refresh()`.
