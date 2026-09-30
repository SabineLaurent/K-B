# K-B — mémoire du projet

Ce que le code et le README ne disent pas : les décisions, leur pourquoi et le contexte. Chargé à
chaque session par le `CLAUDE.md`. Le dépôt est public : rien de personnel ici.

## Contexte

- K-B est le projet support du bloc E1 (pipeline de données) de la certification Développeur IA
  (RNCP37827). Idéalement, il couvre aussi le reste de la certif, hors big data et machine learning.
  Le suivi de la certif vit dans un dépôt séparé, pas ici. Les dates sont tenues par time-knight.
- Les critères de la certif deviennent des exigences de K-B seulement là où ils servent le produit.
- **Binôme** : Sabine travaille avec Claude Code. Claude écrit l'essentiel du code et de la doc ;
  Sabine pilote, relit, teste et décide. Les estimations en tiennent compte : les comptes, la prise
  en main d'outils nouveaux, les décisions et la relecture ne s'accélèrent pas.

## Décisions du 2026-09-29

- **Périmètre.**
  - v0 : pipeline de veille (collecte → fusion → base → API) et fiches de veille.
  - v1 : wiki de savoir à la Karpathy.
  - Plus tard : RAG, fiches rédigées par LLM, MCP, tableau de bord.
- **Deux wikis.**
  - *Veille* : fiches figées, une par question récurrente, tous les 3 jours
    (`wiki/veille/<question>/AAAA-MM-JJ.md`). Requête déterministe via l'API et gabarit, sans
    LLM ni RAG.
  - *Savoir* : pages vivantes, alimentées par `raw/manual/` et par les PDF retenus dans Zotero.
- **Données hors du dépôt de code** (ex. `~/K-B-data/` : `raw/automation/`, `raw/manual/`, base,
  `wiki/`), qui sert aussi de coffre Obsidian. Pourquoi : ne jamais publier de données collectées.
- **Sources de la v0**, une par type de source exigé par la certif, au minimum :

  | Source | Type |
  |---|---|
  | API GitHub, API arXiv | service web |
  | Catalogue CISA KEV (CSV), Web Clipper (`.md`) | fichier |
  | tldr.tech | scraping |
  | Zotero | base de données |
  | GH Archive sur BigQuery | big data |

  - Le scraper TLDR est repris de `brief09_assistant-veille-tech`, relu comme un dépôt tiers
    avant d'être repris. Le `robots.txt` de tldr.tech l'autorise.
  - Le catalogue CISA KEV (vulnérabilités activement exploitées, CSV public, sans clé) a été ajouté
    parce qu'un jury pourrait voir un `.md` comme un document plutôt qu'un fichier de données. Il
    sert aussi un vrai besoin : croiser les failles exploitées avec l'outillage suivi.
  - Zotero : Sabine enregistre ses papiers avec le connecteur et les lit dans Zotero. K-B lit une
    copie de `zotero.sqlite` (papiers, surlignages). Les surlignages alimentent un bloc « Mes
    surlignages » dans les fiches.
- **Sources écartées.**
  - Gmail : TLDR le remplace, et on évite l'OAuth et des mails personnels à traiter.
  - Flux RSS des éditeurs, scraping d'Anthropic : doublons.
  - Historique Brave, favoris Firefox : les favoris faisaient doublon avec le Clipper.
- **BigQuery.**
  - Pourquoi : l'API GitHub ne peut pas repérer les dépôts qui montent. Sa recherche s'arrête à
    1 000 résultats et trie par total d'étoiles, et `/events` est plafonné à 300 événements.
  - Bac à sable, **sans compte de facturation rattaché** : au-delà d'1 To par mois, la requête
    est refusée, pas facturée.
  - Chaque requête est vérifiée par `dry_run` et plafonnée par `maximum_bytes_billed`.

## Estimations (relues le 2026-09-29)

- Chaque issue porte une ligne « Estimation : X h » ; le label `size:*` n'est qu'un ordre de
  grandeur. Les estimations ont été relues à l'aveugle par un agent indépendant : environ 98 h pour
  la v0.
- La surveillance des exécutions (« monitoré », échéance du 25/10) est reportée après E1 : environ
  4 h, sans issue pour l'instant.
- Aucune coupe décidée. arXiv et Zotero vont ensemble ; l'ingester arXiv est repris de brief09.

## Consignes de travail

- Pour la documentation d'une bibliothèque ou d'un service, utiliser Context7 plutôt qu'une
  lecture de page web.
- Vérifier les faits avant de les présenter comme sûrs, sources à l'appui.
