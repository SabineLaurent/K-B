# Enchaîner les étapes des jobs : `kb daily-routine` et `kb digest-watch`

- Date : 2026-11-06
- Branche : `feat/job-routines`
- Issue : #413
- Suite de : [`kb smoke-test` et le stockage d'échange](2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md) (#412)
- Fichiers principaux : `src/k_b/commands/job_routine.py`, `src/k_b/commands/daily_routine_command.py`,
  `src/k_b/commands/digest_watch_command.py`, `src/k_b/commands/job_transfers.py`, `src/k_b/jobs/clip_mirror.py`,
  `src/k_b/jobs/watch_publication.py`, `src/k_b/cli.py`

## Le pourquoi

En ligne, tout tourne dans des jobs d'Azure Container Apps (ACA), et rien sur le Mac (« KB en ligne ne doit pas faire
tourner digest ou autre en local »). Un job lance une seule commande, dans l'image de #200, dont l'`ENTRYPOINT` est
`kb`. Il fallait donc deux commandes qui enchaînent chacune les étapes d'un job, avec ses transferts :

- `kb daily-routine` (job `caj-kb-daily-routine`, chaque jour) : copier les clips que le Mac a envoyés dans le
  conteneur Blob `clippings` vers le coffre du partage Azure Files, puis `kb collect`, `kb import`, `kb write-tops`,
  puis publier `veille/` vers le conteneur `watch`, que le Mac relit ;
- `kb digest-watch` (job `caj-kb-digest-watch`, deux fois par semaine) : réveiller les deux API, `kb digest`,
  `kb trend-report`, puis la même publication.

Le code de sortie de la commande est ce que voit le job, et plus tard l'alerte (#282). Il doit donc résumer
honnêtement les étapes.

## Le comment

### Une routine, c'est une liste d'étapes nommées

Chaque routine est une liste de `RoutineStep` : un nom, une fonction, et au besoin une règle « pas lancée si une
étape d'avant a rendu tel code » (`NotRunAfter`). La règle de l'issue, « `kb import` seulement si `kb collect` ne
rend ni 1 ni 2 », s'écrit ainsi :

```python
    RoutineStep(
        "kb import",
        lambda settings: run_import(settings.data_dir, settings.environ),
        NotRunAfter("kb collect", frozenset({ExitCode.FAILED, ExitCode.NOT_STARTED})),
    ),
```
(`src/k_b/commands/daily_routine_command.py:54-58`)

La `lambda` cherche `run_import` dans le module au moment où l'étape tourne : un test remplace la fonction dans le
module (`monkeypatch.setattr(daily_routine_command, "run_import", …)`) sans lancer de vraie collecte. La même liste
sert à l'exécution (`run_routine`) et au `--dry-run` (`describe_routine`) : les étapes affichées sont celles qui
tournent, sans copie.

### Le même processus, et le pire code

Les étapes sont des appels de fonctions Python, pas des sous-processus. Une exception imprévue d'une étape vaut 1
et la suite tourne, comme `cli.py` le fait pour une commande seule :

```python
    try:
        return step.run(settings)
    except Exception:
        logger.exception("%s stopped by an exception it does not handle", step.name)
        return ExitCode.FAILED
```
(`src/k_b/commands/job_routine.py:110-114`)

`except Exception` ne rattrape ni `StoppedBySigtermError` (une `SystemExit`) ni `KeyboardInterrupt` : un SIGTERM
remonte à `cli.py`, qui rend 143, et aucune étape suivante ne tourne. Le code de la routine est le pire des étapes
comptées, selon un ordre écrit, parce que la valeur des codes ne les ordonne pas (4 est moins grave que 1) :

```python
    exit_code = find_worst_exit_code(
        code
        for step in steps
        if step.is_counted and (code := codes.get(step.name)) is not None
    )
```
(`src/k_b/commands/job_routine.py:79-83`), avec `EXIT_CODES_FROM_BEST_TO_WORST` = 0, 4, 2, 1 (`job_routine.py:22`).
Le réveil des API est marqué `is_counted=False` (`digest_watch_command.py:63,69`) : il est montré au tableau et au
journal, sans décider du code.

### Les noms de blobs : une entrée externe qui devient un nom de fichier

