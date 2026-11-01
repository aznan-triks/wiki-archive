# [P1] PLAN-UX-06 — Reprise (`Resume`) défectueuse : étape 2 sautée dès 1 fichier HTML, dump XML partiel non repris, et flags `clean`/`rerender` persistants qui effacent tout

- **Type :** bug / fonctionnel / perte de données
- **Preuve :**
  - *Confirmé à l'exécution* :
    - Création d'un `wiki.xml` contenant 3 articles (`P0`, `P1`, `P2`) et d'un dossier `html/` contenant uniquement `P0.html` (simulation d'un arrêt `⏹ Stop` pendant l'étape 2). L'exécution de `scripts/run.py` journalise `[2/5] HTML EXTRACTION : ↩ Step already complete -- skipped (1 HTML files already present)` et termine le pipeline sans jamais extraire `P1` ni `P2`.
  - *Déduit du code* :
    - `scripts/run.py:204-207` (`if existing_xml and config_json.exists(): skip_step(...)`, alors que `wikiteam3dumpgenerator` crée le fichier `.xml` et `config.json` dès le début du téléchargement, rendant le bloc `--resume` des lignes 242-246 inatteignable dès que le fichier `.xml` partiel existe)
    - `scripts/run.py:273-277` (`elif html_count > 0: skip_step(...)`, ce qui court-circuite toute la logique de reprise article par article codée dans `scripts/extract.py:225-232`)
    - `server.py:483-484` et `scripts/run.py:185-193` (`clean` et `rerender` sont stockés de façon permanente dans `job.params`, donc tout appel ultérieur à `Resume` ou `Scan` ré-exécute `shutil.rmtree(dump_dir, html_dir, ...)` !)
    - `server.py:453-454` (`resume()` sur un job `stopped` ou `error` appelle `self.start(job_id)` avec `phase="all"` au lieu de reprendre la phase `scan` ou `generate` interrompue, et `scripts/run.py:370` ignore `selection.json` lorsque `phase != "generate"`)

---

## Problème

Le projet met en avant la capacité d'arrêter et de reprendre un job à tout moment sans perte de données (`README.md:33, 94-95`, `PLAN.md` Workstream A). En réalité, quatre bugs cassent la reprise (`Resume`) :

### 1. Arrêter pendant l'étape 2 (`HTML extraction`) puis reprendre ignore toutes les pages restantes
`scripts/extract.py` (lignes 225-232) a été spécialement conçu pour reprendre page par page (`if outfile.exists(): resumed += 1`).
Mais dans `scripts/run.py:276-277` :
```python
elif html_count > 0:
    skip_step(f"{html_count} HTML files already present")
```
Dès qu'**un seul** fichier `.html` a été écrit avant que l'utilisateur ne clique sur `⏹ Stop` (par exemple 5 pages extraites sur 2 000), toute relance (`Resume`, `Scan` ou `Do everything at once`) saute intégralement l'étape 2 ! Les 1 995 pages restantes du dump XML ne sont jamais extraites.

### 2. Arrêter pendant l'étape 1 (`Wiki dump`) puis reprendre saute `wikiteam3 --resume` et plante sur un XML tronqué
Pendant le dump, `wikiteam3dumpgenerator` crée immédiatement `config.json` et écrit au fil de l'eau le fichier `<wiki>-<date>-current.xml`. Tant que le dump n'est pas terminé, ce fichier `.xml` ne contient pas la balise fermante `</mediawiki>`.
Or `scripts/run.py:204-207` teste uniquement :
```python
existing_xml = sorted(p for p in dump_dir.glob("*.xml") if not p.name.endswith(".7z")) if dump_dir.exists() else []
if existing_xml and config_json.exists():
    xml_file = existing_xml[0]
    skip_step(f"XML found: {xml_file} ({human_size(xml_file)})")
```
Comme le fichier `.xml` partiel existe déjà, `run.py` croit le dump terminé, n'atteint jamais les lignes 242-246 (`dump_args.append("--resume")`), et passe le fichier XML tronqué à `extract.py:214`, qui plante avec une trace Python brute `xml.etree.ElementTree.ParseError: no element found`.

### 3. Les options `New full dump (wipes everything)` et `Re-render output` restent actives à vie sur le job
Lorsqu'un utilisateur coche `New full dump (wipes everything)` (`clean: true`) ou `Re-render output` (`rerender: true`) pour relancer un job proprement :
- `ensureJob()` (`server.py:1413`) enregistre `clean: true` / `rerender: true` dans `job.params` (`jobs.json`).
- Rien ne remet jamais `clean` ou `rerender` à `False` après le nettoyage initial !
- Si l'utilisateur clique sur `⏹ Stop` au milieu du nouveau téléchargement (ou si le serveur redémarre) puis clique sur `▶ Resume`, `server.py:483-484` repasse `CLEAN=true` à `run.py`, qui **supprime tout le dossier `dump/` et `html/` qu'on venait de télécharger** au lieu de reprendre !

