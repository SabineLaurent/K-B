# Outils de suivi : la comparaison qui fonde le choix de Grafana Cloud

Écrit le 2026-11-08 pour #163. Les faits sur K-B renvoient au commit `c5e6135` ; les pages des
outils ont été lues le 2026-11-08, sauf mention contraire (section « Sources »).

## Ce que ce document fait

L'outil est déjà choisi : Grafana Cloud, en OpenTelemetry, dès le premier temps (décision de Sabine
du 2026-10-20 ; journal ADR, « Squelette E1 E3 : cadrage du 20/10 », décision 4). Le 2026-11-08,
Sabine a précisé : **Grafana Cloud seul pour le rendu du 25/11, Application Insights repris après
le rendu**. Ce document écrit la comparaison qui fonde ce choix, selon les critères de « Wiki :
métriques » (journal ADR, 2026-10-12) : temps réel, alerte sur seuil, accessibilité de l'interface,
région UE, coût. Il ne tranche rien : un écart entre le tableau et le choix est écrit dans
« Écarts au choix » et remonté à time-knight, qui le porte à Sabine.

Outils comparés : les quatre outils en cloud du critère de #163 (Application Insights, Grafana
Cloud, Langfuse Cloud en région UE, LangSmith en région UE), plus Honeycomb, que le commentaire du
2026-10-24 sur #163 ajoute au tableau (accord de Sabine à la validation du plan, le 2026-11-08).

## Ce dont K-B a besoin

L'API IA émet trois signaux OpenTelemetry, en OTLP (HTTP, protobuf, gzip), vers une URL de base et
un en-tête : c'est ce qu'un outil doit recevoir pour que seuls l'URL et le jeton changent d'un
outil à l'autre.

| Besoin | Ce que K-B émet | Où |
|---|---|---|
| Métriques du modèle | 14 instruments : durée d'un appel, jetons, appels et leur état, coût estimé, compteurs des contrôles et de la fidélité, durée de lecture de la veille | `src/k_b/ai_api/observability/metric_instruments.py:47`, `:53`, `:58` (les trois noms `gen_ai.*`) ; `docs/fiches-veille.md`, « Les mêmes mesures en OpenTelemetry (#162) » |
| Traces | une trace par `POST /digests`, un span par étape, un span `chat <model>` par requête au modèle ; tous gardés | `src/k_b/ai_api/tracing.py:136` (`step`) ; `src/k_b/ai_api/connectors/trace_export.py:72` (`ALWAYS_ON`) |
| Cheminement d'un appel dans l'API IA | l'arbre `POST /digests` → `read_watch` → `classify_batch` → `chat` → `write_subject` → `chat`, et la raison de chaque affirmation retirée, en enregistrement de journal `gen_ai.evaluation.result` rattaché à son `chat` | `src/k_b/ai_api/tracing.py:45` ; `docs/fiches-veille.md`, « Traces de `POST /digests` (#345) » |
| Contenu d'un appel au modèle | un enregistrement `gen_ai.client.inference.operation.details` par requête, sous `KB_TRACE_CONTENT` (`none` par défaut, `anomalies`, `all`) ; `all` refusé au démarrage en production ; en ligne, `none` | `src/k_b/ai_api/tracing.py:54` ; `src/k_b/core/config.py:539` ; `src/k_b/ai_api/connectors/metrics_export.py:51`, `:186-187` ; `infra/main.bicep:217` |
| Trois chemins OTLP | `/v1/metrics`, `/v1/traces`, `/v1/logs` sous une seule URL de base ; aucune variable `OTEL_*` acceptée | `src/k_b/ai_api/connectors/metrics_export.py:52`, `:54-56` |
| Envoi | métriques toutes les 60 s ; spans et journaux par lots, chaque seconde | `src/k_b/core/config.py:516` ; `docs/fiches-veille.md:1538` |
| Copie hors outil | une ligne JSON par appel au modèle sur la sortie standard, qui reste (journal ADR, « Wiki : métriques », révisée le 2026-10-15) | `src/k_b/ai_api/observability/metrics.py:50-51` |
| Restitution | tableaux de bord et alertes, à construire dans l'outil choisi (#164) | — |

