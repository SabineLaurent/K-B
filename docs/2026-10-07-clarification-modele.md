# Clarification : de ce que donnent les sources au modèle de la base

Séance du 2026-10-07 (mission « clarifier ce que K-B doit faire »). Rien n'est codé : ce document
relève les faits, note les parcours de Sabine et consigne ses décisions de modèle. Les décisions
sont aussi au [journal ADR](ADR/journal-decisions-projet.md).

## 1. Ce que les sources donnent

Le détail, champ par champ, est en [annexe](#annexe--les-sources-champ-par-champ).

- Cinq sources ont un lecteur : CISA KEV, GitHub (alertes, releases, plus étoilés) et arXiv.
  TLDR est collecté brut, sans lecteur (« Lire les articles des pages TLDR brutes », #57) ; un
  article TLDR est un résumé qui pointe vers un article d'ailleurs (`openai.com`, `x.com`,
  `github.com`, `arxiv.org`…). Clips
  Obsidian, Zotero et GH Archive ne sont pas encore collectés.
- Une seule table `item` reçoit tout. Deux sous-types existent : `vulnerability` (CVE) et
  `repository` (nom du dépôt). Une release n'a pas de sous-type : son dépôt n'est écrit que
  dans son titre.
- Le code source `github` regroupe trois natures d'items : alerte, release et dépôt.
- Les lecteurs lisent des champs que la base ne garde pas : `vendorProject` et `product` de CISA,
  `severity` et les paquets des alertes GitHub, le rang, les étoiles et les topics des plus
  étoilés, la version d'un papier arXiv. Aucun code n'écrit dans `star_gain`.

## 2. Les parcours de Sabine en v0

En v0, il n'y a pas de LLM : on ne pose pas de question en langage naturel. K-B offre **un champ
de recherche** (titre et résumé), **des filtres** (période, type d'item, source) et **trois
classements** (vent en poupe, plus étoilés, plus forkés). Les parcours ci-dessous disent lequel des
trois sert. Version légère ; la version formelle (user stories, wireframes) relève de C14 et E4.

| Parcours | Moyen en v0 |
|---|---|
| P1 | filtre de période |
| P2, P3 | filtre de type (release, vulnérabilité), combiné à la recherche (`langgraph`) |
| P4 | croisement par CVE, affiché avec la vulnérabilité |
| P5, P7, P8 | classement |
| P6, P9 | champ de recherche |

Effet sur le modèle : un index plein texte sur `item.title` et `item.summary` (FTS5 dans SQLite,
`tsvector` dans PostgreSQL), et un type d'item qui se filtre directement.

| # | Question | Ce qu'elle demande à la base | Aujourd'hui | LLM ? |
|---|---|---|---|---|
| P1 | Quoi de neuf depuis N jours, toutes sources ou par thème ? | une date par item pour filtrer | `published_at` vide pour certains items ; règle à fixer (#21) | non |
| P2 | Quelles nouvelles versions de mes outils ? | relier une release à son dépôt | le dépôt n'est que dans `item.title` | non |
| P3 | Quelles failles touchent mes outils, mes paquets ? | les paquets touchés par une alerte | paquets lus, non gardés | non |
| P4 | Cette faille est-elle exploitée activement ? | croiser CISA et GitHub par CVE | `vulnerability.cve`, non unique : possible | non |
| P5 | Quels dépôts ont le vent en poupe ? Tous les dépôts, via GH Archive, par fenêtre de 3 jours | étoiles gagnées par dépôt et par fenêtre | `star_gain` existe, vide ; GH Archive pas codé | non |
| P6 | Quels papiers récents sur un sujet (prompt injection…) ? | le mot-clé ou le texte du papier | titre et résumé gardés ; mot-clé de la requête non gardé | non par mots-clés, oui par le sens |
| P7 | Quels sont les dépôts les plus étoilés (top 10) ? | les étoiles d'un dépôt à une date | `stargazers_count` lu, non gardé | non |
| P8 | Quels sont les dépôts les plus forkés de GitHub (top 10) ? | les forks d'un dépôt à une date, sur tout GitHub | non collecté : la recherche est triée par étoiles ; une requête triée par forks en plus | non |
| P9 | Quoi de neuf dans l'écosystème LangChain ? | les dépôts et paquets suivis, plus les items qui citent `langchain` ou `langgraph` | liste dans `tracked_repositories.py` ; recherche dans le texte à faire | non par mots-clés, oui par le sens |

- **Question ouverte** : « quels sujets cartonnent en ce moment ? ». LLM : non si l'on compte des
  étiquettes existantes (topics GitHub, mots-clés arXiv, rubriques ou domaines TLDR), oui pour des
  thèmes que personne n'a étiquetés. Ce qu'on compte n'est pas décidé.
- **Pas en v0** : ce que j'ai lu ou surligné, Zotero et clips (LLM : non) ; ce qu'une fiche cite
  (non) ; le doublon entre un résumé TLDR et son article d'origine (non, par l'URL) ; d'où vient
  une affirmation de ma fiche (non si la fiche cite ses items, oui s'il faut la retrouver à partir
  du texte).
- La colonne LLM ne décide pas du modèle : ce qui le décide, c'est si la donnée est collectée et
  gardée. Elle dit seulement ce qui attend le LLM, et la place à laisser à des embeddings.

<!-- Points 3 à 5 : à suivre dans la séance. -->

## Annexe : les sources, champ par champ

**Exemplaires** : tirés de la première vraie collecte, lancée source par source le 2026-10-07
(chemins relatifs à `<KB_DATA_DIR>/`). Une source par nature d'item : les autres releases, les
alertes npm et les éditions TLDR `infosec` et `dev` ont la même forme. Les fixtures de
`tests/fixtures/` en sont des extraits, parfois allégés (logins remplacés par `example-user`, textes et
listes coupés). Les logins vus dans le brut ne sont pas recopiés ici.

Légende : **gardé** = écrit en base ; **lu** = lu et validé par le lecteur, puis abandonné ;
**non lu** = laissé dans le brut.

### CISA KEV (`cisa_kev`, fichier CSV)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/cisa_kev/2026-10-07T083507Z.csv`,
ligne 2 (le catalogue entier : 1 734 vulnérabilités, `dateAdded` du 2021-11-03 au 2026-10-04).

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `cveID` | `CVE-2026-88779` | gardé | `item.source_item_id`, `vulnerability.cve` ; sert aussi à `item.url` |
| — | `https://nvd.nist.gov/vuln/detail/CVE-2026-88779` | construit | `item.url` |
| `vulnerabilityName` | `Citrix NetScaler Improper Restriction of Operations within the Bounds of a Memory Buffer Vulnerability` | gardé | `item.title` |
| `dateAdded` | `2026-10-04` | gardé (minuit UTC) | `item.published_at` |
| `shortDescription` | `Citrix NetScaler ADC (formerly Citrix ADC) and Citrix NetScaler Gateway … contain an improper restriction…` | gardé | `item.summary` |
| `vendorProject` | `Citrix` | lu | — (#84) |
| `product` | `NetScaler` | lu | — (#84) |
| `requiredAction`, `dueDate` | `Apply mitigations in accordance with vendor instructions…`, `2026-10-07` | non lu | — |
| `knownRansomwareCampaignUse` | `Unknown` | non lu | — |
| `forensicTriage`, `notes`, `cwes` | `Yes`, liens Citrix, `CWE-119` | non lu | — |

### GitHub, alertes de sécurité (`github`, API REST `GET /advisories`)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/github_advisories_pip/2026-10-07T083812Z.json`,
entrée 0 (première collecte : 55 alertes, toutes avec un CVE, revues du 2023-04-05 au 2026-06-25).
C'est la même alerte que l'entrée 0 de la fixture ; le vrai brut a en plus le champ `comments`.
Les paquets cités par ces 55 alertes dépassent la liste suivie : `langchain-community`, `numexpr`,
`llama-index-llms-rungpt`… y figurent aussi.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `ghsa_id` | `GHSA-fjqc-hq36-qh5p` | gardé | `item.source_item_id` |
| `cve_id` | `CVE-2026-48775` (peut être `null`) | gardé | `vulnerability.cve` |
| `summary` | `LangGraph Checkpoint: Unsafe JSON deserialization in checkpoint loading` | gardé | `item.title` |
| `html_url` | `https://github.com/advisories/GHSA-fjqc-hq36-qh5p` | gardé | `item.url` |
| `published_at` | `2026-06-25T18:25:42Z` | gardé | `item.published_at` |
| `github_reviewed_at` | `2026-06-25T18:25:42Z` | lu (pilote la collecte) | — |
| `severity` | `medium` | lu | — |
| `vulnerabilities[].package.name` | `langgraph-checkpoint` | lu | — |
| `description` | `## Summary\n\nLangGraph's JsonPlusSerializer…` | non lu | — |
| `vulnerable_version_range`, `first_patched_version` | `< 4.1.1`, `4.1.1` | non lu | — |
| `cvss_severities`, `cwes`, `epss` | `6.8`, `CWE-502`, `0.00685` | non lu | — |
| `source_code_location` | `https://github.com/langchain-ai/langgraph` | non lu | — |
| `credits` | login de la personne créditée | non lu (minimisation RGPD) | — |
| `nvd_published_at`, `references`, `comments` | `2026-06-16T19:16:58Z`, liens NVD et GitHub, `1` | non lu | — |

### GitHub, releases (`github`, API REST `GET /repos/{owner}/{repo}/releases`)

Exemplaire : vraie collecte du 2026-10-07,
`raw/automation/github_releases_anthropics_claude_code/2026-10-07T084008Z.json`, entrée 0
(première collecte : 100 releases, la page entière, publiées du 2026-06-11 au 2026-10-06 ; aucune
préversion ; `name` égal à `tag_name` pour les 100 ; 2,2 Mo, surtout la liste `assets`). La
fixture avait `assets` vide et pas de champ `reactions`.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `id` | `404958910` | gardé | `item.source_item_id` |
| `html_url` | `https://github.com/anthropics/claude-code/releases/tag/v2.1.292` | gardé | `item.url` ; le dépôt en est extrait |
| dépôt + (`name` ou `tag_name`) | `anthropics/claude-code v2.1.292` | gardé, concaténé | `item.title` |
| `published_at` | `2026-10-06T18:59:30Z` | gardé | `item.published_at` |
| `body` | `## What's changed\n\n- Added --marketplace <source> to claude plugin install…` | gardé | `item.summary` |
| `prerelease` | `false` | lu | — |
| `tag_name` seul | `v2.1.292` | lu | — (seulement dans le titre) |
| `author` | login | non lu (minimisation RGPD) | — |
| `created_at`, `assets`, `draft`, `reactions` | `2026-10-06T18:59:09Z`, binaires `claude-darwin-arm64…`, `false`, `24` | non lu | — |

### GitHub, 100 dépôts les plus étoilés (`github`, API REST `GET /search/repositories`)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/github_most_starred/2026-10-07T084154Z.json`,
`items[0]` (100 dépôts, `incomplete_results` à `false` ; 82 champs par dépôt ; 560 Ko). Même
dépôt en tête que dans la fixture.

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `full_name` | `codecrafters-io/build-your-own-x` | gardé | `item.source_item_id`, `item.title`, `repository.repository_name` |
| `html_url` | `https://github.com/codecrafters-io/build-your-own-x` | gardé | `item.url` |
| `description` | `Master programming by recreating your favorite technologies from scratch.` | gardé | `item.summary` |
| rang dans la réponse | `1` | lu | — |
| `stargazers_count`, `topics`, `created_at` | `551937`, `awesome-list`, `tutorials`…, `2018-05-09T12:03:18Z` | lu | — |
| `language`, `forks_count`, `pushed_at` | `Markdown`, `51783`, `2026-07-14T19:25:58Z` | non lu | — |
| `owner` | login et URL du propriétaire | non lu | — |

### arXiv (`arxiv`, API Atom)

Exemplaire : vraie collecte du 2026-10-07, `raw/automation/arxiv/2026-10-07T084333Z.xml`, première
`<entry>` (première collecte, depuis `FIRST_COLLECTION_START` = 2026-05-01 : `totalResults` 511,
511 entrées, publiées du 2026-05-01 au 2026-10-06 ; 1,3 Mo).

| Champ | Exemple | Sort | `table.colonne` |
|---|---|---|---|
| `id` sans version | `2605.00955` (de `http://arxiv.org/abs/2605.00955v1`) | gardé | `item.source_item_id` ; sert à `item.url` |
| — | `https://arxiv.org/abs/2605.00955` | construit | `item.url` |
| version | `1` | lu | — |
| `title` | `E-MIA: Exam-Style Black-Box Membership Inference Attacks against RAG Systems` | gardé | `item.title` |
| `summary` | `Retrieval-Augmented Generation (RAG) equips large language models (LLMs) with external evidence…` | gardé | `item.summary` |
| `author/name` | 7 auteurs, dont `Zelin Guan`, `Shengda Zhuo` | gardé, dans l'ordre | `author.name`, `item_author.position` |
| `published` | `2026-05-01T12:30:00Z` | gardé | `item.published_at` |
| `updated` | `2026-05-01T12:30:00Z` | gardé | `item.revised_at` |
| `link` PDF, `category`, `primary_category` | `https://arxiv.org/pdf/2605.00955v1`, `cs.CR`, `cs.AI` | non lu | — |

### tldr.tech (`tldr`, pages HTML, une par édition et par jour)

Pas encore de lecteur (#57) : le tableau dit ce que la page contient, et ce que `docs/stockage.md`
prévoit d'en garder. Exemplaire : vraie collecte du 2026-10-07,
`raw/automation/tldr_ai/2026-10-07T084509Z/2026-10-06.html`, deuxième `<article>` (5 pages, du
2026-09-30 au 2026-10-06, sans le 03, le 04 ni le 07 ; 74 à 84 Ko chacune). Sur les 5 pages :
80 articles hors sponsor, et 3 sponsors sur la page du 06.

| Élément de l'article | Exemple | Sort prévu | `table.colonne` prévue |
|---|---|---|---|
| lien (`<a href>`) | `https://openai.com/index/eu-text-provenance/?utm_source=tldrai` | gardé, sans `utm_*` | `item.source_item_id`, `item.url` |
| titre (`<h3>`) | `OpenAI to Add Text Watermarks` | gardé | `item.title` |
| mention en fin de titre | `(7 minute read)` ; ailleurs `(GitHub Repo)`, `(Hugging Face Repo)`, `(Website)`, `(Sponsor)` | non prévu ; `(Sponsor)` écarté | — |
| résumé (`<div>`) | `OpenAI said it would add invisible text watermarks to eligible ChatGPT and Codex outputs in the EU…` | gardé | `item.summary` |
| date de l'édition (nom de la page) | `2026-10-06` | gardé (minuit UTC) | `item.published_at` |
| rubrique (titre de section) | `Headlines & Launches`, `Deep Dives & Analysis`, `Engineering & Research` | non prévu | — |

Mentions sur les 80 articles : `N minute read` 75, `GitHub Repo` 2, `Hugging Face Repo` 1,
`Website` 1, une offre d'emploi 1. Domaines des liens les plus fréquents : `x.com` 7, `openai.com` 5,
`techcrunch.com` 5, `www.anthropic.com` 3, `links.tldrnewsletter.com` 3 ; `github.com` 2,
`arxiv.org` 2. La page ne porte ni auteur ni expéditeur (aucune occurrence de `author`).

### À venir : clips Obsidian (#14), Zotero (#15), GH Archive

D'après `docs/stockage.md`, `docs/specs-collecte.md` et `docs/registre-traitements.md` :

| Source | Ce qu'elle donnera | `table.colonne` prévue |
|---|---|---|
| Clips Obsidian | un fichier `.md` par page gardée : en-tête YAML (`source`, `published`, `created`, `author`) et le texte gardé | `item.url` (`source`), `item.published_at` (`published`, vide si absent), `item.saved_at` (`created`), `author.name` (`author`) ; le texte gardé n'a pas de colonne |
| Zotero | papiers lus (titre, auteurs, date, étiquettes, chemin du PDF) et leurs surlignages | `item.*`, `item.saved_at` (`dateAdded`), `author.name`, `highlight.*` ; étiquettes hors base |
| GH Archive | les dépôts qui gagnent le plus d'étoiles sur 3 jours | `repository`, `star_gain.stars_gained`, `star_gain.window_end` |
