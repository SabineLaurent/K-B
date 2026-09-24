# Fiche de veille — `suwonleee/llmwiki` (alias « Quiz_wiki »)

> Analyse en lecture seule d'un clone `--depth 1`. Aucun code n'a été exécuté. Chemins relatifs à la racine du dépôt.

## 1. Identité

- **Pitch** : un wiki de projet local, en markdown versionné dans git (`<projet>/docs/wiki/`), alimenté **par les transcripts de sessions des agents de code** (Claude Code, Codex, OpenCode) et non par des sources web. Un démon capture les sessions, une commande de clôture (`/wiki-save`) les condense en pages datées, et un quiz à répétition espacée fait réviser à l'humain ses propres décisions.
- **Pile** : Bun + TypeScript, SQLite (`bun:sqlite`) avec FTS5, **aucune dépendance d'exécution** (`package.json` : seulement `@types/bun` et `typescript` en dev). Scripts shell pour les hooks et le démon (launchd / systemd / cron).
- **Dernier commit** : `0bda2a2`, 2026-09-06 (clone superficiel, l'historique n'est pas visible).
- **Taille** : 345 fichiers, environ 30 000 lignes de TS hors tests ; 158 fichiers de tests dans `tests/`.
- **Licence** : Apache-2.0 (`LICENSE`).
- **Maturité** : élevée pour un projet solo. CI GitHub Actions sur ubuntu et macOS avec typecheck, tests et une passe à 1000 pages (`.github/workflows/ci.yml`). Documentation abondante (`ARCHITECTURE.md`, `setup_text.md`, `reference/`). Contrepartie : c'est une usine à gaz (1761 lignes pour `src/cli.ts`, 1300 pour `capture.ts` et pour `doctor.ts`), et une grosse part du code sert au câblage des trois harnais d'agents, ce qui ne concerne pas K-B.

## 2. Architecture

```
src/engine/sources/{claude,codex,opencode,plain}.ts   adaptateurs de sources (transcripts ; « plain » = document déposé à la main)
src/daemon/watch.ts                                   démon de capture → file d'attente centrale (capture.db)
src/engine/update.ts                                  squelette du wiki, watermark, append dans log.md
src/engine/autoupdate.ts                              passe générative WRITE → VERIFY → LINT
src/engine/ingest.ts                                  « déposer une source » sans démon
src/engine/consolidate.ts                             log (pages datées) → encyclopédie de sujets 5_topic/
src/engine/db.ts + schema.sql                         index SQLite dérivé : documents, chunks, FTS5, graphe de liens
src/engine/lint.ts                                    lint déterministe (frontmatter, citations, orphelins, obsolescence)
src/engine/review.ts + gaps.ts                        lint sémantique par LLM → file de lacunes 0_review/gap-queue.md
src/engine/excerpt.ts + screen.ts                     extraits de preuve vérifiés à la lettre + masquage des secrets
src/engine/tiering.ts + cold-index.ts                 cycle de vie hot/warm/cold/protected
src/engine/quiz.ts                                    répétition espacée pour l'humain
hooks/*.sh, adapters/                                 injection de contexte au démarrage de session et à chaque tour
skill/wiki-*.md                                       skills /wiki-save, /wiki-deep, /wiki-ask, /wiki-doctor, /wiki-quiz
```

**Flux principal** (`ARCHITECTURE.md:8-27`) : transcripts d'agents (lecture seule) → `sources/*` et `watch.ts` → file de capture avec watermark en octets → commande de clôture → `repo-write.ts` (frontière d'écriture atomique, refus des liens symboliques) → `docs/wiki/*.md` (**source de vérité**) → réindexation SQLite, dérivée et reconstructible → injection de pointeurs vers les pages dans la session suivante.

**Arborescence du wiki** : répertoires numérotés dans l'ordre de lecture, `1_direction`, `2_milestone`, `3_decision` (ADR), `4_insight`, `5_topic`, plus `0_review` (file réservée au jugement humain) et `6_quiz` (`src/engine/update.ts:18-29`, `src/engine/config.ts:62,82-84`). Trois fichiers fixes : `current-state.md` (« L0 », appartient à l'humain), `overview.md` et `log.md` (`config.ts:88`).

## 3. Rapport au pattern Karpathy

Le README cite le gist comme « seule référence extérieure » (`README.md:188`).

