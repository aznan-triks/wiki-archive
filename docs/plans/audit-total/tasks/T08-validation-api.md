# T08 — Validation et contrat d'API (une seule frontière de confiance)

- **Priorité** : P1 · **Axe** : D/H · **Constats couverts** : D08, C16, D28,
  D29, D30, D27, D31
- **Justification** : la seule validation existante est côté navigateur
  (`min`/`max` HTML). Tout le reste — script, `curl`, `settings.json` édité à la
  main, onglet d'un autre site (H02) — traverse sans contrôle et produit des
  états invalidants qui survivent au redémarrage.

## Preuve et conséquence

- **D08 (P1)** : `PUT /api/settings {"max_files":"abc"}` → `200`, valeur
  **persistée** dans `settings.json` ; `POST /preview_packing {"max_files":"abc"}`
  → **500** (trace) ; `MAX_FILES=abc run.py` → `ValueError: invalid literal for
  int() with base 10: 'abc'` avec traceback complet dans le log du job. Une seule
  faute de frappe empoisonne durablement l'application (elle se propage à tous les
  nouveaux jobs et survit au redémarrage).
- **C16** : les bornes n'existent que dans le HTML (`server.py:1259, 1282,
  1292-1294, 1365-1369`) ; `save_settings` (`:100-107`) et `create_job`
  (`:587-598`) n'ont aucun contrôle.
- **D28** : `POST /api/jobs {"wiki_url":"not a url"}` → job créé, `wiki_slug:
  "not_a_url"`, échec seulement à l'étape 1.
- **D29** : corps `not json` sur `POST /api/jobs` → **500** (9 routes concernées :
  `server.py:589, 606, 613, 646, 705, 717, 740, 748, 752`).
- **D30** : `preview_packing {"selection":["Nope","Weapons"]}` → `file_count: 1`,
  aucune mention de « Nope ».
- **D27** : `PUT /api/settings` et `PATCH /api/jobs` recopient les clés connues
  et **suppriment silencieusement** les inconnues (`{"max_file":50}` → 200, sans
  effet ni avertissement).
- **D31** : `GET /api/jobs/{id}` → 404 : aucune lecture unitaire.

## État actuel → état cible

- Une fonction pure `validate_settings(dict) -> (dict, list[str])` et
  `validate_job(dict) -> (dict, list[str])` : types, bornes, énumérations,
  normalisation (int, bool) ; les erreurs sont renvoyées **toutes** avec le nom
  du champ ; les clés inconnues sont **refusées** (`400`, message) plutôt
  qu'ignorées.
- Toute route qui lit un corps passe par `await json_body(req)` → `400` sur JSON
  invalide.
- `wiki_url` validée à la création (`urlparse`, schéma `http(s)`, hôte non vide)
  → `400` avec un exemple.
- `preview_packing` renvoie `unknown: [noms absents]` et `misc_pages: n`
  (cf. T11).
- `GET /api/jobs/{id}` renvoie `job.meta()`.

## Cause racine et sites concernés

Aucune couche de validation entre le transport (FastAPI `Request`) et les
structures internes : chaque handler fait `await req.json()` puis
`body.get(...)` avec des conversions implicites (`int(body.get("max_files") or
0)`). Les bornes vivent dans le HTML (`min`, `max`, `step`) et sont recopiées à
la main dans trois endroits (`server.py:1259, 1282, 1292-1294, 1365-1369`), sans
source unique.

## Référence à réutiliser

- `DEFAULTS` (`server.py:58-75`) est déjà la description canonique des champs et
  de leurs valeurs par défaut : c'est le point naturel pour les bornes
  (`DEFAULTS` + `LIMITS` à côté).
- `NOTEBOOKLM_PLANS` (`server.py:76`) donne déjà l'énumération des plans.
- `tests/test_server_config.py` teste `DEFAULTS`/`NOTEBOOKLM_PLANS` : à étendre.

## Plan d'action

1. `server.py` : à côté de `DEFAULTS`, une table `LIMITS = {"max_files": (1, 600),
   "delay": (0.5, 60), "workers": (1, 16), "notebooklm_plan": set(NOTEBOOKLM_PLANS),
   "export_formats": {...}, "cat_workers": (1, 32), "max_pages_per_file": (10,
   5000)}` + `validate(dict, spec) -> (cleaned, errors)`.
2. Brancher `validate` dans `create_job`, `patch_job`, `put_settings`,
   `preview_packing`, `generate` ; réponse `400 {"errors": {"max_files":
   "must be an integer between 1 and 600"}}`.
3. `json_body(req)` : helper unique, `try/except (JSONDecodeError, UnicodeError)`
   → `400 {"error":"invalid JSON body"}` ; remplacer les 9 occurrences.
4. `create_job` : `urlparse` + `scheme in ("http","https")` + `netloc` non vide
   → sinon 400 avec exemple. Ne pas résoudre le DNS (H03 est un autre sujet).
5. `GET /api/jobs/{job_id}` : 3 lignes, 404 si inconnu.
6. UI : afficher les erreurs champ par champ (`fieldErrors` sur les inputs) au
   lieu d'un toast générique ; supprimer les bornes HTML dupliquées (les générer
   depuis `LIMITS` exposé par `GET /api/settings` → `limits`).
7. `preview_packing` : ajouter `unknown` + `misc_pages` (voir T11).
8. Étendre `tests/test_server_config.py` : `validate` sur les cas de l'audit
   (`"abc"`, `-1`, `0`, `1e9`, `true`, `null`, clé inconnue).

## Points d'impact

`server.py` (handlers `create_job`, `patch_job`, `put_settings`,
`preview_packing`, `generate`, nouvelle route `GET /api/jobs/{id}`), JS
(`fieldErrors`, `buildForm`), `scripts/run.py` (défense en profondeur :
`int(max_files)` entouré d'un message clair plutôt qu'un traceback),
`tests/test_server_config.py`.

## Régression

Aucune pour les valeurs valides : `validate` renvoie la valeur normalisée
identique. Deux risques :
(a) un `settings.json` existant contenant déjà `"abc"` bloquerait le démarrage →
au chargement, les valeurs invalides sont **corrigées vers `DEFAULTS`** avec un
avertissement affiché, jamais un refus de démarrer ;
(b) le refus des clés inconnues casse un client qui envoyait des champs
supplémentaires — aucun client de ce type n'est documenté ni présent (vérifié :
le JS envoie exactement `DEFAULTS` + sélection).

## Actions humaines requises

Aucune.

## Dépendances

T01 (tests). T11 (aperçu) partage le point 7. H02/T14 dépend de la validation
(une requête intersite doit être refusée **avant** d'atteindre ces handlers).

## Non-objectifs

- Pas de `pydantic` : `DEFAULTS` + `LIMITS` tiennent en 30 lignes et évitent une
  dépendance (KISS).
- Pas de validation d'accessibilité réseau de l'URL (pas de DNS, pas de fetch).
- Pas de versionnement de l'API.

## Critères d'acceptation

1. `PUT /api/settings {"max_files":"abc"}` → 400, `settings.json` inchangé.
2. `POST /api/jobs {"wiki_url":"not a url"}` → 400 avec exemple.
3. Corps `not json` → 400 sur les 9 routes (test paramétré).
4. `{"max_file": 50}` → 400 « unknown field ».
5. `preview_packing` avec `["Nope","Weapons"]` → `unknown: ["Nope"]`.
6. `GET /api/jobs/<id>` → 200 ; `<inconnu>` → 404.
7. Un `settings.json` contenant `"max_files":"abc"` démarre avec 50 et un
   avertissement.
8. Test de T01 `test_invalid_params_rejected_with_400` vert.

## Vérification et repli

Rejouer les 9 sondes de l'audit (`curl` sur chaque route, corps invalide, type
invalide, clé inconnue). Repli : `git revert` (points 1-8 indépendants).
