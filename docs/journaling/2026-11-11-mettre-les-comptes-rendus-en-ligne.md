# Mettre les comptes rendus en ligne

- **Date** : 2026-11-11
- **Branche** : `feat/digest-watch-job`
- **Issue** : #423
- **Fichiers principaux** : `infra/modules/digest-watch-job.bicep` (nouveau), `infra/main.bicep`,
  `infra/deployment.json`, `infra/modules/deploy-access.bicep`, `infra/README.md` (« Les comptes rendus en ligne
  (#423) », « La règle des heures »), `docs/registre-traitements.md`, `docs/ADR/journal-decisions-projet.md`
- **Série** : suit [Mettre la routine quotidienne en ligne](2026-11-10-mettre-la-routine-quotidienne-en-ligne.md)
  (#330), dont ce job reprend le modèle.

Tous les commits de la branche sont couverts (hachages après le rebase sur `main` à 94e7b2d). `b673ea8` écrit le job,
et `5fd1989`, `b561f33`, `a6c7e6e` et `f129348` le documentent (README d'infra, autres docs, registre, ADR). `0a5b5e1`
applique le tri des revues, `adcaf64` corrige une référence de ligne, `eef1848` écrit les faits de la première
exécution, et la note vient en dernier. Les docs se retrouvent dans « Choix
faits » et « Preuve ».

## Le pourquoi

Le produit minimum du 25/11, ce sont la veille et les tendances, qui tournent seules en ligne. Depuis #330, la
routine quotidienne collecte et importe chaque jour à 08:00 UTC, et écrit les fiches des tops. Les comptes rendus,
eux, demandent le modèle : `kb digest` (un compte rendu par sujet) et `kb trend-report` (celui des tendances de GH
Archive). Jusqu'ici, ils ne tournaient que sur le Mac. Sabine : « KB en ligne ne doit pas faire tourner digest ou autre
en local ».

La commande existait déjà : `kb digest-watch` (#413) réveille les deux API, lance `kb digest`, les réveille de
nouveau, lance `kb trend-report`, puis publie `veille/` dans le conteneur `watch`. Il manquait le job qui la lance en
ligne, deux fois par semaine, avec ses droits, ses secrets et son dossier de données. C'est tout le travail de #423 :
de l'infrastructure, sans une ligne de Python.

## Le comment

### Un job planifié, sans reprise

```bicep
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      // kb waits 240 s at most for each of its two requests and 65 s for each of the four wakes (core/config.py):
      // 740 s, then the publication, under 1 800 s unless the storage is slow.
      replicaTimeout: 1800
      // No retry (#423): after a timeout on the side of kb, a second run would call the model again. kb digest and kb
      // trend-report refuse only when the report of the day exists, which a cut run may not have written.
      replicaRetryLimit: 0
```
(`infra/modules/digest-watch-job.bicep:65-74`)

Un job `Schedule` d'Azure Container Apps démarre un conteneur à l'heure du cron, lu en UTC. Il fait tourner une seule
réplique (`parallelism: 1`), et l'exécution réussit quand elle sort en 0. Le délai, 1 800 s, se calcule depuis les
bornes de `kb` : 240 s au plus pour chacune des deux demandes à l'API IA, 65 s pour chacun des quatre réveils. Cela
fait 740 s, plus la publication.

**Aucune reprise** : si `kb` abandonne une demande après 240 s, l'API IA peut encore être en train d'appeler le
modèle. Une reprise redemanderait tout, donc paierait un second appel. Et elle ne serait pas toujours refusée : `kb
digest` ne refuse que si une fiche du jour existe déjà.

### L'heure : un paramètre de l'infra

```bicep
param digestWatchCronExpression string = '0 10 * * 1,4'
```
(`infra/main.bicep:32`, passé au module par `infra/main.bicep:341`)

Le lundi et le jeudi à 10:00 UTC : les jours viennent de l'issue, l'heure de la routine, qui finit à 09:00 UTC au plus.
Sabine a voulu ce cron « en paramètre de l'infra, pas en dur ». Le module le reçoit sans défaut
(`digest-watch-job.bicep:12`). `main.bicep` le déclare avec un défaut : une passe qui ne le donne pas, la CI comprise,
garde le rythme décidé. Pour changer d'heure, on ajoute `digestWatchCronExpression='…'` aux paramètres d'une passe,
sans toucher au code. La `@description` du paramètre dit l'heure à éviter, celle de la routine.

### Le partage `job-data`, monté à la racine

```bicep
            {
              volumeName: 'job-data'
              mountPath: dataDir
            }
```
(`infra/modules/digest-watch-job.bicep:105-108`, avec les options de montage de la routine à la ligne `118`)

Sans partage, le conteneur repartirait vide à chaque exécution, et deux choses casseraient :
- `kb trend-report` garde dans `KB_DATA_DIR` le registre de ses comptes rendus, `trend_reports.json`
  (`post/trend_report_registry.py:26`). C'est ce registre qui lui fait demander « les fenêtres d'après le compte rendu
  précédent ». Vide, il redemanderait tout à chaque fois.
- `kb digest` et `kb trend-report` cherchent dans le coffre le compte rendu du jour, et refusent de redemander s'il
  existe.

Le job monte donc le même partage que la routine, à sa racine. Il voit ainsi le même coffre, et la publication
quotidienne de la routine rattrape une fiche que ce job n'aurait pas envoyée. Le prix : il voit aussi le brut, l'état
de la collecte et les journaux de la routine, que ses étapes ne lisent pas. Sabine l'a validé le 11/11. La parade, un
montage de sous-dossiers par `subPath`, est écrite au registre, sans être appliquée.

### Deux clés reprises, aucun secret nouveau

```bicep
var digestWatchSecretVariables = {
  KB_AI_API_KEY_KB_DIGEST: aiApiSecretVariables.KB_AI_API_KEY_KB_DIGEST
  KB_AI_API_KEY_KB_TREND_REPORT: aiApiSecretVariables.KB_AI_API_KEY_KB_TREND_REPORT
}
```
(`infra/main.bicep:175-178`, et leurs rôles aux lignes `198-201`)

Pour appeler l'API IA, `kb` présente une clé par client : `KB_DIGEST` pour `kb digest`, `KB_TREND_REPORT` pour `kb
trend-report`. L'API IA les vérifie déjà, et elles sont déjà dans le Key Vault. Le job les reçoit sous le même nom de
variable que sur le Mac. Chaque nom n'est écrit qu'une fois : on le reprend de la table de l'API IA, si bien qu'une
faute de frappe ne peut pas faire sortir la commande en 2.

L'identité du job, `id-kb-digest-watch`, reçoit Key Vault Secrets User sur ces deux secrets seulement, et AcrPull sur
le registre. Elle n'a aucun rôle sur la base : `kb digest-watch` lit la veille par les deux API. Sur `watch`, elle avait
déjà Storage Blob Data Contributor depuis #420.

### Le déploiement continu suit le job

Le job entre dans `infra/deployment.json`. Chaque tag change donc aussi son image, et `id-kb-deploy` reçoit Container
Apps Jobs Contributor sur lui. Ce rôle permet d'agir sous l'identité du job et d'en lire les secrets
(`listSecrets`). Ce n'est pas un accès nouveau :
- `watch` et `job-data` lui sont déjà ouverts par la routine ;
- les deux clés, aussi : Container Apps Contributor sur `ca-kb-ai-api` lui permet de changer cette app, donc
  d'exécuter du code sous `id-kb-ai-api`, qui lit ces mêmes clés.

Le commentaire de `infra/modules/deploy-access.bicep:1-8` le dit.

### La règle des heures

Rien ne tient deux exécutions à l'écart l'une de l'autre, sauf une consigne écrite au README d'infra. Le verrou de
#426 ne couvrira que les commandes qui touchent la base. Le risque visé : `kb import` qui écrit la base pendant que
l'API de données la lit page par page pour un compte rendu.

D'où, avec 5 minutes de marge pour le démarrage :
- la routine à la main ne démarre jamais entre 06:55 et 09:00 UTC, ni jusqu'à 10:35 le lundi et le jeudi ;
- `kb digest-watch` à la main ne démarre jamais le lundi ni le jeudi avant la fin du cron. Ses fiches du jour
  feraient refuser le cron, qui finirait `Failed`.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un module à part, `digest-watch-job.bicep` | Le modèle de la routine, sans la clé BigQuery | Rendre générique le module de la routine : il touche du code fusionné la veille. La règle du dépôt factorise à la troisième occurrence (`code.md`), et c'est l'objet de #554 |
| Le cron en paramètre, avec défaut | Décision de Sabine ; une passe sans le paramètre garde le rythme | Un paramètre sans défaut, que chaque passe devrait donner |
| `job-data` monté à la racine | Le registre des tendances et le coffre doivent survivre ; décision de Sabine | Un second partage : un second coffre, des gestes de plus, plus de rattrapage par la routine. `subPath` : le coffre reste visible de toute façon, et la création du sous-dossier n'est pas vérifiée |
| Aucune reprise | Pas de second appel au modèle | Une reprise, que Learn conseille contre la maintenance de la plateforme : écrite comme limite, avec sa parade |
| Fenêtre de 3 jours, le défaut | Décision de Sabine (« 5 jours c'est trop ») | 5 jours, recommandés par la session ; 4 jours (laissait le retard de collecte) ; un passage par jour (les tendances sont prévues deux fois par semaine) |
| 0,25 vCPU, 0,5 Gio | Comme la sonde : des appels HTTP et quelques fiches | 1 Gio, comme la routine : rien ne le demandait. La première exécution est allée au bout |

Les choix imposés par une consigne du dépôt :
- l'heure de la routine (ADR de #330) ;
- aucune commande `az` lancée par la session : c'est Sabine qui les lance ;
- le tri des revues par time-knight, sous la délégation de Sabine du 15/10.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `az bicep build` sans erreur, `az bicep lint` sans avertissement (Bicep 0.48.1, la version de la CI) | Le Bicep compile et suit les règles du linter |
| `/security-review` (xhigh) : aucun constat | Ni secret de trop, ni rôle de trop, ni accès nouveau d'`id-kb-deploy` |
| `/code-review high` : 9 constats ; relecteur Azure neuf : aucun bloquant, 5 points corrigés | Les textes (fenêtre, règle des heures, parade sans reprise) disent ce que fait le code |
| `az containerapp job show` avant la passe : `ResourceNotFound` | Le critère rouge : le job n'existait pas |
| What-if : 5 créations (le job, AcrPull, deux Secrets User, Jobs Contributor), le reste du bruit connu | La passe ne fait que ce qui est prévu ; les variables de l'API IA ne changent pas |
| Passe : `Succeeded` ; `job show` : cron `0 10 * * 1,4`, délai 1800, reprise 0, image `k-b:v0.1.2` | Le job est en ligne avec ses réglages |
| Journal système : `SyncingSecretFromAzureKeyVaultForContainerAppJobSucceeded` (deux fois) | Les deux clés se lisent dans le Key Vault |
| Exécution `caj-kb-digest-watch-suoshpa`, 3 min 39 s : 8 fiches sur 9, le compte rendu des tendances, `9 sent` dans `watch`, code 4 | La chaîne tourne en ligne de bout en bout, avec le modèle. Le 4 vient d'un sujet refusé par le contrôle `markup` |

## Ce que tu dois pouvoir défendre

- **Pourquoi aucune reprise, alors que Microsoft en conseille une ?** Parce qu'une reprise après une expiration
  redemanderait tout au modèle, donc le paierait deux fois, sans être toujours refusée. La limite est écrite : une
  maintenance de la plateforme peut couper une exécution. La parade aussi : la routine republie chaque jour, et une
  exécution coupée avant sa première fiche se relance à la main (`digest-watch-job.bicep:72-74`, README d'infra).
- **Pourquoi l'exécution du 11/11 est-elle `Failed`, si tout a marché ?** Le code de sortie d'une routine est le pire
  de ses étapes (`commands/job_routine.py`). Un sujet sur neuf a été refusé par le contrôle `markup` : le modèle avait
  mis un lien ou une balise dans son texte. `kb digest` sort donc en 4 (échec partiel), et Azure appelle `Failed` tout
  code non nul. La protection a fonctionné : rien de refusé n'est écrit.
- **Pourquoi le job voit-il le brut de la routine ?** Parce qu'il monte le même partage, à sa racine : il lui faut le
  registre des tendances et le coffre. Le gain d'un montage plus étroit est faible. Le job tourne avec la même image
  que la routine, et le même `id-kb-deploy` peut changer les deux. Sabine l'a validé, et la parade est au registre.
- **Le déploiement continu n'en sait-il pas trop ?** Il peut agir sous l'identité du job, mais il avait déjà ces accès
  par la routine et par l'API IA. Le registre le dit, sources de Microsoft Learn à l'appui (`deploy-access.bicep:1-8`).
- **Les comptes rendus couvrent-ils toute la semaine ?** Non. Deux pertes sont écrites : le trou du jeudi 10:00 au
  vendredi 10:00, et le retard de collecte (un item du lundi ou du jeudi collecté le lendemain). #565 couvrira le
  premier. Le second attend la lecture par date d'arrivée, prévue après l'oral blanc. Les items restent de toute façon
  dans la base.

## Zones non vérifiées

- **La rotation d'une clé pour un job** : Learn dit qu'une app lit la nouvelle version en 30 minutes, mais ne dit
  rien des jobs. À vérifier à la première rotation.
- **La création d'un sous-dossier par `subPath`** : non essayée, d'où la parade non appliquée.
- **Le pire cas de la publication** : un stockage lent, avec les nouvelles tentatives du SDK, pourrait dépasser les
  1 800 s. Non mesuré ; la première exécution a publié en 4 s.
- **Le cron lui-même** : la première exécution déclenchée par le cron sera celle du jeudi 12/11 à 10:00 UTC. Elle est
  constatée en commentaire sur #423.
- **La cause du refus `markup`** : le texte refusé n'est pas journalisé en ligne (`KB_TRACE_CONTENT=none`).

## Ce qui reste

- Le cron du jeudi 12/11 à 10:00 UTC, constaté sur #423. Sabine ferme ensuite l'issue.
- Le refus `markup` du sujet `coding_assistants` : une issue à part.
- #565 : faire partir chaque compte rendu de la fin du précédent ; puis la lecture par date d'arrivée.
- #570 : retirer aux jobs le droit de supprimer dans `watch`.
- #553 : l'alerte sur une exécution `Failed`. Avec la règle actuelle, un seul sujet refusé suffit à la déclencher.
- #554 : la factorisation des modules de job ; le cron de la routine en paramètre, comme celui-ci.
