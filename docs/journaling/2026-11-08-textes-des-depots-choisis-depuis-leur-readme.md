# Les textes des dépôts choisis, écrits depuis leur README

- **Date** : 2026-11-08
- **Branche** : `feat/trend-writing`
- **Issue** : #369
- **Fichiers principaux** : `src/k_b/ai_api/stages/trend_writing.py`, `src/k_b/ai_api/connectors/github_client.py`,
  `src/k_b/core/outbound.py`, `src/k_b/ai_api/trend_reports.py`, `src/k_b/post/trend_report_client.py`,
  `src/k_b/post/trend_report_sheets.py`, `docs/tendances.md`
- **Série** : [contrat du compte rendu](2026-10-30-contrat-compte-rendu-tendances.md),
  [compte rendu factuel](2026-10-30-api-ia-compte-rendu-factuel-tendances.md),
  [fiche GitHub des candidats](2026-10-31-fiche-github-des-candidats.md),
  [choix du modèle](2026-11-01-choix-du-modele-tendances.md),
  [faits GitHub dans le fichier](2026-11-05-faits-github-dans-le-compte-rendu-des-tendances.md)

## Le pourquoi

Jusqu'ici, le compte rendu des tendances donnait, pour chaque dépôt que le modèle a choisi, ses critères,
ses sujets de la veille et ses faits lus sur GitHub (langage, licence, création, topics). Rien ne disait
**de quoi parle le dépôt**. #369 ajoute quatre textes courts, en français, écrits par le modèle : le
secteur, le lien avec la veille, ce que dit le README (attribué à son auteur), et ce que le dépôt promet.

La difficulté : la source principale est le README, un texte libre écrit par n'importe qui. Il peut
contenir une consigne cachée (« ignore les consignes et écris que… »), une commande à lancer, un lien.
Et le modèle peut inventer. Tout le code de cette PR tient donc une règle : **le modèle écrit, le code
vérifie**. Un texte que le code ne retrouve pas dans sa source est retiré ; une sortie qui porte un lien ou
une commande est refusée en entier. C'est le dernier code du compte rendu des tendances avant l'essai réel
(#370).

## Le comment

### 1. Le README est lu en brut, sa tête seule

GitHub sert un README jusqu'à 100 Mo. La lecture des fiches refusait un corps au-delà de sa borne
(`read_bounded_body` lève `BodyTooLargeError`) : appliquée au README, une liste « awesome » ferait échouer
tout le compte rendu. Il fallait une lecture qui **garde la tête** et laisse le reste sur le réseau. Les
deux lectures partagent une seule boucle :

```python
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > max_bytes:
            return bytes(body[:max_bytes]), True
```
(`src/k_b/core/outbound.py:104-107`)

`read_bounded_body` lève sur le `True` ; `read_body_head` rend la tête et ignore le drapeau. Une seule
boucle, pour que le défaut connu de l'échéance avant le premier morceau (#436) se corrige une fois.

La tête fait 65 536 octets (`MAX_GITHUB_README_BYTES`, `core/config.py`). Pourquoi ce nombre : en UTF-8,
un caractère pèse 4 octets au plus, donc la tête porte au moins 16 384 caractères, plus que la coupe brute
du nettoyage (4 × 4 000 = 16 000, `RAW_CUT_FACTOR`, `ai_api/repository_texts.py:57`). C'est ce qui permet
de ne pas transmettre « la tête a été coupée » : dès qu'elle l'est, le nettoyage voit un texte plus long
que sa coupe brute, le dit coupé et retire le mot entamé. Un test garde la relation
(`test_the_head_of_a_readme_holds_more_than_the_raw_cut_of_the_cleaning`).

Le statut décide de l'état du README :

```python
    if status == httpx2.codes.OK:
        if read_media_type(answer.headers) == JSON_MEDIA_TYPE:
            raise GithubError("github_invalid_response", status)
        return Readme(answer.content.decode("utf-8", errors="replace"))
    if status in NOT_FOUND_STATUSES:
        return "absent"
```
(`src/k_b/ai_api/connectors/github_client.py:197-202`)

La requête demande le fichier brut (`Accept: application/vnd.github.raw+json`) ; si GitHub sert quand même
la forme JSON en base64, le code la refuse au lieu de l'envoyer au modèle. 404 et 410 donnent `absent` ;
un 403 qui n'est pas une limite, un 451 ou une redirection donnent `refused` (le 403 compte parmi les 3
refus des fiches). Tout le reste (401, limite, deux 5xx, délai, budget) lève une `GithubError`. Le chemin
est fait par `to_repository_path` (`github_client.py:214`), depuis le nom tiré du `ref`, jamais depuis la
sortie du modèle : un nom avec `.` ou `..` lève, sans citer le nom.

