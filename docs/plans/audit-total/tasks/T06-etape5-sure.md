# T06 — Étape 5 sûre : ne jamais détruire une sortie valide

- **Priorité** : P1 (D04) + P2 (D19, D20, D21, D42) · **Axe** : D/F
- **Constats couverts** : D04, D19, D20, D21, D42
- **Justification** : l'étape qui produit les fichiers commence par effacer les
  précédents, puis peut échouer ; trois scripts de cette étape masquent leurs
  échecs (code de sortie 0, exceptions ignorées, fichiers sautés).

## Preuve et conséquence

- **D04 (P1)** : `POST /generate {"formats":"none"}` → `Cleaning previous
  output: …`, puis `✗ Unknown format(s): none`, job `error`, **dossier de sortie
  vide**. La sortie valide de la génération précédente a disparu.
- **D19** : `purge()` utilise `ignore_errors=True` puis renvoie
  `{"ok": true, "freed_human": …}` même si rien n'a été supprimé (mesuré :
  `pdf` sur un job sans PDF → `{"ok":true,"freed_human":"0 KB"}`).
- **D20** : `merge_pdf.py:98-103` saute un PDF illisible et compte un succès.
- **D21** : `convert.py` n'a pas de code de retour → 200 conversions échouées
  donnent `exit 0`.
- **D42** : `run.py:75-97` copie tous les PDF dans `flat/` avant de fusionner →
  doublement temporaire de l'occupation disque (3 Go → 6 Go).

## État actuel → état cible

- **Cible 1** : les formats sont validés **avant** tout nettoyage ; `none` est
  refusé avec 400 (« choose at least one format »).
- **Cible 2** : l'étape 5 écrit dans `out_dir/.tmp-{pid}/` puis `os.replace()`
  vers `out_dir/` (ou vers un sous-dossier daté). Un échec laisse la sortie
  précédente intacte.
- **Cible 3** : `merge_pdf.py` fait échouer la catégorie si un PDF n'a pas pu
  être ajouté ; `convert.py` sort en code 1 si `errors > 0` ; `purge()` remonte
  les erreurs de suppression par cible.
- **Cible 4** : `merge_pdf.py` reçoit un index `stem → chemin` (dict JSON) au
  lieu d'un dossier de copies.

## Cause racine et sites concernés

Absence de transaction sur une opération destructive (effacement puis écriture),
et absence de contrat d'échec dans les scripts d'export. Sites :
`run.py:394-413` (séquence nettoyage → merge → export), `run.py:75-97`
(`flatten`), `run.py:150-156` (validation des formats, trop tardive),
`server.py:376-398` (`purge`), `scripts/merge_pdf.py:94-114`,
`scripts/convert.py:186-192`.

## Référence à réutiliser

- `export_categories.py:161-165` et `merge_pdf.py:45-52` savent déjà échouer
  proprement (format inconnu, JSON illisible) : le même style de garde.
- `pikepdf` (`merge_pdf.py:19`) accepte des chemins quelconques : aucun besoin
  d'un dossier aplati.
- `shutil.move`/`os.replace` suffisent pour publier le dossier temporaire.

## Plan d'action

1. `run.py` : valider `EXPORT_FORMATS` en tête de `main()` (ensemble
   `{pdf,md,txt}` ; `all` → les trois ; `none` ou vide → `log(FAILURE)` +
   `return 1`) **avant** de toucher `out_dir`.
2. `run.py` : `tmp_out = out_dir.with_name(out_dir.name + f".tmp{os.getpid()}")`,
   `shutil.rmtree(tmp_out, ignore_errors=True)`, écrire dedans, puis
   `shutil.rmtree(out_dir)` + `os.replace(tmp_out, out_dir)` en cas de succès ;
   en cas d'exception, supprimer `tmp_out` et laisser `out_dir` intact.
3. `run.py` : remplacer `flatten()` par l'écriture d'un index JSON
   (`flat/index.json`, `{stem: chemin absolu}`) et adapter `merge_pdf.py` pour
   accepter ce fichier (rétro-compatibilité : si l'argument est un dossier,
   comportement actuel).
4. `merge_pdf.py` : compter `added` et `expected` ; si `len(chunk) != added`,
   écrire un récapitulatif `⚠ N articles omis` et `sys.exit(1)`.
5. `convert.py` : `sys.exit(1 if errors else 0)` et message final citant la
   première erreur + le lien GTK3 (déjà dans le README).
6. `server.py:purge` : supprimer `ignore_errors=True`, renvoyer
   `{ok:false, errors:[{path, error}]}` en cas d'échec partiel ; le client
   (`purge()` JS) affiche déjà `r.error`.
7. Adapter `tests/test_merge_pdf.py` (index JSON) et `tests/test_run_pipeline.py`
   (dossier temporaire).

## Points d'impact

`scripts/run.py`, `scripts/merge_pdf.py`, `scripts/convert.py`, `server.py`
(`purge`), `tests/test_merge_pdf.py`, `tests/test_run_pipeline.py`.
La commande documentée dans le README (`docker compose exec … export_categories.py
… <out_dir> txt,md`) reste valable : `export_categories.py` reçoit toujours un
chemin de dossier (seul `merge_pdf.py` change d'entrée).

## Régression

Aucune sur les cas nominaux (la sortie finale est identique octet pour octet ;
seul le chemin temporaire change). Point d'attention : `out_dir` peut être monté
en volume — `os.replace` est atomique sur le même système de fichiers, ce qui est
le cas ici (même volume). Vérifier sous Windows (renommage d'un dossier ouvert →
échec) : ajouter une reprise (`shutil.move`) si `os.replace` échoue.

## Actions humaines requises

Aucune.

## Dépendances

T01, T03 (le dossier de sortie doit être par job avant d'introduire un dossier
temporaire).

## Non-objectifs

- Pas de versionnage des sorties (garder N générations) : YAGNI.
- Pas de reprise partielle de l'étape 5 (relancer suffit).

## Critères d'acceptation

1. `formats:"none"` → 400 côté API, **sortie précédente intacte**.
2. Échec simulé de `export_categories.py` (HTML supprimé) → l'ancienne sortie
   est toujours là, job `error`, message explicite.
3. Un PDF unitaire corrompu → code 1 de `merge_pdf.py`, fichier nommé dans le
   log.
4. `convert.py` sans WeasyPrint → code 1, message citant GTK3.
5. Occupation disque de l'étape 5 divisée par ~2 (mesure avant/après sur 200
   PDF synthétiques).

## Vérification et repli

Comparer les sorties avant/après sur le faux wiki (`diff -r`) et mesurer
`du -sh` de l'étape 5. Repli : `git revert` par point (1 à 6 indépendants).
