# Spécification des fiches de veille

Une fiche de veille regroupe, pour un sujet d'une liste fermée, ce que la veille de K-B a vu sur
une fenêtre de quelques jours. C'est la première sortie d'un modèle dans K-B : ce document est son
contrat, écrit avant le code. Il dit ce qui entre, ce qui sort, ce que le code refuse et ce qu'il
mesure. Les décisions et leur pourquoi sont dans le [journal ADR](ADR/journal-decisions-projet.md)
(2026-10-15, « POC du 25/10 », décisions 4, 5, 6 et 8 ; « Fiches de veille : le contrat ») ; les
règles du POC, dans `.claude/rules/poc.md` ; l'API de données lue, dans [specs-api.md](specs-api.md).

**Partie commune avec le wiki.** La liste fermée de sujets, les schémas validés par le code, les
contrôles, les états nommés et la ligne de métrique sont posés ici ; la spécification du wiki
(#148, `docs/wiki.md`, pas encore écrite) les reprend au lieu de les redéfinir.

## Le parcours d'une demande

1. `POST /digests` sur l'API IA, avec une clé (#156) : la demande est validée (section
   « Fenêtre »), avant toute lecture et tout appel au modèle.
2. L'API IA lit la veille de la fenêtre par l'API de données, avec la clé du client `AI_DIGEST`
   (#204) : `GET /items`, puis `GET /items/{item_id}` pour chaque item. Elle ne lit pas la base.
3. **Classement** (#205) : le modèle range chaque item dans un sujet, ou le dit « non retenu ».
4. **Rédaction** (#205) : un appel par sujet ; le modèle écrit des affirmations qui citent leurs
   items.
5. **Contrôles** (#206, #207, section « Contrôles ») : le code revalide chaque sortie avant de
   s'en servir.
6. Réponse JSON ; une ligne de métrique par appel au modèle, sur la sortie standard (#156).

L'appel au modèle, sa nouvelle tentative et le modèle de remplacement des tests sont à #150 ; le
vrai modèle (Mistral) à #158. L'API IA n'écrit rien qui doive survivre à son redémarrage
(règle 7 de `poc.md`) : les fiches sont rendues, pas gardées.

**Pas de tendances au 25/10** (décision de Sabine du 2026-10-15) : une tendance n'est pas un item
(table `trend`, servie par `GET /trends` avec un `repository_id`) et n'a pas d'`item_id` à citer ;
un second type de référence alourdirait le classement et la rédaction (#205).

## Sujets

La liste fermée des sujets est tenue par Sabine dans `core/config.py` (#205 l'y code). Le modèle
ne choisit que dans cette liste (`enum`) ; le code refuse le reste (journal ADR, « POC du 25/10 »,
décision 5). Un nom suit `[a-z][a-z0-9_]*`, 40 caractères au plus : une valeur d'`enum` et un nom
de dossier sûrs.

**Un sujet par item.** Les définitions disent aussi comment départager : un item qui relève de
plusieurs sujets va au **premier** de la liste, dans cet ordre.

| Ordre | Sujet | Définition |
|---|---|---|
| 1 | `vulnerabilities` | une faille identifiée (CVE, GHSA) : catalogue CISA KEV, alertes GitHub des paquets suivis, article qui la décrit |
| 2 | `llm_security` | attaques et défenses propres aux modèles et aux agents (injection d'instructions, jailbreak, empoisonnement, porte dérobée), sans CVE ni GHSA |
| 3 | `agent_frameworks` | versions et nouvelles de LangChain, LangGraph, LlamaIndex et des cadres d'agents |
| 4 | `coding_assistants` | assistants de code (Claude Code et autres) : versions, fonctions, usages |
| 5 | `models` | nouveaux modèles, évaluations, capacités et limites annoncées |
| 6 | `ai_industry` | entreprises, produits, financements et régulation de l'IA |
| 7 | `cybersecurity` | incidents, campagnes d'attaque, outils et pratiques de sécurité hors IA, sans CVE ni GHSA |
| 8 | `software_engineering` | outils, langages et pratiques de développement hors IA |

Liste de départ proposée par la session K-B à partir des sources collectées (dépôts suivis,
`etl/sources/tracked_repositories.py` ; éditions TLDR `ai`, `infosec` et `dev`,
`etl/sources/tldr.py` ; arXiv sur la sécurité de l'IA, [specs-collecte.md](specs-collecte.md) ;
catalogue KEV ; alertes GitHub), validée par Sabine le 2026-10-15. Un item qui n'entre dans aucun
sujet est « non retenu » : il n'y a pas de sujet « autre ».

**Changer la liste.** On la modifie dans `core/config.py`, par une PR. Le `json_schema` envoyé au
modèle et le contrôle des sujets (contrôle 3) sont construits à partir de cette liste ; la
consigne du modèle ne change pas, puisque la liste voyage dans le message utilisateur. Les tests
utilisent leur propre liste de sujets, jamais les noms réels : un renommage ne casse aucun test.

**Limite.** Les fiches sont rangées par sujet (`wiki/veille/<sujet>/AAAA-MM-JJ.md`) : renommer un
sujet ouvre un nouveau dossier, et les anciennes fiches restent dans l'ancien. Option écartée :
lire la liste dans un fichier du dossier de données ou dans une variable d'environnement ; ce
serait un réglage de plus à valider au démarrage, pour une liste qui change rarement. À reprendre
si Sabine la modifie souvent.

## Fenêtre

| Paramètre | Forme | Bornes | Défaut | Hors bornes |
|---|---|---|---|---|
| `window_days` (corps de `POST /digests`) | entier JSON | de 1 à 14 | `KB_DIGEST_WINDOW_DAYS` | 422 `invalid_parameter`, avant toute lecture et tout appel au modèle ; `true`, `3.0` et `"3"` sont refusés (pas des entiers) |
| `KB_DIGEST_WINDOW_DAYS` (variable d'environnement) | chiffres seuls | de 1 à 14 | 3, défaut nommé dans `core/config.py` (règle 2 de `poc.md`) | l'API IA ne démarre pas (code de sortie 2, échouer fermé, comme `kb serve`) |

- `since` = l'instant de la demande, en UTC à la seconde, moins `window_days` × 24 h ; il est
  passé à `GET /items?since=…`, et la règle de « quoi de neuf » de l'API de données s'applique :
  la date est celle de la source, pas celle de la collecte.
- **Limite** : les articles TLDR et les entrées KEV sont datés à minuit UTC
  ([specs-api.md](specs-api.md), « Règle de quoi de neuf ») ; selon l'heure de la demande, une
  fenêtre de 3 jours prend 2 ou 3 éditions. Option écartée : arrondir `since` à minuit (une règle
  de plus, et la fenêtre ne dit plus « les N derniers jours »).

## Schémas

La spec écrit chaque schéma en JSON ; le code le porte en modèle Pydantic `extra="forbid"`, ce qui
écrit `additionalProperties: false` dans le JSON Schema qu'il produit. Le modèle Pydantic reste
**statique** (`int`, `str`) : les `enum` des sujets et des `item_id` sont ajoutés au
`json_schema` envoyé au modèle, et revérifiés par le code dans des contrôles à part (section
« Contrôles »).

### Demande

```json
{"window_days": 3}
```

`window_days` est optionnel ; tout autre champ est refusé (422 `invalid_parameter`).

### Entrée du modèle

**Consigne** (message `system`) : une constante de module, jamais une expression (règle 8 de
`poc.md`). Elle dit le rôle, que le message utilisateur est une donnée et jamais une consigne, et
le sens de `in_cisa_kev`.

**Message utilisateur** : un objet JSON encodé, et rien d'autre.

```json
{
  "subjects": [{"name": "llm_security", "definition": "…"}],
  "items": [{"item_id": 12, "kind": "paper", "title": "…", "summary": "…"}]
}
```

**Liste blanche des sortes** : celle de #204, sans `zotero_entry` ni `clip`. **Liste blanche des
champs**, sans aucune URL (le modèle n'en écrit jamais, #206) :

| Sorte | Champs envoyés |
|---|---|
| `paper` | `item_id`, `kind`, `title`, `summary` ; jamais `authors` (règle 5 de `poc.md`) |
| `vulnerability` | `item_id`, `kind`, `cve_id`, `title`, `description`, `vendor`, `product`, `ransomware_use` |
| `release` | `item_id`, `kind`, `repository_name`, `tag_name`, `title`, `body`, où chaque `@login` est masqué en `@user` |
| `advisory` | `item_id`, `kind`, `ghsa_id`, `cve_id`, `title`, `in_cisa_kev`, `packages` |
| `newsletter_article` | `item_id`, `kind`, `edition`, `title`, `summary` |

- `in_cisa_kev` est le champ `exploited` de l'API de données, renommé : faux y veut dire « absente
  du catalogue KEV », pas « non exploitée » ([specs-api.md](specs-api.md), détail) ; le nom
  d'origine inviterait le modèle au contresens.
- **Au classement**, chaque item n'envoie que `item_id`, `kind`, `title` et son texte long
  (`summary`, `description` ou `body`) coupé à 500 caractères : classer demande moins de texte que
  rédiger (jetons, délai).
- **À la rédaction**, chaque item envoie les champs du tableau, chacun coupé à 2 000 caractères ;
  une fiche reçoit **60 items au plus** (#204), les plus récents d'abord.
- Le découpage des appels de classement est à #205, sous un plafond de caractères par appel
  (`input_chars`) que #205 fixe.
- `items_truncated` compte les items dont un champ est coupé ; `items_dropped`, ceux laissés hors
  d'une fiche (au-delà de 60, ou disparus entre la liste et le détail : 404 `item_not_found`).

### Sortie du classement

`response_format` `json_schema`, `strict: true`.

```json
{
  "assignments": [{"item_id": 12, "subject": "llm_security"}],
  "not_retained": [7]
}
```

| Champ | Contrainte |
|---|---|
| `assignments[].item_id`, `not_retained[]` | `enum` des `item_id` envoyés dans cet appel |
| `assignments[].subject` | `enum` des sujets de `core/config.py` |
| ensemble | chaque item envoyé apparaît **exactement une fois**, dans `assignments` ou dans `not_retained` |

### Sortie de la rédaction

Un appel par sujet ; `response_format` `json_schema`, `strict: true`.

```json
{
  "claims": [
    {
      "text": "…",
      "item_ids": [12, 40],
      "facts": [{"value": "CVE-2026-1234", "item_id": 40}]
    }
  ],
  "not_retained": [7]
}
```

| Champ | Bornes | Contrainte |
|---|---|---|
| `claims` | 1 à 12 affirmations | — |
| `claims[].text` | 1 à 400 caractères | sans lien, image ni balise (contrôle 6) |
| `claims[].item_ids` | 1 à 10 | `enum` des `item_id` du sujet |
| `claims[].facts` | 1 à 5 | — |
| `claims[].facts[].value` | 3 à 120 caractères | un extrait recopié de l'item cité (identifiant, version, nombre, nom, courte expression), écrit aussi dans `text` |
| `claims[].facts[].item_id` | — | l'un des `item_ids` de l'affirmation |
| `not_retained` | — | `enum` des `item_id` du sujet |
| ensemble | — | chaque item du sujet est cité au moins une fois, ou non retenu, **jamais les deux** |

`max_tokens` de chaque appel est au moins la plus longue sortie que ces bornes permettent (calcul
à #150 et #205) : une troncature ne vient alors que d'une sortie hors bornes.

### Réponse

`200` :

```json
{
  "request_id": "1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e",
  "window": {"days": 3, "since": "2026-10-12T09:00:00Z", "until": "2026-10-15T09:00:00Z"},
  "digests": [
    {
      "subject": "llm_security",
      "claims": [{"text": "…", "item_ids": [12, 40]}],
      "sources": [{"item_id": 12, "kind": "paper", "title": "…", "url": "https://arxiv.org/abs/…"}],
      "not_retained": [7],
      "claims_removed": 1,
      "items_uncited": [40]
    }
  ],
  "failed_subjects": [{"subject": "models", "error": "llm_timeout"}],
  "not_retained": [3, 9],
  "items_in": 41,
  "items_truncated": 2,
  "items_dropped": 0
}
```

| Champ | Contenu |
|---|---|
| `request_id` | identifiant de la demande (UUID), repris par chaque ligne de métrique |
| `window` | `days`, et `since` et `until` en UTC, au format des dates de la base |
| `digests` | une fiche par sujet rédigé ; un sujet sans item n'a pas de fiche |
| `digests[].claims` | les affirmations gardées après la fidélité, sans leurs `facts` (contrôle interne) |
| `digests[].sources` | `item_id`, `kind`, `title`, `url` de chaque item des affirmations gardées, lus dans l'API de données, **jamais dans la sortie du modèle** ; une `url` qui ne commence ni par `http://` ni par `https://` est rendue nulle |
| `digests[].not_retained` | les items du sujet que le modèle n'a pas retenus |
| `digests[].claims_removed` | affirmations retirées par la fidélité |
| `digests[].items_uncited` | items du sujet qui ne sont plus cités après ces retraits |
| `failed_subjects` | chaque sujet en échec et son état nommé |
| `not_retained` | items non retenus au classement |
| `items_in`, `items_truncated`, `items_dropped` | compteurs de la section « Entrée du modèle » |

**Limite** : `sources[].title` est une donnée de source, pas une sortie du modèle ; le filtre du
Markdown ne s'y applique pas. L'échapper revient à qui écrira la fiche dans le coffre (`kb`, plus
tard).

Une erreur rend `{"error": "<état>"}`, comme l'API de données (section « États nommés »).

## Contrôles

Chaque sortie du modèle passe ces contrôles **dans cet ordre**, avant tout usage ; le premier qui
échoue nomme l'échec. `strict: true` demande au fournisseur de suivre le schéma ; le code ne s'y
fie pas et revérifie tout (défense en profondeur ; OWASP LLM01:2025 : valider le format de sortie
par du code déterministe).

| N° | Contrôle | Refuse | `failed_check` |
|---|---|---|---|
| 1 | `finish_reason` | `length` ou `model_length` → `llm_truncated` ; `error` → `llm_unavailable` | — |
| 2 | **Schéma** | un texte qui n'est pas du JSON, un champ en trop (`extra="forbid"`), un type ou une longueur hors bornes | `schema` |
| 3 | **Sujets** | un sujet hors de la liste de `core/config.py` | `subject` |
| 4 | **`item_id`** | un identifiant qui n'a pas été envoyé dans **cet** appel (un item inventé, ou d'un autre sujet) ; un `facts[].item_id` hors des `item_ids` de son affirmation | `item_id` |
| 5 | **Complétude** | au classement, un item absent ou présent deux fois ; à la rédaction, un item ni cité ni non retenu, ou les deux | `completeness` |
| 6 | **Markdown** (rédaction) | un `text` qui contient `(?i)[a-z][a-z0-9+.-]*://`, `(?i)www\.`, `![`, `[[`, `](` ou `<` | `markup` |
| 7 | **Fidélité** (rédaction) | voir ci-dessous : retire l'affirmation, n'est pas un échec | — |

- **Contrôles 2 à 6** : `llm_invalid_output`, **une** nouvelle tentative (#150) ; au second échec,
  le sujet échoue (rédaction) ou toute la demande (classement). Aucune fiche partielle n'est rendue.
  Une `ValidationError` n'est ni journalisée ni gardée : seul `failed_check` l'est (règle 5 de
  `poc.md`).
- **Contrôle 6** reprend les motifs de #206, avec une différence : `://` sans casse à la place de
  `http`. Chercher `http` refuserait « HTTP request smuggling », courant dans les descriptions du
  catalogue KEV, et laisserait passer `HTTPS://`. `](` refuse un lien Markdown sans schéma.

### Fidélité

Une fiche ne dit que ce que disent ses items (#207). Avant toute recherche, les deux textes sont
**normalisés** : Unicode NFKC, `casefold`, espaces réduites à une seule, tirets Unicode (U+2010 à
U+2015, U+2212) ramenés à `-`.

- Chaque `facts[].value` doit figurer dans le `text` de son affirmation **et** dans les champs
  **envoyés** de l'item qu'elle cite (`facts[].item_id`).
- Une valeur CVE (`CVE-…`) ou GHSA (`GHSA-…`) n'est trouvée que dans un champ identifiant
  (`cve_id`, `ghsa_id`) de l'item cité, jamais dans un texte libre. Un article TLDR n'a pas de tel
  champ : il ne porte pas de fait CVE ; la fiche cite la CVE par l'entrée KEV ou par l'alerte, si
  elles sont dans la fenêtre (décision de Sabine du 2026-10-15).
- Tout `CVE-…` ou `GHSA-…` écrit dans un `text` doit être déclaré comme fait.

Une affirmation qui manque à l'une de ces règles est **retirée et comptée** (`claims_removed`) ;
ce n'est pas un échec. Un item qui n'est plus cité après ces retraits passe dans `items_uncited`.
Si toutes les affirmations d'un sujet sont retirées, la fiche est rendue sans affirmation : c'est
ce qui a été observé. `fidelity_rate` = `facts_found` / `facts_checked`.

- **Ce qu'elle vérifie** : chaque valeur déclarée est écrite dans la phrase et existe dans l'item
  qu'elle cite.
- **Ce qu'elle ne vérifie pas** : le sens de la phrase (une négation, une paraphrase fausse), un
  nombre écrit dans la phrase sans être déclaré, ni ce que l'item dit au-delà des 2 000 caractères
  envoyés.

### Injection d'instructions

Un item collecté peut porter une consigne (OWASP LLM01:2025, injection indirecte). Ce que fait la
spec :

- la consigne est une constante de module ; sujets et items vont dans le message utilisateur,
  encodés en JSON ; aucun texte d'item n'entre dans un message `system` (règle 8 de `poc.md`) ;
- le modèle ne reçoit aucune URL ; tout lien, image ou balise en sortie est refusé (contrôle 6) ;
- un item piégé ne peut ni créer un sujet (contrôle 3), ni citer un item inventé (contrôle 4) ;
- une affirmation sur une CVE tirée d'un texte libre est retirée (fidélité).

La consigne n'est pas la défense ; le schéma fermé et les contrôles le sont. Ce que la spec ne
couvre pas : un item qui oriente le classement entre deux sujets permis, ou qui fait écrire une
phrase fausse appuyée sur des faits vrais.

## Métriques

Une ligne JSON par appel au modèle, sur la sortie standard, sans fichier (règle 4 de `poc.md`).
Un **appel** est un classement, ou la rédaction d'un sujet, nouvelle tentative comprise : jetons et
durées sont cumulés sur la ligne.

| Champ | Contenu |
|---|---|
| `ts` | date de la ligne, ISO 8601 UTC à la seconde (`2026-10-15T09:00:00Z`, règle 3 de `conventions.md`) |
| `event` | `llm_call` |
| `request_id` | celui de la réponse |
| `stage` | `classify` ou `write` |
| `subject` | le sujet rédigé ; nul au classement |
| `provider`, `model` | lus dans la configuration (#150) |
| `prompt_version` | constante de la consigne utilisée (`classify-1`, `write-1`), changée à la main avec elle |
| `items_in` | items envoyés dans l'appel |
| `items_truncated`, `items_dropped` | compteurs de la section « Entrée du modèle », pour cet appel |
| `input_chars` | longueur du message utilisateur |
| `tokens_in`, `tokens_out` | `usage` rendu par le fournisseur |
| `data_fetch_ms` | durée de la lecture par l'API de données ; sur la ligne du classement seulement, nul ailleurs |
| `llm_ms`, `check_ms` | durée des appels au modèle, durée des contrôles |
| `attempts` | 1 ou 2 |
| `outcome` | `ok`, ou l'état `llm_*` de l'appel |
| `finish_reason` | celui de la dernière tentative |
| `schema_valid` | la dernière tentative a passé le contrôle 2 |
| `failed_check` | le contrôle qui a refusé la dernière tentative (section « Contrôles ») ; nul si `ok` |
| `facts_checked`, `facts_found`, `claims_removed`, `items_uncited` | compteurs de la fidélité (rédaction) ; nuls au classement |
| `cost_estimated` | jetons × prix au million lus dans `core/config.py` ; 0 en offre gratuite |

`ts`, `stage`, `failed_check` et `items_dropped` s'ajoutent à la liste de #156.

**Jamais** dans une ligne : le texte d'un item, la consigne, la sortie du modèle, un titre, un
auteur, une clé (règle 5 de `poc.md`). Un échec `data_api_*` ne fait aucun appel au modèle, donc
aucune ligne `llm_call` : il va au journal de fonctionnement (sortie d'erreur), avec le
`request_id`.

## États nommés

| État | Quand | Le classement échoue (toute la demande) | La rédaction d'un sujet échoue |
|---|---|---|---|
| `llm_invalid_output` | contrôles 2 à 6, deux fois | 502 | le sujet va dans `failed_subjects` |
| `llm_truncated` | `finish_reason` `length` ou `model_length` ; pas de nouvelle tentative (même entrée, `temperature=0`) | 502 | `failed_subjects` |
| `llm_rate_limited` | 429 du fournisseur, après la nouvelle tentative | 503, avec `Retry-After` | `failed_subjects` |
| `llm_unavailable` | 5xx ou connexion refusée, après la nouvelle tentative ; autre 4xx, sans nouvelle tentative ; `finish_reason` `error` | 502 | `failed_subjects` |
| `llm_timeout` | pas de réponse dans le délai du client (#150) | 504 | `failed_subjects` |
| `data_api_unavailable` | API de données injoignable, ou 5xx | 502 | — |
| `data_api_timeout` | délai de lecture dépassé | 504 | — |
| `data_api_unauthorized` | 401 de l'API de données : clé `AI_DIGEST` refusée (sans clé, l'API IA ne démarre pas, règle 2 de `poc.md`) | 502 | — |
| `data_api_invalid_response` | réponse hors du schéma attendu | 502 | — |
| `invalid_parameter` | demande mal formée, `window_days` hors bornes | 422 | — |
| `invalid_api_key` | appel sans clé, ou clé inconnue (#156) | 401 | — |
| `route_not_found`, `method_not_allowed`, `internal_error` | comme l'API de données | 404, 405, 500 | — |

- Les états `data_api_*` sont ceux de la lecture par l'API de données (#204). Un item disparu entre
  la liste et le détail (404 `item_not_found`) n'est pas un échec : il est sauté et compté
  (`items_dropped`).
- 502, 503 et 504 disent la panne de l'amont, comme une passerelle (RFC 9110, § 15.6) : le client
  distingue « réessayer plus tard » (503, 504) d'une sortie fautive (502).
- **Échec partiel** : la réponse est 200 dès que le classement a réussi ; chaque sujet en échec est
  nommé dans `failed_subjects`, et les autres sont rendus (#205).
- Une fenêtre sans item rend 200 avec `digests` vide, sans appel au modèle.

## Sources

Consultées le 2026-10-15.

- [Chat Completion API](https://docs.mistral.ai/api) — Mistral, lu par Context7
  (`/mistralai/platform-docs-public`) : `response_format` `json_schema` « guarantees the message
  the model generates is in JSON and follows the schema you provide » ; `finish_reason` parmi
  `stop`, `length`, `model_length`, `error`, `tool_calls` (contrôle 1, états nommés).
- [Custom Structured Outputs](https://docs.mistral.ai/studio-api/conversations/structured-output/custom)
  — Mistral, lu par Context7 : `json_schema` avec `name`, `schema` et `strict: true`
  (« always recommended »). Un `enum` d'entiers n'y est pas montré : à vérifier par #158 ; le code
  revalide dans tous les cas (contrôles 3 et 4).
- [Models, « Extra data »](https://docs.pydantic.dev/latest/concepts/models/#extra-data) — Pydantic,
  lu par Context7 : `extra='forbid'` refuse un champ en trop (`extra_forbidden`) et écrit
  `additionalProperties: false` dans le JSON Schema (schémas, contrôle 2).
- [LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — OWASP
  Gen AI Security Project, relevé par recherche web : définir et valider le format de sortie par du
  code déterministe ; borner le rôle dans la consigne ; filtrer les sorties (contrôles, injection).
- [RFC 9110, § 15.6](https://www.rfc-editor.org/rfc/rfc9110#section-15.6) — IETF, relevé par
  recherche web : 502 (§ 15.6.3, une réponse invalide de l'amont), 503 (§ 15.6.4, indisponibilité
  temporaire, `Retry-After` permis), 504 (§ 15.6.5, l'amont n'a pas répondu à temps), pour un
  serveur qui agit en passerelle (états nommés).
