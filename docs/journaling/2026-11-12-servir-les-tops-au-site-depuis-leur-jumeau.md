# Servir les tops GitHub au site, depuis le jumeau JSON de leur fiche

- **Date** : 2026-11-12
- **Branche** : `feat/top-twins`
- **Issue** : #559
- **Fichiers principaux** :
  - `src/k_b/exchange/storage.py` (phase A)
  - `src/k_b/items.py`, `src/k_b/post/top_sheets.py`, `src/k_b/jobs/watch_download.py` (phase B)
  - `src/k_b/data_api/watch_reading.py`, `src/k_b/data_api/routers/top_router.py`,
    `src/k_b/data_api/schemas/top_schema.py`, `src/k_b/data_api/errors.py`,
    `src/k_b/commands/serve_data_command.py` (phase C)
  - `src/k_b/etl/tops.py` et les deux sources des tops (revue)
- **Série** :
  - note précédente sur le même chemin : [ranger le client du stockage d'échange dans
    `exchange`](2026-11-11-ranger-le-client-du-stockage-d-echange-dans-exchange.md) (#558), qui a ouvert ce client à
    l'API de données ;
  - le rôle de lecture de `watch` est posé par [la mise en ligne du site
    privé](2026-11-11-mettre-en-ligne-le-site-prive.md) (#571).

Commits de la branche, sur `origin/main` `1b6e0b8` :

| Commit | Contenu |
|---|---|
| `f0d8875` | phase A, le téléchargement borné |
| `2747a34` | phase B, le jumeau |
| `fe0780b` | phase C, les routes |
| `b0cf3ae` | la documentation |
| `65ccd0f` | les corrections du premier passage de revue |
| `ad04fde` | les corrections du second passage |

La liste des fichiers donnée à la note compte aussi des fichiers que cette branche ne touche pas : `src/k_b/web/`,
`infra/`, `observability/`, `tests/database/`, `tests/web/` et trois autres notes. Elle a été calculée depuis une base
plus ancienne que `origin/main`, et ces fichiers viennent de PR déjà fusionnées (#571, #581, #587, #594). Ils ne sont
pas couverts ici.

## Le pourquoi

Le site de K-B est privé : Sabine seule, par la connexion Entra. Il ne lit que l'API de données et ne rend aucun
Markdown (décisions de Sabine du 2026-11-11). Il doit afficher les tops GitHub, les dépôts les plus étoilés et les
plus forkés, au dernier relevé et aux jours passés.

Ces tops ne sont pas en base. `kb write-tops` les écrit en fiches Markdown dans le coffre (`veille/tops/<top>/<jour>.md`),
puis un job les publie dans le conteneur `watch` du stockage d'échange. La fiche est écrite pour Obsidian : son texte
est échappé (`neutralize_text`, `post/vault_files.py`). La relire telle quelle obligerait à défaire cet échappement.

Sabine a donc choisi qu'à côté de chaque fiche, le producteur écrive un **jumeau** en JSON, et que l'API le lise.
C'est la forme du POC. La cible, plus tard, est un index en base des productions (#531).

Cette PR pose trois choses, que #560 (les comptes rendus) et #561 (le rapport de tendances) reprendront :
- l'écriture du jumeau ;
- la lecture de `watch` par l'API de données ;
- deux routes, réservées au site.

## Le comment

### 1. Un seul schéma pour l'écrivain et pour le lecteur

Le jumeau est décrit une fois, dans `items.py`, le vocabulaire commun à toutes les couches (règle 4 de
`.claude/rules/conventions.md`) :

```python
# src/k_b/items.py:689-695
    model_config = ConfigDict(strict=True, extra="forbid")

    top: TopName
    # The moment its ranking was collected, the collected_at of its sheet: named apart from the
    # collected_at of an item, which the data API never serves (docs/specs-api.md).
    ranked_at: Annotated[UtcDatetime, BeforeValidator(read_written_datetime)]
    repositories: Annotated[list[TopRepository], Field(max_length=GITHUB_RANKING_SIZE)]
```

**Le même modèle sert aux deux bouts.** `kb write-tops` construit le jumeau par `TopProduction.model_validate`
(`build_twin`, `post/top_sheets.py`). L'API le relit par `TopProduction.model_validate_json` (`read_twin_production`,
`data_api/watch_reading.py:186`). Si l'écrivain change de forme, le lecteur la refuse.

**Ce que le modèle exige :**
- `extra="forbid"` refuse un champ en plus ;
- `strict=True` refuse une conversion silencieuse, par exemple la chaîne `"3"` pour un entier ;
- `check_ranks_follow_each_other` (`items.py:697-703`) exige les rangs 1 à n, dans l'ordre ;
- chaque dépôt (`TopRepository`) porte une `url` égale à `https://github.com/` suivi de son nom, et un nom de
  255 caractères au plus ;
- la description est un `VisibleText` (`items.py:254`), qui refuse tout caractère caché sauf U+200D, le joint
  des emojis.

**L'écrivain rend la description lisible avant le schéma** (`make_visible`, `post/top_sheets.py:236-243`) :
- chaque caractère caché devient une espace ;
- le texte tient sur une ligne ;
- il est coupé à 1 000 caractères (`description_truncated` le dit).

Le schéma ne refuse donc pas une description de GitHub. Il refuserait seulement un jumeau qu'un autre que
`kb write-tops` aurait écrit.

**Le brut d'un relevé n'est supprimé qu'une fois la fiche et le jumeau présents** (`post/top_sheets.py:165-175`) :

```python
    for collected_at in read_times:
        for path in list_written_paths(sheets_dir, collected_at):
            if not has_sheet(path, vault_dir):
                raise VaultEntryRefusedError(
```

Sans ce contrôle, un relevé pourrait disparaître sans son jumeau, et le jour serait perdu pour le site : le brut est
la seule source du jumeau.

### 2. Ce que le jumeau refuse, la collecte le refuse avant

La première revue a trouvé un cas où la source acceptait ce que le jumeau refuse : un compte négatif, un compte
au-delà de 64 bits, un nom de plus de 255 caractères. Le relevé n'avait alors plus de fiche, et `kb write-tops`
échouait à chaque passage. Les deux sources lisent désormais le nom et le compte par deux aides communes
(`etl/tops.py:43-77`) :

```python
# src/k_b/etl/tops.py:71-74
    if count < 0:
        raise PageRefusedError(f"repository {rank}: {field} below 0")
    if count > MAX_INT64:
        raise PageRefusedError(f"repository {rank}: {field} above {MAX_INT64}")
```

**Ce que refuse `PageRefusedError` :**
- c'est toute la page qui est refusée, pas le seul dépôt : retirer un dépôt décalerait les rangs du top (exception
  de la règle 1 de `conventions.md` pour un classement) ;
- le message nomme la borne franchie, jamais la valeur (règle 3) ;
- un nom refusé n'est cité que par sa longueur, car il porte le login de son propriétaire.

**Le refus par le jumeau reste un filet** (`read_ranking`, `post/top_sheets.py`) : un relevé refusé est gardé et
jamais supprimé.

### 3. Télécharger un blob listé sans lui faire confiance

`watch` est écrit par d'autres identités, celles des jobs : ses noms et ses contenus sont des entrées non fiables.
Le téléchargement est borné de trois façons (`exchange/storage.py:246-252`) :

```python
            downloader = container_client.download_blob(
                blob.name,
                offset=0 if blob.size else None,
                length=max_bytes + 1 if blob.size else None,
                etag=blob.etag,
                match_condition=MatchConditions.IfNotModified,
                decompress=False,
```

**Les trois bornes :**
- **Une plage** de `max_bytes + 1` octets au plus. Sans elle, le SDK lit d'un coup jusqu'à 32 Mio
  (`max_single_get_size`). L'octet de plus permet de voir un blob plus long que la borne. Un blob listé vide se
  demande sans plage, car Azure répond 416 à une plage sur un blob vide.
- **L'etag listé**, en condition (`IfNotModified`). Si un job a remplacé le blob entre la liste et le
  téléchargement, la réponse est 412, et la fonction rend `None`. La version lue est toujours celle qui a été listée.
- **`decompress=False`**. Un blob envoyé compressé (`Content-Encoding: gzip`) dépasserait toute borne une fois
  décompressé.

**Les erreurs gardent leur nom :**
- `ExchangeStorageError` garde le statut et le code du stockage (`BlobNotFound`, `ContainerNotFound`) ;
- un délai dépassé devient `exchange_storage_timeout`, même quand le SDK l'emballe dans une autre erreur ;
- jamais le message du SDK, qui peut nommer un blob.

**Le jeton de l'identité** est demandé par le SDK au milieu d'une requête, pas avant comme dans un job. La revue a
montré qu'un point d'identité qui répond autre chose que du JSON donnait un 500. Ce cas suit maintenant la règle de
`check_identity` des jobs, par une enveloppe du credential (`exchange/storage.py:201-223`) :

```python
    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        """The token of the credential, or exchange_storage_no_token."""
        with naming_token_failures():
            return self.credential.get_token(*scopes, **kwargs)
```

### 4. Lire `watch` : la liste, le cache, les refus

`WatchReader` (`data_api/watch_reading.py`) lit le dossier d'un top par son préfixe, `tops/<top>/`. Il ne garde
que les noms de la forme exacte `tops/<top>/AAAA-MM-JJ.json` (`fullmatch`), et laisse de côté un jour postérieur à
aujourd'hui (UTC).

**La liste suit le marqueur d'une page coupée court** (`watch_reading.py:230-240`) :

```python
        for _ in range(MAX_WATCH_FOLDER_PAGES):
            blobs.extend(next(pages))
            if len(blobs) > MAX_WATCH_FOLDER_NAMES:
                raise WatchReadingError(
```

- List Blobs peut rendre moins de noms que demandé, avec un `NextMarker` (Microsoft Learn, « List Blobs »,
  « Remarks ») : refuser tout marqueur aurait refusé une liste légitime.
- La borne reste fermée : 5 000 noms et 2 pages au plus, au-delà `watch_listing_too_long`.

**Le cache vit en mémoire, sous un `threading.Lock` jamais tenu pendant une requête au stockage**
(`watch_reading.py:132-165`). Le verrou n'entoure que la lecture et l'écriture des dictionnaires. Une route lente
ne bloque donc pas les autres.
- La liste d'un dossier est gardée 60 s.
- Une production est gardée par son nom et son etag (`key = (twin.blob.name, twin.blob.etag)`,
  `watch_reading.py:150`) : un jumeau réécrit change d'etag, et il est relu.
- Les refus sont gardés comme les réussites : un jumeau refusé n'est pas retéléchargé à chaque requête.
- Au plus 8 productions sont gardées, la plus ancienne oubliée d'abord.

**Un jumeau est refusé, et jamais servi** (`read_twin_production`, `watch_reading.py:186-198`), s'il est :
- hors schéma ;
- d'un autre top que son dossier ;
- classé (`ranked_at`) un autre jour que celui de son nom.

Le journal dit le top, le jour et le motif (`locate_first_error` : le champ et le type d'erreur), jamais le texte.

### 5. Deux routes pour le seul client `WEB`

Le routeur des tops ajoute un contrôle du client à ceux de l'application, la clé et le débit
(`data_api/routers/top_router.py:28`) :

```python
    prefix="/tops", tags=["tops"], dependencies=[Depends(check_client_allowed)]
```

`check_client_allowed` (`core/api_access.py:44-49`, déjà écrit pour l'API IA) compare le client de la clé reçue à
celui que la table `DATA_API_CLIENT_BY_ROUTE` donne pour la route. Une route absente de la table est refusée à
tous. `/items` reste ouvert à tous les clients, car le contrôle n'est posé que sur ce routeur.

**Les deux routes :**
- `GET /tops/{top}?day=&limit=` : les `limit` premiers dépôts (10 par défaut, 100 au plus) du jour donné, ou du plus
  récent sans `day` ;
- `GET /tops/{top}/days?limit=&offset=` : les jours, du plus récent au plus ancien, et leur `total`.

La réponse est construite par les schémas de l'API (`schemas/top_schema.py`), jamais en renvoyant le jumeau tel
quel : un champ ajouté au jumeau n'est pas servi sans décision (OWASP API3).

**Chaque échec a son code** (`data_api/errors.py`) :

| Code | Cas |
|---|---|
| 502 | `watch_production_refused`, `watch_listing_too_long`, une erreur du stockage ou de l'identité |
| 503 | `exchange_storage_not_found` (conteneur absent), `watch_production_changed`, `watch_unconfigured` |
| 504 | `exchange_storage_timeout` |
| 404 | `top_not_found` |
| 403 | `client_not_allowed` |

Sans `KB_EXCHANGE_BLOB_URL` ou sans `AZURE_CLIENT_ID`, `kb serve-data` démarre quand même :
- les tops répondent 503 `watch_unconfigured`, et les items restent servis ;
- une ligne INFO nomme les variables absentes ;
- l'URL seule est le réglage normal du Mac (`kb download-watch-sheets` passe par `az login`) ;
- `AZURE_CLIENT_ID` seul est l'identité de la base.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Option écartée, et pourquoi |
|---|---|---|
| Un jumeau JSON à côté de chaque fiche (Sabine, 2026-11-11) | Le site ne rend aucun Markdown, et la fiche est échappée pour Obsidian. Conséquence : le jumeau se revalide par un schéma fermé (règle 8 de `poc.md`). | Relire la fiche Markdown, illisible brute. Un index en base (#531) : la cible, plus tard. |
| Le schéma dans `items.py`, commun à l'écrivain et au lecteur | Règle 4 de `conventions.md` : un type qui sert à plus d'un module vit une fois | Un schéma par côté, qui divergerait ; le schéma dans `core/`, qui n'importe que `core` alors que le schéma a besoin des types d'`items.py` |
| `ranked_at` au lieu de `collected_at` (time-knight) | L'API ne sert jamais une date de collecte, preuve d'API3 tenue par `test_no_route_documents_a_raw_file_path_or_a_collection_date` | Exempter les tops de ce test : une preuve OWASP affaiblie, et un même nom avec deux sens |
| Le marqueur d'une page suivi, sur 2 pages au plus (time-knight) | Une page peut être coupée court avec un marqueur (Microsoft Learn) | Un 502 à tout marqueur, prévu au plan : il aurait refusé une liste légitime |
| `/days` d'un dossier vide : 200, `{"days": [], "total": 0}` | Une liste vide n'est pas une ressource absente | 404 |
| La collecte refuse ce que le jumeau refuse, page entière (time-knight) | Sinon le relevé n'a plus de fiche, et `kb write-tops` échoue à chaque passage | Refuser le seul dépôt : les rangs se décaleraient |
| Tout échec du jeton pendant une requête : 502 `exchange_storage_no_token` (time-knight) | La règle de `check_identity`, jamais un 500 | Garder 504 pour un délai de l'identité : écarté, une seule règle pour le jeton |
| Réglage incomplet de `watch` : INFO, sans arrêt (time-knight, après le second passage) | `/items` marche sans `watch`, et l'URL seule est le réglage du Mac | ERROR au démarrage, ajoutée au premier tri : fausse sur le Mac (`.env.example`), retirée. Refuser le démarrage : couperait `/items`. |
| `WEB_CLIENT` dans `core/config.py`, tenu égal à `web/settings.py` par un test | L'API de données n'importe pas `web` | Importer `web` : une couche qui remonte |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_twin_kb_write_tops_writes_is_served_by_the_route` (`tests/data_api/test_top_router.py`) | Le jumeau écrit par `kb write-tops` est relu et servi par la route : l'écrivain et le lecteur parlent le même schéma |
| `tests/test_top_production.py` (`test_a_twin_out_of_the_schema_is_refused` et les autres) | Chaque règle du schéma refuse son cas |
| `test_another_client_is_refused_and_the_items_stay_open_to_it` | 403 pour un autre client, `watch` jamais lu ; `/items` reste ouvert |
| `test_a_twin_out_of_its_schema_is_refused_and_its_text_never_logged` | Un jumeau hors schéma répond 502 et son texte ne va pas au journal |
| `test_a_twin_larger_than_a_sheet_is_refused_without_its_download` | La taille listée est refusée avant tout téléchargement |
| `test_at_most_one_byte_past_the_bound_is_asked`, `test_a_blob_listed_empty_is_downloaded_whole`, `test_a_blob_compressed_is_given_as_stored` (`tests/exchange/test_storage.py`) | La plage, le blob vide et `decompress=False` |
| `test_a_twin_changed_since_the_listing_is_503_and_the_listing_read_again` | Un jumeau changé depuis la liste répond 503, et la liste est relue |
| `test_a_download_past_its_wait_is_504_without_the_name_of_the_blob` | 504, sans le nom du blob dans la réponse ni dans le journal |
| `test_a_page_cut_short_with_a_marker_is_followed_to_the_end`, `test_a_listing_of_more_pages_than_its_bound_is_refused` | Le marqueur est suivi, et la borne de pages tient |
| `test_a_twin_read_is_kept_by_its_name_and_its_etag`, `test_a_listing_is_kept_until_its_seconds_have_passed` | Le cache garde par etag et relit la liste après 60 s |
| `test_a_top_of_100_with_the_longest_descriptions_stays_under_the_bound_of_the_site` | Le pire cas d'un top tient sous le 1 Mo que le site lit |
| `test_a_token_refused_during_a_request_answers_502_no_token` (4 cas) | Rouge montré avant le code : 500 `internal_error` (HTML, liste JSON) et 502 `exchange_storage_failed` (JSON, refus 400) ; désormais 502 `exchange_storage_no_token`, sans ligne forgée au journal |
| `test_an_invalid_repository_is_refused_with_its_rank`, `test_a_count_out_of_its_bounds_names_the_bound_it_crossed` (les deux sources) | Rouges montrés : 6 `DID NOT RAISE`, puis 4 messages « out of 0 to … » ; la collecte refuse ce que le jumeau refuse, par la borne franchie |
| `test_a_ranking_whose_twin_its_schema_refuses_is_kept_without_its_values` (`tests/post/test_top_sheets.py`) | Le filet du jumeau tient : relevé gardé, ni fiche ni jumeau, aucune valeur au journal |
| `test_serve_without_a_setting_of_the_storage_starts_and_says_the_tops_unconfigured` (3 cas) | Rouge montré : la ligne nommait une seule variable, ou écrivait l'ERROR ; désormais INFO, avec les variables absentes |
| `uv run pytest` → 4929 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt passent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un fichier JSON à côté de la fiche, et pas une table en base ?**
   - C'est la forme du POC, choisie par Sabine le 11/11 ; la base est la cible (#531).
   - Le jumeau se produit au même endroit que la fiche (`kb write-tops`). Un fait du dépôt l'appuie, sans être la
     raison donnée : une table nouvelle en ligne demanderait une migration, que K-B n'a pas encore (#186).
   - L'API le relit par le même schéma que l'écrivain (`items.py:685`).
2. **Un job compromis écrit un faux jumeau dans `watch`. Que voit le site ?**
   - Rien de ce qui sort du schéma : il est refusé (502), jamais servi (`watch_reading.py:186-198`).
   - Un jumeau conforme mais faux serait servi. Le schéma prouve la forme, pas la vérité : la défense est le droit
     d'écriture sur `watch`, réservé aux jobs.
   - Un caractère caché, une URL autre que `https://github.com/<nom>` ou un champ en plus sont refusés.
3. **Pourquoi l'etag au téléchargement ?**
   - Sans lui, un job qui remplace le blob entre la liste et la lecture ferait servir une version que la liste
     n'a pas vue, avec une taille différente de celle contrôlée.
   - Avec lui, Azure répond 412, l'API répond 503 et oublie la liste (`exchange/storage.py:250-251`).
4. **Un autre client de l'API de données (le terminal, l'API IA) appelle `/tops`. Que se passe-t-il ?**
   - 403 `client_not_allowed`, avant toute lecture de `watch` (`top_router.py:28`, `api_access.py:44-49`).
   - Une route oubliée dans la table est refusée à tous : le contrôle échoue fermé.
5. **Pourquoi le verrou n'est-il jamais tenu pendant une requête au stockage ?**
   - Une requête lente (jusqu'à 10 s de lecture) bloquerait toutes les autres routes des tops.
   - Le prix : deux requêtes froides simultanées vont chacune au stockage. C'est la limite (b), avec sa parade
     écrite (`docs/specs-api.md`, « Lecture de `watch` »).

## Zones non vérifiées

- **Aucun essai réel** : les routes n'ont tourné ni contre un vrai compte de stockage ni en ligne. Les tests
  simulent le SDK par `FakeTransport` et le point d'identité par `IDENTITY_ENDPOINT`.
- **Le rôle d'`id-kb-data-api` sur `watch`** (#571, #578) n'est pas vérifié par cette PR. Il le sera par le
  premier appel en ligne.
- **Le comportement du SDK**, lu dans sa source et sur Microsoft Learn, non éprouvé contre Azure :
  - le 416 sur une plage d'un blob vide ;
  - le délai réemballé par le téléchargeur ;
  - la page coupée court avec un marqueur.
- **`uv run pytest -m postgresql`** n'a pas été lancé sur le Mac. Le code ne touche pas `database/`, et la preuve du
  second moteur est le job CI `tests-postgresql` de la PR.
- **Un délai du point d'identité** répond 502 `exchange_storage_no_token`, pas 504 : limite acceptée. Le journal ne
  distingue alors pas un délai d'un refus.

## Ce qui reste

- **Les jumeaux des fiches écrites avant cette PR** : l'historique du site commence au premier jumeau (limite d).
  Sa parade, écrire une fois ces jumeaux depuis le Markdown, n'est pas planifiée.
- **Une fiche écrite avant cette PR** peut recevoir le jumeau d'un relevé plus tardif du même jour (limite e), une
  fois, pour le dernier jour de chaque top.
- **Limites a à c**, avec leur parade écrite dans `docs/specs-api.md`, non codées :
  - une échéance d'ensemble pour une requête froide ;
  - une seule lecture à la fois par dossier ;
  - `AzureCliCredential` sur le Mac.
- **Les comptes rendus (#560) et le rapport de tendances (#561)** reprendront cette lecture de `watch`.
- **Une seule règle des caractères cachés pour tous les lecteurs** : #598.
- **La mise en ligne** : un tag posé par tn-codeur, sur demande de Sabine.