### 4. `Resume` oublie la phase (`scan` vs `generate`) et `phase="all"` ignore `selection.json`
- Dans `server.py:453-454`, `resume()` appelle `self.start(job_id)` qui force `phase="all"`. Si l'utilisateur avait lancé un `Scan` (`phase="scan"`), `Resume` lance le pipeline complet (`phase="all"`) au lieu de terminer le scan.
- Dans `scripts/run.py:370`, la sélection de catégories n'est appliquée que si `phase == "generate"`. Si un job possédant une `selection.json` est relancé via `Resume` (`phase="all"`), sa sélection est ignorée et tout le wiki est exporté.

---

## Impact utilisateur

- **Majeur (P1) :**
  - L'arrêt (`⏹ Stop`) suivi d'une reprise (`▶ Resume`) — fonctionnalité centrale pour des traitements de 30 minutes à plusieurs heures — produit soit un wiki tronqué aux quelques pages extraites avant l'arrêt, soit un crash `ParseError` XML, soit l'effacement complet des données si `New full dump` avait été coché au départ.

---

## Comportement actuel

1. `run.py` saute l'étape 1 dès qu'un fichier `.xml` (même incomplet) existe.
2. `run.py` saute l'étape 2 dès qu'au moins 1 fichier `.html` existe.
3. `clean` et `rerender` restent à `True` dans `job.params` sur toutes les exécutions suivantes du job.
4. `resume()` repart toujours en `phase="all"` et `run.py` ignore `selection.json` en `phase="all"`.

---

## Comportement attendu

1. **Étape 1 (Dump XML) :** un fichier `.xml` existant n'est considéré comme complet que s'il se termine par `</mediawiki>` (vérifiable en lisant les 256 derniers octets du fichier, en temps constant $O(1)$). S'il est incomplet, l'étape 1 n'est pas sautée et `wikiteam3dumpgenerator --resume` est appelé.
2. **Étape 2 (Extraction HTML) :** `extract.py` écrit un fichier marqueur `{job_dir}/html/.complete` uniquement lorsque la boucle `ET.iterparse` s'est terminée normalement (et `run.py` supprime ce marqueur si un nouveau dump a eu lieu). Tant que `{job_dir}/html/.complete` n'existe pas, `run.py` lance `extract.py` qui reprend automatiquement à partir des fichiers `.html` déjà présents (`resumed += 1`).
3. **Options `clean` / `rerender` :** dès que `JobManager._run()` a démarré le job avec `clean=True` ou `rerender=True`, ces deux drapeaux one-shot sont remis à `False` dans `job.params` et sauvegardés via `self._save()`, afin qu'un `Resume` ultérieur ne ré-efface jamais les données.
4. **Mémorisation de la phase et respect de `selection.json` :**
   - `Job` mémorise `last_phase` (ou `phase` dans `job.params` / `jobs.json`, par défaut `"all"`) pour que `resume()` sur un job `stopped`/`error` relance la même phase (`scan`, `generate` ou `all`).
   - Dans `scripts/run.py:370`, appliquer `selection_file` dès que `phase in ("generate", "all") and selection_file.exists() and selection_file.stat().st_size > 0`.

---

## Cause probable

- `html_count > 0` (`scripts/run.py:276`) était une approximation rapide portée depuis l'ancien `run.sh`, sans vérifier si `extract.py` était allé jusqu'au bout du fichier XML.
- `existing_xml and config_json.exists()` (`scripts/run.py:205`) a été placé en amont du bloc `if config_json.exists(): dump_args.append("--resume")` (ligne 242), rendant ce dernier inatteignable dès la création du fichier `.xml` par `wikiteam3`.

---

## Zones concernées

- `scripts/run.py` : lignes 204-208 (vérification de fin de fichier XML `</mediawiki>`), lignes 273-291 (vérification du marqueur `html_dir / ".complete"`), ligne 370 (application de `selection_file` en `phase in ("generate", "all")`).
- `scripts/extract.py` : lignes 269-275 (écriture de `DEST / ".complete"` en fin d'extraction réussie, et gestion propre de `ET.ParseError` avec message clair au lieu d'un traceback brut).
- `server.py` : lignes 400-414, 442-455, 483-496 (réinitialisation de `clean`/`rerender` après lancement et reprise de la phase courante dans `resume()`).
- `tests/test_run_pipeline.py` et `tests/test_extract_fallback.py`.

---

## Points d'impact

- ** Appelants :** `scripts/run.py`, `scripts/extract.py`, `server.py::JobManager`.
- **Tests existants :**
  - `tests/test_run_pipeline.py:48-63` (`test_generate_produces_files_and_exits_zero`) utilise `PHASE="generate"`, où l'étape 2 est sautée (`if phase == "generate":`), donc il n'a pas besoin du marqueur `.complete`.
  - `tests/test_extract_fallback.py` : vérifier que `extract.py` crée bien `html/.complete` en fin d'exécution.
