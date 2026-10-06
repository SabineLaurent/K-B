# K-B — mémoire du projet

Ce que le code et le README ne disent pas : le contexte, les estimations et les consignes. Les
décisions sont dans `docs/ADR/journal-decisions-projet.md`. Chargé à chaque session par le
`CLAUDE.md`. Le dépôt est privé jusqu'au 25/10, puis public : rien de personnel ici.

## Contexte

- K-B est le projet support du bloc E1 (pipeline de données) de la certification Développeur IA
  (RNCP37827). Idéalement, il couvre aussi le reste de la certif, hors big data et machine learning.
  Le suivi de la certif vit dans un dépôt séparé, pas ici. Les dates sont tenues par time-knight.
- Les critères de la certif deviennent des exigences de K-B seulement là où ils servent le produit.
- **Binôme** : Sabine travaille avec Claude Code. Claude écrit l'essentiel du code et de la doc ;
  Sabine pilote, relit, teste et décide. Les estimations en tiennent compte : les comptes, la prise
  en main d'outils nouveaux, les décisions et la relecture ne s'accélèrent pas.

## Estimations (relues le 2026-09-29)

- Chaque issue porte une ligne « Estimation : X h » ; le label `size:*` n'est qu'un ordre de
  grandeur. Les estimations ont été relues à l'aveugle par un agent indépendant : environ 98 h pour
  la v0.
- La surveillance des exécutions (« monitoré », échéance du 25/10) est reportée après E1 : environ
  4 h, sans issue pour l'instant.
- Aucune coupe décidée. arXiv et Zotero vont ensemble ; l'ingester arXiv est repris de brief09.

## Problèmes connus

- **arXiv bloqué au-delà de 2 000 papiers** (constat du 2026-10-05, porté par #71, hors E1 et
  non planifié). Si la fenêtre de collecte contient plus de
  2 000 papiers, la source échoue et sa date reste (`sources/arxiv.py:66-70`). La fenêtre
  suivante part du même point et finit plus tard : elle dépasse encore le plafond, la source
  échoue à chaque collecte. Cela contredit la consigne du 05/10 : lancée tous les jours, K-B
  rattrape les jours manqués (#65).

## Consignes de travail

- Pour la documentation d'une bibliothèque ou d'un service, utiliser Context7 plutôt qu'une
  lecture de page web.
- Vérifier les faits avant de les présenter comme sûrs, sources à l'appui.
- `brief09_assistant-veille-tech` est indicatif, il ne fait pas autorité : une décision concertée
  qui fait mieux, ou plus conforme aux pratiques reconnues, l'emporte.
- **K-B est déterministe** dans sa conception, son code et ses journaux (consigne de Sabine,
  2026-10-04) : un journal ou un message d'erreur dit ce qui a été observé (URL de redirection,
  code HTTP, titre trouvé et titre attendu), jamais une supposition ni une interprétation
  (« probablement », « structure changée ? »). Le pourquoi d'un choix va dans les commentaires
  et la doc, pas dans les journaux.
