# Un seul téléchargement pour toutes les sources

- **Date** : 2026-10-04
- **Branche** : `refactor/common-download`
- **Issue** : #50
- **Fichiers principaux** : `src/k_b/http_download.py` (nouveau), `src/k_b/github_api.py`,
  `src/k_b/cisa_kev_source.py`, `src/k_b/arxiv_source.py`, `tests/test_http_download.py`
- **Série** : reprend le bloc de téléchargement décrit dans
  [collecte-cisa-kev](2026-09-30-collecte-cisa-kev.md),
  [collecte-releases-github](2026-10-02-collecte-releases-github.md) et
  [collecte-arxiv](2026-10-02-collecte-arxiv.md).

## Le pourquoi

Chaque source téléchargeait sa réponse avec le même bloc de dix lignes : `urlopen`, un délai, un
contrôle de l'URL finale après redirection, un plafond de taille. Ce bloc existait en trois
copies (GitHub, CISA, arXiv), et TLDR (#13) en aurait ajouté une quatrième. Or ce bloc est la
**frontière réseau** de K-B : l'endroit où des octets d'Internet, non fiables, entrent dans le
projet. Un contrôle de sécurité corrigé dans une copie et oublié dans une autre, c'est une faille.
La règle du dépôt (`.claude/rules/code.md`) demande de factoriser à la troisième occurrence : on
y était. La revue de la PR #49 l'avait relevé et mis de côté pour garder cette PR chirurgicale.

Le comportement ne change pas : c'est une refactorisation pure.

## Le comment

### Une fonction, quatre contrôles

`src/k_b/http_download.py:22-32` :

```python
request = Request(url, headers={**(headers or {}), "User-Agent": USER_AGENT})
...
with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
    if not response.url.startswith(trusted_url_prefix):
        raise ValueError(f"response redirected outside {trusted_url_prefix}, refused")
    body = response.read(max_bytes + 1)
if len(body) > max_bytes:
    raise ValueError(f"response larger than {max_bytes} bytes, refused")
```

Les quatre défenses de la frontière sont là, une fois : le `User-Agent` qui dit qui interroge, le
délai de 30 s, le préfixe de confiance, le plafond de taille. Ce que chaque source sait seule
reste chez elle et est passé en paramètre : son URL, son préfixe, son plafond (mesuré et commenté
dans son module), ses en-têtes propres.

### Le `User-Agent` posé en dernier

Dans `{**(headers or {}), "User-Agent": USER_AGENT}` (`http_download.py:22`), le `User-Agent` est
écrit **après** les en-têtes de l'appelant : en Python, dans un dictionnaire, la dernière clé
gagne. Une source ne peut donc ni l'oublier ni le remplacer. C'est pour cela que la fonction
l'ajoute d'office au lieu de le laisser aux appelants.

### Le contrôle de redirection

`urlopen` suit les redirections tout seul, même d'`https` vers `http` ou vers un autre domaine.
On ne l'empêche pas : on vérifie **où l'on a fini** (`response.url`) avant de lire le corps
(`http_download.py:27`). Le préfixe se termine par `/` (`https://www.cisa.gov/`), si bien que
`https://www.cisa.gov.example.com/` ne passe pas : c'est testé.

### Le plafond lu à `max_bytes + 1`

`response.read(max_bytes + 1)` (`http_download.py:29`) ne lit jamais plus d'un octet au-delà du
plafond, même si le serveur envoie un gigaoctet. Si l'on a obtenu ce `+1`, la réponse est trop
grosse et refusée. Un test vérifie qu'une réponse **exactement** au plafond passe.

### Le jeton GitHub, jamais transmis à une redirection

`src/k_b/github_api.py:25-26` :

```python
# Never forwarded to a redirection: the token stays with api.github.com.
unredirected_headers={"Authorization": f"Bearer {token}"} if token else None,
```

`urllib` distingue deux sortes d'en-têtes : ceux de `request.headers`, recopiés sur la requête
suivante quand une redirection est suivie, et ceux ajoutés par `add_unredirected_header`, qui ne
quittent jamais la première requête. La fonction commune expose les deux (`headers`,
`unredirected_headers`) ; GitHub met son jeton dans la seconde. Sans jeton, rien n'est envoyé.

### Le 304 de CISA reste chez CISA

`src/k_b/cisa_kev_source.py:26-32` : la fonction commune laisse remonter `HTTPError`. Seul CISA
sait qu'un 304 (« pas modifié depuis ») veut dire « rien de neuf », donc renvoyer `None` ; il
l'attrape autour de l'appel. Pour une autre source, un 304 inattendu reste une erreur.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| urllib, bibliothèque standard | aucune dépendance (`dependencies = []`), contrôles déjà écrits et testés, dans l'estimation d'1 h | **httpx** : défauts plus sûrs (ne suit pas les redirections, délai de 5 s partout) et `MockTransport` pour les tests, mais une dépendance de plus et trois sources à réécrire ; le SDK Anthropic repose désormais sur `httpx2`, les deux paquets cohabiteraient le jour où un LLM rédigera les fiches. **requests** : aucun délai par défaut. |
| Paramètres simples (`url`, `headers`…) | l'appelant ne peut pas oublier le `User-Agent` | Passer un `Request` tout fait : chaque source devrait penser au `User-Agent` |
| Nouveau module `http_download.py` | CISA, arXiv et bientôt TLDR n'ont rien à voir avec GitHub | Garder la fonction dans `github_api.py` : une dépendance sans raison vers un module GitHub |
| `HTTPError` remonte | le sens d'un code HTTP dépend de la source | Gérer le 304 dans la fonction commune : ce serait de la logique CISA hors de CISA |
| `arxiv_source.download` renommée `download_papers` | éviter deux fonctions `download` dans le même module | — |
| Tests de redirection et de taille regroupés dans `test_http_download.py` | le contrôle n'existe plus qu'à un endroit ; critère de fin de #50 | Les garder dans chaque source : trois copies de tests du même code |

Factoriser à la troisième occurrence est imposé par `.claude/rules/code.md`. En passant, le
commentaire de `user_agent.py` est mis à jour : le dépôt est privé jusqu'au 25/10, puis public
(accord de Sabine).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_http_download.py` échoue avant le module (erreur de collecte), passe après (9 tests) | les tests ont été écrits d'abord |
| `test_the_request_names_k_b_and_has_a_timeout` | `User-Agent` et délai posés d'office |
| `test_an_unredirected_header_is_sent_but_never_forwarded_to_a_redirection` | l'en-tête est envoyé mais absent de `request.headers`, ceux que `urllib` recopie |
| `test_a_redirection_away_from_the_trusted_prefix_is_refused` (`http://`, domaine suffixé) | le contrôle de l'URL finale tient |
| `test_a_body_larger_than_the_limit_is_refused`, `..._exactly_at_the_limit_is_returned` | le plafond tombe au bon octet |
| `test_an_http_error_is_raised_to_the_caller` | le 304 reste à la charge de la source |
| Tests existants des sources (304 de CISA, jeton GitHub, fenêtre arXiv) verts, inchangés hormis la cible du faux `urlopen` | comportement inchangé |
| `uv run pytest` : 146 passed | aucune régression |
| `grep -rn urlopen src/` : seul `http_download.py` | plus aucune copie du bloc |
| Revue de code et revue de sécurité en sous-agents : aucun constat | ni bogue ni contrôle affaibli relevé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas avoir pris httpx, plus moderne ?** Nos quatre contrôles existaient et
   étaient testés ; httpx coûtait une dépendance et une réécriture, sans contrôle de taille
   intégré non plus. Il deviendrait utile pour des requêtes en parallèle, que la v0 ne fait pas.
   (`http_download.py`)
2. **Une source peut-elle envoyer un autre `User-Agent` ?** Non : il est écrit après ses
   en-têtes, la dernière clé gagne. (`http_download.py:22`)
3. **Que se passe-t-il si api.github.com redirige vers un autre site ?** Le jeton ne suit pas
   (en-tête non redirigé), et la réponse est refusée car l'URL finale sort du préfixe.
   (`github_api.py:26`, `http_download.py:27`)
4. **Et si un serveur envoie 1 Go ?** On lit au plus le plafond + 1 octet, puis on refuse.
   (`http_download.py:29-31`)
5. **Où est la logique du 304 ?** Chez CISA seul ; la fonction commune ne connaît aucun code
   HTTP. (`cisa_kev_source.py:26-32`)

## Zones non vérifiées

- Les tests remplacent `urlopen` par un faux : on vérifie que `Authorization` n'est pas dans
  `request.headers`, et l'on s'appuie sur la documentation d'`urllib` pour le fait que seuls ces
  en-têtes sont recopiés lors d'une redirection. Aucune vraie redirection n'est jouée.
- Remarque de la revue de code, non corrigée : les tests de redirection et de taille ne vivent
  plus qu'une fois. Si une source passait un jour le mauvais préfixe ou le mauvais plafond à
  `download` (arguments inversés, par exemple), aucun test ne le verrait.
- Le délai de 30 s ne borne que l'attente entre deux paquets, pas la durée totale d'un
  téléchargement (comportement d'`urllib`, déjà vrai avant cette PR).

## Ce qui reste

- TLDR (#13) utilisera `download` pour lire ses pages HTML, sans quatrième copie.
- Les sources GitHub (releases, alertes, dépôts étoilés) passaient déjà par
  `get_from_github_api` : elles en profitent sans changement.