- **Jobs existants sur le disque :** si un job existant a déjà un dossier `html/` complet sans `.complete` mais est relancé en `phase="scan"` ou `phase="all"`, `extract.py` parcourra le XML en mode `resumed` sans ré-extraire les `.html` existants, puis posera `.complete`.

---

## Plan d'action

1. **Vérifier la complétude du XML à l'étape 1 (`scripts/run.py:204-208`) :**
   - Ajouter une fonction `is_xml_complete(p: Path) -> bool` qui lit les 512 derniers octets de `p` et vérifie la présence de `b"</mediawiki>"`.
   - Ne sauter l'étape 1 (`skip_step`) que si `existing_xml and config_json.exists() and is_xml_complete(existing_xml[0])`. Sinon, entrer dans le bloc d'exécution où `config_json.exists()` ajoutera `--resume` à `wikiteam3dumpgenerator`.
2. **Assurer la reprise complète de l'étape 2 (`scripts/extract.py` et `scripts/run.py:273-291`) :**
   - Dans `scripts/extract.py`, entourer la boucle `ET.iterparse` d'un `try ... except ET.ParseError as exc:` qui affiche un message clair (`"✗ XML dump is incomplete or corrupted -- resume or re-run the dump"`) et quitte avec `sys.exit(1)` (zéro traceback brut).
   - À la toute fin de `scripts/extract.py` (après `save_categories()`), écrire `(DEST / ".complete").write_text(str(count + resumed), encoding="utf-8")`.
   - Dans `scripts/run.py:276`, remplacer `elif html_count > 0:` par `elif html_count > 0 and (html_dir / ".complete").exists():`.
3. **Réinitialiser les drapeaux one-shot `clean` et `rerender` (`server.py:472-500`) :**
   - Dans `JobManager._run()`, après avoir lu `job.params.get("clean")` et `job.params.get("rerender")` pour construire `env`, si l'un des deux vaut `True` et que `phase != "generate"`, remettre `job.params["clean"] = False` et `job.params["rerender"] = False` puis appeler `self._save()`.
4. **Conserver la phase lors d'un `Resume` (`server.py:400-455`) et respecter `selection.json` (`scripts/run.py:370`) :**
   - Stocker `job.params["last_phase"] = phase` dans `JobManager.start()` et l'utiliser dans `JobManager.resume()` (`self.start(job_id, phase=job.params.get("last_phase", "all"))`).
   - Dans `scripts/run.py:370`, remplacer `if phase == "generate" and ...` par `if phase in ("generate", "all") and ...`.
5. **Ajouter les tests dans `tests/test_run_pipeline.py` et `tests/test_extract_fallback.py` :**
   - Tester qu'une extraction partielle (1 HTML sur 3, sans `.complete`) reprend et extrait les 2 pages manquantes lors de la relance de `run.py`.
   - Tester qu'un `wiki.xml` tronqué (sans `</mediawiki>`) n'est pas considéré comme terminé à l'étape 1 et produit un message d'erreur propre (sans traceback) s'il est passé à `extract.py`.

### Non-objectifs (ce qu'il ne faut PAS faire)
- Ne pas modifier le format de `jobs.json` avec de nouvelles colonnes de premier niveau (utiliser `job.params` qui est déjà persisté tel quel).

---

## Contraintes

- `human_size` et le comptage des fichiers `.html` (`glob("*.html")`) ignorent déjà `.complete` (qui ne se termine pas par `.html`).

---

## Dépendances

- Peut être exécuté indépendamment ; s'accorde avec `PLAN-UX-01` sur `scripts/run.py`.

---

## Critères d'acceptation

1. Si l'étape 2 est interrompue après 1 page sur 3, relancer le job extrait les 2 pages restantes et crée les 3 fichiers `.html` ainsi que `.complete`.
2. Si `clean=True` ou `rerender=True` est coché lors du lancement, `job.params["clean"]` et `job.params["rerender"]` repassent automatiquement à `False` une fois le lancement pris en compte, de sorte qu'un `Stop` suivi de `Resume` ne supprime pas les données téléchargées.
3. Un `wiki.xml` tronqué passé à `extract.py` quitte avec le code `1` et un message lisible sans traceback Python brut.

---

## Vérification

1. Exécuter `python -m pytest`.
2. Rejouer le scénario d'interruption d'extraction (`P0.html` présent, `P1`/`P2` absents dans `html/`) et vérifier que les 3 pages sont présentes après relance.

---

## Risques

- Faible : sur un job créé avant cette mise à jour où `html/` est déjà complet mais `.complete` absent, une relance en phase `scan`/`all` parcourra une fois `extract.py` en mode `resumed` (sans appel réseau si `categories.json` a déjà toutes les pages) et créera `.complete`.
