# L'API IA rend le compte rendu factuel des tendances : `POST /trend-reports`

- **Date** : 2026-10-30
- **Branche** : `feat/trend-report-ai-api` (commits 83b673c, 5da681f, 69730e3, a14967c)
- **Issue** : #366, PR 1 sur 2 (`Refs #366`) ; la PR 2 (`kb trend-report`) fermera l'issue
- **Fichiers principaux** : `src/k_b/ai_api/trajectories.py`, `src/k_b/ai_api/trend_reports.py`,
  `src/k_b/ai_api/routers/trend_report_router.py`, `src/k_b/ai_api/schemas/trend_report_schema.py`,
  `src/k_b/ai_api/connectors/data_api_client.py` (`read_trend_window`), `src/k_b/items.py`
  (`WrittenDay`)
- **Série** : suit [le contrat du compte rendu](2026-10-30-contrat-compte-rendu-tendances.md) (#364) ;
  le contrat lui-même est `docs/tendances.md`.

## Le pourquoi

GH Archive donne, par fenêtre de 3 jours, les dépôts qui ont gagné le plus d'étoiles et de forks
(table `trend`, lue par `GET /trends`). Une fenêtre seule ne dit rien d'une tendance : un pic d'un
jour y ressemble à un dépôt qui monte depuis une semaine. Le compte rendu des tendances répond à
« quels dépôts ressortent depuis le dernier compte rendu, et pourquoi », par trois critères calculés :
**durable** (dans le top à deux moments distincts), **nouveau** (absent du compte rendu précédent),
**en accélération** (un rang qui monte).

Cette PR pose la moitié serveur du flux : l'API IA reçoit les bornes du compte rendu précédent, lit
les fenêtres utiles par l'API de données, calcule en code pur et rend les dépôts qui remplissent au
moins un critère, avec leur trajectoire. Ni GitHub ni modèle : ils viennent en #367 à #369. La PR 2
écrira le client (`kb trend-report`), le registre des comptes rendus et le fichier du coffre.

L'API IA reste **sans état** (règle 7 de `.claude/rules/poc.md`) : elle ne sait pas quel compte rendu
a été écrit avant ; c'est `kb` qui le lui dit dans la demande.

## Le comment

### 1. La période : quelles fenêtres lire, et une seule fois chacune

La période part de `after`, la dernière fenêtre du compte rendu précédent, et va jusqu'à la plus
récente en base :

```python
    if after is None:
        return [
            *list_days_before(latest, TREND_FIRST_REPORT_WINDOWS - 1),
            latest,
        ], False
    # Compared before any addition: the day after `after` may not exist.
    if after >= latest:
        return [], False
```
(`src/k_b/ai_api/trend_reports.py:129-136`)

Au premier compte rendu (`after` nul), les 4 dernières fenêtres. Sinon, les fenêtres après `after`,
15 au plus (`GH_ARCHIVE_MAX_CATCH_UP_WINDOWS`) : au-delà, les plus récentes, et `windows_capped` le
dit. La comparaison `after >= latest` vient **avant** `after + timedelta(days=1)` : un `after` au
31/12/9999 ferait déborder la date et tomber la requête en 500. Si `after` est postérieur à la plus
récente (base restaurée), la période est vide et `latest_window` le montre.

Trois ensembles de jours sont lus : la période, les 2 fenêtres qui la précèdent (pour « durable »),
et les fenêtres du compte rendu précédent (pour « nouveau »). Ils se recouvrent : l'union, moins la
plus récente déjà lue, est lue en série.

```python
    to_read = sorted({*period, *lookback, *(previous or ())} - {latest.window_end})
```
(`src/k_b/ai_api/trend_reports.py:109`)

D'où « 1 + 31 lectures au plus » : la plus récente, puis 15 + 2 + 15 jours moins les doublons.
Aucune fenêtre nouvelle : une seule lecture, et rien d'autre.

### 2. Le rang par étoiles, recalculé

`GET /trends` rend les lignes de la fenêtre départagées par les forks. Or le rang de la collecte
(`star_rank`, `etl/sources/gh_archive.py`) départage par `repository_id`. Le code le recalcule :

```python
    ranked = sorted(
        (row for row in window.rows if row.stars_gained > 0),
        key=lambda row: (-row.stars_gained, row.repository_id),
    )
```
(`src/k_b/ai_api/trajectories.py:61-64`)

Une fenêtre contient le top 30 par étoiles **et** le top 30 par forks. Un dépôt entré par ses forks,
à égalité d'étoiles avec le 30e mais de `repository_id` plus grand, reste dehors : c'est le test
`test_a_tie_at_the_last_rank_broken_by_the_forks_does_not_enter`. Un dépôt sans étoile gagnée n'est
dans aucun top : sur de vraies fenêtres, le 30e a des dizaines d'étoiles, mais la base de test a deux
dépôts à 0 étoile qui seraient sinon « 4e » et « 5e ».

Chaque fenêtre de la période donne un point de trajectoire : `top` (rang et étoiles), `out_of_top`
(la ligne est là, entrée par les forks, ou le dépôt n'est plus dans les 30), `missing` (la base n'a
pas la fenêtre).

### 3. Les trois critères

**Durable** : deux fenêtres de 3 jours finissant à D et D+2 partagent le jour D ; D et D+3, non. Le
code choisit les fenêtres du top **au plus tôt**, ce qui en garde le plus :

```python
    for end in sorted(top_ends):
        if not picked or (end - picked[-1]).days >= GH_ARCHIVE_WINDOW_DAYS:
            picked.append(end)
    return len(picked) >= TREND_DURABLE_MIN_WINDOWS
```
(`src/k_b/ai_api/trajectories.py:165-168`)

Un pic d'un seul jour apparaît dans les 3 fenêtres qui le contiennent (D, D+1, D+2) : elles se
recouvrent toutes, donc pas « durable ». Les fenêtres lues sont la période et les 2 qui la
précèdent ; deux fenêtres de recul adjacentes ne peuvent pas être choisies toutes les deux, donc
« au moins une dans la période » est tenu par construction.

**Nouveau** : dans le top d'une fenêtre de la période, et dans le top d'aucune fenêtre lue du
compte rendu précédent. Non évalué au premier compte rendu, ni si toutes les fenêtres précédentes
manquent (`new_evaluated` faux).

**En accélération**, selon la décision A de Sabine (30/10) : on lit la **dernière suite** de
fenêtres où le dépôt est dans le top.

```python
    for point in points:
        if point.state == "out_of_top":
            run = []
        elif point.rank is not None:
            run.append(point.rank)
```
(`src/k_b/ai_api/trajectories.py:177-181`)

Une fenêtre hors du top vide la suite, une fenêtre manquante (`rank` nul, état `missing`) est sautée.
Ensuite : au moins deux rangs, chacun meilleur que le précédent, et 5 rangs gagnés au moins
(`TREND_ACCELERATION_MIN_RANKS`). « hors top → 28 → 20 → 9 » accélère ; « 12 → 7 → hors top → 25 →
22 » non (3 rangs gagnés sur la dernière suite) ; un dépôt sorti du top à la dernière fenêtre non
plus (sa suite repart, vide).

### 4. Les deux frontières : la demande et l'API de données

**La demande.** Un jour s'écrit `AAAA-MM-JJ` et rien d'autre. La garde existait pour `GET /trends`
(`data_api/routers/trend_router.py`) ; elle passe dans `items.py`, vocabulaire commun aux deux API
(règle 4 de `conventions.md`), sans changer de comportement (l'OpenAPI de l'API de données est
identique) :

```python
# Not strict: under FastAPI, strict refuses a date given as text.
RequestDay = Annotated[WrittenDay | None, Field(strict=False)]
```
(`src/k_b/ai_api/schemas/trend_report_schema.py:12-13`)

Le modèle est strict (`ConfigDict(extra="forbid", strict=True)`), mais FastAPI lit le corps en
objets Python (`json.loads`) puis le valide par `validate_python` : en mode strict, pydantic n'y
accepte qu'une instance de `date`, jamais un texte. Le champ repasse donc en mode souple, et la garde
`check_day_form` (`src/k_b/items.py:92`), qui tourne **avant** pydantic, refuse tout ce qui n'est pas
un texte `AAAA-MM-JJ` : sans elle, le mode souple accepterait un horodatage Unix ou
`2026-10-30T00:00:00Z`.

Les contrôles croisés vivent dans un `model_validator` (`trend_report_schema.py:28-43`) : un seul des
deux nul, ordre inversé, plus de 15 fenêtres. Leur erreur n'est rattachée à aucun champ : la 422 rend
`{"error": "invalid_parameter", "parameters": ["body"]}`, jamais la valeur reçue.

**L'API de données.** Sa réponse est relue par un schéma fermé (`TrendBody` : `repository_id` > 0,
nom au motif `owner/repo`, 255 caractères au plus, étoiles ≥ 0, en strict), puis :

