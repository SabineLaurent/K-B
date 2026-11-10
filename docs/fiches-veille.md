# Spécification des comptes rendus de veille

Un compte rendu de veille regroupe, pour un sujet d'une liste fermée, ce que la veille de K-B a vu sur
une fenêtre de quelques jours. C'est la première sortie d'un modèle dans K-B : ce document est son
contrat, écrit avant le code. Il dit ce qui entre, ce qui sort, ce que le code refuse et ce qu'il
mesure. Les décisions et leur pourquoi sont dans le [journal ADR](ADR/journal-decisions-projet.md)
(2026-10-15, « POC du 25/10 », décisions 4, 5, 6 et 8 ; « Fiches de veille : le contrat » ;
2026-10-20, « Squelette E1 E3 : cadrage du 20/10 », décision 2) ; les
règles du POC, dans `.claude/rules/poc.md` ; l'API de données lue, dans [specs-api.md](specs-api.md).

**Partie commune avec le wiki.** La liste fermée de sujets, les schémas validés par le code, les
contrôles, les états nommés et la ligne de métrique sont posés ici ; la spécification du wiki
(#148, `docs/wiki.md`, pas encore écrite) les reprend au lieu de les redéfinir.

## Le parcours d'une demande

1. `POST /digests` sur l'API IA, servie par `kb serve-ai` sur `127.0.0.1:8001` par défaut, avec la
   clé d'un client (#156, section « Accès ») : la demande est validée (section « Fenêtre »), avant
   toute lecture et tout appel au modèle.
2. L'API IA lit la veille de la fenêtre par l'API de données, avec la clé du client `AI_DIGEST`
   (#204) : `GET /items` filtré par `kind=` et plafonné (section « Fenêtre »), puis
   `GET /items/{item_id}` pour chaque item gardé. Elle ne lit pas la base.
3. **Classement** (#205) : le modèle range chaque item dans un sujet, ou répond qu'aucun sujet ne
   convient (`no_suitable_subject`).
4. **Rédaction** (#205) : un appel par sujet ; le modèle écrit des affirmations qui citent leurs
   items.
5. **Contrôles** (#206, #207, section « Contrôles ») : le code revalide chaque sortie avant de
   s'en servir.
6. Réponse JSON ; une ligne de métrique par appel au modèle, sur la sortie standard (#156).
7. `kb digest` écrit une fiche par sujet dans le coffre (#209, section « Fiches dans le coffre »).

Ce qui compose l'API IA, ce qu'elle appelle et qui l'appelle : [architecture-api-ia.md](architecture-api-ia.md).

L'appel au modèle, sa nouvelle tentative et le modèle de remplacement des tests sont à #150 ; le
vrai modèle (gpt-6-luna sur Azure AI Foundry, décision de Sabine du 2026-10-16 ; déployé le
2026-10-17 sur l'abonnement de son organisme de formation ;
journal ADR, « Modèle des fiches : gpt-6-luna sur l'abonnement de l'organisme de formation ») à
#158. La spec ne dépend d'aucun fournisseur :
elle s'en tient à l'interface compatible OpenAI. L'API IA n'écrit rien qui doive survivre à son redémarrage
(règle 7 de `poc.md`) : les fiches sont rendues, pas gardées ; `kb digest` les écrit dans le coffre.

**Pas de tendances au 25/10** (décision de Sabine du 2026-10-15) : une tendance n'est pas un item
(table `trend`, servie par `GET /trends` avec un `repository_id`) et n'a pas d'`item_id` à citer ;
un second type de référence alourdirait le classement et la rédaction (#205).

## Sujets

La liste fermée des sujets est tenue par Sabine dans `core/config.py` (#205 l'y code). Le modèle
ne choisit que dans cette liste (`enum`) ; le code refuse le reste (journal ADR, « POC du 25/10 »,
décision 5). Un nom suit `[a-z][a-z0-9_]*`, 40 caractères au plus : une valeur d'`enum` et un nom
de dossier sûrs.

**Un sujet par item.** Les définitions disent aussi comment départager : un item qui relève de
plusieurs sujets va au **premier** de la liste, dans cet ordre.

| Ordre | Sujet | Définition |
|---|---|---|
| 1 | `vulnerabilities` | une faille identifiée (CVE, GHSA) : catalogue CISA KEV, alertes GitHub des paquets suivis, article qui la décrit |
| 2 | `llm_security` | attaques et défenses propres aux modèles et aux agents (injection d'instructions, jailbreak, empoisonnement, porte dérobée), sans CVE ni GHSA |
| 3 | `agent_frameworks` | versions et nouvelles de LangChain, LangGraph, LlamaIndex et des cadres d'agents |
| 4 | `coding_assistants` | assistants de code (Claude Code et autres) : versions, fonctions, usages |
| 5 | `models` | nouveaux modèles, évaluations, capacités et limites annoncées |
| 6 | `ai_industry` | entreprises, produits, financements et régulation de l'IA |
| 7 | `cybersecurity` | incidents, campagnes d'attaque, outils et pratiques de sécurité hors IA, sans CVE ni GHSA |
| 8 | `software_engineering` | outils, langages et pratiques de développement hors IA |
| 9 | `tech_industry` | entreprises, produits, plateformes et matériel de la tech, hors IA |

Liste de départ proposée par la session K-B à partir des sources collectées (dépôts suivis,
`GITHUB_TRACKED_REPOSITORIES` de `core/config.py` ; éditions TLDR `ai`, `infosec` et `dev`,
`etl/sources/tldr.py` ; arXiv sur la sécurité de l'IA, [specs-collecte.md](specs-collecte.md) ;
catalogue KEV ; alertes GitHub), validée par Sabine le 2026-10-15. Un item qui n'entre dans aucun
sujet reçoit `no_suitable_subject` : il n'y a pas de sujet « autre ». `tech_industry` est ajouté
le 2026-11-01 (Sabine), avec l'édition TLDR générale `tech` : en dernier, il ne prend que ce
qu'aucun sujet précis ne prend.

**Changer la liste.** On la modifie dans `core/config.py`, par une PR. Le `json_schema` envoyé au
modèle et le contrôle des sujets (contrôle 3) sont construits à partir de cette liste ; la
consigne du modèle ne change pas, puisque la liste voyage dans le message utilisateur. Les tests
utilisent leur propre liste de sujets, jamais les noms réels : un renommage ne casse aucun test.

**Limite.** Les fiches sont rangées par sujet (`veille/<sujet>/AAAA-MM-JJ.md`, à la racine du
coffre ; journal ADR, 2026-10-19, « Coffre : organisation ») ; `tops` est réservé aux fiches des
tops (`veille/tops/`), aucun sujet ne peut le prendre (`TOPS_DIR_NAME`, `core/config.py`) : renommer un
sujet ouvre un nouveau dossier, et les anciennes fiches restent dans l'ancien. Option écartée :
lire la liste dans un fichier du dossier de données ou dans une variable d'environnement ; ce
serait un réglage de plus à valider au démarrage, pour une liste qui change rarement. À reprendre
si Sabine la modifie souvent.

## Fenêtre

| Paramètre | Forme | Bornes | Défaut | Hors bornes |
|---|---|---|---|---|
| `window_days` (corps de `POST /digests`) | entier JSON | de 1 à 14 | `KB_DIGEST_WINDOW_DAYS`, absent ou `null` | 422 `invalid_parameter`, avant toute lecture et tout appel au modèle ; `true`, `3.0` et `"3"` sont refusés (pas des entiers) |
| `KB_DIGEST_WINDOW_DAYS` (variable d'environnement) | chiffres seuls | de 1 à 14 | 3, défaut nommé dans `core/config.py` (règle 2 de `poc.md`) | l'API IA ne démarre pas (code de sortie 2, échouer fermé, comme `kb serve-data`) |

- `since` = l'instant de la demande, en UTC à la seconde, moins `window_days` × 24 h ; il est
  passé à `GET /items?since=…`, et la règle de « quoi de neuf » de l'API de données s'applique :
  la date est celle de la source, pas celle de la collecte.
- `until` = l'instant de la demande, rendu dans `window.until`. **Limite** : `GET /items` n'a pas
  de borne haute ; un item daté après `until` (une date future dans la source, un décalage
  d'horloge entre `kb serve-data` et `kb serve-ai`) est lu et peut être cité.
- **Limite** : les articles TLDR et les entrées KEV sont datés à minuit UTC
  ([specs-api.md](specs-api.md), « Règle de quoi de neuf ») ; selon l'heure de la demande, une
  fenêtre de 3 jours prend 2 ou 3 éditions. Option écartée : arrondir `since` à minuit (une règle
  de plus, et la fenêtre ne dit plus « les N derniers jours »).

### Lecture plafonnée

La lecture et les appels au modèle sont bornés par demande (OWASP API4:2023, consommation de
ressources sans limite). Volume estimé : 140 à 205 items sur 3 jours, 640 à 740 sur 14 (TLDR
≈ 590, dont ≈ 140 pour l'édition `tech` ajoutée le 2026-11-01, comptée à 14 articles par édition
d'après celle du 2026-10-30 ; arXiv ≈ 45, releases 20 à 60, KEV et alertes quelques-uns).

- **Filtre** : `GET /items?since=…&kind=…`, avec les cinq sortes de la liste blanche (section
  « Schémas ») ; `kind` est répétable ([specs-api.md](specs-api.md), « Paramètres »). Sans ce
  filtre, un import Zotero en masse entrerait dans la lecture.
- **Plafond** : `MAX_ITEMS_PER_DIGEST_REQUEST = 300`, dans `core/config.py`, appliqué à la liste,
  avant les `GET /items/{item_id}`.
- **Ordre** : les sortes rares d'abord, `vulnerability`, `advisory`, `paper`, `release`, puis
  `newsletter_article` jusqu'au plafond ; dans chaque sorte, de la plus récente à la plus
  ancienne. Pourquoi : une coupe par date seule évincerait d'abord arXiv (daté par sa soumission,
  donc parmi les plus anciens) et les entrées KEV plus anciennes, la perte la plus grave pour une
  veille de sécurité.
- **Coupe dite** : `items_capped` est vrai s'il reste au moins un item non retiré au-delà du
  plafond ; la réponse donne alors `window.capped_kind`, la sorte coupée, et
  `window.covered_after`, la date du **premier item laissé de côté** de cette sorte, borne
  exclue : tout item de la sorte coupée strictement plus récent a été lu, et les sortes qui la
  suivent dans l'ordre ne sont pas lues du tout. Ainsi `window.since` ne promet pas ce qui n'a pas
  été lu. Les deux valeurs sont nulles quand `items_capped` est faux. Pourquoi une borne exclue
  (décision de Sabine du 2026-10-15, journal ADR, « Fiches de veille : la lecture par l'API de
  données ») : les articles TLDR d'une édition ont tous la même date, minuit UTC ; une coupe au
  milieu d'une édition aurait annoncé couvert un jour lu en partie. L'ordre de `GET /items`
  (`source_date`, puis `id`, décroissants) est total : la borne est vraie même quand la coupe
  tombe entre deux sortes. Une entrée retirée ne prend pas de place sous le plafond. Avec ce
  plafond, l'offset 10 000 de `GET /items` n'est jamais atteint.
- **Durée totale** : `DIGEST_REQUEST_TIMEOUT_SECONDS` = 200 s (#205, `core/config.py`), comptée
  dès l'arrivée de la demande ; elle borne la lecture et chaque appel au modèle. Les
  appels se font **en série**, un sujet après l'autre (décision de Sabine du 2026-10-17, plan de
  #205) : la chaîne mesurée par #158 dure environ 98 s (113 s avec les appels les plus lents),
  sous les 240 s que l'ingress HTTP d'Azure Container Apps laisse à une requête
  ([Ingress in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview),
  section « HTTP ») ; 200 s gardent 40 s pour le dernier appel en cours et la réponse. Cette
  mesure comptait un appel de plus par sujet, la vérification du sens, sortie du contrat le
  2026-10-20 (section « Ce que la spec ne couvre pas » ; `core/config.py`). Options
  écartées : rédiger les sujets en parallèle (environ 30 s, mais un `replay` à refaire et des 429
  possibles sous le quota, pour un gain sans besoin mesuré) ; une tâche de fond (un état gardé
  entre deux requêtes, contraire à la règle 7 de `poc.md`, utile seulement au-delà de 240 s).
  Le pire cas, 16 appels de 210 s, dépasse 240 s en série comme en parallèle : seule l'échéance
  borne la demande.
  - **Mécanisme** (`ai_api/deadline.py`) : aucune requête au modèle s'il reste moins de
    `MIN_SECONDS_FOR_LLM_REQUEST` = 10 s, au-dessus de la rédaction la plus lente mesurée par #158
    (9,3 s), pour que les items ne partent pas pour une réponse que l'échéance jetterait ; une
    rédaction plus longue (jusqu'à environ 60 s au plafond de sortie) lancée avec moins de temps
    peut encore finir en `llm_timeout` ; les délais d'httpx2 de chaque requête (modèle et API de données) sont ramenés au
    temps restant ; une nouvelle tentative qui ne tient plus n'est pas faite (`llm_timeout`, le
    statut HTTP observé gardé) ; la lecture de l'API de données s'arrête dès que l'échéance passe
    entre deux morceaux (`data_api_timeout`).
  - **Ce que voit le client** : au-delà, chaque sujet pas encore rédigé va dans
    `failed_subjects` avec `llm_timeout` et son étape (`write`), et les autres fiches
    sont rendues (200) ; un classement pas fini fait échouer la demande (`llm_timeout`, 504).
  - **Limite** : ce n'est pas une borne dure. Le délai de lecture d'httpx2 vaut pour chaque morceau
    reçu (« the maximum duration to wait for a chunk of data to be received »,
    [Timeouts](https://github.com/pydantic/httpx2/blob/main/docs/advanced/timeouts.md), doc
    d'httpx2, lue par Context7 le 2026-10-17 ; httpx2 2.13.1 n'a pas de délai total, vérifié
    dans son code) : chaque phase d'une requête (pool, connexion, écriture, lecture) est ramenée
    séparément au temps restant à son départ, si bien qu'une requête lancée avant l'échéance peut
    la dépasser de la somme de ses délais : 30 s au plus pour l'API de données (5 + 5 + 10 + 10) ;
    pour le modèle, 20 s plus sa lecture, et sans borne pour une réponse envoyée au compte-gouttes,
    dont httpx2 lit la réponse entière. Le fournisseur répond d'un bloc (appel sans diffusion), et
    la marge de 40 s sous les 240 s de l'ingress reste au-dessus de ces dépassements. Option
    écartée : lire la réponse du modèle en flux pour contrôler l'échéance entre deux morceaux ;
    elle resterait dépassable de la somme des délais.
- **Appels au modèle** : au plafond, 7 classements ou plus (des lots de 45 items et de 36 000
  caractères de message au plus, `MAX_ITEMS_PER_CLASSIFICATION_CALL` et
  `MAX_CLASSIFICATION_INPUT_CHARS` ; jusqu'à environ 10 quand les titres sont longs), 9
  rédactions (une par sujet) : environ 16 appels, et le double de tentatives au plus avec les
  nouvelles tentatives, soit environ 32. Ce nombre découle du plafond et des sujets : pas de
  constante de plus.

**Limites** : une seule demande à la fois est supposée (une seule utilisatrice, en local) ; le
quota du déploiement Foundry est de 140 000 jetons et 140 requêtes par minute (en-têtes
`x-ratelimit-limit-*`, mesure de #158 du 2026-10-17). Selon le calcul de la doc « Manage quota »
(entrée estimée plus `max_completion_tokens`), une demande approche 110 000 jetons estimés par
minute, même en série : une seconde demande dans la même minute peut rendre un 429 (non observé :
sur l'essai de #158, l'en-tête ne baissait que des jetons d'entrée). Les sortes rares tiennent bien sous
le plafond (≈ 150 items sur 14 jours) : si la coupe tombait sur l'une d'elles, `capped_kind` la
nommerait, et les sortes suivantes ne seraient pas lues. **Durée** : les délais du client
(`DATA_API_*_TIMEOUT_SECONDS`) bornent chaque attente, pas une requête ni la lecture : le délai de
lecture vaut pour chaque morceau reçu, si bien qu'un serveur qui envoie au compte-gouttes ferait
durer une requête sans fin ; et aux 300 détails s'ajoutent les pages de liste, jusqu'à 101 par
sorte (les entrées retirées ne comptent pas sous le plafond). C'est `DIGEST_REQUEST_TIMEOUT_SECONDS`
qui borne la lecture : `read_watch` exige l'échéance de la demande (paramètre sans valeur par
défaut, #205 ; constat de `/code-review` sur #204, tranché par time-knight, délégation de Sabine
du 2026-10-15), et s'arrête en `data_api_timeout` au-delà (« Durée totale », plus haut). **Taille** : chaque réponse de l'API de données est lue en
flux et refusée (`data_api_invalid_response`, sans rien citer du corps) au-delà de
`MAX_DATA_API_BODY_BYTES = 4 000 000` octets décodés, avant toute lecture quand `Content-Length`
l'annonce déjà ; au-dessus du pire honnête, estimé à environ 2 Mo pour une page de liste et
0,75 Mo pour un détail. Défense en profondeur (OWASP API4:2023, API10:2023), décision de Sabine
du 2026-10-15 : une borne dès maintenant, à corriger plus tard si besoin. **Offset** : `GET /items` rend `next_offset` nul
au-delà de l'offset 10 000 ; une entrée retirée ne prenant pas de place sous le plafond, une sorte
qui compterait plus de 10 000 entrées retirées dans la fenêtre serait coupée sans `capped_kind`.
Seules les vulnérabilités KEV sont retirables parmi les sortes lues : limite assumée (constat de
`/code-review` sur #204, écarté par time-knight, délégation de Sabine du 2026-10-15).

## Schémas

La spec écrit chaque schéma en JSON ; le code le porte en modèle Pydantic `extra="forbid"`, ce qui
écrit `additionalProperties: false` dans le JSON Schema qu'il produit. Le modèle Pydantic reste
**statique** (`str`) : les `enum` des sujets et des identifiants d'items sont ajoutés au
`json_schema` envoyé au modèle, et revérifiés par le code dans des contrôles à part (section
« Contrôles »).

**Identifiants d'items en chaînes.** Le modèle reçoit et rend chaque item sous un identifiant
`"i<item_id>"` (`"i17"` pour l'item 17) : un `enum` d'entiers n'est confirmé chez aucun
fournisseur. Le code fait la correspondance dans les deux sens ; la réponse de `POST /digests`
rend les `item_id` entiers de l'API de données.

**Schéma portable.** Le `json_schema` envoyé au modèle n'utilise que ce que les fournisseurs
acceptent en mode strict : `additionalProperties: false`, **tous** les champs dans `required`, et
ni `minLength`, ni `maxLength`, ni `minItems`, ni `maxItems` (Azure les refuse en mode strict).
Les bornes de ce document sont vérifiées par le code. Limites, les plus strictes connues : 100
propriétés d'objet par schéma (Azure, [structured
outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs), page du
2026-08-24, lue le 2026-10-26, qui ne donne pas de limite d'`enum`) ; 500 valeurs d'`enum` et
15 000 caractères de noms de propriétés et de valeurs d'`enum`, d'après des erreurs d'OpenAI
rapportées sur son forum ([500 valeurs](https://community.openai.com/t/500-enums-limitation-in-structured-output/974416),
[15 000 caractères](https://community.openai.com/t/possible-structured-output-schema-length-error-bug-in-api/984509),
lus le 2026-10-26 ; la doc relevée le 2026-10-16 disait 1 000 valeurs, voir « Sources »). Le
schéma du classement porte une propriété par item du lot (`classify-2`) : au plafond de 45 items
et 9 sujets, 45 propriétés, 45 × 10 = 450 valeurs d'`enum` et 6 750 caractères (mesurés le
2026-11-01), sous les trois limites ; un test les tient (`tests/ai_api/test_stages.py`). Les lots
sont passés de 50 à 45 items avec le neuvième sujet, le 2026-11-01 : 50 items auraient donné
500 valeurs, la limite elle-même, jamais essayée sur le modèle ; 45 garde les 450 valeurs d'avant
(50 items, 8 sujets). Un 11e sujet (540 valeurs) ferait échouer ce test avant tout appel réel : il
faudrait alors des lots plus petits.

**Réglages d'appel**, lus dans la configuration (#150) : `reasoning_effort: "none"`
(`KB_LLM_REASONING_EFFORT=none`) pour un modèle à raisonnement, sinon `temperature=0`. Mesure de
#158 sur gpt-6-luna (2026-10-17) : `temperature: 0` seul est refusé (400 `unsupported_value`,
`param` `temperature`) ; avec `reasoning_effort: "none"`, il est accepté, sans preuve qu'il change
la sortie ; `reasoning_tokens` vaut 0. Le client envoie donc `reasoning_effort: "none"` seul ;
option écartée : envoyer les deux (effet non prouvé). Pour gpt-6-luna,
`KB_LLM_REASONING_EFFORT=none` est donc **obligatoire** : sans lui, chaque appel rend un 400, lu
`llm_unavailable`, alors que l'API IA démarre. Chaque requête coupe aussi le cache de prompt
(`prompt_cache_options: {"mode": "explicit"}` sans point d'arrêt ; journal ADR, « Appel du
modèle : cache de prompt coupé ») : le client exige donc un modèle qui accepte ce champ (selon
la doc, un modèle d'avant GPT-5.6 le refuse par un 400) ; un réglage viendra avec un modèle qui
le refuse. Sur Azure AI Foundry, l'URL de base est
`https://<ressource>.openai.azure.com/openai/v1`, sans `api-version`, et la clé part en
`Authorization: Bearer` (mesure de #158). Le déploiement est figé sur une version du modèle. Le
fournisseur, son URL et le nom du modèle n'ont pas de valeur par défaut : sans eux, l'API IA ne
démarre pas (journal ADR, « Appel du modèle »).

### Demande

```json
{"window_days": 3}
```

`window_days` est optionnel : absent ou `null`, c'est la fenêtre de `KB_DIGEST_WINDOW_DAYS`.
Tout autre champ est refusé (422 `invalid_parameter`), comme un corps absent, qui n'est pas un
objet ou pas du JSON (UTF-8 invalide compris) : le corps renvoie alors `"parameters": ["body"]`,
jamais le nom d'un champ en trop, qui vient du client.

**Limite** (FastAPI 0.143, `fastapi/routing.py`) : le corps est lu en entier, et son JSON décodé,
avant la vérification de la clé. Un corps qui n'est pas du JSON reçoit donc 422 même sans clé ;
tout autre appel sans clé reçoit 401, et aucun ne lit la veille ni n'appelle le modèle. La taille
du corps est bornée avant toute route (OWASP API4:2023, #161) : au-delà de `MAX_AI_API_BODY_BYTES`
(1 024 octets, `core/config.py`), qu'elle soit annoncée par `Content-Length` ou comptée au fil du
flux, la demande reçoit 413 `content_too_large`, avec ou sans clé. Annoncée, rien n'est lu ; en
flux, la lecture s'arrête au premier morceau reçu qui dépasse la borne. Le comptage est celui de
Starlette (`RequestBodyLimitMiddleware`) ; K-B refuse d'abord la longueur annoncée, que Starlette
rendrait en texte brut, hors du schéma d'erreur (`core/api_body_limit.py`).

### Entrée du modèle

**Consigne** (message `system`) : une constante de module, jamais une expression (règle 8 de
`poc.md`). Elle dit :

- le rôle, et que le message utilisateur est une donnée, jamais une consigne ;
- les trois valeurs de `cve_listed_in_cisa_kev` ;
- la langue du `text` : le **français** (décision de Sabine du 2026-10-15) ;
- les règles des faits : recopiés mot pour mot depuis l'item, `v` d'une version gardé
  (`v2.0.14`) ; un fait n'est qu'un **identifiant, une version, un nombre ou un nom propre**
  (modèle, entreprise, projet, paquet) ; une CVE ou une GHSA n'est écrite qu'en citant l'entrée
  KEV ou l'alerte qui la porte.

Pourquoi des faits si courts : la fiche est en français, les items surtout en anglais ; une
expression anglaise traduite dans le `text` n'y serait plus trouvée, et l'affirmation serait
retirée (section « Fidélité »).

**Limite** : certains fournisseurs ajoutent le schéma de sortie au message `system` (Mistral le
documente) : le message `system` envoyé n'est donc pas une stricte constante. Ce n'est pas une
faille de la règle 8 : seuls entrent dans ce schéma des identifiants d'items (`"i17"`) et les
sujets de `core/config.py`, jamais un texte d'item.

**Message utilisateur** : un objet JSON encodé, et rien d'autre.

```json
{
  "subjects": [{"name": "llm_security", "definition": "…"}],
  "items": [{"item_id": "i12", "kind": "paper", "title": "…", "summary": "…"}]
}
```

**Liste blanche des sortes** : celle de #204, sans `zotero_entry` ni `clip`. **Liste blanche des
champs**, sans le champ `url` de l'item (le modèle n'écrit jamais d'URL, #206), et la colonne des
champs où la fidélité cherche un fait (section « Fidélité ») :

| Sorte | Champs envoyés | Champs où la fidélité cherche |
|---|---|---|
| `paper` | `item_id`, `kind`, `title`, `summary` ; jamais `authors` (règle 5 de `poc.md`) | `title`, `summary` |
| `vulnerability` | `item_id`, `kind`, `cve_id`, `title`, `description`, `vendor`, `product`, `ransomware_use` | `cve_id` (égalité), `title`, `description`, `vendor`, `product`, `ransomware_use` |
| `release` | `item_id`, `kind`, `repository_name`, `tag_name`, `title`, `body`, où chaque `@login` est masqué en `@user` | `repository_name`, `tag_name`, `title`, `body` |
| `advisory` | `item_id`, `kind`, `ghsa_id`, `cve_id`, `title`, `cve_listed_in_cisa_kev`, `packages` | `ghsa_id` et `cve_id` (égalité), `title`, chaque nom de `packages` |
| `newsletter_article` | `item_id`, `kind`, `edition`, `title`, `summary` | `title`, `summary` |

- **URL masquées** : avant le prompt, dans chaque champ envoyé, toute URL
  (`(?i)[a-z][a-z0-9+.-]*://\S+` et `(?i)www\.\S+`) est remplacée par `[url]`, comme les `@login`
  par `@user` ; le masquage est codé par #204. Ordre : masquer, puis couper (500 ou 2 000
  caractères). La fidélité cherche dans le texte masqué, donc dans les champs envoyés. **Limite** :
  un domaine sans schéma (`example.com/x`) n'est ni masqué ni refusé ; il est rendu en texte non
  cliquable, car CommonMark ne fait un lien que d'un schéma, et GFM, en plus, de `www.`, de
  `mailto:`, de `xmpp:` et d'une adresse mail nue ([doc de pymarkdown, « Extended Autolinks »](https://pymarkdown.readthedocs.io/en/latest/extensions/extended-autolinks/),
  qui suit la spec GFM, lue le 2026-10-21 ; la section de la spec GFM elle-même n'a pas été lue).
- **`@login` masqués** (#204, `ai_api/watch_items.py`), dans `release.body` seul, après les URL
  (une URL peut porter un `@`) : `(?<![A-Za-z0-9_.@/-])@[A-Za-z0-9][A-Za-z0-9-]{0,38}` devient
  `@user`. **Limites** : une adresse mail (`jane.doe@example.com`) n'est pas masquée, la règle ne
  visant que les logins ; un paquet npm (`@anthropic-ai/claude-code`) devient `@user/claude-code`,
  ce qui va dans le sens sûr.

- `cve_listed_in_cisa_kev` est le champ `exploited` de l'API de données, renommé : vrai veut dire
  « la CVE a figuré au catalogue KEV », même si elle en a été retirée depuis ; faux, « absente du
  catalogue KEV », pas « non exploitée » ; nul, une alerte sans CVE
  ([specs-api.md](specs-api.md), détail). Le nom d'origine inviterait le modèle au contresens ; la
  consigne dit les trois valeurs.
- Une entrée retirée (`withdrawn_at` non nul : une vulnérabilité retirée du catalogue KEV) n'est
  pas envoyée : `GET /items` la sert sans filtre ([specs-api.md](specs-api.md), « Réponse »), et le
  modèle la présenterait comme une entrée du catalogue. Elle est comptée dans `items_dropped_before_writing_stage`.
- **Au classement**, chaque item n'envoie que `item_id`, `kind`, `title` et son texte long
  (`summary`, `description` ou `body`) coupé à 500 caractères : classer demande moins de texte que
  rédiger (jetons, délai).
- **À la rédaction**, chaque item envoie les champs du tableau, chacun coupé à 2 000 caractères
  (pour `packages`, chaque nom ; leur nombre est borné par la base, 100 noms de 255 caractères au
  plus, `schema.sql` et `items.py`) ;
  une fiche reçoit **60 items au plus**, les plus récents d'abord : le sujet n'étant connu qu'au
  classement, #204 code la sélection (`select_for_writing`) et #205 l'appelle pour chaque sujet.
- Le découpage des appels de classement (#205) : des lots dans l'ordre de lecture, de 50 items et
  36 000 caractères de message utilisateur (`input_chars`) au plus, soit environ 9 000 jetons
  (#158 : 46 items, environ 5 500 jetons). Une `advisory`, sans texte long, est classée par son
  titre ; un `body` nul de release est envoyé nul.
- `items_truncated` compte les items dont un champ est coupé à 2 000 caractères pour la
  rédaction ; `items_dropped_before_writing_stage`, ceux que les règles du code laissent hors
  d'une fiche avant la rédaction (au-delà de 60, retirés, ou disparus entre la liste et le
  détail : 404 `item_not_found`). Les items sans sujet adapté, sans réponse, ou d'un sujet en
  échec n'y sont pas : ils ont leurs propres champs (`no_suitable_subject`, `unanswered`,
  `failed_subjects`). La coupe à 500 du classement n'y est pas comptée (presque tous les items y
  passent) : elle est comptée par appel, dans la ligne de métrique. **Limite** : la coupe et le
  plafond de 60 ne sont comptés que pour un sujet envoyé à la rédaction ; un sujet laissé en
  `llm_timeout` ou `llm_rate_limited` avant l'envoi n'y ajoute rien.
- `items_capped` est vrai s'il reste au moins un item au-delà de `MAX_ITEMS_PER_DIGEST_REQUEST`
  (section « Lecture plafonnée ») ; ces items ne sont pas lus, donc pas comptés.

### Sortie du classement

`response_format` `json_schema`, `strict: true`. Une réponse par item du lot, sous son
identifiant (consigne `classify-2`) :

```json
{
  "i12": "llm_security",
  "i7": "no_suitable_subject"
}
```

| Champ | Contrainte |
|---|---|
| propriétés | une par item envoyé dans cet appel, dans l'ordre du lot, **toutes dans `required`** ; `additionalProperties: false` |
| valeur | `enum` des sujets de `core/config.py`, plus `no_suitable_subject` (`NO_SUITABLE_SUBJECT_ANSWER`, nom réservé : aucun sujet ne peut le prendre, un test le tient) |
| ensemble | en mode strict, chaque item envoyé reçoit **exactement une** réponse ; le code revérifie (contrôles 2 à 5) et compte un item sans réponse parmi d'autres |

**Trois cas à la sortie** (décision de Sabine du 2026-10-26) :

| Cas | Le modèle | Dans la réponse | Sur la ligne de métrique |
|---|---|---|---|
| catégorisé (x) | répond un sujet de la liste | l'item entre dans la fiche de ce sujet | `items_with_subject` |
| sans sujet adapté (y) | répond `no_suitable_subject` : un **jugement** du modèle | `no_suitable_subject` | `items_no_suitable_subject` |
| non traité (z) | ne répond rien pour l'item : un **raté** du modèle | `unanswered` | `items_unanswered` |

Sur chaque ligne de classement, x + y + z = `items_in` (un test le tient). Le nom de y est celui
qu'a choisi Sabine (« not suitable category », 2026-10-26), le même pour la valeur du modèle, le
champ de la réponse et les compteurs ; il remplace `not_retained`, qui disait le résultat sans dire
pourquoi.

Un item non traité ne fait pas échouer le lot : les autres réponses du lot sont bonnes, et la
demande continue. Il est compté à part, pour ne pas passer pour un jugement. En mode strict, il ne
devrait pas exister : un `items_unanswered` au-dessus de 0 se voit dans les métriques, et manque le
seuil « aucun item oublié » des essais de #210. Un `items_no_suitable_subject` élevé peut dire qu'il manque
un sujet à la liste fermée. Une sortie qui ne répond à **aucun** item, en revanche, ne trie rien :
elle n'est pas comptée, elle est refusée (contrôle 5), avec une nouvelle tentative (revue de code
de la PR de `classify-2`). **Limite** : un item non traité parmi d'autres n'est pas redemandé ; une
seconde chance ciblée (redemander les seuls items oubliés, une fois) viendra si des essais en
montrent.

**Pourquoi une propriété par item** (essai 1 de #210, 2026-10-26, sur la veille réelle). Avec
`classify-1`, la sortie était deux listes, `assignments` (`item_id`, `subject`) et `not_retained`.
Le mode strict ne pouvait pas y interdire un doublon : `uniqueItems` n'est pas pris en charge
([guide OpenAI](https://developers.openai.com/api/docs/guides/prompt-generation), lu le
2026-10-26 ; table des mots-clés refusés de la page Azure citée plus haut). gpt-6-luna a donné à
deux items d'un lot de 50 articles TLDR à la fois un sujet et « non retenu », aux deux tentatives :
le contrôle 5 (doublon) a refusé le lot, et toute la demande a échoué (502 `llm_invalid_output`).
Avec une propriété par item, cet état ne peut plus s'écrire ; le code le revérifie (contrôle 2,
une clé deux fois).
Options écartées : dédoublonner par le code (il réparerait en silence ce que le modèle écrit) ;
laisser un lot en échec sans faire échouer la demande (utile en plus, il ne corrige pas la
cause, et les items du lot seraient perdus) ; des lots plus petits (la probabilité baisse, le cas
reste) ; une phrase de plus dans la consigne (une règle en prose ne tient pas). **Limite** : un
item reçoit un seul sujet ; un sujet secondaire est une piste à décider après les essais de #210.

### Sortie de la rédaction

Un appel par sujet ; `response_format` `json_schema`, `strict: true`.

```json
{
  "claims": [
    {
      "text": "…",
      "item_ids": ["i12", "i40"],
      "facts": [{"value": "CVE-2026-1234", "item_id": "i40"}]
    }
  ]
}
```

| Champ | Bornes | Contrainte |
|---|---|---|
| `claims` | 0 à 12 affirmations (borne de structure, contrôle 2) | aucune : la fiche est rendue vide (le modèle n'a pas à inventer une affirmation pour remplir le schéma) |
| `claims[].text` | 1 à 400 caractères (borne d'affirmation, fidélité) | en français ; sans lien, image ni balise (contrôle 6) |
| `claims[].item_ids` | 1 à 5 (contrôle 2) | `enum` des `item_id` envoyés dans cet appel |
| `claims[].facts` | 1 à 10 (borne d'affirmation, fidélité) | chaque item de `item_ids` porte au moins un fait (fidélité) |
| `claims[].facts[].value` | 3 à 120 caractères (borne d'affirmation, fidélité) | un identifiant, une version, un nombre ou un nom propre, recopié mot pour mot de l'item cité, écrit aussi dans `text` |
| `claims[].facts[].item_id` | — | l'un des `item_ids` de l'affirmation |

Le modèle ne rend pas de `items_not_retained_in_output` à la rédaction : le code le calcule, items envoyés moins
items cités. Un **oubli** n'est donc pas un échec : sur 60 items, un petit modèle en oublie un, et
un seul oubli faisait échouer tout le sujet. La sécurité ne change pas : le contrôle 4 refuse
toujours un identifiant inventé.

Les bornes sont écrites dans la **consigne**, en texte, et non dans le `json_schema` : le schéma
portable n'admet ni `minLength`, ni `maxLength`, ni `minItems`, ni `maxItems` (section
« Schémas »). Le schéma envoyé est donc écrit à la main, et non dérivé du modèle Pydantic, qui
écrirait ces mots-clés (accord du 2026-10-17, commentaire daté sur #205). Le code les vérifie à
deux endroits.
Une **borne de structure** (un type, un champ en trop, plus de 12 affirmations, `item_ids` hors de
1 à 5) fait échouer la sortie (contrôle 2). Une **borne d'affirmation** (longueur du `text` ou d'un
`value`, nombre de faits) ne retire que l'affirmation, comptée (section « Fidélité ») : une
affirmation trop longue n'a pas à faire échouer tout le sujet.

Le **plafond de sortie** de chaque appel (`max_completion_tokens` chez OpenAI et Azure) est au
moins la plus longue sortie que ces bornes permettent (12 affirmations, 5 items et 10 faits de
120 caractères chacune) : une troncature ne vient alors que d'une sortie hors bornes. #205 le
fixe à 8 192 jetons pour la rédaction (`WRITING_MAX_COMPLETION_TOKENS`) : une **estimation**,
environ 24 500 caractères en JSON compact à 3 caractères par jeton (hypothèse ; la note de #158
l'estime à 6 000-7 000 jetons). C'est aussi le plus haut que permet le délai de lecture de 90 s
au débit mesuré par #158, avec 40 % de marge (environ 8 746 jetons ; un test le garde). Au
classement, 2 048 (50 affectations d'environ 25 jetons). Chez un modèle à raisonnement, ce plafond compte aussi les jetons
de raisonnement, attendus à 0 avec `reasoning_effort: "none"` (`reasoning_tokens`, section
« Métriques »).

### Réponse

`200` :

```json
{
  "request_id": "1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e",
  "model": "gpt-6-luna",
  "window": {
    "days": 3,
    "since": "2026-10-12T09:00:00Z",
    "until": "2026-10-15T09:00:00Z",
    "capped_kind": null,
    "covered_after": null
  },
  "digests": [
    {
      "subject": "llm_security",
      "claims": [{"text": "…", "item_ids": [12, 40]}],
      "sources": [
        {"item_id": 12, "kind": "paper", "title": "…", "url": "https://arxiv.org/abs/…"},
        {"item_id": 40, "kind": "advisory", "title": "…", "url": "https://github.com/advisories/…"}
      ],
      "items_not_retained_in_output": [7],
      "claims_removed": 1,
      "items_removed_by_checks": [51]
    }
  ],
  "failed_subjects": [{"subject": "models", "stage": "write", "error": "llm_timeout"}],
  "no_suitable_subject": [3, 9],
  "unanswered": [],
  "items_in": 41,
  "items_truncated": 2,
  "items_dropped_before_writing_stage": 0,
  "items_capped": false
}
```

| Champ | Contenu |
|---|---|
| `request_id` | identifiant de la demande (UUID), repris par chaque ligne de métrique |
| `model` | le modèle de `KB_LLM_MODEL` qui a rédigé les fiches (`replay` pour le replay), écrit par `kb digest` dans chaque fiche (#209) |
| `window` | `days`, et `since` et `until` en UTC, au format des dates de la base ; quand `items_capped` est vrai, `capped_kind`, la sorte coupée, et `covered_after`, la date de son premier item laissé de côté (borne exclue) ; nuls sinon (section « Lecture plafonnée ») |
| `digests` | une fiche par sujet rédigé ; un sujet sans item n'a pas de fiche |
| `digests[].claims` | les affirmations gardées après la fidélité, sans leurs `facts` (contrôle interne) |
| `digests[].sources` | `item_id`, `kind`, `title`, `url` de chaque item des affirmations gardées, lus dans l'API de données, **jamais dans la sortie du modèle** ; une `url` qui ne commence ni par `http://` ni par `https://` est rendue nulle |
| `digests[].items_not_retained_in_output` | les items envoyés pour ce sujet qu'aucune affirmation du modèle ne cite, calculés par le code |
| `digests[].claims_removed` | affirmations retirées par les contrôles (bornes ou fidélité) |
| `digests[].items_removed_by_checks` | items du sujet qui ne sont plus cités après les retraits des contrôles (bornes ou fidélité) |
| `failed_subjects` | chaque sujet en échec, son étape (`stage` : `write`, la rédaction ; son type, `DigestStage`, n'admet que `classify` ou `write` depuis #369) et son état nommé |
| `no_suitable_subject` | items du classement auxquels aucun sujet ne convient : le modèle a répondu `no_suitable_subject` (champ nommé `not_retained` jusqu'à la version 0.2.0, qui y mêlait les items absents de la sortie) |
| `unanswered` | items que le classement a laissés sans réponse, absents des fiches eux aussi (depuis la version 0.3.0 de l'API IA, `classify-2`) |
| `items_in`, `items_truncated`, `items_dropped_before_writing_stage`, `items_capped` | compteurs de la section « Entrée du modèle » |

**Limite** : `sources[].title` est une donnée de source, pas une sortie du modèle ; le filtre du
Markdown ne s'y applique pas. `kb digest` l'écrit en texte dans la fiche (section « Fiches dans le
coffre »).

**Limite** : le `text` d'une affirmation peut recopier une adresse mail d'un item (section
« Entrée du modèle » : une adresse mail n'est pas masquée) ; elle revient dans la
réponse, car le contrôle 6 ne la refuse pas. `kb digest` l'écrit dans la fiche en texte (`@` échappé),
jamais en lien dans Obsidian (recette du 2026-10-21) ; dans un moteur GFM comme celui de GitHub, elle
reste un lien `mailto:` (section « Fiches dans le coffre », « Limites »). Elle reste dans le coffre.

Une erreur rend `{"error": "<état>"}`, comme l'API de données (section « États nommés »). Chaque
réponse, une erreur comprise, porte l'identifiant de sa requête dans l'en-tête `X-Request-ID` :
celui du `request_id` d'une réponse 200, de ses lignes de métrique et de chaque ligne de journal
de la requête.

### Accès

- **Une clé par client** : `KB_AI_API_KEY_<CLIENT>`, avec les règles de `KB_DATA_API_KEY_<CLIENT>` de
  l'API de données ([specs-api.md](specs-api.md), « Accès par clé ») et le même module
  (`core/api_keys.py`, `core/api_access.py`) ; `kb digest` (#209) est le client `KB_DIGEST`,
  `kb trend-report` (#366) le client `KB_TREND_REPORT` ([tendances.md](tendances.md)). Sans
  clé valide, 401 `invalid_api_key`. La clé est fixe ; sa rotation est dans le `README.md`
  (« Changer une clé »).
- **Une route, un client** (OWASP API5:2023) : `POST /digests` s'ouvre à `KB_DIGEST` seul,
  `POST /trend-reports` à `KB_TREND_REPORT` seul (`AI_API_CLIENT_BY_ROUTE`, `core/config.py`). Tout
  autre client à clé valide reçoit 403 `client_not_allowed` ; une route absente de la table est refusée
  à tous.
- **Une demande à la fois par route** (OWASP API4:2023) : tant qu'une demande tourne, la suivante
  reçoit 429 `request_already_running`, avec `Retry-After: 200`, sans file d'attente. Une demande
  court jusqu'à son échéance même si son client est parti : après un Ctrl-C, la relance est refusée
  tant que la première n'a pas fini, environ 200 s au plus. Un digest et un compte rendu peuvent
  tourner ensemble.
- **Débit par client et par route** (OWASP API4 et API6:2023) : 20 demandes par 24 h glissantes sur
  chaque route (`AI_API_RATE_LIMITS`, `core/config.py`), environ 3 fois le pic mesuré du 26 au 29/10 (7 par jour). Au-delà, 429
  `rate_limit_exceeded`, avec `Retry-After`. Ni un 401, ni un 403, ni un refus de concurrence ne comptent.
  **Ce n'est pas un budget** : le compte vit en mémoire, un redémarrage ou un passage à zéro réplique
  le remet à zéro, et il ne vaut que pour une réplique (`maxReplicas: 1` au déploiement, #317). Une
  boucle qui s'emballe est arrêtée, car elle garde la réplique en vie ; un voleur patient de clé ne
  l'est pas. Le compte porte sur les tentatives, pas sur les appels au modèle : un 422 de schéma ou
  une panne rapide consomme aussi. Aucune limite pour les requêtes sans clé valide. Sur le Mac, la
  veille ne compte pas dans les 24 h (`time.monotonic` y lit `mach_absolute_time()`, vérifié le
  2026-11-05) : la fenêtre s'allonge d'autant, la limite est donc plus stricte, jamais plus large.
- **Ordre des contrôles** : 413, 404 ou 405, 422 d'un corps illisible, 401, 403, 429 de concurrence,
  429 de débit, 422 de schéma, puis la route.
- **Pas de `TrustedHostMiddleware`**, écart voulu à la ligne API8 de [specs-api.md](specs-api.md) :
  sans clé, une requête n'atteint que `/health`, et `/docs` et `/openapi.json` en `sandbox`, qui ne
  contiennent aucune donnée, si bien qu'un rebinding DNS n'obtient rien et ne coûte aucun appel. Rappelé à
  « Sécurité : OWASP API Security Top 10 (2023) » (API8), et à revoir en conteneurs (#200), où l'hôte
  appelant change.
- **`GET /health`** répond 200 `{"status": "ok"}` sans clé, comme celle de l'API de données.
- **Méthodes** (OWASP API8:2023) : chaque route n'accepte que sa méthode, `GET` ou `POST` ; `HEAD`,
  que Starlette ajoute à toute route `GET`, est retiré (`core/api_methods.py`), et toute autre
  méthode sur le chemin d'une route, `TRACE` et `CONNECT` compris, rend 405 `method_not_allowed`,
  comme l'API de données ; `CONNECT hôte:port` et `OPTIONS *` rendent 404 `route_not_found` (essayé
  sous uvicorn le 2026-11-05).
- **Documentation** : `/docs` et `/openapi.json` ne sont servis que si
  `KB_DEPLOYMENT_ENVIRONMENT=sandbox`, 404 sinon, comme l'API de données ([specs-api.md](specs-api.md), #393).
- **Version** : `0.12.0` (`info.version` de `docs/api/openapi-ia.json`, écrite par `kb openapi`) ;
  un changement visible par un client change les deux. `0.1.0` : `POST /digests` (#156) ; `0.2.0` :
  `model` dans la réponse (#209) ; `0.3.0` : `unanswered`, et `not_retained` du premier niveau
  renommé `no_suitable_subject` (#210, `classify-2`) ; `0.4.0` : `items_dropped` renommé
  `items_dropped_before_writing_stage`, `digests[].not_retained` renommé
  `digests[].items_not_retained_in_output`, `digests[].items_uncited` renommé
  `digests[].items_removed_by_checks` (décision de Sabine du 2026-10-26) ; `0.5.0` :
  `POST /trend-reports` (#366) ; `0.6.0` : les fiches lues sur GitHub dans la réponse de
  `POST /trend-reports`, et ses erreurs `github_*` (#367) ; `0.7.0` : le choix du modèle dans la
  réponse de `POST /trend-reports`, `model`, `choice_failure` et `chosen` (#368) ; `POST /digests`
  ne change pas ; `0.8.0` : `/docs` et `/openapi.json` en `sandbox` seulement (#393) ; `0.9.0` :
  413 `content_too_large` sur les deux routes, pour un corps de plus de 1 024 octets (#161) ;
  `0.10.0` : 403 `client_not_allowed`, 429 `rate_limit_exceeded` et `request_already_running`, 503
  `data_api_rate_limited` (#161) ; `0.11.0` : `HEAD` refusé sur `/health`, et sur `/docs` et
  `/openapi.json` en `sandbox`, 405 `method_not_allowed` (#161) ; `0.12.0` : les textes de chaque
  dépôt choisi dans la réponse de `POST /trend-reports`, `readme`, `texts`, `texts_removed` et
  `writing_failure`, et `failed_subjects[].stage` de `POST /digests` typé `DigestStage` (`classify`
  ou `write`), sans `select` (#369).

## Contrôles

Chaque sortie du modèle passe ces contrôles **dans cet ordre**, avant tout usage ; le premier qui
échoue nomme l'échec. Le mode strict demande au fournisseur de suivre le schéma ; le code ne s'y
fie pas et revérifie tout (défense en profondeur ; OWASP LLM01:2026 : valider le format de sortie
par du code déterministe).

| N° | Contrôle | Refuse | `failed_check` |
|---|---|---|---|
| 1 | `finish_reason` (liste blanche) | `stop` passe ; `length` → `llm_truncated` ; `content_filter` → `llm_content_filtered` ; toute autre valeur → `llm_invalid_output` (échouer fermé sur une valeur inconnue, `tool_calls` compris) | `content_filter` pour un filtrage ; `finish_reason` pour une valeur hors liste |
| 2 | **Schéma** | un texte qui n'est pas du JSON, une clé deux fois dans un même objet (Pydantic garderait la dernière valeur sans le dire : un item répondu deux fois passerait pour un item répondu une fois ; `is_json_without_key_twice`, `llm_client.py`), un champ en trop (`extra="forbid"`), un type faux, une borne de structure dépassée (plus de 12 affirmations, `item_ids` hors de 1 à 5) | `schema` |
| 3 | **Sujets** | un sujet hors de la liste de `core/config.py` (au classement : une réponse qui n'est ni un sujet de la liste ni `no_suitable_subject`) | `subject` |
| 4 | **`item_id`** | un identifiant qui n'a pas été envoyé dans **cet** appel (un item inventé, ou d'un autre sujet) ; un `facts[].item_id` hors des `item_ids` de son affirmation | `item_id` |
| 5 | **Complétude** (classement) | une sortie qui ne répond à **aucun** item du lot (`{}`, un fournisseur qui ignore le mode strict) ; un item sans réponse parmi d'autres n'est pas refusé, il est compté à part (`unanswered`, `items_unanswered`) ; un item répondu deux fois est refusé par le contrôle 2 (avant `classify-2`, le contrôle 5 refusait un item présent deux fois) | `completeness` |
| 6 | **Markdown** (rédaction) | un `text` qui contient `(?i)[a-z][a-z0-9+.-]*://`, `(?i)www\.`, `(?i)mailto:`, `(?i)xmpp:`, `![`, `[[`, `](`, `]:` ou `<[a-zA-Z/!?]` | `markup` |
| 7 | **Fidélité** (rédaction) | voir ci-dessous : retire l'affirmation, n'est pas un échec | — |

Le choix du compte rendu des tendances suit le même ordre (sujets, `item_id`, puis un contrôle à
lui, `criterion`) : [tendances.md](tendances.md), « Ce que rend #368 ».

- **Contrôles 2 à 6, et une valeur de `finish_reason` hors liste** : `llm_invalid_output`,
  **une** nouvelle tentative (#150) ; au second échec, le sujet échoue (rédaction) ou toute
  la demande (classement). Aucune fiche partielle n'est rendue.
  Une `ValidationError` n'est ni journalisée ni gardée : seul `failed_check` l'est (règle 5 de
  `poc.md`).
- **Contrôle 6** reprend les motifs de #206, avec trois différences (commentaire daté sur #206) :
  - `://` sans casse à la place de `http` : chercher `http` refuserait « HTTP request smuggling »,
    courant dans les descriptions du catalogue KEV, et laisserait passer `HTTPS://` ;
  - `<` n'est refusé qu'au début d'une balise (`<` suivi d'une lettre, de `/`, `!` ou `?`) : une
    plage de versions (« versions < 2.3.1 ») est courante dans les alertes et doit pouvoir être
    recopiée comme fait ;
  - `](` et `]:` s'ajoutent : un lien Markdown sans schéma, et une définition de lien par référence
    (`[a]: javascript:…`, `[a]: //evil.example`), qui n'ont ni `://` ni `<`.
- **`mailto:` et `xmpp:`** s'ajoutent (revue de #206, tranchée par time-knight le 2026-10-21) :
  GFM en fait un lien sans `//`, et un `mailto:` peut porter un sujet et un corps préremplis.
  L'adresse mail nue reste une limite (section « Réponse »).
- **Limite** : le contrôle 6 refuse aussi un texte technique qui n'est pas une balise
  (`Map<K, V>`, un `]:` en milieu de phrase) ; après la nouvelle tentative, le sujet échoue
  (`llm_invalid_output`). `Promise<void>` ou `Vec<u8>` sont des balises en ligne pour CommonMark :
  les refuser est voulu. Le nombre de `failed_check` = `markup` est relevé par les essais sur la
  veille réelle (#210).

### Fidélité

Une fiche ne dit que ce que disent ses items (#207).

**Normalisation**, avant toute recherche, du `text`, des faits et des champs de l'item : Unicode
NFKC, `casefold`, retrait des caractères invisibles (catégorie Unicode `Cf` : U+200B, U+00AD,
U+2060…), espaces réduites à une seule, tirets Unicode (U+2010 à U+2015, U+2212) ramenés à `-`,
apostrophes et guillemets typographiques (U+2018, U+2019, U+201C, U+201D) ramenés à `'` et `"`.

**Faits CVE et GHSA.** Les motifs s'appliquent après la normalisation, sur un **texte de
détection** : les marques d'emphase `*` et `=` retirées (`CVE-2026-00**01**` s'affiche comme un
identifiant), et les lettres cyrilliques, grecques et petites capitales latines qui ressemblent à
une lettre d'un préfixe lues comme elle (`СVЕ` cyrillique se lit `cve`), puis toute autre lettre,
chiffre ou symbole hors ASCII qui n'est pas une lettre ASCII accentuée lu comme `o` (`é` reste `é`,
pour que `numéro` se lise ; `CVE-2026-ЗЗЗЗ` se lit `CVE-2026-oooo`). Écrits sur ce texte, en
minuscules (`ai_api/stages/fidelity.py`, `CVE` et `GHSA`), avec `S` = `[\W_]*` :

- CVE : `c S v S e [s] S [mot de numéro S] [\doli]{4} S [\doli]{4,}` ;
- GHSA : `g S h S s S a [s] S [mot de numéro S] [0-9a-z]{4} S [0-9a-z]{4} S [0-9a-z]{4}`.

Un séparateur peut couper le préfixe (`C.V.E.`, `C*V*E`), et un `s` de pluriel le suivre (« les
CVEs 2026-0001 »). Le **mot de numéro**, facultatif, est `n`, `no`, `nr`, `num`, `numero`, `numéro`,
`number`, `id`, `identifiant`, `ref`, `réf`, `reference` ou `référence` (`№` devient `no` par
NFKC) : « la CVE n°2026-0001 » est une tournure française que le modèle écrit sans attaque. `o`, `l` et `i` comptent
pour des chiffres : `CVE-2026-OOO1` est lu, et n'est jamais égal à un vrai identifiant. Ces règles
de détection sont des décisions de time-knight sur la revue de sécurité de #207 (délégation de
Sabine du 2026-10-15) ; `AAAA-NNNN` seul n'est pas lu comme un identifiant, car `2025-2026` le
deviendrait.

Un séparateur est toute suite sans lettre ni chiffre (décision de Sabine du 2026-10-24, plan de
#207) : avec `[\s-]*`, `CVE_2026_0001` ou `CVE.2026.0001` n'était pas un motif ; déclaré en fait,
il devenait un fait ordinaire, trouvé si un item piégé l'écrivait ainsi, et le piège de #206
passait sous cette écriture. Un identifiant de la phrase finit à une limite, comme tout fait (ni
lettre ni chiffre après lui, ni `.` ou `-` suivi d'une lettre ou d'un chiffre) : `GHSA-fjqc-hq36-qh5pxx`
ou `CVE-2026-86950abc` ne sont pas lus comme `GHSA-fjqc-hq36-qh5p` et `CVE-2026-86950` (revue de
#207, tranchée par time-knight, délégation de Sabine du 2026-10-15).

Un fait qui **contient** l'un de ces motifs est un fait CVE ou GHSA, quelle que soit son écriture
(`cve 2026-1234` compris). Il doit être **égal**, une fois ramené à sa forme canonique
(`CVE-AAAA-NNNN`, `GHSA-xxxx-xxxx-xxxx`), au `cve_id` ou au `ghsa_id` de l'item qu'il cite, jamais
trouvé dans un texte libre. Un article TLDR n'a pas de tel champ : il ne porte pas de fait CVE ; la
fiche cite la CVE par l'entrée KEV ou par l'alerte, si elles sont dans la fenêtre (décision de
Sabine du 2026-10-15). Comme tout fait, un fait CVE ou GHSA doit aussi figurer dans le `text` de
son affirmation ; et tout motif CVE ou GHSA écrit dans un `text` doit être déclaré comme fait.
Dans le `text`, la comparaison se fait par forme canonique : `cve 2026 86950` dans la phrase est le
fait `CVE-2026-86950`. Un fait qui contient plus que le motif (`CVE-2026-86950 (Apple)`) n'a pas
de forme canonique : il n'est pas trouvé. Le fait est comparé à l'item **qu'il cite**
(`facts[].item_id`), plus strict que « un item cité » du journal ADR (2026-10-15).

**Autres faits.** Chaque `facts[].value` doit figurer dans le `text` de son affirmation **et** dans
la valeur de l'un des champs où la fidélité cherche, pour l'item qu'elle cite (tableau de la
section « Entrée du modèle ») : champ par champ, jamais dans une concaténation de champs, jamais
dans `kind`, `item_id` ni `cve_listed_in_cisa_kev`. Une valeur est trouvée seulement entre deux
**limites** : juste après elle, ni lettre ni chiffre, ni `.` ou `-` suivi d'une lettre ou d'un
chiffre ; juste avant, la même règle (ni lettre ni chiffre, ni `.` ou `-` précédé d'une lettre ou
d'un chiffre). Ainsi `1.2` n'est pas trouvé dans `1.2.9`, ni `CVE-2026-1234` dans
`CVE-2026-12345`. « Lettre ou chiffre » s'entend au sens Unicode, après la normalisation : `caf`
n'est pas trouvé dans `café`. Un champ nul (`body`, `cve_id` d'une alerte sans CVE) est sauté ;
chaque nom de `packages` est un champ ; `cve_id` et `ghsa_id` ne servent qu'à l'égalité d'un fait
CVE ou GHSA, jamais à la recherche d'un fait ordinaire. Les repères que K-B pose lui-même dans les
champs (`[url]`, `@user`, section « Entrée du modèle ») sont retirés avant la recherche : un fait
`@user` ne dit rien de l'item (revue de #207, décision de time-knight). La fin d'un champ coupé pour la rédaction
(2 000 caractères, `MAX_FIELD_CHARS_FOR_WRITING`) n'est pas une limite : `…1.2` coupé peut être le
début de `1.2.9`, et `1.2` n'y est pas trouvé (revue de #207, même décision). Un champ d'exactement
2 000 caractères est traité comme coupé, ce qui va dans le sens sûr.

**Texte déguisé.** Une affirmation dont le `text` brut contient un caractère invisible `Cf`, sauf
U+200D (le liant des emoji composés), est retirée : un contrôle de direction U+202E affiche
`1000-6202-EVC` comme `CVE-2026-0001`, et les tags U+E0000 à U+E007F font entrer au coffre un texte
que la lectrice ne voit pas. Faux positifs rares, dans le sens sûr : U+00AD, U+200B, U+2060, le
drapeau écossais (fait de tags). De même, une affirmation dont le `text` contient, une fois
normalisé, un caractère qui cache ou déguise (une marque `Mn` ou `Me`, un point de code privé `Co` ou non attribué `Cn`, un
remplissage hangul ou braille U+115F, U+1160, U+3164, U+FFA0, U+2800, qui s'affiche en blanc), ou
un mot qui mêle des lettres latines à une lettre non latine qui peut leur ressembler, est retirée
et comptée (décision de time-knight sur la revue de sécurité de #207, délégation de Sabine du
2026-10-15). Le mot se lit avant le `casefold` : la capitale grecque `Ε` ressemble à `E`, sa
minuscule `ε` non. Une lettre grecque qui ne ressemble pas à une lettre latine reste permise à côté
de lettres latines, car les titres d'articles en portent (`5 µs`, que NFKC écrit avec un μ grec) ;
`β-VAE` et `α-Fold` ne mêlent rien, le tiret séparant les mots. Une lettre modificative (`Lm`,
comme l'apostrophe U+02BC de `lʼéquipe`) ne ressemble à aucune lettre latine : elle est permise. Cette règle porte sur l'affirmation,
pas sur un fait : elle n'entre pas dans le taux.

**Fait sans lettre ni chiffre.** Un fait qui n'a ni lettre ni chiffre une fois normalisé (`"   "`,
trois U+200B) n'est pas trouvé (décision de Sabine du 2026-10-24, plan de #207) : sa chaîne vide ou
son espace serait trouvé entre ses limites presque partout, et un item se ferait citer pour un fait
qui ne dit rien de lui. Un fait n'est pas rogné : ` v2.1.287 ` n'est pas trouvé (sens sûr).

**Chaque item cité porte un fait.** Chaque item de `item_ids` porte au moins un fait trouvé : un
item ne peut pas se faire citer à côté d'une affirmation qui ne dit rien de lui.

**Bornes d'affirmation.** Un `text` hors de 1 à 400 caractères, un `value` hors de 3 à 120, ou un
nombre de faits hors de 1 à 10 retire l'affirmation (section « Sortie de la rédaction »).

**Ce qu'est un fait.** La consigne limite un fait à un identifiant, une version, un nombre ou un
nom propre, recopié mot pour mot : la fiche est en français, l'item souvent en anglais, et une
expression traduite ne serait plus trouvée. Le code ne vérifie pas cette catégorie : il cherche la
valeur, c'est tout.

Une affirmation qui manque à l'une de ces règles est **retirée et comptée** (`claims_removed`) ;
ce n'est pas un échec. Un item qui n'est plus cité après ces retraits passe dans `items_removed_by_checks`.
Si toutes les affirmations d'un sujet sont retirées, la fiche est rendue sans affirmation : c'est
ce qui a été observé. `fidelity_rate` = `facts_found` / `facts_checked`.

**Ce qui est compté** (décision de Sabine du 2026-10-24, plan de #207). `facts_checked` compte
chaque fait de chaque affirmation d'une sortie contrôlée, y compris d'une affirmation retirée pour
une borne ; `facts_found`, ceux qui sont trouvés. Le taux mesure ce que le modèle recopie, comme
Faithfulness de Ragas, qui met toutes les affirmations au dénominateur
([doc de Ragas, « Faithfulness »](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness),
lue par time-knight le 2026-10-24), et comme `check_evidence.py`, qui vérifie chaque candidat
(`docs/veille/2026-09-23-fiches-existant/Astro-Han_karpathy-llm-wiki.md`, l. 37). Les règles
propres à l'affirmation (motif CVE ou GHSA non déclaré, item cité sans fait trouvé) n'entrent pas
dans le taux : il peut valoir 1 avec des retraits, et se lit avec `claims_removed`. Un `text` vide
rend ses faits non trouvés. `fidelity_rate` est sur la ligne de chaque appel de rédaction
(section « Métriques »), arrondi à 4 décimales, nul quand aucun fait n'est vérifié ; le taux d'un
essai est la somme des `facts_found` sur la somme des `facts_checked` de ses lignes `write`, pas la
moyenne des taux. Option écartée : ne compter que les affirmations dans leurs bornes (un fait exact
d'une affirmation trop longue ne compterait pas).

**Les deux moitiés du fait trouvé** (#518). `facts_found` mêle deux questions : le fait est-il dans
l'item qu'il cite (sinon, le modèle l'a inventé ou pris hors de ces règles), et est-il écrit dans le
`text` (sinon, le modèle n'a pas suivi la consigne) ? `facts_found_in_item` et `facts_found_in_text`
les comptent à part, chacune sans regarder l'autre, avec les mêmes règles que ci-dessus (forme
canonique d'une CVE ou d'une GHSA, limites, champs où chercher). Ainsi, une CVE que l'item ne porte
que dans un texte libre (le corps d'une release, le résumé d'un article) compte comme absente de
l'item, puisqu'elle n'est cherchée que dans `cve_id` et `ghsa_id`. Un fait sans lettre ni chiffre,
ou un fait qui contient plus qu'un motif CVE ou GHSA (`CVE-2026-86950 critique`, sans forme
canonique), n'est trouvé ni dans l'un ni dans l'autre (`both`). `facts_found` compte les faits
trouvés aux deux, et le taux reste `facts_found` / `facts_checked`. Sur le jeu de référence de #479
(`write-1`, enregistré le 2026-11-08), les 26 faits vérifiés sont dans leur item, 14 dans leur
`text` : aucun fait absent de son item, 12 faits non recopiés dans la phrase
(`tests/ai_api/test_digests_reference.py`).

**Partie commune avec le wiki (#153).** Le contrôle de fidélité du wiki reprend d'ici la
normalisation, la recherche mot pour mot entre deux limites et le taux calculé à chaque appel
(critère de #153) ; le code est `ai_api/stages/fidelity.py`. Il n'en reprend pas ce qui tient aux items :
les champs où chercher par sorte et l'égalité des CVE et GHSA à un champ identifiant, qu'un clip
n'a pas.

- **Ce qu'elle vérifie** : chaque valeur déclarée est écrite dans la phrase et existe, entre ses
  limites, dans un champ de l'item qu'elle cite ; chaque identifiant CVE ou GHSA de la phrase est
  celui de l'item cité ; chaque item cité porte un fait.
- **Ce qu'elle ne vérifie pas** : le sens de la phrase (une négation, une paraphrase fausse, un
  sens changé à la traduction) ; un nombre écrit dans la phrase sans être déclaré ; ce que l'item
  dit au-delà des caractères envoyés. Un mot courant déclaré comme fait (« release », « model »)
  passe encore. Option écartée : une liste de mots vides, une liste de plus à tenir pour un gain
  faible. **Limite** : le sens de la phrase, le nombre non déclaré et la traduction ne sont
  vérifiés par aucune étape (section « Ce que la spec ne couvre pas ») ; la fidélité reste sans
  modèle.
- **Limite assumée** : un idéogramme ou une autre lettre non latine collée à des lettres latines
  dans un même mot (un nom de produit suivi d'un caractère chinois) retire l'affirmation, comme un
  sosie (revue de #207, décision de time-knight) ; rare dans une fiche en français.
- **Limite assumée** : la détection lit large, dans le sens sûr. « Le CV en 2026, 0001 candidats »
  est lu `CVE-2026-0001`, non déclaré, et retire l'affirmation ; un emoji suivi du sélecteur de
  variante U+FE0F (`Mn`) aussi.
- **Limite** : ne sont pas lus comme un identifiant `CVE-2026-0001a` (une lettre après le numéro :
  il s'affiche autrement que l'identifiant visé), une phrase sans identifiant (« la faille
  2026-0001 » : le sens n'est pas vérifié, et aucune expression régulière ne l'attrape), ni un sosie
  hors de la liste (`PREFIX_LOOKALIKES`, `GREEK_LOOKALIKES`) ; une table complète des sosies
  (UTS #39) demanderait une dépendance. L'écrivain du coffre retire les caractères `Cc` et `Cs` et
  les douze contrôles bidirectionnels, pas les autres `Cf` (un tag U+E0041) (`post/vault_files.py`) :
  la fidélité retire toute affirmation qui porte un `Cf` autre que U+200D, si bien qu'aucun
  caractère invisible d'une affirmation n'arrive au coffre.
- **Limite** : un chiffre accentué (`CVE-2026-0ö01`) n'est pas lu comme un identifiant, la lettre
  ASCII accentuée restant elle-même ; le tréma se voit. Un symbole collé après un vrai identifiant
  (`CVE-2026-0001🔥`) se lit `o` et rend l'identifiant différent : l'affirmation est retirée, ce qui
  va dans le sens sûr. Décisions de time-knight sur la seconde revue de #207 (délégation de Sabine
  du 2026-10-15).
- **Limite assumée** : un motif CVE peut joindre deux nombres d'une liste (« les CVE 2025, 2026 et
  2027 » se lit `CVE-2025-2026`) ; non déclaré, il retire l'affirmation, ce qui va dans le sens sûr
  (revue de #207, même décision ; un test le fige).
- **Limite assumée** : un motif GHSA peut être un faux positif dans une phrase française (« les
  GHSA dont deux sont critiques » : quatre lettres, trois fois) ; non déclaré, il retire
  l'affirmation, ce qui va dans le sens sûr.
- **Limite** : la borne de 3 à 120 caractères d'un fait se mesure sur la valeur reçue, avant la
  normalisation : `v2` suivi d'un U+200B la passe et devient `v2`, 2 caractères. Signalé par le plan
  de #207, non tranché ; le fait doit encore figurer dans la phrase et dans l'item.
- **Limite assumée** : `1.2.0` n'est pas trouvé dans `v1.2.0` ; l'affirmation est retirée,
  l'erreur va donc dans le sens sûr.

### Injection d'instructions

Un item collecté peut porter une consigne (OWASP LLM01:2026, injection indirecte). Ce que fait la
spec :

- la consigne est une constante de module ; sujets et items vont dans le message utilisateur,
  encodés en JSON ; aucun texte d'item n'entre dans un message `system` (règle 8 de `poc.md`) ;
- les URL des champs envoyés sont masquées en `[url]`, et le champ `url` n'est pas envoyé ; tout
  lien, image ou balise en sortie est refusé (contrôle 6) ;
- un item piégé ne peut ni créer un sujet (contrôle 3), ni citer un item inventé (contrôle 4) ;
- une affirmation sur une CVE tirée d'un texte libre est retirée, et un item cité sans fait trouvé
  aussi (fidélité).

La consigne n'est pas la défense ; le schéma fermé et les contrôles le sont. Ce que la spec ne
couvre pas : un item qui oriente le classement entre deux sujets permis ; une phrase fausse
appuyée sur des faits vrais, dont la fidélité ne vérifie pas le sens (« Ce qu'elle ne vérifie
pas »).

## Sécurité : OWASP API Security Top 10 (2023)

L'auto-évaluation de l'API IA, mesure par mesure (section « How To Prevent » de chaque entrée de
l'édition 2023, la dernière au 2026-11-05), au commit qui la contient (#161). Le pendant de
l'API de données est dans [specs-api.md](specs-api.md). Le référentiel de la certification
(RNCP37827) renvoie à l'édition 2019, la première ; K-B suit l'édition 2023, la seconde, toujours
la dernière le 2026-11-10 (page du projet OWASP). Le top 10 des API est la grille de K-B parce que
K-B n'expose que deux API HTTP, l'API de données et l'API IA : sa console, `kb`, les lance et en
est le client, sans interface web ni compte humain. « Tenue » dit la mesure appliquée et sa
preuve : un test, un essai daté ou le passage du code cité ; « non tenue » dit pourquoi, et où
elle se tiendra : une mesure nécessaire, non intégrée ; *s.o.* : sans objet pour cette API ;
« écart voulu, justifié » dit une mesure non appliquée par décision, dont la justification, écrite
sous son entrée, démontre qu'elle n'est pas nécessaire à K-B et nomme sa limite, ce qui la rendrait
nécessaire ; un écart voulu dans une mesure tenue (« Pour lever l'écart ») la laisse tenue. Une
entrée est tenue quand toutes ses mesures applicables le sont ; elle est un écart voulu, justifié
quand ses mesures applicables sont tenues ou justifiées, au moins une justifiée ; elle est non
tenue dès qu'une mesure l'est. « Au déploiement » renvoie au déploiement sur Azure Container Apps :
au 2026-11-05, une case de #317 (« Plus tard : déploiement », sans jalon) le porte, et aucune
issue du jalon « Mise en ligne 08/11 ».

« **Pour la tenir** » dit comment chaque mesure non tenue le serait, et « **Pour lever l'écart** »
comment on lèverait un écart voulu d'une mesure tenue, avec sa taille (XS ≤ 1 h, S ≤ 3 h, M ≈ 6 h,
L ≈ 15 h), ou « non chiffré », et ce dont elle dépend ; rien n'en est codé (décision de Sabine du
2026-11-05 : dire comment on ferait, sans le faire maintenant). Ce qui touche à ACA vient de sa
documentation, lue le 2026-11-05 (« Sources de l'auto-évaluation ») ; ce qu'elle ne dit pas est
écrit « à vérifier au déploiement ». API8 et API10 sont relues point par point le 2026-11-08 (#454),
contre `infra/` et l'état en ligne.

| Entrée | État | Ce qui reste, et où |
|---|---|---|
| API1 Broken Object Level Authorization | **Tenue** | — |
| API2 Broken Authentication | Écart voulu, justifié | Deux écarts voulus, justifiés sous API2 : « Anti-force brute, plus strict que la limite de débit » (décision de Sabine du 2026-11-05 ; clé de 256 bits, 32 caractères au moins contrôlés au démarrage) et l'authentification TLS mutuelle entre programmes (entrée interne, aucun client hors de l'environnement) |
| API3 Broken Object Property Level Authorization | **Tenue** | — |
| API4 Unrestricted Resource Consumption | Non tenue | Plafond de dépense : mesure nécessaire non intégrée, #501 (`budget-kb` ne compte pas le modèle, non étiqueté ; en ligne, la borne est le quota de 140 000 jetons par minute). Ressources des conteneurs : CPU, mémoire et répliques tenus par #414 ; redémarrages, descripteurs et processus : écart voulu, justifié (aucun processus lancé, aucun client hors de l'environnement) |
| API5 Broken Function Level Authorization | **Tenue** | — |
| API6 Unrestricted Access to Sensitive Business Flows | **Tenue** | — (limite : en ligne, le débit repart de zéro à chaque réveil ; API4, #501) |
| API7 Server Side Request Forgery | **Tenue** | — |
| API8 Security Misconfiguration | Non tenue | Mesures nécessaires non intégrées : durcissement dont la construction et la relecture seraient exigées (#496) ; revue périodique de la configuration en ligne (#497) ; évaluation automatisée de l'environnement déployé, scan de l'image (#498) et sondes après déploiement (#499). Chaîne Envoy → uvicorn, relue le 2026-11-08, non essayée : écart voulu, justifié le 2026-11-10 (aucun client tiers) |
| API9 Improper Inventory Management | Écart voulu, justifié | Documentation sans clé en `sandbox` seulement : écart voulu, justifié sous API9, « Documentation réservée aux utilisateurs autorisés » ; l'API IA en ligne (`ca-kb-ai-api`) est déployée avec `KB_DEPLOYMENT_ENVIRONMENT` à `production` (`infra/main.bicep:234`, non relu en ligne), où `/docs` et `/openapi.json` rendent 404 ; protections externes : écart voulu, justifié sous API9 (aucune version exposée) |
| API10 Unsafe Consumption of APIs | Non tenue | Portée du jeton de Grafana Cloud : mesure nécessaire non intégrée, case ouverte jusqu'au jeton de production refait par #522, sur la seule pile ; le reste tenu (relue le 2026-11-08) |

Le compte : 5 entrées tenues sur 10 (API1, API3, API5, API6, API7). Les 5 autres : 2 écarts voulus
et justifiés, API2 (anti-force brute, TLS mutuel) et API9 (documentation en `sandbox`, protections
externes), dont chaque justification démontre que la mesure n'est pas nécessaire à K-B et nomme sa
limite ; et 3 non tenues, des mesures nécessaires non intégrées : API4 (plafond de dépense, #501),
API8 (durcissement, revue et évaluation, #496 à #499) et API10 (portée du jeton de Grafana Cloud,
#522). Ce qui ne dépend que du code et de la doc est tenu ou justifié ; le reste attend ces issues.

### API1:2023 Broken Object Level Authorization

- **Autorisation fondée sur une politique** : tenue. Une seule propriétaire ; une clé par client
  et un client par route (« Accès ») ; la clé et le droit sont des dépendances de l'app
  (`ai_api/app.py`) : aucune route du modèle ne peut les oublier. `/health`, et `/docs` et
  `/openapi.json` en `sandbox`, routes de Starlette sans donnée, répondent sans clé.
- **Contrôle dans chaque fonction qui lit un enregistrement à partir d'une entrée du client** :
  tenue. Les entrées du client ne désignent qu'une période (`window_days`, `after`,
  `previous_first_window`) ; sans clé valide, rien n'est lu :
  `test_a_request_without_a_valid_key_is_refused_before_any_reading`, sur chaque route.
- **Identifiants aléatoires et imprévisibles** : *s.o.*, aucune route ne prend d'identifiant ; les
  entiers des réponses (`item_id`, `repository_id`) ne sont relus par aucune route de l'API IA.
- **Tests du mécanisme d'autorisation** : tenue. `test_only_the_public_routes_answer_without_a_key`
  et `test_a_client_is_refused_403_on_a_route_that_is_not_its_own`
  (`tests/ai_api/test_digest_router.py`) ; la CI doit passer avant une fusion.

### API2:2023 Broken Authentication

- **Connaître tous les flux d'authentification** : tenue. Un seul, `Authorization: Bearer`, sans
  route de connexion (`core/api_access.py`).
- **Comprendre ses mécanismes** : tenue. La clé identifie un programme, `KB_DIGEST` ou
  `KB_TREND_REPORT`, jamais une personne.
- **Suivre les standards, ne pas réinventer** : tenue.
  - Bearer, avec `WWW-Authenticate: Bearer` sur le 401 (RFC 6750). Sur `POST /digests`, le même
    corps et l'en-tête sans clé, avec une clé inconnue ou un `Bearer` vide :
    `test_a_request_without_a_valid_key_is_refused_before_any_reading`
    (`tests/ai_api/test_digest_router.py`) ; sur `POST /trend-reports`, le test du même nom
    n'essaie que l'absence d'en-tête, et ne vérifie que le 401.
  - Comparaison en temps constant, `hmac.compare_digest`, avec chaque clé (`core/api_access.py`) ;
    non mesurée par un test.
  - Clé de 32 caractères au moins, dans l'alphabet de `secrets.token_urlsafe`, refusée au
    démarrage sinon (`core/api_keys.py`) : la clé trop courte par
    `test_serve_ai_exits_2_and_names_the_variable_refused`, le caractère hors alphabet par
    `test_a_key_of_a_character_out_of_the_rule_is_refused_without_being_quoted`
    (`tests/post/test_ai_api_client.py`) et par `test_serve_exits_2_and_names_the_variable_without_its_value`
    (`tests/data_api/test_serve_data.py`), sur la même fonction ; une clé égale à celle que l'API
    IA envoie à l'API de données est refusée
    (`test_serve_ai_exits_2_when_a_client_has_the_key_it_sends_to_the_data_api`).
- **Utiliser l'OWASP Authentication Cheat Sheet** : confrontée le 2026-11-05, tenue, avec deux écarts
  voulus, justifiés (l'anti-force brute et le TLS mutuel). La
  plupart de ses consignes portent sur les mots de passe, les comptes humains, la MFA ou les
  sessions : *s.o.* Celles qui s'appliquent à une clé entre programmes :
  - comparaison en temps constant : tenue (`hmac.compare_digest`) ;
  - messages et codes d'erreur génériques, sans énumération : tenue, le même 401 pour toute clé
    refusée (ci-dessus) ;
  - journal des échecs : tenue, chaque requête est journalisée avec son statut et son client, sauf
    un `/health` qui répond 200 ; `client=-` sans clé valide (`core/api_request_log.py`, module
    des deux API, `test_a_401_is_logged_without_name_nor_received_value` dans
    `tests/data_api/test_request_log.py`). Aucune revue ni alerte sur les 401 à ce commit ;
  - limitation des essais et défenses contre les attaques automatisées : écart voulu, justifié,
    c'est l'anti-force brute ci-dessous ;
  - transport sous TLS : tenu en ligne ; sur la machine, `http` sur `127.0.0.1`, joignable de la
    machine seule (API8, « TLS, même pour une API interne ») ;
  - authentification TLS mutuelle entre programmes : non appliquée, écart voulu, justifié. Elle
    n'est pas nécessaire : ACA la propose pour un client du dehors (« When your apps are
    communicating with a client outside of the environment, two-way authentication with mTLS is
    supported. »), et l'API IA n'en a aucun ; entre les apps de l'environnement, la même page dit
    l'authentification faite (« Applications within a Container Apps environment are automatically
    authenticated. However, the Container Apps runtime doesn't support authorization for access
    control between applications using the built-in peer-to-peer encryption. », page du
    chiffrement entre apps, lue le 2026-11-10) : l'autorisation reste à la clé et au droit par
    route. Le mTLS de l'environnement, `peerAuthentication.mtls`, reste désactivé
    (`infra/modules/container-apps-environment.bicep:38-42`). Son entrée est interne
    (`infra/modules/api-container-app.bicep:74-80`), aucune route HTTP de l'environnement ne la vise
    (API8, « TLS, même pour une API interne »), et seuls les apps et les jobs de l'environnement
    l'atteignent. À ce commit, deux apps, les deux API, et deux jobs (`infra/deployment.json`), dont
    un seul l'appelle : `caj-kb-smoke-test`, sur `/health`, sans clé ; `kb digest` et
    `kb trend-report`, ses clients à clé, n'ont pas de job en ligne. Ce que le certificat prouverait,
    qu'un appelant est un client permis, la clé le prouve déjà (« Anti-force brute », ci-dessous),
    sous le chiffrement entre apps (API8). Sur la machine, l'écoute sur `127.0.0.1` n'admet que les
    programmes de la machine.
    **Limite** : une entrée externe, une route HTTP de l'environnement qui viserait l'app, ou un
    client hors de l'environnement.
    **Pour réduire le risque** : relire à chaque version `external`, `allowInsecure` et les routes de
    l'environnement, par les commandes d'API8 (« TLS, même pour une API interne »), en lecture
    seule ; #497 en fait la règle.
    **Pour la tenir**, si la limite est franchie : `clientCertificateMode: require` sur l'entrée
    d'ACA, un certificat par client ; l'entrée transmet le certificat à l'app dans
    `X-Forwarded-Client-Cert`, et la page des certificats clients, relue le 2026-11-10, ne dit pas si
    elle en valide la chaîne. Si l'app doit la valider, il lui faut une bibliothèque de certificats
    (`cryptography`, une dépendance directe nouvelle) ; les clients (`core/outbound.py`) enverraient
    leur certificat et leur clé. M.

  La section « API Keys » de la REST Security Cheat Sheet, que la fiche ne cite pas, est tenue :
  clé exigée sur chaque point d'accès protégé, 429 au-delà du débit (#400), clé jamais dans l'URL,
  révocation par rotation (`README.md`, « Changer une clé »). Elle demande de ne pas s'en remettre
  à la seule clé pour une ressource de valeur : la clé s'ajoute au droit par route, au débit et à
  l'écoute sur `127.0.0.1`, et en ligne à l'entrée interne (TLS mutuel, ci-dessus).
- **Anti-force brute, plus strict que la limite de débit** : non appliqué, écart voulu, justifié
  (décision de Sabine du 2026-11-05). La limite de débit ne compte que les clients à clé valide ;
  les essais de clé ne sont pas limités. Il n'est pas nécessaire :
  - la recherche exhaustive d'une clé est impraticable. La commande du `README.md`
    (`secrets.token_urlsafe(32)`) génère une clé de 256 bits ; le code n'en contrôle que le
    minimum, 32 caractères de l'alphabet, soit 192 bits. Le NIST définit sa catégorie 5, la plus
    haute face à un ordinateur quantique, par la recherche d'une clé AES de 256 bits (NIST IR
    8547, tableau 1), et juge que doubler la longueur d'une clé suffit contre l'algorithme de
    Grover (NIST IR 8105, 2016). Même en supposant son gain quadratique appliqué à des essais en
    ligne, il resterait environ 2^128 essais, 2^96 au minimum contrôlé ; à 10 000 requêtes par
    seconde (débit supposé), plus de 10^34 secondes, et plus de 10^24 au minimum ;
  - une limite des 401 par adresse bloquerait les clients légitimes : en local, tous viennent de
    `127.0.0.1`, et un essai répété couperait `kb digest` ;
  - en ligne, seuls les apps et les jobs de l'environnement atteignent l'entrée interne (TLS mutuel,
    ci-dessus) : un essai de clé ne peut venir que d'une pièce de K-B.

  **Limite** : une clé qui n'est pas tirée au hasard (le code contrôle sa longueur et son alphabet,
  pas son hasard), ou une entrée externe, qui ouvrirait les essais au réseau.
  **Pour réduire le risque** : tirer chaque clé par la commande du `README.md`, et la changer
  (« Changer une clé ») dès qu'elle a pu fuir ; garder l'entrée interne (TLS mutuel,
  ci-dessus).

  **Pour la tenir**, si la limite est franchie : compter les 401 par adresse de client et rendre 429
  au-delà d'un seuil à fixer, dans une table à part, bornée : le compteur du débit
  (`core/api_rate_limit.py`) ne connaît que les clients qu'une clé valide nomme, d'où sa taille
  bornée, alors qu'une table par adresse doit oublier les plus anciennes. Derrière l'entrée d'ACA,
  l'adresse vient de `X-Forwarded-For`, dont ACA ne fournit que la valeur la plus à droite ;
  uvicorn 0.54 ne la lit que des adresses de `FORWARDED_ALLOW_IPS` (`127.0.0.1,::1` par défaut, K-B
  ne la règle pas), qui prendrait l'adresse ou la plage de l'entrée, à vérifier au déploiement.
  S.
- **Récupération d'identifiants, ré-authentification, MFA, verrouillage, captcha, mots de passe
  faibles** : *s.o.*, ni compte, ni utilisateur humain, ni mot de passe.
- **Clés d'API pour les seuls clients d'API** : tenue. Les deux clients sont des commandes de K-B.

### API3:2023 Broken Object Property Level Authorization

- **N'exposer que les propriétés auxquelles le client a droit** : tenue. Réponses en liste blanche,
  affirmations sans leurs `facts` (« Réponse »). Limite écrite : le texte d'une affirmation peut
  recopier une adresse mail d'un item (« Réponse »).
- **Choisir les propriétés une à une, sans méthode générique** : tenue. Chaque champ est recopié
  par son nom (`ai_api/routers/digest_router.py`, `ai_api/routers/trend_report_router.py`).
- **Pas de liaison automatique des entrées** (*Mass Assignment*) : tenue. Schémas fermés,
  `extra="forbid"` et `strict=True` (`ai_api/schemas/`) ;
  `test_a_malformed_request_is_refused_422_before_any_call` (`POST /digests`) et
  `test_a_malformed_request_is_refused_422_on_its_body_before_any_reading` (`POST /trend-reports`,
  un champ en trop compris).
- **Modification des seules propriétés permises** : *s.o.*, l'API n'enregistre rien.
- **Validation des réponses par un schéma** : tenue. FastAPI valide chaque réponse contre le type
  de retour de sa route (`-> DigestsSchema`, `-> TrendReportSchema`).
- **Structures de données minimales** : tenue. `DigestsSchema` et `TrendReportSchema` ne portent
  que les champs du contrat (`ai_api/schemas/`).

### API4:2023 Unrestricted Resource Consumption

- **Limiter la mémoire, le CPU, les redémarrages, les descripteurs et les processus** : tenue pour
  la mémoire, le CPU et les répliques (#414) ; écart voulu, justifié, pour les redémarrages, les
  descripteurs et les processus.
  - La mémoire et le CPU sont tenus : chaque API a 0,5 vCPU et 1 Gi
    (`infra/modules/api-container-app.bicep:116-119`).
  - Les répliques aussi : `maxReplicas: 1` (« Accès »), et `minReplicas: 0`, décision de Sabine du 06/11
    (`api-container-app.bicep:149-152`). À 0, le compte du débit repart de zéro à chaque réveil.
    Pendant un déploiement, l'ancienne et la nouvelle révision tournent ensemble, deux répliques
    (journal ADR, 2026-11-06, « Mise en ligne »).
  - Les redémarrages, les descripteurs et les processus ne sont pas limités, et n'ont pas besoin de
    l'être. La mesure borne ce qu'un client fait consommer au serveur (« Use a solution that makes
    it easy to limit memory, CPU, number of restarts, file descriptors, and processes such as
    Containers / Serverless code (e.g. Lambdas). », API4:2023, lue le 2026-11-10). Aucun client ne fait lancer de processus : l'API n'en lance aucun
    (`grep -rlE "subprocess|multiprocessing|os\.fork|Popen" src/k_b/ai_api src/k_b/core` ne rend
    rien), et `uvicorn.run` reçoit l'app elle-même, sans `workers`
    (`commands/serve_ai_command.py:92`) : un seul processus, uvicorn 0.54 refusant plusieurs
    processus sans chaîne d'import. Les descripteurs suivent les connexions, qu'uvicorn tient avant
    tout contrôle de l'app : en ligne, seules les pièces de l'environnement se connectent (API2, TLS
    mutuel), et sur la machine, ses programmes. Un redémarrage vient d'un plantage (« If a container
    crashes, it automatically restarts. », page des conteneurs, lue le 2026-11-10), ou de la sonde
    Liveness (`infra/modules/api-container-app.bicep:138-143` ; « Checks if your application is
    still running and responsive. », page des sondes, lue le 2026-11-10), qu'une charge peut faire
    échouer : là encore, une charge venue des seules pièces de l'environnement. La page des
    conteneurs ne décrit aucune politique de redémarrage pour une app. Un redémarrage remet le débit
    à zéro, ce que borne le quota du modèle (« Plafonds de dépense », ci-dessous). Leur coût reste
    dans le 0,5 vCPU et le 1 Gi de la seule réplique.
    **Limite** : une entrée externe ou un client hors de l'environnement, qui ouvrirait des
    connexions sans fin ; un code de l'API qui lancerait des processus.
    **Pour réduire le risque** : garder l'entrée interne (API2, TLS mutuel) ; si un client du dehors
    devait la joindre, poser d'abord la limite de connexions d'uvicorn, `limit_concurrency`
    (« Maximum number of concurrent connections or tasks to allow, before issuing HTTP 503
    responses. », texte d'aide de `--limit-concurrency` d'uvicorn 0.54, lu le 2026-11-10), une
    décision ouverte du journal ADR.
- **Taille maximale de toutes les entrées** : tenue (#399). Corps de 1 024 octets au plus, refusé
  en 413 avant la clé (`MAX_AI_API_BODY_BYTES`) ; `window_days` de 1 à 14 ; `after` et
  `previous_first_window` au format `AAAA-MM-JJ`, sur 15 fenêtres au plus.
  `test_a_body_beyond_the_bound_is_refused_413_before_the_key`,
  `test_a_body_announced_beyond_the_bound_gets_the_413_of_k_b_on_any_route`,
  `test_a_length_starlette_reads_beyond_the_bound_gets_the_413_of_k_b`,
  `test_a_malformed_request_is_refused_422_on_its_body_before_any_reading` et
  `test_a_day_not_written_yyyy_mm_dd_is_refused_422_by_its_name`
  (`tests/ai_api/test_trend_report_router.py`).
- **Limite de débit** : tenue (#400), pour les clients à clé valide : 20 demandes par 24 h
  glissantes et par route. `test_beyond_its_limit_a_client_gets_429_before_any_reading`,
  `test_beyond_its_limit_the_client_of_the_reports_gets_429_without_a_reading`. Limites écrites
  (« Accès ») : le compte vit en mémoire, ce n'est pas un budget ; les essais sans clé valide ne
  sont pas comptés (API2).
- **Limite de débit ajustée par point d'accès** : tenue. Une limite par route, la même pour les
  deux : 20 par 24 h, tirée des demandes de fiches et reprise pour les comptes rendus
  (`AI_API_RATE_LIMITS`, `core/config.py`) ; `test_every_route_of_the_model_has_its_limit`.
- **Limiter une opération unique par client** : tenue. Une demande à la fois par route,
  `test_while_a_request_runs_the_next_one_on_its_route_gets_429_without_a_queue`.
- **Valider côté serveur le nombre d'enregistrements renvoyés** : tenue. Le client n'en fixe aucun ;
  le code plafonne la lecture (« Lecture plafonnée ») : `test_the_reading_is_capped_inside_a_kind`,
  `test_beyond_the_cap_the_most_recent_windows_are_kept`.
- **Plafonds de dépense ou alertes de facturation** : non tenue, mesure nécessaire non intégrée
  (#501 ; décision de Sabine du 2026-11-08 : la tenir). « Configure spending limits for all service
  providers/API integrations. When setting spending limits is not possible, billing alerts should be
  configured instead. » (API4:2023, lue le 2026-11-10). Le budget `budget-kb` existe, au niveau du
  groupe de ressources (`infra/modules/budget.bicep:5-25`, `infra/main.bicep:136-141`) : 30 € par mois,
  une alerte par e-mail à 50 et 100 % du réel et à 100 % de la prévision, sans rien arrêter. Il ne
  compte que les coûts étiquetés `project=k-b` (`budget.bicep:16-25`), et la ressource du modèle,
  dans le groupe, n'a pas d'étiquette (relevé de Sabine du 2026-11-08, #501) : la dépense du modèle
  n'y entre pas. Ce que bornent les limites, par demande : les jetons de sortie de chaque appel, une
  relance au plus, une échéance de 200 s, que le dernier appel en cours peut dépasser (« Lecture
  plafonnée », « Limite »), une réponse du modèle de 1 000 000 d'octets au plus (#399). Dans la vie
  d'une réplique, l'ordre de grandeur que permettent les limites de débit, au prix de sortie
  (0,60 $ par million de jetons, le plus cher) et sur les estimations de pire cas de la doc :
  20 demandes de fiches × 420 000 jetons (`README.md`), environ 5 $, et 20 comptes rendus × 80 000
  jetons ([tendances.md](tendances.md)), environ 1 $. En ligne, ce n'est pas un plafond par jour :
  avec `minReplicas: 0`, une réplique s'arrête 300 s après la dernière requête (« Cool down period
  is how long after the last event KEDA waits before the application scales down to its minimum
  replica count. », 300 secondes par défaut, page de la mise à l'échelle d'ACA, lue le 2026-11-10 ;
  `api-container-app.bicep:149-152` n'en règle pas d'autre), et la suivante repart d'un compte à
  zéro. Au pire, 20 demandes par route et par réveil, et jusqu'à 288 réveils par jour
  (86 400 s / 300 s) : 5 760 demandes par route, si chacune était instantanée. La borne qui reste est
  le quota du déploiement, 140 000 jetons par minute (`README.md`, « Budget ») : 201 600 000 jetons
  par jour, au plus environ 121 $ par jour au prix de sortie. Ce pire cas demande une clé et une
  pièce de l'environnement (API2, TLS mutuel) : une boucle de K-B qui attend l'arrêt à vide, ou une
  clé volée qu'une pièce détournée utilise.
  **Pour la tenir** : #501, une alerte Azure Monitor par e-mail sur les jetons du déploiement, et
  l'étiquette `project=k-b` sur la ressource du modèle, pour que `budget-kb` la compte. Une alerte
  n'arrête pas la consommation (« Resources aren't affected, and your consumption isn't stopped. »),
  et un budget n'est évalué que toutes les 24 h (« Cost and usage data is typically available within
  8-24 hours and budgets are evaluated against these costs every 24 hours. », page des budgets de
  Cost Management, lue le 2026-11-10). Un plafond qui refuse viendrait d'ailleurs : une politique de la passerelle d'API
  (API9), à vérifier ; ou un compte des jetons par jour tenu par K-B, qui devrait survivre au
  redémarrage, donc vivre hors des deux API (règle 7 de `.claude/rules/poc.md` : l'API IA n'écrit
  rien qui doive survivre à son redémarrage), dans un stockage à concevoir. Non chiffré.
  **Pour réduire le risque** : à ce commit, rien en ligne n'appelle le modèle, aucun job à clé ne
  tournant (API2, TLS mutuel) ; poser l'alerte de #501 avant le premier job à clé en ligne.

### API5:2023 Broken Function Level Authorization

- **Refus par défaut, droit explicite sur chaque fonction** : tenue (#400). La clé est exigée sur
  toute l'app ; chaque route du modèle s'ouvre à un client (`AI_API_CLIENT_BY_ROUTE`) ; une route
  absente de la table est refusée à tous. `test_a_client_is_refused_403_on_a_route_that_is_not_its_own`,
  `test_the_client_of_the_digests_is_refused_on_the_trend_reports`,
  `test_a_route_absent_from_the_table_is_refused_to_every_client`.
- **Revue des points d'accès** : tenue. Les routes et leurs méthodes sont figées par
  `test_only_the_public_routes_answer_without_a_key` (`tests/ai_api/test_digest_router.py`).
- **Contrôleurs et fonctions d'administration** : *s.o.*, aucun.

### API6:2023 Unrestricted Access to Sensitive Business Flows

- **Identifier les flux sensibles** : tenue. L'appel au modèle, payant (« Lecture plafonnée »).
- **Empreinte d'appareil, détection humaine, motifs non humains, blocage de Tor** : *s.o.*, ces
  mesures visent des clients humains ; l'API n'a que des clients programmes.
- **Sécuriser et limiter l'accès des API consommées par des machines** : tenue (#400). Une clé par
  client, un client par route, une demande à la fois, un débit par client ; écoute sur `127.0.0.1`
  par défaut (`test_serve_ai_listens_on_127_0_0_1_8001_by_default_with_the_real_subjects`) ; en
  ligne, une entrée interne, que seules les pièces de l'environnement atteignent (API2, TLS mutuel).
  **Limite** : en ligne, le débit repart de zéro à chaque réveil (`minReplicas: 0`,
  `infra/modules/api-container-app.bicep:149-152`) ; il arrête une boucle qui garde la réplique en
  vie, pas un client qui attend l'arrêt à vide (API4, « Plafonds de dépense »).
  **Pour réduire le risque** : celui d'API4, « Plafonds de dépense » (#501).

### API7:2023 Server Side Request Forgery

Aucune URL ne vient du client ni d'un tiers : les hôtes sont fixés par K-B ou par la
configuration ; le seul élément externe d'un chemin est le nom d'un dépôt, sous l'hôte de GitHub.

- **Isoler la récupération de ressources dans le réseau** : *s.o.*, aucune URL ne venant d'une
  requête ni d'un tiers (ci-dessus). En ligne, l'environnement n'a pas de réseau virtuel (aucun dans
  `infra/modules/container-apps-environment.bicep`, `publicNetworkAccess: 'Enabled'`, l. 45) : ses
  sorties ne sont pas filtrées, sans objet pour la même raison.
- **Listes d'origines et de schémas permis** : tenue. Hôte GitHub constant (`core/github_api.py`) ;
  `https` seul vers le modèle et vers l'export ; vers l'API de données, `https`, ou `http` vers la
  machine ou, en `sandbox`, vers un service du compose seulement (API10, #473).
  `core/outbound.py`, `test_a_url_of_an_allowed_scheme_is_accepted` et
  `test_a_url_refused_is_named_by_its_variable_never_quoted` (`tests/test_outbound.py`).
- **Redirections coupées** : tenue. Vers le modèle, l'API de données et GitHub,
  `follow_redirects=False` (`core/outbound.py`) :
  `test_the_client_of_the_provider_sends_the_key_and_follows_no_redirection`,
  `test_a_redirection_is_not_followed_and_leaves_the_candidate_out`. Vers l'export, le transport du
  SDK OpenTelemetry ne suit aucune redirection, mais compte un 3xx comme un succès
  (`ai_api/connectors/metrics_export.py`).
- **Analyseur d'URL éprouvé** : tenue. `urlsplit` de la bibliothèque standard, avec refus d'une
  identité, d'une requête ou d'un fragment (`core/outbound.py`,
  `test_a_url_refused_is_named_by_its_variable_never_quoted`).
- **Valider et assainir toute entrée du client** : tenue. Schémas stricts (API3) ; le nom de dépôt
  qui forme le chemin GitHub est contrôlé :
  `test_a_repository_whose_name_would_go_up_a_path_is_dropped_and_counted`.
- **Ne pas renvoyer de réponse brute** : tenue. Réponses reconstruites champ par champ
  (`ai_api/routers/`) ; une erreur de l'API de données ne cite ni la clé ni ce qui a été reçu
  (`test_the_error_carries_neither_the_key_nor_what_was_received`, sur une redirection qui porte la
  clé) ; une erreur du modèle ou de GitHub n'est rendue que par son état nommé (« États nommés »).

### API8:2023 Security Misconfiguration

Relue point par point le 2026-11-08 (#454), contre `infra/` et l'état en ligne ; une mesure qui ne
dépend que du code garde son état et sa preuve.

- **Durcissement répétable** : non tenue, en partie : mesure nécessaire non intégrée, risque accepté
  jusqu'à #496 (consigne de Sabine du 2026-11-09). L'image (`Dockerfile`, utilisateur 10001, #200),
  l'environnement, les apps et les jobs d'ACA (`infra/`, Bicep) sont versionnés et relus en PR comme
  le code ; la CI construit `infra/main.bicep` sur toute PR qui touche `infra/`
  (`.github/workflows/infra.yml:27`) ; une version taguée part en ligne par
  `.github/workflows/deploy.yml` (#415). Un réglage refusé empêche le démarrage
  (`test_serve_ai_exits_2_and_names_the_variable_refused`). Ce qui manque, en quatre limites : le
  socle s'applique à la main, en deux passes (`infra/README.md`) ; `deploy.yml` change l'image des
  apps et des jobs par `az containerapp update` et `az containerapp job update`, hors du Bicep
  (`deploy.yml:168`, `:174`) ; la construction du Bicep n'est pas un contrôle exigé de `main`
  (`infra.yml:15`) ; le ruleset de `main` n'exige aucune relecture (`required_approving_review_count`
  0), la relecture en PR est une pratique, pas une règle.
  **Pour la tenir** : la construction du Bicep exigée, sans bloquer les PR qui ne touchent pas
  `infra/` (un job toujours lancé, qui saute la construction hors de `infra/`, #496), et une
  relecture exigée par le ruleset dès qu'une seconde personne peut relire. S.
  **Pour réduire le risque** : d'ici #496, ne fusionner une PR qui touche `infra/` que sur sa
  construction du Bicep verte (`infra.yml:27`) ; après une passe à la main ou une version, relire la
  configuration en ligne (« Revue périodique », ci-dessous).
- **Revue périodique des configurations de toute la pile** : non tenue, en partie : mesure
  nécessaire non intégrée (#497). Chaque changement
  de `infra/` est relu en PR ; la configuration en ligne n'a été relue contre ces fichiers qu'une
  fois, à la main, le 2026-11-08 (#454), pour l'entrée, le chiffrement entre apps et les URL
  internes (« TLS, même pour une API interne », ci-dessous).
  **Pour la tenir** : à chaque déploiement, relire la configuration déployée contre ces fichiers et
  contre cette section (#497). XS par revue.
  **Pour réduire le risque** : d'ici #497, relancer à chaque version les commandes de « TLS, même
  pour une API interne » (ci-dessous), en lecture seule.
- **Évaluation automatisée et continue dans tous les environnements** : non tenue, en partie :
  mesure nécessaire non intégrée (#498, #499). La CI
  lance `pip-audit`, les règles de sécurité de ruff, les tests et leur seuil de couverture
  (`.github/workflows/ci.yml`), et la construction du Bicep (`infra.yml`). Après chaque
  déploiement, `deploy.yml` lance `caj-kb-smoke-test` (l. 204-209), qui demande `GET /health` aux
  deux API (`src/k_b/jobs/api_health.py`) et atteint le stockage d'échange par l'identité du job :
  il vérifie que la version déployée répond, pas sa sécurité.
  **Pour la tenir** : un scan de l'image dans la CI (l'outil, une dépendance de la CI, est à
  choisir, #498), et des essais scriptés des points de cette section, lancés par la CI après chaque
  déploiement, avec une clé de test à prévoir (#499 : des sondes sans clé). M.
  **Pour réduire le risque** : `pip-audit` audite déjà chaque version de `uv.lock`, uvicorn et h11
  compris (`.github/workflows/ci.yml:23-25`) ; restent sans contrôle les paquets Debian de l'image
  (#498).
- **TLS, même pour une API interne** : tenue en ligne ; sur la machine, l'API IA sert en `http` sur
  `127.0.0.1`, joignable de la machine seule.
  - Les deux API n'ont qu'une entrée interne, en HTTPS (`external: false`, `allowInsecure: false`,
    `infra/modules/api-container-app.bicep:74-80`) : « Internal: Makes the app's own fully qualified
    domain name (FQDN) directly reachable only from within the same Container Apps environment, such
    as from other container apps. » (page de l'entrée, relue le 2026-11-10). La documentation de l'entrée nomme une seule exception, une route
    HTTP de l'environnement qui viserait l'app : il n'y en a aucune. L'entrée interne coupe aussi les
    clients `TERMINAL` et `AGENT` de l'API de données, hors de l'environnement. Le point public de
    l'environnement reste ouvert (`publicNetworkAccess: 'Enabled'`,
    `infra/modules/container-apps-environment.bicep:45`, la valeur `Disabled` demandant un réseau
    virtuel) : une requête du dehors atteint son mandataire, qui n'expose pas l'app (« The app isn't
    exposed through the Container Apps environment's inbound IP address », page de l'entrée, relue
    le 2026-11-10) ; la documentation donne le 404 pour un environnement interne, le commentaire du
    Bicep pour celui-ci ; non essayé.
  - Le chiffrement entre apps est activé (`peerTrafficConfiguration.encryption.enabled`,
    `infra/modules/container-apps-environment.bicep:32-36`) : « Traffic to and from the ingress proxy
    within the environment is TLS encrypted with a private certificate and decrypted by the
    receiver. » (relue le 2026-11-10). Le réseau est donc
    chiffré jusqu'à la réplique ; uvicorn y reçoit `http` sur son port (`transport: 'http'`, aucun
    TLS dans uvicorn), et ce dernier pas, dans la réplique, n'est ni décrit par la documentation ni
    essayé. mTLS reste désactivé (l. 38-42).
  - Les clients : l'API IA appelle l'API de données en `https://ca-kb-data-api.internal.<defaultDomain>`
    (`infra/main.bicep:241`), le seul hôte que l'API de données accepte (`KB_DATA_API_ALLOWED_HOSTS`,
    l. 205) ; le test de fumée appelle les deux API en `https` (l. 266-267) ; l'API de données lit
    PostgreSQL en `sslmode=verify-full` (l. 279) ; `https` vers le modèle, GitHub et l'export.
  - Relu en ligne le 2026-11-08, pour `ca-kb-ai-api` et `ca-kb-data-api`, puis pour l'environnement :

    ```sh
    az containerapp show -n <app> -g <groupe> \
      --query "properties.configuration.ingress.{external:external, allowInsecure:allowInsecure, transport:transport, customDomains:customDomains}"
    az containerapp env show -n <environnement> -g <groupe> \
      --query "{encryption: properties.peerTrafficConfiguration.encryption.enabled, mtls: properties.peerAuthentication.mtls.enabled}"
    az containerapp env http-route-config list -n <environnement> -g <groupe>
    az containerapp show -n <app> -g <groupe> \
      --query "properties.template.containers[0].env[?name=='KB_DATA_API_URL' || name=='KB_DATA_API_ALLOWED_HOSTS'].{name:name, value:value}"
    ```

    `external` false, `allowInsecure` false, `transport` Http et `customDomains` null (aucun domaine
    personnalisé) pour les deux apps ; `encryption` true, `mtls` false ; aucune route (`[]`) ; sur
    `ca-kb-ai-api`, `KB_DATA_API_URL` =
    `https://ca-kb-data-api.internal.<defaultDomain>`, sur `ca-kb-data-api`,
    `KB_DATA_API_ALLOWED_HOSTS` = `ca-kb-data-api.internal.<defaultDomain>`.
  - Le code force aussi le `https` (#473) : une URL d'API interne en `http` n'est acceptée que vers
    `127.0.0.1` ou `localhost`, ou, avec `KB_DEPLOYMENT_ENVIRONMENT=sandbox`, vers `api-donnees` ou
    `api-ia`, les services d'un compose (#419) ; sinon le démarrage est refusé (code 2), le message
    nommant la variable (`find_internal_api_url_refusal`, `core/outbound.py` ; `LOCAL_HOSTS` et
    `COMPOSE_HOSTS`, `core/config.py`), pour `KB_DATA_API_URL` (API IA) et `KB_AI_API_URL`
    (`kb digest`, `kb trend-report`), et pour les deux URL de `kb smoke-test` et `kb digest-watch`.
    `test_an_internal_api_url_in_http_elsewhere_is_refused` (un nom public, une IPv4 en un nombre,
    un service mal écrit, en `sandbox` compris), `test_serve_ai_exits_2_and_names_the_variable_refused`
    (`data-api-in-http-outside-the-machine`).
  - Non essayé, l'entrée n'étant joignable que de l'environnement : la version de TLS, « always use
    TLS 1.2 or 1.3 » selon la documentation de l'entrée (lue le 2026-11-08). Côté client, K-B ne
    règle pas la version de TLS : les bibliothèques gardent leur contexte par défaut, TLS 1.2 au
    moins, httpx2 2.13.1 pour `core/outbound.py` et urllib3 de `requests` pour l'export (lu le
    2026-11-05). L'échange de clés post-quantique (`X25519MLKEM768`, ML-KEM, FIPS 203) est documenté
    pour Azure Front Door, du client à Front Door seulement, pas pour l'entrée d'ACA.
- **N'accepter que les verbes HTTP nécessaires** : tenue (#401). Chaque route n'accepte que sa
  méthode ; `HEAD`, que Starlette ajoute à toute route `GET`, est retiré ; toute autre méthode
  rend 405 `method_not_allowed`. `test_every_route_answers_its_method_only_and_405_to_any_other`.
  Écart à la RFC 9110 (§ 9.1), qui demande à tout serveur généraliste d'accepter `GET` et `HEAD` :
  la même section laisse chaque ressource décider des méthodes qu'elle permet, et les clients de
  l'API, connus, n'envoient jamais `HEAD`. Une méthode inconnue (`FOO`) rend 405, là où la RFC
  recommande 501 ; `OPTIONS *` et `CONNECT hôte:port` rendent 404 (essayé le 2026-11-05).
  **Pour lever l'écart**, s'il est levé : 501 pour une méthode qui n'est pas dans la RFC 9110,
  405 pour les autres. S.
- **CORS et en-têtes de sécurité des clients en navigateur** : *s.o.*, aucun client en navigateur
  et aucun `CORSMiddleware` : un navigateur d'une autre origine ne peut pas lire une réponse. Seule
  `/docs`, en `sandbox`, est une page.
- **Restreindre les types de contenu entrants** : tenue. Seul un corps JSON est lu ; un autre type
  rend 422 `invalid_parameter` `["body"]` (essayé le 2026-11-05 avec `text/plain`, sans test). La
  RFC 9110 donnerait 415 : écart voulu, un seul état pour tout corps refusé.
  **Pour lever l'écart**, s'il est levé : 415 pour un corps qui n'est pas `application/json`,
  avant sa lecture, et un test. S.
- **Traitement uniforme dans la chaîne de serveurs** : non essayé, écart voulu, justifié. En ligne,
  deux serveurs : l'entrée d'ACA (Envoy), puis uvicorn 0.54 et h11 0.16 (`uv.lock` de `v0.1.0`,
  les mêmes dans celui de `v0.1.1`) (`transport: 'http'`, `infra/modules/api-container-app.bicep:77`).
  Aucune requête ambiguë, comme `Content-Length` et `Transfer-Encoding` ensemble, n'a été envoyée. L'essai
  n'est pas nécessaire : une désynchronisation demande un client qui envoie au premier serveur une
  requête que le second lira autrement (« Ensure all servers in the HTTP server chain (e.g. load
  balancers, reverse and forward proxies, and back-end servers) process incoming requests in a
  uniform manner to avoid desync issues. », API8:2023, lue le 2026-11-10), et
  l'API IA n'a aucun client tiers. L'adresse entrante de l'environnement n'expose pas l'app (« The
  app isn't exposed through the Container Apps environment's inbound IP address », page de l'entrée,
  lue le 2026-11-10), aucune route HTTP ne la vise (« TLS, même pour une API interne », ci-dessus),
  et l'environnement ne sert que K-B : seules ses pièces atteignent l'entrée interne (API2, TLS
  mutuel).
  **Limite** : une entrée externe, un client tiers dans l'environnement, ou un mandataire de plus
  devant l'app.
  **Pour réduire le risque** : garder l'entrée interne (API2, TLS mutuel) ; `pip-audit` signale une
  vulnérabilité connue d'uvicorn ou de h11 dans la CI (`.github/workflows/ci.yml:23-25`).
  **Pour la tenir**, si la limite est franchie : depuis un job de l'environnement, envoyer les
  requêtes ambiguës d'une désynchronisation, et vérifier qu'Envoy les refuse ou que les deux serveurs
  les lisent de même. S.
- **Schémas de réponse, erreurs comprises, sans trace d'exception** : tenue. Corps `{"error":
  "<état>"}` (« États nommés » ; les états `github_*` dans [tendances.md](tendances.md), « Défenses
  et échecs ») ; une erreur imprévue donne 500 `internal_error`, son type seul au journal.
  `test_a_response_that_fails_to_be_built_is_traced_as_a_500` (le corps),
  `test_an_unexpected_error_gives_500_internal_error_and_logs_its_type_only`
  (`tests/data_api/test_api_errors.py`, le même middleware, la ligne de journal),
  `test_an_unexpected_error_names_its_type_never_its_text_on_the_root` (la trace),
  `test_the_route_documents_each_named_state`. Limites :
  - une requête HTTP mal formée reçoit le 400 d'uvicorn en texte brut, `Invalid HTTP request
    received.`, avant l'app (uvicorn 0.54, h11 0.16, essayé le 2026-11-05) ;
  - un JSON illisible ou hors UTF-8 rend 422, là où la RFC 9110 donnerait 400 : même choix d'un
    seul état ;
  - le budget de 70 requêtes à GitHub épuisé rend 502 `github_unavailable`, alors que la limite est
    celle de K-B, pas une panne de GitHub.

  **Pour lever ces écarts**, s'ils sont levés : en ligne, une requête mal formée passe d'abord
  par Envoy, et ce qu'il en fait n'est pas essayé (même essai que la chaîne de serveurs, ci-dessus) ; un 400
  nommé pour un corps illisible, distinct du 422 de schéma (S) ; un 503 et un état nommé pour le
  budget GitHub épuisé (XS).

Hors de la grille : pas de `TrustedHostMiddleware`, écart voulu et justifié dans « Accès ».

### API9:2023 Improper Inventory Management

- **Inventaire des hôtes** : tenue. `127.0.0.1:8001` par défaut, version `0.12.0` (« Accès »),
  environnements `sandbox` et `production` (`core/api_settings.py`).
- **Inventaire des services intégrés** : tenue. Le modèle, GitHub et Grafana Cloud, avec les
  données échangées ([registre-traitements.md](registre-traitements.md)) ; l'API de données
  (« Lecture plafonnée »).
- **Documenter l'authentification, les erreurs, les redirections, la limite de débit, CORS et les
  points d'accès** : tenue. Accès et débit (« Accès »), erreurs (« États nommés » ;
  [tendances.md](tendances.md), « Défenses et échecs »), routes (`docs/api/openapi-ia.json`),
  redirections sortantes ([tendances.md](tendances.md)), CORS (API8 ci-dessus : aucun).
- **Documentation générée depuis un standard, dans la CI** : tenue. `kb openapi` écrit
  `docs/api/openapi-ia.json` ; `test_the_versioned_openapi_is_the_one_the_app_produces`
  (`tests/ai_api/test_ai_api_openapi.py`).
- **Documentation réservée aux utilisateurs autorisés** : tenue hors `sandbox` ; en `sandbox`, écart
  voulu, justifié. Hors
  `sandbox`, `/docs` et `/openapi.json` rendent 404 (`test_the_documentation_is_served_in_the_sandbox_only`,
  `tests/ai_api/test_serve_ai.py`) ; en `sandbox`, ils répondent sans clé, sans aucune donnée. En
  ligne, l'API IA (`ca-kb-ai-api`) est déployée avec `KB_DEPLOYMENT_ENVIRONMENT` à `production`
  (`infra/main.bicep:234`, non relu en ligne) : l'écart ne vaut qu'en local, quand la variable vaut
  `sandbox`. Le contrat est versionné dans le dépôt, privé au 2026-11-10 et appelé à devenir
  public : s'il l'est, fermer `/docs` ne cacherait pas le contrat. La mesure n'est donc pas
  nécessaire en `sandbox` : ce que `/docs` y sert, le contrat sans aucune donnée, sur `127.0.0.1`,
  ne demande pas d'être autorisé.
  **Limite** : une `sandbox` servie au-delà de `127.0.0.1`, ou un `/docs` qui porterait des
  données.
  **Pour réduire le risque** : `production` en ligne (`infra/main.bicep:234`) ; l'écoute par
  défaut sur `127.0.0.1` (`test_serve_ai_listens_on_127_0_0_1_8001_by_default_with_the_real_subjects`).
  **Pour la tenir**, si l'écart est levé : ne plus servir `/docs` ni `/openapi.json`, même en
  `sandbox` ; le contrat reste dans le dépôt (`kb openapi`). `read_openapi_url`
  (`core/api_settings.py`) vaut pour les deux API : l'API de données fermerait son `/docs` aussi.
  Le coût : plus d'essai dans le navigateur. XS.
- **Protections externes pour toutes les versions exposées** : non appliquée, écart voulu,
  justifié. Aucune solution de sécurité d'API devant l'app. « Use external protection measures such
  as API security specific solutions for all exposed versions of your APIs, not just for the current
  production version. » (API9:2023, lue le 2026-11-10) : la mesure vaut pour chaque version, celle
  de production comprise. Elle n'est pas nécessaire : une solution de sécurité d'API filtre le
  trafic du dehors, et aucun n'atteint l'API IA. Une seule version tourne (`activeRevisionsMode:
  'Single'`, `infra/modules/api-container-app.bicep:73`), derrière une entrée interne que l'adresse
  entrante de l'environnement n'expose pas (API8, « Traitement uniforme dans la chaîne de
  serveurs ») ; ses seuls clients sont les pièces de l'environnement, qui ne servent que K-B.
  **Limite** : une entrée externe, un client hors de l'environnement, ou plusieurs révisions
  actives.
  **Pour réduire le risque** : relire à chaque version l'entrée, les routes de l'environnement et
  `activeRevisionsMode` (#497) ; garder l'entrée interne (API2, TLS mutuel).
  **Pour la tenir**, si la limite est franchie, l'une de ces voies ; non chiffré, la taille dépend de
  la voie :
  - des restrictions d'adresses sur l'entrée d'ACA (`ipSecurityRestrictions`, toutes en `Allow` ou
    toutes en `Deny`) : utiles seulement si les clients ont des adresses fixes ;
  - Azure API Management devant l'app, avec ses politiques (limite de débit) ;
  - Application Gateway avec son WAF, devant un environnement interne dans un réseau virtuel ;
  - Front Door Premium avec son WAF, par Private Link, sur un environnement « workload profiles ».
- **Pas de données de production hors production** : tenue. La production tourne en ligne depuis
  `v0.1.0` (tag du 2026-11-08). Hors production, les deux API tournent sur la machine de Sabine, sur
  une base que `kb collect` et `kb import` remplissent des mêmes sources (`README.md`, « Le POC du
  25/10 et la suite ») : des données de la même sorte. La mesure demande alors le même traitement
  que la production (« If this is unavoidable, these endpoints should get the same security
  treatment as the production ones », API9:2023, lue le 2026-11-10), et la machine le leur donne :
  le même code (`create_app`, `ai_api/app.py:41`, `data_api/app.py:34`), une clé exigée par client
  et refusée au démarrage si elle manque à la règle, les mêmes limites. Deux différences, sans
  donnée : `http` sur `127.0.0.1`, joignable de la machine seule (API8, « TLS, même pour une API
  interne ») ; `/docs` et `/openapi.json` sans clé quand `KB_DEPLOYMENT_ENVIRONMENT` vaut `sandbox`
  (« Documentation réservée aux utilisateurs autorisés »).
  **Limite** : une base de la machine servie au-delà de `127.0.0.1`.
  **Pour réduire le risque** : garder les hôtes d'écoute par défaut, `127.0.0.1`
  (`test_serve_ai_listens_on_127_0_0_1_8001_by_default_with_the_real_subjects`,
  `test_serve_listens_on_127_0_0_1_8000_by_default_without_uvicorn_logging_config`).
- **Analyse de risque des anciennes versions** : *s.o.*, une seule version servie.

### API10:2023 Unsafe Consumption of APIs

L'API IA consomme le modèle, l'API de données, GitHub et l'export OTLP vers Grafana Cloud. Relue
point par point le 2026-11-08 (#454) : seul le TLS vers l'API de données change.

- **Évaluer la sécurité des fournisseurs** : tenue sur pièces publiques, le 2026-11-05, sur les
  pages officielles de chacun, sauf la portée du jeton de Grafana Cloud : non tenue (ci-dessous). Azure publie sa version de TLS pour l'ensemble des « Foundry
  Tools », GitHub par le retrait de TLS 1.0 et 1.1, Grafana pas ; aucun pour le point d'accès
  précis qu'appelle K-B. Le client de K-B accepte TLS 1.2 au moins, par défaut de ses
  bibliothèques (API8).

  | Fournisseur | Transport | Accès de K-B, moindre privilège | Certifications publiées | Vulnérabilités | Limite |
  |---|---|---|---|---|---|
  | Modèle, Azure AI Foundry (France Central, Data Zone UE) | TLS 1.2 ou 1.3 sur les points d'accès « Foundry Tools » | Clé d'API, la méthode « la plus simple mais pas la plus sûre » selon Microsoft ; deux clés pour la rotation, une clé régénérée cesse aussitôt de marcher ; le moindre privilège passe par Entra ID et un rôle d'inférence, non utilisé par K-B | SOC 2 Type 2, ISO/IEC 27001:2022 (Azure) | Microsoft Azure Bounty | Invites et réponses ni données à OpenAI ni utilisées pour l'entraînement ; traitées dans l'UE ; surveillance des abus possible, durée de conservation non trouvée |
  | API REST de GitHub | TLS 1.0 et 1.1 retirés en 2018 ; SHA-1 retiré de HTTPS au 15/09/2026 | Jeton *fine-grained* en lecture seule ([jeton-github.md](jeton-github.md)) ; expiration de 1 à 366 jours | SOC 1 et SOC 2 Type 2, ISO/IEC 27001:2022, CSA STAR | GitHub Security Bug Bounty (HackerOne) | Le produit couvert par chaque rapport n'est pas dit |
  | Grafana Cloud, export OTLP | Version de TLS non publiée | Jeton de politique d'accès aux seuls `metrics:write`, `traces:write`, `logs:write` ([registre-traitements.md](registre-traitements.md)), comme la page des politiques d'accès le recommande ; portée non tenue : le 2026-10-27, la politique recréée couvrait toute l'organisation (même registre), et le passage à l'offre gratuite du 08/11 a supprimé les politiques, si bien que le jeton de production ne vaut plus rien (#522) | ISO 27001, SOC 2 Type 2 (A-LIGN), CSA STAR | Divulgation sur Intigriti, sans prime | K-B ne relit rien de ce qu'il envoie |
  | API de données de K-B | `https` en ligne, par l'entrée interne et le chiffrement entre apps (API8, relu le 2026-11-08) ; `http` sur la machine | Clé `AI_DIGEST`, lecture seule | — | — | Son auto-évaluation : [specs-api.md](specs-api.md) |

  Ce n'est pas un audit : les rapports SOC 2 et ISO sont derrière une connexion chez Microsoft et
  GitHub, et n'ont pas été lus ; la liste des services Azure couverts par ces audits n'a pas été
  lue.

  **Pour la tenir**, pour Grafana Cloud : #522, une politique `kb-production` aux trois droits, sur
  la seule pile de K-B, et son jeton, avec une date d'expiration ; puis la portée relevée par
  Sabine, datée. XS.
  **Pour réduire le risque** : d'ici #522, la production n'envoie rien à Grafana Cloud, son jeton ne
  valant plus rien (#522, constat de time-knight du 2026-11-08) ; `KB_TRACE_CONTENT` vaut `none` en
  ligne (`infra/main.bicep:235`), si bien qu'aucun contenu d'appel au modèle n'y part.
- **TLS avec toutes les API intégrées** : tenue en ligne. `https` seul vers le modèle, GitHub et
  l'export (API7) ; vers l'API de données, `https://ca-kb-data-api.internal.<defaultDomain>`
  (`infra/main.bicep:241`), avec le chiffrement entre apps (API8, « TLS, même pour une API
  interne »). `http` n'est permis vers l'API de données que vers `127.0.0.1` ou `localhost`, ou, en
  `sandbox`, vers un service du compose (#419) : `find_internal_api_url_refusal` (`core/outbound.py`,
  #473).
- **Valider et assainir les données reçues** : tenue. Modèles Pydantic stricts pour chaque réponse ;
  corps bornés, la réponse du modèle comprise (#399,
  `test_an_answer_above_the_bound_is_llm_unavailable_without_retry`) ; textes de dépôt nettoyés
  avant le modèle ; sortie du modèle contrôlée (« Contrôles », « Injection d'instructions »).
- **Liste des redirections permises, pas de suivi aveugle** : tenue, plus strict : aucune
  redirection n'est suivie (API7).

### Sources de l'auto-évaluation

Lues le 2026-11-05. Relues le 2026-11-08 (#454) : l'entrée et le chiffrement entre apps d'ACA,
pour API8 et API10. Relues le 2026-11-10 (#500), pour les justifications et les « Pour réduire le
risque » : API4, API8 et API9 de l'édition 2023, la page du projet OWASP (édition en vigueur),
l'entrée, le chiffrement entre apps, les certificats clients, les conteneurs, les sondes et la mise
à l'échelle d'ACA, les budgets de Cost Management, les réglages d'uvicorn.

- [OWASP API Security Top 10, édition 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/),
  section « How To Prevent » de chaque entrée ; [API2:2023](https://api-security.owasp.org/editions/2023/en/0xa2-broken-authentication) ;
  [page du projet](https://owasp.org/www-project-api-security/) (« Latest Version » : 2023) et
  [notes de version de 2023](https://api-security.owasp.org/editions/2023/en/0x04-release-notes/)
  (la seconde édition, après celle de 2019).
- [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
  et [REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), OWASP.
- [NIST IR 8547](https://nvlpubs.nist.gov/nistpubs/ir/2026/NIST.IR.8547.pdf) (tableau 1, §2.1.3),
  [NIST IR 8105](https://nvlpubs.nist.gov/nistpubs/ir/2016/NIST.IR.8105.pdf),
  [FIPS 203](https://csrc.nist.gov/pubs/fips/203/final).
- RFC 9110, § 9.1, § 15.5.16, § 15.5.1 et § 15.6.2 ([httpwg.org](https://httpwg.org/specs/rfc9110.html)).
- Azure : [sécurité des Foundry Tools](https://learn.microsoft.com/en-us/azure/ai-services/security-features),
  [rotation des clés](https://learn.microsoft.com/en-us/azure/ai-services/rotate-keys),
  [données et confidentialité](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy),
  [SOC 2](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-soc-2),
  [ISO/IEC 27001](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-iso-27001),
  [Microsoft Azure Bounty](https://www.microsoft.com/en-us/msrc/bounty-microsoft-azure).
- GitHub : [jetons personnels](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens),
  [TLS 1.0 et 1.1 retirés](https://github.blog/2018-02-23-weak-cryptographic-standards-removed/),
  [SHA-1 retiré de HTTPS](https://github.blog/changelog/2026-04-20-sunsetting-sha-1-in-https-on-github/),
  [rapports de conformité](https://docs.github.com/en/enterprise-cloud@latest/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/accessing-compliance-reports-for-your-organization),
  [bug bounty](https://bounty.github.com).
- Grafana Cloud : [politiques d'accès](https://grafana.com/docs/grafana-cloud/security-and-account-management/authentication-and-permissions/access-policies/),
  [conformité](https://grafana.com/legal/security-compliance/),
  [signaler une vulnérabilité](https://grafana.com/legal/report-a-security-issue/).
- Azure Container Apps : [conteneurs](https://learn.microsoft.com/en-us/azure/container-apps/containers),
  [sondes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes),
  [mise à l'échelle](https://learn.microsoft.com/en-us/azure/container-apps/scale-app),
  [entrée](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview),
  [chiffrement entre apps](https://learn.microsoft.com/en-us/azure/container-apps/ingress-environment-configuration),
  [restrictions d'adresses](https://learn.microsoft.com/en-us/azure/container-apps/ip-restrictions),
  [certificats clients](https://learn.microsoft.com/en-us/azure/container-apps/client-certificate-authorization),
  [Application Gateway et WAF](https://learn.microsoft.com/en-us/azure/container-apps/waf-app-gateway),
  [Front Door](https://learn.microsoft.com/en-us/azure/container-apps/how-to-integrate-with-azure-front-door) ;
  [échange de clés de Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/tls-key-exchange-policy) ;
  [API Management](https://learn.microsoft.com/en-us/azure/api-management/import-container-app-with-oas) ;
  [budgets de Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).
- uvicorn 0.54 : le texte d'aide de `--limit-concurrency`, dans le code installé
  (`uvicorn/main.py`).

## Ce que la spec ne couvre pas

Ce qu'un produit fini demanderait de plus ; rien n'est décidé ici.

- La **vérification du sens** de chaque affirmation, que la fidélité ne fait pas (« Ce qu'elle ne
  vérifie pas »), est hors du contrat depuis le 2026-10-20 (journal ADR, « Squelette E1 E3 :
  cadrage du 20/10 », décision 2). Le contrat retiré du LLM juge : section « Juge » de
  `git show 4bb57c7:docs/fiches-veille.md` ; son code (#223) et son étalonnage (#224) restent
  ouverts.
- La **complétude vérifiée par un modèle** : un point important d'un item cité que la fiche
  oublierait.
- La **correction du français et du style**.
- Le **lint périodique de l'ensemble des fiches** : contradictions entre fiches, péremption.

## Métriques

Une ligne JSON par appel au modèle, sur la sortie standard, sans fichier (règle 4 de `poc.md`).
Un **appel** est un classement ou la rédaction d'un sujet, nouvelle tentative
comprise : jetons et durées sont cumulés sur la ligne.
Les lignes d'une demande sont écrites quand ses appels sont finis, classement en échec compris,
dans l'ordre des appels, chacune vidée aussitôt (`ai_api/observability/metrics.py`) : sur SIGTERM, uvicorn
renvoie le signal, et une ligne restée dans le tampon d'un tube serait perdue. `ts` est donc
l'heure d'écriture, pas celle de l'appel. Un champ « nul » vaut `null` en JSON.

**Limites** (revue de code de #156, tranchées par time-knight, délégation de Sabine du
2026-10-15) : une demande sans appel au modèle (fenêtre vide, ou échéance passée pendant la
lecture, 504 `llm_timeout`) n'écrit aucune ligne, si bien que ses `data_fetch_ms`,
`items_dropped_before_writing_stage` et `items_capped` ne sont nulle part : une ligne de mesures de la demande se
conçoit avec les métriques de #162. Une exception imprévue pendant la rédaction (500
`internal_error`, journalisé avec son `request_id`) perd les lignes des appels déjà faits : elles
ne sont écrites qu'au retour du parcours.

| Champ | Contenu |
|---|---|
| `ts` | date de la ligne, ISO 8601 UTC à la seconde (`2026-10-15T09:00:00Z`, règle 3 de `conventions.md`) |
| `event` | `llm_call` |
| `request_id` | celui de la réponse |
| `stage` | `classify` ou `write` ; `select` pour le choix d'un compte rendu des tendances ([tendances.md](tendances.md), « Ce que rend #368 »), `write_trends` pour la rédaction des textes d'un dépôt choisi (« Ce que rend #369 ») |
| `subject` | le sujet rédigé ; nul au classement |
| `provider`, `model` | lus dans la configuration (#150) |
| `prompt_version` | constante de la consigne utilisée (`classify-2`, `write-1`), changée à la main avec elle |
| `items_in` | items envoyés dans l'appel |
| `items_truncated` | items de cet appel dont un champ est coupé |
| `items_dropped_before_writing_stage`, `items_capped` | compteurs de la demande (section « Entrée du modèle ») ; sur la première ligne de classement de la demande, nuls ailleurs |
| `input_chars` | longueur du message utilisateur |
| `tokens_in`, `tokens_out` | `usage` rendu par le fournisseur |
| `reasoning_tokens` | jetons de raisonnement rendus par le fournisseur, attendus à 0 avec `reasoning_effort: "none"` ; nul s'il ne les rend pas |
| `data_fetch_ms` | durée de la lecture par l'API de données ; sur la première ligne de classement de la demande, nul ailleurs |
| `llm_ms`, `check_ms` | durée des appels au modèle, nouvelle tentative et attente avant elle comprises ; durée des contrôles 1 à 6 (la fidélité tourne après l'appel, hors de cette durée) |
| `attempts` | 1 ou 2 |
| `outcome` | `ok`, ou l'état `llm_*` de l'appel |
| `finish_reason` | celui de la dernière tentative, coupé à 64 caractères ; nul s'il manque |
| `http_status` | le statut HTTP de la dernière réponse du fournisseur (un 401 de clé refusée se distingue ainsi d'un 503) ; nul sans réponse (délai, connexion refusée) |
| `schema_valid` | la dernière tentative a passé le contrôle 2 |
| `failed_check` | le contrôle qui a refusé la dernière tentative (`content_filter`, `finish_reason`, `schema`, `subject`, `item_id`, `completeness`, `markup`, et `criterion` pour le choix des tendances) ; nul si `ok` |
| `first_failed_check` | le contrôle qui a refusé la première tentative, quand une seconde a suivi ; nul sinon (#205, `LlmCall`, constat de #158 : le motif de la première tentative était perdu) |
| `facts_checked`, `facts_found` | compteurs de la fidélité (rédaction, section « Fidélité », « Ce qui est compté ») ; nuls au classement et pour une rédaction en échec |
| `facts_found_in_item`, `facts_found_in_text` | les faits trouvés dans l'item qu'ils citent, et ceux trouvés dans le `text` de leur affirmation, chacun sans regarder l'autre (section « Fidélité », « Les deux moitiés du fait trouvé ») ; nuls au classement, pour une rédaction en échec, et sur les lignes d'un compte rendu des tendances |
| `fidelity_rate` | `facts_found` / `facts_checked`, arrondi à 4 décimales ; nul au classement, pour une rédaction en échec, et quand `facts_checked` vaut 0 |
| `claims_removed`, `items_removed_by_checks` | compteurs des contrôles, bornes ou fidélité (rédaction) ; nuls au classement |
| `items_with_subject`, `items_no_suitable_subject`, `items_unanswered` | compteurs du classement (section « Sortie du classement », « Trois cas ») : les items du lot qui ont reçu un sujet, ceux auxquels aucun sujet ne convient, et ceux que le modèle a laissés sans réponse, `items_in` à eux trois ; nuls à la rédaction, et pour un classement en échec |
| `cost_estimated` | en USD, arrondi à 6 décimales : `tokens_in` et `tokens_out` × prix au million de `core/config.py` (gpt-6-luna, Data Zone Standard, France Central, contexte court : 0,12 et 0,60) ; 0 en offre gratuite. **Limite** : tout appel est compté à ces prix, le replay compris (ses jetons sont ceux de ses pas, `provider` le dit) et un autre `KB_LLM_MODEL` aussi |

`ts`, `stage`, `failed_check`, `items_dropped`, `items_capped`, `reasoning_tokens` et `http_status`
s'ajoutent à la liste de #156, puis `first_failed_check` (#205), puis `fidelity_rate` (#207), puis
`items_with_subject`, `items_no_suitable_subject` et `items_unanswered` (`classify-2`, #210), puis
`facts_found_in_item` et `facts_found_in_text` (#518). En
0.4.0, `items_dropped` devient `items_dropped_before_writing_stage` et `items_uncited`,
`items_removed_by_checks`.

**Jamais** dans une ligne : le texte d'un item ou d'une affirmation, la consigne, la sortie du
modèle, un titre, un auteur, une clé (règle 5 de `poc.md`). Un échec `data_api_*` ne fait aucun appel au modèle, donc
aucune ligne `llm_call` : il va au log de fonctionnement (sortie d'erreur), avec le
`request_id`.

### Les mêmes mesures en OpenTelemetry (#162)

Les mesures de chaque appel partent aussi en métriques OpenTelemetry, exportées en OTLP (HTTP,
protobuf, gzip) vers Grafana Cloud, en région UE (journal ADR, 2026-10-20, « Squelette E1 E3 »,
décision 4). La ligne JSON reste : l'export s'y ajoute. Le code est dans
`ai_api/observability/metric_instruments.py` (les instruments, `ModelMetrics`) et
`ai_api/connectors/metrics_export.py` (les réglages, le fournisseur de mesures) ; OpenTelemetry
n'est importé nulle part ailleurs (`tests/architecture/test_opentelemetry.py`).

| Instrument | Type, unité | Valeur | Attributs propres |
|---|---|---|---|
| `gen_ai.client.inference.duration` | Histogram, `s` | `llm_ms` / 1000 | `error.type` = `outcome` hors `ok` |
| `gen_ai.client.inference.usage.input_tokens` | Counter, `{token}` | `tokens_in` | `gen_ai.token.modality = text` |
| `gen_ai.client.inference.usage.output_tokens` | Counter, `{token}` | `tokens_out`, raisonnement compris | `gen_ai.token.modality = text` |
| `k_b.llm.calls` | Counter, `{call}` | 1 par appel | `k_b.outcome`, `k_b.schema_valid` |
| `k_b.llm.check.duration` | Histogram, `s` | `check_ms` / 1000, pour un appel dont une tentative au moins a passé les contrôles (`LlmCall.is_checked`) ; un délai, un 5xx ou une réponse illisible n'en passent aucun | — |
| `k_b.llm.cost` | Counter, `{USD}` | `cost_estimated` | — |
| `k_b.digest.claims_removed`, `k_b.digest.items_removed_by_checks` | Counter | les compteurs de la rédaction | — |
| `k_b.digest.items_with_subject`, `k_b.digest.items_no_suitable_subject`, `k_b.digest.items_unanswered` | Counter | les compteurs du classement | — |
| `k_b.digest.facts_checked`, `k_b.digest.facts_found` | Counter, `{fact}` | les compteurs de la fidélité (#207) ; le taux se calcule dans Grafana par leur rapport, un taux ne s'additionnant pas | — |
| `k_b.digest.facts_found_in_item`, `k_b.digest.facts_found_in_text` | Counter, `{fact}` | les faits trouvés dans leur item, et dans leur `text` (#518) ; rien pour un compte rendu des tendances | — |
| `k_b.digest.data_fetch.duration` | Histogram, `s` | `data_fetch_ms` / 1000 | aucun |

- **Attributs communs** aux mesures d'un appel : `gen_ai.operation.name = chat`,
  `gen_ai.provider.name` (`openai_compatible` ou `replay`, ce que K-B sait),
  `gen_ai.request.model`, `k_b.stage`. Jamais le sujet, le `request_id`, un titre, un auteur ni un
  texte (règle 5 de `poc.md`) : des valeurs fermées, que lit un test. Les traces, elles, portent
  le sujet et le `request_id` (section « Traces de `POST /digests` »).
- **Noms** : ceux des conventions OpenTelemetry pour l'IA générative quand elles en ont un (statut
  *Development*, dépôt `semantic-conventions-genai`, lu le 2026-10-24), l'espace `k_b.` sinon.
  Le paquet Python `opentelemetry-semantic-conventions` 0.66b1 (installé avec le SDK 1.45.1) a
  encore les anciens noms (`gen_ai.client.operation.duration`, `gen_ai.client.token.usage`) : K-B
  suit le texte des conventions, pas ce paquet ([client-inference.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md),
  [gen-ai-token-metrics.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-token-metrics.md),
  lus le 2026-10-24).
  Écart : `llm_ms` compte les deux tentatives et l'attente entre elles, là où la convention mesure
  une opération.
- **`data_fetch`** est mesuré à chaque demande dont la lecture réussit, même sans appel au modèle
  (décision de Sabine du 2026-10-24) : la limite ci-dessus ne vaut plus que pour la ligne JSON.
- **Ressource** : `service.name = k-b-ai-api`, `deployment.environment.name` et
  `service.instance.id`, un UUID tiré au hasard par processus ; rien d'autre (ni `host.name`, ni
  `process.*`, ni chemin) : construite sans `Resource.create`, qui lirait l'environnement et des
  détecteurs. L'identifiant d'instance sépare deux processus qui exportent en même temps (`kb
  serve-ai` et le test de bout en bout, deux réplicas), qui sinon écriraient les mêmes séries
  cumulées. Chaque redémarrage ouvre donc de nouvelles séries : 89 pour une demande dont les
  quatre appels réussissent (compte du 2026-10-24, buckets compris), 91 depuis les deux compteurs
  de faits de #207 (une série chacun, aux attributs de la rédaction ; calcul, non recompté dans
  Grafana), davantage avec des échecs ;
  l'offre gratuite de Grafana Cloud en compte 10 000 actives par mois.
- **Réglages** de `kb serve-ai` : `KB_OTLP_ENDPOINT` (URL de base, `https`) et `KB_OTLP_HEADERS`
  (paires `nom=valeur` du format OTLP), les deux ou aucun ; sans eux, rien n'est exporté. Une URL
  qui finit déjà par `/v1/metrics`, `/v1/traces` ou `/v1/logs` est refusée : K-B ajoute ces
  chemins à l'URL de base, un par signal. Le jeton porte `metrics:write`, `traces:write` et
  `logs:write`.
  `KB_DEPLOYMENT_ENVIRONMENT` (`sandbox` ou `production`), sans défaut, est exigée avec l'export
  (décision de Sabine du 2026-10-24). D'un environnement à l'autre, ces trois réglages changent,
  aucun code. `KB_TRACE_CONTENT` (`none` par défaut, `anomalies`, `all`) dit quel contenu des appels
  au modèle part avec les traces (« Traces de `POST /digests` », ci-dessous) ; posé sans l'export,
  il arrête le démarrage. Une variable `OTEL_*` présente arrête le démarrage : le SDK la lirait sans que K-B le
  sache, et relit l'en-tête même quand K-B le lui passe.
- **Envoi** : toutes les 60 s, et un dernier à l'arrêt, dans le `lifespan` de l'app, avant que
  uvicorn relance le SIGTERM, en même temps que celui des traces ; chaque envoi attend 5 s au plus. La session HTTP de l'exporteur ne
  lit ni proxy, ni certificat, ni `.netrc` de l'environnement (`core/outbound.py`).

**Journaux de l'exporteur** : ses lignes et celles du lecteur périodique passent par le journal
de `kb serve-ai`. Un filtre posé sur ces deux journaux (`QuotingFilter`,
`ai_api/connectors/metrics_export.py`) cite chaque texte par `quote_value` (la phrase d'état du
serveur, qui peut porter un CR ou un caractère de contrôle), chaque exception par son type, et
remplace une trace d'exception par le type de l'exception (règle 3 de `conventions.md`) ; la ligne
reste. Il cite aussi les mots fixes du SDK (`'metrics'`) : une règle simple plutôt qu'une liste de
positions d'arguments propre à une version du SDK.

**Limites** : un envoi qui échoue cite le code HTTP et la phrase d'état, jamais l'en-tête, et se
répète à chaque envoi tant que l'outil est injoignable ; le message de la ligne reste celui du
SDK, en anglais. Le transport du SDK ne suit pas les
redirections, mais compte une réponse 3xx comme un succès : les mesures seraient perdues sans
message ; le test de bout en bout ne voit donc pas ce cas, la preuve finale est la série lue dans
Grafana. Le dernier envoi part quand uvicorn a fini les demandes en cours, jusqu'à
`DIGEST_REQUEST_TIMEOUT_SECONDS` : `docker stop` tue le processus 10 s après SIGTERM, et les
mesures non envoyées d'un arrêt pendant une demande seraient perdues ; le délai d'arrêt du
conteneur relève de #200. La télémétrie native de FastAPI (traces, métriques HTTP, journaux) est
coupée dans les deux API (`core/api_telemetry.py`) : avec `FASTAPI_OTEL_AUTO_CONFIGURE=true`, elle
poserait ses propres fournisseurs, et une trace de l'API de données porterait la requête brute d'un
client. Les traces de `POST /digests` sont décrites ci-dessous ; le `traceparent` envoyé à l'API de
données, et le `trace_id` dans les lignes de journal, restent l'objet de #281.

### Traces de `POST /digests` (#345)

Chaque demande est une trace : le résultat de chaque étape, en identifiants et en comptes, et la
raison de chaque affirmation retirée. Elles servent à suivre une demande étape par étape en bac à
sable, et à comprendre une anomalie en production. Les spans et les évaluations ne portent aucun
texte : ni consigne, ni item, ni réponse du modèle. Le contenu d'un appel au modèle part à côté,
sous réglage, dans un enregistrement à part (#347, « Contenu d'un appel au modèle » ci-dessous ;
exception de la règle 5 de `poc.md`).

```
POST /digests            SERVER   http.request.method, http.route, http.response.status_code, error.type, k_b.request_id
├─ read_watch            INTERNAL k_b.items.read, k_b.items.dropped, k_b.items.capped, k_b.capped_kind, error.type
├─ classify_batch        INTERNAL k_b.batch.index, k_b.items.in, k_b.items.truncated, k_b.outcome,
│  │                              k_b.items.no_suitable_subject.ids, k_b.items.unanswered.ids
│  └─ chat <model>       CLIENT   une par requête HTTP au modèle
└─ write_subject         INTERNAL k_b.subject, k_b.outcome, k_b.items.sent.ids, k_b.items.dropped,
   │                              k_b.items.truncated, k_b.items.not_retained.ids, k_b.items.removed_by_checks.ids,
   │                              k_b.facts.checked, k_b.facts.found, k_b.facts.found_in_item,
   │                              k_b.facts.found_in_text, k_b.claims.removed   (englobe les contrôles)
   └─ chat <model>       CLIENT   une par requête ; les évaluations sur la dernière
```

- **Façade** : `ai_api/tracing.py`, seule à appeler l'API d'OpenTelemetry. Les étapes ouvrent leur
  span en ligne (`tracing.step`), et reçoivent la façade par `tracing=`, comme `Deadline`, jamais
  par un fournisseur global. Le défaut, `TRACING_OFF`, n'enregistre rien. Pour qu'il ne cache pas
  un oubli, un test lit le code : dans `ai_api`, tout appel à une fonction qui prend `tracing` le
  lui passe (`tests/architecture/test_apis.py`).
- **Échec** : un état nommé (`llm_timeout`, `data_api_unavailable`…) met le span en `ERROR`, sans
  description, et le pose dans `error.type`. Une exception imprévue y met le nom de son type,
  jamais son texte : aucun span n'enregistre d'exception, dont le message peut citer un item. Un
  sujet sauté (après un 429, ou faute de temps) est un `write_subject` en erreur, sans enfant ; un
  lot de classement sauté faute de temps, un `classify_batch` en erreur, sans enfant.
- **`chat <model>`** : `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.request.max_tokens`, `gen_ai.prompt.name` et `gen_ai.prompt.version` (l'étape et la
  version de sa consigne), `gen_ai.output.type = json`, les jetons de la tentative
  (`gen_ai.usage.*`), `gen_ai.response.finish_reasons` (fermé : `stop`, `length`,
  `content_filter`, sinon `other`, le fournisseur pouvant y mettre un texte libre),
  `http.response.status_code`, et
  `k_b.attempt`, `k_b.outcome`, `k_b.failed_check`, `k_b.input_chars`. Pas de `server.address`.
- **Pourquoi une affirmation est retirée** : un enregistrement de journal OTLP
  `gen_ai.evaluation.result` par affirmation, rattaché au dernier `chat` de sa rédaction, à
  l'instant où il a fini. `gen_ai.evaluation.name = k_b.claim_checks` (bornes et fidélité, une
  évaluation), `gen_ai.evaluation.score.label = fail`, `k_b.claim.index` (sa position dans la
  sortie), et dans `gen_ai.evaluation.explanation` comme dans le corps, les codes séparés par des
  virgules : `out_of_bounds`, `fact_not_found:<index du fait>:<item>:<où>`, `undeclared_identifier`,
  `cited_item_without_fact`, `disguised_text`. `<où>` dit où manque le fait non trouvé : `item`
  (dans l'item qu'il cite), `text` (dans le `text` de l'affirmation) ou `both` (aux deux) ; un fait
  sans lettre ni chiffre est `both` (#518). Les premiers codes qui tiennent en 2 048 octets sont
  gardés entiers ; `k_b.claim.reasons_truncated` dit qu'il en manque. Un journal, pas un événement de span : OpenTelemetry
  déprécie l'API des événements de span.
- **Identifiants** : des entiers internes, sans donnée personnelle (décision de Sabine du
  2026-10-27, registre). Chaque attribut tient en 2 048 octets d'UTF-8, la limite de Grafana Cloud
  Traces : un texte est coupé, une liste garde ses premiers identifiants, et `<nom>_truncated`
  s'ajoute. Le SDK coupe aussi à 2 048 caractères, en défense.
- **Export** : la même URL de base et le même en-tête que les métriques, `/v1/traces` et
  `/v1/logs` ; gzip ; 3 s par envoi ; tous les spans gardés (`ALWAYS_ON`) ; une seule ressource
  pour les trois fournisseurs. Les journaux du SDK et de l'exporteur passent par le même
  `QuotingFilter`, posé sur quatre journaux nommés (`ai_api/connectors/trace_export.py`), le seul
  module qui importe les modules privés du SDK : `pyproject.toml` borne OpenTelemetry sous 1.46.
  Un échec d'envoi ne fait jamais échouer une demande.
- **Arrêt** : les trois fournisseurs s'arrêtent en même temps. Un arrêt peut envoyer deux fois
  (l'envoi en cours, puis le reste) : au plus max(2 × 3, 2 × 3, 5) = 6 s, sous les 10 s de `docker
  stop`, sans demande en cours. Pour que le reste tienne en un envoi, la file d'attente est d'un
  lot, 512 spans ou enregistrements (`TRACE_QUEUE_SIZE`) ; une demande en fait quelques dizaines,
  plus un enregistrement de contenu par requête au modèle avec `all`, jusqu'à 200 000 octets
  chacun. Un envoi part toutes les secondes : un lot porte la seconde écoulée, loin des 64 Mio
  au-delà desquels l'exporteur le jette. À vérifier à l'essai réel ; si un envoi est refusé, une
  file propre aux journaux, plus courte, toujours d'un lot.
  Au-delà, le SDK abandonne le plus ancien en attente, avec une ligne de journal. Le SDK ne borne
  pas le total d'un envoi (son délai vaut pour chaque attente de la connexion) : chaque arrêt tourne
  dans un fil à part, attendu 6 s au plus (`TRACE_STOP_TIMEOUT_SECONDS`), puis laissé, avec une
  ligne de journal.
- **Lire** dans Grafana : Explore, Tempo, `{resource.service.name="k-b-ai-api"}`, ou
  `{status = error}` pour les demandes en échec ; « Logs for this span » sur un `chat` montre les
  raisons, et le contenu quand il est envoyé. Dans Loki, elles se lisent aussi par
  `{service_name="k-b-ai-api"}`, leurs attributs avec un tiret bas à la place du point
  (`k_b_claim_index`) : vu à l'essai réel du 2026-10-27. Le contenu seul, et la sortie du modèle :
  `{service_name="k-b-ai-api"} | event_name="gen_ai.client.inference.operation.details" | json
  output="output_messages[0].parts[0].content"`. Filtrer sur `event_name` avant `| json` : le corps
  d'une évaluation (des codes) n'est pas du JSON et porterait `__error__`. Le corps est une ligne
  longue, sa sortie à la fin : les icônes `{}` (JSON indenté) et ↵ (retour à la ligne), à droite de
  la liste des journaux, le rendent lisible. Vu à l'essai réel de #347 (2026-10-28, demande
  `506e690d-9b4f-4ce5-9d9a-8b2384711aad`).

**Contenu d'un appel au modèle (#347)** : un enregistrement de journal OTLP
`gen_ai.client.inference.operation.details` par requête au modèle, de niveau DEBUG, rattaché à
son `chat` à l'instant où il a fini, comme une évaluation.
- **Réglage** `KB_TRACE_CONTENT` : `none` (défaut), rien ; `anomalies`, chaque requête d'un appel
  en anomalie ; `all`, chaque requête, refusé au démarrage en production. Avec `none`, l'appel ne
  garde aucun texte (`LlmCall.contents` vide) ; avec un autre réglage, les textes restent hors du
  `repr` de l'appel et de ses mesures.
- **Anomalie** (décision D1 de Sabine du 2026-10-27) : un appel qui finit en
  `llm_invalid_output`, `llm_truncated`, `llm_content_filtered` ou `llm_timeout`, un appel relancé
  après le refus d'un contrôle (même si la relance finit en 429 ou en 5xx), ou un lot de
  classement qui a laissé des items sans réponse. Pas `llm_rate_limited` ni `llm_unavailable`, dont
  la cause est le fournisseur (minimisation) ; ni un `llm_timeout` dont la première tentative a eu
  un 429, un 5xx ou une erreur de transport, la relance étant coupée par le délai de la demande avant
  ou après son départ (précisions de Sabine du 2026-10-28 : même cause ; `LlmCall.first_outcome`) ; ni une affirmation retirée, qui a déjà ses raisons et dont le pourquoi
  s'enquête en bac à sable avec `all`. À rejuger après #210. Le choix est fait par
  `trace_contents` (`connectors/llm_client.py`), juste après chaque appel, avant les contrôles de
  l'étape : une faute dans ces contrôles ne fait pas perdre le contenu de l'appel qui l'a provoquée.
- **Corps** : une chaîne JSON aux trois clés de la convention, `system_instructions` (la consigne
  envoyée, rappel compris pour une relance), `input_messages` (le message utilisateur, les champs
  des items masqués comme pour le modèle) et `output_messages` (la sortie d'un 200, refusée ou non ;
  vide sans sortie : un délai, un 429, un 5xx, un 400, une enveloppe illisible, le corps d'une
  erreur pouvant citer l'entrée). La raison de fin reste sur le span. Le contenu va dans le corps,
  pas en attributs : Grafana Cloud Traces coupe un attribut à 2 Ko, et Loki range les attributs en
  métadonnées plafonnées à 64 Ko, quand une ligne accepte 256 Ko. Une chaîne plutôt qu'un
  dictionnaire : K-B mesure les octets de la ligne que Loki reçoit.
- **Coupe** : au-delà de `MAX_CONTENT_EVENT_BYTES` (200 000 octets d'UTF-8), chaque texte est coupé
  à la même longueur, la plus grande qui tient ; toutes les clés et parties restent, et
  `k_b.content_truncated = true` le dit. Seuls attributs : `gen_ai.operation.name = chat` et ce
  drapeau.
- **Sortie refusée** : elle part comme une chaîne échappée dans un corps de journal, jamais
  interprétée ni écrite dans le coffre ou la réponse de l'API (règle 8 de `poc.md`, inchangée).

**Angles morts** : un 401, un 403, un 422 et un 429 n'ont pas de trace, la route n'étant pas
atteinte ; seule la ligne de `log_request` les dit. Une erreur
après le `return` de la route (la validation de la réponse, la fermeture des dépendances) laisse
une racine à 200 alors que le client reçoit 500 ; la ligne de `log_request` dit le vrai code.

**Écarts à la convention** :
- un span `chat` par requête HTTP, là où la convention regroupe les relances : K-B relance après
  une attente, avec la même consigne, ou après un contrôle raté, avec un rappel, et chaque
  tentative a son résultat ;
- la racine est ouverte par la route, pas par la télémétrie native de FastAPI, qui porterait
  `url.path`, `url.query` et `server.address`, et reprendrait un `traceparent` reçu ;
- `gen_ai.prompt.version` vaut la version de K-B (`classify-2`, `write-1`) ;
- le contenu va dans le corps d'un enregistrement, en une chaîne JSON, pas dans les attributs
  `gen_ai.system_instructions`, `gen_ai.input.messages` et `gen_ai.output.messages` ; il se règle par
  `KB_TRACE_CONTENT`, K-B refusant toute variable `OTEL_*`
  (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT`).

Sources, lues le 2026-10-27 :
[client-inference.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md),
[gen-ai-events.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md),
[dépréciation des événements de span](https://opentelemetry.io/blog/2026/deprecating-span-events/),
[limite de 2 Ko de Grafana Cloud Traces](https://grafana.com/docs/grafana-cloud/whats-new/2025-01-17-higher-reliability-for-grafana-cloud-traces-with-new-limits-on-attribute-size).

## États nommés

| État | Quand | Le classement échoue (toute la demande) | La rédaction d'un sujet échoue |
|---|---|---|---|
| `llm_invalid_output` | contrôles 2 à 6, ou `finish_reason` hors liste, deux fois | 502 | le sujet va dans `failed_subjects`, avec son étape (`stage`) |
| `llm_truncated` | `finish_reason` `length` ; pas de nouvelle tentative (même entrée, même modèle figé : même sortie attendue) | 502 | `failed_subjects` |
| `llm_content_filtered` | `finish_reason` `content_filter` : le filtre de contenu du fournisseur a retenu la sortie (celui d'Azure peut réagir aux textes sur le jailbreak et l'injection, sujets de la veille) ; ou un 400 dont `error.code` vaut `content_filter` : il a retenu l'entrée ; pas de nouvelle tentative (même entrée) | 502 | `failed_subjects` |
| `llm_rate_limited` | 429 du fournisseur, après la nouvelle tentative ; ou un 429 dont le `Retry-After` dépasse `LLM_RETRY_AFTER_MAX_SECONDS`, sans nouvelle tentative | 503, avec le `Retry-After` du fournisseur ; sans en-tête s'il n'en a pas donné (aucune attente inventée) | `failed_subjects`, et chaque sujet suivant, sans envoi (#205) |
| `llm_unavailable` | 5xx, connexion refusée ou coupée, après la nouvelle tentative ; autre 4xx, réponse qui ne se décode pas, réponse au-delà de `MAX_LLM_ANSWER_BYTES` (1 000 000 d'octets, annoncés ou comptés, OWASP API10:2023), ou réponse 200 qui n'est pas une complétion lisible (pas du JSON, aucun `choices`, un type faux), sans nouvelle tentative | 502 | `failed_subjects` |
| `llm_timeout` | pas de connexion ou pas de réponse dans le délai du client (#150), sans nouvelle tentative ; ou durée totale de la demande dépassée (`DIGEST_REQUEST_TIMEOUT_SECONDS`), pour chaque sujet pas encore rédigé, ou pendant la lecture d'une réponse | 504 | `failed_subjects` |
| `data_api_unavailable` | API de données injoignable, ou 5xx | 502 | — |
| `data_api_timeout` | délai de lecture dépassé | 504 | — |
| `data_api_unauthorized` | 401 de l'API de données : clé `AI_DIGEST` refusée (sans clé, l'API IA ne démarre pas, règle 2 de `poc.md`) | 502 | — |
| `data_api_rate_limited` | 429 de l'API de données, sans nouvelle tentative ni `Retry-After` transmis | 503 | — |
| `data_api_invalid_response` | réponse hors du schéma attendu | 502 | — |
| `invalid_parameter` | demande mal formée, `window_days` hors bornes | 422 | — |
| `invalid_api_key` | appel sans clé, ou clé inconnue (#156) | 401 | — |
| `client_not_allowed` | clé valide d'un autre client que celui de la route (« Accès », #161) | 403 | — |
| `rate_limit_exceeded` | client au-delà de la limite de la route (« Accès », #161) | 429, avec `Retry-After` | — |
| `request_already_running` | une demande tourne déjà sur la route (« Accès », #161) | 429, avec `Retry-After` | — |
| `content_too_large` | corps de plus de `MAX_AI_API_BODY_BYTES` (1 024 octets), avant la clé (#161) | 413 | — |
| `route_not_found`, `method_not_allowed`, `internal_error` | comme l'API de données | 404, 405, 500 | — |

- Les états `data_api_*` sont ceux de la lecture par l'API de données (#204). Un item disparu entre
  la liste et le détail (404 `item_not_found`) n'est pas un échec : il est sauté et compté
  (`items_dropped_before_writing_stage`).
- **Nouvelle tentative** (#150, `core/config.py`) : une au plus par appel. Après un 429, un 5xx
  ou une connexion refusée, elle attend `Retry-After` (en secondes ; une date HTTP compte comme un
  en-tête absent), ou `LLM_RETRY_WAIT_SECONDS` sans lui ; un `Retry-After` au-delà de
  `LLM_RETRY_AFTER_MAX_SECONDS` met fin à l'appel, car une attente plus courte rendrait la même
  réponse. Un appel dure ainsi 210 s quand les réponses arrivent d'un bloc (deux tentatives de
  5 s de connexion et 90 s de réponse, et 20 s d'attente) ; 90 s couvrent une sortie de 8 192
  jetons au débit mesuré par #158 sur gpt-6-luna (environ 7,35 ms par jeton, soit ~60 s) ; une réponse envoyée par morceaux peut
  durer plus, car chaque lecture a son propre délai : la borne totale est celle de la demande,
  `DIGEST_REQUEST_TIMEOUT_SECONDS` (#205), avec sa limite (section « Lecture plafonnée »).
- 502, 503 et 504 disent la panne de l'amont, comme une passerelle (RFC 9110, § 15.6) : le client
  distingue « réessayer plus tard » (503, 504) d'une sortie fautive (502).
- **Échec partiel** : la réponse est 200 dès que le classement a réussi ; chaque sujet en échec est
  nommé dans `failed_subjects`, et les autres sont rendus (#205).
- **Après un 429 que la rédaction n'a pas surmonté, plus aucun envoi** (#205, constats de `/code-review`, tranchés
  par time-knight, délégation de Sabine du 2026-10-15) : le fournisseur a dit d'attendre,
  et les items des sujets suivants partiraient pour une réponse refusée (minimisation, RGPD
  art. 5.1.c ; « les items ne partent pas pour une réponse que l'échéance jetterait »). Les
  sujets restants vont dans `failed_subjects`, `stage: write`, `llm_rate_limited`, qui veut dire
  ici « pas envoyé : un sujet précédent a reçu un 429 ». Le code lit le 429 observé sur l'une ou
  l'autre tentative (`LlmCall.saw_rate_limit`), pas seulement l'état final : une nouvelle tentative
  après un 429 qui finit en délai dépassé, en 5xx, ou sautée par l'échéance (`llm_timeout`,
  décision de Sabine du 2026-10-17, plan de #205), arrête aussi les envois. En revanche, une
  nouvelle tentative qui a attendu le `Retry-After` puis reçu une réponse a surmonté le 429 : le
  fournisseur accepte de nouveau, et les sujets suivants partent vers un fournisseur qui répond,
  pas vers une réponse refusée (tranché par time-knight, délégation de Sabine du 2026-10-15 ;
  option écartée : arrêter après tout 429, même surmonté, qui ferait tomber des sujets
  rédigeables). Le `Retry-After` d'un classement en échec
  n'est rendu qu'avec `llm_rate_limited` (503), jamais avec un 504 `llm_timeout` ni un 502. On
  n'arrête pas sur `llm_content_filtered`, `llm_truncated` ni `llm_invalid_output`, propres à un
  sujet, ni sur un `llm_timeout` sans 429 observé, que l'échéance garde déjà. **Limite** : on n'arrête pas non plus sur
  `llm_unavailable`, qui mêle les pannes du fournisseur (5xx, connexion refusée) et les refus
  propres à une requête (un autre 4xx, une réponse illisible) : après une panne, les sujets
  suivants partent encore.
- **Limite : un lot de classement en échec fait échouer toute la demande.** Prompt Shields, actif
  dans `DefaultV2`, lit le message utilisateur, où sont les items : un item réel qui parle
  d'injection d'instructions peut faire rendre un 400 `content_filter` à tout un lot (502
  `llm_content_filtered`, sans nouvelle tentative). Un seul item piégé peut aussi provoquer deux
  sorties fautives de suite (un doublon, refusé par le contrôle 2 depuis `classify-2` ; une
  sortie sans fin, `llm_truncated`). Non observé par #158 (aucun filtre sur 20 appels réels) ;
  renvoyé à #206 (décision de Sabine du 2026-10-17), qui teste le doublon sur le replay (une clé
  deux fois, `schema`). Un doublon sans aucun piège a fait échouer l'essai 1 de #210 sur
  `classify-1` (section « Sortie du classement »). Le filtre et la sortie sans
  fin, sur le vrai modèle, passent à #210, où Sabine décide de l'essai (décision du 2026-10-21 :
  provoquer le filtre exprès est l'essai écarté par #158). Option écartée : couper le lot en deux
  et recommencer pour isoler l'item (jusqu'à environ 12 appels de plus, et un contrat changé).
- Une fenêtre sans item rend 200 avec `digests` vide, sans appel au modèle.

## Fiches dans le coffre

`kb digest` (#209) demande les fiches à l'API IA, puis écrit celle de chaque sujet dans le coffre
d'Obsidian : l'API IA n'écrit rien (règle 7 de `poc.md`). Il joint l'API IA par HTTP, jamais par
son code (ni `etl` ni `post` n'importent `ai_api`, `tests/architecture/test_layers.py`). Code :
`commands/digest_command.py` (la porte), `post/ai_api_client.py` (la demande et la réponse),
`post/digest_sheets.py` (la fiche), `post/vault_files.py` (l'écriture sûre, partagée avec les fiches
des tops).

**Parcours**

1. **Réglages** : `KB_VAULT_DIR`, un dossier existant (sinon code 2, aucun dossier créé) ;
   `KB_AI_API_URL`, `https`, ou `http` vers `127.0.0.1`, `localhost` ou, en `sandbox`, un service du
   compose (`api-donnees` ou `api-ia`, #473),
   sans utilisateur, requête ni fragment, par défaut
   `http://127.0.0.1:8001` (`AI_API_URL`, `core/config.py`), qui ne suit pas `KB_AI_API_PORT` ;
   `KB_AI_API_KEY_KB_DIGEST`, sans défaut, aux règles des clés (section « Accès »). Un refus nomme
   la variable, jamais la clé ni l'URL.
2. **Avant la demande**, pour chaque sujet de la liste : ni `veille/` ni `veille/<sujet>/` n'est un
   lien symbolique, et la fiche du jour UTC n'existe pas. Sinon : code 2 (`vault_link_refused`,
   `sheet_not_a_file`, `sheet_exists`), aucune demande : aucun item ne part au modèle pour une
   fiche qui ne serait pas écrite. Rien n'est créé par ce contrôle.
3. **`POST /digests`** avec `{}` : la fenêtre par défaut de l'API IA (`KB_DIGEST_WINDOW_DAYS`).
   Délais nommés (`core/config.py`) : connexion 5 s, pool 5 s, écriture 10 s, lecture 240 s
   (`AI_API_READ_TIMEOUT_SECONDS`) : au-dessus de `DIGEST_REQUEST_TIMEOUT_SECONDS` et du dernier
   appel au modèle en cours (environ 20 s de plus, `ai_api/deadline.py`). La réponse est lue en
   flux par la borne commune des clients de K-B (`read_bounded_body`, `core/outbound.py` ; OWASP
   API4:2023, API10:2023, #422) : 8 000 000 d'octets décodés au plus (`MAX_AI_API_ANSWER_BYTES`),
   annoncés par `Content-Length` ou comptés, et 240 s depuis l'envoi
   (`AI_API_REQUEST_DEADLINE_SECONDS`), contrôlées après chaque morceau. Au-delà de la borne :
   l'état du statut (`ai_api_invalid_response` pour un 200, `ai_api_failed` pour une 5xx…),
   `response larger than 8000000 bytes`, le `X-Request-ID` et le `Retry-After`, jamais le corps ;
   au-delà de l'échéance : `ai_api_timeout`. Aucune nouvelle
   tentative : un `Retry-After` est affiché, jamais attendu. Aucune redirection suivie, aucun proxy
   de l'environnement (`core/outbound.py`). Pendant l'attente, `kb digest` montre qu'il attend
   (`commands/wait_display.py`, paragraphe « Console » ci-dessous).
4. **La réponse est relue** par un schéma fermé (types stricts, champs inconnus ignorés, les
   `facts` jamais lus) : `request_id` en UUID, `model` au motif `MODEL_NAME` (`core/config.py`),
   `stage` et `error` au motif `[a-z_]{1,64}`, `capped_kind` dans la liste fermée des sortes
   d'items (`ItemKind`, `items.py` : un mot que YAML lit comme nul ou booléen ferait passer une
   fenêtre coupée pour entière), dates avec fuseau, au moins une
   source par affirmation. Puis : chaque sujet est de la liste fermée, une fois dans la réponse ; chaque source
   est une fois dans sa fiche ; chaque affirmation cite des sources de sa fiche, chacune une fois.
   Hors de là : `ai_api_invalid_response`, aucune fiche écrite. L'erreur nomme la place et le
   contrôle, jamais la valeur reçue.
5. **Une fiche par sujet rendu**, `veille/<sujet>/AAAA-MM-JJ.md`, au jour UTC de `window.until` :
   le chemin est fait de constantes, d'un sujet de la liste et d'un jour. Elle est écrite une fois :
   `kb` ne réécrit jamais une fiche qu'il voit, et ne suit jamais un lien qu'il voit ; les dossiers
   et la fiche sont recontrôlés juste avant l'écriture, par un temporaire caché au nom fixe, créé
   seulement s'il n'existe pas, puis renommé (règle 2 de `conventions.md`, #295). Une limite : voir
   « Limites », ci-dessous.

**La fiche** : du Markdown déterministe (la même réponse donne les mêmes octets), ses clés en
anglais, son texte en français (règle de Sabine du 2026-10-21) :

```markdown
---
subject: coding_assistants
generated: 2026-10-21T18:28:37Z
model: "gpt-6-luna"
window_days: 3
since: 2026-10-18T18:28:37Z
until: 2026-10-21T18:28:37Z
items_capped: false
capped_kind: null
covered_after: null
request_id: 6ac62295-48be-4dec-9c43-7a71e00e4282
---

# Veille coding_assistants du 2026-10-21

- Claude Code publie la version v2.1.287. (source 1)

## Sources

1. anthropics/claude-code Claude Code 2.1.287 — <https://github.com/anthropics/claude-code/releases/tag/v2.1.287>
```

`generated` est `window.until`, l'instant de la demande côté API IA ; `model` est écrit en chaîne
JSON, que YAML lit telle quelle ; `items_capped` dit une fenêtre coupée par le plafond, et
`capped_kind` et `covered_after` la sorte coupée et la date de son premier item laissé de côté :
cette sorte n'est lue qu'après cette date (section « Lecture plafonnée ») ; `null` quand rien
n'est coupé. Une affirmation cite ses sources par leur numéro, en texte ; seule la liste
des sources porte des URL. Une fiche sans affirmation dit « Aucune affirmation retenue. », sans
sources.

**Écrit en texte.** Le texte de chaque affirmation et le titre de chaque source : sur une ligne
(retours à la ligne et blancs réduits à une espace ; contrôles, surrogates isolés et contrôles
bidirectionnels remplacés par une espace), les caractères ``\ [ ] < > | ` # % $ ~ : @`` et le `&`
qui ouvre une référence de caractère (`&` suivi de `#`, ou d'un nom puis `;` : `R&D` reste tel quel)
précédés d'une barre oblique inverse (CommonMark 0.31.2, § 2.4 : toute ponctuation ASCII
s'échappe), puis le
point de `www.`, sans casse, et la ponctuation d'un marqueur de liste en tête du texte (`-`, `+`,
`*`, ou `.` et `)` après un à neuf chiffres : `\- urgent`, `2026\. Bilan`) ; deux deux-points de
suite sont séparés par une espace (`std::string` s'affiche `std: :string`). Ne s'activent donc ni
lien, image, lien wiki, incorporation, note en ligne, balise, lien automatique `<…>`, ni ceux de GFM
(`http://`, `https://`, `www.`, et, dans Obsidian, `mailto:`, `xmpp:` et une adresse mail : recette
du 2026-10-21), ni code en ligne, bloc
```` ``` ```` ou `~~~`, requête Dataview en ligne (`=`, `$=`), bloc `dataviewjs`, champ Dataview
(`[clé:: valeur]`, `(clé:: valeur)`, `clé:: valeur`), tag, commentaire `%%`, formule `$`, référence
de caractère (`&rlm;`, que CommonMark décode en contrôle bidirectionnel) ni liste imbriquée. Un
champ Dataview demande `::` à deux endroits : l'indexeur de Dataview le cherche dans la source de
la note, où il est écrit `\:\:`, et n'en tire donc aucune métadonnée de la page ; en mode lecture,
Dataview le cherche aussi dans le texte rendu, où les barres obliques ont disparu
(`replaceInlineFields` lit le HTML rendu, Dataview 0.5.68) : seule une espace entre les deux
deux-points l'y empêche (recette de Sabine du 2026-10-21). Une URL de source qui contient `::` est
refusée (ci-dessous) : aucun champ ne se forme donc, ni dans les textes ni dans les URL, ni dans la
source ni dans le texte rendu. Une ligne horizontale ou un soulignement (`---`,
`***`, `===`) n'est jamais seul sur sa ligne : l'affirmation finit par ses sources, le titre par
son URL. Les caractères des fiches des tops sont repris (`post/vault_files.py`), avec la même règle
du `&`, une seule pour les deux écrivains du coffre (décision de Sabine du 2026-10-21) ; `~ : @`,
`www.`, le marqueur de liste et l'espace entre deux deux-points s'y ajoutent, car une URL nue reste du texte dans un compte rendu de veille : une
affirmation du modèle ne fait jamais un lien. Le contrôle 6 de l'API IA reste en amont (défense en profondeur). Non échappée, voulu :
l'emphase (`*x*`, `_x_`, `==x==`), de la mise en forme, ni lien ni code.

**Une URL** n'est écrite, en lien automatique `<…>`, que si elle commence par `http://` ou
`https://` et n'est faite que des caractères de la RFC 3986 (non réservés, délimiteurs, `%` suivi de
deux chiffres hexadécimaux), moins `[`, `]` et `$`, syntaxe d'Obsidian (lien wiki, formule) : elle
ne peut pas sortir de ses chevrons, où une barre oblique n'échappe rien (CommonMark 0.31.2, § 6.5).
Elle est refusée aussi si elle contient une référence de caractère (`&#…`, `&nom;` : cmark-gfm
affiche `&#x202E;` en U+202E dans le texte du lien), `::` (un champ Dataview dans la ligne rendue),
ou, une fois ses pourcents décodés, de l'UTF-8 invalide, un caractère de contrôle, de format (dont
les bidirectionnels), un surrogate ou un séparateur de ligne (`%E2%80%AE`, `%00` : markdown-it les
montre décodés) ; sinon un lien se lirait autrement qu'il ne mène (CWE-451), comme
`https://docs.python.org&#x202E;@evil.example/`. L'URL est refusée, jamais réécrite : la réécrire
changerait sa cible. Sinon la source est écrite « (sans URL) ». `?a=1&b=2`, `%20` et `%C3%A9`
passent. Un hôte en `xn--` (un nom de domaine internationalisé) n'est pas refusé : des domaines
légitimes l'utilisent.

**Codes de sortie** (l'unité est le sujet ; codes nommés par `ExitCode`, listés par `kb --help`) :

| Code | Quand |
|---|---|
| 0 | chaque fiche rendue est écrite ; ou aucune fiche dans la fenêtre (`total  none in the window`) |
| 1 | l'API IA injoignable (`ai_api_unavailable`), délai ou échéance dépassés (`ai_api_timeout`), clé refusée (`ai_api_unauthorized`, 401), route refusée au client (`ai_api_forbidden`, 403), limite atteinte (`ai_api_rate_limited`, 429), panne (`ai_api_failed`, 5xx), autre réponse, réponse hors schéma ou 200 au-delà de 8 000 000 d'octets (`ai_api_invalid_response`) : aucune fiche écrite ; ou un sujet en échec et aucune fiche écrite ; ou une `OSError` au contrôle d'avant la demande |
| 2 | réglage refusé, `KB_VAULT_DIR` absente ou pas un dossier, fiche du jour déjà là ou lien, vus avant la demande : rien n'est demandé |
| 4 | un sujet en échec (nommé dans `failed_subjects`, ou sa fiche non écrite) et au moins une fiche écrite |
| 130 | SIGINT (Ctrl-C) : les fiches déjà écrites restent |
| 143 | SIGTERM : les fiches déjà écrites restent |

Une clé refusée par l'API IA sort en 1, et une clé absente en 2 : avec une clé refusée, la requête
est partie ; c'est la règle de `kb collect`, où une source qui rend 401 échoue (décision de Sabine du
2026-10-21). Le message nomme `KB_AI_API_KEY_KB_DIGEST`, jamais la clé. 4 suit la règle « même
résultat, même code » de `kb collect` et `kb write-tops` (décision de Sabine du 2026-10-21).

**Console** (libellés en anglais) : pendant la demande, sur la sortie d'erreur, l'attente (#349).
Dans un terminal, une ligne qui tourne et compte, coupée à la largeur du terminal, effacée à la
réponse, jamais écrite dans `kb.log` : `⠹ waiting for the digests: 23 s` (courte, 31 caractères, pour
tenir dans la plupart des fenêtres ; le délai de lecture est dans la ligne écrite juste avant la
demande). **Limite** (observée par Sabine le 2026-10-28) : si la fenêtre est rétrécie sous la longueur
de la ligne pendant l'attente, le terminal replie la ligne déjà écrite sur plusieurs rangées ; `\r` ne
revient qu'au début de la dernière, et ni les images suivantes ni l'effacement final n'atteignent les
rangées du dessus : des morceaux de lignes restent à l'écran. Rien de plus qu'un défaut d'affichage :
le compteur avance, la commande n'en est pas affectée. L'effacer demanderait des séquences de contrôle
du terminal (remonter le curseur, effacer les rangées) et le suivi des redimensionnements : écarté le
2026-10-28 (décision de Sabine). Hors
terminal (sortie redirigée, conteneur sans TTY), une ligne datée toutes les
`WAIT_LOG_INTERVAL_SECONDS` (10 s, `core/config.py`), aussi dans `kb.log` :
`still waiting for the digests: 10 seconds, read timeout 240 seconds`. Le mode se choisit sur la
sortie d'erreur, là où l'attente s'écrit ; un conteneur lancé avec un TTY (`docker run -t`,
`tty: true`) recevrait donc l'animation dans son journal. La ligne dit que `kb` attend, pas que l'API
IA avance (l'avancement par sujet : #350). Deux lignes de journal datées bornent la commande :
`digest started: 8 subjects asked`, avant la demande, et `digest finished in 4 min 6 s`, une fois les fiches
écrites (aucune ligne de fin si la réponse est refusée : la ligne d'erreur termine). Puis le bilan, sur
la sortie standard (exemple de l'essai du 2026-10-28, la fenêtre et le nombre d'items en moins) :

```
Digest summary
--------------
Window: 2026-10-25 → 2026-10-28, 412 items read

subject               status         sheet
vulnerabilities       sheet written  veille/vulnerabilities/2026-10-28.md
…
software_engineering  sheet written  veille/software_engineering/2026-10-28.md
------------------------------------------------------------------------------
total                 written 8, failed 0

Model: gpt-6-luna
Request id: 1bc0caf3-78ad-4b8d-ae56-397ba9d766c7
```

La fenêtre (`window.since` → `window.until`, en jours UTC) et `items_in` viennent de la réponse de
`POST /digests`. Un sujet en échec a sa ligne (`digest failed`, ou `sheet not written`), sans chemin ;
la raison est dans sa ligne d'erreur. Le `request_id` vient en dernier, seul : c'est la référence à
donner en cas de problème (décision de Sabine du 2026-10-28). Chaque échec va une fois au journal, sur la sortie d'erreur et
dans `<KB_DATA_DIR>/logs/kb.log` : sujet en échec (étape et état), fiche non écrite, ou réponse
refusée, avec son état, son statut HTTP, l'état de son corps, son `X-Request-ID` (pour la retrouver
dans `logs/kb-serve-ai.log`) et son `Retry-After`, chacun écrit tel quel s'il suit sa règle, sinon
tronqué et échappé (règle 3 de `conventions.md`).

**Limites**

- **L'échéance de la réponse** n'est contrôlée qu'après chaque morceau décodé : rien ne borne
  l'attente avant le premier, ni des morceaux bruts qui ne se décodent en rien. Chaque lecture de
  l'en-tête attend 240 s au plus, mais pas leur somme : un en-tête envoyé octet par octet, ou un
  corps compressé fait de blocs vides, tient `kb` sans fin ; en ligne, l'ingress d'ACA coupe une
  requête à 240 s. C'est un défaut de `read_bounded_body` pour ses quatre clients, déjà sur `main`
  avant #422 (porté par #436). Les clients de l'API IA raccourcissent aussi chaque délai au temps
  qui reste (`ai_api/deadline.py`), que `post` n'importe pas ; au départ d'une demande de `kb`, il
  reste 240 s, et le raccourci ne changerait rien.
- **Relancer le même jour** après un échec partiel sort en 2 : une fiche du jour existe. Les
  sujets en échec s'écrivent le lendemain, si leurs items restent dans la fenêtre.
- **Le jour contrôlé** avant la demande est celui de l'horloge de `kb` ; celui de la fiche,
  `window.until` de l'API IA. Une demande à cheval sur minuit UTC écrit la fiche du lendemain, et un
  sujet dont la fiche du lendemain existe déjà compte en échec (`sheet_exists`).
- **Deux lancements qui se chevauchent** (#295) : chacun réserve la fiche en créant son temporaire
  caché `.AAAA-MM-JJ.md.tmp`, qui n'est créé que s'il n'existe pas (`O_EXCL`, FILE_CREATE sur le
  partage SMB d'Azure Files, où `os.link` n'existe pas), puis, juste avant le renommage, cherche la
  fiche dans la liste du dossier. Le second trouve le temporaire ou la fiche : il ne remplace rien. Un temporaire trouvé
  fait échouer le sujet (`temporary_file_found`), comme pour les tops et le compte rendu des
  tendances : un job planifié ne réussit pas sans sa fiche.
- **Un SIGKILL**, une session SMB perdue, ou un SIGTERM reçu dans les quelques microsecondes entre
  la création du temporaire et le bloc qui le retire, laisse ce temporaire dans `veille/<sujet>/` ;
  Obsidian n'affiche pas un fichier caché. La fiche de ce jour est alors refusée
  (`temporary_file_found`) jusqu'à ce que le temporaire soit retiré à la main ; celle du lendemain a
  son propre nom. Pour les tops, le relevé est gardé et la même fiche réessayée : le top échoue à
  chaque lancement (README, « `kb write-tops` »).
- **Un dossier remplacé par un lien** entre le dernier contrôle et l'écriture y fait écrire hors du
  coffre (CWE-59 ; limite acceptée par Sabine le 2026-11-10, registre, fiche 1, « Sécurité »). Seul
  un processus qui a déjà le compte de l'utilisatrice le peut ; un texte de source ou du modèle ne
  le peut pas.
- **Une adresse mail dans un moteur GFM** : dans cmark-gfm (GitHub), `\@` n'empêche pas le lien
  d'une adresse mail, ni `\:` celui de `mailto:` ou `xmpp:`, car les nœuds de texte y sont recollés
  avant l'extension des liens automatiques (`blocks.c`, `extensions/autolink.c`). Aucune correction
  de code propre ; enjeu très faible (CWE-116) : un lien `mailto:` vers l'adresse, sans sujet ni
  corps, et l'adresse est déjà dans le texte. Le coffre se lit dans Obsidian, où elle reste du texte.
- **Le rendu dans Obsidian**, un logiciel fermé, n'est prouvé que par la recette de #209 (PR) : un
  autre lecteur de Markdown, ou un autre module d'Obsidian (Templater…), n'est pas couvert.

## Sources

Consultées le 2026-10-15, sauf mention.

- [CommonMark Spec 0.31.2](https://spec.commonmark.org/0.31.2/) — lue le 2026-10-21 (#209) :
  § 2.4, toute ponctuation ASCII s'échappe par une barre oblique inverse ; § 6.5, aucun
  échappement dans un lien automatique `<…>`.
- [GitHub Flavored Markdown Spec](https://github.github.com/gfm/) — lue le 2026-10-21 (#209) :
  § 6.9, liens automatiques étendus (`www.`, `http://`, `https://`, adresse mail, `mailto:`,
  `xmpp:`).
- [Dataview, requêtes en ligne DQL et JavaScript](https://blacksmithgu.github.io/obsidian-dataview/queries/dql-js-inline/)
  — lue le 2026-10-21 (#209) : `` `= …` `` et `` `$= …` ``, blocs `dataviewjs` ; les requêtes
  JavaScript ne tournent que si l'utilisatrice les active.
- [RFC 3986, Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986),
  § 2 — grammaire (`unreserved`, `gen-delims`, `sub-delims`, `pct-encoded`) recoupée le 2026-10-21
  par une recherche web, sur des pages qui la reproduisent, pas sur le texte de l'IETF (#209).

- [Azure Retail Prices overview](https://learn.microsoft.com/ar-sa/rest/api/cost-management/retail-prices/azure-retail-prices)
  — Microsoft Learn, rendue par une recherche du 2026-10-21 : l'API des prix de détail,
  `https://prices.azure.com/api/retail/prices`, sans authentification. Requête du 2026-10-21,
  `api-version=2023-01-01-preview`, filtre `armRegionName eq 'francecentral' and
  contains(meterName, 'luna')` : compteurs `6-luna ShortCo Inp Std DZ 1M Tokens` (0,12 USD) et
  `6-luna ShortCo Opt Std DZ 1M Tokens` (0,60 USD), `effectiveStartDate` 2026-09-01
  (`cost_estimated`). Recoupé par une recherche du même jour : [GPT-6 Luna Azure Pricing](https://www.azurespeed.com/AzureAiModelPricing/Models/openai-gpt-6-luna),
  agrégateur tiers, 0,11 à 0,12 et 0,55 à 0,60 USD en Data Zone Standard.

- [Data, privacy, and security for Foundry Models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy)
  — Microsoft, relevé par recherche web : les demandes et réponses ne servent pas à entraîner les
  modèles ; un déploiement Data Zone traite dans la zone choisie (UE).
- [Region availability of Foundry Models sold by Azure](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability)
  — Microsoft, relevé par recherche web : gpt-5.6-luna, version 2026-07-09. Consultée le
  2026-10-16 par time-knight (onglet Data Zone Standard, Europe) : gpt-6-luna
  (2026-09-22) et gpt-5.6-luna ont la même ligne, cochée pour francecentral et swedencentral
  entre autres, non cochée pour northeurope.
- [GPT-6 Astra, Sol and Luna for production agents in Microsoft Foundry](https://azure.microsoft.com/en-us/blog/gpt-6-astra-sol-and-luna-for-production-agents-in-microsoft-foundry/)
  — Microsoft, consultée le 2026-10-16 (relevée par time-knight) : gpt-6-luna en disponibilité
  générale, en Data Zone UE.
- [How to use structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
  — Microsoft, relevé par recherche web : en mode strict, tous les champs `required`, et
  `minLength`, `maxLength`, `minItems`, `maxItems` non pris en charge (schéma portable).
- [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs) —
  OpenAI, relevé par recherche web : 1 000 valeurs d'`enum` au plus par schéma (schéma portable).
- [Reasoning models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning) —
  Microsoft, relevé par recherche web : `reasoning_effort` accepte `none` pour GPT-5.6 ;
  `max_completion_tokens` compte les jetons de raisonnement (réglages d'appel, plafond de sortie).
- [Work with chat completion models](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/chatgpt)
  et [Content filtering](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/content-filter)
  — Microsoft, relevé par recherche web : les modèles à raisonnement ne prennent pas `temperature` ;
  une sortie retenue par le filtre rend `finish_reason` `content_filter` (contrôle 1, états
  nommés).
- [Content filter and policy violation issues when using openAI API](https://learn.microsoft.com/en-us/answers/questions/2044545/content-filter-and-policy-violation-issues-when-us)
  — Microsoft Q&A, relevé par recherche web : une entrée filtrée rend un 400, `error.code`
  `content_filter`, `innererror.code` `ResponsibleAIPolicyViolation` ; la catégorie jailbreak peut
  le déclencher sur une consigne ordinaire (constat du forum CrewAI, même recherche) (états nommés,
  `llm_content_filtered`). Non observé par #158 : aucun filtre déclenché sur 20 appels réels, et
  aucun essai provoqué (commentaire de #158 du 2026-10-17).
- [Custom Structured Outputs](https://docs.mistral.ai/studio-api/conversations/structured-output/custom)
  — Mistral, lu par Context7 : « Your output should be an instance of a JSON object following
  this schema: {{ json_schema }} » est toujours ajouté au début du message `system` (limite de la
  consigne).
- [Models, « Extra data »](https://docs.pydantic.dev/latest/concepts/models/#extra-data) — Pydantic,
  lu par Context7 : `extra='forbid'` refuse un champ en trop (`extra_forbidden`) et écrit
  `additionalProperties: false` dans le JSON Schema (schémas, contrôle 2).
- [LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) — OWASP
  Gen AI Security Project, relevé par recherche web : définir et valider le format de sortie par du
  code déterministe ; borner le rôle dans la consigne ; filtrer les sorties (contrôles, injection).
- [OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/)
  — OWASP Gen AI Security Project, consultée le 2026-10-15 : l'édition 2026 (publiée le
  03/08/2026) remplace la 2025 ; l'injection d'instructions reste LLM01.
- [API4:2023 Unrestricted Resource Consumption](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/)
  — OWASP, relevé par recherche web : une API qui ne borne pas les ressources qu'une demande
  consomme, services tiers payés à l'appel compris, risque un déni de service ou un surcoût ;
  borner le nombre d'enregistrements, les tailles, la durée (lecture plafonnée).
- [RFC 9110, § 15.6](https://www.rfc-editor.org/rfc/rfc9110#section-15.6) — IETF, relevé par
  recherche web : 502 (§ 15.6.3, une réponse invalide de l'amont), 503 (§ 15.6.4, indisponibilité
  temporaire, `Retry-After` permis), 504 (§ 15.6.5, l'amont n'a pas répondu à temps), pour un
  serveur qui agit en passerelle (états nommés).
