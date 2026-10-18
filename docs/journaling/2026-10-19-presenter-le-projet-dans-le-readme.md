# Présenter le projet dans le README

- **Date** : 2026-10-19
- **Branche** : `docs/readme-presentation`
- **Issue** : #5 (critère corrigé et complété par le commentaire du 2026-10-18 : modèle gpt-6-luna,
  lien avec #202, demande certif n° 21, corrections de l'expert)
- **Fichiers principaux** : `README.md`, `docs/stockage.md`, `docs/registre-traitements.md`
- **Série** : suit [l'alignement de la spec de collecte](2026-10-18-aligner-la-spec-de-collecte-sur-le-code.md)
  (#64), la première moitié de la même mission

Les commits listés avant `3db4120` appartiennent à des PR déjà fusionnées (#250, #252, #254,
#255) : ils ne sont pas couverts ici. Cette note couvre les 7 commits de la branche, de `6993263`
à `bea08f9`.

## Le pourquoi

Le README est le premier document que lit le jury. La revue certif du 17/10 y relevait deux
manques : aucune présentation du projet (budget, organisation du travail, planification), et une
variable d'environnement, `GOOGLE_APPLICATION_CREDENTIALS`, utilisée par le code mais absente du
tableau des variables (demande n° 21). L'expert demandait aussi deux corrections : `stockage.md`
disait les lecteurs de la base « pas encore codés », alors que l'API de données tourne, et le
registre des traitements déclarait en base une donnée qui n'y est pas.

Une règle tient tout le travail : une doc ne dit que ce que le code fait. Chaque fait écrit a été
relu dans le code ou dans le journal ADR, et chaque correction a été reportée partout où le même
fait apparaissait (`code.md`, « Avant de déclarer un travail fini », point 7).

## Le comment

### 1. Une section « Conduite du projet » dans le README

Elle se place après « Hors périmètre de la v0 » et avant « Installer et lancer » (`README.md:85`).
Le lecteur lit ainsi ce que fait K-B, puis qui le fait et avec quels moyens, puis comment
l'installer. Six sous-sections : Acteurs, Contraintes techniques, Budget, Organisation du
travail, Planning, Le POC du 25/10 et la suite. Chaque affirmation renvoie à sa source, par
exemple le budget du modèle :

```
| Modèle des fiches | gpt-6-luna sur Azure AI Foundry, sur l'abonnement Azure de mon organisme de formation, […] Je n'en vois pas la facturation. Ordre de grandeur : au pire environ 420 000 jetons par demande de fiches, […] soit quelques centimes (journal ADR, 2026-10-16) ; […]
```

« Je n'en vois pas la facturation » est un fait de l'ADR du 17/10 (rôle « Lecteur », aucun compte
de facturation visible), pas une estimation. Le montant consommé reste « à compléter par Sabine »
dans la PR. L'organisme n'est pas nommé (décision du 17/10, dépôt public le 25/10).

Le README garde sa première personne : « Moi : je porte le projet… ». La ligne 17, qui disait
« Les données restent sur ma machine », est maintenant datée (`README.md:17-18`) : sans cette
date, elle aurait contredit la mise en ligne du 08/11 annoncée plus bas.

### 2. Ce qui est fait et ce qui reste, séparés

La section du POC distingue la cible du 25/10 de l'état du code :

```
**Où on en est** : la collecte, l'import et l'API de données sont codés (voir « Installer et
lancer »). Restent l'image et les conteneurs (#200), le service des fiches par l'API IA (#156) et
l'installation par compose (#202).
```

Le code des fiches existe (`src/k_b/ai_api/`), mais aucune application ne le sert encore ; aucun
Dockerfile n'existe. Présenter le POC comme fait aurait été faux. Le relecteur du plan l'a relevé
(constat 2).

### 3. La variable de BigQuery (n° 21)

La ligne ajoutée au tableau (`README.md:187`) décrit ce que le code fait de la variable :

```python
    for source_name, variable in VARIABLE_BY_SOURCE_NAME.items():
        if collect_only.is_collected(source_name) and not environ.get(variable):
            print(f"{source_name}: skipped ({variable} not set)")
```

(`src/k_b/commands/collect_command.py:61-63`). Pour GH Archive, `source_name` vaut `gh_archive`
(`FOLDER_PREFIX`, `src/k_b/etl/sources/gh_archive.py:44`) et `variable` vaut
`GOOGLE_APPLICATION_CREDENTIALS` (`src/k_b/etl/collected_sources.py:26`). Le message affiché est
donc `gh_archive: skipped (GOOGLE_APPLICATION_CREDENTIALS not set)`. K-B n'ouvre jamais la clé :
le client BigQuery la trouve par la variable (`gh_archive.py:9-10`).

### 4. Qui lit la base aujourd'hui

`stockage.md:20-26` nomme l'API de données, ses trois routes, et la connexion en lecture seule :

```python
def open_database(request: Request) -> Iterator[sqlite3.Connection]:
    """One read-only connection per request, closed once the response is made."""
    connection = connect_database_read_only(request.app.state.database_path)
```

(`src/k_b/data_api/dependencies.py:50-52`). Le code des fiches n'ouvre pas la base : il passe
par l'API de données (`src/k_b/ai_api/connectors/data_api_client.py`, docstring). Le même fait
était répété plus bas (« pour ses lecteurs à venir ») : corrigé aussi.

### 5. SQLite au POC, PostgreSQL au 08/11

`stockage.md` présentait PostgreSQL comme « écarté pour l'instant », alors que sa propre ligne
308 et l'ADR du 15/10 (décision 2) le prévoient au 08/11. Le titre, l'en-tête du tableau et le
pourquoi disent maintenant les deux temps (`stockage.md:28-50`). Au POC, la base ira dans un
volume nommé et non dans le dossier partagé, que l'ADR écarte faute de preuve que le fichier
`-shm` du mode WAL tienne à travers le partage Mac ↔ VM. Cette précision vient de la revue
(constat 1).

### 6. Le registre ne déclare en base que ce qui y est

Le classement des dépôts les plus étoilés n'a pas de lecteur :

```python
    SourceKind(
        github_most_starred.FOLDER_PREFIX,
        (GithubMostStarredSource(),),
        # No reader: the ranking does not enter the base (decision "Tops", 2026-10-08).
        None,
    ),
```

(`src/k_b/etl/source_kinds.py:51-56`). Sans lecteur, l'import ne le lit pas, et aucune table du
schéma ne le reçoit. La ligne 31 du registre passe donc de « oui » à « **non** », et l'exception
« top 100 » de la fiche 1 (l. 50) est retirée. Les autres lignes ont été relues contre
`schema.sql` (`publication.authors`, `release.body`, `trend.repository_name`, `zotero_entry`,
`highlight`, `clip`) : elles étaient justes.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Où présenter le projet | une section du README | un `docs/projet.md` à part : le critère de #5 vise le README, que le jury lit en premier |
| Planning | renvoi à la page des jalons, avec un tableau des jalons à venir relevé le 18/10 | recopier tous les jalons : quatre jalons échus encore ouverts relèvent de time-knight et de Sabine (signalés, traités le 19/10) |
| Board | cité sans lien | un lien : le Project 12 est privé, le lien serait mort pour le jury (décision relayée par time-knight) |
| Langages | Python pour le code, SQL pour le schéma et les requêtes | « Python, seul langage » : faux, le MPD est un script SQL écrit à la main, sans ORM (constat 6 de la revue) |
| Coût du modèle | la borne de l'ADR du 16/10, sa conclusion (« quelques centimes ») et un renvoi à `fiches-veille.md`, « Coût » | calculer un coût sur le découpage actuel des appels : aucune source ne donne de montant, un calcul serait un chiffre inventé |
| Date de la décision « Tops » | journal ADR, 2026-10-07 (l. 496) | le « 2026-10-08 » des commentaires du code : l'entrée est sous `## 2026-10-07` |
| Ordre des commits | un commit par sujet, puis un de corrections de revue | un seul commit : la PR se relit sujet par sujet (consigne de la mission) |

## Preuve

| Commande ou sortie observée | Ce que ça démontre |
|---|---|
| `git grep -n "K-B-data" -- README.md docs/registre-traitements.md docs/stockage.md` → rien | le dossier de données est partout `~/.knowledge_base` |
| `git grep -c "GOOGLE_APPLICATION_CREDENTIALS" -- README.md` → 2 | la variable est au tableau, en plus de la ligne de `kb collect` |
| `git grep -n "pas encore" -- docs/stockage.md` → plus la phrase des l. 20-21 | la base n'est plus décrite comme non lue |
| `grep -rn "connection\|sqlite\|k_b.database" src/k_b/ai_api` → aucune connexion à la base | le code des fiches ne lit pas la base |
| `grep -n "CREATE TABLE" src/k_b/database/schema.sql` → aucune table de classement par étoiles | le top 100 n'est pas en base |
| `uv run pytest -q` → 1769 passed | rien du code n'a bougé |
| `git diff origin/main...HEAD \| grep -c "$HOME"` → 0 | aucun chemin personnel dans la PR |

## Ce que tu dois pouvoir défendre

1. **Combien coûte K-B ?** Rien de visible pour moi : BigQuery tourne en bac à sable, et une
   requête au-delà du quota est refusée, jamais facturée (`docs/bigquery.md`) ; le modèle tourne
   sur l'abonnement de mon organisme, dont je ne vois pas la facturation ; au pire, quelques
   centimes par demande de fiches (ADR du 16/10). La mise en ligne du 08/11 n'est pas chiffrée.
2. **Pourquoi SQLite si la cible est PostgreSQL ?** En localhost, un fichier suffit ; sur Azure
   Container Apps, un fichier SQLite n'a pas de disque fiable. Pour ne pas payer le portage deux
   fois, aucun SQL propre à SQLite n'est ajouté (`poc.md`, règle 1 ; `stockage.md:47-50`).
3. **Le POC est-il prêt ?** Non, et le README le dit : la collecte, l'import et l'API de données
   tournent ; l'image, les conteneurs (#200), le service des fiches (#156) et l'installation par
   compose (#202) restent à faire.
4. **Pourquoi le registre ne déclare-t-il pas le top 100 en base ?** Parce qu'il n'y est pas : la
   source n'a pas de lecteur (`source_kinds.py:51-56`). Le login du propriétaire reste dans le
   brut, d'où la ligne « Personnes concernées », qui garde les propriétaires du top 100.
5. **Que se passe-t-il sans `GOOGLE_APPLICATION_CREDENTIALS` ?** `kb collect` saute GH Archive et
   l'affiche ; les autres sources tournent (`collect_command.py:61-63`).

## Zones non vérifiées

- « Sans frais » pour le jeton GitHub : un jeton personnel est gratuit, mais aucune facture n'a
  été lue.
- `KB_DIGEST_WINDOW_DAYS` est spécifiée (`docs/fiches-veille.md`) mais pas encore codée : le
  README la présente comme la cible du 25/10.
- Le volume nommé et le dossier partagé du POC sont décidés (ADR du 15/10), pas codés (#200).

## Ce qui reste

- Le montant consommé sur l'abonnement Azure : à compléter par Sabine.
- La ligne « Sécurité » du registre (fichiers lisibles par la seule utilisatrice) sera fausse
  quand la base passera dans un volume Docker, puis sur Azure : à mettre à jour avec #200, puis au
  08/11.
- La fiche 1 du registre donne 2 ans au brut de veille, alors que l'ADR du 07/10 dit non décidée
  la durée des fichiers du top 100 : relève de la purge (#83, #139).
- L'« Étape 2 » du README annonce des métriques « émises en OpenTelemetry, gardées sur ma
  machine ». Cela contredit l'ADR du 15/10 (décision 8), la règle 4 de `poc.md` (une ligne JSON par
  appel, sur stdout) et la décision de Sabine du 15/10 (observabilité dans le cloud seulement).
  C'est le périmètre de la v0, hors du critère de #5.
- Le commentaire de `source_kinds.py:54` date la décision « Tops » du 2026-10-08 ; le journal la
  consigne au 2026-10-07. C'est du code, hors de cette mission.
