# Fiche de veille — `akitaonrails/ai-memory`

Source : https://github.com/akitaonrails/ai-memory (clone `--depth 1`, lecture seule, rien exécuté).

## 1. Identité

- **Pitch** : un binaire Rust unique (serveur MCP + HTTP) qui donne une mémoire longue durée partagée aux agents de code (Claude Code, Codex, Cursor, Gemini CLI…). Il capture les événements des sessions par hooks et les compile en un wiki markdown « façon Karpathy » versionné dans git, indexé par SQLite (`docs/ARCHITECTURE.md:7-21`).
- **Pile technique** : Rust (13 crates dans `crates/`), SQLite en mode WAL avec FTS5, `git2` pour versionner le wiki, `notify` pour le watcher, LLM optionnel avec beaucoup de fournisseurs (`crates/ai-memory-llm/src/` : anthropic, openai, gemini, local, openai_compat, fallback…). Web intégré (`crates/ai-memory-web`).
- **Dernier commit** : `fbef4b6`, 2026-09-23 (le jour même de l'analyse). Le clone est superficiel, donc l'historique n'est pas visible, mais `CHANGELOG.md` fait 409 Ko.
- **Taille** : 763 fichiers hors `.git`, environ 167 000 lignes de Rust dans les `src/*.rs` des crates (compte `wc -l`).
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : très élevée, voire industrielle. Environ 3 470 tests (comptés par grep sur `#[test]` / `#[tokio::test]`, sans les lancer), une CI GitHub avec fmt, clippy `-D warnings`, tests, doctests, build Windows et release (`.github/workflows/ci.yml:28,39,73,77`), un scan de secrets (`secret-scan.yml`, `.gitleaks.toml`), plus de 70 documents dans `docs/`. Le projet est beaucoup plus gros et plus complexe que ce qu'il faut à K-B.

## 2. Architecture

```
crates/
  ai-memory-core/        types de domaine, sanitizer de secrets, conformité OKF
  ai-memory-hooks/       routeur des événements de hooks → observations ; log mensuel
  ai-memory-store/       SQLite : writer actor, reader pool, FTS5, décroissance, belief
  ai-memory-wiki/        pages markdown + git + watcher (Obsidian/vim) + migrations
  ai-memory-consolidate/ consolidation LLM, lint, sweep de décroissance, auto-improve
  ai-memory-mcp/         serveur MCP (23 outils) + API admin
  ai-memory-llm/         fournisseurs LLM interchangeables + embeddings + reranker
  ai-memory-web/         navigateur web du wiki + API JSON /api/v1
  ai-memory-cli/         binaire `ai-memory` (serve, hook, install…)
hooks/<agent>/           scripts de hooks par agent (claude-code, codex, cursor…)
companions/ai-memory-importer/  import hors cœur (wiki OMC, conversations exportées)
docs/research-*.md       notes de veille sur la concurrence (voir §2 bis)
```

**Flux principal** (`docs/ARCHITECTURE.md:43-120`) :
1. L'agent émet un hook (SessionStart, PostToolUse…), envoyé à `POST /hook` ou mis en file localement.
2. Le routeur **assainit** le payload (seule entrée du texte non fiable), le classe en `ObservationKind` et l'écrit dans SQLite. Une ligne est ajoutée au journal `log-YYYY-MM.md` (`crates/ai-memory-hooks/src/log.rs:1-6,45-58`).
3. À la fin de session, une page `sessions/<id>.md` est **synthétisée par des règles, sans LLM**. Le wiki est auto-commité.
4. Si un LLM est configuré, `memory_consolidate` réécrit la session en **1 à 5 pages** durables sous `concepts/`, `decisions/` ou `gotchas/` (`crates/ai-memory-consolidate/prompts/batch_consolidate_system.md:1-3`).
5. `memory_query` interroge FTS5, les entités et les voisins de liens, fusionnés par RRF, avec des vecteurs en option (`docs/ARCHITECTURE.md` §Data flow, point 6).
6. Un watcher réindexe les modifications externes, par exemple faites dans Obsidian : événements avec debounce de 300 ms, plus un passage de réconciliation toutes les 30 s. Il n'écrit jamais sur le disque (`crates/ai-memory-wiki/src/watcher.rs:1-19,35-38`).

**Stockage** : le markdown est la source de vérité ; SQLite n'est qu'un index dérivé (`docs/ARCHITECTURE.md:257-266`). Pages versionnées par supersession (`is_latest` + chaîne `supersedes`), tiers de mémoire working / episodic / semantic / procedural avec décroissance exponentielle (`docs/ARCHITECTURE.md` §Memory tiers).

## 2 bis. La note `docs/research-karpathy-llm-wiki.md` (citée par Sabine)

C'est une note de 112 lignes, datée de mai 2026 d'après la note de suivi. Elle fait trois choses.

1. **Elle restitue le gist en séparant ce qu'il dit de ce qu'on lui prête** (§1-2, l.11-53). Principes retenus : compiler plutôt que récupérer ; trois couches (raw immuable, wiki possédé par le LLM, schéma CLAUDE.md/AGENTS.md) ; trois opérations (ingest qui touche 10 à 15 pages, query dont les bonnes réponses sont refilées au wiki, lint) ; les liens croisés sont la synthèse ; `index.md` et `log.md` avec le préfixe grep-able `## [date]`. Point précieux pour K-B (l.46-53) : les tiers épisodique/sémantique, la consolidation « sommeil », les **scores de confiance**, la décroissance d'Ebbinghaus et la supersession **ne viennent pas de Karpathy**. Ils viennent de « LLM Wiki v2 » (Rohit Ghumare). Autres indices d'implémentation (l.57-61) : ingestion manuelle une source à la fois ; `index.md` suffit jusqu'à environ 100 sources et quelques centaines de pages, sans embeddings ; au-delà, recherche hybride locale (`qmd` : BM25 + vecteur + re-rank).
2. **Elle compare les approches voisines** (§4, l.63-70) :

| Approche | Idée | Verdict implicite |
|---|---|---|
| MemGPT/Letta | l'agent pagine lui-même sa mémoire (core/recall/archival) | fort sur la cohérence long terme, mais enferme (possède la boucle agent) |
| Mem0 | couche légère extract/store/retrieve, extraction passive | peu d'enfermement, mais des faits atomiques |
| A-MEM (NeurIPS 2025) | notes atomiques Zettelkasten, liens automatiques, évolution des notes | l'analogue de recherche le plus proche de Karpathy |
| ReadAgent | arbre de résumés « gist » avec pointeurs vers le détail | même instinct « compiler, pas re-récupérer » |
| LLM Wiki v2 | confiance, supersession, décroissance, 4 tiers, hooks | « c'est en gros le modèle agentmemory » |
| Rowboat | graphe d'entités typées (décisions, personnes, projets) | le wiki de résumés casse sur les contextes qui évoluent |

3. **Elle en tire une conception** (§5, l.72-94). Markdown dans git comme vérité ; `raw/`, `wiki/` et schéma imposés par le serveur ; outils MCP calqués sur ingest/query/lint ; ingest pensé comme une écriture en éventail ; `index.md` et `log.md` comme fichiers de premier rang ; récupération hiérarchique (index, puis pages, puis hybride BM25 + vecteur en secours). **Tension reconnue** (l.94) : le gist vise des wikis de recherche curés par un humain, alors qu'un agent de code ingère en continu et sans supervision. Il faut donc ajouter la couche de cycle de vie de LLM Wiki v2 (décroissance, supersession, confiance), sinon le wiki se remplit d'observations périmées.

**La note de suivi `docs/research-2026-landscape.md`** (sept. 2026, 762 lignes) apporte les conclusions actuelles :
- Google Cloud a publié l'**Open Knowledge Format (OKF) v0.1** le 12 juin 2026 : un répertoire de markdown avec frontmatter YAML, un concept par fichier, un seul champ obligatoire `type`. Le document le présente comme la formalisation du gist (l.12-26). Le code l'a adopté (`crates/ai-memory-core/src/okf.rs:175-180`, migration `m2026_09_okf_conformance.rs`).
- Letta publie « Is a Filesystem All You Need? » : des fichiers bruts obtiennent 74 % sur LOCOMO (l.28-36).
- **mempalace** sert de contre-exemple : son 96,6 % R@5 se reproduisait avec ChromaDB par défaut, architecture désactivée. Leçon : une métaphore n'est pas une architecture de récupération, et les étoiles GitHub ne mesurent pas le fond (l.58-68).
- L'article TriMem (arXiv:2605.19952) soutient les pages plutôt que les faits atomiques (l.479-487). La validité bi-temporelle de Zep/Graphiti distingue le temps de l'événement et le temps d'ingestion (l.503-510).
- Recommandations classées R1 à R8 (l.516-640) : conformité OKF ; harnais d'évaluation reproductible avant de publier le moindre chiffre ; arêtes typées `causes`/`fixes`/`contradicts` ; validité temporelle sur les liens ; passe d'abstraction inter-sessions ; embeddings locaux ONNX ; niveaux L0/L1/L2 de divulgation progressive ; filtres par métadonnées/tags. **Explicitement écartés** (l.642-647) : l'agent qui édite lui-même sa mémoire, la base graphe, les architectures à métaphore, publier un benchmark sans harnais, et la course au nombre d'outils.

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans ai-memory | Constat |
|---|---|---|
| `raw/` immuable | **Transformé** | `raw/` ne contient que des segments JSONL de workstreams (`docs/ARCHITECTURE.md:266-268`). Les « sources » sont des observations de hooks stockées en SQLite, pas des documents. |
| `wiki/` compilé par le LLM | Présent | Markdown + git ; mais la page de session est générée par des règles, et le LLM n'intervient qu'en option. |
| Schéma (AGENTS.md) | Transformé | Un « routing snippet » injecté dans le CLAUDE.md/AGENTS.md de l'utilisateur pour router l'agent vers le serveur (`crates/ai-memory-core/src/routing_snippet.rs:1-12`) ; les conventions de pages vivent dans les prompts (`crates/ai-memory-consolidate/prompts/`). |
| Ingest | **Transformé** | Aucun outil `memory_ingest` : l'ingestion est **automatique** par hooks, puis consolidation LLM (1 à 5 pages, pas 10 à 15). C'est l'inverse de l'ingest manuel de Karpathy et de K-B. |
| Query | Présent | `memory_query` : FTS5 + entités + voisins + RRF (+ vecteurs). Pas de mécanisme vérifié pour refiler les réponses au wiki. |
| Lint | Présent, partiel | Règles sans LLM : périmé, vide, doublon de titre, lien inter-projets brisé, feedback, pin expirant. Contradictions via LLM en option ou bande de similarité cosinus (`crates/ai-memory-consolidate/src/lint.rs:1-14,222,361,442`). **Pas de détection d'orphelins, et les liens brisés ne sont signalés qu'entre projets** : la requête filtre `l.to_project IS NOT NULL` (`crates/ai-memory-store/src/reader.rs:7081`). |
| `index.md` | Transformé | Non maintenu comme catalogue vivant. Il est régénéré seulement à l'export OKF, sous forme de liste des familles de dossiers (`crates/ai-memory-mcp/src/admin.rs:985-998`). La navigation passe par SQLite. |
| `log.md` | Présent, transformé | Journal append-only au préfixe exact `## [YYYY-MM-DDTHH:MM:SSZ] event \| titre`, **découpé par mois** (`log-YYYY-MM.md`) (`crates/ai-memory-hooks/src/log.rs:1-16`). |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| La note de recherche qui sépare Karpathy de ses extensions | Elle justifie « pas de scores de confiance LLM » : ce n'est pas dans le gist | `docs/research-karpathy-llm-wiki.md:46-53` |
| Markdown = vérité, SQLite = index dérivé reconstructible | C'est exactement la règle de K-B pour Obsidian ; l'index se reconstruit depuis les fichiers | `docs/ARCHITECTURE.md:257-266`, `crates/ai-memory-wiki/src/wiki.rs:1641` (`reindex_all`) |
| FTS5 `unicode61 remove_diacritics 2` + triggers de synchro | Recherche lexicale d'abord ; « securite » trouve « sécurité » (FR/EN) | `crates/ai-memory-store/migrations/V17__pages_fts_index_path.sql:32-37`, `V12__fts_remove_diacritics.sql:1-8` |
| Requête naturelle en `OR` + bm25 au lieu du `AND` par défaut | Sans ça, le rappel est quasi nul sur les questions en langage naturel | `crates/ai-memory-store/src/fts_query.rs:14-20` |
| Chemin de la page indexé dans FTS | Retrouver une fiche par son slug | `crates/ai-memory-store/migrations/V17__pages_fts_index_path.sql:1-15` |
| Log mensuel au préfixe `## [ts] event \| titre` | Journal grep-able qui ne grossit pas indéfiniment ; bon modèle pour `log.md` | `crates/ai-memory-hooks/src/log.rs:1-16` |
| Watcher avec debounce et réconciliation périodique, qui n'écrit jamais | Prend en compte les modifications faites dans Obsidian et rattrape les événements perdus par FSEvents | `crates/ai-memory-wiki/src/watcher.rs:1-19` |
| Court-circuit par sha256 du corps | Réindexation idempotente déterministe, base pour la dédup de contenu | `crates/ai-memory-store/src/ops.rs:178` |
| Lint déterministe d'abord, LLM en option | Aligné avec « déterministe d'abord » ; rapport écrit en markdown dans `_lint/report.md`, versionné | `crates/ai-memory-consolidate/src/lint.rs:1-14` |
| Prompt « FAITHFULNESS » et frontière de sécurité | Modèle de prompt d'ingest : rien d'inventé (dates, versions, CVE), les sources sont des données et non des instructions | `crates/ai-memory-consolidate/prompts/batch_consolidate_system.md:5-50` |
| Sanitizer de secrets avec type `Sanitized<T>` | Masque les clés API et tokens avant stockage ; utile pour les newsletters et le point RGPD | `crates/ai-memory-core/src/sanitize.rs:1-25` |
| Confiance calculée au moment de la lecture, sans LLM, à partir des preuves | Si K-B veut un jour pondérer, il le fait par calcul (sessions distinctes, récence), pas par une note du LLM | `crates/ai-memory-store/src/belief.rs:1-25` |
| Frontmatter minimal `type` (OKF) et familles de dossiers qui correspondent à un type | Recoupe « wiki découpé par type de page » ; compatibilité avec un format standard | `crates/ai-memory-core/src/okf.rs:175-200` |
| Validité bi-temporelle (événement / ingestion) | Répond directement à la **péremption** de la veille (CVE, versions) | `docs/research-2026-landscape.md:503-510` |
| `DATA_HANDLING.md` (local par défaut, RGPD, suppression/rétention) | Modèle de section RGPD pour la certification | `DATA_HANDLING.md` (§ « Is this personal data under GDPR? ») |
| CI fmt + lint strict + tests + scan de secrets | Modèle de CI transposable en Python (ruff, pytest, gitleaks) | `.github/workflows/ci.yml:28-77`, `.gitleaks.toml` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Ingestion automatique par hooks, sans supervision | K-B a décidé un ingest unitaire déclenché par l'humain ; la note elle-même reconnaît que ça remplit le wiki d'observations de faible valeur | `docs/research-karpathy-llm-wiki.md:94`, `docs/ARCHITECTURE.md:43-60` |
| Auto-improve qui **approuve par défaut** les propositions LLM dans le wiki | Contraire au contrôle humain ; il faut `require_approval = true` pour l'éviter | `docs/ARCHITECTURE.md:29-35` |
| Tiers de mémoire, décroissance exponentielle, éviction, « dream pass » | C'est la mémoire d'un agent de code, pas un wiki de veille ; la péremption doit reposer sur des dates explicites (publication, version), pas sur des formules d'accès | `docs/ARCHITECTURE.md` §Memory tiers |
| Pas de vrai `index.md` catalogue | K-B veut un `index.md` lisible dans Obsidian ; ici tout passe par SQLite et MCP | `crates/ai-memory-mcp/src/admin.rs:950-998` |
| Lint sans orphelins, et liens brisés seulement entre projets | Il faudra écrire ces contrôles déterministes nous-mêmes | `crates/ai-memory-consolidate/src/lint.rs:40`, `crates/ai-memory-store/src/reader.rs:7081` |
| Stopwords codés en dur, en anglais seulement | Contenu FR/EN : il faut une liste par langue | `crates/ai-memory-store/src/fts_query.rs:119-139` |
| Taille et complexité (≈167 k lignes Rust, 23 outils MCP, multi-utilisateur, SSO, webhooks) | Rust, hors de notre pile Python ; aucun morceau n'est réutilisable tel quel. On garde les idées, pas le code | `crates/*/src` (`wc -l`), `docs/ARCHITECTURE.md:419` |
| Pas d'OpenAPI | L'API REST `/api/v1` existe, avec des classes d'authentification propres, mais aucune spécification OpenAPI trouvée (grep `openapi`/`utoipa` sans résultat utile) : pas de modèle pour ce critère de certification | `docs/ARCHITECTURE.md:500-516`, `crates/ai-memory-web/src/routes/api.rs` |
| Aucune notion de veille | Pas de collecte RSS, newsletters, releases ou CVE, pas de question « quoi de neuf cette semaine » ; seulement des sessions d'agents | ensemble du dépôt (constat par absence) |

## 6. En une phrase

K-B retient la **doctrine** plus que le code : la note de recherche (ce qui est vraiment dans le gist de Karpathy et ce qui n'y est pas) et quelques motifs déterministes éprouvés (markdown source de vérité + index SQLite FTS5 insensible aux accents, recherche en `OR`/bm25, log mensuel grep-able, watcher réconciliateur, sanitizer, lint sans LLM, prompt de fidélité). En revanche, K-B rejette l'ingestion automatique, l'auto-approbation et la mémoire à décroissance, qui répondent à un autre problème : la mémoire d'agents de code.

---
*Non vérifié* : le comportement réel à l'exécution (rien lancé) ; le nombre de tests est un comptage par grep ; l'historique git n'est pas disponible (clone superficiel).
