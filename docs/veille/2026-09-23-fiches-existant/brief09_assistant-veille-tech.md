# Fiche — `SabineLaurent/brief09_assistant-veille-tech`

*Revue du 2026-09-23, lecture seule (copie locale de `brief09_assistant-veille-tech`).
Rien n'a été exécuté, aucun `.env` n'a été lu. Les chemins sont relatifs à la racine du dépôt.*

> **Avertissement de lecture.** Une bonne partie du code n'est pas de Sabine. Le premier commit
> `97cf7ca` (« scaffold: backend, frontend, docker-compose, acceptance tests », 2026-06-01) a
> fourni `app/main.py`, `app/chat.py`, `app/rag/llm.py` (160 des 170 lignes), `app/rag/retrieval.py`
> (base), `app/rag/chroma_client.py`, `app/schemas.py`, les stubs `news_api.py`/`enrich.py`,
> `tests/acceptance/*`, tout `web/` et le Docker. Un commit (`1a32313`) mentionne une « codegen-locked
> stub policy » : ces stubs étaient verrouillés par le brief. **Le travail propre de Sabine :** les
> trois ingesters, la couche SQLite, l'indexer, l'agent de review, `fresh_news.py` (11 → 200 lignes),
> les gardes de `cleaning.py`, le dédoublonnage de `retrieval.py`, la CLI, les tests à la racine de
> `tests/` et toute la documentation. Les critiques ci-dessous précisent quand un défaut vient de
> l'échafaudage fourni.

---

## 1. Identité

| | |
|---|---|
| **Pitch** | Un assistant de veille tech RAG : on collecte hors ligne arXiv, TLDR.tech et RSS vers SQLite, puis Chroma ; au moment du chat, on ajoute des releases GitHub et le TLDR du jour, et un LLM rédige la synthèse. Exercice de formation (brief 09, entreprise fictive « Nauda Palisse »). |
| **Pile** | Python 3.11, uv, FastAPI, Pydantic 2, httpx, BeautifulSoup/lxml, feedparser, markdownify, LangChain 0.3 + `ChatOpenAI` vers Azure AI Foundry (Kimi-K2.6 pour le chat, gpt-5.4-mini pour la review), ChromaDB 0.5, sentence-transformers (`multilingual-e5-small`), torch. Frontend Next.js 15. Docker Compose. |
| **Dernier commit** | 2026-07-06 (`2acedac docs: readme`), 88 commits entre le 2026-06-01 et le 2026-07-06. |
| **Taille** | 129 fichiers suivis par git, dont 68 hors `docs/` et `LIVRABLES/`. Environ 2 900 lignes de Python dans `app/`, `scripts/` et `tests/`. Sur le disque : `.venv` pèse 1,0 Go, `web/node_modules` 228 Mo, `.mypy_cache` 80 Mo. Données locales non suivies par git : `ingest.db` (224 Ko), `.docker-data/chroma` (3,5 Mo), `logs/ingest/*.csv` (4 fichiers, dont 124 Ko pour TLDR). |
| **Licence** | Aucun fichier LICENSE. Le README indique « Interne Nauda Palisse » (`README.md`, section Licence). |
| **Maturité** | 13 fichiers de tests : les tests propres de Sabine sont sérieux, ceux de l'échafaudage sont creux (voir §Qualité). **Pas de CI** (pas de `.github/`). Documentation très abondante : 21 notes `docs/steps/`, 8 `docs/notes/`, 3 `docs/bugs/`, `LIVRABLES/` avec diagrammes Mermaid. |

## 2. Architecture

