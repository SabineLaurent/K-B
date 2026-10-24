# Raccourcir les docstrings

- **Date** : 2026-10-24
- **Branche** : `docs/shorten-docstrings`
- **Issue** : #300
- **Fichiers principaux** : `.claude/rules/code.md` (la règle), toutes les docstrings de `src/k_b/` et de
  `tests/`, plus quatre renvois de lignes (`MEMORY.md`, `docs/specs-collecte.md`, `docs/stockage.md`,
  `docs/refactoring/plan.md`).
- **Série** : l'étape 9 de `docs/refactoring/plan.md` (docstrings longues et commentaires), dont cette PR
  fait la moitié « docstrings ».

Les commits couverts sont les onze de la branche, de `38df1fc` à `f4fa829`. Le skill a reçu une liste de
fichiers calculée sur une base plus ancienne que `origin/main` : cette liste ne décrit pas cette PR.

## Le pourquoi

Les docstrings faisaient 20 % des caractères de `src/k_b` (mesure du 24/10). Chaque session de Claude et
chaque relecteur qui ouvre un fichier lit cette prose. Une grande partie redisait le code, rappelait un
numéro d'issue ou racontait l'historique d'une décision. Sabine a tranché le 24/10 : « suppression des
docstrings à rallonge que personne ne lira ». La règle tient en une puce de `code.md`.

## Le comment

### 1. La règle

Elle est recopiée mot pour mot de la source tenue par time-knight :

```
- **Une docstring tient en une phrase** : ce que fait la fonction, la classe ou le module, quand le
  nom ne suffit pas. Le pourquoi seulement s'il n'est pas évident, en une ou deux lignes de plus.
```
(`.claude/rules/code.md:22-23`)

On a donc deux cas :
- **quand le nom dit tout**, la docstring part ;
- **quand une raison n'est pas évidente** (sécurité, contrat avec un tiers, vrai piège), elle reste,
  en une ou deux lignes.

### 2. Supprimer quand le nom suffit

```python
def read_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", NONE_SEEN))
```
(`src/k_b/core/api_request_log.py:51-52`)

L'ancienne docstring disait « The id log_request gave the request, for the other lines of the request » :
le nom et le corps de deux lignes le disaient déjà. Elle est supprimée, comme une vingtaine d'autres dans
`src/`, et davantage dans `tests/`, où le nom d'un test est déjà une phrase.

### 3. Garder le pourquoi de sécurité, en court

```python
    """Refuse a prefix that would trust too much, or a url the prefix does not cover.

    The prefix names an https host and a path, so that "https://example.org.evil.com" cannot
    pass; no user info either: urlsplit reads "https://evil.com\\@good.com/" as good.com, urllib
```
(`src/k_b/etl/http_download.py:50-53`)

Le second paragraphe est le genre de pourquoi que la règle garde. Sans lui, un lecteur pourrait
« simplifier » le contrôle et rouvrir la faille. Il est passé de quatre lignes à deux.

L'exemple contient une barre oblique inverse, écrite `\\` dans le source. L'outil qui appliquait les
nouvelles docstrings la refusait d'abord, puis l'a acceptée doublée. Sinon l'exemple aurait perdu son
sens, et rien ne l'aurait vu : la preuve ne compare pas le texte des docstrings (section 5).

### 4. Une docstring qui est tout le corps de la classe

```python
class NoTransactionError(RuntimeError):
    """A savepoint outside a transaction would begin one, and its release would commit it."""
```
(`src/k_b/database/savepoint.py:23-24`)

Une classe d'exception dont la docstring est le seul corps ne peut pas la perdre. Il faudrait écrire
`pass` à la place, et l'arbre syntaxique changerait. Ces 19 cas (18 dans `src`, 1 dans `tests/test_cli.py`)
gardent une phrase.

### 5. La preuve qu'aucun code n'a changé

Un script jetable, non commité, prend tous les `.py` de `src/` et de `tests/` dans les deux versions
(`git show origin/main:` et `git show HEAD:`) et fait deux contrôles par fichier :
- **l'arbre syntaxique** : chaque fichier est lu par `ast.parse`, on retire sa docstring de tête à chaque
  module, classe et fonction, puis on compare les `ast.dump` des deux versions ;
- **les commentaires** : on compare les jetons `COMMENT` que donne `tokenize`.

Le second contrôle est venu du relecteur du plan : `ast` ignore les commentaires. Un `# type: ignore` ou un
`# noqa` retiré par erreur serait donc passé inaperçu.

Résultat après chaque commit : `compared=194 ast_differences=0 comment_differences=0`.

## Choix faits et options écartées

- **Les 5 docstrings exposées dans l'OpenAPI ne bougent pas** (décision de Sabine). Ce sont les routes
  `list_items`, `read_item`, `list_trends`, `post_digests` et `SourceSchema`. Les raccourcir aurait changé
  `docs/api/*.json`. Or `docs/specs-api.md:11` veut qu'un changement visible par un client change la
  version, et `API_VERSION` vit dans `src/` : la preuve n'aurait plus donné 0 différence. Écarté : les
  raccourcir et monter les versions.
