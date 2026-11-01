# T09 — Accessibilité : clavier, focus, noms et annonces

- **Priorité** : P2 · **Axe** : E/A · **Constats couverts** : E01, E03, E04, E05,
  E06, E07, E08, E09, E10, E11, A01
- **Justification** : l'application est une interface de travail longue durée
  (dump de 20 à 45 minutes). Aujourd'hui elle est inutilisable au clavier seul et
  muette pour un lecteur d'écran — alors que le correctif est entièrement local
  au HTML/CSS/JS déjà présent, sans nouvelle dépendance.

## Preuve et conséquence

Mesuré sur la page servie (`GET /` = 59 258 octets, `server.py:795-1957`) :

- **0** occurrence de `:focus-visible` ; `outline:none` sur les champs (E01).
- **0** `aria-*`, `role=`, `tabindex`, `for=` (E01, E04, E07, E08) — vérifié par
  `grep` sur le payload complet.
- **A01 (P1)** : la liste des jobs est une suite de `div` cliquables ; aucune
  n'est atteignable au clavier, aucune n'expose `aria-current`, et l'ordre
  d'onglets saute des contrôles à cause de `outline` supprimé et d'éléments non
  focusables.
- **E03** : l'arbre de catégories (`server.py:1627-1777`) se développe au clic
  souris uniquement (`div` + `addEventListener("click")`).
- **E05** : cibles mesurées sous 24 × 24 px — cases à cocher 14 px (`.job-cb`,
  `.opt-check`, `.fmt-check`), `.tree-toggle` 14 px, `.btn-sm` ≈ 20 px de haut
  (11,2 px de texte + 7 px de padding vertical).
- **E06** : `✕`, `▸`, `⟳` seuls dans des boutons sans `aria-label`.
- **E07** : aucun `aria-live` : les 55 mises à jour d'état (toasts, statut, étape,
  compteur de sélection) ne sont annoncées qu'en visuel.
- **E09** : l'état des étapes est porté par la couleur du point et de la barre
  exclusivement (`dot-*`, `st-*`).
- **E10** : au zoom 200 % (mesuré par calcul : sidebar 270 px fixe + `#terminal`
  300 px + `.tree-body` 380 px), trois zones défilantes imbriquées se cumulent.
- **E11** : `#terminal` est un `div` avec `overflow:auto`, sans `role="log"` ni
  `aria-live="polite"`, et `flushLogs` ajoute des `div` sans rôle.

## État actuel → état cible

- Tout contrôle actionnable est un `<button>`/`<a>`/`<input>` natif (ou reçoit
  `role`+`tabindex="0"`+gestion `Enter`/`Espace`) ; ordre de tabulation =
  ordre visuel.
- `:focus-visible` visible sur tout élément interactif (anneau 2 px, contraste
  ≥ 3:1, jamais supprimé).
- Chaque champ a un `<label for>` ; chaque bouton icône a un `aria-label`.
- La liste des jobs est un `ul[role="listbox"]` avec `aria-selected`, ou plus
  simplement des `<button role="option">` — navigation `↑/↓/Home/End`.
- L'arbre est un `role="tree"` avec `role="treeitem"`, `aria-expanded`,
  navigation flèches (`→` ouvre, `←` ferme, `↑/↓` déplace).
- `#terminal` : `role="log" aria-live="polite" aria-relevant="additions"`.
- Zones de statut/toast : `role="status"` (non bloquant) et `role="alert"` pour
  les erreurs ; une seule région live pour éviter le bavardage.
