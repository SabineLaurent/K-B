# Restituer les métriques du modèle et alerter sur seuil

- **Date** : 2026-11-08
- **Branche** : `feat/model-dashboard-and-alerts`, commits `268f69f` à `e37bd1f`, sur `b412323`
- **Issue** : #164 (PR « Part of #164 » : l'essai d'accessibilité la fermera, choix 31 de Sabine)
- **Fichiers principaux** : `observability/grafana/dashboard.json`, `observability/grafana/alert-rules.yaml`,
  `tests/test_grafana_files.py`, `tests/e2e/test_sandbox_alerts.py`, `documentation/monitoring_pour_docu.md`
- **Série** : suite de [Émettre les métriques en OpenTelemetry](2026-10-24-emettre-les-metriques-en-opentelemetry.md)
  (#162), qui envoie les mesures ; cette note les lit et alerte dessus.

## Le pourquoi

Depuis #162, chaque appel au modèle part en mesures OpenTelemetry vers Grafana Cloud, mais personne ne les regarde :
une fiche peut dériver (sorties refusées, faits inventés, coût qui monte) sans que tu le saches. #164 rend ces mesures
lisibles d'un coup d'œil, et prévient par e-mail quand l'une passe un seuil, sans relancer de calcul à la main. Et
parce qu'une alerte qui n'a jamais sonné ne prouve rien, un bac à sable la fait sonner exprès. Pour C11 : la
restitution, l'alerte sur seuil, et un test qui la déclenche.

Rien ne change dans `src/` : ce travail est fait de deux fichiers que Grafana importe, de tests et de documentation.

## Le comment

### 1. De l'API à Grafana : OTLP, Mimir, PromQL

L'API IA émet en OpenTelemetry (OTLP) ; Grafana Cloud range les mesures dans Mimir, sa base de séries temporelles
compatible Prometheus, sous des noms à la Prometheus ; on les interroge en PromQL. `k_b.llm.calls` (un compteur, unité
`{call}`) devient `k_b_llm_calls_total` : les points deviennent des `_`, l'unité entre accolades tombe, un compteur
prend `_total`. Le test refait cette conversion à partir des instruments que `ModelMetrics` crée vraiment :

```python
    base = name.replace(".", "_")
    if not (unit.startswith("{") and unit.endswith("}")):
        assert unit in UNIT_WORDS, f"{name}: unit {unit!r} has no word in UNIT_WORDS"
        word = UNIT_WORDS[unit]
```
`tests/test_grafana_files.py:124-127`

Puis il compare le résultat aux 20 noms que tu as relevés dans Explore (`NAMES_SEEN_IN_GRAFANA`, `:28`). Ainsi, chaque
nom du tableau et des règles existe, et un instrument renommé dans `src/` fait échouer le test au lieu de laisser un
panneau vide.

### 2. Compter par `max_over_time`, pas par `increase`

L'API IA tombe à zéro réplique : chaque réveil est un processus neuf, donc une série neuve, qui n'existe qu'après son
premier appel. `increase()` mesure l'écart entre deux points : il ne voit pas le premier incrément d'une série qui
commence déjà à 4. Mesuré dans le bac à sable : `increase` comptait 12 appels, `max_over_time` 21, le compte exact.
Comme un compteur repart de 0 à chaque processus, son maximum sur la fenêtre est le total de ce processus ; on somme
ces maximums :

```yaml
          sum by (deployment_environment_name) (max_over_time(k_b_llm_calls_total{k_b_outcome="llm_invalid_output"}[24h]))
            / sum by (deployment_environment_name) (max_over_time(k_b_llm_calls_total[24h]))
            > 0
```
`observability/grafana/alert-rules.yaml:22-24`

`sum by (deployment_environment_name)` fait une alerte par environnement : `sandbox` et `production` ne se mélangent
pas. Le test `test_each_measure_is_read_through_max_over_time` (`tests/test_grafana_files.py:220`) refuse toute autre
lecture.

### 3. Les seuils, à un seul endroit qui fait foi

Les seuils viennent de ta grille du 15/10 (« 100 % de schémas valides après une nouvelle tentative, au moins 95 % de
fidélité ») et de ton budget du 08/11 (1 USD sur 7 jours). Le seuil d'une alerte est le nombre qui termine son
expression (`> 0`, `< 0.95`, `> 1`). Le tableau le répète trois fois : dans l'état (`… > bool 0`), dans la ligne de
seuil (`vector(0)`) et dans les textes (« Seuil: 0 % »). Trois tests relient chaque copie à la règle, par une
comparaison exacte, et non par la recherche d'un bout de texte : la revue a montré qu'un `or vector(0)` passait pour
une ligne de seuil.

### 4. Le bac à sable : un test lancé à la main

`make sandbox-alerts` lance quatre tests `e2e` : des demandes valides, une sortie invalide, une fidélité basse, un coût
au-dessus du budget. Chacun sert les deux API en mémoire sur la base de test, avec le rejeu du modèle, et envoie ses
mesures pour de vrai à Grafana Cloud. L'environnement y est forcé à `sandbox`, quel que soit le terminal :

```python
    settings = read_metrics_export_settings_or_refusal(
        {**os.environ, DEPLOYMENT_ENVIRONMENT_VARIABLE: SANDBOX}
    )
```
`tests/e2e/test_sandbox_alerts.py:96-98`

Les items de la base de test datent de septembre et d'octobre, hors de la fenêtre de 14 jours. L'heure de la demande
est donc fixée dans le seul harnais de test (`app.dependency_overrides[read_request_time] = lambda: REQUEST_TIME`,
`:158`), comme le font déjà les tests des API. Chaque test échoue si un envoi échoue (`assert len(results) >=
request_count`, `:174`) : un 401 de Grafana l'a prouvé, avant le jeton neuf.

### 5. Un tableau qui ne parle pas par la couleur

Une règle de champ de Grafana vise les champs d'une requête par `byFrameRefID` :

```json
            "matcher": {
              "id": "byFrameRefID",
              "options": "B"
            },
```
`observability/grafana/dashboard.json:162-165`

C'est elle qui donne à la requête B, l'état, ses textes « NORMAL » et « ALERTE: seuil dépassé ». Mon premier fichier
écrivait `frameRefID`, un nom qui n'existe pas : Grafana ignorait la règle sans rien dire, et tu as vu « 100,0 % » à
la place de l'état. Le test compare désormais chaque nom à la liste de Grafana (`FIELD_MATCHER_IDS`, `:76`, relevée
dans le code de Grafana v13.3.0). Aucune valeur n'est colorée (`colorMode: none`) ; un seuil est une ligne de tirets,
nommée dans la légende (`test_no_panel_tells_by_colour_alone`, `:243`).

