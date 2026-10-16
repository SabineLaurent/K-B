# Écarter une entrée invalide d'une source et la tracer au journal d'import

- **Date** : 2026-10-16
- **Branche** : `fix/reject-invalid-source-entries`
- **Issue** : #61 (regroupe #77, ligne invalide du catalogue CISA)
- **Fichiers principaux** : `src/k_b/etl/source_contract.py`, `src/k_b/etl/transform.py`,
  `src/k_b/etl/sources/{github_releases,github_advisories,cisa_kev,arxiv}.py`
- **Série** : suite de [Lire le brut en items communs](2026-10-05-lire-le-brut-en-items-communs.md)
  (le chemin `reject` vers le journal d'import y est né).

## Le pourquoi

K-B collecte des sources qu'il ne contrôle pas. Avant cette PR, trois lecteurs (releases GitHub,
alertes GitHub, catalogue CISA) construisaient leur liste d'un bloc et levaient au premier élément
invalide. Une seule release mal formée faisait échouer la source **à chaque collecte**, puisque
sa date de dernière collecte n'avançait plus et que la même page revenait. À l'import, la page
entière était rejetée, entrées valides comprises. arXiv faisait l'inverse : il écartait l'entrée
par un `logger.warning`, sans aucune trace dans le journal d'import.

La revue d'homogénéité du 11/10 (famille 1) a relevé ces trois façons de faire. Sabine en a
retenu une seule, devenue la règle 1 de `.claude/rules/conventions.md` :

- un lecteur ne lève que pour une **page illisible** ;
- une **entrée** invalide devient un rejet nommé, rendu avec les entrées lues, et suit le seul
  chemin `reject` jusqu'au journal d'import ;
- à la collecte, une source n'échoue que si sa page est illisible ou si **toutes** ses entrées
  sont invalides (`all_items_invalid`).

Cette PR applique la règle aux quatre sources concernées. C'est la demande n° 2 de la revue certif
du 04/10, pour le pipeline de données (E1).

## Le comment

### 1. Le contrat d'un lecteur rend aussi ses rejets

