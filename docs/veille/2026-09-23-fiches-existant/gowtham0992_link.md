# Fiche de veille — `gowtham0992/link` (Link)

> Analyse en lecture seule d'un clone `--depth 1` (commit `cc92f36`, 2026-09-16). Aucun code exécuté. Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : Link est une « mémoire locale pour agents IA » (Claude Code, Codex, Cursor, Kiro, Copilot…) stockée en Markdown + frontmatter YAML, exposée par CLI, serveur MCP, hooks de session et visionneuse web locale. Il reprend explicitement la structure Karpathy (`raw/` → `wiki/` → `LINK.md` schéma) mais son produit central est devenu la **mémoire d'agent** (`wiki/memories/`), pas la base de connaissances.
- **Pile** : Python ≥ 3.10, stdlib quasi exclusivement (argparse, `http.server`, `sqlite3` FTS5) ; embeddings locaux optionnels (model2vec / MiniLM ONNX, `benchmarks/RESULTS.md:18-30`) ; app menu macOS en Swift (`apps/LinkBar/`) ; installeurs shell/PowerShell par agent (`integrations/*/install.sh`).
- **Dernier commit** : 2026-09-16 (merge PR #69 depuis `develop`).
- **Taille** : 332 fichiers suivis ; cœur `mcp_package/link_core/` ≈ 28 100 lignes réparties sur ~60 modules, dont `memory.py` seul = 4 027 lignes ; plus `link.py` (164 Ko) et `serve.py` (81 Ko) à la racine, copies « standalone » du cœur.
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : élevée. 82 fichiers de tests (`tests/`), CI GitHub Actions multi-OS (Linux 3.10/3.12/3.14 + Windows) avec ruff, ratchet mypy, pytest, smoke tests (`.github/workflows/ci.yml:20-132`), `ARCHITECTURE.md`, `CHANGELOG.md` de 124 Ko, site de doc (`docs/*.html`), publication PyPI/MCP Registry/Homebrew. Projet solo très actif, rythme « release-driven ».

## 2. Architecture

```
LINK.md                      schéma = instructions pour l'agent (templates de pages, opérations)
raw/                         sources immuables déposées par l'humain (vide dans le dépôt)
wiki/                        index.md, log.md, _backlinks.json + sous-dossiers par TYPE :
  sources/ concepts/ entities/ memories/ comparisons/ explorations/
link.py                      CLI (`lnk`) : parse, dispatch, rendu
serve.py                     visionneuse web + API JSON, 127.0.0.1 uniquement
mcp_package/link_core/       TOUTE la logique partagée
  ingest.py                  état raw ↔ sources/ (pending / represented / stale)
  structured_ingest.py       ingest déterministe d'exports structurés (1 seul adaptateur : chezmoi)
  validation.py              validation frontmatter + sections obligatoires par type
  doctor.py                  lint (liens morts, pages isolées, dérive d'index…)
  log.py                     log.md append-only chaîné par SHA-256
  search.py / query.py       recherche lexicale SQLite FTS5 + paquet de contexte
  semantic.py                tier sémantique optionnel, offline
  memory.py                  modèle de mémoire : écriture, conflits, doublons, cycle de vie
  staleness.py               détection de mémoires périmées via historique git
  security.py                scan de secrets / injections dans raw/
mcp_package/link_mcp/server.py   surface MCP
scripts/                     benchmarks + garde-fous CI
```

**Flux principal (dépôt d'un document → réponse)** :
1. L'humain dépose un fichier dans `raw/`.
2. `lnk ingest-status` (`ingest.py:745` `collect_ingest_status`) liste les fichiers raw, scanne les secrets (`security.py:124`), et classe chaque fichier en *represented* / *pending* / *stale*. La correspondance raw ↔ page source se fait par **présence du chemin `raw/...` dans le texte de la page source** (`ingest.py:93-124`) ; « stale » = mtime du raw > mtime de la page source (`ingest.py:781`).
3. **C'est l'agent LLM externe** (Claude Code, etc.) qui lit la source et écrit les pages en suivant `LINK.md:320-369` (page source, mise à jour concepts/entités, index, log). Link ne fait aucun appel LLM lui-même (`ARCHITECTURE.md`, invariant 2).
4. `lnk validate` (`validation.py:108`) bloque sur frontmatter/sections manquants ; `rebuild-index` / `rebuild-backlinks` régénèrent `index.md` et `_backlinks.json` de façon déterministe (`wiki.py:1016-1073`, `wiki.py:405`).
5. Question : `lnk query` / MCP `recall` / `GET /api/query-link` → FTS5 (`search.py:74`, table `page_fts(name, title, metadata, body)`), boosts, éventuellement sémantique → « paquet de contexte » avec provenance, que l'agent synthétise.

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans Link | Commentaire |
|---|---|---|
| `raw/` immuable | **Présent** (`LINK.md:27`) | Plus un scan de secrets bloquant avant lecture (`ingest.py:173-222`). |
| `wiki/` compilé par LLM | **Présent**, découpé par type (`LINK.md:12-19`) | 6 types de page avec templates imposés ; validé par `validation.py:14-39`. |
| Schéma type AGENTS.md | **Présent** : `LINK.md` (38 Ko) | Très long, mélange schéma et mode d'emploi CLI/MCP/HTTP. |
| ingest | **Transformé** : 2 chemins | agent-authored (LLM externe) + `structured_ingest.py` déterministe, planifié puis `--apply`, avec hash sources/sorties. |
| query | **Présent**, outillé | Recherche lexicale FTS5 d'abord, sémantique optionnel ; dépôt de la réponse en `explorations/` sur accord humain (`LINK.md:387-389`). |
| lint | **Présent** : `doctor` + `validate` | Partiellement déterministe ; plusieurs règles de `LINK.md:391-425` restent à la charge du LLM (voir §5). |
| `index.md` | **Présent**, régénéré par script | `wiki.py:1016` `build_index_markdown`. |
| `log.md` append-only | **Présent et durci** | Chaque entrée porte `log_previous_hash` + `log_entry_hash` SHA-256 (`log.py:41-73`), vérifiable (`log.py:261`), avec rotation. |
| Obsidian | **Présent** (`link_core/obsidian.py`, `docs/obsidian.html`) | Wikilinks `[[...]]` conservés. |
| Veille / flux entrants | **Absent** | Aucun collecteur RSS, GitHub releases, CVE ; le runtime est volontairement hors-réseau (`ARCHITECTURE.md`, invariant 3). |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Validation déterministe par type de page (`TYPE_DIRECTORIES`, `REQUIRED_FIELDS`, `REQUIRED_SECTIONS`) | Exactement notre décision « wiki découpé par type + statut dans le frontmatter » ; un dict par type suffit à faire un validateur sans LLM. | `mcp_package/link_core/validation.py:14-39` |
| `log.md` append-only **chaîné par SHA-256** (hash précédent + hash de l'entrée), vérifié par `doctor` | Journal lisible en Markdown *et* infalsifiable ; bon argument « journalisation/traçabilité » pour la certification, coût quasi nul. | `mcp_package/link_core/log.py:41-73`, `log.py:261`, `doctor.py:516-525` |
| `index.md` et `_backlinks.json` **régénérés par script**, jamais à la main par le LLM ; `doctor` signale dérive d'index et backlinks périmés | Applique « déterministe d'abord » à l'index Karpathy. | `mcp_package/link_core/wiki.py:1016`, `wiki.py:405`, `doctor.py:460-482` |
| Lint déterministe : liens morts, pages non indexées, pages isolées, `source_count` incohérent, sections Sources manquantes | Liste prête à reprendre pour notre `lint`. | `mcp_package/link_core/doctor.py:449-556` |
| Statut raw → wiki : *pending / represented / stale* calculé sans LLM (mtime raw > mtime page source ⇒ à réingérer) | Répond au besoin de péremption côté dépôt manuel, et sert de file d'attente pour l'ingest unitaire déclenché par l'humain. | `mcp_package/link_core/ingest.py:745-846` (ligne 781) |
| Scan de secrets des fichiers `raw/` **avant** que le LLM ne les lise, avec blocage | Protège contre l'envoi de secrets à une API LLM ; utile aussi côté RGPD. | `mcp_package/link_core/security.py:69-150`, `ingest.py:181` |
| Cycle de vie par dates dans le frontmatter : `review_after` par défaut selon le type (3 à 12 mois), `expires_at`, `supersedes`/`superseded_by`, requête `--as-of DATE` | Modèle simple et déterministe pour gérer la péremption dans le wiki (une CVE ou une version aurait son propre délai). | `mcp_package/link_core/memory.py:552-610` |
| Recherche lexicale SQLite FTS5 comme défaut, sémantique en option offline, index dérivé jetable (`.link-cache/`) | Conforme à notre « lexical d'abord » ; le Markdown reste la vérité, la BDD n'est qu'un cache reconstructible. | `mcp_package/link_core/search.py:73-190` |
| Ingest structuré déterministe : plan puis `--apply`, hash des sources/sorties, refus d'écraser une page modifiée à la main | Patron réutilisable pour nos items de veille (flux → pages sans LLM), avec garde-fou contre l'écrasement. | `mcp_package/link_core/structured_ingest.py:1-92`, `LINK.md:322-329` |
| Journal d'opérations multi-fichiers + sauvegarde/restauration locale avec rotation | Répond à « stockage local + sauvegarde » et à la reprise après écriture interrompue. | `mcp_package/link_core/operations.py:1-17`, `backup.py:78-140` |
| API web locale : liaison 127.0.0.1 imposée, `--host` refusé, contrôle Host/Origin et en-tête obligatoire pour les mutations | Base sécurité raisonnable pour notre futur dashboard (anti-CSRF / DNS rebinding). | `serve.py:1882-1905`, `serve.py:2026` |
| Benchmarks déterministes versionnés, **y compris les échecs** | Bonne pratique d'évaluation de la recherche, reproductible. | `benchmarks/RESULTS.md:1-30` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Le produit a glissé vers la « mémoire d'agent » (préférences, décisions) ; `memory.py` fait 4 000 lignes de détection de conflits/doublons/échos | Hors sujet pour une veille ; énorme surface de code pour un besoin que K-B n'a pas. | `mcp_package/link_core/memory.py` (4 027 lignes), `ARCHITECTURE.md` |
| Scores de confiance `[confidence: high/medium/low]` produits par le LLM sur chaque affirmation, et même un lint « confidence gaps » | Contredit notre décision « pas de scores de confiance produits par le LLM ». | `LINK.md:351`, `LINK.md:416` |
| Règles de lint dites mais **non implémentées** : « stale claims » (`date_published` > 2 ans), contradictions, pages trop longues… laissées au LLM ; `doctor.py` n'utilise jamais `date_published` | La péremption, notre point central, n'est traitée qu'en prose ; à coder en déterministe chez nous. | `LINK.md:411`, `mcp_package/link_core/doctor.py:449-556` (vérifié par `grep date_published`) |
| Péremption fondée sur le mtime des fichiers | Fragile (copie, `git clone`, synchro cloud remettent les mtime) ; préférer un hash de contenu ou une date dans le frontmatter. | `mcp_package/link_core/ingest.py:781` |
| Lien raw ↔ page source par recherche du chemin dans le texte de la page | Implicite et fragile au renommage ; un champ frontmatter `raw:` explicite serait plus sûr. | `mcp_package/link_core/ingest.py:93-124` |
| Runtime **hors réseau** par principe (CI qui interdit le code sortant) | Incompatible avec le flux 1 (collecte RSS/GitHub/CVE) : rien à reprendre pour la collecte. | `ARCHITECTURE.md` (invariant 3), `scripts/check_release_hygiene.py:53-62` |
| Duplication volontaire du cœur dans `link.py` (164 Ko) et `serve.py` (81 Ko) + script anti-dérive | Complexité de maintenance ; nous n'avons pas besoin du « lancer sans installer ». | `ARCHITECTURE.md`, `scripts/check_runtime_duplication.py` |
| `LINK.md` de 38 Ko mêlant schéma, templates et mode d'emploi CLI/MCP/HTTP | Trop long pour un fichier de schéma lu à chaque session ; garder notre AGENTS.md court. | `LINK.md` |
| Pas de base de données, par principe (« si une fonctionnalité a besoin d'une BDD, repensez-la ») | Notre flux veille exige une BDD d'items datés interrogeable (filtre date + comptage) et la certification une BDD modélisée. | `ARCHITECTURE.md` (invariant 5) |
| API HTTP sans authentification ni OpenAPI (sécurité = localhost seulement) | Ne couvre pas le critère « API REST authentifiée documentée OpenAPI ». | `serve.py:1378-1417` |

## 6. En une phrase

Link est la meilleure implémentation outillée du pattern Karpathy vue jusqu'ici côté **hygiène déterministe du wiki** (validation par type, index/backlinks régénérés, log chaîné SHA-256, statut pending/stale, scan de secrets), et K-B peut en reprendre ces briques telles quelles, mais il ne fait aucune veille, s'interdit le réseau et la BDD, et laisse la péremption des affirmations au LLM : c'est précisément la partie que K-B doit construire lui-même.
