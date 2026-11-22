# Ramener le README à un README classique, et donner au site ce qu'il portait

- Date : 2026-11-22
- Branche : `docs/classic-readme-and-short-page-names`
- Issue : #684
- Fichiers principaux : `README.md`, `documentation/produit.md`, `documentation/utilisation.md`,
  `documentation/donnees.md`, `.github/workflows/docs.yml`, `documentation/accessibilite.md`,
  `mkdocs.yml`, `docs/ADR/journal-decisions-projet.md`

Série : la note du 2026-11-18, `2026-11-18-publier-les-fiches-en-site-accessible.md`, pose le site ; celle-ci lui donne
le contenu du README.

## Le pourquoi

Le README faisait 955 lignes : le produit, la conduite du projet, puis 712 lignes de procédures en 30 blocs. Sabine a
demandé, le 2026-11-21 : « Je veux un readme, tout ce qu'il y a de plus classique […] comme on retrouve dans plein
de dépôts. » Le
lecteur d'un dépôt y cherche ce qu'est le projet, comment l'installer, le lancer et le tester ; le détail va au site
de `documentation/`, que lit le jury. Rien du contenu technique ne devait se perdre : chaque bloc a une place nommée,
donnée dans la PR.

## Le comment

### Un README aux sections habituelles

`README.md:1-8` :

```markdown
# K-B

**Une bibliothèque de veille tech qui se range toute seule.**

K-B collecte chaque jour l'actualité tech de sept sources, la range en items datés dans une base, et fait écrire par
un modèle de langage des comptes rendus de veille par sujet et un compte rendu des tendances. ...
```

Suivent Fonctionnalités, Architecture, Installation (« En local », « En ligne »), Utilisation (le tableau des 16
commandes, tiré de `uv run kb --help`), « Lancer les tests », Documentation, Licence, Contenus de tiers, Crédits. Deux
contraintes du code tiennent la forme : le titre « Contenus de tiers » est l'ancre de
`tests/fixtures/clipping/LICENCES.md:4`, et son tableau est lu ligne à ligne par
`tests/ai_api/test_digests_reference.py:39-46` ; « Lancer les tests » garde vrai le commentaire de
`pyproject.toml:77`. La fin du fichier, de « Licence » à « Crédits », est recopiée octet pour octet.

### Deux pages nouvelles

`documentation/produit.md` reçoit l'objectif, le périmètre, les contraintes et les coûts du 2026-10-25, datés.
`documentation/utilisation.md` reçoit les procédures que le site n'avait pas : `kb purge`, les deux API, `kb digest`,
`kb trend-report`, `kb download-watch-sheets`, les commandes des jobs, l'image. En les déplaçant, le texte a été
relu contre le code : le README était en retard sur trois points, que la page corrige. Par exemple
(`documentation/utilisation.md:155`) :

```markdown
- `ok, 1 sheet and 1 twin written`;
```

L'ancien README affichait `ok, 1 sheet written`, alors que `commands/write_tops_command.py:95` écrit aussi le
jumeau JSON que l'API de données lit en ligne.

### Les deux usages et la raison de chaque moteur

`documentation/donnees.md:30-34` (nommée `import_et_base_pour_docu.md` avant les noms courts) :

```markdown
## Deux usages, deux moteurs

K-B a deux usages: en local, sur un poste de travail, sans déploiement, avec SQLite
([En local: SQLite, sans serveur](#en-local-sqlite-sans-serveur)); en ligne, déployé sur Azure, avec PostgreSQL
```

La section qui suit donne une raison par moteur, chacune avec sa source : le journal des décisions pour SQLite
(2026-10-02) et pour PostgreSQL (2026-11-06), et la page de Microsoft sur les volumes de Container Apps, relue le
2026-11-22, qui dit qu'un conteneur Blob ne se monte pas. « En local » et « en ligne » remplacent « sur le Mac »
dans tout le site.

### La publication à chaque fusion

`.github/workflows/docs.yml:42-50` :

```yaml
    if: >-
      github.ref == 'refs/heads/main' && (github.event_name == 'workflow_dispatch'
      || (github.event_name == 'push' && vars.PAGES_PUBLISH == 'true'))
    needs: build
    ...
    concurrency:
      group: pages
      cancel-in-progress: false
```

Le job `deploy` publie à chaque push sur `main` quand la variable de dépôt `PAGES_PUBLISH` vaut `true`, et toujours à la
main. Sans la variable, le job est sauté : elle a été choisie quand Pages n'était pas encore activé, et le job aurait
échoué à chaque fusion. Pages est activé depuis le 2026-11-22 ; la variable reste à poser. `concurrency` fait tourner un
seul déploiement ; GitHub garde un seul déploiement en attente et l'annule quand un plus récent arrive.

### Les noms courts des pages

Les dix fiches passent à un nom court (`installation`, `donnees`, `api-ia`…), par `git mv` et un script qui réécrit
chaque renvoi hors des documents datés (`docs/journaling/`, `docs/ADR/`, `docs/20*`) et de `observability/`. Le
titre affiché et le menu ne changent pas ; l'adresse de chaque page, si. Le script tourne en dernier, après la
dernière fusion de `main`, pour attraper les renvois des PR fusionnées avant.

