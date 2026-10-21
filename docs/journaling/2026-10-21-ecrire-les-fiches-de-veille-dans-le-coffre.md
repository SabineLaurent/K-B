# Écrire les fiches de veille dans le coffre par `kb digest`

- **Date** : 2026-10-21
- **Branche** : `feat/kb-digest`
- **Issue** : #209
- **Fichiers principaux** : `src/k_b/commands/digest_command.py`, `src/k_b/etl/ai_api_client.py`,
  `src/k_b/etl/digest_sheets.py`, `src/k_b/etl/vault_files.py`, `src/k_b/commands/exit_codes.py`,
  `src/k_b/core/outbound.py`
- **Série** : suit [Servir les fiches par l'API IA](2026-10-21-servir-les-fiches-par-l-api-ia.md)
  (#156), [Écrire les fiches des tops](2026-10-19-ecrire-les-fiches-des-tops.md) (#265) et
  [Refuser un lien ou une balise dans une fiche](2026-10-21-refuser-un-lien-ou-une-balise-dans-une-fiche.md)
  (#206).

## Le pourquoi

Jusqu'ici, l'API IA rédigeait les fiches de veille et les rendait en JSON à qui les demandait, sans
rien garder (règle 7 de `poc.md`). Il manquait le dernier geste du produit : « je lis ma veille
simplement », dans Obsidian. `kb digest` le fait : il demande les fiches à l'API IA, puis écrit
une fiche Markdown par sujet dans le coffre, `veille/<sujet>/AAAA-MM-JJ.md`. C'est aussi
l'intégration de l'API IA côté client (E3).

Deux risques guident le code. Le premier : la réponse est une entrée non fiable. Une affirmation
vient du modèle, un titre vient d'une source ; écrits tels quels dans le coffre, un lien, une balise
ou une requête Dataview piégés deviendraient actifs, jusqu'au JavaScript si l'utilisatrice a
activé `dataviewjs` (OWASP LLM10). Le second : le coffre est à l'utilisatrice. `kb` n'y suit jamais
un lien symbolique, n'y réécrit jamais une fiche, et ne crée pas de faux coffre sur une faute de
frappe.

La PR change aussi trois choses autour, par décision de Sabine du 2026-10-21 : la réponse de
l'API IA donne le modèle (`model`, version 0.2.0) ; une règle de codes de sortie commune,
« même résultat, même code » (4 pour un échec partiel, aussi pour `kb write-tops`) ; les clés du
frontmatter en anglais, aussi pour les fiches des tops.

## Le comment

### 1. Une porte qui refuse avant de demander

La commande se lit comme une recette : réglages, contrôle du coffre, demande, écriture
(`src/k_b/commands/digest_command.py:50-55`) :

```python
    subject_names = [subject.name for subject in DIGEST_SUBJECTS]
    try:
        refuse_written_sheets(vault_dir, subject_names, read_today())
    except VaultEntryRefusedError as error:
        logger.error("no digest asked: %s", error)
        return ExitCode.NOT_STARTED
```

`refuse_written_sheets` regarde, pour chaque sujet de la liste, si `veille/` ou
`veille/<sujet>/` est un lien symbolique, et si la fiche du jour existe déjà. Si oui, rien n'est
demandé (code 2) : les items ne partent pas au modèle pour une fiche qui ne serait pas écrite
(minimisation, coût). Ce contrôle ne crée rien. Une `OSError` à ce moment (dossier illisible)
est une panne, pas un refus : code 1, comme pour `kb write-tops`.

### 2. Un client qui ne fait confiance qu'à un schéma fermé

`request_digests` envoie `POST /digests` avec `{}` (la fenêtre par défaut de `kb serve-ai`) et
traduit chaque panne en état nommé (`src/k_b/etl/ai_api_client.py:197-202`) :

```python
    try:
        answer = http_client.post(DIGESTS_PATH, json={})
    except httpx2.TimeoutException:
        raise AiApiError("ai_api_timeout") from None
    except httpx2.TransportError:
        raise AiApiError("ai_api_unavailable") from None
```

`from None` coupe la chaîne d'exceptions : l'erreur d'httpx2 nomme l'URL, et une `ValidationError`
de Pydantic cite la valeur reçue ; ni l'une ni l'autre n'atteint le journal. Le client est ouvert
par `open_http_client` (`core/outbound.py`) : ni proxy de l'environnement ni redirection suivie.
Le délai de lecture est de 240 s, au-dessus des 200 s qu'une demande peut durer côté API IA ; pas
de nouvelle tentative, un `Retry-After` est affiché, jamais attendu.

La réponse est relue par `DigestsResponse`, un modèle Pydantic strict qui ignore les champs qu'il
ne lit pas (les `facts` ne sont jamais lus). Les valeurs qui iront dans le frontmatter sont
validées par motif : `request_id` en UUID, `model` par `MODEL_NAME`. Puis `refuse_out_of_lists`
recoupe la réponse avec les listes fermées (`src/k_b/etl/ai_api_client.py:284-287`) :

```python
        for claim_number, claim in enumerate(digest.claims):
            place = f"digests.{number}.claims.{claim_number}.item_ids"
            if not set(claim.item_ids) <= set(source_ids):
                raise_invalid(response, place, "item_not_in_sources")
```

Un sujet hors de la liste ferait un chemin hors de `veille/` : il est refusé avant toute
écriture. Une affirmation qui cite un item absent des sources de sa fiche citerait ce que la
fiche ne liste pas : refusée aussi. L'erreur nomme la place et le contrôle, jamais la valeur.

### 3. Écrire en texte : échapper, et refuser une URL douteuse

Chaque affirmation et chaque titre passent par `neutralize_digest_text`
(`src/k_b/etl/digest_sheets.py:200-202`) :

```python
    neutralized = neutralize_text(text, DIGEST_ESCAPED_CHARACTERS)
    neutralized = ESCAPED_DOUBLE_COLON.sub(r"\\: ", WWW_DOT.sub(r"\1\\.", neutralized))
    return LEADING_LIST_MARKER.sub(escape_list_marker, neutralized)
```

`neutralize_text` (partagée avec les tops) met le texte sur une ligne et place une barre oblique
inverse devant chaque caractère de syntaxe : CommonMark permet d'échapper toute ponctuation
ASCII (§ 2.4), et le caractère s'affiche sans la barre. Dans la même passe, elle échappe le `&`
qui ouvre une référence de caractère (`&rlm;` rendrait un contrôle bidirectionnel), mais pas celui
de `R&D` ni d'une URL avec requête, qui restent justes dans une fiche de top. Le jeu des fiches de
veille ajoute à celui des tops tout `&`, `~` (bloc `~~~`), `:` et `@` (liens automatiques
`http://`, `mailto:`, adresse mail ; ces deux derniers restent du texte dans Obsidian, mais
cmark-gfm, le moteur de GitHub, en fait encore un lien).
Trois étapes viennent ensuite, toutes après `neutralize_text`, qui sinon doublerait leurs barres
obliques :

- le point de `www.`, sans casse, car ce lien automatique de GFM n'a besoin d'aucun des caractères
  échappés ;
- une espace entre deux deux-points échappés : la recette de Sabine dans Obsidian a montré qu'un
  champ Dataview `\[champ\:\: valeur\]` s'affichait encore en mode lecture. Dataview y cherche
  `::` dans le HTML rendu (`replaceInlineFields`, version 0.5.68), où les barres obliques ont
  disparu ; l'espace l'en empêche (`std::string` s'affiche `std: :string`) ;
- la ponctuation d'un marqueur de liste en tête (`\- urgent`, `2026\. Bilan`) : une affirmation
  ouvre déjà une puce, un titre une ligne numérotée, et ce marqueur imbriquerait une liste.

Une URL de source est le seul lien de la fiche. Elle est écrite entre chevrons, où une barre
oblique n'échappe rien (CommonMark § 6.5) : on ne peut donc pas l'échapper, seulement la refuser
(`src/k_b/etl/digest_sheets.py:174-180`) :

```python
        url.startswith(URL_SCHEMES)
        and URL_CHARACTERS.fullmatch(url) is not None
        and "::" not in url
        and CHARACTER_REFERENCE.search(url) is None
        and not has_hidden_character(url)
```

`URL_CHARACTERS` (`:55`) sont les caractères de la RFC 3986, moins `[`, `]` et `$` (syntaxe
d'Obsidian) : une espace, un `>` ou un accent grave ferait sortir l'URL de ses chevrons. Les trois
autres conditions viennent des revues : `::` ferait un champ Dataview, même dans les métadonnées
de la page ; une référence de caractère (`&#x202E;`) est décodée même dans un lien automatique ; un
caractère caché encodé en pourcents (`%E2%80%AE`) peut s'afficher décodé. Dans les deux derniers
cas, le lien se lirait autrement qu'il ne mène, comme `https://docs.python.org&#x202E;@evil.example/`.
Une URL refusée n'est jamais réécrite, ce qui changerait sa cible : la source est écrite
« (sans URL) ».

### 4. Une écriture sûre, partagée avec les fiches des tops

`write_new_sheet` (`src/k_b/etl/vault_files.py:52-56`) est l'écriture des tops, sortie de
`top_sheets.py` pour être réemployée, pas recopiée :

```python
    refuse_linked_folders(vault_dir, sheets_dir)
    if has_sheet(sheet_path, vault_dir):
        return False
    write_file_atomically(sheet_path, content.encode("utf-8"))
    return True
```

Les dossiers sont recontrôlés juste avant l'écriture : `write_file_atomically` suivrait un lien.
`has_sheet` lit l'entrée elle-même (`lstat`) : un lien ou un dossier sous le nom de la fiche est
refusé. La fiche passe par un temporaire caché renommé (règle 2 de `conventions.md`) : Obsidian
ne voit jamais une fiche à moitié écrite.

La limite, acceptée par Sabine pour le POC : entre `has_sheet` et le renommage (`os.replace`), une
fiche apparue est remplacée sans message (CWE-367), et un dossier remplacé par un lien ferait
écrire hors du coffre (CWE-59). Seuls deux lancements de l'utilisatrice qui se chevauchent le
peuvent. La correction (publier par `os.link`, qui échoue si la cible existe) est à #295.

### 5. Même résultat, même code

`find_exit_code` (`src/k_b/commands/exit_codes.py:52-58`) tient la règle de Sabine pour les trois
commandes faites de parties (sources, tops, sujets) :

```python
def find_exit_code(*, has_failed: bool, has_done: bool) -> ExitCode:
    if not has_failed:
        return ExitCode.SUCCEEDED
    return ExitCode.PARTIAL_FAILURE if has_done else ExitCode.FAILED
```

Pour `kb digest`, une partie est faite quand sa fiche est écrite, et en échec quand l'API IA la
nomme dans `failed_subjects` ou que sa fiche n'est pas écrite. Pour `kb write-tops`, un relevé
illisible avec des fiches écrites donne 4 : « échouer fermé » tient, car 4 n'est pas 0.

### 6. Les règles de connexion dans `core/`

`find_url_refusal` et `open_http_client` étaient dans `ai_api/connectors/outbound.py`. `etl`
n'importe pas `ai_api` (règle 5 de `conventions.md`), et une règle de sécurité ne se recopie pas :
le module passe dans `core/outbound.py`, que tout le monde peut importer. Un test d'architecture
tient désormais qu'`etl` n'importe ni `data_api` ni `ai_api`
(`tests/architecture/test_layers.py`, `test_etl_imports_neither_the_data_api_nor_the_ai_api`).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le client dans `etl/ai_api_client.py`, l'API IA jointe par HTTP | seul `kb` écrit le coffre ; `etl` est sous les commandes et n'importe pas `ai_api` | un paquet de client au-dessus d'`ai_api` |
| `model` dans la réponse 200, API IA 0.2.0 | décision de Sabine : le critère met le modèle dans le frontmatter | lire `KB_LLM_MODEL` (réglage d'un autre processus) ; pas de modèle |
| 401 → 1, clé absente → 2 | décision de Sabine : avec une clé refusée, la requête est partie ; règle de `kb collect` (une source en 401 échoue) | 2 avec un sens élargi (ma proposition) ; un code dédié à l'authentification, à revoir avec #160 |
| 4 pour un échec partiel de `kb collect`, `kb write-tops` et `kb digest` | règle de Sabine, « même résultat, même code » | 1 pour `kb digest` (ma proposition) ; `kb write-tops` dans une issue à part |
| Un top sans relevé compte comme abouti | comme une source sans rien de neuf pour `kb collect` (accepté par time-knight) | le compter comme rien fait |
| `outbound.py` dans `core/` | décision de Sabine : `etl` n'importe pas `ai_api`, une règle de sécurité ne se recopie pas | un paquet `outbound/` ; une copie temporaire |
| L'écriture sûre dans `etl/vault_files.py` | la mission : réemployée, pas recopiée | la recopier ; la mettre dans `core/` (elle écrit par `etl/raw_store.py`) |
| Échapper `~ : @` et `www.` en plus du jeu des tops | une affirmation du modèle ne fait jamais un lien ; Dataview lit `::` | se fier au seul contrôle 6 de l'API IA (il laisse passer `$=`, `#`, `%%`, `::`, une adresse mail, et ne lit pas les titres) |
| Une URL en RFC 3986, moins `[ ] $` | dans `<…>` rien ne s'échappe : refuser plutôt qu'échapper | l'ASCII imprimable sans espace, `<`, `>`, `\` (plan v2, moins strict) |
| Contrôler les fiches du jour avant la demande | aucun item envoyé pour une fiche qui ne serait pas écrite | demander puis sauter les fiches existantes |
| `capped_kind` et `covered_after` dans le frontmatter, `null` sinon | une fenêtre coupée doit dire quelle sorte et après quelle date (constat 6 de la revue) | `items_capped` seul |
| Le `&` d'une référence de caractère échappé dans les tops, tout `&` dans les fiches de veille | une référence nommée (`&rlm;`) rend un contrôle bidirectionnel ; décisions de Sabine : un `&` toujours échappé cassait les URL nues des tops avec requête | `&` dans les seules fiches de veille ; tout `&` échappé dans les tops |
| Une URL refusée si elle contient `::`, une référence de caractère ou un caractère caché en pourcents | un champ Dataview, ou un lien qui se lit autrement qu'il ne mène (CWE-451) | réécrire l'URL, ce qui change sa cible ; refuser un hôte en `xn--`, que des domaines légitimes utilisent |
| Une espace entre deux deux-points | Dataview lit le HTML rendu en mode lecture (recette de Sabine) ; son indexeur lit la source, où `\:\:` n'est pas un champ | un caractère invisible (U+2060), qui tromperait un copier-coller |
| Le marqueur de liste en tête échappé | une affirmation ou un titre « 2026. Bilan » imbriquait une liste (constat 7) | le laisser, comme l'emphase |
| La fenêtre entre contrôle et renommage acceptée, #295 | décision de Sabine : seuls deux lancements qui se chevauchent la déclenchent | changer `write_file_atomically` et la règle 2 de `conventions.md` dans cette PR |
| `describe_os_error` dans `commands/run_log.py`, `locate_first_error` dans `core/quoting.py` | troisième occurrence (constat 9) ; un outil générique à côté de `without_values` (constat 10), qui cite une clé venue de l'entrée (constat 7 de la seconde revue) | trois copies ; un outil dans `etl/ai_api_client.py` |
| `capped_kind` validé par `ItemKind` | un mot que YAML lit comme nul ou booléen ferait passer une fenêtre coupée pour entière | le motif `[a-z_]{1,64}` |
| Lecture de 240 s, sans nouvelle tentative, sans borne de taille | au-dessus des ~220 s d'une demande ; la borne de taille : risque accepté par Sabine pour le POC | relancer après un 503 (une attente sans borne) |
| Clés du frontmatter en anglais, texte en français | règle de Sabine : les identifiants en anglais, le texte rédigé en français | garder `classement`, `releve`, `depots` pour les tops |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `tests/etl/test_ai_api_client.py` (44 tests) | réglages refusés par leur nom, jamais leur valeur ; la clé dans `Authorization`, le corps `{}`, les délais ; chaque panne nommée, sans URL ; une valeur reçue hors règle citée tronquée et échappée ; une réponse hors schéma ou hors listes refusée par sa place |
| `tests/etl/test_digest_sheets.py` (90 tests) | la fiche attendue octet par octet ; un titre et une affirmation piégés écrits en texte, sur leur ligne ; les `facts` jamais écrits ; 26 URL refusées, 6 acceptées ; `::` absent du texte rendu ; `&` et le marqueur de liste échappés ; les refus avant la demande |
| `tests/etl/test_vault_files.py` (24 tests), `test_a_character_reference_in_a_description_is_written_as_text` | écrite une fois, une fiche vue jamais réécrite ; liens et dossier sous le nom refusés ; aucun temporaire laissé ; `&` échappé dans une description de top |
| `tests/test_cli.py`, tests `digest` (18) | les codes 0, 1, 2, 4, 143 ; aucune demande quand une fiche du jour existe ; la clé absente des sorties et du journal sur un 401 |
| `tests/test_cli.py`, tests `write_tops` et `test_a_part_that_failed_gives_4_beside_a_part_done_and_1_alone` | la règle « même résultat, même code » |
| `tests/architecture/test_layers.py`, `test_etl_imports_neither_the_data_api_nor_the_ai_api` | `etl` n'atteint jamais le code des API |
| Démonstration sur le Mac (base de test, replay, coffre neuf) | trois fiches écrites (0) ; relance le même jour : `sheet_exists`, aucune demande (2) ; clé refusée : aucune fiche, la variable nommée (1) ; les trois clés absentes de toutes les sorties et de tous les journaux |
| Recette de Sabine dans Obsidian (Dataview 0.5.68, JavaScript activé), trois fiches | témoin positif : 22 pièges actifs ; témoin négatif : propre ; fiche testée : 21 pièges sur 22 en texte, aucun JavaScript exécuté ; le champ Dataview, actif en mode lecture, a donné l'espace entre deux deux-points |
| `/security-review` (deux étapes : recherche, puis filtre) | aucune vulnérabilité HIGH ni MEDIUM ; un constat LOW filtré, `::` dans une URL de source, corrigé quand même |
| `uv run pytest` (2 261 tests), `ruff check --no-cache`, `ruff format --check`, `mypy --strict` | les contrôles de la CI, sur chaque commit |

## Ce que tu dois pouvoir défendre

1. **Pourquoi échapper, alors que l'API IA filtre déjà les liens (contrôle 6) ?** Le contrôle 6 ne
   lit que les affirmations, pas les titres, qui sont des données de source ; et il laisse passer
   `$=`, `#`, `%%`, `::` et une adresse mail. L'échappement à l'écriture est la seconde défense, au
   point d'usage (`digest_sheets.py:143`).
2. **Pourquoi refuser une URL au lieu de l'échapper ?** Dans un lien automatique `<…>`, une barre
   oblique n'est pas un échappement (CommonMark § 6.5) : seul un refus garantit que l'URL ne sort
   pas de ses chevrons (`digest_sheets.py:40`).
3. **Que se passe-t-il si la clé est refusée ?** Rien n'est écrit, le message nomme
   `KB_AI_API_KEY_KB_DIGEST`, jamais la clé, et la commande sort en 1 : la requête est partie
   (`digest_command.py`, `describe_remedy`).
4. **Que se passe-t-il si `veille/` est un lien vers un autre dossier ?** `kb digest` le voit
   avant toute demande et sort en 2 ; il le revoit juste avant chaque écriture
   (`vault_files.py:43`).
5. **Pourquoi un top sans relevé compte-t-il comme abouti ?** Il est allé au bout sans échec,
   comme une source sans rien de neuf pour `kb collect` : la règle est la même pour les trois
   commandes (`exit_codes.py:52`).

## Zones non vérifiées

- **Le rendu réel dans Obsidian** : la recette à trois fiches, faite par Sabine, en est la seule
  preuve (résultat dans la PR). L'échappement suit CommonMark 0.31.2 et GFM, mais Obsidian est un
  logiciel fermé.
- **Une fiche créée entre le contrôle et le renommage** serait écrasée par `os.replace` (constat 1
  de la revue de code) : la fenêtre est de quelques millisecondes ; acceptée pour le POC, #295.
- **Le champ Dataview, `&` et le marqueur de liste** : corrigés après la première recette, vérifiés
  par les tests et par la lecture du code de Dataview ; la seconde recette de Sabine en apportera
  la preuve dans Obsidian.
- **La grammaire de la RFC 3986** a été recoupée sur des pages qui la reproduisent, pas sur le
  texte de l'IETF.
- **La chaîne réelle en CI** (`kb digest` → API IA → API de données → modèle) n'est pas testée
  ici : les tests passent par `httpx2.MockTransport`, la démonstration par le replay. C'est #26.

## Ce qui reste

- Une borne de taille de la réponse lue, avant la mise en ligne du 08/11, dans `core/outbound.py`.
- Publier une fiche sans écraser, et écrire par descripteurs (#295).
- Relancer les seuls sujets en échec le même jour (un filtre de sujets dans `POST /digests`).
- Où tournent `kb digest` et `kb write-tops` en ligne, avec le coffre (décision ouverte).
- La chaîne en CI (#26), la fidélité (#207), le vrai modèle (#210).
- Les commits de la liste injectée antérieurs à `b7e223b` et les fichiers qu'ils touchent
  appartiennent aux PR déjà fusionnées (#156 et avant) : cette note ne couvre que les commits de
  la branche.

## Sources

| Source | Consultée | Pour |
|---|---|---|
| [CommonMark Spec 0.31.2](https://spec.commonmark.org/0.31.2/), § 2.4 et § 6.5 | 2026-10-21 | toute ponctuation ASCII s'échappe ; aucun échappement dans `<…>` |
| [GitHub Flavored Markdown Spec](https://github.github.com/gfm/), § 6.9 | 2026-10-21 | les liens automatiques étendus : `www.`, `http://`, adresse mail, `mailto:`, `xmpp:` |
| [Dataview, requêtes en ligne DQL et JavaScript](https://blacksmithgu.github.io/obsidian-dataview/queries/dql-js-inline/) | 2026-10-21 | `` `= …` ``, `` `$= …` ``, `dataviewjs`, désactivés par défaut |
| [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986), § 2, grammaire recoupée par une recherche web | 2026-10-21 | les caractères permis d'une URL |
| httpx2, documentation par Context7 (`/pydantic/httpx2`) | 2026-10-21 | les délais `connect`, `read`, `write`, `pool` ; `MockTransport` |
| [AWS CLI, return codes](https://github.com/aws/aws-cli/blob/v2/awscli/topics/return-codes.rst) ; [`gh auth status`](https://cli.github.com/manual/gh_auth_status), consultés par time-knight | 2026-10-21 | 253 contre 254 : configuration absente contre service qui refuse |
| Code de Dataview 0.5.68 (`main.js` et son worker, du coffre de recette) : `replaceInlineFields`, `extractInlineFields`, `parseMarkdown` ; documentation par Context7 (`/blacksmithgu/obsidian-dataview`, « Inline Fields ») | 2026-10-21 | le mode lecture lit le HTML rendu ; l'indexeur lit la source ; un champ du corps est indexé comme le frontmatter |
| [CWE-367](https://cwe.mitre.org/data/definitions/367.html), [CWE-59](https://cwe.mitre.org/data/definitions/59.html), [CWE-116](https://cwe.mitre.org/data/definitions/116.html), cités par le relecteur de sécurité | 2026-10-21 | la fenêtre entre contrôle et écriture ; le lien suivi ; l'encodage de la sortie |
| [OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) (`conformite.md`) | 2026-10-15 | LLM10 : la sortie du modèle est une entrée non fiable |
