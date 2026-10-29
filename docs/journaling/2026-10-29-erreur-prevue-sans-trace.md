# Journaliser l'échec prévu d'une source sur sa ligne seule, sans la trace de Python

- **Date** : 2026-10-29
- **Branche** : `fix/collect-expected-errors-without-traceback`
- **Issue** : #361
- **Fichiers principaux** :
  - `src/k_b/etl/source_contract.py` (les deux classes) ;
  - `src/k_b/etl/extract.py` (la ligne d'échec) ;
  - `src/k_b/core/quoting.py` (la longueur de coupe en paramètre) ;
  - les sources, dont les refus de page deviennent `PageRefusedError`.
- **Commits** :
  - `af1ac6a` : le code et ses tests ;
  - `c214000` puis `63665e1` : le message de clipping et la coupe à 300 ;
  - `673f43b` : la doc ;
  - `6a2dfd3` : le test de la coupe ;
  - `8fa980b` : l'entrée du journal ADR, puis cette note.
- **Série** : suit [Arrêter kb sur Ctrl-C par une ligne datée et le code 130, sans la trace de
  Python](2026-10-28-arreter-kb-sur-ctrl-c.md).

## Le pourquoi

Quand une source échoue, `kb collect` écrit une ligne datée au journal, puis continue avec les
autres sources. Jusqu'ici, cette ligne était toujours suivie de la **trace de Python** (la pile des
appels), même quand l'échec était attendu.

L'essai du 29/10, sur un coffre Obsidian sans dossier `Clippings`, l'a montré : une ligne claire
(`ClippingsFolderMissingError 'clippings_folder_missing: …'`), puis 11 lignes de trace qui
n'apprenaient rien. Ces 11 lignes ressemblent à un plantage, alors que la source a seulement
constaté un réglage manquant.

Une trace sert à **trouver une faute dans le code** : elle dit par quelles fonctions l'erreur est
passée. Pour un échec prévu (le réseau tombe, une page est refusée, un dossier manque), le message
suffit, et la trace n'est que du bruit. Pour un bug, en revanche, elle est indispensable.

Décisions de Sabine du 2026-10-29 :
- **choix (1)** : une famille d'erreurs prévues, plus les erreurs réseau, s'écrit sans trace ;
  toute autre erreur garde la sienne ;
- **choix (a)** : une classe nommée pour les refus voulus d'une page.

## Le comment

### 1. Deux classes : une famille, et le refus d'une page

`src/k_b/etl/source_contract.py:24-31` :

```python
class ExpectedSourceError(Exception):
    """A failure a source meets in normal operation, whose message says all: logged without its
    traceback (etl/extract.py)."""


class PageRefusedError(ExpectedSourceError, ValueError):
    """A page refused on what it holds (conventions.md, rule 1); a ValueError still, which the
    import rejects as a page it cannot read."""
```

- **`ExpectedSourceError`, une classe parente.** Elle permet de dire « prévue » par un seul test
  `isinstance`, au lieu d'une liste de onze noms à tenir à jour. Les onze erreurs nommées des
  sources s'y rattachent : seule leur classe de base change, ni leur nom ni leur message. Ce sont
  `ClippingsFolderMissingError`, les trois `Zotero…Error`, les erreurs du coût de BigQuery
  (`DryRun…`), `GithubPausedError`, etc.
- **`PageRefusedError` hérite de deux classes.** Python les range dans un ordre fixe, le MRO
  (*method resolution order*) :
  `PageRefusedError → ExpectedSourceError → ValueError → Exception`. C'est un ordre valide,
  puisque les deux parentes descendent toutes deux d'`Exception`.
- **Pourquoi rester un `ValueError`.** L'import relit les mêmes pages avec les mêmes lecteurs, et
  il rejette une page illisible en rattrapant `ValueError` (`src/k_b/etl/raw_reading.py:128`).
  Si `PageRefusedError` n'en était pas un, l'import s'arrêterait sur une page qu'il rejette
  aujourd'hui proprement.

