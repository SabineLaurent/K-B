# Revue de `src/k_b/etl/` — rapport

Revue du 2026-10-24, branche `refactoring/etl`, commit `f8b6d33`, arbre propre. Première revue de
l'ETL dans son entier : les 4 700 lignes de `src/k_b/etl/` et `src/k_b/etl/sources/`, et non les
seuls commits du chantier 11.

**Ce qu'elle cherchait** : ce qui peut casser. Bugs, cas d'erreur mal gérés, entrées externes mal
validées, sécurité, données personnelles, et tout écart avec `.claude/rules/`. La lisibilité est
hors périmètre : elle est relevée dans `docs/refactoring/lisibilite.md`.

**Comment elle a été faite.** Trois sous-agents sans aucun contexte des décisions de la session,
un par lot, chacun lisant ses fichiers en entier, lisant d'abord `.claude/rules/`, et lançant les
commandes de vérification des règles :

1. les stages et leurs aides : `pipeline`, `extract`, `transform`, `raw_reading`, `normalize`,
   `load`, `file_writing`, `withdrawals`, `import_log`, `rejections`, `raw_files` ;
2. la frontière du système de fichiers et la composition : `raw_store`, `raw_purge`,
   `source_contract`, `source_kinds`, `collected_sources`, `tops` ;
3. la frontière réseau et les sources : `http_download`, `user_agent`, les onze sources,
   `github_api`, `tracked_repositories`.

Aucun fichier du dépôt n'a été modifié, aucun test `-m e2e` lancé, aucune source réelle appelée.
Chaque constat a ensuite été **revérifié par la session** avant d'entrer ici. Les constats sont
rapportés, pas corrigés (`methode.md`).

**Niveau de preuve**, donné pour chaque constat, parce qu'ils ne sont pas tous établis au même
degré :

- **Reproduit** : exécuté dans cette session, sortie à l'appui.
- **Lu** : le mécanisme est établi par lecture du code ; aucune supposition.
- **Sonde de la revue** : un sous-agent l'a exécuté et donne sa sortie ; la session ne l'a pas
  rejoué, seulement relu le code.

## Le constat d'ensemble

La validation des entrées et la frontière réseau sont solides : préfixe d'URL de confiance
contrôlé avant la requête **et** après la redirection, bornes de taille, jeton jamais transmis à
une redirection, valeurs citées par `quote_value`, auteurs écartés conformément au registre, pas
d'injection SQL, pas de code dynamique, pas de traversée de chemin.

Le point faible est **ce qui arrive après un refus**. Deux règles se combinent mal :

