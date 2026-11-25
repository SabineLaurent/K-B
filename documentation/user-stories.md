# Les user stories de K-B

!!! note "Compétences de la certification"

    > Rédaction des spécifications fonctionnelles sous forme de user story.

    — C14

    > Chaque spécification fonctionnelle couvre le contexte, les scénarios d'utilisation et les critères de validation.

    — C14

    > Définition des objectifs techniques d'accessibilité des interfaces.

    — C14

    > Les objectifs d'accessibilités sont directement intégrés aux critères d'acceptation des user stories.

    — C14

    > Les objectifs d'accessibilité sont formulés en s'appuyant sur un des standards d'accessibilité: WCAG, RG2AA, etc.

    — C14

Cette fiche donne les spécifications fonctionnelles de K-B sous forme de <span lang="en">user stories</span>, une par
fonction. Elle est écrite d'après le code de `main` au commit `a1a01efd`: chaque test cité existe à ce commit, avec son
chemin et sa ligne. Les chemins partent de la racine du dépôt.

Les sigles de la fiche: WCAG, les règles pour l'accessibilité des contenus web
(<span lang="en">Web Content Accessibility Guidelines</span>); WCAG2ICT, la note du W3C (<span lang="en">World Wide Web
Consortium</span>) sur l'application des WCAG aux logiciels et aux documents non web; RGAA, le référentiel général
d'amélioration de l'accessibilité, le référentiel français; API, interface de programmation
(<span lang="en">Application Programming Interface</span>).

## La forme d'une story

Une <span lang="en">user story</span> décrit une fonction du point de vue de celui qui s'en sert: qui (<q>en tant que</q>), ce qu'il veut
faire (<q>je veux</q>) et pourquoi (<q>afin de</q>). Elle fixe ce que la fonction doit faire, et dit quand elle est
terminée: quand ses critères de validation sont tenus.

Chaque story suit la forme <q>en tant que…, je veux…, afin de…</q>, puis donne trois parties:

- **le contexte**: ce que fait K-B pour cette fonction, et les commandes ou les routes en jeu;
- **les scénarios d'utilisation**: les cas que la fonction traite, y compris les cas d'erreur;
- **les critères de validation**: ce qui doit être vrai pour que la story soit tenue, chacun avec le test automatisé
    qui le vérifie. Les critères d'accessibilité en font partie: chacun nomme le critère des WCAG qu'il applique.

Une story qui n'a pas d'interface le dit dans ses critères.

Vérifier une story, c'est lancer les tests nommés dans ses critères, par exemple
`uv run pytest -k test_collect_refuses_to_run_without_a_data_directory` ([les tests](tests.md)). Un test qui passe dit
que le critère est tenu dans le code tel qu'il est.

## Les objectifs d'accessibilité

Un objectif d'accessibilité dit ce qu'une interface doit permettre à une personne qui lit avec un lecteur d'écran, qui
navigue au clavier ou qui ne distingue pas les couleurs. Écrit dans les critères d'acceptation d'une story, il se
vérifie comme le reste de la story.

Les interfaces de K-B visent les WCAG 2.1, niveau AA, le niveau que demande le RGAA 4.1.2. Les WCAG sont écrites pour
le web. Pour la console et les fichiers Markdown, qui ne sont pas des pages web, WCAG2ICT dit comment appliquer chaque
critère à un logiciel ou à un document. Chaque interface a ses objectifs, repris dans les critères de validation des
stories:

