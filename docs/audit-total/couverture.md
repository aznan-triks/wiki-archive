# Registre de couverture — audit total

> Périmètre : tout le dépôt `aznan-triks/wiki-archive` (serveur, scripts, interface
> embarquée, docs, Docker, tests).
> Mode : **PLANIFICATION** — aucune modification du code, des styles, des
> dépendances, de la configuration ni des données du projet.
> Date : 2026-11-01.

## Environnement d'observation

| Élément | Valeur |
|---|---|
| OS hôte du bac à sable | Linux, Python 3.11.2 |
| Dépendances | `pip install -r requirements.txt -r requirements-dev.txt` dans un venv local (hors dépôt) |
| WeasyPrint | **inutilisable dans le bac à sable** (`libpango` absent, non installable) → tout le chemin PDF est *déduit*, pas observé |
| Navigateur | **aucun** (ni Chromium, ni Firefox, ni Playwright/jsdom installables) → aucune capture d'écran, aucun test de rendu/clavier réel |
| Wiki réel | **inaccessible** (réseau sortant limité à GitHub/PyPI) → pipeline observé contre un **faux wiki MediaWiki local** (serveur HTTP jetable hors dépôt) + un **stub** de `wikiteam3dumpgenerator` |
| Serveur | `DATA_DIR=/tmp/...` (hors dépôt), `uvicorn` 0.0.0.0:8080 |

Conséquence : les constats visuels sont **mesurés dans la feuille de style**
(contrastes calculés, tailles en px, absence de media queries) et non observés à
l'écran ; les constats d'interaction sont **déduits du code** (ils sont marqués
comme tels). Un audit sans navigateur ne prouve pas l'absence de défauts de rendu.

## Points d'entrée HTTP (100 % visités)

| Route | Méthode | Statut | États/essais vus | Constats |
|---|---|---|---|---|
| `/` | GET | Vu | 200, 59 258 octets | B10, E01, E08, H09 |
| `/api/jobs` | GET | Vu | liste vide, 1 job, 41 jobs | F03, G03, G04, G05 |
| `/api/jobs` | POST | Vu | URL valide, URL vide, URL invalide, JSON malformé, corps `text/plain` | D08, D28, D29, H02 |
| `/api/settings` | GET | Vu | défauts, après PUT | C02, F03 |
| `/api/settings` | PUT | Vu | nominal, valeurs non numériques, `text/plain` | D08, D27, H02 |
| `/api/jobs/{id}` | GET | **N'existe pas** (404) | — | D31 |
| `/api/jobs/{id}` | PATCH | Vu | `params`, `wiki_url` | D27 |
| `/api/jobs/{id}/start` | POST | Vu | job neuf | D18 |
| `/api/jobs/{id}/scan` | POST | Vu | scan complet (faux wiki) | D06, D44 |
| `/api/jobs/{id}/generate` | POST | Vu | sélection partielle, `selection:null`, formats `none`, formats `exe`, pendant un run | D04, D07, A08, C14 |
| `/api/jobs/{id}/pause` | POST | Vu | → état `T` (vérifié ps) | — (fonctionne) |
| `/api/jobs/{id}/resume` | POST | Vu | → état `S` | — (fonctionne) |
| `/api/jobs/{id}/stop` | POST | Vu | arbre tué < 3 s | — (fonctionne) |
| `/api/jobs/{id}/category_tree` | GET | Vu | arbre 4 nœuds ; 4 000 nœuds | C14, F02 |
| `/api/jobs/{id}/preview_packing` | POST | Vu | 4 nœuds, 4 000 catégories, `max_files` invalide, sélection inconnue | D07, D08, D30, F01, F02, F13 |
| `/api/jobs/{id}/selection` | PUT | Vu | écriture / suppression | C14 |
| `/api/jobs/{id}/disk` | GET | Vu | 5 000 fichiers / 20 Mo (45-47 ms) | mesuré, écarté (cf. rapport §6) |
| `/api/jobs/{id}/purge` | POST | Vu | `pdf`, `intermediate`, `bogus` | D19, A06 |
| `/api/jobs/bulk_delete` | POST | Vu | 1 job, job en cours, corps `text/plain` | D02, D32, H02 |
| `/api/jobs/{id}/logs` (SSE) | GET | Vu | `from_pos=0`, job terminé (`__END__`) | E11, F04 |

## Écrans et composants de l'interface (100 % visités dans le code source)

