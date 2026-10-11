# Bac à sable BigQuery de K-B

La collecte « dépôts qui montent » (#16) interroge GH Archive, un jeu de données public sur
BigQuery. Elle tourne dans un projet Google Cloud **sans compte de facturation** : c'est le bac à
sable. Au-delà du quota gratuit (1 Tio lu par mois), une requête est refusée, jamais facturée.

## Le projet

Console Google Cloud → sélecteur de projet → **Nouveau projet** : `k-b-bigquery`, sans
organisation, **sans compte de facturation**. Dans BigQuery, le badge « Bac à sable » le confirme.
Ne jamais cliquer sur « Mettre à niveau » : cela rattache la facturation.

## Le compte de service

Une identité « robot », distincte du compte Google, sous laquelle le pipeline se connecte.

1. **IAM et administration** → **Comptes de service** → **Créer un compte de service** :
   `k-b-collecte`.
2. Rôle : **Utilisateur de job BigQuery** (`roles/bigquery.jobUser`), et aucun autre. Il suffit
   pour lancer des requêtes dans le projet ; GH Archive est public.
3. Aucun accès donné à un utilisateur.

## La clé

Compte `k-b-collecte` → onglet **Clés** → **Ajouter une clé** → **Créer une clé** → **JSON**.
Le fichier téléchargé vaut un mot de passe. Le ranger hors du dépôt, dans un dossier non
synchronisé (ni iCloud, ni Dropbox), lisible par soi seul :

```
mkdir -p ~/.dev-project-config/k-b && chmod 700 ~/.dev-project-config
mv ~/Downloads/k-b-bigquery-*.json ~/.dev-project-config/k-b/bigquery-key.json
chmod 600 ~/.dev-project-config/k-b/bigquery-key.json
```

Puis, dans le `.env` à la racine du dépôt (chemin absolu : `~` n'y est pas développé) :

```
GOOGLE_APPLICATION_CREDENTIALS=/Users/<compte>/.dev-project-config/k-b/bigquery-key.json
```

La clé n'expire pas. Pour la remplacer : en créer une nouvelle, puis supprimer l'ancienne dans
l'onglet **Clés**. Google désactive d'office une clé détectée dans un dépôt public.

## Vérifier

Depuis la racine du dépôt :

```
uv run --env-file .env --with google-cloud-bigquery python -c "import os; from google.cloud import bigquery as bq; print('variable :', 'présente' if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') else 'ABSENTE'); c=bq.Client(); print('projet :', c.project); j=c.query('SELECT COUNT(*) FROM \`githubarchive.day.20260930\` WHERE type = \"WatchEvent\"', job_config=bq.QueryJobConfig(dry_run=True, use_query_cache=False)); print('dry_run : %.1f Mo lus' % (j.total_bytes_processed/1e6))"
```

La commande n'affiche jamais la clé, seulement :

- `présente` ou `ABSENTE` : la variable est lue, ou non ;
- `projet : k-b-bigquery` : la clé est valide et appartient au bon projet ;
- `dry_run : 16.5 Mo lus` (le 2026-10-01) : le rôle permet de lancer une requête. Un `dry_run`
  n'exécute rien et ne consomme pas de quota ; une erreur 403 signale un rôle manquant.

`--with` fournit la bibliothèque pour cette seule commande, sans l'ajouter au projet.

## Le plafond de la collecte

`kb collect` (source `gh_archive`) fait un `dry_run`, puis exécute la requête avec
`maximum_bytes_billed` = **650 Mo par fenêtre, 2 Go au plus** (`compute_bytes_cap`,
`src/k_b/sources/gh_archive.py`). Au-delà, la source échoue sans rien exécuter ; seul un
rattrapage déjà plafonné par la borne de 2 Go perd ses fenêtres les plus anciennes. Sans la
variable `GOOGLE_APPLICATION_CREDENTIALS`, la source est sautée. Les valeurs viennent des mesures
ci-dessous (décision de Sabine du 2026-10-11, journal ADR).

### Mesures du 2026-10-11

Toutes les tailles sont en octets lus selon BigQuery ; un `dry_run` n'exécute rien et ne
consomme pas de quota.

**Chaque fenêtre de 3 jours prise seule** (`dry_run` de `TRENDS_QUERY`, une fenêtre) :

| Fenêtre finissant le | Jour | Lu |
|---|---|---|
| 2026-09-26 | samedi | 312 350 287 |
| 2026-09-27 | dimanche | 393 374 342 |
| 2026-09-28 | lundi | **433 499 230** (la plus lourde) |
| 2026-09-29 | mardi | 421 584 757 |
| 2026-09-30 | mercredi | 329 235 750 |
| 2026-10-01 | jeudi | 305 929 300 |
| 2026-10-02 | vendredi | 301 502 134 |
| 2026-10-03 | samedi | 339 253 973 |
| 2026-10-04 | dimanche | 323 085 505 |
| 2026-10-05 | lundi | 320 319 082 |
| 2026-10-06 | mardi | 295 174 718 |
| 2026-10-07 | mercredi | 204 735 578 |
| 2026-10-08 | jeudi | 143 161 861 |
| 2026-10-09 | vendredi | 98 688 339 |
| 2026-10-10 | samedi | 133 780 468 |

**Plusieurs fenêtres en une requête** (les plus récentes finissant le 2026-10-10) :

| Fenêtres | Jours lus | Lu | Par jour lu |
|---|---|---|---|
| 1 | 3 | 133 780 468 | 44,6 Mo |
| 7 | 9 | 661 601 551 | 73,5 Mo |
| 15 | 17 (24/09 → 10/10) | 1 582 987 509 | 93,1 Mo |
| 30 | 32 | 3 218 149 666 | 100,6 Mo |

Une journée entière pèse 1 060 Mo dans BigQuery (table du 2026-10-10, métadonnées) ; la requête
n'en lit que 4 colonnes : 133,8 Mo pour trois jours.

Commande (lancée par Sabine dans le terminal de K-B ; elle n'affiche que des octets) :

```python
from datetime import date, timedelta
from k_b.sources import gh_archive as g

client = g.create_bigquery_client()
last = date(2026, 10, 10)
def dry_run(window_ends):
    job = client.query(g.TRENDS_QUERY, job_config=g.configure_query(window_ends, dry_run=True),
                       timeout=g.QUERY_TIMEOUT_SECONDS)
    return job.total_bytes_processed
for offset in reversed(range(15)):
    end = last - timedelta(days=offset)
    print(end, dry_run([end]))
for count in (1, 7, 15, 30):
    print(count, dry_run([last - timedelta(days=i) for i in reversed(range(count))]))
```

(`uv run --env-file .env python -I <script>` depuis la racine du dépôt.)

### Le calcul des bornes

- **Par fenêtre** : la fenêtre la plus lourde prise seule lit 433 499 230 octets ; × 1,5 = 650 Mo,
  arrondi. Une collecte quotidienne ordinaire (une fenêtre) qui lirait 20 fois son volume
  habituel est arrêtée au `dry_run`. Avec 200 Mo, 12 des 15 fenêtres mesurées auraient échoué
  seules ; avec 300 Mo, 10.
- **Borne** : le rattrapage maximal mesuré, 15 fenêtres (17 jours, du 24/09 au 10/10, période
  lourde de fin septembre comprise), lit 1,58 Go : il tient sous 2 Go, marge × 1,26. Le **pire
  cas**, 17 jours tous au rythme de la fenêtre la plus lourde (433,5 / 3 = 144,5 Mo par jour),
  donnerait environ 2,46 Go : c'est une estimation, pas une mesure ; il dépasserait la borne, et
  la collecte retirerait alors ses fenêtres les plus anciennes, en le disant au journal.
- La borne s'applique dès 4 fenêtres (4 × 650 Mo > 2 Go) : c'est seulement là que retirer une
  fenêtre fait baisser le volume plus que le plafond.
- Une collecte quotidienne lit de 100 à 430 Mo selon la période, soit 3 à 13 Go par mois sur le
  1 Tio gratuit.

### Anomalie constatée : les tables de GH Archive incomplètes depuis le 2026-10-06

Les fenêtres finissant du 07 au 10/10 lisent 3 à 4 fois moins que celles de fin septembre, sans
effet de semaine (le samedi 26/09 lit 312 Mo, le samedi 10/10 134 Mo). Vérifié en trois temps.

**1. Métadonnées des tables** (`client.get_table("githubarchive.day.AAAAMMJJ")`, sans requête ni
quota ; le 2026-10-11) :

| Jour | Lignes (`num_rows`) | Taille (`num_bytes`) | Dernière modification (UTC) |
|---|---|---|---|
| 2026-09-24 | 1 479 398 | 1 257 814 536 | 2026-09-25 00:08 |
| 2026-09-25 | 1 774 311 | 1 330 325 030 | 2026-09-26 00:08 |
| 2026-09-26 | 2 352 987 | 1 465 253 987 | 2026-09-27 00:08 |
| 2026-09-27 | 2 955 892 | 1 672 651 390 | 2026-09-28 00:08 |
| 2026-09-28 | 2 515 844 | 1 556 199 186 | 2026-09-29 00:08 |
| 2026-09-29 | 2 116 338 | 1 787 191 349 | 2026-09-30 00:08 |
| 2026-09-30 | 1 255 842 | 2 179 673 217 | 2026-10-01 00:08 |
| 2026-10-01 | 2 073 894 | 1 948 063 993 | 2026-10-02 00:08 |
| 2026-10-02 | 2 040 996 | 2 218 113 075 | 2026-10-03 00:09 |
| 2026-10-03 | 1 954 722 | 2 202 602 748 | 2026-10-04 00:08 |
| 2026-10-04 | 1 807 842 | 1 589 959 674 | 2026-10-05 00:08 |
| 2026-10-05 | 2 005 530 | 1 502 717 348 | 2026-10-06 00:08 |
| 2026-10-06 | 1 505 681 | 1 339 062 715 | 2026-10-07 00:08 |
| 2026-10-07 | **162 528** | 875 351 710 | 2026-10-08 00:08 |
| 2026-10-08 | 891 215 | 860 279 916 | 2026-10-09 00:08 |
| 2026-10-09 | 701 573 | 882 329 676 | 2026-10-10 00:08 |
| 2026-10-10 | 803 270 | 1 060 250 442 | 2026-10-11 00:08 |

**2. Fichiers source** (`curl -sIL https://data.gharchive.org/AAAA-MM-JJ-H.json.gz`, en-têtes
seulement, rien téléchargé ; le 2026-10-11) : les 24 fichiers horaires existent pour chacun des
jours 06, 07, 08 et 10/10, aucun sous 3 Mo. Taille compressée : 06/10 338 Mo, 07/10 196 Mo,
08/10 215 Mo, 10/10 272 Mo.

**3. Événements par heure** (une requête réelle, accordée par Sabine, 49 283 072 octets
facturés ; le 2026-10-11) :

```sql
SELECT _TABLE_SUFFIX AS day, EXTRACT(HOUR FROM created_at) AS hour, COUNT(*) AS events
FROM `githubarchive.day.20*`
WHERE _TABLE_SUFFIX BETWEEN '261005' AND '261010'
GROUP BY day, hour
ORDER BY day, hour
```

| Jour | Heures présentes | Heure la plus faible | Heure la plus forte | Total |
|---|---|---|---|---|
| 2026-10-05 | 24 | 68 888 | 89 685 | 2 005 530 |
| 2026-10-06 | 24 | 6 605 | 90 974 | 1 505 681 |
| 2026-10-07 | 24 | 4 552 | 9 182 | 162 528 |
| 2026-10-08 | 24 | 4 787 | 50 750 | 891 215 |
| 2026-10-09 | 24 | 4 389 | 47 331 | 701 573 |
| 2026-10-10 | 24 | 5 394 | 42 227 | 803 270 |

**Le détail heure par heure** (une seconde exécution de la même requête, accordée par Sabine,
49 283 072 octets facturés, le 2026-10-11 ; sortie écrite telle quelle avant tout traitement) :
les 144 comptes sont dans
[2026-10-11-gh-archive-evenements-par-heure.csv](2026-10-11-gh-archive-evenements-par-heure.csv)
(colonnes `day`, `hour_utc`, `events`), trop longs pour un tableau ici. Ce qu'ils montrent :

| Période (UTC) | Heures | Événements par heure |
|---|---|---|
| 05/10 00:00 → 06/10 16:59 | 41 | 68 888 à 90 974 |
| 06/10 17:00 | 1 | 60 968 : déjà sous le minimum de la période normale, la baisse commence |
| 06/10 18:00 | 1 | 27 666 : la baisse devient franche |
| 06/10 19:00 | 1 | 6 815 : la chute est complète (première heure de la ligne suivante) |
| 06/10 19:00 → 08/10 02:59 | 32 | 4 552 à 9 182 (environ dix fois moins) |
| 08/10 03:00 → 08:59 | 6 | 18 204 à 42 890 (remontée) |
| 08/10 09:00 → 09/10 14:59 | 30 | 36 755 à 50 750 (environ la moitié d'avant) |
| 09/10 15:00 | 1 | 12 743 |
| 09/10 16:00 → 10/10 00:59 | 9 | 4 389 à 6 602 (nouvelle chute) |
| 10/10 01:00 → 05:59 | 5 | 14 340 à 28 577 (remontée) |
| 10/10 06:00 → 23:59 | 18 | 30 480 à 42 227 |

Le script qui a produit le fichier : la requête ci-dessus, exécutée avec
`QueryJobConfig(maximum_bytes_billed=100_000_000)`, chaque ligne écrite par `csv.writer`.

**Constat.** Aucune heure n'est absente, mais des heures sont appauvries. Le 06/10, la baisse
commence dès 17:00 UTC (60 968, sous le minimum de 68 888 de la période normale), devient franche à
18:00 (27 666) et complète à 19:00 (6 815) ; les heures comptent ensuite environ dix fois moins
d'événements qu'avant, jusqu'au 08/10 à 02:59, puis environ moitié moins, avec une nouvelle chute
du 09/10 15:00 au 10/10 00:59. Le 07/10, les fichiers source ne pèsent que 42 % de moins que le
06/10, quand BigQuery compte 89 % d'événements en moins.

**Conclusion, avec sa limite.** Les tables BigQuery de GH Archive sont très probablement
incomplètes par rapport aux fichiers source depuis le 2026-10-06 : un défaut de la source, pas du
code de K-B. Ce n'est pas démontré au sens strict : les événements des fichiers n'ont pas été
comptés (il faudrait les télécharger). La collecte réelle du 2026-10-11 (fenêtre du 08 au 10/10,
48 dépôts) a été faite sur ces données partielles. Le contrôle de la table close est passé (chaque
table a été modifiée vers 00:08 le lendemain) : il ne protège pas de ce cas, et un contrôle des
heures présentes non plus ; il faudrait comparer les volumes d'un jour aux jours précédents. La
fenêtre la plus lourde, qui fixe le plafond par fenêtre, est antérieure à l'anomalie.

**Une piste, pas une cause : les incidents de GitHub sur ces dates.** Recherche du 2026-10-11 sur
la page d'état officielle de GitHub ([githubstatus.com](https://www.githubstatus.com/), historique
des incidents), vue par des résultats de recherche web : aucune page d'incident n'a été ouverte une
à une, et aucun lien direct vers un incident n'a été trouvé. Incidents rapportés :

| Date (UTC) | Services | Ce que la page d'état en dit |
|---|---|---|
| 05/10 23:05 → 06/10 00:11 | facturation et réglages des organisations | une panne réseau entre un centre de données et des bases hébergées dans le cloud |
| 06/10 à partir de 19:57 | Pull Requests, Webhooks | performances dégradées ; migrations d'entreprise suspendues |
| 07/10, impact large de 15:06 à 15:16, résolu à 18:04 | Git Operations, Issues, Actions, Pull Requests | analyse des causes annoncée, non publiée à la date de la recherche |
| 08/10 → 10/10 | — | aucun incident trouvé |

Ce que ces dates disent, et ne disent pas :
- La baisse dans BigQuery commence le 06/10 à 17:00 UTC, près de trois heures **avant**
  l'incident de 19:57. L'incident du 06/10 ne l'explique donc pas à lui seul. Une source
  secondaire non vérifiée cite aussi un incident le 06/10 vers 21:01 UTC ; il n'a pas été retrouvé
  sur la page officielle.
- Aucun incident n'est rapporté du 08 au 10/10, alors que les heures restent appauvries et
  rechutent du 09/10 15:00 au 10/10 00:59.
- Deux baisses peuvent se cumuler : celle des fichiers source le 07/10 (- 42 %) pourrait venir de
  GitHub lui-même, qui aurait émis moins d'événements pendant ses incidents ; celle de BigQuery
  (- 89 %) viendrait plutôt du chargement des fichiers dans les tables. Rien de ceci n'est
  démontré.

## Sources (consultées le 2026-10-01)

- [Try BigQuery using the sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)
- [Get started with authentication](https://cloud.google.com/bigquery/docs/authentication/getting-started)
- [Authenticate with a service account key file](https://cloud.google.com/bigquery/docs/authentication/service-account-file)
