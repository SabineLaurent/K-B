# Brancher gpt-6-luna sur Foundry en zone de données UE

- Date : 2026-10-17
- Branche : `docs/gpt-6-luna-foundry`
- Issue : #158
- Fichiers : `src/k_b/ai_api/llm_client.py` (cache de prompt coupé), `src/k_b/core/config.py`
  (délai de lecture à 90 s), `tests/ai_api/test_llm_client.py`, `docs/registre-traitements.md`,
  `docs/ADR/journal-decisions-projet.md` (trois entrées du 17/10), `docs/fiches-veille.md`, et
  cette note.
- Note précédente de la série : [Brancher Gemini 2.5 Flash-Lite en repli temporaire](2026-10-16-brancher-gemini-en-repli.md).

## Le pourquoi

Les fiches de veille passent par un vrai modèle. La cible décidée le 16/10 est `gpt-6-luna` sur
Azure AI Foundry, en zone de données UE. Jusqu'ici, le compte prévu était à 0 jeton par minute, et
K-B passait par des replis (Mistral, puis Gemini, #227). Le 17/10, Sabine a obtenu une ressource
sur l'abonnement Azure de son organisme de formation, fournie pour son projet de certification.

Cette PR fait trois choses :

1. elle **fonde l'envoi des données** sur ce nouvel abonnement, au registre des traitements et au
   journal ADR, avant le premier appel ;
2. elle **mesure le vrai modèle** : en-tête, réglages, filtres, quota, durées. Les durées servent à
   #205 pour choisir entre la rédaction en parallèle et une tâche de fond ;
3. elle **corrige le client** sur deux points que l'essai a rendus nécessaires : le cache de
   prompt, coupé, et le délai de lecture, porté à 90 s.

## Le comment

### 1. Le contrat : qui est le client de Microsoft

Avant tout appel, le registre exigeait de relire la chaîne contractuelle pour tout nouvel
abonnement. Les constats de Sabine dans le portail :
- l'offre est un « Plan Azure », vendu sous le Microsoft Customer Agreement ;
- l'annuaire et le compte de connexion sont ceux de l'organisme ;
- son rôle est « Lecteur » ;
- aucun compte de facturation ne lui est visible.

Le DPA de Microsoft (édition du 22/05/2026) fixe les rôles entre Microsoft et **son** client :

> « Customer is the controller of Personal Data and Microsoft is the processor of such data,
> except (a) when Customer acts as a processor of Personal Data, in which case Microsoft is a
> subprocessor »

Le client est donc l'organisme. Microsoft est son sous-traitant, pas celui de Sabine. Trois
lectures ont été soumises à Sabine, et elle a retenu la première : le traitement fait partie de sa
formation, et son contrat de formation fonde l'usage de la ressource
(`docs/registre-traitements.md`, « Fondement de la sous-traitance »). Le registre ajoute aussi les
**destinataires possibles chez l'organisme** :
- un administrateur général de l'annuaire peut se donner l'accès à la ressource ;
- si l'organisme active les preuves des prompts de Defender for Cloud, des extraits des prompts
  apparaissent dans ses alertes.

L'organisme n'est nommé dans aucun fichier : le dépôt devient public le 25/10.

### 2. Le cache de prompt, coupé à chaque requête

À partir de GPT-5.6, Azure écrit par défaut un cache sur le dernier message de chaque requête,
donc sur le texte des items. Ce cache reste réutilisable « at least 30 minutes, but the service
might retain it longer ». Le client le coupe :

```python
PROMPT_CACHE_OFF: Mapping[str, str] = {"mode": "explicit"}
```
(`src/k_b/ai_api/llm_client.py:40`)

```python
        "prompt_cache_options": PROMPT_CACHE_OFF,
```
(`src/k_b/ai_api/llm_client.py:254`, dans `build_request_body`)

En mode `explicit`, seuls les points d'arrêt marqués par l'appelant sont mis en cache. K-B n'en
marque aucun, donc rien n'est écrit. Le champ est envoyé à **chaque** requête, quel que soit le
réglage d'effort : le test du corps exact
(`test_the_request_is_a_chat_completion_with_a_strict_json_schema_written_as_a_dict`) le vérifie
sans effort, et `test_a_reasoning_model_gets_reasoning_effort_none_and_no_temperature`
(`tests/ai_api/test_llm_client.py:200`) avec `reasoning_effort: "none"`.

### 3. Le délai de lecture, confronté au débit mesuré

L'appel n'est pas en diffusion : la réponse arrive d'un bloc, et le délai de lecture borne
l'attente de la réponse **entière**. Mesuré sur 12 appels à une tentative : environ 7,35 ms par
jeton de sortie. Une sortie de 8 192 jetons demande donc environ 60 s, la valeur du délai
d'avant :

```python
LLM_CALL_TIMEOUT_SECONDS = 90
```
(`src/k_b/core/config.py:62`)

La borne d'un appel passe de 2 × (5 + 60) + 20 = 150 s à 2 × (5 + 90) + 20 = 210 s
(`src/k_b/core/config.py:64`). Le test garde la **raison** du changement, pas seulement la
valeur :

```python
    seconds_at_cap = MEASURED_MS_PER_OUTPUT_TOKEN * LONGEST_MEASURED_OUTPUT_CAP / 1000

    assert seconds_at_cap * 1.4 <= LLM_CALL_TIMEOUT_SECONDS
```
(`tests/ai_api/test_llm_client.py:563-565`)

Il échouait à 60 s (60,2 × 1,4 ≈ 84 s) et passe à 90 s.

### 4. `reasoning_effort` plutôt que `temperature`

Le client envoie l'un ou l'autre, jamais les deux :

```python
    if settings.reasoning_effort is None:
        body["temperature"] = 0
    else:
        body["reasoning_effort"] = settings.reasoning_effort
```
(`src/k_b/ai_api/llm_client.py:257-260`)

L'essai tranche la contradiction de la doc de Microsoft :
- `temperature: 0` seul rend un 400 `unsupported_value` (`param: temperature`) ;
- avec `reasoning_effort: "none"`, il est accepté, mais rien ne prouve qu'il change la sortie.

Le réglage reste donc `KB_LLM_REASONING_EFFORT=none`, et `reasoning_tokens` vaut 0 sur tous les
appels.

### 5. Comment la mesure a été faite, sans rien afficher

Les scripts de mesure vivent hors du dépôt, dans le dossier temporaire de la session. Ils
appellent le code de production : `build_request_body`, `call_model`, `send_and_check`. Le
déroulé :
- une **veille réelle** est collectée le 17/10 dans une base de test (jamais `~/K-B-data/`), avec
  la fenêtre depuis le 10/10 : 274 items, sous le plafond de 300 ;
- la chaîne de #205 est rejouée en entier : 6 classements de 44 à 46 items, puis 3 rédactions du
  sujet le plus fourni et 2 du suivant, puis 3 jugements sur une rédaction réelle.

Un crochet `httpx2` sur chaque réponse affiche le statut, le `model` rendu, les en-têtes
`x-ratelimit-*`, l'`usage` brut et les **booléens** des filtres. Il n'affiche jamais un texte
d'item ni une sortie du modèle (règle 5 de `poc.md`). Le `.env` n'est pas lu : `uv run --env-file`
le passe au processus, et les réglages ont été relus tels que le client les voit, sans afficher
la clé ni le nom de la ressource.

## Choix faits et options écartées

- **Abonnement de l'organisme, lecture (a)** (décision de Sabine). Écartées : (b) écrire une
  limite assumée, la chaîne n'étant pas contractualisée ; (c) ne pas envoyer de données réelles.
- **Zone de données standard, France Central, version 2026-09-22 figée** (déploiement de Sabine,
  guidée par time-knight). Écartés : un premier déploiement en Global Standard (traitement possible
  dans toute région Azure, contraire à `.claude/rules/conformite.md`) ; la mise à niveau
  automatique (le modèle changerait sans prévenir).
- **Juge = `gpt-6-luna` en phases 1 et 2** (décision de Sabine, repli du 16/10). Écarté :
  déployer `gpt-5.6-luna`, de la même famille que le rédacteur. Le juge définitif se choisit en
  phase 3 ; #158 vérifie seulement que les candidats (DeepSeek-V4-Flash, Mistral-Large-3) tiennent
  le mode strict, sur des données fabriquées.
- **Cache coupé, à chaque requête, sans réglage** (tranché par time-knight, délégation de Sabine
  du 15/10). Écartés : garder le cache et le décrire au registre (une rétention de plus, pour un
  gain presque nul, puisque chaque message de K-B est différent) ; une variable d'environnement
  (sans second usage aujourd'hui, YAGNI). Limite : un modèle d'avant GPT-5.6 refuse le champ.
- **Délai de lecture à 90 s** (tranché par time-knight). Écarté : garder 60 s et plafonner la
  rédaction vers 6 000 jetons, car la marge reposerait sur une estimation non mesurée.
- **`reasoning_effort: "none"` seul.** Écarté : envoyer aussi `temperature: 0`, accepté mais
  d'effet non prouvé.
- **Pas d'essai provoqué du filtre de contenu** (tranché par time-knight). Un faux message de
  contournement des consignes enverrait un signal à la surveillance des abus de Microsoft, sur le
  compte de l'organisme. Le critère est accordé : « confirmé s'il est observé, sinon non
  observé ».
- **Consignes minimales des scripts** : constantes, selon la spec, sans optimisation ; les vraies
  consignes sont à #205.

## Preuve

Toutes les requêtes du 17/10 (UTC), sur `gpt-6-luna` :

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 1 528 tests verts ; ruff, format, mypy strict verts | le client et la config changés tiennent tous les contrôles |
| les assertions de `prompt_cache_options` et `test_the_read_timeout_covers_…` : rouges avant le code, verts après | les deux changements sont écrits tests d'abord |
| `GET /openai/v1/models` (13:23:31Z) : `gpt-6-luna-2026-09-22`, `generally-available`, `deprecation.inference` = 2028-03-11 | date de retrait lue ; c'est la date du modèle de base sur ce point d'accès, pas par SKU de zone de données |
| ping avec `Authorization: Bearer` : 200 ; `model` rendu `gpt-6-luna-2026-09-22` | en-tête confirmé, sans repli `api-key` ; version figée ; hôte `*.openai.azure.com/openai/v1` sans `api-version` |
| ping `reasoning_effort: "none"` : `reasoning_tokens` 0 ; `temperature: 0` seul : 400 `unsupported_value` ; les deux : 200 | contradiction de la doc tranchée |
| 20 réponses : `cached_tokens` 0, `cache_write_tokens` 0 | le cache est bien coupé |
| 20 réponses : aucun booléen de filtre à vrai (entrée et sortie, jailbreak et matériel protégé compris) | 400 et `finish_reason` `content_filter` : non observés |
| en-têtes `x-ratelimit-limit-tokens` 140 000, `-requests` 140, fenêtre de 60 s | quota consigné ; constat : `remaining-tokens` baisse des seuls jetons d'entrée (140 000 − 6 228 = 133 772), pas du plafond de sortie, à l'inverse de la doc « Manage quota » ; constat sur l'en-tête, sans règle tirée |
| 6 classements (13:24:06Z → 13:24:35Z), 46 items, ~5 500 jetons en entrée : 3 744 (1er), 3 441, 3 193, 3 196, 3 239 ms ; 1 appel à 2 tentatives (6 659 ms) | médiane 3 239 ms, max 3 744 ; `enum` strict des `"i<id>"` et des sujets tenu ; 271 items attribués, 2 non retenus, 0 absent |
| rédactions (13:24:47Z → 13:25:38Z), 42 à 50 items, ~6 000 jetons en entrée, 1 042 à 1 292 en sortie : 9 278 (1er), 7 747, 7 654, 8 881 ms ; 1 appel à 2 tentatives (18 936 ms) | médiane 8 314 ms, max 9 278 ; 9 à 11 affirmations |
| 3 jugements (13:25:41Z → 13:25:49Z), 10 affirmations, 2 012 jetons en entrée, 184 en sortie : 1 514, 1 996, 1 403 ms | médiane 1 514 ms ; le juge coûte environ un tiers de l'entrée d'une rédaction |
| ajustement linéaire sur 12 appels à une tentative : `llm_ms ≈ -306 + 7,35 × tokens_out` | 8 192 jetons ≈ 59,9 s : le délai de 60 s ne suffisait pas |

**Pour #205.** La chaîne mesurée, sans nouvelle tentative, prend environ 98 s en série pour
8 sujets (6 × 3,3 + 8 × 8,3 + 8 × 1,5). C'est sous les **240 s** que l'ingress HTTP d'Azure
Container Apps laisse à une requête (« Request time out is 240 seconds », page
[Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview),
section « HTTP », du 2026-10-16, relevée par time-knight). La borne de pire cas, 22 appels de
210 s, dépasse ces 240 s avec 60 comme avec 90 s : le choix « parallèle ou tâche de fond » ne
dépend pas du délai de lecture.

## Ce que tu dois pouvoir défendre

1. **Pourquoi Microsoft est-il le sous-traitant de l'organisme, et pas le tien ?** Le DPA définit
   les rôles entre Microsoft et le titulaire de l'abonnement. L'abonnement, l'annuaire et le compte
   de connexion sont ceux de l'organisme. Tu as retenu que la ressource t'est fournie au titre de
   ton contrat de formation (`docs/registre-traitements.md`, « Fondement de la sous-traitance »).
2. **Pourquoi couper le cache, puisque Microsoft ne le partage pas entre abonnements ?** Parce
   qu'il garde le texte des items au moins 30 min, pour un gain presque nul : chaque message de
   K-B est différent. C'est de la minimisation (RGPD, RGESN 1.6). Preuve : `cache_write_tokens`
   à 0 sur 20 réponses, vérifié une fois à l'essai (`cached_tokens`, à 0 aussi, compte les
   lectures du cache, pas les écritures) (`llm_client.py:254`).
3. **Pourquoi 90 s et pas 60 ?** Au débit mesuré, une sortie de 8 192 jetons prend environ 60 s.
   À 60 s, elle finirait en `llm_timeout`, que le client ne retente pas (`llm_client.py:273-274`) :
   la fiche serait perdue. Le test le garde avec 40 % de marge (`test_llm_client.py`,
   `test_the_read_timeout_covers_…`).
4. **Que se passe-t-il si un item parle d'injection d'instructions ?** Prompt Shields lit le
   message utilisateur, là où sont les items. Il peut rendre un 400 `content_filter` pour tout le
   lot, que le client lit `llm_content_filtered`, sans nouvelle tentative
   (`llm_client.py:309-312`). Ce n'est pas observé sur la veille du 17/10 : c'est signalé à #205
   et #206.
5. **Ces mesures valent-elles pour la production ?** Pour l'ordre de grandeur, oui : même
   déploiement, même client, cache coupé comme en production, veille réelle. Mais les consignes
   des scripts sont minimales, les rédactions de 42 et 50 items restent sous le plafond de 60, et
   le maximum de 4 ou 5 valeurs n'est pas une queue de distribution.

## Zones non vérifiées

- **Le contrôle qui a refusé la première tentative** des deux appels retentés : `LlmCall` ne garde
  que celui de la dernière tentative (signalé à #205).
- **L'effet de `temperature: 0`** quand il est envoyé avec `reasoning_effort: "none"` : accepté,
  effet non mesuré.
- **La date de retrait par SKU de zone de données** : seule la date du modèle de base a été lue.
- **Le calcul interne du quota** : seul l'en-tête `remaining-tokens` a été observé.
- **Un 429 réel** : non obtenu ; on ne sait pas s'il porte `Retry-After`, `retry-after-ms` ou les
  deux.
- **L'action par défaut de Prompt Shields** (bloquer ou annoter) : aucun filtre déclenché.
- **Le prix en zone de données** : la page officielle des prix d'Azure OpenAI montre des cases
  vides pour ces modèles ; des relevés tiers donnent 0,11 à 0,12 $ en entrée et 0,55 à 0,60 $ en
  sortie par million de jetons (non officiel).
- **Ce que l'organisme active dans son annuaire** (Defender, journaux de diagnostic) : inconnu.
- **La plus longue sortie permise par les bornes de la spec** (~6 000 à 7 000 jetons) : estimée,
  pas mesurée.

## Ce qui reste

- **Candidats juges** (DeepSeek-V4-Flash, Mistral-Large-3) : mode strict à vérifier sur des
  données fabriquées dès que Sabine les a déployés ; leur choix est en phase 3.
- **#205** : plafonds de sortie, concurrence sous le quota (une rédaction ≈ 14 000 jetons estimés,
  entrée et plafond), choix « parallèle ou tâche de fond », motif de la première tentative dans la
  métrique, lot refusé par Prompt Shields.
- **#223** : un réglage du cache si le juge définitif est un modèle qui refuse `prompt_cache_options`.
- **Fichier de Sabine** : `.env.example:47-48` cite encore `gpt-5.6-luna` comme modèle à
  raisonnement ; non touché.
- Les replis de #227 (Mistral, puis Gemini) prennent fin à la fusion de cette PR.