### 2. Tous les README avant la première rédaction, et une erreur GitHub n'arrête que les textes

Les fiches et les README partagent **une seule** `GithubReading` (`trend_reports.py`), donc un budget de
70 requêtes (60 fiches, 5 README, 5 relances) et un compteur de refus. Les README sont tous lus avant la
première rédaction :

```python
        for repository in chosen:
            if failure is not None or not reading.deadline.allows_llm_request():
                readmes.append(None)
                skipped += 1
                continue
```
(`src/k_b/ai_api/trend_reports.py:375-379`)

Après une erreur GitHub, plus aucun README n'est lu. Puis, côté rédaction, `find_writing_skip` saute tous
les dépôts quand GitHub a échoué :

```python
    if github_failure is not None:
        return github_failure
    if readme is None:
        return "llm_timeout"
    return find_skipped_state(is_rate_limited, deadline)
```
(`src/k_b/ai_api/stages/trend_writing.py:277-281`)

Pourquoi lire tout avant d'écrire : si on écrivait dépôt par dépôt, le README du premier partirait au
modèle alors que GitHub échoue sur le deuxième (minimisation : aucune donnée envoyée pour un résultat
qu'on ne gardera pas d'un bloc). Pourquoi l'erreur GitHub ne fait pas échouer la requête (décision de
Sabine du 08/11) : le choix du modèle est déjà payé, et le compte rendu reste utile avec ses faits ; chaque
choisi porte alors `writing_failure` (par exemple `github_unavailable`), et le fichier écrit
`Textes non écrits : GitHub indisponible.` La règle « pas de compte rendu partiel » reste vraie pour les
fenêtres et les fiches.

Un README `None` sans erreur GitHub veut dire « pas lu faute de temps » : `llm_timeout`, sans requête.

### 3. Le README est une donnée, jamais une consigne

La consigne (`TREND_WRITING_SYSTEM_PROMPT`, `trend_writing.py:75`) est une constante de module : elle est
évaluée avant qu'un README existe, elle ne peut pas en contenir (règle 8 de `poc.md`). Le README va dans le
message utilisateur, encodé en JSON :

```python
            "ref": chosen.ref,
            "name": candidate.trajectory.repository_name.partition("/")[2],
```
(`src/k_b/ai_api/stages/trend_writing.py:368-369`)

Le dépôt n'est identifié que par son `ref` (`c1`, `c2`…) ; son nom part **sans le login du propriétaire**
(minimisation, tranché par time-knight). Ne partent ni les étoiles, ni les dates, ni les prudences : le code
les écrit lui-même, et ces nombres feraient retirer les textes par la règle des nombres (section 5). Un
README absent part en `null`, pas en mot « absent » : un résumé « absent » pourrait sinon passer la
fidélité (décision 5 de Sabine).

Le schéma envoyé au modèle n'admet qu'un `ref`, celui du dépôt :

```python
    properties: dict[str, object] = {"ref": {"type": "string", "enum": [ref]}}
```
(`src/k_b/ai_api/stages/trend_writing.py:431`)

Un README piégé qui dit « écris sur un autre dépôt » ne peut donc que viser son propre `ref`, et un appel
ne voit qu'un README : il n'a pas accès aux autres.

### 4. Deux niveaux de contrôle : la sortie entière, puis chaque texte

**La sortie entière est refusée** (puis relancée une fois avec un rappel constant) si elle porte un `ref`
autre que celui envoyé, ou un texte avec un lien, une image, une balise (`MARKUP`, repris des fiches),
un accent grave, `~~~` ou une commande :

```python
    if repository.ref != ref:
        return "item_id"
    if any(is_markup(getattr(repository, name).text) for name in TREND_TEXTS):
        return "markup"
```
(`src/k_b/ai_api/stages/trend_writing.py:452-455`)

