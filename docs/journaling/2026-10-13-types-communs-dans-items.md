# Définir une seule fois les types communs dans `items.py`

- Date : 2026-10-13
- Branche : `refactor/shared-types-in-items`
- Issue : #133
- Fichiers principaux : `src/k_b/items.py`, les lecteurs de `src/k_b/etl/sources/`,
  `tests/test_items.py`, `tests/test_schema.py`
- Note précédente de la série : [ranger le parcours dans `etl/`](2026-10-13-ranger-le-parcours-dans-etl.md)

## Le pourquoi

K-B valide une entrée deux fois. L'item Pydantic la valide à la lecture du brut, puis la base
SQLite la valide une seconde fois par ses `CHECK`. Les deux doivent dire la même chose. Si l'item
accepte une valeur que la base refuse, l'erreur n'éclate qu'à l'écriture et fait tomber l'import.

Avant cette PR, une même règle était écrite plusieurs fois, sous plusieurs formes :
- la CVE, deux fois dans `items.py` ;
- le nom de dépôt, trois fois ;
- la date avec fuseau, trois fois ;
- la forme GHSA, hors de `items.py`.

Une copie divergeait, et c'est elle qui causait le bogue. La règle 4 de
`.claude/rules/conventions.md` fixe le remède : un type défini une fois dans `items.py`, et un
test qui le compare au `CHECK` de la base.

## Le comment

### Une forme écrite une fois, en texte

```python
CVE_ID = r"CVE-[0-9]{4}-[0-9]{4,}"
```
`src/k_b/items.py:45`

La forme est un texte, pas un motif compilé. Deux utilisateurs en ont besoin :
- le type Pydantic l'ancre : `CveId = Annotated[str, StringConstraints(pattern=f"^{CVE_ID}$")]`
  (`items.py:139`) ;
- les lecteurs, encore des `dataclass` validées à la main jusqu'à #85, l'appliquent par
  `re.fullmatch(CVE_ID, cve_id)` (`etl/sources/cisa_kev.py:121`,
  `etl/sources/github_advisories.py:117`).

`GHSA_ID` (`:47`) et `REPOSITORY_NAME` (`:49`) suivent le même modèle, comme `ARXIV_ID` avant eux.

### Ce que `\d` laissait passer

En Python, `\d` reconnaît tout chiffre Unicode, par exemple les chiffres pleine chasse `２０２６`.
Le `GLOB '[0-9]…'` de `schema.sql` n'accepte, lui, que les chiffres ASCII. Ainsi,
`CVE-２０２６-1234` passait l'item puis était refusé par la base. `[0-9]` s'en tient aux dix
chiffres ASCII.

### Le texte qu'on peut stocker

```python
UNSTORABLE_CHARACTER = re.compile("[\0\ud800-\udfff]")
```
`src/k_b/items.py:84`

Deux caractères posent problème :
- le NUL, parce que SQLite arrête `length()` et `GLOB` au premier NUL : un `tag_name` qui commence
  par NUL mesure 0 et tombe sur `CHECK (length(tag_name) > 0)` ;
- le surrogate isolé, parce que `sqlite3` ne peut pas l'encoder en UTF-8 (`UnicodeEncodeError`).

Tout le reste passe, retours à la ligne et tabulations compris, car les résumés sont du Markdown
sur plusieurs lignes. La fonction `check_text_can_be_stored` (`:87`) lève une simple
`ValueError` : le lecteur Zotero reconstruit les erreurs par leur type, et ce type doit être l'un
de ceux que Pydantic connaît.

### L'ordre des annotations compte

```python
NonEmptyText = Annotated[str, StringConstraints(min_length=1), CAN_BE_STORED]
```
`src/k_b/items.py:127`

`CAN_BE_STORED` vient **en dernier** dans chaque type de texte. Placé avant la longueur, il ferait
basculer Pydantic sur un contrôle de longueur générique. L'erreur s'appellerait alors `too_long`,
« at most N items », au lieu de `string_too_long`, « at most N characters ». Le message du rejet
Zotero en changerait.

### La date en UTC, l'entier sur 64 bits, l'identifiant de release

