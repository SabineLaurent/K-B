# Registre des traitements de données personnelles

Les traitements de données personnelles de K-B : ce qui est écarté dès la collecte, ce qui est
gardé et combien de temps, et la procédure de tri qui tient ces durées. Une fiche par finalité,
comme le recommande la CNIL. Les tables citées sont celles de [stockage.md](stockage.md).

Une donnée publique reste une donnée personnelle : un nom d'auteur ou un login rattaché à une
personne entre dans le registre, même publié par la personne elle-même.

Contexte : K-B est un outil personnel, pour une seule utilisatrice ; il relève probablement de
l'exemption des activités strictement personnelles (RGPD art. 2.2.c). Le registre est tenu
quand même : l'exemption tomberait si l'outil servait un usage professionnel ou d'autres
personnes.

**Responsable des traitements** : l'utilisatrice de K-B, propriétaire du dépôt. Pas de
sous-traitant.

## Inventaire par source

| Source | Donnée personnelle | Écartée dès la collecte | Gardée dans le brut | Gardée dans la base |
|---|---|---|---|---|
| API GitHub | login de l'auteur d'une release ou d'une alerte ; login des personnes créditées dans une alerte (`credits` : qui a trouvé ou corrigé la faille) | — | oui | **non** : écarté à la lecture (minimisation) |
| API GitHub (texte d'une release) | login ou @mention écrits par les auteurs de la release dans ses notes (`body`), texte libre | — | oui | oui, `release.body`, gardé tel que reçu, sans filtre |
| API GitHub (dépôts les plus étoilés) | login du propriétaire, dans le nom du dépôt (`owner/repo`), quand c'est une personne | — | oui | oui : il identifie le dépôt |
| GH Archive | login de l'auteur de chaque événement (`actor`) | **oui** : la requête ne le sélectionne pas | non | non |
| API arXiv | noms des auteurs des papiers | — | oui | oui, `publication.authors` (liste JSON, dans l'ordre d'arXiv) |
| Web Clipper | auteur de l'article gardé (`author`) ; date où l'utilisatrice l'a gardé (`created`) | — | oui | oui, `author` et `item.saved_at` |
| Zotero | auteurs des papiers ; ce que l'utilisatrice a enregistré et surligné (titres, étiquettes, surlignages et commentaires, dates d'ajout, nom du fichier PDF) | **oui** : la requête ne lit ni les notes, ni les résumés, ni les autres annotations, ni les bibliothèques de groupe | oui, l'extrait JSON de chaque collecte | non : l'extrait n'est pas encore lu vers la base |
| tldr.tech | aucune : les pages ne portent ni auteur ni expéditeur (vérifié dans #13) ; un résumé peut citer une personnalité publique | — | oui | sans objet (aucune donnée personnelle collectée) |
| CISA KEV | aucune | — | — | — |

K-B ne lit aucun mail : tldr.tech est lu sur le web, et l'éditeur de la newsletter est une
entreprise.

## Fiche 1 — Veille technologique

| Rubrique | Contenu |
|---|---|
| Finalité | Suivre l'actualité tech (papiers, vulnérabilités, versions, dépôts, articles) et répondre à « quoi de neuf cette semaine ». |
| Base légale | Intérêt légitime (art. 6.1.f) : veille professionnelle et formation. Les données sont publiées par les personnes elles-mêmes pour être diffusées, et réduites à un nom. |
| Personnes concernées | Auteurs de papiers arXiv, auteurs d'articles gardés avec Web Clipper, auteurs de releases et d'alertes GitHub, personnes créditées dans une alerte GitHub, personnes citées dans les notes d'une release, propriétaires d'un dépôt du top 100 GitHub. |
| Données | Noms des auteurs d'un papier, en liste JSON dans l'ordre d'arXiv (`publication.authors`). Login GitHub : brut seulement, sauf celui du propriétaire d'un dépôt du top 100, gardé dans le nom du dépôt, et sauf un login ou une @mention écrits dans les notes d'une release, gardées telles que reçues (`release.body`). Constat sur la collecte du 2026-10-07 : 12 des 100 notes de release contiennent un `@mot` (`@Claude`, `@file`, `@mention`, `@team`…) ; aucun n'a été vérifié comme étant un compte. Le brut GitHub contient aussi, pour chaque compte cité (auteur, personne créditée, propriétaire), son identifiant numérique et l'URL de son avatar, qui peut être une photo de la personne : brut seulement. |
| Destinataires | L'utilisatrice ; les agents qu'elle lance, par l'API REST. |
| Transferts hors UE | Quand un agent comme Claude Code lit les items par l'API, les noms d'auteurs lus partent chez le fournisseur du modèle, aux États-Unis. Cadre juridique de ce transfert non vérifié. |
| Durée de conservation | Celle du mode d'acquisition de la source, tenue dans `src/k_b/config.py` (`RETENTION_YEARS_BY_ACQUISITION_MODE`) : pour la veille (`watch`), **2 ans après la collecte**, dans la base et dans le brut (provisoire, à confirmer dans #20). Le brut et la base ont la même durée : la base doit rester reconstructible depuis le brut. |
| Sécurité | Données hors du dépôt de code (`~/K-B-data/`), jamais publiées ; fichiers lisibles par la seule utilisatrice ; l'API ouvre la base en lecture seule ; secrets en variables d'environnement. |

## Fiche 2 — Bibliothèque de lecture de l'utilisatrice

| Rubrique | Contenu |
|---|---|
| Finalité | Garder les papiers lus et les articles choisis par l'utilisatrice, avec ses surlignages, pour les rapprocher de la veille (bloc « Mes surlignages » des fiches). |
| Base légale | Intérêt légitime (art. 6.1.f) : l'utilisatrice traite ses propres données, pour son usage. |
| Personnes concernées | L'utilisatrice ; les auteurs des papiers et articles gardés (déjà couverts par la fiche 1). |
| Données | Extrait JSON de la bibliothèque Zotero, écrit à chaque collecte : documents, auteurs, étiquettes, surlignages et commentaires, dates d'ajout, nom du fichier PDF ; pas les notes. Dans la base K-B : rien pour l'instant, l'extrait n'est pas encore lu. Le coffre Obsidian (articles gardés avec Web Clipper) reste chez l'utilisatrice. |
| Destinataires | L'utilisatrice ; les agents qu'elle lance, par l'API REST. |
| Transferts hors UE | Comme la fiche 1 : surlignages lus par un agent, envoyés au fournisseur du modèle. |
| Durée de conservation | Extraits Zotero du brut : tous gardés ; **aucune durée décidée, aucune purge codée** (constat du 2026-10-11). Surlignages et date d'ajout dans la base : comme l'item auquel ils sont rattachés. Zotero et le coffre Obsidian : gérés par l'utilisatrice dans ces outils, pas par K-B. |
| Sécurité | Comme la fiche 1. La base Zotero n'est lue que par une copie temporaire, supprimée à la fin de chaque extraction ; ni cette copie ni les extraits ne sont publiés ou versionnés. |

## Procédure de tri

Chaque étape dit ce qu'elle fait, si elle est automatisée, et sa fréquence. Le code de la purge
relève de #20 ; chaque passage journalise ce qu'il a supprimé (nombre de lignes et de fichiers,
jamais les noms).

