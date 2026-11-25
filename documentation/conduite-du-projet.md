# La conduite du projet K-B

!!! note "Compétences de la certification"

    > Les outils de pilotage (tableau kanban, <span lang="en">burndown chart</span>, <span lang="en">backlog</span>,
    > etc.) sont disponibles dans les conditions prévues par la méthode appliquée.

    — C16

    > Les objectifs et les modalités des rituels sont partagés à toutes les parties prenantes et rappeler si besoin.

    — C16

Cette fiche dit avec quels outils K-B est piloté, et quels rituels rythment son travail: l'objectif de chacun, ses
modalités et sa trace. Ses chiffres sont relevés le 2026-11-21 à 20:31 UTC, par `gh` en lecture et dans les fichiers
de `main` au commit `36c1e02d`; chaque relevé donne sa commande, qui se rejoue.

## Les outils de pilotage

Le pilotage tient sur GitHub: les issues, leurs labels et leurs tailles, le tableau du projet, les jalons, les
demandes de fusion et l'intégration continue. Le tableau du projet est privé, comme le dépôt:

```sh
gh repo view SabineLaurent/K-B --json visibility             # {"visibility":"PRIVATE"}
gh project view 12 --owner SabineLaurent --format json \
    --jq '{title, public}'                                    # {"public":false,"title":"K-B by LS"}
```

### Les issues

