# Passer K-B à gpt-6.1-sol : seuils du monitorage, prix, durée d'une demande, effort en production

- Date : 2026-11-18
- Branche : `feat/gpt-6-1-sol-thresholds`
- Issues : #631 (prix), #632 (budget et alerte de coût), #633 (appels en échec), #634 (durée d'une demande),
  #635 (effort en production)
- Fichiers principaux : `src/k_b/ai_api/observability/metric_instruments.py`, `src/k_b/ai_api/routers/digest_router.py`,
  `src/k_b/ai_api/routers/trend_report_router.py`, `src/k_b/core/config.py`, `observability/grafana/alert-rules.yaml`,
  `observability/grafana/dashboard.json`, `infra/main.bicep`, `infra/modules/budget.bicep`
- Série : suit [2026-11-08, restituer les métriques du modèle et alerter](2026-11-08-restituer-les-metriques-du-modele-et-alerter.md)

## Le pourquoi

Le benchmark de C7 préconise gpt-6.1-sol, et l'essai du 17/11 l'a fait tourner depuis le poste. Mais K-B restait
réglé pour gpt-6-luna, sur trois points :
- la production posait l'effort de raisonnement `none`, que gpt-6.1-sol refuse ;
- le coût estimé était calculé aux prix de gpt-6-luna, environ 20 fois plus bas ;
- les seuils d'alerte dataient de gpt-6-luna.

L'essai du 17/11 a aussi montré un risque nouveau : `POST /digests` a atteint son échéance de 200 s. Avant cette PR,
aucune mesure ne voyait la durée d'une demande entière, seulement celle de chaque appel.

Cette PR applique les seuils que Sabine a décidés le 18/11. Elle ajoute la mesure et les deux alertes qui
manquaient, et règle la production pour gpt-6.1-sol.

## Le comment

### Une mesure nouvelle : la durée d'une demande de compte rendu

`src/k_b/ai_api/observability/metric_instruments.py:206-214` :

```python
@contextmanager
def measure_request(self, route: ReportRoute) -> Iterator[None]:
    """The duration of the block, recorded whatever its end, a failure included."""
    started = time.perf_counter()
    try:
        yield
    finally:
        self._request_duration.record(
            time.perf_counter() - started, {"http.route": route}
        )
```

C'est un gestionnaire de contexte : il enveloppe un bloc et enregistre sa durée à la sortie. Grâce au `finally`, une
demande qui échoue (502, 504) est mesurée aussi : une demande lente qui finit en erreur est justement celle qu'on
veut voir. `time.perf_counter` est une horloge monotone, que l'heure du système ne déplace pas.

`route` a pour type `ReportRoute = Literal["/digests", "/trend-reports"]` (`:43`). L'attribut ne peut prendre que
ces deux valeurs, fixées dans le code : jamais un texte, un sujet ni un identifiant de demande (règle 5 de
`.claude/rules/poc.md`).

### Où la mesure commence

`src/k_b/ai_api/routers/digest_router.py:94-99` :

```python
with (
    request.app.state.model_metrics.measure_request("/digests"),
    tracing.step(
        ROOT_SPAN, "server", ROOT_ATTRIBUTES | {"k_b.request_id": request_id}
    ) as root,
):
```

La mesure enveloppe le span racine de la route : tout ce que fait la demande, lecture et appels au modèle compris.
`trend_report_router.py:82` fait de même. Elle commence à l'entrée dans la route, comme l'échéance de 200 s, que
`answer_digests` pose juste après (`Deadline.after(DIGEST_REQUEST_TIMEOUT_SECONDS)`, `digest_router.py:170`). La
mesure et l'échéance partent donc presque du même instant, et 180 s mesurées veulent bien dire « 20 s avant
l'échéance ».

### Les paliers de l'histogramme

`metric_instruments.py:39-41` : `REQUEST_SECONDS_BUCKETS = (1, 2, 5, 10, 20, 30, 60, 90, 120, 150, 180, 200, 240)`.
Un histogramme OpenTelemetry ne garde pas chaque durée : il compte combien de demandes tombent sous chaque palier.
Le palier de 180 est là pour que l'alerte puisse compter les demandes au-dessus de 180 s. Les paliers par défaut
de `gen_ai.client.inference.duration` s'arrêtent à 81,92 s : ils ne conviennent pas.

### Les deux alertes nouvelles

`observability/grafana/alert-rules.yaml:68-73`, `KbRequestOverDuration` :

```yaml
(sum by (deployment_environment_name) (max_over_time(k_b_request_duration_seconds_count[24h]))
  - sum by (deployment_environment_name) (max_over_time(k_b_request_duration_seconds_bucket{le=~"180|180.0"}[24h])))
  / sum by (deployment_environment_name) (max_over_time(k_b_request_duration_seconds_count[24h]))
  > 0
```

