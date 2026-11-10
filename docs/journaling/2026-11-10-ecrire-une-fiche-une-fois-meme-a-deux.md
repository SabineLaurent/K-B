# Écrire une fiche ou un brut une fois, même par deux lancements qui se chevauchent

- **Date** : 2026-11-10
- **Branche** : `fix/publish-without-replacing`
- **Issue** : #295
- **Commits** : `25df4fb` (le code, ses tests, README, `fiches-veille.md`, registre), `9d7f60a` (journal ADR),
  `a78478d` (le tri de la revue de code : la liste lue juste avant le renommage, les limites nommées), `cd2f4cb` (le
  tri de la seconde revue : le test de course du brut, les limites dans les docstrings)
- **Fichiers principaux** : `src/k_b/core/atomic_write.py`, `src/k_b/post/vault_files.py`,
  `src/k_b/etl/raw_store.py`
- **Série** : la fenêtre corrigée ici a été acceptée pour le POC dans
  [Écrire les fiches de veille dans le coffre](2026-10-21-ecrire-les-fiches-de-veille-dans-le-coffre.md) ; l'écriture
  par un temporaire caché vient de [Écrire par un temporaire caché](2026-10-16-ecrire-par-un-temporaire-cache.md).

La liste de commits et de fichiers injectée au lancement de la note comprend aussi l'historique de `main` (les PR
#521 à #538) : seuls les commits ci-dessus sont de cette branche, et la note ne couvre qu'eux (le commit de la note
elle-même mis à part).

## Le pourquoi

`kb write-tops`, `kb digest` et `kb trend-report` écrivent chacun une fiche par jour dans le coffre, et ne la
réécrivent jamais. Avant cette PR, la règle tenait par deux gestes successifs : regarder si la fiche existe
(`has_sheet`), puis l'écrire par un temporaire renommé sur la cible (`os.replace`). Entre les deux, une fiche écrite
par un autre lancement était remplacée sans message : c'est une course « contrôle puis usage » (CWE-367). Le brut
avait la même fenêtre (`write_new_raw_file` : `path.exists()`, puis l'écriture).

Sabine l'avait acceptée le 2026-10-21, tant que seule elle lançait `kb`. Cela cesse avec #330 : la routine
quotidienne tourne dans un job Azure Container Apps, et deux exécutions d'un job peuvent se chevaucher (une planifiée
et une lancée à la main, sur deux répliques). La fenêtre devient alors réelle, d'où l'issue, préalable du premier
passage planifié de #330.

Le moyen prévu par l'issue, `os.link`, ne marche pas là où les jobs écrivent : le partage SMB `job-data` d'Azure
Files. La page « Plan an Azure Files deployment » (Microsoft Learn, mise à jour le 2026-10-26) donne « Hard link
support: Not supported » pour SMB. Cette PR remplace donc le moyen, pas le but.

## Le comment

### 1. Un paramètre de la fonction d'écriture unique

La règle 2 de `conventions.md` veut une seule fonction pour tout fichier que K-B écrit. Le mode « écrit une fois »
est donc un paramètre de `write_file_atomically`, et non une seconde fonction :

```python
def write_file_atomically(path: Path, content: bytes, *, replace: bool = True) -> None:
```

(`src/k_b/core/atomic_write.py:29`). `replace=True` reste le défaut : l'état de collecte, le journal d'import, le
registre des comptes rendus, le miroir des clips et l'OpenAPI, qui se remplacent par nature, ne changent pas. Seuls
`write_new_sheet` (`src/k_b/post/vault_files.py:70`) et `write_new_raw_file` (`src/k_b/etl/raw_store.py:182`)
passent `replace=False`.

### 2. La réservation : un temporaire au nom fixe, créé seulement s'il n'existe pas

```python
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        return open(temporary_path, "xb", opener=open_private_file)
    except FileExistsError as error:
        raise TemporaryFileFoundError(temporary_path) from error
```

(`src/k_b/core/atomic_write.py:83-87`). Le mode `"x"` d'`open` ajoute `O_CREAT | O_EXCL` : le système crée le
fichier, ou échoue s'il existe déjà, en un seul geste. Pour deux lancements, la création du temporaire n'est donc
plus un contrôle suivi d'un usage : un seul des deux la réussit. Le temporaire devient ainsi la réservation de
l'écriture. Sur le partage SMB, le client Linux traduit `O_EXCL` en `FILE_CREATE` (`fs/smb/client/dir.c`,
`cifs_do_create`), que le serveur refuse si le nom existe (MS-SMB2, 2.2.13 et 3.3.5.9) : c'est le serveur qui
tranche, pas un des deux clients.

