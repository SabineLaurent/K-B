# Lire la veille par l'API de données depuis l'API IA

- **Date** : 2026-10-15
- **Branche** : `feat/data-api-reader`
- **Issue** : #204
- **Fichiers principaux** : `src/k_b/ai_api/data_api_client.py`, `src/k_b/ai_api/watch_items.py`,
  `src/k_b/ai_api/data_api_settings.py`, `src/k_b/ai_api/outbound.py`
- **Série** : suit [Appeler le modèle et son remplacement](2026-10-15-appeler-le-modele-et-son-remplacement.md)
  (#150) et [Spécifier les fiches de veille](2026-10-15-specifier-les-fiches-de-veille.md).

## Le pourquoi

Une fiche de veille regroupe, pour un sujet, ce que K-B a vu sur quelques jours. Avant de
demander quoi que ce soit au modèle, l'API IA doit **lire cette veille**. Ce code est cette
lecture : l'étape 2 du parcours d'une demande (`docs/fiches-veille.md`, « Le parcours d'une
demande »). Il rend une liste d'items prêts à être classés et rédigés par #205.

Trois exigences le structurent :

1. **L'API IA ne lit pas la base.** Elle passe par l'API de données, avec sa propre clé (client
   `AI_DIGEST`). La base n'a qu'une porte d'entrée en lecture, déjà fermée par une clé, déjà
   journalisée, déjà en lecture seule. L'API IA reste sans état et n'importe ni `database` ni
   `etl` (règle 7 de `poc.md`, prouvée par `tests/test_module_dependencies.py`). Au 08/11, les
   deux tourneront dans des conteneurs séparés : le seul lien entre eux sera HTTP, avec une clé
   qu'on peut révoquer seule.
2. **La lecture est bornée** : 300 items au plus par demande (OWASP API4:2023, consommation de
   ressources sans limite). Chaque item lu donne une requête et, plus tard, des jetons payés.
3. **Le modèle ne reçoit que ce qui est permis** : une liste blanche de champs par sorte, sans
   auteur ni URL d'item. Les URL et les logins GitHub y sont masqués, et chaque champ est coupé.

## Le comment

### 1. Une sorte après l'autre, page après page

La spec demande les sortes rares d'abord : une coupe à 300 doit évincer des articles TLDR,
jamais une entrée du catalogue KEV. `GET /items` trie par date, toutes sortes mêlées. On ne peut
donc pas obtenir cet ordre en une seule liste : on fait **une liste par sorte**, dans l'ordre de
`WATCH_KINDS`.

```python
for kind in WATCH_KINDS:
    for listed_item in list_kind(http_client, since, kind):
        if listed_item.id in seen_ids:
            continue
```
`src/k_b/ai_api/data_api_client.py:218-221`

`list_kind` est un **générateur** : il demande une page, rend ses items un par un, et ne demande
la page suivante (`offset = next_offset`) que si la boucle en a encore besoin. Quand le plafond
est atteint, la boucle s'arrête : aucune page de plus n'est demandée, et les sortes suivantes ne
sont pas lues du tout. Deux gardes protègent la pagination :

- `if page.next_offset <= offset` (`data_api_client.py:252`) : une page qui ne fait pas avancer
  l'offset serait redemandée sans fin. On la refuse (`data_api_invalid_response`).
- `seen_ids` : un import qui écrit entre deux pages décale la pagination par offset
  (`docs/specs-api.md`, « Tri et pagination »). Le même item peut alors revenir. On le lit une
  seule fois, sinon #205 le verrait en double.

### 2. Le plafond, et ce que la réponse en dit

```python
if len(kept) == MAX_ITEMS_PER_DIGEST_REQUEST:
    return ItemList(kept, withdrawn, kind, listed_item.source_date)
kept.append(listed_item)
```
`src/k_b/ai_api/data_api_client.py:226-228`

Quand on voit un 301ᵉ item non retiré, on s'arrête. On rend la sorte où l'on est
(`capped_kind`) et la date de **cet item laissé de côté** (`covered_after`).

Pourquoi la date du premier item *non lu*, et pas celle du dernier lu ? Les articles TLDR d'une
même édition ont tous la même date, minuit UTC. Si la coupe tombe au milieu d'une édition, « le
plus ancien item gardé » daterait un jour lu seulement en partie. Avec `covered_after` en borne
**exclue**, la phrase reste vraie : *tout item de cette sorte strictement plus récent a été lu*.
C'est vrai parce que `GET /items` trie par `source_date` puis par `id`, tous deux décroissants :
cet ordre est total, et rien de plus récent ne peut venir après. Les sortes qui suivent
`capped_kind` ne sont pas lues : la réponse le dit en nommant la sorte (décision de Sabine).

Une entrée retirée (`withdrawn_at` non nul) est comptée et sautée **avant** le test du plafond :
elle ne prend pas de place.

### 3. Les états nommés

Toute réponse de l'API de données passe par deux fonctions. `send` traduit une requête qui
échoue ; `read_body` traduit une réponse qui n'est pas un 200 dans son schéma.

```python
except httpx2.TimeoutException:
    raise DataApiError("data_api_timeout") from None
except httpx2.TransportError:
    raise DataApiError("data_api_unavailable") from None
```
`src/k_b/ai_api/data_api_client.py:280-283`

L'ordre des `except` compte : dans httpx2, `TimeoutException` hérite de `TransportError`
(vérifié sur le paquet installé, 2.13.1). Mis dans l'autre ordre, un délai deviendrait
« indisponible ». `from None` coupe la chaîne : l'exception d'httpx2 cite l'URL demandée, et
`DataApiError` ne doit porter que l'état et le statut.

Côté statut (`read_body`, `data_api_client.py:310`), un 401 donne `data_api_unauthorized` et un
5xx `data_api_unavailable`. Tout autre statut donne `data_api_invalid_response` : une
redirection, qu'on ne suit pas ; le 400 d'un hôte refusé, le réglage le plus probable à manquer
en conteneur ; un 422.

Une seule exception : un 404 dont le corps est exactement `{"error": "item_not_found"}`, au
détail (`data_api_client.py:262`). L'item a disparu entre la liste et le détail. On le saute et on
le compte, ce n'est pas une panne. Un 404 avec un autre corps (une route inconnue, une mauvaise
URL de base) reste un échec : c'est le test qui sépare « l'item est parti » de « je parle au
mauvais service ».