Un changement part le plus souvent d'une issue. Le corps d'une issue se range sous des intitulés en gras, d'ordinaire
« Pourquoi » et « Critère de fin », et selon le besoin « Dépend de », « Hors périmètre » et « Taille », ou, jusqu'au
2026-10-20, « Estimation ». Trois familles de labels classent les issues: leur taille (`size:XS` à `size:XL`), leur
partie (`etl`, `base`, `api-données`, `api-ia`, `coffre`, `wiki`, `cli`, `interface`, et les parties transverses
`observabilité`, `données-perso`, `outillage`, `déploiement`) et le livrable de la certification qu'elles servent
(`E1` à `E5`, ou `hors E1`, `hors E3`, `hors E4` quand l'issue touche un livrable sans qu'il l'exige); s'y ajoutent
les labels `documentation` et `accessibility`. Le 2026-11-21, le dépôt compte 367 issues, 230 fermées et
137 ouvertes:

```sh
gh issue list --repo SabineLaurent/K-B --state all --limit 1000 --json state \
    --jq '[length, (map(select(.state == "CLOSED")) | length), (map(select(.state == "OPEN")) | length)]'
# [367,230,137]
```

### Les tailles

La taille d'une issue est une estimation, de XS à XL, portée par son label `size:*` et par le champ
<span lang="en">Size</span> du tableau du projet. Le 2026-11-21, les labels se répartissent ainsi: 96 XS, 164 S,
69 M et 16 L.

```sh
gh issue list --repo SabineLaurent/K-B --state all --limit 1000 --json labels \
    --jq '[.[].labels[].name | select(startswith("size:"))] | group_by(.) | map({(.[0]): length}) | add'
# {"size:L":16,"size:M":69,"size:S":164,"size:XS":96}
```

### Le tableau du projet

Le tableau du projet, « <span lang="en">K-B by LS</span> » (GitHub Project n° 12), est le tableau kanban de K-B: ses
cartes sont des issues, rangées dans cinq colonnes, les valeurs du champ <span lang="en">Status</span>. Chaque
colonne, ce qu'elle contient et son nombre de cartes le 2026-11-21:

| Colonne | Ce qu'elle contient | Cartes |
|---|---|---|
| <span lang="en">Backlog</span> | les issues à faire | 113 |
| <span lang="en">Ready</span> | les issues prêtes à commencer | 0 |
| <span lang="en">In progress</span> | les issues commencées | 8 |
| <span lang="en">In review</span> | les issues en relecture | 3 |
| <span lang="en">Done</span> | les cartes des issues fermées: une carte y passe à la fermeture de son issue, par l'automatisme « <span lang="en">Item closed</span> » du tableau du projet | 221 |

```sh
gh project item-list 12 --owner SabineLaurent --format json -L 1000 \
    --jq '[.items[].status] | group_by(.) | map({(.[0]): length}) | add'
# {"Backlog":113,"Done":221,"In progress":8,"In review":3}
gh api graphql -f query='query{user(login:"SabineLaurent"){projectV2(number:12){workflows(first:20){nodes{name enabled}}}}}' \
    --jq '.data.user.projectV2.workflows.nodes[] | select(.name == "Item closed")'
# {"enabled":true,"name":"Item closed"}
```

Le tableau du projet porte aussi les champs <span lang="en">Priority</span> (P0 à P2), <span lang="en">Size</span>
(XS à XL), <span lang="en">Iteration</span> et <span lang="en">Estimate</span>, un nombre. Il a 19 vues:

- « Itération en cours » et « Itération suivante », en colonnes;
- « <span lang="en">Prioritized backlog</span> », en colonnes, et « <span lang="en">Roadmap</span> », une frise dans
    le temps;
- « <span lang="en">In review</span> », en table;
- quatorze tables filtrées, par livrable ou par partie.

```sh
gh project field-list 12 --owner SabineLaurent --format json --jq '[.fields[].name]'
# ["Title","Assignees","Status","Labels","Linked pull requests","Milestone","Repository","Reviewers","Parent issue",
#  "Sub-issues progress","Created","Updated","Closed","Priority","Size","Estimate","Iteration"]
gh project field-list 12 --owner SabineLaurent --format json \
    --jq '.fields[] | select(.options) | "\(.name): \([.options[].name] | join(" "))"'
# Status: Backlog Ready In progress In review Done
# Priority: P0 P1 P2
# Size: XS S M L XL
gh api graphql -f query='query{user(login:"SabineLaurent"){projectV2(number:12){views(first:50){totalCount nodes{name layout}}}}}'
```

### Les itérations

Le champ <span lang="en">Iteration</span> porte des itérations datées: « <span lang="en">Sprint 1</span> » à
« <span lang="en">Sprint 4</span> », d'une semaine chacune, à partir du 2026-09-21; « <span lang="en">Sprint 5</span> »,
de deux semaines, à partir du 2026-10-19; puis une itération par semaine, de « Semaine du 02/11 » à
« Semaine du 30/11 ».

```sh
gh api graphql -f query='query{user(login:"SabineLaurent"){projectV2(number:12){field(name:"Iteration"){... on ProjectV2IterationField{configuration{completedIterations{title startDate duration} iterations{title startDate duration}}}}}}}'
```

### Les jalons

Un jalon regroupe les issues d'une échéance, et son avancement se suit par ses issues fermées et ouvertes. Les neuf
jalons le 2026-11-21, par échéance, sous le titre exact que la commande rend:

| Jalon | Échéance | État | Issues fermées | Issues ouvertes |
|---|---|---|---|---|
| `Wiki : ingest des clips` | sans échéance | ouvert | 0 | 1 |
| `Fusion et base` | 2026-10-07 | fermé | 13 | 0 |
| `Cadrage et socle` | 2026-10-11 | fermé | 8 | 0 |
| `API « quoi de neuf »` | 2026-10-12 | fermé | 5 | 0 |
| `Collecte multi-sources` | 2026-10-18 | fermé | 33 | 0 |
| `POC 25/10` | 2026-10-25 | ouvert | 54 | 8 |
| `Oral blanc E1 E3 29/10` | 2026-10-29 | ouvert | 6 | 2 |
| `Fiches de veille tous les 3 jours` | 2026-11-01 | ouvert | 0 | 2 |
| `Mise en ligne 08/11` | 2026-11-08 | ouvert | 8 | 7 |

```sh
gh api 'repos/SabineLaurent/K-B/milestones?state=all' \
    --jq 'sort_by(.due_on) | .[] | [.title, .state, (.due_on // "-")[:10], .closed_issues, .open_issues] | @tsv'
```

### Les demandes de fusion

Un changement passe par une branche, puis une demande de fusion (PR, <span lang="en">pull request</span>) vers
`main`, ce que le ruleset de `main` exige depuis sa création; une PR qui livre une issue la ferme par
`Closes #n`. Le 2026-11-21, 299 PR sont fusionnées. Le ruleset
« <span lang="en">Basic-rules-main-protect</span> » de `main` interdit la suppression de la branche et le push forcé,
exige une PR, et ne fusionne que par commit de fusion.

```sh
gh pr list --repo SabineLaurent/K-B --state merged --limit 1000 --json number --jq length    # 299
gh api repos/SabineLaurent/K-B/rulesets/25257125 --jq '{name, created_at}'
# {"created_at":"2026-10-16T19:24:02.035+02:00","name":"Basic-rules-main-protect"}
gh api repos/SabineLaurent/K-B/rules/branches/main --jq '.[].type'
# deletion
# non_fast_forward
# pull_request
# required_status_checks
```

### L'intégration continue

Chaque PR vers `main`, et chaque push sur `main`, lance l'intégration continue (CI): les jobs `audit`, `tests`,
`lint`, `types`, `tests-postgresql`, `tests-data` et `digests-reference` (`.github/workflows/ci.yml`), `image-build`
(`.github/workflows/image.yml`) et `bicep-build` (`.github/workflows/infra.yml`). Chaque PR construit aussi le site de
ces fiches (`build`, `.github/workflows/docs.yml`). Une PR ne fusionne que si six contrôles sont verts, sur une
branche à jour avec `main`: `audit`, `tests`, `lint`, `types`, `tests-postgresql` et `bicep-build`. Le détail est dans
[la fiche de l'intégration continue](integration-continue.md).

```sh
gh api repos/SabineLaurent/K-B/rules/branches/main \
    --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context'
```

## Les rituels

Chaque rituel, son objectif, ses modalités et sa trace sur GitHub:

| Rituel | Objectif | Modalités | Trace |
|---|---|---|---|
| La conception dans l'issue | décider ce qui se fait et ce qui ne se fait pas, avant le code | pour un changement de code, une conception courte dans l'issue: ce qui se fait, ce qui ne se fait pas, les options et le choix; validée avant le code | l'issue, son corps et ses commentaires |
| Le cycle d'une PR | livrer un changement vérifié | une branche depuis `main`; pour du code, les tests d'abord et une relecture du diff, son compte rendu dans la PR, en commentaire ou dans sa description; les contrôles du dépôt en local; la PR vers `main`; la CI verte; la fusion | la PR: son corps, ses commentaires, ses contrôles |
| La note de journal | garder ce qu'une PR a fait, pourquoi et comment | une note écrite dans la PR qu'elle explique, versionnée avec elle | `docs/journaling/`, 200 notes le 2026-11-21 |
| Le journal des décisions d'architecture (ADR, <span lang="en">Architecture Decision Record</span>) | garder chaque décision qui engage la suite du projet, son pourquoi et les options écartées | les décisions d'un jour réunies sous sa date, chacune avec son pourquoi | `docs/ADR/journal-decisions-projet.md`, 46 journées de décisions le 2026-11-21 |
| Le point d'arrêt | reprendre un travail interrompu sans rien perdre | quand un travail s'interrompt avant sa PR, un commentaire sur l'issue: la branche, ce qui est fait, l'état des tests, l'étape suivante, la question en attente | les commentaires « point d'arrêt » des issues |
| Le jalon | regrouper les issues d'une échéance et en suivre l'avancement | un jalon, le plus souvent daté; son avancement se lit par ses issues fermées et ouvertes | la [page des jalons du dépôt](https://github.com/SabineLaurent/K-B/milestones) |

```sh
git ls-tree --name-only 36c1e02d docs/journaling/ | wc -l                           # 200
git show 36c1e02d:docs/ADR/journal-decisions-projet.md | grep -cE "^## [0-9]{4}-"    # 46
gh search issues --repo SabineLaurent/K-B "point d'arrêt" --limit 300 --json number --jq length    # 25
```

Le pilotage et les rituels sont partagés par leurs traces sur GitHub: les issues, les PR, le tableau du projet, la
CI, les notes de journal et le journal des décisions, lisibles par toute personne qui a accès au dépôt et au
tableau du projet.
