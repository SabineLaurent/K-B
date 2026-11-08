# Un seuil de couverture de 96 %, vérifié par la CI

- Date : 2026-11-08
- Branche : `ci/coverage-threshold`
- Issue : #465
- Fichiers : `pyproject.toml`, `.github/workflows/ci.yml`, `README.md`, `docs/ADR/journal-decisions-projet.md`
- Série : suite de #405 (2026-11-06), qui mesurait la couverture sans seuil (journal ADR, « Tests : mesurer la
  couverture par `pytest-cov`, sans seuil ») ; la CI venait d'accueillir `tests-postgresql` (#464,
  [note](2026-11-08-faire-entrer-tests-postgresql-dans-la-ci.md)).

## Le pourquoi

C12 d'E3 demande une couverture souhaitée, établie et vérifiée. La mesure existait depuis #405, mais rien ne
l'imposait : une PR pouvait faire baisser la couverture sans que personne ne le voie. Tu as tranché le 08/11 :
**96 %**, un plancher contre la régression et non une cible. La mesure du jour, 98,41 % sur le Mac, laisse
2,4 points de marge. Cette PR écrit le seuil à un seul endroit et fait échouer la CI en dessous.

## Le comment

### Le seuil, dans la configuration de coverage

```toml
[tool.coverage.report]
...
fail_under = 96
...
precision = 2
```
(`pyproject.toml:80-85`)

`fail_under` est un réglage de `coverage` : sous ce total (lignes et branches de `src/k_b/`, réglages de
`[tool.coverage.run]`), la mesure échoue. Il vit dans `pyproject.toml`, à côté des autres réglages de
coverage, et non dans la commande de CI.

### pytest-cov lit ce seuil tout seul

`pytest-cov` reprend le `fail_under` de coverage quand on ne lui passe pas `--cov-fail-under`
(`pytest_cov/plugin.py:270-271`, version 7.1.0). Toute commande `pytest --cov` vérifie donc le seuil :
`make test-cov` en local, et le job `tests` en CI. Une commande sans `--cov` (`make test`, `uv run pytest`)
ne mesure rien et ne vérifie rien.

### `precision` : l'arrondi avant la comparaison

coverage arrondit le total avant de le comparer : `round(total, precision) < fail_under`
(`coverage/results.py:486`, `should_fail_under`). Avec `precision = 0`, la valeur par défaut, 95,5 %
s'arrondit à 96 et passe. Avec `precision = 2`, seul un total d'au moins 95,995 % passe. Effet de bord :
le résumé de `pytest-cov` compare, lui, le total brut. Dans cette bande de 0,005 point, il affiche donc
« FAIL » sur un job qui passe.

### Le job `tests` mesure en lançant la suite

```yaml
      - run: uv run pytest --cov --cov-report=term-missing:skip-covered
```
(`.github/workflows/ci.yml:34`)

Ce sont les mêmes tests que `make test-cov`, sans son rapport markdown. `skip-covered` n'affiche que les
fichiers sous 100 %, avec leurs lignes et branches manquées (`118->exit` : la branche de la ligne 118 vers la
sortie de la fonction n'est jamais prise). Le job garde son nom, `tests`, qui est déjà un contrôle exigé du
ruleset de `main`.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| 96 % | ta décision : un plancher, 2,4 points sous la mesure, au-dessus du plus haut niveau que Google propose (90 %) | 90 % : 8 points de régression passeraient sans signal ; 98 % : une PR ajoutant un peu de code non couvert échouerait sans régression réelle |
| Le seuil dans `pyproject.toml` | un seul endroit, partagé par `make test-cov` et la CI | `--cov-fail-under=96` dans `ci.yml` : un second endroit à tenir |
| `precision = 2` | l'arrondi n'avale plus que 0,005 point au lieu de 0,5 | `precision = 0` (défaut) |
| Dans le job `tests` | la suite ne tourne qu'une fois (30 s → 41 s en local, job de CI 75 s → 112 s) | un job `coverage` à part : la suite deux fois, et un sixième contrôle à exiger |

Choix imposé par une consigne : `pyproject.toml` ne change qu'avec ton accord explicite, donné le 08/11 avec
le plan.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `fail_under = 99` : `ERROR: Coverage failure: total of 98.41 is less than fail-under=99.00`, code 1 | le seuil fait échouer la suite (test rouge, avant le vrai seuil) |
| `fail_under = 96` : `Required test coverage of 96.0% reached. Total coverage: 98.41%`, code 0 ; `make test-cov`, code 0 | le vrai seuil passe, en local, par les deux commandes |
| `pytest tests/etl --cov` : code 1 (57,00 %) ; avec `--cov-fail-under=0` : code 0 | une mesure partielle échoue, d'où la ligne du README |
| CI de la PR, job `tests` (run 42469593428) : `Required test coverage of 96.0% reached. Total coverage: 98.41%`, job en 112 s (75 s avant) | le seuil tient sur le runner Linux, avec la même mesure que le Mac |

## Ce que tu dois pouvoir défendre

1. **Pourquoi 96 % et pas 100 % ?** Un fort taux ne garantit pas la qualité des tests, et le billet de Google
   déconseille de courir après le chiffre au-delà de 90 % (sources dans l'ADR). 96 % sert à détecter une
   régression, pas à fixer un objectif.
2. **Où vit le seuil ?** Dans `pyproject.toml:83`, et nulle part ailleurs. `pytest-cov` le lit pour toute
   commande `--cov`.
3. **Que se passe-t-il si une PR fait baisser la couverture sous 96 % ?** Le job `tests` échoue. C'est un
   contrôle exigé de `main`, donc la PR ne peut pas être fusionnée.
4. **Que mesure ce chiffre exactement ?** Les lignes et les branches de `src/k_b/`, sur la suite SQLite. Les
   tests `e2e` et `postgresql` n'y entrent pas : `database/postgresql.py` reste à 73,79 %, parce que ses
   chemins ne tournent que sur PostgreSQL.

## Zones non vérifiées

- Le message « FAIL » dans la bande de 0,005 point vient de la lecture du code de `pytest-cov`
  (`plugin.py:413`), pas d'un essai.

## Ce qui reste

- Combiner les mesures des jobs `tests` et `tests-postgresql` (`coverage combine`) relèverait le chiffre et
  compterait les chemins de PostgreSQL. Ce n'est pas fait ici : la proposition est chez toi, sans issue
  (« Left out of the plan » de la PR).
- #470 : la connexion SQLite laissée ouverte par le test du 403 de `kb smoke-test`, vue en mesurant.
