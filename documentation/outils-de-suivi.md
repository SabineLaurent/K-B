# Le choix de l'outil de suivi du monitorage

!!! note "Compétences de la certification"

    > La documentation explicite les arguments en faveur des choix techniques pour l'outillage du monitorage de
    > l'application.

    — C20

Cette fiche donne l'outil qui reçoit et restitue les mesures de l'API IA, Grafana Cloud, et les arguments de ce
choix: ce que l'outil doit recevoir, les critères, la comparaison de cinq outils en ligne, les outils écartés et les
limites de la comparaison. L'installation et l'usage de l'outil sont dans [la fiche du monitorage](monitorage.md).
Les faits sur K-B sont lus dans le code de `main` au commit `a1a01efd` (2026-11-22); les pages des outils ont été
lues le 2026-11-22 (section [Sources](#sources), numéros entre crochets). Les chemins du code de K-B (`ai_api/…`,
`core/…`) partent de `src/k_b/`, les autres de la racine du dépôt.

## Ce que l'outil reçoit

L'API IA émet trois signaux OpenTelemetry, les métriques, les traces et les journaux, en OTLP, le protocole d'export
d'OpenTelemetry, sur HTTP. Ils partent vers une seule URL de base, avec un en-tête d'authentification: changer d'outil
compatible change cette URL et ce jeton, pas le code. Le tableau suivant donne chaque signal, ce que K-B émet, et où
le code le fait.

| Signal | Ce que K-B émet | Où |
|---|---|---|
| Métriques du modèle | 17 instruments: durée d'un appel, jetons d'entrée et de sortie, appels et leur état, coût estimé, contrôles, fidélité, durée de lecture de la veille, durée d'une demande; trois portent un nom des conventions GenAI d'OpenTelemetry (`gen_ai.client.inference.duration`, `gen_ai.client.inference.usage.input_tokens`, `gen_ai.client.inference.usage.output_tokens`) | `ai_api/observability/metric_instruments.py:56-143`, `:57`, `:63`, `:68` |
| Traces | une trace par `POST /digests`, un span par étape (`read_watch`, `classify_batch`, `write_subject`), un span `chat <modèle>` par requête au modèle; tous les spans sont gardés (échantillonneur `ALWAYS_ON`) | `ai_api/routers/digest_router.py:46`, `:240`; `ai_api/stages/classification.py:127`; `ai_api/digests.py:204`; `ai_api/connectors/llm_client.py:276`; `ai_api/connectors/trace_export.py:85` |
| Journaux | la raison de chaque affirmation retirée (`gen_ai.evaluation.result`), rattachée à son span `chat`; le contenu d'une requête au modèle (`gen_ai.client.inference.operation.details`), sous `KB_TRACE_CONTENT`, qui vaut `none` par défaut et en ligne, et refuse `all` en production | `ai_api/tracing.py:50`, `:59`; `ai_api/connectors/metrics_export.py:186`; `infra/main.bicep:324` |
| Chemins OTLP | `/v1/metrics`, `/v1/traces` et `/v1/logs` sous l'URL de base; une variable `OTEL_*` arrête le démarrage | `ai_api/connectors/metrics_export.py:52-56` |
| Cadence et forme | métriques toutes les 60 s, en temporalité cumulative, histogrammes à bornes explicites; spans par lots toutes les 5 s et journaux chaque seconde, délais par défaut du SDK 1.45.2, que K-B ne règle pas | `core/config.py:636`; `ai_api/connectors/metrics_export.py:66-68`; `ai_api/observability/metric_instruments.py:34`, `:39`, `:45`; `ai_api/connectors/trace_export.py:101-113` |
| Copie hors outil | une ligne JSON par appel au modèle sur la sortie standard | `ai_api/observability/metrics.py:50-51` |

Les noms `gen_ai.*` viennent des conventions sémantiques GenAI d'OpenTelemetry, dans le dépôt
`open-telemetry/semantic-conventions-genai`, au statut <q><span lang="en">Development</span></q> le 2026-11-22
[24]; l'ancienne page d'opentelemetry.io renvoie à ce dépôt [25]. Ces noms peuvent changer d'une version des
conventions à l'autre.

## Les critères

Cinq critères viennent du journal des décisions d'architecture (ADR, <span lang="en">Architecture Decision
Record</span>), dans son entrée du 2026-10-12 sur les métriques: l'alerte sur seuil, le temps réel, l'accessibilité de
l'interface, la région et le coût. Le tableau y ajoute deux lignes: les signaux que l'outil reçoit, puisque K-B les
émet tous les trois, et le contrat, que le RGPD (règlement général sur la protection des données) demande pour un
sous-traitant.