### 2. Trier les `ValueError` : refus voulu ou faute

Les sources lèvent `ValueError` dans deux cas qu'on ne distinguait pas :
- **un refus voulu de la page reçue.** `incomplete search results, refused`, `120 papers found,
  only 100 returned`, `response larger than …`, `all_items_invalid`, `empty_catalog`… Ces cas
  deviennent `raise PageRefusedError(`.
- **un bug, un réglage faux ou un état faux.** Un segment de chemin non sûr, un dernier jour de
  collecte après aujourd'hui, une URL hors de son préfixe de confiance (construite par K-B), ou un
  `int('x')` dans un lecteur. Ces cas restent `ValueError` et gardent leur trace.

Le critère de conversion : le refus porte sur **la donnée reçue**, et il remonte de `fetch` jusqu'à
la collecte. Les refus d'**une entrée** ne changent pas : `read_each_entry` les rattrape déjà et en
fait des rejets (règle 1). Un sous-agent a relu ce classement site par site, en suivant les appels
depuis chaque `fetch`.

**Un cas particulier.** Un classement refuse sa page entière : les dix refus de `most_starred.py`
et les neuf de `most_forked.py` sont tous convertis. Mais la date `created_at` est lue par
`items.parse_aware_datetime`, qui lève un `ValueError` simple. Or `items.py` ne peut pas importer
`source_contract.py`, qui importe déjà `items` : ce serait un import circulaire. Le refus est donc
rattrapé dans la source, `src/k_b/etl/sources/github/most_starred.py:106-112` :

```python
    try:
        created_at = parse_aware_datetime(
            item.get("created_at"), f"repository {rank}: created_at"
        )
    except ValueError as error:
        # Raised by items.py, which cannot import the contract of the sources.
        raise PageRefusedError(str(error)) from None
```

### 3. La ligne d'échec : la trace selon la famille

`src/k_b/etl/extract.py:28` et `:65-72` :

```python
EXPECTED_SOURCE_ERRORS = (ExpectedSourceError, URLError, ConnectionError, TimeoutError)
...
            logger.error(
                "collection failed for source %r: %s %s%s",
                ...
                exc_info=not isinstance(error, EXPECTED_SOURCE_ERRORS),
            )
```

- **De `logger.exception` à `logger.error`.** `logger.exception(…)` est un `logger.error(…)` qui
  ajoute toujours la trace. Avec `logger.error(…, exc_info=…)`, on choisit au cas par cas : la
  trace est écrite si `exc_info` est vrai.
- **Un piège dans les tests.** Avec `exc_info=False`, l'enregistrement garde `False`, pas `None`.
  Les tests vérifient donc `assert not record.exc_info`, et non `is None`.
- **Les erreurs réseau, des classes de la bibliothèque standard :**
  - `URLError` couvre `HTTPError` (un statut HTTP refusé, 4xx compris) et ce que `urlopen` emballe
    (DNS, connexion, TLS) ;
  - `ConnectionError` couvre `RemoteDisconnected` (connexion coupée avant la réponse) ;
  - `TimeoutError` est le même objet que `socket.timeout` depuis Python 3.10.
- **Le reste ne bouge pas.** Une erreur imprévue garde sa trace, et le bilan
  (`failed (<type>)`), le code de sortie et la date de dernière collecte ne changent pas.

### 4. Sans trace, la ligne est la seule copie du message : 300 caractères

La règle 3 de `conventions.md` veut qu'une valeur citée au journal soit échappée et coupée à une
longueur fixe, par une seule fonction, `quote_value`. Avant cette PR, la coupe à 100 caractères
ne faisait rien perdre : la dernière ligne de la trace répétait le message en entier. Sans trace,
la ligne datée en est la seule copie. Le message de Zotero, qui va jusqu'à 200 caractères, était
coupé en son milieu.

La revue de code l'a relevé. La correction, `src/k_b/core/quoting.py:15-18` :

