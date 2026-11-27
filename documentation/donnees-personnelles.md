# Les données personnelles dans K-B

!!! note "Compétences de la certification"

    > Le registre des traitements de données personnelles intègre l'ensemble des traitements de données personnelles
    > impliqués dans la base de données.

    — C4

    > Les procédures de tri des données personnelles pour la mise en conformité de la base de données avec le RGPD sont
    > rédigées.

    — C4

    > Les procédures de tri détaillent les traitements de conformité (automatisés ou non) à appliquer ainsi que leur
    > fréquence d'exécution.

    — C4

Cette fiche dit quelles données personnelles K-B collecte et garde, source par source, puis donne son registre des
traitements, tenu selon le règlement général sur la protection des données (RGPD), les tables de la base qui portent
une donnée personnelle, et les procédures de tri qui tiennent les durées de conservation: chaque étape, automatisée ou
non, sa fréquence et le code qui la porte. Elle reprend
[le registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md),
`docs/registre-traitements.md`, contrôlé contre le code. Elle est écrite d'après le code de `main` au commit
`39cb5eb9`. Les chemins du code de K-B (`etl/…`, `database/…`, `purge/…`, `commands/…`) partent de
`src/k_b/`, les autres de la racine du dépôt.

## Ce que K-B collecte de personnel

Une donnée publiée par la personne elle-même reste une donnée personnelle: un nom d'auteur, ou un login GitHub
rattaché à une personne, entre dans le registre. Le tableau suivant donne, pour chaque source, ses données
personnelles, ce qui en est écarté dès la collecte, et ce qui en est gardé dans le brut et dans la base.

| Source | Donnée personnelle | Écartée dès la collecte | Gardée dans le brut | Gardée dans la base |
|---|---|---|---|---|
| API GitHub, <span lang="en">releases</span> et alertes | le login de l'auteur d'une <span lang="en">release</span> ou d'une alerte; les logins des personnes créditées dans une alerte (qui a trouvé ou corrigé la faille) | non | oui | non: écartés à la lecture (`etl/sources/github/releases.py:103`, `etl/sources/github/advisories.py:109`) |
| API GitHub, notes d'une <span lang="en">release</span> | les logins et les mentions `@` que ses auteurs écrivent dans les notes, en texte libre | non | oui | oui, `release.body`, gardé tel que reçu |
| API GitHub, dépôts suivis | le login du propriétaire, dans le nom du dépôt (`owner/repo`), quand c'est une personne; la liste des dépôts suivis est choisie par l'utilisatrice (`GITHUB_TRACKED_REPOSITORIES`, `core/config.py:58`) | non | oui | oui, `tracked_repository.repository_name`: il identifie le dépôt, et chaque <span lang="en">release</span> y est rattachée (`release.tracked_repository_id`) |
| API GitHub, dépôts les plus étoilés et les plus forkés | le login du propriétaire, dans le nom du dépôt; la description du dépôt, en texte libre | non | oui: le dernier relevé lisible de chaque top, et ceux qui le suivent (étape 7) | non: les classements n'entrent pas dans la base, leur sorte n'a pas de lecteur (`etl/source_kinds.py:66-77`); `kb write-tops` écrit le nom et la description neutralisée dans une fiche par top et par jour, dans le coffre (`veille/tops/`) |
| GH Archive, événements | le login de l'auteur de chaque événement (`actor`) | oui: la requête ne le lit pas (`etl/sources/gh_archive.py:49-59`) | non | non |
| GH Archive, dépôts qui montent | le login du propriétaire, dans le nom du dépôt (`repo.name`) | non | oui | oui, `trend.repository_name`: il identifie le dépôt |
| API GitHub, dépôts du compte rendu des tendances | le login du propriétaire, dans `owner/repo`; la description, les mots-clés (<span lang="en">topics</span>) et le README, en texte libre | non | non: lus par l'API IA au moment du compte rendu, jamais écrits | non; le compte rendu, dans le coffre (`veille/tendances/`), écrit le nom `owner/repo` des dépôts retenus et les textes du modèle |
| API arXiv | les noms des auteurs des papiers | non | oui | oui, `publication.authors`, une liste JSON dans l'ordre d'arXiv |
| Web Clipper | l'auteur de l'article gardé (`author`); la date où l'utilisatrice l'a gardé (`created`); le texte gardé et la description, qui peuvent nommer des personnes; les tags, choisis par l'utilisatrice | non | oui: la copie de chaque clip nouveau ou changé | le titre, l'URL, `created` (`clip.saved_at`), `published`, le texte gardé (`clip.body`) et les tags normalisés (`tag`, `item_has_tag`); ni `author` ni la description, écartés à la lecture (`etl/sources/clipping.py:360-361`) |
| Zotero | les auteurs des papiers; ce que l'utilisatrice a enregistré et surligné: titres, étiquettes, surlignages et commentaires, dates d'ajout, nom du fichier PDF | en partie: la requête ne lit ni les notes, ni les résumés, ni les autres annotations, ni les bibliothèques de groupe (`etl/sources/zotero.py:73-86`) | oui: le dernier extrait importé, et ceux pas encore importés (étape 7) | le titre, le type, l'URL et la date d'ajout de chaque document (`zotero_entry`); le texte, le commentaire et la date de chaque surlignage (`highlight`); ni les auteurs, ni les étiquettes, ni les PDF |
| tldr.tech | aucune: les pages ne portent ni auteur ni expéditeur; un résumé peut citer une personnalité publique | sans objet | oui | sans objet |
| CISA KEV, le catalogue des vulnérabilités exploitées (<span lang="en">Known Exploited Vulnerabilities</span>) de l'agence américaine de cybersécurité | aucune | sans objet | sans objet | sans objet |

- **K-B ne lit aucun mail**: tldr.tech est lu sur le web, et l'éditeur de cette lettre d'information est une
    entreprise.
- **Le brut de GitHub** garde aussi, pour chaque compte cité (auteur, personne créditée, propriétaire), son
    identifiant numérique et l'adresse de son avatar, qui peut être une photo de la personne: dans le brut seulement,
    que l'étape 3 supprime à 6 mois.
- **Hors de la base, K-B écrit dans le coffre** de l'utilisatrice, sous `veille/`: les fiches des tops, avec le nom
    `owner/repo` et la description neutralisée de chaque dépôt (`post/top_sheets.py:260`); les comptes rendus de
    veille, avec le titre et l'URL de chaque source citée et les affirmations du modèle; le compte rendu des
    tendances, avec le nom `owner/repo` des dépôts retenus et les textes du modèle. Chaque fiche d'un top ou d'un sujet
    a son jumeau JSON, à côté.

## Le registre des traitements