- `UtcDatetime = Annotated[AwareDatetime, AfterValidator(convert_to_utc)]` (`:150`). L'item garde
  une date avec fuseau, ramenée en UTC. Une date que l'UTC ferait sortir du domaine de
  `datetime` (le 1er janvier de l'an 1, à l'est de l'UTC) est refusée au lieu de lever un
  `OverflowError` en plein import. La boucle de conversion de `etl/normalize.py` disparaît, et
  une seule fonction lit une date dans un texte : `parse_aware_datetime`.
- `Int64 = Annotated[int, Field(ge=MIN_INT64, le=MAX_INT64)]` (`:152`). C'est le plus grand entier
  que SQLite sait écrire. `rank` et les entiers de `TrendRow` le resserrent, par exemple avec
  `Annotated[Int64, Field(ge=1)]` (`:325`).
- L'identifiant d'une release est un texte dans l'item, mais `etl/load.py` l'écrit en entier.
  `check_source_item_id` (`:392`) vérifie donc sa forme, avec la table `SOURCE_ITEM_ID_BY_KIND`
  (`:198`). La forme est `[1-9][0-9]{0,18}` : sans zéro en tête, car `0007` et `7` seraient une
  même release en base, et 19 chiffres au plus, ce qui évite la conversion par `int()` d'un texte
  géant. La borne `MAX_INT64` reste vérifiée à part, car `9999999999999999999` a 19 chiffres et
  dépasse pourtant 64 bits.

## Choix faits et options écartées

- **Le nom de dépôt** prend l'alphabet ASCII de GitHub, `[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+`
  (décision de Sabine, option A1). Le `GLOB '?*/?*'` de la base est plus large et ne refuse rien
  que l'item accepte : le schéma ne change pas. Le contrôle des caractères de contrôle de la
  tendance, devenu inatteignable, est retiré.
  - Écartée, la règle large `[^/\s]+` partout : `?`, `#` et `%` entreraient dans l'URL d'une
    release.
  - Écarté, un `GLOB` resserré : le schéma changerait sans aucun gain.
- **Pas d'alias `GhsaId`** : aucun champ n'a ce type, puisque `source_item_id` change selon la
  sorte. Il est reporté à #85, sur décision de Sabine.
- **`AwareDatetime` + conversion, plutôt qu'un type maison** : Pydantic valide déjà le fuseau ;
  K-B n'ajoute que la conversion en UTC.
- **Un type explicite par champ, plutôt qu'un validateur sur tout le modèle** : chaque champ dit
  ce qu'il accepte, et un test parcourt tous les champs de texte.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_cve_with_other_than_ascii_digits_is_refused` (item), `test_a_malformed_row_is_refused` (CISA KEV), `test_an_invalid_advisory_is_refused_with_its_position` (alertes) | `CVE-２０２６-1234` est refusé par l'item et par les deux lecteurs |
| `\d` remis à la main dans `CVE_ID` : 5 échecs, puis retour à `[0-9]` | ces tests voient bien la règle |
| `tests/test_schema.py`, un test par type (`…_is_refused_by_its_type_and_by_the_base`) | chaque type refuse une valeur que la base refuse |
| `test_a_text_field_of_an_item_with_a_nul_or_a_lone_surrogate_is_refused`, et ses équivalents pour le surlignage et la tendance | tout champ de texte refuse le NUL et le surrogate isolé |
| `test_a_summary_on_several_lines_with_a_tab_is_accepted` | le texte de la fixture des alertes passe |
| `grep` des types (`items.py` seul) ; `grep` des dates (une fonction) | une seule définition par règle |

## Ce que tu dois pouvoir défendre

- **Pourquoi la base ne suffit-elle pas ?** Une valeur refusée par la base ne l'est qu'à
  l'écriture, au milieu de l'import. L'item la refuse à la lecture, avec un rejet nommé (règle 1).
- **Pourquoi `[0-9]` et pas `\d` ?** `\d` est Unicode en Python et dans le moteur de Pydantic.
  `[0-9]` correspond exactement au `GLOB` de la base (`items.py:45`).
- **Pourquoi refuser le NUL mais pas le retour à la ligne ?** Le NUL fausse `length()` et `GLOB`
  dans SQLite. Le retour à la ligne est du contenu légitime : un résumé Markdown en contient.
- **Que se passe-t-il pour un nom GH Archive non ASCII ?** La ligne est refusée, et avec elle
  tout le classement, qui refuse sa page entière (règle 1). C'est un risque accepté : les noms
  observés sont ASCII.
- **Pourquoi ne pas avoir changé le schéma ?** La règle 4 demande seulement que l'item refuse
  tout ce que la base refuse. Le `GLOB` plus large le permet, et la base locale de Sabine n'a pas
  à être reconstruite.

## Zones non vérifiées

- Que GitHub n'admette que l'alphabet ASCII dans les noms de dépôt : la recherche n'a trouvé
  aucune source officielle. Seuls les 5 noms de la fixture ont été vérifiés.
- Le test du résumé sur plusieurs lignes passait déjà avant la PR : il n'a pas pu être vu en
  échec. Même chose pour le surlignage Zotero avec un surrogate, déjà refusé sur `main` par le
  modèle du lecteur.
- Le comportement de Pydantic (ordre des annotations, surrogate transmis tel quel au validateur)
  a été observé sur Pydantic 2.13.5, sans lire son code Rust.

## Ce qui reste

- `GhsaId`, et les types utilisés par les modèles des lecteurs : #85.
- Les valeurs citées sans troncature dans les messages, et la valeur reçue que Pydantic recopie
  dans le motif d'un rejet : #134, #92.
- Les séquences d'échappement du terminal dans le texte libre : signalées, sans issue.
