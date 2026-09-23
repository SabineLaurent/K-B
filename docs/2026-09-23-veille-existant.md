# Veille — quatorze implémentations du « LLM wiki », lues pour K-B

*Exploration du 2026-09-23. Sources : le document Drive « Inspi » et les notes de conception du
Drive (`PROJECT-karpathy-wiki-notes`). Chaque dépôt a été lu **dans son code**, pas seulement dans
son README, sur un clone `--depth 1`, sans rien exécuter. Les constats citent des fichiers ; deux
ou trois citations par dépôt ont été revérifiées à la main avant suppression du clone. Les fiches
détaillées, une par dépôt, sont dans `docs/veille/2026-09-23-fiches-existant/`. Le même dossier
contient la revue de `brief09_assistant-veille-tech`, le projet de formation de l'autrice, lu avec
la même grille.*

Ce document ne juge pas ces projets pour eux-mêmes. Il répond à une seule question :
**qu'est-ce que K-B en retient, et qu'est-ce que K-B évite ?** Les rubriques « à retenir » et
« à éviter » sont relatives à nos contraintes : deux flux (veille automatique, dépôt manuel), la
péremption de l'information, le déterministe d'abord, un modèle interchangeable, Obsidian comme
interface, et la défendabilité en soutenance.

## K-B en quelques lignes

> **K-B — une bibliothèque de veille tech qui se range toute seule.**
> Deux portes d'entrée. D'un côté, un pipeline récupère automatiquement l'actualité tech (blogs,
> newsletters, releases, alertes de sécurité, vidéos) pour qu'on puisse l'interroger à chaud :
> « quoi de neuf cette semaine ? », « pourquoi tel outil fait le buzz ? ». De l'autre, je dépose
> à la main les documents qui comptent, et ils nourrissent un wiki durable. Entre les deux, une IA
> joue les bibliothécaires : elle classe, relie, résume, et veille à ce que ce qui est écrit reste
> à jour. Les documents vivent sur ma machine, sauvegardés à part ; l'inférence passe par API. On
> lit dans Obsidian, on questionne depuis le terminal. Et quand tout tournera, un tableau de bord
> montrera l'état de la bibliothèque et le travail de ses scribes.

## Les sources en un coup d'œil

| # | Source | Dernier commit | Pile | Ce qu'on en retient en une phrase |
|---|---|---|---|---|
| 1 | `j-wang/knowledge-agent-template` | 2026-07-08 | Python | Le modèle de péremption `as_of` / `status` / `superseded_by` (décrit, pas codé) et une recherche BM25 qui se dégrade proprement. |
| 2 | `Tencent/WeKnora` | 2026-09-23 | Go + Python | Un lint wiki 100 % déterministe avec autofix, et un connecteur RSS incrémental propre. |
| 3 | `JanYork/llm-wiki-cli` | 2026-09-13 | Rust | Le lint écrit en SQL, une règle par requête ; la fraîcheur des sources par hash. |
| 4 | `suwonleee/llmwiki` | 2026-09-06 | TypeScript (Bun) | La propagation `stale_since` dans le graphe de liens, et l'interdiction des scores chiffrés vérifiée par lint. |
| 5 | `XBlueSky/cortexes` | 2026-09-22 | Python | Le drapeau `⚠️ Contradicts` et un banc d'évaluation de la recherche (P@k, MRR). |
| 6 | `gowtham0992/link` | 2026-09-16 | Python | L'hygiène du wiki en Python stdlib : validation par type, index régénéré, `log.md` chaîné par SHA-256. |
| 7 | `frankchu91/mindbase` | 2026-09-13 | TypeScript | Un vocabulaire d'actions fermé pour le LLM, et des citations de lint vérifiées mot pour mot. |
| 8 | `notfounnd/marc-server` | 2026-07-21 | TypeScript | « Markdown = vérité, index = dérivé reconstructible », écrit en ADR. |
| 9 | `jp-lorenc1o/Eva-brain` | 2026-07-29 | Rust + TS | Le lint avant/après l'ingest comme **porte de fusion**, et la frontière d'écriture vérifiée par Git. |
| 10 | `Encod3d-Sec/ClaudeBrain` | 2026-09-01 | Python | La **péremption par classe de sujet** (90 j / 365 j), datée par le frontmatter. |
| 11 | `OrangeproAI/orangepro-mcp` | 2026-09-21 | TypeScript | Une chaîne de péremption déterministe : hash → stale → propagation aux dérivés. |
| 12 | `Astro-Han/karpathy-llm-wiki` | 2026-07-24 | Markdown + Python | Un script qui vérifie que chaque valeur du wiki existe mot pour mot dans la source. |
| 13 | `toolboxmd/karpathy-wiki` | 2026-08-27 | Bash + Python | Les `_index.md` générés par script, et un validateur imposé par une porte de commit. |
| 14 | `akitaonrails/ai-memory` | 2026-09-23 | Rust | La note de recherche qui sépare ce que dit Karpathy de ce qu'on lui prête. |
| — | gist `rohitg00` « LLM Wiki v2 » | 2026-09-23 | texte | La supersession explicite ; le reste (scores, décroissance, automatisation) est écarté. |

Le gist de Karpathy sert d'étalon : on ne l'a pas « veillé », on a mesuré les autres à lui.

**Le constat qui domine tout le reste : aucune des quatorze implémentations ne fait de veille.**
Toutes traitent de recherche, de mémoire d'agent ou de coordination. Deux seulement collectent du
RSS (WeKnora, mindbase), et aucune ne stocke des items datés interrogeables par période. Le
constat posé dans la note du 2026-08-01 (§7) tient, à quatorze sources contre trois.