```
app/
  main.py                 FastAPI : /health, /topics (liste codée en dur), /chat        [échafaudage]
  chat.py                 retrieve(k=8) → enrich (stub) → fresh_news.fetch → compose_answer [échafaudage]
  config.py               pydantic-settings : sources en listes JSON dans .env, vocabulaire contrôlé
  data/article.sql        LA table unique `article` (statut CHECK, dates en TEXT, listes en JSON)
  data/article_store.py   upsert INSERT OR IGNORE, watermark MAX(date), statuts, écriture de la review
  data/csv_exporter.py    un CSV horodaté par session d'ingestion (logs/ingest/)
  ingest/sources_ingesters/
    arXiv_api.py          API Atom arXiv, pagination, watermark sur <updated>
    tldr_scraper.py       newsletter TLDR → 1 item par <article>, watermark par édition
    rss_feed.py           feedparser, watermark par flux
  ingest/cleaning.py      HTML→Markdown, chunk (LangChain), gardes titre et contenu
  ingest/scraper.py       scraper générique (utilisé par la review pour les « blockers »)
  indexing/indexer.py     chunk → titre en préfixe → embed → upsert Chroma → status='indexed'
  review/                 agent LLM (structured output) : topics filtrés + keywords + résumé si contenu maigre
  rag/                    Chroma HTTP, retrieval top-k dédoublonné par article, LLM de synthèse
  runtime/fresh_news.py   releases GitHub (/releases/latest) + TLDR J/J-1/J-2, à CHAQUE /chat
scripts/ingest_cli.py     Typer : fetch | tldr | rss | index
Makefile                  pipeline-e2e = ingest → review-blocking → index → review
```

**Flux principal.**

1. **Collecte :** `make ingest` lance les ingesters, qui produisent des `Article` Pydantic. Ils passent ensuite par `upsert_article` (INSERT OR IGNORE sur `reference`) avec `status='ingested'`, et chaque session laisse un CSV.
2. **Review des blockers :** `make review-blocking` traite les articles dont le titre est inutilisable ou le contenu fait moins de 150 caractères. L'agent scrape la page source, récupère le titre et fait résumer le contenu par le LLM. Si rien n'est récupérable, l'article passe en `rejected`.
3. **Indexation :** `make index` découpe chaque article `ingested` en chunks, les vectorise dans Chroma et passe l'article en `indexed`.
4. **Review classique :** `make review` écrit les tags et keywords en SQLite, puis corrige les métadonnées Chroma.
5. **Chat :** la question est complétée par les topics (concaténation de chaînes), suivie d'une recherche des 8 plus proches voisins dans Chroma. On ajoute tout le TLDR du jour et la dernière release de chaque dépôt surveillé, puis le LLM produit sa réponse. Les cartes, elles, sont construites par le code et non par le LLM.

Fichiers clés : `app/data/article.sql`, `app/ingest/sources_ingesters/tldr_scraper.py`,
`app/review/article_reviewer.py`, `app/runtime/fresh_news.py`, `app/indexing/indexer.py`.

## 3. Rapport au pattern Karpathy

**Absent.** C'est un RAG vectoriel classique, sans aucune couche wiki.

| Élément Karpathy | Ici |
|---|---|
| `raw/` immuable | **Non.** Le « brut » est la colonne `content` de SQLite, et la review peut l'**écraser** par un résumé LLM (`app/data/article_store.py:173-175`). |
| `wiki/` compilé | Absent. Aucun Markdown produit. |
| Schéma (AGENTS.md) | Absent. Le vocabulaire contrôlé des topics (`app/config.py:108-117`) en est l'embryon le plus proche. |
| ingest / query / lint | Ingest oui, automatique et par lots. Query oui, en vectoriel pur. Lint absent, mais on trouve des **gardes déterministes** avant indexation (`app/ingest/cleaning.py:72-92`). |
| `index.md` / `log.md` | Absents. Les CSV de session (`app/data/csv_exporter.py:20-40`) font office de journal d'ingestion rudimentaire. |

À l'inverse, ce dépôt couvre précisément **ce qu'aucune des 14 implémentations de la veille ne
couvrait** : des items datés en base, une newsletter découpée en items (TLDR), un connecteur de releases
GitHub, une collecte incrémentale par watermark et une date de publication distincte de la date de
collecte. C'est ce qui fait sa valeur pour K-B, **en tant que matière première du flux (1)**.

## 4. Ce qui fonctionne vraiment, et ce qui est annoncé