| # | Traitement | Étape | Automatisée | Fréquence |
|---|---|---|---|---|
| 1 | Veille (fiche 1) | Les logins GitHub des champs d'auteur et de crédit (auteurs, personnes créditées) ne sont pas lus dans les items ; GH Archive ne sélectionne pas `actor`. Les notes d'une release sont lues telles que reçues, avec les logins ou @mentions qu'elles contiennent. | oui, à la lecture et à la requête | à chaque collecte (une par jour) |
| 2 | Veille (fiche 1) | Supprimer les items collectés depuis plus longtemps que la durée de leur mode d'acquisition (`src/k_b/config.py` ; 2 ans pour la veille). Les auteurs d'un papier partent avec lui : ils sont une colonne de `publication`. Constat : le schéma n'a de suppression en cascade ni vers les sous-types (`release`, `advisory`) ni vers les référentiels (`publication`, `vulnerability`). | prévue en dernière étape de la collecte ; pas encore codée (#83) | à chaque collecte (une par jour) |
| 3 | Veille (fiche 1) | Supprimer les fichiers bruts de `raw/automated_watch/` plus anciens que la durée du mode `watch` (`src/k_b/config.py` ; 2 ans). | prévue après l'étape 2 ; pas encore codée (#83) | à chaque collecte (une par jour) |
| 4 | Bibliothèque (fiche 2) | Supprimer la copie temporaire de la base Zotero, succès ou échec. | oui, à la fin de chaque extraction (testé) | à chaque collecte |
| 5 | Les deux | Demande d'une personne. Accès : lui dire ce qui est gardé à son nom. Effacement ou opposition : supprimer son nom de la base, supprimer les fichiers bruts qui le contiennent, et noter le nom dans une liste d'exclusion lue par la fusion, pour qu'une collecte ou une reconstruction ne le réintroduise pas. Dans la base, un nom d'auteur est dans la liste JSON de chaque papier (`publication.authors`) et un login peut être dans les notes d'une release (`release.body`) : l'effacement réécrit ces valeurs, ce n'est pas une suppression de ligne. | non | à la demande, sous un mois (art. 12.3) |
| 6 | Les deux | Relire ce registre : sources ajoutées, champs ajoutés à la base, durées. | non | une fois par an, et à chaque nouvelle source |

L'étape 5 est une exception assumée à la règle du brut jamais modifié : une obligation légale
prime. La liste d'exclusion est elle-même une donnée personnelle ; elle vit hors du dépôt, avec
les données.

## Sources (consultées le 2026-10-02)

- [Le registre des activités de traitement](https://www.cnil.fr/fr/RGPD-le-registre-des-activites-de-traitement) — CNIL
- [Exemple de registre](https://www.cnil.fr/sites/default/files/atoms/files/registre_rgpd_basique.pdf) — CNIL
- [Le règlement général sur la protection des données](https://www.cnil.fr/fr/reglement-europeen-protection-donnees) — CNIL
- [Les six grands principes du RGPD](https://www.cnil.fr/fr/comprendre-le-rgpd/les-six-grands-principes-du-rgpd) — CNIL
