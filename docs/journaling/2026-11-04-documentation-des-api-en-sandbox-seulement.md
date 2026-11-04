# Servir la documentation des API en sandbox seulement

- **Date** : 2026-11-04
- **Branche** : `feat/api-docs-in-sandbox-only`
- **Issue** : #393
- **Fichiers principaux** : `src/k_b/core/api_settings.py`, `src/k_b/data_api/app.py`,
  `src/k_b/ai_api/app.py`, `src/k_b/commands/serve_data_command.py`,
  `src/k_b/commands/serve_ai_command.py`

## Le pourquoi

En ligne, `/docs` et `/openapi.json` décrivent les routes de l'API à qui les demande, sans clé. Ils ne
contiennent aucune donnée, mais personne n'en a besoin en production. Tu as fixé la règle : `sandbox`
pour le développement ; `production`, une autre valeur ou rien : on n'affiche rien.

## Le comment

### 1. Une seule valeur ouvre

`core/api_settings.py:41-46` :

```python
def read_openapi_url(environ: Mapping[str, str]) -> str | None:
    if environ.get(DEPLOYMENT_ENVIRONMENT_VARIABLE) == "sandbox":
        return OPENAPI_PATH
    return None
```

Tout ce qui n'est pas exactement `sandbox` donne `None`. Ainsi, une variable oubliée sur Azure ou
mal écrite (`prod`, `Sandbox`) ne montre rien : c'est la règle « échouer fermé » de `code.md`. La lecture
est dans `core/`, car l'API de données n'a pas le droit d'importer `ai_api`. Pour la même raison, le
nom de la variable et ses valeurs ont quitté `ai_api/connectors/metrics_export.py`.

### 2. Couper la route, pas le contrat

`data_api/app.py:44`, et de même `ai_api/app.py:52` :

```python
openapi_url=openapi_url,
```

Avec `openapi_url=None`, FastAPI n'ajoute ni `/openapi.json` ni `/docs`, et ces chemins répondent 404.
`app.openapi()`, lui, calcule toujours le schéma : `kb openapi` continue donc d'écrire les contrats
versionnés dans `docs/api/`. Le paramètre de `create_app` vaut `None` par défaut : une application
créée sans le préciser ne montre rien non plus.

### 3. La commande décide

`commands/serve_data_command.py:35`, et de même `serve_ai_command.py:103` :

```python
openapi_url=read_openapi_url(environ),
```

L'environnement est lu par la commande et passé à l'application (règle 2 de `poc.md`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Seul `sandbox` ouvre | ta décision ; un oubli ne montre rien | couper sur `production` seul (mon premier plan) : un oubli laissait la doc servie |
| Pas de refus au démarrage sur une valeur inconnue | elle ne montre rien de toute façon | refuser : du code sans gain |
| Les deux API | ta décision ; elles servent `/docs` de la même façon | l'API de données seule |
| Versions 0.6.0 et 0.8.0 | `specs-api.md` : un changement visible par un client change la version | garder les versions : la règle du dépôt ne le permet pas |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_documentation_is_served_in_the_sandbox_only`, sur les deux API, 6 valeurs | 200 en `sandbox` ; 404 avec `production`, `prod`, `Sandbox`, vide ou absente ; `/health` répond ; `app.openapi()` produit le contrat dans tous les cas |
| `test_the_versioned_openapi_is_the_one_the_app_produces` | `kb openapi` écrit bien le contrat depuis une application sans route |
| `git diff docs/api` : seule `info.version` change | le contrat lui-même n'a pas bougé |
| `uv run pytest` : 3 339 verts ; `ruff`, `mypy --strict` verts | les contrôles du dépôt |
| Test rouge avant le code : 10 cas en échec, les 2 `sandbox` déjà verts | le test visait bien le changement |
| `/code-review low` : un constat, une phrase de `specs-api.md`, corrigée | pas de seconde revue : la correction ne touche qu'une phrase |

## Ce que tu dois pouvoir défendre

1. **Est-ce une mesure de sécurité ?** Non : « ce qui est caché n'est pas pour autant protégé ». La
   clé protège les données. Couper la doc réduit seulement ce qu'on montre à un inconnu ; l'entrée
   interne de l'API de données en ligne reste à faire.
2. **Le contrat de l'API est-il perdu en production ?** Non : il reste versionné dans `docs/api/`, et la
   CI le compare à ce que produit l'application.
3. **Que se passe-t-il si on oublie la variable sur Azure ?** La doc ne s'affiche pas. L'oubli est du
   côté sûr ; seule la valeur exacte `sandbox` l'ouvre (`core/api_settings.py:44`).
4. **Pourquoi `/health` reste-t-il ouvert ?** C'est la sonde d'un conteneur : il ne dit que `ok`.

## Zones non vérifiées

- `openapi_url=None` n'a été essayé qu'avec `TestClient`, pas sur un serveur réel lancé par `uvicorn`.
- L'absence de `/docs` avec `openapi_url=None` vient du guide de FastAPI (« Conditional OpenAPI »,
  lu par Context7 le 2026-11-04) et elle est prouvée par les tests ; le code de FastAPI n'a pas été relu.
- Je ne sais pas si ton `.env` local contient déjà `KB_DEPLOYMENT_ENVIRONMENT=sandbox` : sans cette
  ligne, `/docs` répond 404 chez toi.

## Ce qui reste

- Poser `KB_DEPLOYMENT_ENVIRONMENT=production` sur Azure au déploiement, surtout pour les mesures ; la
  doc, elle, reste coupée même sans la variable.
- L'entrée interne de l'API de données en ligne (architecture cible, non codée).
