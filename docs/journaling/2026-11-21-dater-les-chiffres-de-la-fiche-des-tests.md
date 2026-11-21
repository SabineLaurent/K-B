# Dater les chiffres de la fiche des tests, et séparer les API servies des tests de bout en bout

- Date : 2026-11-21
- Branche : `docs/tests-sheet-dated-figures`
- Issue : #672
- Fichier principal : `documentation/tests_pour_docu.md`
- Série : [mettre en forme la fiche du monitorage](2026-11-21-mettre-en-forme-la-fiche-du-monitorage.md) (#669), et
  [mettre en forme les fiches restantes](2026-11-18-mettre-en-forme-les-fiches-restantes.md) (#646)

Le commit de cette PR est `eca2c460`, plus celui de cette note, sur `main` à `36c1e02d`. Les autres commits de la liste
fournie à la note sont déjà sur `main` (#670, #662, #665, #664) et ont leurs propres notes.

## Le pourquoi

La fiche des tests est montrée au jury d'E3 pour la compétence C12 (la documentation de l'environnement et de
l'exécution des tests), par des captures refaites depuis `main` après cette PR. Une relecture de nuit y a relevé trois
défauts :

- ses chiffres dataient du 2026-11-08 (commit `852dad4`), alors que la suite a grandi depuis ;
- une ligne du plan de tests de `POST /digests` appelait « bout en bout, dans la CI » un test qui tourne bien dans la
  CI, alors que la fiche réserve « bout en bout » aux tests `e2e`, lancés à la main hors de la CI ;
- un commentaire du bloc de code de « Calculer la couverture » dépassait la largeur du bloc, donc était coupé à
  l'écran.

Un quatrième défaut est entré en route, sur décision du Second : le tableau « Ce que lance la CI » ne listait pas le
job `digests-reference`, alors qu'un tableau qui porte ce titre se lit comme une liste complète.

## Le comment

### Des chiffres d'une exécution nommée, lus dans son journal

Chaque chiffre vient d'une exécution qu'on peut rouvrir : l'exécution 44770275956 du workflow `CI`, déclenchée par le
push du commit `cf7b8983` (tag `v0.1.8`) le 2026-11-20 à 16:08 UTC. Le tampon de la fiche le dit, avec un lien vers
cette exécution :

```markdown
(2026-11-18). Les comptes de tests, la couverture et ce que lance l'intégration continue (CI) sont ceux du commit
`cf7b8983` (tag `v0.1.8`, 2026-11-20): les comptes de la suite et de `tests-postgresql` et la couverture lus dans le
journal de [l'exécution 44770275956 de la CI](https://github.com/SabineLaurent/K-B/actions/runs/44770275956), les
```

(`documentation/tests_pour_docu.md:16-21`, qui développe aussi le sigle CI à son premier emploi). Les chiffres ont été lus par `gh run view --job <id> --log`, pas
recopiés d'un message. Dans le job `tests` : `5664 passed, 365 deselected` et `Total coverage: 98.54%`. Dans le job
`tests-postgresql` : `350 passed`. Ils remplacent les mêmes chiffres partout où la fiche les donnait : la table
« Lancer les tests » (`:107`, `:109`) et le paragraphe de la mesure de couverture (`:241-243`). Les chiffres que
tn-orchestrateur avançait (98,54 %, 5 664, 350) sont confirmés par ce journal.

### Compter sans lancer : `--collect-only`

Les tests `e2e` appellent de vraies sources et un vrai service : en lancer un pour le compter coûterait des appels
réels. `pytest -m e2e --collect-only -q` collecte les tests et s'arrête, sans en exécuter un seul. Au commit
`cf7b8983` exact (un `checkout` détaché du worktree propre, puis retour à `36c1e02d`), et dans un environnement vidé
(`env -i`), il compte `15/6029 tests collected (6014 deselected)` : 1 test de l'export, 10 de sources, 4 du bac à
sable. Le total de 6029 est celui que la CI collecte au même commit, ce qui recoupe les deux mesures. Le compte
remplace « 11 au commit `852dad4` » (`:110`) et le commit de « 15 tests de bout en bout » (`:196-197`), qui valait déjà
15 au commit `1d2f554`.

### Nommer ce que lance le test, pas sa distance

`tests/commands/test_live_apis.py` n'est pas marqué `e2e` : la suite par défaut le lance, et le journal du job `tests`
montre `tests/commands/test_live_apis.py ...` (3 tests réussis). La ligne était donc vraie, mais son nom la confondait
avec les tests `e2e`. Elle prend le nom de ce qu'elle lance :

```markdown
| API servies, dans la CI | `kb digest`, puis les deux API servies par uvicorn sur `127.0.0.1`, puis la base de test, sur le modèle rejoué et sans réseau hors de la machine (`tests/commands/test_live_apis.py`, lancé par le job `tests`) |
```

(`documentation/tests_pour_docu.md:262`). « Sur le modèle rejoué et sans réseau hors de la machine » vient de la
docstring du module (`tests/commands/test_live_apis.py:1-4`). La ligne `e2e` dit en plus qu'ils sont lancés à la
main, avec un lien vers leur section (`:264`). Le même nom remplace « Bout en bout, dans la CI » dans la section « 6. Routes »
(`:378-379`), et « le transport réseau hors du bout en bout » devient « hors des API servies et des tests de bout en
bout » (`:440-441`) : deux restes relevés par la relecture neuve.

### Le job `digests-reference` dans la table de la CI

Le job rejoue le jeu de référence de `POST /digests` et échoue sous un seuil, si le rejeu n'envoie pas tous les
appels enregistrés dans leur ordre, ou si la route ne répond pas 200 : `digests_evaluation.py` sort alors avec
`EXIT_BELOW_THRESHOLD` (seuils `tests/ai_api/digests_evaluation.py:28-34`, rejeu `:80-90`, sortie `:189-190`). La
ligne ajoutée (`documentation/tests_pour_docu.md:214`) reprend les faits que la fiche de la CI donne déjà
(`documentation/integration_continue_pour_docu.md:101`), en plus court, avec ses renvois. La phrase qui suit la table
dit que les sept jobs ont réussi dans cette exécution (`:216-217`), ce que montre `gh run view 44770275956 --json jobs`.

### Le commentaire au-dessus de la commande

La ligne de `make test-cov` et de son commentaire faisait 134 caractères : le bloc de code défilait à la
largeur du site. Chaque commentaire passe sur sa propre ligne, au-dessus de sa commande (`:223-226`) ; la plus longue
ligne fait 86 caractères, et la capture de la section, à 1 240 pixels de large, montre le bloc en entier.

## Choix faits et options écartées

- **Le mot « exécution », pas « run »** : la fiche de la CI écrit déjà « l'exécution 42617081839 de `CI` »
  (`integration_continue_pour_docu.md:384`), et un mot anglais du texte devrait être balisé `<span lang="en">` (règle
  6.2 de la notice AcceDe Web). Écarté : « run », plus court mais anglais.
- **Un lien vers l'exécution** plutôt que la seule commande `gh run view` : un jury le suit sans terminal. Le lien
  vaut tant que GitHub garde l'exécution ; ses journaux sont gardés 90 jours (la fiche de la CI).
- **Les l. 106 et 108 mises au même exécution**, alors que la mission ne citait que la mesure de couverture et les
  comptes `e2e` : une fiche qui donnerait deux comptes différents pour la même suite se contredirait. Accord du Second.
- **« API servies, dans la CI »** plutôt que garder « bout en bout » avec une précision : le terme « bout en bout »
  désigne dans toute la fiche les tests `e2e` (sections « Pour les tests de bout en bout », « Les tests de bout en
  bout ») ; le garder pour un autre type entretenait la confusion.
- **Les nombres sans séparateur** (5664), comme le 4061 qu'ils remplacent dans la même fiche.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `gh run list --commit cf7b8983…` : `CI` 44770275956, `push`, `success`, 2026-11-20T16:08:07Z | l'exécution est celle du commit, et elle a réussi |
| journal du job `tests` : `5664 passed, 365 deselected`, `Total coverage: 98.54%` (16:10:30 UTC) | les chiffres de la suite et de la couverture |
| journal du job `tests-postgresql` : `350 passed, 5679 deselected` | le chiffre de PostgreSQL |
| `uv run pytest -m e2e --collect-only -q` à `cf7b8983` : `15/6029 tests collected` | le compte des tests de bout en bout, sans en lancer un |
| journal du job `tests` : `tests/commands/test_live_apis.py ...` | le test des API servies tourne dans la CI |
| `mkdocs build --strict` vert ; capture de « Calculer la couverture » à 1 240 pixels | la fiche se construit, et le bloc de code se lit en entier |
| `grep -c "98,42 %\|4061 réussis"` → 0 ; « bout en bout, dans la CI » cherché sans casse et à travers les sauts de ligne → 0 | les anciens chiffres et l'ancien nom ont disparu |
| relecture neuve en lecture seule (sous-agent) : aucun chiffre faux ; cinq constats corrigés sur le tri du Second | les faits et les renvois sont vérifiés par un second lecteur |

## Ce que tu dois pouvoir défendre

1. **D'où viennent 5664 et 98,54 % ?** Du journal du job `tests` de l'exécution 44770275956 de la CI, au commit
   `cf7b8983` (`v0.1.8`) ; le lien est dans le tampon de la fiche (`tests_pour_docu.md:16-21`).
2. **Pourquoi ne pas avoir lancé les tests `e2e` pour les compter ?** Ils appellent de vraies sources, Grafana Cloud et
   BigQuery ; `--collect-only` les compte sans les exécuter.
3. **Le test des API servies est-il un test de bout en bout ?** Il enchaîne `kb digest`, les deux API sur des sockets
   réelles et la base de test, mais sur un modèle rejoué et sans réseau hors de la machine : c'est pour cela qu'il tourne
   dans la CI, et que la fiche ne l'appelle plus « bout en bout » (`:262`, `:378-379`).
4. **Que vérifie `digests-reference` que `tests` ne vérifie pas ?** Les seuils du 2026-10-15 sur les sorties
   enregistrées du modèle : 100 % de schémas valides après une nouvelle tentative, au moins 95 % de fidélité, aucun
   item oublié (`ci.yml:111-114`).

## Zones non vérifiées

- Le rendu du bloc de code à une largeur plus étroite que 1 240 pixels (écran de portable, téléphone) n'a pas été
  capturé.
- Le compte `e2e` a été collecté au commit `cf7b8983` sur le Mac, pas dans la CI, qui ne les collecte jamais.

## Ce qui reste

- Rien dans cette fiche pour cette issue. Le « provisoire » de la fiche du monitorage attend Sabine, hors de cette PR.
- Les captures de c12.1.a et c12.6.a se refont depuis `main` après la fusion.
