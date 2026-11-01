# docs/audit-total — audit total (mode planification)

Audit de l'ensemble du dépôt, **sans aucune modification du projet** (code,
styles, dépendances, configuration, données). Date : 2026-11-01.

## Par où commencer

1. **`rapport.md`** — le rapport : méthode, base de référence mesurée, couverture,
   constats majeurs, régressions, actions humaines, limites.
2. **`registre.md`** — les **131 constats**, localisés (fichier:ligne ou écran),
   avec niveau de preuve, suggestion, verdict de régression et méthode de
   vérification.
3. **`regressions-et-conflits.md`** — les 5 régressions assumées (à valider par un
   humain, aucune n'est appliquée), la matrice des conflits entre constats et
   l'ordre d'exécution.
4. **`couverture.md`** — ce qui a été visité (routes, écrans, états, volumes) et
   ce qui ne l'a pas été, avec les exceptions déclarées.
5. **`captures/`** — pourquoi il n'y a pas d'images, et à la place les mesures
   calculées (contrastes WCAG, tailles, largeurs fixes).
6. **`../plans/audit-total/tasks/`** — les 16 plans d'exécution (P0 à P2 et causes
   communes), un fichier par plan.

## Les cinq choses à retenir

| Constat | Effet |
|---|---|
| **D01** — sans API, aucun fichier par catégorie n'est écrit | un `Misc.md` fourre-tout, job « réussi » |
| **D02** — deux jobs d'un même wiki partagent la sortie | les archives se détruisent entre elles |
| **D03** — collisions de noms de fichiers | une page perdue, comptée « resumed » |
| **H01/H02** — pas d'authentification, pas d'anti-CSRF | un site visité (ou le LAN) pilote l'outil |
| **F01** — regroupement quadratique | 4,5 s d'aperçu et serveur figé à 4 000 catégories |

## Reproduire les preuves

Aucun script de sonde n'a été laissé dans le dépôt (contrainte : ne rien laisser
derrière). La recette du harnais est dans `rapport.md` §10 et dans le plan
`T01-base-de-reference-et-tests.md` : un faux wiki MediaWiki
(`ThreadingHTTPServer` : `siteinfo`, `categorymembers`, `parse`, `/dump.xml`) et
un stub `wikiteam3dumpgenerator` sur le `PATH`.
