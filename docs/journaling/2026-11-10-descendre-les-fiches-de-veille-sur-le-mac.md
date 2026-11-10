# Descendre les fiches de veille d'Azure sur le Mac, sans croire ni les noms ni les textes

- **Date** : 2026-11-10
- **Branche** : `feat/download-watch-sheets`
- **Issue** : #424 (réduite à `make download-watch-sheets` ; `make upload-library` part dans #542)
- **Commits** : `be3c450` (la commande, ses tests, README, registre), `4cf2b78` (`.env.example`), `4712323` (journal
  ADR), `39b8f63` (tri de la première revue de code : contrôles bidirectionnels, échecs nommés), `e16fdd0` et
  `fc380c5` (tri de la revue de sécurité : le Markdown actif refusé), `2bddce2` (remise à jour sur `origin/main`),
  `98cebb0`, `c9bd2c9` et `3e5b800` (tri des deuxième et troisième revues : références de caractère, `\` dans un
  autolien, `~~~` dans une URL).
- **Fichiers principaux** : `src/k_b/commands/download_watch_sheets_command.py`, `src/k_b/jobs/watch_download.py`,
  `src/k_b/jobs/exchange_storage.py`, `src/k_b/post/vault_files.py`, `src/k_b/core/config.py`
- **Série** : le stockage d'échange et le rôle de lecture de l'opératrice sur `watch` viennent de
  [Créer le stockage des jobs et des échanges avec le Mac](2026-11-10-creer-le-stockage-des-jobs-et-des-echanges.md)
  (#420) ; l'écriture qui ne remplace jamais une fiche, de
  [Écrire une fiche ou un brut une fois](2026-11-10-ecrire-une-fiche-une-fois-meme-a-deux.md) (#295).
- **Hors de cette note** : les commits `00fb02d`, `e9558c2`, `f37bade`, `16dae02`, `6a924ca` et `7e44098` de la liste
  de la branche sont ceux de `kb purge` (#540), arrivés de `main` par la fusion `2bddce2` ; ils ont leur note,
  [Purger par sa propre commande](2026-11-10-purger-par-sa-propre-commande.md).

## Le pourquoi

En ligne, les jobs écrivent les fiches de veille (comptes rendus par sujet, tops, tendances) dans le coffre de
travail du partage `job-data`, puis les publient dans le conteneur `watch` du stockage d'échange. Le Mac, lui, ne fait
plus qu'Obsidian : il faut une commande, lancée à la main, qui ramène ces fiches dans `veille/` du coffre.

Deux contraintes font de cette commande une frontière de sécurité, pas une simple copie :

1. **Le contenu de `watch` est une entrée non fiable.** Deux identités de jobs y écrivent (revue de sécurité de #420).
   Si l'une d'elles est détournée, elle peut déposer un blob nommé `models/../../.zshrc`, ou une fiche qui contient
   une requête Dataview capable de lire tout le coffre. Le Mac est l'endroit où ce contenu s'exécuterait.
2. **Le critère de #424** : un second passage copie 0 fichier, et une fiche modifiée en local n'est pas écrasée.

La commande ne fait donc qu'une chose : copier dans `veille/` chaque fiche de `watch` qui y manque, après avoir
vérifié que son nom et son texte sont exactement ce que kb écrit lui-même.

## Le comment

### 1. Une commande en étapes nommées, par le compte d'`az login`

`src/k_b/commands/download_watch_sheets_command.py:75-94` :

```python
    settings = value_or_log_refusal(read_watch_download_settings_or_refusal(environ))
    if settings is None:
        return ExitCode.NOT_STARTED
    try:
        with (
            naming_storage_errors(),
            build_cli_credential() as credential,
            open_container_client(
                settings.account_url, WATCH_CONTAINER, credential
            ) as container_client,
        ):
            check_identity(credential)
            result = download_watch(container_client, settings.vault_dir)
```

Le chemin se lit sans ouvrir les étapes : lire les réglages (refus → code 2), ouvrir le jeton et le client du
conteneur, demander un jeton tout de suite (`check_identity`), puis télécharger. `build_cli_credential`
(`src/k_b/jobs/exchange_storage.py:140-143`) rend un `AzureCliCredential` : le SDK lance `az` pour chaque jeton, sur
le compte Entra qu'`az login` a ouvert. Pas d'`AZURE_CLIENT_ID` (c'est le réglage d'une identité managée, celle d'un
job), pas de clé de compte, rien qui se garde sur le disque par kb. `check_identity` avant la liste : sans
`az login`, la commande s'arrête sur `exchange_storage_no_token`, avant tout appel au conteneur.

`naming_storage_errors()` entoure le tout : une erreur du SDK devient une `ExchangeStorageError` nommée par son statut
et son code, jamais par `str(error)`, qui citerait l'URL d'un blob, donc un nom.

La lecture de l'URL du compte est partagée avec les jobs : `find_exchange_blob_url_refusal`
(`src/k_b/jobs/exchange_storage.py:111`) a été extraite de `read_exchange_storage_settings_or_refusal`, pour que le Mac
lise `KB_EXCHANGE_BLOB_URL` par la même règle sans exiger `AZURE_CLIENT_ID`.

### 2. Une liste fermée de noms, jamais un nom nettoyé

`src/k_b/jobs/watch_download.py:34-37` :

```python
SHEET_NAME = re.compile(
    r"(?P<folder>[a-z_]{1,64}(?:/[a-z_]{1,64})?)"
    r"/(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})\.md"
)
```

Un nom de blob n'est une fiche que s'il a **exactement** la forme `<dossier>/<jour>.md`, lue par `fullmatch`
(`watch_download.py:138`) : `$` laisserait passer un retour à la ligne final. Les classes sont ASCII (`[a-z_]`,
`[0-9]`) et non `\w` ou `\d`, qui prennent les lettres et les chiffres d'autres écritures. Il n'y a ni `.`, ni `/`
en tête, ni `\` possibles dans le dossier : `../`, un chemin absolu, un nom caché ne peuvent pas correspondre. Le jour
est relu par `is_day` (`watch_download.py:144-149`) : `date.fromisoformat(text).isoformat() == text` refuse
`2026-13-40` et toute autre écriture d'une date que celle que kb produit.

Le dossier doit ensuite être l'un de ceux où kb écrit, `WATCH_SHEET_FOLDERS`
(`download_watch_sheets_command.py:57-61`) : les 9 sujets, `tops/<top>` (deux niveaux, d'où le `(?:/…)?` de la
regex), `tendances`. Le chemin local est alors **reconstruit** à partir de ces deux morceaux validés
(`download_watch_sheets_command.py:136-137`), jamais à partir du nom brut.

Deux sorts différents (`watch_download.py:182-188`) :

```python
    sheet_name = read_sheet_name(blob.name)
    if sheet_name is None:
        refuse_blob(result, where, "sheet_name_refused")
        return None
    if sheet_name.folder not in folders:
        result.left_aside["sheet_folder_unknown"] += 1
        return None
```

Un nom hors de la forme est **refusé** : un échec, journalisé par sa position (`blob 3 of 12`), jamais par son nom
(`refuse_blob`, `watch_download.py:196-201` ; règle 3 de `conventions.md`). Un nom de la bonne forme dans un dossier
inconnu (un sujet retiré depuis) est **laissé de côté**, sans échec : ce n'est pas une attaque, c'est l'histoire
du projet.

### 3. Ne rien remplacer, ne suivre aucun lien

`src/k_b/commands/download_watch_sheets_command.py:138-144` :

```python
    try:
        # The links first: lstat follows a link among the folders above the sheet.
        refuse_linked_folders(vault_dir, sheets_dir)
        if has_sheet(sheet_path, vault_dir):
            result.already_there += 1
            return
        content = download_sheet(container_client, sheet)
```

L'ordre compte. D'abord les dossiers de `veille/` jusqu'à la fiche, chacun lu par `lstat` : un lien symbolique est
refusé (`vault_link_refused`), car un `lstat` sur la fiche suivrait un lien posé plus haut. Puis `has_sheet` : une
fiche déjà là (même modifiée par Sabine) n'est **ni téléchargée ni remplacée**. C'est ce qui donne « un second
passage copie 0 fichier » sans comparer de date ni de contenu, et sans même demander le blob au stockage.

L'écriture passe par `write_new_sheet` (`src/k_b/post/vault_files.py:52-72`), la fonction des trois écrivains du
coffre : elle revérifie les liens, puis appelle `write_file_atomically(..., replace=False)`, qui réserve le
temporaire par `O_EXCL` et ne remplace jamais une cible apparue entre-temps (#295). Une seule règle des liens et du
non-remplacement pour tout ce qui écrit dans le coffre.

### 4. Des bornes : la liste, la taille, la version listée

La liste est bornée sans tout charger (`watch_download.py:157-167`) :

```python
    with naming_storage_errors():
        blobs = list(
            itertools.islice(container_client.list_blobs(), MAX_WATCH_LISTED_BLOBS + 1)
        )
    if len(blobs) > MAX_WATCH_LISTED_BLOBS:
```

`islice(..., N + 1)` lit au plus un blob de trop : assez pour savoir que la borne est dépassée
(`MAX_WATCH_LISTED_BLOBS = 20_000`, `src/k_b/core/config.py:615`), sans parcourir tout le conteneur. Les fiches
listées sont copiées quand même ; la commande échoue (`is_truncated`).

La taille est bornée sur la liste, avant le téléchargement (`watch_download.py:189-192`,
`MAX_WATCH_SHEET_BYTES = 4_000_000`, `config.py:611`). Le téléchargement lui-même
(`src/k_b/jobs/clip_mirror.py:259-264`, repris du miroir des clips) :

```python
            downloader = container_client.download_blob(
                blob.name,
                etag=blob.etag,
                match_condition=MatchConditions.IfNotModified,
                decompress=False,
            )
```

`etag` et `IfNotModified` : on télécharge **la version listée**, celle dont on a contrôlé la taille ; un blob changé
depuis répond 412 et est laissé au passage suivant (`left_to_next_run`). `decompress=False` : un blob envoyé avec
`Content-Encoding: gzip` passerait la borne une fois décompressé. `download_sheet` (`watch_download.py:204-212`)
vérifie encore que le nombre d'octets reçus est celui de la liste.

### 5. Le texte : refuser ce que kb n'écrit jamais

`watch_download.py:219-234`, `find_sheet_text_refusal`, dans l'ordre : de l'UTF-8 strict (un surrogate isolé n'en est
pas), aucun caractère de contrôle (`Cc`) hors tabulation et retour à la ligne, aucun contrôle bidirectionnel
(`BIDI_CONTROLS`, qui inverserait l'affichage d'une ligne), puis aucun Markdown actif. Ce dernier contrôle est une
table de motifs (`watch_download.py:71-75`) :

```python
ACTIVE_MARKDOWN: tuple[tuple[re.Pattern[str], SheetRefusal], ...] = (
    (re.compile(NOT_ESCAPED + "`"), "sheet_text_with_code"),
    (re.compile(NOT_ESCAPED + "~~~"), "sheet_text_with_tilde_fence"),
    (re.compile(r"!\["), "sheet_text_with_embed"),
    (re.compile(NOT_ESCAPED + "<(?!https?://)"), "sheet_text_with_html"),
```

Un accent grave ouvre du code, donc une requête Dataview (`` `= this.file.name` ``) ; `~~~` ouvre une clôture de
code même dans une citation ou une liste ; `![` charge une image distante ou inclut une note ; un `<` qui n'ouvre pas
un autolien est du HTML ou une commande Templater (`<% … %>`). Suivent deux motifs : une référence de caractère non
échappée (`&#x202E;` serait décodée en contrôle bidirectionnel, même dans un autolien), et un `\` dans un autolien,
où il n'échappe rien (CommonMark 0.31.2, § 6.5) et laisserait passer la référence qui le suit.

`NOT_ESCAPED = r"(?<!\\)(?:\\\\)*"` (`watch_download.py:45`) compte la parité des barres obliques : un caractère
précédé d'un nombre impair de `\` est échappé (il s'affiche tel quel), d'un nombre pair (zéro compris) il ne l'est
pas. C'est exactement ce que font les écrivains de `post/`, qui échappent la syntaxe d'un texte de source par un
seul `\` : leurs fiches passent.

Pour que le contrôle et les écrivains disent la même chose, deux changements de l'autre côté :
- `BIDI_CONTROLS` et `CHARACTER_REFERENCE` sont passés de `post/vault_files.py` à `core/config.py`
  (`config.py:454`, `config.py:462`) : `jobs/` n'importe pas `post/`, et une connaissance vit à un seul endroit.
- `is_writable_url` (`src/k_b/post/digest_sheets.py:150`) n'écrit plus en autolien une URL qui contient `~~~` :
  sinon la descente aurait refusé toute la fiche du sujet et du jour pour une seule source.

Et un test par écrivain fabrique une fiche à partir d'un texte piégé, puis vérifie que `find_sheet_text_refusal` la
laisse passer (`tests/post/test_digest_sheets.py:525`, `test_top_sheets.py:601`, `test_trend_report_sheets.py:596`).

### 6. Un blob refusé n'arrête rien ; le code de sortie le dit

`download_watch` (`download_watch_sheets_command.py:113-125`) copie fiche après fiche ; seule une erreur du stockage
arrête la boucle. Un nom refusé, un texte refusé, une fiche non écrite (un dossier remplacé par un fichier, un
temporaire laissé) sont comptés dans `DownloadResult` et la suite continue. Le code final vient de la règle commune
(`src/k_b/commands/exit_codes.py:84-89`) :

```python
    if not has_failed:
        return ExitCode.SUCCEEDED
    return ExitCode.PARTIAL_FAILURE if has_done else ExitCode.FAILED
```

`has_done` (`watch_download.py:129-132`) est vrai si une fiche de `watch` est dans `veille/`, copiée maintenant ou
avant : 4 quand une partie a échoué et une autre est là, 1 si rien ne l'est. La ligne de résultat (`print`) compte
chaque issue et ses raisons : `5 blobs listed: 1 copied, 1 already there, 1 left to the next run, 1 left aside
(sheet_folder_unknown: 1), 1 refused (sheet_name_refused: 1), 0 failed` (`watch_download.py:237-247`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le SDK (`azure-storage-blob`, déjà installé) et `AzureCliCredential` | Chaque nom se contrôle avant toute écriture ; `az` est sur le Mac, AzCopy non ; rien n'écrit de journal ni de plan qui cite les noms ; seuls des appels au conteneur, comme les jobs. Proposé par la session, validé par Sabine (journal ADR, 2026-11-10, « Le Mac : les fiches de `watch` par le SDK (#424) ») | `azcopy copy --recursive --overwrite=false`, l'outil du plan du 06/11 : AzCopy bâtit lui-même le chemin local à partir du nom. `azcopy list` puis `--include-path` : deux outils et une sortie texte à lire |
| `AzureCliCredential` seul | La commande ne doit agir que par le compte d'`az login`. Choix de code, non débattu au plan | `DefaultAzureCredential` : une chaîne qui essaie d'autres sources (variables d'environnement, identité managée) avant `az` ; on ne saurait plus par quel compte on agit |
| Une liste fermée de noms, chemin reconstruit | Un nom non fiable ne touche jamais le système de fichiers | Nettoyer le nom (retirer `..`, normaliser) : un nettoyage oublie toujours un cas ; refuser est plus sûr que corriger |
| Dossier inconnu : laissé de côté ; autre nom : refusé, sans bloquer les autres | Sabine n'a que Reader sur `watch` : un seul blob inattendu, qu'elle ne peut pas supprimer, bloquerait tous ses passages pour toujours. Remarque de tn-orchestrateur, validée par Sabine | Arrêter tout au premier refus |
| Code 4 ou 1 par `find_exit_code` | La règle commune des commandes faites de parties. Tranché par time-knight | Un code propre à la commande |
| Une fiche présente n'est jamais remplacée, par `write_new_sheet` | Le critère de #424 ; une seule règle des liens pour les écrivains du coffre | Déplacer `vault_files` dans `core/` (les trois écrivains à toucher) ; recopier ses contrôles dans `jobs/` |
| Refuser le Markdown actif, par la parité des `\` | Une requête Dataview (DQL), active par défaut, lirait tout le coffre ; kb n'écrit aucun de ces motifs sans l'échapper. Tranché par time-knight sur la revue de sécurité, sous la délégation de Sabine du 15/10 | Refuser une clôture seulement en début de ligne (`> ~~~` en ouvre une aussi) ; compter sur le seul réglage JavaScript de Dataview, qui ne coupe pas DQL ; un parseur Markdown complet : une dépendance nouvelle |
| Références de caractère et `\` dans un autolien refusés ; URL avec `~~~` écrite « (sans URL) » | Une référence redonnait le contrôle bidirectionnel que kb retire. Tranché par time-knight sur les deuxième et troisième revues | Échapper `~` dans les descriptions des tops ; une regex des références plus étroite que celle des écrivains (règle de Sabine du 2026-10-21 : la descente refuse exactement ce qu'ils échappent) |
| Bornes 4 000 000 octets et 20 000 blobs | Borner ce qu'une identité de job peut faire écrire sur le Mac (OWASP API4:2023) | Pas de borne ; une borne d'octets par passage (parade notée, pas faite) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : `4198 passed, 337 deselected` (2026-11-10) | Rien d'autre n'a cassé |
| `uv run ruff check --no-cache` : `All checks passed!` ; `ruff format --check` : `339 files already formatted` ; `mypy --strict src` : `no issues found in 176 source files` | Contrôles du dépôt verts |
| `test_a_name_out_of_the_closed_list_is_not_a_sheet`, 16 noms piégés (`tests/jobs/test_watch_download.py:61`) | `../`, chemin absolu, `\`, `//`, `/` ou retour à la ligne final, chiffres arabes-indiens, date mal écrite ou impossible, trois niveaux, nom caché, `.MD`, fiche hors de tout dossier : aucun n'est une fiche |
| `test_a_trapped_name_is_refused_by_its_place_and_the_sheets_beside_it_are_copied` (`tests/commands/test_download_watch_sheets_command.py:162`) | `models/../../escaped.md` n'est ni téléchargé ni écrit nulle part, le journal dit `blob 1 of 2 refused: sheet_name_refused` sans le nom, la fiche voisine est copiée, code 4 |
| `test_a_watch_of_trapped_names_only_fails_with_1` (`:180`) | Rien de copié : code 1 |
| `test_a_second_download_asks_no_blob_and_copies_nothing` (`:131`) | Critère de #424 : second passage, 0 téléchargement, `0 copied, 2 already there` |
| `test_a_sheet_changed_on_the_mac_is_neither_downloaded_nor_replaced` (`:147`) | Critère de #424 : la fiche modifiée garde ses notes |
| `test_veille_as_a_symbolic_link_…` et `test_a_folder_of_veille_as_a_symbolic_link_…` (`:197`, `:213`) | Rien n'est écrit à travers un lien |
| `test_a_text_kb_never_writes_is_refused`, 28 cas (`test_watch_download.py:200`) | Chaque refus de texte, dont `\\` puis un accent grave (parité paire, non échappé) |
| `test_the_markdown_kb_writes_is_a_sheet` (`:223`) et les trois tests `…_passes_the_check_of_the_download` de `tests/post/` | Ce que kb écrit, textes piégés compris, passe : pas de faux refus sur les fiches réelles |
| `test_the_folders_of_watch_are_those_the_writers_of_veille_write_in` (`test_download_watch_sheets_command.py:100`) | La liste fermée est celle des trois `find_sheets_dir` de `post/` : un sujet ajouté sans elle fait échouer ce test |
| `test_a_sheet_larger_than_the_bound_…`, `test_a_listing_longer_than_the_bound_…` (`test_watch_download.py:117`, `:131`) | Les deux bornes |
| `test_a_blob_changed_since_the_listing_is_left_to_the_next_run` (`test_download_watch_sheets_command.py:280`) | La version listée seule est téléchargée |
| `test_without_an_account_logged_in_nothing_is_listed_and_kb_exits_with_1` (`:291`) | Sans `az login`, aucune requête au conteneur |
| `test_the_download_stops_on_sigterm` (`:346`) | La commande est dans `COMMANDS_STOPPED_BY_SIGTERM` (règle 6 de `poc.md`) |

Tous ces tests simulent le stockage (`FakeContainer`, `tests/jobs/storage_fakes.py`) : aucun ne parle à Azure.

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas AzCopy, l'outil prévu ?** Parce qu'AzCopy écrit le fichier local au chemin que lui donne le nom du
   blob : on ne peut pas contrôler un nom avant l'écriture. Avec le SDK, le nom est lu, validé, et le chemin
   reconstruit par kb (`download_watch_sheets_command.py:136-137`). En plus, AzCopy n'est pas installé et tient des
   journaux qui citeraient les noms.
2. **Un job détourné dépose `models/../../.zshrc`. Que se passe-t-il ?** `SHEET_NAME.fullmatch` échoue : le blob
   est refusé, cité par sa position, jamais téléchargé ; les autres fiches sont copiées ; code 4
   (`watch_download.py:182-185`).
3. **kb échappe déjà le Markdown en écrivant les fiches. Pourquoi le refuser encore au téléchargement ?** Défense en
   profondeur : l'échappement protège contre un texte de source piégé ; le refus protège contre une identité de job
   qui écrirait directement dans `watch`, sans passer par les écrivains. Les deux règles sont tenues ensemble par les
   tests `…_passes_the_check_of_the_download`.
4. **Sabine supprime une fiche du coffre. Et après ?** Elle revient au passage suivant tant que `watch` la porte :
   limite assumée (constat 12 de #424). Parade : la supprimer dans `job-data`, puis dans `watch` (rôle temporaire),
   puis sur le Mac (README, « Les fiches en ligne sur le Mac » ; registre, durée de conservation).
5. **Pourquoi ne pas tout arrêter au premier blob refusé ?** Sabine n'a que la lecture sur `watch` : elle ne pourrait
   pas retirer le blob fautif, et plus aucune fiche ne descendrait. Le refus reste visible (code 4 ou 1, ligne de
   journal par position).

## Zones non vérifiées

- **Aucun essai contre Azure.** `AzureCliCredential` sur un vrai `az login`, la liste et le téléchargement avec le seul
  rôle Storage Blob Data Reader sur `watch` : tout est simulé. L'essai réel attend la première fiche publiée par #330 ;
  la PR l'attend pour être fusionnée.
- **Qu'Obsidian décode une référence de caractère dans un autolien comme cmark-gfm** : non vérifié (journal ADR) ; le
  refus vaut dans les deux cas.
- **La liste du Markdown actif** vient des revues et des réglages de Dataview et de Templater lus le 2026-11-10, pas
  d'une lecture d'Obsidian ni de chaque plugin installé dans le coffre de Sabine. Un plugin qui agit sur un fichier neuf
  (Templater, « Trigger Templater on new file creation ») reste hors de ce contrôle ; la vérification de ses réglages
  et de ceux de Dataview est à faire par Sabine sur son coffre.
- **4 000 000 octets** : le double d'une réponse de l'API IA non échappée, supposé, pas mesuré.
- **`az` reçoit tout l'environnement** chargé par `uv run --env-file`, secrets du `.env` compris : lu dans
  azure-identity 1.27.0 (`_credentials/azure_cli.py:278`, `"env": dict(os.environ, AZURE_CORE_NO_COLOR="true")`) ;
  ce qu'`az` en fait n'est pas vérifié. Parade (un fichier d'environnement réduit) non faite.
- **Les fenêtres de l'écriture du coffre** restent celles de `post/vault_files.py` : un lien posé après le contrôle est
  suivi (README, « Limites »).

## Ce qui reste

- L'essai réel, à la première fiche de #330 (un second passage qui copie 0 fiche, une fiche modifiée gardée).
- `make upload-library` (clips et Zotero vers Azure) : #542.
- Les parades notées, pas faites : un fichier d'environnement réduit pour cette cible, une borne d'octets par passage.
- La vérification, par Sabine, des réglages de Dataview (JavaScript désactivé) et de Templater (déclencheur inactif
  ou `veille/` exclu).
