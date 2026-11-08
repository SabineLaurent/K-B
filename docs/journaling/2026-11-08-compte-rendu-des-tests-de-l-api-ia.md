# Le compte rendu interprété des tests de l'API IA

- **Date** : 2026-11-08
- **Branche** : `docs/ai-api-test-report`
- **Issue** : #280
- **Fichiers principaux** : `docs/2026-11-08-tests-api-ia.md` (nouveau), `README.md` (une ligne de renvoi)
- **Série** : fait suite à [L'architecture de l'API IA, en un document](2026-11-08-architecture-de-l-api-ia.md)
  (#279), qui montre ce que ces tests vérifient.

## Le pourquoi

L'API IA et la chaîne des fiches ont 1550 tests, dans 37 fichiers. Les lire un à un ne dit pas ce
qu'ils prouvent ensemble, ni ce qu'ils laissent hors de leur preuve. La certification lit C9.7 et C10.8 d'E3 comme
partiels sans un compte rendu interprété des tests. Le document sert aussi d'annexe au rapport E3 : chaque fait doit
être vrai au commit cité (`f91bb97`).

C'est une PR de documentation seule : aucun code ni test ne change.

## Le comment

### 1. Des nombres tirés d'une exécution réelle, au commit cité

Les nombres ne sont pas recopiés : ils viennent de `make test`, `make test-ai-api` et d'un `uv run pytest` sur la
partie `kb`, lancés sur `main` (`docs/2026-11-08-tests-api-ia.md:12-21`). `main` a bougé pendant la session
(fusion de #483, à `f91bb97`) : la branche a été rebasée, et tous les tests ont été relancés avant d'écrire, car le
total était passé de 4035 à 4061.

### 2. Chaque fichier dans un seul groupe

```
Chaque fichier est compté dans un seul groupe ; la somme redonne 1550.
```

(`docs/2026-11-08-tests-api-ia.md:51`). Le critère nomme cinq groupes (contrôles, routes, clé, modèle de
remplacement, bout en bout). Deux familles de fichiers n'y entrent pas : la lecture de la veille et de GitHub, et les
mesures et traces. Elles ont donc leur groupe, sinon le total ne se vérifierait pas. La clé, elle, n'a pas de
fichier : ses tests sont dans les routes et dans les clients. Elle est une table de tests nommés, non recomptés
(`docs/2026-11-08-tests-api-ia.md:64-65`, `:110-138`).

### 3. « Ce qu'il prouve » et « ce qu'il ne prouve pas », par groupe

Chaque groupe a les deux paragraphes. Le second est ce qui intéresse un relecteur : le `TestClient` appelle
l'application sans socket ; le *replay* remplace le transport du client du modèle, pas son code
(`ai_api/connectors/llm_client.py:210`). Il ne dit donc rien de la qualité d'une vraie fiche.

### 4. Le bout en bout : ce qui est réel, ce qui est simulé

Le schéma Mermaid sépare les flèches réelles (HTTP sur `127.0.0.1`, entre des API construites par `kb serve-data`
et `kb serve-ai`) des flèches simulées (le *replay*, GitHub, l'identité managée et le stockage
d'échange de `kb smoke-test`) et de ce que le test règle (l'horloge, les sujets). Il est suivi du même contenu en texte
(`docs/2026-11-08-tests-api-ia.md:249-297`). Le test de #462 (PR #472) en est l'un des trois.

### 5. Les manques rassemblés, chacun avec ce qui le porte

La table finale (`docs/2026-11-08-tests-api-ia.md:299-310`) donne pour chaque manque l'issue ou le test qui le
porte : #210 pour la qualité des fiches d'un vrai modèle, #370 pour celle des comptes rendus de tendances, le test `e2e`
d'export pour Grafana, aucun test pour les traces, `kb smoke-test` pour la vérification en ligne, #436 pour la lecture
bornée.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nom du fichier | daté, `docs/2026-11-08-tests-api-ia.md` : c'est le compte rendu d'une exécution, comme `docs/2026-10-26-collecte-reelle.md` | sans date, à côté de `architecture-api-ia.md` : un compte rendu vaut pour son commit, pas pour `main` en général |
| Groupes | les cinq du critère, plus deux : chaque fichier compté une fois | les seuls cinq groupes : deux familles de fichiers seraient restées sans groupe |
| Périmètre | `tests/ai_api`, le code commun aux deux API, `tests/post` sans `test_top_sheets.py`, les commandes de la chaîne | `tests/data_api` (son propre groupe) ; `test_top_sheets.py` (`kb write-tops` n'appelle pas l'API IA) ; les fichiers qui ne touchent l'API IA qu'en partie, ou par du code commun, nommés avec leur nombre dans « Hors du compte » (`docs/2026-11-08-tests-api-ia.md:28-47`) |
| #210 et #370 | dites comme des manques : ouvertes ; un seul essai de #210 consigné | écrire que les essais « couvrent » la qualité : faux tant qu'elles sont ouvertes |
| Relecture | par un sous-agent neuf, effort `xhigh`, au lieu de `/code-review` | consigne de la mission (doc seule) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `make test` → `4061 passed, 328 deselected` sur `f91bb97` | toute la suite passe au commit cité |
| `make test-ai-api` → `1087 passed`, puis `8 passed` | les nombres des cinq groupes de l'API IA et du code commun |
| `uv run pytest --co -q … --deselect tests/post/test_top_sheets.py` → `1550/1583 tests collected (33 deselected)` | la somme des groupes du tableau |
| `uv run pytest -m e2e --co -q` → 11 ; `-m postgresql` → 317 | les 328 écartés |
| `--cov=k_b.ai_api.dependencies` sur toute la suite → lignes `29-30, 34` non exécutées | `open_github_client` et `read_request_time` ne sont exécutées par aucun test |
| contrôle des caractères `Cc`/`Cf` et des liens relatifs (script du scratchpad) | aucun caractère caché, aucun lien cassé |

## Ce que tu dois pouvoir défendre

- **« Vos tests prouvent-ils que les fiches sont bonnes ? »** Non. Ils prouvent que les contrôles retirent ou
  refusent ce qui sort du contrat, sur des sorties écrites à l'avance. La qualité d'un vrai modèle est mesurée par
  les essais de #210 pour les fiches et de #370 pour les tendances, encore ouvertes
  (`docs/2026-11-08-tests-api-ia.md:303-304`).
- **« Pourquoi un modèle de remplacement plutôt que le vrai en CI ? »** Pas de clé ni de coût en CI, et des tests
  reproductibles. Le *replay* garde le code de l'appel ; seul le transport change (`llm_client.py:210`).
- **« Qu'est-ce qui est réellement de bout en bout ? »** Les trois tests de `test_live_apis.py` : les deux API servies
  par uvicorn, appelées en HTTP par `kb`. Le modèle et GitHub restent simulés.
- **« Et PostgreSQL ? »** Aucun des 1550 tests ne le lit ; il est testé par les tests marqués `postgresql`
  (job `tests-postgresql`), hors de ce périmètre.

## Zones non vérifiées

- Les durées (31,34 s, 13,08 s…) sont celles d'une exécution sur le Mac : elles varient d'une machine à l'autre.
- Le document lit ce que prouve un test par son nom, sa docstring et ses assertions citées. Il ne dit pas que chaque
  assertion de chaque test a été relue.

## Ce qui reste

- Les essais de #210 sur la veille réelle.
- Une nouvelle exécution à chaque changement des tests : les nombres valent pour `f91bb97` seulement.
