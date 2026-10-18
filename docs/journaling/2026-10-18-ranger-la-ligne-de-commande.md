# Ranger la ligne de commande : une porte mince, chaque réglage dans sa couche

- **Date** : 2026-10-18
- **Branche** : `refactor/thin-command-line`
- **Issue** : #247
- **Fichiers principaux** : `src/k_b/cli.py`, `src/k_b/commands/` (10 fichiers),
  `src/k_b/data_api/settings.py`, `src/k_b/core/api_keys.py`, `src/k_b/etl/collected_sources.py`,
  `tests/test_module_dependencies.py`
- **Série** : même geste que [le rangement de l'API IA par rôle](2026-10-18-ranger-l-api-ia-par-role.md)
  (#242). Le code déplacé vient de [choisir les sources collectées](2026-10-18-choisir-les-sources-collectees.md)
  (#201) et de [nommer les codes de sortie](2026-10-18-nommer-les-codes-de-sortie-de-kb.md) (#193) :
  ces deux notes sont des instantanés. Ce qui y est appelé `read_collect_only`, `read_serve_settings`
  ou `read_api_keys` (`src/k_b/cli.py`) est devenu une lecture de couche (`*_or_refusal`) suivie de
  `value_or_log_refusal` (section 2.4).

## 1. Le pourquoi

Sur `main` 4ebff3a, `src/k_b/cli.py` faisait 700 lignes, le plus gros fichier de K-B. Il faisait deux
métiers à la fois. Le premier est celui d'une **porte** : lire la commande tapée, lire l'environnement
du lancement, ouvrir le journal, s'arrêter sur SIGTERM, traduire un résultat en texte et en code de
sortie. Le second n'appartient pas à la porte : il dit quels hôtes et quel port `kb serve` accepte, ce
qu'est une clé de client valide, quelles sources `KB_COLLECT_ONLY` peut choisir. Ces règles-là
appartiennent à la couche qui les porte : l'API de données, le vocabulaire commun, la collecte.

Trois issues allaient encore toucher ce fichier : #63 (jeton GitHub), #200 et #209 (`kb digest`, une
sixième commande). Le ranger avant elles évite qu'elles l'allongent. La décision de Sabine du 18/10 :
« cli mince et chaque réglage dans sa couche ». C'est un **déplacement seul** : aucune aide, aucun
message, aucun code de sortie ne change, et la preuve en est donnée en section 4.

## 2. Le comment

### 2.1 La porte : `cli.py` aiguille, `commands/` exécute

`cli.py` ne garde que trois fonctions : `main`, `describe_exit_codes` et l'aiguillage.

```python
def run_command(command: str, data_dir: Path) -> int:
    if command == "create-db":
        return run_create_db(data_dir)
    if command == "import":
        return run_import(data_dir)
    if command == "serve":
        return run_serve(data_dir)
    return run_collect(data_dir)
```
(`src/k_b/cli.py:105-112`)

Chaque `run_*` vit dans son module de `commands/` : `collect_command.py`, `create_db_command.py`,
`import_command.py`, `serve_command.py`, `openapi_command.py`. Le suffixe `_command` n'est pas
décoratif : `import` est un mot réservé de Python, un fichier `import.py` ne s'importerait pas.
Ce que les commandes partagent est écrit une fois, dans quatre modules : `exit_codes.py`
(`ExitCode`), `sigterm.py` (l'arrêt propre), `run_log.py` (le journal du lancement) et
`environment.py` (`KB_DATA_DIR` et `KB_LOG_TO_FILE`, lus avant que le journal soit ouvert).
`commands/__init__.py` est vide (`code.md` : « `__init__.py` reste vide, sauf raison écrite »).

Le point d'entrée `kb = "k_b.cli:main"` de `pyproject.toml` ne change pas : `main` est resté dans
`cli.py`.

### 2.2 Chaque réglage dans sa couche, lu sous la forme « valeur ou motif du refus »

Une couche ne journalise pas ses refus : elle les **rend**. Exemple des réglages de `kb serve` :

```python
def read_serve_settings_or_refusal(environ: Mapping[str, str]) -> ServeSettings | str:
```
(`src/k_b/data_api/settings.py:35`)

La fonction rend soit les réglages (`ServeSettings`, une dataclass figée), soit une phrase qui dit
pourquoi une variable est refusée. Le corps est celui de `main`, à une ligne près : là où il y avait
`logger.error("%s", refusal)` puis `return None`, il y a `return refusal`. Même forme pour les clés
(`read_api_keys_or_refusal`, `src/k_b/core/api_keys.py:17`) et pour le choix des sources
(`read_collect_only_or_refusal`, `src/k_b/etl/collected_sources.py:49`). Le modèle existait déjà
dans le dépôt : `read_settings_or_refusal` de `ai_api/connectors/data_api_settings.py`.

Pourquoi rendre le refus au lieu de le journaliser sur place ? Pour garder le nom du journal. Chaque
ligne de `kb` porte le nom `k_b.cli` (section 2.3). Si `data_api/settings.py` journalisait lui-même,
la ligne porterait `k_b.data_api.settings`, et le test `test_cli.py` qui lit `ERROR k_b.cli:`
casserait : ce serait un changement de comportement.

Les clés vont dans `core/` et non dans `data_api/` : l'API IA ne peut importer que `ai_api`, `items`
et `core` (`tests/test_module_dependencies.py`), et #156 prévoit un module commun des clés. Les poser
dans `core/` dès maintenant évite un second déplacement.

### 2.3 Un seul nom de journal pour toute la porte

```python
LOGGER_NAME = "k_b.cli"
```
(`src/k_b/commands/run_log.py:15`)

Chaque module de la porte qui journalise prend `logging.getLogger(LOGGER_NAME)`, et non
`getLogger(__name__)`. Avec `__name__`, la ligne écrite par `serve_command.py` aurait porté
`k_b.commands.serve_command` : un journal lu par un humain ou par Log Analytics aurait changé sans
que le code change de sens. La seule exception est `logging_to`, qui prend le journal racine,
`logging.getLogger()` sans nom (`run_log.py:56`) : c'est là qu'il pose ses gestionnaires, pour
recevoir les lignes de tous les modules.

### 2.4 La porte journalise le refus, puis décide de s'arrêter

```python
def value_or_log_refusal[ValueT](value_or_refusal: ValueT | str) -> ValueT | None:
    """The value read by a layer, or None after logging why the layer refused it; the caller
    decides to stop. The value read is never a str: a str is the refusal."""
    if isinstance(value_or_refusal, str):
        logger.error("%s", value_or_refusal)
        return None
    return value_or_refusal
```
(`src/k_b/commands/run_log.py:71-77`)

Trois lectures avaient la même enveloppe : appeler la couche, journaliser une `str`, rendre `None`.
À la troisième occurrence, `code.md` demande de factoriser : une seule fonction, générique
(`[ValueT]`, la syntaxe de Python 3.12 que le dépôt emploie déjà dans `read_each_entry`). L'appel
est une affectation, d'où le nom, qui dit ce qui revient :

```python
    api_keys = value_or_log_refusal(read_api_keys_or_refusal(os.environ))
    settings = value_or_log_refusal(read_serve_settings_or_refusal(os.environ))
    if api_keys is None or settings is None:
        return ExitCode.NOT_STARTED
```
(`src/k_b/commands/serve_command.py:22-25`)

L'ordre est celui de `main` : les clés, puis les réglages, **tous deux lus avant le test**. Si les
deux sont refusés, les deux refus sont journalisés, les clés d'abord. `kb serve` échoue fermé : rien
ne démarre tant qu'une lecture est refusée.

La limite est écrite dans la docstring : `isinstance(..., str)` ne sait pas distinguer un refus d'une
valeur qui serait elle-même une `str`. Aucun lecteur n'en a aujourd'hui : les succès sont un `dict`,
`ServeSettings` et `CollectOnly`.

### 2.5 Le choix des sources reçoit ses sortes, il ne les importe pas

```python
def list_collected_sources(
    collect_only: CollectOnly, environ: Mapping[str, str], kinds: Sequence[SourceKind]
) -> list[Source]:
```
(`src/k_b/etl/collected_sources.py:91-93`)

Sur `main`, ces fonctions lisaient la variable de module `SOURCE_KINDS` de `cli.py`. Elles la
reçoivent maintenant en paramètre (`kinds`, le nom et le type de `list_sources` et de
`read_raw_items`), et c'est `collect_command.py` qui la lit **au moment de l'appel**. Les tests de la
collecte remplacent `SOURCE_KINDS` par de fausses sources. Ils le font dans un seul module,
`collect_command`, là où le nom est lu :

```python
    monkeypatch.setattr(
        collect_command, "SOURCE_KINDS", collected_kinds(WorkingSource())
    )
```
(`tests/test_cli.py:99-101`)

Si `collected_sources.py` importait lui-même `SOURCE_KINDS`, chaque test devrait remplacer le nom
dans deux modules, et l'oubli d'un des deux lancerait les vraies sources, réseau compris.

`collected_sources.py` crée `ZoteroSource`, `ClippingSource` et `GhArchiveSource` : c'est donc un
module de **composition** d'`etl`, à côté de `source_kinds.py`, pas un module du pipeline. Le test
des dépendances le range ainsi (`ETL_COMPOSITION_MODULES`).

### 2.6 Le sens des imports, tenu par un test

```python
COMMAND_LINE_FORBIDDEN_MODULES = {"commands": {"cli"}} | {
    module: {"cli", "commands"} for module in ETL_COMPOSITION_MODULES
}
```
(`tests/test_module_dependencies.py:429-431`)

La porte est en haut : `cli` importe `commands`, `commands` importe les couches. Le test refuse les
imports qui remontent : `commands/` n'importe pas `cli`, et la composition d'`etl` n'importe ni `cli`
ni `commands`. Les autres couches (`core`, `database`, `data_api`, `ai_api`, le pipeline et les
sources d'`etl`) étaient déjà tenues par leurs listes d'imports permis. Le test a été prouvé par trois
mutations, faites sur une copie du dépôt (section 4).

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Forme de la porte | `cli.py` qui aiguille et un paquet `commands/` (décision de Sabine, 18/10) | Un paquet `cli/` dont `__init__.py` porte `main` : `__init__.py` reste vide (`code.md`). Un seul `cli.py` sans les règles : environ 470 lignes, que `kb digest` allongerait |
| Nom du paquet | `commands/` | `cli_commands/` : répète `cli` |
| Nom des modules | `<commande>_command.py` | `collect.py`… : `import.py` est impossible (mot réservé) |
| Clés des clients | `core/api_keys.py` (décision de Sabine, 18/10) | `data_api/settings.py` : #156 aurait dû les redéplacer |
| Qui journalise un refus | la porte, sous `k_b.cli` | la couche elle-même, comme `llm_settings` : le nom de chaque ligne aurait changé |
| Nom des journaux | `LOGGER_NAME = "k_b.cli"` partout | `getLogger(__name__)` : `k_b.commands.<module>` dans chaque ligne |
| `SOURCE_KINDS` | passé en paramètre à `collected_sources` | importé par `collected_sources` : deux modules à remplacer par test |
| Enveloppe des refus | une seule, `value_or_log_refusal` (tri de la revue, time-knight) | trois copies : la règle de la troisième occurrence. Les noms `log_refusal` (ne dit pas qu'une valeur revient) et `unwrap_or_log_refusal` (« unwrap » n'est pas un mot de K-B) |
| Type du refus | une `str` | un type `Refusal` : aucun lecteur n'a une `str` pour succès (YAGNI), à poser s'il en arrive un |
| Variable de `main` | `command_parsers` (décision de Sabine, 18/10) | `commands` : le même mot que le paquet importé dans le fichier. `subparsers` : un mot d'argparse, pas de K-B |
| Test du sens des imports | ajouté (tri de la revue) | un `grep` seul : il ne tient pas dans la durée |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `kb --help` et l'aide des cinq commandes, enregistrées sur `main` 4ebff3a puis sur la branche : `diff` vide | aucune aide ne change |
| `uv run pytest -q` : 1757 passed (1756 sur `main`, plus le test du sens des imports) | aucun message, code de sortie ni comportement testé ne change |
| `diff` des listes de tests (`pytest --collect-only`), la clé aléatoire de `test_a_key_refused_is_never_quoted` remplacée par un repère : une seule ligne en plus | aucun test retiré |
| `git diff -U0 4ebff3a -- tests \| grep -E '^[-+] +assert'` : seulement `create_bigquery_client`, lu dans `collected_sources` | les tests ne changent que la cible des remplacements |
| Trois mutations sur une copie (un import de `cli` dans `commands/sigterm.py`, de `commands` dans `etl/collected_sources.py`, de `k_b.cli` dans `etl/source_kinds.py`) : le nouveau test échoue chaque fois | le test du sens des imports voit ce qu'il interdit |
| `git diff 4ebff3a -- pyproject.toml` : vide | le point d'entrée `kb` ne change pas |
| `/security-review` : aucun constat ; chaque contrôle (hôte IPv4, port, hôtes permis, clés) comparé ligne à ligne avec `main` | la forme `valeur \| refus` ne relâche aucun contrôle |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi une couche rend-elle son refus au lieu de le journaliser ?** Pour séparer le métier de
   la présentation : la couche dit *si* et *pourquoi* une valeur est refusée, la porte décide quoi en
   faire (journal, code de sortie 2). Concrètement, le nom `k_b.cli` reste dans chaque ligne
   (sections 2.2 et 2.3).
2. **Que se passe-t-il si les clés et l'hôte de `kb serve` sont tous deux faux ?** Les deux lectures
   ont lieu avant le test : deux lignes d'erreur, les clés d'abord, puis le code 2, et le serveur ne
   démarre pas (`serve_command.py:22-25`).
3. **Une clé peut-elle finir dans le journal ?** Non : aucun motif de refus de
   `core/api_keys.py` n'insère la clé. Il cite le nom de la variable, échappé par `quote_value`, et la
   longueur de la clé. Les clés lues sont des `SecretStr`.
4. **Comment sait-on que rien n'a changé ?** Par trois `diff` vides et les tests : l'aide, la liste des
   tests (un seul ajout), `pyproject.toml`. Puis 1757 tests verts, qui lisent les messages exacts et les
   codes de sortie (section 4).
5. **Pourquoi `etl/collected_sources.py` et non `etl/extract.py` ?** `extract.py` est le pipeline : il
   ne doit connaître aucune source (`test_no_module_of_the_pipeline_imports_the_sources_or_the_composition`).
   Créer `ZoteroSource` est un acte de composition, comme déclarer `SOURCE_KINDS`.

## 6. Zones non vérifiées

- Le rendu des journaux en conteneur (`docker compose logs`) n'a pas été relancé : la preuve du nom
  `k_b.cli` vient des tests, qui lisent la sortie d'erreur et `logs/kb.log`.
- `kb serve` n'a pas été lancé à la main ; son démarrage est vérifié par les tests de
  `tests/data_api/test_serve.py`, qui remplacent `uvicorn.run`.

## 7. Ce qui reste

- Les deux enveloppes de l'API IA (`read_llm_settings`, `read_data_api_settings`) gardent leur copie
  du même motif. `value_or_log_refusal` rejoindra `core/` quand elles le rejoindront : #156 ou une
  issue à part.
- Le préfixe des clés de l'API IA (`KB_AI_API_KEY_`), et `KB_API_KEY_AI_DIGEST` écrit en dur dans
  `ai_api/connectors/data_api_settings.py`, restent à #156.
- La paire source → variable écrite trois fois et la liste des sources permises, relevées par la
  revue de #201, restent hors de ce rangement.
- Des tests unitaires des trois modules déplacés : ils sont couverts aujourd'hui de bout en bout, par
  `cli.main`.
- Le routeur de l'API de données (#246) suit, dans la partie 3 de la mission.
