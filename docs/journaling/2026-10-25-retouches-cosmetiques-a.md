# Retouches cosmétiques A : utilitaires dans `core`, API IA rangée, `kb serve-data`

- **Date** : 2026-10-25
- **Branche** : `refactor/cosmetic-a`
- **Issue** : #299 (le renommage) ; les autres points viennent de la revue d'organisation du code faite par certif le 2026-10-25
- **Fichiers principaux** : `src/k_b/core/atomic_write.py`, `src/k_b/core/dates.py`, `src/k_b/ai_api/stages/fidelity.py`,
  `src/k_b/ai_api/observability/`, `src/k_b/commands/serve_data_command.py`, `tests/architecture/test_apis.py`

## Le pourquoi

Une revue de l'organisation du code a relevé des retouches locales. Aucune n'est un défaut de structure : il s'agit de
ranger ce qui est mal placé, sans changer de comportement. Tu as décidé de les traiter dans une session cosmétique
dédiée. Le comportement ne change qu'à un endroit, voulu : le nom de la commande `kb serve-data`.

## Le comment

### 1. Ce qui sert à plusieurs modules va dans `core`

`write_file_atomically` vivait dans `etl/raw_store.py`, alors que `post`, `commands` et `etl` s'en servent tous les trois.
`database/dates.py` servait à `database`, `etl`, `post` et `commands`. Les deux passent dans `core`, le vocabulaire
commun à toutes les couches (règle 5 de `conventions.md`). Le code est déplacé tel quel : seuls les imports changent.

```python
from k_b.core.atomic_write import write_file_atomically
```
(`src/k_b/post/vault_files.py:12`) : `post` n'importe plus `etl` pour écrire un fichier.

### 2. Les API n'écrivent toujours aucun fichier

Tant que la fonction était dans `etl`, le refus d'`etl` aux API suffisait à leur interdire d'écrire un fichier. Or `core`
leur est permis : sans précaution, le déplacement aurait ouvert une porte. La règle refuse donc ce module précis aux deux
API :

```python
AI_API_ALLOWED_MODULES = {"ai_api", "items", "core"}
AI_API_FORBIDDEN_MODULES = {"core.atomic_write"}
```
(`tests/architecture/test_apis.py:100-101`, et `DATA_API_FORBIDDEN_MODULES` aux lignes 21-25 pour l'API de données.)

### 3. L'API IA rangée par rôle

`fidelity` contrôle une affirmation rédigée : c'est une étape de la chaîne, elle rejoint `classification` et `writing`
dans `stages/`. `metrics` et `metric_instruments` mesurent les appels : ils vont dans un nouveau paquet,
`observability/`. Ce qui reste à la racine :
- le squelette de l'API, comme dans `data_api` ;
- le parcours d'une demande (`digests`) ;
- le vocabulaire que partagent toutes les couches (`watch_items`, `deadline`).

Les couches de `AI_API_LAYERS` ne bougent pas, seuls les noms des modules changent.

### 4. Des noms qui disent ce qu'ils font

- `kb serve` devient `kb serve-data`, symétrique de `kb serve-ai` ; son journal devient `logs/kb-serve-data.log`.
- Dans la doc en français, « fiches de veille » devient « comptes rendus de veille ».
- Les quatre `* 1000` qui convertissaient une durée utilisent la constante `MILLISECONDS_PER_SECOND`, qui existait déjà :

```python
    data_fetch_ms = round((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
```
(`src/k_b/ai_api/routers/digest_router.py:61`)

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Nom `core/atomic_write.py` | dit ce que fait le module | `core/file_writing.py` : collision avec `etl/file_writing.py`, qui écrit en base |
| Refus de `core.atomic_write` aux API | la règle 7 de `poc.md` reste tenue par un test | la laisser tenue par un `grep` seul |
| `watch_items` et `deadline` à la racine d'`ai_api` | les connecteurs, plus bas, les importent | les mettre dans `stages/` |
| `kb serve` sans alias | une seule façon de lancer l'API de données | garder l'ancien nom en alias |
| Fichier `docs/fiches-veille.md` gardé tel quel | 94 lignes le citent (code, tests, ADR) | le renommer, ce qui casserait les renvois de l'ADR |
| `clipping.py:151` (`* 1000`) laissé | il convertit des microsecondes en nanosecondes, pas des secondes | — |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `uv run pytest` : 2 469 tests verts | aucun comportement cassé par les déplacements |
| `ruff check`, `ruff format --check`, `mypy --strict` verts | aucun import mort ni cassé |
| Un import de `core.atomic_write` ajouté à `ai_api/settings.py`, puis à `data_api/settings.py` : `test_apis.py` échoue (1 test) | la nouvelle règle des API détecte bien l'écart |
| `kb --help` liste `serve-data` et plus `serve` | le renommage est effectif |
| `/code-review` (effort low) : aucun constat | relecture indépendante du diff de `src/` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi mettre `write_file_atomically` dans `core` ?** Parce que trois modules s'en servent, et que `core` est le
   vocabulaire commun à toutes les couches (`conventions.md`, règle 5).
2. **L'API IA peut-elle maintenant écrire un fichier ?** Non : `core.atomic_write` lui est refusé par un test, comme à
   l'API de données (`test_apis.py:21-25`, `:100-101`).
3. **Pourquoi `fidelity` dans `stages/` ?** C'est une étape de la chaîne (rédiger, puis vérifier chaque fait), au même
   titre que `classification` et `writing`.
4. **Pourquoi ne pas avoir tout sorti de la racine d'`ai_api` ?** `watch_items` et `deadline` sont importés par toutes les
   couches, connecteurs compris : les ranger dans un sous-dossier de la chaîne serait faux.

## Zones non vérifiées

- Les tests e2e (11, désélectionnés par défaut) n'ont pas été lancés. Ils n'invoquent pas `kb serve` d'après un `grep`.
- Un script ou un service hors du dépôt qui lancerait `kb serve` échouera : aucun n'est connu dans le dépôt.

## Ce qui reste

- `post` : son nom, son contenu et la suppression des classements dans `raw/` restent ouverts (décision de Sabine du
  2026-10-25).
- Le découpage de `tests/test_cli.py` et `tests/etl/test_load.py` : mission cosmétique B.
- Le mot « fiche » seul reste dans `docs/fiches-veille.md` ; dans le code, le terme reste `digest`.
