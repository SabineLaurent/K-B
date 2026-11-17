# Appeler les modèles du banc de C7

- **Date** : 2026-11-17
- **Branche** : `feat/llm-settings-bench-models`
- **Issue** : #627
- **Fichiers principaux** : `src/k_b/core/config.py`, `src/k_b/ai_api/connectors/llm_settings.py`,
  `src/k_b/ai_api/connectors/llm_client.py`, `tests/ai_api/test_llm_settings.py`, `tests/ai_api/test_llm_client.py`
- **Série** : suit [Appeler le modèle et son remplacement](2026-10-15-appeler-le-modele-et-son-remplacement.md).

## Le pourquoi

Le banc de C7 (16/11) a fait passer les fiches de veille par plusieurs modèles, chez plusieurs fournisseurs, pour
choisir celui de C8. Il préconise gpt-6.1-sol. Or ce modèle refuse les efforts de raisonnement `none` et `minimal` :
il lui faut `low`. Sur `main`, `KB_LLM_REASONING_EFFORT` n'acceptait que `none` : l'API IA aurait refusé de démarrer
avec le réglage que C8 va décrire.

Le banc a buté sur deux autres obstacles, que la même PR lève :

- le champ `prompt_cache_options`, que K-B envoie à chaque requête pour qu'aucun cache de prompt ne soit écrit, est
  refusé par un 400 par un modèle d'avant GPT-5.6 et par un fournisseur qui ne le connaît pas ;
- Google Cloud nomme ses modèles derrière leur éditeur, `google/<modèle>`, et le motif d'un nom de modèle refusait
  la barre oblique.

Le code a été écrit et testé sur la branche du banc ; cette PR le propose à `main`, avec sa doc. Sans aucune des
nouvelles variables, l'API IA se comporte exactement comme avant : la production (gpt-6-luna) ne change pas.

## Le comment

### 1. Une liste fermée d'efforts, écrite une fois

```python
type ReasoningEffort = Literal["none", "minimal", "low"]
REASONING_EFFORTS: tuple[ReasoningEffort, ...] = get_args(ReasoningEffort.__value__)
```
(`src/k_b/core/config.py:260`)

Le type `Literal` dit à mypy les trois seules valeurs possibles ; `get_args` en tire le tuple dont le code se sert
à l'exécution (contrôle et message d'erreur). La connaissance vit donc à un seul endroit : ajouter un effort, c'est
changer cette ligne. Le dépôt fait déjà ainsi pour `GITHUB_ECOSYSTEMS` et `TRACE_CONTENTS` (`config.py:42`, `:653`).

### 2. Lire l'effort sans perdre le type

```python
def is_reasoning_effort(value: str) -> TypeIs[ReasoningEffort]:
    return value in REASONING_EFFORTS
```
(`src/k_b/ai_api/connectors/llm_settings.py:109`)

La variable d'environnement est une `str`. Après `if effort is not None and not is_reasoning_effort(effort):`
(`llm_settings.py:71`), qui renvoie un refus, mypy sait que `effort` est un `ReasoningEffort` : `TypeIs` (Python
3.13) affine le type dans la branche où la fonction rend `True`. Sans lui, il faudrait un `cast`, que mypy ne
vérifie pas. Une valeur hors liste (`medium`) arrête le démarrage avec un message qui la cite, tronquée et échappée
par `quote_value`, et nomme les valeurs permises : `KB_LLM_REASONING_EFFORT: 'medium' not none nor minimal nor low`.

### 3. Un interrupteur pour `prompt_cache_options`

```python
SEND_PROMPT_CACHE_OPTIONS_VALUES = {"true": True, "false": False}
```
(`llm_settings.py:38`)

Seuls les textes `true` et `false` sont acceptés ; vide ou absent vaut `true` (`LLM_SEND_PROMPT_CACHE_OPTIONS`,
`config.py:266`), toute autre valeur (`no`, `0`, `False`) est refusée au démarrage. Échouer fermé : un `yes` mal tapé
ne doit pas laisser deviner l'intention. Puis, au moment de construire la requête :

```python
if settings.send_prompt_cache_options:
    body["prompt_cache_options"] = PROMPT_CACHE_OFF
```
(`src/k_b/ai_api/connectors/llm_client.py:416`)

Le champ n'est plus écrit en dur dans le dictionnaire : il n'y entre que si le réglage le demande.

### 4. Un champ ajouté en dernier, avec son défaut

```python
send_prompt_cache_options: bool = LLM_SEND_PROMPT_CACHE_OPTIONS
```
(`llm_settings.py:61`)

