# T03 — Une sortie par job : arrêter les destructions croisées

- **Priorité** : P0 · **Axe** : D/H · **Constats couverts** : D02, D14
- **Justification** : deux archivages du même wiki s'effacent mutuellement ;
  supprimer un job détruit les fichiers d'un autre. Perte de données silencieuse.

## Preuve et conséquence

Reproduit et mesuré : job A génère `Weapons.md/.txt` ; job B (même URL) génère
`Pistols` → `data/output/127.0.0.1/` ne contient plus que `Pistols.md` et l'API
annonce `[Pistols.md]` **pour les deux jobs** (A reste `done`). Puis
`bulk_delete` de B → le dossier disparaît et A renvoie `files: []` alors que
`status` vaut toujours `done`.

## État actuel → état cible

- Actuel : `scripts/run.py:163-164` (`out_dir = data_dir/"output"/slug`),
  `run.py:395-398` (le dossier est vidé au début de l'étape 5),
  `server.py:176` (`merged_dir()` identique), `server.py:236-247` (listing),
  `server.py:349-363` (`delete()` → `rmtree(job.merged_dir())`).
- Cible : `data/output/{slug}/{job_id}/` par job ; `out_path` pointe dessus ;
  `delete()` ne supprime que ce sous-dossier (puis le parent s'il devient vide).

## Cause racine et sites concernés

Le dossier de sortie est dérivé de l'URL seule alors que l'unité de travail est
le job. Sites : `run.py:164` (écriture), `run.py:395-398` (nettoyage),
`server.py:176` (listing), `server.py:228` (`out_path`), `server.py:349-363`
(suppression), README §« Data structure » et §« 5-step pipeline » (chemins cités).

## Référence à réutiliser

`Job.job_dir()` (`server.py:149`) applique déjà `{racine}/{job_id}`.
`_host_path()` (`server.py:129-137`) gère l'affichage Windows/Unix : inchangé.

## Plan d'action

1. `server.py:176` : `merged_dir()` → `DATA_DIR/"output"/self.wiki_slug()/self.id`.
2. `scripts/run.py:164` : `out_dir = data_dir/"output"/slug/Path(job_dir).name`.
3. `delete()` : supprimer `merged_dir()` puis `rmdir` du parent (ignorer l'échec
   s'il reste des jobs).
4. README : remplacer `data/output/{wiki-hostname}/` par
   `data/output/{wiki-hostname}/{job-id}/` (intro, §5, « Data structure »,
   « Copy path »).
5. Migration douce : au chargement, si l'ancien dossier plat contient des
   fichiers, ne rien déplacer (attribution ambiguë) ; le prochain run du job
   journalise « ancien dossier plat détecté : la prochaine génération écrira
   dans …/{job_id}/ ».

## Points d'impact

`server.py` (`merged_dir`, `delete`), `scripts/run.py` (une ligne), README,
`docs/`. Tests : `tests/test_server_config.py::test_host_path_and_human_size`,
`tests/test_run_pipeline.py` (chemin de sortie attendu). `HOST_PROJECT_DIR` et
« Copy path » continuent de fonctionner (chemin relatif préfixé).

## Régression

**Assumée et à valider par un humain** : le chemin gagne un niveau (les habitudes
`data/output/<wiki>/` changent). Justification : sans cela la perte de données
est certaine dès le deuxième job sur le même wiki. Atténuation : (a) message
explicite dans le README et dans la carte Files ; (b) option
`FLAT_OUTPUT=1` pour conserver l'ancien comportement, documentée comme non sûre
et déconseillée.

## Actions humaines requises

Valider la régression assumée (changement de chemin) avant exécution.

## Dépendances

T01 avant ; à faire avant T11 (les tests de parité portent sur les chemins).

## Non-objectifs

- Aucun déplacement automatique des anciennes sorties (risque d'attribution
  erronée).
- Pas de lien symbolique de compatibilité (fragile sous Windows).

## Critères d'acceptation

1. Deux jobs du même wiki → deux dossiers, chacun listant ses propres fichiers.
2. `bulk_delete` d'un job laisse l'autre intact (fichiers **et** statut).
3. `delete` nettoie le parent s'il devient vide.
4. Test de T01 vert.

## Vérification et repli

Rejouer la séquence A/B de l'audit (deux jobs, deux générations, suppression de
B) et vérifier disque + `GET /api/jobs`. Repli : `git revert` + `FLAT_OUTPUT=1`.