---

## 1 — `j-wang/knowledge-agent-template`

Un gabarit : un agent de code lit `CLAUDE.md` et en suit la méthode pour extraire des PDF et des
articles, puis rédiger des fiches « concept » et « thèse ». Le seul vrai code est la recherche
(`engine/kb_engine/`, 1 764 lignes). Aucun test, aucune CI. C'est le dépôt que décrit la page
« Anatomie du Knowledge Agent » liée dans Inspi.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **`LEARNING.md` : `as_of`, `status: current \| superseded \| contested`, `superseded_by`, « rétrograder et annoter, ne jamais supprimer »** (`LEARNING.md:28-46`) | C'est le modèle de péremption dont K-B a besoin, compatible avec le statut dans le frontmatter. **Attention : il n'est pas implémenté** (« Nothing here is built yet », `LEARNING.md:3`). On reprend l'idée, pas du code. |
| BM25 local par défaut, vecteurs et rerank activés par variable d'environnement, repli sur BM25 en cas de panne (`search.py:373-428`) | « Lexical d'abord, vectoriel si nécessaire », avec un modèle interchangeable par configuration. |
| La règle de recherche multi-passes **paresseuse**, mesurée : décomposer systématiquement la question dégrade un corpus factuel de 1,5 à 2,5 points sur 10 (`README.md:132`) | La veille est un corpus factuel. À appliquer à « pourquoi X fait le buzz ». |
| Un journal JSONL des pages récupérées et citées (`LEARNING.md:70-78`) | Détecter sans LLM les pages jamais utiles ; matière pour le monitoring. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| **Tokenizer ASCII seul** (`search.py:87` : `[a-z0-9]+`) | Casse le français : « sécurité » devient `s` + `curit`. |
| Frontmatter lu par regex, sans validation (`kb_docs.py:45-63`) | Un `tags: [a, b]` en ligne est ignoré sans avertissement. |
| Aucune date dans le frontmatter des gabarits | Rédhibitoire pour « quoi de neuf cette semaine ». |
| `WAKE_CMD` exécutée avec `shell=True` depuis la configuration (`providers.py:84`) | Exécution de commande arbitraire par un fichier de config. |

---

## 2 — `Tencent/WeKnora`

Une plateforme RAG d'entreprise (Go, parsing en Python, front Vue), avec un module « Wiki » qui
compile les documents en pages reliées par `[[liens]]`. Très mûre : 12 workflows de CI, 1 225
fichiers de test, 110 migrations, un OpenAPI vérifié par un test de contrat, un mode « Lite » en
SQLite. C'est l'implémentation industrielle la plus proche du pattern.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Lint entièrement déterministe** : pages orphelines, liens brisés, sources supprimées, liens croisés manquants, pages vides, slugs en double (`wiki_lint.go:17-22`) | Exactement notre liste « script, pas LLM ». À porter en Python sur des fichiers `.md`. |
| Autofix prudent : un lien mort devient du texte, une page vide est **archivée** et non supprimée (`wiki_lint.go:346-420`) | Des corrections réversibles, sans LLM. |
| Pré-dédup par similarité de surface **avant** d'interroger le LLM (`wiki_ingest_dedup.go:15-50`) | Le commentaire documente un vrai cas où le LLM a fusionné deux entités sans aucun caractère commun. |
| Prompt de mise à jour de page avec une section **« Contradictions / Updates »** (`prompts_wiki.go:321-343`) | Réponse directe à la péremption, à reprendre dans notre `AGENTS.md`. |
| **Connecteur RSS incrémental** : identifiant GUID puis lien puis titre, empreinte du contenu, curseur par flux, échecs partiels tolérés (`rss/connector.go:239-351`) | Un modèle direct pour notre collecteur. |
| Une interface `Connector` commune à toutes les sources (Validate / FetchAll / FetchIncremental) | Le gabarit pour RSS, releases GitHub, CVE, YouTube. Et un argument « collecte multi-sources » pour la certification. |
| OpenAPI généré **et testé en CI**, authentification JWT + clé API, audit avec rétention | Des exemples concrets pour C5 et la journalisation. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| **Ingest wiki automatique** dès la fin d'indexation (`knowledge_post_process.go:263-268`) | Contraire à l'ingest déclenché par l'humain, et ruineux sur un flux de veille. |
| Wiki stocké en base de données | Pas d'Obsidian, pas de diff git. |
| Mise à jour d'une source = suppression puis recréation | Perd l'historique : impossible de dire ce qui a changé dans une release. |
| Date de publication rangée dans un JSON libre, écrasée par la date de modification pour le RSS (`rss/connector.go:319-325`) | K-B a besoin de colonnes typées `published_at` et `fetched_at`. |
| « stale_ref » veut dire « source supprimée », pas « information périmée » | Aucune notion d'âge. C'est le vide que K-B comble. |

---

## 3 — `JanYork/llm-wiki-cli`