Dans une `dataclass`, un champ avec une valeur par défaut doit venir après ceux qui n'en ont pas. Le défaut est
celui qui coupe le cache : un `LlmSettings` construit sans ce champ (dans un test, par exemple) garde le comportement
sûr.

### 5. Un nom de modèle derrière son éditeur

```python
MODEL_NAME = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}(?:/[A-Za-z0-9][A-Za-z0-9._:-]{0,99})?"
)
```
(`config.py:275`)

Le motif d'avant, inchangé, suivi d'une partie optionnelle : une barre oblique et un second nom de même forme. Une
seule barre au plus, chaque côté commence par une lettre ou un chiffre et fait 100 caractères au plus. Le motif est
appliqué par `fullmatch` : il couvre toute la chaîne. Le nom part dans le corps JSON de la requête seulement : une
barre oblique ne peut donc pas modifier le chemin de l'URL appelée.

## Choix faits et options écartées

- **Une liste fermée de trois efforts**, plutôt que toute valeur passée telle quelle au fournisseur : la consigne du
  dépôt veut une entrée validée à la frontière par un type fermé (`code.md`, « Sécurité dès la conception »). Les
  efforts au-delà de `low` (`medium`, `high`) restent refusés : aucun modèle du banc n'en a besoin.
- **Un réglage `KB_LLM_SEND_PROMPT_CACHE_OPTIONS` à `true` par défaut.** Le défaut garde la décision du 2026-10-17
  (cache de prompt coupé, une correction de minimisation). Cette décision écartait une variable « sans second usage
  aujourd'hui » et annonçait un réglage avec le second modèle : le banc en est le second usage (journal ADR,
  2026-11-17). Option écartée de fait : ne plus jamais envoyer le champ, qui rouvrirait le cache pour gpt-6-luna.
