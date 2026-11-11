# Mettre la routine quotidienne en ligne

- **Date** : 2026-11-10
- **Branche** : `feat/daily-routine-job`
- **Issue** : #330
- **Fichiers principaux** : `infra/modules/daily-routine-job.bicep` (nouveau), `infra/main.bicep`,
  `infra/deployment.json`, `infra/postgresql/create-daily-routine-principal.sql` (nouveau),
  `infra/postgresql/grant-roles.sql`, `infra/README.md` (« La routine quotidienne (#330) »),
  `docs/registre-traitements.md`, `docs/ADR/journal-decisions-projet.md`
- **Série** : suit [Mettre la base PostgreSQL en ligne](2026-11-06-mettre-la-base-postgresql-en-ligne.md) (#421),
  [Créer le stockage des jobs et des échanges](2026-11-10-creer-le-stockage-des-jobs-et-des-echanges.md) (#420),
  [Écrire une fiche une fois, même à deux](2026-11-10-ecrire-une-fiche-une-fois-meme-a-deux.md) (#295) et
  [Purger par sa propre commande](2026-11-10-purger-par-sa-propre-commande.md) (#540).

Tous les commits de la branche sont couverts. Le premier commit du job (`d5df721`) le planifiait à 03:00 UTC ;
`1266398` le déplace à 08:00 UTC, et seul ce second réglage reste dans le code. Les commits de documentation (README
d'infra, registre, journal ADR) se retrouvent dans « Choix faits » et « Preuve » ; ceux des revues et du rebase sur
`kb purge` (`7f43ba8`, `1c8117a`, `dcd29e9`, `b967df0`), dans « Preuve ».

## Le pourquoi

Le produit minimum du rendu, c'est la veille et les tendances qui tournent seules, en ligne. `kb daily-routine`
(#413) existait déjà dans l'image : le miroir des clips, `kb collect`, `kb import`, `kb write-tops`, puis la
publication des fiches dans `watch`. Mais rien ne la lançait en ligne. La base (#421) et le partage `job-data`
(#420) attendaient leur premier écrivain.

Cette PR crée le job planifié qui lance la routine chaque jour. Elle lui donne une identité, ses droits sur la base,
le stockage et les secrets, et elle écrit la procédure d'amorçage suivie le 10/11. Aucun code Python de production
ne change : la routine existait, ce qui change, c'est où elle tourne et sous quelle identité.

## Le comment

### Un job planifié, une exécution à la fois, bornée dans le temps

```bicep
        cronExpression: '0 8 * * *'
        parallelism: 1
…
      replicaTimeout: 3600
      replicaRetryLimit: 1
```
(`infra/modules/daily-routine-job.bicep:78-86`)

Container Apps lit le cron en UTC : 08:00 UTC, c'est 9 h à Paris en hiver et 10 h en été. `parallelism: 1` : une
seule réplique par exécution. `replicaTimeout` arrête une réplique au bout de 3 600 s, et une seule reprise suit un
échec. D'après Microsoft Learn (« Jobs in Azure Container Apps »), le délai l'emporte sur les reprises : une
exécution du cron finit donc avant 09:00 UTC, reprise comprise, et ne déborde pas sur les comptes rendus de #423,
prévus à 10:00.

Un code de sortie autre que 0 fait échouer la réplique. C'est le cas du code 4 de la routine, « une étape a échoué,
une autre a abouti » : le job la reprend une fois, puis l'exécution est `Failed`. L'essai du 10/11 l'a montré
(« Preuve »).

### Une identité à elle, membre de `kb_writer`

```sql
SELECT * FROM pg_catalog.pgaadauth_create_principal_with_oid(
    'id-kb-daily-routine', :'daily_routine_principal_id', 'service', false, false
);
```
(`infra/postgresql/create-daily-routine-principal.sql:11-13`)

```sql
GRANT kb_writer TO "id-kb-daily-routine";
```
(`infra/postgresql/grant-roles.sql:59`)

Le rôle PostgreSQL est lié à l'identité Azure par l'identifiant de son principal de service, et non par son nom :
une identité d'un autre groupe de ressources pourrait porter le même nom. Il a son propre fichier, parce que
`create-principals.sql` ne se relance pas (son `CREATE DATABASE kb` échoue une fois la base créée). Puis
`grant-roles.sql` le fait entrer dans `kb_writer`, le groupe qui écrit les données sans pouvoir changer les tables.
Jusqu'ici, les tests posaient ce `GRANT` eux-mêmes (fixture `daily_routine_member`). Il est maintenant dans le
script appliqué en ligne, et les tests lisent le même script : la fixture disparaît (`tests/database/test_grants.py`).

### Deux secrets à elle, dont un en fichier

```bicep
var dailyRoutineSecretVariables = {
  KB_GITHUB_TOKEN: 'kb-github-token'
}
var bigQueryKeySecretName = 'kb-bigquery-key'
```
(`infra/main.bicep:166-169`)

Le jeton GitHub est un jeton *fine-grained* sans aucune permission, sur les dépôts publics, à part de celui de l'API
IA : chacun se révoque sans arrêter l'autre. La clé BigQuery, elle, se lit comme un fichier :
`GOOGLE_APPLICATION_CREDENTIALS` donne un chemin. Elle passe donc par un volume de type `Secret` :

```bicep
          storageType: 'Secret'
          // The key of BigQuery alone: without this list, every secret of the job is a file of the
          // volume, the token of GitHub included.
          secrets: [
            {
              secretRef: bigQueryKeySecretName
```
(`infra/modules/daily-routine-job.bicep:139-144`)

Sans la liste `secrets`, chaque secret du job deviendrait un fichier du volume, jeton GitHub compris. Le volume est
monté sur `/mnt/secrets`, hors du partage : la clé n'est jamais écrite là où le job garde ses données. Chaque secret
est lu sous l'identité du job, qui n'a le rôle Key Vault Secrets User que sur ses deux secrets (`main.bicep:179-188`).

### Le partage `job-data` monté sur le dossier de données

```bicep
          storageType: 'AzureFile'
…
          mountOptions: 'uid=10001,gid=10001,dir_mode=0700,file_mode=0600'
```
(`infra/modules/daily-routine-job.bicep:131-135`)

Le partage est monté sur `/var/lib/knowledge_base`, que `KB_DATA_DIR` nomme, et le coffre de travail est
`KB_VAULT_DIR`, sous lui (`main.bicep:302-303`). Le brut, l'état de la collecte et les fiches restent ainsi d'une
exécution à l'autre. Les options de montage donnent les fichiers à l'utilisateur de l'image (10001), lisibles par lui
seul : ce sont celles que la sonde de #420 a essayées.

La routine refuse de démarrer sans le dossier `vault/`, et la collecte des clips échoue sans `vault/Clippings/`.
Personne ne les crée automatiquement, pour qu'un `KB_VAULT_DIR` mal écrit se voie. L'opératrice les crée une fois,
sous un rôle temporaire posé sur le seul partage, puis retiré.

### La livraison continue suit le job

```json
  "jobs": ["caj-kb-smoke-test", "caj-kb-migrate-database", "caj-kb-daily-routine"]
```
(`infra/deployment.json:3`)

Chaque tag change désormais l'image de la routine, comme celles des API et des deux autres jobs. Pour cela,
`id-kb-deploy` reçoit le rôle Container Apps Jobs Contributor sur le job. Ce rôle permet aussi de lancer le job, donc
d'agir sous son identité : lire les clips, écrire la base, obtenir ses deux secrets. Le commentaire de
`infra/modules/deploy-access.bicep:1-7` le dit, et le registre le porte comme un risque accepté.

### L'amorçage : de zéro, deux exécutions le même jour

Le README d'infra (« La routine quotidienne (#330) ») donne l'ordre suivi le 10/11. D'abord le critère rouge : le job
n'existe pas. Puis les deux secrets, le principal et ses droits (`t|t|t`), la seconde passe avec un tag posé après la
fusion de #295, et les dossiers du coffre. Viennent ensuite deux exécutions le même jour UTC, puis le retrait du rôle
temporaire, et enfin le cron du lendemain.

Le même geste prépare l'essai de #295 : un temporaire caché `.<jour>.md.tmp`, posé depuis le Mac dans le dossier de
la fiche du top `most_forked`. La première exécution doit le trouver et refuser d'écrire cette fiche, puis échouer.
Une fois le temporaire retiré, la seconde écrit `most_forked` et ne réécrit pas la fiche de `most_starred` déjà là.
On a ainsi éprouvé l'écriture « une fois » sur un vrai partage SMB, entre deux clients, sans fausse fiche publiée.

## Choix faits et options écartées

| Décision | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Heure du cron | 08:00 UTC, « collecte quotidienne à 9h » (Sabine, 10/11) | 03:00 UTC, venu du plan du 06/11 sans raison écrite |
| Données de départ | Rien du Mac : « les collect et production précédente de kb local sur ma machine ne sont pas à garder » (Sabine, 10/11) | Copier `raw/`, l'état et `veille/` avec un instantané avant (texte d'origine de l'issue) : des essais de développement |
| Dossiers du coffre | Créés une fois par l'opératrice, rôle temporaire retiré ensuite (« on garde le plan », Sabine) | Les créer dans la routine : un coffre mal nommé passerait inaperçu ; `kb init` (#356) viendra plus tard |
| Droits de `id-kb-deploy` | Jobs Contributor sur la routine, risque accepté par Sabine après la revue de sécurité | Un rôle personnalisé sans `Microsoft.App/jobs/*/action` : `Microsoft.App/jobs/write`, nécessaire pour changer l'image, couvre déjà tout le job |
| Jeton GitHub | Un jeton propre à la routine, sans permission, 90 jours | Celui de l'API IA : une révocation arrêterait les deux |
| Reprise | 1 reprise, bornée par le délai (plan validé ; constat 1 de la revue écarté) | Aucune reprise : un échec passager (arXiv qui expire) attendrait le lendemain |
| Essai de #295 | Dans l'amorçage, sans sonde ni tag à part (Sabine, 10/11) | Une sonde à part ; pas d'essai |
| #458 (échecs de connexion à la base) | Plus un préalable : `t\|t\|t` et le test `kb_writer` la remplacent (Sabine, 10/11) | L'attendre avant la mise en ligne |
| Brut en ligne | Fichier sous `KB_DATA_DIR`, sur Azure Files ; Blob seulement pour les échanges (règle 3 de `poc.md` amendée, décision 9 du 06/11) | Brut dans Blob : suite du projet, #317 |
| `kb write-tops` en ligne | Dans la routine : « témoin de fonctionnement du pipeline » et « restitution sans llm » (Sabine) | Le garder sur le Mac (question ouverte depuis le 19/10, fermée ici) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `tests/database/test_grants.py:66` et `:77`, rouges sans le `GRANT` de `grant-roles.sql` (« permission denied for database », `488e1af`) | Le script appliqué en ligne suffit : la routine écrit les données et ne change aucune table |
| `tests/commands/test_purge_command.py:221`, rouge sur deux sorties faussées exprès, puis vert (`b967df0`) | Sous le rôle de la routine, `kb import` écrit, puis `kb purge` supprime items, lignes du brut et du registre |
| 4 111 tests, plus 323 sur PostgreSQL ; ruff, format, mypy ; compilation du Bicep | Rien d'autre n'a bougé |
| `/security-review` xhigh : 0 constat ; `/code-review high` : 8 constats, puis 7 sur le rebase, triés par time-knight | Revues faites, tri écrit dans la PR |
| `az containerapp job show` : `ResourceNotFound` avant la passe | Le critère rouge de l'issue |
| `t\|t\|t` (membre de `kb_writer`, `CONNECT`, `INSERT`) | Le principal existe en ligne, avec ses droits |
| Aperçu de la seconde passe : 5 créations attendues | La passe ne crée que le job et ses rôles |
| Exécution `y14t4m5` : code 4 deux fois, `temporary_file_found` pour `most_forked`, `most_starred` écrite, statut `Failed` | L'écriture « une fois » de #295 sur `job-data`, et la reprise du job |
| Exécution `vm5kiy7` : `Succeeded`, code 0 ; `most_starred` en `sheet_exists`, même etag (`0x8DF3F3CF48EDCC5`) | Une fiche écrite n'est jamais réécrite, même par une autre exécution |
| `gh_archive` : 6 fenêtres, 60 Mo, 288 lignes | La clé BigQuery est lisible par l'utilisateur 10001 |
| Exécution `29906400` du cron, le 11/11 de 08:00:00 à 08:01:28 UTC : `Succeeded` ; 5 étapes sorties en 0, routine en 56 s ; 16 sources collectées en 41 s ; `gh_archive` : 1 fenêtre, 17,5 Mo, 50 lignes ; import : 8 bruts lus, 0 rejet ; fiches des tops du 11/11 écrites, 2 envoyées à `watch`, 2 déjà présentes | Le critère de fin de l'issue : le cron lance seul la routine, qui collecte, importe et publie |

## Ce que tu dois pouvoir défendre

1. **Que se passe-t-il si deux exécutions se chevauchent ?** Le cron n'en lance qu'une (`parallelism: 1`), mais rien
   n'empêche une exécution lancée à la main de croiser celle du cron. D'où la règle des heures : aucune exécution à
   la main après 07:00 UTC (README d'infra). Si cela arrive quand même, l'écriture « une fois » de #295 refuse la
   seconde fiche au lieu de l'écraser. Le verrou entre exécutions viendra avec #426.
2. **Le déploiement continu peut-il lire tes secrets ?** Oui, en lançant le job sous son identité. C'est le risque
   propre à toute livraison continue, accepté par Sabine. Il est réduit par des secrets au moindre privilège : un
   jeton sans permission, la clé d'un compte qui n'a que BigQuery Job User dans un projet sans facturation, chacun
   révocable seul (`deploy-access.bicep:1-7`, registre « Déploiement continu »).
3. **Pourquoi la clé BigQuery est-elle un fichier, et seule dans son volume ?** La bibliothèque Google lit un
   chemin (`GOOGLE_APPLICATION_CREDENTIALS`). Sans la liste `secrets` du volume, le jeton GitHub y serait aussi écrit
   en fichier (`daily-routine-job.bicep:139-144`).
4. **Pourquoi la routine a-t-elle échoué le 10/11, et pourquoi était-ce voulu ?** Un temporaire caché avait été posé
   exprès dans le dossier d'une fiche. `kb write-tops` a refusé d'écrire cette fiche (`temporary_file_found`), et
   l'exécution est sortie en 4, puis a fini `Failed` après sa reprise. C'est la preuve qu'une fiche en cours
   d'écriture n'est jamais écrasée. L'exécution suivante, temporaire retiré, a réussi.
5. **Pourquoi la base en ligne n'a-t-elle rien de ton Mac ?** Les données du Mac sont des essais de développement.
   La base en ligne part de sa première collecte, et le registre dit ce que ça coûte : arXiv depuis le 01/05,
   7 jours de TLDR, tout CISA KEV, 8 jours de GH Archive.

## Zones non vérifiées

- **Un secret renouvelé** : qu'une exécution lancée plus de 30 minutes après lise la nouvelle version n'est pas
  vérifié. Ce sera fait à la première rotation.
- **Le délai qui borne la reprise** : il est lu dans Microsoft Learn, mais pas observé, aucune exécution n'ayant
  atteint 3 600 s.
- **Le mode du fichier de la clé** n'a pas été lu directement : on le déduit de la lecture réussie de GH Archive.
- **Une exécution `Failed` sans heure de fin** (`"end": null`) : c'est observé, pas cherché dans la documentation.
- **Les ressources** (0,5 vCPU, 1 Gio) : seule la durée est relevée (2 min 16 s pour la première tentative de
  l'essai, 56 s pour la vraie première exécution), pas la mémoire consommée.
- **La suppression d'un dossier** (`rmdir`) sur `job-data` : elle n'a pas été essayée, et la purge du brut n'en
  aura pas besoin avant mai 2027.
- **Deux conteneurs qui écrivent en même temps**, et ce qu'un client voit d'une écriture faite par un autre : ce
  sont les limites écrites au registre, avec leur parade.

## Ce qui reste

- **Le tag suivant** apporte `kb purge` comme étape à part en ligne (6 étapes). Il ne demande rien au Bicep : la
  purge est une étape de `kb daily-routine`. D'ici là, l'image `v0.1.1` purge dans `kb import`, en 5 étapes.
- **#423** : les comptes rendus de veille et des tendances en ligne, dans un job à part, à 10:00 UTC le lundi et le
  jeudi.
- **#426** : tenir deux exécutions à l'écart l'une de l'autre.
- **#542** : l'envoi des clips et de Zotero ; **#425** : la copie de Zotero en ligne.
- **Trois issues en Backlog**, créées à la PR : le retrait d'un temporaire orphelin, l'alerte sur une exécution
  `Failed`, et la factorisation des variables d'environnement des modules Bicep.
- **Un instantané de `job-data`** avant chaque mise en production, dès le tag suivant.
- **#458** après #423 ; **#317** (le brut dans Blob) et **#356** (`kb init`) plus tard.