Une CLI Rust (~102 000 lignes, CI complète) pilotée par un agent de code. Le binaire n'appelle
aucun LLM : l'agent raisonne, l'outil tient les registres dans SQLite.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Lint entièrement en SQL**, une CTE par règle (`src/store/types.rs:114-200`) | Orphelins, liens brisés, pages sans source : facile à porter en Python + SQLite, testable, gratuit. |
| Règle `shallow_ingest` : un ingest terminé sans page produite exige une raison (`types.rs:133-145`) | Garde-fou contre l'ingest bâclé. |
| Fraîcheur des sources par hash + `source refs` pour savoir quelles pages citent une source modifiée (`definitions.rs:926-995`) | Les briques de la péremption côté dépôt manuel. |
| Provenance par page (`user-provided`, `agent-observed`, `hypothesis`) **au lieu d'un score** | Qualifier l'origine sans chiffre de confiance. |
| Mémoire temporelle `valid_from` / `valid_to` (`temporal_memory.rs`) | Le bon modèle de données pour dater un item de veille. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| **SQLite fait foi, le Markdown est une projection écrasée** (`docs/agent-workflow.md:15-16`) | Toute retouche faite dans Obsidian serait perdue. |
| Aucune collecte : fichiers texte locaux seulement | Rien pour notre flux 1. |
| Colonne `confidence` fournie par l'agent | Score de confiance du LLM, exclu. |
| Dérive de périmètre : tuteur, sync SSH, graphe de code, trois moteurs de stockage | Le contre-exemple de « simplicité d'abord ». |

---

## 4 — `suwonleee/llmwiki`

Un wiki de projet en Bun/TypeScript, alimenté par les sessions des agents de code, avec index
SQLite FTS5. Mûr (158 fichiers de tests, CI ubuntu et macOS) mais lourd (~30 000 lignes).

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Propagation `stale_since`** : quand une page change, les pages qui pointent vers elle sont marquées possiblement dépassées (`db.ts:875-896`) | Notre problème de péremption, traité de façon déterministe. |
| **Lint `numeric-confidence`** : un score chiffré dans le frontmatter est refusé (`lint.ts:434-447`) | Notre décision « pas de score de confiance », rendue vérifiable par script. |
| `status: superseded` impose `superseded_by` (`lint.ts:422-433`) | Une page de version remplacée pointe vers la suivante au lieu de disparaître. |
| Extraits de preuve vérifiés à la lettre contre la source (`excerpt.ts:14-19`) | Garde-fou déterministe contre l'hallucination. |
| FTS5 en trigrammes, requêtes nettoyées pour ne pas planter sur « CVE-2026-1234 » (`db.ts:93-110`) | Robuste en français et sur les identifiants techniques. |
| Choix du modèle par configuration, **sans valeur par défaut** (`models.ts:12-19`) | Aucun identifiant de modèle codé en dur qui vieillit. |
| Cadence du lint imposée par le code, pas par le prompt (`review.ts:40-48`) | « Une règle écrite en prose s'applique au bon vouloir du modèle. » |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Écriture autonome programmée du wiki | Contraire à l'ingest déclenché par l'humain. |
| Pages refusées par la vérification LLM abandonnées sans le signaler | Une information perdue en silence. |
| La « vérification par un second modèle » est le plus souvent le même modèle qui se relit (`session-model.ts:311-314`) | Ne jamais présenter une relecture par LLM comme une garantie. *Le chemin exact de l'avertissement n'a été vérifié qu'en partie.* |
| Le brut n'est pas conservé : les sessions sources expirent | Notre `raw/` doit être immuable. |

---

## 5 — `XBlueSky/cortexes`

Un plugin Claude Code (Python, ~538 tests, CI ruff + pytest) qui capture les sessions de travail
dans un vault Obsidian, les distille en notes puis les propage dans les pages existantes.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| Ingest en deux temps : *distill* (faut-il une page ?) puis *broadcast* (quelles pages mettre à jour ?) | Sépare la création de l'intégration transverse, le cœur du pattern. |
| **Drapeau `⚠️ Contradicts [[source]]`** au lieu d'écraser (`cortex-broadcast/SKILL.md:224-238`) | Le vieillissement reste lisible ; le LLM propose, l'humain tranche. |
| Audit d'index par **comparaison d'ensembles**, pas de nombres (`docs/index-audit.md`) | Un compteur tenu par le LLM y a dérivé jusqu'à 280 entrées pour 238 réelles. |
| **Banc d'évaluation de la recherche** : jeu de référence validé par l'humain, P@k, R@k, MRR par méthode (grep, BM25, vecteurs, hybride) | Les chiffres pour décider, ou non, de passer au vectoriel. Solide en soutenance. |
| CI et pre-commit qui lancent le même script | Pas d'écart entre la CI et le poste local. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Modèles OpenAI codés en dur (`store.py:23`) | Contraire au modèle interchangeable. |
| Reconstruction complète de l'index avec un appel LLM par page | Coût proportionnel à la taille du wiki. |
| Tokenizer anglais et chinois, rien pour le français | Contenu FR/EN. |
| Logique métier dans des prompts de 480 lignes | Intestable. |

---

## 6 — `gowtham0992/link`

