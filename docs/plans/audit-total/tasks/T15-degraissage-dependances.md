# T15 — Dégraissage : images inutiles, dépendances, code mort

- **Priorité** : P2 (D46) + P3 (F11, F12, G06, G08, G11, G12) + P4 (G01-G05, G07)
- **Axe** : G/F · **Constats couverts** : D46, F11, F12, B08 (partagé), G01, G02,
  G03, G04, G05, G06, G07, G08, G11, G12, G14
- **Justification** : le dépôt porte du poids inutile à trois niveaux :
  téléchargement (images du wiki jamais utilisées), image Docker (paquets
  d'exécution inutiles, contexte non filtré) et code (CSS/JS/champs morts). Tout
  est mesuré ou vérifié par `grep`, aucun n'est une supposition.

## Preuve et conséquence

- **D46 (P2)** : `images: True` par défaut (`server.py:65`) →
  `--images` passé à `wikiteam3` (`run.py:237-238`), et **aucune** occurrence de
  `img`/`image` dans `extract.py`, `convert.py`, `clean_html.py`,
  `export_categories.py` (hors CSS). Les images sont téléchargées (souvent la
  majorité des octets d'un dump) puis jamais utilisées ; pire, `convert.py`
  laisse WeasyPrint les re-télécharger page par page (échecs lents, `base_url`
  absent).
- **F12 (P3)** : aucun `.dockerignore` ; le contexte de build inclut `data/`
  (dumps archivés) et `.venv/` — un `docker build` peut envoyer des gigaoctets
  au démon.
- **F11 (P3)** : le Dockerfile installe des paquets dont aucun script ne dépend à
  l'exécution ; les binaires externes (`wikiteam3dumpgenerator`, `pandoc`) sont
  référencés **uniquement** dans le Dockerfile (vérifié par `grep` sur le
  dépôt) : impossible de lancer le pipeline hors conteneur, ce qui rend les
  tests d'intégration dépendants de Docker.
- **G06 (P3)** : `MAX_PAGES_PER_FILE` n'est positionné nulle part (seule
  occurrence : `pack_files.py`, lecture) ⇒ la branche de découpage par pages est
  morte ; le seul découpage effectif est celui de `merge_pdf.py` (`max_pages`
  distinct).
- **G08 (P3)** : `pack_files.py` lit `MAX_FILES` dans l'environnement **avant**
  l'argument positionnel : l'argument est ignoré si la variable existe (piège
  silencieux).
- **G11 (P3)** : `requirements.txt` non épinglé (aucune version) ⇒ aucun build
  reproductible ; **G12** : la même liste existe en deux exemplaires (Dockerfile
  et `requirements.txt`), déjà divergents.
- **G14 (P3)** : un transcript de conversation IA (298 lignes, lien de partage
  privé) est versionné dans le dépôt.
- **G01-G05/G07 (P4)** : CSS mort (`t-hidden`, `dot-*`, `st-*`, `toast`,
  `job-item`, `l-ok/l-sep/l-warn`), `loadPrefs`/`savePrefs` (fonctionnalité
  abandonnée), champs `has_output` et `log_count` calculés et jamais lus,
  `STEPS[].id` inutilisé, un import inutilisé.

## État actuel → état cible

- Les images ne sont téléchargées que si `images=true` **et** que le pipeline les
  utilise ; par défaut, pas de téléchargement. Si l'option est conservée, les
  `src` sont réécrits vers les fichiers locaux et `base_url` est passé à
  WeasyPrint.
- `.dockerignore` présent (au minimum `data/`, `.venv/`, `__pycache__/`,
  `.git/`, `*.md` de travail).
- Une seule source de dépendances (`requirements.txt` épinglé, installé par le
  Dockerfile).
- Aucune variable d'environnement morte, aucun code mort non justifié.
- Le transcript de conversation IA n'est plus dans l'arbre public (déplacé hors
  dépôt ou retiré de l'index ; l'historique n'est pas réécrit).

## Cause racine et sites concernés

Fonctionnalités amorcées puis abandonnées (images, préférences, `has_output`),
copier-coller de configuration (Dockerfile/requirements), et absence de garde
`grep`-testable sur le code mort. Sites : `server.py:65` (défaut images),
`run.py:237-238`, `pack_files.py` (`MAX_PAGES_PER_FILE`, `MAX_FILES`),
`requirements.txt`, `Dockerfile`, `docker-compose.yml`, CSS/JS de `server.py`,
racine du dépôt (transcript).

## Référence à réutiliser

- `clean_html.py` réécrit déjà des attributs (c'est là que les `src` d'images se
  réécriraient) : ne pas créer un nouveau module.
- `convert.py` appelle `HTML(filename=src)` : ajouter `base_url=dump_dir` est une
  modification d'une ligne.
- Les tests `tests/test_clean_html.py` (s'il existe) et `test_merge_pdf.py`
  couvrent déjà les transformations de HTML/PDF.

## Plan d'action

1. **D46 — décider** : (a) supprimer `--images` et passer le défaut à `false`
   (rapide, gain immédiat) ; ou (b) garder l'option et l'honorer (réécriture des
   `src` + `base_url`). Recommandation : (a) maintenant, (b) si un utilisateur
   demande les images. Mettre à jour le libellé de la case et le README
   (« images: downloaded for future use » est trompeur).
2. `.dockerignore` (8 lignes).
3. `requirements.txt` : épingler (`==`) les 6 dépendances après un
   `pip freeze` filtré **au moment de l'exécution** (action humaine : valider les
   versions, car cela fige les correctifs de sécurité) ; `Dockerfile` :
   `COPY requirements.txt && RUN pip install -r requirements.txt` ; supprimer la
   liste dupliquée.
4. `F11` : lister les paquets réellement requis par `weasyprint`, `pikepdf`,
   `pandoc` (mesurer avec `docker history`/`dpkg -L` si l'image est construite —
   impossible ici : marqué **Déduit**, vérifier à la construction) ; retirer les
   outils de compilation du stage final (multi-stage).
5. `G06` : soit exposer `MAX_PAGES_PER_FILE` dans les réglages (il manque un
   champ, cf. C01 qui montre le même trou pour `max_words`), soit supprimer la
   branche de `pack_files.py`. Décision : supprimer (YAGNI) — le découpage par
   pages existe déjà dans `merge_pdf.py`.
6. `G08` : inverser la priorité (argument d'abord, environnement ensuite) et
   journaliser la valeur retenue.
7. `G01-G05, G07` : supprimer les sélecteurs CSS morts après vérification
   (`grep` sur le JS + HTML), supprimer `loadPrefs`/`savePrefs` **si** le thème
   unique est retenu (T10), retirer `has_output`/`log_count`/`STEPS[].id` de
   `meta()`/`STEPS` et des consommateurs JS, retirer l'import inutilisé.
8. `G14` : `git mv` le transcript hors de l'arbre suivi (ou `git rm --cached`),
   ajouter un motif d'ignore ; **ne pas réécrire l'historique** (proposé, non
   exécuté).

## Points d'impact

`server.py` (défaut images, CSS/JS morts, `meta()`), `scripts/run.py`,
`scripts/clean_html.py`/`convert.py` (si option b), `scripts/pack_files.py`,
`requirements.txt`, `Dockerfile`, `.dockerignore` (nouveau), dépôt (transcript).
Tests : `tests/test_pack_files` (si `MAX_FILES`), `test_server_config.py`
(champs de `meta()`).

## Régression

- **Suppression des images par défaut** : un utilisateur qui comptait sur les
  images téléchargées les perd → **régression assumée**, justifiée par le fait
  qu'elles ne sont **jamais** utilisées par le pipeline (preuve : zéro référence
  dans le code d'export). L'option reste disponible.
- **Suppression de `has_output`/`log_count`/`STEPS[].id`** : aucune (jamais lus —
  vérifié par `grep` sur le JS).
- **Épinglage des dépendances** : plus de mises à jour automatiques de correctifs
  → assumé (reproductibilité), avec une tâche de revue trimestrielle
  (`pip-audit` est déjà passé : aucune vulnérabilité connue au moment de
  l'audit).
- **CSS mort supprimé** : risque de casser un effet visuel non détecté (classes
  construites dynamiquement). Atténuation : `grep` des préfixes (`st-${…}`,
  `dot-${…}` sont **construits** dynamiquement — vérifié : `st-` et `dot-` sont
  interpolés avec un statut, donc **ne pas** les supprimer sans vérifier chaque
  statut ; G01 doit être réduit aux sélecteurs réellement orphelins).

## Actions humaines requises

1. Valider les versions épinglées (impact sécurité).
2. Décider du sort des images (supprimer le téléchargement par défaut).
3. Valider le retrait du transcript du dépôt (et, si souhaité, la purge
   d'historique — **non exécutée ici** ; la conversation contient un lien de
   partage privé, donc aucun secret applicatif, mais des informations de projet).

## Dépendances

T10 (décision thème) pour G02 ; T16 (documentation) pour les libellés.

## Non-objectifs

- Pas de remplacement de `weasyprint`/`pikepdf`/`pandoc` (choix structurant, hors
  périmètre).
- Pas de réécriture d'historique.
- Pas d'optimisation de l'image Docker au-delà du multi-stage et du
  `.dockerignore` (pas de build Alpine, non mesurable ici).

## Critères d'acceptation

1. Un dump par défaut ne télécharge plus d'images ; le log le dit.
2. `docker build` avec `data/` rempli de 2 Go → contexte < 5 Mo.
3. `pip install -r requirements.txt` deux fois de suite → mêmes versions.
4. `grep` : zéro variable `MAX_PAGES_PER_FILE` non alimentée ; zéro fonction JS
   non appelée ; zéro champ de `meta()` non lu.
5. Le transcript n'est plus dans `git ls-files`.

## Vérification et repli

`du -sh` du contexte de build (via `docker build --no-cache` — impossible ici :
**Déduit**), `git ls-files | grep -c`, `grep` des champs `meta()`. Repli :
`git revert` point par point ; le transcript peut être restauré depuis
l'historique.
