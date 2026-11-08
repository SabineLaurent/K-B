# Lancer les tests des données dans un job de CI nommé, `tests-data`

- **Date** : 2026-11-08
- **Branche** : `ci/data-tests-job`
- **Issue** : #481
- **Fichiers** : `.github/workflows/ci.yml`, `README.md`, `.github/dependabot.yml`
- **Série** : suite de [la note de #464](2026-11-08-faire-entrer-tests-postgresql-dans-la-ci.md), qui
  avait ajouté le job `tests-postgresql`, et de [celle de #485](2026-11-08-une-seule-version-d-uv.md),
  qui fixe uv 0.13.6 dans chaque job.

## Le pourquoi

Le référentiel demande que la chaîne de livraison intègre les tests des données (C13.4). Dans K-B, ces
tests existaient, mais ils se perdaient dans les 4061 tests du job `tests` : un rouge sur la validation
d'un item ne se voyait pas comme tel. Le besoin vient de la revue de la certif du 07/11. Il a été
découpé le 08/11, et Sabine a retenu cette recommandation : « les tests de l'ETL, du schéma, et de la
préparation des items pour le modèle ».

Le job `tests-data` fait apparaître ces tests à part dans la liste des checks d'une PR. Il couvre deux
moments : les données **avant la base** (ce qu'on lit des sources, et la forme qu'on leur impose), et
**avant le modèle** (ce que l'API IA envoie au modèle à partir des items).

## Le comment

### 1. La sélection : quatre chemins

`.github/workflows/ci.yml:108` :

```yaml
      - run: uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py
```

| Chemin | Tests | Ce qu'ils vérifient |
|---|---|---|
| `tests/etl` | 879 | l'extraction, la transformation et le chargement de chaque source, ceux de `make test-etl` |
| `tests/test_schema.py` | 227 | le schéma de la base : tables, contraintes, valeurs admises |
| `tests/test_items.py` | 230 | l'item commun dans lequel chaque source est lue avant l'import (`src/k_b/items.py`) : un item invalide est refusé |
| `tests/ai_api/test_watch_items.py` | 18 | les items tels que le modèle les reçoit : liste blanche des champs, masquage des URL et des logins, coupe pour la rédaction |

Ce sont 1354 tests, en 3,3 s sur le Mac. pytest accepte une liste de chemins : il ne collecte que ces
fichiers et ces dossiers.

### 2. Ce que le job ne lance pas : le test `postgresql` de `tests/etl`

`tests/conftest.py:114-116` :

```python
def pytest_collection_modifyitems(config, items):
    """Leave out the end-to-end tests and those on PostgreSQL unless -m names them, so that the CI
    never calls a real source, and the job without PostgreSQL never needs one."""
```

`tests/etl/test_import_on_both_engines.py` porte le marqueur `postgresql` (l. 45). Sans `-m postgresql`,
ce hook le retire de la collecte : c'est le « 2 deselected » de la sortie. Le job n'a pas de serveur
PostgreSQL, et ce test tourne déjà dans `tests-postgresql`. La ligne du README le dit.

### 3. Le job, calqué sur les autres

`.github/workflows/ci.yml:99-107` :

```yaml
  tests-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          version: "0.13.6" # the uv of the Dockerfile, in the uv_build range of pyproject.toml
          save-cache: false # the jobs share one cache key: only tests saves it
      - run: uv sync --locked
```

Mêmes actions, épinglées par leur SHA, même uv que l'image (#485). `save-cache: false` : seul `tests`
enregistre le cache d'uv, que les autres jobs relisent. Le job est **le dernier du fichier** : placé
plus haut, il aurait décalé les numéros de ligne que d'autres documents citent (constat 4 de la revue).

### 4. Pas de `--cov` : le seuil reste dans `tests`

Le seuil de couverture (96 %) se mesure sur toute la suite, dans le job `tests`, comme le demande le
critère de fin. Une mesure sur ces 1354 tests serait sans objet : elle échoue sous le seuil (57,43 %, « FAIL Required
test coverage of 96.0% not reached », essayé le 08/11). Ces tests
tournent donc deux fois, dans `tests` et dans `tests-data`, ce qui coûte environ 3 s.

### 5. La doc

`README.md:721` décrit le job, avec ses quatre chemins, dans le tableau de la CI, après
`tests-postgresql`, dans l'ordre du fichier. Trois mots suivent le nouveau compte :
- « cinq jobs requis de la CI » (`README.md:127`) : la liste nomme les 5 checks requis du ruleset de
  `main`, que ce travail ne change pas ;
- « six » (`README.md:727`, `:736`) et « 6 jobs » (`.github/dependabot.yml:23`) : les jobs où la version
  d'uv est à changer à la main.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Sélection | Les quatre chemins du plan, validés par Sabine. `tests/test_items.py` est un ajout à la liste de l'issue : il vérifie les données avant la base, ce qui est le « Pourquoi » de l'issue. | `tests/ai_api/test_stages.py` : il mêle les lots d'items et l'appel au modèle (schéma, consignes, rappels) ; choisir ses tests un par un, par leur nom, serait fragile. |
| Mode de sélection | Des chemins, comme l'issue. | Un marqueur `data` (constat 5) : il faudrait toucher `tests/conftest.py` et chaque fichier de tests. |
| Job ou étape | Un job à part, qui apparaît dans `gh pr checks` (l'issue demande un job nommé). | Une étape de plus dans `tests` (constat 7) : elle ne serait pas un check à part. |
| Couverture | Sans `--cov` : le seuil reste mesuré sur toute la suite, dans `tests`. | Retirer ces tests de `tests` pour éviter le double travail : la couverture de `tests` tomberait sous le seuil. |
| Makefile | Rien : les jobs de la CI appellent `uv run pytest` directement. | Une cible `make test-data` (constat 8) : ni l'issue ni le plan ne la demandent, et elle écrirait un rapport HTML inutile en CI. |
| Place dans `ci.yml` | En fin de fichier (constat 4, tranché par time-knight). | Juste après `tests` : la première version, qui décalait les lignes citées ailleurs. |
| Check requis | Non : hors de l'issue, c'est la décision de Sabine, à prendre sur GitHub (constat 1). | L'ajouter au ruleset dans cette PR. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/etl tests/test_schema.py tests/test_items.py tests/ai_api/test_watch_items.py` : « 1354 passed, 2 deselected in 3.23s » | La commande du job passe, sans serveur PostgreSQL. |
| `ruby -ryaml` sur `ci.yml` : jobs `audit, tests, lint, types, tests-postgresql, tests-data` | Le fichier se lit, et le job est le dernier. |
| `git diff origin/main -- .github/workflows/ci.yml` : un seul bloc, `@@ -90,3 +90,19 @@` | Aucune ligne existante de `ci.yml` ne bouge. |
| CI de la PR (à venir) : `gh pr checks` liste `tests-data` vert, avec 1354 passed dans son journal | Le job tourne sur GitHub. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un job à part, si `tests` lance déjà ces tests ?** Pour que les tests des données se voient
   comme tels : un rouge dans `tests-data` dit tout de suite que ce sont les données qui cassent. Le
   critère C13.4 demande que la chaîne intègre ce test, et un job nommé le montre (`ci.yml:99`).
2. **Pourquoi ces quatre fichiers ?** Ils vérifient les données à deux moments : avant la base (l'ETL,
   l'item commun, le schéma) et avant le modèle (la liste blanche, le masquage, la coupe). Le reste de la
   suite teste le comportement des API et des commandes (`ci.yml:108`).
3. **Pourquoi pas de mesure de couverture ici ?** Le seuil vaut pour toute la suite. Mesuré sur un
   sous-ensemble, il échouerait sans rien dire de la qualité des tests. `tests` le garde.
4. **Que se passe-t-il si `tests-data` est rouge ?** Le check est rouge dans la PR, mais il ne bloque pas
   la fusion : il n'est pas requis par le ruleset. En pratique, `tests` échoue aussi, puisqu'il lance les
   mêmes tests, et `tests` est requis.
5. **Et un nouveau test des données ?** S'il est dans un des quatre chemins, il est pris. Ailleurs, non :
   c'est la limite d'une sélection par chemins (« Ce qui reste »).

## Zones non vérifiées

- **La CI de la PR** est à venir au moment d'écrire cette note.
- **La frontière « données » / « reste »** est un jugement : `tests/test_items.py` en est, et
  `tests/ai_api/test_stages.py` n'en est pas. Un jury peut la discuter.

## Ce qui reste

- **Rendre `tests-data` requis** dans le ruleset de `main` : décision et geste de Sabine, sur GitHub.
- **Un nouveau test des données hors des quatre chemins** n'est pas pris : la sélection est à revoir s'il
  en apparaît un (un marqueur `data` serait alors le moyen).
- **Les renvois aux lignes de `ci.yml`** dans `docs/2026-11-08-tests-api-ia.md`, faux depuis #489 :
  issue #491 (XS), hors de ce travail.
