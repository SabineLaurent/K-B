# Classer les items par sujet et rédiger les fiches

- **Date** : 2026-10-17
- **Branche** : `feat/digests-classify-and-write`
- **Issue** : #205
- **Fichiers principaux** :
  - `src/k_b/ai_api/digests.py` : le parcours ;
  - `classification.py` et `writing.py` : les deux étapes ;
  - `deadline.py` : l'échéance ;
  - `llm_client.py` et `data_api_client.py` : modifiés ;
  - `core/config.py` ;
  - `docs/fiches-veille.md` et le journal ADR.
- **Notes de la série** :
  - [appeler le modèle et son remplacement](2026-10-15-appeler-le-modele-et-son-remplacement.md) (#150) ;
  - [lire la veille par l'API de données](2026-10-15-lire-la-veille-par-l-api-de-donnees.md) (#204) ;
  - [spécifier les fiches de veille](2026-10-15-specifier-les-fiches-de-veille.md) (#203) ;
  - [brancher gpt-6-luna sur Foundry](2026-10-17-brancher-gpt-6-luna-sur-foundry.md) (#158), qui a mesuré les durées utilisées ici.

## Le pourquoi

L'API IA a une fonction : rendre une fiche de veille par sujet de la liste fermée, sur les items
d'une fenêtre de quelques jours. #204 savait lire la veille ; #150 savait appeler le modèle et
vérifier sa sortie. Il manquait **ce qu'on demande au modèle et ce qu'on fait de sa réponse** :

- ranger chaque item dans un sujet, ou le dire « non retenu » ;
- rédiger, pour chaque sujet, des affirmations en français qui citent leurs items ;
- et tenir le tout dans un temps borné, puisque l'API sera derrière l'ingress d'Azure Container
  Apps au 08/11.

Ce code n'a pas encore d'appelant de production : la route `POST /digests` viendra avec #156, qui
dépend aussi de #206 (filtre du Markdown). Ici, tout est prouvé sur le modèle de remplacement.

## Le comment

### 1. Le parcours : classer par lots, puis rédiger sujet après sujet

`build_digests` (`src/k_b/ai_api/digests.py:147`) lit comme une recette. D'abord `classify`
(`digests.py:222`) envoie les items par lots et construit `subject_by_item_id`. Ensuite, une
boucle sur les sujets **dans l'ordre de la liste**, un appel après l'autre :

```python
        if is_rate_limited:
            failed_subjects.append(
                FailedSubject(subject.name, "write", "llm_rate_limited")
            )
            continue
        if not deadline.allows_llm_request():
            failed_subjects.append(FailedSubject(subject.name, "write", "llm_timeout"))
            continue
```

(`digests.py:172-179`). Deux gardes avant tout envoi : un 429 déjà reçu, puis l'échéance. Dans les
deux cas, le sujet est nommé dans `failed_subjects` et **ses items ne partent pas** (minimisation,
RGPD art. 5.1.c). Un sujet sans item n'est pas rédigé ; un sujet en échec ne bloque pas les
autres. Un classement en échec, lui, fait échouer toute la demande (`ClassificationFailure`).

Pourquoi en série : la chaîne mesurée par #158 dure environ 98 s pour 8 sujets, juge compris, sous
les 240 s de l'ingress d'ACA. En série, le `replay` (qui donne ses réponses dans l'ordre) reste tel
quel, et il n'y a pas de pointe sous le quota de 140 000 jetons par minute.

### 2. L'échéance : un temps restant, appliqué à chaque requête

`Deadline` (`src/k_b/ai_api/deadline.py`) tient un instant sur une horloge monotone, injectable
pour les tests. Deux méthodes portent la règle :

```python
    def allows_llm_request(self, wait_seconds: float = 0) -> bool:
        """Whether a request to the model, sent after wait_seconds, still has the time it needs."""
        return self.remaining_seconds() - wait_seconds >= MIN_SECONDS_FOR_LLM_REQUEST
```

(`deadline.py:41-43`). La seconde, `cap` (`deadline.py:45`), ramène chaque délai d'httpx2 (pool,
connexion, écriture, lecture) au temps restant. `call_model` passe ce délai à chaque requête
(`llm_client.py:303`, `timeout=timeout`) et saute une nouvelle tentative qui ne tiendrait plus :

```python
    if (
        first.retry_wait_seconds is not None
        and deadline is not None
        and not deadline.allows_llm_request(first.retry_wait_seconds)
    ):
        call = summarize(attempts, len(user_message), time.perf_counter() - started)
        return replace(call, outcome="llm_timeout", output=None)
```

(`llm_client.py:237-243`). L'appel finit en `llm_timeout`, mais `summarize` a gardé ce que la
première tentative a observé : `http_status`, `retry_after_seconds`, `failed_check` (décision de
Sabine, Q2 du plan). `read_watch` exige la même échéance (paramètre sans défaut). Elle est contrôlée
avant chaque requête et entre deux morceaux lus (`data_api_client.py:283` et `:318`) ; au-delà,
`data_api_timeout`.

### 3. Le classement : projection, lots, contrôles 3 à 5

Le classement n'envoie que `item_id`, `kind`, `title` et le texte long coupé à 500 caractères par
`cut_value`, la même règle de coupe que #204 ; une `advisory`, sans texte long, est classée par son
titre (`classification.py:72`). Les lots sont remplis dans l'ordre de lecture :

```python
        is_full = len(batch) == MAX_ITEMS_PER_CLASSIFICATION_CALL or (
            len(encode_user_message(to_user_data(subjects_sent, candidate)))
            > MAX_CLASSIFICATION_INPUT_CHARS
        )
        if batch and is_full:
```

(`classification.py:128-132`). La longueur mesurée est celle du message réellement envoyé
(`encode_user_message`, partagé avec `call_model`). `if batch` empêche un lot vide quand un item
dépasse à lui seul le plafond. La sortie est revérifiée par le code, dans l'ordre de la spec :

```python
    if any(a.subject not in subject_names for a in output.assignments):
        return "subject"
    cited = [a.item_id for a in output.assignments] + output.not_retained
    if any(ref not in item_refs for ref in cited):
        return "item_id"
    if any(count > 1 for count in Counter(cited).values()):
        return "completeness"
```

(`classification.py:204-210`). Un item absent n'est pas un échec : `classify` le compte « non
retenu ». Un item d'un autre lot est refusé, car `item_refs` est celui de **ce** lot.

### 4. La rédaction : un schéma écrit à la main, les bornes dans la consigne

Azure refuse `minItems`, `maxItems`, `minLength` et `maxLength` en mode strict. Or le modèle Pydantic
qui revérifie la sortie porte les bornes de structure (`Field(max_length=MAX_CLAIMS)`,
`writing.py:103`), et un schéma dérivé de lui les écrirait. Le schéma envoyé est donc écrit à la
main (`build_writing_schema`, `writing.py:116`), avec l'`enum` des items de l'appel. Les bornes
sont dites dans la consigne, en texte littéral (règle 8 de `poc.md` : jamais une expression), et un
test vérifie que les nombres écrits sont ceux des constantes.

Le contrôle 4 (`check_writing`, `writing.py:153`) refuse :
- un item qui n'a pas été envoyé ;
- un item cité deux fois dans une même affirmation (`writing.py:161`) ;
- un fait qui cite un item absent de son affirmation.

Une borne d'affirmation dépassée (texte de 1 à 400 caractères, 1 à 10 faits de 3 à 120
caractères) ne fait pas échouer le sujet : `to_digest` retire l'affirmation et la compte
(`digests.py:276`). Le code calcule ensuite :
- `not_retained` : envoyés moins cités ;
- `items_uncited` : cités par le modèle, plus cités après les retraits (`uncited`, `digests.py:284`) ;
- `sources` : lues dans l'API de données, l'`url` rendue nulle hors `http(s)://` (`digests.py:321`).

### 5. Un 429 arrête les envois, quelle que soit la suite de l'appel

`LlmCall.saw_rate_limit` est vrai si **une** tentative a reçu un 429 (`llm_client.py:464`).
`build_digests` le lit pour un sujet en échec (`digests.py:207`) : un 429 suivi d'une nouvelle
tentative qui finit en délai dépassé, en 500, ou qui est sautée par l'échéance, arrête donc les
envois. Une nouvelle tentative qui a attendu le `Retry-After` puis reçu une réponse a surmonté le
429 : le sujet est rédigé, et les suivants partent. Le fournisseur accepte de nouveau, si bien
qu'aucun item ne part vers une réponse refusée. Il a fallu quatre passes de revue pour arriver à
cette forme ; le détail est dans « Choix ».

## Choix faits et options écartées

**Série sous échéance** (validé par Sabine le 17/10 ; journal ADR, « Fiches de veille : la durée
d'une demande »).
- Retenu : la série sous `DIGEST_REQUEST_TIMEOUT_SECONDS = 200`, soit 240 − 40 s de marge.
- Écarté :
  - le parallèle : environ 30 s, mais un `replay` à refaire et des 429 possibles ;
  - la tâche de fond : un état entre deux requêtes, contraire à la règle 7 de `poc.md`.
- Le pire cas (22 × 210 s) dépasse 240 s dans les deux formes : seule l'échéance borne.

**Où vit l'échéance.**
- Retenu : une constante de `core/config.py`, comme la spec le décidait.
- Écarté : `KB_DIGEST_REQUEST_TIMEOUT_SECONDS`, une variable d'environnement avec 200 par défaut,
  proposée par la seconde `/code-review`. La règle 2 de `poc.md` vise ce qu'ACA règle par conteneur
  (hôte, port, chemin), et sa « fenêtre de temps » désigne la fenêtre de la veille. L'échéance
  découle d'une limite de la plateforme qu'on ne règle pas, et une variable n'aurait pas de second
  usage (tranché par time-knight, délégation de Sabine du 15/10).

**L'échéance n'est pas une borne dure.**
- httpx2 n'a pas de délai total, et `cap` ramène chaque phase séparément.
- Une requête lancée avant l'échéance peut donc la dépasser de la somme de ses délais : 30 s au
  plus pour l'API de données ; pour le modèle, 20 s plus sa lecture, et sans borne pour une réponse
  envoyée au compte-gouttes.
- Ce point revoit le motif d'un rejet de l'ADR « Appel du modèle » (2026-10-15).
- Écarté : lire la réponse du modèle en flux, qui resterait dépassable.

**Le minimum de 10 s.**
- Retenu : 10 s, au-dessus de la rédaction la plus lente mesurée (9,3 s).
- Une rédaction longue (jusqu'à environ 60 s) lancée avec moins de temps peut encore être coupée.
- Écarté : 60 s, qui ferait tomber des sujets qu'on mesure à 8 s.

**Le contrôle de l'échéance avant l'envoi est dans l'étape, pas dans `call_model`.**
- Sinon, un appel sans requête donnerait une ligne de métrique à 0 tentative.
- `deadline` est un paramètre obligatoire de `call_model` (`Deadline | None`, sans défaut) : le
  juge (#223) ne peut pas l'oublier sans l'écrire.

**`saw_rate_limit` plutôt que l'état ou le statut HTTP.**
- 1re forme : l'arrêt sur `outcome == "llm_rate_limited"` ratait la nouvelle tentative sautée
  (`llm_timeout`).
- 2e forme : l'arrêt sur `http_status == 429` ratait un 429 effacé par une tentative suivante.
- Un booléen calculé sur toutes les tentatives règle les deux et sort les codes HTTP de
  `digests.py`.
- Lu seulement pour un sujet en échec : un 429 surmonté par la nouvelle tentative n'arrête rien.
  Écarté : arrêter après tout 429, même surmonté, qui ferait tomber des sujets rédigeables
  (tranché par time-knight, délégation de Sabine du 15/10).
- Écarté : la liste des statuts de chaque tentative (un booléen suffit au seul usage).
- On n'arrête pas sur `llm_unavailable` : cet état mêle pannes du fournisseur et refus propres à
  une requête (limite écrite dans la spec).

**Le `Retry-After` d'un classement en échec** n'est rendu qu'avec `llm_rate_limited` (503), jamais
avec un 504 ni un 502, comme la table des états nommés.

**Plafonds de sortie.**
- 8 192 jetons pour la rédaction, une **estimation** : environ 24 500 caractères au plus long, à
  3 caractères par jeton (hypothèse). C'est aussi le plus haut que permet le délai de 90 s au
  débit mesuré, avec 40 % de marge ; un test l'importe.
- 2 048 jetons pour le classement.

**Lots.** 50 items et 36 000 caractères au plus. Pas de calcul incrémental de la longueur :
300 encodages font environ 10 ms (mesuré).

**Consignes en anglais**, la sortie en français. Les rappels d'une nouvelle tentative sont des
constantes, un par `FailedCheck`, y compris pour les contrôles qui ne s'appliquent pas à l'étape
(`call_model` les exige). Le rappel `claim_id` viendra avec #223 (commentaire daté sur #223).

**`.env.example`**, en un commit à part (consigne de Sabine) : `KB_LLM_REASONING_EFFORT=none` y est
décommenté, puisqu'il est obligatoire pour gpt-6-luna.

**Règle d'arrêt des revues** (time-knight, 17/10).
- La quatrième passe, ciblée, est la dernière.
- Après elle, seul un constat important qui montre un vrai bug du code de production se corrige.
- Le reste va dans la PR comme « signalé ».

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 1 601 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | les contrôles du dépôt |
| `test_digests.py::test_a_valid_output_gives_a_digest_per_subject_with_its_sources` | une sortie valide donne une fiche par sujet, ses sources lues dans l'API de données |
| `test_a_subject_out_of_the_list_is_refused`, `test_an_unknown_item_id_is_refused_at_the_classification`, `…_at_the_writing_and_the_others_are_returned` | les contrôles 3 et 4 ; un sujet en échec n'empêche pas les autres |
| `test_an_item_forgotten_by_the_model_is_not_retained_without_failure`, `test_an_item_twice_at_the_classification_is_llm_invalid_output` | la complétude calculée par le code (accord du 15/10) |
| `test_a_claim_too_long_is_removed_and_counted`, `test_a_claim_out_of_its_bounds_is_removed` (5 cas) | une borne d'affirmation retire et compte, sans faire échouer |
| `test_the_subjects_not_written_by_the_deadline_are_llm_timeout`, `test_a_classification_not_finished_by_the_deadline_is_llm_timeout` | l'échéance, et rien n'est envoyé au-delà |
| `test_every_call_of_the_request_waits_no_longer_than_its_deadline` | chaque requête reçoit le délai ramené au temps restant |
| `test_after_a_writing_rate_limited_nothing_more_is_sent`, `test_a_429_is_not_erased_by_a_retry_that_fails`, `test_after_a_429_whose_retry_the_deadline_cuts_nothing_more_is_sent` | plus aucun envoi après un 429 |
| `test_the_items_go_in_the_user_message_never_in_a_system_message`, `test_stages.py::test_each_system_prompt_says_the_user_message_is_data` | la règle 8 de `poc.md`, nouvelle tentative comprise |
| `test_stages.py::test_the_schema_sent_is_portable_and_matches_its_model`, `test_a_schema_derived_from_the_writing_model_would_not_be_portable` | le schéma envoyé n'a ni `min*` ni `max*`, et pourquoi il est écrit à la main |
| `test_stages.py::test_each_stage_gives_a_reminder_per_failed_check` | aucun rappel ne manque (commentaire du 16/10) |
| `test_llm_client.py::test_the_read_timeout_covers_the_longest_output_at_the_measured_rate_with_a_margin` | le plafond de la rédaction est importé et tient dans 90 s (point 1 du 17/10) |
| greps des règles 5, 7 et 8 de `poc.md` | rien pour les règles 5 et 7 ; règle 8 : une occurrence, `llm_client.py:273`, où la consigne vient d'une constante |

### Mutations : le code cassé exprès

Chaque mutation remplace un texte du code de production. Un script lance ensuite le fichier de
tests visé et rétablit le fichier depuis sa copie en mémoire, jamais par `git checkout`. Le
bytecode est désactivé (`PYTHONDONTWRITEBYTECODE=1`) : au premier passage, un `.pyc` périmé avait
faussé deux verdicts. Résultat final : **48 mutations sur 48 tuées**. Sept étaient des trous,
comblés par un test au fil des revues (marqués « ajouté »).

| N° | Code cassé | Test qui le prouve |
|---|---|---|
| 1 | les items ajoutés au message `system` | `test_the_items_go_in_the_user_message_never_in_a_system_message` |
| 2, 6 | contrôle des sujets désactivé ; `enum` des sujets retiré du schéma | `test_a_subject_out_of_the_list_is_refused` |
| 3, 4, 5 | contrôle des `item_id` désactivé (classement, rédaction, faits) | `test_an_unknown_item_id_is_refused_…`, `test_a_fact_of_an_item_its_claim_does_not_cite_is_refused` |
| 7, 8 | `enum` des items vide dans le schéma envoyé | `test_the_schema_of_each_call_holds_the_items_of_this_call_only` (ajouté) |
| 9, 10, 11 | `not_retained`, `items_uncited`, `sources` mal calculés | `test_a_valid_output_…`, `test_a_claim_too_long_is_removed_and_counted` |
| 12, 13 | un item absent compté en échec ; un doublon toléré | `test_an_item_forgotten_…`, `test_an_item_twice_…` |
| 14 | l'état d'un sujet en échec écrasé | `test_a_subject_in_failure_is_named_and_the_others_are_returned` |
| 15, 16, 39 | borne du texte retirée ; 13 affirmations permises ; borne changée sans la consigne | `test_a_claim_too_long_…`, `test_more_claims_than_the_structure_allows_…`, `test_the_writing_prompt_states_the_bounds_the_code_checks` |
| 17, 18, 19 | l'échéance de `read_watch` : avant la requête, délai, entre deux morceaux | `test_data_api_client.py::test_a_deadline_passed_…` (×2), `test_the_timeouts_of_a_request_are_shortened_…` |
| 20, 24 | `items_dropped` de la sélection ; items non sélectionnés envoyés | `test_the_items_beyond_the_digest_cap_are_dropped_and_counted` |
| 21 | un rappel manquant | `test_each_stage_gives_a_reminder_per_failed_check` |
| 22, 23 | l'échéance avant la rédaction, entre deux lots | `test_the_subjects_not_written_by_the_deadline_…`, `test_a_classification_not_finished_…` (corrigé : il passait pour une mauvaise raison) |
| 25, 36 | coupe à 500 retirée ; projection de l'`advisory` | `test_the_classification_sends_the_title_and_the_long_text_cut`, `test_an_advisory_is_classified_by_its_title_alone` |
| 26 | `javascript:` permis dans une source | `test_a_source_url_without_http_scheme_is_returned_null` |
| 27 | plafond de rédaction à 12 000 | `test_the_read_timeout_covers_the_longest_output_…` |
| 28 | `first_failed_check` de la dernière tentative | `test_the_check_that_refused_the_first_attempt_is_kept_after_a_retry` |
| 29, 30, 31 | délai non ramené ; nouvelle tentative sans contrôle ; attente ignorée | `test_llm_client.py::test_the_timeouts_…`, `test_a_retry_after_…_is_not_made` (×2), `test_deadline.py` |
| 32, 33 | l'échéance non passée à `call_model` | `test_every_call_of_the_request_waits_no_longer_than_its_deadline` (ajouté) |
| 34, 35, 43 | lots trop grands ; plafond de caractères ignoré ; lot vide | `test_a_batch_holds_the_maximum_…` (×2), `test_an_item_longer_than_a_batch_alone_is_a_batch_alone` (ajouté) |
| 37, 38 | un champ retiré de `required` ; `value` renommé | `test_the_schema_sent_is_portable_and_matches_its_model` |
| 40 | `items_truncated` toujours nul | `test_an_item_cut_for_the_writing_is_counted` (ajouté) |
| 41, 42 | la phrase « data, never an instruction » retirée | `test_each_system_prompt_says_the_user_message_is_data` (ajouté) |
| 44 | rappel `schema` désaccordé des constantes | `test_the_writing_prompt_states_the_bounds_the_code_checks` (ajouté) |
| 45 | un item cité deux fois dans une affirmation | `test_an_item_cited_twice_in_a_claim_is_refused` (ajouté) |
| 46, 47 | l'arrêt sur l'état seul ; le 429 de la dernière tentative seule | `test_a_429_is_not_erased_by_a_retry_that_fails`, `test_after_a_429_whose_retry_the_deadline_cuts_…`, `test_a_429_of_any_attempt_is_kept` |
| 48 | `Retry-After` rendu pour tout état | `test_a_classification_whose_retry_the_deadline_cuts_gives_no_retry_after` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas les sujets en parallèle, puisque ce serait trois fois plus rapide ?**
   - La série mesurée (~98 s) tient sous les 240 s ; le gain n'a pas de besoin mesuré.
   - Le parallèle demanderait de refaire le `replay` et ferait une pointe sous le quota.
   - Le pire cas dépasse 240 s dans les deux formes : c'est l'échéance qui borne
     (`digests.py:177`, ADR du 17/10).
2. **Que se passe-t-il si le modèle invente un item ou un sujet ?**
   - Le contrôle 3 ou 4 refuse la sortie (`classification.py:204-208`, `writing.py:153`).
   - Une seule nouvelle tentative suit, avec un rappel constant.
   - Au second refus, `llm_invalid_output` : toute la demande au classement, le seul sujet à la
     rédaction.
   - Le mode strict n'est pas la défense : le code revérifie tout.
3. **Où est la défense contre l'injection d'instructions ?**
   - Les consignes sont des constantes ; les items ne vont que dans le message `user`, en JSON.
   - La sortie passe un schéma fermé et des `enum` revérifiés.
   - Un item piégé ne peut ni créer un sujet ni citer un item inventé.
   - Le filtre des liens et balises est #206 : rien ne rend encore ces fiches.
4. **Pourquoi le schéma envoyé n'est-il pas dérivé du modèle Pydantic ?**
   - Il contiendrait `maxItems` et `minItems`, qu'Azure refuse en mode strict.
   - Le `replay`, qui ignore le schéma, aurait laissé les tests verts et fait échouer chaque vrai
     appel.
   - Un test le montre : `test_a_schema_derived_from_the_writing_model_would_not_be_portable`.
5. **L'échéance de 200 s est-elle garantie ?**
   - Non, et c'est écrit : chaque délai d'httpx2 est ramené séparément.
   - Une requête peut dépasser de la somme de ses délais, et une réponse au compte-gouttes du
     modèle sans borne.
   - La marge de 40 s sous 240 s couvre les dépassements bornés (`deadline.py`, spec « Durée
     totale »).

## Zones non vérifiées

- **Rien n'a été appelé sur le vrai modèle** (règle de la mission) : les consignes `classify-1` et
  `write-1` n'ont jamais été lues par gpt-6-luna ; leur effet sur la qualité est à #210.
- Que **Azure accepte le schéma écrit à la main** en mode strict n'est vérifié que par la doc et par
  les sondes de #158, qui n'utilisaient pas ces schémas exacts.
- Le **rapport de 3 caractères par jeton** du plafond de 8 192 est une hypothèse ; la plus longue
  sortie réelle n'est pas mesurée.
- Les **mutations** lancent le fichier de tests visé, pas un test isolé : le tableau nomme le test
  écrit pour le cas, sans vérifier que c'est lui, et lui seul, qui échoue.
- Le **calcul du quota** par Azure (entrée plus `max_completion_tokens`) vient de la doc « Manage
  quota » ; #158 a observé que l'en-tête ne baissait que des jetons d'entrée.

## Ce qui reste

- **#156** :
  - la route `POST /digests`, qui calcule l'échéance à l'arrivée de la demande, la passe à
    `read_watch` puis à `build_digests` ;
  - la clé et la ligne de métrique. Elle choisit ses champs un par un, jamais `StageCall` en
    entier : `llm_call.output` et `DigestClaim.facts` portent du texte du modèle (constat de
    `/security-review`) ;
  - `first_failed_check` et `saw_rate_limit` sont prêts à être émis.
- **#206** : le filtre des liens, images et balises dans le texte des affirmations (contrôle 6), et
  Prompt Shields sur un lot entier (limite écrite).
- **#207** : la recherche des faits, dont « chaque item cité porte un fait ».
- **#223** : le juge, avec `claim_id`, son rappel au classement et à la rédaction, et son propre
  contrôle de l'échéance avant l'appel (commentaire daté sur #223).
- **#210** : la première fiche réelle.
- **Piste signalée, non retenue** : qu'une nouvelle tentative sautée par l'échéance garde l'état de
  la première tentative (`llm_rate_limited`) plutôt que `llm_timeout`. Les étiquettes seraient
  cohérentes, mais cela rouvrirait la décision Q2 de Sabine.

## Sources

- [How to use structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs),
  Microsoft, consultée le 2026-10-17 (relevée par time-knight) : `minItems`, `maxItems`,
  `minLength` et `maxLength` ne sont pas pris en charge en mode strict.
- [Timeouts](https://github.com/pydantic/httpx2/blob/main/docs/advanced/timeouts.md), doc
  d'httpx2, lue par Context7 le 2026-10-17 : « The read timeout specifies the maximum duration to
  wait for a chunk of data to be received » ; le délai par requête (`timeout=`) et l'extension
  `timeout` de la requête, que les tests lisent.
- [Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview),
  section « HTTP », page du 2026-10-16, relevée par time-knight : « Request time out is 240
  seconds ».
- Durées et débit de gpt-6-luna : [note de #158](2026-10-17-brancher-gpt-6-luna-sur-foundry.md),
  mesures du 2026-10-17.