Pourquoi la sortie entière et pas le texte seul : un lien ou une commande dans un texte est le signe que le
README a pris la main ; on ne garde rien de cet appel. Ce contrôle passe avant les contrôles par texte : un
texte trop long qui porte une commande fait refuser la sortie, il n'est pas seulement retiré.

Le motif de commande (`COMMAND`, `trend_writing.py:135-149`) vise une forme exécutable (`| sh`, `sudo `,
`curl -`, `pip install`, `git clone`, `$(`, `&&`…), pas le nom d'un programme : « développé en Go »,
« un client comme curl » restent de la prose.

**Puis chaque texte**, son premier refus le retire seul :

```python
    if not is_within_text_bounds(name, written):
        return OUT_OF_BOUNDS
    if not sources:
        return NO_SOURCE
    missing = next((index for index, is_ok in enumerate(found) if not is_ok), None)
```
(`src/k_b/ai_api/stages/trend_writing.py:503-507`)

L'ordre est celui du contrat (`docs/tendances.md`, « Rédaction ») : bornes, texte sans source
(`no_source`, par exemple un secteur alors que le dépôt n'a aucun topic), fait introuvable, CVE ou GHSA,
nombre non déclaré, texte maquillé. Chaque fait déclaré est cherché **dans son texte et dans la seule source
de ce texte** (`is_fact_found`, `trend_writing.py:539`) : le secteur dans les topics, le lien avec la veille
dans la définition des sujets du dépôt, le résumé dans le README, la promesse dans le README ou la
description. La recherche réutilise `normalize`, `is_found` et `to_searched_text` de la fidélité des fiches,
avec la longueur de coupe en paramètre (4 000 pour le README) ; le masque `[email]` y est retiré comme
`[url]` et `@user`, pour qu'un masque de K-B ne soit jamais la source d'un fait.

Un texte vide sans fait est permis : il dit « rien à dire », il n'est ni écrit ni retiré (décision 2 de
Sabine). Un texte qui passe tous les contrôles mais n'a ni lettre ni chiffre une fois normalisé compte pour
vide (`is_empty`, `trend_writing.py:487`) ; il est testé **après** les contrôles, pour qu'un texte de seuls
caractères invisibles soit d'abord retiré comme maquillé (correction de la revue du 08/11).

Une rédaction en échec (sortie refusée deux fois, filtre de contenu, délai) ne retire que les textes de son
dépôt ; ses faits restent, et les autres dépôts sont écrits. Après un 429, plus rien n'est envoyé.

### 5. La règle des nombres

Un modèle invente volontiers un nombre (« 10 000 utilisateurs »). Plutôt qu'une liste de motifs de nombres,
toujours incomplète, le code retire du texte chaque fait déclaré et trouvé, puis regarde s'il reste un
chiffre :

```python
    remaining = text
    for fact in sorted(facts, key=len, reverse=True):
        remaining = remove_between_limits(remaining, fact)
    return any(char.isdigit() for char in remaining)
```
(`src/k_b/ai_api/stages/trend_writing.py:554-557`)

Le plus long d'abord, pour que « Python 3.12 » soit retiré avant « 3 ». Le retrait respecte les limites
de mot (`joins_a_word`, de la fidélité) : le fait « 3 » ne retire pas le 3 de « 30 ». Le texte est
normalisé en NFKC avant : `²` et `３` deviennent des chiffres et sont vus.

### 6. `kb` relit la réponse, puis écrit en texte neutre

`kb` tient la réponse de l'API IA pour non fiable. Chaque texte passe un schéma fermé : borné comme dans
l'API IA, et sans caractère qui cache (catégories Cf sauf U+200D, Co, Cn ; `check_visible_text`,
`post/trend_report_client.py:94`). Puis `kb` refuse une réponse qui se contredit (des textes écrits avec un
échec, un texte retiré encore présent, un résumé sans README, un secteur sans topic…), en citant la place et
le contrôle, jamais une valeur (`refuse_inconsistent_writings`, `trend_report_client.py:428`).

Le rendu suit la décision 1 de Sabine :

```python
        if name in chosen.texts_removed:
            lines.append(f"  {label} : {NOT_RETAINED}.")
        elif text is not None:
            lines.append(f"  {label} : {neutralize_digest_text(text)}")
```
(`src/k_b/post/trend_report_sheets.py:320-323`)

