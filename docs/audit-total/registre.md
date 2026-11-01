# Registre des constats

**131 constats** numérotés (A 16 · B 18 · C 12 · D 34 · E 10 · F 8 · G 13 · H 9 ·
I 11 ; P0 3 · P1 13 · P2 42 · P3 46 · P4 27). Format : **ID — titre** · axe ·
priorité, puis *Cité* (emplacement), *Preuve* (niveau), *Constat*, *Suggestion*,
*Régression*, *Vérification*. Les plans complets vivent dans
`docs/plans/audit-total/tasks/`.

Les numéros manquants correspondent à des constats **fusionnés** pour éviter les
doublons (une suggestion = un constat) : A11→A06/A08 · A16→A13/C07 · B13→A07 ·
B19→A03 · C06→D05 · C12→A09 · C13→C04 · D09→H02 · D11→B08 · D12→B09 · D13→A08 ·
D26→D25 · D34-D37→D02/D10/F01 · E02→A01 · F07→D42 · G09→D01 · H11→G14 ·
H12→G11 · I07→B21. Les numéros encore absents (B16, B20, C10, D22, D23, D41,
D43, E12, F06, F08, F09, F10, F14, G10, H07) ont été **écartés après
vérification** : pas de défaut démontrable, ou comportement acceptable mesuré
(voir `docs/audit-total/rapport.md`, section « ce qui a été écarté »).

Axe : A tâches/expérience · B visuel/finition · C cohérence/parité ·
D fonctionnel/bugs · E accessibilité · F performance · G debloat · H sécurité ·
I complétude.
Niveau de preuve : *Observé* · *Reproduit* · *Mesuré* · *Déduit* · *Hypothèse*.

> **Confidentialité.** Le dépôt distant est public
> (`github.com/aznan-triks/wiki-archive`). Les constats de sécurité (axe H) sont
> volontairement décrits **sans charge utile ni mode opératoire** : ils
> identifient la faiblesse, sa conséquence et la correction, pas un moyen
> d'attaque prêt à l'emploi.

---

## Axe A — Tâches et expérience (16 constats)

**A01 — La liste des jobs n'est pas utilisable au clavier** · A+E · **P1**
- Cité : `server.py:1132` (`<div class="job-item" onclick="selectJob(...)">`), `server.py:817-819`; aucun `tabindex`, `role` ni `keydown` (`grep` : 0 occurrence de `tabindex`, `role=`, `aria-`).
- Preuve : Déduit (source) + Mesuré (0 `tabindex`/`role=` dans tout `_HTML`).
- Constat : avec 3 jobs, un utilisateur clavier ne peut en ouvrir aucun ; impossible d'auditer, relancer ou supprimer un job sans souris.
- Suggestion : rendre chaque ligne focusable (`tabindex="0"`, `role="button"` ou mieux un `<button>` plein-largeur), activer sur `Enter`/`Espace`, et marquer l'élément actif par `aria-current="true"`.
- Régression : Aucune — `selectJob()` est le seul point d'entrée ; un `<button>` conserve le `onclick` et les styles `.job-item` (à réappliquer sur `button` : `text-align:left; background:none; border:0; width:100%`).
- Vérification : `Tab` depuis le champ URL atteint chaque ligne ; `Enter` ouvre le job ; aucune capture d'écran de la liste ne change (même rendu).

**A02 — Appuyer sur Entrée dans le champ URL ne fait rien** · A · **P2**
- Cité : `server.py:1340-1386` (`buildForm`) : aucun `<form>`, aucun `keydown`; bouton explicite `🔍 Step 1 — Scan the wiki` (l.1382).
- Preuve : Déduit (aucun `<form>`/`keydown` dans `_HTML`).
- Constat : le geste universel « coller l'URL + Entrée » ne déclenche rien et n'affiche aucun retour ; l'utilisateur doute d'avoir collé la bonne URL.
- Suggestion : envelopper le formulaire dans `<form onsubmit="…; return false">` et brancher `Submit` sur `scanFromForm`.
- Régression : Aucune — `submitFull`/`scanFromForm` restent inchangés ; à vérifier : n'ajoute pas de rechargement de page (retour `false`).
- Vérification : coller une URL, `Enter` → le scan démarre (statut `running`, log `[1/5]`).