- **les trois signaux**: l'outil reçoit les métriques, les traces et les journaux de K-B en OTLP;
- **l'alerte sur seuil**: une règle sur une mesure envoie un e-mail;
- **le temps réel**: le délai entre l'envoi et l'affichage;
- **l'accessibilité de l'interface**: une déclaration publiée selon les WCAG (<span lang="en">Web Content
    Accessibility Guidelines</span>) 2.1;
- **la région**: les données restent dans l'Union européenne (UE);
- **le coût**: l'offre gratuite couvre K-B;
- **le contrat**: l'outil propose un accord de traitement des données (DPA, <span lang="en">Data Processing
    Agreement</span>).

## La comparaison

Le tableau suivant compare les cinq outils sur ces critères. « Non trouvé »: la page lue ne le dit pas.

| Critère | Application Insights | Grafana Cloud (retenu) | Langfuse Cloud (UE) | LangSmith (UE) | Honeycomb (UE) |
|---|---|---|---|---|---|
| Métriques OTLP | oui: une ressource Application Insights avec <q><span lang="en">OTLP support</span></q>, l'option recommandée [1] | oui, reçues depuis #162 | non trouvé: seules les traces sont décrites [12] | non trouvé: seules les traces sont décrites [18] | oui [26] |
| Traces OTLP | oui [1] | oui (Tempo), reçues depuis #345 | oui, sur HTTP seulement: <q><span lang="en">gRPC is not supported yet</span></q> [12] | oui [18] | oui, gRPC et HTTP [26] |
| Journaux OTLP | oui [1] | oui (Loki), reçus depuis #345 | non trouvé [12] | non trouvé [18] | oui [26] |
| Tableaux de bord | des tableaux Grafana dans le portail Azure, sans les alertes Grafana [28] | Grafana | personnalisables sur toutes les offres, à partir des traces, des observations et des scores [10][13] | personnalisables sur le cloud des États-Unis; en UE, une version <q><span lang="en">legacy</span></q> [19] | non trouvé pour l'offre gratuite [22] |
| Alerte sur seuil | alertes sur métriques, y compris d'Application Insights, et groupes d'actions par e-mail; sur les métriques OpenTelemetry, en préversion publique [2] | règles d'alerte Grafana, par e-mail; un compte gratuit ouvert depuis le 2026-04-20 n'envoie d'e-mail qu'aux utilisateurs de son instance [7] | 2 alertes sur l'offre Hobby; Slack, PagerDuty, webhook, GitHub Actions; e-mail non trouvé [14] | erreurs, latence, coût, retours, nombre d'exécutions, sur 5 ou 15 min; Slack, PagerDuty, Dynatrace, webhook; e-mail non trouvé [20] | 2 déclencheurs sur l'offre gratuite [22] |
| Temps réel | délai non trouvé | délai non trouvé; K-B envoie ses métriques toutes les 60 s | <q><span lang="en">new data appears in real time</span></q> avec l'en-tête `x-langfuse-ingestion-version: 4`, sinon jusqu'à 10 min [12] | <q><span lang="en">The OTel endpoint is asynchronous</span></q>, délai non chiffré [18] | délai non trouvé |
| Accessibilité publiée | Azure fait partie des plateformes du rapport WCAG 2.1 de Microsoft; le portail et Azure Monitor n'y sont pas nommés [4] | <q><span lang="en">partially conformant with WCAG 2.1 level AA</span></q>, déclaration du 2025-09-09; certaines parties ne sont pas entièrement accessibles au clavier [8] | aucune déclaration trouvée [10][12][15] | aucune déclaration trouvée [16][17][21] | aucune déclaration trouvée, ni sur la page des prix [22], ni par un lien de la page d'accueil |
| Région UE | les services régionaux déployés dans une région de l'<span lang="en">EU Data Boundary</span> en font partie; Azure Monitor n'y est pas nommé [5] | pile `prod-eu-west-2`, en Allemagne [7]; la région d'une pile ne se change pas [9] | Irlande (AWS `eu-west-1`), offre gratuite comprise [10][11] | Pays-Bas (GCP `europe-west4`), offre gratuite comprise; facturation aux États-Unis; <q><span lang="en">We do not have a legal entity in the EU for customer contracting today</span></q> [17] | Irlande (AWS `eu-west-1`) [23]; sur l'offre gratuite: non trouvé |
| Coût, offre gratuite | journaux: 5 Go par mois et par compte de facturation, puis 2,76 USD le Go; métriques: 0,11 USD les 10 millions d'échantillons; 10 séries surveillées par une alerte sur métrique [3] | 0 USD: 10 000 séries actives par mois, 50 Go de journaux et 50 Go de traces par mois, 14 jours de rétention, 3 utilisateurs actifs [6] | 0 USD (Hobby): 50 000 unités par mois, 30 jours, 2 utilisateurs [10] | 0 USD (Developer): 1 siège, 5 000 traces de base par mois, gardées 14 jours [16] | 0 USD: 20 millions d'événements par mois; rétention non trouvée [22] |
| Contrat | les conditions de Microsoft renvoient à son DPA [29] | DPA de Grafana Labs, version 2026.04.02, qui prend effet signé par la cliente et reçu par Grafana Labs (registre des traitements, « Envoi des mesures à Grafana Cloud », ligne « Contrat ») | <q><span lang="en">You can enter into a DPA with Langfuse</span></q>; le lien du DPA mène à celui de ClickHouse [15] | conditions de LangChain Inc., société du Delaware, qui renvoient à un <span lang="en">Enterprise Data Processing Addendum</span>; offre gratuite sans <q><span lang="en">data retention rights</span></q> [21] | DPA intégré aux conditions, offre gratuite comprise [30] |
| Ce que K-B ajoute pour l'envoi | un collecteur OpenTelemetry 0.132.0 ou plus, avec une authentification Microsoft Entra [1], ou l'exportateur Azure Monitor, une dépendance nouvelle en version bêta, `1.0.0b59` [27]; l'agent OpenTelemetry géré d'Azure Container Apps n'envoie pas de métriques à Application Insights [33] | rien: `KB_OTLP_ENDPOINT` et le secret `kb-otlp-headers` (`infra/main.bicep:333`, `:209`) | l'URL et l'en-tête; les métriques et les journaux de K-B n'ont pas de destination | l'URL et l'en-tête; les métriques et les journaux de K-B n'ont pas de destination | l'URL de l'instance UE et une clé en en-tête [26] |

