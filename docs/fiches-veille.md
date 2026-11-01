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
du corps n'est pas bornée (OWASP API4:2023) : signalé à #161, dont le critère borne la taille
d'entrée en configuration.

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
| `failed_subjects` | chaque sujet en échec, son étape (`stage` : `write`, la rédaction) et son état nommé |
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
- **Pas de `TrustedHostMiddleware`**, écart voulu à la ligne API8 de [specs-api.md](specs-api.md) :
  sans clé, une requête n'atteint que `/health`, `/docs` et `/openapi.json`, qui ne contiennent
  aucune donnée, si bien qu'un rebinding DNS n'obtient rien et ne coûte aucun appel. Signalé à
  #161 (OWASP API Top 10 de l'API IA) et à revoir en conteneurs (#200), où l'hôte appelant change.
- **`GET /health`** répond 200 `{"status": "ok"}` sans clé, comme celle de l'API de données.
- **Version** : `0.6.0` (`info.version` de `docs/api/openapi-ia.json`, écrite par `kb openapi`) ;
  un changement visible par un client change les deux. `0.1.0` : `POST /digests` (#156) ; `0.2.0` :
  `model` dans la réponse (#209) ; `0.3.0` : `unanswered`, et `not_retained` du premier niveau
  renommé `no_suitable_subject` (#210, `classify-2`) ; `0.4.0` : `items_dropped` renommé
  `items_dropped_before_writing_stage`, `digests[].not_retained` renommé
  `digests[].items_not_retained_in_output`, `digests[].items_uncited` renommé
  `digests[].items_removed_by_checks` (décision de Sabine du 2026-10-26) ; `0.5.0` :
  `POST /trend-reports` (#366) ; `0.6.0` : les fiches lues sur GitHub dans la réponse de
  `POST /trend-reports`, et ses erreurs `github_*` (#367) ; `POST /digests` ne change pas.

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
| `stage` | `classify` ou `write` |
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
| `failed_check` | le contrôle qui a refusé la dernière tentative (`content_filter`, `finish_reason`, `schema`, `subject`, `item_id`, `completeness`, `markup`) ; nul si `ok` |
| `first_failed_check` | le contrôle qui a refusé la première tentative, quand une seconde a suivi ; nul sinon (#205, `LlmCall`, constat de #158 : le motif de la première tentative était perdu) |
| `facts_checked`, `facts_found` | compteurs de la fidélité (rédaction, section « Fidélité », « Ce qui est compté ») ; nuls au classement et pour une rédaction en échec |
| `fidelity_rate` | `facts_found` / `facts_checked`, arrondi à 4 décimales ; nul au classement, pour une rédaction en échec, et quand `facts_checked` vaut 0 |
| `claims_removed`, `items_removed_by_checks` | compteurs des contrôles, bornes ou fidélité (rédaction) ; nuls au classement |
| `items_with_subject`, `items_no_suitable_subject`, `items_unanswered` | compteurs du classement (section « Sortie du classement », « Trois cas ») : les items du lot qui ont reçu un sujet, ceux auxquels aucun sujet ne convient, et ceux que le modèle a laissés sans réponse, `items_in` à eux trois ; nuls à la rédaction, et pour un classement en échec |
| `cost_estimated` | en USD, arrondi à 6 décimales : `tokens_in` et `tokens_out` × prix au million de `core/config.py` (gpt-6-luna, Data Zone Standard, France Central, contexte court : 0,12 et 0,60) ; 0 en offre gratuite. **Limite** : tout appel est compté à ces prix, le replay compris (ses jetons sont ceux de ses pas, `provider` le dit) et un autre `KB_LLM_MODEL` aussi |

`ts`, `stage`, `failed_check`, `items_dropped`, `items_capped`, `reasoning_tokens` et `http_status`
s'ajoutent à la liste de #156, puis `first_failed_check` (#205), puis `fidelity_rate` (#207), puis
`items_with_subject`, `items_no_suitable_subject` et `items_unanswered` (`classify-2`, #210). En
0.4.0, `items_dropped` devient `items_dropped_before_writing_stage` et `items_uncited`,
`items_removed_by_checks`.

**Jamais** dans une ligne : le texte d'un item ou d'une affirmation, la consigne, la sortie du
modèle, un titre, un auteur, une clé (règle 5 de `poc.md`). Un échec `data_api_*` ne fait aucun appel au modèle, donc
aucune ligne `llm_call` : il va au journal de fonctionnement (sortie d'erreur), avec le
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
   │                              k_b.facts.checked, k_b.facts.found, k_b.claims.removed   (englobe les contrôles)
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
  virgules : `out_of_bounds`, `fact_not_found:<index du fait>:<item>`, `undeclared_identifier`,
  `cited_item_without_fact`, `disguised_text`. Les premiers codes qui tiennent en 2 048 octets sont
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

**Angles morts** : un 401 et un 422 n'ont pas de trace, la route n'étant pas atteinte. Une erreur
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
| `llm_unavailable` | 5xx, connexion refusée ou coupée, après la nouvelle tentative ; autre 4xx, réponse qui ne se décode pas, ou réponse 200 qui n'est pas une complétion lisible (pas du JSON, aucun `choices`, un type faux), sans nouvelle tentative | 502 | `failed_subjects` |
| `llm_timeout` | pas de connexion ou pas de réponse dans le délai du client (#150), sans nouvelle tentative ; ou durée totale de la demande dépassée (`DIGEST_REQUEST_TIMEOUT_SECONDS`), pour chaque sujet pas encore rédigé | 504 | `failed_subjects` |
| `data_api_unavailable` | API de données injoignable, ou 5xx | 502 | — |
| `data_api_timeout` | délai de lecture dépassé | 504 | — |
| `data_api_unauthorized` | 401 de l'API de données : clé `AI_DIGEST` refusée (sans clé, l'API IA ne démarre pas, règle 2 de `poc.md`) | 502 | — |
| `data_api_invalid_response` | réponse hors du schéma attendu | 502 | — |
| `invalid_parameter` | demande mal formée, `window_days` hors bornes | 422 | — |
| `invalid_api_key` | appel sans clé, ou clé inconnue (#156) | 401 | — |
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
   `KB_AI_API_URL`, `http` ou `https`, sans utilisateur, requête ni fragment, par défaut
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
   appel au modèle en cours (environ 20 s de plus, `ai_api/deadline.py`). Aucune nouvelle
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
   et la fiche sont recontrôlés juste avant l'écriture, par un temporaire caché renommé (règle 2 de
   `conventions.md`). Une limite : voir « Limites », ci-dessous.

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
| 1 | l'API IA injoignable (`ai_api_unavailable`), délai dépassé (`ai_api_timeout`), clé refusée (`ai_api_unauthorized`, 401), panne (`ai_api_failed`, 5xx), autre réponse ou réponse hors schéma (`ai_api_invalid_response`) : aucune fiche écrite ; ou un sujet en échec et aucune fiche écrite ; ou une `OSError` au contrôle d'avant la demande |
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

- **Pas de borne de taille** sur la réponse lue : risque accepté par Sabine pour le POC
  (2026-10-21 : le service de K-B, à une adresse qu'elle règle). À poser avant la mise en ligne du
  08/11, dans `core/outbound.py`, commune aux deux clients (`read_bounded_body` et son échéance).
- **Relancer le même jour** après un échec partiel sort en 2 : une fiche du jour existe. Les
  sujets en échec s'écrivent le lendemain, si leurs items restent dans la fenêtre.
- **Le jour contrôlé** avant la demande est celui de l'horloge de `kb` ; celui de la fiche,
  `window.until` de l'API IA. Une demande à cheval sur minuit UTC écrit la fiche du lendemain, et un
  sujet dont la fiche du lendemain existe déjà compte en échec (`sheet_exists`).
- **Un SIGKILL** pendant une écriture laisse un temporaire caché `.AAAA-MM-JJ.md.*.tmp` dans
  `veille/<sujet>/`, comme pour les tops ; Obsidian n'affiche pas un fichier caché.
- **Entre le dernier contrôle et le renommage** (limite acceptée par Sabine pour le POC, le
  2026-10-21, à corriger par #295) : une fiche apparue dans cette fenêtre est remplacée sans
  message (CWE-367) ; un dossier remplacé par un lien y fait écrire hors du coffre (CWE-59, déjà
  accepté pour les tops, registre, fiche 1, « Sécurité »). Seuls deux lancements de l'utilisatrice
  qui se chevauchent peuvent le déclencher ; un texte de source ou du modèle ne le peut pas. À
  corriger au plus tard dès que `kb digest` tourne sans elle (tâche planifiée, conteneur).
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