| Annoncé (README) | D'après le code |
|---|---|
| Ingestion arXiv, TLDR et RSS vers SQLite | **Oui**, code complet et cohérent. Mais le watermark arXiv perd des articles (voir Bugs). |
| « Injection d'articles récents au moment du chat » | **Oui, mais sans aucun filtrage** : tout le TLDR du jour et toutes les releases partent au LLM et dans les cartes, quel que soit le sujet (`app/runtime/fresh_news.py:124-126`, `app/rag/llm.py:80-91`). |
| « Sélection de sujets » dans l'UI | **Cosmétique.** Les topics sont concaténés au texte de la requête (`app/chat.py:39-42`). Ils ne filtrent rien et ne correspondent pas aux tags de la review (`app/main.py:10-16` contre `app/config.py:108-117`). Le problème est connu (`docs/TODO.md` point 11). |
| « Quelles tendances reviennent cette semaine ? » (question d'exemple, `Makefile:133`) | **Impossible par construction** : la recherche n'a aucun filtre de date (`app/rag/retrieval.py:40`), et « cette semaine » n'est qu'un vecteur parmi d'autres. Seul le flux « frais » donne une notion de récence. |
| Agent de review : topics, keywords, complétion | **Oui**, et c'est la partie la mieux conçue : le code décide, le LLM annote, et sa sortie est filtrée (`app/review/article_reviewer.py:235-238`). |
| NewsAPI, `enrich_retrieval`, commandes CLI `news` et `scrape` | **Stubs** qui lèvent `NotImplementedError` (`app/ingest/news_api.py:17-18`, `app/ingest/enrich.py:6-7`, `scripts/ingest_cli.py:102-109`). |
| « Aller plus loin : Postgres, comptes, RGPD » | Rien dans le code : c'est uniquement un paragraphe du README. |

## 5. Bugs et défauts

Légende. **Bug avéré** : le code lu prouve le défaut. **Fragilité** : défaut probable dans des
conditions réalistes. **Choix discutable** : fonctionne, mais mauvais pour la suite. *(E)* signale un
défaut hérité de l'échafaudage.

| Gravité | Constat | Preuve |
|---|---|---|
| **Bug avéré — haute** | **Watermark arXiv global à tous les topics.** Il est calculé une seule fois pour `source="arXiv"`, puis sert d'arrêt pour chaque topic. Si le topic A contient un article plus récent que ce qui manque au topic B, les articles de B entre les deux ne sont jamais collectés. | `app/ingest/sources_ingesters/arXiv_api.py:211` (calcul unique), `:214` (boucle sur les topics), `:239-245` (arrêt) |
| **Bug avéré — haute** | **Watermark arXiv combiné à un plafond de pages : perte définitive.** Avec les valeurs par défaut `max_results=2` et `max_pages=1`, un run ne prend que les 2 plus récents. Au run suivant, le watermark vaut le plus récent, et tout ce qui dépassait le plafond est sauté pour toujours. | `app/config.py:62-63`, `arXiv_api.py:215` et `:250-251` |
| **Bug avéré — moyenne** | **TLDR : une édition en échec est perdue si une édition plus récente réussit.** `run()` avale l'erreur, et le watermark est `MAX(published_date)` : il saute par-dessus le trou. | `tldr_scraper.py:74-75`, `app/data/article_store.py:84`, `tldr_scraper.py:133` |
| **Bug avéré — moyenne** | **Le flux « frais » ignore la question.** À chaque `/chat`, on envoie au LLM (600 caractères chacun) et dans les cartes *toutes* les releases et *tout* le TLDR du jour, jusqu'à une centaine d'articles d'après le commentaire de `:192`. Cela fait du bruit, des tokens et de la latence (scraping séquentiel à chaque requête). | `app/runtime/fresh_news.py:124-126`, `:45-51`, `:90-93` ; `app/rag/llm.py:54-60`, `:80-91` |
| **Bug avéré — moyenne** | **Retry infini sur les 403 et 404.** Le `Scraper` renvoie `[]` pour toute erreur, et la review traite ce cas comme transitoire, donc elle retente à chaque passe. Connu (`docs/TODO.md` point 13), non corrigé. | `app/ingest/scraper.py:48-49`, `app/review/article_reviewer.py:162-165` |
| **Bug avéré — moyenne** | `/topics` renvoie une liste codée en dur, alors que `config.py` affirme que `available_topics` est « la source de vérité UNIQUE » partagée avec `/topics`. Le commentaire ment et les vocabulaires sont disjoints. | `app/main.py:10-16` (E) contre `app/config.py:105-107` |
| **Bug avéré — faible** | `status="ok"` est renvoyé même quand l'appel LLM a échoué. Le statut `degraded` existe pourtant. | `app/rag/llm.py:150-154` (E, non corrigé) |
| **Bug avéré — faible** | Le commentaire du schéma affirme que `CURRENT_TIMESTAMP` produit `2026-06-09T14:32:00`. En réalité SQLite produit `2026-06-09 14:32:00`. `ingested_at` est écrit par Python avec `T`, alors que `indexed_at`, `llm_reviewed_at` et `chroma_synced_at` le sont par SQLite avec une espace : **deux formats dans la même table**. | `app/data/article.sql:14-17`, `app/data/article_store.py:42` et `:101` |
| **Fragilité** | Les dates mélangent naïf et aware : arXiv est en UTC aware, TLDR et RSS sont naïfs. `ingested_at` est naïf en heure locale. Pas de crash aujourd'hui, car chaque watermark ne compare qu'une source avec elle-même, mais toute requête inter-sources « cette semaine » sera fausse. | `arXiv_api.py:168` ; `tldr_scraper.py:185` ; `rss_feed.py:42` ; `article_models.py:53` |
| **Fragilité** | Clé de dédoublonnage RSS = URL **sans toute la query string**. Des articles du type `?p=123` ou `?id=` entrent en collision et le second est silencieusement ignoré (INSERT OR IGNORE). | `rss_feed.py:143-144` |
| **Fragilité** | Nettoyage TLDR : seul `?utm_source=` est retiré, et seulement s'il est le premier paramètre. L'URL stockée garde le tracking. | `tldr_scraper.py:209`, `:219` |
| **Fragilité** | Le scraper générique garde toute la page moins `nav`, `footer`, `script` et `style`, puis l'envoie au LLM **sans troncature** pour résumé. Le coût est imprévisible et le contexte peut déborder. | `cleaning.py:55`, `scraper.py:36`, `article_reviewer.py:173-174` et `:228` |
| **Fragilité** | `multilingual-e5-small` exige les préfixes `query:` et `passage:`. Ni l'indexer ni la recherche ne les ajoutent, ce qui dégrade la qualité de la recherche. | `app/indexing/indexer.py:74`, `app/rag/retrieval.py:23` |
| **Fragilité** | Contenu externe (TLDR, releases, pages scrapées) injecté tel quel dans les prompts, sans délimiteurs ni consigne « ceci est une donnée ». C'est un risque d'injection de prompt, sujet n°10 de la veille. | `app/rag/llm.py:57-59`, `article_reviewer.py:228` |
| **Fragilité** | Configuration lue à l'import du module (valeur par défaut du dataclass). Le code ne suit pas la surcharge de settings utilisée ailleurs, et c'est difficile à tester. | `tldr_scraper.py:22` |
| **Fragilité** | `/chat` est `async` mais appelle une recherche synchrone (embedding, puis HTTP vers Chroma) qui bloque la boucle d'événements. | `app/chat.py:17` (E) |
| **Choix discutable** | **Le contenu source est écrasé par un résumé LLM** rédigé « STRICTLY IN ENGLISH », sans marqueur de provenance. On perd le brut, et les sources françaises sont traduites. C'est l'inverse de `raw/` immuable. | `article_store.py:173-175`, `article_reviewer.py:114` |
| **Choix discutable** | Deux orchestrateurs d'ingestion font la même chose : `ingester.run_all` (appelé nulle part par le Makefile) et `ingest_cli._persist_and_report`. | `app/ingest/ingester.py:36-63` et `:90-116` ; `scripts/ingest_cli.py:41-67` ; `Makefile:59-68` |
| **Choix discutable** | Du code mort : `dedupe()` n'est testé que par l'échafaudage, et `to_chroma_metadata` et `to_indexable` ne sont jamais appelés. L'indexer reconstruit les métadonnées à la main avec des champs différents (`reference` d'un côté, `authors` de l'autre). | `cleaning.py:20` ; `article_models.py:58-76` contre `indexer.py:55-66` |
| **Choix discutable** | Aucune migration : `CREATE TABLE IF NOT EXISTS` seul. Le code d'`ALTER` a été volontairement retiré (`docs/steps/16-…md:55`), donc une base existante n'obtient jamais les nouvelles colonnes. | `app/data/migrate.py:13-14` |
| **Choix discutable** | `init_db()` est appelé à l'import de `app.main`, avec une base SQLite créée dans le conteneur, qui ne lit pourtant jamais SQLite. | `app/main.py:8` |
| **Choix discutable** | Les connexions `sqlite3` sont ouvertes par `with`. Ce `with` valide la transaction mais **ne ferme pas** la connexion, et il y en a une par appel dans des boucles. | `app/data/article_store.py:24`, `:98`, `:182` |
| **Choix discutable** | `uv.lock` est ignoré par git et le Dockerfile ne copie que `pyproject.toml`, donc le build n'est pas reproductible. `--reload` est laissé dans la commande du conteneur. torch complet s'installe dans une image slim. | `.gitignore:21` (E), `Dockerfile.backend:14-15`, `:22` (E) |

## 6. Qualité

- **Structure et séparation des responsabilités.** Le découpage `ingest/`, `data/`, `indexing/`, `review/` et `rag/` est lisible. Les ingesters se ressemblent : une classe dataclass, un `run()` tolérant aux pannes et une normalisation vers un `Article` Pydantic. Les points faibles : deux orchestrateurs concurrents, des métadonnées Chroma construites à deux endroits, et une configuration chargée à l'import.
- **Typage.** Les annotations sont présentes partout. En revanche, `settings: Settings | None` suivi de `self.settings.sources…` (`arXiv_api.py:29` puis `:67`) ne passe pas mypy en mode strict. Les dicts non typés (`dict[str, Any]`) circulent entre la couche data et l'indexer. Les listes sont stockées en JSON dans des colonnes TEXT.
- **Gestion d'erreurs.** La philosophie « pipeline dégradable » est cohérente : une source en panne n'arrête pas les autres. Mais elle est poussée jusqu'à **avaler les erreurs sans distinguer leur nature** (403/404 contre timeout, édition absente contre panne). C'est la cause directe de trois bugs du tableau.
- **Tests.**
  - *Tests propres de Sabine*, bons : `tests/test_review_logic.py` teste la matrice de décision complète avec un agent et un scraper simulés. `tests/test_chroma_sync_stamp.py` utilise une vraie base SQLite en `tmp_path`. `tests/test_retrieval_dedupe.py` et `tests/test_indexer_title_prefix.py` vérifient un vrai comportement. `tests/test_cleaning_title.py` couvre les gardes, accents compris.
  - *Tests de l'échafaudage*, creux : `tests/acceptance/test_fresh_news.py` appelle le réseau et n'affirme presque rien (`:30` : `out == [] or isinstance(out, list)` ; `:20-24` : « filters_by_since » ne vérifie aucun filtre). Les 3 tests NewsAPI **échouent** (`.pytest_cache/v/cache/lastfailed`), parce que le stub était verrouillé par le brief.
  - **Aucun test** sur les watermarks et la logique incrémentale (hors `missing_edition_dates`, non testé non plus), ni sur le parsing TLDR, arXiv ou RSS avec des fixtures. C'est justement là que sont les bugs.
- **Secrets.** Correct : `.env` n'est pas suivi par git, et les clés de `.env.example` sont vides (vérifié par la longueur des valeurs). En revanche, `docker-compose.yml:37` monte `.env` dans le conteneur. Pas de masquage des secrets avant l'envoi au LLM, mais le contenu envoyé est public.
- **Dépendances.** Lourdes pour ce qu'elles apportent : torch et sentence-transformers (des centaines de Mo), LangChain 0.3 utilisé seulement pour `RecursiveCharacterTextSplitter` et `ChatOpenAI`, ChromaDB 0.5. Pour K-B (lexical d'abord), c'est l'essentiel du poids de `.venv`.
- **Documentation.** C'est le point fort du dépôt. `docs/steps/` forme un journal de décisions pédagogique (watermark, trafilatura contre bs4, HNSW, matrice de review). `docs/TODO.md` identifie lui-même plusieurs défauts (points 11, 12 et 13). En revanche, le README décrit parfois l'intention plutôt que le code (topics, RGPD).

