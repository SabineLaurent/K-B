# Monitorage du modèle et de l'application: tableau de bord, alertes, journaux

!!! note "Compétences de la certification"

    > Rédaction de la documentation technique des procédures d'installation, de maintenance du monitorage du modèle.

    — C11

    > Rédaction de la documentation utilisateur, pour l'utilisation du monitorage.

    — C11

    > La documentation technique de la chaîne de monitorage couvre la procédure d'installation de la chaîne, de
    > configurations, et d'utilisation du monitorage à destination des équipes techniques.

    — C11

    > Documentation du monitorage et des procédures d'installation et de configuration de l'outillage utilisé dans
    > l'environnement de l'application.

    — C20

    > La documentation liste les métriques et les seuils et valeurs d'alerte pour chaque métrique à risque.

    — C20

    > La documentation explicite les arguments en faveur des choix techniques pour l'outillage du monitorage de
    > l'application.

    — C20

    > La documentation couvre la procédure d'installation et de configuration des dépendances pour l'outillage du
    > monitorage de l'application.

    — C20

    > La documentation est communiquée dans un format qui respecte les recommandations d'accessibilité (par exemple
    > celles de l'association Valentin Haüy ou de Microsoft).

    — C11, C20

La liste suivante donne, pour chaque phrase de l'encadré, les sections de cette fiche qui y répondent.