La décision ouverte « texte envoyé à l'outil de suivi » (journal ADR, « Décisions encore
ouvertes ») est tranchée pour l'API IA par #347, le 2026-10-28 : le texte part seulement par
l'enregistrement de contenu, sous `KB_TRACE_CONTENT`, et c'est inscrit au registre ; elle reste
ouverte pour le wiki.

Volume : 91 séries de métriques par démarrage de `kb serve-ai` quand une demande réussit, davantage
en cas d'échec (`docs/fiches-veille.md:1434-1436`).

**Conventions GenAI d'OpenTelemetry.** Elles vivent depuis peu dans un dépôt à part,
`open-telemetry/semantic-conventions-genai` ; l'ancienne page d'opentelemetry.io dit « This page has
moved » [27]. Au commit `e6658f1` de ce dépôt (2026-11-06), chaque document lu porte « **Status**:
Development » (`docs/gen-ai/README.md:7`, `client-inference.md:7`, `gen-ai-metrics.md:7`,
`gen-ai-spans.md:7`, `gen-ai-events.md:7`), et le dépôt n'a ni release ni tag [26]. Les noms que K-B
émet y figurent encore (`client-inference.md` : `gen_ai.client.inference.duration`,
`gen_ai.client.inference.usage.input_tokens`, `gen_ai.client.inference.usage.output_tokens`,
`gen_ai.client.inference.operation.details`). Conséquence : ces noms peuvent changer ; K-B suit le
texte des conventions, et ses écarts sont écrits dans `docs/fiches-veille.md` (« Écarts à la
convention »).

## Le tableau

« Non trouvé » : la page lue ne le dit pas. « Non vérifié » : aucune page lue sur ce point. Les
numéros renvoient à la section « Sources ».

