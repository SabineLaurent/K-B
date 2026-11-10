# Écrire la fiche de l'intégration continue

- Date: 2026-11-10
- Branche: `docs/ci-sheet`
- Issue: #508
- Fichiers principaux: `documentation/integration_continue_pour_docu.md` (neuf), `README.md:776-779`
- Série: [2026-11-09-ecrire-la-fiche-de-l-installation.md](2026-11-09-ecrire-la-fiche-de-l-installation.md); la
  livraison, qui suit la CI, a sa fiche: `documentation/livraison_continue_pour_docu.md`.

La PR compte six commits, de `4b898ae` à `79f605f`. `4b898ae` écrit la fiche le 2026-11-09, d'après `0292266`.
`430c8db` la revérifie sur `89ef7fb`, après le rebase, et donne à chaque limite sa parade. `7a8a648` et `70aaadf`
appliquent les deux relectures. `accd7fc` et `79f605f` corrigent le témoin du README. Les autres commits et fichiers
que liste l'outil viennent de PR déjà fusionnées sur `main`: ils ne sont pas de cette PR.

## Le pourquoi

Le référentiel demande deux documentations de la chaîne d'intégration continue (C18): celle des procédures
d'installation et de test de la chaîne, et la documentation utilisateur de son déclenchement. Jusqu'ici, la CI de K-B
n'était décrite que dans le README, section « La CI », sans son installation (le ruleset, les réglages des Actions,
Dependabot) ni la manière de la tester ou de la dépanner. La fiche réunit tout cela dans un fichier, et chaque fait
s'y vérifie dans le code de `main` ou par une commande en lecture seule.

## Le comment

### 1. Un fait, une ligne du dépôt

La fiche ne décrit rien de mémoire: chaque job, étape, réglage ou version renvoie à la ligne qui le porte, au commit
`89ef7fb`. Exemple, le job PostgreSQL:

```
| `tests-postgresql` (l. 62-92) | `uv run pytest -m postgresql`, contre le service `postgres:18.6` du job (utilisateur `kb`, base en UTF8 et collation C, l. 71-75), joint par `KB_TEST_POSTGRESQL_URL` (l. 84), …
```
(`documentation/integration_continue_pour_docu.md:70`)

Après le rebase de `0292266` à `89ef7fb`, une seule commande a suffi à savoir si ces renvois tenaient encore:
`git diff --quiet 0292266 origin/main -- .github pyproject.toml Dockerfile .dockerignore tests/conftest.py Makefile`
ne rend aucun écart. Les fichiers cités n'ont pas bougé, donc leurs lignes non plus. Seuls les faits datés ont
changé: le commit de référence, le push témoin, la dernière exécution d'`Infra`.

### 2. Ce qui n'est pas dans le dépôt se lit par `gh api`

Le ruleset de `main`, les réglages des Actions et ceux de Dependabot vivent dans GitHub, pas dans le code. La fiche
donne la commande qui les lit, et ce qu'elle a rendu le 2026-11-10:

```sh
gh api repos/SabineLaurent/K-B/rulesets --jq '.[] | "\(.id) \(.name) \(.target) \(.enforcement)"'
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '{name, enforcement, bypass_actors, conditions, rules}'
```
(`documentation/integration_continue_pour_docu.md:169-170`)

C'est la partie « Installer la chaîne »: sur un dépôt neuf, ces réglages se recréent à la main, règle par règle. Leur
recréation n'a pas été essayée, et la fiche le dit.

### 3. Une limite, sa parade, sa source

Règle du 2026-11-10: chaque limite écrite est suivie de « Pour réduire le risque: … », vérifié à la source le jour
même, avec « faisable avec nos droits » ou non. Exemple:

```
- **Aucune relecture n'est exigée**: le ruleset demande une PR, mais aucune approbation
  (`required_approving_review_count: 0`). La relecture en PR est une pratique, pas une règle.
  Pour réduire le risque: exiger une approbation dans le ruleset serait faisable avec nos droits (administratrice du
  dépôt), mais « Pull request authors cannot approve their own pull requests »: […]
```
(`documentation/integration_continue_pour_docu.md:268-271`)

Les six parades viennent de GitHub Docs (lues par Context7 et WebFetch) et du dépôt `anchore/scan-action` (lu par
`gh api`). Elles sont listées sous « Sources », à la fin de la section. Ce sont des propositions: aucune n'est
appliquée par cette PR.

### 4. Le témoin du README

Le README citait #475 et « les 6 checks que reçoit une PR qui ne touche pas `infra/` ». C'était vrai le 2026-11-08 à
10:59 UTC, quand #475 a été fusionnée. #492 (issue #481) a ajouté le job `tests-data` à 14:39 UTC le même jour: une
telle PR reçoit maintenant 7 checks. Le témoin devient #533:

```
**Une PR témoin** : [#533](https://github.com/SabineLaurent/K-B/pull/533) a passé, avant sa fusion le
2026-11-09, les 7 checks que reçoit une PR qui ne touche ni `infra/` ni `.github/workflows/infra.yml` : […]
```
(`README.md:776-777`)

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Le README dans cette PR | oui, `README.md:776-779` seulement (décision de Sabine du 2026-11-10, transmise par time-knight; plan et critère de #508 amendés) | une PR à part, que recommandait la session: Sabine a préféré une seule PR sur la CI |
| Le témoin | #533, ses 7 checks lus par `gh pr checks 533` | garder #475: ses 6 checks ne sont plus ce que reçoit une PR |
| L'absence de `concurrency` | une description, pas une limite (time-knight, 2026-11-10) | en faire une limite avec sa parade: deux exécutions finissent toutes deux, sans risque pour la fusion |
| Les équivalents locaux d'`image-build` | la construction et `--help`; le reste « ne tourne que sur le runner » | une recette pas à pas: elle planterait un `.env` et deux `.sqlite` que git n'ignore pas dans la copie de travail |
| Le scanner d'image proposé | Grype (`anchore/scan-action`), dont l'`action.yml` a été lu | Trivy: sa release a été lue, mais pas sa page ni ses réglages; un seul exemple suffit |
| Le fichier de `audit` en local | `"${TMPDIR:-/tmp}/requirements-audit.txt"` | à la racine du dépôt, comme en CI: git ne l'ignore pas, il pourrait être commité |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `git diff --quiet 0292266 origin/main -- .github pyproject.toml Dockerfile .dockerignore tests/conftest.py Makefile` → 0 | les renvois `fichier:ligne` écrits le 2026-11-09 tiennent sur `89ef7fb` |
| `gh api repos/SabineLaurent/K-B/rulesets/25257125` → 5 contrôles requis, `strict_required_status_checks_policy: true`, `bypass_actors: []` | la section « Installer » décrit le ruleset tel qu'il est |
| `gh pr checks 533` → 7 checks `pass` | le témoin de la fiche et du README |
| `gh run list --commit 89ef7fb…` → `CI` 42815479408 et `Image` 42815479369, `success` | le push témoin |
| Première relecture (sous-agent neuf): 14 constats certains, 4 plausibles; seconde, sur le delta: 6 et 2 | tous corrigés, sauf le quatrième plausible de la première, réécrit et laissé non vérifié (tri de time-knight) |
| Contrôles: 0 caractère `Cc`/`Cf`, 0 espace avant « : » ou « ; », aucune ligne de plus de 120 caractères hors tableaux et liens | la fiche suit les règles d'écriture de `documentation/` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi trois contrôles ne bloquent-ils pas la fusion?** `tests-data`, `image-build` et `bicep-build` ne sont
   pas dans le ruleset. `bicep-build` ne tourne que si `infra/` change: exigé, il laisserait « Pending » toute autre PR.
   Ils comptent tout de même à la livraison: `Deploy` refuse un commit dont une exécution n'est pas verte
   (`deploy.yml:51-67`).
2. **Pourquoi pas une approbation obligatoire?** L'autrice d'une PR ne peut pas approuver la sienne, et le ruleset n'a
   aucun contournement: avec une seule personne, plus rien ne fusionnerait (« Limites », première entrée).
3. **La CI peut-elle déployer, ou lire un secret?** Non: chaque workflow de la CI n'a que `contents: read`
   (`ci.yml:9-10`, `image.yml:9-10`, `infra.yml:11-12`), et aucun ne lit de secret ni de variable.
4. **Que se passe-t-il si `uv.lock` a une vulnérabilité connue?** `audit` échoue, et la PR ne fusionne pas. Le refus
   témoin, l'exécution 41215069368, montre `pyasn1 0.6.4` refusé, avec la version corrigée.
5. **Pourquoi les tests de bout en bout ne sont-ils pas en CI?** Ils appellent les vraies sources, dont une requête
   BigQuery réelle, et deux d'entre eux lisent des fichiers du poste. Un workflow planifié est possible, à ce prix
   (« Limites », troisième entrée).

## Zones non vérifiées

- Aucune commande de « Tester la chaîne » n'a été lancée sur le poste (pytest, pip-audit, docker, az).
- La recréation des réglages sur un dépôt neuf n'a pas été essayée.
- « Dependabot ne met pas à jour l'image du service `postgres` »: seul le commentaire de `ci.yml:63-64` le dit; la
  documentation de Dependabot n'a pas été lue sur ce point.
- Aucune PR de sécurité de Dependabot n'existe encore: le déclencheur est décrit d'après les réglages, sans exemple.
- Les parades ne sont pas essayées, en particulier la condition de job qui remplacerait le filtre de `bicep-build`.
- « Ce journal se relit jusque vers le 2027-01-29 » suppose que la durée de garde reste à 90 jours.

## Ce qui reste

- Les parades sont des propositions: chacune qui serait retenue demande une issue, sur décision de Sabine.
- #482 modifiera `ci.yml`: la fiche se relit après sa fusion.
- Quand le dépôt deviendra public, les phrases sur les minutes d'un dépôt privé (« Limites ») seront à reprendre.
