# Fiche de veille : j-wang/knowledge-agent-template

> Analysé le 2026-09-23, en lecture seule, sur un clone `--depth 1`. Aucun code n'a été exécuté.
> Les numéros de ligne renvoient à l'état du commit `f3fb33d`.

## 1. Identité

- **Pitch** : un gabarit (« template ») de base de connaissance. Un agent LLM (Claude Code) lit `CLAUDE.md`, en suit la méthodologie pour extraire des PDF et des articles vers du markdown, puis pour synthétiser des fiches **concept** (~1 000 mots) et **thèse** (1 500 à 3 000 mots). Le code Python ne s'occupe **que de la recherche** : BM25 par défaut, avec en option des vecteurs denses fusionnés par RRF et un reranker.
- **Pile technique** : Python ≥ 3.10, `numpy`, `rank-bm25`, `scikit-learn` (`engine/pyproject.toml:6`). Les appels HTTP aux fournisseurs d'embeddings et de reranking passent par `urllib` de la bibliothèque standard. `sentence-transformers` est optionnel. Scripts au format PEP 723 pour `uv run`.
- **Dernier commit** : `f3fb33d`, 2026-07-08 (« docs: LEARNING.md »). Le clone superficiel ne montre qu'un seul commit, donc l'historique n'a pas pu être vérifié.
- **Taille** : 21 fichiers, environ 3 255 lignes. Le code tient en 1 764 lignes dans `engine/kb_engine/`, dont 602 pour `search.py` et 510 pour `providers.py`. Le reste est de la documentation et des gabarits.
- **Licence** : MIT (`LICENSE:1`, `README.md:367`).
- **Maturité** : **aucun test, aucune CI** (pas de dossier `.github/`, pas de `tests/`), pas de linter configuré. La documentation est abondante (README, CLAUDE.md, SYSTEM.md), mais elle se contredit par endroits (voir §5). Le moteur est versionné (`kb-engine 1.1.0`) et conçu pour être partagé entre plusieurs agents dérivés. Le dépôt ne contient aucun corpus d'exemple : `extracted/concepts/` ne contient que `PRIMER_TEMPLATE.md`.

## 2. Architecture

```
CLAUDE.md                 # LA méthodologie (401 l.) : prompts d'extraction, de synthèse et de multi-pass, statut manuel
SYSTEM.md                 # justification du design (3 couches, pourquoi BM25 + RRF)
LEARNING.md               # feuille de route NON implémentée : péremption, journal des requêtes, boucle de réconciliation
search.py / build_embeddings.py   # shims de 21 lignes : fixent KB_ROOT puis importent kb_engine
engine/kb_engine/
  _root.py                # KB_ROOT = variable d'env ou cwd
  kb_docs.py              # chargement des .md, parsing du frontmatter PAR REGEX, représentations texte partagées
  search.py               # tokenizer, BM25, dense, RRF, rerank, CLI (--json, --type, --related)
  build_embeddings.py     # embeddings des documents -> .doc_embeddings.npz, avec métadonnées fournisseur/modèle
  providers.py            # Null/OpenAI/TEI/sentence-transformers ; rerankers TEI/Cohere/HTTP ; « wake command »
  retrieval_config.py     # configuration par variables d'env, dataclasses figées, parseur .env maison
input_docs/               # dépôt des sources brutes (vide)
extracted/sources/<slug>/ # extractions markdown écrites par l'agent
extracted/concepts/{docs,theses}/  # le « wiki » compilé
templates/concept.md, thesis.md    # gabarits du frontmatter et des sections
```

