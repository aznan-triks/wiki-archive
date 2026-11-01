# [P0] PLAN-UX-01 — Conversion PDF ignorée dans le parcours en 2 étapes (Scan → Generate) et après purge du cache PDF

- **Type :** bug / fonctionnel / UX
- **Preuve :**
  - *Confirmé à l'exécution* : exécution de `scripts/run.py` avec `PHASE=generate` et `EXPORT_FORMATS=pdf` après un scan (`html/*.html`, `category_groups.json`, `category_tree.json` présents, dossier `pdf/` absent) → `run.py` journalise `[3/5] PDF CONVERSION : ↩ Skipped (phase generate)`, `flatten` copie 0 fichier, `merge_pdf.py` écrit `✓ 0 PDF(s)`, et le pipeline échoue avec `⚠ FAILURE: pipeline produced 0 output files` (code de sortie `1`).
  - *Déduit du code* :
    - `scripts/run.py:297-309` (`if phase in ("scan", "generate"): log(f"↩ Skipped (phase {phase})")`)
    - `server.py:67` (`"export_formats": "pdf"` par défaut dans `DEFAULTS`)
    - `server.py:1382` (bouton primaire `🔍 Step 1 — Scan the wiki` appelant `scanFromForm()`)
    - `server.py:1545-1546` (boutons d'étape 2 `Generate all` et `▶ Generate selection` appelant `/api/jobs/{id}/generate` avec `phase="generate"`)
    - `server.py:383-384, 1862` (`Clear PDF cache` supprimant `job_dir/pdf` et `job_dir/flat`)
    - `scripts/convert.py:72-75` (retourne toujours le code `0` même si 100 % des conversions WeasyPrint échouent)

---

## Problème

Le parcours principal mis en avant par l'interface web est un flux en deux étapes :
1. **Step 1 — Scan the wiki** (`phase="scan"`) ;
2. **Step 2 — Choose which categories to keep, then generate your files** (`phase="generate"`).

Par ailleurs, le format d'export coché par défaut est **PDF (`.pdf`)** (`DEFAULTS["export_formats"] = "pdf"`).

Or, dans `scripts/run.py:298`, l'étape 3 (`[3/5] PDF CONVERSION`, qui appelle `scripts/convert.py` pour produire les PDF unitaires dans `{job_dir}/pdf/`) est sautée à la fois lorsque `phase == "scan"` **et** lorsque `phase == "generate"` :

```python
if phase in ("scan", "generate"):
    log(f"↩ Skipped (phase {phase})")
```

Par conséquent, `scripts/convert.py` n'est **jamais exécuté** dans le parcours en 2 étapes (il ne s'exécute que si l'utilisateur clique sur le lien secondaire `Do everything at once`, qui lance `phase="all"`).

Trois pannes en découlent directement :
1. **Échec systématique du parcours par défaut (`PDF` seul)** : après `Scan the wiki`, cliquer sur `▶ Generate selection` ou `Generate all` saute l'étape 3, tente de fusionner un dossier `pdf/` vide à l'étape 5, et plante avec `⚠ FAILURE: pipeline produced 0 output files`.
2. **Succès silencieux trompeur en multi-format (`PDF` + `Markdown`/`Text`)** : si l'utilisateur a coché `PDF` et `Markdown`, l'étape 5 produit 0 PDF (`✓ 0 PDF(s)`) mais génère les fichiers `.md`. `produced` n'étant pas vide, le job passe à `Done` (`✓ PIPELINE COMPLETE`) alors qu'**aucun fichier PDF demandé n'a été généré**.
3. **Impossibilité de régénérer des PDF après `Clear PDF cache`** : le bouton `Clear PDF cache` (`purge(jobId, 'pdf')`) supprime `{job_dir}/pdf`. Toute tentative ultérieure de cliquer sur `▶ Generate selection` ou `Generate all` (`phase="generate"`) saute l'étape 3 et échoue.
4. **Absence de Fail Fast dans `convert.py`** : si WeasyPrint échoue sur 100 % des pages (ex. runtime GTK3 absent sous Windows), `scripts/convert.py` affiche les erreurs mais termine avec le code de sortie `0`, laissant le pipeline poursuivre inutilement jusqu'à la fin de l'étape 5.

---

## Impact utilisateur

- **Critique (P0)** : un nouvel utilisateur qui suit exactement le parcours guidé par l'interface (`+ New` → colle l'URL → clique sur le bouton principal bleu `🔍 Step 1 — Scan the wiki` → clique sur le bouton principal bleu `▶ Generate selection`) avec les réglages par défaut (`PDF`) subit **100 % d'échec** après avoir attendu la fin du téléchargement et de l'extraction HTML.
- L'erreur affichée (`⚠ FAILURE: pipeline produced 0 output files`) ne donne aucune indication sur la cause réelle ni sur le moyen de contourner le bug.

