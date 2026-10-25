# SOURCES

## Sources minimales (v0)

Au moins une source par type exigé par la certif, décidées le 2026-09-29 (le pourquoi est dans
`MEMORY.md`).

| Source | Type | Ce qu'on en tire |
|---|---|---|
| API GitHub | service web | releases des dépôts choisis, alertes de sécurité, dépôts les plus étoilés et les plus forkés |
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

### Dépôts GitHub (releases et alertes de sécurité)

Chaque dépôt suivi donne ses releases et les alertes de sécurité de ses paquets. Seuls les
paquets principaux sont suivis ; une intégration (`langchain-anthropic`…) s'ajoute quand elle sert.
Écartés le 2026-10-02 : `langchain-community` et `langchain-experimental` (dépôts archivés, plus
maintenus), `langchain-classic` (compatibilité avec la v0, non utilisée).
La sécurité des projets de Sabine relève de Dependabot, pas de cette liste (décidé le 2026-10-02).
La liste vit dans `TRACKED_REPOSITORIES` de `src/k_b/core/config.py`.

| Dépôt | Pourquoi | Paquets (alertes) |
|---|---|---|
| `langchain-ai/langchain` | écosystème LLM (monorepo : une release par paquet, bruyant) | pip : `langchain`, `langchain-core`, `langchain-text-splitters` |
| `langchain-ai/langgraph` | écosystème LLM, agents | pip : `langgraph`, `langgraph-checkpoint` |
| `run-llama/llama_index` | écosystème LLM, RAG | pip : `llama-index`, `llama-index-core` |
| `anthropics/claude-code` | outil de travail | npm : `@anthropic-ai/claude-code` |

Sous le coude, à ajouter plus tard, avec leurs paquets :

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
| `cs.CR` | *Cryptography and Security* : sécurité ; environ 365 papiers par semaine sans filtre (mesuré le 2026-09-30) |
| `cs.AI` | *Artificial Intelligence* : IA générale, agents ; croisée avec `cs.CR` (2026-10-01) |

On ne garde que les papiers classés **à la fois** en `cs.CR` et en `cs.AI`, et dont le résumé
contient un de ces mots-clés : `prompt injection`, `jailbreak`, `red teaming`,
`adversarial attack`, `backdoor`, `poisoning`, `membership inference`, `agent security`. Filtre à
la requête (journal du 2026-10-01) : environ 20 papiers par semaine. Détail dans
[specs-collecte.md](specs-collecte.md).

### Variables d'environnement

Le nom seulement, jamais la valeur. Modèle à copier en `.env` : `.env.example`.

| Variable | Rôle |
|---|---|
| `KB_DATA_DIR` | **obligatoire** pour `kb collect` : dossier des données, hors du dépôt de code ; le brut y est écrit dans `raw/`, l'état de collecte dans `collection_state.json` |
| `KB_ZOTERO_DIR` | facultatif : dossier de données de Zotero, celui qui contient `zotero.sqlite`, en chemin complet (un `~` écrit dans `.env` n'est pas développé) ; sans elle, `kb collect` saute Zotero et l'affiche |
| `KB_VAULT_DIR` | facultatif : dossier du coffre Obsidian de K-B, celui qui contient `Clippings/`, en chemin complet ; sans elle, `kb collect` saute les clips et l'affiche |
| `KB_GITHUB_TOKEN` | facultatif (60 requêtes par heure sans, 5 000 avec) : jeton GitHub *fine-grained*, lecture seule des dépôts publics, sans permission ; création et vérification : [jeton-github.md](jeton-github.md) |
| `GOOGLE_APPLICATION_CREDENTIALS` | chemin de la clé du compte de service BigQuery, pour GH Archive : [bigquery.md](bigquery.md) |

## Sources étendues

### Pour plus tard : Hugging Face *Daily Papers*

Papiers (surtout arXiv) sélectionnés et votés par la communauté : une sélection générale d'IA,
où les LLM et les agents côtoient surtout la vision. API JSON
`https://huggingface.co/api/daily_papers?week=AAAA-Www&limit=100&p=<page>`, sans
authentification, documentée seulement de façon
[non officielle](https://github.com/0x0is1/hf-papers-api-docs). Idée retenue : stocker toute la
semaine, garder les 10 plus votés à la lecture. Le nom d'utilisateur de la personne qui soumet le
papier n'entrerait pas dans les items. Les mesures du 2026-10-01 sont dans le
[journal ADR](ADR/journal-decisions-projet.md).

### Autres pistes

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