- **Aucun nouveau document** (mission). Le détail retiré d'une docstring n'a pas été déplacé dans `docs/`.
  Un renvoi vers un document existant reste permis, par exemple `docs/specs-collecte.md` pour les jours
  refusés de TLDR.
- **`.claude/rules/poc.md` n'est pas touché** (décision de Sabine). Ses renvois `fichier:ligne` décrivent
  le commit de départ `9e6e2e8` (`poc.md:7-8`), pas `main`. Ils restent donc justes.
- **Renvois corrigés** : `MEMORY.md:40`, `docs/specs-collecte.md:447-473` et `docs/stockage.md:255,264`.
  Ils étaient exacts sur `origin/main`, et les lignes retirées les décalaient (`code.md`, « Avant de
  déclarer un travail fini », point 7).
- **Renvois signalés, non corrigés** : ceux des notes datées (`docs/journaling/`, `docs/2026-*`, journal
  ADR) et des notes de refactorisation. Ce sont des archives.
- **Un commit par paquet**, chacun vert, pour qu'un relecteur puisse lire `src/` paquet par paquet.
- **Rédaction par un fichier d'édition** (`@@ chemin:ligne`, puis le nouveau texte, ou `-` pour
  supprimer), appliqué par un script qui remplace exactement le nœud de la docstring. Écarté : l'édition
  fichier par fichier à la main, trop longue pour environ 800 docstrings, avec un risque de toucher une
  ligne de code. Ce risque, la preuve l'aurait vu.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `compared=194 ast_differences=0 comment_differences=0` | aucun code ni commentaire changé, dans les 194 `.py` de `src/` et `tests/` |
| `uv run pytest` → 2353 passed, 11 deselected | le comportement est le même |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | le style et les types tiennent |
| `tests/data_api/test_openapi.py`, `tests/ai_api/test_ai_api_openapi.py` verts, `docs/api/*.json` inchangés | l'OpenAPI est la même |
| docstrings de `src/k_b` : 495 → 480, 103 392 → 60 976 caractères (−41 %) ; `tests/` : 306 → 300, 39 021 → 28 125 (−28 %) | le coût en lecture baisse |
| `git diff origin/main...HEAD \| grep -c "$HOME"` → 0 ; 0 caractère `Cc`/`Cf` dans les fichiers touchés | ni chemin personnel ni caractère invisible |

## Ce que tu dois pouvoir défendre

1. **Pourquoi une phrase, et pas une docstring complète avec `Args`, `Returns`, `Raises` ?** Les types sont
   dans les annotations, et `mypy --strict` les vérifie. Une section `Raises` paraphrasait le code et
   vieillissait dès que le code changeait. PEP 257 elle-même dit qu'une docstring d'une ligne ne doit pas
   redire la signature, que l'introspection donne déjà.
2. **Comment sais-tu qu'aucun code n'a changé ?** Par la comparaison des arbres syntaxiques et des
   commentaires sur tous les fichiers (section 5), puis par les tests. Une docstring n'est pas du code :
   l'arbre sans docstrings est le même.
3. **Une information de sécurité a-t-elle été perdue ?** La consigne était de garder chaque raison de
   sécurité ou de contrat, en une ou deux lignes : l'URL jamais citée parce qu'elle peut porter une clé, le
   `compare_digest` en temps constant, la limite CWE-367 acceptée dans `post/vault_files.py`. La revue de
   code a relu chaque docstring raccourcie contre son code.
4. **Pourquoi ne pas avoir touché aux docstrings de l'OpenAPI ?** Elles sont un contrat avec les clients
   de l'API. Les changer, c'est changer un document versionné, et sa version vit dans le code.

## Zones non vérifiées

- **Le texte des docstrings.** La preuve garantit que le code n'a pas bougé, pas que chaque nouvelle phrase
  dit juste. Cette justesse repose sur la relecture : la mienne, puis `/code-review high`.
- **L'appréciation de ce qui est « évident ».** Elle est une affaire de jugement, et elle a été tranchée
  docstring par docstring sans seconde lecture humaine.
- **Les tests de bout en bout** (`tests/e2e/`) n'ont pas été relancés. Leurs fichiers ne changent que par
  des docstrings (preuve à 0).

## Ce qui reste

- **Les commentaires**, l'autre moitié de l'étape 9 de `docs/refactoring/plan.md`, qui reste à faire.
- **Les renvois `fichier:ligne` des notes datées et des notes de refactorisation**, laissés tels quels.

## Sources

| Source | URL | Consultée le |
|---|---|---|
| PEP 257 – Docstring Conventions, « One-line Docstrings » : « One-liners are for really obvious cases » ; « The one-line docstring should NOT be a “signature” reiterating the function/method parameters » | https://peps.python.org/pep-0257/ | 2026-10-24 |
| PEP 8, qui renvoie à PEP 257 pour les docstrings | https://peps.python.org/pep-0008/ | 2026-10-24 (résultat de recherche) |
| Module `ast` de Python (`ast.parse`, `ast.dump`, `ast.get_docstring`) | https://docs.python.org/3/library/ast.html | non relue ce jour : usage courant |
| Module `tokenize` (jeton `COMMENT`) | https://docs.python.org/3/library/tokenize.html | non relue ce jour : usage courant |
