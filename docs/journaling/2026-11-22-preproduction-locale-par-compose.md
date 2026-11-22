# Lancer K-B en préproduction locale par compose

- **Date** : 2026-11-22
- **Branche** : `feat/local-preproduction-compose`
- **Issue** : #419
- **Fichiers principaux** : `compose.yaml`, les quatre modèles `.env.<service>.example`, `.gitignore`,
  `tests/test_compose_file.py`, `docs/preproduction-locale.md` (le how-to, ses commandes et ses mesures)
- **Série** : la note du 2026-11-08, [https-vers-les-api-internes](2026-11-08-https-vers-les-api-internes.md),
  a posé les noms `api-donnees` et `api-ia` que ce compose emploie.

Les commandes, les sorties attendues et les mesures de l'essai et du contre-essai sont dans
[preproduction-locale.md](../preproduction-locale.md) : cette note ne les recopie pas, elle explique les choix.

## Le pourquoi

K-B tourne en ligne sur Azure Container Apps : une image, deux API, des jobs, une base PostgreSQL. Avant de
mettre une version en ligne, il faut pouvoir l'essayer **dans les mêmes conteneurs**, sur le poste, sans
toucher à la production : c'est la préproduction. Le compose lance l'image de la production et PostgreSQL 18,
crée la base, collecte, importe, puis sert les deux API jusqu'à une `POST /digests` réelle, la chaîne entière
de la base au modèle.

Ce que le compose doit prouver, c'est que l'image se comporte en conteneur comme en ligne : utilisateur non
root, aucun état écrit hors du dossier de données, arrêt propre sur signal, secrets hors du dépôt. D'où les six
services, les règles de durcissement et un test qui les tient à chaque PR sans Docker.

## Le comment

### Une ancre commune, deux familles de services

Les règles communes s'écrivent une fois, dans une ancre YAML que chaque service fusionne (`<<:`) :

```yaml
x-container: &container
  init: true
  read_only: true
  tmpfs:
    - /tmp
  cpus: 0.5
  mem_limit: 1g
  stop_grace_period: 20s
```

(`compose.yaml:22-29`.) Une seconde ancre, `x-kb` (`compose.yaml:32-35`), y ajoute l'image `k-b:preprod`
et `platform: linux/amd64` pour les cinq services `kb` : la plateforme d'Azure, émulée sur un Mac Apple
Silicon. Un service peut redéfinir une clé de l'ancre : la clé redéfinie **remplace** celle de l'ancre, elle
ne s'y ajoute pas. C'est ce que fait `postgres`, avec ses ressources à lui (`cpus: 1`, `mem_limit: 2g`,
`compose.yaml:58-59`, la taille du serveur en ligne, `Standard_B1ms`) et une liste `tmpfs` qui reprend `/tmp`
et ajoute `/var/run/postgresql`, où le serveur écrit son socket et son verrou.

Les API (`api-donnees`, `api-ia`) tournent sans volume, comme en ligne : seuls les trois jobs (`create-db`,
`collecte`, `import`, profil `jobs`) montent `kb-data` sur `/var/lib/knowledge_base`. Le profil fait qu'un
`docker compose up -d` ne lance pas les jobs : chacun se lance seul, par `docker compose run --rm <job>`.

### La sonde de la base passe par TCP

```yaml
      test: ["CMD", "pg_isready", "--host", "127.0.0.1", "--username", "kb", "--dbname", "k_b"]
```

(`compose.yaml:78`.) Au premier démarrage, le script d'entrée de l'image `postgres` lance un **serveur
temporaire** qui n'écoute que sur le socket Unix (`listen_addresses=''`, fonction `docker_temp_server_start`)
pour créer le rôle et la base, puis l'arrête et lance le serveur final. Sans `--host`, `pg_isready` passe par le
socket : il déclare la base saine pendant la phase temporaire, et `create-db`, qui se connecte en TCP à
`postgres:5432`, peut partir trop tôt. Avec `--host 127.0.0.1`, seule la réponse du serveur final compte. Le
contre-essai le montre au journal de `postgres` : deux « ready to accept connections », un seul « listening
on IPv4 ».

### `sandbox` pour la seule API IA

L'API IA appelle l'API de données par `http://api-donnees:8000`. K-B refuse une URL interne en `http`, sauf
vers la machine elle-même, ou vers un service du compose en `sandbox` :

```python
    if parts.scheme == "https" or parts.hostname in LOCAL_HOSTS:
        return None
    if parts.hostname in COMPOSE_HOSTS and is_sandbox(environ):
        return None
    return f"{variable}: {INTERNAL_API_HTTP_REFUSAL}"
```

