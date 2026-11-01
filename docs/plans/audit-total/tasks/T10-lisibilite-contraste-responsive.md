# T10 — Lisibilité : contrastes, tailles de texte, largeur et mouvement

- **Priorité** : P2 · **Axe** : B/E · **Constats couverts** : B01, B02, B03, B04,
  B05, B06, B07, B10, B11, B21, B22, E10 (volet responsive, partagé avec T09)
- **Justification** : 7 couples texte/fond échouent au contraste WCAG AA, 28
  règles descendent sous 12 px, et la mise en page suppose une fenêtre ≥ 1 100 px.
  Le tout a été **mesuré** sur le CSS servi, pas estimé.

## Preuve et conséquence

Mesures (`contrast.py`, ratios calculés selon WCAG 2.1, seuil 4,5:1 texte
courant / 3:1 grand texte et composants) :

| Élément | Couleurs | Ratio | Seuil | Constat |
|---|---|---|---|---|
| `.job-meta` sur `.job-item:hover` | `#7d8590` / `#21262d` | **4,08** | 4,5 | B01 |
| `.l-dim` du terminal | `#666666` / `#010409` | **3,58** | 4,5 | B02 |
| `input::placeholder` (`--muted` à `opacity:.6`) | `#505760` / `#0d1117` | **2,84** | 4,5 | B03 |
| `.st-pending` | `#7d8590` / `#21262d` | **4,08** | 4,5 | B04 |
| `.btn-primary` | `#ffffff` / `#388bfd` | **3,34** | 4,5 | B05 |
| `.btn-danger` | `#ffffff` / `#f85149` | **3,35** | 4,5 | B05 |
| Bordure d'`input` au repos | `#30363d` / `#0d1117` | **1,55** | 3,0 | B06 |

- **B07** : 28 déclarations `font-size` sous 12 px (0,62 à 0,73 rem, racine 16 px → 9,9 à 11,7 px)
  — mesurées par extraction du CSS, y compris des libellés de formulaire.
- **B10** : `.sidebar` 270 px fixe, grille à deux colonnes sans `@media` ;
  **0** `@media` dans tout le CSS (vérifié par `grep`). À 375 px de large, la zone
  de contenu tombe sous 105 px : inutilisable.
- **B11** : 0 `prefers-reduced-motion` alors que le CSS anime la barre de
  progression et les badges (`transition`, `@keyframes`).
- **B21** : thème unique ; `loadPrefs`/`savePrefs` (G02) montrent qu'un thème
  alternatif a été amorcé puis abandonné.
- **B22** : `.btn:hover` éclaircit le fond sans changer le texte → le contraste
  des boutons primaires **baisse encore** au survol.

## État actuel → état cible

- Tous les couples texte/fond ≥ 4,5:1 (≥ 3:1 pour ≥ 24 px ou gras ≥ 19 px) ;
  bordures de champs ≥ 3:1.
- Aucun texte fonctionnel sous 12 px ; 13 px minimum pour le log, 14 px pour les
  libellés.
- Une seule règle de disposition, avec `@media (max-width: 900px)` (pile) et
  `@media (max-width: 600px)` (contrôles pleine largeur) ; aucune largeur fixe en
  px pour les conteneurs principaux.
- `prefers-reduced-motion: reduce` neutralise animations et transitions.
- Un second thème (clair) **optionnel** : si retenu, il doit être validé par les
  mêmes mesures de contraste ; sinon, supprimer `loadPrefs`/`savePrefs` (G02).
- `:hover` ne dégrade jamais le contraste (assombrir le fond ou changer le texte
  simultanément).

## Cause racine et sites concernés

Palette définie une fois (`server.py:795-830`) sans contrainte de contraste, puis
réutilisée avec des variantes ad hoc (`#666`, `#8a8a8a`, opacités) ; tailles
fixées au cas par cas en `rem` arbitraires ; largeurs en `px` (`270px`, `300px`,
`380px`) et une grille sans point de rupture. Aucun test de contraste dans la
suite.

## Référence à réutiliser

- Les variables CSS existantes (`--muted`, `--accent`, `--border`) : corriger la
  palette **une fois** corrige la majorité des 7 échecs.
