# La commande `kb collect` : un squelette de collecte qui ne perd rien

- **Date** : 2026-09-30
- **Branche** : `feat/collect-command` (commit `8720ff4`)
- **Issue** : #9 « Lancer toutes les collectes d'une seule commande »
- **Fichiers principaux** : `src/k_b/raw_store.py`, `src/k_b/collect.py`, `src/k_b/cli.py`, et
  leurs tests `tests/test_raw_store.py`, `tests/test_collect.py`, `tests/test_cli.py`.
- **Autres fichiers** : `pyproject.toml` déclare la commande `kb`. `MEMORY.md` reçoit une consigne
  de travail (expliquer le code à Sabine) qui ne touche pas au code et n'est pas traitée ici.

## Le pourquoi

K-B doit collecter plusieurs sources (CISA KEV, GitHub, arXiv, TLDR…). Chacune peut tomber en
panne : un site indisponible, un format qui change. La collecte doit donc réunir trois propriétés :

1. **Une panne ne bloque pas les autres sources.**
2. **Rien ne se perd.** Une panne aujourd'hui ne doit pas créer un trou définitif dans la veille.
   C'est le bug relevé dans brief09 : un curseur qui avance malgré une erreur saute par-dessus la
   période manquée.
3. **Le brut est gardé tel quel**, daté, pour pouvoir rejouer le traitement plus tard sans
   recollecter.

Ce travail pose le squelette : la commande, le stockage du brut et l'état de collecte. Aucune
vraie source n'existe encore : la première sera CISA KEV (#23). Les tests utilisent des sources
factices.

## Le comment

Trois modules, un par responsabilité, qui s'appellent dans un seul sens :
`cli` (présentation) → `collect` (logique) → `raw_store` (fichiers).

### 1. Le contrat commun à toutes les sources

`src/k_b/collect.py:16-22` : une source est un objet qui a un `name`, une `extension` et une
méthode `fetch(last_collected_at)` qui renvoie le brut en octets.

```python
class Source(Protocol):
    name: str
    extension: str

    def fetch(self, last_collected_at: datetime | None) -> bytes:
```

Un `Protocol` décrit une forme sans imposer d'héritage : `WorkingSource` et `BrokenSource`, dans
les tests, n'héritent de rien et satisfont pourtant le contrat. La source reçoit la date de sa
dernière collecte réussie (`None` la première fois) et décide seule de ce qu'elle en fait : un
filtre sur `dateAdded` pour CISA KEV, un paramètre de requête pour une API. Elle renvoie des
`bytes` et non des objets, parce que ce qui est stocké est le brut exact, avant toute
interprétation.

### 2. Le curseur par source, qui n'avance que sur un succès

`src/k_b/collect.py:36-45`, le cœur du module :

```python
    for source in sources:
        try:
            collect_one_source(source, raw_dir, now, last_collection_dates.get(source.name))
        except Exception as error:
            logger.exception("collection failed for source %r", source.name)
            errors_by_source[source.name] = error
        else:
            last_collection_dates[source.name] = now
            errors_by_source[source.name] = None
    save_last_collection_dates(raw_dir, last_collection_dates)
```

- **Isolation des pannes** : le `try` enveloppe une seule source. Une exception, quelle qu'elle
  soit, est journalisée puis gardée, et la boucle passe à la source suivante.
- **Curseur qui n'avance que sur un succès** : `last_collection_dates[source.name] = now` est dans
  le `else`, qui ne s'exécute que si le `try` n'a rien levé. Une source en échec garde son ancien
  curseur. Au prochain passage, elle redemande tout depuis sa dernière collecte réussie : le trou
  se comble tout seul.
- **Un curseur par source**, et non un curseur global : un dictionnaire indexé par `source.name`.
- **L'état est sauvegardé une seule fois, à la fin**, après toutes les sources.

La fonction renvoie `{nom de source: erreur ou None}` au lieu d'afficher quoi que ce soit : c'est
à la ligne de commande de présenter le résultat.

### 3. Le brut immuable, écrit de façon atomique

`src/k_b/raw_store.py:12-28` : deux fonctions empilées.

```python
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary_file:
        temporary_file.write(content)
    try:
        os.replace(temporary_file.name, path)
```

- **Écriture atomique.** On écrit dans un fichier temporaire, puis `os.replace` le renomme vers
  son nom final. Un renommage à l'intérieur d'un même système de fichiers est atomique : le
  fichier final est soit absent, soit complet, jamais à moitié écrit, même si le programme est tué
  en cours de route. Le temporaire est créé **dans le même dossier** (`dir=path.parent`) pour
  garantir qu'il est sur le même disque.
- **Immuabilité.** `write_new_raw_file` (`raw_store.py:26-27`) refuse d'écrire si le fichier
  existe déjà. Un brut n'est jamais remplacé.

Le chemin du brut est construit dans `src/k_b/collect.py:56-57` :
`raw/automation/<nom>/2026-09-30T100000Z.<extension>`. Le `Z` signifie UTC, sans les `:` de
l'ISO 8601, qui posent problème dans les noms de fichiers sur certains systèmes.