Une mémoire locale pour agents, en Markdown, en Python stdlib (82 fichiers de tests, CI Linux et
Windows, ruff, mypy). Il reprend fidèlement la structure `raw/` → `wiki/` → schéma, mais son
produit central a glissé vers la mémoire d'agent (`memory.py`, 4 027 lignes).

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Validation par type de page** : `TYPE_DIRECTORIES`, `REQUIRED_FIELDS`, `REQUIRED_SECTIONS` (`validation.py:14-39`) | Un dictionnaire par type suffit à valider sans LLM. Colle à « wiki découpé par type ». |
| **`log.md` en ajout seul, chaîné par SHA-256** (`log.py:41-73`) | Journal lisible en Markdown *et* infalsifiable. Un bon argument de traçabilité pour la certification. |
| `index.md` et backlinks **régénérés par script**, jamais par le LLM | « Déterministe d'abord » appliqué à l'index de Karpathy. |
| Statut raw → wiki : *pending / represented / stale*, calculé sans LLM (`ingest.py:745-846`) | La file d'attente de l'ingest manuel. |
| Scan de secrets des fichiers bruts **avant** que le LLM ne les lise | On n'envoie pas un jeton à une API par mégarde. |
| Dates de cycle de vie dans le frontmatter : `review_after`, `expires_at`, `supersedes` (`memory.py:552-610`) | Simple et déterministe. |
| Serveur web local : liaison 127.0.0.1 imposée, contrôle Host/Origin | Une base de sécurité pour le futur dashboard. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Niveaux de confiance high/medium/low attribués par le LLM à chaque affirmation | Exclu par K-B. |
| **La règle « affirmations périmées » n'existe qu'en prose** : `doctor.py` n'utilise jamais `date_published` (`LINK.md:411`) | La péremption, notre point central, n'est pas codée. |
| Péremption par la date de modification du fichier | Fragile : une copie ou un `git clone` remet les dates à zéro. |
| Réseau et base de données interdits par principe | Incompatible avec notre flux 1. |

---

## 7 — `frankchu91/mindbase`

« Le LLM Wiki de Karpathy en produit » : monorepo TypeScript, serveur et app web, ~115 fichiers
de tests, CI. Le projet a pivoté : une ancienne version automatique et une nouvelle, pilotée par
l'humain, cohabitent.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Vocabulaire d'actions fermé, validé par schéma** : le LLM ne produit qu'un plan JSON, et aucune action ne peut toucher la couche brute (`ops/types.ts:3-21`) | L'immuabilité de `raw/` garantie par construction, pas par une consigne. En Python : pydantic. |
| **Citations du lint vérifiées par le code** : une contradiction sans deux citations retrouvées mot pour mot est jetée (`runner.ts:336-384`) | Le déterministe appliqué à la sortie du LLM. |
| Citation de source ajoutée d'office si le LLM l'oublie ; contrôles `unsourced_page` et `uncited_source` sans LLM | Chaque page reste reliée à sa source. |
| **Collecte RSS polie** : ETag, 304, timeout, User-Agent, Readability, pas d'historique au premier ajout (`rss-worker.ts:76-213`) | Directement transposable (feedparser + trafilatura). |
| « Daily Brief » : pages modifiées depuis N heures, puis synthèse citée | Le modèle de « quoi de neuf cette semaine », à refaire sur une vraie requête SQL. |
| Règle de prompt « document the shape of things, never live values » | Ne pas figer dans le wiki des valeurs qui changent. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| **Le RSS compilé automatiquement dans le wiki** (`capture-worker.ts`) | Exactement ce que K-B a écarté. |
| Aucune base pour les items de veille, dédup gardée en mémoire 5 minutes | Un item revient au redémarrage. |
| Statut porté par le déplacement dans `processed/` et `failed/` | L'équivalent du `.done` écarté. |
| « Stale » calculé sur l'âge de la page seulement (`lint.ts:162-163`) | La péremption doit comparer à des sources plus récentes. |
| **API d'environ 40 groupes de routes sans authentification**, écoute sur toutes les interfaces, annonce mDNS | À l'opposé de C5, et un risque sur le réseau local. |

---

## 8 — `notfounnd/marc-server`

Un outil de coordination entre agents de code : chaque tâche est un fil Markdown fermé par un
résumé. Ce n'est pas un wiki mais un journal de décisions. 32 fichiers de tests, aucune CI.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **ADR « Markdown source de vérité, index dérivé reconstructible »** (`docs/adrs/0001-…`) | Notre principe, formulé et argumenté. |
| Reconstruction incrémentale par sha256, manifeste publié seulement après succès | Ne réindexer que ce qui a changé. |
| Écriture atomique (fichier temporaire + renommage) et verrous | Si la collecte planifiée et l'ingest manuel écrivent en même temps. |
| Constats d'audit au format `{severity, code, location, message, suggestion}` | Format de rapport de lint simple à reproduire. |
| Schéma en deux couches : partie régénérée par l'outil, section `Custom Rules` préservée | Pour notre `AGENTS.md` : séparer ce que l'outil écrit de ce que tu écris. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Vectoriel d'abord, le lexical ne fait que reclasser (`operations.ts:116-123`) | Un numéro de CVE absent des voisins vectoriels ne remonte jamais. |
| Index binaire de 7,5 Mo commité dans git, avec des chemins Windows | Contredit « dérivé reconstructible ». |
| « Gate » qui repose sur la bonne foi de l'agent (`responses.ts:38`) | De la politesse, pas un contrôle. |
| Jeton accepté dans l'URL | Il finit dans les logs. Pour C5 : en-tête et comparaison à temps constant. |

---

## 9 — `jp-lorenc1o/Eva-brain`

