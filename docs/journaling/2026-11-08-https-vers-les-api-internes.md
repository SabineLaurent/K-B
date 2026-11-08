# `https` vers les API internes, `http` vers la machine ou un service du compose

- Date : 2026-11-08
- Branche : `fix/internal-api-https`
- Issue : #473
- Fichiers : `src/k_b/core/outbound.py`, `src/k_b/core/config.py`, `src/k_b/core/api_settings.py`, les
  trois lecteurs (`ai_api/connectors/data_api_settings.py`, `post/ai_api_client.py`,
  `commands/smoke_test_command.py`), leurs tests, `.env.example`, `README.md`, `docs/fiches-veille.md`,
  le journal ADR
- Série : suite de [la relecture d'API8 et d'API10](2026-11-08-relire-api8-et-api10-apres-la-mise-en-ligne.md)
  (#454), qui avait écrit la limite.

## Le pourquoi

La relecture #454 l'a montré : en ligne, l'API IA appelle l'API de données en `https`, mais uniquement
parce que le Bicep pose cette URL. Le code acceptait `http` vers n'importe quel hôte. Une URL `http`
posée par erreur aurait fait partir une clé d'API en clair, sans aucun refus au démarrage. Tu as
accepté ce risque pour quelques heures, puis demandé qu'il soit corrigé tout de suite. Ta règle OWASP
du 05/11 s'applique : toutes les URL d'API interne que K-B lit suivent la même règle.

## Le comment

### Une règle, à un seul endroit

```python
    parts = urlsplit(url)
    if parts.scheme == "https" or parts.hostname in LOCAL_HOSTS:
        return None
    if parts.hostname in COMPOSE_HOSTS and is_sandbox(environ):
        return None
    return f"{variable}: {INTERNAL_API_HTTP_REFUSAL}"
```
(`src/k_b/core/outbound.py`, `find_internal_api_url_refusal`)

La règle se lit dans l'ordre :
- `https` passe toujours ;
- `http` passe vers la machine (`127.0.0.1`, `localhost`) ;
- `http` passe aussi vers un service du compose (`api-donnees`, `api-ia`), mais seulement en
  `sandbox` ;
- tout le reste est refusé.

Avant ces trois tests, `find_url_refusal` refuse déjà un schéma autre que `http` et `https`, un hôte
qui n'est pas un nom en minuscules, des informations d'utilisateur, une requête ou un fragment.

### Une liste fermée de noms, pas une forme de nom

```python
LOCAL_HOSTS = ("127.0.0.1", "localhost")
DATA_API_ALLOWED_HOSTS = LOCAL_HOSTS
# The services of a compose network (#419), reached in http in the sandbox only.
COMPOSE_HOSTS = ("api-donnees", "api-ia")
```
(`src/k_b/core/config.py`)

Ton premier choix, C, acceptait `http` vers tout hôte en `sandbox`. Restreindre aux noms sans point ne
suffisait pas : `http://134744072` est une IPv4 écrite en un seul nombre, sans point. Seule une liste
fermée de noms ferme la porte. C'est C', ton choix.

### Les trois lecteurs l'appellent

```python
    refusal = find_internal_api_url_refusal(
        DATA_API_URL_VARIABLE, base_url, environ
    ) or find_api_key_refusal(api_key)
```
(`src/k_b/ai_api/connectors/data_api_settings.py`)

Même appel dans `post/ai_api_client.py` (`KB_AI_API_URL`, pour `kb digest` et `kb trend-report`) et
dans `commands/smoke_test_command.py` (les deux URL, pour `kb smoke-test` et `kb digest-watch`). Un
refus arrête la commande avant toute requête, avec le code 2. Le message nomme la variable, jamais
sa valeur.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| C' : la machine partout, `api-donnees` et `api-ia` en `sandbox` | ta décision du 08/11 : le compose de #419 garde son `http`, et aucun autre hôte ne reçoit la clé en clair | C, `http` vers tout hôte en `sandbox` : un nom public y recevait la clé en clair (revue de code, verdict de sécurité) ; « sans point » : contourné par `http://134744072` |
| `KB_DEPLOYMENT_ENVIRONMENT` garde la porte du compose | les API en ligne sont en `production`, les jobs n'ont pas la variable : tous sont tenus au `https` | D, les quatre noms dans tout environnement : il accepterait `http://api-ia` en production, et la résolution d'un nom sans point dans Container Apps n'est pas vérifiée |
| Une fonction à part de `find_url_refusal` | `find_url_refusal` sert aussi la collecte et le modèle, qui ne sont pas des API internes | la règle dans `find_url_refusal` : elle toucherait des URL qu'elle ne concerne pas |
| Le message ne nomme pas la variable qui débloque | ne pas dire comment contourner la règle | « or with KB_DEPLOYMENT_ENVIRONMENT=sandbox » (premier tri) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Rouge avant le code de C' : 16 échecs, dont un nom public, `http://134744072` et `http://api-ai`, en `sandbox` | les tests visent la règle, pas le code |
| `test_an_internal_api_url_in_http_elsewhere_is_refused` (10 cas) et `…_is_accepted` (7 cas) | la règle, cas par cas |
| `test_serve_ai_exits_2_and_names_the_variable_refused[data-api-in-http-outside-the-machine]`, et les tests de démarrage refusé de `kb digest`, `kb trend-report` et `kb smoke-test` | chaque URL du périmètre fait refuser le démarrage (code 2) |
| `test_smoke_test_reaches_the_compose_services_in_http_in_the_sandbox` | le compose garde son `http` en `sandbox` |
| Suite rejouée avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox` et deux URL `http` exportées : tout passe | les tests ne dépendent plus du terminal (`tests/conftest.py`) |
| `uv run pytest` : 4 061 tests, couverture 98,42 % ; ruff et mypy verts | rien d'autre ne casse |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une liste de noms et pas une forme de nom ?** Une IPv4 peut s'écrire en un seul nombre
   (`http://134744072`) : « sans point » laisse passer une adresse publique. La liste fermée, non.
2. **Que se passe-t-il en ligne si quelqu'un pose une URL en `http` ?** L'API ou le job refuse de
   démarrer (code 2), avec un message qui nomme la variable. La clé ne part jamais.
3. **Pourquoi `sandbox` ne suffit-il pas à tout ouvrir ?** Sur le Mac, `.env.example` conseille
   `sandbox` pour développer. Une faute d'URL y aurait envoyé la clé en clair. Désormais, `sandbox`
   n'ouvre que les deux noms du compose.
4. **Où ajouter un autre nom de service ?** Dans `COMPOSE_HOSTS` (`core/config.py`), comme le dit
   `.env.example`.

## Zones non vérifiées

- Les noms `api-donnees` et `api-ia` ne correspondent encore à aucun compose : #419 les posera.
- Qu'`urlsplit` et le client HTTP (httpx2) lisent le même hôte pour toute URL acceptée : vérifié par
  la revue de sécurité, pas par un test du dépôt. Elle a essayé 579 URL acceptées, avec les quatre
  hôtes et des caractères Unicode insérés à chaque position, et aucune n'a fait se connecter httpx2
  2.13.1 en `http` ailleurs. Une espace en tête d'URL est retirée par `urlsplit`, alors que httpx2
  lit l'URL sans hôte : la requête échoue et rien ne part.

## Ce qui reste

- Le compose de #419, qui posera `KB_DEPLOYMENT_ENVIRONMENT=sandbox` et ces deux noms de service.
- #470, ensuite.