Le nom d'un blob de `clippings` devient `Clippings/<nom>` sur le partage. Deux filtres, dans cet ordre. D'abord ce qui
n'est pas un clip du premier niveau, laissé de côté sans échec :

```python
    if "/" in name:
        return "blob_in_a_folder"
    if name.startswith("."):
        return "blob_name_hidden"
    if not name.endswith(extension):
        return "blob_not_markdown"
```
(`src/k_b/jobs/clip_mirror.py:154-159`)

Sans `/`, un nom n'a qu'un composant ; `..` commence par un `.` : aucun nom restant ne peut sortir du dossier. Puis ce
qu'un clip ne peut pas porter sur le partage, refusé (l'étape rend 4) : `\` (un séparateur pour le client CIFS), un
caractère de contrôle (`Cc`), d'usage privé (`Co`) ou surrogate (`Cs`), les caractères qu'Azure Files refuse
(`" : | < > * ?`), et plus de 241 octets (`clip_mirror.py:163-177`). 241 = 255, la longueur d'un nom de fichier,
moins les 14 caractères que `write_file_atomically` ajoute pour son temporaire (`.<nom>.XXXXXXXX.tmp`). Le journal
cite un blob refusé par sa position (`blob 12 of 120`), jamais par son nom, qui est le titre du clip.

### Recoder `ifSourceNewer`

Sur le Mac, azcopy envoie les clips avec `--overwrite=ifSourceNewer` (décision 7). Le SDK Python n'a pas cette
option : le miroir la recode.

```python
    if status is not None and (
        status.st_mtime_ns > modified_ns
        or (status.st_mtime_ns == modified_ns and status.st_size == blob.size)
    ):
        result.unchanged += 1
        return
    content = download_listed_version(container_client, blob)
    ...
    write_file_atomically(path, content)
    result.copied += 1
    try:
        os.utime(path, ns=(modified_ns, modified_ns), follow_symlinks=False)
```
(`src/k_b/jobs/clip_mirror.py:231-244`)