(`src/k_b/core/outbound.py:58-61`.) D'où `KB_DEPLOYMENT_ENVIRONMENT: sandbox` sur `api-ia`
(`compose.yaml:125`). L'API de données, elle, n'appelle personne : en `sandbox`, elle ne ferait que servir
`/docs` et `/openapi.json` sans clé. Elle tourne donc en `production`, comme en ligne (`compose.yaml:96`). Le
contre-essai le vérifie : `404` sur `8000/docs`, `200` sur `8001/docs`, et l'API IA lit toujours l'API de
données.

### Les secrets : un fichier par service, un modèle suivi par git

Chaque service lit ses secrets dans `.env.<service>`, que `.env.*` fait ignorer par git, avec
`required: true` : sans son fichier, compose refuse de démarrer. Le modèle `.env.<service>.example`, sans
valeur, est suivi grâce à une négation placée **après** la règle qui ignore (`.gitignore`, `!.env.*.example`) :
dans un `.gitignore`, la dernière règle qui correspond l'emporte. Les autres réglages (ports, hôtes permis,
environnement, modèle) sont écrits en clair dans `compose.yaml`, et aucun secret ne s'y trouve : le test le
vérifie par le nom de la variable et par la forme de sa valeur.

### Le test lit le fichier, sans Docker

`tests/test_compose_file.py` charge `compose.yaml` par PyYAML et vérifie chaque règle, service par service. Un
exemple, la règle des secrets :

```python
    # A list of NAME=value would hide the names from the checks below.
    assert isinstance(environment, dict)
    assert [name for name in environment if SECRET_NAME.fullmatch(name)] == []
    assert [
        name
        for name, value in environment.items()
        if CREDENTIALS_IN_URL.search(str(value))
    ] == []
```

