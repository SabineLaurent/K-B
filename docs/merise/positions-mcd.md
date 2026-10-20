# MCD de K-B : positions des entités

Merise ne fixe pas de sens de lecture à une association. Convention retenue pour le MCD de K-B
(Sabine, 2026-10-09) : **le sujet du verbe est placé à gauche du complément, ou au-dessus s'ils
sont dans la même colonne**. Les cardinalités se lisent depuis l'entité voisine.

| Association | Sujet (à gauche ou au-dessus) | Complément | Lecture depuis le sujet | Lecture depuis le complément | Dans `mcd-k-b_20261020.drawio` |
|---|---|---|---|---|---|
| FOURNIR | Source (0,N) | Donnée brute (1,1) | une source fournit 0 à N données brutes | une donnée brute est fournie par une seule source | à gauche |
| CONTENIR | Donnée brute (0,N) | Item (1,1) | une donnée brute contient 0 à N items | un item est contenu dans une seule donnée brute | à gauche |
| PRODUIRE | Donnée brute (0,N) | Classement (1,1) | une donnée brute produit 0 à N classements | un classement est produit par une seule donnée brute | au-dessus |
| COMPTER | Classement (1,N) | Tendance (1,1) | un classement compte 1 à N tendances | une tendance est comptée dans un seul classement | au-dessus |
| DÉCRIRE | Item (0,1) | Publication (0,1) | un item décrit 0 ou 1 publication | une publication est décrite par 0 ou 1 item | à gauche |
| RECENSER | Item (0,1) | Vulnérabilité (0,1) | un item recense 0 ou 1 vulnérabilité | une vulnérabilité est recensée par 0 ou 1 item | à gauche |
| CITER | Alerte GitHub (0,1) | Vulnérabilité (0,N) | une alerte GitHub cite 0 ou 1 vulnérabilité | une vulnérabilité est citée par 0 à N alertes GitHub | à gauche |
| RÉSUMER | Article de newsletter (0,1) | Publication (0,N) | un article de newsletter résume 0 ou 1 publication | une publication est résumée par 0 à N articles de newsletter | à gauche |
| DÉSIGNER | Entrée Zotero (0,1) | Publication (0,N) | une entrée Zotero désigne 0 ou 1 publication | une publication est désignée par 0 à N entrées Zotero | au-dessus |
| PUBLIER | Dépôt suivi (0,N) | Version publiée (1,1) | un dépôt suivi publie 0 à N versions | une version est publiée par un seul dépôt suivi | à gauche |
| ANNOTER | Surlignage (1,1) | Entrée Zotero (0,N) | un surlignage annote une seule entrée Zotero | une entrée Zotero est annotée par 0 à N surlignages | au-dessus |
| PORTER | Item (0,N) | Étiquette (1,N) | un item porte 0 à N étiquettes | une étiquette est portée par 1 à N items | à gauche, plus bas (question ci-dessous) |
| ÉCRIRE | Auteur (1,1) | Publication (0,N) | un auteur écrit une seule publication | une publication est écrite par 0 à N auteurs | à gauche |
| COMPRENDRE | Dépôt suivi (1,N) | Paquet suivi (1,1) | un dépôt suivi comprend 1 à N paquets suivis | un paquet suivi est compris dans un seul dépôt suivi | au-dessus |
| TOUCHER | Alerte GitHub (1,N) | Paquet touché (1,1) | une alerte GitHub touche 1 à N paquets | un paquet touché l'est par une seule alerte GitHub | au-dessus |

**Spécialisation (X, exclusion sans totalité)** : Item, l'entité générique, est placée au-dessus de
ses sous-entités (Version publiée, Clip de page web, Alerte GitHub, Article de newsletter, Entrée
Zotero). Respecté.

Un auteur est une place dans la liste des auteurs d'une publication, pas une personne (légende du
MCD) : d'où « un auteur écrit une seule publication ».

Question ouverte (Sabine) : la règle « à gauche » admet un sujet plus bas que son complément (ici
Item, à gauche mais en dessous d'Étiquette) ; une règle plus stricte serait « le sujet en haut à
gauche du complément ».