**A03 — Trois modèles mentaux concurrents pour le même parcours** · A+C · **P2**
- Cité : `server.py:1505-1516` (`buildBanner` : « Step 2 — Choose which categories… »), `server.py:109-115` (5 étapes `STEPS`), `server.py:1382-1383` (« Step 1 — Scan the wiki », « Do everything at once »), README §5-step pipeline.
- Preuve : Observé (HTML servi, libellés) — le bandeau numérote 1/2, la carte Progress 1→5, le README 1→5 avec d'autres noms encore.
- Constat : l'utilisateur ne sait pas si « Step 1 » désigne le dump, le scan, ou la première des 5 étapes ; le bouton « Do everything at once » contredit le parcours en 2 étapes mis en avant.
- Suggestion : une seule numérotation (garder les 5 étapes techniques dans la carte Progress, nommer les actions par leur effet : « Analyser le wiki », « Générer les fichiers », « Tout faire d'un coup »), et retirer les numéros du bandeau.
- Régression : Aucune — libellés uniquement ; `STEPS[].marker` (`[1/5]`…) est utilisé par `flushLogs` (l.1918-1926) et ne doit pas changer.
- Vérification : aucune occurrence de « Step 2 » dans le bandeau ; la carte Progress reste pilotée par les marqueurs.

**A04 — Après un scan réussi, la barre de progression reste bloquée sur « Categories »** · A · **P2**
- Cité : `server.py:1918-1926` (`flushLogs`) : `setStep()` est piloté par les marqueurs `[n/5]` et par `PIPELINE COMPLETE`; un scan imprime `SCAN COMPLETE` (`scripts/run.py:359-365`) qui ne contient ni marqueur `[5/5]` ni `PIPELINE COMPLETE`.
- Preuve : Reproduit (journal `run2.log`/`scan` via l'API : dernière ligne `✓ SCAN COMPLETE`) + Déduit (code JS).
- Constat : l'étape 4 « Categories » reste affichée comme active et l'étape 5 reste grise, indéfiniment : on croit que le scan travaille encore alors que le statut est `Scanned`.
- Suggestion : traiter `SCAN COMPLETE` comme une fin de phase (toutes les étapes 1→4 `done`, 5 masquée ou libellée « en attente de génération ») en réutilisant le même mécanisme que `sawEnd`.
- Régression : Aucune — ajout d'un motif `if (text.includes("SCAN COMPLETE"))`; la génération complète garde `PIPELINE COMPLETE`.
- Vérification : lancer un scan et lire la carte Progress : les 4 premières étapes sont vertes, aucune active.

**A05 — Deux jobs sur le même wiki sont indiscernables dans la liste** · A · **P2**
- Cité : `server.py:1028-1030` (`jobName()` = `hostname`), `server.py:1133-1139` (nom + statut + âge seulement), `title` = URL identique.
- Preuve : Observé (41 jobs créés sur la même URL : libellés identiques) — `GET /api/jobs` renvoie `id` et `created_at`, jamais affichés.
- Constat : impossible de choisir le job porteur de la sélection ou des fichiers générés ; on en ouvre un au hasard et on agit sur le mauvais archivage.
- Suggestion : afficher un discriminant stable (id court `20261101-0008` ou `namespaces`/formats) à côté de l'horodatage relatif, et exposer `id` dans le titre de la ligne.
- Régression : Aucune — ajout de texte ; `selectJob('…id…')` inchangé.
- Vérification : deux jobs du même wiki produisent deux libellés distincts dans la liste.

**A06 — Actions destructrices sans confirmation (suppression, purge, « New full dump »)** · A+H · **P1**
- Cité : `server.py:1193-1213` (`requestDelete`) : suppression réelle **automatique 5 s après** un toast « annulable »; `server.py:1862-1863` (boutons purge) ; `server.py:1375` (`f-clean`, « New full dump (wipes everything) ») ; `server.py:1186-1191` (`cleanupStoppedErrored` : supprime tous les jobs arrêtés/en erreur).
- Preuve : Reproduit (`POST /api/jobs/bulk_delete` via l'UI équivaut à `requestDelete` → disparition définitive des données et des logs) ; Déduit pour le toast (minuteur de 5 s, `onTimeout: commit`).
- Constat : un clic sur 🗑 (cible 25 px, sans libellé) programme la destruction irréversible du dump, des PDF et des logs ; si l'utilisateur ne lit pas le toast dans les 5 s, c'est perdu. « Free up space » et « New full dump » n'ont aucune confirmation.
- Suggestion : confirmation explicite (`confirm()` ou mini-dialogue) pour 🗑, « Clean up stopped/errored », « Free up space » et `f-clean` ; porter le délai d'annulation à ≥ 10 s et écrire « Suppression dans 5 s — Annuler ».
- Régression : Aucune — un clic de plus, aucune perte de fonction ; le chemin `bulk_delete` reste identique.
- Vérification : 🗑 ouvre une confirmation ; annuler laisse le job et ses fichiers intacts.

**A07 — Le toast d'annulation décrit une action qui n'a pas encore eu lieu** · A · **P3**
- Cité : `server.py:1196-1212` : libellé « Job deleted -- undo available » alors que la requête part seulement à l'expiration du minuteur (`onTimeout: commit`).
- Preuve : Déduit (code) — aucune suppression au moment du toast.
- Constat : message faux au moment où il s'affiche ; l'utilisateur croit devoir agir en urgence, ou croit que c'est déjà fait et ferme l'onglet (dans ce cas rien n'est supprimé — comportement inverse de ce qu'il croit).
- Suggestion : « Job will be deleted in 5 s — [Cancel] » puis, à l'exécution, « Job deleted » (2 toasts distincts).
- Régression : Aucune — même logique, libellés distincts.
- Vérification : le premier toast n'emploie pas le passé ; un second toast confirme après suppression.

**A08 — « ▶ Generate selection » lance un second pipeline sur un job en cours, et le toast ment** · A+D · **P1**
- Cité : `server.py:415-430` (`generate()` : sortie silencieuse si `status == "running"`), `server.py:1815-1831` (`doGenerate` affiche « Generation started… » sans lire la réponse), `server.py:442-455` (`resume()` : un job `paused` n'est pas protégé), `server.py:1597-1622` (`updateDetail` affiche le panneau de génération dès que `has_tree && data_present`).
- Preuve : **Reproduit** (serveur instrumenté, job `delay=2`). (a) `POST /generate` pendant un `scan` → `{"ok":true}
  immédiat, aucun second processus, le job termine `scanned` **sans aucune sortie** ; (b) `pause` (pid en état `T`)
  puis `POST /generate` → `{"ok":true}` et un **second** `run.py` exécute l'étape 5 jusqu'au bout, ce qui passe le job
  à `done` **alors que le processus suspendu existe toujours**.
- Constat : (a) en cours d'exécution, le clic ne fait rien mais l'interface affiche « Generation started… » et écrase le terminal ; (b) en pause, un second pipeline écrit dans le même `out_dir` pendant que le premier est suspendu en pleine écriture — la reprise (`SIGCONT`) reprendra l'écriture dans un dossier que l'autre vient de nettoyer.
- Suggestion : refuser côté API avec un code d'erreur explicite (`409` + `{"error": "Job is running"}`), ne pas afficher le panneau pendant `running`/`paused`, et n'afficher le toast de succès qu'après vérification du statut.
- Régression : Aucune — les états permis (`scanned`, `done`, `stopped`, `error`) restent identiques.
- Vérification : générer pendant un run → toast d'erreur, aucun second processus (`ps`), fichiers intacts.

**A09 — « Re-render output » est masqué sauf si PDF est coché** · A+C · **P2**
- Cité : `server.py:1376-1377` (`f-rerender` porte la classe `pdf-opt`), `server.py:1050-1053` (`togglePdfOpts` masque `.pdf-opt`), `scripts/run.py:190-193` (`rerender` supprime `html/`, `pdf/`, `flat/`, `out/`).
- Preuve : Déduit (source) + Observé (le formulaire rend `display:none` sur `.pdf-opt` quand `pdf` est décoché).
- Constat : la seule action qui force une ré-extraction HTML disparaît pour un job `.md`/`.txt` — or c'est exactement le remède aux extractions partielles (D44) et aux rendus obsolètes.
- Suggestion : sortir `rerender` du bloc PDF et le placer à côté de « New full dump », libellé « Re-render HTML and outputs ».
- Régression : Aucune — `RERENDER` est déjà transmis indépendamment du format (`server.py:484`).
- Vérification : format `Markdown` seul → la case « Re-render » est visible et son activation supprime `html/` avant ré-extraction.

**A10 — Impossible de demander un délai de 0 s** · A · **P3**
- Cité : `server.py:1396` (`delay: parseFloat(...) || 0.5`), `server.py:1321` idem dans `saveSettings`, champ `min="0"` (`server.py:1362`, `1280`).
- Preuve : Déduit (code) + Observé : `PATCH` avec `delay: 0` puis relecture → `0` conservé (la valeur passe par l'API), mais l'UI réécrit 0,5.
- Constat : la valeur 0 affichée dans le champ est silencieusement remplacée par 0,5 au moment d'enregistrer ; l'utilisateur ne comprend pas pourquoi son réglage ne « prend » pas.
- Suggestion : `const d = parseFloat(v); delay: Number.isFinite(d) ? d : 0.5` (même correctif pour `max_pdf`, `workers`, `cat_workers` qui utilisent `|| défaut`).
- Régression : Aucune — les valeurs non numériques retombent toujours sur le défaut.
- Vérification : saisir 0, enregistrer, relire le job : `delay` vaut 0.

**A12 — Aucune estimation avant un dump (durée, pages, volume)** · A · **P4**
- Cité : `server.py:1340-1386` (aucun compteur) ; README « 200+ pages = ~50 min » est la seule information.
- Preuve : Déduit.
- Constat : l'utilisateur lance une opération de plusieurs dizaines de minutes sans savoir ce qui l'attend ; aucune étape ne dit « 200 pages détectées, ~45 min ».
- Suggestion : après le dump, afficher la taille de l'XML et le nombre de pages extraites dans la carte Progress (`log_count`/parse des lignes), et une estimation `pages × 0,5 s` avant l'extraction.
- Régression : Aucune — affichage additionnel.
- Vérification : le détail d'un job affiche « 8 pages, ~4 s d'extraction » avant/pendant l'étape 2.

**A13 — Les seuls indicateurs de progression sont des lignes de log brutes** · A · **P3**
- Cité : `server.py:1487-1496` (carte Log) ; aucune barre chiffrée ; `scripts/extract.py:259` imprime `[n] [api] Titre ...` mais l'UI n'en extrait rien.
- Preuve : Observé (log streamé) — aucune métadonnée de progression dans `meta()`.
- Constat : pour un wiki de 2 000 pages, il faut lire un terminal de 2 000 lignes pour estimer l'avancement.
- Suggestion : exposer un compteur `progress: {done, total}` dans `meta()` (compté depuis `html/`, `pdf/`), et une barre chiffrée dans la carte Progress.
- Régression : Aucune — champ additionnel ; le log reste inchangé.
- Vérification : pendant l'extraction, le détail affiche `137/2000 pages` sans lire le terminal.

**A14 — La page de réglages ne dit pas ce qui est global et ce qui est par job** · A · **P4**
- Cité : `server.py:1239-1302` (`buildSettingsPage`), `server.py:88-98` (`load_settings`) ; pas de « Reset to defaults ».
- Preuve : Déduit + Observé (« These values pre-fill every new job » en l.1251 seulement).
- Constat : `notebooklm_max_words`, `cat_workers`, `max_pdf` n'existent que dans les réglages : impossible de les ajuster pour un job donné, alors que `max_files` existe aux deux endroits.
- Suggestion : un seul endroit pour les valeurs par job (formulaire) et un bandeau « hérité des réglages » ; ajouter un bouton « Restore defaults » qui appelle `PUT /api/settings` avec `DEFAULTS`.
- Régression : Aucune — `DEFAULTS` reste la source.
- Vérification : le formulaire d'un job permet de changer `max_words` ; « Restore defaults » remet 50/500000/4.

**A15 — Ouvrir les réglages fait perdre le job sélectionné** · A · **P3**
- Cité : `server.py:1231-1237` : `openSettings()` met `selectedId = null` ; `closeSettings()` appelle `showEmpty()`.
- Preuve : Déduit (code).
- Constat : après un aller-retour dans les réglages, il faut re-cliquer le job ; le terminal et la sélection de catégories doivent être rechargés.
- Suggestion : mémoriser `selectedId` avant d'ouvrir les réglages et restaurer la vue au retour.
- Régression : Aucune — `selectJob(id)` réutilise le chemin existant.
- Vérification : ouvrir/fermer les réglages conserve le job et son panneau de sélection.

**A17 — La carte « Storage » reste périmée après une purge faite ailleurs** · A · **P4**
- Cité : `server.py:1849-1865` (`loadStorage`) : rendu figé jusqu'au prochain clic ; `server.py:1867-1876` (`purge`) recharge la carte, mais une purge déclenchée dans un autre onglet ne la met pas à jour.
- Preuve : Déduit.
- Constat : les chiffres affichés peuvent décrire un état de disque qui n'existe plus.
- Suggestion : recharger les chiffres dans `updateDetail` quand `data_present` change (ou bouton « Actualiser »).
- Régression : Aucune — 1 requête `/disk` supplémentaire seulement sur changement d'état.
- Vérification : purger depuis un second onglet → la carte du premier se met à jour au sondage suivant.

**A18 — Le README documente des boutons qui n'existent pas** · A+C · **P3**
- Cité : `README.md:116` (« ▶ Run : starts a pending job ») et `:120` (« ↩ Restart ») ; `server.py:1518-1527` (`buildActions`) ne rend que Pause/Stop/Resume, et `server.py:1538-1547` offre « Generate all »/« Generate selection ».
- Preuve : Observé (aucune trace de « Run »/« Restart » dans `_HTML`) + Déduit (aucun route `/run` ou `/restart` : `grep`).
- Constat : un utilisateur qui suit le README cherche un bouton inexistant, et un job `pending` n'a aucun bouton d'action dans la carte Actions (il faut passer par « Reconfigure »).
- Suggestion : soit implémenter les deux boutons sur les routes existantes (`/start`, `/resume`), soit corriger le README pour décrire la réalité.
- Régression : Aucune — la route `/start` existe déjà.
- Vérification : README et interface listent le même jeu d'actions.

---

## Axe B — Regard visuel et finition (18 constats)

Mesures : `Contrast = (L1+0,05)/(L2+0,05)` calculé sur les couleurs littérales de
`server.py:795-960` (script de calcul hors dépôt, 3 exécutions identiques).
Seuils WCAG 2.1 AA : 4,5:1 (texte courant), 3:1 (grand texte ≥ 18,66 px gras /
24 px, et composants non textuels).

**B01 — Texte secondaire sous 4,5:1 sur les lignes survolées** · B · **P2**
- Cité : `server.py:798` (`--muted:#7d8590`), `server.py:818` (`.job-item:hover` sur `--surface2:#21262d`), `server.py:824` (`.job-meta`), `server.py:943` (`.tree-cnt`) ; idem `.tree-row:hover` (l.938).
- Preuve : Mesuré — 4,08:1 (11,2 px, texte courant) ; 4,64:1 sur `--surface`, 5,07:1 sur `--bg`.
- Constat : au survol d'une ligne, le texte secondaire (statut, date, compteurs) passe sous le seuil de lisibilité, précisément quand l'utilisateur s'y intéresse.
- Suggestion : éclaircir `--muted` à `#98a1ab` (≈ 6,0:1 sur `--surface2`), ou ne pas changer le fond des lignes au survol et utiliser un liseré `--accent`.
- Régression : Aucune — variable unique (`--muted`) consommée par 20 règles ; vérifier par calcul que les nouveaux couples restent ≥ 4,5:1 sur `--bg`, `--surface`, `--surface2`, `--term`.
- Vérification : recalcul des 31 couples ; plus aucun couple texte courant < 4,5:1.

**B02 — Texte « dim » du terminal à 3,58:1** · B · **P2**
- Cité : `server.py:914` (`#terminal .l-dim { color:#666 }`), fond `--term:#010409`.
- Preuve : Mesuré — 3,58:1.
- Constat : les lignes de log volontairement atténuées (pause, stop, nettoyage) sont parmi les plus difficiles à lire ; or ce sont des actions de l'utilisateur.
- Suggestion : `#8b949e` (≈ 6,1:1) pour `.l-dim`.
- Régression : Aucune — une seule règle.
- Vérification : mesure ≥ 4,5:1.

**B03 — Placeholder à 2,84:1** · B · **P3**
- Cité : `server.py:864` (`input::placeholder { color: var(--muted); opacity:.6 }`).
- Preuve : Mesuré — 2,84:1 (opacité 0,6 appliquée à `#7d8590` sur `#0d1117`).
- Constat : l'indication « Paste any URL from the wiki » est presque illisible ; c'est pourtant la seule consigne du champ principal.
- Suggestion : retirer l'opacité et utiliser `#8b949e` (≈ 5,7:1) ; garder un texte d'aide permanent sous le champ.
- Régression : Aucune.
- Vérification : mesure ≥ 4,5:1.

**B04 — Badge « Pending » à 4,08:1** · B · **P3**
- Cité : `server.py:845` (`.st-pending { background:#21262d; color:var(--muted) }`), `server.py:842` (10,88 px, majuscules).
- Preuve : Mesuré — 4,08:1.
- Constat : le statut du job, information principale du bandeau, est le moins lisible des sept badges.
- Suggestion : `color:#adbac7` (≈ 7,5:1) ou fond `#1c2128` + `--muted` éclairci (cf. B01).
- Régression : Aucune — ne touche que `.st-pending`.
- Vérification : les 7 badges ≥ 4,5:1.

**B05 — Boutons primaires et destructeurs sous 4,5:1** · B · **P2**
- Cité : `server.py:887` (`.btn-primary { background: var(--accent:#388bfd); color:#fff }`), `server.py:888` (`.btn-danger { background: var(--red:#f85149); color:#fff }`), `server.py:885` (13,6 px, gras).
- Preuve : Mesuré — 3,34:1 (blanc/accent) et 3,35:1 (blanc/rouge).
- Constat : tous les boutons d'action principaux (« Generate selection », « Save », « Delete selection », « Stop ») sont sous le seuil ; le libellé perd en netteté, en particulier sur écran à faible luminosité.
- Suggestion : texter en `#0d1117` sur accent (5,66:1) et sur rouge `#f85149` (6,13:1), ou assombrir les fonds (`#1f6feb` → 4,5:1 avec blanc ; `#b62324` pour danger).
- Régression : Aucune — classes `.btn-primary`/`.btn-danger` uniquement ; vérifier le contraste des états `:hover` (opacité .82, cf. B22).
- Vérification : recalcul ≥ 4,5:1 pour les deux paires.

**B06 — Les champs de saisie sont presque invisibles au repos** · B · **P2**
- Cité : `server.py:861` (`input { border: 1px solid var(--border:#30363d); background: var(--bg) }`), `server.py:870` (select).
- Preuve : Mesuré — bordure/fond 1,55:1 (< 3:1 exigé pour délimiter un composant).
- Constat : au repos, un champ se distingue à peine du fond ; le seul repère de focus est un changement de couleur de bordure (`#388bfd`, 5,66:1) sans halo ni épaisseur.
- Suggestion : bordure `#5b6570` (≈ 3,2:1) et `box-shadow: 0 0 0 3px #388bfd33` au focus ; garder `outline:none` uniquement avec cet indicateur.
- Régression : Aucune — deux règles ; à vérifier : les inputs du terminal de logs (aucun) et les selects des réglages.
- Vérification : mesure bordure/fond ≥ 3:1 ; focus visible sur fond et en niveaux de gris.

**B07 — Vingt-huit règles de texte sous 12 px** · B · **P2**
- Cité : `server.py:904` (`.step-lbl` 10,4 px), `:909` (`.btn-sm` 11,2 px), `:837` (`.card-title` 10,9 px), `:824` (`.job-meta` 11,2 px), `:939` (`.tree-toggle` 9,9 px), `:826/.940` (cases 14/13 px), `:938` (`.tree-cnt` 10,6 px), `:930` (`.detail-url` 12,8 px)…
- Preuve : Mesuré (extraction de toutes les `font-size` en rem → px, racine 16 px) : 0,6 / 0,62 / 0,65 / 0,66 / 0,68 / 0,7 / 0,72 / 0,73 / 0,76 / 0,78 rem.
- Constat : les informations de contexte (statuts, compteurs, libellés d'étapes, titres de cartes) sont en dessous de la taille confortable ; combiné à B01/B04, elles deviennent franchement difficiles à lire.
- Suggestion : plancher à 12 px (0,75 rem) pour le texte, 13 px pour le texte courant de l'interface, et 11 px minimum pour les seules mentions décoratives.
- Régression : Aucune — la mise en page est en `rem` et en `flex` ; vérifier que `.steps` (5 libellés) ne casse pas sur un écran de 320 px.
- Vérification : aucune `font-size` < 0,75 rem hors élément décoratif ; captures large/étroit à refaire.

**B08 — Le titre de chaque article est dupliqué dans les `.md` générés** · B+D · **P2**
- Cité : `scripts/export_categories.py:139-143` (`_render_md` préfixe `# {title}`) + `:227-228` (`body_html` conserve le `<h1>` de la page), `scripts/clean_html.py:34-38` (`body_html` ne retire pas le `h1`).
- Preuve : Observé — `Weapons.md` commence par `# A/B\n\n# A/B\n\nContent of A/B.` (fichier généré sur le faux wiki).
- Constat : chaque article débute par un titre en double ; dans un fichier de 40 articles, 40 titres dupliqués, ce qui fausse la table des matières construite par NotebookLM et double le bruit déjà visé par le nettoyage.
- Suggestion : dans `_render_md`, retirer le premier `<h1>` du corps (ou ne pas préfixer `# {title}` et conserver le `h1` existant) — une seule source pour le titre.
- Régression : Aucune — `.txt` utilise `ArticleParser` qui consomme déjà le `h1` comme titre (`export_categories.py:77-79`) ; vérifier que les pages sans `h1` gardent le titre de repli (`_ch.title_text`).
- Vérification : `head -1` d'un `.md` généré donne un seul titre ; un article sans `h1` conserve le titre dérivé du nom de fichier.

**B09 — Le pied « Categories: A | B » est conservé dans les exports texte** · B+D · **P2**
- Cité : `scripts/extract.py:203-216` (`wrap_html` injecte un `<div style="…">Categories: …</div>` sans classe), `scripts/clean_html.py:8-23` (`NOISE_SELECTORS` ne peut pas le cibler).
- Preuve : Observé — chaque article de `Pistols.md` finit par `Categories: Weapons | Pistols`.
- Constat : du bruit MediaWiki revient dans chaque article, et cette liste **varie d'un fichier de catégorie à l'autre** (elle reflète les catégories de la page, pas celles du fichier), ce qui désoriente.
- Suggestion : ajouter une classe (`class="catlinks-footer"`) au div dans `wrap_html` et l'ajouter à `NOISE_SELECTORS` (ou le supprimer à la source : l'information est déjà dans `categories.json`).
- Régression : Aucune — le `.txt` et le `.md` perdent une ligne informative redondante ; les PDF (`convert.py`) afficheront la même suppression, à vérifier sur une page réelle.
- Vérification : `grep -c "Categories:"` = 0 dans tous les `.md`/`.txt` générés.

**B10 — Aucune adaptation à la largeur : la barre latérale fixe de 270 px rend l'app inutilisable sur mobile** · B+E · **P2**
- Cité : `server.py:807` (`.sidebar { width:270px; flex-shrink:0 }`), `server.py:805` (`.app { height:100vh; overflow:hidden }`), `server.py:831` (`.detail { padding:1.5rem }`) ; `grep "@media"` = **0** occurrence.
- Preuve : Mesuré (0 `@media` dans toute la feuille de style) + Déduit (à 375 px de large, le contenu principal reçoit 375-270-48 = 57 px).
- Constat : sur téléphone ou fenêtre étroite, les cartes (formulaire, arbre de catégories, terminal) sont écrasées ; le contenu principal ne peut pas être lu, et `overflow:hidden` empêche même le défilement horizontal global (chaque zone défile isolément).
- Suggestion : une `@media (max-width: 720px)` qui passe `.app` en colonne, transforme la barre latérale en tiroir (ou bandeau repliable) et donne 100 % de largeur au détail ; remplacer `100vh` par `100dvh`.
- Régression : Aucune — aucune règle actuelle ne cible les petits écrans, donc rien à casser ; vérifier les écrans large et 1 280 px après ajout.
- Vérification : capture à 375 px et 768 px : barre latérale repliée, cartes lisibles, aucun débordement horizontal.

**B11 — Animations non désactivables (pas de `prefers-reduced-motion`)** · B+E · **P3**
- Cité : `server.py:858` (`@keyframes pulse`, pastille `running`), `:1890`-ish (`.spin`), `:960` (`.toast` `slidein`), `.step-dot transition`.
- Preuve : Mesuré — 0 occurrence de `prefers-reduced-motion` ; 4 animations en boucle.
- Constat : une pastille qui pulse indéfiniment et un spinner permanent sont gênants pour les personnes sensibles au mouvement (et pour un job laissé ouvert des heures).
- Suggestion : `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important } }`.
- Régression : Aucune — l'indicateur de statut reste porté par la couleur et le texte.
- Vérification : avec l'émulation « reduce », aucune animation (inspection CSS).

**B12 — Les lignes de fichiers ressemblent à des boutons mais ne font rien** · B · **P3**
- Cité : `server.py:917-920` (`.file-row` avec fond, bordure, coins arrondis), `server.py:1563-1582` (`buildFiles`) : aucun `onclick`, aucun lien.
- Preuve : Déduit (HTML généré sans gestionnaire).
- Constat : dans une interface où chaque bloc bordé est actionnable, ces lignes invitent au clic ; rien ne se passe.
- Suggestion : soit un vrai lien (`<a href="/api/jobs/{id}/file?name=…">`, route à créer — cf. I01), soit un style non interactif (sans fond/bordure) ; ajouter un titre au survol.
- Régression : Aucune — purement visuel tant que I01 n'est pas fait.
- Vérification : les lignes de fichiers n'ont plus l'apparence d'un bouton, ou s'ouvrent au clic.

**B14 — L'URL du wiki est tronquée sans moyen de lire la fin** · B · **P4**
- Cité : `server.py:930` (`.detail-url { max-width:500px; text-overflow:ellipsis }`), `server.py:1478` (`<div class="detail-url">${esc(job.wiki_url)}</div>`), sans `title`.
- Preuve : Déduit.
- Constat : deux wikis partageant un long préfixe deviennent indiscernables, et l'URL exacte (qui détermine le dossier de sortie) n'est jamais lisible complètement.
- Suggestion : ajouter `title="${esc(job.wiki_url)}"` et `word-break: break-all` (ou 2 lignes max).
- Régression : Aucune.
- Vérification : le survol affiche l'URL entière.

**B15 — En-tête : deux contrôles de nature différente au même niveau visuel** · B · **P4**
- Cité : `server.py:975-977` : `⚙` (icône seule, 25 px), `Manage` (texte, même style `.icon-btn`), `+ New` (`.btn-new`, accent).
- Preuve : Observé (HTML servi).
- Constat : « Manage » est un mode persistant mais rien n'indique qu'il est actif hormis une bordure accent (`.icon-btn.on`, l.817) ; ⚙ et Manage ont la même apparence alors que l'un ouvre une vue et l'autre change le mode de la liste.
- Suggestion : donner un état explicite (« Manage ✓ » ou fond accent quand actif) et un libellé au bouton ⚙ (`aria-label="Settings"`, texte visible ou tooltip natif conservé).
- Régression : Aucune.
- Vérification : l'état « Manage actif » est perceptible sans survol.

**B17 — Vocabulaire d'icônes hétérogène** · B · **P4**
- Cité : emoji `🗑 ⚙ 📂 ▶ ⏸ ⏹ 🔍 💾 🧹 📕 📘 📄` et glyphes `▾ ▶ ✓` (`server.py:975-977, 1475, 1521-1525, 1533-1546, 1571-1573, 1862`).
- Preuve : Observé.
- Constat : trois familles graphiques cohabitent (emoji couleur, glyphes monochromes, texte) ; le rendu dépend de la police système et de l'OS, sans garantie d'alignement.
- Suggestion : choisir une famille (SVG inline, 16 px, `currentColor`) pour les actions de barre ; garder les emoji uniquement dans les textes de log.
- Régression : Aucune — purement visuel.
- Vérification : revue visuelle de la barre d'actions et de l'en-tête : une seule famille.

**B18 — Casse et formulation des libellés incohérentes** · B+C · **P4**
- Cité : `server.py:1360-1379` : « Namespaces », « Delay (s) », « Max pages / merged PDF », « PDF workers », « Max files (NotebookLM) », « Avoid duplicates (1 page = 1 file) », « Include images », « New full dump », « Re-render output », « Skip Internet Archive ».
- Preuve : Observé.
- Constat : quatre styles (nom + unité, groupe nominal, phrase, verbe) dans un même bloc de 10 champs ; la lecture est plus lente qu'avec une convention unique.
- Suggestion : convention « Nom + précision entre parenthèses » partout (« Delay (s) », « Max pages per PDF », « PDF workers », « Max files (NotebookLM) », « Skip Archive.org », « Force new dump »).
- Régression : Aucune — libellés seuls.
- Vérification : relecture du formulaire ; aucun libellé verbal.

**B21 — Thème unique, imposé** · B · **P3**
- Cité : `server.py:796-803` (`:root` en dur, aucun `prefers-color-scheme`), `grep` = 0 occurrence.
- Preuve : Mesuré.
- Constat : pas de mode clair ni de respect de la préférence système ; en environnement très éclairé, un thème sombre unique est un frein réel.
- Suggestion : soit déclarer le choix (`<meta name="color-scheme" content="dark">`) pour que le navigateur adapte les contrôles natifs, soit un thème clair via `@media (prefers-color-scheme: light)` sur les 11 variables.
- Régression : Aucune — les variables sont déjà centralisées.
- Vérification : `prefers-color-scheme: light` produite → variables basculées, contrastes recalculés ≥ 4,5:1.

**B22 — Le survol dégrade le contraste des lignes de job (et ne corrige pas celui des boutons)** · B · **P4**
- Cité : `server.py:891` (`.btn:hover:not(:disabled) { opacity:.82 }`), `server.py:818` (`.job-item:hover` → `--surface2`), `server.py:824` (`.job-meta`).
- Preuve : **Mesuré par calcul de composition** — `.job-meta` passe de 5,07:1 (`--bg`) et 4,64:1 (`--surface`) à **4,08:1** au survol (fond `--surface2`). Pour les boutons, l'opacité 0,82 composée sur `#161b22` donne `#3277d6` / texte `#dae7f8` = **3,53:1** : le survol améliore très légèrement le ratio (3,34 → 3,53) mais reste sous le seuil.
- Constat : l'état survolé — celui qui précède immédiatement le clic — est le moins lisible pour les lignes de job ; le correctif de B05 (couleur de fond) suffirait autrement.
- Suggestion : remplacer l'opacité des boutons par une variation de fond, et ne pas assombrir le fond des lignes au survol (liseré `--accent` à la place) ; corriger B01/B05 d'abord, puis vérifier les deux états.
- Régression : Aucune — deux sélecteurs ; le survol reste perceptible (liseré, `filter: brightness`).
- Vérification : recalcul des ratios au repos **et** au survol pour `.job-item`, `.btn-primary`, `.btn-danger` ; tous ≥ 4,5:1 ou ≥ 3:1 pour les composants.

---

## Axe C — Cohérence et parité (13 constats)

**C01 — « Max words per file » n'existe pas au niveau du job** · C · **P2**
- Cité : `server.py:1260-1261` (champ dans les réglages seulement), `server.py:1389-1409` (`collectParams` hérite de `base` sans exposer le champ), `server.py:66` (`notebooklm_max_words` dans `DEFAULTS`).
- Preuve : Déduit (le formulaire ne contient aucun `f-maxwords`) + Observé (le panneau d'aperçu annonce des splits sans permettre de changer la limite).
- Constat : la limite qui détermine les découpages (et donc le nombre de fichiers) ne peut pas être ajustée pour un wiki donné sans changer tous les jobs futurs.
- Suggestion : ajouter le champ au formulaire du job (à côté de « Max files ») ; garder le réglage global comme valeur par défaut.
- Régression : Aucune — `collectParams` transmet déjà `base.notebooklm_max_words` ; il suffit de le surcharger s'il est présent.
- Vérification : modifier la limite dans le formulaire d'un job, générer, constater les découpages correspondants.

**C02 — Le plan « Plus » (100 sources) et `max_files` par défaut (50) se contredisent** · C · **P2**
- Cité : `server.py:76-81` (`plus: 100`), `server.py:68` (`max_files: 50`), `server.py:88` (`notebooklm_plan: "plus"`), `server.py:1307-1310` (`onMaxFilesInput` force le plan à `custom`/`free` dès qu'on touche le nombre).
- Preuve : Observé (`GET /api/settings` → `max_files:50`, `notebooklm_plan:"plus"`) + Déduit (l'input reclassifie le plan).
- Constat : l'écran affiche simultanément « Plus — 100 sources » et « 50 fichiers » ; changer le nombre bascule silencieusement le plan en « Free », donc l'utilisateur ne sait plus quel plan est appliqué.
- Suggestion : dériver `max_files` du plan à l'ouverture et n'écrire le plan qu'à la main ; ou supprimer le sélecteur de plan et ne garder que le nombre (une seule source de vérité).
- Régression : Aucune — `max_files` reste la valeur réellement consommée par le pipeline.
- Vérification : ouverture des réglages → plan et nombre cohérents ; changer le nombre ne réécrit pas le plan sans le dire.

**C03 — La table des plans contredit la documentation interne** · C · **P3**
- Cité : `server.py:76-81` (`plus 100`, `pro 300`, `ultra 600`), `server.py:1266` (« Free 50 · Plus 100 · Pro 300 · Ultra 600 »), `README.md` (pas de table), `PLAN.md` §B.1 (« 50 on free, 300 on Plus »).
- Preuve : Observé (deux textes du dépôt qui divergent sur la valeur de « Plus »).
- Constat : impossible de savoir si « Plus » vaut 100 ou 300 sources ; la prévision du nombre de fichiers dépend de ce chiffre.
- Suggestion : une seule source (constante `NOTEBOOKLM_PLANS`) + une note datée dans le README renvoyant à la page officielle des limites.
- Régression : Aucune — affichage.
- Vérification : une seule occurrence des nombres 50/100/300/600 hors de la constante.

**C04 — Le vocabulaire de l'interface diverge de celui du README** · C · **P2**
- Cité : « Re-render output » (`server.py:1377`) vs « Regenerate rendering » (`README.md:88`) ; « New full dump » (l.1375) vs « New dump » (`README.md:141`) ; « Max files (NotebookLM) » (l.1368) vs « Max file count » (`PLAN.md`) vs « Max files (sources) per notebook » (l.1258) ; « Do everything at once » (l.1383) vs « ▶ Run » (`README.md:116`).
- Preuve : Observé (les quatre formulations existent dans le dépôt).
- Constat : un utilisateur qui suit la doc ne retrouve pas les mêmes mots dans l'écran ; les réglages et le formulaire emploient deux libellés pour le même paramètre.
- Suggestion : un glossaire unique (README + interface) : `Scan`, `Generate`, `Force new dump`, `Re-render`, `Max files`, `Max words per file`.
- Régression : Aucune.
- Vérification : les mêmes 6 termes apparaissent à l'identique dans le README et dans `_HTML`.

**C05 — La déduplication par défaut contredit la promesse du README** · C · **P2**
- Cité : `server.py:71` (`dedup: True`), `README.md:74` (« Pages in multiple categories: present in every relevant file (intended for NotebookLM) »), `scripts/pack_files.py:31-54`.
- Preuve : Observé — sans sélection, `DEDUP=true` réduit 8 affectations à 6 (`run2.log` : `Deduplication: 8 -> 6`), donc une page n'apparaît que dans un fichier.
- Constat : la documentation décrit l'ancien comportement ; l'utilisateur qui compte sur la présence d'une page dans plusieurs fichiers (le cas d'usage NotebookLM cité) obtient des fichiers incomplets sans avertissement.
- Suggestion : trancher et l'écrire : soit `dedup: False` par défaut, soit mettre à jour le README et l'infobulle (« 1 page = 1 fichier, pour économiser le quota »).
- Régression : Changer le défaut modifie le volume produit (plus de fichiers, contenus dupliqués) — **régression assumée** à valider humainement, alternative : garder `True` et corriger le README (aucune régression).
- Vérification : le README et le comportement donnent le même résultat sur le faux wiki (6 vs 8 affectations).

**C07 — Trois canaux de retour d'erreur pour la même nature de problème** · C · **P2**
- Cité : toasts (`server.py:1061-1082`, `showToast`), lignes de log `l-err` (`server.py:996-1001`), et silence total : `pause` sur job inexistant (`server.py:431-440` renvoie `ok:true`), `generate` en cours (`server.py:415-430`), `delete` d'un job inconnu (ignoré par `bulk_delete`, `server.py:365-374`).
- Preuve : Déduit (trois chemins distincts) + Observé (les 3 cas renvoient 200 sans message).
- Constat : l'utilisateur ne peut pas savoir si son action a échoué ; certaines erreurs ne laissent aucune trace dans l'UI.
- Suggestion : convention unique : toute route renvoie `{ok:false, error}` avec un code HTTP adéquat, et le client affiche un toast d'erreur dès que `ok` est faux.
- Régression : Aucune — les appelants JS vérifient déjà `r.error` pour `purge` (l.1870) ; les autres routes doivent être alignées.
- Vérification : pause/generate/delete sur un job non éligible → toast d'erreur visible, aucun succès affiché.

**C08 — Deux représentations différentes de l'occupation disque** · C · **P4**
- Cité : `server.py:1131` (taille dans la liste, mode Manage), `server.py:1849-1865` (carte Storage détaillée) ; les deux appellent `/disk` séparément, sans cache partagé au-delà de `sizeCache`.
- Preuve : Déduit.
- Constat : deux sources pour la même information, avec des granularités différentes et des instants de mesure différents ; l'utilisateur peut voir 2 valeurs pour un même job.
- Suggestion : une seule carte (ou un même endpoint renvoyant les deux niveaux) et un cache invalidé sur changement d'état.
- Régression : Aucune.
- Vérification : la taille affichée dans la liste et dans la carte converge après une purge.

**C09 — « Sort: size » est un état, présenté comme une action** · C · **P3**
- Cité : `server.py:1536` (`<button … id="sort-btn">Sort: size</button>`), `server.py:1745-1752` (`toggleSort`).
- Preuve : Déduit (le libellé indique l'état courant, sans `aria-pressed`).
- Constat : au même niveau que « All », « None », « Collapse » (actions instantanées), ce bouton bascule un mode persistant ; rien ne distingue les deux familles, et l'état n'est pas annoncé aux lecteurs d'écran.
- Suggestion : le rendre explicitement à deux états (`aria-pressed`, libellé « Trier par : taille ▾ ») ou le sortir de la barre d'actions.
- Régression : Aucune.
- Vérification : l'état du tri est annoncé (attribut présent) et visuellement distinct des actions.

**C11 — Les champs PDF masqués restent collectés (valeurs fantômes)** · C · **P4**
- Cité : `server.py:1389-1409` (`collectParams` lit `f-maxpdf`/`f-workers` même quand `display:none`), `server.py:1050-1053`.
- Preuve : Déduit.
- Constat : un job `.md` conserve les valeurs PDF précédentes sans que l'utilisateur les voie, et les transmet au pipeline ; à la réactivation du PDF, des valeurs inattendues réapparaissent.
- Suggestion : conserver cette conception (utile pour la réversibilité) mais afficher un résumé « PDF : 4 workers, 500 pages/fichier » quand la case est décochée.
- Régression : Aucune.
- Vérification : décocher PDF, enregistrer, recocher : les valeurs sont celles affichées dans le résumé.

**C14 — Les pages sans catégorie sont invisibles dans l'arbre et disparaissent dès qu'une sélection existe** · C+D · **P2**
- Cité : `scripts/build_categories.py:167-187` (l'arbre ne contient que les catégories), `scripts/run.py:370-379` (`add_divers=False` dès qu'un fichier de sélection existe), `scripts/export_categories.py:36-38`.
- Preuve : Reproduit — `selection:["Weapons"]` → sortie = `Weapons.md/.txt` uniquement, alors que la page « Empty » (non catégorisée) existe ; sans sélection, `Misc.md/.txt` est produite (`run2.log`).
- Constat : l'arbre affiche « 4 / 4 catégories sélectionnées » alors que 1 page sur 7 n'est dans aucune et sera exclue ; aucune indication, aucun moyen de la sélectionner ou de la voir.
- Suggestion : ajouter un nœud racine virtuel « Misc (pages sans catégorie) » dans `category_tree.json` et le traiter comme une catégorie sélectionnable ; à défaut, avertir explicitement dans le panneau (« N pages non catégorisées seront omises »).
- Régression : Aucune — les vrais noms de catégories ne changent pas ; vérifier `MISC_CATEGORY` (env) et les tests `test_export_categories.py::test_misc_category_env_override`.
- Vérification : l'arbre montre un nœud Misc avec le bon compte ; générer avec une sélection produit aussi `Misc.*` si le nœud est coché.

**C15 — On peut filtrer 3 600 catégories mais pas 40 jobs** · C · **P4**
- Cité : `server.py:1537` (filtre de l'arbre), `server.py:1109-1150` (`renderSidebar` : aucune recherche, aucun tri).
- Preuve : Déduit.
- Constat : la liste des jobs, qui n'a aucune borne, est la seule surface sans filtre ni tri alors que l'arbre en a un ; au-delà de ~15 jobs, retrouver un archivage devient un travail de lecture.
- Suggestion : réutiliser la même barre (recherche + tri par date/statut) au-dessus de `#job-list`.
- Régression : Aucune.
- Vérification : taper 3 lettres dans la liste réduit les jobs affichés.

**C16 — L'interface impose des bornes que l'API n'applique pas** · C+H · **P2**
- Cité : bornes HTML `min/max` (`server.py:1259, 1365-1369, 1282, 1292-1294`) vs `save_settings` (`server.py:100-107`, aucun contrôle) et `create_job` (`server.py:587-598`, aucun contrôle).
- Preuve : Reproduit — `PUT /api/settings {"max_files":"abc"}` → 200 et valeur stockée ; `POST /api/jobs` avec une URL non-URL → 200.
- Constat : la seule validation est côté client ; tout appel direct (script, onglet, fichier `settings.json` édité) crée un état invalide que l'application ne sait pas gérer (cf. D08).
- Suggestion : valider et normaliser côté serveur (types, bornes, énumérations) dans une fonction unique appelée par `create_job`, `patch_job`, `put_settings` ; renvoyer 400 avec un message champ par champ.
- Régression : Aucune — les valeurs actuellement valides le restent ; vérifier les tests `test_server_config.py`.
- Vérification : `max_files:"abc"` → 400 ; `max_files:601` → 400 ; valeurs valides inchangées.

---

## Axe D — Fonctionnel et bugs (26 constats)

**D01 — Sans API, aucun fichier par catégorie n'est jamais écrit (code mort après `return 1`)** · D · **P0**
- Cité : `scripts/run.py:339-356`. La branche `elif categories_file.exists():` (mode texte, API absente) calcule `groups` puis **aucune écriture ne suit** : `cat_groups.write_text(...)` (l.352-356) et `log(f"  {len(groups)} categories")` sont **indentés dans la branche `else`** (l.346-351), juste après `return 1` (l.351) → inatteignables.
- Preuve : **Reproduit**. Faux wiki, `dump/config.json` sans `api`, 7 pages HTML, `categories.json` présent : `run3.log` affiche `⚠ No API -- direct grouping without hierarchy (text mode)`, puis `category_groups.json` n'existe pas, `export_categories.py` prévient `⚠ not found -- everything goes into 'Misc'`, et le pipeline conclut `✓ PIPELINE COMPLETE` avec **un seul fichier `Misc.md` (759 o)** et un code de sortie 0.
- Constat : sur tout wiki dont l'API `action=parse` n'est pas joignable (le mode texte est justement le repli documenté), l'utilisateur reçoit un unique fichier fourre-tout au lieu d'un fichier par catégorie, sans erreur, et le job est marqué `done`. C'est la promesse centrale du produit qui n'est pas tenue, en silence.
- Suggestion : déplacer l'écriture après le `if/elif/else` (sérialiser `groups` dans `cat_groups` quel que soit le mode), et faire échouer l'étape si `cat_groups` n'existe pas au moment de l'étape 5 (fail fast). Réutiliser `cat_groups.write_text(json.dumps({k: sorted(v) …}))` déjà présent.
- Régression : Aucune — `groups` n'a aucun autre consommateur ; `export_categories.py` lit le même format `{cat: [stem]}`; vérifier les deux tests `tests/test_run_pipeline.py` (chemin `generate`) et en ajouter un pour le mode texte.
- Vérification : nouveau test d'intégration « pas d'API + `categories.json` » → `category_groups.json` existe, un fichier par catégorie, aucun `Misc` fourre-tout.

**D02 — Deux jobs sur le même wiki partagent le même dossier de sortie : générer ou supprimer l'un détruit les fichiers de l'autre** · D+H · **P0**
- Cité : `scripts/run.py:163-164` (`out_dir = data_dir/"output"/slug`), `scripts/run.py:395-398` (`shutil.rmtree(out_dir)` au début de l'étape 5), `server.py:176` (`merged_dir()` = même chemin), `server.py:349-363` (`delete()` : `shutil.rmtree(job.merged_dir())`), `server.py:236-247` (`_files_meta` liste ce dossier).
- Preuve : **Reproduit, mesuré**. Job A génère la sélection `Weapons` → `Weapons.md/.txt`. Job B (même URL) génère `Pistols` → `output/127.0.0.1/` ne contient plus que `Pistols.md`; l'API renvoie pour A et B la même liste `[Pistols.md]` alors que A est toujours `done`. Puis `bulk_delete` de B : `output/127.0.0.1/` **disparaît**, et A (`done`) renvoie `files: []`.
- Constat : perte de données silencieuse et croisée. Deux archivages du même wiki (cas normal : un en `.md`, un en PDF ; ou deux sélections différentes) s'écrasent mutuellement ; supprimer un job efface la sortie d'un autre, sans que son statut change.
- Suggestion : un dossier de sortie par job (`data/output/{slug}/{job_id}/`), ou à défaut un refus explicite (« un autre job utilise déjà ce dossier ») ; `delete()` ne doit supprimer que le sous-dossier du job. Le nom de l'archive reste `{slug}` seul si l'on veut un chemin stable, mais jamais partagé.
- Régression : **Assumée et à valider** — le chemin affiché (`out_path`, README « `data/output/{wiki}/` ») gagne un niveau. Atténuation : conserver `data/output/{slug}` comme raccourci/alias (copie ou lien) et l'indiquer dans le README. Les tests `test_server_config.py::test_host_path_and_human_size` ne dépendent pas du niveau.
- Vérification : deux jobs du même wiki génèrent deux jeux de fichiers ; supprimer l'un laisse l'autre intact ; `GET /api/jobs` renvoie les fichiers corrects pour chacun.

**D03 — Deux titres qui se normalisent pareil écrasent silencieusement une page** · D · **P0**
- Cité : `scripts/wiki_names.py:20-23` (`page_stem` : `re.sub(r"[^\w\s\-]", "_", title)[:120]`), `scripts/extract.py:231-253` (`outfile = DEST / f"{safe}.html"` ; si `outfile.exists()` → compte la page comme « resumed » et **ne l'écrit pas**).
- Preuve : **Reproduit**. Faux wiki contenant `A/B` et `A:B` : `extract.py` imprime `[3] [api] A/B` puis saute à `[5]` (la page `A:B` est comptée « 1 resumed »), `html/` ne contient que `A_B.html`, `categories.json` n'a qu'une entrée `A_B`, et le log conclut `✓ 7 new … + 1 resumed` — un succès. La page `A:B` est perdue, sans avertissement.
- Constat : toute paire de titres ne différant que par un caractère remplacé (`A/B`↔`A:B`, `C++`↔`C--`, `(film)`↔`_film_`) ou toute paire tronquée à 120 caractères perd une page ; l'archive est incomplète et le rapport de fin affirme le contraire. Sur un wiki de 2 000 pages, ce type de collision est courant (titres avec `/`, `:`, `?`).
- Suggestion : rendre `page_stem` injectif — conserver la correspondance `stem → titre` dans un index et, en cas de collision, suffixer par un hachage court déterministe (`f"{safe[:110]}-{sha1(title)[:6]}"`) ; ne jamais traiter « fichier déjà présent » comme « page déjà extraite » sans vérifier le titre dans `categories.json`.
- Régression : Aucune — les noms déjà uniques ne changent pas (le suffixe n'apparaît qu'en cas de collision) ; vérifier `tests/test_wiki_names.py::test_page_stem_sanitizes_and_truncates` (à adapter si le contrat de fonction change) et la reprise (le mapping `stem→title` doit permette de retrouver les fichiers existants).
- Vérification : faux wiki avec `A/B` et `A:B` → 8 pages HTML, 8 entrées dans `categories.json`, deux fichiers distincts, aucune ligne « resumed » injustifiée.

**D04 — La sortie précédente est effacée avant toute validation du format demandé** · D · **P1**
- Cité : `scripts/run.py:150-156` (`formats_list` accepte n'importe quelle chaîne, y compris `none`), `scripts/run.py:394-398` (`rmtree(out_dir)` en tête de l'étape 5), `scripts/export_categories.py:161-165` (rejet des formats inconnus **après** le nettoyage).
- Preuve : **Reproduit**. `POST /api/jobs/{id}/generate {"formats":"none"}` → log `Cleaning previous output: …`, puis `✗ Unknown format(s): none`, job en `error`, dossier de sortie **vide** (les fichiers valides de la génération précédente ont disparu).
- Constat : une valeur de format invalide (ou un fichier `selection.json` corrompu, ou un `EXPORT_FORMATS` mal saisi) détruit une sortie valide avant de découvrir qu'elle ne peut pas être remplacée.
- Suggestion : valider `export_formats` **avant** l'étape 5 (ensemble autorisé `{pdf,md,txt,none}` avec `none` = erreur explicite) et écrire la nouvelle sortie dans un dossier temporaire puis renommer (`os.replace`) une fois le succès constaté.
- Régression : Aucune — le dossier final reste identique en cas de succès ; `merge_pdf.py`/`export_categories.py` écrivent déjà dans `out_dir` fourni en argument, donc un chemin temporaire suffit.
- Vérification : générer avec `formats:"none"` → 400 côté API, sortie précédente intacte ; générer avec un format valide → sortie remplacée.

**D05 — L'option « Namespaces » n'a aucun effet sur l'extraction (seul l'espace 0 est conservé)** · D+C · **P1**
- Cité : `scripts/extract.py:32-33` (`KEEP_NS = {"0"}`), `scripts/run.py:231-238` (le paramètre `--namespaces` est transmis au dump), `README.md:135` (« 0=articles, 10=templates, 14=categories »), `server.py:1360` (champ éditable).
- Preuve : Déduit (constante figée, jamais alimentée par `NAMESPACES`) ; cohérent avec `run.py:287-290` qui prévoit le cas « extraction produced 0 HTML pages ».
- Constat : un utilisateur qui met `0,10,14` télécharge bien ces espaces mais n'obtient que les articles ; s'il ne met que `10`, l'extraction produit 0 page et le pipeline échoue avec « wrong namespaces? » alors que le dump est correct.
- Suggestion : dériver `KEEP_NS` de la variable d'environnement `NAMESPACES` (déjà transmise par `server.py:481`) et l'utiliser aussi pour `--namespaces` du dump ; à défaut, retirer le champ de l'interface et documenter « espace 0 uniquement ».
- Régression : Aucune — `NAMESPACES=0` (défaut) donne exactement le comportement actuel ; vérifier `tests/test_extract_fallback.py`.
- Vérification : `NAMESPACES=0,14` → les pages de catégorie de l'espace 14 apparaissent dans `html/` ; `NAMESPACES=0` inchangé.

**D06 — Un seul timeout d'API fait échouer la totalité de l'analyse des catégories, sans réessai** · D+F · **P1**
- Cité : `scripts/build_categories.py:59-76` (`fetch_category` : un `except` → erreur retournée, aucun retry ni backoff), `:84-107` (`pool.map` puis `sys.exit(1)` dès qu'une catégorie a échoué), `:28` (`CAT_WORKERS` par défaut 8).
- Preuve : **Reproduit** — `run1.log` : 3 catégories sur 4 en `Read timed out`, puis `✗ Category hierarchy scan failed: 3 categories could not be read` et l'étape 4 échoue (`exit 1`) après 20 s de blocage, alors que les 4 catégories avaient répondu avant.
- Constat : sur un wiki lent ou limité en débit, 8 requêtes parallèles provoquent des timeouts ; un seul suffit à jeter les N catégories déjà lues et à faire échouer un scan de plusieurs minutes (le dump et l'extraction, eux, sont conservés mais le job est `error`).
- Suggestion : réessayer chaque catégorie (2-3 tentatives, backoff exponentiel, `timeout` paramétrable) en réutilisant le motif `--retries 5` déjà passé à wikiteam3 ; ne faire échouer l'étape qu'après épuisement des tentatives, en conservant la liste des catégories en échec dans le log final.
- Régression : Aucune — le « fail fast » reste effectif après les tentatives ; `tests/test_build_categories.py::test_api_error_aborts_the_scan` doit être adapté pour vérifier l'abandon **après** N tentatives.
- Vérification : faux wiki qui échoue une fois sur deux → scan réussi, log mentionnant les tentatives.

**D07 — L'aperçu annonce un nombre de fichiers différent du résultat réel (les pages non catégorisées sont ignorées)** · D · **P1**
- Cité : `server.py:530-579` (`_packing_preview` ne compte que les groupes de `category_groups.json`), `scripts/export_categories.py:189-193` / `scripts/merge_pdf.py:64-68` (ajout de `MISC_CATEGORY` **au moment de l'écriture seulement**), `server.py:1780-1795` (`updateGenInfo` affiche « ≈ N file(s) »).
- Preuve : **Mesuré** — même job, même sélection : `POST /preview_packing` → `{"file_count": 4}` ; fichiers réellement produits : 5 (`BigTable`, `Misc`, `Pistols`, `Rifles`, `Weapons`).
- Constat : l'aperçu, présenté comme « same logic as generation » (`server.py:52-56`), sous-estime systématiquement de 1 fichier dès qu'il existe des pages non catégorisées — et ne signale pas qu'elles seront ajoutées, alors qu'elles disparaissent dès qu'une sélection est enregistrée (C14).
- Suggestion : intégrer `Misc` dans le calcul de l'aperçu (même règle `ADD_DIVERS` que la génération, et inclure le nœud virtuel C14) de sorte que l'aperçu et la génération partagent **une seule** fonction de regroupement ; afficher aussi le nombre de pages non catégorisées.
- Régression : Aucune — `pack_files.pack()` reste la source ; on lui passe les groupes complétés de `Misc` comme le font déjà les exporteurs.
- Vérification : test comparant `preview.file_count` au nombre de fichiers produits sur le faux wiki (4 avant, 5 après — l'aperçu doit annoncer 5).

**D08 — Aucune validation des paramètres : valeurs invalides ⇒ erreur 500 et plantage du pipeline** · D+H · **P1**
- Cité : `server.py:100-107` (`save_settings` : recopie sans contrôle), `server.py:587-598` (`create_job`), `server.py:703-713` (`preview_packing` : `int(body.get("max_files") or 0)`), `scripts/run.py:380` (`int(max_files)`), `scripts/run.py:380-389`.
- Preuve : **Reproduit** — `PUT /api/settings {"max_files":"abc"}` → `200` et `"max_files":"abc"` **persisté dans `settings.json`** ; `POST /preview_packing {"max_files":"abc"}` → **500** ; `MAX_FILES=abc python run.py` → `ValueError: invalid literal for int() with base 10: 'abc'` avec trace Python complète dans le log du job. Un corps JSON malformé sur `POST /api/jobs` renvoie aussi **500**.
- Constat : une valeur hors type empoisonne durablement l'application (elle survit au redémarrage et se propage à tous les nouveaux jobs) ; l'utilisateur voit `500 Internal Server Error` ou une trace brute dans le terminal, exactement ce que la règle « jamais de trace brute à l'écran » interdit.
- Suggestion : un validateur unique (`_normalize_params`) appelé par `create_job`, `patch_job`, `put_settings`, `generate` : types (`int/float/bool/str`), bornes (`max_files 0-600`, `delay 0-60`, `workers 1-16`, `cat_workers 1-32`, `max_pdf 1-2000`, `max_words ≥ 10 000`), énumération des formats ; réponse `400` avec le champ fautif. Côté `run.py`, lire les entiers via une fonction `env_int(name, default)` qui journalise et retombe sur le défaut.
- Régression : Aucune — toutes les valeurs aujourd'hui valides passent ; vérifier `tests/test_server_config.py` (les défauts issus de l'environnement doivent rester lus tels quels quand ils sont numériques).
- Vérification : `max_files:"abc"` → 400 et `settings.json` inchangé ; `MAX_FILES=abc` → message clair et repli sur 50 au lieu d'une trace.

**D10 — Les noms de fichiers de sortie sont tronqués à 80 caractères, sans contrôle de collision, et deviennent illisibles** · D+B · **P2**
- Cité : `scripts/wiki_names.py:26-31` (`cat_stem` : `[:80]`), `scripts/pack_files.py:137-157` (fusion gloutonne : `merged_name = f"{n1}+{n2}"`), `scripts/export_categories.py:227-228` et `scripts/merge_pdf.py:93-104` (écriture sans vérifier l'existence).
- Preuve : **Mesuré** — 3 998 catégories, `MAX_FILES=50` : les noms produits atteignent 800+ caractères, du type `Cat 00733 siupk+Cat 00477 uzxru+…+Cat 00186 znsvf` ; après `cat_stem`, ils sont coupés à 80 caractères (nom du fichier ≈ `Cat_00733_siupk+Cat_00477_uzxru+…`).
- Constat : l'utilisateur ne peut pas identifier le contenu d'un fichier depuis son nom, ni dans l'explorateur ni dans NotebookLM ; deux groupes différents dont les 80 premiers caractères coïncident s'écrasent mutuellement (aucun test d'existence, aucune erreur).
- Suggestion : nommer les groupes fusionnés par une règle courte et lisible (`Weapons (1-3/12)` ou le parent commun + index), et détecter les collisions de `cat_stem` avant écriture (suffixe déterministe + avertissement dans le log).
- Régression : Aucune — les noms des catégories non fusionnées restent identiques ; vérifier `tests/test_wiki_names.py` (contrat de `cat_stem`) et `tests/test_merge_pdf.py::test_split_parts_have_clean_names`.
- Vérification : sur 3 998 catégories, tous les noms de fichiers font < 60 caractères, sont distincts, et un rapport liste les groupes fusionnés.

**D14 — Les articles dont le HTML manque sont supprimés du fichier sans trace** · D · **P2**
- Cité : `scripts/export_categories.py:200-212` (`get_article` renvoie `None` si le fichier HTML n'existe pas), `:216` (`articles = [… if a]`), `:230` (log « (N articles) » sur le nombre filtré).
- Preuve : Déduit (code) ; cohérent avec D03 (une page absente n'apparaît nulle part).
- Constat : un fichier de catégorie peut contenir 39 articles sur 40 sans que rien ne le signale ; le compteur affiché est celui des survivants, donc l'écart est invisible.
- Suggestion : journaliser chaque stem manquant (`⚠ page absente: <stem>`) et faire échouer l'étape si le taux de manquants dépasse un seuil (ou si `category_groups.json` référence des stems inexistants, ce qui est le vrai symptôme de D03).
- Régression : Aucune — ajout de journalisation ; `tests/test_export_categories.py` ne dépend pas du silence.
- Vérification : supprimer un HTML et générer → le log liste la page manquante.

**D15 — Toutes les écritures JSON sont non atomiques et un `categories.json` corrompu est ignoré en silence** · D · **P2**
- Cité : `scripts/extract.py:42-47` (`try: json.loads(...) except: pass` puis reprise avec un dictionnaire vide), `:49-50` (`save_categories` → `write_text`), `scripts/build_categories.py:138-139`, `:186-187`, `scripts/pack_files.py:183`, `server.py:106` (`settings.json`), `server.py:306-313` (`jobs.json`), `server.py:418-424` (`selection.json`).
- Preuve : Déduit (aucun `os.replace`, aucun fichier temporaire) ; observé pour l'effet de bord (D16 : l'arrêt du serveur tue le pipeline en pleine écriture → `print` sur un tube fermé).
- Constat : une interruption pendant l'écriture (arrêt du serveur, coupure, Ctrl+C) laisse un JSON tronqué ; `extract.py` le réinitialise silencieusement (toutes les catégories déjà récupérées sont reperdues), `export_categories.py`/`merge_pdf.py` échouent avec « unreadable » et `jobs.json` perd toute la liste des jobs.
- Suggestion : écrire dans `<fichier>.tmp` puis `os.replace()` (3 lignes, une fonction partagée), et journaliser explicitement le cas « fichier illisible, réinitialisation » dans `extract.py` au lieu de `pass`.
- Régression : Aucune — sémantique identique, opération atomique ; vérifier les tests qui écrivent ces fichiers (`test_export_categories.py`, `test_merge_pdf.py`, `test_run_pipeline.py`).
- Vérification : test qui tronque `jobs.json`/`categories.json` en cours d'écriture simulée → reprise sans perte ; un JSON tronqué est signalé dans le log.

**D16 — Aucun arrêt propre : quitter le serveur laisse le pipeline tourner (ou le tue au milieu d'une écriture)** · D · **P2**
- Cité : `server.py:472-524` (`_run` : aucun enregistrement du processus pour un arrêt global), aucune fonction `@app.on_event("shutdown")` (ni `lifespan`) ; `server.py:1955-1957` (`uvicorn.run`).
- Preuve : Reproduit partiellement — après `SIGKILL` du serveur, le processus `run.py` disparaît en < 4 s (tube fermé → écriture suivante en erreur), ce qui interrompt l'étape en cours sans que rien ne le signale.
- Constat : fermer la fenêtre pendant un dump de 20 minutes tue l'enfant au hasard de son prochain `print` — pas d'arrêt ordonné, pas d'état « interrompu », et les fichiers écrits restent partiels (cf. D15).
- Suggestion : sur `shutdown`, suspendre/arrêter les arbres (`_terminate_tree`) et marquer les jobs concernés `stopped`; ou mieux, détacher le pipeline (`start_new_session=True`) pour qu'il survive à un redémarrage du serveur, le serveur réattachant l'état au démarrage (cf. D17).
- Régression : Aucune — le comportement actuel (mort non contrôlée) n'est pas une garantie à préserver ; vérifier `server.py:_load` qui convertit déjà `running`→`stopped`.
- Vérification : arrêter le serveur pendant un scan → le job apparaît `stopped` au redémarrage, aucun processus orphelin, log `__END__` présent.

**D17 — Un job interrompu par un crash du serveur reste `running` en mémoire jusqu'au redémarrage, puis est requalifié `stopped` sans vérification** · D · **P2**
- Cité : `server.py:315-329` (`_load` : `if job.status in ("running","paused"): job.status = "stopped"`), `:222` (`meta()` renvoie ce statut), `:442-455` (`resume()` peut relancer un pipeline alors que l'ancien tourne encore dans certains cas).
- Preuve : Déduit (le statut est déduit du fichier, jamais du processus ; aucun `pid` n'est persisté).
- Constat : si le pipeline a survécu (D16, détachement), le serveur redémarre en affichant `stopped` alors que deux writers peuvent cohabiter après un « Resume » — exactement le scénario de D02 mais sur le même job.
- Suggestion : persister `pid` + `started_at` dans `jobs.json`, et au démarrage vérifier l'existence du processus (`psutil.pid_exists` + ligne de commande) avant de requalifier ; proposer « rattacher / tuer ».
- Régression : Aucune — un job réellement mort est toujours requalifié `stopped`.
- Vérification : tuer le serveur pendant un run, redémarrer : le job est `running` (rattaché) ou `stopped` (processus absent), jamais un état incohérent.

**D18 — Relancer un job efface ses logs précédents** · D · **P2**
- Cité : `server.py:400-409` (`start()` : `job.logs.clear()` + `job.log_file().unlink()`).
- Preuve : **Reproduit** — job `…-002828-452c` : le `scan` (log de 00:28:28) a été remplacé par le log du `generate` (00:28:35) ; `GET /logs?from_pos=0` ne renvoie plus que la seconde exécution, la première étant définitivement perdue.
- Constat : impossible de comparer « avant/après » une modification de réglages, ni de retrouver la raison d'un premier échec — alors que le diagnostic repose entièrement sur ce log.
- Suggestion : archiver l'ancien log (`{job_id}.{n}.log`) et conserver `job.logs` en mémoire pour l'exécution courante, avec un sélecteur d'exécution dans l'UI.
- Régression : Aucune — l'affichage par défaut reste le dernier log ; vérifier `_load` (l.315-329) qui relit le fichier principal.
- Vérification : deux exécutions successives laissent deux fichiers de log ; l'UI propose le dernier.

**D19 — « Libérer de l'espace » rapporte un succès même si la suppression a échoué** · D · **P2**
- Cité : `server.py:376-398` (`shutil.rmtree(t, ignore_errors=True)` puis `freed = max(before-after, 0)` et `{"ok": True, …}`).
- Preuve : Reproduit pour le cas nominal (`{"ok":true,"freed_human":"9.5 MB"}`) ; Déduit pour l'échec (les erreurs de `rmtree` sont ignorées par construction).
- Constat : un échec de suppression (fichier verrouillé sous Windows, permissions) est présenté comme un succès avec « 0 KB libéré » ou un chiffre calculé avant/après sans rapport.
- Suggestion : supprimer `ignore_errors=True`, collecter les erreurs par cible et renvoyer `{ok:false, errors:[…]}` ; afficher le résultat réel par dossier (`dump: 1,2 Go`, `html: 240 Mo`).
- Régression : Aucune — le cas nominal produit le même message.
- Vérification : rendre un dossier non supprimable (chmod) → l'API renvoie une erreur explicite, aucun toast de succès.

**D20 — La fusion PDF ignore un fichier corrompu et compte tout de même un succès** · D · **P2**
- Cité : `scripts/merge_pdf.py:94-107` : `except Exception as e: print("⚠ skipped …")` à l'intérieur de la boucle, puis `ok += 1` et `merged.save(...)`.
- Preuve : Déduit (le `try` interne n'incrémente ni `errors` ni un compteur de pages manquantes) ; non exécutable ici (WeasyPrint indisponible).
- Constat : une catégorie peut perdre des articles sans que le job échoue ; le PDF final est présent, crédible, et incomplet. Le log porte l'information mais l'utilisateur ne lit pas 200 lignes.
- Suggestion : compter les pages omises et faire échouer la catégorie (ou l'étape) si `len(chunk) != pages_ajoutées` ; à défaut, un récapitulatif final `⚠ 3 articles omis (X.pdf, Y.pdf)` + statut `done` avec avertissement.
- Régression : Aucune — les PDF valides se comportent pareil ; vérifier `tests/test_merge_pdf.py`.
- Vérification : corrompre un PDF unitaire → l'étape se termine en erreur explicite nommant le fichier.

**D21 — `convert.py` se termine toujours avec le code 0, même si toutes les conversions échouent** · D · **P2**
- Cité : `scripts/convert.py:127-135` (`convert_one` renvoie l'erreur), `:179-188` (comptage + `print` final), `:191-192` (`main()` sans code de retour).
- Preuve : Déduit ; confirmé par lecture du `CHANGELOG.md` (« Fail Fast across the pipeline ») qui ne mentionne pas ce script.
- Constat : sur une machine Windows sans GTK3 (cas documenté dans le README), 200 pages échouent, l'étape 3 est « réussie », et l'échec n'apparaît qu'indirectement à l'étape 5 (« pipeline produced 0 output files ») — le message ne dit pas que la cause est WeasyPrint.
- Suggestion : `sys.exit(1)` si `errors > 0` (ou si `ok == 0`), avec un message final reprenant la première erreur et le lien GTK3 déjà présent dans le README.
- Régression : Aucune — les runs réussis sortent toujours à 0 ; `run.py:307` traite déjà un code non nul comme un échec.
- Vérification : `convert.py` sur un dossier HTML avec WeasyPrint absent → code 1 et message actionnable.

**D24 — Le chronomètre d'étape affiche « ✓ Done » même quand l'étape échoue** · D · **P3**
- Cité : `scripts/run.py:41-49` (`Step.__exit__` : `log(f"✓ Done in …")` inconditionnel, `return False`).
- Preuve : **Observé** (3 occurrences) — `run1.log` : `✓ Done in 20s` suivi de `⚠ FAILURE: pipeline step exited with code 1` ; reproduit via l'API (`✓ Done in 0s` puis `⚠ FAILURE: … export_categories.py … HTML directory not found`).
- Constat : la ligne « ✓ Done » est le seul repère de durée ; sur un échec elle affirme le contraire de ce qui vient de se produire et fausse la lecture du log.
- Suggestion : `__exit__` reçoit `exc_type` ; afficher `✗ Failed after Xs` si `exc_type`, sinon `✓ Done in Xs`.
- Régression : Aucune — texte de log.
- Vérification : une étape qui échoue produit « ✗ Failed after ».

**D25 — Deux formateurs de taille humaine, deux résultats différents** · D+G · **P3**
- Cité : `server.py:118-127` (`_human_size` : « 0 KB », « 1 KB », « 1.0 MB ») vs `scripts/run.py:56-66` (`human_size` : « 0B », « 1.0KB » sans espace, unités jusqu'à PB).
- Preuve : Observé — l'UI affiche `1 KB`, le log `1.6KB`, pour le même fichier.
- Constat : deux implémentations de la même connaissance (DRY) qui donnent déjà des sorties différentes ; toute correction devra être faite deux fois, et les chiffres de l'UI et du log ne se comparent pas visuellement.
- Suggestion : une seule fonction dans `wiki_names.py` (déjà importée des deux côtés) ou un petit module `format.py` partagé, et suppression des deux doublons.
- Régression : Aucune — `tests/test_server_config.py::test_host_path_and_human_size` fige le contrat de `_human_size` : à adapter en même temps (une seule fois).
- Vérification : l'UI et le log affichent la même chaîne pour le même octet.

**D27 — `PUT /api/settings` et `PATCH /api/jobs` suppriment silencieusement les clés inconnues** · D · **P3**
- Cité : `server.py:100-107` (`for k, v in data.items(): if k in allowed`), `server.py:611-624` (`job.params = {k: body["params"].get(k, v) for k, v in DEFAULTS.items()}`).
- Preuve : Déduit ; observé pour l'effet de bord : `load_settings()` ajoute `notebooklm_plan` aux paramètres d'un job, et un `PATCH` le supprime.
- Constat : un client qui envoie un champ utile mais non listé n'a aucun retour ; les paramètres du job changent de forme selon le chemin d'écriture (create vs patch), ce qui rend les tests fragiles.
- Suggestion : fusionner (`{**current, **validated}`) au lieu de reconstruire, et renvoyer la liste des clés ignorées dans la réponse.
- Régression : Aucune — les clés connues suivent le même chemin.
- Vérification : `PATCH` avec une clé inconnue → réponse mentionnant la clé ignorée, paramètres existants conservés.

**D28 — Aucune validation d'URL : un texte quelconque crée un job** · D · **P3**
- Cité : `server.py:587-598` (`create_job` : seul le vide est refusé), `scripts/wiki_names.py:34-37` (`wiki_slug` accepte n'importe quoi), `scripts/detect_wiki.py:83-136`.
- Preuve : **Reproduit** — `POST /api/jobs {"wiki_url":"not a url"}` → job `20261101-000855-5957`, `wiki_slug: "not_a_url"`, aucun avertissement ; l'échec n'arrive qu'à l'étape 1.
- Constat : l'utilisateur obtient un job voué à l'échec, avec un dossier de sortie fantaisiste ; le message d'erreur n'arrive qu'après le démarrage.
- Suggestion : valider à la création (`urlparse`, schéma `http/https`, hôte non vide) et renvoyer 400 avec un exemple d'URL valide (« https://mon-wiki.fandom.com/wiki/Page »).
- Régression : Aucune — les URL valides passent ; vérifier `test_server_config.py` (aucun test ne crée de job avec une URL invalide).
- Vérification : `"not a url"` → 400 ; `ftp://…` → 400 ; URL valide inchangée.

**D29 — Un corps JSON malformé renvoie 500 au lieu de 400** · D · **P3**
- Cité : `server.py:589` (`body = await req.json()`), idem l.606, 613, 646, 705, 717, 740, 748, 752, sans `try`.
- Preuve : **Reproduit** — `POST /api/jobs` avec `not json` → HTTP 500.
- Constat : 500 = « le serveur a un bug », alors que c'est une entrée invalide ; les journaux d'erreur se remplissent de traces inutiles.
- Suggestion : un helper `async def json_body(req)` qui renvoie 400 (`{"error": "invalid JSON"}`) et l'utiliser dans les 9 routes.
- Régression : Aucune.
- Vérification : corps invalide → 400 sur toutes les routes qui lisent un corps.

**D30 — Une sélection contenant des catégories inconnues est acceptée sans avertissement** · D · **P3**
- Cité : `server.py:558-560` (`sel = set(selection); groups = {k: v for k, v in groups.items() if k in sel}`), `scripts/run.py:370-379` (idem, filtre muet).
- Preuve : **Reproduit** — `preview_packing {"selection":["Nope","Weapons"],"max_files":2}` → `file_count: 1` (le groupe « Weapons »), aucune mention de « Nope ».
- Constat : une catégorie renommée côté wiki (ou une sélection enregistrée il y a longtemps) disparaît de la sortie sans que l'utilisateur sache que sa sélection est partiellement obsolète.
- Suggestion : renvoyer `{"unknown": ["Nope"], …}` et l'afficher dans le panneau (« 1 catégorie introuvable — relancer un scan »).
- Régression : Aucune — le calcul est identique.
- Vérification : sélection avec un nom inconnu → avertissement visible, génération non bloquée.

**D31 — Pas de route de lecture d'un job : `GET /api/jobs/{id}` renvoie 404** · D+I · **P3**
- Cité : `server.py:582-760` (liste des routes) ; `grep "@app.get(\"/api/jobs/{"` → seules `category_tree`, `disk`, `logs`.
- Preuve : **Observé** — `curl GET /api/jobs/<id>` → 404 `{"detail":"Not Found"}`.
- Constat : tout client (script, test, intégration) doit télécharger la liste entière pour lire un job ; l'UI s'en accommode mais l'API est asymétrique et non documentée.
- Suggestion : ajouter `GET /api/jobs/{job_id}` renvoyant `job.meta()` (3 lignes) et le documenter dans le README.
- Régression : Aucune — route additionnelle.
- Vérification : `GET` sur un id existant → 200 ; sur un id inconnu → 404.

**D32 — Supprimer un job en cours tue son arbre de processus de façon synchrone, sans coordination avec le lecteur de logs** · D · **P3**
- Cité : `server.py:349-363` (`delete()` → `self._kill(job)` → `_terminate_tree(..., timeout=4.0)` → `rmtree`), `:472-524` (le thread lecteur appelle `job.push()` qui ouvre `log_file()` en append).
- Preuve : Déduit ; non reproduit en 1 essai (le processus mourait avant l'`rmtree`). Le risque est réel : entre la mort du processus et `rmtree`, le thread lecteur peut appeler `push()` sur un dossier déjà supprimé → `FileNotFoundError` dans le thread, `finally` qui relance, job perdu à mi-chemin.
- Constat : fenêtre de course ; en cas de déclenchement, l'exception est avalée par le thread (aucune trace côté UI) et le job n'est pas sauvé (`_save()` non atteint).
- Suggestion : marquer `status = "stopped"` et attendre la fin du thread (`join` avec délai) avant `rmtree` ; rendre `Job.push()` tolérant (`mkdir(parents=True, exist_ok=True)` + `try/except OSError`).
- Régression : Aucune.
- Vérification : test qui supprime un job en cours 20 fois de suite → aucune trace dans stderr, `jobs.json` cohérent.

**D33 — Pause/Resume sur un processus disparu renvoie `ok:true` sans rien faire** · D · **P3**
- Cité : `server.py:431-440` (pause : `if job.status != "running" or not job._proc: return`), `:442-455` (resume : `elif job.status in (…) : self.start(job_id)`).
- Preuve : Reproduit pour le cas nominal (pause → état `T`, resume → `S`), Déduit pour les cas muets.
- Constat : le bouton Pause sur un job qui vient de finir ne produit aucun retour ; l'utilisateur clique plusieurs fois et ne sait pas si l'action a été prise en compte.
- Suggestion : renvoyer `{ok:false, error:"Job is not running"}` et afficher un toast (cf. C07).
- Régression : Aucune.
- Vérification : pause sur un job `done` → toast d'erreur, aucun succès.

**D38 — La suite de tests ne couvre aucun des défauts P0/P1 de cet audit** · D · **P2**
- Cité : `tests/` (28 tests, 7 fichiers) ; aucun test pour : le mode texte (D01), le dossier de sortie partagé (D02), les collisions de `page_stem` (D03), la parité aperçu/résultat (D07), la sélection/`ADD_DIVERS` (C14), les paramètres invalides (D08), le cycle de vie du serveur (D14-D19).
- Preuve : Mesuré — `pytest -q` → 28 passés ; `grep -c "def test"` par fichier ; inventaire complet en annexe du rapport.
- Constat : la suite protège les régressions de la passe précédente (nommage, fail-fast, configuration) mais pas les chemins où se trouvent les pertes de données actuelles ; elle donne une fausse assurance (28/28 verts alors que D01/D02/D03 sont reproductibles).
- Suggestion : ajouter 6 tests de caractérisation avant toute correction (mode texte, collision de stem, sortie partagée, parité aperçu, paramètres invalides, cycle de vie) — un par défaut, sur le faux wiki décrit dans `docs/audit-total/rapport.md`.
- Régression : Aucune.
- Vérification : chaque test échoue sur le code actuel (preuve du défaut) et passe après le correctif.

**D39 — « Resumes automatically if the dump is incomplete » n'est pas vrai** · D · **P3**
- Cité : `README.md:33`, `scripts/run.py:204-207` : la reprise se déclenche si **un** `*.xml` et `config.json` existent, sans vérifier la complétude.
- Preuve : Déduit (aucune vérification de taille/dernière page) ; cohérent avec D44 (même logique pour l'extraction).
- Constat : un dump interrompu (XML tronqué, présent) est considéré comme complet ; l'extraction ne verra que les pages déjà écrites dans l'XML et l'archive sera partielle sans erreur.
- Suggestion : faire écrire par `wikiteam3` un marqueur de fin (ou vérifier `config.json`/`--resume`), et ne skipper que si ce marqueur est présent ; sinon relancer avec `--resume`.
- Régression : Aucune — un dump complet reste skippé.
- Vérification : interrompre un dump (stub) → relancer → le dump reprend au lieu d'être accepté.

**D40 — La validité du dump repris dépend d'une nouvelle détection d'URL, qui peut différer et provoquer un re-téléchargement complet** · D · **P3**
- Cité : `scripts/run.py:242-250` (`saved_url = config_field(config_json,"api","index")` comparé à `wiki_url` issu d'un `detect_wiki.py` relancé à chaque exécution), `scripts/detect_wiki.py:83-136`.
- Preuve : Déduit (comparaison de chaînes exactes ; `detect_wiki` peut renvoyer `--api https://x/api.php` ou `--index https://x/index.php` selon l'état du wiki).
- Constat : si la détection choisit une autre voie (API tombée entre-temps → `--index`), `saved_url != wiki_url` et le dossier `dump/` est **supprimé** (`shutil.rmtree`) avant un nouveau dump complet — perte de plusieurs dizaines de minutes de téléchargement, présentée comme un simple log.
- Suggestion : comparer l'hôte et le chemin de base, pas la voie d'accès, et ne purger qu'après confirmation explicite (ou archiver l'ancien dump au lieu de le supprimer).
- Régression : Aucune — un vrai changement de wiki déclenche toujours un nouveau dump.
- Vérification : relancer un job dont le `config.json` contient `index` alors que la détection renvoie `api` → le dossier `dump/` est conservé.

**D42 — La fusion PDF double l'occupation disque (copie `flat/` de tous les PDF)** · D+F · **P3**
- Cité : `scripts/run.py:75-97` (`flatten` : `shutil.copy2` de chaque PDF), `:404` (`flatten(pdf_dir, flat_dir, ".pdf")` avant `merge_pdf.py`), `server.py:380-383` (`purge` doit nettoyer les deux dossiers).
- Preuve : Déduit (copie intégrale, sans lien) ; mesuré sur un cas réduit (`flat/` = copie exacte de `pdf/`).
- Constat : pour un wiki produisant 3 Go de PDF, 3 Go supplémentaires sont écrits puis supprimés — sur un disque de 20 Go libres, cela peut faire échouer la fusion pour une raison incompréhensible.
- Suggestion : passer à `merge_pdf.py` un index `stem → chemin physique` (il n'a besoin que des chemins) au lieu d'un dossier aplati ; sinon, créer des liens durs (`os.link`) quand le système de fichiers le permet.
- Régression : Aucune — `merge_pdf.py` reçoit déjà un dictionnaire `available: {stem: Path}` (l.36-38) ; seul le chemin source change.
- Vérification : après l'étape 5, `flat/` n'existe plus ou occupe ~0 octet ; le PDF fusionné est identique.

**D44 — Une extraction partielle est considérée comme terminée : archive silencieusement incomplète** · D · **P1**
- Cité : `scripts/run.py:273-277` (`elif html_count > 0: skip_step(...)` : n'importe quel nombre de fichiers HTML > 0 suffit à sauter toute l'extraction), `scripts/extract.py:234-242` (la reprise page à page existe mais n'est jamais appelée dans ce cas).
- Preuve : **Reproduit** — `dump/` complet + 2 fichiers HTML sur 8 (simulant un arrêt en cours d'extraction) : `run5.log` affiche `↩ Step already complete -- skipped (2 HTML files already present)`, puis `⚠ FAILURE: …/categories.json not found -- delete the 'html' folder of this job …` et `EXIT=1`. Si `categories.json` existe (cas réel : il est sauvegardé tous les 50 articles), le run continue et produit une archive de 2 pages sur 8, marquée `done`.
- Constat : après une coupure, un redémarrage ou un `Stop`, la reprise ne complète pas l'archive ; elle la fige à l'état partiel — et le seul remède proposé est de supprimer un dossier à la main.
- Suggestion : toujours appeler `extract.py` (il sait reprendre) ou comparer le nombre de pages du XML au nombre de fichiers HTML et ne skipper que si les deux coïncident ; le coût d'un appel est un parcours d'XML, déjà nécessaire.
- Régression : Aucune — le skip reste possible quand `html_count == pages(XML)` ; vérifier `tests/test_run_pipeline.py` (phase `generate`, aucun changement).
- Vérification : `dump/` de 8 pages + 2 HTML → le run extrait les 6 manquantes (log `6 new + 2 resumed`) et produit 8 pages.

**D45 — Le remède conseillé par l'application est une action cachée** · D+A · **P2**
- Cité : `scripts/run.py:349-350` (« delete the 'html' folder of this job (or check 'New dump') »), `server.py:1377` + `server.py:1050-1053` (« Re-render output » masqué sauf PDF, cf. A09), `server.py:1862-1863` (les boutons de purge ne suppriment pas `html/` en scope `pdf` et suppriment aussi `dump/` en scope `intermediate`).
- Preuve : Reproduit (message observé dans `run5.log`) + Déduit (aucune action de l'UI ne supprime `html/` seul ; `clean` supprime **tout** dont `dump/`).
- Constat : l'utilisateur à qui on demande de supprimer `html/` n'a comme options que « New full dump » (qui re-télécharge tout) ou « Re-render » (invisible en mode texte). Il choisit donc de tout re-télécharger, ou abandonne.
- Suggestion : ajouter une action « Re-extraire (conserve le dump) » qui appelle le pipeline avec `rerender=true`, visible quel que soit le format.
- Régression : Aucune — `rerender` existe déjà dans le pipeline (`run.py:190-193`).
- Vérification : un job avec `html/` partiel propose cette action et ré-extrait sans re-télécharger.

**D46 — Les images sont téléchargées puis jamais utilisées** · D+F · **P2**
- Cité : `server.py:65` (`images: True` par défaut), `scripts/run.py:237-238` (`dump_args.append("--images")`), et **aucune** occurrence de `img`/`image` dans `scripts/extract.py` (hors CSS), `scripts/convert.py`, `scripts/clean_html.py`, `scripts/export_categories.py` (vérifié par `grep`).
- Preuve : Déduit (chaîne d'export : le HTML produit par `action=parse` conserve les `src` distants ; `convert.py:132` appelle `HTML(filename=src)` sans `base_url`).
- Constat : chaque dump télécharge l'intégralité des images (souvent la majorité du volume et du temps) pour un résultat qui n'en contient aucune localement — et la conversion PDF tente de les récupérer à nouveau sur le réseau page par page (échecs lents).
- Suggestion : soit réécrire les `src` vers les fichiers téléchargés (`dump/images/…`) et passer `base_url` à WeasyPrint, soit décocher « Include images » par défaut et le documenter comme non supporté ; dans les deux cas, mesurer l'effet sur la durée du dump.
- Régression : **Assumée** si l'on désactive par défaut — les PDF perdraient des images distantes qu'ils n'affichent déjà pas de façon fiable ; à valider humainement. Atténuation : conserver l'option.
- Vérification : dump avec et sans images (durée, taille) ; un PDF exporté affiche les images localement ou aucune requête réseau n'est émise (`convert.py` avec `url_fetcher` bloqué).

**D47 — Un processus suspendu devient orphelin : `stop`, `resume` et `delete` ne le suivent plus** · D+H · **P1**
- Cité : `server.py:400-410` (`start()` : `job._proc = Popen(...)` remplace la référence), `:431-440` (`pause()`), `:442-455` (`resume()`), `:349-363` (`delete()` → `_kill(job)` n'agit que sur `job._proc`), `:472-524` (`_run` ne garde que le dernier `Popen`).
- Preuve : **Reproduit** — job `20261101-002828-452c` : `scan` démarré (pid 2871), `POST /pause` → état `T` ; `POST /generate` → **second** `run.py` qui termine et passe le job à `done` ; `POST /resume` → un **troisième** processus démarre ; `POST /stop` → `{"ok":true}` alors que **2871 reste en état `T`** (seul `kill -9` manuel l'a arrêté).
- Constat : dès qu'un job est relancé, le pid suspendu n'est plus référencé par personne ; aucun bouton ne peut l'arrêter, il conserve ses descripteurs et ses verrous (sous Windows, la suppression du dossier du job échoue), et il reprendra son écriture si un `resume` le réveille. Des processus suspendus invisibles peuvent s'accumuler.
- Suggestion : conserver **l'ensemble** des processus par job (`job._procs: set[Popen]`), refuser tout nouveau run si l'un d'eux est vivant (409, cf. A08), et faire porter `stop`/`delete`/`pause` sur la liste complète (`_terminate_tree` pour chacun).
- Régression : Aucune — le cas nominal n'a qu'un processus ; l'interface n'expose pas la notion de processus multiples.
- Vérification : pause → generate → stop : `ps` ne montre plus aucun `run.py` du job ; `delete` du job réussit sous Windows.

---

## Axe E — Accessibilité (10 constats)

**E01 — Aucun style de focus visible ; `outline:none` sur les champs** · E · **P2**
- Cité : `server.py:861` et `:870` (`outline:none`), `server.py:863` (seul `:focus` existant = changement de `border-color`) ; `grep ":focus-visible"` = 0.
- Preuve : Mesuré (0 `:focus-visible`, 2 `outline:none`, 3 `:focus`) + calcul : la bordure passe de 1,55:1 à 5,66:1 — un liseré de 1 px.
- Constat : au clavier, l'utilisateur ne voit pas où il est ; sur les boutons, l'anneau natif est conservé (donc incohérent avec les champs où il est supprimé).
- Suggestion : `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }` global, et retirer `outline:none`.
- Régression : Aucune — ajout de règle ; vérifier que l'anneau ne soit pas rogné par `overflow:hidden` de `.app`/`.tree-body` (offset interne de 2 px).
- Vérification : parcours au clavier de chaque écran : indicateur visible, contraste ≥ 3:1.

**E03 — Le développement/repli de l'arbre est réservé à la souris** · E+A · **P2**
- Cité : `server.py:1664-1678` (`nodeHtml` : `<div class="tree-row" …>` avec `span.tree-toggle`), `server.py:1724-1731` (`treeClick` sur `onclick` du conteneur), `server.py:937` (`cursor:pointer`, aucun `tabindex`).
- Preuve : Déduit (aucun élément focusable dans la ligne hors la case à cocher) + Mesuré (0 `tabindex`, 0 `role=`).
- Constat : un utilisateur clavier peut cocher/décocher une catégorie visible mais ne peut pas déplier une branche pour atteindre ses sous-catégories : la sélection fine est impossible.
- Suggestion : `<button class="tree-toggle" aria-expanded="false" aria-controls="…">` + gestion `Enter`/`Espace`, et `role="treeitem"`/`aria-level` sur la ligne.
- Régression : Aucune — `treeClick` reste le gestionnaire, appelé aussi par le bouton.
- Vérification : `Tab` atteint chaque chevron, `Entrée` déplie, `aria-expanded` bascule.

**E04 — Aucun `<label for>` : les champs ne sont pas nommés pour les technologies d'assistance** · E · **P2**
- Cité : `server.py:1256-1294` et `:1360-1379` (`<div class="opt-group"><label>Texte</label><input …></div>`) ; `grep "for="` = 0 occurrence.
- Preuve : Mesuré (0 `for=`), Observé (les `<label>` sont des frères, pas des enveloppes : seules les cases `.fmt-check`/`.opt-check` sont enveloppées).
- Constat : un lecteur d'écran annonce « zone de texte » sans nom pour ~18 champs ; cliquer sur le libellé ne place pas le focus.
- Suggestion : `id` déjà présent sur chaque input → ajouter `for="<id>"` sur le `<label>` correspondant (18 occurrences mécaniques).
- Régression : Aucune — purement déclaratif.
- Vérification : chaque input a un nom accessible (inspecteur d'accessibilité) ; clic sur libellé → focus.

**E05 — Cibles tactiles sous 24 × 24 px** · E · **P2**
- Cité : `server.py:940` (`.tree-cb` 13 px), `:826` (`.job-cb` 14 px), `:939` (`.tree-toggle` largeur 14 px), `:909` (`.btn-sm` : 0,7 rem de texte + 0,22 rem de padding vertical ≈ 20 px de haut), `:881`/`:873` (cases 14 px).
- Preuve : Mesuré (dimensions déclarées + calcul de la hauteur de `.btn-sm` : 11,2 × 1,2 + 2 × 3,5 ≈ 20,4 px).
- Constat : les contrôles les plus utilisés du panneau de sélection (cases, chevrons) et toutes les actions secondaires sont sous le minimum WCAG 2.5.8 (24 px) ; au doigt, les erreurs de ciblage sont certaines.
- Suggestion : porter la zone cliquable à 24 px minimum (`width/height:24px` sur les cases + `padding` sur `.btn-sm`), et agrandir la ligne cliquable du chevron à toute la ligne.
- Régression : Aucune — l'arbre gagne 11 px de hauteur par ligne ; vérifier `.tree-body { max-height:380px }` (moins de lignes visibles → à ajuster à 440 px).
- Vérification : mesure des zones cliquables ≥ 24 × 24 px sur les 6 contrôles cités.

**E06 — Boutons réduits à une icône : nom accessible fragile** · E · **P3**
- Cité : `server.py:975` (`title="Settings"` seul), `:1475` (`title="Delete"`), `:1491` (« Clear » textuel, OK), `:1571` (📂 + texte, OK).
- Preuve : Déduit (le `title` n'est pas une source fiable de nom accessible selon les implémentations ; il n'apparaît pas au clavier sur mobile).
- Constat : deux boutons n'ont pas de nom textuel fiable ; le sens de 🗑 (supprimer le job et ses données) n'est pas exprimé.
- Suggestion : `aria-label="Delete job (data and logs)"` + `title` conservé, ou libellé visible.
- Régression : Aucune.
- Vérification : nom accessible non vide pour les deux boutons.

**E07 — Aucune région `aria-live` : les changements d'état ne sont pas annoncés** · E · **P2**
- Cité : `server.py:1061-1082` (`showToast` crée des `div` sans `role="status"`), `server.py:1597-1622` (`updateDetail` change le badge sans annonce), `server.py:1115` (sondage toutes les 2 s).
- Preuve : Mesuré (0 occurrence de `aria-`).
- Constat : un utilisateur de lecteur d'écran n'apprend ni la fin d'un job, ni une erreur, ni le résultat d'une suppression ; il doit re-parcourir la page.
- Suggestion : `<div id="toasts" role="status" aria-live="polite">` et `aria-live="polite"` sur le conteneur du badge/`gen-info`.
- Régression : Aucune — attributs seulement.
- Vérification : un toast est lu par le lecteur d'écran (test manuel ou `aria-live` inspecté).

**E08 — Aucune structure de titres : les titres de cartes sont des `div`** · E · **P3**
- Cité : `server.py:837` (`.card-title` appliqué à des `<div>` : l.1253, 1269, 1275, 1289, 1484, 1493, 1499, 1503, 1529-1530), `server.py:977` (`h1` unique dans la barre latérale, pas dans le contenu).
- Preuve : Déduit + `grep "<h2\|<h3"` dans `_HTML` = 0.
- Constat : aucune navigation par titres ; le contenu principal n'a pas de titre de niveau 1 (le seul `h1` est « Wiki Archive » dans la barre latérale), et les cartes ne sont pas repérables.
- Suggestion : `<h2 class="card-title">` pour chaque carte, `<h1>` pour le nom du job affiché dans `.detail-head`.
- Régression : Aucune — styles inchangés (`.card-title` s'applique à n'importe quel élément).
- Vérification : la liste des titres d'une page de détail reflète la hiérarchie (h1 = job, h2 = cartes).

**E09 — L'état des étapes est porté uniquement par des couleurs** · E · **P3**
- Cité : `server.py:900-906` (`\.step\.done .step-dot { background: green }`, `.step.active` accent, `.step.error` rouge) et `buildSteps` (`server.py:1554-1561`) — aucun texte « terminé/active/erreur », aucun `aria-current`.
- Preuve : Déduit (le numéro reste identique dans tous les états) ; en niveaux de gris, seuls le remplissage et une ombre changent.
- Constat : une personne daltonienne ou sur un écran délavé ne distingue pas « étape terminée » de « étape en cours ».
- Suggestion : ajouter une coche `✓`/croix `✗` dans `.step-dot` pour les états terminé/erreur, et `aria-current="step"` sur l'étape active.
- Régression : Aucune.
- Vérification : test des yeux plissés/flou : les 3 états restent distincts sans couleur.

**E10 — Au zoom 200 %, les zones de défilement imbriquées se cumulent** · E · **P3**
- Cité : `server.py:805` (`.app { height:100vh; overflow:hidden }`), `:831` (`.detail { overflow-y:auto }`), `:935` (`.tree-body { max-height:380px; overflow-y:auto }`), `:910` (`#terminal { height:300px; overflow-y:auto }`).
- Preuve : Déduit (aucune contrainte relative ; le zoom double les dimensions fixes et réduit la zone utile à ~50 %).
- Constat : à 200 %, l'écran de détail devient une fenêtre de ~150 px de haut contenant elle-même deux zones défilantes ; le contenu est difficilement atteignable, et `overflow:hidden` sur `.app` empêche tout défilement global de secours.
- Suggestion : remplacer les hauteurs fixes par `min-height`/`max-height` en unités relatives (`60vh`), et `100vh` par `100dvh`.
- Régression : Aucune.
- Vérification : à 200 %, toutes les cartes restent atteignables au clavier/souris.

**E11 — Le terminal n'est pas une région de log** · E · **P3**
- Cité : `server.py:910` (`#terminal` est un `div`), `server.py:1911-1931` (`flushLogs` ajoute des `div`).
- Preuve : Déduit.
- Constat : les nouvelles lignes ne sont pas annoncées, le contenu n'est pas sélectionnable comme un bloc (`<pre>`), et un lecteur d'écran le traite comme du texte quelconque.
- Suggestion : `<pre id="terminal" role="log" aria-live="polite" aria-atomic="false" tabindex="0">`.
- Régression : Aucune — le style s'applique déjà par `id`.
- Vérification : les nouvelles lignes sont annoncées poliment, le bloc est focalisable et copiable.

---

## Axe F — Performance et légèreté (8 constats)

**F01 — Le regroupement est en O(k²) et bloque tout le serveur pendant plusieurs secondes** · F+D · **P1**
- Cité : `scripts/pack_files.py:137-157` (boucle gloutonne : un seul couple fusionné par tour, tri complet de `packed` à chaque tour, `sorted(set(p1)|set(p2))` à chaque fusion), `server.py:703-713` (`preview_packing` → `asyncio.to_thread(_packing_preview)`), `server.py:1796-1814` (aperçu relancé à chaque changement de sélection, 350 ms de debounce).
- Preuve : **Mesuré** (3 exécutions) — 800 cat./3 000 pages : 116 / 120 / 121 ms ; 3 998 cat./20 000 pages : 3 489 / 3 569 / 3 732 ms (×5 catégories → ×30 de temps ⇒ quadratique). Endpoint `preview_packing` (4 000 cat.) : 3,94 / 4,42 / 4,55 s. **Pendant** qu'un seul aperçu tourne (4,55 s), les autres requêtes échouent : `GET /api/jobs` renvoie `000` (connexion non servie) contre `200` en 7 ms au repos ; 4 aperçus concurrents prennent 25 à 29 s chacun.
- Constat : sur un wiki de la taille annoncée par le code lui-même (« Minecraft = 3600+ catégories », `server.py:1650-1652`), chaque clic dans l'arbre gèle l'interface et **le serveur entier** (sondage, streaming de logs, boutons Stop/Pause) pendant plusieurs secondes : on ne peut plus arrêter un job pendant ce temps.
- Suggestion : (a) rendre la fusion en tas (`heapq`) avec fusions par lots jusqu'à `≤ max_files` en O(k log k) ; (b) mémoïser l'aperçu par `(hash(selection), max_files, max_words, dedup, mtime des fichiers)` ; (c) pour une sélection « tout coché », renvoyer directement `len(groups)` sans repasser par `pack`. Cible chiffrée : < 300 ms à 4 000 catégories, aucune requête bloquée > 100 ms.
- Régression : Aucune sur les résultats si l'ordre de fusion reste déterministe et identique pour les cas où il n'y a pas de blocage ; vérifier que les noms produits (D10) restent stables — un test comparant les sorties de `pack` avant/après sur 3 jeux de données est obligatoire.
- Vérification : mesure avant/après (3 exécutions, médiane) ; test de non-blocage : pendant un aperçu, `GET /api/jobs` reste < 100 ms.

**F02 — L'aperçu relit et reparse 3 fichiers JSON à chaque changement de sélection** · F · **P2**
- Cité : `server.py:530-556` (`_packing_preview` : `read_text` + `json.loads` de `category_groups.json`, `category_tree.json`, `page_words.json` à chaque appel).
- Preuve : Mesuré — 0,68 Mo + 0,66 Mo + ~0,4 Mo par appel, ×2,5 appels/seconde pendant une sélection active dans l'arbre ; aucun cache.
- Constat : le coût d'entrée/sortie s'ajoute au coût CPU (F01) et grandit avec le wiki (un `category_groups.json` de 30 Mo est courant pour 20 000 pages).
- Suggestion : charger une fois par `(job_id, mtime)` dans un cache mémoire du serveur (`@lru_cache` keyé sur `mtime`), et le partager entre aperçu et génération.
- Régression : Aucune — invalidation par `mtime` ; vérifier le cas où le fichier est réécrit pendant un scan (mtime change → rechargement).
- Vérification : deuxième aperçu consécutif < 50 ms ; un scan réécrit les fichiers → aperçu à jour.

**F03 — Chaque sondage renvoie 700 octets de constantes par job** · F+G · **P3**
- Cité : `server.py:218-234` (`meta()` inclut `"steps": STEPS`), `:1115` (`setInterval(refresh, 2000)`), `server.py:1118-1150`.
- Preuve : Mesuré — 41 jobs → 31 761 octets par sondage (≈ 775 o/job), dont ≈ 500 o pour le tableau `STEPS`, identique pour tous les jobs et déjà présent côté client (`server.py:994` `const STEPS = …`).
- Constat : ~65 % de la bande passante de sondage est une constante recopiée ; à 200 jobs (cas d'un utilisateur qui archive beaucoup), 150 Ko toutes les 2 s.
- Suggestion : retirer `steps` (et `log_count`, cf. G04) de `meta()` ; le client a déjà `STEPS`.
- Régression : Aucune — `meta()` n'est consommé que par `_HTML` (vérifié : aucune occurrence de `job.steps` en JS).
- Vérification : taille de `/api/jobs` pour 40 jobs divisée par ~2,5 ; l'affichage des étapes est inchangé.

**F04 — Dans un onglet en arrière-plan, les logs s'accumulent sans limite (flush par `requestAnimationFrame`)** · F · **P2**
- Cité : `server.py:1907-1910` (`queueLog` → `requestAnimationFrame(flushLogs)`), `:1911-1931` (`flushLogs`).
- Preuve : Déduit (rAF est suspendu pour un onglet non visible) ; un job de 2 000 pages produit ~2 000 lignes en 15-45 min.
- Constat : l'utilisateur lance un archivage puis change d'onglet (cas normal, 45 min d'attente) : `logBuffer` croît indéfiniment en mémoire, et au retour un unique insert DOM de plusieurs milliers de `div` bloque le thread principal.
- Suggestion : vider le tampon via `setInterval` (ou `setTimeout`) plutôt que rAF, plafonner le tampon (dernier N), et ne pas rendre les lignes au-delà de N dans le terminal.
- Régression : Aucune — le flux et l'ordre sont conservés ; vérifier l'auto-défilement (`term.scrollTop`).
- Vérification : onglet caché 2 min pendant un scan → mémoire du tampon bornée, retour instantané.

**F05 — Le terminal conserve chaque ligne en DOM, indéfiniment** · F · **P3**
- Cité : `server.py:1920-1926` (`term.appendChild(frag)` sans purge), `:910` (hauteur fixe 300 px avec `overflow-y:auto`).
- Preuve : Déduit ; mesuré indirectement (une exécution complète du faux wiki produit 69 lignes pour 8 pages → ≈ 8,6 lignes/page ; 2 000 pages ≈ 17 000 nœuds).
- Constat : au-delà de quelques milliers de lignes, le rendu et le défilement se dégradent, pour un contenu que personne ne relit en entier ; le log complet reste disponible dans le fichier.
- Suggestion : conserver les 2 000 dernières lignes en DOM (retirer les premières au-delà) et proposer « Voir tout le log » (fichier, cf. I09).
- Régression : Aucune — les lignes anciennes restent dans `jobs/<id>.log`.
- Vérification : job de 20 000 lignes → DOM borné, défilement fluide.

**F11 — L'image Docker embarque des paquets inutilisés au moment de l'exécution** · F+G · **P3**
- Cité : `Dockerfile:3-12` : `git`, `curl`, `libxml2-dev`, `libxslt1-dev`, `libffi-dev`, `ghostscript`, `poppler-utils`, `dos2unix`.
- Preuve : Déduit — `grep -rnE "\bgs\b|ghostscript|pdftk|pdfunite|curl|git "` dans `scripts/` et `server.py` → **aucune** occurrence ; la fusion PDF utilise `pikepdf` (`scripts/merge_pdf.py:19`), `lxml` arrive en wheel (donc pas besoin des en-têtes `-dev`), `git`/`curl` ne servent qu'au clonage côté hôte.
- Constat : image plus grosse et build plus lent (ghostscript + poppler ≈ 150 Mo) pour des outils que le code n'appelle jamais ; surface d'attaque supplémentaire (H08).
- Suggestion : ne garder que `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 libcairo2 fonts-liberation fonts-dejavu` et `dos2unix` ; supprimer le reste.
- Régression : Aucune par analyse statique — à confirmer par un `docker build` + un run complet réel (non réalisable ici) ; garder `git` si l'on veut permettre `pip install` depuis un dépôt git.
- Vérification : `docker images` (taille) et pipeline complet dans le conteneur.

**F12 — Pas de `.dockerignore` : le contexte inclut `data/` et `.venv/`** · F+G · **P3**
- Cité : racine du dépôt (`ls -a`) : `.gitignore` existe, **aucun `.dockerignore`** ; `docker-compose.yml:4` (`build: .`).
- Preuve : Déduit (Docker envoie tout le contexte) ; ordre de grandeur : un `.venv` ≈ 200 Mo, un `data/` avec un dump XML peut dépasser 1 Go.
- Constat : chaque `docker compose up --build` (le mode proposé par `update.bat`) transfère et hache des gigaoctets inutiles ; sur le parcours utilisateur Windows documenté, c'est plusieurs minutes d'attente.
- Suggestion : ajouter un `.dockerignore` (`data/`, `.venv/`, `__pycache__/`, `*.pyc`, `tests/`, `.git/`, `.pytest_cache/`, `docs/`).
- Régression : Aucune — le `COPY server.py` / `COPY scripts/` reste explicite ; attention : le build a besoin de `scripts/` (ne pas l'exclure).
- Vérification : taille du contexte (`docker build` : « Sending build context ») < 1 Mo.

**F13 — `asyncio.to_thread` ne parallélise pas du Python pur : 4 aperçus concurrents prennent 6× plus de temps** · F · **P4**
- Cité : `server.py:713` (`await asyncio.to_thread(_packing_preview, …)`).
- Preuve : **Mesuré** — 1 aperçu : 3,94-4,55 s ; 4 en parallèle : 25,4 / 27,1 / 28,6 / 28,9 s (attendu si parfaitement parallèle : ~4,6 s ; si purement séquentiel : ~18 s).
- Constat : le `to_thread` donne l'illusion d'un traitement asynchrone ; sous GIL, les threads se disputent le CPU et dégradent aussi la boucle d'événements (F01). L'utilisateur qui clique vite déclenche une file d'aperçus obsolètes.
- Suggestion : annuler/ignorer l'aperçu précédent (`AbortController` + identifiant de requête côté serveur), et exécuter le calcul dans un sous-processus (`ProcessPoolExecutor`) si F01 n'a pas suffi à descendre sous 300 ms.
- Régression : Aucune — la dernière réponse gagne (déjà le comportement attendu, mais non garanti : `updateGenInfo` applique la réponse arrivée en dernier, pas la plus récente).
- Vérification : 4 clics rapides → une seule réponse appliquée, aucune file.

---

## Axe G — Debloat (13 constats)

**G01 — Règle CSS morte** · G · **P4**
- Cité : `server.py:936` (`.tree-node.t-hidden { display:none; }`) ; `grep "t-hidden"` = 1 seule occurrence (la définition).
- Preuve : Mesuré (grep).
- Constat : la classe n'est jamais appliquée ; le filtre remplace entièrement le contenu (`filterTree`, l.1754), donc la règle est un vestige d'une implémentation antérieure.
- Suggestion : supprimer la règle.
- Régression : Aucune — aucune occurrence dans le HTML généré ni le JS.
- Vérification : `grep -c t-hidden` = 0 ; le filtre fonctionne.

**G02 — `loadPrefs`/`savePrefs` : fonctionnalité de préférences abandonnée mais présente** · G · **P4**
- Cité : `server.py:1054-1058` (définition des deux fonctions + clé `localStorage` `wiki-archive-prefs`) ; aucune référence ailleurs (`grep` = 1 occurrence chacune).
- Preuve : Mesuré (grep) ; aucune écriture dans `localStorage` n'est possible sans appel.
- Constat : 6 lignes mortes qui suggèrent une fonctionnalité (mémorisation des préférences du formulaire) que l'utilisateur ne voit jamais, et qui induit en erreur un futur mainteneur.
- Suggestion : supprimer les deux fonctions ; si la fonctionnalité est voulue, la câbler (`loadPrefs()` dans `buildForm`, `savePrefs` dans `collectParams`).
- Régression : Aucune — code jamais exécuté (preuve : aucun appel).
- Vérification : `grep -c "Prefs"` = 0 après suppression.

**G03 — `has_output` est calculé et transmis mais jamais lu** · G · **P4**
- Cité : `server.py:232` (`"has_output": self._has_files(self.merged_dir())`), référence unique.
- Preuve : Mesuré (grep sur `_HTML` : 0 occurrence de `has_output`).
- Constat : un `iterdir()` supplémentaire par job à chaque sondage (toutes les 2 s) pour une donnée que personne ne consomme ; le client déduit la présence de fichiers de `files.length`.
- Suggestion : supprimer le champ (ou l'utiliser pour l'affichage de la carte Files).
- Régression : Aucune (aucun consommateur).
- Vérification : `grep -c has_output` = 0 ; carte Files inchangée.

**G04 — `log_count` transmis mais jamais lu** · G · **P4**
- Cité : `server.py:226`.
- Preuve : Mesuré (0 occurrence en JS).
- Constat : donnée morte dans un payload déjà trop gros (F03) ; `len(self.logs)` est de plus une lecture d'un état mutable partagé entre threads, sans verrou.
- Suggestion : supprimer ; si un compteur est utile pour A13, l'exposer sous une forme consommée (`progress`).
- Régression : Aucune.
- Vérification : idem.

**G05 — `STEPS[].id` n'est utilisé par personne** · G · **P4**
- Cité : `server.py:109-115` (`id: "dump"|"extract"|…`), `server.py:1554-1561` (`buildSteps` n'utilise que `label`), `server.py:1918-1926` (n'utilise que `marker`).
- Preuve : Mesuré (grep `s.id`/`.id` sur `STEPS` en JS : absent).
- Constat : trois champs dont un inutile, dupliqué dans chaque réponse (F03).
- Suggestion : supprimer `id` ; garder `label` + `marker`.
- Régression : Aucune.
- Vérification : `grep STEPS` côté JS cohérent.

**G06 — `MAX_PAGES_PER_FILE` n'est jamais positionné : la branche de découpage par nombre de pages est morte** · G · **P3**
- Cité : `scripts/pack_files.py:168` (`max_pages = int(os.getenv("MAX_PAGES_PER_FILE","0"))`), `:57-62` (`_exceeds`), `:65-86` (`_split_large`), `:96-111` ; aucun `MAX_PAGES_PER_FILE` dans `server.py`, `run.py`, `docker-compose.yml`, `.env.example` (absent).
- Preuve : Mesuré (grep sur tout le dépôt : une seule occurrence, la lecture).
- Constat : trois signatures et deux boucles portent une limite de pages toujours nulle ; code mort en pratique, et le message d'aide du CLI (`:17`) laisse croire qu'elle est disponible.
- Suggestion : soit l'exposer (le paramètre `max_pdf` pour les PDF existe déjà côté `merge_pdf`), soit supprimer le paramètre et ses branches.
- Régression : Aucune — `max_pages=0` désactive tout ; vérifier que retirer le paramètre ne change pas `pack()` (3 tests à ajouter).
- Vérification : `grep MAX_PAGES_PER_FILE` = 0 ; sorties identiques sur les 3 jeux de données.

**G07 — Import inutilisé** · G · **P4**
- Cité : `scripts/detect_wiki.py:8` (`import json`) ; ruff `F401`.
- Preuve : Mesuré (`ruff check --select F`).
- Constat : bruit ; le fichier n'utilise pas `json` (il utilise `r.json()`).
- Suggestion : supprimer l'import.
- Régression : Aucune.
- Vérification : `ruff check` propre sur `F`.

**G08 — `pack_files.py` lit `MAX_FILES` dans l'environnement avant l'argument positionnel, qui devient ignoré** · G · **P3**
- Cité : `scripts/pack_files.py:166` (`max_files = int(os.getenv("MAX_FILES", argv[3] …))`), `scripts/run.py:385-388` (positionne `MAX_FILES` **et** passe l'argument).
- Preuve : Déduit + Observé (même valeur dans les deux cas aujourd'hui, donc le bug est latent).
- Constat : deux sources pour le même paramètre (SSOT violé) ; un appel manuel `pack_files.py … 500` avec `MAX_FILES=50` exporté produit silencieusement 50 groupes — et `run.py` modifie `os.environ` pour les sous-processus, ce qui fuit vers les étapes suivantes.
- Suggestion : l'argument positionnel fait foi, l'environnement seulement en repli (`argv[3] if len(argv) > 3 else os.getenv(...)`).
- Régression : Aucune — `run.py` passe la même valeur aux deux endroits.
- Vérification : `MAX_FILES=10 python pack_files.py in tree out 3` → 3 groupes.

**G11 — Dépendances non épinglées : aucun build reproductible** · G+H · **P3**
- Cité : `requirements.txt` (11 lignes, aucune version), `requirements-dev.txt` (`pytest>=7`).
- Preuve : Mesuré — `pip-audit -r requirements.txt` → « No known vulnerabilities found » **aux versions résolues aujourd'hui** ; `wikiteam3` tire `internetarchive`, `mwclient`, `lxml`… dont les versions changent sans contrôle.
- Constat : deux installations à des dates différentes peuvent produire des comportements différents (c'est exactement ce qui a provoqué plusieurs correctifs du CHANGELOG : `--namespaces`, formats d'export) ; un futur avis de sécurité ne sera pas détecté en CI.
- Suggestion : `requirements.txt` avec bornes (`fastapi>=0.110,<1`, etc.) + un `requirements.lock` généré (`pip freeze`) utilisé par le Dockerfile et `run.bat`.
- Régression : Aucune fonctionnelle ; à valider par un run complet après épinglage.
- Vérification : deux environnements neufs installent exactement les mêmes versions.

**G12 — La liste des dépendances existe en deux exemplaires (Dockerfile et requirements.txt)** · G · **P3**
- Cité : `Dockerfile:15-25` (`pip install wikiteam3 mwparserfromhell …`) vs `requirements.txt`.
- Preuve : Observé (les deux listes sont identiques aujourd'hui, à la casse près).
- Constat : duplication garantie de dériver ; ajouter une dépendance demande deux éditions (le CHANGELOG montre déjà une correction de ce type).
- Suggestion : `COPY requirements.txt . && RUN pip install --no-cache-dir -r requirements.txt`.
- Régression : Aucune — même résolution (et G11 s'applique aussi).
- Vérification : une seule liste dans le dépôt ; build OK.

**G13 — Le montage `:ro` rend le `dos2unix` de démarrage inopérant, et masque la copie de l'image** · G+D · **P3**
- Cité : `docker-compose.yml:6` (`./scripts:/scripts:ro`), `Dockerfile:26-29` (`COPY scripts/ /scripts/` + `RUN dos2unix`), `Dockerfile:33` (`CMD … dos2unix /scripts/*.py 2>/dev/null; …`), `README.md:399` (« rebuilt on every startup to fix Windows line endings »).
- Preuve : Déduit (écriture impossible sur un montage `:ro` ; l'erreur est redirigée vers `/dev/null`) ; le `COPY` est de toute façon masqué par le montage.
- Constat : la conversion annoncée n'a jamais lieu dans le mode docker-compose (seul le build, masqué ensuite, l'applique) ; le README décrit un mécanisme qui ne peut pas fonctionner, et l'échec est invisible.
- Suggestion : soit monter en lecture-écriture et garder le `dos2unix` (en journalisant l'échec), soit l'assumer et documenter « vérifier les fins de ligne avant `docker compose up` ». Supprimer `2>/dev/null`.
- Régression : Aucune fonctionnelle (Python 3 tolère les CRLF pour les sources importées) ; le message d'erreur devient visible.
- Vérification : un `scripts/*.py` en CRLF monté en `:ro` → le conteneur démarre et le log dit que la conversion a été ignorée.

**G14 — Un transcript de conversation IA est versionné dans le dépôt, avec un lien de partage privé** · G+H · **P3**
- Cité : `Claude-Archiving MediaWiki for NotebookLM on Windows 10.md` (298 lignes, 11 Ko), ligne 6 : lien `claude.ai/chat/<identifiant>`.
- Preuve : Observé (fichier présent, 298 lignes de dialogue interne et de traces d'outils).
- Constat : bruit documentaire (ce n'est ni une doc utilisateur ni une spécification) et **divulgation** : un lien de conversation partagée est exposé dans un dépôt public, sans rapport avec le produit.
- Suggestion : déplacer hors du dépôt (ou dans un `docs/history/` explicitement privé) et **révoquer le partage** du lien côté Claude (action humaine) ; ne conserver que le prompt utile s'il a une valeur de documentation.
- Régression : Aucune — aucun code ni test ne le référence (vérifié par grep).
- Vérification : le fichier n'est plus suivi ; le lien ne résout plus.

**G15 — `PLAN.md` décrit comme « à faire » un travail déjà livré** · G · **P4**
- Cité : `PLAN.md` (workstreams A/B/C/D) : `scripts/pack_files.py`, `category_tree.json`, `scripts/clean_html.py`, l'interface de sélection (`server.py:1529-1550`) existent désormais.
- Preuve : Observé (les quatre livrables sont présents et fonctionnels).
- Constat : un lecteur (ou un agent) prend PLAN.md pour la feuille de route et peut « re-implémenter » l'existant ; il ne reste aucune trace de ce qui est fait, partiel ou abandonné.
- Suggestion : soit archiver (`docs/history/plan-2026.md`) avec un état par workstream, soit cocher les items livrés en tête de fichier.
- Régression : Aucune.
- Vérification : PLAN.md indique explicitement l'état de chaque workstream.

---

## Axe H — Sécurité (9 constats)

**Modèle de menaces retenu** : application locale mono-utilisateur, mais exposée
par défaut sur `0.0.0.0:8080` et publiée par `docker-compose.yml` (`ports: 8080:8080`).
Actifs : les archives produites (données), le disque de l'hôte (volume `/data`),
le réseau local (l'app effectue des requêtes sortantes arbitraires). Acteurs :
un site web visité par l'utilisateur (navigateur), un poste du réseau local, un
wiki distant malveillant.

**H01 — Aucune authentification et écoute sur toutes les interfaces** · H · **P1**
- Cité : `server.py:1955-1957` (`uvicorn.run(app, host="0.0.0.0", …)`), `docker-compose.yml:12-13` (`ports: "8080:8080"`), aucune notion d'utilisateur/session/jeton dans `server.py`.
- Preuve : Observé (`ss`/`listening_ports` : `0.0.0.0:8080`) ; toutes les routes répondent sans identifiant (essais par `curl`).
- Constat : sur un poste connecté à un réseau partagé (bureau, Wi-Fi public, VM NAT), n'importe qui peut créer des jobs (remplir le disque), lire les journaux (chemins, URL), lancer des téléchargements et **supprimer** toutes les archives.
- Suggestion : écouter sur `127.0.0.1` par défaut (option `BIND_HOST`), et documenter le mode « réseau » avec un jeton (`?token=`/en-tête) vérifié par un middleware. Dans `docker-compose.yml`, publier `127.0.0.1:8080:8080`.
- Régression : Aucune pour un usage local ; un utilisateur qui accède depuis un autre poste devra définir `BIND_HOST=0.0.0.0` + jeton (à documenter).
- Vérification : depuis une autre machine du réseau, la connexion est refusée par défaut ; avec jeton, les routes sans jeton renvoient 401.

**H02 — Aucune protection contre les requêtes intersites : un site visité peut agir sur l'application** · H · **P1**
- Cité : `server.py:587-760` (aucune vérification d'`Origin`/`Referer`, aucun jeton anti-CSRF), `server.py:589` (lecture du corps JSON via `req.json()`, indépendante du `Content-Type`), `server.py:605-608` (`PUT /api/settings`), `:644` (`/generate`), `:748` (`/bulk_delete`).
- Preuve : Reproduit — des requêtes de modification d'état émises avec un en-tête `Origin` étranger et un `Content-Type` que le navigateur autorise en requête « simple » sont acceptées (200) et exécutées (suppression effective d'un job de test).
- Constat : une page web quelconque ouverte dans le même navigateur peut, sans lire les réponses, modifier les réglages, créer des jobs et déclencher des suppressions ; combiné à une attaque de rebinding DNS (le nom de domaine résout vers 127.0.0.1), l'attaquant lit aussi les réponses et contrôle l'API entière, y compris l'exfiltration du contenu des archives.
- Suggestion : exiger un en-tête personnalisé (`X-Requested-With`/jeton) sur toutes les routes mutantes (une requête « simple » ne peut pas en porter sans préflight), vérifier `Origin`/`Host` contre une liste (`localhost`, `127.0.0.1`), et n'accepter que `application/json`. Documenter le jeton pour le mode réseau (H01).
- Régression : Aucune — l'UI envoie déjà `Content-Type: application/json` (`server.py:1198-1200`, `1782-1785`, etc.) ; ajouter l'en-tête dans un helper `apiFetch` unique.
- Vérification : une requête mutante sans en-tête personnalisé ou avec un `Origin` étranger → 403 ; l'UI continue de fonctionner.

**H03 — SSRF : l'URL du wiki est fournie par le client et récupérée côté serveur** · H · **P2**
- Cité : `server.py:587-598` (aucune contrainte sur `wiki_url`), `scripts/detect_wiki.py:39-76` (`SESSION.get` sur des URL dérivées), `scripts/extract.py:82-89`, `scripts/build_categories.py:61`, `scripts/run.py:228-236` (wikiteam3 sur cette URL).
- Preuve : Reproduit (le pipeline interroge l'hôte fourni — faux wiki local servi sur `127.0.0.1:8099` pendant tout l'audit) ; Déduit pour les cibles internes.
- Constat : le serveur émet des requêtes vers n'importe quelle adresse `http(s)` (y compris `127.0.0.1`, plages privées, endpoints de métadonnées cloud) et écrit les réponses dans le dossier de sortie ; combiné à H02/rebinding, cela devient un canal de lecture de services internes.
- Suggestion : refuser les adresses privées/loopback/link-local par défaut (résolution + filtrage, en suivant les redirections), avec une option explicite (`ALLOW_PRIVATE_HOSTS=1`) pour les wikis internes — c'est un usage légitime à conserver.
- Régression : **Assumée** pour un utilisateur qui archive un wiki d'entreprise : il devra activer l'option (documentée). Aucun impact sur les wikis publics.
- Vérification : `wiki_url` pointant vers `127.0.0.1`/`169.254.x` → refus avec message explicite ; option activée → autorisé.

**H04 — Aucune limite de nombre de jobs ni de volume : remplissage du disque** · H · **P2**
- Cité : `server.py:330-338` (`create`) ; aucune borne ; `server.py:365-374` (`bulk_delete` ne nettoie que sur demande).
- Preuve : Reproduit — 41 jobs créés en quelques secondes par script, tous persistés (`jobs.json`) ; chaque job garde son dump et son HTML.
- Constat : un script (ou un site, cf. H02) peut saturer le volume `/data` de la machine hôte, avec pour conséquence l'échec de tous les archivages en cours et, sur un petit disque, l'indisponibilité du système.
- Suggestion : quota configurable (nombre de jobs, octets totaux) vérifié à la création et avant chaque étape ; refus explicite avec la liste des jobs les plus volumineux.
- Régression : Aucune — un usage normal reste très en dessous.
- Vérification : au-delà du quota, `POST /api/jobs` → 507/400 avec message.

**H05 — L'XML du wiki est analysé avec `xml.etree.ElementTree` (expansion d'entités)** · H · **P3**
- Cité : `scripts/extract.py:16` (`import xml.etree.ElementTree`), `:224` (`ET.iterparse`).
- Preuve : Déduit (signalé par `bandit` B314/B405) ; l'XML provient d'un wiki distant non maîtrisé.
- Constat : un dump malveillant (entités internes récursives) peut consommer toute la mémoire du processus d'extraction ; impact limité (le job échoue) mais réel sur un serveur qui héberge aussi d'autres jobs.
- Suggestion : `defusedxml.ElementTree.iterparse` (dépendance légère) ou désactiver explicitement la résolution d'entités ; borner la taille du XML traité.
- Régression : Aucune — les dumps légitimes n'utilisent pas d'entités personnalisées.
- Vérification : dump de test avec entités récursives → erreur claire, mémoire bornée.

**H06 — Les journaux et l'API exposent des chemins absolus de l'hôte** · H · **P3**
- Cité : `scripts/run.py:170-173` (journalise `out_dir`, `job_dir`), `server.py:228` (`out_path`), `server.py:933` (affichage) ; observé : `/tmp/audit/...` dans chaque log, `/data/jobs/...` en Docker.
- Preuve : Observé.
- Constat : les chemins révèlent l'arborescence, le nom d'utilisateur Windows (`C:\Users\<nom>\…` via `HOST_PROJECT_DIR`) et la structure du conteneur ; utile à un attaquant qui a déjà un accès partiel (H01/H02), et sans intérêt pour l'utilisateur qui lit un log.
- Suggestion : journaliser des chemins relatifs au job et n'afficher le chemin absolu que dans la carte Files (déjà prévu pour « Copy path »).
- Régression : Aucune — le chemin complet reste accessible par le bouton dédié.
- Vérification : les logs ne contiennent plus de chemin absolu ; « Copy path » fonctionne.

**H08 — Le conteneur s'exécute en root et monte les données de l'hôte en écriture** · H · **P3**
- Cité : `Dockerfile` (aucune directive `USER` après l'installation), `docker-compose.yml:5` (`./data:/data` en lecture-écriture, pas d'option `:ro` ni `user:`).
- Preuve : Déduit (image `python:3.11-slim` par défaut root).
- Constat : un défaut d'exploitation du pipeline (XML malveillant, dépendance compromise) donne root dans le conteneur avec un accès en écriture au dossier `data/` de l'hôte ; sans isolation supplémentaire (`read_only`, `cap_drop`), la surface est inutilement large.
- Suggestion : `RUN useradd -m app && USER app`, `chown` du volume, et `cap_drop: [ALL]`, `security_opt: [no-new-privileges]` dans le compose.
- Régression : Aucune — le pipeline n'a besoin que d'écrire dans `/data` ; attention aux permissions du volume monté (documenter `chown`).
- Vérification : `docker compose exec … id` → uid non nul ; run complet OK.

**H09 — Les en-têtes de sécurité HTTP sont absents** · H · **P3**
- Cité : `server.py:580-586` (`FastAPI(title=…)` sans middleware), réponse de `/` (aucun `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`).
- Preuve : Observé (`curl -i /` : seulement `server: uvicorn`).
- Constat : la page peut être encadrée par un site tiers (clickjacking sur « Delete selection »), et aucune politique ne limite l'exécution de scripts ; défense en profondeur manquante sur une interface qui déclenche des suppressions.
- Suggestion : middleware ajoutant `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, et une CSP adaptée (le script inline actuel impose `'unsafe-inline'` ou un nonce généré).
- Régression : Aucune — à vérifier : la CSP ne doit pas casser l'`EventSource` (connect-src 'self') ni le presse-papier.
- Vérification : en-têtes présents sur `/` ; l'UI fonctionne (logs SSE, copie de chemin).

**H10 — « Clean up stopped/errored » supprime les données de plusieurs jobs en un clic, après 5 s** · H+A · **P2**
- Cité : `server.py:1186-1191` (`cleanupStoppedErrored` : sélectionne **tous** les jobs `stopped`/`error`), `:1193-1213` (`requestDelete`, annulation 5 s), `server.py:365-374` (`bulk_delete` → `delete` → `rmtree` du job **et** de la sortie).
- Preuve : Déduit (aucun écran de confirmation, aucune liste des cibles avant l'action).
- Constat : un clic sur 🧹 détruit définitivement les dumps, HTML et PDF de tous les jobs arrêtés/en erreur — c'est-à-dire précisément ceux qu'on veut reprendre plus tard ; le seul garde-fou est un toast de 5 s.
- Suggestion : afficher la liste des jobs concernés (noms, tailles) avant l'action, exiger une confirmation, et par défaut ne purger que les données intermédiaires (pas la sortie finale).
- Régression : Aucune — l'action reste disponible, en deux étapes.
- Vérification : 🧹 ouvre une liste ; annuler ne supprime rien.

---

## Axe I — Complétude (11 constats)

**I01 — Aucun moyen d'ouvrir ni de télécharger un fichier produit depuis l'interface** · I · **P3**
- Cité : `server.py:1563-1582` (`buildFiles` : nom + taille, sans lien), `server.py:582-760` (aucune route `/file`).
- Preuve : Déduit + Observé (« Copy path » est la seule action, utile seulement si `HOST_PROJECT_DIR` est défini et le chemin monté sur l'hôte).
- Constat : en Docker sans `HOST_PROJECT_DIR`, le chemin affiché (`data/output/…`) n'existe pas sur la machine de l'utilisateur : il ne peut pas atteindre ses fichiers sans passer par `docker cp`.
- Suggestion : route `GET /api/jobs/{id}/file?name=…` (validation stricte du nom contre la liste de `_files_meta`), et un lien sur chaque ligne de fichier (cf. B12).
- Régression : Aucune — route additionnelle en lecture seule ; la vérification du nom empêche toute traversée de chemin.
- Vérification : clic sur `Weapons.md` → contenu affiché/téléchargé ; `?name=../server.py` → 400.

**I02 — Le nombre de mots par fichier n'est visible nulle part** · I · **P3**
- Cité : `server.py:1563-1582` (nom + taille uniquement), `server.py:530-579` (l'aperçu calcule `words` par groupe, `groups: [{name, pages, words}]` mais `updateGenInfo` n'affiche que `file_count`).
- Preuve : Déduit (les mots sont calculés puis jetés côté client).
- Constat : la contrainte qui a motivé tout le regroupement (500 000 mots par source NotebookLM) n'est jamais montrée ; l'utilisateur ne peut pas vérifier qu'elle est respectée, ni voir les fichiers proches de la limite.
- Suggestion : afficher dans la carte Files les mots par fichier (données déjà présentes dans l'aperçu et dans `page_words.json`) et signaler les fichiers > 90 % de la limite.
- Régression : Aucune.
- Vérification : la carte Files affiche « Weapons.md — 44 mots », avec un avertissement au-delà de 450 000.

**I03 — Aucune action de reprise ciblée par étape** · I · **P3**
- Cité : `server.py:1518-1527` (actions limitées à Pause/Stop/Resume), `server.py:400-410` (`start()` relance le pipeline complet avec sauts d'étapes implicites).
- Preuve : Déduit.
- Constat : après l'échec de l'étape 4 (D06), « Resume » relance tout (dump, extraction) et le log ne dit pas clairement ce qui sera refait ; l'utilisateur n'a pas de « relancer l'étape 4 ».
- Suggestion : exposer `POST /api/jobs/{id}/start?from=categories` et l'afficher sur l'étape en erreur (bouton ↻ dans la carte Progress).
- Régression : Aucune — `phase` existe déjà (`run.py:142`) ; ajouter une valeur `from_step` n'invalide pas les sauts actuels.
- Vérification : relancer l'étape 4 seule, sans re-télécharger (mesure : durée < 1 min sur le faux wiki).

**I04 — On ne peut exclure que des catégories, jamais des pages** · I · **P4**
- Cité : `server.py:1529-1540` (arbre de catégories), `scripts/pack_files.py:31-54` (granularité page non exposée).
- Preuve : Déduit.
- Constat : une catégorie fourre-tout (« Misc », « Stubs ») ne peut être réduite qu'en entier ; la tâche « exclure 3 pages » est impossible.
- Suggestion : troisième niveau optionnel dans l'arbre (pages), déjà présent dans `category_tree.json` (`pages`, retiré par `server.py:696-698` pour alléger) ; le remettre à la demande.
- Régression : **Assumée** (charge utile plus grande) — atténuation : chargement à la demande au dépliage.
- Vérification : déplier une catégorie affiche ses pages ; décocher une page l'exclut de la sortie.

**I05 — La correspondance catégorie → pages n'est consultable nulle part dans l'interface** · I · **P4**
- Cité : `server.py:687-701` (`category_tree` renvoie `total_pages`, pas les pages), `scripts/build_categories.py:173-187`.
- Preuve : Déduit.
- Constat : avant de lancer une génération de 45 minutes, l'utilisateur ne peut pas vérifier qu'une catégorie contient bien ce qu'il croit (seulement un compteur).
- Suggestion : afficher au clic sur une catégorie un aperçu (10 premiers titres) — sans changer le contrat de l'endpoint (nouvelle route ou paramètre `?with_pages=1`).
- Régression : Aucune.
- Vérification : clic sur « Weapons » → liste des titres.

**I06 — Aucune estimation de volume avant la génération** · I · **P4**
- Cité : `server.py:1780-1795` (aperçu : nombre de fichiers, pas de volume), `server.py:567-570` (`words_of` disponible).
- Preuve : Déduit (les mots sont agrégés puis non affichés, cf. I02).
- Constat : impossible de savoir si la génération va produire 5 Mo ou 2 Go avant de la lancer.
- Suggestion : afficher les mots et un ordre de grandeur d'octets (`mots × ~6` pour le texte) dans la barre de génération.
- Régression : Aucune.
- Vérification : la barre indique « ≈ 34 fichiers · 12,4 M mots ».

**I08 — Les jobs ne peuvent pas être renommés** · I · **P4**
- Cité : `server.py:1028-1030` (`jobName` = hôte), `server.py:611-624` (`PATCH` n'accepte que `wiki_url`/`params`).
- Preuve : Déduit.
- Constat : avec plusieurs archivages du même wiki, les libellés sont identiques (A05) et il n'existe aucun moyen de les distinguer durablement.
- Suggestion : champ `label` optionnel dans `jobs.json`, éditable par `PATCH`, affiché dans la liste.
- Régression : Aucune — champ additionnel, repli sur l'hôte.
- Vérification : renommer un job, recharger la page : le libellé persiste.

**I09 — Le log complet n'est pas téléchargeable** · I · **P4**
- Cité : `server.py:1911-1931` (contenu du terminal seulement), `Job.log_file()` (`server.py:150`) jamais exposé par une route.
- Preuve : Déduit.
- Constat : pour diagnostiquer un échec, il faut copier-coller un terminal de 300 px ou aller chercher `data/jobs/<id>.log` à la main.
- Suggestion : `GET /api/jobs/{id}/log.txt` (`FileResponse`) + bouton « Download log ».
- Régression : Aucune.
- Vérification : le bouton télécharge un fichier texte complet.

**I10 — « New full dump » et « Re-render » ne peuvent pas être définis comme valeurs par défaut** · I · **P4**
- Cité : `server.py:1240-1302` (`buildSettingsPage` : `force`, `images`, `max_pdf`, `workers`, `delay`, `cat_workers`, formats, NotebookLM — ni `clean` ni `rerender`).
- Preuve : Déduit.
- Constat : les deux options les plus coûteuses (re-télécharger tout, ré-extirper) ne sont réglables que job par job ; incohérence avec les autres options, et impossibilité d'un « toujours ré-extirper ».
- Suggestion : les ajouter aux réglages (elles existent déjà dans `DEFAULTS`, l.62-63) ou documenter pourquoi elles en sont exclues.
- Régression : Aucune.
- Vérification : les deux cases apparaissent dans les réglages et pré-remplissent un nouveau job.

**I11 — Aucune version de l'application n'est visible ni interrogeable** · I · **P4**
- Cité : `server.py` (aucune constante `VERSION`), `_HTML` (aucun pied de page), aucune route `/api/version`.
- Preuve : Déduit.
- Constat : impossible de savoir quelle version tourne (utile quand `docker compose` réutilise une image ancienne) ; un rapport de bug ne peut pas la citer.
- Suggestion : `VERSION = "0.6.0"` (aligné sur `CHANGELOG.md`), exposé dans `/api/settings` et affiché dans le pied de la barre latérale.
- Régression : Aucune.
- Vérification : la version s'affiche et correspond au CHANGELOG.

**I12 — Pas de sonde de santé pour Docker** · I · **P4**
- Cité : `docker-compose.yml` (ni `healthcheck`, ni `restart:`), `server.py` (aucune route `/healthz`).
- Preuve : Déduit.
- Constat : après un redémarrage de la machine, le conteneur reste arrêté (pas de `restart: unless-stopped`), et aucun outil ne peut vérifier que l'application répond.
- Suggestion : `GET /healthz` (200 + version) et `healthcheck` + `restart: unless-stopped` dans le compose.
- Régression : Aucune.
- Vérification : `docker compose ps` montre l'état `healthy` ; après redémarrage de l'hôte, le service revient.
