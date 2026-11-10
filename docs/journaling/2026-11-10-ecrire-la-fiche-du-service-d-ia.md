# Écrire la fiche du service d'IA: le déploiement de gpt-6-luna sur Foundry

- Date: 2026-11-10
- Branche: `docs/ai-service-sheet`
- Issue: #506
- Fichier principal: `documentation/service_ia_pour_docu.md` (neuf)
- Série: [2026-11-09-ecrire-la-fiche-de-l-architecture.md](2026-11-09-ecrire-la-fiche-de-l-architecture.md) et
  [2026-11-08-ecrire-la-fiche-de-l-api-ia.md](2026-11-08-ecrire-la-fiche-de-l-api-ia.md); le branchement d'origine:
  [2026-10-17-brancher-gpt-6-luna-sur-foundry.md](2026-10-17-brancher-gpt-6-luna-sur-foundry.md).

La PR est un seul commit sur `c31f408`. Il réunit les étapes du travail: la fiche, les constats retenus des deux
relectures, cette note, puis le masquage des noms de la ressource et du groupe. La branche a été refaite en un
commit avant le push, pour que ces noms n'entrent pas dans l'historique public. Les autres commits et fichiers que
liste l'outil sont ceux de PR déjà fusionnées sur `main`: ils ne sont pas de cette PR.

## Le pourquoi

Le référentiel demande une documentation du service d'IA (C8): la gestion des accès, l'installation et le test,
les dépendances et interconnexions, les données impliquées. Le service de K-B est un déploiement fait à la main dans
le portail Foundry le 2026-10-17, hors du code: ses réglages n'étaient écrits que dans une note datée, le registre
des traitements et le journal ADR. La fiche les réunit, les vérifie sur la ressource elle-même, et les distingue de
l'API IA, qui a sa propre fiche.

## Le comment

### 1. Deux sortes de faits, deux preuves

Ce que montre le code se cite en `fichier:ligne` au commit `c31f408`. Ce qui est hors du code se lit sur Azure, en
lecture seule, par des commandes que l'opératrice lance elle-même; la fiche les recopie dans « Relire l'état », le
groupe et la ressource en variables (`RG=<groupe de ressources>`). Par exemple, la ressource:

```sh
az cognitiveservices account list -g "$RG" --query "[].{nom:name, region:location, type:kind, sous_domaine:properties.customSubDomainName, acces_public:properties.publicNetworkAccess, cle_coupee:properties.disableLocalAuth, journal_abus:join(',', properties.capabilities[?name=='ContentLogging'].value)}" -o table
```
(`documentation/service_ia_pour_docu.md`, « Relire l'état »)

Une seule ligne montre trois faits: l'authentification par clé est active (`disableLocalAuth` à `False`), l'accès
réseau public est activé, et le stockage de la surveillance des abus n'est pas coupé (`ContentLogging` absent:
selon Microsoft, la capacité n'apparaît, à `false`, que s'il l'est).

### 2. La clé, de bout en bout

K-B appelle le modèle par la clé de la ressource:

```python
        else {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}
```
(`src/k_b/ai_api/connectors/llm_client.py:214`)

Microsoft le dit: avec une clé, les rôles ne s'appliquent plus (« the key grants full access without role
restrictions »). D'où le tableau des rôles: Owner, Contributor et Foundry User suffisent chacun à lire la clé, donc
à tout appeler. En ligne, la clé est le secret `kb-llm-api-key`, lu par la seule identité de `ca-kb-ai-api` parmi
celles de K-B (`infra/main.bicep:141`, `:144-153`).

### 3. Tester sans afficher la clé

La commande de test lit la clé dans la variable que `uv run --env-file` pose, et la passe à `curl` par l'entrée
standard:

```sh
uv run --env-file .env sh -c 'printf "Authorization: Bearer %s\n" "$KB_LLM_API_KEY" | curl -sS -H @- \
```
(`documentation/service_ia_pour_docu.md`, « Refaire le test », étape 2)

`printf` est une commande interne du shell: la clé n'apparaît ni à l'écran, ni dans l'historique, ni dans la liste
des processus, où `curl -H "Authorization: …"` l'aurait mise. La sortie se réduit au modèle rendu et au
`finish_reason`. La commande a d'abord été essayée sur un serveur local factice (une clé fictive, l'en-tête et le
corps relus), puis lancée sur Foundry. Un appel sans clé, lui, doit rendre 401.

### 4. Ce que Microsoft garde, malgré le cache coupé

Le cache de la consigne est coupé par K-B à chaque requête (`llm_client.py:41`, `:414`). Mais la surveillance des
abus peut stocker une demande signalée pour une revue humaine, dans la géographie de la ressource, sans durée
publiée. Elle n'est modifiable que sur demande du titulaire de l'abonnement, l'organisme. La fiche l'écrit dans
« Les données envoyées au modèle », avec ses deux pages de Microsoft.

