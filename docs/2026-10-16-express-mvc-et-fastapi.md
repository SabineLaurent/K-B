# D'Express MVC à FastAPI : correspondance dans l'API de données de K-B

Où trouver, dans `src/k_b/data_api/`, ce qu'une application Node.js et Express organisée en MVC
range dans ses dossiers `routes/`, `controllers/`, `models/`, `services/` et ses middlewares.
L'organisation du paquet est décidée au journal ADR (PR de #182, paquet `src/k_b/data_api/`).

## Correspondance

| Express (MVC clean code) | FastAPI, dans K-B | Ce qui change |
|---|---|---|
| `routes/trend.routes.js` : `router.get('/trends', trendController.list)` | `@router.get("/trends")` dans `routers/trend_router.py` | Le décorateur associe l'URL à la fonction qu'il précède : la route et le contrôleur sont dans le même fichier. |
| `controllers/trend.controller.js` : `(req, res) => {...}` | La fonction `list_trends` de `routers/trend_router.py` | Elle ne reçoit ni `req` ni `res`. Elle reçoit des paramètres typés et renvoie un objet, que FastAPI convertit en JSON. |
| Middleware de validation (Joi, express-validator) | Les types de la signature : `Annotated[WindowEnd \| None, Query()]` | La validation est déclarée dans la signature. Si elle échoue, FastAPI répond 422 sans entrer dans la fonction. |
| `res.status(404).json(...)` | `raise ApiError(404, "trend_window_not_found")` | Une erreur se lève. Le gestionnaire d'erreurs, écrit une fois, construit la réponse. |
| Middleware d'erreurs `(err, req, res, next)` | `errors.py` (`ERROR_HANDLERS`, passé à `FastAPI(exception_handlers=...)`) | Même rôle. |
| `app.use(auth)` | `app.py` : `FastAPI(dependencies=[Depends(check_api_key)])`, fonction de `dependencies.py` | Une dépendance posée sur l'application : aucune route de données ne peut s'en passer. |
| `req.db` posé par un middleware | `dependencies.py` : `Database`, déclaré dans la signature (`connection: Database`) | Injection de dépendances : la route déclare ce dont elle a besoin, FastAPI le lui fournit, une connexion par requête. |
| Middlewares transverses (journal, hôtes permis, erreur inattendue) | `app.py` : `app.middleware("http")(log_request)`, `respond_to_unexpected_error`, `TrustedHostMiddleware` | Les middlewares existent aussi en FastAPI, pour ce qui vaut pour toute requête. |
| `models/` (Mongoose, Sequelize) | `src/k_b/database/` (SQL, sans ORM ; lecture dans `reading.py`) | Hors du paquet de l'API, qui n'importe que `database`, `items` et `core` (`.claude/rules/conventions.md`, règle 5). |
| DTO ou vue de la réponse | `schemas/` (modèles Pydantic) | FastAPI en tire aussi la description des réponses dans l'OpenAPI (`docs/api/openapi-donnees.json`). |
| `services/` | Aucun module pour l'instant | Les routes lisent la base et mettent en forme le résultat : il n'y a pas de logique métier entre les deux. |
| `app.js` : `app.use('/api', router)` | `app.py` : `app.include_router(trend_router.router)` | Même rôle. |

## Trois différences qui déroutent

1. **La signature typée remplace plusieurs middlewares.** Express lit `req.query.window_end`, le
   valide et le convertit. En FastAPI, `window_end: WindowEnd | None` suffit : la lecture, la
   validation, la conversion, la réponse 422 et la documentation OpenAPI viennent de cette ligne.
2. **On renvoie une valeur, on n'écrit pas dans `res`.** La fonction de route se lit et se teste
   comme une fonction ordinaire.
3. **L'appel du contrôleur n'est écrit nulle part.** Le décorateur réunit la route et le
   contrôleur. Un dossier `controllers/` ne ferait que transmettre l'appel à
   `database/reading.py` : il a été écarté (journal ADR, PR de #182).

## Quand une couche de service aurait du sens

Quand une logique métier apparaît entre la lecture et la réponse : plusieurs lectures combinées,
un calcul, ou un même traitement partagé par l'API et une commande `kb`. Elle irait alors dans une
fonction métier sous la présentation. L'API de données ne pourrait toujours importer ni `etl` ni
`database/writers` (`.claude/rules/conventions.md`, règle 5).
