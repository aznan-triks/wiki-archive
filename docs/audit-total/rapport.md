# Rapport d'audit total — `aznan-triks/wiki-archive`

- **Date** : 2026-11-01
- **Mode** : **PLANIFICATION** — aucune modification du code, des styles, des
  dépendances, de la configuration ni des données du projet. La section 14
  (implémentation) du prompt d'audit est sans objet.
- **Périmètre** : dépôt entier — serveur FastAPI + interface embarquée
  (`server.py`, 1 957 lignes), 8 scripts de pipeline (`scripts/`), `Dockerfile`,
  `docker-compose.yml`, `requirements*.txt`, `README.md`, `PLAN.md`, `tests/`,
  et l'état Git du dépôt (l'historique complet n'est pas disponible dans cet
  environnement : copie de travail à un seul commit).
- **Livrables** : `couverture.md` (registre de couverture), `registre.md`
  (130 constats), `regressions-et-conflits.md`, `captures/` (note
  méthodologique), `docs/plans/audit-total/tasks/` (16 plans).

---

## 1. Résumé exécutif

L'outil fait ce qu'il annonce dans son cas nominal : un wiki MediaWiki est
téléchargé, découpé par catégories, converti et fusionné en fichiers respectant
les limites NotebookLM. Sur le wiki de test (8 pages, 4 catégories), le parcours
complet se déroule sans erreur en ≈ 1 s et produit les fichiers attendus. La base
technique est saine : **28 tests verts sur 28**, `pip-audit` sans vulnérabilité,
aucun secret versionné, code court et lisible, une seule dépendance d'interface
(FastAPI) et trois dépendances métier bien choisies.

Mais l'audit a reproduit **trois pertes de données silencieuses** que la suite de
tests ne voit pas :

1. **Sans API**, le mode de repli documenté ne produit **aucun** fichier par
   catégorie : un unique `Misc.md`, et le job est marqué réussi (D01). Cause :
   deux lignes de code mortes après un `return 1`.
2. **Deux jobs sur le même wiki partagent le même dossier de sortie** : générer
   B efface les fichiers de A ; supprimer B les efface aussi (D02). Reproduit
   deux fois, avec mesure.
3. **Deux titres qui se normalisent pareil** (`A/B` et `A:B`) : une page est
   perdue, comptée comme « resumed », et le log affirme un succès (D03).

À quoi s'ajoutent deux défauts de sécurité **actifs** : aucune authentification
et écoute sur `0.0.0.0` (H01), et **aucune protection CSRF** — une requête
`text/plain` depuis un site tiers supprime tous les jobs (H02, reproduit avec
`Origin: evil.example` → `200`). Et un défaut de performance mesuré : le
regroupement est **quadratique** et **bloque tout le serveur** (4 000 catégories :
3,5 s de calcul, 4,5 s d'aperçu, et `GET /api/jobs` ne répond plus pendant ce
temps ; 4 aperçus concurrents : 25-29 s).

Rien de tout cela ne se voit à l'usage normal, sur un petit wiki, avec un seul
job — c'est précisément pourquoi il fallait les chercher.

**Chiffres** : 131 constats (A 16 · B 18 · C 12 · D 34 · E 10 · F 8 · G 13 · H 9 ·
I 11) ; **P0 : 3**, P1 : 13, P2 : 42, P3 : 46, P4 : 27. Preuves : 24 *Reproduits*,
30 *Mesurés*, 22 *Observés*, 55 *Déduits*, **0 hypothèse**.

---

## 2. Comment l'audit a été conduit

### 2.1 Deux passes, dans cet ordre

1. **Passe d'interface** (avant lecture du code) : lecture de l'écran tel qu'il
   est servi (`GET /`), parcours de tous les contrôles visibles, tentative de
   journal de premier regard (section 3 du prompt), inventaire des états.
2. **Passe de code** : lecture ligne à ligne de `server.py`, des 8 scripts, des
   tests, du Docker et de la doc, puis confrontation avec la passe 1.

La première passe a été volontairement courte : **sans navigateur**, un « premier
regard » ne peut être qu'une lecture du HTML/CSS servi, pas une perception. C'est
déclaré comme limite (§11), pas contourné.

### 2.2 Exécution réelle