Une application macOS (Tauri, Rust + TypeScript) : un agent CLI entretient un wiki Markdown à
partir de `raw/`, dans un worktree Git isolé. L'implémentation la plus **défensive** du pattern.
39 tests Rust et 17 tests vitest, mais la CI ne les lance pas.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Le lint avant/après comme porte de fusion** : fusion automatique seulement s'il n'y a ni nouveau problème ni suppression, sinon attente de l'humain (`ingest.rs:3243`) | Le lint devient un critère d'acceptation, pas une option. |
| **Frontière d'écriture vérifiée après coup par Git** : « Prompts are instructions, not an access boundary » (`ingest.rs:1866-1896`) | Garantit l'immuabilité de `raw/` même si le LLM désobéit. |
| Une page d'analyse **générée par le code** à partir d'un JSON validé ; une citation inventée devient un lien brisé qui bloque la fusion | Vérifier les citations par le lint, sans score. |
| Un lint sémantique en lecture seule : « Do not use general-world knowledge to call a claim stale » | Le bon cadrage pour un futur lint de péremption par LLM : il propose, il n'écrit pas. |
| Schéma versionné (`eva.json`), refus d'opérer sur une version inconnue | Faire évoluer le format sans corrompre un vault ancien. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| « Déjà ingéré » = le nom du fichier apparaît dans `log.md` (`ingest.rs:4727`) | Recherche de sous-chaîne, fragile. |
| Un nouveau fichier du même nom est ignoré sans avertissement | Perte silencieuse d'une nouvelle version de source. |
| Chaque déclenchement ingère tout `raw/` d'un coup | Contraire à l'ingest unitaire. |
| Péremption confiée au seul LLM | K-B la veut calculée. |

---

## 10 — `Encod3d-Sec/ClaudeBrain`

Une base de connaissance et un outillage Claude Code pour le pentest (~517 pages). *Seul
l'outillage a été lu : l'agent d'analyse a été interrompu deux fois par le filtre de sécurité à
cause du contenu offensif du wiki. La fiche a été rédigée à partir de `scripts/` et `docs/`.*

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Péremption par classe de sujet** : 90 jours pour les sujets rapides (llm, mcp, ai…), 365 pour les autres (`scripts/freshness.py:22-24`) | La première règle de péremption **typée** rencontrée. Elle amorce la question ouverte « règles de péremption par type ». |
| **Date du frontmatter, jamais la date du fichier** (`freshness.py:5-7`) | Le commentaire explique pourquoi la date du fichier ment. |
| Un signal en lecture seule : le script signale, il n'édite jamais | La décision reste humaine. |
| `gen_index.py --check` échoue si l'index a divergé (`gen_index.py:14`) | Un index qui se vérifie en CI. |
| Un seul chemin d'écriture dans `wiki/`, avec staging et promotion (`wiki-promote.py:4`) | La même idée que la porte de fusion d'Eva-brain. |
| `sources: []` dans le frontmatter comme registre d'ingest (`docs/page-types.md:15-19`) | Savoir qu'une source a déjà nourri une page sans relire la page. Une alternative propre au `.done`. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| `raw/` hors versionnement (`.gitignore:22-25`) | Plus de couche source immuable et citable. |
| Installation qui modifie la configuration globale de Claude Code | Couplage fort. |
| 77 fichiers de tests, aucune CI | Les tests ne protègent rien s'ils ne tournent pas. |

---

## 11 — `OrangeproAI/orangepro-mcp`

Un outil d'analyse de couverture de tests pour dépôts de code (TypeScript, 164 fichiers de
tests, CI avec un contrôle de confidentialité). Pas un wiki, mais son mécanisme de fraîcheur est
transposable tel quel.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Chaîne de péremption déterministe** : hash par fichier → état fresh / stale / missing → tout élément dérivé d'une source modifiée passe `stale` (`operations.ts:3043-3050`) | Une page du wiki qui cite une source modifiée passe `stale` dans son frontmatter, sans LLM. |
| Le rescan remplace la couche automatique et **préserve la couche manuelle** | Nos deux flux : recalculer la veille sans toucher aux dépôts manuels. |
| Chaque identifiant cité par le LLM est résolu contre la base ; les inconnus sont signalés, jamais ignorés | Le lint des sources inventées. |
| **Provenance en labels posés par le code** (`hard`, `reviewed`, `weak`, `ai_suggested`) ; ce qui vient du LLM ne compte jamais comme preuve | La bonne réponse à la question de la confiance, sans chiffre. |
| Un **fournisseur de modèle factice hors ligne** pour les tests | CI et tests sans clé API ni coût. À reproduire en Python. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Champ `confidence` numérique renvoyé par le LLM (`links.ts:660`) | Exclu, même atténué par un label. |
| Télémétrie activée par défaut | Pour un outil personnel et le RGPD : opt-in explicite. |
| Un « journal » `ledger.json` réécrit en entier | `log.md` doit rester en ajout seul. |
| Fichiers de plus de 3 000 lignes | Indéfendables en soutenance. |

---

## 12 — `Astro-Han/karpathy-llm-wiki`

