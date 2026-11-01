# T13 — sécurité : frontière locale, CSRF, SSRF, en-têtes

- **Priorité** : P1 (H01, H02) + P2 (H03, H04, H10) + P3 (H06, H08, H09) · **Axe** : H
- **Constats couverts** : H01, H02, H03, H04, H06, H08, H09, H10
- **Justification** : l'application écrit et supprime des fichiers arbitraires sur
  l'hôte, sans authentification, en écoutant sur toutes les interfaces, et sans
  protection contre les requêtes intersites. Deux de ces points ont été
  **reproduits** pendant l'audit.

## Modèle de menace (rappel)

Actif local, sans identité : un site web visité par l'utilisateur pendant que
l'application tourne (réseau privé ou `localhost`), un autre utilisateur du
réseau local (H01), et le wiki distant (contenu non fiable : XML, HTML, noms de
fichiers). Hors périmètre : compromission de l'hôte, attaque du wiki distant.

## Preuve et conséquence

- **H01 (P1)** : `uvicorn.run(host="0.0.0.0", port=8080)`
  (`server.py:1955-1957`) et `docker-compose.yml` publient `8080:8080` ; aucune
  authentification, aucune restriction d'origine. Sur un réseau partagé, toute
  personne peut créer des jobs (donc écrire des fichiers) et supprimer ceux des
  autres.
- **H02 (P1, REPRODUIT)** : les routes qui modifient l'état (suppression de jobs,
  réglages) acceptent une requête **inter-sites simple** : corps en `text/plain`
  et origine étrangère → **200**. Un navigateur n'exige aucun preflight pour ce
  type de requête, et le serveur ne vérifie ni `Origin`, ni `Referer`, ni jeton.
  Conséquence : un site visité pendant que l'application tourne peut supprimer
  tous les jobs de l'utilisateur. *Détail volontairement limité dans ce document
  (voir la note de confidentialité en fin de plan).*
- **H03 (P2)** : `wiki_url` est fournie par le client et récupérée côté serveur
  (`detect_wiki.py:83-136`, puis `wikiteam3dumpgenerator`) : un site peut faire
  interroger `http://192.168.1.1/`, `http://169.254.169.254/` ou un port local.
  Le GET d'API renvoie le contenu dans le log du job (lecture directe).
- **H04 (P2)** : aucune limite de nombre de jobs ni de volume ; `data/` est sur
  le volume monté (`docker-compose.yml`) ; un disque plein casse aussi l'hôte.
- **H10 (P2)** : « Clean up stopped/errored » supprime les données de plusieurs
  jobs en un clic, avec seulement 5 s d'annulation (toast), sans récapitulatif du
  volume.
- **H06 (P3)** : les logs et `out_path` exposent des chemins absolus de l'hôte
  (`/home/user/…`), et `_host_path` les traduit avec `HOST_PROJECT_DIR`.
- **H08 (P3)** : le conteneur tourne en root (Dockerfile) et monte `./data` en
  écriture ; les fichiers créés appartiennent à root sur l'hôte.
- **H09 (P3)** : aucun `Content-Security-Policy`, `X-Content-Type-Options`,
  `Referrer-Policy`, `X-Frame-Options`.

## État actuel → état cible

1. **Écoute locale par défaut** : `HOST=127.0.0.1` (docker-compose :
   `127.0.0.1:8080:8080`) ; `HOST=0.0.0.0` n'est possible qu'avec un jeton
   défini (`APP_TOKEN`), exigé sur **toutes** les routes (cookie `HttpOnly` +
   `SameSite=Strict` posé après saisie du jeton, ou en-tête `Authorization`).
2. **Anti-CSRF** : toutes les routes mutantes exigent
   `Content-Type: application/json` **et** un en-tête `X-Requested-With:
   wiki-archive` (impossible en formulaire/`text/plain` sans preflight) ;
   vérification `Origin`/`Sec-Fetch-Site` en défense supplémentaire ; réponse 403
   explicite.
3. **SSRF maîtrisé** : refus des schémas non `http(s)`, résolution DNS puis refus
   des adresses privées/loopback/link-local (sauf si l'utilisateur coche
   explicitement « autoriser les wikis internes », nécessaire en entreprise) ;
   `--api`/`--index` limités au même hôte que l'URL.
4. **Quotas** : `MAX_JOBS` (défaut 20) → 429 ; `MAX_TOTAL_BYTES` (défaut 20 Go) →
   refus avant démarrage d'un dump ; affichage du volume dans `GET /api/jobs`.
5. **Suppressions groupées** : récapitulatif (nombre de jobs, volume) avant
   confirmation, pas seulement le toast d'annulation.