`_count` est le nombre total de demandes, et `_bucket{le="180"}` le nombre de demandes de 180 s au plus. Leur
différence donne les demandes de plus de 180 s ; divisée par le total, c'est une part. Au-dessus de 0 %, l'alerte se
déclenche. Chaque total passe par `max_over_time`, comme dans les trois alertes existantes : chaque processus de
l'API IA est une série nouvelle, dont `increase()` ne voit pas le premier incrément (relevé du 2026-11-08).

`KbModelCallFailures` (`:57-61`) compte de la même façon la part des appels dont l'issue finale, après la nouvelle
tentative, est `llm_timeout`, `llm_unavailable`, `llm_rate_limited`, `llm_content_filtered` ou `llm_truncated`. La mesure existait
déjà : c'est `k_b.llm.calls`, avec son attribut `k_b.outcome`.

Chaque alerte a, dans le tableau de bord, un panneau d'état et une courbe avec son seuil en tirets
(`dashboard.json`, panneaux 17 à 20). `tests/test_grafana_files.py` vérifie que le seuil d'une règle et celui du
tableau sont égaux.

### Les seuils et les prix

- `src/k_b/core/config.py:302-303` : `2.40` et `12.00` USD par million de jetons, relus le 2026-11-18 dans l'API
  Azure Retail Prices (compteurs `6.1-sol ShortCo Inp Std DZ 1M Tokens` et `Opt`). Le commentaire au-dessus donne
  l'adresse, le filtre et la date.
- `observability/grafana/alert-rules.yaml:50` : le seuil de coût passe à `> 2` (USD sur 7 jours).
- `infra/modules/budget.bicep:11` : `amount: 40` (EUR par mois, pour tout K-B).
- `infra/main.bicep:304` : `KB_LLM_REASONING_EFFORT: 'low'`. Le nom du modèle reste le paramètre `llmModel` de la
  seconde passe.

## Choix faits et options écartées

- **« Compte rendu » = `POST /digests` et `POST /trend-reports`.** Ce sont le compte rendu de veille et celui des
  tendances, dans le vocabulaire de Sabine (interprétation de la session, acceptée par time-knight). Option écartée :
  `POST /digests` seul. C'est lui qui a atteint l'échéance, mais `POST /trend-reports` a la même échéance de 200 s.
- **L'attribut `http.route`**, comme sur les spans racines, plutôt que `k_b.route`, qui était prévu au plan : un
  seul nom pour la même chose dans les traces et les mesures (écart accepté par time-knight).
- **Mesurer depuis l'entrée dans la route, pas dans un middleware.** Ainsi la mesure part du même point que
  l'échéance. Écarté : un middleware, qui compterait aussi l'attente d'un fil du pool et la sérialisation, mais ne se
  comparerait plus à l'échéance (constat C5 de la revue, tranché par time-knight : garder le code, corriger le
  texte).
- **La part des demandes de plus de 180 s, plutôt que `histogram_quantile(1, …) > 180`.** Le quantile rend une
  borne de palier interpolée, pas une durée, et demande de grouper par `le`, ce que le test des règles
  (`test_each_rule_sums_by_environment`) refuse. La part se compare à 0 comme les autres alertes et réutilise leur
  format de seuil (« 0 % »).
- **`le=~"180|180.0"`** : Prometheus écrit `le` sous l'une ou l'autre forme, et celle que donne Grafana Cloud n'est
  pas encore relevée. Le constat C3 de la revue (palier compté deux fois) a été écarté : une série n'a qu'une
  forme.
- **Seuil des appels en échec : au-dessus de 0 % sur 24 h**, choisi par Sabine sur la recommandation de la session
  et de time-knight. L'alerte se déclenchera à chaque fiche tant que #630 n'est pas fait, et c'est un vrai signal.
- **`llm_truncated` compte parmi les échecs**, ajouté par Sabine sur le constat C1 de la revue de code : une sortie
  coupée au plafond de jetons n'a pas de nouvelle tentative (`llm_client.py:557`), le sujet manque, et aucune
  autre alerte ne la voyait. À l'effort `low`, le raisonnement compte dans ce plafond. Option écartée : les quatre
  causes de la mission seules.
