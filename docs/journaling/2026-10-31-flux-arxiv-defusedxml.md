# Le flux arXiv lu par defusedxml

- **Date** : 2026-10-31
- **Branche** : `fix/arxiv-defusedxml`
- **Issue** : #69 (« Lire le flux arXiv sans développer les entités XML »)
- **Fichiers principaux** : `src/k_b/etl/sources/arxiv.py`, `tests/etl/sources/test_arxiv.py`,
  `pyproject.toml` et `uv.lock`, `docs/specs-collecte.md`, `docs/ADR/journal-decisions-projet.md`

La PR tient en trois commits : `d6da8fe` (le changement), `29d306f` (corrections du premier
`/code-review`), `76d89f9` (corrections du second). Les autres commits et fichiers que liste
`git log` depuis la branche de départ sont ceux des PR #377 et #378, déjà fusionnées sur `main` :
ils ne font pas partie de celle-ci.

## Le pourquoi

La collecte arXiv télécharge un flux Atom, donc du XML, venu d'un service externe : une donnée
non fiable (`code.md`, « Toute entrée externe est non fiable »). Le XML permet de déclarer, dans
l'en-tête du document (le DTD), des **entités** : des noms remplacés par un texte (entité
interne) ou par le contenu d'une ressource (entité externe, `SYSTEM "file:///…"` ou une URL).
C'est la porte des attaques XXE (lecture de fichiers, requêtes vers le réseau interne) et des
« bombes » d'expansion.

Jusqu'ici, le flux était lu par `xml.etree.ElementTree.fromstring`, avec un `# noqa: S314` qui
faisait taire la règle de ruff dédiée, et un commentaire qui affirmait l'analyseur sûr. Le constat
de #69 le contredisait : l'expat de Python refuse bien une entité externe, mais **développe une
entité interne** déclarée dans le flux. Sabine a tranché le 18/10 pour `defusedxml`, « pour raison
de sécurité ».

## Le comment

### 1. Un seul point de lecture du XML

Les trois fonctions qui lisent le flux, `count_papers` et `read_total_results` (à la collecte) et
`read_papers` (à l'import), passent toutes par `parse_feed`. Changer l'analyseur à cet endroit
suffit donc pour tout K-B : c'est le seul `fromstring` de `src/k_b` (vérifié par la revue de
sécurité).

```python
    try:
        feed = DefusedElementTree.fromstring(raw_response)
    except ElementTree.ParseError as error:
        raise PageRefusedError(f"not an XML document: {error}") from error
```
`src/k_b/etl/sources/arxiv.py:164-167`

