# Remettre à jour les passages des fiches que `main` a dépassés

- **Date** : 2026-11-18
- **Branche** : `docs/stale-passages-request-94`
- **Issue** : #623 (la demande 94 de la revue de la certification du 14/11)
- **Fichiers** : `documentation/monitoring_pour_docu.md`, `README.md`, `docs/2026-11-08-tests-api-ia.md`,
  `documentation/tests_pour_docu.md`, `documentation/service_ia_pour_docu.md`

## Le pourquoi

Le jury lit les fiches comme des preuves. Une fiche qui décrit un état que le code a dépassé affaiblit la preuve. La
revue du 14/11 relevait des passages de ce genre. Revérifiés sur `main` le 2026-11-18, la plupart étaient déjà à
jour ; quatre ne l'étaient pas.

## Le comment

### Revérifier avant de corriger

Chaque passage cité par la revue a été relu sur `main` par une commande, pas de mémoire : `git show`, `grep`, `gh`.
Le commentaire de #623 du 2026-11-18 donne la commande de chaque passage et son résultat attendu. Un passage déjà
à jour garde sa commande de preuve, pour que la revue suivante puisse le dire « servi ».

### Le compte des noms de séries

La fiche du monitorage disait 20 noms de séries relevés dans Grafana le 2026-11-08. Le test qui tient ces noms en
porte 22 (`tests/test_grafana_files.py:28-51`) :

```
# The names Grafana Cloud gave the measures of the sandbox, in Explore, on 2026-11-08 (count by
# (__name__) of the series labelled sandbox).
NAMES_SEEN_IN_GRAFANA = {
```

La fiche cite maintenant ce fichier, et son tampon dit la date et le commit de la correction.

### La relance du compte rendu des tests

Le compte rendu des tests de l'API IA date du 2026-11-08, au commit `f91bb97`. Plutôt que de le réécrire, une section
« Relance du 2026-11-18 » s'ajoute en tête (`docs/2026-11-08-tests-api-ia.md:12`) : les mêmes commandes locales,
leurs résultats, les groupes recomptés (1 550 tests, puis 1 705), les PR qui ont changé ces fichiers, l'état des
issues citées. Les tests `e2e` et `postgresql` ne sont pas relancés : les premiers demandent des clés et le réseau,
les seconds un serveur ; la raison est écrite.

### Le passage de la production à gpt-6.1-sol

La fiche du service d'IA parlait de ce passage au futur. Il a eu lieu le 2026-11-18, à la seconde passe de
l'infrastructure. Le dépôt ne le trace pas : la fiche l'écrit comme ses autres lectures d'Azure, avec la commande de
lecture et sa sortie (`az containerapp show`), sans nommer la ressource, le registre ni le groupe.

## Choix faits et options écartées

- **Pas d'issue neuve** : #623 portait déjà la demande 94 ; la PR la ferme (décision de time-knight).
- **Une relance en tête du compte rendu**, plutôt qu'un compte rendu neuf : le corps reste la preuve du 2026-11-08, la
  relance dit ce qui a changé.
- **Le test comme source du compte de noms**, plutôt qu'un nouveau relevé dans Grafana : le test fige le relevé du
  2026-11-08, et la fiche cite cette date.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `make test` : 5628 réussis, 365 écartés ; `make test-ai-api` : 1154 et 8 ; la partie `kb` : 543 | la relance, sans échec |
| `git diff --stat a7d7c309 1bef80f2 -- src tests Makefile pyproject.toml uv.lock` vide | la relance vaut pour `1bef80f2` |
| Les commandes de preuve du commentaire de #623 | chaque passage, à jour ou corrigé |
| `mkdocs build --strict` | liens et menu valides |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas relancer les tests `e2e` ?** Ils lisent des clés et appellent de vrais services ; la relance se
   limite au local, et la CI lance les tests `postgresql` à chaque fusion.
2. **D'où vient l'heure du passage à gpt-6.1-sol ?** De la sortie de la seconde passe et d'une lecture de l'app par
   l'opératrice, le 2026-11-18 : la fiche donne la commande à relancer.

## Zones non vérifiées

- Les tests `e2e` et `postgresql`, non relancés ici.
- L'état en ligne après le 2026-11-18 : relevé une fois, vers 11:28 UTC.

## Ce qui reste

- Le retrait de `gpt-6-luna`, prévu après le passage du job des fiches, jeudi : #621.
