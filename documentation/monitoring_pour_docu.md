# Monitorage du modèle et de l'application: tableau de bord, alertes, journaux

« Rédaction de la documentation technique des procédures d'installation, de maintenance du monitorage du modèle. » — C11

« Rédaction de la documentation utilisateur, pour l'utilisation du monitorage. » — C11

« La documentation couvre la procédure d'installation et de configuration des dépendances pour l'outillage du monitorage de l'application. » — C20

Écrit le 2026-11-08 pour #164. Le monitorage du modèle tient dans deux fichiers du dépôt, que Grafana Cloud importe
tels quels: le tableau de bord, `observability/grafana/dashboard.json`, et les trois règles d'alerte,
`observability/grafana/alert-rules.yaml`. Les mesures viennent de l'API IA, qui les envoie en OpenTelemetry depuis
#162 (`docs/fiches-veille.md`, « Les mêmes mesures en OpenTelemetry (#162) »). Le choix de l'outil est écrit dans
`docs/outils-de-suivi.md`. Le monitorage de l'application, ses journaux, est dans la section « Journaux de
l'application » (#165).

## Ce que le monitorage suit

L'API IA mesure chaque appel au modèle: 14 instruments OpenTelemetry, dans
`src/k_b/ai_api/observability/metric_instruments.py`. Grafana Cloud les range sous 20 noms de séries, relevés dans
Explore le 2026-11-08, par exemple `k_b_llm_calls_total` (les appels), `k_b_llm_cost_total` (le coût estimé),
`k_b_digest_facts_found_total` et `k_b_digest_facts_checked_total` (la fidélité). Chaque série porte son
environnement, `deployment_environment_name`: `production` pour l'API en ligne, `sandbox` pour le bac à sable.

Trois mesures ont une alerte:

| Alerte | Ce qu'elle mesure | Fenêtre | Seuil | Source du seuil |
|---|---|---|---|---|
| `KbModelInvalidOutputs` | la part des appels refusés après leur nouvelle tentative (`llm_invalid_output`) | 24 h | au-dessus de 0 % | grille de Sabine du 2026-10-15: « 100 % de schémas valides après une nouvelle tentative » (`docs/ADR/journal-decisions-projet.md`) |
| `KbModelLowFidelity` | la part des faits retrouvés à la fois dans le texte où ils sont affirmés et dans leur source: l'item que chacun désigne, pour les fiches de veille, la source de leur texte, pour le compte rendu des tendances | 24 h | sous 95 % | même grille: « au moins 95 % de fidélité »; provisoire jusqu'au benchmark des modèles et à l'optimisation de la consigne (Sabine, 2026-11-08) |
| `KbModelCostOverBudget` | le coût estimé des appels, aux prix de `src/k_b/core/config.py` | 7 jours | au-dessus de 1 USD | budget choisi par Sabine le 2026-11-08, à revoir avec le relevé des coûts de #411 |

Les fenêtres sont longues: les fiches ne sortent que deux fois par semaine. Sans appel au modèle sur la fenêtre, il
n'y a pas de série, et l'alerte reste normale. De même pour la fidélité sans fait vérifié: elle n'est pas calculée
(le tableau affiche « Aucun appel sur la période ») et l'alerte reste au repos, plutôt qu'une fidélité jamais mesurée
affichée saine.

## Qui lit le tableau et l'alerte

| Lecteur | Ce qu'il en fait | Outil d'assistance |
|---|---|---|
| Sabine, qui exploite K-B | lit le tableau, reçoit seule les alertes par e-mail, corrige | aucun |
| Le jury, pendant la démonstration | lit le tableau et une alerte déclenchée dans le bac à sable | non connus: l'essai d'accessibilité couvre le clavier seul, le lecteur d'écran et le zoom (`docs/accessibilité_pour_docu.md`) |

## Lire le tableau