(`tests/test_compose_file.py:180-187`.) La première ligne existe parce qu'un `environment` écrit en liste
(`- KB_LLM_API_KEY=…`) ferait passer les deux suivantes à vide. La troisième trouve un mot de passe dans une
URL, quel que soit le nom de la variable. Le test lit aussi le `Dockerfile` (son `USER` n'est pas root), le
`ci.yml` (la base a l'image et les réglages d'`initdb` de la CI) et le `.env.example` (chaque variable d'un
modèle y est décrite).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Créer la base | `kb create-db` : la base `k_b` et son rôle viennent de l'image (`POSTGRES_USER`, `POSTGRES_DB`) | `kb migrate-database` : il donne les tables aux rôles des identités d'Azure, absents ici (`src/k_b/cli.py:146-149`) |
| Le rôle de la base | un seul rôle, `kb`, superutilisateur du serveur, car l'image le crée ainsi ; décision de Sabine du 2026-11-22 (E). L'API de données lit en `READ ONLY` | un rôle de lecture pour l'API de données : il faudrait un script d'initialisation monté, hors de la conception validée |
| Arrêt | `init: true`, exigé par l'issue : il transmet le signal d'arrêt et récupère les processus fils | `kb` en PID 1, comme en ligne : l'issue demande `init`. Ce que cela change pour l'arrêt est écrit dans les écarts de la fiche |
| Délai d'arrêt | 250 s pour l'API IA, comme en ligne, la plus longue demande que laisse passer l'entrée d'ACA (240 s) et une marge ; 20 s ailleurs | moins de 30 s partout, le texte de l'issue : une demande de fiches serait coupée |
| Système de fichiers | `read_only` et `tmpfs: /tmp`, plus stricts qu'en ligne : une écriture hors du volume et de `/tmp` échoue, ce qui vérifie la règle 4 de `.claude/rules/poc.md` | un système de fichiers inscriptible, comme en ligne : il laisserait passer une écriture d'état hors de `KB_DATA_DIR` |
| Fichiers de secrets | un par service, et un seul `.env.jobs` pour les trois jobs (tranché par le Second, gardé par Sabine, K) | un fichier par job : trois fichiers pour deux secrets ; ou un seul fichier pour tout : chaque API lirait les secrets de l'autre |
| Clé dans le how-to | passée à `curl` par l'entrée standard (`-H @-`), puis `unset KEY` (décision de Sabine, R) | `-H "Authorization: Bearer $KEY"` : la clé est dans les arguments de `curl`, que `ps` montre |
| Réseau | le réseau par défaut du projet (décision de Sabine, Z) | deux réseaux, pour que l'API IA ne joigne pas `postgres` : hors périmètre |
| Mesures | aucun export vers Grafana Cloud (`KB_OTLP_*` non posés) : la préproduction ne se mêle pas aux séries de la production | l'export : les demandes de la préproduction se mêleraient aux séries de la production |
| CI | aucun job pour compose : le test tient les règles à chaque PR, l'essai prouve le lancement (mission du 21/11) | un job qui lance compose à chaque PR |
| Documentation | un how-to dans `docs/` (décision du Second) ; la doc d'installation reste à #202 | tout dans le README |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/test_compose_file.py` : 70 tests passés, 3 en échec avant les corrections de la revue (ressources de la base, sonde en TCP, API de données en `production`) | chaque règle du compose est tenue, et chaque correction de la revue a eu son test rouge d'abord |
| Cinq copies modifiées dans le scratchpad (négation avant `.env.*`, `USER root`, `environment` en liste, mot de passe dans une URL, hôte non permis) : chacune fait échouer son test | les tests renforcés échouent sur un fichier fautif, ils ne passent pas à vide |
| Essai du 2026-11-22, `8a047e6b` : trois jobs à `0`, 3 201 items, services sains en 11 s, `POST /digests` `200` en 32,9 s, `stop` en 0,83 s, données gardées après `down` puis `up` | la chaîne entière tourne en conteneurs, de la collecte au modèle |
| Contre-essai, `f24d5cd7` : `create-db` à `0` sur un volume neuf, après la sonde en TCP ; `404` et `200` sur `/docs` ; `docker stats` à 2 GiB pour `postgres` | les trois changements du compose après l'essai tiennent |
| `id -u` : `999`, puis `10001` pour chaque service `kb` | aucun service ne tourne en root |
| Journaux, 27 lignes comptées : aucune ne porte `postgresql://`, `Bearer `, `github_pat_` ni `password=` | aucun secret ne sort dans les journaux de ces lignes |
| `git check-ignore -v` sur les quatre fichiers ; `git ls-files '.env.*.example'` | les secrets sont ignorés, leurs modèles suivis |

## Ce que tu dois pouvoir défendre

1. **Pourquoi la préproduction n'est-elle pas identique à la production ?** Parce que certaines choses n'ont
   pas d'équivalent local : les identités Entra et leurs rôles, le HTTPS de l'entrée d'ACA. Chaque différence
   est un écart nommé, avec sa raison, dans la fiche (« Les écarts voulus à la production ») et dans le
   commentaire de tête de `compose.yaml:12-16`.
2. **Que se passe-t-il si un service écrit hors de son volume ?** L'écriture échoue : le système de fichiers
   est en lecture seule (`read_only: true`, `compose.yaml:24`), seul `/tmp` est en mémoire. C'est plus strict
   qu'en ligne, volontairement : la préproduction attrape une écriture d'état qu'en ligne on perdrait au
   redémarrage.
3. **Où sont les secrets, et comment sait-on qu'ils ne fuient pas ?** Dans `.env.<service>`, ignoré par git
   et exclu du contexte du build (`.dockerignore`, `**/.env*`). Le test refuse un nom de secret ou une URL
   avec mot de passe dans `compose.yaml` et une valeur dans un modèle. `docker compose config` ne se lance
   qu'avec `--quiet`, car sans lui il affiche les secrets résolus.
4. **Pourquoi `--host 127.0.0.1` dans la sonde de la base ?** Pour ne déclarer la base saine qu'une fois le
   serveur final à l'écoute en TCP. Le serveur temporaire de l'initialisation ne répond que sur le socket
   (`compose.yaml:74-78`).
5. **Pourquoi l'API IA est-elle en `sandbox` et pas l'API de données ?** L'API IA appelle un service du
   compose en `http`, ce que seul `sandbox` permet (`src/k_b/core/outbound.py:58-61`). L'API de données
   n'appelle personne : en `production`, comme en ligne, elle ne sert pas sa documentation sans clé.

## Zones non vérifiées

- La limite de CPU des conteneurs n'est pas lue : `docker stats` ne la donne pas, et `docker inspect` est
  écarté par la mission. Seule la limite de mémoire est constatée (2 GiB, 1 GiB).
- Le comportement du serveur temporaire de l'image `postgres` est lu dans sa documentation (Context7,
  `docker-library/postgres`) et constaté au journal ; le script `docker-entrypoint.sh` n'est pas relu ligne à
  ligne.
- « Joignable des seuls conteneurs du compose » : c'est le réseau par défaut du projet. Le contre-essai n'en
  vérifie qu'une partie : chaque API répond en `http` depuis le poste par `127.0.0.1`.
- Les journaux de la `POST /digests` de l'essai n'ont pas été comptés : ils ont été retirés avec les
  conteneurs avant le comptage. Ceux du contre-essai n'ont aucune ligne `WARNING`, `ERROR` ou `CRITICAL`.

## Ce qui reste

- **#202** : la documentation de l'installation par compose, avec la sauvegarde de la base (`pg_dump`), dans
  la fiche de l'installation.
- **`VARIABLE_LINE`** apparaît pour la troisième fois dans les tests (`tests/architecture/test_environment.py`,
  `tests/e2e/conftest.py`, ce test) : la factorisation toucherait deux autres fichiers de test et est laissée
  hors de cette PR.
- Hors du compose, volontairement : le site (`kb serve-web`), les autres jobs (`kb daily-routine`,
  `kb digest-watch`, `kb smoke-test`) et le stockage d'échange.
