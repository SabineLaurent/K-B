# Spécification des fiches de veille

Une fiche de veille regroupe, pour un sujet d'une liste fermée, ce que la veille de K-B a vu sur
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

1. `POST /digests` sur l'API IA, avec une clé (#156) : la demande est validée (section
   « Fenêtre »), avant toute lecture et tout appel au modèle.
2. L'API IA lit la veille de la fenêtre par l'API de données, avec la clé du client `AI_DIGEST`
   (#204) : `GET /items` filtré par `kind=` et plafonné (section « Fenêtre »), puis
   `GET /items/{item_id}` pour chaque item gardé. Elle ne lit pas la base.
3. **Classement** (#205) : le modèle range chaque item dans un sujet, ou le dit « non retenu ».
4. **Rédaction** (#205) : un appel par sujet ; le modèle écrit des affirmations qui citent leurs
   items.
5. **Contrôles** (#206, #207, section « Contrôles ») : le code revalide chaque sortie avant de
   s'en servir.
6. Réponse JSON ; une ligne de métrique par appel au modèle, sur la sortie standard (#156).

L'appel au modèle, sa nouvelle tentative et le modèle de remplacement des tests sont à #150 ; le
vrai modèle (gpt-6-luna sur Azure AI Foundry, décision de Sabine du 2026-10-16 ; déployé le
2026-10-17 sur l'abonnement de son organisme de formation ;
journal ADR, « Modèle des fiches : gpt-6-luna sur l'abonnement de l'organisme de formation ») à
#158. La spec ne dépend d'aucun fournisseur :
elle s'en tient à l'interface compatible OpenAI. L'API IA n'écrit rien qui doive survivre à son redémarrage
(règle 7 de `poc.md`) : les fiches sont rendues, pas gardées.

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

Liste de départ proposée par la session K-B à partir des sources collectées (dépôts suivis,
`etl/sources/tracked_repositories.py` ; éditions TLDR `ai`, `infosec` et `dev`,
`etl/sources/tldr.py` ; arXiv sur la sécurité de l'IA, [specs-collecte.md](specs-collecte.md) ;
catalogue KEV ; alertes GitHub), validée par Sabine le 2026-10-15. Un item qui n'entre dans aucun
sujet est « non retenu » : il n'y a pas de sujet « autre ».

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
| `window_days` (corps de `POST /digests`) | entier JSON | de 1 à 14 | `KB_DIGEST_WINDOW_DAYS` | 422 `invalid_parameter`, avant toute lecture et tout appel au modèle ; `true`, `3.0` et `"3"` sont refusés (pas des entiers) |
| `KB_DIGEST_WINDOW_DAYS` (variable d'environnement) | chiffres seuls | de 1 à 14 | 3, défaut nommé dans `core/config.py` (règle 2 de `poc.md`) | l'API IA ne démarre pas (code de sortie 2, échouer fermé, comme `kb serve`) |

- `since` = l'instant de la demande, en UTC à la seconde, moins `window_days` × 24 h ; il est
  passé à `GET /items?since=…`, et la règle de « quoi de neuf » de l'API de données s'applique :
  la date est celle de la source, pas celle de la collecte.
- **Limite** : les articles TLDR et les entrées KEV sont datés à minuit UTC
  ([specs-api.md](specs-api.md), « Règle de quoi de neuf ») ; selon l'heure de la demande, une
  fenêtre de 3 jours prend 2 ou 3 éditions. Option écartée : arrondir `since` à minuit (une règle
  de plus, et la fenêtre ne dit plus « les N derniers jours »).

### Lecture plafonnée

La lecture et les appels au modèle sont bornés par demande (OWASP API4:2023, consommation de
ressources sans limite). Volume estimé : 110 à 165 items sur 3 jours, 500 à 600 sur 14 (TLDR
≈ 450, arXiv ≈ 45, releases 20 à 60, KEV et alertes quelques-uns).

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
  Le pire cas, 14 appels de 210 s, dépasse 240 s en série comme en parallèle : seule l'échéance
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
- **Appels au modèle** : au plafond, 6 classements ou plus (des lots de 50 items et de 36 000
  caractères de message au plus, `MAX_ITEMS_PER_CLASSIFICATION_CALL` et
  `MAX_CLASSIFICATION_INPUT_CHARS` ; jusqu'à environ 10 quand les titres sont longs), 8
  rédactions (une par sujet) : environ 14 appels, et le double de tentatives au plus avec les
  nouvelles tentatives, soit environ 28. Ce nombre découle du plafond et des sujets : pas de
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
Les bornes de ce document sont vérifiées par le code. Limite : 1 000 valeurs d'`enum` au plus par
schéma (OpenAI, structured outputs) ; au plafond, environ 300 identifiants et 8 sujets, donc
sous la limite.

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

`window_days` est optionnel ; tout autre champ est refusé (422 `invalid_parameter`).

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
  cliquable, car CommonMark et GFM ne font un lien que d'un schéma ou de `www.`.
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
  modèle la présenterait comme une entrée du catalogue. Elle est comptée dans `items_dropped`.
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
  rédaction ; `items_dropped`, ceux laissés hors d'une fiche (au-delà de 60, retirés, ou disparus
  entre la liste et le détail : 404 `item_not_found`). La coupe à 500 du classement n'y est pas
  comptée (presque tous les items y passent) : elle est comptée par appel, dans la ligne de
  métrique. **Limite** : la coupe et le plafond de 60 ne sont comptés que pour un sujet envoyé à
  la rédaction ; un sujet laissé en `llm_timeout` avant l'envoi n'y ajoute rien.
- `items_capped` est vrai s'il reste au moins un item au-delà de `MAX_ITEMS_PER_DIGEST_REQUEST`
  (section « Lecture plafonnée ») ; ces items ne sont pas lus, donc pas comptés.

### Sortie du classement

`response_format` `json_schema`, `strict: true`.

```json
{
  "assignments": [{"item_id": "i12", "subject": "llm_security"}],
  "not_retained": ["i7"]
}
```

| Champ | Contrainte |
|---|---|
| `assignments[].item_id`, `not_retained[]` | `enum` des `item_id` envoyés dans cet appel |
| `assignments[].subject` | `enum` des sujets de `core/config.py` |
| ensemble | chaque item envoyé apparaît **au plus une fois**, dans `assignments` ou dans `not_retained` ; un item absent est compté « non retenu » par le code |

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

Le modèle ne rend pas de `not_retained` à la rédaction : le code le calcule, items envoyés moins
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
      "not_retained": [7],
      "claims_removed": 1,
      "items_uncited": [51]
    }
  ],
  "failed_subjects": [{"subject": "models", "stage": "write", "error": "llm_timeout"}],
  "not_retained": [3, 9],
  "items_in": 41,
  "items_truncated": 2,
  "items_dropped": 0,
  "items_capped": false
}
```

| Champ | Contenu |
|---|---|
| `request_id` | identifiant de la demande (UUID), repris par chaque ligne de métrique |
| `window` | `days`, et `since` et `until` en UTC, au format des dates de la base ; quand `items_capped` est vrai, `capped_kind`, la sorte coupée, et `covered_after`, la date de son premier item laissé de côté (borne exclue) ; nuls sinon (section « Lecture plafonnée ») |
| `digests` | une fiche par sujet rédigé ; un sujet sans item n'a pas de fiche |
| `digests[].claims` | les affirmations gardées après la fidélité, sans leurs `facts` (contrôle interne) |
| `digests[].sources` | `item_id`, `kind`, `title`, `url` de chaque item des affirmations gardées, lus dans l'API de données, **jamais dans la sortie du modèle** ; une `url` qui ne commence ni par `http://` ni par `https://` est rendue nulle |
| `digests[].not_retained` | les items envoyés pour ce sujet qu'aucune affirmation du modèle ne cite, calculés par le code |
| `digests[].claims_removed` | affirmations retirées par la fidélité |
| `digests[].items_uncited` | items du sujet qui ne sont plus cités après les retraits de la fidélité |
| `failed_subjects` | chaque sujet en échec, son étape (`stage` : `write`, la rédaction) et son état nommé |
| `not_retained` | items non retenus au classement, ou absents de sa sortie |
| `items_in`, `items_truncated`, `items_dropped`, `items_capped` | compteurs de la section « Entrée du modèle » |

**Limite** : `sources[].title` est une donnée de source, pas une sortie du modèle ; le filtre du
Markdown ne s'y applique pas. L'échapper revient à qui écrira la fiche dans le coffre (`kb`, plus
tard).

**Limite** : le `text` d'une affirmation peut recopier une adresse mail d'un item (section
« Entrée du modèle » : une adresse mail n'est pas masquée) ; elle revient dans la
réponse, car le contrôle 6 ne la refuse pas.

Une erreur rend `{"error": "<état>"}`, comme l'API de données (section « États nommés »).

## Contrôles

Chaque sortie du modèle passe ces contrôles **dans cet ordre**, avant tout usage ; le premier qui
échoue nomme l'échec. Le mode strict demande au fournisseur de suivre le schéma ; le code ne s'y
fie pas et revérifie tout (défense en profondeur ; OWASP LLM01:2026 : valider le format de sortie
par du code déterministe).

| N° | Contrôle | Refuse | `failed_check` |
|---|---|---|---|
| 1 | `finish_reason` (liste blanche) | `stop` passe ; `length` → `llm_truncated` ; `content_filter` → `llm_content_filtered` ; toute autre valeur → `llm_invalid_output` (échouer fermé sur une valeur inconnue, `tool_calls` compris) | `content_filter` pour un filtrage ; `finish_reason` pour une valeur hors liste |
| 2 | **Schéma** | un texte qui n'est pas du JSON, un champ en trop (`extra="forbid"`), un type faux, une borne de structure dépassée (plus de 12 affirmations, `item_ids` hors de 1 à 5) | `schema` |
| 3 | **Sujets** | un sujet hors de la liste de `core/config.py` | `subject` |
| 4 | **`item_id`** | un identifiant qui n'a pas été envoyé dans **cet** appel (un item inventé, ou d'un autre sujet) ; un `facts[].item_id` hors des `item_ids` de son affirmation | `item_id` |
| 5 | **Complétude** (classement) | un item présent deux fois dans la sortie du classement ; un item absent n'est pas un échec : il est compté « non retenu » | `completeness` |
| 6 | **Markdown** (rédaction) | un `text` qui contient `(?i)[a-z][a-z0-9+.-]*://`, `(?i)www\.`, `![`, `[[`, `](`, `]:` ou `<[a-zA-Z/!?]` | `markup` |
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

### Fidélité

Une fiche ne dit que ce que disent ses items (#207).

**Normalisation**, avant toute recherche, du `text`, des faits et des champs de l'item : Unicode
NFKC, `casefold`, retrait des caractères invisibles (catégorie Unicode `Cf` : U+200B, U+00AD,
U+2060…), espaces réduites à une seule, tirets Unicode (U+2010 à U+2015, U+2212) ramenés à `-`,
apostrophes et guillemets typographiques (U+2018, U+2019, U+201C, U+201D) ramenés à `'` et `"`.

**Faits CVE et GHSA.** Les motifs s'appliquent après la normalisation :

- CVE : `(?i)CVE[\s-]*\d{4}[\s-]*\d{4,}` ;
- GHSA : `(?i)GHSA[\s-]*[0-9a-z]{4}[\s-]*[0-9a-z]{4}[\s-]*[0-9a-z]{4}`.

Un fait qui **contient** l'un de ces motifs est un fait CVE ou GHSA, quelle que soit son écriture
(`cve 2026-1234` compris). Il doit être **égal**, une fois ramené à sa forme canonique
(`CVE-AAAA-NNNN`, `GHSA-xxxx-xxxx-xxxx`), au `cve_id` ou au `ghsa_id` de l'item qu'il cite, jamais
trouvé dans un texte libre. Un article TLDR n'a pas de tel champ : il ne porte pas de fait CVE ; la
fiche cite la CVE par l'entrée KEV ou par l'alerte, si elles sont dans la fenêtre (décision de
Sabine du 2026-10-15). Comme tout fait, un fait CVE ou GHSA doit aussi figurer dans le `text` de
son affirmation ; et tout motif CVE ou GHSA écrit dans un `text` doit être déclaré comme fait.

**Autres faits.** Chaque `facts[].value` doit figurer dans le `text` de son affirmation **et** dans
la valeur de l'un des champs où la fidélité cherche, pour l'item qu'elle cite (tableau de la
section « Entrée du modèle ») : champ par champ, jamais dans une concaténation de champs, jamais
dans `kind`, `item_id` ni `cve_listed_in_cisa_kev`. Une valeur est trouvée seulement entre deux
**limites** : juste après elle, ni lettre ni chiffre, ni `.` ou `-` suivi d'une lettre ou d'un
chiffre ; juste avant, la même règle (ni lettre ni chiffre, ni `.` ou `-` précédé d'une lettre ou
d'un chiffre). Ainsi `1.2` n'est pas trouvé dans `1.2.9`, ni `CVE-2026-1234` dans
`CVE-2026-12345`.

**Chaque item cité porte un fait.** Chaque item de `item_ids` porte au moins un fait trouvé : un
item ne peut pas se faire citer à côté d'une affirmation qui ne dit rien de lui.

**Bornes d'affirmation.** Un `text` hors de 1 à 400 caractères, un `value` hors de 3 à 120, ou un
nombre de faits hors de 1 à 10 retire l'affirmation (section « Sortie de la rédaction »).

**Ce qu'est un fait.** La consigne limite un fait à un identifiant, une version, un nombre ou un
nom propre, recopié mot pour mot : la fiche est en français, l'item souvent en anglais, et une
expression traduite ne serait plus trouvée. Le code ne vérifie pas cette catégorie : il cherche la
valeur, c'est tout.

Une affirmation qui manque à l'une de ces règles est **retirée et comptée** (`claims_removed`) ;
ce n'est pas un échec. Un item qui n'est plus cité après ces retraits passe dans `items_uncited`.
Si toutes les affirmations d'un sujet sont retirées, la fiche est rendue sans affirmation : c'est
ce qui a été observé. `fidelity_rate` = `facts_found` / `facts_checked`.

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

| Champ | Contenu |
|---|---|
| `ts` | date de la ligne, ISO 8601 UTC à la seconde (`2026-10-15T09:00:00Z`, règle 3 de `conventions.md`) |
| `event` | `llm_call` |
| `request_id` | celui de la réponse |
| `stage` | `classify` ou `write` |
| `subject` | le sujet rédigé ; nul au classement |
| `provider`, `model` | lus dans la configuration (#150) |
| `prompt_version` | constante de la consigne utilisée (`classify-1`, `write-1`), changée à la main avec elle |
| `items_in` | items envoyés dans l'appel |
| `items_truncated` | items de cet appel dont un champ est coupé |
| `items_dropped`, `items_capped` | compteurs de la demande (section « Entrée du modèle ») ; sur la première ligne de classement de la demande, nuls ailleurs |
| `input_chars` | longueur du message utilisateur |
| `tokens_in`, `tokens_out` | `usage` rendu par le fournisseur |
| `reasoning_tokens` | jetons de raisonnement rendus par le fournisseur, attendus à 0 avec `reasoning_effort: "none"` ; nul s'il ne les rend pas |
| `data_fetch_ms` | durée de la lecture par l'API de données ; sur la première ligne de classement de la demande, nul ailleurs |
| `llm_ms`, `check_ms` | durée des appels au modèle, nouvelle tentative et attente avant elle comprises ; durée des contrôles |
| `attempts` | 1 ou 2 |
| `outcome` | `ok`, ou l'état `llm_*` de l'appel |
| `finish_reason` | celui de la dernière tentative, coupé à 64 caractères ; nul s'il manque |
| `http_status` | le statut HTTP de la dernière réponse du fournisseur (un 401 de clé refusée se distingue ainsi d'un 503) ; nul sans réponse (délai, connexion refusée) |
| `schema_valid` | la dernière tentative a passé le contrôle 2 |
| `failed_check` | le contrôle qui a refusé la dernière tentative (`content_filter`, `finish_reason`, `schema`, `subject`, `item_id`, `completeness`, `markup`) ; nul si `ok` |
| `first_failed_check` | le contrôle qui a refusé la première tentative, quand une seconde a suivi ; nul sinon (#205, `LlmCall`, constat de #158 : le motif de la première tentative était perdu) |
| `facts_checked`, `facts_found`, `claims_removed`, `items_uncited` | compteurs de la fidélité (rédaction) ; nuls au classement |
| `cost_estimated` | jetons × prix au million lus dans `core/config.py` ; 0 en offre gratuite |

`ts`, `stage`, `failed_check`, `items_dropped`, `items_capped`, `reasoning_tokens` et `http_status`
s'ajoutent à la liste de #156, puis `first_failed_check` (#205).

**Jamais** dans une ligne : le texte d'un item ou d'une affirmation, la consigne, la sortie du
modèle, un titre, un auteur, une clé (règle 5 de `poc.md`). Un échec `data_api_*` ne fait aucun appel au modèle, donc
aucune ligne `llm_call` : il va au journal de fonctionnement (sortie d'erreur), avec le
`request_id`.

## États nommés

| État | Quand | Le classement échoue (toute la demande) | La rédaction d'un sujet échoue |
|---|---|---|---|
| `llm_invalid_output` | contrôles 2 à 6, ou `finish_reason` hors liste, deux fois | 502 | le sujet va dans `failed_subjects`, avec son étape (`stage`) |
| `llm_truncated` | `finish_reason` `length` ; pas de nouvelle tentative (même entrée, même modèle figé : même sortie attendue) | 502 | `failed_subjects` |
| `llm_content_filtered` | `finish_reason` `content_filter` : le filtre de contenu du fournisseur a retenu la sortie (celui d'Azure peut réagir aux textes sur le jailbreak et l'injection, sujets de la veille) ; ou un 400 dont `error.code` vaut `content_filter` : il a retenu l'entrée ; pas de nouvelle tentative (même entrée) | 502 | `failed_subjects` |
| `llm_rate_limited` | 429 du fournisseur, après la nouvelle tentative ; ou un 429 dont le `Retry-After` dépasse `LLM_RETRY_AFTER_MAX_SECONDS`, sans nouvelle tentative | 503, avec `Retry-After` | `failed_subjects`, et chaque sujet suivant, sans envoi (#205) |
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
  (`items_dropped`).
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
  sorties fautives de suite (un doublon, `completeness` ; une sortie sans fin, `llm_truncated`).
  Non observé par #158 (aucun filtre sur 20 appels réels) ; renvoyé à #206 (décision de Sabine du
  2026-10-17). Option écartée : couper le lot en deux et recommencer pour isoler l'item (jusqu'à
  environ 12 appels de plus, et un contrat changé).
- Une fenêtre sans item rend 200 avec `digests` vide, sans appel au modèle.

## Sources

Consultées le 2026-10-15.

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