## Choix faits et options écartées

- **Une fiche neuve dans `documentation/`, aucun fichier de `docs/` ni le README modifiés** (critère de #506).
  Le registre a deux écarts avec Microsoft (la zone de l'Union et l'AELE; la surveillance modifiable): ils iront
  dans une issue de documentation à part (tranché par time-knight).
- **Le périmètre de la zone de l'Union**: la fiche suit la page « Understanding deployment types » (EU Data
  Boundary, AELE possible), comme C8, et cite la page « Data, privacy, and security », qui dit « European Union
  Member Nation ». Écarté: n'en citer qu'une, ce qui cacherait l'écart.
- **Le retrait avec `NoAutoUpgrade`**: la même page de Microsoft le dit de deux façons; la fiche cite les deux.
- **`DeepSeek-V4-Flash`**: la fiche dit « aucun fichier du code, de l'infrastructure, des tests ni de la
  configuration ne le nomme », et non « aucun fichier du dépôt », que le journal ADR et une note contredisent.
- **La valeur en ligne de `KB_LLM_MODEL`**: non lue (décision de Sabine); la fiche dit que le dépôt ne la fixe
  pas.
- **Les noms de la ressource et du groupe**: masqués (constat 1 de la première relecture, tranché par Sabine). Le
  nom de la ressource donne l'adresse du modèle, que la clé ouvre; la fiche suit la forme de `infra/README.md`
  (`RG=<groupe de ressources>`). Écarté: les garder, comme la mission et C8 les nomment.
- **Les 25 autres constats de la première relecture**: tranchés par time-knight, sur délégation de Sabine du 15/10.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `az … deployment list` (2026-11-09, 23:41 et 23:42 UTC): deux déploiements, `DataZoneStandard`, `gpt-6-luna` en `NoAutoUpgrade` | le type et la version figée, sur la ressource elle-même |
| `az … account list` (23:54 UTC): une ligne, `Enabled`, `False`, `ContentLogging` absent | une seule ressource dans le groupe; clé active; réseau public activé; surveillance des abus non modifiée |
| appel avec la clé (2026-11-10, 00:03 UTC): `gpt-6-luna-2026-09-22 stop` | le déploiement répond, à la version figée |
| appel sans clé (00:03 UTC): `HTTP 401` | sans clé, l'appel est refusé |
| `git grep -niE deepseek c31f408 -- src infra tests observability …`: rien | K-B n'appelle pas `DeepSeek-V4-Flash` |
| `git diff origin/main...HEAD`, cherché pour les noms de la ressource et du groupe: rien | aucun des deux noms dans la PR |
| `git diff --stat origin/main -- docs/ README.md --diff-filter=M`: vide | aucun fichier existant de `docs/` ni le README modifié |
| deux relectures par un sous-agent neuf, sur le code, les relevés et Microsoft Learn | chaque citation vérifiée; 26, puis 15 constats |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi une clé, et pas une identité Entra ID? »** La clé est ce que K-B code aujourd'hui
   (`llm_client.py:214`). Elle passe outre les rôles; un jeton Entra ID, par l'identité managée de l'API IA et
   Foundry User, ne l'est pas encore (fiche, « Limites »).
2. **« Les données restent-elles en Europe? »** Le traitement reste dans la zone de données de l'Union, que
   Microsoft définit et peut étendre; les données au repos restent dans la géographie de la ressource. Les deux
   pages de Microsoft ne disent pas le même périmètre (AELE ou non): la fiche cite les deux.
3. **« Le cache est coupé: Microsoft ne garde donc rien? »** Non: la surveillance des abus peut garder une
   demande signalée, pour une revue humaine dans l'Espace économique européen, sans durée publiée. `ContentLogging`
   absent montre qu'elle n'est pas coupée.
4. **« La production appelle-t-elle le modèle? »** Non: aucun job déployé ne demande de fiche; le test de fumée
   n'appelle que `GET /health` (`core/api_health.py:12-13`, `infra/deployment.json`).
5. **« Que se passe-t-il au retrait de la version? »** Microsoft le dit de deux façons: le déploiement cesse de
   répondre, ou il est mis à niveau d'office. La date lue est le 2028-03-11, pour le modèle de base; le courriel
   de préavis ne va pas à l'opératrice.

## Zones non vérifiées

- Les libellés du portail Foundry (« Déployer un modèle », « Clés et point de terminaison »): repris de la note du
  2026-10-17 et du registre, pas revus dans le portail.
- Les règles réseau de la ressource (`networkAcls`), l'existence de l'ancienne ressource hors du groupe, et la
  sortie brute de `az role assignment list`: non relues dans cette session.
- La procédure de changement de clé: décrite, pas essayée.

## Ce qui reste

- Les deux écarts du registre avec Microsoft: une issue de documentation, plus tard (time-knight).
- Un jeton Entra ID au lieu de la clé, et une alerte avant le retrait de la version: non prévus ici.
