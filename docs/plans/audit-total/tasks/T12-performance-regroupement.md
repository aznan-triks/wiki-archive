# T12 — Performances : regroupement, aperçu et flux de logs

- **Priorité** : P1 (F01) + P2 (F02, F04) + P4 (F13) · **Axe** : F
- **Constats couverts** : F01, F02, F04, F05 (annexe), F13
- **Justification** : mesuré : le regroupement passe de 120 ms (800 cat.) à 3,5 s
  (4 000 cat.) — croissance quadratique — et l'aperçu, relancé à chaque clic dans
  l'arbre, **bloque le serveur entier** : pendant 4,5 s, `GET /api/jobs` ne
  répond plus.

## Preuve et conséquence

Mesures (3 répétitions, médiane, même machine, `.venv` Python 3.12) :

| Charge | `pack_files` | `preview_packing` (HTTP) |
|---|---|---|
| 800 cat. / 3 000 pages (6 058 affectations) | 116 / 120 / 121 ms | — |
| 3 998 cat. / 20 000 pages (39 941 affectations) | 3 489 / 3 569 / 3 732 ms | 3,94 / 4,42 / 4,55 s |

- **F01** : ×5 catégories → ×30 de temps ⇒ O(k²) (boucle gloutonne :
  `pack_files.py:137-157`, un seul couple fusionné par tour, tri complet de
  `packed` à chaque tour, `sorted(set(p1)|set(p2))` à chaque fusion).
- **Blocage** : pendant un aperçu, `GET /api/jobs` renvoie **000** (connexion non
  servie) contre 200 en 7 ms au repos. `asyncio.to_thread` ne rend pas la main :
  la boucle d'événements attend le `await` d'un thread qui tient le GIL.
- **F13** : 4 aperçus concurrents → **25,4 / 27,1 / 28,6 / 28,9 s** (parallèle
  idéal ≈ 4,6 s ; séquentiel ≈ 18 s) : la contention GIL est pire que la
  sérialisation.
- **F02** : chaque aperçu relit et reparse 3 JSON (~1,7 Mo cumulés), à chaque
  frappe/changement de sélection (debounce 350 ms, `server.py:1796-1814`).
- **F04** : `flushLogs` est déclenché par `requestAnimationFrame`
  (`server.py:1907-1931`) — suspendu pour un onglet en arrière-plan, donc
  `logBuffer` croît sans limite pendant un job de 45 min.

## État actuel → état cible

- `build_packing` en O(k log k) : 3 998 catégories < 300 ms, 20 000 < 800 ms.
- L'aperçu ne bloque jamais la boucle : < 100 ms par appel après cache, et jamais
  plus de 1 calculateur actif (les requêtes obsolètes sont annulées).
- Un seul chargement des JSON par `(job_id, mtime)`, partagé entre aperçus.
- Le flux de logs est piloté par un `setInterval` plafonné, indépendant de la
  visibilité de l'onglet.

## Cause racine et sites concernés

1. **Algorithme** : fusion gloutonne naïve avec recalcul complet à chaque tour
   (`pack_files.py:137-157`).
2. **I/O** : aucun cache des JSON d'étape (`server.py:530-556`).
3. **Concurrence** : `await asyncio.to_thread(...)` (`server.py:713`) sur du
   Python pur CPU-bound ⇒ le GIL reste tenu par le thread pendant tout le calcul,
   ce qui gèle la boucle.
4. **Rendu** : `requestAnimationFrame` comme horloge de vidage
   (`server.py:1907-1910`).

## Référence à réutiliser

- `category_groups.json` est déjà un `{cat: [stems]}` : une structure
  d'index inversé (`stem → frozenset(cats)`) se construit en un passage et permet
  de fusionner **par** page plutôt que **par** catégorie.
- `MAX_FILES` borne le nombre de fichiers finaux : c'est le paramètre qui doit
  guider la fusion.
- Le debounce de 350 ms existe déjà (`server.py:1796-1814`) : il suffit de
  l'accompagner d'une annulation.

## Plan d'action

