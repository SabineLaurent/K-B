# Fiche de veille — toolboxmd/karpathy-wiki

> Clone `--depth 1`, commit `d8107e7` (2026-08-27). Lecture seule, rien exécuté.

## 1. Identité
- **Pitch** : plugin d'agent (Codex d'abord, Claude Code, Grok) qui entretient automatiquement un wiki markdown versionné par git selon le pattern LLM wiki de Karpathy. Des « captures » écrites pendant la conversation (ou des fichiers déposés dans `inbox/`) sont ingérées en arrière-plan par un agent CLI détaché (`claude`, `codex` ou `grok`), avec un modèle configurable.
- **Pile** : Bash + Python (sans dépendance déclarée : pas de `requirements.txt`/`pyproject.toml`), hooks SessionStart/Stop, skills markdown, LaunchAgent macOS.
- **Dernier commit** : 2026-08-27 (`feat: retire schema-proposals inbox`), `VERSION` indique 0.7.0 alors que le README annonce encore v0.3.2 (README.md:331) : la doc a du retard sur le code.
- **Taille** : 346 fichiers (hors `.git`), ~12 300 lignes pour README/MANUAL/AGENTS + scripts ; les deux plus gros : `scripts/wiki_dispatch.py` (1 941 l.) et `scripts/wiki_config.py` (1 903 l.).
- **Licence** : MIT (LICENSE:1, « Copyright (c) 2026 lukaszmaj »).
- **Maturité** : beaucoup de tests (`tests/unit` ~91 fichiers, `integration`, `red`/`green`, benchmarks d'ingest sémantique avec fixtures), specs et plans datés abondants. **Pas de CI** : aucun `.github/` ; les tests se lancent à la main (`tests/run-all.sh`, `tests/self-review.sh`, README.md « Tests »). Beaucoup de doc interne (planning, specs, reviews, benchmarks), mais qui se contredit parfois avec le code (voir §3).

## 2. Architecture

```
bin/wiki                      CLI unique (status, capture, ingest-now, config, scheduler, tick…)
hooks/session-start           injecte le skill « loader » dans chaque session + lance un tick
skills/
  using-karpathy-wiki/        loader : « iron laws », déclencheurs de capture et de lecture
  karpathy-wiki-capture/      comment l'agent principal écrit une capture
  karpathy-wiki-read/         protocole de lecture (échelle en 6 étapes + citations)
  karpathy-wiki-ingest/       protocole de l'ingesteur détaché (501 l., cœur sémantique)
  karpathy-wiki-doctor/       recensement périodique (lint, tags, schema)
scripts/
  wiki_dispatch.py / wiki_scheduler.py / wiki_providers.py   file d'attente, verrous, relances, adaptateurs claude|codex|grok
  wiki-validate-page.py / wiki_yaml.py                       validation déterministe du frontmatter (stdlib seule)
  wiki-build-index.py / wiki-discover.py                     génération des _index.md et de l'index.md racine
  wiki-manifest.py                                           manifeste sha256 de raw/
  wiki-commit.sh / wiki-complete-ingest.sh                   portes de commit et de fin d'ingest
.claude-plugin/ .codex-plugin/ .grok-plugin/                 trois manifestes de plugin
```

**Flux principal** : (1) pendant la conversation, l'agent appelle `wiki capture` → fichier dans `<wiki>/.wiki-pending/` ; ou bien un fichier déposé dans `inbox/` est détecté par `wiki-scan.sh` → capture `raw-direct` (README.md « How it works »). (2) Le dispatcher (au SessionStart ou via LaunchAgent macOS) réserve la capture et lance un **agent CLI détaché** avec le prompt « Load and follow this ingest skill exactly » (scripts/wiki_providers.py:106-133). (3) Cet agent lit schema/index, écrit ou fusionne les pages, archive la source dans `raw/`, appelle `wiki-build-index.py`, `wiki-validate-page.py`, `wiki-schema-patch.py` (skills/karpathy-wiki-ingest/SKILL.md:354-470). (4) Il clôt avec `wiki-complete-ingest.sh` : vérifie le manifeste, archive la capture, commit git (scripts/wiki-complete-ingest.sh:152-183) ; `wiki-commit.sh` refuse le commit si une page stagée échoue la validation (scripts/wiki-commit.sh:42-73). (5) Côté question, l'agent principal suit la règle d'orientation puis l'échelle de lecture (skills/karpathy-wiki-read/SKILL.md).

**Modèle interchangeable ?** Oui, mais seulement **à travers des agents CLI** : `SUPPORTED_PROVIDERS = {"claude", "codex", "grok"}` (scripts/wiki_providers.py:20), avec `--model`/`--effort` configurables par wiki dans `~/.config/karpathy-wiki/.../runtime.toml` (README.md « Per-machine ingest configuration »). Aucun appel API direct : l'ingesteur doit être un agent avec shell et accès fichiers. Pour l'obtenir sans intervention humaine, le code désactive les garde-fous : `--always-approve` pour Grok (wiki_providers.py:375), `--sandbox danger-full-access` pour Codex (wiki_providers.py:420), `--permission-mode auto` pour Claude. Le README reconnaît qu'une capture piégée par injection de prompt peut exécuter des commandes avec les droits de l'utilisateur (README.md:212-218).

## 3. Rapport au pattern Karpathy

| Élément Karpathy | Ici | Commentaire |
|---|---|---|
| `raw/` immuable | **Présent, transformé** | `raw/` est l'archive *de l'ingesteur*, pas un dépôt humain (« Do NOT put files in `raw/` », scripts/wiki-init.sh:156) ; le dépôt humain passe par `inbox/`. Manifeste sha256 + `referenced_by` (scripts/wiki-manifest.py:10-20). |
| `wiki/` compilé | **Présent** | Catégories = répertoires de premier niveau, découvertes dynamiquement (`concepts entities queries ideas` par défaut, scripts/wiki-init.sh:61) ; `type` du frontmatter doit égaler le répertoire. |
| Schéma type AGENTS.md | **Transformé** | `schema.md` dans le wiki, patché par script (`wiki-schema-patch.py`) ; les règles de comportement sont dans les skills, pas dans le wiki. |
| ingest | **Présent, automatisé** | Capture automatique pendant la conversation, puis ingest en arrière-plan sans validation humaine. |
| query | **Présent** | Échelle en 6 étapes, sans recherche vectorielle : correspondance de sous-chaînes dans les `_index.md` (skills/karpathy-wiki-read/SKILL.md:34-51). |
| lint | **Présent, en partie déterministe** | Validateur + portes de commit (déterministe) ; contradictions et « stale-claim » laissés au jugement du LLM et consignés dans `.ingest-issues.jsonl` (skills/karpathy-wiki-ingest/SKILL.md:95-110). |
| `index.md` + `log.md` | **Présents, transformés** | `index.md` racine réduit à un sommaire (MOC) + `_index.md` par répertoire ; `log.md` créé à l'init (scripts/wiki-init.sh:93), mais l'historique réellement utilisé passe par `.ingest-runs.jsonl` et git. |
| Obsidian | Présent en surface | `.obsidian/` créé à l'init (scripts/wiki-init.sh:61), rien de plus. |

### Vérification des trois points de la note du 2026-08-01

1. **`_index.md` récursifs par répertoire — PRÉSENTS, inchangés sur le fond, et générés par script.** `scripts/wiki-build-index.py:1-20` (« Recursive _index.md builder ») ; chaque entrée = `- [Title](page.md) — (q: …) description [tags]`, sous-répertoires avec compteur et 5 premiers titres (wiki-build-index.py:150-214) ; l'`index.md` racine n'est qu'un MOC vers les `<catégorie>/_index.md` (wiki-build-index.py:217-232 ; README.md:342). Le skill interdit au LLM d'écrire les index lui-même (skills/karpathy-wiki-ingest/SKILL.md:354 : « Do NOT write `index.md` or any `_index.md` directly »). **Mais attention** : c'est l'ingesteur LLM qui *appelle* le script ; la fin d'ingest déterministe (`wiki-complete-ingest.sh`) ne reconstruit pas les index. Si l'appel échoue, on consigne et « The next ingest catches up » (skills/karpathy-wiki-ingest/SKILL.md:365). Les lignes d'index affichent aussi le score `quality` produit par le LLM (wiki-build-index.py:71-83).
2. **Validation déterministe du frontmatter — PRÉSENTE et renforcée.** `scripts/wiki-validate-page.py` : stdlib uniquement, champs obligatoires `title, type, tags, sources, created, updated` (l.47), dates ISO-8601 UTC, `type` doit correspondre à `path.parts[0]` (violation bloquante, l.123-142), profondeur ≥ 5 refusée, liens relatifs et `sources` doivent résoudre. **Changement depuis la note** : l'exécution est maintenant imposée par le code, plus seulement par la prose : `wiki-commit.sh:42-73` refuse le commit si une page stagée échoue (« 0.2.8 #3 »). **Réserves** : (a) le validateur exige aussi un bloc `quality` (accuracy/completeness/signal/interlinking, 1-5, `overall` = moyenne) **noté par le LLM** (l.192-245), ce qui va contre la décision K-B « pas de scores produits par le LLM » ; (b) la docstring dit encore que le contrôle de `type` n'est qu'un avertissement (l.12-13), alors que le code le rend bloquant (l.123-125) : doc périmée.
3. **Orientation obligatoire avant toute réponse — PRÉSENTE, mais reste de la prose.** Iron law n° 4 : « NO ANSWERING ANY USER QUESTION WITHOUT ORIENTING FIRST » (skills/using-karpathy-wiki/SKILL.md:33), avec un tableau anti-rationalisations (l.51-57). Elle a été **perdue puis restaurée** : le README dit que le découpage v2.4 l'avait « silently dropped » et que la 0.2.7 l'a rétablie (README.md:344). Elle est désormais **une fois par session** (skills/karpathy-wiki-read/SKILL.md:32), suivie d'un comptage de candidats avec seuils fixes (0 → web, 1-5 → lecture directe, 6+ → sous-agent Explore) et d'un contrat de citation (l.111-119 : toute affirmation sans citation doit être signalée « from training data »). Aucune vérification par le code : `bin/wiki orient` est explicitement reporté (README.md:359). Effet de bord : un résultat vide déclenche **toujours** une capture automatique (l.100-108).

**Couplage outil (mise à jour de la note)** : la note parlait d'un fort couplage à Claude Code. Ce n'est plus exact : Codex est devenu l'hôte principal (README.md:331), Claude Code et Grok sont supportés, trois manifestes de plugin coexistent. Le couplage reste fort, mais porte maintenant sur *la famille des agents CLI avec hooks* plutôt que sur un outil précis. Avec la contrainte révisée de K-B (outil libre, modèle interchangeable), le dépôt est **acceptable sur le principe** : le modèle se règle par `--model`. En revanche, le prix est lourd : il faut un agent CLI avec shell complet et garde-fous désactivés pour chaque ingest.

## 4. À retenir pour K-B

| Élément | Pourquoi ça nous sert | Fichier cité |
|---|---|---|
| `_index.md` par répertoire générés par script, jamais par le LLM ; `index.md` racine réduit à un MOC | Catalogue toujours cohérent avec l'état du disque, qui passe à l'échelle (le LLM ne lit que l'index de la catégorie utile), lisible dans Obsidian. **K-B doit le lancer depuis le pipeline Python, pas le confier au LLM.** | scripts/wiki-build-index.py:150-232 ; skills/karpathy-wiki-ingest/SKILL.md:354 |
| Validateur de page en stdlib pure (champs requis, ISO-8601 UTC, `type` = répertoire, liens et `sources` résolus, profondeur max) | Exactement le « déterministe d'abord » de K-B ; à reprendre **sans** le bloc `quality` | scripts/wiki-validate-page.py:47, 118-190 |
| Validation imposée par une porte de commit (refus si une page échoue) plutôt que par une consigne | Transforme une règle de prose en garantie ; en Python, ce sera la porte de fin d'ingest | scripts/wiki-commit.sh:42-73 |
| Manifeste sha256 de `raw/` avec `origin` et `referenced_by` + `diff` NEW/MODIFIED/DELETED | Déduplication et détection des sources modifiées sans LLM ; `referenced_by` permet de retrouver quelles pages refaire quand une source change (péremption) | scripts/wiki-manifest.py:10-30 |
| Séparation `inbox/` (dépôt humain) / `raw/` (archive gérée) | Correspond à notre flux 2 (dépôt manuel) ; le statut peut vivre dans le frontmatter comme décidé | scripts/wiki-init.sh:61, 156 |
| Règle d'orientation + seuils fixes de candidats + contrat de citation (affirmation sans citation = « from training data ») | Bon modèle pour le `query` de K-B en terminal : recherche lexicale dans les index d'abord, citations obligatoires. **À coder** dans la commande query (qui lit schema + index avant l'appel au modèle) au lieu de le demander dans un prompt. | skills/using-karpathy-wiki/SKILL.md:33 ; skills/karpathy-wiki-read/SKILL.md:34-51, 111-119 |
| Types de problèmes consignés en JSONL (`broken-cross-link`, `contradiction`, `stale-claim`, `tag-drift`, `orphan`…) | Taxonomie de lint réutilisable ; `stale-claim` touche directement la péremption de la veille ; un JSONL aide pour la journalisation (certification) | skills/karpathy-wiki-ingest/SKILL.md:95-110 |
| Adaptateurs de fournisseur avec `model`/`effort` en config locale hors dépôt, classement des erreurs (rate limit ≠ échec) | Idée à garder pour « modèle interchangeable par configuration » et pour le monitoring | scripts/wiki_providers.py:20, 565 ; README.md:208 |
| Benchmarks d'ingest avec fixtures `source.md` / `expected.yaml` (pièges de fidélité, faible preuve, etc.) | Méthode pour comparer des modèles sur *notre* ingest avant d'en changer | tests/benchmarks/semantic-ingest/fixtures/ |

## 5. À éviter dans K-B

| Écueil | Pourquoi ça ne nous convient pas | Fichier cité |
|---|---|---|
| Ingesteur = agent CLI complet, avec garde-fous désactivés (`--always-approve`, `danger-full-access`, env complet transmis) | Surface d'attaque énorme pour de la **veille** (RSS, newsletters et pages web non fiables = injection de prompt). K-B doit appeler un modèle par API avec des entrées et sorties structurées, et laisser le code Python faire les écritures | scripts/wiki_providers.py:375, 420 ; README.md:212-218 |
| Capture et ingest automatiques en arrière-plan (hook SessionStart, LaunchAgent, capture « always » sur résultat vide) | Contredit la décision K-B « ingest unitaire déclenché par l'humain » | skills/karpathy-wiki-read/SKILL.md:100-108 ; README.md « Activation modes » |
| Bloc `quality` 1-5 noté par le LLM, obligatoire et affiché dans les index | Contredit « pas de scores produits par le LLM » ; donne une fausse précision | scripts/wiki-validate-page.py:192-245 ; scripts/wiki-build-index.py:71-83 |
| Règles critiques en prose (orientation, appel de build-index par le LLM) | Elles ont déjà été perdues une fois sans que personne le remarque (README.md:344) ; `orient` en CLI est reporté (README.md:359) | skills/using-karpathy-wiki/SKILL.md:27-57 |
| Complexité d'orchestration (dispatcher 1 941 l., config 1 903 l., leases, cooldowns, scheduler global, promotion projet→main) | Disproportionné pour un outil personnel avec ingest manuel ; aucune valeur pour la veille | scripts/wiki_dispatch.py ; scripts/wiki_config.py |
| Doc en retard sur le code (VERSION 0.7.0 contre README v0.3.2 ; docstring « WARNING only » contre violation bloquante) | Rappel : générer ou tester la doc des règles plutôt que la maintenir à la main | VERSION ; README.md:331 ; scripts/wiki-validate-page.py:12-13 vs 123-125 |
| Péremption traitée seulement par le jugement du LLM (`stale-claim` repéré au passage d'un ingest, `contradictions:` jamais résolues) | Pour la veille, il faut un mécanisme déterministe (date `updated`, TTL par type, version et CVE suivies) | skills/karpathy-wiki-ingest/SKILL.md:103, 468 |
| Pas de CI, pas de base de données, pas d'API REST | Rien de réutilisable pour ces volets de la certification | (absence de `.github/`) |

## 6. En une phrase
K-B reprend de karpathy-wiki trois éléments déterministes : les `_index.md` générés par script, le validateur de frontmatter imposé par une porte de commit (sans le bloc `quality` du LLM) et le manifeste sha256 de `raw/`. Il reprend aussi l'idée d'orientation obligatoire et du contrat de citation, **mais codée dans la commande query** au lieu d'être confiée à un prompt, et il rejette l'ingesteur « agent CLI sans garde-fous » déclenché automatiquement.
