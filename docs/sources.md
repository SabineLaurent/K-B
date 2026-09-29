# SOURCES

## Sources minimales (v0)

Au moins une source par type exigé par la certif, décidées le 2026-09-29 (le pourquoi est dans
`MEMORY.md`).

| Source | Type | Ce qu'on en tire |
|---|---|---|
| API GitHub | service web | releases des dépôts choisis, alertes de sécurité, dépôts les plus étoilés |
| API arXiv | service web | nouveaux papiers : métadonnées et résumé |
| Catalogue CISA KEV (CSV) | fichier | vulnérabilités activement exploitées, ajoutées depuis la dernière collecte |
| Web Clipper | fichier | pages gardées à la main, en `.md` |
| tldr.tech | scraping | un item par article de chaque édition |
| Zotero (`zotero.sqlite`) | base de données | papiers lus, surlignages, chemin du PDF |
| GH Archive sur BigQuery | big data | dépôts qui gagnent le plus d'étoiles sur 3 jours |

Écartées de la v0 : Gmail, flux RSS des éditeurs, scraping d'Anthropic, historique Brave, favoris
Firefox.

## Notes de départ

- github: api rest, releases de dépots choisis (frameworks, outils, owasp, etc), alertes de sécurités, repo top étoiles, repo meilleures progression étoiles

- newsletters gmail: quel format? html à scraper?

- web clipper: .md dès le départ.

- blog ou flux rss selon le format de langchain et son ecosysteme, llamaindex, hugging face, claude, mistral, owasp, cve, etc

- github archive avec bigquery

- arxiv: .pdf