1. Réécrire `pack_files.pack()` en trois passes :
   a. index `page → frozenset(catégories)` (un seul parcours) ;
   b. tant que `len(groups) > max_files` : choisir le couple de groupes
      **adjacents** (partageant au moins une page) minimisant
      `len(a)+len(b)` via un tas (`heapq`) et une carte d'adjacence, puis fusionner
      et mettre à jour les voisins — chaque fusion coûte O(deg × log n), pas un
      tri complet ;
   c. nommer les groupes (cf. T04).
   Objectif mesurable : 3 998 cat. < 300 ms.
2. `server.py` : cache `_step_cache[(job_id, mtime, name)] → objet` avec verrou,
   invalidé par `mtime` ; `_packing_preview` ne lit plus qu'une fois par
   modification.
3. `server.py` : remplacer `await asyncio.to_thread` par un
   `ProcessPoolExecutor(max_workers=1)` (ou `run_in_executor` sur un pool dédié
   de 1) + `asyncio.Lock` par job : une seule requête d'aperçu en vol, les autres
   attendent le résultat du même calcul (clé = hash de la sélection) ; renvoyer
   `204`/`429` si plus de 2 requêtes en attente.
4. JS : `AbortController` sur la requête d'aperçu précédente ; ne pas lancer de
   nouvel aperçu tant que le précédent n'est pas revenu (indicateur « calcul… »).
5. `flushLogs` : `setInterval(flushLogs, 250)` démarré au premier log, arrêté
   quand la file est vide ; plafonner `logBuffer` à 5 000 lignes (garder les
   dernières) ; plafonner le DOM à 5 000 `div` (`term.removeChild(firstChild)`
   au-delà) — F05 traité au passage.
6. Test de performance minimal (`tests/test_pack_perf.py`, marqué `slow`,
   exclu par défaut) : 4 000 catégories / 20 000 pages < 1 s.

## Points d'impact

`scripts/pack_files.py` (réécriture de `pack`), `server.py` (`_packing_preview`,
`preview_packing`, JS logs et aperçu), éventuellement `run.py` (même fonction
appelée). Tests : `tests/test_run_pipeline.py` (noms de fichiers produits),
nouveau test de perf.

## Régression

Aucune sur le résultat : les assertions de non-régression portent sur
`preview_packing` == fichiers produits (T11) et sur l'invariant « chaque catégorie
apparaît dans un fichier », « le nombre de fichiers ≤ `max_files` ». La
**répartition** des catégories entre fichiers peut changer (l'algorithme choisit
d'autres couples) — c'est une régression **assumée** et documentée : les noms de
fichiers produits pour un même wiki peuvent différer d'une version à l'autre.
Le cache peut servir un aperçu obsolète si `mtime` n'a pas changé (résolution à
la seconde sur certains FS) : ajouter la taille du fichier à la clé.

## Actions humaines requises

Aucune.

## Dépendances

T01 ; T04 (nommage) doit être fait dans le même bloc de modifications de
`pack_files.py` ; T11 utilise le même `build_packing`.

## Non-objectifs

- Pas de parallélisme multi-processus pour le calcul lui-même (le coût de
  sérialisation dépasse le gain à 4 000 catégories : mesurer avant).
- Pas de base de données ni de cache disque persistant.
- Pas d'optimisation de `export_categories.py` (mesuré à 9,3 s pour 2 000 pages /
  53 Mo : dominé par WeasyPrint/I-O, hors périmètre P1-P2).

## Critères d'acceptation

1. 3 998 catégories / 20 000 pages : `pack_files` < 300 ms, `preview_packing` HTTP
   < 600 ms.
2. Pendant 10 aperçus consécutifs, `GET /api/jobs` répond en < 50 ms (mesuré par
   un client concurrent).
3. 4 aperçus simultanés → au total < 2 s (contre 25-29 s).
4. Onglet en arrière-plan 10 minutes : `logBuffer` plafonné, DOM ≤ 5 000 nœuds.
5. `preview_packing` == fichiers produits (T11) toujours vrai.

## Vérification et repli

Refaire la campagne de mesures de l'audit (mêmes fixtures : 800/3 000 et
4 000/20 000) et comparer médianes avant/après. Repli : `git revert` de la
réécriture de `pack` (le reste — cache, pool, logs — est indépendant).
