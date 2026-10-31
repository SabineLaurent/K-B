# La fiche GitHub de chaque candidat du compte rendu des tendances

- Date : 2026-10-31
- Branche : `feat/trend-report-github-cards`
- Issue : #367 (plan de time-knight, validé par Sabine le 31/10)
- Suite de : [2026-10-30-api-ia-compte-rendu-factuel-tendances.md](2026-10-30-api-ia-compte-rendu-factuel-tendances.md)
  (#366, le compte rendu factuel) et [2026-10-30-kb-trend-report-commande.md](2026-10-30-kb-trend-report-commande.md)
- Fichiers principaux : `src/k_b/ai_api/connectors/github_settings.py`,
  `src/k_b/ai_api/connectors/github_client.py`, `src/k_b/ai_api/repository_cards.py`,
  `src/k_b/ai_api/trend_reports.py`, `src/k_b/post/trend_report_sheets.py`, `docs/tendances.md`

## Le pourquoi

Le compte rendu des tendances de #366 dit quels dépôts montent dans les classements de GH Archive,
mais GH Archive ne dit rien d'un dépôt : ni sa licence, ni sa date de création, ni son langage, et
il ne voit qu'environ 1 % des étoiles. Pour que le modèle choisisse (#368) et que la fiche du coffre
dise ce qu'est un dépôt (#369), il faut lire sur GitHub la **fiche** de chaque candidat :
`GET /repos/{owner}/{repo}`.

#367 fait cette lecture, dans l'API IA, pour les 60 candidats au plus, une requête après l'autre,
avant tout appel au modèle. Rien n'est gardé entre deux demandes (règle 7 de `poc.md`). La réponse
de `POST /trend-reports` gagne les faits de chaque dépôt rapporté et les compteurs des candidats ;
`kb` n'écrit encore aucun fait dans le coffre, seulement une ligne quand GitHub a écarté des
candidats.

## Le comment

### 1. Un second jeton, refusé s'il n'est pas *fine-grained*

`kb serve-ai` ne démarre plus sans `KB_AI_GITHUB_TOKEN`. Le jeton est lu une fois, depuis
l'environnement reçu en paramètre (règle 2 de `poc.md`), et refusé sans jamais être cité :

```python
if not TOKEN_CHARACTERS.fullmatch(token):
    return (
        f"{GITHUB_TOKEN_VARIABLE}: token with a character outside"
        f" {TOKEN_CHARACTERS.pattern}"
    )
if not token.startswith(FINE_GRAINED_PREFIX):
```
(`src/k_b/ai_api/connectors/github_settings.py:27-32`)

La liste fermée des caractères empêche qu'un retour à la ligne glissé dans le `.env` devienne un
second en-tête HTTP. Le préfixe `github_pat_` refuse un jeton *classic*, qui porte des *scopes* :
plus de droits qu'il n'en faut pour lire des dépôts publics (moindre privilège,
`docs/jeton-github.md`). La fonction rend un `GithubSettings` ou un texte de refus, jamais une
exception : `serve_ai_command.py:45` journalise le refus et sort en `ExitCode.NOT_STARTED`. Le jeton
est tenu en `SecretStr`, qui s'affiche `**********` si on l'imprime par erreur.

### 2. Une lecture bornée de partout : budget, échéance, taille

Chaque requête passe par `send`, qui vérifie d'abord le budget et l'échéance :

```python
if reading.requests >= GITHUB_MAX_REQUESTS_PER_REPORT:
    raise GithubError("github_unavailable")
if reading.deadline.is_passed():
    raise GithubError("github_timeout")
reading.requests += 1
```
(`src/k_b/ai_api/connectors/github_client.py:170-174`)

Trois bornes, trois risques :
- **le budget** (70 requêtes, `core/config.py:104`) : 60 candidats et la place de leurs relances ;
  c'est le client qui compte, relances comprises, donc aucun appelant ne peut l'oublier ;
- **l'échéance** : la même `Deadline` de 60 s que les lectures de l'API de données ; chaque délai
  httpx est réduit à ce qui reste (`deadline.cap`) ;
- **la taille du corps** (`MAX_GITHUB_REPOSITORY_BYTES = 400_000`, `core/config.py:112`, environ 60 fois
  la fixture de 6 382 octets) : refusée sur l'en-tête `Content-Length`, puis pendant la lecture, en
  octets décodés (un corps compressé est borné par ce qu'il pèse une fois lu,
  `github_client.py:194-214`).

Les exceptions de httpx sont relancées `from None` : leur message cite l'URL, donc le nom du dépôt,
que ni les journaux ni les traces ne doivent porter (registre des traitements).

### 3. Chaque statut a un sens nommé

`read_repository` traduit la réponse en une fiche, un motif d'écart, ou une erreur qui arrête tout :

```python
if status == httpx2.codes.OK:
    return to_card(answer, repository_id)
if httpx2.codes.is_redirect(status):
    # Not followed (core/outbound.py): a repository moved, which its name no longer names.
    return "moved"
```
(`src/k_b/ai_api/connectors/github_client.py:153-157`)

- 200 → la fiche, lue par un schéma strict qui ignore les champs non lus (le propriétaire, son
  avatar) ; un `id` différent de celui de GH Archive → écarté `id_mismatch` (le nom désigne
  désormais un autre dépôt) ;
- 3xx → `moved`, **non suivie** (`follow_redirects=False`) ; 404 et 410 → `not_found` ; 451 →
  `unavailable_for_legal_reasons` ;
- 403 : si c'est une **limite** (`x-ratelimit-remaining: 0`, un `retry-after`, ou un message qui
  contient « rate limit » ou « abuse », `is_rate_limit`, `github_client.py:240`), arrêt en 503
  `github_rate_limited` ; sinon le candidat est écarté `forbidden`, et le 3e d'un compte rendu
  arrête en 502 `github_forbidden` (`count_forbidden`, `:255`) ;
