# Écrire la fiche des tests, avec le plan de tests de `POST /digests`

- Date : 2026-11-08
- Branche : `docs/tests-sheet`
- Issue : #478
- Fichier principal : `documentation/tests_pour_docu.md` (neuf)
- Série : la note [2026-11-08-documenter-les-tests-et-la-ci-dans-le-readme.md](2026-11-08-documenter-les-tests-et-la-ci-dans-le-readme.md)
  a écrit les tests dans le README ; celle-ci en fait une fiche à part, vérifiée contre le code.

## Le pourquoi

Le référentiel demande une documentation de l'environnement de test, de ses dépendances, du lancement des tests et du
calcul de la couverture (C12, et l'exécution des tests pour C17), et un plan de tests : les cas « listés et définis ».
Décision de Sabine du 08/11 : chaque documentation demandée devient une fiche neuve de `documentation/`, écrite
d'après le code, sans compléter un fichier de `docs/`. Le plan de tests de `POST /digests` (#478) entre dans cette
fiche au lieu d'une section de `docs/fiches-veille.md`.

## Le comment

### Ce que `uv run pytest` laisse de côté

`tests/conftest.py:46` :

```python
MARKERS_LEFT_OUT_BY_DEFAULT = (E2E_MARKER, POSTGRESQL_MARKER)
```

`pytest_collection_modifyitems` (même fichier) écarte ces deux marqueurs tant que `-m` ne les nomme pas. C'est
pourquoi la fiche donne trois commandes : la suite, `-m postgresql` (un serveur, `KB_TEST_POSTGRESQL_URL`) et
`-m e2e` (de vraies sources). Les comptes de la fiche (4061, 317, 11) viennent de `uv run pytest --co -q` à
`852dad4`.

### Le seuil de couverture

`pyproject.toml:76-83` :

```toml
branch = true
# pytest-cov 7 ne mesure plus les sous-processus : des tests lancent un processus enfant.
patch = ["subprocess"]

[tool.coverage.report]
# Plancher contre la régression, pas une cible (décision du 2026-11-08, journal ADR) : `--cov` échoue
# sous 96 %, en local (`make test-cov`) comme en CI (job `tests`).
fail_under = 96
```

Les branches comptent, les sous-processus sont mesurés, et `--cov` échoue sous 96 %. Seule une commande avec `--cov`
vérifie le seuil : `make test` ne le fait pas, le job `tests` de la CI si.

### Le modèle rejoué, la stratégie du plan

`src/k_b/ai_api/connectors/llm_replay.py:87-88` :

```python
class ReplayTransport(httpx2.MockTransport):
    """Gives the steps in order, one per request, and keeps each request."""
```

Le transport du client HTTP rend des réponses écrites d'avance : l'appel au modèle tourne en entier, sans réseau ni
clé. Avec la vraie API de données sur la base de test et les mesures en mémoire, c'est ce qui permet de classer chaque
fichier du plan en unitaire, intégration ou bout en bout, sans qu'aucun test de la CI n'appelle le modèle.

### Pourquoi le test de l'export échoue (#495)

`tests/conftest.py:145-149` retire, avant chaque test, les variables de `KB_SETTINGS_VARIABLES`, dont
`KB_DEPLOYMENT_ENVIRONMENT`. Or `tests/e2e/test_real_export.py:62-65` lit ses réglages dans `os.environ` :

```python
settings = read_metrics_export_settings_or_refusal(os.environ)
if settings is None:
    pytest.skip("KB_OTLP_ENDPOINT and KB_OTLP_HEADERS not set")
assert not isinstance(settings, str), settings
```

Avec l'adresse et les en-têtes posés, la variable a déjà disparu : le refus est une chaîne, et l'assertion échoue.
La fiche le dit tant que #495 est ouverte (ajout de Sabine au plan).

## Choix faits et options écartées

- **Une colonne « Fichier » par ligne du plan** (time-knight, règle de Sabine du 08/11). Trois noms de test existent
  dans deux fichiers. Écarté : le fichier seulement dans l'introduction de chaque composante, ambigu.
- **Les huit composantes de #478, telles quelles.** Les erreurs du fournisseur (429, 5xx, délai) n'en sont pas une :
  elles vont en note sous les contrôles. Écarté : une neuvième composante, hors du critère.
- **Renvoyer, ne pas recopier.** La fiche renvoie au contrat (`docs/fiches-veille.md`), au plan de `POST /trend-reports`
  (`docs/tendances.md`, « Ce qui le prouve ») et au compte rendu (`docs/2026-11-08-tests-api-ia.md`). Écarté : en
  recopier les tableaux, qui divergeraient.
- **Aucun numéro de passage de la certif** dans la fiche (règle de Sabine du 08/11) : l'en-tête recopie les intitulés
  du référentiel.

## Preuve

| Commande ou sortie | Ce qu'elle démontre |
|---|---|
| `grep -rn "def <nom>(" tests/` pour chaque nom cité | chaque test du plan existe ; la relecture a vérifié qu'il est dans le fichier de sa ligne et que le cas décrit ce que le test vérifie |
| `uv run pytest --cov --cov-report=term-missing:skip-covered`, 18:41 UTC, `852dad4` | 4061 réussis, 328 écartés, 98,42 % : la commande et le seuil de la fiche |
| la commande de #495, 18:44 UTC, `852dad4` | `AssertionError: KB_DEPLOYMENT_ENVIRONMENT: not set, sandbox or production`, `tests/e2e/test_real_export.py:65` |
| deux relectures par un sous-agent neuf (15 constats, puis 4 sur le delta) | corrigés, triés par time-knight |
| `git diff --stat --diff-filter=M origin/main -- docs/ README.md` | vide : aucun fichier existant de `docs/` ni le README touché |

## Ce que tu dois pouvoir défendre

- **Pourquoi la CI ne lance pas les tests `e2e` ?** Ils appellent de vraies sources et Grafana Cloud :
  `pytest_collection_modifyitems` les écarte (`tests/conftest.py`), pour qu'aucune CI n'appelle une vraie source.
- **Comment prouver qu'un appel au modèle est bien contrôlé sans appeler le modèle ?** Par le modèle rejoué : une
  sortie hors schéma, un sujet inventé ou un item piégé sont écrits d'avance, et le test vérifie l'état nommé
  (`tests/ai_api/test_llm_client.py`, `tests/ai_api/test_digests.py`).
- **96 %, c'est une cible ?** Non, un plancher contre la régression (commentaire de `pyproject.toml:81-82`, journal
  ADR du 2026-11-08). La mesure du jour est 98,42 %.
- **Les tests sur PostgreSQL comptent-ils dans la couverture ?** Non : `tests-postgresql` lance `-m postgresql` sans
  `--cov` (`.github/workflows/ci.yml`).
- **Un `.env` exporté fausse-t-il les tests ?** Les réglages de `kb` et de libpq sont retirés avant chaque test
  (`no_kb_setting_of_the_terminal`) ; `tests/commands/` et `tests/jobs/` en retirent d'autres. La fiche ne promet pas
  plus.

## Zones non vérifiées

- Le comportement par défaut de uv sur le groupe `dev` vient de sa documentation (Context7, 2026-11-08), pas du code.
- L'URL `https` du `git clone`, reprise du README, n'a pas été essayée : le dépôt local est cloné en SSH.

## Ce qui reste

- À la fusion de #164 : ajouter à la fiche `tests/e2e/test_sandbox_alerts.py` et `make sandbox-alerts` (ajout de
  Sabine au plan).
- À la correction de #495 : retirer de la fiche l'échec du test de l'export.
- L'accessibilité de la fiche : après le déploiement (#167).
