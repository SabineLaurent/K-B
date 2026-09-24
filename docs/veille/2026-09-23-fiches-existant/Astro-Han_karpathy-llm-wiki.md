# Fiche de veille — Astro-Han/karpathy-llm-wiki

Dépôt : https://github.com/Astro-Han/karpathy-llm-wiki — analysé le 2026-09-23 sur un clone `--depth 1` (lecture seule, rien exécuté).

## 1. Identité

- **Pitch** : une *skill* au format Agent Skills (agentskills.io), c'est-à-dire un `SKILL.md` de consignes que l'agent de code (Claude Code, Cursor, Codex…) suit pour faire ingest / query / lint sur un wiki `raw/` → `wiki/`. Ce n'est pas une application : le LLM fait tout le travail, sauf un seul script Python déterministe qui vérifie les preuves.
- **Pile technique** : Markdown (consignes + gabarits) et un script Python 3 sans dépendance (`scripts/check_evidence.py`, 431 lignes, stdlib seule : `re`, `pathlib`, `dataclasses`), testé avec `unittest` (`tests/test_check_evidence.py`, 765 lignes, 52 `def test`).
- **Dernier commit** : `eafcc77` du 2026-07-24 (« fix: align log inventory and examples »). Clone superficiel, donc **l'historique n'est pas consultable**.
- **Fichiers** : 16 (hors `.git`). Licence MIT (`LICENSE:1-3`, © 2026 Yuhan Lei).
- **Maturité** : spécification soignée et précise (`SKILL.md`, 233 lignes), vrais tests pour le script, exemples tirés d'un wiki réel. **Pas de CI** (aucun dossier `.github/`). Pas de `pyproject`/`requirements` (inutile ici : stdlib seule).

## 2. Architecture

```
SKILL.md                     ← le « schéma » : toutes les règles ingest/query/lint (c'est le produit)
references/
  raw-template.md            ← en-tête d'une source : Source / Collected / Published
  article-template.md        ← article : Sources / Raw / Updated + blocs Status Outdated/Disputed
  archive-template.md        ← réponse de query archivée (Sources = articles wiki, pas de Raw)
  index-template.md          ← index.md : une table par thème, colonnes Article | Summary | Updated
scripts/check_evidence.py    ← SEUL code : vérif. déterministe « chaque nombre/date/citation du wiki existe mot pour mot dans le raw lié »
tests/test_check_evidence.py ← 52 tests unittest du script
examples/                    ← un vrai article, sa source brute, un extrait d'index, un extrait de log
README.md                    ← pitch + section « Design Boundaries » (ce qui n'a pas été construit, et pourquoi)
```