- tout 429 → `github_rate_limited` ; 401 → `github_unauthorized` ;
- 5xx → une relance **sans attente**, puis `github_unavailable` ;
- tout autre statut, un corps illisible ou hors schéma → `github_invalid_response`.

Le `Retry-After` renvoyé à `kb` (`find_retry_after`, `:277`) : le `retry-after` de GitHub ; sinon,
si plus aucune requête ne reste, le reset moins l'heure de la demande, 60 s au moins ; sinon 60 s ;
jamais plus de 3 600 s.

### 4. Les faits et leurs prudences, en code pur

`repository_cards.py` ne lit rien : il transforme une fiche en faits, et compte les candidats.

```python
if card.created_at > now - timedelta(days=TREND_RECENT_REPOSITORY_DAYS):
    cautions.append("created_recently")
if card.license is None:
    cautions.append("no_license")
```
(`src/k_b/ai_api/repository_cards.py:74-77`)

`now` est l'heure de la demande, reçue de la dépendance `RequestTime` : le test fixe l'heure sans
toucher à l'horloge. Comparaison stricte : un dépôt créé à 7 jours pile n'est pas « récent ». La
licence vaut `license.spdx_id`, et `None` quand GitHub n'en reconnaît aucune (`license` nul,
`spdx_id` nul ou `NOASSERTION`). `CandidateCounts.count` (`:50-57`) garantit l'invariant
`selected = read + somme des dropped`, chaque motif présent, à 0 s'il n'a servi.

### 5. Un candidat écarté sort du compte rendu, et se compte

```python
if trajectory.criteria and trajectory.repository_id not in cards.dropped_ids
```
(`src/k_b/ai_api/trend_reports.py:292`)

