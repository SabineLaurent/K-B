# Écrire chaque fichier par un temporaire caché, vidé sur le disque

- **Date** : 2026-10-16
- **Branche** : `fix/hidden-temporary-file`
- **Issue** : #62 (regroupe #112 et #78)
- **Fichiers principaux** : `src/k_b/etl/raw_store.py` (`write_file_atomically`),
  `tests/etl/test_raw_store.py`, `tests/etl/test_transform.py`, `.claude/rules/conventions.md`
  (règle 2)
- **Série** : suit [Lire un dossier de pages brutes](2026-10-06-lire-un-dossier-de-pages-brutes.md),
  qui fait sauter les noms cachés à l'import.

## Le pourquoi

K-B écrit lui-même quatre sortes de fichiers : le brut de chaque collecte, l'état de collecte
(`collection_state.json`, la date de la dernière collecte par source), le journal d'import et
l'OpenAPI de l'API de données. Les quatre passent par une seule fonction, `write_file_atomically`
(règle 2 de `conventions.md`). Avant cette PR, elle avait trois défauts :

1. **Un temporaire visible.** Il s'appelait `tmpXXXXXXXX`. Si l'écriture était coupée, ce reste
   restait dans le dossier, et dans un dossier de pages l'import le lisait comme une page (#112).
2. **Un nettoyage incomplet.** Le temporaire n'était supprimé que si le renommage levait une
   `OSError`. Un disque plein à l'écriture ou à la fermeture (#78), ou un Ctrl-C, le laissait.
3. **Aucune écriture sur le disque.** Ajout de Sabine le 16/10. Le brut est écrit pendant la
   collecte, l'état de collecte à la fin (`etl/extract.py:63-64`). Sans `fsync`, les deux restent
   dans le cache du système. Après une coupure de courant, l'état peut être sur le disque, avec la
   nouvelle date, et le brut vide, tronqué ou absent. La collecte suivante repart de la date
   avancée : des items manquent, sans que rien ne le dise.

Le POC tourne en conteneurs (#193, #200 ensuite). Or `docker stop` coupe un processus : la
fonction doit rester sûre quelle que soit l'étape où elle est coupée.

## Le comment

### 1. Écrire à côté, puis renommer

`src/k_b/etl/raw_store.py:60-68` :

```python
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as temporary_file:
        try:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_file.close()
            os.replace(temporary_file.name, path)
```

Le contenu va d'abord dans un fichier temporaire, **dans le dossier de la cible**. `os.replace`
le renomme ensuite sur la cible. Sous POSIX, ce renommage est atomique : un lecteur voit l'ancien
fichier ou le nouveau, jamais un fichier à moitié écrit. Le temporaire doit être dans le même
dossier, donc sur le même système de fichiers : la doc de Python le dit, `os.replace` « may fail
if src and dst are on different filesystems ».

`delete=False` : c'est nous qui décidons du sort du temporaire (renommé ou supprimé), pas le
gestionnaire de contexte.

### 2. Un nom caché

Le préfixe `f".{path.name}."` donne par exemple `.2026-10-05.html.k3j2l1ab.tmp`. Ce nom :

- commence par `.`, donc l'import le saute. `list_visible_entries`
  (`src/k_b/etl/transform.py:205-208`) écarte tout nom qui commence par un point. Elle sert au
  lecteur des pages comme à celui des classements de GH Archive. Un reste laissé par un
  processus tué n'est donc jamais lu comme une page, sans aucune étape de nettoyage ;
- nomme sa cible, ce qui aide à comprendre un reste trouvé sur le disque ;
- a une partie aléatoire, créée avec `O_CREAT | O_EXCL` (c'est `mkstemp` qui travaille sous
  `NamedTemporaryFile`). Deux écritures de la même cible n'ont donc jamais le même temporaire, et
  un fichier ou un lien symbolique déjà en place fait échouer la création au lieu d'être suivi.

### 3. Tout nettoyer sur toute exception

`src/k_b/etl/raw_store.py:69-77` :

```python
        except BaseException:
            ...
            with contextlib.suppress(OSError):
                temporary_file.close()
            with contextlib.suppress(OSError):
                os.remove(temporary_file.name)
            raise
```

- **`BaseException`, pas `Exception`.** Ctrl-C lève `KeyboardInterrupt`, et `sys.exit` lève
  `SystemExit`. Aucune des deux n'hérite d'`Exception`. Avec `except
  Exception`, un Ctrl-C au mauvais moment laisserait le temporaire.
- **Fermer avant de supprimer.** Sur un disque plein, `flush()` lève `ENOSPC`, mais les données
  restent dans le tampon. Sans cette fermeture, la sortie du `with` refermerait le fichier,
  retenterait le flush et lèverait une seconde `ENOSPC` à la place de l'erreur d'origine. Pire :
  un Ctrl-C pendant ce flush ressortirait en `OSError`, que le `except Exception` de la collecte
  (`etl/extract.py:45`) attraperait, et la collecte continuerait au lieu de s'arrêter. Fermé
  ici, sous `suppress`, le fichier ne lève plus à la sortie du `with` : une sonde sur Python
  3.13.13 montre qu'un `BufferedWriter` dont `close()` lève est bien fermé (`closed` vaut
  `True`), et qu'un second `close()` ne fait rien.
