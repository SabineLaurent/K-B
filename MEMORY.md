# K-B — mémoire du projet

Ce que le code et le README ne disent pas : le contexte, les estimations et les consignes. Les
décisions sont dans `docs/ADR/journal-decisions-projet.md`. Chargé à chaque session par le
`CLAUDE.md`. Le dépôt est privé jusqu'au 25/10, puis public : rien de personnel ici.

## Contexte

- K-B est le projet support de la certification Développeur IA (RNCP37827) : E1 (pipeline de
  données) et E3 (API IA) d'abord, hors machine learning. K-B tourne en trois temps : d'abord sur le
  Mac, sans conteneur (retour en CLI, fiches `.md`) ; puis en conteneurs en local, avant le 29/10 si
  le temps le permet ; puis sur Azure Container Apps au 08/11 (journal ADR, 2026-10-20,
  « Squelette E1 E3 : cadrage du 20/10 », décision 1). Le suivi de la certif vit dans un dépôt
  séparé, pas ici. Les dates sont tenues par time-knight.
- Les critères de la certif deviennent des exigences de K-B seulement là où ils servent le produit.
- **Binôme** : Sabine travaille avec Claude Code. Claude écrit l'essentiel du code et de la doc ;
  Sabine pilote, relit, teste et décide. Les estimations en tiennent compte : les comptes, la prise
  en main d'outils nouveaux, les décisions et la relecture ne s'accélèrent pas.
- **Refactorisation de l'ETL** (branche `refactoring/etl`, PR du 2026-10-24) :
  `docs/refactoring/plan.md` fait foi pour la cible et les étapes restantes (3 bis avant la mise
  en ligne du 08/11, puis 6 à 9), une branche et une PR par étape (sa partie 6). Ce qui en est
  acté est au journal ADR (2026-10-22 : `post/` hors de l'ETL ; 2026-10-23 : `etl/pipeline.py`,
  porte des deux parcours pour `commands/`) et à la règle 5 de `conventions.md`.

## Estimations