Le responsable des traitements est l'utilisatrice de K-B. Le registre est tenu même pour une seule utilisatrice:
l'exemption des activités strictement personnelles ou domestiques (RGPD, art. 2.2.c) ne vaut pas dès qu'un traitement
a un lien avec une activité professionnelle (considérant 18), et la Cour de justice de l'Union européenne
l'interprète strictement (arrêt Ryneš, C-212/13, 11/12/2014). Le registre a une fiche par finalité, comme le
recommande la Commission nationale de l'informatique et des libertés (CNIL): la veille technologique et la
bibliothèque de lecture. Les destinataires et les hébergeurs des deux fiches suivent, puis les traitements terminés.

### La veille technologique

Le tableau suivant donne la fiche 1 du registre, rubrique par rubrique.

| Rubrique | Contenu |
|---|---|
| Finalité | Suivre l'actualité technique (papiers, vulnérabilités, versions de logiciels, dépôts, articles) et répondre à la question « quoi de neuf cette semaine ». |
| Base légale | L'intérêt légitime (RGPD, art. 6.1.f): la veille professionnelle et la formation. Les données sont publiées par les personnes elles-mêmes pour être diffusées, et réduites à un nom. |
| Personnes concernées | Les auteurs des papiers d'arXiv; les auteurs des <span lang="en">releases</span> et des alertes GitHub, et les personnes créditées dans une alerte; les personnes citées dans les notes d'une <span lang="en">release</span>; les propriétaires d'un dépôt des tops GitHub (les 100 plus étoilés, les 100 plus forkés) ou d'un classement de GH Archive (les dépôts qui montent). |
| Données | Dans la base: les noms des auteurs d'un papier (`publication.authors`); le login du propriétaire dans le nom d'un dépôt suivi (`tracked_repository.repository_name`) ou d'un dépôt d'un classement de GH Archive (`trend.repository_name`); les logins et les mentions `@` des notes d'une <span lang="en">release</span>, gardées telles que reçues (`release.body`). Dans le brut seulement: les logins des auteurs et des personnes créditées, avec l'identifiant numérique et l'adresse de l'avatar de chaque compte. Dans le coffre (`veille/`): le nom `owner/repo` et la description neutralisée des dépôts des tops (`kb write-tops`); le titre et l'URL des sources citées par les comptes rendus de veille (`kb digest`), dont le nom d'un dépôt suivi dans le titre d'une <span lang="en">release</span>, et les affirmations du modèle; le nom `owner/repo` des dépôts du compte rendu des tendances (`kb trend-report`) et les textes du modèle tirés de leur description et de leur README. Les auteurs d'un papier n'entrent dans aucun compte rendu: l'API IA ne les lit pas (`ai_api/connectors/data_api_client.py:70-72`). |
| Destinataires | L'utilisatrice, et les agents qu'elle lance, par l'API de données. Le site de K-B (`kb serve-web`), que l'utilisatrice seule ouvre: la connexion Microsoft Entra, puis son identifiant d'objet, contrôlé à chaque requête (`web/operator_check.py:27-43`). Le site lit l'API de données par la clé de son client `WEB` et ne garde rien; il montre le nom des dépôts suivis et des dépôts des tendances, les auteurs dans le détail d'un papier et les notes dans celui d'une <span lang="en">release</span>, jamais un clip ni une entrée Zotero, dont le détail rend la page 404 (`web/pages.py:134-135`). L'API de données sert au seul client `WEB` les jumeaux JSON des fiches des tops et des comptes rendus de veille (`core/config.py:381-386`). Microsoft, pour le modèle qui rédige les comptes rendus, et comme hébergeur en ligne; Grafana Labs, pour les mesures et les traces de l'API IA ([Les destinataires et les hébergeurs](#les-destinataires-et-les-hebergeurs)). |
| Transferts hors de l'Union européenne | Le modèle des comptes rendus traite les données dans la zone de données de l'Union européenne de Microsoft ([L'envoi des items au modèle des fiches](#lenvoi-des-items-au-modele-des-fiches)). Les mesures et les traces envoyées à Grafana Labs ne portent aucune donnée personnelle, et le contenu des appels au modèle n'y est pas envoyé ([L'envoi des mesures à Grafana Cloud](#lenvoi-des-mesures-a-grafana-cloud)). |
| Durée de conservation | Dans la base, la veille, items et tendances, est gardée 3 ans après la collecte de son fichier, jour pour jour (`RETENTION_YEARS_BY_ACQUISITION_MODE`, `core/config.py:143-147`; [journal des décisions](https://github.com/SabineLaurent/K-B/blob/main/docs/ADR/journal-decisions-projet.md), `docs/ADR/journal-decisions-projet.md:3351-3356` et `:4909`). CISA KEV, catalogue d'état sans donnée personnelle, est gardé sans limite dans la base: une vulnérabilité retirée du catalogue y est marquée (`withdrawn_at`), pas supprimée (`docs/ADR/journal-decisions-projet.md:4909`). Le brut est gardé 6 mois au plus, relevés des tops compris (`RAW_RETENTION_MONTHS`, `core/config.py:155`; `docs/ADR/journal-decisions-projet.md:4909`: la base est la source de vérité). Du brut de CISA KEV, seul le dernier catalogue importé est gardé, avec ceux pas encore importés; des tops, le dernier relevé lisible de chaque top et ceux qui le suivent (étape 7). En ligne, un instantané du partage `job-data`, pris avant chaque mise en production, garde le brut 7 jours de plus, puis est supprimé à la main: 6 mois et 7 jours (`docs/ADR/journal-decisions-projet.md:6309`). Les fiches du coffre (fiches des tops, comptes rendus de veille, compte rendu des tendances) sont gardées sans limite, comme un carnet de veille que l'utilisatrice tiendrait à la main, et supprimées à la main par elle (étape 9). Leur durée est un critère et non un chiffre, comme le permet le RGPD, qui demande d'informer sur la durée ou sur <q>les critères utilisés pour déterminer cette durée</q> (art. 13.2.a). |
| Sécurité | Les données sont hors du dépôt de code, dans le dossier de données (`KB_DATA_DIR`), et ne sont jamais versionnées par git. Les fichiers écrits par `write_file_atomically` (brut, état de collecte, journaux d'import, fiches du coffre) sont créés en mode `0600`, lisibles par leur seul propriétaire (`core/atomic_write.py:17`). Un fichier brut ou une fiche s'écrit une fois: un temporaire caché au nom fixe, créé seulement s'il n'existe pas, réserve l'écriture, et un temporaire trouvé fait échouer la commande (`temporary_file_found`, `post/vault_files.py:53-70`). `kb write-tops` et `kb digest` refusent d'écrire sous un dossier `veille/…` qui est un lien symbolique, ou dans une fiche qui est un lien ou n'est pas un fichier ordinaire, et le contrôlent de nouveau avant chaque écriture (`post/vault_files.py`); `kb write-tops` ne supprime aucun relevé dont la fiche manque (`sheet_missing`). L'API de données ouvre la base en lecture seule. Les secrets sont dans des variables d'environnement. En ligne, le brut, l'état et le coffre de travail des jobs sont dans le partage `job-data`, les fiches publiées dans le conteneur `watch`: sans clé partagée, joints par les seules identités, un rôle par identité et par conteneur, et un verrou contre la suppression (`infra/README.md`, « Le stockage (#420) »). Rien de ce que K-B a collecté ou produit en local ne passe en ligne: la routine en ligne part de zéro (`docs/ADR/journal-decisions-projet.md:6492`). |

### La bibliothèque de lecture

Le tableau suivant donne la fiche 2 du registre, rubrique par rubrique.

| Rubrique | Contenu |
|---|---|
| Finalité | Garder les papiers lus et les articles choisis par l'utilisatrice, avec ses surlignages, pour les rapprocher de la veille. |
| Base légale | L'intérêt légitime (RGPD, art. 6.1.f): l'utilisatrice traite ses propres données, pour son usage. |
| Personnes concernées | L'utilisatrice; les auteurs des papiers gardés, déjà couverts par la fiche 1; les auteurs des articles gardés avec Web Clipper, et les personnes que leur texte nomme. |
| Données | L'extrait JSON de la bibliothèque Zotero, écrit à chaque collecte: documents, auteurs, étiquettes, surlignages et commentaires, dates d'ajout, nom du fichier PDF; pas les notes. Dans la base: le titre, le type, l'URL et la date d'ajout de chaque document; le texte, le commentaire et la date de chaque surlignage; ni les auteurs, ni les étiquettes, ni les PDF. Les clips de Web Clipper: dans le brut, la copie telle quelle de chaque clip nouveau ou changé, son en-tête compris, donc `author`; dans la base, la dernière version de chaque clip, son titre, son URL, sa date d'ajout, sa date de publication, son texte, la date de sa dernière révision (`revised_at`) et ses tags normalisés, sans `author`. Le coffre Obsidian reste chez l'utilisatrice: K-B lit ses clips sans jamais les modifier, et n'écrit que sous `veille/`. |
| Destinataires | L'utilisatrice, et les agents qu'elle lance, par l'API de données. Le site de K-B ne montre ni un clip ni une entrée Zotero (fiche 1, « Destinataires »). |
| Transferts hors de l'Union européenne | Aucune donnée de la bibliothèque n'est envoyée au modèle des comptes rendus: l'API IA ne lit que les sortes de la veille, ni entrée Zotero ni clip (`WatchKind`, `items.py:52-54`). |
| Durée de conservation | Du brut de Zotero, seul le dernier extrait importé est gardé, avec ceux pas encore importés; `kb purge` supprime les autres une fois le nouveau importé (étape 7; `docs/ADR/journal-decisions-projet.md:2929`). Un extrait identique au dernier n'est pas écrit (`etl/sources/zotero.py:225-227`). Les copies des clips du brut sont gardées 6 mois au plus, comme le reste du brut (étapes 3 et 8; `docs/ADR/journal-decisions-projet.md:4909`). Le clip lui-même n'est jamais supprimé par K-B, ni dans le coffre ni dans la base (`docs/ADR/journal-decisions-projet.md:4909`): gardé sans limite dans la base (mode `library`), il n'en part que par un effacement à la demande (étape 5). Un document ou un surlignage supprimé dans Zotero est marqué retiré (`withdrawn_at`), pas supprimé (`docs/ADR/journal-decisions-projet.md:1535`); gardés sans limite, ils ne partent eux aussi que par un effacement à la demande. Une liaison à un tag part avec son clip (`ON DELETE CASCADE`), et un tag dont une réécriture du clip retire la dernière liaison est supprimé avec elle (`database/writers/clip_writer.py:57-63`). Zotero et les clips du coffre sont gérés par l'utilisatrice dans ces outils, pas par K-B. En ligne, les clips du conteneur `clippings` sont gardés sans limite, versions comprises, comme dans la base: un clip appartient à la bibliothèque de l'utilisatrice, qu'elle seule supprime (décision 6, `docs/ADR/journal-decisions-projet.md:6276`). Un clip supprimé du conteneur reste 30 jours en suppression réversible (`infra/modules/exchange-storage.bicep:21-24`). |
| Sécurité | Celle de la fiche 1. En local, la base Zotero n'est lue que par une copie temporaire, hors du dossier de données, supprimée à la fin de chaque extraction (étape 4); ni cette copie ni les extraits ne sont versionnés par git. En ligne, la routine recopie dans le coffre de travail des jobs chaque clip du conteneur `clippings` qui lui manque, puis le collecte (`commands/daily_routine_command.py:45-54`); elle ne collecte pas Zotero: elle n'a pas `KB_ZOTERO_DIR` (`infra/main.bicep:414-420`). |

### Les destinataires et les hébergeurs

#### L'envoi des items au modèle des fiches

Pour rédiger les comptes rendus de veille, l'API IA envoie au modèle des champs des items de la veille, chez
Microsoft, par Microsoft Foundry. C'est un traitement de la fiche 1. Le tableau suivant donne ce qui part, à qui, et
ce que Microsoft en fait.

| Rubrique | Contenu |
|---|---|
| Données envoyées | Une liste blanche de champs par sorte d'item, sans l'auteur ni l'URL de l'item (`FIELDS_BY_KIND`, `ai_api/watch_items.py:86-92`). Toute URL d'un champ devient `[url]`, chaque `@login` des notes d'une <span lang="en">release</span> devient `@user` (`ai_api/watch_items.py:26-33`, `:94`); chaque texte est ensuite coupé, à 500 caractères au classement et à 2 000 à la rédaction (`core/config.py:451`, `:469`). Le détail par sorte d'item est dans [Les données envoyées au modèle](service-ia.md#les-donnees-envoyees-au-modele). |
| Donnée personnelle qui part | Le login du propriétaire d'un dépôt, dans `repository_name` (`owner/repo`), quand c'est une personne: il identifie le dépôt. |
| Destinataire et région | Microsoft, le déploiement `gpt-6.1-sol` de Microsoft Foundry, en France Central, en zone de données de l'Union européenne, à version figée ([Le service d'IA de K-B](service-ia.md)). Pour une zone de données d'une ressource située dans l'Union européenne, la page « <span lang="en">Data, privacy, and security for Foundry Models sold by Azure</span> » de Microsoft écrit: <q><span lang="en">prompts and responses may be processed in that or any other European Union Member Nation</span></q>. |
| Contrat | L'avenant de Microsoft sur la protection des données (DPA, <span lang="en">Microsoft Products and Services Data Protection Addendum</span>), qui régit le traitement des données par les modèles vendus par Azure. |
| Usage par le fournisseur | Ni entraînement ni amélioration des modèles: <q><span lang="en">prompts and completions are not used to train, retrain, or improve the base models</span></q>. K-B n'appelle que `chat/completions` (`ai_api/connectors/llm_client.py:40`) et coupe le cache de la consigne: chaque requête porte `prompt_cache_options` en mode explicite, sans point d'arrêt (`:416-417`). C'est le réglage par défaut (`core/config.py:271`), et `kb serve-ai` refuse de démarrer en production sans lui (`ai_api/connectors/llm_settings.py:91-94`, `:106-118`). La revue automatique des abus ne stocke rien; seules les demandes signalées sont stockées pour une revue humaine, par des employés de Microsoft situés dans l'Espace économique européen. |
| Durée chez K-B | Rien: l'API IA n'écrit rien. |

#### L'envoi des dépôts au modèle des tendances

Pour le compte rendu des tendances, l'API IA lit sur GitHub la fiche de chaque candidat, puis le README des dépôts
choisis, et en envoie une partie au modèle. C'est un traitement de la fiche 1. Le tableau suivant donne ce qui part.

| Rubrique | Contenu |
|---|---|
| Données envoyées | Au choix des dépôts, pour chaque candidat lu (60 au plus, `core/config.py:105`): son nom `owner/repo`, sa description (500 caractères au plus une fois nettoyée), ses 20 premiers mots-clés, son langage, et des nombres calculés par le code (critères, rangs par fenêtre) (`core/config.py:472-473`). À la rédaction, pour chaque dépôt choisi (5 au plus, `core/config.py:483`): son nom sans le login du propriétaire, son langage, sa licence, ses mots-clés, ses critères, les sujets de la veille qu'il porte, sa description et son README, nettoyé puis coupé à 4 000 caractères (`core/config.py:475`). Avant l'envoi, chaque texte est nettoyé: toute URL devient `[url]`, tout `@login` devient `@user`, toute adresse mail devient `[email]` (`ai_api/repository_texts.py:55-66`); commentaires et balises HTML, images et badges, blocs de code délimités et caractères invisibles sont retirés. |
| Donnée personnelle qui part | Au choix, le login du propriétaire, dans `owner/repo`, quand c'est une personne: il identifie le dépôt. À la rédaction, le nom part sans le login. |
| Destinataire et région | Ceux de l'envoi des items: Microsoft, le même déploiement, en zone de données de l'Union européenne. |
| Durée chez K-B | Rien: l'API IA n'écrit rien, et rien de la lecture de GitHub n'est gardé, ni dans le brut ni dans la base. Le compte rendu écrit dans le coffre suit la fiche 1. |

#### L'envoi des mesures à Grafana Cloud

`kb serve-ai` peut exporter en OpenTelemetry les mesures de chaque appel au modèle et les traces de `POST /digests`
vers Grafana Cloud. Le tableau suivant donne ce qui part et ce qui ne part pas.

| Rubrique | Contenu |
|---|---|
| Destinataire et région | Grafana Labs, par Grafana Cloud: une pile au compte de l'utilisatrice, dans la région `prod-eu-west-2`, en Allemagne. |
| Données envoyées | Les mesures des appels au modèle (durées, jetons, coût estimé, état, contrôle du schéma, fidélité), avec des attributs à valeurs fermées; les traces de `POST /digests`: les comptes et l'état de chaque étape, le sujet, l'identifiant de la demande, les identifiants des items (des entiers internes à K-B) et les codes des contrôles qui retirent une affirmation. Jamais un texte d'item, un titre, un auteur, la consigne ni la sortie du modèle: les tests `test_a_measure_carries_closed_attributes_never_a_text` et `test_no_value_holds_a_text_of_the_items_or_of_the_output` le tiennent (`tests/ai_api/test_digest_router.py`). |
| Contenu des appels au modèle | Il n'est pas envoyé. Le réglage `KB_TRACE_CONTENT` vaut `none` par défaut et en ligne (`infra/main.bicep:324`), et `kb serve-ai` refuse de démarrer en production avec `all` (`ai_api/connectors/metrics_export.py:186-187`). |
| Durée | Celle de l'offre gratuite de Grafana Cloud: 14 jours pour les mesures, les traces et les journaux. K-B ne garde rien: l'API IA tient les mesures en mémoire jusqu'à l'envoi. |
| Sécurité | Un jeton aux seuls droits `metrics:write`, `traces:write` et `logs:write`: il écrit, et K-B ne relit rien de ce qu'il envoie. |

#### La base en ligne

Depuis sa mise en ligne, K-B a une base sur Azure, créée vide et remplie par la routine en ligne. Le tableau suivant donne son hébergement, qui la lit,
et sa protection.

| Rubrique | Contenu |
|---|---|
| Hébergeur et région | Microsoft, par Azure Database for PostgreSQL: le serveur `pgsql-kb-<suffixe>` (`infra/modules/postgresql-server.bicep:17`), en France Central, sauvegardes comprises, sans géoredondance (`:37-40`). |
| Données | Celles des tables de la base ([Les tables de la base qui portent une donnée personnelle](#les-tables-de-la-base-qui-portent-une-donnee-personnelle)). |
| Qui la lit | L'API de données, par l'identité `id-kb-data-api`, en lecture seule (rôle `kb_reader`); le job `caj-kb-migrate-database`, par `id-kb-migrate-database`, propriétaire des tables, qui les crée; la routine quotidienne, par `id-kb-daily-routine`, membre de `kb_writer`; l'utilisatrice, administratrice Entra du serveur. Aucun autre rôle ne se connecte à la base (`infra/postgresql/grant-roles.sql:6-9`). |
| Sécurité | Microsoft Entra seul, sans mot de passe (`infra/modules/postgresql-server.bicep:28-29`): chaque connexion présente un jeton de son identité managée, et K-B ne l'envoie que sur une connexion `sslmode=verify-full`. `log_error_verbosity` vaut `TERSE` (`:78-82`): le journal du serveur perd le détail qui recopierait la ligne refusée par une contrainte. |
| Durée | Celle de chaque table, par `kb purge` (procédures de tri). Une ligne purgée ou effacée à la demande reste jusqu'à 7 jours dans les sauvegardes automatiques du serveur (`:39`). |

#### L'hébergement sur Azure

K-B est en ligne. Le tableau suivant donne l'hébergeur, les données qu'il héberge et leurs
durées.

| Rubrique | Contenu |
|---|---|
| Sous-traitant | Microsoft, hébergeur: Azure Container Apps (les deux API, le site et les jobs), Azure Container Registry (l'image), Key Vault (les secrets), Storage (le stockage d'échange `stkbexchange…`, en Blob, et celui des jobs, `stkbjobfiles…`, en Azure Files), Azure Monitor et son espace Log Analytics `log-kb` (les journaux des conteneurs), Microsoft Entra ID (les identités managées et l'inscription d'application du site), Azure Database for PostgreSQL (la base). |
| Services couverts | Les « <span lang="en">Privacy and Security Terms</span> » de Microsoft nomment parmi les « <span lang="en">Microsoft Azure Core Services</span> » Azure Container Apps, Azure Container Registry, Key Vault, Storage, Azure Monitor, Microsoft Entra ID et Azure Database for PostgreSQL; aucun n'est dans le tableau « <span lang="en">Exceptions to the DPA</span> ». |
| Région | France Central, la région du groupe de ressources (`infra/main.bicep:8`). |
| Données hébergées | La routine quotidienne, `caj-kb-daily-routine`, chaque jour à 08:00 UTC (`infra/modules/daily-routine-job.bicep:78`), écrit les données de la fiche 1: le brut, l'état de la collecte et les fiches des tops dans `job-data`, les items dans la base, les fiches dans `watch`. Le job des comptes rendus, `caj-kb-digest-watch`, le lundi et le jeudi à 10:00 UTC par défaut (`infra/main.bicep:32`), écrit les comptes rendus de veille et des tendances dans le coffre de travail de `job-data`, puis les publie dans `watch`; il lit la base par les deux API seulement. |
| Durées en ligne | Les journaux des conteneurs: 30 jours dans `log-kb` (`infra/modules/log-analytics.bicep:14`). Le brut, l'état et le coffre de travail dans `job-data`: les durées de la fiche 1; un partage supprimé y reste 30 jours (`infra/modules/job-files-storage.bicep:53-55`). Les fiches de `watch`: sans limite, versions comprises (fiche 1). Le stockage d'échange porte deux règles de l'infrastructure: ce qui est écrit dans le conteneur `zotero` est effacé, avec ses versions, une fois passés 14 jours après son écriture, et aucune règle n'efface `clippings`; un objet supprimé du compte reste 30 jours en suppression réversible (`infra/modules/exchange-storage.bicep:21-24`, `:215-245`). |
| Site de K-B | `ca-kb-web` montre à l'utilisatrice seule des données de la fiche 1, lues par l'API de données: la connexion Microsoft Entra de la plateforme n'admet que son identifiant d'objet, et le code le contrôle de nouveau à chaque requête (`web/operator_check.py:27-43`). Aucun destinataire de plus. |

#### Le dépôt GitHub de K-B

Le dépôt GitHub de K-B porte le code, ses issues, ses PR (<span lang="en">pull requests</span>) et les journaux de
GitHub Actions. Le tableau suivant donne les données personnelles qu'il porte (relevé du 2026-11-06).

| Rubrique | Contenu |
|---|---|
| Données | Les métadonnées des commits et des tags: le nom de l'autrice et deux adresses électroniques, l'une dans 1 354 commits, l'autre dans 32 commits et 2 tags annotés. Dans les données de test et la documentation: des logins GitHub (auteur de notes de version, personnes créditées dans une alerte, propriétaires de dépôts, dans le nom du dépôt), gardés pour leur finalité de test. La base, le brut et le coffre n'ont jamais été versionnés: aucun chemin `temp/`, `raw/`, `logs/`, `reports/` ni `*.sqlite` dans l'historique. |
| Historique | Gardé tel quel (`docs/ADR/journal-decisions-projet.md:5559`). |
| Durée | Celle du dépôt, sans limite fixée. |
| Effacement | Retirer une valeur de l'historique demande de le réécrire, puis de faire purger par le support de GitHub les `refs/pull/*` et les commits hors des références. |

### Les traitements terminés

- Le 2026-10-16, l'appel du modèle des fiches est passé par l'API Gemini de Google, en repli temporaire; terminé le
    2026-10-17, quand l'appel est passé par Azure AI Foundry. Ce qui est parti, à qui et sous quelles conditions:
    la section du repli chez Google du
    [registre des traitements](https://github.com/SabineLaurent/K-B/blob/main/docs/registre-traitements.md).
- Le 2026-11-16, un banc d'essai a fait passer le classement, la rédaction des fiches et les tendances par onze
    modèles chez trois fournisseurs (Microsoft, Google et Anthropic), pour choisir le modèle de production; terminé le
    2026-11-16. Ce qui est parti et les conditions de chaque fournisseur: la section du banc d'essai du 2026-11-16 du
    même registre.

## Les tables de la base qui portent une donnée personnelle

Le tableau suivant donne les tables de la base qui portent une donnée personnelle, leurs colonnes, ce qu'elles
deviennent après leur durée, et l'étape de la procédure de tri qui les traite. Chaque table et chaque colonne est dans
`database/schema.sql`; la base en ligne a la même structure, dans `database/schema_postgresql.sql`, comparée par
`tests/test_schema_structures.py`, un test qui se lance sur un serveur PostgreSQL.

| Table (colonnes) | Donnée personnelle | Après sa durée | Étape |
|---|---|---|---|
| `publication` (`authors`) | les noms des auteurs d'un papier | vidée avec son item de veille, 3 ans après la collecte: un papier encore cité ne garde que son identifiant arXiv | 2; effacement: 5 |
| `release` (`body`, `url`) | les logins et les mentions `@` des notes; le login du propriétaire dans l'URL | supprimée avec son item de veille, 3 ans après la collecte | 2; effacement: 5 |
| `trend` (`repository_name`) | le login du propriétaire, dans le nom du dépôt | supprimée 3 ans après la collecte de son fichier (`raw_data.collected_at`) | 2; effacement: 5 |
| `tracked_repository` (`repository_name`) | le login du propriétaire d'un dépôt suivi | gardée tant que le dépôt est dans `GITHUB_TRACKED_REPOSITORIES`; retiré de la liste, il part quand plus aucune <span lang="en">release</span> ne le cite | 2 |
| `raw_data` (`raw_file_path`, `stream`) | le login du propriétaire d'un dépôt suivi, dans le nom du dossier de ses <span lang="en">releases</span>, `github_releases_<owner>_<name>` (`etl/sources/github/releases.py:46`) | supprimée quand son fichier n'existe plus et que plus rien ne la cite; celle du dernier fichier importé d'un catalogue d'état reste | 3 |
| `zotero_entry`, `highlight` | ce que l'utilisatrice a enregistré et surligné | gardées sans limite (mode `library`); un document ou un surlignage supprimé dans Zotero est marqué retiré | effacement: 5 |
| `clip` (`title`, `body`), `tag` (`name`), `item_has_tag` | un nom dans le titre ou le texte d'un clip, ou dans un tag | gardées sans limite (mode `library`); un tag que plus aucun clip ne porte est supprimé à l'import (`database/writers/clip_writer.py:57-63`) | effacement: 5 |

La durée de chaque mode d'acquisition est dans `core/config.py:143-147`: 3 ans pour `watch`, aucune pour `library` et
`wiki`. Les sources de la veille sont en mode `watch`, Web Clipper et Zotero en mode `library`
(`database/seed_sources.sql:5-11`). Les catalogues d'état, Zotero et CISA KEV, sont gardés sans limite quel que soit
leur mode (`commands/purge_command.py:32-41`, `purge/base.py:84-95`).

## Les procédures de tri

Deux décisions les fondent (journal des décisions, `docs/ADR/journal-decisions-projet.md:4909`): la base est la source de vérité, et le brut est
gardé 6 mois au plus. Le code de la purge est dans `purge/`, son SQL dans `database/purge.py`, et la commande
`kb purge` la lance. Le tableau suivant donne chaque étape: le traitement qu'elle sert, ce qu'elle fait, si elle est
automatisée, sa fréquence et le code qui la porte.

| # | Traitement | Étape | Automatisée | Fréquence | Code |
|---|---|---|---|---|---|
| 1 | Veille (fiche 1) | Ne pas lire les logins des auteurs et des personnes créditées dans les items; GH Archive ne lit pas `actor`. Les notes d'une <span lang="en">release</span> sont gardées telles que reçues. | oui, à la lecture et dans la requête | à chaque collecte: chaque jour en ligne | `etl/sources/github/releases.py:103`, `etl/sources/github/advisories.py:109`, `etl/sources/gh_archive.py:49-59` |
| 2 | Veille (fiche 1) | Supprimer de la base la veille collectée il y a plus de 3 ans, jour pour jour, puis ce qu'elle laisse sans citation. | oui, par `kb purge`, en une transaction | à chaque `kb purge` | `purge/base.py`, `database/purge.py` |
| 3 | Les deux | Supprimer du brut chaque collection de plus de 6 mois, sauf les catalogues d'état; puis les lignes du registre `raw_data` dont le fichier n'existe plus et que rien ne cite. | oui, par `kb purge` | à chaque `kb purge` | `purge/raw.py`, `purge/registry.py` |
| 4 | Bibliothèque (fiche 2) | Supprimer la copie temporaire de la base Zotero, après un succès, une erreur ou un Ctrl-C; une copie laissée par un processus tué est retirée au début de l'extraction suivante. | oui | à chaque collecte de Zotero | `etl/sources/zotero.py:207-213`, `:231-248` |
| 5 | Les deux | Répondre à la demande d'une personne: accès, effacement ou opposition. | non | à la demande, sous un mois (RGPD, art. 12.3) | (procédure écrite: [Les étapes manuelles](#les-etapes-manuelles)) |
| 6 | Les deux | Relire le registre: sources ajoutées, champs ajoutés à la base, durées. | non | une fois par an, et à chaque nouvelle source | (relecture) |
| 7 | Les deux | Ne garder du brut que le dernier fichier importé de chaque catalogue d'état (Zotero, CISA KEV) et ceux pas encore importés; des tops, que le dernier relevé lisible et ceux qui le suivent. | oui, par `kb purge`; pour les tops, par `kb write-tops` | à chaque `kb purge`; à chaque `kb write-tops` | `purge/catalogs.py`, `post/top_sheets.py:84-85` |
| 8 | Bibliothèque (fiche 2) | Les copies des clips du brut suivent l'étape 3, 6 mois au plus. K-B ne touche jamais au clip du coffre ni au clip de la base. | oui, par l'étape 3 | à chaque `kb purge` | `purge/raw.py` |
| 9 | Les deux | Les fiches du coffre ne sont jamais purgées automatiquement: l'utilisatrice les supprime à la main. | non | à la décision de l'utilisatrice | (procédure écrite: section « Les étapes manuelles ») |
| 10 | Les deux | Effacer, à la fin de chaque test de bout en bout, tout son dossier de données sauf `logs/`: le brut, la base et les journaux d'import. | oui, à la fin de chaque test, réussi ou non | à chaque lancement des tests de bout en bout | `tests/e2e/test_real_sources.py:112-121`, `:197-203` |
| 11 | Les deux | Supprimer les logs de fonctionnement et les journaux d'import de plus de 6 mois. | oui, par `kb purge` | à chaque `kb purge` | `purge/run_records.py` |

`kb purge` tourne chaque jour en ligne, comme étape de `kb daily-routine`
([Sa place dans `kb daily-routine`](#sa-place-dans-kb-daily-routine)). En local, elle se lance à la main, après un
import ou seule:

```sh
KB_DATA_DIR=~/.knowledge_base uv run kb purge
```

ou `make purge`, qui la lance avec le `.env` du dépôt (`Makefile:18-19`).

### L'enchaînement de `kb purge`

`kb purge` date la purge par l'heure de son lancement, en UTC (`commands/purge_command.py:52`),
puis lit une fois la liste des fichiers bruts que la base a importés (`purge/all_purges.py:48-49`). Elle lance ensuite
cinq purges, dans cet ordre (`purge/all_purges.py:39-66`):

1. **Les catalogues remplacés (étape 7).** Dans `raw/selected_library/zotero/` et `raw/automated_watch/cisa_kev/`,
    chaque fichier brut importé avant le dernier importé est supprimé. La liste vient du registre de la base
    (`raw_data`), jamais du dossier: un fichier pas encore importé n'est jamais supprimé, et rien n'est supprimé si le
    dernier fichier importé manque (`purge/catalogs.py:13-35`).
2. **La base (étape 2).** Pour chaque source dont le mode a une durée et qui n'est pas un catalogue d'état, la borne
    est l'heure de la purge moins 36 mois du calendrier (`purge/base.py:84-95`, `core/dates.py:28-35`). Les items
    dont le fichier brut a été collecté avant elle sont supprimés: les sous-types `release`, `advisory` et
    `newsletter_article` d'abord, le schéma n'ayant pas de cascade vers eux; un papier perd ses auteurs, et, s'il est
    encore cité par une `zotero_entry` ou une `newsletter_article`, ne garde que son identifiant arXiv; ses liaisons à
    des tags et ses surlignages partent en cascade (`database/purge.py:17-34`). Les lignes de `trend` partent à la
    même borne, comptée depuis la collecte de leur fichier (`database/purge.py:36-42`). Puis les références que plus
    rien ne cite (`publication`, `vulnerability`) sont supprimées (`database/purge.py:44-62`), et un dépôt suivi sorti
    de `GITHUB_TRACKED_REPOSITORIES` que plus aucune <span lang="en">release</span> ne cite (`purge/base.py:98-113`).
    Le tout tient en une transaction, prise sous le verrou des écrivains (`purge/base.py:35-53`).
3. **Le brut (étape 3).** Chaque collection, un fichier ou un dossier de pages, dont le nom la date de plus de 6 mois
    avant la purge est supprimée, les catalogues d'état mis à part (`purge/raw.py:17-48`). La liste vient des
    dossiers: une collection jamais importée part aussi, et le journal la compte à part. Un nom qui n'est pas une
    heure de collecte n'est jamais supprimé (`purge/raw.py:57-61`); un lien n'est jamais suivi, et une collection qui
    contient un dossier, un lien ou un nom avec une barre oblique inverse est gardée (`etl/raw_store.py:97-118`).
4. **Le registre (fin de l'étape 3).** Une ligne de `raw_data` part quand son fichier n'existe plus et que plus rien
    ne la cite, sauf celle du dernier fichier importé d'un catalogue d'état, que l'import lit. Aucune ligne d'un
    dossier d'acquisition absent, comme un volume non monté, n'est supprimée; une ligne dont le chemin est refusé
    reste (`purge/registry.py:41-78`). Cette purge prend elle aussi le verrou des écrivains (`purge/registry.py:25`).
5. **Les logs et les journaux (étape 11).** Les logs de fonctionnement d'un jour passé (`logs/kb.log.<jour>`,
    `logs/kb-serve-data.log.<jour>`, `logs/kb-serve-ai.log.<jour>`, `logs/kb-serve-web.log.<jour>`) et les journaux
    d'import (`journals/import-journal-<date>.jsonl`) de plus de 6 mois sont supprimés, le jour lu dans leur nom
    (`purge/run_records.py:23-48`, `core/config.py:173-185`). Un autre nom, un dossier ou un lien n'est jamais
    supprimé. Six mois est le bas de la fourchette que recommande la CNIL pour une journalisation, six mois à un an
    (délibération n° 2021-122 du 14 octobre 2021); K-B applique cette durée à tous ses logs, techniques compris, pour
    une seule règle (`docs/ADR/journal-decisions-projet.md:5000`). En ligne, les conteneurs n'écrivent aucun fichier de log
    (`KB_LOG_TO_FILE=false`, `Dockerfile:46`): leur sortie d'erreur part dans `log-kb`, gardée 30 jours; les journaux
    d'import, eux, restent dans `job-data` et suivent cette étape.

**La première erreur arrête les purges suivantes**, et le `kb purge` suivant les relance. Le journal le dit en une
ligne qui nomme le type de l'erreur, et pour une erreur du système de fichiers sa raison, jamais le nom d'un fichier
brut: `purge failed: <type>; run kb purge again` (`commands/purge_command.py:66-74`). Sur SIGTERM ou Ctrl-C, la purge
en cours dans la base est annulée, et ce qui a déjà été supprimé le reste (`purge/base.py:45-51`,
`commands/sigterm.py:22-36`).

Le tableau suivant donne les codes de sortie de `kb purge`.

| Code | Sens | Où |
|---|---|---|
| 0 | les cinq purges ont réussi; le bilan est affiché | `commands/purge_command.py:75-77` |
| 1 | une purge a échoué; les suivantes ne tournent pas, et le `kb purge` suivant les relance | `commands/purge_command.py:66-74` |
| 2 | rien n'est lancé: l'emplacement de la base est refusé, ou la base n'existe pas (`kb create-db`) | `commands/purge_command.py:48-51`, `:60-65` |
| 143, 130 | SIGTERM, SIGINT (Ctrl-C): la purge en cours dans la base est annulée, ce qui a déjà été supprimé le reste | `purge/base.py:45-51`, `commands/exit_codes.py:63-85` |

### Sa place dans `kb daily-routine`

En ligne, le job `caj-kb-daily-routine` lance `kb daily-routine` chaque jour à 08:00 UTC
(`infra/modules/daily-routine-job.bicep:78`). La routine enchaîne ses étapes dans le même processus, dans cet ordre
(`commands/daily_routine_command.py:44-75`):

1. le miroir des clips, du conteneur `clippings` vers le coffre de travail;
2. `kb collect`;
3. `kb import`, qui ne tourne pas si `kb collect` sort en 1 ou en 2;
4. `kb purge`, lancé même après un `kb import` en échec ou non lancé: un import en échec n'a rien validé, et la purge
    lit la base du dernier import validé (journal des décisions, `docs/ADR/journal-decisions-projet.md:6373`);
5. `kb write-tops`, qui écrit les fiches des tops puis supprime les relevés qu'elles remplacent (étape 7);
6. la publication de `veille/` dans le conteneur `watch`.

Le code de sortie de la routine est le pire de ses étapes (`commands/job_routine.py:117-120`). Une purge en échec un
jour est relancée par la routine du lendemain. `kb daily-routine --dry-run` affiche ces six étapes sans en lancer
aucune ([Vérifier cette fiche](#verifier-cette-fiche)).

### Ce que chaque passage journalise

Chaque purge journalise ce qu'elle a supprimé, en nombres, jamais un nom. Le tableau suivant donne la ligne de chaque
passage.

| Passage | Ligne de journal | Où |
|---|---|---|
| les catalogues remplacés | `raw purge: N superseded files deleted` | `purge/catalogs.py:34` |
| la base | `base purge: N items, N trend rows, N references, N tracked repositories deleted` | `purge/base.py:54-57` |
| le brut | `raw purge: N collections older than 6 months deleted, N of them never imported, N kept (a folder or a link inside)` | `purge/raw.py:40-47` |
| le registre | `registry purge: N rows deleted` | `purge/registry.py:37` |
| les logs et les journaux | `logs and journals purge: N files older than 6 months deleted` | `purge/run_records.py:43-47` |
| les relevés des tops | `<top>: N superseded rankings deleted` | `post/top_sheets.py:85` |

`kb purge` journalise aussi `purge started` et `purge finished in <durée>`, puis affiche son bilan sur une ligne
(`commands/purge_command.py:53`, `:75`, `:87-96`). Chaque module de la purge a son test qui vérifie que la ligne donne
des nombres et aucun nom (`test_the_log_gives_numbers_never_a_name`, `tests/purge/`).

### Les étapes manuelles

Chaque étape manuelle a son déclencheur.

- **La demande d'une personne (étape 5)**, déclenchée par sa demande, traitée sous un mois (RGPD, art. 12.3). Elle
    est une exception à la règle du brut jamais modifié: une obligation légale prime.
    - L'accès: dire à la personne ce qui est gardé à son nom.
    - L'effacement ou l'opposition: supprimer son nom de la base et les fichiers bruts qui le contiennent.
        - Un nom d'auteur dans `publication.authors`, un login dans `release.body`: l'effacement réécrit la valeur, il
            ne supprime pas la ligne.
        - Un login de propriétaire dans `trend.repository_name`: l'effacement supprime la ligne.
        - Un nom dans le titre ou le texte d'un clip (`clip.title`, `clip.body`): l'effacement réécrit ces valeurs et
            la copie brute du clip; l'utilisatrice corrige aussi le clip du coffre, où K-B n'écrit jamais.
        - Un nom dans un tag (`tag.name`): la recherche lit aussi `tag.name` et ses liaisons (`item_has_tag`);
            l'effacement réécrit ou supprime le tag, pour tous les clips qui le portent, et dans chaque clip du coffre.
        - Un nom dans un compte rendu de veille (`veille/<sujet>/`): l'effacement édite la fiche et son jumeau JSON.
        - Un login dans une fiche de top (`veille/tops/`), ou un nom dans la description d'un dépôt: d'abord
            `kb write-tops`, pour qu'aucun jour ne perde sa fiche; puis retirer la ligne de ce dépôt de chaque fiche
            et de son jumeau JSON, par une édition du fichier et non sa suppression; enfin supprimer les relevés du
            brut qui le contiennent, sans les réécrire.
        - En ligne, la donnée peut être aussi dans `job-data`, dans les conteneurs du stockage d'échange, dans leurs
            versions et dans les instantanés de `job-data`: un instantané qui la garde est supprimé, et effacer une
            version demande un rôle temporaire (<span lang="en">Storage Blob Data Owner</span>), retiré ensuite, le
            verrou du compte levé le temps du geste (`infra/README.md`, « Les instantanés de `job-data` »).
- **La relecture du registre (étape 6)**, une fois par an et à chaque nouvelle source: les sources ajoutées, les
    champs ajoutés à la base, les durées.
- **La suppression d'une fiche du coffre (étape 9)**, à la décision de l'utilisatrice. Une fiche est dans trois
    endroits, où elle se supprime dans cet ordre: le coffre de travail de `job-data`, puis le conteneur `watch`, puis
    le coffre local. La publication renvoie en effet à `watch` une fiche que `job-data` porte encore, et
    `make download-watch-sheets` recopie en local une fiche que `watch` porte encore. Une fiche d'un top ou d'un sujet
    se supprime avec son jumeau JSON. Dans `watch`, chaque fiche garde ses versions précédentes: les supprimer demande
    un rôle temporaire, retiré ensuite, le verrou du compte levé.
- **Les instantanés de `job-data`**, un avant chaque mise en production: chacun porte sa date de suppression et se
    supprime à la main 7 jours après, par sa date (`infra/README.md`, « Les instantanés de `job-data` »).
- **`kb purge` en local**, lancé à la main, après un import ou seul (`make purge`).
- **Le rapport des tests de bout en bout** (`reports/e2e-report.html`, ignoré par git): un seul fichier, écrasé à
    chaque lancement, retiré à la main par l'utilisatrice.

## Vérifier cette fiche

Depuis la racine du dépôt, au commit `39cb5eb9`:

```bash
# Les durées: 3 ans pour la veille (watch), aucune pour library et wiki; 6 mois pour le brut, les logs et les
# journaux. Attendu: les lignes 143 à 147, puis RAW_RETENTION_MONTHS = 6 (ligne 155) et RECORD_RETENTION_MONTHS = 6
# (ligne 185).
grep -n -A4 "^RETENTION_YEARS_BY_ACQUISITION_MODE" src/k_b/core/config.py
grep -n "^RAW_RETENTION_MONTHS\|^RECORD_RETENTION_MONTHS" src/k_b/core/config.py
# Le mode de chaque source: watch pour cinq sources, library pour Web Clipper et Zotero. Attendu: 7 lignes.
grep -n "'watch')\|'library')" src/k_b/database/seed_sources.sql
# L'ordre des purges de kb purge. Attendu: delete_superseded_raw_files, purge_expired_rows, delete_expired_raw,
# purge_registry, delete_expired_records, dans cet ordre.
grep -n "= delete_\|= purge_" src/k_b/purge/all_purges.py
# Le message d'échec, sans nom de fichier. Attendu: la ligne 69.
grep -n "purge failed" src/k_b/commands/purge_command.py
# Les étapes de kb daily-routine, sur un dossier de données vide, sans rien lancer ni écrire. Attendu: 6 étapes,
# kb purge en quatrième, sans règle, et le code 0.
KB_DATA_DIR="$(mktemp -d)" KB_LOG_TO_FILE=false uv run kb daily-routine --dry-run
# Les tests de la purge, sans PostgreSQL. Attendu: 76 passed, 5 deselected.
uv run pytest tests/purge -q
# kb purge: un échec arrête les suivantes, ne nomme aucun fichier brut, et le kb purge suivant purge. Attendu:
# 7 passed, 1 deselected (le test marqué postgresql).
uv run pytest tests/commands/test_purge_command.py -q
# La routine: kb purge juste après kb import, lancé même après un import en 1 ou en 2. Attendu: 4 passed.
uv run pytest tests/commands/test_daily_routine_command.py -q -k purge
# Les journaux des purges: des nombres, jamais un nom. Attendu: 5 passed.
uv run pytest tests/purge -q -k "never_a_name"
# La minimisation à la collecte: ni le login de l'auteur d'une release, ni les personnes créditées d'une alerte, ni
# actor dans GH Archive. Attendu: 4 passed.
uv run pytest tests/etl/sources/test_github_releases.py tests/etl/sources/test_github_advisories.py tests/etl/sources/test_gh_archive.py -q -k "author_login or credited or actor"
# La copie temporaire de Zotero supprimée (étape 4). Attendu: 4 passed.
uv run pytest tests/etl/sources/test_zotero.py -q -k "temporary_copy or killed_process"
# Les 15 tables de chaque schéma. Attendu: 15 et 15. Leur comparaison, tests/test_schema_structures.py, est marquée
# postgresql: elle se lance avec KB_TEST_POSTGRESQL_URL=<URL d'un serveur> uv run pytest -m postgresql.
grep -c "^CREATE TABLE" src/k_b/database/schema.sql src/k_b/database/schema_postgresql.sql
# En ligne: la routine à 08:00 UTC, les journaux 30 jours, les sauvegardes 7 jours sans géoredondance, les durées du
# stockage d'échange (30 et 14 jours), et le contenu des appels au modèle coupé. Attendu: '0 8 * * *', 30, 7 et
# 'Disabled', 30 et 14, 'none'.
grep -n "cronExpression" infra/modules/daily-routine-job.bicep
grep -n "retentionInDays" infra/modules/log-analytics.bicep
grep -n "backupRetentionDays\|geoRedundantBackup" infra/modules/postgresql-server.bicep
grep -n "softDeleteDays =\|zoteroCopyDays =" infra/modules/exchange-storage.bicep
grep -n "KB_TRACE_CONTENT" infra/main.bicep
```

Un `fichier:ligne` se relit sans changer de commit: `git show 39cb5eb9:<chemin> | sed -n '<début>,<fin>p'`, avec
`src/k_b/` devant un chemin du code de K-B.
