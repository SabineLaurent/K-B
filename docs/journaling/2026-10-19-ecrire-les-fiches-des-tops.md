# Écrire les fiches des tops dans le coffre : `kb write-tops`

- **Date** : 2026-10-19
- **Branche** : `feat/write-tops`
- **Issue** : #265 (critère : commentaire du 2026-10-19 sur l'issue, qui remplace son corps)
- **Fichiers principaux** : `src/k_b/etl/top_sheets.py`, `src/k_b/commands/write_tops_command.py`,
  `src/k_b/etl/raw_store.py`, `src/k_b/etl/source_kinds.py`, `src/k_b/etl/sources/github_most_starred.py`,
  `src/k_b/etl/sources/github_most_forked.py`, `tests/etl/test_top_sheets.py`, `tests/test_cli.py`
- **Série** : suit [la collecte du top des forkés](2026-10-19-collecter-le-top-des-depots-forkes.md)
  (#264), qui écrit le relevé que cette commande lit.

## Le pourquoi

Les deux tops GitHub (les 100 dépôts les plus étoilés, les 100 plus forkés) sont collectés chaque
jour, mais n'entrent pas en base (décision « Tops » du 2026-10-07) : jusqu'ici, rien ne les lisait.
Sabine veut qu'ils deviennent les deux premiers produits lisibles de K-B : une fiche Markdown par top
et par jour, dans son coffre Obsidian, écrite par du code et sans LLM.

Le 19/10, Sabine a fait de l'écriture des fiches une **commande à part**, `kb write-tops`, plutôt
qu'une étape cachée à la fin de `kb import` : la chaîne est faite d'étapes logiques (collecte, import
en base, fiches) qu'une automatisation enchaînera en ligne, et qu'on lance en dev par
`kb collect; kb import; kb write-tops`. Chaque commande garde son code de sortie.

La commande a un second rôle : une fois la fiche d'un jour écrite, le relevé brut qui l'a donnée n'a
plus à rester. Sabine : « je valide le dernier json importé avec succès ». Pour un top, « importé
avec succès » veut dire « sa fiche est écrite ». Le brut d'un top ne garde donc que son dernier
relevé lisible.

## Le comment

### 1. Un module du pipeline, déclaré par la composition

`etl/top_sheets.py` est un module du pipeline : il ne connaît aucune source (le test
`test_no_module_of_the_pipeline_imports_the_sources_or_the_composition` l'interdit). Il reçoit un
`Top` qui lui dit tout ce qu'il doit savoir d'un classement :

```python
TOPS = (
    Top(
        "most_starred",
        make_source_folder_key(
            AUTOMATED_WATCH_DIR_NAME, github_most_starred.FOLDER_PREFIX
        ),
        github_most_starred.read_top_entries,
```
(`src/k_b/etl/source_kinds.py:89`)

Le nom du dossier des fiches, la clé du dossier brut, le lecteur, puis l'en-tête de la colonne et le
sujet du titre. `TOPS` vit dans la composition (`source_kinds.py`), à côté de `SOURCE_KINDS`, parce
que `kb top` (#266) lira les mêmes deux relevés. Chaque source donne son `read_top_entries` : son
lecteur existant, puis une `TopEntry` par dépôt, avec l'URL **construite depuis le nom**
(`f"{REPOSITORY_URL_PREFIX}{repository.full_name}"`), jamais lue dans `html_url`.

### 2. Le parcours d'un top : lire tout, écrire ce qui manque, supprimer ensuite

```python
    for key in keys:
        ranking = read_ranking(store, top, key)
        if ranking is None:
            continue
        readable_keys.append(key)
        read_times.append(ranking.collected_at)
        written_count += write_sheet(vault_dir, sheets_dir, top, ranking)
    refuse_linked_folders(vault_dir, sheets_dir)
    refuse_missing_sheets(vault_dir, sheets_dir, read_times)
    deleted_count = sum(store.delete(key) for key in readable_keys[:-1])
```
(`src/k_b/etl/top_sheets.py:111-120`)

Trois idées dans ces lignes :

- **Le dossier est lu une fois** (`keys`, juste au-dessus). Un relevé qu'une collecte écrit pendant la
  commande n'est pas dans la liste : il n'est ni lu ni supprimé.
- **Chaque relevé est lu, même quand la fiche de son jour existe.** Seul un relevé lu sans erreur
  entre dans `readable_keys`. C'est la correction du seul constat bloquant de la relecture du plan :
  sans elle, un second relevé corrompu du même jour aurait passé pour « le dernier lisible », et le
  vrai dernier lisible aurait été supprimé.
- **La suppression vient après la boucle.** Une exception levée pendant une lecture ou une écriture
  (`OSError`, ou SIGTERM, qui arrive comme un `SystemExit`) sort de la fonction avant la ligne 120 :
  aucun relevé n'est supprimé. `readable_keys[:-1]` garde le dernier lisible, et tout ce qui le
  suit dans la liste (un illisible n'y est jamais).

### 3. Une fiche par jour, jamais réécrite

```python
    sheet_path = find_sheet_path(sheets_dir, ranking.collected_at)
    refuse_linked_folders(vault_dir, sheets_dir)
    if has_sheet(sheet_path, vault_dir):
        logger.info("%s sheet of %s: sheet_exists, not rewritten", top.name, day)
        return False
```
(`src/k_b/etl/top_sheets.py:245-249`)

Le chemin est fait de constantes (`veille`, `tops`, le nom du top) et d'une date reformatée depuis un
`datetime` : aucune valeur venue de GitHub n'y entre. Le jour vient du nom du fichier brut, contrôlé
par un aller-retour :

```python
    if collected_at.strftime(COLLECTION_NAME_FORMAT) != collection_name:
        return None
```
(`src/k_b/etl/top_sheets.py:163-164`)

`strptime` accepte `2026-10-5T093000Z` ; l'aller-retour le refuse, sinon l'ordre des noms ne serait
plus l'ordre du temps, et « le dernier » serait faux. Une fiche qui existe n'est jamais réécrite : la
fiche est du *curated*, Sabine peut l'éditer. Le journal ne nomme que le top et le jour, jamais le
chemin du coffre.

### 4. Une description de GitHub est une donnée, jamais une syntaxe

```python
    return "".join(
        f"\\{character}" if character in ESCAPED_CHARACTERS else character
        for character in " ".join(visible.split())
    )
```
(`src/k_b/etl/top_sheets.py:291-294`)

Avant ces lignes, chaque contrôle (`Cc`), surrogate isolé (`Cs`) ou contrôle bidirectionnel devient
une espace. Puis `split()` réduit tous les blancs, retours à la ligne compris, à une espace : la
description reste sur la ligne de son dépôt et ne peut ni ouvrir une ligne de tableau ni un `---`.
Enfin, `\`, `[`, `]`, `<`, `>`, `|`, l'accent grave, `#`, `%` et `$` reçoivent une barre oblique
inverse : plus de lien, d'image, de
wikilink, de HTML, de cellule, de code, de tag, de commentaire `%%` ni de formule. Le `\` est dans
la liste pour qu'une description finie par `\` n'échappe pas le `|` qui ferme sa cellule. Le
surrogate isolé n'est pas qu'un détail : `json.loads` l'accepte, mais l'encodage UTF-8 de la fiche
lèverait `UnicodeEncodeError` et ferait tomber toute la commande.

### 5. La commande : un réglage refusé, un top qui échoue

```python
    if not vault_dir.is_dir():
        logger.error(
            "%s is not an existing directory; no folder is created", VAULT_DIR_VARIABLE
        )
        return ExitCode.NOT_STARTED
```
(`src/k_b/commands/write_tops_command.py:34-38`)

`write_file_atomically` crée les dossiers parents : sans ce contrôle, une faute de frappe dans
`KB_VAULT_DIR` créerait un faux coffre. Sans coffre, la commande sort en 2 (« rien n'a été lancé :
un réglage est refusé »). Ensuite, chaque top est traité à part : une `OSError` sur l'un est
journalisée (type et `strerror`, jamais un chemin) et l'autre top est écrit quand même ; la commande
sort en 1 si un top a échoué ou garde un relevé illisible. Avant de lire un relevé et d'écrire une fiche, chaque dossier `veille/`, `veille/tops/`, `veille/tops/<top>/` est refusé s'il est un lien symbolique, et la fiche de chaque relevé listé s'il est un lien ou pas un fichier régulier (`refuse_linked_folders`, `refuse_linked_sheets`, `has_sheet`, `src/k_b/etl/top_sheets.py`) : le refus est tout ou rien. Les dossiers et la fiche sont recontrôlés avant chaque écriture, puis les dossiers et les fiches des relevés lisibles avant la suppression, où chaque fiche doit être là (`sheet_missing` sinon, `refuse_missing_sheets`) : une entrée prise pour une fiche écrite, ou une fiche retirée depuis son écriture, laisserait supprimer son relevé sans fiche. Décision de Sabine : `kb write-tops` ne suit jamais un lien symbolique dans le coffre, puisque c'est le dossier où il écrit qui est en jeu. `KB_VAULT_DIR` n'a qu'un lecteur,
`read_vault_dir` (`src/k_b/etl/collected_sources.py:92`), que la collecte des clips et cette
commande appellent.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une commande `kb write-tops` | Décision de Sabine : des étapes qui s'enchaînent, chacune avec son code | La fiche en fin de `kb import` (premier critère) : deux rôles dans une commande |
| `kb collect; kb import; kb write-tops` en dev | Décision de Sabine : `kb collect` sort en 4 dès qu'une source échoue | `&&` : une source en panne arrêterait les fiches, alors qu'elles ne lisent que le brut |
| Une fiche par jour de collecte encore dans le brut | Décision de Sabine (« une fiche par top et par collecte ») ; `kb collect` et `kb write-tops` n'ont pas le même rythme | La fiche du dernier relevé seul : un jour sans `kb write-tops` perdrait sa fiche |
| Un relevé illisible gardé, sortie 1 | Décision de Sabine : échouer fermé | Le journaliser et sortir en 0 |
| Sans coffre : code 2, aucun dossier créé | Le sens de 2, comme une source choisie sans sa variable dans `kb collect` ; tranché par time-knight | Succès avec « skipped » : `kb collect; kb import; kb write-tops` finirait en 0 sans fiche |
| `#`, `%`, `$`, surrogates et contrôles bidirectionnels ajoutés à la liste du critère | Un tag, un commentaire, une formule ; un encodage qui échoue ; un affichage réordonné | Tout retirer de `Cf` : U+200D joint les émojis (la fixture contient « 🚀✨ ») |
| `TOPS` dans `source_kinds.py` | `kb top` (#266) lira les mêmes relevés | Dans la commande, comme `LATEST_ONLY_FOLDER_KEYS` : #266 devrait le déplacer |
| `read_top_entries` dans chaque source, sans factoriser | Deux occurrences ; on factorise à la troisième (`code.md`) ; #269 réécrit les deux lecteurs | Une fonction commune qui prendrait le nom du champ du compte |
| Un lien symbolique dans `veille/…` refusé (`vault_link_refused`), une fiche qui n'est pas un fichier régulier aussi (`sheet_not_a_file`), sortie 1 | Décision de Sabine : `kb write-tops` ne suit jamais un lien symbolique dans le coffre, c'est le dossier où il écrit ; `sheet_not_a_file`, `sheet_missing` et les recontrôles avant chaque écriture et avant la suppression (time-knight) | Le suivre et l'écrire comme une limite (premier plan) ; écrire par descripteurs (`write_file_atomically` est partagée) |
| `read_latest` lit la dernière clé de `list_file_keys` | Une seule règle « fichiers visibles, ordre des noms » (constat 9 de la revue) | Deux compréhensions identiques |
| `WATCH_DIR_NAME`, `TOPS_DIR_NAME` dans `core/config.py` | À côté de `DIGEST_SUBJECTS`, dont les noms sont des dossiers sous `veille/` : le test du nom réservé les compare | Dans `etl/` : `kb digest` (#209) devra les lire aussi |
| Le compteur des relevés sautés s'appelle `skipped_count` | Il compte aussi un second relevé du même jour dont la fiche vient d'être écrite (constat 4 de la revue) | « already written », qui laissait croire que la fiche existait avant |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_ranking_gives_the_sheet_of_its_day_by_rank` | Le contenu exact d'une fiche : frontmatter, titre, tableau, URL construite, description absente → cellule vide |
| `test_the_url_is_built_from_the_name_never_read_in_html_url` | Un `html_url` différent n'apparaît pas dans la fiche |
| `test_each_day_of_collection_gets_its_sheet_and_the_older_rankings_are_deleted` | Trois jours, trois fiches ; les deux plus anciens relevés supprimés, le dernier gardé |
| `test_two_rankings_of_a_day_give_one_sheet_the_one_of_the_first` | La limite du même jour : la fiche vient du premier relevé |
| `test_a_last_ranking_unreadable_keeps_the_last_readable_one`, `test_a_second_ranking_of_a_day_unreadable_is_read_and_kept` | Un illisible n'est jamais pris pour le dernier lisible, et n'est jamais supprimé |
| `test_a_ranking_written_after_the_folder_is_read_is_neither_read_nor_deleted` | Une collecte pendant la commande ne perd rien |
| `test_a_sheet_not_written_deletes_no_ranking` (`PermissionError`, `StoppedBySigtermError`) | Rien n'est supprimé avant que les fiches soient écrites |
| `test_a_file_not_named_by_a_collection_time_is_kept_and_its_name_never_logged` | L'aller-retour du nom, et aucun nom de fichier au journal |
| `test_a_description_is_neutralized_on_one_line` (15 cas), `test_a_trapped_description_stays_in_its_cell` | La neutralisation, ligne à ligne |
| `test_a_folder_of_the_sheets_that_is_a_symbolic_link_is_refused_before_any_ranking_is_read` (3 dossiers), `test_a_sheet_that_is_a_symbolic_link_refuses_its_top_before_any_sheet_is_written` (cible absente ou présente), `test_a_folder_replaced_by_a_link_while_the_sheets_are_written_deletes_no_ranking`, `test_a_sheet_replaced_by_a_link_while_the_sheets_are_written_deletes_no_ranking`, `test_a_folder_named_as_a_sheet_refuses_its_top_and_no_ranking_is_deleted`, `test_a_linked_sheet_of_an_unreadable_ranking_refuses_the_top_too`, `test_a_sheet_removed_before_the_deletion_refuses_its_top_and_deletes_no_ranking`, `test_a_folder_of_a_top_linked_elsewhere_is_refused_exits_1_and_the_other_top_is_written` | Un lien dans `veille/…` n'est jamais suivi : refus tout ou rien, rien n'est écrit à sa cible, aucun relevé n'est supprimé, sortie 1, l'autre top écrit |
| `test_no_value_of_github_enters_the_path_of_a_sheet` | L'ensemble des fichiers créés est exactement celui attendu, même avec `../` dans la description |
| `tests/test_cli.py`, `test_write_tops_*` et `test_kb_import_writes_nothing_in_the_vault` | Codes 0, 1, 2 et 143 ; sans coffre, rien n'est supprimé ni créé ; `kb import` ne touche pas au coffre |
| `uv run pytest -q` → 1946 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles de la CI |

## Ce que tu dois pouvoir défendre

1. **Pourquoi relire un relevé dont la fiche du jour existe déjà ?** Pour savoir s'il est lisible.
   Seul un relevé lu sans erreur peut devenir « le dernier lisible » qu'on garde ; sinon un second
   relevé corrompu du même jour ferait supprimer le seul bon (`top_sheets.py:111-120`).
2. **Que se passe-t-il si la commande est tuée au milieu ?** Un SIGTERM arrive comme
   `StoppedBySigtermError`, qui remonte avant la suppression : les fiches déjà écrites restent,
   aucun relevé n'est supprimé, le code est 143. `write_file_atomically` retire son temporaire. Un
   SIGKILL, lui, peut laisser un `.AAAA-MM-JJ.md.*.tmp` caché dans le coffre (limite écrite).
3. **Une description GitHub peut-elle injecter quelque chose dans le coffre ?** Ni chemin (il est fait
   de constantes et d'une date), ni ligne (tous les blancs deviennent une espace), ni lien, HTML, tag
   ou commentaire (échappés). Il reste de la mise en forme (`*`, `_`, `~`, `==`) et une URL nue,
   cliquable comme sur GitHub (`top_sheets.py:278-294`).
4. **Pourquoi la fiche contient-elle des logins, et combien de temps ?** Le nom `owner/repo` identifie
   le dépôt ; 36 des 100 plus forkés appartiennent à une personne. La fiche est du *curated*, gardée
   tant que Sabine la garde pour sa veille : un critère et non un chiffre, comme le permet
   l'article 13.2.a du RGPD (registre, fiche 1, durée ; l'effacement est à l'étape 5).
5. **Pourquoi pas le code 4 quand un top échoue et l'autre réussit ?** Le 4 est défini pour
   `kb collect` ; le critère de #265, décidé par Sabine, demande 1. La sortie imprimée dit, top par
   top, ce qui a été fait.

## Zones non vérifiées

- **Le rendu dans Obsidian** : les tests vérifient le texte Markdown écrit, pas son affichage. Que
  Obsidian respecte chaque échappement par `\` (en particulier `\#`, `\%`, `\$` dans une cellule de
  tableau) n'a pas été essayé ; aucune page d'aide d'Obsidian trouvée ne le dit.
- **La règle de CommonMark** (« toute ponctuation ASCII peut être échappée ») n'a été lue que citée
  dans des fils de discussion, pas dans la spécification elle-même : Context7 était déconnecté.
- **Les vrais relevés** : aucun `kb write-tops` n'a tourné sur le brut réel. Au premier lancement,
  tout l'historique des relevés devient des fiches, puis ces relevés sont supprimés ; un ancien relevé
  illisible ferait sortir la commande en 1 à chaque lancement.
- **Un lien posé entre un contrôle et l'écriture** : les dossiers et les fiches sont recontrôlés
  avant chaque écriture et avant la suppression (testé), mais une entrée remplacée par un lien
  entre le dernier contrôle et l'écriture serait suivie. Seul un processus qui a déjà le compte de l'utilisatrice
  peut exploiter cette course.
- **Un coffre synchronisé** (iCloud, Obsidian Sync) ferait sortir les logins de la machine : non
  vérifié, écrit au registre.

## Ce qui reste

- **#266** : `kb top`, l'affichage du dernier relevé, qui lira `TOPS`.
- **#269** : les deux tops en GraphQL ; les anciens relevés REST devront rester lisibles, ou être
  retirés, sinon `kb write-tops` sortira en 1.
- **#272** : la fréquence de collecte de chaque source ; les tops à 7 jours donneraient une fiche par
  semaine.
- **Ouvert dans l'ADR** : où tourne `kb write-tops` en ligne, avec le coffre, d'ici le 08/11.
- **Signalé, non fait ici** : `parse_collection_name` (`etl/transform.py`) n'a pas l'aller-retour du
  nom ; un brut nommé à la main `2026-10-5T…` serait mal ordonné par l'import et la purge des
  catalogues d'état (constat 3 de la revue, soumis à Sabine).

Hors de cette note : les commits et fichiers listés au lancement de la note appartiennent à des PR
déjà fusionnées sur `main` ; cette branche n'en a que cinq (d828490, 4bb57c7, d14f94b, eb989ad, et
celui de cette note).

## Sources

| Source | URL | Consultée le |
|---|---|---|
| CommonMark, section 6.1 « Backslash escapes », citée dans un fil de discussion de CommonMark (la spécification elle-même n'a pas été lue) | https://talk.commonmark.org/t/current-rule-on-backslash-escapes-6-1-conflicts-with-stated-overriding-design-goal/3312 | 2026-10-19 |
| Obsidian Help, « Basic formatting syntax » (commentaires `%%`), lue par une copie de la page d'aide | https://huggingface.co/spaces/anpigon/obsidian-qa-bot/blob/main/docs/obsidian-help/Editing%20and%20formatting/Basic%20formatting%20syntax.md | 2026-10-19 |
| Obsidian Help, page officielle de la syntaxe (texte coupé avant la section des commentaires dans le résultat de recherche) | https://help.obsidian.md/Editing+and+formatting/Basic+formatting+syntax | 2026-10-19 |