## 7. Pour la certification

| Compétence | Utilisable ? | À quelle condition |
|---|---|---|
| **C1 — collecte multi-sources** | **Partiellement.** API REST : arXiv (Atom) et GitHub releases. Scraping : TLDR.tech. Flux RSS : feedparser. **Manquent** « fichier » comme source (le CSV n'est qu'une sortie) et « BDD » comme source (SQLite n'est qu'une destination). | Réécrire les connecteurs dans K-B, corriger les watermarks et ajouter des tests sur fixtures HTML/XML. Ajouter une source fichier (export OPML, dépôt manuel) et une source BDD. |
| **C3 — agrégation, nettoyage, normalisation** | **Oui, en idée.** Normalisation vers un modèle commun (`article_models.py:20-55`), HTML→Markdown, gardes de qualité déterministes (`cleaning.py:60-92`), dédoublonnage par hash d'URL. | Canonicaliser correctement les URL, uniformiser les dates (UTC aware, un seul format), et mesurer le nettoyage (compteurs par étape : les CSV et `IndexResult` en donnent l'amorce). |
| **C4 — BDD Merise + RGPD** | **Non en l'état.** Une seule table, sans MCD/MLD, sans clé étrangère. Listes en JSON dans du TEXT (`article.sql:10-12`), ce qui viole la 1FN. `authors` stocke des noms de personnes (arXiv) sans registre ni durée de conservation. Le RGPD n'apparaît que dans un paragraphe du README. | À refaire. Le schéma `article` sert seulement de **premier jet** au modèle d'item de K-B : colonnes `published_date`, `updated_date`, `ingested_at` et `status` avec CHECK. |
| **C5 — API REST** | **Non.** L'API vient de l'échafaudage, n'a ni authentification ni vraie documentation OpenAPI, et ouvre le CORS à `*` (`app/main.py:24-29`). Elle n'expose aucun endpoint sur les items. | Rien à reprendre, sinon la forme de réponse dégradable (`status: ok/empty/degraded`, `app/schemas.py:39-42`). |
| **C6 — veille** | **Oui, c'est le meilleur matériau.** `docs/steps/` (21 notes datées), `docs/notes/`, `docs/bugs/` et `LIVRABLES/SOURCES.md` montrent une démarche de veille technique : comparaisons argumentées, décisions tracées. | À reformuler en protocole de veille : sources, fréquence, grille de tri, synthèse. Citer ces notes comme antériorité, pas comme livrable K-B. |