### 4. L'état de collecte validé à la lecture

L'état est un fichier JSON, `raw/collection_state.json` :
`{"working": "2026-09-30T10:00:00+00:00"}`. Il vient de l'extérieur du programme : on peut
l'éditer à la main, le corrompre, le remplir d'une date sans fuseau. Il est donc validé dès sa
lecture (`src/k_b/raw_store.py:53-60`) :

```python
    parsed_date = datetime.fromisoformat(stored_date)
    if parsed_date.tzinfo is None:
        raise ValueError(f"date without a time zone: {stored_date!r}")
```

Une date **naïve** (sans fuseau) est refusée, parce qu'elle ne se compare pas correctement à une
date **aware** (avec fuseau). C'est le second défaut de brief09. Le refus arrête toute la collecte :
mieux vaut ne pas collecter que collecter à partir d'un curseur douteux (principe « échouer
fermé »).

### 5. Les chemins protégés contre les noms dangereux

`src/k_b/collect.py:52-54` : `name` et `extension` deviennent des morceaux de chemin. Ils doivent
donc correspondre à `[a-z0-9_]+`, sinon la source est refusée.

```python
    for path_segment in (source.name, source.extension):
        if not SAFE_PATH_SEGMENT.fullmatch(path_segment):
            raise ValueError(f"not a safe path segment: {path_segment!r}")
```

Sans ce contrôle, une source nommée `../../x` écrirait hors de `raw/`. `fullmatch` exige que toute
la chaîne corresponde, et pas seulement son début. La vérification a lieu **avant** `fetch` : une
source mal nommée n'est même pas interrogée.

### 6. La ligne de commande, et le dossier de données obligatoire

`src/k_b/cli.py:20-26` : `KB_DATA_DIR` doit être définie et désigner un dossier existant, sinon le
programme s'arrête avec le code 2.

```python
    data_dir = os.environ.get(DATA_DIR_VARIABLE)
    if not data_dir:
        print(f"error: {DATA_DIR_VARIABLE} must point to the data directory", file=sys.stderr)
        return 2
```

Les données collectées ne doivent jamais se retrouver dans le dépôt de code, qui est public
(`MEMORY.md`). Sans valeur par défaut, impossible de les y écrire par accident. Le contrôle
« dossier existant » protège d'une faute de frappe dans le chemin, qui créerait sinon une
arborescence au mauvais endroit.

Codes de sortie (`cli.py:34-35`) : 0 si tout a réussi, 1 si au moins une source a échoué, 2 si la
configuration est invalide. Un futur planificateur pourra ainsi détecter une collecte partielle.
L'affichage ne montre que le type d'erreur (`failed (ConnectionError)`) ; le détail complet va
dans le journal.

## Choix faits et options écartées

