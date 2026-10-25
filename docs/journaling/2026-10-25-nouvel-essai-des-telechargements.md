# Un seul nouvel essai, poli envers les sources

- Date : 2026-10-25
- Branche : `fix/source-download-retry`
- Issue : aucune (constat du 2026-10-24 sur l'extract ; demande de Sabine du 2026-10-25)
- Fichiers : `src/k_b/etl/http_retry.py` (nouveau), `src/k_b/etl/http_download.py`,
  `src/k_b/etl/sources/github_api.py`, `tests/etl/test_http_retry.py`, `tests/etl/test_http_download.py`,
  `tests/etl/sources/test_github_api.py`, `tests/etl/conftest.py`, `tests/etl/http_helpers.py`

## Le pourquoi

Une source qui recevait un 429 (« trop de requêtes »), un 5xx ou une coupure réseau échouait tout de suite : sa
date de dernière collecte restait, et seule la collecte suivante rattrapait. Rien ne lisait le `Retry-After` ni le
quota de GitHub. Un service qui demande d'attendre doit être écouté (c'est ce que demandent les conditions d'usage
d'arXiv et de GitHub), et une panne passagère ne doit pas coûter une collecte.

## Le comment

### Deux rôles, deux fichiers

`http_download.py` télécharge ; `http_retry.py` décide s'il faut retenter et combien attendre. `download` ne fait que
demander la décision et l'appliquer (`src/k_b/etl/http_download.py:52-65`) :

```python
    except (URLError, ConnectionError) as error:
        wait = find_retry_wait(error, trusted_url_prefix, rate_limited_wait_seconds)
        if wait is None:
            raise
```

`URLError` couvre un statut HTTP d'erreur (`HTTPError` en hérite) et une connexion refusée ; `ConnectionError`, une
connexion coupée avant la réponse, que `http.client` lève telle quelle, hors d'un `URLError`. La décision est prise
ailleurs.

### La règle

`find_retry_wait` (`src/k_b/etl/http_retry.py:30-67`) répond « attendre tant » ou « ne pas retenter » :
- 429, 5xx, ou 403 qui porte un `Retry-After` (la limite secondaire de GitHub) : attendre le `Retry-After` s'il
  est en secondes et ne dépasse pas 60 s, jamais moins de 3 s (`http_retry.py:67`) ; sans lui, 5 s, et pour un 429
  l'attente donnée par l'appelant (60 s pour GitHub, `github_api.py:34`) ;
- `Retry-After` au-delà de 60 s : ne pas retenter, une attente plus courte donnerait la même réponse ;
- connexion qui échoue : 5 s ; délai dépassé (`TimeoutError`, `http_retry.py:44`) : ne pas retenter, cela
  doublerait les 30 s déjà attendues ;
- quota épuisé (`x-ratelimit-remaining: 0`) : ne pas retenter, la remise à zéro peut être dans une heure ;
- réponse d'erreur servie hors du préfixe de confiance, après une redirection : ses en-têtes ne sont pas lus.

### Le quota épuisé se lit dans le journal

`note_rate_limit_reset` (`http_retry.py:79`) ajoute à l'erreur une note : « rate limit reached, no request left
until 2026-10-25T16:00:00+00:00 ». `extract.py` écrit déjà les notes d'une erreur sur la ligne datée de la source en
échec : rien d'autre à changer pour qu'elle apparaisse.

## Choix faits et options écartées

| Retenu | Écarté, et pourquoi |
|---|---|
| Un seul nouvel essai | plusieurs, à attente croissante : la collecte est planifiée, la suivante rattrape |
| La règle de l'appel au modèle (`llm_client.py`) | une règle à part : deux règles pour un même sujet |
| 5 s par défaut | 2 s (le modèle) : arXiv demande 3 s entre deux requêtes |
| 60 s pour un 429 de GitHub | 5 s : GitHub demande au moins une minute sans `Retry-After` ; 60 s aussi sur un 5xx : une panne de GitHub coûterait une minute par requête (revue de code) |
| Jamais moins de 3 s | suivre un `Retry-After: 0` : arXiv demande 3 s entre deux requêtes (revue de code) |
| Les en-têtes d'une erreur servie hors du préfixe ne sont pas lus | les lire : un hôte tiers déciderait de l'attente (revue de code) |
| Quota épuisé : échouer, noter l'heure | attendre la remise à zéro : jusqu'à une heure dans une collecte |
| Un module `http_retry.py` | tout dans `http_download.py` : deux rôles dans un fichier (demande de Sabine : structurer) |
| L'URL journalisée sans sa requête | l'URL entière : une source pourrait un jour y mettre une valeur à ne pas écrire |

## Preuve

| Test | Ce que ça démontre |
|---|---|
| `test_a_429_or_a_5xx_without_retry_after_waits_the_default`, `test_a_retry_after_in_seconds_is_waited` | 429 et 5xx retentés, `Retry-After` suivi |
| `test_a_retry_after_above_the_maximum_gets_no_retry` (61, 10 chiffres, 5 000 chiffres) | pas d'attente démesurée, pas d'`int()` sur un nombre géant |
| `test_a_retry_after_not_in_seconds_is_read_as_no_header` (date HTTP, `-1`, `1.5`, chiffre pleine chasse) | seuls les chiffres ASCII sont lus |
| `test_a_rate_limit_with_no_request_left_gets_no_retry`, `..._notes_its_reset_in_utc` | quota épuisé : pas de nouvel essai, heure de remise à zéro en UTC |
| `test_a_timeout_gets_no_retry`, `test_a_failed_connection_waits_the_default` | délai dépassé et connexion distingués |
| `test_a_second_failure_is_raised_without_a_third_request` | jamais plus de deux requêtes |
| `test_only_a_rate_limited_request_waits_the_minute_github_asks` | 60 s pour un 429 de GitHub, 5 s pour un 502 |
| `test_a_short_retry_after_still_waits_the_3_seconds_arxiv_asks` | jamais moins de 3 s |
| `test_an_answer_served_from_outside_the_trusted_prefix_is_not_read` | un hôte tiers ne décide de rien |
| `test_a_403_with_retry_after_is_the_secondary_rate_limit_of_github_and_is_retried` | limite secondaire de GitHub |
| `test_a_failed_connection_is_retried` (refusée, coupée) | les deux formes d'échec de connexion |
| `test_the_retry_is_logged_without_the_query_of_the_url` | la ligne de journal |
| 2 515 tests en 18 s, ruff, mypy | aucun test n'attend vraiment (fixture `no_wait_before_a_retry`) |

## Ce que tu dois pouvoir défendre

- **Pourquoi pas de nouvel essai sur un délai dépassé ?** Il doublerait 30 s d'attente, et un service qui ne répond
  pas en 30 s a peu de chances de répondre aussitôt après. Même choix que pour le modèle.
- **Un 403 de GitHub est-il retenté ?** Seulement s'il porte un `Retry-After` : c'est alors la limite secondaire de
  GitHub. Sans lui, un 403 est d'abord un refus (jeton, droits) : la source échoue, la collecte suivante redemande.
- **Que se passe-t-il si GitHub coupe le quota au milieu d'une collecte ?** Les sources GitHub suivantes échouent
  chacune sans nouvel essai, avec l'heure de remise à zéro dans le journal ; les autres sources continuent.

## Zones non vérifiées

- Aucun vrai 429 ni 5xx n'a été provoqué sur une source réelle : la règle est vérifiée par les tests seulement.
- L'heure de remise à zéro suppose `x-ratelimit-reset` en secondes depuis l'époque UTC, comme GitHub le documente.

## Ce qui reste

- Lire la page suivante d'une liste GitHub pleine (point 10 du constat du 24/10).
- La lecture du `Retry-After` existe en double, ici et dans `ai_api/connectors/llm_client.py` : la mettre dans
  `core` toucherait l'API IA, hors de cette PR.
- Écartés à la revue : une erreur de certificat ou de DNS est retentée une fois (5 s perdues, sans risque) ; un 501
  aussi (irréaliste pour ces sources, et la règle reste celle du modèle).

## Sources

| Source | Consultée |
|---|---|
| [Rate limits for the REST API — GitHub Docs](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) | 2026-10-25 |
| [Best practices for using the REST API — GitHub Docs](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api) | 2026-10-25 |
| Terms of Use for arXiv APIs (3 s entre deux requêtes), relevé dans la fiche de source du 2026-10-24 | 2026-10-24 |
| RFC 9110, § 10.2.3 (`Retry-After`) | déjà cité par `llm_client.py` |
