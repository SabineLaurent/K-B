# Repérer les dépôts GitHub qui montent : la source GH Archive sur BigQuery

- **Date** : 2026-10-11
- **Branche** : `feat/gh-archive-extraction`
- **Issue** : #16 (critère corrigé le 2026-10-11)
- **Fichiers principaux** : `src/k_b/sources/gh_archive.py`, `src/k_b/cli.py`,
  `src/k_b/source_kinds.py`, `tests/sources/test_gh_archive.py`, `docs/bigquery.md`
- **Série** : même forme que la note sur Zotero
  ([2026-10-11-extraire-la-bibliotheque-zotero.md](2026-10-11-extraire-la-bibliotheque-zotero.md)) :
  une source dont la requête vit dans son module, un brut qui n'entre pas encore en base.

## 1. Le pourquoi

La veille de K-B suit des dépôts choisis à l'avance. Il lui manque ce qui fait le buzz ailleurs :
les dépôts qui gagnent soudain beaucoup d'étoiles ou de forks. L'API GitHub ne sait pas le dire :
sa recherche trie par total d'étoiles et s'arrête à 1 000 résultats, et `/events` s'arrête à 300
événements. GH Archive enregistre tous les événements publics de GitHub, une table par jour,
publiée comme jeu de données public sur BigQuery. C'est aussi la seule source « big data » de K-B.

Ce travail **extrait** : chaque `kb collect` compte, par fenêtre de 3 jours, les étoiles et forks
gagnés par dépôt, garde les 30 premiers de chaque classement, et écrit ce résultat tel quel dans
`raw/automated_watch/gh_archive/`. Il n'entre pas encore en base : la table TENDANCE viendra dans
une issue de suite (décision du 2026-10-11).

## 2. Le comment

### 2.1 Une seule requête, qui lit le moins possible

`src/k_b/sources/gh_archive.py:65` — la requête `TRENDS_QUERY`, début :

```sql
  FROM `githubarchive.day.20*`
  WHERE _TABLE_SUFFIX BETWEEN @first_suffix AND @last_suffix
    AND type IN ('WatchEvent', 'ForkEvent')
    AND repo.id IS NOT NULL
```

- `day.20*` est un **joker** : la requête porte sur toutes les tables `day.20AAMMJJ`, et
  `_TABLE_SUFFIX` vaut ce qui suit `20` (`261008` pour le 8 octobre 2026). Le filtre `BETWEEN`
  fait que BigQuery n'ouvre que les tables des jours voulus. Piège corrigé à la relecture du plan :
  le suffixe a 6 chiffres, pas 8 ; la date se reconstruit par `CONCAT('20', _TABLE_SUFFIX)`.
- BigQuery stocke **par colonnes** : il ne lit que les colonnes nommées. La requête en lit quatre
  (`repo.id`, `repo.name`, `type`, `created_at`) ; jamais `actor`, le login de qui a mis l'étoile.
  Une journée entière pèse 1 060 Mo ; trois jours de ces quatre colonnes, 133,8 Mo.
- Toutes les fenêtres d'un rattrapage passent dans **une** requête : chaque jour n'est lu qu'une
  fois, et chaque événement est rattaché aux fenêtres qui le couvrent par une jointure sur
  `UNNEST(@window_ends)`.
- Les valeurs variables sont des **paramètres** (`@first_suffix`, `@window_ends`, `@window_days`,
  `@top_size`), jamais du texte collé dans le SQL : pas d'injection possible, et `TOP_SIZE` ou
  `WINDOW_DAYS` ne s'écrivent qu'à un endroit (constat c6 du premier `/code-review`).

### 2.2 Quelles fenêtres collecter : le rattrapage

`src/k_b/sources/gh_archive.py:196-208` :

```python
    first_end = last_collected_at.astimezone(UTC).date()
    ...
    due_count = (yesterday - first_end).days + 1
    if due_count > MAX_CATCH_UP_WINDOWS:
```

Une fenêtre se nomme par son dernier jour. Une collecte faite le jour L a couvert la fenêtre qui
finit à L-1 ; la suivante prend donc les fenêtres qui finissent de L à hier. Première collecte :
la seule fenêtre qui finit hier. Déjà collecté aujourd'hui : aucune, `fetch` rend `None` et rien
n'est écrit. Au-delà de 15 fenêtres manquées, seules les 15 plus récentes sont prises, et le
journal le dit. La date vient de `last_collected_at`, que `collect.py` n'avance que si la source
réussit : une collecte en échec est reprise à la suivante.

### 2.3 Le plafond : `dry_run`, puis exécution plafonnée