- L'état des étapes est doublé d'un texte (`Étape 3 : terminée` en `sr-only`).
- Au zoom 200 %, une seule zone défilante par axe (`main` défile, `#terminal` et
  l'arbre ont une hauteur relative `max-height: min(40vh, 380px)`).

## Cause racine et sites concernés

L'interface est construite par concaténation de chaînes HTML dans `server.py`
(`buildForm` 1336, `buildBanner` 1505, `buildActions` 1518, `buildFiles` 1563,
`renderJob`, arbre 1627-1777) : aucun composant réutilisable, donc aucune
propriété transverse (focus, rôle, nom) n'est appliquée systématiquement. Le CSS
(`server.py:795-960`) n'a ni `@media` ni `:focus-visible`.

## Référence à réutiliser

- Les éléments natifs déjà présents (`<button>`, `<input type=number>`,
  `<select>`) fonctionnent : ne pas les remplacer par des `div`.
- `DEFAULTS`/`STEPS` fournissent déjà les libellés à réutiliser pour les noms
  accessibles.
- Le CSS a déjà des variables (`--bg`, `--muted`…) : l'anneau de focus peut s'y
  brancher.

## Plan d'action

1. CSS : ajouter `*:focus-visible { outline: 2px solid var(--accent); outline-offset:
   2px }`, supprimer `outline:none`, passer les `.btn-icon` à `min-width/height:
   28px`, ajouter `.sr-only`.
2. `buildForm` : envelopper chaque champ dans `<label for>` ou ajouter
   `aria-labelledby` ; générer les `id` uniques à partir de la clé.
3. Boutons icônes : ajouter `aria-label` + `title` (une seule source :
   constante `ICON_LABELS`).
4. Liste des jobs : remplacer les `div.job-item` par des `<button>` (style
   inchangé) + `role="listbox"` sur le conteneur, `aria-selected` sur l'actif,
   gestion `ArrowUp/ArrowDown/Home/End/Enter`.
5. Arbre : `role="tree"`/`treeitem`, `aria-expanded`, `aria-checked` pour les
   cases, gestion `ArrowRight/ArrowLeft` (ouvrir/fermer sans cocher), `Espace`
   pour cocher.
6. `#terminal` : `role="log" aria-live="polite"` + `aria-label="Log du job"`.
7. Toasts : conteneur unique `role="status"` ; les erreurs passent par
   `role="alert"`. Ne pas recréer la région à chaque toast (sinon pas d'annonce).
8. Étapes : ajouter un `<span class="sr-only">` avec l'état en texte à côté du
   point coloré.
9. `@media (max-width: 900px)` : passer la sidebar en pile, `height:auto`,
   supprimer les `max-height` fixes ; `@media (prefers-reduced-motion: reduce)` :
   `animation:none; transition:none`.
10. Vérification sans navigateur : script de contrôle statique (parser le HTML
    servi, vérifier chaque `input` a un `label`/`aria-label`, chaque `button` un
    nom accessible, chaque `id` référencé existe) à ajouter dans `tests/`.

## Points d'impact

`server.py` (CSS 795-960, JS 1019-1957, templates HTML), `tests/` (nouveau
`test_markup_a11y.py`). Aucun changement d'API, aucune dépendance.

## Régression

Aucune fonctionnelle : les classes CSS et le comportement souris sont conservés ;
`outline` restauré peut changer l'apparence au focus (voulu). Risque : remplacer
`div.job-item` par `button` hérite du style natif → réinitialiser
(`all: unset` ciblé + les propriétés existantes). Régression **assumée** :
certains libellés d'icônes deviennent visibles en `title` (infobulle).

## Actions humaines requises

- Validation par un utilisateur réel de lecteur d'écran (NVDA/VoiceOver) : **non
  réalisable dans cet environnement** (aucun navigateur, aucun lecteur d'écran).
  Le plan doit être considéré comme non validé du point de vue perception tant que
  cette passe n'a pas eu lieu.

## Dépendances

T01 (tests). Indépendant des autres plans ; à faire avant T10 (contrastes) pour
ne pas retoucher deux fois les mêmes sélecteurs.

## Non-objectifs

- Pas de refonte en framework (React/Vue) : hors périmètre, coût élevé.
- Pas de support ARIA « complet » (landmarks, `aria-describedby` partout) :
  uniquement ce qui débloque un parcours réel.
- Pas de tests avec navigateur (impossible ici).

## Critères d'acceptation

1. Parcours complet au clavier : créer un job, lancer un scan, ouvrir l'arbre,
   cocher une catégorie, générer, lire le log — sans souris.
2. `grep` sur le HTML servi : 0 `input` sans `label`/`aria-label`, 0 `button`
   sans nom accessible, 0 `div` cliquable sans `role`/`tabindex`.
3. Anneau de focus visible sur tous les contrôles (contraste ≥ 3:1, calculé).
4. `role="log"` sur le terminal ; une ligne de log ajoutée produit une annonce
   (test manuel lecteur d'écran — à faire par un humain).
5. `@media` présent ; au zoom 200 % et en 375 px de large, aucun défilement
   horizontal du `body`.

## Vérification et repli

Contrôle statique automatisé (point 10) + passe humaine lecteur d'écran
(à planifier). Repli : `git revert` (le CSS et le JS sont deux commits séparés).