- **`suppress(OSError)` autour de la suppression.** Si Ctrl-C arrive juste après `os.replace`,
  le temporaire n'existe plus : `os.remove` lèverait `FileNotFoundError` et masquerait le
  `KeyboardInterrupt`. Avec ce `suppress`, c'est toujours l'erreur d'origine que relève le
  `raise` nu. Si la suppression échoue vraiment, le reste est caché, donc sauté.

### 4. Pourquoi le renommage seul ne suffit pas : `fsync`

Le renommage protège un **lecteur** d'un fichier à moitié écrit. Il ne protège pas d'une
**coupure de courant**. Le système garde les écritures dans son cache et les envoie au disque
plus tard, dans l'ordre qui lui convient. Il peut envoyer le renommage (une écriture du dossier)
avant le contenu du fichier : après la coupure, la cible existe, mais vide. Il peut aussi envoyer
l'état de collecte, écrit plus tard, avant le brut.

D'où deux `fsync` :

- **sur le fichier, avant le renommage** (ligne 66). `flush()` vide d'abord le tampon de Python
  vers le système, puis `os.fsync` demande au système d'écrire sur le disque. C'est l'ordre que
  donne la doc de Python : « first do `f.flush()`, and then do `os.fsync(f.fileno())` » ;
- **sur le dossier, après le renommage** (lignes 78-86). Le nom d'un fichier vit dans son
  dossier. Le man de `fsync(2)` le dit : « Calling fsync() does not necessarily ensure that the
  entry in the directory containing the file has also reached disk. For that an explicit
  fsync() on a file descriptor for the directory is also needed. »

Un dossier que l'écriture crée (`mkdir(parents=True)`) est lui aussi une entrée dans son parent.
Une collecte en pages crée `raw/automated_watch/<source>/<collection>/`. Si seule la page et son
dossier sont synchronisés, l'entrée `<collection>` dans `<source>/` peut se perdre, et toute la
collecte avec. Avant le `mkdir`, la fonction relève donc les dossiers qui manquent
(`raw_store.py:52-58`) :

```python
    folders_to_sync = [path.parent]
    folders_to_sync += [
        folder.parent
        for folder in itertools.takewhile(
            lambda folder: not folder.exists(), path.parents
        )
    ]
```

`path.parents` part du dossier de la cible et remonte. `takewhile` s'arrête au premier dossier
qui existe. Pour chaque dossier qui manque, la fonction synchronise son parent, celui qui
contient sa nouvelle entrée.

### 5. Un dossier qui refuse le `fsync`

`src/k_b/etl/raw_store.py:28` et `:83` :

```python
REFUSED_FOLDER_SYNC_ERRORS = (errno.EBADF, errno.EINVAL)
...
            if error.errno not in REFUSED_FOLDER_SYNC_ERRORS:
                raise
```

Certains systèmes de fichiers ne savent pas synchroniser un dossier. Le man de `fsync(2)`
documente `EINVAL` (« fd is bound to a special file … which does not support
synchronization ») ; `EBADF` vient sur d'autres systèmes. PostgreSQL tolère ces deux-là au
`fsync` d'un dossier : `EINVAL` a été ajouté pour les anciens CIFS de Linux (bug #15636). C'est
le cas qui nous concerne, puisque Azure Files, prévu au 08/11, est un partage SMB. Toute autre
erreur, par exemple `EIO`, remonte.

### 6. Pas de fonction de plus

