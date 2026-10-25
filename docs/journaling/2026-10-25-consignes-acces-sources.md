# Consignes d'accès des sources : trois écarts corrigés

- **Date** : 2026-10-25
- **Branche** : `fix/source-access-rules`
- **Issue** : aucune. La source est la vérification indépendante du 25/10, demandée par Sabine
  (dépôt `certif-deviaa-rncp37827`, `verifications-kb/2026-10-25-consignes-acces-sources.md`).
- **Fichiers principaux** : `src/k_b/etl/http_retry.py`, `src/k_b/etl/sources/github/api.py`,
  `src/k_b/etl/sources/tldr.py`, `src/k_b/data_api/app.py`, `README.md`
- **Série** : suite de [nouvel essai des téléchargements](2026-10-25-nouvel-essai-des-telechargements.md),
  qui a posé les règles de nouvel essai que cette PR complète.

## Le pourquoi

La vérification a comparé le code de collecte aux consignes publiées par chaque source. Elle n'a
trouvé ni limite dépassée ni page interdite, mais trois écarts :

1. arXiv demande à tous les utilisateurs de son API d'afficher une mention de crédit « on your
   product ». K-B ne l'affichait nulle part.
2. Quand GitHub annonce un quota épuisé, il demande de ne plus rien envoyer avant la remise à
   zéro. K-B ne réessayait pas la requête refusée, mais les sources GitHub suivantes envoyaient
   quand même les leurs.
3. La règle que K-B s'impose pour tldr.tech, une page à la fois avec une pause, n'était pas tenue
   d'une édition à la suivante.

Ces corrections comptent pour l'annexe E1 sur la conformité des sources, et doivent être faites
avant la mise en public du dépôt.

## Le comment

### 1. Une mention de crédit, à un seul endroit du code

```python
ARXIV_ACKNOWLEDGEMENT = (
    "Thank you to arXiv for use of its open access interoperability."
)
```
(`src/k_b/data_api/app.py:23`). La constante est passée à `FastAPI(description=...)`
(`app.py:38`). La phrase apparaît ainsi dans `/docs` et dans `/openapi.json`, et donc dans
l'OpenAPI versionnée `docs/api/openapi-donnees.json`, régénérée par `kb openapi`. Le README la
reprend dans une section « Crédits ».

### 2. Lire la pause demandée : `find_pause_end`

```python
    if is_rate_limit_exhausted(error):
        # Without a readable reset, or a reset already past (a clock off): the minute GitHub asks.
        return max(read_rate_limit_reset(error) or 0, now + MIN_PAUSE_SECONDS)
```
(`src/k_b/etl/http_retry.py:72-74`). La fonction répond à une seule question : jusqu'à quand,
en secondes epoch, ne faut-il plus rien envoyer ?

- **Quota épuisé** (`x-ratelimit-remaining: 0`) : jusqu'à `x-ratelimit-reset`, l'heure de remise
  à zéro donnée par GitHub. `read_rate_limit_reset` (`:102`) vérifie d'abord, avec
  `EPOCH_SECONDS`, que l'en-tête ne contient que 1 à 10 chiffres. Sans heure lisible, ou avec une
  heure déjà passée (horloge décalée), la pause dure une minute, le minimum que GitHub demande.
- **`Retry-After` de plus de 60 s, sur un statut de limite** (429, 5xx, ou 403 avec
  `Retry-After`, `is_retried_status`, `:85`) : jusqu'à `now + Retry-After`. S'il est trop long
  pour être lu, la pause dure jusqu'à la fin du processus (`math.inf`, `:82`).
- **Tout autre cas** : `None`, pas de pause.

La fonction ne lit pas une réponse servie hors de l'adresse attendue : elle s'appuie sur
`is_served_from`, comme `note_rate_limit_reset`. Elle reste générique (préfixe et heure en
paramètres), à côté des autres règles de politesse du fichier.

