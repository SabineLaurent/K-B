# Écrire la fiche de l'API IA, et le bac à sable dans la fiche des tests

- Date : 2026-11-08
- Branche : `docs/ai-api-sheet`
- Issue : #507 ; l'ajout du bac à sable vient du plan de #478 (ajout 2), après la fusion de #517
- Fichiers principaux : `documentation/api_ia_pour_docu.md` (neuf), `documentation/tests_pour_docu.md` (une section)
- Série : [2026-11-08-ecrire-la-fiche-des-tests.md](2026-11-08-ecrire-la-fiche-des-tests.md) et
  [2026-11-08-ecrire-la-fiche-de-la-livraison-continue.md](2026-11-08-ecrire-la-fiche-de-la-livraison-continue.md) ;
  l'architecture elle-même est expliquée dans [2026-11-08-architecture-de-l-api-ia.md](2026-11-08-architecture-de-l-api-ia.md).

La note couvre les trois commits : 66db1ca (la fiche), 631c989 (le bac à sable, commit à part), a4c2092 (les
22 corrections de la relecture).

## Le pourquoi

Le référentiel demande une documentation de l'API (C9) et des étapes d'authentification et de leur renouvellement
(C10). Les faits existaient, mais dispersés : `docs/architecture-api-ia.md`, `docs/fiches-veille.md`, le README et
l'OpenAPI. Décision de Sabine du 08/11 : chaque documentation demandée devient une fiche neuve de `documentation/`,
écrite d'après le code, sans toucher à `docs/`. Qui appelle l'API IA trouve dans un seul fichier son architecture,
ses cinq chemins, ses règles d'accès, et ce qu'il faut faire d'une clé, qui n'expire pas.

## Le comment

### L'en-tête recopie le référentiel

`documentation/api_ia_pour_docu.md:3-5` :

```markdown
« Rédaction et/ou génération de la documentation de l'API. » — C9

« Les éventuelles étapes d'authentification et de renouvellement de l'authentification (expiration des jetons par exemple) sont intégrées correctement en suivant la documentation de l'API. » — C10
```

Les deux lignes sont celles du critère de fin de #507, mot pour mot. Le reste de la fiche répond à ces deux
intitulés : l'architecture et les chemins pour C9, l'authentification, l'absence d'expiration et le changement
d'une clé pour C10.

### Le contrat reste l'OpenAPI ; la fiche y renvoie

`tests/ai_api/test_ai_api_openapi.py:31-33` :

```python
def test_the_versioned_openapi_is_the_one_the_app_produces():
    # Through JSON, as kb openapi writes it: a tuple of the schema becomes a list.
    assert read_versioned_openapi() == json.loads(json.dumps(describe_ai_api()))
```

