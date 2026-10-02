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
| API GitHub (dépôts les plus étoilés) | login du propriétaire, dans le nom du dépôt (`owner/repo`), quand c'est une personne | — | oui | oui : il identifie le dépôt |
| GH Archive | login de l'auteur de chaque événement (`actor`) | **oui** : la requête ne le sélectionne pas | non | non |
| API arXiv | noms des auteurs des papiers | — | oui | oui, `author` |
| Web Clipper | auteur de l'article gardé (`author`) ; date où l'utilisatrice l'a gardé (`created`) | — | oui | oui, `author` et `item.saved_at` |
| Zotero | auteurs des papiers ; toute la bibliothèque de l'utilisatrice (notes, surlignages, dates d'ajout) | — | oui, copie de la base | auteurs (`author`), surlignages (`highlight`), date d'ajout (`item.saved_at`) |
| tldr.tech | aucune attendue ; noms d'auteurs d'articles possibles, à vérifier dans #13 | — | oui | non, tant que #13 ne l'a pas décidé |
| CISA KEV | aucune | — | — | — |

K-B ne lit aucun mail : tldr.tech est lu sur le web, et l'éditeur de la newsletter est une
entreprise.

## Fiche 1 — Veille technologique

| Rubrique | Contenu |
|---|---|
| Finalité | Suivre l'actualité tech (papiers, vulnérabilités, versions, dépôts, articles) et répondre à « quoi de neuf cette semaine ». |
| Base légale | Intérêt légitime (art. 6.1.f) : veille professionnelle et formation. Les données sont publiées par les personnes elles-mêmes pour être diffusées, et réduites à un nom. |
| Personnes concernées | Auteurs de papiers arXiv, auteurs d'articles gardés avec Web Clipper, auteurs de releases et d'alertes GitHub, personnes créditées dans une alerte GitHub, propriétaires d'un dépôt du top 100 GitHub. |
| Données | Nom d'auteur et ordre dans la liste des auteurs (`author`, `item_author`). Login GitHub : brut seulement, sauf celui du propriétaire d'un dépôt du top 100, gardé dans le nom du dépôt. Le brut GitHub contient aussi, pour chaque compte cité (auteur, personne créditée, propriétaire), son identifiant numérique et l'URL de son avatar, qui peut être une photo de la personne : brut seulement. |
| Destinataires | L'utilisatrice ; les agents qu'elle lance, par l'API REST. |
| Transferts hors UE | Quand un agent comme Claude Code lit les items par l'API, les noms d'auteurs lus partent chez le fournisseur du modèle, aux États-Unis. Cadre juridique de ce transfert non vérifié. |
| Durée de conservation | **2 ans après la collecte**, dans la base et dans le brut (provisoire, à confirmer dans #20). Le brut et la base ont la même durée : la base doit rester reconstructible depuis le brut. |
| Sécurité | Données hors du dépôt de code (`~/K-B-data/`), jamais publiées ; fichiers lisibles par la seule utilisatrice ; l'API ouvre la base en lecture seule ; secrets en variables d'environnement. |

## Fiche 2 — Bibliothèque de lecture de l'utilisatrice

| Rubrique | Contenu |
|---|---|
| Finalité | Garder les papiers lus et les articles choisis par l'utilisatrice, avec ses surlignages, pour les rapprocher de la veille (bloc « Mes surlignages » des fiches). |
| Base légale | Intérêt légitime (art. 6.1.f) : l'utilisatrice traite ses propres données, pour son usage. |
| Personnes concernées | L'utilisatrice ; les auteurs des papiers et articles gardés (déjà couverts par la fiche 1). |
| Données | Copie de la base Zotero : bibliothèque, notes, surlignages, dates d'ajout. Dans la base K-B : surlignages (`highlight`) et date d'ajout (`item.saved_at`). Le coffre Obsidian (articles gardés avec Web Clipper) reste chez l'utilisatrice. |
| Destinataires | L'utilisatrice ; les agents qu'elle lance, par l'API REST. |
| Transferts hors UE | Comme la fiche 1 : surlignages lus par un agent, envoyés au fournisseur du modèle. |
| Durée de conservation | Copie Zotero du brut : **seule la dernière est gardée** (provisoire). Surlignages et date d'ajout dans la base : comme l'item auquel ils sont rattachés. Zotero et le coffre Obsidian : gérés par l'utilisatrice dans ces outils, pas par K-B. |
| Sécurité | Comme la fiche 1. La copie Zotero n'est jamais publiée ni versionnée. |

## Procédure de tri

Chaque étape dit ce qu'elle fait, si elle est automatisée, et sa fréquence. Le code de la purge
relève de #20 ; chaque passage journalise ce qu'il a supprimé (nombre de lignes et de fichiers,
jamais les noms).

| # | Traitement | Étape | Automatisée | Fréquence |
|---|---|---|---|---|
| 1 | Veille (fiche 1) | Les logins GitHub (auteurs, personnes créditées) ne sont pas lus dans les items ; GH Archive ne sélectionne pas `actor`. | oui, à la lecture et à la requête | à chaque collecte (hebdomadaire) |
| 2 | Veille (fiche 1) | Supprimer les items collectés il y a plus de 2 ans ; la cascade retire leurs liens d'auteurs, surlignages et sous-types. | oui, dernière étape de la collecte | hebdomadaire |
| 3 | Veille (fiche 1) | Supprimer les auteurs qui n'ont plus aucun item. | oui, après l'étape 2 | hebdomadaire |
| 4 | Veille (fiche 1) | Supprimer les fichiers bruts de plus de 2 ans dans `raw/automation/`. | oui, après l'étape 3 | hebdomadaire |
| 5 | Bibliothèque (fiche 2) | Supprimer les copies Zotero du brut sauf la plus récente. | oui, après chaque copie Zotero | hebdomadaire |
| 6 | Les deux | Demande d'une personne. Accès : lui dire ce qui est gardé à son nom. Effacement ou opposition : supprimer son nom de la base, supprimer les fichiers bruts qui le contiennent, et noter le nom dans une liste d'exclusion lue par la fusion, pour qu'une collecte ou une reconstruction ne le réintroduise pas. | non | à la demande, sous un mois (art. 12.3) |
| 7 | Les deux | Relire ce registre : sources ajoutées, champs ajoutés à la base, durées. | non | une fois par an, et à chaque nouvelle source |

L'étape 6 est une exception assumée à la règle du brut jamais modifié : une obligation légale
prime. La liste d'exclusion est elle-même une donnée personnelle ; elle vit hors du dépôt, avec
les données.

## Sources (consultées le 2026-10-02)

- [Le registre des activités de traitement](https://www.cnil.fr/fr/RGPD-le-registre-des-activites-de-traitement) — CNIL
- [Exemple de registre](https://www.cnil.fr/sites/default/files/atoms/files/registre_rgpd_basique.pdf) — CNIL
- [Le règlement général sur la protection des données](https://www.cnil.fr/fr/reglement-europeen-protection-donnees) — CNIL
- [Les six grands principes du RGPD](https://www.cnil.fr/fr/comprendre-le-rgpd/les-six-grands-principes-du-rgpd) — CNIL
