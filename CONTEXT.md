# CONTEXTE PROJET : wiki-archive

> Dernière mise à jour : 2026-09-28.
> ⚠️ Fichier `.env` présent à la racine — ne jamais le lire, l'exposer, ni citer son contenu.

## Nature

Pipeline Docker qui archive un wiki MediaWiki entier (dump → HTML → PDF/Markdown/texte, un fichier par catégorie), pour import dans NotebookLM. Statut : actif.

## Commandes
- Lancer le pipeline : `docker-compose up` (voir `docker-compose.yml`, `run.bat`, `update.bat`)
- Pas de suite de tests automatisée sur disque.
- Vérifier avant tout terminé : manquant — pas de tests, pas de recherche des valeurs en dur — à créer. Seul contrôle existant : « Contrôle des couches » ci-dessous (exécuté le 2026-09-29 : vide ; ne couvre ni comportement ni valeurs en dur).
- Version : pas de versioning formel.

## Architecture

**Modules / couches** :
| Module | Rôle | Règle d'isolation |
|---|---|---|
| Extraction (wikiteam3) | dump du wiki source | n'importe jamais la génération PDF |
| Server (`server.py`) | FastAPI/HTTP, orchestration | seul point d'entrée du pipeline |
| Génération HTML | conversion dump → HTML (`scripts/extract.py`) | n'importe ni PDF ni serveur ; interroge l'API du wiki (`requests`, catégories/rendu) — pas « sans réseau » |
| Génération PDF (WeasyPrint) | HTML → PDF par catégorie (`scripts/convert.py`, `scripts/merge_pdf.py`) | pas d'accès direct au dump brut |

### Règles d'architecture (vérifiées sur disque le 2026-09-29)
- Couches et droits : `server.py` (web) lance `scripts/run.py` en sous-processus ; `run.py` enchaîne les scripts d'étape (`extract`, `build_categories`, `pack_files`, `convert`, `merge_pdf`, `export_categories`) en sous-processus, jamais par import. Les scripts d'étape ne s'importent pas entre eux (seule exception voulue : `export_categories` → `clean_html`) ni `server`/`run`. WeasyPrint/pikepdf uniquement dans `convert.py`/`merge_pdf.py` ; seule exception côté serveur : `server.py` importe `pack_files`.
- Contrôle des couches : `grep -nE "^\s*(from|import)\s+(extract|run|server|convert|merge_pdf|build_categories|detect_wiki|pack_files)\b" scripts/*.py ; grep -nE "^\s*(from|import)\s+.*(weasyprint|pikepdf)" scripts/extract.py scripts/build_categories.py scripts/detect_wiki.py scripts/export_categories.py scripts/clean_html.py scripts/pack_files.py` (doit revenir vide ; exécuté le 2026-09-29 : vide).
- Points d'extension : nouvelle étape = un script dans `scripts/` (entrées/sorties en arguments) + un appel dans `scripts/run.py` + une entrée de `STEPS` dans `server.py` ; nouveau format d'export = option de `export_categories.py` (`export_formats`).
- Config : réglages du pipeline dans `DEFAULTS` de `server.py` (surchargés par l'interface, sauvés dans `data/settings.json`) ; chemins et ports par variables d'environnement (`SCRIPTS_DIR`, `DATA_DIR`, `PORT`, `NOTEBOOKLM_MAX_WORDS`…). Les plans NotebookLM (`NOTEBOOKLM_PLANS`) sont en dur dans `server.py`.
- Carte : `server.py` (~2000 lignes : API + interface HTML intégrée), `scripts/` (une étape par fichier), `extract.py` à la racine (29 lignes, non référencé par Dockerfile, compose, `run.bat`, `server.py` ; version plus ancienne de `scripts/extract.py`, à trancher) ; `grep -n "def " server.py scripts/*.py` avant de créer.

Flux détaillé (5 étapes) et scripts associés : voir `PLAN.md` (§"Technical context") et `README.md` — s'y référer plutôt que dupliquer ici.

## Livraison

- Dépôt git existe (1 commit, 2026-08-12) : `origin` → `github.com/aznan-triks/wiki-archive.git`.
- Compte GitHub requis : `aznan-triks` — vérifier `gh auth status` avant toute action git (switch avec `gh auth switch --hostname github.com --user aznan-triks` si besoin ; le switch ne tient pas entre deux push, revérifier avant chaque push).
- Commit/push : à défaut de règle explicite du projet, demander avant.
- Test en conditions réelles : relancer le pipeline complet (`docker-compose`) sur un wiki de test après tout changement d'une étape.

## Règles propres au projet

- Toute modification touchant une étape du pipeline signalée cassée (dump incomplet, PDF corrompu…) : diagnostic avant fix (cause racine avant symptôme, cf. METHODE §2/§5).
- Isolation stricte entre étapes du pipeline (cf. tableau Architecture) : ne pas faire fuiter la logique d'une étape dans une autre.

## Pièges
- ⚠️ Le fichier `.env` contient des secrets — ne jamais le lire ni le citer.
- ⚠️ `gh auth switch` ne tient pas durablement entre deux push (constaté sur top-des-tops) — revérifier `gh auth status` avant chaque push, même après un switch déjà fait dans la session.

## Règles communes

> Propres à ce projet (aucun fichier commun à la racine du coffre) : les adapter ici.

- **Parler** : français, bref mais clair ; l'utilisateur ne lit pas le code (pas de nom de fonction ni de jargon bruts) ; fichier cité dans le chat = lien en chemin absolu.
- **Vérité** : « terminé » dit ce qui a été vérifié, comment, et ce qui ne l'a pas été ; un défaut vu en passant se signale ; rien d'inventé (`TBD`) ; un résumé n'est pas une preuve, vérifier sur disque.
- **Avant d'agir** : lire `NEXT_SESSION` puis ce fichier ; chercher l'existant avant de créer ; vérifier sur internet ce qui peut avoir changé, jamais de mémoire ; ne toucher qu'à ce projet ; consigne floue qui change le résultat → demander ; rien déplacer ni supprimer sans accord.
- **Plans** : commencent par « Terminé quand » (conditions vérifiables) ; rédiger ≠ exécuter sans mandat ; micro-fix (≤ 10 lignes, ≤ 2 fichiers, rien de visible) sans plan.
- **Code** : diff minimal, rien de spéculatif ; chercher avant d'écrire (pas de doublon) ; couches séparées ; aucune valeur réglable en dur ; jamais d'erreur avalée ; bug non évident → une ligne dans « Pièges ».
- **Livrer** : tout ce qui est publié en anglais ; `CHANGELOG.md` avec **Plain words:** et **Technical:** ; `gh auth status` avant chaque push ; commit + push après chaque tranche vérifiée, jamais de secret.
- **État** : `NEXT_SESSION` = état présent, une ligne par sujet réécrite, jamais journal ni changelog, court ; questions pour l'auteur dans le `DECISIONS.md` de ce projet ; règle ou architecture changée → ce fichier à jour.
- **Agents** : un script pour le mécanique ; sous-agent seulement si beaucoup de lecture pour un résultat court, modèle recommandé (le moins cher qui suffit).
