# Mettre la base PostgreSQL en ligne, ouverte par Entra seul

- **Date** : 2026-11-06
- **Branche** : `feat/online-database`
- **Issue** : #421
- **Fichiers principaux** : `src/k_b/database/entra.py`, `src/k_b/database/location.py`,
  `src/k_b/database/postgresql.py`, `src/k_b/database/creation.py`,
  `src/k_b/commands/migrate_database_command.py`, `infra/postgresql/create-principals.sql`,
  `infra/postgresql/grant-roles.sql`, `src/k_b/database/grants_postgresql.sql`,
  `infra/modules/postgresql-server.bicep`, `infra/modules/migrate-database-job.bicep`, `infra/main.bicep`,
  `infra/modules/api-container-app.bicep`
- **Série** : suit [Créer la base et importer en PostgreSQL](2026-11-06-creer-la-base-et-importer-en-postgresql.md)
  (#417), [Lire la base en PostgreSQL](2026-11-06-lire-la-base-en-postgresql.md) (#418) et
  [Mettre en ligne le squelette sur Azure](2026-11-06-mettre-en-ligne-le-squelette-sur-azure.md) (#414).

## 1. Le pourquoi

Depuis #417 et #418, K-B sait écrire et lire une base PostgreSQL. Depuis #414, ses deux API tournent sur Azure
Container Apps, mais l'API de données n'a pas de base : ses routes de données répondent 503. Cette PR donne à
K-B sa base en ligne, un serveur Azure Database for PostgreSQL, et la façon de créer son schéma.

Trois contraintes, toutes décidées avant le code :

- **Aucun mot de passe** (décision 2 du plan de mise en ligne, reprise dans #421). Chaque programme se présente
  au serveur par son identité managée Microsoft Entra, et le serveur refuse l'authentification par mot de passe.
  Il n'y a donc aucun secret de base à garder, à faire tourner ou à fuiter.
- **L'API de données ne fait que lire** (le registre des traitements le promet). Le serveur doit le garantir
  lui-même, pas seulement le code de l'API.
- **Pas de migration, base de prod vierge** (Sabine, 06/11). `kb migrate-database` crée le schéma sur une base
  vide et ne touche pas une base qui l'a déjà. Les vraies migrations attendent le premier changement de schéma
  en ligne (#186).

Le critère de fin de #421 : `caj-kb-migrate-database` lancé deux fois rend `Succeeded` les deux fois, et la
seconde ne change rien ; l'authentification par mot de passe est coupée sur le serveur ; sous
`id-kb-data-api`, une écriture est refusée. Les trois ont été vérifiés en ligne le 06/11 (section 5).

## 2. Le comment

### 2.1 Choisir l'authentification par une variable explicite

`KB_DATABASE_AUTH` dit comment `kb` s'authentifie : `libpq` (défaut, ce que dit l'URL) ou `entra` (un jeton de
l'identité). Sous `entra`, K-B exige l'identifiant client de l'identité, un GUID :

```python
    client_id = environ.get(CLIENT_ID_VARIABLE)
    if not client_id:
        return (
            f"{CLIENT_ID_VARIABLE}: not set, {DATABASE_AUTH_VARIABLE} is {ENTRA_AUTH}"
        )
    if not CLIENT_ID.fullmatch(client_id):
        return f"{CLIENT_ID_VARIABLE}: not a GUID"
```
(`src/k_b/database/location.py:151-157`)

La fonction rend soit la base, soit la raison du refus : un réglage faux arrête la commande avant toute
connexion (échouer fermé). Le même fichier refuse aussi `entra` sans `KB_DATABASE_URL`
(`location.py:116-125`). Sans ce refus, le job en ligne retomberait sur le fichier SQLite de son disque
éphémère et dirait « database created » : c'est le constat C1 de la revue de code.

### 2.2 Un jeton par connexion, jamais un jeton hors d'une connexion vérifiée

Le jeton Entra est un **secret porteur** : qui le détient se connecte. K-B ne l'envoie qu'à un serveur dont
libpq a vérifié le certificat et le nom, donc en `sslmode=verify-full`, et refuse une URL qui porterait en plus
un mot de passe :

```python
    if settings.get("sslmode") != VERIFY_FULL:
        return (
            f"{DATABASE_URL_VARIABLE} does not set sslmode={VERIFY_FULL}, which"
            f" {DATABASE_AUTH_VARIABLE} {ENTRA_AUTH} asks for"
        )
```
(`src/k_b/database/postgresql.py:187-191`)

`check_url` (`postgresql.py:161`) fait ce contrôle **avant** de demander le moindre jeton. Ensuite, chaque
connexion nouvelle reçoit son jeton comme mot de passe, par une fonction que psycopg appelle à chaque fois :

```python
    def with_token() -> dict[str, Any]:
        """The parameters of one new connection, its token asked for now."""
        try:
            token = entra.fetch_database_token(credential)
        except entra.EntraTokenError:
            raise DatabaseNoTokenError(entra.DATABASE_NO_TOKEN) from None
        return {"connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS, "password": token}
```
(`src/k_b/database/postgresql.py:205-211`)

Le pool de l'API de données reçoit cette même fonction (`kwargs=make_connection_parameters(location)`,
`postgresql.py:254`) : `psycopg_pool` accepte un `kwargs` appelable, évalué à chaque connexion qu'il ouvre. Un
jeton vit environ une heure, et le `max_lifetime` par défaut du pool (3 600 s) borne la vie d'une session.

Le jeton est demandé par `ManagedIdentityCredential` pour la portée de PostgreSQL :

```python
POSTGRESQL_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"  # noqa: S105 — a scope, not a token
```
(`src/k_b/database/entra.py:19`)

Tout échec devient `database_no_token`, sans le texte d'azure-identity, qui peut citer la réponse du point
d'identité (`entra.py:56-59`). `DatabaseNoTokenError` hérite de `psycopg.OperationalError` : chaque commande
l'attrape déjà par `except ENGINE_ERRORS`, sans code nouveau.

### 2.3 Trois rôles, posés par l'administratrice et vérifiés par le serveur

La base `kb` et les rôles ne viennent pas du Bicep, mais de deux scripts SQL lancés une fois par
l'administratrice Entra du serveur (Sabine). `create-principals.sql` rattache chaque rôle à son identité par
l'**identifiant de son principal**, pas par son nom, qu'une autre identité de l'annuaire peut porter.
`grant-roles.sql` pose les droits :

```sql
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO kb_reader, kb_writer, "id-kb-migrate-database"',
        current_database()
    );
```
(`infra/postgresql/grant-roles.sql:46-50`)

Par défaut, PostgreSQL donne `CONNECT` et `TEMPORARY` à `PUBLIC`, c'est-à-dire à tout rôle. Le script les
retire, puis rend `CONNECT` aux seuls trois rôles. Il retire aussi `CREATE` sur `public`
(`grant-roles.sql:54`) : sur Azure, tout rôle peut y créer des objets. `id-kb-data-api` n'entre que dans
`kb_reader`, qui n'a que `SELECT` (`src/k_b/database/grants_postgresql.sql:6`). Le refus d'écrire est donc
celui du serveur, pas celui du code de l'API.

Le script commence par `SET search_path = pg_catalog;` (`grant-roles.sql:17`). Le rôle du job peut créer des
fonctions dans `public`. Si l'une d'elles correspondait mieux à un appel du script que celle de `pg_catalog`
(par exemple un `public.format(text, name)`), elle s'exécuterait avec les droits de l'administratrice : c'est le
schéma de la CVE-2018-1058, relevé par la revue de sécurité (S1). Chaque `psql` du README passe aussi par
`admin_psql`, qui pose `PGOPTIONS='-c search_path=pg_catalog'`.

### 2.4 `kb migrate-database` : créer si absente, sinon ne rien écrire

```python
    connection = connect_database(location)
    try:
        if has_its_tables(connection):
            return False
        write_postgresql_schema(connection)
        connection.executescript(
            DATABASE_SCRIPTS.joinpath("grants_postgresql.sql").read_text()
        )
        connection.commit()
```
(`src/k_b/database/creation.py:97-105`)

`has_its_tables` vérifie d'abord les réglages de la base (UTF8, collation C), puis demande
`to_regclass('source') IS NOT NULL` (`creation.py:21`, `112-116`). Si la table `source` existe, rien n'est
écrit et la commande dit `database unchanged`. Sinon, le schéma, les sept sources et les droits sur les tables
sont écrits dans **une seule transaction** : le DDL de PostgreSQL est transactionnel, et un échec ne laisse rien
à moitié. Les droits sont posés par le propriétaire des tables, le rôle du job, au moment où il les crée.

La commande est dans `COMMANDS_STOPPED_BY_SIGTERM` (`src/k_b/commands/sigterm.py:28`) : un SIGTERM pendant la
transaction l'annule, et le code de sortie est nommé.

### 2.5 Le serveur et le job, en Bicep, branchés après #414

Le serveur est décrit dans son propre module :

```bicep
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
```
(`infra/modules/postgresql-server.bicep:27-31`)

Le module du job crée l'identité `id-kb-migrate-database` et son AcrPull à chaque passe, et le job seulement à
la seconde (`resource job … = if (deployJob)`, `infra/modules/migrate-database-job.bicep:58`). La raison :
`create-principals.sql` a besoin du principal de l'identité avant le premier lancement du job.

Dans `main.bicep`, les deux URL partagent les mêmes options TLS :

```bicep
var databaseUrlOptions = 'sslmode=verify-full&sslrootcert=/etc/ssl/certs/ca-certificates.crt'
```
(`infra/main.bicep:252`)

`sslrootcert` désigne le magasin de certificats de l'image, vérifié avant le premier lancement : `openssl` rend
`Verify return code: 0 (ok)` contre le fichier extrait de `k-b:3abd525`.

Pour l'API de données, une ligne de plus a été nécessaire :

```bicep
    identityLifecycle: 'Main'
```
(`infra/main.bicep:164`, paramètre de `infra/modules/api-container-app.bicep:26`)

Le module de #414 réglait l'identité des API à `lifecycle: 'None'`. Avec ce réglage, l'identité sert à tirer
l'image et à lire le coffre, mais le code du conteneur ne peut pas obtenir de jeton : chaque connexion aurait
échoué en `database_no_token` (constat R1 de la revue de code). `'Main'` est réservé à l'API de données ; l'API
IA garde `'None'`.

## 3. Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Authentification | Entra seul, un jeton par connexion (décision 2) | Un mot de passe dans le Key Vault : un secret à garder et à faire tourner (décision 2) |
| Brancher le jeton | Un `kwargs` appelable de `psycopg_pool` et de `psycopg.connect` | La sous-classe de `psycopg.Connection` de l'exemple de Microsoft : plus de code pour le même effet |
| Choisir Entra | Une variable explicite, `KB_DATABASE_AUTH` | Déduire Entra d'`AZURE_CLIENT_ID` ou d'`IDENTITY_ENDPOINT` : implicite |
| Certificat du serveur | Le magasin de l'image (`sslrootcert=/etc/ssl/certs/…`) | `sslrootcert=system`, qui dépend de la libssl embarquée par psycopg-binary ; un certificat versionné, à suivre à chaque rotation d'Azure |
| Création de la base et des rôles | En SQL, par l'administratrice, une fois | Par le Bicep, dont la doc ne dit pas qu'il pose `LC_CTYPE` |
| Droits sur les tables | Posés par leur propriétaire, dans la transaction qui les crée | L'identité du job administratrice Entra (membre d'`azure_pg_admin`, bien au-delà du DDL) ; `ALTER DEFAULT PRIVILEGES`, utile seulement à une table ajoutée plus tard (#186) |
| Deux migrations à la fois | Aucun verrou : la seconde échoue (23505 sur `pg_type`), rien n'est écrit à moitié, la relance dit `unchanged` | Un verrou consultatif ; le verrou d'une seconde commande `kb` est #426 |
| Délai par requête | Le `SET` de session de #418, pas de PgBouncer (B1ms n'en a pas d'intégré) | `ALTER ROLE … SET statement_timeout`, écarté par #418 (la valeur hors du dépôt) |
| Jeton de l'API | `lifecycle: 'Main'` pour l'API de données seule (Sabine, 06/11) | Une seconde identité réservée à la base : une identité, un rôle et du SQL de plus pour un gain presque nul |
| Base `postgres` | Laissée ouverte, limite acceptée par Sabine (S2) ; le critère 3 la lit | La fermer dans #421 : sans données de K-B, le risque est un disque rempli |
| Image de l'application | Construite depuis la branche rebasée, étiquetée par son SHA (Sabine, option A) | Depuis `main` après la fusion : les critères n'auraient été vérifiés qu'après coup |

Choix imposés par les règles du dépôt :

- les journaux ne citent jamais l'URL ni le texte de libpq (règle 3 de `conventions.md`) ;
- `log_error_verbosity = TERSE` sur le serveur retire le `DETAIL` qui recopierait une ligne refusée, auteur
  compris (règle 5 de `poc.md`) ;
- le transport et l'identifiant client sont écrits une seconde fois, après `jobs/exchange_storage.py`, parce que
  `database/` ne peut pas importer les jobs (règle 5 de `conventions.md`) ;
- les tests d'abord : chaque correction des revues a son commit `test:` rouge avant son `fix:`.

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_under_entra_a_url_that_could_give_the_token_away_is_refused_before_any_token` (`tests/database/test_postgresql.py`) | Sans `verify-full`, ou avec un mot de passe, aucun jeton n'est demandé |
| `test_under_entra_the_pool_asks_a_token_for_each_connection_it_opens` | Le pool demande un jeton par connexion nouvelle |
| `test_under_entra_an_identity_without_token_is_a_named_error_of_the_base` | Un jeton refusé devient `database_no_token`, une erreur de la base |
| `test_an_identity_that_gives_no_token_is_named_without_what_it_answered` (`tests/database/test_entra.py`) | Le texte d'azure-identity n'apparaît jamais |
| `test_kb_database_auth_entra_without_kb_database_url_is_refused` (`tests/database/test_location.py`) | Le job en ligne ne crée jamais de base SQLite |
| `test_kb_migrate_database_run_twice_creates_the_postgresql_base_then_changes_nothing` | Le second lancement n'écrit rien |
| `test_the_data_api_writes_nothing_in_the_base` (`tests/database/test_grants.py`) | `kb_reader` est refusé en écriture, sur le serveur de test |
| `test_grant_roles_sql_runs_no_function_the_job_created_in_public` | Le piège de la CVE-2018-1058 ne s'exécute pas |
| `test_a_sigterm_during_kb_migrate_database_leaves_no_base_and_exits_with_its_code` | SIGTERM annule la création |
| `uv run pytest` 3707 passed, `-m postgresql` 317 passed ; ruff, format, mypy ; `az bicep build` et `lint` sans avertissement | Les contrôles du dépôt sont verts |
| En ligne : deux lancements `Succeeded`, l'empreinte `15\|d4bd76ded10713228410326253171525\|7` avant et après le second, puis `database created` et `database unchanged … already has its tables` dans `log-kb` | Critère 1 |
| En ligne : `authConfig` rend `passwordAuth: Disabled` et `activeDirectoryAuth: Enabled` | Critère 2 |
| En ligne : catalogue de `kb` `t\|f\|f\|f` ; dans `ca-kb-data-api`, `SELECT (7,)`, puis `REFUSED INSERT InsufficientPrivilege 42501` et `REFUSED CREATE InsufficientPrivilege 42501` | Critère 3 : l'API ouvre la base par son jeton et ne peut pas écrire |
| En ligne : `SHOW search_path` rend `pg_catalog` ; `openssl` rend `Verify return code: 0 (ok)` contre le magasin de l'image | L'administration est protégée sur Azure ; le job peut joindre la base en `verify-full` |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi pas un mot de passe, rangé dans le Key Vault ?** Un mot de passe est un secret de longue durée, à
   garder, à faire tourner, qui peut fuiter. Avec Entra, chaque connexion présente un jeton d'environ une heure,
   obtenu par l'identité managée, et le serveur refuse tout mot de passe (`postgresql-server.bicep:27-31`, vérifié
   en ligne).
2. **Que se passe-t-il si quelqu'un met une URL sans `verify-full` ?** K-B refuse la commande avant de demander un
   jeton (`postgresql.py:161-192`). Sans vérification du certificat, libpq enverrait le jeton à un serveur qui se
   ferait passer pour celui de K-B.
3. **Comment sais-tu que l'API ne peut pas écrire, même si son code avait un défaut ?** Le refus vient du
   serveur : `id-kb-data-api` n'est membre que de `kb_reader`, qui n'a que `SELECT`, et `PUBLIC` n'a plus rien
   (`grant-roles.sql:46-58`). En ligne, un `INSERT` et un `CREATE TABLE` lancés depuis le conteneur de l'API ont
   été refusés en 42501.
4. **Que fait `kb migrate-database` sur une base qui existe déjà, ou plus récente ?** Il lit seulement : si
   `source` existe, il rend `unchanged` et n'écrit rien (`creation.py:97-100`). Un retour en arrière par tag est
   donc sans effet sur la base. La compatibilité du schéma avec la version d'avant relève de #186.
5. **Pourquoi `search_path = pg_catalog` dans l'administration ?** Le rôle du job peut créer des fonctions dans
   `public`. Sans cela, l'une d'elles pourrait s'exécuter avec les droits de l'administratrice (CVE-2018-1058).
   Un test pose un `public.format(text, name)` piégé et vérifie qu'il ne s'exécute pas.

## 6. Zones non vérifiées

- **`create-principals.sql`** n'a pas de test automatique : `pgaadauth_create_principal_with_oid` n'existe que
  sur Azure. Il a tourné une fois en ligne, sans erreur.
- **La survie d'une session à l'expiration de son jeton** : aucune source officielle ne la décrit.
  `max_lifetime` (3 600 s) la borne.
- **La latence d'un échec de jeton** : les nouvelles tentatives d'azure-core l'allongent (environ 45 s, estimé,
  pas mesuré).
- **Les journaux du serveur** : je n'ai vérifié ni la valeur par défaut d'Azure pour
  `log_parameter_max_length_on_error`, ni ce qu'Azure garde des journaux du serveur, ni combien de temps.
- **L'accès de l'administratrice à `postgres`** : on ne sait pas si elle y entre par le seul `CONNECT` de
  `PUBLIC`. C'est la raison de « jamais `CONNECT` » dans l'issue de suite.
- **Le coût** : environ 0,022 €/h, d'après la liste publique des prix (France Central). Ce n'est pas le prix
  de l'abonnement, et la part des sauvegardes comprise dans le prix n'est pas vérifiée.
- **Les aperçus `what-if`** contiennent du bruit (valeurs par défaut renvoyées par Azure, sondes permutées,
  `reference(…)` non résolus). Je l'ai trié à la lecture, pas par un outil.

## 7. Ce qui reste

- **L'étape `caj-kb-migrate-database` dans la livraison continue**, entre l'envoi de l'image et la mise à jour
  des apps. Elle vient avec #415 (tn-codeur) si #421 est fusionnée avant, sinon par une petite PR de suite.
  Jusque-là, le job se lance à la main.
- **L'amorçage de la base et la routine quotidienne (#330)** : le membre `id-kb-daily-routine` de `kb_writer` et
  son `GRANT`.
- **Les migrations (#186)** : une table ajoutée à la base en ligne n'aura de droits que par une migration, et
  la compatibilité du schéma avec la version d'avant arrive avec le premier changement.
- **L'issue nouvelle décidée par Sabine le 06/11** :
  - le 503 `database_unavailable` sur `PoolTimeout` ;
  - une ligne qui nomme la cause d'un échec de connexion du pool ;
  - le coût de `check_connection` sur Azure ;
  - `kb import` sur une base sans tables ;
  - `check_database_exists`, qui ne vérifie rien sur PostgreSQL ;
  - l'entrée `psycopg_pool` de `LIBRARY_LOG_LEVELS`, qui vise le mauvais logger ;
  - une route `/health/database`.
- **La base `postgres`** : `TEMPORARY` reste à `PUBLIC` (`t|f|azure_pg_admin` en ligne). L'issue de suite le
  révoquerait, sans jamais toucher à `CONNECT`.
- **Le verrou PostgreSQL d'une seconde commande `kb` (#426).**

Commits non décrits un par un : ceux de documentation (`.env.example`, `MEMORY.md`, registre, journal ADR,
`infra/README.md`). Leur contenu est repris dans les sections 1, 3 et 7.