```python
def quote_value(value: object, max_length: int = MAX_QUOTED_VALUE_LENGTH) -> str:
    ...
    return repr(value)[:max_length]
```

La ligne d'échec cite son message et ses notes avec `MAX_QUOTED_FAILURE_LENGTH = 300`
(`extract.py:32`). C'est toujours une seule fonction, et la longueur reste bornée : un test le
vérifie.

### 5. Le remède dans le message de clipping

Le message dit maintenant quoi faire : `…no Clippings folder in the vault of KB_VAULT_DIR; create
it, or check KB_VAULT_DIR` (`clipping.py:102`).

Le premier essai réel l'a montré coupé à `…or check KB_`, à cause de la limite de 100. Une première
correction a raccourci le message (`c214000`). Une fois la coupe passée à 300, il a retrouvé ses
premiers mots (`63665e1`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Les erreurs prévues sans trace, les autres avec (choix (1) de Sabine) | Le message suffit pour un échec attendu ; la trace sert à trouver une faute | La trace seulement dans `kb.log` (choix (2)) : non retenue par Sabine |
| `PageRefusedError` pour les refus voulus (choix (a)) | Un bug dans un lecteur garde sa trace | (b) Compter tout `ValueError` comme prévu : un `int('x')` perdrait sa trace |
| Convertir site par site | Le tri reste explicite | Convertir tout `ValueError` levé pendant `fetch` (proposé par la revue) : même défaut que (b) |
| `PageRefusedError` reste un `ValueError` | L'import le rattrape, comme les tests qui attendent un `ValueError` | Une classe indépendante : l'import s'arrêterait sur une page qu'il rejette aujourd'hui |
| `created_at` rattrapé dans la source | `items.py` ne peut pas importer le contrat (cycle) | Convertir dans `items.py` : import circulaire |
| Coupe à 300 sur la ligne d'échec, par un paramètre de `quote_value` | Sans trace, la ligne est la seule copie ; une seule fonction (règle 3) | Garder 100 : la fin des messages longs est perdue. Supprimer la coupe : une ligne pourrait grossir sans limite |
| Pas de `/security-review` | `http_download.py` ne change que de classe d'erreur : rien de ce qui est accepté ou refusé ne bouge | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_expected_failure_is_logged_on_its_line_without_its_traceback` (`tests/etl/test_extract.py:64`), paramétré sur les 5 classes du tuple | Une erreur prévue ne porte pas de trace, et sa ligne garde son texte |
| `test_an_unexpected_failure_is_logged_with_its_traceback` (`:114`), `ValueError` et `KeyError` | Une erreur imprévue garde sa trace |
| `test_an_expected_failure_is_logged_with_its_long_message_and_notes_whole` (`:80`) et `test_a_failure_message_longer_than_the_cut_is_cut_on_its_line` (`:96`) | Un message de 250 caractères arrive entier ; un de 500 est coupé à 300 |
| `test_each_named_failure_of_a_source_is_an_expected_one` (`tests/etl/test_source_contract.py:133`) | Les 11 erreurs nommées sont dans la famille |
| `test_collect_shows_the_traceback_of_an_unexpected_failure_only` (`tests/commands/test_collect_command.py:64`) | De bout en bout, par `kb collect` : une seule trace, celle de la faute |
| 44 `pytest.raises(ValueError…)` passés à `PageRefusedError`, dans 10 fichiers, plus le faux refus de `test_tldr.py` | Chaque refus converti est tenu par un test |
| 10 mutations, toutes attrapées | Les tests échouent si on remet `exc_info=True` ou `False`, si on retire `TimeoutError` du tuple, un refus remis en `ValueError` (un classement, tldr), `created_at` non rattrapé, la classe de base de clipping, ou la coupe à 100 ou sans limite |
| Essai réel, `KB_COLLECT_ONLY=clipping` sur un coffre sans `Clippings` | La ligne ERROR avec le remède, aucune trace, bilan `clipping: failed (ClippingsFolderMissingError)`, code 1 |
| `uv run pytest` (2 782 verts), `ruff check`, `ruff format --check`, `mypy --strict` | Les contrôles du dépôt passent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas tout écrire sans trace ?** Parce que la trace est le seul moyen de trouver la
   ligne d'un bug. Un `ValueError` levé par un `int('x')` dans un lecteur doit la garder : c'est
   pour ça qu'on a une classe nommée plutôt qu'un « tout `ValueError` est prévu »
   (`extract.py:28`).
2. **Pourquoi `PageRefusedError` hérite-t-elle de `ValueError` ?** Parce que l'import relit les
   mêmes pages et rejette une page illisible en rattrapant `ValueError` (`raw_reading.py:128`).
   Sans cet héritage, une page refusée arrêterait l'import au lieu d'être rejetée.
3. **Un 404 de GitHub dû à une URL fausse perd sa trace : est-ce un problème ?** C'est une limite
   assumée. Un statut HTTP est la réponse observée du serveur, et la ligne nomme la source, dont
   chacune n'a qu'une sorte de requête.
4. **Le journal peut-il grossir sans limite maintenant qu'on coupe à 300 ?** Non. Chaque valeur
   reste coupée (`quote_value`, testé à 500 → 300). Le nombre de notes dépend de la fenêtre de
   tldr, comme avant, et la trace d'avant les répétait déjà en entier.
5. **Le journal de collecte part-il chez Grafana Cloud ?** Non. Seule l'API IA y envoie traces,
   métriques et journaux. La collecte écrit sur la sortie d'erreur et dans `logs/kb.log` : la
   ligne est la seule copie, d'où la coupe à 300.

## Zones non vérifiées

- **Un délai de BigQuery** : `job.result` lève un `TimeoutError` souvent sans message. C'est lu
  dans le code de la bibliothèque, jamais vu en vrai. La ligne dirait `TimeoutError ''`.
- **`ssl.SSLError` et `IncompleteRead` pendant la lecture d'une réponse** : déduit des classes
  (ce ne sont ni des `URLError` ni des `ConnectionError`), jamais observé. Ces erreurs gardent leur
  trace.
- **Les 252 caractères du message de Zotero** : mesurés avec un problème fait de `x`, pas avec un
  vrai problème de `integrity_check`. Des caractères de contrôle, échappés deux fois, peuvent
  dépasser 300.
- **Le classement des refus** : il repose sur la lecture des chemins d'appel (par moi et par un
  sous-agent). Aucun test ne fait la liste des sites qui peuvent lever.