## 8. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Newsletter découpée en items (un `<article>` TLDR = un item, sponsors exclus) | C'est exactement le « newsletters découpées en items » de K-B, **qu'aucun des 14 dépôts n'avait**. | `app/ingest/sources_ingesters/tldr_scraper.py:160-224` |
| Connecteur releases GitHub (`/releases/latest`, jeton facultatif, 404 ignoré) | C'est le connecteur « releases » absent des 14 dépôts. Il est à transformer en collecte stockée, pas en appel au moment de la question. | `app/runtime/fresh_news.py:24-67` |
| Date de publication, date de révision et date de collecte **séparées** | Première réponse concrète au sujet n°1 de la veille (modèle d'item de veille). | `app/data/article.sql:6-7`, `:17-18` ; `docs/steps/12-ingestion-incrementale-watermark.md:81-108` |
| Watermark par source et « règle d'or » (trier et comparer sur le même champ) | Collecte incrémentale polie. **Le principe est bon, l'implémentation est à corriger** : un watermark par (source, topic), et il ne doit avancer que sur une plage entièrement collectée. | `docs/steps/12-…md:139-145` ; `tldr_scraper.py:118-139` |
| `status` avec CHECK et horodatages de cycle de vie (`indexed_at`, `llm_reviewed_at`, `chroma_synced_at`) | Du déterministe d'abord : l'état est lisible en SQL. Cela colle à « statut dans les métadonnées, pas de renommage `.done` ». | `app/data/article.sql:13`, `:17-27` |
| Liste blanche SQL pour les noms de colonnes dynamiques | Une hygiène d'injection SQL simple à reprendre. | `app/data/article_store.py:16`, `:78-79` |
| Gardes de qualité déterministes (titre ≥ 3 caractères alphanumériques Unicode, contenu ≥ 150 caractères) | Du lint d'item avant tout LLM, qui gère les accents. | `app/ingest/cleaning.py:72-92` |
| « Le code décide, le LLM annote » ; vocabulaire fermé **refiltré** après la réponse du LLM | Même conclusion que la veille (point 3, « une règle en prose ne tient pas ») et même idée que le vocabulaire d'actions fermé de mindbase. | `app/review/article_reviewer.py:197-198`, `:235-238` |
| Matrice de décision de la review (`ok` / `retry` / `reject`) testée avec agent et scraper simulés | C'est le modèle de test à reproduire pour l'ingest de K-B (fournisseur LLM factice). | `tests/test_review_logic.py:37-128` ; `docs/notes/matrice-review-blocker-et-scraping.md` |
| Préfixe du titre à l'embedding, document stocké brut | À garder **si** K-B passe un jour au vectoriel. | `app/indexing/indexer.py:70-79` |
| Journal de décisions `docs/steps/` | La méthode à reprendre (K-B a déjà `adr-ls`), avec des arbitrages réutilisables comme trafilatura contre bs4. | `docs/steps/7-trafilatura-vs-bs4.md`, `docs/steps/17-agent-review-deterministe-vs-tool-calling.md` |

## 9. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Watermark = `MAX(date)` sur une source entière, après une collecte partielle ou en erreur | Des trous silencieux et définitifs dans la veille. Il faut un curseur par flux, qui n'avance que sur un succès complet. | `arXiv_api.py:211-251`, `tldr_scraper.py:74-75` |
| Répondre à « cette semaine » par similarité vectorielle | C'est la question centrale de K-B. Il faut un filtre `published_at BETWEEN` en SQL, puis un comptage, et seulement ensuite le LLM. | `app/rag/retrieval.py:40`, `app/chat.py:39-42` |
| Collecter au moment de la question (le flux « frais ») | Latence, pas d'historique, pas de comptage possible, et tout est envoyé au LLM sans tri. K-B stocke d'abord. | `app/runtime/fresh_news.py:118-155`, `app/chat.py:27` |
| Écraser le contenu source par un résumé LLM, en anglais imposé | Contraire à `raw/` immuable et au bilinguisme FR/EN de K-B. | `app/data/article_store.py:173-175`, `article_reviewer.py:114` |
| Avaler toutes les erreurs HTTP en `[]` | On ne peut plus distinguer le permanent du transitoire, d'où les retries infinis et les trous. | `app/ingest/scraper.py:48-49` |
| Listes en JSON dans des colonnes TEXT, une table unique | Incompatible avec C4 (Merise, 1FN) et avec le comptage « quelles failles ont le vent en poupe » par tag. | `app/data/article.sql:10-12` |
| Dates naïves et aware mélangées, deux formats de texte | Comparaisons inter-sources fausses. En UTC aware partout, un seul format. | `tldr_scraper.py:185`, `rss_feed.py:42`, `article.sql:14-17` |
| Deux orchestrateurs et des méthodes de modèle mortes | Dette dès le départ. Il faut un seul chemin. | `app/ingest/ingester.py:90`, `scripts/ingest_cli.py:41`, `article_models.py:58-76` |
| Pile RAG lourde (torch, Chroma, LangChain) par défaut | Contraire à « lexical d'abord ». C'est aussi l'essentiel du 1 Go de `.venv`. | `pyproject.toml` (dépendances) |
| Tests d'acceptance qui appellent le réseau et n'affirment rien | Ils donnent une fausse confiance. | `tests/acceptance/test_fresh_news.py:20-30` |

## 10. Verdict par composant

| Composant | Verdict | Raison |
|---|---|---|
| `app/ingest/sources_ingesters/tldr_scraper.py` (`_parse_newsletter`) | **Garder tel quel** (la fonction de parsing) | Correcte et ciblée. Seul exemple de newsletter découpée en items. À protéger par un test sur une fixture HTML (la structure du site peut changer). |
| `tldr_scraper.py` (`run_incremental`, `run`) | **Reprendre l'idée** | Le watermark par édition est bon, mais une édition en erreur fait un trou. Configuration lue à l'import. |
| `app/ingest/sources_ingesters/arXiv_api.py` | **Reprendre l'idée** | Le parsing Atom (`:88-142`) est réutilisable. La logique incrémentale est fausse (watermark global et plafond). |
| `app/ingest/sources_ingesters/rss_feed.py` | **Reprendre l'idée** | Watermark par flux correct dans l'esprit. Clé de dédoublonnage trop agressive et dates naïves. |
| `app/runtime/fresh_news.py` (`_fetch_github`, `_normalize_release`) | **Reprendre l'idée** | Bon connecteur de releases, au mauvais endroit (au moment de la question). À transformer en collecte stockée, en paginant `/releases` et pas seulement `latest`. |
| `app/runtime/fresh_news.py` (cascade TLDR, `fetch`) | **Jeter** | Du scraping à chaque requête, sans filtre. |
| `app/data/article.sql` | **Reprendre l'idée** | Bon premier jet des colonnes de dates et de statut, à éclater en modèle Merise (source, item, tag, auteur…). |
| `app/data/article_store.py` | **Reprendre l'idée** | Requêtes paramétrées et liste blanche, bien. Connexions non fermées, pas de migrations, formats de date mixtes. |
| `app/data/csv_exporter.py` | **Jeter** | Journal CSV redondant avec la base. Un vrai journal structuré ou `log.md` fera mieux. |
| `app/ingest/cleaning.py` (gardes `is_usable_title`, `has_enough_content`) | **Garder tel quel** | Simples, testées, déterministes, compatibles avec les accents. |
| `app/ingest/cleaning.py` (`dedupe`, `chunk`, `strip_boilerplate`) | **Jeter** | `dedupe` n'est pas utilisé. `chunk` dépend de LangChain. `strip_boilerplate` est trop naïf (trafilatura est la bonne réponse, déjà étudiée dans `docs/steps/7`). |
| `app/ingest/scraper.py` | **Jeter** | Avale les statuts HTTP et garde la page entière. |
| `app/ingest/article_models.py` | **Reprendre l'idée** | Le modèle Pydantic commun est bon. Les méthodes mortes et les sous-classes vides sont à retirer. |
| `app/ingest/ingester.py` | **Jeter** | Doublon de la CLI. |
| `app/review/article_reviewer.py` | **Reprendre l'idée** | Excellente séparation entre décision par le code et annotation par le LLM, avec filtre du vocabulaire. Mais elle écrase le brut, impose l'anglais et envoie la page entière sans limite. |
| `app/review/review_orchestrator.py` | **Reprendre l'idée** | Le compte-rendu `reviewed + rejected + skipped == entrée` est une bonne pratique. Le reste est lié à Chroma. |
| `app/indexing/indexer.py` | **Jeter** (pour l'instant) | Chroma et embedding sont hors du périmètre « lexical d'abord ». Garder en mémoire l'idée « préfixe titre, document brut ». |
| `app/rag/*`, `app/chat.py`, `app/main.py`, `app/schemas.py` | **Jeter** | Échafaudage fourni, sans authentification, recherche sans date, statut faux en cas d'échec. |
| `app/config.py` | **Reprendre l'idée** | Sources déclarées comme objets typés dans la configuration, et vocabulaire contrôlé avec glose. |
| `scripts/ingest_cli.py` | **Reprendre l'idée** | Typer avec un tableau Rich « récupérés / nouveaux » par source : un bon retour opérateur. |
| `tests/test_review_logic.py`, `tests/test_chroma_sync_stamp.py` | **Reprendre l'idée** | Le bon modèle de test (LLM factice, base en `tmp_path`). |
| `tests/acceptance/*` | **Jeter** | Échafaudage, appels réseau, assertions tautologiques, 3 tests en échec. |
| `web/`, Docker | **Jeter** | Échafaudage. Build non reproductible. |
| `docs/steps/`, `docs/notes/`, `docs/TODO.md` | **Garder tel quel** (comme archive) | Matière pour C6 et arbitrages déjà instruits (watermark, trafilatura, matrice de review). |

## 11. En une phrase

K-B y prend le **modèle d'item daté** (publication, révision, collecte, statut), le **découpage de
newsletter en items**, le **connecteur de releases GitHub** et la règle « le code décide, le LLM
annote, sa sortie est refiltrée ». Il laisse le RAG vectoriel, la collecte au moment de la question,
l'écrasement du brut et des watermarks qui perdent silencieusement des données.

## 12. Verdict global

**Prélever des morceaux, ne pas repartir de ce code.** Ce dépôt est un RAG vectoriel construit sur un
échafaudage imposé. Son architecture (Chroma, collecte au moment de la question, pas de requête par
date) va à l'opposé des choix de K-B. En revanche, trois ou quatre pièces couvrent exactement ce que les
14 implémentations lues ne couvraient pas : newsletter découpée en items, releases GitHub, dates
séparées, watermark. Elles sont à réécrire proprement, tests d'abord, car c'est précisément dans la
logique incrémentale que se trouvent les bugs.
