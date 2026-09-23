# Fiche de veille — `frankchu91/mindbase`

> Analyse en lecture seule d'un clone `--depth 1` (commit `7aa8fcd`, 2026-09-13). Aucun code exécuté : les constats viennent de la lecture des sources. Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : « Karpathy's LLM Wiki, as a product » (`README.md:1`). Un serveur local et une app web où un LLM maintient un wiki markdown à partir de vos sources, avec une étape d'approbation humaine avant toute écriture. Il est aussi distribué comme serveur MCP et comme plugin Claude Code.
- **Pile** : **TypeScript** en monorepo pnpm (`package.json`, `pnpm-workspace.yaml`). `packages/core` (vitest), `apps/server` (Express), `apps/web` (React 19 + Zustand), `apps/mcp`, `apps/plugin`, `apps/browser-ext`, plus des ébauches iOS/Android. Recherche MiniSearch (BM25) avec un embedding BGE-M3 en option (`packages/core/src/search/hybrid.ts:129`). Validation des sorties LLM par zod. Adaptateurs OpenAI, DeepSeek, Anthropic, Ollama (`packages/core/src/adapters/registry.ts:7-20`).
- **Dernier commit** : 2026-09-13, « chore(release): 0.4.5 — wiki integrity ».
- **Taille** : 746 fichiers, environ 53 500 lignes TS/TSX hors tests, 115 fichiers `*.test.ts`.
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : élevée pour un projet solo. CI GitHub Actions (build core, tests core et serveur, démarrage du MCP, typecheck et build web : `.github/workflows/ci.yml`), tests e2e serveur et Playwright, CHANGELOG tenu à jour, `CLAUDE.md` très détaillé. En revanche, **`CLAUDE.md` est en retard sur le code** : il affirme que le lint n'est « Not implemented » (`CLAUDE.md:47`) alors que le lint existe en deux versions (voir §3). Le produit a pivoté en cours de route (`docs/pivot-plan-2026-05-25.md`), et **deux dispositions de données coexistent** (v1 et v2, voir §2).

## 2. Architecture

```
packages/core/src/
  compile/         l1.ts (compilation source -> page wiki, disposition v1), index_md.ts, contradiction-probe.ts
  wiki/            lint.ts (lint déterministe v0), schema.ts (wiki/schema.md), index-md.ts, log-parse.ts
  search/          MiniSearch + tokenizer multilingue (CJK/pinyin) + hybride RRF
  feeds/store.ts   abonnements RSS dans un fichier feeds.json
  plugin-layout/   chemins de la disposition v2 (sources/, context.md, index.yaml, logs/)
  adapters/        fournisseurs LLM interchangeables
  brief/build.ts   « Daily Brief » : pages mises à jour ces N dernières heures, puis synthèse LLM
apps/server/src/
  index.ts         Express, ~40 groupes de routes, démarre 7 workers en arrière-plan
  lib/rss-worker.ts, lib/inbox.ts, lib/capture-worker.ts   pipeline de capture automatique
  ops/             pipeline « v2 » avec approbation : runner.ts, types.ts (vocabulaire d'actions), executors.ts, recipes/{contribute,build,lint,research}.ts
apps/mcp, apps/plugin   49 outils MCP, commandes /mb:*, sous-agents avec liste blanche d'outils
```

**Deux flux coexistent**, et c'est le point clé de l'architecture :

