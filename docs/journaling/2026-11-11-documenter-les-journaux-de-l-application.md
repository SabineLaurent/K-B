# Documenter les journaux de l'application, en local et en ligne

- Date : 2026-11-11
- Branche : `docs/application-logs-monitoring`
- Issue : #165
- Fichier principal : `documentation/monitoring_pour_docu.md`, section « Journaux de l'application »
- Série : [journaux horodatés et fichier de journal](2026-10-14-journaux-horodates-et-fichier-de-journal.md),
  [garder logs et journaux 6 mois](2026-11-04-garder-logs-et-journaux-6-mois.md),
  [purger par sa propre commande](2026-11-10-purger-par-sa-propre-commande.md)

Les commits de la branche sont `fd00026`, `0dd92b1` et `2aa3054`. Les autres de la liste viennent de `main` : ils
sont antérieurs au rebase, et cette note n'en traite pas.

## Le pourquoi

C20.6 demande que la documentation couvre l'installation et la configuration de l'outillage qui suit
**l'application**. La fiche du monitorage ne couvrait que le modèle (tableau Grafana, alertes). Les journaux de
`kb`, de `kb serve-data` et de `kb serve-ai` n'étaient dans aucune fiche : où ils vont, ce qui les règle, comment on
les lit, en local comme sur Azure. La section ajoutée le dit, et chaque fait renvoie à son `fichier:ligne`.
Elle ne change aucun code.

## Le comment

### Une seule fonction ouvre tous les journaux

Chaque commande passe par `logging_to`, qui écrit sur la sortie d'erreur et, sauf `KB_LOG_TO_FILE=false`, dans un
fichier tourné à minuit UTC (`src/k_b/commands/run_log.py:74-81`) :

```python
TimedRotatingFileHandler(
    log_path,
    when="midnight",
    utc=True,
    # A rotation deletes nothing: backupCount counts files, not days. Only the purge
```

`backupCount=0` : la rotation ne supprime rien. Seul `kb purge` supprime un journal, d'après le jour écrit dans son
nom. La fiche le dit, et précise que le fichier courant, `kb.log`, sans date dans son nom, n'est jamais purgé
(`src/k_b/purge/run_records.py:60-65`).

### Un fichier par API

`src/k_b/cli.py:68-71` donne à chaque processus long son propre fichier :

```python
LOG_FILE_PATH_BY_COMMAND = {
    "serve-data": SERVE_DATA_LOG_FILE_PATH,
    "serve-ai": SERVE_AI_LOG_FILE_PATH,
}
```

La raison est écrite au-dessus, en `:66-67`. Si une autre commande faisait tourner le fichier, l'API continuerait
d'écrire dans le fichier de la veille, déjà renommé. La fiche en tire une limite : un seul `kb serve-data` et un seul
`kb serve-ai` par `KB_DATA_DIR`.

### En ligne, la sortie d'erreur est le journal

L'image règle le mode conteneur (`Dockerfile:45-47`) :

```dockerfile
ENV PATH="/app/.venv/bin:$PATH" \
    KB_LOG_TO_FILE=false \
    PYTHONUNBUFFERED=1
```

Pas de fichier de journal, et une sortie standard sans tampon. L'environnement `cae-kb` envoie la sortie des
conteneurs à l'espace Log Analytics `log-kb` par un paramètre de diagnostic, sans clé partagée
(`infra/modules/container-apps-environment.bicep:49-69`). La fiche donne la requête `az monitor log-analytics query`
qui lit `ContainerAppConsoleLogs`, et les comptes relevés le 2026-11-11.

### Ce que le code ne fait pas devient une limite

