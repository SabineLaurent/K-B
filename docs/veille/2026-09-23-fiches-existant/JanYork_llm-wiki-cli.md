# Fiche de veille : JanYork/llm-wiki-cli (`lwc`)

> Analyse en lecture seule du clone `--depth 1` (commit `11e869f`). Rien n'a été exécuté : ni build, ni tests.
> Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : `lwc` est une CLI Rust conçue pour être pilotée par un agent de code (Claude Code, Codex, Cursor… 12 hôtes). Elle stocke les sources immuables et les pages de wiki compilées dans SQLite. Le binaire **n'appelle aucun LLM** : tout le raisonnement revient à l'agent hôte, et `lwc` se charge de la comptabilité (citations, liens, index FTS, journal, file d'ingestion, lint).
- **Pile** : Rust 2024, `rusqlite` (FTS5 bundled), `axum`/`tokio` (viewer web local), `clap`, `pulldown-cmark`, `grafeo` + `surrealdb` (graphes annexes), `rs-fsrs` (répétition espacée pour le module « Tutor »), `zstd` (`Cargo.toml`). Viewer en TypeScript/Vite (`web/src/`). Il n'y a aucun client HTTP dans les dépendances, donc aucune collecte réseau.
- **Dernier commit** : 2026-09-13 (`git log`). Version 0.18.5.
- **Taille** : 436 fichiers, environ 102 000 lignes de Rust dans `src/`. Les skills sont dupliqués quatre fois (`skills/`, `integrations/{claude,codex,pi}-lwc/skills/`).
- **Licence** : Apache-2.0 (`LICENSE`, `Cargo.toml`).
- **Maturité** : élevée côté ingénierie. 38 fichiers de tests d'intégration dans `tests/` et environ 890 `#[test]` recensés par grep. La CI (`.github/workflows/ci.yml`) enchaîne fmt, clippy `-D warnings`, `cargo test`, les tests du viewer, npm, l'installeur et un job Windows. Il y a aussi des workflows release et pages, et des benchmarks (`benchmarks/`, LongMemEval). Le périmètre, lui, déborde largement : Tutor/Book/Practice, Todo/Plan, Sync SSH, CodeGraph, hooks pour 12 agents. `.agents/project-memory.md` montre un projet mené presque en solo, très axé sur la release.

## 2. Architecture

```
src/
  store/schema.rs        schéma SQLite canonique (sources, pages, page_sources, links, operations, ingest_jobs, FTS5…)
  store/migrations.rs    migrations versionnées (user_version), tables todo/plan/changesets ajoutées au fil des versions
  store/content_search.rs  source_add (dédup SHA-256), page_put (liens extraits, provenance), search
  store/indexing.rs      requêtes FTS5 + bm25 pondéré (titre 8, chemin 6, résumé 4, corps 1)
  store/materialize.rs   projection Markdown + lint + log + paquet d'ingestion
  store/types.rs         LINT_ISSUES_SQL : toutes les règles de lint déterministes en une seule requête SQL
  store/temporal_memory.rs  « événements » datés (valid_from/valid_to, rétention 365 j / 256 MiB)
  artifacts/render.rs    rendu des .md (frontmatter YAML), index.md, log.md
  import.rs              import d'un dossier (extensions texte uniquement)
  secret_scan.rs         détection de secrets avant ingestion
  source_diff.rs         diff source ↔ fichier vivant
  changeset.rs           brouillons transactionnels (snapshot SQLite privé, commit/rollback)
  view/mod.rs            viewer web lecture seule, loopback
  mcp.rs                 serveur MCP stdio
  agent/*, learning/*, codegraph/, sync*.rs, archive.rs   périphérie (hors intérêt pour K-B)
docs/agent-workflow.md   contrat de confiance et de workflow (l'équivalent du « schéma »)
skills/using-lwc/        skill agent + references/llm-wiki.md (copie du gist de Karpathy)
```

**Flux principal** (d'après le code) :
1. `lwc source add <fichier>` ou `add-dir` : le secret scan (`src/secret_scan.rs:3`) peut bloquer, sauf `--acknowledge-sensitive-source`. Le contenu est haché en SHA-256 et un `INSERT` n'a lieu que s'il est nouveau (`src/store/changeset_merge.rs` ~l.28-51, contrainte `content_hash … UNIQUE` en `src/store/schema.rs:18`). Le chemin est ensuite enregistré dans `source_path_revisions` et un `ingest_job` est créé à l'état `pending` (`src/store/schema.rs:113-127`).
2. `lwc ingest next` réserve atomiquement le plus ancien job (`pending → analyzing`) et renvoie à l'agent un paquet : source (fenêtrée), schéma, purpose, index des pages (`src/cli/definitions.rs:1022-1035`, `src/store/materialize.rs:520`).
3. L'agent (LLM externe) lit, raisonne, puis écrit ses pages avec `lwc page put` : liens `[[…]]` extraits, `source_ids` validés, provenance obligatoire, contrôle de concurrence optimiste par empreinte (`src/store/content_search.rs:467-560`). Plusieurs écritures peuvent être regroupées dans un changeset (`src/changeset.rs`).
4. Le job passe à `completed`. Sans page dérivée ni raison explicite, le lint lève `shallow_ingest` (`src/store/types.rs:133`).
5. Côté question, `lwc context` ou `lwc search` (FTS5/bm25, granularité document/passage/phrase) fournit le contexte, et c'est l'agent qui synthétise la réponse.
6. `lwc maintenance materialize` régénère `.lwc/wiki/*.md`, `index.md` et `log.md` à partir de SQLite (`src/artifacts/render.rs`).

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans `lwc` | Verdict |
|---|---|---|
| `raw/` immuable | Table `sources` en SQLite, dédupliquée par hash, `source remove` refusé si la source est citée (`src/cli/definitions.rs` ~l.1000). `.lwc/raw` n'est qu'une projection. | **Transformé** : l'immuabilité est garantie par la base, plus par le système de fichiers |
| `wiki/` markdown | Table `pages`. Les `.md` sont une **projection générée** : « Treat `.lwc/raw`, `.lwc/wiki`… as generated projections » (`docs/agent-workflow.md:15-16`). « Never edit `.lwc/wiki.db` directly » (`:13`). | **Inversé** : SQLite fait foi, le Markdown n'est qu'une vue |
| Schéma (AGENTS.md) | `lwc schema set` et `purpose set` stockés dans `meta`. Lint `missing_schema` (`src/store/types.rs:116`). Le skill `using-lwc` sert de mode d'emploi. | Présent, mais rangé dans la base |
| Ingest | File d'attente persistante à états (`pending/analyzing/generating/completed/failed`) (`src/store/schema.rs:116`). Réservation atomique. | **Présent et durci** |
| Query | `search`/`context`/`span`. La réponse elle-même vient de l'agent. Pas de mécanisme dédié au « file back » des réponses, hormis le dossier `queries` de l'index (`src/artifacts/render.rs:36-50`). | Présent côté recherche |
| Lint | 100 % déterministe en SQL (orphelins, liens brisés, pages non citées, index FTS incohérent…), plus des règles de structure Markdown. Contradictions et obsolescence **laissées à l'agent** (`src/cli/definitions.rs:505`). | **Présent, bien découpé** |
| `index.md` / `log.md` | Générés depuis `pages` et `operations`. Le log reprend exactement le format `## [date] action \| cible` du gist (`src/artifacts/render.rs:72-88`). | Présents en projection |
| Obsidian | Seuls les dossiers `.obsidian` sont ignorés à l'import (`src/import.rs:12`). Aucune écriture vers Obsidian n'est prévue, et une page modifiée à la main est écrasée à la prochaine matérialisation. | **Absent** comme interface d'écriture |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Lint entièrement en SQL (une CTE `issues` par règle, code + page + cible + message) | C'est exactement notre « déterministe d'abord » : orphelins, liens brisés, pages sans source, résumé manquant. C'est facile à porter en Python + SQLite, testable, et ça ne coûte rien en LLM. | `src/store/types.rs:114-200` |
| Lint `shallow_ingest` : une ingestion terminée sans page dérivée exige une raison explicite | C'est un garde-fou contre l'ingest bâclé. On peut le transposer avec un champ `statut` dans le frontmatter et un `raison_sans_page`. | `src/store/types.rs:133-145` |
| Séparation « le lint mécanique bloque, le sémantique revient au LLM » (sévérités blocking/advisory) | Ça clarifie ce qui passe par script et ce qui passe par le LLM, et c'est justifiable pour la certification. | `src/store/materialize.rs:391-450`, `src/cli/definitions.rs:505` |
| Dédup des sources par SHA-256 du contenu (`UNIQUE`) + historique des révisions par chemin | Pour la veille, on transposera à l'URL canonique plus le hash du contenu. L'historique `source_path_revisions` permet de détecter qu'une page de release a changé. | `src/store/schema.rs:16-25,129-139` |
| `source status` / `source diff` : fraîcheur par comparaison de hash entre snapshot et fichier vivant, puis `source refs` pour savoir quelles pages citent la source | Ce sont les briques de base de la **péremption** : une source a changé, donc les pages qui la citent sont à revoir. C'est de la détection déterministe, et le LLM n'intervient qu'ensuite. | `src/cli/definitions.rs:926-995` |
| File d'ingestion avec états + compteur de tentatives + `last_error` | Ça trace proprement l'ingest unitaire déclenché par l'humain. On garde la table d'états sans l'automatisation. C'est utile pour le monitoring et la journalisation (certification). | `src/store/schema.rs:113-127` |
| Table `operations` append-only projetée en `log.md` au format du gist | Le journal est interrogeable en SQL **et** lisible en Markdown/grep. Ça répond à la fois à `log.md` et à l'exigence de journalisation. | `src/store/schema.rs:105-111`, `src/artifacts/render.rs:72-88` |
| Frontmatter généré : `type`, `title`, `sources`, `provenance`, `created`, `updated`, `summary` | C'est un bon socle de frontmatter validable par script, avec des dates exploitables pour l'obsolescence et `type` pour notre découpage par type de page. | `src/artifacts/render.rs:1-34` |
| Provenance explicite par page (`user-provided`, `agent-observed`, `hypothesis`) plutôt qu'un score | On qualifie l'origine de l'information sans score de confiance produit par le LLM, ce qui colle à notre décision. | `src/store/schema.rs:47-54` |
| Recherche FTS5 bm25 pondérée par champ (titre > chemin > résumé > corps), sans embeddings | Ça confirme « lexical d'abord » avec une implémentation minimale, directement reproductible en Python `sqlite3`. | `src/store/indexing.rs:513` |
| Scan de secrets avant ingestion (fichiers `.env`, clés privées, préfixes `ghp_`, `sk-proj-`, `AKIA`…) | Garde-fou RGPD/sécurité peu coûteux pour le dossier de dépôt manuel. | `src/secret_scan.rs:3-60` |
| Mémoire temporelle avec `valid_from` / `valid_to` et `since/until` au rappel | C'est le modèle de données qui convient à la **péremption** d'un item de veille (CVE, version) et aux questions « cette semaine ». | `src/store/temporal_memory.rs:152,449-453,794-816` |
| Checkpoints SQLite via l'API backup | Sauvegarde locale propre sans arrêter l'outil. | `src/cli/definitions.rs:440-446` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| SQLite canonique, Markdown en projection écrasée | K-B veut Obsidian comme interface et un wiki Markdown qui fait foi. Ici, toute retouche humaine dans `.lwc/wiki` est perdue à la rematérialisation. | `docs/agent-workflow.md:13-16` |
| Aucun LLM dans l'outil : il dépend d'un agent de code hôte | K-B veut une inférence par API avec un modèle interchangeable par configuration. Ici, le « bibliothécaire », c'est Claude Code ou Codex, donc impossible à piloter depuis un pipeline ou un dashboard. | `Cargo.toml` (aucun client HTTP ni SDK LLM) |
| Aucune collecte : import de fichiers texte locaux seulement | Il n'y a ni RSS, ni API GitHub, ni CVE, ni scraping, alors que c'est le cœur du flux veille de K-B et un critère de certification. | `src/import.rs:8-12` |
| Colonne `confidence REAL` sur les relations sémantiques, fournie par l'agent | C'est un score de confiance produit par le LLM, ce qu'on a explicitement écarté. | `src/store/schema.rs:92-103`, `src/store/graph_search.rs:130` |
| `retrieval_weights` / `retrieval_feedback` (poids −2…+2 réglés par l'agent) | Le classement devient opaque et dérive au gré des sessions agent. C'est une complexité injustifiée à notre échelle. | `src/store/schema.rs:141-163` |
| Dérive de périmètre : Tutor/Book/Practice, Todo/Plan, Sync SSH, CodeGraph, hooks pour 12 agents, graphes Grafeo + SurrealDB | Environ 100 000 lignes, dont l'essentiel ne sert pas au wiki. C'est le contre-exemple de « simplicité d'abord » : trois moteurs de stockage pour un wiki personnel. | `Cargo.toml`, `src/agent/install.rs` (4 388 l.), `src/sync.rs` (5 366 l.) |
| Duplication des skills en quatre copies | C'est une dette de maintenance (tests dédiés pour vérifier la synchronisation). Pour K-B, un seul `AGENTS.md`. | `skills/`, `integrations/*/skills/` |
| Viewer web loopback, lecture seule, sans authentification | Il ne sert pas de modèle pour l'API REST authentifiée et documentée OpenAPI que demande la certification. Il n'y a pas non plus d'OpenAPI dans le dépôt (vérifié par l'arborescence, pas par une recherche exhaustive). | `src/view/mod.rs:59-102` |
| Le lint ne traite pas l'obsolescence sémantique | Il ne détecte que des changements de fichiers source. Aucune règle « page non mise à jour depuis N jours » ni « version/CVE dépassée ». K-B devra l'ajouter, par exemple une règle SQL sur `updated` du frontmatter. | `src/cli/definitions.rs:505` |
| Pas de modèle de données « item daté » pour la veille | `sources.created_at` correspond à la date d'ingestion, pas à la date de publication. Impossible de répondre à « quoi de neuf cette semaine » sur la date réelle de l'item. | `src/store/schema.rs:16-25` |

## 6. En une phrase

Ce que K-B en retire : un lint 100 % SQL déterministe, la dédup par hash avec détection de fraîcheur `source status/diff/refs`, et la table d'opérations projetée en `log.md`. En revanche, K-B garde le Markdown comme source de vérité, appelle le LLM lui-même par API et construit de zéro la collecte et le modèle d'items datés que `lwc` n'a pas.