| Interface | Stories | Objectifs |
|---|---|---|
| La console (`kb` et ses commandes) | F1, F2, F5, F6, F7, F8 | appliqués selon WCAG2ICT: 1.4.1 (utilisation de la couleur), 4.1.3 (messages d'état) |
| Les fiches Markdown du coffre de notes | F5, F6, F7 | appliqués selon WCAG2ICT: 1.3.1 (information et relations), 2.4.4 (fonction du lien selon le contexte) |
| Les deux API | F3, F4 | sans interface: elles rendent du JSON à une application |
| Le site | F9 | 1.3.1, 1.4.1, 1.4.3 (contraste minimum), 1.4.4 (redimensionnement du texte), 1.4.10 (redistribution), 1.4.11 (contraste des éléments non textuels), 2.1.1 (clavier), 2.4.1 (contourner des blocs), 2.4.2 (titre de page), 2.4.7 (visibilité du focus), 3.1.1 (langue de la page), 3.3.1 (identification des erreurs), 3.3.2 (étiquettes ou instructions) |

## F1. Collecter les sources de veille

**Story**: en tant qu'utilisatrice de la veille, je veux collecter en une commande toutes les sources, afin d'avoir
chaque jour les nouveautés sans les chercher à la main.

**Contexte**: les sources de K-B sont de types différents: API web, pages web, fichiers, base de données, système big
data ([la collecte](collecte.md)). La commande `kb collect` les interroge et garde leur réponse brute, telle quelle,
dans le dossier de données.

**Scénarios d'utilisation**

1. Toutes les sources répondent: chaque réponse brute est rangée dans le dossier, et la commande affiche un résumé.
2. Une source échoue: les autres sont collectées et gardées, et la commande le signale par un code de sortie distinct.
3. Une source dont la variable de configuration, clé ou dossier, n'est pas posée est sautée, et la commande le dit.
4. Une source n'a rien de nouveau depuis la collecte précédente: elle n'écrit aucun fichier brut.

**Critères de validation**

- Sans dossier de données, rien n'est lancé (code 2). Test: `test_collect_refuses_to_run_without_a_data_directory`
    (`tests/commands/test_collect_command.py:38`).
- Une source en échec laisse les autres gardées (code 4). Test:
    `test_collect_reports_a_failure_but_still_stores_the_other_sources` (`tests/commands/test_collect_command.py:53`).
- Une source sans sa clé est sautée et nommée. Test: `test_collect_skips_gh_archive_and_says_so_without_the_bigquery_key`
    (`tests/commands/test_collect_command.py:254`).
- Une source sans nouveauté n'écrit aucun fichier brut. Test: `test_collect_succeeds_with_a_source_that_has_nothing_new`
    (`tests/commands/test_collect_command.py:374`).
- Accessibilité, WCAG 1.4.1 (utilisation de la couleur): aucune information n'est portée par la couleur seule. `kb`
    n'écrit aucun code de couleur: le code de `src/k_b/` ne contient ni séquence d'échappement de couleur ni bibliothèque
    de mise en couleur.
- Accessibilité, WCAG 4.1.3 (messages d'état): la fin de la commande est annoncée par une ligne de texte, le résumé,
    qu'un lecteur d'écran lit sans déplacer le focus.

## F2. Ranger la veille en base, sans doublon

**Story**: en tant qu'utilisatrice de la veille, je veux que les items collectés soient rangés dans une base, sans
doublon ni entrée corrompue, afin de pouvoir les interroger et les dater.

**Contexte**: `kb create-db` crée la base; `kb migrate-database` la crée seulement si ses tables manquent. `kb import`
lit les fichiers bruts pas encore importés et écrit leurs items. `kb purge`, une commande à part, purge les fichiers
bruts et les journaux trop anciens. La base est SQLite en local et PostgreSQL en ligne
([l'agrégation, l'import et la base](donnees.md)).

**Scénarios d'utilisation**

1. Des fichiers bruts nouveaux existent: leurs items sont écrits, et un item déjà en base est écarté.
2. Un item est corrompu: il est rejeté, et son motif est gardé dans le journal de l'import.
3. L'import échoue: la base reste telle qu'avant, et aucun fichier brut n'est supprimé.
4. `kb purge` purge les fichiers bruts et les journaux trop anciens; l'import, lui, ne supprime rien.

**Critères de validation**

- Les items bruts sont écrits en base. Test: `test_the_raw_files_go_into_the_database`
    (`tests/etl/test_load_items.py:42`).
- Des fichiers bruts relus laissent la base inchangée: chaque item est écarté et noté dans le journal. Test:
    `test_raw_files_read_again_give_the_same_database_and_journal_every_item_as_a_discard`
    (`tests/etl/test_load_seen_again.py:43`).
- Un item corrompu est rejeté, son motif noté dans le journal, et les autres sont importés. Test:
    `test_an_invalid_release_is_written_to_the_journal_and_the_others_are_imported`
    (`tests/etl/test_load_rejections.py:63`).
- Un import en échec laisse la base inchangée et n'écrit aucun journal. Test:
    `test_a_failed_import_leaves_the_database_and_the_journal_unchanged` (`tests/etl/test_load_rejections.py:87`).
- L'import ne supprime aucun fichier brut et ne lance aucune purge. Test:
    `test_import_deletes_no_raw_file_and_runs_no_purge` (`tests/commands/test_import_command.py:84`).
- Une purge en échec sort en code 1 sans nommer de fichier brut, et la purge suivante purge. Test:
    `test_a_failed_purge_exits_1_names_no_raw_file_and_the_next_purge_purges`
    (`tests/commands/test_purge_command.py:134`).
- Accessibilité, WCAG 1.4.1 et 4.1.3: console, mêmes critères que F1.

## F3. Consulter la veille par l'API de données

**Story**: en tant qu'application cliente, je veux lire les items de la veille et les tendances par une API, afin de
m'en servir sans accéder à la base.

**Contexte**: l'API de données sert la base en lecture seule. Une application cliente y lit `GET /items` (liste
filtrée), `GET /items/{item_id}` (détail d'un item) et `GET /trends` (tendances); ses autres chemins servent le site
([l'API de données](api-donnees.md#les-points-de-terminaison)). Chaque demande porte une clé (F4).

**Scénarios d'utilisation**

1. Le client liste les items d'un type, depuis une date, ou contenant un mot, page par page.
2. Le client lit le détail d'un item.
3. Le client lit les tendances d'une fenêtre de relevé.
4. Le client envoie un paramètre hors bornes: la réponse 422 nomme le paramètre, sans recopier sa valeur.
5. Le client dépasse son débit: la réponse 429 dit quand réessayer.

**Critères de validation**

- Les filtres de type, de date, de texte, de limite et de décalage filtrent comme une lecture de la base. Test:
    `test_kind_since_q_limit_offset_filter_as_the_reading` (`tests/data_api/test_item_router.py:158`).
- Chaque type d'item a son détail. Test: `test_each_kind_has_its_detail` (`tests/data_api/test_item_router.py:394`).
- Le client lit les tendances d'une fenêtre. Test: `test_trends_of_a_given_window`
    (`tests/data_api/test_trend_router.py:60`).
- Un paramètre hors bornes donne 422 avec son seul nom. Test: `test_a_parameter_out_of_bounds_gives_422_with_its_name_only`
    (`tests/data_api/test_item_router.py:188`).
- Au-delà de son débit, un client reçoit 429 avec son attente. Test:
    `test_beyond_its_limit_a_client_gets_429_with_its_wait_and_its_id` (`tests/data_api/test_rate_limit.py:34`).
- Accessibilité: sans interface. L'API rend du JSON à une application.

## F4. Contrôler l'accès aux deux API par clé

**Story**: en tant qu'exploitante, je veux que chaque application cliente ait sa propre clé et que l'API IA n'ouvre
chaque route qu'à un client, afin de limiter l'usage du modèle payant et de pouvoir retirer un accès.

**Contexte**: les deux API refusent toute demande sans clé valide. L'API IA appelle un modèle facturé à l'usage:
chacune de ses deux routes est réservée à une seule commande ([l'API IA](api-ia.md#authentification-et-autorisation)).

**Scénarios d'utilisation**

1. Une demande sans clé, ou avec une clé fausse, reçoit la même réponse 401.
2. Un client se sert d'une route qui n'est pas la sienne: 403.
3. Une clé est retirée de la configuration, puis l'API est redémarrée: ce client reçoit 401, les autres sont toujours
    servis.

**Critères de validation**

- Clé absente et clé fausse: même réponse. Test:
    `test_every_data_route_refuses_a_missing_and_a_wrong_key_with_the_same_body` (`tests/data_api/test_api_keys.py:71`).
- Sur l'API IA, une demande sans clé valide reçoit 401 avant toute lecture de l'API de données. Test:
    `test_a_request_without_a_valid_key_is_refused_before_any_reading` (`tests/ai_api/test_digest_router.py:435`,
    `tests/ai_api/test_trend_report_router.py:530`).
- Clé retirée: 401, les autres clients servis. Test: `test_a_removed_key_gives_401_and_the_other_clients_are_still_served`
    (`tests/data_api/test_api_keys.py:101`).
- Un client hors de sa route: 403. Test: `test_a_client_is_refused_403_on_a_route_that_is_not_its_own`
    (`tests/ai_api/test_digest_router.py:1682`).
- Accessibilité: sans interface.

## F5. Recevoir un compte rendu de veille par sujet

**Story**: en tant qu'utilisatrice de la veille, je veux un compte rendu en français par sujet, chaque affirmation
reliée aux items qui la fondent, afin de lire l'essentiel et de pouvoir vérifier chaque fait.

**Contexte**: `kb digest` demande à l'API IA les comptes rendus des items récents. L'API IA classe les items dans la
liste fermée des sujets, fait rédiger chaque compte rendu par le modèle, puis retire les affirmations que ses
contrôles refusent ([le service d'IA](service-ia.md)). `kb digest` écrit une fiche Markdown par sujet dans le coffre
de notes.

**Scénarios d'utilisation**

1. Des items récents existent: une fiche par sujet est écrite, avec ses affirmations et la liste numérotée de leurs
    sources.
2. Aucun item dans la période: la commande le dit et réussit.
3. La fiche du jour existe déjà: rien n'est demandé au modèle (code 2).
4. Le coffre de notes n'est pas configuré: rien n'est demandé (code 2).

**Critères de validation**

- Une fiche par sujet, annoncée par la commande. Test: `test_digest_writes_the_sheet_of_each_subject_and_says_so`
    (`tests/commands/test_digest_command.py:109`).
- Une fiche du jour existante: rien n'est demandé, code 2. Test:
    `test_digest_with_a_sheet_of_the_day_asks_nothing_and_exits_2` (`tests/commands/test_digest_command.py:386`).
- Chaque affirmation cite ses sources par leur numéro. Test:
    `test_the_sources_are_numbered_in_their_order_and_cited_by_number` (`tests/post/test_digest_sheets.py:701`).
- Les faits extraits pour le contrôle ne sont jamais écrits dans la fiche. Test: `test_the_facts_of_a_claim_are_never_written`
    (`tests/post/test_digest_sheets.py:378`).
- Accessibilité, WCAG 1.4.1 et 4.1.3: console, mêmes critères que F1.
- Accessibilité, WCAG 1.3.1 (information et relations): la fiche a un titre de niveau 1, une liste d'affirmations et
    une section « Sources » de niveau 2, numérotée. Test:
    `test_a_digest_gives_the_sheet_of_its_subject_and_of_the_day_of_its_window` (`tests/post/test_digest_sheets.py:114`).
- Accessibilité, WCAG 2.4.4 (fonction du lien selon le contexte): le texte du lien est l'adresse, précédée du titre de
    l'item dans le même élément de liste, un contexte que 2.4.4 admet. Même test.

## F6. Recevoir le compte rendu des tendances

**Story**: en tant qu'utilisatrice de la veille, je veux un compte rendu des dépôts GitHub qui ressortent depuis le
précédent, afin de repérer les projets qui montent sans parcourir les classements.

**Contexte**: `kb trend-report` demande à l'API IA le compte rendu des fenêtres de relevé de GH Archive postérieures
au précédent. Le modèle choisit au plus cinq dépôts (`src/k_b/ai_api/stages/trend_selection.py:60`) et rédige des
textes courts par dépôt, d'après son README. La commande écrit une fiche Markdown, puis l'inscrit dans un registre.

**Scénarios d'utilisation**

1. Premier compte rendu: il est écrit, puis ajouté au registre.
2. Comptes rendus suivants: seules les fenêtres après la dernière entrée du registre sont demandées.
3. Le compte rendu du jour existe déjà: rien n'est demandé (code 2).

**Critères de validation**

- Le premier compte rendu est écrit puis inscrit. Test: `test_the_first_report_is_written_then_added_to_the_register`
    (`tests/commands/test_trend_report_command.py:102`).
- Le suivant ne demande que les fenêtres nouvelles. Test: `test_the_next_report_asks_the_windows_after_the_last_entry`
    (`tests/commands/test_trend_report_command.py:143`).
- Celui du jour existe: rien n'est demandé, code 2. Test: `test_a_report_of_the_day_asks_nothing_and_exits_2`
    (`tests/commands/test_trend_report_command.py:235`).
- Accessibilité, WCAG 1.4.1 et 4.1.3: console, mêmes critères que F1.
- Accessibilité, WCAG 1.3.1 (information et relations): la fiche a un titre de niveau 1 et des sections de niveau 2.
    Test: `test_a_report_gives_its_period_its_limit_and_a_row_per_repository`
    (`tests/post/test_trend_report_sheets.py:67`).
- Accessibilité, WCAG 2.4.4 (fonction du lien): chaque lien est l'adresse GitHub du dépôt, qui porte son nom. Même
    test.

## F7. Lire les tops

**Story**: en tant qu'utilisatrice de la veille, je veux une fiche par relevé de chaque classement des dépôts GitHub,
les plus étoilés et les plus forkés, afin de voir d'un coup d'œil les projets en tête.

**Contexte**: la collecte relève deux classements de dépôts GitHub, les plus étoilés et les plus forkés.
`kb write-tops` écrit une fiche par relevé de chaque classement dans le coffre de notes, puis garde le dernier relevé
brut et supprime les plus anciens.

**Scénarios d'utilisation**

1. De nouveaux relevés existent: une fiche par relevé est écrite, le dernier relevé est gardé, les plus anciens sont
    supprimés.
2. La commande est relancée sans nouveau relevé: rien de nouveau n'est écrit.
3. Les fiches d'un classement ne peuvent pas être écrites: ses relevés sont gardés, et celles de l'autre classement
    sont écrites (code 4).

**Critères de validation**

- Les fiches sont écrites, puis les relevés anciens supprimés. Test:
    `test_write_tops_writes_the_sheets_of_each_top_then_deletes_the_older_rankings`
    (`tests/commands/test_write_tops_command.py:34`).
- Relancée, la commande n'écrit rien de nouveau. Test: `test_write_tops_again_writes_nothing_new`
    (`tests/commands/test_write_tops_command.py:77`).
- Un classement dont les fiches ne s'écrivent pas garde ses relevés, l'autre est écrit, code 4. Test:
    `test_a_sheet_not_written_keeps_its_rankings_exits_4_and_the_other_top_is_written`
    (`tests/commands/test_write_tops_command.py:164`).
- Accessibilité, WCAG 1.4.1 et 4.1.3: console, mêmes critères que F1.
- Accessibilité, WCAG 1.3.1 (information et relations): le classement est un tableau avec une ligne d'en-tête (rang,
    dépôt, étoiles ou forks, description). Tests: `test_a_ranking_gives_the_sheet_of_its_day_by_rank`
    (`tests/post/test_top_sheets.py:94`), `test_the_sheet_of_the_most_starred_counts_their_stars`
    (`tests/post/test_top_sheets.py:128`).
- Accessibilité, WCAG 2.4.4 (fonction du lien): le texte de chaque lien est le nom du dépôt. Test:
    `test_a_ranking_gives_the_sheet_of_its_day_by_rank`.

## F8. Faire tourner la veille en une commande

**Story**: en tant qu'exploitante, je veux enchaîner les étapes de la veille en une commande, afin qu'une tâche
planifiée puisse la faire tourner seule.

**Contexte**: `kb daily-routine` enchaîne la copie des clips, `kb collect`, `kb import`, `kb purge`, `kb write-tops`
et la publication de la veille (`src/k_b/commands/daily_routine_command.py:44`). `kb digest-watch` réveille les deux
API, lance `kb digest` puis `kb trend-report`, et publie la veille. En ligne, deux tâches planifiées les lancent:
`caj-kb-daily-routine` chaque jour à 08:00 UTC, `caj-kb-digest-watch` le lundi et le jeudi à 10:00 UTC
(`infra/README.md`).

**Scénarios d'utilisation**

1. `kb collect` sort en 0 ou 4: `kb import` suit.
2. `kb collect` sort en 1 ou 2: `kb import` ne tourne pas, les étapes suivantes tournent.
3. Un réglage est refusé: aucune étape ne tourne (code 2).
4. Avec `--dry-run`: les étapes sont listées, aucune ne tourne.

**Critères de validation**

- `kb import` suit une collecte en 0 ou 4. Test: `test_kb_import_runs_after_kb_collect_exits_with_0_or_4`
    (`tests/commands/test_daily_routine_command.py:59`).
- `kb import` ne suit pas une collecte en 1 ou 2, et le reste tourne. Test:
    `test_kb_import_does_not_run_after_kb_collect_exits_with_1_or_2_the_rest_does`
    (`tests/commands/test_daily_routine_command.py:71`).
- Un réglage refusé: aucune étape ne tourne, code 2. Test: `test_a_setting_refused_runs_no_step_and_exits_with_2`
    (`tests/commands/test_daily_routine_command.py:144`).
- `--dry-run` liste sans lancer. Test: `test_the_dry_run_lists_the_steps_runs_none_and_exits_with_0`
    (`tests/commands/test_daily_routine_command.py:154`).
- Accessibilité: sans interface quand une tâche planifiée la lance. Lancée à la main, WCAG 1.4.1 et 4.1.3: console,
    mêmes critères que F1.

## F9. Lire la veille sur le site

**Story**: en tant qu'opératrice de la veille, je veux lire la veille dans un navigateur, la filtrer et ouvrir chaque
item, afin de la parcourir sans ligne de commande, sur un ordinateur, une tablette ou un téléphone.

**Contexte**: le site est privé. Il est rendu par le serveur, sans JavaScript, et lit la veille par l'API de données,
avec sa propre clé. L'accès passe par la connexion Microsoft Entra, puis le site vérifie que l'identifiant est celui
du compte autorisé ([les maquettes et le parcours](maquettes-et-parcours.md#le-parcours-de-loperatrice)).

**Scénarios d'utilisation**

1. Après la connexion, le fil « Quoi de neuf » montre les items d'hier et d'aujourd'hui, par pages de 20.
2. Une recherche par mot, un filtre par sorte et par date: les filtres restent d'une page à l'autre.
3. Un item ouvert affiche son détail. Le lien vers sa source s'ouvre dans un nouvel onglet, que son texte annonce.
4. Les dépôts GitHub en tendance se consultent par fenêtre de jours.
5. Une saisie refusée: un message sous le champ et un résumé en haut du formulaire disent pourquoi.
6. Un autre compte se connecte: il reçoit la page « Accès réservé » (403).

**Critères de validation**

- Le fil montre 20 cartes, le total et la page. Test: `test_the_feed_shows_twenty_cards_the_results_and_the_page`
    (`tests/web/test_feed_page.py:44`).
- Les liens de page gardent les filtres. Test: `test_the_links_of_the_pages_keep_the_filters`
    (`tests/web/test_feed_page.py:92`).
- Chaque sorte d'item a sa page de détail. Test: `test_each_kind_has_its_page_its_title_and_its_h1`
    (`tests/web/test_item_page.py:64`).
- Les tendances donnent le rang et le lien GitHub de chaque dépôt. Test:
    `test_the_rows_give_the_rank_of_the_order_of_the_data_api_and_a_link_to_github` (`tests/web/test_trends.py:144`).
- Seul l'identifiant du compte autorisé passe. Tests: `test_the_object_id_of_the_operator_is_let_through`
    (`tests/web/test_operator_check.py:55`), `test_a_header_of_another_account_or_malformed_is_refused`
    (`tests/web/test_operator_check.py:44`).
- Accessibilité, WCAG 3.1.1 et 2.4.2: chaque page est en français et a son propre titre. Tests:
    `test_a_page_is_an_html_document_in_french` (`tests/web/test_accessibility.py:189`),
    `test_each_page_has_a_title_of_its_own_ending_with_the_name_of_the_site` (`tests/web/test_accessibility.py:194`).
- Accessibilité, WCAG 2.4.1: le premier lien mène au contenu. Test: `test_the_first_link_skips_to_the_content`
    (`tests/web/test_accessibility.py:224`).
- Accessibilité, WCAG 1.3.1: un seul titre de niveau 1, aucun niveau sauté, chaque zone une fois. Tests:
    `test_a_page_has_one_h1_first_and_no_level_skipped` (`tests/web/test_accessibility.py:202`),
    `test_a_page_has_each_landmark_once_each_navigation_named` (`tests/web/test_accessibility.py:211`).
- Accessibilité, WCAG 1.4.3, 1.4.11 et 2.4.7: contrastes de la charte et focus visible. Tests:
    `test_each_pair_of_the_chart_has_its_contrast` (`tests/web/test_stylesheet.py:79`),
    `test_the_focus_ring_is_the_one_of_the_chart` (`tests/web/test_stylesheet.py:85`).
- Accessibilité, WCAG 3.3.1 et 3.3.2: chaque champ a son étiquette, chaque refus son message. Tests:
    `test_every_field_of_the_feed_has_its_label` (`tests/web/test_accessibility.py:458`),
    `test_each_field_refused_says_why_under_it_and_in_the_summary` (`tests/web/test_accessibility.py:491`).
- Accessibilité, WCAG 1.4.1: l'état d'une faille exploitée est dit en mots. Test:
    `test_the_exploited_mark_is_a_word_not_a_colour` (`tests/web/test_accessibility.py:587`).
- Accessibilité, WCAG 1.4.4, 1.4.10 et 2.1.1: zoom à 200 %, affichage sur 320 pixels et clavier, contrôlés hors de la
    suite de tests, par un relevé scripté du 22/11/2026 dans un navigateur piloté
    ([PR n° 704](https://github.com/SabineLaurent/K-B/pull/704)).

## Sources

- Les tests cités, dans `tests/` à `a1a01efd`.
- [WCAG 2.1](https://www.w3.org/TR/WCAG21/), W3C.
- [<span lang="en">Guidance on Applying WCAG 2 to Non-Web Information and Communications Technologies</span>
    (WCAG2ICT)](https://www.w3.org/TR/wcag2ict/), W3C.
- [RGAA 4.1.2](https://accessibilite.numerique.gouv.fr/methode/criteres-et-tests/), Direction interministérielle du
    numérique.
