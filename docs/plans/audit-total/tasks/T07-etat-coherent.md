# T07 — État cohérent : écritures atomiques, arrêt propre, réconciliation

- **Priorité** : P2 · **Axe** : D/G · **Constats couverts** : D15, D16, D17, D18,
  D24, D32, D33, **D47**
- **Justification** : le serveur n'a aucune notion d'état durable cohérent entre
  le disque, la mémoire et les processus. Une coupure (ou un simple Ctrl+C)
  interrompt un dump de 20 minutes au hasard d'un `print`, efface le log de
  l'exécution précédente, et laisse des statuts faux. Rien ne répare au
  redémarrage.

## Preuve et conséquence

- **D15** : aucun `os.replace`, aucun fichier temporaire. Tous les JSON d'état
  sont écrits en place : `extract.py:49-50` (`categories.json` toutes les 50
  articles), `build_categories.py:138-139, 186-187`, `pack_files.py:183`,
  `server.py:106` (`settings.json`), `:306-313` (`jobs.json`), `:418-424`
  (`selection.json`). Pire, `extract.py:42-47` avale l'exception de lecture et
  repart d'un dictionnaire vide : un `categories.json` tronqué fait **re-perdre**
  toutes les catégories déjà collectées, sans un mot.
- **D16** : `server.py:472-524` lance `run.py` dans un thread lecteur ; aucun
  `on_event("shutdown")`. Reproduit partiellement : après `kill -9` du serveur
  (pid 2005), le `run.py` enfant disparaît en < 4 s, tué par la fermeture du tube
  au prochain `print` — donc au milieu d'une écriture possible.
- **D17** : `server.py:315-329` requalifie `running`/`paused` en `stopped` au
  chargement **sans vérifier aucun processus** ; aucun `pid` n'est persisté.
- **D18** : `server.py:400-409` (`start()`) fait `job.logs.clear()` et
  `job.log_file().unlink()` : le log de l'exécution précédente est détruit au
  moment précis où l'on en aurait besoin (« qu'est-ce qui avait échoué ? »).
- **D24** : `run.py:41-49` — `Step.__exit__` affiche `✓ Done in …`
  **inconditionnellement**. Observé dans `run1.log` : `✓ Done in 20s` suivi
  immédiatement de `⚠ FAILURE: pipeline step exited with code 1`.
- **D32** : `server.py:349-363` → `_kill` → `_terminate_tree(timeout=4.0)` →
  `rmtree`, en synchrone dans le handler, pendant que le thread lecteur appelle
  `job.push()` (ouverture du log en append) : fenêtre de course, exception avalée
  par le thread.
- **D33** : `server.py:431-440` / `:442-455` — Pause/Resume sur un job qui n'a
  plus de processus renvoie `ok:true` sans rien faire.
- **D47 (P1, reproduit)** : job `…-002828-452c` — `scan` (pid 2871) → `pause`
  (état `T`) → `generate` (2ᵉ `run.py`, job passé `done`) → `resume` (3ᵉ
  processus) → `stop` renvoie `{"ok":true}` alors que **2871 reste suspendu**
  (arrêté seulement par `kill -9`). `start()` remplace `job._proc` : le pid
  suspendu n'est plus référencé par personne.

## État actuel → état cible

- Toute écriture d'état passe par une primitive unique `write_json_atomic`
  (temporaire + `os.replace`) ; une lecture corrompue **renomme** le fichier en
  `.bad` et journalise, au lieu de repartir silencieusement de zéro.
- Arrêt propre : sur `shutdown`, tous les arbres de processus sont arrêtés
  (`_terminate_tree`), les jobs concernés passés à `stopped` et sauvegardés.
- Réconciliation au démarrage : `pid` + `started_at` persistés ; un job
  `running` sans processus vivant devient `interrupted` (statut affiché
  distinctement, action « Relancer » visible).
- Le log est **versionné** : `{job_id}.1.log`, `{job_id}.2.log`… et `job.logs`
  repart à zéro ; `GET /logs` accepte `?run=n`.
- `Step.__exit__` distingue succès et échec (`✗ Failed after Xs`).
- `delete()` d'un job en cours : marque `stopped`, attend la fin du thread
  lecteur (`join`, 5 s), puis tue et supprime ; en cas d'échec, 409.

## Cause racine et sites concernés