Un dépôt écarté par GitHub ne figure plus dans `repositories[]` : son nom peut désigner un autre
dépôt, et le coffre en ferait un lien. Pour que ce retrait se voie, `kb` relit les compteurs par son
schéma fermé et écrit une ligne, seulement si au moins un candidat est écarté :
« Candidats écartés par GitHub : n (introuvables : …, bloqués : …, …) », motifs à zéro omis
(`src/k_b/post/trend_report_sheets.py:162-170`). Sans écarté, le fichier est celui de #366.

Le span `read_repository_cards` (`trend_reports.py:255-280`) porte des comptes et des états, jamais
un nom de dépôt ni un `repository_id`.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un 403 hors limite écarte le candidat ; le 3e arrête en `github_forbidden` (Q1 (b), décision de Sabine du 31/10) | La doc de GitHub donne le 403 comme réponse propre de l'endpoint : un dépôt toujours refusé bloquerait chaque compte rendu | (a) tout 403 arrête : un seul dépôt bloquerait la période ; nommer le 3e `github_rate_limited` : ce serait nommer une supposition (`code.md`) |
| Préfixe `github_pat_` exigé | Moindre privilège : un jeton *classic* porte des *scopes* | Accepter tout jeton |
| Le budget compté par le client, relances comprises | Aucun appelant ne peut l'oublier ; les README de #369 le partageront | Un compte par appelant |
| Tous les candidats lus, même hors critère (plan, choix 3) | C'est le contrat ; #368 les envoie au modèle | Lire seulement les dépôts rapportés : #368 referait la lecture |
| Relance d'une 5xx sans attente | Une attente de 5 s mangerait l'échéance de 60 s | L'attente de la collecte (`RETRY_WAIT_SECONDS`) |
| Délais de la collecte vers un service distant (`HTTP_TIMEOUT_SECONDS`, 30 s), réduits par l'échéance (correction 12 du plan) | GitHub est distant | Les délais de l'API de données, prévus pour la même machine |
| La lecture bornée copiée de `data_api_client.py` (2e copie) | `code.md` : factoriser à la 3e ; la décision ouverte « Une borne de lecture » la réunira dans `core/outbound.py` | Factoriser dès maintenant |
| `kb` n'écrit aucun fait, seulement la ligne des écartés | La mise en page d'un dépôt est fixée par #369 | Rendre les faits dès #367 : deux mises en page à écrire |
| `API_URL` passé dans `core/github_api.py` | La collecte et l'API IA l'importent du même endroit (couches, règle 5 de `conventions.md`) | Le dupliquer |

## Tri des revues

**`/code-review high`** (10 constats ; tranchés par time-knight, délégation de Sabine du 15/10) :

| n° | Constat | Décision | Raison |
|---|---|---|---|
| 1 | Les 60 candidats sont lus, même hors critère ; l'un peut faire échouer le compte rendu | Écarté | Choix 3 du plan ; le 3e 403 qui arrête = Q1 (b), décidée par Sabine |
| 2 | « Dépôts écartés par GitHub » compte aussi des candidats hors critère | Corrigé | « Candidats écartés par GitHub » : « Dépôts » laissait croire à des dépôts rapportés retirés |
| 3 | `k_b.repositories.reported` compté avant les écartés | Corrigé par la doc | Décrit dans « Traces » de `docs/tendances.md`, avec les autres attributs du span des fenêtres |
| 4 | Une 5xx au corps trop gros devient `github_invalid_response`, sans relance | Écarté vers #376 | Même défaut sur `main` dans `data_api_client.py` ; corriger une seule copie ferait diverger les deux |
| 5 | L'échéance testée après le dernier morceau jette un corps complet | Écarté | Identique sur `main` ; l'échéance est l'échéance |
| 6 | 60 s par défaut contredit la docstring de `to_api_error` | Docstring corrigée | 60 s = correction 3 du plan ; « 0 » transmis tel quel, `kb` n'attend pas de lui-même |
| 7 | `language` laisse passer les caractères de format (Cf) | Corrigé (relecteur neuf, xhigh) | Motif `[^\p{Cc}\p{Cf}\p{Co}\p{Zl}\p{Zp}]` ; une valeur refusée → `github_invalid_response`, tout le compte rendu s'arrête (échec fermé) |
| 8 | Deux docstrings citent une issue ou un plan | Corrigé | `code.md` : ni rappel d'issue ni historique |
| 9 | `DROP_REASON_LABELS` non relié aux motifs | Corrigé par un test | Ses clés = les champs de `DroppedCandidates`, dans l'ordre |
| 10 | 2e copie de la lecture bornée | Écarté | Correction 13 du plan |

