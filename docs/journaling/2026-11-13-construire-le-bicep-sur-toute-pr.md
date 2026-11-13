# Construire le Bicep sur toute PR, pour en faire un contrôle exigé de `main`

- **Date** : 2026-11-13
- **Branche** : `ci/bicep-build-every-pr`, commits `5b9e194` et `ad71d6b`, sur `main` à `0cf26ba`
- **Issue** : #496
- **Série** : suite de [Écrire la fiche de l'intégration continue](2026-11-10-ecrire-la-fiche-de-l-integration-continue.md),
  qui proposait déjà de rendre `bicep-build` exigé ; la mesure d'API8 vient de l'auto-évaluation OWASP de l'API IA
  (#454, #500).
- **Fichiers principaux** : `.github/workflows/infra.yml`, `docs/fiches-veille.md` (API8), la doc de la CI
  (`README.md`, `infra/README.md`, `documentation/integration_continue_pour_docu.md`,
  `documentation/livraison_continue_pour_docu.md`), `docs/ADR/journal-decisions-projet.md`.

La liste des commits donnée à la note compte aussi ceux de `main` entre `eef28b2` et `0cf26ba` (#606, #602, #605) :
ils sont entrés par d'autres PR, qui ont leur note. Cette note ne couvre que `5b9e194` et `ad71d6b`.

## Le pourquoi

L'infrastructure de K-B sur Azure est décrite en Bicep, dans `infra/`. Le job `bicep-build` la compile, sans aucun
droit sur Azure : une erreur de Bicep se voit dans la PR, pas au moment où Sabine applique la passe. Mais ce job ne
tournait que sur une PR qui touchait `infra/`, et il n'était pas exigé par le ruleset de `main` : une PR pouvait
fusionner sans que le Bicep se compile. L'auto-évaluation OWASP de l'API IA le comptait comme une limite de la mesure
« durcissement répétable » d'API8 (Security Misconfiguration). Sabine a décidé le 08/11 de tenir cette partie de la
mesure, et de justifier le reste.

Ce travail fait deux choses : il fait tourner `bicep-build` sur toute PR, pour qu'il puisse être exigé ; il écrit les
trois écarts qui restent dans la mesure, chacun avec sa limite.

## Le comment

### 1. Un contrôle exigé ne doit jamais être sauté par un filtre

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

`.github/workflows/infra.yml:3-7`. Avant, chaque déclencheur portait
`paths: ["infra/**", ".github/workflows/infra.yml"]`. GitHub ne lance alors pas le workflow sur une PR qui ne touche
aucun de ces chemins. Ce n'est pas un échec, mais pour un contrôle exigé, c'est un blocage : pour « A workflow is
skipped by path filtering, branch filtering, or a commit message », la doc de GitHub dit « Associated checks stay in
a "Pending" state and block merging », et conseille « Avoid requiring workflows that can be skipped »
([Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
github.com, lu le 2026-11-13). Le ruleset attend un résultat qui ne vient jamais, et la PR ne fusionne pas. D'où le commentaire de l'ancienne version :
« Not a required check: with its path filter, it would block every pull request that leaves infra/ alone ». Pour
exiger le contrôle, il fallait donc le faire tourner partout. Le commentaire dit maintenant pourquoi
(`infra.yml:12-14`).

### 2. Ce que le job fait, et pourquoi il est sûr de le lancer sur toute PR

```yaml
      - run: az bicep install --version v0.48.1
      # SHA256 of bicep-linux-x64 v0.48.1 (GitHub release asset digest): update it with the version.
      - run: echo "b09ec25a9d376c1f8e33ede6ed22b587f915ad68488d5db77a6f9541748c7f6e  $HOME/.azure/bin/bicep" | sha256sum -c
      - run: az bicep version
```

`infra.yml:22-25`, inchangé. Bicep est épinglé à une version, et le binaire téléchargé est comparé à son empreinte
avant sa première exécution (`az bicep version`). Le workflow n'a que `permissions: contents: read`
(`infra.yml:9-10`), ne lit aucun secret, et se déclenche par `pull_request`, pas par `pull_request_target` : une PR
d'un fork tourne avec un jeton en lecture seule, sans secret. Aucune commande ne reprend un texte de la PR (titre,
branche). La revue de sécurité du 13/11 n'a rien trouvé : le lancer sur plus d'événements n'ouvre aucun chemin
d'attaque.

### 3. L'effet sur le déploiement

```bash
          runs=$(gh api "repos/$GITHUB_REPOSITORY/actions/runs?head_sha=$SHA&per_page=100" \
            --jq '[.workflow_runs[] | select(.path | startswith(".github/workflows/"))
              | select(.path != ".github/workflows/deploy.yml") | {path, status, conclusion}]')
```

`.github/workflows/deploy.yml:60-62`, inchangé. Avant de mettre un tag en ligne, `deploy.yml` exige que chaque
exécution d'un workflow sur le commit du tag soit finie et verte. Il ne liste pas les workflows : il prend ceux qui ont
tourné. Avant #496, un commit de `main` qui ne touchait pas `infra/` n'avait pas d'exécution `Infra`, et rien ne
l'attendait. Désormais, chaque fusion lance `Infra`, et un Bicep cassé sur `main` bloque aussi le déploiement : la
barrière devient plus stricte, sans une ligne de `deploy.yml` changée.

### 4. Le ruleset, changé juste avant la fusion

Le dépôt ne change pas le ruleset : c'est un réglage de GitHub, que Sabine pose à la main (Settings → Rules →
Rulesets → `Basic-rules-main-protect`), puis qu'elle relit :

```sh
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context'
```

Le 13/11, avant le geste, la commande rendait `audit`, `tests`, `lint`, `types`, `tests-postgresql`. Le moment
compte. Posé avant la fusion de #496, le contrôle bloquerait toutes les PR ouvertes qui ne touchent pas `infra/` :
elles tournent encore avec l'ancien `infra.yml`, filtré, et `bicep-build` n'y viendrait jamais. Posé juste avant la
fusion, il ne gêne que pour quelques minutes, car le ruleset est `strict` : après la fusion de #496, chaque PR
ouverte doit de toute façon se mettre à jour sur `main`, et son run `pull_request` prend alors l'`infra.yml` sans
filtre.

### 5. Les trois écarts voulus du « durcissement répétable »

`docs/fiches-veille.md:1305-1328`. La mesure demande « A repeatable hardening process leading to fast and easy
deployment of a properly locked down environment ». Trois limites restent, et ne seront pas levées :
- **le socle appliqué à la main** (`:1305`) : appliquer le Bicep crée des rôles, ce qui demande le droit d'Owner
  sur le groupe ; donner ce droit à la CI irait contre le moindre privilège. La passe reste répétable : même Bicep,
  mêmes commandes, aperçu (`what-if`) avant la création ;
- **l'image changée hors du Bicep par `deploy.yml`** (`:1315`) : seule l'image change, tenue par son digest, vérifié
  contre le commit du tag ;
- **aucune relecture exigée** (`:1322`) : une seule personne au dépôt, et GitHub dit « Pull request authors cannot
  approve their own pull requests » ; exiger une approbation bloquerait toute PR de Sabine.

Chacun a sa « Limite » (ce qui le rendrait à lever : la grille le définit ainsi, `docs/fiches-veille.md:948-950`),
son « Pour lever l'écart » et son « Pour réduire le risque », dit faisable ou non avec nos droits.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Comment faire tourner `bicep-build` partout | Retirer `paths` des deux déclencheurs | Un job préalable qui calcule si `infra/` a changé, et `bicep-build` sous `if:` : plus de code, et un job sauté par une condition « reports "Success" » (même page de GitHub), ce qu'il aurait fallu rattraper par `always()` et un test de `needs.<id>.result`. L'action `dorny/paths-filter` : une dépendance de plus dans la CI. |
| Coût | 18 à 54 s de runner par PR (les dernières exécutions, le 11/11) | — |
| Moment du ruleset | Juste avant la fusion | Avant : bloque les PR des autres pistes. Après : `main` reçoit des pages qui disent le contrôle exigé alors qu'il ne l'est pas encore. |
| État de la mesure dans cette PR | « Non tenue, en partie » | « Tenue » tout de suite : la mission interdit d'écrire une mesure tenue d'avance, et le constat d'une PR hors d'`infra/` n'existe qu'après la fusion. |
| `concurrency` et `cancel-in-progress` dans `infra.yml` | Non | Proposé par la revue de code ; `ci.yml` et `image.yml` n'en ont pas non plus, hors du périmètre (tri de time-knight). |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code : `grep -n "paths" .github/workflows/infra.yml` → lignes 6 et 9 | le critère rouge de l'issue |
| Après : la même commande ne rend rien | le filtre a disparu (premier critère de #496) |
| Avant le geste : la lecture du ruleset ne nomme pas `bicep-build` | le second critère, rouge |
| `uv run pytest` : 5119 passés ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | rien d'autre n'a bougé |
| `/security-review` : aucune faille | lancer le workflow partout est sûr |
| `/code-review` (high) : 8 constats de doc, triés par time-knight ; 2 corrigés dans `ad71d6b`, 2 au commit de la lecture du ruleset | la doc dit ce qui est observé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas garder le filtre et exiger quand même le contrôle ?** Un workflow sauté par son filtre laisse
   son contrôle « Pending » : une PR qui ne touche pas `infra/` ne fusionnerait jamais (section 1).
2. **Pourquoi ne pas sauter la construction par un `if:`, pour économiser le runner ?** Un job sauté par une
   condition rend « Success » : il faudrait encore vérifier que le job préalable a réussi. Plus de code pour gagner
   moins d'une minute par PR.
3. **Lancer un workflow sur toutes les PR, même celles des forks, n'est-il pas dangereux ?** Non ici : `pull_request`
   et non `pull_request_target`, jeton en lecture seule, aucun secret, aucune entrée de la PR dans une commande, Bicep
   vérifié par son SHA256 (`infra.yml:9-10`, `:24`).
4. **Pourquoi la CI n'applique-t-elle pas le Bicep elle-même ?** Il faudrait lui donner le droit de créer des rôles
   (Owner) : le moindre privilège l'emporte, c'est un écart voulu, écrit avec sa limite (`fiches-veille.md:1305`).
5. **Que change ce travail pour une mise en ligne ?** `deploy.yml` attend désormais aussi `Infra` sur le commit du
   tag (section 3).

## Zones non vérifiées

- Que `bicep-build` tourne et soit vert sur une PR qui ne touche pas `infra/` : constaté seulement après la fusion.

## Ce qui reste

- Le geste de Sabine sur le ruleset, juste avant la fusion, et sa lecture citée dans la PR.
- Le constat d'une PR qui ne touche pas `infra/` et reçoit `bicep-build`, vert : la PR de #611 (API10). La PR de #498,
  qui touche ensuite API8, l'écrit et passe la mesure à « tenue ».
- Faire échouer `bicep-build` sur un avertissement de Bicep : #452.
