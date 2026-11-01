# [P0] PLAN-UX-04 — Destruction des fichiers générés d'un autre job partageant le même wiki et écrasement destructif avant génération

- **Type :** bug / conception / perte de données
- **Preuve :**
  - *Confirmé à l'exécution* :
    - Création de `Job 1` (`https://wiki.play.eco/en/Eco_Wiki`, statut `done`, fichier `data/output/wiki.play.eco/Weapons.pdf` généré) et de `Job 2` (`https://wiki.play.eco/en/Weapons`, statut `pending`).
    - L'appel `GET /api/jobs` retourne `Weapons.pdf` dans `Job 2.files` alors que `Job 2` n'a jamais tourné.
    - La suppression de `Job 2` via `POST /api/jobs/bulk_delete` supprime le dossier `data/output/wiki.play.eco/`, détruisant les fichiers finaux de `Job 1` (`Job 1.files` devient `[]`).
  - *Déduit du code* :
    - `server.py:176` (`def merged_dir(self) -> Path: return DATA_DIR / "output" / self.wiki_slug()`)
    - `server.py:227, 236-246` (`meta()` et `_files_meta()` listent `self.merged_dir()` quel que soit le statut du job)
    - `server.py:357-360` (`JobManager.delete()` exécute inconditionnellement `shutil.rmtree(job.merged_dir(), ignore_errors=True)`)
    - `server.py:199` (`disk_usage()` compte `output_bytes = tree_size(self.merged_dir())` sur chaque job du même wiki)
    - `scripts/run.py:397` (`shutil.rmtree(out_dir, ignore_errors=True)` exécuté au début de l'étape 5 avant toute génération et quel que soit le format demandé)

---

## Problème

Le projet associe les données intermédiaires à un identifiant de job (`data/jobs/<job_id>/`), mais associe le dossier de sortie final uniquement au nom d'hôte du wiki (`data/output/<wiki_slug>/`). Cette asymétrie provoque trois défauts graves :

### 1. Suppression d'un job en erreur / arrêté = suppression des fichiers finaux du job réussi sur le même wiki
Un utilisateur crée souvent un second job pour le même wiki (par exemple après un essai arrêté ou en erreur, ou pour tester d'autres paramètres), puis utilise le bouton **`🗑`** ou le bouton **`🧹 Clean up stopped/errored`** du mode `Manage` (`server.py:1158, 1186`).
Or `JobManager.delete(job_id)` (`server.py:357-360`) exécute systématiquement :
```python
out = job.merged_dir()
if out.exists():
    shutil.rmtree(out, ignore_errors=True)
```
Supprimer le job en échec ou arrêté **efface immédiatement le dossier `data/output/<wiki_slug>/`**, détruisant tous les fichiers finaux (`*.pdf`, `*.md`, `*.txt`) produits par le job réussi (`Done`) sur ce même wiki.

### 2. Attribution mensongère des fichiers générés aux jobs `pending`, `scanned` ou `error`
`Job._files_meta()` (`server.py:236-246`) liste le contenu de `data/output/<wiki_slug>/` sans vérifier si ce job a effectivement généré des fichiers.
Dès qu'un dossier `data/output/<wiki_slug>/` existe d'un job antérieur :
- Tout nouveau job créé pour ce même wiki affiche immédiatement la carte **Generated files** avec les fichiers de l'ancien job, même s'il est en statut `Pending`, `Scanned` ou `Error`.
- En mode `Manage`, la taille disque affichée dans la sidebar (`disk_usage()`) additionne `output_bytes` à chacun des jobs du même wiki.

### 3. Destruction prématurée de `out_dir` au début de l'étape 5 (`scripts/run.py:397`)
Au début de l'étape 5 (`scripts/run.py:397`), `run.py` exécute `shutil.rmtree(out_dir, ignore_errors=True)` **avant** de générer les nouveaux fichiers, et supprime **tous** les formats confondus :
- Si l'utilisateur a d'abord généré les `.pdf` (45 minutes de calcul), puis décoche `PDF` et coche `Markdown` pour générer aussi les `.md` via `Generate`, `shutil.rmtree(out_dir)` **détruit tous ses `.pdf`**.
- Si l'étape 5 échoue en cours de route (ou si la sélection produit 0 fichier), les fichiers finaux valides de l'exécution précédente ont déjà été détruits.

---

## Impact utilisateur

- **Critique (P0) — Perte de données irréversible :** le bouton `🧹 Clean up stopped/errored`, présenté comme une action d'entretien sûre, détruit le résultat de jobs terminés (`Done`) ayant pris jusqu'à plusieurs heures de calcul.
- De même, générer un format supplémentaire (`.md` après `.pdf`) détruit les fichiers du premier format.

---

## Comportement actuel

1. `JobManager.delete(job_id)` supprime toujours `data/output/<wiki_slug>`, même si un autre job (`done` ou actif) existe pour ce `wiki_slug`.
2. Un job `pending`, `scanned` ou `error` affiche dans `#d-files` les fichiers de `data/output/<wiki_slug>` produits par un autre job.
3. L'étape 5 vide intégralement `data/output/<wiki_slug>` avant d'avoir produit quoi que ce soit.

---

## Comportement attendu

1. `JobManager.delete(job_id)` ne supprime `data/output/<wiki_slug>` que si **aucun autre job restant** dans `self._jobs` (hors `job_id`) ne possède le même `wiki_slug()`.
2. À l'étape 5 de `scripts/run.py`, la génération s'effectue d'abord dans un dossier de staging `{job_dir}/out_staging/`, et seulement lorsque au moins un fichier a été produit avec succès :
   - seuls les anciens fichiers de `out_dir` correspondant aux extensions demandées dans cette exécution (`.pdf` si `want_pdf`, `.md`/`.txt` si présents dans `doc_formats`) sont remplacés, ou bien si l'utilisateur change la sélection de catégories pour ces formats, seules les extensions régénérées sont purgées de `out_dir` avant d'y déplacer les nouveaux fichiers.
   - Ainsi, générer `.md` après `.pdf` conserve les `.pdf` existants, et un échec à l'étape 5 laisse `out_dir` intact.
3. Dans `Job.meta()`, `files` n'est peuplé que lorsque le job a atteint au moins une génération (`status == "done"` ou présence d'un marqueur/horodatage de génération sur le job, ou a minima `status not in ("pending",)`).

---

## Cause probable

Le chemin de sortie `data/output/<wiki-hostname>/` est une exigence produit documentée dans `README.md` pour faciliter l'import dans NotebookLM (un dossier lisible par wiki), mais `JobManager.delete()` et l'étape 5 de `run.py` ont été codés comme si `out_dir` appartenait exclusivement à une seule exécution et un seul job.

---

## Zones concernées

- `server.py` : lignes 218-246 (`meta`, `_files_meta`), lignes 349-363 (`JobManager.delete`).
- `scripts/run.py` : lignes 391-424 (étape 5 `PER-CATEGORY FILE PRODUCTION`).
- `tests/test_server_config.py` et `tests/test_run_pipeline.py`.

---

## Points d'impact

- **Appelants :** `POST /api/jobs/bulk_delete` (`server.py:750-755`), `scripts/run.py` étape 5.
- **Documentation :** `README.md:22-23, 62-63` (`data/output/{wiki-hostname}/` est intégralement préservé).
- **Tests existants :** `tests/test_run_pipeline.py:66-82` (`test_zero_output_files_is_a_failure`) vérifie qu'une génération qui produit 0 fichier échoue avec le code `1` et le message `0 output files` — en utilisant un dossier de staging, il faut vérifier `produced` sur le dossier de staging avant de toucher à `out_dir`, tout en conservant exactement le même message d'erreur `⚠ FAILURE: pipeline produced 0 output files in <out_dir>`.

---

## Plan d'action

1. **Protéger `data/output/<wiki_slug>` lors de la suppression d'un job (`server.py:349-363`) :**
   - Dans `JobManager.delete(self, job_id: str)`, calculer `slug = job.wiki_slug()` et vérifier `other_jobs_same_wiki = any(j.id != job_id and j.wiki_slug() == slug for j in self._jobs.values())`.
   - Ne supprimer `out = job.merged_dir()` que si `not other_jobs_same_wiki`.
2. **Ne pas afficher les fichiers d'un autre job sur un job `pending` (`server.py:236-246`) :**
   - Dans `Job._files_meta(self)`, si `self.status == "pending"`, retourner `[]`.
3. **Utiliser un dossier de staging par format à l'étape 5 (`scripts/run.py:391-424`) :**
   - Créer `staging_dir = job_dir / "out_staging"` (nettoyé au début de l'étape 5).
   - Exécuter `merge_pdf.py` (si `want_pdf`) et `export_categories.py` (si `want_docs`) vers `staging_dir`.
   - Vérifier `staged = [f for f in sorted(staging_dir.glob("*")) if f.is_file()]`. Si `not staged`, supprimer `staging_dir`, afficher la bannière `⚠ FAILURE: pipeline produced 0 output files in {out_dir}` et retourner `1` **sans avoir détruit `out_dir`**.
   - Si `staged` est non vide : créer `out_dir`, supprimer de `out_dir` uniquement les fichiers existants dont l'extension fait partie des formats demandés lors de cette exécution (`{f".{fmt}" for fmt in formats_list}`), déplacer les fichiers de `staging_dir` vers `out_dir`, puis supprimer `staging_dir`.
4. **Ajouter les tests dans `tests/test_server_config.py` et `tests/test_run_pipeline.py` :**
   - Tester que supprimer un job `error`/`pending` ne supprime pas `data/output/<slug>` lorsqu'un autre job existe pour le même wiki, mais le supprime bien lorsqu'il s'agit du dernier job de ce wiki.
   - Tester qu'une génération `.txt` après une génération `.md` conserve les fichiers `.md` déjà présents dans `data/output/<slug>`, et qu'une génération qui échoue à l'étape 5 ne détruit pas les fichiers précédemment générés.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas changer le chemin de sortie public `data/output/<wiki-hostname>/` (documenté dans `README.md` et attendu par l'utilisateur).

---

## Contraintes

- Conserver le message exact `"0 output files"` dans `scripts/run.py` pour la compatibilité avec `tests/test_run_pipeline.py:81`.

---

## Dépendances

- Peut être exécuté indépendamment ; s'articule avec `PLAN-UX-01` et `PLAN-UX-02` sur l'étape 5 de `scripts/run.py` (exécuter après `PLAN-UX-01` et `PLAN-UX-02`).

---

## Critères d'acceptation

1. Avec deux jobs sur le même wiki (Job 1 `done` ayant des fichiers dans `data/output/<slug>`, Job 2 `error`), cliquer sur `🧹 Clean up stopped/errored` supprime Job 2 et conserve tous les fichiers de Job 1.
2. Supprimer ensuite Job 1 (dernier job de ce wiki) supprime bien `data/output/<slug>`.
3. Générer d'abord en format `md`, puis relancer `Generate` uniquement en format `txt` laisse à la fois les fichiers `.md` et `.txt` dans `data/output/<slug>`.
4. Si une génération échoue à l'étape 5 (`0 output files`), les fichiers produits lors d'une génération précédente dans `out_dir` restent intacts.

---

## Vérification

1. Exécuter `python -m pytest`.
2. Créer deux jobs pour la même URL, simuler des fichiers de sortie, supprimer le second job via `bulk_delete`, vérifier que le dossier de sortie existe toujours.

---

## Risques

- Si l'utilisateur réduit sa sélection de catégories (ex. de 10 catégories à 3 catégories) dans le **même** format `.md`, les 10 anciens `.md` doivent bien être nettoyés pour qu'il n'en reste que 3 : la suppression par extension demandée (`for old in out_dir.glob(f"*{ext}"): old.unlink()`) garantit qu'aucun ancien fichier `.md` hors sélection ne subsiste tout en préservant les `.pdf` ou `.txt` non régénérés.