Le nom est fixe (`.2026-11-10.md.tmp`), et non plus aléatoire comme celui de `NamedTemporaryFile` : sinon deux
lancements auraient chacun le leur, et rien ne les départagerait. `opener=open_private_file`
(`atomic_write.py:90-92`) crée le fichier en `0o600`, le mode que `tempfile` donne aux autres. Il garde aussi le
chemin dans `.name`, dont `os.replace` a besoin.

### 3. Une réservation trouvée fait échouer l'écriture, et n'est jamais retirée

`TemporaryFileFoundError` hérite d'`Exception`, pas de `FileExistsError` (`atomic_write.py:20-26`). Sinon, un
`except FileExistsError` l'avalerait et la prendrait pour « la fiche est là ». Or rien ne dit que la fiche viendra :
un lancement est peut-être en train de l'écrire, ou bien un lancement tué a laissé son temporaire. `write_new_sheet`
la change en refus nommé :

```python
    except TemporaryFileFoundError as error:
        named = error.temporary_path.relative_to(vault_dir).as_posix()
        raise VaultEntryRefusedError(
            f"temporary_file_found: {named} is there"
        ) from error
```

(`src/k_b/post/vault_files.py:71-75`). `VaultEntryRefusedError` fait échouer les trois commandes : `kb write-tops`
sort en 4 pour ce top, `kb digest` compte le sujet en échec, `kb trend-report` sort en 1. C'est le fait relevé par
tn-codeur : sans cela, le job planifié de #330 réussirait sans sa fiche, car `kb write-tops` traite une fiche déjà là
comme une simple information (`top_sheets.py:149`). Le temporaire d'un autre n'est jamais supprimé : son nom peut
être la réservation d'un lancement en cours.

### 4. La cible cherchée dans la liste du dossier, juste avant le renommage

```python
            temporary_file.close()
            if not replace:
                refuse_listed_file(path)
            os.replace(temporary_file.name, path)
```

(`atomic_write.py:49-52`). Une fois la réservation tenue, il reste à savoir si un lancement antérieur a déjà écrit la
fiche. Deux détails comptent :

- **La liste, pas le statut.** `refuse_listed_file` cherche le nom dans `os.listdir` (`atomic_write.py:95-100`), et
  non par `lstat`. Le client SMB de Linux garde en cache la réponse « ce nom n'existe pas » jusqu'à une seconde
  (`cifs_d_revalidate`, noyau 6.19 : `time_after(jiffies, cifs_get_time(direntry) + HZ)`), et `has_sheet` vient
  justement de poser cette question. Un `lstat` pourrait donc répondre « absent » pour une fiche qu'une autre réplique
  vient d'écrire. Une liste de dossier n'est gardée que sous un bail du dossier, qu'Azure Files n'accorde pas
  (« SMB Directory Leasing: Not supported », même page).
- **Juste avant le renommage.** Au premier commit, la liste était lue avant l'écriture et le fsync. Le constat 2 de
  la revue l'a déplacée après : un écrivain autre que `kb` (Obsidian, une synchronisation), qui ne prend pas de
  réservation, n'est plus remplacé que s'il écrit dans le temps du renommage lui-même.

Le renommage se fait alors sur une cible absente. Avec la réservation, l'invariant est le suivant : dès la réservation
prise, le temporaire ou la fiche existe toujours (le renommage est un seul geste, sur APFS comme sur le serveur SMB).
Un second lancement échoue donc sur la réservation, ou trouve la fiche.

### 5. `write_new_sheet` garde ses contrôles

