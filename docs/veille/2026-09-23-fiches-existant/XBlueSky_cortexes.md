# Fiche de veille — XBlueSky/cortexes

> Clone `--depth 1`, lu sans rien exécuter. Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : un plugin Claude Code qui enregistre automatiquement chaque session de travail sous forme de « Raw » markdown dans un vault Obsidian versionné par git. Des skills LLM « distillent » ensuite ces Raw en pages `Notes/` et `Projects/`, puis les fusionnent dans les pages existantes (« broadcast », dans l'esprit llm-wiki). La recherche est hybride : BM25 et vecteurs, fusionnés par RRF.
- **Pile technique** : Python ≥ 3.10 pour la CLI `cortex-vec` (PyPI), qui s'appuie sur `chromadb`, `openai`, `python-frontmatter`, `rank-bm25`, `jieba` et `snowballstemmer` (`cortex-vec/pyproject.toml:19-27`). Les hooks sont en Bash et en Python. Les skills et commandes sont des fichiers markdown (prompts). Le site statique est en Node (`site/`).
- **Dernier commit** : 2026-09-22 (`ff2eaeb`, merge PR #21). Le CHANGELOG remonte à 0.4.0 (2026-04-11) et s'arrête à 2.1.0 (2026-09-22) (`CHANGELOG.md:8`, `:1236`). Le projet est donc très actif, avec beaucoup de versions sur 5 mois.
- **Taille** : 245 fichiers, dont environ 3 400 lignes de Python dans `cortex-vec/src` et un gros hook `hooks/scripts/filter-transcript.py` (938 lignes).
- **Licence** : Apache-2.0 (`LICENSE`, `NOTICE`).
- **Maturité** : élevée pour un projet perso.
  - Environ 538 fonctions de test (`tests/` et `cortex-vec/tests/`).
  - CI GitHub Actions ruff + pytest (`.github/workflows/python.yml`) qui réutilise `scripts/run-checks.sh`, le même script que le pre-commit.
  - Doc abondante : README EN/zh-TW, `PRIVACY.md`, `SECURITY.md`, `docs/index-audit.md`.
  - Commentaires de code souvent en chinois traditionnel.

## 2. Architecture

```
hooks/
  hooks.json                    SessionStart / SessionEnd
  scripts/session-end-record.sh fin de session → filtre → Raw/AAAA/MM/JJ/*.md + git commit
  scripts/filter-transcript.py  pipeline TOML (filters/*.toml) + redaction de secrets + classifieur LLM optionnel
  scripts/session-start-inject.sh  menu interactif « charger la mémoire ? »
commands/*.md                   /cortexes:genesis|evolve|distill|query|broadcast|takeoff
skills/*/SKILL.md               protocoles LLM (distill : 480 l., broadcast : 358 l.)
cortex-vec/src/cortex_vec/
  store.py      ChromaDB + embeddings OpenAI + résumé bilingue LLM (double vecteur)
  bm25.py       index BM25 picklé + évaluateur de filtres commun aux 3 flux
  fusion.py     RRF vector/bm25/(graph), rerank LLM optionnel
  tokenize.py   jieba (han) + Porter (latin)
  graph.py      graphe des wikilinks
  distill_queue.py / reclaim.py / raw_*.py / distill_plan.py   navigation bornée dans un Raw
  eval/         banc d'évaluation P@k / R@k / MRR
```

Côté vault : `Raw/AAAA/MM/JJ/`, `Notes/<catégorie>/`, `Projects/<repo>/`, `_index.md` et `log.md` (`README.md`, section « Vault Structure »).

**Flux principal, de la source à la réponse :**

1. **Capture automatique.** En fin de session, le hook enregistre toute session de plus de 4 Ko (`hooks/scripts/session-end-record.sh:53`) et ignore les sessions headless (`:47`). Il filtre le transcript, masque les secrets (`hooks/scripts/filter-transcript.py:675-727`), écrit le Raw puis fait un `git add` et un `git commit` dans le vault (`session-end-record.sh:327-328`).
2. **Distill**, déclenché par l'humain (`skills/cortex-distill/SKILL.md`).
   - La file d'attente est calculée de façon déterministe à partir d'un marqueur `<!-- distilled: ... -->` (`cortex-vec/src/cortex_vec/distill_queue.py:45`).
   - Le LLM parcourt le Raw par cartes et pages bornées (`raw-map` / `raw-span`), sans jamais lire le fichier entier (`SKILL.md:101-104`).
   - Une règle explicite `has_insight()` décide s'il y a quelque chose à retenir (`:189`).
   - Une recherche de doublons compare le score au top-1 avec deux seuils, 0.45 et 0.60 (`:273-277`, `:318-320`). Il en sort quatre issues : `new`, `pending-merge`, `skip-routine` ou `no-insight`, toujours confirmées par l'humain (`:302-304`).
   - Viennent ensuite l'écriture de la page, le marqueur dans le Raw (`:363-365`), une ligne dans `_index.md` (`:370`), une entrée dans `log.md` (`:385-394`) et un commit.
3. **Broadcast.** Il cherche les pages candidates au-dessus de 0.40, présente un menu à cocher, puis propose des modifications page par page, que l'humain valide par oui ou non. Un conflit donne un drapeau `⚠️ Contradicts [[raw]]`, sans écrasement silencieux. Chaque page est ré-indexée puis commitée, et le marqueur `| broadcast:` est ajouté (`skills/cortex-broadcast/SKILL.md:20-24`, `:160-175`, `:224-238`, `:268-285`).
4. **Query.**
   - `cortex-vec search` fusionne BM25 (poids 0.4) et vecteurs (poids 0.6) par RRF avec k=60 (`cortex-vec/src/cortex_vec/fusion.py:8-26`, `config.py:13-28`).
   - Sans `OPENAI_API_KEY`, la recherche passe en BM25 seul (`fusion.py:40-49`).
   - Un graphe de wikilinks et un rerank LLM existent en option, désactivés par défaut.

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans cortexes | Verdict |
|---|---|---|
| `raw/` immuable | `Raw/AAAA/MM/JJ/`, mais **modifié** : marqueurs HTML ajoutés au fichier (distill, puis broadcast), et suppression des Raw qui ne sont que le préfixe d'un autre (`reclaim.py:1-30`) | Transformé : raw mutable, non immuable |
| `wiki/` compilé par le LLM | `Notes/<catégorie>/` + `Projects/<repo>/`, en markdown Obsidian avec wikilinks | Présent (découpé par catégorie ou par repo, pas par type de page) |
| Schéma (AGENTS.md) | Réparti dans les `skills/*/SKILL.md` et `commands/*.md`, sans fichier de schéma unique | Transformé (dispersé) |
| ingest | Scindé en deux : **distill** (Raw → nouvelle page ou pending-merge) puis **broadcast** (propagation dans les pages existantes) | Présent, plus fin que Karpathy |
| query | `/cortexes:query` avec recherche hybride, repli sur grep | Présent |
| lint | **Absent.** Les tags de distill sont « réservés pour un futur lint » (`skills/cortex-distill/SKILL.md:262`). L'audit de `_index.md` est un runbook Python à lancer à la main (`docs/index-audit.md`) | Absent |
| `index.md` | `_index.md`, tableau `\| [[titre]] \| tags \| résumé \|` maintenu par le LLM et régénéré par genesis (`commands/genesis.md:113-148`) | Présent, sans vérification automatique (README, section « Vault Structure ») |
| `log.md` | Journal en ajout seul, avec des entrées structurées `## [date] distill\|broadcast \| raw` (`skills/cortex-broadcast/SKILL.md:296-302`) | Présent, bien formalisé |
| Obsidian | Vault = markdown Obsidian + git, le vecteur est un index dérivé qu'on peut reconstruire (README, « Design philosophy ») | Présent |

**Veille** : absente. Le projet sert de mémoire des sessions Claude Code. Il n'y a ni collecte externe (RSS, CVE, releases), ni items datés interrogeables par période, ni gestion de la péremption. La date n'apparaît que dans le chemin des Raw.

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Ingest en deux temps : distill (créer ou mettre en attente de fusion) puis broadcast (propager) | Sépare « faut-il une nouvelle page ? » de « quelles pages existantes mettre à jour ? ». Utile pour la péremption : un nouveau document peut modifier plusieurs pages anciennes | `skills/cortex-distill/SKILL.md:264-330`, `skills/cortex-broadcast/SKILL.md` |
| Drapeau de contradiction inline `⚠️ Contradicts [[source]]` plutôt qu'un écrasement silencieux | Trace le vieillissement de l'information (version ou CVE dépassée) sans perdre l'ancien énoncé. Proposé par le LLM, tranché par l'humain | `skills/cortex-broadcast/SKILL.md:224-238` |
| Doublons repérés par un seuil sur la similarité du top-1, trois issues, décision toujours humaine | Correspond à l'ingest unitaire déclenché par l'humain. Le seuil est configurable (`distill.dedup_threshold_*`) | `skills/cortex-distill/SKILL.md:273-320` |
| File d'attente calculée par script à partir de l'état du fichier, avec l'interdiction explicite d'utiliser grep | Principe « déterministe d'abord ». Leçon aussi : leur marqueur dans le corps est cité ailleurs dans le texte, d'où un parseur de position dédié. Notre choix du frontmatter évite ce piège | `cortex-vec/src/cortex_vec/distill_queue.py:45-70`, `skills/cortex-broadcast/SKILL.md:49-51` |
| Entrées de `log.md` structurées (type, source, pages touchées, compteur de contradictions) | Rend le journal lisible par un script (stats, audit) et pas seulement par l'humain | `skills/cortex-broadcast/SKILL.md:290-320` |
| Audit d'index par comparaison d'ensembles (liens morts, orphelins, doublons, collisions de noms) et ses trois pièges de regex | Base directe de notre lint déterministe. Point à retenir : comparer des ensembles, pas des nombres | `docs/index-audit.md` |
| BM25 d'abord : `rank_bm25` picklé, dégradation automatique sans clé API, RRF si on ajoute des vecteurs plus tard | Correspond à « lexical d'abord, vectoriel si nécessaire ». Implémentation courte (175 lignes) | `cortex-vec/src/cortex_vec/bm25.py`, `fusion.py:8-49` |
| Filtre qui échoue fermé sur un champ inconnu | Évite un filtre (par date, type ou tag) ignoré en silence par un des moteurs | `cortex-vec/src/cortex_vec/bm25.py:32-80` |
| Banc d'évaluation de la recherche : jeu de référence confirmé par l'humain, P@k / R@k / MRR par adaptateur (grep, bm25, vecteur, hybride) | Donne les chiffres pour justifier (ou non) le passage au vectoriel. Argument solide pour la certification | `cortex-vec/src/cortex_vec/eval/score.py:5-29`, `eval/corpus.py:4-33` |
| Masquage des secrets par regex avant écriture, avec compteur `redactions=N` dans l'en-tête | Sert l'hygiène RGPD et sécurité du dépôt manuel et des newsletters. Transposable tel quel | `hooks/scripts/filter-transcript.py:654-727` |
| Principe de suppression des doublons : un candidat n'est supprimé que s'il est un préfixe strict du survivant (« le doublon reste, jamais de contenu perdu ») | Bon garde-fou pour notre dédup d'items de veille | `cortex-vec/src/cortex_vec/reclaim.py:11-27` |
| CI qui appelle le même script que le pre-commit | Évite l'écart entre CI et poste local. Point de certification | `.github/workflows/python.yml`, `scripts/run-checks.sh` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Modèles OpenAI codés en dur (embedding et résumé), seul le modèle de rerank est configurable | K-B exige un modèle interchangeable par configuration | `cortex-vec/src/cortex_vec/store.py:23`, `config.py:10` |
| `rebuild` supprime toute la collection, ré-embarque tout et appelle **un LLM par page** pour le résumé bilingue | Coût et latence proportionnels à la taille du wiki, sans mise à jour incrémentale par hash | `cortex-vec/src/cortex_vec/store.py:191-260`, `:49-68` |
| Tokenizer : Porter anglais + jieba, rien pour le français | Contenu FR/EN : il faudrait un stemmer par langue (snowball `french`) | `cortex-vec/src/cortex_vec/tokenize.py:21-26` |
| Logique métier dans d'énormes prompts SKILL.md (480 et 358 lignes) | Difficile à tester et à faire évoluer. À réserver aux décisions de jugement, le reste en Python | `skills/cortex-distill/SKILL.md`, `skills/cortex-broadcast/SKILL.md` |
| `_index.md` édité à la main par le LLM, sans invariant vérifié par machine (un compteur `entries:` a dérivé jusqu'à 280 contre 238 réels) | Chez nous, l'index doit être généré par script | `docs/index-audit.md:3-8` |
| Raw modifié (marqueurs ajoutés) et supprimé (reclaim) | Contraire à `raw/` immuable. Chez nous le statut va dans le frontmatter, jamais de suppression | `reclaim.py`, `skills/cortex-distill/SKILL.md:346-365` |
| Capture automatique de tout, avec un commit git par session | K-B veut un ingest unitaire déclenché par l'humain, et la masse de Raw oblige cortexes à un outillage lourd (budget, pagination, reclaim) | `hooks/scripts/session-end-record.sh:53`, `:327` |
| Seuils cosinus « magiques » (0.40 / 0.45 / 0.60) qui reposent sur les vecteurs. En BM25 seul, il faut un recalcul du cosinus, lui aussi dépendant des vecteurs | Si K-B reste lexical, ces seuils ne se transposent pas directement | `cortex-vec/src/cortex_vec/store.py:362-406` |
| Chemins d'index fixes `~/.cortex/`, un seul vault | Limite la sauvegarde et les tests. K-B doit rendre les chemins configurables | `cortex-vec/src/cortex_vec/config.py:7-11`, README (tableau des variables d'environnement) |
| Couplage fort à Claude Code (hooks, plugin, skills) | K-B vise un CLI Python autonome avec un modèle interchangeable | `hooks/hooks.json`, `.claude-plugin/plugin.json` |

Non vérifié : je n'ai pas lu `graph.py`, `rerank.py`, `raw_view.py` ni le site en détail. La qualité réelle des résumés et des seuils n'a pas été mesurée, puisqu'aucune exécution n'était autorisée.

## 6. En une phrase

K-B peut reprendre de cortexes l'ingest en deux temps (distill, puis broadcast avec drapeau de contradiction), le journal `log.md` structuré, l'audit d'index par comparaison d'ensembles et le banc d'évaluation P@k/MRR. En revanche, K-B doit éviter les modèles codés en dur, la reconstruction complète qui appelle le LLM à chaque fois, le tokenizer sans français et la logique enfouie dans des prompts géants.