`defusedxml.ElementTree.fromstring` a la même signature que celle de la bibliothèque standard et
rend le même `Element`. Le module garde `import xml.etree.ElementTree as ElementTree` pour deux
choses : le type de retour `ElementTree.Element` (les types de `types-defusedxml` ne le
réexportent pas) et `ElementTree.ParseError`, que defusedxml lève tel quel pour un XML mal formé
(c'est la même classe ; vérifié par la revue de sécurité).

### 2. Les réglages par défaut de defusedxml

Trois paramètres règlent ce que defusedxml refuse (Context7, `/tiran/defusedxml`, README et
référence de `ElementTree`) :

| Paramètre | Défaut | Ce qu'il refuse |
|---|---|---|
| `forbid_dtd` | `False` | tout `<!DOCTYPE>` (`DTDForbidden`) |
| `forbid_entities` | `True` | toute déclaration `<!ENTITY>`, interne ou externe (`EntitiesForbidden`) |
| `forbid_external` | `True` | toute référence externe d'une entité ou d'un DTD (`ExternalReferenceForbidden`) |

K-B garde les défauts. `forbid_entities` agit **à la déclaration** : defusedxml installe un
gestionnaire d'expat qui lève dès qu'une `<!ENTITY>` est lue, avant toute utilisation. Une entité
externe est donc refusée par `EntitiesForbidden` elle aussi, avant même qu'on cherche à la
charger. Un `DOCTYPE` qui pointe vers un DTD externe, sans entité, est lu sans erreur et le DTD
n'est jamais chargé (observé : un `<!DOCTYPE feed SYSTEM "http://127.0.0.1:9/x.dtd">` rend
l'élément sans erreur réseau).

### 3. Le refus devient une erreur prévue, sans le contenu du flux

```python
    except DefusedXmlException as error:
        # The type only, its cause hidden from the trace: the exception quotes the entity name
        # and the address declared in the feed.
        raise PageRefusedError(f"XML refused: {type(error).__name__}") from None
```
`src/k_b/etl/sources/arxiv.py:168-171`

- `DefusedXmlException` est la classe mère des trois refus : un seul `except` les prend.
- `PageRefusedError` (`src/k_b/etl/source_contract.py:29`) est une erreur prévue : à la collecte,
  la source échoue sur une ligne de journal sans trace, et sa date de dernière collecte ne bouge
  pas (`src/k_b/etl/extract.py:28`, `:71`) ; à l'import, la page devient un rejet nommé
  (règle 1 de `conventions.md`).
- Le message ne garde que **le nom du type**. Observé : `str(EntitiesForbidden)` vaut
  `EntitiesForbidden(name='…', system_id='…', public_id=None)`, soit le nom de l'entité et
  l'adresse déclarés **par le flux**. Les citer reviendrait à recopier une donnée non fiable dans
  le journal.
- `from None` : sans lui, Python affiche l'exception d'origine sous « During handling of the
  above exception… », et le nom et l'adresse reviennent par la trace. `from None` pose
  `__suppress_context__ = True` : `traceback` et `logging` ne l'affichent plus. L'exception reste
  pourtant attachée dans `__context__` (voir « Zones non vérifiées »).

### 4. Le commentaire dit ce qui est observé

L'ancien commentaire, au-dessus de la constante `ATOM`, affirmait que l'expat de Python
« refuses entity expansion attacks ». Le test l'a démenti. Le nouveau est sur `parse_feed`, là où
il s'applique (`arxiv.py:161-163`), et ne dit que l'observé : `ElementTree` seul développe une
entité déclarée ; defusedxml refuse toute déclaration d'entité ; un DTD externe est accepté mais
jamais chargé.

### 5. Deux dépendances, dont une de développement

`defusedxml` 0.7.1 (publiée le 2021-03-08, `uv.lock`) n'a pas de `py.typed` : `mypy --strict`, qui
tourne en CI, ne connaîtrait pas ses types. Ils viennent de `types-defusedxml`
(0.7.0.20260504, de typeshed), ajouté en dépendance de développement, comme `types-pyyaml`.
Les deux sont accordées par Sabine le 31/10.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| `defusedxml` | décision de Sabine du 18/10 ; c'est la dépendance que conseille la règle ruff S314 | `# noqa: S314` justifié : l'entité interne resterait développée |
| réglages par défaut | ils refusent toute entité et toute référence externe | `forbid_dtd=True` : refuserait un flux pour un seul `DOCTYPE`, sans protection de plus |
| `types-defusedxml` en dev | `mypy --strict` en CI ; accord de Sabine (Q-A) | `# type: ignore[import-untyped]` ou un `cast` : ils masquent les types au lieu de les fournir |
| message `XML refused: <type>` | le type suffit à diagnostiquer, rien du flux n'est cité | citer `str(error)` : il porte le nom et l'adresse déclarés par le flux |
| `from None` | la trace ne montre plus l'exception de defusedxml | `from error` : la trace la cite ; lever hors du bloc `except` pour vider aussi `__context__` : 4 lignes de plus pour un attribut que rien dans l'ETL ne lit (tranché par time-knight) |
| message « not an XML document » gardé | `tests/etl/test_load_registry.py:199` le lit | — |

### Tri des revues (time-knight, délégation de Sabine du 15/10)

**Premier `/code-review high`**, 5 constats :
1. `from error` chaîne l'`EntitiesForbidden`, dont le texte cite le flux → **corrigé** (`from
   None`), test d'abord.
2. Le journal ADR disait « observé par le test », or aucun test gardé n'exécute `ElementTree` →
   **corrigé** : « observé le 31/10 : le test de l'entité interne, lancé sur l'ancien code, ne
   lève rien ».
3. Seul `read_papers` était testé, pas les lecteurs de la collecte → **corrigé** : le test de
   l'entité interne est paramétré sur les trois lecteurs.
4. Le commentaire était loin de `parse_feed` → **corrigé** : déplacé.
5. defusedxml 0.7.1 retire un instant `_elementtree` de `sys.modules` à son import → **écarté** :
   effet unique au chargement, aucun import concurrent de `xml.etree` dans K-B, et la 0.8.0 n'est
   qu'en version candidate.

**`/security-review`** : 1 sous-agent, 0 constat.

**Second `/code-review medium`**, 6 constats :
1. `from None` masque la cause dans la trace mais la laisse dans `__context__` → **corrigé par le
   texte** : commentaire et ADR disent « masquée de la trace », ce que le test prouve.
2. Le test ne lit que `format_exception` → **écarté** : avec 1, il prouve exactement la promesse.
3. Un encodage inconnu (`encoding="bogus-enc"`) lève `LookupError`, hors `PageRefusedError` →
   **issue #379** : le défaut existe déjà sur `main`.
4. La branche `ParseError` chaîne et cite `{error}` → **écarté** : antérieur ; le message d'expat
   ne porte que ligne et colonne, et `extract.py:69` le cite par `quote_value`.
5. Ligne de l'ADR à 128 caractères, et « sans chaîner » inexact → **corrigé**.
6. Le test de la trace ne couvre qu'un lecteur → **écarté** : les trois passent par `parse_feed`,
   et la valeur d'une entité interne n'est pas dans le message de l'exception.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_feed_declaring_an_internal_entity_is_refused_unexpanded` (`test_arxiv.py:332`), rouge sur l'ancien code : `DID NOT RAISE PageRefusedError` | `ElementTree` développait l'entité ; defusedxml la refuse, sur les trois lecteurs |
| `test_a_feed_declaring_an_external_entity_is_refused_unread` (`:356`), sur l'ancien code : `not an XML document: undefined entity &a;` | l'entité externe était déjà refusée, mais par accident ; elle l'est maintenant à sa déclaration |
| `test_a_refused_entity_leaves_no_value_of_the_feed_in_the_traceback` (`:342`), rouge avant `from None` : `'declaredname' is contained here` | ni le nom ni l'adresse déclarés ne sont dans la trace |
| `test_a_recorded_response_gives_one_paper_per_entry` (`:207`), inchangé et vert | le vrai flux enregistré se lit comme avant |
| `uv run ruff check --select S314 src/` → `All checks passed!` ; `git grep -n "noqa: S314" src` → vide | le critère de #69 est tenu sans `noqa` |
| `uv run pytest` → 3084 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

- **Pourquoi pas `forbid_dtd=True`, plus strict ?** Un `DOCTYPE` seul n'est pas dangereux : le
  danger vient des entités et des références externes, déjà refusées par les deux autres réglages.
  Refuser tout `DOCTYPE` ferait échouer une collecte pour un en-tête inoffensif
  (`arxiv.py:161-163`).
- **Que se passe-t-il si arXiv envoie une entité demain ?** La collecte arXiv échoue sur une ligne
  `XML refused: EntitiesForbidden`, sans trace ; sa date ne bouge pas, et la collecte suivante
  redemande la même fenêtre. Les autres sources ne sont pas touchées (`extract.py:71`).
- **Pourquoi ne pas citer l'erreur de defusedxml dans le journal ?** Son texte porte le nom et
  l'adresse déclarés par le flux : une donnée non fiable, qui pourrait aussi servir à injecter du
  texte dans le journal. Le type suffit (`arxiv.py:168-171`, règle 3 de `conventions.md`).
- **Pourquoi une entité externe était-elle déjà refusée avant ?** L'expat de Python ne charge pas
  les entités externes : il levait « undefined entity ». C'était un comportement de l'analyseur,
  pas une décision de K-B ; defusedxml le rend explicite et testé.
- **Où est la sécurité, en profondeur ?** Analyseur durci (defusedxml), refus en erreur prévue,
  message réduit au type puis coupé et échappé par `quote_value` (`extract.py:69`), et des tests
  pour chaque lecteur.

## Zones non vérifiées

- `__context__` : avec `from None`, l'`EntitiesForbidden` reste attachée à la
  `PageRefusedError` (`__context__`), seulement masquée de la trace. Rien dans l'ETL ne la lit
  aujourd'hui ; un outil qui parcourrait `__context__` sans lire `__suppress_context__` la verrait.
- L'effet de defusedxml 0.7.1 sur `sys.modules` à son import (il retire un instant
  `_elementtree` pour charger l'analyseur en pur Python) : lu dans son code
  (`defusedxml/ElementTree.py:36-44`), sans test de concurrence.
- Le test « billion laughs » (entités imbriquées) n'est pas écrit : le plan l'a retiré, l'expat
  local le refuse déjà et defusedxml s'arrête à la première déclaration. Non rejoué ici.
- Le vrai flux d'arXiv n'a pas été relu par une collecte réelle dans cette PR : seul le flux
  enregistré (`tests/fixtures/arxiv_extract.xml`) l'a été.

## Ce qui reste

- #379 : un flux à l'encodage inconnu lève `LookupError` au lieu d'un refus nommé.
- #86 : passer le téléchargement (`http_download.py`) de `urllib` à `httpx2`, la PR suivante.