- une source qui lève garde sa date de dernière collecte (`extract.py:61-63`, voulu : la règle 1
  de `conventions.md` veut qu'une source en échec ne fasse pas avancer sa date) ;
- la fenêtre de collecte suivante repart de cette date.

Donc **toute donnée amont durablement invalide devient un échec permanent**, qui se répète à
chaque lancement. `MEMORY.md` ne consigne qu'une occurrence, arXiv (#71) ; la revue en trouve
trois autres de la même forme : TLDR (B2, le plus grave), les alertes GitHub (I1), et GH Archive
pendant seize jours avec un coût BigQuery à chaque fois (I3). C'est une famille, pas quatre
accidents : elle mérite une décision de conception, pas quatre correctifs.

À côté de cela, un défaut d'une autre nature : **rien ne vérifie la complétude d'un catalogue
d'état** (B1), alors que la règle 1 de `conventions.md` l'impose déjà pour un classement.

---

# 1. Constats retenus

## Bloquants

### B1. Un catalogue CISA KEV tronqué retire des CVE en masse, et l'import rapporte un succès

`src/k_b/etl/withdrawals.py:30-36` ; `src/k_b/etl/file_writing.py:92-97` ; chemin d'arrivée :
`src/k_b/etl/http_download.py:47-49`

**Observé.** `mark_withdrawn_vulnerabilities` marque retirée toute CVE absente du catalogue, sous
deux conditions seulement : `if not present_cve_ids or raw_file.rejection_count: return 0`.
Aucun contrôle de complétude : ni nombre de lignes, ni comparaison avec le catalogue précédent. Un
CSV coupé en plein milieu reste un CSV valide : toutes ses lignes parsent, aucune n'est rejetée,
`rejection_count` vaut 0.

**Risque.** Les CVE absentes du fichier tronqué sont marquées retirées ; `kb search`, « quoi de
neuf » et les fiches de veille les omettent. La collecte complète du lendemain lève le retrait
mais **estampille un `revised_at` faux** sur chaque ligne, durablement, alors que le contenu n'a
pas changé. Entre-temps la purge a supprimé les bruts antérieurs (`cisa_kev` est dans
`LATEST_ONLY_FOLDER_KEYS`), donc la preuve. L'import sort en SUCCEEDED à chaque étape.

Le chemin d'arrivée est atteignable **depuis le réseau** : `download()` lit `max_bytes + 1` et ne
contrôle que la borne haute, jamais la longueur annoncée ; une réponse coupée en cours de corps est
acceptée telle quelle.

**Gravité** : bloquant — corruption de données atteignable, rapportée comme un succès.

**Reproduit** (script de la session, base neuve, fixture réelle `cisa_kev_extract.csv`, 4 lignes) :

| Import | Résultat |
|---|---|
| catalogue entier | `item_count=4, rejection_count=0, withdrawn_count=0` |
| catalogue coupé après 1 ligne sur 4 | `rejection_count=0`, **`withdrawn_count=3`** ; `withdrawn_at=2026-10-06T09:30:00Z` sur les 3 CVE absentes |
| catalogue entier de nouveau | retrait levé, **`revised_at=2026-10-07T09:30:00Z` posé à tort** sur les 3 lignes |

Et pour la lecture courte, **reproduit** aussi : `http.client` rend 37 octets quand l'en-tête
annonce `Content-Length: 1000000`, sans lever.

**Aucun test ne couvre ce cas.** `tests/etl/test_load.py` couvre « une ligne rejetée ne retire
rien », « une ligne refusée par la base ne retire rien », « un catalogue plus ancien ne retire
rien » — jamais un catalogue dont toutes les lignes sont valides mais qui est incomplet.

**Reste à vérifier** : si `cisa.gov` sert le catalogue en `Transfer-Encoding: chunked`,
`http.client` lève `IncompleteRead` et le cas ne passe plus par le réseau ; il reste atteignable
par un brut tronqué sur le disque. Non vérifiable sans réseau.

### B2. Une seule journée en erreur bloque une édition TLDR à chaque collecte, définitivement

`src/k_b/etl/sources/tldr.py:128-142` ; `src/k_b/etl/sources/tldr.py:186-196` ;
`src/k_b/etl/extract.py:61-63`

**Observé.** `read_pages` parcourt chaque jour de la fenêtre. Dans son `except Exception`, seule
une redirection vers la page d'accueil de l'édition est sautée (`continue`) ; toute autre erreur
reçoit une note et est **relancée**, donc `fetch` échoue en entier. `collect_all_sources`
journalise et passe à la source suivante, mais `last_collection_dates[source.name] = now` n'est
exécuté que dans la branche `else`. `list_days_to_collect` repart de
`last_collected_at.astimezone(UTC).date()` : la journée fautive reste dans la fenêtre à tous les
lancements suivants.

**Risque.** Si `tldr.tech` répond durablement autre chose qu'une édition ou une redirection pour un
jour donné (404, 500, page au-delà de `MAX_PAGE_BYTES` = 1 Mio), l'édition n'est **plus jamais
collectée**. Chaque collecte retélécharge les jours précédents, les jette, échoue sur le même jour,
et recommence le lendemain avec une requête de plus. Les éditions des jours **après** le jour
fautif sont téléchargées puis jetées elles aussi. Même forme que #71 (arXiv), non consignée.

Le mécanisme de « jour abandonné » existe déjà (`tldr.py:99-108`) mais ne s'applique qu'aux refus
du lecteur, jamais à une erreur HTTP, de taille ou de réseau.

**Gravité** : bloquant — collecte qui échoue à chaque fois, données perdues pour les jours suivants.

**Lu** (la relance, la fenêtre, et la branche `else` d'`extract.py` : les trois sites lus par la
session). **Sonde de la revue**, sans réseau, `download` et `current_day` remplacés :

```
dernière collecte 2026-10-18 : fetch lève HTTPError 404 ; 3 requêtes faites, 2 pages jetées
dernière collecte 2026-10-21 (après le jour fautif) : fetch -> 3 jours lus
```

`tests/etl/sources/test_tldr.py:314` couvre la levée, pas la conséquence sur la date ; aucun test
ne couvre la répétition.

## Importants

### I1. Une alerte GitHub invalide, seule dans sa fenêtre, bloque la source définitivement

`src/k_b/etl/sources/github_advisories.py:67-74` ; `src/k_b/etl/source_contract.py:61-69`

**Observé.** La requête filtre `reviewed >= last_collected_at - 1 jour`. `check_not_all_invalid`
lève si la page n'a que des rejets. La date ne bouge pas, donc la borne basse de la fenêtre ne
bouge pas : l'alerte fautive y reste. Le cas **mixte** est traité explicitement et correctement
(`github_advisories.py:84-87` rend la page pour que le rejet atteigne le journal d'import) ; c'est
le cas « toutes invalides » qui est fatal.

**Risque.** Une seule alerte invalide (GHSA mal formé, `severity` inconnue, `html_url` hors du
préfixe, `vulnerabilities` sans nom de paquet, `github_reviewed_at` absent) qui est la seule de sa
fenêtre fait échouer `github_advisories_<écosystème>` à chaque collecte, sans fin, jusqu'à ce
qu'une alerte valide entre dans la fenêtre. **Gravité** : important. **Lu.** Aucun test ne couvre
la répétition.

### I2. TLDR n'a aucun plafond de rattrapage, contrairement à GH Archive

`src/k_b/etl/sources/tldr.py:186-196` ; à comparer à `src/k_b/etl/sources/gh_archive.py:45,198-205`

**Observé.** `list_days_to_collect` rend un jour par jour écoulé depuis la dernière collecte, sans
borne ; `read_pages` fait un `download` par jour avec deux secondes de pause. Trois éditions sont
suivies. GH Archive a reçu `MAX_CATCH_UP_WINDOWS = 15` pour ce motif exact (décision du
2026-10-11).

**Risque.** Après un arrêt d'un mois : 93 requêtes vers `tldr.tech` et environ 3 minutes de pauses
en un seul `kb collect` ; après un an : 1 098 requêtes et 36 minutes. Combiné à B2, chaque échec
recommence tout. RGESN 1.6 (« limiter le volume lu par requête »). **Gravité** : important.
**Sonde de la revue** : `365 jours -> 366 requêtes, >= 730 s de pauses` contre `15 fenêtres
(plafond 15)` pour GH Archive. **Lu** pour l'absence de plafond et la présence de celui de
GH Archive.

### I3. Un résultat BigQuery refusé fait repayer la requête chaque jour pendant seize jours

`src/k_b/etl/sources/gh_archive.py:151-170` ; `:309-342` ; `:198-205`

**Observé.** `fetch` lance le dry run, puis la requête facturée, encode le résultat, **puis** le
valide par `read_trends`. Une ligne invalide lève après la dépense. Rien n'est écrit, la date ne
bouge pas, et la fenêtre fautive reste dans les quinze fenêtres les plus récentes.

**Risque.** Jusqu'à seize collectes consécutives relancent une requête réelle plafonnée à 2 Go
facturés, pour un résultat jeté, et seize jours de tendances sont perdus. Non bloquant : le plafond
de rattrapage finit par purger la fenêtre. `MEMORY.md` dit déjà de ne pas relancer cette requête à
la légère. **Gravité** : important. **Lu.** **Reste à vérifier** : si un `repo.name` de GH Archive
peut réellement sortir de `[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+`.

### I4. Une page pleine fait avancer la fenêtre : au-delà de 100 entrées, la perte est silencieuse

`src/k_b/etl/sources/github_releases.py:82-95` ; `src/k_b/etl/sources/github_advisories.py:86-99`

**Observé.** Les deux sources ne lisent que la première page (100 entrées). Quand la page est
pleine **et** que la plus ancienne entrée lue est postérieure à la dernière collecte — donc qu'il
existe certainement des entrées non lues — le code émet un `logger.warning` puis **rend quand même
la page**. La collecte réussit, la date avance, la page 2 ne sera jamais demandée.

**Risque.** Perte irrécupérable de releases ou d'alertes dès que plus de 100 entrées tombent entre
deux collectes, avec un avertissement pour seule trace. La limite est documentée
(`docs/2026-10-04-flux-donnees.md:62`), la perte ne l'est pas, et aucune issue ne la porte — alors
que la limite équivalente d'arXiv est portée par #71. **Gravité** : important. **Lu.**

### I5. `write_new_raw_file` vérifie puis écrit : un fichier brut peut être écrasé en silence

`src/k_b/etl/raw_store.py:158-162` ; `src/k_b/etl/raw_store.py:137`

**Observé.** `if path.exists(): raise FileExistsError` puis `write_file_atomically`, qui finit par
`os.replace`, lequel écrase sans condition. Entre la vérification et le renommage : un `mkdir`, la
création du temporaire, l'écriture du contenu, un `fsync`. La fenêtre dure le temps d'écrire le
fichier. La docstring affirme pourtant « raw/ is immutable: a raw file is written once and never
overwritten ».

**Risque.** Deux `kb collect` qui se chevauchent sur la même source dans la même seconde (les noms
de collecte sont à la seconde) : les deux passent `exists()`, le second `os.replace` écrase le
premier, les deux rapportent un succès, aucune trace. Combiné au problème connu des dates
(`MEMORY.md`, « Deux collectes en même temps perdent des dates », #200), la collecte à la fenêtre
large peut perdre contre celle à la fenêtre étroite, et l'état dit que la source est collectée.
Pour un catalogue d'état, le fichier écrasé était le seul brut de son état. **Gravité** : important.
**Lu** pour la structure vérifier-puis-écrire. **Sonde de la revue** pour la course elle-même, avec
`os.replace` ralenti par une barrière. `test_write_new_raw_file_refuses_to_overwrite` ne couvre que
le cas séquentiel.

### I6. `read_each_entry` fait `str(error)` sur une `ValueError` qui peut être une `ValidationError`

`src/k_b/etl/source_contract.py:54-55`

**Observé.** `except ValueError as error: rejection_reasons.append(str(error))`.
`pydantic.ValidationError` **est** une sous-classe de `ValueError` (vérifié : `True`). La règle 5
de `poc.md` dit : « Une `ValidationError` de Pydantic n'est jamais journalisée ni gardée telle
quelle […] jamais par `str(error)` ni par `{error}` ». Le `grep` de contrôle de cette règle ne peut
pas voir ce passage, puisque l'`except` porte sur `ValueError`.

**Risque.** Aucune fuite aujourd'hui : les modèles construits sous `read_each_entry` portent tous
`hide_input_in_errors=True`. Mais l'invariant n'est ni écrit dans le contrat ni testé, et la
convention n'est pas universelle : **`TrendRow` (`items.py:536`) ne porte pas ce réglage**. Un
modèle sans lui recopierait la valeur reçue — pour Zotero et les clips, cela veut dire **un
auteur** (registre, fiches 1 et 2 : « jamais écrit dans un journal »). C'est le seul endroit
générique qui traite tous les rejets d'entrée : la défense en profondeur y manque.
**Gravité** : important (écart à une règle du dépôt). **Lu** et **reproduit** pour
`issubclass(ValidationError, ValueError)` et pour l'absence du réglage sur `TrendRow`.
`tests/etl/test_source_contract.py` n'exerce `read_each_entry` qu'avec un `ValueError` nu.

### I7. Le nom d'un fichier brut injecte des lignes dans le journal de fonctionnement

`src/k_b/etl/rejections.py:19` ; `src/k_b/etl/raw_reading.py:113`, `:143`, `:188`

**Observé.** `reject()` écrit `logger.warning("rejected from %s: %s", raw_file_path, reason)` : ni
le chemin ni le motif ne passent par `quote_value`. Et les motifs construits par `read_collection`,
`read_page` et `read_trend_file` sont `f"{type(error).__name__}: {error}"` : le message de
`strptime` recopie le nom du fichier ou du dossier **tel qu'il est sur le disque**, retours à la
ligne compris.

**Risque.** Un fichier déposé dans `raw/<dir>/<source>/` avec un retour à la ligne dans son nom
écrit des lignes forgées dans `logs/kb.log` et sur la sortie d'erreur. La règle 3 de
`conventions.md` l'interdit explicitement, avec l'OWASP Logging Cheat Sheet en *pourquoi*. Le même
module le fait correctement dix lignes plus haut pour un dossier sans sorte
(`raw_reading.py:63-66`), et **ce cas-là a son test** ; le chemin de rejet n'en a pas. Le journal
d'import est protégé par le JSON ; `kb.log` ne l'est pas. **Gravité** : important.
**Lu** ; **sonde de la revue** pour les deux lignes forgées. Note pour la correction :
`tests/etl/test_transform.py:385` fixe le comportement actuel.

### I8. Le chemin absolu du dossier de données part dans `import-log.jsonl` et dans `kb.log`

`src/k_b/etl/raw_reading.py:109-115`, `:139-144`, `:186-189` ; l'outil existant :
`src/k_b/commands/run_log.py:90`

**Observé.** Les trois `except … as error` transforment l'erreur en motif par
`f"{type(error).__name__}: {error}"`. Le texte d'une `OSError` nomme le fichier **en chemin
absolu** (reproduit : `FileNotFoundError: [Errno 2] No such file or directory: '/Users/…'`). Le
motif va au journal d'import (champ `reason`) et au journal de fonctionnement.

**Risque.** Un `chmod` malheureux, un disque en erreur, et le journal d'import — gardé sans durée,
voir M8 — contient l'arborescence de la machine. Le dépôt a l'outil fait pour cela :
`describe_os_error`, « An OSError by its type and its reason, never by its text, which names a
file », utilisé par trois commandes et **pas ici**. Écart à la règle 3 de `conventions.md`.
**Gravité** : important. **Lu** et **reproduit** pour le texte de l'`OSError`. Le test existant
n'assertionne que `reason.startswith("PermissionError")` : il ne voit pas le chemin.

### I9. Un dossier de source illisible arrête tout l'import, un dossier de collection non

`src/k_b/etl/raw_reading.py:74-79`, `:211` ; à comparer à `:109-115`

**Observé.** `list_collections` appelle `list_visible_entries(source_dir)` **hors de tout `try`** ;
`folder.iterdir()` lève l'`OSError` jusqu'à `read_raw_files`, puis `run_import`, qui rend
`ExitCode.FAILED` sans lire **aucune** autre source. Un niveau plus bas, le même cas est rejeté
seul par `read_collection`, qui a son `except (ValueError, OSError)` — et son test.

**Risque.** Un seul dossier de `raw/automated_watch/` devenu illisible bloque tous les imports : le
brut s'accumule à chaque lancement quotidien jusqu'à intervention manuelle. Asymétrie avec l'esprit
de la règle 1 de `conventions.md`. Le message porte en plus le chemin absolu (I8).
**Gravité** : important. **Lu** ; **sonde de la revue** pour la levée. Aucun test ne couvre ce cas.

### I10. La trace de `logger.exception` republie le message brut, et le test ne le voit pas

`src/k_b/etl/extract.py:52-59` ; `tests/etl/test_extract.py:397`

**Observé.** La ligne datée est correctement citée (`quote_value(str(error))` et les notes), mais
`logger.exception` ajoute la trace, dont la dernière ligne recopie le message **brut**. Un message
multi-ligne écrit donc des lignes non préfixées dans `kb.log`. Le commentaire du code assume la
répétition ; sa conséquence pour la règle 3 ne l'est pas.

**Risque.** La protection repose entièrement sur le fait que toutes les sources lèvent un message
d'une seule ligne et borné. C'est vrai aujourd'hui, mais rien ne le tient : une source nouvelle qui
laisse passer `{error}` d'une bibliothèque réintroduit l'injection. Et le test censé couvrir le cas
n'assertionne que `record.getMessage()`, **qui n'inclut pas la trace** que le formateur ajoute à la
sortie réelle : il donne une assurance qu'il ne prouve pas. **Gravité** : important (écart à une
règle, et un test qui n'établit pas ce qu'il annonce). **Lu** ; **sonde de la revue** pour les
lignes forgées par la trace.

### I11. Une raison de rejet non bornée part dans `import-log.jsonl` et dans `kb.log`

`src/k_b/etl/sources/clipping.py:311-316` ; `src/k_b/etl/sources/zotero.py:414-420` ;
`src/k_b/etl/raw_reading.py:150-160` ; la fonction qui existe pour cela :
`src/k_b/core/quoting.py:45`

**Observé.** Les raisons de rejet interpolent la `ValidationError` en entier. `without_values`
retire bien les valeurs mais garde **une entrée par erreur**. `locate_first_error`, qui rend « la
place et le type de la première erreur, sur une ligne […] le compte quand il y en a plus (poc.md,
règle 5) », n'est utilisée que par `src/k_b/post/ai_api_client.py:227`, jamais dans l'ETL.

**Risque.** Une entrée portant des milliers de valeurs refusées une à une produit une raison de
rejet de plus d'un mégaoctet, écrite en une ligne JSON dans `import-log.jsonl`, et le message
complet part aussi dans la trace de `logger.exception` (I10). L'extrait Zotero n'a **aucune borne
de taille** : le même mécanisme y est sans plafond d'entrée. Aucune valeur ne fuit ; c'est une
amplification de journal, contraire à l'esprit de la règle 3 (« citée tronquée à une longueur
fixe ») et à la règle 5 de `poc.md`, avec une fonction déjà écrite et non employée. Les journaux
partent vers un service en ligne au 08/11. **Gravité** : important.
**Reproduit** :

```
  100 erreurs : str(without_values(error)) ->     13 617 caractères | locate_first_error ->  29
3 000 erreurs : str(without_values(error)) ->    412 918 caractères | locate_first_error ->  30
9 000 erreurs : str(without_values(error)) ->  1 240 918 caractères | locate_first_error ->  30
locate_first_error rend : tags.0 (int_type), 9000 errors
```

### I12. Deux dépôts suivis peuvent partager un dossier brut et une date de collecte

`src/k_b/etl/sources/github_releases.py:54` ; `src/k_b/etl/extract.py:97-102`

**Observé.** Le nom de source est `re.sub(r"[^a-z0-9]+", "_", repository.lower())` préfixé. La
transformation n'est pas injective, et **rien ne vérifie l'unicité des noms de `SOURCE_KINDS`**
(aucun test dans `tests/etl/test_source_kinds.py` ni `tests/architecture/`).

**Risque.** Ajouter à `TRACKED_REPOSITORIES` un dépôt dont le nom assaini collide avec un existant
donne deux sources qui partagent le même dossier de `raw/` **et** la même clé de
`collection_state.json` : la seconde lève `FileExistsError` à chaque collecte, et les deux dépôts
partagent une seule date de dernière collecte. Les quatre dépôts actuels ne collident pas ; le
déclencheur est une modification de configuration banale, sans garde-fou. **Gravité** : important.
**Reproduit** :

```
'owner-x/repo' -> github_releases_owner_x_repo
'owner/x-repo' -> github_releases_owner_x_repo   même dossier et même clé d'état : True
'A/b' et 'a/B' -> github_releases_a_b            même dossier et même clé d'état : True
```

### I13. La requête Zotero exige SQLite ≥ 3.44, exigence écrite nulle part ailleurs qu'en docstring

`src/k_b/etl/sources/zotero.py:106-158` ; `:184`

**Observé.** Les quatre agrégats de `EXTRACTION_QUERY` utilisent `json_group_array(… ORDER BY …)`,
syntaxe apparue dans SQLite 3.44 (vérifié : 4 occurrences, `ORDER BY` aux lignes 108, 118, 127,
146). La seule trace de l'exigence est la docstring de `ZoteroQueryFailedError` et un commentaire de
test. Rien ne la déclare ni ne la contrôle : pas de minimum dans `pyproject.toml`, pas de
vérification au démarrage.

**Risque.** Sur une image dont `sqlite3.sqlite_version < 3.44`, la source Zotero échoue à **chaque**
collecte avec un message « syntax error » qui ne nomme pas la cause. Le POC en conteneurs et Azure
au 08/11 sont exactement les étapes où l'image de base est choisie. **Gravité** : important.
**Reproduit** : version locale 3.50.4 (convient) ; `grep -rn "3\.44|sqlite_version" src tests
pyproject.toml` ne renvoie que la docstring et le commentaire de test. **Reste à vérifier** :
l'image de base du 29/10, qui n'existe pas encore.

### I14. `RawStore` liste des clés que `find_path` refuse ensuite

`src/k_b/etl/raw_store.py:84-88` ; `:93-107` ; `:68-74`

**Observé.** `list_file_keys` construit `f"{folder_key}/{path.name}"` à partir de `iterdir()`, sans
filtrer le nom ; `find_path` refuse toute clé contenant un `\`, caractère de nom de fichier
parfaitement légal sous POSIX. Le store rend donc des clés que son propre `read`, `has_file` et
`delete` refusent.

**Risque.** Deux chemins : `read_latest` prend `keys[-1]` et lève `ValueError`, que
`ZoteroSource.fetch` laisse remonter — **Zotero échoue à chaque collecte** et sa date n'avance
jamais, avec un message qui ne dit pas que c'est le nom du fichier ; et `kb write-tops` rapporte
`ranking_unreadable` sur un relevé parfaitement lisible, donc sortie 1 ou 4 à chaque exécution.
Atteignabilité faible : K-B ne nomme jamais ainsi (noms issus de `strftime`, pages de clips en
SHA-256 tronqué) ; il faut un fichier déposé à la main ou par un autre outil.
**Gravité** : important (défaut réel, état collant, message trompeur). **Lu** pour l'incohérence ;
**sonde de la revue** pour les deux conséquences. Le test du refus d'une clé hors du dossier
de données n'essaie que des clés venues de l'extérieur.

## Mineurs

« Preuve » : R = reproduit dans cette session, L = lu dans cette session, S = sonde de la revue.

| # | Constat | Fichier:ligne | Risque | Preuve |
|---|---|---|---|---|
| M1 | `load_last_collection_dates` ne rattrape que `ValueError` ; un JSON trop imbriqué lève `RecursionError`, que `raw_reading.py:139-140` rattrape explicitement pour la même raison (#103). La docstring promet `InvalidCollectionStateError` | `etl/raw_store.py:165-197` | `kb collect` sort en 1 avec un traceback au lieu de 2 avec un message actionnable ; les deux lectures de JSON du dépôt divergent | L + S |
| M2 | `find_path` refuse le vide, l'absolu, `..` et `\`, jamais un **lien symbolique** ; `is_file`, `read_bytes` et `unlink` suivent les liens. Contraste avec `post/vault_files.py:75` (refus explicite) et `sources/clipping.py:236` (`O_NOFOLLOW`) | `etl/raw_store.py:57-91` | Un lien posé sous `raw/` fait lire, lister et **supprimer** hors du dossier de données. Modèle de menace local | L + S |
| M3 | `deleted_count += sum(store.delete(key) for key in …)` : si une suppression lève, le générateur s'arrête, le compte est perdu et le `logger.info` qui suit n'est jamais atteint | `etl/raw_purge.py:37-38` | La procédure de tri du registre (étape 7) annonce « un nombre de fichiers » : la trace manque exactement quand la purge a mal tourné, pour une étape qui supprime des extraits Zotero | L |
| M4 | `find_stream` interpole la valeur sans `quote_value` ; et `find_stream("/a/b/c")` rend `'a'`, car `parts[0]` d'un chemin absolu est `'/'` | `etl/raw_store.py:34-40` | Écart de forme à la règle 3. Branche morte avec les appelants d'aujourd'hui (tous passent un chemin relatif à `raw/`) ; piège pour un troisième appelant | R |
| M5 | `TopEntry` est une dataclass sans aucune contrainte ; `render_sheet` écrit `full_name` et `url` crus, seule `description` passe par `neutralize_text` | `etl/tops.py:9-20` ; `post/top_sheets.py:188` | Aucune faille aujourd'hui (`REPOSITORY_NAME` exclut `[ ] ( ) |` et les retours à la ligne, en `fullmatch`), mais un seul contrôle, loin du point d'usage, contre « défense en profondeur » de `code.md` | L |
| M6 | Le nom du dépôt d'une release hors liste n'est ni tronqué ni échappé | `etl/transform.py:106` | Le contenu en clair est **accepté** par le registre (2026-10-19), donc pas de constat RGPD ; reste la troncature : `RepositoryName` n'a pas de longueur maximale et l'URL est bornée à 2 000 caractères, là où la règle 3 demande 100 | L |
| M7 | `position` compte les entrées **gardées**, alors que les motifs du lecteur portent la position dans le fichier : deux rejets du même fichier peuvent dire « entry 3 » et « line 5 » pour deux entrées différentes | `etl/raw_reading.py:150` ; `etl/source_contract.py:51` | Diagnostic : impossible de remonter d'un rejet d'item à la ligne du brut dès qu'une entrée a été rejetée avant | L |
| M8 | Un `import-log-<horodatage>.jsonl` par import, jamais supprimé par aucun code ; un import sans rien à écrire en produit un quand même | `etl/import_log.py:86-89` ; `etl/pipeline.py:46,80-82` | `conformite.md` : RGESN 1.6 (minimiser la durée même pour une donnée non personnelle) et RGPD (chaque donnée au registre avec sa durée, purge codée et testée). Ces lignes portent `source_item_id`, l'URL d'un clip pour un clip. Le registre ne nomme leur suppression que pour les tests e2e | L |
| M9 | `collect_all_sources` refuse un `now` hors UTC ; `import_raw_files` ne contrôle rien, et met `imported_at` dans le **nom du fichier** par `strftime`, qui suffixe un `Z` | `etl/pipeline.py:66-82` ; `etl/extract.py:37-38` | Nul aujourd'hui (le seul appelant passe `datetime.now(UTC)`) ; asymétrie sur la porte documentée des deux parcours | L |
| M10 | `read_imported_paths` lit sur une connexion qu'il ferme, puis `import_items` en ouvre une autre : rien n'empêche deux `kb import` simultanés | `etl/pipeline.py:83-87` | Le plus probable : le second échoue sur `database is locked`. S'il passe, l'effet est pour l'essentiel idempotent, mais un second journal est produit et les retraits d'un catalogue rejoués. Pendant de la limite connue sur deux collectes | L, non reproduit |
| M11 | La docstring dit « the others are kept as written, in their order », mais le filtre supprime aussi un paramètre **vide**, et le préfixe est sensible à la casse | `etl/normalize.py:26-32` | L'URL stockée n'est pas exactement celle de la source. Idempotent, donc pas de doublon au ré-import. `code.md` : n'affirmer que l'observé, docstrings comprises | R : `?b=1&&c=2` → `?b=1&c=2` ; `?UTM_SOURCE=1` survit |
| M12 | « A commit that fails, or an interruption before the commit, removes the log written » : vrai pour une exception Python, faux pour un SIGKILL ou une coupure entre `write_import_log` (qui a fait son `fsync`) et `connection.commit()` | `etl/load.py:121-126` | Un journal d'import trompeur, gardé indéfiniment (M8). Inhérent : pas de commit atomique entre deux ressources — c'est la docstring qui doit le dire | L, non reproduit |
| M13 | Le jeton est posé tel quel dans l'en-tête. Si sa valeur contient un CR ou un LF, `http.client` refuse l'en-tête — protection utile — mais son message est `'Invalid header value %r' % (values[i],)`, donc **le jeton entier** | `etl/sources/github_api.py:32` ; stdlib `http/client.py:1336` | Fuite de secret dans `logs/kb.log`, sur la sortie d'erreur, et vers un service en ligne au 08/11 (`code.md` : « Secrets : jamais dans les logs »). La fuite est établie, **le déclencheur ne l'est pas** : rien ne `strip()` `KB_GITHUB_TOKEN`, mais qu'un CR/LF survive au chargement de `.env` n'est pas démontré | L (message de la stdlib lu) + S |
| M14 | CISA KEV est la seule source qui passe `last_collected_at` tel quel à `format_datetime(usegmt=True)` et appelle `.date()` sans `astimezone(UTC)` ; les quatre autres font `astimezone(UTC)` d'abord | `etl/sources/cisa_kev.py:86-90,140` | Un `collection_state.json` retouché à la main avec un décalage non nul fait lever `ValueError: usegmt option requires a UTC datetime` à chaque collecte, et décalerait le filtre d'un jour | S |
| M15 | `read_clip_file` ouvre en `O_NOFOLLOW` — la protection marche — mais l'erreur est un `OSError` `ELOOP`, que `read_clip_files` ne rattrape pas (seul `FileNotFoundError` l'est) | `etl/sources/clipping.py:196-201,232-242` | Un clip remplacé par un lien dans la fenêtre de course fait échouer toute la source, alors que les deux courses sœurs sont comptées et sautées. Fenêtre étroite ; un lien persistant est écarté au listage | S |
| M16 | Le garde est `isdigit()` puis `int()` : `'²'.isdigit()` est vrai et `int('²')` lève ; `'١'` est lu comme `1` | `etl/sources/arxiv.py:164-169` | L'échec reste un `ValueError` mais le message est celui de CPython, pas un état nommé (`code.md`) | S |
| M17 | `Paper.version` est lu et converti par `int()`, mais aucun code de `src/` ne le lit ensuite ; un `v` suivi de plus de 4 300 chiffres fait lever et rejette l'entrée | `etl/sources/arxiv.py:188,200` | Un papier écarté de la veille pour un champ que la base ne stocke pas ; champ mort au sens de `code.md` | S |
| M18 | L'identité d'un article TLDR est son rang parmi les éléments `article` ; le jour de la dernière collecte est relu à chaque collecte, par conception | `etl/sources/tldr.py:186-196,242-246` | Si la page gagne un élément `article` entre deux lectures du même jour, les rangs décalent : les connus sont écartés en `already_seen`, le ou les derniers sont écrits une seconde fois. Pas de corruption, grâce à « la première version vue est gardée » | L. **Reste à vérifier** : si `tldr.tech` modifie une page après publication |
| M19 | Dédoublonnage par `if name not in package_names` sur une `list`, construite en entier avant qu'`Item` ne la plafonne à 100 | `etl/sources/github_advisories.py:166-180` | Une réponse hostile de 5 Mio tient environ 163 000 entrées : de l'ordre d'une minute de calcul pour une liste qui sera ensuite refusée. Collecte lente, pas d'arrêt | S : 30 000 noms en 2,35 s |
| M20 | Une `HTTPError` est un objet-réponse ; CISA KEV la ferme pour 304 seulement, les autres sources jamais, et elle est conservée dans `errors_by_source` jusqu'à la fin de `kb collect` | `etl/http_download.py:43` ; `etl/sources/cisa_kev.py:95-99` | Réponse non fermée pendant toute la collecte | L. **Reste à vérifier** : si la socket reste réellement ouverte |
| M21 | Le registre consacre une ligne au texte libre d'une release, mais la ligne « API GitHub » affirme que rien de personnel n'entre en base hors ce cas. Or le `summary` d'une alerte devient `item.title`, est gardé en base et figure dans la liste blanche envoyée au modèle | `docs/registre-traitements.md:29-30` ; `etl/sources/github_advisories.py:186-197` | Inventaire incomplet par asymétrie : du texte libre, qui peut nommer une personne (« reported by … »). Le code minimise correctement (ni `credits` ni l'auteur ne sont lus). À trancher par Sabine : ajouter une ligne, ou expliciter que ce `summary` est couvert | L |
| M22 | La règle 4 de `poc.md` annonce deux sites `tempfile.` pour Zotero ; il y en a **trois** : `remove_left_copies` utilise `tempfile.gettempdir()` | `etl/sources/zotero.py:248` | La règle est tenue (le troisième site est prévu par le registre, procédure de tri étape 4), mais sa liste de référence est incomplète, et `plan.md` §7 n'annonce qu'un changement de chemin | R |
| M23 | La règle 1 de `poc.md` interdit « aucun nouveau `PRAGMA`, `json_each`… » sans dire qu'elle ne vise que la base K-B ; seules ses commandes de vérification le disent. La requête Zotero en emploie légitimement | `.claude/rules/poc.md` règle 1 ; `etl/sources/zotero.py:106-158,174,324` | Ambiguïté de texte : un lecteur pressé croit la règle enfreinte, ou s'interdit la syntaxe utile sur une base externe | L |
| M24 | Un brut dont le nom n'est pas une heure de collecte, ou une page illisible, n'est jamais enregistré : il est re-rejeté à **chaque** import, pour toujours, et ajoute une ligne à chaque journal | `etl/raw_reading.py:101-115,177-183` | Bruit permanent dans les journaux. Les docstrings l'assument | L |
| M25 | `page_path.read_bytes()` lit une page entière sans borne, et `read_raw_files` matérialise tous les items de tous les bruts non importés avant la première écriture. Les bornes existent à la collecte, aucune à l'import | `etl/raw_reading.py:138` ; `etl/transform.py` | Pas un déni de service au volume mesuré au registre ; le deviendrait sur un gros coffre au premier import, ou après un import en panne plusieurs semaines | L. **Reste à vérifier** : la taille réelle du coffre |

---

# 2. Constats écartés

Aucun constat n'a été écarté en silence. Pour chacun : le fait vérifié faux, et comment ; ou la
décision déjà prise, avec sa source.

### É1. « Le paramètre `last_collected_at` de `read_new_vulnerabilities` est mort en production »

`etl/sources/cisa_kev.py:117-147`, `:211-213`. Le constat est **exact** : le seul appel de `src/`
passe toujours `None`, la branche de filtre n'est atteinte que par onze appels de tests.

**Écarté : décision déjà prise.** `docs/refactoring/plan.md` §9, chantier 14 : « Reporté, le
paramètre `last_collected_at` de `read_new_vulnerabilities` : décision de Sabine, hors étapes. Le
retirer change les tests ; le garder garde une branche que la production n'exécute jamais. » Le
relevé de lisibilité le porte déjà (`lisibilite.md` §5, chantier 14). Rien de nouveau : la décision
est de laisser en l'état, et elle est consignée.

### É2. « La liste de référence de la règle 3 de `poc.md` est périmée »

Les deux lots l'ont signalé : la règle annonce « au départ, six fichiers » et la sortie du `grep`
en compte dix. Vérifié : la règle est **tenue** (aucun des fichiers nouveaux ne touche `raw/`,
relevé fichier par fichier), mais son énumération ne sert plus de garde-fou.

**Écarté : déjà porté.** `docs/refactoring/plan.md` §8, dernier point : « six fichiers sont entrés
dans la sortie du grep de la règle 3 de poc.md depuis le commit 9e6e2e8, sans la justification que
la règle demande […] Aucun ne touche raw/ (relevé du 2026-10-22, fichier par fichier). À justifier
ou à écarter de la liste, hors de cette refactorisation. » Le constat de la règle **4** (un
troisième site `tempfile.`), lui, n'est porté par rien : il est retenu en M22.

### É3. « Un changement de casse du nom d'un dépôt suivi casse tout l'import »

Le lot 1 a cherché un `TypeError` fatal : `transform.is_untracked_release` compare en minuscules
alors que `release_writer.write` cherche `WHERE repository_name = ?`, et `release_writer.py:71-75`
dépaquette `fetchone()` sans garde.

**Écarté : fait vérifié faux**, par le lot lui-même puis relu ici. `database/schema.sql:162` porte
`COLLATE NOCASE`, et `NOCASE` plie l'ASCII, le seul alphabet que `REPOSITORY_NAME` autorise.
Reproduit par le lot avec une liste suivie en `Anthropics/claude-code` contre un brut en
`anthropics/claude-code` : `ImportSummary(item_count=3, …)`, aucune erreur.

**À garder pour le 08/11** : le retrait de `COLLATE NOCASE` au portage PostgreSQL est déjà listé
(`docs/stockage.md:340`, « un index unique sur `lower(colonne)` »). Si ce remplacement se faisait
sans toucher à `transform.py:124`, le `TypeError` deviendrait réel — et le dépaquetage sans garde de
`release_writer.py:71-75` est déjà noté dans `plan.md` §8, « hors étapes ».

### É4. « Une bombe YAML dans un clip épuise la mémoire »

**Écarté : fait vérifié faux**, par le lot 3. Un alias PyYAML rend **le même objet**, pas une
copie : la structure est un graphe, pas un arbre (`b[0] is b[1] is a: True`), et rien ne la parcourt
en profondeur (`extra="ignore"` sur `ClipFrontmatter`). Mesuré sur un vrai coffre avec un clip à
alias : « 1 clip, 0,00 s, pic RSS 35 Mo ». La seule imbrication dangereuse, la profondeur pure, est
déjà traitée : `RecursionError` rattrapé à la collecte et à l'import, avec un test (#103).

### É5. « `RawStore.find_path` est publique et rend un `Path` : écart à la règle 3 de `poc.md` »

**Écarté : fait vérifié faux.** La règle ne contraint que ce qu'une fonction **prend** (« Toute
fonction nouvelle de `raw_store.py` prend une clé POSIX relative au dossier de données […] pas un
`Path` »). Le lot 2 l'a lui-même conclu. La remarque utile reste : c'est la porte de sortie de
l'abstraction par clé, et aucun test ne la ferme — à verser à l'étape 3 bis, pas à cette revue.

### É6. « Les entités XML d'arXiv permettent une amplification »

**Écarté : fait vérifié faux.** Le commentaire `arxiv.py:59-60` tient : entité externe refusée
(`not an XML document: undefined entity &x;`), et l'amplification interne est plafonnée par
expat 2.6.3 (407 octets acceptés pour 1 000 000 de caractères ; 462 octets →
« limit on input amplification factor breached »). La garantie vient d'expat, pas de K-B, mais elle
est effective.

---

# 3. Ce que la revue n'a pas pu vérifier

- **Aucune source réelle n'a été appelée** (consigne). Le format effectif des réponses d'arXiv, de
  l'API GitHub, de `tldr.tech`, de CISA et de GH Archive repose sur les fixtures et sur la
  documentation du dépôt. Trois constats en dépendent explicitement : l'encodage de transfert de
  `cisa.gov` (B1), un `repo.name` réellement hors motif (I3), une page d'édition modifiée après
  publication (M18).
- **Les tests de bout en bout** (`-m e2e`) n'ont pas été lancés : ils interrogent les sources
  réelles et celui de `gh_archive` déclenche une requête BigQuery facturée.
- **La concurrence** : deux `kb collect` simultanés (I5) et deux `kb import` simultanés (M10) n'ont
  pas été lancés en vrais processus ; le résultat dépend du `busy_timeout` par défaut de 5 s. La
  structure vérifier-puis-écrire de I5, elle, est lue dans le code.
- **Un SIGKILL ou une coupure de courant** entre l'écriture du journal d'import et le commit (M12).
- **Le déclencheur de M13** : qu'un `KB_GITHUB_TOKEN` porteur d'un CR ou d'un LF survive au
  chargement de `.env`. La fuite, elle, est établie par le code de la bibliothèque standard.
- **La taille réelle du coffre** et du dossier de données, donc l'ampleur de M25.
- **`test_serve_ai_stops_on_sigterm_with_the_code_of_a_process_stopped_by_it`** échoue dans le bac à
  sable de la session (`PermissionError` sur `socket.bind`) : l'arrêt sur SIGTERM n'est pas prouvé
  ici. Les 2 288 autres tests passent.
- **La robustesse de `bs4` sur une page hostile** de 1 Mio (profondeur de balises, nombre
  d'éléments `article`) : le garde `soup.select_one("article article")` évite la recherche
  quadratique annoncée, mais rien n'a été mesuré.
- **Le délai de `http_download`** est un délai par opération de socket, pas un délai total : un
  serveur qui livre un octet toutes les 29 s n'est pas borné. Non démontré (le bac à sable interdit
  l'écoute sur un port).
- **Le comportement du code une fois la base passée à PostgreSQL** : voir É3.
- Lus moins en profondeur, faute de surface d'entrée externe propre : `tracked_repositories.py`,
  `user_agent.py`, et `github_most_forked.py`, comparé ligne à ligne à son jumeau plutôt
  qu'éprouvé seul.

---

# 4. Ce qui a été éprouvé et qui tient

À ne pas rouvrir : ces invariants ont été attaqués sans céder.

- **La frontière réseau** (`http_download.py`), la plus solide du lot : préfixe de confiance refusé
  s'il n'est pas `https://<hôte>/` sans *user info*, **avant** toute requête ; origine de la réponse
  contrôlée **avant** de lire le corps ; corps borné par `read(max_bytes + 1)` puis comparé ; jeton
  passé par `add_unredirected_header`, qu'urllib ne recopie pas vers une redirection. Dix tests, y
  compris `https://example.org.example.com` et la bascule en HTTP clair. Pas de `verify=False`, pas
  de contexte SSL bricolé, pas de `Accept-Encoding: gzip` (donc pas de bombe de décompression),
  aucune URL porteuse de secret.
- **`write_file_atomically` ne détruit jamais la cible** : les cinq modes d'échec paramétrés
  laissent le contenu précédent intact et aucun temporaire ; l'erreur d'origine est relevée ; le
  calcul des dossiers à `fsync` est correct (impossible de produire un « trou ») ; `SIGTERM` passe
  par `except BaseException` et le descripteur de dossier est fermé sur toute sortie. Les fichiers
  écrits sont en `0600`.
- **Pas de traversée de chemin** : `extract.py:91-108` valide le nom de source, l'extension et
  chaque nom de page **avant la première écriture** ; le nom de page d'un clip est un préfixe de
  SHA-256, pas le titre du fichier ; `is_repository_name` refuse `.`, `..` et les noms à plus de
  deux parties ; `has_dot_segment` refuse un segment `..` même percent-encodé.
- **Pas d'injection SQL ni de code dynamique** : les deux requêtes externes sont des constantes,
  BigQuery reçoit des paramètres typés, Zotero est ouvert en `?mode=ro` après `PRAGMA
  integrity_check`, sur une copie. Aucun `eval`, `exec`, `pickle`, `shell=True` dans l'ETL.
- **Les messages ne citent pas d'auteur** : vérifié sur un document Zotero hostile, sur les tops
  (nom de dépôt cité par sa seule longueur) et sur GH Archive (`FIELDS_QUOTED` exclut
  `repository_name`, cinq tests le prouvent). Aucune donnée personnelle ne passe par le chemin d'un
  brut : `clipping.make_page_name` hache le nom du fichier du coffre.
- **`raw_purge.py` correspond au registre**, point par point : liste venue du registre de la base et
  jamais du dossier ; rien supprimé si le dernier fichier importé manque ; seuls les deux dossiers
  prévus purgés ; journal réduit à un nombre. L'ordre lexicographique des clés est bien l'ordre
  chronologique ; un fichier non importé ou illisible n'est jamais supprimé ; la purge est
  idempotente.
- **Journal et commit** : `check_log_absent` est hors du `try`, donc un journal déjà présent n'est
  pas supprimé ; le verrou d'écriture est tenu quand le contrôle a lieu ; le nettoyage distingue
  correctement « commit échoué » et « commit passé ». `json.dumps` échappe les caractères de
  contrôle, donc le motif non échappé de I7 n'injecte rien dans `import-log.jsonl`.
- **Ordre et déterminisme** : même brut, même base. Les deux tris par `collected_at` sont stables,
  les dossiers sont listés par `sorted()`.
- **Retraits et doublons** : un item que la base **laisse de côté** reste compté comme présent ;
  un item qu'elle **refuse** incrémente `rejection_count` avant le retrait ; un catalogue plus
  ancien que le dernier importé ne retire rien.
- **La composition** (`source_kinds.py`, `collected_sources.py`) : rien à signaler. Le refus d'une
  source choisie sans sa variable ferme le trou « `kb collect` sort en 0 sans rien lancer » ; les
  préfixes de dossier ne se couvrent pas ; `KB_VAULT_DIR` et `KB_ZOTERO_DIR` n'ont pas de défaut.
- **Zotero, copie et nettoyage** : les états du fichier et de son WAL sont comparés avant et après
  la copie ; `remove_left_copies` ne touche qu'un dossier qui est un répertoire **et** appartient à
  l'uid courant.
- **Rejet d'une entrée invalide, règle 1** : chaque lecteur respecte le contrat ; les classements
  refusent leur page entière (exception prévue par la règle) ; les trois `logger.warning` de
  `etl/sources/` ne sont pas des rejets d'entrée.

---

# 5. Commandes de vérification des règles

Lancées par les trois lots et recoupées. `uv` échoue dans le bac à sable : tout passe par
`.venv/bin/…` et `PYTHONDONTWRITEBYTECODE=1`.

| Règle | Sortie | Verdict |
|---|---|---|
| contrôles du dépôt | `ruff check --no-cache` : *All checks passed!* ; `ruff format --check` : 186 fichiers ; `mypy --strict` : *no issues found in 118 source files* ; `pytest` : 2 288 passés, 1 échec (bac à sable) | vert |
| `conventions.md` 1 | `logger.warning` dans les sources : 3 lignes, aucune n'est un rejet d'entrée ; `SAVEPOINT` : `database/savepoint.py` seul ; `Rejection(` : la classe et sa seule construction | tenue |
| `conventions.md` 2 | `NamedTemporaryFile|.tmp|os.replace` : `raw_store.py` seul ; `TemporaryDirectory` : `zotero.py` seul | tenue |
| `conventions.md` 3 | `may be|maybe|probably|perhaps` : rien. Horodatage et format : conformes | tenue sauf I7, I8, M4, M6 |
| `conventions.md` 4 | identifiants : 4 lignes, toutes dans `items.py` ; une seule fonction de date | tenue |
| `conventions.md` 5 | SQL hors `database/` : rien ; `grep -c "execute" etl/load.py` : 0 ; les commandes ne nomment aucun module d'`etl` | tenue |
| `poc.md` 1 | les trois compteurs : 36, 11, 52 — exactement les repères de départ | tenue (voir M23) |
| `poc.md` 2 | hôtes et ports : 5 lignes, tous des défauts nommés de `core/config.py` ; chemins en dur : rien | tenue, meilleure que le repère |
| `poc.md` 3 | 10 fichiers hors `raw_store.py` ; `etl/raw_reading.py` est bien le seul qui touche le brut | tenue (liste périmée : É2) |
| `poc.md` 4 | `Path.home|expanduser|tempfile.` : 3 sites, tous permis | tenue (liste incomplète : M22) |
| `poc.md` 5 | `except ValidationError` + `str(error)` : rien ; repère secondaire : rien | le grep passe, mais voir I6 et I11 |
| `poc.md` 6 | `return <chiffre>` : 0 (17 au départ) ; `sys.exit(<chiffre>)` : rien ; `SIGTERM` présent | tenue, meilleure que le repère |
| `conformite.md` | `robots.txt` de `tldr.tech` lu le 2026-10-01 et consigné ; le `User-Agent` nomme un contact public | tenue |
