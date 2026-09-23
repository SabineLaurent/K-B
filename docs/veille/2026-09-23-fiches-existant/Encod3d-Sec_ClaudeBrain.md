# Encod3d-Sec/ClaudeBrain (« TORCH »)

*Fiche rédigée par la session principale : l'agent d'analyse a été interrompu deux fois par le filtre
de sécurité, le wiki du dépôt contenant des techniques d'attaque. Lecture limitée à l'architecture :
`scripts/`, `docs/`, `README.md`, `.gitignore`. Ni `wiki/` ni `skills/` n'ont été ouverts.*

## 1. Identité

- **Pitch** : base de connaissance et outillage Claude Code pour le pentest et le bug bounty, qui se réclame du pattern LLM Wiki de Karpathy (`README.md:24`, relevé par l'agent). Environ 517 pages de wiki.
- **Pile** : Python (scripts), Claude Code (hooks, skills), qmd pour la recherche sémantique.
- **Dernier commit** : 2026-09-01. **Licence** : MIT.
- **Maturité** : 77 fichiers `test_*.py`, **aucune CI** (pas de `.github/`).

## 2. Architecture (partie outillage)

| Élément | Rôle | Fichier |
|---|---|---|
| Oracle de fraîcheur | Signale les pages dont `date_updated` dépasse un seuil par classe ; lecture seule, n'édite jamais | `scripts/freshness.py:1-24` |
| Index généré | Réécrit `wiki/index.md` à partir du frontmatter ; mode `--check` qui échoue si l'index est périmé | `scripts/gen_index.py:1-15` |
| Lint déterministe | Liens brisés, références de scripts mortes, frontmatter incomplet, index périmé, zones pauvres | `scripts/lint-wiki.py:1-10` |
| Promotion contrôlée | Seul chemin d'écriture dans `wiki/` : staging, revue, puis promotion après contrôle de fuite | `scripts/wiki-promote.py:1-8` |
| Dédup à l'ingest | Champ `sources: []` dans le frontmatter : si le slug est déjà listé, la page est sautée | `docs/page-types.md:15-19` |

## 3. Rapport au pattern Karpathy

- **Wiki et schéma** : présents, avec des types de pages et un frontmatter normé.
- **Ingest** : présent, avec la dédup par `sources`.
- **Lint** : déterministe (script), plus la fraîcheur.
- **Index** : généré, pas maintenu à la main.
- **Journal** : un log de deltas en ajout seul (`docs/wiki-delta-log.md`, relevé par l'agent, non revérifié).
- **`raw/` n'est pas une couche immuable** : son contenu est ignoré par git (`.gitignore:22-25`) et sert d'espace de travail. Le déplacement des fichiers bruts dans `_processed/` après ingest, signalé par l'agent, **n'a pas pu être confirmé** dans `scripts/` ni `docs/`.

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| **Péremption par classe de sujet** | Seuil de 90 jours pour les sujets rapides (llm, mcp, ai…) et 365 jours pour les autres. C'est la première règle de péremption **typée** rencontrée ; elle répond à la question ouverte « règles de péremption par type ». | `scripts/freshness.py:22-24` |
| **Date du frontmatter, pas mtime** | Le mtime ment (synchronisation, checkout) ; seul `date_updated` mesure l'âge du contenu. Même critique que pour link. | `scripts/freshness.py:5-7` |
| **Signal en lecture seule** | L'oracle signale, il n'édite jamais : la décision reste humaine. | `scripts/freshness.py:7` |
| **`gen_index.py --check`** | Un index qui se vérifie en CI : échec si le catalogue a divergé du wiki. | `scripts/gen_index.py:14` |
| **Un seul chemin d'écriture dans `wiki/`** | Staging, revue, promotion, avec contrôle automatique préalable. Même idée que la porte de fusion d'Eva-brain. | `scripts/wiki-promote.py:4-5` |
| **`sources: []` comme registre d'ingest** | Savoir, depuis le seul frontmatter, qu'une source a déjà nourri une page, sans relire la page. Alternative propre au `.done`. | `docs/page-types.md:15-19` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| `raw/` hors versionnement | Plus de couche source immuable et citable : c'est l'inverse de notre `raw/`. | `.gitignore:22-25` |
| Installation « aggressive by design » | Modifie la configuration globale de Claude Code ; couplage fort à un outil. | `README.md:108` |
| Pas de CI malgré 77 fichiers de tests | Les tests ne protègent rien s'ils ne tournent pas. | absence de `.github/` |
| Domaine de contenu | Contenu offensif : on n'en reprend que l'outillage. | — |

## 6. En une phrase

La péremption par classe de sujet, datée par le frontmatter et signalée sans édition, est la brique qui manquait à K-B ; le reste est de l'outillage de wiki déjà vu ailleurs.