- Une issue porte sa taille seule (label `size:*` et champ `Size` du board), sans heures (règle
  de l'utilisatrice du 2026-10-20).
- La surveillance du modèle est portée par #163 (comparaison des outils), puis #162 et #164, au
  jalon « POC 25/10 » : métriques en OpenTelemetry vers Grafana Cloud dès le premier temps
  (journal ADR, 2026-10-20, décision 4).
- Coupes du 15/10 (journal ADR, « POC du 25/10 ») : la compilation des clips en wiki passe après
  le 29/10, `kb search` après le 08/11. arXiv et Zotero vont ensemble ; l'ingester arXiv est
  repris de brief09.

## Problèmes connus

- **arXiv bloqué au-delà de 2 000 papiers** (constat du 2026-10-05, porté par #71, hors E1 et
  non planifié). Si la fenêtre de collecte contient plus de
  2 000 papiers, la source échoue et sa date reste (`src/k_b/etl/sources/arxiv.py:91-95`). La fenêtre
  suivante part du même point et finit plus tard : elle dépasse encore le plafond, la source
  échoue à chaque collecte. Cela contredit la consigne du 05/10 : lancée tous les jours, K-B
  rattrape les jours manqués (#65).
- **Deux collectes en même temps perdent des dates** (relevé par la revue de #201, le 2026-10-18,
  porteur à désigner par Sabine). `collect_all_sources` lit tout `collection_state.json` au début
  et le réécrit en entier à la fin (`src/k_b/etl/extract.py`) : la dernière collecte qui écrit
  l'emporte. Avec `KB_COLLECT_ONLY`, le Mac (`zotero,clipping`) et les conteneurs (le reste)
  collectent à part ; s'ils partagent l'état (#200), leurs collectes ne doivent pas se chevaucher.
- **Le README annonce des métriques « gardées sur ma machine » et restituées « par un outil à
  choisir »** (« Étape 2 », constat de la revue de #5, le 2026-10-18, porté par #165) : contredit
  l'ADR du 15/10 (décision 8), la règle 4 de `poc.md` (une ligne JSON par appel sur stdout) et
  l'ADR du 20/10 (décision 4 : OpenTelemetry vers Grafana Cloud, l'outil est choisi). Périmètre de
  la v0, non corrigé.
- **La ligne « Sécurité » du registre** (fiche 1 : fichiers lisibles par la seule utilisatrice)
  devient fausse quand la base passe dans un volume Docker (#200), puis sur Azure au 08/11 : la PR
  qui change l'hébergement la met à jour (revue de #5, le 2026-10-18).
- **Deux pourquoi de `.claude/rules/poc.md` contredisent le cadrage du 20/10** (revue de #275, le
  2026-10-20 ; signalé à Sabine, qui modifie `.claude/`) : la règle 1 dit « La base passe à
  PostgreSQL au 08/11 (décision 2) », décision en attente de « La base au temps 3 » ; la règle 6
  dit « Le POC en conteneurs », alors que le premier temps se fait sans conteneur (journal ADR,
  2026-10-20, décision 1).

## Interface

- Au premier temps : sur le Mac, sans conteneur, retour dans la console, par les commandes
  `kb`, et fiches `.md` ; ni interface CLI dédiée ni front (journal ADR, 2026-10-20, décision 1).
  `kb search` vient après le 08/11 ; un front écoconçu, plus tard (journal ADR, 2026-10-15,
  « POC du 25/10 »). Une commande de plus, `kb write-tops` (#265), écrit les fiches des tops dans
  le coffre, après `kb import` (journal ADR, 2026-10-19, « Tops : les fiches par `kb write-tops` »).
- L'API IA est servie par `kb serve-ai` (#156), à côté de `kb serve`, sur `127.0.0.1:8001` ; ses
  clients ont leur clé dans `KB_AI_API_KEY_<CLIENT>`, ceux de l'API de données dans
  `KB_DATA_API_KEY_<CLIENT>` (journal ADR, 2026-10-21, « API IA : servir les fiches par
  `POST /digests` »).
- `kb digest` (#209) demande les fiches à l'API IA, puis les écrit dans le coffre,
  `veille/<sujet>/AAAA-MM-JJ.md` ; `kb serve` et `kb serve-ai` doivent tourner (journal ADR,
  2026-10-21, « Fiches de veille : `kb digest` les écrit dans le coffre »).

## Consignes de travail

- Pour la documentation d'une bibliothèque ou d'un service, utiliser Context7 plutôt qu'une
  lecture de page web. Ce que Context7 ne couvre pas : WebSearch, source et date à l'appui ;
  WebFetch seulement sur une URL qu'une recherche du jour vient de rendre.
- Une décision actée ne se repose pas, sauf si Sabine demande à la réviser ou si elle est notée
  « à revoir » : chercher d'abord dans `MISSION.md`, le journal ADR et la conversation, et citer
  d'où vient la réponse. Redemander un accord (commit, push) reste permis.
- Un essai sur un fichier non committé ne s'annule jamais par `git checkout` (il efface aussi le
  travail du fichier) : committer d'abord, essayer sur une copie dans le scratchpad, ou annuler
  par une édition inverse.
- Vérifier les faits avant de les présenter comme sûrs, sources à l'appui.
- `brief09_assistant-veille-tech` est indicatif, il ne fait pas autorité : une décision concertée
  qui fait mieux, ou plus conforme aux pratiques reconnues, l'emporte.
- **Mutations sur une copie du dépôt** (constat du 2026-10-17, #14) : les lancer avec
  `PYTHONDONTWRITEBYTECODE=1` et sans `__pycache__`. Une mutation qui garde la taille du fichier,
  restaurée dans la même seconde, laisse sinon Python exécuter le bytecode de la version mutée :
  les mutations suivantes semblent tuées ou survivantes à tort. Une copie qui garde le `.venv` du
  dépôt lit le `src` du dépôt d'origine (`k_b.pth` y pointe ; constat du 2026-10-18, #242) :
  vérifier d'abord que `import k_b; print(k_b.__file__)` donne le chemin de la copie.
- **Fichiers d'environnement et Bash** (constat du 2026-10-21, #156) : l'outil refuse toute
  commande Bash qui nomme un fichier `.env*`, `.env.example` compris : `cat`, `grep`, `git add`, et
  même un message de commit qui en cite le nom. `.env.example` et `.env.e2e_test.example` se lisent
  et se modifient par Read et Edit ; Sabine tape `! git add <fichier>`. Ne pas contourner (pas de
  `git add -u`).
- **Échappements `\u` et `\x` dans un fichier écrit par Write ou Edit** (constat du 2026-10-21,
  #209) : un `"\u202e"` écrit dans le contenu est arrivé dans le fichier comme le caractère
  lui-même, un contrôle bidirectionnel invisible (Write dans le code, Edit dans ce fichier même ;
  Write a fait de même d'un `\x1b`), alors que `\\` et `\n` restaient tels quels. Écrire ces
  caractères par `chr(0x202E)`, ou par un script Python ou un heredoc `<<'EOF'`, et vérifier
  qu'aucun fichier modifié ne contient de caractère des catégories Unicode `Cc` ou `Cf` hors
  tabulation, retour à la ligne et U+200D.
- **`ruff` sans son cache** (constat du 2026-10-19, revue de #265) : `uv run ruff check` a passé,
  puis `uv run ruff check --no-cache` a trouvé trois imports non triés. Cause non établie : le cache
  est supposé (le `pyproject.toml` ne fixe ni `src` ni `known-first-party`, la détection des imports
  internes est une autre piste). Avant de déclarer les contrôles verts :
  `uv run ruff check --no-cache`.
- **Tests de bout en bout** (#25, 2026-10-21) : un par source, dans `tests/e2e/`, marqués
  `e2e` ; `uv run pytest` (la CI) les écarte (`tests/conftest.py`). Les rejouer sur le Mac, avec
  leur rapport HTML (#290), depuis un terminal sans `.env` exporté :
  `uv run --env-file .env.e2e_test pytest -m e2e -rs --html=reports/e2e-report.html --self-contained-html`
  (une source : `-k <source>`). `.env.e2e_test` ne porte que leurs variables
  (`.env.e2e_test.example`) ; une autre variable de `.env.example` dans l'environnement les arrête
  avant tout `kb`. Le rapport (`reports/`, ignoré par git, en `0600`) donne les résultats, pas leur
  interprétation : le compte rendu reste écrit à la main. Celui de `gh_archive`
  lance une requête BigQuery réelle : ne pas le relancer à la légère. Sans `--basetemp` : pytest
  garde ses 3 dernières sessions (registre, étape 10 de la procédure de tri) ; un `--basetemp`
  n'a plus de rotation et est effacé par pytest s'il existe déjà.
- **Liste des tests collectés** (constat du 2026-10-18, #247) : elle n'est pas stable d'une
  exécution à l'autre. `test_a_key_refused_is_never_quoted` (`tests/ai_api/test_data_api_settings.py`)
  est paramétré par une clé tirée par `secrets.token_urlsafe(32)` au chargement du module. Pour
  comparer deux listes, remplacer d'abord cette clé par un repère :
  `sed -E 's/(never_quoted)\[[A-Za-z0-9_-]{43} /\1[<random key> /'`.
- **Fixtures** (consigne de Sabine, 2026-10-10) : une fixture part toujours d'un exemple issu de
  la collecte.
- **K-B est déterministe** dans sa conception, son code et ses journaux (consigne de Sabine,
  2026-10-04) : un journal ou un message d'erreur dit ce qui a été observé (URL de redirection,
  code HTTP, titre trouvé et titre attendu), jamais une supposition ni une interprétation
  (« probablement », « structure changée ? »). Le pourquoi d'un choix va dans les commentaires
  et la doc, pas dans les journaux.

## Revue, PR et GitHub

- Ordre fixe : commit → revue → rapport à Sabine → corrections sur accord → push → PR. Pas de
  push tant que la revue n'a pas rendu son rapport.
- `/code-review` est lancé directement par la session, jamais enveloppé dans un sous-agent : le
  skill tourne déjà dans le sien.
- Chaque constat de `/code-review` et `/security-review` est rapporté dans la conversation, avec
  un avis (corriger ou non, pourquoi), avant d'ouvrir la PR. Le budget se signale ; il ne fait
  sauter ni une étape ni ce rapport.
- Un plan non trivial est relu par un sous-agent sans contexte avant d'être soumis, son verdict
  rapporté en entier, sauf si la mission dit autrement.
- Titre, description et commentaires d'une PR (compte rendu de revue compris) : en anglais. Une
  issue et ses commentaires : en français.
- Tout texte publié sur GitHub (description et commentaire de PR, commentaire d'issue) finit par
  une ligne vide, `--`, puis `*Written by Claude Code*`. Un message de commit ne porte ni
  `Co-Authored-By` ni `Claude-Session:` ; une PR ne porte pas de lien de session.
- **Labels d'une issue** (consigne de Sabine, 2026-10-19) : une session K-B pose `size:*` et le
  label de périmètre, jamais un label de livrable (`E1`, `hors E1`…) : « si kb n'a pas
  connaissance du livrable, qu'elle ne mette pas de label livrable ».
