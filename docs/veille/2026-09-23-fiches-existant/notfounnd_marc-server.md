# Fiche de veille — `notfounnd/marc-server` (mARC, « markdown Agent Relay Chat »)

Source : https://github.com/notfounnd/marc-server — clone `--depth 1`, lu sans rien exécuter.

## 1. Identité

- **Pitch** : couche de coordination locale pour agents de code (Claude Code, Codex, Copilot) : chaque tâche devient un *thread* Markdown (`CHAT.md`) dans `.marc/` du dépôt cible, les longs contenus deviennent des *artifacts*, et un thread est « fermé » par un `SUMMARY.md`. Une mémoire sémantique optionnelle (LanceDB + embeddings locaux) indexe ces résumés pour que les agents retrouvent les décisions passées avant d'en reprendre (`README.md:9`, `docs/memory.md:3`).
- **Pile** : TypeScript / Node ≥ 22, serveur MCP (`@modelcontextprotocol/sdk`), daemon HTTP + SSE, UI React 19 / Vite / Tailwind / Radix, `@lancedb/lancedb`, `@huggingface/transformers` (modèle `Xenova/paraphrase-multilingual-MiniLM-L12-v2`, 384 dim., `src/core/memory/local-provider.ts:6-8`), zod (`package.json`). **Pas de Python.**
- **Dernier commit** : `e0a091f`, 2026-07-21 (« calibration of lexical recall and memory candidates »). Le clone superficiel ne montre qu'un commit ; l'historique réel n'est visible que via `CHANGELOG.md` (0.1.0 le 2026-05-07, 0.2.0 le 2026-05-26).
- **Taille** : 422 fichiers, dont ~8 500 lignes de TS pour core/mcp/daemon, et 7,5 Mo de fichiers binaires LanceDB **commités** dans `.marc/memory/` (l'essentiel des 12 Mo du dépôt).
- **Licence** : MIT (`LICENSE:1`).
- **Maturité** : 32 fichiers de test (`node --test`, ~136 cas repérés par grep, jamais lancés ici), ESLint et Prettier, 9 ADR (`docs/adrs/`), doc correcte (7 fichiers dans `docs/`). **Pas de CI** : aucun dossier `.github/`. Le projet se sert de lui-même : 48 threads dans `.marc/threads/` (38 fermés), en portugais, qui sont un vrai journal de décisions. Projet d'un seul auteur, jeune (v0.2.0), `"private": true` dans `package.json` (pas publié sur npm).

## 2. Architecture

```
src/
  cli.ts                 point d'entrée `marc` (mcp | daemon | memory …)
  core/                  logique métier, aucune dépendance HTTP
    markdown.ts          format des messages de CHAT.md (blocs <!-- marc-message … -->)
    threads.ts           création/ajout/lecture par curseur, fermeture par SUMMARY.md
    thread-index.ts      cache JSON reconstructible (mtime de CHAT.md/SUMMARY.md)
    write-coordination.ts verrous fichiers coopératifs + écriture atomique (tmp + rename)
    audit/               « lint » du workspace : références, artefacts, règles, agents
    memory/              index sémantique des SUMMARY.md (LanceDB, ranking hybride)
    recommendations.ts   génère/réécrit INSTRUCTIONS.md, RULES.md, SKILL.md en préservant « Custom Rules »
  mcp/                   serveur MCP stdio (outils workspace_*, thread_*, message_*, memory_*)
  daemon/                HTTP local + SSE + registre des workspaces, auth par jeton
  ui/                    tableau de bord React
.marc/                   (dans chaque projet cible) INSTRUCTIONS.md, RULES.md, agents/, threads/<id>/{CHAT,SUMMARY}.md + artifacts/, cache/, memory/
```

**Flux principal** (pas de « dépôt de source » au sens K-B : la source est la conversation d'agents) :
1. L'agent appelle `workspace_bootstrap` (`src/mcp/bootstrap.ts:11`) : crée `.marc/`, rafraîchit les fichiers gérés, renvoie `INSTRUCTIONS.md` + `RULES.md` + la liste des agents.
2. Les outils suivants exigent `bootstrapConfirmed: true` (`src/mcp/responses.ts:38`).
3. `message_post` ajoute un bloc à `CHAT.md` (`src/core/threads.ts:88`, `appendFile` sous verrou de thread) ; le format est un commentaire HTML de métadonnées (`id`, `threadId`, `timestamp`, `agentId`, `role`, `artifacts`) suivi du corps (`src/core/markdown.ts:36-50`).
4. Fermeture : un agent rédige `SUMMARY.md` (objectif, décisions, validation, risques).
5. `memory_rebuild` découpe chaque `SUMMARY.md` en un morceau global + un morceau par section `##` (`src/core/memory/summaries.ts:88`), n'embarque que les résumés dont le sha256 a changé (`src/core/memory/rebuild-operations.ts:140`), écrit LanceDB puis publie `manifest.json` seulement en cas de succès.
6. `memory_recall` : recherche vectorielle cosinus → re-classement 0,7 vecteur + 0,25 lexical + 0,05 bonus de section (« Décision », « Risques »…) (`src/core/memory/ranking.ts:3-31`, appelé dans `src/core/memory/operations.ts:116-123`) → paquet avec score, raison lisible et référence `marc://$thread`.
7. `workspace_audit` contrôle la cohérence de façon déterministe (`src/core/audit/`).

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Dans mARC | Constat |
|---|---|---|
| `raw/` immuable | **Transformé** : `CHAT.md` est en ajout seul (append) mais pas immuable (`addArtifactToMessage` réécrit le fichier, `src/core/markdown.ts:85`) | Pas de notion de source externe déposée par un humain. |
| `wiki/` compilé par le LLM | **Partiel** : `SUMMARY.md` est la seule page « compilée » (1 par thread). Pas de pages par concept ou entité, pas de liens croisés entretenus | C'est un journal de décisions, pas un wiki. |
| Schéma type AGENTS.md | **Présent et soigné** : `INSTRUCTIONS.md` (géré, ne pas éditer) + `RULES.md` (base gérée + section `Custom Rules` préservée) + `.agents/skills/marc-ops/SKILL.md` (`src/core/recommendations.ts:12`, ADR 0007) | Le point le plus abouti. |
| ingest | **Absent** en tant que tel ; l'équivalent est `message_post` + fermeture par SUMMARY | — |
| query | **Présent** : `memory_recall` (vectoriel + re-classement lexical) | Uniquement sur les SUMMARY, pas sur CHAT ni artefacts (`docs/memory.md:7`). |
| lint | **Présent et déterministe** : `workspace_audit` (liens `marc://` cassés, artefact manquant ou orphelin, règles mal formées, profils d'agents) avec sévérités `critical/warning/suggestion` (`src/core/audit/artifacts.ts:29,47,63`, `src/core/audit/references.ts`) | Bon modèle pour K-B. |
| `index.md` | **Transformé** : `.marc/cache/thread-index.json`, cache JSON reconstructible, pas une page Markdown lisible | Invisible dans Obsidian. |
| `log.md` | **Transformé** : chaque `CHAT.md` est un journal par thread ; pas de journal global | — |
| Obsidian | **Absent** : UI web maison, liens propriétaires `marc://` non reconnus par Obsidian (`docs/architecture.md`, § Internal references) | — |

Principe commun, explicitement assumé : « Markdown est la source de vérité, caches et index sont dérivés et reconstructibles » (`docs/adrs/0001-markdown-source-of-truth.md`), inscrit aussi comme règle critique pour les agents (`.marc/RULES.md:53-56`).

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| ADR « Markdown source de vérité, index = dérivé reconstructible » | Même principe que K-B (le wiki Markdown reste la vérité lisible dans Obsidian, SQLite/index peuvent être jetés et reconstruits). Formulation réutilisable dans nos propres ADR. | `docs/adrs/0001-markdown-source-of-truth.md` |
| Audit déterministe avec codes et sévérités (`artifact_file_orphaned`, `reference_thread_missing`…) + suggestion de correction | Correspond exactement à notre `lint` scripté (liens brisés, orphelins) sans LLM ; le format finding `{severity, scope, code, location, message, suggestion}` est simple à reproduire en Python. | `src/core/audit/artifacts.ts:10-73`, `src/core/audit/support.ts:248-255` |
| Reconstruction incrémentale par sha256 du fichier source + manifest publié seulement après succès | Pour ré-indexer uniquement les pages wiki modifiées ; transposable en Python avec `hashlib`. | `src/core/memory/rebuild-operations.ts:102-149`, `docs/memory.md` (« Rebuild flow ») |
| Écriture atomique `tmp + rename` + verrous fichiers par ressource, avec reprise des verrous périmés | Utile si le pipeline de veille (cron) et l'ingest humain écrivent en même temps dans le wiki. | `src/core/write-coordination.ts:89-102`, `docs/adrs/0009-cooperative-locks-and-atomic-markdown-writes.md` |
| Découpage d'une page par section `##` + bonus de section (« Décision », « Risques ») au classement | Idée de découpage par section pour nos pages wiki ; le bonus de section est un signal déterministe (pas un score produit par le LLM). | `src/core/memory/summaries.ts:88-133`, `src/core/memory/ranking.ts:11-31` |
| `reason` lisible pour chaque résultat (« Exact terms: … Section boost: … ») | Réponses explicables en terminal, sans score de confiance inventé par le LLM. | `src/core/memory/ranking.ts:150-183` |
| Schéma en deux couches : fichier géré (écrasé à chaque mise à jour) + section `Custom Rules` préservée | Pour notre AGENTS.md : séparer ce que l'outil régénère de ce que Sabine écrit à la main. | `src/core/recommendations.ts:12-31`, `docs/adrs/0007-rules-managed-baseline-and-custom-rules.md` |
| Règles au format `Trigger / Do instead / Evidence / Severity` | Format contrôlable par script pour les consignes du bibliothécaire. | `.marc/RULES.md:39-56` |
| Lecture par curseur (`thread_read_since`, `lastMessageId`) | Même logique qu'un « quoi de neuf depuis ma dernière requête ? » sur les items de veille. | `README.md` (Core workflow, étape 8), `docs/mcp-tools.md` |
| ADR courts (Decision / Context / Consequences) | Rejoint la skill `adr-ls` ; bon gabarit, utile pour la certification. | `docs/adrs/README.md` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Vectoriel d'abord : le lexical ne sert qu'à re-classer des candidats déjà sortis de la recherche vectorielle | Un terme exact (nom de CVE, version) absent des 30 plus proches voisins vectoriels ne remonte jamais. K-B a décidé l'inverse : lexical d'abord. | `src/core/memory/operations.ts:116-123`, `src/core/memory/ranking.ts:3-9` |
| Index binaire LanceDB (7,5 Mo) commité dans git, avec chemins absolus Windows dans le manifest | Pas portable (`C:\\Projetos\\marc\\…`), fait grossir le dépôt, conflits git garantis ; contredit « dérivé reconstructible ». Chez nous l'index reste hors git, la sauvegarde est gérée à part. | `.marc/memory/manifest.json:19` |
| Titre de résumé tiré du premier `#` : 20 des 38 résumés indexés s'appellent « Resumo/Sumario executivo » | Titres inutilisables dans les résultats. D'où l'intérêt de notre frontmatter validé (titre, type, statut) plutôt que de deviner avec une regex. | `src/core/memory/summaries.ts:79-86`, `.marc/memory/manifest.json` (champs `title`) |
| « Gate » de bootstrap purement déclaratif : il suffit que l'agent envoie `bootstrapConfirmed: true` | Aucune vérification côté serveur : c'est de la politesse, pas un contrôle. À ne pas présenter comme une garantie. | `src/mcp/responses.ts:35-38` |
| Jeton du daemon accepté en paramètre d'URL `?token=` et comparé avec `===` | Le jeton finit dans les logs et l'historique ; pour l'API REST authentifiée de la certification, préférer un en-tête + une comparaison à temps constant. | `src/daemon/http.ts:84-86` |
| Liens propriétaires `marc://…` | Obsidian ne les reconnaît pas : notre wiki doit rester en `[[wikilinks]]` ou en liens relatifs standard. | `docs/adrs/0005-marc-reference-scheme.md` |
| Métadonnées dans des commentaires HTML parsés par regex au lieu d'un frontmatter YAML | Invisible et non validable dans Obsidian ; pour K-B, le statut va dans le frontmatter (décision déjà prise). | `src/core/markdown.ts:3-4,53-56` |
| Mémoire limitée aux résumés de conversations d'agents, aucune notion de date de péremption | Rien sur la veille, les sources externes ou le vieillissement de l'information : c'est un outil de coordination de code, pas de connaissance. | `docs/memory.md:7` |
| Pile Node/React + transformers.js + LanceDB + daemon + UI dès la v0.2 | Trop lourd pour notre stade. Rien n'est réutilisable tel quel en Python. | `package.json` |
| Pas de CI malgré 32 fichiers de test | La certification exige une CI ; le projet montre ce qu'il ne faut pas oublier. | absence de `.github/` |

## 6. En une phrase

mARC n'est pas un wiki de veille mais un journal de décisions d'agents. K-B en retient la discipline « Markdown = vérité, index = dérivé reconstructible par hash », l'audit déterministe à codes et sévérités, et le schéma « section gérée / section préservée ». Il écarte le vectoriel d'abord, l'index binaire commité et les métadonnées cachées dans des commentaires HTML.