Une « skill » (un `SKILL.md` que suit l'agent de code) et un seul script Python, testé par 52
tests unitaires. Pas de CI. La note du 2026-08-01 la jugeait « la plus instructive ».

### Correction de la note du 2026-08-01

La note écrit que ce projet a **« retiré »** des fonctions après trois mois de logs. Le README dit
autre chose : « **Deliberately not built**, after three months of production logs and a survey of
the ecosystem » (`README.md:126`). Ce sont des fonctions **jamais construites**, et la
justification mêle usage réel et revue d'autres projets :

| Élément écarté | Ce que dit le README |
|---|---|
| Recherche vectorielle | Confirmé, **à une échelle précise** : « at 50K–100K tokens of curated wiki, grep and read are more reliable » (`:135`). Ne vaut pas tel quel pour une base d'items de veille qui grossit chaque jour. |
| Scores de confiance | Confirmé mot pour mot : « false precision with no calibration behind it » (`:130`). |
| Ancres de numéro de ligne | Confirmé, et c'est le seul argument vraiment tiré des logs (`:129`). |
| Suivi par hash de source | Argument de conception (`raw/` est immuable), pas constat d'usage (`:128`). |
| Planification automatique | Écartée parce qu'une skill ne peut pas planifier, pas après un échec (`:134`). |
| 94 articles, 99 sources | Affirmé par l'auteur, invérifiable avec le seul dépôt (`:42-46`). |

Le fond ne change pas ; la formulation de la note est à corriger.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| **Invariant de fidélité vérifié par script** : chaque nombre, date ou citation du wiki doit exister mot pour mot dans la source brute liée (`scripts/check_evidence.py`) | Très pertinent pour la veille : versions, numéros de CVE, scores CVSS, dates de release. À compléter d'un motif `CVE-\d{4}-\d+`. |
| L'en-tête de métadonnées de la source est retiré avant la vérification (`check_evidence.py:282-287`) | Sinon une date de collecte « valide » à tort une date inventée. Un piège qu'on aurait eu. |
| **Triage New / Update / Disputed / No material** avant d'écrire (`SKILL.md:64-73`) | Le cas « rien de nouveau » est courant en veille. |
| **Blocs `Status: Outdated (date)` / `Disputed`** au lieu de réécrire | L'historique d'une version ou d'une CVE reste lisible dans Obsidian. |
| Lint en trois niveaux : correction automatique, rapport mécanique, jugement | Une séparation script / LLM transposable. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Métadonnées en citation Markdown plutôt qu'en frontmatter | Invalidables par script, invisibles pour Dataview. |
| Wiki découpé par thème | Nous découpons par type, avec les thèmes en tags. |
| Tout le pipeline repose sur l'agent, jusqu'aux corrections « sûres » | Chez nous, le mécanique est scripté. |
| Dédup par nom de fichier | Chez nous, par URL. |

---

## 13 — `toolboxmd/karpathy-wiki`

Un plugin d'agent (Codex d'abord, puis Claude Code et Grok) qui entretient un wiki Markdown
versionné. Beaucoup de tests, aucune CI, documentation en retard sur le code.

### Les trois points que la note du 2026-08-01 voulait reprendre

| Point | État actuel |
|---|---|
| `_index.md` récursifs par répertoire | **Présent**, générés par script (`wiki-build-index.py:150-232`), mais c'est l'agent qui doit penser à appeler le script. |
| Validation déterministe du frontmatter | **Renforcée** : désormais bloquante au commit (`wiki-commit.sh:42-73`). Mais elle exige un bloc `quality` noté de 1 à 5 par le LLM, contraire à nos décisions. |
| Règle d'orientation avant toute réponse | **Toujours une consigne de prompt** (« NO ANSWERING ANY USER QUESTION WITHOUT ORIENTING FIRST », `SKILL.md:33`), sans contrôle par le code. Elle a déjà été perdue une fois sans que personne s'en aperçoive (`README.md:344`). |

Le couplage a changé : il ne porte plus sur Claude Code, mais passe toujours par un agent CLI
détaché, **lancé avec ses garde-fous désactivés** (`--always-approve`, `danger-full-access`).

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| Les `_index.md` générés par script, lancés **par notre pipeline Python** et non par le LLM | Un catalogue toujours juste, qui passe à l'échelle. |
| Le validateur de page (champs requis, dates ISO, `type` = dossier, liens et sources résolus), **sans** le bloc `quality` | Le « déterministe d'abord ». |
| La validation imposée par une porte, pas par une consigne | Transforme une règle de prose en garantie. |
| Manifeste sha256 de `raw/` avec `referenced_by` | Savoir quelles pages refaire quand une source change. |
| L'orientation et le contrat de citation, **codés dans la commande query** | La commande lit le schéma et l'index avant d'appeler le modèle. |
| Benchmarks d'ingest avec fixtures `source.md` / `expected.yaml` | Comparer des modèles sur *notre* ingest avant d'en changer. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| **Un agent CLI sans garde-fous nourri de contenus non fiables** | Pour de la veille (RSS, newsletters, pages web), c'est une porte ouverte à l'injection de prompt. K-B appelle un modèle par API, avec des entrées et des sorties structurées, et c'est le code Python qui écrit. |
| Capture et ingest automatiques en arrière-plan | Contraire à l'ingest déclenché par l'humain. |
| Score `quality` noté par le LLM | Exclu. |
| Péremption traitée par le seul jugement du LLM | Il faut un mécanisme déterministe. |

---

## 14 — `akitaonrails/ai-memory`

Un binaire Rust (~167 000 lignes, CI stricte, ~3 470 tests) qui donne une mémoire partagée aux
agents de code, compilée en wiki Markdown versionné, indexé par SQLite. Son intérêt principal pour
K-B est sa **note de recherche**, que les notes du Drive citent déjà.

### Ce qu'apporte la note de recherche

- Elle sépare le gist de Karpathy de ce qu'on lui prête : « Confidence scoring, Ebbinghaus decay,
  supersession semantics — these are LLM Wiki v2's additions, not the original »
  (`docs/research-karpathy-llm-wiki.md:52`). **Notre refus des scores de confiance n'écarte donc
  rien du pattern original.**
- Elle reconnaît une tension : un agent qui ingère sans supervision remplit le wiki de pages
  périmées (`:94`).
- Sa suite (`docs/research-2026-landscape.md`) signale le format **OKF** de Google (juin 2026),
  très proche de ce que produit un LLM wiki, et la **validité bi-temporelle** : distinguer
  *quand un fait est vrai dans le monde* de *quand on l'a observé*, et marquer l'ancien fait comme
  remplacé au lieu de l'effacer (`:76`). C'est le bon cadre conceptuel pour la péremption en veille.

