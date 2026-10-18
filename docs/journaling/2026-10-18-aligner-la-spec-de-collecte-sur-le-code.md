# Aligner la spec de collecte sur le code

- **Date** : 2026-10-18 (UTC)
- **Branche** : `docs/align-collection-spec`
- **Issue** : #64
- **Fichier** : `docs/specs-collecte.md`, seul fichier changé (4 commits `docs:`)
- **Notes liées** : [nommer les codes de sortie de kb](2026-10-18-nommer-les-codes-de-sortie-de-kb.md)
  (#193), [choisir les sources collectées](2026-10-18-choisir-les-sources-collectees.md) (#201),
  [collecter les clips du coffre Obsidian](2026-10-17-collecter-les-clips-du-coffre-obsidian.md) (#14)

## Le pourquoi

`docs/specs-collecte.md` est la doc que le jury lira pour E1. La revue certif du 17/10 laisse
vides trois de ses cases :
- la spec ne nomme pas le langage (C1, l. 19) ;
- elle ne spécifie pas l'entrée des clips en base (C1, l. 20) ;
- elle décrit une table d'auteurs qui n'existe pas (C3, l. 40).

L'issue #64 demande en plus trois choses que le code fait et que la spec ne disait pas, ou disait
mal :
- les codes de sortie nommés par #193 ;
- ce qui se passe quand chacune des neuf sources tombe en panne ;
- la puce arXiv.

Le principe du dépôt : une doc ne dit que ce que le code fait. Chaque phrase ajoutée a donc été
relue dans le code de `origin/main` (991a384), et aucun code n'a changé.

## Le comment

### 1. Les codes de sortie viennent d'une seule fonction

Le code de `kb collect` se décide en un endroit, `src/k_b/commands/collect_command.py:66-76` :

```python
    if outcome.state_error is not None:
        return ExitCode.FAILED
    if all(error is None for error in errors):
        return ExitCode.SUCCEEDED
    if any(error is None for error in errors):
        return ExitCode.PARTIAL_FAILURE
    return ExitCode.FAILED
```

L'ordre compte : un état non écrit l'emporte sur tout le reste (1), même si chaque source a
réussi. Les dates ne sont pas sauvées, et la collecte suivante refera tout. La spec reprend cet
ordre dans une table (0, 1, 2, 4, 143), rangée comme `kb --help` les liste.

Le code 2 (`NOT_STARTED`) se décide ailleurs, avant toute collecte : `KB_DATA_DIR`
(`commands/environment.py`), `KB_LOG_TO_FILE` et le fichier de journal (`cli.py`), un état
invalide (`collect_command.py:41-43`), `KB_COLLECT_ONLY` refusée. `argparse` sort aussi en 2 par
lui-même, quand la commande est absente ou inconnue.

### 2. Une panne de source est rattrapée en un seul endroit

`src/k_b/etl/extract.py:45` rattrape toute `Exception` d'une source. La date n'avance qu'en cas
de succès (`extract.py:61`) :

```python
            last_collection_dates[source.name] = now
```

La spec l'écrit donc une fois, dans « Panne d'une source » (règles communes). Chaque source ne
dit ensuite que ses états propres, sur sa ligne « En cas de panne : ». Ce qui ne vaut que pour
certaines sources est dit avec sa portée. Le téléchargement (`http_download.py`) ne concerne que
tldr, arXiv, CISA KEV et GitHub : Zotero, les clips et GH Archive n'y passent pas.

### 3. Le délai de 30 s n'est pas une durée totale

`src/k_b/etl/http_download.py:43` :

```python
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
```

Ce `timeout` borne chaque opération réseau bloquante (la connexion, chaque lecture), pas le
téléchargement entier. La première rédaction disait « délai de 30 s dépassé » ; la revue l'a
relevé, et la spec dit maintenant que la durée totale n'est pas bornée.

### 4. arXiv lit sa page à la collecte

La puce du critère (« `read_papers` n'est appelée nulle part ») décrivait le code du 04/10.
Aujourd'hui, `src/k_b/etl/sources/arxiv.py:100` :

```python
        check_not_all_invalid(read_papers(raw_response))
```

Une page dont toutes les entrées sont invalides fait échouer la source (`all_items_invalid`) ; une
entrée invalide parmi des valides entre dans le brut, et l'import la rejette. La spec le disait
déjà. Le critère a été corrigé par un commentaire daté sur #64, et la spec n'a pas été réécrite
sur ce point.

### 5. Les auteurs sont une liste JSON, pas une table

`src/k_b/database/schema.sql:62-66` :

```sql
    -- The names, in arXiv's order.
    authors      TEXT
        CHECK (json_valid(authors) AND json_type(authors) = 'array'
            AND json_array_length(authors) > 0)
```

Les deux puces sur « un auteur lié une fois » et « un auteur sans item supprimé » décrivaient une
table qui a disparu. Elles sont remplacées par ce que fait le code : la liste est écrite telle
quelle, et une révision arXiv plus récente la remplace (`paper_writer.py`, `UPSERT_PUBLICATION`).
Seul arXiv remplit les auteurs d'un item, d'où « auteurs (arXiv) » à l'étape 2.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Citer le code dans la spec | Le module et la constante (`extract.py`, `ExitCode`) : la piste A renomme du code ce soir, et un numéro de ligne vieillit au premier changement. Les `fichier:ligne` sont dans la PR. | Les numéros de ligne dans la spec. |
| Retrait d'une ligne de catalogue | Décrit par ce qu'il fait, sans nom de fonction (consigne de la mission : `withdraw_absent` est renommée par la piste A). | Nommer la fonction. |
| Puce arXiv du critère, périmée | Corriger le critère par un commentaire daté (l'usage du dépôt, comme pour `KB_SOURCES`). | Réécrire la spec pour coller au critère : elle aurait décrit un code qui n'existe plus. |
| Clips | Garder l'agrégation déjà écrite par #14 et y renvoyer depuis la section Web Clipper. | La réécrire : elle concorde avec `schema.sql` et `clipping.py`. |
| Écart de tldr à la règle 1 | L'écrire comme constaté, non tranché, et le signaler dans la PR. | Le taire ; ou le trancher ici (c'est une question de code). |
| Date de l'en-tête et de la note | 2026-10-18, en UTC (`date -u`, règle 3 de `conventions.md` ; tranché par time-knight). | La date locale du 19/10. |
| Unités | « Mio » là où le code compte en `1024 * 1024`. | « Mo », faux de 4,9 % (constat de revue). |

## Preuve

| Commande ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -c "En cas de panne :" docs/specs-collecte.md` → 9 | une ligne par source codée ; la puce commune ne porte pas la chaîne |
| `grep -n "KB_DATA_DIR" docs/specs-collecte.md` → l. 34 (table, code 2) | les deux cas de `KB_DATA_DIR` sont décrits |
| `grep -n "la rejette et la journalise\|KB_SOURCES\|Un auteur qui n'a plus d'item\|Un nom répété dans les auteurs" docs/specs-collecte.md` → rien | les phrases fausses sont parties |
| `uv run python -c "import csv,io;print(list(csv.DictReader(io.StringIO('a,b\n1,\x002\n',newline=''))))"` → `[{'a': '1', 'b': '\x002'}]` | un octet NUL ne lève pas `csv.Error` en Python 3.13 |
| `uv run python -c "import csv;print(csv.field_size_limit())"` → `131072` | la limite citée pour `csv.Error` |
| `kb nope` et `kb` sans commande → code 2 (essai du relecteur du plan) | le refus d'`argparse` sort en 2 |
| `uv run pytest -q` → 1769 passed | rien du code n'a bougé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un code 4 distinct de 1 ?** Avec 4, les sources réussies sont acquises et l'état
   est écrit ; avec 1, rien n'est acquis (aucune source réussie, ou état non écrit). Un job en
   conteneur ne voit que ce code (`collect_command.py:66-76`).
2. **Une source en panne bloque-t-elle les autres ?** Non : `extract.py:45` rattrape l'erreur, et
   seule la date de cette source reste. Exception : le Ctrl-C (`KeyboardInterrupt`), qui n'est pas
   une `Exception` et arrête tout.
3. **Une panne fait-elle perdre des données ?** Une source qui a une fenêtre (arXiv, alertes,
   tldr, GH Archive) la redemande à la collecte suivante. Le classement des plus étoilés n'en a
   pas : l'instantané d'un jour manqué est perdu, et la spec le dit.
4. **Où sont les auteurs ?** Ceux d'arXiv dans `publication.authors`, en liste JSON. Ceux de
   Zotero et des clips n'entrent pas en base (minimisation, registre des traitements).
5. **Pourquoi Python 3.13 ?** C'est la version de `.python-version`, et `pyproject.toml` exige
   `>=3.13`. Le choix lui-même est antérieur à cette PR ; cette PR ne fait que le nommer.

## Zones non vérifiées

- Le code exact d'un statut HTTP renvoyé par GitHub pour un jeton refusé, et la classe des
  erreurs du client BigQuery (droits, quota) : décrits sans être nommés, rien n'a été exécuté
  contre ces services.
- Le code 130 de Ctrl-C est celui du shell pour un processus tué par SIGINT ; il n'a pas été
  observé sur `kb collect`.
- Le cas « SIGTERM après l'écriture de l'état » (code 143, état écrit) est lu dans le code
  (`stopping_on_sigterm` entoure toute la commande), pas testé.

## Ce qui reste

- Signalé, non fait ici (code) :
  - la docstring de `cisa_kev.py:82` dit encore qu'un NUL lève `csv.Error` ;
  - aucun code nommé pour SIGINT ;
  - tldr ne lit pas sa page à la collecte (écart à la règle 1).
- Le README et `KB_COLLECT_ONLY` sont faits dans #201. La sortie réelle de `kb collect` relève
  de #25.
