# Comparer les outils de suivi : ce qui fonde le choix de Grafana Cloud

- Date : 2026-11-08
- Branche : `docs/monitoring-tools-comparison`
- Issue : #163
- Fichiers : `docs/outils-de-suivi.md` (nouveau), `docs/ADR/journal-decisions-projet.md`,
  `docs/registre-traitements.md`, `MEMORY.md`
- Note précédente sur le sujet : [2026-10-24-emettre-les-metriques-en-opentelemetry.md](2026-10-24-emettre-les-metriques-en-opentelemetry.md)

## Le pourquoi

Le 2026-10-20, tu as choisi Grafana Cloud pour les mesures de l'API IA, et l'ADR a écrit « Pourquoi :
à établir par la comparaison de #163 ». La revue certif lit C11.2 comme partiel et C11.4 comme vide
tant que cette comparaison écrite manque. Cette PR l'écrit : elle **justifie un choix fait**, elle
ne le refait pas. Ta décision du 08/11 (Grafana Cloud seul pour le 25/11, Application Insights après)
entre au journal avec son pourquoi. La PR corrige aussi un fait : le DPA de Grafana Labs, que deux
fichiers disaient « à signer ».

## Le comment

### 1. Partir de ce que K-B émet, pas des fiches produit

Un outil vaut pour K-B s'il reçoit ce que l'API IA envoie déjà. Elle envoie trois signaux sous une
seule URL de base :

```python
METRICS_PATH = "/v1/metrics"
TRACES_PATH = "/v1/traces"
LOGS_PATH = "/v1/logs"
```

(`src/k_b/ai_api/connectors/metrics_export.py:54-56`). C'est la première section du document
(`docs/outils-de-suivi.md:20-55`). Elle rend le tri net : Langfuse Cloud et LangSmith ne décrivent
que des traces OTLP. Les 14 instruments de métriques et les enregistrements de journal de K-B n'y
auraient donc pas de destination (`docs/outils-de-suivi.md:117-123`).

### 2. Un tableau où chaque case a sa source

Le tableau (`docs/outils-de-suivi.md:61-74`) croise cinq outils et douze critères. Chaque case
renvoie à une source numérotée, lue le 2026-11-08 ; « non trouvé » veut dire que la page lue ne le
dit pas, « non vérifié » qu'aucune page n'a été lue. Les faits repris de la comparaison de time-knight
sans relecture sont rangés à part ([31] à [38]), pour que personne ne les croie revérifiés.

### 3. Un écart s'écrit comme un fait, il ne se tranche pas

Exemple : le critère de #163 dit que l'avantage de Langfuse et LangSmith (montrer le texte des
prompts) « pèse moins », parce que K-B sait l'envoyer à Grafana. Or :

```bicep
      KB_TRACE_CONTENT: 'none'
```

(`infra/main.bicep:217`) : en ligne, Grafana ne montre aucun prompt. Le document l'écrit comme un fait
(`docs/outils-de-suivi.md:155-158`), sans le juger, et time-knight te le porte.

### 4. Le DPA : corriger le fait, garder l'interdiction