| Critère | Application Insights | Grafana Cloud (en place) | Langfuse Cloud (UE) | LangSmith (UE) | Honeycomb (UE) |
|---|---|---|---|---|---|
| Métriques OTLP de K-B | oui : une ressource Application Insights avec « OTLP support », les métriques allant dans un Azure Monitor workspace [1][6] | oui, en place depuis #162 | non trouvé : seules les traces sont décrites [14] | non trouvé : seules les traces sont décrites [20] | oui : l'offre gratuite compte « 100M time series data points » [24] |
| Traces OTLP | oui, dans Log Analytics [1] | oui (Tempo), en place depuis #345 | oui, HTTP seul, « gRPC is not supported yet » [14] | oui [20] | oui, gRPC et HTTP [30] |
| Journaux OTLP (raisons, contenu) | oui [1] | oui (Loki), en place depuis #345 et #347 | non trouvé [14] | non trouvé [20] | non vérifié |
| Cheminement d'un appel | les traces arrivent ; vue non essayée | vu à l'essai réel du 2026-10-27 : Tempo, et « Logs for this span » sur un `chat` (`docs/fiches-veille.md:1549`) | les traces arrivent ; vue non essayée | les traces arrivent ; vue non essayée | les traces arrivent ; vue non essayée |
| Tableaux de bord | classeurs et tableaux Grafana du portail [31] | Grafana | personnalisables, sur toutes les offres, à partir des traces, observations et scores ; pas de métriques OTLP [12][15] | personnalisables sur le cloud US seulement ; en UE, une version « legacy » ; à partir des traces (nombre, latence, jetons, coût, retours) [21] | non vérifié |
| Alerte sur seuil | alertes sur métriques, y compris d'Application Insights ; groupes d'actions par e-mail ; alertes sur métriques OpenTelemetry en « public preview » [2] | alertes Grafana ; pour un compte gratuit ouvert depuis le 20/04/2026 : plus de Cloud Alertmanager, e-mail aux seuls utilisateurs de l'instance, webhooks gardés [9] ; limite de règles non trouvée [8] | 2 alertes en Hobby ; latence, coût, scores ; Slack, PagerDuty, webhook, GitHub Actions ; e-mail non trouvé [16] | erreurs, latence, coût, retours, nombre d'exécutions, sur 5 ou 15 min ; Slack, PagerDuty, Dynatrace, webhook ; offre minimale non trouvée [22] | 2 déclencheurs en offre gratuite [24] |
| Temps réel | délai d'ingestion non vérifié | délai d'ingestion non vérifié ; K-B envoie ses métriques toutes les 60 s | « new data appears in real time » avec l'en-tête `x-langfuse-ingestion-version: 4`, sinon jusqu'à 10 min [14] | ingestion asynchrone, délai non chiffré [20] | non vérifié |
| Accessibilité publiée | Azure fait partie des plateformes du rapport WCAG 2.1 de Microsoft ; rapport non ouvert ; portail et Azure Monitor non nommés [4] | « partially conformant with WCAG 2.1 level AA » (09/09/2025), certaines parties pas entièrement accessibles au clavier ; pas de VPAT ni d'ACR [10] ; **essai de Sabine** (section « Accessibilité ») | aucune déclaration trouvée | aucune déclaration trouvée | aucune déclaration trouvée |
| Région UE | région de l'abonnement de l'école ; un service régional déployé dans une région de l'EU Data Boundary en fait partie, mais Azure Monitor n'est pas nommé [5] | pile en `prod-eu-west-2`, Allemagne (registre, `docs/registre-traitements.md:127`) ; région d'une pile non modifiable [11] ; transferts vers les États-Unis possibles selon le DPA (registre, `:128`) | Irlande (AWS `eu-west-1`), offre gratuite comprise [12][13] | Pays-Bas (GCP `europe-west4`), offre gratuite comprise ; facturation aux États-Unis ; « We do not have a legal entity in the EU » [19] | Irlande (AWS `eu-west-1`) [25] ; sur l'offre gratuite : non trouvé |
| Coût pour K-B | journaux : 0 $ jusqu'à 5 Go par mois et par compte de facturation, puis 2,76 $/Go ; métriques : 0,11 $ les 10 millions d'échantillons ; alerte sur métrique : 0 $ jusqu'à 10 séries ; alerte sur journaux : 0,50 à 1,50 $ par mois ; facturé à l'école [3] | 0 $ : 10 000 séries actives par mois, 50 Go de journaux et 50 Go de traces par mois, 14 jours, 3 utilisateurs actifs [8] | 0 $ (Hobby) : 50 000 unités par mois, 30 jours, 2 utilisateurs ; Core à 29 $ par mois, 90 jours [12] | 0 $ (Developer) : 1 siège, 5 000 traces par mois, traces de base gardées 14 jours ; Plus à 39 $ par siège et par mois [18] | 0 $ : 20 millions d'événements par mois ; rétention non trouvée [24] |
| Contrat | DPA de Microsoft, entre Microsoft et l'école, déjà au registre (`docs/registre-traitements.md:18-23`) ; aucun sous-traitant nouveau [32] | Raintank Inc., dba Grafana Labs (New York) ; DPA lu le 24/10, signé et envoyé par Sabine le 28/10 ; le 29/10, Grafana Labs répond qu'il ne vaut que pour les entreprises (source : Sabine, voir « Écarts au choix ») | « Data processing agreement (GDPR) » sur l'offre Hobby [12] ; le lien du DPA mène à celui de ClickHouse, non lu ; société contractante non trouvée [17] | LangChain Inc., société du Delaware ; DPA par le support ; offre gratuite « without warranties, indemnities, support obligations, performance commitments, or data retention rights » [23] | DPA intégré aux conditions, offre gratuite comprise [33] |
| Mise en place sur l'abonnement de l'école | le 08/11 vers 11:25 UTC, `Microsoft.Monitor` et `Microsoft.AlertsManagement` sont « NotRegistered » (relevé de time-knight par `az provider show`) ; Sabine, Reader, ne peut pas les enregistrer ; un Azure Monitor workspace est une ressource `Microsoft.Monitor/accounts` [7] ; l'envoi passe par un collecteur OpenTelemetry ≥ 0.132.0 et une authentification Entra [1] | en place : `KB_OTLP_ENDPOINT` et `KB_OTLP_HEADERS` (`infra/main.bicep:224`, `:142`) | URL et en-tête ; métriques et journaux de K-B sans destination | URL et en-tête ; métriques et journaux de K-B sans destination | URL de l'instance UE et clé en en-tête [30] |

