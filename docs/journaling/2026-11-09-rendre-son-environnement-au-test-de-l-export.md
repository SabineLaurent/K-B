# Rendre son environnement au test de bout en bout de l'export

- **Date** : 2026-11-09
- **Branche** : `fix/e2e-export-environment` (commits `971510d`, `cc0c1fb`, `9607f88`, sur `cbada1e`)
- **Issue** : #495
- **Fichiers** : `tests/conftest.py`, `tests/e2e/test_real_export.py`, `tests/test_e2e_selection.py`,
  `tests/architecture/test_environment.py`

Ni `src/` ni les exemples d'environnement ne changent : la PR ne touche que des tests. La liste de
commits que donne l'outil de la note remonte à des commits de `main` (#502, #507, #518) : ils ne
sont pas de cette PR et la note ne les couvre pas.

## Le pourquoi

`tests/e2e/test_real_export.py` est la seule preuve que les mesures de l'API IA partent vraiment
vers Grafana Cloud. Depuis le 2026-11-08, il échouait dès que l'export était réglé, pour deux
raisons sans lien entre elles :

1. `e781f3a` (#473) a ajouté `KB_DEPLOYMENT_ENVIRONMENT` aux réglages que la fixture autouse
   `no_kb_setting_of_the_terminal` retire de chaque test. Le test de l'export lit cette variable
   dans l'environnement : il ne la trouvait plus, et s'arrêtait sur « KB_DEPLOYMENT_ENVIRONMENT:
   not set ».
2. `06fb1f0` a ouvert `/digests` au seul client `KB_DIGEST`. Le test ouvrait l'API au client
   `TERMINAL`, et aurait reçu un 403 une fois le premier défaut levé.

La CI écarte les tests `e2e`, si bien qu'aucun des deux défauts ne s'y voyait. Sabine a ajouté une
demande : que les exemples d'environnement nomment chaque variable que lit le code, et rien d'autre.

## Le comment

### Un test de bout en bout garde les réglages qu'il lit

```python
END_TO_END_SETTINGS = frozenset({DEPLOYMENT_ENVIRONMENT_VARIABLE})
...
    is_end_to_end = request.node.get_closest_marker(E2E_MARKER) is not None
    kept = END_TO_END_SETTINGS if is_end_to_end else frozenset()
```
(`tests/conftest.py:43`, `:152-153`)

La fixture reçoit `request`, l'objet de pytest qui décrit le test en cours. Elle regarde si ce
test porte le marqueur `e2e` et, dans ce cas seulement, ne retire pas `KB_DEPLOYMENT_ENVIRONMENT`.
La suite par défaut reste protégée d'un terminal qui exporterait `production`, ce que #473 voulait.
Le nom passe par la constante de `src/k_b/core/api_settings.py`, aussi dans `KB_SETTINGS_VARIABLES` :
si la variable est renommée, les deux listes suivent.

La fixture racine retire ses réglages avant que la garde des tests e2e ne lise l'environnement
(`tests/e2e/conftest.py:23-24`). Une variable gardée doit donc aussi être permise par la garde :
`KB_DEPLOYMENT_ENVIRONMENT` l'est, puisque `.env.e2e_test.example:30` la donne.

### Le test de l'export ouvre l'API au client de la route

```python
        {DIGEST_CLIENT: SecretStr(client_key)},
```
(`tests/e2e/test_real_export.py:82`)

Le test prend la constante `DIGEST_CLIENT` de `src/k_b/core/config.py:300`, comme le bac à sable
(`tests/e2e/test_sandbox_alerts.py:121`). Si le nom du client change, le test suit.

### Une valeur hors liste prouve que la variable arrive, sans réseau

```python
    result = run_the_end_to_end_tests_of(
        "real_export",
        {
            ENDPOINT_VARIABLE: "https://otlp.example.invalid/otlp",
            HEADERS_VARIABLE: "Authorization=Basic%20AAAA",
            DEPLOYMENT_ENVIRONMENT_VARIABLE: "staging",
        },
    )

    assert result.returncode == pytest.ExitCode.TESTS_FAILED
```
(`tests/test_e2e_selection.py:179-188`)

Ce test de la suite par défaut lance le test de l'export dans un pytest à part. Avec `staging`, la
lecture des réglages rend un refus qui cite la valeur
(`src/k_b/ai_api/connectors/metrics_export.py:178-182`), et le test de l'export s'arrête à sa
ligne 65, avant de créer l'application. Rien ne part sur le réseau. Si la variable se perd, le
refus devient « not set » et le test échoue. Avec `sandbox`, la valeur aurait été valide, le test
aurait exporté, et la suite par défaut aurait fait une requête réseau.

Le sous-processus part d'un environnement nettoyé : ni les noms de `.env.example`, ni
`KB_DATA_API_KEY_*`, `KB_AI_API_KEY_*` ou `OTEL_*` (`tests/test_e2e_selection.py:99-119`). Sans ce
nettoyage, un terminal qui exporte son `.env` ferait sortir la garde avant le test, et ce test
échouerait pour une raison étrangère à son objet. La fonction sert aussi aux deux tests de la garde
qui existaient déjà : c'est son troisième usage dans le fichier, d'où sa généralisation.

### Les exemples nomment chaque variable lue

```python
    for module_info in pkgutil.walk_packages(k_b.__path__, "k_b."):
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
```
(`tests/architecture/test_environment.py:117-119`)

Par convention, `src/k_b` nomme chaque variable par une constante `*_VARIABLE`, et chaque famille
par une constante `*_VARIABLE_PREFIX` (`KB_DATA_API_KEY_`). Le test importe chaque module et lit
ces constantes. Il vérifie trois choses : chacune figure dans `.env.example` (pour un préfixe, au
moins un nom qui commence par lui) ; chaque nom de `.env.example` est l'une d'elles ; chaque nom de
`.env.e2e_test.example` figure dans `.env.example`. `OTEL_` est mis à part, parce que c'est un
préfixe que kb refuse et non un réglage.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Rendre la variable au test | La fixture la garde pour un test marqué `e2e` | La retirer de `KB_SETTINGS_VARIABLES` : la suite par défaut relirait le terminal, ce que #473 a fermé. Copier l'environnement à l'import du test : ça contourne la fixture au lieu de la corriger. Une fixture propre au seul test de l'export : plus étroite, mais aucune autre commande des tests e2e ne lit `is_sandbox` (plan validé par Sabine le 09/11). |
| Prouver le critère 3 | Sous-processus avec une valeur hors liste | Une adresse locale refusée : le test irait jusqu'à l'export et ses nouvelles tentatives, avec du réseau dans la CI. |
| Lire les constantes | Import des modules | L'AST ne voit pas les trois constantes écrites en f-string (`post/ai_api_client.py:47`, `post/trend_report_client.py:59`, `ai_api/connectors/data_api_settings.py:15`). Mesure du 2026-11-09 sur les 172 modules : aucun accès réseau, aucune variable `KB_` lue ; azure-identity lance `uname` et `file` à l'import, comme dans le reste de la suite. Tranché par time-knight. |
| Lecture des exemples | Recopiée dans `test_environment.py` | La partager avec `tests/e2e/conftest.py` : c'est la deuxième occurrence, et `code.md` fait factoriser à la troisième. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Commande du constat de #495, avant : `AssertionError: KB_DEPLOYMENT_ENVIRONMENT: not set`, `test_real_export.py:65` | Le défaut 1 est reproduit. |
| Même commande, après : échec à `test_real_export.py:119` (`all(result is SUCCESS)`) | La variable arrive, la réponse est 200 (ligne 117 passée, donc pas de 403), et le test exporte jusqu'à l'adresse factice. |
| `test_the_end_to_end_test_of_the_export_gets_the_environment_of_the_terminal` : rouge avant le correctif, vert après | Critère 3 de #495 : la suite par défaut voit la perte de l'environnement. |
| Les mêmes tests avec `KB_LLM_API_KEY`, `KB_TRACE_CONTENT`, `KB_AI_API_KEY_OTHER`, `OTEL_SERVICE_NAME` exportés : 35 passés | Le sous-processus ne dépend pas du terminal. |
| Simulation sur `find_read_variables` : une variable retirée de l'exemple, une ajoutée, un préfixe sans nom → chacune détectée | Les trois tests des exemples voient les écarts qu'ils visent. |
| `uv run pytest` : 4091 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé. |

## Ce que tu dois pouvoir défendre

- **Pourquoi ne pas simplement retirer `KB_DEPLOYMENT_ENVIRONMENT` de la liste ?** Parce qu'un
  terminal qui exporte `production` changerait alors ce que vérifient les tests de l'URL interne
  et de `/docs` (`src/k_b/core/api_settings.py:41-43`). Seuls les tests e2e lisent leurs réglages
  dans le terminal (`tests/conftest.py:152-153`).
- **Le test du critère 3 fait-il du réseau ?** Non. `staging` est refusé à la lecture des
  réglages, avant que l'application soit créée (`metrics_export.py:178-182`, `test_real_export.py:65`).
- **Que se passe-t-il si une nouvelle variable est lue sans être dans `.env.example` ?** Si elle
  est nommée par une constante `*_VARIABLE`, `test_every_variable_kb_reads_is_in_the_example`
  échoue. Si elle est lue par un littéral, rien ne la voit : c'est la limite écrite dans la
  docstring du module.
- **Importer tous les modules dans un test, n'est-ce pas risqué ?** La mesure ne trouve ni réseau
  ni lecture de variable `KB_`, et la suite importe déjà ces modules par ses autres tests. Le coût
  est de 0,30 s pour le test le plus long.
- **Où est la sécurité ?** Aucun secret n'est lu : le test réel prend ses valeurs dans
  `.env.e2e_test`, et c'est Sabine qui le lance. Les valeurs factices (`example.invalid`,
  `Basic%20AAAA`) ne valent rien. Le sous-processus ne reçoit aucune clé du terminal.

## Zones non vérifiées

- Le test réel avec les vraies valeurs de `.env.e2e_test` (critère 2 de #495) est lancé par Sabine
  et n'a pas encore son résultat au moment où la note est écrite.
- L'ordre des fixtures autouse (la fixture racine avant la garde e2e) est repris du commentaire de
  `tests/e2e/conftest.py:23-24` et des sorties observées, pas relu dans la documentation de pytest.
- La mesure des effets de bord de l'import est faite sur macOS ; sur Linux (la CI), `platform`
  peut lire d'autres fichiers.

## Ce qui reste

- Un nom de variable lu sans constante `*_VARIABLE` échappe au test des exemples. Rien ne tient
  cette convention, et aucun cas n'existe aujourd'hui.
- Les autres littéraux de `KB_SETTINGS_VARIABLES` (`tests/conftest.py:28-38`) restent écrits en
  dur : ils existaient avant cette PR.