Le `fsync` des dossiers est écrit dans `write_file_atomically`, pas dans une fonction à part. La
règle 3 de `poc.md` veut qu'une fonction nouvelle de `raw_store.py` prenne une clé POSIX, pas un
`Path`, pour préparer Azure Blob Storage. Une fonction `sync_directory(directory: Path)` l'aurait
enfreinte. La fonction est plus longue, mais elle reste la seule à écrire un fichier.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nom du temporaire | `.<nom>.<aléatoire>.tmp` : caché, nomme sa cible, unique | Nom fixe `.<nom>.tmp` : deux écritures en même temps s'écraseraient |
| Restes d'une écriture tuée | Un nom caché, sauté par l'import | Nettoyer au démarrage : le reste reste visible entre-temps, une étape de plus à chaque lancement (revue du 11/10) |
| Nettoyage | `try … except BaseException` lisible (exigé par la règle 2 et le critère) | `NamedTemporaryFile(delete_on_close=False)` : même effet, mais implicite ; et le nettoyage de la stdlib n'ignore que `FileNotFoundError`, un autre échec de suppression y masquerait l'erreur d'origine |
| Forme du code | `try` dans le `with` | `try` hors du `with` : ruff le refuse (SIM115), constaté par l'architecte |
| Durabilité | `fsync` du fichier puis des dossiers (décision de Sabine du 16/10) | Seulement signaler : l'état de collecte peut dépasser le brut après une coupure |
| Dossiers créés | Synchronisés dans leur parent (constat de revue, tranché par time-knight) | Seul le dossier cible : une collecte en pages peut se perdre entière |
| Erreurs tolérées | `EBADF`, `EINVAL`, comme PostgreSQL | `EOPNOTSUPP` : aucune source trouvée ; tout ignorer : une vraie `EIO` passerait inaperçue |
| `EIO` au `fsync` du dossier | Relevée : échouer fermé (`code.md`) | Avaler l'erreur parce que le fichier est en place : sa durabilité n'est pas acquise |
| Un `fsync` de dossier par page | Gardé : quelques pages par collecte, et une seule fonction (règle 2) | Un seul `fsync` après la dernière page : chaque appelant porterait la règle |
| macOS | Pas de `F_FULLFSYNC` : la cible est Linux en conteneur | Un chemin propre à macOS pour une plateforme qui n'est pas la cible |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_failed_write_leaves_no_temporary_file_and_raises_its_own_error` (`test_raw_store.py:88`), 5 cas : écriture, flush, Ctrl-C au flush, fermeture, Ctrl-C au renommage | L'erreur qui remonte est exactement celle d'origine (`raised.value is error`), le dossier ne contient que la cible, dont le contenu n'a pas changé |
| `test_the_temporary_file_is_synced_before_the_rename_then_its_folder` (`:116`) | L'ordre : `fsync` du fichier (même inode que la cible), puis `os.replace`, puis `fsync` du dossier |
| `test_each_folder_created_for_the_write_is_synced_in_its_parent` (`:144`) | Fichier, dossier de la collecte, puis dossier de la source, qui contient l'entrée de la collecte |
| `test_a_folder_that_refuses_fsync_does_not_fail_the_write` (`:183`), `EBADF` et `EINVAL` | Un refus documenté ne fait pas échouer l'écriture |
| `test_a_failed_fsync_of_the_folder_is_raised` (`:194`) | `EIO` remonte |
| `test_the_rest_of_an_interrupted_write_in_a_folder_of_pages_is_skipped` (`test_transform.py:321`) | Avec `os.replace` neutralisé (processus tué avant le renommage), le vrai temporaire reste, au nom `.2026-10-06.html.….tmp`, et l'import ne rend que la vraie page, sans rejet |
| Avant le code, ces tests échouaient sur `main` (nom `tmp3v30goe5`, temporaire laissé) | Chaque test prouve une ligne nouvelle |
| `uv run pytest` : 1468 verts ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Contrôles du dépôt |
| `grep -rn "NamedTemporaryFile\|\.tmp\|os\.replace" src/k_b` → `raw_store.py` seul, dans `write_file_atomically` | Critère : une seule fonction écrit |
| Sonde Python 3.13.13 : `BufferedWriter` sur un disque plein simulé | Après un `close()` qui lève, `closed` vaut `True` et un second `close()` ne lève pas |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas simplement `open(path, "wb").write(...)` ?** Un lecteur pourrait voir un
   fichier à moitié écrit, et un arrêt pendant l'écriture laisserait une page tronquée que
   l'import lirait. Le renommage atomique l'empêche (`raw_store.py:68`).
2. **Le renommage est atomique : à quoi sert `fsync` ?** L'atomicité vaut pour un lecteur, pas
   pour une coupure de courant. Le système peut écrire le renommage avant le contenu, ou l'état
   de collecte avant le brut. `fsync` force l'ordre : le contenu, puis le nom (`:66`, `:81`).
3. **Pourquoi `BaseException` ?** Ctrl-C (`KeyboardInterrupt`) et `SystemExit` n'héritent pas
   d'`Exception`. Le test « ctrl-c-at-rename » le prouve.
