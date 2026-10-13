# Lire l'extrait Zotero vers la base

- **Date** : 2026-10-13
- **Branche** : `feat/zotero-import`
- **Issue** : #138
- **Fichiers principaux** : `src/k_b/sources/zotero.py` (lecteur), `src/k_b/items.py` (types,
  `Highlight`), `src/k_b/import_items.py` (écrivain, retraits), `src/k_b/database/schema.sql`
  (`zotero_entry`, `highlight`), `src/k_b/raw_items.py` (lecture de `raw/selected_library/`).
- **Série** : suit [laisser la base dédoublonner les items](2026-10-12-laisser-la-base-dedoublonner-les-items.md)
  (natures de source, catalogue d'état de CISA KEV) et
  [importer seulement les bruts nouveaux](2026-10-12-importer-seulement-les-bruts-nouveaux.md)
  (registre `raw_data`).

## Le pourquoi

Depuis #15, `kb collect` écrit toute la bibliothèque Zotero en JSON sous
`raw/selected_library/zotero/`, mais rien n'en entrait dans la base : la table `highlight`
restait vide. Zotero est la dernière source manquante du bloc E1, et la seule source « base de
données » de K-B.

Cette PR fait entrer chaque document de la bibliothèque comme un item (`zotero_entry`) et chaque
surlignage comme une ligne de `highlight`. Le document est relié au papier qu'il est
(`publication`) par sa référence arXiv. Les décisions de modèle ont été prises par Sabine avant
le code (journal ADR, 2026-10-13) :
- un sous-type propre à Zotero ;
- les colonnes arXiv d'une publication restent vides tant qu'arXiv n'a pas vu le papier ;
- les PDF et les étiquettes restent hors base ;
- Zotero est un catalogue d'état ;
- la clé est la clé Zotero seule.

Le besoin de Sabine qui fixe la nature : une fiche de lecture tirée d'un article reste dans son
coffre même si elle supprime l'article dans Zotero, et une modification d'un commentaire doit se
reporter en base. D'où : une modification est réécrite, une suppression est marquée, jamais
effacée.

## Le comment

### 1. Le lecteur valide chaque document seul, et ne cite jamais sa valeur

Le lecteur suit le contrat des sources (`SourceReader`) :
- `read_documents` ne lève que si l'extrait entier est illisible (pas une liste JSON, ou trop
  imbriqué) ;
- `convert_document` valide un document à la fois. Une erreur devient un rejet de ce document
  seul (règle 1 des conventions), écrit au journal d'import par `read_page` (`raw_items.py`).

Le motif d'un rejet recopierait par défaut la valeur refusée : Pydantic l'écrit
(`input_value=…`). Un titre ou un surlignage est une donnée personnelle de Sabine, et le journal
d'import est lisible par tout outil. La première relecture du plan l'a constaté par un essai ;
`convert_document` relève donc l'erreur sans les valeurs :

```python
# src/k_b/sources/zotero.py:437
def without_values(error: ValidationError) -> ValidationError:
    """The same errors, without the value each one received."""
    line_errors = []
    for detail in error.errors():
        line_error: InitErrorDetails = {
            "type": detail["type"],
            "loc": detail["loc"],
            "input": None,
        }
```

Le motif garde le champ (`loc`), le type d'erreur et sa mesure (`ctx`, par exemple la longueur
maximale), ce que demande la règle 3 des conventions. `from None` (ligne 434) empêche la trace
d'origine, qui contient les valeurs, de suivre l'exception.

### 2. Les types partagés vivent dans `items.py`