- **`false` refusé en production** (`KB_DEPLOYMENT_ENVIRONMENT=production`), accepté en local et en bac à sable :
  tranché par time-knight après un relecteur neuf, sur le constat C2 de la revue de code. Pourquoi : le même refus
  que `KB_TRACE_CONTENT=all`, et aucun usage bloqué (gpt-6-luna et gpt-6.1-sol acceptent le champ). Option
  écartée : une garde par l'écrit seul (le registre), que proposait la session et que rien ne fait respecter. Le
  refus vit dans `read_llm_settings_or_refusal`, là où le réglage est lu, plutôt que dans le démarrage de
  `kb serve-ai` (qui ne porte aucune règle d'un réglage) ou dans l'export des mesures (qui ne lit
  `KB_DEPLOYMENT_ENVIRONMENT` que si l'export est actif) ; il compare la valeur telle quelle, comme `is_sandbox`
  (`core/api_settings.py`).
- **`true` et `false` seulement**, plutôt que les mille façons d'écrire un booléen : échouer fermé.
- **Une barre oblique au plus dans le nom du modèle** : la forme `éditeur/modèle` de Google Cloud, rien de plus.
  Les autres options n'ont pas été consignées par la session du banc.
- **Le retrait de `.env.bench.example`** : le fichier décrivait les variables du script du banc, qui vit hors de K-B
  (« K-B reads none of them ») ; la mission demandait de ne le garder que s'il sert à K-B. Il reste sur la branche
  `benchmark`. Les commits `02d2f3c3` et `8feea86a`, qui ne touchent que ce fichier, sont donc sans effet sur `main`.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_reasoning_effort_allowed_is_read` (`tests/ai_api/test_llm_settings.py:87`), paramétré `none`, `minimal`, `low` | les trois efforts sont lus |
| `test_a_setting_refused_gives_its_reason`, cas `medium` et `no` (`test_llm_settings.py:297`) | un effort ou un interrupteur hors liste arrête le démarrage, avec son message |
| `test_the_prompt_cache_options_are_sent_unless_set_to_false` (`test_llm_settings.py:106`) | absent, vide ou `true` : envoyé ; `false` : retiré |
| `test_the_replay_reads_whether_the_prompt_cache_options_are_sent` (`:157`) | le fournisseur simulé lit le réglage comme le vrai |
| `test_a_model_with_or_without_its_publisher_is_read` et `test_a_model_out_of_the_publisher_form_is_refused` (`:173`, `:205`) | la forme `éditeur/modèle` passe ; deux barres, une barre au bord, un côté trop long ou un espace sont refusés |
| `test_a_reasoning_model_gets_its_reasoning_effort_and_no_temperature` (`tests/ai_api/test_llm_client.py:236`) | la requête porte l'effort choisi, sans `temperature` |
| `test_a_model_that_refuses_the_prompt_cache_options_is_called_without_them` (`test_llm_client.py:247`) | à `false`, le champ est absent de la requête |
| `test_the_name_of_a_model_behind_its_publisher_goes_in_the_body_only` (`test_llm_client.py:257`) | le nom part dans le corps, l'URL reste la même, aucun en-tête ne le porte |
| `test_serve_ai_logs_its_reasoning_effort_and_whether_it_sends_the_prompt_cache_options` (`tests/ai_api/test_serve_ai.py`), écrit rouge avant le code (revue de code, C3) | le démarrage de `kb serve-ai` dit l'effort et si `prompt_cache_options` part : un mode où le fournisseur peut garder un cache se voit dans le journal |
| `test_the_prompt_cache_options_left_out_are_refused_in_production` et `test_the_prompt_cache_options_are_refused_left_out_in_production_only` (`tests/ai_api/test_llm_settings.py`), le premier écrit rouge avant le code (revue de code, C2) | `false` arrête le démarrage en production, avec un message qui nomme les deux variables ; il passe en bac à sable et en local, et `true` ou rien passe en production |
| `uv run pytest` : 5 612 réussis ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts (2026-11-17) | rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi ne pas laisser passer n'importe quel effort au fournisseur ? »** Une entrée externe se valide à la
   frontière par un type fermé ; une faute de frappe arrête le démarrage au lieu de donner un 400 à chaque appel,
   lu `llm_unavailable`. (`config.py:260`, `llm_settings.py:71`)
2. **« À `false`, que deviennent les données ? »** Le fournisseur peut garder les items dans son cache de prompt,
   selon ses règles. C'est pourquoi le réglage par défaut reste `true`, que `false` est refusé au démarrage en
   production (`llm_settings.py`, `read_llm_settings_or_refusal`), et qu'un modèle qui en aurait besoin en
   production a d'abord sa ligne au registre des traitements (`docs/registre-traitements.md`, « Usage par le
   fournisseur »), puis la levée de ce refus. Le démarrage le journalise dans tous les cas.
3. **« Une barre oblique dans un nom, n'est-ce pas un risque d'injection de chemin ? »** Le nom ne part que dans le
   corps JSON, jamais dans l'URL : un test le vérifie (`test_llm_client.py:257`). Le motif n'admet qu'une barre, au
   milieu, entre deux noms sans espace ni contrôle.
4. **« Le nom du modèle écrit dans une fiche est-il contrôlé ? »** Il ne vient jamais de la réponse du
   fournisseur : l'API IA renvoie celui de `KB_LLM_MODEL` (`ai_api/routers/digest_router.py:205`). `kb digest`
   relit la réponse de l'API IA comme une entrée non fiable, par le même `MODEL_NAME` (`post/ai_api_client.py:156`,
   `items.py:809`), avant d'écrire la fiche et son jumeau ; la fiche l'écrit comme une chaîne JSON, que YAML lit
   telle quelle (`post/digest_sheets.py:249`). Avec une seule barre oblique au milieu, il ne forme ni `..` entier
   ni `//`, et aucun chemin de fichier ne le contient (revue de sécurité de #627).
5. **« La production change-t-elle ? »** Non : sans les nouvelles variables, effort et cache restent ceux d'avant
   (`LLM_REASONING_EFFORT = None`, `LLM_SEND_PROMPT_CACHE_OPTIONS = True`).

## Zones non vérifiées

- Les refus des fournisseurs (gpt-6.1-sol qui refuse `none` et `minimal`, Google Cloud qui refuse
  `prompt_cache_options`, le nommage `google/<modèle>`) viennent du banc de C7 ; ils n'ont pas été reproduits dans K-B.
- À `minimal` ou `low`, le raisonnement compte dans `max_completion_tokens` (référence de l'API OpenAI). Le banc de
  C7 l'a mesuré hors de K-B (gpt-6.1-sol à `low` : aucun appel coupé sur 5 passages ; gemini-4-hydrogen : choix des
  dépôts coupé 2 fois sur 5 au plafond de 1 024) ; aucun test de K-B ne le couvre, l'essai de bout en bout de C8 le
  remesure.
- Le jeu de référence de `POST /digests` reste enregistré avec gpt-6-luna à `none` : il ne dit rien d'un autre
  modèle.

## Ce qui reste

- Le choix du modèle de production et sa ligne au registre : C8.
- Le script du banc et ses réglages restent hors de K-B (dépôt de time-knight, branche `benchmark`).