6. **En-têtes** : middleware ajoutant `X-Content-Type-Options: nosniff`,
   `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
   `Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src
   'self' 'unsafe-inline'` (le CSS/JS est inline aujourd'hui : `'unsafe-inline'`
   reste nécessaire tant que T09/T10 n'ont pas extrait les fichiers — documenter
   cette dette).
7. **Conteneur** : utilisateur non-root (`user: "1000:1000"` ou `USER app` dans
   l'image), `read_only` sauf `./data`, `security_opt: no-new-privileges`.
8. **Chemins** : option `MASK_HOST_PATHS=1` (défaut) qui remplace le préfixe hôte
   par `…/` dans l'UI et les logs ; `HOST_PROJECT_DIR` continue de fonctionner.

## Cause racine et sites concernés

Le serveur a été conçu comme un outil local mono-utilisateur, mais son modèle de
déploiement (Docker, `0.0.0.0`) et son API HTTP en font un service réseau sans
frontière. Aucune couche transverse : chaque handler fait confiance au corps et à
l'origine. Sites : `server.py:526+` (tous les handlers), `:1955-1957`
(`uvicorn.run`), `docker-compose.yml`, `Dockerfile`, `scripts/detect_wiki.py:83-136`.

## Référence à réutiliser

- `DEFAULTS` (`server.py:58-75`) : accueillera `MAX_JOBS`/`MAX_TOTAL_BYTES`.
- `_host_path` (`server.py:129-137`) : point unique pour le masquage (H06).
- T08 (`validate`, `json_body`) crée la couche où s'insèrent les contrôles 2 et 3.
- `disk_usage` existe déjà : le quota de volume peut s'appuyer dessus.

## Plan d'action (ordre imposé)

1. **H02 + T08 d'abord** (une nuit d'exposition sinon) : `json_body` exige
   `application/json`, middleware `Origin`/`Sec-Fetch-Site`, en-tête
   `X-Requested-With` côté JS.
2. **H01** : passer `host`/`port` en variables (`HOST`, défaut `127.0.0.1`),
   `docker-compose.yml` sur `127.0.0.1:8080:8080`, documenter « pour un accès
   distant, mettez un reverse-proxy authentifié » — ou implémenter `APP_TOKEN`
   (si retenu : middleware, pas de dépendance).
3. **H03** : `validate_wiki_url()` (T08) + résolution DNS + refus des plages
   privées (`ipaddress.ip_address(...).is_private/is_loopback/is_link_local`),
   avec échappatoire explicite `ALLOW_PRIVATE_HOSTS=1`.
4. **H04** : quotas dans `create_job` et avant le dump ; messages 429/413 clairs.
5. **H10** : dialogue de confirmation récapitulatif.
6. **H09 + H06 + H08** : middleware d'en-têtes, masquage des chemins, non-root.

## Points d'impact

`server.py` (middleware, `create_job`, `uvicorn.run`), `docker-compose.yml`,
`Dockerfile`, `scripts/detect_wiki.py` (résolution), JS (en-tête
`X-Requested-With`), README (§« Security », §« Remote access »). Tests :
nouveau `tests/test_security.py` (403 sans en-tête, 400 sur texte brut, refus
d'URL privée), `tests/test_server_config.py`.

## Régression

- **H02** : les clients non-navigateur (scripts de l'utilisateur) doivent envoyer
  les deux en-têtes → **régression assumée**, documentée dans le README avec un
  exemple `curl`. Aucun script de ce type n'est fourni par le dépôt (vérifié).
- **H01** : un utilisateur qui accédait au port depuis une autre machine perdra
  l'accès par défaut → **régression assumée**, avec `HOST=0.0.0.0` + `APP_TOKEN`
  documenté comme échappatoire.
- **H03** : un wiki d'entreprise en `10.x` sera bloqué → échappatoire
  `ALLOW_PRIVATE_HOSTS=1` documentée.
- **H09** : `'unsafe-inline'` conservé ⇒ CSP partielle ; aucune régression.
- **H08** : le conteneur non-root ne peut plus écrire dans `./data` si les droits
  de l'hôte sont `root:root` → le README doit indiquer `chown -R 1000:1000 data`
  (action humaine).

## Actions humaines requises

1. Choisir la stratégie d'accès distant : (a) `127.0.0.1` uniquement
   (recommandé), (b) `APP_TOKEN`, (c) reverse-proxy authentifié. Le plan
   s'adapte ; (a) est la valeur par défaut proposée.
2. Après application : `chown -R 1000:1000 data` sur la machine hôte.
3. Vérifier qu'aucun port n'était exposé au-delà du réseau local pendant la
   période d'utilisation (journal du routeur/pare-feu) — action de l'utilisateur,
   **non exécutée** ici.

## Dépendances

T08 (validation, `json_body`) doit être livré avant ou avec l'étape 1.

## Note de confidentialité

Si ce dépôt est public, ce document décrit des défauts **non corrigés** et ne doit
pas y être publié tel quel : il indique précisément quelles routes sont
vulnérables et quelles protections manquent. Le principe décrit reste volontaire
(« pas de jeton anti-CSRF, pas de contrôle d'origine ») sans fournir de recette
d'exploitation ; les plans P0-P2 devraient être appliqués avant toute publication
de l'audit. **Non tranché** : la visibilité du dépôt n'a pas pu être vérifiée
depuis cet environnement (accès limité au dépôt et à son API).

## Non-objectifs

- Pas de système de comptes/mots de passe complet (YAGNI pour un outil local).
- Pas de TLS dans le conteneur (reverse-proxy si nécessaire).
- Pas de bac à sable des commandes externes (`wikiteam3`, `pandoc`) : hors
  périmètre, mais à mentionner comme limite assumée (exécution dans le conteneur
  non-root, sans réseau sortant limité).

## Critères d'acceptation

1. `POST /api/jobs/bulk_delete` avec `text/plain` + `Origin: evil.example` → 403.
2. `POST` JSON sans `X-Requested-With` → 403 ; avec → 200.
3. `HOST` par défaut `127.0.0.1` : `curl` depuis l'extérieur du conteneur sur
   l'IP de l'hôte → connexion refusée.
4. `wiki_url: "http://169.254.169.254/"` → 400 (sauf `ALLOW_PRIVATE_HOSTS=1`).
5. 21e job → 429 ; dump dépassant `MAX_TOTAL_BYTES` → refus avant démarrage.
6. `curl -I` → `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
   `Content-Security-Policy` présents.
7. Tests `tests/test_security.py` verts.

## Vérification et repli

Rejouer les deux sondes reproduites (CSRF `text/plain`, `Origin` étranger) et
vérifier 403 ; `curl` sur les en-têtes ; `docker compose config` pour l'exposition
des ports. Repli : `git revert` étape par étape (l'ordre 1→6 permet de revenir en
arrière sans casser l'accès local).
