# Documenter les tests et toute la CI dans le README

- Date : 2026-11-08
- Branche : `docs/readme-tests-and-ci`
- Issues : #476 (doc des tests), #477 (doc de la CI)
- Fichier : `README.md`, section « Lancer les tests »
- Série : [faire entrer `tests-postgresql` dans la CI](2026-11-08-faire-entrer-tests-postgresql-dans-la-ci.md),
  [seuil de couverture vérifié par la CI](2026-11-08-seuil-de-couverture-verifie-par-la-ci.md)

## Le pourquoi

Qui reprend K-B doit trouver à un seul endroit à quoi sert chaque outil de test, comment lancer chaque famille
de tests, et ce que fait la CI. Avant cette PR, le README disait que `make test` lançait « tous les tests », ce
qui était faux : `uv run pytest` écarte les tests `e2e` et `postgresql`. Il ne décrivait que les cinq jobs de
`ci.yml` et `image-build`, sans Dependabot, sans la protection de `main` et sans les réglages lus par la CI.

## Le comment

### Ce que `uv run pytest` laisse de côté

```python
MARKERS_LEFT_OUT_BY_DEFAULT = (E2E_MARKER, POSTGRESQL_MARKER)
```

`tests/conftest.py:46`. Un test qui porte l'un de ces marqueurs n'est lancé que si `-m` le nomme. D'où les deux
paragraphes ajoutés : les tests sur PostgreSQL (`README.md:643`) et les tests de bout en bout (`README.md:659`).
Une famille absente de la commande par défaut n'est donc plus cachée. Le tableau des huit paquets du groupe
`dev` (`README.md:633-641`) relie chaque outil à son usage.

### Une table par job, pas par workflow

Le tableau de la CI (`README.md:713-723`) a une ligne par job. Chaque ligne est complète : aucune cellule vide,
ce qui la garde lisible par un lecteur d'écran (RGAA, tableaux à en-têtes). Les déclencheurs des quatre
workflows sont dans la phrase au-dessus.

### Ce qui est requis à la fusion, et ce qui ne compte qu'au déploiement

```yaml
# Not a required check: with its path filter, it would block every pull request that leaves infra/ alone.
```

`.github/workflows/infra.yml:15`. Le ruleset de `main` exige 5 checks. `image-build` et `bicep-build` n'en font
pas partie. Le README dit où ils comptent quand même : le job `check` de Deploy exige que la CI du commit tagué
soit verte, sauf Deploy et les exécutions de Dependabot (`deploy.yml:51-53`, `README.md:747-750`).

### Ce que Dependabot touche, et ce qu'il ne touche pas

```yaml
      - dependency-name: "python"
        update-types: ["version-update:semver-minor", "version-update:semver-major"]
```

`.github/dependabot.yml:24-25`. Ses mises à jour de version ne suivent que les actions et les images du
`Dockerfile`, en correctif et en digest pour `python` et `astral-sh/uv`. `uv.lock` n'a pas d'écosystème déclaré.
Ses mises à jour de sécurité sont activées dans les réglages, et elles couvrent uv depuis le 16/12/2025
([changelog de GitHub, « Dependabot security updates now support uv »](https://github.blog/changelog/2025-12-16-dependabot-security-updates-now-support-uv/),
lu le 2026-11-08 par la relecture). D'où la phrase : seule une mise à jour de sécurité peut ouvrir une PR sur
`uv.lock` (`README.md:736-737`).

## Choix faits et options écartées

- **Une PR pour les deux issues** : elles réécrivaient le même paragraphe de la CI. Deux PR auraient dû se
  rebaser l'une sur l'autre sur les mêmes lignes.
- **Renvoyer à `infra/README.md` pour le déploiement** plutôt que le recopier : il y est déjà décrit étape par
  étape. Une seule source.
- **PR témoin : #475**, existante, avec ses 6 checks. Écarté : ouvrir une PR témoin neuve, qui aurait passé
  l'issue de XS à S.
- **Le ruleset est décrit, pas recréé par commande** : une commande de création n'aurait pas pu être essayée
  ici.
- **uv non fixé en CI** : le fait est écrit (`README.md:725-727`), sans correction. #485 le fixera.
- **Écarté : un `docs/tests.md` séparé**, car l'issue demande le README.

## Preuve

| Commande ou sortie observée | Ce que ça démontre |
|---|---|
| Boucle `for d in mypy … types-pyyaml` de #476 → rien | chaque paquet `dev` est nommé |
| `grep -n "make test .*tous les tests" README.md` → rien | l'erreur sur `make test` est corrigée |
| Boucle sur les jobs de `.github/workflows/*.yml` de #477 → rien | chaque job est nommé |
| `gh api repos/SabineLaurent/K-B/rulesets/25257125` | 5 checks requis, `strict`, fusion par merge seule, aucun contournement |
| `gh pr checks 475` | 5 checks de l'exécution 42473488447, `image-build` de 42473488442, tous verts |
| `gh api …/automated-security-fixes` → `enabled:true` | les mises à jour de sécurité sont activées |
| Journal de l'exécution 42473488447 : « Falling back to latest », uv 0.13.7 | la CI ne fixe pas uv |
| Deux relectures par des sous-agents neufs, en lecture seule ; constats tranchés par time-knight | chaque fait a été revérifié contre `origin/main` et GitHub |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `uv run pytest` ne lance-t-il pas tout ?** Les tests `postgresql` demandent un serveur, et les
   tests `e2e` appellent les vraies sources. La CI lance les premiers dans son propre job ; les seconds restent
   sur le Mac (`tests/conftest.py:46`, `README.md:628`).
2. **Pourquoi `image-build` n'est-il pas requis à la fusion ?** Le ruleset ne l'exige pas. Il compte quand même
   au déploiement, par `check` (`README.md:747-750`). Le pourquoi de ce choix n'est écrit nulle part : voir la
   section suivante.
3. **Où sont les secrets de la CI ?** Cinq secrets du dépôt, lus par `deploy.yml` seul. Le README les nomme,
   sans valeur. Aucun autre workflow ne lit de secret (`README.md:755-761`).
4. **Qui met `uv.lock` à jour ?** Personne d'office. `audit` y cherche les vulnérabilités connues, et seule une
   mise à jour de sécurité de Dependabot peut ouvrir une PR dessus.

## Zones non vérifiées

- Pourquoi `image-build` n'est pas un check requis : aucun texte du dépôt ne le dit. Le README le constate sans
  l'expliquer.
- La commande de `KB_TEST_POSTGRESQL_URL` avec `<rôle>` n'a pas été lancée ici. Elle reprend la forme de
  `ci.yml:79`.
- La couverture d'uv par les mises à jour de sécurité de Dependabot repose sur le changelog de GitHub : aucune PR
  de sécurité ne l'a encore montrée sur ce dépôt.

## Ce qui reste

- #485 fixera uv dans la CI, le `Dockerfile` et le `pyproject.toml`, puis réécrira `README.md:725-727`.
- Une étape de CI nommée pour les tests des données (C13.4) et l'évaluation des sorties du modèle en CI
  (C13.5) ont leurs propres issues.