## Pourquoi Grafana Cloud

- **Il reçoit les trois signaux tels que K-B les émet.** L'envoi direct en OTLP, sans collecteur, se règle par une
    URL et un en-tête (`infra/main.bicep:333`, `:209`). Les cinq règles d'alerte et le tableau de bord se déclarent
    dans deux fichiers du dépôt, `observability/grafana/alert-rules.yaml` et `observability/grafana/dashboard.json`,
    que Grafana Cloud importe ([la fiche du monitorage](monitorage.md)).
- **Ses alertes arrivent par e-mail.** Dans le bac à sable, trois alertes déclenchées ont envoyé leur e-mail
    ([la fiche du monitorage](monitorage.md#releve-des-alertes-du-bac-a-sable)).
- **Son offre gratuite couvre K-B**: 10 000 séries actives par mois, 50 Go de journaux et 50 Go de traces [6].
- **Sa pile est dans l'UE**, en Allemagne [7].
- **Il publie une déclaration d'accessibilité**, partielle au niveau AA des WCAG 2.1 [8]. Langfuse, LangSmith et
    Honeycomb n'en publient pas sur les pages lues.
- **Application Insights demande plus que l'URL et le jeton.** L'envoi passe par un collecteur et Microsoft Entra
    [1], ou par une dépendance nouvelle en version bêta [27]. Ses tableaux et ses requêtes attendent des métriques en
    temporalité delta et des histogrammes exponentiels: <q><span lang="en">Application Insights experiences, including
    prebuilt dashboards and queries, expect and require OTLP metrics with delta temporality and exponential histogram
    aggregation</span></q> [1]. K-B émet en temporalité cumulative, avec des bornes explicites
    (`ai_api/connectors/metrics_export.py:66-68`, `ai_api/observability/metric_instruments.py:34`). La page donne la
    conversion de la temporalité dans le collecteur (`cumulativetodelta`), pas celle des histogrammes [1].
- **Langfuse et LangSmith ne reçoivent que des traces** [12][18]: les métriques de K-B (coût, fidélité, état des
    appels) et ses journaux demanderaient un second outil, et leurs alertes portent sur ce qu'ils calculent des
    traces [14][20]. Leur avantage propre, montrer le texte des requêtes au modèle, ne sert pas K-B en ligne:
    `KB_TRACE_CONTENT` y vaut `none` (`infra/main.bicep:324`).
- **Honeycomb reçoit les trois signaux** [26], mais son offre gratuite a 2 déclencheurs [22], et aucune
    déclaration d'accessibilité n'a été trouvée.

## Les outils écartés

Le tableau suivant donne les outils écartés avant la comparaison, chacun avec sa raison.

| Outil | Raison |
|---|---|
| Langfuse auto-hébergé | 6 services, environ 11 CPU et 25 Gio de mémoire (journal des décisions, entrée du 2026-10-12 sur les métriques) |
| LangSmith auto-hébergé | sous contrat Enterprise seulement (même entrée) |
| Azure Managed Grafana | il lit Azure Monitor [31]: il s'ajoute à Azure Monitor au lieu de le remplacer |
| Dash0 | un essai gratuit de 14 jours, sans offre gratuite [32] |

## Les limites

- **L'accessibilité des cinq outils est comparée sur leurs déclarations publiées.** La grille de l'essai de Grafana
    Cloud au clavier et au lecteur d'écran est dans
    [l'essai d'accessibilité de Grafana Cloud](https://github.com/SabineLaurent/K-B/blob/main/docs/accessibilit%C3%A9_pour_docu.md);
    ce fichier ne porte aucun résultat.
- **Le délai d'ingestion** d'Application Insights, de Grafana Cloud et de Honeycomb n'est pas publié sur les pages
    lues.
- **Le statut de l'ingestion OTLP d'Azure Monitor**, disponible ou en préversion, n'est pas dit par sa page [1].
- **Les vues des traces** d'Application Insights, de Langfuse, de LangSmith et de Honeycomb n'ont pas été essayées:
    K-B ne leur envoie rien.
- **La limite de règles d'alerte** de l'offre gratuite de Grafana Cloud n'est pas publiée [6].
- **Le DPA de Langfuse** est celui de ClickHouse, lien non suivi [15].
- **Grafana Labs a répondu le 2026-10-29 qu'un particulier n'a pas à signer son DPA**, qui ne vaut que pour les
    entreprises (registre des traitements, même ligne; la réponse n'est pas dans le dépôt). Aucun contenu de requête
    n'est envoyé à Grafana Cloud: `KB_TRACE_CONTENT` vaut `none` en ligne (`infra/main.bicep:324`).

## Sources

Le tableau des critères et chaque renvoi entre crochets s'appuient sur les pages suivantes, lues le 2026-11-22.

1. [<span lang="en">OTLP ingestion in Azure Monitor</span>](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/opentelemetry-protocol-ingestion), Microsoft Learn, mise à jour le 2026-11-10.
2. [<span lang="en">Azure Monitor alerts overview</span>](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview), Microsoft Learn, 2026-07-08.
3. [<span lang="en">Azure Monitor pricing</span>](https://azure.microsoft.com/en-us/pricing/details/monitor/) et [l'API des prix d'Azure](https://prices.azure.com/api/retail/prices?$filter=serviceName%20eq%20'Azure%20Monitor'%20and%20armRegionName%20eq%20'francecentral'%20and%20priceType%20eq%20'Consumption'), région France Central, services `Azure Monitor` et `Log Analytics`.
4. [<span lang="en">WCAG 2.1 compliance offering</span>](https://learn.microsoft.com/compliance/regulatory/offering-wcag-2-1), Microsoft Learn, mise à jour le 2026-06-02.
5. [<span lang="en">EU Data Boundary</span>](https://learn.microsoft.com/en-us/privacy/eudb/eu-data-boundary-learn), Microsoft Learn.
6. [<span lang="en">Grafana Pricing</span>](https://grafana.com/pricing/), Grafana Labs.
7. [<span lang="en">Restrictions on Alerts & Reports for Grafana Cloud Free/Trial Users</span>](https://status.grafana.com/incidents/xg2h8ht1d44n), page d'état de Grafana, du 2026-04-20, résolu le 2026-04-24; composant touché <q><span lang="en">AWS Germany - prod-eu-west-2</span></q>.
8. [<span lang="en">Grafana accessibility</span>](https://grafana.com/accessibility/), déclaration du 2025-09-09.
9. [<span lang="en">Grafana Cloud regional availability</span>](https://grafana.com/docs/grafana-cloud/security-and-account-management/regional-availability/), Grafana Labs.
10. [<span lang="en">Langfuse pricing</span>](https://langfuse.com/pricing).
11. [<span lang="en">Langfuse data regions</span>](https://langfuse.com/security/data-regions).
12. [<span lang="en">Langfuse OpenTelemetry</span>](https://langfuse.com/docs/opentelemetry).
13. [<span lang="en">Langfuse custom dashboards</span>](https://langfuse.com/docs/metrics/features/custom-dashboards).
14. [<span lang="en">Langfuse alerts</span>](https://langfuse.com/docs/observability/features/alerts).
15. [<span lang="en">Langfuse security</span>](https://langfuse.com/security).
16. [<span lang="en">LangSmith pricing</span>](https://www.langchain.com/pricing-langsmith) et [<span lang="en">usage and billing</span>](https://docs.langchain.com/langsmith/usage-and-billing).
17. [<span lang="en">LangSmith regions FAQ</span>](https://docs.langchain.com/langsmith/regions-faq) et [<span lang="en">LangSmith cloud</span>](https://docs.langchain.com/langsmith/cloud).
18. [<span lang="en">Trace with OpenTelemetry</span>](https://docs.langchain.com/langsmith/trace-with-opentelemetry), LangSmith.
19. [<span lang="en">LangSmith dashboards</span>](https://docs.langchain.com/langsmith/dashboards).
20. [<span lang="en">LangSmith alerts</span>](https://docs.langchain.com/langsmith/alerts).
21. [<span lang="en">LangChain terms of service</span>](https://www.langchain.com/terms-of-service), mises à jour le 2026-11-19.
22. [<span lang="en">Honeycomb pricing</span>](https://www.honeycomb.io/pricing).
23. [<span lang="en">Where is Honeycomb’s data stored</span>](https://support.honeycomb.io/articles/4871225658-where-is-honeycomb-s-data-stored).
24. [<span lang="en">semantic-conventions-genai</span>](https://github.com/open-telemetry/semantic-conventions-genai), le dépôt des conventions GenAI d'OpenTelemetry.
25. [<span lang="en">Semantic conventions for generative client AI spans</span>](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/), opentelemetry.io.
26. [<span lang="en">Honeycomb OpenTelemetry exporters</span>](https://docs.honeycomb.io/send-data/opentelemetry/collector/exporters).
27. [`azure-monitor-opentelemetry-exporter`](https://pypi.org/pypi/azure-monitor-opentelemetry-exporter/json), métadonnées de PyPI: version `1.0.0b59`, Microsoft Corporation, classé `Development Status :: 4 - Beta`.
28. [<span lang="en">Azure Monitor dashboards with Grafana</span>](https://learn.microsoft.com/azure/azure-monitor/visualize/grafana-plugin), Microsoft Learn, 2026-04-02.
29. [<span lang="en">Privacy & Security Terms</span>](https://www.microsoft.com/licensing/terms/product/PrivacyandSecurityTerms/MCA), Product Terms de Microsoft, qui renvoient au DPA de Microsoft.
30. [<span lang="en">Honeycomb launches data residency in Europe</span>](https://www.honeycomb.io/blog/honeycomb-launches-data-residency-europe), mis à jour le 2024-02-20.
31. [<span lang="en">Azure Managed Grafana overview</span>](https://learn.microsoft.com/en-us/azure/managed-grafana/overview), Microsoft Learn.
32. [<span lang="en">Dash0 pricing</span>](https://dash0.com/pricing).
33. [<span lang="en">OpenTelemetry agents in Azure Container Apps</span>](https://learn.microsoft.com/azure/container-apps/opentelemetry-agents), Microsoft Learn, en préversion.
