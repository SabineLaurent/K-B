# Lancer la CI sur main après chaque fusion, en jobs nommés

- **Date** : 2026-10-17
- **Branche** : `ci/named-jobs-on-main`
- **Issue** : #233
- **Fichiers principaux** : `.github/workflows/ci.yml`, `README.md`, `.claude/rules/conformite.md`

## Le pourquoi

Jusqu'ici, la CI ne tournait que sur une PR (`pull_request`), en un seul job `test`. Deux manques :

- **Après une fusion, rien ne prouvait que `main` restait vert.** Le commit de fusion est un commit
  nouveau, qui n'a jamais été testé tel quel : la PR testait sa branche, pas le résultat de la fusion.
- **L'onglet Actions ne disait pas ce qui avait échoué.** Un job unique enchaînait l'audit, les tests,
  le lint et le typage. Une croix rouge sur `test` obligeait à ouvrir le journal pour savoir laquelle
  des étapes avait cassé.

Sabine l'a décidé le 16/10 : « ok pour ajouter le push sur main », et des jobs séparés, « plus
explicite à la lecture de l'action ». La PR recopie aussi la version du 16/10 des règles de
conformité, tenue par time-knight, dans un commit à part.

## Le comment

### Deux déclencheurs

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
(`.github/workflows/ci.yml:3-7`)

- `pull_request` vers `main` : le workflow tourne à l'ouverture d'une PR et à chaque push sur sa
  branche, comme avant.
- `push` vers `main` : il tourne aussi sur chaque commit qui arrive sur `main`. La protection de `main`
  interdit le push direct, donc ce commit est toujours un commit de fusion.
- Le filtre `branches: [main]` sur `push` évite un double run : un push sur la branche de la PR ne
  déclenche que `pull_request`, pas `push`.
- GitHub lit le workflow **du commit poussé**. La PR qui ajoute `push:` déclenche donc déjà un run sur
  `main` à sa propre fusion.

### Un jeton en lecture seule

```yaml
permissions:
  contents: read
```
(`.github/workflows/ci.yml:9-10`)

- **Le problème.** GitHub donne à chaque run un jeton, `GITHUB_TOKEN`, qui agit sur le dépôt.
  Aujourd'hui, ses droits viennent seulement d'un réglage du dépôt, dans l'interface (« read »). Il
  suffirait de passer ce réglage en « read and write » pour que chaque run sur `main` reçoive un jeton
  en écriture. Ce jeton serait alors à portée de tout le code qui s'exécute dans les jobs, celui des
  actions et celui des dépendances installées par `uv sync` compris.
- **Ce que fait le bloc.** Écrit en tête du workflow, il fixe les droits dans le code. Le jeton peut
  lire le contenu du dépôt, et rien d'autre : tout droit non nommé est retiré.
- **Pourquoi l'avoir ajouté.** C'est le moindre privilège et la défense en profondeur de `code.md` :
  deux contrôles plutôt qu'un réglage seul.
- **Le critère est tenu.** Ce n'est pas une commande, donc « mêmes commandes qu'avant » reste vrai.
- **D'où vient la décision.** Constat 2 de la revue, décision de Sabine du 16/10, qui revient sur le
  premier plan.

### Quatre jobs nommés

```yaml
jobs:
  audit:
  ...
  tests:
  ...
  lint:
  ...
  types:
```
(`.github/workflows/ci.yml:13`, `:23`, `:31`, `:40`)

- **Chaque job tourne sur sa propre machine, en parallèle.** L'onglet Actions affiche un statut par
  job.
- **Aucun job n'a de clé `name:`.** Le check publié porte alors l'identifiant du job (`audit`,
  `tests`…). C'est ce nom que le ruleset de `main` exige.
- **Constaté sur la PR #232 :** `gh pr checks 232` donne `test`, le même texte que le contexte du
  ruleset. L'affichage « CI / audit (pull_request) » n'est qu'un libellé de l'interface.

### Chaque job installe ce qu'il lui faut

```yaml
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.2.0
      - run: uv sync --locked
      - run: uv run mypy --strict
```
(`.github/workflows/ci.yml:42-46`)

- **Les jobs ne partagent rien.** Chaque machine part vide : il faut donc récupérer le code
  (`checkout`), installer uv, puis l'environnement.
- **`--locked`** fait échouer le sync si `uv.lock` n'est plus à jour par rapport au `pyproject.toml`.
  C'est déjà un contrôle en soi.
- **`audit` le fait aussi.** Le critère de l'issue le demande. Le coût est de 1,2 s, mesuré sur le run
  38972965922 par la relecture du plan.