**Flux principal (d'une source à la réponse)** :
1. *Fetch* : l'agent récupère l'URL/le fichier avec ses propres outils et l'écrit dans `raw/<thème>/AAAA-MM-JJ-slug.md` avec un en-tête blockquote (`SKILL.md:49-62`, `references/raw-template.md:3-5`).
2. *Triage* : recherche des entités et synonymes dans `wiki/`, puis décision explicite **New / Update / Disputed / No material** (`SKILL.md:64-73`). « No material » : on garde le raw, on journalise, on s'arrête (`SKILL.md:71`).
3. *Compile* : fusion ou création d'article, avec la règle de fidélité « locate before write » : toute valeur est retrouvée dans le raw (grep) avant d'être écrite, sous sa forme exacte (`SKILL.md:85`).
4. *Cascade* : recherche plein texte des autres articles touchés ; l'ancienne affirmation est conservée avec un bloc `Status: Outdated` (daté) ou `Disputed` : « Never silently rewrite history » (`SKILL.md:92-98`, `references/article-template.md:17-21`).
5. *Post-ingest* : mise à jour de `index.md` + ajout au `log.md` dans un format fixe (`SKILL.md:100-120`).
6. *Query* : `index.md` puis recherche plein texte avec synonymes → lecture → réponse citée ; aucune écriture sauf archivage demandé (`SKILL.md:139-160`).
7. *Lint* : trois niveaux d'autorité : corrections sûres automatiques (index, liens, Raw, See Also), rapports mécaniques via `check_evidence.py`, rapports de jugement laissés au LLM sans correction (`SKILL.md:164-215`).

**Le script** (`scripts/check_evidence.py`) : il analyse chaque article (titre H1, en-tête blockquote, corps, en ignorant les blocs de code : `parse_document`, l.96), extrait un ensemble **fermé** de candidats (citations de 15 caractères ou plus, dates ISO, nombres à suffixe/séparateur/décimale ou de 4 chiffres ou plus : docstring l.18-26, `keep_number` l.173-177), et cherche chacun mot pour mot dans le corps des raw liés, **sans leur en-tête de métadonnées** pour ne pas valider à tort des dates (`source_content` l.282-287). Il signale aussi les articles sans Raw ou avec un Raw qui sort de `raw/` (`check_article` l.290-315) et les raw jamais référencés, sauf ceux journalisés « no material », retrouvés en analysant le titre de log (`NO_MATERIAL_HEADING_RE` l.53-55, `unreferenced_raws` l.345). Rapport seul, jamais de modification ; « The exit code carries no information » (l.28).

## 3. Rapport au pattern Karpathy

| Élément du gist | Ici | Commentaire |
|---|---|---|
| `raw/` immuable | **Présent** (`SKILL.md:18`) | Immuabilité posée comme invariant, et utilisée pour justifier l'absence de hash (`README.md:128`). |
| `wiki/` compilé | **Présent**, un seul niveau `wiki/<thème>/` (`SKILL.md:20`, `:230`) | Découpage **par thème**, pas par type de page (≠ décision K-B). |
| Schéma (AGENTS.md) | **Transformé** : c'est le `SKILL.md` lui-même (`SKILL.md:24`) | Portable d'un agent à l'autre, mais le schéma est celui de la skill, pas celui du projet de l'utilisateur. |
| ingest / query / lint | **Présents**, plus une variante *Research* multi-sources (`SKILL.md:122-128`) et l'*archivage* de réponses (`SKILL.md:146-160`) | Le triage « No material » est un ajout utile par rapport au gist. |
| `index.md` | **Présent**, tables par thème avec date `Updated` (`references/index-template.md`) | |
| `log.md` append-only | **Présent**, format lisible par machine (`SKILL.md:104-120`) | Le titre « no material » sert de clé d'inventaire au script : le log est devenu une donnée, pas seulement un journal. |
| Obsidian | **Absent** | Liens markdown relatifs standards (`SKILL.md:229`), pas de wikilinks : compatible Obsidian mais sans rien de spécifique. |
| Frontmatter YAML | **Absent** : métadonnées en blockquote `> Raw:` / `> Updated:` | Moins validable par un outil standard qu'un frontmatter. |

## 4. Vérification des affirmations de la note de conception (2026-08-01)

| Affirmation | Verdict | Où |
|---|---|---|
| Usage quotidien depuis avril 2026, ~94 articles, 99 sources | **Confirmé (affirmation de l'auteur, non vérifiable)** | `README.md:42-46` (94 articles / 13 thèmes / 99 sources / 87 entrées de log sur 7 jours), `README.md:122`. Le dépôt ne contient que 2 fichiers d'exemple de ce wiki : impossible de vérifier les chiffres. |
| Il a « RETIRÉ » des fonctions après trois mois de logs | **Nuancé** | Le README dit « **Deliberately not built**, after three months of production logs and a survey of the ecosystem (LLM Wiki v2, llm-wiki-compiler, OKF, agent-memory literature) » (`README.md:126`). Ce sont des choses **jamais construites** (écartées), pas des fonctions retirées ; et la justification mêle logs et revue de l'écosystème. Historique indisponible (clone `--depth 1`) : je n'ai pas pu vérifier si certaines ont existé un moment. |
| Recherche vectorielle : « grep and read are more reliable » | **Confirmé, avec condition** | `README.md:135` : « at 50K–100K tokens of curated wiki, grep and read are more reliable. Add search tooling only when recall measurably degrades. » La réserve d'échelle (50-100K tokens) est essentielle ; « graph search » est écarté aussi. |
| Suivi par hash de source | **Confirmé, mais le motif n'est pas empirique** | `README.md:128` : raw/ immuable, donc les hash « guard against events that cannot happen ». C'est un argument de conception, pas un constat tiré des logs. Cohérent avec `SKILL.md:41` (« no incremental state to maintain »). |
| Scores de confiance : « fausse précision sans calibration » | **Confirmé** | `README.md:130` : « false precision with no calibration behind it. Evidence strength belongs in the prose. » |
| Ancres de numéro de ligne | **Confirmé, argument le plus empirique** | `README.md:129` : toutes les erreurs de fidélité observées étaient « value absent from the source », ce qu'un grep sur le fichier entier détecte ; en plus, la friction d'annotation poussait les agents à sauter la règle. Mis en œuvre par `check_evidence.py` (`contains`, l.270). |
| Dates de revue par article | **Confirmé** | `README.md:131` : impossible de prévoir la vitesse d'un domaine à la compilation ; maintenance par lint global. Mais il existe une date `Updated` par article (`references/article-template.md:5`) : c'est une date de dernière modification, pas une échéance. |
| Planification automatique | **Nuancé** | `README.md:134` : « Automatic hooks and scheduled runs — those belong to the agent harness, not a tool-agnostic skill. » C'est une question de **périmètre** (une skill ne peut pas planifier), pas un constat d'échec dans les logs. |
| Non cité dans la note, mais présent | — | Autres éléments écartés : « Access-based decay » (`README.md:132`), mécanisme de rétractation (`:133`), ontologies de relations typées (`:136`), OKF (`:137`), MCP/UI (`:138`). |

Aucune trace de ces mécanismes dans le code : un grep de `vector|hash|confidence|schedul|decay|line-number` sur `SKILL.md`, `scripts/`, `tests/`, `references/` et `examples/` ne renvoie rien en dehors de `README.md:128-135`.

## 5. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| **Invariant de fidélité vérifié par script** : chaque nombre, date ou citation du wiki doit apparaître mot pour mot dans le raw lié | Exactement « déterministe d'abord » ; très pertinent pour la veille (versions, numéros de CVE, scores CVSS, dates de release). À ajouter : un motif pour les identifiants `CVE-\d{4}-\d+`. | `SKILL.md:39-41`, `scripts/check_evidence.py:18-26`, `:290-315` |
| Ignorer l'en-tête de métadonnées du raw pendant la vérification | Évite qu'une date de collecte « valide » à tort une date inventée : piège subtil qu'on aurait eu | `scripts/check_evidence.py:282-287` |
| Ensemble fermé de candidats (« frozen ») plutôt qu'une extraction ouverte | Script prévisible et testable ; les cas limites vont à la revue humaine ou LLM | `scripts/check_evidence.py:18-26` |
| Triage explicite **New / Update / Disputed / No material** avant d'écrire | Le cas « rien de nouveau » est courant en veille (un article qui recopie une annonce) ; on garde la source sans polluer le wiki | `SKILL.md:64-73` |
| Blocs `Status: Outdated (date)` / `Disputed` au lieu de réécrire | Répond directement à la **péremption** : l'historique d'une version ou d'une CVE reste lisible dans Obsidian | `SKILL.md:96`, `references/article-template.md:17-21` |
| Inventaire des raw orphelins, sauf ceux journalisés « no material » | Transforme le log en file d'attente vérifiable par script (backlog d'ingest) | `scripts/check_evidence.py:324-356` |
| Lint en trois niveaux d'autorité (correction auto / rapport mécanique / jugement) | Bonne séparation script ↔ LLM, directement transposable | `SKILL.md:166-215` |
| Section « Design Boundaries » : chaque refus avec sa raison | Modèle pour nos ADR, et conforte nos décisions (lexical d'abord, pas de score de confiance LLM) | `README.md:124-138` |
| Query : ne jamais dire « rien trouvé » avant index **et** plein texte avec synonymes | Règle simple contre les faux négatifs en recherche lexicale (utile en FR/EN) | `SKILL.md:141` |
| Compilation séquentielle obligatoire, même si la collecte est parallèle | index/log/cascade sont un état partagé : ça vaudra pour notre pipeline | `SKILL.md:128` |
| Suite de tests unitaires du vérificateur (52 tests) | Exemple de ce qu'on doit tester côté déterministe (limites de nombres, blocs de code, en-têtes) | `tests/test_check_evidence.py:208-765` |

## 6. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Tout le pipeline dépend de l'agent (fetch, index, log, liens) | K-B a une collecte automatique en base et des scripts pour tout ce qui est mécanique ; ici même les corrections « sûres » de lint (index, liens) sont faites par le LLM | `SKILL.md:51`, `SKILL.md:168-191` |
| Métadonnées en blockquote (`> Raw:`), pas en frontmatter YAML | Nous avons décidé d'un statut dans le frontmatter, validable par script et exploitable par Obsidian (Properties/Dataview) | `references/article-template.md:3-5`, `scripts/check_evidence.py:48` |
| Wiki découpé par thème, un seul niveau | Nous découpons par type de page, avec les thèmes en tags | `SKILL.md:20`, `:230` |
| Pas de base de données, pas de requêtes temporelles | Le « quoi de neuf cette semaine » et les comptages de la veille sont hors de son périmètre (il fait de la recherche, pas de la veille) | `SKILL.md:132-144` |
| Justifications à reprendre avec leur contexte, pas comme des dogmes | « grep suffit » vaut pour 50-100K tokens de wiki trié, pas pour une base d'items de veille qui grossit chaque jour ; « pas de planification » est une limite de périmètre de skill, pas une conclusion générale | `README.md:134-135` |
| Dédoublonnage des sources par nom de fichier (suffixe `-2`) | Pas de dédup par URL : chez nous, c'est un script | `SKILL.md:58` |
| Vérificateur qui ne contrôle pas les petits entiers ni les formes « exotiques » | Couverture partielle assumée ; un numéro de version comme `v3` ou « 42 failles » passerait sans contrôle | `scripts/check_evidence.py:23-25` |
| Aucune CI | Les 52 tests existent mais ne sont lancés automatiquement nulle part ; pour la certification, il nous faut une CI | absence de `.github/` |
| Exemples peu cohérents à la marge | L'article d'exemple cite deux dates de source (`2026-03-19; 2026-03-24`) mais un seul raw : la règle « chaque source a son raw » n'est pas visible dans l'exemple | `examples/claude-code-statusline-landscape.md:3-4` |

## 7. En une phrase

K-B retient surtout l'**invariant de fidélité vérifié par un script** (toute valeur du wiki se retrouve mot pour mot dans un raw immuable), le **triage New/Update/Disputed/No material** et les **blocs Status Outdated/Disputed** contre la péremption, en lisant ses « Design Boundaries » comme des choix jamais construits et liés à l'échelle d'un wiki trié de 50-100K tokens, pas comme des fonctions retirées après usage.