`src/k_b/sources/gh_archive.py:179-180` et `:255` :

```python
def compute_bytes_cap(window_count: int) -> int:
    return min(window_count * MAX_BYTES_PER_WINDOW, MAX_BYTES_BILLED)
...
        if cap < MAX_BYTES_BILLED or len(window_ends) == 1:
```

Un `dry_run` demande à BigQuery combien la requête lirait, sans l'exécuter ni consommer de quota.
Si c'est au-dessus du plafond (650 Mo par fenêtre, 2 Go au plus), la requête n'est pas lancée.
Sinon elle s'exécute avec `maximum_bytes_billed` au même plafond : si BigQuery devait lire plus,
il refuserait lui-même. Deux contrôles, l'un avant, l'autre pendant (défense en profondeur).

Retirer la plus ancienne fenêtre n'aide que quand la borne de 2 Go s'applique : en dessous, chaque
fenêtre retirée baisse le plafond de 650 Mo mais le volume d'un seul jour lu. Le second
`/code-review` a trouvé ce défaut dans la première version de la boucle ; d'où la condition
`cap < MAX_BYTES_BILLED`. Un `dry_run` qui ne donne pas de volume fait échouer la source
(`DryRunVolumeUnknownError`) : échouer fermé.

### 2.4 Valider le résultat avant de l'écrire

`src/k_b/sources/gh_archive.py:117-124` :

```python
class TrendRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_end: date
    repository_id: Annotated[int, Field(gt=0, le=MAX_INT64)]
```

La réponse de BigQuery est une entrée externe, donc non fiable. Avant d'être rendue à
`collect.py`, elle est relue par `read_trends` : modèle Pydantic strict (un booléen n'est pas un
entier), aucun champ en plus (`extra="forbid"` : un `actor` glissé serait refusé), au plus 60
lignes par fenêtre, pas deux fois le même dépôt dans une fenêtre. Le résultat est un
**classement** : une seule ligne invalide le fait refuser en entier (règle 1 des conventions,
exception « classement »). Cette validation a servi dès la première exécution réelle : une ligne
sans `repo.id` ni `repo.name` (14 `ForkEvent` sans dépôt) a été refusée, d'où le filtre
`repo.id IS NOT NULL`.

Les messages d'erreur ne citent une valeur que pour une date ou un nombre
(`FIELDS_QUOTED`, `:51`) ; un nom de dépôt `owner/name` contient le login du propriétaire quand
c'est une personne, il n'est décrit que par sa longueur (règle 3 des conventions, RGPD).

### 2.5 La clé : jamais lue par K-B

`src/k_b/cli.py:136-138` :

```python
    bigquery_key = os.environ.get(BIGQUERY_KEY_VARIABLE)
    if bigquery_key:
        sources.append(GhArchiveSource(create_bigquery_client))
```

La clé du compte de service est un fichier JSON hors du dépôt, désigné par
`GOOGLE_APPLICATION_CREDENTIALS`. K-B ne fait que vérifier que la variable existe ; c'est le client
de Google qui ouvre le fichier. Sans la variable, la source est sautée et `kb collect` l'affiche
(`gh_archive: skipped (...)`), comme Zotero sans son dossier. Le client est créé **dans** `fetch`
(par `create_client`) : une clé invalide fait échouer cette source seule, et les tests passent un
faux client sans jamais appeler BigQuery.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Extraction seule dans #16 | l'estimation tenait ; pas de SQL d'écriture hors de `database/` avant #135 (règle 5) | aller jusqu'à TENDANCE : SQL dans `import_items.py`, dépassement |
| Client `google-cloud-bigquery` | le client officiel : `dry_run`, plafond et clé intégrés | l'API REST à la main : il faudrait signer un jeton avec la clé, donc `google-auth` ou `cryptography` quand même, et un POST |
| Import en tête du module | une seule ligne, lisible ; coût mesuré : 86 à 92 ms par commande `kb` (`python -X importtime`, cache chaud) | import dans les fonctions : environ 90 ms gagnés, au prix de deux imports cachés et d'un import réservé au typage |
| BigQuery plutôt que PySpark | voir la sous-section ci-dessous | PySpark sur les fichiers bruts |
| Fenêtre J-3 à J-1, glissante | trois jours complets ; le jour en cours est partiel | inclure aujourd'hui |
| Rattrapage, 15 fenêtres au plus | les tables passées restent lisibles (ADR du 2026-10-05) ; au-delà de deux semaines, un dépôt qui a monté n'apporte plus grand-chose (Sabine) | pas de rattrapage ; 30 fenêtres ; échouer au-delà (bloquerait la source, comme arXiv #71) |
| 650 Mo par fenêtre, 2 Go au plus | fenêtre la plus lourde mesurée × 1,5 ; le rattrapage maximal mesuré tient sous la borne | 4 Go fixes ; 200 Mo et 300 Mo par fenêtre (13 et 11 des 15 fenêtres mesurées auraient échoué seules) |
| Table de la veille « close » | sa dernière heure arrive vers 00:08 UTC le lendemain | aucun contrôle |
| Source sautée sans la clé | une machine sans clé ne fait pas échouer chaque collecte | toujours lancer et échouer |
| Fixture tirée d'une vraie collecte | consigne de Sabine du 2026-10-10 | une fixture inventée |