### Mêmes commandes qu'avant

- Le critère interdit d'ajouter ou de retirer une commande : la PR ne fait que répartir l'existant. La
  commande de contrôle compare les lignes `run:` distinctes avant et après :
  `diff <(git show main:.github/workflows/ci.yml | grep -oE "run: .*" | sort -u) <(grep -oE "run: .*" .github/workflows/ci.yml | sort -u)`.
  Elle ne renvoie rien.
- Seule différence : `uv sync --locked` apparaît quatre fois au lieu d'une, une fois par job.

### La protection de `main` doit suivre

Le ruleset « Basic-rules-main-protect » exige le statut `test`. Après cette PR, plus aucun job ne
publie `test`. Le ruleset n'a aucun contournement (`bypass_actors` vide) : si `test` reste exigé, la PR
est bloquée pour tout le monde.

L'ordre est donc :

1. les quatre jobs sont verts sur la PR ;
2. Sabine retire `test` du ruleset et ajoute `audit`, `tests`, `lint` et `types`, avec la source
   GitHub Actions ;
3. Sabine fusionne.

Si Sabine retirait `test` sans ajouter les quatre noms, `main` n'aurait plus aucun check requis, et une
PR rouge pourrait être fusionnée.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nom des checks | Identifiant du job, sans `name:` : un seul nom, celui que le ruleset exige | `name:` lisible (« Unit tests ») : deux noms pour un job, et le ruleset devrait suivre le libellé |
| `uv sync --locked` dans `audit` | Gardé : le critère le dit ; 1,2 s ; pip-audit garde l'interpréteur Python 3.13 que le sync télécharge ; le cache de setup-uv reste cohérent entre les quatre jobs | Le retirer : écart au critère, et l'interpréteur et le cache changeraient (relecture du plan) |
| Étapes communes | Recopiées dans chaque job : trois lignes, lisibles sans indirection. Elles changent toutes pour la même raison (une version d'action), et Dependabot, prévu par #234, met à jour toutes les occurrences d'un coup | Action composite ou workflow réutilisable : un fichier de plus pour trois lignes. Ancres YAML (acceptées par GitHub Actions depuis le 18/09/2025) : sans clés de fusion, et contestées pour l'analyse de sécurité |
| Découpage | Quatre jobs explicites, `lint` regroupe `ruff check` et `ruff format --check` (le critère le dit) | Une matrice de commandes : noms de checks moins lisibles |
| `permissions:` | `contents: read` au niveau du workflow (décision de Sabine du 16/10, constat 2 de la revue) : les droits du jeton sont fixés dans le code | S'en remettre au seul réglage du dépôt (premier plan) : un réglage d'interface, qu'un changement ferait passer en écriture sans rien dans le code |
| Épinglage des actions | Tags inchangés dans cette PR ; épinglage par SHA reporté à #234 (décision de Sabine du 16/10, constat 3 de la revue) | Le faire ici : hors du critère de #233 |
| `conformite.md` | Recopié tel quel (`cp`), dans un commit à part : time-knight tient ce fichier | Le modifier à la main : interdit par la règle « Fraîcheur » du fichier |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `yaml.safe_load` du workflow : déclencheurs `push` et `pull_request` sur `main`, jobs `['audit', 'tests', 'lint', 'types']` | Le YAML se lit. C'est un contrôle de syntaxe seulement, pas du schéma GitHub Actions |
| `diff` des lignes `run:` distinctes, `main` contre la branche : rien | Aucune commande ajoutée ni retirée |
| `grep -c "uv sync --locked" .github/workflows/ci.yml` : 4 | Chaque job installe son environnement |
| `yaml.safe_load` : `permissions` vaut `{'contents': 'read'}` au niveau du workflow | Le jeton de chaque job n'a que la lecture du contenu ; que les quatre jobs passent toujours avec ce jeton, c'est le run de la PR qui le montre |
| `diff` de la copie de `conformite.md` tenue par time-knight et de `.claude/rules/conformite.md` : rien | Copie identique, octet pour octet |
| `uv run pytest` (1525 passed), `ruff check`, `ruff format --check`, `mypy --strict` en local : verts | Les quatre commandes que les jobs lancent passent sur la branche |
| Run de la PR, puis `gh run list --branch main --event push --limit 1` après la fusion | La vraie preuve du critère : quatre checks verts sur la PR, puis un run vert sur `main` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi relancer la CI sur `main` si la PR était verte ?** Le commit de fusion n'a jamais été
   testé tel quel. Deux PR vertes chacune peuvent casser une fois fusionnées l'une après l'autre (le
   ruleset n'exige pas d'être à jour avec `main`, `strict` est à false). Le run `push` le voit.
2. **Comment le ruleset sait-il quels jobs exiger ?** Par le nom du check, qui est l'identifiant du job
   faute de `name:` (`ci.yml:13`). Il faut aussi la source GitHub Actions : sinon, n'importe quelle
   autre app qui publierait un statut `tests` validerait le check.
3. **Quatre jobs, ce n'est pas quatre fois plus cher ?** Quatre machines au lieu d'une, en parallèle.
   Le temps total est plus court, les minutes un peu plus nombreuses : chaque job refait checkout,
   setup-uv et sync.
4. **Où est la sécurité ?**
   - Le jeton du workflow ne peut que lire le contenu du dépôt, fixé dans le code (`ci.yml:9-10`)
     et pas seulement par le réglage du dépôt.
   - Les actions sont encore référencées par tag. `actions/checkout@v7` est un tag mobile :
     l'épinglage par SHA, avec Dependabot, est porté par #234, avant le déploiement.
   - `pull_request`, contrairement à `pull_request_target`, donne aux PR venant d'un fork un jeton en
     lecture et pas de secrets. Ce sera utile une fois le dépôt public le 25/10.
   - L'audit pip-audit vérifie les versions et les empreintes de `uv.lock`.
5. **Pourquoi des étapes recopiées malgré le principe « factoriser à la troisième occurrence » ?** La
   revue l'a relevé. Les quatre copies changent pour la même raison, une version d'action, et
   Dependabot (#234) les met à jour toutes d'un coup. Trois lignes par job se lisent sans ouvrir un
   autre fichier.

## Zones non vérifiées

- **Le nom du check.** Le check d'un job sans `name:` porte son identifiant : c'est constaté sur la PR
  #232 (`test`). Je n'ai pas lu de page de la doc GitHub qui l'écrit en toutes lettres. Le run de cette
  PR le confirmera, par `gh pr checks`.
- **L'interpréteur de `uvx`.** Il ignore le `.python-version` du projet et reprendrait sinon le Python
  du runner : c'est ce que la relecture du plan a rapporté de la doc uv. Je ne l'ai pas lu moi-même. Ce
  point justifie le sync dans `audit`, pas le code.
- **La clé de cache.** Le cache de setup-uv (`enable-cache: auto`) a une clé commune aux quatre jobs,
  et c'est le premier job fini qui le sauve : observé dans le journal du run 38972965922 par la
  relecture du plan. Je ne l'ai pas vérifié dans la doc de setup-uv.

## Ce qui reste

Constats de la revue, tranchés par time-knight (délégation de Sabine du 15/10) :

- **Épingler les actions par SHA de commit, avec Dependabot** : porté par #234, avant le déploiement
  du 08/11.
- **Groupe `concurrency`, pour annuler les runs périmés d'une PR** : écarté. Le coût est mineur, et
  les minutes sont gratuites une fois le dépôt public.
- **pip-audit planifié (`schedule:`)** : écarté. Les alertes Dependabot sont actives, et le graphe des
  dépendances lit `uv.lock`. Une CVE publiée entre deux fusions donne donc une alerte, puis une PR, et
  la PR lance la CI.

`CLAUDE.md:28` (« fait passer les tests sur chaque PR ») reste vrai mais incomplet : signalé, pas
modifié.

## Sources

- GitHub Docs, « Triggering a workflow » (filtre `branches` sur `push`) :
  https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
  (lue par Context7 le 2026-10-16, UTC).
- GitHub Docs, « Using jobs in a workflow » (`jobs.<job_id>`, `jobs.<job_id>.name`) :
  https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs
  (lue par Context7 le 2026-10-16, UTC).
- GitHub Docs, « Control deployments » (exemple `on: push` et `pull_request` sur `main`) :
  https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments
  (lue par Context7 le 2026-10-16, UTC).
- API GitHub du dépôt, lue par `gh api` le 2026-10-16 : ruleset 25257125 (`required_status_checks`,
  `bypass_actors`), `actions/permissions/workflow`.
- GitHub Docs, « Lock workflow dependencies » (épinglage par SHA, pour #234) :
  https://docs.github.com/en/actions/how-tos/secure-your-work/lock-workflow-dependencies
  (relevée par time-knight le 2026-10-16, non relue ici).
- GitHub Changelog, « Actions: YAML anchors and non-public workflow templates », 18/09/2025 :
  https://github.blog/changelog/2025-09-18-actions-yaml-anchors-and-non-public-workflow-templates/
  (relevée par time-knight le 2026-10-16, non relue ici).