`has_sheet` reste avant l'écriture (`vault_files.py:67`) : il refuse tout de suite un lien ou un dossier au nom de la
fiche, et évite de prendre une réservation pour rien. Après un `FileExistsError`, il est rappelé (`vault_files.py:78`)
pour classer ce qui est apparu : une fiche (rendu `False`, `sheet_exists`), un lien (`vault_link_refused`), ou un
autre type d'entrée (`sheet_not_a_file`).

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Moyen d'écrire sans remplacer | La réservation par un temporaire `O_EXCL` (plan validé par Sabine le 10/11) | `os.link` : pas de lien physique sur SMB ; `renameat2(RENAME_NOREPLACE)` ou `renamex_np` : absents de `os`, appelés par ctypes, comportement non vérifié sur SMB2 ; créer la cible elle-même en `O_EXCL` : après un SIGKILL, une fiche tronquée serait publiée dans `watch`, figée par `If-None-Match`, jamais réécrite ; un verrou `fcntl` : dépend des options de montage ; un verrou par lancement : même reste après un arrêt brutal, et il bloque davantage |
| Où chercher la cible | La liste du dossier | `lstat` ou `exists()` : servis par le cache du client SMB (constat du relecteur sans contexte du plan) |
| Quand la chercher | Après le fsync, juste avant le renommage | Avant l'écriture (premier commit) : un écrivain autre que `kb` pouvait être remplacé pendant l'écriture et le fsync (constat 2 de la revue, tranché par time-knight) |
| Type de l'erreur de réservation | `TemporaryFileFoundError(Exception)` | Une sous-classe de `FileExistsError` : avalée par `except FileExistsError`, elle deviendrait un faux `sheet_exists` |
| Réservation trouvée | Échec de la commande | Une simple information : le job de #330 réussirait sans sa fiche (fait relevé par tn-codeur) ; retirer le temporaire : il peut être la réservation d'un lancement en cours |
| Dossier remplacé par un lien (CWE-59) | Hors de #295, limite et parade au registre (décision de Sabine du 10/11) | La descente par `dir_fd` et `O_NOFOLLOW` : le montage de `job-data` essayé pour #420 n'a pas `mfsymlinks`, sans lequel SMB n'a pas de lien symbolique ; sur le Mac, seul un processus de l'utilisatrice le peut |
| Mode du fichier | `0o600` par `opener` | `os.fdopen(os.open(...))` (constat 9 de la revue) : `.name` devient le numéro du descripteur |
| Journal d'import | Inchangé | Le passer en `replace=False` (constat 4 de la revue) : écarté par time-knight, car son contrôle se fait sous le verrou d'écriture de la base (`load.py:125-129`) et le second import n'a rien en cache pour ce nom |
| Règle 2 de `conventions.md` | Texte d'amendement proposé à Sabine, par time-knight | La modifier ici : `.claude/` est tenu par Sabine, et l'issue le dit |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : `ImportError` (`tests/test_atomic_write.py`) ; `write_new_sheet` rendait `True` sur la fiche d'un autre lancement ; le brut d'un autre lancement remplacé ; `kb write-tops` sortait en 0 avec un temporaire | Les tests rouges visaient bien la fenêtre et le faux succès |
| `test_a_file_written_once_is_never_replaced` | Une cible présente n'est jamais remplacée, et aucun temporaire ne reste |
| `test_a_file_written_once_is_looked_for_in_its_folder_not_by_its_status` | `stat` et `lstat` rendus « absent » pour la cible : la liste la trouve quand même (le cache du client SMB simulé) |
| `test_the_temporary_file_of_another_run_is_neither_removed_nor_replaced` | La réservation d'un autre lancement reste intacte ; l'erreur la nomme |
| `test_a_file_written_once_that_fails_leaves_no_temporary_file` | Un fsync en échec retire la réservation : le lancement suivant n'est pas bloqué |
| `test_a_file_written_once_is_synced_then_readable_by_its_owner_only` | fsync du fichier puis du dossier, mode `0o600` |
| `test_a_file_that_appears_while_the_file_written_once_is_synced_is_not_replaced` | Rouge au premier commit (`DID NOT RAISE FileExistsError`), vert après le déplacement : la liste est lue après le fsync |
| `test_a_sheet_written_by_another_run_after_the_check_is_not_replaced` | La fenêtre de l'issue est fermée pour une fiche |
| `test_a_raw_file_written_by_another_run_during_the_write_is_not_replaced` | Rouge contre l'ancien chemin (`exists()` puis `replace=True`, remis le temps de l'essai par une édition inverse : `DID NOT RAISE FileExistsError`), vert avec la réservation : la fenêtre est fermée pour le brut. Sa première version remplaçait `Path.exists`, que le code n'appelle plus (constat 5 de la seconde revue) |
| `test_a_temporary_file_of_the_sheet_is_refused_and_kept` et les trois tests de commande `test_a_temporary_file_left_…` | `temporary_file_found` fait échouer `kb write-tops` (4), `kb digest` (4) et `kb trend-report` (1), le temporaire gardé |
| `uv run pytest` (après `cd2f4cb`) : 4108 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |
| La vérification de la règle 3 de `poc.md` : même liste de fichiers qu'`origin/main` | Aucun fichier nouveau ne touche au disque hors de `raw_store.py` et des exceptions connues |
| Scratchpad : un dossier de fiche changé en fichier après `has_sheet` lève `NotADirectoryError` | Le constat 5 de la revue ne produit pas de faux `sheet_exists` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas `os.link`, que l'issue prévoyait ?** Le coffre des jobs est un partage SMB d'Azure Files, qui n'a
   pas de lien physique (« Hard link support: Not supported »). La réservation n'utilise que deux gestes que SMB
   tient côté serveur : créer un fichier s'il n'existe pas (`FILE_CREATE`), et renommer sur un nom absent
   (`atomic_write.py:83-87`, `:52`).
