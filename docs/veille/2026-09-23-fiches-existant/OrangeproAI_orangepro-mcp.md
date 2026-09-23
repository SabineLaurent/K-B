# Fiche de veille — OrangeproAI/orangepro-mcp

> Analysé le 2026-09-23, clone `--depth 1` (commit `e4c4b38`, « chore: release v0.2.44 », 2026-09-21). Lecture seule, aucun code exécuté.
> **Hors sujet direct** : ce n'est ni un wiki LLM, ni un outil de veille, ni de la recherche documentaire. C'est un outil d'**analyse de couverture de tests** pour dépôts de code. Son intérêt pour K-B tient à quelques briques transversales (fraîcheur par hash, propagation de péremption, validation déterministe des citations produites par un LLM, étiquetage de la provenance IA).

## 1. Identité

- **Pitch** : « OrangePro » cartographie les comportements publics d'une base de code, leur attribue un niveau de preuve (de « No Signal » à « Dynamically Proven » par mutation) et génère des tests « ancrés » via un LLM en BYOK. Le même dépôt contient aussi un serveur MCP qui expose une plateforme hébergée (agents, analytics QA), sans code partagé avec l'outil local (`CLAUDE.md:7-11`).
- **Pile** : TypeScript / Node 20, `@modelcontextprotocol/sdk` (McpServer), tree-sitter pour l'analyse, vitest. Aucun Python côté produit (seulement des scripts de mutation Python/Go/Java dans `scripts/spikes/`).
- **Dernier commit** : 2026-09-21 (v0.2.44).
- **Volume** : 808 fichiers ; environ 42 000 lignes de TS dans `src/` (hors fixtures) ; `src/local/operations.ts` fait à lui seul 3 193 lignes.
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : élevée côté ingénierie. 164 fichiers de tests vitest (`tests/`, `tests/local/`), CI GitHub Actions en jobs parallèles, dont un gate « privacy » (`.github/workflows/ci.yml:1-5`, `:37-48`), doc mainteneur (`docs/maintainers.md`), publication npm + MCP Registry (`server.json`, `glama.json`). Produit commercial avec une partie hébergée fermée : l'outil MCP « hosted » (`src/server.ts`) ne fonctionne pas sans leur backend.

## 2. Architecture

```
src/
  index.ts, server.ts, apiClient.ts, config.ts   — MCP « hosted » : proxy HTTP vers le backend OrangePro (fermé)
  orangeproTools.ts, qaTools.ts                  — handlers des outils hébergés (agents, analytics QA)
  local/                                         — le vrai produit livré (bin `opro`)
    cli.ts (1 539 l.), mcp.ts (703 l.)           — CLI + serveur MCP local (18 outils orangepro_*)
    operations.ts (3 193 l.)                     — orchestration : analyze, update, prove, export…
    analyze/                                     — analyse statique (tree-sitter, liens tests↔code)
    enrich/ csv.ts, markdown.ts                  — ingestion de documents d'exigences fournis par l'humain
    graph/ ontology.ts, factories.ts, citations.ts — modèle de graphe + validation des citations
    freshness/ manifest.ts, status.ts, changed.ts — fraîcheur : manifeste de hash, diff, impact
    aiGraph/links.ts, flows/llmFlowDiscovery.ts  — voies LLM (suggestions « faibles »)
    generate/ providers.ts, prompt*.ts           — génération de tests, adaptateurs LLM
    ledger.ts, provenance.ts                     — journal des exécutions / preuves
    pack/                                        — export « metadata-only » (evidence pack)
    telemetry.ts                                 — ping d'usage anonyme
    util/ hash.ts, redact.ts, walk.ts            — sha256, masquage de secrets, parcours
infra/telemetry-worker/                          — Cloudflare Worker + schema.sql pour la télémétrie
```

**Flux principal (local)** : `opro start .` → parcours du dépôt en respectant `.orangeproignore` (`src/local/workspace.ts:36-45`) → analyse statique + enrichers CSV/Markdown → graphe sérialisé en **un seul `.orangepro/graph.json`** (`src/local/workspace.ts:6-8`, `saveGraph` dans `src/local/operations.ts:1156`) avec un manifeste de hash par fichier → score, rapport HTML, éventuellement génération de tests par LLM → preuve par mutation → journal `ledger.json` (`src/local/ledger.ts:7-8`) → export d'un « evidence pack » ne contenant que des métadonnées.

