# Épingler le jeu de référence de `POST /digests` sur le modèle de production

- **Date** : 2026-11-20
- **Branche** : `test/reference-set-on-production-model`
- **Issue** : #520
- **Fichiers principaux** : `tests/ai_api/test_digests_reference.py` (le test qui épingle le jeu, et ceux du refus
  de l'outil), `tests/ai_api/digests_reference.py` (l'enregistrement : son refus nomme maintenant chaque erreur de
  transport). `tests/fixtures/digests_reference.json` (le jeu, réenregistré le 2026-11-20 à 09:33 UTC) ; `docs/fiches-veille.md` (ses mesures face au 08/11).
- **Série** : le jeu et son outil viennent de
  [2026-11-08-enregistrer-un-jeu-de-reference-des-fiches.md](2026-11-08-enregistrer-un-jeu-de-reference-des-fiches.md) ;
  le passage de K-B à gpt-6.1-sol, de [2026-11-18-passer-k-b-a-gpt-6-1-sol.md](2026-11-18-passer-k-b-a-gpt-6-1-sol.md).

## Le pourquoi

Le jeu de référence (#479) est l'enregistrement de vraies réponses d'un modèle à `POST /digests`. La CI le rejoue
sans réseau ni coût. Celui du 08/11 a été enregistré sur gpt-6-luna, effort `none`. Depuis le banc de C7, la
production tourne sur gpt-6.1-sol, effort `low` : le jeu ne mesure donc plus ce qui est livré.

Décision de Sabine du 2026-11-20 : le jeu se réenregistre sur gpt-6.1-sol, avec les consignes en production
(`write-1` pour la rédaction). Pourquoi : le jeu teste ce qui est livré. La consigne `write-2` et la borne commune
(#519) sont renvoyées à après la certification.

L'enregistrement est un appel payant, que seule Sabine lance. Cette PR prépare tout ce qui peut l'être avant lui :
- un test qui dit sur quoi le jeu doit être enregistré, et qui échoue tant qu'il ne l'est pas ;
- la commande exacte de l'enregistrement.

## Le comment

### 1. Ce que le jeu garde de chaque appel

L'outil d'enregistrement écrit, pour chaque appel, l'étape, la consigne, le modèle qui a répondu et l'effort
(`tests/ai_api/digests_reference.py:344-347`) :

```python
            prompt_version=PROMPT_VERSION_BY_STAGE[stage],
            model=self.settings.model,
            response_model=read_response_model(body),
            reasoning_effort=self.settings.reasoning_effort,
```

Ces quatre champs suffisent : le test nouveau n'a besoin ni du réseau ni du rejeu. Il lit le jeu par
`read_reference`, la même lecture que les autres tests du fichier.

`response_model` est le nom que le fournisseur renvoie dans sa réponse. `model` est le nom du déploiement Azure
(`KB_LLM_MODEL`), que Sabine choisit. Le test épingle `response_model` : c'est le seul champ qui dit quel modèle a
vraiment répondu.

### 2. Les valeurs épinglées, écrites telles quelles

`tests/ai_api/test_digests_reference.py:30-36` :

```python
PRODUCTION_MODEL = re.compile(r"gpt-6\.1-sol(-\d{4}-\d{2}-\d{2})?")
PRODUCTION_REASONING_EFFORT = "low"
RECORDED_PROMPT_VERSION_BY_STAGE = {"classify": "classify-2", "write": "write-1"}
```

- **Le modèle** : un motif, car le nom que renvoie Azure pour gpt-6.1-sol n'est écrit nulle part dans le dépôt.
  Pour gpt-6-luna, c'était `gpt-6-luna-2026-09-22`, le nom suivi de la date de version. Le motif accepte le nom
  seul ou suivi d'une date, et refuse une variante (`gpt-6.1-sol-mini`).
- **L'effort** : `low`, celui que pose `infra/main.bicep:304`.
- **Les consignes** : `classify-2` et `write-1`, celles du code de production au 20/11.

Ce sont des valeurs écrites en dur, pas `WRITING_PROMPT_VERSION` ni `CLASSIFICATION_PROMPT_VERSION`. Si le test
lisait ces constantes, le passage à `write-2` (#519) le ferait échouer alors que le jeu n'a pas changé. Or juger
qu'un jeu est périmé revient à #482 (`MEMORY.md`, « Jeu de référence »).

### 3. Trois assertions, chacune lisible en échec

`tests/ai_api/test_digests_reference.py:90-103`. La première rend la liste des modèles refusés, pas un booléen :

```python
    assert [
        call.response_model
        for call in calls
        if not PRODUCTION_MODEL.fullmatch(call.response_model or "")
    ] == []
```

En échec, pytest affiche donc le nom fautif (`'gpt-6-luna-2026-09-22'`). Un `all(...)` n'aurait affiché que
`False`. Un `response_model` absent (`None`) devient `""` et il est refusé : un jeu dont aucune réponse ne nomme
son modèle ne prouve rien.

La troisième compare l'ensemble des couples (étape, consigne) à `{("classify", "classify-2"), ("write",
"write-1")}`. Elle refuse une consigne de brouillon, et aussi une étape absente : un jeu sans rédaction ne
passerait pas.

### 4. Le nouveau jeu remplace l'ancien par suppression

L'outil refuse d'écraser le jeu (`tests/ai_api/digests_reference.py:409-413`) :

```python
    if REFERENCE_PATH.exists():
        print(
            f"{REFERENCE_PATH.name}: already recorded, no call sent; remove it to record again",
```

C'est voulu : une relance par erreur ne coûte rien et ne détruit rien. Le message dit déjà comment réenregistrer.
Sabine supprime le jeu par `git rm`, puis lance l'outil. L'ancien jeu reste dans l'historique de git (commit
`d10f5bf9`), et ses mesures sont déjà écrites dans `docs/fiches-veille.md` et dans la note du 08/11.

### 5. Un premier essai refusé, et un refus qui nomme ses erreurs

Le 20/11 à 01:50 UTC, Sabine a lancé l'enregistrement. Le classement et deux rédactions sont passés en 200. La
rédaction d'`agent_frameworks` a fini en `llm_unavailable` : 2 tentatives en 2 101 ms, dont les 2 s d'attente avant
la seconde (`LLM_RETRY_WAIT_SECONDS`), donc une cinquantaine de ms chacune, sans statut HTTP. L'outil a refusé le
jeu : `not recorded: transport errors: 2`. Rien n'a été écrit, et l'appel a coûté environ 0,02 USD (la somme des
`cost_estimated`).

Ce refus ne permettait pas de trouver la cause : l'outil comptait les erreurs sans les nommer. Il les décrit
maintenant (`tests/ai_api/digests_reference.py:366-377`) :

```python
    while link is not None and len(classes) < MAX_ERROR_CHAIN_LINKS:
        classes.append(name_error_class(link))
        link = link.__cause__ or link.__context__
    if link is not None:
        classes.append("\u2026")
```

- **La chaîne des causes, pas seulement l'erreur.** httpx2 relance l'erreur de httpcore2 sous le même nom. Sur une
  connexion refusée, le refus lit donc `httpx2.ConnectError from httpcore2.ConnectError from
  ConnectionRefusedError`. Un seul niveau de cause aurait dit « ConnectError from ConnectError », sans la cause
  réelle.
- **La classe et son paquet de tête, jamais le message** (`name_error_class`, l. 380-384). Le message d'une erreur
  de httpx2 peut porter l'URL du point du fournisseur. Le paquet dit quelle bibliothèque a levé quel maillon ;
  `builtins` est omis.
- **Une chaîne bornée, et dite coupée.** 5 maillons au plus (`MAX_ERROR_CHAIN_LINKS`) ; s'il en reste, la chaîne
  finit par ` from …`, pour qu'on ne prenne pas le cinquième maillon pour la racine.
- **Le statut reçu avant l'erreur** (l. 329-339). Il est retenu dès que le fournisseur a répondu. Une erreur
  pendant la lecture du corps se lit `… after status 200`, et une erreur de connexion n'a pas de statut.

### 6. La cause nommée, puis le jeu enregistré

La relance de 09:10 UTC a été refusée à son tour, mais le refus nommait sa cause :
`httpx2.ConnectError from httpcore2.ConnectError from ssl.SSLEOFError`, deux fois. La connexion a été fermée
pendant la poignée de main TLS, avant le premier octet HTTP : ni clé ni requête ne sont parties (0 jeton, aucun
statut). `llm_ms` compte l'attente de 2 s entre les deux tentatives (`llm_client.py:257`, `:319`, `:325`) :
chaque tentative a duré environ 67 ms, et celles de 01:50 environ 50 ms.

Une vérification sans appel au modèle a ensuite localisé la cause. Elle ouvre 35 connexions neuves vers l'hôte du
fournisseur, avec le transport de l'outil, et envoie `GET /` sans en-tête ni corps :

| Réseau | Connexions qui aboutissent |
|---|---|
| Réseau fixe habituel (09:14, 09:21, 09:23) | 4, 3 et 5 sur 35 |
| Réseau mobile, par le téléphone (09:19) | 34 sur 35 |
| Réseau mobile, par une box 4G (09:31) | 35 sur 35 |

Même machine, même Python, même outil : seul le réseau change. La cause est donc ce réseau fixe, qui coupait
environ 9 connexions TLS sur 10 vers ce point, alors que le jeu du 08/11 y avait été enregistré sans erreur. Ni
le client de `src/`, ni l'outil, ni Azure. Le jeu a été enregistré à 09:33 UTC par la box 4G : 4 appels, chacun
répondu à sa première tentative. Ses mesures, face à celles du 08/11, sont dans `docs/fiches-veille.md`
(« Le jeu de référence, du 08/11 au 20/11 »).

## La commande de Sabine

Dans `/Users/sabine/REPO_GIT/worktrees-temp/K-B_banc`, qui n'a pas de `.env` : celui du dépôt principal sert.

```sh
git switch test/reference-set-on-production-model
# Avant de lancer : le KB_LLM_MODEL du .env nomme le déploiement de gpt-6.1-sol ; sinon le test échoue après un appel payé.
git rm -q tests/fixtures/digests_reference.json
KB_LLM_REASONING_EFFORT=low KB_LLM_SEND_PROMPT_CACHE_OPTIONS=true uv run --env-file /Users/sabine/REPO_GIT/K-B/.env python tests/ai_api/digests_reference.py
```

- **Les deux variables devant `uv run`** : avec uv 0.13.6, une variable du shell l'emporte sur la même variable
  de `--env-file`. Je l'ai vérifié le 20/11 sur un fichier d'essai du scratchpad : `from_shell` a gagné sur
  `from_file`. Elles imposent ce qui tourne en production, quel que soit le `.env` :
  - l'effort `low` (`infra/main.bicep:304`) ;
  - l'envoi des options de cache de prompt. C'est le défaut (`src/k_b/core/config.py:271`), et `main.bicep` ne pose
    pas la variable.
- **`KB_LLM_MODEL` n'est pas forcé** : c'est le nom du déploiement, que seule Sabine connaît. D'où la ligne de
  vérification. Le 20/11, Sabine a vérifié que celui de son `.env` nomme bien gpt-6.1-sol.
- **Sortie attendue** : `digests_reference.json: 6 items, N calls`. Le 08/11, N valait 3 : un classement et deux
  rédactions.
- **Si l'outil refuse** (`not recorded: …`) : rien n'est écrit. `git restore --staged --worktree
  tests/fixtures/digests_reference.json` rend le jeu du 08/11.

## Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Remplacer l'ancien jeu | Le supprimer par `git rm` : l'outil le prévoit, aucun code | Un drapeau `--replace` : du code pour un seul usage, qui affaiblit la garde contre une relance par erreur. Garder les deux jeux : deux rejeux à tenir, et le critère de #520 n'en demande qu'un |
| Épingler la consigne | Des valeurs écrites en dur | Les constantes du code : un `write-2` ferait échouer le test sans que le jeu ait changé, alors que la péremption revient à #482 |
| Épingler le modèle | `response_model`, le nom renvoyé par le fournisseur | `model` : c'est le déploiement choisi par Sabine, il ne dit pas quel modèle a répondu |
| Forme du motif | Nom seul ou suivi d'une date (revue, constat 3) | Tout suffixe : une variante `-mini` passait |
| Code de `src/` | Aucun | Le jeu teste ce qui est livré, sans rien y changer |
| Après le refus de 01:50 | Nommer chaque erreur de transport dans le refus, avant toute relance (écart au plan « sans code », tranché par time-knight, règle de Sabine du 08/11) | Relancer tel quel : un nouvel échec n'aurait rien dit de plus |
| Ce que le refus nomme | La chaîne des classes jusqu'à la racine, bornée à 5 maillons | Un seul niveau de cause : « ConnectError from ConnectError ». Le message de l'erreur : il peut porter l'URL du fournisseur |
| Un contexte masqué par `raise … from None` | Suivi quand même (revue 2, constat 3 écarté) | L'ignorer comme le fait une trace Python : un outil de diagnostic dit ce qu'il observe, et aucun message n'apparaît |

La revue (`/code-review high`) a rendu 6 constats. Le tri est de time-knight, par délégation de Sabine du 15/10 :
- corrigés : 3 (le motif), 5 (le commentaire disait que `main.bicep` fixe le modèle, alors qu'il ne fixe que
  l'effort), 6 (`classify-2` épinglé aussi) ;
- écartés : 1 (le test est rouge avant le jeu : c'est voulu, la PR reste en brouillon) ;
- reportés après l'enregistrement : 2 (les comptes `[26, 26, 14, 14]`) et 4 (la documentation et `MEMORY.md`).

La seconde revue (`/code-review high` sur le refus qui nomme ses erreurs) a rendu 6 constats, même tri :
- corrigés : 2 (le paquet de tête de chaque classe), 4 (une chaîne coupée le dit), 5 (la borne et le passage par
  `__context__` testés), 6 (le premier transport du test fermé) ;
- écartés : 1 (le test rouge, voulu) et 3 (le contexte masqué, voir le tableau).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/ai_api/test_digests_reference.py` → 1 failed, 4 passed ; `AssertionError: assert ['gpt-6-luna-...a-2026-09-22'] == []` | Le test échoue sur le jeu du 08/11, à cause de son modèle |
| Les trois assertions essayées une à une sur le jeu du 08/11 → modèle refusé, effort refusé (`none`), consignes acceptées | Le jeu du 08/11 a déjà `classify-2` et `write-1` : seuls le modèle et l'effort le séparent de la production |
| Le motif essayé sur des noms → `gpt-6.1-sol` et `gpt-6.1-sol-2026-09-29` acceptés ; `gpt-6.1-sol-mini` et `gpt-6-luna-2026-09-22` refusés | Le motif tient le modèle sans ses variantes |
| L'essai de Sabine, 01:50 UTC → `not recorded: transport errors: 2` | L'outil refuse un jeu dont un appel n'a pas eu de réponse, et n'écrit rien |
| `test_a_transport_error_is_refused_by_its_classes_and_its_status_never_its_message`, rouge avant le code (`'transport errors: 2' == …`), vert après | Le refus nomme chaque erreur, et le statut reçu avant elle ; il ne contient pas l'URL des messages |
| `test_a_chain_of_causes_is_named_through_its_contexts_and_cut_after_five_links` | Une chaîne de 5 maillons est entière, une de 6 finit par ` from …` ; `__context__` est suivi |
| Une vraie connexion refusée (`https://127.0.0.1:1`) → `transport errors: 1 (httpx2.ConnectError from httpcore2.ConnectError from ConnectionRefusedError)` | Sur une vraie erreur de httpx2, la racine apparaît |
| Rejeu en local (scratchpad) : 3 rédactions en parallèle sur un faux fournisseur en HTTP, 3 essais → 0 erreur de transport | Le parallèle de l'outil ne suffit pas à causer l'erreur de 01:50 (sans TLS : pas Azure) |
| `uv run pytest` → 1 failed, 5630 passed, 365 deselected ; le seul échec est le test qui épingle le jeu | Rien d'autre n'est cassé |
| `uv run ruff check --no-cache`, `ruff format --check`, `uv run mypy --strict` → verts | Les contrôles du dépôt passent |
| La relance de Sabine, 09:10 UTC → `transport errors: 2 (httpx2.ConnectError from httpcore2.ConnectError from ssl.SSLEOFError, …)`, 0 jeton | Le refus nomme sa cause : une connexion fermée pendant la poignée de main TLS, avant tout envoi HTTP |
| La vérification sans appel au modèle (scratchpad, `probe_tls.py`) → réseau fixe 4, 3 et 5 connexions sur 35 ; réseaux mobiles 34 et 35 sur 35 | La coupure suit le réseau, pas la machine ni l'outil |
| L'enregistrement de 09:33 UTC → `digests_reference.json: 6 items, 4 calls`, chaque appel `attempts: 1`, `outcome: ok` | Le jeu porte gpt-6.1-sol, effort `low`, sans nouvelle tentative ni échec |
| Après l'enregistrement : `uv run pytest` → 5631 passed, 365 deselected ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` → verts | Le test d'épinglage passe sur le nouveau jeu, le rejeu aussi, avec les comptes `[26, 26, 26, 26]` |

## Ce que tu dois pouvoir défendre

- **Pourquoi un test rouge dans une PR ?** Il dit ce que le jeu doit être avant qu'il existe : c'est le test
  d'abord. La PR reste en brouillon jusqu'à l'enregistrement, qui le fait passer sans toucher au code.
- **Pourquoi ne pas lire `WRITING_PROMPT_VERSION` ?** Le test vérifie le jeu, pas le code. Si le code passe à
  `write-2`, le jeu reste enregistré en `write-1`. Le dire périmé revient à #482
  (`test_digests_reference.py:30-33`).
- **Et si le `.env` nommait encore gpt-6-luna ?** L'appel serait payé, puis le test échouerait sur
  `response_model`, et le jeu ne passerait pas la CI. D'où la ligne de vérification avant la commande.
- **Que contrôle ce test de la production elle-même ?** Rien. Il ne lit ni `infra/main.bicep` ni l'Azure en
  ligne. Si la production change de modèle ou d'effort, le test passe toujours, et c'est une décision humaine
  de réenregistrer.
- **Pourquoi ne pas citer le message de l'erreur ?** Il peut porter l'URL du point du fournisseur, que le dépôt
  public ne doit pas montrer dans une sortie recopiée. Les classes suffisent à distinguer une connexion refusée,
  coupée ou un échec du TLS (`digests_reference.py:366-384`).
- **Quelles données partent chez Azure ?** Les mêmes que le 08/11 : les champs de 6 items sous CC0 1.0, sans
  auteur. gpt-6.1-sol est déjà nommé comme destinataire au registre des traitements.

## Zones non vérifiées

- La cause des 2 erreurs de transport de 01:50 : non nommée, car l'outil ne nommait pas encore ses erreurs.
  Elles ont la forme de celles de 09:10 (environ 50 ms par tentative, sans statut), sur la même machine ; le
  réseau de cet essai n'est pas relevé. Que ce soit la même coupure TLS reste une hypothèse.
- Ce qui coupe les connexions dans le réseau fixe (la box ou le réseau de l'opérateur) : non cherché, hors de
  #520.
- Le coût réel de l'enregistrement : K-B l'estime à 0,0228 USD (somme des `cost_estimated` des 4 appels, aux prix de
  `src/k_b/core/config.py`) ; la facture d'Azure n'a pas été lue.
- La variance du modèle : chaque jeu est un seul enregistrement. L'écart au 08/11 compare deux sorties, pas deux
  moyennes ; une seconde sortie de gpt-6.1-sol pourrait retirer des affirmations.

## Ce qui reste

- Fait dans cette PR, après l'enregistrement de 09:33 UTC :
  - le jeu committé : `response_model` vaut `gpt-6.1-sol-2026-09-29`, que le motif accepte ; aucune rédaction
    coupée, aucune nouvelle tentative, aucun sujet en échec ;
  - les comptes du test de fidélité passés à `[26, 26, 26, 26]`, et le test renommé
    `test_the_facts_of_the_set_are_all_in_their_item_and_in_their_text`, car son ancien nom disait le contraire ;
  - les mesures face au 08/11 dans `docs/fiches-veille.md`, « Le jeu de référence, du 08/11 au 20/11 » ;
  - `MEMORY.md`, « Jeu de référence » : gpt-6.1-sol, effort `low`, `classify-2` et `write-1`.
- Hors de cette PR : #519 (`write-2` et la borne commune), après la certification ; #482 (la péremption du jeu et
  ses seuils) ; la coupure TLS du réseau fixe, qui n'est pas un défaut de K-B.
