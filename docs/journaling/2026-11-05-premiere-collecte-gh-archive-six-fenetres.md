# Une première collecte de GH Archive à six fenêtres

- **Date** : 2026-11-05
- **Branche** : `feat/gh-archive-first-collection-windows`
- **Issue** : aucune ; demande de Sabine du 05/11, après le premier essai réel de `kb trend-report`
- **Fichiers principaux** : `src/k_b/etl/sources/gh_archive.py`, `src/k_b/core/config.py`

## Le pourquoi

Une première collecte ne prenait qu'une fenêtre, celle qui finit hier. Le premier compte rendu des
tendances lit 4 fenêtres, et « durable » en lit 2 de plus avant elles. Le 05/11, le premier essai a
donc écrit un compte rendu à 3 fenêtres manquantes sur 4, sans aucun dépôt à critère ; il a fallu
reculer la date de collecte à la main pour rattraper. Désormais, une installation neuve donne un
compte rendu utile dès le premier `make collect`, `make import`, `make trend-report`.

## Le comment

### 1. Le nombre vient du compte rendu

```python
GH_ARCHIVE_FIRST_COLLECTION_WINDOWS = (
    TREND_FIRST_REPORT_WINDOWS + TREND_DURABLE_LOOKBACK_WINDOWS
)
```
(`src/k_b/core/config.py`, sous `TREND_DURABLE_LOOKBACK_WINDOWS`)

4 + 2 = 6. Si #370 change l'un des deux, la première collecte suit sans autre modification.

### 2. Les fenêtres sont glissantes : une par jour

```python
if last_collected_at is None:
    due_count = GH_ARCHIVE_FIRST_COLLECTION_WINDOWS
    return [yesterday - timedelta(days=offset) for offset in reversed(range(due_count))]
```
(`src/k_b/etl/sources/gh_archive.py`, `list_window_ends`)

Une fenêtre couvre 3 jours, mais il en finit une chaque jour (décision du 2026-10-11) : six fenêtres
finissent les six derniers jours. C'est le même pas que le rattrapage, juste en dessous, et que le
contrôle du compte rendu, qui refuse deux fenêtres à plus d'un jour d'écart. La requête lit chaque jour
une fois : 8 jours ici, du premier jour de la plus ancienne fenêtre à hier.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| 6 fenêtres, calculées | Juste ce que lit le premier compte rendu | 15, le plafond du rattrapage : plus de lecture, sans usage |
| Dans la collecte | Collecte et compte rendu restent séparés | Rattraper depuis `kb trend-report` |
| Aucun réglage | Personne n'en a demandé | Une variable d'environnement |
| Deux tests d'une fenêtre partent d'une collecte de la veille | Ils vérifient le cas d'une fenêtre, qui existe toujours | Les réécrire pour six fenêtres : ils perdraient leur objet |

## Preuve

| Test | Ce que ça démontre |
|---|---|
| `test_a_first_collection_takes_the_windows_of_a_first_trend_report` | Six fins de fenêtre consécutives, la dernière hier ; la constante vaut 6 |
| `test_a_first_collection_reads_each_day_of_its_windows_once` | La requête va du 03/10 au 10/10, 8 jours, plafond de 6 fenêtres |
| `test_fetch_runs_a_dry_run_then_the_query_capped_with_its_parameters` | Une collecte le lendemain prend toujours une fenêtre |

Le test était rouge avant le code (`ImportError` sur la constante).

## Ce que tu dois pouvoir défendre

- **Pourquoi 6 et pas 4 ?** « Durable » lit les 2 fenêtres avant la période (`docs/tendances.md`,
  « Rang et critères ») ; sans elles, un dépôt ne peut être durable qu'à l'intérieur de la période.
- **Six fenêtres de 3 jours, ça fait 18 jours ?** Non : elles glissent d'un jour, la requête lit 8 jours,
  chacun une fois.
- **Combien ça coûte ?** Estimé entre 50 et 230 Mo de lecture BigQuery (une fenêtre récente a lu
  20,7 Mo, 15 fenêtres 481 Mo le 05/11), sous le plafond de 2 Go, qui reste.
- **Et une installation existante ?** Rien ne change : sa collecte a déjà un état, le rattrapage
  s'applique.

## Zones non vérifiées

- Aucun essai réel sur un état vide : le volume lu est une estimation.
- Les rendus de `make collect` des annexes d'E1 montrent « 1 window(s) » : vrais pour leur commit.

## Ce qui reste

- L'essai réel sur un état vide, sans toucher à l'état de Sabine.
- #370 : la revue des seuils peut changer le nombre, la constante suit.