Après la revue de code, les trois règles que `find_retry_wait`, `note_rate_limit_reset` et
`find_pause_end` répétaient sont extraites, chacune à un seul endroit (règle « une connaissance
vit à un seul endroit » de `.claude/rules/code.md`) : `is_retried_status` (quels statuts sont des
limites), `is_retry_after_beyond_max` (`:95`), `read_rate_limit_reset`. Le comportement du nouvel
essai et de la note est inchangé : leurs tests passent sans modification.

### 3. Tenir la pause : `paused_until`, partagé par les sources GitHub

```python
    global paused_until  # the pause of every GitHub source of the run
    if time() < paused_until:
        raise GithubPausedError(paused_until)
```
(`src/k_b/etl/sources/github/api.py:44-46`). Toutes les sources GitHub (releases, alertes, tops)
passent par `get_from_github_api`. Une variable de module `paused_until` (`:25`) leur est donc
commune, comme le jeton dont elles partagent le quota. Avant chaque requête, si la pause court,
la fonction lève `GithubPausedError` sans rien envoyer. Sur une `HTTPError`, elle met la pause à
jour, puis relève l'erreur (`:64-66`) : la source en échec reste journalisée comme avant.
`max(...)` empêche qu'une pause plus courte en remplace une plus longue.

Dans `etl/extract.py`, `GithubPausedError` est un échec de source ordinaire : il est journalisé,
la date de dernière collecte ne bouge pas, et la collecte suivante redemande.

### 4. tldr.tech : une pause avant chaque page

```python
        for day in days:
            # Before every page, the first too: ...
            sleep(TLDR_PAUSE_BETWEEN_PAGES_SECONDS)
```
(`src/k_b/etl/sources/tldr.py:108-111`). Avant, `if position > 0` sautait la pause pour la
première page. Or chaque édition (`ai`, `infosec`, `dev`) est une source distincte, collectée
juste après la précédente : la première page d'une édition partait aussitôt après la dernière de
l'autre.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où afficher le crédit arXiv | README et description de l'OpenAPI : c'est là que K-B montre ses données | Un pied de page dans chaque fiche de veille : plus de code, et arXiv ne le demande pas |
| Version de l'API de données | Inchangée (0.5.0) : la description ne touche ni une route ni un schéma | Monter la version : rien ne change dans le contrat avec un client |
| Portée de la pause GitHub | Toutes les requêtes GitHub : simple, et au pire les tops attendent la collecte suivante | Une pause par quota (core ou search, d'après l'en-tête `x-ratelimit-resource`) : plus de code pour un gain minime |
| Durée de la pause | Jusqu'à l'heure de remise à zéro, ce que dit la consigne de GitHub, sans état périmé même dans un processus long | « Jusqu'à la fin de la collecte » : moins fidèle à la consigne |
| Où garder l'état | Variable de module dans `api.py`, le seul point d'entrée vers GitHub | Un objet « quota » passé aux constructeurs des 4 sources (`source_kinds.py`) : plus de code pour le même effet |
| tldr.tech | Pause avant chaque page, un changement d'une ligne, qui coûte 6 s par collecte | Une horloge « dernière page lue » : plus de code pour gagner 6 s. Corriger la spécification à la place : affaiblirait une règle posée par Sabine |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_after_a_rate_limit_with_no_request_left_no_request_is_sent_until_its_reset` (`tests/etl/sources/test_github_api.py:102`) | Après un 403 avec quota épuisé, l'appel suivant lève `GithubPausedError` sans requête. Une fois l'heure de remise à zéro passée, il redemande. Ce test échoue si la ligne `paused_until = max(...)` est retirée (vérifié) |
| `test_a_rate_limit_with_no_request_left_pauses_until_its_reset`, `test_a_reset_missing_unreadable_or_past_pauses_a_minute`, `test_no_pause_otherwise` (`tests/etl/test_http_retry.py:164-214`) | Chaque cas de `find_pause_end`, dont la réponse servie ailleurs, un 404 avec `Retry-After` (pas une limite, donc sans pause) et le `Retry-After` de 60 s (attendu, donc sans pause) |
| `test_a_pause_comes_before_every_page_the_first_too` (`tests/etl/sources/test_tldr.py:605`) | 8 pages lues donnent 8 pauses. L'ancien code en aurait fait 7 |
| `test_the_versioned_openapi_is_valid_and_declares_its_security_scheme` | L'OpenAPI versionnée porte la mention arXiv |
| `uv run pytest` : 2 610 réussis ; `mypy`, `ruff check`, `ruff format --check` verts | Rien d'autre n'a cassé |

