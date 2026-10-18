# Rassembler les routeurs de l'API de données dans `api_router.py`

- **Date** : 2026-10-18
- **Branche** : `refactor/data-api-router`
- **Issue** : #246
- **Fichiers principaux** : `src/k_b/data_api/api_router.py` (nouveau), `src/k_b/data_api/app.py`,
  `tests/test_module_dependencies.py`, `docs/specs-api.md`
- **Série** : suit [Ranger la ligne de commande](2026-10-18-ranger-la-ligne-de-commande.md) (#247) et
  [Ranger l'API IA par rôle](2026-10-18-ranger-l-api-ia-par-role.md) (#242).

## 1. Le pourquoi

L'API de données a un dossier `routers/` : un fichier par entité (`item_router.py`, `trend_router.py`).
Jusqu'ici, `app.py` importait chaque routeur et l'incluait un par un. Chaque routeur ajouté aurait donc
touché `app.py`, le fichier qui monte l'application (clé, middlewares, erreurs).

Sabine a décidé le 18/10 que le dossier `routers/` a son fichier qui le rassemble, comme l'`index.js` de
l'organisation apprise en DWWM. Ce fichier ne peut pas être `routers/__init__.py` : dans K-B, un
`__init__.py` reste vide (`code.md`, « Séparation des responsabilités » ; ADR du 2026-10-18, #242). Le
rassembleur est donc un module à part, à côté de l'app : `api_router.py`.

C'est un **déplacement seul** : aucune route, aucun schéma, aucune réponse ne change.

## 2. Le comment

### 2.1 Un routeur qui inclut les routeurs

`src/k_b/data_api/api_router.py:8-10` :

```python
api_router = APIRouter()
api_router.include_router(item_router.router)
api_router.include_router(trend_router.router)
```

Un `APIRouter` peut inclure d'autres `APIRouter`, comme une application le fait (doc FastAPI,
« Bigger Applications », section « Include an `APIRouter` in another »). `api_router` n'a pas de route à
lui : il ne fait que porter celles des deux routeurs. L'ordre est celui que suivait `app.py` (articles
d'abord, tendances ensuite) : c'est aussi l'ordre des chemins dans l'OpenAPI.

Aucun argument à l'inclusion (ni `prefix`, ni `tags`, ni `dependencies`) : les deux routeurs n'en ont pas,
et le skill `fastapi` du dépôt demande de mettre ces réglages sur le routeur lui-même, pas sur
`include_router()`.

### 2.2 L'app ne branche plus qu'un routeur

`src/k_b/data_api/app.py:13` et `:51` :

```python
from k_b.data_api.api_router import api_router
...
    app.include_router(api_router)
```

L'appel reste à la même place, après les middlewares et avant `/health`. La clé, elle, reste posée sur
l'app (`app.py:36`, `dependencies=[Depends(check_api_key)]`) : FastAPI l'applique à toute route incluse,
à quelque profondeur qu'elle le soit. Un routeur ajouté plus tard ne peut donc pas sortir de la clé.

### 2.3 La barre oblique finale : pourquoi rien ne change

L'app est créée avec `redirect_slashes=False` : `/items/` répond 404, pas une redirection vers `/items`.
Un `APIRouter()` garde, lui, `redirect_slashes=True` par défaut. Ce n'était pas nouveau :
`item_router.router` l'avait déjà. Mais il fallait vérifier qu'un routeur de plus entre les deux ne
réveille pas la redirection.

Lu dans la source de FastAPI 0.143.1 (`fastapi/routing.py`) :
- un routeur inclus ne répond qu'aux chemins de ses propres routes (`_IncludedRouter.matches`, l. 1803,
  puis `APIRouter.matches`, l. 2875) ;
- un chemin inconnu revient donc au routeur de l'application, le seul qui lise `redirect_slashes`
  (`APIRouter.app`, l. 2805). Or celui-ci vaut `False`.

Le test `test_a_final_slash_gives_404_not_a_redirection` (`tests/data_api/test_api_errors.py:24`) le
prouve à chaque exécution.

### 2.4 Un test de garde tient la règle

`tests/test_module_dependencies.py:302-313` :

```python
def test_the_app_of_the_data_api_imports_no_router():
    path = PACKAGE_DIR / "data_api" / "app.py"
    imported = list_imported_modules(path, find_package(path), depth=3)

    assert {name for name in imported if is_within(name, {"data_api.routers"})} == set()
```

Le test lit le code d'`app.py` sans l'exécuter, par l'arbre syntaxique (`ast`), et liste ce qu'il importe
de K-B, coupé à trois niveaux (`data_api.routers.item_router`). Si `app.py` importait de nouveau un
routeur, le test échouerait. C'était le test rouge de la PR : avant le déplacement, il renvoyait
`data_api.routers.item_router` et `data_api.routers.trend_router`.

Le second test, `test_the_package_of_the_routers_is_empty` (l. 309), vérifie que
`routers/__init__.py` est vide, au caractère près. D'abord écrit « n'importe rien » (aucune instruction
`import`), il a été durci à la revue de code : un fichier qui relierait les routeurs sans import
(`__all__`, par exemple) serait passé ; `code.md` dit « reste vide », et le test dit désormais la même
chose.

Pourquoi un test et pas seulement une commande de recherche dans le critère de fin de l'issue :
l'ADR du 2026-10-18 (« Ligne de commande : une porte mince ») l'a tranché pour #247. Une commande de
recherche vérifie la PR une fois ; un test vérifie toutes celles qui suivront.

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où rassembler | Un module à part, `api_router.py`, à la racine de l'API, à côté d'`app.py` : « le routeur principal de l'API ; dans `routers/`, ce sont les routeurs secondaires importés par le principal » (Sabine, 18/10) | `routers/__init__.py` : interdit par `code.md` et l'ADR de #242. `routers/api_router.py` : il mêlerait le principal aux routeurs d'entité, et la garde ne serait plus « `app.py` n'importe rien de `routers/` » |
| Nom | `api_router.py`, objet `api_router` : le nom du full-stack-fastapi-template (décision de Sabine) | `routers_index.py` (proposition de la session), `index_route.py` (c'est un routeur, pas une route), `router.py` (à une lettre de `routers/`), `routes.py` (se confond avec `routers/`), `routers.py` (impossible à côté du paquet `routers/`) |
| Arguments d'inclusion | Aucun : la clé reste sur l'app | Une clé posée à l'inclusion : un routeur ajouté sans elle échapperait à la clé |
| Garde de la règle | Deux tests, une chose chacun (décision de Sabine, puis tri de time-knight) ; `__init__.py` vide au caractère près (tri de la revue de code) | Un seul test à deux assertions ; un `grep` du critère de fin seul (ADR de #247) ; « n'importe rien » seul, moins strict que `code.md` |
| Spec | Une demi-phrase dans `docs/specs-api.md:66`, sans changement de version | Changer la version : rien n'est visible par un client |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run kb openapi`, puis `git diff 4ebff3a -- docs/api/openapi-donnees.json` → vide | Les chemins, leur ordre et les schémas de l'OpenAPI n'ont pas bougé |
| `test_a_final_slash_gives_404_not_a_redirection` vert | Le routeur de plus ne réveille pas la redirection de `/items/` |
| `tests/data_api/test_api_keys.py` verts | Toute route de données demande toujours la clé |
| `test_the_app_of_the_data_api_imports_no_router` rouge avant, vert après | Le test voit bien l'import d'un routeur dans `app.py` |
| `uv run pytest -q` → 1759 passed (1757 sur `main` ed9e1df, plus les deux tests de garde) | Aucun test existant ne casse |
| `diff -r` des aides de `kb`, `main` contre la branche → identiques | La ligne de commande ne change pas |
| Essai du relecteur du plan : 30 requêtes sur l'app de `main` et sur l'app réécrite → réponses, lignes de journal et OpenAPI identiques | Le comportement est le même, au-delà des tests existants |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas tout mettre dans `routers/__init__.py`, comme un `index.js` ?** Dans K-B, un
   `__init__.py` reste vide, sauf raison écrite (`code.md`, « Séparation des responsabilités ») ; pour
   `ai_api`, l'ADR de #242 le tient par un test. Le rassembleur est un module nommé, qu'on trouve par son
   nom dans le dossier (`api_router.py:1-2`).
2. **Un routeur ajouté demain échappe-t-il à la clé ?** Non : la clé est une dépendance de l'app
   (`app.py:36`), pas de chaque routeur. FastAPI l'applique à toute route incluse, même à travers
   `api_router`. Le relecteur l'a observé : `/items` sans clé répond toujours 401.
3. **Qu'est-ce qui change pour un client ?** Rien. L'OpenAPI versionné est identique, octet pour octet. Le
   seul écart observé est interne : `app.routes` compte 4 entrées au lieu de 5 (les deux routeurs n'en font
   plus qu'une), et aucun code ne lit ce nombre.
4. **Que vérifie exactement le test de garde ?** Les imports d'`app.py`, lus dans son arbre syntaxique,
   sans l'exécuter. Il ne voit pas un import dynamique (`importlib`) : K-B n'en a aucun, et la docstring de
   `parse_imported_modules` le dit.
5. **Comment ajouter un troisième routeur ?** Créer `routers/<entité>_router.py` avec son
   `router = APIRouter()`, puis une ligne `api_router.include_router(...)` dans `api_router.py`. `app.py`
   ne change pas.

## 6. Zones non vérifiées

- Le fonctionnement interne des routeurs imbriqués est lu dans la source de FastAPI 0.143.1, la version
  du `uv.lock`. Il a changé en 0.137.0 (les routes incluses ne sont plus copiées). Avec une version plus
  ancienne, les routes seraient copiées ; le relecteur l'a fait tourner en 0.122.0, mais la suite de tests
  de K-B n'y passe pas (`iter_route_contexts`, utilisé par un test, date de 0.137.2).
- `kb serve` n'a pas été lancé pour de vrai sur cette branche : la preuve repose sur les tests et l'OpenAPI.

## 7. Ce qui reste

- L'API IA suivra la même règle (un module à côté de l'app rassemble ses routeurs) à #156. Rien n'est fait
  dans `ai_api` ici.
- Signalé, sans porteur : `pyproject.toml:12` déclare `fastapi>=0.122`, alors que les tests demandent
  0.137.2 ou plus (`iter_route_contexts`, `tests/data_api/test_api_keys.py:6`).
