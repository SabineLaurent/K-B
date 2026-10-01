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

## Ce qu'on suit

Décidé le 2026-09-30 (#24). On démarre petit ; les listes grossiront à l'usage. Les réglages de
départ sont dans [sources-detaillees.md](sources-detaillees.md).

### Dépôts GitHub (releases)

| Dépôt | Pourquoi |
|---|---|
| `langchain-ai/langchain` | écosystème LLM (monorepo : une release par paquet, bruyant) |
| `langchain-ai/langgraph` | écosystème LLM, agents |
| `run-llama/llama_index` | écosystème LLM, RAG |
| `anthropics/claude-code` | outil de travail |

Sous le coude, à ajouter plus tard :

| Dépôt | Pourquoi |
|---|---|
| `astral-sh/uv` | outil du projet |
| `pytest-dev/pytest` | outil du projet |
| `fastapi/fastapi` | API REST de la v0 |
| `pydantic/pydantic` | validation des entrées à la frontière |
| `anthropics/anthropic-sdk-python` | inférence par API |
| `huggingface/transformers` | écosystème LLM |
| `mistralai/client-python` | écosystème LLM |
| `modelcontextprotocol/python-sdk` | serveur MCP prévu après la v0 |
| `OWASP/www-project-top-10-for-large-language-model-applications` | top 10 LLM ; releases rares |
| `obsidianmd/obsidian-releases` | interface de lecture |

Sans release GitHub (tags seuls), donc non suivis par cette source : `python/cpython`,
`OWASP/Top10`.

### Catégories arXiv

| Catégorie | Pourquoi |
|---|---|
| `cs.CR` | sécurité ; environ 365 papiers par semaine (mesuré le 2026-09-30) |

Mots-clés de départ : `prompt injection`, `jailbreak`, `LLM security`,
`adversarial attack`, `red teaming`, `agent hijacking`. Ils filtrent à la requête (journal du
2026-10-01) : environ 45 papiers par semaine. Détail dans [specs-collecte.md](specs-collecte.md).

### Variables d'environnement

Le nom seulement, jamais la valeur.

| Variable | Rôle |
|---|---|
| `KB_GITHUB_TOKEN` | jeton GitHub *fine-grained*, lecture seule des dépôts publics, sans permission ; création et vérification : [jeton-github.md](jeton-github.md) |

## Sources étendues

Pour les compétences de veille:

- OWASP: webapp top 10, llm top 10, agents top 10
- accessibilité: webaim, wcag, ...
- ecoconception du numérique: ecoindex, ...
- articles de blog de cyberattaque par agent
- site "c'est qui qui a fuité"

## Notes de départ

- github: api rest, releases de dépots choisis (frameworks, outils, owasp, etc), alertes de sécurités, repo top étoiles, repo meilleures progression étoiles

- newsletters gmail: quel format? html à scraper?

- web clipper: .md dès le départ.

- blog ou flux rss selon le format de langchain et son ecosysteme, llamaindex, hugging face, claude, mistral, owasp, cve, etc

- github archive avec bigquery

- arxiv: .pdf
