# Créer le stockage des jobs et des échanges avec le Mac

- **Date** : 2026-11-10
- **Branche** : `feat/storage-accounts-and-roles`
- **Issue** : #420
- **Fichiers principaux** : `infra/modules/exchange-storage.bicep`, `infra/modules/job-files-storage.bicep`
  (nouveau), `infra/modules/container-apps-environment.bicep`, `infra/main.bicep`, `infra/README.md`
  (« Le stockage (#420) »), `docs/registre-traitements.md`
- **Série** : suit [Mettre en ligne le squelette sur Azure](2026-11-06-mettre-en-ligne-le-squelette-sur-azure.md)
  et [`kb smoke-test`, les API et le stockage d'échange](2026-11-06-kb-smoke-test-api-et-stockage-d-echange.md).

Tous les commits de la branche sont couverts. Deux d'entre eux ne laissent rien dans le code final : le commit
d'essai, qui écrit la sonde dans `caj-kb-smoke-test`, et son revert. Ils sont décrits plus bas, dans « La sonde ».

## Le pourquoi

En ligne, les jobs de K-B (`kb daily-routine`, `kb digest-watch`, #330) ont besoin d'un dossier qui dure d'une
exécution à l'autre : le brut, l'état et le coffre de travail. Le Mac, lui, n'est plus qu'un lieu de lecture dans
Obsidian. Il n'échange avec Azure que par des dossiers à sens unique : les clips et la base Zotero montent, les
fiches de veille descendent. Ce sens doit être verrouillé, de sorte qu'une synchronisation à l'envers échoue au lieu
d'écraser des données.

Cette PR crée ces lieux et leurs protections, rien de plus. Elle n'ajoute aucun code Python. Les jobs qui monteront
le partage arrivent avec #330, et les commandes du Mac avec #424. Les critères de l'issue demandent pourtant
d'écrire sous l'identité d'un job qui n'existe pas encore : d'où la sonde.

## Le comment

### Deux comptes, deux usages

`stkbexchange…` (Blob, né avec #414) reçoit trois conteneurs d'échange. `stkbjobfiles…` (Files, nouveau) porte le
partage `job-data`, que le Mac ne touche jamais (décision 3 de Sabine du 06/11).

```bicep
var exchangeContainerNames = [
  'clippings'
  'zotero'
  'watch'
]
```
`infra/modules/exchange-storage.bicep:90-94`

Il n'y a pas de conteneur `wiki` : aucune identité ne pourrait y écrire, et l'ingest du wiki sur Azure reste #170.

### Le sens tenu par les rôles, un par identité et par conteneur

Chaque droit est une ligne d'un tableau. Il n'y a aucun rôle sur le compte entier.

```bicep
  {
    container: 'watch'
    principal: 'dailyRoutine'
    roleId: blobDataContributorRoleId
  }
```
`infra/modules/exchange-storage.bicep:148-152`

Le tableau compte sept lignes. `id-kb-daily-routine` lit `clippings` et `zotero`, et écrit `watch`.
`id-kb-digest-watch` écrit `watch`. Sabine écrit `clippings` et `zotero`, et lit `watch`. Les API et
`id-kb-migrate-database` n'ont rien. Comme la clé partagée est coupée (`allowSharedKeyAccess: false`), aucun autre
chemin n'existe : écrire à contresens répond 403.

Les identités sont décrites par deux tables (`exchange-storage.bicep:118-136`), et non par une seule :

```bicep
var principalKeys = {
  dailyRoutine: dailyRoutineIdentity.id
  digestWatch: digestWatchIdentity.id
  operator: operatorObjectId
}
```
`infra/modules/exchange-storage.bicep:118-122`

La raison vient de Bicep. Le nom d'un rôle doit être calculable dès le début du déploiement, alors que le
`principalId` d'une identité n'est connu qu'une fois l'identité créée. En mêlant les deux dans un même objet, on
obtient l'erreur BCP120. `principalKeys` sert donc au nom, par `guid(conteneur.id, clé, rôle)`, et `principals` sert
aux propriétés (`exchange-storage.bicep:175-189`).

### Les protections de `stkbexchange`

Les versions et la suppression réversible sont posées sur le service Blob :

```bicep
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: softDeleteDays
```
`infra/modules/exchange-storage.bicep:52-55`

- **Les versions.** Chaque écrasement ou suppression garde la version précédente (décision 6 du 06/11). Personne
  n'a Storage Blob Data Owner, le seul rôle qui efface une version.
- **La suppression réversible**, de 30 jours, vaut pour les blobs comme pour les conteneurs. C'est la seule parade
  à un `clippings` supprimé par erreur.

Les copies de Zotero sont effacées par une règle de cycle de vie (`exchange-storage.bicep:192-232`) :

```bicep
              prefixMatch: [
                'zotero/'
              ]
```
`infra/modules/exchange-storage.bicep:209-211`

- **Le préfixe.** Il commence par le nom du conteneur ; sans lui, la règle toucherait aussi `clippings`, que rien
  n'efface (Sabine, 04/11).
- **Les deux actions.** La règle efface la copie à 14 jours (`baseBlob.delete`), et sa version précédente aussi
  (`version.delete`). Sans la seconde action, chaque copie effacée resterait en version précédente, sans fin.

Enfin, un verrou `CanNotDelete` protège chaque compte (`exchange-storage.bicep:237-244`).

### Le montage de `job-data` par l'identité système de l'environnement

Un job de Container Apps ne monte pas un partage avec sa propre identité. C'est l'**environnement** qui le monte,
avec la sienne. `cae-kb` reçoit donc une identité système :

```bicep
  identity: {
    type: 'SystemAssigned'
  }
```
`infra/modules/container-apps-environment.bicep:13-15`

Cette identité reçoit le rôle Storage File Data SMB MI Admin, à la portée du compte, la seule que Microsoft accepte
pour ce rôle (`job-files-storage.bicep:73-81`). Le compte autorise le SMB par jeton OAuth, sans Active Directory :

```bicep
    azureFilesIdentityBasedAuthentication: {
      directoryServiceOptions: 'None'
      smbOAuthSettings: {
        isSmbOAuthEnabled: true
```
`infra/modules/job-files-storage.bicep:38-41`

Le lien entre l'environnement et le partage est un « stockage d'environnement ». Il n'accepte une identité que dans
une préversion de l'API :

```bicep
resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2026-03-02-preview' = {
```
`infra/modules/job-files-storage.bicep:89`

Il porte `identity: 'system'` (`:97`) et dépend du rôle (`dependsOn: [smbMiAdmin]`, `:102-104`). Cette dépendance
attend la création du rôle, pas son activation, qui prend jusqu'à 10 minutes. Si ce PUT échoue, on relance la même
passe 10 minutes plus tard (`infra/README.md`, première passe et section #420). Le 10/11, il est passé du premier
coup. `main.bicep:125-134` passe le `principalId` de l'environnement au module : le même déploiement crée
l'environnement, puis le rôle, puis le stockage.

### La sonde : un essai dans `caj-kb-smoke-test`, puis son retrait

Les critères demandent d'écrire sous `id-kb-daily-routine`, partage monté, alors que le job de la routine n'existe
pas encore. Une exécution de job ne peut changer ni ses identités ni ses volumes, et sa surcharge remplace tout le
modèle. La sonde a donc été écrite **dans le modèle** de `caj-kb-smoke-test`, le temps d'un commit d'essai :

```python
if not os.path.ismount(root):
    failures.append("job-data is not mounted")
```
`git show f10e5e3:infra/modules/smoke-test-job.bicep`, ligne 66

Elle échoue si le partage n'est pas monté. Elle appelle deux fois `write_file_atomically` au même chemin (`:72-73`,
le remplacement d'un fichier existant), puis tente d'écrire dans `clippings`, où le 403 est attendu, et dans `watch`
(`:87`, `:94`). Le volume y était monté avec les options de l'utilisateur de l'image (`:173`) :
`uid=10001,gid=10001,dir_mode=0700,file_mode=0600`.

Le revert du commit, puis une seconde passe, ont rendu au job son modèle de `main`. Tant que la sonde était en ligne,
aucune exécution du workflow Deploy n'était permise : `id-kb-deploy` peut lancer le job, et donc agir sous
`id-kb-daily-routine`.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| L'identité **système** de `cae-kb` | Liée à l'environnement, elle ne peut être attachée ailleurs ; une ressource de moins (constat 15 de la relecture du plan, choix de la session) | Une identité attribuée par l'utilisateur (`id-kb-<pièce>`) : un Contributor pourrait l'attacher à une autre ressource, qui aurait l'accès SMB admin à tout le compte |
| La clé partagée coupée aussi sur `stkbjobfiles`, sans repli codé | Choix B de Sabine (10/11) : un repli jamais essayé ne prouve rien ; l'essai a montré que le montage s'en passe | Le montage par la clé (`listKeys()`, paramètre `filesAuth`), demandé par Sabine le 06/11 en repli : devenu inutile |
| Un rôle par identité et par conteneur | Le verrou de sens (décision 4 du 06/11) | Un rôle sur le compte : il ouvrirait tous les conteneurs |
| `CanNotDelete` | Contre l'erreur de manipulation | `ReadOnly` : il bloquerait les attributions de rôle |
| Les instantanés de `job-data`, 7 jours au plus, à la main | Choix C (a) de Sabine (10/11) : revenir sur une mise en production ratée, ce qui se voit en un ou deux jours | Aucun instantané (rien ne protège le brut fichier par fichier) ; Azure Backup (un coffre, un coût, et le même écart à la règle des 6 mois) |
| La sonde dans le modèle du job d'essai | Choix A de Sabine (10/11) : une exécution ne change ni identités ni volumes | Reporter ces essais à #330 : le critère changeait, et le choix B se tranchait trop tard |
| Le partage en `TransactionOptimized`, quota de 100 Gio | Beaucoup de petites écritures (`write_file_atomically`) ; le quota est un plafond, seul l'espace utilisé est facturé | Aucun autre essayé |
| `publicNetworkAccess: 'Enabled'` | Un environnement sans VNet n'atteint que des points de terminaison publics, et le Mac aussi (#424) | Un point de terminaison privé : il demande un VNet (décision 1 du plan du 06/11) |

Le risque d'accès des tiers de l'organisme (choix D) a été accepté par Sabine le 10/11 et écrit au registre, ligne
« Droits d'accès ».

## Preuve

Toutes ces sorties ont été observées le 10/11, par des commandes lancées par Sabine.

| Sortie observée | Ce que ça démontre |
|---|---|
| Depuis le Mac, l'envoi dans `watch` est refusé (message de rôle de `az`, un 403) ; l'envoi dans `clippings` rend une `version_id` | Le sens est tenu pour Sabine ; les versions sont actives |
| `az storage account list … allowSharedKeyAccess` : `False` sur les deux comptes | Aucun accès par la clé |
| La sonde : `Succeeded` en 38 s ; `process uid 10001 gid 10001` ; `mount uid=10001 gid=10001 mode=0o700` ; `file uid=10001 gid=10001 mode=0o600` ; `clippings 403 AuthorizationPermissionMismatch` ; `watch written, then deleted` ; `passed` | Le montage par identité passe, clé coupée ; les options de montage tiennent ; l'écriture atomique marche pour l'utilisateur non root ; le sens est tenu pour la routine |
| `az lock list` : deux `CanNotDelete` | Les verrous sont en place |
| `blob-service-properties` : `True`, `30`, `30` ; `management-policy` : `erase-zotero-copies`, `zotero/`, `14`, `14` ; `file-service-properties` : `True`, `30` | Les versions, la suppression réversible et la règle Zotero sont en place |
| Après le revert et la seconde passe, `az containerapp job show` donne une seule identité (`id-kb-smoke-test`), pas de volume, pas de commande, `args` `smoke-test` | La sonde est retirée d'Azure |
| `caj-kb-smoke-test` repasse : `Succeeded` en 84 s | `kb smoke-test` ne sort à 0 que si ses trois vérifications passent (`src/k_b/commands/smoke_test_command.py:94-96`) |
| `az bicep build` et `az bicep lint` sans erreur | Le Bicep compile |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une sync à l'envers échoue-t-elle, plutôt que d'écraser ?** La clé partagée est coupée, donc seul
   Entra donne accès, et chaque identité n'a de droit d'écriture que sur son conteneur de sortie. Une écriture dans
   un conteneur où elle n'est que lectrice répond 403 `AuthorizationPermissionMismatch` : on l'a vu pour la routine
   et pour Sabine (`exchange-storage.bicep:137-173`).
2. **Pourquoi le job ne monte-t-il pas le partage avec sa propre identité ?** Container Apps monte un partage au
   niveau de l'environnement, par l'identité de l'environnement (`job-files-storage.bicep:89-103`). C'est aussi la
   limite : toute app ou tout job de `cae-kb` qui déclare le volume monte le partage. La protection est une
   convention, pas un contrôle : seuls les jobs de #330 le déclareront.
3. **Et si on veut effacer la donnée d'une personne qui en fait la demande ?** Il faut aussi effacer ses versions et
   ses instantanés. Une version ne s'efface qu'avec Storage Blob Data Owner, que personne n'a : il faut un rôle
   temporaire, verrou levé, puis le retrait des deux (registre, procédure de tri, étape 5 ; `infra/README.md`,
   « Le verrou : le lever, agir, le reposer »).
4. **Pourquoi deux tables pour les identités ?** C'est une contrainte de Bicep (BCP120) : le nom d'un rôle doit être
   connu au début du déploiement, le `principalId` ne l'est qu'après (`exchange-storage.bicep:114-136`).
5. **Comment sais-tu que la sonde ne traîne plus en ligne ?** Le revert dans git ne suffit pas : il a fallu une
   seconde passe, puis `az containerapp job show`, qui ne montre plus que `id-kb-smoke-test`, sans volume ni
   commande.

## Zones non vérifiées

- **La préversion `2026-03-02-preview`** du stockage d'environnement est la seule qui accepte une identité. Elle
  peut changer avant de devenir stable.
- **Les options de montage** (`uid`, `gid`, modes) avec un montage par identité ne sont pas décrites par la doc de
  Microsoft. Elles ont tenu lors d'un seul essai, le 10/11.
- **La relance de la première passe sur un groupe neuf** n'a jamais été essayée : le 10/11, le stockage
  d'environnement est passé du premier coup sur le squelette existant.
- **Le calendrier de la règle Zotero** vient de la doc, lue le 10/11 par le relecteur de time-knight : un passage
  par jour, sans heure garantie ; la copie part à un passage, sa version précédente au suivant, puis 30 jours de
  suppression réversible, environ 46 jours. Aucune copie Zotero n'existe encore pour l'observer.
- **Les instantanés et le geste « lever le verrou, agir, le reposer »** sont écrits dans le README, mais non lancés :
  aucun instantané n'est pris dans #420, puisque le partage est vide.
- **Kerberos reste permis par défaut** sur le compte. Que `SMBOAuth` ne l'active ni ne le contrôle vient de la
  doc, non essayé.
- **Que `id-kb-deploy` puisse ajouter le volume à une API** est possible d'après la doc, non essayé (registre,
  « Déploiement continu »).

## Ce qui reste

- **#330** : le job `caj-kb-daily-routine`, qui monte `job-data` sur `/var/lib/knowledge_base`, l'amorçage, et le
  premier instantané. Il reste aussi à corriger `poc.md:101`, qui dit encore `/data`.
- **#424** : les commandes du Mac (`make upload-library`, `make download-watch-sheets`).
- **#535** : nommer les rôles du Bicep par leur `principalId`, pour qu'une identité recréée sous le même nom ne
  bloque pas la passe. Le défaut est le même sur `main`.
- **#170** : un conteneur `wiki`, avec un vrai ingest du wiki sur Azure.
- **#428** : la suppression des ressources, qui demandera de lever les verrous.
- **La limite assumée des versions** : les clips et les fiches gardent leurs versions sans limite, contre le
  critère 1.6 du RGESN (registre).