La fiche écrit comme limites ce que le code ne fait pas :
- aucune alerte ne lit les journaux (#282) ;
- la purge des journaux passe en dernier, et un échec avant elle l'arrête (`src/k_b/purge/all_purges.py:1-3`) ;
- une demande ne se suit pas d'une API à l'autre (`src/k_b/core/api_request_log.py:27`) ;
- le job `caj-kb-digest-watch` n'est pas encore déclaré (`[WIP #423]`).

## Choix faits et options écartées

- **Une section dans la fiche existante, au titre élargi à l'application**, plutôt qu'une fiche à part. C'est
  l'avis de time-knight, retenu au plan validé par Sabine le 09/11 : une seule fiche du monitorage à citer en C20.6.
- **Des relevés réels**, plutôt que des lignes inventées. Les lignes d'exemple et les comptes de `log-kb` sont des
  sorties observées et datées. Raison : la règle du dépôt (`code.md`, « n'affirmer que l'observé »).
- **Rebase et revérification de chaque renvoi**, plutôt qu'une PR sur l'ancienne base. `main` avait avancé de
  113 commits entre-temps, dont `kb purge` (#540) et le job `caj-kb-daily-routine` (#330). Plusieurs faits avaient
  changé, et les numéros de ligne avec eux.
- **Le tri des deux relectures** a été tranché par time-knight, sous la délégation de Sabine du 15/10. Le
  commentaire faux du plafond, dans `infra/modules/log-analytics.bicep:16`, est laissé tel quel : `infra/` est en
  lecture seule pour cette mission, et sa correction va dans une issue à part.

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| `kb create-db`, `kb import`, `kb purge` sur un `KB_DATA_DIR` neuf, le 2026-11-11 : codes 0, lignes de `logs/kb.log` | le format d'une ligne et la ligne de la purge des journaux, citées dans la fiche |
| Requête en lecture seule sur `log-kb`, 30 jours, le 2026-11-11 à 14:38 UTC | les deux API et les trois jobs écrivent dans `log-kb` ; aucune ligne de mesure en ligne |
| Script de contrôle : 0 caractère `Cc`/`Cf` ; chaque renvoi `fichier:ligne` dans la longueur de son fichier | pas de caractère invisible ni de renvoi hors du fichier |
| Relecture 1 (15 constats, tous traités), relecture 2 sur le delta | justesse des renvois au code de `d1b5400` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas une alerte sur les journaux ?** Ce n'est pas dans le périmètre de #165, et c'est porté par #282.
   La fiche le dit en tête des limites.
2. **Où va un journal en ligne, et combien de temps ?** Dans `log-kb`, 30 jours, dans la limite de 0,2 Go par jour.
   Au-delà, la collecte s'arrête jusqu'à la remise à zéro (`infra/modules/log-analytics.bicep:13-19` ; Microsoft
   Learn, lu le 2026-11-11).
3. **Un journal peut-il contenir une donnée personnelle ou une clé ?** Non par construction. La ligne d'une requête
   donne le gabarit de la route, jamais le chemin reçu ni la clé (`src/k_b/core/api_request_log.py:1-2`). Les
   bibliothèques qui citeraient une URL ou une connexion sont tenues à WARNING ou ERROR
   (`src/k_b/commands/run_log.py:31-55`).
4. **Que faut-il installer ?** En local, rien : c'est le module `logging` de Python. En ligne, l'Azure CLI et son
   extension `log-analytics`, et le rôle Lecteur.

## Zones non vérifiées

- Les lignes de `kb-serve-data.log` citées datent du 2026-11-09 et n'ont pas été relevées de nouveau. Les fichiers
  qu'elles touchent (`core/api_request_log.py`, `commands/serve_data_command.py`) n'ont pas changé depuis.
- L'heure de remise à zéro du plafond de `log-kb` n'a pas été lue : elle est propre à l'espace.
- Le délai d'arrivée d'une ligne d'API dans `log-kb` n'a pas été mesuré. La fiche cite celui qu'`infra/README.md`
  donne pour un job.

## Ce qui reste

- Les alertes sur les journaux : #282.
- Les journaux du job des fiches de veille : avec #423.
- La correction du commentaire du plafond dans `infra/` : l'issue à créer après l'accord de time-knight.
