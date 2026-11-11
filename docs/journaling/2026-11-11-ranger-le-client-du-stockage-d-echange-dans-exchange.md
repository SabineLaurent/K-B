# Ranger le client du stockage d'échange dans un paquet `exchange`, que l'API de données peut importer

- **Date** : 2026-11-11
- **Branche** : `refactor/exchange-package`
- **Issue** : #558
- **Commits** : `9609149` (le déplacement, les règles de couches et leurs tests, `conventions.md`, `MEMORY.md`),
  `1effaba` (tri de la revue de code : les faux du stockage dans `tests/exchange/`, trois noms de tests, un
  commentaire, les renvois de la doc).
- **Fichiers principaux** : `src/k_b/exchange/storage.py` (ex-`src/k_b/jobs/exchange_storage.py`),
  `src/k_b/jobs/clip_mirror.py`, `src/k_b/jobs/watch_download.py`, `tests/architecture/test_layers.py`,
  `tests/architecture/test_apis.py`, `tests/exchange/storage_fakes.py` (ex-`tests/jobs/storage_fakes.py`)
- **Série** : le client est né avec `kb smoke-test`, dans
  [kb smoke-test, l'API et le stockage d'échange](2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md) (#412) ;
  `download_listed_version` a servi une seconde fois dans
  [Descendre les fiches de veille sur le Mac](2026-11-10-descendre-les-fiches-de-veille-sur-le-mac.md) (#424).
- **Hors de cette note** : la liste des commits fournie à la note part d'une base plus ancienne. Seuls `9609149` et
  `1effaba` sont à cette branche (`git log origin/main..HEAD`) ; les autres sont déjà sur `main`, par les PR de
  #550, #330, #551, #424, #540 et #500, et chacune a sa note.

## Le pourquoi

Le site, l'interface web du livrable, est entièrement privé et ne lit que l'API de données (décisions de Sabine du
2026-11-11). Il doit afficher les tops, les comptes rendus de veille et le rapport de tendances. Ces fiches ne sont
pas en base : les jobs les publient dans le conteneur `watch` du stockage d'échange, Azure Blob Storage. L'API de
données doit donc lire ce conteneur (#559 à #561).

Or le client du stockage (réglages, identité managée, transport, erreurs nommées) vivait dans `jobs/`, et une règle
d'architecture tenue par un test interdisait à tout autre paquet que `commands` d'importer `jobs`. L'API de données
ne pouvait pas l'atteindre.

Cette PR ne fait que **ranger** : elle sort le client de `jobs/` dans un paquet à lui, `exchange/`, et écrit qui a le
droit de l'importer. Aucun comportement ne change. La lecture de `watch` par l'API de données vient avec #559.

## Le comment

### 1. Un paquet de plus, et ses deux règles

`exchange/` se place sous ceux qui s'en servent et au-dessus de `core`. La règle tient en trois ensembles :

```python
EXCHANGE_ALLOWED_MODULES = {"exchange", "core"}
EXCHANGE_FORBIDDEN_MODULES = {"core.atomic_write"}
EXCHANGE_IMPORTERS = {"exchange", "jobs", "commands", "data_api"}
```
(`tests/architecture/test_layers.py:393-395`)

Les deux premiers disent ce qu'`exchange` **importe** : rien de K-B hors de `core`, et jamais `core.atomic_write`.
Le troisième dit qui **l'importe** : `jobs`, `commands` et `data_api`, et personne d'autre. Deux tests les
vérifient sur le code réel, en lisant les imports de chaque fichier par l'arbre syntaxique (`ast`) :
`test_exchange_imports_only_core_and_never_the_writing_of_a_file` (`:411`) et
`test_only_jobs_commands_and_the_data_api_import_exchange` (`:417`). Deux autres prouvent que la règle refuse ce
qu'elle doit refuser, sur des imports écrits exprès (`:441`, `:461`). Sans eux, une règle trop lâche passerait sans
bruit. Le nouveau paquet est aussi listé dans `TOP_LEVEL_MODULES` (`tests/architecture/module_imports.py:21`), que
`test_every_module_of_k_b_is_listed` compare aux modules réels de `k_b` : un paquet non listé fait échouer ce test.

### 2. Pourquoi jamais `core.atomic_write`, et pourquoi `from k_b import core` est refusé

`core.atomic_write` est l'écriture d'un fichier de K-B (règle 2 de `conventions.md`). Le client du stockage rend des
**octets** : ce qu'on en fait (écrire un clip dans le coffre, une fiche dans `veille/`) reste dans `jobs/`. L'API de
données, elle, n'écrit aucun fichier : la règle de l'API le lui interdit déjà (`tests/architecture/test_apis.py`). Si
`exchange` importait l'écriture, l'API de données l'atteindrait à travers lui.

D'où une ligne qui surprend dans le test des refus :

```python
        ("from k_b import core", True),
```
(`tests/architecture/test_layers.py:434`)

`core` est permis, mais importer **le paquet entier** atteint aussi `core.atomic_write`. C'est ce que mesure
`reaches` :

```python
    return is_within(name, modules) or any(
        module.startswith(f"{name}.") for module in modules
    )
```
(`tests/architecture/module_imports.py:94-96`)

`reaches("core", {"core.atomic_write"})` est vrai, car `core.atomic_write` commence par `core.`. La règle de l'API de
données fait de même pour `database` et `database.writers`.

### 3. Le téléchargement d'une version listée change de maison

`download_listed_version` vivait dans `jobs/clip_mirror.py`, et `jobs/watch_download.py` l'importait de là. Il passe
dans `exchange/storage.py`, tel quel :

```python
            downloader = container_client.download_blob(
                blob.name,
                etag=blob.etag,
                match_condition=MatchConditions.IfNotModified,
                decompress=False,
            )
```
(`src/k_b/exchange/storage.py:197-202`)

Trois choses à savoir dire :
- **`etag` + `IfNotModified`** : le SDK envoie `If-Match` avec l'etag lu à la liste. Si le blob a changé entre la
  liste et le téléchargement, le stockage répond 412 au lieu de rendre une autre version que celle dont on a vérifié
  la taille.
- **`decompress=False`** : un blob envoyé avec `Content-Encoding: gzip` serait décompressé par le SDK, et
  quelques kilo-octets compressés peuvent donner des gigaoctets. Les octets restent tels que stockés.
- **`None` sur 404 ou 412** (`STATUS_CHANGED_SINCE_LISTING`, `:65`) : le blob a été retiré ou changé depuis la liste.
  Le miroir des clips le laisse au lancement suivant, le téléchargement de `veille/` le saute.

La constante s'appelait `STATUS_LEFT_TO_NEXT_RUN`. Ce nom disait ce que fait **le miroir des clips** de ce cas.
Dans un module partagé, il serait faux pour l'API de données, qui n'a pas de « lancement suivant ». Le nouveau nom
dit ce que le statut **observe**.

### 4. Les règles des voisins

Trois règles changent d'un mot :
- `jobs` importe désormais `exchange` et `core` (`JOBS_ALLOWED_MODULES`, `tests/architecture/test_layers.py:326`) ;
- l'API de données importe aussi `exchange` (`DATA_API_ALLOWED_MODULES`, `tests/architecture/test_apis.py:22`), et
  le test des refus vérifie qu'elle n'atteint toujours pas `jobs` (`:67`) ;
- l'API IA reste coupée du stockage : un import d'`exchange` y est refusé (`test_apis.py:138`).

Leurs tests portent le nom de la règle nouvelle (`test_jobs_imports_only_exchange_and_core`,
`test_data_api_imports_only_data_api_database_items_core_and_exchange`) : un test qui échoue doit nommer la règle en
vigueur.

### 5. Les tests suivent le code

`tests/jobs/test_exchange_storage.py` devient `tests/exchange/test_storage.py`, et les faux du stockage
(`FakeTransport`, `FakeContainer`, le point d'identité simulé) passent de `tests/jobs/storage_fakes.py` à
`tests/exchange/storage_fakes.py`. Seuls changent les chemins d'import. Hors des tests d'architecture, **aucune
assertion ne change** :

```
git diff origin/main...HEAD -M -- tests ':!tests/architecture' | grep -E "^[+-]" | …
```

Ne restent que des imports, la fixture du nouveau `conftest.py` et deux textes qui citaient l'ancien chemin. C'est la
preuve qu'un déplacement n'a rien changé : les mêmes tests, avec les mêmes attentes, passent sur le code déplacé.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où mettre le client | Un paquet neuf, `exchange/` : seuls ceux qui en ont besoin l'atteignent (plan de la session, accepté par time-knight le 2026-11-11) | `core/`, ouvert à toutes les couches : l'API IA, `etl` et `database` atteindraient le stockage. Ouvrir `jobs` à `data_api` : l'API atteindrait l'écriture d'un fichier (`jobs/clip_mirror.py` importe `core.atomic_write`). Une seconde copie du client, pour deux raisons (time-knight, le 2026-11-11) : une même connaissance à deux endroits (`code.md`, « Duplication ») ; et les gardes du client, `decompress=False` et `If-Match` sur l'etag, à tenir à l'identique dans les deux copies, si bien qu'une correction de sécurité faite dans l'une manquerait à l'autre |
| Ce qu'`exchange` importe | `core`, jamais `core.atomic_write` : il rend des octets, l'écriture reste dans `jobs` | Laisser `core` entier : l'API de données atteindrait l'écriture par lui |
| Le nom du statut | `STATUS_CHANGED_SINCE_LISTING`, ce que le statut observe | Garder `STATUS_LEFT_TO_NEXT_RUN`, vrai pour le seul miroir des clips |
| Les faux du stockage | Dans `tests/exchange/` dès cette PR (tri de time-knight : les faux vont avec le paquet qu'ils simulent) | Les laisser dans `tests/jobs/` jusqu'à #559 : une chose de plus à se rappeler, et des tests de l'API de données qui dépendraient de `tests/jobs` |
| La fixture qui retire les variables d'un lancement en ligne | Deux `conftest.py` de deux lignes (`tests/jobs/`, `tests/exchange/`), qui appellent `remove_online_variables`, définie une fois | Une fixture `autouse` à la racine : elle s'appliquerait à tous les tests |
| La copie du transport et de l'identifiant client dans `database/entra.py` et `location.py` | Gardée : la base n'importe pas `exchange`, et la mise en commun attend une troisième copie (journal ADR, 2026-11-06, #421) | Les mettre dans `core` : Azure deviendrait atteignable par l'API IA et `etl` |
| Revue de sécurité | Pas de `/security-review` (tranché par time-knight) : un déplacement, sans entrée externe, ni secret, ni authentification nouvelle | — ; l'accès de l'API de données au stockage arrive avec #559, qui aura la sienne |

La règle 5 de `.claude/rules/conventions.md` et `MEMORY.md` disent la nouvelle règle (`9609149`).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Les tests de `9609149` lancés sur une copie de `origin/main` (`git archive d1b5400`, son propre `src`) : `ModuleNotFoundError: No module named 'k_b.exchange'` à la collecte de `tests/exchange/test_storage.py`, puis `test_exchange_imports_only_core_and_never_the_writing_of_a_file` et `test_every_module_of_k_b_is_listed` rouges, `2 failed, 261 passed` (sortie dans « Checks » de la PR) | Les tests nouveaux échouent sans le paquet : ils testent bien quelque chose |
| `test_exchange_imports_only_core_and_never_the_writing_of_a_file`, `test_only_jobs_commands_and_the_data_api_import_exchange` | La règle tient sur le code réel |
| `test_the_rule_of_exchange_refuses_every_layer_and_the_writing_of_a_file`, `test_the_rule_of_exchange_refuses_every_way_to_it_but_its_importers` | La règle refuse `core.atomic_write`, `from k_b import core`, `jobs`, `database`, et tout import d'`exchange` par l'API IA, `etl`, `database`, `post`, `purge` ou `core` |
| `test_every_module_of_k_b_is_listed` | `exchange` est listé dans `TOP_LEVEL_MODULES` |
| `uv run pytest` → 4243 passed (après `1effaba`) | Les tests des jobs et du stockage passent sans changement d'assertion |
| `uv run ruff check --no-cache`, `ruff format --check`, `mypy --strict` (177 fichiers) verts ; aucun caractère `Cc` ni `Cf` dans les 39 fichiers modifiés | Les contrôles du dépôt |
| `git grep` des anciens noms et chemins (`jobs/exchange_storage`, `jobs.storage_fakes`, `STATUS_LEFT_TO_NEXT_RUN`, les trois anciens noms de tests), hors notes et journal datés → rien | Aucun renvoi ne pointe vers ce qui n'existe plus |
| Job CI `tests-postgresql` de la PR | Le second moteur : `uv run pytest -m postgresql` n'a pas été lancé sur le Mac |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas mettre le client dans `core`, qui est déjà commun ?** Parce que `core` est ouvert à toutes les
   couches : l'API IA, l'ETL et la base atteindraient le stockage d'Azure. `exchange` n'est ouvert qu'à `jobs`,
   `commands` et `data_api` (`tests/architecture/test_layers.py:395`). C'est le moindre privilège, appliqué aux
   imports.
2. **L'API de données peut-elle maintenant écrire un fichier ?** Non. Sa règle refuse toujours `core.atomic_write`
   (`tests/architecture/test_apis.py`), et `exchange` ne l'importe pas, même indirectement : `from k_b import core`
   y est refusé (`test_layers.py:434`).
3. **Comment sais-tu qu'un déplacement n'a rien cassé ?** Hors des tests d'architecture, les tests n'ont changé que
   leurs imports : mêmes assertions, toutes vertes (4243). Le déplacement de `exchange_storage.py` est un renommage
   pour git, et `download_listed_version` est recopiée à l'identique (`git diff origin/main:src/k_b/jobs/exchange_storage.py
   HEAD:src/k_b/exchange/storage.py`).
4. **Que se passe-t-il si un blob change entre la liste et son téléchargement ?** Le stockage répond 412, grâce à
   `If-Match` sur l'etag, et la fonction rend `None` (`src/k_b/exchange/storage.py:189-208`). Limite connue : un
   conteneur absent répond 404 lui aussi, et rend `None` de même. #559 la corrige (dernière section).
5. **Pourquoi un test qui vérifie qu'une règle refuse ?** Un test qui ne lit que le code réel passe aussi avec une
   règle vide. Les tests paramétrés (`:441`, `:461`) donnent des imports interdits écrits exprès et vérifient que la
   règle les refuse.

## Zones non vérifiées

- **`uv run pytest -m postgresql` n'a pas été lancé sur le Mac** : la preuve du second moteur est le job CI
  `tests-postgresql` de la PR (précédent du 09/11). Le diff ne touche pas au SQL.
- **`download_listed_version` n'a pas de test direct** : son contrat (404 et 412 rendent `None`, `decompress=False`,
  `If-Match`) n'est testé qu'à travers le miroir des clips et le téléchargement de `veille/` (constat 8 de la revue,
  reporté à #559).
- **Les renvois `fichier:ligne` corrigés** dans la doc l'ont été un par un contre `origin/main`. Seuls ceux qui visent
  des fichiers de ce diff ont été revus : les renvois des mêmes documents vers d'autres fichiers ne changent pas avec
  cette PR.

## Ce qui reste

- **#559** (les tops servis par l'API de données) fait de l'API le troisième appelant du téléchargement. Il porte
  les constats de la revue écartés ici parce que préexistants, à écrire en commentaire de #559 (texte remis à
  Sabine par time-knight) :
  - (1) ne rendre `None` que sur `BlobNotFound` et `ConditionNotMet`, pour qu'un conteneur absent (`ContainerNotFound`)
    soit une erreur nommée ;
  - (2) une borne en octets dans la fonction (`length` de `download_blob`) ;
  - (8) des tests directs de la fonction ;
  - (10) des textes qui ne disent plus « l'identité d'un job ».
- **#560 et #561** : les comptes rendus de veille et le rapport de tendances, par le même chemin.
- **Côté Azure** : le rôle de lecture de `watch` pour l'identité de l'API de données, et `KB_EXCHANGE_BLOB_URL` sur
  son conteneur. C'est l'infra, tenue par tn-codeur, pas cette PR.
