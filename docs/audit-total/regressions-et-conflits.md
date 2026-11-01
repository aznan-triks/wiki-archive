# Régressions assumées, conflits et ordre d'exécution

> Périmètre : les 131 constats de `registre.md`. Un constat n'apparaît ici que
> s'il implique soit une **régression assumée** (comportement visible qui change),
> soit un **conflit** avec un autre constat, un plan, ou une attente documentée du
> README. Tous les autres portent « Régression : Aucune » avec sa preuve.

## 1. Définition appliquée

Une régression est un changement **observable par l'utilisateur** qui n'est pas
strictement nécessaire au correctif. Dans cet audit, chaque fois qu'un correctif
impose un tel changement, il est listé ici avec : la preuve que le changement est
inévitable, l'atténuation, et la décision humaine attendue. Aucune régression
n'est appliquée par les plans : ce document est une **demande de validation**.

## 2. Tableau des régressions assumées (5)

| # | Constat | Changement visible | Pourquoi c'est inévitable | Atténuation | Validation |
|---|---|---|---|---|---|
| R1 | D02 → T03 | Le chemin de sortie gagne un niveau : `data/output/{wiki}/{job_id}/` | Le dossier actuel est dérivé du wiki seul ⇒ deux jobs s'écrasent (reproduit) ; aucun correctif ne peut garder le même chemin | `FLAT_OUTPUT=1` (mono-job, déconseillé) ; README + UI affichent le nouveau chemin | Humaine, avant exécution |
| R2 | D46 → T15 | Les images du wiki ne sont plus téléchargées par défaut | Aucun script ne consomme `dump/images` (0 référence, `grep`) ; le dump est dominé par ces octets | Case « Include images » conservée, désactivée par défaut, libellé corrigé | Humaine |
| R3 | H03 → T13 | Les wikis en adresse privée (10.x, 172.16.x, `.local`) sont refusés par défaut | Sans filtrage, l'URL fournie par le client fait interroger n'importe quel service interne (SSRF) | `ALLOW_PRIVATE_HOSTS=1`, documenté | Humaine |
| R4 | I04 → (P4, non planifié en P0-P2) | Déplier une catégorie renvoie ses pages ⇒ charge utile plus grande | Le payload actuel retire `pages` (`server.py:696-698`) pour alléger | Chargement à la demande au dépliage | Humaine (P4) |
| R5 | C02/C05 → T16 | `max_files` par défaut ≠ 50, et `dedup` par défaut à `false` | Les deux défauts contredisent le plan affiché et le README (mesuré : `Deduplication: 8 -> 6`) | Choix explicite dans les réglages ; valeurs affichées | Humaine |

### R1 — Sortie par job (D02)

- **Preuve du besoin** : job A (`Weapons`) puis job B (`Pistols`) sur la même URL
  → le dossier ne contient plus que `Pistols.md` ; `bulk_delete` de B supprime les
  fichiers de A, qui reste `done` et renvoie `files: []`.
- **Ce que l'utilisateur perd** : le chemin court `data/output/{wiki}/`.
- **Ce qu'il gagne** : deux archivages du même wiki coexistent ; supprimer l'un
  n'affecte plus l'autre.