### À retenir pour K-B

| Élément | Pourquoi ça nous sert |
|---|---|
| Markdown = vérité, SQLite = index dérivé reconstructible | Notre règle pour Obsidian. |
| **FTS5 insensible aux accents** (`remove_diacritics 2`) | « securite » trouve « sécurité ». |
| Requête en langage naturel traduite en `OR` + bm25 plutôt qu'en `AND` | Sans ça, le rappel est quasi nul sur une vraie question. |
| Journal découpé par mois, préfixe grep-able | Un `log.md` qui ne grossit pas indéfiniment. |
| Surveillance des fichiers compatible Obsidian, qui n'écrit jamais | Prendre en compte les retouches faites à la main. |
| Prompt de fidélité : rien d'inventé, les sources sont des données et non des instructions | Le modèle de notre prompt d'ingest. |
| `DATA_HANDLING.md` (local par défaut, RGPD, rétention) | Un modèle de section RGPD pour la certification. |

### À éviter dans K-B

| Écueil | Pourquoi |
|---|---|
| Ingestion automatique par hooks, auto-approbation des propositions du LLM | Contraire à la supervision humaine. |
| Mémoire à décroissance et tiers de mémoire | Un autre problème : la mémoire d'agent. |
| Liens brisés signalés seulement entre projets, pas d'orphelins (`reader.rs:7081`) | Ces contrôles seront à écrire. |
| Mots vides en anglais seulement | Contenu FR/EN. |

---

## Gist `rohitg00` — « LLM Wiki v2 »

*Texte, pas de code, lu via la page du gist.* Tiré d'`agentmemory`, une mémoire pour **agents
autonomes**. Il propose des scores de confiance, une décroissance façon courbe d'Ebbinghaus, un
graphe typé, une recherche hybride, des hooks d'ingest et de lint automatiques, et affirme qu'un
`index.md` plat casse vers 200 à 500 documents. Les commentaires du gist lui opposent les objections
de production : la confiance chiffrée masque la preuve, les écritures pilotées par LLM se
corrompent en silence.