- `/tmp/audit/contrast.py` (script jetable de cet audit) peut être transposé en
  `tests/test_css_contrast.py` (parse le CSS, calcule les ratios) : c'est la
  seule façon de garantir la non-régression.

## Plan d'action

1. Définir la palette cible (documenter les ratios visés dans un commentaire du
   CSS) : `--muted` → `#9aa4b2` (≥ 5,2 sur `--bg`, ≥ 4,6 sur `--panel`), `.dim`
   → `#8f8f8f` (≥ 5,4 sur `#111`), placeholder → `#8d96a3`, `--accent` pour
   `btn-primary` assombri jusqu'à ≥ 4,5, `btn-danger` idem, `--border` ≥ 3:1.
2. Remplacer les 28 `font-size` < 12 px : 12 px minimum (libellés secondaires),
   13 px (log), 14 px (formulaires) ; conserver la hiérarchie visuelle par la
   graisse et la couleur, pas par la taille.
3. Réécrire la mise en page en `grid-template-columns: minmax(220px, 270px) 1fr`
   + `@media (max-width: 900px) { grid-template-columns: 1fr; }` ; `#terminal
   { height: clamp(180px, 30vh, 300px) }` ; `.tree-body { max-height: min(45vh,
   380px) }` ; `.sidebar { width: auto }`.
4. `@media (prefers-reduced-motion: reduce) { *, *::before, *::after {
   animation-duration: .01ms !important; transition-duration: .01ms !important } }`.
5. Décider du thème : soit ajouter `[data-theme="light"]` avec variables
   inversées (et l'exposer dans les réglages, en réutilisant `loadPrefs`/
   `savePrefs` — sinon G02 est un code mort à supprimer), soit supprimer G02.
   **Décision humaine requise** (voir « Actions humaines »).
6. `.btn:hover` : assombrir le fond primaire, éclaircir le texte, ou ajouter
   `filter: brightness(.92)` sur le fond uniquement — recalculer les ratios.
7. `tests/test_css_contrast.py` : extraire les couples du CSS, échouer si un
   couple texte/fond < seuil ; vérifier aussi qu'aucune `font-size` < 12 px
   n'apparaît.

## Points d'impact

`server.py:795-960` (CSS) uniquement, plus `tests/test_css_contrast.py` et la
décision G02 (JS). Aucun changement de balisage (T09 s'en charge).

## Régression

Aucune fonctionnelle : aucun comportement, aucune API, aucune donnée.
Régression **esthétique assumée** : la palette s'éclaircit/s'assombrit et la
densité augmente (textes plus grands) — plusieurs éléments tiendront sur moins de
lignes ; à valider visuellement par un humain (impossible ici : pas de
navigateur). Documenter les ratios avant/après dans le commit.

## Actions humaines requises

1. Choix : thème unique corrigé **ou** second thème clair. Si le thème clair est
   retenu, il faut une passe visuelle humaine.
2. Validation visuelle finale (aucun navigateur dans cet environnement) : les
   contrastes sont calculés, pas vus. Les tailles et retours à la ligne ne sont
   **pas observés**.

## Dépendances

T09 (les sélecteurs de focus/`aria` sont dans le même bloc CSS ; faire T09
d'abord évite deux passages sur les mêmes lignes).

## Non-objectifs

- Pas de design system ni de bibliothèque CSS.
- Pas de thème « sombre/clair automatique par `prefers-color-scheme` » si le
  choix humain est « thème unique ».
- Pas de refonte graphique.

## Critères d'acceptation

1. `tests/test_css_contrast.py` vert : 0 couple sous seuil, 0 `font-size` < 12 px.
2. `@media` présent (≤ 900 px et ≤ 600 px) ; à 375 px de large, pas de
   débordement horizontal (vérifié par calcul de largeur, pas visuellement).
3. `prefers-reduced-motion` neutralise les animations.
4. Ratios avant/après consignés dans le message de commit.

## Vérification et repli

`python -m pytest tests/test_css_contrast.py`. Repli : `git revert` (CSS seul).
