# Écrire la fiche de la conduite du projet

- Date : 2026-11-21
- Branche : `docs/project-conduct-sheet`
- Issue : #512
- Fichiers : `documentation/conduite-du-projet.md` (nouveau), `mkdocs.yml`, `documentation/index.md`,
  `documentation/accessibilite_pour_docu.md`, `documentation/integration_continue_pour_docu.md`
- Série : [la mise en forme de la fiche du monitorage (#669)](2026-11-21-mettre-en-forme-la-fiche-du-monitorage.md),
  pour la forme des fiches selon la notice d'AcceDe Web

## Le pourquoi

Le livrable E4 portait une marque « [WIP #512] » sur C16 : aucune fiche ne montrait comment K-B est piloté. La
fiche sert deux critères de C16, cités mot pour mot dans son encadré : les outils de pilotage disponibles, et les
objectifs et modalités des rituels partagés. Elle montre des faits, relevés par `gh` le 2026-11-21, chacun avec la
commande qui le relit : un jury peut rejouer chaque chiffre.

## Le comment

### Des faits datés, chacun avec sa commande

Chaque section donne un fait, puis la commande qui le rend, avec sa sortie en commentaire
(`documentation/conduite-du-projet.md:40-44`) :

```sh
gh issue list --repo SabineLaurent/K-B --state all --limit 1000 --json state \
    --jq '[length, (map(select(.state == "CLOSED")) | length), (map(select(.state == "OPEN")) | length)]'
# [367,230,137]
```

`--jq` filtre le JSON de `gh` sans outil de plus. L'heure du relevé est dans l'introduction (`:14-16`) : un chiffre
qui bouge ensuite, par l'activité normale du dépôt, reste juste à son heure.

### Une convention écrite comme elle est pratiquée

La première version disait « une issue suit un plan », « une carte par issue », « une note par PR ». La relecture a
compté : aucune issue n'a les cinq intitulés, 345 cartes pour 367 issues, 200 notes pour 299 PR fusionnées. Chaque
phrase dit maintenant ce qui est vrai de toutes, ou dit la fréquence (`:31-33`) :

```markdown
Un changement part le plus souvent d'une issue. Le corps d'une issue se range sous des intitulés en gras, d'ordinaire
« Pourquoi » et « Critère de fin », et selon le besoin « Dépend de », « Hors périmètre » et « Taille », ou, jusqu'au
2026-10-20, « Estimation ». Trois familles de labels classent les issues: leur taille (`size:XS` à `size:XL`), leur
```

De même : « ses cartes sont des issues » (`:60-61`), « une PR qui livre une issue la ferme par `Closes #n` »
(`:137-140`), « porte aussi les champs » au lieu de « chaque carte porte » (`:81-82`), « les issues en relecture » pour
la colonne `In review` (`:69`).

### Le tableau du projet et ses itérations

Le tableau kanban est le GitHub Project n° 12 : cinq colonnes, les valeurs du champ `Status`, quatre autres champs
(dont `Estimate`, un nombre), 19 vues (`:58-100`). Une carte passe en `Done` à la fermeture de son issue, par
l'automatisme « Item closed », actif (lu par `gh api graphql`, `:76-78`). La section « Les itérations » (`:102-111`)
décrit la configuration du champ
`Iteration` : quatre sprints d'une semaine, un de deux semaines, puis une itération par semaine du 02/11 au 30/11.

### Les rituels, en un tableau

`:168-185` donnent six rituels, chacun avec son objectif, ses modalités et sa trace sur GitHub : la conception dans
l'issue, le cycle d'une PR, la note de journal, le journal des décisions (ADR), le point d'arrêt et le jalon. Trois
compteurs suivent, chacun avec sa commande : 200 notes, 46 journées de décisions, 25 issues avec un point d'arrêt.
Le partage tient en une phrase (`:187-189`) : le pilotage et les rituels sont partagés par leurs traces sur GitHub,
lisibles par toute personne qui a accès au dépôt et à son tableau.

### La fiche dans le site

La fiche entre au menu, dans une partie « 5. Conduite du projet » (`mkdocs.yml:26-27`), et à l'index
(`documentation/index.md:21`). La déclaration d'accessibilité compte douze pages vérifiées selon la notice d'AcceDe
Web. Les deux lignes ajoutées à `mkdocs.yml` décalent les lignes qui suivent : chaque renvoi `mkdocs.yml:n` de la
déclaration et de la fiche de la CI a été décalé de deux, et relu sur le fichier de la branche.

## Choix faits et options écartées

- **Le nom court, `conduite-du-projet.md`**, plutôt que `conduite_du_projet_pour_docu.md` qu'écrit le critère de
  #512 : décision de Sabine du 2026-11-21 ; une PR à venir renomme les autres pages.
- **Les outils, les rituels et leurs traces seulement** : la fiche ne décrit ni personnes ni rôles (décision de
  Sabine du 2026-11-21) ; ni la méthode nommée (C16.1) ni la mise en public du tableau (C16.4), décisions de Sabine.
- **Le partage par les traces** : choix de Sabine du 2026-11-21, entre la phrase des traces et d'autres formes.
- **Le rituel de l'itération retiré** : aucune carte n'est rangée dans une itération hebdomadaire. La fiche décrit la
  configuration du champ ; le rituel revient sur un fait relevé si les cartes sont rangées.
- **Les titres des jalons en code** : ils sont recopiés tels que `gh` les rend, et l'un porte une espace avant un
  deux-points, que la typographie de `documentation/` exclut du texte.
- **« Le tableau du projet »** plutôt que « board » : un mot français, sans balise de langue, et le critère dit
  « tableau kanban ».

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Chaque commande de la fiche, relancée le 2026-11-21 : `[367,230,137]`, `{"size:L":16,"size:M":69,"size:S":164,"size:XS":96}`, 299 PR, 19 vues, les six contrôles requis, 46, 25 | Chaque chiffre de la fiche se relit |
| `uv run --locked --only-group docs mkdocs build --strict` : sortie 0 | La fiche est au menu, ses liens et ses ancres existent |
| Le HTML construit : `lang="fr"`, un seul `h1`, aucun saut de niveau, trois tableaux avec en-têtes, aucun lien nommé par une adresse | La fiche tient le contrôle du HTML de la déclaration d'accessibilité |
| `git diff --stat origin/main -- README.md docs/ ':!docs/journaling'` : vide | Ni le README ni `docs/` ne changent |
| Relecture neuve de `ea3e89eb`, relecture du delta `132ec427` | Les constats, triés, sont dans la PR |

## Ce que tu dois pouvoir défendre

1. **Où est le burndown chart ?** Le critère le cite parmi d'autres (« etc. ») ; K-B suit l'avancement par jalon,
   par ses issues fermées et ouvertes (`documentation/conduite-du-projet.md:113-133`).
2. **Pourquoi la colonne Ready est-elle vide ?** Elle tient les issues prêtes à commencer ; le 2026-11-21, aucune
   carte n'y est (`:67`). C'est un fait du tableau, à la main de Sabine.
3. **Comment un rituel est-il partagé ?** Par sa trace sur GitHub : l'issue, la PR, ses contrôles, la note, l'entrée
   du journal des décisions, le commentaire de point d'arrêt (`:174-189`).
4. **Une PR peut-elle fusionner sans contrôle ?** Non : le ruleset de `main` exige six contrôles verts, sur une
   branche à jour (`:154-166`).
5. **Pourquoi 46 journées de décisions et non 47 titres ?** Le journal a aussi un titre « Décisions encore
   ouvertes » ; la commande ne compte que les titres datés (`grep -cE "^## [0-9]{4}-"`).

## Zones non vérifiées

- Le rendu de la page dans un navigateur, avec WAVE et la touche Tab.
- La recherche « point d'arrêt » compte les issues dont le texte contient l'expression, corps ou commentaires ; un
  échantillon de 14 issues la contient bien, toutes ne sont pas relues.

## Ce qui reste

- Le compte des contrôles requis dans la fiche de la CI (sept) et le README (cinq), quand le ruleset en a six : la
  PR du README le reprend.
- Le rituel de l'itération, si les cartes sont rangées dans les itérations de la semaine.
- La colonne Ready et les jalons échus : décisions de Sabine.