**`since` arrondi à la seconde suivante** (`format_since`, `data_api_client.py:195`). L'API de
données lit `since` ainsi (`database/reading.py`, `format_since`), et l'API IA ne peut pas
importer `database` : la règle est recopiée et cite sa source. Un instant 09:00:00,7 devient
09:00:01, et un item daté 09:00:00, antérieur, n'est pas lu. Le garde porte sur `utcoffset()`, pas
sur `tzinfo` : un fuseau sans décalage laisserait la date naïve, lue comme heure locale. Et
`isoformat` remplace `strftime`, qui laisse la largeur de l'année à la bibliothèque C (constat de
`/code-review`, corrigé).

**Une borne de taille des corps** (`read_bounded_body`, appelée par `send`). Chaque réponse est
lue en flux (`http_client.stream`, puis `iter_bytes`) et refusée en `data_api_invalid_response`
dès que les octets lus dépassent `MAX_DATA_API_BODY_BYTES` (4 Mo, `core/config.py`). Elle est
refusée avant toute lecture si `Content-Length` annonce déjà plus. `iter_bytes` rend des octets
décodés : un corps compressé est borné par la place qu'il prend une fois lu. Sans cette borne,
`response.content` lisait tout le corps en mémoire, quelle que soit sa taille. C'est une défense
en profondeur : l'API de données est la nôtre, et ses réponses honnêtes restent loin dessous
(environ 2 Mo au pire pour une page de liste, estimation de la revue). Décision de Sabine, prise
sur un constat de `/code-review` : une borne dès maintenant, à corriger plus tard si besoin.

Rien n'est journalisé ici : #156 journalisera l'état une fois, avec l'identifiant de la demande
(règle 3 de `conventions.md` : un échec est journalisé là où il est traité).

### 4. Des modèles de réponse qui laissent tomber ce qui ne sert pas