Deux espaces d'indentation gardent les lignes dans l'élément de liste du dépôt. `neutralize_digest_text`
met le texte sur une ligne et échappe ce qui ferait un lien, une balise, un champ Dataview ou une liste
dans Obsidian. Un README `absent` ou `refused` remplace la ligne du résumé par `README : absent.` ou
`README : non servi par GitHub.`, quel que soit le texte rendu.

Les traces et les métriques ne portent jamais de nom de dépôt : un span `read_readmes` de comptes, un span
`write_trend` par choisi (son `ref`, l'état du README, les noms des textes gardés, les codes des retraits) ;
une ligne de métrique par rédaction envoyée, à l'étape `write_trends`. `kb` journalise une rédaction en
échec par sa place (`writing of chosen.0 not made: …`), jamais par son nom.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Lecture du README (C1 du plan) | Brut, tête de 65 536 octets, reste non téléchargé | JSON base64 : corps entier à lire, puis à décoder ; refus au-delà d'une borne : un long README ferait échouer le compte rendu ; en-tête `Range` : non documenté par GitHub |
| Mode tête pour le seul 200 | Une autre réponse (une limite 403 ou 429) est lue entière, pour que son message de limite soit lu (relecture du plan, constat 16) | Tête pour toute réponse : un message de limite coupé serait mal classé |
| Ordre README / rédaction (C3) | Tous les README, puis toutes les rédactions | Dépôt par dépôt : un README partirait au modèle pour un appel qu'une erreur GitHub suivante rendrait inutile (minimisation) |
| Erreur GitHub sur un README (décision 3 de Sabine) | Le compte rendu est écrit, les textes non écrits, les faits gardés | Faire échouer la requête : le choix déjà payé perdu. Le plan proposait ce dernier, avec une ligne de métrique écrite quand même (C4) ; C4 tombe avec la décision |
| Type de `writing_failure` (choix interne, laissé à la session) | Un seul champ, `LlmFailure \| GithubState`, les deux familles disjointes par leur préfixe `llm_` / `github_` | Deux champs : deux lignes possibles dans le fichier, et un contrôle croisé de plus dans `kb` pour interdire les deux à la fois |
| Ce qui part au modèle (décision 5 de Sabine, nom sans login par time-knight) | Le nom sans le propriétaire, les topics, critères, sujets, description et README nettoyés ; `null` si pas de README | Étoiles, dates et prudences : rendues par le code, elles feraient retirer les textes par la règle des nombres ; le nom complet : le login est une donnée personnelle inutile au texte |
| Règle des nombres (C9) | Retirer les faits trouvés, puis chercher un chiffre | Une liste de motifs de nombres : toujours incomplète |
| Contrôles de la sortie (C6) | Les états existants `item_id` et `markup`, leur rappel propre | Un état `FailedCheck` nouveau : un rappel de plus dans chaque table des étapes |
| Fidélité (C10) | `to_searched_text(field, max_chars)` réutilisée, masque `[email]` retiré pour tous | Une copie de la fonction : deux règles qui divergeraient |
| `find_skipped_state` (C11) | Passée de `digests.py` à `stage_calls.py`, partagée par les fiches et la rédaction | La copier |
| Étape de métrique (C13) | `write_trends`, et `FailedSubjectSchema.stage` typé par `DigestStage` (`classify`, `write`) | Réutiliser `write` : les taux des fiches et des tendances se mêleraient |
| Réponse (C14, version 0.12.0) | `readme`, `texts`, `texts_removed` (noms, dans l'ordre), `writing_failure` | Un simple compte de textes retirés : le fichier ne pourrait pas dire lequel |
| Texte vide (décision 2 de Sabine) | Permis, ni écrit ni retiré ; un texte écrit sans source est retiré (`no_source`) | Textes jamais vides (borne de l'architecte du 29/10) : pousserait le modèle à écrire ce que la source ne dit pas |
| Limites (décision 4 de Sabine) | Écrites dans le contrat : blocs de code indentés gardés, « version récente » et « prudence en faits » par la consigne seule, nombre en lettres et « Installez X » en prose non vus, `sudo` et `npx` refusés même en prose, gestionnaires hors liste (`conda`, `poetry`…) non vus, README lu par le nom sans contrôle de l'`id` | Les coder : un analyseur Markdown, un détecteur de nombres en lettres, un appel de plus à GitHub, pour des risques bornés par le rendu neutre du coffre |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_trapped_readme_is_in_no_system_message_even_on_the_retry` (`tests/ai_api/test_trend_writing.py:229`) | Le texte piégé n'est dans aucun message `system`, même à la relance ; il atteint bien le message utilisateur (témoin) |
| `test_a_readme_aiming_at_another_repository_leaves_the_other_texts_alone` (`tests/ai_api/test_trend_report_router.py:1397`) | Un README qui vise un autre dépôt ne passe pas dans l'appel de cet autre dépôt, dont les textes restent |
| `test_markup_a_backtick_a_fence_or_a_command_refuses_the_whole_output`, `test_prose_that_names_a_tool_is_not_a_command` | Lien, accent grave, `~~~`, commande refusent la sortie ; le nom d'un outil en prose passe |
| `test_a_fact_not_found_in_the_source_of_its_text_removes_it_alone`, `test_a_fact_of_the_sector_is_searched_in_the_topics_sent_only` | Un fait introuvable retire son texte seul ; un fait se cherche dans la seule source de son texte |
| `test_a_number_not_declared_as_a_found_fact_removes_its_text`, `test_a_cve_or_ghsa_removes_its_text`, `test_a_disguised_text_is_removed`, `test_a_text_without_source_is_removed` | Les retraits 2 à 6 du contrat |
| `test_a_writing_that_fails_removes_the_texts_of_its_repository_alone` (stage et route) | Une rédaction en échec ne retire que les textes de son dépôt ; ses faits restent |
| `test_a_failure_of_github_on_a_readme_leaves_the_texts_unwritten_and_keeps_the_facts` (route, paramétré : 401, 429, 403 de limite, deux 5xx, délai, budget) | Décision 3 : un 200, les textes non écrits, les faits et le choix gardés |
| `test_a_readme_keeps_its_head_up_to_its_bound_the_rest_unread`, `test_the_head_of_a_gzip_body_is_kept_once_decoded`, `test_a_readme_served_as_json_is_refused_by_its_exact_media_type` | La tête est gardée, le reste non lu, y compris compressé ; la forme JSON est refusée |
| `test_a_name_with_dot_or_dotdot_never_makes_a_path`, `test_the_path_of_a_readme_is_made_from_the_name_of_its_ref` | Le chemin vient du nom tiré du `ref`, jamais du modèle ; `.` et `..` refusés |
| `test_with_content_none_no_content_record_is_sent`, `test_with_content_all_only_the_body_of_a_content_record_holds_a_repository`, `test_neither_the_traces_nor_the_logs_hold_a_repository`, `test_the_readmes_and_the_writings_are_spans_of_counts_and_refs` | `KB_TRACE_CONTENT` : rien avec `none`, le contenu dans le seul corps avec `all` ; ni nom de dépôt ni `repository_id` dans les traces et les journaux |
| `test_the_texts_of_a_repository_chosen_are_written_under_its_facts`, `test_a_text_of_the_model_makes_neither_link_nor_markup_in_the_vault` (`tests/post/test_trend_report_sheets.py`) | Le rendu exact des lignes, et l'échappement de ce qui ferait un lien, une balise ou une liste |
| `test_texts_that_contradict_the_writing_are_refused`, `test_a_text_beyond_its_bound_or_with_a_hidden_character_is_refused_never_quoted` (`tests/post/test_trend_report_client.py`) | `kb` refuse une réponse qui se contredit, sans citer de valeur |
| `uv run pytest` à `04399b0` : 4034 passed, 328 deselected ; ruff, format, `mypy --strict` verts ; OpenAPI régénérée | Les contrôles du dépôt |
| Mutations du groupe 3 (copie sans `.venv` ni `__pycache__`) : `COMMAND` retiré → 19 échecs ; règle des nombres neutralisée → 5 ; saut GitHub retiré → 1 ; tous les topics cherchés → 1 ; `no_source` retiré → 4 | Les tests de la rédaction voient ces cinq défauts. Ils compensent un écart de méthode : au groupe 3, le code a été écrit avant le test rouge (rouge rejoué ensuite sur une copie sans le code : `ModuleNotFoundError`) |

## Ce que tu dois pouvoir défendre

1. **Un README peut-il faire écrire au modèle ce qu'il veut dans le coffre ?** Il peut l'essayer : il est
   envoyé au modèle. Mais il n'est jamais dans la consigne (constante, règle 8), un appel ne voit qu'un dépôt
   et ne peut répondre que sur son `ref` (schéma à `enum` d'une valeur), un lien ou une commande fait refuser
   toute la sortie, et chaque texte doit retrouver ses faits dans sa source. Ce qui passe reste un texte
   neutralisé dans Obsidian : rien ne s'y exécute (`trend_writing.py:431,452-455` ;
   `trend_report_sheets.py:323`).
2. **Pourquoi ne pas faire échouer le compte rendu quand GitHub échoue sur un README ?** Le choix est déjà
   payé et les faits valent seuls ; Sabine a décidé le 08/11 que la règle « pas de compte rendu partiel »
   vaut pour les fiches. Le fichier dit pourquoi les textes manquent (`find_writing_skip`,
   `trend_writing.py:277`).
3. **Pourquoi 65 536 octets, et pas 16 000 ?** Parce que 16 000 est un nombre de caractères : en octets,
   un caractère en pèse jusqu'à 4. 65 536 octets assurent au moins 16 384 caractères, plus que la coupe
   brute de 16 000 : le nettoyage voit toujours la coupe et retire le mot entamé (test de la relation).
4. **Pourquoi la règle des nombres plutôt qu'une liste de formats ?** Une liste oublie toujours une forme
   (`1,2k`, `²`, `３`) ; « tout chiffre doit être un fait trouvé » est fermé par construction
   (`has_undeclared_number`, `trend_writing.py:550`). Le prix : un nombre écrit en lettres n'est pas vu
   (limite écrite).
5. **Que reçoit le modèle sur une personne ?** Pas le login du propriétaire ; un README nettoyé, ses
   adresses mail, URL et `@login` masqués. Un nom en texte libre peut y rester : c'est écrit au registre
   (`docs/registre-traitements.md`), et `KB_TRACE_CONTENT` reste à `none` avant la signature du DPA de
   Grafana Labs.

## Zones non vérifiées

- **Aucun appel réel** à GitHub ni au modèle : tout est simulé. Le type de média d'un README servi en brut
  n'est pas documenté par GitHub (recherche du 08/11) ; seul `application/json` est refusé. La fermeture
  d'un flux gzip avant sa fin est testée sur un transport simulé, pas sur GitHub.
- **La fidélité sur des textes français tirés de README anglais** : les faits doivent être recopiés mot pour
  mot ; le taux de textes retirés n'est pas mesuré. #370 le mesure, avec la fréquence de Prompt Shields sur
  des README et la durée sous 200 s (60 fiches, le choix, 5 rédactions).
- **`TREND_WRITING_MAX_COMPLETION_TOKENS = 2048`** repose sur une estimation de 3 caractères par jeton
  (supposée, écrite dans le commentaire) ; le schéma strict à 3 niveaux n'a pas été essayé contre Azure.
- **Le rendu déterministe** des textes est prouvé par l'égalité exacte des lignes rendues ; le test « même
  réponse, mêmes octets » (`test_the_same_response_and_instant_give_the_same_bytes`) porte sur un compte
  rendu sans choisi.
- **`read_body_head` hérite du défaut #436** : rien n'est borné avant le premier morceau décodé.
- **Le nettoyage d'un README** coûte du temps sans contrôle de l'échéance pendant qu'il tourne, et un README
  lent peut finir en `github_timeout` (limite écrite, mesurée par #370).
- **`/security-review` exclut par sa règle l'injection de consignes** : ce risque n'a pas été jugé par cette
  revue ; il est tenu par les défenses ci-dessus et prouvé par les deux premiers tests du tableau.

## Ce qui reste

- #370 : l'essai réel, qui mesure les retraits, Prompt Shields et la durée, et relève le type de média.
- #466 : `llm_timeout` sans requête envoyée se lit « le modèle n'a pas répondu à temps » ; défaut déjà sur
  `main` pour le choix.
- #436 : l'échéance avant le premier morceau, pour les deux lectures.
- Les limites écrites au contrat (blocs indentés, nombres en lettres, prose impérative, gestionnaires hors
  liste, README lu par le nom) : à reprendre seulement si #370 montre qu'elles coûtent.
