# K-B — mémoire du projet

Ce que le code et le README ne disent pas : le contexte, les estimations et les consignes. Les
décisions sont dans `docs/ADR/journal-decisions-projet.md`. Chargé à chaque session par le
`CLAUDE.md`. Le dépôt est privé jusqu'au 25/10, puis public : rien de personnel ici.

## Contexte

- K-B est le projet support de la certification Développeur IA (RNCP37827) : E1 (pipeline de
  données) et E3 (API IA) d'abord, hors machine learning. Le 25/10 est un POC en conteneurs en
  localhost ; mise en ligne sur Azure Container Apps au 08/11 (journal ADR, 2026-10-15, « POC du
  25/10 »). Le suivi de la certif vit dans un dépôt séparé, pas ici. Les dates sont tenues par
  time-knight.
- Les critères de la certif deviennent des exigences de K-B seulement là où ils servent le produit.
- **Binôme** : Sabine travaille avec Claude Code. Claude écrit l'essentiel du code et de la doc ;
  Sabine pilote, relit, teste et décide. Les estimations en tiennent compte : les comptes, la prise
  en main d'outils nouveaux, les décisions et la relecture ne s'accélèrent pas.

## Estimations

- Chaque issue porte une ligne « Estimation : X h » ; le label `size:*` n'est qu'un ordre de
  grandeur. Le jalon « POC 25/10 » porte ses estimations.
- La surveillance des exécutions est portée par #163 (rédaction), puis #162 et #164 (08/11).
- Coupes du 15/10 (journal ADR, « POC du 25/10 ») : la compilation des clips en wiki passe après
  le 29/10, `kb search` après le 08/11. arXiv et Zotero vont ensemble ; l'ingester arXiv est
  repris de brief09.

## Problèmes connus

- **arXiv bloqué au-delà de 2 000 papiers** (constat du 2026-10-05, porté par #71, hors E1 et
  non planifié). Si la fenêtre de collecte contient plus de
  2 000 papiers, la source échoue et sa date reste (`src/k_b/etl/sources/arxiv.py:88-92`). La fenêtre
  suivante part du même point et finit plus tard : elle dépasse encore le plafond, la source
  échoue à chaque collecte. Cela contredit la consigne du 05/10 : lancée tous les jours, K-B
  rattrape les jours manqués (#65).

## Interface

- Le 25/10 : POC en conteneurs en localhost, retour console ; ni interface CLI dédiée ni front.
  `kb search` vient après le 08/11 ; un front écoconçu, plus tard (journal ADR, 2026-10-15,
  « POC du 25/10 »).

## Consignes de travail

- Pour la documentation d'une bibliothèque ou d'un service, utiliser Context7 plutôt qu'une
  lecture de page web.
- Vérifier les faits avant de les présenter comme sûrs, sources à l'appui.
- `brief09_assistant-veille-tech` est indicatif, il ne fait pas autorité : une décision concertée
  qui fait mieux, ou plus conforme aux pratiques reconnues, l'emporte.
- **Fixtures** (consigne de Sabine, 2026-10-10) : une fixture part toujours d'un exemple issu de
  la collecte.
- **K-B est déterministe** dans sa conception, son code et ses journaux (consigne de Sabine,
  2026-10-04) : un journal ou un message d'erreur dit ce qui a été observé (URL de redirection,
  code HTTP, titre trouvé et titre attendu), jamais une supposition ni une interprétation
  (« probablement », « structure changée ? »). Le pourquoi d'un choix va dans les commentaires
  et la doc, pas dans les journaux.