Deux fixtures autouse (`tests/etl/conftest.py`) : `no_github_pause` remet `paused_until` à 0
avant chaque test, pour qu'une pause ne déborde pas sur le test suivant ; `no_pause_before_a_tldr_page`
supprime la pause tldr, qui faisait attendre 2 s réelles à un test de `test_extract.py` (constat
de la revue).

## Ce que tu dois pouvoir défendre

1. **Pourquoi une variable globale, alors que le code n'en a pas ailleurs ?** La pause est un fait
   partagé par toutes les sources GitHub d'un même processus, comme leur quota. `api.py` est le
   seul passage vers GitHub, donc l'état y vit et nulle part ailleurs. Les tests la remettent à
   zéro (`tests/etl/conftest.py`).
2. **Et si l'horloge du Mac est décalée ?** Une heure de remise à zéro déjà passée donne quand
   même une minute de pause (`http_retry.py:74`). On n'enchaîne pas les requêtes refusées.
3. **Pourquoi ne pas simplement attendre la remise à zéro ?** Elle peut être dans une heure.
   Bloquer `kb collect` aussi longtemps priverait toutes les autres sources. La source échoue,
   et la collecte suivante redemande.
4. **Une réponse piégée pourrait-elle bloquer K-B ?** Seule une réponse servie depuis
   `https://api.github.com/` est lue (`is_served_from`). Au pire, une pause infinie ne touche que
   les sources GitHub de ce processus, et la commande suivante repart de zéro.
5. **Le crédit arXiv dans le README, est-ce suffisant ?** arXiv demande la mention « on your
   product ». Le README et l'OpenAPI sont les deux faces publiques de K-B aujourd'hui. Les fiches
   de veille n'en ont pas : ce choix est indiqué plus haut.

## Zones non vérifiées

- Les en-têtes d'un vrai quota GitHub épuisé n'ont pas été observés : les tests les fabriquent
  d'après la documentation de GitHub (« Rate limits for the REST API », consultée le 2026-10-25).
- Aucune collecte réelle n'a été lancée pour mesurer les 6 s ajoutées par tldr.tech.

## Ce qui reste

- La licence des extraits de tldr.tech dans `tests/fixtures/`, relevée en passant par la
  vérification : à décider avant la mise en public, hors de cette PR.
- Une pause par quota GitHub (core ou search), si les tops devaient un jour ne pas attendre.
- Une pause qui survit au processus (écrite à côté des dates de dernière collecte) : un
  `kb collect` relancé avant la remise à zéro renverrait au plus une requête refusée par source
  GitHub. Écarté à la revue : la collecte prévue est quotidienne (launchd,
  `docs/2026-10-07-clarification-modele.md:568`), bien au-delà d'une remise à zéro (une heure au plus).
- Un intervalle minimal par hôte dans `download()`, qui espacerait toutes les sources sans cas
  particulier : une refonte de la couche réseau, à proposer à part.

## Sources

| Source | URL | Consultée |
|---|---|---|
| arXiv API Access | https://info.arxiv.org/help/api/index.html | 2026-10-25 (vérification certif) |
| GitHub, Best practices for using the REST API | https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api | 2026-10-25 (vérification certif) |
| GitHub, Rate limits for the REST API | https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api | 2026-10-25 (vérification certif) |