```python
    repository_ids = {trend.repository_id for trend in body.trends}
    if (window_end is not None and body.window_end != window_end) or len(
        repository_ids
    ) != len(body.trends):
        raise DataApiError("data_api_invalid_response", response.status_code)
```
(`src/k_b/ai_api/connectors/data_api_client.py:308-312`)

Une fenêtre autre que celle demandée, ou un dépôt en double, et la demande échoue fermée. Un 404
`trend_window_not_found` est une fenêtre manquante ; un autre 404 (une route inconnue) est une erreur.

### 5. Les noms qui iraient dans un chemin

Le motif `owner/repo` laisse passer `owner/..`. Le nom servira en PR 2 à construire une URL et des
textes du coffre. Le dépôt garde son rang (le rang est celui de la collecte, avec tous les dépôts),
mais il est retiré de la réponse et compté :

```python
    repositories = tuple(
        trajectory
        for trajectory in meeting_a_criterion
        if is_repository_name(trajectory.repository_name)
    )
```
(`src/k_b/ai_api/trend_reports.py:163-167`)

`repositories_dropped` dit combien ; `kb` n'aura donc jamais à refuser toute une réponse pour un nom.

### 6. Traces et erreurs

La route ouvre un span racine `POST /trend-reports` (comme `POST /digests`), puis
`build_trend_report` un span `read_trend_windows` qui ne porte **que des comptes** : fenêtres de la
période, lues, manquantes, plafond, dépôts rendus et écartés. Jamais un nom de dépôt ni un
`repository_id` (registre des traitements : un nom de dépôt contient un login). La réponse est
construite **dans** le `try` :

