# Consigner les décisions de cadrage du 20/10

- **Date** : 2026-10-20
- **Branche** : `docs/adr-framing-2026-10-20`
- **Issue** : #275
- **Fichiers principaux** : `docs/ADR/journal-decisions-projet.md`, `MEMORY.md`, `README.md`,
  `docs/stockage.md`, `docs/specs-api.md`
- **Commits** : ceux de la branche sur `main` (`git log origin/main..HEAD`) : le journal ADR, la
  mémoire et les docs, les corrections de la revue avec cette note, puis les pourquoi que tu as
  donnés. La liste de commits fournie au début de la note contenait aussi l'historique de `main`.

## Le pourquoi

Le 20/10, tu as pris sept décisions sur le « squelette E1 E3 », la liste des tâches qui couvrent
E1 et E3 par les usages de K-B : où K-B tourne, ce que le contrat des fiches promet, comment la
clé reste valable, où partent les métriques, combien de temps la veille est gardée. Tant qu'elles
ne sont pas au journal, aucune PR qui les applique (#276, #277, #156, #162, #210) ne peut les
citer, et la mémoire du projet et le README disaient encore le contraire (« POC en conteneurs »,
« PostgreSQL au 08/11 »).

Cette PR ne change aucun code. Elle écrit la trace : ce qui est décidé, pourquoi quand le pourquoi
existe, ce qui a été écarté, et quelles décisions anciennes ne tiennent plus.

## Le comment

### Une rubrique, sept décisions numérotées

Les sept décisions sont dans une seule rubrique, comme celles du 15/10 (« POC du 25/10 ») :

```
### Squelette E1 E3 : cadrage du 20/10
```
(`docs/ADR/journal-decisions-projet.md:3280`)

Chaque décision a un numéro, qu'une PR cite (« décision 4 »). Chacune suit la forme du skill
`/adr-ls` : ce qui est décidé en gras, puis le pourquoi, les options écartées et leur raison, les
limites, et ce qu'elle révise.

### Un pourquoi a trois états, et l'absent s'écrit

Le skill `/adr-ls` distingue un pourquoi **explicite** (donné), **inféré** (déduit) et **absent**.
Un pourquoi inventé aurait l'autorité de l'écrit. L'en-tête de la rubrique le dit une fois :

```
l'autre d'un architecte (deux sous-agents de time-knight). Les décisions 6 et 7 ont été prises le
même jour, au découpage du squelette en issues. Un pourquoi que ces sources ne donnent pas est
écrit « non consigné ».
```
(`docs/ADR/journal-decisions-projet.md:3285-3287`)

Trois pourquoi manquaient aux sources : Grafana Cloud plutôt qu'Azure Monitor, 3 ans plutôt que
2, purger la veille plutôt que la garder. Tu les as donnés avant la PR : ils sont cités tels
quels, entre guillemets, avec « décision de Sabine du 2026-10-20 » (décisions 4 et 5). Celui de
Grafana Cloud renvoie à la comparaison de #163, encore à faire. Un premier plan écrivait un pourquoi déduit pour l'étape 8 ; le relecteur l'a montré
inexact (le 08/11 reste la date d'ACA ; seule la question sur la base met PostgreSQL en attente).
Il est devenu « non consigné ».

Quand la proposition de time-knight donne un argument, il est attribué à sa source et non à toi :

```
  refonte.** Décision de Sabine. Pourquoi de Sabine : non consigné ; elle dit que « le premier
  temps passe d'abord ». Argument de la proposition : les conteneurs (#200, #202) ne remplissent
```
(`docs/ADR/journal-decisions-projet.md:3294-3295`)

### Un revirement se dit dans les deux sens

Le journal ne réécrit jamais une entrée ancienne. Il ajoute, à sa fin, une mention datée qui
renvoie à la nouvelle. C'est l'usage déjà en place (« **Révisée le 2026-10-15** »). Par exemple,
dans la décision 1 du 15/10 :

```
  […] pas d'hébergement en v0 » (2026-10-12). — PR de #198 **Révisée le 2026-10-20** : trois temps,
```
(`docs/ADR/journal-decisions-projet.md:1734`)

Quatre verbes sont employés, chacun pour un cas : **Révisée** (la décision change), **Précisée**
(elle tient, avec un détail en plus), **Close** (une question est tranchée), **En attente** (elle
dépend d'une question ouverte). Dix-huit mentions ont été posées. Le relecteur du plan en a fait
ajouter plusieurs : trois entrées qui reposaient sur le juge, et la phrase « le *cleansed* n'est
jamais purgé » du 19/10. La revue de code a fait passer « Brut : catalogues d'état et conservation »
de « Précisée » à « Révisée » : sa règle et son pourquoi (« la purge ne touche que le *raw* ») ne
tiennent plus pour la veille.

### La question ouverte : « La base au temps 3 »

Une décision non prise ne disparaît pas : elle va dans « Décisions encore ouvertes », en tête :

```
- **La base au temps 3** (2026-10-20) : SQLite et Blob, ou PostgreSQL. Avec la première option,
```
(`docs/ADR/journal-decisions-projet.md:3378`)

Elle met en attente deux choses : « PostgreSQL au 08/11 » (décision 2 du 15/10) et l'étape 8 du
tri, qui attend une sauvegarde de la base. « Conservation des vieilles veilles », que la décision 5
tranche, reste dans la section, marquée « Close le 2026-10-20 » : une entrée du 19/10 y renvoie
(constat de `/code-review`).

### Le même fait partout

La règle 7 de « Avant de déclarer un travail fini » (`code.md`) demande qu'une correction de fond
se reporte partout. Le critère de #275 nommait certaines lignes ; une recherche a trouvé les autres
(`git grep "PostgreSQL au 08/11"`). Exemple dans le README :

```
- **Base** : SQLite aux deux premiers temps ; au troisième (Azure Container Apps, 08/11), SQLite
```
(`README.md:103`)

Les lignes tldr de `MEMORY.md` (« Problèmes connus ») n'ont pas été touchées par cette branche :
#274, sur l'autre piste de travail, les a retirées (PR #283, fusionnée pendant ce travail). Au
rebase, le conflit sur `MEMORY.md` a gardé les deux changements : ce retrait, et la ligne des
métriques réécrite ici.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Rangement | une rubrique, décisions numérotées : les PR les citent comme un tout | une rubrique par thème : elle disperse des décisions prises ensemble |
| Entrées anciennes | une mention datée à chacune, selon l'usage du journal | ne rien annoter : l'entrée ancienne ne dirait pas qu'elle ne tient plus |
| Pourquoi absent | « non consigné », signalé (mission et skill `/adr-ls`) | un pourquoi déduit, écrit comme sûr |
| Lignes hors du critère | corrigées quand elles disent le même fait (`code.md`, point 7) | les laisser : la même page se contredirait |
| `.claude/rules/poc.md` | signalé à toi | le modifier : ce dossier se modifie par toi seule |
| « B1 » de la décision 7 | non recopié : K-B ne le définit nulle part | le recopier sans définition |

## Preuve

| Commande ou sortie | Ce que ça démontre |
|---|---|
| `git grep -n "^## 2026-10-20" HEAD -- docs/ADR/journal-decisions-projet.md` → ligne 3278 | l'entrée du jour existe |
| `git grep -n "La base au temps 3\*\*" HEAD -- docs/ADR/…` → ligne 3378 | la question ouverte est ajoutée |
| `git grep -n -i "POC en conteneurs" HEAD -- MEMORY.md README.md` → une ligne, `MEMORY.md:55`, qui cite la règle 6 de `poc.md` comme problème connu | le premier temps n'est plus dit « en conteneurs » |
| `git grep -n "porté par #165" HEAD -- MEMORY.md` → ligne 49 | la ligne des métriques renvoie à son issue |
| `git grep -n tldr HEAD -- MEMORY.md` → rien, après le rebase sur #283 | le retrait des lignes tldr par #274 est gardé |
| `git diff origin/main...HEAD \| grep -c "$HOME"` → 0 | aucun chemin personnel |
| `uv run pytest -q` → 1956 passed, après le rebase sur `main` | aucun test ne dépend de ces textes |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas réécrire les entrées anciennes ?** Un journal qui efface ses revirements ne
   montre plus comment le projet a évolué. La mention datée garde les deux états et dit lequel
   vaut (`docs/ADR/journal-decisions-projet.md:1734`).
2. **Pourquoi écrire « non consigné » au lieu d'un pourquoi plausible ?** Un pourquoi inventé
   serait cru sans être vérifié. « Non consigné » dit honnêtement ce qui manque, et se complète
   (`:3287`).
3. **La purge de la veille contredit-elle « le *cleansed* est immuable » ?** Non : « immuable »
   veut dire jamais réécrit, pas gardé pour toujours (décision 5, `:3340`). L'entrée du 19/10
   est révisée sur place, avec la mention datée.
4. **Pourquoi la base au temps 3 reste-t-elle ouverte ?** Elle n'a pas été tranchée le 20/10, et
   rien ne presse aux temps 1 et 2 avec l'option SQLite et Blob (`:3378`).
5. **Le juge est-il abandonné ?** Non : il sort du contrat (« on voit plus tard ») ; #223 et #224
   restent ouvertes (`:3301`).

## Zones non vérifiées

- Les propriétés des options de monitorage (M1 à M4) viennent du rapport de l'architecte, pas
  d'une lecture des documentations de Grafana Cloud ou d'Azure Monitor.
- Les lignes du journal ADR citées par numéro ici (3278, 3378…) bougeront à la prochaine entrée.

## Ce qui reste

- Les pourquoi encore « non consignés » (décisions 1 et 6, rejet d'Azure Monitor) ; celui de
  Grafana Cloud, que la comparaison de #163 établira.
- L'application des décisions : #276 (durées, procédure de tri), #277 (spec des fiches sans juge),
  #156 (rotation de la clé, 401), #162 et #163 (métriques), #210 (essais).
- `.claude/rules/poc.md`, lignes 32 (« PostgreSQL au 08/11 ») et 144 (« POC en conteneurs ») : à
  toi de les modifier.
- La question « La base au temps 3 ».