4. **Que se passe-t-il si le `fsync` du dossier lève `EIO` ?** La fonction lève, alors que le
   fichier est déjà renommé. La source est marquée en échec et sa date n'avance pas. La collecte
   suivante refait la même fenêtre dans un nouveau fichier brut. C'est sans perte : l'import
   écrit par upsert (`ON CONFLICT`, `database/writers/`). On échoue fermé.
5. **Où est la sécurité ?** Le nom du temporaire est aléatoire et créé en `O_EXCL` : un lien
   symbolique déjà en place n'est pas suivi. `path.name` ne contient pas de séparateur, donc pas
   de traversée de chemin. Les noms viennent de valeurs déjà validées (`SAFE_PAGE_NAME`,
   `SAFE_PATH_SEGMENT`). `/security-review` n'a rendu aucun constat.

## Zones non vérifiées

- **Le disque doit respecter les demandes de vidage de son cache.** `fsync` demande au système
  d'envoyer les données au disque. Un disque qui ment sur son cache peut encore perdre des
  données à la coupure. Ce n'est pas vérifiable depuis le code.
- **macOS.** La doc d'Apple dit que `fsync` envoie les données au disque, mais que le disque
  peut les écrire plus tard et dans le désordre ; elle renvoie à `F_FULLFSYNC`. D'après la doc
  de Python, `os.fsync` appelle le `fsync()` natif sous Unix. Sur le Mac de Sabine, la garantie
  est donc plus faible. La cible du POC est Linux en conteneur.
- **Azure Files.** Ce que ce partage SMB répond au `fsync` d'un dossier n'a pas été essayé.
  `EBADF` et `EINVAL` sont tolérés sur la foi de PostgreSQL. Une autre erreur ferait échouer
  chaque écriture : à vérifier au déploiement du 08/11.
- **Le coût.** Environ 12 ms par fichier, d'après la mesure publiée par safewrite (NVMe, ext4) ;
  rien n'a été mesuré sur K-B.
- **Une coupure de courant réelle** n'a pas été simulée. Les tests vérifient l'ordre des appels,
  pas ce qui reste sur le disque.

## Ce qui reste

- **Noms longs** : le temporaire ajoute 14 octets au nom (`.`, `.`, 8 caractères aléatoires,
  `.tmp`). Un nom de page de plus de 241 octets donnerait `ENAMETOOLONG` (la limite d'un nom
  est 255 octets). `SAFE_PAGE_NAME` ne borne pas la longueur, mais les pages réelles s'appellent
  par une date. Rien n'est fait (YAGNI).
- **Droits `0600`** : `mkstemp` crée en `0600`, et `os.replace` garde ce mode, ce qui était déjà
  le cas avant. Signalé sur #200 : l'UID du conteneur doit être le propriétaire de `/data`.
- **Arrêt sur SIGTERM** : #193, qui s'appuie sur ce nettoyage (`except BaseException`).
- **Brut dans Azure Blob Storage** (08/11, règle 3 de `poc.md`) : l'écriture du brut y sera
  reprise ; ce que deviennent le temporaire et le `fsync` n'est pas étudié ici.

## Sources

Consultées le 2026-10-16.

- [os — `os.replace`, `os.fsync`](https://docs.python.org/3.13/library/os.html), lu par
  Context7 : le renommage est atomique (exigence POSIX) et peut échouer d'un système de fichiers
  à l'autre ; `flush()` puis `os.fsync(f.fileno())` ; sous Unix, `os.fsync` appelle `fsync()`.
- [tempfile — `NamedTemporaryFile`](https://docs.python.org/3.13/library/tempfile.html), lu par
  Context7 : `prefix`, `suffix`, `dir`, `delete`, `delete_on_close`.
- [fsync(2), man-pages 6.13](https://www.mankier.com/2/fsync) : le `fsync` explicite du dossier
  pour l'entrée d'un fichier ; `EINVAL`.
- [PostgreSQL, commit « Tolerate EINVAL too, for older versions of Linux CIFS »](https://www.postgresql.org/message-id/E1gxrcU-0002A8-17%40gemulon.postgresql.org)
  (bug #15636) : `EBADF` et `EINVAL` tolérés au `fsync` d'un dossier.
- [fsync(2), Apple](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html) :
  le disque peut écrire plus tard et dans le désordre ; `F_FULLFSYNC`.
- [safewrite sur PyPI](https://pypi.org/project/safewrite/) : environ 12,2 ms par fichier avec
  `fsync`, contre 0,05 ms sans (NVMe, ext4, mesure de l'auteur).