```python
            response = to_trend_report_schema(request_id, report)
        except ApiError as error:
```
(`src/k_b/ai_api/routers/trend_report_router.py:61-62`)

sans quoi un échec à cette étape était tracé en 200 pendant que le client recevait une 500 (revue de
la PR). Limite qui reste, la même que pour `/digests` et écrite dans le commentaire de la route :
FastAPI valide et sérialise la réponse **après** le `return`, hors du span.

Les erreurs déclarées dans l'OpenAPI sont celles de l'API de données seulement (502, 504), sans les
états `llm_*` : une fonction les construit pour chaque route depuis ses états
(`describe_error_responses`, `src/k_b/ai_api/errors.py`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Deux PR pour #366 (API IA, puis `kb`) | #366 est taillée L : relecture tenable, chaque PR verte seule (plan validé par Sabine le 30/10) | une seule PR : deux couches (API et `kb`) à relire d'un coup |
| Rang recalculé par `(étoiles desc, repository_id asc)` | c'est la définition de `star_rank` à la collecte (contrat) | l'ordre de `GET /trends` : départagé par les forks, qui n'entrent pas dans le rang des étoiles |
| Un dépôt à 0 étoile n'est dans aucun top | il n'est entré que par ses forks ; sinon la base de test donne des « 4e » à 0 étoile | le garder classé : sans effet sur de vraies fenêtres, absurde sur de petites |
| « Durable » par un choix glouton au plus tôt | il maximise le nombre de fenêtres sans jour commun, et tient pour tout `TREND_DURABLE_MIN_WINDOWS` | tester toutes les paires : même résultat à 2 fenêtres, rien à 3 |
| Accélération sur la dernière suite (décision A de Sabine, 30/10) | un dépôt qui entre dans le top puis monte est le cas cherché | « aucune fenêtre hors top sur la période » (le plan d'avant) : écartait ce cas |
| Sorti du top à la dernière fenêtre = pas en accélération | lecture de la décision A : la suite repart, vide ; dite à Sabine | prendre la dernière suite non vide : annoncerait en accélération un dépôt qui vient de sortir |
| Les deux champs de la demande obligatoires | le protocole porte toujours les deux bornes ; « refuser ce qui n'est pas prévu » (`code.md`) | `{}` vaut premier compte rendu : un oubli du client effacerait l'historique |
| `owner/..` gardé au rang, retiré de la réponse et compté | le rang reste celui de la collecte ; `kb` ne bloque pas tout le compte rendu | le retirer avant le rang : décalerait les rangs des autres ; le laisser passer : `kb` refuserait la réponse entière |
| Une lecture par jour, en série, sous 60 s | le contrat le prévoit ; l'API de données ne change pas | une plage de dates dans `GET /trends` (revue) : à reposer en #370 avec la mesure de durée sur ACA |
| `select_candidates` (60 au plus) écrit et testé dès cette PR | décision de Sabine (30/10) : il avance #367, qui le consomme | le retirer (revue : code sans appelant, `code.md`) : Sabine l'a gardé |
| Gestion du span racine copiée, pas factorisée | deuxième occurrence ; factoriser toucherait `digest_router.py`, hors périmètre (`code.md` : à la troisième) | un gestionnaire commun aux deux routes (revue) |
| Renvois `fichier:ligne` du contrat laissés tels quels | ils sont justes au commit qu'il cite (`8898095`) | les « corriger » à `ed0a512` (relecture du plan) : faux au commit cité |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_tie_at_the_last_rank_broken_by_the_forks_does_not_enter` | l'égalité au 30e rang ne fait pas entrer le dépôt de plus grand `repository_id` |
| `test_durable_needs_two_windows_in_the_top_without_a_day_in_common` (5 cas) | faux pour une fenêtre, un pic d'un jour, D et D+2 ; vrai pour D et D+3 |
| `test_accelerating_reads_the_last_run_of_windows_in_the_top` (9 cas) | 4 contre 5 rangs, fenêtre manquante sautée, entrée puis montée, sortie puis retour, sortie à la fin |
| `test_the_first_report_reads_the_last_four_windows_without_new` | 4 fenêtres, « nouveau » non évalué, chaque jour lu une fois, dans l'ordre |
| `test_no_window_after_the_previous_report_reads_nothing_more` | `after` = ou > la plus récente : une seule lecture, période vide |
| `test_beyond_the_cap_…` et `test_up_to_the_cap_…` | 16 fenêtres → 15 et `windows_capped` ; 15 → aucune laissée |
| `test_without_any_window_of_the_previous_report_new_is_not_evaluated` | `new_evaluated` faux si toutes les fenêtres précédentes manquent |
| `test_a_malformed_request_is_refused_422_…` et `test_a_day_not_written_yyyy_mm_dd_…` | un seul nul, ordre inversé, 16 fenêtres, champ en trop, `T00:00:00Z`, horodatage, `True` : 422 sans lecture |
| `test_a_trend_window_out_of_its_schema_gives_data_api_invalid_response` (9 cas) | autre jour, doublon, étoiles négatives ou en texte, nom sans propriétaire ou trop long |
| `test_a_repository_whose_name_would_go_up_a_path_is_dropped_and_counted` | `owner/..` absent de la réponse, `repositories_dropped` = 1 |
| `test_neither_the_traces_nor_the_logs_hold_a_repository` | aucun nom ni `repository_id` dans les spans, les enregistrements ni le journal |
| `test_a_response_that_fails_to_be_built_is_traced_as_a_500` | span racine en 500 et en erreur, corps `internal_error`, texte de l'exception absent |
| `test_only_the_public_routes_answer_without_a_key` | la route neuve répond 401 sans clé |
| 14 mutations (seuils, `<` en `<=`, filtre des noms, plafond…) | toutes tuées par les tests |
| `uv run pytest` : 2 863 verts ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | les contrôles du dépôt |
| `uv run kb openapi` | `/digests` et l'OpenAPI de l'API de données inchangés ; API IA en 0.5.0 |

Revues : `/code-review medium` (9 constats ; 3, 6, 8 corrigés, 5 gardé, les autres écartés), seconde
revue sur les corrections (5 constats ; 2, 4, 5 corrigés, 1 et 3 écartés), `/security-review` en
sous-agent : rien de confiance 8 ou plus. Le tri et ses raisons sont dans la PR.

## Ce que tu dois pouvoir défendre

1. **Pourquoi recalculer le rang au lieu de prendre l'ordre de `GET /trends` ?** L'API de données
   départage les égalités par les forks ; le rang des étoiles de la collecte les départage par
   `repository_id`. Prendre l'ordre reçu ferait entrer au 30e rang un dépôt qui n'y est pas
   (`trajectories.py:61-64`).
2. **Pourquoi l'API IA ne lit-elle pas elle-même le compte rendu précédent ?** Elle doit pouvoir être
   redémarrée sur ACA sans rien perdre (règle 7 de `poc.md`) : `kb` lit son registre et envoie
   `after` et `previous_first_window` (`trend_report_schema.py`).
3. **Que se passe-t-il si la base a été restaurée et que `after` est dans le futur ?** Période vide,
   une seule lecture, `latest_window` rendu ; la comparaison passe avant toute addition de date
   (`trend_reports.py:135`).
4. **Où est la sécurité ?** Clé sur toute l'app ; schéma fermé à l'entrée (jours `AAAA-MM-JJ`, champs
   en trop refusés) et à la lecture de l'API de données (fenêtre demandée, identifiants uniques) ;
   noms `.`/`..` écartés ; ni nom ni identifiant de dépôt dans les traces et les journaux ; une 422 ne
   cite que des noms de champ.
5. **Pourquoi `Field(strict=False)` dans un modèle strict ?** FastAPI valide le corps en mode Python,
   où le strict refuse un texte pour une `date` ; la garde `check_day_form` rend le mode souple aussi
   exigeant que voulu (`trend_report_schema.py:12-13`, `items.py:92`).

## Zones non vérifiées

- **Sur de vraies fenêtres** : seules la base de test (2 fenêtres) et des fenêtres simulées ont servi.
  Le seuil « 5 rangs » est dans le bruit entre les rangs 10 et 30 (mesure du 30/10, plan de #366) :
  à revoir à l'essai réel (#370).
- **Durée sur ACA** : 32 lectures en série sous 60 s, non mesurées ailleurs que sur le Mac en test.
- **Date lue de l'API de données** : la doc de pydantic annonce, en JSON, un texte RFC 3339 ou un
  horodatage Unix pour une `date`. Essayé le 30/10 sur `TREND_WINDOW` : `1760054400` et
  `"2026-10-09T00:00:00Z"` sont refusés. Seul « 9 octobre » est dans les tests ; les deux autres non.
- **Une date extrême** venue de l'API de données (`0001-01-02`) fait déborder le calcul de la période :
  500 `internal_error` au lieu d'un état nommé (constat de revue écarté : données internes corrompues).
- **Span racine après le `return`** : un échec de sérialisation par FastAPI reste tracé en 200, comme
  pour `/digests`.
- **httpx2** : non vérifié par Context7 ; le code neuf n'utilise que ce que `read_watch` utilisait déjà.

## Ce qui reste

- **PR 2 de #366** (`Closes #366`) : `kb trend-report`, le registre `trend_reports.json`, le rendu
  Markdown dans `veille/tendances/<jour>.md`, la clé `KB_TREND_REPORT`, SIGTERM et codes de sortie,
  README.
- **#367** : la fiche GitHub de chaque candidat ; premier appelant de `select_candidates`.
- **#368, #369** : le choix et la rédaction par le modèle ; `model` cessera d'être nul.
- **#370** : l'essai réel, les seuils (en étoiles ou par tranches de rangs), la durée sur ACA, la
  piste d'une plage de dates dans `GET /trends`.
- À la troisième route de l'API IA : factoriser la gestion du span racine.

## Sources

Vérification par Context7 le 2026-10-30, demandée par Sabine :

- pydantic v2.13.4 (installée : 2.13.5), `docs/concepts/strict_mode.md` : en strict, une `date`
  n'accepte qu'une instance en mode Python, un texte en JSON ; `Field(strict=False)` lève le strict du
  modèle pour un champ, aussi dans un `Annotated`.
- pydantic v2.13.4, `docs/api/standard_library_types.md` (« Dates », « Strictness ») : en JSON, texte
  RFC 3339 (date seule) ou horodatage Unix ; en strict, l'essai du 30/10 refuse l'horodatage.
- pydantic v2.13.4, `docs/examples/custom_validators.md` : une erreur d'un `model_validator(mode="after")`
  n'est rattachée à aucun champ.
- FastAPI, référence `Request.json` (fastapi.tiangolo.com/reference/request/) : le corps est lu par
  `json.loads` ; référence `response_model` (fastapi.tiangolo.com/reference/fastapi/) : la réponse est
  validée et sérialisée après la fonction, une réponse invalide donne une 500.
- Code installé, FastAPI 0.143.1 : `fastapi/_compat/v2.py:182`, validation par `validate_python`.