- L'installation et la maintenance du monitorage du modèle: [Brancher l'export](#brancher-lexport),
    [Installer](#installer) et [Maintenir](#maintenir).
- L'utilisation du monitorage: [Qui lit le tableau et l'alerte](#qui-lit-le-tableau-et-lalerte) et
    [Lire le tableau](#lire-le-tableau).
- La chaîne de monitorage, son installation, ses configurations et son utilisation par les équipes techniques:
    [Brancher l'export](#brancher-lexport), [Installer](#installer), [Lire le tableau](#lire-le-tableau) et
    [Journaux de l'application](#journaux-de-lapplication).
- Le monitorage et l'outillage de l'environnement de l'application, leur installation et leur configuration:
    [Journaux de l'application](#journaux-de-lapplication), en local et en ligne.
- Les métriques, les seuils et les valeurs d'alerte: [Ce que le monitorage suit](#ce-que-le-monitorage-suit).
    Aucune alerte ne lit les journaux de l'application ([Limites des journaux](#limites-des-journaux)).
- Les arguments des choix techniques de l'outillage: [Les arguments du choix des outils](#les-arguments-du-choix-des-outils).
- Les dépendances de l'outillage, leur installation et leur configuration: [Brancher l'export](#brancher-lexport)
    (la pile, la politique d'accès, le jeton, les variables de l'API IA) et
    [Journaux de l'application](#journaux-de-lapplication).
- Le format accessible: [L'accessibilité de la documentation](accessibilite.md).

Les renvois `fichier:ligne` de cette fiche visent `main` au commit `a1a01efd`. Le monitorage du modèle tient dans deux
fichiers du dépôt, que Grafana Cloud importe tels quels: le tableau de bord, `observability/grafana/dashboard.json`,
et les cinq règles d'alerte, `observability/grafana/alert-rules.yaml`. Les mesures viennent de l'API IA, qui les envoie
en OpenTelemetry (`docs/fiches-veille.md`, « Les mêmes mesures en OpenTelemetry (#162) »).
Les arguments du choix des outils sont dans la section [Les arguments du choix des outils](#les-arguments-du-choix-des-outils);
la comparaison détaillée est dans `docs/outils-de-suivi.md`. Le monitorage de l'application, ses journaux, est dans la section
[Journaux de l'application](#journaux-de-lapplication) (#165).

## Ce que le monitorage suit

L'API IA mesure chaque appel au modèle et la durée de chaque demande de compte rendu: 17 instruments OpenTelemetry,
dans `src/k_b/ai_api/observability/metric_instruments.py`. Grafana Cloud les range sous 25 noms de séries, relevés
dans Explore (`NAMES_SEEN_IN_GRAFANA`, `tests/test_grafana_files.py`), par exemple `k_b_llm_calls_total` (les
appels), `k_b_llm_cost_total` (le coût estimé), `k_b_digest_facts_found_total` et `k_b_digest_facts_checked_total`
(la fidélité), et les trois noms de la durée d'une demande, `k_b_request_duration_seconds_bucket`, `_count` et
`_sum`. Chaque série porte son environnement, `deployment_environment_name`: `production` pour l'API en ligne,
`sandbox` pour le bac à sable.

Le tableau suivant donne les cinq alertes: ce que chacune mesure, sa fenêtre, son seuil et la source de ce seuil.

| Alerte | Ce qu'elle mesure | Fenêtre | Seuil | Source du seuil |
|---|---|---|---|---|
| `KbModelInvalidOutputs` | la part des appels refusés après leur nouvelle tentative (`llm_invalid_output`) | 24 h | au-dessus de 0 % | la grille de lecture du journal des décisions: <q>100 % de schémas valides après une nouvelle tentative</q> (`docs/ADR/journal-decisions-projet.md:3389`) |
| `KbModelLowFidelity` | la part des faits retrouvés à la fois dans le texte où ils sont affirmés et dans leur source: l'item que chacun désigne, pour les fiches de veille, la source de leur texte, pour le compte rendu des tendances | 24 h | sous 95 % | la même grille: <q>au moins 95 % de fidélité</q> (`docs/ADR/journal-decisions-projet.md:3389-3390`); provisoire jusqu'au <span lang="en">benchmark</span> des modèles et à l'optimisation de la consigne (#674) |
| `KbModelCostOverBudget` | le coût estimé des appels, aux prix de gpt-6.1-sol de `src/k_b/core/config.py` | 7 jours | au-dessus de 2 USD | au-dessus du maximum normal de gpt-6.1-sol, 1,55 USD par semaine: l'alerte signale une dépense anormale (`docs/ADR/journal-decisions-projet.md:7419-7421`) |
| `KbModelCallFailures` | la part des appels en échec après leur nouvelle tentative: délai dépassé (`llm_timeout`), service indisponible (`llm_unavailable`), trop de requêtes (`llm_rate_limited`), filtre de contenu (`llm_content_filtered`), sortie coupée au plafond de jetons (`llm_truncated`) | 24 h | au-dessus de 0 % | un appel en échec est un sujet ou un compte rendu qui manque (`docs/ADR/journal-decisions-projet.md:7428-7433`) |
| `KbRequestOverDuration` | la part des demandes de compte rendu (`POST /digests`, `POST /trend-reports`) de plus de 180 s, de l'entrée dans leur route à leur réponse, comme l'échéance de 200 s | 24 h | au-dessus de 0 % | 180 s, sous l'échéance de 200 s d'une demande (`docs/ADR/journal-decisions-projet.md:7436-7438`) |

Les fenêtres sont longues: les fiches ne sortent que deux fois par semaine. Sans appel au modèle sur la fenêtre, il
n'y a pas de série, et l'alerte reste normale. De même pour la fidélité sans fait vérifié: elle n'est pas calculée
(le tableau affiche « Aucun appel sur la période ») et l'alerte reste au repos, plutôt qu'une fidélité jamais mesurée
affichée saine.

Deux alertes d'Azure, posées par `infra/main.bicep`, suivent aussi la dépense: le budget du groupe de ressources et,
si `modelAccountName` est donné, les jetons de la ressource du modèle (`infra/main.bicep:159`, `:178`). Le tableau suivant les donne, avec ce que chacune mesure, sa fenêtre, son seuil
et sa source dans le code. Toutes deux écrivent par e-mail à l'adresse du paramètre `budgetContactEmail`
(`infra/main.bicep:161`, `:181`).

| Alerte | Ce qu'elle mesure | Fenêtre | Seuil | Source |
|---|---|---|---|---|
| `budget-kb` | les coûts étiquetés `project=k-b`, hébergement et inférence; l'inférence y entre quand la ressource du modèle porte l'étiquette | le mois (`Monthly`) | 40 € par mois; un e-mail à 50 % et à 100 % des coûts réels, et à 100 % des coûts prévus (`Forecasted`) | `infra/modules/budget.bicep:11-12`, `:20-22`, `:27-58`; `docs/ADR/journal-decisions-projet.md:7414-7418` |
| `alert-kb-model-tokens` | les jetons (`TotalTokens`) de la ressource du modèle, en somme | 24 h glissantes (`P1D`), évaluées toutes les 15 minutes (`PT15M`) | au-dessus de 400 000 jetons | `infra/modules/model-token-alert.bicep:30`, `:41-42`, `:52-55`; `infra/main.bicep:176`; `docs/ADR/journal-decisions-projet.md:7613-7614` |

## Les arguments du choix des outils

Le monitorage de K-B repose sur deux outils, parce qu'il suit deux sortes de données. Les métriques du modèle sont des
nombres émis par le code: elles demandent un tableau de bord et des alertes sur seuil. Les journaux de l'application
sont des lignes de texte: l'hébergement en ligne les recueille sans code de plus. Grafana Cloud reçoit les premières,
Log Analytics les secondes, et deux alertes d'Azure suivent la dépense. Cette section donne, pour chaque outil, ce
qu'il devait faire et les arguments qui l'ont fait retenir.

### Grafana Cloud, pour les signaux de l'API IA

L'API IA émet trois signaux au format d'OpenTelemetry: les métriques, les traces, qui suivent une demande étape par
étape, et les enregistrements de journal (<span lang="en">log records</span>). Le premier critère est donc un outil
qui les reçoit tous les trois. Les critères suivants sont le temps réel, l'alerte sur seuil, l'accessibilité de
l'interface, l'hébergement dans l'Union européenne et le coût (`docs/outils-de-suivi.md:9-17`). Cinq outils ont été
comparés sur ces critères: Application Insights, Grafana Cloud, Langfuse, LangSmith et Honeycomb
(`docs/outils-de-suivi.md:60-72`).

Grafana Cloud est retenu pour ces arguments:

- **il reçoit les trois signaux**: les métriques, les traces (Tempo) et les journaux (Loki) (`docs/outils-de-suivi.md:63-65`);
- **son offre gratuite suffit au volume de K-B** (`docs/outils-de-suivi.md:72`);
- **le temps réel**: l'API IA envoie ses métriques toutes les 60 secondes (`src/k_b/core/config.py:636`), et Grafana
    évalue les cinq règles d'alerte toutes les 5 minutes (`observability/grafana/alert-rules.yaml:23`);
- **la pile est hébergée en Allemagne**, dans l'Union européenne (`docs/registre-traitements.md:128`);
- **l'accessibilité**: Grafana Labs déclare son interface <q><span lang="en">partially conformant with WCAG 2.1 level
    AA</span></q>, c'est-à-dire partiellement conforme au niveau AA des règles d'accessibilité des contenus web
    (`docs/outils-de-suivi.md:70`).

Les outils écartés, et pourquoi:

- **Langfuse et LangSmith**, deux outils de suivi des modèles de langage: leur documentation ne décrit que la
    réception des traces (`docs/outils-de-suivi.md:63`);
- **Honeycomb**: son offre gratuite ne permet que deux règles d'alerte, quand K-B en compte cinq
    (`docs/outils-de-suivi.md:68`);
- **Application Insights**, l'outil de suivi d'Azure: il dépend de deux services d'Azure, `Microsoft.Monitor` et
    `Microsoft.AlertsManagement`, qui ne sont pas enregistrés sur l'abonnement où K-B est déployé, et que le rôle
    Lecteur (<span lang="en">Reader</span>) du compte ne permet pas d'enregistrer (`docs/outils-de-suivi.md:74`);
- **la sortie standard des conteneurs envoyée vers Log Analytics**, avec un classeur et une alerte: pour les mesures
    du modèle, rien n'y est visible avant la mise en ligne, alors que Grafana Cloud reçoit aussi les mesures du bac à
    sable (`docs/ADR/journal-decisions-projet.md:3337-3338`);
- **Grafana et Loki en local, par compose**: il faudrait ensuite un second outil en ligne, ou réécrire les tableaux
    dans un autre langage de requête (`docs/ADR/journal-decisions-projet.md:3339-3340`).

### Log Analytics, pour les journaux de l'application

Log Analytics est le service de journaux d'Azure Monitor. Il est retenu parce qu'Azure Container Apps, le service
d'Azure qui fait tourner les conteneurs de K-B, y envoie leur sortie sans code ni secret de plus: la destination
`azure-monitor` passe par un paramètre de diagnostic de l'environnement, sans la clé partagée de l'espace de journaux
(`docs/ADR/journal-decisions-projet.md:5688-5691`). En local, chaque commande et chaque serveur écrit son journal sur
la sortie d'erreur et dans un fichier; en conteneur, Log Analytics recueille déjà la sortie d'erreur, et le fichier en
double ne servirait à rien ([Journaux de l'application](#journaux-de-lapplication)).

L'espace de journaux de K-B garde les lignes 30 jours et plafonne leur volume à 0,2 Go par jour, ce qui borne le coût
d'un emballement; au-delà du plafond, la collecte s'arrête jusqu'à l'heure de remise à zéro de l'espace
(`infra/modules/log-analytics.bicep:13-22`). Ce choix tient à l'intégration de Log Analytics à Azure Container Apps:
aucun autre outil n'a été comparé pour les journaux.

### Les alertes d'Azure, pour la dépense

Deux alertes d'Azure suivent ce que coûte K-B, hors de Grafana Cloud:

- **le budget de K-B**, 40 euros par mois pour l'hébergement et, quand la ressource du modèle porte l'étiquette
    `project=k-b`, l'inférence; il écrit à la moitié et à la totalité de la dépense du mois, et sur prévision quand la
    dépense prévue atteint le budget (`infra/modules/budget.bicep:11`, `:28-57`;
    `docs/ADR/journal-decisions-projet.md:7417-7418`);
- **l'alerte sur les jetons du modèle**, `alert-kb-model-tokens`, qui lit la métrique `TotalTokens` du déploiement et
    prévient au-delà de 400 000 jetons sur 24 heures glissantes, évaluée toutes les 15 minutes
    (`infra/modules/model-token-alert.bicep:41-55`, `infra/README.md:578-579`).

## Qui lit le tableau et l'alerte

Le tableau suivant donne les deux lecteurs du tableau de bord et des alertes, ce que chacun en fait, et ses outils
d'assistance.

| Lecteur | Ce qu'il en fait | Outil d'assistance |
|---|---|---|
| Sabine, qui exploite K-B | lit le tableau, reçoit seule les alertes par e-mail, corrige | aucun |
| Le jury, pendant la démonstration | lit le tableau et une alerte déclenchée dans le bac à sable | non connus: l'essai d'accessibilité couvre le clavier seul, le lecteur d'écran et le zoom ([l'essai d'accessibilité de Grafana Cloud](https://github.com/SabineLaurent/K-B/blob/main/docs/accessibilit%C3%A9_pour_docu.md)) |

## Lire le tableau

Le tableau s'appelle « K-B, modèle: qualité, coût, alertes », dans le dossier K-B de la pile. Il s'ouvre sur deux
listes: **Source de données** (la source Prometheus de la pile, `grafanacloud-<pile>-prom`, choisie d'office) et
**Environnement** (`production` par défaut, ou `sandbox`). Le tableau a trois rangées de panneaux.

- **Alertes**: pour chaque alerte, un panneau donne la valeur sur sa fenêtre et son état, écrit en toutes lettres,
    « NORMAL » ou « ALERTE: seuil dépassé ». Dessous, une courbe montre la même valeur dans le temps, et son seuil en ligne
    de tirets, nommé dans la légende (« Seuil: 95 % »).
- **Appels et contenu des fiches**: un tableau des appels sur 24 h par étape et par résultat, les jetons, les items
    du classement, et ce que les contrôles ont retiré des fiches.
- **Durées**: la durée d'un appel au modèle (médiane et 95e centile), celle des contrôles et celle de la lecture des
    données.

Aucune information n'y passe par la seule couleur: les valeurs sont écrites sans couleur, un état est un texte, un
seuil est une ligne nommée (tenu par `tests/test_grafana_files.py`). Les valeurs de chaque panneau se lisent aussi en
tableau: menu du panneau, <span lang="en">**Inspect**, **Data**</span>. Un panneau sans appel sur sa fenêtre affiche
« Aucun appel sur la période », et celui des demandes de plus de 180 s, « Aucune demande sur la période ».

Une alerte déclenchée arrive par e-mail. L'état y est écrit (« <span lang="en">Firing</span> »), avec le nom de
l'alerte, son environnement, sa valeur et son seuil.

## Brancher l'export

L'API IA envoie ses mesures et ses traces à Grafana Cloud par OTLP (le protocole d'export d'OpenTelemetry) sur HTTP
quand ses variables d'export sont posées; sans elles, rien n'est exporté (`docs/fiches-veille.md:1892-1896`). Les
chemins de l'interface sont ceux de la documentation de Grafana Cloud ([Sources](#sources)).

1. **La pile**: l'espace de Grafana Cloud qui reçoit et garde les mesures, les journaux et les traces, avec son
    Grafana. Sa région fixe le pays où les données sont gardées: une région de l'Union européenne les y garde. Dans le
    portail Grafana Cloud, <span lang="en">**Add Stack**</span>, un nom, puis une région de l'Union européenne. Celle
    de K-B est `prod-eu-west-2`, chez AWS (<span lang="en">Amazon Web Services</span>), en
    Allemagne, lue sur l'hôte de son adresse OTLP (`docs/registre-traitements.md:128`). Grafana ne change pas la
    région d'une pile existante: une autre région demande une pile neuve, et l'offre gratuite n'a qu'une pile
    ([Limites](#limites)).

2. **L'adresse et l'identifiant**: l'adresse OTLP est celle où l'API IA envoie ses données; l'identifiant
    d'instance est le nom d'utilisateur de l'authentification, que l'en-tête de l'étape 4 associe au jeton. Dans le
    portail, la pile choisie, <span lang="en">**Configure**</span> sur la tuile <span lang="en">**OpenTelemetry**</span>. Y relever l'adresse OTLP, de la forme
    `https://otlp-gateway-<région>.grafana.net/otlp`, et l'identifiant d'instance, le nombre affiché sur la tuile. Ne
    pas y générer de jeton: celui de l'étape 3 a ses droits choisis. Ne pas reprendre non plus les variables
    `OTEL_EXPORTER_OTLP_*` que la tuile propose: `kb serve-ai` refuse toute variable `OTEL_*` (étape 5).

3. **Le jeton**: il prouve à Grafana Cloud que l'envoi vient de K-B. Il naît d'une politique d'accès, qui fixe ses
    droits: écrire les mesures, les journaux et les traces, sur cette seule pile, jusqu'à une date d'expiration. Un
    jeton qui fuirait ne permettrait ni de lire les données, ni d'agir sur une autre pile, et cesserait de valoir à sa
    date (moindre privilège). Dans le Grafana de la pile, <span lang="en">**Administration**, **Users and access**,
    **Cloud access policies**, **Create access policy**</span>. Une politique créée là ne vaut que pour cette pile.
    - <span lang="en">**Display name**</span> et <span lang="en">**Name**</span>: le nom de la politique.
    - <span lang="en">**Scopes**</span>: l'écriture sur les seules lignes des mesures, des journaux et des traces
        (`metrics:write`, `logs:write`, `traces:write`), puis <span lang="en">**Create**</span>.
    - Sous la politique, <span lang="en">**Add token**</span> ouvre la boîte <span lang="en">**Create new
        token**</span>: un nom (<span lang="en">**Display name**</span>), une date d'expiration
        (<span lang="en">**Expiration date**</span>, sous la forme année/mois/jour; vide, le jeton n'expire pas), puis
        <span lang="en">**Create**</span>. Le jeton ne s'affiche qu'une fois. Il ne fait qu'écrire: K-B ne relit rien
        de ce qu'il envoie.

4. **L'en-tête**: l'en-tête d'authentification que l'API IA joint à chaque envoi, `Authorization=Basic%20` suivi du
    base64 de `<identifiant d'instance>:<jeton>`, sans espace ni chevron (`.env.example:161-163`): `%20` tient la
    place de l'espace. Le base64 est un codage, pas un chiffrement: qui voit l'en-tête lit le jeton. Le bloc suivant
    le fabrique donc sans jamais l'afficher. Sur le Mac, dans un terminal interactif, car
    la saisie sans écho (`read -s`) demande un clavier. Remplacer `<instance>` par l'identifiant de l'étape 2, puis
    coller le bloc; s'il reste sur la ligne de commande, Entrée. Quand `Jeton:` s'affiche, coller le jeton, puis
    Entrée. Les accolades font lire tout le bloc au shell avant de lancer `read`, qui attend alors le jeton. Le jeton
    ne passe ni par l'écran ni par l'historique du shell, et l'en-tête va dans le presse-papiers:

    ```sh
    {
        printf 'Jeton: '; read -rs TOKEN; echo
        printf 'Authorization=Basic%%20%s' "$(printf '%s:%s' '<instance>' "$TOKEN" | base64 | tr -d '\n')" | pbcopy
        unset TOKEN
    }
    ```

    L'en-tête porte le jeton en base64, donc lisible. Une fois l'en-tête collé à l'étape 5, vider le presse-papiers:
    `pbcopy < /dev/null`. Si l'historique du presse-papiers de Spotlight est activé (Commande + Barre d'espace, puis
    Commande + 4), l'en-tête y reste: l'effacer là aussi, par le bouton **Plus** à droite du champ de recherche, puis
    **Effacer l'historique** ([Sources](#sources)).

5. **Les variables**: elles disent à `kb serve-ai` où envoyer, avec quel en-tête, et sous quel environnement ranger
    les séries, l'étiquette `deployment_environment_name` que le tableau et les alertes lisent. Sur la même pile, un
    jeton par environnement: pour chacun, l'étape 3 (ou seulement
    <span lang="en">**Add token**</span>, sur une politique qui existe déjà) et l'étape 4. La production a sa
    politique, `kb-production` (#522), le bac à sable la sienne, `kb-sandbox` (`docs/registre-traitements.md:131`).
    - En local, pour le bac à sable, dans `.env.e2e_test` (modèle: `.env.e2e_test.example:25-30`):
        `KB_OTLP_ENDPOINT` (l'adresse de base, sans `/v1/metrics`), `KB_OTLP_HEADERS` (l'en-tête) et
        `KB_DEPLOYMENT_ENVIRONMENT=sandbox`. Un `kb serve-ai` lancé sur le Mac lit les mêmes variables dans le
        `.env` qu'on lui passe (modèle: `.env.example:155-172`).
    - En ligne, pour la production: l'en-tête dans le secret `kb-otlp-headers` du coffre (étape 4
        d'« Appliquer » d'`infra/README.md`; `infra/main.bicep:209`), l'adresse dans le paramètre `otlpEndpoint` de
        la seconde passe (étape 5 d'« Appliquer »; `infra/main.bicep:28-29`, `:333`). `KB_DEPLOYMENT_ENVIRONMENT`
        y vaut `production`, écrit dans le gabarit (`infra/main.bicep:323`).

    `kb serve-ai` ne démarre pas sur un réglage refusé, et nomme sa variable
    (`src/k_b/ai_api/connectors/metrics_export.py:99-151`, `:169-188`, `:198-213`; `src/k_b/core/outbound.py:19-39`;
    `src/k_b/commands/serve_ai_command.py:48-59`). Par exemple:

    - l'adresse ou l'en-tête posé sans l'autre;
    - une adresse qui n'est pas en `https`, qui porte un utilisateur, une requête ou un fragment, ou qui finit par
        `/v1/metrics`, `/v1/traces` ou `/v1/logs`;
    - un en-tête qui n'est pas fait de paires `nom=valeur`;
    - avec l'export, `KB_DEPLOYMENT_ENVIRONMENT` absente, ou ni `sandbox` ni `production`;
    - une variable `OTEL_*`, même sans export.

6. **Vérifier**: la vérification montre que la chaîne marche de bout en bout, de l'API IA jusqu'aux séries dans
    Grafana, avant d'importer le tableau et les règles. Le test de l'export envoie à la pile les mesures d'une demande
    sur le rejeu, depuis un terminal où le `.env` n'est pas chargé:

    ```sh
    uv run --env-file .env.e2e_test pytest -m e2e -k real_export -rs
    ```

    Un jeton refusé fait échouer le test (`tests/e2e/test_real_export.py:119`). Le test vérifie que chaque envoi est
    accepté; l'arrivée des séries se vérifie dans Explore, car le SDK d'OpenTelemetry
    (<span lang="en">Software Development Kit</span>, la bibliothèque qui exporte) compte aussi une réponse 3xx, une
    redirection, comme un succès (`tests/e2e/test_real_export.py:7-8`). Dans Grafana, donc,
    <span lang="en">**Explore**</span>, la source Prometheus de la pile, `grafanacloud-<pile>-prom`, la requête
    `k_b_llm_calls_total{deployment_environment_name="sandbox"}`, <span lang="en">**Run query**</span>: la série de
    la demande y paraît. Le test n'envoie que les mesures (`tests/e2e/test_real_export.py:96-97`): les traces se
    vérifient après une demande à `kb serve-ai`, dans <span lang="en">**Explore**</span>, la source Tempo, par la
    requête `{resource.service.name="k-b-ai-api"}` (`docs/fiches-veille.md:2004`). En ligne, les séries arrivent
    avec la première demande à l'API IA: la durée de lecture des données se mesure à chaque `POST /digests` lu, que
    le modèle soit appelé ou non (`src/k_b/ai_api/routers/digest_router.py:177-178`).

## Installer

Sur la pile qui reçoit les mesures ([Brancher l'export](#brancher-lexport)), par l'interface, sans jeton ni outil à
installer.
Les chemins sont ceux de l'interface de Grafana 13.

1. **Le tableau**: <span lang="en">**Dashboards**, **New**, **Import**, **Upload dashboard JSON file**</span>, le
    fichier `observability/grafana/dashboard.json`. Dossier: K-B (créé au besoin par
    <span lang="en">**Dashboards**, **New**, **New folder**</span>). Garder l'identifiant `k-b-model`: il permet de
    réimporter par-dessus.
2. **Les règles**: <span lang="en">**Alerts & IRM**, **Alerting**, **Alert rules**, **More**, **Import**</span>.
    - <span lang="en">**Import source**</span>: <span lang="en">**Prometheus YAML file**</span>, puis
        <span lang="en">**Upload file**</span>, le fichier `observability/grafana/alert-rules.yaml`.
    - <span lang="en">**Target data source**</span>: la source Prometheus de la pile.
    - <span lang="en">**Target folder**</span>: K-B.
    - <span lang="en">**Pause imported alerting rules**</span>: désactivé, sinon aucune alerte ne part.
    - <span lang="en">**Recording rules, Target data source**</span>: la même source (champ obligatoire; le fichier
        n'a pas de règle d'enregistrement).
    - <span lang="en">**Import**</span>, puis confirmer. Les règles arrivent dans le groupe `k-b-model`, évalué
        toutes les 5 minutes.
3. **L'état en cas d'erreur**: l'import règle « <span lang="en">Alert state if execution error or timeout</span> »
    sur « OK », et une requête en échec laisserait l'alerte au repos. Pour chacune des cinq règles:
    <span lang="en">**Edit**</span>, section <span lang="en">**Configure no data and error handling**</span>,
    <span lang="en">**Alert state if execution error or timeout**</span> sur <span lang="en">**Error**</span>, puis
    <span lang="en">**Save rule**</span>. Une requête en échec déclenche alors une alerte à part, `DatasourceError`.
    Le fichier des règles ne porte pas ce réglage: il est à refaire après chaque import des règles. Une règle
    enregistrée repart sans instance jusqu'à son évaluation suivante, au plus 5 minutes après: une alerte en cours y
    repasse un moment par « <span lang="en">Normal</span> ».
4. **Le point de contact**: <span lang="en">**Alerts & IRM**, **Alerting**, **Notification configuration**,
    **Contact points**</span>. Modifier le point de contact de la politique par défaut:
    <span lang="en">**Add contact point integration**, **Email**</span>, l'adresse d'une utilisatrice de la pile,
    <span lang="en">**Test**</span>, puis <span lang="en">**Save contact point**</span>. L'adresse n'est pas
    versionnée: c'est une donnée personnelle.

## Maintenir

- **Changer un seuil**: changer le nombre qui termine l'expression de la règle dans `alert-rules.yaml`, et le même
    nombre dans le tableau (la valeur d'état `> bool …` et la ligne `vector(…)`).
    `uv run pytest tests/test_grafana_files.py` échoue tant que les deux ne sont pas égaux. Puis réimporter les deux
    fichiers.
- **Une règle changée dans l'interface**: les règles importées restent modifiables dans Grafana. Un changement fait
    là se reporte dans `alert-rules.yaml`, sinon la réinstallation suivante l'efface.
- **Renommer ou ajouter une mesure**: le test compare chaque nom du tableau et des règles aux instruments que
    `ModelMetrics` crée, convertis comme Grafana Cloud le fait; il échoue sur un nom qui n'existe plus.
- **Le jeton d'envoi**: un par environnement (`.env.e2e_test` pour le bac à sable; le secret `kb-otlp-headers` du
    coffre pour la production, refait par la procédure « Pour refaire un seul secret » d'`infra/README.md`). Un refus
    de Grafana se lit dans le journal de l'API IA: `Failed to export 'metrics' batch code: 401`. La date
    d'expiration d'un jeton est celle choisie à sa création, dans le champ
    <span lang="en">**Expiration date**</span> de la boîte <span lang="en">**Create new token**</span> (étape 3 de
    [Brancher l'export](#brancher-lexport)); un jeton expiré est marqué <span lang="en">Expired</span> sur la page
    <span lang="en">**Access Policies**</span> du portail, qui liste toutes les politiques, celles d'une pile
    comprises: <q lang="en">All access policies can be modified from the Access Policy page in the Cloud Portal</q>
    ([Sources](#sources)). Le temps qui reste à un jeton s'affiche sur la page
    <span lang="en">**Cloud access policies**</span> de la pile
    (`docs/journaling/2026-11-20-relire-api10-depuis-le-jeton-de-production.md:24-29`, `:109-110`). Le jeton de la
    production, de la politique `kb-production`, a une durée de 90 jours, choisie à sa création (#522). Avant l'expiration d'un jeton, Grafana écrit aux administrateurs de la pile de sa politique:
    <q lang="en">Warning emails are sent to the admins of the corresponding stack</q>. Ces e-mails partent par
    défaut; la case <span lang="en">**Enable token expiration emails**</span>, page
    <span lang="en">**Settings**</span> des <span lang="en">**Org Settings**</span> du portail, les coupe si elle
    est décochée ([Sources](#sources)).

## Le bac à sable

Le bac à sable déclenche chaque alerte sans modèle réel ni production: il sert les deux API sur la base de test, à
l'heure des tests, avec le rejeu du modèle, et envoie ses mesures à la même pile avec l'environnement `sandbox`
(`tests/e2e/test_sandbox_alerts.py`). Il ne tourne pas dans l'intégration continue.

Depuis un terminal où le `.env` n'est pas chargé, avec `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` dans `.env.e2e_test`:

```sh
make sandbox-alerts
```

Environ 2 min 15. Quatre scénarios, un processus de l'API IA chacun, comme après un réveil en ligne. Le tableau
suivant donne ce que chacun envoie.

| Scénario | Ce qu'il envoie |
|---|---|
| fiches valides | 3 demandes à 65 s d'écart, 12 appels |
| sortie invalide | 1 classement refusé deux fois: `llm_invalid_output` |
| fidélité basse | 3 faits trouvés sur 7 |
| coût au-dessus du budget | au classement, les jetons d'entrée qui coûtent 1,1 fois le budget de l'alerte, sous le plafond de 10 millions qu'une réponse peut déclarer: 916 667 jetons aux prix de gpt-6.1-sol, 2,20 USD pour le classement seul (calculé, pas relevé) |

Chaque test échoue si un envoi échoue. Sans adresse ni en-tête, il est sauté. Les deux alertes du 2026-11-18,
`KbModelCallFailures` et `KbRequestOverDuration`, n'ont pas de scénario: la seconde demanderait une demande de plus
de 180 s.

## Relevé des alertes du bac à sable

Bac à sable lancé par Sabine le 2026-11-08, fin vers 17:45 UTC: 4 tests réussis, chaque envoi accepté. Son scénario
de coût envoyait alors 10 millions de jetons, soit 1,20084 USD. Le tableau suivant donne, pour chacune des trois
alertes, son seuil, la valeur lue dans le tableau de bord, l'heure de son déclenchement et celle de son e-mail.

| Alerte | Seuil | Valeur observée dans le tableau (19:03 UTC) | Déclenchée | E-mail reçu |
|---|---|---|---|---|
| `KbModelInvalidOutputs` | > 0 % | 4,8 % (1 appel sur 21) | oui, 19:15:20 UTC | oui, 19:27 UTC |
| `KbModelLowFidelity` | < 95 % | 73,3 % (11 faits sur 15) | oui, 19:15:20 UTC | oui, 19:27 UTC |
| `KbModelCostOverBudget` | > 1 USD (seuil d'alors) | 1,2641 USD | oui, 19:15:20 UTC | oui, 19:27 UTC |

Le coût observé dépasse les 1,20516 USD du bac à sable: le reste vient de mesures `sandbox` plus anciennes de la
fenêtre de 7 jours (essais locaux du 2 au 6 novembre). L'e-mail de test du point de contact est arrivé à 19:25:12
UTC. Les trois e-mails sont arrivés 12 min 26 s après le déclenchement, une fois le point de contact enregistré, un
par alerte. Le sujet donne l'alerte et son environnement
(<q lang="en">[FIRING:1] KbModelCostOverBudget K-B/alert-rules.yaml (sandbox warning)</q>), le corps son résumé, sa
valeur et ses étiquettes (`deployment_environment_name` vaut `sandbox`).

## Réimport du 2026-11-18

Après le relevé du bac à sable, le tableau et la règle de fidélité ont changé dans le dépôt (la fidélité sans fait
vérifié ne donne plus de donnée), et deux alertes se sont ajoutées le 2026-11-18. Le même jour, vers 11:45 UTC,
Sabine a réimporté les deux fichiers de `main` de ce jour-là, dont le dernier changement est le commit `d2332d0e`:
ils n'ont pas changé depuis. Elle a ensuite refait l'étape 3 d'[Installer](#installer) pour les cinq règles,
« <span lang="en">Alert state if execution error or timeout</span> » sur « <span lang="en">Error</span> ». La pile a
alors les cinq règles dans le groupe `k-b-model`, sans doublon. Le tableau a ses panneaux
« Appels en échec sur 24 h » et « Demandes de plus de 180 s sur 24 h », et le budget de 2 USD. Au même moment,
`KbModelCallFailures` s'est déclenchée dans le bac à sable, à 4,878 %, sur les échecs des essais du 2026-11-17, et
son e-mail est arrivé.

## Relevé de la production du 2026-11-19

Le 2026-11-19, un jeudi, le tableau a été exporté en PDF, sur la fenêtre de 05:18:26 à 17:18:26 UTC. L'export ne
montre pas l'environnement choisi dans la liste **Environnement**: la lecture d'Explore du 2026-11-21, sur la même
journée, le dit. Ce jour-là, `k_b_llm_calls_total` n'a que des séries de la production, toutes à 10:00 UTC, l'heure
du job des fiches de veille, `caj-kb-digest-watch`. Le tableau suivant donne, pour chaque alerte, son seuil, la
valeur de l'export et son état.

| Alerte | Seuil | Valeur dans l'export | État |
|---|---|---|---|
| `KbModelInvalidOutputs` | > 0 % | 0,0 % | NORMAL |
| `KbModelLowFidelity` | < 95 % (provisoire) | 99,4 % | NORMAL |
| `KbModelCostOverBudget` | > 2 USD | 0,3358 USD | NORMAL |
| `KbModelCallFailures` | > 0 % | 0,0 % | NORMAL |
| `KbRequestOverDuration` | > 0 % | 0,0 % | NORMAL |

La courbe du coût monte d'une marche vers 10:00 UTC. Le panneau des demandes de plus de 180 s affiche 0,0 %, et non
« Aucune demande sur la période », le texte d'un panneau sans demande.

Sabine a lu Explore le 2026-11-21, entre 02:27 et 02:38 UTC, sur la plage du 2026-11-19 00:00 au 2026-11-20
00:00 UTC.

- Les noms `k_b_llm_calls_total`, `k_b_request_duration_seconds_bucket`, `_count` et `_sum` ont chacun une série,
    à 10:00 UTC, toutes du même environnement.
- En légende <span lang="en">Verbose</span>, `k_b_llm_calls_total` a quatre séries, toutes
    `deployment_environment_name="production"`, `gen_ai_request_model="gpt-6.1-sol"`, `job="k-b-ai-api"`,
    `k_b_outcome="ok"` et `k_b_schema_valid="true"`. Leur étape, `k_b_stage`, vaut `classify`, `select`, `write` et
    `write_trends`, pour 4, 1, 9 et 5 appels: les nombres du tableau « Appels sur 24 h, par étape et par résultat »
    de l'export.

## Limites

- **Le décompte par `max_over_time`**. Chaque processus de l'API IA est une série neuve, dont `increase()` ne voit
    pas le premier incrément: dans le bac à sable, `increase` comptait 12 appels sur 21, `max_over_time` les 21. Le
    tableau et les règles somment donc le maximum de chaque série sur la fenêtre, depuis le début de son processus. Un
    processus encore vivant au début de la fenêtre y compte aussi ses appels d'avant; en ligne, un processus ne vit
    que quelques minutes (l'API tombe à zéro réplique). Deux cas faussent donc le décompte: un `kb serve-ai` local
    laissé ouvert plus longtemps que la fenêtre (une sortie invalide de la veille garde l'alerte déclenchée), et un
    `minReplicas` de l'API IA au-dessus de 0.
- **Une série s'éteint 5 minutes après son processus**: aucun panneau ne lit une valeur instantanée.
- **Une seule pile**: l'offre gratuite n'en a qu'une; le bac à sable est un environnement de la même pile.
- **E-mail aux seules utilisatrices de la pile**: depuis le 2026-04-20, un compte gratuit nouveau n'envoie d'e-mail
    qu'aux utilisatrices de son instance (incident `xg2h8ht1d44n` de status.grafana.com, clos le 2026-04-24); les
    <span lang="en">webhooks</span> marchent toujours.
- **Un changement d'offre supprime les jetons sans prévenir**: le 2026-11-08, le passage de la pile de l'essai Pro à
    l'offre gratuite a supprimé ses <span lang="en">access policies</span>; le bac à sable a reçu `401 Unauthorized`
    jusqu'au jeton neuf. Le jeton de la production a été refait de même (#522, close le 2026-11-12).
- **Rétention de 14 jours** sur l'offre gratuite: aucune fenêtre ne la dépasse.
- **Ce que la fidélité mesure aujourd'hui** (2026-11-08): une recherche faite sur le jeu de #479 rejoué
    par les fonctions de K-B, trouve les 26 faits présents dans l'item cité, donc aucune invention; les 12 faits
    « non trouvés » manquent seulement dans le texte français de la fiche: des CVE
    (<span lang="en">Common Vulnerabilities and Exposures</span>, les identifiants publics des vulnérabilités) non
    écrites, des faits traduits. La fidélité mesure donc surtout l'écart entre la consigne, qui demande un texte en
    français, et le contrôle, qui ne compte un fait trouvé que s'il est, mot pour mot après normalisation, un CVE ou
    un GHSA (<span lang="en">GitHub Security Advisory</span>) sous sa forme canonique, à la fois dans le texte
    français de son affirmation et dans l'anglais de l'item qu'il désigne. Son seuil de 95 % est provisoire.
- **L'état en cas d'erreur n'est pas dans le fichier**: l'import des règles au format Prometheus règle
    « <span lang="en">Alert state if execution error or timeout</span> » sur « OK », comme l'absence de données (vu
    dans la règle importée le 2026-11-08). Le passer sur « <span lang="en">Error</span> » est l'étape 3
    d'[Installer](#installer), faite à la main: une réinstallation qui l'oublie laisse une requête en échec sans
    alerte.
- **Le coût est une estimation**: tout appel est compté aux prix de `src/k_b/core/config.py`, le rejeu compris.
- **L'installation est manuelle**: deux imports et un point de contact, sans jeton. L'API de <span lang="en">provisioning</span> des
    alertes de Grafana, qui l'automatiserait, est marquée « <span lang="en">deprecated</span> » et demanderait un
    secret.

## Journaux de l'application

Le tableau de bord et les alertes de Grafana suivent le modèle, et les alertes d'Azure la dépense; l'application se
suit par ses journaux: ceux de
`kb`, de `kb serve-data` (l'API de données), de `kb serve-ai` (l'API IA) et de `kb serve-web` (le site). En local, ils ne demandent rien à
installer: `kb` les écrit par le module `logging` de Python. En ligne, ils vont dans l'espace Log Analytics `log-kb`,
qu'`infra/main.bicep` crée. Aucune alerte ne les lit ([Limites des journaux](#limites-des-journaux)).

### Ce que l'application écrit

Le tableau suivant donne six sorties de l'application: ce que chacune contient, où elle va en local et en ligne, et
son renvoi au code ou aux règles.

| Journal | Ce qu'il contient | En local | En ligne | Code |
|---|---|---|---|---|
| journal de `kb` | le déroulé d'une commande, réussites et échecs, une ligne datée par événement | sortie d'erreur et `<KB_DATA_DIR>/logs/kb.log` | sortie d'erreur du job, dans `log-kb` | `src/k_b/commands/run_log.py:24-26`, `:73-96` |
| journal de `kb serve-data` | son démarrage, ses clients, son arrêt, une ligne par requête | sortie d'erreur et `<KB_DATA_DIR>/logs/kb-serve-data.log` | sortie d'erreur de `ca-kb-data-api`, dans `log-kb` | `src/k_b/cli.py:66-71`, `src/k_b/commands/serve_data_command.py:41-42`, `src/k_b/data_api/app.py:71` |
| journal de `kb serve-ai` | de même, pour l'API IA | sortie d'erreur et `<KB_DATA_DIR>/logs/kb-serve-ai.log` | sortie d'erreur de `ca-kb-ai-api`, dans `log-kb` | `src/k_b/cli.py:66-71`, `src/k_b/commands/serve_ai_command.py:74-93`, `src/k_b/ai_api/app.py:96` |
| journal de `kb serve-web` | son démarrage, le réveil de l'API de données, une ligne par requête | sortie d'erreur et `<KB_DATA_DIR>/logs/kb-serve-web.log` | sortie d'erreur de `ca-kb-web`, dans `log-kb` | `src/k_b/cli.py:72-76`, `src/k_b/core/config.py:172`, `src/k_b/commands/serve_web_command.py:27-33`, `:49-50`, `:64-66`, `src/k_b/web/app.py:64` |
| ligne de mesure d'un appel au modèle | une ligne JSON par appel: durée, jetons, coût estimé, états; ni texte ni clé | sortie standard de `kb serve-ai`, aucun fichier | sortie standard de `ca-kb-ai-api`, dans `log-kb` | `src/k_b/ai_api/observability/metrics.py:1-2`, `:35-51` |
| résultat d'une commande | ce que la commande affiche par `print`, le bilan d'un import par exemple | sortie standard | sortie standard du job, dans `log-kb` | `.claude/rules/conventions.md`, règle 3 |

Deux autres sorties ne sont pas des journaux de fonctionnement. Le journal d'import,
`<KB_DATA_DIR>/journals/import-journal-<AAAA-MM-JJTHHMMSSZ>.jsonl` (`src/k_b/core/config.py:172-173`,
`src/k_b/etl/pipeline.py:35`), dit ce qu'un import a décidé des données ([la fiche des données](donnees.md), « Le script
d'agrégation et d'import: `kb import` »). Les traces et les
enregistrements de l'API IA partent vers Grafana Cloud avec ses mesures, sous le même réglage
(`docs/architecture-api-ia.md`, « Les métriques et les journaux »).

### Lire une ligne

Une ligne s'écrit `<date> <niveau> <module>: <message>`, et `<date> <niveau> <module>: trace_id=<identifiant> <message>`
pendant une requête de l'une des deux API; la date en ISO 8601, en UTC, à la seconde, avec son `Z`
(`src/k_b/commands/run_log.py:97-99`). Le niveau est INFO ou au-dessus (`:108`). Les bibliothèques n'écrivent
qu'à partir d'un niveau supérieur, car aux niveaux inférieurs elles citent ce que `kb` ne journalise pas: `httpx2` dès
WARNING (l'URL du fournisseur du modèle); `azure` et `urllib3` dès ERROR (l'URL d'un blob, qui porte le titre d'un
clip); `psycopg` et `psycopg_pool` dès ERROR (l'hôte, l'utilisateur et la base) (`:38-62`, `:109-110`). uvicorn écrit
par les mêmes sorties, sans son propre journal d'accès (`log_config=None`, `access_log=False`:
`src/k_b/commands/serve_data_command.py:55-56`, `src/k_b/commands/serve_ai_command.py:113-114`). Le message d'une
ligne écrite par une bibliothèque, uvicorn compris, est cité comme une valeur observée: entre guillemets, ses retours
à la ligne et ses caractères de contrôle échappés, coupé à 300 caractères (`src/k_b/commands/run_log.py:63-68`,
`:122-151`). Il ne peut donc pas écrire une seconde ligne datée (`tests/commands/test_run_log.py:233`). Une ligne de
`kb` garde son message tel quel (`tests/commands/test_run_log.py:283`): `kb` cite lui-même chaque valeur qu'il
journalise (`.claude/rules/conventions.md`, règle 3).

La ligne d'une requête donne la méthode, le gabarit de la route (`/items/{item_id}`, jamais le chemin reçu), le
statut, la durée en ms, le nom du client et l'identifiant de la requête, rendu aussi dans l'en-tête `X-Request-ID`
de la réponse (`src/k_b/core/api_request_log.py:27-33`, `:56-81`). Jamais la clé, une valeur de paramètre ni un
chemin brut (`:1-2`). Un champ vaut `-` quand rien n'a été vu: aucune route reconnue, aucun client nommé par une clé
valide, aucune réponse envoyée (`:18-19`; la liste des cas: `docs/specs-api.md`, « Journal »). Un `/health` qui
répond 200 n'est pas écrit; une sonde en échec l'est (`:36-38`). Une erreur de la base reprend le même identifiant
(`src/k_b/data_api/errors.py:46-56`), et la ligne de mesure de l'API IA aussi, en JSON (`"request_id": "…"`,
`src/k_b/ai_api/observability/metrics.py:65`): il relie une demande à ses erreurs et à ses appels au modèle, dans
une même API. Chaque API tire le sien (`src/k_b/core/api_request_log.py:27`): une demande de `kb digest` a un
identifiant dans l'API IA, et chacune des requêtes que l'API IA fait alors à l'API de données (une liste par sorte,
un détail par item) a le sien (`src/k_b/ai_api/connectors/data_api_client.py:211-214`). L'identifiant de trace les
relie: chaque ligne écrite pendant une requête de l'une des deux API le porte après le nom de son journal (`trace_id=`,
`src/k_b/commands/run_log.py:37`, `:122-134`). L'API IA le tire pour chaque demande et l'envoie à l'API de données
dans l'en-tête `traceparent` du W3C (<span lang="en">World Wide Web Consortium</span>) <span lang="en">Trace Context</span>,
dont les lignes le reprennent (`src/k_b/core/trace_context.py:27-44`; `src/k_b/ai_api/connectors/data_api_client.py:345-352`).

Les deux premières lignes viennent de `logs/kb.log`, sur un `KB_DATA_DIR` neuf: `kb create-db`, `kb import`, puis
`kb purge`. Les deux suivantes viennent des deux API construites par `kb serve-data` et `kb serve-ai`, servies par uvicorn en HTTP (<span lang="en">Hypertext
Transfer Protocol</span>) réel sur 127.0.0.1, dans un seul processus, sur la
base de test et avec le rejeu du modèle (`tests/commands/test_live_apis.py`). La première est une requête de l'API IA
à l'API de données, la seconde la demande de `kb digest` à l'API IA: elles portent le même identifiant de trace.

```text
2026-11-11T14:37:27Z INFO k_b.cli: import started
2026-11-11T14:37:28Z INFO k_b.purge.run_records: logs and journals purge: 0 files older than 6 months deleted
2026-11-22T00:46:36Z INFO k_b.core.api_request_log: trace_id=07365d77d4dcfa1b6582835926dd526c request method='GET' route=/items status=200 duration_ms=6 client=AI_DIGEST request_id=d1ffc68f-d1be-41d0-b4d5-0015a6d783b3
2026-11-22T00:46:36Z INFO k_b.core.api_request_log: trace_id=07365d77d4dcfa1b6582835926dd526c request method='POST' route=/digests status=200 duration_ms=43 client=KB_DIGEST request_id=9a023c6c-3e41-45d2-8c31-151dbe4b5ce4
```

### En local: installer et configurer

Rien à installer. Deux variables règlent les journaux. `kb` ne lit jamais un fichier `.env` lui-même: elles viennent
de l'environnement, ou d'un fichier passé par `uv run --env-file .env kb …` (`src/k_b/commands/environment.py:21-22`).

- `KB_DATA_DIR`, obligatoire et sans défaut, un dossier qui existe déjà. Absente, la commande s'arrête sur
    `error: KB_DATA_DIR must point to the data directory` (`src/k_b/commands/environment.py:32-37`); un chemin qui
    n'est pas un dossier, sur `error: KB_DATA_DIR is not an existing directory` (`:38-42`); les deux en code 2, sans
    rien lancer (`src/k_b/cli.py:110-111`). Les journaux vont dans son dossier `logs/`
    (`src/k_b/core/config.py:164-171`), créé au premier lancement (`src/k_b/commands/run_log.py:84-85`).
- `KB_LOG_TO_FILE`, `true` par défaut (`src/k_b/core/config.py:223-225`), lue par
    `src/k_b/commands/environment.py:46-58`: `false` écrit sur la sortie d'erreur seule, sans fichier. Une autre
    valeur arrête la commande en code 2, sans rien lancer: `error: KB_LOG_TO_FILE: 'oui' neither true nor false`.
    Son modèle commenté est dans `.env.example:59-61`.

Une commande dont le fichier de journal ne s'ouvre pas ne se lance pas: `error: log file not opened: …`, code 2
(`src/k_b/cli.py:213-229`). `kb openapi` et le `--dry-run` des routines n'écrivent aucun journal
(`src/k_b/cli.py:103-116`). Chaque API et le site ont leur fichier: une rotation faite par une autre commande
laisserait un processus long écrire dans le fichier de la veille (`src/k_b/cli.py:66-67`; `docs/specs-api.md`, « Journal »).

**Rotation et durée.** Chaque fichier tourne à la première ligne écrite après minuit UTC: ses lignes passent dans
`kb.log.<AAAA-MM-JJ>`, au jour de ces lignes (de même pour les trois autres), et les nouvelles vont dans un `kb.log`
neuf (`src/k_b/commands/run_log.py:86-96`; nom daté: `src/k_b/purge/run_records.py:20-30`). La rotation ne supprime
rien. Le fichier courant, sans date dans son nom, n'est jamais purgé (`src/k_b/purge/run_records.py:60-65`).
`kb purge`, dernière de ses purges, supprime les journaux et les journaux d'import dont le jour du nom a plus de
6 mois (`src/k_b/purge/run_records.py:36-50`, appelée par `src/k_b/purge/all_purges.py:63`; durée:
`src/k_b/core/config.py:174-178`). En local, elle se lance à la main. En ligne, le job `caj-kb-daily-routine` la
lance: `kb daily-routine` l'enchaîne après `kb import` (`src/k_b/commands/daily_routine_command.py:63`), et ne
démarre pas sans les réglages du job, dont `AZURE_CLIENT_ID` (`src/k_b/commands/daily_routine_command.py:80-84`,
`src/k_b/exchange/storage.py:106-110`).

### En local: lire

```sh
tail -f "$KB_DATA_DIR/logs/kb-serve-ai.log"                  # suivre l'API IA
grep -E " (WARNING|ERROR) " "$KB_DATA_DIR"/logs/kb*.log*   # avertissements et échecs, des commandes et des API, jours passés compris
grep "request_id=<id>" "$KB_DATA_DIR"/logs/kb-serve-*.log    # les lignes d'une requête, par son X-Request-ID
grep "trace_id=<id>" "$KB_DATA_DIR"/logs/kb-serve-*.log      # les lignes d'une demande dans les deux API, par sa trace
```

Un avertissement nomme un état, un délai de la base dépassé par exemple (`query_timeout`,
`src/k_b/data_api/errors.py:55`). La trace d'une erreur imprévue suit sa ligne datée, sur des lignes sans date
(`.claude/rules/conventions.md`, règle 3): `grep -A` la montre avec sa ligne. Le motif `request_id=` trouve la ligne
de la requête et les autres lignes de la même requête (`database_error`, `query_timeout`, `internal_error`:
`docs/specs-api.md:140-142`; l'échec de lecture de l'API IA: `src/k_b/ai_api/routers/digest_router.py:173-175`);
une ligne de mesure porte `"request_id"`, sur la sortie standard.

Les lignes de mesure ne vont que sur la sortie standard de `kb serve-ai`: aucun fichier ne les garde
(`src/k_b/ai_api/observability/metrics.py:50-51`). Les mêmes mesures partent vers Grafana Cloud quand l'export est
réglé (les sections du monitorage du modèle, de [Ce que le monitorage suit](#ce-que-le-monitorage-suit) à
[Limites](#limites)).

### En ligne: installer et configurer

Tout est posé par `infra/main.bicep`, qui s'applique à la main (`infra/README.md`, « Appliquer »):

- l'espace `log-kb` (`infra/modules/log-analytics.bicep:5-23`): 30 jours de rétention, et un plafond de 0,2 Go par
    jour (`:13-22`): atteint, la collecte s'arrête jusqu'à l'heure de remise à zéro, propre à chaque espace et non
    réglable (Microsoft Learn, « <span lang="en">Set daily cap on Log Analytics workspace</span> »);
- l'environnement `cae-kb` y envoie les journaux des conteneurs par Azure Monitor, sans clé partagée, par le
    paramètre de diagnostic `logs-to-log-kb`, en deux tables: `ContainerAppConsoleLogs` (sortie standard et sortie
    d'erreur des conteneurs) et `ContainerAppSystemLogs` (démarrage, tirage de l'image, réveil d'une app à 0
    réplique) (`infra/modules/container-apps-environment.bicep:25-29`, `:49-69`; `infra/README.md:322-323`);
- l'image règle `KB_LOG_TO_FILE=false` et `PYTHONUNBUFFERED=1` (`Dockerfile:42-47`): en conteneur, pas de fichier
    de journal, la sortie d'erreur est le journal, et une ligne de la sortie standard part aussitôt. Aucune pièce
    d'`infra/` ne change `KB_LOG_TO_FILE`. Le `KB_DATA_DIR` en ligne est un dossier de l'image, vidé à chaque
    démarrage, sauf pour `caj-kb-daily-routine` et `caj-kb-digest-watch`, qui y montent le partage `job-data`
    (`infra/main.bicep:69-71`): les journaux d'import de la routine y restent, pas le journal de
    fonctionnement d'un job.

Y écrivent les deux API, `ca-kb-data-api` et `ca-kb-ai-api` (`infra/main.bicep:203`, `:238`), le site, `ca-kb-web`
(`infra/main.bicep:79`, `:349-354`), et les quatre jobs:
`caj-kb-smoke-test` (`infra/modules/smoke-test-job.bicep:30`), `caj-kb-migrate-database`
(`infra/modules/migrate-database-job.bicep:59`), `caj-kb-daily-routine`, qui lance `kb daily-routine` chaque jour
à 08:00 UTC (`infra/modules/daily-routine-job.bicep:59`, `:77-78`), et `caj-kb-digest-watch`, qui lance
`kb digest-watch` le lundi et le jeudi à 10:00 UTC par défaut
(`infra/modules/digest-watch-job.bicep:48`, `:58`, `:65`; `infra/main.bicep:32`, `:437`).

Pour lire `log-kb`: l'Azure CLI, connectée à l'abonnement (`az login`), et son extension `log-analytics`, qui porte
`az monitor log-analytics query` (`az extension add --name log-analytics`; message
<q lang="en">This command is from the following extension: log-analytics</q>, avec azure-cli 2.92.0 et l'extension
1.0.0b3). Le rôle Lecteur (`*/read`) suffit à lire
`log-kb` (`docs/registre-traitements.md:234`, source Microsoft Learn: `:328`). `RG` se règle comme pour
l'application de l'infrastructure (`infra/README.md`, « 0. Les variables du shell »); `az account show` doit être
l'abonnement du groupe de ressources (`infra/README.md:415`).

### En ligne: lire

Ce qu'a écrit un job se lit dans `log-kb` <q>quelques minutes après sa fin</q> (`infra/README.md:310`); le délai
d'arrivée des lignes d'une API n'est pas relevé. Les journaux d'une API:

```sh
RG=<groupe de ressources>
WS=$(az monitor log-analytics workspace show -n log-kb -g "$RG" --query customerId -o tsv)
az monitor log-analytics query -w "$WS" -o tsv \
  --analytics-query "ContainerAppConsoleLogs | where TimeGenerated > ago(1h) and ContainerAppName == 'ca-kb-ai-api' | order by TimeGenerated asc" \
  --query "[].[TimeGenerated, Stream, Log]"
```

`ca-kb-data-api` à la place pour l'API de données; `isnotempty(JobName)` pour les jobs (`infra/README.md:314-317`),
`JobName == 'caj-kb-daily-routine'` pour la routine (`:1064-1065`); `ContainerAppSystemLogs` pour le démarrage et le
réveil. La colonne `Stream` vaut `stdout` ou `stderr`: les lignes de mesure de l'API IA sont sur `stdout`.
`az containerapp job logs show` ne lit qu'une exécution en cours (`infra/README.md:310-311`).

Relevé le 2026-11-11 à 14:38 UTC, en lecture seule, sur les 30 derniers jours: `ca-kb-data-api`, 100 lignes, et
`ca-kb-ai-api`, 130, toutes sur `stderr`; `caj-kb-daily-routine`, 310 lignes sur `stderr` et 150 sur `stdout`, la
dernière le 2026-11-11 à 08:01 UTC; `caj-kb-smoke-test`, 35 sur `stderr` et 62 sur `stdout`;
`caj-kb-migrate-database`, 5 sur `stdout`. Aucune ligne `stdout` pour `ca-kb-ai-api`: pas de ligne de mesure sur la
période.

### Limites des journaux

- **Aucune alerte ne lit les journaux**: ni l'échec d'un job, ni une source muette, ni des réponses 5xx, ni
    `/health` en ligne. Elles sont portées par #282, ouverte. Un échec ne se voit qu'en lisant le journal.
- **En local, rien ne lance `kb purge` de lui-même**: une machine qui ne lance que les API, ou `kb import` sans
    `kb purge`, ne purge jamais `logs/`.
- **La purge des journaux passe en dernier, et la première purge qui échoue arrête les suivantes**, par choix
    (`src/k_b/purge/all_purges.py:1-3`, `:63`): sans base, `kb purge` ne lance aucune purge (`:49`, `:69-71`), et une
    purge qui échoue avant celle des journaux laisse `logs/` et `journals/` tels quels. Pour réduire le risque: la
    purge suivante relance toutes les purges (`:3`); en ligne, l'échec d'une étape donne son code à la routine
    (`src/k_b/commands/job_routine.py:2`), et l'exécution du job se lit `Failed` (`infra/README.md:1059`).
- **En ligne, `log-kb` est la seule copie**: aucun fichier dans le conteneur, et la purge à 6 mois ne s'y applique
    pas. Log Analytics efface après 30 jours; au-delà de 0,2 Go, la collecte s'arrête jusqu'à l'heure de remise à
    zéro du plafond; les lignes envoyées entre-temps ne sont pas reçues.
- **Les lignes de mesure ne sont gardées nulle part en local**: la sortie standard de `kb serve-ai` va au terminal.
- **Un seul `kb serve-data` et un seul `kb serve-ai` par `KB_DATA_DIR`**: deux, sur deux ports, écriraient le même
    fichier (`docs/specs-api.md`, « Journal »; [Utiliser K-B](utilisation.md), « La lancer et lui demander des
    comptes rendus »).

## Sources

- Grafana Cloud, conversion OTLP (le protocole d'export d'OpenTelemetry) et promotion des attributs de ressource:
    [page de Grafana Cloud sur le format OTLP](https://grafana.com/docs/grafana-cloud/send-data/otlp/otlp-format-considerations/)
    et
    [page de Grafana Cloud sur la promotion des attributs de ressource](https://grafana.com/docs/grafana-cloud/send-data/otlp/promote-resource-attributes/).
- Restrictions des alertes d'un compte gratuit:
    [incident `xg2h8ht1d44n` de la page d'état de Grafana](https://status.grafana.com/incidents/xg2h8ht1d44n).
- Import de règles Prometheus dans des règles gérées par Grafana:
    [page de Grafana sur la migration des règles d'alerte](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/alerting-migration/).
- API de <span lang="en">provisioning</span> des alertes, « <span lang="en">deprecated</span> »:
    [page de Grafana sur l'API HTTP de <span lang="en">provisioning</span>](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/).
- État d'une règle en cas d'erreur de requête (« <span lang="en">Error</span> » par défaut pour une règle créée dans
    Grafana, `DatasourceError`): `docs/sources/alerting/guides/connectivity-errors.md` et
    `docs/sources/shared/alerts/modify-error-state.md` du dépôt grafana/grafana, version v13.3.0.
- Repères des règles de champ d'un tableau (`byFrameRefID`):
    `packages/grafana-data/src/transformations/matchers/ids.ts` du dépôt grafana/grafana, version v13.3.0.
- Noms des séries et comportement d'`increase`: relevés dans Explore; les trois noms de la durée d'une demande, sur
    les séries de la production ([le relevé de la production](#releve-de-la-production-du-2026-11-19)).

Pour [Brancher l'export](#brancher-lexport), l'expiration d'un jeton et Explore:

- Création d'une pile, <span lang="en">**Add Stack**</span>:
    [page de Grafana Cloud sur la création d'une pile](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/account-management/cloud-stacks/create-update-stacks/).
- Région d'une pile, que Grafana ne change pas:
    [page de Grafana Cloud sur les régions](https://grafana.com/docs/grafana-cloud/account-management/regional-availability/);
    `prod-eu-west-2`, chez AWS, en Allemagne:
    [page de Grafana Cloud sur les adresses des régions](https://grafana.com/docs/grafana-cloud/security-and-account-management/region-url-formats/).
- Tuile <span lang="en">**OpenTelemetry**</span>, <span lang="en">**Configure**</span>, forme de l'adresse OTLP et
    variables `OTEL_EXPORTER_OTLP_*` que la tuile propose:
    [page de Grafana Cloud sur l'envoi en OTLP](https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/).
- Identifiant d'instance affiché sur la tuile, sans y générer de jeton:
    [page de Grafana Cloud qui décrit la tuile <span lang="en">OpenTelemetry</span> et son identifiant d'instance](https://grafana.com/docs/grafana-cloud/observe-and-act/agent-observability/get-started/grafana-cloud/).
- <span lang="en">**Create access policy**</span>, droits d'écriture par signal,
    <span lang="en">**Add token**</span>, la boîte <span lang="en">**Create new token**</span> et son champ
    <span lang="en">**Expiration date**</span>, jeton affiché une fois:
    [parcours de Grafana sur la politique et son jeton](https://grafana.com/docs/learning-paths/connect-agent-to-agent-observability/create-access-policy-and-token/)
    et
    [page de Grafana Cloud sur la création d'une politique](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/create-access-policies/).
- Une ligne par signal dans <span lang="en">**Scopes**</span>:
    [page de Grafana Cloud sur la politique des traces](https://grafana.com/docs/grafana-cloud/send-data/traces/set-up/add-access-policy/).
- Politique d'une pile, dont les jetons ne valent que pour elle; jeton expiré marqué
    <span lang="en">Expired</span> sur la page <span lang="en">**Access Policies**</span>; e-mails avant l'expiration
    d'un jeton, leurs destinataires et leur réglage dans les <span lang="en">**Org Settings**</span>:
    [page de Grafana Cloud sur les politiques d'accès](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/).
- <span lang="en">**Explore**</span>, la source `grafanacloud-<pile>-prom` et <span lang="en">**Run query**</span>:
    [page de Grafana Cloud sur l'analyse des séries dans Explore](https://grafana.com/docs/grafana-cloud/account-management/billing-and-usage/control-prometheus-metrics-usage/usage-analysis-explore),
    [page de Grafana Cloud sur ses sources de données](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources-in-cloud/)
    et [page de Grafana sur l'éditeur de requêtes d'Explore](https://grafana.com/docs/grafana/latest/visualizations/explore/query-editor/).
- Historique du presse-papiers de Spotlight, son ouverture et son effacement:
    [aide d'Apple, « Effectuer une recherche dans l'historique du presse-papiers à l'aide de Spotlight sur Mac »](https://support.apple.com/fr-fr/guide/mac-help/mchl40d5b86b/mac).
