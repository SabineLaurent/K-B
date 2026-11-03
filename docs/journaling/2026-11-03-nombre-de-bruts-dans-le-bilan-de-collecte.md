# Le nombre de bruts écrits dans le bilan de `kb collect`

- Date : 2026-11-03
- Branche : `feat/collect-summary-file-count`
- Issue : aucune (demande de Sabine du 2026-11-03)
- Fichiers principaux : `src/k_b/etl/extract.py`, `src/k_b/commands/collect_command.py`
- Suite de : [2026-10-29-retour-console-sans-tableau.md](2026-10-29-retour-console-sans-tableau.md)

## Le pourquoi

`kb collect` finit par une ligne par source : `cisa_kev: ok`. Ce `ok` dit que la source n'a pas
échoué, pas ce qu'elle a rapporté. Une source qui n'a rien de neuf et une source qui a écrit six
pages affichaient la même ligne. Le nombre existait déjà, mais seulement au journal (décision du
2026-10-29, #359). Sabine le veut sur la ligne du bilan, pour qu'une collecte se lise source par
source, en démo et dans la capture de l'annexe E1 c1.8 :

```
tldr_ai: ok (6 raw files)
cisa_kev: ok (1 raw file)
arxiv_cscr_x_csai: ok (0 raw files)
github_most_forked: failed (HTTPStatusError)
zotero: skipped (KB_ZOTERO_DIR not set)
```

## Le comment

### 1. Le nombre existe déjà : `collect_one_source` le rend

`collect_one_source` (`src/k_b/etl/extract.py`) écrit le brut d'une source et rend combien de
fichiers il a écrits. Trois cas :
- `fetch` rend `None` (« rien de neuf ») : 0 ;
- il rend des octets : 1 fichier ;
- il rend un dict de pages (tldr : un jour d'édition par page ; clips : un clip par page) : un
  fichier par page.

Avant ce changement, `collect_all_sources` ne s'en servait que pour la ligne de journal
`source 'cisa_kev' collected, raw files written: 1`. Rien n'est recompté : le bilan reprend ce
nombre.

### 2. Le résultat de la collecte le transporte

`src/k_b/etl/extract.py:41-50` :

```python
class CollectionOutcome(NamedTuple):
    errors_by_source: dict[str, Exception | None]
    state_error: OSError | None
    written_count_by_source: dict[str, int]
```

`CollectionOutcome` est ce que la collecte (`k_b.etl`) rend à la commande (`k_b.commands`). La
commande n'écrit rien elle-même : pour afficher le nombre, elle doit le recevoir. Un `NamedTuple`
est un tuple aux champs nommés. Le troisième champ est donc passé aux deux endroits qui
construisent le résultat (`extract.py:99` et `:100`).

### 3. Rempli seulement pour une source collectée

`src/k_b/etl/extract.py:90-92`, dans la branche `else` du `try` (exécutée seulement si
`collect_one_source` n'a pas levé d'erreur) :

```python
            last_collection_dates[source.name] = now
            errors_by_source[source.name] = None
            written_count_by_source[source.name] = written_count
```

Une source en échec n'a pas d'entrée dans `written_count_by_source` : sa ligne dit `failed (…)`.

### 4. Le bilan l'affiche, au singulier ou au pluriel

`src/k_b/commands/collect_command.py:69-74` :

```python
    for source_name, source_error in outcome.errors_by_source.items():
        if source_error is None:
            written_count = outcome.written_count_by_source[source_name]
            print(f"{source_name}: ok ({describe_count(written_count, 'raw file')})")
        else:
            print(f"{source_name}: {describe_failure(source_error)}")
```

`describe_count` (`src/k_b/commands/batch_summary.py`) donne `1 raw file` ou `0 raw files`,
`6 raw files`. La même fonction écrit déjà `collection started: 17 sources selected`. La
recherche `[source_name]` ne peut pas manquer : une source sans erreur a toujours son nombre (§ 3).

### 5. `describe_outcome` devient `describe_failure`

`src/k_b/commands/collect_command.py:127-129` :

```python
def describe_failure(error: Exception) -> str:
    """Describe a failure, of a source or of the state: failed with the type of its error."""
    return f"failed ({type(error).__name__})"
```

Avant, `describe_outcome` rendait aussi `ok` quand l'erreur valait `None`. Le `ok` s'écrit
maintenant dans la boucle (§ 4), et ses deux appels lui passent une vraie erreur (une source en
échec, `collection_state`). Sa branche `ok` serait restée du code mort : elle est retirée, son type
se resserre à `Exception` (`mypy --strict` le vérifie), et son nom dit ce qu'elle fait désormais
(constat de `/code-review`). `kb write-tops` garde sa propre `describe_outcome`, qui n'est pas
touchée.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Format de la ligne | `ok (6 raw files)`, choisi par Sabine : mêmes parenthèses que `failed (…)` et `skipped (…)` | `ok, 6 raw files written`, aligné sur `kb write-tops` ; garder `ok` seul (décision du 29/10) |
| Où porter le nombre | un dict à part, `written_count_by_source` (la forme de `raw_file_counts` de #291) | un résultat par source (erreur ou nombre) dans un seul dict : plus juste en type, mais il réécrit les 17 assertions de tests sur `errors_by_source`, hors besoin |
| Une source en échec | pas de nombre, ligne `failed (…)` inchangée (demande de Sabine) | le nombre de pages écrites avant l'échec : jamais donné, déjà avant #291 |
| Décision du 29/10 | revirement écrit dans l'ADR du 2026-11-03, qui le dit | la changer sans le dire |

Imposé par une consigne du dépôt : le test rouge montré avant le code, les docstrings des
définitions publiques du pipeline tenues à jour (`.claude/rules/code.md`).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : 11 tests rouges, dont `AttributeError: 'CollectionOutcome' object has no attribute 'written_count_by_source'` et `- working: ok (1 raw file)` / `+ working: ok` | Les tests mesurent bien le changement demandé, pas autre chose. |
| `test_the_outcome_gives_the_raw_files_written_by_each_source_collected` (`tests/etl/test_extract.py:319`) → `{"working": 1, "unchanged": 0, "scraped": 2}` | Un fichier, rien de neuf et deux pages sont comptés comme au journal ; la source en échec est absente. |
| `test_collect_says_how_many_raw_files_each_source_collected_wrote` (`tests/commands/test_collect_command.py:348`) | Dans une même collecte : `ok (0 raw files)` (le cas qui a fait naître le besoin), `ok (1 raw file)` au singulier, `ok (2 raw files)` pour deux pages, et `failed (ConnectionError)` inchangé. |
| Les 8 sorties attendues de `test_collect_command.py` passées à `ok (1 raw file)` | Zotero, les clips, GH Archive, `KB_COLLECT_ONLY` et l'état non écrit gardent leur bilan, avec le nombre en plus. |
| `uv run pytest` : 3 251 passés ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre ne lisait l'ancienne forme. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `1 raw file` et pas le nombre d'items ?** La collecte ne lit pas ce qu'elle écrit :
   elle stocke le brut tel que reçu. Les items sont comptés à l'import (`kb import`, ligne
   `N raw read, N written…`). Voir `extract.py`, `collect_one_source`.
2. **Que veut dire `0 raw files` ?** La source a répondu « rien de neuf » (`fetch` rend `None`).
   Elle a réussi : sa date de dernière collecte avance (`extract.py:90`).
3. **Pourquoi tldr affiche-t-il plusieurs fichiers ?** Une source à pages écrit un fichier par
   page dans un dossier de collecte : pour tldr, un jour d'édition par page.
4. **Une source qui échoue au milieu de ses pages ?** Les pages déjà écrites restent dans `raw/`,
   mais la ligne dit `failed (…)` sans leur nombre, comme avant (limite écrite dans l'ADR).
5. **Pourquoi ne pas avoir fusionné erreurs et nombres dans un seul dict ?** Ce serait plus juste
   en type, mais il fallait réécrire 17 assertions et le calcul du code de sortie, sans gain pour
   le besoin.

## Zones non vérifiées

- La sortie réelle de `kb collect` sur les 17 vraies sources n'a pas été relancée : seules les
  sources de test l'ont été. La capture de l'annexe E1 c1.8 la montrera.

## Ce qui reste

- Le nombre d'items par source reste à l'import, pas au bilan de collecte : voulu, la collecte ne
  lit pas ce qu'elle stocke.
- Les docs datées (`docs/2026-10-04-flux-donnees.md`, `docs/2026-10-26-collecte-reelle.md`)
  gardent l'ancien `ok` : ce sont des instantanés, non modifiés.
