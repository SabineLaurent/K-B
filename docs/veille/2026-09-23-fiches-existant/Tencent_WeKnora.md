# Fiche de veille : Tencent/WeKnora

> Analyse en lecture seule d'un clone `--depth 1` (commit `1fa915d`, 2026-09-23). Rien n'a été exécuté. Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : plateforme RAG d'entreprise (Tencent) qui parse des documents hétérogènes, les indexe (hybride mots-clés + vecteurs + graphe optionnel) et y répond via un chat et des agents. Depuis quelques versions, elle embarque un **module « Wiki »** qui compile les documents en pages Markdown reliées par des `[[liens]]`, et c'est l'implémentation industrielle la plus proche du pattern Karpathy que j'aie vue.
- **Pile technique** : backend **Go 1.26** (`go.mod:3`, Gin + GORM + asynq/Redis), service de parsing **Python** en gRPC (`docreader/`, uv), frontend **Vue 3** (`frontend/package.json`), app WeChat mini-programme, CLI, serveur MCP. Stockage : PostgreSQL/ParadeDB (défaut), MySQL, ou **SQLite en mode « Lite »** (`migrations/sqlite/`, `docs/LITE.md`). Moteurs de recherche interchangeables : `internal/application/repository/retriever/{postgres,sqlite,elasticsearch,opensearch,qdrant,milvus,weaviate,doris,neo4j,tencentvectordb}`.
- **Dernier commit** : 2026-09-23 (`chore: update BrowserSkill extension version to 0.3.1…`). Version `0.8.0` (`VERSION`).
- **Taille** : 4 317 fichiers suivis, dont 2 571 `.go` (1 225 `_test.go`) et 811 fichiers frontend.
- **Licence** : MIT pour le code Tencent, avec des composants tiers sous d'autres licences (`LICENSE:8`, `THIRD_PARTY_NOTICES.md`). Réutilisation libre, K-B pouvant rester en CC BY-NC.
- **Maturité** : élevée. On compte 12 workflows CI (`.github/workflows/`, par ex. `app.yml:136-143` pour `go test` et `go build`, plus go-lint, docreader et frontend). Il y a 110 migrations versionnées (`migrations/versioned/`), un OpenAPI **généré et testé par contrat** (`docs/swagger.yaml`, `docs/swagger_contract_test.go`), une documentation abondante (en chinois surtout) dans `website-docs/`, du tracing Langfuse et un journal d'audit avec rétention (`internal/application/service/audit_log_retention.go:14`). L'envers : un produit d'entreprise **énorme** (multi-tenant, RBAC, IM DingTalk/Feishu, sandbox, skills, navigateur…) dont le cœur utile pour K-B ne représente qu'une petite fraction.

## 2. Architecture

```
cmd/server/                    point d'entrée Go
internal/
  handler/                     contrôleurs HTTP (Gin) ; wiki_page.go = API wiki
  router/                      routes /api/v1/... (RBAC, X-API-Key, JWT)
  middleware/auth.go           JWT Bearer puis repli X-API-Key (l.118)
  application/service/
    knowledge_create.go        création d'un "knowledge" (fichier/URL), FileHash (l.81)
    knowledge_process.go       parsing -> chunking -> embeddings
    knowledge_post_process.go  fin d'indexation -> déclenche le wiki (l.263-268)
    wiki_ingest.go / _batch.go compilation wiki map/reduce (LLM)
    wiki_ingest_dedup.go       pré-filtre déterministe avant dédup LLM
    wiki_linkify.go            injection déterministe de [[liens]]
    wiki_lint.go               lint déterministe du wiki + autofix
    wiki_page.go               CRUD + révisions des pages
    datasource_service.go      synchro des connecteurs -> knowledge
    chat_pipeline/             pipeline RAG en plugins (query_understand, search, rerank, wiki_boost, merge…)
    retriever/                 indexeur hybride mots-clés + vecteur
  application/repository/retriever/<moteur>/   un backend par moteur (sqlite = FTS5 + BM25)
  datasource/                  cadre de connecteurs + scheduler cron
    connector/{rss,notion,confluence,gitlab,feishu,yuque,dingtalk,ima}
  agent/prompts_wiki.go        TOUS les prompts wiki (résumé, extraction, citation, modif, dédup, taxonomie)
  models/providers/            ~30 fournisseurs LLM (openai, anthropic, deepseek, ollama, openrouter, litellm…)
  types/wiki_page.go           modèle de page (types, statuts, plafonds de révisions)
docreader/                     microservice Python gRPC : parseurs pdf/docx/xlsx/pptx/epub/html/md/image…
migrations/{versioned,sqlite}  schémas SQL
config/config.yaml             configuration ; builtin_models.yaml.example pour les modèles
```