## Accessibilité

Le critère demande une accessibilité « essayée ». Choix de Sabine du 2026-11-08 (choix 15 de
time-knight) : **un seul essai, sur Grafana Cloud**, l'outil en place. Les quatre autres outils
sont jugés sur leurs déclarations publiées : c'est une limite. Le tableau de bord et l'alerte de
#164 n'existent pas encore : l'essai porte sur Explore, un tableau de bord de test à un panneau, et
la liste des règles d'alerte.

Grille : les critères WCAG 2.1 AA visés par RGAA 4.1.2 (`.claude/rules/conformite.md`), là où ils
touchent la lecture d'une mesure et d'une alerte. Est bloquant ce qui empêche, au clavier seul ou au
lecteur d'écran, de lire la valeur d'un panneau, de savoir qu'une alerte existe ou est déclenchée,
ou de l'ouvrir. Outils : Accessibility Insights for Web (FastPass), VoiceOver, l'émulation des
déficiences de la vision de Chrome, Colour Contrast Analyser, le zoom du navigateur.

| n° | Étape | Écran | Critère WCAG 2.1 | Résultat |
|---|---|---|---|---|
| 1 | contrôles automatiques (FastPass) | Explore, panneau, règles d'alerte | plusieurs | à venir |
| 2 | clavier seul : ouvrir le tableau de bord, changer la période | panneau | 2.1.1 | à venir |
| 3 | clavier seul : lire le panneau en tableau (Inspect > Data) | panneau | 2.1.1 | à venir |
| 4 | clavier : sortir de chaque menu ou fenêtre ouvert | les trois | 2.1.2 | à venir |
| 5 | focus visible tout au long du parcours | les trois | 2.4.7 | à venir |
| 6 | lecteur d'écran : nom et rôle des commandes | Explore, panneau | 4.1.2 | à venir |
| 7 | lecteur d'écran : valeur d'un panneau, résultat d'une requête | Explore, panneau | 4.1.2, 4.1.3 | à venir |
| 8 | lecteur d'écran : règles d'alerte et leur état | règles d'alerte | 4.1.2, 4.1.3 | à venir |
| 9 | couleur seule (émulation du daltonisme) | panneau, règles d'alerte | 1.4.1 | à venir |
| 10 | contrastes du texte, des axes, de la légende | Explore, panneau | 1.4.3, 1.4.11 | à venir |
| 11 | zoom à 200 % | Explore, panneau | 1.4.4 | à venir |
| 12 | zoom à 400 % | panneau | 1.4.10 | à venir |

Contournements prévus pour #164, si un point bloque : un texte à côté de la couleur d'un seuil
(« SOUS SEUIL ») ; l'alerte reçue par e-mail, en texte, qu'un compte gratuit récent n'envoie
qu'aux utilisateurs de l'instance [9].

## La recommandation « un seul outil généraliste »

La recommandation à évaluer : « Application Insights si la souscription le permet, sinon Grafana
Cloud ».

