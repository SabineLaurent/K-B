# Monitorage du modèle: tableau de bord et alertes

« Rédaction de la documentation technique des procédures d'installation, de maintenance du monitorage du modèle. » — C11

« Rédaction de la documentation utilisateur, pour l'utilisation du monitorage. » — C11

Écrit le 2026-11-08 pour #164. Le monitorage du modèle tient dans deux fichiers du dépôt, que Grafana Cloud importe
tels quels: le tableau de bord, `observability/grafana/dashboard.json`, et les trois règles d'alerte,
`observability/grafana/alert-rules.yaml`. Les mesures viennent de l'API IA, qui les envoie en OpenTelemetry depuis
#162 (`docs/fiches-veille.md`, « Les mêmes mesures en OpenTelemetry (#162) »). Le choix de l'outil est écrit dans
`docs/outils-de-suivi.md`.

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
