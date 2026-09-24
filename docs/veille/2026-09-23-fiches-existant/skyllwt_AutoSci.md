# `skyllwt/AutoSci` (ex-OmegaWiki)

Lu le 2026-09-24, clone `--depth 1`, commit `cf88930` du 2026-09-18 (« SECURITY: revert malicious requests dependency »). Lecture seule : rien n'a été exécuté. Un seul commit est visible (clone superficiel) : l'historique de l'attaque (`9ff3087`) n'a pas pu être vérifié.

## 1. Identité

- **Pitch.** Plateforme de recherche scientifique « tout le cycle » (lecture d'articles → idées → expériences sur GPU distant → rédaction → poster → rebuttal) pilotée par Claude Code, avec un wiki Markdown typé comme mémoire persistante. Le wiki n'est pas le produit final : c'est la mémoire d'un agent qui écrit des articles.
- **Pile.** Python 3.9+ (stdlib + PyMuPDF, feedparser, requests, PyYAML, deepxiv-sdk, playwright optionnel), 26 skills Claude Code (`.claude/skills/`), un serveur MCP maison (`mcp-servers/llm-review/server.py`), une SPA JS sans framework (`app/`) servie par `tools/serve.py`. Bilingue en/zh via `i18n/` copié par `setup.sh`.
- **Taille.** 268 fichiers ; ~20 000 lignes de Python/JS, dont `tools/research_wiki.py` (2 861 l.), `tools/init_discovery.py` (1 713 l.), `tools/daily_arxiv.py` (1 534 l.), `tools/lint.py` (1 170 l.).
- **Licence.** MIT (`LICENSE`), « OmegaWiki Contributors ». Article associé arXiv 2605.31468.
- **Maturité.** Badge « internal beta » (`README.md:15`). **Un seul fichier de test** (`.sleepcode/tests/test_discover_from_venue.py`), **aucune CI de tests** : le seul workflow est la tâche planifiée `daily-arxiv.yml`. Doc abondante (README 27 Ko, CHANGELOG, `runtime/CLAUDE.md`, `docs/runtime-directory-structure.*.md`). Dépendances non épinglées (`requirements.txt` : que des `>=`).

## 2. Architecture

```
raw/{papers,notes,web}/   sources de l'utilisateur, lecture seule (règle en prose)
raw/{discovered,tmp}/     zone écrivable par les skills
wiki/<type>/<slug>.md     9 types : papers, concepts, topics, people, ideas, methods,
                          experiments, Summary, foundations (+ outputs/)
wiki/index.md, log.md     catalogue régénéré / journal en ajout seul
wiki/graph/               edges.jsonl, citations.jsonl, context_brief.md, open_questions.md
runtime/schema/*.yaml     LE contrat : entités, arêtes, xref, conventions
runtime/policy/writers.yaml   qui a le droit d'écrire quoi (spéc. non appliquée)
runtime/loader.py         API Python du contrat, partagée par lint et moteur
tools/research_wiki.py    moteur : slug, set-meta, add-edge, transition, rebuild-*, checkpoint
tools/lint.py             validateur déterministe + --fix
tools/daily_arxiv.py      pipeline de veille arXiv (config → prepare → décision LLM → finalize)
tools/serve.py + app/     API REST locale + SPA de lecture/édition
.claude/skills/           la logique métier (ingest, ask, check, daily-arxiv, init…)
```

**Flux d'ingest** (`.claude/skills/ingest/SKILL.md`) : l'agent résout la source (arXiv, PDF, .tex), obtient le slug par `research_wiki.py slug` (l.110), **écrit lui-même la page** en suivant `runtime/templates/papers.md.tmpl` avec un « shape check » volontairement minimal (l.139-147), cherche les doublons de concepts par `find-similar-concept` (`references/dedup-policy.md`), crée les arêtes par `add-edge` (qui refuse une arête sans `evidence`/`confidence`, l.66-68), puis `log` et `rebuild-context-brief` / `rebuild-open-questions` (l.192-202). **Le lint n'est pas appelé** dans l'ingest : c'est le rôle de `/check`, lancé à part.

**Flux de question** (`.claude/skills/ask/SKILL.md:65-83`) : lecture de `context_brief.md` + `open_questions.md`, correspondance de mots-clés dans `index.md`, lecture de ≤ 15 pages, synthèse ; option `--crystallize` pour réécrire la réponse dans `wiki/outputs/`. Pas de moteur de recherche : c'est l'agent qui « grep » à la main.

**Flux de veille** (`tools/daily_arxiv.py`, `.github/workflows/daily-arxiv.yml`) : voir §4 (ce qu’on retient), §6 (nouveauté) et §7 (risques).

## 3. Rapport au pattern Karpathy

| Élément | Statut | Détail |
|---|---|---|
| `raw/` immuable | **présent, transformé** | Découpé en zone utilisateur (lecture seule) et zone agent (`discovered/`, `tmp/`) — `runtime/schema/conventions.yaml:22-25`. Protection par règle en prose (`CLAUDE.md`, règle 1), pas par code. |
| `wiki/` compilé | **présent, fortement typé** | 9 types d'entités, champs typés, enums, `required_when`, cycle de vie (`runtime/schema/entities.yaml`). |
| Schéma type AGENTS.md | **transformé** | Le schéma n'est plus de la prose : c'est du YAML lu par le code (`runtime/loader.py`), le `CLAUDE.md` renvoie vers les YAML. C'est l'aboutissement le plus net de la convergence « la règle doit être du code »… sauf pour les droits d'écriture (§5). |
| ingest | présent | Unitaire (`/ingest`) ou en masse parallèle (`/init`, sous-agents dans des worktrees git). |
| query | présent | `/ask`, avec « cristallisation » optionnelle dans le wiki. |
| lint | présent, séparé | `tools/lint.py` (8 contrôles mécaniques + `--fix`) ; `/check` pour le jugement. |
| `index.md` | présent, **généré** | `research_wiki.py rebuild_index` (l.1823), format YAML-like. |
| `log.md` | présent | Ajout seul, grammaire `## [date] skill | détails` (`conventions.yaml:19`, `research_wiki.py:2080`). |
| Obsidian | secondaire | Liens `[[slug]]` compatibles ; mais le graphe sémantique vit dans `edges.jsonl`, invisible dans Obsidian. |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| **Pipeline de veille découpé en étapes déterministes + une seule étape LLM** : `config` → `prepare` (collecte, dédup, enrichissement, pré-classement) → décision LLM → `finalize` (digest md + json). | C'est exactement la séparation « déterministe d'abord » voulue pour K-B, appliquée à un flux de veille. | `tools/daily_arxiv.py:1383-1466`, `.github/workflows/daily-arxiv.yml` |
| **Repli sans LLM** : si les décisions LLM manquent, chaque candidat est affiché avec le score déterministe et une mention explicite. | La veille reste utilisable si l'API tombe ou si l'on n'a pas de clé. | `tools/daily_arxiv.py:832-842` |
| **Sortie LLM bornée par le code** : identifiants filtrés contre la liste des candidats réels, vocabulaire fermé (`strong_recommend/maybe/skip`), valeurs inconnues ramenées à `maybe`. | Empêche le LLM d'inventer un article ou une action ; même esprit que le « vocabulaire d'actions fermé » de mindbase, appliqué au tri de veille. | `tools/daily_arxiv.py:1182-1200` |
| **Deux modes `inform` / `auto-ingest`, `inform` par défaut ; le chemin « LLM tiers » ne peut jamais ingérer** (`ingest` rétrogradé en `strong_recommend`). | Le mode `inform` est notre modèle : la veille recommande, l'humain décide de l'ingest. | `config/daily-arxiv.yml.example` (`mode: inform`), `tools/daily_arxiv.py:1193-1194` |
| **Le wiki comme profil d'intérêt** pour classer la veille : mots-clés extraits des pages et du journal récent, préférences positives/négatives en configuration. | Répond à « pourquoi cet item m'intéresse ? » sans vectoriel ; transposable aux tags du wiki de K-B. | `tools/daily_arxiv.py:487-530`, `690-735` |
| **Dédup par identifiant canonique** (arXiv sans version, extrait d'URL ou de texte) contre tout le wiki. | Même besoin que notre `url_canonique` ; la normalisation est un bon modèle. | `tools/daily_arxiv.py:346-378` |
| **Contrat en YAML lu par le code** (entités, arêtes, xref) : ajouter un champ ou un type = éditer du YAML, lint et moteur suivent sans codegen. | Forme concrète de notre « validation du frontmatter par type » ; `required_when` couvre des règles conditionnelles (ex. `failure_reason` si `status: failed`). | `runtime/CLAUDE.md`, `runtime/schema/entities.yaml:1-15`, `runtime/loader.py` |
| **Cycle de vie codé avec préconditions** : `transition` refuse une transition non déclarée et exige certains champs (`key_result` pour `completed`, `--reason` pour `failed`). | Pour le statut dans le frontmatter (décision déjà prise), c'est la façon de le rendre vérifiable. | `tools/research_wiki.py:1607-1660`, `entities.yaml:96-100` |
| **Règles de lien retour déclaratives** (`xref.yaml`) vérifiées et réparées par `lint --fix`. | Liens bidirectionnels garantis sans LLM. | `runtime/schema/xref.yaml`, `tools/lint.py:451`, `835` |
| **Dédup d'entités par similarité lexicale à seuils** (≥ 0,80 fusion, 0,40-0,80 lecture, < 0,40 création) et **plafond de créations par source**. | Contre l'inflation de pages « concept » quasi identiques ; complément de la dédup par URL. | `tools/research_wiki.py:1007-1035`, `.claude/skills/ingest/references/dedup-policy.md:30-50` |
| **`merge=union` pour les fichiers en ajout seul** (`log.md`, `edges.jsonl`, `index.md`) + refus des reconstructions dans un worktree secondaire. | Évite les conflits git sur le journal si on travaille sur deux branches. | `.gitattributes:15-28`, `tools/research_wiki.py:791-818` |
| **Frontière UI / LLM explicite** : la SPA ne lance jamais une skill, elle génère la commande à coller dans Claude Code ; chaque écriture depuis l'UI est journalisée `frontend | …`. | Cohérent avec « ingest déclenché par l'humain » et utile pour le futur dashboard ; la journalisation par origine sert le monitoring. | `tools/serve.py:17-45` (docstring), `_audit_log` l.149 |
| **Indépendance du relecteur** : ne jamais transmettre au second modèle le jugement du premier. | Règle simple si K-B ajoute un jour une vérification croisée. | `.claude/skills/shared-references/cross-model-review.md:9-27` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| **Droits d'écriture déclarés mais non appliqués**, et assumés comme tels : « STATUS: SPEC, NOT A RUNTIME GATE… Enforcement is at the prompt level ». | Contre-exemple parfait de la convergence n°3 : la règle existe, le code ne la lit pas. | `runtime/policy/writers.yaml:3-14` |
| **`confidence` high/medium/low produite par le LLM, obligatoire sur chaque arête sémantique**, et `confidence` + `score` sur chaque recommandation de veille. | Contraire à notre décision (pas de score produit par le LLM). Garder seulement le champ `evidence` obligatoire. | `runtime/schema/edges.yaml:30`, `.github/workflows/daily-arxiv.yml` (prompt JSON) |
| **Le graphe sémantique ne vit que dans `edges.jsonl`**, pas dans le Markdown ; seules les arêtes « frontmatter » sont reprojetables. | Le Markdown n'est plus toute la vérité (convergence n°1) ; Obsidian ne voit pas ces relations. | `tools/research_wiki.py:275-300`, `586-600` |
| **Trois parseurs YAML écrits à la main** alors que PyYAML est une dépendance ; celui du lint ignore listes et clés imbriquées. | Le validateur ne voit pas ce qu'il valide ; utiliser un vrai parseur. | `tools/lint.py:114-141`, `tools/research_wiki.py:2155`, `tools/daily_arxiv.py:168` |
| **Tokenisation ASCII seulement** : `[^a-z0-9\s]` supprime les lettres accentuées. | « sécurité » devient « s curit » : dédup et profil d'intérêt cassés en français. | `tools/research_wiki.py:987`, `999` |
| **Pas de porte de fusion** : l'ingest écrit les pages directement, avec un contrôle de forme « intentionnellement étroit », le lint vient après, à part. | Nous voulons le lint avant/après avec refus (Eva, ClaudeBrain). | `.claude/skills/ingest/SKILL.md:139-147` |
| **Aucune péremption** : pas de contrôle d'âge dans le lint ; `papers` n'a que `year` et `date_added` ; `maturity: deprecated` est posé à la main. | Rien à reprendre sur notre point central. | `tools/lint.py:684-730`, `runtime/schema/entities.yaml:17-33` |
| **Items de veille éphémères** : le flux est écrit dans `.daily-arxiv/run/feed.json`, publié comme artefact CI, puis perdu ; `published` reste une chaîne brute ; pas de date de collecte. | Impossible de répondre à « quoi de neuf cette semaine » après coup. | `.github/workflows/daily-arxiv.yml` (étape « Upload »), `tools/daily_arxiv.py:533-548` |
| **Filtre temporel probablement inopérant** : `datetime.fromisoformat` appliqué au champ `published` du RSS arXiv (format RFC 822 attendu), et toute date illisible est **conservée** sans avertissement. Non vérifié à l'exécution. | Un filtre « 24 h » qui laisse tout passer ; utiliser `published_parsed` ou `email.utils`, et rejeter plutôt que garder. | `tools/fetch_arxiv.py:66-78` |
| **Auto-ingest en CI** : Claude Code Action lit des résumés arXiv (texte non fiable) avec `Bash`, `Write`, `Agent` autorisés, puis le workflow pousse sur `main`. | Chemin d'injection de prompt direct ; notre sujet n°10. | `.github/workflows/daily-arxiv.yml` (`--allowedTools "Read,Write,Edit,Bash,Skill,TodoWrite,Agent"`, `git push`) |
| **Moteur monolithique, quasi sans tests** (2 861 lignes, 1 fichier de test, pas de CI de tests). | Incompatible avec la CI attendue par la certification. | `tools/research_wiki.py`, `.sleepcode/tests/` |
| **Correspondance par sous-chaîne** dans le lint qualité (`if slug in cc`). | Faux positifs sur des slugs courts. | `tools/lint.py:696-701` |

## 6. Ce qu'il apporte de nouveau par rapport aux 14

1. **C'est le premier des quinze à faire de la veille.** La note de synthèse affirmait « aucun des quatorze ne sait répondre à "quoi de neuf" » : AutoSci a un vrai pipeline quotidien (collecte RSS arXiv, dédup contre le wiki, enrichissement Semantic Scholar/DeepXiv, pré-classement, décision LLM bornée, digest Markdown + JSON, e-mail, planification GitHub Actions). **Il ne comble pourtant pas notre manque n°1** (le modèle d'item) : les items ne sont pas persistés, n'ont pas de date de collecte, et la date de publication reste une chaîne. La phrase « aucun ne traite la veille » est donc à nuancer en « un seul traite une veille arXiv, sans mémoire des items ».
2. **Le wiki sert de profil pour classer la veille** (`build_wiki_profile`). Aucun des 14 ne relie les deux flux dans ce sens (le wiki filtre la veille, pas seulement l'inverse). Idée directe pour K-B : classer les items de la semaine par recouvrement avec les tags du wiki.
3. **Modes `inform` / `auto-ingest` et repli déterministe sans LLM** : c'est une réponse concrète à la convergence n°6 (« l'ingest automatique est la pente naturelle »). Le dépôt y va en option, mais garde `inform` par défaut et interdit l'ingest au chemin LLM tiers.
4. **Le schéma exprimé en YAML exécutable, cycle de vie compris** (`runtime/`). link et toolboxmd valident le frontmatter ; AutoSci va plus loin avec les transitions d'état à préconditions et les règles de lien retour déclaratives réparées par `lint --fix`.
5. **Dédup d'entités (pas seulement de sources)** par similarité lexicale à seuils, avec un plafond de créations par source.
6. **Travail parallèle sur git** : `merge=union` sur les fichiers en ajout seul, reconstructions interdites dans les worktrees secondaires, points de reprise (`checkpoint-*`).
7. **Frontière UI / LLM** : l'interface web ne simule jamais une skill et journalise chaque écriture avec son origine.
8. **L'aveu écrit que la règle en prose ne s'applique pas** (`writers.yaml`) : le contre-exemple le plus explicite de toute la veille.

## 7. Sécurité

Rien n'a été exécuté. Constats par lecture seule.

**Chaîne d'approvisionnement.**
- Le commit HEAD rétablit `requests` depuis PyPI (message de `cf88930`). `requirements.txt` actuel : aucune URL git, mais **tout est en `>=`, sans hash ni verrouillage**, ce qui a rendu l'attaque possible et n'empêche pas la suivante.
- `setup.sh:134` et `setup.ps1:120` font `pip install -r requirements.txt` ; le workflow CI aussi (étape « Install dependencies »). Toute personne ayant lancé `setup` entre le 12 et le 18/09 est concernée.
- `deepxiv-sdk` : paquet peu connu ; `tools/fetch_deepxiv.py:14` indique que le SDK « s'auto-enregistre au premier usage » (appel réseau implicite).
- `playwright` optionnel : `python -m playwright install chromium` télécharge un navigateur (`requirements.txt`, commentaire).

**Scripts d'installation.** Pas de `curl | sh`, pas de téléchargement direct, pas de modification de profil shell. En revanche ils :
- créent `.env` à partir de `.env.example` (`setup.sh:141-146`) ;
- copient `config/settings.local.json.example` vers `.claude/settings.local.json` (`setup.sh:150-157`), qui accorde **`Bash(*)`, `Read(*)`, `Edit(*)`, `WebFetch(*)`, `WebSearch`, `MCP(*)` et `enableAllProjectMcpServers: true`**. Donc tout ce qu'un article, une page web ou un résumé injecté pourrait demander à Claude s'exécuterait sans confirmation. **C'est le point le plus grave pour un usage local.**
- écrasent `CLAUDE.md` et `.claude/skills/*` par les copies de `i18n/<lang>/` (`setup.sh:160-170`) : les consignes actives ne sont pas celles qu'on lit dans le dépôt tant qu'on n'a pas comparé les deux arborescences (non fait ici).

**Hooks.** Aucun hook Claude Code (pas de `settings.json` versionné, pas de clé `hooks`) ; aucun hook git. `.gitattributes` n'utilise que le pilote intégré `merge=union` (pas de filtre exécutable).

**MCP.** `.mcp.json` lance `python3 mcp-servers/llm-review/server.py` (local). Ce serveur envoie les contenus qu'on lui passe (pages du wiki, brouillons) à un **fournisseur tiers configurable** (`LLM_BASE_URL`, ex. DeepSeek, `server.py:14`) via `httpx`, et expose un outil `web_search`. Pas de masquage des secrets. Il journalise dans un fichier de `/tmp` (URL et modèle, pas la clé : `server.py:52`, `74-78`).

**Éléments suspects ou à signaler.**
- **Secret codé en dur et auto-inscription** : la skill `/setup` demande à Claude d'exécuter un Python en ligne qui s'inscrit auprès de `https://data.rag.ac.cn/api/register/sdk` avec un `sdk_secret` en clair et une **adresse e-mail fictive générée** (`.claude/skills/setup/SKILL.md:126-160`). Pas malveillant en soi, mais c'est exactement le type de commande réseau à ne pas laisser exécuter automatiquement.
- **`tools/_env.py:30` charge `~/.env` (répertoire personnel)** en plus du `.env` du projet : toutes les clés globales de l'utilisateur deviennent visibles des outils et des sous-processus lancés par Claude.
- **Workflow `daily-arxiv.yml`** : `contents: write`, `id-token: write`, `persist-credentials: true`, Claude Code Action avec `Bash` sur du texte arXiv non fiable, puis `git remote set-url` avec le `GITHUB_TOKEN` et `git push` sur `main`. Aucune consigne anti-injection dans la skill (`grep` de « untrusted/injection » : aucun résultat). Secrets SMTP exposés au même job.
- **`tools/serve.py`** : lié à 127.0.0.1 mais **sans vérification d'`Origin` ni du `Content-Type`** (`_read_json_body`, l.366). Un site web ouvert dans le navigateur pourrait envoyer des `POST` « simples » à `/api/log`, `/api/edges`, `/api/lint/fix` (écriture dans le wiki). Déduit du code, non testé.
- **`tools/remote.py`** : exécute par SSH une commande arbitraire (`launch --cmd`) sur un serveur GPU configuré. C'est sa fonction, mais combinée à `Bash(*)` cela donne à l'agent l'accès aux machines distantes.
- Je n'ai rien trouvé d'obfuscation (`base64`, `eval`, `exec`) dans `tools/`.

## 8. En une phrase

K-B retient d'AutoSci la forme d'un pipeline de veille « déterministe, puis une seule décision LLM bornée, avec repli sans LLM et mode `inform` par défaut », le wiki comme profil pour classer les items, et le schéma YAML exécutable avec cycle de vie ; il en rejette la confiance produite par le LLM, le graphe hors Markdown, la tokenisation ASCII, les items éphémères et, surtout, le modèle de sécurité (`Bash(*)`, auto-ingest avec push en CI, dépendances non verrouillées).
