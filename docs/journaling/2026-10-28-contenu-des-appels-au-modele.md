# Envoyer le contenu des appels au modèle avec les traces, sous réglage

- **Date** : 2026-10-28
- **Branche** : `feat/trace-model-content`
- **Issue** : #347
- **Fait suite à** : [`2026-10-27-tracer-les-etapes-des-fiches.md`](2026-10-27-tracer-les-etapes-des-fiches.md)
  (#345 : les spans et les raisons, sans texte)
- **Fichiers principaux** :
  - `src/k_b/ai_api/tracing.py` ;
  - `src/k_b/ai_api/connectors/llm_client.py` ;
  - `src/k_b/ai_api/connectors/metrics_export.py` ;
  - `src/k_b/ai_api/connectors/trace_export.py` ;
  - `src/k_b/ai_api/stages/classification.py` ;
  - `src/k_b/ai_api/digests.py` ;
  - `src/k_b/commands/serve_ai_command.py` ;
  - `src/k_b/core/config.py`.
- **Commits** : `3d433dc` (le code et ses tests), puis un commit des docs : `.claude/rules/poc.md`,
  le registre, `.env.example`, `docs/fiches-veille.md`, le journal ADR et cette note.

## Le pourquoi

Depuis #345, chaque `POST /digests` est une trace dans Grafana Cloud. Mais elle ne porte aucun texte :
on sait qu'une affirmation a été retirée parce qu'un fait est introuvable (`fact_not_found:0:17`),
pas si le refus était juste. L'essai réel du 27/10 en a retiré 37. Pour savoir si le modèle a inventé,
reformulé, ou si le contrôle est trop strict, il faut voir ce que le modèle a reçu et ce qu'il a
répondu. Tu l'as demandé le 26/10 : « surtout en phase de dev. Mais aussi en prod quand quelque chose
sort des clous ».

Ce contenu porte des données personnelles : un login reste dans le nom d'un dépôt, un nom peut rester
dans un texte libre. Il ne part donc que sous réglage (`KB_TRACE_CONTENT`), vers un sous-traitant dont
le DPA est signé. Il fait l'objet d'une exception écrite à la règle 5 de `poc.md` (« un journal ne
contient pas de texte »), dans les mots que tu as validés (D2).

## Le comment

### 1. Le réglage, lu avec l'export

`KB_TRACE_CONTENT` vaut `none` (le défaut), `anomalies` ou `all`. Il est lu par la fonction qui lit
déjà `KB_OTLP_ENDPOINT`, `KB_OTLP_HEADERS` et `KB_DEPLOYMENT_ENVIRONMENT`
(`src/k_b/ai_api/connectors/metrics_export.py:184-188`) :

```python
    trace_content = environ.get(TRACE_CONTENT_VARIABLE) or "none"
    if trace_content not in TRACE_CONTENTS:
        return find_unknown_content_refusal(trace_content)
    if trace_content == "all" and environment == "production":
        return f"{TRACE_CONTENT_VARIABLE}: all refused in production, anomalies or none"
```

- C'est là qu'on connaît l'environnement, dont dépend le refus en production.
- Posé sans l'export, le réglage est refusé aussi (`metrics_export.py:153`). Sinon, des textes seraient
  gardés en mémoire alors que rien ne part.
- Le réglage voyage ensuite sans aucune signature nouvelle : `MetricsExportSettings.trace_content` →
  `TraceExport.content` → `Tracing.content`.

### 2. Les textes gardés, seulement si le réglage le demande

Chaque requête au modèle (chaque tentative) garde ses textes dans un `AttemptContent`, mais seulement
si le réglage n'est pas `none` (`src/k_b/ai_api/connectors/llm_client.py:289-292`) :

```python
        if tracing.content != "none":
            contents.append(
                AttemptContent(step.ref, prompt, user_message, attempt.output_text)
            )
```

- `prompt` est la consigne réellement envoyée, rappel compris pour une relance.
- `output_text` est la sortie d'une réponse 200, même refusée par un contrôle : c'est elle qu'on veut
  lire. Elle vaut `None` hors 200, parce que le corps d'une erreur peut citer l'entrée.
- `step.ref` est la référence du span `chat` de cette tentative. C'est elle qui rattache plus tard
  l'enregistrement à son span.
- Ces textes vont dans `LlmCall.contents`, déclaré `field(default=(), repr=False)`
  (`llm_client.py:166`). Le `repr` d'un appel, qu'un test ou un journal pourrait afficher, ne montre
  donc jamais de texte. Avec `none`, `contents` reste vide : le contrat « never a text » de `LlmCall`
  tient.

### 3. Ce qu'est une anomalie (D1, et sa précision du 28/10)

Une seule fonction décide (`llm_client.py:328-338`) :

```python
    is_provider_timeout = (
        call.outcome == "llm_timeout" and call.first_outcome in PROVIDER_FAILURES
    )
    return call.first_failed_check is not None or (
        call.outcome in ANOMALY_OUTCOMES and not is_provider_timeout
    )
```

- `ANOMALY_OUTCOMES` vaut `llm_invalid_output`, `llm_truncated`, `llm_content_filtered` et
  `llm_timeout`. Ce sont les cas que le contenu peut expliquer.
- `first_failed_check` n'est posé que si l'appel a été relancé après le refus d'un contrôle. Ce cas
  l'emporte : un refus, une relance, puis un 5xx, c'est une anomalie.
- `first_outcome` est neuf : l'état de la première tentative (`llm_client.py:615`). Si elle a eu un
  429, un 5xx ou une erreur réseau, et que l'appel finit en `llm_timeout`, la cause est le
  fournisseur, puis le délai de la demande : ce n'est pas une anomalie. Peu importe que la relance
  n'ait pas eu le temps de partir, ou qu'elle soit partie avec un délai réduit puis ait expiré. Ce sont
  tes deux précisions du 28/10, la seconde sur les deux revues de la PR.
- Le troisième cas de D1, un lot de classement qui a laissé des items sans réponse, ne se voit pas
  dans l'appel : seule l'étape le sait. Elle le passe en paramètre (`classification.py:151`) :
  `has_unanswered=batch_answers is not None and None in batch_answers`. Le garde `is not None` évite
  `None in None`, qui lèverait une exception sur chaque classement en échec.

`trace_contents` (`llm_client.py:340-349`) applique le réglage : avec `all`, tout part ; avec
`anomalies`, seulement si `is_anomaly(call) or has_unanswered`. Elle est appelée juste après chaque
appel, avant les contrôles de l'étape (`classification.py:148-152`, `digests.py:111`) : une faute
dans ces contrôles (un 500) ne fait pas perdre le contenu de l'appel qui l'a provoquée (première
revue de code). Une affirmation retirée n'est pas une anomalie (D1) : la rédaction n'envoie que
selon l'état de son appel.

### 4. L'enregistrement et son corps

`Tracing.record_content` (`src/k_b/ai_api/tracing.py:189`) émet un enregistrement de journal OTLP
`gen_ai.client.inference.operation.details`, de niveau DEBUG. Comme une évaluation de #345, il porte
le contexte du span `chat` et l'instant où ce span a fini : Grafana le montre sous « Logs for this
span ».

Le corps est une chaîne JSON qui suit la forme des messages de la convention GenAI
(`tracing.py:261-282`) :

```python
            "system_instructions": [part(content.system_prompt)],
            "input_messages": [{"role": "user", "parts": [part(content.user_message)]}],
            "output_messages": output_messages,
```

Les attributs restent courts : `gen_ai.operation.name = chat`, et `k_b.content_truncated` si le corps
a été coupé. Le texte va dans le corps, jamais en attribut. Grafana Cloud Traces coupe un attribut à
2 Ko, et Loki range les attributs dans des métadonnées plafonnées à 64 Ko.

### 5. La coupe à 200 000 octets

Loki refuse une ligne de plus de 256 Ko. `build_content_body` (`tracing.py:234-258`) garde le corps
entier s'il tient dans `MAX_CONTENT_EVENT_BYTES` (200 000). Sinon, elle cherche par bissection la plus
grande longueur L telle que, chaque texte étant coupé à L caractères, le corps tienne.

- Tous les textes sont coupés à la même longueur, et toutes les clés et parties restent.
- La recherche termine : la taille croît avec L, et L = 0 tient toujours, la structure seule faisant
  environ 250 octets.
- La coupe se fait sur des caractères Python, jamais au milieu d'un caractère.
- On mesure les octets du JSON final : une guillemet ou un saut de ligne du message utilisateur
  (lui-même du JSON) doublent une fois échappés, et le test le vérifie.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Le contenu dans le corps d'un enregistrement de journal | 256 Ko par ligne dans Loki ; relié au span | En attributs de span : coupé à 2 Ko par Grafana. Un stockage externe avec une référence : recommandé par la convention en production, mais un second service à tenir pour une utilisatrice. Langfuse : un sous-traitant de plus. |
| Un corps en chaîne JSON | K-B mesure les octets de la ligne que Loki reçoit | Un dictionnaire : le récepteur le convertit avec son propre échappement, et la taille n'est plus garantie. |
| `KB_TRACE_CONTENT`, une variable `KB_*` (C6) | K-B refuse toute variable `OTEL_*` (consigne du dépôt, #162) | `OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT`. |
| Lu dans `metrics_export.py` | L'environnement y est lu ; aucune signature ne change | Une lecture à part dans `trace_export.py`, comme l'issue le listait : une branche de refus et un paramètre de plus. |
| Refusé sans l'export | Pas de textes gardés pour rien | Accepter et journaliser « off ». |
| D1 dans `llm_client.py` | Les couches interdisent à `tracing.py` d'importer `LlmCall` (`tests/architecture/test_apis.py`) | Dans `tracing.py`, comme l'issue le listait. |
| Les textes gardés par `call_model`, la sortie lue dans `Attempt.output_text` | Un seul endroit décide ; `Attempt` ne sort jamais de `call_model` | Descendre un drapeau dans trois fonctions de lecture de la réponse. |
| La coupe : la même longueur pour tous les textes | Simple, garantie, la structure reste | Ne couper que le message utilisateur : le plus long en pratique, sans garantie. |
| `trace_contents(llm_call, tracing=tracing, …)` | Le test d'architecture exige `tracing=` en mot-clé | `trace_contents(tracing, llm_call)` : refusé par le test. |
| La lecture des réglages découpée en deux fonctions | Ruff refuse une complexité au-delà de 10 (le dépôt n'a aucun `noqa: C901`) | Un `noqa`. |

La règle 8 de `poc.md` (« une sortie hors schéma n'est jamais écrite ») ne change pas. Elle vise le
coffre et la réponse de l'API, à cause de l'injection. Ici, la sortie refusée part comme une chaîne
échappée dans un corps de journal, jamais interprétée.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 2 732 tests verts (58 de plus) ; `mypy --strict src`, `ruff check`, `ruff format --check` propres | Rien de cassé, dont le test d'architecture de `tracing=` |
| `test_with_content_none_the_call_keeps_no_text_and_sends_none` (`tests/ai_api/test_llm_client.py`) | Avec `none`, aucun texte gardé, rien envoyé |
| `test_with_content_all_each_request_is_a_content_tied_to_its_chat_span` | Un enregistrement par tentative, rattaché au `span_id` de son `chat` ; le rappel de la relance ; la sortie refusée présente ; aucun texte dans le `repr` |
| `test_a_request_without_output_text_keeps_no_output` (429, 5xx, 400 filtré, délai, 200 illisible) | Pas de sortie sans réponse 200 lisible |
| `test_with_content_anomalies_only_a_call_in_anomaly_is_sent` (18 cas) | D1 : les quatre états, la relance après un refus (même finie en 429 ou 5xx) envoient ; `ok`, 429 et 5xx seuls ou relancés avec succès n'envoient pas |
| `test_a_retry_cut_by_the_deadline_is_an_anomaly_only_after_a_refusal`, et les cas `*-then-timeout` du test précédent | Les précisions du 28/10 : après un 429, un 5xx ou une erreur réseau, un délai dépassé n'envoie pas, que la relance soit partie ou non ; après un refus de contrôle, si |
| `test_with_content_anomalies_*` (`tests/ai_api/test_digests.py`) | Un lot avec un item sans réponse envoie ; un classement en échec envoie, sans 500 ; une affirmation retirée et un sujet en 503 n'envoient rien |
| `test_a_content_beyond_the_maximum_is_cut_keeping_its_structure` (`tests/ai_api/test_tracing.py`) | Au plus 200 000 octets, avec des caractères sur plusieurs octets et à échapper ; mêmes clés ; un caractère de plus dépasserait ; drapeau posé |
| `test_with_content_all_only_the_body_of_a_content_record_holds_a_text` (`tests/ai_api/test_digest_router.py`) | Règle 5 : avec `all`, le texte d'un item n'apparaît que dans le corps des enregistrements de contenu, ni dans un attribut, ni dans une évaluation, ni dans une ligne de journal ou de métrique |
| `tests/ai_api/test_metrics_export.py`, `test_serve_ai.py`, `test_trace_export.py` | Le défaut, le vide, une valeur inconnue, `all` en production (sans valeur citée), le réglage sans export, `OTEL_*` d'abord ; la ligne de démarrage et `app.state.tracing.content` |

## Ce que tu dois pouvoir défendre

1. **« Vous envoyez des données personnelles à un tiers ? »** Oui, sous réglage, et seulement ce qui
   part déjà au modèle, masqué de la même façon. Le DPA est signé avant le premier envoi. `all` est
   refusé en production, où seuls les appels en anomalie partent. Tout est inscrit au registre, avec
   ses limites : une purge par la rétention de Grafana (14 jours), et pas de droits séparés
   (`metrics_export.py:188`, `docs/registre-traitements.md`).
2. **« Pourquoi pas tout envoyer en production, c'est plus simple ? »** C'est la minimisation (RGPD
   art. 5.1.c) : n'envoyer que ce qui explique un problème. Une affirmation retirée ne compte pas,
   parce que les 8 sujets en avaient à l'essai, et son pourquoi se rejoue en bac à sable. Un 429 non
   plus : c'est le fournisseur, la métrique suffit (`llm_client.py:330-337`).
3. **« Que se passe-t-il si une consigne et 60 items dépassent la taille d'une ligne de Loki ? »**
   Chaque texte est coupé à la même longueur, la plus grande qui tient sous 200 000 octets ; la
   structure reste, et `k_b.content_truncated` le dit (`tracing.py:234-258`).
4. **« Comment être sûr qu'aucun texte ne fuit ailleurs ? »** Un test exécute une demande complète
   avec `all`, puis cherche les mots des items partout : spans, évaluations, journaux, sortie
   standard. Il ne les trouve que dans le corps du contenu. Le `repr` d'un appel n'affiche pas
   `contents`.
5. **« Un `llm_timeout` est-il toujours une anomalie ? »** Non : si la première tentative a eu un
   429, un 5xx ou une erreur réseau, la cause est le fournisseur, puis le délai. `first_outcome`
   garde l'état de cette première tentative (`llm_client.py:328-338`). Un délai dépassé dès la
   première tentative (le modèle trop lent) en reste une.

## Essai réel (2026-10-28, `gpt-6-luna`, bac à sable, fenêtre de 3 jours)

| Vérification | Résultat |
|---|---|
| `KB_TRACE_CONTENT=all`, ligne de démarrage | `model content all` |
| Demande `506e690d-9b4f-4ce5-9d9a-8b2384711aad` | 200 en 56,8 s, 8 fiches, 22 spans, aucune relance, donc 10 requêtes au modèle |
| Dans Loki, « Logs for this trace » | 10 enregistrements DEBUG (le contenu) et 37 INFO (les évaluations) : aucun perdu |
| Un corps lu dans Loki | JSON complet, trois clés, la sortie du modèle comprise (8 Ko pour une rédaction, 25 Ko pour un lot de classement) ; l'attribut s'appelle `event_name` ; lisible avec les icônes `{}` et ↵ |
| Erreurs d'envoi dans le terminal | aucune (`WARNING`, `ERROR`, `Failed to export`) |
| `none`, demande `cabf2a92-dc9f-43d6-b0d2-534401519c1a` (`POST /digests` direct, sans écrire de fiche) | 200 en 56,6 s ; dans Loki, 41 INFO, aucun DEBUG |

Ce que l'essai montre déjà : un fait déclaré en anglais (« 8.2 million ») dans une affirmation
écrite en français (« 8,2 millions »), le genre de cas que #210 doit trancher.

## Zones non vérifiées

- **Une demande plus chargée** : à cette charge (une demande, 10 corps de 8 à 25 Ko), aucun lot
  n'approche les limites. Un corps proche de 200 000 octets, et la limite d'une requête chez
  Grafana, n'ont pas été essayés en réel.
- **La procédure de suppression de journaux dans Grafana Cloud** (droit à l'effacement) : citée au
  registre, pas lue.
- **La rétention pendant l'essai de 14 jours** de la pile : non relevée. 14 jours dans l'offre
  gratuite (page « Pricing », lue le 2026-10-28).
- **L'accusé de réception du DPA** : signé et envoyé le 2026-10-28 ; l'accusé n'est pas arrivé au
  moment de l'essai.

## Ce qui reste

- **L'accusé de réception du DPA**, à inscrire au registre s'il arrive.
- **`KB_DEPLOYMENT_ENVIRONMENT=production`** à figer dans la configuration du conteneur à la mise en
  ligne sur ACA (08/11) : le refus de `all` en production ne repose que sur elle.
- **Une file propre aux journaux**, si un envoi est refusé pour sa taille.
- **La variante écartée de D1** (le texte des seules affirmations retirées en production) : à
  rejuger après #210.
- **#281** : le `traceparent` vers l'API de données et le `trace_id` dans les lignes de journal.