Une fois écrit, le fichier prend la date du blob (`os.utime`). La comparaison suivante oppose donc deux dates du
stockage, quelle que soit l'horloge du conteneur. Poser une date change le ctime, et `clipping.py` lit
`max(mtime, ctime)` : le clip copié, même daté de 2020, est vu comme changé par la collecte qui suit (un test le
prouve). À la même date seulement, la taille rattrape un second envoi dans la même seconde : `last_modified` n'a
qu'une précision d'une seconde. Un fichier plus récent que le blob est gardé quelle que soit sa taille : c'est
`ifSourceNewer` (une première correction de revue, qui comparait la taille dans tous les cas, l'avait cassé ; le
second passage l'a vu). Un fichier écrit dont la date ne peut être posée compte « copié », pour que l'attente ait
lieu, et en échec (`not dated`). Le téléchargement demande la version listée (`etag`, `MatchConditions.IfNotModified`), sans la décompresser
(`decompress=False`, `clip_mirror.py:259-264`). Un blob `Content-Encoding: gzip` de moins de 1 Mo pourrait faire des
Go une fois décompressé, et la taille vérifiée à la liste ne bornerait plus rien. Un 404 ou un 412 laisse le clip à
l'exécution suivante.

`kb collect` laisse au lendemain un clip changé depuis moins de 60 s. Après une copie, la routine attend donc la
marge plus 5 s (`CLIP_MIRROR_WAIT`, `job_transfers.py:56-64`), pour que le clip soit lu le jour même.

### Publier sans rien écraser

```python
        with naming_storage_errors():
            container_client.upload_blob(sheet_name, content, overwrite=False)
    except ExchangeStorageError as error:
        if error.http_status not in STATUS_ALREADY_THERE:
            raise
        result.already_there += 1
```
(`src/k_b/jobs/watch_publication.py:145-150`)

`overwrite=False` fait poser `If-None-Match: *` par le SDK : le stockage refuse (409) d'écrire sur un blob qui
existe, même créé par une autre exécution entre la liste et l'envoi. Avant, la liste des noms de `watch` évite de
renvoyer chaque jour toutes les fiches. Le parcours de `veille/` ne suit pas les liens. Il laisse de côté les entrées
cachées (dont les temporaires d'une écriture tuée) et lit chaque fiche par `O_NOFOLLOW`. Un dossier illisible est
compté par `on_error` et fait échouer l'étape (`watch_publication.py:99-107`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Les étapes dans le même processus | `kb` est le PID 1, seul à recevoir SIGTERM ; `stopping_on_sigterm` couvre toute la routine | `subprocess.run` par étape : relayer le signal vers l'enfant et attendre sa fin, du code de plus |
| Pire code dans l'ordre 0, 4, 2, 1 (Sabine, 06/11) | Un 2 peut être bénin (`kb digest` relancé le même jour) ; un 1 est une étape lancée qui a échoué | 0, 4, 1, 2 : un 2 bénin aurait caché un vrai 1 |
| Le réveil ne compte pas (time-knight) | Une API injoignable fait échouer l'étape qui suit, qui le dit | Le compter : un job qui a fait son travail rendrait 1 |
| Deux réveils, avant `kb digest` et avant `kb trend-report` | Une fiche dure jusqu'à 200 s ; les 300 s d'éveil d'ACA ne sont pas chronométrées | Un seul réveil : dépendre d'une durée non mesurée |
| Laissé de côté contre refusé | `clipping.py` saute de même ce qui n'est pas un clip ; un clip refusé ne l'est jamais en silence | Tout refuser : un `.DS_Store` rendrait 4 chaque jour |
| `..` comme composant de chemin (Sabine) | Couvert par `/`, `\` et le `.` initial | `..` partout : un titre « Les options... » refusé chaque jour |
| Date du blob posée sur le fichier ; la taille à la même date | Deux dates du stockage ; la taille pour la même seconde | La date d'écriture seule : dépend de l'horloge du conteneur ; la taille en tout cas : écrase un fichier plus récent |
| Version épinglée, `decompress=False` | Borne exacte de la taille téléchargée | Le défaut du SDK, qui décompresse |
| Attente de 65 s après une copie | Collecte du clip déterministe, le jour même | Rien : le jour même ou le lendemain, selon la durée des sources |
| `--dry-run` sans les réglages du job | Le critère le lance dans l'image sans eux | Lire les réglages : le critère sortirait en 2 |
| La purge du brut reste dans `kb import` jusqu'à #390 (Sabine, option c) | Tient le maximum de 6 mois du 04/11 | (a) pas de purge en ligne : le maximum tomberait ; (b) `pg_dump` dans #413 : périmètre de #390 |
| `jobs/` reçoit l'extension et `CLIP_MAX_BYTES` en paramètres | Règle des couches : `jobs` n'importe que `core` (`test_layers`) | Les recopier : une connaissance à deux endroits |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_kb_import_runs_after_kb_collect_exits_with_0_or_4`, `…_does_not_run_after_kb_collect_exits_with_1_or_2_the_rest_does` | La conduite pour les codes 0, 4, 1, 2 de `kb collect` |
| `test_kb_trend_report_and_the_publication_run_after_kb_digest_fails` | `kb trend-report` et la publication après un échec de `kb digest` |
| `test_a_sigterm_during_kb_collect_stops_the_routine_with_143`, `…_during_kb_digest_…` | SIGTERM réel : 143, la suite non lancée, le gestionnaire remis |
| `test_both_apis_are_woken_before_kb_digest_and_again_before_kb_trend_report` | L'ordre des réveils |
| `test_the_exit_code_is_the_worst_in_the_order_0_4_2_1` | L'ordre des codes |
| `test_a_name_that_is_not_a_clip_…_is_left_aside`, `test_a_clip_name_the_share_cannot_hold_is_refused` | Un cas par nom laissé de côté ou refusé, 241 octets acceptés, 242 refusés |
| `test_a_clip_unchanged_is_not_copied_again` | Aucun téléchargement, même inode et même ctime |
| `test_a_file_newer_than_its_blob_is_left_as_it_is` (deux tailles), `test_a_clip_sent_again_within_the_same_second_is_copied_by_its_size` | `ifSourceNewer`, et la même seconde rattrapée par la taille |
| `test_a_compressed_blob_is_copied_as_stored_never_decompressed` | `decompress=False` |
| `test_the_clip_copied_is_seen_changed_by_the_collection_that_follows` | Le ctime posé par la copie fait voir le clip à `ClippingSource.fetch` |
| `test_a_refused_clip_fails_by_its_position_…`, `test_a_local_error_is_counted_by_its_errno_never_its_path` | Aucun nom de clip au journal, `OSError` comprise |
| `test_every_sheet_is_sent_without_replacing_a_blob`, `test_a_sheet_sent_by_another_run_…` | `If-None-Match: *`, et 409 compté « déjà là » |
| `docker run --rm -e KB_DATA_DIR=/var/lib/knowledge_base k-b:413 daily-routine --dry-run` (et `digest-watch`) | Code 0 dans l'image construite en `linux/amd64` |
| `uv run pytest` : 3797 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | Contrôles du dépôt verts |
| `/security-review` : aucun constat au seuil | Revue de sécurité sur le chemin nom de blob → fichier |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas un `subprocess.run` par étape, plus simple à isoler ?** Dans le conteneur, `kb` est le PID 1, et
   ACA envoie SIGTERM au PID 1 seul. Un enfant ne le recevrait pas sans code de relais. Dans le même processus, le
   gestionnaire de `stopping_on_sigterm` couvre chaque étape (`sigterm.py:23`), et une étape interrompue se nettoie
   comme sur toute exception.
2. **Un blob nommé `../../etc/passwd.md` peut-il écrire hors du coffre ?** Non : un nom avec `/` est laissé de côté
   avant toute écriture (`clip_mirror.py:154`), `\` est refusé, et `Clippings` en lien symbolique est refusé
   (`ClippingsFolderRefusedError`). Le fichier écrit est toujours `Clippings/<un seul composant>`.
3. **Pourquoi la routine attend-elle 65 s après une copie ?** `clipping.py` laisse au lendemain un clip changé depuis
   moins de 60 s, et la copie vient de poser son ctime. Sans attente, le même clip serait lu le jour même ou le
   lendemain selon la durée des sources d'avant ; les 5 s couvrent l'écart d'horloge du partage, non mesuré.
4. **Pourquoi un réveil échoué ne fait-il pas échouer le job ?** Le réveil est un moyen. Si l'API reste injoignable,
   `kb digest` échoue et son code le dit ; s'il réussit, le job a fait son travail. Les lignes ERROR du réveil restent
   au journal.
5. **La publication peut-elle écraser une fiche que le Mac a déjà ?** Non : chaque envoi porte `If-None-Match: *`, et
   le stockage refuse en 409 d'écrire sur un blob existant, quel que soit l'ordre des exécutions.

## Zones non vérifiées

- Tout passe par des doubles : `FakeContainer` simule Blob Storage d'après sa documentation REST. Aucune exécution
  sur un vrai compte.
- Sur Azure Files monté en CIFS : que `os.utime` soit permis (il faut être propriétaire, d'où `uid=10001` dans les
  options de montage, #330), que le ctime suive, l'écart d'horloge entre le partage et le conteneur, et l'unité de
  longueur d'un nom du client CIFS (octets, supposée).
- Le délai entre SIGTERM et SIGKILL d'un job ACA : un job n'a pas de `terminationGracePeriodSeconds`.
- Deux blobs `a.md` et `A.md` : le plus récent l'emporte et reste, par raisonnement sur le code, sans test (APFS et
  l'ext4 de la CI ne traitent pas la casse pareil).
- Les 300 s d'éveil d'une API, défaut d'ACA non chronométré.
- Les tests ont d'abord été rouges à l'import seul, faute de code. Pendant le code, trois l'ont été sur le
  comportement : un `\` après un `.` initial (le nom est laissé de côté avant d'être refusé, test corrigé), le nom
  d'un blob vu dans les lignes INFO du SDK (capture limitée au logger `k_b`), et le format de la ligne de fin. Les
  corrections de la revue ont été vues rouges sur le comportement avant leur code.

## Ce qui reste

- L'étape Zotero, entre le miroir et `kb collect` (#425).
- La sauvegarde par `pg_dump`, puis la purge du brut couvert par deux sauvegardes saines, dans `kb daily-routine`
  (#390).
- Les jobs en Bicep et leur planification, avec leurs variables et le montage du partage (#330, #423) ; les comptes et
  leurs rôles (#420).
- Un verrou contre deux routines simultanées (#426).
- La liste de `watch` grandit sans purge, comme `veille/` du partage.