### 6. Une fidélité jamais mesurée n'est pas une fidélité saine

Sans fait vérifié, la fidélité vaudrait 0/0, NaN ; or toute comparaison avec NaN est fausse en PromQL, et l'état
aurait affiché « NORMAL ». On ne divise donc que s'il y a un fait :

```yaml
            / (sum by (deployment_environment_name) (max_over_time(k_b_digest_facts_checked_total[24h])) > 0)
```
`observability/grafana/alert-rules.yaml:34`

`(… > 0)` retire le cas zéro : il n'y a plus de donnée, le tableau affiche « Aucun appel sur la période », et
l'alerte reste au repos (`test_a_fidelity_without_a_checked_fact_gives_no_data`, `tests/test_grafana_files.py:373`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Installer tableau et règles | par l'interface, sans jeton : aucun secret, aucun outil (C, validé par Sabine) | API de provisioning avec un jeton : marquée « deprecated », secret, `/security-review` ; Terraform : un outil et un fichier d'état ; `gcx` : un outil ; Git Sync : tableaux seulement |
| Format des règles | règles Prometheus, importées par « Import to Grafana-managed rules » | format de provisioning de Grafana : sans import par l'interface trouvé |
| Bac à sable | un test `e2e` lancé à la main, sur `.env.e2e_test` (B bis, validé par Sabine) | une base aux dates décalées : 3 terminaux et un redémarrage par scénario ; un réglage de l'heure dans l'API IA : un levier de test dans le code de production |
| Décompte | `max_over_time` par série (mesuré : 21 sur 21) | `increase` : 12 sur 21 |
| Seuils | grille du 15/10 et budget du 08/11 | 20 % et 90 %, ma première proposition, qui contredisait la grille |
| État en cas d'erreur de requête | « Error », réglé à la main après import : une alerte `DatasourceError` (tri de time-knight) | « OK », laissé par l'import : une requête en échec ne prévient pas |
| Ponctuation des textes | sans espace avant « : » et « ; » (choix 30 de Sabine) | l'espace de `docs/` |
| Rafraîchissement | toutes les minutes, comme l'export de l'API | aucun : pas de « temps réel » visible (C11.3) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_names_k_b_gives_its_measures_are_those_grafana_cloud_showed` | la conversion des noms est celle de Grafana Cloud (20 sur 20) |
| `make sandbox-alerts` de Sabine : `4 passed in 133.35s` | chaque scénario a envoyé ses mesures à Grafana Cloud |
| Explore : `increase` 12, `max_over_time` 21 | le choix de `max_over_time` |
| Tableau en `sandbox` : 4,8 % (1/21), 73,3 % (11/15), 1,2641 USD, états « ALERTE: seuil dépassé » | les requêtes et les états, sur données réelles |
| Les 3 règles en Firing à 19:15:20 UTC, 3 e-mails à 19:27 UTC | une alerte déclenchée, reçue (C11.5) |
| Rouge avant le code : sélection e2e (11 au lieu de 15), fichiers absents (9 échecs), `byFrameRefID` (4 échecs), ponctuation (19 textes), fidélité non gardée | chaque test voit ce qu'il garde |
| 11 mutations attrapées : `increase`, nom faux, couleur de fond, seuil changé d'un côté, règle sans environnement, ligne de seuil retirée, `> bool 10`, légende seule, description seule, résumé seul, garde de la fidélité retirée | les tests ne passent pas par hasard |
| `uv run pytest` : 4078 passed ; `mypy --strict`, `ruff check --no-cache` verts | rien d'autre n'a cassé |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi pas `rate()` ou `increase()`, comme tout le monde ? »** Parce que l'API tombe à zéro réplique : chaque
   réveil est une série neuve, dont `increase` ne voit pas le premier incrément. Mesuré : 12 appels sur 21. Avec un
   seuil à 0, l'alerte des sorties invalides serait restée muette (`alert-rules.yaml:22`).
2. **« Ton alerte a-t-elle déjà sonné ? »** Oui, exprès, dans le bac à sable : 19:15:20 UTC, e-mails à 19:27 UTC, valeurs
   au tableau (`documentation/monitoring_pour_docu.md`, « Relevé »).
3. **« Que se passe-t-il si Grafana Cloud ne répond pas ? »** L'API IA continue : l'export échoue et se journalise
   (`Failed to export … 401` vu ce soir). Côté alertes, une requête en échec déclenche `DatasourceError`, depuis le
   réglage « Error » fait à la main.
4. **« Où est la sécurité ? »** Aucun secret dans le dépôt : l'import se fait par l'interface, le jeton OTLP reste dans
   `.env.e2e_test` ou dans le coffre, jamais affiché (`read_sandbox_export_settings`, `tests/e2e/test_sandbox_alerts.py:93`).
   Le nom de la pile n'est écrit nulle part, ton adresse e-mail non plus.
5. **« Un daltonien lit-il ton tableau ? »** Rien n'y passe par la couleur seule : l'état est écrit, le seuil est une
   ligne en tirets nommée. Un test le tient. L'essai au lecteur d'écran et au zoom reste à faire.

## Zones non vérifiées

- **L'essai d'accessibilité** n'est pas fait (choix 31) : `docs/accessibilité_pour_docu.md` attend ses 13 résultats.
- **La version corrigée n'est pas dans Grafana** : la garde de la fidélité et les tests du tri sont dans le dépôt, mais
  la pile garde l'import du 08/11 au soir. Réimport et étape « Error » à refaire avant l'essai.
- **Le scénario de coût à 9 166 667 jetons** n'a pas tourné contre Grafana : celui du relevé envoyait 10 millions de
  jetons (1,20084 USD).
- **La production n'envoie rien** : son jeton OTLP est très probablement mort avec le passage à l'offre Free, et aucune
  fiche n'a tourné en ligne.
- **Le coût des requêtes** d'un tableau rafraîchi toutes les minutes n'est pas mesuré (constat 4 de la revue, écarté).
- **Les e-mails reçus** portent les textes d'avant le choix 30 et la valeur brute ; les nouveaux textes (`humanize`)
  n'ont pas encore été envoyés.

## Ce qui reste

- **L'essai d'accessibilité**, puis la petite PR qui ferme #164.
- **Le jeton OTLP de la production**, à refaire dans le coffre (`infra/README.md`, « Pour refaire un seul secret »).
- **#282** : les alertes de collecte, de source muette et de 5xx, qui réutilisent ce bac à sable.
- **#495** : `tests/e2e/test_real_export.py`, cassé deux fois sur `main`.
- **Une piste** : servir de ce tableau pour comparer des modèles (C7), avec un sélecteur de modèle ; à trancher par toi.