2. **Deux jobs écrivent la même fiche au même instant : que se passe-t-il ?** Un seul crée la réservation ; l'autre
   reçoit `TemporaryFileFoundError` et sa commande échoue (`temporary_file_found`). S'il arrive après le renommage,
   il trouve la fiche dans la liste et ne la remplace pas (`sheet_exists`). Dans aucun cas une fiche n'est écrasée.
3. **Pourquoi lire la liste du dossier plutôt qu'un `stat` ?** Le client SMB de Linux répond « absent » depuis son
   cache jusqu'à une seconde après une recherche du même nom, et `has_sheet` vient d'en faire une. La liste n'est
   pas gardée en cache sans bail de dossier, qu'Azure Files n'accorde pas (`atomic_write.py:95-100`).
4. **Et si `kb` est tué pendant l'écriture ?** Une exception, Ctrl-C et SIGTERM compris, retire la réservation
   (`atomic_write.py:53-63`). Un SIGKILL, une session SMB perdue, ou un SIGTERM reçu dans les quelques microsecondes
   entre la création et le bloc qui la retire la laisse en place : la fiche est alors refusée jusqu'au retrait à la
   main. C'est la fiche d'un jour pour `kb digest` et `kb trend-report`, mais pour `kb write-tops` la même fiche est
   réessayée à chaque lancement, puisque son relevé est gardé. C'est une limite écrite (ADR, README, `fiches-veille.md`) ;
   le retrait d'un temporaire vieux de plus d'une heure et l'alerte sur une exécution en échec sont deux issues que
   tn-codeur crée avec #330.
5. **Un lien symbolique planté peut-il faire écrire ailleurs ?** Pas au nom de la réservation : `O_EXCL` refuse toute
   entrée existante, lien compris (essai de la revue de sécurité sur APFS). Pas au nom de la fiche : un lien est listé,
   donc refusé. Reste un dossier remplacé par un lien après `refuse_linked_folders` (CWE-59) : limite acceptée par
   Sabine, impossible sur le partage monté sans `mfsymlinks`, avec sa parade au registre.

## Zones non vérifiées

- **Rien n'a tourné sur le partage SMB.** `FILE_CREATE`, le renommage sur un nom absent et la liste vue d'une autre
  réplique reposent sur la documentation Microsoft, la spécification MS-SMB2 et le code du noyau lu sur un miroir
  (v6.19), pas sur un essai. Le noyau des répliques d'ACA n'est pas connu. L'essai sur `job-data` se fait pendant
  l'amorçage de #330, préparé par tn-codeur dans #330 (décision de Sabine du 10/11).
- **Le moment exact où Python lève l'exception d'un signal** (juste après le retour d'un appel, avant le `try`) est
  raisonné, pas mesuré : la fenêtre du constat 1 n'a pas de test.
- **Les tests simulent les autres lancements** dans le même processus (un `has_sheet` ou un `fsync` qui écrit la
  cible) : aucun test ne lance deux processus en même temps.
- **Le cas d'une casse différente** (SMB et APFS ignorent la casse) n'est pas traité : les noms de `kb` sont en
  minuscules ASCII et la liste est comparée telle quelle. Un `2026-11-10.MD` écrit par un autre programme serait
  remplacé.

## Ce qui reste

- L'essai sur `job-data` de la réservation, pendant l'amorçage de #330, sans sonde à part ni tag pour lui : préparé
  par tn-codeur dans #330 (décision de Sabine du 10/11).
- L'amendement de la règle 2 de `conventions.md`, par Sabine (texte proposé par time-knight).
- Le retrait d'un temporaire vieux de plus d'une heure et l'alerte sur une exécution en échec : issues de tn-codeur,
  avec #330.
- La descente par `dir_fd` contre CWE-59 : parade écrite au registre, non faite.