- **Langfuse Cloud et LangSmith** ne reçoivent, d'après leurs pages, que des traces OTLP [14][20] :
  les métriques de K-B (fidélité, coût, état des appels) et ses enregistrements de journal (raisons
  d'une affirmation retirée, contenu) n'y auraient pas de destination, et leurs alertes portent sur
  ce qu'ils calculent des traces, pas sur les compteurs de K-B [16][22]. Ils demanderaient un second
  outil pour les métriques. Leur avantage propre est de montrer le texte des prompts ; K-B sait
  l'envoyer à Grafana Cloud sous `KB_TRACE_CONTENT`, mais ce réglage vaut `none` en ligne : voir
  « Écarts au choix », point 1.
- **Application Insights** reçoit les trois signaux [1], mais le 2026-11-08 la souscription ne le
  permet pas sans un administrateur : deux fournisseurs de ressources ne sont pas enregistrés, et
  Sabine, Reader, ne peut pas le faire. Il demande aussi un collecteur et Entra [1], soit plus que
  l'URL et le jeton.
- **Grafana Cloud** reçoit les trois signaux, est en place, et coûte 0 $ dans les limites de l'offre
  gratuite [8]. Selon la recommandation elle-même, c'est l'outil retenu tant que la souscription ne
  permet pas Application Insights. Le tableau ne montre pas d'écart avec le choix de Sabine sur ce
  point.
- **Honeycomb** reçoit métriques et traces, en Irlande, gratuitement [24][25][30], mais n'a que deux
  déclencheurs et aucune déclaration d'accessibilité trouvée.

## Écartés, avec leur raison

| Outil | Raison |
|---|---|
| Auto-hébergement | décision de Sabine (critère de #163). Langfuse auto-hébergé : 6 services, environ 11 CPU et 25 Gio ; LangSmith auto-hébergé : sous contrat Enterprise seulement (journal ADR, « Wiki : métriques », `docs/ADR/journal-decisions-projet.md:1127-1128`) ; Grafana OSS sur ACA : 10 à 33 $ par mois de calcul [34] |
| Jaeger, pour la restitution | traces seules, ni métriques ni alertes, et il s'héberge soi-même ; gardé comme visionneuse de traces en local après le POC (critère de #163) |
| Azure Managed Grafana | environ 68 $ par mois, en plus d'Azure Monitor, qu'il lit [35] (prix déduit par le sous-agent de time-knight) |
| New Relic | requêtes NRQL non portables ; VPAT de 2016 [36] |
| Dash0 | essai de 14 jours seulement [37] |
| SigNoz Cloud | sources tierces contradictoires (comparaison du sous-agent de time-knight) |

## Écarts au choix

Écrits comme des faits ; remontés à time-knight, qui les porte à Sabine. Aucun n'est tranché ici.

1. **Le texte des prompts.** Le critère dit que l'avantage de Langfuse et LangSmith « pèse moins »
   parce que K-B envoie aussi ce texte à Grafana Cloud. En ligne, `KB_TRACE_CONTENT` vaut `none`
   (`infra/main.bicep:217`), et `MEMORY.md` interdit `anomalies` et `all` : aujourd'hui, Grafana
   Cloud ne montre aucun texte de prompt.
2. **Le DPA de Grafana Labs.** Signé et envoyé par Sabine le 2026-10-28 ; le 2026-10-29, Grafana Labs
   lui répond qu'un particulier n'a pas à le signer, le DPA ne valant que pour les entreprises
   (source : Sabine, auprès de time-knight le 2026-11-08 ; aucune copie de la réponse dans le
   dépôt). Ce qui en dépend (registre, journal ADR, `poc.md`, critère de #163) est porté à Sabine
   par time-knight.
3. **« Seuls l'URL et le jeton changent »** (décision 4 du 20/10) : vrai tant que l'outil reste
   Grafana Cloud. Pour Application Insights, repris après le rendu, l'envoi passe par un collecteur
   et Entra [1].
4. **Les alertes d'un compte gratuit récent** : depuis le 20/04/2026, un compte gratuit nouveau
   n'envoie d'e-mail qu'aux utilisateurs de son instance, sans Cloud Alertmanager [9]. La date
   d'ouverture du compte de Sabine n'est pas relevée ; à vérifier au début de #164.

## Non vérifié

- La vue des traces d'Application Insights, de Langfuse, de LangSmith et de Honeycomb : rien n'y a
  été envoyé.
- Le délai d'ingestion d'Application Insights, de Grafana Cloud et de Honeycomb.
- Le statut GA ou préversion de l'ingestion OTLP d'Azure Monitor : la page ne le dit pas [1].
- Si une ressource Application Insights avec OTLP dépend des fournisseurs non enregistrés : la page
  ne nomme pas de fournisseur [1][6].
- Si la part gratuite de 5 Go de Log Analytics, comptée par compte de facturation, reste disponible
  sur celui de l'école [3].
- Le rapport de conformité d'Azure, non ouvert [4] ; Azure Monitor dans l'EU Data Boundary [5].
- La limite de règles d'alerte de l'offre gratuite de Grafana Cloud [8] ; la date d'ouverture du
  compte de Sabine, et l'état actuel de la restriction des alertes (page close le 24/04/2026) [9].
- Les journaux OTLP, les tableaux de bord et la rétention de l'offre gratuite de Honeycomb, et sa
  région UE sur cette offre [24][25].
- La société contractante et le DPA de Langfuse (page de ClickHouse non lue) [17].
- L'offre minimale des alertes de LangSmith [22].
- Les faits marqués [30] à [37] : lus le 2026-11-08 par un sous-agent de time-knight, non relus par
  cette session.

## Sources

Lues le 2026-11-08 par la session de #163, sauf [30] à [37].

1. [OTLP ingestion in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/opentelemetry-protocol-ingestion) — Microsoft Learn, mise à jour le 2026-05-31 : option recommandée (Application Insights avec « OTLP support »), traces, journaux, métriques ; collecteur ≥ 0.132.0 ; « requires Microsoft Entra authentication ».
2. [Azure Monitor alerts overview](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview) — Microsoft Learn, 2026-07-08 : types d'alertes, groupes d'actions, alertes sur métriques OpenTelemetry en « public preview ».
3. [API des prix Azure](https://prices.azure.com/api/retail/prices) — France Central, consommation, `Log Analytics` et `Azure Monitor` ; [Azure Monitor pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/) : « The first 5 GB/month per billing account in this tier are free ».
4. [WCAG 2.1 compliance offering](https://learn.microsoft.com/compliance/regulatory/offering-wcag-2-1) — Microsoft Learn, mise à jour le 2026-06-02 : Azure parmi les « in-scope cloud platforms ».
5. [EU Data Boundary](https://learn.microsoft.com/en-us/privacy/eudb/eu-data-boundary-learn) — Microsoft Learn : « regional services that a customer deploys in an EU Data Boundary region will be in-scope ».
6. [Azure Monitor workspace overview](https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/azure-monitor-workspace-overview) — Microsoft Learn, 2026-10-28 : stocke les métriques Prometheus et OpenTelemetry.
7. [Microsoft.Monitor/accounts](https://learn.microsoft.com/en-us/azure/templates/microsoft.monitor/accounts) — référence des modèles ARM, vue dans un résultat de recherche du 2026-11-08, page non ouverte.
8. [Grafana Pricing](https://grafana.com/pricing/) — offre gratuite : 10 000 séries actives, 50 Go, 14 jours, 3 utilisateurs actifs.
9. [Restrictions on Alerts & Reports for Grafana Cloud Free/Trial Users](https://status.grafana.com/incidents/xg2h8ht1d44n) — Grafana, du 20/04/2026, close le 24/04/2026.
10. [Grafana accessibility](https://grafana.com/accessibility/) — déclaration du 09/09/2025.
11. [Grafana Cloud regional availability](https://grafana.com/docs/grafana-cloud/security-and-account-management/regional-availability/) — régions UE ; « does not support changing the Grafana Cloud region of an existing stack ».
12. [Langfuse pricing](https://langfuse.com/pricing) — Hobby, Core, régions, DPA, tableaux de bord.
13. [Langfuse data regions](https://langfuse.com/security/data-regions) — UE : « Ireland (AWS `eu-west-1`) ».
14. [Langfuse OpenTelemetry](https://langfuse.com/docs/opentelemetry) — point OTLP UE, traces, HTTP seul, délai sans l'en-tête de version.
15. [Langfuse custom dashboards](https://langfuse.com/docs/metrics/features/custom-dashboards).
16. [Langfuse alerts](https://langfuse.com/docs/observability/features/alerts) — « 2 (Hobby), 20 (Core), 50 (Pro), and 100 (Enterprise) ».
17. [Langfuse security](https://langfuse.com/security) — « You can enter into a DPA with Langfuse » ; `security/dpa` redirige vers le DPA de ClickHouse, non lu.
18. [LangSmith pricing](https://www.langchain.com/pricing-langsmith) et [usage and billing](https://docs.langchain.com/langsmith/usage-and-billing) — Developer, Plus, rétention de 14 jours des traces de base.
19. [LangSmith regions FAQ](https://docs.langchain.com/langsmith/regions-faq) et [LangSmith cloud](https://docs.langchain.com/langsmith/cloud) — région UE sur toutes les offres, hébergeurs, données gardées aux États-Unis.
20. [Trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry) — point OTLP UE, traces, ingestion asynchrone.
21. [LangSmith dashboards](https://docs.langchain.com/langsmith/dashboards) — tableaux personnalisables réservés au cloud US.
22. [LangSmith alerts](https://docs.langchain.com/langsmith/alerts).
23. [LangChain terms of service](https://www.langchain.com/terms-of-service) — DPA, offre gratuite, LangChain Inc. (Delaware).
24. [Honeycomb pricing](https://www.honeycomb.io/pricing) — offre gratuite : 20 millions d'événements, 100 millions de points de séries, 2 déclencheurs.
25. [Where is Honeycomb's data stored](https://support.honeycomb.io/articles/4871225658-where-is-honeycomb-s-data-stored) — UE : « AWS eu-west-1 (Europe - Ireland) ».
26. [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) — commit `e6658f1` (2026-11-06), `docs/gen-ai/*.md` lus par l'API GitHub : « Status: Development », aucune release.
27. [Semantic conventions for generative client AI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) — « This page has moved ».

Lues le 2026-11-08 par un sous-agent de time-knight (comparaison sans biais, non versionnée), non
relues par cette session :

30. [Honeycomb OpenTelemetry exporters](https://docs.honeycomb.io/send-data/opentelemetry/collector/exporters) — gRPC et HTTP, `api.eu1.honeycomb.io`.
31. [Azure Monitor Grafana plugin](https://learn.microsoft.com/azure/azure-monitor/visualize/grafana-plugin) — tableaux Grafana du portail, sans alertes Grafana.
32. [Microsoft Products and Services Data Protection Addendum](https://www.microsoft.com/licensing/terms/product/PrivacyandSecurityTerms/MCA).
33. [Honeycomb launches data residency in Europe](https://www.honeycomb.io/blog/honeycomb-launches-data-residency-europe).
34. [Azure Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing).
35. [Azure Managed Grafana overview](https://learn.microsoft.com/en-us/azure/managed-grafana/overview).
36. [New Relic VPAT](https://static.carahsoft.com/concrete/files/9415/5717/4779/New_Relic_VPAT_Final_v1.1.pdf).
37. [Dash0 pricing](https://dash0.com/pricing).