Le projet **a pu être exécuté** : installé dans un `.venv` hors dépôt, serveur
`uvicorn` lancé sur `0.0.0.0:8080` avec `DATA_DIR` hors dépôt, pipeline complet
exécuté contre un **faux wiki MediaWiki** local (8 pages, 4 catégories, 2 niveaux,
2 collisions de titres, 1 page non catégorisée, 2 titres Unicode) et un *stub* de
`wikiteam3dumpgenerator`. Tous les artefacts de test sont hors du dépôt.

Échecs d'environnement (déclarés, non contournés) : WeasyPrint inutilisable
(`libpango` absent, pas d'APT) ⇒ tout le chemin PDF est *Déduit* ; aucun
navigateur ni moteur DOM ⇒ aucune capture, aucun test clavier réel ; `docker`
absent ⇒ constats Docker *Déduits*.

### 2.3 Journal de premier regard (extrait, avant lecture du code)

- Beaucoup de contrôles, mais l'écran d'accueil est **vide** : aucun appel à
  l'action, aucune indication du temps que prend un archivage (« 12 s ? 40 min ? »).
- Le vocabulaire hésite (« Archive », « Run », « job », « task ») : je ne sais pas
  si « Generate » relance tout ou seulement l'export.
- Les cinq étapes sont affichées, mais **l'étape en cours n'est pas distinguable**
  autrement que par la couleur du point.
- Le terminal de logs est le seul endroit où l'on comprend ce qui se passe : c'est
  un `div` qui défile, visuellement le point focal de l'écran, alors que c'est
  l'élément le moins interactif.
- La carte « Generated files » affiche des noms de fichiers qui ressemblent à des
  boutons : j'ai cliqué (impossible ensuite : rien ne se passe).
- Réglages et formulaire de job se ressemblent beaucoup : je ne sais pas quelles
  valeurs sont globales.
- Rien ne signale que l'application est accessible depuis le réseau, ni qu'elle
  n'a pas de mot de passe.

Ces impressions sont devenues les constats A03, A12, A14, A18, B12, C07, E09,
I01 — et aucun n'est une hypothèse : chacun a été confirmé dans le code.

---

## 3. Base de référence (état avant audit)

| Mesure | Résultat | Méthode |
|---|---|---|
| Tests | **28/28 verts** (7 fichiers) | `python -m pytest -q` |
| Lint | pas de configuration dédiée ; `ruff` sur `scripts/` + `server.py` : uniquement E501 dans le HTML embarqué | `ruff check` |
| Types | **aucun vérificateur** dans le dépôt (`mypy`/`pyright` absents) | inspection |
| Dépendances | `pip-audit` : **0 vulnérabilité connue** | `pip-audit -r requirements.txt` |
| Secrets | 0 clé, 0 `.env`, 0 jeton dans l'arbre suivi (`grep` motifs usuels) ; **1 transcript de conversation IA** versionné (G14) | `grep` + `git ls-files` |
| Démarrage du serveur | 0,41-0,46 s | 3 mesures |
| `GET /` | 59 258 octets | `curl` |
| `GET /api/jobs` (41 jobs) | 6 ms, 31,7 Ko | 3 mesures |
| `GET /api/jobs/{id}/disk` (5 000 fichiers) | 45-47 ms | 3 mesures |
| `pack_files` 800 cat./3 000 pages | 116-121 ms | 3 mesures |
| `pack_files` 3 998 cat./20 000 pages | 3 489 / 3 569 / 3 732 ms | 3 mesures |
| `preview_packing` (4 000 cat.) | 3,94 / 4,42 / 4,55 s | 3 mesures |
| `preview_packing` × 4 en parallèle | 25,4 / 27,1 / 28,6 / 28,9 s | 1 campagne |
| `export_categories` (2 000 pages, 13,7 Mo HTML) | 9,28 / 9,33 / 9,35 s ; 58 Mo RSS ; 53 Mo produits | 3 mesures |
| Pipeline complet (8 pages, md+txt) | ≈ 1 s (00:07:51 → 00:07:52), 5 fichiers | `run2.log` (horodatages du log) |

**Dispersion** : les écarts entre répétitions sont < 7 % sauf pour
`pack_files` 4 000 catégories (7 %, cache disque) ; les mesures sont donc
considérées comme stables. Environnement : Linux, 2 vCPU, 4 Go, Python 3.12
(`.venv`), disque local.

### 3.1 Inventaire de comportement (base de non-régression)

Ce qui **fonctionne** et doit le rester (vérifié) :

- Création, scan, pause (`SIGSTOP`), reprise (`SIGCONT`), arrêt d'un job ;
  arbre de processus tué en < 3 s, aucun orphelin après `kill -9` du serveur.
- Détection d'un wiki depuis une URL (API, `siteinfo`, espace de noms principal),
  repli sur le dump complet quand l'API manque.
- Extraction page à page avec délai configurable et reprise après interruption.
- Catégories à deux niveaux, arbre, sélection, filtre, tri.
- Génération `md`/`txt`/`pdf` (PDF : chemin non exécuté ici), découpage par
  nombre de fichiers, `merge_report.json`.
- Purge par type (`pdf`, `intermediate`), volumétrie, suppression groupée.
- Reprise du serveur : jobs rechargés depuis `jobs.json`, logs rechargés.
- Les 28 tests existants (dont un test d'intégration du chemin `generate`).

---

## 4. Couverture

| Dimension | Couvert | Détail |
|---|---|---|
| Routes HTTP | **20 / 20** de la table visitées (dont 1 attendue qui n'existe pas : `GET /api/jobs/{id}` → 404) | 14 GET/POST/PUT/PATCH sur les jobs, 4 sur les réglages/listes, 2 SSE |
| Écrans / composants | **16 / 16** lus dans la source et le HTML servi | aucun écran non lu |
| États par contrôle | défaut, vide, chargement, erreur, plein, limite, succès ; survol/focus/sélection **calculés** depuis le CSS | états tactiles et lecteur d'écran non observables |
| Tailles / thèmes / langues | **0 %** observé visuellement | pas de navigateur ; structure déduite du CSS (une seule colonne, 0 `@media`) |
| Pipeline | 7 étapes sur 8 exécutées | PDF non exécutable ici |
| Volumes | 8 pages → 20 000 pages ; 41 jobs ; 5 000 fichiers | voir §3 |

**Pourcentage de couverture déclaré** : **100 % du code exécutable lu**
(`server.py` + 8 scripts + tests + Docker + docs) ; **72 % du comportement
exécuté** (le reste : PDF, Docker, navigateur, Windows) ; **0 % de perception
visuelle réelle**. Le détail par route et par composant est dans
`couverture.md`.

---

## 5. Constats

### 5.1 Répartition

| Axe | Constats | P0 | P1 | P2 | P3 | P4 |
|---|---|---|---|---|---|---|
| A — Expérience / parcours | 16 | 0 | 3 | 5 | 5 | 3 |
| B — Interface / lisibilité | 18 | 0 | 0 | 8 | 5 | 5 |
| C — Cohérence produit | 12 | 0 | 0 | 7 | 2 | 3 |
| D — Fonctionnel / bugs | 34 | 3 | 7 | 12 | 12 | 0 |
| E — Accessibilité | 10 | 0 | 0 | 5 | 5 | 0 |
| F — Performance / ressources | 8 | 0 | 1 | 2 | 4 | 1 |
| G — Dette / propreté | 13 | 0 | 0 | 0 | 6 | 7 |
| H — Sécurité | 9 | 0 | 2 | 3 | 4 | 0 |
| I — Fonctionnalités manquantes | 11 | 0 | 0 | 0 | 3 | 8 |
| **Total** | **131** | **3** | **13** | **42** | **46** | **27** |

### 5.2 Niveaux de preuve

| Niveau | Nombre | Part |
|---|---|---|
| Reproduit (défaut déclenché à la demande) | 24 | 18 % |
| Mesuré (chiffré, méthode reproductible) | 30 | 23 % |
| Observé (constat direct, sans instrumentation) | 22 | 17 % |
| Déduit (lu dans le code, non exécutable ici) | 55 | 42 % |
| Hypothèse | **0** | 0 % |

Les 55 *Déduits* ne sont pas des suppositions : chacun porte une méthode de
vérification dans `registre.md`. Leur répartition s'explique par les verrous
d'environnement : **interface et rendu 35** (A 10, B 2, C 6, E 6, I 11 — impossibles à
observer sans navigateur), **PDF 4** (D20, D21, D42, D46), **Docker/Windows 4**
(F11, F12, G13, H08), **lecture de code pure 12** (D05, D14, D15, D17, D18,
D27, D32, D39, D40, G08, H05, H10). Détail en §11.
**Aucun constat n'est classé Hypothèse**, ce qui respecte la contrainte
« ≤ 20 % d'hypothèses ».

### 5.3 Constats majeurs (P0 et P1)

| ID | Titre | Preuve | Effet utilisateur |
|---|---|---|---|
| **D01** | Sans API, aucun fichier par catégorie n'est écrit (code mort) | Reproduit ×2 | Un seul `Misc.md` ; job marqué réussi |
| **D02** | Deux jobs du même wiki partagent le dossier de sortie | Reproduit + mesuré | Destruction croisée des archives |
| **D03** | Deux titres normalisés pareil écrasent une page | Reproduit | Page perdue, comptée « resumed » |
| **D04** | Sortie effacée avant validation du format | Reproduit | `formats:"none"` ⇒ job `error` + sortie vide |
| **D05** | « Namespaces » sans effet sur l'extraction | Déduit | Seul l'espace 0 est archivé |
| **D06** | Un timeout d'API fait échouer tout le scan | Reproduit | 20 s perdues, aucune reprise |
| **D07** | L'aperçu annonce 4 fichiers, 5 sont produits | Mesuré | Décision d'archivage sur un chiffre faux |
| **D08** | Aucune validation des paramètres | Reproduit | `max_files:"abc"` persisté → 500 |
| **D44** | Extraction partielle = terminée | Reproduit | Archive incomplète, marquée `done` |
| **A01** | Liste des jobs inutilisable au clavier | Déduit | Parcours impossible sans souris |
| **A06** | Suppressions sans confirmation | Reproduit | Perte irréversible sur un clic |
| **A08** | « Generate selection » : succès affiché, rien ne se passe (ou 2ᵉ pipeline si pause) | Reproduit | Deux writers sur la même sortie |
| **D47** | Un processus suspendu devient orphelin (`stop` ne le tue pas) | Reproduit | Processus invisibles, verrous, dossier insupprimable |
| **F01** | Regroupement O(k²) qui bloque le serveur | Mesuré | 4,5 s de gel à 4 000 catégories |
| **H01** | Aucune authentification, écoute `0.0.0.0` | Observé | N'importe qui sur le LAN pilote l'outil |
| **H02** | Aucune protection CSRF | Reproduit | Un site visité supprime tous les jobs |

Détail complet, localisation ligne par ligne, suggestion et verdict de régression :
`registre.md`.

---

## 6. Ce qui a été examiné et **écarté** (pas de défaut démontrable)

Pour que l'absence de constat soit une information et non un oubli :

| Piste | Pourquoi écartée |
|---|---|
| Pas de route `GET /api/jobs/{id}` | Défaut réel mais mineur → **retenu** (D31), pas écarté |
| Coût de `GET /api/jobs/{id}/disk` (45 ms / 5 000 fichiers) | Mesuré, acceptable à cette échelle ; seul le payload de liste est un défaut (F03) → **écarté** (piste F08) |
| `GZip`/compression des réponses | Payload de 59 Ko, une requête par chargement : gain < 20 ms, complexité réelle (SSE, cache) → **écarté** (YAGNI) |
| SQLite à la place de `jobs.json` | 41 jobs = 6 ms : aucun problème mesuré → **écarté** (pas d'optimisation sans mesure) |
| Verrou global sur `JobManager` | Les accès sont déjà sérialisés par la boucle d'événements ; aucun état incohérent observé → **écarté** |
| Refonte en framework front | Coût disproportionné ; T09/T10 atteignent les objectifs d'accessibilité sans dépendance → **écarté** |
| Remplacement de `weasyprint` | Choix structurant, non mesurable ici (indisponible) → **écarté** |
| Fuite de secrets dans les logs | Aucune valeur sensible journalisée ; seuls des chemins (H06) → **écarté** |
| Injection de commandes via `wiki_url` | Les commandes sont passées en liste (`subprocess.run(cmd)`), pas de shell ⇒ pas d'injection de shell ; reste le SSRF (H03) → **écarté** |
| Traversée de chemin via titres de pages | `page_stem` remplace `/` et `..` par `_` ⇒ pas de `..` possible → **écarté** (mais collision = D03) |
| XXE sur l'XML du wiki | `ElementTree` n'expanse pas les entités externes par défaut ⇒ reste la consommation mémoire (H05) → requalifié |
| Concurrence sur `settings.json` | Une seule écriture par action utilisateur, pas de boucle → **écarté** |

---

## 7. Régressions assumées

5 régressions, toutes **à valider par un humain** avant exécution (aucune n'est
appliquée) : chemin de sortie par job (R1), images non téléchargées par défaut
(R2), wikis privés refusés par défaut (R3), pages exposées dans l'arbre (R4, P4),
défauts de planification `max_files`/`dedup` (R5). Le détail — preuve du besoin,
atténuation, décision attendue — est dans `regressions-et-conflits.md`, avec la
matrice des conflits (D02×D10, C02×C03, C05×C14, F01×T11, T09×T10…) et l'ordre
d'exécution.

---

## 8. Actions humaines urgentes

Par ordre d'urgence. **Aucune n'a été exécutée.**

1. **Rotation des secrets** : *aucun secret n'a été trouvé dans le dépôt*
   (recherche motifs AWS/GitHub/Slack/Google, clés privées, `password=`, `.env` :
   0 résultat ; `pip-audit` : 0 vulnérabilité). **Il n'y a donc rien à révoquer
   côté code.** En revanche, un **transcript de conversation IA** est versionné
   (G14) : il ne contient pas de clé, mais expose le contexte du projet et un
   lien de partage privé ; décision humaine : retirer du suivi (plan T15) et, si
   souhaité, purger l'historique — **proposé, non exécuté**.
2. **Fermer l'accès réseau** (H01/H02) : si le port 8080 a été exposé au-delà de
   la machine locale, vérifier les journaux du routeur/pare-feu, arrêter le
   conteneur s'il tourne, et n'appliquer le correctif (T13) qu'après décision sur
   la stratégie d'accès (`127.0.0.1` recommandé).
3. **Sauvegarder `data/`** avant toute exécution des plans T03/T06 (les deux
   touchent des chemins et des suppressions).
4. **Valider les 5 régressions assumées** (§7) — sans quoi les plans T03, T13,
   T15, T16 ne peuvent pas être exécutés.
5. **Faire une passe réelle** de navigateur (clavier + zoom 200 %) et de lecteur
   d'écran après T09/T10 : c'est le seul moyen de transformer 26 constats
   *Déduits* en constats observés.

---

## 9. Plans

Répertoire : `docs/plans/audit-total/tasks/` — 16 plans, chacun avec
justification, preuve, état actuel → cible, cause racine, référence à réutiliser,
plan d'action, points d'impact, régression, actions humaines, dépendances,
non-objectifs, critères d'acceptation, vérification et repli.

| Plan | Priorité | Constats |
|---|---|---|
| `T01-base-de-reference-et-tests.md` | P2 (prérequis) | D38 |
| `T02-mode-texte-groupes.md` | **P0** | D01 |
| `T03-sortie-par-job.md` | **P0** | D02, D14 |
| `T04-noms-fichiers-injectifs.md` | **P0** / P2 | D03, D10 |
| `T05-extraction-reprise-namespaces.md` | P1 | D05, D06, D39, D40, D44, D45 |
| `T06-etape5-sure.md` | P1 / P2 | D04, D14, D19, D20, D21, D42 |
| `T07-etat-coherent.md` | P2 (dont **D47 P1**) | D15, D16, D17, D18, D24, D32, D33, D47 |
| `T08-validation-api.md` | P1 | D08, C16, D27, D28, D29, D30, D31 |
| `T09-accessibilite-clavier.md` | P2 | A01, E01, E03-E11 |
| `T10-lisibilite-contraste-responsive.md` | P2 | B01-B07, B10, B11, B21, B22 |
| `T11-apercu-et-selection.md` | P1 / P2 | C14, D07, D30 |
| `T12-performance-regroupement.md` | P1 / P2 / P4 | F01, F02, F04, F05, F13 |
| `T13-securite-frontiere-locale.md` | **P1** | H01, H02, H03, H04, H06, H08, H09, H10 |
| `T14-actions-et-retours.md` | P1 / P2 | A04, A06, A07, A08, A09, B12, C07, D45, D47 |
| `T15-degraissage-dependances.md` | P2 / P3 | D46, F11, F12, G01-G08, G11, G12, G14 |
| `T16-coherence-produit-et-doc.md` | P2 | A03, A05, A09, A18, B08, B09, C01-C05, C09, G15 |

**Ordre recommandé** (justifié dans `regressions-et-conflits.md` §4) :

```
T01  (filet de tests, aucun changement de comportement)
 ├─ T02, T03, T04          (P0 : pertes de données)
 ├─ T13 (étapes 1-2)       (P1 : fermer l'exposition réseau)
 ├─ T05, T06, T08, T11     (P1 : intégrité et contrat d'API)
 ├─ T07, T14               (P2 : état cohérent, actions sûres)
 ├─ T09 → T10              (P2 : perception)
 └─ T12, T15, T16          (P2-P4 : performance, dégraissage, cohérence)
```

Les trois P0 (T02, T03, T04) sont livrables en une vague de ~200 lignes de
modifications, toutes couvertes par un test de caractérisation qui **échoue
aujourd'hui** - c'est la définition de leur acceptation.

---

## 10. Reproductibilité des preuves

Les scripts de sonde sont **hors du dépôt** (`/tmp/audit/…`) et n'ont pas été
conservés : la contrainte « ne rien laisser dans le dépôt » primeraient sur la
commodité. Ce qui est conservé, dans les documents :

- les commandes exactes et les sorties mesurées (citées dans `registre.md`) ;
- les jeux de données de test décrits en taille et composition (§3,
  `couverture.md`) ;
- les valeurs de contraste et les ratios (recalculables à partir du CSS cité, par
  les formules WCAG) ;
- les durées, avec nombre de répétitions et dispersion (§3).

Toute personne peut rejouer les mesures : le faux wiki se résume à un
`ThreadingHTTPServer` renvoyant `siteinfo`/`categorymembers`/`parse` et un
`wikiteam3dumpgenerator` qui copie un XML ; le plan T01 le spécifie précisément.

---

## 11. Ce que je n'ai pas pu voir (limites de l'audit)

1. **Fluidité réelle** : aucune mesure de rendu, d'animation ou de scroll. Les
   constats de performance portent sur le serveur et les scripts, jamais sur le
   navigateur.
2. **Tactile** : aucun appareil, aucun émulateur. Les constats E05 (cibles
   < 24 px) sont des mesures CSS, pas des observations d'usage.
3. **Écran réel** : aucun rendu à 1 280 px, 768 px, 375 px ni à 200 %. B10 et
   E10 sont calculés, pas vus.
4. **Lecteur d'écran réel** : NVDA/VoiceOver indisponibles. E01-E11 sont de
   l'analyse de balisage ; la qualité d'annonce reste à valider.
5. **PDF** : WeasyPrint non installable (`libpango` absent) ⇒ D20, D21, D42, D46
   et F11 sont *Déduits*.
6. **Wiki réel** : Fandom/Miraheze inaccessibles ⇒ le comportement face à un vrai
   wiki (redirections, gros dumps > 1 Mo, images, International Archive) n'est pas
   observé.
7. **Docker / Windows** : `docker` et Windows absents ⇒ F11, F12, G13, H08 et les
   chemins Windows sont *Déduits*.
8. **Charge réelle longue** : le plus long run observé dure quelques secondes
   (faux wiki local) ;
   aucun run de 45 minutes, donc aucune dérive mémoire longue durée.
9. **Contenu sensible** : aucune donnée utilisateur réelle n'a été consultée ;
   aucun compte réel utilisé ; aucun système hors périmètre contacté (le faux wiki
   était local).
10. **Dépôt public** : la question n'a pas pu être tranchée (accès limité au
    dépôt). Par précaution, ce rapport **ne contient aucune recette
    d'exploitation** : les constats de sécurité décrivent le mécanisme (une
    requête `text/plain` acceptée sans contrôle d'origine) sans fournir de code
    d'attaque. Si le dépôt est public, ces documents (liste des défauts non
    corrigés) devraient être déplacés hors du dépôt avant publication.

### Ce que l'audit ne prouve pas

- L'**absence** de défauts non cherchés (rendu, i18n, accessibilité réelle).
- Que les correctifs proposés suffisent : chaque plan a ses propres critères et
  sa vérification, à exécuter séparément.
- Que les valeurs mesurées sont représentatives d'un wiki de production : elles
  viennent d'un faux wiki et de volumes synthétiques, calibrés pour reproduire
  les ordres de grandeur annoncés par le README (20 000 pages, 3 998 catégories).

---

## 12. Verdict

Le projet est **fonctionnel, lisible et bien testé pour son cas nominal**, mais
il porte **trois pertes de données silencieuses** (D01, D02, D03) et **deux
défauts de sécurité exploitables sans authentification** (H01, H02). Ces cinq
constats sont reproductibles en quelques minutes et aucun n'est couvert par la
suite de tests actuelle.

Le correctif est **modeste** : ~200 lignes pour les P0, ~400 pour l'ensemble des
P1, sans nouvelle dépendance, sans changement d'architecture, sans migration de
données. L'ordre proposé (§9) permet de livrer chaque vague indépendamment, avec
un test qui échoue avant et passe après.

Rien n'a été modifié : ce rapport est une **proposition d'exécution**.