`docs/api/openapi-ia.json` est généré par `uv run kb openapi` et ce test le tient égal à l'app : il ne peut pas
dériver du code sans que la CI échoue. La fiche nomme donc les schémas (`DigestRequestSchema`, `DigestsSchema`…)
sans recopier leurs champs. Elle ne dit en texte que ce que l'OpenAPI ne montre pas : les deux règles du corps de
`POST /trend-reports` tenues par un validateur Pydantic (l'ordre des deux jours, 15 fenêtres au plus), qui
n'apparaissent pas dans le schéma JSON.

### Trois chemins hors du contrat, décrits d'après le code

`src/k_b/ai_api/app.py:98-100` :

```python
    # add_route, as FastAPI adds /docs: a route of Starlette, which the key of the app does not
    # reach (fastapi/applications.py, 0.143).
    app.add_route(HEALTH_PATH, answer_health, methods=["GET"], include_in_schema=False)
```

L'OpenAPI ne décrit que `/digests` et `/trend-reports`. `GET /health` est ajouté hors du schéma, `/docs` et
`/openapi.json` ne sont servis qu'en `sandbox` (`core/api_settings.py:41-51`). Sabine l'a précisé à la validation
du plan : ces trois chemins sont dits hors du contrat, et décrits d'après le code.

### Une clé qui n'expire pas, et comment la changer

`src/k_b/core/api_access.py:17-21` :

```python
BEARER_SCHEME_DESCRIPTION = (
    "One key per client, sent as `Authorization: Bearer <key>`. A missing or unknown key gets"
    " the same 401 `invalid_api_key`. No login route and no token lifetime: a key is revoked by"
    " removing it and restarting the API."
)
```

Cette phrase est la description du schéma `HTTPBearer` dans l'OpenAPI. C'est la réponse de la fiche à C10 : il
n'y a pas de jeton à renouveler, donc pas d'étape de renouvellement chez le client. La fiche décrit à la place ce
que le code fait : la clé est lue au démarrage (`commands/serve_ai_command.py:39-41`), se change dans sa variable
puis par un redémarrage, et, en ligne, par une nouvelle version du secret Key Vault puis un redémarrage de la
révision. Elle dit aussi comment les deux clients appliquent ces règles : la même variable que le serveur, la clé
dans l'en-tête, un 401 qui nomme la variable et jamais la clé.

### Le bac à sable dans la fiche des tests

`Makefile:64-66` :

```make
sandbox-alerts:
	uv run --env-file $(E2E_ENV_FILE) pytest -m e2e tests/e2e/test_sandbox_alerts.py -rs \
		--html=reports/$@.html --self-contained-html
```

#517 a ajouté quatre tests de bout en bout qui envoient des mesures `sandbox` à Grafana Cloud. La fiche des tests
dit maintenant comment les lancer, ce que chacun vérifie, et ce qu'ils ne prouvent pas : le déclenchement d'une
alerte se lit dans Grafana, pas dans le test. Elle note aussi que `pytest -m e2e` les lance avec les autres (15 tests
au commit `1d2f554`).

## Choix faits et options écartées

- **Renvoyer à l'OpenAPI plutôt que recopier les schémas.** Retenu : le critère de #507 le demande, et un test tient
  l'OpenAPI égal au code. Écarté : une table des champs, qui dériverait du code sans qu'aucun test la voie.
- **Citer chaque fait par `fichier:ligne` au commit `1d2f554`.** Retenu : le critère demande que chaque fait se
  vérifie dans le code. Écarté : reprendre les renvois de `docs/architecture-api-ia.md`, écrits au commit `56d013b` :
  plusieurs lignes ont bougé depuis (par exemple les constantes de `core/config.py`).
- **Un schéma mermaid, décrit par une liste.** Retenu : il se lit sur GitHub, et la liste qui le suit le rend lisible
  sans l'image (règle de documentation de `conformite.md`, RGAA). Écarté : un schéma sans texte.
- **Les mesures renvoyées à `monitoring_pour_docu.md`**, fusionnée par #517 pendant le travail. Écarté : les
  recopier.
- **Le bac à sable dans un commit à part.** Imposé par la mission : l'ajout vient de #478, pas de #507.
- **Les 22 constats de la relecture tous corrigés.** Tranché par time-knight, délégation de Sabine du 15/10 : des
  faits dits trop largement ou cités à la mauvaise ligne, dont un faux (les quatre tests du bac à sable ne visent pas
  chacun une alerte : trois le font).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/ai_api/test_ai_api_openapi.py tests/architecture/test_apis.py` → 64 passed | l'OpenAPI versionné est celui du code ; les couches et les imports décrits tiennent |
| `uv run pytest tests/ai_api/test_digest_router.py -k "key or bound or limit or runs or body or client or other_route or method or health"` → 39 passed | clé, client, corps, débit, concurrence, méthodes et `/health` se comportent comme la fiche le dit |
| `uv run pytest tests/ai_api/test_serve_ai.py -k documentation` → 1 passed | `/docs` et `/openapi.json` ne sont servis qu'en `sandbox` |
| `grep -rnE "raw_store\|writers\|…" src/k_b/ai_api \| wc -l` → 0 | le paquet `ai_api` n'écrit aucun fichier (règle 7) |
| `uv run pytest -m e2e --collect-only` → 15 tests | `-m e2e` lance aussi les quatre tests du bac à sable |
| contrôles de la mission : `Cc`/`Cf` → aucun ; liens → tous existent ; ponctuation hors blocs → 0 ; `git diff --stat --diff-filter=M origin/main -- docs/ README.md` → vide | les règles des fiches sont tenues, et aucun fichier existant de `docs/` n'est modifié |
| relecture par un sous-agent neuf, puis seconde relecture du delta | chaque `fichier:ligne` relu contre le code |

## Ce que tu dois pouvoir défendre

- **Pourquoi une clé fixe, et pas un jeton qui expire ?** Décision écrite (journal ADR, « POC du 25/10 »,
  décision 7, précisée le 2026-10-20) : la clé reste fixe et sa rotation est documentée. La clé identifie un
  programme, pas une personne, et il n'y a pas de route de connexion à protéger (`core/api_access.py:17-21`).
- **Une clé fuit : que fais-tu ?** Une nouvelle clé dans la variable du client, puis un redémarrage de
  `kb serve-ai` ; l'ancienne est refusée dès le redémarrage. En ligne : une nouvelle version du secret, puis un
  redémarrage de la révision (`infra/README.md`, « 4. Poser les secrets »).
- **Un client vole la route d'un autre ?** Chaque route s'ouvre à un seul client : une clé valide d'un autre client
  reçoit 403 `client_not_allowed` (`core/config.py:300-305`, `core/api_access.py:44-49`).
- **Comment sais-tu que la documentation de l'API est à jour ?** L'OpenAPI est généré et tenu égal au code par un
  test de la CI (`tests/ai_api/test_ai_api_openapi.py:31-33`) ; la fiche cite chaque fait au commit `1d2f554`.
- **Pourquoi `/docs` n'est-il pas servi en production ?** Il n'est servi qu'avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox` ;
  en ligne, la variable vaut `production` (`core/api_settings.py:41-51`, `infra/main.bicep:216`).

## Zones non vérifiées

- Les 30 minutes que met Container Apps à lire une nouvelle version d'un secret viennent d'`infra/README.md` et d'un
  commentaire du Bicep, pas de la documentation d'Azure.
- Que FastAPI ne sert `/docs` qu'avec un chemin d'OpenAPI est lu dans fastapi 0.143.1 (`applications.py:1158`) ; une
  autre version peut changer cette ligne.
- La comparaison des clés en temps constant n'est mesurée par aucun test : la fiche le dit.
- Les tests du bac à sable et les autres tests de bout en bout n'ont pas été lancés (ils envoient à Grafana Cloud et
  demandent des secrets).

## Ce qui reste

- La fiche de l'installation et de l'environnement de développement : #502, la PR suivante.
- Les jetons qui expirent ne sont pas codés (#160, hors du squelette) : la fiche décrit la clé fixe, pas un futur
  jeton.
- Les essais de clé ne sont pas limités, écart voulu du 2026-11-05 : dit dans « Limites » de la fiche.
- En ligne, aucun job n'appelle encore `POST /digests` ni `POST /trend-reports` : le job `caj-kb-digest-watch` n'est
  pas déclaré dans `infra/`.