**Flux principal, du dépôt d'une source à la réponse :**
1. **Entrée.** Upload manuel, URL ou connecteur (`datasource_service.go:ingestItem`, l.1281). Le connecteur RSS transforme chaque item de flux en document Markdown (`internal/datasource/connector/rss/connector.go:295-351`) et le scheduler cron le relance périodiquement (`internal/datasource/scheduler.go:18`).
2. **Parsing.** Le service Go appelle `docreader` en gRPC (`docreader/parser/registry.py`), le contenu est découpé (`docreader/splitter/splitter.py`) puis embarqué (embeddings) et indexé en mots-clés.
3. **Post-traitement.** Si la KB a `IndexingStrategy.WikiEnabled`, une opération wiki durable est persistée (`task_pending_ops`) et une tâche asynq `wiki:ingest` est lancée **automatiquement** (`knowledge_post_process.go:263-268`).
4. **Compilation wiki.** Phase MAP en parallèle par document (`wiki_ingest_batch.go:433`) : résumé, extraction d'entités et concepts, citation au niveau du chunk, dédup. Vient ensuite un plan de taxonomie, puis la phase REDUCE par slug sous verrou Redis (`wiki_ingest_batch.go:594`), qui produit un rewrite LLM de chaque page touchée. Suivent le nettoyage des liens morts, l'injection des liens croisés et la reconstruction de la page `index` (`wiki_ingest.go:2207`).
5. **Question.** Le pipeline de chat à plugins récupère des chunks en hybride (documents bruts **et** pages wiki indexées comme chunks `wiki_page`), rerank, puis multiplie le score des chunks wiki par 1,3 (`chat_pipeline/wiki_boost.go:15`) avant la génération. Les agents disposent aussi d'outils wiki (`internal/agent/tools/wiki_*.go`).

## 3. Rapport au pattern Karpathy

Le code cite explicitement le pattern par ses concepts (page `index`, log, lint, ingest), sans nommer Karpathy (grep « karpathy » sans résultat).