Le tableau s'appelle « K-B, modèle: qualité, coût, alertes », dans le dossier K-B de la pile. En haut, deux listes:
**Source de données** (la source Prometheus de la pile, `grafanacloud-<pile>-prom`, choisie d'office) et
**Environnement** (`production` par défaut, ou `sandbox`).

- **Alertes**: pour chaque alerte, un panneau donne la valeur sur sa fenêtre et son état, écrit en toutes lettres,
  « NORMAL » ou « ALERTE: seuil dépassé ». Dessous, une courbe montre la même valeur dans le temps, et son seuil en
  ligne de tirets, nommé dans la légende (« Seuil: 95 % »).
- **Appels et contenu des fiches**: un tableau des appels sur 24 h par étape et par issue, les jetons, les items du
  classement, et ce que les contrôles ont retiré des fiches.
- **Durées**: la durée d'un appel au modèle (médiane et 95e centile), celle des contrôles et celle de la lecture
  des données.

Aucune information n'y passe par la seule couleur: les valeurs sont écrites sans couleur, un état est un texte, un
seuil est une ligne nommée (tenu par `tests/test_grafana_files.py`). Les valeurs de chaque panneau se lisent aussi
en tableau: menu du panneau, **Inspect**, **Data**. Un panneau sans appel sur sa fenêtre affiche « Aucun appel sur
la période ».

Une alerte déclenchée arrive par e-mail. L'état y est écrit (« Firing »), avec le nom de l'alerte, son environnement,
sa valeur et son seuil.

## Installer

Sur une pile Grafana Cloud qui reçoit déjà les mesures (#162), par l'interface, sans jeton ni outil à installer.
Relevé le 2026-11-08 sur la pile de Sabine (Grafana 13).

1. **Le tableau**: **Dashboards**, **New**, **Import**, **Upload dashboard JSON file**, le fichier
   `observability/grafana/dashboard.json`. Dossier: K-B (créé au besoin par **Dashboards**, **New**, **New folder**).
   Garder l'identifiant `k-b-model`: il permet de réimporter par-dessus.
2. **Les règles**: **Alerts & IRM**, **Alerting**, **Alert rules**, **More**, **Import**.
   - **Import source**: **Prometheus YAML file**, puis **Upload file**, le fichier
     `observability/grafana/alert-rules.yaml`.
   - **Target data source**: la source Prometheus de la pile.
   - **Target folder**: K-B.
   - **Pause imported alerting rules**: désactivé, sinon aucune alerte ne part.
   - **Recording rules, Target data source**: la même source (champ obligatoire; le fichier n'a pas de règle
     d'enregistrement).
   - **Import**, puis confirmer. Les règles arrivent dans le groupe `k-b-model`, évalué toutes les 5 minutes.
3. **L'état en cas d'erreur**: l'import règle « Alert state if execution error or timeout » sur « OK », et une
   requête en échec laisserait l'alerte au repos. Pour chacune des trois règles: **Edit**, section **Configure no
   data and error handling**, **Alert state if execution error or timeout** sur **Error**, puis **Save rule**. Une
   requête en échec déclenche alors une alerte à part, `DatasourceError`. Le fichier des règles ne porte pas ce
   réglage: il est à refaire après chaque import des règles. Une règle enregistrée repart sans instance jusqu'à son
   évaluation suivante, au plus 5 minutes après: une alerte en cours y repasse un moment par « Normal » (vu le
   2026-11-08).
4. **Le point de contact**: **Alerts & IRM**, **Alerting**, **Notification configuration**, **Contact points**.
   Modifier le point de contact de la politique par défaut: **Add contact point integration**, **Email**, l'adresse
   d'une utilisatrice de la pile, **Test**, puis **Save contact point**. L'adresse n'est pas versionnée: c'est une
   donnée personnelle.

## Maintenir

- **Changer un seuil**: changer le nombre qui termine l'expression de la règle dans `alert-rules.yaml`, et le même
  nombre dans le tableau (la valeur d'état `> bool …` et la ligne `vector(…)`). `uv run pytest tests/test_grafana_files.py`
  échoue tant que les deux ne sont pas égaux. Puis réimporter les deux fichiers.
- **Une règle changée dans l'interface**: les règles importées restent modifiables dans Grafana. Un changement fait
  là se reporte dans `alert-rules.yaml`, sinon la réinstallation suivante l'efface.
- **Renommer ou ajouter une mesure**: le test compare chaque nom du tableau et des règles aux instruments que
  `ModelMetrics` crée, convertis comme Grafana Cloud le fait; il échoue sur un nom qui n'existe plus.
- **Le jeton d'envoi**: un par environnement (`.env.e2e_test` pour le bac à sable; le secret `kb-otlp-headers` du
  coffre pour la production, refait par la procédure « Pour refaire un seul secret » d'`infra/README.md`). Un refus
  de Grafana se lit dans le journal de l'API IA: `Failed to export 'metrics' batch code: 401`.

## Le bac à sable

Le bac à sable déclenche chaque alerte sans modèle réel ni production: il sert les deux API sur la base de test, à
l'heure des tests, avec le rejeu du modèle, et envoie ses mesures à la même pile avec l'environnement `sandbox`
(`tests/e2e/test_sandbox_alerts.py`). Il ne tourne pas en CI.

Depuis un terminal où le `.env` n'est pas chargé, avec `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` dans `.env.e2e_test`:

```sh
make sandbox-alerts
```

Environ 2 min 15. Quatre scénarios, un processus de l'API IA chacun, comme après un réveil en ligne:

| Scénario | Ce qu'il envoie |
|---|---|
| fiches valides | 3 demandes à 65 s d'écart, 12 appels |
| sortie invalide | 1 classement refusé deux fois: `llm_invalid_output` |
| fidélité basse | 3 faits trouvés sur 7 |
| coût au-dessus du budget | au classement, les jetons d'entrée qui coûtent 1,1 fois le budget de l'alerte, sous le plafond de 10 millions qu'une réponse peut déclarer: 9 166 667 jetons, 1,10084 USD |

Chaque test échoue si un envoi échoue. Sans adresse ni en-tête, il est sauté.

## Relevé des alertes du bac à sable

Bac à sable lancé par Sabine le 2026-11-08, fin vers 17:45 UTC: 4 tests réussis, chaque envoi accepté. Son scénario
de coût envoyait alors 10 millions de jetons, soit 1,20084 USD.

| Alerte | Seuil | Valeur observée dans le tableau (19:03 UTC) | Déclenchée | E-mail reçu |
|---|---|---|---|---|
| `KbModelInvalidOutputs` | > 0 % | 4,8 % (1 appel sur 21) | oui, 19:15:20 UTC | oui, 19:27 UTC |
| `KbModelLowFidelity` | < 95 % | 73,3 % (11 faits sur 15) | oui, 19:15:20 UTC | oui, 19:27 UTC |
| `KbModelCostOverBudget` | > 1 USD | 1,2641 USD | oui, 19:15:20 UTC | oui, 19:27 UTC |

Le coût observé dépasse les 1,20516 USD du bac à sable: le reste vient de mesures `sandbox` plus anciennes de la
fenêtre de 7 jours (essais locaux du 2 au 6 novembre). L'e-mail de test du point de contact est arrivé à 19:25:12 UTC.
Les trois e-mails sont arrivés 12 min 26 s après le déclenchement, une fois le point de contact enregistré, un par
alerte. Le sujet donne l'alerte et son environnement (« [FIRING:1] KbModelCostOverBudget K-B/alert-rules.yaml
(sandbox warning) »), le corps son résumé, sa valeur et ses étiquettes (`deployment_environment_name` vaut `sandbox`).

**À réimporter**: après ce relevé, le tableau et la règle de fidélité ont changé dans le dépôt (la fidélité sans fait
vérifié ne donne plus de donnée). La pile garde la version importée le 2026-11-08: réimporter les deux fichiers, puis
refaire l'étape 3 d'« Installer », avant l'essai d'accessibilité.

## Limites

- **Le décompte par `max_over_time`**. Chaque processus de l'API IA est une série neuve, dont `increase()` ne voit
  pas le premier incrément: dans le bac à sable, `increase` comptait 12 appels sur 21, `max_over_time` les 21. Le
  tableau et les règles somment donc le maximum de chaque série sur la fenêtre, depuis le début de son processus. Un
  processus encore vivant au début de la fenêtre y compte aussi ses appels d'avant; en ligne, un processus ne vit que
  quelques minutes (l'API tombe à zéro réplique). Deux cas faussent donc le décompte: un `kb serve-ai` local laissé
  ouvert plus longtemps que la fenêtre (une sortie invalide de la veille garde l'alerte déclenchée), et un
  `minReplicas` de l'API IA au-dessus de 0.
- **Une série s'éteint 5 minutes après son processus**: aucun panneau ne lit une valeur instantanée.
- **Une seule pile**: l'offre gratuite n'en a qu'une; le bac à sable est un environnement de la même pile.
- **E-mail aux seules utilisatrices de la pile**: depuis le 2026-04-20, un compte gratuit nouveau n'envoie d'e-mail
  qu'aux utilisatrices de son instance (incident `xg2h8ht1d44n` de status.grafana.com, clos le 2026-04-24); les
  webhooks marchent toujours.
- **Un changement d'offre supprime les jetons sans prévenir**: le 2026-11-08, le passage de la pile de l'essai Pro à
  l'offre gratuite a supprimé ses access policies; le bac à sable a reçu `401 Unauthorized` jusqu'au jeton neuf.
  Le jeton de la production est à refaire de même.
- **Rétention de 14 jours** sur l'offre gratuite: aucune fenêtre ne la dépasse.
- **Ce que la fidélité mesure aujourd'hui** (2026-11-08): une recherche de time-knight, sur le jeu de #479 rejoué par
  les fonctions de K-B, trouve les 26 faits présents dans l'item cité, donc aucune invention; les 12 faits « non
  trouvés » manquent seulement dans le texte français de la fiche (CVE non écrites, faits traduits). La fidélité
  mesure donc surtout l'écart entre la consigne, qui demande un texte en français, et le contrôle, qui ne compte un
  fait trouvé que s'il est, mot pour mot après normalisation (un CVE ou un GHSA sous sa forme canonique), à la fois
  dans le texte français de son affirmation et dans l'anglais de l'item qu'il désigne. Son seuil de 95 % est provisoire.
- **L'état en cas d'erreur n'est pas dans le fichier**: l'import des règles au format Prometheus règle « Alert state if
  execution error or timeout » sur « OK », comme l'absence de données (vu dans la règle importée le 2026-11-08). Le
  passer sur « Error » est l'étape 3 d'« Installer », faite à la main: une réinstallation qui l'oublie laisse une
  requête en échec sans alerte.
- **Le coût est une estimation**: tout appel est compté aux prix de `src/k_b/core/config.py`, le rejeu compris.
- **L'installation est manuelle**: deux imports et un point de contact, sans jeton. L'API de provisioning des
  alertes de Grafana, qui l'automatiserait, est marquée « deprecated » et demanderait un secret.

## Journaux de l'application

Écrit le 2026-11-09 pour #165 et revu le 2026-11-11 d'après le code de `main` au commit `d1b5400`. Le tableau et les alertes ci-dessus
suivent le modèle; l'application se suit par ses journaux: ceux de `kb`, de `kb serve-data` (l'API de données) et de
`kb serve-ai` (l'API IA). En local, ils ne demandent rien à installer: `kb` les écrit par le module `logging` de
Python. En ligne, ils vont dans l'espace Log Analytics `log-kb`, qu'`infra/main.bicep` crée. Aucune alerte ne les lit
(« Limites des journaux », plus bas).

### Ce que l'application écrit

| Journal | Ce qu'il contient | En local | En ligne | Code |
|---|---|---|---|---|
| journal de `kb` | le déroulé d'une commande, réussites et échecs, une ligne datée par événement | sortie d'erreur et `<KB_DATA_DIR>/logs/kb.log` | sortie d'erreur du job, dans `log-kb` | `src/k_b/commands/run_log.py:21-23`, `:61-83` |
| journal de `kb serve-data` | son démarrage, ses clients, son arrêt, une ligne par requête | sortie d'erreur et `<KB_DATA_DIR>/logs/kb-serve-data.log` | sortie d'erreur de `ca-kb-data-api`, dans `log-kb` | `src/k_b/cli.py:66-71`, `src/k_b/commands/serve_data_command.py:41-42`, `src/k_b/data_api/app.py:71` |
| journal de `kb serve-ai` | de même, pour l'API IA | sortie d'erreur et `<KB_DATA_DIR>/logs/kb-serve-ai.log` | sortie d'erreur de `ca-kb-ai-api`, dans `log-kb` | `src/k_b/cli.py:66-71`, `src/k_b/commands/serve_ai_command.py:74-87`, `src/k_b/ai_api/app.py:96` |
| ligne de mesure d'un appel au modèle | une ligne JSON par appel: durée, jetons, coût estimé, états; ni texte ni clé | sortie standard de `kb serve-ai`, aucun fichier | sortie standard de `ca-kb-ai-api`, dans `log-kb` | `src/k_b/ai_api/observability/metrics.py:1-2`, `:35-51` |
| résultat d'une commande | ce que la commande affiche par `print`, le bilan d'un import par exemple | sortie standard | sortie standard du job, dans `log-kb` | `.claude/rules/conventions.md`, règle 3 |

Deux autres sorties ne sont pas des journaux de fonctionnement. Le journal d'import,
`<KB_DATA_DIR>/journals/import-journal-<AAAA-MM-JJTHHMMSSZ>.jsonl` (`src/k_b/core/config.py:172-173`, `src/k_b/etl/pipeline.py:35`), dit ce qu'un
import a décidé des données (`README.md:286-292`). Les traces et les enregistrements de l'API IA partent vers Grafana
Cloud avec ses mesures, sous le même réglage (`docs/architecture-api-ia.md`, « Les métriques et les journaux »).

### Lire une ligne

Une ligne s'écrit `<date> <niveau> <module>: <message>` (`src/k_b/commands/run_log.py:30`), la date en ISO 8601, en
UTC, à la seconde, avec son `Z` (`:84-86`). Le niveau est INFO ou au-dessus (`:95`). Les bibliothèques n'écrivent qu'à
partir d'un niveau plus haut, car en dessous elles citent ce que `kb` ne journalise pas: `httpx2` dès WARNING (l'URL
du fournisseur du modèle); `azure` et `urllib3` dès ERROR (l'URL d'un blob, qui porte le titre d'un clip); `psycopg`
et `psycopg_pool` dès ERROR (l'hôte, l'utilisateur et la base) (`:31-55`, `:96-97`). uvicorn écrit par les mêmes
sorties, sans son propre journal d'accès (`log_config=None`, `access_log=False`:
`src/k_b/commands/serve_data_command.py:55-56`, `src/k_b/commands/serve_ai_command.py:107-108`).

La ligne d'une requête donne la méthode, le gabarit de la route (`/items/{item_id}`, jamais le chemin reçu), le
statut, la durée en ms, le nom du client et l'identifiant de la requête, rendu aussi dans
l'en-tête `X-Request-ID` de la réponse (`src/k_b/core/api_request_log.py:27-33`, `:56-81`). Jamais la clé, une
valeur de paramètre ni un chemin brut (`:1-2`). Un champ vaut `-` quand rien n'a été vu: aucune route reconnue,
aucun client nommé par une clé valide, aucune réponse envoyée (`:18-19`; la liste des cas: `docs/specs-api.md`,
« Journal »). Un `/health` qui répond 200 n'est pas écrit; une sonde en échec l'est
(`:36-38`). Une erreur de la base reprend le même identifiant (`src/k_b/data_api/errors.py:46-56`), et la ligne de
mesure de l'API IA aussi, en JSON (`"request_id": "…"`, `src/k_b/ai_api/observability/metrics.py:65`): il relie une
demande à ses erreurs et à ses appels au modèle, dans une même API. Chaque API tire le sien
(`src/k_b/core/api_request_log.py:27`): une demande de `kb digest` a un identifiant dans l'API IA, un autre dans l'API
de données, sans lien entre eux (« Limites des journaux »).

Relevé sur un `KB_DATA_DIR` neuf. Les deux premières lignes viennent de `logs/kb.log`, le 2026-11-11: `kb create-db`,
`kb import`, puis `kb purge`. Les deux suivantes viennent de `logs/kb-serve-data.log`, le 2026-11-09: `kb serve-data` et
quatre requêtes (`/health`, puis trois `/items`, dont une sans clé); le `/health` n'a pas de ligne.

```text
2026-11-11T14:37:27Z INFO k_b.cli: import started
2026-11-11T14:37:28Z INFO k_b.purge.run_records: logs and journals purge: 0 files older than 6 months deleted
2026-11-09T13:27:36Z INFO k_b.core.api_request_log: request method='GET' route=/items status=200 duration_ms=3 client=TERMINAL request_id=e5a0072a-ed6b-403f-b2e8-3e397c677f9b
2026-11-09T13:27:36Z INFO k_b.core.api_request_log: request method='GET' route=/items status=401 duration_ms=0 client=- request_id=7b915163-04a9-4238-9692-89f5cf161959
```

### En local: installer et configurer

Rien à installer. Deux variables règlent les journaux. `kb` ne lit jamais un fichier `.env` lui-même: elles viennent
de l'environnement, ou d'un fichier passé par `uv run --env-file .env kb …` (`src/k_b/commands/environment.py:21-22`).

- `KB_DATA_DIR`, obligatoire et sans défaut, un dossier qui existe déjà: sinon, `error: KB_DATA_DIR is not an existing
  directory`, code 2, sans rien lancer (`src/k_b/commands/environment.py:38-42`, `src/k_b/cli.py:110-111`). Les
  journaux vont dans son dossier `logs/` (`src/k_b/core/config.py:164-171`), créé au premier lancement
  (`src/k_b/commands/run_log.py:71-72`).
- `KB_LOG_TO_FILE`, `true` par défaut (`src/k_b/core/config.py:223-225`), lue par
  `src/k_b/commands/environment.py:46-58`: `false` écrit sur la sortie d'erreur seule, sans fichier. Une autre valeur
  arrête la commande en code 2, sans rien lancer: `error: KB_LOG_TO_FILE: 'oui' neither true nor false` (relevé le
  2026-11-09). Son modèle commenté est dans `.env.example:59-61`.

Une commande dont le fichier de journal ne s'ouvre pas ne se lance pas: `error: log file not opened: …`, code 2
(`src/k_b/cli.py:213-229`). `kb openapi` et le `--dry-run` des routines n'écrivent aucun journal
(`src/k_b/cli.py:103-116`). Chaque API a son fichier: une rotation faite par une autre commande laisserait un
processus long écrire dans le fichier de la veille (`src/k_b/cli.py:66-67`; `docs/specs-api.md`, « Journal »).

**Rotation et durée.** Chaque fichier tourne à la première ligne écrite après minuit UTC: ses lignes passent dans
`kb.log.<AAAA-MM-JJ>`, au jour de ces lignes (de même pour les deux autres), et les nouvelles vont dans un `kb.log`
neuf (`src/k_b/commands/run_log.py:74-81`; nom daté: `src/k_b/purge/run_records.py:20-30`). La rotation ne supprime
rien. Le fichier courant, sans date dans son nom, n'est jamais purgé (`src/k_b/purge/run_records.py:60-65`). `kb purge`, dernière de ses purges, supprime les
journaux et les journaux d'import dont le jour du nom a plus de 6 mois (`src/k_b/purge/run_records.py:36-50`, appelée
par `src/k_b/purge/all_purges.py:63`; durée: `src/k_b/core/config.py:174-178`). En local, elle se lance à la main.
En ligne, le job `caj-kb-daily-routine` la lance: `kb daily-routine` l'enchaîne après `kb import`
(`src/k_b/commands/daily_routine_command.py:63`), et ne démarre pas sans les réglages du job, dont `AZURE_CLIENT_ID`
(`src/k_b/commands/daily_routine_command.py:80-84`, `src/k_b/jobs/exchange_storage.py:101-105`).

### En local: lire

```sh
tail -f "$KB_DATA_DIR/logs/kb-serve-ai.log"                  # suivre l'API IA
grep -E " (WARNING|ERROR) " "$KB_DATA_DIR"/logs/kb.log*    # avertissements et échecs des commandes, jours passés compris
grep "request_id=<id>" "$KB_DATA_DIR"/logs/kb-serve-*.log    # les lignes d'une requête, par son X-Request-ID
```

Un avertissement nomme un état, un délai de la base dépassé par exemple (`query_timeout`,
`src/k_b/data_api/errors.py:55`). La trace d'une erreur imprévue suit sa ligne datée, sur des lignes sans date
(`.claude/rules/conventions.md`, règle 3): `grep -A` la montre avec sa ligne. Le motif `request_id=` ne trouve que
les lignes de requête et d'erreur; une ligne de mesure porte `"request_id"`, sur la sortie standard.

Les lignes de mesure ne vont que sur la sortie standard de `kb serve-ai`: aucun fichier ne les garde
(`src/k_b/ai_api/observability/metrics.py:50-51`). Les mêmes mesures partent vers Grafana Cloud quand l'export est
réglé (sections ci-dessus).

### En ligne: installer et configurer

Tout est posé par `infra/main.bicep`, que Sabine applique à la main (`infra/README.md`, « Appliquer »):

- l'espace `log-kb` (`infra/modules/log-analytics.bicep:5-20`): 30 jours de rétention, et un plafond de 0,2 Go par
  jour (`:13-19`): atteint, l'espace cesse de recevoir jusqu'à son heure de remise à zéro, propre à chaque espace et
  non réglable; ce qui est déjà reçu reste (Microsoft Learn, « Set daily cap on Log Analytics workspace », lu le
  2026-11-11);
- l'environnement `cae-kb` y envoie les journaux des conteneurs par Azure Monitor, sans clé partagée, par le paramètre
  de diagnostic `logs-to-log-kb`, en deux tables: `ContainerAppConsoleLogs` (sortie standard et sortie d'erreur des
  conteneurs) et `ContainerAppSystemLogs` (démarrage, tirage de l'image, réveil d'une app à 0 réplique)
  (`infra/modules/container-apps-environment.bicep:25-29`, `:49-69`; `infra/README.md:322-323`);
- l'image règle `KB_LOG_TO_FILE=false` et `PYTHONUNBUFFERED=1` (`Dockerfile:42-47`): en conteneur, pas de fichier
  de journal, la sortie d'erreur est le journal, et une ligne de la sortie standard part aussitôt. Aucune pièce
  d'`infra/` ne change `KB_LOG_TO_FILE`. Le `KB_DATA_DIR` en ligne est un dossier de l'image, vidé à chaque
  démarrage, sauf pour `caj-kb-daily-routine`, qui y monte le partage `job-data` (`infra/main.bicep:55-58`): ses
  journaux d'import y restent, pas son journal de fonctionnement.

Y écrivent les deux API, `ca-kb-data-api` et `ca-kb-ai-api` (`infra/main.bicep:203`, `:238`), et les trois jobs:
`caj-kb-smoke-test` (`infra/modules/smoke-test-job.bicep:30`), `caj-kb-migrate-database`
(`infra/modules/migrate-database-job.bicep:59`) et `caj-kb-daily-routine`, qui lance `kb daily-routine` chaque jour à
08:00 UTC (`infra/modules/daily-routine-job.bicep:59`, `:77-78`).

Pour lire `log-kb`: l'Azure CLI, connectée à l'abonnement (`az login`), et son extension `log-analytics`, qui porte
`az monitor log-analytics query` (`az extension add --name log-analytics`; message « This command is from the
following extension: log-analytics », relevé le 2026-11-09 avec azure-cli 2.92.0 et l'extension 1.0.0b3, encore les
dernières le 2026-11-11). Le rôle Lecteur (`*/read`) suffit à lire `log-kb` (`docs/registre-traitements.md:199`, source
Microsoft Learn: `:293`). L'abonnement et `RG` se règlent comme pour l'application de l'infrastructure
(`infra/README.md`, « 0. Les variables du shell »).

### En ligne: lire

Ce qu'a écrit un job se lit dans `log-kb` « quelques minutes après sa fin » (`infra/README.md:310`). Les journaux
d'une API:

```sh
RG=<groupe de ressources>
WS=$(az monitor log-analytics workspace show -n log-kb -g "$RG" --query customerId -o tsv)
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(1h) and ContainerAppName == 'ca-kb-ai-api' | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Stream, Log]"
```

`ca-kb-data-api` à la place pour l'API de données; `isnotempty(JobName)` pour les jobs (`infra/README.md:314-317`), `JobName == 'caj-kb-daily-routine'` pour la
routine (`:1064-1065`);
`ContainerAppSystemLogs` pour le démarrage et le réveil. La colonne `Stream` vaut `stdout` ou `stderr`: les lignes de
mesure de l'API IA sont sur `stdout`. `az containerapp job logs show` ne lit qu'une exécution en cours
(`infra/README.md:310-311`).

Relevé le 2026-11-11 à 14:38 UTC, en lecture seule, sur les 30 derniers jours: `ca-kb-data-api`, 100 lignes, et
`ca-kb-ai-api`, 130, toutes sur `stderr`; `caj-kb-daily-routine`, 310 lignes sur `stderr` et 150 sur `stdout`, la
dernière le 2026-11-11 à 08:01 UTC; `caj-kb-smoke-test`, 35 sur `stderr` et 62 sur `stdout`;
`caj-kb-migrate-database`, 5 sur `stdout`. Aucune ligne `stdout` pour `ca-kb-ai-api`: pas de ligne de mesure sur la
période.

### Limites des journaux

- **Aucune alerte ne lit les journaux**: ni l'échec d'un job, ni une source muette, ni des réponses 5xx, ni `/health`
  en ligne. Elles sont portées par #282, ouverte. Un échec ne se voit qu'en lisant le journal.
- **En local, rien ne lance `kb purge` de lui-même**: une machine qui ne lance que les API, ou `kb import` sans
  `kb purge`, ne purge jamais `logs/`.
- **La purge des journaux passe en dernier, et la première purge qui échoue arrête les suivantes**, par choix
  (`src/k_b/purge/all_purges.py:1-3`, `:63`): sans base, `kb purge` ne lance aucune purge (`:49`, `:69-71`), et une purge
  qui échoue avant celle des journaux laisse `logs/` et `journals/` tels quels. Pour réduire le risque: la purge
  suivante relance toutes les purges (`:3`); en ligne, l'échec d'une étape donne son code à la routine
  (`src/k_b/commands/job_routine.py:2`), et l'exécution du job se lit `Failed` (`infra/README.md:1059`).
- **En ligne, `log-kb` est la seule copie**: aucun fichier dans le conteneur, et la purge à 6 mois ne s'y applique
  pas. Log Analytics efface après 30 jours; au-delà de 0,2 Go dans la journée, les lignes qui arrivent jusqu'à la remise
  à zéro du plafond sont perdues.
- **Les lignes de mesure ne sont gardées nulle part en local**: la sortie standard de `kb serve-ai` va au terminal.
- **Une demande ne se suit pas d'une API à l'autre**: l'API IA n'envoie pas son identifiant à l'API de données, qui
  tire le sien (`src/k_b/core/api_request_log.py:27`). Les lignes des deux API se rapprochent par l'heure et par le nom du client que l'API de données journalise.
- **Un seul `kb serve-data` et un seul `kb serve-ai` par `KB_DATA_DIR`**: deux, sur deux ports, écriraient le même
  fichier (`docs/specs-api.md`, « Journal »; `README.md:476`).
- **L'export vers Grafana Cloud en ligne**: son jeton de production est l'objet de #522; aucune mesure de la
  production n'est relevée ici, faute d'appel au modèle en ligne sur la période.
- **[WIP #423] Le job des fiches de veille, `caj-kb-digest-watch`**, n'est pas déclaré dans `infra/` au commit `d1b5400`;
  son identité, `id-kb-digest-watch`, y est déjà (`infra/main.bicep:46`). Ses journaux, quand il y sera, se liront
  comme ceux des autres jobs.

## Sources

Lues le 2026-11-08.

- Grafana Cloud, conversion OTLP et promotion des attributs de ressource:
  https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/ et
  https://grafana.com/docs/grafana-cloud/send-data/otlp/promote-resource-attributes/
- Restrictions des alertes d'un compte gratuit: https://status.grafana.com/incidents/xg2h8ht1d44n
- Import de règles Prometheus dans des règles gérées par Grafana:
  https://grafana.com/docs/grafana/latest/alerting/alerting-rules/alerting-migration/
- API de provisioning des alertes, « deprecated »:
  https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/
- État d'une règle en cas d'erreur de requête (« Error » par défaut pour une règle créée dans Grafana, `DatasourceError`):
  `docs/sources/alerting/guides/connectivity-errors.md` et `docs/sources/shared/alerts/modify-error-state.md` du dépôt
  grafana/grafana, version v13.3.0.
- Repères des règles de champ d'un tableau (`byFrameRefID`): `packages/grafana-data/src/transformations/matchers/ids.ts`
  du dépôt grafana/grafana, version v13.3.0.
- Noms des séries et comportement d'`increase`: relevés de Sabine dans Explore, le 2026-11-08.