La règle 4 des conventions demande qu'un type servant à plusieurs modules soit écrit une fois.
L'identifiant arXiv sert à `arxiv.py` (identifiant d'un papier) et à `zotero.py` (référence
d'un document) :

```python
# src/k_b/items.py:51
ARXIV_ID = r"(?:[0-9]{4}\.[0-9]{4,5}|[a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2})?/[0-9]{7})"
```

- Deux formes : celle d'après 2007 (`2609.31282`) et celle d'avant (`hep-th/9901001`). Une
  bibliothèque personnelle peut contenir un vieux papier ; refusé, il aurait bloqué tous les
  retraits (voir § 4).
- `[0-9]` et non `\d` : en Python, `\d` reconnaît tout chiffre Unicode. Des chiffres pleine
  largeur (`２６０９`) passaient, et auraient créé une seconde publication pour le même papier
  (constat de revue, vérifié par commande).
- Le motif est du texte, pas une expression compilée : Pydantic le reçoit ancré
  (`f"^{ARXIV_ID}$"`), comme `NewsletterEdition`.

`Highlight` est un petit modèle Pydantic strict, rangé dans `items.py`, car la base le contraint
(sa clé, ses longueurs) ; ses bornes (`HIGHLIGHT_MAX_LENGTH_BY_FIELD`) sont comparées aux `CHECK`
par `tests/test_schema.py`.

### 3. L'URL en `http` pour Zotero seulement

Les 5 URL de l'extrait réel sont en `http://`. `Item.url` n'acceptait que `https://` : les 5
documents auraient été rejetés. L'URL devient facultative dans l'item, et la règle par sorte est
écrite à part :

```python
# src/k_b/items.py:311
def check_url_scheme(item: Item) -> None:
    if (
        item.url is not None
        and not item.url.startswith("https://")
        and item.kind not in KINDS_WITH_HTTP_URL
    ):
```

Les 5 autres sortes exigent toujours `url` (`REQUIRED_FIELDS_BY_KIND`) en `https` : un test par
sorte le vérifie.

### 4. Le catalogue d'état, à deux niveaux, dans le SQL de l'écrivain

La règle de la nature est une clause SQL de l'écrivain, et nulle part ailleurs (décision de
#105). Pour Zotero, elle s'applique à l'entrée et à chaque surlignage. Celle du surlignage :

```sql
-- src/k_b/import_items.py:161
ON CONFLICT (zotero_key) DO UPDATE SET
    ...
    revised_at = :collected_at,
    withdrawn_at = NULL
WHERE :is_after_latest_catalog
    AND (highlight.withdrawn_at IS NOT NULL
        OR (highlight.text, highlight.comment, highlight.highlighted_at, highlight.item_id)
        IS NOT (excluded.text, excluded.comment, excluded.highlighted_at,
            excluded.item_id))
RETURNING highlight_id
```

- Une ligne connue n'est réécrite que si l'extrait est plus récent que le dernier importé et
  qu'elle a changé, ou qu'elle était retirée (elle réapparaît).
- `IS NOT` sur une ligne de valeurs compare aussi les `NULL` (un commentaire ajouté ou effacé).
- `RETURNING` ne rend rien quand le `WHERE` refuse : c'est ainsi que l'écrivain sait ce qui a
  été écrit.

Le retrait est un `UPDATE` des clés absentes de l'extrait, jamais un `DELETE` : seule la purge
supprime (règle 5 des conventions, « Écarté »). Il est gardé par les conditions de CISA KEV :

```python
# src/k_b/import_items.py:874
    if not entries or raw_file.rejection_count:
        return 0
```

Un extrait avec un document rejeté ne retire rien. Une entrée rejetée est présente, pas
absente. Les surlignages sont comparés à tous ceux de l'extrait : le dernier surlignage de la
bibliothèque, supprimé, est bien retiré (constat de la relecture du plan).

### 5. Une seule règle « après le dernier catalogue »

CISA KEV, Zotero et les deux fonctions de retrait demandent la même chose : le fichier lu
est-il plus récent que le dernier catalogue importé de sa source ? À la troisième occurrence, la
règle est factorisée (`code.md`, duplication) dans `read_latest_catalog`,
`find_withdrawn_at_of_new_row` et `discard_from_catalog` :

```python
# src/k_b/import_items.py:945
def find_withdrawn_at_of_new_row(latest: LatestCatalog) -> str | None:
    """A row only a file older than the latest catalog brings is absent from the latest one:
    it is written withdrawn at it. Without a latest catalog, nothing to compare."""
    if latest.is_file_after or latest.collected_at is None:
        return None
    return latest.collected_at
```

Les tests de CISA KEV, inchangés, passent : le comportement de CISA n'a pas bougé.

### 6. La publication, créée avec sa seule référence

Un document arXiv pointe vers sa `publication`. Si arXiv n'a pas encore vu le papier (cas des 5
documents réels), la publication est créée avec `arxiv_id` seul, comme une CVE créée par une
alerte GitHub ; le `CHECK` de `publication` impose que ses colonnes arXiv restent vides tant
qu'aucun item arXiv ne la porte. Un extrait importé en retard, qui n'écrira pas une entrée
connue, ne fait que chercher sa publication :