**Flux principal, du dépôt à la réponse :**
1. L'humain dépose un PDF ou un article dans `input_docs/` (`CLAUDE.md:91`).
2. L'agent LLM **extrait** le contenu : vision par morceaux de 50 pages, OCR Tesseract en secours, WebFetch pour le web, ou Gmail pour les newsletters (`CLAUDE.md:105-160`). Il écrit le résultat dans `extracted/sources/<slug>/`. **Aucun script ne fait cette étape** : tout passe par des prompts.
3. L'agent **propose des concepts**, les déduplique « à la main » contre l'existant (`CLAUDE.md:231`), les rédige avec `templates/concept.md`, puis rédige les thèses et enrichit au passage les mots-clés des concepts.
4. `python3 search.py --rebuild` construit l'index BM25, sérialisé en pickle, et une matrice de similarité TF-IDF (`engine/kb_engine/search.py:113-149`).
5. En option, `build_embeddings.py` calcule les vecteurs et **enregistre le fournisseur et le modèle** dans le `.npz`, ce qui permet de détecter qu'ils sont périmés (`engine/kb_engine/build_embeddings.py:131-138`).
6. Pour une **requête**, l'agent charge `PRIMER.md` puis appelle `search.py "q" --json`. Le pipeline enchaîne BM25, puis le dense si c'est disponible, puis la fusion RRF k=60, puis le rerank en option (`engine/kb_engine/search.py:373-456`). L'agent lit les documents avec `cat` et synthétise la réponse.

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Ici | Commentaire |
|---|---|---|
| `raw/` immuable | **Transformé** : `input_docs/` plus `extracted/sources/` | L'immuabilité n'est jamais énoncée ni vérifiée. `extracted/sources` est une couche intermédiaire (transcription) que l'on peut aussi indexer via `KB_INDEX_SOURCES` (`kb_docs.py:97-110`). |
| `wiki/` compilé par le LLM | **Présent** : `extracted/concepts/docs` et `theses` | Découpage **par type de page** (concept ou thèse), comme dans K-B. Les liens sont au format `[[slug]]`, donc compatibles Obsidian, mais Obsidian n'est jamais mentionné. |
| Schéma (AGENTS.md) | **Présent, et hypertrophié** : `CLAUDE.md` + `PRIMER.md` | Le PRIMER est un schéma *côté requête* (comment chercher), distinct du schéma *côté construction*. L'idée est intéressante. |
| ingest | **Présent, 100 % LLM** | Par lots (« 15-25 concepts par source »), sans script ni garde-fou déterministe. |
| query | **Présent et outillé** | C'est la partie la plus solide : un vrai CLI, un mode `--json` et une règle de multi-pass « paresseuse » mesurée (`README.md:132`). |
| lint | **Absent** | Rien ne vérifie les liens brisés, les orphelins ou la validité du frontmatter. Les seuls contrôles de cohérence portent sur les index (`search.py:171-259`). |
| `index.md` | **Absent** | Il est remplacé par l'index BM25 et, en partie, par le PRIMER, qui est rédigé à la main. |
| `log.md` | **Absent** | Le statut est un tableau manuel modifiable dans `CLAUDE.md:335`, pas un journal append-only. Un journal de requêtes JSONL est seulement *projeté* (`LEARNING.md:85,96`). |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| BM25 local et hors ligne par défaut, dense et rerank activés par variables d'env seulement, avec dégradation gracieuse et un message d'une ligne sur stderr | Correspond exactement à « lexical d'abord, vectoriel si nécessaire », avec un modèle interchangeable par configuration | `engine/kb_engine/search.py:373-428`, `retrieval_config.py:202-226` |
| Détection des index périmés : `doc_ids` et fournisseur/modèle stockés avec les vecteurs, contrôle de forme, repli sur BM25 | Détection déterministe des index obsolètes. Réutilisable pour l'index de veille | `engine/kb_engine/search.py:194-259`, `build_embeddings.py:131-138` |
| Un seul module pour les représentations texte, partagé entre la construction et la requête (« SINGLE SOURCE OF TRUTH ») | Évite la dérive entre indexation et recherche. Le commentaire documente le bug réellement rencontré | `engine/kb_engine/kb_docs.py:1-14` |
| RRF (k=60) plutôt que la normalisation des scores, avec renvoi du `score` réel et de sa `source` en JSON | Résultats traçables, utiles pour une API REST et pour le monitoring | `engine/kb_engine/search.py:331-344`, `569-595` |
| Configuration par dataclasses figées plus variables d'env documentées dans `.env.example` | Modèle propre pour « modèle interchangeable », facile à exposer dans la documentation OpenAI/certif | `engine/kb_engine/retrieval_config.py:157-192` |
| Règle de multi-pass **paresseuse** : une recherche large, puis décomposition **seulement** des facettes non couvertes. Mesure : la décomposition *dégrade* un corpus factuel (−1,5 à −2,5/10) | La veille est un corpus factuel. À appliquer à « quoi de neuf / pourquoi X buzze » | `README.md:132`, `CLAUDE.md:305-321` |
| Reranker désactivé par défaut, avec l'argument chiffré | Justifie de ne pas ajouter de machinerie. Réutilisable comme argument dans un ADR | `README.md:144` |
| Garde-fous dans le code côté agent de requête : plafond de 10 à 12 recherches, dédup des requêtes quasi identiques, outils natifs plutôt qu'un protocole texte `ACTION:` | Condition d'arrêt de la boucle agentique, explicite et déterministe | `README.md:154-157` |
| PRIMER : un document d'orientation côté requête, séparé du schéma de construction | Le terminal de questions de K-B peut charger un PRIMER court, distinct de l'AGENTS.md du bibliothécaire | `extracted/concepts/PRIMER_TEMPLATE.md:28-77` |
| **LEARNING.md** : typer les affirmations (mécanisme / état / prévision), frontmatter `as_of`, `status: current\|superseded\|contested`, `superseded_by`, et « rétrograder et annoter, ne jamais supprimer » | C'est **le** modèle de péremption dont K-B a besoin (CVE, versions). Compatible avec « statut dans le frontmatter » | `LEARNING.md:28-46` |
| Passe de réconciliation qui produit une **liste de contradictions** à relire, au lieu de réécrire le wiki | Mise à jour humaine du wiki, cohérente avec l'ingest unitaire déclenché par l'humain | `LEARNING.md:46`, `64-78` |
| Signal « récupéré mais jamais cité » tiré d'un journal JSONL append-only des requêtes | Monitoring et journalisation (certif) et détection des pages inutiles sans LLM | `LEARNING.md:70-78`, `85`, `96` |
| Section `## Keywords` généreuse dans chaque page, pondérée ×2 dans BM25 | Levier de rappel transparent et réversible, sans vectoriel | `templates/concept.md:59-63`, `search.py:95-106` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| **Tokenizer ASCII seul** `[a-z0-9]+`, stopwords anglais, `stop_words='english'` en TF-IDF | Casse le français : « sécurité » devient `s` + `curit`. Pour K-B, normaliser en Unicode (NFKD ou `\w`) et utiliser des stopwords FR+EN | `engine/kb_engine/search.py:70-88`, `kb_docs.py:256` |
| Frontmatter **parsé par regex** : seuls 7 champs, `tags` uniquement en liste bloc, `sources` et `related_concepts` ignorés, aucune validation | Contredit « déterministe d'abord ». Un `tags: [a, b]` inline est ignoré sans avertissement. K-B doit utiliser un vrai parseur YAML et un schéma validé (pydantic) | `engine/kb_engine/kb_docs.py:45-63` |
| Ingest **tout LLM** : extraction, dédup de concepts et statut sont confiés à des prompts | Pas de dédup par URL ni de contrôle d'idempotence. Rien de reproductible pour la certification | `CLAUDE.md:231-238`, `CLAUDE.md:105-160` |
| Ingest **par lots** (15 à 25 concepts par source, 5 à 7 agents en parallèle) | Opposé à la décision « ingest unitaire déclenché par l'humain » | `CLAUDE.md:219-229`, `CLAUDE.md:393` |
| **Aucune date** dans le frontmatter des gabarits. La date d'extraction n'est que du texte libre dans le corps | Impossible de filtrer par date : c'est rédhibitoire pour la veille (« quoi de neuf cette semaine ? ») | `templates/concept.md:1-24`, `CLAUDE.md:187` |
| Péremption **seulement sur le papier** (« Nothing here is built yet ») | Ne pas compter dessus comme implémentation de référence : c'est une idée à reprendre, pas du code | `LEARNING.md:3` |
| Statut d'avancement dans un tableau **modifiable** de `CLAUDE.md` | Mélange schéma et état. K-B prévoit un `log.md` append-only et un statut dans le frontmatter | `CLAUDE.md:335-353` |
| Index BM25 en **pickle** sans contrôle de fraîcheur ; `load_index` ignore les erreurs sans le signaler | Un index obsolète répond sans prévenir, et charger un pickle est risqué si le fichier est partagé. Préférer SQLite FTS5, qui sert aussi de BDD de veille interrogeable | `engine/kb_engine/search.py:128-129`, `152-168` |
| `KB_*_WAKE_CMD` exécuté avec `shell=True` depuis `.env` | Exécution de commande arbitraire via la configuration. À ne pas reproduire dans une API exposée | `engine/kb_engine/providers.py:69-93` |
| Deux parseurs de `.env` redondants (l'un d'eux relit `.env` à chaque chargement) | Duplication, et lecture de secrets hors du chemin de configuration central | `kb_docs.py:97-110`, `retrieval_config.py:78-112` |
| Documentation incohérente : `--type concept` alors que le CLI attend `concepts` ; 381, 358 ou 406 documents selon le fichier ; « requires OpenAI API » alors que le code est multi-fournisseur ; `getdoc` natif annoncé mais absent du code | Signe d'une documentation qui dérive sans test. K-B doit générer la documentation du CLI et de l'API (OpenAPI) depuis le code | `README.md:60`, `search.py:529`, `SYSTEM.md:52`, `PRIMER_TEMPLATE.md:52` |
| Aucun test, aucune CI, aucun lint du wiki | Rien de réutilisable pour les critères CI et qualité de la certification | Constat : absence de `tests/` et de `.github/` |
| Aucune collecte automatisée (RSS, API GitHub, CVE) et aucune BDD | Couvre 0 % du flux « veille » de K-B. Seul le flux « dépôt manuel » a un équivalent | `CLAUDE.md:91`, `CLAUDE.md:153-160` |

## 6. En une phrase

K-B peut reprendre le **moteur de recherche** (BM25 d'abord, dense et rerank optionnels avec dégradation gracieuse, détection des index périmés, RRF, multi-pass paresseux avec garde-fous) et le **modèle de péremption décrit dans `LEARNING.md`** (`as_of` / `status` / `superseded_by`, contradictions à relire, journal des citations), mais ni son ingest tout-LLM par lots, ni son tokenizer ASCII, ni son frontmatter parsé par regex sans validation : la veille datée, la BDD et le lint restent entièrement à construire.