**K-B en garde** la supersession explicite (marquer l'ancien sans l'effacer), le seuil de l'index
plat (qui justifie l'index hiérarchique déjà acté) et la primauté du schéma. **K-B en écarte** le
scoring, la décroissance et l'automatisation, qui répondent à un autre cas d'usage.

---

## Ce qui converge

**1. Le Markdown fait foi, l'index se reconstruit.** marc-server, link, suwonleee, ai-memory,
toolboxmd le disent tous, souvent dans un ADR. Deux contre-exemples le confirment par l'échec :
llm-wiki-cli (Markdown écrasé à chaque projection) et WeKnora (wiki en base, illisible hors de
l'application).

**2. Le lint mécanique ne passe pas par le LLM.** WeKnora, llm-wiki-cli, link, mindbase, Eva,
ClaudeBrain, toolboxmd et Astro-Han séparent tous le contrôle par script (liens, orphelins,
frontmatter, index) du jugement par LLM (contradictions). La liste des règles est pratiquement la
même partout : on peut la considérer comme acquise.

**3. Une règle écrite en prose ne tient pas.** Le constat revient sous plusieurs formes :
« Prompts are instructions, not an access boundary » (Eva), la règle d'orientation perdue sans que
personne le remarque (toolboxmd), le « gate » déclaratif (marc-server), la cadence imposée par le
code « parce qu'une règle en prose s'applique au bon vouloir du modèle » (suwonleee). **Tout ce qui
compte doit être vérifié par du code** : la porte de fusion, le vocabulaire d'actions fermé, le
validateur au commit.

**4. On marque l'ancien, on ne l'efface pas.** `superseded_by` (knowledge-agent-template,
suwonleee, link), `Status: Outdated` (Astro-Han), `⚠️ Contradicts` (cortexes), « Contradictions /
Updates » (WeKnora), la validité bi-temporelle (ai-memory). C'est la forme que doit prendre la
péremption dans le wiki de K-B.

**5. Le refus du score de confiance produit par le LLM est largement partagé** chez ceux qui ont
un usage réel : Astro-Han, suwonleee (qui l'interdit par lint), orangepro (labels posés par le code).
Ceux qui l'utilisent (link, llm-wiki-cli, toolboxmd, orangepro sur les liens) ne le justifient pas.

**6. L'ingest automatique est la pente naturelle.** WeKnora, mindbase v1, cortexes, ai-memory,
toolboxmd, suwonleee y vont tous. mindbase a fait le chemin inverse après pivot : le LLM propose un
plan, l'humain coche, le code applique. C'est notre choix.

---

## Où se situe K-B

### Ce que personne ne traite

| Point | Détail |
|---|---|
| **La veille elle-même** | Aucun des quatorze ne stocke d'items datés interrogeables par période. Aucun ne sait répondre à « quoi de neuf cette semaine » par une requête. Aucun connecteur releases GitHub, CVE, newsletter ou YouTube. |
| **La péremption des faits de veille** | Les mécanismes existants datent des **fichiers** (hash, date de mise à jour) ou des **pages** (âge). Aucun ne date un **fait** par sa source (date de publication d'une release, d'une CVE). Même la règle de link sur `date_published` n'est pas codée. |
| **Date de publication ≠ date de collecte** | WeKnora les confond pour le RSS, llm-wiki-cli n'a que la date d'ingestion. K-B a besoin des deux, typées. |
| **Base de données modélisée + API REST authentifiée** | Seul WeKnora a les deux (et un OpenAPI testé), dans une architecture d'entreprise hors de proportion. C'est aussi ce qu'attend la certification. |

### Ce qui existe et qu'on assemble

| Brique | Où la prendre |
|---|---|
| Lint déterministe (liste des règles) | WeKnora, llm-wiki-cli (en SQL), link, mindbase |
| Validation du frontmatter par type, bloquante | link, toolboxmd |
| `index.md` et `_index.md` générés par script, vérifiés en CI | link, toolboxmd, ClaudeBrain |
| `log.md` en ajout seul, grep-able, éventuellement chaîné | link, ai-memory, Eva |
| Porte de fusion par lint avant/après | Eva, ClaudeBrain |
| Péremption par classe de sujet, datée par le frontmatter | ClaudeBrain |
| Propagation de la péremption aux pages dérivées | suwonleee, orangepro |
| Fidélité : valeurs vérifiées mot pour mot contre la source | Astro-Han, mindbase, suwonleee |
| Collecte RSS polie et incrémentale | WeKnora, mindbase |
| Recherche lexicale FTS5, accents, `OR` + bm25 | ai-memory, suwonleee |
| Banc d'évaluation de la recherche | cortexes |
| Masquage des secrets avant envoi au LLM | link, cortexes, orangepro, ai-memory |
| Fournisseur de modèle factice pour les tests | orangepro |

---

## Ce que la veille révèle comme manquant

Rien ici n'est une décision : ce sont des sujets à instruire.

| # | Sujet | Source | Échéance probable |
|---|---|---|---|
| 1 | **Le modèle d'item de veille** : colonnes typées `published_at`, `fetched_at`, `url_canonique`, `source`, `hash`. Aucun existant ne le fournit. | constat d'absence ; contre-exemples WeKnora, llm-wiki-cli | avant la première collecte |
| 2 | **La table des classes de péremption** : ClaudeBrain donne un point de départ (90 j / 365 j) ; il faut une ligne par type (CVE, release, framework, réglementation). Répond à la question ouverte n°4 du 01/08. | ClaudeBrain | avec le schéma du frontmatter |
| 3 | **Péremption des faits, pas des fichiers** : combiner la date de la source (bi-temporel) et la propagation aux pages dérivées. | ai-memory, suwonleee, orangepro | après le premier ingest |
| 4 | **La porte de fusion** : lint avant/après l'ingest, fusion seulement sans nouveau problème. | Eva, ClaudeBrain | avec la commande ingest |
| 5 | **Le vocabulaire d'actions fermé** : le LLM propose un plan structuré, le code l'applique et ne peut jamais toucher `raw/`. | mindbase | avec la commande ingest |
| 6 | **Le vérificateur de fidélité** : toute valeur (version, CVE, date) doit exister dans la source ; retirer l'en-tête avant de comparer. | Astro-Han | avec la commande ingest |
| 7 | **La tokenisation française** : aucun existant n'a de mots vides ni de racinisation en français. FTS5 `remove_diacritics` ou trigrammes. | ai-memory, suwonleee ; contre-exemples knowledge-agent-template, cortexes | avec la recherche |
| 8 | **Le banc d'évaluation de la recherche**, avant tout passage au vectoriel : c'est lui qui tranchera la question du « RAG » sur la veille. | cortexes ; condition d'échelle d'Astro-Han | quand la base aura quelques centaines d'items |
| 9 | **Corriger la note du 2026-08-01, §6** : « retiré » → « jamais construit », et la condition d'échelle de « grep suffit ». | Astro-Han | à la prochaine reprise des notes |
| 10 | **Sécurité du contenu entrant** : la veille injecte du texte non fiable ; jamais d'agent CLI sans garde-fous, sources traitées comme des données. | toolboxmd (contre-exemple), ai-memory | avant la première collecte |

## Sources

Relevé le 2026-09-23 pour toutes les sources.

| Source | Adresse |
|---|---|
| `j-wang/knowledge-agent-template` | <https://github.com/j-wang/knowledge-agent-template> |
| `Tencent/WeKnora` | <https://github.com/Tencent/WeKnora> |
| `JanYork/llm-wiki-cli` | <https://github.com/JanYork/llm-wiki-cli> |
| `suwonleee/llmwiki` | <https://github.com/suwonleee/llmwiki> |
| `XBlueSky/cortexes` | <https://github.com/XBlueSky/cortexes> |
| `gowtham0992/link` | <https://github.com/gowtham0992/link> |
| `frankchu91/mindbase` | <https://github.com/frankchu91/mindbase> |
| `notfounnd/marc-server` | <https://github.com/notfounnd/marc-server> |
| `jp-lorenc1o/Eva-brain` | <https://github.com/jp-lorenc1o/Eva-brain> |
| `Encod3d-Sec/ClaudeBrain` | <https://github.com/Encod3d-Sec/ClaudeBrain> |
| `OrangeproAI/orangepro-mcp` | <https://github.com/OrangeproAI/orangepro-mcp> |
| `Astro-Han/karpathy-llm-wiki` | <https://github.com/Astro-Han/karpathy-llm-wiki> |
| `toolboxmd/karpathy-wiki` | <https://github.com/toolboxmd/karpathy-wiki> |
| `akitaonrails/ai-memory` | <https://github.com/akitaonrails/ai-memory> |
| Gist « LLM Wiki v2 » (rohitg00) | <https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2> |
| Gist « LLM Wiki » (Karpathy), étalon | <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f> |
