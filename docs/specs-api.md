# Spécifications de l'API de données

L'API de données sert la veille et la bibliothèque de K-B, en lecture seule, sur la machine de
Sabine. Elle est appelée par les programmes de Sabine (terminal, scripts), par des agents, et par
l'API IA si celle-ci lit la base. Ce document fixe ce qu'elle sert, la règle de « quoi de neuf », l'accès par clé, les
erreurs et les exigences de sécurité. Les décisions et leur pourquoi sont dans le
[journal ADR](ADR/journal-decisions-projet.md) (entrées du 2026-10-14) ; la collecte, dans
[specs-collecte.md](specs-collecte.md) ; la base, dans [stockage.md](stockage.md).

**Version de la spec : 0.2.0**, la même que `info.version` de l'OpenAPI
(`docs/api/openapi-donnees.json`, que #184 écrit). Un changement de comportement visible par un client, comme
l'ordre des résultats, change la version.

| Version | Ce qui change pour un client |
|---|---|
| 0.1.0 | `GET /items` (#184) |
| 0.2.0 | `GET /items/{item_id}` et `GET /trends` servis (#185) ; un `item_id` au-delà de 64 bits répond 422 |

## Règles communes

- **Locale** : l'API écoute sur `127.0.0.1`, en dur ; `TrustedHostMiddleware` n'accepte que les
  hôtes `127.0.0.1` et `localhost`. Pas de CORS.
- **Lecture seule** : GET seulement. La base est ouverte en lecture seule (`mode=ro`), une
  connexion par requête.
- **Clé** : chaque route de données demande `Authorization: Bearer <clé>`. `/docs` et
  `/openapi.json` sont publics : ils ne contiennent aucune donnée.
- **Réponses** : JSON, champs en liste blanche (modèles de réponse propres à l'API, jamais le
  modèle de lecture des sources).
- **OpenAPI** : `kb openapi` (#184) écrit `docs/api/openapi-donnees.json`, versionné ; la CI le compare
  au schéma produit par l'app.
- **Journal** : une ligne par requête, horodatée en ISO 8601 UTC, à la seconde. Elle donne la
  méthode, le gabarit de route (`/items/{item_id}`, pas l'identifiant), le statut, la durée en ms
  et le nom du client (`-` pour un statut sans réponse envoyée, une route inconnue ou un client
  sans clé valide) ; jamais la clé, une valeur de paramètre ni un chemin brut. Elle va dans
  `<KB_DATA_DIR>/logs/kb-serve.log`, à part de `kb.log` : `kb serve` tourne longtemps, et la rotation
  de minuit faite par `kb collect` ou `kb import` dans un fichier partagé le laisserait écrire dans
  le fichier de la veille (constat sur `TimedRotatingFileHandler`, Python 3.13).
- **Organisation du code** : paquet `src/k_b/data_api/`, un dossier par rôle (`routers/`,
  `schemas/`) ; le détail et les options écartées sont au journal ADR (2026-10-14, « Paquet
  `src/k_b/data_api/` »).

## Accès par clé

- **Un client nommé, une clé** : la variable d'environnement `KB_API_KEY_<CLIENT>` porte la clé du
  client `<CLIENT>` (`[A-Z0-9_]+`, par exemple `KB_API_KEY_TERMINAL`, `KB_API_KEY_AGENT`).
  La clé identifie le programme qui appelle (le terminal ou un script de Sabine, un agent, l'API
  IA) ; aucune personne ne se connecte.
- **Clé générée en 256 bits** par `secrets.token_urlsafe(32)` ; le minimum contrôlé est de
  32 caractères. Au démarrage, `kb serve` refuse un
  nom de client vide ou hors `[A-Z0-9_]+`, une clé de moins de 32 caractères, une clé hors de
  l'alphabet de `token_urlsafe` (`[A-Za-z0-9_-]` : les espaces autour de la clé reçue sont retirées,
  une clé qui en porte ne serait jamais reconnue), deux clients de
  même clé, et l'absence de toute clé (code de sortie 2, message qui nomme la variable sans sa valeur).
- **Révocable seule** : retirer la variable d'un client et redémarrer l'API ; les autres clients
  restent servis. Un retrait ne prend effet qu'au redémarrage.
- **Vérification** : comparaison en temps constant (`hmac.compare_digest`). Sans clé, ou avec une
  clé inconnue, la réponse est la même : 401 `invalid_api_key`.
- **Pas de route de connexion**, pas de jeton à durée de vie : voir l'entrée « Clés par client »
  du journal.
- **Journal** : il nomme le client, jamais la clé. Un 401 est journalisé sans nom ni valeur reçue.

## Les parcours P1–P9

Les parcours de [la clarification du modèle](2026-10-07-clarification-modele.md) (section 2), et
la route qui répond à chacun.

| Parcours | Question | Route | Hors API, et pourquoi |
|---|---|---|---|
| P1 | Quoi de neuf depuis N jours, toutes sources ou par thème ? | `GET /items?since=…`, avec `kind` ou `q` pour un thème | — |
| P2 | Quelles nouvelles versions de mes outils ? | `GET /items?kind=release&q=<dépôt>` : le titre d'une release commence par son dépôt | — |
| P3 | Quelles failles touchent mes outils, mes paquets ? | `GET /items?kind=advisory` : les alertes ne sont collectées que pour les paquets suivis (`affects=`, [specs-collecte.md](specs-collecte.md)) | le filtre par paquet : non planifié |
| P4 | Cette faille est-elle exploitée activement ? | `GET /items/{item_id}` d'une alerte : `cve_id` et `exploited` | — ; limite : la liste n'a pas de `cve_id` et `q` ne cherche pas dans `cve_id`, on le lit au détail de l'alerte |
| P5 | Quels dépôts ont le vent en poupe ? | `GET /trends?window_end=…` | — |
| P6 | Quels papiers récents sur un sujet ? | `GET /items?kind=paper&q=…&since=…` | — |
| P7 | Quels sont les dépôts les plus étoilés (top 10) ? | — | hors API : les tops sont hors base (journal ADR, 2026-10-07) ; la commande `kb top`, décidée le 2026-10-08, n'est pas codée |
| P8 | Quels sont les dépôts les plus forkés (top 10) ? | — | hors API : les tops sont hors base (journal ADR, 2026-10-07), et le top des plus forkés n'est pas collecté (la recherche des plus étoilés trie par `stars`) |
| P9 | Quoi de neuf dans l'écosystème LangChain ? | `GET /items?q=langchain`, puis `GET /items?q=langgraph` : un seul morceau de texte par `q` | — |

Les chemins du brut (`raw_file_path`) ne sont servis par aucune route : un chemin local dévoile le
dossier personnel (API3, ci-dessous).

## `GET /items` : la liste et « quoi de neuf »

### Paramètres

| Paramètre | Forme | Bornes | Défaut | Hors bornes |
|---|---|---|---|---|
| `kind` | une valeur d'`ItemKind`, répétable (`kind=paper&kind=release`) | valeurs exactes : `kind=vulnerability` ne ramène pas les alertes (`advisory`) | toutes les sortes | 422 |
| `since` | date-heure ISO 8601 **avec fuseau** (`2026-10-07T00:00:00Z`, `2026-10-07T00:00:00%2B02:00`) ; dans l'URL, `+` s'écrit `%2B`, sinon il est lu comme une espace | — | aucun filtre de date | 422, sans fuseau compris, et pour un nombre (jamais lu comme une date Unix) |
| `q` | texte | de 1 à 200 caractères | aucune recherche | 422 |
| `limit` | entier | de 1 à 100 | 20 | 422 |
| `offset` | entier | de 0 à 10 000 | 0 | 422 |

### Règle de « quoi de neuf »

`since` porte sur **la date que la source donne**, propre à chaque sorte (tableau ci-dessous). Il
est converti en UTC, puis comparé en `>=` à cette date. Une date de jour (`date_added` de CISA,
`edition_date` de TLDR) est écrite à minuit UTC : `since=2026-10-07T00:00:00%2B02:00`
(soit `2026-10-06T22:00:00Z`) prend le 2026-10-07 et pas le 2026-10-06.

Ni la date de collecte ni une date de révision n'entrent dans la règle : un item ancien découvert
cette semaine n'apparaît pas dans « quoi de neuf » (limite assumée, journal ADR).

### Date, titre et résumé par sorte

| Sorte (`kind`) | Date de `since` (`source_date`) | Titre (`title`) | Résumé, cherché par `q` |
|---|---|---|---|
| `paper` | `publication.submitted_at` | `publication.title` | `publication.summary` |
| `vulnerability` | `vulnerability.date_added` | `vulnerability.name` | `vulnerability.description` |
| `release` | `release.published_at` | `<dépôt> <nom ou tag>` : `tracked_repository.repository_name`, une espace, puis `release.name`, ou `release.tag_name` si le nom est vide | `release.body` |
| `advisory` | `advisory.published_at` | `advisory.summary` | aucun : K-B ne lit et ne garde que `summary` |
| `newsletter_article` | `newsletter_article.edition_date` | `newsletter_article.title` | `newsletter_article.summary` |
| `zotero_entry` | `zotero_entry.saved_at` | `zotero_entry.title` | aucun |

### Tri et pagination

- Tri par `source_date` décroissante, puis par `id` décroissant.
- La réponse donne `next_offset`, l'`offset` de la page suivante, nul à la dernière page, ou quand
  l'offset suivant dépasserait 10 000 : les items au-delà ne sont pas servis par la liste ; affiner
  par `since`, `kind` ou `q`.
- Limite : un import qui écrit entre deux pages décale la pagination par `offset`.

### Réponse

```json
{
  "items": [
    {
      "id": 1234,
      "kind": "paper",
      "title": "…",
      "source_date": "2026-10-07T14:03:00Z",
      "url": "https://arxiv.org/abs/…",
      "withdrawn_at": null
    }
  ],
  "next_offset": 20
}
```

| Champ | Contenu |
|---|---|
| `id` | `item.id`, l'identifiant du détail |
| `kind` | la sorte |
| `title` | le titre (tableau ci-dessus) |
| `source_date` | la date de `since`, texte UTC `AAAA-MM-JJTHH:MM:SSZ`, comme en base |
| `url` | l'adresse de l'item ; nulle pour une entrée Zotero sans URL |
| `withdrawn_at` | date K-B du retrait d'une ligne de catalogue (vulnérabilité, entrée Zotero) ; nulle sinon |

Les lignes retirées sont servies avec leur `withdrawn_at`, pas filtrées.

**Pas dans la liste** : le résumé, la description, le corps d'une release, les auteurs (texte long
ou donnée personnelle, servis au détail), `raw_file_path` et `collected_at` (jamais servis).

## `GET /items/{item_id}` : le détail

`item.id` dans le chemin ; les clés naturelles sont des champs de la réponse. `item_id` est un
entier écrit en chiffres, sans zéro en tête, sans `+`, sans espace ni décimale (`1`, `-1`, pas
`01`, `1.0` ni `+1` : une seule URL par item), tenu sur 64 bits ; sinon 422 `invalid_parameter`.
Un entier qu'aucun item ne porte rend 404 `item_not_found`. La réponse reprend les six champs de
la liste et, selon la sorte (`kind`, qui dit le schéma suivi : `oneOf` et `discriminator` dans
l'OpenAPI), exactement ceux-ci :

| Sorte | Clés naturelles | En plus de la liste |
|---|---|---|
| `paper` | `arxiv_id` | `authors` (les noms, dans l'ordre d'arXiv), `summary`, `arxiv_updated_at` (colonne `publication.revised_at`, date arXiv) |
| `vulnerability` | `cve_id` | `description`, `vendor`, `product`, `ransomware_use`, `revised_at` (date K-B) |
| `release` | `release_id` | `repository_name`, `tag_name`, `body` (le corps) |
| `advisory` | `ghsa_id` | `cve_id` (nul si l'alerte ne cite aucune CVE), `exploited`, `packages` (les paquets touchés) |
| `newsletter_article` | `edition`, `edition_date`, `rank` | `summary` |
| `zotero_entry` | `zotero_key` | `item_type`, `arxiv_id` (lu par `publication_id`, nul hors arXiv), `revised_at` (date K-B), `highlights` : les surlignages, retirés compris, par date de création |

Un surlignage sert `text`, `comment`, `highlighted_at` (date Zotero), `revised_at` et
`withdrawn_at` (dates K-B) ; sa clé Zotero n'est pas servie. Le `name` d'une release n'est pas
servi : il est dans `title`. Les dates sont servies comme en base (`AAAA-MM-JJTHH:MM:SSZ`).
L'OpenAPI décrit chaque date par son origine : date K-B (la collecte qui a vu le changement),
date arXiv ou date Zotero.

`exploited` vaut vrai si la CVE de l'alerte est au catalogue CISA KEV
(`vulnerability.item_id IS NOT NULL`) : faux veut dire « absente du catalogue KEV », pas « non
exploitée ». Il est nul pour une alerte sans CVE. Il reste vrai si la CVE a été retirée du
catalogue depuis : le retrait se lit dans `withdrawn_at`, au détail de la vulnérabilité, que
le détail de l'alerte ne désigne pas encore (« Hors de cette version »).

`source_date` et `arxiv_updated_at` sont des noms de champs de l'API : ils ne renomment aucune
colonne (décision ouverte « Noms des colonnes de date », journal ADR).

## `GET /trends` : les dépôts qui montent

| Paramètre | Forme | Défaut | Hors bornes |
|---|---|---|---|
| `window_end` | date écrite `AAAA-MM-JJ` exactement, le dernier jour d'une fenêtre de 3 jours | la fenêtre la plus récente en base | 422 : une autre forme (`20261012`, `2026-10-12T00:00:00Z`), un nombre (jamais lu comme une date Unix), une date qui n'existe pas (`2026-02-30`) |

```json
{
  "window_end": "2026-10-12",
  "trends": [
    {
      "repository_id": 123456,
      "repository_name": "owner/repo",
      "stars_gained": 1500,
      "forks_gained": 120
    }
  ]
}
```

- Une ligne par dépôt : les 30 premiers par étoiles gagnées et les 30 premiers par forks gagnés,
  réunis, soit 60 lignes au plus ; pas de pagination.
- Tri par `stars_gained` décroissant, puis `forks_gained` décroissant, puis `repository_id`.
- `window_end` est stocké à minuit UTC et rendu en `AAAA-MM-JJ`.
- **Fenêtre absente : 404 `trend_window_not_found`**, dans les deux cas du tableau des erreurs.
  Pourquoi (choix de la session K-B, validé par Sabine le 2026-10-14) : une fenêtre n'existe en
  base que par ses lignes : une liste vide ne décrirait aucune fenêtre
  réelle, et le client ne distinguerait pas une date sans fenêtre d'une réponse valide. L'état
  nommé dit ce qui est observé, comme `item_not_found`.
- Limite : les fenêtres glissent d'un jour et aucune route ne les liste ; sans `window_end`, la
  route rend la plus récente.

## Erreurs

Corps : `{"error": "<état>"}`. Aucune erreur ne renvoie de pile, de requête SQL, de chemin ni la
valeur reçue.

| État | Statut | Quand |
|---|---|---|
| `invalid_api_key` | 401 | route de données appelée sans clé, ou avec une clé inconnue (même corps) |
| `item_not_found` | 404 | `GET /items/{item_id}` : aucun item de cet identifiant |
| `trend_window_not_found` | 404 | `GET /trends?window_end=…` : aucune tendance pour cette fenêtre |
| `trend_window_not_found` | 404 | `GET /trends` sans `window_end` : aucune tendance en base |
| `route_not_found` | 404 | chemin inconnu |
| `method_not_allowed` | 405 | méthode autre que GET |
| `invalid_parameter` | 422 | paramètre hors bornes ou mal formé ; le corps ajoute `"parameters": [<noms>]`, sans les valeurs |
| `database_missing` | 503 | la base n'existe pas |
| `database_error` | 500 | toute autre erreur de la base, sans détail |
| `internal_error` | 500 | toute autre erreur, sans détail ; journalisée par son type seul, sans pile ni message |

Exception : un `Host` qui n'est ni `127.0.0.1` ni `localhost` reçoit le 400 de
`TrustedHostMiddleware`, qui répond avant l'app, en texte.

## Recherche `q`

- `q` cherche un morceau de texte dans le titre et le résumé (tableau « Date, titre et résumé par
  sorte »), jamais dans le texte des surlignages (journal ADR, 2026-10-09).
- Moyen : `LIKE … ESCAPE` de SQLite ; `%` et `_` sont cherchés tels quels.
- Comportement relevé le 2026-10-14 sur SQLite 3.50.4 (module `sqlite3` de Python) et 3.51.0
  (commande `sqlite3`), base en mémoire :

  | Recherche | Texte | Trouvé |
  |---|---|---|
  | `vuln` | « Vulnérabilités », « vulnerability » | oui (morceau de mot) |
  | `abc` | « ABC » | oui (casse ignorée, lettres sans accent) |
  | `vulnerabilite` | « Vulnérabilité » | non (accents exacts) |
  | `É` | « é » | non |

- Tri par date, comme sans `q`.
- **Écart temporaire** à la recherche plein texte triée par pertinence (journal ADR,
  2026-10-09) : elle se fera avec PostgreSQL (`tsvector`) après le 08/11 (journal ADR,
  2026-10-15, « POC du 25/10 », décision 2), changera l'ordre des résultats avec `q`, et passera
  la spec et l'OpenAPI à une nouvelle version.

## Données personnelles

Selon le [registre des traitements](registre-traitements.md) :

- les noms des auteurs d'un papier et les logins écrits dans le corps d'une release : au détail
  seulement, jamais dans la liste ni au journal ;
- le login du propriétaire d'un dépôt, dans le nom du dépôt : servi par `/trends`
  (`repository_name`), dans le titre d'une release (liste) et dans son `repository_name`
  (détail) ;
- les titres et dates des entrées Zotero de Sabine : dans la liste ; ses surlignages et
  commentaires : au détail de leur entrée.

Un agent qui lit ces données les envoie au fournisseur de son modèle : décision ouverte
« Transfert hors UE par les agents » (journal ADR).

## Sécurité : OWASP API Security Top 10 (2023)

Ce que l'API vise pour chaque exigence. La dernière colonne est remplie par l'issue qui sert le
détail et les tendances (#185 : « chaque ligne dit si l'exigence est tenue, et par quel test »).

| Exigence | Intention | Tenue, par quel test |
|---|---|---|
| API1:2023 Broken Object Level Authorization | Une seule propriétaire, Sabine : tout client authentifié lit tous les items. Un identifiant inconnu rend 404, jamais une erreur qui dirait autre chose. `item.id`, séquentiel, est dans l'URL : la recommandation d'identifiants difficiles à deviner est écartée tant que l'API n'a qu'une propriétaire (journal ADR, 2026-10-15). | **Tenue.** `test_each_client_is_served_with_its_key`, `test_an_unknown_item_id_gives_404_item_not_found`, `test_an_unknown_window_gives_404` |
| API2:2023 Broken Authentication | Une clé par client, générée en 256 bits (minimum contrôlé : 32 caractères) ; pas de route de connexion ; comparaison en temps constant ; 401 testé sur chaque route de données. | **Tenue.** `test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body` (les trois routes, lues dans l'app), `test_an_app_without_key_refuses_every_data_route`, `test_a_removed_key_gives_401_and_the_other_clients_are_still_served`, `test_serve_exits_2_and_names_the_variable_without_its_value` ; le temps constant n'est pas mesuré par un test (`hmac.compare_digest`, `dependencies.py`) |
| API3:2023 Broken Object Property Level Authorization | Réponses en liste blanche : ni `raw_file_path`, ni `collected_at`, ni texte long dans la liste ; au détail, les champs du tableau de sa sorte et rien d'autre. | **Tenue.** `test_the_list_serves_only_the_six_fields`, `test_each_kind_has_its_detail` (corps entier, une sorte par cas), `test_no_detail_serves_a_raw_file_path_or_a_collection_date`, `test_trends_without_window_end_give_the_latest_window`, `test_no_error_body_holds_a_raw_file_path_or_a_path`, `test_no_route_documents_a_raw_file_path_or_a_collection_date` |
| API4:2023 Unrestricted Resource Consumption | Bornes de `limit` (100), `offset` (10 000) et `q` (200 caractères) ; `/trends` rend 60 lignes au plus, sans pagination. Pas de limite de débit : le client est local. | **Non tenue** : aucun délai de requête (« Hors de cette version »), aucune limite de débit, et le détail d'une entrée Zotero sert tous ses surlignages, sans borne de nombre (chacun jusqu'à 10 000 caractères de texte et autant de commentaire). Ce qui est tenu : les bornes et la taille de page, `test_a_parameter_out_of_bounds_gives_422_with_its_name_only`, `test_next_offset_stops_at_the_offset_bound`, `test_an_item_id_not_written_as_an_integer_gives_422`, `test_a_malformed_window_end_gives_422` ; les 60 lignes d'une fenêtre sont bornées à la collecte (`gh_archive.py`), pas par l'API |
| API5:2023 Broken Function Level Authorization | GET seulement, 405 sinon ; aucune route d'administration. | **Tenue.** `test_every_data_route_refuses_another_method_with_405`, `test_the_data_routes_are_listed`, `test_docs_and_openapi_are_public_and_no_other_page_is_served` |
| API6:2023 Unrestricted Access to Sensitive Business Flows | Sans objet : l'API n'a aucun flux métier à protéger (ni achat, ni réservation, ni création de compte), seulement des lectures. | Sans objet, sans test |
| API7:2023 Server Side Request Forgery | Sans objet : l'API ne va chercher aucune adresse fournie par un client. | Sans objet, sans test |
| API8:2023 Security Misconfiguration | Hôte `127.0.0.1` en dur, `TrustedHostMiddleware`, pas de CORS, erreurs sans pile. Limite : Swagger UI (`/docs`) charge ses fichiers depuis un CDN. | **Tenue, avec la limite du CDN.** `test_serve_listens_on_127_0_0_1_without_uvicorn_logging_config`, `test_a_host_other_than_localhost_gives_400`, `test_no_route_answers_cors`, `test_an_unexpected_error_gives_500_internal_error_and_logs_its_type_only`, `test_a_database_error_gives_500_without_detail_and_logs_its_type` |
| API9:2023 Improper Inventory Management | OpenAPI versionnée (`docs/api/openapi-donnees.json`), comparée en CI au schéma produit. | **Tenue.** `test_the_versioned_openapi_is_the_one_the_app_produces`, `test_the_versioned_openapi_is_valid_and_declares_its_security_scheme`, `test_each_data_route_documents_its_errors` |
| API10:2023 Unsafe Consumption of APIs | Le contenu servi vient de tiers (arXiv, GitHub, CISA, TLDR, Zotero) : pour un client, et d'abord pour un agent, c'est une donnée, jamais une consigne. Côté K-B, la réponse d'une source est validée à la collecte (modèles de `items.py`, `CHECK` de `schema.sql`). | **Tenue côté K-B** : `tests/test_schema.py` (chaque type refusé par l'item et par la base) et les tests de chaque source. Côté client, une consigne, sans test |

## Hors de cette version

- Les filtres `source` et `in` : options de `kb search` seulement (#187).
- Le filtre par paquet (P3).
- Les tops P7 et P8.
- Une limite de débit : le client est local.
- **Un délai de requête : non tenu.** `conformite.md` (API4) cite le délai, et un `LIKE '%q%'`
  lit tout `release.body`, jusqu'à 125 000 caractères par release. Signalé, sans issue.
- **D'une alerte à sa vulnérabilité** : le détail d'une alerte dit `cve_id` et `exploited`, pas
  l'`id` de l'item vulnérabilité ; la liste n'a pas `cve_id` et `q` ne le cherche pas. Un client
  ne peut donc pas lire au détail de la vulnérabilité si elle a été retirée du catalogue KEV.
  Signalé ; une issue sera créée.

## Sources (consultées le 2026-10-14)

- [OWASP Top 10 API Security Risks — 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/) : les noms et
  le périmètre des dix exigences du tableau de sécurité.
- [API2:2023 Broken Authentication](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication/), section
  « How To Prevent » — OWASP : une clé d'API authentifie un programme client, pas une personne
  (accès par clé).
- [Bigger Applications — Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) — FastAPI,
  lu par Context7 : un `APIRouter` par module, `include_router` (organisation du paquet).
- [Advanced Middleware, `TrustedHostMiddleware`](https://fastapi.tiangolo.com/advanced/middleware/) — FastAPI,
  lu par Context7 : un `Host` non permis reçoit un 400 (erreurs).