---

## Comportement actuel

1. En `phase == "scan"` : les étapes 1, 2 et 4 s'exécutent ; l'étape 3 (`convert.py`) est sautée. `{job_dir}/pdf/` n'existe pas.
2. En `phase == "generate"` : les étapes 1, 2, 3 et 4 sont sautées. L'étape 5 appelle `merge_pdf.py` sur un dossier vide, produit 0 PDF, et fait échouer le job (ou omet silencieusement les PDF si `.md`/`.txt` est aussi coché).
3. `scripts/convert.py` renvoie toujours un code de sortie `0`, même lorsque `ok == 0` et `errors == total`.

---

## Comportement attendu

1. En `phase == "scan"` : l'étape 3 reste sautée (le scan doit rester rapide et dédié à la découverte des catégories).
2. En `phase == "generate"` (comme en `phase == "all"`) : si `want_pdf` est vrai (`"pdf"` dans `EXPORT_FORMATS`), l'étape 3 (`convert.py`) est exécutée sur les pages HTML requises qui n'ont pas encore leur `.pdf` dans `{job_dir}/pdf/`.
3. Si une sélection de catégories est active en `phase == "generate"`, seules les pages appartenant aux groupes retenus (ou à défaut toutes les pages HTML présentes si la sélection n'est pas encore filtrée) ont besoin d'être converties en PDF.
4. Si `want_pdf` est vrai et que `convert.py` ne produit aucun PDF valide (`0` PDF disponible après l'étape 3) ou que `merge_pdf.py` produit `0` fichier PDF, le pipeline échoue immédiatement (Fail Fast) avec un message explicite indiquant la cause (ex. absence du runtime GTK3 / WeasyPrint sous Windows), même si `.md` ou `.txt` est également coché.

---

## Cause probable

Lors de la séparation du pipeline en deux phases (`SCAN` et `GENERATE`, Workstream D de `PLAN.md`), l'auteur a considéré que `GENERATE` correspondait uniquement à l'étape 5 (`if phase in ("scan", "generate"): skip` aux étapes 1, 2, 3, 4), en oubliant que l'étape 3 (`convert.py`) avait déjà été différée pendant `SCAN` et devait donc impérativement tourner lors de `GENERATE` lorsque le format PDF est demandé.

---

## Zones concernées

- `scripts/run.py` : lignes 293-310 (étape 3 `PDF CONVERSION`) et lignes 402-406 (étape 5 `want_pdf`).
- `scripts/convert.py` : lignes 24-76 (`main()`, code de sortie lorsque toutes les conversions échouent).
- `tests/test_run_pipeline.py` : tests d'intégration du pipeline en phase `generate`.

---

## Points d'impact

- **Appelants :** `JobManager.generate()` (`server.py:415-429`), `JobManager.scan()` (`server.py:411-413`), `JobManager.start()` (`server.py:400-409`).
- **Tests existants :** `tests/test_run_pipeline.py` (les tests actuels passent `formats="txt"`, il faut ajouter le cas `formats="pdf"` et `formats="pdf,txt"` en `PHASE="generate"`).
- **Documentation :** `README.md:9-24` et `PLAN.md:107-109` (le comportement réel de l'étape 3 lors de la génération correspondra enfin à la promesse utilisateur).
- **Risque de casse pour les utilisateurs :** aucun ; pour les jobs qui n'utilisent que `.md`/`.txt` (`want_pdf == False`), l'étape 3 reste sautée (`elif not want_pdf:`).

---

## Plan d'action

1. **Dans `scripts/run.py` (lignes 297-310) :**
   - Remplacer la condition `if phase in ("scan", "generate"):` par `if phase == "scan":` afin que l'étape 3 s'exécute en `phase == "generate"` dès lors que `want_pdf` est vrai et que `pdf_count < html_count` (ou `pdf_count == 0`).
   - *Raccourci assumé :* convertir les fichiers HTML manquants de `html_dir` via `convert.py` existant sans filtrer `convert.py` par `selection.json` (`shortcut: convertit tous les HTML non encore en cache PDF lors du premier export PDF, filtrer par stems sélectionnés uniquement si les wikis > 5 000 pages montrent un coût rédhibitoire`). `convert.py` met déjà en cache les `.pdf` dans `{job_dir}/pdf/`, donc les générations suivantes restent instantanées.
2. **Dans `scripts/convert.py` (lignes 70-76) :**
   - Si `ok + resumed == 0` et `errors > 0`, afficher un message d'erreur clair (rappelant l'installation du runtime GTK3 si WeasyPrint ne charge pas les bibliothèques natives) et quitter avec `sys.exit(1)`.
3. **Dans `scripts/run.py` (lignes 402-406) :**
   - Après l'exécution de `merge_pdf.py` lorsque `want_pdf` est vrai, vérifier qu'au moins un fichier `.pdf` a été écrit dans `out_dir` ; sinon, journaliser une erreur explicite et retourner `1` (afin qu'un export `pdf,md` ne masque pas l'absence totale de PDF derrière la présence de fichiers `.md`).
4. **Dans `tests/test_run_pipeline.py` :**
   - Ajouter un test vérifiant qu'après un scan (où `html/*.html` et `category_groups.json` existent mais `pdf/` est absent), lancer `run.py` avec `PHASE="generate"` et `EXPORT_FORMATS="pdf"` exécute l'étape 3 et produit le PDF final.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas exécuter `convert.py` pendant `phase == "scan"` (le scan doit rester rapide et ne pas dépendre de WeasyPrint).
- Ne pas ajouter de nouvelle dépendance ni de nouveau script.

---

## Contraintes

- Préserver le cache incrémental de `convert.py` (`pending = [(s, o) for s, o in all_jobs if not Path(o).exists()]`) pour que les PDF déjà convertis ne soient pas recalculés.
- Préserver le saut complet de l'étape 3 lorsque `PDF` n'est pas coché (`not want_pdf`).

---

## Dépendances

- **À traiter avec ou avant :** `PLAN-UX-02` (suppression de `flatten()` qui corrompt les noms de fichiers entre `convert.py` et `merge_pdf.py`).

---

## Critères d'acceptation

1. Créer un job avec le format par défaut (`PDF`), lancer `Scan` (`PHASE=scan`), puis lancer `Generate` (`PHASE=generate`) produit les fichiers `.pdf` attendus dans `data/output/<slug>/` et termine avec le code `0`.
2. Cliquer sur `Clear PDF cache` (`purge('pdf')`) sur un job terminé puis cliquer sur `▶ Generate selection` régénère les PDF dans `{job_dir}/pdf/` et produit les PDF finaux sans erreur.
3. Si `EXPORT_FORMATS="pdf,md"` et que la génération PDF produit 0 fichier `.pdf`, le job passe en statut `error` (code `1`) au lieu de `done`.
4. La suite `python -m pytest` passe intégralement.

---

## Vérification

1. **Parcours nominal :** Créer un job avec `EXPORT_FORMATS=pdf` → `Scan` → vérifier que `{job_dir}/pdf/` est vide → `Generate selection` → vérifier que l'étape `[3/5] PDF CONVERSION` s'exécute et que `{out_dir}/*.pdf` est créé.
2. **Parcours purge :** Sur ce même job, appeler `POST /api/jobs/{id}/purge` avec `{"scope": "pdf"}` → relancer `Generate` → vérifier la recréation des PDF.
3. **Non-régression `.md`/`.txt` :** Avec `EXPORT_FORMATS=md,txt`, vérifier que `[3/5] PDF CONVERSION` affiche toujours `Skipped -- PDF format not requested`.

---

## Risques

- **Durée de la première génération PDF après scan :** en `PHASE=generate`, si l'utilisateur a coché `PDF`, l'étape 3 tournera lors du premier clic sur `Generate`. C'est le comportement normal et nécessaire puisque le rendu PDF a été différé hors du scan ; la barre de progression (`[3/5] Conversion`) et les logs d'ETA de `convert.py` informeront l'utilisateur en temps réel.
