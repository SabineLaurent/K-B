# MCD de K-B : positions des entités

Merise ne fixe pas de sens de lecture à une association. Convention retenue pour le MCD de K-B
(Sabine, 2026-10-09) : **le sujet du verbe est placé à gauche du complément, ou au-dessus s'ils
sont dans la même colonne**. Les cardinalités se lisent depuis l'entité voisine.

| Association | Sujet (à gauche ou au-dessus) | Complément | Lecture depuis le sujet | Lecture depuis le complément | Respecté dans `mcd-k-b.drawio` (2026-10-09) |
|---|---|---|---|---|---|
| REGROUPER | MODE D'ACQUISITION (0,n) | SOURCE (1,1) | un mode d'acquisition regroupe 0 à n sources | une source est regroupée dans un seul mode d'acquisition | oui |
| FOURNIR | SOURCE (0,n) | DONNÉE BRUTE (1,1) | une source fournit 0 à n données brutes | une donnée brute est fournie par une seule source | oui |
| CONTENIR | DONNÉE BRUTE (1,n) | ITEM (1,1) | une donnée brute contient 1 à n items | un item est contenu dans une seule donnée brute | oui |
| PRODUIRE | DONNÉE BRUTE (0,n) | TENDANCE (1,1) | une donnée brute produit 0 à n tendances | une tendance est produite par une seule donnée brute | oui |
| DÉCRIRE | PUBLICATION (0,1) | ITEM (0,1) | une publication décrit 0 ou 1 item | un item est décrit par 0 ou 1 publication | oui |
| CITER | ALERTE GITHUB (0,1) | VULNÉRABILITÉ (0,n) | une alerte GitHub cite 0 ou 1 vulnérabilité | une vulnérabilité est citée par 0 à n alertes GitHub | oui |
| RECENSER | VULNÉRABILITÉ (0,1) | ITEM (0,1) | une vulnérabilité recense 0 ou 1 item | un item est recensé par 0 ou 1 vulnérabilité | non : VULNÉRABILITÉ est à droite de ITEM, et en dessous |
| RÉSUMER | ARTICLE DE NEWSLETTER (0,1) | PUBLICATION (0,n) | un article de newsletter résume 0 ou 1 publication | une publication est résumée par 0 à n articles de newsletter | non : ARTICLE DE NEWSLETTER est à droite de PUBLICATION |
| PUBLIER | DÉPÔT SUIVI (0,n) | RELEASE (1,1) | un dépôt suivi publie 0 à n releases | une release est publiée par un seul dépôt suivi | non : DÉPÔT SUIVI est sous RELEASE, dans la même colonne |

**Spécialisation (XT)** : ITEM, l'entité générique, est placée au-dessus de ses sous-entités
(ARTICLE DE NEWSLETTER, RELEASE, ALERTE GITHUB). Respecté.

Cardinalités relevées dans `mcd-k-b.drawio` le 2026-10-09 ; le sujet de RECENSER et de DÉCRIRE
vient de la légende du diagramme (« VULNÉRABILITÉ les recense, PUBLICATION les décrit »).
