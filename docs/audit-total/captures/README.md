# Captures — pourquoi ce dossier ne contient pas d'images

**Aucune capture d'écran n'a pu être produite.** Aucun navigateur n'est
installable dans l'environnement d'audit (ni Chromium, ni Firefox, ni
Playwright/Puppeteer ; `npm` est bloqué par le réseau). Une « capture » simulée
(un rendu par un moteur tiers, ou une image générée) serait une **preuve fausse** :
elle ne montrerait pas ce que l'utilisateur voit réellement. Elle n'a donc pas été
produite.

Ce que ce dossier contient à la place : les **mesures qui peuvent être faites sans
navigateur**, avec leur méthode de calcul et la citation de code correspondante —
c'est-à-dire des preuves vérifiables et reproductibles, à défaut de preuves
visuelles.

## Fichiers

| Fichier | Contenu |
|---|---|
| `README.md` | ce document : ce qui manque, pourquoi, et ce qui le remplace |
| `mesures-css.md` | contrastes calculés (WCAG 2.1), tailles de texte, largeurs fixes, animations, absence de `@media` |

## Ce qu'une capture aurait apporté (et qui reste à faire)

1. La **fluidité** perçue (animations, défilement du terminal, latence de l'aperçu
   telle qu'elle se ressent) — non mesurable sans navigateur.
2. Le **rendu aux différentes largeurs** (375 px, 768 px, 1 280 px) et au **zoom
   200 %** — B10 et E10 sont calculés, pas vus.
3. Les **états de survol et de focus** réels — E01 et B22 sont calculés.
4. Le **comportement tactile** — E05 est mesuré en CSS.
5. La **qualité d'annonce d'un lecteur d'écran** — E07, E08, E11 sont des constats
   de balisage.

**Action recommandée** : après exécution des plans T09 (clavier/focus) et T10
(contrastes/responsive), faire une passe humaine de captures aux 4 largeurs et au
zoom 200 %, plus une passe NVDA (Windows) ou VoiceOver (macOS), et déposer les
images ici. Tant que ce n'est pas fait, les constats B/E restent des constats
**calculés** ou **déduits**, jamais « vus ».

## Méthode des mesures de substitution

- HTML servi récupéré par `curl http://127.0.0.1:8080/` (59 258 octets), CSS et JS
  extraits du même payload (ils sont embarqués dans `server.py`).
- Contrastes : formule WCAG 2.1 (`(L1+0.05)/(L2+0.05)`, luminance relative sRGB),
  seuils 4,5:1 (texte courant), 3:1 (grand texte ≥ 24 px ou gras ≥ 19 px,
  composants d'interface).
- Tailles : extraction des déclarations `font-size`, conversion en pixels avec une
  racine de 16 px.
- Mise en page : extraction des largeurs fixées en `px` et recherche de
  `@media`/`prefers-*` (0 occurrence).