1. **Flux « capture » (v1, automatique)** : `RSSWorker`, lancé toutes les heures (`apps/server/src/lib/rss-worker.ts:23`), interroge les flux avec `ETag`/`If-Modified-Since` (`:80-95`). Il déduplique par `guid`, en ne gardant que les 200 derniers (`packages/core/src/feeds/store.ts:120`), et extrait le texte avec Readability, avec le résumé RSS en repli (`rss-worker.ts:164-213`). Le résultat part dans une `Inbox` faite de fichiers JSON dans `inbox/`, `inbox/processed/` et `inbox/failed/` (`apps/server/src/lib/inbox.ts:38-41`). Le `CaptureWorker`, lancé toutes les 60 s, vide cette inbox : il écrit `raw/<date>/<id>.md` avec un `.meta.json` (`packages/core/src/ingest/paste.ts:51-85`), puis appelle **directement `compileL1`**, qui écrit dans `wiki/notes/` (`apps/server/src/lib/capture-worker.ts:15, 90` ; `packages/core/src/compile/l1.ts:79`). **Rien n'est validé par un humain dans ce flux.**
2. **Flux « ops » (v2, avec approbation)** : `contribute`, `build`, `research` et `lint` sont déclenchés par l'utilisateur. Le LLM reçoit `context.md`, `index.yaml` et `README.md` (`apps/server/src/ops/gather.ts:16`) et renvoie un **plan JSON validé par zod** (`ops/llm.ts:42-55`). L'utilisateur coche ce qu'il accepte, puis les exécuteurs appliquent le plan (`ops/executors.ts:28-80`) et une ligne est ajoutée à `logs/<date>.md` (`ops/runner.ts:163-169`).

D'après le code, la disposition v1 est refusée pour les projets v2 (`apps/server/src/lib/layout-guard.ts:24-27`), mais le flux RSS/capture continue d'écrire au format v1 via `ctx.store`. **Je n'ai pas vérifié en l'exécutant** comment les deux flux se rejoignent pour l'utilisateur final.

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans MindBase | Verdict |
|---|---|---|
| `raw/` immuable | v1 : `raw/<date>/<id>.md` + `.meta.json`. v2 : `sources/contributors/<user>/<date>.md` et `sources/raw/`, en ajout seul. **L'immuabilité est garantie par le schéma d'actions** : aucune action ne peut cibler `sources/contributors` ou `sources/raw` (`apps/server/src/ops/types.ts:3-7, 12-21`). | Présent, bien protégé en v2 |
| `wiki/` compilé | v1 : `wiki/notes/`, `wiki/concepts/`, avec les métadonnées dans des **`.meta.json` à part, pas en frontmatter** (`packages/core/src/wiki/lint.ts:83-86`). v2 : `context.md` (plafonné à 400 lignes, `ops/types.ts:32`, `executors.ts:38-40`) et `sources/research/*.md`. Les pages écrites par l'IA vivent donc **sous `sources/`**, ce qui brouille la frontière entre sources et wiki. | Transformé, et ambigu |
| Schéma (AGENTS.md) | `wiki/schema.md` global, modifiable, avec des sections injectées dans les prompts (`packages/core/src/wiki/schema.ts:1-26`, `compile/l1.ts:8`). Le flux v2 lit `README.md`, `index.yaml` et `soul.md` à la place. `CLAUDE.md` reconnaît que le schéma est encore « hard-coded in prompts ». | Partiel, en deux versions |
| Ingest | Flux v2 : plan, puis approbation par case à cocher, puis écriture (conforme). Flux RSS v1 : compilation automatique sans humain. | Mixte |
| Query | Recherche hybride BM25 + dense avec citations `source`/`wiki` (`CHANGELOG.md` 0.4.5), et un retour de réponse vers le wiki (`/api/answer/file-back`, `packages/core/src/file-back/build-plan.ts`, non lu en détail). | Présent |
| Lint | **Deux niveaux.** (a) Déterministe : orphelins, liens vers des pages manquantes, pages périmées, doublons entre projets (`packages/core/src/wiki/lint.ts:11-16`). (b) LLM avec **preuves vérifiées par le code** : une contradiction exige 2 citations littérales retrouvées dans les pages, une affirmation périmée en exige 1, sinon le constat est jeté (`apps/server/src/ops/runner.ts:336-384`). S'y ajoutent `unsourced_page` et `uncited_source`, calculés sans LLM (`runner.ts:388-419`). | Présent, et c'est le point fort |
| `index.md` | v1 : `compile/index_md.ts`, `wiki/index-md.ts`. v2 : `index.yaml`. | Présent, deux formats |
| `log.md` | v1 : `wiki/log.md`. v2 : `logs/<date>.md` au format `## [YYYY-MM-DD HH:MM] op \| résumé` (`ops/runner.ts:168`), un fichier par jour, analysable (`wiki/log-parse.ts`). | Présent, transformé |
| Obsidian | Routes `/api/obsidian` et `packages/core/src/obsidian/colorize.ts`. Le markdown reste lisible, mais les métadonnées v1 en `.meta.json` ne sont pas visibles dans Obsidian. | Partiel |

