# Rapport HTML et variables des tests de bout en bout

- **Date** : 2026-10-21
- **Branche** : `test/e2e-report-and-env-file`
- **Issue** : #290
- **Suite de** : [Roder la collecte sur données réelles](2026-10-21-roder-la-collecte-sur-donnees-reelles.md) (#25)
- **Fichiers principaux** : `tests/conftest.py`, `tests/e2e/test_real_sources.py`,
  `tests/test_e2e_selection.py`, `.env.e2e_test.example`, `.gitignore`, `pyproject.toml`
- **Commits** : `933edbe` (code), `f87b3c2` (docs et ADR), `3b5dbd9` et `18b92f9` (corrections
  de la revue). Les commits plus anciens que la liste du skill donne viennent de `main` : ils ne
  sont pas de cette branche, la note ne les couvre pas.

## Le pourquoi

Les tests de bout en bout (#25) lancent `kb create-db`, `kb collect` et `kb import` sur les vraies
sources. Deux manques sont apparus en les rejouant le 21/10 :

1. **Pas de trace exploitable.** Le compte rendu de #25 a été recopié à la main depuis la console.
   Il faut un rapport produit par la commande elle-même, qui donne les résultats (codes de sortie,
   items, rejets) ; l'interprétation reste écrite à la main.
2. **Trop de privilèges.** Lancés par `uv run --env-file .env`, chaque `kb` recevait tout le
   `.env`, clés Azure et clés d'API comprises, alors qu'aucun test n'en a besoin. C'était une
   limite assumée de #25 ; l'utilisatrice a demandé de la lever juste après (moindre privilège,
   `code.md`, « Sécurité dès la conception »).

## Le comment

### 1. Un fichier d'environnement réduit, et un garde-fou par noms

`.env.e2e_test.example`, suivi par git, liste les quatre variables des tests : `KB_GITHUB_TOKEN`,
`KB_ZOTERO_DIR`, `KB_VAULT_DIR`, `GOOGLE_APPLICATION_CREDENTIALS`. L'utilisatrice en fait une copie,
`.env.e2e_test`, ignorée par git (`.gitignore` : `.env.*`, sauf `!.env.e2e_test.example`).

Mais uv **ajoute** le fichier à l'environnement du terminal, qui prime : un `.env` exporté dans
le terminal donnerait encore toutes les clés à `kb`. D'où un garde-fou, au début de chaque test :

```python
    names_beyond = find_names_beyond_the_end_to_end_tests(
        ENV_EXAMPLE_PATH, E2E_ENV_EXAMPLE_PATH
    )
    present = sorted(
        name
        for name in os.environ
        if name in names_beyond or name.startswith(API_KEY_VARIABLE_PREFIX)
    )
```
(`tests/e2e/test_real_sources.py:130-137`)

Il ne lit que des **noms** (les clés de `os.environ`), jamais `os.environ[name]` : une valeur ne
peut donc ni s'afficher ni rester dans une variable locale. En plus des noms de `.env.example`, il
arrête sur toute clé d'un client de l'API de données, `KB_API_KEY_<CLIENT>` : `kb serve` lit cette
famille par son préfixe (`API_KEY_VARIABLE_PREFIX`, importé de `k_b.core.api_keys`, jamais écrit en
dur), et `.env.example` n'en nomme que deux. `pytest.exit` arrête toute la session, pas
seulement le test, avec le code `USAGE_ERROR` : aucun `kb` n'est lancé.

### 2. Quels noms comptent

```python
VARIABLE_LINE = re.compile(r"^#?[ \t]*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
SET_VARIABLE_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)
```
(`tests/e2e/test_real_sources.py:98-100`)

Deux lectures différentes, et c'est voulu :
- dans `.env.example`, une ligne **commentée** compte : des clés y sont commentées
  (`# KB_API_KEY_AI_DIGEST=`), et une clé exportée doit arrêter les tests même si son modèle la
  commente ;
- dans `.env.e2e_test.example`, seule une ligne **posée** compte : un nom commenté là n'est pas
  une variable des tests. Sans cette distinction, écrire `# KB_LLM_API_KEY=` dans le modèle e2e
  laissait passer la clé (constat de la revue, vérifié par le relecteur de time-knight).

`[ \t]*` plutôt que `\s*` : avec `re.MULTILINE`, `\s` traverse un saut de ligne.

Sont retirés de la liste les noms que le test pose lui-même (`KB_DATA_DIR`, `KB_COLLECT_ONLY`,
`VARIABLES_SET_BY_THE_TEST`, l. 103). Ceux que `tests/conftest.py` retire (`KB_LOG_TO_FILE`,
`KB_DATA_API_HOST`, `KB_DATA_API_PORT`, `KB_DATA_API_ALLOWED_HOSTS`) n'ont pas besoin d'être nommés :
la fixture du garde-fou est de portée fonction, définie dans le module ; pytest instancie d'abord
les fixtures `autouse` du `conftest.py` (`no_kb_setting_of_the_terminal`), donc ces variables ont
déjà disparu quand le garde-fou lit l'environnement.

### 3. Les chiffres de chaque test : `record_property`

```python
    record_property("create_db_exit_code", create_db_exit_code)
    assert create_db_exit_code == ExitCode.SUCCEEDED
```
(`tests/e2e/test_real_sources.py:286-287`)

`record_property` est une fixture intégrée à pytest : elle ajoute une paire `(nom, valeur)` à
`report.user_properties`. Chaque chiffre est inscrit **avant** son `assert` : un test en échec
garde ses chiffres dans le rapport. Sont inscrits : les trois codes de sortie, les rejets, les
lignes d'avertissement ou d'erreur, les items par sorte (`SELECT kind, COUNT(*) FROM item GROUP BY
kind`), les tendances (`gh_archive`), les relevés des tops, et les octets lus par BigQuery, lus
dans `collect.err` sur la ligne que `gh_archive` journalise déjà
(`src/k_b/etl/sources/gh_archive.py:170`). Si cette ligne manque, rien n'est inscrit ; si BigQuery
n'a pas donné de compte, la valeur inscrite est `None` (l. 292-298). Le nombre d'items et celui
de la sorte attendue sont pris du même décompte par sorte : une seule source pour un même fait.

### 4. Les montrer dans le rapport : une colonne par les hooks de pytest-html

pytest-html 4.2.0 ne lit jamais `user_properties` (vérifié dans son code). Il offre deux hooks
pour ajouter une colonne :

```python
    properties = getattr(report, "user_properties", ())
    lines = "<br>".join(html.escape(f"{name}={value}") for name, value in properties)
    cells.insert(PROPERTIES_COLUMN, f'<td class="col-properties">{lines}</td>')
```
(`tests/conftest.py:85-87`)

- `getattr(..., ())` : un rapport de **collecte** (`CollectReport`) passe aussi par ce hook et n'a
  pas d'attribut `user_properties` ; sans `getattr`, une erreur de collecte deviendrait une
  erreur interne de pytest.
- `html.escape` : le rapport insère les cellules par `innerHTML`. Une valeur qui contiendrait une
  balise serait interprétée comme du HTML ; échappée, elle reste du texte.
- `optionalhook=True` (l. 76, 81) : sans pytest-html, pytest refuserait un hook qu'il ne connaît
  pas.

### 5. Le rapport lisible par l'utilisatrice seule, et jamais dans un commit

Le rapport garde la sortie capturée de chaque test, réussi compris (repliée), et la trace d'un
échec. `restrict_report_to_user` (`tests/conftest.py:51-73`) agit dans `pytest_configure`, avant que
pytest-html écrive :

```python
    if resolved_path.is_relative_to(
        repository_dir
    ) and not resolved_path.is_relative_to(repository_dir / REPORT_DIR_NAME):
        pytest.exit(
```
(`tests/conftest.py:63-66`)

- **Emplacement** : dans le dépôt (`config.rootpath`, la racine de K-B), seul `reports/` est permis,
  car seul `/reports/` est ignoré par git. Ailleurs dans le dépôt : arrêt avant tout fichier. Hors
  du dépôt : permis.
- **Droits** : le dossier, s'il est neuf, est créé en `0700` ; le fichier est créé d'avance en
  `0600` (`os.open(..., O_CREAT, 0o600)`, l. 72), puis `chmod 0600` s'il existait. pytest-html le
  réécrit ensuite par `open("w")` (`pytest_html/basereport.py:140`), qui garde le mode d'un fichier
  existant. Un dossier existant n'est jamais modifié : ce pourrait être la racine du dépôt.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Outil du rapport | `pytest-html` en dépendance de développement : décision de l'utilisatrice du 21/10 | `rich` ou un rapport maison : non demandés |
| Chiffres | `record_property`, fixture intégrée : décision du 21/10 | un fichier JSON à part : un second format à lire |
| Garde-fou | arrêt par `pytest.exit`, sur les noms de `.env.example` moins ceux du modèle e2e | une liste d'autorisation passée en `env=` à `run_kb` : la décision « `run_kb` reste tel quel » de l'issue ; notée par time-knight pour après le 25/10 |
| Noms posés ou retirés par le test | exemptés (option b, décision de l'utilisatrice relayée par time-knight) | le critère à la lettre : en conteneur, `KB_DATA_DIR` et `KB_LOG_TO_FILE` sont posés, tout aurait été arrêté |
| Où vit le garde-fou | une fixture du module e2e : il ne coûte qu'aux tests e2e | `tests/conftest.py` : toute la suite le paierait |
| Emplacement du rapport | `reports/` à la racine, ignoré par git ; refus ailleurs dans le dépôt (décision de time-knight) | `temp/`, dossier de données des essais de l'utilisatrice ; `$TMPDIR`, durée de conservation non vérifiable ; `reports/` à toute profondeur, qui ne couvre ni un rapport hors d'un tel dossier ni un fichier suivi écrasé |
| Droits | fichier créé d'avance en `0600` | `chmod` à la fin (`pytest_unconfigure`) : une fenêtre où le fichier est en `0644` |
| Conservation | un seul fichier, écrasé à chaque production | un fichier daté par exécution : s'accumule sans purge |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_end_to_end_tests_stop_on_a_variable_beyond_theirs_without_its_value` (`tests/test_e2e_selection.py:117`) | avec `KB_LLM_API_KEY` posé, `pytest -m e2e -k zotero` sort en `USAGE_ERROR`, nomme la variable, n'affiche jamais sa valeur ; `KB_DATA_DIR` et `KB_LOG_TO_FILE` n'arrêtent pas. Sans `KB_ZOTERO_DIR`, un garde-fou cassé ferait sauter le test : aucune source réelle n'est appelée |
| `test_the_end_to_end_tests_stop_on_the_key_of_any_client_without_its_value` (l. 137) | une clé `KB_API_KEY_<CLIENT>` que `.env.example` ne nomme pas arrête aussi, sans afficher sa valeur |
| `test_a_name_commented_out_in_the_end_to_end_example_is_not_theirs` (l. 275) | un nom commenté dans le modèle e2e n'exempte pas ; un nom commenté dans `.env.example` compte |
| `test_a_recorded_property_is_in_the_report_escaped` (l. 197) | une valeur inscrite par `record_property` est dans le rapport produit, échappée |
| `test_the_report_and_its_new_folder_are_readable_by_the_user_alone` (l. 210), `test_a_report_written_before_is_made_readable_by_the_user_alone` (l. 221) | dossier neuf en `0700`, fichier en `0600`, même s'il existait en `0644` |
| `test_a_report_in_the_repository_outside_reports_is_refused_before_any_file` (l. 234), `test_a_report_outside_the_repository_is_written` (l. 250) ; avec `--basetemp` dans le dépôt, ces tests passent (`--rootdir` donné au sous-processus) | refus avant tout fichier dans le dépôt hors de `reports/` ; écriture permise hors du dépôt |
| `env -u KB_ZOTERO_DIR uv run pytest -m e2e -k zotero tests/e2e -rs` → `1 skipped, 9 deselected` | dans un environnement propre, le garde-fou laisse passer |
| rapport produit sur `tests/test_e2e_selection.py` : `stat -f %Lp` → `700 reports`, `600 reports/e2e-report.html` ; `git status --short` inchangé ; ouvert dans le navigateur | le rapport s'ouvre, n'est pas suivi par git, n'est lisible que par l'utilisatrice |
| `--html=e2e-report.html` à la racine → `Exit: --html: …/e2e-report.html is in the repository outside reports/…`, aucun fichier | le refus fonctionne sur le vrai dépôt |
| `uv run pytest` → 1969 passed, 10 deselected ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | la suite reste verte, les tests e2e restent écartés |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un garde-fou plutôt que de ne passer à `kb` que ses variables ?** La décision de
   l'issue était de garder `run_kb` tel quel ; une liste d'autorisation (`env=`) serait plus forte
   et reste à repenser après le 25/10. Le garde-fou rend la consigne « terminal sans `.env`
   exporté » vérifiée, au lieu d'être seulement écrite (`tests/e2e/test_real_sources.py:124-144`).
2. **Le garde-fou peut-il divulguer un secret ?** Non : il ne lit que la présence d'un nom ; le
   message ne contient que des noms ; un test vérifie que la valeur n'est ni sur stdout ni sur
   stderr (`tests/test_e2e_selection.py:117`, 137).
3. **Que se passe-t-il si quelqu'un ajoute `--html=docs/rapport.html` ?** pytest s'arrête avant
   d'écrire quoi que ce soit : seul `reports/` est ignoré par git, et le dépôt devient public le
   25/10 (`tests/conftest.py:63-70`).
4. **Pourquoi le fichier est-il créé avant pytest-html ?** Pour qu'il ne soit jamais lisible par un
   autre compte, même un instant : pytest-html le réécrit sur place, ce qui garde le mode `0600`.
5. **Pourquoi échapper des nombres ?** La colonne accepte toute valeur inscrite ; un jour une chaîne
   y viendra. Le rapport insère ses cellules par `innerHTML` : sans échappement, ce serait une
   injection de HTML.

## Zones non vérifiées

- **Les tests de bout en bout réels n'ont pas été relancés** : le rapport n'a été produit que sur
  `tests/test_e2e_selection.py`. Les chiffres de `record_property` sur les vraies sources, dont les
  octets BigQuery, n'ont donc pas été vus dans un rapport ; cela attend une décision de
  l'utilisatrice.
- **`read_bigquery_bytes` n'a pas de test dédié** : la fonction vit dans le module e2e, dont la
  fixture `autouse` du garde-fou s'appliquerait à un test placé là. Sa regex a été relue contre
  `gh_archive.py:170`, pas exécutée sur un vrai journal.
- **L'ordre des fixtures `autouse`** (celles du `conftest.py` avant celles du module) est le
  comportement documenté de pytest ; il est prouvé indirectement par le test du garde-fou
  (`KB_LOG_TO_FILE` posé n'arrête pas).
- **`config.rootpath`** vaut la racine de K-B parce que pytest prend le `pyproject.toml` comme
  fichier de configuration même sans table `[tool.pytest]` ; vérifié depuis `tests/`
  (`rootdir: <dépôt>`, `configfile: pyproject.toml`), pas depuis un autre sous-dossier.
- **La table « Environment »** de pytest-metadata 3.1.1 n'a été vue que sur le Mac (Python,
  Platform, Packages, Plugins) ; sur un service de CI, elle ajoute ses variables.

## Ce qui reste

- Produire le rapport sur les tests e2e réels, sur décision de l'utilisatrice (pas `gh_archive` ni
  arXiv sans elle).
- Une liste d'autorisation des variables passée à `kb` (`env=` dans `run_kb`), avec la lecture
  centralisée des réglages : notée par time-knight, après le 25/10.
- En conteneur (#200) : le conteneur des tests ne porte que leurs variables, sinon le garde-fou les
  arrête (`KB_DATA_API_URL` compris) ; `.env.example` et `.env.e2e_test.example` doivent être dans
  l'image (un `.dockerignore` qui exclut `.env*` demandera `!.env*.example`, comme le `.gitignore`) ;
  l'ADR écrit `docker compose run kb …`, alors que #200 ne prévoit pas de service `kb` : il faudra
  un service ou un profil e2e, avec son propre fichier d'environnement.
- Un lien symbolique posé en `reports/e2e-report.html` serait suivi (sa cible passe en `0600` et
  est écrasée) : écarté par time-knight, risque très faible ; `O_NOFOLLOW` ne couvrirait que le
  dernier composant du chemin.
- #276 réécrira la procédure de tri du registre en partant de l'étape 10 mise à jour ici.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| pytest, `record_property` (les propriétés passent dans le rapport du test, `user_properties`), par Context7 | https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/output.rst | 2026-10-21 |
| pytest-html, hooks `pytest_html_results_table_header` et `pytest_html_results_table_row`, par Context7 | https://github.com/pytest-dev/pytest-html/blob/master/docs/user_guide.rst | 2026-10-21 |
| pytest-html, `BaseReport` (dossier créé à la construction, écriture par `open("w")`, `user_properties` jamais lu), par Context7 puis lecture de `pytest_html/basereport.py` 4.2.0 | https://github.com/pytest-dev/pytest-html/blob/master/src/pytest_html/basereport.py | 2026-10-21 |
| pytest-html 4.2.0, publiée le 19/01/2026 (piwheels, DepScope), par WebSearch | https://www.piwheels.org/project/pytest-html/ | 2026-10-21 |
| uv, « Environment variable files » (l'environnement prime sur `--env-file`), par Context7 | https://docs.astral.sh/uv/concepts/configuration-files | 2026-10-21 |