- **La destination de la sortie d'erreur sur Azure Container Apps** : pas encore vérifiée.

## Ce qui reste

- **Gardent leur trace, volontairement** (à rouvrir si l'un apparaît en vrai) :
  - `JSONDecodeError` dans les lecteurs GitHub, `UnicodeDecodeError` et `csv.Error` dans celui de
    CISA ;
  - les erreurs de BigQuery et de google-auth ;
  - les `OSError` hors réseau (coffre, `zotero.sqlite` absent, écriture de `raw/`) ;
  - l'état de collecte non écrit (`extract.py`) et l'exception non traitée (`cli.py`).
- **Effet visible, voulu** : le type affiché d'un refus de page devient `PageRefusedError` à quatre
  endroits : la ligne de journal, le bilan, `import-log.jsonl` et le journal de `kb write-tops`.
- **Tri des deux revues de code** :
  - **première revue, 10 constats** : 3 corrigés (la coupe à 300, une référence de ligne, la
    définition d'une erreur réseau) ; 7 écartés, déjà dans « Non fait », voulus, contraires au
    choix (a) ou présents avant la PR ;
  - **seconde revue, 9 constats** : 3 corrigés (le test de la coupe, deux commentaires) ; 6
    écartés.

  Le détail des deux tris est dans le commentaire de la PR.