```python
# src/k_b/import_items.py:720
    publication_id = (
        write_cited_publication(connection, item.arxiv_id)
        if known_item_id is None or latest.is_file_after
        else find_publication(connection, item.arxiv_id)
    )
```

Sinon une référence corrigée depuis dans Zotero aurait laissé une publication que rien ne
désigne (constat de revue).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Place du document | Sous-type `zotero_entry` (Sabine, piste du 12/10) : le plus petit chemin | DOCUMENT commun aux clips (trancher #14 d'avance, ~45 min) ; CONTENU (question du texte complet, hors issue) |
| Colonnes arXiv sans arXiv | Vides (Sabine) : une seule source de vérité, `CHECK` inchangé | Zotero les remplit (deux sources de vérité, `CHECK` à changer) |
| Nature | Catalogue d'état à deux niveaux (Sabine, son besoin cité ci-dessus) | Flux de nouveautés (ne suit pas les modifications) ; flux avec révisions (il faut `dateModified`, absent des extraits) |
| Quasi-doublon | Clé Zotero seule (Sabine) : la publication relie déjà deux entrées du même papier arXiv | Empreinte du titre (peu fiable sans texte) |
| PDF, étiquettes, auteurs, champ `date` | Hors base, dans l'extrait (Sabine) : aucun usage en base, minimisation | Colonnes JSON ou tables (coût, MCD) |
| Rejet persistant | Règle CISA gardée (Sabine) : un extrait avec rejet ne retire rien | Retirer en épargnant les rejetés (~30 min, écart à la règle du 12/10) |
| Surlignage sans texte | Gardé, `text` facultatif (Sabine, constat de revue) | Rejet du document (bloquait les retraits) ; surlignage écarté |
| Modèle de l'extrait | `extra="ignore"` : ne valide que les champs gardés (choix de la session) | Valider aussi auteurs, étiquettes, PDF (un document rejeté pour un champ non gardé) |
| Date Zotero | Forme vérifiée, puis `Z` ajouté et lecture par Pydantic : pas de nouvelle fonction de date (règle 4) | Une fonction `parse_…_date` de plus |
| Clé Zotero | `GLOB` de 8 caractères `0-9A-Z`, sans `CHECK` de longueur (la forme suffit) | Alphabet exact de Zotero (non vérifié dans sa doc) |
| SQL d'écriture | Dans `import_items.py` (consigne de la mission : écart temporaire à la règle 5, #135) | Dans `database/` dès maintenant (le rangement vient après les sources) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `tests/test_import_zotero.py::test_each_document_and_highlight_of_an_extract_goes_into_the_database` | Un extrait produit par la collecte (bibliothèque fabriquée) donne ses entrées et ses surlignages, dates converties |
| `…::test_an_identical_newer_extract_changes_nothing_and_is_logged_unchanged` | Deux extraits identiques ne comptent pas deux fois (`unchanged`) |
| `…::test_a_document_changed_in_zotero_is_written_again_and_dated`, `…::test_a_highlight_changed_in_zotero_is_written_again_and_its_entry_counted_written` | Une modification est réécrite, `revised_at` daté |
| `…::test_a_document_deleted_in_zotero_is_withdrawn_with_its_highlights_not_removed`, `…::test_the_last_highlights_of_the_library_deleted_are_withdrawn` | Une suppression marque, n'efface pas |
| `…::test_an_extract_with_a_rejected_document_withdraws_nothing`, `…::test_an_older_extract_imported_late_…` | Les gardes de CISA s'appliquent à Zotero |
| `…::test_a_rebuilt_database_has_the_content_of_the_one_kept_import_after_import` | Une base reconstruite égale la base tenue import après import |
| `…::test_a_rejected_document_is_logged_without_its_title_or_highlight_text`, `tests/sources/test_zotero.py::test_a_refused_document_is_described_by_its_field_and_measure_without_its_value` | Aucun titre ni surlignage au journal |
| `tests/test_schema.py::test_each_maximum_length_of_the_items_is_the_check_of_its_column`, `…::test_a_zotero_key_the_item_refuses_is_refused_by_the_base` | Item et base refusent la même chose |
| Clause de dédoublonnage de `UPSERT_ZOTERO_ENTRY` retirée à la main | 6 tests d'import Zotero échouent ; remise à la main, fichier identique à l'original |
| `CHECK (length(text) <= 9000)` au lieu de 10 000 | 3 tests de `test_schema.py` échouent |
| Import des 2 extraits réels dans une base neuve temporaire | 5 entrées, 6 surlignages, 5 publications à référence seule, second extrait écarté (5 `unchanged`), 0 rejet, 0 retrait |
| `uv run pytest`, `ruff check`, `ruff format --check`, `mypy --strict` | Verts (899 tests après les corrections de revue) |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas supprimer en base ce que tu supprimes dans Zotero ?** Les fiches de lecture
   tirées d'un article doivent survivre à sa suppression dans Zotero (ton besoin), et seule la
   purge supprime (règle 5, « Écarté »). `withdrawn_at` dit quand l'absence a été constatée
   (`import_items.py`, `WITHDRAW_ABSENT_*`).
2. **Un document invalide bloque-t-il tout ?** Il est rejeté seul ; les autres sont écrits. Mais
   tant qu'il revient dans l'extrait, rien n'est retiré : c'est la règle de CISA, acceptée comme
   limite, et le rejet est compté à chaque import (`withdraw_absent_zotero_rows`).
3. **Où est la sécurité ?** Validation à la frontière (`ZoteroDocument`, puis `Item` strict),
   SQL paramétré (`json_each(:present_keys)` pour les listes), aucune valeur personnelle dans un
   motif de rejet (`without_values`), le `CHECK` de la base derrière chaque borne de l'item.
4. **Pourquoi `http` pour Zotero seulement ?** Zotero garde l'URL d'où le document a été
   enregistré ; la refuser aurait rejeté les 5 documents réels. Les sources de la veille gardent
   `https` (`check_url_scheme`).
5. **Deux entrées du même papier ?** Elles restent deux entrées (clé Zotero), mais pointent vers
   la même `publication` : le doublon se voit par une requête. Hors arXiv, rien ne les relie
   (limite écrite dans `specs-collecte.md`).

## Zones non vérifiées

- « Type 1 = surlignage » vient de #15, déduit des annotations observées ; la doc de Zotero
  consultée ne le dit pas.
- Qu'un surlignage puisse être enregistré sans texte (PDF scanné) est l'hypothèse du relecteur ;
  le cas n'a pas été observé ni vérifié dans la doc de Zotero. Le code l'accepte quand même.
- La forme ancienne des références arXiv dans `archiveID` de Zotero (`arXiv:hep-th/9901001`)
  n'a pas été observée : seule la forme récente l'a été (5 sur 5).
- Le champ `date` de Zotero est décrit par sa forme observée (« AAAA-MM-JJ AAAA-MM-JJ ») ; son
  sens exact n'a pas été vérifié dans la doc de Zotero. Il n'entre pas en base.
- Le texte d'un surlignage n'est pas contrôlé pour le caractère NUL ni les caractères de
  contrôle, comme les autres textes (#133).

## Ce qui reste

- **Déplacer le SQL d'écriture** dans `src/k_b/database/` : #135.
- **Rejeter l'item que la base refuse sans arrêter l'import** (`SAVEPOINT`) : #136.
- **Afficher les surlignages** dans `kb search` : hors de l'issue, sans issue.
- **Le chemin absolu dans le journal d'import** (une erreur de lecture d'un fichier écrit son
  chemin, donc le nom du compte) : signalé sans issue, à traiter avant la mise en public du
  25/10.
- **Le contrat des sources rend un item plat**, et les surlignages y passent par un champ propre
  à Zotero. Aucune issue ne porte un chemin pour un item à sous-lignes.
- **MCD, MLD et dictionnaire de données** : à mettre à jour par Sabine (`zotero_entry`,
  colonnes de `highlight`).
- **Sabine doit reconstruire sa base locale** : le schéma a changé, sans migration.