```python
model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
```
`src/k_b/ai_api/data_api_client.py:66`

L'API IA ne peut pas importer les schémas de `data_api` (règle des dépendances) : elle a ses
propres modèles. Ils ne déclarent que les champs utiles, et `extra="ignore"` laisse tomber le
reste **dès la lecture du JSON**. Les auteurs d'un papier, servis par le détail, ne sont donc
jamais dans un objet Python de l'API IA. `strict=True` refuse un `id` envoyé en texte (`"2"`).
Pour le détail, l'union discriminée par `kind` (`DETAIL`, `data_api_client.py:132`) refuse une
sorte hors liste blanche, `zotero_entry` compris.

`exploited` est renommé à la lecture (`validation_alias="exploited"`, `data_api_client.py:114`) :
le modèle recevra `cve_listed_in_cisa_kev`. Le nom d'origine l'inviterait à lire un « faux »
comme « non exploitée ».

### 5. Masquer, puis couper

```python
masked = URL.sub(MASKED_URL, value)
return LOGIN.sub(MASKED_LOGIN, masked) if has_logins else masked
```
`src/k_b/ai_api/watch_items.py:157-158`

Chaque champ texte envoyé est masqué **à la lecture**. Le titre tel que servi reste à part,
sous le nom `source_title` : il sert aux sources de la réponse, jamais au modèle, qui reçoit
`fields.title`, masqué ; le nom le dit, pour que #205 ne les confonde pas (constat de
`/code-review`, corrigé). D'abord les URL (`[url]`), car une URL
peut porter un `@` (`https://jane@github.com`). Ensuite, dans `release.body` seulement, les
logins GitHub (`@user`). Le motif `LOGIN` (`watch_items.py:34`) exige que le `@` ne suive ni une
lettre, ni un chiffre, ni `.`, `/` ou `-`. Ainsi `jane.doe@example.com` n'est pas réécrit en
`jane.doe@user.com`, ce qui enverrait la partie locale d'une adresse en croyant l'avoir masquée.

On coupe ensuite, dans `select_for_writing` (`watch_items.py:161`) : les 60 items les plus
récents d'une fiche, chaque champ à 2 000 caractères. Masquer avant de couper, c'est l'ordre de
la spec : une URL coupée en deux ne serait plus reconnue, et sa moitié partirait au modèle.

Pourquoi masquer et couper avant le modèle :

- **Données personnelles** : un login est une donnée personnelle (registre des traitements),
  et le fournisseur du modèle est un tiers.
- **Injection** : une URL dans un texte d'item est une invitation à la recopier. Le modèle n'en
  écrit jamais (contrôle 6 de la spec), et il n'en reçoit pas.
- **Coût et délai** : les jetons se paient, et un champ de 50 000 caractères ne rend pas une
  fiche meilleure.

### 6. Des règles de sécurité écrites une fois