- **Alternative rejetée** : refuser la création d'un second job sur la même URL
  (bloque un cas d'usage normal : un export PDF et un export texte du même wiki).
- **Décision attendue** : accepter le niveau supplémentaire (recommandé) ou
  choisir l'alternative « un seul job actif par wiki ».

### R2 — Images (D46)

- **Preuve du besoin** : `grep -rn "img\|image"` dans `extract.py`, `convert.py`,
  `clean_html.py`, `export_categories.py` → uniquement du CSS. `convert.py` ouvre
  le HTML avec `HTML(filename=src)` sans `base_url`, donc les images distantes ne
  sont même pas résolues de façon fiable.
- **Ce que l'utilisateur perd** : les fichiers d'images dans `dump/` (qu'il ne
  voit pas dans l'interface : aucun navigateur de dump).
- **Décision attendue** : désactiver par défaut (recommandé) ou implémenter le
  support complet (réécriture des `src` + `base_url`), qui est un travail de
  développement distinct, non couvert par les plans P0-P2.

### R3 — Wikis privés (H03)

- **Preuve du besoin** : le serveur émet des requêtes vers l'hôte fourni ;
  aucun filtrage. Un contenu hostile (page HTML d'un site visité, cf. H02) peut
  faire interroger `169.254.169.254` ou un port d'administration local.
- **Ce que l'utilisateur perd** : la possibilité d'archiver un wiki interne
  **sans changer un réglage**.
- **Décision attendue** : accepter le refus par défaut + échappatoire.

### R5 — Défauts de planification (C02, C05)

- **Preuve** : `DEFAULTS.max_files = 50` (`MAX_FILES` par défaut) et
  `notebooklm_plan = "plus"` (100 sources) ; `dedup = True` alors que le README
  promet « a page appears in every file of its categories » ; mesuré
  `Deduplication: 8 -> 6` sur 8 pages.
- **Ce que l'utilisateur perd** : la valeur 50 comme défaut, et l'absence de
  doublons.
- **Décision attendue** : deux choix binaires, indépendants.

## 3. Conflits détectés entre constats

| Conflit | Nature | Arbitrage retenu | Conséquence |
|---|---|---|---|
| **D02 vs D10** | Deux changements de chemins/noms de fichiers dans la même zone | T03 (dossier) **avant** T04 (noms) | Un seul commit de migration, un seul message de changement |
| **C02 vs C03** | Deux valeurs de plan (« Plus » = 100 dans le code, 300 dans `PLAN.md`) | La constante `NOTEBOOKLM_PLANS` fait foi ; `PLAN.md` est corrigé | Aucune donnée migrée ; seul le texte change |
| **C05 vs C14** | La déduplication (C05) et les pages non catégorisées (C14) changent toutes deux le contenu des fichiers | Les deux sont livrées dans T16 et T11, avec un avertissement dans l'aperçu | Volume produit supérieur ; à annoncer dans le CHANGELOG |
| **D04 vs T06** | « Valider avant de nettoyer » suppose de connaître les formats valides **avant** l'étape 5 | La validation se fait en tête de `main()` (avant toute écriture) | T06 impose l'ordre : validation → dossier temporaire → publication |
| **F01 vs T11** | L'aperçu doit être exact (T11) mais le calcul actuel est déjà trop lent (F01) | F01 d'abord (algorithme), T11 ensuite (exactitude) | Si T11 passe avant, l'aperçu devient plus lent qu'aujourd'hui |
| **T09 vs T10** | Les deux modifient le même bloc CSS (focus/`:hover`/contrastes) | T09 puis T10, deux commits distincts | Évite un conflit de fusion interne |
| **H01 vs confort local** | Restreindre l'écoute à `127.0.0.1` casse l'accès depuis une autre machine | Défaut `127.0.0.1` + `HOST`/`APP_TOKEN` documentés | Régression assumée, non chiffrée en §2 : elle est inhérente au correctif de sécurité H01 (un service sans authentification ne peut pas rester exposé) |
| **D01 vs D07/C14** | Rendre le mode texte fonctionnel change le nombre de fichiers produits en mode texte | Les deux corrigent le **même** déficit de comptage | L'aperçu doit refléter les deux (T11) |
| **G01 (CSS mort) vs G02/B21** | `dot-*`/`st-*` sont construits dynamiquement (`dot-${status}`) | Ne supprimer que les sélecteurs réellement orphelins | Le dégraissage (T15) doit être fait APRÈS T09/T10 |
| **D47 vs A08/T14** | `generate` pendant une pause lance un second processus (A08) et le premier devient orphelin (D47) | Un seul correctif : liste des processus par job + refus 409 (T07 point 10, T14 point 1) | Un seul endroit à corriger, deux constats fermés |
| **D38 vs tout** | Les tests de caractérisation doivent échouer **avant** les correctifs | T01 en premier, avec `xfail(strict=True)` | Ordre imposé, sinon les tests « passent » sans rien prouver |

## 4. Dépendances et ordre d'exécution

```
T01 (tests)  ──┬── T02 (D01 texte)
               ├── T03 (D02 sortie)  ── T04 (D03/D10 noms) ── T12 (F01 perf)
               │        └── T06 (D04 étape 5 sûre) ── T07 (état)
               ├── T05 (D05/D06/D44 extraction)
               ├── T08 (validation API) ── T13 (sécurité H02 puis H01/H03)
               ├── T09 (a11y) ── T10 (contrastes) ── T15 (dégraissage CSS)
               ├── T11 (aperçu/sélection)   [après T03, T12]
               ├── T14 (actions/retours)    [après T07, T08]
               └── T16 (cohérence produit/doc)
```

**Ordre recommandé (par vagues)** :

1. **Vague 0 — filet** : T01. Aucun changement fonctionnel.
2. **Vague 1 — pertes de données (P0)** : T02, T03, T04. Une seule livraison,
   car les trois touchent `run.py`/`names`/`paths`.
3. **Vague 2 — exposition (P1 sécurité)** : T13 étapes 1-2 (H02, H01). C'est la
   seule correction qui protège contre un acteur **existant** : elle passe avant
   les correctifs de confort.
4. **Vague 3 — intégrité (P1)** : T05, T06, T08, T11 (avec T12 si l'aperçu est
   jugé trop lent après T11).
5. **Vague 4 — cohérence d'état (P2)** : T07, T14.
6. **Vague 5 — perception (P2)** : T09, T10.
7. **Vague 6 — propreté/cohérence (P2-P4)** : T12, T15, T16.

Justification de l'ordre : (a) aucun correctif n'est appliqué sans test qui
échoue d'abord ; (b) la sécurité réseau (H02/H01) est traitée avant les
améliorations, car son coût d'inaction est une compromission, non une gêne ;
(c) les P0 de perte de données précèdent la sécurité, car ils se produisent à
chaque utilisation de l'outil, alors que l'exposition réseau dépend du contexte ;
(d) les plans de perception (a11y, contrastes) viennent après parce qu'ils
touchent le même fichier (`server.py`) et provoqueraient des conflits.

## 5. Ce qui n'est PAS une régression

Pour éviter les faux positifs lors de la revue des correctifs :

- **Un fichier de sortie en plus** (`Misc.md`, C14/T11) n'est pas une régression :
  c'est la correction d'une omission silencieuse ; les pages étaient déjà dans
  `Misc` quand aucune sélection n'existait.
- **Un nom de fichier différent en cas de collision** (T04) n'est pas une
  régression : aujourd'hui, la page est **perdue**.
- **Un refus 400/403** là où l'application acceptait une entrée invalide (T08,
  T13) n'est pas une régression : l'état créé était inutilisable (500 au premier
  usage).
- **Un log plus bavard** (T05, T06, T16) n'est pas une régression : le terminal
  défile et est déjà plafonné (T12).
- **Un rebuild complet** consécutif à une dépendance épinglée (T15) n'est pas une
  régression : c'est le prix de la reproductibilité.

## 6. Risques résiduels acceptés par l'audit

| Risque | Où | Pourquoi accepté |
|---|---|---|
| Le pipeline reste dans le processus du serveur (pas de service détaché) | D16/T07 | Un détachement change le modèle de déploiement ; T07 rend l'interruption honnête (`interrupted`) et récupérable |
| `weasyprint` reste non épinglé dans les tests de PDF | T15 | Les tests n'exercent pas WeasyPrint (indisponible dans cet environnement : `libpango` absent) |
| Les tests de sécurité ne couvrent pas le DNS rebinding | T13 | Hors périmètre : nécessite un contrôle du résolveur ; documenté comme limite |
| Aucun test de rendu visuel | T09/T10 | Aucun navigateur dans l'environnement d'audit (déclaré en `couverture.md`) |