**Limite du lint « stale »** : en v0, une page est dite périmée **uniquement sur son âge** (90 jours par défaut). La comparaison avec la date de mise à jour des sources est explicitement « deferred » (`packages/core/src/wiki/lint.ts:52, 161-163`). Pour la veille, où la péremption est au cœur du problème, c'est insuffisant.

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| **Vocabulaire d'actions fermé, validé par un schéma** : le LLM ne produit qu'un plan JSON (`create_research_page`, `update_context`, `append_context_section`, `add_wikilinks`), et aucune de ces actions ne peut toucher la couche brute | L'immuabilité de `raw/` est garantie par construction plutôt que par une consigne dans le prompt. À transposer en Python avec pydantic. | `apps/server/src/ops/types.ts:3-21` |
| **Citations du lint vérifiées par le code** : chaque contradiction ou affirmation périmée doit citer mot pour mot, et le script vérifie la présence de la citation (après normalisation) ou jette le constat | Du « déterministe d'abord » appliqué à la sortie du LLM, sans score de confiance. Le compteur `dropped=N` va dans le log. | `apps/server/src/ops/runner.ts:336-384` |
| **Lint déterministe séparé du lint LLM** : orphelins, liens manquants, pages sans source, sources jamais citées | C'est exactement notre catégorie « script, pas LLM ». `unsourced_page` et `uncited_source` sont des idées simples à reprendre. | `packages/core/src/wiki/lint.ts:91-149` ; `apps/server/src/ops/runner.ts:388-419` |
| **Citation garantie par le code** : si le LLM oublie `[@chemin/source]`, le code l'ajoute | Chaque page du wiki reste reliée à sa source, ce qui rend la traçabilité et les contrôles de péremption possibles. | `apps/server/src/ops/runner.ts:141-159` |
| **Garde-fou contre les pages en double** : slug normalisé (casse, séparateurs) comparé aux pages existantes et aux plans en attente | Dédup déterministe peu coûteuse avant écriture. | `apps/server/src/ops/runner.ts:82, 111-125` |
| **Collecte RSS polie** : `ETag`/`If-Modified-Since` et 304, un timeout, un User-Agent configurable, Readability avec le résumé RSS en repli, et au premier ajout d'un flux on n'ingère pas l'historique | Bonnes pratiques directement transposables (feedparser + trafilatura/readability en Python). Couvre le critère « collecte multi-sources » de la certification. | `apps/server/src/lib/rss-worker.ts:76-123, 164-213` |
| **Format de log analysable** `## [date heure] op \| résumé` avec les résultats chiffrés | Journal en ajout seul consultable par `grep`, que le LLM peut aussi relire. | `apps/server/src/ops/runner.ts:163-169` ; `packages/core/src/wiki/log-parse.ts` |
| **« Daily Brief »** : pages modifiées depuis N heures, puis synthèse LLM avec des citations `[n]` | Modèle pour « quoi de neuf cette semaine ? ». À refaire sur une vraie requête SQL par date plutôt qu'en parcourant des fichiers. | `packages/core/src/brief/build.ts:67-104` |
| **Plafond de taille sur le fichier de synthèse** (`context.md` ≤ 400 lignes, sinon il faut une page dédiée) | Empêche la page centrale d'enfler, et la règle est simple et déterministe. | `apps/server/src/ops/types.ts:32` ; `ops/executors.ts:38-40` |
| **Règle de prompt « document the shape of things, never live values (SHAs, counts, last synced) »** | Réponse directe à notre problème de péremption : ne pas figer dans le wiki des valeurs qui changent. | `CHANGELOG.md` (0.4.5, « State rule ») ; `apps/server/src/ops/recipes/build.ts:21` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| **RSS compilé automatiquement dans le wiki** : RSS, puis inbox, puis `CaptureWorker` qui appelle `compileL1` sans intervention humaine | Contredit notre décision « ingest unitaire déclenché par l'humain ». Chez nous, les items de veille vont en base de données, pas dans le wiki. | `apps/server/src/lib/capture-worker.ts:10-16, 90` ; `apps/server/src/index.ts:188, 194` |
| **Aucune base pour les items de veille** : `feeds.json`, inbox en fichiers JSON, index MiniSearch sérialisé | Impossible de répondre à « combien d'items sur X cette semaine » par une requête. C'est aussi insuffisant pour la certification (BDD modélisée). | `packages/core/src/feeds/store.ts:34` ; `apps/server/src/lib/inbox.ts:38-61` |
| **Dédup fragile** : `seen_guids` limité aux 200 derniers, clé de dédup de l'inbox **en mémoire** avec une fenêtre de 5 min, pas d'URL canonique | Au redémarrage ou sur un gros flux, un item peut revenir. Nous voulons une dédup par URL persistée en base, avec contrainte d'unicité. | `packages/core/src/feeds/store.ts:19, 120` ; `apps/server/src/lib/inbox.ts:31, 53-58` |
| **Statut porté par des déplacements de fichiers** (`inbox/processed/`, `inbox/failed/`) | C'est l'équivalent du renommage `.done` que nous avons écarté : le statut doit vivre dans le frontmatter ou en base. | `apps/server/src/lib/inbox.ts:38-41` |
| **Métadonnées dans des `.meta.json` à côté des pages** au lieu du frontmatter | Invisibles dans Obsidian, et une deuxième source de vérité qui peut diverger du markdown. | `packages/core/src/wiki/lint.ts:83-86` ; `packages/core/src/ingest/paste.ts:85` |
| **« Stale » calculé sur l'âge seul** | Pour la veille, la péremption doit comparer la page à des sources plus récentes (nouvelle release, CVE mise à jour), pas à une durée arbitraire. | `packages/core/src/wiki/lint.ts:151-171` |
| **Deux dispositions (v1/v2) et deux pipelines coexistants** après un pivot, avec un `CLAUDE.md` en retard sur le code | Complexité et dette : on ne sait plus quel flux écrit où. Mieux vaut une seule disposition dès le départ et un fichier de schéma tenu à jour. | `apps/server/src/lib/layout-guard.ts:10-27` ; `CLAUDE.md` (sections « Operations » et « Critical gaps ») |
| **Pages écrites par l'IA rangées sous `sources/research/`** | Brouille la séparation entre `raw/` et `wiki/`, pourtant centrale dans notre modèle. | `packages/core/src/plugin-layout/paths.ts` (`researchDir: 'sources/research'`) |
| **API sans authentification** : environ 40 groupes de routes, dont `/api/config` qui reçoit les clés API, sans middleware d'authentification (seul `/api/capture` exige un Bearer). `app.listen(PORT)` sans hôte écoute sur toutes les interfaces, et le serveur s'annonce en mDNS | Inacceptable pour notre critère « API REST authentifiée », et c'est un risque sur un réseau local. | `apps/server/src/index.ts:141-183, 232` ; `apps/server/src/routes/capture.ts:77-94` ; `apps/server/src/lib/mdns.ts:3-10` |
| **Tokenizer taillé pour l'anglais et le CJK** : mots vides anglais seulement, pas de français | Notre contenu est en français et en anglais : il faut des mots vides et une racinisation FR, ou le FTS5 de SQLite. | `packages/core/src/search/tokenizer.ts:5-9` |
| **Périmètre éclaté** (iOS, Android, extension navigateur, SRS, graphe, communautés, briefs par SMTP…) | Dispersion typique. K-B doit rester petit. | `apps/` ; `packages/core/src/{srs,analysis}` |
| Pas de spécification OpenAPI | Pas de documentation de l'API à reprendre pour la certification. | vérifié par `grep openapi\|swagger` : aucun résultat |

## 6. En une phrase

K-B reprend de MindBase ses garde-fous déterministes autour du LLM : un vocabulaire d'actions fermé validé par schéma, des citations de lint vérifiées mot pour mot par le code, des citations de source ajoutées d'office, les contrôles orphelins et sources non citées, et une collecte RSS polie. K-B rejette en revanche sa compilation automatique des flux dans le wiki, son stockage en fichiers JSON sans base ni dédup persistante, et son API ouverte sans authentification.
