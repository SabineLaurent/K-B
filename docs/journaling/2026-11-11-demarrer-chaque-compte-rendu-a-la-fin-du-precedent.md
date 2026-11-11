# Démarrer chaque compte rendu de veille à la fin du précédent de son sujet

- **Date** : 2026-11-11
- **Branche** : `feat/digest-window-per-subject`, sur `main` au commit `94e3f4e`
- **Issue** : #565
- **Commits** : `ac92902` (la règle), `8230dff` (le tri de la première revue et la lecture vide), `7999c3e` (les
  textes de #423 sur la fenêtre fixe), `42a2da8` (le tri de la seconde revue). Les autres commits de la liste
  injectée sont ceux de `main` avant la branche (#550 à #577) : ils ont leur propre note.
- **Fichiers principaux** : `src/k_b/ai_api/routers/digest_router.py`, `src/k_b/ai_api/digests.py`,
  `src/k_b/ai_api/schemas/digest_schema.py`, `src/k_b/post/digest_sheets.py`, `src/k_b/post/vault_files.py`,
  `src/k_b/post/ai_api_client.py`, `src/k_b/commands/digest_command.py`, `docs/fiches-veille.md` (« Fenêtre »,
  « Fiches dans le coffre »).
- **Série** : [écrire les fiches dans le coffre](2026-10-21-ecrire-les-fiches-de-veille-dans-le-coffre.md),
  [servir les fiches par l'API IA](2026-10-21-servir-les-fiches-par-l-api-ia.md),
  [mettre les comptes rendus en ligne](2026-11-11-mettre-les-comptes-rendus-en-ligne.md) (#423).

## 1. Le pourquoi

Les comptes rendus de veille partent le lundi et le jeudi à 10:00 UTC (`caj-kb-digest-watch`, #423). Jusqu'ici,
chacun lisait une fenêtre fixe : les 3 derniers jours avant la demande. Or du jeudi au lundi, il y a 4 jours : la
tranche du jeudi 10:00 au vendredi 10:00 n'entrait dans aucun compte rendu. La règle de Sabine du 2026-10-26,
redite le 2026-11-11, est qu'aucun item ne tombe entre deux comptes rendus : chaque compte rendu d'un sujet part
de la fin du précédent du même sujet (son `until`) et finit à l'instant de la demande.

Ce code fait donc passer K-B d'une fenêtre fixe à une fenêtre par sujet, sans que l'API IA garde quoi que ce soit
entre deux demandes. C'est `kb digest` qui retrouve, dans le coffre, où s'est arrêté chaque sujet, et qui l'envoie.
La règle devait être en ligne avant le lundi 16/11, si possible avant le jeudi 12/11 10:00 UTC.

## 2. Le comment

### 2.1 L'API IA reste sans état : le début de chaque sujet vient de la demande

`POST /digests` reçoit un champ facultatif, `since_by_subject`, `{sujet: date}`. La route calcule le début
appliqué à chaque sujet :

```python
    default_since = until - timedelta(days=window_days)
    bound = until - timedelta(days=MAX_DIGEST_WINDOW_DAYS)
    ...
            name: max(given.get(name, default_since), bound) for name in names
```
(`src/k_b/ai_api/routers/digest_router.py:145-151`)

Un sujet donné garde sa date ; un sujet absent part de `until − window_days`, la fenêtre de
`KB_DIGEST_WINDOW_DAYS` (3 jours par défaut) ; un début de plus de 14 jours est ramené à la borne (`max`). Juste
avant, la même fonction refuse en 422 un sujet hors de la liste fermée ou un début après la demande, avant toute
lecture. Une date est lue par la fonction des dates de K-B, pas par Pydantic :

```python
def read_start_text(start: object) -> datetime:
    ...
    return parse_aware_datetime(start, "start")
```
(`src/k_b/ai_api/schemas/digest_schema.py:17-20`)

Pourquoi : laissé à Pydantic, un nombre serait lu comme une heure Unix, et le mode strict refuse le texte que
FastAPI transmet ; `parse_aware_datetime` refuse une date sans fuseau (règle 4 de `conventions.md` : un type
défini une fois, dans `items.py`). Rien n'est gardé côté API : la règle 7 de `poc.md` (l'API IA n'écrit rien qui
doive survivre à son redémarrage) est tenue, sur le modèle de `after` pour `kb trend-report`.

### 2.2 Une seule lecture, puis un filtre par sujet : [début, `until`[

L'API IA lit une seule fois, depuis le plus ancien des débuts (`window.since`), et classe une seule fois. Chaque
sujet ne garde ensuite que ses items :

```python
        items_from_start = [
            item
            for item in classified_items
            if item.source_date >= subject_starts[subject.name]
        ]
        ...
        subject_items = [item for item in items_from_start if item.source_date < until]
```
(`src/k_b/ai_api/digests.py:101-108`)

Le filtre passe **avant** la sélection des 60 items d'une fiche (`select_for_writing`) : sinon, des items déjà
écrits occuperaient des places. Les items d'avant le début sont comptés (`items_before_subject_start`) : ils sont
dans la fiche précédente. La borne haute `< until` vient de la première revue : `GET /items` n'a pas de borne
haute, et un item daté de `until` ou après aurait été dans cette fiche et dans la suivante. Quand tous les débuts
sont égaux, rien ne change : même lecture, même nombre d'appels au modèle. C'est ce qui permet au jeu de référence
de `POST /digests` de rejouer sans nouvel enregistrement.

### 2.3 `kb digest` relit le `until` de la dernière fiche de chaque sujet

```python
    names = list_sheet_names(sheets_dir, SHEET_NAME)
    if not names:
        return None
    sheet_path = sheets_dir / max(names)
    # Refuses a link or another entry under the name of the sheet, read by lstat.
    has_sheet(sheet_path, vault_dir)
    until = read_until(read_sheet_head(sheet_path, vault_dir, MAX_FRONT_MATTER_BYTES))
```
(`src/k_b/post/digest_sheets.py:100-106`)

La dernière fiche est celle du plus grand jour parmi les noms `AAAA-MM-JJ.md` (`SHEET_NAME`, `:41`) : une note
ou un temporaire caché n'en est pas une. Sans fiche, le sujet n'a pas de début, et l'API IA lui donne la fenêtre
par défaut : c'est le premier compte rendu. Une fiche écrite à fenêtre fixe, avant #565, se lit comme une autre :
la reprise se fait sans cas à part. Une fiche sans `until` valide, ou au `until` dans le futur, arrête tout avant
la demande (`previous_sheet_invalid`, code 2) : aucun item ne part au modèle pour rien.

La lecture du coffre est sûre, et vit dans `post/vault_files.py`, à côté de l'écriture sûre (seconde revue) :

```python
    descriptor = os.open(sheet_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as sheet:
        if not stat.S_ISREG(os.fstat(sheet.fileno()).st_mode):
            ...
        return sheet.read(max_bytes)
```
(`src/k_b/post/vault_files.py:126-133`)

`has_sheet` refuse d'abord un lien ou une entrée qui n'est pas un fichier (`lstat`). Puis l'ouverture ne suit pas
de lien (`O_NOFOLLOW`) et n'attend pas sur un tube nommé (`O_NONBLOCK`) ; l'entrée ouverte est recontrôlée par
`fstat`, car elle a pu être remplacée entre le `lstat` et l'ouverture. Seuls 4 096 octets sont lus
(`MAX_FRONT_MATTER_BYTES`, `digest_sheets.py:43`) : l'en-tête, jamais le texte. La date lue est ramenée en UTC par
`convert_to_utc` (une date hors des dates possibles une fois en UTC devient une erreur nommée, pas une
`OverflowError`), puis tronquée à la seconde, comme `kb` l'envoie (`digest_sheets.py:131-134`).

### 2.4 `kb digest` revérifie la réponse avant d'écrire

`kb` envoie les débuts au format des dates de la base (`post/ai_api_client.py:214-217`), puis contrôle la
réponse : les sujets de `since_by_subject` sont ceux de la liste (`subjects_not_the_list`), chacun est une fois
dans `digests`, `failed_subjects` ou `subjects_without_items` (`subject_missing`). Et les débuts appliqués :

```python
    window_start = response.window.until - timedelta(days=response.window.days)
    bound = response.window.until - timedelta(days=MAX_DIGEST_WINDOW_DAYS)
    ...
                raise_invalid(response.request_id, place, "start_not_the_window")
    ...
            raise_invalid(response.request_id, place, "start_before_the_one_sent")
    ...
            raise_invalid(response.request_id, place, "start_after_the_one_sent")
```
(`src/k_b/post/ai_api_client.py:405-417`)

Un début avant celui envoyé redonnerait des items de la fiche précédente ; un début après, sauf à la borne,
laisserait des items hors de toute fiche ; un sujet sans début envoyé doit partir de la fenêtre de la réponse. La
réponse de l'API IA est une entrée non fiable (OWASP API10:2023) : `kb` ne lui fait pas confiance, même si c'est
du code de K-B. Un début ramené à la borne est journalisé (`<sujet>: start … brought to …, the bound of 14 days`) :
le journal dit ce qui a été observé, puisque `kb` a vérifié que c'est bien la borne.

### 2.5 La fiche « Aucun item classé », et la lecture vide

Un sujet sans item reçoit une fiche qui le dit (`NO_ITEM`, `digest_sheets.py:39`) : sans elle, son début
n'avancerait jamais, et la lecture suivante remonterait toujours plus loin. Mais une lecture **entièrement** vide
n'écrit rien :

```python
    if response.items_in == 0:
        # An empty base or an import not run: a sheet would move a start over items not read
        # (decision of Sabine of 2026-11-11).
        logger.warning("no item read: no sheet written, the start of each subject kept")
        rows = []
```
(`src/k_b/commands/digest_command.py:112-116`)

Une base vide ou un import pas lancé aurait donné neuf fiches « Aucun item » et avancé chaque début sur des items
jamais lus. `kb` sort en 0 : rien n'a échoué, et le compte rendu suivant repartira des mêmes débuts.

## 3. Choix faits et options écartées

| Choix retenu | Pourquoi | Options écartées et pourquoi |
|---|---|---|
| D1 (Sabine) : `kb` relit le `until` de la dernière fiche du coffre | Le coffre reste la seule source de la fin d'un compte rendu ; les fiches déjà écrites à fenêtre fixe (job en ligne du 11/11) doivent servir de précédent | Un registre `KB_DATA_DIR/digest_windows.json` (comme `trend_reports.json`) : deux sources de la même fin, et les fiches relues quand même à la reprise. C'est un écart, pour les seules fiches de veille, au choix des tendances du 30/10 (ne pas relire le coffre) |
| D2 (Sabine) : `KB_DIGEST_WINDOW_DAYS` pour le premier compte rendu | Une variable de moins, déjà bornée de 1 à 14 et documentée, dont le sens devient « la fenêtre d'un sujet sans début » | `KB_DIGEST_FIRST_WINDOW_DAYS`, proposée par l'issue : une seconde variable de même sens |
| Une seule lecture et un seul classement, depuis le plus ancien début | Débuts égaux : même lecture, même nombre d'appels au modèle, jeu de référence intact | Deux passes, la plus récente d'abord (retirée par time-knight, plan v3) : elle reste la parade de la limite « Une seule passe de lecture » |
| Reprise à `until`, pas à `covered_after`, après une lecture plafonnée | Repartir de `covered_after` relirait les sortes rares déjà écrites, en double | — ; ce que le plafond laisse de côté est perdu pour les fiches (limite écrite) |
| Début ramené à 14 jours, pas refusé | La borne existante de `window_days` (`MAX_DIGEST_WINDOW_DAYS`) ; `kb` le journalise | — (non discuté) |
| Fenêtre [début, `until`[ (première revue) | Un item daté de `until` ou après n'est écrit qu'une fois | Garder la lecture sans borne haute (doublons) |
| Lecture vide : aucune fiche, code 0 (Sabine, constat 6) | Ne pas avancer les débuts sur des items non lus | Neuf fiches « Aucun item » (le code avant ce tri) |
| `window_days` retiré de l'en-tête des fiches ; « none in the window » retiré du bilan | Aucun code ne lisait `window_days`, et une fenêtre n'a plus de durée fixe ; chaque sujet a maintenant sa ligne | — (écarts tranchés par time-knight) |
| Lecture sûre déplacée dans `post/vault_files.py` (seconde revue) | Une seule place pour l'accès sûr au coffre | La garder dans `digest_sheets.py` : deux modules à corriger pour une même faille |

Consignes du dépôt qui imposent un choix : règle 7 de `poc.md` (API sans état), règle 4 de `conventions.md` (la
date lue par `items.py`), règle 3 de `conventions.md` (une valeur jamais citée dans un refus : `kb` nomme la place
et le contrôle), `code.md` « Échouer fermé » (fiche illisible : code 2 pour tous les sujets).

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_two_digests_follow_each_other_without_a_gap` (`tests/commands/test_digest_command.py`) | Le second compte rendu part du `until` du premier |
| `test_a_first_digest_gives_no_start`, `test_without_a_start_each_subject_starts_at_the_window` | Le premier compte rendu prend la fenêtre de `KB_DIGEST_WINDOW_DAYS` ; un corps vide ne change rien |
| `test_a_sheet_written_with_a_fixed_window_gives_the_start_of_its_subject`, `test_the_previous_until_is_the_one_of_the_last_sheet_written_with_a_fixed_window` | La reprise d'une fiche d'avant #565 |
| `test_a_failed_subject_keeps_its_start_for_the_next_digest` | Un sujet en échec garde son début |
| `test_the_items_before_the_start_of_a_subject_leave_before_the_digest_cap` ; mutation `if True` : `0 == 3` | Le filtre passe avant les 60 items, et le test le voit |
| `test_the_items_dated_from_the_until_are_left_to_the_next_digest` ; mutation : `5 == 3` | La borne haute `< until` |
| `test_a_start_older_than_the_bound_is_brought_to_the_bound`, `test_a_malformed_request_is_refused_422_before_any_call` (sujet inconnu, sans fuseau, nombre, après la demande) | La validation de `since_by_subject`, avant toute lecture |
| `test_a_start_after_the_one_sent_is_refused_unless_it_is_the_bound`, `test_a_start_brought_to_the_bound_is_accepted`, `test_a_subject_without_a_start_sent_is_refused_unless_it_starts_at_the_window`, `test_a_response_that_breaks_the_closed_lists_is_refused_before_any_sheet` (`subject_missing`) | Les contrôles de `kb` sur la réponse (rouges d'abord : `DID NOT RAISE`) |
| `test_a_last_sheet_without_a_valid_until_is_refused` (dont `out-of-range-in-utc`, rouge d'abord : `OverflowError`), `test_the_previous_until_is_read_to_its_second_as_kb_sends_it` (rouge : 700 000 µs) | La lecture du `until` |
| `test_a_pipe_slipped_under_the_last_sheet_after_its_check_is_refused_without_waiting` ; avant le code, pytest bloqué 15 s puis tué (code 142) | Un tube nommé ne fait plus attendre `kb` |
| `test_an_empty_reading_writes_no_sheet_and_keeps_the_starts` (rouge : 3 fiches écrites) | La décision de Sabine sur la lecture vide |
| `test_the_body_of_every_subject_of_the_list_holds_under_the_bound_of_the_ai_api` ; mutation de la borne : `379 <= 300` | Le corps de `kb digest` (379 octets pour 9 sujets) tient sous les 1 024 octets de l'API IA |
| `tests/ai_api/test_digests_reference.py` vert sans nouvel enregistrement | Le nombre d'appels au modèle ne change pas |
| `uv run pytest` → 4539 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles du dépôt |
| `/security-review` : aucun constat ; `/code-review` high, deux passages (10 et 10 constats), triés par time-knight | La revue |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi l'API IA ne garde-t-elle pas elle-même la fin de chaque sujet ?** Elle doit pouvoir être redémarrée
   ou déplacée sur Azure Container Apps sans rien perdre (règle 7 de `poc.md`) ; seul `kb` écrit dans le coffre. Elle
   reçoit donc les débuts dans la demande (`digest_router.py:145-151`).
2. **Que se passe-t-il si un sujet échoue ?** Il n'a pas de fiche, donc il garde son début : le compte rendu
   suivant reprend au `until` de sa dernière fiche écrite, 14 jours au plus. Revers : la lecture, commune, part
   alors de ce début plus ancien pour tous (limite « Une seule passe de lecture »).
3. **Un fichier piégé dans le coffre peut-il faire lire autre chose à `kb` ?** Le chemin est fait de constantes,
   d'un sujet de la liste fermée et d'un nom `AAAA-MM-JJ.md` ; un lien est refusé (`lstat`, `O_NOFOLLOW`), un
   tube ne bloque pas (`O_NONBLOCK`, `fstat`), seuls 4 096 octets sont lus, et seule une date en sort
   (`vault_files.py:126-133`). Il faudrait de toute façon écrire dans le coffre de l'utilisatrice.
4. **Pourquoi ne pas reprendre à `covered_after` après une coupe du plafond ?** Les sortes rares, lues en premier,
   sont déjà écrites : elles reviendraient en double. Ce que la coupe laisse de côté est perdu pour les fiches, et
   la coupe est dite dans la fiche (`items_capped`, `capped_kind`, `covered_after`).
5. **Reste-t-il des items qui ne sont dans aucune fiche ?** Oui, c'est écrit avec les parades
   (`docs/fiches-veille.md`, « Limites de la fenêtre ») : le retard de collecte (un item daté avant un `until` mais
   importé après), la marge du lundi sous le plafond de 300, les 60 items d'une fiche, un item reclassé, un job
   arrêté plus de 14 jours.

## 6. Zones non vérifiées

- **Le second moteur** : `uv run pytest -m postgresql` n'a pas été lancé sur le Mac ; la preuve est le job CI
  `tests-postgresql` de la PR. Ce code ne touche pas `database/`.
- **Aucun essai réel** : `kb digest` n'a pas tourné contre le vrai modèle ni en ligne avec `since_by_subject` ; le
  premier essai réel sera le premier passage de `caj-kb-digest-watch` après le tag.
- **La marge du lundi** (190 à 275 items pour 4 jours, sous le plafond de 300) est une extrapolation du volume
  estimé, pas une mesure.
- **Obsidian** : ce qu'il fait d'un `until` modifié par son éditeur de propriétés (un `Z` retiré, par exemple)
  n'a pas été essayé ; un `until` sans fuseau est refusé en code 2.
- **`O_NONBLOCK`** n'est essayé que sur le Mac (APFS) ; le partage SMB d'Azure Files n'a pas de tube nommé.
- **4 096 octets** suffisent à l'en-tête que `kb` écrit (environ 300 octets) ; un en-tête allongé à la main
  au-delà serait refusé en code 2.

## 7. Ce qui reste

- **Le rejeu des créneaux manqués** (une requête par créneau, une fiche datée de son créneau) : après l'oral blanc
  du 13/11 (décision du 2026-10-26) ; c'est la parade d'un job arrêté plus de 14 jours.
- **Le compte à la date d'arrivée dans K-B**, parade du retard de collecte : il demande une date de première
  arrivée, donc une colonne et une migration (#186).
- **Un compteur des items datés après `until`**, des **deux passes** de lecture, la **rédaction par lots de 60** :
  parades écrites, non codées.
- **Le tag** qui met la règle en ligne, avant jeudi 10:00 UTC si possible : décision de Sabine, posé par tn-codeur.