- **Pas de test nouveau du prix.** `test_the_cost_is_the_tokens_at_the_prices_of_the_config` fige déjà le coût
  calculé (0.0048 USD pour 1 000 jetons d'entrée et 200 de sortie). Un test « le prix vaut 2.40 » répéterait la
  constante (écart accepté par time-knight).
- **Les noms nouveaux de séries ne sont pas ajoutés à `NAMES_SEEN_IN_GRAFANA`** : ce serait écrire qu'on les a vus
  dans Grafana le 2026-11-08. Ils vont dans `NAMES_NOT_SEEN_IN_GRAFANA_YET` (`tests/test_grafana_files.py:54`).
- **L'effort reste dans le Bicep, le modèle en paramètre** : c'est le partage fixé par la mission. Le constat C4 de
  la revue (rien ne lie les deux) a été écarté par time-knight : la parade est de donner à Sabine le modèle
  et l'effort dans la même commande de déploiement.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| 3 tests rouges avant le code (02:20Z) : `k_b.request.duration` absente | les tests voyaient bien le manque |
| `test_a_request_measures_its_duration_by_its_route` (`tests/ai_api/test_digest_router.py:1133`, `tests/ai_api/test_trend_report_router.py:1211`) | une demande donne un point, avec la seule route pour attribut |
| `test_a_request_that_fails_measures_its_duration_too` (`test_digest_router.py:1143`) | une demande en erreur est mesurée aussi (le `finally`) |
| `test_a_measure_carries_closed_attributes_never_a_text` | `/digests` est la seule valeur nouvelle parmi les attributs |
| `test_the_cost_is_the_tokens_at_the_prices_of_the_config` (`:879`, `0.0048`) | le coût est calculé aux prix de gpt-6.1-sol |
| `tests/test_grafana_files.py` (17 tests) | les règles et le tableau ne lisent que des mesures émises ; les seuils concordent ; les cinq alertes sont là |
| `uv run pytest` : 5621 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | rien d'autre n'est cassé |
| `curl` de l'API Azure Retail Prices, 2026-11-18 02:22Z, code 200 | 2,40 et 12,00 USD, en vigueur depuis le 2026-10-01 |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une alerte à 180 s et pas à 200 s ?** À 200 s, la demande est déjà coupée par son échéance, et des
   sujets manquent. 180 s prévient avant, tant qu'il reste 20 s (`DIGEST_REQUEST_TIMEOUT_SECONDS`,
   `core/config.py`).
2. **Pourquoi une demande en échec est-elle mesurée ?** Le `finally` de `measure_request` (`metric_instruments.py:211`)
   enregistre la durée quelle que soit la fin du bloc. Une demande qui finit en 504 après 200 s est celle que
   l'alerte doit voir.
3. **La mesure ne fuit-elle aucune donnée ?** Son seul attribut est un `Literal` de deux routes, fixé dans le code
   (`:43`, `digest_router.py:95`). Ni sujet, ni identifiant de demande, ni texte (règle 5 de `poc.md`). Le test des
   attributs fermés le vérifie.
4. **Que se passe-t-il si on déploie l'effort `low` avec gpt-6-luna ?** Ce n'est pas mesuré : luna a été validé à
   `none`. D'où la règle « jamais l'un sans l'autre », écrite dans `main.bicep:301-303` et `infra/README.md`, étape 5.
5. **Le budget de 40 € voit-il le modèle ?** Seulement quand `sabl-certif-resource` porte `project=k-b`. Le budget
   filtre sur cette étiquette, dans son groupe de ressources (`budget.bicep:18-26`). La ressource est dans ce
   groupe (lecture de Sabine, 02:35Z) ; l'étiquette est son geste après la fusion.

## Zones non vérifiées

- La forme de `le` que Grafana Cloud donne au palier de 180 (`180` ou `180.0`) : l'expression lit les deux, mais
  aucune série `k_b_request_duration_seconds_*` n'a encore été vue dans Grafana.
- Les deux alertes nouvelles n'ont été déclenchées ni dans le bac à sable ni en ligne. Seuls les tests des fichiers
  les vérifient.
- La limite entre contexte court et contexte long des prix : K-B est compté au tarif court (2,40), sans vérifier
  où Azure place la limite. Le tarif long est de 4,80 et 18,00.
- Le comportement de gpt-6-luna à l'effort `low` : jamais mesuré.
- Le maximum normal de 1,55 USD par semaine, qui fonde le seuil de 2 USD, vient de C7 et n'a pas été recalculé ici.

## Ce qui reste

- Les gestes de Sabine après la fusion : l'étiquette `project=k-b` sur `sabl-certif-resource`, la clé de la ressource
  dans le coffre, la seconde passe avec le modèle gpt-6.1-sol, et le réimport des règles et du tableau dans Grafana.
- #630 : la rédaction des sujets en parallèle et le délai de 90 s par appel, recalculé pour gpt-6.1-sol. Tant
  qu'il n'est pas fait, `KbModelCallFailures` et `KbRequestOverDuration` se déclencheront à chaque fiche de veille.
- Un scénario du bac à sable pour les deux alertes nouvelles (une demande de plus de 180 s est trop longue pour lui).
- Le passage des trois noms `k_b_request_duration_seconds_*` dans `NAMES_SEEN_IN_GRAFANA`, une fois vus dans Grafana.