| Choix retenu | Alternative écartée | Raison |
|---|---|---|
| `KB_DATA_DIR` obligatoire | Valeur par défaut `~/K-B-data`, ou option `--data-dir` | **Décision de Sabine.** Aucune écriture possible sans configuration explicite. |
| Curseur = heure de la collecte réussie (`now`) | Curseur = date la plus récente trouvée dans les données (`MAX(date)`, comme brief09) | `MAX(date)` saute les trous après un échec partiel. `now` est connu sans lire les données. |
| Curseur par source | Curseur global | Bug avéré de brief09 : un sujet en avance fait sauter les éléments d'un autre. |
| Brut en `bytes`, un fichier par exécution | Stocker des objets déjà analysés, ou écraser le dernier fichier | `raw/` immuable (veille de l'existant) : on garde la preuve et on peut rejouer. |
| `Protocol` | Classe de base abstraite (`ABC`) | Pas d'héritage imposé. La consigne `.claude/rules/code.md` autorise l'abstraction, car deux implémentations existent (dans les tests). |
| Trois modules | Tout dans `collect.py` | Consigne SoC de `.claude/rules/code.md` : fichiers, logique et présentation séparés. |
| Bibliothèque standard seule (`argparse`, `json`, `tempfile`) | Click, Typer, Pydantic | Aucune dépendance nouvelle pour un squelette. La mission interdit de toucher aux dépendances. |
| Vérification d'existence avant l'écriture | Verrou de fichier | Pas de collectes simultanées prévues pour l'instant (YAGNI). Voir « Zones non vérifiées ». |
| Reportés à #23 : timeout, User-Agent, ETag/304, date de publication | Les coder maintenant | Ils n'ont de sens qu'avec une vraie source HTTP. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_broken_source_does_not_stop_the_others` | Le critère de l'issue : la source en panne n'empêche pas l'autre d'écrire son brut au bon chemin. |
| `test_only_successful_sources_advance_their_last_collection_date` | Seule la source réussie a un curseur dans l'état. |
| `test_a_source_receives_its_last_successful_collection_date` | 1ʳᵉ collecte : `fetch` reçoit `None`. 2ᵉ collecte : il reçoit la date de la 1ʳᵉ. |
| `test_a_second_run_at_the_same_instant_fails_without_overwriting` | Deux collectes au même instant : la 2ᵉ échoue, rien n'est écrasé. |
| `test_write_new_raw_file_refuses_to_overwrite` | Le premier contenu reste intact après une tentative d'écrasement. |
| `test_a_source_name_that_is_not_a_safe_path_segment_is_refused` | `../escape` est refusé, rien n'est écrit. |
| `test_last_collection_dates_round_trip_as_utc_aware_datetimes` | Une date sauvegardée se relit identique, avec son fuseau. |
| `test_invalid_collection_state_is_refused` (4 cas) | Date naïve, texte, nombre, liste : tous refusés par `ValueError`. |
| `test_collect_refuses_to_run_without_a_data_directory`, `..._that_does_not_exist` | Code 2 sans configuration valide. |
| `test_collect_reports_a_failure_but_still_stores_the_other_sources` | Le chemin complet par la commande : code 1 et le brut de la source réussie écrit. |
| `uv run pytest` | 16 tests passent. |
| `kb collect` avec une source factice en panne (lancé à la main) | Affiche `broken: failed (ConnectionError)`, code 1. La trace complète part sur stderr alors que `logging` n'est pas configuré : c'est son gestionnaire de secours qui l'affiche. |
| `ls -l raw/` après une collecte | `collection_state.json` est en `-rw-------` : `NamedTemporaryFile` crée en `0600`, et le renommage garde ces droits. Les fichiers ne sont lisibles que par leur propriétaire. |
| `KB_DATA_DIR=<dossier> uv run kb collect` | Affiche `no source registered`, code 0, crée `raw/collection_state.json` contenant `{}`. |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi le curseur ne prend-il pas la date du document le plus récent ? »** Parce qu'après
   un échec, cette date peut être plus récente que ce qui manque, et le trou devient définitif.
   Avec l'heure de la dernière collecte **réussie**, on redemande toute la période depuis ce
   succès. Voir `collect.py:42-43`.
2. **« Que se passe-t-il si le programme plante entre l'écriture du brut et la sauvegarde de
   l'état ? »** Le brut est là, mais le curseur n'a pas avancé. La collecte suivante redemande la
   même période : on aura un **doublon**, pas un **trou**. C'est voulu, et le dédoublonnage viendra
   à la fusion. Voir `collect.py:45`.
3. **« Où est la sécurité ? »**
   - Les noms qui forment des chemins sont validés (`collect.py:52-54`).
   - L'état relu est validé et refusé en cas de doute (`raw_store.py:53-60`).
   - Les données ne peuvent pas atterrir dans le dépôt (`cli.py:20-26`).
   - Les messages affichés ne montrent que le type d'erreur (`cli.py:32`).
4. **« Pourquoi attraper `Exception`, ce qui est d'habitude déconseillé ? »** Parce qu'une source
   peut échouer de n'importe quelle façon (réseau, format, bug), et qu'aucune ne doit arrêter les
   autres. L'erreur n'est pas avalée : elle est journalisée avec sa trace, renvoyée, et elle
   produit le code de sortie 1. Voir `collect.py:39-41`.
5. **« Pourquoi un fichier temporaire, au lieu d'écrire directement ? »** Pour qu'une coupure en
   pleine écriture ne laisse jamais un fichier tronqué, qu'on prendrait ensuite pour un brut
   valide. Voir `raw_store.py:15-18`.

## Zones non vérifiées

- **Fichier temporaire orphelin.** Si `temporary_file.write(content)` échoue (disque plein), le
  fichier temporaire reste dans le dossier : le `try` ne couvre que `os.replace`
  (`raw_store.py:15-21`). Cas non testé.
- **État corrompu vu par l'utilisateur.** Un `collection_state.json` invalide arrête bien la
  collecte, mais par une exception non rattrapée dans `cli.py` : l'utilisateur voit une trace
  Python, pas un message propre. Seule la fonction de lecture est testée, pas ce chemin de bout en
  bout. Un JSON illisible lève `json.JSONDecodeError`, une sous-classe de `ValueError` : non testé
  non plus.
- **Collectes simultanées.** Entre `path.exists()` et `os.replace`, une autre collecte pourrait
  écrire le même fichier. Improbable (même seconde, même source), non protégé.
- **Windows.** L'atomicité de `os.replace` est supposée pour macOS et Linux uniquement.
- **Doublons de noms.** Deux sources de même nom partageraient le même curseur et le même dossier.
  Rien ne l'empêche.

## Ce qui reste

- **La première vraie source, CISA KEV** : #23. Elle apportera la collecte polie (timeout,
  User-Agent, ETag/304) et une limite de taille. `SOURCES` est vide jusque-là.
- **La date de publication distincte de la date de collecte** : elle concerne les items, qui
  n'existent pas encore. Elle viendra avec la fusion vers la base.
- **La surveillance des exécutions** : reportée après E1 (`MEMORY.md`).
- **L'état dans `raw/`** : provisoire, en attendant la base.
