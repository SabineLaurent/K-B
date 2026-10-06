# Ranger les conversions à côté de leur lecteur

- **Date** : 2026-10-06
- **Branche** : `refactor/converters-beside-readers`
- **Issue** : #97 (plan ETL, étape 1 : `docs/2026-10-06-plan-etl.md`)
- **Fichiers principaux** : `src/k_b/items.py`, `src/k_b/cisa_kev.py`, `src/k_b/raw_items.py`
- **Série** : fait suite à `2026-10-05-lire-le-brut-en-items-communs.md`, qui avait créé `Item` et
  les `convert_*`.

## Le pourquoi

K-B doit devenir un ETL explicite : des étapes E, T et L génériques, et un module par source qui
porte ce qui lui est propre. Or le modèle commun, `items.py`, importait les 5 sources pour porter
leurs fonctions de conversion. Le module générique connaissait donc chaque source. Ajouter une
source obligeait à le modifier.

Cette PR est un **déplacement pur** : chaque conversion va dans le module qui lit le brut de sa
source. Le sens des dépendances s'inverse : les sources dépendent du modèle commun, et plus
l'inverse. Aucun comportement ne change.

## Le comment

### 1. Le modèle commun ne connaît plus aucune source

`items.py` n'importe plus que la bibliothèque standard et pydantic (`src/k_b/items.py:6-15`). Il
garde `Item`, `SourceCode` et les types de champs. Il ne garde rien de propre à une source.

### 2. Chaque conversion vit en fin du module de son lecteur

Exemple CISA (`src/k_b/cisa_kev.py:80-87`) :

```python
def convert_vulnerability(
    vulnerability: Vulnerability, collected_at: datetime, raw_file_path: str
) -> Item:
    return Item(
        source_code="cisa_kev",
        source_item_id=vulnerability.cve_id,
        title=vulnerability.vulnerability_name,
        url=NVD_PAGE_URL + vulnerability.cve_id,
```

Le corps de la fonction est inchangé, à la ligne près. La constante `NVD_PAGE_URL` l'a suivie
(`cisa_kev.py:12`) : seule CISA s'en sert. Chaque module reçoit `from k_b.items import Item`
(par exemple `cisa_kev.py:10`). Sa docstring dit désormais qu'il lit et convertit.

### 3. Le motif CVE passe dans le module commun

`CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")` est maintenant à `src/k_b/items.py:22`. Avant, il était
dans `cisa_kev.py`, et le lecteur des alertes GitHub l'importait de là : **une source dépendait
d'une autre**. Désormais, les deux lecteurs l'importent du module commun (`cisa_kev.py:10`,
`github_advisories.py:9`).

### 4. Pourquoi les deux changements vont dans le même commit

Si les lecteurs importent `items` alors que `items` importe encore les lecteurs, Python rencontre un
**import circulaire** : `items` commence à se charger, appelle `arxiv_papers`, qui redemande `Item`
à un `items` encore à moitié chargé, et l'import échoue. Retirer les imports de `items.py` et
ajouter ceux des lecteurs dans le même commit garde chaque état du dépôt importable.

### 5. Les tests suivent leur fonction

Les 7 tests de conversion quittent `tests/test_items.py` pour le fichier de test de chaque lecteur.
Chaque fichier y gagne ses constantes d'exemple, avec un chemin brut de sa propre source
(`tests/test_cisa_kev.py:14`) :

```python
RAW_FILE_PATH = "automation/cisa_kev/2026-10-05T093000Z.csv"
```

