# T04 — Noms de fichiers injectifs et lisibles

- **Priorité** : P0 (D03) + P2 (D10) · **Axe** : D
- **Constats couverts** : D03, D10
- **Justification** : D03 perd des pages sans avertissement (l'archive est
  incomplète et le rapport affirme le contraire) ; D10 rend les fichiers
  inidentifiables et peut faire écraser un groupe par un autre.

## Preuve et conséquence

- D03 : faux wiki avec `A/B` et `A:B` → `[3] [api] A/B` puis `[5]` ; la seconde
  page est comptée **« resumed »**, `html/` ne contient qu'un `A_B.html`,
  `categories.json` une seule entrée, et le log conclut `✓ 7 new … + 1 resumed`.
  La page `A:B` n'existe nulle part.
- D10 : 3 998 catégories, `MAX_FILES=50` → noms fusionnés de 800+ caractères
  (`Cat 00733 siupk+Cat 00477 uzxru+…`), tronqués à 80 par `cat_stem` :
  illisibles, et deux groupes peuvent converger vers le même nom de fichier
  (aucun test d'existence avant écriture).

## État actuel → état cible

- Actuel : `scripts/wiki_names.py:20-23` (`page_stem` : `re.sub(r"[^\w\s\-]","_")`
  puis `[:120]`) et `:26-31` (`cat_stem` : `[:80]`) — non injectives ;
  `scripts/extract.py:231-253` traite « fichier existant » comme « page déjà
  extraite » ; `scripts/pack_files.py:137-157` fabrique des noms concaténés.
- Cible : (a) `page_stem` injectif (suffixe de hachage court en cas de collision,
  décidé via un index `titre → stem`) ; (b) `cat_stem` ≤ 60 caractères avec
  suffixe déterministe en cas de convergence ; (c) groupes fusionnés nommés
  court et lisible (`Weapons (1-3 sur 12)`), le détail écrit dans
  `packing_plan.json`.

## Cause racine et sites concernés

Normalisation destructive sans registre d'unicité, utilisée à trois endroits qui
doivent rester cohérents : `extract.py` (écrit `{stem}.html`),
`build_categories.py:65` (`page_stem(m["title"])` pour les groupes),
`export_categories.py:208` (`stem.replace("_"," ")` comme titre de repli).
`export_categories.py:227-228` et `merge_pdf.py:93-104` écrivent
`{cat_stem}.{ext}` sans vérifier l'existence.

## Référence à réutiliser

`wiki_names.py` est déjà le point unique importé par 6 modules : c'est le bon
endroit pour la règle. `tests/test_wiki_names.py` fixe le contrat actuel et doit
évoluer dans le même commit.

## Plan d'action

1. `wiki_names.py` : `unique_stem(base, taken: dict[str,str], key) -> str`
   renvoie `base` si libre ou déjà associé à `key`, sinon
   `f"{base[:113]}-{sha1(key.encode()).hexdigest()[:6]}"`.
2. `extract.py` : maintenir `stem → title` (rechargé depuis `page_titles.json`),
   et n'utiliser « fichier existant » comme preuve d'extraction que si l'index
   associe ce stem au titre courant ; écrire `page_titles.json` atomiquement
   (cf. T07) tous les 50 articles et à la fin.
3. `build_categories.py` : utiliser le même index pour `page_stem`.
4. `pack_files.py` : nommer les groupes fusionnés par une règle courte (parent
   commun + plage, sinon `f"{n1[:24]}…+{len(n2)} more"`) et écrire
   `packing_plan.json` (`{fichier → [catégories]}`).
5. `export_categories.py` / `merge_pdf.py` : construire la liste des noms de
   sortie avant écriture, détecter les collisions, suffixer via `unique_stem`,
   journaliser chaque collision.

## Points d'impact

`extract.py`, `build_categories.py`, `wiki_names.py`, `pack_files.py`,
`export_categories.py`, `merge_pdf.py`, et les tests
`test_wiki_names.py`, `test_build_categories.py`, `test_merge_pdf.py`,
`test_extract_fallback.py`. Les stems sans collision ne changent pas (le suffixe
n'apparaît qu'en cas de collision) ; un job déjà extrait avec une collision doit
être re-extrait (log explicite « index absent → re-extraction »).

## Régression

Aucune sur les noms non conflictuels (preuve : `unique_stem` renvoie `base` si
libre ; le test `test_page_stem_sanitizes_and_truncates` reste valable, étendu
d'un cas de collision). Risque identifié : un renommage invaliderait les sorties
existantes — atténué puisque seules les collisions changent, et qu'aujourd'hui
elles provoquent une perte silencieuse.

## Actions humaines requises

Aucune.

## Dépendances

T01, puis T03 (les deux touchent les chemins de sortie ; T03 d'abord).

## Non-objectifs

- Ne pas changer l'encodage des noms (`Café.html` reste `Café.html`).
- Ne pas renommer les catégories sans collision.

## Critères d'acceptation

1. Faux wiki `A/B` + `A:B` → 8 pages HTML, 8 entrées d'index, deux fichiers
   distincts, aucune « resumed » injustifiée.
2. 3 998 catégories → noms < 60 caractères, distincts,
   `packing_plan.json` présent.
3. `written == expected` vérifié avant d'annoncer le succès (aucun écrasement).

## Vérification et repli

Rejouer le faux wiki et l'inventaire de noms sur 3 998 catégories. Repli :
`git revert` ; les anciens stems restent lisibles tant qu'il n'y a pas collision.

## Risques

Un index `page_titles.json` absent sur un job ancien déclenche une
re-extraction : coûteux (re-`action=parse` de toutes les pages). Atténuation :
ne re-extraire que si une collision est détectée à partir de `categories.json`
(déjà présent), sinon continuer.
