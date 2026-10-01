# Bac à sable BigQuery de K-B

La collecte « dépôts qui montent » (#16) interroge GH Archive, un jeu de données public sur
BigQuery. Elle tourne dans un projet Google Cloud **sans compte de facturation** : c'est le bac à
sable. Au-delà du quota gratuit (1 To lu par mois), une requête est refusée, jamais facturée.

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

## Sources (consultées le 2026-10-01)

- [Try BigQuery using the sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox)
- [Get started with authentication](https://cloud.google.com/bigquery/docs/authentication/getting-started)
- [Authenticate with a service account key file](https://cloud.google.com/bigquery/docs/authentication/service-account-file)