Ce chemin est relatif au dossier `raw/` (`items.py:48`), comme celui qu'écrit la collecte
(`collect.py:104` : `raw/automation/<source>/`). `test_items.py` garde les tests d'`Item` et celui
qui compare `SourceCode` aux sources de la base (`SEED_SOURCES`).

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Conversion dans le module du lecteur | Le plan ETL validé le 06/10 le prévoit : un module par source porte lecture et conversion (T). | La conversion dans la classe source (`x_source.py`) : mêlerait le téléchargement (E) et la transformation (T). |
| Conversion en fin de module | Le lecteur et ses fonctions d'aide restent groupés en tête ; la conversion vient après, puisqu'elle prend ce que le lecteur produit. | « Juste après le lecteur » : couperait le lecteur de ses fonctions d'aide (arXiv : `read_papers`, puis `parse_paper`, `read_text`, `read_date`). |
| `CVE_ID` dans `items.py` | C'est le modèle commun que toutes les sources importent déjà ; le plan l'y place. | Le laisser dans `cisa_kev.py` : le couplage entre deux sources restait. |
| Ne pas dériver `CveId` de `CVE_ID` | Ce serait changer une définition, pas déplacer du code. C'est le point S6 de la revue d'architecture, à part. | L'unifier ici : mélangerait deux sujets dans une PR qui promet « aucun comportement ne change ». |
| Un chemin brut par source dans les tests | Décision de Sabine : un chemin arXiv dans le test de CISA se lit mal. Le comportement ne change pas : la conversion recopie le chemin sans le lire. | Copier le chemin arXiv partout (déplacement strict). |
| `COLLECTED_AT` défini dans chaque fichier de test | Chaque test fixe sa date d'exemple ; ces valeurs peuvent changer pour des raisons différentes (`code.md`, DRY). | Une constante commune dans `conftest.py` : lierait des tests indépendants. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Tests déplacés avant le code : 5 `ImportError` (`cannot import name 'convert_paper' from 'k_b.arxiv_papers'`…) | Les tests visent bien le nouvel emplacement. |
| `uv run pytest` : 251 réussis, avant et après | Aucun test perdu, aucun comportement changé. |
| `grep -nE "k_b\.(arxiv|cisa|github|tldr)" src/k_b/items.py` : vide | Le modèle commun n'importe plus aucune source. |
| `grep -n "cisa_kev" src/k_b/github_advisories.py` : vide | Les alertes GitHub ne dépendent plus de CISA. |
| `grep -n convert_ tests/test_items.py` : vide | Les tests de conversion sont partis avec leur fonction. |
| `ruff check`, `ruff format --check`, `mypy --strict` : verts | Pas d'import mort, typage intact. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas avoir laissé les conversions dans `items.py` ?** Parce qu'un module générique
   qui importe chaque source doit changer à chaque nouvelle source. Ici, la source dépend du
   modèle commun, jamais l'inverse (`items.py:6-15`).
2. **Que se passe-t-il si quelqu'un réimporte un lecteur dans `items.py` ?** Import circulaire :
   `items` et le lecteur s'attendent l'un l'autre. Le critère de fin le surveille par un `grep`.
   Un test de dépendances l'automatisera à l'étape 3 du plan.
3. **Pourquoi le motif CVE dans le modèle commun, et pas dans un module « CVE » à part ?** Parce
   qu'il n'a que deux usagers, tous deux importent déjà `items`, et qu'un nouveau module pour une
   ligne serait une abstraction sans besoin (`code.md`, KISS).
4. **Le format CVE n'est-il pas toujours écrit deux fois ?** Si : `CVE_ID` (`items.py:22`) et
   `CveId` (`items.py:28`), plus le `CHECK` SQL. Les unifier est le point S6, désormais faisable
   puisque l'import circulaire a disparu.
5. **Comment sait-on que rien n'a changé ?** Les 7 tests de conversion sont recopiés tels quels,
   seule leur constante de chemin change, et les 251 tests passent avant et après.

## Zones non vérifiées

- Les 5 corps de `convert_*` ont été déplacés par script, par plages de lignes. Leur identité avec
  l'original est montrée par les tests, pas par une comparaison ligne à ligne faite à la main.
- Le motif CVE reste dupliqué (voir question 4) : non traité ici.

## Ce qui reste

- **Releases autonomes** (#98) : le lecteur des releases tire le dépôt de son brut.
- **Une seule liste des sources** (#99) : le contrat `SourceReader` gagne un typage qui lie un
  lecteur à sa conversion (constat 3 de la revue de cette PR).
- **S6** : un seul type Python pour le format CVE.
