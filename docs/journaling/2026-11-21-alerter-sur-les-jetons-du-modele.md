# Alerter par e-mail sur les jetons de la ressource du modèle

- Date : 2026-11-21 (code du 2026-11-20, posé en ligne le 2026-11-20)
- Branche : `feat/model-token-alert`
- Issue : #501 (PR #665)
- Fichiers : `infra/modules/model-token-alert.bicep` (nouveau), `infra/main.bicep`, `infra/README.md`,
  `docs/fiches-veille.md` (API4 de l'auto-évaluation OWASP), `docs/ADR/journal-decisions-projet.md`
- Série : [restituer les métriques du modèle et alerter](2026-11-08-restituer-les-metriques-du-modele-et-alerter.md)
  (les alertes Grafana, côté K-B).

Les commits `b06a40ab` à `4ca6e2f0` de la liste de la branche sont ceux de #611 (PR #664), fusionnés dans `main`
avant que la branche parte : ils ont leur note, `2026-11-20-relire-api10-depuis-le-jeton-de-production.md`. Les
fichiers `MEMORY.md`, `docs/registre-traitements.md` et cette note de #611 viennent d'eux.

## Le pourquoi

OWASP API4:2023 demande, pour chaque fournisseur payant, un plafond de dépense, ou à défaut une alerte de
facturation (« When setting spending limits is not possible, billing alerts should be configured instead »). K-B
paie un fournisseur : chaque appel à gpt-6.1-sol coûte des jetons. Jusqu'ici, deux garde-fous existaient, et aucun ne
voyait vite une dépense anormale :

- `budget-kb` (40 € par mois, #632) ne s'évalue qu'une fois par 24 h, et ne comptait pas le modèle avant que sa
  ressource soit étiquetée `project=k-b`, le 2026-11-18 ;
- l'alerte Grafana `KbModelCostOverBudget` est calculée par K-B lui-même, à partir de ses propres mesures : une clé
  du modèle utilisée hors de K-B ne passe pas par elle, et si l'export vers Grafana s'arrête, elle se tait.

L'alerte de #501 regarde la ressource du modèle côté Azure, toutes les 15 minutes, quel que soit l'appelant. Elle
prévient Sabine par e-mail ; elle n'arrête rien.

## Le comment

### Deux ressources dans un module : le destinataire, puis la règle

Le module crée un groupe d'actions (qui reçoit) et une règle d'alerte sur métrique (quand). La règle nomme le
groupe par son identifiant :

```bicep
    actions: [
      {
        actionGroupId: operatorGroup.id
      }
    ]
```

(`infra/modules/model-token-alert.bicep:59-63`). Le groupe s'appelle `ag-kb-operator`, du nom de son destinataire
et non de l'alerte (`:9-11`) : les alertes suivantes de K-B (#553, #282) écriront à la même personne, et Azure
permet à plusieurs règles de partager un groupe. Son unique destinataire, `operator`, est l'adresse passée au
déploiement (`budgetContactEmail`), jamais écrite dans le dépôt.

### Ce que mesure la règle : le total des jetons, sur toute la ressource

```bicep
          metricNamespace: 'Microsoft.CognitiveServices/accounts'
          // Prompt and completion together, for every deployment: no dimension filter.
          metricName: 'TotalTokens'
          timeAggregation: 'Total'
```

(`model-token-alert.bicep:50-53`). `TotalTokens` compte l'entrée et la sortie ensemble ; `Total` additionne sur la
fenêtre. Aucune `dimensions` : la règle ne filtre pas sur `ModelDeploymentName`, elle compte tous les déploiements
de la ressource. Sa portée est la ressource elle-même :

```bicep
    scopes: [
      resourceId('Microsoft.CognitiveServices/accounts', modelAccountName)
    ]
```

(`:37-39`). Pourquoi la ressource entière : une clé de la ressource ouvre tous ses déploiements (Microsoft Learn,
« API keys provide full access to the resource and can't be scoped to specific users or actions »). Une clé volée
peut appeler un autre déploiement que celui de K-B ; un filtre sur le déploiement de K-B ne le verrait pas.

### Quand elle sonne : 400 000 jetons sur 24 h glissantes, vus toutes les 15 minutes

```bicep
    windowSize: 'P1D'
    evaluationFrequency: 'PT15M'
    autoMitigate: true
```

(`:41-43`). Toutes les 15 minutes, Azure additionne les jetons des 24 dernières heures et compare au seuil
(`GreaterThan`, `:54-55`). `autoMitigate` referme l'alerte quand la somme repasse sous le seuil. Le seuil vient de
`main.bicep` :

```bicep
var modelTokenAlertThreshold = 400000
```

(`infra/main.bicep:166`) : 4 fois les 80 954 jetons du jeudi 2026-11-19, un jour de collecte et de veille, arrondi
au 100 000 au-dessus (seuil de Sabine du 2026-11-20). Au prix de gpt-6.1-sol, 400 000 jetons coûtent de 0,96 $ (tout
en entrée, 2,40 $ le million) à 4,80 $ (tout en sortie, 12 $ le million).

### Une passe sans le paramètre ne touche pas l'alerte

```bicep
module modelTokenAlert 'modules/model-token-alert.bicep' = if (!empty(modelAccountName)) {
```

(`infra/main.bicep:168`). Le module ne se déploie que si `modelAccountName` est donné, et il est hors de
`deployWorkloads` : il ne dépend ni de l'image ni des apps, la première passe (sans `imageTag`) le pose. En mode
incrémental, Azure ne supprime rien qu'un modèle ne nomme pas : une passe qui oublie le paramètre laisse l'alerte
telle qu'en ligne. Les étapes 0, 2 et 5 du README posent `MODEL_ACCOUNT` et le passent ; `kb_check` refuse une
valeur vide.

### Ce que fait Sabine si elle sonne

`infra/README.md`, « Si elle sonne » (`:590-601`) : lire les jetons par jour et par déploiement
(`az monitor metrics list … --dimension ModelDeploymentName`), puis, si la dépense ne vient pas de K-B, régénérer la
clé de la ressource dans le portail, jamais par une commande qui l'afficherait, et refaire le secret de K-B. C'est la
parade de la limite principale : l'alerte prévient, la seule borne qui refuse est le quota du déploiement.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| `TotalTokens`, une règle | Le total suffit à voir une dépense anormale | `ProcessedPromptTokens` et `GeneratedTokens`, que l'issue nommait : deux règles pour la même question ; `FoundryModelEstimatedCost` : en préversion |
| Toute la ressource (Sabine, B4) | Une clé ouvre tous les déploiements ; un seul déploiement lu le 2026-11-20, celui de K-B | Le filtre `ModelDeploymentName` : laisserait passer un autre déploiement appelé avec la même clé |
| 400 000 sur `P1D` (Sabine, B3) | 4 fois un jour réel de K-B | Le 2026-11-18 (136 812), jour d'essais, écarté par Sabine |
| `PT15M` | Même prix que `PT1H`, dépense vue quatre fois plus tôt | `PT1H`, gardé en repli si Azure avait refusé le couple (il l'a accepté) |
| `ag-kb-operator`, du nom du destinataire | Repris par #553 et #282 | Un groupe par alerte |
| Portée par `resourceId(…)` | Même identifiant, aucune version d'API de plus à vérifier | Une ressource `existing` |
| Sévérité 2 (avertissement) | Une alerte de coût, pas une panne | — |
| `metricAlerts@2026-01-01`, `actionGroups@2023-01-01` | Les versions GA les plus récentes, relues le 2026-11-20 ; build sans BCP081 | `actionGroups@2024-10-01`, en préversion |

Imposé par les consignes du dépôt : aucune commande `az` lancée par la session (Sabine les lance, une à la fois) ;
l'adresse caviardée dans toute sortie recopiée (décision de Sabine du 2026-11-20).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `bicep build infra/main.bicep` : exit 0, aucun avertissement | Les versions d'API existent pour Bicep 0.48.1, celui de la CI |
| Aperçu du 2026-11-20 : 2 à créer (`ag-kb-operator`, `alert-kb-model-tokens`), 31 à modifier (bruit), 1 non analysable, aucune suppression | La passe n'ajoute que ces deux ressources ; le reste est le bruit connu des passes précédentes |
| `az deployment group create` → `Succeeded` | Azure accepte le couple `P1D` et `PT15M`, que Learn ne décrit pas |
| `az monitor metrics alert show` : actif, `P1D`, `PT15M`, `TotalTokens` > 400 000, `ag-kb-operator` | La règle en ligne est celle du module |
| `az monitor action-group show` : actif, `operator`, `Enabled` ; le portail : « Vérifiée(s) » | Le destinataire a validé le code à usage unique |
| E-mail d'essai reçu, déclenché à 23:23 UTC | L'adresse reçoit les e-mails du groupe |
| `az resource show … tags.project` → `k-b` | `budget-kb` compte la ressource du modèle |
| `uv run pytest` : 5664 passés ; ruff, mypy, mkdocs verts | Aucune régression ; le dépôt ne teste pas le Bicep au-delà du build |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une alerte et pas un plafond qui refuse ?** La mesure d'API4 accepte une alerte de facturation à
   défaut de plafond. La borne qui refuse existe : le quota du déploiement, 250 000 jetons par minute. L'alerte
   ajoute ce que le quota ne dit pas : une dépense anormale sur 24 h, vue en 15 minutes. (`docs/fiches-veille.md`,
   API4, « Plafonds de dépense », première limite.)
2. **Que se passe-t-il si une clé volée appelle un autre déploiement ?** Ses jetons comptent : la règle porte sur
   toute la ressource, sans filtre (`model-token-alert.bicep:37-39`, `:50-53`).
3. **Et si quelqu'un relance une passe sans `modelAccountName` ?** L'alerte reste en ligne : le module n'est pas
   déployé, et le mode incrémental ne supprime rien (`main.bicep:168`).
4. **D'où vient 400 000 ?** De la consommation réelle de K-B le 2026-11-19, multipliée par 4, arrondie
   (`main.bicep:163-166`, journal ADR, 2026-11-20).
5. **Où est l'adresse, et qui la voit ?** Passée au déploiement, jamais dans le dépôt ; lisible par un lecteur du
   groupe de ressources, comme celle du budget ; caviardée dans toute sortie recopiée (journal ADR, 2026-11-20).

## Zones non vérifiées

- **Le délai d'arrivée de la métrique** : la limite d'API4 le nomme sans le chiffrer ; il n'a pas été mesuré.
- **L'état final de l'e-mail d'essai** : la commande attendait encore la fin de l'essai plus de 3 minutes après
  l'e-mail, et Sabine l'a arrêtée ; l'e-mail reçu fait la preuve, pas l'état rendu par Azure.
- **Une alerte réelle** : aucune n'a sonné ; seul l'e-mail d'essai a été reçu.

## Ce qui reste

- Les alertes sur les jobs et la disponibilité (#553, #282) reprendront `ag-kb-operator` ; elles ne se font pas ici.
- La passe historique « La passe A : le site fermé » (#571) reste sans `modelAccountName` : elle décrit le
  2026-11-11.
- `docs/tendances.md:532` donne encore le quota de gpt-6-luna ; hors d'API4 et de #501.