**BigQuery plutôt que PySpark.** PySpark traiterait les fichiers bruts de `data.gharchive.org` (un
JSON compressé par heure). Pour une fenêtre de 3 jours, il faudrait d'abord rapatrier 72 fichiers,
environ 0,8 Go compressés (272 Mo pour la seule journée du 10/10, mesurés par les en-têtes
`Content-Length`), les décompresser et lire chaque événement en entier, `actor` compris (à
écarter ensuite : contraire à la minimisation). BigQuery fait l'inverse : le calcul va aux
données, déjà chargées chez Google ; il ne lit que les quatre colonnes utiles (133,8 Mo), et seul le
résultat arrive chez nous (8 764 octets). Il n'y a ni Java ni cluster à installer, et le bac à
sable est gratuit et plafonné. Le besoin tient en SQL : filtrer, compter, classer. Spark
redeviendrait le bon outil si les données étaient déjà chez nous en fichiers, si le traitement
dépassait le SQL (apprentissage automatique, transformations en Python), ou pour un flux continu
(Structured Streaming).

**La dépendance, simplement.** `google-cloud-bigquery` est la bibliothèque officielle de Google
pour parler à BigQuery depuis Python. Elle sait trouver la clé, envoyer la requête avec ses
paramètres, faire un `dry_run` et poser le plafond. Elle en amène 25 autres (dont `grpcio` pour le
réseau et `cryptography` pour signer avec la clé) : c'est le prix de ne pas réécrire tout ça.

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_first_collection_takes_the_window_that_ends_yesterday`, `test_the_windows_missed_since_the_last_collection_are_caught_up`, `test_a_second_collection_the_same_day_takes_no_window`, `test_the_catch_up_keeps_the_most_recent_windows_up_to_its_maximum` | le calcul des fenêtres, sans décalage d'un jour |
| `test_fetch_runs_a_dry_run_then_the_query_capped_with_its_parameters` | `dry_run` d'abord, puis plafond et paramètres au format `AAMMJJ` |
| `test_the_cap_is_650_mb_a_window_up_to_2_gb`, `test_fetch_drops_the_oldest_windows_while_the_bound_applies`, `test_fetch_drops_no_window_below_the_bound`, `test_fetch_refuses_to_run_when_the_dry_run_gives_no_volume` | le plafond, la boucle corrigée, l'échec fermé |
| `test_the_query_never_reads_the_actor`, `test_the_raw_result_holds_no_actor`, `test_the_message_never_quotes_a_whole_row` (et ses voisins) | aucun login d'auteur lu ; aucun nom de dépôt dans une erreur |
| `test_collect_skips_gh_archive_and_says_so_without_the_bigquery_key`, fixture `no_bigquery_key` | sans clé, la source est sautée ; les tests ne peuvent pas appeler BigQuery |
| Code cassé exprès (plafond retiré, fenêtre décalée, `actor` ajouté, filtre `repo.id` retiré), puis remis à la main | chaque défaut fait échouer au moins un test |
| `kb collect` réel du 2026-10-11 : code 0, `gh_archive: ok`, 133 780 468 octets lus, 48 dépôts, aucun `actor` | la chaîne entière marche sur le bac à sable |
| `uv run pytest`, `ruff check`, `ruff format --check`, `mypy --strict` verts | les contrôles du dépôt |

## 5. Contrôle de la qualité des données : un exemple complet

Ce travail a produit un exemple de contrôle qualité, de la mesure à la documentation
(`docs/bigquery.md`, section « Anomalie constatée »).

1. **Mesure.** Pour fixer le plafond, chaque fenêtre a été mesurée par `dry_run`. Les fenêtres qui
   finissent du 07 au 10/10 lisent 3 à 4 fois moins que celles de fin septembre.
2. **Anomalie.** Ce n'est pas un effet de semaine : un samedi de septembre lit 312 Mo, un samedi
   d'octobre 134 Mo.
3. **Vérification, du moins coûteux au plus coûteux.** Les métadonnées des tables (gratuites) : le
   07/10 a 162 528 lignes contre 1 505 681 la veille. Les fichiers source (en-têtes, rien
   téléchargé) : les 24 heures existent, le volume ne baisse que de 42 %. Une petite requête
   réelle (49 Mo, accordée par Sabine), puis la même pour garder les 144 comptes heure par
   heure : aucune heure ne manque, mais le 06/10 la baisse commence dès 17:00 UTC (déjà sous le
   minimum de la période normale), devient franche à 18:00 et complète à 19:00 ; ensuite, les
   heures ont environ dix fois moins d'événements qu'avant (fichier joint à `docs/bigquery.md`).
4. **Conclusion et sa limite.** Les tables BigQuery sont très probablement incomplètes par rapport
   aux fichiers source depuis le 06/10 en fin de journée (UTC) : un défaut de la source, pas de
   K-B. Ce n'est pas démontré au sens strict (les fichiers n'ont pas été comptés). La collecte réelle du jour en dépend.
5. **Documentation.** Chiffres datés, commandes exactes, conclusion et limite dans
   `docs/bigquery.md` et dans les specs ; un contrôle de complétude est proposé en issue de suite.

Leçon : le contrôle « table close » est passé sur ces tables. Un contrôle de forme ne voit pas
une donnée appauvrie ; il faut comparer des volumes.

## 6. Ce que tu dois pouvoir défendre

- **Pourquoi BigQuery et pas l'API GitHub, ni PySpark ?** L'API ne sait pas dire ce qui monte
  (plafonds de 1 000 résultats et de 300 événements). PySpark demanderait de rapatrier et de lire
  ~0,8 Go compressés par fenêtre ; BigQuery calcule là où sont les données et ne lit que quatre
  colonnes. Section 3.
- **Que se passe-t-il si une requête lit trop ?** Le `dry_run` l'arrête avant toute exécution ; si
  l'estimation était fausse, `maximum_bytes_billed` fait refuser la requête par BigQuery ; et le
  bac à sable, sans facturation, refuse au-delà du quota. `gh_archive.py:232-268`.
- **Où sont les données personnelles ?** `actor` n'est jamais lu (`test_the_query_never_reads_the_actor`).
  Le nom `owner/name` peut contenir le login du propriétaire : gardé parce qu'il identifie le
  dépôt (registre des traitements), jamais cité dans une erreur. `gh_archive.py:51`, `:347`.
- **Si K-B n'est pas lancé pendant une semaine ?** La collecte suivante rattrape les 7 fenêtres
  en une requête (661,6 Mo mesurés, sous le plafond de 2 Go). Au-delà de 15, les plus anciennes
  sont abandonnées, et le journal le dit. `gh_archive.py:187-208`.
- **Les valeurs du plafond sont-elles choisies au hasard ?** Non : 433,5 Mo pour la fenêtre la plus
  lourde mesurée, × 1,5 ; 1,58 Go mesurés pour 15 fenêtres sous la borne de 2 Go. Tableau daté et
  commande dans `docs/bigquery.md`.

## 7. Zones non vérifiées

- **La complétude des tables de GH Archive depuis le 06/10** n'est pas démontrée : seulement
  fortement suggérée (section 5) : les événements des fichiers source n'ont pas été comptés.
- **Le contrôle « table close »** repose sur un constat (dernière modification vers 00:08 UTC), pas
  sur une garantie documentée de GH Archive ; il ne voit ni une heure appauvrie ni un jour absent.
- **Le pire cas de la borne** (2,46 Go pour 15 fenêtres en période lourde) est une estimation, pas
  une mesure.
- **Le comportement du client Google** quand `total_bytes_processed` est absent d'un `dry_run` est
  supposé possible (le type l'autorise) ; il n'a pas été observé.
- La création du client sans clé valide n'a été testée qu'avec un faux client.

## 8. Ce qui reste

- **TENDANCE en base** : lecteur et écrivain du brut, totaux d'étoiles et de forks par GraphQL
  (après le passage à httpx, #86), borne 64 bits à déplacer dans `items.py`. Issue de suite.
- **Contrôle de complétude** des tables de GH Archive (comparer le volume d'un jour aux jours
  précédents) : proposé en issue de suite, non codé.
- Le sort des tables `repository` et `star_gain` de `schema.sql` reste ouvert (journal ADR).

Commits non commentés à part : `574fd01` (la règle 5 exclut `gh_archive.py`, section 2.1 sur la
requête dans son module) et les commits `docs:` (specs, registre, ADR), repris dans les sections
3, 5 et 8.