| Écran / composant | Statut | États parcourus | Constats |
|---|---|---|---|
| Barre latérale (liste des jobs) | Vu (source + rendu HTML servi) | vide, 1 job, 41 jobs, mode « Manage » | A05, A01, B01, F03 |
| En-tête (⚙ / Manage / + New) | Vu | — | B15, E06 |
| Écran vide (« No job selected ») | Vu | — | A15 |
| Formulaire « New job » | Vu | PDF coché / décoché, nouveaux params | A02, A09, C01, C16 |
| Page « Default settings » | Vu | plan Libre/Plus/Pro/Ultra/Custom | C02, C03, A14, E04 |
| Bandeau d'étape (`buildBanner`) | Vu | pending, scanned, done sans données | A03, A14 |
| Barre d'actions (Pause/Stop/Resume) | Vu | running, paused, autres | D33, A06 |
| Panneau de sélection (arbre) | Vu | tout coché, rien, partiel, filtre, tri, collapse | A01, E03, E05, F02 |
| Barre de génération + aperçu | Vu | aperçu OK, erreur, splits | D07, C09, F02 |
| Carte « Progress » (5 étapes) | Vu | running, scan terminé, done | A04, E09 |
| Terminal de logs | Vu | vide, flux, `__END__`, « Clear » | E11, F04, F05 |
| Carte « Storage » | Vu | avant/après purge | D19, C08 |
| Carte « Generated files » | Vu | 2 fichiers, 0 fichier, partagés entre jobs | D02, B12, I01 |
| Toasts | Vu | succès, erreur, annulation | A07, E07 |
| Modale | **Aucune dans l'app** | — | E01 (aucun piège de focus à vérifier) |

## Tailles, thèmes, langues

| Variante | Statut | Raison |
|---|---|---|
| Large (≥ 1 280 px) | Non observé visuellement | pas de navigateur ; structure déduite du CSS |
| Portable / tablette / mobile | Non observé | idem ; **aucune `@media`** dans la feuille de style (mesuré) |
| Zoom 200 % | Non observé | idem |
| Thème clair | Inexistant | un seul thème, aucune `prefers-color-scheme` (mesuré) |
| Langue | Anglais uniquement | interface entièrement en anglais ; aucun mécanisme i18n |

## Pipeline (scripts) — couverture dynamique

| Étape | Statut | Preuve |
|---|---|---|
| 1. Dump (`run.py` + `wikiteam3dumpgenerator`) | Vu avec **stub** local | `run2.log` ; le vrai outil n'est pas exécutable ici |
| 2. Extraction API (`extract.py`) | Vu (faux wiki, 8 pages) | `run2.log`, collision `A/B` / `A:B` observée |
| 2'. Extraction mode texte (sans API) | Vu | `run3.log` |
| 3. Conversion PDF (`convert.py`) | **Non exécuté** | WeasyPrint indisponible → déduit (D21, F11, H05) |
| 4. Catégories (`build_categories.py`) | Vu (nominal + timeouts) | `run2.log`, `run1.log` |
| 4'. Mots par page (`measure_words.py`) | Vu | 7 pages puis 2 000 pages synthétiques |
| 4.5 Groupement (`pack_files.py`) | Vu | 800 cat. (120 ms) et 3 998 cat. (3,57 s) |
| 5. PDF fusion (`merge_pdf.py`) | Partiel | chemins d'erreur non atteints (pas de PDF réels) ; `tests/test_merge_pdf.py` couvre les noms de parties |
| 5'. Export texte (`export_categories.py`) | Vu | 7 pages, puis 2 000 pages (9,3 s, 58 Mo RSS) |
| Sélection (`selection.json`) | Vu | 1 catégorie sélectionnée → 1 fichier, Misc absent |
| Pause/Reprise/Stop | Vu | états `T`/`S`, arbre tué |

## Correspondance avec le registre

131 constats : A 16 · B 18 · C 12 · D 34 · E 10 · F 8 · G 13 · H 9 · I 11
(P0 3 · P1 13 · P2 42 · P3 46 · P4 27). Les identifiants cités dans ce tableau
renvoient à `registre.md` ; les numéros qui y manquent correspondent à des
constats fusionnés (table de correspondance en tête de `registre.md`).

## Échantillonnage assumé

* Faux wiki : 8 pages dont 2 collisions de stem, 1 page non catégorisée, 1 tableau, 2 titres Unicode, 4 catégories (2 niveaux).
* Grands volumes synthétiques : 800 cat./3 000 pages, 3 998 cat./20 000 pages (poids), 2 000 pages HTML réelles (export), 5 000 fichiers (disque), 41 jobs (liste).
* Cycle de vie : 6 jobs pilotés par l'API (création, `scan`, `pause` en état `T`, `generate`, `resume`, `stop`), dont le scénario `pause` → `generate` → `resume` → `stop` qui laisse un processus suspendu orphelin (D47, reproduit).
* Non couvert : wikis réels (Fandom/Miraheze), dumps > 1 Mo, WeasyPrint, images, Internet Archive, Windows/Docker réels, lecteur d'écran réel, appareils tactiles.

## Exceptions consignées

1. **PDF** : impossibilité d'installer pango/cairo dans le bac à sable → conversion jamais exécutée.
2. **Captures d'écran** : aucun navigateur disponible → aucune preuve visuelle ; les
   constats B sont calculés depuis le CSS et les constats d'interaction sont marqués *Déduits*.
3. **Réseau** : aucun wiki réel atteignable → un faux wiki local remplace l'observation réelle.
4. **Docker** : `docker` absent → image non construite ; constats Docker *Déduits*.
