# Le lecteur des releases tire le dépôt de son brut

- **Date** : 2026-10-06
- **Branche** : `refactor/release-repository-from-raw`
- **Issue** : #98 (plan ETL, étape 2 : `docs/2026-10-06-plan-etl.md`)
- **Fichiers principaux** : `src/k_b/github_releases.py`, `src/k_b/tracked_repositories.py`,
  `src/k_b/github_releases_source.py`
- **Série** : suit `2026-10-06-ranger-les-conversions.md` (PR #102). La branche part de celle de la
  PR #102, dont les 4 commits (`c0cfc54` à `10f26a7`) sont expliqués dans cette note-là. Celle-ci
  ne couvre que `8e13f33` et `aa3b1da`.

## Le pourquoi

Pour qu'un ETL soit explicite, l'étape T doit pouvoir lire un fichier brut sans savoir qui l'a
collecté. Or le lecteur des releases recevait le dépôt de la source suivie :
`read_releases(raw_response, repository)`. Le brut d'un dépôt retiré de la liste suivie ne
pouvait donc plus être relu (#87). Pourtant, l'information est dans le brut : chaque release a une
`html_url` de la forme `https://github.com/<propriétaire>/<nom>/releases/tag/<tag>`.

Ce travail rend le lecteur autonome. Il met aussi la règle du nom de dépôt à un seul endroit.

## Le comment

### 1. Une seule règle du nom de dépôt

`src/k_b/tracked_repositories.py:51-57` :

```python
def is_repository_name(text: str) -> bool:
    return (
        OWNER_SLASH_NAME.fullmatch(text) is not None
        and ".." not in text
        and "." not in text.split("/")
    )
```

La même règle était écrite deux fois, dans `github_releases_source.py` et
`github_most_starred.py`. Elle n'existe plus qu'ici, et les trois usagers l'importent
(`github_releases.py:10`, `github_releases_source.py:21`, `github_most_starred.py:51`).
`tracked_repositories.py` ne fait aucun appel externe et sert déjà toutes les sources GitHub.
La règle refuse tout ce qui l'était déjà, et en plus un propriétaire ou un nom égal à `.`.

### 2. Le dépôt est lu dans l'URL, et toute l'URL est contrôlée

`src/k_b/github_releases.py:16-19` et `:55-59` :

```python
RELEASE_URL = re.compile(
    rf"https://github\.com/({OWNER_SLASH_NAME.pattern})/releases/tag/"
    r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/-]|%[0-9A-Fa-f]{2})+"
)
...
    url_match = RELEASE_URL.fullmatch(url) if isinstance(url, str) else None
    if (
        url_match is None
        or not is_repository_name(url_match.group(1))
        or has_dot_segment(url_match.string)
    ):
```

- `fullmatch` impose que **toute** l'URL ait cette forme, pas seulement son début.
- Le groupe 1 est le dépôt, réutilisé du motif commun : la règle n'est pas recopiée.
- La partie du tag n'accepte que les caractères de chemin de la RFC 3986, plus `/`. Un `%` n'y
  est admis que suivi de deux chiffres hexadécimaux, comme la RFC le demande. Il n'y a donc ni
  `?` (requête), ni `#` (fragment), ni espace, ni caractère non ASCII, ni le RLO (caractère
  invisible qui inverse le sens d'affichage).
- `isinstance(url, str)` passe avant le motif : un `html_url` absent donne une `ValueError`, que
  l'import sait rattraper. `RELEASE_URL.fullmatch(None)` lèverait au contraire un `TypeError`, que
  l'import ne rattrape pas.

### 3. Pourquoi refuser les segments `.` et `..`

`src/k_b/github_releases.py:86-88` :

```python
def has_dot_segment(url: str) -> bool:
    """A `.` or `..` path segment, even percent-encoded: a browser would resolve it."""
    return any(segment in (".", "..") for segment in unquote(url).split("/"))
```

C'est le constat 1 de la revue de sécurité, reproduit avant correction. Avec
`https://github.com/a/b/releases/../../../evil/x/releases/tag/v9`, le titre disait `a/b`, mais un
navigateur résout les `..` et ouvre `evil/x`. Le titre et le lien doivent désigner le même dépôt.

Ce cas précis est refusé par le motif, pas par `has_dot_segment` : `/releases/tag/` doit suivre
directement le dépôt. `has_dot_segment` refuse les `..` placés **après** `tag/`, comme
`…/releases/tag/../../../../evil/x`. `unquote` décode `%2e` en `.` avant le découpage : un `..`
déguisé (`%2e%2e`, `.%2e`, `%2E.`) est vu aussi. Il refuse un peu trop : `%2f` décodé en `/` coupe
un segment que le navigateur garderait entier. Ce n'est pas un trou de sécurité.

### 4. La collecte refuse une page d'un autre dépôt

`src/k_b/github_releases_source.py:35-41` :

```python
        for position, release in enumerate(releases):
            if release.repository.lower() != self.repository.lower():
                raise ValueError(
```

C'est la défense en profondeur : le lecteur fait maintenant confiance à l'URL, alors la collecte
vérifie que la page reçue est bien celle du dépôt demandé. La casse est ignorée, car GitHub peut
écrire `Anthropics/Claude-Code` là où la liste suivie écrit `anthropics/claude-code`. Le contrôle
passe **avant** le retour de la première collecte (ligne 41) : sans cela, la première collecte y
échapperait.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| La règle dans `tracked_repositories.py` | Module pur, commun aux sources GitHub, déjà consacré aux dépôts. | `github_releases.py` : le classement importerait une autre source. `github_api.py` : module d'entrées/sorties. `items.py` : il ne garde que le modèle commun. |
| `RepositoryName` (`items.py`) laissé tel quel | C'est le point S5 de la revue d'architecture, à part. | L'unifier ici : élargirait la PR. |
| `fullmatch` sur toute l'URL | Décision de Sabine après la revue de sécurité : le lien doit ouvrir le dépôt du titre. | Garder `.match` ancré au début seulement : laissait passer `…/releases/../../evil/x`. |
| Accepter `/` dans le tag | Git autorise `/` dans un nom de tag. | Le refuser : je n'ai pas vérifié si GitHub l'écrit tel quel dans `html_url`, et des releases réelles seraient peut-être refusées. |
| `url=url_match.string` | `mypy --strict` refuse `url=url` (`"Any \| None"; expected "str"`) : il ne déduit pas que `url` est un texte une fois le motif trouvé. | `url=url` : proposé par la revue de code, refusé par mypy. |
| Refuser tout le fichier sur une release invalide | Comportement inchangé (`raw_items.py:82`). | Écarter la seule release fautive : c'est #61. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_repository_is_read_in_the_release_url` (`tests/test_github_releases.py:82`) | Un dépôt non suivi est lu, et son nom vient de l'URL. |
| `test_a_release_url_with_any_path_character_in_its_tag_is_read`, 4 cas | Un tag avec `/`, `+`, `==` ou un caractère encodé `%E2%80%A6` est lu. |
| `test_a_release_url_without_a_repository_is_refused_with_the_url`, 20 cas | `None`, `.`, `..`, `...`, `%2e%2e`, `.%2e`, `%2E.`, la barre oblique inverse, un `%` mal formé, un autre hôte, une requête, un fragment, un espace, un retour à la ligne, le RLO et une URL sans `tag/` sont refusés, et le message cite l'URL. |
| Mutants : sans `is_repository_name` (lancé ici : 1 échec, le cas `a/...`) ; sans `has_dot_segment`, `match` au lieu de `fullmatch`, sans `unquote` (lancés par le relecteur indépendant, avant les cas ajoutés) | Chacun fait échouer au moins un test : chaque contrôle est couvert. |
| `test_a_page_of_another_repository_is_refused` (`tests/test_github_releases_source.py:63`), sur `None` et une date | La collecte refuse un autre dépôt, dès la première collecte. |
| `test_the_case_of_the_repository_name_is_ignored` (`:70`) | `Anthropics/Claude-Code` suivi accepte la page de `anthropics/claude-code`. |
| `test_a_release_is_titled_by_the_repository_of_its_url` (`tests/test_raw_items.py:73`) | Le brut de claude-code, rangé dans le dossier de langchain, reste titré claude-code : le dossier ne compte plus. |
| Cas `./x`, `x/.` (source) et `owner/.` (classement) | La règle commune refuse `.` partout où elle sert. |
| Avant le code : 24 tests rouges ; puis 9 pour l'URL entière ; puis 2 pour le `%` mal formé. Après : 282 réussis, ruff, format et mypy verts | Les tests visaient le comportement voulu, et rien d'autre n'a cassé. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi faire confiance à l'URL écrite dans le brut ?** C'est une entrée non fiable, donc
   elle est validée à la frontière par un motif fermé (`github_releases.py:16-19`, `:55-59`). Et la
   collecte vérifie le dépôt contre celui qu'elle a demandé (`github_releases_source.py:35-40`).
2. **Une release d'un autre dépôt peut-elle entrer par l'import ?** Oui, si le brut a été déposé ou
   modifié à la main, ou écrit avant ce contrôle : l'import ne compare pas au dossier, c'est voulu
   (`raw_items.py`, commentaire du `case GithubReleasesSource()`). Le dépôt lu reste un nom valide.
   Il ne va que dans le titre, puis dans une requête SQL paramétrée.
3. **Que se passe-t-il si un dépôt suivi est renommé chez GitHub ?** La page renvoie le nouveau
   nom, la collecte la refuse à chaque fois, et l'erreur cite les deux dépôts. C'est la défense
   voulue. Il faut alors mettre à jour la liste suivie.
4. **Pourquoi `unquote` avant de chercher les `..` ?** Parce qu'un navigateur traite `%2e` comme
   `.` dans un chemin. Sans décodage, `%2e%2e` passerait.
5. **Qu'est-ce qui change pour l'utilisateur ?** Le titre d'une release prend le dépôt écrit par
   GitHub, et plus celui de la liste suivie. L'identité de l'item (`release_id`) ne change pas,
   donc le dédoublonnage non plus.

## Zones non vérifiées

- La forme réelle de toutes les `html_url` de release que GitHub produit : seules les 3 de la
  fixture (claude-code) sont vérifiées. Je n'ai pas vérifié si un tag avec `/`, `+` ou un caractère
  non ASCII est écrit tel quel ou encodé. Si GitHub écrit un caractère hors de la classe, la
  release est refusée et son fichier entier aussi.
- La casse que GitHub renvoie pour les 4 dépôts suivis, et la redirection d'un dépôt renommé.
- Les bruts déjà écrits avant ce contrôle : non relus avec la nouvelle règle.
- La résolution des URL : un relecteur indépendant a fait résoudre 28 URL par `new URL()` de
  Node (standard WHATWG). Aucun navigateur n'a été testé directement.
- Le routage du serveur de GitHub : s'il décodait `%252e` deux fois, ou traitait `..;` comme `..`,
  une URL acceptée pourrait changer de dépôt. Hypothèse non testée. `;` et `%25` restent acceptés,
  car ce sont des caractères de chemin valides (décision de Sabine, 2026-10-06).

## Ce qui reste

- **Un brut trop imbriqué fait tomber l'import** (#103) : `RecursionError` n'est pas rattrapée. La
  même issue borne la taille de l'URL citée dans les messages.
- **Écarter une seule release invalide** au lieu du fichier : #61.
- **Lire le dossier d'un dépôt non suivi** à l'import : étape 3 du plan ETL (#99). Aujourd'hui, le
  lecteur en est capable, mais l'import saute encore un dossier qu'il ne connaît pas.
- **S5** : `RepositoryName` (`items.py`) garde sa propre règle, plus large.
