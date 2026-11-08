# Faire entrer le job `tests-postgresql` dans `ci.yml`

- Date : 2026-11-08
- Branche : `ci/tests-postgresql-in-ci`
- Issue : #464
- Fichiers : `.github/workflows/ci.yml`, `.github/workflows/postgresql.yml` (supprimé), `README.md`,
  `MEMORY.md`, `docs/ADR/journal-decisions-projet.md`
- Série : suite de [la note de #417](2026-11-06-creer-la-base-et-importer-en-postgresql.md), qui avait
  créé le workflow à part.

## Le pourquoi

La production tourne sur PostgreSQL. Ses tests (marqueur `postgresql`) tournaient dans un workflow à
part, `postgresql.yml`. Ce n'était pas un choix de fond : pendant que plusieurs PR étaient ouvertes en
parallèle, il évitait qu'elles touchent le même fichier (note de #417, « Choix faits »). Ce besoin a
disparu. Un job de `ci.yml` peut devenir un contrôle exigé par le ruleset de `main`, comme `audit`,
`tests`, `lint` et `types`, pour qu'une PR qui casse PostgreSQL ne soit plus fusionnable.

## Le comment

### Un déplacement, pas une réécriture

Le job garde son nom, son service et ses étapes. Seul le commentaire change, pour dater #418 au
passé :

```yaml
  tests-postgresql:
    ...
        image: postgres:18.6@sha256:bd5dfa494a5a259704365813dbfa5fa6b3e69be7348d43b547f540c730478583
```
(`.github/workflows/ci.yml:58`, `:62`)

Pour GitHub, le nom du contrôle est celui du job, `tests-postgresql`, et pas celui du workflow. Le
ruleset pourra donc l'exiger sous le nom qu'il portait déjà.

### Un seul cache pour tous les jobs

```yaml
          save-cache: false # the jobs share one cache key: only tests saves it
```
(`.github/workflows/ci.yml:82`, même ligne en `:20`, `:40`, `:51`)

Tous les jobs calculent la même clé de cache de `setup-uv`. Seul `tests` l'enregistre, sinon plusieurs
jobs tenteraient d'écrire la même entrée. Le commentaire ne compte plus les jobs : ajouter un job ne
le rend plus faux (constat 5 de la revue).

### Le contrôle du déploiement ne dépend pas des noms de workflow

```
--jq '[.workflow_runs[] | select(.path | startswith(".github/workflows/"))
  | select(.path != ".github/workflows/deploy.yml") | {path, status, conclusion}]')
```
(`.github/workflows/deploy.yml:61-62`)

Avant de déployer un tag, `deploy.yml` prend toutes les exécutions du commit, sauf la sienne, et les
veut toutes vertes (`:64`). Il ne nomme aucun workflow. Supprimer `postgresql.yml` ne change donc rien
pour lui : un commit récent n'a plus qu'une exécution `ci.yml`, qui ne réussit que si ses 5 jobs
réussissent.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| Le job recopié tel quel, sous le même nom | le contrôle garde son nom, le ruleset l'exige sans autre changement | un nom nouveau : une seconde entrée dans le ruleset, sans gain |
| `postgresql.yml` supprimé | deux copies du même job feraient tourner les tests deux fois | le garder en doublon |
| `deploy.yml` inchangé | son filtre est générique (voir plus haut) | y nommer les workflows : un nom de plus à tenir |
| ADR : mention « Révisée le 2026-11-08 » sur l'entrée de #417 | convention du journal pour une décision révisée | une entrée neuve : la décision n'est pas nouvelle, elle est revue |
| Les règles de `main` changées par Sabine, après la fusion | c'est un réglage de GitHub, hors du code, qu'aucune session ne change ; après la fusion, le contrôle exigé correspond à ce que contient `main` | avant la fusion : cela marcherait aussi, puisque l'ancien `postgresql.yml` produit déjà ce contrôle, mais le réglage dépendrait d'une PR pas encore fusionnée |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| YAML relu par Ruby : job de `ci.yml` = job de l'ancien `postgresql.yml` → `true`, les 4 autres jobs identiques à `origin/main` → `true` | le déplacement ne change ni le job ni les autres |
| `actions/runs` de `ccf1455` (`v0.1.0`, le seul tag) : `ci.yml`, `postgresql.yml`, `image.yml`, `infra.yml` en `success` | revenir à `v0.1.0` reste possible |
| CI de la PR : un seul run « CI » à 5 jobs verts, plus aucun run « PostgreSQL » | la preuve du critère de fin, dans la PR |
| GET du ruleset après la commande de Sabine : 5 contextes exigés | `tests-postgresql` protège `main` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi deux workflows avant, un seul maintenant ?** Le workflow à part ne servait qu'au travail
   en parallèle. Ce besoin a disparu, et un seul fichier décrit toute la CI exigée.
2. **Le contrôle exigé change-t-il de nom ?** Non : GitHub nomme un contrôle d'après son job,
   `tests-postgresql` (`ci.yml:58`).
3. **Un tag peut-il partir en ligne avec des tests PostgreSQL rouges ?** Non : `deploy.yml` veut toutes
   les exécutions du commit vertes (`deploy.yml:61-64`), et le job en fait maintenant partie.
4. **Pourquoi un mot de passe absent (`POSTGRES_HOST_AUTH_METHOD: trust`) ?** Le serveur n'existe que
   le temps du job et n'est joignable que depuis le runner : il n'y a aucun mot de passe à garder
   (commentaire du service dans `ci.yml`).

## Zones non vérifiées

- La commande du ruleset n'a été jouée qu'à blanc : son corps a été construit, mais pas envoyé. Le GET
  qui suit la commande de Sabine en apporte la preuve. Que le contrôle porte le nom du job est
  observé : les contrôles de la PR #463 s'appelaient déjà `tests-postgresql`.

## Ce qui reste

- La commande qui ajoute `tests-postgresql` aux contrôles exigés de `main`, lancée par Sabine après la
  fusion (description de la PR, « After merge »).
- Le seuil de couverture des tests (#465), qui touche aussi `ci.yml`, après cette PR.