| Élément Karpathy | Dans llmwiki | Verdict |
|---|---|---|
| `raw/` immuable | Les transcripts restent dans les dossiers des agents et ne sont jamais copiés. Ils sont cités par footnote et **disparaissent avec la rétention de l'agent** (environ 30 jours pour Claude Code, `README.md` § Transcript retention). Les dépôts manuels passent par `sources/plain.ts`. | **Transformé** : le brut n'est pas conservé, ce qui fragilise la preuve à long terme. |
| `wiki/` compilé par le LLM | `docs/wiki/`, découpé par type (direction, décision, insight…) puis consolidé par sujet (`5_topic`). Règle « pas de wiki→wiki » : tout est re-dérivé du brut (`README.md:186`, `README.md:620`). | Présent, et plus strict que le gist. |
| Schéma (AGENTS.md) | Pas de fichier de schéma : les règles vivent dans les prompts (`autoupdate.ts`), dans `skill/*.md` et dans `llmwiki.config.toml` (catégories, langue, termes bannis). | Transformé : le schéma devient config TOML + prompts. |
| ingest | `llmwiki ingest <ws> <file>` (`src/engine/ingest.ts:1-10`) ; watermark en octets, si bien que redéposer un fichier inchangé ne fait rien (`sources/plain.ts:1-8`). | Présent. |
| query | Recherche FTS5 en trigrammes + injection de pointeurs à chaque tour (`turncontext.ts`), skill `/wiki-ask`. | Présent, orienté « contexte pour l'agent » plutôt que « réponse à l'humain ». |
| lint | Scindé en deux : `lint.ts` déterministe (environ 30 codes d'erreur) et `review.ts`, un lint sémantique par LLM, **consultatif**, qui ne modifie jamais les pages (`review.ts:1-8`). | Présent, et bien découpé. |
| `index.md` | Absent sous ce nom. `overview.md` joue le rôle de pointeur et `cold-index.md` catalogue les pages froides (`cold-index.ts:7`). L'index réel est SQLite. `index.md` n'est reconnu que comme page racine par le lint (`lint.ts:198`). | Transformé. |
| `log.md` append-only | Oui, format `## [date] type \| titre` (`update.ts:304-310`), avec `merge=union` dans `.gitattributes` pour éviter les conflits (`update.ts:222-225`). | Présent. |
| Obsidian | Des `[[wikilinks]]` sont résolus (`refs.ts`), mais Obsidian n'est pas ciblé explicitement. | Compatible par effet de bord (non vérifié en pratique). |

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| Index SQLite **dérivé et reconstructible**, le markdown restant la vérité | Correspond exactement à notre principe (markdown lisible dans Obsidian, base de données en cache) ; commande `reindex` ; reconstruction incrémentale par `content_hash` | `src/engine/schema.sql:1-6,32-35` |
| FTS5 `tokenize='trigram'`, « pas de base vectorielle volontairement » | Recherche lexicale d'abord, robuste en FR/EN (accents, identifiants de code, noms de CVE). Limite : moins de 3 caractères, pas de match | `src/engine/schema.sql:100-113` |
| Nettoyage des requêtes FTS (tokens entre guillemets) + repli ET→OU classé par bm25 | Évite les `SQLiteError` sur « CVE-2026-1234 » ou « native-epub » ; se reprend en Python en quelques lignes | `src/engine/db.ts:93-110` et suivantes |
| Propagation de l'obsolescence dans le graphe de liens (`stale_since` sur les pages qui pointent vers une page mise à jour, en excluant les pages éditées dans la même passe) | Notre problème central de péremption : une CVE ou une version mise à jour marque ses dépendants, de façon déterministe | `src/engine/db.ts:875-896`, `lint.ts:789` |
| Lint déterministe riche : frontmatter requis, footnotes orphelines, citations non résolues, `dangling-wikilink`, `orphan-page`, `uncited-source` | Notre liste « déterministe d'abord », déjà codifiée ; bon catalogue de règles à porter | `src/engine/lint.ts:385-420,687-789` |
| Lint `numeric-confidence` : un score de confiance chiffré dans le frontmatter est interdit, la certitude passe par une chaîne de footnotes | Rejoint notre décision « pas de score de confiance produit par le LLM », et c'est vérifiable par script | `src/engine/lint.ts:434-447` |
| Extraits de preuve **vérifiés à la lettre** contre la source (`unverified-excerpt` si la citation n'y figure pas) | Garde-fou déterministe contre l'hallucination : on peut exiger une citation littérale de l'article ou de l'advisory et la vérifier sans LLM | `src/engine/excerpt.ts:14-19`, `lint.ts:620-629` |
| `status: superseded` impose `superseded_by` | Pour la veille : une page de version remplacée pointe vers la suivante au lieu d'être supprimée ; se combine avec notre statut dans le frontmatter | `src/engine/lint.ts:422-433` |
| Commande LLM **opt-in**, sans commande ni modèle par défaut ; modèles lus dans env > toml | Modèle interchangeable par configuration, sans ID de modèle codé en dur qui vieillit | `src/engine/claude.ts:12-14`, `models.ts:12-19` |
| Masquage des secrets **avant** toute persistance et tout envoi au LLM, par forme de jeton | Utile si l'on dépose des newsletters ou des mails ; argument RGPD et sécurité pour la certification | `src/engine/screen.ts:1-21` |
| Cadence du lint sémantique **imposée par le moteur** (`--if-due`, 7 jours) et non par le prompt | « Une règle écrite en prose s'applique au bon vouloir du modèle » : bonne leçon pour nos tâches périodiques | `src/engine/review.ts:40-48` |
| File de lacunes qui se referme d'elle-même (`gap-queue.md`, état stocké dans des commentaires HTML) | Le lint sémantique produit une liste d'actions suivie plutôt qu'un rapport jeté après lecture | `src/engine/gaps.ts:1,107` |
| Tiering hot/warm/cold (froid après 180 jours, pages protégées exclues) | Base pour vieillir les items de veille sans les supprimer | `src/engine/tiering.ts:4,187-214` |
| `merge=union` sur `log.md` | Une ligne à ajouter pour que le journal append-only survive aux merges git | `src/engine/update.ts:222-225` |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Écriture **automatique** du wiki par minuterie (`autoupdate-schedule.sh`, « le commutateur totalement autonome ») | Contredit notre décision : l'ingest est unitaire et déclenché par l'humain. Chez eux c'est désactivé par défaut, mais l'architecture est pensée pour ça | `daemon/autoupdate-schedule.sh:2-5` |
| Pages « rejetées » par VERIFY **abandonnées sans escalade** vers l'humain (watermark passé à `skipped`) | Une information perdue en silence est inacceptable pour la veille, et le verdict d'un LLM tient lieu d'arbitre | `src/engine/autoupdate.ts:12-17` |
| Indépendance WRITE/VERIFY **illusoire par défaut** : sans épinglage, les deux tiers reprennent le même modèle observé, et l'avertissement ne se déclenche que si les modèles sont passés explicitement | Le « second modèle adversarial » tourne en pratique en auto-correction silencieuse. Conclusion : ne pas vendre une vérification par LLM comme une garantie | `src/engine/session-model.ts:311-314`, `autoupdate.ts:548` |
| VERIFY rendu par la chaîne exacte `VERIFIED` | Contrôle fragile, verdict binaire non structuré | `src/engine/autoupdate.ts:358` |
| Brut non conservé (transcripts soumis à la rétention de l'agent) | Notre `raw/` doit être immuable et sauvegardé ; ici la preuve expire | `README.md:620`, § Transcript retention |
| Complexité démesurée : trois harnais, hooks, démon, plugin, autodétection des profils Windows… | Presque tout concerne l'intégration aux agents de code, sans intérêt pour K-B ; environ 30 000 lignes pour un cœur qui en demanderait quelques milliers | `src/engine/sources/opencode.ts` (1236 l.), `src/engine/state-dir.ts` (1219 l.) |
| Schéma dispersé entre prompts en dur, skills et TOML, avec des prompts traduits en quatre langues dans le code | Difficile à relire et à faire évoluer ; nous préférons un schéma unique et lisible (type AGENTS.md) | `src/engine/update.ts:150-205`, `autoupdate.ts:537-538` |
| TypeScript/Bun | Hors pile (Python) : on ne récupère que des idées et des règles, pas de code | `package.json` |
| Aucune notion de flux daté ni d'agrégation temporelle (« quoi de neuf cette semaine », comptage) | Le projet sert de mémoire de projet, pas de veille : notre flux 1 reste à concevoir entièrement | constat global (aucun module de collecte web/RSS dans `src/engine/sources/`) |

## 6. En une phrase

K-B ne reprend pas le moteur, mais les **garde-fous déterministes** : index SQLite FTS5 en trigrammes dérivé du markdown, propagation `stale_since` dans le graphe de liens, lint des citations, extraits vérifiés à la lettre, interdiction des scores de confiance, `superseded_by` obligatoire. Il écarte l'écriture autonome et la vérification LLM « adversariale », qui en pratique se note elle-même.