**`/security-review`** : aucune vulnérabilité de confiance suffisante (un sous-agent de détection,
aucun à filtrer). L'écart noté sous le seuil est le constat 7 ci-dessus.

**`/code-review medium`** sur les corrections (6 constats) :

| n° | Constat | Décision | Raison |
|---|---|---|---|
| 1 | Le commentaire du motif dit « comme `digest_sheets.py` », dont la liste a Cs et pas Co | Commentaire corrigé | Le motif reste ; un surrogate isolé est refusé par le JSON |
| 2 | Deux formes de « caractère caché » (DRY) | Écarté | Deux couches, deux raisons ; une constante commune toucherait `digest_sheets.py`, hors périmètre |
| 3 | La docstring de la lecture bornée a perdu son pourquoi | Écarté | Constat 8 de la 1re revue ; le pourquoi est dans le journal ADR et #376 |
| 4 | `language` accepte espaces seuls et points non attribués | Écarté | Noms de la liste fermée de Linguist ; aucun chemin vers journal, trace ou coffre à #367 |
| 5 | « Traces » ne nomme qu'un attribut du span des fenêtres | Corrigé par la doc | Les six nommés |
| 6 | « Dépôts écartés » à côté de « Candidats écartés par GitHub » | Écarté | Deux ensembles, deux mots : le but du constat 2 |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_card_is_read_from_a_real_answer_with_the_headers_of_k_b` (`tests/ai_api/test_github_client.py:80`) | Une vraie réponse de GitHub (fixture `fastapi/fastapi`) donne la fiche ; les quatre en-têtes partent |
| `test_a_redirection_is_not_followed_and_leaves_the_candidate_out`, `test_a_repository_gone_or_blocked_is_left_out`, `test_another_id_leaves_the_candidate_out` | 3xx, 404, 410, 451 et `id` différent écartent le candidat |
| `test_a_403_of_rate_limit_stops_with_its_retry_after`, `test_any_429_stops_as_a_rate_limit` | Une limite arrête, avec le bon `Retry-After` (en-tête, reset, 60 s) |
| `test_a_403_alone_leaves_the_candidate_out_and_the_third_stops_the_reading` | Q1 (b) |
| `test_a_server_error_is_retried_once_without_wait`, `test_two_server_errors_are_github_unavailable` | La relance unique d'une 5xx |
| `test_the_requests_of_a_report_stop_at_the_budget`, `test_a_retry_counts_in_the_budget` | La 71e requête n'est pas envoyée |
| `test_a_body_announced_beyond_the_bound_is_refused`, `test_a_body_beyond_the_bound_without_its_length_is_refused` | La borne de taille, avant et pendant la lecture |
| `test_an_answer_out_of_its_schema_is_an_invalid_response` (dont `language-format`, `-zero-width`, `-line-separator`, rouges avant le constat 7) | Le schéma refuse ; les caractères cachés aussi |
| `test_created_recently_is_strictly_less_than_seven_days_before_the_request` (`tests/ai_api/test_repository_cards.py:52`) | La règle des 7 jours pile |
| `test_a_token_refused_is_named_never_quoted` (`tests/ai_api/test_github_settings.py:47`), `test_serve_ai_says_it_loaded_the_github_token_never_its_value` | Le jeton n'est jamais cité, ni refusé ni chargé |
| `test_without_any_window_github_is_not_called` (`tests/ai_api/test_trend_report_router.py:772`) | Période vide : zéro requête à GitHub |
| `test_neither_the_traces_nor_the_logs_hold_a_repository` (`:620`) | Ni trace ni journal ne porte un nom de dépôt |
| `test_a_candidate_left_out_by_github_leaves_the_report_and_is_counted` (`:718`) | Le choix 2 du plan |
| `test_the_candidates_left_out_by_github_are_counted_by_reason_after_the_table` (`tests/post/test_trend_report_sheets.py:232`) | La ligne du coffre, rouge avant le constat 2 |
| `uv run pytest` → 3079 passed, 11 deselected ; `ruff check --no-cache`, `ruff format --check`, `mypy` verts | Les contrôles du dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un candidat écarté sort-il du compte rendu, au lieu d'y rester sans faits ?** Un 301,
   un 404 ou un `id` différent disent que le nom ne désigne plus le dépôt classé : le coffre en
   ferait un lien vers un autre dépôt. Il est compté, et `kb` le dit en une ligne
   (`trend_reports.py:292`, `trend_report_sheets.py:162`).
2. **Pourquoi ne pas suivre la redirection, comme GitHub le recommande ?** Suivre enverrait le jeton
   et la requête vers une adresse que K-B n'a pas choisie, et le nom resterait faux dans le coffre.
   `open_http_client` ne suit jamais (`core/outbound.py`) ; l'écart à la recommandation est écrit
   dans `docs/tendances.md`.
3. **Que se passe-t-il si GitHub limite le débit au 30e candidat ?** Plus aucune requête : 503
   `github_rate_limited` avec un `Retry-After`, aucun compte rendu partiel, la période n'avance pas ;
   `kb` cite le délai et s'arrête (`github_client.py:264-286`).
4. **Où est la sécurité du jeton ?** Pas de défaut, refus sans citation, caractères en liste fermée
   (pas d'injection d'en-tête), préfixe *fine-grained* (moindre privilège), `SecretStr`, exceptions
   httpx relancées `from None`, aucune redirection suivie (`github_settings.py:22-34`).
5. **Pourquoi lire 60 candidats alors que 5 seulement sont rapportés ?** Le contrat le demande :
   #368 enverra au modèle les faits de tous les candidats pour choisir. Lire seulement les rapportés
   obligerait #368 à refaire la lecture. Le prix : un candidat non rapporté peut faire échouer le
   compte rendu (constat 1 de la revue, écarté).

## Zones non vérifiées

- **Le vrai GitHub n'a pas été appelé** : aucun test ne le fait (correction 2 du plan). La forme de la
  réponse vient d'une vraie réponse gardée en fixture, mais les en-têtes de limite (403, 429,
  `x-ratelimit-*`) sont simulés d'après la doc de GitHub, pas observés.
- **La durée de 60 lectures** sous l'échéance de 60 s n'est pas mesurée (à #370).
- **Les cas où un dépôt répond lui-même 403** : la doc de GitHub ne les décrit pas ; Q1 (b) les
  suppose rares.
- `tests/e2e/test_real_export.py` est hors CI et hors mypy : vérifié à la main (`mypy` : 12
  `import-untyped` contre 11 sur `main`, même sorte ; `pytest --collect-only` le collecte), pas
  rejoué contre de vrais services.
- Le motif `\p{…}` de `language` repose sur le moteur de regex de pydantic-core (Rust) en mode
  strict ; vérifié par les tests, pas dans sa documentation.

## Ce qui reste

- Les faits dans le coffre : #368 (choix du modèle, description lue et nettoyée) et #369 (mise en
  page, README).
- Une 5xx au corps trop gros, nommée indisponible et relancée : #376, avec la borne de lecture
  commune dans `core/outbound.py` avant le 08/11.
- L'échéance de 60 s ne tient pas pour les appels au modèle de #368-#369 : à revoir dans le plan
  de #368.
- Sabine crée le second jeton et l'ajoute à son `.env` avant de relancer `kb serve-ai`
  (`docs/jeton-github.md`).