## Choix faits et options écartées

- **Une seule PR**, pas deux (une pour les pages, une pour le README) : décision du Second ; écarté, deux PR, qui
  auraient laissé un README à moitié réduit entre les deux.
- **« Le produit » en tête du menu, « Utiliser K-B » dans « 1. Démarrer »** : décision du Second, sur le plan relu ;
  écarté, une seule page fourre-tout.
- **Aucune section « Utilisateurs »** : règle de Sabine (ni acteurs ni rôles dans les pages).
- **Les coûts du 2026-10-25 gardés, datés, sans leur origine** : décision du Second ; la ligne « Temps », fausse
  (les issues portent une taille, pas des heures), retirée ; la phrase de Microsoft sur le niveau Burstable, retirée.
- **`PAGES_PUBLISH` plutôt qu'une publication sans condition** (option A du Second) : sans elle, `deploy` aurait échoué
  à chaque fusion tant que Pages n'était pas activé (il l'est depuis le 2026-11-22). **`queue: max` écarté** : la
  documentation de GitHub ne le montre qu'au niveau du workflow, et `deploy` le porterait au niveau du job. Décision au
  journal, entrée du 2026-11-22.
- **Six contrôles requis**, le fait lu au ruleset le 2026-11-22, alors que le journal dit `image-build` exigé depuis
  #498 : la question est posée à Sabine.

## Preuve

GitHub Actions ne tourne pas du 2026-11-22 au prochain déploiement : les contrôles exigés de `main` ont été rejoués en
local, avec les commandes de `ci.yml`.

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` vert | aucun lien ni aucune ancre cassés, aucune page hors du menu |
| le contrôle du HTML construit : `lang`, un `h1`, aucun saut de titre, chaque tableau à en-têtes, aucun lien vague | les deux pages nouvelles tiennent les règles de la notice d'AcceDe Web que le HTML montre |
| aucune espace avant « : » ni « ; » hors du code dans `documentation/`, aucun caractère `Cc` ou `Cf` | la règle typographique de Sabine, et aucun caractère invisible |
| `uv run pytest --cov --cov-report=term-missing:skip-covered`, la commande du job `tests` : 5 708 réussis, couverture de 98,55 % pour un seuil de 96 % ; ruff, format et mypy verts | les commentaires changés dans `src/` ne cassent rien, et le tableau « Contenus de tiers » reste lu |
| les commandes du job `audit` (`uv export` de tous les groupes, puis `uvx pip-audit@2.10.1 --require-hashes`) : « No known vulnerabilities found » | aucune version épinglée par `uv.lock` n'a de vulnérabilité connue |
| `uv run pytest -m postgresql` sur `postgres:18.6`, l'image de `ci.yml` par son digest, sous Docker : 350 réussis | le job `tests-postgresql` passe sur le serveur de la CI |
| `diff` de la fin du README contre l'ancienne | la licence, les contenus de tiers et les crédits sont inchangés |
| une relecture de cohérence neuve, puis une relecture du delta | chaque phrase confrontée au code et au journal ; 20 constats triés par le Second |

## Ce que tu dois pouvoir défendre

- **Où est passé le contenu du README ?** Chaque bloc a sa place, dans la table de la PR : la page « Utiliser K-B »
  pour les commandes, les fiches existantes pour le reste ; seuls l'historique et la conduite du projet sont partis.
- **Pourquoi deux SGBD ?** En local, une utilisatrice et un seul écrivain : SQLite, sans serveur. En ligne, plusieurs
  conteneurs : un fichier SQLite sur un partage SMB n'a pas de verrous garantis, et Blob ne se monte pas ; PostgreSQL
  donne aussi un rôle par identité et une connexion par Entra (`documentation/donnees.md:40-56`).
- **Que se passe-t-il si trois fusions se suivent ?** Le déploiement du milieu est annulé par GitHub ; le site publié
  est celui de la dernière, et un tag posé sur le commit annulé attend la relance de son `Docs`
  (`documentation/accessibilite.md`, « Publier »).
- **Pourquoi la publication est-elle conditionnée ?** Pages n'était pas activé quand la condition a été choisie : sans
  `PAGES_PUBLISH`, `deploy` aurait échoué à chaque fusion (`.github/workflows/docs.yml:42-44`). Pages l'est depuis le
  2026-11-22 : poser la variable est le seul geste qui reste pour publier à chaque fusion.

## Zones non vérifiées

- `queue: max` au niveau d'un job : non essayé, d'où le choix de garder le comportement par défaut.
- La publication à chaque fusion : `PAGES_PUBLISH` n'est pas encore posée ; elle se vérifie à la première fusion qui
  suit (la première publication, à la main, a réussi le 2026-11-22).
- Le rendu des deux pages nouvelles au lecteur d'écran, comme pour les autres fiches.

## Ce qui reste

- `image-build` dans le ruleset ou au journal : la réponse de Sabine.
- Les noms courts, par script, après la dernière fusion de `main`, puis les contrôles et un seul push.
- `docs/2026-11-08-tests-api-ia.md:373` cite encore une section du README : un document daté, non réécrit.
- La fiche de l'intégration continue propose encore `git rebase` et `--force-with-lease` pour mettre une branche à
  jour : une issue à part.