| Élément Karpathy | Dans WeKnora | Verdict |
|---|---|---|
| `raw/` immuable | Les documents sources (« knowledge ») restent stockés tels quels (objet + chunks). Mais une mise à jour venant d'un connecteur **supprime puis recrée** la source (`datasource_service.go:1274`, « update = delete + re-create »). | **Transformé** : immuable tant qu'on ne resynchronise pas, sans historique des sources |
| `wiki/` markdown compilé par le LLM | Tables `wiki_pages` et `wiki_folders` en **base de données**, pas de fichiers. Six types de page : `summary`, `entity`, `concept`, `index`, `synthesis`, `comparison` (`internal/types/wiki_page.go:138-152`). Les liens sont en `[[slug\|nom]]`. Aucun export Markdown/Obsidian trouvé dans `internal/handler/wiki_page.go`. | **Présent mais en BDD**, donc pas lisible dans Obsidian |
| Schéma (AGENTS.md) | Les règles d'écriture sont figées dans des prompts Go (`internal/agent/prompts_wiki.go`). L'utilisateur ne peut qu'ajouter des « custom instructions » et choisir une granularité `focused/standard/exhaustive` (`prompts_wiki.go:538-569`). | **Transformé** : un schéma codé en dur, pas un fichier éditable |
| Ingest | Il est automatique et par lots (map/reduce), déclenché par la fin d'indexation (`knowledge_post_process.go:263`). Il retire aussi les contributions d'un document supprimé (`EnqueueWikiRetract`, `wiki_ingest.go:648`). | **Présent, industrialisé**, mais automatique |
| Query | Il n'y a pas de « query » qui réécrit le wiki. Le wiki sert de source boostée au RAG, et les pages `synthesis`/`comparison` ne naissent que par un agent via `wiki_write_page` (`types/wiki_page.go:148-152`). | **Partiel** : la boucle « une bonne réponse devient une page » existe côté agent |
| Lint | **100 % déterministe** : pages orphelines, liens brisés, contenu vide, références vers des sources supprimées, cross-refs manquants par recherche de titre dans le texte (`wiki_lint.go:17-22`, `126-240`). S'y ajoutent un autofix (`wiki_lint.go:346`) et un « health score » (`wiki_lint.go:270-300`). | **Présent, et exactement dans l'esprit K-B** |
| `index.md` | Une page `index` régénérée par LLM à chaque lot, dont seule l'intro est rédigée, le répertoire étant dérivé (`wiki_ingest.go:2207`). | Présent (en BDD) |
| `log.md` | Une table `wiki_log_entries` a été créée (`migrations/versioned/000040`), puis **supprimée** (`000077_remove_wiki_log.up.sql`) au profit du flux d'activité / audit (`website-docs/03-features/14-wiki.md`, section « 操作历史 »). S'y ajoutent des **révisions par page** (`wiki_page_revisions`, migration `000075`) avec source `pipeline/agent/user/revert`. | **Transformé** : historique par page et audit, plus de journal lisible |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Lint déterministe du wiki (orphelines, liens brisés, vides, sources disparues, cross-refs manquants) | Exactement la liste « déterministe d'abord » de K-B. Il n'y a qu'à la porter en Python sur des fichiers `.md`, et le check « titre mentionné mais non lié » est simple et efficace. | `internal/application/service/wiki_lint.go:17-22`, `:126-240` |
| Autofix prudent : `[[lien-mort]]` devient du texte brut, une page vide est **archivée** (pas supprimée), une source morte est retirée des refs | Des corrections scriptables sans LLM et réversibles, qui s'accordent avec notre statut porté par le frontmatter. | `wiki_lint.go:346-420` |
| Linkification déterministe : le premier mot reconnu devient `[[slug\|texte]]`, en ignorant le code et les liens existants, avec des frontières de mot | Maintient le graphe Obsidian sans appel LLM. | `internal/application/service/wiki_ingest.go` (injectCrossLinks l.1911) + `wiki_linkify.go:35` |
| Pré-filtre de dédup par similarité de surface (Jaccard / trigrammes, top-5) **avant** d'interroger le LLM, puis garde `validMerge` après | Le commentaire documente un vrai cas d'hallucination de fusion entre deux entités sans aucun caractère commun. C'est l'argument pour un dédup d'abord scripté. | `wiki_ingest_dedup.go:15-50`, `wiki_ingest.go:2573` |
| Prompt « compilateur » pour la mise à jour de page : rester au plus près du texte source, pas de remplissage, affirmations attribuées, et une section **« Contradictions / Updates »** quand une info nouvelle en contredit une ancienne | Réponse directe à notre problème de **péremption**, qu'on peut reprendre dans notre AGENTS.md. | `internal/agent/prompts_wiki.go:321-343` (règle 3 l.326) |
| Métadonnée `source_updated_at` / `source_created_at` distincte du `updated_at` technique | Le commentaire explique que l'`updated_at` de la ligne bouge à chaque re-parse. Pour dater une info de veille, il faut garder la date **de la source**. | `internal/application/service/datasource_service.go:1297-1307` |
| Connecteur RSS incrémental : ID = GUID, à défaut lien, à défaut titre ; empreinte du contenu ; curseur par flux ; échecs partiels tolérés (`PartialFetchError`) ; article complet extrait puis converti en Markdown | Un modèle direct pour notre collecteur RSS : dédup déterministe et resynchro idempotente. | `internal/datasource/connector/rss/connector.go:239-270`, `:277-284`, `:295-351` |
| Interface `Connector` commune (Validate / ListResources / FetchAll / FetchIncremental) + guide d'implémentation | Un bon gabarit pour nos sources multiples (RSS, GitHub releases, CVE, YouTube), et un argument « collecte multi-sources » pour la certification. | `internal/datasource/connector.go`, `internal/datasource/CONNECTOR_IMPLEMENTATION_GUIDE.md` |
| Révisions de page avec `edit_source` (pipeline/agent/user/revert), plafond souple de 50 qui purge d'abord les versions machine, plafond dur de 200 | Protège les corrections humaines contre la réécriture LLM. Chez nous, git joue ce rôle, mais l'idée « marquer qui a écrit » est à reprendre dans le frontmatter. | `internal/types/wiki_page.go:350-354`, `migrations/versioned/000075_wiki_page_revisions.up.sql` |
| SQLite FTS5 + BM25 en mode Lite, sans aucun service externe | Confirme que la recherche lexicale locale suffit pour démarrer, conformément à notre décision. | `internal/application/repository/retriever/sqlite/repository.go:62-80`, `:288-305` |
| OpenAPI généré et vérifié par un test de contrat en CI ; auth JWT + X-API-Key ; audit avec rétention | Des exemples concrets pour les critères « API REST documentée, authentifiée », « CI » et « journalisation/RGPD » de la certification. | `docs/swagger_contract_test.go`, `internal/middleware/auth.go:118`, `internal/application/service/audit_log_retention.go:14` |
| Couche fournisseurs LLM (~30 providers) derrière une interface `chat.Chat` | Confirme le choix « modèle interchangeable par config ». En Python, LiteLLM ou une interface maison mince fera le même travail. | `internal/models/providers/`, `internal/models/chat/chat.go` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Ingest wiki **automatique** dès la fin d'indexation | Contraire à notre décision « ingest unitaire déclenché par l'humain ». En plus, les coûts LLM explosent sur un flux de veille (chaque item RSS deviendrait des pages). | `internal/application/service/knowledge_post_process.go:263-268` |
| Wiki stocké en BDD (pages, dossiers, liens entrants/sortants dénormalisés) | Pas d'Obsidian, pas de diff git, pas de lecture hors appli. Notre wiki doit rester en fichiers `.md`. | `internal/types/wiki_page.go`, `migrations/versioned/000037_wiki_and_indexing.up.sql` |
| Schéma figé dans des constantes Go | On ne peut pas faire évoluer les règles sans recompiler. Chez K-B, le schéma est un fichier (AGENTS.md) versionné. | `internal/agent/prompts_wiki.go:10-597` |
| Mise à jour d'une source = suppression + recréation | Perd l'historique : impossible de répondre à « qu'est-ce qui a changé dans cette release/CVE ? ». Pour la veille, il faut des items datés **append-only** avec des versions. | `internal/application/service/datasource_service.go:1274`, `:1311-1330` |
| Date de la source rangée dans un JSON `metadata` libre, et `UpdatedAt` qui écrase `PublishedAt` pour le RSS | Impossible de filtrer proprement « cette semaine » en SQL, et on confond date de publication et date de modification. K-B a besoin de colonnes typées `published_at` / `fetched_at`. | `datasource_service.go:1302-1307`, `rss/connector.go:319-325` |
| « stale_ref » = source **supprimée**, pas info **périmée** | Le lint ne connaît aucune notion d'âge ou d'expiration. La péremption temporelle (CVE corrigée, version dépassée) n'est traitée nulle part. C'est justement le vide que K-B veut combler. | `wiki_lint.go:19`, `:198-222` |
| « Health score » arbitraire (-25, -10, -5×…) | C'est un score produit par le code, pas par le LLM, donc acceptable. Mais ses pondérations ne sont pas justifiées : mieux vaut exposer les comptes bruts. | `wiki_lint.go:270-300` |
| Boost fixe ×1,3 des pages wiki dans le RAG | Une heuristique magique qui favorise la synthèse LLM face à la source primaire. Pour la veille, la source datée doit primer. | `internal/application/service/chat_pipeline/wiki_boost.go:15` |
| Complexité d'infrastructure : Redis, asynq, verrous par slug, scripts Lua de réservation d'identité, file de lettres mortes | Justifiée pour du multi-tenant concurrent, c'est une sur-ingénierie pour un outil personnel à ingest unitaire. | `wiki_ingest.go:40-120` |
| Aucun connecteur GitHub releases, CVE/advisories, YouTube ou newsletter (seulement rss, notion, confluence, gitlab, feishu, yuque, dingtalk, ima) | Pour notre flux veille, seul le RSS se transpose. Le reste est à construire. | `internal/datasource/connector/` |

## 6. En une phrase

WeKnora montre qu'un wiki façon Karpathy tient en production et fournit à K-B trois pièces à recopier en Python sur des fichiers Markdown : un lint et un autofix entièrement déterministes, une linkification et un pré-dédup scriptés, et un prompt « compilateur » avec sa section « Contradictions / Updates ». Son wiki en base, son ingest automatique et l'absence de toute notion de péremption ou d'items de veille datés sont en revanche exactement ce que K-B doit faire autrement.
