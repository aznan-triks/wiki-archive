# Mesures de substitution (aucune capture possible)

Source : feuille de style et HTML servis par `GET /` (59 258 octets), construits
dans `server.py` (variables CSS l. 796-802, styles l. 795-960, JS l. 1019-1957).
Toutes les valeurs ci-dessous sont **recalculables** : lancer le serveur, extraire
le CSS, appliquer la formule WCAG 2.1.

## 1. Contrastes (WCAG 2.1) — 7 échecs mesurés

Palette réelle : `--bg #0d1117`, `--surface #161b22`, `--surface2 #21262d`,
`--border #30363d`, `--text #e6edf3`, `--muted #7d8590`, `--accent #388bfd`,
`--red #f85149`, `--green #3fb950`, `--yellow #d29922`, `--term #010409`.

| Élément | Sélecteur cité | Couleurs (texte / fond) | Ratio | Seuil | Verdict | Constat |
|---|---|---|---|---|---|---|
| Texte secondaire d'une ligne de job survolée | `.job-item:hover` (`--surface2`) + `.job-meta` (`--muted`) | `#7d8590` / `#21262d` | **4,08** | 4,5 | **Échec** | B01, B22 |
| Texte « dim » du terminal | `.l-dim` | `#666666` / `#010409` | **3,58** | 4,5 | **Échec** | B02 |
| Texte indicatif des champs | `input::placeholder` (`--muted` à `opacity:.6`) | `#505760` / `#0d1117` | **2,84** (2,59 avec le mélange exact) | 4,5 | **Échec** | B03 |
| Badge « Pending » | `.st-pending` | `#7d8590` / `#21262d` | **4,08** | 4,5 | **Échec** | B04 |
| Bouton primaire | `.btn-primary` | `#ffffff` / `#388bfd` | **3,34** | 4,5 | **Échec** | B05 |
| Bouton destructeur | `.btn-danger` | `#ffffff` / `#f85149` | **3,35** | 4,5 | **Échec** | B05 |
| Bordure de champ au repos | `input`, `select` (`--border` sur `--bg`) | `#30363d` / `#0d1117` | **1,55** | 3,0 | **Échec** | B06 |

**Couples qui passent** (vérifiés, pour situer la marge) : texte principal
`#e6edf3/#0d1117` = 16,02 ; `--muted` sur `--bg` = 5,07 ; `--muted` sur
`--surface` = 4,64 ; terminal `#adbac7/#010409` = 10,39 ; `.l-ok` 8,08 ;
`.l-warn` 8,14 ; `.l-err` 6,13 ; badges `running` 5,90, `done` 5,62, `paused`
5,35, `stopped` 6,00.

**Effet de bord du survol** : `.btn:hover:not(:disabled) { opacity:.82 }` — le
bouton s'estompe sur son fond ; composité sur la carte `#161b22`, le bouton
primaire passe à `#3277d6` avec un texte `#dae7f8` : **3,53** (toujours sous le
seuil, mais légèrement moins mauvais). Le vrai échec de survol est ailleurs :
`.job-item:hover` fait passer le texte secondaire de 4,64 à **4,08** (B22).

## 2. Tailles de texte — 28 déclarations sous 12 px

Extrait (racine 16 px) : `.62rem` (9,9 px, `.tree-toggle`), `.65rem` (10,4 px,
`.step-lbl`), `.66rem` (10,6 px, `.tree-cnt`), `.68rem` (10,9 px, `.card-title`,
`.badge`, `.job-size`), `.7rem` (11,2 px, `.btn-sm`, `.job-meta`), `.72rem`
(11,5 px, `.icon-btn`, `.opt-group label`, `.fmt-title`), `.73rem` (11,7 px,
`.file-size`). Constat **B07**.

## 3. Mise en page — largeurs fixes, aucune adaptation

| Élément | Valeur citée | Conséquence |
|---|---|---|
| `.sidebar` | `width: 270px` (l. 807) | À 375 px de large, 105 px restent pour le contenu |
| `#terminal` | `height: 300px` (l. 910) | Zone défilante supplémentaire, hauteur figée |
| `.tree-body` | `max-height: 380px` (l. 935) | Trois défilements imbriqués au zoom 200 % (E10) |
| `@media` | **0** dans toute la feuille | Aucun point de rupture (B10) |
| `prefers-reduced-motion` | **0** | `@keyframes pulse` (`.dot-running`) et `transition` non désactivables (B11) |
| `prefers-color-scheme` | **0** | Thème unique sombre imposé (B21) |
| `:focus-visible` | **0** | `outline: none` sur les champs (l. 861) ; seul `:focus` = `border-color` (l. 863) (E01) |
| `aria-*` / `role=` / `tabindex` / `<label for>` | **0 / 0 / 0 / 0** | Aucune sémantique exposée (E01, E04, E07, E08) |

## 4. Autres mesures de la page

| Mesure | Valeur | Méthode |
|---|---|---|
| Poids du HTML servi | 59 258 octets | `curl -s \| wc -c` |
| Fonctions JS déclarées | 79 | extraction du payload |
| Fonctions JS jamais appelées | 2 (`loadPrefs`, `savePrefs`) | `grep` de chaque nom |
| Sélecteurs CSS sans usage | `t-hidden`, `toast`, `job-item` (variantes), `l-sep`, `l-ok`, `l-warn` ; `dot-*`/`st-*` partiellement construits dynamiquement | `grep` sur le HTML généré et le JS |
| Cibles tactiles < 24 px | cases à cocher 14 px (l. 873, 881), `.tree-toggle` 14 px | extraction CSS |
| Couleur de texte du terminal | `#adbac7` sur `#010409` | 10,39 (passe) |

> Rappel : ces valeurs sont **calculées**, pas vues. Elles ne remplacent ni un
> rendu réel, ni une session de lecteur d'écran, ni une mesure de fluidité (voir
> `README.md`).