Trois états cohabitent sans source de vérité : mémoire (`self.jobs`), disque
(`jobs.json`, `job.json`, JSON d'étape), système (`Popen`/PID). Aucune
sérialisation, aucune réconciliation, aucune écriture atomique.
Sites : `server.py:106, 191-225, 306-329, 349-363, 400-409, 431-455, 472-524`,
`scripts/extract.py:42-50`, `scripts/build_categories.py:138-139, 186-187`,
`scripts/pack_files.py:183`, `scripts/run.py:41-49`.

## Référence à réutiliser

- `Job.save()`/`_load()` (`server.py:191-225, 306-329`) centralisent déjà la
  persistance : la primitive atomique s'y branche.
- `_terminate_tree` (`server.py`) existe et gère déjà SIGTERM → SIGKILL : le
  réutiliser pour `shutdown` et `delete`.
- `Step` (`run.py:33-49`) est le seul formateur de durée d'étape : une seule
  modification suffit pour D24.

## Plan d'action

1. `scripts/wiki_names.py` (ou `scripts/jsonio.py`, nouveau, 10 lignes) :
   `write_json_atomic(path, obj)` (même dossier, `os.replace`, `fsync` optionnel).
   L'utiliser dans les 7 sites listés ; `run.py` et `server.py` partagent le
   module via `sys.path` (déjà le cas pour `wiki_names`).
2. `extract.py:42-47` : sur `JSONDecodeError`, copier le fichier en
   `categories.json.bad-<ts>` puis **échouer** (`return 1`) si le fichier est
   non vide ; ne repartir de zéro que s'il est vide.
3. `server.py` : `Job.save()` → `write_json_atomic` ; idem `settings.save()`.
4. `server.py` : ajouter un `lifespan` FastAPI (ou `on_event("shutdown")`) qui
   itère les jobs `running`/`paused`, appelle `_terminate_tree`, met
   `status="stopped"` et `save()`.
5. `server.py:_load` : persister `pid` dans `job.json` au démarrage du process ;
   au chargement, `if status in ("running","paused") and not _pid_alive(pid):
   status = "interrupted"`. `_pid_alive` : `os.kill(pid,0)` (POSIX) et
   `OpenProcess` non disponible sans dépendance → sous Windows, se contenter de
   `interrupted` (jamais `running` fantôme).
6. `server.py:start()` : avant `unlink()`, `shutil.move(log, log.with_suffix(
   f".{n}.log"))` en incrémentant `n` (stocké dans `job.json`) ; `GET /logs`
   accepte `?run=` ; le client garde le dernier par défaut.
7. `run.py:Step` : `if exc_type: log(f"✗ Failed after {s}s") else: log(f"✓ Done in {s}s")`.
8. `server.py:delete()` : `job.status="stopped"`, `_kill`, `thread.join(5)`
   (stocker le thread sur le job), puis `rmtree` ; si le thread ne meurt pas →
   `409 {"error":"job still shutting down"}`.
9. UI : accepter le statut `interrupted` (badge gris `⚠ Interrupted`), bouton
   « Relancer » ; Pause/Resume renvoient `{ok:false, error:…}` si aucun
   processus.
10. `Job` : `_procs: set[Popen]` au lieu de `_proc` ; `start()` refusé (409) si
    un pid de la liste est vivant ; `pause`/`resume`/`stop`/`delete` itèrent sur
    la liste (`_terminate_tree` pour chacun). Purger un pid mort au passage
    (`Popen.poll()`).

## Points d'impact

`server.py` (`save`, `_load`, `start`, `stop`, `delete`, `_run`, `logs`),
`scripts/extract.py`, `scripts/build_categories.py`, `scripts/pack_files.py`,
`scripts/run.py`, `scripts/wiki_names.py` (ou nouveau `scripts/jsonio.py`), JS
(`renderJob`, `fetchLogs`), README (§« Jobs and state »). Tests :
`tests/test_server_config.py` (settings), `tests/test_run_pipeline.py` (écritures).

## Régression

Aucune fonctionnelle : les formats de fichiers ne changent pas (mêmes noms,
mêmes contenus). Deux points à surveiller :
(a) les logs changent de nom → `job.logs` doit rester la source d'affichage
lue par le client ; (b) le nouveau statut `interrupted` doit être géré par toute
branche `if status == "running"` (vérifier le JS : `renderJob`, `updateGenInfo`,
`canGenerate`).
Régression **assumée** : `interrupted` n'est pas un statut antérieur, donc un
client tiers qui ne connaît que 4 statuts affichera un badge inconnu — le
serveur renvoie aussi `status_label`. Aucun client tiers n'est documenté
(vérifié : le README ne documente pas l'API).

## Actions humaines requises

Aucune.

## Dépendances

T01 (tests de caractérisation). T03 avant (les chemins de sortie entrent dans
`purge`/`delete`).

## Non-objectifs

- Pas de reprise automatique d'un job interrompu (coût d'un `--resume`
  inattendu > coût d'un clic).
- Pas de base de données ni de journal transactionnel : `os.replace` suffit.
- Pas de détachement du pipeline via `setsid`/service (hors périmètre d'un plan
  P2 ; à traiter si le besoin « fermer la fenêtre pendant 45 min » est confirmé).

## Critères d'acceptation

1. `kill -9` du serveur pendant un run → au redémarrage le job est
   `interrupted`, jamais `running`.
2. `Ctrl+C` (SIGINT) sur le serveur → `run.py` arrêté dans les 5 s, job
   `stopped`, log conservé.
3. `settings.json` tronqué à la main → démarrage réussi, fichier renommé
   `.bad`, valeurs par défaut.
4. Deux exécutions successives → deux fichiers de log, l'UI affiche la dernière.
5. Étape en échec → `✗ Failed after Xs` (jamais `✓ Done`).
6. `DELETE` d'un job en cours → 200 seulement une fois le processus disparu.
7. Test de T01 vert.

## Vérification et repli

`kill -9`, `kill -INT`, `truncate -s 10 settings.json`, `ps`, deux runs.
Repli : `git revert` point par point (les 9 étapes sont indépendantes, sauf 1
qui précède 3/5).