**Mise à jour incrémentale** (`opro update`, `incrementalMerge` dans `src/local/operations.ts:3003-3055`) : le rescan remplace les nœuds produits par l'analyseur, **préserve les nœuds manuels/enrichers** (filtrés par `source_scope_id`, `:3020`), marque `stale: true` les nœuds disparus (`:3023-3025`) et **tout artefact généré dont l'ancrage touche un fichier modifié** (`:3043-3050`).

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Présent ? | Commentaire |
|---|---|---|
| `raw/` immuable | Transformé | La « source brute » est le dépôt de code du client, jamais modifié. Chaque fichier est haché (sha256, `src/local/util/hash.ts:5-15`) dans un manifeste (`src/local/freshness/manifest.ts:34-44`). |
| `wiki/` markdown compilé | **Absent** | La connaissance dérivée est un graphe JSON (`graph.json`), pas du markdown lisible. Le seul rendu humain est un rapport HTML généré. |
| Schéma (AGENTS.md) | Partiel | Un `CLAUDE.md` pour les contributeurs et une ontologie typée (`src/local/graph/ontology.ts:30-57`) qui fait office de schéma, mais ce n'est pas un document de consignes pour un LLM mainteneur. |
| ingest | Transformé | `analyze` + enrichers CSV/Markdown (`src/local/enrich/markdown.ts:115-145`), déterministes. Le LLM n'intervient pas dans l'ingestion. |
| query | Transformé | Outils MCP (`orangepro_explain_test`, `orangepro_find_test_gaps`, `orangepro_changed_impact`…, `src/local/mcp.ts:63-662`), pas de question-réponse en langage naturel. |
| lint | **Présent en esprit, et c'est le plus intéressant** | `status` fresh/stale/missing (`src/local/freshness/status.ts:17-41`), `doctor`, validation des citations (`src/local/graph/citations.ts:1-22`). Tout est déterministe. |
| `index.md` / `log.md` | Transformé | Pas d'index markdown. `ledger.json` joue le rôle de journal des exécutions, en ajoutant l'entrée à un tableau puis en réécrivant tout le JSON (`src/local/ledger.ts:141-143`) : il n'est pas append-only sur disque. |
| Obsidian | Absent | — |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Manifeste de fraîcheur `{hash, size, kind}` par fichier + état `missing / fresh / stale` calculé par diff ajout/suppression/modification | Détecter sans LLM qu'un document de `raw/` (ou un item de veille) a changé depuis la dernière compilation du wiki. Le script fait moins de 50 lignes. | `src/local/freshness/status.ts:17-41`, `src/local/freshness/manifest.ts:34-44` |
| **Propagation de la péremption** : un artefact dérivé est marqué `stale` dès que l'une de ses sources d'ancrage change | C'est exactement le mécanisme qu'il faut à K-B pour la péremption : une page wiki qui cite une source modifiée (ou une CVE/release mise à jour) passe `stale` dans son frontmatter, sans LLM. | `src/local/operations.ts:3043-3050` |
| Rescan qui écrase la couche machine mais **préserve la couche manuelle**, séparées par `source_scope_id` | Ça correspond à nos deux flux : les items de veille automatiques peuvent être recalculés sans toucher aux documents déposés à la main. | `src/local/operations.ts:3019-3033` |
| Validation déterministe des citations : chaque id cité par le LLM est résolu contre la base, les ids non résolus sont **signalés et jamais ignorés**, avec un décompte validés / invalides / preuves | Lint de K-B : vérifier que chaque source citée par une page wiki existe dans `raw/` ou dans la base de veille (liens brisés, sources inventées). Fonction pure, sans I/O. | `src/local/graph/citations.ts:1-60` |
| Échelle de « force de preuve » **attribuée par règle** (`hard`, `reviewed`, `framework-derived`, `candidate`, `weak`) et statut de revue (`local_reviewed`, `auto_detected`, `inferred`, `ai_suggested`) | Remplace les scores de confiance produits par le LLM, que nous refusons : la provenance est un label discret posé par le code. Ce qui vient du LLM est toujours `weak` / `ai_suggested` et ne compte jamais comme preuve. | `src/local/graph/ontology.ts:48-61`, `src/local/aiGraph/links.ts:724-725` |
| Provenance sans stockage du texte : `source_ref` + `quote_hash` (sha256 de la citation exacte) + `model_provider/model_name/prompt_version` | Permet de prouver qu'un extrait cité par le wiki existe bien dans la source (on recalcule le hash), et de tracer quel modèle et quel prompt ont produit une page (utile quand on change de modèle par configuration). | `src/local/graph/ontology.ts:66-80` |
| Garde-fou sur la sortie JSON du LLM : parsing tolérant, les items invalides sont rangés dans `dropped[]` avec une raison, et le prompt contient « Never invent ids » | Modèle simple pour les synthèses de veille qui renvoient du JSON structuré. | `src/local/aiGraph/links.ts:571`, `:630-664` |
| Adaptateurs de modèles interchangeables (OpenAI-compatible, Anthropic, Ollama) + `DeterministicProvider` hors ligne | Le fournisseur déterministe permet des tests et une CI sans clé API ni coût. C'est à reproduire en Python pour K-B. | `src/local/generate/providers.ts:271-277`, `:476-489` |
| Masquage des secrets (regex clés API, JWT, clés privées) avant tout envoi au LLM ou affichage | Les newsletters et documents déposés peuvent contenir des jetons. Point RGPD / sécurité de la certification. | `src/local/util/redact.ts:6-24` |
| Fichier d'exclusion `.orangeproignore` créé par défaut, avec `*.env`, `*.pem`, `secrets/` | Même idée pour le dossier de dépôt manuel de K-B. Ça rejoint notre règle « ne jamais lire `.env` ». | `src/local/workspace.ts:36-45` |
| CI avec un **gate « privacy »** obligatoire, jobs parallèles, `permissions: contents: read` | Exemple concret pour le volet CI de la certification. | `.github/workflows/ci.yml:1-48` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Vérité stockée dans un **unique `graph.json`** réécrit en entier | K-B veut un markdown lisible dans Obsidian comme source de vérité, et une base interrogeable pour la veille. Un gros JSON n'est ni lisible, ni versionnable proprement, ni requêtable par date. | `src/local/workspace.ts:6-8`, `src/local/operations.ts:1156` |
| Le LLM renvoie un champ `confidence` numérique (0.0 par défaut, repli à 0.5), stocké sur les nœuds et les arêtes | Contraire à notre décision « pas de scores de confiance produits par le LLM ». Ils l'atténuent par le label `weak`, mais le chiffre existe quand même et remonte dans `explain`. | `src/local/aiGraph/links.ts:574`, `:660` ; `src/local/explain/explain.ts:92` |
| Télémétrie **activée par défaut** (opt-out via `DO_NOT_TRACK=1`), vers un domaine tiers | Pour un outil personnel et dans une logique RGPD, il faut au minimum un opt-in explicite. | `src/local/telemetry.ts:10`, `:69-76` ; appel `src/local/operations.ts:2489` |
| Fichiers monolithes (`operations.ts` 3 193 l., `cli.ts` 1 539 l.) | Difficile à relire et à défendre en soutenance. Nous visons des modules courts, un par opération (ingest / query / lint). | `src/local/operations.ts`, `src/local/cli.ts` |
| Deux produits sans code commun dans un même dépôt, dont un proxy vers un backend fermé | Brouille la lecture. Le « MCP hosted » ne sert à rien sans leur SaaS. | `CLAUDE.md:7-11`, `src/apiClient.ts` |
| « Journal » `ledger.json` réécrit au lieu d'être append-only | Notre `log.md` doit rester append-only pour être auditable. | `src/local/ledger.ts:141-143` |
| Heuristiques très spécifiques au code (seuils de hub, repli par zone de répertoire) | Beaucoup de complexité liée au domaine des tests, sans équivalent pour des documents. Seule l'idée « plafonner le repli grossier » est transposable. | `src/local/freshness/changed.ts:11-28` |

**Non vérifié** : la qualité effective des tests (rien n'a été exécuté), et le code de `infra/telemetry-worker/` (non lu en détail).

## 6. En une phrase

Ce n'est pas un wiki : K-B en retient surtout la **chaîne déterministe de péremption** (hash par source → état fresh/stale → propagation `stale` vers les pages dérivées qui citent la source) et la **validation des citations produites par le LLM contre la base**, avec une provenance en labels discrets plutôt qu'en scores.