`outbound.py` porte la vérification d'une URL (jamais citée, car elle peut contenir une clé) et
la construction du client httpx2 (`follow_redirects=False`, `trust_env=False`,
`outbound.py:50`). Le client du modèle (#150) et celui de l'API de données l'appellent tous les
deux. Les deux constantes de la clé (32 caractères au moins, alphabet de `token_urlsafe`) vivent
dans `core/config.py` : `kb serve` et l'API IA appliquent la même règle.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une liste par sorte, dans l'ordre de la spec | Seule façon d'obtenir « les sortes rares d'abord » d'une liste triée par date | Une liste unique sans `kind=`, filtrée après : un import Zotero en masse entrerait dans la lecture (spec) |
| `covered_after` (borne exclue) et `capped_kind` | Vrai même avec des dates égales et une coupe entre deux sortes (décision de Sabine) | « Date du plus ancien item gardé » : promettait un jour lu en partie |
| Une exception `DataApiError` | Un échec arrête toute la lecture, sans mesure à garder | Rendre une union : chaque appelant devrait tester, pour rien |
| Pas de nouvelle tentative | Service local, la spec n'en prévoit pas | Reprendre la politique du modèle : une couche de plus sans cas observé |
| Lecture synchrone, détails l'un après l'autre | Les routes de #156 seront en `def` ; 13 détails lus en 66 ms à la démonstration | Client asynchrone ou parallèle : de la complexité pour un gain non mesuré |
| `extra="ignore"` sur les réponses | Les auteurs tombent dès la lecture ; un champ ajouté à l'API de données ne casse pas l'API IA | `extra="forbid"` : refuserait le détail d'un papier, qui porte `authors` |
| `KB_API_KEY_AI_DIGEST`, la variable de `kb serve` | Une seule valeur pour les deux côtés | `KB_DATA_API_KEY` : une seconde variable à tenir égale |
| `KB_DATA_API_URL` avec défaut local | Règle 2 de `poc.md` : un réglage de déploiement a un défaut nommé ; un secret n'en a pas | Pas de défaut : un réglage de plus à poser en local |
| 60 par fiche, livré en fonction (`select_for_writing`) | Le sujet n'est connu qu'au classement (#205) | Couper à 60 à la lecture : on perdrait des items avant de connaître leur sujet |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_reading_gives_the_items_of_the_whitelist_in_the_order_of_the_spec` | Contre la vraie API de données et la base d'essai : ordre des sortes, aucun `zotero_entry`, l'entrée retirée comptée et jamais demandée au détail |
| `test_an_item_read_keeps_its_source_and_sends_its_whitelist_only` | Le papier garde `url` et `source_title` pour les sources ; ses champs envoyés sont `title` et `summary` ; « Yixuan Liu » n'apparaît nulle part |
| `test_the_reading_follows_the_pages` | La pagination réelle (pages de 2) rend les mêmes items |
| `test_the_reading_is_capped_inside_a_kind`, `…_between_two_kinds_names_the_next_one`, `test_a_withdrawn_entry_takes_no_place_under_the_cap` | `capped_kind` et `covered_after` dans les deux cas de coupe ; les sortes suivantes ne sont pas lues |
| `test_a_failed_request_gives_its_state`, `test_an_answer_of_the_list_other_than_200_gives_its_state`, `test_a_detail_that_fails_gives_its_state` | Chaque état `data_api_*`, une redirection jamais suivie |
| `test_an_item_gone_between_the_list_and_the_detail_is_skipped_and_counted` contre `test_a_detail_that_fails_gives_its_state` (404 `route_not_found`) | Un item parti est sauté ; un mauvais service est un échec |
| `test_the_error_carries_neither_the_key_nor_what_was_received` | Ni la clé ni l'en-tête `Location` dans l'erreur ; pas de cause chaînée |
| `test_since_is_sent_in_utc_to_the_second_rounded_up`, `test_a_since_without_time_zone_is_refused` | `since` arrondi à la seconde suivante, l'an 1 écrit sur quatre chiffres, un fuseau sans décalage refusé |
| `test_a_body_up_to_the_bound_is_read`, `test_a_list_above_the_bound_gives_data_api_invalid_response`, `test_a_detail_above_the_bound_gives_data_api_invalid_response`, `test_an_item_not_found_is_still_read_under_the_bound`, `test_a_content_length_above_the_bound_is_refused_before_reading` | La borne de taille sur la liste et sur le détail ; un `Content-Length` trop grand refusé sans lire le corps (un corps qui fait échouer le test s'il est lu) |
| `test_the_masking_of_a_release_body` | URL avant login, adresse mail laissée, portée npm masquée |
| `test_the_client_reads_no_proxy_of_the_environment_and_follows_no_redirection` | Lu sur un client construit sans transport : avec un transport simulé, httpx2 ne lit jamais le proxy, et le test ne prouverait rien |
| Démonstration : `kb serve` sur une base d'essai, port 8765 | 13 items en 66 ms, `items_dropped: 1` ; 5 listes et 13 détails au journal, `client=AI_DIGEST` ; API arrêtée : `state: data_api_unavailable, http_status: None` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi l'API IA ne lit-elle pas la base directement ?** Elle n'a qu'une porte, l'API de
   données : clé révocable, lecture seule, journal par client. Au 08/11, les conteneurs ne
   partagent pas la base. Règle 7 de `poc.md`, prouvée par `tests/test_module_dependencies.py`.
2. **Que se passe-t-il si un import écrit pendant la lecture ?** La pagination par offset peut
   décaler une page. Un item vu deux fois est ignoré (`seen_ids`) ; un item manqué n'est pas
   détecté, c'est la limite écrite dans `specs-api.md`.
3. **`covered_after` : pourquoi pas la date du dernier item lu ?** Les dates TLDR sont égales
   dans une édition : on annoncerait couvert un jour lu en partie. Avec la date du premier item
   non lu, en borne exclue, la phrase est toujours vraie (ordre total de `GET /items`).
4. **Où sont les données personnelles ?** Les auteurs ne sont jamais lus (`extra="ignore"`). Les
   logins des corps de release sont masqués. Le login du propriétaire reste dans
   `repository_name` et `title`, ce que le registre permet. Une adresse mail n'est pas masquée :
   c'est une limite écrite.
5. **Et si l'API de données redirige vers un autre hôte ?** La redirection n'est pas suivie
   (`follow_redirects=False`) : elle devient `data_api_invalid_response`, et la clé ne part pas
   ailleurs.

## Zones non vérifiées

- Les délais (5 s de connexion, 10 s de lecture) sont **supposés**. La démonstration locale les
  laisse très loin (66 ms en tout), mais ils ne sont pas mesurés en conteneur.
- La lecture n'a **pas de borne totale**. Les délais bornent chaque attente, pas une requête : le
  délai de lecture vaut pour chaque morceau reçu, et un serveur qui envoie au compte-gouttes fait
  durer une requête sans fin. Aux 300 détails s'ajoutent jusqu'à 101 pages de liste par sorte.
  Seule `DIGEST_REQUEST_TIMEOUT_SECONDS` (#205) bornera la lecture, et `read_watch` ne se branche
  sur une route qu'avec elle (commentaire daté sur #205).
- Le comportement d'un `next_offset` nul au-delà de l'offset 10 000 n'est pas testé : il faudrait
  plus de 10 000 entrées retirées d'une même sorte dans la fenêtre.
- Le motif d'un login GitHub (39 caractères, lettres, chiffres, tirets) vient de la règle connue
  de GitHub, non revérifiée aujourd'hui à la source.

## Ce qui reste

- **#156** : calculer `since` depuis `window_days` ; lire les réglages au démarrage (sortie en
  code 2) ; journaliser l'état `data_api_*` avec l'identifiant de la demande ; mesurer
  `data_fetch_ms`. Le module commun des clés par client y vient aussi.
- **#205** : appeler `select_for_writing` pour chaque sujet ; couper à 500 au classement avec la
  même règle ; écrire les identifiants `"i17"` ; additionner les deux `items_dropped` ; poser
  `DIGEST_REQUEST_TIMEOUT_SECONDS` ; rendre nulle une `url` qui n'est pas en `http(s)`.

## Sources

Consultées le 2026-10-15.

- [The exception hierarchy](https://github.com/encode/httpx/blob/master/docs/exceptions.md) —
  httpx, lu par Context7 : `TimeoutException` et `NetworkError` sous `TransportError`,
  `DecodingError` sous `RequestError`. Recoupé sur httpx2 2.13.1 installé (classes parentes lues
  dans le paquet) : même hiérarchie. Fonde l'ordre des `except` de `send`.
- `starlette/testclient.py` (Starlette 1.8.0, paquet installé), lu par l'agent architecte :
  `TestClient` hérite de `httpx2.Client`. Fonde les tests contre la vraie API de données.
- `httpx2/_client.py` (paquet installé), lu par l'agent architecte : `allow_env_proxies = trust_env
  and transport is None`. Fonde le test de `trust_env` sur un client sans transport.
- [`docs/specs-api.md`](../specs-api.md) (« Tri et pagination », « Erreurs ») et
  [`docs/fiches-veille.md`](../fiches-veille.md) (« Lecture plafonnée », « Entrée du modèle »,
  « États nommés ») : le contrat lu et le contrat suivi. Les références OWASP (API4:2023, LLM01)
  sont dans les sources de la spec des fiches.
