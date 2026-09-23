# Gist rohitg00 — « LLM Wiki v2 »

*Texte, pas de code. Lu via la page du gist le 2026-09-23 ; résumé produit par un outil de lecture web, citations à reprendre telles que rapportées.*

## Identité
- Fork du gist de Karpathy par @rohitg00, dernière activité le 2026-09-23.
- Tiré de l'expérience d'`agentmemory`, un moteur de mémoire **persistante pour agents autonomes**.

## Propositions par rapport à Karpathy
- **Cycle de vie** : score de confiance par fait (sources, récence, contradictions) ; décroissance façon courbe d'Ebbinghaus sans renforcement ; **supersession explicite** avec historique conservé ; consolidation mémoire en quatre étages.
- **Passage à l'échelle** : l'`index.md` plat casserait vers « 200-500 documents » ; recherche hybride BM25 + vecteurs + parcours de graphe, fusion RRF ; graphe de connaissances typé.
- **Automatisation** : hooks événementiels (ingest et lint automatiques, injection de contexte), scores de qualité, lint auto-réparateur, propositions de résolution de contradictions.
- **Primauté du schéma** : le document de schéma (CLAUDE.md, AGENTS.md) serait le fichier le plus important du système.

## Les commentaires du gist
Des lecteurs y opposent des objections de production : la confiance chiffrée masque la chaîne de preuve ; les écritures pilotées par LLM se corrompent en silence ; l'automatisation sans porte humaine menace l'intégrité.

## À retenir pour K-B
| Élément | Pourquoi |
|---|---|
| **La supersession explicite, historique conservé** | Rejoint `superseded_by` (knowledge-agent-template, suwonleee) et `Status: Outdated` (Astro-Han) : on marque l'ancien, on ne l'efface pas. |
| **Le seuil de l'index plat** | Argument de l'index hiérarchique déjà acté dans la note du 01/08. |
| **Le schéma comme produit** | Confirme la place centrale d'`AGENTS.md`. |

## À éviter
| Écueil | Pourquoi |
|---|---|
| Scores de confiance, décroissance, qualité notée par le LLM | Fausse précision ; exclu par K-B, et contesté par Astro-Han après usage réel. |
| Ingest et lint automatiques par hooks | Contraire à l'ingest déclenché par l'humain. Le cas d'usage (mémoire d'agent autonome) n'est pas le nôtre (wiki curé). |

## En une phrase
Une vision d'architecture pour la mémoire d'agent autonome, dont K-B garde la supersession et le seuil d'index, et rejette le scoring et l'automatisation.
