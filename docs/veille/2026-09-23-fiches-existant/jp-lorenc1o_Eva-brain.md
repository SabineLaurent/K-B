# Fiche de veille — `jp-lorenc1o/Eva-brain`

Dépôt : https://github.com/jp-lorenc1o/Eva-brain — clone `--depth 1`, commit `706fb91` (lecture seule, rien exécuté).

## 1. Identité

- **Pitch** : application desktop macOS (Tauri) « local-first » qui fait entretenir par un agent CLI (Claude Code, Codex ou OpenCode + Ollama local) un wiki Markdown lié, à partir de sources déposées dans `raw/`. C'est une implémentation fidèle et outillée du pattern Karpathy, dont l'apport majeur est une **porte de revue Git** : l'agent travaille dans un worktree isolé, et un lint déterministe décide si on fusionne automatiquement ou si on attend l'humain.
- **Pile** : Rust (Tauri v2, `apps/desktop/src-tauri/src/ingest.rs`, 4 854 lignes, quasiment tout le métier), TypeScript (`packages/wiki-lib` : parsing/graphe/lint ; `apps/desktop/src/main.ts`, 3 887 lignes d'UI graphe), Node (`packages/eva-mcp` : serveur MCP en lecture seule + CLI de lint). **Aucun Python.**
- **Dernier commit** : 29 juillet 2026 (merge PR #2 « restrictive CSP »).
- **Taille** : 127 fichiers, dont environ 50 icônes et assets marketing ; le code utile tient en une dizaine de fichiers.
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : tests réels — 39 `#[test]` Rust dans `ingest.rs` (dont la porte de revue, p. ex. `opencode_style_deletion_is_held_by_the_shared_gate`, `ingest.rs:4644`), 17 tests vitest dans `packages/wiki-lib/test/wiki-lib.test.ts`, avec un vault de test de 16 pages. **Mais la CI ne lance pas les tests** : `.github/workflows/release.yml` se déclenche seulement sur un tag `v*.*.*`, fait un build et vérifie la présence des fichiers (`release.yml:64-69`). Pas de CI sur PR. Doc soignée : `docs/EVA_BRAIN_STANDARD.md` (spec versionnée), `AGENTS.md` (décisions et contraintes explicites). Projet personnel avec un seul auteur principal, V1 limitée à macOS et non signée, par choix assumé (`AGENTS.md:1-15`).

## 2. Architecture

```text
schema/                 EVA.md (contrat agent, inclus dans le binaire), AGENTS.md, CLAUDE.md, eva.json
templates/vault/        index.md et log.md de départ
packages/wiki-lib/src/  parse.ts (frontmatter + [[liens]]), vault.ts (résolution de liens), graph.ts, lint.ts
packages/eva-mcp/       server.mjs (MCP lecture seule : search, read_page, neighbors, shortest_path)
                        lint-cli.mjs (lint JSON appelé par Rust), vault-io.mjs (chargement, exclusions)
apps/desktop/src-tauri/src/ingest.rs   orchestration : brains, runtimes, ingest, query, health, porte de revue
apps/desktop/src/main.ts               UI : graphe, file d'ingest, revue de diff, i18n
docs/EVA_BRAIN_STANDARD.md             spec du format « Eva brain » v1
```

**Flux ingest** (du dépôt à la fusion) :
1. `ingest_enqueue` (`ingest.rs:4682`) copie les fichiers choisis dans `raw/` **par nom de fichier** (et ignore un fichier du même nom déjà présent, `ingest.rs:4706`), **puis ajoute aussi tout fichier de `raw/` jamais ingéré** (`ingest.rs:4711-4722`). Un fichier est considéré comme déjà ingéré si son nom apparaît dans `log.md` (`ingest.rs:4726-4727`). Les fichiers sont triés par nom, puis `git commit` « raw: add … ».
2. `run_job` (`ingest.rs:3130`) : lint du vault **avant** l'ingest, création d'une branche `ingest/<slug>`, puis d'un worktree Git dans `$TMPDIR`.
3. `drive_agent` lance le CLI de l'agent avec un prompt fixe (`ingest.rs:1920-1930` : lire EVA.md, lire `raw/<source>`, *chercher avant de créer*, fusionner plutôt que dupliquer, provenance, ne pas toucher raw/infra ni git). Les outils sont restreints par `--allowedTools` (`ingest.rs:1948`), et le serveur MCP d'Eva est exposé en lecture seule.
4. `gate_agent_changes` (`ingest.rs:3209-3270`) : vérification de la frontière d'écriture (`verify_agent_write_boundary`, `ingest.rs:1881`, sur `git status` et `git diff base..HEAD` des chemins protégés `raw`, `eva.json`, `EVA.md`, `AGENTS.md`, `CLAUDE.md`, `log.md`), commit agent, ajout d'une entrée `log.md` par Eva (pas par l'agent), lint **après**, puis comparaison : **aucune suppression et aucun nouveau problème de lint → merge `--no-ff` automatique ; sinon → `Held`** avec le patch, les nouveaux problèmes et les suppressions, pour décision humaine (`ingest_decide`, `ingest.rs:4779`). Les renommages sont comptés comme suppressions (`--no-renames`, `ingest.rs:3193`).

**Query** : l'agent répond en JSON `{answer, citations[{page, sources}]}` (`ingest.rs:2072`). La sauvegarde en page `analysis` est générée par du code Rust (`analysis_markdown`, `ingest.rs:3369`), puis passe par la même comparaison de lint : une citation vers une page inexistante devient un `broken-link` et bloque la fusion.

**Health** : le lint déterministe, plus une passe agent **en lecture seule** qui renvoie des constats typés (`contradiction`, `provenance`, `stale-claim`, `coverage-gap`, `research-question`) suivant un schéma JSON strict (`ingest.rs:2176-2181`, `codex_health_schema`, `ingest.rs:2585`).

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Eva | Commentaire |
| --- | --- | --- |
| `raw/` immuable | **Présent et imposé par le code** | La consigne du prompt est vérifiée ensuite par Git (`ingest.rs:1866-1896`) ; c'est le point le plus solide du dépôt. |
| `wiki/` compilé | Présent, découpé par **type** : `entities/`, `concepts/`, `summaries/`, `analyses/` | Même choix que K-B (découpage par type de page). Les thèmes passent par des « profils » et non par des tags. |
| Schéma (AGENTS.md) | `EVA.md`, avec `AGENTS.md`/`CLAUDE.md` réduits à des renvois | Les pointeurs pour chaque agent sont un bon pattern. Le schéma est versionné par `eva.json` (`docs/EVA_BRAIN_STANDARD.md:11-33`). |
| ingest | Présent, un worktree par source | Dédup et reprise par nom de fichier (voir §5). |
| query | Présent, citations structurées | Pas de requête temporelle (le projet ne fait pas de veille). |
| lint | **Transformé en porte de merge** | Il ne sert pas seulement de rapport : c'est un **diff avant/après** qui décide de la fusion. Le lint sémantique reste une option et ne peut rien écrire. |
| `index.md` | Présent, maintenu par l'agent | `templates/vault/index.md` |
| `log.md` append-only | Présent, **écrit par Eva et jamais par l'agent** | Format `## [YYYY-MM-DD] op \| sujet` (`ingest.rs:1815-1826`). Détourné en registre des sources ingérées. |
| Obsidian | Compatible (liens `[[ ]]`), mais l'UI propre est un graphe Tauri | |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
| --- | --- | --- |
| Porte de revue = lint **avant/après** : on fusionne automatiquement seulement si aucun nouveau problème et aucune suppression | Principe « déterministe d'abord » appliqué à la sortie du LLM. Le lint devient un critère d'acceptation, pas une option. Transposable en Python (état initial, ingest, comparaison des ensembles de problèmes). | `apps/desktop/src-tauri/src/ingest.rs:3209-3270` |
| Frontière d'écriture vérifiée **après coup** par Git, pas seulement demandée dans le prompt (« Prompts are instructions, not an access boundary ») | Garantit l'immuabilité de `raw/` et du schéma même si le LLM désobéit, y compris s'il a lancé `git commit` lui-même. | `ingest.rs:1866-1896` |
| Renommage = suppression + ajout (`--no-renames`) : les suppressions ne fusionnent jamais automatiquement | Une page renommée casse les liens entrants d'Obsidian ; bon garde-fou pour un wiki long terme. | `ingest.rs:3188-3207` |
| Règles de lint `missing-source` / `invalid-source` : un `summary` doit pointer vers `raw/…` | Provenance vérifiable par script. À reprendre pour nos pages de source. | `packages/wiki-lib/src/lint.ts:100-115` |
| Règle `misplaced-page` : détecte les chemins absolus hallucinés (`private/var/…`, `Users/…`) recréés dans le vault | Défaut réel observé chez les agents ; règle déterministe peu coûteuse. | `packages/wiki-lib/src/lint.ts:13-32, 61-69` |
| `log.md` écrit par le code, pas par le LLM ; format d'en-tête `## [date] op \| sujet` facile à analyser | Journal fiable et analysable avec grep. Également utile pour la certification (journalisation). | `ingest.rs:1815-1826`, `templates/vault/log.md` |
| Page `analysis` **générée par le code** à partir d'un JSON `{answer, citations}` validé par schéma ; une citation inventée devient un `broken-link` et bloque la fusion | Utiliser le lint pour vérifier les citations, sans score de confiance produit par le LLM (conforme à nos décisions). | `ingest.rs:3369-3420`, `ingest.rs:2072` |
| Health sémantique **en lecture seule**, catégories fermées, `pages` obligatoires, « Do not use general-world knowledge to call a claim stale » | Bon cadrage pour un futur lint de péremption assisté par LLM : il propose, il n'écrit pas. | `ingest.rs:2174-2182`, `ingest.rs:2585-2609` |
| Schéma versionné (`eva.json` : `format`, `version`) avec refus d'opérer sur une version inconnue | Permet de faire évoluer le format du wiki K-B sans corrompre un vault ancien. | `docs/EVA_BRAIN_STANDARD.md:11-40` |
| `AGENTS.md` / `CLAUDE.md` réduits à un renvoi vers le contrat unique | Une seule source de vérité, quel que soit l'agent : modèle interchangeable. | `schema/AGENTS.md`, `schema/CLAUDE.md` |
| Serveur MCP **en lecture seule** (`search`, `read_page`, `neighbors`, `shortest_path`), rechargé à chaque appel | La recherche lexicale suffit (cohérent avec « lexical d'abord »). Obliger à « chercher avant de créer » réduit les doublons. | `packages/eva-mcp/server.mjs:1-51` |
| `AGENTS.md` du dépôt qui documente les décisions et l'interdiction de les « corriger » (macOS seul, non signé, modèle local et `num_ctx`) | Bonne pratique à reprendre dans le CLAUDE.md de K-B, en complément des ADR. | `AGENTS.md:1-59` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
| --- | --- | --- |
| « Déjà ingéré » = le nom du fichier apparaît comme **sous-chaîne** de `log.md` | Fragile : `a.md` est trouvé dans n'importe quelle entrée qui le contient, et une réécriture du log fait tout réingérer. K-B doit dédupliquer par URL ou hash et stocker le statut dans le frontmatter ou en base. | `ingest.rs:4726-4727` |
| Dépôt dans `raw/` par nom : un nouveau fichier **du même nom** est ignoré silencieusement | Perte silencieuse d'une nouvelle version de source (grave pour la veille : releases, CVE mises à jour). | `ingest.rs:4705-4707` |
| Chaque enqueue **ramasse tous les fichiers non ingérés** de `raw/` | Contraire à notre décision « ingest unitaire déclenché par l'humain » : on ne choisit pas une source, on vide la file. | `ingest.rs:4711-4722` |
| Parseur de frontmatter « à plat » (`key: value`), YAML imbriqué et listes non gérés | Nos thèmes sont des **tags** (listes YAML) : ce parseur les ignorerait. En Python, il faut un vrai parseur YAML. | `packages/wiki-lib/src/parse.ts:28-41` |
| Péremption confiée uniquement à l'agent (`stale-claim`), aucune règle déterministe sur `updated` (qui est seulement « strongly recommended ») | K-B a besoin d'une péremption calculée : date `updated` ou `valid_until` obligatoire selon le type, alerte par script. | `schema/EVA.md:66`, `ingest.rs:2176` |
| Pas de flux de veille : ni collecte, ni base datée, ni requête temporelle | Eva couvre seulement notre flux 2 (dépôt manuel vers wiki). Rien pour le flux 1. | ensemble du dépôt (aucun collecteur) |
| Tout le métier dans un fichier Rust de 4 854 lignes, avec lint et MCP en Node : **deux runtimes obligatoires** | Hors de notre pile Python ; illustration de ce qu'il ne faut pas faire (un seul langage, des modules séparés). | `apps/desktop/src-tauri/src/ingest.rs`, `README.md` (section « Node.js is a hard runtime dependency ») |
| Pas d'appel API : l'inférence passe par des **CLI d'agents** (`claude -p`, `codex`, `opencode`) pilotés en sous-processus | K-B veut une API avec un modèle interchangeable par config. Piloter des CLI ajoute de la fragilité (versions d'Ollama cassées, `AGENTS.md:40-59`). | `ingest.rs:1941-1953`, `AGENTS.md:40-59` |
| Fusion automatique quand le lint est vert : les modifications de contenu (réécriture d'une affirmation) passent sans relecture | Le lint structurel ne voit pas une modification sémantique erronée. Pour K-B, au minimum journaliser le diff ou exposer le dernier ingest à la relecture. | `ingest.rs:3244-3257` |
| Aucune CI sur PR (les tests existent mais ne tournent pas en CI) | À ne pas reproduire : la certification demande une CI qui teste. | `.github/workflows/release.yml:19-21` |

## 6. En une phrase

Eva est la meilleure implémentation « défensive » du pattern Karpathy vue jusqu'ici : K-B doit lui prendre l'idée du **lint avant/après comme porte de fusion** et de la **frontière d'écriture vérifiée par Git après l'agent**, et laisser de côté sa dédup par nom de fichier, son frontmatter à plat et son absence totale de veille et de péremption déterministe.