Le contrat `SourceReader` disait qu'un lecteur rend une suite d'entrées. Un rejet ne pouvait donc
sortir du lecteur que par une exception (toute la page tombe) ou par un journal (aucune trace au
journal d'import). Le contrat rend maintenant les deux listes ensemble :

```python
# src/k_b/etl/source_contract.py:31
class EntryReading[EntryT](NamedTuple):
    """The entries of a raw file read, and the reason each invalid one was rejected."""

    entries: list[EntryT]
    # Each one names its entry (position or line, identifier once read) and its field.
    rejection_reasons: list[str]
```

`read_entries` est désormais typé `Callable[[bytes], EntryReading[EntryT]]`
(`source_contract.py:83`). `EntryReading` est un `NamedTuple` générique, comme `SourceReader`
juste en dessous : mypy `--strict` vérifie qu'un lecteur de releases rend bien des `Release`.
TLDR et Zotero valident déjà leurs entrées à `convert` (par l'`Item`). Ils rendent
`EntryReading(entrées, [])`, sans rejet de lecteur.

### 2. Une seule boucle de lecture, qui ne garde que `parse`

Les quatre lecteurs faisaient la même chose : pour chaque entrée, la valider, et en cas d'erreur…
lever ou journaliser. La boucle est écrite une fois :

```python
# src/k_b/etl/source_contract.py:51
    for number, raw_entry in numbered_entries:
        try:
            entry = parse(raw_entry, number)
        except ValueError as error:
            rejection_reasons.append(str(error))
            continue
        entries.append(entry)
```

Deux détails comptent :

- **Le `try` n'entoure que `parse`, pas l'itération.** Pour CISA, `numbered_entries` est un
  générateur sur un `csv.DictReader`. Si le module `csv` ne sait pas découper la page (un octet
  NUL), il lève `csv.Error` pendant l'itération. Cette erreur traverse la boucle et la page reste
  illisible. Le test `test_an_error_while_listing_the_entries_is_not_a_rejection` le prouve.
- **Le numéro est donné par l'appelant.** arXiv et GitHub passent `enumerate(entries)`, la
  position. CISA passe le numéro de ligne :

```python
# src/k_b/etl/sources/cisa_kev.py:122
    # line_num is read once its row is: the line the row ends on.
    reading = read_each_entry(
        ((rows.line_num, row) for row in rows), parse_vulnerability
    )
```

Le générateur lit `rows.line_num` après que `DictReader` a rendu la ligne. Selon la
documentation, c'est « le nombre de lignes lues dans l'itérateur source ». Pour une ligne CSV
écrite sur plusieurs lignes physiques, c'est donc la dernière.

### 3. Un rejet dit où, qui et quoi

Chaque fonction `parse_*` construit un libellé qui s'enrichit à mesure que l'entrée est lue : la
position, puis l'identifiant **une fois validé**.

```python
# src/k_b/etl/sources/cisa_kev.py:150
    # From here on, named by its CVE identifier too: it is read.
    label = f"line {line_number} ({quote_value(cve_id)})"
```

Le motif d'une ligne CISA invalide devient par exemple
`line 3 ('CVE-2026-88772'): invalid dateAdded: '27/09/2026'`. On y lit la ligne, l'identifiant,
le champ en cause et la valeur observée. Toute valeur citée passe par `quote_value`
(`core/quoting.py`), qui l'échappe par `repr` et la coupe à 100 caractères. C'est la règle 3 de
`conventions.md`, retenue par Sabine (Q1). Un auteur, un titre ou un résumé n'est jamais cité : le
motif d'un papier sans auteur dit `no author`, sans nom.

CISA vérifie aussi `knownRansomwareCampaignUse` dès la lecture (`cisa_kev.py:158`). Une valeur
hors de `Known` ou `Unknown` était refusée seulement à `convert`, sans numéro de ligne ni `cveID`.
La garde `is_ransomware_use` (`cisa_kev.py:174`) est typée `TypeIs[RansomwareUse]` : après le
`if`, mypy sait que la valeur est du bon type, et le `cast` d'avant disparaît.

### 4. Le rejet suit le chemin `reject` jusqu'au journal d'import

```python
# src/k_b/etl/transform.py:143
    rejections = [
        reject(raw_file_path, reason) for reason in entry_reading.rejection_reasons
    ]
```

`reject` (`transform.py:216`) journalise le rejet et le rend comme `Rejection(raw_file_path,
reason)`. Les `Rejection` sont écrites dans `import-log-<AAAA-MM-JJTHHMMSSZ>.jsonl` par l'import,
si l'écriture en base réussit. Ce chemin était déjà celui des rejets de `convert`. Le chemin du
brut nomme la source (`github_releases_<dépôt>`, `github_advisories_pip`), d'où « le dépôt » du
critère (Q2).

Ces rejets comptent dans `rejection_count` (`RawFile`). Un catalogue CISA ou un extrait Zotero
qui a un rejet ne retire donc aucune ligne de la base (`load.py:259`, `:280`, règle de #106) : une
ligne rejetée est dans le catalogue, pas absente.

### 5. À la collecte : `all_items_invalid`

```python
# src/k_b/etl/source_contract.py:65
    if reading.rejection_reasons and not reading.entries:
        raise ValueError(
            f"all_items_invalid: {len(reading.rejection_reasons)} entries, all rejected; "
            f"first: {reading.rejection_reasons[0]}"
        )
```

Les quatre `fetch` appellent `check_not_all_invalid` après la lecture. Si elle lève, la source
échoue comme n'importe quelle source qui lève. `extract.py` journalise une fois l'échec, ne met pas
la date à jour et n'écrit rien dans `raw/`. Une page **sans** entrée n'est pas refusée : elle n'a
aucune entrée invalide. Une entrée invalide parmi des valides ne fait pas échouer la collecte : le
brut est écrit tel quel, et le rejet a lieu à l'import.

Deux sources ont un cas particulier, tranché par Sabine (Q3) :

- **Alertes** : une page qui porte une alerte rejetée est écrite même sans alerte valide nouvelle
  (`github_advisories.py:82`). Le filtre `reviewed>=` fait sortir l'alerte de la fenêtre quand la
  date avance ; sans cela, son rejet n'atteindrait jamais le journal d'import.
- **Releases** : le comportement est gardé. La page des 100 dernières releases change peu, et
  l'écrire chaque jour irait contre la collecte incrémentale. La limite est écrite dans
  `docs/specs-collecte.md`.

L'avertissement « page pleine, pages suivantes non lues » compte toutes les entrées, rejetées
comprises (`github_releases.py:82`, `github_advisories.py:86`). Sinon, une page de 100 entrées
dont une est rejetée ne préviendrait plus.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Où valider | Le lecteur valide et rend ses rejets : la collecte vérifie ce qu'elle écrit (option A de la revue du 11/10, décision de Sabine). | Valider seulement à `convert` : la collecte n'aurait plus rien vérifié (option B, écartée par Sabine). |
| Forme d'un rejet de lecteur | Une chaîne : `reject` y ajoute le chemin du brut. | Un type `EntryRejection` à un seul champ, sans second usage (`code.md`, simplicité). |
| La boucle | Une fonction commune pour quatre lecteurs (`code.md`, factoriser dès la 3e occurrence). | Une boucle par source : quatre copies. |
| L'état `all_items_invalid` | Une `ValueError` dont le message commence par l'état ; le test le vérifie par `match=`. | Une classe d'exception : aucun appelant ne la distingue (constat 10 de l'architecte). Rendre `None` : la date avancerait sans trace. |
| La valeur observée dans le motif (Q1) | Citée par `quote_value` (règle 3 de `conventions.md`, Sabine). | Ne jamais la citer : la règle 3 l'a écartée (« perd la longueur, le maximum et l'URL observée »). La phrase de la mission qui le demandait était une erreur, reconnue par time-knight. |
| Identifiant d'une alerte (Q2) | Son GHSA s'il est lisible ; le chemin du brut nomme l'écosystème. | Ajouter les paquets : la liste des paquets est elle-même un champ qui peut être invalide. |
| Page à entrée rejetée sans entrée valide nouvelle (Q3) | Alertes : écrite ; releases : non, limite écrite. | Écrire les deux : un brut par jour pour les releases. |
| Position d'un rejet à `convert` | `read entry N`, position parmi les entrées lues (le mot dit ce qu'elle compte). | Garder la position brute avec chaque entrée : change `EntryReading` et la signature de `convert` pour toutes les sources. |
| Filtre par date de `read_new_vulnerabilities` | Gardé et adapté : la PR ne touche pas au code voisin qui marche. | Le retirer (constat 9 de l'architecte) : code mort en production, mais hors de la demande. Signalé sans issue. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_an_entry_refused_by_its_parser_is_rejected_and_the_others_are_read` (`tests/etl/test_source_contract.py`) | La boucle commune rejette une entrée et lit les autres. |
| `test_an_error_while_listing_the_entries_is_not_a_rejection` | Une `csv.Error` d'itération reste une page illisible. |
| `test_an_invalid_release_is_rejected_with_its_id_and_field_and_the_others_are_read`, et son pendant pour les alertes, CISA (`..._with_its_line_cve_and_field_...`) et arXiv (`test_a_rejected_entry_does_not_hide_the_valid_ones`) | Par source : une entrée invalide parmi des valides donne les valides, et un motif avec position ou ligne, identifiant et champ. |
| `test_a_page_with_an_invalid_release_is_collected` (et alertes, CISA, arXiv) | La collecte réussit et rend le brut tel quel. |
| `test_a_page_whose_releases_are_all_invalid_fails_the_collection` (et alertes, CISA, arXiv) | Toutes invalides : `all_items_invalid`. |
| `test_a_source_whose_entries_are_all_invalid_writes_no_raw_and_keeps_its_date` (`tests/etl/test_extract.py`) | Avec le vrai `CisaKevSource` : rien dans `raw/`, date inchangée, une seule ligne d'erreur. |
| `test_an_entry_rejected_by_its_reader_is_rejected_and_counted_with_its_file` (`tests/etl/test_transform.py`) | Le rejet du lecteur devient une `Rejection` ; `rejection_count` compte les deux sortes. |
| `test_an_invalid_release_is_written_to_the_log_and_the_others_are_imported` (`tests/etl/test_load.py`) | Le rejet arrive dans `import-log-*.jsonl`. |
| `test_a_page_with_an_invalid_advisory_is_collected_even_without_a_new_valid_one` | Q3, alertes. |
| `test_a_full_page_counts_its_rejected_releases` (et alertes) | L'avertissement de page pleine compte les rejetées. |
| `test_an_entry_with_a_missing_or_invalid_field_is_rejected_with_its_arxiv_id` | Le nom d'un auteur n'apparaît pas dans le motif. |
| `grep -n "logger.warning" src/k_b/etl/sources/*.py` → `github_advisories.py:90`, `github_releases.py:86` | Plus aucun rejet d'entrée par `logger.warning` ; restent les deux avertissements de page pleine. |
| `uv run pytest` → 1491 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt passent. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas tout valider à l'import, puisque l'import rejette déjà ?** Parce que la
   collecte doit vérifier ce qu'elle écrit : une page de maintenance n'est pas stockée comme un
   catalogue. Le lecteur sert aux deux étapes : `fetch` l'appelle avant d'écrire, l'import
   l'appelle pour lire (`source_contract.py:83`).
2. **Que se passe-t-il si toutes les entrées sont invalides ?** La source échoue avec
   `all_items_invalid`, sa date ne bouge pas et rien n'est écrit (`source_contract.py:65`, test
   d'`extract`). Limite assumée : si la fenêtre ne contient qu'une entrée invalide (petit
   écosystème d'alertes, semaine creuse d'arXiv), la source échoue à chaque collecte jusqu'à
   l'arrivée d'une entrée valide. C'est la lettre de la règle 1, écrite dans
   `docs/specs-collecte.md`.
3. **Où est la protection des données personnelles dans les rejets ?** Les motifs ne citent que
   des positions, des identifiants validés, des noms de champ et des valeurs passées par
   `quote_value` ; jamais un auteur ni un texte. La `/security-review` n'a rien trouvé. Reste la
   `ValidationError` de `convert`, citée par `{error}` (`transform.py:154`) : elle est sur `main`
   avant cette PR, et elle est traitée par #212.
4. **Pourquoi le `try` de la boucle n'entoure-t-il que `parse` ?** Une erreur d'itération signifie
   que la page ne se découpe pas en entrées : c'est une page illisible, qui doit rester rejetée
   entière (`source_contract.py:51-56`).
5. **Une ligne CISA rejetée bloque-t-elle les retraits ?** Oui, tant qu'elle reste dans le
   catalogue (`load.py:259`, règle de #106). Ce n'est pas une régression : avant la PR, la même
   ligne faisait échouer toute la collecte CISA. Une suite possible, retirer sauf les `cveID`
   rejetés, a été remontée à Sabine.

## Zones non vérifiées

- `line_num` pour une ligne CSV écrite sur plusieurs lignes physiques : il vaut la dernière ligne
  physique, d'après la documentation. Aucun test ne le vérifie : la fixture n'a pas de ligne de ce
  genre.
- Les erreurs autres que `ValueError` dans une fonction `parse_*` (un `TypeError` sur une forme
  inattendue) traversent la boucle et rendent la page illisible. Ce n'est pas testé : aucun cas
  connu.
- Le comportement de l'API GitHub avec une alerte invalide réelle n'a pas été observé : les
  entrées invalides des tests sont fabriquées à partir des fixtures enregistrées.

## Ce qui reste

- #212 : la `ValidationError` d'un rejet à `convert` cite encore `input_value=`.
- #136 : rejeter l'item que la base refuse, par un `SAVEPOINT`, sans arrêter l'import.
- Signalés sans issue (tri de time-knight) :
  - la position brute d'un rejet à `convert` ;
  - la validation de l'`Item` dès la collecte ;
  - le format des motifs du journal d'import (type d'erreur en tête ou non) ;
  - l'analyse du flux arXiv faite trois fois ;
  - le filtre par date mort de `read_new_vulnerabilities` ;
  - la tension entre la lettre de la règle 1 et son « Pourquoi » quand la fenêtre ne contient
    qu'une entrée invalide.
- Remonté à Sabine : retirer les vulnérabilités d'un catalogue CISA sauf les `cveID` rejetés.

## Sources

- Documentation Python 3.13, module `csv`, attribut `csvreader.line_num` :
  https://docs.python.org/3.13/library/csv.html (par Context7, consultée le 2026-10-16).
- Documentation Python 3.13, module `typing`, `TypeIs` et `get_args` :
  https://docs.python.org/3.13/library/typing.html (par Context7, consultée le 2026-10-16).
- `.claude/rules/conventions.md`, règles 1 et 3 ; `docs/2026-10-11-revue-homogeneite.md`,
  famille 1 (décision de Sabine).
