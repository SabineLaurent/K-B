# Servir au site les comptes rendus de veille, depuis le jumeau JSON de leur fiche

- **Date** : 2026-11-14
- **Branche** : `feat/digest-twins`
- **Issue** : #560
- **Commits de la branche** : `295fc90` (le jumeau), `ea6e740` (le lecteur et les routes), `08d24cb` (les tests de
  borne du cache), `12523e1` et `305559e` (les documents), `5b41091` (le tri de la revue). Les autres commits de
  la liste injectée sont ceux de `main`, déjà fusionnés avant la branche (#559, #564, #596, #600 à #613) : ils ont
  leur propre note.
- **Fichiers principaux** : `src/k_b/items.py` (`DigestProduction`), `src/k_b/post/digest_sheets.py`,
  `src/k_b/commands/digest_command.py`, `src/k_b/data_api/watch_reading.py`,
  `src/k_b/data_api/routers/watch_digest_router.py`, `src/k_b/data_api/schemas/watch_digest_schema.py`,
  `src/k_b/core/config.py`.
- **Série** : suit [la note des tops](2026-11-12-servir-les-tops-au-site-depuis-leur-jumeau.md) (#559), dont elle
  reprend la forme et généralise le lecteur.

## Le pourquoi

Le site privé de Sabine doit montrer le compte rendu de veille de chaque sujet, au dernier jour et aux jours passés.
Ce compte rendu existe déjà : `kb digest` l'écrit en Markdown dans le coffre (`veille/<sujet>/<jour>.md`), et les
jobs publient le coffre dans le conteneur `watch`. Mais le site ne lit que l'API de données et ne rend aucun
Markdown (décision de Sabine du 2026-11-11), et la fiche est échappée pour Obsidian, donc illisible brute. On
reprend la solution de #559 : le producteur écrit à côté de la fiche un **jumeau JSON**, fait de la même réponse,
et l'API de données le relit par un schéma fermé avant de le servir.

Une donnée manque à la fiche : l'`item_id` de chaque source. Le jumeau la garde, pour que le site mène d'une source
à l'item du fil.

## Le comment

### 1. Un schéma pour l'écrivain et le lecteur

`DigestProduction` (`items.py:798`) est strict et fermé (`extra="forbid"`) : `kb digest` le construit, l'API le
revalide. Ses validateurs disent ce qu'un compte rendu cohérent doit être, par exemple chaque source citée une
fois :

```python
# src/k_b/items.py:850-855
        for claim in self.claims:
            if len(set(claim.item_ids)) != len(claim.item_ids):
                raise ValueError("a source cited twice by a claim")
            cited_ids.update(claim.item_ids)
        if cited_ids != set(source_ids):
            raise ValueError("sources not those the claims cite")
```

Pourquoi un seul schéma : la règle 4 de `conventions.md` (une règle écrite une fois). Si l'écrivain et le lecteur
avaient chacun la leur, un jumeau accepté à l'écriture pourrait être refusé à la lecture.

### 2. Le jumeau avant la fiche, puis la fiche, puis le jumeau

```python
# src/k_b/commands/digest_command.py:205-222
    try:
        twin = build_twin()
    except ValidationError as error:
        ...
        return SummaryRow(subject, "twin refused", "")
    try:
        sheet = write_sheet()
    ...
    try:
        write_digest_twin(vault_dir, twin)
```

Le jumeau est **construit et validé** d'abord. S'il est refusé, rien n'est écrit : le sujet échoue et garde son
début (#565), et son compte rendu suivant relit la même fenêtre. Sinon la fiche est écrite, puis le jumeau. La fiche
passe avant parce qu'elle seule fait avancer le début du sujet (`find_previous_until` lit les fiches). Un jumeau
écrit avant une fiche en échec montrerait au site un compte rendu absent du coffre. Le revers est la limite (c) :
un jumeau non écrit après sa fiche perd ce jour sur le site.

### 3. Un lecteur pour deux sortes de jumeaux

#559 avait écrit un lecteur des seuls tops. Au lieu d'en copier un second (et un troisième pour #561), le lecteur
reçoit une **sorte** de jumeau, une `TwinKind` (`watch_reading.py:71`), qui dit tout ce qui change d'une sorte à
l'autre :

```python
# src/k_b/data_api/watch_reading.py:101-110
DIGEST_TWINS = TwinKind(
    parent="",
    schema=DigestProduction,
    read_folder=lambda production: production.subject,
    read_moment=lambda production: production.until,
    folder_refusal="subject_not_its_folder",
    day_refusal="until_not_its_day",
    max_bytes=MAX_DIGEST_TWIN_BYTES,
    kept_count=WATCH_CACHED_DIGESTS,
)
```

`TwinKind` est générique (`TwinKind[Production: BaseModel]`) : mypy sait que `production.subject` existe parce que
`schema=DigestProduction` fixe le type. La relecture applique ensuite les trois refus, communs à toutes les sortes :

```python
# src/k_b/data_api/watch_reading.py:250-257
    try:
        production = kind.schema.model_validate_json(content)
    except ValidationError as error:
        return TwinRefusal(locate_first_error(error))
    if kind.read_folder(production) != folder:
        return TwinRefusal(kind.folder_refusal)
    if kind.read_moment(production).astimezone(UTC).date() != day:
        return TwinRefusal(kind.day_refusal)
```

Un jumeau posé dans le mauvais dossier, ou au nom d'un autre jour, n'est jamais servi. Le journal dit le motif
(`locate_first_error` : la place et le type d'erreur), jamais le texte.

### 4. Un cache par sorte

```python
# src/k_b/data_api/watch_reading.py:205-215
        with self.lock:
            kept = self.productions.setdefault(kind, OrderedDict())
            production: Production | TwinRefusal | None = kept.get(key)
            ...
                while len(kept) > kind.kept_count:
                    kept.popitem(last=False)
```

Chaque sorte garde ses dernières productions lues, par nom et etag : 8 tops, 16 comptes rendus (le dernier jour
des 9 sujets et une marge). Si le cache était commun, lire les 9 sujets ferait oublier les tops. Le `setdefault`
vient de la revue (constat 3) : la première version préparait le cache pour une liste de sortes écrite en dur, et
une troisième sorte aurait levé `KeyError`. Le verrou n'est jamais tenu pendant une requête au stockage.

### 5. Les routes

```python
# src/k_b/data_api/routers/watch_digest_router.py:41-44
    found = watch.read_production(DIGEST_TWINS, subject, day)
    if found is None:
        raise ApiError(404, "digest_not_found")
    return WatchDigestSchema(day=found.day, **found.production.model_dump())
```

La réponse est faite du schéma propre à l'API (`WatchDigestSchema`), jamais du jumeau tel quel : un champ ajouté au
jumeau ne serait pas servi (OWASP API3). `subject` est un `Literal` (`DigestSubjectName`) : un sujet hors de la liste
répond 422, et le préfixe du dossier ne peut viser ni `tops/` ni `tendances/`. Le routeur porte
`check_client_allowed` : seul le client `WEB` passe (403 pour un autre).

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le jumeau JSON, forme de #559 | Décision de Sabine du 2026-11-11 : le site ne rend aucun Markdown | Relire la fiche Markdown : échappée pour Obsidian, illisible brute ; la cible reste un index en base (#531) |
| Le jumeau validé avant la fiche | Rien n'est écrit que l'API refuserait ; le sujet garde son début | Écrire la fiche quoi qu'il arrive : un jour sans jumeau, perdu sur le site |
| La fiche avant le jumeau | Elle seule fait avancer le début du sujet | Le jumeau d'abord : un compte rendu au site, absent du coffre (validé par time-knight) |
| Un lecteur, une `TwinKind` par sorte | Plan validé (point 4) | Un second lecteur copié, que #561 aurait triplé |
| Des fonctions typées dans `TwinKind` | mypy vérifie `production.subject` | `getattr` sur un nom de champ : non typé, une faute de frappe devient un 500 |
| `MAX_DIGEST_TWIN_BYTES` = 400 000 | Le pire cas mesuré : 389 968 octets ; servi, sous le 1 Mo du site | Les 4 Mo d'une fiche : le cache de 16 pèserait 64 Mo |
| `DigestSubjectName`, un `Literal` écrit en clair, tenu égal à `DIGEST_SUBJECTS` par un test | Il donne l'`enum` dans l'OpenAPI et mypy le vérifie | Un type construit à l'exécution : ne se vérifie pas statiquement |
| `WATCH_CACHED_PRODUCTIONS` renommée `WATCH_CACHED_TOPS` | Le nom serait devenu faux | Garder le nom |
| Schémas nommés `WatchDigest…` | L'API IA a déjà `DigestSchema`, `ClaimSchema`, `SourceSchema` | Les mêmes noms dans deux API : confusion à la lecture |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Rouge avant le code : 41 failed (404 au lieu de 200, 422 ou 403 ; OpenAPI ; limite de débit) | Les tests visaient bien les routes absentes |
| `test_the_twin_kb_digest_writes_is_served_by_the_route` (`tests/data_api/test_watch_digest_router.py:168`) | Le jumeau écrit par `kb digest` est servi tel quel, plus `day` |
| `test_a_twin_out_of_its_schema_is_refused_and_its_text_never_logged` (`:414`), 8 cas | Hors schéma, autre dossier, autre jour : 502, motif au journal, texte jamais cité |
| `test_another_client_is_refused_and_the_items_stay_open_to_it` (`:343`) | Seul `WEB` lit les comptes rendus ; aucune requête au stockage pour un autre |
| `test_the_largest_twin_kb_can_write_is_read_and_served_under_the_bound_of_the_site` (`:325`) | Le pire cas tient sous `MAX_DIGEST_TWIN_BYTES` et sous le 1 Mo du site |
| `test_the_digests_read_never_push_a_top_out_of_the_reader` (`:536`) | Un cache par sorte |
| `test_a_kind_the_reader_was_not_built_with_is_read_and_kept` (`:555`), rouge `KeyError` d'abord | Une sorte nouvelle n'a besoin d'aucune liste dans le lecteur |
| Mutations de `watch_reading.py` : 7 tuées sur 8 | Les gardes sont tenues par les tests ; le survivant (`astimezone`) est équivalent, `WrittenDatetime` étant déjà en UTC (`items.py:356`) |
| `test_the_subjects_of_the_route_are_those_of_the_digests` (`:319`) | `DigestSubjectName` ne dérive pas de `DIGEST_SUBJECTS` |
| `uv run pytest` : 5582 passed ; ruff, format, mypy verts | Rien d'autre n'est cassé |
| Rejeu de `tests/fixtures/digests_reference.json` : 2 passed | Aucun appel au modèle de plus |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas relire la fiche Markdown ?** Elle est échappée pour Obsidian (`neutralize_text`), et le site
   ne rend aucun Markdown : `markdown-it-py` et `nh3` ont été retirées par #559, ni dépendance ni risque XSS d'un
   rendu (journal ADR, 2026-11-12). Le jumeau est fait de la même réponse et relu par un schéma fermé
   (`items.py:798`).
2. **Un job compromis écrit un faux jumeau dans `watch` : que se passe-t-il ?** Il est revalidé :
   champs en plus refusés, URL limitées à `http(s)` sans caractère caché, textes sans caractère caché, sujet et
   jour contrôlés contre son nom (`watch_reading.py:250-257`). Refusé, il n'est jamais servi, et son texte jamais
   journalisé. Ce qui passe le schéma reste un texte affiché comme du texte par le site (autoescape de Jinja2).
3. **Pourquoi un `Literal` écrit à la main plutôt que `DIGEST_SUBJECTS` ?** L'OpenAPI liste les sujets et mypy le
   vérifie ; un test empêche les deux listes de diverger (`test_watch_digest_router.py:319`). Revers : un sujet
   retiré rend ses anciens comptes rendus inaccessibles (limite (e)).
4. **L'`item_id` mène-t-il toujours au bon item ?** Non : c'est une clé de substitution. Une base refaite
   renumérote, et le lien mène sans erreur à un autre item (limite (d)). Parade côté site : ne mener à l'item que si
   son titre est celui de la source.
5. **Que se passe-t-il si le disque refuse le jumeau après la fiche ?** Ce jour est perdu pour le site ; le sujet
   est compté en échec et `kb digest` sort en erreur (limite (c), `digest_command.py:218-222`).

## Zones non vérifiées

- Aucune exécution réelle : ni contre un vrai compte de stockage ni en ligne. Les tests simulent le SDK
  (`FakeTransport`, `FakeContainer`).
- `uv run pytest -m postgresql` n'est pas lancé sur le Mac : la preuve du second moteur est le job CI
  `tests-postgresql` de la PR. Le code ne touche pas `database/`.
- La sérialisation de la réponse par FastAPI n'est mesurée que par le test du pire cas (`len(response.content)`),
  pas lue dans le code de FastAPI.
- Une affirmation faite seulement de blancs ou de caractères cachés passe l'API IA, puis le jumeau la refuse :
  le sujet attend le lancement suivant (limite (g), constat 1 de la revue, parade #624).

## Ce qui reste

- #531 : l'index en base, la cible.
- #561 : le rapport de tendances, troisième `TwinKind`.
- #624 : l'API IA retire une affirmation sans caractère visible.
- La page des comptes rendus du site (session FO), qui lira ces routes : autoescape sans `|safe`, URL possiblement
  en `http`.
- Les limites (a) à (g) de `docs/specs-api.md`, avec leur parade, non codées.
- La mise en ligne : un tag (tn-codeur, sur demande de Sabine), une exécution de `caj-kb-digest-watch`, l'abonnement
  Azure rétabli.
