# Roder la collecte sur données réelles

- **Date** : 2026-10-21
- **Branche** : `test/collect-real-sources`
- **Issue** : #25
- **Fichiers principaux** :
  - `tests/e2e/test_real_sources.py` ;
  - `tests/conftest.py` ;
  - `tests/test_e2e_selection.py` ;
  - `docs/2026-10-21-collecte-reelle.md` (le compte rendu) ;
  - `docs/registre-traitements.md` (étape 10 de la procédure de tri) ;
  - `docs/ADR/journal-decisions-projet.md` (entrée du 2026-10-21) ;
  - `MEMORY.md`.

La liste de commits injectée au lancement de cette note remonte jusqu'aux PR déjà fusionnées
(#250 à #287). Seuls les six commits de la branche (`cf7faa6` à `6b76976`) relèvent de #25 : les
autres ne sont pas couverts ici, ils ont chacun leur note.

## Le pourquoi

Les tests unitaires de K-B tournent sur des fixtures. Une fixture part d'un exemple réel, mais
elle ne dit pas comment une source se comporte aujourd'hui. #25 est la première exécution de bout
en bout de `kb collect` et de `kb import` sur les dix vraies sources, au premier temps (le Mac,
sans conteneur).

Le critère de l'issue demande :
- trois exécutions complètes, avec les codes de sortie attendus ;
- de vrais clips et le top des dépôts les plus forkés ;
- les lignes extraites par les deux requêtes SQL (Zotero, GH Archive) ;
- les sorties gardées hors de la rotation des journaux, et un compte rendu daté.

Le 2026-10-21, Sabine y a ajouté **un test de bout en bout par source**, marqué `e2e`. Ces tests
pourront être rejoués tels quels au deuxième temps (conteneurs, #200) et au troisième (un job sur
Azure Container Apps). Ils comptent pour les compétences C17, C18, C19 et C1 ; le compte rendu
interprété, pour C9 et C10.

Aucun code de `src/` n'a changé. La branche ajoute des tests, leur exclusion de la CI et de la
documentation.

## Le comment

### 1. Un test, dix sources

Le test est paramétré par la liste des sources telle que le code la déclare :

```python
@pytest.mark.parametrize("source_name", [kind.folder_prefix for kind in SOURCE_KINDS])
```
(`tests/e2e/test_real_sources.py:161`)

Les identifiants des tests sont les noms des dossiers de sources : `cisa_kev`,
`arxiv_cscr_x_csai`, `tldr`… Une source ajoutée à `SOURCE_KINDS` reçoit donc son test d'office.
Si le test ne sait pas ce qu'elle doit apporter, il échoue **avant** le moindre appel réel
(`is_expected`, l. 164).

Le déroulé de chaque test est le même :
1. `kb create-db` ;
2. `KB_COLLECT_ONLY=<source> kb collect` ;
3. `kb import` ;
4. les vérifications : code 0 de chaque commande, aucun rejet au journal d'import, aucune ligne
   WARNING ou ERROR, et ce qui est arrivé en base, selon le type de source :
   - au moins un item de la bonne sorte, pour une source d'items ;
   - un relevé dans le brut et aucun item, pour les tops ;
   - des lignes de `trend`, pour GH Archive.

### 2. Chaque code de sortie est lu juste après sa commande

```python
    create_db_exit_code = run_kb("create-db", console_dir)
    assert create_db_exit_code == ExitCode.SUCCEEDED
    with monkeypatch.context() as collect_patch:
        collect_patch.setenv(COLLECT_ONLY_VARIABLE, source_name)
        collect_exit_code = run_kb("collect", console_dir)
    assert collect_exit_code == ExitCode.SUCCEEDED
```
(`tests/e2e/test_real_sources.py:193-198`)

Deux raisons :
- **le coût** : si `create-db` échoue, rien n'est collecté. Pour `gh_archive`, cela évite une
  requête BigQuery réelle pour rien (1er passage de la revue, constat 2) ;
- **une seule source** : `KB_COLLECT_ONLY` n'est posée qu'autour de `collect`, par
  `monkeypatch.context()`. Le test retire d'abord celle du terminal (l. 182). Avec la clé
  BigQuery présente, sans ce filtre, `gh_archive` tournerait dans chacun des dix tests.

`kb` tourne dans un sous-processus. C'est le vrai `kb`, avec son journal, ses codes de sortie et
son gestionnaire de SIGTERM, comme dans un conteneur. Appeler `main()` dans le processus de
pytest aurait mêlé les gestionnaires de journal des deux (`tests/test_cli.py:543`).

### 3. Le jeton GitHub n'est jamais dans une variable du test

```python
    with subprocess.Popen(  # noqa: S603 — runs the kb of this interpreter, fixed arguments
        [str(KB_PATH), command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
```
(`tests/e2e/test_real_sources.py:88-93`)

Il n'y a pas d'argument `env=` : le sous-processus hérite de l'environnement du processus de
test. Les variables propres au test, `KB_DATA_DIR` et `KB_COLLECT_ONLY`, y sont posées par
`monkeypatch.setenv` (l. 179, 196).

Pourquoi : quand un test échoue, pytest affiche les variables locales des frames si on le lance
avec `-l`, et il détaille un appel écrit dans un `assert`. Une variable `environ` aurait contenu
`KB_GITHUB_TOKEN` (2e passage de la revue, constat 6). Pour la même raison, les `assert` portent
sur des codes déjà calculés, jamais sur `run_kb(...)` lui-même.

### 4. Un délai dépassé arrête kb proprement

```python
def stop(process):
    """SIGTERM, then SIGKILL past STOP_TIMEOUT_SECONDS; what the process printed."""
    process.terminate()
    try:
        return process.communicate(timeout=STOP_TIMEOUT_SECONDS)
```
(`tests/e2e/test_real_sources.py:104-108`)

`subprocess.run(timeout=…)` tue le processus par SIGKILL. Ni le gestionnaire de SIGTERM de kb ni
le `TemporaryDirectory` de la copie Zotero ne tournent alors, et la copie entière de
`zotero.sqlite` resterait dans le dossier temporaire du système. Avec `Popen`, un délai dépassé
envoie d'abord SIGTERM, comme `docker stop` ; SIGKILL ne vient qu'après 30 s. Ce qui a été
affiché avant est écrit dans `console/`, puis l'exception repart.

### 5. Un test n'emporte aucune donnée personnelle

```python
    try:
        collect_and_import(source_name, data_dir, console_dir, monkeypatch)
    finally:
        # A failed assert, a timeout or a Ctrl-C deletes as well.
        delete_all_but_logs(data_dir)
```
(`tests/e2e/test_real_sources.py:184-187`)

`delete_all_but_logs` (l. 119) efface tout le dossier de données sauf `logs/` :
- le brut, dont l'extrait Zotero avec ses auteurs et les copies des clips ;
- la base, avec ses `-wal` et `-shm` (la base est en WAL) ;
- les journaux d'import, dont `source_item_id` est l'URL d'un clip.

Le `finally` couvre aussi un `assert` raté, un délai dépassé et un Ctrl-C. Ce qui reste
(`console/`, `data/logs/`), combien de temps (les 3 dernières sessions de pytest) et ce que ces
fichiers peuvent contenir est écrit à l'étape 10 de la procédure de tri du registre.

### 6. La CI ne les lance pas

```python
    if E2E_MARKER in MARKER_NAME.findall(config.option.markexpr):
        return
    deselected = [item for item in items if item.get_closest_marker(E2E_MARKER)]
```
(`tests/conftest.py:42-44`)

Le hook `pytest_collection_modifyitems` écarte les tests marqués `e2e`, sauf si l'expression
`-m` nomme `e2e`. Il les signale par `config.hook.pytest_deselected` (l. 47) : `uv run pytest`
les compte « 10 deselected ».

Le nom est cherché par la règle `ident` de la grammaire de pytest (`MARKER_NAME`, l. 28, recopiée
de `_pytest/mark/expression.py:10`). Ainsi `nightly-e2e` ou `e2e.slow` comptent comme un seul
nom, et non comme `e2e` : la 2e revue avait montré qu'avec `\w+`, `-m "not nightly-e2e"` lançait
les dix tests, BigQuery compris. `tests/test_e2e_selection.py` le prouve en lançant pytest dans
un sous-processus. On vérifie le code de retour 5 (aucun test collecté) et le compte
« deselected » ; avec `-m e2e`, les dix identifiants, dans l'ordre de `SOURCE_KINDS`.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un test paramétré par `SOURCE_KINDS` | une source nouvelle a son test d'office | dix tests écrits à la main : dix copies du même déroulé |
| Exclusion dans `tests/conftest.py` | sans toucher à `pyproject.toml` | `addopts = "-m 'not e2e'"` : modification que Sabine doit taper, sans gain (plan de #25) |
| Interface `-m e2e` | celle de la mission et de l'ajout du 21/10 | `--run-e2e` : change la commande décidée ; l'API `Expression` de pytest : privée, changée en 8.x (2e revue, constat 7) |
| Source sans sa variable : sautée | en conteneur, Zotero et les clips restent sur le Mac | en échec : chaque rejeu en conteneur serait rouge |
| Sans jeton GitHub : les tests tournent | décision du plan de #25 ; 60 requêtes par heure suffisent à un test | sautés : ils ne tourneraient jamais en conteneur sans le secret |
| Un seul avertissement admis, celui du quota sans jeton | il suit la décision précédente | aucune exception : sans jeton, le test serait rouge à coup sûr ; une liste ouverte : un cas nouveau passerait sans décision |
| Trois exécutions le même jour, dans un seul dossier | tester l'incrémental et les doublons (décision de Sabine) | trois dossiers neufs : trois premières collectes identiques, trois requêtes BigQuery |
| `kb write-tops` lancé, dans le coffre de développement | décision de Sabine : ce coffre est ignoré par git, ce n'est pas le coffre Obsidian de l'utilisatrice | ne pas le lancer : la dernière puce du critère serait restée sans objet |
| Effacer `data/` sauf `logs/`, dans un `finally` | aucune donnée personnelle laissée derrière un test | `tmp_path_retention_policy` : demande `pyproject.toml` |

Chaque constat des revues porte sa décision dans la PR : « decided by time-knight, delegation of
Sabine of 2026-10-15 ».

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` → `1961 passed, 10 deselected` | la CI ne lance aucun test e2e |
| `uv run pytest -m e2e --collect-only -q` → 10 identifiants, `1958 deselected` | un test par source, et seulement eux |
| `tests/test_e2e_selection.py` : `not nightly_e2e`, `not nightly-e2e`, `not e2e.slow` | un marqueur qui contient « e2e » ne lève pas l'exclusion |
| 10 tests e2e verts, de 08:43 à 08:46 UTC | chaque source tient de bout en bout dans une base vide |
| Exécutions 1, 2 et 3 : `collect` 0, `import` 0, 0 rejet | le critère « trois exécutions complètes » |
| 3 022 items à l'exécution 1, soit la somme des dix tests | collecter les sources ensemble ne change pas ce que chacune apporte |
| Exécutions 2 et 3 : 21 papiers écartés, 0 item écrit | l'incrémental et les doublons, le même jour |
| `zotero: 5 documents, 6 highlights extracted` ; `gh_archive: … 49 rows` | les lignes des deux requêtes SQL sont dans la sortie gardée |
| `kb write-tops` : 0, 2 fiches, 2 relevés supprimés par top ; brut copié avant | la dernière puce du critère |
| Relance des 9 sources gratuites : chaque dossier ne garde que `data/logs/` et `console/`, celui du test rouge compris | l'effacement passe aussi sur un échec |
| Relance d'arXiv : `TimeoutError` après 30 s, deux fois ; `curl` → HTTP 429 en 0,33 s ; vert 27 min plus tard (551 papiers, 3,9 s) | un rouge e2e peut venir de la source et non de K-B (voir le compte rendu) |

## Ce que tu dois pouvoir défendre

1. **Pourquoi des tests qui appellent les vraies sources, s'ils ne tournent pas dans la CI ?**
   Ils prouvent que la chaîne tient sur les données d'aujourd'hui, ce qu'une fixture ne peut pas
   faire. La même commande, `uv run pytest -m e2e`, se rejoue sur le Mac, en conteneur et sur
   ACA. Hors CI, parce qu'ils demandent des clés, du réseau et une requête BigQuery réelle
   (`tests/conftest.py:38`).
2. **Que se passe-t-il si un test échoue au milieu ?** Le `finally` efface le dossier de données
   sauf `logs/` (`test_real_sources.py:185-187`). Sur un délai dépassé, kb reçoit d'abord SIGTERM
   pour nettoyer sa copie Zotero (`stop`, l. 104). La console de la commande est gardée.
3. **Où est la sécurité ?**
   - Le jeton n'est dans aucune variable du test (`run_kb`, l. 81).
   - Aucune donnée personnelle ne reste après un test (`delete_all_but_logs`, l. 119).
   - `gh_archive` ne tourne que dans son propre test (`KB_COLLECT_ONLY`, l. 196).
   - `/security-review` n'a rien trouvé de HIGH ou MEDIUM.
   - Limite acceptée : chaque `kb` reçoit tout l'environnement, comme un `kb` lancé à la main.
4. **Pourquoi un rouge e2e n'est-il pas forcément un défaut de K-B ?** Le test dépend de la
   source réelle. arXiv a dépassé le délai deux fois de suite et refusé une requête `curl` par un
   429. kb a traité le cas comme prévu : la source échoue sous son nom, sa date reste, la commande
   sort en 1. Après 27 min sans requête, la relance était verte, sans rien changer au code. Un
   rouge se lit donc d'abord dans `console/collect.err`.
5. **Pourquoi pas `addopts` dans `pyproject.toml` ?** Ce fichier ne change pas sans une demande
   expresse de Sabine. Le hook de `conftest.py`, corrigé par la grammaire de pytest, fait la même
   chose et sa preuve est un test.

## Zones non vérifiées

- **Le chemin SIGTERM puis SIGKILL de `run_kb`** n'a pas été exercé en vrai : aucune commande n'a
  atteint les 900 s. Pas de test automatique non plus.
- **Les cas « not nightly-e2e » et « not e2e.slow »** n'ont pas été vus rouges avant la
  correction ; le relecteur, lui, avait constaté le défaut en le lançant.
- **La cause du délai d'arXiv** n'est pas établie : limitation de débit probable, d'après le 429
  de la mesure, et non prouvée. Le rythme demandé par arXiv (une requête toutes les 3 s) a été
  tenu.
- **Le rejeu en conteneur et sur ACA** n'a pas été essayé : #200 et le troisième temps.
- **L'effacement de `data/`** a été vérifié à la main, sur une relance, et non par un test
  automatique.

## Ce qui reste

- Le rejeu des tests e2e en conteneur, avec les dépendances de développement dans l'image (#200).
- Voir comment kb traite un 429 d'arXiv (en-tête `Retry-After`), et si une nouvelle tentative
  avec attente sur une erreur réseau passagère se justifie. Ce n'est pas fait dans #25 : cela
  changerait un comportement documenté sur une seule observation.
- Une collecte le lendemain (fenêtre GH Archive due, nouvelles éditions TLDR) et une collecte
  après plusieurs jours manqués : non mesurées ici.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| pytest, « Control skipping of tests according to command line option » (hook `pytest_collection_modifyitems`), par Context7 | https://github.com/pytest-dev/pytest/blob/main/doc/en/example/simple.rst | 2026-10-21 |
| pytest, « Registering custom markers » (`pytest_configure`, `addinivalue_line`), par Context7 | https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/writing_plugins.rst | 2026-10-21 |
| pytest 9.1.1, grammaire des expressions `-m` (règle `ident`), lue dans le paquet installé | `_pytest/mark/expression.py:10` | 2026-10-21 |
| uv, « Environment variable files » (l'environnement prime sur `--env-file`), par Context7 | https://docs.astral.sh/uv/concepts/configuration-files | 2026-10-21 |
| arXiv, « Terms of Use for arXiv APIs » (une requête toutes les 3 s, une seule connexion), par WebSearch puis WebFetch | https://info.arxiv.org/help/api/tou.html | 2026-10-21 |
| Volumes et quota BigQuery de K-B | [`docs/bigquery.md`](../bigquery.md) | 2026-10-21 |
