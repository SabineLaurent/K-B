# Ranger l'API IA par rôle, comme l'API de données

- **Date** : 2026-10-18
- **Branche** : `refactor/ai-api-by-role`
- **Issue** : #242
- **Fichiers principaux** : `src/k_b/ai_api/` (`connectors/`, `stages/`, `digests.py`,
  `deadline.py`, `watch_items.py`), `tests/test_module_dependencies.py`,
  `docs/ADR/journal-decisions-projet.md` (2026-10-18, « API IA : organisation par rôle »)
- **Série** : reprend le plan de [l'API de données](2026-10-14-servir-la-liste-par-une-api-locale.md)
  (#184, `data_api/` rangé par rôle), et suit [la lecture de la veille par l'API de
  données](2026-10-15-lire-la-veille-par-l-api-de-donnees.md) (les modules déplacés ici).

## Le pourquoi

`src/k_b/ai_api/` avait douze fichiers à plat. Ils mêlaient trois rôles : parler aux services
extérieurs (le modèle, l'API de données), régler ces connexions, et enchaîner les étapes qui
font une fiche. `src/k_b/data_api/` est rangé par rôle depuis #182 : un dossier par rôle, un
fichier par entité, où l'on voit ce qui est où d'un coup d'œil. C'est l'organisation apprise en
DWWM, et Sabine l'a voulue pour l'API IA aussi (décision du 17/10). Le journal ADR l'avait
annoncé : il écartait les fichiers à plat pour `data_api` « quand l'API IA reprendra le même
plan ».

Le rangement est fait **maintenant**, avant #156 (la couche HTTP de l'API IA) et #206. Sinon,
le code nouveau de ces issues aurait été écrit à plat, puis déplacé. Et c'est un **déplacement
seul** : aucune logique ne change, pour qu'un relecteur n'ait que des renommages à lire.

## Le comment

### 1. Le plan : deux dossiers et trois modules à la racine

```
src/k_b/ai_api/
├── digests.py      le parcours : classe, rédige, assemble
├── deadline.py     l'échéance d'une demande
├── watch_items.py  l'item de veille tel que l'API IA le lit
├── connectors/     outbound, llm_replay, llm_settings, llm_client,
│                   data_api_settings, data_api_client
└── stages/         classification, writing
```

- `connectors/` : tout ce par quoi l'API IA sort d'elle-même, avec les réglages de ces
  connexions. Chaque module y joue le rôle d'une *Gateway* au sens de Martin Fowler : « An object
  that encapsulates access to an external system or resource » (catalogue de Fowler, consulté le
  2026-10-18, cité au journal ADR).
- `stages/` : les étapes qui appellent le modèle (classer, rédiger).
- La racine garde le parcours (`digests.py`), ce que tout le monde utilise (`deadline.py`,
  `watch_items.py`) et, après #156, la couche HTTP au plan de `data_api` (`app.py`, `routers/`,
  `schemas/`, `errors.py`, `dependencies.py`, `health.py`, `request_log.py`).

Les noms de fichiers ne changent pas, et `tests/ai_api/` reste à plat, comme `tests/data_api/`.

### 2. Un déplacement que Git reconnaît comme renommage

Chaque fichier est déplacé par `git mv`, un commit par dossier (`3e05acc` pour `connectors/`,
`806e578` pour `stages/`). Dans ces fichiers, seules les lignes d'import changent. Git compare
donc l'ancien et le nouveau fichier et les voit comme un seul fichier renommé, avec leur taux de
ressemblance (`git diff -M --summary main...806e578`) :

```
 rename src/k_b/ai_api/{ => connectors}/llm_client.py (99%)
 rename src/k_b/ai_api/{ => connectors}/llm_replay.py (100%)
 rename src/k_b/ai_api/{ => stages}/classification.py (98%)
```

100 % : aucune ligne n'a changé (`llm_replay`, `outbound` n'importent rien d'`ai_api`). 96 à
99 % : seules les lignes d'import ont changé, réordonnées par `ruff` (règle `I`), qui range
`ai_api.connectors…` avant `ai_api.deadline` dans l'ordre alphabétique.

Il y a deux pièges, qu'un remplacement automatique ne voit pas : l'import **par le paquet**.
`from k_b.ai_api import classification, watch_items` (`tests/ai_api/test_digests.py:14` sur
`main`) importe deux modules qui ne sont plus au même endroit. Il a été coupé à la main en deux
lignes. Les chemins cités en commentaire et dans la doc suivent (`core/config.py`,
`.env.example`, `docs/fiches-veille.md`, `docs/registre-traitements.md`). Les entrées passées du
journal ADR et des notes ne sont pas réécrites : un journal dit ce qui était vrai à sa date.

### 3. Le sens des imports, tenu par un test

Ranger ne suffit pas : il faut que le rangement ne se défasse pas. Le test place chaque module
dans une couche, du bas vers le haut (`tests/test_module_dependencies.py:331`) :

```python
AI_API_LAYERS = (
    {"ai_api.deadline", "ai_api.watch_items"},
    {"ai_api.connectors.outbound", "ai_api.connectors.llm_replay"},
    {"ai_api.connectors.llm_settings", "ai_api.connectors.data_api_settings"},
    {"ai_api.connectors.llm_client", "ai_api.connectors.data_api_client"},
    {"ai_api.stages.classification", "ai_api.stages.writing"},
    {"ai_api.digests"},
)
```

La règle (`tests/test_module_dependencies.py:353-354`) : un nom importé est refusé s'il
« atteint » un module de la couche du module ou d'une couche au-dessus.

```python
    own_layer_and_above = set().union(*AI_API_LAYERS[layer:])
    return {name for name in imported if reaches(name, own_layer_and_above)}
```

`reaches` existait déjà : un nom atteint un module s'il est dans ce module, ou s'il est un paquet
qui le contient. `from k_b import ai_api` atteint donc tout, et il est refusé partout. De même,
`from k_b.ai_api import stages`, écrit depuis une étape, atteint sa propre couche et il est
refusé. Trois tests s'appuient dessus : chaque module est dans exactement une couche ; chaque
module n'importe que les couches sous la sienne ; un `__init__.py` n'importe rien d'`ai_api`.
C'est le modèle de la règle interne d'`etl`, qui existait déjà dans le même fichier.

### 4. Lire à trois niveaux : le paramètre `depth`

Le lecteur d'imports coupait chaque nom à deux niveaux sous `k_b` : `ai_api.connectors`, pour
n'importe quel module du dossier. À ce niveau, `llm_client` et `outbound` ont le même nom, et le
test ne peut pas dire lequel importe l'autre. D'où un paramètre, 2 par défaut
(`tests/test_module_dependencies.py:77`) :

```python
            ".".join(name.split(".")[1 : 1 + depth])
```

Avec `depth=3`, `from k_b.ai_api.connectors.llm_client import call_model` donne
`ai_api.connectors.llm_client`. Toutes les autres règles appellent la fonction sans `depth` :
elles lisent comme avant, et aucun test existant n'a changé.

### 5. Le correctif « may be »

La règle 3 de `conventions.md` veut qu'un texte dise ce qui est observé, et son grep
(`may be|maybe|probably|perhaps` dans `src/k_b`) trouvait la docstring de `read_failure`. Elle dit
maintenant ce que la fonction rend (`src/k_b/ai_api/connectors/llm_client.py:332-334`) :

```python
    """The state of an answer other than 200: a 429 or a 5xx gets a wait before a retry, none
    when Retry-After is above the maximum (wait_or_end); a 400 of a prompt filtered is not
    retried; any other is a provider that cannot answer this request."""
```

« is not retried » vient de la revue : une première version disait « gets none », qu'on pouvait
lire « relancé sans attente ».

## Choix faits et options écartées

- **`connectors/`** (décision de Sabine, 18/10). Écartés : `clients/` (« client » désigne déjà,
  dans `data_api`, celui qui appelle l'API avec sa clé) ; `gateways/`, `adapters/`, `outgoing/`.
- **Les réglages dans `connectors/`, pas dans un `settings/`** : `llm_settings` importe
  `llm_replay`, donc `settings/` et `connectors/` se seraient importés l'un l'autre.
- **`digests.py` à la racine, pas dans `stages/`** : c'est le parcours, pas une étape.
- **`deadline` et `watch_items` à la racine, pas dans `common/`** : un dossier pour deux modules.
- **Pas de dossier `digests/` pour toute la chaîne** : `data_api_client` importe `watch_items`.
- **Couches strictement inférieures, rien de la même couche** (décision de Sabine du 18/10, sur
  recommandation). Ce choix va plus loin que les flèches de #242 : classer et rédiger ne
  peuvent pas s'importer. Le code de `main` le respecte déjà (25 imports internes, tous vers le
  bas). Écartée : une table « module → modules permis », plus longue. Si un import latéral
  devient nécessaire un jour, on le décidera à ce moment-là.
- **Un paramètre `depth` plutôt que des noms entiers** : enlever la coupe à deux niveaux aurait
  simplifié le lecteur, mais aurait changé les tests existants, ce que le critère de #242
  interdit. C'est noté pour plus tard dans la PR.
- **Le test du sens après les déplacements, pas avant** : il nomme les nouveaux chemins, il ne
  peut pas exister avant eux. La preuve qu'il mord est faite à part (ci-dessous).
- **`config.py:60` et `:109` non recoupés** (107 et 102 caractères) : le diff de ce fichier
  reste un pur changement de chemin. Décision de time-knight, sur délégation de Sabine.
- **Imposé par une consigne** : un commit par rôle déplacé (critère de #242) ; le correctif
  « may be » dans un commit à part (mission) ; le test du sens dans un commit à part (décision
  de Sabine du 17/10).

Le commit `663c773` (`.claude/settings.json`, la mémoire automatique remise à sa valeur par
défaut) est une demande de Sabine, à part du rangement. Il n'a rien à expliquer ici.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `git diff -M --summary main...806e578` : 8 `rename` (96 à 100 %) et 2 `create` (`__init__.py`) | Les deux commits de déplacement ne sont que des renommages |
| `uv run pytest -q` : 1711 sur `main`, 1711 après chaque commit de déplacement, 1732 à la fin | Aucun test perdu ; 21 tests nouveaux, ceux du sens des imports |
| `ruff check`, `ruff format --check`, `mypy --strict` verts à chaque commit | Les imports déplacés se résolvent tous |
| Un import montant ajouté exprès à `connectors/outbound.py`, puis annulé : `test_a_module_of_ai_api_imports_only_the_layers_below_its_own` échoue | Le test lit vraiment les fichiers et attrape un import qui remonte |
| Un import ajouté exprès à `connectors/__init__.py`, puis annulé : `test_the_packages_of_ai_api_import_nothing_of_ai_api` échoue | Les `__init__.py` sont surveillés eux aussi |
| `test_the_rule_of_ai_api_refuses_its_layer_and_the_layers_above` (13 cas) | La règle refuse un import montant, un import latéral, un import du paquet et un import relatif ; elle accepte un import vers le bas |
| `grep -rniE "may be\|maybe\|probably\|perhaps" src/k_b` → rien | Règle 3 de `conventions.md` tenue |
| `/code-review high` : aucun bug, 6 constats de gravité basse, triés par time-knight | Relecture indépendante du déplacement |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi ranger un code qui marche ? »** Parce que #156 va ajouter une couche HTTP. Sans
   rangement, elle serait à plat au milieu des connecteurs et des étapes. Ranger avant coûte un
   déplacement pur ; ranger après aurait déplacé du code neuf. Le plan est celui de `data_api` :
   quand on connaît l'une des deux API, on lit l'autre.
2. **« Comment prouves-tu que rien n'a changé ? »** Git voit des renommages à 96-100 %, et les
   lignes qui changent sont des imports. Les 1711 tests de `main` passent après chaque commit de
   déplacement, ainsi que `mypy --strict`, qui vérifie chaque import.
3. **« Qu'est-ce qui empêche le rangement de se défaire ? »** Le test des couches
   (`tests/test_module_dependencies.py:331`). Un module qui importe sa couche ou une couche
   au-dessus fait échouer la CI. Un module nouveau qu'on n'a mis dans aucune couche aussi : le
   test le nomme.
4. **« Pourquoi `connectors/` et pas `services/` ? »** Le dossier regroupe ce qui parle aux
   services extérieurs : le modèle, l'API de données, et leurs réglages. C'est le pattern
   *Gateway* de Fowler. `clients/` était ambigu, parce que dans `data_api`, le client est celui
   qui appelle l'API.
5. **« Pourquoi interdire à deux étapes de s'importer ? »** Une règle d'une ligne, que le code
   respecte déjà, vaut mieux qu'une table de permissions. Si un vrai besoin apparaît, on change
   la règle en le décidant, et le changement se voit dans le test.

## Zones non vérifiées

- Le nom de journal de `llm_settings` et de `data_api_settings` devient
  `k_b.ai_api.connectors.*`. Aucun test ni réglage n'en dépend (vérifié par grep), mais rien ne
  lance encore l'API IA : aucune ligne de journal réelle n'a été observée.
- Les raisons de six options écartées (`gateways/`, `adapters/`, `outgoing/`, `services/`,
  les fichiers renommés en `<entité>_<rôle>.py`, `watch_items` sous `schemas/`) ne sont pas
  écrites dans #242. Le journal ADR le dit au lieu de les inventer.
- La CI de la PR n'a pas encore tourné au moment de la note.

## Ce qui reste

- **#156** : la couche HTTP de l'API IA, au plan de `data_api`, à la racine d'`ai_api`. Elle
  devra ajouter ses modules à `AI_API_LAYERS`, faute de quoi le test les nommera.
- **#206** : reprend les nouveaux chemins.
- **Pour plus tard, sans issue** : lire les imports à pleine profondeur au lieu de la coupe à
  deux niveaux, ce qui supprimerait `depth`. Et le choix de faire vérifier la longueur des
  lignes par `ruff` (E501), une décision d'outillage à part.