Le registre disait le DPA signé et en attente de réception ; le 29/10, Grafana Labs t'a répondu qu'il
ne vaut que pour les entreprises. La ligne « Contrat » le dit maintenant
(`docs/registre-traitements.md:126`). `MEMORY.md:117-119` garde l'interdiction de `anomalies` et
`all`, avec un renvoi vers #163 et sans motif nouveau. Ce qui en dépend est remonté sans être
touché : les engagements, les transferts, trois entrées ADR, `poc.md:134` et le critère.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Colonnes | les 4 du critère et Honeycomb, ajouté par le commentaire du 24/10 (ton accord du 08/11) | Honeycomb dans les écartés (reco de la mission) : le commentaire fait partie de la demande |
| Essai d'accessibilité | un seul, sur Grafana Cloud (ton choix 15) | un essai par outil : quatre comptes à ouvrir pour des outils non retenus ; c'est écrit comme une limite |
| Sources | relire le jour même les faits qui portent la comparaison (coût, UE, alertes, accessibilité) | tout reprendre de l'annexe : la mission demande une relecture des faits décisifs |
| DPA dans `MEMORY.md` | garder l'interdiction, avec un renvoi | écrire « sans décision de Sabine » : la relecture du plan y a vu une décision tranchée |
| Nom du fichier | `docs/outils-de-suivi.md`, nommé par son sujet comme `docs/stockage.md` | un nom de comparaison : le document décrit aussi l'instrumentation de référence |

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| `gh api …/semantic-conventions-genai/contents/docs/gen-ai/README.md` → `**Status**: [Development]`, 0 release | le statut des conventions `gen_ai.*` est vérifié à la source le 08/11 |
| relecture xhigh : 21 constats, 21 corrigés ; relecture du delta : 21 faits, 5 corrections de plus | chaque fait est confronté au code et à sa source par un relecteur neuf |
| contrôle Python : 0 caractère Cc ou Cf, sources citées = sources listées | la forme demandée par la mission |
| `uv.lock` → `opentelemetry-sdk` 1.45.1 ; `.venv` → 5000 ms (spans), 1000 ms (journaux) | le délai d'envoi écrit est celui du code |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas Application Insights, puisque l'école le paie ?** Le 08/11, deux fournisseurs
   (`Microsoft.Monitor`, `Microsoft.AlertsManagement`) ne sont pas enregistrés sur l'abonnement, et tu
   es Reader. Il demande aussi un collecteur et Entra, et des histogrammes exponentiels
   (`docs/outils-de-suivi.md:164-174`). Il revient après le rendu, pour garder traces et journaux
   chez Microsoft.
2. **Pourquoi pas Langfuse ou LangSmith, faits pour les LLM ?** Ils ne reçoivent que des traces :
   fidélité, coût et état des appels resteraient sans outil (`docs/outils-de-suivi.md:117-123`).
3. **L'accessibilité est-elle prouvée ?** Pas encore : ton essai sur Grafana Cloud passe à #164
   (ton choix 18), sur le vrai tableau de bord et l'alerte ; la grille est prête
   (`docs/outils-de-suivi.md`, section « Accessibilité »). D'ici là, chaque outil n'est jugé que
   sur sa déclaration ; Grafana Labs se dit partiellement conforme, et aucun des trois outils d'IA
   n'en publie (`docs/outils-de-suivi.md:70`).
4. **Le choix change-t-il si l'offre gratuite de Grafana change ?** Elle a déjà changé le 20/04/2026
   pour les alertes [9] : l'e-mail ne part qu'aux utilisateurs de l'instance, à vérifier au début de
   #164 (`docs/outils-de-suivi.md`, « Écarts au choix », point 4).

## Zones non vérifiées

- La vue des traces dans les quatre autres outils : rien n'y a été envoyé.
- Les délais d'ingestion, le statut GA de l'OTLP d'Azure Monitor, et si la ressource
  Application Insights « OTLP support » crée elle-même l'Azure Monitor workspace.
- La réponse de Grafana Labs du 29/10 : sa seule source est ce que tu en as dit ; aucune copie dans
  le dépôt.
- Les sources [31] à [38], lues par le sous-agent de time-knight et non relues.

## Ce qui reste

- Ton essai d'accessibilité, passé à #164 (ton choix 18), et ses résultats dans la grille
  (`docs/outils-de-suivi.md`, section « Accessibilité »).
- Ton choix 17 sur le DPA, porté par time-knight ; ce qui en dépend reste tel quel d'ici là.
- Le délai des spans écrit à tort dans `docs/fiches-veille.md:1538` : un commentaire sur #165.
- Le tableau de bord et l'alerte : #164.
